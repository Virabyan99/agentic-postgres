"""Login, introspection, issuance, and the administrative lifecycle.

**The one rule underneath all of it:** a client never submits a role or a scope.
Both are read from the server-side record, sorted and deduplicated before
signing, and refused outright if the stored value is outside the committed
vocabulary. The request models in `models.py` have no field for either, which
makes that a property of the shape rather than of a check somebody remembers.
"""

from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from app import claims as claim_contract
from app import keys as key_module
from app import refresh_sessions
from app import scopes as scope_map
from app.errors import AuthenticationFailed, AuthorizationFailed, InvalidRequest
from app.hashing import BoundedHasher, PasswordRejected, StoredHashRejected, assess, normalize
from app.repository import AgentCredential, Credential, Repository, SubjectState
from app.tokens import LocalKeySet, MalformedToken, pre_parse

#: How long an issued token lives. The contract's ceiling, not a fraction of it:
#: a shorter default would be a second number to keep in step, and the ceiling
#: is already the figure every rotation window is computed from. A token is live
#: for `TOKEN_TTL_SECONDS + CLOCK_SKEW_SECONDS` -- 930, not 900 (D241).
TOKEN_TTL_SECONDS = claim_contract.MAX_TTL_SECONDS

#: The one `token_use` this API authenticates (ADR 0114).
#:
#: `claims.TOKEN_USES` is `("access", "agent")` and both are real: this
#: deployment issues both, and `POST /auth/agent-token` is not going away. An
#: agent token is for **PostgREST**, where role membership refuses it at
#: `SET ROLE`; this API is human-only in both of ADR 0101's modes.
#:
#: Named rather than written inline so the refusal below and
#: `test_an_agent_token_is_refused_before_any_subject_lookup` bind to one value.
#: Session 8's agent surface must state its own answer here rather than inherit
#: this one.
#:
#: (S105 matches on the NAME. "access" is a `token_use` discriminator from the
#: claim contract and is published in every token this service issues; the same
#: noqa sits on `issue`'s call sites for the same reason.)
ACCEPTED_TOKEN_USE = "access"  # noqa: S105


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    expires_at: int
    token_use: str


@dataclass(frozen=True, slots=True)
class Principal:
    """A caller whose token verified AND whose record still matches it."""

    user_id: UUID
    role_name: str
    scopes: list[str]
    state: SubjectState


class AuthService:
    """Everything the routes call. Holds the pool, the hasher and the keys.

    **Issuing and verifying are two capabilities, and this class may be given
    either or both** (ADR 0113). `auth` holds a signing key and issues; `storage`
    holds none and only verifies. The key set is therefore a **parameter** rather
    than something derived here: D381 was a storage container told it was the
    third verifier and handed nothing to verify with, because the set was
    implied by a signing key that is deliberately absent in that mode.
    """

    def __init__(
        self,
        *,
        repository: Repository,
        hasher: BoundedHasher,
        signing_key: key_module.SigningKey | None,
        key_set: LocalKeySet,
        issuer: str,
        audience: str,
        role_suffixes: dict[str, str],
    ) -> None:
        self.repository = repository
        self.hasher = hasher
        #: `None` in storage mode. Every issuing path checks it, because "this
        #: service cannot issue" is a property worth enforcing rather than a
        #: route that happens not to be mounted.
        self.signing_key = signing_key
        self.issuer = issuer
        self.audience = audience
        #: Derived role name -> suffix. The scope ceiling is keyed by SUFFIX,
        #: because the mapping is a property of the kind of identity and a
        #: per-project role name would make it a per-project authorization
        #: model (ADR 0006). The service is given the mapping rather than
        #: deriving it, because `naming.py` is the single authority and it is
        #: not in this image (ADR 0002).
        self.role_suffixes = role_suffixes
        #: Given, never derived (ADR 0113). An issuer builds it from the public
        #: half of what it signs with, so it verifies exactly what it published;
        #: a non-issuing verifier reads the rendered JWKS from a file. Both are
        #: parsed by the same loader, so a key set this service could not read
        #: is a startup failure rather than a token nobody can check.
        self.key_set = key_set

    # -- login -------------------------------------------------------------

    async def login(self, username: str, password: str) -> tuple[IssuedToken, str]:
        """Authenticate, then issue. Four failures, one outcome.

        **The order is the security property.** The password is verified before
        the status is consulted, and a subject that does not exist is verified
        against a dummy hash. So an unknown username, a wrong password and a
        disabled account all cost one Argon2 comparison at the frozen profile
        and return the same bytes. Reversing these two blocks would make a
        disabled account answer in microseconds.
        """
        credential = await self.repository.lookup(normalize(username))

        stored = credential.password_hash if credential is not None else None
        try:
            matched = await self.hasher.verify(stored, normalize(password))
        except StoredHashRejected as exc:
            # An operational fault, not a wrong password. The dummy has already
            # been verified inside `Hasher.verify`, so the cost is unchanged.
            raise AuthenticationFailed(f"stored hash unusable: {exc}") from exc

        if credential is None:
            raise AuthenticationFailed("no such subject")
        if not matched:
            raise AuthenticationFailed("password mismatch")
        if credential.status != "active":
            raise AuthenticationFailed(f"subject is {credential.status}")

        # (S106 matches on the argument name. "access" is a token_use
        # discriminator from the claim contract, published in every token.)
        issued = self.issue(credential, token_use="access")  # noqa: S106
        await self.repository.record_login(credential.user_id)

        # The session opens here rather than on first refresh, so that a client
        # holds a renewable credential from the moment it authenticates. Before
        # Session 15 there was none, and a client staying logged in past 930
        # seconds had to keep the PASSWORD and replay it (D813).
        refresh = await self.open_session(credential)
        return issued, refresh

    # -- issuance ----------------------------------------------------------

    def issue(self, credential: Credential, *, token_use: str) -> IssuedToken:
        """Mint a token from the server-side record. Nothing here is requested.

        The scopes are the stored ones, intersected with nothing and validated
        against the ceiling: a stored value outside the role's ceiling is a
        refusal rather than a quiet truncation, because a subject holding a
        scope its role may not carry is a state somebody has to know about.

        **A verifier-only runtime refuses here, before any work** (ADR 0113).
        `/auth/login` is not mounted in storage mode, so there is no caller and
        this is a defect rather than a request to deny. It is stated instead of
        left to an `AttributeError` on `None.private_pem` further down, because
        that is precisely what D381 looked like in a log.
        """
        if self.signing_key is None:
            raise RuntimeError(
                "this runtime holds no signing key and cannot issue; it is a verifier "
                "only (ADR 0101, ADR 0113)"
            )

        suffix = self.role_suffixes.get(credential.role_name)
        if suffix is None:
            raise InvalidRequest(
                "the stored role is not one this deployment derives; no token may name it"
            )
        ceiling = scope_map.ceiling(suffix)
        if ceiling is None:
            raise InvalidRequest(f"no token may name the role {suffix!r}")

        scopes = sorted(set(credential.scopes))
        beyond = set(scopes) - ceiling
        if beyond:
            raise InvalidRequest(
                f"the stored record grants {sorted(beyond)}, which a {suffix} token may not carry"
            )
        if token_use not in claim_contract.TOKEN_USES:
            raise InvalidRequest(f"token_use must be one of {claim_contract.TOKEN_USES}")

        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": str(credential.user_id),
            "role": credential.role_name,
            "scope": scopes,
            "token_use": token_use,
            # Random per token, so two tokens issued in the same second for the
            # same subject are still distinguishable -- which is what a
            # revocation list would need and what an audit trail reads.
            "jti": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + TOKEN_TTL_SECONDS,
            "credential_version": credential.credential_version,
            "authz_version": credential.authz_version,
        }

        # Verified before signing, against the same function the verifier runs.
        # An issuer that could mint a token its own verifier refuses is an
        # issuer whose contract is a comment.
        claim_contract.verify_claims(payload, issuer=self.issuer, audience=self.audience, now=now)

        token = jwt.encode(
            payload,
            self.signing_key.private_pem,
            algorithm=key_module.ALGORITHM,
            headers=key_module.jose_header(self.signing_key),
        )
        return IssuedToken(token=token, expires_at=payload["exp"], token_use=token_use)

    # -- verification ------------------------------------------------------

    async def authenticate(self, authorization: str | None) -> Principal:
        """Verify a bearer token AND confirm the record still matches it.

        Signature and shape are not enough. `credential_version` and
        `authz_version` are compared against current state inside this request,
        so a password reset, a role change, a scope change or a disable takes
        effect on the next call rather than at the next expiry -- which is
        SEC-REV-001's mechanism and the reason both claims exist.
        """
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationFailed("no bearer token")

        try:
            parsed = pre_parse(authorization[len("Bearer ") :].strip())
            key = self.key_set.resolve(parsed)
        except MalformedToken as exc:
            raise AuthenticationFailed(f"malformed token: {exc}") from exc

        try:
            payload = jwt.decode(
                parsed.token,
                jwt.PyJWK.from_dict(key).key,
                algorithms=[key_module.ALGORITHM],
                audience=self.audience,
                issuer=self.issuer,
                # Every temporal check is `verify_claims`', applied with the
                # measured skew. Letting PyJWT apply its own default would be a
                # second window, and a smaller one than PostgREST's 30 seconds.
                options={"verify_exp": False, "verify_nbf": False},
            )
        except jwt.InvalidTokenError as exc:
            raise AuthenticationFailed(f"signature or registered claim: {exc}") from exc

        try:
            verified = claim_contract.verify_claims(
                payload, issuer=self.issuer, audience=self.audience, now=int(time.time())
            )
        except claim_contract.ClaimError as exc:
            raise AuthenticationFailed(f"claim contract: {exc}") from exc

        # Only an ACCESS token reaches this API, and it is refused here rather
        # than by the shape of the tables below (ADR 0114).
        #
        # `TOKEN_USES` carries `"agent"` too, correctly: this deployment issues
        # both, and `POST /auth/agent-token` exists. An agent token is for
        # PostgREST, where role membership refuses it at `SET ROLE`. Nothing was
        # ever meant to present one here.
        #
        # Before it did, this refused anyway -- an agent's `sub` is an agent id,
        # `auth_user_state` knows only humans, and the lookup below returned
        # nothing, so the caller got 401 "the subject no longer exists". Correct
        # outcome, false reason: the agent exists. A boundary that holds because
        # of which table a row is in is not a boundary anybody chose, and it
        # would silently change the day `authenticate` learned about agents.
        #
        # 401 and not 403: this runtime cannot check an agent against the record
        # -- that comparison is ADR 0095's whole model and it has no agent half
        # -- so a 403 would claim an authentication that never happened.
        if verified["token_use"] != ACCEPTED_TOKEN_USE:
            raise AuthenticationFailed(
                f"token_use {verified['token_use']!r} is not accepted by this API"
            )

        try:
            user_id = UUID(verified["sub"])
        except ValueError as exc:
            raise AuthenticationFailed("sub is not a uuid") from exc

        state = await self.repository.state(user_id)
        if state is None:
            raise AuthenticationFailed("the subject no longer exists")
        if state.status != "active":
            raise AuthenticationFailed(f"the subject is {state.status}")
        if verified["credential_version"] != state.credential_version:
            raise AuthenticationFailed("credential_version is stale")
        if verified["authz_version"] != state.authz_version:
            raise AuthenticationFailed("authz_version is stale")
        if verified["role"] != state.role_name:
            raise AuthenticationFailed("the role has changed")
        if list(verified["scope"]) != sorted(state.scopes):
            raise AuthenticationFailed("the scopes have changed")

        return Principal(
            user_id=user_id,
            role_name=state.role_name,
            scopes=sorted(state.scopes),
            state=state,
        )

    @staticmethod
    def require_scope(principal: Principal, scope: str) -> None:
        """API-ADMIN-001: the scope, never the role.

        A `project_admin` without `admin_users:write` is refused, and that is
        the requirement rather than a nicety -- a check on the role name would
        pass every test that only ever issued tokens to real administrators.
        """
        if scope not in principal.scopes:
            raise AuthorizationFailed(scope)

    # -- the administrative lifecycle -------------------------------------

    async def create_user(
        self,
        *,
        username: str,
        display_name: str,
        role_suffix: str,
        scopes: list[str],
        password: str,
        forbidden: tuple[str, ...] = (),
    ) -> UUID:
        role_name = self._role_name(role_suffix)
        checked = self._check_scopes(role_suffix, scopes)
        hashed = await self._hash(password, forbidden=forbidden)
        return await self.repository.create_user(
            username=normalize(username),
            display_name=normalize(display_name),
            role_name=role_name,
            scopes=checked,
            password_hash=hashed,
        )

    async def set_authorization(
        self, user_id: UUID, *, role_suffix: str, scopes: list[str]
    ) -> int | None:
        role_name = self._role_name(role_suffix)
        checked = self._check_scopes(role_suffix, scopes)
        return await self.repository.set_authorization(user_id, role_name=role_name, scopes=checked)

    async def set_status(self, user_id: UUID, status: str) -> int | None:
        if status not in ("active", "disabled"):
            raise InvalidRequest("status must be 'active' or 'disabled'")
        return await self.repository.set_status(user_id, status)

    async def set_password(
        self, user_id: UUID, password: str, *, forbidden: tuple[str, ...] = ()
    ) -> int | None:
        return await self.repository.set_password(
            user_id, await self._hash(password, forbidden=forbidden)
        )

    # -- helpers -----------------------------------------------------------

    def _role_name(self, role_suffix: str) -> str:
        for name, suffix in self.role_suffixes.items():
            if suffix == role_suffix:
                return name
        raise InvalidRequest(f"this deployment derives no role named {role_suffix!r}")

    def _check_scopes(self, role_suffix: str, scopes: list[str]) -> list[str]:
        """Sorted, deduplicated, and inside the ceiling -- or refused.

        The sort happens here rather than being required of the caller, because
        the database's CHECK requires it too and a client that had to know that
        would be a client encoding a storage detail.
        """
        ceiling = scope_map.ceiling(role_suffix)
        if ceiling is None:
            raise InvalidRequest(f"no token may name the role {role_suffix!r}")
        requested = sorted(set(scopes))
        if not requested:
            raise InvalidRequest(
                "a subject with no scopes has an authority nothing describes; the claim "
                "is required and may not be empty"
            )
        beyond = set(requested) - ceiling
        if beyond:
            raise InvalidRequest(
                f"a {role_suffix} may not hold {sorted(beyond)}; the ceiling is {sorted(ceiling)}"
            )
        return requested

    # -- agents ------------------------------------------------------------

    async def agent_token(self, agent_id: str, secret: str) -> IssuedToken:
        """Exchange an agent's id and secret for a token. Same shape as a login.

        The failure path is identical to `login`'s and for the same reasons: the
        secret is verified before the status is consulted, an unknown id is
        verified against the dummy hash, and every outcome is one
        `AuthenticationFailed`. An agent that has been revoked must not be
        distinguishable from one that never existed.

        **The token is issued even though agent access is not live.** That is
        deliberate and is §6's stated design: `postgrest_authenticator` holds no
        membership in either agent role, so PostgREST refuses the token at `SET
        ROLE` before the pre-request hook runs. Session 9 of the product
        activates it; measured here as `permission denied to set role`.
        """
        try:
            identifier = UUID(agent_id)
        except ValueError:
            # Still pay for a hash. An id that is not a UUID would otherwise be
            # the one failure that answers in microseconds.
            await self.hasher.verify(None, secret)
            raise AuthenticationFailed("agent id is not a uuid") from None

        credential = await self.repository.lookup_agent(identifier)
        stored = credential.secret_hash if credential is not None else None
        try:
            matched = await self.hasher.verify(stored, secret)
        except StoredHashRejected as exc:
            raise AuthenticationFailed(f"stored hash unusable: {exc}") from exc

        if credential is None:
            raise AuthenticationFailed("no such agent")
        if not matched:
            raise AuthenticationFailed("secret mismatch")
        if credential.status != "active":
            raise AuthenticationFailed(f"agent is {credential.status}")

        # (S106 matches on the argument name; "agent" is a token_use
        # discriminator from the claim contract, published in every token.)
        return self.issue(self._as_credential(credential), token_use="agent")  # noqa: S106

    @staticmethod
    def _as_credential(agent: AgentCredential) -> Credential:
        """An agent, in the shape `issue` reads.

        `credential_version` is 0, not 1, and not the `authz_version`. An agent
        has no password, so there is no version of one -- and the contract
        requires the claim to be present and non-negative, so it is present and
        it is zero. Reusing `authz_version` for both would make a rotation move
        two claims that mean different things, and a reader could not tell which
        of them a mismatch referred to.
        """
        return Credential(
            user_id=agent.agent_id,
            role_name=agent.role_name,
            scopes=agent.scopes,
            status=agent.status,
            credential_version=0,
            authz_version=agent.authz_version,
            password_hash=None,
        )

    async def create_agent(
        self,
        *,
        name: str,
        description: str,
        role_suffix: str,
        scopes: list[str],
        owner_id: UUID,
    ) -> tuple[UUID, str]:
        """Returns the id AND the secret, once.

        The plaintext is returned to the caller and never stored: the column
        holds an Argon2id verifier at the frozen profile, there is no retrieval
        function in either migration, and the documented recovery for a lost
        secret is to rotate. `test_no_endpoint_returns_an_agent_secret_twice`
        asserts the absence rather than trusting it.
        """
        role_name = self._role_name(role_suffix)
        checked = self._check_scopes(role_suffix, scopes)
        secret, hashed = await self._mint_secret()
        agent_id = await self.repository.create_agent(
            name=normalize(name),
            description=normalize(description),
            role_name=role_name,
            scopes=checked,
            owner_id=owner_id,
            secret_hash=hashed,
        )
        return agent_id, secret

    async def rotate_agent_secret(self, agent_id: UUID) -> tuple[str, int] | None:
        secret, hashed = await self._mint_secret()
        version = await self.repository.rotate_agent_secret(agent_id, hashed)
        return None if version is None else (secret, version)

    async def set_agent_authorization(
        self, agent_id: UUID, *, role_suffix: str, scopes: list[str]
    ) -> int | None:
        role_name = self._role_name(role_suffix)
        checked = self._check_scopes(role_suffix, scopes)
        return await self.repository.set_agent_authorization(
            agent_id, role_name=role_name, scopes=checked
        )

    async def set_agent_status(self, agent_id: UUID, status: str) -> int | None:
        if status not in ("active", "revoked"):
            # `revoked`, not `disabled`. 0011 gave agents their own enum because
            # the words differ in kind: a user is disabled and can be re-enabled,
            # an agent credential is revoked, which is terminal for that
            # credential. Accepting the other vocabulary here would let a caller
            # write a state the column cannot hold and find out from a 500.
            raise InvalidRequest("status must be 'active' or 'revoked'")
        return await self.repository.set_agent_status(agent_id, status)

    async def _mint_secret(self) -> tuple[str, str]:
        """A one-time secret and its verifier.

        `token_urlsafe(32)` is 256 bits from the OS. It is NOT run through
        `assess`: that function screens things a person chose, and its blocklist
        and length rules are about human habits. A refusal here would be a
        random string failing a policy written for passwords.
        """
        secret = secrets.token_urlsafe(32)
        return secret, await self.hasher.hash(secret)

    async def _hash(self, password: str, *, forbidden: tuple[str, ...]) -> str:
        try:
            screened = assess(password, forbidden=forbidden)
        except PasswordRejected as exc:
            # The one place a specific reason is right: the subject already
            # knows the value, so saying why leaks nothing, and refusing
            # silently produces eleven variations of the same weak password.
            raise InvalidRequest(str(exc)) from exc
        return await self.hasher.hash(screened)

    # -- the session plane (Session 15 Run 3, ADR 0171) ---------------------

    async def open_session(self, credential: Credential) -> str:
        """Mint the first refresh token of a session and store only its digest.

        Called after `login` has already authenticated. The token is returned to
        exactly one HTTP response and retained nowhere: this method is the only
        place in the service that holds one, and it holds it for the length of a
        return statement.
        """
        token, digest = refresh_sessions.mint()
        expires_at = datetime.now(UTC) + timedelta(seconds=refresh_sessions.REFRESH_TTL_SECONDS)
        await self.repository.open_session(credential.user_id, digest, expires_at)
        return token

    async def refresh(self, presented: str) -> tuple[IssuedToken, str]:
        """Exchange a refresh token for an access token and its successor.

        **Every refusal answers identically**, which is `login`'s shape and is
        the same reason: an unknown token, a replayed one, a revoked family and
        an expired token are four causes a caller does not need distinguished,
        and distinguishing them would tell whoever presented a guess whether it
        named something real. The reason travels to the log, as
        `AuthenticationFailed` has always carried one.

        **A refused refresh is translated, never relayed** (D433, ADR 0139).
        There is no upstream status here to pass on and there will not be one:
        the outcome is computed from facts this deployment holds.
        """
        if not refresh_sessions.is_wellformed(presented):
            # Refused before a query. Not a security boundary -- the digest
            # lookup is that -- but a value this plane could not have minted is
            # a caller error, and answering it without a round trip is honest.
            raise AuthenticationFailed("malformed refresh token")

        token, digest = refresh_sessions.mint()
        expires_at = datetime.now(UTC) + timedelta(seconds=refresh_sessions.REFRESH_TTL_SECONDS)
        attempt = await self.repository.consume_refresh_token(
            refresh_sessions.hash_token(presented), digest, expires_at
        )

        if not attempt.rotated:
            outcome = refresh_sessions.classify(
                refresh_sessions.TokenState(
                    found=attempt.found,
                    consumed=attempt.was_consumed,
                    family_revoked=attempt.family_revoked,
                    expires_at=int(attempt.expires_at.timestamp())
                    if attempt.expires_at is not None
                    else 0,
                ),
                now=int(datetime.now(UTC).timestamp()),
            )
            # The family was already revoked inside the function when the
            # outcome is REUSE -- detection and response are one transaction,
            # because a service that found a leaked chain and died before
            # revoking it would have left the chain live.
            raise AuthenticationFailed(f"refresh refused: {outcome.value}")

        # Rotated. The subject's CURRENT authority is read again rather than
        # carried in the refresh token: a refresh token names a session, and a
        # session is not a claim about what its owner may do. So a disable, a
        # role change or a scope change takes effect at the next refresh, which
        # is the same property `authenticate` gives an access token.
        state = await self.repository.state(attempt.user_id)
        if state is None or state.status != "active":
            raise AuthenticationFailed("subject is not active at refresh")

        issued = self.issue(
            Credential(
                user_id=attempt.user_id,
                role_name=state.role_name,
                scopes=state.scopes,
                status=state.status,
                credential_version=state.credential_version,
                authz_version=state.authz_version,
                password_hash=None,
            ),
            token_use="access",  # noqa: S106
        )
        return issued, token

    async def list_sessions(self, principal: Principal) -> list[dict[str, Any]]:
        """Every session this subject has, live or ended.

        Ended families are included rather than filtered: a session that ended
        in `reuse_detected` is the row its owner most needs to see, and hiding
        it would make the alarm visible only to an operator.
        """
        rows = await self.repository.list_sessions(principal.user_id)
        return [
            {
                "session_id": str(row["family_id"]),
                "created_at": row["created_at"].isoformat(),
                "last_used_at": row["last_used_at"].isoformat(),
                "revoked_at": row["revoked_at"].isoformat() if row["revoked_at"] else None,
                "revoked_reason": row["revoked_reason"],
            }
            for row in rows
        ]

    async def terminate_session(self, principal: Principal, session_id: UUID) -> bool:
        """End one of this subject's sessions. Scoped in SQL, not here.

        `auth_revoke_session` filters on the owner, so a caller naming another
        subject's family id gets the same `false` as one naming a family that
        does not exist. The scoping is in the function rather than in a check
        here because a second caller added later would have to remember this
        one, and D204's lesson is that the guard belongs where every caller
        passes through it.
        """
        return await self.repository.revoke_session(
            principal.user_id,
            session_id,
            refresh_sessions.RevocationReason.LOGGED_OUT.value,
        )

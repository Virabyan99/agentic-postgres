"""Login, introspection, issuance, and the administrative lifecycle.

**The one rule underneath all of it:** a client never submits a role or a scope.
Both are read from the server-side record, sorted and deduplicated before
signing, and refused outright if the stored value is outside the committed
vocabulary. The request models in `models.py` have no field for either, which
makes that a property of the shape rather than of a check somebody remembers.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt

from app import claims as claim_contract
from app import keys as key_module
from app import scopes as scope_map
from app.errors import AuthenticationFailed, AuthorizationFailed, InvalidRequest
from app.hashing import BoundedHasher, PasswordRejected, StoredHashRejected, assess, normalize
from app.repository import Credential, Repository, SubjectState
from app.tokens import LocalKeySet, MalformedToken, pre_parse

#: How long an issued token lives. The contract's ceiling, not a fraction of it:
#: a shorter default would be a second number to keep in step, and the ceiling
#: is already the figure every rotation window is computed from. A token is live
#: for `TOKEN_TTL_SECONDS + CLOCK_SKEW_SECONDS` -- 930, not 900 (D241).
TOKEN_TTL_SECONDS = claim_contract.MAX_TTL_SECONDS


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
    """Everything the routes call. Holds the pool, the hasher and the key."""

    def __init__(
        self,
        *,
        repository: Repository,
        hasher: BoundedHasher,
        signing_key: key_module.SigningKey,
        issuer: str,
        audience: str,
        role_suffixes: dict[str, str],
    ) -> None:
        self.repository = repository
        self.hasher = hasher
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
        #: The service verifies with the same public material it publishes,
        #: parsed through the same loader a verifier would use -- so a JWKS this
        #: service could not read is a startup failure rather than a token
        #: nobody can check.
        self.key_set = LocalKeySet.load(json.dumps(signing_key.jwks()).encode("utf-8"))

    # -- login -------------------------------------------------------------

    async def login(self, username: str, password: str) -> IssuedToken:
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
        return issued

    # -- issuance ----------------------------------------------------------

    def issue(self, credential: Credential, *, token_use: str) -> IssuedToken:
        """Mint a token from the server-side record. Nothing here is requested.

        The scopes are the stored ones, intersected with nothing and validated
        against the ceiling: a stored value outside the role's ceiling is a
        refusal rather than a quiet truncation, because a subject holding a
        scope its role may not carry is a state somebody has to know about.
        """
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

    async def _hash(self, password: str, *, forbidden: tuple[str, ...]) -> str:
        try:
            screened = assess(password, forbidden=forbidden)
        except PasswordRejected as exc:
            # The one place a specific reason is right: the subject already
            # knows the value, so saying why leaks nothing, and refusing
            # silently produces eleven variations of the same weak password.
            raise InvalidRequest(str(exc)) from exc
        return await self.hasher.hash(screened)

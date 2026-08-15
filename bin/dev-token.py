#!/usr/bin/env python
"""Mint a short-lived bootstrap token and hand it to a child. Never print one.

D105's rule, stricter than the specification it comes from: **there is no flag
that prints a credential**, because a flag that prints one is a credential in a
scrollback buffer, a shell history, a screen share and a support ticket. So this
command does not emit a token at all. It signs one, puts it in the environment
of a child process through `execve`, and replaces itself with that child.

`execve` and not `env VAR=... command`: the second puts the token in `env`'s own
argument vector, where every user on the host can read it out of `ps`. The
environment block is readable only by the process's own user through `/proc`,
which is the difference this whole design turns on.

**Nothing about the token is chosen by the caller, and it carries no subject at
all.** The role is one of three enumerated names resolved through the deployed
document; the lifetime is bounded; the issuer and audience come from the
document. A caller who could name a role, a subject and a lifetime would be a
caller who could mint any credential this issuer can sign.

The subject was *derived* from the project until Run 14, which was the same
argument one step short. Migration 0013 compares a subject against
`app_private.users` inside the request transaction, so a derived subject names
nobody and is refused. **This issuer names a role; the auth service names a
subject** (ADR 0095) -- which means a token from here can reach the surface and
can read no owner's rows, and that is the property rather than a shortfall.

Signing is `openssl dgst -sha256 -sign`, measured end to end against the locked
PostgREST before this was written: a token signed that way and verified against
the JWKS derived from the same key answers **200**, a token signed by a
different key is **401 `PGRST301`** ("None of the keys was able to decode the
JWT"), and an expired one is **401 `PGRST303`". There is no hash-locked JWT
dependency in `requirements-dev.txt` and no crypto in the standard library, so
openssl is not a shortcut here -- it is the only route that adds no unlocked
input, and ADR 0051 measured only that PostgREST accepts RS256, not how to
produce one.

Exit codes (runbook §2 convention):
  0  the child's exit code is what you get; this process is replaced
  2  invalid operator input
  3  missing local prerequisite, or not root
  5  the deployed document or the signing key is unusable
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import jwt_claims, jwt_keys, scope_registry, secrets_contract
from agentic_postgres.secret_generation import SECRET_ROOT

#: The three roles a token may name, and the key each resolves through in the
#: deployed document's `database.roles`. An enumeration rather than a
#: pass-through: `SET ROLE` is bounded by the authenticator's memberships, but a
#: tool that will ask for any role is a tool that probes for the boundary rather
#: than staying inside it.
#:
#: `object_owner`, `migration_user`, `app_runtime` and the two agent roles are
#: deliberately absent. The authenticator is not a member of any of them, so a
#: token naming one is 403 -- and a command that offers the option invites
#: somebody to find out.
#:
#: That last paragraph was a comment. `scope_registry.permitted_scopes` refuses
#: a role no token may name, so it is now a check: a fourth entry here naming a
#: service identity fails offline rather than at a 403 somebody has to diagnose
#: (ADR 0079). The agent roles are the interesting case -- they ARE nameable by a
#: token, and are absent from this map for the different reason that Session 9
#: grants their memberships.
ROLES: dict[str, str] = {
    "anon": "anon",
    "authenticated": "authenticated",
    "docs": "api_documentation",
}

#: Which environment variable each role's token arrives in. Separate names so a
#: reader token cannot be picked up by a tool expecting a documentation one --
#: they authorize different things, and `bin/api-contract.sh` reads exactly one.
TOKEN_VARIABLES: dict[str, str] = {
    "anon": "APG_API_TOKEN",
    "authenticated": "APG_API_TOKEN",
    "docs": "APG_DOCS_TOKEN",
}

#: The bound on a token's life. Fifteen minutes is long enough for a capture and
#: short enough that a leaked one is a smaller problem than the leak.
#:
#: Read from `jwt_claims` rather than restated (ADR 0078). It was written here
#: and there as the same literal, which is the D177 shape -- and the number is
#: no longer only a policy: a token is actually live for
#: `MAX_TTL_SECONDS + CLOCK_SKEW_SECONDS`, because the locked PostgREST was
#: measured to accept a token 30 seconds past its expiry (D241). Anything
#: reasoning about how long a token can be used reads the sum.
DEFAULT_TTL_SECONDS = 300
MAX_TTL_SECONDS = jwt_claims.MAX_TTL_SECONDS

#: The root-plane file the signing key is materialized into (ADR 0054, 0055).
SIGNING_KEY_FILE = "bootstrap_jwt_signing_key.pem"

#: There is no subject namespace any more, and its absence is the decision
#: (ADR 0095). `SUBJECT_NAMESPACE` and `development_subject()` derived a stable
#: per-project UUIDv5 so that a caller could not choose one. Migration 0013
#: settled the question differently and more strictly: a subject is compared
#: against `app_private.users` inside the request transaction, so a derived one
#: names nobody and is refused with `PT401`. This issuer names a **role**; the
#: auth service names a subject.


class TokenError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_deployed(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TokenError(2, f"deployed document not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TokenError(2, f"cannot read {path}: {error}") from error
    if document.get("document_kind") != "deployed":
        raise TokenError(
            2,
            "that is a rendered document, not a deployed one. A rendered document "
            "describes what was asked for; the roles and the issuer this token "
            "carries are what a deployment actually established.",
        )
    return document


def signing_key_path(project_key: str, document: dict[str, Any]) -> Path:
    """The active generation's root-plane copy of the signing key.

    The generation comes from the deployed document, so the key used is the one
    that deployment recorded -- not whatever happens to be newest. D76 is the
    standing lesson: the document's generation is deploy-time history and the
    live pointer moves at the first restart, and reading the wrong one here
    would sign with a key the running service does not verify against.
    """
    generation = (document.get("secrets") or {}).get("generation_id")
    if not generation:
        raise TokenError(5, "the deployed document records no secret generation")
    path = (
        SECRET_ROOT
        / project_key
        / "generations"
        / generation
        / secrets_contract.ROOT_PLANE_DIRECTORY
        / SIGNING_KEY_FILE
    )
    if not path.is_file():
        raise TokenError(
            5,
            f"no signing key at {path}. The bootstrap issuer's key is materialized by "
            "the deploy into the root plane; a project deployed before session 5 has none.",
        )
    return path


def base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def key_id(key_path: Path) -> str:
    """The RFC 7638 thumbprint of the key at `key_path`.

    Loaded from `bin/render-jwks.py` rather than reimplemented, for the reason
    `tests/deployment/conftest.py:jwks_command` already gives: the derivation has
    the shape it does because the obvious spelling (`openssl rsa -in <private>
    -noout -text`) prints `privateExponent` and both primes, and because openssl
    labels the exponent differently for a public and a private key. A second copy
    would be written from the obvious spelling.

    Imported here rather than at module scope so that a caller who only wants
    `signing_key_path` or `development_subject` -- and the test suite, which
    imports this module off-host -- does not pay for a command that shells out to
    openssl (ADR 0094).
    """
    import importlib.util

    source = Path(__file__).resolve().parent / "render-jwks.py"
    specification = importlib.util.spec_from_file_location("apg_dev_token_jwks", source)
    if specification is None or specification.loader is None:
        raise TokenError(3, f"cannot load {source}")
    jwks_command = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(jwks_command)

    try:
        modulus, exponent = jwks_command.read_public_parameters(key_path)
    except Exception as error:
        # The message, never the path's contents: this function is handed a
        # private key and openssl prints material from one on some failures.
        raise TokenError(5, f"could not derive this key's identifier: {error}") from error
    return jwt_keys.public_jwk(modulus_hex=modulus, exponent=exponent)["kid"]


def mint(
    *, key_path: Path, role_name: str, subject: str | None, ttl: int, document: dict[str, Any]
) -> str:
    """Sign an RS256 token. The return value is a credential: do not log it.

    **The `kid` is derived from `key_path`, not read from the document** (ADR
    0094). It was `jwt.active_kid` until Run 13, and that was correct for exactly
    as long as the published set held one key. `render-jwks.py` publishes the
    auth service's key *first* from Session 6, `observe_jwt` takes
    `active_kid = kids[0]`, and this function signs with the **bootstrap** key --
    so every token minted after that deploy was signed by one key and labelled
    with the other's identifier.

    Measured against the locked PostgREST, four arms: signed-by-bootstrap
    labelled-auth is **401 `PGRST301`**, while the same token labelled with the
    bootstrap key's own `kid` is 200, with no `kid` at all is 200, and the auth
    key's own token is 200. The image selects by `kid`; the three controls are
    what make that attributable to the label rather than to the signature.
    Confirmed on alpha-dev through this command, against the published route,
    with an unauthenticated 200 as the control that the route was never the
    problem.

    A thumbprint is a function of the key (ADR 0051), so deriving it here is the
    one spelling under which the label cannot disagree with the signature.
    """
    jwt = document.get("jwt") or {}
    now = int(time.time())
    header: dict[str, Any] = {"alg": "RS256", "typ": "JWT", "kid": key_id(key_path)}

    claims: dict[str, Any] = {"role": role_name, "iat": now, "exp": now + ttl}
    if jwt.get("issuer"):
        claims["iss"] = jwt["issuer"]
    if jwt.get("audience"):
        claims["aud"] = jwt["audience"]
    if subject is not None:
        claims["sub"] = subject

    signing_input = (
        f"{base64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{base64url(json.dumps(claims, separators=(',', ':')).encode())}"
    ).encode("ascii")

    # The key reaches openssl as a path, and the payload over stdin. Neither the
    # key nor the signature is ever an argument.
    signed = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
        input=signing_input,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if signed.returncode != 0:
        # stderr deliberately not echoed: openssl prints the key's path and, on
        # some failures, material from it.
        raise TokenError(5, "openssl could not sign with the bootstrap key")

    return f"{signing_input.decode('ascii')}.{base64url(signed.stdout)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dev-token",
        description="Mint a short-lived bootstrap token and exec a command with it.",
        allow_abbrev=False,
    )
    parser.add_argument("--project-outputs", metavar="FILE", required=True)
    parser.add_argument("--role", choices=sorted(ROLES), required=True)
    parser.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL_SECONDS, metavar="N")
    parser.add_argument("command", nargs=argparse.REMAINDER)

    arguments = parser.parse_args(argv)

    try:
        if not arguments.command:
            raise TokenError(
                2,
                "a command is required after `--`. This tool has no way to give you a "
                "token: it puts one in a child's environment and becomes that child.",
            )
        command = arguments.command[1:] if arguments.command[0] == "--" else arguments.command
        if not command:
            raise TokenError(2, "a command is required after `--`.")

        if not 1 <= arguments.ttl_seconds <= MAX_TTL_SECONDS:
            raise TokenError(2, f"--ttl-seconds must be between 1 and {MAX_TTL_SECONDS}")

        if os.geteuid() != 0:
            raise TokenError(
                3,
                "must run as root: the bootstrap signing key is materialized 0400 owned "
                "by root, which is what makes 'no service holds it' a filesystem fact.",
            )

        document = load_deployed(Path(arguments.project_outputs))
        project_key = document["project"]["key"]
        roles = (document.get("database") or {}).get("roles") or {}
        role_key = ROLES[arguments.role]
        # Refuses a role no token may name (ADR 0079). Nothing is minted with the
        # scopes yet -- the bootstrap issuer has no subject records to draw them
        # from, and full issuance arrives with the auth service -- but the
        # *nameability* half is checkable now, and it is the half whose failure
        # mode is a 403 somebody has to attribute.
        scope_registry.permitted_scopes(role_key)
        role_name = roles.get(role_key)
        if not role_name:
            raise TokenError(
                5,
                f"the deployed document declares no {role_key!r} role. A document below "
                "outputs schema v6 has no documentation role at all.",
            )

        # NO ROLE GETS A SUBJECT (ADR 0095). This read
        # `None if arguments.role == "docs" else development_subject(...)` until
        # Run 14, when the first host gate after migration 0013 answered `PT401`
        # to every token that named one.
        #
        # 0013's hook compares a subject against `app_private.users` inside the
        # request's own transaction, and `auth_claims_are_current` is an EXISTS
        # over five equalities including `credential_version`, `authz_version`
        # and an exact scope array. A bootstrap token carries none of those
        # three, so the comparison is against NULL and NO value of the subject
        # can satisfy it. Only the identity registry's own issuer can name a
        # subject, which is the property rather than the limitation -- and it is
        # the one this module's docstring has argued for since Session 5.
        #
        # Migration 0009's older rule is subsumed: the documentation role was
        # already refused a subject, and now nothing has one.
        token = mint(
            key_path=signing_key_path(project_key, document),
            role_name=role_name,
            subject=None,
            ttl=arguments.ttl_seconds,
            document=document,
        )
    except TokenError as error:
        print(f"dev-token: {error}", file=sys.stderr)
        return error.code

    print(
        f"dev-token: minted a {arguments.role} token for {arguments.ttl_seconds}s and "
        f"exec'd {command[0]}. The token is in this process's environment and in no "
        "argument, no file and no output.",
        file=sys.stderr,
    )

    environment = {**os.environ, TOKEN_VARIABLES[arguments.role]: token}
    try:
        # Replaces this process. The token crosses into the child through the
        # environment block of `execve`, never through an argument vector.
        os.execvpe(command[0], command, environment)  # noqa: S606
    except OSError as error:
        print(f"dev-token: cannot execute {command[0]}: {error}", file=sys.stderr)
        return 3
    return 0  # unreachable: execvpe does not return


if __name__ == "__main__":
    raise SystemExit(main())

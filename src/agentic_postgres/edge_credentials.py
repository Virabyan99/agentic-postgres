"""The documentation credential, and the middleware that checks it.

The one per-project artifact this repository writes into Traefik's file
provider. Everything else a project contributes to the edge is a container
label, and this is the exception for a reason that has changed twice.

**It is not because a label cannot express it.** D163 measured that: a container
carrying `traefik.http.middlewares.<n>.basicauth.usersfile=…` produces a working
middleware, 401 without a credential and 200 with it. **Nor is it any longer
about a container's lifecycle**, which is what this docstring said next until Run
10 measured it — a middleware in the file provider does not keep a route alive
while its backend is down, because the *router* is a label and is withdrawn with
the container whatever its middleware is doing (ADR 0085).

**It is a rule about where a secret may go.** Since ADR 0086 the middleware
carries the bcrypt hash inline, and a label carrying it would put a credential
into Compose interpolation — one of the five places CLAUDE.md forbids a secret
value to reach. It would also need every `$` doubled, and a hash that survived
interpolation half-escaped is a 401 on a correct password, which is D165's
failure through a new door.

**The hash is inline, and that is D252's fix** (ADR 0086). It used to live in a
sibling `.htpasswd` file named by a `usersFile` key. Measured on the host during
the first documentation-credential rotation this project ever performed: the new
password returned 401 and **the old password returned 200**, with the correct new
hash on disk throughout. The middleware names a *path*, so rewriting the file
behind it leaves the parsed configuration identical, Traefik has nothing to
rebuild, and the middleware never re-reads a file it has already read.

Re-measured offline against the locked image, with a control that tells the two
passwords apart: rewriting the users file changes nothing (old 200, new 401);
changing one byte inside the middleware's own definition makes the same rewrite
take effect (old 401, new 200); and the hash written inline and rewritten in
place takes effect on its own. So the rule is **the artifact a rotation rewrites
must be the artifact the provider parses** — otherwise the correct-looking
action is a no-op and the credential is rotated everywhere except where it is
checked.

**Nothing here hashes anything.** `crypt` was removed from the standard library
in Python 3.13 and the deployment host's interpreter is past that, so a hash
cannot be produced by the code that runs the deploy. The locked Python runtime
image is 3.12 and its glibc offers `METHOD_BLOWFISH`, so the hash is produced
*there* — in a container, from a locked digest — and arrives here as a string
this module validates and refuses. That split is deliberate: the validation is
pure and testable, and the one impure step is a container invocation the caller
owns.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from agentic_postgres.config import ManifestError

#: The user in the generated htpasswd file. One, always, and named rather than
#: derived: an operator types it, and a per-project username would be a second
#: derived identity whose only job is to be remembered.
DOCS_USER = "docs"

#: Where the edge's file provider reads from, as Traefik sees it. The host side
#: is `/var/lib/agentic-postgres/edge/dynamic`, mounted read-only.
TRAEFIK_DYNAMIC_DIR = "/etc/traefik/dynamic"

#: bcrypt, and only bcrypt.
#:
#: Traefik accepts several htpasswd formats and fails the same way for all the
#: ones it does not: **401 on a correct password**, with nothing in the log to
#: say the hash was the problem. Measured -- a SHA-512 crypt hash (`$6$`), which
#: is what `crypt.crypt` produces by default and what any `mkpasswd` on the host
#: hands you, is refused exactly like a wrong password. `$2b$` from
#: `METHOD_BLOWFISH` was measured to work.
#:
#: So the format is checked here rather than discovered on the host, because the
#: symptom of getting it wrong is indistinguishable from the operator typing the
#: password incorrectly.
_BCRYPT = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")

__all__ = [
    "DOCS_USER",
    "TRAEFIK_DYNAMIC_DIR",
    "assert_bcrypt",
    "htpasswd_entry",
    "middleware_document",
    "middleware_file_name",
    "render_middleware",
    "retired_users_file_name",
]


def assert_bcrypt(hashed: str) -> str:
    """Refuse anything Traefik would answer 401 to.

    The value is not echoed on failure. It is a password hash, and a message
    quoting it would put it in whatever log the deploy writes to -- which is the
    one place a hash is materially easier to attack than a password, because
    nothing rate-limits a file.
    """
    if not isinstance(hashed, str) or not _BCRYPT.match(hashed):
        raise ManifestError(
            "the documentation credential hash is not bcrypt. Traefik refuses every "
            "other htpasswd format with a 401 that is indistinguishable from a wrong "
            "password, so the format is checked here rather than on the host"
        )
    return hashed


def htpasswd_entry(hashed: str, *, user: str = DOCS_USER) -> str:
    """One `user:hash` entry, unterminated.

    One entry, not a list of them: a second entry is a second credential nobody
    rotates, and this middleware is generated from exactly one materialized
    secret.

    Unterminated because it is a YAML scalar now rather than a line in a file.
    A trailing newline in `basicAuth.users` would be part of the hash Traefik
    compares against, which fails as a 401 on a correct password -- the one
    failure mode this module exists to keep off the host (D165).
    """
    if ":" in user or not user:
        raise ManifestError(f"not a usable htpasswd user: {user!r}")
    return f"{user}:{assert_bcrypt(hashed)}"


def middleware_file_name(project_key: str) -> str:
    return f"project-{project_key}.yaml"


def retired_users_file_name(project_key: str) -> str:
    """The file this design used to write, so the deploy can remove it.

    Not a path this repository writes any more. It is named here because every
    project deployed before ADR 0086 has one sitting in the dynamic directory,
    holding a bcrypt hash of a credential nothing reads -- and a stale
    credential file that no rotation reaches is exactly the artifact this
    project keeps finding. The deploy unlinks it; the name has to come from
    somewhere, and one authority beats a literal in `bin/`.
    """
    return f"{project_key}.htpasswd"


def middleware_document(*, middleware_name: str, project_key: str, hashed: str) -> dict[str, Any]:
    """The per-project dynamic configuration: one middleware, nothing else.

    No router and no service, and ADR 0085 is now the reason rather than a
    guess about one. Measured against the locked Traefik: a router and service
    in the file provider answer 502 while their backend is down, where a
    label-defined router answers Traefik's own 404 -- which is the more legible
    failure and is not reachable here, because a file-provider service can only
    address its backend by DNS and the Compose service name resolves to
    whichever project the edge attached to first (ten resolutions, ten times
    project A, project B unreachable). A router here would serve one tenant's
    requests from another tenant's container.

    **The hash is inline** (ADR 0086, D252). It was a `usersFile` naming a
    sibling path, which meant a rotation rewrote a file the parsed
    configuration did not mention: Traefik saw no change, rebuilt nothing, and
    kept honouring the previous password. Inline, the rotation *is* a change to
    the document the provider parses.

    `removeHeader: true` is the clause that matters. Without it the
    `Authorization` header travels to the documentation service, which is the
    one container that must never hold this credential (SEC-DOCS-001); with it,
    the upstream was measured to see no `authorization` header at all.
    """
    if not middleware_name:
        raise ManifestError("middleware_name is required")
    if not project_key:
        raise ManifestError("project_key is required")
    return {
        "http": {
            "middlewares": {
                middleware_name: {
                    "basicAuth": {
                        "users": [htpasswd_entry(hashed)],
                        "removeHeader": True,
                        # Shown in the browser's prompt, so it names the project
                        # rather than the product: an operator with two
                        # deployments open needs to know which one is asking.
                        "realm": f"{project_key} documentation",
                    }
                }
            }
        }
    }


def render_middleware(*, middleware_name: str, project_key: str, hashed: str) -> bytes:
    """Serialize deterministically, with a header saying what it is."""
    document = middleware_document(
        middleware_name=middleware_name, project_key=project_key, hashed=hashed
    )
    header = (
        "# Generated by ./deploy.sh for one project. Do not edit.\n"
        "# The credential is the bcrypt hash inline below, and it is inline so\n"
        "# that rotating it changes the document the file provider parses -- a\n"
        "# usersFile does not, and the old password kept working (ADR 0086).\n"
    )
    body = yaml.safe_dump(document, sort_keys=True, default_flow_style=False, width=10_000)
    return (header + body).encode("utf-8")

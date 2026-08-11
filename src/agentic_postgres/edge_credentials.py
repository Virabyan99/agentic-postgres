"""The documentation credential, and the middleware that checks it.

The first per-project artifact this repository writes into Traefik's file
provider. Everything else a project contributes to the edge is a container
label; this cannot be, because a `usersFile` names a path inside the Traefik
container and the file has to be put there by something.

**The middleware itself could be a label**, and that is worth writing down
because the plan says otherwise. Measured against the locked Traefik: a
container carrying
`traefik.http.middlewares.<n>.basicauth.usersfile=/etc/traefik/dynamic/<f>`
produces a working middleware — 401 without a credential, 200 with it, and the
`Authorization` header removed before the upstream sees it. What cannot be a
label is the *file*. So the choice between a label and a file-provider entry is
a real choice rather than a constraint, and this module takes the file: the
middleware then exists independently of any container's lifecycle, so a docs
service that is being recreated cannot leave a router referencing a middleware
that has momentarily stopped existing — which Traefik rejects route-by-route
while the hostname keeps answering 404 behind a valid certificate.

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
    "htpasswd_line",
    "middleware_document",
    "middleware_file_name",
    "render_middleware",
    "users_file_name",
    "users_file_path",
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


def htpasswd_line(hashed: str, *, user: str = DOCS_USER) -> str:
    """One `user:hash` line, newline-terminated.

    One line, not a file of them: a second entry is a second credential nobody
    rotates, and this file is generated from exactly one materialized secret.
    """
    if ":" in user or not user:
        raise ManifestError(f"not a usable htpasswd user: {user!r}")
    return f"{user}:{assert_bcrypt(hashed)}\n"


def users_file_name(project_key: str) -> str:
    """Per-project, because the credential is.

    The extension is `.htpasswd` and not `.yaml`, and that is load-bearing:
    Traefik's file provider parses `.yaml`, `.yml`, `.toml` and `.json` in the
    directory it watches. Measured -- a `.htpasswd` file sitting in the same
    directory is ignored by the provider and read by the middleware, which is
    the pair this design needs.
    """
    return f"{project_key}.htpasswd"


def middleware_file_name(project_key: str) -> str:
    return f"project-{project_key}.yaml"


def users_file_path(project_key: str) -> str:
    """The path as *Traefik* resolves it, which is not the host path."""
    return f"{TRAEFIK_DYNAMIC_DIR}/{users_file_name(project_key)}"


def middleware_document(*, middleware_name: str, project_key: str) -> dict[str, Any]:
    """The per-project dynamic configuration: one middleware, nothing else.

    No router and no service. Those belong to the container that serves the
    documentation, which does not exist yet -- and a router in the file provider
    pointing at a service that is not running is a route that answers 502 rather
    than one that is absent.

    `removeHeader: true` is the clause that matters. Without it the
    `Authorization` header travels to the documentation service, which is the
    one container that must never hold this credential (SEC-DOCS-001); with it,
    the upstream was measured to see no `authorization` header at all.
    """
    if not middleware_name:
        raise ManifestError("middleware_name is required")
    return {
        "http": {
            "middlewares": {
                middleware_name: {
                    "basicAuth": {
                        "usersFile": users_file_path(project_key),
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


def render_middleware(*, middleware_name: str, project_key: str) -> bytes:
    """Serialize deterministically, with a header saying what it is."""
    document = middleware_document(middleware_name=middleware_name, project_key=project_key)
    header = (
        "# Generated by ./deploy.sh for one project. Do not edit.\n"
        "# The credential itself is in the .htpasswd file this names, which the\n"
        "# file provider ignores and the middleware reads.\n"
    )
    body = yaml.safe_dump(document, sort_keys=True, default_flow_style=False, width=10_000)
    return (header + body).encode("utf-8")

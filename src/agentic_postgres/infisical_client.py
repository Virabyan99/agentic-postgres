"""A direct HTTPS client for Infisical, and no CLI on the host.

The runbook specifies two mechanisms for one job — install a pinned Infisical
CLI, *and* use a direct API client. This is the API client, and it is the only
one (plan divergence D11b). Installing a CLI would add a per-architecture binary
and a checksum to every host for a handful of HTTPS calls the standard library
already makes.

Three rules shape this module, and each is a leak surface it closes:

**Credentials are read from files, never from arguments.** Anything in ``argv``
is in ``ps`` output for every user on the box, and in shell history. The client
takes paths and reads them itself.

**Nothing is logged.** No response body, no token, no secret value, and no
digest of one. A digest of a low-entropy secret is a checkable guess. Errors
name the operation and the status code, never the payload.

**The access token lives in memory only.** It is never written, never exported,
and never passed to a subprocess.

Standard library only. Adding an HTTP dependency would widen the hash-locked
requirement set for something ``urllib`` does correctly.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Requests are small and the host is remote; a hung call must not hang a boot.
DEFAULT_TIMEOUT = 30.0

#: Sent so that a server-side log can attribute a call without identifying a
#: project. It carries no project key and no host identity on purpose.
USER_AGENT = "agentic-postgres/2"


class InfisicalError(RuntimeError):
    """An API call failed. The message never contains a credential or a value.

    ``status`` is the HTTP status when the failure was a *response*, and ``None``
    when it was anything else -- a DNS failure, a timeout, a non-JSON body. That
    distinction is load-bearing rather than informational: a secret declared
    ``required: false`` is expected to be absent, and only a **404** may be read
    as absent. A connection failure treated as "not there" would materialize a
    generation silently missing a secret the provider actually holds, and the
    deploy would then start a service without it.

    An attribute rather than something parsed back out of the message, because
    the message is written for a human and the code that branches on it is not.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Credential:
    """A Universal Auth client identity, read from two root-only files."""

    client_id: str
    client_secret: str

    @classmethod
    def from_files(cls, client_id_path: Path, client_secret_path: Path) -> Credential:
        return cls(
            client_id=_read_credential(client_id_path),
            client_secret=_read_credential(client_secret_path),
        )


def _read_credential(path: Path) -> str:
    """Read one credential file, refusing anything a stray copy would produce."""
    if path.is_symlink():
        raise InfisicalError(f"{path} is a symlink, which is not accepted for a credential")
    if not path.is_file():
        raise InfisicalError(f"credential file is missing: {path}")

    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise InfisicalError(
            f"{path} is mode {oct(mode)}; a credential readable by group or other is refused"
        )

    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise InfisicalError(f"credential file is empty: {path}")
    return value


class InfisicalClient:
    """Universal Auth login plus raw secret reads. Nothing else.

    The surface is deliberately this narrow. Every additional method is another
    thing a compromised host process could do with a credential it already has,
    and Session 2 needs exactly two operations.
    """

    def __init__(self, api_url: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        parsed = urllib.parse.urlparse(api_url)
        if parsed.scheme != "https":
            raise InfisicalError(
                f"the API URL must be https, got {parsed.scheme or 'no scheme'!r}. "
                "A credential is sent on the first call."
            )
        if not parsed.netloc:
            raise InfisicalError(f"the API URL has no host: {api_url!r}")

        self._base = api_url.rstrip("/")
        self._timeout = timeout
        self._token: str | None = None
        # Default verification, always. A client that could be told not to
        # verify is one call away from sending a credential to whatever
        # answered.
        self._context = ssl.create_default_context()

    # -- transport ---------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", USER_AGENT)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if authenticated:
            if self._token is None:
                raise InfisicalError("not authenticated; call login() first")
            request.add_header("Authorization", f"Bearer {self._token}")

        try:
            # S310: the scheme was asserted https in __init__ and the host is
            # fixed for the client's lifetime; only the path varies here.
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=self._timeout, context=self._context
            ) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            # The body is deliberately not included. On a failed auth call it
            # can echo request fields, and this message reaches logs.
            raise InfisicalError(
                f"{method} {path} failed with HTTP {exc.code}", status=exc.code
            ) from None
        except urllib.error.URLError as exc:
            raise InfisicalError(f"{method} {path} could not reach the API: {exc.reason}") from None

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            raise InfisicalError(f"{method} {path} returned a non-JSON response") from None

    # -- operations --------------------------------------------------------

    def login(self, credential: Credential) -> None:
        """Exchange a Universal Auth client identity for a short-lived token.

        The token is kept in memory and never returned, so a caller cannot
        accidentally write it somewhere.
        """
        response = self._request(
            "POST",
            "/api/v1/auth/universal-auth/login",
            body={
                "clientId": credential.client_id,
                "clientSecret": credential.client_secret,
            },
            authenticated=False,
        )
        token = response.get("accessToken")
        if not isinstance(token, str) or not token:
            raise InfisicalError("login succeeded but returned no access token")
        self._token = token

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    def read_secret(
        self,
        *,
        name: str,
        project_id: str,
        environment: str,
        # S107: a folder path inside the provider, not a credential. The name
        # comes from Infisical's own API vocabulary.
        secret_path: str = "/",  # noqa: S107
    ) -> str:
        """Read one secret value by name.

        ``expandSecretReferences`` and ``includeImports`` are both off. With
        them on, the value returned could come from a different path than the
        one asked for, which would make the per-project scoping this whole
        design rests on unverifiable from the response.
        """
        response = self._request(
            "GET",
            f"/api/v3/secrets/raw/{urllib.parse.quote(name, safe='')}",
            query={
                "workspaceId": project_id,
                "environment": environment,
                "secretPath": secret_path,
                "expandSecretReferences": "false",
                "includeImports": "false",
            },
        )
        secret = response.get("secret") or {}
        value = secret.get("secretValue")
        if not isinstance(value, str) or not value:
            raise InfisicalError(f"secret {name!r} returned no value")
        return value

    def logout(self) -> None:
        """Drop the token.

        Not a security boundary — the process could still be read — but it
        keeps a long-lived materializer from holding a token after its last use.
        """
        self._token = None

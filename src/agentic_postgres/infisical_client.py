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
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Requests are small and the host is remote; a hung call must not hang a boot.
DEFAULT_TIMEOUT = 30.0

#: An idempotent call -- a login, a read -- is attempted this many times before
#: the failure is reported, and only for a TRANSIENT failure: a read timeout, or
#: a 502/503/504 from the provider's edge. Measured on 2026-09-05 (D976): the
#: first authenticated read after a login took 8.9 s on one project and came
#: back 504 after 60 s on another, while every read after it took 0.4 s; a
#: deploy makes twenty-two reads and one in four converged. A DNS failure, a
#: 401 or a 404 is not transient and is raised on the first attempt: a 404 is
#: the one status the materializer reads as "absent" and it must stay exact.
RETRY_ATTEMPTS = 3
#: Seconds slept before the second and third attempts.
RETRY_BACKOFF_SECONDS = (1.0, 3.0)
TRANSIENT_HTTP_STATUSES = frozenset({502, 503, 504})

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

    def __init__(
        self,
        api_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
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
        self._sleep = sleep
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
        idempotent: bool = False,
    ) -> dict[str, Any]:
        """One call, retried only when ``idempotent`` and the failure is transient.

        Opt-in per call site rather than by method: a login is a POST and is
        safe to repeat, a destroy is a DELETE and is not, and the transport
        cannot tell those apart by looking at the verb.
        """
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

        attempts = RETRY_ATTEMPTS if idempotent else 1
        for attempt in range(1, attempts + 1):
            try:
                # S310: the scheme was asserted https in __init__ and the host is
                # fixed for the client's lifetime; only the path varies here.
                with urllib.request.urlopen(  # noqa: S310
                    request, timeout=self._timeout, context=self._context
                ) as response:
                    payload = response.read()
                break
            except urllib.error.HTTPError as exc:
                if attempt < attempts and exc.code in TRANSIENT_HTTP_STATUSES:
                    self._sleep(RETRY_BACKOFF_SECONDS[attempt - 1])
                    continue
                # The body is deliberately not included. On a failed auth call it
                # can echo request fields, and this message reaches logs.
                raise InfisicalError(
                    f"{method} {path} failed with HTTP {exc.code}"
                    + (f" after {attempt} attempts" if attempt > 1 else ""),
                    status=exc.code,
                ) from None
            except urllib.error.URLError as exc:
                if attempt < attempts and isinstance(exc.reason, TimeoutError):
                    self._sleep(RETRY_BACKOFF_SECONDS[attempt - 1])
                    continue
                raise InfisicalError(
                    f"{method} {path} could not reach the API: {exc.reason}"
                ) from None
            except TimeoutError:
                # A read that timed out AFTER the connection: urllib raises the
                # bare socket timeout here, not a URLError, and until D976 it
                # escaped this client as a traceback the materializer never
                # caught. Converted so ``status`` is None -- never "absent".
                if attempt < attempts:
                    self._sleep(RETRY_BACKOFF_SECONDS[attempt - 1])
                    continue
                raise InfisicalError(
                    f"{method} {path} timed out after {self._timeout:g}s"
                    + (f" on each of {attempt} attempts" if attempt > 1 else "")
                ) from None

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
            # A repeated login mints another short-lived token and nothing else.
            idempotent=True,
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
            idempotent=True,
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

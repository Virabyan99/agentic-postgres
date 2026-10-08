"""The management API's command-line client: its state, its secrets, its wire (D2066).

`bin/cloud.py` is the program (`apg login|logout|context|org|project`); this
module is everything about it a test can hold still.

**The state is a 0700 directory of 0600 files**:
`${XDG_CONFIG_HOME:-$HOME/.config}/apg/`, holding `context.json` (`endpoint`,
`organization`, `project`, and EITHER `key_file` -- the PATH of a key file the
person keeps, never the key -- OR `session: true`) and, for a password login
only, `session.json` (the refresh token). The access token is never written: a
command exchanges the refresh token for one, keeps the successor, and holds the
access token in memory for its own lifetime. A directory that is a symlink,
another user's, or readable by anyone else is refused, never repaired.

**A secret enters only through a private file whose mode is checked, or a
TTY.** `read_private_file` opens with `O_NOFOLLOW` and checks the open
descriptor -- a regular file, owned by the caller, nothing for group or other
-- so the file checked is the file read. No flag carries a secret, no
environment variable is read for one, and no secret is printed to a stdout that
is not a terminal.

**https only**, except `http://127.0.0.1` and `http://localhost` (the tests).
Redirects are never followed: a redirect would carry the bearer to wherever
the answer pointed.

Exit codes: 0 ok; 2 usage; 3 no context, no credential, an unusable local file,
or not https; 5 refused by the server (its `error` word is printed); 6 the
server could not be reached or answered something unreadable.
"""

from __future__ import annotations

import errno
import json
import os
import ssl
import stat
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5
EXIT_UNREACHABLE = 6

CONTEXT_NAME = "context.json"
SESSION_NAME = "session.json"

#: The hosts plain http is accepted for. Nothing else gets a bearer in clear.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})

#: How long one request may take before the server is reported unreachable.
TIMEOUT_SECONDS = 30

#: The members of a refusal the client relays -- the server's own words for
#: what it refused, never a body it did not shape.
RELAYED_MEMBERS = ("error", "message", "ledger_row")


class ClientError(Exception):
    """A refusal or a failure, with the exit code that names its kind."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# The state directory and its files
# ---------------------------------------------------------------------------


def state_directory(environ: Mapping[str, str] | None = None) -> Path:
    """`${XDG_CONFIG_HOME:-$HOME/.config}/apg` -- where it would be, unchecked."""
    environ = os.environ if environ is None else environ
    base = environ.get("XDG_CONFIG_HOME") or ""
    if not base:
        home = environ.get("HOME") or ""
        if not home:
            raise ClientError(EXIT_PREREQUISITE, "neither XDG_CONFIG_HOME nor HOME is set")
        base = str(Path(home) / ".config")
    return Path(base) / "apg"


def _refuse_unless_private_directory(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise ClientError(EXIT_PREREQUISITE, f"{path} is a symlink, which is not accepted")
    if not stat.S_ISDIR(info.st_mode):
        raise ClientError(EXIT_PREREQUISITE, f"{path} exists and is not a directory")
    if info.st_uid != os.geteuid():
        raise ClientError(EXIT_PREREQUISITE, f"{path} is owned by uid {info.st_uid}, not by you")
    if info.st_mode & 0o077:
        raise ClientError(
            EXIT_PREREQUISITE,
            f"{path} is mode {stat.S_IMODE(info.st_mode):04o}; it must be 0700, because "
            "it holds a refresh token",
        )


def ensure_state_directory(path: Path) -> Path:
    """The directory, created 0700 if absent; refused if it exists and is not private."""
    if path.exists() or path.is_symlink():
        _refuse_unless_private_directory(path)
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)  # the umask narrows mkdir's mode; this states it
    except OSError as error:
        raise ClientError(
            EXIT_PREREQUISITE, f"{path} cannot be created: {error.strerror}"
        ) from error
    return path


def existing_state_directory(path: Path) -> Path | None:
    """The directory if it exists and is private; None if it does not exist."""
    if not (path.exists() or path.is_symlink()):
        return None
    _refuse_unless_private_directory(path)
    return path


def read_private_file(path: Path) -> bytes:
    """A regular file, owned by the caller, mode 0600 or narrower, not a symlink.

    The checks are made on the OPEN descriptor, so the file checked is the file
    read; `O_NOFOLLOW` refuses a symlink at the last component."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise ClientError(EXIT_PREREQUISITE, f"{path} does not exist") from error
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ClientError(
                EXIT_PREREQUISITE, f"{path} is a symlink, which is not accepted"
            ) from error
        raise ClientError(EXIT_PREREQUISITE, f"{path} cannot be read: {error.strerror}") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ClientError(EXIT_PREREQUISITE, f"{path} is not a regular file")
        if info.st_uid != os.geteuid():
            raise ClientError(
                EXIT_PREREQUISITE, f"{path} is owned by uid {info.st_uid}, not by you"
            )
        if info.st_mode & 0o077:
            raise ClientError(
                EXIT_PREREQUISITE,
                f"{path} is mode {stat.S_IMODE(info.st_mode):04o}; it must be 0600 or "
                "stricter. A secret others can read is a secret others have.",
            )
        chunks = []
        while chunk := os.read(descriptor, 65536):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def write_private_file(path: Path, data: bytes) -> None:
    """Replace `path` with `data`, 0600: a temporary name, then `os.replace`."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
        )
    except OSError as error:
        raise ClientError(
            EXIT_PREREQUISITE, f"{path} cannot be written: {error.strerror}"
        ) from error
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def write_new_private_file(path: Path, data: bytes) -> None:
    """Create `path`, 0600, refusing one that exists (a symlink included)."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as error:
        raise ClientError(EXIT_USAGE, f"{path} already exists; nothing was written") from error
    except OSError as error:
        raise ClientError(
            EXIT_PREREQUISITE, f"{path} cannot be created: {error.strerror}"
        ) from error
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, data)
    finally:
        os.close(descriptor)


def refuse_existing_output(path: Path) -> None:
    """Checked BEFORE a secret is minted, so a refusal costs nothing on the server."""
    if path.exists() or path.is_symlink():
        raise ClientError(EXIT_USAGE, f"{path} already exists; nothing was requested")
    if not path.parent.is_dir():
        raise ClientError(EXIT_USAGE, f"{path.parent} is not a directory; nothing was requested")


# ---------------------------------------------------------------------------
# The context and the session
# ---------------------------------------------------------------------------


def check_endpoint(url: str) -> str:
    """An https URL, or http to a loopback host; returned without a trailing slash."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ClientError(EXIT_PREREQUISITE, f"{url!r} is not an http(s) URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ClientError(
            EXIT_PREREQUISITE, "the endpoint carries no credentials, query or fragment"
        )
    if parts.scheme == "http" and parts.hostname not in LOOPBACK_HOSTS:
        raise ClientError(
            EXIT_PREREQUISITE,
            f"{url} is plain http; the management API is reached over https (http is accepted "
            "only for 127.0.0.1 and localhost)",
        )
    return url.rstrip("/")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(read_private_file(path).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ClientError(EXIT_PREREQUISITE, f"{path} is not readable as JSON") from error
    if not isinstance(document, dict):
        raise ClientError(EXIT_PREREQUISITE, f"{path} is not a JSON object")
    return document


def _dump(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_context(directory: Path) -> dict[str, Any]:
    """The context, validated; exit 3 when there is none."""
    path = directory / CONTEXT_NAME
    if existing_state_directory(directory) is None or not (path.exists() or path.is_symlink()):
        raise ClientError(
            EXIT_PREREQUISITE,
            "no context: log in first (bin/login.sh password|key --endpoint URL ...)",
        )
    context = _load_json(path)
    endpoint = context.get("endpoint")
    if not isinstance(endpoint, str):
        raise ClientError(EXIT_PREREQUISITE, f"{path} names no endpoint")
    check_endpoint(endpoint)
    for name in ("organization", "project"):
        if context.get(name) is not None and not isinstance(context[name], str):
            raise ClientError(EXIT_PREREQUISITE, f"{path}: {name} is not a string")
    key_file, session = context.get("key_file"), context.get("session")
    if (isinstance(key_file, str)) == (session is True):
        raise ClientError(
            EXIT_PREREQUISITE, f"{path} must hold exactly one of key_file and session"
        )
    return context


def save_context(directory: Path, context: dict[str, Any]) -> None:
    write_private_file(directory / CONTEXT_NAME, _dump(context))


def load_session(directory: Path) -> str | None:
    """The refresh token, or None when no session is held."""
    path = directory / SESSION_NAME
    if not (path.exists() or path.is_symlink()):
        return None
    token = _load_json(path).get("refresh_token")
    if not isinstance(token, str) or not token:
        raise ClientError(EXIT_PREREQUISITE, f"{path} holds no refresh token")
    return token


def save_session(directory: Path, refresh_token: str) -> None:
    write_private_file(directory / SESSION_NAME, _dump({"refresh_token": refresh_token}))


def remove_session(directory: Path) -> None:
    (directory / SESSION_NAME).unlink(missing_ok=True)


def read_key(path: Path) -> str:
    key = read_private_file(path).decode("utf-8", errors="replace").strip()
    if not key.startswith("apg_") or any(c.isspace() for c in key):
        raise ClientError(EXIT_PREREQUISITE, f"{path} does not hold a management key (apg_...)")
    return key


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is answered, never followed: following it would hand the
    bearer to whatever host the answer named."""

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )


def send(
    method: str, url: str, body: dict[str, Any] | None = None, *, bearer: str | None = None
) -> tuple[int, Any]:
    """One request: the status and the parsed body (None for an empty one).

    Exit 6 when the server could not be reached, redirected, or answered
    something that is not JSON."""
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method)  # noqa: S310
    request.add_header("Accept", "application/json")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if bearer is not None:
        request.add_header("Authorization", f"Bearer {bearer}")
    try:
        with _opener().open(request, timeout=TIMEOUT_SECONDS) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise ClientError(EXIT_UNREACHABLE, f"the server could not be reached: {reason}") from error
    if 300 <= status < 400:
        raise ClientError(
            EXIT_UNREACHABLE, f"the server answered a redirect ({status}); not followed"
        )
    if not raw:
        return status, None
    try:
        return status, json.loads(raw)
    except ValueError as error:
        raise ClientError(
            EXIT_UNREACHABLE, f"the server answered {status} with something that is not JSON"
        ) from error


def refusal(status: int, body: Any) -> ClientError:
    """A 4xx as exit 5 with the server's own word; anything else as exit 6."""
    if 400 <= status < 500 and isinstance(body, dict) and isinstance(body.get("error"), str):
        said = [f"{name}: {body[name]}" for name in RELAYED_MEMBERS[1:] if body.get(name)]
        detail = f" ({'; '.join(said)})" if said else ""
        return ClientError(
            EXIT_REFUSED, f"refused by the server ({status}): {body['error']}{detail}"
        )
    return ClientError(
        EXIT_UNREACHABLE, f"the server answered {status}, which this client does not read"
    )


def download(url: str) -> bytes:
    """The body of one GET of a presigned URL -- an export's (ADR 0259) -- or a
    ClientError. https only (http to a loopback host for the tests), no
    redirect followed, nothing of the URL in any message: it is a bearer
    credential to the object until it expires."""
    parts = urllib.parse.urlsplit(url)
    if not parts.hostname or not (
        parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS)
    ):
        raise ClientError(EXIT_UNREACHABLE, "the download URL is not https; nothing was fetched")
    request = urllib.request.Request(url, method="GET")  # noqa: S310
    try:
        with _opener().open(request, timeout=TIMEOUT_SECONDS) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, b""
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as error:
        raise ClientError(
            EXIT_UNREACHABLE, f"the download could not be fetched ({type(error).__name__})"
        ) from error
    if status != 200:
        raise ClientError(
            EXIT_UNREACHABLE,
            f"the download answered {status}"
            + ("; a redirect is not followed" if 300 <= status < 400 else ""),
        )
    return body


#: Where `project create` keeps each handoff token (ADR 0260), named by its
#: creation's operation id, until `project claim` presents it: a 0700
#: directory of 0600 files inside the state directory.
HANDOFF_DIRECTORY = "handoffs"


def handoff_directory(directory: Path) -> Path:
    """The state directory's `handoffs/`, created 0700, refused when not private."""
    ensure_state_directory(directory)
    return ensure_state_directory(directory / HANDOFF_DIRECTORY)


class Session:
    """The credential a context names, turned into a bearer for one process.

    A key context reads its key file on every use. A session context exchanges
    the refresh token once, writes the successor before anything else, and keeps
    the access token in memory; a 401 is answered by one more exchange and one
    retry, never more."""

    def __init__(self, directory: Path, context: dict[str, Any]) -> None:
        self.directory = directory
        self.context = context
        self.endpoint = check_endpoint(context["endpoint"])
        self._access: str | None = None

    @property
    def is_key(self) -> bool:
        return isinstance(self.context.get("key_file"), str)

    def adopt_access_token(self, token: str) -> None:
        """A login's own access token, so its first request needs no exchange."""
        self._access = token

    def _exchange(self) -> str:
        refresh = load_session(self.directory)
        if refresh is None:
            raise ClientError(
                EXIT_PREREQUISITE,
                "not logged in: no session is held (bin/login.sh password --endpoint ...)",
            )
        status, body = send("POST", f"{self.endpoint}/sessions/refresh", {"refresh_token": refresh})
        if status == 401:
            remove_session(self.directory)
            raise ClientError(
                EXIT_PREREQUISITE, "the session has ended; log in again (bin/login.sh password)"
            )
        if status != 200 or not isinstance(body, dict):
            raise refusal(status, body)
        successor, access = body.get("refresh_token"), body.get("access_token")
        if not isinstance(successor, str) or not isinstance(access, str):
            raise ClientError(EXIT_UNREACHABLE, "the refresh answer did not carry two tokens")
        save_session(self.directory, successor)
        self._access = access
        return access

    def bearer(self) -> str:
        if self.is_key:
            return read_key(Path(self.context["key_file"]))
        return self._access or self._exchange()

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        """One authenticated request; the body on 2xx, a ClientError otherwise."""
        url = f"{self.endpoint}{path}"
        status, answer = send(method, url, body, bearer=self.bearer())
        if status == 401 and not self.is_key:
            status, answer = send(method, url, body, bearer=self._exchange())
        if 200 <= status < 300:
            return answer
        raise refusal(status, answer)

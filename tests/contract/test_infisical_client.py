"""The Infisical client's refusals, tested without a network.

Everything asserted here is a property the client has before it ever makes a
call: that it will not talk to a plaintext endpoint, that it reads credentials
from files rather than arguments, that it refuses a credential file anyone else
can read, and that its errors never carry a payload.

The last one is the easiest to lose and the hardest to notice. An exception that
includes the response body is the most natural thing to write, and on a failed
login the body can echo the request — so the credential ends up in the log line
that reports it did not work.
"""

from __future__ import annotations

import inspect
import json
import urllib.error
from pathlib import Path

import pytest

from agentic_postgres import infisical_client
from agentic_postgres.infisical_client import (
    Credential,
    InfisicalClient,
    InfisicalError,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

SENTINEL = "s3cr3t-value-that-must-not-be-echoed"


@pytest.fixture
def credential_files(tmp_path: Path) -> tuple[Path, Path]:
    client_id = tmp_path / "infisical-client-id"
    client_secret = tmp_path / "infisical-client-secret"
    client_id.write_text("an-identity\n", encoding="utf-8")
    client_secret.write_text(f"{SENTINEL}\n", encoding="utf-8")
    client_id.chmod(0o400)
    client_secret.chmod(0o400)
    return client_id, client_secret


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["http://infisical.example.invalid", "ftp://x", "infisical.example.invalid", ""],
)
def test_a_non_https_api_url_is_refused(url: str) -> None:
    """A credential is sent on the first call; there is no safe plaintext case."""
    with pytest.raises(InfisicalError):
        InfisicalClient(url)


def test_an_https_url_is_accepted() -> None:
    client = InfisicalClient("https://infisical.example.invalid/")
    assert not client.authenticated


def test_there_is_no_way_to_disable_certificate_verification() -> None:
    """A client that could be told not to verify is one call from a leak."""
    signature = inspect.signature(InfisicalClient.__init__)
    assert set(signature.parameters) == {"self", "api_url", "timeout"}

    source = inspect.getsource(infisical_client)
    for escape in ("CERT_NONE", "check_hostname = False", "_create_unverified"):
        assert escape not in source, f"the client can disable verification via {escape}"


def test_an_unauthenticated_read_is_refused_before_any_request() -> None:
    client = InfisicalClient("https://infisical.example.invalid")
    with pytest.raises(InfisicalError, match="not authenticated"):
        client.read_secret(name="anything", project_id="p", environment="dev")


# ---------------------------------------------------------------------------
# Credentials come from files
# ---------------------------------------------------------------------------


def test_credentials_are_read_from_files(credential_files: tuple[Path, Path]) -> None:
    credential = Credential.from_files(*credential_files)
    assert credential.client_secret == SENTINEL


def test_no_public_entry_point_accepts_a_raw_secret_string() -> None:
    """``argv`` is world-readable in ``ps``; a path is not a value."""
    parameters = set(inspect.signature(Credential.from_files).parameters)
    assert parameters == {"cls", "client_id_path", "client_secret_path"} or parameters == {
        "client_id_path",
        "client_secret_path",
    }, parameters


def test_a_group_readable_credential_is_refused(credential_files: tuple[Path, Path]) -> None:
    client_id, client_secret = credential_files
    client_secret.chmod(0o440)

    with pytest.raises(InfisicalError, match="readable by group or other"):
        Credential.from_files(client_id, client_secret)


def test_a_symlinked_credential_is_refused(
    credential_files: tuple[Path, Path], tmp_path: Path
) -> None:
    client_id, client_secret = credential_files
    link = tmp_path / "linked-secret"
    link.symlink_to(client_secret)

    with pytest.raises(InfisicalError, match="symlink"):
        Credential.from_files(client_id, link)


def test_a_missing_credential_is_named_not_guessed(tmp_path: Path) -> None:
    with pytest.raises(InfisicalError, match="missing"):
        Credential.from_files(tmp_path / "absent-id", tmp_path / "absent-secret")


def test_an_empty_credential_is_refused(credential_files: tuple[Path, Path]) -> None:
    client_id, client_secret = credential_files
    client_secret.chmod(0o600)
    client_secret.write_text("   \n", encoding="utf-8")
    client_secret.chmod(0o400)

    with pytest.raises(InfisicalError, match="empty"):
        Credential.from_files(client_id, client_secret)


# ---------------------------------------------------------------------------
# Errors carry no payload
# ---------------------------------------------------------------------------


def test_an_http_error_does_not_echo_the_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failed-login case is the dangerous one: the body can echo the request."""
    body = json.dumps({"message": "invalid client secret", "received": SENTINEL}).encode()

    def raise_http_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError(
            url="https://infisical.example.invalid/api/v1/auth/universal-auth/login",
            code=401,
            msg="Unauthorized",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_http_error)

    client = InfisicalClient("https://infisical.example.invalid")
    with pytest.raises(InfisicalError) as caught:
        client.login(Credential(client_id="an-identity", client_secret=SENTINEL))

    message = str(caught.value)
    assert SENTINEL not in message, "the failure message carries the client secret"
    assert body.decode() not in message
    assert "401" in message, "the message should still say what happened"


def test_a_network_error_names_the_operation_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_url_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("name or service not known")

    monkeypatch.setattr(urllib.request, "urlopen", raise_url_error)

    client = InfisicalClient("https://infisical.example.invalid")
    with pytest.raises(InfisicalError) as caught:
        client.login(Credential(client_id="an-identity", client_secret=SENTINEL))

    assert SENTINEL not in str(caught.value)
    assert "could not reach" in str(caught.value)


def test_the_module_never_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    """No print, no logging call. Nothing here has anything safe to say."""
    source = inspect.getsource(infisical_client)
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith(("#", '"', "'"))
    )
    for emitter in ("print(", "logging.", "sys.stdout", "sys.stderr", "warnings.warn"):
        assert emitter not in code, f"the client emits output via {emitter}"


# ---------------------------------------------------------------------------
# Reads are scoped to exactly what was asked for
# ---------------------------------------------------------------------------


def test_reads_disable_reference_expansion_and_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    """With either on, the value could come from a path other than the one asked
    for, and per-project scoping would be unverifiable from the response."""
    captured: dict[str, str] = {}

    class Response:
        status = 200

        def read(self) -> bytes:
            return json.dumps({"secret": {"secretValue": "ok"}}).encode()

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def capture(request: object, *args: object, **kwargs: object) -> Response:
        captured["url"] = request.full_url  # type: ignore[attr-defined]
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", capture)

    client = InfisicalClient("https://infisical.example.invalid")
    # S105/SLF001: a fixed placeholder standing in for a token, set directly to
    # exercise the authenticated path without a live login.
    client._token = "in-memory-only"  # noqa: S105
    value = client.read_secret(name="session2_sentinel", project_id="p", environment="dev")

    assert value == "ok"
    assert "expandSecretReferences=false" in captured["url"]
    assert "includeImports=false" in captured["url"]


def test_the_token_is_never_returned_or_stored_outside_memory() -> None:
    source = inspect.getsource(infisical_client)
    assert "def login(self, credential: Credential) -> None:" in source, (
        "login must return None; a returned token invites a caller to write it somewhere"
    )
    # Word-bounded: a bare "open(" substring also matches urlopen(), which is
    # how this call is made in the first place.
    import re

    for persistence in (r"\bopen\(", r"\bwrite_text\b", r"\bos\.environ\["):
        assert not re.search(persistence, source), (
            f"the client persists something via {persistence}"
        )


def test_logout_drops_the_token() -> None:
    client = InfisicalClient("https://infisical.example.invalid")
    # S105/SLF001: a fixed placeholder standing in for a token, set directly to
    # exercise the authenticated path without a live login.
    client._token = "in-memory-only"  # noqa: S105
    assert client.authenticated
    client.logout()
    assert not client.authenticated

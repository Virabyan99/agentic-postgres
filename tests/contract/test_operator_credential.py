"""The control-plane credential, and the exception that printed it.

A two-line credential file was read whole and used as a bearer token, so the
header became ``Bearer <client-id>\\n<client-secret>``. ``http.client.putheader``
rejects a header containing a newline by raising

    ValueError('Invalid header value %r' % value)

and that ``%r`` is the credential. The most privileged secret in the system was
printed in full to a terminal, and from there into a transcript, by a validation
error in the standard library.

Every deliberate leak surface in §5 was covered — process arguments, shell
history, ``docker inspect``, image layers, the access log — and none of them was
this one. The value never reached a log the project controls; it reached an
exception message, on a path that only runs when something is already wrong.

Two rules follow, and both are tested here against a real secret-shaped value:

**A credential is validated for shape before the standard library sees it.**
Refusing early is not about tidiness; it is the only way to keep the value out
of somebody else's error formatting.

**No failure message contains a credential.** Including the ones that describe
what was wrong with it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

#: Shaped like the value that leaked: a UUID client id and a 64-hex secret.
CLIENT_ID = "a8882891-af1d-4491-b034-60def46365aa"
# S105: this is the shape of a leaked value, planted so the tests can prove it
# does not come back out. It is not a credential -- the real one was revoked.
CLIENT_SECRET = "3bff15bcf0d46fca98b11bdff03d11a02c8879b47b28e91c10d108e48ea0bd00"  # noqa: S105


@pytest.fixture(scope="module")
def bootstrap():
    """Load bin/bootstrap-providers.py as a module; it has no .py importable name."""
    spec = importlib.util.spec_from_file_location(
        "bootstrap_providers_under_test", REPO_ROOT / "bin" / "bootstrap-providers.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "credential"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_two_line_credential_is_read(bootstrap, tmp_path: Path) -> None:
    path = write(tmp_path, f"{CLIENT_ID}\n{CLIENT_SECRET}\n")
    assert bootstrap.read_operator_credential(path) == (CLIENT_ID, CLIENT_SECRET)


@pytest.mark.parametrize(
    ("description", "content"),
    [
        ("one line", f"{CLIENT_ID} {CLIENT_SECRET}\n"),
        ("three lines", f"{CLIENT_ID}\n{CLIENT_SECRET}\nextra\n"),
        ("empty", "\n\n"),
        ("secret only", f"{CLIENT_SECRET}\n"),
    ],
)
def test_a_malformed_credential_is_refused_without_echoing_it(
    bootstrap, tmp_path: Path, description: str, content: str
) -> None:
    """The message may name the file and the line count. Never a value."""
    path = write(tmp_path, content)
    with pytest.raises(Exception) as raised:
        bootstrap.read_operator_credential(path)

    message = str(raised.value)
    assert CLIENT_SECRET not in message, f"the {description} case leaked the secret: {message}"
    assert CLIENT_ID not in message, f"the {description} case leaked the client id"


def test_a_token_that_cannot_be_a_header_is_refused_before_the_header_is_built(
    bootstrap,
) -> None:
    """This is the exact failure, reproduced.

    A newline in a bearer token is what made http.client raise with the value
    in the message. It has to be refused here, because the code that raises
    afterwards is not ours and does not know what it is holding.
    """
    with pytest.raises(Exception) as raised:
        bootstrap.ControlPlane("https://app.infisical.com", f"{CLIENT_ID}\n{CLIENT_SECRET}")

    message = str(raised.value)
    assert CLIENT_SECRET not in message
    assert CLIENT_ID not in message
    assert "deliberately not shown" in message


def test_a_well_formed_token_is_accepted(bootstrap) -> None:
    """Guard the guard: a validator that rejected everything would also pass."""
    assert bootstrap.ControlPlane("https://app.infisical.com", "eyJhbGciOi.J9-_~+/=")


def test_the_control_plane_authenticates_rather_than_sending_the_credential(bootstrap) -> None:
    """It used the operator's long-lived secret as the bearer token itself.

    So the credential travelled on every request, and the machine identity the
    plan specifies was never actually authenticated as. Universal Auth exchanges
    it once for a short-lived access token, which is what §5's secret path
    describes for the runtime client and applies no less to the control plane.
    """
    assert hasattr(bootstrap.ControlPlane, "login")
    source = (REPO_ROOT / "bin" / "bootstrap-providers.py").read_text(encoding="utf-8")
    assert "universal-auth/login" in source
    assert "ControlPlane.login(" in source, "apply still constructs a client from the raw file"


def test_no_failure_path_prints_a_traceback_through_the_credential(bootstrap) -> None:
    """The reader is called inside a handler that reports rather than raises.

    An uncaught exception prints a traceback, and a traceback is how this got
    out in the first place.
    """
    source = (REPO_ROOT / "bin" / "bootstrap-providers.py").read_text(encoding="utf-8")
    body = source.split("read_operator_credential(credential_file)", 1)[1][:400]
    assert "except BootstrapStateError" in body, "a malformed credential still raises to the top"
    assert "fail(" in body

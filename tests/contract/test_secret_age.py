"""A secret's age is the provider's update time, read, never acted on (ADR 0250).

`OPS-ROTATE-001`. `secrets.required.yaml` may declare `max_age_days` per
secret; `doctor secrets --project KEY` reads the provider's `updatedAt` for
each declaring secret and reports `ok`, `overdue` (a WARN) or `unknown`.

**The value is the subject of this module.** The provider's response to the
time read is the same response the materializer reads a value from, so every
response here carries a PLANTED value, and every proof that touches a response
asserts the plant appears in no return and no printed line, at every rendering.
The real `InfisicalClient` is used with its one transport method replaced, so
the function that drops the value is the function under test -- not a fake
that never had one.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import uuid
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    config,
    deployed_output,
    diagnosis,
    infisical_client,
    secret_age,
)
from agentic_postgres.infisical_client import InfisicalClient, InfisicalError, SecretTimes
from agentic_postgres.secrets_contract import load_secret_contract

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

DOCTOR_PY = REPO_ROOT / "bin" / "doctor.py"
CONTRACT = REPO_ROOT / "secrets.required.yaml"
KEY = "alpha-dev"
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)

PLANTED_VALUE = f"APG-VALUE-CANARY-{uuid.uuid4().hex}"
PLANTED_CLIENT_SECRET = f"APG-CREDENTIAL-CANARY-{uuid.uuid4().hex}"

#: The three credentials the rotation trio proves (D1995) -- and nothing else
#: yet (ADR 0250).
DECLARING = {
    "postgrest_authenticator_password",
    "docs_basic_auth_password",
    "app_runtime_password",
}


@pytest.fixture(scope="module")
def doctor() -> Any:
    spec = importlib.util.spec_from_file_location("_apg_doctor_secret_age", DOCTOR_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(updated_at: object = "2026-08-28T07:54:57.437Z", version: object = 3) -> dict:
    """What the provider returns for one secret: the value INCLUDED."""
    return {
        "secret": {
            "secretKey": "APG_SOMETHING",
            "secretValue": PLANTED_VALUE,
            "version": version,
            "createdAt": "2026-08-11T15:25:18.934Z",
            "updatedAt": updated_at,
        }
    }


def times(updated_at: str | None, version: int | None = 3) -> SecretTimes:
    return SecretTimes(version=version, created_at=None, updated_at=updated_at)


# ---------------------------------------------------------------------------
# The declaration
# ---------------------------------------------------------------------------


def test_the_contract_declares_an_age_for_exactly_the_three_rotated_credentials() -> None:
    contract = load_secret_contract(CONTRACT)
    declared = {s["name"]: s["max_age_days"] for s in secret_age.declared(contract["secrets"])}
    assert set(declared) == DECLARING
    assert set(declared.values()) == {90}


@pytest.mark.parametrize(
    ("value", "valid"), [(1, True), (3650, True), (0, False), (3651, False), ("90", False)]
)
def test_max_age_days_is_bounded_by_the_schema(value: object, valid: bool) -> None:
    document = copy.deepcopy(load_secret_contract(CONTRACT))
    document["secrets"][0]["max_age_days"] = value
    if valid:
        config.validate_against_schema(document, "secret-contract.schema.json")
    else:
        with pytest.raises(config.ManifestError):
            config.validate_against_schema(document, "secret-contract.schema.json")


# ---------------------------------------------------------------------------
# The reader holds no value
# ---------------------------------------------------------------------------


def test_the_time_reader_never_returns_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """The response carries the plant; the return carries three fields."""
    calls: list[tuple[str, str]] = []

    def transport(self: InfisicalClient, method: str, path: str, **_: Any) -> dict:
        calls.append((method, path))
        return response()

    monkeypatch.setattr(InfisicalClient, "_request", transport)
    result = InfisicalClient("https://provider.invalid").read_secret_times(
        name="APG_DOCS_BASIC_AUTH_PASSWORD", project_id="p", environment="prod"
    )
    assert PLANTED_VALUE not in repr(result)
    assert PLANTED_VALUE not in json.dumps(result.__dict__)
    assert {f.name for f in fields(SecretTimes)} == {"version", "created_at", "updated_at"}
    assert result == SecretTimes(
        version=3, created_at="2026-08-11T15:25:18.934Z", updated_at="2026-08-28T07:54:57.437Z"
    )
    assert calls == [("GET", "/api/v3/secrets/raw/APG_DOCS_BASIC_AUTH_PASSWORD")]


def test_a_field_in_the_wrong_type_is_none_never_a_substitute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def transport(self: InfisicalClient, method: str, path: str, **_: Any) -> dict:
        return response(updated_at=1727950497, version=True)

    monkeypatch.setattr(InfisicalClient, "_request", transport)
    result = InfisicalClient("https://provider.invalid").read_secret_times(
        name="APG_X", project_id="p", environment="prod"
    )
    assert (result.version, result.updated_at) == (None, None)


# ---------------------------------------------------------------------------
# Three outcomes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "outcome"),
    [(0, secret_age.OK), (89, secret_age.OK), (90, secret_age.OK), (91, secret_age.OVERDUE)],
)
def test_an_age_is_ok_through_the_declaration_and_overdue_after_it(days: int, outcome: str) -> None:
    updated = (NOW - timedelta(days=days, hours=1)).isoformat()
    age = secret_age.judge("docs_basic_auth_password", 90, times(updated), now=NOW)
    assert (age.outcome, age.age_days) == (outcome, days)
    assert age.updated_at == datetime.fromisoformat(updated).isoformat()


@pytest.mark.parametrize(
    ("updated_at", "reason"),
    [
        (None, "no update time"),
        ("last tuesday", "not a timestamp"),
        ("2026-08-28T07:54:57", "no timezone"),
        ((NOW + timedelta(hours=2)).isoformat(), "in the future"),
    ],
)
def test_a_time_the_reading_cannot_use_is_unknown(updated_at: str | None, reason: str) -> None:
    age = secret_age.judge("docs_basic_auth_password", 90, times(updated_at), now=NOW)
    assert age.outcome == secret_age.UNKNOWN
    assert reason in age.reason
    assert age.age_days is None


@pytest.mark.parametrize(
    ("status", "reason"),
    [(404, "holds no such secret"), (None, "could not be reached"), (500, "HTTP 500")],
)
def test_a_failed_read_is_unknown_and_only_404_means_absent(
    status: int | None, reason: str
) -> None:
    age = secret_age.unreadable("app_runtime_password", 90, status)
    assert age.outcome == secret_age.UNKNOWN
    assert reason in age.reason


def test_overdue_warns_and_exits_zero_and_unknown_exits_six() -> None:
    ok = secret_age.judge("a", 90, times((NOW - timedelta(days=3)).isoformat()), now=NOW)
    overdue = secret_age.judge("b", 90, times((NOW - timedelta(days=200)).isoformat()), now=NOW)
    unknown = secret_age.unreadable("c", 90, 404)

    checks = diagnosis.secret_age_report((ok, overdue))
    assert [c.verdict for c in checks] == [diagnosis.OK, diagnosis.WARN]
    assert diagnosis.exit_code(checks) == 0
    assert diagnosis.exit_code(diagnosis.secret_age_report((ok, unknown))) == 6
    assert [c.name for c in checks] == ["secret a", "secret b"]


# ---------------------------------------------------------------------------
# The doctor's reading, end to end, with the provider replaced at its transport
# ---------------------------------------------------------------------------


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, doctor: Any) -> Path:
    """A deployed document, a root-only credential pair carrying a planted
    client secret, a host manifest and a bootstrap state -- the four things the
    reading reads before it reaches the provider."""
    root = tmp_path / "projects"
    deployed = deployed_output.deployed_path(KEY, root=root)
    deployed.parent.mkdir(parents=True)
    deployed.write_text(json.dumps({"deployed_through_session": 36}), encoding="utf-8")

    credentials = tmp_path / "credentials"
    (credentials / KEY).mkdir(parents=True)
    for name, value in (
        ("infisical-client-id", "client-id"),
        ("infisical-client-secret", PLANTED_CLIENT_SECRET),
    ):
        path = credentials / KEY / name
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
    monkeypatch.setattr(doctor, "CREDENTIAL_ROOT", credentials)
    monkeypatch.setattr(
        doctor.host_config,
        "load_host_manifest",
        lambda _path: {"infisical": {"api_url": "https://provider.invalid"}},
    )
    monkeypatch.setattr(
        doctor.bootstrap_state,
        "load_state",
        lambda _path: {"infisical_project_id": "p", "environment_slug": "prod"},
    )
    return root


def provider(monkeypatch: pytest.MonkeyPatch, *, login_status: int | None = 0) -> list[dict]:
    """Replace the real client's transport. Every secret answers with the plant."""
    seen: list[dict] = []

    def transport(self: InfisicalClient, method: str, path: str, **kwargs: Any) -> dict:
        seen.append({"method": method, "path": path, **kwargs})
        if path.endswith("/login"):
            if login_status:
                raise InfisicalError(
                    f"{method} {path} failed with HTTP {login_status}", status=login_status
                )
            return {"accessToken": "token"}
        return response(updated_at=(NOW - timedelta(days=36)).isoformat())

    monkeypatch.setattr(infisical_client.InfisicalClient, "_request", transport)
    return seen


@pytest.mark.parametrize("rendering", [(), ("--verbose",), ("--json",)])
def test_the_reading_prints_no_value_at_any_rendering(
    doctor: Any,
    host: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rendering: tuple[str, ...],
) -> None:
    seen = provider(monkeypatch)
    code = doctor.main(["--reading", "secrets", "--project", KEY, "--root", str(host), *rendering])
    printed = capsys.readouterr()
    output = printed.out + printed.err

    assert code == 0
    assert PLANTED_VALUE not in output
    assert PLANTED_CLIENT_SECRET not in output
    for name in DECLARING:
        assert f"secret {name}" in output
    reads = [call for call in seen if not call["path"].endswith("/login")]
    assert len(reads) == len(DECLARING), "one GET per declaring secret, and no other"


def test_a_failed_login_is_unknown_for_every_declared_secret(
    doctor: Any,
    host: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen = provider(monkeypatch, login_status=401)
    code = doctor.main(["--reading", "secrets", "--project", KEY, "--root", str(host), "--json"])
    document = json.loads(capsys.readouterr().out)

    assert code == 6
    assert {check["verdict"] for check in document["checks"]} == {diagnosis.UNKNOWN}
    assert len(document["checks"]) == len(DECLARING)
    assert all("login failed (HTTP 401)" in check["detail"] for check in document["checks"])
    assert [call["path"] for call in seen] == ["/api/v1/auth/universal-auth/login"]

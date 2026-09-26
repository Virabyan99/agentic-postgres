"""`OPS-LEDGER-001` -- `bin/migrate.sh` prints what dbmate said (D1707).

From 1.8.0 until Session 33, `run_dbmate` went through
`container_exec.compose_run`, which always captures (ADR 0218), and returned the
exit code alone. So `bin/migrate.sh --runtime status` printed no ledger and
exited 0 on every deployment, and a failed `up` reached the deploy's step 6
with an empty stderr. Nobody noticed for five releases because the operator
reads the ledger through the doctor's `migrations` check instead -- which is
the right verdict (D941) and was never the only reader.

These proofs drive the real `run_dbmate` over a fake `compose_run` that returns
what dbmate prints. The bytes are dbmate's own shape: `[X]` per applied
version, then the two count lines.
"""

from __future__ import annotations

import importlib.util
import subprocess
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

MIGRATE_PY = REPO_ROOT / "bin" / "migrate.py"

DOCUMENT = {"database": {"roles": {"migration_user": "apg_fixture_alpha_dev_migration_user"}}}

STATUS_BYTES = (
    b"[X] 20260917120033_agent_audit_retention.sql\n"
    b"[X] 20260917120034_workflow_substrate.sql\n"
    b"\n"
    b"Applied: 34\n"
    b"Pending: 0\n"
)


@pytest.fixture
def migrate() -> Any:
    """`bin/migrate.py` imported by path -- `bin/` is not a package."""
    spec = importlib.util.spec_from_file_location("_apg_migrate_under_test", MIGRATE_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_compose_run(
    returncode: int, stdout: bytes, stderr: bytes, calls: list[tuple[Any, ...]]
) -> Any:
    def fake(*arguments: Any, **options: Any) -> subprocess.CompletedProcess:
        calls.append((arguments, options))
        return subprocess.CompletedProcess(list(arguments), returncode, stdout, stderr)

    return fake


def test_status_prints_the_ledger_lines_dbmate_wrote(
    migrate: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        migrate.container_exec, "compose_run", _fake_compose_run(0, STATUS_BYTES, b"", calls)
    )

    code = migrate.run_dbmate("status", DOCUMENT, "/nonexistent/rendered")

    printed = capsys.readouterr().out
    assert code == 0
    assert "[X] 20260917120034_workflow_substrate.sql" in printed, printed
    assert "Pending: 0" in printed, printed
    # Still through the discipline: one captured, stdin-closed call, never a
    # second way to start the container (ADR 0218).
    assert len(calls) == 1
    assert calls[0][1].get("text") is False


def test_the_exit_is_dbmates_and_stderr_is_not_swallowed(
    migrate: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[Any, ...]] = []
    refusal = b'Error: pq: relation "app_private.schema_migrations" does not exist\n'
    monkeypatch.setattr(
        migrate.container_exec, "compose_run", _fake_compose_run(1, b"", refusal, calls)
    )

    code = migrate.run_dbmate("status", DOCUMENT, "/nonexistent/rendered")

    captured = capsys.readouterr()
    assert code == 1
    assert "app_private.schema_migrations" in captured.err, captured.err
    # A byte that is not UTF-8 is replaced, never allowed to fail the relay.
    monkeypatch.setattr(
        migrate.container_exec,
        "compose_run",
        _fake_compose_run(2, b"\xff\xfe[X] broken\n", b"\xc3", calls),
    )
    assert migrate.run_dbmate("status", DOCUMENT, "/nonexistent/rendered") == 2
    assert "[X] broken" in capsys.readouterr().out

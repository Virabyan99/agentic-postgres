"""`bin/record.sh size|prune`: ADR 0213's TTY act made a command (OPS-RETAIN-002).

The command is loaded as a module and its one outward edge --
`container_exec.run` -- is replaced by a recorder, so every proof here can say
what WAS and was NOT sent to a container. `require_root` is replaced too: the
proofs run as a user, and root is checked by `test_size_refuses_without_root`
against the real function.

What the database does with each call is `test_record_retention.py`'s; what is
proved here is the command's half -- the refusals before any connection, the
names read from the deployed document, the horizon passed as a variable, the
three outcomes of a reading, and that nothing calls the command but a person.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

KEY = "alpha-dev"
CONTAINER = "apg-alpha-dev-postgres-1"
DATABASE = "alpha_dev"

SIZE_ROWS = "\n".join(
    [
        "agent_audit|12|2026-09-01 10:00:00+00",
        "workflow_run|4|2026-09-20 10:00:00+00",
        "workflow_approval (pending on an ended run)|0|",
    ]
)


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("apg_record", REPO_ROOT / "bin" / "record.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder:
    """`container_exec.run`'s stand-in: records each call, answers from a script."""

    def __init__(self, answers: list[tuple[int, str, str]]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._answers = list(answers)

    def __call__(self, container: str, *argv: str, **kwargs: Any) -> Any:
        self.calls.append({"container": container, "argv": list(argv), **kwargs})
        code, out, err = self._answers.pop(0) if self._answers else (0, SIZE_ROWS, "")
        return subprocess.CompletedProcess(argv, code, out, err)


@pytest.fixture
def record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = _load()
    state = tmp_path / "projects"
    (state / KEY).mkdir(parents=True)
    document = {
        "schema_version": 19,
        "project": {"key": KEY},
        "database": {"container": CONTAINER, "name": DATABASE},
    }
    (state / KEY / "outputs.json").write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(module, "STATE_ROOT", state)
    monkeypatch.setattr(module, "require_root", lambda: None)
    monkeypatch.setattr(module.deployed_output, "read_deployed_document", lambda raw: raw)
    return module


def _use(record: Any, monkeypatch: pytest.MonkeyPatch, answers: list) -> Recorder:
    recorder = Recorder(answers)
    monkeypatch.setattr(record.container_exec, "run", recorder)
    return recorder


PAST = "2026-10-01T00:00:00Z"


def _prune(record: Any, *extra: str) -> int:
    return record.main(["prune", "--project", KEY, "--what", "runs", *extra])


def test_prune_requires_a_horizon_and_a_confirmation(
    record: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No horizon, no confirmation, or a confirmation that is not the key EXACTLY
    -- a different case included -- is exit 2 with nothing sent. The control:
    the same call with both is served."""
    recorder = _use(record, monkeypatch, [])
    assert _prune(record, "--confirm", KEY) == 2
    assert _prune(record, "--before", PAST) == 2
    assert _prune(record, "--before", PAST, "--confirm", "beta-dev") == 2
    assert _prune(record, "--before", PAST, "--confirm", KEY.upper()) == 2
    assert recorder.calls == [], "a refused prune reached a container"

    assert _prune(record, "--before", PAST, "--confirm", KEY) == 0
    assert len(recorder.calls) == 3


def test_an_unparseable_or_future_horizon_is_refused_before_any_connection(
    record: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Prose, a time with no timezone, and a time in the future: exit 2, and the
    recorder never called -- the refusal happens before the document is read."""
    recorder = _use(record, monkeypatch, [])
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    for horizon, said in (
        ("last tuesday", "not an ISO 8601"),
        ("2026-10-01T00:00:00", "no timezone"),
        (future, "in the future"),
    ):
        assert _prune(record, "--before", horizon, "--confirm", KEY) == 2, horizon
        assert said in capsys.readouterr().err, horizon
    assert recorder.calls == []


def test_the_container_and_database_are_read_from_the_deployed_document(
    record: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1184: the names come from `/etc/agentic-postgres/projects/<KEY>/outputs.json`
    and nothing is typed; a key that is not a key is refused before a path is built."""
    recorder = _use(record, monkeypatch, [])
    assert record.main(["size", "--project", KEY]) == 0
    (call,) = recorder.calls
    assert call["container"] == CONTAINER
    assert call["argv"][:6] == ["psql", "-U", "postgres", "-d", DATABASE, "-X"]
    assert "record_size()" in call["input"]

    assert record.main(["size", "--project", "../alpha-dev"]) == 2
    assert record.main(["size", "--project", "gamma-dev"]) == 3
    assert len(recorder.calls) == 1


def test_prune_prints_before_count_and_after(
    record: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Size, the one call, size: three round trips in that order. The horizon
    travels as a `psql` variable and is never in the statement's text; `--what`
    picks exactly one function; `--limit` reaches it as an integer."""
    recorder = _use(record, monkeypatch, [(0, SIZE_ROWS, ""), (0, "3\n", ""), (0, SIZE_ROWS, "")])
    assert _prune(record, "--before", PAST, "--limit", "50", "--confirm", KEY) == 0
    out = capsys.readouterr().out
    assert out.index("before") < out.index("removed 3") < out.index("after"), out

    size_before, call, size_after = recorder.calls
    assert "record_size()" in size_before["input"] and "record_size()" in size_after["input"]
    assert call["input"].strip() == (
        "SELECT app_private.workflow_run_prune(:'before'::timestamptz, 50);"
    )
    assert "2026-10-01" not in call["input"], "the horizon was interpolated into the SQL"
    assert "before=2026-10-01T00:00:00+00:00" in call["argv"]
    assert set(record.PRUNES.values()) == {
        "workflow_run_prune",
        "connector_delivery_prune",
        "agent_prune",
        "agent_audit_prune",
        "agent_idempotency_prune",
    }


def test_a_database_refusal_is_printed_verbatim_and_exits_5(
    record: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The function's own AP422 sentence reaches the operator, and the size after
    is not read for a prune that did not run."""
    refusal = "psql:<stdin>:1: ERROR:  AP422: a retention horizon inside the inbound replay window"
    recorder = _use(record, monkeypatch, [(0, SIZE_ROWS, ""), (3, "", refusal)])
    assert _prune(record, "--before", PAST, "--confirm", KEY) == 5
    assert refusal in capsys.readouterr().err
    assert len(recorder.calls) == 2


def test_size_reports_unknown_when_the_cluster_does_not_answer(
    record: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0195's third outcome: a cluster that did not answer, or answered in a
    shape nobody asked for, is *could not be read* and exit 6 -- never a table of
    zeros. The control: the same command over an answering cluster exits 0."""
    _use(record, monkeypatch, [(2, "", "connection to server failed"), (0, "garbage\n", "")])
    assert record.main(["size", "--project", KEY]) == 6
    assert "could not be read" in capsys.readouterr().err
    assert record.main(["size", "--project", KEY, "--json"]) == 6
    assert "could not be read" in capsys.readouterr().err

    _use(record, monkeypatch, [])
    assert record.main(["size", "--project", KEY, "--json"]) == 0
    reading = json.loads(capsys.readouterr().out)
    assert reading["relations"][0] == {
        "relation": "agent_audit",
        "rows": 12,
        "oldest": "2026-09-01 10:00:00+00",
    }


def test_size_refuses_without_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real `require_root`, with the uid read as a user's: exit 3."""
    module = _load()
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)
    assert module.main(["size", "--project", KEY]) == 3


def test_nothing_schedules_a_prune() -> None:
    """ADR 0213 and 0248: nothing prunes on its own. The command and the five
    functions are named only by the command itself and the migrations that
    create them -- no unit, timer, service or other `bin/` command calls them.

    The control is that the scan FINDS the command's own two files: a scan that
    found nothing anywhere would pass on a broken glob.
    """
    names = re.compile(
        r"(?<![\w-])record\.(?:sh|py)\b|\b(?:workflow_run_prune|connector_delivery_prune"
        r"|agent_prune|agent_audit_prune|agent_idempotency_prune)\b"
    )
    found = set()
    for root in ("systemd", "bin", "services", "infra", "src"):
        for path in (REPO_ROOT / root).rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if names.search(text):
                found.add(str(path.relative_to(REPO_ROOT)))
    assert found == {"bin/record.sh", "bin/record.py"}, sorted(found)

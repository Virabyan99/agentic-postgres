"""`bin/control.sh adopt|registry|totp-reset`: the control plane's operator verbs (CTL-REG-001).

The command is loaded as a module and its one outward edge --
`container_exec.run` -- is replaced by a recorder, as `test_record_command.py`
does, so every proof can say what WAS and was NOT sent to a container.
`require_root` is replaced too, and checked against the real function by
`test_adopt_requires_root_and_a_confirmation`.

`read_deployed_document` is replaced by a stand-in that keeps the one property
these proofs read -- versions 19 and 20 are read, anything else raises, as
`deployed_output.UnreadableVersion` does -- so the documents here carry only the
members the command asks for. What the database does with each call is
`test_control_set.py`'s (the three functions executable by no role, a project
adopted as the superuser); what is proved here is the command's half.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

CONTROL = "control-prod"
CONTAINER = "apg-control-prod-postgres-1"
DATABASE = "control_prod"
ORG = "0b5c6f0e-8d0e-4c3a-9a4e-3f1d2b7c9e11"
COMMIT = "2538ac0" + "0" * 33


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("apg_control", REPO_ROOT / "bin" / "control.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _document(key: str, *, version: int = 20, control: bool | None = False) -> dict[str, Any]:
    slug, environment = key.rsplit("-", 1)
    document: dict[str, Any] = {
        "schema_version": version,
        "document_kind": "deployed",
        "project": {
            "key": key,
            "slug": slug,
            "environment": environment,
            "domain": f"{slug}.example.com",
        },
        "template_version": "1.14.0",
        "source_commit": COMMIT,
        "database": {"container": f"apg-{key}-postgres-1", "name": key.replace("-", "_")},
    }
    if control is not None:
        document["control"] = {"enabled": control}
    return document


def _row(key: str, **changes: str) -> dict[str, Any]:
    document = _document(key)
    row = {
        "key": key,
        "organization_id": ORG,
        **{name: document["project"][name] for name in ("slug", "environment", "domain")},
        "template_version": document["template_version"],
        "source_commit": document["source_commit"],
        "adopted_at": "2026-10-06T10:00:00+00:00",
    }
    row.update(changes)
    return row


def _read_by_version(raw: Any) -> dict[str, Any]:
    if raw.get("schema_version") not in (19, 20):
        raise ValueError(
            f"the deployed document is outputs version {raw.get('schema_version')}; "
            "this release reads versions 19 and 20"
        )
    return raw


class Recorder:
    """`container_exec.run`'s stand-in: records each call, answers from a script."""

    def __init__(self, answers: list[tuple[int, str, str]]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._answers = list(answers)

    def __call__(self, container: str, *argv: str, **kwargs: Any) -> Any:
        self.calls.append({"container": container, "argv": list(argv), **kwargs})
        code, out, err = self._answers.pop(0) if self._answers else (0, "control-prod\n", "")
        return subprocess.CompletedProcess(argv, code, out, err)


class Host:
    """The state root a proof owns, and the module pointed at it."""

    def __init__(self, module: Any, state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.module = module
        self.state = state
        self._monkeypatch = monkeypatch

    def write(self, key: str, document: dict[str, Any] | str) -> None:
        (self.state / key).mkdir(parents=True, exist_ok=True)
        text = document if isinstance(document, str) else json.dumps(document)
        (self.state / key / "outputs.json").write_text(text, encoding="utf-8")

    def answer(self, *answers: tuple[int, str, str]) -> Recorder:
        recorder = Recorder(list(answers))
        self._monkeypatch.setattr(self.module.container_exec, "run", recorder)
        return recorder

    def main(self, *argv: str) -> int:
        return self.module.main(list(argv))


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Host:
    module = _load()
    state = tmp_path / "projects"
    state.mkdir()
    monkeypatch.setattr(module, "STATE_ROOT", state)
    monkeypatch.setattr(module, "require_root", lambda: None)
    monkeypatch.setattr(module.deployed_output, "read_deployed_document", _read_by_version)
    deployment = Host(module, state, monkeypatch)
    deployment.write(CONTROL, _document(CONTROL, control=True))
    # Alpha and beta at 1.14.0 wrote outputs 19, which has no `control` member.
    deployment.write("alpha-dev", _document("alpha-dev", version=19, control=None))
    deployment.write("beta-dev", _document("beta-dev", version=19, control=None))
    return deployment


def _registry_answer(*rows: dict[str, Any]) -> tuple[int, str, str]:
    return (0, json.dumps(list(rows)) + "\n", "")


def _lines(out: str) -> dict[str, str]:
    """`registry`'s text, below its heading, as project -> what was said."""
    return dict(line.split(None, 1) for line in out.splitlines()[1:])


def test_adopt_requires_root_and_a_confirmation(
    host: Host, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without root, without `--confirm`, with a confirmation that is not the
    control project's key EXACTLY (a different case included), with a malformed
    organisation, or with a key that has no deployed document: refused, and
    nothing sent. The control: the same call with all of it right is ONE call
    into the CONTROL project's container, every value a `psql` variable."""
    adopt = ("adopt", "--project", "alpha-dev", "--organization", ORG)
    recorder = host.answer()

    real = _load()
    monkeypatch.setattr(real.os, "geteuid", lambda: 1000)
    assert real.main([*adopt, "--confirm", CONTROL]) == 3
    assert "must run as root" in capsys.readouterr().err

    assert host.main(*adopt) == 2
    assert host.main(*adopt, "--confirm", "alpha-dev") == 2
    assert host.main(*adopt, "--confirm", CONTROL.upper()) == 2
    assert "nothing was adopted" in capsys.readouterr().err
    assert (
        host.main(
            "adopt", "--project", "alpha-dev", "--organization", "org-1", "--confirm", CONTROL
        )
        == 2
    )
    assert (
        host.main("adopt", "--project", "../alpha-dev", "--organization", ORG, "--confirm", CONTROL)
        == 2
    )
    assert (
        host.main("adopt", "--project", "gamma-dev", "--organization", ORG, "--confirm", CONTROL)
        == 3
    )
    assert "no deployed document for gamma-dev" in capsys.readouterr().err
    assert recorder.calls == [], "a refused adopt reached a container"

    assert host.main(*adopt, "--confirm", CONTROL) == 0
    (call,) = recorder.calls
    assert call["container"] == CONTAINER
    assert call["argv"][:6] == ["psql", "-U", "postgres", "-d", DATABASE, "-X"]
    assert call["input"] == host.module.ADOPT_SQL
    for variable in (
        "key=alpha-dev",
        f"organization={ORG}",
        "slug=alpha",
        "environment=dev",
        "domain=alpha.example.com",
        "template_version=1.14.0",
        f"source_commit={COMMIT}",
    ):
        assert variable in call["argv"], variable
    assert "alpha" not in call["input"], "a value was interpolated into the SQL"
    assert "adopted alpha-dev" in capsys.readouterr().out


def test_the_control_project_is_found_by_its_facility(
    host: Host, capsys: pytest.CaptureFixture[str]
) -> None:
    """D2068: found by `control.enabled`, never by name. A directory called
    anything is the control project when its document enables the facility; an
    outputs-19 document predates the facility; none is exit 3, two is exit 5
    naming both, and an unreadable neighbour stops a DECISION (exit 6) while the
    registry, a report, still reads."""
    host.write(CONTROL, _document(CONTROL, control=False))
    host.write("ops-main", _document("ops-main", control=True))
    recorder = host.answer((0, "t\n", ""))
    assert host.main("totp-reset", "--username", "operator", "--confirm", CONTROL) == 2
    assert host.main("totp-reset", "--username", "operator", "--confirm", "ops-main") == 0
    (call,) = recorder.calls
    assert call["container"] == "apg-ops-main-postgres-1"
    assert call["argv"][4] == "ops_main"

    host.write("ops-main", _document("ops-main", control=False))
    assert host.main("registry") == 3
    assert "no deployed project enables the control facility" in capsys.readouterr().err

    host.write(CONTROL, _document(CONTROL, control=True))
    host.write("ops-main", _document("ops-main", control=True))
    assert host.main("registry") == 5
    assert f"{CONTROL}, ops-main" in capsys.readouterr().err
    assert len(recorder.calls) == 1, "an ambiguous search reached a container"

    host.write("ops-main", "{ not json")
    assert (
        host.main("adopt", "--project", "alpha-dev", "--organization", ORG, "--confirm", CONTROL)
        == 6
    )
    assert "could not be determined" in capsys.readouterr().err
    assert len(recorder.calls) == 1, "a decision acted on a search it could not finish"
    host.answer(_registry_answer(_row(CONTROL), _row("alpha-dev"), _row("beta-dev")))
    assert host.main("registry") == 6
    said = _lines(capsys.readouterr().out)
    assert said["ops-main"].startswith("could not determine: "), said
    assert said["alpha-dev"] == "agrees"


def test_registry_reports_three_outcomes(host: Host, capsys: pytest.CaptureFixture[str]) -> None:
    """Agreement, a difference naming its fields, and both directions of
    absence -- a row with no document, a document with no row. Exit 5 on any of
    them; the control: every row agreeing is exit 0, in text and in `--json`."""
    host.write("delta-dev", _document("delta-dev", version=19, control=None))
    host.answer(
        _registry_answer(
            _row(CONTROL),
            _row("alpha-dev"),
            _row("beta-dev", source_commit="f" * 40, domain="old.example.com"),
            _row("ghost-dev"),
        )
    )
    assert host.main("registry") == 5
    assert _lines(capsys.readouterr().out) == {
        "alpha-dev": "agrees",
        "beta-dev": "differs: domain, source_commit",
        CONTROL: "agrees",
        "delta-dev": "not in the registry",
        "ghost-dev": "no deployed document",
    }

    (host.state / "delta-dev" / "outputs.json").unlink()
    host.answer(_registry_answer(_row(CONTROL), _row("alpha-dev"), _row("beta-dev")))
    assert host.main("registry") == 5
    assert _lines(capsys.readouterr().out)["delta-dev"] == "no deployed document"

    (host.state / "delta-dev").rmdir()
    recorder = host.answer(_registry_answer(_row(CONTROL), _row("alpha-dev"), _row("beta-dev")))
    assert host.main("registry", "--json") == 0
    (call,) = recorder.calls
    assert call["container"] == CONTAINER
    assert call["input"] == host.module.REGISTRY_SQL
    reading = json.loads(capsys.readouterr().out)
    assert reading["control_project"] == CONTROL
    assert [(p["project"], p["outcome"]) for p in reading["projects"]] == [
        ("alpha-dev", "agrees"),
        ("beta-dev", "agrees"),
        (CONTROL, "agrees"),
    ]


def test_an_unreadable_document_is_undetermined_not_agreeing(
    host: Host, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0195's third outcome. Beta's row matches what beta's document said;
    the document then becomes unreadable -- not JSON, a version this release does
    not read, or missing a pointer -- and each time beta reads *could not
    determine* and the exit is 6, never `agrees` and never 0. A registry that
    could not be read is exit 6 too. The control: the readable document agrees."""
    rows = _registry_answer(_row(CONTROL), _row("alpha-dev"), _row("beta-dev"))
    for broken, said in (
        ("{ not json", "not valid JSON"),
        (_document("beta-dev", version=18, control=None), "outputs version 18"),
        (
            {**_document("beta-dev", version=19, control=None), "source_commit": None},
            "carries no source_commit",
        ),
    ):
        host.write("beta-dev", broken)
        host.answer(rows)
        assert host.main("registry") == 6, said
        beta = _lines(capsys.readouterr().out)["beta-dev"]
        assert beta.startswith("could not determine: ") and said in beta, beta

    host.answer((2, "", "psql: error: connection to server failed"))
    assert host.main("registry") == 6
    assert "the registry could not be read: psql: error" in capsys.readouterr().err
    host.answer((0, "garbage\n", ""))
    assert host.main("registry") == 6
    assert "shape asked for" in capsys.readouterr().err

    host.write("beta-dev", _document("beta-dev", version=19, control=None))
    host.answer(rows)
    assert host.main("registry") == 0
    assert _lines(capsys.readouterr().out)["beta-dev"] == "agrees"


def test_totp_reset_requires_the_confirmation(
    host: Host, capsys: pytest.CaptureFixture[str]
) -> None:
    """No confirmation, the wrong key, the right key in another case: exit 2 and
    nothing sent. The control: the right key removes a factor (`t`) or reports
    there was none (`f`), the username travelling as a variable; an answer in
    another shape is *not known*, exit 6; a database error is exit 5."""
    recorder = host.answer((0, "t\n", ""), (0, "f\n", ""), (0, "", ""), (3, "", "ERROR: boom"))
    reset = ("totp-reset", "--username", "o'neil")
    assert host.main(*reset) == 2
    assert host.main(*reset, "--confirm", "alpha-dev") == 2
    assert host.main(*reset, "--confirm", "Control-Prod") == 2
    assert host.main("totp-reset", "--username", "", "--confirm", CONTROL) == 2
    assert recorder.calls == []

    assert host.main(*reset, "--confirm", CONTROL) == 0
    assert "removed the second factor of o'neil" in capsys.readouterr().out
    assert recorder.calls[0]["input"] == host.module.TOTP_RESET_SQL
    assert "username=o'neil" in recorder.calls[0]["argv"]
    assert host.main(*reset, "--confirm", CONTROL) == 0
    assert "nothing was removed" in capsys.readouterr().out
    assert host.main(*reset, "--confirm", CONTROL) == 6
    assert "not known" in capsys.readouterr().err
    assert host.main(*reset, "--confirm", CONTROL) == 5
    assert "ERROR: boom" in capsys.readouterr().err


def test_every_exec_goes_through_container_exec() -> None:
    """ADR 0218's rule for new code: the command builds no argv for docker and
    starts no process of its own -- `container_exec.run` is its only edge. The
    control is that the scan finds that edge."""
    source = (REPO_ROOT / "bin" / "control.py").read_text(encoding="utf-8")
    assert "container_exec.run(" in source
    for forbidden in ("subprocess.run(", "subprocess.Popen(", "os.system(", '"docker"', "execvp"):
        assert forbidden not in source, forbidden


def test_a_deleted_project_agrees_only_with_its_tombstone(
    host: Host,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """D2167: a row the reconciler marked deleted agrees -- `agrees (deleted)`,
    exit 0 -- only when no document is deployed under its key AND the slot's
    tombstone is present. No tombstone is `differs: tombstone`; a document
    still deployed is `differs: deleted`; both exit 5."""
    slots = tmp_path / "slots"
    monkeypatch.setattr(host.module, "SLOT_ROOT", slots)
    deleted = _row("slot1-prod") | {"deleted_at": "2026-10-08T10:00:00+00:00"}
    rows = (_row(CONTROL), _row("alpha-dev"), _row("beta-dev"), deleted)

    host.answer(_registry_answer(*rows))
    assert host.main("registry") == 5
    assert _lines(capsys.readouterr().out)["slot1-prod"] == "differs: tombstone"

    (slots / "slot1-prod").mkdir(parents=True)
    (slots / "slot1-prod" / "consumed").write_text("", "utf-8")
    host.answer(_registry_answer(*rows))
    assert host.main("registry") == 0
    assert _lines(capsys.readouterr().out)["slot1-prod"] == "agrees (deleted)"
    host.answer(_registry_answer(*rows))
    assert host.main("registry", "--json") == 0
    projects = json.loads(capsys.readouterr().out)["projects"]
    assert [o["outcome"] for o in projects if o["project"] == "slot1-prod"] == ["deleted"]

    host.write("slot1-prod", _document("slot1-prod", version=19, control=None))
    host.answer(_registry_answer(*rows))
    assert host.main("registry") == 5
    assert _lines(capsys.readouterr().out)["slot1-prod"] == "differs: deleted"

    # Control: the same row without `deleted_at`, beside the same document, agrees.
    host.answer(_registry_answer(*rows[:3], _row("slot1-prod")))
    assert host.main("registry") == 0
    assert _lines(capsys.readouterr().out)["slot1-prod"] == "agrees"


def test_a_prepared_slot_agrees(
    host: Host,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """D2341 (D2307 on the host): a slot between its bootstrap and its creation
    -- the slot manifest `slot.sh prepare` wrote, the bootstrap state in the
    state root, no document and no row -- reads `prepared (slot)`, agreeing,
    exit 0. Each half alone is still a difference (exit 5): a directory with
    only a bootstrap state is not a prepared slot, and neither is a manifest
    with no state directory's record."""
    slots = tmp_path / "slots"
    monkeypatch.setattr(host.module, "SLOT_ROOT", slots)
    rows = (_row(CONTROL), _row("alpha-dev"), _row("beta-dev"))
    (host.state / "slot3-prod").mkdir()
    (host.state / "slot3-prod" / "bootstrap-state.json").write_text("{}", "utf-8")

    host.answer(_registry_answer(*rows))
    assert host.main("registry") == 5, "a bootstrap state alone was read as a prepared slot"
    assert _lines(capsys.readouterr().out)["slot3-prod"] == "no deployed document"

    (slots / "slot3-prod").mkdir(parents=True)
    (slots / "slot3-prod" / "manifest.yaml").write_text("project: {}\n", "utf-8")
    host.answer(_registry_answer(*rows))
    assert host.main("registry") == 0
    assert _lines(capsys.readouterr().out)["slot3-prod"] == "prepared (slot)"
    host.answer(_registry_answer(*rows))
    assert host.main("registry", "--json") == 0
    projects = json.loads(capsys.readouterr().out)["projects"]
    assert [o["outcome"] for o in projects if o["project"] == "slot3-prod"] == ["prepared"]

    # The manifest without the state's record is not prepared either.
    (host.state / "slot3-prod" / "bootstrap-state.json").unlink()
    host.answer(_registry_answer(*rows))
    assert host.main("registry") == 5
    assert _lines(capsys.readouterr().out)["slot3-prod"] == "no deployed document"

    # And a key that is not a slot's never reads prepared, whatever it holds.
    (host.state / "gamma-dev").mkdir()
    (host.state / "gamma-dev" / "bootstrap-state.json").write_text("{}", "utf-8")
    host.answer(_registry_answer(*rows))
    assert host.main("registry") == 5
    assert _lines(capsys.readouterr().out)["gamma-dev"] == "no deployed document"


def _typed_set(source: str, name: str) -> frozenset[str] | None:
    """The string members of `NAME = frozenset({...})` at a module's top level."""
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and [getattr(t, "id", None) for t in node.targets] == [name]
            and isinstance(node.value, ast.Call)
            and node.value.args
            and isinstance(node.value.args[0], ast.Set)
        ):
            return frozenset(
                e.value for e in node.value.args[0].elts if isinstance(e, ast.Constant)
            )
    return None


def test_the_live_registry_proof_tolerates_every_agreeing_outcome_and_no_other() -> None:
    """D2409: `prepared` (D2341) joined `control.AGREEING` and the sweep's
    registry proof still read it as a difference -- a reader of the outcomes
    that did not move. The proof types its own set (it must not share the
    command's belief); this holds that set to the command's agreeing outcomes
    other than `agrees`, read from the proof's text. The control: the scan
    finds a planted set and misses an absent one."""
    proof = REPO_ROOT / "tests" / "deployment" / "test_session37_control.py"
    typed = _typed_set(proof.read_text("utf-8"), "AGREEING_WITHOUT_A_DOCUMENT")
    assert typed == _load().AGREEING - {"agrees"}, typed
    planted = 'X = frozenset({"deleted"})\n'
    assert _typed_set(planted, "X") == {"deleted"}
    assert _typed_set(planted, "AGREEING_WITHOUT_A_DOCUMENT") is None


# -- `status` (ADR 0293, OPS-CTLSTATUS-001) -------------------------------------------------

#: The sections ADR 0293 names, typed here rather than read from the command.
STATUS_SECTION_NAMES = {
    "organizations",
    "projects",
    "operations",
    "branches",
    "slots",
    "notifications",
}


def _op(kind: str, status: str, error: str | None = None, at: str = "10:00") -> dict[str, Any]:
    return {
        "type": kind,
        "status": status,
        "error_code": error,
        "created_at": f"2026-10-24T{at}:00+00:00",
    }


def _project_row(
    key: str, history: list[dict[str, Any]], *, deleted_at: str | None = None
) -> dict[str, Any]:
    return {
        "key": key,
        "organization": "Virabyan",
        "slot": key if key.startswith("slot") else None,
        "profile": "small" if key.startswith("slot") else None,
        "deleted_at": deleted_at,
        "history": history,
    }


def _status_rows() -> dict[str, Any]:
    """One answer per section, in the shape each SELECT asks for. The states
    the projects must read are typed beside them in the tests below."""
    return {
        "organizations": [
            {
                "id": ORG,
                "name": "Virabyan",
                "plan": "free",
                "owners": ["andranik"],
                "projects": 1,
                "projects_limit": 1,
            }
        ],
        "projects": [
            _project_row("alpha-dev", []),
            _project_row(
                "slot3-prod",
                [_op("project.create", "succeeded"), _op("project.sleep", "succeeded", at="11:00")],
            ),
            _project_row(
                "slot5-prod",
                [
                    _op("project.create", "succeeded"),
                    _op("project.resize", "failed", "interrupted", at="11:00"),
                    _op("branch.create", "running", at="12:00"),
                ],
            ),
            _project_row(
                "slot2-prod",
                [
                    _op("project.create", "succeeded"),
                    _op("project.delete", "succeeded", at="11:00"),
                ],
                deleted_at="2026-10-24T11:05:00+00:00",
            ),
        ],
        "operations": [
            {
                "id": "6f1d2b7c-9e11-4c3a-9a4e-0b5c6f0e8d0e",
                "organization": "Virabyan",
                "project_key": None,
                "type": "project.create",
                "status": "running",
                "step": "deploy",
                "created_at": "2026-10-24T12:00:00+00:00",
                "started_at": "2026-10-24T12:00:05+00:00",
            }
        ],
        "branches": [
            {"project_key": "slot3-prod", "name": "dev", "state": "ready", "expires_at": None}
        ],
        "slots": [{"state": "allocated", "slots": 2}, {"state": "consumed", "slots": 9}],
        "notifications": [{"kind": "operation_succeeded", "notifications": 3}],
    }


class StatusRecorder:
    """`container_exec.run`'s stand-in for `status`: answers each call by the
    section whose SELECT it carried -- a statement that is no section's SQL
    fails the unpacking, so nothing outside the sections can be sent unseen."""

    def __init__(self, module: Any, answers: dict[str, Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._module = module
        self._answers = answers

    def __call__(self, container: str, *argv: str, **kwargs: Any) -> Any:
        self.calls.append({"container": container, "argv": list(argv), **kwargs})
        (name,) = [n for n, sql in self._module.STATUS_SECTIONS.items() if sql == kwargs["input"]]
        self.calls[-1]["section"] = name
        answer = self._answers[name]
        if isinstance(answer, BaseException):
            raise answer
        if not isinstance(answer, tuple):
            answer = (0, json.dumps(answer) + "\n", "")
        return subprocess.CompletedProcess(argv, *answer)


def _answer_status(host: Host, monkeypatch: pytest.MonkeyPatch, **changes: Any) -> StatusRecorder:
    answers = {**_status_rows(), **changes}
    recorder = StatusRecorder(host.module, answers)
    monkeypatch.setattr(host.module.container_exec, "run", recorder)
    return recorder


#: What a status SELECT may never do or read: a write, a function of the
#: control set (each of which may write), and any table or column holding a
#: hash, a key, a token, an address or a credential.
_WRITES = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|CREATE|DROP|GRANT|REVOKE|COPY|CALL|MERGE|"
    r"nextval|setval|set_config|pg_advisory\w*)\b|\bapp\.\w+\s*\(",
    re.IGNORECASE,
)
_SECRET_READS = re.compile(
    r"\b(control_keys|control_invitations|control_totp|result_secret|result|arguments|token\w*|"
    r"\w*secret\w*|\w*hash\w*|password\w*|endpoints|pool_host|direct_host|app_route|domain)\b",
    re.IGNORECASE,
)


def test_status_runs_only_selects(
    host: Host, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0293 decision 1: one SELECT per section, as the cluster's superuser
    in the CONTROL project's container, nothing written and no secret column
    read. The control: every section answered in its shape reads exit 0, and
    the scan finds a planted write and a planted secret column."""
    recorder = _answer_status(host, monkeypatch)
    assert host.main("status") == 0, capsys.readouterr().err
    assert {call["section"] for call in recorder.calls} == STATUS_SECTION_NAMES
    assert len(recorder.calls) == len(STATUS_SECTION_NAMES)
    for call in recorder.calls:
        assert call["container"] == CONTAINER
        assert call["argv"][:5] == ["psql", "-U", "postgres", "-d", DATABASE]
        statement = call["input"].strip()
        assert statement.endswith(";") and ";" not in statement[:-1], (call["section"], statement)
        assert statement.upper().startswith("SELECT "), (call["section"], statement)
        assert not _WRITES.search(statement), (call["section"], _WRITES.search(statement))
        assert not _SECRET_READS.search(statement), (
            call["section"],
            _SECRET_READS.search(statement),
        )
    assert _WRITES.search("SELECT 1; DELETE FROM app.control_slots;")
    assert _WRITES.search("SELECT app.control_totp_reset('x');")
    assert _SECRET_READS.search("SELECT o.result_secret FROM app.control_operations o;")
    assert _SECRET_READS.search("SELECT k.key_hash FROM app.control_keys k;")


def test_status_states_are_the_services(
    host: Host, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0293 decision 2 (D704): each state is `control_states.project_state`
    -- the service's own function object, loaded as `plans` is -- over the
    project's operations oldest first, read in the order the service reads
    them (0004's `ORDER BY created_at, id`). Typed expectations: no history
    is `ready (operator-managed)`, create+sleep `sleeping`, an interrupted
    resize followed by a branch `unknown`; a deleted project is counted, never
    listed. The control: replacing the shared function replaces every state."""
    from agentic_postgres import control_states, service_source

    module = host.module
    assert module.control_states.project_state is control_states.project_state
    assert control_states.project_state is service_source.load("control_states").project_state
    assert re.search(r"ORDER BY \w+\.created_at, \w+\.id", module.STATUS_SECTIONS["projects"]), (
        "the history is not read oldest first, as the service reads it"
    )

    _answer_status(host, monkeypatch)
    assert host.main("status", "--json") == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["control_project"] == CONTROL
    listed = {p["key"]: p for p in answer["projects"]["listed"]}
    assert answer["projects"]["deleted"] == 1
    assert set(listed) == {"alpha-dev", "slot3-prod", "slot5-prod"}
    assert (listed["alpha-dev"]["state"], listed["alpha-dev"]["managed_by"]) == (
        "ready",
        "operator",
    )
    assert listed["slot3-prod"]["state"] == "sleeping"
    assert listed["slot5-prod"]["state"] == "unknown"
    assert listed["slot3-prod"]["last_operation"] == {
        "type": "project.sleep",
        "status": "succeeded",
        "created_at": "2026-10-24T11:00:00+00:00",
    }
    assert listed["alpha-dev"]["last_operation"] is None
    for row in _status_rows()["projects"]:
        if row["key"] in listed:
            assert listed[row["key"]]["state"] == control_states.project_state(row["history"])[0]

    _answer_status(host, monkeypatch)
    assert host.main("status") == 0
    text = capsys.readouterr().out
    lines = {line.split()[0]: line for line in text.splitlines() if line.startswith("  ")}
    assert "ready (operator-managed)" in lines["alpha-dev"]
    assert "sleeping" in lines["slot3-prod"]
    assert "slot2-prod" not in lines
    assert "1 deleted" in text

    monkeypatch.setattr(module.control_states, "project_state", lambda h: ("sentinel", "x"))
    _answer_status(host, monkeypatch)
    assert host.main("status", "--json") == 0
    answer = json.loads(capsys.readouterr().out)
    assert {p["state"] for p in answer["projects"]["listed"]} == {"sentinel"}


def test_status_names_an_unread_section(
    host: Host, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0293 decision 3 (ADR 0195): a section the cluster refused, one that
    answered in a shape nobody asked for and one that never answered are each
    printed as *could not be read* with the reason, the others still printed,
    exit 6 -- never 0 with a section folded to empty. `--json` carries
    `{"unread": reason}`. The control is `test_status_runs_only_selects`'s
    exit 0 with every section in its shape.

    The refusal is psql's as rig 46c read it: the ERROR line, then the
    statement and a caret -- the reason is the ERROR line, never the caret."""
    refusal = (
        'psql:<stdin>:1: ERROR:  relation "app.control_branches" does not exist\n'
        "LINE 1: SELECT b.project_key FROM app.control_branches b;\n"
        "                                  ^\n"
    )
    changes: dict[str, Any] = {
        "branches": (1, "", refusal),
        "slots": (0, "not json\n", ""),
        "notifications": [{"kind": 3}],
        "operations": subprocess.TimeoutExpired("psql", 120),
    }
    _answer_status(host, monkeypatch, **changes)
    assert host.main("status") == 6
    text = capsys.readouterr().out
    headed = {line.split()[0]: line for line in text.splitlines() if not line.startswith("  ")}
    assert 'could not be read: ERROR:  relation "app.control_branches"' in headed["branches"]
    assert (
        "could not be read: the reading did not arrive in the shape asked for" in (headed["slots"])
    )
    assert "could not be read" in headed["notifications"]
    assert "could not be read" in headed["operations"]
    assert "could not be read" not in headed["organisations"]
    assert "Virabyan" in text and "slot3-prod" in text

    _answer_status(host, monkeypatch, **changes)
    assert host.main("status", "--json") == 6
    answer = json.loads(capsys.readouterr().out)
    for name in changes:
        assert set(answer[name]) == {"unread"}, (name, answer[name])
        assert answer[name]["unread"], name
    assert isinstance(answer["organizations"], list) and answer["organizations"]
    assert answer["projects"]["listed"]


def test_status_needs_root(
    host: Host, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Root, as the other verbs (the control project's database is reached as
    its superuser): without it exit 3 and nothing sent. `--help` is a read the
    shell answers before root, and the verb is in the shell's `case`. The
    control: the same call with root is `test_status_runs_only_selects`'s 0."""
    recorder = _answer_status(host, monkeypatch)
    real = _load()
    monkeypatch.setattr(real.os, "geteuid", lambda: 1000)
    assert real.main(["status"]) == 3
    assert "must run as root" in capsys.readouterr().err
    assert recorder.calls == [], "status reached a container without root"

    shell = str(REPO_ROOT / "bin" / "control.sh")
    shown = subprocess.run(
        [shell, "status", "--help"], capture_output=True, text=True, check=False,
        stdin=subprocess.DEVNULL,
    )  # fmt: skip
    assert shown.returncode == 0 and "sudo bin/control.sh status [--json]" in shown.stdout
    unknown = subprocess.run(
        [shell, "frobnicate"], capture_output=True, text=True, check=False,
        stdin=subprocess.DEVNULL,
    )  # fmt: skip
    assert unknown.returncode == 2 and " status " in unknown.stderr, unknown.stderr

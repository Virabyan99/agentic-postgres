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

import importlib.util
import json
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

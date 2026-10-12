"""`bin/slot.sh prepare|status|revoke` and `agentic_postgres.slot` (SLOT-001; ADR 0257).

D2149: a slot is DECLARED in the host manifest and its state is DERIVED from
what exists on the host -- never written. D2150: `prepare` writes the slot's
manifest through the product's own loader and refuses a slot not in the state
to receive one; `status` names every state with its reason and exits 6 on any
`undetermined`; `revoke` revokes a CONSUMED slot's identity from the state its
deletion kept (D2158). D2148: `ready` needs a DNS reading that was taken.

The command is loaded as a module with its roots moved under tmp, `require_root`
replaced, and its two outward edges -- `dns_reading` and `subprocess.run` --
replaced by recorders.
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
import yaml

from agentic_postgres import REPO_ROOT, config, host_config, slot

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

HOST = REPO_ROOT / "host.example.yaml"
KEY = "slot1-dev"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("apg_slot", REPO_ROOT / "bin" / "slot.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = _load()
    for name in ("SLOT_ROOT", "STATE_ROOT", "SECRET_ROOT"):
        monkeypatch.setattr(module, name, tmp_path / name.lower())
    monkeypatch.setattr(module, "require_root", lambda: None)
    monkeypatch.setattr(module, "dns_reading", lambda domain, expected: (True, "recorded"))
    return module


def _prepared(command: Any) -> None:
    """The provider half of the sheet, as files: the bootstrap state and an
    active secret generation (what `bootstrap-providers --apply` and
    `materialize-secrets` write)."""
    state = command.STATE_ROOT / KEY
    state.mkdir(parents=True, exist_ok=True)
    (state / "bootstrap-state.json").write_text('{"runtime_identity_id": "id-1"}\n', "utf-8")
    generation = command.SECRET_ROOT / KEY / "generations" / "g1"
    generation.mkdir(parents=True, exist_ok=True)
    (generation / "manifest.json").write_text("{}", "utf-8")
    (command.SECRET_ROOT / KEY / "active-secret-generation.json").write_text(
        '{"generation_id": "g1"}\n', "utf-8"
    )


def _status(command: Any, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    code = command.main(["status", "--host", str(HOST), "--json"])
    rows = {row["key"]: row for row in json.loads(capsys.readouterr().out)["slots"]}
    return code, rows[KEY]


def test_prepare_writes_a_manifest_the_loader_accepts(
    command: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """0600 in a 0700 directory, loaded by the product, the profile `small`,
    every provider fact from the host's `slots.defaults` -- and a second
    prepare, an undeclared slot and a consumed slot are refused."""
    assert command.main(["prepare", "--host", str(HOST), "--slot", KEY]) == 0
    written = command.SLOT_ROOT / KEY / slot.MANIFEST
    assert oct(written.stat().st_mode & 0o777) == "0o600"
    assert oct(written.parent.stat().st_mode & 0o777) == "0o700"
    loaded = config.load_project_manifest(written)
    host = host_config.load_host_manifest(HOST)
    defaults = host_config.slot_defaults(host)
    assert loaded["compute"] == {"profile": "small"}
    assert loaded["project"]["domain"] == "slot1.example.test"
    assert loaded["project"]["lifecycle"] == {"kind": "permanent"}
    assert loaded["backup"]["account_id"] == defaults["backup"]["account_id"]
    assert loaded["backup"]["mirror"]["endpoint"] == defaults["backup"]["mirror"]["endpoint"]
    assert loaded["storage"]["account_id"] == defaults["storage"]["account_id"]
    assert "migrations" not in yaml.safe_load(written.read_text("utf-8"))
    assert [p.name for p in written.parent.iterdir()] == [slot.MANIFEST], "a temporary was left"
    capsys.readouterr()

    assert command.main(["prepare", "--host", str(HOST), "--slot", KEY]) == 5
    assert "already prepared" in capsys.readouterr().err
    assert command.main(["prepare", "--host", str(HOST), "--slot", "slot2-dev"]) == 5
    assert "not declared" in capsys.readouterr().err
    assert command.main(["prepare", "--host", str(HOST), "--slot", "../etc"]) == 2


def test_status_derives_each_state_from_what_exists(
    command: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """declared -> prepared (DNS false) -> ready -> allocated -> quarantined
    -> consumed, each read from files alone; nothing writes a state."""
    code, row = _status(command, capsys)
    assert (code, row["state"]) == (0, "declared")
    assert command.main(["prepare", "--host", str(HOST), "--slot", KEY]) == 0
    capsys.readouterr()
    code, row = _status(command, capsys)
    assert (code, row["state"]) == (0, "declared")
    assert "bootstrap state" in row["reason"]
    _prepared(command)
    command.dns_reading = lambda domain, expected: (False, "no A record")
    assert _status(command, capsys)[1]["state"] == "prepared"
    command.dns_reading = lambda domain, expected: (True, "A 203.0.113.10")
    code, row = _status(command, capsys)
    assert (code, row["state"], row["region_id"]) == (0, "ready", "eu-example-1")
    directory = command.SLOT_ROOT / KEY
    for marker, expected in (
        (slot.ALLOCATED, "allocated"),
        (slot.QUARANTINED, "quarantined"),
        (slot.CONSUMED, "consumed"),
    ):
        (directory / marker).write_text("", "utf-8")
        assert _status(command, capsys)[1]["state"] == expected, marker
    # Nothing under the slot's directory but what was written above.
    assert sorted(p.name for p in directory.iterdir()) == sorted(
        [slot.MANIFEST, slot.ALLOCATED, slot.QUARANTINED, slot.CONSUMED]
    )


def test_an_unreadable_dns_reading_is_undetermined_never_ready(
    command: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """D2148 and ADR 0195: a prepared slot whose DNS could not be read is
    `undetermined`, and the command exits 6 -- never `ready`, never 0."""
    assert command.main(["prepare", "--host", str(HOST), "--slot", KEY]) == 0
    _prepared(command)
    capsys.readouterr()
    command.dns_reading = lambda domain, expected: (None, "dig is not installed")
    code, row = _status(command, capsys)
    assert (code, row["state"]) == (6, "undetermined"), row
    assert "dig is not installed" in row["reason"]
    # The same with an unreadable marker: undetermined, not the state below it.
    command.dns_reading = lambda domain, expected: (True, "A 203.0.113.10")
    readings = slot.read(
        KEY,
        dns=True,
        slot_root=command.SLOT_ROOT,
        state_root=command.STATE_ROOT,
        secret_root=command.SECRET_ROOT,
    )
    for field in ("consumed", "quarantined", "allocated", "secret_generation"):
        unread = slot.Readings(**{**readings.__dict__, field: None})
        assert slot.state(unread)[0] == "undetermined", field
    # Control: every reading taken, and the slot is ready.
    code, row = _status(command, capsys)
    assert (code, row["state"]) == (0, "ready")
    assert slot.state(readings)[0] == "ready"


def test_a_slot_is_ready_only_when_all_three_records_are(
    command: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0268 (D2335, D2342): a slot with public endpoints has THREE grey
    records -- its domain, `pool.` and `direct.` below it -- and is `ready` only
    when every one is this host alone. Each name wrong in turn keeps it
    `prepared` with THAT name in the reason; an unreadable name with none wrong
    is `undetermined` (exit 6); a wrong name decides even beside an unreadable
    one. Control: all three right -> `ready`. The slot's manifest asks for the
    door it is read for: schema 11, `public_endpoints.enabled: true`."""
    assert command.main(["prepare", "--host", str(HOST), "--slot", KEY]) == 0
    _prepared(command)
    capsys.readouterr()
    domain = "slot1.example.test"
    names = (domain, f"pool.{domain}", f"direct.{domain}")
    asked: list[str] = []

    def reading(wrong: str | None = None, unread: str | None = None) -> Any:
        def dns(name: str, expected: str | None) -> tuple[bool | None, str]:
            asked.append(name)
            if name == wrong:
                return False, f"{name} resolves to 188.114.96.1, not {expected} alone"
            if name == unread:
                return None, f"dig A {name} did not answer"
            return True, f"{name} A {expected}, no AAAA"

        return dns

    for wrong in names:
        command.dns_reading = reading(wrong=wrong)
        code, row = _status(command, capsys)
        assert (code, row["state"]) == (0, "prepared"), (wrong, row)
        assert wrong in row["reason"], (wrong, row["reason"])
    command.dns_reading = reading(unread=f"direct.{domain}")
    code, row = _status(command, capsys)
    assert (code, row["state"]) == (6, "undetermined") and "direct." in row["reason"], row
    command.dns_reading = reading(wrong=f"pool.{domain}", unread=domain)
    assert _status(command, capsys)[1]["state"] == "prepared"
    asked.clear()
    command.dns_reading = reading()
    code, row = _status(command, capsys)
    assert (code, row["state"]) == (0, "ready"), row
    assert asked == list(names), asked

    manifest = yaml.safe_load((command.SLOT_ROOT / KEY / slot.MANIFEST).read_text("utf-8"))
    assert manifest["schema_version"] == 11
    assert manifest["database"]["public_endpoints"] == {"enabled": True}
    assert config.public_endpoints_enabled(manifest)


def test_nothing_removes_a_tombstone(command: Any, capsys: pytest.CaptureFixture[str]) -> None:
    """A consumed slot is never reissued: `prepare` refuses it and leaves the
    tombstone where it is, and no code in `bin/` or `src/` names the tombstone
    in a removal."""
    directory = command.SLOT_ROOT / KEY
    directory.mkdir(parents=True)
    tombstone = directory / slot.CONSUMED
    tombstone.write_text("deleted by operation 7\n", "utf-8")
    assert command.main(["prepare", "--host", str(HOST), "--slot", KEY]) == 5
    assert "consumed" in capsys.readouterr().err
    assert tombstone.read_text("utf-8") == "deleted by operation 7\n"
    assert not (directory / slot.MANIFEST).exists()

    removals = {"unlink", "remove", "rmtree", "rmdir"}
    offenders = []
    for path in [*(REPO_ROOT / "bin").glob("*.py"), *(REPO_ROOT / "src").rglob("*.py")]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name in removals and "CONSUMED" in ast.unparse(node):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], offenders
    for path in (REPO_ROOT / "bin").glob("*.sh"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\brm\b[^\n]*consumed", text), path.name


def test_revoke_restores_the_kept_state_and_runs_the_products_destroy(
    command: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    """D2158: only a consumed slot with a kept state; the state put back where
    `bootstrap-providers` reads it and `--destroy` run with the operator's
    credential; a `revoked` marker; the kept copy never removed. A failed
    destroy leaves no restored copy behind."""
    assert command.main(["prepare", "--host", str(HOST), "--slot", KEY]) == 0
    credential = tmp_path / "operator-credential"
    credential.write_text("id\nsecret\n", "utf-8")
    base = ["revoke", "--host", str(HOST), "--slot", KEY,
            "--operator-credential-file", str(credential)]  # fmt: skip
    directory = command.SLOT_ROOT / KEY
    live = command.STATE_ROOT / KEY / "bootstrap-state.json"
    kept = directory / slot.RETIRED_STATE
    calls: list[list[str]] = []
    exit_code = {"value": 0}

    def recorder(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        assert live.read_bytes() == kept.read_bytes(), "destroy ran without the kept state"
        if exit_code["value"] == 0:
            live.unlink()
        return subprocess.CompletedProcess(argv, exit_code["value"], "revoked identity", "")

    monkeypatch.setattr(command.subprocess, "run", recorder)
    assert command.main([*base, "--confirm", "slot9-dev"]) == 2
    assert command.main([*base, "--confirm", KEY]) == 5, "not consumed yet"
    (directory / slot.CONSUMED).write_text("", "utf-8")
    assert command.main([*base, "--confirm", KEY]) == 5, "no kept state"
    kept.write_text('{"runtime_identity_id": "id-1"}\n', "utf-8")
    live.parent.mkdir(parents=True)
    live.write_text("{}", "utf-8")
    assert command.main([*base, "--confirm", KEY]) == 5, "a live state holds the key"
    live.unlink()
    assert calls == []
    capsys.readouterr()

    exit_code["value"] = 7
    assert command.main([*base, "--confirm", KEY]) == 6
    assert not live.exists(), "a failed revocation left the restored copy"
    assert kept.exists() and not (directory / slot.REVOKED).exists()

    exit_code["value"] = 0
    assert command.main([*base, "--confirm", KEY]) == 0
    destroy = calls[-1]
    assert Path(destroy[0]).name == "bootstrap-providers.sh"
    assert destroy[destroy.index("--project") + 1] == str(directory / slot.MANIFEST)
    assert "--destroy" in destroy and destroy[destroy.index("--confirm") + 1] == KEY
    assert destroy[destroy.index("--operator-credential-file") + 1] == str(credential)
    marker = json.loads((directory / slot.REVOKED).read_text("utf-8"))
    assert marker["runtime_identity_id"] == "id-1"
    assert kept.exists(), "the kept state is the record and is never removed"
    assert command.main([*base, "--confirm", KEY]) == 5, "already revoked"


def test_revoke_removes_the_state_directory_it_made(
    command: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    """D2405: after a deletion the key has no state directory; `revoke` makes
    one for the destroy's copy, and an empty one left behind refused the next
    deploy's admission on the node. Removed after a destroy that succeeded AND
    one that failed. The control: a directory `revoke` did not make is left,
    and so is one the destroy did not empty -- named on stderr."""
    assert command.main(["prepare", "--host", str(HOST), "--slot", KEY]) == 0
    credential = tmp_path / "operator-credential"
    credential.write_text("id\nsecret\n", "utf-8")
    base = ["revoke", "--host", str(HOST), "--slot", KEY,
            "--operator-credential-file", str(credential), "--confirm", KEY]  # fmt: skip
    directory = command.SLOT_ROOT / KEY
    state = command.STATE_ROOT / KEY
    live = state / "bootstrap-state.json"
    (directory / slot.CONSUMED).write_text("", "utf-8")
    (directory / slot.RETIRED_STATE).write_text('{"runtime_identity_id": "id-1"}\n', "utf-8")
    behaviour = {"exit": 7, "leave": False}

    def destroy(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert live.is_file(), "destroy ran without the kept state"
        if behaviour["exit"] == 0:
            live.unlink()
        if behaviour["leave"]:
            (state / "stray").write_text("", "utf-8")
        return subprocess.CompletedProcess(argv, behaviour["exit"], "", "")

    monkeypatch.setattr(command.subprocess, "run", destroy)
    assert not state.exists(), "the fixture's slot has a state directory before any revoke"

    assert command.main(base) == 6
    assert not state.exists(), "a failed revocation left the directory it made"

    behaviour.update(exit=0, leave=True)
    assert command.main(base) == 0
    assert (state / "stray").exists(), "a directory the destroy did not empty was emptied"
    assert str(state) in capsys.readouterr().err
    (state / "stray").unlink()
    state.rmdir()
    (directory / slot.REVOKED).unlink()

    behaviour.update(leave=False)
    assert command.main(base) == 0
    assert not state.exists(), "the revocation left the directory it made"
    (directory / slot.REVOKED).unlink()

    state.mkdir(mode=0o700)
    assert command.main(base) == 0
    assert state.is_dir(), "a directory revoke did not make was removed"


def test_the_slot_vocabulary_is_one_list_everywhere() -> None:
    """The key pattern: `slot.SLOT_KEY`, the host schema and the control set's
    CHECK. The states: `slot.STATES` and `control_slots.state`'s CHECK."""
    schema = json.loads((REPO_ROOT / "schemas" / "host.schema.json").read_text("utf-8"))
    text = json.dumps(schema)
    assert json.dumps(slot.SLOT_KEY.pattern)[1:-1] in text
    sql = (
        REPO_ROOT / "projects/control/migrations/templates/0004-control-operations.sql"
    ).read_text("utf-8")
    assert f"key ~ '{slot.SLOT_KEY.pattern}'" in sql
    check = re.search(r"state\s+text NOT NULL CHECK \(state IN \((.*?)\)\)", sql, re.DOTALL)
    assert check is not None
    assert tuple(re.findall(r"'([a-z]+)'", check.group(1))) == slot.STATES

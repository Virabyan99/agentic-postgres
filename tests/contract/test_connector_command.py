"""`bin/connector.sh`, driven as an operator drives it.

`CONN-CMD-001` (ADR 0236, ADR 0237, D1804). **The product's own command**
(D1114): the three HTTP verbs are run through `bin/connector.sh` against a
loopback recorder that keeps what it was SENT -- the method, the target, the
Authorization header and the body -- so what is asserted is the request the
command made, not one this module would have built.

`key` is root's and this suite is not root, so its two write proofs call the
command's own `main` in-process with `os.geteuid` answering 0 and the secret
root moved into a temporary directory -- the one module attribute the command
reads it from, which nothing on the command line can move. The non-root
refusal is driven through the real `bin/connector.sh`.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.contract.test_workflow_command import Recorder, _is_a_docstring

from agentic_postgres import REPO_ROOT, connector_keys, naming

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

COMMAND = REPO_ROOT / "bin" / "connector.sh"
SOURCE = REPO_ROOT / "bin" / "connector.py"
EXAMPLE = REPO_ROOT / "project.example.yaml"

API_TOKEN = "a-human-access-token-7a1f"  # noqa: S105
AGENT_ID = "0b1c2d3e-4f50-4617-8293-a4b5c6d7e8f9"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(COMMAND), *arguments], capture_output=True, text=True, check=False, timeout=120
    )


def command_module() -> Any:
    """`bin/connector.py`, loaded by path -- it is a command, not a package."""
    specification = importlib.util.spec_from_file_location("apg_connector_command", SOURCE)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture
def recorder(tmp_path: Path) -> Any:
    started = Recorder()
    document = tmp_path / "outputs.json"
    document.write_text(
        json.dumps({"routes": {"app": {"url": started.url, "status": "ready"}}}), encoding="utf-8"
    )
    started.outputs = str(document)
    yield started
    started.stop()


# ---------------------------------------------------------------------------
# The three HTTP verbs
# ---------------------------------------------------------------------------


def test_the_three_http_verbs_call_the_enumerated_routes_and_nothing_else(
    recorder: Any, monkeypatch: Any
) -> None:
    """**The closed table**: three verbs, the three admin routes, and no other
    path-shaped string anywhere in the module -- the inbound route a SENDER
    uses among the absent ones. Each verb makes exactly one request, `enable`
    carries `agent_id` and nothing else, and `disable` carries no body."""
    module = command_module()
    assert module.ROUTES == {
        "status": ("GET", "/admin/connectors"),
        "enable": ("POST", "/admin/connectors/{name}/enable"),
        "disable": ("POST", "/admin/connectors/{name}/disable"),
    }
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    declared = {path for _, path in module.ROUTES.values()}
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("/")
        and len(node.value) > 1
        and " " not in node.value
        and not _is_a_docstring(tree, node)
    }
    assert literals <= declared, f"the module names {sorted(literals - declared)}"

    monkeypatch.setenv("APG_API_TOKEN", API_TOKEN)
    out = ("--project-outputs", recorder.outputs)
    for arguments in (
        ("status", "--dead-limit", "7", *out),
        ("enable", "--name", "notes-inbox", "--confirm", "notes-inbox", "--agent", AGENT_ID, *out),
        ("enable", "--name", "note-embedded", "--confirm", "note-embedded", *out),
        ("disable", "--name", "notes-digest", "--confirm", "notes-digest", *out),
    ):
        result = run(*arguments)
        assert result.returncode == 0, (arguments, result.stdout, result.stderr)

    assert [(r["method"], r["target"], r["body"]) for r in recorder.received] == [
        ("GET", "/admin/connectors?dead_limit=7", None),
        ("POST", "/admin/connectors/notes-inbox/enable", {"agent_id": AGENT_ID}),
        ("POST", "/admin/connectors/note-embedded/enable", {"agent_id": None}),
        ("POST", "/admin/connectors/notes-digest/disable", None),
    ]

    recorder.received.clear()
    for arguments in (
        ("status", "--dead-limit", "0", *out),
        ("status", "--dead-limit", "21", *out),
        ("enable", "--name", "../../auth", "--confirm", "../../auth", *out),
        ("enable", "--name", "a", "--confirm", "a", "--agent", "not-a-uuid", *out),
        ("disable", "--name", "a", "--confirm", "a", "--agent", AGENT_ID, *out),
    ):
        result = run(*arguments)
        assert result.returncode == 2, (arguments, result.stderr)
    assert recorder.received == [], "a refused input was sent"


def test_the_http_verbs_take_the_api_token(recorder: Any, monkeypatch: Any) -> None:
    """`APG_API_TOKEN`, `bin/api.sh`'s variable, and never an argument: with it
    empty each verb exits 3 before any request, and the parser has no flag
    that would take one. Control: with it set, each sends exactly it."""
    module = command_module()
    assert module.TOKEN_VARIABLE == "APG_API_TOKEN"  # noqa: S105
    flags = {a.option_strings[0] for a in module.build_parser()._actions if a.option_strings}
    assert not {flag for flag in flags if "token" in flag or "secret" in flag or "key" in flag}

    out = ("--project-outputs", recorder.outputs)
    verbs = (
        ("status", *out),
        ("enable", "--name", "a", "--confirm", "a", *out),
        ("disable", "--name", "a", "--confirm", "a", *out),
    )
    monkeypatch.delenv("APG_API_TOKEN", raising=False)
    monkeypatch.setenv("APG_AGENT_TOKEN", "an-agent-token")
    for arguments in verbs:
        result = run(*arguments)
        assert result.returncode == 3, (arguments, result.stderr)
        assert "APG_API_TOKEN is empty" in result.stderr
    assert recorder.received == []

    monkeypatch.setenv("APG_API_TOKEN", API_TOKEN)
    for arguments in verbs:
        assert run(*arguments).returncode == 0
    assert [r["authorization"] for r in recorder.received] == [f"Bearer {API_TOKEN}"] * 3


def test_enable_and_disable_refuse_without_a_matching_confirm(
    recorder: Any, monkeypatch: Any
) -> None:
    """Binding an agent starts runs as it, and disabling holds deliveries, so
    the name is typed twice -- exit 2 before the token is even looked for.
    Control: the same command with the name repeated is sent."""
    monkeypatch.delenv("APG_API_TOKEN", raising=False)
    out = ("--project-outputs", recorder.outputs)
    for verb in ("enable", "disable"):
        for confirm in ((), ("--confirm", "notes-inbo"), ("--confirm", "")):
            result = run(verb, "--name", "notes-inbox", *confirm, *out)
            assert result.returncode == 2, (verb, confirm, result.stderr)
            assert "--confirm must repeat the connector's name" in result.stderr
    assert recorder.received == []

    monkeypatch.setenv("APG_API_TOKEN", API_TOKEN)
    for verb in ("enable", "disable"):
        result = run(verb, "--name", "notes-inbox", "--confirm", "notes-inbox", *out)
        assert result.returncode == 0, result.stderr
    assert len(recorder.received) == 2, "the control failed: a matching confirm was not sent"


def test_status_prints_the_document_whole_and_a_refusal_as_its_word(
    recorder: Any, monkeypatch: Any
) -> None:
    """No summary (ADR 0195): the document, `indent=2`, and nothing else on
    stdout; a refusal is the service's own word on stderr, exit 5, empty
    stdout."""
    monkeypatch.setenv("APG_API_TOKEN", API_TOKEN)
    document = {"connectors": [{"name": "x", "deliveries": {"dead": 2}}], "dead_limit": 20}
    recorder.answer = (200, document)
    result = run("status", "--project-outputs", recorder.outputs)
    assert result.returncode == 0, result.stderr
    assert result.stdout == json.dumps(document, indent=2, sort_keys=True) + "\n"

    recorder.answer = (409, {"error": "agent_scopes_differ"})
    refused = run("enable", "--name", "x", "--confirm", "x", "--agent", AGENT_ID,
                  "--project-outputs", recorder.outputs)  # fmt: skip
    assert refused.returncode == 5
    assert "agent_scopes_differ" in refused.stderr
    assert refused.stdout == ""


# ---------------------------------------------------------------------------
# key (root)
# ---------------------------------------------------------------------------

MASTER_ONE = hashlib.sha256(b"generation-one").hexdigest()
MASTER_TWO = hashlib.sha256(b"generation-two").hexdigest()


def _manifest(tmp_path: Path, *, enabled: bool = True) -> Path:
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    document = copy.deepcopy(document)
    if enabled:
        document["connectors"] = {"enabled": True, "endpoints": {}}
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _secret_root(tmp_path: Path, active: str | None) -> Path:
    """Two generations, each with its own master; the pointer names `active`."""
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    key = naming.project_key(document["project"]["slug"], document["project"]["environment"])
    root = tmp_path / "secrets"
    for generation, master in (("genone", MASTER_ONE), ("gentwo", MASTER_TWO)):
        directory = root / key / "generations" / generation / "auth"
        directory.mkdir(parents=True)
        (directory / "connector_signing_key").write_text(master, encoding="ascii")
    if active is not None:
        (root / key / "active-secret-generation.json").write_text(
            json.dumps({"generation_id": active}), encoding="utf-8"
        )
    return root


def _key(module: Any, monkeypatch: Any, root: Path, *arguments: str, euid: int = 0) -> int:
    monkeypatch.setattr(module.os, "geteuid", lambda: euid)
    monkeypatch.setattr(module, "SECRET_ROOT", root)
    try:
        code = module.main(["key", *arguments])
    except SystemExit as exit_:
        code = int(exit_.code or 0)
    return code


def test_key_writes_a_new_private_file_and_never_stdout(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """A NEW file, mode 0600, holding exactly the derived key; the key and the
    master appear on neither stream; an existing path -- a file or a symlink --
    is refused and left as it was. Not root is exit 4 through the real
    command, with nothing written."""
    module = command_module()
    manifest = _manifest(tmp_path)
    root = _secret_root(tmp_path, "genone")
    output = tmp_path / "notes-inbox.key"

    code = _key(
        module, monkeypatch, root,
        "--project", str(manifest), "--name", "notes-inbox", "--output", str(output),
    )  # fmt: skip
    captured = capsys.readouterr()
    assert code == 0, captured.err
    expected = connector_keys.derive(MASTER_ONE, "notes-inbox")
    assert output.read_text(encoding="ascii") == expected + "\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    for secret in (expected, MASTER_ONE):
        assert secret not in captured.out + captured.err

    code = _key(
        module, monkeypatch, root,
        "--project", str(manifest), "--name", "notes-inbox", "--output", str(output),
    )  # fmt: skip
    assert code == 2
    assert "already exists" in capsys.readouterr().err
    assert output.read_text(encoding="ascii") == expected + "\n"

    victim = tmp_path / "victim"
    victim.write_text("unchanged", encoding="utf-8")
    link = tmp_path / "link.key"
    os.symlink(victim, link)
    code = _key(
        module, monkeypatch, root,
        "--project", str(manifest), "--name", "notes-inbox", "--output", str(link),
    )  # fmt: skip
    assert code == 2
    assert victim.read_text(encoding="utf-8") == "unchanged"

    fresh = tmp_path / "not-root.key"
    result = run("key", "--project", str(manifest), "--name", "notes-inbox",
                 "--output", str(fresh))  # fmt: skip
    assert result.returncode == 4, result.stdout + result.stderr
    assert "must run as root" in result.stderr
    assert not fresh.exists()


def test_key_derives_the_generation_path(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """The master is read from the generation `active-secret-generation.json`
    names -- move the pointer and the key moves with it -- and each thing a
    key could be derived for nothing is refused before root is asked for."""
    module = command_module()
    manifest = _manifest(tmp_path)

    def derive_into(active: str | None, name: str = "notes-inbox") -> tuple[int, Path]:
        base = tmp_path / f"case-{active}-{name}"
        base.mkdir()
        output = base / "out.key"
        code = _key(
            module, monkeypatch, _secret_root(base, active),
            "--project", str(manifest), "--name", name, "--output", str(output),
        )  # fmt: skip
        return code, output

    code, output = derive_into("gentwo")
    assert code == 0
    assert output.read_text(encoding="ascii").strip() == connector_keys.derive(
        MASTER_TWO, "notes-inbox"
    )
    code, output = derive_into("genone")
    assert code == 0
    assert output.read_text(encoding="ascii").strip() == connector_keys.derive(
        MASTER_ONE, "notes-inbox"
    )

    code, output = derive_into(None)
    assert code == 4 and not output.exists()
    code, output = derive_into("gentwo", name="not-a-connector")
    assert code == 5 and not output.exists()

    capsys.readouterr()
    disabled = tmp_path / "disabled"
    disabled.mkdir()
    code = _key(
        module, monkeypatch, _secret_root(disabled, "genone"),
        "--project", str(_manifest(disabled, enabled=False)), "--name", "notes-inbox",
        "--output", str(disabled / "out.key"),
    )  # fmt: skip
    assert code == 5
    assert "does not enable the connectors facility" in capsys.readouterr().err
    assert not (disabled / "out.key").exists()


# ---------------------------------------------------------------------------
# The command's own shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verb", ["init", "validate", "status", "enable", "disable", "key"])
def test_every_verbs_help_needs_no_project(verb: str) -> None:
    """A verb's help is a READ (D1395, D1402, D1405): no project, no token, no
    host and no root -- `key`'s included."""
    result = run(verb, "--help")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip()) > 40
    assert verb in result.stdout.lower()


def test_the_command_holds_no_sql() -> None:
    """A command that could run SQL would be a command a human runs SQL
    through. Over string literals, docstrings excepted."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    keywords = re.compile(r"\b(select|insert|update|delete|app_private)\b", re.IGNORECASE)
    offenders = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and keywords.search(node.value)
        and not _is_a_docstring(tree, node)
    ]
    assert not offenders, offenders
    source = SOURCE.read_text(encoding="utf-8")
    assert "https://" not in source and "http://" not in source

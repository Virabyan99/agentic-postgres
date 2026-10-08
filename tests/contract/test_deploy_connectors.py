"""Step 6e: the deploy installs a project's connectors, or says which reason it did not.

`CONN-DEF-001`'s deploy half (ADR 0236). The shape of Session 33's D1705 proofs
of step 6d (`test_workflow_install.py`): `bin/deploy-project.py` imported by
path, `container_exec.run` replaced by a recorder, the example project's REAL
lock and definitions. So what is proved is the helper step 6e calls -- which
reasons it prints, when it refuses at exit 5, and what argv reaches psql -- and
where 6e sits among the steps is read out of the deploy's AST.

And `connector_install`, beside `workflow_install`: one constant statement,
every value a psql variable, the SQL on stdin, and as many values as the
migration's function declares.

Nothing here reaches a database. Whether `connector_install` behaves is
`test_connectivity_substrate.py`'s question, under a real cluster.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, connector_install
from agentic_postgres import connector_definition as cd
from agentic_postgres import workflow_definition as wd

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

DEPLOY = REPO_ROOT / "bin" / "deploy-project.py"
MODULE = REPO_ROOT / "src" / "agentic_postgres" / "connector_install.py"
MIGRATION = REPO_ROOT / "migrations" / "templates" / "0036-connectivity.sql"
EXAMPLE_SET = REPO_ROOT / "projects" / "example"
ENDPOINT = "http://apg-s34-sink:8080/ok"


@pytest.fixture
def deploy() -> Any:
    """`bin/deploy-project.py` imported by path -- `bin/` is not a package."""
    spec = importlib.util.spec_from_file_location("_apg_deploy_connectors_under_test", DEPLOY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record_every_container(deploy: Any, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    reached: list[Any] = []

    def record(*arguments: Any, **options: Any) -> Any:
        reached.append((arguments, options))
        return subprocess.CompletedProcess(list(arguments), 0, "installed\n", "")

    monkeypatch.setattr(deploy.container_exec, "run", record)
    return reached


def _release_with_the_example_set(tmp_path: Path) -> Path:
    """A release directory holding a copy of the example set, to break in place."""
    release = tmp_path / "release"
    shutil.copytree(EXAMPLE_SET, release / "projects" / "example")
    return release


def _arguments(release: Path, tmp_path: Path) -> dict[str, Any]:
    lock_path = tmp_path / "lock.json"
    lock_path.write_text("{}", encoding="utf-8")
    return {
        "release": release,
        "manifest_path": tmp_path / "project.yaml",
        "lock_path": lock_path,
        "database": {"container": "apg-test-postgres-1", "name": "test"},
    }


def _manifest(enabled: bool | None, endpoints: dict[str, str] | None = None) -> dict[str, Any]:
    document: dict[str, Any] = {"migrations": {"set": "projects/example"}}
    if enabled is not None:
        document["connectors"] = {"enabled": enabled, "endpoints": endpoints or {}}
    return document


@pytest.fixture
def real_lock(deploy: Any, monkeypatch: pytest.MonkeyPatch) -> wd.LockView:
    view = wd.lock_view_for_project(REPO_ROOT / "project.example.yaml")
    monkeypatch.setattr(deploy.workflow_definition.LockView, "from_json", lambda raw: view)
    return view


# ---------------------------------------------------------------------------
# The reasons, and the refusal
# ---------------------------------------------------------------------------


def test_nothing_is_installed_without_the_facility_saying_which_reason(
    deploy: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Three reasons, three sentences, and none of them reaches a container or
    reads the lock (the lock path here holds no lock, so a read would raise).

    **The facility is read before the directory**: a project that has not
    enabled connectors installs none of the files its set ships, which is
    beta's state until the trip turns it on as its own operation (D1807) --
    and alpha's, which declares no set at all. The control, in the same test:
    the facility on installs all four."""
    reached = _record_every_container(deploy, monkeypatch)
    release = _release_with_the_example_set(tmp_path)
    arguments = _arguments(release, tmp_path)
    arguments["lock_path"] = tmp_path / "no-such-lock.json"

    monkeypatch.setattr(deploy, "load_project_manifest", lambda path: {})
    deploy.install_connectors(**arguments)
    no_set = capsys.readouterr().out

    for enabled in (None, False):
        monkeypatch.setattr(deploy, "load_project_manifest", lambda path, e=enabled: _manifest(e))
        deploy.install_connectors(**arguments)
        assert (
            "no connectors (the manifest's connectors.enabled is false)" in capsys.readouterr().out
        ), enabled

    (release / "projects" / "bare").mkdir()
    monkeypatch.setattr(
        deploy,
        "load_project_manifest",
        lambda path: {"migrations": {"set": "projects/bare"}, "connectors": {"enabled": True}},
    )
    deploy.install_connectors(**arguments)
    no_directory = capsys.readouterr().out

    assert "no connectors (the project declares no migration set)" in no_set, no_set
    assert "no connectors (the project declares none)" in no_directory, no_directory
    assert reached == []

    # The control: the facility on, the real lock, the four files installed.
    view = wd.lock_view_for_project(REPO_ROOT / "project.example.yaml")
    monkeypatch.setattr(deploy.workflow_definition.LockView, "from_json", lambda raw: view)
    monkeypatch.setattr(deploy, "load_project_manifest", lambda path: _manifest(True))
    deploy.install_connectors(**_arguments(release, tmp_path))
    installed = capsys.readouterr().out
    assert len(reached) == 4, installed
    for name in ("note-embedded", "notes-deadletter", "notes-digest", "notes-inbox"):
        assert f" {name} v1  " in installed, installed


def test_an_uninstallable_connector_refuses_at_exit_five(
    deploy: Any,
    monkeypatch: pytest.MonkeyPatch,
    real_lock: wd.LockView,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A connector that does not compile refuses the deploy at exit 5 naming
    the file, before ANY connector reaches the cluster; a psql failure refuses
    at exit 5 naming the file and never the endpoint."""
    reached = _record_every_container(deploy, monkeypatch)
    release = _release_with_the_example_set(tmp_path)
    inbox = release / "projects" / "example" / "connectors" / "notes-inbox.yaml"
    text = inbox.read_text(encoding="utf-8")
    assert text.count("workflow: notes-inbox@1") == 1
    inbox.write_text(text.replace("workflow: notes-inbox@1", "workflow: notes-inbox@9"))
    monkeypatch.setattr(deploy, "load_project_manifest", lambda path: _manifest(True))

    with pytest.raises(SystemExit) as raised:
        deploy.install_connectors(**_arguments(release, tmp_path))
    assert raised.value.code == deploy.EXIT_VALIDATION == 5
    refused = capsys.readouterr().err
    assert "notes-inbox.yaml does not compile" in refused, refused
    assert reached == [], "a connector reached the cluster before a sibling was compiled"

    inbox.write_text(text)

    def failing(*arguments: Any, **options: Any) -> Any:
        return subprocess.CompletedProcess(
            list(arguments),
            3,
            "",
            "ERROR:  AP409: this connector version is installed with other content\n",
        )

    monkeypatch.setattr(deploy.container_exec, "run", failing)
    monkeypatch.setattr(
        deploy,
        "load_project_manifest",
        lambda path: _manifest(True, {"note-embedded": ENDPOINT}),
    )
    with pytest.raises(SystemExit) as raised:
        deploy.install_connectors(**_arguments(release, tmp_path))
    assert raised.value.code == 5
    refused = capsys.readouterr()
    assert "note-embedded.yaml was not installed" in refused.err
    assert "AP409" in refused.err
    assert ENDPOINT not in refused.err + refused.out


def test_a_missing_endpoint_is_reported_and_never_printed(
    deploy: Any,
    monkeypatch: pytest.MonkeyPatch,
    real_lock: wd.LockView,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An outbound connector with no endpoint installs WITHOUT one and the line
    says `enable` will refuse it (a report, ADR 0195); an endpoint naming no
    outbound connector is reported and sent nowhere; the endpoint that IS used
    reaches psql as a variable and appears in no printed line (D1786)."""
    reached = _record_every_container(deploy, monkeypatch)
    release = _release_with_the_example_set(tmp_path)
    monkeypatch.setattr(
        deploy,
        "load_project_manifest",
        lambda path: _manifest(
            True, {"note-embedded": ENDPOINT, "notes-inbox": ENDPOINT, "no-such": ENDPOINT}
        ),
    )
    deploy.install_connectors(**_arguments(release, tmp_path))
    printed = capsys.readouterr()
    assert ENDPOINT not in printed.out + printed.err

    lines = {line.split()[1]: line for line in printed.out.splitlines() if " v1  " in line}
    assert "no endpoint" not in lines["note-embedded"]
    assert "no endpoint in the manifest; `enable` will refuse it" in lines["notes-deadletter"]
    assert "no endpoint" not in lines["notes-inbox"]
    assert "endpoint for no-such: names no outbound connector" in printed.out
    assert "endpoint for notes-inbox: names no outbound connector" in printed.out

    sent = {}
    for arguments, options in reached:
        argv = list(arguments)
        name = next(value for value in argv if value.startswith("name="))[5:]
        sent[name] = next(value for value in argv if value.startswith("endpoint="))[9:]
        assert options["input"] == connector_install.INSTALL_SQL
        assert argv[:6] == ["apg-test-postgres-1", "psql", "-U", "postgres", "-d", "test"]
    assert sent == {
        "note-embedded": ENDPOINT,
        "notes-deadletter": "",
        "notes-digest": "",
        "notes-inbox": "",
    }


# ---------------------------------------------------------------------------
# Where 6e sits
# ---------------------------------------------------------------------------


def _step_labels() -> list[str]:
    tree = ast.parse(DEPLOY.read_text(encoding="utf-8"))
    labels: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "step"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            labels.append((node.lineno, node.args[0].value))
    return [label for _, label in sorted(labels)]


def test_step_6e_installs_connectors_after_the_definitions_and_before_the_services() -> None:
    """After 6d, because an inbound or scheduled connector names a definition
    6d installs; before 6b, so the route never answers `no_such_connector`
    about a connector this deploy installs. Gated at CONNECTOR_SESSION."""
    labels = _step_labels()
    positions = {
        name: index
        for index, label in enumerate(labels)
        for name in ("6.", "6b.", "6d.", "6e.")
        if label.startswith(name)
    }
    assert set(positions) == {"6.", "6b.", "6d.", "6e."}, labels
    assert positions["6."] < positions["6d."] < positions["6e."] < positions["6b."], positions

    source = DEPLOY.read_text(encoding="utf-8")
    assert "CONNECTOR_SESSION = 34\n" in source
    assert "if arguments.through_session >= CONNECTOR_SESSION:" in source
    call = source[source.index("def install_connectors") :]
    call = call[: call.index("\ndef ", 1)]
    assert "container_exec.run(" in call and '"postgres",' in call
    assert "input=statement.stdin" in call


# ---------------------------------------------------------------------------
# The statement
# ---------------------------------------------------------------------------


def test_the_install_statement_is_a_constant_of_psql_variables() -> None:
    """No f-string, `%` or `.format(` builds SQL in the module, the statement
    is the constant, and it names as many variables as `connector_install`
    declares parameters -- read out of migration 0036."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    constant = next(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "INSTALL_SQL" for target in node.targets
        )
    )
    assert isinstance(constant, ast.Constant), "INSTALL_SQL is built rather than written"
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            raise AssertionError("a % formats something in connector_install")
        if isinstance(node, ast.Attribute) and node.attr == "format":
            raise AssertionError("a .format( in connector_install")

    migration = MIGRATION.read_text(encoding="utf-8")
    declaration = migration[migration.index("CREATE FUNCTION app_private.connector_install(") :]
    declaration = declaration[: declaration.index(") RETURNS")]
    declared = re.findall(r"\bp_[a-z0-9_]+", declaration)
    variables = re.findall(r":'([a-z_]+)'", connector_install.INSTALL_SQL)
    assert len(declared) == len(variables) == 13, (declared, variables)
    assert [name[2:] for name in declared] == [
        {"source": "source_sha256", "scopes": "required_scopes"}.get(v, v) for v in variables
    ]


def test_every_value_travels_as_a_variable_and_the_endpoint_only_outbound() -> None:
    lock = wd.lock_view_for_project(REPO_ROOT / "project.example.yaml")
    definitions = cd.definitions_for(EXAMPLE_SET, lock)
    for path in cd.connectors_of(EXAMPLE_SET):
        compiled = cd.compile_file(path, lock, definitions)
        endpoint = ENDPOINT if compiled.kind == "outbound" else None
        (statement,) = connector_install.statements(compiled, endpoint)
        assert statement.stdin == connector_install.INSTALL_SQL
        assert statement.argv[-2:] == ("-f", "-")
        assert "-c" not in statement.argv
        names = [
            value.split("=", 1)[0]
            for flag, value in zip(statement.argv, statement.argv[1:], strict=False)
            if flag == "-v" and value != "ON_ERROR_STOP=1"
        ]
        assert names == re.findall(r":'([a-z_]+)'", connector_install.INSTALL_SQL)
        if compiled.kind != "outbound":
            with pytest.raises(ValueError, match="only an outbound connector sends"):
                connector_install.statements(compiled, ENDPOINT)


# ---------------------------------------------------------------------------
# `apg dev up` (D1808)
# ---------------------------------------------------------------------------


def test_dev_up_installs_connectors_only_with_the_facility(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`bin/dev.py`'s `install_connectors` over a recording `docker`: the
    example manifest (schema 7, no facility) installs nothing and says why --
    the sentence the cluster proof reads off `up`'s stdout -- and a throwaway
    schema-7 manifest with the facility on installs the four, the endpoint to
    the outbound connector the manifest names and to nothing else."""
    import yaml

    spec = importlib.util.spec_from_file_location(
        "_apg_dev_under_test", REPO_ROOT / "bin" / "dev.py"
    )
    assert spec is not None and spec.loader is not None
    dev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dev)

    reached: list[tuple[str, ...]] = []

    def record(*arguments: str, stdin: str | None = None, timeout: int = 300) -> Any:
        reached.append(arguments)
        assert stdin == connector_install.INSTALL_SQL
        return subprocess.CompletedProcess(list(arguments), 0, "installed\n", "")

    monkeypatch.setattr(dev, "docker", record)
    capabilities = wd.DEFAULT_CAPABILITIES
    example = REPO_ROOT / "project.example.yaml"

    said = dev.install_connectors(example, capabilities, "apg-dev-probe", "probe")
    assert said == "not enabled (the manifest's connectors.enabled is false)"
    assert reached == []

    manifest = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 10  # 10 since Session 38 (ADR 0258)
    manifest["connectors"] = {"enabled": True, "endpoints": {"note-embedded": ENDPOINT}}
    enabled = tmp_path / "project.enabled.yaml"
    enabled.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    said = dev.install_connectors(enabled, capabilities, "apg-dev-probe", "probe")
    assert said == "4 connector(s) installed, disabled"
    sent = {
        next(value for value in argv if value.startswith("name="))[5:]: next(
            value for value in argv if value.startswith("endpoint=")
        )[9:]
        for argv in reached
    }
    assert sent == {
        "note-embedded": ENDPOINT,
        "notes-deadletter": "",
        "notes-digest": "",
        "notes-inbox": "",
    }

"""`pg_stat_statements` loaded on every project and every branch (Session 42,
ADR 0278, D2566, D2597).

Three offline readings -- the database's command, a branch's command, the
bootstrap's statements -- and one on a real cluster: the locked image started
with every literal `-c` setting `compose.yaml`'s `postgres` command carries
(so the preload is read out of the release's own file), the bootstrap plane's
statements applied as the deploy applies them, and the bootstrap's OWN
`check_violations` asked -- the reader that runs on every deploy, not a second
one written here (D1114). The customer roles are then refused the view AND the
function under it (rig 42b: the function was open after the views alone were
revoked); `postgres` reads it (the control).

The container is removed WITH its anonymous volume (`docker rm -fv`, D2098).
"""

from __future__ import annotations

import importlib.util
import secrets
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, bootstrap_statements, branch_plan, config, naming, rendering

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"
SETTINGS = bootstrap_statements.PG_STAT_STATEMENTS_SETTINGS


def _settings(command: list[str]) -> list[str]:
    """The `-c` values of a `postgres` command, in order."""
    assert command[0] == "postgres", command
    return [command[i + 1] for i, part in enumerate(command) if part == "-c"]


def _release_command() -> list[str]:
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    return [str(part) for part in compose["services"]["postgres"]["command"]]


def test_the_database_command_loads_the_extension() -> None:
    """`compose.yaml`'s `postgres` command carries the five settings, in
    order, exactly as `bootstrap_statements.PG_STAT_STATEMENTS_SETTINGS` holds
    them -- `track_utility=off` among them, without which an `ALTER ROLE ...
    PASSWORD` is kept as typed."""
    settings = _settings(_release_command())
    found = [s for s in settings if s.split("=")[0].startswith(("shared_preload", "pg_stat"))]
    assert found == list(SETTINGS), found
    assert "pg_stat_statements.track_utility=off" in SETTINGS
    assert "pg_stat_statements.track=top" in SETTINGS


def test_a_branch_loads_it_too() -> None:
    """A branch's catalogue holds its parent's extension, so its own
    `postgres` preloads it: `persistent_command()` ends with the same five
    (and `infra/branch/compose.yaml` is held equal to it by
    `test_branch_runtime`)."""
    settings = _settings(list(branch_plan.persistent_command()))
    assert settings[-len(SETTINGS) :] == list(SETTINGS), settings
    branch = yaml.safe_load((REPO_ROOT / "infra/branch/compose.yaml").read_text("utf-8"))
    (service,) = [s for s in branch["services"].values() if "command" in s]
    assert _settings([str(p) for p in service["command"]])[-len(SETTINGS) :] == list(SETTINGS)


def test_the_bootstrap_creates_and_revokes_it() -> None:
    """The bootstrap plane creates it in `extensions` right after `vector`
    and revokes every one of its five objects from `PUBLIC`: the two views
    AND the three functions (D2597)."""
    document = _document_in_memory()
    statements = bootstrap_statements.build_statements(
        document, "8f14e45f-ceea-467a-9c1e-1a1f9c1a2b3c"
    )
    vector = statements.index("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;")
    assert statements[vector + 1] == (
        "CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA extensions;"
    )
    assert statements[vector + 2] == (
        "REVOKE ALL ON extensions.pg_stat_statements, extensions.pg_stat_statements_info "
        "FROM PUBLIC;"
    )
    assert statements[vector + 3] == (
        "REVOKE ALL ON FUNCTION extensions.pg_stat_statements(boolean), "
        "extensions.pg_stat_statements_info(), "
        "extensions.pg_stat_statements_reset(oid, oid, bigint, boolean) FROM PUBLIC;"
    )
    assert not any("GRANT" in s and "pg_stat_statements" in s for s in statements)


# ---------------------------------------------------------------------------
# On a cluster
# ---------------------------------------------------------------------------


def _bootstrap() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_bootstrap_pgss", REPO_ROOT / "bin" / "postgres-bootstrap.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def docker(*arguments: str, stdin: str | None = None, timeout: int = 300) -> Any:
    return subprocess.run(
        ["docker", *arguments], input=stdin, capture_output=True, text=True, check=False,
        timeout=timeout,
    )  # fmt: skip


def _document_in_memory() -> dict[str, Any]:
    """The example project, public endpoints ON (so the customer roles exist),
    built in memory (test_customer_roles_on_a_cluster.py's shape)."""
    raw = yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))
    raw["database"]["public_endpoints"] = {"enabled": True}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "project.yaml"
        path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        manifest = config.load_project_manifest(path)
    identity = naming.derive(
        slug=manifest["project"]["slug"],
        environment=manifest["project"]["environment"],
        domain=manifest["project"]["domain"],
        api_base_path=manifest["api"]["public_base_path"],
        mcp_base_path=manifest["mcp"]["public_base_path"],
        database_name=manifest["database"]["name"],
    )
    return rendering.build_outputs(
        manifest, config.load_capabilities_manifest(CAPABILITIES), identity, {}
    )


@pytest.fixture(scope="module")
def cluster() -> Iterator[tuple[str, dict[str, Any], Any]]:
    bootstrap = _bootstrap()
    document = _document_in_memory()
    database = document["database"]["name"]
    lock = {
        name: value
        for name, _, value in (
            line.partition("=")
            for line in (REPO_ROOT / "versions.env").read_text("utf-8").splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    # Every literal `-c` the release's command carries: the preload among them.
    literal = [s for s in _settings(_release_command()) if "${" not in s]
    arguments = [part for setting in literal for part in ("-c", setting)]
    name = f"apg-pgss-{secrets.token_hex(4)}"
    started = docker(
        "run", "-d", "--name", name, "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
        "-e", f"POSTGRES_DB={database}", lock["POSTGRES_IMAGE"], "postgres", *arguments,
    )  # fmt: skip
    if started.returncode != 0:
        raise RuntimeError(f"cannot start the locked cluster: {started.stderr.strip()[:200]}")
    try:
        rounds = 0
        for _ in range(90):
            probe = docker("exec", name, "pg_isready", "-U", "postgres", "-d", database, timeout=30)
            rounds = rounds + 1 if probe.returncode == 0 else 0
            if rounds >= 2:
                break
            time.sleep(1)
        assert rounds >= 2, "the cluster never became ready"
        statements = bootstrap.build_statements(document, "8f14e45f-ceea-467a-9c1e-1a1f9c1a2b3c")
        bootstrap.psql(name, database, "\n".join(statements))
        yield name, document, bootstrap
    finally:
        docker("rm", "-fv", name, timeout=120)


def _as(name: str, database: str, sql: str, role: str | None = None) -> Any:
    prefix = f'SET ROLE "{role}";\n' if role else ""
    return docker(
        "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", database, stdin=prefix + sql,
    )  # fmt: skip


def test_the_bootstrap_check_reads_the_preload_and_the_revocation(
    cluster: tuple[str, dict[str, Any], Any],
) -> None:
    """On the cluster: the bootstrap's own `check_violations` finds nothing
    wrong with `pg_stat_statements` (preloaded, in `extensions`, PUBLIC
    holding none of its objects); each customer role is refused the view AND
    `extensions.pg_stat_statements(true)`; `postgres` reads it (the control)."""
    name, document, bootstrap = cluster
    database = document["database"]["name"]
    violations = [
        v for v in bootstrap.check_violations(name, database, document) if "pg_stat_statements" in v
    ]
    assert violations == [], violations
    for suffix in ("customer_app", "customer_admin"):
        role = document["database"]["roles"][suffix]
        for sql in (
            "SELECT count(*) FROM extensions.pg_stat_statements;",
            "SELECT count(*) FROM extensions.pg_stat_statements(true);",
            "SELECT count(*) FROM extensions.pg_stat_statements_info;",
        ):
            refused = _as(name, database, sql, role)
            assert refused.returncode != 0 and "permission denied" in refused.stderr, (role, sql)
    control = _as(name, database, "SELECT count(*) > 0 FROM extensions.pg_stat_statements;")
    assert control.returncode == 0 and control.stdout.strip() == "t", control.stderr

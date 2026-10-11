"""The customer roles on a real cluster (Session 39, ADR 0269, D2332).

`test_bootstrap_statements` proves what the bootstrap WRITES. This proves what
the catalog then GRANTS: one throwaway cluster from the locked image, the
example project's document with public endpoints on, the bootstrap plane's own
statements (`build_statements`), the release's and the project's migrations as
the superuser, and `activate_customer_roles` -- then the two roles exercised.

Privileges are read by `SET ROLE` from the superuser, which is what a grant
answers to; LOGIN and the passwords are the customer poolers' half
(`test_customer_poolers.py`). The read-back goes through the bootstrap's own
`check_violations`, with a planted grant as its control -- so the reader that
runs on every deploy is the one asserted, not a second one written here.

The container is removed WITH its anonymous volume (`docker rm -fv`, D2098).
"""

# ruff: noqa: S608 -- every interpolated value is a name this module derived.

from __future__ import annotations

import importlib.util
import secrets
import subprocess
import time
from collections.abc import Iterator
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config, migrations, naming, rendering

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"


def _bootstrap() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_bootstrap_customer", REPO_ROOT / "bin" / "postgres-bootstrap.py"
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


def _document(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The example project, public endpoints ON, built in memory (no render on
    disk, CLAUDE.md §1)."""
    raw = yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))
    raw["database"]["public_endpoints"] = {"enabled": True}
    path = tmp_path_factory.mktemp("customer") / "project.yaml"
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


class Cluster:
    def __init__(self, name: str, document: dict[str, Any], bootstrap: Any) -> None:
        self.name = name
        self.document = document
        self.database = document["database"]["name"]
        self.roles = document["database"]["roles"]
        self.bootstrap = bootstrap

    def run(self, sql: str, *, as_role: str | None = None) -> Any:
        prefix = f'SET ROLE "{as_role}";\n' if as_role else ""
        return docker(
            "exec", "-i", self.name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", self.database, "-1", stdin=prefix + sql,
        )  # fmt: skip

    def ok(self, sql: str, *, as_role: str) -> list[str]:
        result = self.run(sql, as_role=as_role)
        assert result.returncode == 0, f"{as_role}: {sql!r} was refused: {result.stderr}"
        return [line for line in result.stdout.splitlines() if line.strip()]

    def refused(self, sql: str, *, as_role: str) -> str:
        result = self.run(sql, as_role=as_role)
        assert result.returncode != 0, f"{as_role}: {sql!r} was ALLOWED: {result.stdout!r}"
        return result.stderr

    def customer_violations(self) -> list[str]:
        return [
            violation
            for violation in self.bootstrap.check_violations(
                self.name, self.database, self.document
            )
            if "customer_" in violation
        ]


@pytest.fixture(scope="module")
def cluster(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Cluster]:
    bootstrap = _bootstrap()
    document = _document(tmp_path_factory)
    database = document["database"]["name"]
    lock = {
        name: value
        for name, _, value in (
            line.partition("=")
            for line in (REPO_ROOT / "versions.env").read_text("utf-8").splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    name = f"apg-customer-roles-{secrets.token_hex(4)}"
    started = docker(
        "run", "-d", "--name", name, "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
        "-e", f"POSTGRES_DB={database}", lock["POSTGRES_IMAGE"],
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
        # The bootstrap plane's own statements, as the deploy issues them.
        statements = bootstrap.build_statements(document, "8f14e45f-ceea-467a-9c1e-1a1f9c1a2b3c")
        bootstrap.psql(name, database, "\n".join(statements))
        for migration_set in migrations.sets_for(document):
            set_manifest = migration_set.load_manifest()
            for entry in set_manifest["migrations"]:
                payload = migrations.render_migration(
                    entry, set_manifest, document, migration_set.root
                )
                up = payload.split("-- migrate:down", 1)[0].replace("-- migrate:up", "", 1)
                applied = docker(
                    "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
                    "-U", "postgres", "-d", database, "-1", stdin=up,
                )  # fmt: skip
                assert applied.returncode == 0, f"{entry['name']}: {applied.stderr}"
        bootstrap.activate_customer_roles(
            name, database, document["database"]["roles"], bootstrap.customer_limits(document)
        )
        yield Cluster(name, document, bootstrap)
    finally:
        docker("rm", "-fv", name, timeout=120)


def test_the_admin_writes_only_in_public(cluster: Cluster) -> None:
    """`customer_admin` creates, alters and drops its own tables in `public` --
    one with a pgvector column, through `extensions` -- and the read-back finds
    nothing wrong with either customer role (LOGIN at the document's limits,
    the grants exactly)."""
    admin = cluster.roles["customer_admin"]
    cluster.ok(
        "CREATE TABLE public.items (id bigserial PRIMARY KEY, label text, "
        "embedding extensions.vector(3));"
        "ALTER TABLE public.items ADD COLUMN note text;"
        "INSERT INTO public.items (label, embedding) VALUES ('a', '[1,2,3]');"
        "CREATE TABLE public.scratch (x int); DROP TABLE public.scratch;",
        as_role=admin,
    )
    assert cluster.customer_violations() == []
    limits = cluster.bootstrap.customer_limits(cluster.document)
    for suffix, limit in limits.items():
        role = cluster.roles[suffix]
        read = (
            "SELECT rolcanlogin::text || ' ' || rolconnlimit FROM pg_roles "
            f"WHERE rolname = '{role}'"
        )
        assert cluster.ok(read, as_role=admin) == [f"true {limit}"], role


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE app.mine (x int);",
        "SELECT count(*) FROM app_private.project_identity;",
        "CREATE TABLE app_private.mine (x int);",
        "CREATE TABLE api.mine (x int);",
        "CREATE SCHEMA mine;",
        "CREATE EXTENSION pg_trgm;",
        "CREATE ROLE intruder;",
        "CREATE TEMPORARY TABLE scratch (x int);",
    ],
)
def test_the_admin_is_refused_everything_else(cluster: Cluster, statement: str) -> None:
    """D2332: nothing on `app`, `api`, `app_private`; no schema, no extension,
    no role, no temporary table. Each refusal is the server's own."""
    error = cluster.refused(statement, as_role=cluster.roles["customer_admin"])
    assert "permission denied" in error or "must have" in error.lower(), error


def test_the_application_role_writes_rows_not_tables(cluster: Cluster) -> None:
    """`customer_app` reads and writes the admin's tables through default
    privileges, uses their sequences, and may create nothing -- not even in
    `public`. Control for the read-back: a planted grant on `app` is reported
    by the bootstrap's own reader, and its removal clears it."""
    admin, app = cluster.roles["customer_admin"], cluster.roles["customer_app"]
    cluster.ok(
        "CREATE TABLE IF NOT EXISTS public.notes (id bigserial PRIMARY KEY, body text);",
        as_role=admin,
    )
    assert cluster.ok(
        "INSERT INTO public.notes (body) VALUES ('hello'); UPDATE public.notes SET body = 'hi';"
        "SELECT count(*) FROM public.notes;",
        as_role=app,
    ) == ["1"]
    assert "permission denied" in cluster.refused("CREATE TABLE public.mine (x int);", as_role=app)
    assert "permission denied" in cluster.refused(
        "SELECT 1 FROM app_private.project_identity;", as_role=app
    )

    cluster.ok(f'GRANT USAGE ON SCHEMA app TO "{app}";', as_role="postgres")
    try:
        assert any("holds USAGE on app" in v for v in cluster.customer_violations())
    finally:
        cluster.ok(f'REVOKE USAGE ON SCHEMA app FROM "{app}";', as_role="postgres")
    assert cluster.customer_violations() == []

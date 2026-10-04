"""The shared control-set cluster (Session 37, ADR 0251).

One throwaway cluster from the locked image with the release's migrations and
then the control project's own set applied, as the superuser, from the
document `project.control.example.yaml` renders to -- the same rendering every
proof of a set uses (`test_auth_endpoints.py`'s shape, generalised here so the
control modules of Runs 3-5 share one fixture instead of each growing its own).

What the fixture supplies is what the bootstrap plane supplies in production
and no migration does: the roles, the database, the `extensions` schema, and
`auth_service`'s LOGIN and password -- the role the control mode connects as.

**The container is removed WITH its anonymous volume** (`docker rm -fv`). The
fixtures that remove with `-f` alone leave the data volume behind, and on the
workstation those had grown to 4,290 volumes and 206 GB by Session 37 (D2090).
"""

from __future__ import annotations

import contextlib
import json
import secrets
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from agentic_postgres import REPO_ROOT, config, migrations, naming, rendering

CONTROL_EXAMPLE = REPO_ROOT / "project.control.example.yaml"
CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"


def _lock() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            name, _, value = line.partition("=")
            values[name] = value
    return values


def docker(
    *arguments: str, stdin: str | None = None, timeout: int = 300
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *arguments],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def control_document() -> dict[str, Any]:
    """The outputs document of the control example, built in memory.

    `rendering.build_outputs` rather than a render on disk: the migration
    renderer needs the roles and the database name, and a render would publish
    under `.generated/` and have to be deleted again (CLAUDE.md §1).
    """
    manifest = config.load_project_manifest(CONTROL_EXAMPLE)
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


@dataclass
class ControlCluster:
    name: str
    database: str
    port: int
    roles: dict[str, str]
    auth_password: str
    document: dict[str, Any] = field(repr=False)

    @property
    def auth_role(self) -> str:
        return self.roles["auth_service"]

    def run(self, sql: str, *, as_role: str | None = None) -> subprocess.CompletedProcess:
        """`sql` through psql in ONE transaction, as the superuser or -- with
        `as_role` -- after `SET ROLE` to that role. Never raises: the caller
        reads the result, because half of these proofs are refusals."""
        prefix = f'SET ROLE "{as_role}";\n' if as_role else ""
        return docker(
            "exec", "-i", self.name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", self.database, "-1",
            stdin=prefix + sql,
        )  # fmt: skip

    def query(self, sql: str, *, as_role: str | None = None) -> list[str]:
        result = self.run(sql, as_role=as_role)
        assert result.returncode == 0, result.stderr
        return [line for line in result.stdout.splitlines() if line.strip()]

    def as_service(self, sql: str) -> list[str]:
        """As the control mode connects: the identity service's role."""
        return self.query(sql, as_role=self.auth_role)

    def refused(self, sql: str, *, as_role: str | None = None) -> str:
        """The error text of a statement that must fail."""
        result = self.run(sql, as_role=as_role if as_role is not None else self.auth_role)
        assert result.returncode != 0, f"expected a refusal, got: {result.stdout!r}"
        return result.stderr


@contextlib.contextmanager
def control_cluster() -> Iterator[ControlCluster]:
    """Start, migrate and yield a control cluster; removed with its volume."""
    lock = _lock()
    name = f"apg-control-set-{secrets.token_hex(4)}"
    started = docker(
        "run", "-d", "--name", name,
        "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
        "-p", "127.0.0.1::5432",
        lock["POSTGRES_IMAGE"],
    )  # fmt: skip
    if started.returncode != 0:
        raise RuntimeError(f"cannot start the locked cluster: {started.stderr.strip()[:200]}")
    try:
        rounds = 0
        for _ in range(90):
            probe = docker("exec", name, "pg_isready", "-U", "postgres", timeout=30)
            rounds = rounds + 1 if probe.returncode == 0 else 0
            if rounds >= 2:
                break
            time.sleep(1)
        if rounds < 2:
            raise RuntimeError("the cluster never became ready")
        mapped = docker("port", name, "5432/tcp").stdout.strip().splitlines()[0]
        port = int(mapped.rsplit(":", 1)[1])

        document = control_document()
        roles = document["database"]["roles"]
        owner = roles["object_owner"]
        database = document["database"]["name"]

        def superuser(sql: str, target: str = "postgres") -> None:
            result = docker(
                "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-d", target,
                stdin=sql,
            )  # fmt: skip
            assert result.returncode == 0, result.stderr

        superuser("\n".join(f'CREATE ROLE "{role}" NOLOGIN;' for role in sorted(roles.values())))
        superuser(f'CREATE DATABASE "{database}" OWNER "{owner}";')
        superuser(
            f'CREATE SCHEMA extensions AUTHORIZATION "{owner}";\n'
            "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;",
            database,
        )
        # ADR 0198: every set this project applies, the release's first.
        for migration_set in migrations.sets_for(document):
            set_manifest = migration_set.load_manifest()
            for entry in set_manifest["migrations"]:
                payload = migrations.render_migration(
                    entry, set_manifest, document, migration_set.root
                )
                up = payload.split("-- migrate:down", 1)[0].replace("-- migrate:up", "", 1)
                applied = docker(
                    "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
                    "-U", "postgres", "-d", database, "-1",
                    stdin=up,
                )  # fmt: skip
                assert applied.returncode == 0, f"{entry['name']}: {applied.stderr}"

        auth_password = secrets.token_hex(24)
        superuser(f"ALTER ROLE \"{roles['auth_service']}\" LOGIN PASSWORD '{auth_password}';")
        yield ControlCluster(
            name=name,
            database=database,
            port=port,
            roles=roles,
            auth_password=auth_password,
            document=json.loads(json.dumps(document)),
        )
    finally:
        docker("rm", "-fv", name, timeout=120)

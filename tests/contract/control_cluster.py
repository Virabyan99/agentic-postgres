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

# ruff: noqa: S608 -- every interpolated value is a uuid or a name this fixture
# made itself, quoted by `_sql_text`; nothing here comes from outside the test.

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


# ---------------------------------------------------------------------------
# The control mode over the cluster (Run 4)
#
# `test_auth_endpoints.py`'s `drive` shape: the same `create_app` the container
# runs, its own `lifespan_context`, reached over ASGI. What this supplies and
# the product does not is what the bootstrap plane supplies in production: a
# signing key, a passfile, a capability lock compiled from the committed
# contract, and accounts made directly in the registry so a proof can start
# from "a person who is an admin with a factor" without walking the product
# path every time. A proof that IS about that path walks it.
# ---------------------------------------------------------------------------

PASSWORD = "a-correct-horse-battery-staple"  # noqa: S105 -- a fixture, hashed and verified

#: The registry administrator's scopes in these proofs: the bootstrap
#: administrator's shape, `admin_users:write` the one that matters (D2051).
ADMIN_SCOPES = ["admin_users:read", "admin_users:write"]


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class ControlDriver:
    """One live control-mode application and the cluster under it."""

    def __init__(self, cluster: ControlCluster, application: Any, loop: Any) -> None:
        self.cluster = cluster
        self.application = application
        self.loop = loop

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        import httpx

        transport = httpx.ASGITransport(app=self.application)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://control.invalid"
        ) as http:
            return await http.request(method, path, **kwargs)

    @staticmethod
    def _arguments(token: str | None, body: Any) -> dict[str, Any]:
        arguments: dict[str, Any] = {}
        if token is not None:
            arguments["headers"] = {"Authorization": f"Bearer {token}"}
        if body is not None:
            arguments["content"] = json.dumps(body)
        return arguments

    def call(self, method: str, path: str, *, token: str | None = None, body: Any = None) -> Any:
        return self.loop.run_until_complete(
            self._request(method, path, **self._arguments(token, body))
        )

    def concurrently(self, *requests: tuple[str, str, str | None, Any]) -> list[Any]:
        """Several requests on several tasks of ONE event loop, at once."""
        import asyncio

        async def run() -> list[Any]:
            return await asyncio.gather(
                *(
                    self._request(method, path, **self._arguments(token, body))
                    for method, path, token, body in requests
                )
            )

        return self.loop.run_until_complete(run())

    # -- accounts made in the registry, as the bootstrap plane would ----------

    def account(self, username: str, *, admin: bool = False) -> str:
        """A registry user and its control display row; returns the user id.

        A plain control account is `api_documentation` holding `meta:read`
        (D2049); `admin=True` is a registry administrator (`project_admin`
        with `admin_users:write`), as `auth-admin.sh bootstrap` makes one.
        """
        from app.hashing import Hasher

        hashed = Hasher().hash(PASSWORD)
        roles = self.cluster.roles
        role = roles["project_admin"] if admin else roles["api_documentation"]
        scopes = ADMIN_SCOPES if admin else ["meta:read"]
        array = "ARRAY[" + ",".join(_sql_text(s) for s in scopes) + "]::text[]"
        user = self.cluster.query(
            "SELECT app_private.auth_create_user("
            f"{_sql_text(username)}, {_sql_text(username)}, {_sql_text(role)}, {array}, "
            f"{_sql_text(hashed)});"
        )[0]
        self.cluster.query(
            "INSERT INTO app.control_accounts (user_id, username, display_name) "
            f"VALUES ('{user}', {_sql_text(username)}, {_sql_text(username)});"
        )
        return user

    def enable_factor(self, user: str) -> bytes:
        """An ENABLED second factor with a known seed; returns the seed."""
        seed = secrets.token_bytes(20)
        self.cluster.query(
            "INSERT INTO app.control_totp (user_id, seed, enabled_at) "
            f"VALUES ('{user}', '\\x{seed.hex()}'::bytea, now());"
        )
        return seed

    def organization(self, owner: str, name: str = "an organisation") -> str:
        org = self.cluster.query(
            "INSERT INTO app.control_organizations (name, created_by) "
            f"VALUES ({_sql_text(name)}, '{owner}') RETURNING id;"
        )[0]
        self.member(org, owner, "owner")
        return org

    def member(self, org: str, user: str, role: str) -> None:
        self.cluster.query(
            "INSERT INTO app.control_memberships (organization_id, user_id, role) "
            f"VALUES ('{org}', '{user}', '{role}');"
        )

    def login(self, username: str, seed: bytes | None = None, *, offset: int = 0) -> Any:
        """`POST /v1/sessions`; with `seed`, the code for now + `offset` steps."""
        from app import totp

        body: dict[str, Any] = {"username": username, "password": PASSWORD}
        if seed is not None:
            body["totp_code"] = totp.totp(seed, int(time.time()) + offset * totp.STEP_SECONDS)
        return self.call("POST", "/v1/sessions", body=body)

    def token(self, username: str, seed: bytes | None = None, *, offset: int = 0) -> str:
        response = self.login(username, seed, offset=offset)
        assert response.status_code == 200, response.text
        return response.json()["access_token"]


def _environment(cluster: ControlCluster, work: Any) -> dict[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from agentic_postgres import capability_compiler, scope_registry

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signing = work / "signing.pem"
    signing.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    passfile = work / "pgpass"
    passfile.write_text(f"*:*:*:*:{cluster.auth_password}\n", encoding="utf-8")
    passfile.chmod(0o600)
    # The release's vocabulary: the control project declares no surface of its
    # own, so its lock's vocabulary is the release's (D2078).
    canonical = json.loads(
        (
            REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
        ).read_text(encoding="utf-8")
    )
    lock = capability_compiler.compile_lock(
        canonical=canonical,
        project_key=cluster.document["project"]["key"],
        upstream="https://fixture-control-dev.test/api/rest",
        sources={
            "capabilities_sha256": "0" * 64,
            "api_surface_sha256": "0" * 64,
            "canonical_openapi_sha256": "0" * 64,
        },
        vocabulary=scope_registry.vocabulary_block(),
    )
    lock_path = work / "capability-lock.json"
    lock_path.write_text(capability_compiler.canonical_bytes(lock).decode("utf-8"), "utf-8")
    role_names = {
        suffix: cluster.roles[suffix]
        for suffix in sorted(scope_registry.ROLE_CLASSES)
        if suffix in cluster.roles
    }
    return {
        "APG_MCP_LOCK_FILE": str(lock_path),
        "APG_CONNECTOR_KEY_FILE": str(work / "no-connector-signing-key"),
        "APG_PROJECT_KEY": cluster.document["project"]["key"],
        "APG_PROJECT_ENVIRONMENT": "dev",
        "APG_JWT_ISSUER": cluster.document["jwt"]["issuer"],
        "APG_JWT_AUDIENCE": cluster.document["jwt"]["audience"],
        "APG_DATABASE_HOST": "127.0.0.1",
        "APG_DATABASE_PORT": str(cluster.port),
        "APG_DATABASE_NAME": cluster.database,
        "APG_DATABASE_ROLE": cluster.auth_role,
        "APG_DATABASE_PASSFILE": str(passfile),
        # Four, so two acceptances and their hashes can genuinely overlap.
        "APG_POOL_SIZE": "4",
        "APG_SIGNING_KEY_FILE": str(signing),
        "APG_LISTEN_PORT": "8080",
        "APG_ROLE_NAMES": json.dumps(role_names, separators=(",", ":"), sort_keys=True),
    }


@contextlib.contextmanager
def control_app(cluster: ControlCluster, work: Any) -> Iterator[ControlDriver]:
    """`create_app("control")` over `cluster`, started by its own lifespan."""
    import asyncio
    import os

    from app import main as main_module

    previous = dict(os.environ)
    os.environ.update(_environment(cluster, work))
    application = main_module.create_app("control")
    loop = asyncio.new_event_loop()
    context = application.router.lifespan_context(application)
    loop.run_until_complete(context.__aenter__())
    try:
        yield ControlDriver(cluster, application, loop)
    finally:
        loop.run_until_complete(context.__aexit__(None, None, None))
        loop.close()
        os.environ.clear()
        os.environ.update(previous)

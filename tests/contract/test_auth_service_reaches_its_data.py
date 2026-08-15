"""The auth service's role can do the auth service's work (D288, D289, D291).

**Three defects in a row hid each other**, and each was found only by a host
deploy that got one layer further than the last:

* D288 -- the role had no password, so it never authenticated;
* D289 -- it dialled a pooler whose userlist does not carry it, so it was
  refused before postgres saw it;
* D291 -- it had no `CONNECT` on the database, so it authenticated and was then
  refused.

Every one is the same cause: adding a service means touching every list that
enumerates roles, and nothing enumerated the lists. Each fix revealed the next
failure, which is a very expensive way to find three lines.

So this module stops asking whether a particular list is right and asks the
question the lists exist to answer: **can this role, credentialed the way the
product credentials it, connect to the database the product builds and execute
the functions the service calls?** It is the offline proof the three rigs that
reported this service healthy did not have, because each of them granted the
role what the product had failed to grant it.

Nothing here is a fake. The roles and grants come from
`postgres-bootstrap.py::build_statements`, the password from that file's own
`apply_credential`, the schema from the released migrations applied as
`migration_user`, and the queries from `services/auth-api/app/`'s own SQL. The
only thing this module supplies is a cluster.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Interpolated values are role and database names from a rendered outputs
# document this repository produced. See tests/deployment/conftest.py.
import importlib.util
import json
import secrets
import subprocess
import time
import uuid
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, migrations

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"


def _docker(*args: str, stdin: str | None = None, timeout: int = 240):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, input=stdin, timeout=timeout
    )


def _bootstrap() -> Any:
    specification = importlib.util.spec_from_file_location(
        "apg_pb_reach", REPO_ROOT / "bin" / "postgres-bootstrap.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _locked_image() -> str:
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "POSTGRES_IMAGE":
            return value.strip()
    pytest.fail("POSTGRES_IMAGE is absent from versions.env")


@pytest.fixture(scope="module")
def cluster() -> Any:
    """A cluster built the way a deploy builds one, then credentialed the way a
    deploy credentials one. Self-contained, so test order cannot matter."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    database = document["database"]["name"]
    name = f"apg-auth-reach-{secrets.token_hex(4)}"
    auth_password = secrets.token_hex(24)
    migration_password = secrets.token_hex(24)

    started = _docker(
        "run", "-d", "--name", name,
        "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
        _locked_image(),
    )  # fmt: skip
    if started.returncode != 0:
        pytest.skip(f"cannot start the locked cluster: {started.stderr.strip()[:200]}")

    try:
        rounds = 0
        for _ in range(90):
            probe = _docker("exec", name, "pg_isready", "-U", "postgres", timeout=30)
            rounds = rounds + 1 if probe.returncode == 0 else 0
            if rounds >= 2:
                break
            time.sleep(1)
        assert rounds >= 2, "the cluster never became ready"

        def su(sql: str, db: str = "postgres") -> subprocess.CompletedProcess[str]:
            return _docker(
                "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-d", db, stdin=sql,
            )  # fmt: skip

        setup = [f'CREATE ROLE "{role}" NOLOGIN;' for role in sorted(set(roles.values()))]
        setup += [
            f"ALTER ROLE \"{roles['migration_user']}\" LOGIN PASSWORD '{migration_password}';",
            f'GRANT "{roles["object_owner"]}" TO "{roles["migration_user"]}" '
            "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;",
            f'CREATE DATABASE "{database}" OWNER "{roles["object_owner"]}";',
        ]
        result = su("\n".join(setup))
        assert result.returncode == 0, result.stderr
        result = su(f'CREATE SCHEMA extensions AUTHORIZATION "{roles["object_owner"]}"', database)
        assert result.returncode == 0, result.stderr

        # The product's own database posture: REVOKE ALL FROM PUBLIC and the
        # CONNECT grants. This is the statement list D291 was missing from, and
        # taking it from the product is the whole point -- a hand-written copy
        # here would have been correct while the product's was not.
        bootstrap = _bootstrap()
        result = su("\n".join(bootstrap.build_statements(document, str(uuid.uuid4()))), database)
        assert result.returncode == 0, f"the product's bootstrap statements failed: {result.stderr}"

        manifest = migrations.load_manifest()
        for entry in manifest["migrations"]:
            payload = migrations.render_migration(entry, manifest, document)
            body = payload.split("-- migrate:down", 1)[0].replace("-- migrate:up", "", 1)
            applied = _docker(
                "exec", "-i", "-e", f"PGPASSWORD={migration_password}", name,
                "psql", "-U", roles["migration_user"], "-h", "127.0.0.1", "-d", database,
                "-qtA", "-v", "ON_ERROR_STOP=1", "-1", "-f", "-",
                stdin=body,
            )  # fmt: skip
            assert applied.returncode == 0, f"{entry['name']}: {applied.stderr[:400]}"

        # The credential, through the product's own function rather than an
        # ALTER ROLE written here. `test_auth_endpoints.py` writes its own, with
        # a comment noting the product does not -- which is exactly how D288
        # stayed invisible for four runs.
        bootstrap.apply_credential(name, database, roles["auth_service"], auth_password)

        yield {
            "name": name,
            "database": database,
            "roles": roles,
            "auth_password": auth_password,
        }
    finally:
        _docker("rm", "-f", name, timeout=60)


def as_auth(cluster: dict[str, Any], sql: str) -> subprocess.CompletedProcess[str]:
    """One statement, over TCP, as the auth service's own role."""
    return _docker(
        "exec", "-i", "-e", f"PGPASSWORD={cluster['auth_password']}", cluster["name"],
        "psql", "-U", cluster["roles"]["auth_service"], "-h", "127.0.0.1",
        "-d", cluster["database"], "-qtA", "-v", "ON_ERROR_STOP=1", stdin=sql,
    )  # fmt: skip


def test_the_auth_role_can_connect_at_all(cluster: dict[str, Any]) -> None:
    """D291, as the property rather than as a line in a grant.

    `REVOKE ALL ON DATABASE ... FROM PUBLIC` means a role absent from the CONNECT
    grant authenticates and is then refused with `permission denied for
    database`. That reached a host.
    """
    result = as_auth(cluster, "SELECT current_user;")
    assert result.returncode == 0, (
        f"the auth service's role cannot connect to its own database: {result.stderr.strip()[:300]}"
    )
    assert result.stdout.strip() == cluster["roles"]["auth_service"]


def test_the_auth_role_can_execute_the_functions_the_service_calls(
    cluster: dict[str, Any],
) -> None:
    """The access plane 0012 and 0013 grant it, exercised as the caller.

    Named one by one rather than by scanning the schema: the point is that the
    functions the SERVICE calls are executable, and a scan would pass just as
    happily on a set that had drifted away from the code.

    Each is called with an argument that finds nothing, so this measures
    authorization rather than data. `auth_lookup_user` returning no row for an
    unknown username is its documented contract.
    """
    probes = [
        "SELECT count(*) FROM app_private.auth_lookup_user('nobody-by-this-name');",
        "SELECT count(*) FROM app_private.auth_list_users();",
        "SELECT count(*) FROM app_private.auth_list_agents();",
        "SELECT count(*) FROM app_private.auth_user_state("
        "'00000000-0000-0000-0000-000000000000'::uuid);",
        "SELECT count(*) FROM app_private.auth_lookup_agent("
        "'00000000-0000-0000-0000-000000000000'::uuid);",
    ]
    refused = {}
    for sql in probes:
        result = as_auth(cluster, sql)
        if result.returncode != 0:
            refused[sql.split("app_private.")[1].split("(")[0]] = result.stderr.strip()[:200]

    assert not refused, (
        f"the auth service's role cannot execute functions its own code calls: {refused}. "
        "0012 and 0013 grant EXECUTE on these; a failure here means the grant and the "
        "caller have drifted apart"
    )


def test_the_auth_role_cannot_reach_past_its_access_plane(cluster: dict[str, Any]) -> None:
    """The control, and it is what makes the test above mean something.

    A role that could read the tables directly would pass every probe above
    while the SECURITY DEFINER functions were doing nothing for it -- and the
    grants those migrations spend two hundred lines on would be decoration.
    """
    for table in ("users", "user_credentials", "agents", "agent_credentials"):
        result = as_auth(cluster, f"SELECT count(*) FROM app_private.{table};")
        assert result.returncode != 0, (
            f"the auth service's role can read app_private.{table} directly. Its reach is "
            "supposed to be the SECURITY DEFINER functions and nothing else"
        )
        assert "permission denied" in result.stderr.lower(), result.stderr.strip()[:200]


def test_the_bootstrap_administrator_function_is_not_reachable_by_the_service(
    cluster: dict[str, Any],
) -> None:
    """0012's deliberate omission, verified as the caller rather than read off a grant.

    A service that could call it could create the first administrator in
    response to a request, which is the public bootstrap endpoint SEC-BOOT-002
    says does not exist.
    """
    result = as_auth(
        cluster,
        "SELECT app_private.auth_bootstrap_administrator("
        "'probe', 'Probe', 'role', ARRAY['notes:read']::text[], 'hash');",
    )
    assert result.returncode != 0, (
        "the auth service's role can call auth_bootstrap_administrator, so the bootstrap "
        "is reachable from an HTTP request"
    )
    assert "permission denied" in result.stderr.lower(), result.stderr.strip()[:200]

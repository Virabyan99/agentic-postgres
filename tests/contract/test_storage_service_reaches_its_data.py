"""The storage role can do the storage service's work, and nothing else.

Run 4's exit criterion, and the proof Run 3 could not make: *the role connects
directly, executes exactly the storage functions, and can reach nothing else*.

Run 3 reached `storage_service` through `SET ROLE` from a superuser session,
which exercises the GRANTS and says nothing about the login path. That gap was
stated in the module docstring rather than left implicit, because D211-D214 is
what happens otherwise -- and it was the right split, since the login path did
not exist until this run: the role had a connection limit from Run 1 and was
absent from the `CONNECT` grant.

**Nothing here is a fake.** The roles and grants come from
`postgres-bootstrap.py::build_statements`, the password from that file's own
`apply_credential`, the schema from the fourteen released migrations applied as
`migration_user`, and the credential is recovered through the contract's own
consumer. The only thing this module supplies is a cluster.

That is ADR 0065/0066's rule, and D288/D289/D291 are what ignoring it cost: three
rigs reported the auth service healthy because each of them credentialed the role
itself, in a way the product did not. This module credentials nothing.
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

from agentic_postgres import REPO_ROOT, migrations, secrets_contract

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"


def _docker(*args: str, stdin: str | None = None, timeout: int = 240):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, input=stdin, timeout=timeout
    )


def _bootstrap() -> Any:
    specification = importlib.util.spec_from_file_location(
        "apg_postgres_bootstrap", REPO_ROOT / "bin" / "postgres-bootstrap.py"
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
def cluster(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Built the way a deploy builds one, credentialed the way a deploy does."""
    tmp_root = tmp_path_factory.mktemp("secret-root")
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    database = document["database"]["name"]
    name = f"apg-storage-reach-{secrets.token_hex(4)}"
    storage_password = secrets.token_hex(24)
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

        # A second project's database, so cross-project isolation can be tested
        # against a database that EXISTS. Asserting a refusal against an absent
        # database would pass for the wrong reason -- "does not exist" and
        # "permission denied" are both non-zero exits.
        peer = f"{database}_peer"
        result = su(
            f'CREATE DATABASE "{peer}" OWNER "{roles["object_owner"]}";'
            f'REVOKE ALL ON DATABASE "{peer}" FROM PUBLIC;'
        )
        assert result.returncode == 0, result.stderr

        # The product's own database posture, including the CONNECT list this
        # run added the storage role to. A hand-written copy here would have
        # been correct while the product's was not -- which is exactly how D291
        # stayed invisible.
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

        # **Through the product's own DECISION, not just its ALTER ROLE.**
        #
        # The first version of this called `apply_credential` directly, and the
        # mutation battery caught it: removing the product's credential logic
        # entirely left every test here green, because this fixture was doing
        # the product's job. That is D288/D289/D291's mistake occurring inside
        # the module whose docstring says it does not make it -- a rig that
        # reaches the right end state by a route the product does not take.
        #
        # So a generation is written where the materializer writes one, and
        # `activate_storage_service` is asked to find it. `SECRET_ROOT` is
        # redirected because the real path is root-owned; everything after that
        # is the product's -- which consumer it looks for, what filename that
        # implies, how the pgpass line is read back, and whether to credential
        # at all.
        generation = tmp_root / "alpha" / "generations" / "gen-0001" / "storage"
        generation.mkdir(parents=True)
        consumer = bootstrap.STORAGE_SERVICE_CONSUMER
        (generation / consumer["target_file"]).write_text(
            secrets_contract.render_secret(storage_password, consumer), encoding="utf-8"
        )
        (tmp_root / "alpha" / "active-secret-generation.json").write_text(
            json.dumps({"generation_id": "gen-0001"}), encoding="utf-8"
        )
        # BOTH module globals, because `materialized_secret_path` reads the root
        # twice: the generation pointer through its own module's `SECRET_ROOT`,
        # and the file path through `secrets_contract.secret_source_path`, which
        # reads `secrets_contract.SECRET_ROOT`. Redirecting one left the pointer
        # found under the fake root and the file looked for under the real one.
        # They are the same constant in production, so nothing was wrong -- but
        # a value read from two places is a value that can be read from two
        # places, and this test found out the hard way.
        original_roots = (bootstrap.SECRET_ROOT, secrets_contract.SECRET_ROOT)
        bootstrap.SECRET_ROOT = str(tmp_root)
        secrets_contract.SECRET_ROOT = str(tmp_root)

        credentialed = bootstrap.activate_storage_service(
            name, database, "alpha", roles["storage_service"], 6
        )
        bootstrap.SECRET_ROOT, secrets_contract.SECRET_ROOT = original_roots
        assert credentialed, (
            "the product declined to credential the storage role from a generation that "
            "carries its file, so nothing below is about a role the product activated"
        )

        yield {
            "name": name,
            "database": database,
            "peer": peer,
            "roles": roles,
            "password": storage_password,
            "su": su,
        }
    finally:
        _docker("rm", "-f", name, timeout=60)


def as_storage(cluster: dict[str, Any], sql: str) -> subprocess.CompletedProcess[str]:
    """One statement, over TCP, as the storage service's own role.

    Over TCP with a password rather than `-U role` on the socket: the socket
    would use peer authentication as root and could connect as a role this test
    has established no password for, which would quietly exercise a different
    login path from the one the container uses.
    """
    return _docker(
        "exec", "-i", "-e", f"PGPASSWORD={cluster['password']}", cluster["name"],
        "psql", "-U", cluster["roles"]["storage_service"], "-h", "127.0.0.1",
        "-d", cluster["database"], "-qtA", "-v", "ON_ERROR_STOP=1", stdin=sql,
    )  # fmt: skip


def owner(cluster: dict[str, Any], sql: str) -> subprocess.CompletedProcess[str]:
    return cluster["su"](
        f'SET ROLE "{cluster["roles"]["object_owner"]}";\n{sql}', cluster["database"]
    )


@pytest.fixture(scope="module")
def subject(cluster: dict[str, Any]) -> str:
    result = owner(
        cluster,
        "SELECT app_private.auth_create_user('storage-reach-owner', 'storage-reach-owner', "
        "'authenticated', ARRAY['objects:read','objects:write']::text[], "
        "'$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA');",
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


# ---------------------------------------------------------------------------
# It connects
# ---------------------------------------------------------------------------


def test_the_storage_role_can_connect_at_all(cluster: dict[str, Any]) -> None:
    """D291 as a property rather than as a line in a grant.

    The failure this catches is `FATAL: permission denied for database` with
    `DETAIL: User does not have CONNECT privilege` -- which is what the role got
    before this run, because `REVOKE ALL ON DATABASE ... FROM PUBLIC` means a
    role absent from the CONNECT list cannot connect however correct its
    password is.
    """
    result = as_storage(cluster, "SELECT 1;")
    assert result.returncode == 0, (
        f"the storage role cannot connect to its own database: {result.stderr.strip()[:300]}"
    )
    assert result.stdout.strip().splitlines()[-1] == "1"


def test_the_storage_role_carries_the_connection_limit_the_division_produced(
    cluster: dict[str, Any],
) -> None:
    """ADR 0099's fourth claimant, read from the catalog.

    A limit that is computed and not applied is a claimant the cluster does not
    know about, and the budget it was computed from is then a number in a
    document rather than a bound on anything.
    """
    result = cluster["su"](
        "SELECT rolconnlimit::text FROM pg_roles WHERE rolname = "
        f"'{cluster['roles']['storage_service']}';",
        cluster["database"],
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "6"


def test_the_storage_role_holds_no_membership_in_anything(cluster: dict[str, Any]) -> None:
    """No membership in `authenticated`, `project_admin`, the agent roles, the
    owner role or the migration role -- the plan's list, asserted as *none at
    all* rather than as that list.

    Stated as a closed property because an enumerated one is only as complete as
    whoever wrote it, and D266 is the cost of a membership nobody meant: without
    `INHERIT FALSE` a holder gets every request role's reach merely by
    connecting. The storage service needs no role but its own -- it reaches its
    data through SECURITY DEFINER functions, which run as their owner and need
    no membership from the caller.
    """
    result = cluster["su"](
        "SELECT coalesce(string_agg(r.rolname, ',' ORDER BY r.rolname), '') "
        "FROM pg_catalog.pg_auth_members m "
        "JOIN pg_catalog.pg_roles r ON r.oid = m.roleid "
        "JOIN pg_catalog.pg_roles member ON member.oid = m.member "
        f"WHERE member.rolname = '{cluster['roles']['storage_service']}';",
        cluster["database"],
    )
    assert result.returncode == 0, result.stderr
    observed = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert observed == "", (
        f"the storage role is a member of {observed!r}. It needs no membership at all: its "
        "functions are SECURITY DEFINER and run as their owner"
    )


# ---------------------------------------------------------------------------
# It executes exactly the storage functions
# ---------------------------------------------------------------------------


def test_the_storage_role_can_run_the_functions_the_service_calls(
    cluster: dict[str, Any], subject: str
) -> None:
    """All seven, over its own connection, in the order the service uses them.

    Driven as a sequence rather than as seven independent calls because that is
    what the service does, and because a function that only works from a state
    no earlier call can produce is not reachable in practice.
    """
    key = f"objects/fixture-alpha-dev/v1/{uuid.uuid4()}"

    created = as_storage(
        cluster,
        "SELECT app_private.storage_create_upload_intent("
        f"'{subject}'::uuid, '{key}', 'application/pdf', 2048, 900);",
    )
    assert created.returncode == 0, created.stderr
    identifier = created.stdout.strip().splitlines()[-1]

    completed = as_storage(
        cluster,
        f"SELECT app_private.storage_complete_upload('{identifier}'::uuid, "
        f"'{subject}'::uuid, 2048);",
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().splitlines()[-1] == "available"

    looked_up = as_storage(
        cluster,
        "SELECT object_key FROM app_private.storage_lookup_for_download("
        f"'{identifier}'::uuid, '{subject}'::uuid);",
    )
    assert looked_up.returncode == 0, looked_up.stderr
    assert looked_up.stdout.strip().splitlines()[-1] == key

    tombstoned = as_storage(
        cluster,
        f"SELECT app_private.storage_tombstone('{identifier}'::uuid, '{subject}'::uuid);",
    )
    assert tombstoned.returncode == 0, tombstoned.stderr
    assert tombstoned.stdout.strip().splitlines()[-1] == "t"

    claimed = as_storage(
        cluster,
        "SELECT id FROM app_private.storage_claim_cleanup_batch('reach-worker', 10, 300, 0);",
    )
    assert claimed.returncode == 0, claimed.stderr
    assert identifier in claimed.stdout

    finished = as_storage(
        cluster,
        f"SELECT app_private.storage_finish_cleanup('{identifier}'::uuid, 'reach-worker');",
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip().splitlines()[-1] == "t"

    swept = as_storage(cluster, "SELECT app_private.storage_expire_intents(10);")
    assert swept.returncode == 0, swept.stderr


# ---------------------------------------------------------------------------
# And can reach nothing else
# ---------------------------------------------------------------------------


def test_the_storage_role_cannot_reach_past_its_access_plane(cluster: dict[str, Any]) -> None:
    """Proved by ATTEMPTING, over the role's own connection (D103).

    `has_table_privilege` returned true once for a table the role could not
    actually read, so a catalog bit is not the evidence. Every statement below
    is run and refused.
    """
    for statement in (
        "SELECT count(*) FROM app_private.storage_objects;",
        "SELECT count(*) FROM app_private.users;",
        "SELECT count(*) FROM app_private.user_credentials;",
        "SELECT count(*) FROM app.notes;",
        "SELECT app_private.auth_list_users();",
        "UPDATE app_private.storage_objects SET state = 'available';",
    ):
        result = as_storage(cluster, statement)
        assert result.returncode != 0, (
            f"the storage role executed {statement!r} over its own connection. It must reach "
            "its data only through the definer functions"
        )
        assert "permission denied" in result.stderr.lower(), result.stderr


def test_the_storage_role_cannot_become_another_role(cluster: dict[str, Any]) -> None:
    """The control for the membership test: no membership means no SET ROLE.

    Without this, "holds no membership" would be a catalog reading rather than a
    capability, and the two came apart once already (D103's shape).
    """
    for target in ("authenticated", "project_admin", "object_owner", "auth_service"):
        result = as_storage(cluster, f'SET ROLE "{cluster["roles"][target]}"; SELECT 1;')
        assert result.returncode != 0, (
            f"the storage role became {target}, so its own privileges are not its ceiling"
        )


def _connect_to(cluster: dict[str, Any], database: str) -> subprocess.CompletedProcess[str]:
    return _docker(
        "exec", "-i", "-e", f"PGPASSWORD={cluster['password']}", cluster["name"],
        "psql", "-U", cluster["roles"]["storage_service"], "-h", "127.0.0.1",
        "-d", database, "-qtA", "-v", "ON_ERROR_STOP=1", stdin="SELECT 1;",
    )  # fmt: skip


def test_the_storage_role_cannot_reach_a_peer_projects_database(cluster: dict[str, Any]) -> None:
    """Cross-project isolation, at the connection rather than at the row.

    `REVOKE ALL ON DATABASE … FROM PUBLIC` plus a per-project CONNECT list is
    what makes this true, and the peer database in this rig **exists** —
    deliberately. Asserting a refusal against an absent database would pass for
    the wrong reason, because "does not exist" and "permission denied" are both
    a non-zero exit.
    """
    refused = _connect_to(cluster, cluster["peer"])
    assert refused.returncode != 0, (
        "the storage role connected to a peer project's database, which its CONNECT grant "
        "does not name"
    )
    assert "permission denied for database" in refused.stderr.lower(), (
        f"refused for the wrong reason: {refused.stderr.strip()[:200]}"
    )

    # The control: its own database, over the same connection path.
    allowed = _connect_to(cluster, cluster["database"])
    assert allowed.returncode == 0, (
        "the storage role cannot reach its OWN database either, so the refusal above says "
        "nothing about isolation"
    )


def test_the_maintenance_database_is_reachable_by_every_service_role(
    cluster: dict[str, Any],
) -> None:
    """**A boundary this repository has never stated, recorded rather than assumed.**

    `build_statements` issues `REVOKE ALL ON DATABASE … FROM PUBLIC` on the
    PROJECT database only. The `postgres` maintenance database keeps PostgreSQL's
    default PUBLIC CONNECT, so every role with LOGIN can open a session there —
    `app_runtime`, `postgrest_authenticator`, `auth_service` and now
    `storage_service` alike. Session 7 did not introduce it and Run 4 does not
    fix it: the change would touch every role in every session.

    What it exposes is catalog metadata and nothing else, and this test measures
    that rather than asserting it. Project *data* stays unreachable — the peer
    database test above is what proves that half.

    This test asserts the CURRENT state so the state is visible. If a later
    session revokes PUBLIC CONNECT on the maintenance database, this goes red and
    the fix is to invert it, which is the point (D340).
    """
    reached = _connect_to(cluster, "postgres")
    assert reached.returncode == 0, (
        "the maintenance database is no longer reachable. If that was deliberate, invert "
        "this test and note the session that closed it"
    )

    # What it can actually see from there, measured rather than reasoned about.
    listing = _docker(
        "exec", "-i", "-e", f"PGPASSWORD={cluster['password']}", cluster["name"],
        "psql", "-U", cluster["roles"]["storage_service"], "-h", "127.0.0.1",
        "-d", "postgres", "-qtA", "-v", "ON_ERROR_STOP=1",
        stdin="SELECT count(*) > 0 FROM pg_catalog.pg_database;",
    )  # fmt: skip
    assert listing.returncode == 0
    assert listing.stdout.strip().splitlines()[-1] == "t", (
        "the role reached the maintenance database but cannot read pg_database; the "
        "exposure is narrower than this test records and the docstring should say so"
    )

    # And still no project data, from the maintenance database either.
    blocked = _docker(
        "exec", "-i", "-e", f"PGPASSWORD={cluster['password']}", cluster["name"],
        "psql", "-U", cluster["roles"]["storage_service"], "-h", "127.0.0.1",
        "-d", "postgres", "-qtA", "-v", "ON_ERROR_STOP=1",
        stdin="SELECT count(*) FROM app_private.users;",
    )  # fmt: skip
    assert blocked.returncode != 0, (
        "project tables are visible from the maintenance database, which would make this a "
        "data boundary rather than a metadata one"
    )

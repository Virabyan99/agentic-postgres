"""Migration 0014's object-storage plane, against a real cluster.

The schema half of Session 7. Everything here runs against the locked
`pgvector/pgvector:pg18` digest with all fourteen released migrations applied
**as `migration_user`**, never as a superuser (D285): every offline rig before
Session 6 applied migrations with `psql -U postgres`, a superuser bypasses the
ownership check, and that is how 0012 and 0013 shipped unable to apply.

**What this module does not prove, and where that now lives.** The privilege
tests here reach `storage_service` through `SET ROLE` from a superuser session,
which exercises the GRANTS and says nothing about the login path — when this was
written the role had a connection limit from Run 1 and was absent from the
`CONNECT` grant, so there was no login path to exercise.

**Run 4 built it, and `tests/contract/test_storage_service_reaches_its_data.py`
is the proof**: the role connecting over TCP with a password the product's own
`apply_credential` set, running all seven functions, and refused everything else.
This module keeps the `SET ROLE` form deliberately — it is about what migration
0014 decides, and 0014 decides grants rather than logins. The two together are
what D211-D214 asks for: the gap was named while it existed rather than
discovered later.

The privilege proofs attempt the operation rather than reading a catalog bit.
D103 recorded `has_table_privilege` returning true for a table the role could not
actually read, so "denied" here means a statement was run and refused.
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
import threading
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
def cluster() -> Any:
    """A cluster built the way a deploy builds one, with all fourteen applied."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    database = document["database"]["name"]
    name = f"apg-storage-plane-{secrets.token_hex(4)}"
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

        yield {"name": name, "database": database, "roles": roles, "su": su}
    finally:
        _docker("rm", "-f", name, timeout=60)


def su(cluster: dict[str, Any], sql: str) -> subprocess.CompletedProcess[str]:
    return cluster["su"](sql, cluster["database"])


def as_storage(cluster: dict[str, Any], sql: str) -> subprocess.CompletedProcess[str]:
    """One statement as `storage_service`, reached by SET ROLE.

    Not by logging in: the role has no LOGIN attribute and no CONNECT grant until
    Run 4's bootstrap-plane work. `SET ROLE` exercises the GRANTS, which is what
    0014 decides; the connect path is Run 4's and is not proved here.
    """
    return su(cluster, f'SET ROLE "{cluster["roles"]["storage_service"]}";\n{sql}')


def owner(cluster: dict[str, Any], sql: str) -> subprocess.CompletedProcess[str]:
    """As the object owner -- what a migration or an operator would use."""
    return su(cluster, f'SET ROLE "{cluster["roles"]["object_owner"]}";\n{sql}')


@pytest.fixture(scope="module")
def subjects(cluster: dict[str, Any]) -> dict[str, str]:
    """Two registered subjects, created through the product's own function.

    `auth_create_user` rather than an INSERT written here: the owner column is a
    foreign key into `app_private.users`, and a subject this test invented would
    be an identity the deployment has never heard of. D313 is the same point at
    the token layer.
    """
    created: dict[str, str] = {}
    for label, username in (("first", "storage-owner-one"), ("second", "storage-owner-two")):
        result = owner(
            cluster,
            "SELECT app_private.auth_create_user("
            f"'{username}', '{username}', 'authenticated', "
            "ARRAY['objects:read','objects:write']::text[], "
            "'$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA');",
        )
        assert result.returncode == 0, result.stderr
        created[label] = result.stdout.strip().splitlines()[-1]
    assert created["first"] != created["second"]
    return created


def new_intent(
    cluster: dict[str, Any], owner_id: str, *, ttl: int = 900, key: str | None = None
) -> str:
    key = key or f"objects/fixture-alpha-dev/v1/{uuid.uuid4()}"
    result = as_storage(
        cluster,
        "SELECT app_private.storage_create_upload_intent("
        f"'{owner_id}'::uuid, '{key}', 'application/pdf', 1024, {ttl});",
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


# ---------------------------------------------------------------------------
# Ownership and ACLs
# ---------------------------------------------------------------------------


def test_the_storage_functions_are_owned_by_the_object_owner(cluster: dict[str, Any]) -> None:
    """A SECURITY DEFINER function runs as its owner, so who owns it is the
    privilege it confers. One created outside the `SET LOCAL ROLE` would run as
    `migration_user` and confer that instead.

    **Eight since Run 6**, not 0014's seven: migration 0015 adds
    `storage_completion_key`, the function 0014 needed and did not have. The
    count is updated rather than relaxed to a `>=`, because what it catches is a
    function DISAPPEARING and a floor would stop catching that.
    """
    result = su(
        cluster,
        "SELECT p.proname || '=' || pg_catalog.pg_get_userbyid(p.proowner) "
        "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'app_private' AND p.proname LIKE 'storage\\_%' ORDER BY 1;",
    )
    assert result.returncode == 0, result.stderr
    rows = [line for line in result.stdout.strip().splitlines() if line]
    assert len(rows) == 8, f"expected eight storage functions, found {rows}"
    for row in rows:
        assert row.endswith(f"={cluster['roles']['object_owner']}"), row


def test_every_storage_function_is_a_definer_with_a_pinned_search_path(
    cluster: dict[str, Any],
) -> None:
    """`SET search_path = pg_catalog, pg_temp` on every one.

    Without it a caller who can create a temporary object shadows an unqualified
    name inside a function running with the owner's authority.
    """
    result = su(
        cluster,
        "SELECT p.proname || '|' || p.prosecdef::text || '|' || "
        "COALESCE(pg_catalog.array_to_string(p.proconfig, ','), 'NONE') "
        "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'app_private' AND p.proname LIKE 'storage\\_%' ORDER BY 1;",
    )
    assert result.returncode == 0, result.stderr
    rows = [line for line in result.stdout.strip().splitlines() if line]
    assert rows
    for row in rows:
        name, secdef, config = row.split("|")
        # `true`, not psql's display form `t`. An explicit ::text cast renders
        # the boolean's own text representation; an UNCAST boolean column is
        # displayed by psql as t/f. Two different strings, and the first draft of
        # this test asserted the one the other assertions in this module use.
        assert secdef == "true", f"{name} is not SECURITY DEFINER"
        assert config == "search_path=pg_catalog, pg_temp", f"{name} has search_path {config!r}"


def test_no_storage_function_is_executable_by_public(cluster: dict[str, Any]) -> None:
    """D57 and D262, measured twice in this repository three sessions apart.

    A newly created function is PUBLIC-executable, and the
    `ALTER DEFAULT PRIVILEGES … REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC` that
    0011 uses for tables records nothing at all for functions. The blanket revoke
    in 0014 is the only thing standing between these seven and every role holding
    USAGE on `app_private`.

    `proacl IS NULL` means the built-in default, and the built-in default
    INCLUDES PUBLIC -- so a NULL acl here is a failure, not an absence.
    """
    result = su(
        cluster,
        "SELECT p.proname || '=' || COALESCE(p.proacl::text, 'NULL') "
        "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'app_private' AND p.proname LIKE 'storage\\_%' ORDER BY 1;",
    )
    assert result.returncode == 0, result.stderr
    rows = [line for line in result.stdout.strip().splitlines() if line]
    assert rows
    for row in rows:
        assert "NULL" not in row, (
            f"{row}: proacl is NULL, which is the built-in default, and the built-in "
            "default is PUBLIC-executable (D262)"
        )
        assert "=X/" not in row.split("{", 1)[-1].split(",")[0] or "storage" in row, row
        # An entry with an empty grantee is PUBLIC.
        assert not any(
            item.strip().startswith("=") for item in row.split("{", 1)[-1].rstrip("}").split(",")
        ), f"{row}: PUBLIC holds a privilege on this function"


def test_the_storage_role_holds_no_privilege_on_the_table(cluster: dict[str, Any]) -> None:
    """The property the whole access plane exists for, proved by ATTEMPTING.

    D103 is why this is not `has_table_privilege`: that returned true for a table
    the role could not actually read. A denial here is a statement that ran and
    was refused.
    """
    for statement in (
        "SELECT count(*) FROM app_private.storage_objects;",
        "INSERT INTO app_private.storage_objects "
        "(owner_id, object_key, content_type, declared_bytes, intent_expires_at) "
        "VALUES (gen_random_uuid(), 'k', 'text/plain', 1, now());",
        "UPDATE app_private.storage_objects SET state = 'available';",
        "DELETE FROM app_private.storage_objects;",
    ):
        result = as_storage(cluster, statement)
        assert result.returncode != 0, (
            f"the storage role executed {statement!r}. It must reach the table only through "
            "the definer functions, or a defect in the service can read another owner's row"
        )
        assert "permission denied" in result.stderr.lower(), result.stderr


def test_the_auth_role_cannot_call_a_storage_function(cluster: dict[str, Any]) -> None:
    """One image runs both modes (ADR 0101), and the database is where that
    boundary is real rather than aspirational."""
    result = su(
        cluster,
        f'SET ROLE "{cluster["roles"]["auth_service"]}";\n'
        "SELECT app_private.storage_expire_intents(1);",
    )
    assert result.returncode != 0
    assert "permission denied" in result.stderr.lower(), result.stderr


def test_the_storage_role_cannot_call_an_auth_function(cluster: dict[str, Any]) -> None:
    """The same boundary from the other side. One direction alone is satisfied by
    a role that can call nothing at all."""
    result = as_storage(cluster, "SELECT app_private.auth_list_users();")
    assert result.returncode != 0
    assert "permission denied" in result.stderr.lower(), result.stderr


# ---------------------------------------------------------------------------
# The transition matrix
# ---------------------------------------------------------------------------


def test_a_fresh_intent_is_pending_and_not_downloadable(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    identifier = new_intent(cluster, subjects["first"])
    result = as_storage(
        cluster,
        "SELECT count(*) FROM app_private.storage_lookup_for_download("
        f"'{identifier}'::uuid, '{subjects['first']}'::uuid);",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "0", (
        "a pending object is downloadable, so an abandoned upload intent would hand out a "
        "URL for bytes that may never have arrived (STO-COMPLETE-001)"
    )


def test_completion_makes_it_downloadable_and_is_idempotent(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    identifier = new_intent(cluster, subjects["first"])

    first = as_storage(
        cluster,
        f"SELECT app_private.storage_complete_upload('{identifier}'::uuid, "
        f"'{subjects['first']}'::uuid, 2048);",
    )
    assert first.returncode == 0, first.stderr
    assert first.stdout.strip().splitlines()[-1] == "available"

    second = as_storage(
        cluster,
        f"SELECT app_private.storage_complete_upload('{identifier}'::uuid, "
        f"'{subjects['first']}'::uuid, 4096);",
    )
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip().splitlines()[-1] == "available", (
        "a second completion raised or reported something else. Completion is a CAS and "
        "the second call must report the state the object is already in"
    )

    verified = as_storage(
        cluster,
        "SELECT verified_bytes FROM app_private.storage_lookup_for_download("
        f"'{identifier}'::uuid, '{subjects['first']}'::uuid);",
    )
    assert verified.stdout.strip().splitlines()[-1] == "2048", (
        "the second completion overwrote verified_bytes, so a replayed completion can "
        "rewrite what the provider reported"
    )


def test_a_tombstone_stops_the_download_and_is_idempotent(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    identifier = new_intent(cluster, subjects["first"])
    as_storage(
        cluster,
        f"SELECT app_private.storage_complete_upload('{identifier}'::uuid, "
        f"'{subjects['first']}'::uuid, 512);",
    )

    first = as_storage(
        cluster,
        f"SELECT app_private.storage_tombstone('{identifier}'::uuid, '{subjects['first']}'::uuid);",
    )
    assert first.stdout.strip().splitlines()[-1] == "t"

    second = as_storage(
        cluster,
        f"SELECT app_private.storage_tombstone('{identifier}'::uuid, '{subjects['first']}'::uuid);",
    )
    assert second.stdout.strip().splitlines()[-1] == "f", (
        "a second tombstone reported that it moved the object. False is the honest answer "
        "and is what makes the operation safe to retry"
    )

    lookup = as_storage(
        cluster,
        "SELECT count(*) FROM app_private.storage_lookup_for_download("
        f"'{identifier}'::uuid, '{subjects['first']}'::uuid);",
    )
    assert lookup.stdout.strip().splitlines()[-1] == "0", (
        "a tombstoned object is still downloadable. The tombstone commits before any later "
        "grant reads this, and that ordering is the linearization the security matrix names"
    )


def test_a_tombstoned_object_cannot_be_completed(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    """The state machine is one-way. Without the CAS predicate a late completion
    would resurrect an object its owner had deleted."""
    identifier = new_intent(cluster, subjects["first"])
    as_storage(
        cluster,
        f"SELECT app_private.storage_tombstone('{identifier}'::uuid, '{subjects['first']}'::uuid);",
    )
    result = as_storage(
        cluster,
        f"SELECT app_private.storage_complete_upload('{identifier}'::uuid, "
        f"'{subjects['first']}'::uuid, 64);",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "tombstoned", (
        "completing a tombstoned object did not report it as tombstoned; if it returned "
        "'available' the object has been resurrected"
    )


def test_the_state_constraints_refuse_an_incoherent_row(cluster: dict[str, Any]) -> None:
    """ADR 0080 in the direction that matters: these constraints are TOTAL.

    A CHECK passes when its expression is NULL, so a coherence constraint written
    as `completed_at IS NOT NULL` is safe while one written as
    `completed_at > created_at` would silently accept a NULL. Driven as the
    owner, because the storage role holds no privilege on the table.
    """
    owner_id = (
        owner(
            cluster,
            "SELECT app_private.auth_create_user('constraint-probe', 'constraint-probe', "
            "'authenticated', ARRAY['objects:read']::text[], "
            "'$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA');",
        )
        .stdout.strip()
        .splitlines()[-1]
    )

    # available with no verified_bytes and no completed_at
    bad = owner(
        cluster,
        "INSERT INTO app_private.storage_objects "
        "(owner_id, object_key, content_type, declared_bytes, intent_expires_at, state) "
        f"VALUES ('{owner_id}'::uuid, 'objects/probe/bad-available', 'text/plain', 1, "
        "now() + interval '1 hour', 'available');",
    )
    assert bad.returncode != 0, "an available object with no verified size was accepted"
    assert "storage_objects_available_is_verified" in bad.stderr, bad.stderr

    # a lease holder with no expiry
    half = owner(
        cluster,
        "INSERT INTO app_private.storage_objects "
        "(owner_id, object_key, content_type, declared_bytes, intent_expires_at, state, "
        " tombstoned_at, cleanup_lease_holder) "
        f"VALUES ('{owner_id}'::uuid, 'objects/probe/half-lease', 'text/plain', 1, "
        "now() + interval '1 hour', 'tombstoned', now(), 'worker');",
    )
    assert half.returncode != 0, "a lease holder with no expiry was accepted"
    assert "storage_objects_lease_is_a_pair" in half.stderr, half.stderr

    # cleanup state on a live object
    live = owner(
        cluster,
        "INSERT INTO app_private.storage_objects "
        "(owner_id, object_key, content_type, declared_bytes, intent_expires_at, "
        " cleanup_lease_holder, cleanup_lease_expires_at) "
        f"VALUES ('{owner_id}'::uuid, 'objects/probe/live-lease', 'text/plain', 1, "
        "now() + interval '1 hour', 'worker', now() + interval '1 minute');",
    )
    assert live.returncode != 0, (
        "a pending object was given a cleanup lease, so a bug in the claim query could "
        "lease a live object and delete bytes its owner can still download"
    )
    assert "storage_objects_only_tombstones_are_collected" in live.stderr, live.stderr


def test_a_duplicate_object_key_is_refused(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    """Key uniqueness is what stops a replayed presigned PUT reaching a second row."""
    key = f"objects/fixture-alpha-dev/v1/{uuid.uuid4()}"
    new_intent(cluster, subjects["first"], key=key)
    result = as_storage(
        cluster,
        "SELECT app_private.storage_create_upload_intent("
        f"'{subjects['first']}'::uuid, '{key}', 'application/pdf', 1024, 900);",
    )
    assert result.returncode != 0, "two intents were created on one object key"
    assert "storage_objects_object_key_key" in result.stderr, result.stderr


# ---------------------------------------------------------------------------
# Cross-owner: the four answers that must be identical
# ---------------------------------------------------------------------------


def test_a_second_owner_gets_nothing_and_cannot_tell_why(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    """STO-OWN-001. Absent, foreign, pending and tombstoned are ONE answer.

    A caller that could tell "not yours" from "no such id" can enumerate another
    user's object ids by trying them.
    """
    available = new_intent(cluster, subjects["first"])
    as_storage(
        cluster,
        f"SELECT app_private.storage_complete_upload('{available}'::uuid, "
        f"'{subjects['first']}'::uuid, 128);",
    )
    pending = new_intent(cluster, subjects["first"])
    tombstoned = new_intent(cluster, subjects["first"])
    as_storage(
        cluster,
        f"SELECT app_private.storage_tombstone('{tombstoned}'::uuid, '{subjects['first']}'::uuid);",
    )
    absent = str(uuid.uuid4())

    answers = {}
    for label, identifier in (
        ("foreign-available", available),
        ("foreign-pending", pending),
        ("foreign-tombstoned", tombstoned),
        ("absent", absent),
    ):
        result = as_storage(
            cluster,
            "SELECT count(*) FROM app_private.storage_lookup_for_download("
            f"'{identifier}'::uuid, '{subjects['second']}'::uuid);",
        )
        assert result.returncode == 0, result.stderr
        answers[label] = result.stdout.strip().splitlines()[-1]

    assert set(answers.values()) == {"0"}, answers

    # The control: the owner's own available object DOES come back. Without it,
    # a lookup that returned nothing to everybody would pass the assertion above.
    mine = as_storage(
        cluster,
        "SELECT count(*) FROM app_private.storage_lookup_for_download("
        f"'{available}'::uuid, '{subjects['first']}'::uuid);",
    )
    assert mine.stdout.strip().splitlines()[-1] == "1", (
        "the owner cannot read their own available object, so the cross-owner assertion "
        "above holds for a reason that has nothing to do with ownership"
    )


def test_a_second_owner_cannot_tombstone_or_complete_another_subjects_object(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    identifier = new_intent(cluster, subjects["first"])

    stolen = as_storage(
        cluster,
        f"SELECT app_private.storage_tombstone('{identifier}'::uuid, "
        f"'{subjects['second']}'::uuid);",
    )
    assert stolen.stdout.strip().splitlines()[-1] == "f"

    completed = as_storage(
        cluster,
        f"SELECT app_private.storage_complete_upload('{identifier}'::uuid, "
        f"'{subjects['second']}'::uuid, 99);",
    )
    assert completed.returncode == 0, completed.stderr
    # A SQL NULL comes back as an empty line, so `.strip()` is empty and
    # `splitlines()` is []. Compared as a whole rather than by last line, which
    # is what the first draft did and what raised IndexError on the right answer.
    assert completed.stdout.strip() == "", (
        "completing another subject's object returned a state rather than NULL, which tells "
        f"the caller the id exists: {completed.stdout.strip()!r}"
    )

    # The owner's object is untouched by either attempt.
    state = owner(
        cluster,
        f"SELECT state FROM app_private.storage_objects WHERE id = '{identifier}'::uuid;",
    )
    assert state.stdout.strip().splitlines()[-1] == "pending"


# ---------------------------------------------------------------------------
# The cleanup lease (ADR 0104)
# ---------------------------------------------------------------------------


def test_an_expired_intent_becomes_collectable(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    """An abandoned upload converges rather than accumulating."""
    identifier = new_intent(cluster, subjects["first"], ttl=-60)

    swept = as_storage(cluster, "SELECT app_private.storage_expire_intents(100);")
    assert swept.returncode == 0, swept.stderr
    assert int(swept.stdout.strip().splitlines()[-1]) >= 1

    state = owner(
        cluster,
        f"SELECT state FROM app_private.storage_objects WHERE id = '{identifier}'::uuid;",
    )
    assert state.stdout.strip().splitlines()[-1] == "tombstoned"


def test_a_live_intent_is_not_swept(cluster: dict[str, Any], subjects: dict[str, str]) -> None:
    """The control for the sweep. A sweep that tombstoned everything would pass
    the test above and delete objects nobody had finished uploading."""
    identifier = new_intent(cluster, subjects["first"], ttl=3600)
    as_storage(cluster, "SELECT app_private.storage_expire_intents(100);")
    state = owner(
        cluster,
        f"SELECT state FROM app_private.storage_objects WHERE id = '{identifier}'::uuid;",
    )
    assert state.stdout.strip().splitlines()[-1] == "pending"


def test_a_claimed_object_is_not_claimed_twice(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    """The lease predicate, which is the correctness half of ADR 0104.

    Sequential rather than concurrent, and deliberately: this asserts the LEASE
    holds a claim across transaction boundaries, which is the property a row lock
    cannot provide because it is released at COMMIT. The concurrent case is the
    test below.
    """
    identifier = new_intent(cluster, subjects["first"])
    as_storage(
        cluster,
        f"SELECT app_private.storage_tombstone('{identifier}'::uuid, '{subjects['first']}'::uuid);",
    )

    first = as_storage(
        cluster, "SELECT id FROM app_private.storage_claim_cleanup_batch('worker-a', 10, 300);"
    )
    assert first.returncode == 0, first.stderr
    assert identifier in first.stdout

    # A separate statement, therefore a separate transaction. Any row lock the
    # first claim took is long gone; only the stored lease can refuse this.
    second = as_storage(
        cluster, "SELECT id FROM app_private.storage_claim_cleanup_batch('worker-b', 10, 300);"
    )
    assert second.returncode == 0, second.stderr
    assert identifier not in second.stdout, (
        "a second worker claimed an object whose lease is live. The lease predicate is the "
        "correctness mechanism and a row lock cannot stand in for it -- the provider DELETE "
        "happens outside this transaction (ADR 0104)"
    )


def test_an_expired_lease_is_reclaimed(cluster: dict[str, Any], subjects: dict[str, str]) -> None:
    """A crashed worker loses its hold by expiry, not by disconnection.

    The lease is set to a past instant directly, because the alternative is
    sleeping for the shortest lease the function will accept.
    """
    identifier = new_intent(cluster, subjects["first"])
    as_storage(
        cluster,
        f"SELECT app_private.storage_tombstone('{identifier}'::uuid, '{subjects['first']}'::uuid);",
    )
    as_storage(
        cluster,
        "SELECT id FROM app_private.storage_claim_cleanup_batch('worker-crashed', 10, 300);",
    )
    owner(
        cluster,
        "UPDATE app_private.storage_objects SET cleanup_lease_expires_at = now() - interval "
        f"'1 second' WHERE id = '{identifier}'::uuid;",
    )

    reclaimed = as_storage(
        cluster, "SELECT id FROM app_private.storage_claim_cleanup_batch('worker-next', 10, 300);"
    )
    assert identifier in reclaimed.stdout, (
        "an object whose lease expired was not reclaimed, so a worker that died mid-delete "
        "strands its object forever"
    )

    attempts = owner(
        cluster,
        "SELECT cleanup_attempts FROM app_private.storage_objects "
        f"WHERE id = '{identifier}'::uuid;",
    )
    assert int(attempts.stdout.strip().splitlines()[-1]) >= 2, (
        "cleanup_attempts did not move on the second claim. It is incremented on claim so "
        "an object that repeatedly kills its worker is visible"
    )


def test_finishing_requires_still_holding_the_lease(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    identifier = new_intent(cluster, subjects["first"])
    as_storage(
        cluster,
        f"SELECT app_private.storage_tombstone('{identifier}'::uuid, '{subjects['first']}'::uuid);",
    )
    as_storage(
        cluster, "SELECT id FROM app_private.storage_claim_cleanup_batch('worker-holder', 10, 300);"
    )

    impostor = as_storage(
        cluster,
        f"SELECT app_private.storage_finish_cleanup('{identifier}'::uuid, 'worker-other');",
    )
    assert impostor.stdout.strip().splitlines()[-1] == "f", (
        "a worker that does not hold the lease marked the object collected"
    )

    holder = as_storage(
        cluster,
        f"SELECT app_private.storage_finish_cleanup('{identifier}'::uuid, 'worker-holder');",
    )
    assert holder.stdout.strip().splitlines()[-1] == "t"

    # And it leaves the queue.
    again = as_storage(
        cluster, "SELECT id FROM app_private.storage_claim_cleanup_batch('worker-next', 10, 300);"
    )
    assert identifier not in again.stdout


def test_two_concurrent_workers_never_claim_the_same_object(
    cluster: dict[str, Any], subjects: dict[str, str]
) -> None:
    """The throughput half of ADR 0104, under real concurrency.

    `FOR UPDATE SKIP LOCKED` was measured on this server with a control before
    0014 was written: without it the second claimant blocks until `lock_timeout`
    kills it. Here the property asserted is the one that matters to the product
    -- two workers running at the same time partition the queue and never
    overlap.
    """
    identifiers = []
    for _ in range(6):
        identifier = new_intent(cluster, subjects["first"])
        as_storage(
            cluster,
            f"SELECT app_private.storage_tombstone('{identifier}'::uuid, "
            f"'{subjects['first']}'::uuid);",
        )
        identifiers.append(identifier)

    claimed: dict[str, list[str]] = {}

    def claim(worker: str) -> None:
        result = as_storage(
            cluster,
            f"SELECT id FROM app_private.storage_claim_cleanup_batch('{worker}', 3, 300);",
        )
        claimed[worker] = [
            line.strip() for line in result.stdout.strip().splitlines() if line.strip()
        ]

    threads = [threading.Thread(target=claim, args=(w,)) for w in ("worker-p", "worker-q")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    first = set(claimed.get("worker-p", []))
    second = set(claimed.get("worker-q", []))
    assert not first & second, (
        f"two workers claimed the same objects: {sorted(first & second)}. The claim would "
        "delete one object twice and, worse, two workers would be writing the same lease"
    )
    assert first or second, "neither worker claimed anything, so this asserts nothing"

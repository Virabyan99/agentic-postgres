"""Every released migration applies as the role that applies them in production.

**This test exists because the first Session 6 host deploy failed and no offline
proof could have predicted it** (D285). Migration 0012 died with

    ERROR: permission denied for function is_scope_set (42501)

because its `RESET ROLE` sat *above* the privileges block, so
`REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC` -- which requires
ownership of every function it touches -- ran as the **connected** role. On a
host that is `migration_user`, which owns nothing. 0011 already had the two
statements in the correct order; 0012 and 0013 did not.

**Why four sessions of green proofs missed it.** Every offline rig that applies
migrations does so with `psql -U postgres` -- as a SUPERUSER, which bypasses the
ownership check entirely (`test_auth_endpoints.py`, and the others like it).
`bin/migrate.py` on a host runs dbmate connected as `migration_user`. So the
proofs applied the right SQL as the wrong role, and reported success for a
migration that cannot be applied. ADR 0065 and 0066 named this class -- *a rig is
a second configuration of the product* -- and this is its fourth instance and its
most expensive: it was found by a deploy that took a live project down.

So this module is deliberately narrow: it does not test what the migrations
*do*. It tests only that they can be applied at all, by the role that has to
apply them, against the locked image. Everything else about the schema is
measured elsewhere, by rigs that may keep using a superuser.

The pre-state comes from `bin/postgres-bootstrap.py::build_statements` -- the
product's own bootstrap SQL -- rather than from a hand-written approximation of
it. A second copy of "what the migration user is granted" would drift from the
real one, and drifting in the permissive direction is exactly how this defect
survived.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every interpolated value below is a role or database name read from a rendered
# outputs document this repository produced, validated by the outputs schema.
# None of it is caller input, and a role name cannot be bound as a parameter --
# the same judgement tests/deployment/conftest.py records.
import importlib.util
import json
import secrets
import subprocess
import time
import uuid
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    bootstrap_statements,
    dev_environment,
    migrations,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"


def _lock() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() and not name.strip().startswith("#"):
            values[name.strip()] = value.strip()
    return values


def _docker(*args: str, stdin: str | None = None, timeout: int = 180):
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=False,
        input=stdin,
        timeout=timeout,
    )


def _bootstrap_module() -> Any:
    specification = importlib.util.spec_from_file_location(
        "apg_postgres_bootstrap", REPO_ROOT / "bin" / "postgres-bootstrap.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cluster() -> Any:
    """A cluster on the locked image, with the two roles a deploy establishes."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    name = f"apg-migration-role-{secrets.token_hex(4)}"
    database = document["database"]["name"]
    password = secrets.token_hex(24)

    started = _docker(
        "run", "-d", "--name", name,
        "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
        _lock()["POSTGRES_IMAGE"],
    )  # fmt: skip
    if started.returncode != 0:
        pytest.skip(f"cannot start the locked cluster: {started.stderr.strip()[:200]}")

    try:
        # Two consecutive successes: the initdb server answers once and goes
        # away, and a rig that took the first answer would race it.
        rounds = 0
        for _ in range(90):
            probe = _docker("exec", name, "pg_isready", "-U", "postgres", timeout=30)
            rounds = rounds + 1 if probe.returncode == 0 else 0
            if rounds >= 2:
                break
            time.sleep(1)
        assert rounds >= 2, "the cluster never became ready"

        # **The product's own statements, not this fixture's** (Session 22 Run
        # 3, ADR 0203). `apg dev up` builds this same pre-state from the same
        # three functions, so the cluster this module measures and the cluster a
        # developer gets are established identically. That is what makes "the
        # product path is the fixture path" a fact rather than a claim: if
        # `activation_statements` ever activated a third role, or dropped
        # `INHERIT FALSE` from the owner grant -- the option that makes `SET
        # LOCAL ROLE` the only route to the owner's authority, and therefore the
        # option D285's defect depends on -- this module would measure the
        # weaker thing and say so.
        setup = dev_environment.role_statements(document)
        setup += dev_environment.activation_statements(document, password, password)
        setup += dev_environment.owner_grant_statements(document)
        setup += [f'CREATE DATABASE "{database}" OWNER "{roles["object_owner"]}";']
        result = _docker(
            "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
            stdin="\n".join(setup),
        )  # fmt: skip
        assert result.returncode == 0, result.stderr

        result = _docker(
            "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", database,
            "-c", dev_environment.extensions_schema_statement(document),
        )  # fmt: skip
        assert result.returncode == 0, result.stderr

        yield {
            "name": name,
            "database": database,
            "document": document,
            "roles": roles,
            "password": password,
        }
    finally:
        _docker("rm", "-f", name, timeout=60)


def _apply_as_migration_user(
    cluster: dict[str, Any], body: str
) -> subprocess.CompletedProcess[str]:
    """One migration, over TCP as the migration user, in one transaction.

    Over TCP with a password rather than `-U role` on the socket, because the
    socket would use peer authentication as root and could connect as a role
    this test has not established a password for -- which would quietly test a
    different login path from the one dbmate uses.
    """
    return _docker(
        "exec", "-i", "-e", f"PGPASSWORD={cluster['password']}", cluster["name"],
        "psql", "-U", cluster["roles"]["migration_user"], "-h", "127.0.0.1",
        "-d", cluster["database"], "-qtA", "-v", "ON_ERROR_STOP=1", "-1", "-f", "-",
        stdin=body,
    )  # fmt: skip


def _apply_every_set(cluster: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Apply every set this project applies, as the migration user. `(applied, planned)`.

    **A function rather than a fixture**, deliberately. An assertion that fails
    inside a fixture is reported as an ERROR, and a reader that cannot tell an
    ERROR from a FAILED reports a broken fixture as a kill (D386) -- for this
    module, the one whose failure means a deploy would take a live project down
    (D285), that distinction is the whole signal. Called from a test, a failure
    here is a FAILED with the message the caller needs.

    It exists because two tests need the schema applied and there must be ONE
    applier (question 5: two paths to one state is the defect class this project
    keeps producing). The second caller is the grant proof at the bottom of this
    file, which applies nothing when the schema is already there -- so in a
    whole-module run this runs exactly once, and in a node-id selection of
    either test it runs for that test.
    """
    document = cluster["document"]

    # ADR 0198. EVERY set this project applies, release first -- and this is the
    # module where that matters most, because it is the one that exists after a
    # deploy took a live project down (D285). A project's set runs through the
    # same migration plane as the same `migration_user`, which holds NOINHERIT
    # and reaches the owner only through `SET LOCAL ROLE`; if it is not applied
    # here, by that role, then nothing proves it can be applied at all.
    #
    # Every offline rig that applies migrations as a superuser bypasses the
    # ownership check entirely, which is exactly how D285's defect survived four
    # sessions of green proofs. Applying a tenant's SQL only under a superuser
    # would recreate that hole for the half of the schema an adopter writes.
    planned = []
    for migration_set in migrations.sets_for(document):
        set_manifest = migration_set.load_manifest()
        planned += [
            (entry, set_manifest, migration_set.root) for entry in set_manifest["migrations"]
        ]
    assert planned, "no migrations at all"
    assert any(migration_set.is_project for migration_set in migrations.sets_for(document)), (
        "the fixture project declares no migration set, so this module applies only the "
        "release's SQL as the migration user and a tenant's set is proved by nothing "
        "(ADR 0198). Re-render the fixture from project.example.yaml."
    )

    # The statements are imported from `agentic_postgres.bootstrap_statements`
    # since Session 22 Run 3; `_bootstrap_module` stays because
    # `test_a_superuser_is_not_what_the_host_uses` and the sibling modules load
    # the COMMAND by path, and what they are checking is that the command still
    # re-exports what it published (ADR 0175).
    assert _bootstrap_module().build_statements is bootstrap_statements.build_statements, (
        "bin/postgres-bootstrap.py no longer re-exports the statements it used to "
        "define, so a reader that loads it by path sees a different function"
    )

    # **The bootstrap FIRST, which is where the deploy puts it** (Session 22
    # Run 3, D1185). `bin/deploy-project.py` step 6 runs
    # `postgres-bootstrap.sh --apply` and THEN `migrate.sh up`; this module used
    # to apply it after the first migration, on the belief that it needed
    # `app_private` to exist. Rig 22b measured the belief and it is false: the
    # deploy's order applies 32 of 32, because the bootstrap's statements are
    # written to be the first thing a fresh cluster sees -- which they have to
    # be, since on a host they run before any migration has ever applied.
    #
    # The order became load-bearing here the moment each migration started
    # carrying its own `schema_migrations` row, which is the row dbmate writes:
    # the migration user cannot write into `app_private` until the bootstrap
    # grants it, so at the old position every migration failed on its own row
    # (0 of 32 in rig 22b's control). One order, and it is production's.
    statements = bootstrap_statements.build_statements(document, str(uuid.uuid4()))
    result = _docker(
        "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", cluster["database"],
        stdin="\n".join(statements),
    )  # fmt: skip
    assert result.returncode == 0, (
        f"the product's own bootstrap statements did not apply: {result.stderr[:400]}"
    )

    applied: list[str] = []
    for entry, manifest, root in planned:
        payload = migrations.render_migration(entry, manifest, document, root)
        # The product's own transformation, and the row it appends is what makes
        # this cluster's `schema_migrations` the shape a deployment carries --
        # the same function `apg dev up` sends (ADR 0203).
        body = dev_environment.transaction_body(payload, entry["version"])

        result = _apply_as_migration_user(cluster, body)
        assert result.returncode == 0, (
            f"{entry['name']} cannot be applied by "
            f"{cluster['roles']['migration_user']}, which is the role dbmate connects "
            f"as on a host.\n{result.stderr.strip()[:600]}\n"
            f"(applied before this: {applied})"
        )
        applied.append(entry["name"])

    return applied, [entry["name"] for entry, _, _ in planned]


def test_every_released_migration_applies_as_the_migration_user(cluster: dict[str, Any]) -> None:
    """The whole released set, in order, as the role dbmate connects with.

    Goes red if: a migration's `RESET ROLE` moves above a statement that needs
    ownership; a `GRANT` or `REVOKE` is added after the reset; or an object is
    created outside the `SET LOCAL ROLE` and so ends up owned by the migration
    user.

    The bootstrap pre-state is applied where the deploy applies it -- after the
    schema exists and before dbmate runs -- using the product's own
    `build_statements`, so the grants under test are the deployed ones.
    """
    applied, planned = _apply_every_set(cluster)
    assert len(applied) == len(planned)


def test_a_superuser_is_not_what_the_host_uses(cluster: dict[str, Any]) -> None:
    """The control, and the reason the test above is not redundant.

    If the migration user and the superuser were equivalent here, the test above
    would measure nothing beyond what the existing rigs already do. They are not
    equivalent, and this asserts the difference is real on this server: the
    migration user does not own the functions, does not inherit the owner's
    rights, and reaches them only by `SET LOCAL ROLE`.

    Without this, a future change that granted the migration user ownership --
    or superuser -- would make the test above pass for a reason that has nothing
    to do with the migrations being correct.
    """
    roles = cluster["roles"]
    probe = _docker(
        "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", cluster["database"], "-c",
        "SELECT rolsuper::text FROM pg_roles "
        f"WHERE rolname = '{roles['migration_user']}'",
    )  # fmt: skip
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "false", (
        "the migration user is a superuser in this rig, so it bypasses every ownership "
        "check and the test above proves nothing"
    )

    # The MEMBERSHIP option, from `pg_auth_members`, not `pg_roles.rolinherit`.
    #
    # The first version of this control read `rolinherit` and failed against a
    # correct rig: `rolinherit` is a property of the role itself and defaults to
    # true, while `GRANT ... WITH INHERIT FALSE` records its option on the
    # membership row. D266 measured exactly this -- the three options record
    # `admin=f inherit=f set=t` -- and reading the wrong catalog would have made
    # this control unsatisfiable by any correct deployment.
    membership = _docker(
        "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", cluster["database"], "-c",
        "SELECT m.admin_option::text || '|' || m.inherit_option::text || '|' "
        "|| m.set_option::text FROM pg_auth_members m "
        "JOIN pg_roles member ON member.oid = m.member "
        "JOIN pg_roles grantee ON grantee.oid = m.roleid "
        f"WHERE member.rolname = '{roles['migration_user']}' "
        f"AND grantee.rolname = '{roles['object_owner']}'",
    )  # fmt: skip
    assert membership.returncode == 0, membership.stderr
    assert membership.stdout.strip() == "false|false|true", (
        f"the migration user's membership of the object owner records "
        f"{membership.stdout.strip()!r}, not 'false|false|true'. With INHERIT TRUE it "
        "would hold the owner's rights merely by connecting (D266), and the test above "
        "would pass without `SET LOCAL ROLE` doing anything"
    )

    owner = _docker(
        "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", cluster["database"], "-c",
        "SELECT pg_get_userbyid(proowner) FROM pg_proc p JOIN pg_namespace n "
        "ON n.oid = p.pronamespace WHERE n.nspname = 'app_private' "
        "AND p.proname = 'is_scope_set'",
    )  # fmt: skip
    assert owner.returncode == 0, owner.stderr
    assert owner.stdout.strip() == roles["object_owner"], (
        f"is_scope_set is owned by {owner.stdout.strip()!r}; the defect this module "
        "catches depends on it being owned by the object owner and not by the migration "
        "user"
    )


def test_the_example_sets_grants_reach_the_agent_roles_and_not_anon(
    cluster: dict[str, Any],
) -> None:
    """D1156: a tenant's tool is refused by the database until the tenant grants.

    **It applies the sets if they are not applied**, through the same
    `_apply_every_set` the proof above uses, and does nothing when they are. The
    first version of this test read the state that proof left behind, and Run
    2's battery killed it for the wrong reason: selecting the two node ids on
    one command line put this one first, and it went red on a missing relation
    rather than on a missing grant. The gate selects claim proofs by node id, so
    that is not a hypothetical ordering -- it is how this test would have been
    run (D1181).

    What it proves. Session 21 put `note_embeddings:read` and
    `note_embeddings:write` in the derived vocabulary and the compiled roster
    (ADR 0200, ADR 0201), and the tool was served and then refused upstream: a
    capability compiler reads a reviewed surface and a snapshot is captured as
    `api_documentation`, so neither can see a GRANT. Migration 20260914120002
    is the tenant's half. The release's own grants (`api.notes` to
    `agent_reader`, migration 0004) are the control for "the mechanism works";
    `anon` is the control for "the grant is to two named roles and not to the
    world".

    Goes red if: the second migration stops being applied, its two GRANT lines
    lose a role, the placeholders stop resolving to the agent roles, or the view
    or the function is republished without them.
    """
    roles = cluster["roles"]

    def privilege(role: str, kind: str, target: str) -> str:
        function = "has_table_privilege" if kind == "table" else "has_function_privilege"
        access = "SELECT" if kind == "table" else "EXECUTE"
        result = _docker(
            "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", cluster["database"], "-c",
            f"SELECT {function}({migrations.quote_literal(role)}, "
            f"{migrations.quote_literal(target)}, '{access}')::text",
        )  # fmt: skip
        assert result.returncode == 0, (
            f"{function}({role}, {target}) could not be asked: {result.stderr.strip()[:300]}"
        )
        return result.stdout.strip()

    def published() -> bool:
        probe = _docker(
            "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", cluster["database"], "-c",
            "SELECT to_regclass('api.note_embeddings') IS NOT NULL",
        )  # fmt: skip
        return probe.returncode == 0 and probe.stdout.strip() == "t"

    if not published():
        _apply_every_set(cluster)
    assert published(), (
        "api.note_embeddings does not exist after every set was applied, so this "
        "cluster does not carry the project's own migrations at all and the grants "
        "below would be measuring nothing"
    )

    assert privilege(roles["agent_reader"], "table", "api.note_embeddings") == "true"
    assert privilege(roles["agent_writer"], "table", "api.note_embeddings") == "true"
    assert (
        privilege(
            roles["agent_writer"],
            "function",
            "api.set_note_embedding(uuid, extensions.vector)",
        )
        == "true"
    )

    # The controls. `anon` is granted nothing by the set, and the release's own
    # grant to the reader is what says the mechanism under test is privilege and
    # not absence.
    assert privilege(roles["anon"], "table", "api.note_embeddings") == "false", (
        "anon can select the project's view. The set grants it to the two agent "
        "roles, the authenticated role and the documentation role, and to nobody else"
    )
    assert privilege(roles["agent_reader"], "table", "api.notes") == "true", (
        "the release's own grant of api.notes to the agent reader is absent, so the "
        "assertions above would read 'true' for a reason that has nothing to do with "
        "this project's migration"
    )

    # **And the TABLE the view reads** (D1189). `api.note_embeddings` is
    # declared `security_invoker = true`, so PostgreSQL checks the CALLER's
    # privileges on `app.note_embeddings` -- and 20260914120001 granted only the
    # view. Every caller was refused with `permission denied for table
    # note_embeddings`: not the view it had been granted, the table underneath.
    # Granting the view and asserting only the view is how that survived two
    # sessions, so the reading below is what this test now ends on.
    for role_key in ("authenticated", "agent_reader", "agent_writer", "api_documentation"):
        assert privilege(roles[role_key], "table", "app.note_embeddings") == "true", (
            f"{role_key} may select the VIEW api.note_embeddings and not the TABLE it "
            "reads. A security_invoker view checks the caller against what it reads, so "
            "this is a grant that grants nothing (D1189)"
        )
    assert privilege(roles["anon"], "table", "app.note_embeddings") == "false"

    # The reading itself, as the request role a signed-in caller becomes. A
    # privilege bit is what the catalog says; this is what PostgreSQL does.
    read = _docker(
        "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", cluster["database"], "-c",
        f'SET ROLE "{roles["authenticated"]}"; '
        "SELECT count(*)::text FROM api.note_embeddings",
    )  # fmt: skip
    assert read.returncode == 0, (
        f"a signed-in caller cannot read this project's own view: "
        f"{read.stderr.strip()[:300]}. The grant is the point of the migration under test"
    )

    # The control, in the same test: the release's own view reads the same way,
    # so a failure above is this project's grant and not the schema's shape.
    control = _docker(
        "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", cluster["database"], "-c",
        f'SET ROLE "{roles["authenticated"]}"; SELECT count(*)::text FROM api.notes',
    )  # fmt: skip
    assert control.returncode == 0, control.stderr

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

from agentic_postgres import REPO_ROOT, migrations

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

        setup = [f'CREATE ROLE "{role}" NOLOGIN;' for role in sorted(set(roles.values()))]
        setup += [
            f"ALTER ROLE \"{roles['migration_user']}\" LOGIN PASSWORD '{password}';",
            # The three options the bootstrap plane sets (D266). INHERIT FALSE
            # is what makes `SET LOCAL ROLE` the only way the migration user
            # reaches the owner's authority -- which is precisely the mechanism
            # under test here.
            f'GRANT "{roles["object_owner"]}" TO "{roles["migration_user"]}" '
            "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;",
            f'CREATE DATABASE "{database}" OWNER "{roles["object_owner"]}";',
        ]
        result = _docker(
            "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
            stdin="\n".join(setup),
        )  # fmt: skip
        assert result.returncode == 0, result.stderr

        result = _docker(
            "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", database,
            "-c", f'CREATE SCHEMA extensions AUTHORIZATION "{roles["object_owner"]}"',
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
    manifest = migrations.load_manifest()
    document = cluster["document"]
    released = manifest["migrations"]
    assert released, "no released migrations"

    bootstrap = _bootstrap_module()

    applied: list[str] = []
    for index, entry in enumerate(released):
        payload = migrations.render_migration(entry, manifest, document)
        body = payload.split("-- migrate:down", 1)[0].replace("-- migrate:up", "", 1)

        # `postgres-bootstrap.py` runs between the schema existing and dbmate
        # being invoked. Its statements are idempotent by construction, so they
        # are applied once, after the first migration creates `app_private`.
        if index == 1:
            statements = bootstrap.build_statements(document, str(uuid.uuid4()))
            result = _docker(
                "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-d", cluster["database"],
                stdin="\n".join(statements),
            )  # fmt: skip
            assert result.returncode == 0, (
                f"the product's own bootstrap statements did not apply: {result.stderr[:400]}"
            )

        result = _apply_as_migration_user(cluster, body)
        assert result.returncode == 0, (
            f"{entry['name']} cannot be applied by "
            f"{cluster['roles']['migration_user']}, which is the role dbmate connects "
            f"as on a host.\n{result.stderr.strip()[:600]}\n"
            f"(applied before this: {applied})"
        )
        applied.append(entry["name"])

    assert len(applied) == len(released)


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

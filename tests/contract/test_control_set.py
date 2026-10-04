"""The control project's own migration set (CTL-SET-001; ADR 0251, ADR 0252).

`projects/control/` holds the control plane's tables. It is linted like every
set, with the one facility-gated widening (D2046, D2073), and applied here to a
real cluster from the locked image -- the release's migrations first, then this
set -- so every property below is read from PostgreSQL's own catalog and from
calls made as the role the control mode connects as, never from the SQL text.

Design G (rig 37b): every table forces row security; the definer functions
scope rows by the caller and by an organisation scope set only after the
caller's own membership was read, and reset on entry (D2074).
"""

# ruff: noqa: S608 -- every interpolated value is a uuid or a key this module
# generated, run against a throwaway cluster.

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import control_cluster as cc
import pytest

from agentic_postgres import REPO_ROOT, config, migrations, rendering

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

CONTROL_SET = REPO_ROOT / "projects" / "control"

TABLES = {
    "control_accounts",
    "control_organizations",
    "control_memberships",
    "control_invitations",
    "control_totp",
    "control_keys",
    "control_projects",
    "control_operations",
}
#: Every function the identity service may execute, and no other (ADR 0251).
GRANTED = {
    "control_record_account",
    "control_caller_roles",
    "control_create_organization",
    "control_list_organizations",
    "control_get_organization",
    "control_list_members",
    "control_set_member_role",
    "control_mint_invitation",
    "control_list_invitations",
    "control_revoke_invitation",
    "control_accept_invitation",
    "control_totp_begin",
    "control_totp_seed",
    "control_totp_confirm",
    "control_totp_accept_step",
    "control_mint_key",
    "control_list_keys",
    "control_revoke_key",
    "control_key_lookup",
    "control_key_used",
    "control_remove_member",
    "control_list_projects",
    "control_get_project",
    "control_list_operations",
    "control_get_operation",
}
#: The operator's three, run by root through `bin/control.sh` (D2068).
OPERATOR = {"control_adopt_project", "control_registry_rows", "control_totp_reset"}
#: The helpers that run only inside the functions above.
HELPERS = {"control_enter", "control_require_role", "control_role_rank"}


def _set() -> migrations.MigrationSet:
    return migrations.MigrationSet(label="project", root=CONTROL_SET / "migrations")


@pytest.fixture(scope="module")
def cluster() -> Iterator[cc.ControlCluster]:
    try:
        with cc.control_cluster() as started:
            yield started
    except RuntimeError as error:
        pytest.skip(str(error))


def _account(cluster: cc.ControlCluster, label: str) -> str:
    user = str(uuid.uuid4())
    cluster.as_service(
        f"SELECT app.control_record_account('{user}', 'probe-{label}-{user[:8]}', '{label}')"
    )
    return user


def _organization(cluster: cc.ControlCluster, user: str, name: str) -> str:
    return cluster.as_service(f"SELECT app.control_create_organization('{user}', '{name}')")[0]


# ---------------------------------------------------------------------------
# The lint (no cluster)
# ---------------------------------------------------------------------------


def test_the_set_lints_only_with_the_control_facility() -> None:
    """The committed set passes with the facility and is refused without it,
    naming the source -- and the example manifest that names it enables it."""
    migrations.lint_project_set(_set(), control=True)
    with pytest.raises(migrations.ProjectSetError, match=r"database\.roles\.auth_service"):
        migrations.lint_project_set(_set())
    manifest = config.load_project_manifest(cc.CONTROL_EXAMPLE)
    assert config.control_enabled(manifest) is True
    assert config.project_migration_set(manifest) == "projects/control"


def test_auth_service_is_refused_outside_a_function_grant(tmp_path: Path) -> None:
    """A copy of the committed set with ONE extra table grant to the identity
    service is refused even with the facility; the committed set, in the same
    invocation, passes (D499)."""
    copied = tmp_path / "control"
    shutil.copytree(CONTROL_SET, copied)
    template = copied / "migrations" / "templates" / "0001-control-identity.sql"
    text = template.read_text(encoding="utf-8")
    anchor = "-- migrate:down"
    assert text.count(anchor) == 1
    template.write_text(
        text.replace(
            anchor, "GRANT SELECT ON app.control_accounts TO {{auth_service}};\n\n" + anchor
        ),
        encoding="utf-8",
    )
    candidate = migrations.MigrationSet(label="project", root=copied / "migrations")
    with pytest.raises(migrations.ProjectSetError, match=r"\{\{auth_service\}\}"):
        migrations.lint_project_set(candidate, control=True)
    migrations.lint_project_set(_set(), control=True)


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------


def test_every_control_table_forces_row_level_security(cluster: cc.ControlCluster) -> None:
    rows = cluster.query(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'app' AND c.relkind = 'r' AND c.relname LIKE 'control\\_%' "
        "ORDER BY 1"
    )
    found = {row.split("|")[0]: row.split("|")[1:] for row in rows}
    assert set(found) == TABLES, sorted(found)
    assert all(flags == ["t", "t"] for flags in found.values()), found


def _executable_by(cluster: cc.ControlCluster, role: str) -> set[str]:
    rows = cluster.query(
        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'app' AND p.proname LIKE 'control\\_%' "
        f"AND has_function_privilege('{role}', p.oid, 'EXECUTE')"
    )
    return set(rows)


def test_no_request_role_can_execute_a_control_function(cluster: cc.ControlCluster) -> None:
    """No control function is executable by PUBLIC or by any role but the
    identity service (and the owner, which owns them): not a request role, not
    an agent role, not the documentation role, not the runtime."""
    public = cluster.query(
        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'app' AND p.proname LIKE 'control\\_%' "
        "AND (p.proacl IS NULL OR EXISTS (SELECT 1 FROM aclexplode(p.proacl) a "
        "WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'))"
    )
    assert public == [], f"executable by PUBLIC: {public}"
    for suffix, role in sorted(cluster.roles.items()):
        if suffix in {"auth_service", "object_owner"}:
            continue
        assert _executable_by(cluster, role) == set(), suffix
    in_api = cluster.query(
        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'api' AND p.proname LIKE 'control\\_%'"
    )
    assert in_api == [], "a control function in api would be published by PostgREST"


def test_the_operator_functions_are_executable_by_no_role(cluster: cc.ControlCluster) -> None:
    """The identity service executes exactly the granted set: not the operator's
    three (root's, through bin/control.sh) and not the helpers."""
    assert _executable_by(cluster, cluster.auth_role) == GRANTED
    every = set(
        cluster.query(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'app' AND p.proname LIKE 'control\\_%'"
        )
    )
    assert every == GRANTED | OPERATOR | HELPERS, sorted(every ^ (GRANTED | OPERATOR | HELPERS))
    for suffix, role in sorted(cluster.roles.items()):
        if suffix == "object_owner":
            continue
        assert not (_executable_by(cluster, role) & (OPERATOR | HELPERS)), suffix


# ---------------------------------------------------------------------------
# Scoping, as the identity service calls it
# ---------------------------------------------------------------------------


def test_a_caller_sees_only_their_own_organisations(cluster: cc.ControlCluster) -> None:
    one, two, three = (_account(cluster, label) for label in ("one", "two", "three"))
    a = _organization(cluster, one, "alpha")
    b = _organization(cluster, two, "bravo")

    assert cluster.as_service(f"SELECT id FROM app.control_list_organizations('{one}')") == [a]
    assert cluster.as_service(f"SELECT id FROM app.control_list_organizations('{two}')") == [b]
    assert cluster.as_service(
        f"SELECT organization_id, role FROM app.control_caller_roles('{one}')"
    ) == [f"{a}|owner"]

    # A member arrives by invitation and then reads the member list.
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex
    cluster.as_service(
        f"SELECT app.control_mint_invitation('{one}', '{a}', 'member', '{token_hash}', "
        "now() + interval '72 hours')"
    )
    accepted = cluster.as_service(
        "SELECT organization_id, role FROM "
        f"app.control_accept_invitation('{token_hash}', '{three}')"
    )
    assert accepted == [f"{a}|member"]
    members = cluster.as_service(f"SELECT user_id FROM app.control_list_members('{three}', '{a}')")
    assert set(members) == {one, three}

    # D2074: in ONE transaction, a member's call scopes organisation A; the
    # next call, by someone outside it, inherits nothing.
    rows = cluster.as_service(
        f"SELECT count(*) FROM app.control_list_members('{one}', '{a}');\n"
        f"SELECT id FROM app.control_list_organizations('{two}');"
    )
    assert rows == ["2", b], rows
    refusal = cluster.refused(
        f"SELECT count(*) FROM app.control_list_members('{one}', '{a}');\n"
        f"SELECT count(*) FROM app.control_list_members('{two}', '{a}');"
    )
    assert "AP404: not_found" in refusal


def test_a_non_member_sees_nothing(cluster: cc.ControlCluster) -> None:
    owner, outsider = _account(cluster, "owner"), _account(cluster, "outsider")
    org = _organization(cluster, owner, "charlie")
    key = f"probe-{uuid.uuid4().hex[:6]}-dev"
    cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{org}', 'probe', 'dev', "
        "'probe-dev.test', '1.15.0', 'deadbeef')"
    )

    assert cluster.as_service(f"SELECT key FROM app.control_get_project('{owner}', '{key}')") == [
        key
    ]
    assert (
        cluster.as_service(f"SELECT key FROM app.control_get_project('{outsider}', '{key}')") == []
    )
    assert (
        cluster.as_service(f"SELECT key FROM app.control_list_projects('{outsider}', '{org}')")
        == []
    )
    assert (
        cluster.as_service(f"SELECT id FROM app.control_get_organization('{outsider}', '{org}')")
        == []
    )
    assert "AP404: not_found" in cluster.refused(
        f"SELECT * FROM app.control_list_members('{outsider}', '{org}')"
    )
    # A foreign organisation and a missing one give one answer (D2053).
    assert "AP404: not_found" in cluster.refused(
        f"SELECT * FROM app.control_list_members('{outsider}', '{uuid.uuid4()}')"
    )
    # And the identity service itself reads no table directly.
    assert "permission denied" in cluster.refused("SELECT count(*) FROM app.control_memberships")


# ---------------------------------------------------------------------------
# The example renders (D2089: the first full render of a control project)
# ---------------------------------------------------------------------------


def test_the_control_example_renders_as_the_control_plane() -> None:
    directory = rendering.render_project(cc.CONTROL_EXAMPLE, cc.CAPABILITIES)
    try:
        import json

        outputs = json.loads((directory / "outputs.json").read_text(encoding="utf-8"))
        assert outputs["control"] == {"enabled": True}
        assert outputs["routes"]["control"] == "https://fixture-control-dev.test/api/v1"
        assert outputs["migrations"]["project_set"]["root"] == "projects/control"
        assert outputs["migrations"]["project_set"]["count"] == 3
        assert outputs["storage"]["enabled"] is False
        values = dict(
            line.split("=", 1)
            for line in (directory / "compose.env").read_text(encoding="utf-8").splitlines()
            if "=" in line and not line.startswith("#")
        )
        assert values["AUTH_APP_MODE"] == "control"
        assert values["CONTROL_ROUTE_PATH"] == "/api/v1"
        assert values["API_CONTROL_PATH"] == "/api"
        rendered_set = sorted(p.name for p in (directory / "migrations-project").glob("*.sql"))
        assert len(rendered_set) == 3, rendered_set
    finally:
        # CLAUDE.md §1: a proof that renders deletes what it published.
        shutil.rmtree(directory, ignore_errors=True)

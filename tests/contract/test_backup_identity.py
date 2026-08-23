"""Activating `backup_user`, Session 10 Run 5 (ADR 0148).

`backup_user` has been one of the thirteen derived roles since Session 3 --
NOLOGIN, null verifier, no privilege, no credential. This module covers what
Run 5 gives it: five privileges, a credential, a ceiling, and `CONNECT`.

**Every number and every grant here was measured** against the pinned PG 18
digest and the Run 4 derived image (rig 5, eight arms, each with a control).
ADR 0148 carries the arms; what is asserted here is that the product issues what
was measured, which is a different claim from "the measurement was right".

What is deliberately NOT here: anything that needs a cluster. The privileges
reaching a real catalog, and pgBackRest actually running as this role, belong to
the host trip -- `REC-WAL-001` and the Run 6 command. A module that ran the
grants against a container it started itself would prove the grants are
issuable, which nobody doubts, and not that this program issues them.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, config, output_migrations, secrets_contract

pytestmark = [pytest.mark.contract, pytest.mark.p0]

INSTANCE_UUID = "6f1d2f7a-6f2c-4a3f-9a1e-2f0b7c9d1e35"


@pytest.fixture
def bootstrap() -> Any:
    """`bin/postgres-bootstrap.py`, imported rather than run (D185's caveat)."""
    specification = importlib.util.spec_from_file_location(
        "apg_postgres_bootstrap_backup", REPO_ROOT / "bin" / "postgres-bootstrap.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture
def document() -> dict[str, Any]:
    """A version 7 rendered document, migrated from the committed v5 render.

    `test_bootstrap_statements.py`'s fixture, and migrated rather than rendered
    for its stated reason: `rendering.render_project` publishes to
    `.generated/<key>` derived from the manifest rather than to a path the
    caller chose, and a test that leaves a render behind fails the gate for
    whoever runs the suite next.

    v7 is enough because `build_statements` reads roles, the database name, the
    project key and the compose name, all of which have been stable since then.
    """
    v5 = json.loads((REPO_ROOT / "tests" / "fixtures" / "outputs-v5.json").read_text("utf-8"))
    v6 = output_migrations.migrate_v5_to_v6(
        v5,
        documentation_role=v5["database"]["roles"]["app_runtime"].removesuffix("app_runtime")
        + "api_documentation",
    )
    roles = v6["database"]["roles"]
    return output_migrations.migrate_v6_to_v7(
        v6,
        statement_timeouts={
            roles["app_runtime"]: "30s",
            roles["anon"]: "2s",
            roles["authenticated"]: "5s",
        },
    )


def _statements(bootstrap: Any, document: dict[str, Any]) -> list[str]:
    return bootstrap.build_statements(document, INSTANCE_UUID)


# ---------------------------------------------------------------------------
# The five privileges
# ---------------------------------------------------------------------------


def test_the_backup_role_is_granted_exactly_the_five_measured_privileges(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """The necessity matrix, asserted as a set (rig 5 arm G, ADR 0148).

    Five, because `pgbackrest check` needs two that `pgbackrest backup` does
    not, and the deploy's step 6c and both timers run `check`. Arm G revoked
    each in turn and every one broke something; the control -- all five restored
    -- came back green in the same invocation.

    **Asserted as equality rather than containment.** A superset is not a
    harmless margin here: a grant that can be revoked with nothing failing is a
    privilege this project measured itself into not needing, and `pg_monitor`
    was the tempting shortcut that would have carried three of them.
    """
    role = document["database"]["roles"]["backup_user"]
    statements = _statements(bootstrap, document)

    granted = {
        statement.split(" ON FUNCTION ", 1)[1].split(" TO ", 1)[0].strip()
        for statement in statements
        if statement.startswith("GRANT EXECUTE ON FUNCTION") and role in statement
    }
    assert granted == set(bootstrap.BACKUP_FUNCTION_GRANTS), (
        f"the backup role is granted EXECUTE on {sorted(granted)}, not on "
        f"{sorted(bootstrap.BACKUP_FUNCTION_GRANTS)}. Each of those four was measured "
        "load-bearing by revoking it and watching a command fail; a fifth would be one "
        "nothing measured"
    )

    assert bootstrap.BACKUP_FUNCTION_GRANTS == (
        "pg_catalog.pg_backup_start(text, boolean)",
        "pg_catalog.pg_backup_stop(boolean)",
        "pg_catalog.pg_create_restore_point(text)",
        "pg_catalog.pg_switch_wal()",
    ), (
        "the measured privilege set has changed. `pg_create_restore_point` and "
        "`pg_switch_wal` are needed by `check` alone and `pg_backup_start`/`stop` by "
        "`backup` alone -- dropping either pair leaves a role that works until the "
        "other command runs (D541)"
    )


def test_the_settings_membership_is_a_role_grant_and_not_a_function_grant(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """`pg_read_all_settings` is a role, and the syntax is the load-bearing part.

    Measured (rig 5 arm C): a non-superuser is refused this one with
    `permission denied to grant role "pg_read_all_settings"` / `Only roles with
    the ADMIN option ... may grant this role`, while the four function grants are
    refused with `permission denied for function`. Two refusals, one plane
    boundary -- which is why all five are issued here.

    Its absence does not surface as a permission error at all (D542):
    `pg_settings` OMITS a restricted row rather than nulling it, so pgBackRest
    sees four rows where it asked for five and reports `unable to select some
    rows from pg_settings`.
    """
    role = document["database"]["roles"]["backup_user"]
    statements = _statements(bootstrap, document)

    grants = [
        statement
        for statement in statements
        if bootstrap.BACKUP_SETTINGS_ROLE in statement and role in statement
    ]
    assert len(grants) == 1, (
        f"expected exactly one grant of {bootstrap.BACKUP_SETTINGS_ROLE}, found {grants}"
    )
    statement = grants[0]
    assert "ON FUNCTION" not in statement, (
        "`pg_read_all_settings` is being granted as a function privilege. It is a role, "
        "and `GRANT EXECUTE ON FUNCTION pg_read_all_settings` does not name anything"
    )
    assert "ADMIN FALSE" in statement and "INHERIT TRUE" in statement, (
        f"the membership is {statement!r}. INHERIT TRUE is load-bearing and is the "
        "OPPOSITE of the authenticator's: pgBackRest issues no SET ROLE, it connects and "
        "reads pg_settings, so a membership it had to assume is one it would never use"
    )
    assert "SET FALSE" in statement, (
        f"the membership is {statement!r}; the backup identity has no reason to become "
        "pg_read_all_settings, and SET TRUE would be reach nothing measured asked for"
    )


def test_the_backup_role_may_connect_to_the_database(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """`REVOKE ALL ... FROM PUBLIC` means this list is exhaustive, not additive.

    D291 is the record of what omission costs: `auth_service` reached a host with
    every privilege it needed and no `CONNECT`, and failed with `FATAL:
    permission denied for database`. Two more instances followed in Session 7.
    A privilege granted to a role that cannot connect is inert in the most
    expensive possible way -- it looks correct in the catalog.
    """
    role = document["database"]["roles"]["backup_user"]
    connect = [s for s in _statements(bootstrap, document) if s.startswith("GRANT CONNECT ON DATA")]
    assert len(connect) == 1, f"expected one CONNECT grant, found {len(connect)}"
    assert f'"{role}"' in connect[0], (
        f"{role} is not in the CONNECT grant. Every privilege above is inert without it, "
        "and the failure is `FATAL: permission denied for database` at the first "
        "archive-push rather than anywhere near this list (D291)"
    )


def test_the_privileges_are_issued_whether_or_not_a_credential_exists(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """The grants are in `build_statements`, not in `activate_backup_user`.

    `build_statements` takes a document and nothing else -- it cannot see a
    secret generation, so it cannot make the grants conditional on one. That is
    the property, and asserting it this way is why the test is cheap: a
    refactor that moved the grants into the activation function would have to
    change this signature to compile.

    Why it matters: a project whose first deploy carries no backup credential
    still gets a correctly privileged role, so the deploy that finally
    materializes the secret activates a role that is already right rather than
    one that becomes right. The alternative makes the catalog depend on which
    generation happened to run.
    """
    role = document["database"]["roles"]["backup_user"]
    statements = _statements(bootstrap, document)
    reaching = [s for s in statements if role in s]
    assert len(reaching) >= 6, (
        f"only {len(reaching)} statements name the backup role; expected the five "
        "privileges plus CONNECT, all unconditional"
    )


# ---------------------------------------------------------------------------
# The credential and the ceiling
# ---------------------------------------------------------------------------


def _contract_consumer() -> dict[str, Any]:
    """`backup_user_password`'s consumer, read from `secrets.required.yaml`.

    **Read from the contract, never from `bootstrap.BACKUP_USER_CONSUMER`**, and
    the battery is why. M5 mutated the module's `target_file` to a wrong name and
    the activation test below still passed -- because the fixture wrote the
    generation wherever the module said, so the test moved with the mutation and
    could not see it.

    That is D288/D289/D291 occurring inside the test whose docstring says it does
    not make that mistake: a rig that reaches the right end state by a route the
    product does not take proves the end state is reachable, not that the product
    reaches it (ADR 0065/0066). The materializer writes where the CONTRACT says,
    so that is the only honest source for this path.
    """
    contract = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    secret = next(s for s in contract["secrets"] if s["name"] == "backup_user_password")
    consumer = next(c for c in secret["consumers"] if c["service"] == "postgres")
    return consumer


def _generation(root: Path, password: str) -> None:
    """Write a generation exactly where the MATERIALIZER writes one."""
    consumer = _contract_consumer()
    directory = root / "alpha" / "generations" / "gen-0001" / consumer["service"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / consumer["target_file"]).write_text(
        secrets_contract.render_secret(password, consumer), encoding="utf-8"
    )
    (root / "alpha" / "active-secret-generation.json").write_text(
        json.dumps({"generation_id": "gen-0001"}), encoding="utf-8"
    )


@pytest.fixture
def recorded(bootstrap: Any, monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Record what the product would have applied, without a cluster.

    `apply_credential` and `apply_connection_limit` are the two SQL-issuing
    calls, and they are the boundary this module stops at. Everything before
    them -- which consumer to look for, what filename that implies, how the
    pgpass line is read back, and *whether to credential at all* -- is the
    product's own decision and is what gets driven.
    """
    calls: list[tuple] = []
    monkeypatch.setattr(
        bootstrap,
        "apply_credential",
        lambda container, database, role, password, connection_limit=None: calls.append(
            ("credential", role, password, connection_limit)
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "apply_connection_limit",
        lambda container, database, role, limit: calls.append(("limit", role, limit)),
    )
    return calls


def test_a_generation_carrying_the_credential_activates_the_role(
    bootstrap: Any, recorded: list[tuple], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Driven through the product's DECISION, not through `apply_credential`.

    Session 7 Run 4's mutation battery is why this is written this way: with the
    logic inline and the test calling `apply_credential` itself, a mutation that
    never applied the credential at all left every test green. A rig that
    reaches the right end state by a route the product does not take proves the
    end state is reachable, not that the product reaches it (ADR 0065/0066).

    **Both `SECRET_ROOT` globals are redirected**, because `materialized_secret_
    path` reads the root twice -- the pointer through this module's, the file
    through `secrets_contract`'s. They are the same constant in production, and
    redirecting one left the pointer under the fake root and the file under the
    real one.
    """
    _generation(tmp_path, "s3cr3t-backup-password")
    monkeypatch.setattr(bootstrap, "SECRET_ROOT", str(tmp_path))
    monkeypatch.setattr(secrets_contract, "SECRET_ROOT", str(tmp_path))

    credentialed = bootstrap.activate_backup_user(
        "container", "db", "alpha", "apg_alpha_dev_backup_user", 2
    )

    assert credentialed, (
        "the product declined to credential the backup role from a generation that carries its file"
    )
    assert recorded == [("credential", "apg_alpha_dev_backup_user", "s3cr3t-backup-password", 2)], (
        f"the product applied {recorded}; expected the credential and the ceiling together, "
        "with the password read back out of the consumer's own materialized file"
    )


def test_a_generation_without_the_credential_leaves_the_role_nologin(
    bootstrap: Any, recorded: list[tuple], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the row above, and the state of every first deploy.

    Without this the clause could credential unconditionally and the test above
    would still pass. It is also not a hypothetical: a project materialized
    before Session 10 has no such file, and those are the projects the
    convergence path exists for.

    **The ceiling is still applied.** `ALTER ROLE ... CONNECTION LIMIT` on a
    NOLOGIN role is a catalog change and nothing else, so the bound is in place
    before the role can ever use it -- rather than arriving with the credential
    and leaving a window where it has one and not the other.
    """
    (tmp_path / "alpha").mkdir(parents=True)
    (tmp_path / "alpha" / "active-secret-generation.json").write_text(
        json.dumps({"generation_id": "gen-0001"}), encoding="utf-8"
    )
    monkeypatch.setattr(bootstrap, "SECRET_ROOT", str(tmp_path))
    monkeypatch.setattr(secrets_contract, "SECRET_ROOT", str(tmp_path))

    credentialed = bootstrap.activate_backup_user(
        "container", "db", "alpha", "apg_alpha_dev_backup_user", 2
    )

    assert not credentialed
    assert recorded == [("limit", "apg_alpha_dev_backup_user", 2)], (
        f"the product applied {recorded}; a generation with no backup file must leave the "
        "role NOLOGIN and still apply its bound"
    )


def test_the_ceiling_the_deploy_applies_is_the_one_the_budget_charges(
    bootstrap: Any,
) -> None:
    """The two arithmetics agree by construction, not by coincidence (D327).

    `config._validate_connection_budget` charges this figure against the
    manifest and `connection_limits` hands the same object to the role. D327 is
    the record of the alternative: the manifest's arithmetic and this plane's
    *"agreed by coincidence, 23 against 20"*, and nothing compared them for four
    sessions.

    **What would have to break for this to go red:** somebody sets the role's
    ceiling from a different number than the budget reserves for it -- which is
    how a fifth claimant becomes a sixth.
    """
    *_, backup_limit = bootstrap.connection_limits(56, 3, 13, 6, 6, 20)
    assert backup_limit == config.BACKUP_RESERVED_CONNECTIONS == 2, (
        f"the deploy would apply CONNECTION LIMIT {backup_limit} to a role the manifest "
        f"check reserves {config.BACKUP_RESERVED_CONNECTIONS} connections for"
    )


def test_the_ceiling_is_above_the_measured_concurrency(bootstrap: Any) -> None:
    """Two, because `check` and `backup` genuinely overlap (rig 5 arm I).

    A lone pgBackRest command holds ONE connection -- 68 samples of
    `pg_stat_activity` taken inside the same invocation as a real full backup,
    maximum 1. The second is the overlap: Run 6 puts `check` in the deploy's
    step 6c and Run 9 puts `backup` on a timer, and a deploy does not consult a
    timer. pgBackRest takes no lock that prevents them running together --
    measured, a `check` launched two seconds into a full backup ran to
    completion, both exited 0, and the sampler recorded 2.

    **What a ceiling of 1 costs, measured rather than imagined (D543):** the
    overlapping `check` fails `[027]: no database found` with the hint `check
    indexed pg-path/pg-host configurations`, and `too many connections for role`
    appears only as a WARN above it. The headline sends the reader to the one
    setting that is correct.
    """
    assert config.BACKUP_RESERVED_CONNECTIONS >= 2, (
        "the backup ceiling is below the measured concurrency of a check overlapping a "
        "backup. The failure is not reported as a capacity problem: pgBackRest answers "
        "`[027]: no database found` and sends the reader to pg1-path (D543)"
    )


# ---------------------------------------------------------------------------
# The reserve the fifth claimant came out of
# ---------------------------------------------------------------------------


def test_the_administration_reserve_no_longer_claims_to_hold_backup_connections() -> None:
    """D530, and it is the half of the decision that is easy to skip.

    `ADMINISTRATION_RESERVED_CONNECTIONS` has said since Session 5 that it holds
    connections "for migrations, backups, a direct developer session and
    PostgreSQL's own superuser_reserved_connections". After ADR 0148 it does not
    hold any for backups -- they are charged their own summand. A comment
    describing work that moved elsewhere is D276's shape, and D276 was found in
    this very file: a sentence deferring an activation to a session that was
    already the current one.

    **Asserted on the docstring rather than on the number**, because the number
    did not change and that is exactly the trap. 5 before and 5 after; the only
    thing that moved is what the 5 is for.
    """
    source = (REPO_ROOT / "src" / "agentic_postgres" / "config.py").read_text(encoding="utf-8")
    marker = "ADMINISTRATION_RESERVED_CONNECTIONS = 5"
    assert marker in source
    comment = source.split(marker)[0].rsplit("AUTH_RESERVED_CONNECTIONS", 1)[-1]

    assert "for migrations, backups, a direct developer session" not in comment, (
        "the administration reserve still claims to hold connections for backups. After "
        "ADR 0148 it does not -- the backup identity is its own summand -- and a reserve "
        "that describes a claimant charged elsewhere is the arithmetic D530 warned about"
    )
    assert "BACKUP_RESERVED_CONNECTIONS" in source, (
        "the backup claimant is not declared in config; the manifest check and the "
        "bootstrap plane would have no shared authority over the number"
    )

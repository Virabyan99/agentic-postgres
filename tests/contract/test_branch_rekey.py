"""A branch's re-key, as statements (Session 40, ADR 0271, D2427, D2455, D2459).

Rig 40a ran these statements on a cluster restored by pgBackRest: the parent's
customer, migration and superuser passwords accepted from a peer container
before, refused after; the branch's verifiers accepted. These proofs hold the
statements the runtime will send -- every role once, the verifiers only as psql
variables on stdin -- and Run 3's `test_branch_runtime_on_a_cluster` runs them.
"""

from __future__ import annotations

import pytest

from agentic_postgres import branch_rekey, naming, scram

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

ROLES = naming.database_roles("slot3_prod")
APP = scram.verifier("branch-app-password-for-the-proof")
ADMIN = scram.verifier("branch-admin-password-for-the-proof")


def test_the_rekey_names_every_role_once() -> None:
    """One transaction: each of the fourteen platform roles `NOLOGIN PASSWORD
    NULL` exactly once, the superuser `PASSWORD NULL`, both customer roles
    `LOGIN` at `small`'s doors with their own verifier variable, every live
    refresh family revoked as `administrative` (the enum has no `branch`,
    D2455), every unexpired agent credential expired.

    Goes red if: any platform role is skipped (rig 40a: `migration_user` would
    answer the parent's password), a customer role is locked, the order leaves
    a statement outside the transaction, or the revocation names a value the
    enum refuses."""
    statements = branch_rekey.statements(ROLES)
    assert statements[0] == "BEGIN;" and statements[-1] == "COMMIT;"
    body = "\n".join(statements)
    platform = [s for s in naming.ROLE_SUFFIXES if s not in branch_rekey.CUSTOMER_ROLES]
    assert len(platform) == 14
    for suffix in platform:
        line = f'ALTER ROLE "{ROLES[suffix]}" NOLOGIN PASSWORD NULL;'
        assert statements.count(line) == 1, (suffix, line)
    assert statements.count('ALTER ROLE "postgres" PASSWORD NULL;') == 1
    assert (
        f"ALTER ROLE \"{ROLES['customer_app']}\" LOGIN CONNECTION LIMIT 2 PASSWORD :'app_verifier';"
        in statements
    )
    assert (
        f'ALTER ROLE "{ROLES["customer_admin"]}" LOGIN CONNECTION LIMIT 2 '
        "PASSWORD :'admin_verifier';" in statements
    )
    for suffix in branch_rekey.CUSTOMER_ROLES:
        assert f'ALTER ROLE "{ROLES[suffix]}" NOLOGIN' not in body
    assert "revoked_reason = 'administrative' WHERE revoked_at IS NULL" in body
    assert "'branch'" not in body
    assert "WHERE expires_at IS NULL OR expires_at > now()" in body
    assert len(statements) == 2 + 14 + 1 + 2 + 2

    incomplete = dict(ROLES)
    del incomplete["migration_user"]
    with pytest.raises(branch_rekey.RekeyError, match="migration_user"):
        branch_rekey.statements(incomplete)


def test_no_verifier_reaches_an_argv() -> None:
    """The verifiers arrive as `\\set` lines on psql's stdin -- the
    `credential.rotate` path (ADR 0269) -- and appear nowhere in the
    statements. A value that is not a verifier is refused WITHOUT being
    repeated in the error; a missing or extra role is refused.

    Goes red if: a verifier is interpolated into a statement, or an error
    message echoes what it refused."""
    text = branch_rekey.psql_input(ROLES, {"customer_app": APP, "customer_admin": ADMIN})
    lines = text.splitlines()
    assert lines[0] == f"\\set app_verifier '{APP}'"
    assert lines[1] == f"\\set admin_verifier '{ADMIN}'"
    assert all(APP not in s and ADMIN not in s for s in branch_rekey.statements(ROLES))
    assert text.count(APP) == 1 and text.count(ADMIN) == 1

    secret = "a-plaintext-password-that-must-not-be-echoed"  # noqa: S105 -- a probe value
    with pytest.raises(branch_rekey.RekeyError) as refused:
        branch_rekey.psql_input(ROLES, {"customer_app": secret, "customer_admin": ADMIN})
    assert secret not in str(refused.value)
    with pytest.raises(branch_rekey.RekeyError):
        branch_rekey.psql_input(ROLES, {"customer_app": APP})
    with pytest.raises(branch_rekey.RekeyError):
        branch_rekey.psql_input(
            ROLES, {"customer_app": APP, "customer_admin": ADMIN, "migration_user": APP}
        )


def test_the_restore_settings_are_reset_outside_the_transaction() -> None:
    """D2459: pgBackRest's `restore_command` and recovery targets stay in the
    restored `postgresql.auto.conf` (rig 40a (e)); the reset removes them.
    `ALTER SYSTEM` cannot run in a transaction block, so these are separate
    statements, then a reload -- and none of them is in the re-key's
    transaction."""
    resets = branch_rekey.reset_statements()
    assert resets == (
        "ALTER SYSTEM RESET restore_command;",
        "ALTER SYSTEM RESET recovery_target_time;",
        "ALTER SYSTEM RESET recovery_target_action;",
        "SELECT pg_reload_conf();",
    )
    assert not set(resets) & set(branch_rekey.statements(ROLES))

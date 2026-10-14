"""A branch's re-key: the parent's credentials opened nothing in it (ADR 0271, D2427).

A physical restore carries `pg_authid` whole -- every platform login role's
verifier, both customer roles', the superuser's -- so a branch that started
answering would answer its parent's passwords. The re-key runs ONCE, as
`postgres` over the branch container's local socket, BEFORE either door
exists (the runtime starts the poolers only after it; Run 3):

- every role of the document's sixteen but the two customer roles:
  `NOLOGIN PASSWORD NULL`;
- the superuser: `PASSWORD NULL` -- its LOGIN is kept for the local socket,
  which the image's `pg_hba.conf` trusts, as it trusts loopback INSIDE the
  container; every network peer meets `scram-sha-256` (D2458);
- `customer_app` / `customer_admin`: `LOGIN CONNECTION LIMIT` at `small`'s
  doors, `PASSWORD` the BRANCH's own verifier -- generated on the customer's
  workstation, sent as a verifier (ADR 0269), set here as a psql variable on
  stdin, never an argument;
- every live refresh family revoked, `revoked_reason = 'administrative'` (the
  enum has no `branch`, D2455); every unexpired agent credential expired.

All in one transaction: a re-key that stopped half way is a re-key that did
not happen, and the runtime refuses to open a door on it. Measured in rig 40a:
19 statements in 0.31 s; the parent's customer, migration and superuser
passwords accepted from a peer before and refused after; the branch's
verifiers accepted.

:func:`reset_statements` runs AFTER the transaction -- `ALTER SYSTEM` cannot
run inside one -- and removes pgBackRest's `restore_command` and recovery
targets from `postgresql.auto.conf`, so the branch's configuration names
nothing of its parent's repository (D2459).
"""

# ruff: noqa: S608 -- every interpolated value is a role name quoted by
# `migrations.quote_identifier`, a limit read from the profile table, or a
# module constant; a verifier only ever arrives as a psql variable.

from __future__ import annotations

from agentic_postgres import compute_profiles, migrations, naming, reconciler_dispatch, scram

__all__ = [
    "CUSTOMER_ROLES",
    "REVOKED_REASON",
    "SUPERUSER",
    "VERIFIER_VARIABLES",
    "RekeyError",
    "customer_limits",
    "psql_input",
    "reset_statements",
    "statements",
]

#: The two roles whose doors a branch opens, in door order (ADR 0269).
CUSTOMER_ROLES: tuple[str, ...] = ("customer_app", "customer_admin")

#: The psql variable each customer role's verifier arrives in.
VERIFIER_VARIABLES: dict[str, str] = {
    "customer_app": "app_verifier",
    "customer_admin": "admin_verifier",
}

#: The image's superuser (`compose.yaml`'s `POSTGRES_USER`).
SUPERUSER = "postgres"

#: `app_private.refresh_revocation`'s value for an operator's act (`0023:50-55`).
REVOKED_REASON = "administrative"

#: The settings pgBackRest's restore writes into `postgresql.auto.conf`
#: (rig 40a (e): `restore_command`, `recovery_target_time`,
#: `recovery_target_action`); `recovery_target_time` is absent for a branch at
#: the end of the archive, and RESET of an absent setting is a no-op.
_RESTORE_SETTINGS: tuple[str, ...] = (
    "restore_command",
    "recovery_target_time",
    "recovery_target_action",
)


class RekeyError(ValueError):
    """The re-key cannot be built. The message never carries a verifier."""


def customer_limits() -> dict[str, int]:
    """Each customer role's CONNECTION LIMIT in a branch: `small`'s doors."""
    doors = compute_profiles.CUSTOMER_CONNECTIONS["small"]
    return {"customer_app": int(doors["pool"]), "customer_admin": int(doors["direct"])}


def _roles(roles: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    missing = [suffix for suffix in naming.ROLE_SUFFIXES if not roles.get(suffix)]
    if missing:
        raise RekeyError(
            f"the parent's document names no {missing} role; a re-key that skipped "
            "a role would leave it answering the parent's password"
        )
    platform = [roles[s] for s in naming.ROLE_SUFFIXES if s not in CUSTOMER_ROLES]
    return platform, {suffix: roles[suffix] for suffix in CUSTOMER_ROLES}


def statements(roles: dict[str, str]) -> tuple[str, ...]:
    """The re-key, one statement per entry, inside `BEGIN` / `COMMIT`.

    ``roles`` is the parent's deployed document's `database.roles` (ADR 0002:
    read, never re-derived). The verifiers are the psql variables of
    :data:`VERIFIER_VARIABLES`; :func:`psql_input` sets them.
    """
    platform, customer = _roles(roles)
    q = migrations.quote_identifier
    limits = customer_limits()
    out = ["BEGIN;"]
    out += [f"ALTER ROLE {q(role)} NOLOGIN PASSWORD NULL;" for role in platform]
    out.append(f"ALTER ROLE {q(SUPERUSER)} PASSWORD NULL;")
    for suffix in CUSTOMER_ROLES:
        out.append(
            f"ALTER ROLE {q(customer[suffix])} LOGIN CONNECTION LIMIT {limits[suffix]} "
            f"PASSWORD :'{VERIFIER_VARIABLES[suffix]}';"
        )
    out.append(
        "UPDATE app_private.refresh_families SET revoked_at = now(), "
        f"revoked_reason = '{REVOKED_REASON}' WHERE revoked_at IS NULL;"
    )
    out.append(
        "UPDATE app_private.agent_credentials SET expires_at = now() "
        "WHERE expires_at IS NULL OR expires_at > now();"
    )
    out.append("COMMIT;")
    return tuple(out)


def psql_input(roles: dict[str, str], verifiers: dict[str, str]) -> str:
    """The re-key as psql's stdin: one `\\set` per verifier, then :func:`statements`.

    ``verifiers`` maps `customer_app` / `customer_admin` to a SCRAM-SHA-256
    verifier. Anything that is not exactly one verifier per customer role, in
    PostgreSQL's own shape, is refused WITHOUT echoing it.
    """
    if set(verifiers) != set(CUSTOMER_ROLES):
        raise RekeyError(
            f"expected one verifier for each of {list(CUSTOMER_ROLES)}, got {sorted(verifiers)}"
        )
    for suffix, value in verifiers.items():
        if not isinstance(value, str) or not scram.VERIFIER.fullmatch(value):
            raise RekeyError(f"the {suffix} value is not a SCRAM-SHA-256 verifier")
    variables = {VERIFIER_VARIABLES[suffix]: verifiers[suffix] for suffix in CUSTOMER_ROLES}
    return reconciler_dispatch.psql_input("\n".join(statements(roles)), variables)


def reset_statements() -> tuple[str, ...]:
    """Run after the re-key's COMMIT, outside any transaction (D2459)."""
    return (
        *(f"ALTER SYSTEM RESET {setting};" for setting in _RESTORE_SETTINGS),
        "SELECT pg_reload_conf();",
    )

"""The connection snippets `/v1` serves for a project's public doors (D2352,
ADR 0268 item 6).

The property: **no snippet can carry a password.** Every place a password
goes says `PASSWORD_PLACEHOLDER`, and a record carrying a value under any name
does not reach the text. Then what each measured client needs (rig 39c): libpq
`verify-full` with the system roots, Prisma's two URLs with strict acceptance
and no `pgbouncer=true`, node-postgres rejecting an unauthorised certificate.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from agentic_postgres import service_source

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

snippets_module = service_source.load("connection_snippets")
PLACEHOLDER = snippets_module.PASSWORD_PLACEHOLDER

DOORS: dict[str, Any] = {
    "enabled": True,
    "pooled": {
        "host": "pool.slot1.example.com", "port": 5432, "user": "slot1_prod_customer_app",
        "database": "slot1_prod", "sslmode": "verify-full", "connection_limit": 2,
    },
    "direct": {
        "host": "direct.slot1.example.com", "port": 5432, "user": "slot1_prod_customer_admin",
        "database": "slot1_prod", "sslmode": "verify-full", "connection_limit": 2,
    },
}  # fmt: skip


def test_every_measured_client_has_one_snippet_and_no_other() -> None:
    served = snippets_module.snippets(DOORS)
    assert tuple(served) == snippets_module.CLIENTS == ("psql", "prisma", "node-pg", "psycopg")


def test_no_snippet_can_carry_a_password() -> None:
    """A record carrying a value -- as `password`, inside a door, or as an
    extra member -- never reaches the text; every snippet that names a
    password names the placeholder."""
    tainted = copy.deepcopy(DOORS)
    secret = "s3cret-value-never-served"  # noqa: S105 -- the planted value the proof hunts
    tainted["password"] = secret
    tainted["pooled"]["password"] = secret
    tainted["direct"]["url"] = f"postgresql://x:{secret}@h/d"
    served = snippets_module.snippets(tainted)
    assert served == snippets_module.snippets(DOORS)
    for client, text in served.items():
        assert secret not in text, client
        if client != "psql":
            assert PLACEHOLDER in text, client
    # psql reads the password from the prompt or PGPASSFILE: its line names none.
    assert "password" not in served["psql"].split("#")[0]


def test_each_client_verifies_the_server() -> None:
    served = snippets_module.snippets(DOORS)
    assert served["psql"].count("sslmode=verify-full sslrootcert=system") == 2
    assert "sslmode=verify-full sslrootcert=system" in served["psycopg"]
    assert "rejectUnauthorized: true" in served["node-pg"]
    prisma = served["prisma"].splitlines()
    assert prisma[0].startswith('DATABASE_URL="postgresql://slot1_prod_customer_app:')
    assert "@pool.slot1.example.com:5432/slot1_prod?" in prisma[0]
    assert prisma[1].startswith('DIRECT_URL="postgresql://slot1_prod_customer_admin:')
    assert "@direct.slot1.example.com:5432/slot1_prod?" in prisma[1]
    for line in prisma:
        assert line.endswith('?sslmode=require&sslaccept=strict"'), line
    assert "pgbouncer" not in served["prisma"]


def test_the_pooled_door_is_the_default_and_the_direct_is_named() -> None:
    served = snippets_module.snippets(DOORS)
    for client in ("node-pg", "psycopg"):
        assert "pool.slot1.example.com" in served[client]
        assert "direct." not in served[client]
    assert "host=pool.slot1.example.com" in served["psql"]
    assert "host=direct.slot1.example.com" in served["psql"]


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": False},
        {"pooled": None},
        {"direct": {"host": "x", "port": 5432, "user": "u", "database": "d"}},
        {"pooled": {**DOORS["pooled"], "host": 'pool.example.com" && rm -rf /'}},
        {"pooled": {**DOORS["pooled"], "port": "5432"}},
        {"pooled": {**DOORS["pooled"], "port": True}},
        {"pooled": {**DOORS["pooled"], "user": "Robert'); DROP TABLE"}},
        {"direct": {**DOORS["direct"], "database": "a b"}},
    ],
)
def test_a_record_that_is_not_one_yields_no_snippet(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        snippets_module.snippets({**DOORS, **change})

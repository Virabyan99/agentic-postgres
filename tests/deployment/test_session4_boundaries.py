"""The two transports do not widen the authorization model (SEC-DBX-002, SEC-DBX-003).

Replaces two of the three Session 4 placeholders in
``tests/security/test_future_security_boundaries.py``. The third, SEC-DBX-001,
is a negative claim about public reachability and is proved from off-host in
``tests/external/test_session4_public_transports.py`` — a scan run on the host
traverses loopback and the host's own routing table, so it can report "closed"
for a port the world can reach.

**Under tests/deployment/ rather than tests/security/, and marked ``security``.**
The marker decides what runs and what the evidence records; the directory decides
which ``conftest.py`` is in scope, and the fixtures that make these measurable —
the materialized per-consumer secret, the built client image, the resolved
Compose model — live in ``tests/deployment/conftest.py``. Copying them into a
second conftest to satisfy a directory convention would create two definitions of
how a credential is read, which is the class of duplication this repository has
paid for twice.

Both tests run against the **pooled** transport, deliberately. The direct
transport reaches PostgreSQL's own authorization, which Session 3 already proves;
the pooled one adds a process holding server connections open across clients, and
every property below is one that process could quietly break.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.database,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: The pooler's port on the project network, not its published host port.
INTERNAL_POOL_PORT = 6432

#: A value nothing else in this system would ever set. If it turns up in a
#: second client's session, it got there by following a server connection.
LEAK_UUID = "0c9d1f77-4a02-4b7e-9e1a-8f30d2c6b515"


def key(document: dict[str, Any]) -> str:
    return document["project"]["key"]


def run_probe(
    document: dict[str, Any],
    image: str,
    script: str,
    password: str,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a Psycopg probe on the project's own network. Credential on stdin.

    The script is an argument and the password is on stdin, because only one of
    the two is secret and only one of them may appear in a process listing.
    """
    arguments = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--network",
        document["edge"]["project_internal_network"],
        "--env",
        "APG_POOL_HOST=pgbouncer",
        "--env",
        f"APG_POOL_PORT={INTERNAL_POOL_PORT}",
        "--env",
        f"APG_ROLE={document['database']['access_profiles']['runtime_pooled']['role']}",
        "--env",
        f"APG_DATABASE={document['database']['name']}",
    ]
    for name, value in sorted((environment or {}).items()):
        arguments += ["--env", f"{name}={value}"]
    arguments += ["--entrypoint", "python", image, "-c", script]

    result = subprocess.run(
        arguments, input=password, capture_output=True, text=True, check=False, timeout=300
    )
    assert result.returncode == 0, (
        f"the probe exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return json.loads(result.stdout.splitlines()[-1])


_PRIVILEGE_PROBE = r"""
import json, os, sys
import psycopg

password = sys.stdin.read().rstrip("\n")
role = os.environ["APG_ROLE"]
owner = role.rsplit("_app_runtime", 1)[0] + "_object_owner"
conninfo = (
    f"host={os.environ['APG_POOL_HOST']} port={os.environ['APG_POOL_PORT']} "
    f"user={role} dbname={os.environ['APG_DATABASE']} "
    "sslmode=disable application_name=apg-privilege-probe"
)

answer = {"owner_role": owner}
with psycopg.connect(conninfo, password=password, autocommit=True) as connection:
    attributes = connection.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolconnlimit"
        "  FROM pg_roles WHERE rolname = %s",
        (role,),
    ).fetchone()
    (
        answer["superuser"],
        answer["createdb"],
        answer["createrole"],
        answer["replication"],
        answer["bypassrls"],
        answer["connection_limit"],
    ) = attributes

    answer["owns_relations"] = connection.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner"
        " WHERE r.rolname = %s",
        (role,),
    ).fetchone()[0]
    answer["owns_schemas"] = connection.execute(
        "SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner"
        " WHERE r.rolname = %s",
        (role,),
    ).fetchone()[0]
    answer["database_create"] = connection.execute(
        "SELECT has_database_privilege(%s, current_database(), 'CREATE')", (role,)
    ).fetchone()[0]
    answer["database_temp"] = connection.execute(
        "SELECT has_database_privilege(%s, current_database(), 'TEMPORARY')", (role,)
    ).fetchone()[0]

    # Attempted, not asked of the catalog. D103 measured has_table_privilege
    # returning true for app.notes while the read is denied.
    for label, statement in (
        ("read_app", "SELECT count(*) FROM app.notes"),
        ("create_table", "CREATE TABLE api.apg_probe_should_not_exist (id int)"),
        ("set_role", 'SET ROLE "' + owner + '"'),
    ):
        try:
            connection.execute(statement)
            answer[label] = "allowed"
        except psycopg.Error as error:
            answer[label] = type(error).__name__

    # The positive control: the api surface answers. Without it, a cluster where
    # every statement failed would satisfy all three refusals above.
    answer["api_readable"] = connection.execute("SELECT count(*) FROM api.notes").fetchone()[0]

print(json.dumps(answer))
"""

_SESSION_STATE_PROBE = r"""
import json, os, sys
import psycopg

password = sys.stdin.read().rstrip("\n")
conninfo = (
    f"host={os.environ['APG_POOL_HOST']} port={os.environ['APG_POOL_PORT']} "
    f"user={os.environ['APG_ROLE']} dbname={os.environ['APG_DATABASE']} "
    "sslmode=disable application_name=apg-session-state-probe"
)
answer = {}

# One client sets a transaction-local claim and a deliberately SESSION-scoped
# GUC, then disconnects. A second client asks for both back. Under transaction
# pooling the second may well be handed the same SERVER connection -- that is
# what pooling is -- so what must not survive is the state, not the socket.
with psycopg.connect(conninfo, password=password) as first:
    with first.transaction():
        first.execute("SELECT set_config('app.user_id', %s, true)", (os.environ["APG_LEAK_UUID"],))
        answer["claim_inside"] = first.execute(
            "SELECT current_setting('app.user_id', true)"
        ).fetchone()[0]
        first.execute("SELECT set_config('apg.leak_probe', 'leaked', false)")
    with first.transaction():
        answer["claim_after_commit"] = first.execute(
            "SELECT current_setting('app.user_id', true)"
        ).fetchone()[0]

with psycopg.connect(conninfo, password=password) as second:
    with second.transaction():
        answer["claim_next_client"] = second.execute(
            "SELECT current_setting('app.user_id', true)"
        ).fetchone()[0]
        answer["guc_next_client"] = second.execute(
            "SELECT current_setting('apg.leak_probe', true)"
        ).fetchone()[0]
        answer["rows_next_client"] = second.execute("SELECT count(*) FROM api.notes").fetchone()[0]

print(json.dumps(answer))
"""


def test_the_app_runtime_role_holds_no_ownership_or_ddl(
    project_a, materialized_secret, client_image
) -> None:
    """SEC-DBX-002. Measured through the credential, not read from the catalog.

    D103 is why. ``has_table_privilege(app_runtime, 'app.notes', 'SELECT')`` is
    TRUE and the role still cannot read the table, because the boundary is schema
    ``USAGE`` and the table grant is what makes the security-invoker views work.
    A test asserting the catalog bit would fail while the property held, and the
    obvious fix for that failure — revoking SELECT from ``authenticated`` — would
    silently break every api view. So the reads and the DDL are **attempted**.

    Goes red if: migration 0006's revokes are dropped or a later migration
    re-grants schema ``USAGE`` on ``app``; ``CREATE`` appears on ``api``; the
    membership in ``authenticated`` is granted ``SET TRUE``, letting the role
    shed its own identity; or the ``CONNECTION LIMIT`` is removed, which is how
    one application exhausts a cluster and takes the migration plane and an
    operator's psql down with it.

    The api read is a positive control. Without it, a cluster where every
    statement failed would satisfy all three refusals.
    """
    document = project_a
    password = materialized_secret(key(document), "pgbouncer", "app_runtime_password")
    answer = run_probe(
        document, client_image(key(document), "client-psycopg"), _PRIVILEGE_PROBE, password
    )

    for attribute in ("superuser", "createdb", "createrole", "replication", "bypassrls"):
        assert answer[attribute] is False, f"app_runtime holds {attribute}"

    assert answer["connection_limit"] > 0, "app_runtime has no connection limit"
    assert answer["owns_relations"] == 0, f"app_runtime owns {answer['owns_relations']} relations"
    assert answer["owns_schemas"] == 0, f"app_runtime owns {answer['owns_schemas']} schemas"
    assert answer["database_create"] is False
    assert answer["database_temp"] is False

    assert answer["read_app"] != "allowed", "app.notes was readable through the runtime credential"
    assert answer["create_table"] != "allowed", "app_runtime created a table in api"
    assert answer["set_role"] != "allowed", (
        f"app_runtime could SET ROLE to {answer['owner_role']}, so its own identity is optional"
    )
    assert isinstance(answer["api_readable"], int), (
        "the api surface did not answer, so the three refusals above prove nothing"
    )


def test_pooled_session_state_does_not_survive_release(
    project_a, materialized_secret, client_image
) -> None:
    """SEC-DBX-003. Two product contracts, stated as such rather than as bugs.

    A transaction-local claim must be gone at commit, and a deliberately
    session-scoped GUC must be absent for the next client.

    Goes red if: the pool mode is changed to ``session``, in which case
    ``apg.leak_probe`` follows the server connection to the next client; or the
    pooler stops resetting server state between clients. Either would let one
    request's asserted identity become the next one's, which is the most
    dangerous single failure available in this design.

    The claim is asserted **inside** its own transaction as a positive control.
    A test that only checked it was absent afterwards would pass against a
    cluster where ``set_config`` never worked at all.
    """
    document = project_a
    password = materialized_secret(key(document), "pgbouncer", "app_runtime_password")
    answer = run_probe(
        document,
        client_image(key(document), "client-psycopg"),
        _SESSION_STATE_PROBE,
        password,
        {"APG_LEAK_UUID": LEAK_UUID},
    )

    assert answer["claim_inside"] == LEAK_UUID, (
        "the claim was not set inside its own transaction, so its absence afterwards proves nothing"
    )
    assert not answer["claim_after_commit"], (
        f"a transaction-local claim outlived its transaction: {answer['claim_after_commit']!r}"
    )
    assert not answer["claim_next_client"], (
        f"the next client inherited a claim: {answer['claim_next_client']!r}"
    )
    assert not answer["guc_next_client"], (
        f"a session GUC followed the server connection to the next client: "
        f"{answer['guc_next_client']!r}. That is what session pooling looks like."
    )
    assert answer["rows_next_client"] == 0, (
        "a client with no claim of its own read rows, so the previous client's identity "
        "was still in force"
    )

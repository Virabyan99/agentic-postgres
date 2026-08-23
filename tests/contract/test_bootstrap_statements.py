"""What the bootstrap plane applies, and what `--check` can see afterwards.

Both halves of ADR 0067, tested on the two sides of the boundary it is about.

`bin/postgres-bootstrap.py` had no offline test of its statement list at all.
That is how one hard-coded `ALTER ROLE <app_runtime> SET statement_timeout =
'30s'` stood in for a per-role setting the manifest had been declaring since
Run 1: the manifest declared it, `config` validated it, the render dropped it,
and the only thing that would have noticed was a test comparing what a
document *says* against what this plane *issues* (D197).

The `check_violations` half matters more than it looks. The whole class of
defect this project keeps producing is a value that reads as measured and is
not, and the answer ADR 0067 gives is that where a setting crosses a plane
boundary, the test that matters is on the far side. `--check` is that far side,
and it was blind to statement timeouts entirely -- it would have reported a
clean cluster while every request role ran unbounded.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, config, output_migrations

pytestmark = [pytest.mark.contract, pytest.mark.p0]

INSTANCE_UUID = "8f14e45f-ceea-467a-9c1e-1a1f9c1a2b3c"


@pytest.fixture(scope="module")
def bootstrap() -> Any:
    """`bin/postgres-bootstrap.py`, imported rather than run.

    Imported, so `__name__` is not `"__main__"` and `main()` never fires. That
    is also the reason a test like this cannot be the only check on the file:
    a definition placed below the main guard is unbound when the script runs and
    bound when a test imports it, which is how D185 passed every test and
    raised `NameError` on a deploy.
    """
    specification = importlib.util.spec_from_file_location(
        "apg_postgres_bootstrap", REPO_ROOT / "bin" / "postgres-bootstrap.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture
def document() -> dict[str, Any]:
    """A version 7 rendered document, migrated from the committed v5 render.

    Migrated rather than rendered: `rendering.render_project` publishes to
    `.generated/<key>` derived from the manifest rather than to a path the
    caller chose, and a test that leaves a render behind fails the gate for
    whoever runs the suite next.
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


def timeout_statements(statements: list[str]) -> dict[str, str]:
    """The applied timeouts, parsed back out of the SQL this plane would issue."""
    found = {}
    for statement in statements:
        if "SET statement_timeout" not in statement:
            continue
        head, _, value = statement.partition(" SET statement_timeout = ")
        found[head.removeprefix("ALTER ROLE ").strip('"')] = value.rstrip(";").strip("'")
    return found


# ---------------------------------------------------------------------------
# What is applied
# ---------------------------------------------------------------------------


def test_every_timeout_in_the_document_becomes_a_statement(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """The near side of the boundary: document in, SQL out, nothing dropped."""
    applied = timeout_statements(bootstrap.build_statements(document, INSTANCE_UUID))
    assert applied == document["database"]["statement_timeouts"]


def test_the_plane_holds_no_opinion_of_its_own(bootstrap: Any, document: dict[str, Any]) -> None:
    """Change the document, and every statement changes with it.

    This is the test the hard-coded literal could not have survived, and the
    reason it is written as a *second* render rather than as a match against
    `'30s'`: a plane that ignored the document entirely would still emit `30s`
    for `app_runtime` and pass a test that only looked for the value the
    document happened to carry.
    """
    roles = document["database"]["roles"]
    document["database"]["statement_timeouts"] = {
        roles["app_runtime"]: "17s",
        roles["agent_reader"]: "250ms",
    }
    applied = timeout_statements(bootstrap.build_statements(document, INSTANCE_UUID))
    assert applied == {roles["app_runtime"]: "17s", roles["agent_reader"]: "250ms"}
    assert roles["anon"] not in applied, (
        "a role the document no longer bounds is still being bounded, so this plane "
        "is carrying a timeout of its own"
    )


def test_a_document_naming_no_timeouts_produces_no_timeout_statements(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """The control for the two above.

    Without it, a plane that emitted its own fixed set would pass
    `test_every_timeout_in_the_document_becomes_a_statement` on any document
    whose timeouts happened to match.
    """
    document["database"]["statement_timeouts"] = {}
    assert timeout_statements(bootstrap.build_statements(document, INSTANCE_UUID)) == {}


def test_the_statements_are_issued_in_a_stable_order(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    roles = document["database"]["roles"]
    document["database"]["statement_timeouts"] = {
        roles["authenticated"]: "5s",
        roles["anon"]: "2s",
        roles["app_runtime"]: "30s",
    }
    issued = [
        statement
        for statement in bootstrap.build_statements(document, INSTANCE_UUID)
        if "SET statement_timeout" in statement
    ]
    assert issued == sorted(issued)


def test_the_role_and_the_duration_are_both_quoted(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """An identifier through `quote_identifier`, a value through `quote_literal`.

    The schema's pattern is why a duration cannot carry a quote today. That is
    a reason to write it safely, not a reason to interpolate it bare and depend
    on a pattern two files away staying strict.
    """
    for statement in bootstrap.build_statements(document, INSTANCE_UUID):
        if "SET statement_timeout" not in statement:
            continue
        assert statement.startswith('ALTER ROLE "')
        assert "SET statement_timeout = '" in statement


# ---------------------------------------------------------------------------
# What `--check` can see
# ---------------------------------------------------------------------------


def catalog(timeouts: dict[str, str], roles: list[str]) -> Any:
    """A stand-in for `query` that answers from a described cluster.

    Every answer other than the timeouts is the answer of a healthy cluster, so
    a violation in the result is a timeout violation and nothing else. Built by
    matching on the SQL rather than by call order: an assertion keyed to the
    order of the queries would go red for a reordering that changed nothing.

    `roles` is what exists, and it filters the timeout answer as well as the
    role answer. The first version of this did not: it returned a `rolconfig`
    row for a role it had just been told was absent, which no cluster does.
    That made the `present` guard in `check_violations` unobservable -- removing
    it left the battery green, because the fake answered for the missing role
    exactly as it did for the others. A rig that behaves unlike the product
    measures the rig (ADR 0065, ADR 0066).
    """

    def answer(container: str, database: str, sql: str) -> str:
        if "rolconfig" in sql:
            return "\n".join(
                f"{role} {value}" for role, value in sorted(timeouts.items()) if role in roles
            )
        if "rolsuper" in sql:
            return ""
        if "rolname FROM pg_roles" in sql:
            return "\n".join(roles)
        if "admin_option" in sql:
            return "false false true"
        # Run 9 asks a second membership question: are the agent roles ABSENT?
        # Answered separately rather than folded into the line above, because
        # the two questions want opposite answers -- a fake returning one string
        # for both would make the agent check unobservable, which is the failure
        # this fixture's own docstring records from the last time.
        if "string_agg('present'" in sql:
            return "absent"
        if "rolcanlogin" in sql:
            return "true true"
        if "pg_namespace" in sql or "pg_extension" in sql:
            return "1"
        if "has_database_privilege('public'" in sql:
            return "false"
        if "has_database_privilege" in sql:
            return "true"
        raise AssertionError(f"the fake catalog was asked something it does not know: {sql}")

    return answer


def test_a_cluster_carrying_the_documents_timeouts_is_clean(
    bootstrap: Any, document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control. Without it every assertion below passes on a check that always fires."""
    wanted = document["database"]["statement_timeouts"]
    roles = sorted(document["database"]["roles"].values())
    monkeypatch.setattr(bootstrap, "query", catalog(wanted, roles))
    assert bootstrap.check_violations("c", "d", document) == []


def test_a_role_with_no_timeout_at_all_is_a_violation(
    bootstrap: Any, document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D197's own cluster, described.

    Every role exists, every grant is right, and one role out of three carries
    the setting. `--check` returned 0 against exactly this.
    """
    roles = sorted(document["database"]["roles"].values())
    runtime = document["database"]["roles"]["app_runtime"]
    observed = {role: "absent" for role in document["database"]["statement_timeouts"]}
    observed[runtime] = "30s"
    monkeypatch.setattr(bootstrap, "query", catalog(observed, roles))

    violations = bootstrap.check_violations("c", "d", document)
    assert len(violations) == 2, violations
    assert all("statement_timeout 'absent'" in violation for violation in violations)
    assert not any(runtime in violation for violation in violations)


def test_a_role_with_the_wrong_timeout_is_a_violation(
    bootstrap: Any, document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale value is the failure mode a redeploy produces, and it is silent.

    Lowering a manifest's timeout and not redeploying leaves the old, higher
    bound in place -- which looks exactly like a bound that was applied.
    """
    roles = sorted(document["database"]["roles"].values())
    anon = document["database"]["roles"]["anon"]
    observed = dict(document["database"]["statement_timeouts"])
    observed[anon] = "30s"
    monkeypatch.setattr(bootstrap, "query", catalog(observed, roles))

    violations = bootstrap.check_violations("c", "d", document)
    assert violations == [f"{anon} has statement_timeout '30s', the document says '2s'"]


def test_a_role_that_does_not_exist_yet_reports_the_missing_role_only(
    bootstrap: Any, document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh cluster must describe itself as fresh.

    The check runs most often against a cluster with no roles at all. Reporting
    a missing timeout for each missing role buries the violations that say what
    is actually wrong under a second copy of them -- the reason the CREATE check
    beside it is guarded the same way.
    """
    anon = document["database"]["roles"]["anon"]
    roles = [role for role in sorted(document["database"]["roles"].values()) if role != anon]
    monkeypatch.setattr(
        bootstrap, "query", catalog(document["database"]["statement_timeouts"], roles)
    )

    violations = bootstrap.check_violations("c", "d", document)
    assert violations == [f"role {anon} does not exist"]


def test_a_document_naming_no_timeouts_asks_the_catalog_nothing(
    bootstrap: Any, document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty map must not become a query with an empty `IN ()`, which is a syntax error."""
    document["database"]["statement_timeouts"] = {}
    roles = sorted(document["database"]["roles"].values())
    asked: list[str] = []

    inner = catalog({}, roles)

    def recording(container: str, database: str, sql: str) -> str:
        asked.append(sql)
        return inner(container, database, sql)

    monkeypatch.setattr(bootstrap, "query", recording)
    assert bootstrap.check_violations("c", "d", document) == []
    assert not any("rolconfig" in sql for sql in asked)


# ---------------------------------------------------------------------------
# The connection budget, divided (D161, ADR 0070)
# ---------------------------------------------------------------------------


#: The one fact here that is NOT read from the product (ADR 0116, ADR 0137).
#:
#: Everything else about the membership set is derived from
#: `bootstrap.AUTHENTICATOR_REQUEST_ROLES`, because a copy is what let the last
#: two changes through -- this module carried a fourth one until Session 8 Run 2,
#: alongside the two `check_violations` carried, alongside the constant that
#: exists to stop exactly this (D301). But a set derived entirely from the
#: product's own constant cannot refuse a bad edit to that constant, which is
#: D300's warning. So one name stays written down.
#:
#: **It was `agent_writer` until Session 9 Run 2, and that was the wrong KIND of
#: anchor.** A name held here because a later session is expected to activate it
#: has an expiry date: it does its job until that session arrives, and then the
#: correct edit is to remove it -- which leaves the derived set with nothing
#: holding it, at exactly the moment the constant is being changed. The anchor
#: has to name a role that must **never** be a request role, so that moving this
#: line is always a mistake rather than sometimes a milestone.
#:
#: `mcp_audit_service` is that role. It is a service identity that authenticates
#: as nothing over HTTP, and ADR 0135 decided it stays unactivated rather than
#: deferring the question again -- so there is no session in which granting the
#: authenticator a membership of it is the right thing to do.
NEVER_A_REQUEST_ROLE = "mcp_audit_service"


def _authenticator_grants(statements: list[str], roles: dict[str, str]) -> dict[str, str]:
    """Every `GRANT <role> TO <authenticator>` the plane emits, by suffix."""
    target = roles["postgrest_authenticator"]
    found: dict[str, str] = {}
    for statement in statements:
        if not statement.startswith("GRANT ") or f'TO "{target}"' not in statement:
            continue
        for suffix, name in roles.items():
            if statement.startswith(f'GRANT "{name}" '):
                found[suffix] = statement
    return found


def test_the_authenticator_is_granted_every_request_role_and_no_other(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """Found by mutation: nothing asserted these grants existed.

    The catalogue verifier reads them back, but its rig answers the membership
    question from a fake -- so adding `agent_reader` to the loop that BUILDS the
    grants left the whole suite green. This reads the statements themselves.

    **Against the product's own enumeration, since Session 8 Run 2.** It used to
    compare them against a copy of the list kept here, which is the same defect
    D301 records and which had by then been made four times: the constant, two
    literals in `check_violations`, and this one. What the comparison still buys
    with the copy gone is real -- the builder can emit one grant fewer than the
    constant has entries, or emit a role name that is not the derived one, and
    both fail here. What it can no longer catch is a bad edit to the constant
    itself, which is why `test_the_session_nine_role_is_not_activated` exists
    beside it and names a role rather than deriving one.
    """
    roles = document["database"]["roles"]
    granted = _authenticator_grants(bootstrap.build_statements(document, INSTANCE_UUID), roles)
    expected = set(bootstrap.AUTHENTICATOR_REQUEST_ROLES)

    assert set(granted) == expected, (
        f"the authenticator is granted {sorted(granted)}; "
        f"AUTHENTICATOR_REQUEST_ROLES names {sorted(expected)}"
    )

    # The complement, over the project's own declared roles. `object_owner` is
    # excluded because `migration_user`'s membership of it is a different
    # relation with its own assertion. Derived rather than listed, so a role
    # this release does not activate is refused whether or not anybody thought
    # to name it -- the two-name literal this replaced would have left
    # `app_runtime`, `auth_service` and `storage_service` forbidden by nothing.
    forbidden = {
        key for key in roles if key not in expected | {"postgrest_authenticator", "object_owner"}
    }
    leaked = sorted(forbidden & set(granted))
    assert not leaked, (
        f"the authenticator is granted {leaked}, which this release does not activate. "
        "A token naming one of them must fail at SET ROLE"
    )


def test_a_service_identity_is_never_a_request_role(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """The one membership fact this module states rather than derives (ADR 0137).

    Every other assertion about the membership set reads
    `AUTHENTICATOR_REQUEST_ROLES`, which means a bad edit to that constant would
    be invisible to all of them -- D300's warning, and the reason this test does
    not derive its subject.

    **The subject changed in Session 9 Run 2 and the change is the point.** This
    used to name `agent_writer`, on the ground that activating it was Session 9's
    decision. Session 9 activated it, so the anchor's correct edit was to remove
    it -- leaving the derived set unanchored exactly when the constant moved.
    An anchor that expires is not an anchor.

    `mcp_audit_service` cannot expire that way: it is a service identity, it
    authenticates as nothing over HTTP, and ADR 0135 decided it stays unactivated
    rather than deferring the question. Granting the authenticator a membership
    of it is wrong in every session, which is what an anchor has to be.

    Goes red if: a service identity joins `AUTHENTICATOR_REQUEST_ROLES`; or the
    statement builder emits a grant for one by some other route, which is worse
    than the grant itself.
    """
    roles = document["database"]["roles"]
    granted = _authenticator_grants(bootstrap.build_statements(document, INSTANCE_UUID), roles)

    assert NEVER_A_REQUEST_ROLE not in bootstrap.AUTHENTICATOR_REQUEST_ROLES, (
        f"{NEVER_A_REQUEST_ROLE} is in AUTHENTICATOR_REQUEST_ROLES. It is a service "
        "identity that authenticates as nothing over HTTP; a token naming it must fail "
        "at SET ROLE (ADR 0135, ADR 0137)"
    )
    assert NEVER_A_REQUEST_ROLE not in granted, (
        f"{NEVER_A_REQUEST_ROLE} is granted to the authenticator by a route that does "
        "not go through AUTHENTICATOR_REQUEST_ROLES, which is worse than the grant itself"
    )


def test_every_request_role_grant_carries_the_three_options(
    bootstrap: Any, document: dict[str, Any]
) -> None:
    """`INHERIT FALSE` is not cosmetic, and a plain GRANT does not imply it.

    Measured on the locked image: a `GRANT` without the options records
    `inherit_option = true`, which would give the authenticator every request
    role's reach merely by connecting -- no `SET ROLE` needed, and no request
    involved. `SET TRUE` is what makes impersonation work at all, and
    `ADMIN FALSE` stops a compromised authenticator handing the membership on.
    """
    roles = document["database"]["roles"]
    granted = _authenticator_grants(bootstrap.build_statements(document, INSTANCE_UUID), roles)

    for suffix, statement in sorted(granted.items()):
        assert statement.endswith("WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;"), (
            f"the grant of {suffix} is {statement!r}, which does not carry the three "
            "options; a plain GRANT records inherit_option = true"
        )


def test_the_two_limits_and_the_reserve_fit_what_the_server_will_give(bootstrap: Any) -> None:
    """The property the old code could not have: the parts add up.

    `app_runtime` used to be given `maximum - reserved - headroom` -- everything
    -- and the authenticator nothing, because a ceiling for the API on top of
    everything is two limits that sum past what the server hands out. That is a
    budget that looks computed and is not.

    Four claimants since ADR 0099. **Five since ADR 0148**, and the sum is the
    same relation -- re-derived to five rather than weakened, which is what an
    ADR authorises a passing assertion to become (D518). The backup identity is
    the fifth, and it is in this sum because it carries a server-enforced
    `CONNECTION LIMIT`; a ceiling this arithmetic cannot see is how the enforced
    limits come to exceed what the server hands out with every check passing.
    """
    maximum, reserved = 56, 3
    api_budget, auth_budget, storage_budget = 13, 6, 6
    application, api, auth, storage, backup = bootstrap.connection_limits(
        maximum, reserved, api_budget, auth_budget, storage_budget, 20
    )

    assert api == api_budget, "the API's ceiling is not the figure the document published"
    assert auth == auth_budget, "the auth service's ceiling is not the document's figure"
    assert storage == storage_budget, "the storage service's ceiling is not the document's figure"
    assert backup == config.BACKUP_RESERVED_CONNECTIONS, (
        "the backup identity's ceiling is not `config.BACKUP_RESERVED_CONNECTIONS`. That "
        "constant is the ONE authority over this number -- the manifest check in "
        "`config._validate_connection_budget` charges the same value -- and a second "
        "literal in this plane is two arithmetics over one budget (D327, D545)"
    )
    assert application > 0
    assert (
        application + api + auth + storage + backup + bootstrap.OPERATIONAL_CONNECTION_HEADROOM
        == maximum - reserved
    ), (
        "the five limits and the operational headroom do not account for exactly what the "
        "server will hand out; one of them is being computed independently of the others"
    )


def test_the_application_gets_what_is_left_rather_than_a_chosen_number(bootstrap: Any) -> None:
    """Raising the API's commitment lowers the application's, one for one.

    Written as a difference rather than against a literal: a division that
    ignored the API's figure would return the same number for both calls and
    pass any single-value assertion.

    `pooler_pool_size` is 1 so that the second call -- which deliberately drives
    the remainder low -- fails this test's own assertion if the relation breaks,
    rather than being refused by the pooler guard that
    `test_a_remainder_below_the_poolers_pool_is_refused` owns.
    """
    small, *_ = bootstrap.connection_limits(56, 3, 10, 6, 6, 1)
    large, *_ = bootstrap.connection_limits(56, 3, 20, 6, 6, 1)
    assert small - large == 10, (
        "the application's ceiling did not move with the API's; the two are not being "
        "divided out of one budget"
    )


def test_the_application_gives_way_to_the_storage_claimant_too(bootstrap: Any) -> None:
    """The fourth claimant is divided out of the same budget, not added beside it.

    The same difference-shaped assertion the API gets, applied to the argument
    ADR 0099 introduced. Without it the new parameter would be exercised only as
    a passenger -- present in every call and load-bearing in none, which is the
    shape D260 found three times in one run.
    """
    small, *_ = bootstrap.connection_limits(56, 3, 13, 6, 2, 1)
    large, *_ = bootstrap.connection_limits(56, 3, 13, 6, 6, 1)
    assert small - large == 4, (
        "the application's ceiling did not move with the storage service's; the fourth "
        "claimant is not being divided out of the one budget"
    )


def test_the_application_gives_way_to_the_backup_claimant_too(
    bootstrap: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fifth claimant is divided out of the same budget, not added beside it.

    The same difference-shaped assertion the API and the storage service get,
    and it exists for the reason theirs do: without it the new term would be
    exercised only as a passenger -- present in every call and load-bearing in
    none, which is D260's shape found three times in one run.

    **Driven by moving the constant rather than by passing an argument**, because
    the backup figure deliberately is not a parameter: it is a constant of the
    release, not a manifest `pool_size` (ADR 0148). Monkeypatching it is
    therefore the only way to vary it -- and a test that could not vary it would
    be asserting a literal against itself.
    """
    monkeypatch.setattr(config, "BACKUP_RESERVED_CONNECTIONS", 2)
    small, *_ = bootstrap.connection_limits(56, 3, 13, 6, 6, 1)
    monkeypatch.setattr(config, "BACKUP_RESERVED_CONNECTIONS", 6)
    large, *_ = bootstrap.connection_limits(56, 3, 13, 6, 6, 1)

    assert small - large == 4, (
        "the application's ceiling did not move with the backup identity's; the fifth "
        "claimant is being added beside the budget rather than divided out of it, which "
        "is the arithmetic that hands out more connections than the server has"
    )


def test_the_bootstrap_plane_does_not_restate_the_backup_figure(bootstrap: Any) -> None:
    """One authority over the number, and the other plane imports it (D545).

    `config._validate_connection_budget` charges this figure against the
    manifest and `connection_limits` charges it against the live server. Two
    literals with one meaning is D327 exactly -- the manifest's arithmetic and
    the bootstrap plane's *"agreed by coincidence, 23 against 20"*, and nothing
    compared them until Session 7.

    **What would have to break for this to go red:** somebody types `2` into
    `bin/postgres-bootstrap.py` instead of importing it.

    **This was a text scan and the battery killed it.** M9 replaced
    `backup_budget = config.BACKUP_RESERVED_CONNECTIONS` with `backup_budget = 2`
    and this test still passed, because the string `config.BACKUP_RESERVED_-
    CONNECTIONS` also appears in a COMMENT a few lines above the import. That is
    D277 exactly -- *a scan asking whether a name is mentioned is satisfied by
    dead code* -- and D464 is the standing example in this repository of a text
    scan producing a false positive.

    So the assertion is on what the code PRODUCES: the value bound to
    `backup_budget` inside `connection_limits` must be an attribute access on
    `config`, read from the syntax tree, where a comment cannot reach and a
    literal cannot hide.
    """
    tree = ast.parse((REPO_ROOT / "bin" / "postgres-bootstrap.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "connection_limits"
    )
    bindings = [
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "backup_budget" for t in node.targets)
    ]
    assert len(bindings) == 1, (
        f"`backup_budget` is bound {len(bindings)} times in `connection_limits`; this "
        "assertion cannot say which binding the arithmetic used"
    )
    bound = bindings[0]
    assert isinstance(bound, ast.Attribute) and bound.attr == "BACKUP_RESERVED_CONNECTIONS", (
        f"`backup_budget` is bound to {ast.dump(bound)}, not to an attribute of `config`. "
        "A literal here is a second authority over one number: the manifest check charges "
        "`config.BACKUP_RESERVED_CONNECTIONS` and this plane would charge its own copy, "
        "which is two arithmetics over one budget (D327)"
    )
    assert isinstance(bound.value, ast.Name) and bound.value.id == "config", (
        f"`backup_budget` reads BACKUP_RESERVED_CONNECTIONS from {ast.dump(bound.value)}, "
        "not from `config`"
    )

    # And the arithmetic actually uses it, rather than binding it and ignoring it.
    application, *_ = bootstrap.connection_limits(56, 3, 13, 6, 6, 1)
    assert application == (56 - 3) - 13 - 6 - 6 - config.BACKUP_RESERVED_CONNECTIONS - (
        bootstrap.OPERATIONAL_CONNECTION_HEADROOM
    ), "the remainder does not reflect `config.BACKUP_RESERVED_CONNECTIONS`"


def test_the_headroom_is_held_back_from_all_of_them(bootstrap: Any) -> None:
    """It is what leaves a psql available when this arithmetic is wrong.

    **The headroom does not move when a claimant is added**, and that is the
    half worth asserting after ADR 0148: the fifth claimant's two connections
    are charged to the application's remainder, not taken out of the slack that
    keeps a psql available. Charging them to the headroom would have been the
    invisible way to pay for a backup.
    """
    application, api, auth, storage, backup = bootstrap.connection_limits(56, 3, 13, 6, 6, 20)
    assert (56 - 3) - application - api - auth - storage - backup == (
        bootstrap.OPERATIONAL_CONNECTION_HEADROOM
    )


def test_a_remainder_below_the_poolers_pool_is_refused(bootstrap: Any) -> None:
    """D327, and it is the reason ADR 0099 exists rather than a number choice.

    `default_pool_size` is per (user, database) and `app_runtime` is the pooler's
    only application user, so a remainder below it is a pool the pooler cannot
    fill. PostgreSQL refuses the backend with `too many connections for role`,
    PgBouncer hands that to the client, and the message names the role rather
    than the arithmetic that produced it.

    **Paired with a control that differs in one field.** The arm is the same
    call with `max_connections` at 50 -- what it was before this session -- which
    is exactly the state a cluster is in until its restart. Without the control
    a passing test would not distinguish "refuses correctly" from "refuses
    everything".
    """
    # Control: 56 leaves the application 21, above the pooler's 20.
    #
    # **21 rather than the 23 this asserted through Session 9**, and the two are
    # the price of ADR 0148's fifth claimant, stated here rather than discovered:
    # the backup identity's two connections come out of the application's
    # remainder, so its slack over the pooler's pool is 1 where it was 3. Nothing
    # is weakened -- the relation asserted is the same one, against the division
    # the current arithmetic actually computes.
    application, *_ = bootstrap.connection_limits(56, 3, 13, 6, 6, 20)
    assert application == 21, (
        "the control does not produce the division ADR 0148 computed; the arm below would "
        "be measuring something else"
    )

    # Arm: one field differs. 50 leaves 15, and 15 < 20.
    with pytest.raises(ValueError, match=r"below the pooler's server-side pool"):
        bootstrap.connection_limits(50, 3, 13, 6, 6, 20)


def test_the_pooler_refusal_names_a_max_connections_that_would_work(bootstrap: Any) -> None:
    """The message carries the number, and the number is right.

    A refusal that says "raise max_connections" and leaves the operator to redo
    the arithmetic is a refusal that gets guessed at. This asserts the suggested
    ceiling actually passes, by calling with it -- so the message cannot drift
    into naming a value that still fails.
    """
    with pytest.raises(ValueError) as caught:
        bootstrap.connection_limits(50, 3, 13, 6, 6, 20)

    match = re.search(r"at least (\d+)", str(caught.value))
    assert match, f"the refusal names no ceiling to raise to: {caught.value}"

    suggested = int(match.group(1))
    application, *_ = bootstrap.connection_limits(suggested, 3, 13, 6, 6, 20)
    assert application >= 20, (
        f"the refusal suggested max_connections={suggested}, and at that value the "
        f"application still gets {application} against a pooler pool of 20"
    )


@pytest.mark.parametrize(
    ("maximum", "reserved", "api_budget", "auth_budget", "storage_budget"),
    [
        (10, 3, 13, 6, 6),  # the API alone exceeds what is available
        (10, 3, 2, 6, 6),  # nothing left after the headroom
        (8, 3, 1, 6, 6),  # a tiny cluster
        (5, 5, 1, 6, 6),  # the reservation takes everything
        # The third claimant's own case: everything else fits and the auth
        # service is what tips it over. Without this the parameter set would
        # exercise the new argument only as a passenger.
        (30, 3, 13, 20, 2),
        # The fourth claimant's own case, added by ADR 0099 for the same reason.
        (30, 3, 13, 6, 20),
    ],
)
def test_a_budget_that_does_not_fit_raises_rather_than_returning_a_number(
    bootstrap: Any,
    maximum: int,
    reserved: int,
    api_budget: int,
    auth_budget: int,
    storage_budget: int,
) -> None:
    """A negative limit is 'unlimited' to PostgreSQL and 0 is 'refuse every login'.

    Both are values it would accept and neither is what the arithmetic meant, so
    an error is the only honest failure. Written as literals rather than derived
    from the constant, so emptying the constant cannot empty the parameter set
    (D190).

    `pooler_pool_size` is 1 here on purpose: every case must fail on the
    *remainder* being unusable, not on the pooler check that
    `test_a_remainder_below_the_poolers_pool_is_refused` owns. A parameter set
    where two different guards could produce the same exception is a set that
    stops distinguishing them the day one of them breaks.
    """
    with pytest.raises(ValueError, match=r"would be left with"):
        bootstrap.connection_limits(maximum, reserved, api_budget, auth_budget, storage_budget, 1)


def test_the_authenticator_is_activated_with_its_ceiling(bootstrap: Any) -> None:
    """D161 is closed, and the comment that recorded it is gone.

    The role was activated with LOGIN and a password and deliberately no
    CONNECTION LIMIT, because half the arithmetic had nowhere to come from. The
    document now carries that half.
    """
    source = (REPO_ROOT / "bin" / "postgres-bootstrap.py").read_text(encoding="utf-8")
    assert "no CONNECTION LIMIT yet" not in source, "the D161 placeholder is still in the code"
    assert "connection_limit=api_limit" in source, "the authenticator is activated without a limit"
    assert 'api_budget = int(document["database"]["api_connection_budget"])' in source, (
        "the API's ceiling is computed here rather than read from the document"
    )

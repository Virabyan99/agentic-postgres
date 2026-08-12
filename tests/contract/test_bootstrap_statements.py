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

import importlib.util
import json
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, output_migrations

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

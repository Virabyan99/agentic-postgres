"""Installing a definition: the statement is a constant and the values are psql variables.

Four things are guarded here, and each one is a thing that has gone wrong
somewhere in this tree before:

1. **The SQL is never formatted.** An author's description concatenated into a
   statement the bootstrap superuser runs is the oldest shape there is. The
   guard is an AST scan of the module, not a reading of the one call site.
2. **The statement goes to STDIN, and `-c` would not work.** Rig 32g measured
   it: `psql -v body=… -c "SELECT :'body'"` fails with `syntax error at or near
   ":"`, because a `-c` string never passes through psql's lexer, which is what
   substitutes. A `-c` here would be a refusal at step 6d on the host (D1684).
3. **The call's arity is the migration's.** The statement names six values and
   `app_private.workflow_install_definition` declares six parameters; the
   number is read out of the migration rather than written here twice.
4. **Step 6d is where the deploy says it is** -- after step 6 has migrated and
   before step 6b starts the services -- read out of `bin/deploy-project.py`'s
   AST, because the ordering is the property and a comment saying so is not.

Nothing here reaches a database. Whether the function behaves is
`test_workflow_substrate.py`'s question, under a real cluster.
"""

from __future__ import annotations

import ast
import re

import pytest

from agentic_postgres import REPO_ROOT, workflow_install
from agentic_postgres import workflow_definition as wd

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

MODULE = REPO_ROOT / "src" / "agentic_postgres" / "workflow_install.py"
DEPLOY = REPO_ROOT / "bin" / "deploy-project.py"
MIGRATION = REPO_ROOT / "migrations" / "templates" / "0034-workflow-substrate.sql"


@pytest.fixture(scope="module")
def compiled() -> wd.Compiled:
    lock = wd.lock_view_for_project(REPO_ROOT / "project.example.yaml")
    return wd.compile_file(
        REPO_ROOT / "projects" / "example" / "workflows" / "notes-roundtrip.yaml", lock
    )


def test_no_sql_in_this_module_is_built_from_a_value() -> None:
    """**The scan, not the call site** (D600's shape: guard the class).

    An f-string, a `%` or a `.format(` whose text carries SQL is refused
    wherever it appears in this module. The module DOES use f-strings -- for
    `-v name=…`, which is an argv element and not SQL -- so a blanket ban would
    be a rule nobody could keep; what is banned is a formatted string that
    contains a SQL keyword.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    keywords = re.compile(r"\b(select|insert|update|delete|app_private)\b", re.IGNORECASE)

    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            literal = "".join(part.value for part in node.values if isinstance(part, ast.Constant))
            assert not keywords.search(literal), f"an f-string carries SQL: {literal!r}"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            rendered = ast.unparse(node)
            assert not keywords.search(rendered), f"a %-format carries SQL: {rendered!r}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "format":
                rendered = ast.unparse(node)
                assert not keywords.search(rendered), f"a .format carries SQL: {rendered!r}"


def test_the_statement_is_one_constant_and_the_caller_cannot_change_it(
    compiled: wd.Compiled,
) -> None:
    statements = workflow_install.statements(compiled)
    assert len(statements) == 1
    assert statements[0].stdin == workflow_install.INSTALL_SQL
    # Nothing an author wrote appears in the statement.
    assert compiled.name not in workflow_install.INSTALL_SQL
    assert compiled.description not in workflow_install.INSTALL_SQL


def test_the_values_travel_as_psql_variables_and_the_sql_travels_on_stdin(
    compiled: wd.Compiled,
) -> None:
    """**D1684.** `-f -` and not `-c`, with every value behind `-v`.

    The two halves are one decision: `-c` does not interpolate, so a statement
    built with `-c` would carry `:'body'` to the server as text.
    """
    statement = workflow_install.statements(compiled)[0]
    assert statement.argv[-2:] == ("-f", "-")
    assert "-c" not in statement.argv, (
        "a -c string never passes through psql's lexer, so the variables would "
        "reach the server unsubstituted (rig 32g)"
    )

    variables = {
        statement.argv[index + 1].split("=", 1)[0]
        for index, flag in enumerate(statement.argv)
        if flag == "-v"
    }
    assert {"name", "version", "body", "source", "lock", "scopes"} <= variables

    # Every value the row takes is in the argv exactly once, and the body is
    # the compiled document rather than the file's text.
    joined = "\x00".join(statement.argv)
    assert f"name={compiled.name}" in joined
    assert f"source={compiled.source_sha256}" in joined
    assert f"lock={compiled.lock_tools_sha256}" in joined
    assert '"schema_version":1' in joined


def test_the_statement_names_as_many_values_as_the_migration_declares() -> None:
    """The arity is read from migration 0034, never written here twice.

    A seventh parameter added to the function and not to this statement would
    otherwise be a runtime error on the host at step 6d, on a cluster the
    deploy has already migrated.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    signature = re.search(
        r"CREATE FUNCTION app_private\.workflow_install_definition\((.*?)\)\s*RETURNS",
        sql,
        re.DOTALL,
    )
    assert signature is not None, "the migration no longer declares this function by that name"
    declared = [
        line.strip()
        for line in signature.group(1).split(",")
        if line.strip() and not line.strip().startswith("--")
    ]
    supplied = re.findall(r":'([a-z_]+)'", workflow_install.INSTALL_SQL)
    assert len(supplied) == len(declared), (
        f"the migration declares {len(declared)} parameters {declared} and the "
        f"statement supplies {len(supplied)} {supplied}"
    )


def test_a_scope_name_the_compiler_could_not_have_derived_is_refused() -> None:
    """The array literal is built by joining on a comma, so a scope carrying
    one would silently become two. It cannot occur -- scopes are
    `<relation>:read`-shaped names read off the lock -- and a value that cannot
    occur is one whose escaping nobody would ever test, so it is refused."""
    for bad in ("a,b", "a{b", 'a"b', "a b", ""):
        with pytest.raises(ValueError, match="not a scope name"):
            workflow_install._scopes_literal((bad,))
    assert workflow_install._scopes_literal(("notes:read", "notes:write")) == (
        "{notes:read,notes:write}"
    )


# ---------------------------------------------------------------------------
# Where step 6d sits in the deploy
# ---------------------------------------------------------------------------


def _step_labels() -> list[str]:
    """Every `step("…")` label the deploy emits, in source order."""
    tree = ast.parse(DEPLOY.read_text(encoding="utf-8"))
    labels: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "step"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            labels.append((node.lineno, node.args[0].value))
    return [label for _, label in sorted(labels)]


def test_step_6d_installs_definitions_after_the_migration_and_before_the_services() -> None:
    """**The ordering is the property.**

    After step 6, because `workflow_install_definition` is a released
    migration's function and does not exist until the migrations have applied.
    Before step 6b, because a definition is state the plane may serve the
    moment it starts -- installing it afterwards leaves a window in which
    `POST /workflows/runs` answers *no such definition* about a definition this
    deploy is about to install.
    """
    labels = _step_labels()
    positions = {
        name: index
        for index, label in enumerate(labels)
        for name in ("6.", "6b.", "6d.")
        if label.startswith(name)
    }
    assert set(positions) == {"6.", "6b.", "6d."}, (
        f"the deploy's step labels are {labels}; this proof reads three of them by "
        "prefix and one is missing"
    )
    assert positions["6."] < positions["6d."] < positions["6b."], (
        f"step 6d is at {positions['6d.']}, step 6 at {positions['6.']} and step 6b "
        f"at {positions['6b.']}"
    )


def test_the_deploy_installs_definitions_as_the_superuser_over_the_socket() -> None:
    """`workflow_install_definition` is granted to NOBODY (ADR 0228).

    So the only caller is the bootstrap superuser over the container's own
    socket. A deploy that reached it as the service role would mean the
    migration's grant list had been widened, and this reads the call site
    rather than the grant.
    """
    source = DEPLOY.read_text(encoding="utf-8")
    call = source[source.index("def install_workflow_definitions") :]
    call = call[: call.index("\ndef ", 1)]
    assert '"-U",\n                "postgres",' in call, (
        "step 6d no longer connects as the OS postgres user"
    )
    assert "container_exec.run(" in call, (
        "step 6d builds a docker exec argv by hand; new code uses container_exec.run (ADR 0218)"
    )
    assert "input=statement.stdin" in call, (
        "the statement's stdin is not passed, so psql would read nothing from -f - "
        "and exit 0 having executed nothing"
    )

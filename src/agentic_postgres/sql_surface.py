"""One interpreter for what a migration set publishes in `api`.

Lifted, unchanged in behaviour, out of `tests/contract/test_api_migrations.py`,
where it had been the only reader of released SQL since Session 5. It becomes a
module in Session 20 for one reason: **a project's set needs the same reader as
the release's**, and a second copy would drift. A tenant's views would then be
read by an interpreter that had never been corrected by D1036 — the defect where
`_CREATE_VIEW` accepted a bare `CREATE VIEW` and not `CREATE OR REPLACE VIEW`,
so a view added the ordinary way was published to clients, named in no reviewed
document, and invisible to the equality that exists to catch exactly that.

`test_api_migrations.py` imports these names back and **its assertions do not
change** (D1089). That is deliberate: the release's anti-vacuity guard keeps its
equality against `{"notes","tasks"}`, because with a project's set separate the
release's reader never sees a project's object. Loosening an equality to a
containment check is what the non-negotiables call weakening, and the design
removes the need for it.

**This is a text reader, not a parser.** It knows the shapes this repository's
own migrations use and refuses to guess at others; `lint_project_set` in
`migrations.py` is what stops a project set from using a shape this cannot see.
The two are a pair: the reader says what a set publishes, and the lint bounds a
set to what the reader can read.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

#: `OR REPLACE` is optional here for the same reason it is optional in
#: `_CREATE_FUNCTION`, and the asymmetry between the two was a hole rather than
#: a style difference (D1036).
#:
#: Measured: migration 0004 creates api.notes and api.tasks with
#: `CREATE OR REPLACE VIEW`, and 0007 recreates them with a bare `CREATE VIEW`.
#: This reader saw the published surface at all ONLY because 0007 happens to use
#: the bare form -- luck, and load bearing for every relation assertion written
#: against it.
#:
#: The direction that matters is the silent one. A view added with OR REPLACE
#: never enters `final_surface`, so it is absent from the left side of the
#: equality against the reviewed contract, so the equality holds while the view
#: is published to clients and named in no reviewed document.
CREATE_VIEW = re.compile(
    r"CREATE (?:OR REPLACE )?VIEW api\.(\w+)\b.*?AS\s+SELECT\s+(.*?)\s+FROM\b", re.DOTALL
)
DROP_VIEW = re.compile(r"DROP VIEW api\.(\w+)")
CREATE_FUNCTION = re.compile(
    r"CREATE (?:OR REPLACE )?FUNCTION api\.(\w+)\s*\((.*?)\)\s*\n\s*RETURNS", re.DOTALL
)
DROP_FUNCTION = re.compile(r"DROP FUNCTION api\.(\w+)")
CREATE_ENUM = re.compile(r"CREATE TYPE api\.(\w+) AS ENUM \((.*?)\)", re.DOTALL)

#: A `RAISE EXCEPTION` and everything up to the statement terminator, so the
#: `USING` clause that follows it is part of the match.
RAISE = re.compile(r"RAISE EXCEPTION\s+(.*?);", re.DOTALL)

DOWN_MARKER = "-- migrate:down"


def up_section(text: str) -> str:
    """Only the applied half. A `migrate:down` block is unreachable SQL."""
    return text.split(DOWN_MARKER)[0]


def down_section(text: str) -> str:
    """Only the half dbmate would run on a rollback, which here must refuse.

    Returns the empty string for a template with no `down` marker at all --
    which the lint treats as a failure rather than as an empty rollback, because
    a set with no refusal is a set dbmate would happily roll back.
    """
    _, marker, rest = text.partition(DOWN_MARKER)
    return rest if marker else ""


def sql_only(text: str) -> str:
    """The statements, with the reasoning stripped out.

    Needed because these files argue with themselves: the comment above the
    pre-request hook explains that `pg_catalog.nullif` is the spelling that
    broke, so a test forbidding that string matched the sentence forbidding it.
    That is Session 2 Run 7's defect exactly -- a substitution that also matched
    the comment documenting the substitution.

    Line comments only. None of these templates has a `--` inside a string
    literal, and a reader that quietly stopped working if one appeared would be
    worse than one that never handled the case: the anti-vacuity assertions on
    both sides fail if this strips too much.
    """
    return "\n".join(line.split("--")[0] for line in text.splitlines())


def statements(text: str) -> str:
    """One template's applied statements, with its reasoning removed."""
    return sql_only(up_section(text))


def final_surface(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    """What `api` holds after every migration in one set has been applied.

    ``root`` is the set's own directory -- `migrations/` for the release,
    `projects/<slug>/migrations/` for a project. It is a parameter and not a
    default because the eleven callers that took the default are the whole of
    D1088, and a default here would put a twelfth back.

    Applied in manifest order, which `_assert_manifest_semantics` has already
    proved is ascending version order, which is the order dbmate applies. A
    reader that walked the directory instead would answer a different question
    from the one the cluster answers.
    """
    views: dict[str, list[str]] = {}
    functions: dict[str, list[str]] = {}
    enums: dict[str, list[str]] = {}

    for entry in manifest["migrations"]:
        body = statements((root / entry["template"]).read_text(encoding="utf-8"))

        for name in DROP_VIEW.findall(body):
            views.pop(name, None)
        for name in DROP_FUNCTION.findall(body):
            functions.pop(name, None)

        for name, columns in CREATE_VIEW.findall(body):
            views[name] = [column.strip() for column in columns.replace("\n", " ").split(",")]
        for name, arguments in CREATE_FUNCTION.findall(body):
            # Parameter names only: the wire format is the name, and the type is
            # what the contract deliberately does not carry.
            functions[name] = [
                argument.strip().split()[0]
                for argument in arguments.replace("\n", " ").split(",")
                if argument.strip()
            ]
        for name, values in CREATE_ENUM.findall(body):
            enums[name] = [value.strip().strip("'") for value in values.split(",")]

    return {"views": views, "functions": functions, "enums": enums}


def published_names(surface: dict[str, Any]) -> set[str]:
    """Every name a surface publishes, across all three kinds.

    One set rather than three, because the question a caller usually has --
    "does this set publish anything the release already owns?" -- does not care
    which kind the collision is in, and answering it three times is how one of
    them gets forgotten.
    """
    return set(surface["views"]) | set(surface["functions"]) | set(surface["enums"])


__all__ = [
    "CREATE_ENUM",
    "CREATE_FUNCTION",
    "CREATE_VIEW",
    "DOWN_MARKER",
    "DROP_FUNCTION",
    "DROP_VIEW",
    "RAISE",
    "down_section",
    "final_surface",
    "published_names",
    "sql_only",
    "statements",
    "up_section",
]

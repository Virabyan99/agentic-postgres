"""Installing a compiled definition: the psql invocation, and nothing else.

One statement per definition, built here so that the deploy's step 6d and
`apg dev up` issue the same one (ADR 0203's rule for the bootstrap statements,
applied to this). The caller supplies the container, the database and the user;
this supplies the argv and refuses to build anything else.

**Every value is a psql VARIABLE, never formatted into the SQL.** `-v body=…`
and `:'body'` is psql's own parameterisation: the value is quoted as a literal
by psql, after argv parsing, so a definition whose description contains a
quote is a description and not a syntax error. The SQL text this module emits
is a constant -- a proof reads the module's AST and refuses an f-string, a `%`
or a `.format(` anywhere near it -- because the alternative is a document an
author writes being concatenated into a statement the superuser runs.

**The statement goes to STDIN through `-f -`, and `-c` would not work at all**
(D1684). Rig 32g measured it: `psql -v body=… -c "SELECT length(:'body')"`
fails with `syntax error at or near ":"`, because a `-c` string is sent to the
server without passing through psql's own lexer, which is what performs the
substitution. The same statement on stdin interpolates correctly, survives a
value carrying a quote, a backslash, a newline and a `$$`, and -- the property
that matters most -- REFUSES with the same syntax error when a variable is
unset, rather than substituting an empty string. A missing value cannot become
a silently installed empty definition.

The one function the deploy calls with this is `workflow_install_definition`,
which migration 0034 grants to NOBODY: the deploy calls it as the bootstrap
superuser over the container's own socket, and a grant to the role the HTTP
routes run as would put a definition-writing authority behind an identity
reachable over the network (ADR 0228).
"""

from __future__ import annotations

import json
from typing import NamedTuple

from agentic_postgres.workflow_definition import Compiled

#: The call, verbatim and constant. Six arguments, in the function's own order.
INSTALL_SQL = (
    "SELECT app_private.workflow_install_definition("
    ":'name', :'version'::integer, :'body'::jsonb, "
    ":'source', :'lock', :'scopes'::text[])"
)

#: The psql flags every statement carries. `ON_ERROR_STOP` because the whole
#: point of `PT409` is that it stops the deploy; `-qtA` because the only output
#: wanted is the returned uuid; `-X` because a `.psqlrc` on a host is not part
#: of this release.
PSQL_FLAGS = ("-X", "-v", "ON_ERROR_STOP=1", "-qtA")


class InstallStatement(NamedTuple):
    """One definition's psql invocation: the argv after `psql`, and its stdin.

    The pair is the unit because the two halves are one decision: the values go
    in the argv as psql variables and the statement goes in the stdin, and a
    caller that took only the argv would run `psql -f -` with nothing on its
    input and exit 0 having executed nothing -- which is the silent failure
    `postgres-bootstrap.psql`'s own comment records about the missing `-i`.
    """

    argv: tuple[str, ...]
    stdin: str


def _scopes_literal(scopes: tuple[str, ...]) -> str:
    """A PostgreSQL array literal for `:'scopes'::text[]`.

    Scopes are `<relation>:read`-shaped names the compiler derived from the
    lock, so a comma or a brace in one would mean the lock was wrong; it is
    refused here rather than quoted, because a value that cannot occur is one
    whose escaping nobody will ever test.
    """
    for scope in scopes:
        if not scope or any(character in scope for character in ',{}"\\ '):
            raise ValueError(f"not a scope name the compiler derives: {scope!r}")
    return "{" + ",".join(scopes) + "}"


def statements(compiled: Compiled) -> list[InstallStatement]:
    """The one invocation that installs this definition.

    A list of one, rather than one, because the deploy installs a directory and
    a caller that had to special-case the count would grow a branch the moment
    a definition needed two statements.
    """
    return [
        InstallStatement(
            argv=(
                *PSQL_FLAGS,
                "-v",
                f"name={compiled.name}",
                "-v",
                f"version={compiled.version}",
                "-v",
                "body=" + json.dumps(compiled.body(), sort_keys=True, separators=(",", ":")),
                "-v",
                f"source={compiled.source_sha256}",
                "-v",
                f"lock={compiled.lock_tools_sha256}",
                "-v",
                "scopes=" + _scopes_literal(compiled.required_scopes),
                "-f",
                "-",
            ),
            stdin=INSTALL_SQL,
        )
    ]


__all__ = ["INSTALL_SQL", "PSQL_FLAGS", "InstallStatement", "statements"]

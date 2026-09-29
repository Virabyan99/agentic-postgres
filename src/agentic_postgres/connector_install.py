"""Installing a compiled connector: the psql invocation, and nothing else (step 6e).

`workflow_install`'s shape exactly, for its reasons: every value is a psql
VARIABLE and never formatted into the SQL; the statement is one constant and
travels on stdin through `-f -`, because a `-c` string never passes through
psql's lexer and would fail at `:` (D1684); and an unset variable is a syntax
error rather than an empty string, so a missing value cannot install a
silently empty connector.

**A NULL is an empty variable.** `connector_install` takes thirteen arguments
and a kind leaves some of them NULL -- an outbound connector has no
definition, an inbound one no event and no endpoint. psql has no NULL
variable, so each nullable argument is sent as `''` and turned back into NULL
by `NULLIF` in the constant. None of them can be legitimately empty: every one
is a name, a number or a URL the compiler or the manifest's schema already
refused empty.

The function is `app_private.connector_install`, which migration 0036 grants
to NOBODY: step 6e calls it as the bootstrap superuser over the container's
own socket (ADR 0236).
"""

from __future__ import annotations

import json

from agentic_postgres.connector_definition import CompiledConnector
from agentic_postgres.workflow_install import (
    PSQL_FLAGS,
    InstallStatement,
    _scopes_literal,
)

#: The call, verbatim and constant. Thirteen arguments, in the function's order.
INSTALL_SQL = (
    "SELECT app_private.connector_install("
    ":'name', :'version'::integer, :'kind'::app_private.connector_kind, "
    ":'body'::jsonb, :'source', NULLIF(:'event', ''), NULLIF(:'endpoint', ''), "
    "NULLIF(:'definition_name', ''), NULLIF(:'definition_version', '')::integer, "
    ":'scopes'::text[], NULLIF(:'every_seconds', '')::integer, "
    "NULLIF(:'retry_max', '')::integer, NULLIF(:'backoff_seconds', '')::integer)"
)

#: The words `connector_install` returns, and so the only words step 6e prints
#: as a result.
RESULTS = ("installed", "unchanged", "endpoint_updated", "replaced", "replaced_disabled")


def _text(value: object) -> str:
    return "" if value is None else str(value)


def statements(compiled: CompiledConnector, endpoint: str | None) -> list[InstallStatement]:
    """The one invocation that installs this connector with this deployment's endpoint.

    `endpoint` is refused on anything but an outbound connector: the table's
    CHECK would refuse it too, and a deploy should say so before psql does.
    """
    if endpoint is not None and compiled.kind != "outbound":
        raise ValueError(f"{compiled.name} is {compiled.kind}; only an outbound connector sends")
    values = compiled.as_install()
    return [
        InstallStatement(
            argv=(
                *PSQL_FLAGS,
                "-v",
                f"name={values['name']}",
                "-v",
                f"version={values['version']}",
                "-v",
                f"kind={values['kind']}",
                "-v",
                "body=" + json.dumps(values["body"], sort_keys=True, separators=(",", ":")),
                "-v",
                f"source={values['source_sha256']}",
                "-v",
                f"event={_text(values['event'])}",
                "-v",
                f"endpoint={_text(endpoint)}",
                "-v",
                f"definition_name={_text(values['definition_name'])}",
                "-v",
                f"definition_version={_text(values['definition_version'])}",
                "-v",
                "scopes=" + _scopes_literal(values["required_scopes"]),
                "-v",
                f"every_seconds={_text(values['every_seconds'])}",
                "-v",
                f"retry_max={_text(values['retry_max'])}",
                "-v",
                f"backoff_seconds={_text(values['backoff_seconds'])}",
                "-f",
                "-",
            ),
            stdin=INSTALL_SQL,
        )
    ]


__all__ = ["INSTALL_SQL", "RESULTS", "statements"]

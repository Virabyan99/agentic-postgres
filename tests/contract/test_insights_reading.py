"""The insights reading on a real server (Session 42, ADR 0278, D2568).

The canary the stage plan asks for, on PostgreSQL itself rather than on a
fixture that shares the reader's belief (CLAUDE.md §7, question 6): the locked
image started with every literal `-c` of `compose.yaml`'s `postgres` command,
the bootstrap's statements applied, statements run AS each role (`SET ROLE`,
which is what PostgREST does -- rig 42b measured the extension recording the
role current at execution), then the product's own reader --
`usage_reading.insights_sql` through the container as `postgres`, and
`reconciler_dispatch.insight_sample` -- read back. A literal, a `DO` block and
a password never appear; a platform role's statement is not kept; the text is
cut at 2000.
"""

# ruff: noqa: S608 -- every interpolated value is a name or a canary this module made.

from __future__ import annotations

import json
import secrets
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import test_pg_stat_statements as pgss

from agentic_postgres import REPO_ROOT, reconciler_dispatch, usage_reading

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

CANARY = f"APG-INSIGHT-CANARY-{uuid.uuid4()}"


@pytest.fixture(scope="module")
def reading() -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """One cluster, the statements of every case run once, the reader's sample."""
    document = pgss._document_in_memory()
    database = document["database"]["name"]
    roles = document["database"]["roles"]
    lock = {
        name: value
        for name, _, value in (
            line.partition("=")
            for line in (REPO_ROOT / "versions.env").read_text("utf-8").splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    literal = [s for s in pgss._settings(pgss._release_command()) if "${" not in s]
    arguments = [part for setting in literal for part in ("-c", setting)]
    name = f"apg-insights-{secrets.token_hex(4)}"
    started = pgss.docker(
        "run", "-d", "--name", name, "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
        "-e", f"POSTGRES_DB={database}", lock["POSTGRES_IMAGE"], "postgres", *arguments,
    )  # fmt: skip
    if started.returncode != 0:
        raise RuntimeError(f"cannot start the locked cluster: {started.stderr.strip()[:200]}")
    try:
        # Two readies in a row: the image's entrypoint restarts the server once
        # after initialising (test_pg_stat_statements' loop).
        rounds = 0
        for _ in range(90):
            probe = pgss.docker("exec", name, "pg_isready", "-U", "postgres", "-d", database)
            rounds = rounds + 1 if probe.returncode == 0 else 0
            if rounds >= 2:
                break
            time.sleep(1)
        assert rounds >= 2, "the cluster never became ready"
        bootstrap = pgss._bootstrap()
        bootstrap.psql(
            name, database, "\n".join(bootstrap.build_statements(document, str(uuid.uuid4())))
        )

        def as_role(role: str, sql: str) -> None:
            done = pgss._as(name, database, sql, roles[role])
            assert done.returncode == 0, (role, sql, done.stderr)

        as_role("customer_app", f"SELECT count(*) FROM pg_class WHERE relname = '{CANARY}';")
        as_role(
            "customer_app",
            f"DO $$ BEGIN PERFORM count(*) FROM pg_class WHERE relname = '{CANARY}'; END $$;",
        )
        as_role("customer_admin", "SELECT count(*) FROM pg_namespace WHERE nspname = 'public';")
        as_role("auth_service", "SELECT count(*) FROM pg_database WHERE datname = 'platform-only';")
        long_select = "SELECT " + ", ".join(f"{i} AS column_{i:04d}" for i in range(300)) + ";"
        as_role("customer_app", long_select)
        password = pgss._as(
            name, database, f"ALTER ROLE \"{roles['customer_app']}\" PASSWORD '{CANARY}';"
        )
        assert password.returncode == 0, password.stderr
        insight_roles = tuple(roles[s] for s in reconciler_dispatch.INSIGHT_ROLE_SUFFIXES)
        answered = pgss.docker(
            "exec", "-i", name, "psql", "-U", "postgres", "-d", database, "-X", "-qtA",
            "-c", usage_reading.insights_sql(insight_roles),
        )  # fmt: skip
        assert answered.returncode == 0, answered.stderr
        raw = json.loads(answered.stdout)
        sample, why = reconciler_dispatch.insight_sample("beta-dev", raw, insight_roles)
        assert sample is not None, why
        everything = pgss._as(
            name, database, "SELECT string_agg(query, ' ') FROM extensions.pg_stat_statements;"
        )
        yield sample, {"raw": raw, "all_text": everything.stdout, "roles": roles}
    finally:
        pgss.docker("rm", "-fv", name, timeout=120)


def test_a_literal_is_normalised_away(reading: tuple[dict[str, Any], dict[str, Any]]) -> None:
    """The canary planted as a constant appears nowhere in the sample -- and
    the statement it was in IS there, normalised (`relname = $1`), under the
    role that ran it."""
    sample, _ = reading
    assert CANARY not in json.dumps(sample)
    texts = [s["query"] for s in sample["statements"]]
    assert any("relname = $1" in text for text in texts), texts


def test_a_utility_statement_is_not_recorded(
    reading: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """`track_utility = off`: the `ALTER ROLE ... PASSWORD '<canary>'` and the
    `DO` block are not in the extension at all -- not merely filtered from the
    sample -- so no password and no inner literal can reach an insight."""
    sample, extra = reading
    assert CANARY not in extra["all_text"]
    assert "password" not in extra["all_text"].lower()
    assert not any(
        s["query"].lstrip().upper().startswith(("DO ", "ALTER")) for s in sample["statements"]
    )


def test_a_platform_roles_statement_is_absent(
    reading: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """A statement run as `auth_service` (a platform role) is recorded by the
    extension and NOT kept by the reading; **control**: `customer_admin`'s
    statement is kept under its role."""
    sample, extra = reading
    roles = extra["roles"]
    kept_roles = {s["role"] for s in sample["statements"]}
    assert roles["auth_service"] not in kept_roles
    # The SQL's own role filter, on the RAW reading -- not only the dispatch's
    # check after it (each layer is held on its own).
    assert roles["auth_service"] not in {s["role"] for s in extra["raw"]["statements"]}
    assert "platform-only" not in json.dumps(sample)
    assert roles["customer_admin"] in kept_roles
    assert "datname = $1" in extra["all_text"], "the control: the platform statement WAS recorded"


def test_the_text_is_cut_at_two_thousand(reading: tuple[dict[str, Any], dict[str, Any]]) -> None:
    """A normalised text longer than 2000 characters is kept as its first 2000."""
    sample, _ = reading
    longest = max(len(s["query"]) for s in sample["statements"])
    assert longest == 2000, longest

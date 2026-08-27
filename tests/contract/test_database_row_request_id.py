"""Migration 0022 — what the `database` audit row records (ADR 0161).

Source-level, over the rendered SQL, and labelled as such: a migration is text
until a cluster applies it, and the behavioural proof is `REC`-style and lives on
the host. What *is* checkable offline is that the two facts Run 1 measured are
the ones the migration encodes — because both have a plausible wrong form that
would pass review:

* **D632** — the lowercase key, the two-argument `current_setting`, and *no*
  `nullif(…, '')`. The idiom is everywhere in this repository and is wrong here.
* **D633** — the value is shape-tested *before* it is cast. An unguarded cast
  does not fail to correlate; it rolls the caller's write back to zero rows.

These read the **rendered** migration rather than the template, so they describe
what a cluster would actually receive.
"""

from __future__ import annotations

import json
import re

import pytest

from agentic_postgres import REPO_ROOT, migrations

pytestmark = [pytest.mark.contract, pytest.mark.p0]

MIGRATION = "database_row_request_id"


@pytest.fixture(scope="module")
def rendered() -> str:
    """The rendered 0022, from whichever fixture the last render produced."""
    candidates = sorted((REPO_ROOT / ".generated").glob("*/migrations/rendered-manifest.json"))
    assert candidates, "no rendered project; run ./deploy.sh --render-only first"

    for manifest_path in candidates:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["migrations"]:
            if entry["name"] == MIGRATION:
                return (manifest_path.parent / entry["file"]).read_text(encoding="utf-8")
    pytest.fail(f"{MIGRATION} is in no rendered manifest; the render did not pick it up")


@pytest.fixture(scope="module")
def helper_body(rendered: str) -> str:
    """Just `app_private.agent_request_id`'s body."""
    return rendered.split("CREATE OR REPLACE FUNCTION app_private.agent_request_id")[1].split(
        "$fn$;"
    )[0]


# ---------------------------------------------------------------------------
# It is a migration at all
# ---------------------------------------------------------------------------


def test_it_is_declared_and_released(rendered: str) -> None:
    declared = {entry["name"] for entry in migrations.load_manifest()["migrations"]}
    assert MIGRATION in declared
    lock = json.loads((REPO_ROOT / "migrations" / "released.lock.json").read_text("utf-8"))
    names = {entry["name"] for entry in lock["migrations"]}
    assert MIGRATION in names, "0022 is not in the released lock; run bin/migrate.sh freeze-lock"


def test_its_down_block_refuses_like_every_other(rendered: str) -> None:
    """Fix-forward only. Every released migration's down block raises AP900."""
    down = rendered.split("-- migrate:down")[1]
    assert "AP900" in down


def test_it_does_not_edit_a_released_migration() -> None:
    """ADR 0091. 0019 is applied on both clusters; this had to be a new file."""
    nineteen = (
        REPO_ROOT / "migrations" / "templates" / "0019-agent-write-and-audit-plane.sql"
    ).read_text(encoding="utf-8")
    assert "agent_request_id" not in nineteen, "0019 was edited; it is released (ADR 0091)"


# ---------------------------------------------------------------------------
# D632 — how the header is read
# ---------------------------------------------------------------------------


def test_the_header_key_is_lowercase(helper_body: str) -> None:
    """Measured: a capitalised lookup read NULL in the same request the lowercase
    one succeeded, and a header sent as `x-ReQuEsT-iD` still read under the
    lowercase key. PostgREST lowercases; the lookup must match."""
    assert "'x-request-id'" in helper_body
    assert "'X-Request-Id'" not in helper_body
    assert "'X-Request-ID'" not in helper_body


def test_current_setting_is_the_two_argument_form(helper_body: str) -> None:
    """These functions are reachable from psql, where `request.headers` does not
    exist at all — and the one-argument form RAISES on an unset GUC. Measured in
    Run 1, arm 4."""
    assert "current_setting('request.headers', true)" in helper_body, (
        "the one-argument form raises when called outside a PostgREST request"
    )


def test_the_empty_string_idiom_is_not_used(helper_body: str) -> None:
    """**The idiom that is wrong here**, and it is everywhere else in this
    repository: `nullif(current_setting(...), '')` guards a GUC the pre-request
    hook sets, which reads as `''` when unset. An absent *jsonb key* is SQL NULL
    — measured both ways in one call — so copying the idiom would guard a case
    that does not occur and say nothing about the one that does."""
    assert "nullif" not in helper_body.lower(), (
        "0022 uses the nullif(..., '') idiom on a jsonb lookup. An absent key is "
        "already NULL (D632); this guards nothing and misleads the next reader"
    )


# ---------------------------------------------------------------------------
# D633 — the guard, which is the whole run
# ---------------------------------------------------------------------------


def test_the_value_is_shape_tested_before_it_is_cast(helper_body: str) -> None:
    """**D633.** An unguarded `candidate::uuid` on a malformed caller-supplied
    header raises 22P02, PostgREST answers 400, and the table is left with ZERO
    rows — the caller's own note, destroyed by a header.

    The regex must appear *before* the cast in the source, because that ordering
    is the guard: a shape test after the cast has already lost.
    """
    assert "!~" in helper_body or "~" in helper_body, "no shape test at all"
    guard_at = helper_body.index("[0-9a-fA-F]{8}")
    cast_at = helper_body.index("::uuid")
    assert guard_at < cast_at, "the cast happens before the shape test; the guard is decorative"


def test_the_guard_pattern_is_anchored(helper_body: str) -> None:
    """Unanchored, `'x' || <uuid> || 'y'` matches and the cast then fails — which
    is the defect the guard exists to prevent, reintroduced by a missing `^`."""
    pattern = re.search(r"'(\^[^']+\$)'", helper_body)
    assert pattern, "the uuid pattern is not anchored at both ends"


def test_the_helper_never_raises(helper_body: str) -> None:
    """Every path returns. A `RAISE` here would put the correlation field back in
    a position to fail the write it annotates."""
    assert "RAISE" not in helper_body, "the helper can raise; a bad header would take the write"
    assert helper_body.count("RETURN") >= 4, "not every branch returns a value"


def test_it_uses_a_shape_test_rather_than_an_exception_block(helper_body: str) -> None:
    """A `BEGIN ... EXCEPTION` opens a subtransaction on every agent write; a
    regex is a comparison. Recorded because the exception block is what a reader
    reaches for first."""
    assert "EXCEPTION" not in helper_body


# ---------------------------------------------------------------------------
# One authority, called by both — question 5, answered in advance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rpc", ["api.create_note", "api.update_task_status"])
def test_both_write_rpcs_record_the_request_id(rendered: str, rpc: str) -> None:
    """D500 exists because 0019 asked a question of one path and not the other.
    Both, or the next reader inherits the same asymmetry."""
    body = rendered.split(f"CREATE OR REPLACE FUNCTION {rpc}")[1].split("$fn$;")[0]
    assert "app_private.agent_request_id()" in body, f"{rpc} does not record a request id"
    assert "request_id" in body, f"{rpc}'s INSERT does not name the column"


def test_neither_rpc_inlines_the_rule(rendered: str) -> None:
    """A shared function rather than the expression twice: a third write RPC
    added later gets the rule by calling it, instead of getting whichever of two
    copies its author happened to read."""
    for rpc in ("api.create_note", "api.update_task_status"):
        body = rendered.split(f"CREATE OR REPLACE FUNCTION {rpc}")[1].split("$fn$;")[0]
        assert "request.headers" not in body, (
            f"{rpc} reads the header itself instead of calling the helper; that is two "
            "authorities over one rule and they will drift"
        )


def test_the_helper_is_not_granted_to_any_request_role(rendered: str) -> None:
    """It needs no privilege of its own: running inside a SECURITY DEFINER caller
    it executes as that function's owner. A grant would create a path to it that
    nothing needs."""
    assert "REVOKE ALL ON FUNCTION app_private.agent_request_id() FROM PUBLIC" in rendered
    assert "GRANT EXECUTE ON FUNCTION app_private.agent_request_id" not in rendered


def test_the_rpc_signatures_are_unchanged(rendered: str) -> None:
    """CREATE OR REPLACE with identical signatures, so no grant moves and nothing
    in `api` is created or dropped. A changed signature would drop the function
    and take its grants with it."""
    assert (
        "CREATE OR REPLACE FUNCTION api.create_note(p_title text, p_content text DEFAULT '')"
        in (rendered)
    )
    assert "DROP FUNCTION" not in rendered


# ---------------------------------------------------------------------------
# The deployment test that had to flip
# ---------------------------------------------------------------------------


def test_the_deployment_proof_no_longer_asserts_the_absence() -> None:
    """Migration 0020 named this test as *"the thing that will fail on the day
    the repair lands"*. It landed, and §6 requires the replacement be stricter
    rather than weaker: the new assertion fails for a missing id, a mismatched
    id, or an id no agent-plane row shares — three ways, against the old one's
    one."""
    source = (REPO_ROOT / "tests" / "deployment" / "test_session9_agent_writes.py").read_text(
        encoding="utf-8"
    )
    body = source.split("def test_the_request_id_is_recorded_and_is_this_planes_own_mint")[1]
    body = body.split("\ndef ")[0]

    assert 'row["request_id"] is None' not in body, "the old absence assertion is still here"
    assert "set(recorded) <= set(ids)" in body, "the correlation assertion is missing"
    assert "0022" in body, "the docstring does not say what authorised the replacement"

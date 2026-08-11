"""The reviewed contract, and the schema cache (API-CONTRACT-001, API-CACHE-001).

Replaces two Session 5 placeholders in ``tests/integration/test_future_api.py``.

Both proofs are about the *served* document rather than about a file, and the
document they read is the one the **documentation role** is served. Under
``openapi-mode = follow-privileges`` a caller is shown what its own grants reach,
so "the OpenAPI document" is not one artifact -- and the one the snapshot was
reviewed against is the one that role sees (ADR 0050).

Nothing here writes the snapshot. ADR 0050's split is that the gate cannot
approve its own subject: ``--update`` is a separate command an operator runs and
a human reviews, and a test that regenerated the file on a mismatch would turn
every drift into a green run.

**Every test states what would have to break for it to go red**, because both
are deselected in an offline gate.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every statement below interpolates values that came from a deployed outputs
# document -- role names and a database name derived by `naming` and validated
# by the outputs schema -- plus fixed UUID constants declared in this file. None
# of it is operator input, and parameter binding is unavailable where an
# identifier, a role name or a `SET` target goes, which is the same reason
# `migrations.quote_identifier` exists. Suppressed per module rather than per
# line, as `tests/security/test_session3_authorization.py` does, because a wall
# of inline noqa comments is one nobody reads.
import json
import time
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import api_surface, openapi_normalize
from agentic_postgres.rendering import ACCEPTANCE_PROBE_FUNCTION, project_lock

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: How long the schema cache may take to reflect a `NOTIFY`. Bounded, and short
#: enough that a listener which is not running is a failure rather than a wait.
#: The reload is asynchronous: PostgREST answers the NOTIFY on a connection it
#: holds for the process's life, so the DDL commit and the served document are
#: not ordered with respect to each other.
RELOAD_TIMEOUT_SECONDS = 30


@pytest.fixture(scope="module")
def documentation_token(project_a: dict[str, Any], mint_token: Callable[..., str]) -> str:
    """A documentation token, which carries no subject.

    Migration 0009's hook refuses a documentation token that carries one, with
    401. Minting a subject here would produce a credential rejected by design
    and a failure that reads as a broken deployment.
    """
    return mint_token(project_a, project_a["database"]["roles"]["api_documentation"], subject=None)


def served_document(api_call: Callable[..., Any], base: str, token: str) -> dict[str, Any]:
    response = api_call(base, token=token)
    assert response.status == 200, (
        f"the OpenAPI document was not served: {response.status} "
        f"{response.reason or response.body[:200]}"
    )
    return openapi_normalize.load_document(response.body)


# ---------------------------------------------------------------------------
# API-CONTRACT-001 — the live document equals the reviewed snapshot
# ---------------------------------------------------------------------------


def test_the_live_openapi_matches_the_reviewed_snapshot(
    project_a: dict[str, Any],
    api_contract: Any,
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    documentation_token: str,
) -> None:
    """API-CONTRACT-001, all three of its clauses.

    The live document normalized equals the committed snapshot; the snapshot's
    objects equal the reviewed surface contract's; and no object exists in ``api``
    that the contract does not name -- which is the clause the §4.4 probe is the
    live test of.

    The comparison is **object-level, not method-level**, and that is ADR 0060
    rather than a weakening. ``follow-privileges`` filters paths by grant and
    does not filter methods: a ``SELECT``-only role is served a document
    advertising ``delete``, ``patch`` and ``post`` on both views, and all three
    return 403. A method-for-method comparison against the reviewed contract
    could therefore only ever fail, and the obvious repair -- editing the
    contract to list the advertised methods -- would widen a reviewed read-only
    surface into a permissive one on paper.

    Goes red if: a migration changes a column type, adds an object, or renames
    one, and nobody ran ``--update``; a PostgREST upgrade changes the generated
    document's shape; the deployment serves a document for a different project,
    which the host and base-path assertions inside ``normalize`` are what catch;
    or the snapshot is edited by hand into something the loader refuses.
    """
    base = rest_base(project_a)
    live = served_document(api_call, base, documentation_token)

    host, base_path = api_contract.published_address(project_a)
    normalized = openapi_normalize.normalize(live, expected_host=host, expected_base_path=base_path)

    snapshot = api_contract.load_snapshot()
    live_objects = openapi_normalize.declared_objects(normalized)
    snapshot_objects = openapi_normalize.declared_objects(snapshot)
    assert openapi_normalize.fingerprint(normalized) == openapi_normalize.fingerprint(snapshot), (
        "the live document does not match the reviewed snapshot. Run "
        "`bin/api-contract.sh --update` into a candidate file, review the diff, and "
        "commit it -- this gate cannot approve its own subject (ADR 0050).\n"
        f"only live: {sorted(live_objects - snapshot_objects)}\n"
        f"only snapshot: {sorted(snapshot_objects - live_objects)}\n"
        "An equal object list here means the difference is inside a definition -- a "
        "column type, a description, an enum's order -- which the diff will show."
    )

    surface = api_surface.load_surface()
    disagreements = api_contract.compare_snapshot_to_surface(snapshot, surface)
    assert not disagreements, (
        "the approved snapshot and the reviewed surface contract disagree: "
        + "; ".join(disagreements)
    )

    published = openapi_normalize.declared_objects(normalized)
    assert ACCEPTANCE_PROBE_FUNCTION not in {name.removeprefix("rpc/") for name in published}, (
        f"api.{ACCEPTANCE_PROBE_FUNCTION} is in the published document. The §4.4 probe "
        "outlived the fixture that created it, and the snapshot above was compared "
        "against a surface that has an extra object on it"
    )


def test_the_deployed_document_records_the_checksums_it_serves(
    project_a: dict[str, Any],
    api_contract: Any,
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    documentation_token: str,
) -> None:
    """API-CONTRACT-001's recorded half: three checksums that are not one.

    ``outputs.json`` carries the reviewed surface's digest, the project-neutral
    canonical snapshot's, and the per-project document actually published. They
    move for three different reasons -- a reviewed change, a PostgREST upgrade,
    and a project's own host -- and a single "contract checksum" could not say
    which one had.

    Goes red if: a deploy records a checksum it did not compute from what it
    served, which is the failure a reader has no other way to detect; the
    surface contract is edited without redeploying; or the project document
    drifts from the one whose digest was recorded, which is what a route
    repointed at another project's service would produce.
    """
    recorded = project_a.get("api") or {}
    assert recorded.get("status") == "ready", (
        f"the deployed document reports api.status={recorded.get('status')!r}; there is "
        "no published surface here to check checksums against"
    )

    assert recorded["api_surface_sha256"] == api_surface.contract_digest(), (
        "the deployment recorded a different digest for the reviewed surface contract "
        "than this checkout has. The two must be redeployed together"
    )

    snapshot = api_contract.load_snapshot()
    assert recorded["canonical_openapi_sha256"] == openapi_normalize.fingerprint(snapshot), (
        "the deployment recorded a canonical snapshot digest that is not this checkout's snapshot"
    )

    base = rest_base(project_a)
    live = served_document(api_call, base, documentation_token)
    served = openapi_normalize.fingerprint(openapi_normalize.sort_maps(live))
    assert recorded["project_openapi_sha256"] == served, (
        "the deployment recorded a project document digest that is not the digest of "
        "what the route is serving now"
    )


# ---------------------------------------------------------------------------
# API-CACHE-001 — a DDL change reaches OpenAPI without a restart
# ---------------------------------------------------------------------------


def test_a_ddl_change_reaches_openapi_without_a_restart(
    project_a: dict[str, Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    running_containers: list[dict[str, Any]],
    sh: Callable[..., str],
    documentation_token: str,
) -> None:
    """API-CACHE-001. The listener is live, and nothing restarted to prove it.

    This test creates and drops the §4.4 probe itself rather than taking the
    ``acceptance_probe`` fixture, because what it measures is the *transition*:
    the object absent, then present, then absent again, with the document
    re-read at each point. A fixture that had already created it would leave the
    "before" measurement unavailable, and a test that only saw it present could
    not distinguish a live reload from a PostgREST started after the DDL.

    **The container and its start time are asserted unchanged across the
    reload**, which is the half that makes this about the schema cache rather
    than about a restart. Without it, a supervisor that restarted PostgREST on
    any database change would pass.

    Goes red if: the ``NOTIFY`` channel name changes on one side only; the
    LISTEN connection is drawn from the pool and dropped when the pool recycles;
    ``db-channel-enabled`` is turned off; or PostgREST is restarted to make the
    change appear, which the identity assertions detect rather than tolerate.
    """
    base = rest_base(project_a)
    roles = project_a["database"]["roles"]
    owner = roles["object_owner"]
    qualified = f"api.{ACCEPTANCE_PROBE_FUNCTION}"
    signature = f"{qualified}(double precision)"

    service = [
        container
        for container in running_containers
        if container.get("Names", "").endswith("-postgrest-1")
        and project_a["project"]["key"] in container.get("Names", "")
    ]
    assert len(service) == 1, (
        f"expected exactly one PostgREST container for {project_a['project']['key']}, "
        f"found {[c.get('Names') for c in service]}"
    )
    container_id = service[0]["ID"]
    started_before = sh("docker", "inspect", "--format", "{{.State.StartedAt}}", container_id)

    before = openapi_normalize.declared_objects(
        served_document(api_call, base, documentation_token)
    )
    assert f"rpc/{ACCEPTANCE_PROBE_FUNCTION}" not in before, (
        f"{qualified} is already published before this test created it; something "
        "else left it behind and the transition below would prove nothing"
    )

    # The project's deployment lock, for the reason the ``acceptance_probe``
    # fixture takes it: a capture interleaving with this DDL would put the probe
    # into a reviewed snapshot. Non-blocking, so a deploy in flight fails this
    # test rather than racing it.
    with project_lock(project_a["project"]["key"]):
        status, _, error = psql(
            project_a,
            f"CREATE FUNCTION {qualified}(p_seconds double precision) "
            "RETURNS double precision LANGUAGE sql VOLATILE "
            "SET search_path = pg_catalog, pg_temp "
            "AS $probe$ SELECT p_seconds FROM pg_catalog.pg_sleep(p_seconds) $probe$; "
            f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC; "
            f'GRANT EXECUTE ON FUNCTION {signature} TO "{roles["api_documentation"]}";',
            role=owner,
        )
        assert status == 0, f"could not create the probe: {error}"

        try:
            psql(project_a, "NOTIFY pgrst, 'reload schema';")
            appeared = _await_object(
                api_call,
                base,
                documentation_token,
                f"rpc/{ACCEPTANCE_PROBE_FUNCTION}",
                present=True,
            )
            assert appeared, (
                f"{qualified} did not appear in the served document within "
                f"{RELOAD_TIMEOUT_SECONDS}s of the NOTIFY; the schema cache is not live"
            )
        finally:
            dropped, _, drop_error = psql(
                project_a, f"DROP FUNCTION IF EXISTS {signature};", role=owner
            )
            psql(project_a, "NOTIFY pgrst, 'reload schema';")
            assert dropped == 0, f"the probe could not be dropped: {drop_error}"

    gone = _await_object(
        api_call, base, documentation_token, f"rpc/{ACCEPTANCE_PROBE_FUNCTION}", present=False
    )
    assert gone, f"{qualified} is still published after being dropped"

    after = [
        container
        for container in json.loads(sh("docker", "inspect", container_id))
        if container["Id"] == container_id
    ]
    assert after, "the PostgREST container disappeared during the reload"
    assert after[0]["State"]["StartedAt"] == started_before.strip(), (
        "PostgREST restarted during this test, so the change reaching OpenAPI says "
        "nothing about whether the schema cache reloads"
    )


def _await_object(
    api_call: Callable[..., Any], base: str, token: str, name: str, *, present: bool
) -> bool:
    """Poll the served document until ``name``'s presence matches, or time out.

    Polling only because the reload is asynchronous, and bounded so that a
    listener which is not running fails rather than hangs. A steady-state
    assertion elsewhere in this suite stays immediate: wrapping one in a retry
    turns a broken deployment into a slow green.
    """
    deadline = time.monotonic() + RELOAD_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        response = api_call(base, token=token)
        if response.status == 200:
            published = openapi_normalize.declared_objects(
                openapi_normalize.load_document(response.body)
            )
            if (name in published) is present:
                return True
        time.sleep(1)
    return False

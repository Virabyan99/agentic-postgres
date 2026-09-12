"""Studio's decisions, without a socket (Session 24 Run 2).

`STU-QUERY-001`, `STU-SESSION-001` and the pure halves of `STU-BIND-001`,
`STU-SURFACE-001` and `STU-REVOKE-001`.

Everything `src/agentic_postgres/studio.py` decides is a function returning a
value, so every refusal below is reached by calling it rather than by arranging
a request that provokes it. That is the point of the split (ADR 0205): the
process cannot answer a request without having asked `request_checks`, and a
battery can drive all of its branches in milliseconds. The proofs that need a
real server and a real deployment are `test_studio_server.py`'s and
`test_studio_runtime.py`'s, and they prove different things -- that the handler
actually calls these, and that the answers are right against the product.

**Marked, and the marks are load-bearing** (D1240). Without them no
marker-selected sweep collects this module at all, and every proof in it would
pass only when somebody named the file.
"""

from __future__ import annotations

import ast
import json
from hashlib import sha256
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    capability_manifest,
    client_ir,
    config,
    openapi_normalize,
    scope_registry,
    studio,
    template_version,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

APP_SNAPSHOT = REPO_ROOT / "contracts" / "app-openapi.canonical.json"
CANONICAL_MCP = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
PROJECT_MANIFEST = REPO_ROOT / "project.example.yaml"

#: The address the rig 24b arm measured, and the one every `surface_answer`
#: proof below re-addresses the committed snapshot to. `:443` is part of the
#: host as PostgREST spells it (`bin/api-contract.py`'s measurement).
HOST = "fixture-alpha-dev.test:443"
BASE_PATH = "/api/rest"


@pytest.fixture(scope="module")
def ir() -> client_ir.IR:
    """The example project's IR, compiled the way `bin/mcp-contract.py` compiles it.

    `test_client_ir.py`'s sequence, for its reason: a committed fixture lock
    would freeze the compiler's output of the day it was written, and what these
    proofs need is the IR the product builds today.
    """
    inputs = capability_manifest.project_inputs(config.load_project_manifest(PROJECT_MANIFEST))
    capabilities = config.load_capabilities_manifest(REPO_ROOT / "capabilities.example.yaml")
    canonical = capability_manifest.compile_joint_contract(capabilities, inputs)
    lock = capability_compiler.compile_lock(
        canonical=canonical,
        project_key="fixture-alpha-dev",
        upstream="https://example.invalid/api/rest",
        sources={
            "capabilities_sha256": "0" * 64,
            "api_surface_sha256": api_surface.contract_digest(),
            "canonical_openapi_sha256": "0" * 64,
            "project_manifest_sha256": "0" * 64,
            "project_capabilities_sha256": sha256(
                capability_manifest.project_capabilities_path(inputs.root).read_bytes()
            ).hexdigest(),
            "project_contract_sha256": sha256(
                capability_manifest.project_contract_path(inputs.root).read_bytes()
            ).hexdigest(),
        },
        profile=None,
        vocabulary=scope_registry.vocabulary_block(inputs.surface),
    )
    return client_ir.build(
        surface=inputs.surface,
        snapshot=json.loads(
            api_surface.project_snapshot_path(inputs.root).read_text(encoding="utf-8")
        ),
        app_snapshot=json.loads(APP_SNAPSHOT.read_text(encoding="utf-8")),
        lock=lock,
        project_root=str(inputs.root.relative_to(REPO_ROOT)),
        pt_sources=client_ir.project_pt_sources(inputs.root),
        app_snapshot_bytes=APP_SNAPSHOT.read_bytes(),
        template_version=template_version(),
    )


@pytest.fixture(scope="module")
def served_document() -> dict[str, Any]:
    """The committed snapshot, re-addressed to a real deployment.

    The snapshot on disk is the project-NEUTRAL form -- `host:
    project.invalid:443`, `basePath: /__project_base_path__` -- because that is
    what `normalize` produces and what the capture stores. A served document is
    the same document carrying the address it is actually published at, so this
    puts one back, which is exactly what `surface_answer` has to take out again.

    Building it this way rather than committing a second file is what makes the
    `ok` proof mean something: the two documents are the same bytes apart from
    the two fields under test (D1260).
    """
    snapshot = json.loads(
        (
            REPO_ROOT / "projects" / "example" / "contracts" / "postgrest-openapi.canonical.json"
        ).read_text(encoding="utf-8")
    )
    snapshot["host"] = HOST
    snapshot["basePath"] = BASE_PATH
    return snapshot


def deployed(rest: str, app: str, *, kind: str = "deployed", status: str = "ready") -> dict:
    return {
        "document_kind": kind,
        "routes": {
            "rest": {"status": status, "url": rest},
            "app": {"status": status, "url": app},
        },
    }


# ---------------------------------------------------------------------------
# the module's own surface
# ---------------------------------------------------------------------------


def test_the_public_surface_is_the_declared_set() -> None:
    """`__all__` is the module's contract, so a name added later is a decision.

    Studio's core is the one place in this session where "what may this process
    decide" is a list somebody can read. A helper that appeared here without
    being declared would be a decision taken by whoever needed it.
    """
    source = (REPO_ROOT / "src" / "agentic_postgres" / "studio.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Read from the SOURCE rather than from `vars(studio)`, because at runtime a
    # module's namespace also holds everything it imported -- `json`, `re`,
    # `urllib`, `openapi_normalize` -- and no introspection tells an import from
    # a definition without special cases for each kind. The question is what
    # this file DECLARES.
    defined: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined |= {target.id for target in node.targets if isinstance(target, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
    defined = {name for name in defined if not name.startswith("_") and name != "__all__"}

    declared = set(studio.__all__)
    assert defined == declared, (
        f"studio.py's declarations and its __all__ disagree. Defined and not declared: "
        f"{sorted(defined - declared)}; declared and not defined: {sorted(declared - defined)}"
    )
    assert declared <= set(vars(studio)), (
        f"declared in __all__ but not importable: {sorted(declared - set(vars(studio)))}"
    )
    assert defined, "this test compared nothing"


def test_the_operator_wire_forms_are_the_runtimes() -> None:
    """A second copy of a table, and the comparison that keeps it honest (D486).

    `app.mcp_query.OPERATORS` is the authority for how a contract operator is
    spelled toward PostgREST, and `studio.py` cannot import it: an operator
    command reaches the standard library and `agentic_postgres` only (ADR 0093).
    So there are two tables and this is the pair.

    An equality, not a containment: an operator Studio could spell and the
    runtime could not would be a filter one caller can send and another cannot,
    and a subset check would pass for an empty table forever (D300).
    """
    from app.mcp_query import IS_NULL_OPERAND, OPERATORS

    assert studio.OPERATOR_WIRE_FORMS == OPERATORS, (
        "Studio's operator table and the agent runtime's disagree. They are two copies of "
        "one decision and neither is allowed to be a second authority"
    )
    assert studio.IS_NULL_OPERAND == IS_NULL_OPERAND


def test_the_operator_set_is_the_contracts_and_not_studios(ir: client_ir.IR) -> None:
    """D1210, restated for humans: the operator set is the capability schema's.

    `rest_query` checks against `ir.filter_operators`, which `client_ir.build`
    takes from `evaluation_harness.filter_operators()` -- the closed set derived
    from the capability schema. Studio declares no set of its own, and this is
    what would notice if it started to.
    """
    from agentic_postgres.evaluation_harness import filter_operators

    assert set(ir.filter_operators) == set(filter_operators())
    assert set(studio.OPERATOR_WIRE_FORMS) == set(ir.filter_operators), (
        "Studio can spell an operator the contract does not name, or cannot spell one it "
        "does. The wire table and the contract's set are the same set by construction"
    )


# ---------------------------------------------------------------------------
# the address book (ADR 0158, D1254)
# ---------------------------------------------------------------------------


def test_the_address_book_is_the_document_and_derives_the_published_address() -> None:
    """Both routes, and the pair `surface_answer` needs, derived once (ADR 0002).

    The expected host carries `:443` because that is how the locked PostgREST
    spells a document published at an https proxy URI -- measured, and a
    derivation that dropped the default port would refuse every correct
    deployment.
    """
    book = studio.address_book(
        deployed("https://alpha.example.test/api/rest/", "https://alpha.example.test/app")
    )
    assert book.rest_url == "https://alpha.example.test/api/rest"
    assert book.app_url == "https://alpha.example.test/app"
    assert book.expected_host == "alpha.example.test:443"
    assert book.expected_base_path == "/api/rest"


def test_a_rendered_document_and_an_unready_route_are_two_different_refusals() -> None:
    """Exit 2 and exit 5, and they are not interchangeable.

    A rendered document is the wrong FILE -- `bin/api.py`'s sentence, because a
    render says what was asked for and a route is an observation (D132). An
    unready route is the right file from a deploy that did not publish one, and
    the remedy is a deploy rather than a different path.
    """
    with pytest.raises(studio.StudioError) as rendered:
        studio.address_book(
            deployed("https://a.test/api/rest", "https://a.test/app", kind="rendered")
        )
    assert rendered.value.exit_code == 2

    with pytest.raises(studio.StudioError) as unready:
        studio.address_book(
            deployed("https://a.test/api/rest", "https://a.test/app", status="unavailable")
        )
    assert unready.value.exit_code == 5


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8080/api/rest", "http://localhost:8080/api/rest"],
)
def test_a_loopback_route_may_be_cleartext_and_nothing_else_may(url: str) -> None:
    """The one written-down exception, and the control beside it (D1254).

    Loopback never leaves the machine, which is the same sentence that lets
    Studio itself serve plain HTTP on `127.0.0.1`. Any other host over `http`
    would put the human's token on a network in cleartext, which is the one
    thing this tool exists to avoid.

    The refusal names the scheme and the host and NOT the URL: a route URL can
    carry a query or userinfo, and a refusal is not a place to print either
    (D105).
    """
    book = studio.address_book(deployed(url, url))
    assert book.rest_url == url

    with pytest.raises(studio.StudioError) as refused:
        studio.address_book(
            deployed("http://elsewhere.test/api/rest?token=sekrit", "https://a.test/app")
        )
    assert refused.value.exit_code == 5
    assert "sekrit" not in str(refused.value)
    assert "elsewhere.test" in str(refused.value)


# ---------------------------------------------------------------------------
# the surface answer (ADR 0204, D1260)
# ---------------------------------------------------------------------------


def answer(ir: client_ir.IR, document: Any, error: str | None = None) -> studio.SurfaceAnswer:
    """`surface_answer` over a document, bytes, or nothing.

    Bytes pass through untouched so an arm can hand it something that is not
    JSON at all; anything else is serialised the way a service would serialise
    it.
    """
    if isinstance(document, bytes):
        payload: bytes | None = document
    elif document is None:
        payload = None
    else:
        payload = json.dumps(document).encode("utf-8")
    return studio.surface_answer(
        ir, payload, error, expected_host=HOST, expected_base_path=BASE_PATH
    )


def test_the_surface_answer_is_ok_for_the_document_the_ir_was_built_from(
    ir: client_ir.IR, served_document: dict[str, Any]
) -> None:
    """The equality, with the address supplied rather than read out of the answer.

    This is the proof that `fingerprint(normalize(served, ...))` and not
    `fingerprint(served)` is the comparison (D1260). The raw document's digest
    is asserted to DIFFER, in the same test, because that is the value a version
    of this function without the two keyword arguments would have computed --
    and it would have reported `stale_contract` against every correct
    deployment, green in no environment and visible in none.
    """
    verdict = answer(ir, served_document)
    assert verdict.answer == "ok", verdict
    assert verdict.served_sha256 == ir.digests.rest_openapi_sha256
    assert openapi_normalize.fingerprint(served_document) != ir.digests.rest_openapi_sha256, (
        "the raw served document already fingerprints to the IR's digest, so this test "
        "cannot tell a normalizing comparison from a naive one"
    )


def test_a_moved_byte_is_stale_contract_naming_both_digests(
    ir: client_ir.IR, served_document: dict[str, Any]
) -> None:
    """One description changed: a disagreement the caller is told both sides of.

    Named rather than summarised, because the next thing whoever reads it does
    is compare the two by eye against a regeneration.
    """
    moved = json.loads(json.dumps(served_document))
    moved["info"]["title"] = moved["info"]["title"] + " (edited)"

    verdict = answer(ir, moved)
    assert verdict.answer == "stale_contract"
    assert verdict.expected_sha256 == ir.digests.rest_openapi_sha256
    assert verdict.served_sha256 and verdict.served_sha256 != verdict.expected_sha256


def test_unreachable_unreadable_and_a_foreign_host_are_three_reports(
    ir: client_ir.IR, served_document: dict[str, Any]
) -> None:
    """ADR 0195: three ways of not knowing, none of them folded into an answer.

    `unreachable` is *the deployment did not answer*; `unreadable` is *it
    answered with something this cannot read*. Neither is `stale_contract`,
    which is a disagreement that was actually observed.

    The third arm is the one D1260 found: a document published at a host the
    deployed document does not name is REFUSED by the normalizer rather than
    substituted into agreement (ADR 0050), and that refusal has to arrive as an
    answer rather than as an exception out of a UI's launch path.
    """
    assert answer(ir, None, "connection refused").answer == "unreachable"
    assert answer(ir, b"not json at all").answer == "unreadable"
    assert answer(ir, [1, 2, 3]).answer == "unreadable"

    foreign = json.loads(json.dumps(served_document))
    foreign["host"] = "somewhere.else:443"
    verdict = answer(ir, foreign)
    assert verdict.answer == "unreadable"
    assert "somewhere.else:443" in (verdict.reason or "")
    assert HOST in (verdict.reason or "")


def test_the_four_answers_are_the_declared_set(
    ir: client_ir.IR, served_document: dict[str, Any]
) -> None:
    """Every answer this function can produce is one of `SURFACE_ANSWERS`.

    The constant is what `bin/studio.py --help` prints and what the page
    branches on, so a fifth answer invented here would reach a UI that has no
    branch for it.
    """
    produced = {
        answer(ir, served_document).answer,
        answer(ir, None, "timed out").answer,
        answer(ir, b"{").answer,
    }
    assert produced <= set(studio.SURFACE_ANSWERS)
    assert len(studio.SURFACE_ANSWERS) == 4


# ---------------------------------------------------------------------------
# the schema view
# ---------------------------------------------------------------------------


def test_the_schema_view_is_the_ir_and_nothing_else(ir: client_ir.IR) -> None:
    """What the page renders is the IR, and a relation the IR does not name is absent.

    The schema browser is served only when the surface answered `ok`, so what it
    shows has been confirmed by the deployment. That makes the interesting
    question the other one: does it show anything the IR does not carry -- a
    count, a row, a digest of the human's? It does not, and the key set is
    asserted exactly so that a later addition is a decision rather than a leak.
    """
    view = studio.schema_view(ir)
    assert set(view) == {"relations", "rpcs", "tools", "enums", "filter_operators", "digests"}

    assert [item["name"] for item in view["relations"]] == [r.name for r in ir.relations]
    assert [item["name"] for item in view["tools"]] == [t.name for t in ir.tools]
    assert view["enums"] == {name: list(members) for name, members in ir.enums.items()}
    assert set(view["digests"]) == {
        "rest_openapi_sha256",
        "tools_sha256",
        "merged_surface_sha256",
    }
    assert "app_openapi_sha256" not in view["digests"], (
        "the application document's digest is provenance and is compared to nothing served "
        "(D1209); publishing it in a view invites somebody to compare it"
    )

    notes = next(item for item in view["relations"] if item["name"] == "notes")
    assert {column["name"] for column in notes["columns"]} == {
        column.name for column in next(r for r in ir.relations if r.name == "notes").columns
    }
    assert not [item for item in view["relations"] if item["name"] == "not_a_relation"]


# ---------------------------------------------------------------------------
# the query builder (D1250)
# ---------------------------------------------------------------------------


def test_rest_query_refuses_a_relation_a_column_or_an_operator_the_surface_does_not_name(
    ir: client_ir.IR,
) -> None:
    """Three refusals before any request, each naming the set it checked against.

    The positive arm runs first and has to succeed: a function that refused
    everything would pass all three refusals and be indistinguishable from a
    perfect boundary.
    """
    served = studio.rest_query(
        ir, relation="notes", select=["id", "title"], filters=[], order=None, limit=10
    )
    assert served.startswith("/notes?")
    assert "select=id,title" in served

    for kwargs, expected in (
        ({"relation": "pg_shadow"}, "not a relation"),
        ({"select": ["id", "password"]}, "not a column"),
        ({"filters": [("id", "like", "%x%")]}, "not an operator"),
        ({"order": ("nope", "asc")}, "not a column"),
        ({"order": ("id", "sideways")}, "not an order direction"),
    ):
        arguments: dict[str, Any] = {
            "relation": "notes",
            "select": ["id"],
            "filters": [],
            "order": None,
            "limit": 10,
        }
        arguments.update(kwargs)
        with pytest.raises(studio.StudioError) as refused:
            studio.rest_query(ir, **arguments)
        assert refused.value.exit_code == 422
        assert expected in str(refused.value), f"{kwargs}: {refused.value}"


def test_rest_query_bounds_limit_and_names_the_constant(ir: client_ir.IR) -> None:
    """1..`STUDIO_MAX_ROWS`, refused outside it, and the constant is in the message.

    Refused rather than clamped, which is `GET /admin/audit`'s rule and the same
    argument: a clamp answers a question the caller did not ask and says nothing
    about having done so.

    `True` is refused as well as `0`. In Python `bool` is an `int`, so a page
    sending `true` for a limit would otherwise pass the range check as 1.
    """
    query = studio.rest_query(
        ir, relation="notes", select=[], filters=[], order=None, limit=studio.STUDIO_MAX_ROWS
    )
    assert query.endswith(f"limit={studio.STUDIO_MAX_ROWS}")

    for bad in (0, -1, studio.STUDIO_MAX_ROWS + 1, True, "10", 1.5):
        with pytest.raises(studio.StudioError) as refused:
            studio.rest_query(ir, relation="notes", select=[], filters=[], order=None, limit=bad)
        assert refused.value.exit_code == 422
        assert "STUDIO_MAX_ROWS" in str(refused.value), bad


def test_a_value_is_encoded_as_a_value_and_never_as_syntax(ir: client_ir.IR) -> None:
    """D1250's rule, over the characters that are PostgREST's syntax.

    `,` `.` `(` `)` and `&` all mean something in a PostgREST query string, so a
    value carrying them must arrive percent-encoded or it is a filter the caller
    wrote. The runtime half is `test_studio_runtime.py`'s pair: the same string
    as a value finds zero rows, and as a stored value is found by `eq`.

    `is_null` sends an operand this process chose and the caller did not, which
    is the one case where nothing is encoded because nothing came from outside.
    """
    query = studio.rest_query(
        ir,
        relation="notes",
        select=[],
        filters=[("title", "eq", "a,b)or(1=1&x")],
        order=None,
        limit=1,
    )
    assert "title=eq.a%2Cb%29or%281%3D1%26x" in query
    for character in (",", "(", ")", "&"):
        assert f"eq.{character}" not in query
        assert character not in query.split("title=eq.", 1)[1].split("&limit")[0]

    listed = studio.rest_query(
        ir,
        relation="notes",
        select=[],
        filters=[("id", "in", ["a,b", "c"])],
        order=None,
        limit=1,
    )
    assert "id=in.(a%2Cb,c)" in listed, listed

    nulled = studio.rest_query(
        ir, relation="notes", select=[], filters=[("title", "is_null", None)], order=None, limit=1
    )
    assert f"title=is.{studio.IS_NULL_OPERAND}" in nulled


def test_the_forwarder_table_has_no_rest_write(ir: client_ir.IR) -> None:
    """Every REST operation is a GET, asserted as a property of the table.

    *A human cannot run SQL through a product surface* and the query builder
    READS: there is no `POST`, `PATCH` or `DELETE` to the REST route anywhere in
    the table, and no RPC call at all -- a reviewed RPC is a write. The one
    write in the whole table is the revocation, which is an application endpoint
    a human's own token already reaches.
    """
    table = studio.forwarder_table()
    rest = {name: operation for name, operation in table.items() if operation.upstream == "rest"}
    assert rest, "no REST operation in the table; this test compared nothing"
    assert all(operation.method == "GET" for operation in rest.values()), (
        f"a REST operation is not a GET: "
        f"{[(n, o.method) for n, o in rest.items() if o.method != 'GET']}"
    )
    assert not any("/rpc/" in operation.path for operation in table.values())

    writes = {name for name, operation in table.items() if operation.method != "GET"}
    assert writes == {"revoke_agent"}, f"the table has writes beyond revocation: {sorted(writes)}"
    assert table["revoke_agent"].upstream == "app"
    del ir


# ---------------------------------------------------------------------------
# revocation (D1251, ADR 0140)
# ---------------------------------------------------------------------------


def test_revoke_refuses_a_confirmation_that_is_not_the_agent_id_before_any_request() -> None:
    """`--confirm`'s shape, checked in the process (ADR 0140).

    The message is the shell's, word for word, because an operator who has typed
    `--confirm` at `bin/edge.sh` should not have to learn a second sentence for
    the same refusal. *Nothing was changed* is the load-bearing half: the check
    happens before any upstream request exists to have changed anything.

    A confirmation that matches a NON-identifier is refused too. `confirm ==
    agent_id` is true for two equal pieces of nonsense, so the shape is checked
    first.
    """
    agent = "8a1e5c1e-0a1b-4c2d-9e3f-0a1b2c3d4e5f"
    path, body = studio.revoke_request(agent, agent)
    assert path == f"/admin/agents/{agent}"
    assert body == {"status": "revoked"}

    with pytest.raises(studio.StudioError) as mismatched:
        studio.revoke_request(agent, "yes")
    assert mismatched.value.exit_code == 422
    assert "Nothing was changed." in str(mismatched.value)
    assert agent in str(mismatched.value)

    with pytest.raises(studio.StudioError) as shapeless:
        studio.revoke_request("not-an-id", "not-an-id")
    assert shapeless.value.exit_code == 422
    assert "not a uuid" in str(shapeless.value)


# ---------------------------------------------------------------------------
# the five checks (STU-BIND-001's pure half)
# ---------------------------------------------------------------------------

BOUND = "127.0.0.1:41234"
OWN_ORIGIN = f"http://{BOUND}"
KEY = "a-launch-key"


def check(**overrides: Any) -> int | None:
    arguments: dict[str, Any] = {
        "method": "GET",
        "path": "/",
        "host": BOUND,
        "bound": BOUND,
        "cookie": f"{studio.LAUNCH_COOKIE}={KEY}",
        "expected_cookie": KEY,
        "origin": None,
        "own_origin": OWN_ORIGIN,
        "custom_header": None,
    }
    arguments.update(overrides)
    return studio.request_checks(**arguments)


def test_request_checks_refuses_five_ways_and_serves_every_control() -> None:
    """Twelve inputs: each refusal, and the request it differs from by one field.

    A refusal proved without its control proves nothing -- a function returning
    403 unconditionally would pass every negative arm here. So each refusal is
    paired with the request that differs from it in exactly the field under
    test, and that one must be served.
    """
    # the controls
    assert check() is None, "a well-formed request is refused"
    assert check(origin=OWN_ORIGIN) is None, "the page's own Origin is refused"
    assert check(path="/open/x", cookie=None) is None, "the launch path needs the cookie it issues"
    assert check(path="/__apg/audit", custom_header="1") is None
    assert check(method="POST", path="/__apg/query", custom_header="1") is None

    # the refusals
    assert check(method="OPTIONS") == 405, "a preflight is answered"
    assert check(method="OPTIONS", path="/__apg/query", custom_header="1") == 405
    assert check(host="evil.example:41234") == 421
    assert check(host=None) == 421
    assert check(origin="http://attacker.example") == 403
    assert check(cookie=None) == 401
    assert check(cookie=f"{studio.LAUNCH_COOKIE}=wrong") == 401
    assert check(path="/__apg/audit", custom_header=None) == 403
    assert check(path="/__apg/audit", custom_header="0") == 403


def test_the_cookie_is_parsed_and_not_substring_matched() -> None:
    """`apg_studio=x` is a prefix of `apg_studio=xy`, and a browser sends more than one.

    A membership test over the raw header would accept a launch key that merely
    BEGINS with the real one, which is a credential comparison done by prefix.
    """
    assert check(cookie=f"other=1; {studio.LAUNCH_COOKIE}={KEY}; third=2") is None
    assert check(cookie=f"{studio.LAUNCH_COOKIE}={KEY}extra") == 401
    assert check(cookie=f"not_{studio.LAUNCH_COOKIE}={KEY}") == 401


def test_an_absent_origin_is_not_a_foreign_one() -> None:
    """A same-origin navigation sends no `Origin`, so absent must be served.

    Refusing it would refuse the page's own first request, and the refusal that
    matters -- a cross-site form post -- carries one by definition.
    """
    assert check(origin=None) is None
    assert check(origin="null") == 403


# ---------------------------------------------------------------------------
# the session Studio opened (D1252, ADR 0195)
# ---------------------------------------------------------------------------

BEFORE = "2026-09-12T17:13:49.000000+00:00"


def row(created: str, *, session: str, revoked: str | None = None) -> dict[str, Any]:
    return {"session_id": session, "created_at": created, "revoked_at": revoked}


def test_the_own_session_is_the_newest_live_row_after_the_login() -> None:
    """One login, one row: the determined path.

    The row has to be strictly after the instant recorded before the login --
    an older live session belongs to a human's other window and closing it would
    be this tool ending somebody else's work.
    """
    rows = [
        row("2026-09-12T17:13:40.000000+00:00", session="older"),
        row("2026-09-12T17:13:50.000000+00:00", session="mine"),
        row("2026-09-12T17:13:55.000000+00:00", session="revoked-later", revoked="whenever"),
    ]
    assert studio.own_session(rows, BEFORE) == "mine"


def test_an_undetermined_own_session_is_reported_and_none_is_ended() -> None:
    """The third outcome, reported rather than guessed (ADR 0195).

    Two live rows sharing the newest instant is a question this process cannot
    answer, and a tool that picked one might end the session a human is using
    from another window. `created_at` was measured at MICROSECOND resolution in
    rig 24b -- three logins inside 0.68 s produced three distinct values -- so
    the tie is practically unreachable, which is precisely why it is proved here
    and not left to a rig that would never produce one.
    """
    tied = [
        row("2026-09-12T17:13:50.000000+00:00", session="one"),
        row("2026-09-12T17:13:50.000000+00:00", session="two"),
    ]
    assert studio.own_session(tied, BEFORE) is None

    assert studio.own_session([], BEFORE) is None
    assert studio.own_session([row(BEFORE, session="same-instant")], BEFORE) is None
    assert (
        studio.own_session(
            [row("2026-09-12T17:13:50.000000+00:00", session="x", revoked="yes")], BEFORE
        )
        is None
    )


# ---------------------------------------------------------------------------
# what the viewer says and what the log says
# ---------------------------------------------------------------------------


def test_audit_view_header_carries_the_pages_own_count() -> None:
    """*n of m on this page*, always visible (D1248).

    A view filter hides rows in the browser; this sentence is what makes a
    hidden row visible as a number. It names the page's size too, because *m*
    alone would let somebody read the newest 500 as the whole table.
    """
    header = studio.audit_view_header(3, 57)
    assert header == "showing 3 of 57 rows on this page; the page is the newest 500"
    assert str(studio.AUDIT_PAGE_LIMIT) in header


def test_redact_for_log_drops_the_query_and_the_launch_key() -> None:
    """D1256: a method, a path without its query, and nothing else.

    `http.server`'s default logger writes the request line, so the query
    builder's values, the audit filters and the launch key would all reach
    stderr by way of a logger nobody chose. The key is REPLACED rather than
    trimmed: a path is the one place in this process where a credential-shaped
    value appears by design.
    """
    assert studio.redact_for_log("GET", "/notes?title=eq.secret") == "GET /notes"
    assert studio.redact_for_log("GET", "/open/x7Kq-launch-key") == "GET /open/<key>"
    assert studio.redact_for_log("POST", "/__apg/query") == "POST /__apg/query"
    assert "eq.secret" not in studio.redact_for_log("GET", "/notes?title=eq.secret")


def test_the_module_verifies_no_token_and_holds_no_key() -> None:
    """Studio is a HOLDER, not a verifier (D1246).

    The import list is the assertion: a module that verified a JWT would have to
    import something that can, and there is nothing in the standard library that
    does it by accident. The verifier count stays four (ADR 0170) and this
    session adds no rotation precondition.
    """
    source = (REPO_ROOT / "src" / "agentic_postgres" / "studio.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"jwt", "jwks", "cryptography", "jose", "hmac"}, sorted(imported)
    assert imported <= {
        "__future__",
        "json",
        "re",
        "urllib",
        "dataclasses",
        "typing",
        "agentic_postgres",
    }, (
        f"studio.py imports {sorted(imported)}; an operator command reaches the standard "
        "library and agentic_postgres only (ADR 0093)"
    )

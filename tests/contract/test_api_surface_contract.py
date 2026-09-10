"""The reviewed API surface contract (ADR 0048, ADR 0050).

The file this module tests exists because of a specific failure. For two
sessions four source-controlled documents described one example domain and six
applied migrations implemented another, and nothing caught it -- because every
test that could have was written *from the code*. `SEC-FUNC-001` reads function
signatures out of the catalog and asserts they match the catalog. The one test
that mentioned the divergence asserted it.

So the properties asserted here are mostly about what the contract *cannot* say.
A contract that can name a class of objects cannot refuse a member of it; a
contract generated from the catalog cannot disagree with the catalog; a contract
whose forbidden list is merely non-empty forbids nothing in particular. Each of
those is a way for a file to validate and stop being a contract.

Nothing here reads a database. The comparison against the catalog and against
the generated OpenAPI is `API-CONTRACT-001`, which needs a running service and
is Session 5's later runs; what is provable offline is that the reviewed file
says something exact, and that is what this asserts.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, api_surface, config, openapi_normalize
from agentic_postgres.rendering import ACCEPTANCE_PROBE_FUNCTION

pytestmark = [pytest.mark.contract, pytest.mark.p0]


@pytest.fixture
def surface() -> dict[str, Any]:
    return api_surface.load_surface()


@pytest.fixture
def mutable(surface: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(surface)


def check(tmp_path: Path, document: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "postgrest-api-surface.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return api_surface.load_surface(path)


# ---------------------------------------------------------------------------
# The shipped contract
# ---------------------------------------------------------------------------


def test_the_committed_contract_loads(surface: dict[str, Any]) -> None:
    assert surface["schema_version"] == 1
    assert surface["exposed_schema"] == "api"


def test_it_states_adr_0003s_domain_as_adr_0048_amends_it(surface: dict[str, Any]) -> None:
    """The four operations, named. This is the executable form ADR 0003 lacked.

    `update_task_status` is the one that matters: ADR 0003 argued at length for a
    narrow status transition rather than a general update, and what shipped was a
    second create. A contract that listed `create_task` would be this file
    agreeing with the defect.
    """
    assert set(surface["relations"]) == {"notes", "tasks"}
    # ADR 0196 amends ADR 0048's amendment, and the exclusion inverts rather
    # than disappearing. `0007` was right to drop the create ADR 0003 never
    # sanctioned; what it did not notice is that the removal left NO way to make
    # a task, so `update_task_status` -- ADR 0003's operation 4 -- had never run
    # against a row outside a fixture. `0031` restores one, reviewed here
    # deliberately rather than inherited.
    assert set(surface["rpcs"]) == {"create_note", "create_task", "update_task_status"}
    assert surface["rpcs"]["create_task"]["arguments"] == ["p_title", "p_note_id"]
    assert surface["rpcs"]["create_task"]["methods"] == ["POST"]
    assert "status" in surface["relations"]["tasks"]["columns"]
    assert "done" not in surface["relations"]["tasks"]["columns"]
    assert "content" in surface["relations"]["notes"]["columns"]
    assert "body" not in surface["relations"]["notes"]["columns"]


def test_reads_are_views_and_writes_are_rpcs(surface: dict[str, Any]) -> None:
    """No table-style write on a relation, at any level of the file.

    A grant of INSERT on `api.notes` would let a caller name the `owner_id` it
    liked and satisfy the row policy by saying so, which is the whole reason
    migration 0004 grants SELECT and nothing else.
    """
    for name, relation in surface["relations"].items():
        assert relation["kind"] == "view", name
        assert set(relation["methods"]) <= api_surface.RELATION_METHODS, name
    for name, rpc in surface["rpcs"].items():
        assert rpc["methods"] == ["POST"], name


def test_the_forbidden_schemas_are_the_four_that_can_be_reached(
    surface: dict[str, Any],
) -> None:
    assert api_surface.REQUIRED_FORBIDDEN_SCHEMAS <= set(surface["forbidden_schemas"])
    assert surface["exposed_schema"] not in surface["forbidden_schemas"]


def test_the_contract_is_project_neutral(surface: dict[str, Any]) -> None:
    """One contract, two projects (ADR 0050).

    Asserted against the fixtures' own identities rather than against a list of
    forbidden words, so a third project added later is covered without anyone
    remembering to extend this.
    """
    text = api_surface.CONTRACT_PATH.read_text(encoding="utf-8")
    for manifest in ("project.example.yaml", "project.second.example.yaml"):
        project = yaml.safe_load((REPO_ROOT / manifest).read_text(encoding="utf-8"))["project"]
        assert project["slug"] not in text, manifest
        assert project["domain"] not in text, manifest


def test_the_arguments_are_the_parameter_names_not_a_friendlier_spelling(
    surface: dict[str, Any],
) -> None:
    """PostgREST maps JSON body keys onto parameter names, so these are the wire.

    The runbook's §7.2 names them `title`, `content`, `task_id` and so on; the
    functions carry a `p_` prefix, and a contract that dropped it would describe
    a request body no caller can send.
    """
    assert surface["rpcs"]["create_note"]["arguments"] == ["p_title", "p_content"]
    assert surface["rpcs"]["update_task_status"]["arguments"] == [
        "p_task_id",
        "p_expected_status",
        "p_new_status",
    ]


def test_every_declared_object_is_schema_qualified_once(surface: dict[str, Any]) -> None:
    """The form both sides of the catalog comparison will use.

    A comparison whose two sides spell the same object differently reports a
    difference that is not one, and the repair for that is always to loosen the
    comparison.
    """
    assert api_surface.declared_objects(surface) == {
        "api.notes",
        "api.tasks",
        "api.create_note",
        # ADR 0196, migration 0031. Declared AND published, unlike the four
        # agent-plane functions below: `0031` grants EXECUTE to
        # `api_documentation`, and under `openapi-mode = follow-privileges` that
        # grant is exactly what puts a function into the generated document
        # (F-007, migration 0009's rule).
        "api.create_task",
        "api.update_task_status",
        # ADR 0118. `declared_objects` answers "what may exist in the exposed
        # schema", and these two do exist there -- reachable over HTTP by the
        # agent role, and kept out of the generated document only by a grant.
        # `published_objects` is the other question and omits them.
        "api.mcp_agent_context",
        "api.owner_activity_report",
        # ADR 0136, by the same reasoning: the audit functions exist in `api`,
        # are reachable by the two agent roles, and are absent from the document
        # because `api_documentation` holds no EXECUTE on them. They sit in
        # `agent_write_rpcs` rather than `agent_rpcs` because they write, and a
        # function that writes takes arguments.
        "api.agent_audit_begin",
        "api.agent_audit_complete",
    }
    assert api_surface.published_objects(surface) == {
        "api.notes",
        "api.tasks",
        "api.create_note",
        "api.create_task",
        "api.update_task_status",
    }
    assert api_surface.published_objects(surface) < api_surface.declared_objects(surface), (
        "the published set is not a proper subset of the declared set, which means "
        "either the agent plane vanished or something advertised is not reviewed"
    )


# ---------------------------------------------------------------------------
# What a file that validates still cannot be
# ---------------------------------------------------------------------------


def test_a_wildcard_column_is_refused(tmp_path: Path, mutable: dict) -> None:
    """A contract that names a class of objects cannot refuse a member of it.

    `columns: ["*"]` is the shape that matters: it reads as "all of them", it
    would be true of every catalog, and a comparison against it can never fail.
    """
    mutable["relations"]["notes"]["columns"] = ["*"]
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_a_wildcard_relation_name_is_refused(tmp_path: Path, mutable: dict) -> None:
    mutable["relations"]["note%"] = mutable["relations"].pop("notes")
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_a_sql_fragment_cannot_be_expressed(tmp_path: Path, mutable: dict) -> None:
    """'The contract contains no SQL' is a property of the schema, not a rule.

    Every string in the document is either a bare identifier or a member of a
    closed enumeration, so a fragment cannot be spelled -- there is nowhere with
    a space in it.
    """
    mutable["relations"]["notes"]["columns"] = ["id, title FROM app.notes --"]
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_a_quoted_or_qualified_name_is_refused(tmp_path: Path, mutable: dict) -> None:
    mutable["rpcs"]["api.create_note"] = mutable["rpcs"].pop("create_note")
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_dropping_a_forbidden_schema_is_refused(tmp_path: Path, mutable: dict) -> None:
    """The schema requires a non-empty list, not a particular one.

    A file that stopped naming `app_private` would still validate, and would
    stop refusing the schema that holds the identity row and the pre-request
    function.
    """
    mutable["forbidden_schemas"] = [s for s in mutable["forbidden_schemas"] if s != "app_private"]
    with pytest.raises(api_surface.SurfaceError, match="app_private"):
        check(tmp_path, mutable)


def test_forbidding_the_exposed_schema_is_refused(tmp_path: Path, mutable: dict) -> None:
    """The contradiction would produce a surface that agrees with every catalog."""
    mutable["forbidden_schemas"].append(mutable["exposed_schema"])
    with pytest.raises(api_surface.SurfaceError, match="also in forbidden_schemas"):
        check(tmp_path, mutable)


def test_a_write_method_on_a_relation_is_refused(tmp_path: Path, mutable: dict) -> None:
    mutable["relations"]["notes"]["methods"] = ["GET", "POST"]
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_a_get_rpc_is_refused(tmp_path: Path, mutable: dict) -> None:
    """A `GET /rpc/` puts the arguments in a query string.

    Which is in every access log, every proxy cache and every browser history
    between the caller and the database -- for a function whose arguments are
    the row being written.
    """
    mutable["rpcs"]["create_note"]["methods"] = ["GET"]
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_a_base_table_cannot_be_declared(tmp_path: Path, mutable: dict) -> None:
    """`kind: view` is a one-member enum, and not by oversight.

    A base table exposed directly runs the caller's query against the table's own
    privileges rather than through `security_invoker`, which is the failure that
    migration's whole comment block is about.
    """
    mutable["relations"]["notes"]["kind"] = "table"
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_a_name_declared_as_both_a_relation_and_an_rpc_is_refused(
    tmp_path: Path, mutable: dict
) -> None:
    mutable["rpcs"]["notes"] = {"methods": ["POST"], "arguments": []}
    with pytest.raises(api_surface.SurfaceError, match="both a relation and an RPC"):
        check(tmp_path, mutable)


# ---------------------------------------------------------------------------
# The enum section (ADR 0058)
# ---------------------------------------------------------------------------


def test_the_frozen_status_values_have_an_executable_form(surface: dict[str, Any]) -> None:
    """ADR 0003's most-argued clause was the one with no way to check it.

    Four values, frozen in Session 1 and restated in three documents, and until
    now checkable only by reading two of them side by side -- which is exactly
    how the domain drifted for two sessions.
    """
    assert surface["enums"] == {
        "task_status": {"values": ["pending", "in_progress", "completed", "cancelled"]}
    }


def test_a_type_may_not_share_a_name_with_a_relation(tmp_path: Path, mutable: dict) -> None:
    """PostgreSQL puts types and relations in one namespace.

    `CREATE TYPE api.tasks` fails against the view of that name, so a contract
    declaring both would describe a catalog that cannot exist -- and a
    comparison against a real one would report a difference nobody could repair.
    """
    mutable["enums"]["tasks"] = {"values": ["a"]}
    with pytest.raises(api_surface.SurfaceError, match="both a relation and an enum type"):
        check(tmp_path, mutable)


def test_the_declared_types_are_separate_from_the_declared_objects(
    surface: dict[str, Any],
) -> None:
    """Two accessors, because they are compared against two catalogs.

    Folded into one set, a missing `api.task_status` and a missing `api.tasks`
    would be reported identically, and the repair for an ambiguous difference is
    always to loosen the comparison.
    """
    assert api_surface.declared_types(surface) == {"api.task_status"}
    assert api_surface.declared_objects(surface) == {
        "api.notes",
        "api.tasks",
        "api.create_note",
        # ADR 0196, migration 0031. Declared AND published, unlike the four
        # agent-plane functions below: `0031` grants EXECUTE to
        # `api_documentation`, and under `openapi-mode = follow-privileges` that
        # grant is exactly what puts a function into the generated document
        # (F-007, migration 0009's rule).
        "api.create_task",
        "api.update_task_status",
        # ADR 0118. `declared_objects` answers "what may exist in the exposed
        # schema", and these two do exist there -- reachable over HTTP by the
        # agent role, and kept out of the generated document only by a grant.
        # `published_objects` is the other question and omits them.
        "api.mcp_agent_context",
        "api.owner_activity_report",
        # ADR 0136, by the same reasoning: the audit functions exist in `api`,
        # are reachable by the two agent roles, and are absent from the document
        # because `api_documentation` holds no EXECUTE on them. They sit in
        # `agent_write_rpcs` rather than `agent_rpcs` because they write, and a
        # function that writes takes arguments.
        "api.agent_audit_begin",
        "api.agent_audit_complete",
    }
    assert api_surface.published_objects(surface) == {
        "api.notes",
        "api.tasks",
        "api.create_note",
        "api.create_task",
        "api.update_task_status",
    }
    assert api_surface.published_objects(surface) < api_surface.declared_objects(surface), (
        "the published set is not a proper subset of the declared set, which means "
        "either the agent plane vanished or something advertised is not reviewed"
    )


def test_a_contract_with_no_enums_is_refused(tmp_path: Path, mutable: dict) -> None:
    """The section is required, not optional-and-usually-present.

    An absent section would mean "this surface publishes no bounded values",
    which is a claim about the catalog rather than a gap in the file -- and it
    is a false one here.
    """
    mutable.pop("enums")
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_a_duplicate_enum_value_is_refused(tmp_path: Path, mutable: dict) -> None:
    mutable["enums"]["task_status"]["values"] = ["pending", "pending"]
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_an_enum_value_that_is_not_a_bare_identifier_is_refused(
    tmp_path: Path, mutable: dict
) -> None:
    """These values reach a published document and a `CREATE TYPE`. Anything
    needing quotes in either is a value this contract cannot state exactly."""
    mutable["enums"]["task_status"]["values"] = ["pending", "in progress'; DROP TABLE x --"]
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_an_unknown_key_is_refused(tmp_path: Path, mutable: dict) -> None:
    mutable["relations"]["notes"]["writable"] = True
    with pytest.raises(config.ManifestError):
        check(tmp_path, mutable)


def test_a_duplicate_key_is_refused(tmp_path: Path) -> None:
    """Inherited from the strict loader, and worth asserting here.

    Default PyYAML keeps the last value for a duplicate key, so a second
    `relations:` block would silently discard every object in the first one --
    a contract containing objects nobody reviewed, produced by a typo.
    """
    path = tmp_path / "postgrest-api-surface.yaml"
    path.write_text(
        api_surface.CONTRACT_PATH.read_text(encoding="utf-8") + "\nexposed_schema: app\n",
        encoding="utf-8",
    )
    with pytest.raises(config.ManifestError, match="duplicate"):
        api_surface.load_surface(path)


# ---------------------------------------------------------------------------
# The gate cannot approve its own subject (ADR 0050)
# ---------------------------------------------------------------------------


def test_the_module_cannot_write_a_contract() -> None:
    """The property ADR 0050 asks for, obtained structurally.

    "The final gate must never rewrite the approved contract" is a rule somebody
    has to keep. A check path containing no writer is a fact. Asserted on the
    public surface and on the source, because the second is what would change
    first.
    """
    assert not any(
        name.startswith(("write", "update", "capture", "save")) for name in api_surface.__all__
    )
    source = (REPO_ROOT / "src" / "agentic_postgres" / "api_surface.py").read_text("utf-8")
    for writer in ("write_text", "write_bytes", "open(", "yaml.safe_dump", "yaml.dump"):
        assert writer not in source, writer


def test_the_digest_is_of_the_bytes_not_the_parse() -> None:
    """What a deployment served is a file somebody reviewed.

    A digest of the parsed document would be equal for two files whose comments
    differ, and the comments are where the reasoning lives.
    """
    from hashlib import sha256

    assert (
        api_surface.contract_digest() == sha256(api_surface.CONTRACT_PATH.read_bytes()).hexdigest()
    )
    assert len(api_surface.contract_digest()) == 64


def test_the_schema_is_referenced_by_the_module_and_exists() -> None:
    """ADR 0198 adds version 2, and this asserts more than it did before.

    It pinned the enum to `[1]`. Widening that to `[1, 2]` on its own would be
    the kind of edit that reads as bookkeeping and quietly stops saying
    anything, so the replacement names what each version IS -- which is the
    property a reader of this file actually needs and which the old assertion
    never carried.
    """
    schema = config.load_schema(api_surface.SCHEMA_NAME)
    assert schema["properties"]["schema_version"]["enum"] == [1, 2]
    assert schema["additionalProperties"] is False

    # Version 1 is the release's and must still require every section it
    # required before. Version 2 is a project's and must forbid the three that
    # describe the whole database. Both gates are read from the schema rather
    # than assumed, because the version 2 change moved these bounds off the
    # properties and a gate that lost one would be invisible here otherwise.
    gates = {gate["if"]["properties"]["schema_version"]["const"]: gate for gate in schema["allOf"]}
    assert set(gates) == {1, 2}

    assert set(gates[1]["then"]["required"]) == {
        "enums",
        "agent_rpcs",
        "agent_write_rpcs",
        "forbidden_schemas",
    }
    for section in ("enums", "relations", "rpcs"):
        assert gates[1]["then"]["properties"][section]["minProperties"] == 1

    forbidden_at_two = {entry["required"][0] for entry in gates[2]["then"]["not"]["anyOf"]}
    assert forbidden_at_two == set(api_surface.PLATFORM_ONLY_SECTIONS)

    # And the module's own copy of that list agrees with the schema's. Two
    # copies of a fact with a test between them are one fact -- the reason
    # REQUIRED_FORBIDDEN_SCHEMAS is held in both places too.
    assert set(api_surface.PLATFORM_ONLY_SECTIONS) == {
        "agent_rpcs",
        "agent_write_rpcs",
        "forbidden_schemas",
    }


# ---------------------------------------------------------------------------
# The transient acceptance object is never reviewed surface (plan §4.4)
# ---------------------------------------------------------------------------


def test_the_acceptance_probe_is_not_on_the_reviewed_surface() -> None:
    """The one half of §4.4 that has a signal before a deployment exists.

    The probe is created in ``api`` -- it has to be, because that is the only
    schema PostgREST exposes -- so for as long as it lives it is a published
    object. Three tests check it is gone afterwards: two on the host, against
    the served document and the catalog, and this one, against the two committed
    artifacts that say what may be served at all.

    Here rather than only on the host because the host tests are deselected in
    an offline gate, and a reviewed contract that had acquired the probe's name
    would then be caught by nothing until Run 9.

    Goes red if: somebody adds the probe to the reviewed contract to make a host
    failure go away. That is the repair the failure invites, and it would widen
    the approved surface permanently in order to fix a fixture that leaked.
    """
    surface = api_surface.load_surface()
    # Qualified, because that is how `declared_objects` spells a name. The bare
    # constant would be absent from that set for every possible contract, which
    # is an assertion that cannot fail and therefore measures nothing.
    qualified = f"{surface['exposed_schema']}.{ACCEPTANCE_PROBE_FUNCTION}"
    assert qualified not in api_surface.declared_objects(surface), (
        f"{qualified} is on the reviewed surface"
    )
    assert ACCEPTANCE_PROBE_FUNCTION not in api_surface.CONTRACT_PATH.read_text("utf-8"), (
        f"the reviewed contract names {ACCEPTANCE_PROBE_FUNCTION} somewhere the object "
        "list does not reach"
    )

    # Conditional because Run 9 is what commits the snapshot. The two assertions
    # above are unconditional and are the ones carrying this test today; this is
    # the clause that starts carrying it the moment there is a file to check.
    snapshot = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
    if snapshot.is_file():
        assert ACCEPTANCE_PROBE_FUNCTION not in snapshot.read_text("utf-8"), (
            f"the approved snapshot names {ACCEPTANCE_PROBE_FUNCTION}; a capture was "
            "taken while the probe existed, and was then approved"
        )


# ---------------------------------------------------------------------------
# The agent plane is reviewed and unpublished (ADR 0118)
# ---------------------------------------------------------------------------


def test_no_agent_plane_function_is_published() -> None:
    """**The rule with teeth**, and it reads the generated artefact.

    ADR 0118 keeps `mcp_agent_context` and `owner_activity_report` out of the
    published OpenAPI document by withholding `EXECUTE` from
    `api_documentation` -- `openapi-mode = follow-privileges` builds the
    document as that role. That is a grant, and a grant is one line.

    Everything else asserting this reads the migration, which is the intention.
    **D274 is why that is not enough**: `/docs/rest` was proved at 401 and 200
    for four runs and had never rendered, because nothing requested the script
    its own markup named. So this asserts the property of the artefact -- the
    approved snapshot -- rather than of the file that hopes to produce it.

    Goes red if: `api_documentation` is granted EXECUTE on either function and a
    capture is then approved; or an agent-plane name is moved into `rpcs:` while
    still in `agent_rpcs:`.
    """
    surface = api_surface.load_surface()
    agent_names = set(surface["agent_rpcs"])
    assert agent_names, "the agent_rpcs section is empty; this test would assert nothing"

    assert not agent_names & set(surface["rpcs"]), (
        f"{sorted(agent_names & set(surface['rpcs']))} is in both rpcs and agent_rpcs. One "
        "list is the published surface and the other is deliberately not"
    )

    snapshot = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
    if not snapshot.is_file():
        pytest.skip("no approved snapshot to check against")

    published = openapi_normalize.declared_objects(json.loads(snapshot.read_text("utf-8")))
    assert published, "the snapshot publishes nothing; this comparison would be vacuous"
    leaked = sorted(name for name in agent_names if f"rpc/{name}" in published)
    assert not leaked, (
        f"the approved snapshot publishes {leaked}, which the reviewed contract lists as "
        "agent-plane functions. Either a grant to api_documentation was added and a "
        "capture approved, or the contract moved a name and the document did not"
    )


def test_the_published_set_is_exactly_what_the_snapshot_names() -> None:
    """The other direction, and the reason `published_objects` exists.

    `declared_objects` answers "what may exist in the exposed schema" and
    `published_objects` answers "what may be advertised". Session 8 is where
    those stopped being the same question, and a single accessor with a filter
    at each call site is how one of the call sites eventually gets it wrong.
    """
    surface = api_surface.load_surface()
    snapshot = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
    if not snapshot.is_file():
        pytest.skip("no approved snapshot to check against")

    published = openapi_normalize.declared_objects(json.loads(snapshot.read_text("utf-8")))
    expected = {name.split(".", 1)[1] for name in api_surface.published_objects(surface)}
    served = {name.removeprefix("rpc/") for name in published}
    assert served == expected, (
        f"the snapshot names {sorted(served)} and the reviewed published surface names "
        f"{sorted(expected)}"
    )


# ---------------------------------------------------------------------------
# A project's own reviewed surface (ADR 0198, TEN-SURF-001)
# ---------------------------------------------------------------------------

EXAMPLE_PROJECT = REPO_ROOT / "projects" / "example"


@pytest.fixture
def project_surface() -> dict[str, Any]:
    return api_surface.load_project_surface(api_surface.project_contract_path(EXAMPLE_PROJECT))


def test_the_example_projects_contract_loads_at_version_two(
    project_surface: dict[str, Any],
) -> None:
    """The file an adopter writes, through the same strict loader as the release's.

    Anti-vacuity first: a contract naming nothing would satisfy every comparison
    below, so what it names is asserted before anything is compared against it.
    """
    assert project_surface["schema_version"] == 2
    assert project_surface["exposed_schema"] == "api"
    assert set(project_surface["relations"]) == {"note_embeddings"}
    assert set(project_surface["rpcs"]) == {"set_note_embedding"}


@pytest.mark.parametrize("section", api_surface.PLATFORM_ONLY_SECTIONS)
def test_a_project_contract_may_not_carry_a_platform_section(
    tmp_path: Path, project_surface: dict[str, Any], section: str
) -> None:
    """`forbidden_schemas` is the one with teeth.

    It names the schemas nothing may ever publish. A project able to write its
    own list could write a shorter one, and the merged surface would then check
    the served document against the weaker of two authorities. The agent
    sections are refused for the neighbouring reason: the roster is a hardcoded
    six and a project cannot add to it (D1056, D933).
    """
    import yaml

    document = copy.deepcopy(project_surface)
    document[section] = {} if section != "forbidden_schemas" else ["app_private"]
    path = tmp_path / "postgrest-api-surface.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(config.ManifestError):
        api_surface.load_project_surface(path)


def test_a_project_surface_cannot_redeclare_a_release_object(
    surface: dict[str, Any], project_surface: dict[str, Any]
) -> None:
    """Across every kind, not kind by kind.

    PostgREST serves relations at `/{name}` and functions at `/rpc/{name}`, so
    those two do not collide on the wire -- but a project view named `notes`
    would replace the release's on a deployed cluster while the release's
    reviewed contract still described the old one, and the comparison that
    exists to notice would be comparing the merged document against itself.

    The enum arm matters for a reason the others do not share: PostgreSQL puts
    types and relations in one namespace, so a project enum named `notes` names
    a catalog that cannot exist.
    """
    for kind, name in (
        ("relations", "notes"),
        ("rpcs", "create_note"),
        ("relations", "mcp_agent_context"),
        ("enums", "task_status"),
    ):
        candidate = copy.deepcopy(project_surface)
        candidate.setdefault(kind, {})
        if kind == "enums":
            candidate[kind][name] = {"values": ["a"]}
        elif kind == "relations":
            candidate[kind][name] = {"kind": "view", "methods": ["GET"], "columns": ["id"]}
        else:
            candidate[kind][name] = {"methods": ["POST"], "arguments": ["p_x"]}

        with pytest.raises(api_surface.SurfaceError, match="redeclares"):
            api_surface.merged_surface(surface, candidate)

    # The control, in the same test: the real pair still merges.
    api_surface.merged_surface(surface, project_surface)


def test_the_merged_surface_keeps_the_releases_platform_sections(
    surface: dict[str, Any], project_surface: dict[str, Any]
) -> None:
    """The merge adds and never replaces.

    Asserted on `forbidden_schemas` and the two agent sections specifically,
    because those are the three a project cannot carry -- so the only way they
    could change is if the merge dropped them, and a merged surface missing
    `forbidden_schemas` would make `compare_snapshot_to_surface`'s forbidden
    check iterate an empty list and pass.
    """
    merged = api_surface.merged_surface(surface, project_surface)

    assert merged["forbidden_schemas"] == surface["forbidden_schemas"]
    assert set(merged["forbidden_schemas"]) >= api_surface.REQUIRED_FORBIDDEN_SCHEMAS
    assert merged["agent_rpcs"] == surface["agent_rpcs"]
    assert merged["agent_write_rpcs"] == surface["agent_write_rpcs"]

    assert set(merged["relations"]) == set(surface["relations"]) | {"note_embeddings"}
    assert set(merged["rpcs"]) == set(surface["rpcs"]) | {"set_note_embedding"}


def test_merging_no_project_is_the_release_unchanged(surface: dict[str, Any]) -> None:
    """The control for every merge assertion above.

    Without it, "the merge keeps the release's sections" would hold for a merge
    that ignored its project argument entirely.
    """
    assert api_surface.merged_surface(surface, None) is surface


def test_a_project_contract_that_names_nothing_is_refused(
    tmp_path: Path, project_surface: dict[str, Any]
) -> None:
    """A surface with nothing in it agrees with every catalog.

    The release's contract states this bound in the schema (`minProperties: 1`
    on `relations` and `rpcs`); a project's cannot, because a project may
    legitimately publish only a view or only an RPC. So the rule moves into the
    module, where the reason can sit beside it.
    """
    import yaml

    document = copy.deepcopy(project_surface)
    document["relations"] = {}
    document["rpcs"] = {}
    path = tmp_path / "postgrest-api-surface.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(api_surface.SurfaceError, match="describes nothing"):
        api_surface.load_project_surface(path)


def test_a_release_contract_missing_a_platform_section_is_refused(
    tmp_path: Path, surface: dict[str, Any]
) -> None:
    """The version 1 gate still requires what it required before ADR 0198.

    Version 2 exists by moving four `required` entries and three
    `minProperties` bounds off the properties and into a version 1 gate. That is
    a widening only if the gate puts every one of them back; if it does not, the
    release's contract silently stopped being required to name its own agent
    plane. Asserted rather than reviewed, because the diff that would introduce
    it looks like tidying.
    """
    import yaml

    for section in ("enums", "agent_rpcs", "agent_write_rpcs", "forbidden_schemas"):
        document = copy.deepcopy(surface)
        del document[section]
        path = tmp_path / f"missing-{section}.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        with pytest.raises(config.ManifestError):
            api_surface.load_surface(path)

    for section in ("enums", "relations", "rpcs"):
        document = copy.deepcopy(surface)
        document[section] = {}
        path = tmp_path / f"empty-{section}.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        with pytest.raises(config.ManifestError):
            api_surface.load_surface(path)

    # The control: the real contract still loads through the same loader.
    api_surface.load_surface()

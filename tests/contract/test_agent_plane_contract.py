"""The agent plane's contract, before any of it runs (Session 8, Run 1).

Three things are asserted here and none of them needs an MCP runtime to exist,
which is the point: each is a decision that would otherwise be discoverable only
by deploying one.

**Which `token_use` each surface accepts** (ADR 0114, ADR 0115). The two
constants are mirror images, they live in two runtimes, and a test asserting only
its own value would pass for a surface that accepted both.

**That the deployed document's shape and the code's honest-absence constant agree
member for member.** `MCP_NOT_PUBLISHED` is what every project on every host
publishes today; a member the schema requires and the constant omits is a
`ManifestError` on a host, and a member the constant carries and the schema
forbids is the same.

**That the MCP runtime takes no share of the connection budget** (D407). ADR 0099
divides `max_connections` 56 four ways -- api 13, auth 6, storage 6, application
23, headroom 5 -- and the agent plane holds no database credential, so its share
is zero. **A considered zero is recorded the way a cost is**, because otherwise
the next reader cannot tell it from an oversight. D309 was a service added with
no term in the budget at all; this is the opposite case, written down so the two
stay distinguishable.
"""

from __future__ import annotations

import ast
import json
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, config, deployed_output
from app import claims as claim_contract
from app import service as auth_service_module

pytestmark = [pytest.mark.contract, pytest.mark.p0]

#: The one `token_use` the MCP surface accepts (ADR 0115). Declared here, in the
#: repository's contract layer, because Run 1 has no MCP runtime to declare it
#: in -- and the deployed document already publishes it as a field, so the value
#: exists before the service does. Run 4 moves this to the runtime and this test
#: module reads it from there; until then the schema is the authority and this
#: constant is checked against it rather than trusted.
#:
#: (S105 matches on the NAME. "agent" is a `token_use` discriminator from the
#: claim contract, published in every agent token this deployment issues.)
MCP_ACCEPTED_TOKEN_USE = "agent"  # noqa: S105


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))


# ---------------------------------------------------------------------------
# ADR 0115 -- the two surfaces, and the two refusals
# ---------------------------------------------------------------------------


def test_the_two_surfaces_accept_different_token_uses() -> None:
    """ADR 0115's substance, and the assertion ADR 0114 could not make alone.

    The application API accepts `access`; the agent plane accepts `agent`. Both
    are real values of `claims.TOKEN_USES` and this deployment issues both, so
    neither refusal is implied by the claim contract -- each is a decision, taken
    by one runtime, for one reason.

    Asserted as a **difference** rather than as two values. A surface that
    accepted both would satisfy any test that only checked its own constant, and
    "both" is exactly the state ADR 0114 found the application API in before D393
    named it: the refusal happened, but because of which table a row lived in.
    """
    assert auth_service_module.ACCEPTED_TOKEN_USE != MCP_ACCEPTED_TOKEN_USE, (
        "one surface accepts what the other does. A human token reaching /mcp and an "
        "agent token reaching /api/app are each a principal in the wrong place, and "
        "ADR 0114 and ADR 0115 exist so that neither is refused by accident"
    )
    accepted = {auth_service_module.ACCEPTED_TOKEN_USE, MCP_ACCEPTED_TOKEN_USE}
    assert accepted == set(claim_contract.TOKEN_USES), (
        f"the two surfaces accept {sorted(accepted)} while the claim contract mints "
        f"{sorted(claim_contract.TOKEN_USES)}. A token use this deployment issues and no "
        "surface accepts is a credential with nowhere to go; a surface accepting a value "
        "the contract cannot mint is a branch nothing reaches"
    )


def test_the_deployed_schema_permits_exactly_one_accepted_token_use(schema: dict[str, Any]) -> None:
    """The published field is the decision, not a restatement of it (D413).

    `mcp.accepted_token_use` is what a proof reads to learn what the surface
    accepts. If the schema permitted either value, a deployment that had quietly
    changed its mind would publish a valid document saying so, and every reader
    would believe it -- which is why the enum has one member and is deliberately
    not `claims.TOKEN_USES`.
    """
    field = schema["$defs"]["deployedMcp"]["properties"]["accepted_token_use"]
    permitted = [branch for branch in field["oneOf"] if branch.get("type") == "string"]
    assert len(permitted) == 1, "expected exactly one string branch in accepted_token_use"
    assert permitted[0]["enum"] == [MCP_ACCEPTED_TOKEN_USE], (
        f"the schema permits {permitted[0]['enum']} where ADR 0115 accepts "
        f"{[MCP_ACCEPTED_TOKEN_USE]}"
    )
    assert auth_service_module.ACCEPTED_TOKEN_USE not in permitted[0]["enum"], (
        "the deployed document would validate an agent plane accepting the application "
        "API's token use, which is the mirror of the state D393 recorded"
    )


# ---------------------------------------------------------------------------
# The honest-absence constant, against the schema that has to accept it
# ---------------------------------------------------------------------------


def test_the_not_published_constant_matches_the_schema_member_for_member(
    schema: dict[str, Any],
) -> None:
    """`MCP_NOT_PUBLISHED` is what every deployment publishes today.

    Compared as sets rather than by validating one example: a validation would
    pass while the constant carried a member the schema merely tolerated, and
    `additionalProperties: false` is what makes the reverse direction fail. The
    two failures land in different places -- one on a host at deploy time, one
    nowhere at all -- and this catches both here.
    """
    required = set(schema["$defs"]["deployedMcp"]["required"])
    declared = set(schema["$defs"]["deployedMcp"]["properties"])
    assert required == declared, "deployedMcp requires a different set than it declares"
    assert set(deployed_output.MCP_NOT_PUBLISHED) == required, (
        "MCP_NOT_PUBLISHED and the deployed schema disagree about the block's members. "
        "This constant is what a session-7 deployment publishes, so a disagreement is a "
        "ManifestError on a host rather than a red test here"
    )


def test_an_unpublished_agent_plane_names_nothing_at_all() -> None:
    """A status that forces every other member null, and the reason it does.

    `authorization_spec_conformant` is the member worth stating: it is `false`
    for a running agent plane and **null** for a deployment that has none. False
    would read as a measurement of a bearer profile that is not there, which is
    the substitution `NOT_OBSERVED` exists to refuse.
    """
    block = deployed_output.MCP_NOT_PUBLISHED
    assert block["status"] == "unavailable"
    others = {name: value for name, value in block.items() if name != "status"}
    assert all(value is None for value in others.values()), (
        f"an unpublished agent plane names {[k for k, v in others.items() if v is not None]}"
    )


# ---------------------------------------------------------------------------
# D407 -- the considered zero
# ---------------------------------------------------------------------------

#: Every claimant on `max_connections`, by the name `config` gives it (ADR 0099).
#: The MCP runtime is deliberately not here: it holds no database credential and
#: opens no pool, so its share is zero.
BUDGET_CLAIMANTS = frozenset(
    {
        "rest_budget",
        "auth_budget",
        "storage_budget",
        "database",
        "ADMINISTRATION_RESERVED_CONNECTIONS",
    }
)


def _summands_of_the_budget_check() -> set[str]:
    """The names summed inside `config._validate_connection_budget`, parsed.

    Parsed rather than grepped, and read from the **arithmetic** rather than from
    a list beside it. A test comparing two lists of claimants passes while both
    are wrong in the same way (D332); this reads the expression the manifest is
    actually checked against, so a fifth claimant added to the sum fails here
    whether or not anybody remembered to write it down.
    """
    tree = ast.parse((REPO_ROOT / "src" / "agentic_postgres" / "config.py").read_text("utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_validate_connection_budget"
    )
    assignment = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "committed" for t in node.targets)
    )
    names: set[str] = set()
    for node in ast.walk(assignment.value):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            # `database["pool_size"]` -- the application's own term.
            names.add(node.value.id)
    return names


def test_the_connection_budget_has_no_term_for_the_agent_plane() -> None:
    """D407, and it is a *record* rather than an omission.

    The MCP runtime forwards the caller's bearer token to PostgREST and holds no
    database credential of its own, so it opens no connection and takes no share
    of ADR 0099's division. `max_connections` 56 stays api 13, auth 6, storage 6,
    application 23, headroom 5.

    **What would have to break for this to go red:** somebody gives MCP a pool.
    The moment a fifth summand appears in the arithmetic every manifest is
    checked against, this fails -- by arithmetic, here, rather than by a cluster
    refusing a login on a host. D309 was the same class of defect found the
    expensive way: a service added with no term in the budget at all.
    """
    summands = _summands_of_the_budget_check()
    assert summands == BUDGET_CLAIMANTS, (
        f"the connection budget is summed over {sorted(summands)}, not {sorted(BUDGET_CLAIMANTS)}. "
        "A claimant added here is a claimant every manifest is now checked against, and "
        "one removed is a service whose connections nothing bounds"
    )
    assert not any("mcp" in name.lower() for name in summands), (
        "the agent plane has acquired a share of the connection budget. That is a "
        "decision with an ADR, not an addend"
    )


def test_no_module_derives_an_mcp_connection_budget() -> None:
    """The other half: nothing computes a figure for a claimant that has none.

    `config` carries `postgrest_connection_budget`, `auth_connection_budget` and
    `storage_connection_budget`, one per claimant. A fourth would be a number
    with no term in the sum -- which is the shape that lets an unbounded service
    look budgeted.
    """
    derivers = sorted(
        name
        for name in dir(config)
        if name.endswith("_connection_budget") and not name.startswith("_")
    )
    assert derivers == [
        "auth_connection_budget",
        "postgrest_connection_budget",
        "storage_connection_budget",
    ], f"config derives {derivers}; a budget for a claimant that opens no connection is a fiction"


def test_the_deployed_agent_block_publishes_no_pool(schema: dict[str, Any]) -> None:
    """And the document says nothing about a pool either, for the same reason."""
    members = set(schema["$defs"]["deployedMcp"]["properties"])
    suspicious = {name for name in members if "pool" in name or "connection" in name}
    assert not suspicious, (
        f"the deployed agent-plane block publishes {sorted(suspicious)}. A service that "
        "holds no database credential has no pool to publish, and a field here would be "
        "the first place a reader looked to find out otherwise"
    )

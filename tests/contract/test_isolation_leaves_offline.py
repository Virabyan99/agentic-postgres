"""Every leaf of a deployed document is classified -- OFFLINE (Session 38, D2162).

`tests/deployment/test_session12_isolation_matrix.py::test_every_leaf_is_classified`
runs only against two live documents, so a field a session adds is found one
TRIP late: `backup.mirror.*` (D1029), `connectors.enabled` (D1853) and
`control.enabled` (D2142) each reached a sweep unclassified and cost a repair.
This module asks the same question on every push, with the SAME categories
(`tests/deployment/isolation_matrix.py`, D2195), over two readings:

1. **Built documents.** Each example manifest is rendered by the product's own
   renderer and assembled by `deployed_output.build_deployed_document` with every
   route `ready` -- the shape a host records -- so the leaves are the ones a real
   deployment carries, nulls included.
2. **The schema.** Every property path the deployed branch of
   `schemas/outputs.schema.json` declares, optional blocks and both arms of a
   nullable object included -- so a member is classified the day the schema
   gains it, whether or not any fixture fills it.

Control (D499): a planted leaf no category names is reported by both readers.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.contract.test_deployed_output import PUBLISHED_API, PUBLISHED_JWT, build
from tests.deployment.isolation_matrix import classify

from agentic_postgres import REPO_ROOT, config, deployed_output, rendering, upgrade_plan

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"
EXAMPLES = ("project.example.yaml", "project.second.example.yaml", "project.control.example.yaml")


@pytest.fixture(scope="module")
def built_documents(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    generated = tmp_path_factory.mktemp("leaves") / "generated"
    patch = pytest.MonkeyPatch()
    patch.setattr(rendering, "GENERATED_ROOT", generated)
    patch.setattr(rendering, "STAGING_ROOT", generated / ".staging")
    patch.setattr(rendering, "LOCK_ROOT", generated / ".locks")
    try:
        documents = {}
        for name in EXAMPLES:
            directory = rendering.render_project(
                REPO_ROOT / name, CAPABILITIES, validate_compose=False
            )
            rendered = json.loads((directory / "outputs.json").read_text(encoding="utf-8"))
            # What THIS project serves, from its own manifest and render, so the
            # document passes the coherence rules a host's would (a control route
            # only on the control plane; REST only where the manifest publishes it).
            manifest = config.load_project_manifest(REPO_ROOT / name)
            rest_enabled = bool(((manifest.get("api") or {}).get("rest") or {}).get("enabled"))
            control = bool((rendered.get("control") or {}).get("enabled"))
            documents[name] = build(
                rendered,
                rest_status="ready" if rest_enabled else "unavailable",
                rest_enabled=rest_enabled,
                docs_status="ready",
                app_status="ready",
                app_docs_status="ready",
                storage_status="ready",
                mcp_status="ready",
                metrics_status="ready",
                control_status="ready" if control else "unavailable",
                api=PUBLISHED_API if rest_enabled else deployed_output.API_NOT_PUBLISHED,
                jwt=PUBLISHED_JWT,
                deployed_through_session=38,
            )
        return documents
    finally:
        patch.undo()


def _schema_leaves(node: Any, path: str, defs: dict[str, Any]) -> set[str]:
    """Every dotted path a document valid under ``node`` can carry a scalar at.

    Maps (`additionalProperties` / `patternProperties` schemas) contribute a `*`
    segment, lists a `[0]`, and a nullable object or list contributes its own path
    too -- a null there is a leaf in a real document (`migrations.project_set` is
    the case D1029 repeated)."""
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return _schema_leaves(defs[name], path, defs)
    found: set[str] = set()
    for key in ("oneOf", "anyOf", "allOf"):
        for branch in node.get(key, []):
            found |= _schema_leaves(branch, path, defs)
    types = node.get("type", [])
    types = [types] if isinstance(types, str) else list(types)
    is_object = "object" in types or "properties" in node
    is_array = "array" in types or "items" in node
    if is_object:
        for key, child in node.get("properties", {}).items():
            found |= _schema_leaves(child, f"{path}.{key}" if path else key, defs)
        extra = node.get("additionalProperties")
        maps = [extra] if isinstance(extra, dict) else []
        maps += list(node.get("patternProperties", {}).values())
        if extra is True:
            maps.append({})
        for child in maps:
            found |= _schema_leaves(child, f"{path}.*", defs)
        if "null" in types:
            found.add(path)
    elif is_array:
        items = node.get("items")
        if isinstance(items, dict):
            found |= _schema_leaves(items, f"{path}[0]", defs)
        if "null" in types:
            found.add(path)
    elif node == {} or any(key in node for key in ("type", "enum", "const")):
        # A scalar, or a free value (`additionalProperties: true`). A node that is
        # only a constraint -- `if/then/else`, `not`, `required` inside an `allOf`
        # -- names no value and contributes no leaf (the lifecycle's expiry rule
        # was read as a leaf at `project.lifecycle` until this said so).
        found.add(path)
    return found


def _deployed_schema_leaves() -> set[str]:
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))
    defs = schema["$defs"]
    return {leaf for leaf in _schema_leaves(defs["deployedDocument"], "", defs) if leaf}


def test_every_leaf_of_a_built_deployed_document_is_classified(
    built_documents: dict[str, dict[str, Any]],
) -> None:
    """A deployed document built from each example render, and every leaf the
    deployed schema declares, falls in an isolation category."""
    unclassified: dict[str, list[str]] = {}
    for name, document in built_documents.items():
        deployed_output.validate_deployed_document(document)
        missing = sorted(p for p in upgrade_plan.leaves(document) if classify(p) is None)
        if missing:
            unclassified[name] = missing
    missing = sorted(p for p in _deployed_schema_leaves() if classify(p) is None)
    if missing:
        unclassified["outputs.schema.json (deployed)"] = missing
    assert not unclassified, (
        "these deployed-document leaves are in no isolation category -- decide for "
        "each whether it is project scope (MUST_DIFFER), the shared substrate "
        "(MUST_MATCH), or carries no authority (NOT_AUTHORITY_PREFIXES) in "
        "tests/deployment/isolation_matrix.py:\n" + json.dumps(unclassified, indent=2)
    )


def test_a_planted_unclassified_leaf_is_reported(
    built_documents: dict[str, dict[str, Any]],
) -> None:
    """The control: both readers report a leaf no category names."""
    document = json.loads(json.dumps(built_documents["project.example.yaml"]))
    document["zz"] = {"unclassified": 1}
    assert [p for p in upgrade_plan.leaves(document) if classify(p) is None] == ["zz.unclassified"]
    planted = {
        "properties": {
            "zz": {"type": "object", "properties": {"unclassified": {"type": "integer"}}}
        }
    }
    leaves = _schema_leaves(planted, "", {})
    assert [p for p in leaves if classify(p) is None] == ["zz.unclassified"]
    assert len(_deployed_schema_leaves()) > 100, "the schema walk found almost nothing"

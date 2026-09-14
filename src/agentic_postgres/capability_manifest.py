"""A project's capability manifest, beside its migration set (ADR 0201).

**What a project owns here.** `projects/<slug>/capabilities.yaml` at capability
schema 4 -- its own capabilities over its own relations and RPCs, and
optionally the release capabilities it leaves out of ITS lock:

    release:
      disabled: [create_note]

Its compiled contract, `projects/<slug>/contracts/mcp-capabilities.canonical.json`,
is compiled against the MERGED surface (release + project, ADR 0198) and the
project's own snapshot, and `bin/mcp-contract.sh check --project` compares it
byte for byte. The deployed lock is compiled from the JOINED manifest: the
release's capabilities less the disabled ones, plus the project's, against the
merged surface and the project's snapshot (D1147: joined as MANIFESTS, not as
compiled contracts, because a disabled capability behind a grouped tool --
`query_notes` under `query_resource` -- cannot be removed from a compiled tool
without recompiling it).

**A project's capabilities presuppose its reviewed surface.** The contract id
derives from the surface's, the merged surface is what the scopes are approved
against, and the project's snapshot is what the operations are checked
against; all three live beside the migration set (ADR 0198). So a manifest
that names `mcp.capabilities` without `migrations.set` is refused at load,
with that reason -- a project with no relations of its own has nothing to open.

**What a project may not declare**, each refused here with its reason: a
`kind: metadata` capability (the pair is the runtime's own, ADR 0200); a
capability name the release declares, or a new tool under a release tool's
name; a disabled name the release does not declare, or one that is a metadata
tool; a manifest below schema version 4 (its scopes are derived, and the
derivation arrives at 4). A read over an RPC with arguments and an
`agent_rpcs` operation are refused by the compiler and the surface loader
respectively, not here.

Named by `mcp.capabilities` in the project manifest at project schema 6 (the
same repo-relative shape as `migrations.set`), and tracked in the checkout for
ADR 0198's reason: a tool an agent can call is code, not configuration.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_postgres import REPO_ROOT, api_surface, capability_compiler, config, openapi_normalize
from agentic_postgres.config import ManifestError

__all__ = [
    "CONTRACTS_DIRECTORY",
    "PROJECT_CAPABILITIES_NAME",
    "PROJECT_CONTRACT_NAME",
    "PROJECT_REPORT_NAME",
    "PROJECT_SCHEMA_FROM",
    "ProjectInputs",
    "compile_joint_contract",
    "compile_project_contract",
    "disabled_release_capabilities",
    "joined_capabilities",
    "load_contract_document",
    "load_project_capabilities",
    "project_capabilities_path",
    "project_contract_path",
    "project_inputs",
    "project_report_path",
]

PROJECT_CAPABILITIES_NAME = "capabilities.yaml"
CONTRACTS_DIRECTORY = "contracts"
PROJECT_CONTRACT_NAME = "mcp-capabilities.canonical.json"
PROJECT_REPORT_NAME = "evaluation-report.md"

#: The capability schema version a project's manifest must be at or above:
#: the one at which a scope is a shape approved against the surface (ADR
#: 0200). Below it the enum applies, and the enum names only the release's
#: relations, so a project's manifest at 3 could not name its own.
PROJECT_SCHEMA_FROM = 4


def project_capabilities_path(root: Path) -> Path:
    """`projects/<slug>/capabilities.yaml`, from the directory the manifest names."""
    return root / PROJECT_CAPABILITIES_NAME


def project_contract_path(root: Path) -> Path:
    """The project's compiled contract, beside its reviewed surface."""
    return root / CONTRACTS_DIRECTORY / PROJECT_CONTRACT_NAME


def project_report_path(root: Path) -> Path:
    """The project's evaluation report, rendered from its joint contract."""
    return root / CONTRACTS_DIRECTORY / PROJECT_REPORT_NAME


def load_contract_document(path: Path) -> dict[str, Any]:
    """Read a compiled capability contract, REPORTING one that cannot be read.

    **Why this is a function and not four `json.loads` calls** (D1359). The
    documented way to produce a project's contract is a shell redirect::

        bin/mcp-contract.sh compile --project project.yaml > <this path>

    and the shell creates and truncates the target BEFORE the command runs. So
    when `compile` correctly refuses -- which it does for every project until
    its first deploy has produced the OpenAPI snapshot it compiles against --
    the refusal leaves a 0-byte file exactly where a contract belongs. The
    second walk followed that line and the NEXT documented command died in an
    unhandled `json.JSONDecodeError` with exit 1, a code
    `docs/exit-codes.md` does not define.

    ADR 0195's three outcomes: the contract, the absence of one, and **I could
    not read what is there**. The third was folded into a traceback. Absence
    stays each caller's to report -- it is the caller that knows what to
    suggest -- and this reports the other two as a `CapabilityContractError`,
    which every one of these commands already maps to its own convention.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise config.CapabilityContractError(f"{path} could not be read: {error}") from error

    if not raw.strip():
        raise config.CapabilityContractError(
            f"{path} is empty, so there is no contract in it. A compile that REFUSES still "
            "leaves its redirect target behind, because the shell truncates the file before "
            "the command runs -- delete it, and compile again once the snapshot it needs "
            "has been captured."
        )

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise config.CapabilityContractError(
            f"{path} is not readable JSON: {error}. It is written by "
            "`bin/mcp-contract.sh compile`; nothing else should edit it."
        ) from error

    if not isinstance(document, dict):
        raise config.CapabilityContractError(
            f"{path} is {type(document).__name__}, not a JSON object"
        )
    return document


def disabled_release_capabilities(document: dict[str, Any]) -> tuple[str, ...]:
    """The release capabilities a project manifest leaves out, in declared order."""
    return tuple((document.get("release") or {}).get("disabled") or [])


def load_project_capabilities(root: Path) -> dict[str, Any]:
    """Parse, schema-check and validate a project's own capability manifest.

    Through the same strict loader as the release's, so it inherits every
    refusal the manifests get. What is added is the project form's own rules,
    each stated with its reason in the message.
    """
    path = project_capabilities_path(root)
    document = config.load_capabilities_manifest(path)

    if document["schema_version"] < PROJECT_SCHEMA_FROM:
        raise ManifestError(
            f"{path} declares schema_version {document['schema_version']}; a project's "
            f"capability manifest is version {PROJECT_SCHEMA_FROM} or later, where a scope is "
            "a shape approved against the reviewed surface (ADR 0200). Below it the enum "
            "applies, and the enum names only the release's relations."
        )

    metadata = sorted(
        entry["name"] for entry in document["capabilities"] if entry["kind"] == "metadata"
    )
    if metadata:
        raise ManifestError(
            f"{path} declares metadata capabilities {metadata}. The two metadata tools are the "
            f"runtime's own -- {sorted(capability_compiler.METADATA_TOOL_NAMES)} -- and every "
            "lock carries exactly them; a project answers from the same lock and declares "
            "neither (ADR 0200)."
        )

    disabled = disabled_release_capabilities(document)
    withheld = sorted(set(disabled) & set(capability_compiler.METADATA_TOOL_NAMES))
    if withheld:
        raise ManifestError(
            f"{path} disables {withheld} in release.disabled. The runtime requires both "
            "metadata tools; a lock without either is a surface no caller can discover."
        )
    return document


def joined_capabilities(release: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """The manifest the deployed lock is compiled from (ADR 0201).

    The release's capabilities less the ones the project disables, plus the
    project's own, at the release manifest's schema version. Refused: a
    capability name the project declares that the release already does; a
    NEW tool under a release tool's name; and a disabled name the release
    does not declare -- a typo there would otherwise disable nothing and
    report success (D927's shape).
    """
    release_names = {entry["name"] for entry in release["capabilities"]}
    release_tools = {entry.get("tool") or entry["name"] for entry in release["capabilities"]}

    collisions = sorted({entry["name"] for entry in project["capabilities"]} & release_names)
    if collisions:
        raise ManifestError(
            f"the project manifest declares capabilities {collisions}, which the release "
            "already declares. A project's capability is its own; narrowing a release one "
            "is the profile's job (ADR 0183) and removing one is release.disabled's."
        )

    # A project may GROUP a read under a release tool -- `tool: query_resource`
    # over its own relation is ADR 0120's shape and the point of the exercise.
    # What it may not do is declare a NEW tool under a release tool's name,
    # which is what a project capability without `tool:` whose name is a
    # release tool would be: two tools, one name, and the runtime registers the
    # second over the first.
    stolen = sorted(
        entry["name"]
        for entry in project["capabilities"]
        if entry.get("tool") is None and entry["name"] in release_tools
    )
    if stolen:
        raise ManifestError(
            f"the project manifest declares {stolen} as tools of its own, and the release "
            "already serves tools by those names. Group a read under the release tool with "
            "`tool:`, or name the project's tool for the project."
        )

    disabled = disabled_release_capabilities(project)
    unknown = sorted(set(disabled) - release_names)
    if unknown:
        raise ManifestError(
            f"release.disabled names {unknown}, which the release manifest does not declare "
            f"({sorted(release_names)}). A name that disables nothing would report success."
        )

    joined = copy.deepcopy(release)
    joined["capabilities"] = [
        entry for entry in joined["capabilities"] if entry["name"] not in disabled
    ] + copy.deepcopy(project["capabilities"])
    joined.pop("release", None)
    return joined


@dataclass(frozen=True)
class ProjectInputs:
    """Everything a project's contract and its joint lock are compiled from."""

    #: `projects/<slug>`, absolute.
    root: Path
    #: The project's own capability manifest, loaded and validated.
    capabilities: dict[str, Any]
    #: The MERGED reviewed surface (release + project, ADR 0198).
    surface: dict[str, Any]
    #: What the project's approved snapshot publishes.
    published_objects: frozenset[str]
    #: The project's own contract id, derived from its reviewed surface's.
    contract_id: str
    #: The joint lock's contract id, `<release>+<project>`.
    joint_contract_id: str


def project_inputs(
    manifest: dict[str, Any], *, repo_root: Path = REPO_ROOT
) -> ProjectInputs | None:
    """The compile inputs a project manifest names, or None when it names no
    capability manifest of its own.

    The reviewed surface and the snapshot are required rather than defaulted
    to the release's (D1117's lesson, from the other side): the release's
    snapshot publishes none of the project's objects, so a project capability
    checked against it could never compile, and a project contract id derived
    from the release's surface would name the wrong surface.
    """
    named = config.project_capabilities(manifest)
    if named is None:
        return None
    set_named = config.project_migration_set(manifest)
    if set_named is None:
        raise ManifestError(
            f"mcp.capabilities names {named!r} and the manifest declares no migrations.set. "
            "A project's capabilities are compiled against its reviewed surface and checked "
            "against its snapshot, and both live beside its migration set (ADR 0198); a "
            "project with no relations of its own has nothing to open (ADR 0201)."
        )
    root = repo_root / named
    set_root = repo_root / set_named

    surface_path = api_surface.project_contract_path(set_root)
    if not surface_path.is_file():
        # **A CONTRACT failure, not invalid operator input** (D1360). The
        # manifest is well formed and names a real set; what is missing is an
        # artefact of the project's own review. `CapabilityContractError`'s
        # own docstring draws that line, and these two sites never got it, so
        # the evaluation report exited 2 where compile, check and generate all
        # exited 5 on this very sentence.
        raise config.CapabilityContractError(
            f"{set_named} has no reviewed surface at {surface_path}; a project's capabilities "
            "are approved against it (ADR 0201). Write it beside the set (ADR 0198) and check "
            "it with `bin/api-contract.sh --check --project <manifest>`."
        )
    snapshot_path = api_surface.project_snapshot_path(set_root)
    if not snapshot_path.is_file():
        raise config.CapabilityContractError(
            f"{set_named} has no approved snapshot at {snapshot_path}. It is captured from the "
            "project's deployment with `bin/api-contract.sh --update --project <manifest> "
            "--project-outputs <deployed outputs.json>`, reviewed and committed (ADR 0198)."
        )

    project_surface = api_surface.load_project_surface(surface_path)
    merged = api_surface.merged_surface(api_surface.load_surface(), project_surface)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    project_id = capability_compiler.project_contract_id(project_surface["contract_id"])
    return ProjectInputs(
        root=root,
        capabilities=load_project_capabilities(root),
        surface=merged,
        published_objects=frozenset(openapi_normalize.declared_objects(snapshot)),
        contract_id=project_id,
        joint_contract_id=capability_compiler.joint_contract_id(
            capability_compiler.CONTRACT_ID, project_id
        ),
    )


def _refuse_platform_operations(project: dict[str, Any], surface: dict[str, Any]) -> None:
    """A project capability may not name an `agent_rpcs` operation (ADR 0201).

    The merged surface carries the release's agent-only functions, so the
    compiler would resolve one; but they describe the whole database (the audit
    pair writes every project's audit rows) and stay platform-only, so a tenant
    tool always addresses a PUBLISHED object (ADR 0050 from the other side,
    D1128). Refused by name, before the compiler sees it.
    """
    operations = capability_compiler.surface_operations(surface)
    platform = sorted(
        f"{entry['name']} -> {entry['operation']['operation_id']}"
        for entry in project["capabilities"]
        if entry["operation"]["source"] in capability_compiler.BACKED_SOURCES
        and (operations.get(entry["operation"]["operation_id"]) or {}).get("section")
        == "agent_rpcs"
    )
    if platform:
        raise ManifestError(
            f"the project manifest backs {platform} with agent-plane operations. An operation "
            "in agent_rpcs is the platform's -- it describes the whole database -- and a "
            "project's tool addresses only what the reviewed surface publishes (ADR 0201)."
        )


def compile_project_contract(inputs: ProjectInputs) -> dict[str, Any]:
    """The project's OWN contract: its capabilities, the merged surface, its
    snapshot. What `projects/<slug>/contracts/mcp-capabilities.canonical.json`
    holds once reviewed."""
    _refuse_platform_operations(inputs.capabilities, inputs.surface)
    return capability_compiler.compile_canonical(
        capabilities=inputs.capabilities,
        surface=inputs.surface,
        published_objects=set(inputs.published_objects),
        contract_id=inputs.contract_id,
    )


def compile_joint_contract(
    release_capabilities: dict[str, Any], inputs: ProjectInputs
) -> dict[str, Any]:
    """The contract the project's deployed lock is compiled from: the joined
    manifest against the merged surface and the project's snapshot."""
    _refuse_platform_operations(inputs.capabilities, inputs.surface)
    return capability_compiler.compile_canonical(
        capabilities=joined_capabilities(release_capabilities, inputs.capabilities),
        surface=inputs.surface,
        published_objects=set(inputs.published_objects),
        contract_id=inputs.joint_contract_id,
    )

#!/usr/bin/env python
"""Compile, compare and refuse to approve the agent capability contract.

`bin/api-contract.py`'s split, applied to the agent surface, and for its reason
(ADR 0050): a gate that can approve its own subject is not a gate.

``compile``  streams the candidate canonical contract to **stdout**. There is no
             output-path option and that is not an omission: the operator's own
             shell does the redirect, so a candidate lands where a human has to
             look at it before committing it.
``check``    compares and **contains no writer at all**. It compiles the
             committed manifest against the committed reviewed surface and the
             approved OpenAPI snapshot, and compares the result byte-for-byte
             against the committed canonical contract. The gate runs only this.
             With ``--project`` it also applies that project's ``mcp.profile``
             to the approved contract and exits 5 if the profile would widen
             any bound (ADR 0183) -- the refusal is here, at compile time.
``lock``     resolves the canonical contract for one project, from that
             project's rendered outputs and its manifest, whose profile narrows
             the lock. ``--project`` is required, so a deploy cannot compile a
             lock that ignores one. Also stdout-only.

**A project's own capabilities** (ADR 0201, Session 21). A project manifest at
schema 6 may name ``mcp.capabilities: projects/<slug>``, a capability manifest
of the project's own beside its migration set. Then ``compile --project FILE``
streams THAT project's contract, compiled against the merged surface and the
project's snapshot; ``check --project FILE`` compares it byte for byte with the
committed ``projects/<slug>/contracts/mcp-capabilities.canonical.json`` (and
still applies the profile, to the joint contract); and ``lock`` compiles the
JOINT contract -- the release's capabilities less the ones the project
disables, plus the project's own -- after proving both committed contracts
are what their manifests compile to. A manifest that names no capability
manifest takes every path it took before.

**The compiler reads OpenAPI and never enumerates from it.** Every question it
asks starts from a declared capability; nothing iterates the served document
looking for things to expose. That asymmetry is `AGT-DRIFT-001`, and
`capability_compiler` is where it lives.

Exit codes (runbook section 2 convention):
  0  success
  2  invalid operator input
  3  missing local prerequisite
  5  the contracts are out of sync, or no approved contract exists yet
"""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    capability_manifest,
    config,
    openapi_normalize,
    scope_registry,
)

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_CONTRACT = 5

#: The approved contract, at a fixed path for the reason `api_surface` fixes
#: its own: a contract that can be pointed somewhere else can be pointed at a
#: copy of the thing it constrains.
CANONICAL_PATH = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"

SNAPSHOT_PATH = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
DEFAULT_CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"


def fail(code: int, message: str) -> int:
    print(f"mcp-contract: {message}", file=sys.stderr)
    return code


def _inputs(capabilities_path: Path) -> tuple[dict, dict, set[str]]:
    if not capabilities_path.is_file():
        raise FileNotFoundError(capabilities_path)
    if not SNAPSHOT_PATH.is_file():
        raise FileNotFoundError(SNAPSHOT_PATH)

    capabilities = config.load_capabilities_manifest(capabilities_path)
    surface = api_surface.load_surface()
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return capabilities, surface, openapi_normalize.declared_objects(snapshot)


def compile_candidate(capabilities_path: Path) -> bytes:
    capabilities, surface, published = _inputs(capabilities_path)
    canonical = capability_compiler.compile_canonical(
        capabilities=capabilities, surface=surface, published_objects=published
    )
    return capability_compiler.canonical_bytes(canonical)


def _manifest(project_path: Path) -> dict:
    if not project_path.is_file():
        raise FileNotFoundError(project_path)
    return config.load_project_manifest(project_path)


def _profile(manifest: dict) -> dict | None:
    """The project's narrowing, or None for a version 1 manifest (ADR 0183).

    Loaded through `config.load_project_manifest`, so the schema has already
    refused a profile on a version 1 document and required one on a version 2
    -- the None here is a manifest that predates profiles, not one that forgot.
    """
    if manifest["schema_version"] < config.PROJECT_PROFILE_FROM:
        return None
    return manifest["mcp"]["profile"]


def _project_contract(inputs: capability_manifest.ProjectInputs) -> bytes:
    """The project's own contract, as the bytes its committed file must hold."""
    return capability_compiler.canonical_bytes(capability_manifest.compile_project_contract(inputs))


def _require_project_contract_current(inputs: capability_manifest.ProjectInputs) -> int | None:
    """Exit 5 unless the committed project contract is what its manifest compiles to."""
    path = capability_manifest.project_contract_path(inputs.root)
    if not path.is_file():
        return fail(
            EXIT_CONTRACT,
            f"no approved capability contract at {path.relative_to(REPO_ROOT)}. Compile it "
            "with `bin/mcp-contract.sh compile --project <manifest> > <that path>`, READ it, "
            "and commit it (ADR 0201)",
        )
    if _project_contract(inputs) != path.read_bytes():
        return fail(
            EXIT_CONTRACT,
            f"{inputs.root.relative_to(REPO_ROOT)}/capabilities.yaml no longer compiles to "
            f"{path.relative_to(REPO_ROOT)}. Either the project's manifest changed and its "
            "contract was not re-approved, or the merged surface or the project's snapshot "
            "moved underneath it. Re-compile, READ the difference, then commit",
        )
    return None


def _report_profile(canonical: dict, profile: dict | None) -> None:
    """What the profile narrowed, per tool and field, on standard output."""
    if profile is None:
        print("mcp-contract: the project manifest is schema version 1 and declares no profile")
        return
    if not profile:
        print("mcp-contract: the project profile is empty; the lock is the approved contract")
        return
    compiled = {tool["name"]: tool for tool in canonical["tools"]}
    print("mcp-contract: the project profile narrows the approved contract:")
    for tool_name, entries in sorted(profile.items()):
        for field, value in sorted(entries.items()):
            before = (
                {r["name"]: r["max_rows"] for r in compiled[tool_name]["resources"]}
                if field == "max_rows"
                else compiled[tool_name][field]
            )
            print(f"  {tool_name}.{field:<21} {before!r} -> {value!r}")


def command_compile(arguments: argparse.Namespace) -> int:
    try:
        if arguments.project is None:
            candidate = compile_candidate(arguments.capabilities)
        else:
            inputs = capability_manifest.project_inputs(_manifest(arguments.project))
            if inputs is None:
                return fail(
                    EXIT_INPUT,
                    f"{arguments.project} declares no mcp.capabilities, so it has no contract "
                    "of its own to compile; `compile` without --project is the release's",
                )
            candidate = _project_contract(inputs)
        sys.stdout.write(candidate.decode("utf-8"))
    except FileNotFoundError as exc:
        return fail(EXIT_PREREQUISITE, f"missing input: {exc}")
    except config.ManifestError as exc:
        return fail(EXIT_CONTRACT, str(exc))
    return EXIT_OK


def command_check(arguments: argparse.Namespace) -> int:
    if not CANONICAL_PATH.is_file():
        return fail(
            EXIT_CONTRACT,
            f"no approved capability contract at {CANONICAL_PATH.relative_to(REPO_ROOT)}. "
            "Compile one with `bin/mcp-contract.sh compile > <path>` and review it before "
            "committing -- a contract compiled and approved in one step is a surface nobody "
            "read",
        )
    try:
        candidate = compile_candidate(arguments.capabilities)
    except FileNotFoundError as exc:
        return fail(EXIT_PREREQUISITE, f"missing input: {exc}")
    except config.ManifestError as exc:
        return fail(EXIT_CONTRACT, str(exc))

    approved = CANONICAL_PATH.read_bytes()
    if candidate != approved:
        return fail(
            EXIT_CONTRACT,
            "the capability manifest no longer compiles to the approved contract. Either the "
            "manifest changed and the contract was not re-approved, or the reviewed API "
            "surface moved underneath it. Re-compile, READ the difference, then commit",
        )

    document = json.loads(approved.decode("utf-8"))
    names = tuple(tool["name"] for tool in document["tools"])
    if names != tuple(sorted(names)):
        return fail(EXIT_CONTRACT, f"the approved contract's tools are not sorted: {names}")

    print(f"mcp-contract: the manifest compiles to the approved contract ({len(names)} tools)")
    for tool in document["tools"]:
        sets = " | ".join(",".join(scopes) for scopes in tool["discovery_scope_sets"])
        print(f"  {tool['name']:<20} {tool['kind']:<9} {sets}")

    # **A profile is refused HERE, at compile time, or not at all** (ADR 0183,
    # D867). `check --project` applies one project's profile to the approved
    # contract in a checkout, with no host and no root, so a profile that would
    # widen a bound fails the gate before a deployment exists rather than
    # becoming one more runtime denial. Still no writer: the narrowed contract
    # is computed and discarded.
    if arguments.project is not None:
        try:
            manifest = _manifest(arguments.project)
            profile = _profile(manifest)
            # A project's OWN contract, compared byte for byte with the one it
            # committed (ADR 0201) -- the same comparison as the release's,
            # against the merged surface and the project's snapshot. The
            # profile is then applied to the JOINT contract, because a profile
            # may name a project tool as readily as a release one.
            inputs = capability_manifest.project_inputs(manifest)
            if inputs is not None:
                problem = _require_project_contract_current(inputs)
                if problem is not None:
                    return problem
                capabilities = config.load_capabilities_manifest(arguments.capabilities)
                document = capability_manifest.compile_joint_contract(capabilities, inputs)
                print(
                    f"mcp-contract: {inputs.root.relative_to(REPO_ROOT)}/capabilities.yaml "
                    f"compiles to its approved contract; the joint contract "
                    f"{document['contract_id']} carries {document['tool_count']} tools"
                )
            if profile is not None:
                capability_compiler.apply_profile(document, profile)
        except FileNotFoundError as exc:
            return fail(EXIT_PREREQUISITE, f"missing input: {exc}")
        except config.ManifestError as exc:
            return fail(EXIT_CONTRACT, f"the project is refused: {exc}")
        _report_profile(document, profile)
    return EXIT_OK


def command_lock(arguments: argparse.Namespace) -> int:
    if not CANONICAL_PATH.is_file():
        return fail(EXIT_CONTRACT, "no approved capability contract to lock")
    try:
        outputs = json.loads(arguments.outputs.read_text(encoding="utf-8"))
    except OSError as exc:
        return fail(EXIT_PREREQUISITE, f"cannot read the rendered outputs: {exc}")

    # **The RENDERED shape, and the deployed one is refused by name** (D465).
    #
    # `routes.rest` is a string on the rendered branch and a published-route
    # object on the deployed one. Handed the wrong branch, this compiled happily
    # and wrote a lock whose `upstream` was a dict -- and the runtime refused it
    # at container start, four steps and one restart later. A wrong input that
    # produces an artefact is worse than one that produces an error: the artefact
    # gets published.
    upstream = (outputs.get("routes") or {}).get("rest")
    if not isinstance(upstream, str):
        return fail(
            EXIT_PREREQUISITE,
            f"routes.rest is {type(upstream).__name__}, not str. This looks like a "
            "DEPLOYED document, where routes.rest is a published-route object; the "
            "lock is compiled from the RENDERED one, where it is the URL itself "
            "(ADR 0126, D465).",
        )

    # **`--project` is required for a lock, not optional** (ADR 0183). An
    # optional flag the deploy forgot to pass would compile a lock ignoring the
    # project's profile and report success -- D927's shape, one step later. The
    # profile is None for a version 1 manifest, and the lock is then
    # byte-identical to the one this command compiled before profiles existed.
    try:
        manifest = _manifest(arguments.project)
        profile = _profile(manifest)
        inputs = capability_manifest.project_inputs(manifest)
    except FileNotFoundError as exc:
        return fail(EXIT_PREREQUISITE, f"missing input: {exc}")
    except config.ManifestError as exc:
        return fail(EXIT_CONTRACT, f"cannot read the project manifest: {exc}")

    canonical = json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))
    surface = None
    sources: dict[str, str] = {}
    if inputs is not None:
        # **The joint contract, and only from approved parts** (ADR 0201,
        # D1147). The release's committed contract and the project's are each
        # proved to be what their manifests compile to, and the lock is then
        # compiled from the two manifests JOINED -- the release's capabilities
        # less the ones this project disables, plus the project's own --
        # against the merged surface and the project's snapshot. Joined as
        # manifests rather than as compiled contracts, because a disabled
        # capability behind a grouped tool cannot be removed from a compiled
        # tool without recompiling it.
        try:
            if compile_candidate(arguments.capabilities) != CANONICAL_PATH.read_bytes():
                return fail(
                    EXIT_CONTRACT,
                    "the release's capability manifest no longer compiles to the approved "
                    "contract; run `bin/mcp-contract.sh check` and re-approve it before "
                    "compiling a lock that joins it",
                )
            problem = _require_project_contract_current(inputs)
            if problem is not None:
                return problem
            capabilities = config.load_capabilities_manifest(arguments.capabilities)
            canonical = capability_manifest.compile_joint_contract(capabilities, inputs)
        except FileNotFoundError as exc:
            return fail(EXIT_PREREQUISITE, f"missing input: {exc}")
        except config.ManifestError as exc:
            return fail(EXIT_CONTRACT, f"cannot compile the joint contract: {exc}")
        surface = inputs.surface
        project_contract = capability_manifest.project_contract_path(inputs.root)
        sources = {
            "project_capabilities_sha256": sha256(
                capability_manifest.project_capabilities_path(inputs.root).read_bytes()
            ).hexdigest(),
            "project_contract_sha256": sha256(project_contract.read_bytes()).hexdigest(),
        }

    try:
        lock = capability_compiler.compile_lock(
            canonical=canonical,
            project_key=outputs["project"]["key"],
            # The ONE address the runtime may call. Read from the document rather
            # than rebuilt, so this never becomes a second derivation of an
            # address `naming` owns (ADR 0002, ADR 0053).
            upstream=upstream,
            # Digests of the BYTES, not of the parsed documents. A digest over a
            # re-serialization is equal for two files whose comments differ, and
            # the comments are where the reasoning lives -- which is the reason
            # `api_surface.contract_digest` reads bytes too.
            sources={
                "capabilities_sha256": sha256(arguments.capabilities.read_bytes()).hexdigest(),
                "api_surface_sha256": api_surface.contract_digest(),
                "canonical_openapi_sha256": sha256(SNAPSHOT_PATH.read_bytes()).hexdigest(),
                "project_manifest_sha256": sha256(arguments.project.read_bytes()).hexdigest(),
                # And the project's two, when it declares capabilities: a
                # lock whose inputs cannot be identified is a surface nobody
                # can prove was reviewed.
                **sources,
            },
            profile=profile,
            # The deployment's scope classes, for the issuer (ADR 0200). Over
            # the RELEASE surface for a project without capabilities of its
            # own, and over the MERGED one when it declares some (ADR 0201):
            # that is where a tenant's scope becomes issuable on one
            # deployment and on no other.
            vocabulary=scope_registry.vocabulary_block(surface),
        )
    except (KeyError, config.ManifestError) as exc:
        return fail(EXIT_CONTRACT, f"cannot compile the lock: {exc}")

    sys.stdout.write(capability_compiler.canonical_bytes(lock).decode("utf-8"))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcp-contract", description=__doc__)
    parser.add_argument(
        "--capabilities",
        type=Path,
        default=DEFAULT_CAPABILITIES,
        help="the capability manifest to compile (default: capabilities.example.yaml)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    compile_ = commands.add_parser("compile", help="compile a candidate contract to stdout")
    compile_.add_argument(
        "--project",
        type=Path,
        default=None,
        help="a project manifest naming mcp.capabilities; streams THAT project's contract, "
        "compiled against the merged surface and its snapshot (ADR 0201)",
    )
    check = commands.add_parser("check", help="compare; never write")
    check.add_argument(
        "--project",
        type=Path,
        default=None,
        help="a project manifest whose mcp.profile is applied to the approved contract and "
        "refused if it would widen any bound (ADR 0183); when it names mcp.capabilities, "
        "the project's committed contract is compared with what its manifest compiles to "
        "(ADR 0201)",
    )
    lock = commands.add_parser("lock", help="resolve the approved contract for one project")
    lock.add_argument("--outputs", type=Path, required=True, help="a rendered outputs.json")
    lock.add_argument(
        "--project",
        type=Path,
        required=True,
        help="the project manifest; its mcp.profile narrows the lock (ADR 0183)",
    )

    arguments = parser.parse_args(argv)
    return {
        "compile": command_compile,
        "check": command_check,
        "lock": command_lock,
    }[arguments.command](arguments)


if __name__ == "__main__":
    raise SystemExit(main())

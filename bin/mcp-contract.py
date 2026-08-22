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
``lock``     resolves the canonical contract for one project, from that
             project's rendered outputs. Also stdout-only.

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
    config,
    openapi_normalize,
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


def command_compile(arguments: argparse.Namespace) -> int:
    try:
        sys.stdout.write(compile_candidate(arguments.capabilities).decode("utf-8"))
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

    canonical = json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))
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
            },
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
    commands.add_parser("compile", help="compile a candidate contract to stdout")
    commands.add_parser("check", help="compare; never write")
    lock = commands.add_parser("lock", help="resolve the approved contract for one project")
    lock.add_argument("--outputs", type=Path, required=True, help="a rendered outputs.json")

    arguments = parser.parse_args(argv)
    return {
        "compile": command_compile,
        "check": command_check,
        "lock": command_lock,
    }[arguments.command](arguments)


if __name__ == "__main__":
    raise SystemExit(main())

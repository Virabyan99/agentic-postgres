#!/usr/bin/env python3
"""Generate a typed client for one project, from the contracts it was reviewed against.

Reached as `apg generate` (ADR 0093). `bin/generate.sh` decides every argument
error before this runs; what is left here is reading the four inputs, building
the IR, emitting the package and either writing it or comparing it.

**Four inputs, and the deployed document is not one of them** (ADR 0204,
ADR 0158). This command reads the RENDERED document only, and only for the
project's key and its rendered directory -- never `routes.*`, never a live
address. A client that learned the live hash from a deployed document is this
session's named stop condition; it learns it at runtime, from the service, as
the caller.

Exit codes (runbook §2 convention):
  0  success, or `--check` found no drift
  2  invalid operator input
  3  a missing local prerequisite
  4  the project has not been rendered, naming the command that renders it
  5  a contract that could not produce a client, or `--check` found drift
"""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    capability_manifest,
    client_ir,
    client_typescript,
    compatibility,
    config,
    deployed_output,
    naming,
    openapi_normalize,
    scope_registry,
    template_version,
)

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_NOT_RENDERED = 4
EXIT_CONTRACT = 5

#: Where the IR is written beside the client. `--check` and the next
#: generation's `classify_changes` both read it, which is why it is a file and
#: not recomputed: the previous IR is the previous CONTRACT's, and a contract
#: that is no longer in the tree cannot be rebuilt from the tree.
IR_MANIFEST = "generated.json"

APP_SNAPSHOT = REPO_ROOT / "contracts" / "app-openapi.canonical.json"
CANONICAL_MCP = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
RELEASE_SNAPSHOT = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"


def fail(code: int, message: str) -> None:
    print(f"generate: {message}", file=sys.stderr)
    raise SystemExit(code)


def versions_value(name: str) -> str:
    """One pinned value out of `versions.env`, which is the authority for it."""
    path = REPO_ROOT / "versions.env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(EXIT_PREREQUISITE, f"cannot read {path}: {error}")
    for line in lines:
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    fail(EXIT_PREREQUISITE, f"{path} pins no {name}; run bin/lock-versions.sh")
    raise AssertionError("unreachable")


def project_key_of(project_path: Path) -> str:
    """The key this manifest derives, through `naming` and nothing else.

    ADR 0002: one authority for a derived identity. `slug`, which is what every
    other caller passes -- `bin/dev.py:95` records what reading `name` cost.
    """
    try:
        manifest = config.load_project_manifest(project_path)
    except config.ManifestError as error:
        fail(EXIT_CONTRACT, f"{project_path} did not load: {error}")
    project = manifest["project"]
    return naming.project_key(project["slug"], project["environment"])


def load_inputs(project_path: Path, capabilities_path: Path):
    """The merged surface, the snapshot, the lock and the project's root.

    A project that declares a migration set is generated from ITS surface and
    ITS snapshot (ADR 0198, ADR 0201); one that declares none is generated from
    the release's. Both are real cases in this tree -- `alpha` declares no set
    and is the control that the boundary exists.
    """
    try:
        manifest = config.load_project_manifest(project_path)
        inputs = capability_manifest.project_inputs(manifest)
    except config.ManifestError as error:
        fail(EXIT_CONTRACT, f"cannot read the project manifest: {error}")
    except FileNotFoundError as error:
        fail(EXIT_PREREQUISITE, f"missing input: {error}")

    try:
        canonical = capability_manifest.load_contract_document(CANONICAL_MCP)
    except config.CapabilityContractError as error:
        fail(EXIT_CONTRACT, str(error))
    sources: dict[str, str] = {}
    vocabulary_surface = None
    root = None

    if inputs is not None:
        try:
            capabilities = config.load_capabilities_manifest(capabilities_path)
            canonical = capability_manifest.compile_joint_contract(capabilities, inputs)
        except config.ManifestError as error:
            fail(EXIT_CONTRACT, f"cannot compile the joint contract: {error}")
        vocabulary_surface = inputs.surface
        root = inputs.root
        sources = {
            "project_capabilities_sha256": sha256(
                capability_manifest.project_capabilities_path(root).read_bytes()
            ).hexdigest(),
            "project_contract_sha256": sha256(
                capability_manifest.project_contract_path(root).read_bytes()
            ).hexdigest(),
        }
        surface = inputs.surface
        snapshot_path = api_surface.project_snapshot_path(root)
    else:
        surface = api_surface.load_surface()
        snapshot_path = RELEASE_SNAPSHOT

    if not snapshot_path.is_file():
        fail(
            EXIT_PREREQUISITE,
            f"{snapshot_path} is not there, so there is no approved surface to generate "
            "against. Capture it with `bin/api-contract.sh --update` after the deploy that "
            "serves it",
        )

    try:
        lock = capability_compiler.compile_lock(
            canonical=canonical,
            project_key=project_key_of(project_path),
            # **Deliberately not an address.** The lock's `upstream` is the one
            # URL the RUNTIME may call; a generated client is handed its URL by
            # whoever runs it, and baking a deployment's address into a
            # committed artefact is how a client ends up pointed at somebody
            # else's database. The IR reads the lock's tools, never its
            # upstream, and a test asserts no emitted file carries a URL.
            upstream="https://client.invalid/api/rest",
            sources={
                "capabilities_sha256": sha256(capabilities_path.read_bytes()).hexdigest(),
                "api_surface_sha256": api_surface.contract_digest(),
                "canonical_openapi_sha256": sha256(RELEASE_SNAPSHOT.read_bytes()).hexdigest(),
                "project_manifest_sha256": sha256(project_path.read_bytes()).hexdigest(),
                **sources,
            },
            profile=None,
            vocabulary=scope_registry.vocabulary_block(vocabulary_surface),
        )
    except (KeyError, config.ManifestError) as error:
        fail(EXIT_CONTRACT, f"cannot compile the lock: {error}")

    return surface, json.loads(snapshot_path.read_text(encoding="utf-8")), lock, root


def default_out(root: Path | None) -> Path:
    return (root / "clients" / "typescript") if root else (REPO_ROOT / "clients" / "typescript")


def previous(out: Path) -> tuple[client_ir.IR | None, str | None]:
    """The IR and version this directory was last generated with, if any."""
    manifest = out / IR_MANIFEST
    package = out / "package.json"
    ir = None
    version = None
    if manifest.is_file():
        try:
            ir = client_ir.from_document(json.loads(manifest.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, client_ir.ClientIrError) as error:
            fail(
                EXIT_CONTRACT,
                f"{manifest} is there but did not parse as an IR ({error}). It is written by "
                "this command; if it was edited, delete it and regenerate rather than "
                "comparing against something nobody wrote",
            )
    if package.is_file():
        try:
            version = json.loads(package.read_text(encoding="utf-8")).get("version")
        except json.JSONDecodeError:
            version = None
    return ir, version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generate", add_help=False)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument(
        "--capabilities", type=Path, default=REPO_ROOT / "capabilities.example.yaml"
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)

    key = project_key_of(arguments.project)

    # The RENDERED document, for one reason only: to refuse a project this
    # checkout has not rendered, with the command that renders it (D975).
    try:
        deployed_output.read_rendered_document(key, runtime=False)
    except deployed_output.RenderedDocumentAbsent:
        fail(
            EXIT_NOT_RENDERED,
            f"{key} has not been rendered in this checkout. Render it first:\n"
            f"  ./deploy.sh --project {arguments.project} "
            f"--capabilities {arguments.capabilities} --render-only",
        )
    except deployed_output.RenderedDocumentUnreadable as error:
        fail(EXIT_PREREQUISITE, str(error))

    surface, snapshot, lock, root = load_inputs(arguments.project, arguments.capabilities)

    out = (arguments.out or default_out(root)).resolve()
    try:
        out.relative_to(REPO_ROOT.resolve())
    except ValueError:
        fail(
            EXIT_INPUT,
            f"--out {out} is outside this checkout. A generated client is a tracked "
            "artefact of the project it was generated for; writing one anywhere on the "
            "filesystem is not this command's business",
        )

    try:
        ir = client_ir.build(
            surface=surface,
            snapshot=snapshot,
            app_snapshot=json.loads(APP_SNAPSHOT.read_text(encoding="utf-8")),
            lock=lock,
            project_root=str(root.relative_to(REPO_ROOT)) if root else None,
            pt_sources=client_ir.project_pt_sources(root),
            app_snapshot_bytes=APP_SNAPSHOT.read_bytes(),
            # The TEMPLATE's version, carried as provenance. The CLIENT's own
            # number is derived below from the IR diff and moves independently
            # (ADR 0204): a client regenerated from an unchanged contract does
            # not move, whatever the template did.
            template_version=template_version(),
        )
    except client_ir.ClientIrError as error:
        fail(EXIT_CONTRACT, str(error))

    before, last_version = previous(out)
    changes = client_ir.classify_changes(before, ir) if before else ()

    # **An unchanged contract does not move the number** (D1224). The rule as
    # planned -- *"the previous version bumped by `required_level(...)`"* -- moves
    # it every time, because `required_level([])` is `patch`: a release that
    # publishes nothing new is still a release, which is the right answer for the
    # TEMPLATE and the wrong one for a generated artefact. Applied literally it
    # made `--check` fail immediately after a successful generate, because the
    # second run bumped 1.0.0 to 1.0.1 and then compared against the file holding
    # 1.0.0. Measured, not reasoned: the first `--check` this command ever ran
    # exited 5 on an unmodified client it had just written.
    if before is None:
        version = last_version or "1.0.0"
    elif not changes:
        version = last_version or "1.0.0"
    else:
        version = client_ir.next_version(last_version, compatibility.required_level(list(changes)))

    files = client_typescript.emit(
        ir,
        client_version=version,
        sentinel_host=openapi_normalize.SENTINEL_HOST,
        sentinel_base_path=openapi_normalize.SENTINEL_BASE_PATH,
        required_schemes=openapi_normalize.REQUIRED_SCHEMES,
        typescript_version=versions_value("TYPESCRIPT_VERSION"),
        types_node_version=versions_value("TYPES_NODE_VERSION"),
    )
    files[IR_MANIFEST] = json.dumps(client_ir.to_document(ir), indent=2, sort_keys=True) + "\n"

    if arguments.check:
        return check(out, files)

    out.mkdir(parents=True, exist_ok=True)
    for name in sorted(files):
        (out / name).write_text(files[name], encoding="utf-8")
        print(f"generate: wrote {(out / name).relative_to(REPO_ROOT)}")

    print(
        f"generate: version {version} ({', '.join(changes) if changes else 'no contract change'})"
    )
    print(f"generate:   merged surface  {ir.digests.merged_surface_sha256}")
    print(f"generate:   rest openapi    {ir.digests.rest_openapi_sha256}")
    print(f"generate:   app openapi     {ir.digests.app_openapi_sha256}")
    print(f"generate:   tools           {ir.digests.tools_sha256}")
    print("generate: init() checks the rest digest against the SERVED document, as the caller.")
    return EXIT_OK


def check(out: Path, files: dict[str, str]) -> int:
    """Compare, write nothing, and name the FIRST file that differs.

    The first rather than all of them, because the second difference is almost
    always a consequence of the first and a list of twelve reads as a disaster
    when one contract moved.
    """
    for name in sorted(files):
        path = out / name
        if not path.is_file():
            print(
                f"generate: {path.relative_to(REPO_ROOT)} is missing; the client has not been "
                "generated from this contract. Run the same command without --check",
                file=sys.stderr,
            )
            return EXIT_CONTRACT
        if path.read_text(encoding="utf-8") != files[name]:
            print(
                f"generate: {path.relative_to(REPO_ROOT)} differs from what this contract "
                "generates. Either the contract moved and the client was not regenerated, or "
                "the file was edited by hand. Run the same command without --check",
                file=sys.stderr,
            )
            return EXIT_CONTRACT
    where = out.relative_to(REPO_ROOT)
    print(f"generate: {where} is what this contract generates ({len(files)} files).")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

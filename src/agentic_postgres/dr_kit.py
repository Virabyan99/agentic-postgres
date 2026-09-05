"""The disaster kit: what an operator holds off the host, and that it holds no value.

`REC-KIT-001` (ADR 0189). On the day the host is gone, the operator must be
holding, somewhere else, everything a replacement needs to be BUILT and
ADOPTED: the host manifest, the capability manifest, and per project the
project manifest, `bootstrap-state.json` (the provider ids the replacement
adopts by, ADR 0011), the deployed document (the identity the restore is
verified against, `REC-NODE-002`), and `secrets.txt` -- the NAME, provider
path and origin of every secret the project holds, with no value.

**Every file in a kit is either a document a loader validated or a listing
generated from names.** That is the whole of how the kit carries no value: the
manifests and the state pass `assert_no_sensitive_keys` on the way in, the
deployed document passes its schema, and `secrets.txt` is written from the
contract rather than read from anywhere a value lives. Nothing here opens a
secret generation, a credential file or the provider.

Pure: this module plans an export as a list of entries and verifies a
directory; `bin/dr-kit.py` does the copying. Nothing here reads a clock.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_postgres import bootstrap_state, config, deployed_output, host_config, naming
from agentic_postgres.config import ManifestError
from agentic_postgres.secrets_contract import active_secrets, enabled_facilities

__all__ = [
    "BOOTSTRAP_STATE",
    "CAPABILITIES_MANIFEST",
    "DEPLOYED_DOCUMENT",
    "HOST_MANIFEST",
    "KIT_KIND",
    "KIT_MANIFEST",
    "PROJECT_ARTIFACTS",
    "PROJECT_MANIFEST",
    "SECRETS_LISTING",
    "KitEntry",
    "KitError",
    "kit_manifest",
    "plan_export",
    "secrets_listing",
    "verify_kit",
]

KIT_KIND = "disaster_kit"
KIT_MANIFEST = "kit.json"
HOST_MANIFEST = "host.yaml"
CAPABILITIES_MANIFEST = "capabilities.yaml"
PROJECT_MANIFEST = "project.yaml"
BOOTSTRAP_STATE = "bootstrap-state.json"
DEPLOYED_DOCUMENT = "outputs.json"
SECRETS_LISTING = "secrets.txt"
#: What every project directory in a kit must hold, by name. The runbook names
#: each one and `verify` refuses a kit missing any.
PROJECT_ARTIFACTS = (PROJECT_MANIFEST, BOOTSTRAP_STATE, DEPLOYED_DOCUMENT, SECRETS_LISTING)


class KitError(ManifestError):
    """The kit cannot be exported or does not verify. The message names why."""


@dataclass(frozen=True)
class KitEntry:
    """One artifact: its path inside the kit and its bytes."""

    relative: str
    content: bytes
    #: Where it came from, for the export's own report; None for a generated file.
    source: Path | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def secrets_listing(contract: dict[str, Any], session: int, facilities: frozenset[str]) -> str:
    """`secrets.txt`: one line per secret THIS project holds, and no value.

    The project's view of the contract (ADR 0191), so a mirrored project lists
    the mirror's pair and an unmirrored one does not. Each line is the local
    name, the provider path and key, and who creates the value -- the three
    things the runbook's adoption step needs to know are present at the
    provider before materialization is attempted.
    """
    lines = [
        "# The secrets this project holds at its provider, by name (ADR 0189).",
        "# No value is here and none may be: values live in the project's",
        "# Infisical project, reached by the identity --adopt mints.",
        "# name  provider_path/provider_key  origin  [facility]",
    ]
    for secret in active_secrets(contract, session, facilities=facilities):
        facility = secret.get("facility")
        lines.append(
            f"{secret['name']}  {secret['provider_path']}/{secret['provider_key']}  "
            f"{secret['origin']}" + (f"  facility={facility}" if facility else "")
        )
    return "\n".join(lines) + "\n"


def plan_export(
    *,
    host_path: Path,
    capabilities_path: Path,
    project_paths: tuple[Path, ...],
    state_root: Path,
    contract: dict[str, Any],
    session: int,
) -> list[KitEntry]:
    """Every artifact the kit holds, validated on the way in.

    Each manifest passes its own loader (which refuses a secret-bearing key,
    ADR 0008), each state file passes `validate_state`, each deployed document
    passes its schema; the listing is generated. Two manifests deriving one key
    are refused: a kit holding two projects under one directory is a kit that
    restores the wrong one.
    """
    if not project_paths:
        raise KitError("a kit needs at least one project manifest")
    try:
        host = host_config.load_host_manifest(host_path)
        config.load_capabilities_manifest(capabilities_path)
    except (OSError, ValueError) as problem:
        raise KitError(f"a host-level manifest did not load: {problem}") from None
    del host

    entries = [
        KitEntry(HOST_MANIFEST, host_path.read_bytes(), host_path),
        KitEntry(CAPABILITIES_MANIFEST, capabilities_path.read_bytes(), capabilities_path),
    ]
    seen: set[str] = set()
    for path in project_paths:
        try:
            # `expiry=False`: the kit records what is deployed, and an ephemeral
            # project past its expiry is still a project whose restore may be
            # wanted (D978's reading of the rule).
            manifest = config.load_project_manifest(path, expiry=False)
        except (OSError, ValueError) as problem:
            raise KitError(f"{path} did not load as a project manifest: {problem}") from None
        project = manifest["project"]
        key = naming.project_key(project["slug"], project["environment"])
        if key in seen:
            raise KitError(f"two manifests derive the project key {key!r}")
        seen.add(key)

        state_path = state_root / key / BOOTSTRAP_STATE
        try:
            state = bootstrap_state.load_state(state_path)
        except ManifestError as problem:
            raise KitError(
                f"{key}: {problem}. A project with no recorded bootstrap has no provider "
                "ids to adopt by; the kit cannot describe it."
            ) from None
        if state["project_key"] != key:
            raise KitError(f"{state_path} records project {state['project_key']!r}, not {key!r}")

        deployed_path = deployed_output.deployed_path(key, root=state_root)
        try:
            deployed = json.loads(deployed_path.read_text(encoding="utf-8"))
            deployed_output.validate_deployed_document(deployed)
        except (OSError, ValueError, ManifestError) as problem:
            raise KitError(
                f"{key}: no valid deployed document at {deployed_path}: {problem}. The kit "
                "carries the identity a restore is verified against; a project never "
                "deployed here has none."
            ) from None
        if (deployed.get("project") or {}).get("key") != key:
            raise KitError(f"{deployed_path} describes another project")

        prefix = f"projects/{key}"
        entries += [
            KitEntry(f"{prefix}/{PROJECT_MANIFEST}", path.read_bytes(), path),
            KitEntry(f"{prefix}/{BOOTSTRAP_STATE}", state_path.read_bytes(), state_path),
            KitEntry(f"{prefix}/{DEPLOYED_DOCUMENT}", deployed_path.read_bytes(), deployed_path),
            KitEntry(
                f"{prefix}/{SECRETS_LISTING}",
                secrets_listing(contract, session, enabled_facilities(manifest)).encode("utf-8"),
            ),
        ]
    return entries


def kit_manifest(
    entries: list[KitEntry], *, exported_at: str, release: str | None, session: int
) -> dict[str, Any]:
    """`kit.json`: what the kit holds and each artifact's digest, so `verify`
    can tell a kit that was tampered with or half-copied from a whole one."""
    return {
        "kind": KIT_KIND,
        "exported_at": exported_at,
        "release": release,
        "session": session,
        "projects": sorted(
            {
                entry.relative.split("/")[1]
                for entry in entries
                if entry.relative.startswith("projects/")
            }
        ),
        "artifacts": {entry.relative: entry.sha256 for entry in entries},
    }


def verify_kit(kit_dir: Path) -> list[str]:
    """Every problem with a kit, or an empty list. Raises nothing itself.

    A kit verifies when `kit.json` is present and well-formed, every artifact it
    names is present with the recorded digest, the two host-level manifests
    load, and every project directory holds the four artifacts with the state,
    the document and the manifest all naming that directory's key.
    """
    problems: list[str] = []
    manifest_path = kit_dir / KIT_MANIFEST
    if not manifest_path.is_file():
        return [f"no {KIT_MANIFEST} in {kit_dir}; this is not a kit"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        return [f"{manifest_path} is not readable as JSON: {problem}"]
    if not isinstance(manifest, dict) or manifest.get("kind") != KIT_KIND:
        return [f"{manifest_path} does not describe a {KIT_KIND}"]
    artifacts = manifest.get("artifacts")
    projects = manifest.get("projects")
    if not isinstance(artifacts, dict) or not isinstance(projects, list) or not projects:
        return [f"{manifest_path} names no artifacts or no projects"]

    for relative, digest in sorted(artifacts.items()):
        path = kit_dir / relative
        if not path.is_file():
            problems.append(f"missing artifact: {relative}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"digest mismatch: {relative} is not the file that was exported")

    for name, loader in (
        (HOST_MANIFEST, host_config.load_host_manifest),
        (CAPABILITIES_MANIFEST, config.load_capabilities_manifest),
    ):
        if name not in artifacts:
            problems.append(f"{name} is not in the kit")
        elif (kit_dir / name).is_file():
            try:
                loader(kit_dir / name)
            except (OSError, ValueError) as problem:
                problems.append(f"{name} does not load: {problem}")

    for key in projects:
        prefix = f"projects/{key}"
        for artifact in PROJECT_ARTIFACTS:
            if f"{prefix}/{artifact}" not in artifacts:
                problems.append(f"{key}: {artifact} is not in the kit")
        directory = kit_dir / prefix
        if not directory.is_dir():
            problems.append(f"{key}: no directory in the kit")
            continue
        problems += _verify_project(directory, key)
    return problems


def _verify_project(directory: Path, key: str) -> list[str]:
    problems: list[str] = []
    manifest_path = directory / PROJECT_MANIFEST
    if manifest_path.is_file():
        try:
            manifest = config.load_project_manifest(manifest_path, expiry=False)
            project = manifest["project"]
            derived = naming.project_key(project["slug"], project["environment"])
            if derived != key:
                problems.append(f"{key}: the manifest derives {derived!r}")
        except (OSError, ValueError) as problem:
            problems.append(f"{key}: the manifest does not load: {problem}")
    state_path = directory / BOOTSTRAP_STATE
    if state_path.is_file():
        try:
            state = bootstrap_state.load_state(state_path)
            if state["project_key"] != key:
                problems.append(f"{key}: the state records {state['project_key']!r}")
        except ManifestError as problem:
            problems.append(f"{key}: the bootstrap state does not validate: {problem}")
    document_path = directory / DEPLOYED_DOCUMENT
    if document_path.is_file():
        try:
            document = json.loads(document_path.read_text(encoding="utf-8"))
            deployed_output.validate_deployed_document(document)
            if (document.get("project") or {}).get("key") != key:
                problems.append(f"{key}: the deployed document describes another project")
        except (OSError, ValueError, ManifestError) as problem:
            problems.append(f"{key}: the deployed document does not validate: {problem}")
    listing = directory / SECRETS_LISTING
    if listing.is_file():
        lines = [
            line
            for line in listing.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not lines:
            problems.append(f"{key}: {SECRETS_LISTING} names no secret")
        for line in lines:
            fields = line.split()
            if len(fields) < 3 or "=" in fields[1] or "/" not in fields[1]:
                problems.append(f"{key}: {SECRETS_LISTING} has a line that is not a name listing")
                break
    return problems

"""Provider bootstrap state (Session 2, Phase 4).

`bootstrap-state.json` records which external provider resources a project owns.
It is the *authority* for provider ownership; the deployed `outputs.json` is a
published observation of it and is not authoritative (ADR 0012).

Three rules shape this module, all from ADR 0011:

**Ownership is an ID, never a name.** Destruction and revocation act on the
identifiers recorded here. Adopting a provider resource because its name matches
is how one project deletes another project's Infisical project — provider names
are not unique and are not proof of anything.

**Convergence is keyed by provider-relevant inputs only.**
`provider_inputs_sha256` is computed from the fields that actually determine
provider resources. Hashing the whole manifest would make a domain change or an
`api.max_rows` change look like provider drift, and an operator who sees churn
they cannot explain stops reading the plan.

**A missing credential file is a repair condition, not an idempotent apply.**
If state says a client secret exists and the local file is gone, the provider
still holds a secret nobody can use. Silently creating another one leaks the
first. `--repair-runtime-credential` creates, validates, writes, and only then
revokes the recorded ID.

Nothing in this module reads a credential. It handles identifiers and paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_postgres import config, naming
from agentic_postgres.config import ManifestError

STATE_ROOT = Path("/etc/agentic-postgres/projects")
CREDENTIAL_ROOT = Path("/etc/agentic-postgres/credentials")

#: The manifest fields that determine provider resources, as dotted paths.
#:
#: Deliberately short. Everything absent from this tuple is a field a project can
#: change without any provider resource needing to change -- the domain, route
#: base paths, pool sizes, storage and backup names. Adding a field here means
#: asserting that changing it must cause provider convergence work.
PROVIDER_RELEVANT_FIELDS: tuple[str, ...] = (
    "project.slug",
    "project.environment",
)

#: Host-level provider coordinates that also determine resources. Kept separate
#: because they come from `host.yaml`, not from the project manifest.
PROVIDER_RELEVANT_HOST_FIELDS: tuple[str, ...] = (
    "infisical.api_url",
    "infisical.organization_id",
    "infisical.organization_slug",
    "infisical.environment_slug",
    "infisical.runtime_folder",
)


class BootstrapStateError(ManifestError):
    """State is unreadable, invalid, or disagrees with what was asked of it."""


def state_path(project_key: str) -> Path:
    return STATE_ROOT / project_key / "bootstrap-state.json"


def credential_paths(project_key: str) -> dict[str, str]:
    """The two root-owned credential files for one project.

    Derived from the project key so the path itself carries the project scope.
    A state file naming another project's directory is therefore detectable by
    comparing against this, which :func:`validate_state` does.
    """
    directory = CREDENTIAL_ROOT / project_key
    return {
        "client_id_path": str(directory / "infisical-client-id"),
        "client_secret_path": str(directory / "infisical-client-secret"),
    }


def provider_inputs_digest(project: dict[str, Any], host: dict[str, Any]) -> str:
    """Digest only the inputs that determine provider resources.

    Canonical JSON of an explicit field map, not of the manifests. Two
    consequences, both wanted: the digest is stable against unrelated manifest
    edits, and adding a field to the convergence key is a visible source change
    rather than a side effect of editing a manifest.
    """
    selected: dict[str, Any] = {}
    for dotted in PROVIDER_RELEVANT_FIELDS:
        selected[dotted] = _at(project, dotted, "project manifest")
    for dotted in PROVIDER_RELEVANT_HOST_FIELDS:
        selected[dotted] = _at(host, dotted, "host manifest")

    from hashlib import sha256

    return sha256(naming.canonical_json(selected)).hexdigest()


def load_state(path: Path) -> dict[str, Any]:
    """Read and validate one bootstrap-state file."""
    if not path.is_file():
        raise BootstrapStateError(f"bootstrap state is missing: {path}")
    if path.is_symlink():
        raise BootstrapStateError(f"bootstrap state is a symlink, which is not accepted: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BootstrapStateError(f"{path} is not valid JSON: {exc}") from exc
    validate_state(document)
    return document


def validate_state(document: Any) -> dict[str, Any]:
    """Schema-validate, then check the things the schema cannot express."""
    if not isinstance(document, dict):
        raise BootstrapStateError("bootstrap state must be a JSON object")

    config.validate_against_schema(document, "bootstrap-state.schema.json")
    config.assert_no_sensitive_keys(document)

    project_key = document["project_key"]

    # The credential paths must be *this* project's. A state file that names
    # another project's credential directory would make one project authenticate
    # as another, and it is exactly the collision-refusal case runbook §15 lists.
    expected = credential_paths(project_key)
    if document["credential_files"] != expected:
        raise BootstrapStateError(
            f"bootstrap state for {project_key!r} names credential files outside its own "
            f"directory: {document['credential_files']}. Expected {expected}."
        )

    # A managed resource with no recorded ID cannot be destroyed by ID, and
    # falling back to a name lookup is how one project deletes another's.
    if "runtime_client_secret" in document["managed_resources"]:
        if not document.get("active_client_secret_id"):
            raise BootstrapStateError(
                f"{project_key!r} claims to manage a runtime client secret but records no "
                "active_client_secret_id; revocation would have to guess"
            )

    if document["created_at"] > document["updated_at"]:
        raise BootstrapStateError(
            f"{project_key!r} was updated before it was created; the state file is not "
            "a record of what happened"
        )

    return document


def is_converged(document: dict[str, Any], expected_digest: str) -> bool:
    """True when no provider work is needed.

    The whole value of `--plan` is that a second run reports nothing. That is
    only true if convergence is decided by comparing a digest, rather than by
    listing provider resources and hoping the comparison is complete.
    """
    return document["provider_inputs_sha256"] == expected_digest


def needs_credential_repair(document: dict[str, Any]) -> list[str]:
    """Credential files that state claims exist but that are absent on disk.

    A non-empty result is a **repair** condition, never an ordinary apply. The
    provider still holds a credential; creating a second one without revoking
    the first leaks it, and revoking the first before the second is validated
    leaves the project with none.
    """
    return [name for name, raw in document["credential_files"].items() if not Path(raw).is_file()]


def _at(document: dict[str, Any], dotted: str, what: str) -> Any:
    value: Any = document
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise BootstrapStateError(f"{what} has no field {dotted!r}")
        value = value[part]
    return value


__all__ = [
    "CREDENTIAL_ROOT",
    "PROVIDER_RELEVANT_FIELDS",
    "PROVIDER_RELEVANT_HOST_FIELDS",
    "STATE_ROOT",
    "BootstrapStateError",
    "credential_paths",
    "is_converged",
    "load_state",
    "needs_credential_repair",
    "provider_inputs_digest",
    "state_path",
    "validate_state",
]

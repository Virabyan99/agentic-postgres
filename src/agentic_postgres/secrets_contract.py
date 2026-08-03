"""Secret requirements contract (Session 2, Phase 2).

`secrets.required.yaml` declares *which* secrets exist, *which* service consumes
each one, and *under what numeric ownership* it is materialized. It never
declares a value, and this module never reads one — every function here operates
on identifiers.

The design commitment recorded in `docs/decisions/0010-secret-materialization.md`
is that a secret is an **individual file granted to one service**, not an entry
in an environment bundle. Two consequences shape this module:

* a provider secret consumed by two services is materialized as two separate
  files, one per consumer directory, so there is no shared path whose
  permissions have to satisfy two different runtime users;
* the *source path* is derived from the project key by the materializer and can
  never be supplied from a manifest, because a manifest that could name its own
  secret directory could name another project's.

The session filter matters more than it looks. `active_secrets(contract, 2)`
returns only secrets introduced by session 2 or earlier, so a Session 3 database
credential declared here does not become a Session 2 Compose mount — which is
what lets later sessions append to this file without changing Session 2's
tested grant surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_postgres import config
from agentic_postgres.config import ManifestError

#: Where a materialized generation lives. `{project_key}` and `{generation_id}`
#: are substituted by the materializer; nothing in a manifest reaches this.
#: S105 is a false positive twice over here: these are directory paths, and the
#: whole point of this module is that it handles *names* and never a value.
SECRET_ROOT = "/var/lib/agentic-postgres/secrets"  # noqa: S105

#: Where Compose exposes a granted file inside a container.
CONTAINER_SECRET_DIR = "/run/secrets"  # noqa: S105


def load_secret_contract(path: Path) -> dict[str, Any]:
    """Parse, schema-validate and semantically validate the requirements file."""
    document = config.load_manifest(path)
    config.assert_no_sensitive_keys(document)
    config.validate_against_schema(document, "secret-contract.schema.json")
    _validate_semantics(document)
    return document


def active_secrets(contract: dict[str, Any], session: int) -> list[dict[str, Any]]:
    """Secrets introduced by ``session`` or earlier, in declaration order."""
    return [s for s in contract["secrets"] if s["introduced_in_session"] <= session]


def consumers_of(contract: dict[str, Any], service: str, session: int) -> list[dict[str, Any]]:
    """Every ``(secret, consumer)`` grant this service holds through ``session``.

    This is the function that answers "what does this container get", and it is
    the one the Compose renderer and the isolation tests both use, so that the
    rendered model and the assertion about the rendered model cannot be derived
    from two different readings of the file.
    """
    grants: list[dict[str, Any]] = []
    for secret in active_secrets(contract, session):
        for consumer in secret["consumers"]:
            if consumer["service"] == service:
                grants.append({"secret": secret, "consumer": consumer})
    return grants


def granted_services(contract: dict[str, Any], session: int) -> set[str]:
    return {
        consumer["service"]
        for secret in active_secrets(contract, session)
        for consumer in secret["consumers"]
    }


def generation_directory(project_key: str, generation_id: str) -> str:
    """Absolute path of one immutable generation. Derived, never supplied."""
    return f"{SECRET_ROOT}/{project_key}/generations/{generation_id}"


def secret_source_path(project_key: str, generation_id: str, consumer: dict[str, Any]) -> str:
    """Absolute host path of one materialized secret file.

    Per-consumer, not per-secret: the service name is a path component. That is
    what makes "service A cannot read service B's copy" a filesystem property
    rather than a convention.
    """
    root = generation_directory(project_key, generation_id)
    return f"{root}/{consumer['service']}/{consumer['target_file']}"


def container_secret_path(consumer: dict[str, Any]) -> str:
    return f"{CONTAINER_SECRET_DIR}/{consumer['target_file']}"


# ---------------------------------------------------------------------------
# Semantic validation — what JSON Schema cannot say
# ---------------------------------------------------------------------------


def _validate_semantics(document: dict[str, Any]) -> None:
    secrets = document["secrets"]

    _reject_duplicates(
        [s["name"] for s in secrets],
        "secret name",
        "two declarations of one name make the grant surface ambiguous",
    )
    _reject_duplicates(
        [s["provider_key"] for s in secrets],
        "provider_key",
        "two local names for one provider key would fetch the same value twice "
        "and make rotation ambiguous",
    )

    for secret in secrets:
        _validate_consumers(secret)


def _validate_consumers(secret: dict[str, Any]) -> None:
    name = secret["name"]
    consumers = secret["consumers"]

    # Uniqueness is per (service, target_file), not per target_file: two
    # services legitimately receive the same basename, because each gets its
    # own directory and each sees it at the same /run/secrets path.
    pairs = [(c["service"], c["target_file"]) for c in consumers]
    _reject_duplicates(
        pairs,
        f"consumer of secret {name!r}",
        "one service cannot receive two files with the same name",
    )

    for consumer in consumers:
        target = consumer["target_file"]
        # The schema pattern already excludes '/' and a leading dot, so this is
        # belt and braces -- but path escape is the failure this contract exists
        # to prevent, and a defence that lives only in a regex is one edit from
        # being gone.
        if "/" in target or ".." in target or Path(target).name != target:
            raise ManifestError(
                f"secret {name!r} consumer {consumer['service']!r} declares target_file "
                f"{target!r}, which is not a simple basename; a target filename must not "
                "be able to leave its generation directory"
            )
        if consumer["uid"] == 0 or consumer["gid"] == 0:
            raise ManifestError(
                f"secret {name!r} consumer {consumer['service']!r} declares root ownership; "
                "a root-owned secret file is unreadable by a container that drops privileges"
            )


def _reject_duplicates(values: list[Any], what: str, why: str) -> None:
    seen: set[Any] = set()
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise ManifestError(f"duplicate {what}: {duplicates}; {why}")


__all__ = [
    "CONTAINER_SECRET_DIR",
    "SECRET_ROOT",
    "active_secrets",
    "consumers_of",
    "container_secret_path",
    "generation_directory",
    "granted_services",
    "load_secret_contract",
    "secret_source_path",
]

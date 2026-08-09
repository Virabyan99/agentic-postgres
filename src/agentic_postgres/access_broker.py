"""Resolving one access profile of one project to an endpoint and a password.

This is the release-owned half of ADR 0043. The installed trampoline finds the
release; ``bin/database-access.py`` checks root and the caller's identity; and
everything between "which project and profile" and "here is the answer" is here,
where it can be run against a directory tree in ``tmp_path`` by a test with no
privilege, no host and no cluster.

**Authorization is decided before any project state is read.** Not as an
optimisation — as the whole of ADR 0043's point 5. A refusal that happened after
the deployed document was opened would answer a question the caller was not
entitled to ask, by the shape of its failure: *no such project* and *not yours*
would become distinguishable, and the second is the interesting one to an
attacker. Here, a caller with no grant gets the same refusal whether the project
is deployed, released, or has never existed.

**The password comes from the active pointer, not from the deployed document.**
Both name a generation. The deployed document names the one that was current
when the project last deployed; ``active-secret-generation.json`` names the one
the running containers are actually mounting. After a rotation those differ, and
returning the document's would hand out a credential that no longer
authenticates — a failure that looks like the developer's mistake. The document's
value is reported alongside as context, never used to open a file.

**Two things that agree are checked against each other.** Which secret backs a
profile is enumerated in :data:`~agentic_postgres.access_policy.PROFILE_SECRETS`;
the deployed document also records a ``password_secret_ref`` per profile. They
are produced by different code at different times, so the broker compares them
and refuses on disagreement rather than picking one. A profile whose recorded
reference has drifted from the release's mapping is a project whose credential
the release can no longer safely identify.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from agentic_postgres import access_policy, port_allocations
from agentic_postgres.config import ManifestError

#: Host configuration and per-project state (ADR 0020).
ETC_ROOT = Path("/etc/agentic-postgres")

#: Secret generations. Separate root, because these are data rather than
#: configuration and are excluded from configuration backups.
SECRET_ROOT = Path("/var/lib/agentic-postgres/secrets")

__all__ = [
    "ETC_ROOT",
    "SECRET_ROOT",
    "BrokerError",
    "authorize",
    "endpoint",
    "load_policy",
    "password",
    "resolve_allocation",
]


class BrokerError(RuntimeError):
    """A refusal, carrying the exit code the command surface reports.

    Codes follow the convention D42 froze and D87 mapped Session 4 onto: ``2``
    invalid input, ``3`` missing prerequisite, ``4`` missing runtime state,
    ``5`` a contract failure, ``6`` refused, ``8`` a secret could not be read.
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _read_json(path: Path, *, code: int) -> Any:
    """Read a root-owned state file, refusing a symlink at the last component.

    The directories above are root-owned, so this is not the main defence; it is
    the cheap one that turns an operator's stray ``ln -s`` into a refusal instead
    of a file read from somewhere nobody looked. Runbook §7 asks for it on every
    state path and the launchers already do it.
    """
    if os.path.islink(path):
        raise BrokerError(2, f"{path} is a symlink, which is not accepted")
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise BrokerError(code, f"{path} does not exist") from None
    except OSError as error:
        raise BrokerError(code, f"{path} could not be read: {error.strerror}") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise BrokerError(5, f"{path} is not valid JSON: {error}") from None


# ---------------------------------------------------------------------------
# Authorization — first, and from the policy alone
# ---------------------------------------------------------------------------


def load_policy(*, etc_root: Path = ETC_ROOT) -> dict[str, Any]:
    """Load and validate the host's access policy.

    An absent file is exit ``3``, not an empty policy. A host that has never had
    a policy published and a host whose policy was deleted are both "no access",
    but only one of them is a state an operator meant to be in, and a broker that
    silently treated a missing file as "deny everything" would make the
    difference invisible until someone asked why access stopped working.
    """
    path = etc_root / "database-access-policy.json"
    document = _read_json(path, code=3)
    try:
        return access_policy.validate(document)
    except access_policy.PolicyError as error:
        raise BrokerError(5, f"{path} is not a usable access policy: {error}") from None


def authorize(
    *,
    unix_user: str,
    project_key: str,
    profile: str,
    etc_root: Path = ETC_ROOT,
) -> None:
    """Refuse, or return, having read nothing about the project.

    The refusal message names neither the project nor the profile. It is not
    coyness: the caller already knows what they asked for, and the only reader
    who learns anything from a specific message is one probing for which
    projects exist.
    """
    if profile not in access_policy.PROFILE_SECRETS:
        raise BrokerError(2, f"not an access profile: {profile!r}")

    policy = load_policy(etc_root=etc_root)
    if not access_policy.permits(
        policy, unix_user=unix_user, project_key=project_key, profile=profile
    ):
        raise BrokerError(6, "refused.")


# ---------------------------------------------------------------------------
# Project state
# ---------------------------------------------------------------------------


def _deployed_document(project_key: str, *, etc_root: Path) -> dict[str, Any]:
    path = etc_root / "projects" / project_key / "outputs.json"
    document = _read_json(path, code=4)
    if not isinstance(document, dict):
        raise BrokerError(5, f"{path} is not a JSON object")
    if document.get("document_kind") != "deployed":
        raise BrokerError(
            5,
            f"{path} is a {document.get('document_kind')!r} document. A rendered "
            "document describes what would be deployed, and its endpoints are the "
            "ones a render can know, which is none of them",
        )
    return document


def _loopback_address(*, etc_root: Path) -> str:
    """The address every publication binds, from the host manifest (ADR 0040).

    Read here rather than taken from the deployed document, because it is a
    property of the host and the document is a property of one project. A
    project deployed before the operator narrowed the address would otherwise
    keep handing out the old one.
    """
    path = etc_root / "host.yaml"
    if os.path.islink(path):
        raise BrokerError(2, f"{path} is a symlink, which is not accepted")
    try:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BrokerError(3, f"{path} does not exist") from None
    except yaml.YAMLError as error:
        raise BrokerError(5, f"{path} is not valid YAML: {error}") from None

    try:
        address = manifest["database_access"]["loopback_address"]
    except (TypeError, KeyError):
        raise BrokerError(
            5,
            f"{path} declares no database_access.loopback_address. A host manifest "
            "at schema_version 1 predates the section that says where database "
            "transports may be published",
        ) from None
    if not isinstance(address, str) or not address:
        raise BrokerError(5, f"{path} declares a non-string loopback address")
    return address


def resolve_allocation(registry: dict[str, Any], project_key: str) -> dict[str, Any]:
    """The live allocation for this project key, or a refusal.

    **This is the one place the port registry is searched by project key**, and
    the registry says in its own module docstring that the key is never the match
    key: the authoritative identity is the volume's ``instance_uuid``, because two
    projects can share a key across a rebuild and one project can change it.

    The deployed document records no instance UUID, so the broker has nothing else
    to search by. What it does instead of guessing is refuse ambiguity: released
    records are excluded, and two *live* allocations carrying one key is an error
    rather than a first match. That turns the missing identifier into a visible
    failure on the day it would matter, instead of a credential handed out for the
    wrong cluster. Recorded as a plan divergence; the fix is a document that
    carries the UUID, which is a schema version.
    """
    matches = [
        allocation
        for allocation in port_allocations.live_allocations(registry)
        if allocation["project_key"] == project_key
    ]
    if not matches:
        raise BrokerError(
            4,
            f"no live port allocation for {project_key}. Its transports have not "
            "been published, or the allocation was released",
        )
    if len(matches) > 1:
        raise BrokerError(
            5,
            f"{len(matches)} live allocations record the project key {project_key}, on "
            f"ports {sorted(p for m in matches for p in (m['pooled_port'], m['direct_port']))}. "
            "The registry is keyed by the volume's instance UUID and only records the "
            "key for humans; two live records for one key means the broker cannot tell "
            "which cluster a credential would reach",
        )
    return matches[0]


def _allocation(project_key: str, *, etc_root: Path) -> dict[str, Any]:
    path = etc_root / "database-port-allocations.json"
    registry = _read_json(path, code=4)
    try:
        port_allocations.validate(registry)
    except (port_allocations.AllocationError, ManifestError) as error:
        raise BrokerError(5, f"{path} is not a usable port registry: {error}") from None
    return resolve_allocation(registry, project_key)


# ---------------------------------------------------------------------------
# The two operations
# ---------------------------------------------------------------------------


def _profile_block(document: dict[str, Any], profile: str) -> dict[str, Any]:
    try:
        block = document["database"]["access_profiles"][profile]
    except (TypeError, KeyError):
        raise BrokerError(
            5,
            f"the deployed document carries no access_profiles.{profile}. It was "
            "written by a release that predates ADR 0041; redeploy this project",
        ) from None

    if block.get("status") != "available":
        raise BrokerError(
            4,
            f"{profile} is {block.get('status')!r} for this project. It becomes "
            f"available from session {block.get('available_from_session')}",
        )

    expected_secret, _ = access_policy.secret_for(profile)
    recorded = block.get("password_secret_ref")
    if recorded != expected_secret:
        raise BrokerError(
            5,
            f"the deployed document says {profile} is backed by {recorded!r} and this "
            f"release says {expected_secret!r}. One of the two describes a system that "
            "no longer exists, and the broker will not choose between them",
        )
    return block


def endpoint(
    project_key: str,
    profile: str,
    *,
    etc_root: Path = ETC_ROOT,
) -> dict[str, Any]:
    """Where to connect and as whom. Contains no secret and never will.

    Callers on a developer's machine build a connection string from this and
    obtain the password separately, so that the two operations can be logged,
    audited and refused independently — and so the common case, printing an
    environment, involves no credential at all.
    """
    document = _deployed_document(project_key, etc_root=etc_root)
    block = _profile_block(document, profile)
    allocation = _allocation(project_key, etc_root=etc_root)

    transport = access_policy.transport_for(profile)
    port = allocation["pooled_port"] if transport == "pooled" else allocation["direct_port"]

    return {
        "project_key": project_key,
        "profile": profile,
        "transport": transport,
        "host": _loopback_address(etc_root=etc_root),
        "port": port,
        "role": block["role"],
        "database": document["database"]["name"],
        "allocation_state": allocation["state"],
        "deployed_through_session": document["deployed_through_session"],
    }


def active_generation(project_key: str, *, secret_root: Path = SECRET_ROOT) -> str:
    """Which generation the running containers are mounting, from the pointer."""
    path = secret_root / project_key / "active-secret-generation.json"
    pointer = _read_json(path, code=4)
    generation = pointer.get("generation_id") if isinstance(pointer, dict) else None
    if not isinstance(generation, str) or not generation:
        raise BrokerError(5, f"{path} names no generation_id")
    if not generation.isalnum() or not generation.islower():
        raise BrokerError(
            2,
            f"{path} names a generation that is not a lowercase alphanumeric token: "
            f"{generation!r}. It is about to be a path component",
        )
    return generation


def password(
    project_key: str,
    profile: str,
    *,
    etc_root: Path = ETC_ROOT,
    secret_root: Path = SECRET_ROOT,
) -> str:
    """The profile's password, read from the active generation.

    Returned as a value rather than written anywhere. The caller prints it to a
    pipe; nothing here logs it, formats it into a message, or puts it in an
    exception — including the exceptions raised on the paths below, which name
    the file and never its contents.
    """
    document = _deployed_document(project_key, etc_root=etc_root)
    _profile_block(document, profile)

    secret_name, consumer = access_policy.secret_for(profile)
    generation = active_generation(project_key, secret_root=secret_root)
    path = secret_root / project_key / "generations" / generation / consumer / secret_name

    if os.path.islink(path):
        raise BrokerError(2, f"{path} is a symlink, which is not accepted")
    try:
        value = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise BrokerError(
            8,
            f"{secret_name} is not materialized in generation {generation} for "
            f"{project_key}. Run materialize-secrets for this project",
        ) from None
    except OSError as error:
        raise BrokerError(8, f"{path} could not be read: {error.strerror}") from None

    value = value.rstrip("\n")
    if not value:
        raise BrokerError(8, f"{path} is empty")
    return value

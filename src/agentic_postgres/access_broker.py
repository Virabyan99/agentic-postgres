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
import subprocess
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
    "recorded_instance_uuid",
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


def resolve_allocation(
    registry: dict[str, Any], project_key: str, *, instance_uuid: str | None = None
) -> dict[str, Any]:
    """The live allocation for this project, matched on the identity that is one.

    The registry is keyed by the volume's ``instance_uuid`` and says in its own
    module docstring that the project key is recorded for humans and is never the
    match key: two projects can share a key across a rebuild, and one project can
    change it. Until outputs version 5 the deployed document carried no copy of
    the UUID, so this function had nothing else to search by (D106). It searched
    by key and refused ambiguity rather than resolving it, which turned the
    missing identifier into a visible failure instead of a credential handed out
    for the wrong cluster.

    **With a UUID it stops searching by key altogether.** The key is then checked
    rather than used: an allocation whose recorded key disagrees with the project
    being asked about is a refusal, because two documents describing one cluster
    have to agree about what it is called before either can be trusted about
    where it is.

    Without one -- a document written by a release that predates version 5, or a
    project whose cluster has never been read -- the old behaviour is exactly
    preserved. It is not a fallback that guesses; it is the same refusal it
    always was.
    """
    if instance_uuid is not None:
        allocation = port_allocations.find(registry, instance_uuid)
        if allocation is None or allocation not in port_allocations.live_allocations(registry):
            raise BrokerError(
                4,
                f"no live port allocation for instance {instance_uuid}. Its transports "
                "have not been published, or the allocation was released",
            )
        if allocation["project_key"] != project_key:
            raise BrokerError(
                5,
                f"the allocation for instance {instance_uuid} records the project key "
                f"{allocation['project_key']!r}, and the deployed document being read is "
                f"{project_key!r}. One of the two describes a cluster that has been "
                "rebuilt or renamed, and the broker will not choose between them",
            )
        return allocation

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
            "which cluster a credential would reach. This document predates outputs "
            "version 5 and carries no instance UUID; redeploy the project",
        )
    return matches[0]


def _allocation(
    project_key: str, *, etc_root: Path, instance_uuid: str | None = None
) -> dict[str, Any]:
    path = etc_root / "database-port-allocations.json"
    registry = _read_json(path, code=4)
    try:
        port_allocations.validate(registry)
    except (port_allocations.AllocationError, ManifestError) as error:
        raise BrokerError(5, f"{path} is not a usable port registry: {error}") from None
    return resolve_allocation(registry, project_key, instance_uuid=instance_uuid)


def recorded_instance_uuid(document: dict[str, Any]) -> str | None:
    """The cluster identity this deployed document observed, or ``None``.

    ``None`` covers three different situations that are one situation here: a
    document written before outputs version 5, a deployment that interrogated no
    cluster, and a cluster whose identity could not be read. All three mean the
    broker has no identity to match on, and the honest response to all three is
    the same one -- fall back to the refusal that predates the field, rather than
    to a guess.
    """
    observed = document.get("database", {}).get("observed", {})
    uuid = observed.get("instance_uuid") if isinstance(observed, dict) else None
    return uuid if isinstance(uuid, str) and uuid else None


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


#: The port each transport listens on *inside* its container. Not the port a
#: developer binds — that is the allocation, and the two are different numbers
#: on purpose, because ADR 0042 allocates the near end from a host-wide range.
CONTAINER_PORTS = {"pooled": 6432, "direct": 5432}


def container_address(container: str, network: str) -> str:
    """The container's current address on one network, read from Docker.

    **Resolved per call and never written down** (ADR 0044). A container address
    changes when the container is recreated, so a recorded one is right until the
    next restart — this project's most frequent defect wearing a different hat.
    The broker is privileged and on the host, so asking Docker at the moment it
    answers costs one exec and removes the staleness entirely.
    """
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "docker",
            "inspect",
            "-f",
            f'{{{{ (index .NetworkSettings.Networks "{network}").IPAddress }}}}',
            container,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    address = result.stdout.strip()
    if result.returncode != 0 or not address or address == "<no value>":
        raise BrokerError(
            4,
            f"could not read {container}'s address on {network}: "
            f"{result.stderr.strip() or 'no address'}. The transports are reached "
            "through an SSH forward to the container, so there is nothing to "
            "forward to until it is running",
        )
    return address


def endpoint(
    project_key: str,
    profile: str,
    *,
    etc_root: Path = ETC_ROOT,
    resolve_address: Any = container_address,
) -> dict[str, Any]:
    """Where to connect and as whom. Contains no secret and never will.

    Two endpoints, and keeping them apart is the whole of ADR 0044.

    **``host`` and ``port`` are the tunnel target** — the container's current
    address on the project's own network, which ``bin/connect.sh`` forwards to
    and nothing records. **``local_port`` is the allocated port** the developer
    binds at the near end, which is stable across redeploy, restart and reboot
    because it is keyed by the identity the volume carries. So a saved command
    keeps working even though the address it forwards to does not.

    Nothing is published. The host reaches the container because it is the
    gateway of that bridge; the outside world reaches neither.

    ``resolve_address`` is a parameter so a test can supply one. Everything else
    here reads files under a root it was given, and one function that could only
    run where Docker does would have taken the whole module's tests onto a host
    with it.
    """
    document = _deployed_document(project_key, etc_root=etc_root)
    block = _profile_block(document, profile)
    allocation = _allocation(
        project_key,
        etc_root=etc_root,
        instance_uuid=recorded_instance_uuid(document),
    )

    transport = access_policy.transport_for(profile)
    local_port = allocation["pooled_port"] if transport == "pooled" else allocation["direct_port"]

    # The pooled transport is the pooler's container, the direct one the
    # cluster's. Derived from the recorded container name rather than rebuilt
    # from the project key: the deployed document is what says which containers
    # this project actually has.
    container = document["database"]["container"]
    if transport == "pooled":
        container = container.replace("-postgres-1", "-pgbouncer-1")

    return {
        "project_key": project_key,
        "profile": profile,
        "transport": transport,
        "host": resolve_address(container, document["edge"]["project_internal_network"]),
        "port": CONTAINER_PORTS[transport],
        "local_port": local_port,
        "local_address": _loopback_address(etc_root=etc_root),
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

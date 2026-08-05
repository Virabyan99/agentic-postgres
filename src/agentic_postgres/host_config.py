"""Host manifest loading and semantic validation (Session 2, Phase 1).

`host.yaml` is the authority for non-secret *host* configuration, and is
deliberately separate from `project.yaml`. Two reasons, both recorded in
`docs/decisions/0009-host-and-edge-plane.md`: a host is shared by projects, and
folding host facts into a project manifest would make the deterministic render
of `.generated/{project_key}/` depend on which machine ran it — which would
destroy the byte-identical rendering contract Session 1 established.

Nothing here reads a secret. The provider *coordinates* live in this file; the
provider *credentials* live in root-owned files outside the repository.

Three layers, the same shape as `config.py`:

1. strict parse (reused from :mod:`agentic_postgres.config` — duplicate keys,
   merge keys, multiple documents and non-string keys are all refused);
2. JSON Schema, with format checking enabled;
3. the semantic checks below, which are the ones JSON Schema cannot express.

The checks that require the *live host* — is the address actually assigned, does
the operator user exist, is the port already open in the provider firewall — are
deliberately not here. They belong to ``bin/provision-host.sh --check``, which
runs on the host with root. This module must stay importable and runnable
offline, because the contract suite runs in CI where there is no host.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

from agentic_postgres import config
from agentic_postgres.config import ManifestError

#: The implementation's fixed supported-host allowlist. This is a *mirror* for
#: error messages and for ``provision-host.sh``; the authority is the
#: ``osRelease`` enum in ``schemas/host.schema.json``, per ADR 0007's rule that
#: the schema owns anything the schema can express. ``test_host_manifest.py``
#: asserts the two agree, so the mirror cannot drift silently.
SUPPORTED_OS_RELEASES: tuple[str, ...] = ("26.04", "24.04")

#: Canonical release. Anything else in the allowlist is a documented fallback
#: and is recorded as a deviation in Session 2 evidence.
CANONICAL_OS_RELEASE = "26.04"

#: A default route is not a source restriction. It is permitted — an operator
#: with no static address has no alternative — but it is reported on every run
#: so the deviation stays visible rather than becoming invisible background.
_DEFAULT_ROUTES = frozenset({"0.0.0.0/0", "::/0"})

#: Ranges that cannot appear on the public Internet: RFC 1918, RFC 6598 CGNAT,
#: link-local, and the IPv6 unique-local and link-local blocks.
#:
#: Enumerated rather than using ``ip_address(...).is_private``, which also
#: covers the RFC 5737 and RFC 3849 *documentation* ranges. `host.example.yaml`
#: is required to use documentation addresses, so ``is_private`` would reject
#: the repository's own committed example -- and it did, which is how this list
#: came to exist.
_SITE_LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "169.254.0.0/16",
        "fc00::/7",
        "fe80::/10",
    )
)


def load_host_manifest(path: Path) -> dict[str, Any]:
    """Parse, schema-validate and semantically validate one ``host.yaml``."""
    document = config.load_manifest(path)
    config.assert_no_sensitive_keys(document)
    config.validate_against_schema(document, "host.schema.json")
    _validate_semantics(document)
    return document


def unrestricted_ssh_sources(document: dict[str, Any]) -> list[str]:
    """Return any configured SSH source CIDR that is a default route.

    Not an error. ``bin/provision-host.sh`` reports the result so that
    ``0.0.0.0/0`` stays a written, visible choice; the controls that actually
    carry the SSH boundary are key-only authentication, ``PermitRootLogin no``
    and ``MaxAuthTries``, all of which the live-host suite asserts against
    ``sshd -T``.
    """
    return [c for c in document["ssh"]["allowed_source_cidrs"] if c in _DEFAULT_ROUTES]


#: Where the edge plane's rendered configuration and ACME state live. Root-owned
#: and outside the repository: `traefik.yaml` names the ACME environment, and
#: that selection must not be editable by anyone who can write to a checkout.
EDGE_STATE_DIR = "/var/lib/agentic-postgres/edge"

#: The Compose project name of the shared edge stack. Fixed rather than derived:
#: there is exactly one per host, and a derived name would imply otherwise.
EDGE_STACK_NAME = "apg-edge"

#: The exact key set of the edge `compose.env`. Disjoint from `versions.env` and
#: from every project `compose.env`, so no --env-file ordering can let one
#: silently override another.
EDGE_COMPOSE_ENV_KEYS: tuple[str, ...] = (
    "EDGE_STACK_NAME",
    "CONTROL_NETWORK_NAME",
    "EGRESS_NETWORK_NAME",
    "EDGE_STATE_DIR",
)


def edge_compose_env(document: dict[str, Any]) -> bytes:
    """Render the edge stack's `compose.env` from a validated host manifest.

    Derived rather than stored so that `--edge config` works offline and in CI,
    where the root-owned `/var/lib/agentic-postgres/edge/compose.env` does not
    exist. `bin/edge.sh` writes the same content to that path for the systemd
    unit, which cannot read a manifest from an operator's checkout.
    """
    values = {
        "EDGE_STACK_NAME": EDGE_STACK_NAME,
        "CONTROL_NETWORK_NAME": document["edge"]["control_network"],
        "EGRESS_NETWORK_NAME": document["edge"]["egress_network"],
        "EDGE_STATE_DIR": EDGE_STATE_DIR,
    }
    lines = [
        "# Generated from host.yaml. Do not edit; do not shell-source.",
        "# Consumed only by bin/compose.sh --edge via --env-file.",
        *(f"{key}={values[key]}" for key in EDGE_COMPOSE_ENV_KEYS),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


#: The exact key set of a project's *runtime* `compose.env` -- the root-owned
#: third `--env-file` that only `--runtime` mode passes.
#:
#: These are the host-derived values ADR 0013 keeps out of rendered output.
#: `host.yaml` is not one of the digested inputs, so a rendered file carrying
#: the ACME resolver name would depend on which machine produced it while
#: claiming to be a pure function of the manifests. Disjoint from the project
#: key set and from `versions.env`, so no `--env-file` ordering can shadow
#: anything.
RUNTIME_COMPOSE_ENV_KEYS: tuple[str, ...] = (
    "ACME_RESOLVER_NAME",
    "BASELINE_MIDDLEWARE_CHAIN",
)

#: The middleware every project route passes through, in order. Fixed here
#: rather than per project: a project that could choose its own chain could
#: choose to skip the security headers, and the chain is a platform guarantee
#: rather than a project preference.
BASELINE_MIDDLEWARE_CHAIN = "apg-security-headers@file,apg-rate-limit@file"


def runtime_compose_env(document: dict[str, Any]) -> bytes:
    """Render a project's root-owned runtime `compose.env` from the host manifest.

    Root-owned, and outside the project's generated directory on purpose. An
    operator who can write a project's rendered output must not thereby be able
    to change which ACME resolver issues its certificate, or drop the middleware
    chain from its routes.
    """
    values = {
        "ACME_RESOLVER_NAME": document["edge"]["acme_resolver_name"],
        "BASELINE_MIDDLEWARE_CHAIN": BASELINE_MIDDLEWARE_CHAIN,
    }
    lines = [
        "# Generated from host.yaml by ./deploy.sh. Do not edit; do not shell-source.",
        "# Passed as a third --env-file by bin/compose.sh --runtime only.",
        *(f"{key}={values[key]}" for key in RUNTIME_COMPOSE_ENV_KEYS),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _validate_semantics(document: dict[str, Any]) -> None:
    host = document["host"]
    ssh = document["ssh"]
    edge = document["edge"]

    _validate_os_releases(host["supported_os_releases"])
    _validate_addresses(host)
    _validate_cidrs(ssh["allowed_source_cidrs"])
    _validate_networks(edge)


def _validate_os_releases(declared: list[str]) -> None:
    """The manifest may narrow the fixed allowlist. It may never widen it.

    The schema enum already enforces this. The check is repeated here because
    the message the schema produces names a JSON pointer, and an operator who
    typed ``22.04`` needs to be told that the allowlist is a property of the
    implementation rather than of their file.
    """
    unsupported = [release for release in declared if release not in SUPPORTED_OS_RELEASES]
    if unsupported:
        raise ManifestError(
            f"host.supported_os_releases contains unsupported releases {unsupported}; "
            f"the implementation supports exactly {list(SUPPORTED_OS_RELEASES)}. "
            "A manifest can narrow this list but cannot extend it."
        )


def _validate_addresses(host: dict[str, Any]) -> None:
    """Reject addresses that are syntactically fine but cannot be a public host.

    JSON Schema's ``format: ipv4`` proves the string parses. It does not
    prove the address could ever appear on the public Internet, and a loopback
    or unspecified address here would produce a host that passes every offline
    check and is unreachable.
    """
    for field in ("expected_public_ipv4", "expected_public_ipv6"):
        raw = host[field]
        if raw is None:
            continue
        address = ipaddress.ip_address(raw)
        if address.is_loopback or address.is_unspecified or address.is_multicast:
            raise ManifestError(f"host.{field} is {raw}, which cannot be a public host address")

    if host["expected_public_ipv4"] is None and host["expected_public_ipv6"] is None:
        raise ManifestError(
            "at least one of host.expected_public_ipv4 or host.expected_public_ipv6 "
            "must be set; a host with neither has no address for DNS to point at"
        )

    # A site-local address is legitimate in `nat` mode and a configuration error
    # in `direct` mode, so the mode decides whether this is a failure.
    #
    # The membership test is explicit rather than `ip_address(...).is_private`.
    # Python counts the RFC 5737 / RFC 3849 documentation ranges as private, and
    # `host.example.yaml` is required to use exactly those -- so `is_private`
    # rejects the committed example. Naming the site-local ranges says what is
    # actually meant and leaves documentation addresses valid.
    if host["address_mode"] == "direct":
        for field in ("expected_public_ipv4", "expected_public_ipv6"):
            raw = host[field]
            if raw is None:
                continue
            address = ipaddress.ip_address(raw)
            if any(address in network for network in _SITE_LOCAL_NETWORKS):
                raise ManifestError(
                    f"host.{field} is the site-local address {raw} but address_mode is "
                    "'direct'. Use address_mode: nat when a provider forwards a public "
                    "address to a privately addressed host."
                )


def _validate_cidrs(declared: list[str]) -> None:
    """Parse every CIDR properly, and refuse a host-bits-set network.

    ``198.51.100.24/24`` is a common and dangerous typo: the operator means one
    host and has written a 256-address range. ``ip_network(strict=True)`` is
    what catches it, which is why the schema's pattern is deliberately only a
    shape check.
    """
    for raw in declared:
        try:
            ipaddress.ip_network(raw, strict=True)
        except ValueError as exc:
            raise ManifestError(
                f"ssh.allowed_source_cidrs entry {raw!r} is not a valid CIDR: {exc}. "
                "A single address must be written /32 (IPv4) or /128 (IPv6)."
            ) from exc


def _validate_networks(edge: dict[str, Any]) -> None:
    """The two host-scoped networks must be distinct.

    If control and egress were the same network, every project service reachable
    on the egress network would also be able to address the Docker socket proxy,
    which is the one component whose whole purpose is a restricted blast radius.

    The rule that a host network may not collide with a *project* network name is
    not checkable here — it needs the rendered project identities — and is
    enforced by ``bin/edge.sh`` and ``bin/edge-network.sh`` against deployed
    state, where both names are actually known.
    """
    if edge["control_network"] == edge["egress_network"]:
        raise ManifestError(
            "edge.control_network and edge.egress_network must differ; sharing one network "
            "would put the Docker socket proxy on the same segment as project traffic"
        )


__all__ = [
    "CANONICAL_OS_RELEASE",
    "EDGE_COMPOSE_ENV_KEYS",
    "EDGE_STACK_NAME",
    "EDGE_STATE_DIR",
    "SUPPORTED_OS_RELEASES",
    "edge_compose_env",
    "load_host_manifest",
    "unrestricted_ssh_sources",
]

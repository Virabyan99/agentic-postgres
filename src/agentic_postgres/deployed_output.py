"""The deployed document: what is running, observed rather than intended.

A rendered `outputs.json` says what the manifests describe. This says what the
host actually has — which release is installed, which certificate the edge
holds, which secret generation is mounted. The two share a schema file and
nothing else, and ADR 0012 makes the difference explicit: the deployed document
is a *published observation*, never the authority. Bootstrap state owns provider
ownership; this reports it.

Three properties follow from that.

**Every field is passed in, none is inferred.** This module does no discovery.
A function that both observes and assembles would be one that can quietly
substitute an assumption for a measurement — reporting `tls.status: issued`
because a resolver is configured rather than because a certificate exists. The
caller measures; this validates the shape and refuses what does not fit.

**A deployed document is never byte-compared.** ADR 0013 keeps `observed_at` out
of rendered output and the determinism test scoped to rendered documents; this
one carries timestamps precisely because it describes a moment.

**Nothing here may carry a secret.** The same secret-free assertion the rendered
path uses runs over this document too. A deployed document names paths, ids and
a certificate fingerprint — a public certificate is public, and its digest
reveals nothing a TLS handshake does not already hand out.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_postgres import access_policy, config
from agentic_postgres.config import ManifestError

SCHEMA_VERSION = 8

#: Which declared secret backs each access profile. Derived from the broker's
#: own mapping rather than restated: the broker reads that mapping to decide
#: which file to open and refuses a document whose recorded reference disagrees
#: with it, so a second copy here would be a deployment the release will not
#: serve.
SECRET_FOR_PROFILE = {name: secret for name, (secret, _) in access_policy.PROFILE_SECRETS.items()}
PROJECT_STATE_ROOT = Path("/etc/agentic-postgres/projects")
RENDERED_ROOT = Path("/var/lib/agentic-postgres/rendered")

#: The database facts of a deployment nobody has read yet.
#:
#: Session 3 introduces `database.observed`, and the deploy path publishes a
#: document before anything has interrogated the cluster. This is the honest
#: value for that moment, and it is a named constant rather than a literal at
#: the call site so that "we did not look" cannot be spelled two ways. Reading
#: the cluster is `bin/session-03-check.sh --mode host`, which replaces this
#: wholesale; there is deliberately no path that fills in one member and leaves
#: the status saying nothing was observed.
NOT_OBSERVED: dict[str, Any] = {
    "status": "not_observed",
    "server_version": None,
    "extensions": None,
    "memory": None,
    "instance_uuid": None,
}

#: The API block of a deployment that publishes no REST surface.
#:
#: Every project deployed through a session before 5 is in this state, and so is
#: a session-5 project whose surface did not come up. It is a named constant for
#: the same reason `NOT_OBSERVED` is: "there is no published API" is a fact, it
#: has exactly one spelling, and a caller assembling eight nulls by hand would
#: eventually assemble seven.
API_NOT_PUBLISHED: dict[str, Any] = {
    "status": "unavailable",
    "exposed_schema": None,
    "max_rows": None,
    "request_body_max_bytes": None,
    "pool_size": None,
    "connection_budget_reserved": None,
    "api_surface_sha256": None,
    "canonical_openapi_sha256": None,
    "project_openapi_sha256": None,
}

#: The token-metadata block of a deployment with no issuer.
#:
#: Note what is *not* here: the issuer and audience the rendered document
#: derives. They are derivations and this branch could carry them at every
#: session -- but an issuer recorded beside `status: unavailable` would name a
#: verification authority for tokens nothing can mint, and ADR 0051's whole
#: subject is that the bootstrap issuer's existence is a state somebody has to
#: retire. Saying it does not exist yet is cheaper than explaining later why it
#: appeared to.
JWT_NOT_PUBLISHED: dict[str, Any] = {
    "status": "unavailable",
    "issuer": None,
    "audience": None,
    "algorithm": None,
    "active_kid": None,
    "verification_kids": None,
    "public_jwks_sha256": None,
    "temporary": None,
    "retire_after": None,
}

#: A route that this deployment does not publish. `health` is deliberately not
#: expressible this way: its URL is the same string for every project at every
#: session, so nulling it would delete an address rather than withhold a claim.
ROUTE_NOT_PUBLISHED: dict[str, Any] = {"status": "unavailable", "url": None}

__all__ = [
    "API_NOT_PUBLISHED",
    "JWT_NOT_PUBLISHED",
    "NOT_OBSERVED",
    "PROJECT_STATE_ROOT",
    "RENDERED_ROOT",
    "ROUTE_NOT_PUBLISHED",
    "SCHEMA_VERSION",
    "build_deployed_document",
    "deployed_path",
    "published_route",
    "rendered_path",
    "validate_deployed_document",
    "write_deployed_document",
]


def deployed_path(project_key: str, *, root: Path = PROJECT_STATE_ROOT) -> Path:
    return root / project_key / "outputs.json"


def rendered_path(project_key: str, *, root: Path = RENDERED_ROOT) -> Path:
    """The installed rendered directory, not a file inside it.

    Callers need the directory: it is what `bin/compose.sh` is given as the
    Compose project directory. Returning `outputs.json` here would make the one
    caller that wants the directory derive it back out with `.parent`.
    """
    return root / project_key


def observe_transports(
    *,
    rendered: dict[str, Any],
    loopback_address: str,
    allocation: dict[str, Any] | None,
) -> dict[str, Any]:
    """The `pooled`, `direct` and `access_profiles` blocks, as measured.

    **This is the writer those three blocks did not have.** The render
    hard-codes all of them `unavailable` with null references, deliberately —
    a render knows no port and no host. `build_deployed_document` then carried
    the rendered `database` block through verbatim, so a project deployed
    through session 4, with a healthy pooler and materialized secrets, still
    published a document saying every transport was unavailable. Three readers
    depend on the field and nothing set it: the access broker refuses any
    profile that is not `available`, the external suite reads the ports out of
    it, and §4.1 says deployed output may not report ready before the negative
    checks pass — which presumes it eventually reports something else. Found by
    deploying, not by reading (D112).

    **Availability is gated on the allocation being `active`, not on it
    existing.** `reserved` means two ports were set aside and nothing has
    connected to either; `active` means `database-ports.sh verify` connected to
    both. Publishing `available` off a reservation would claim an endpoint
    answers because something once intended it to — and §4.1 puts the off-host
    scan *before* that promotion, so it would also be making the claim ahead of
    the check that guards it.

    Pure: it takes an allocation rather than reading a registry, so the cases
    that matter — no allocation, a reservation, a released record — are testable
    with no host.
    """
    database = rendered["database"]
    profiles = {name: dict(profile) for name, profile in database["access_profiles"].items()}
    endpoints = {"pooled": dict(database["pooled"]), "direct": dict(database["direct"])}

    if allocation is None or allocation.get("state") != "active":
        return {**endpoints, "access_profiles": profiles}

    runtime_role = profiles["runtime_pooled"]["role"]
    name = database["name"]

    for transport, port in (
        ("pooled", allocation["pooled_port"]),
        ("direct", allocation["direct_port"]),
    ):
        endpoints[transport] = {
            "status": "available",
            "available_from_session": endpoints[transport]["available_from_session"],
            "host": loopback_address,
            "port": port,
            # A role and a host, never a password. The schema's `postgresUrl`
            # pattern admits one identifier in the userinfo component and no
            # colon, so a credential-bearing URL cannot validate here rather
            # than being redacted later by something that might forget. The
            # endpoint says *where*; `access_profiles` says as whom, which is
            # why one URL for two roles is not a loss of information.
            "url": f"postgresql://{runtime_role}@{loopback_address}:{port}/{name}",
            "password_secret_ref": SECRET_FOR_PROFILE["runtime_pooled"],
        }

    for profile_name, profile in profiles.items():
        profile["status"] = "available"
        profile["password_secret_ref"] = SECRET_FOR_PROFILE[profile_name]

    return {**endpoints, "access_profiles": profiles}


def published_route(rendered_url: str, status: str) -> dict[str, Any]:
    """One `routes.rest` or `routes.docs` entry, from the render plus a status.

    The URL is taken from the rendered document rather than rebuilt, so this
    branch never becomes a second derivation of an address the render already
    owns (ADR 0053). It is dropped when the status is not `ready`, because the
    schema says an unpublished route names nothing -- and it says so rather than
    leaving it optional because the value that would otherwise sit there is a
    URL that reads exactly like a working one.
    """
    if status not in {"ready", "unavailable"}:
        raise ManifestError(
            f"a published route is 'ready' or 'unavailable', not {status!r}. "
            "'planned' is the rendered branch's word, and copying it here would "
            "publish a manifest's intention as an observation"
        )
    return {"status": status, "url": rendered_url if status == "ready" else None}


def build_deployed_document(
    *,
    rendered: dict[str, Any],
    transports: dict[str, Any] | None = None,
    source_commit: str,
    host: dict[str, Any],
    edge: dict[str, Any],
    tls: dict[str, Any],
    bootstrap: dict[str, Any],
    secrets: dict[str, Any],
    runtime: dict[str, Any],
    health_status: str,
    rest_status: str,
    docs_status: str,
    api: dict[str, Any],
    jwt: dict[str, Any],
    database_observed: dict[str, Any],
    deployed_through_session: int,
) -> dict[str, Any]:
    """Assemble a deployed document from a rendered one plus observed facts.

    The project identity, health-route URL, database block and template version
    are carried over from the rendered document rather than re-derived. Deriving
    them again would create a second path to the same answer, and the failure
    that produces is a deployed document describing a project the render never
    produced — the collision the isolation tests exist to catch, arriving from
    inside the tool instead of from a manifest.

    The health *status* is not carried over, and the schema is what makes that
    unavoidable: rendered documents report `planned`, deployed documents accept
    only `ready` or `unavailable`. A render-time claim and a measurement of a
    running route are different facts that happen to share a field name, and
    copying one into the other would publish "the health endpoint is fine"
    because a manifest once said it would be.

    `rest_status`, `docs_status`, `api` and `jwt` are version 5's additions and
    none of them defaults. A default would put a session-5 shape on a session-4
    deployment, which is the same substitution `database_observed` refuses; the
    honest values for a deployment that publishes no API are
    :data:`API_NOT_PUBLISHED` and :data:`JWT_NOT_PUBLISHED`, named so that
    "nothing was published" cannot be spelled two ways.
    """
    if rendered.get("document_kind") != "rendered":
        raise ManifestError(
            f"expected a rendered document to build from, got {rendered.get('document_kind')!r}"
        )

    document = {
        "schema_version": SCHEMA_VERSION,
        "document_kind": "deployed",
        "source_commit": source_commit,
        # What was actually deployed, recorded beside the commit that deployed
        # it. The systemd launcher reads this at boot to decide which secrets to
        # materialize and which Compose profiles to start; without it, a
        # restart is a guess (D59, ADR 0032). A rendered document has no such
        # field and cannot: rendering happens with no host and deploys nothing.
        "deployed_through_session": deployed_through_session,
        "project": {
            "slug": rendered["project"]["slug"],
            "environment": rendered["project"]["environment"],
            "key": rendered["project"]["key"],
            "domain": rendered["project"]["domain"],
        },
        "host": dict(host),
        # `edge` as measured, plus the project's own two network names carried
        # from the render (ADR 0023). The caller's block names the *shared* edge
        # plane -- `apg-edge-control` and `apg-edge-egress` -- which is the same
        # pair for every project on the host. Reading those as though they were
        # project-scoped is what made three isolation assertions vacuous: with
        # one project deployed there was nothing for a shared value to collide
        # with, and with two the collision was one line of output.
        #
        # Carried, not re-derived. `apg-<key>-edge` is a convention this module
        # could reproduce, and reproducing it is exactly how a document naming
        # `apg-edge_control` -- a network that never existed -- got published.
        # The rendered document decides what `compose.env` will say, and
        # `compose.env` is what `bin/edge-network.sh` reads to decide what to
        # attach.
        "edge": {
            **edge,
            "project_edge_network": rendered["compose"]["networks"]["edge"],
            "project_internal_network": rendered["compose"]["networks"]["internal"],
        },
        "routes": {
            "health": {
                "status": health_status,
                "url": rendered["routes"]["health"]["url"],
            },
            # Version 5. Both URLs come from the render, which is their one
            # derivation; what this branch adds is whether anything is serving
            # them. `routes.docs` is the documentation root the rendered branch
            # has carried since Session 1, and the REST documentation page lives
            # under it -- so the status recorded here is the status of the page
            # this session publishes, not a claim about a root reserved for a
            # later index.
            "rest": published_route(rendered["routes"]["rest"], rest_status),
            "docs": published_route(rendered["routes"]["docs"], docs_status),
        },
        "api": dict(api),
        "jwt": dict(jwt),
        "tls": dict(tls),
        "bootstrap": dict(bootstrap),
        "secrets": dict(secrets),
        "runtime": dict(runtime),
        # Derived members carried from the render, plus the one measured member.
        # `database_observed` is a required argument with no default for the
        # same reason every other observation here is: a default would let a
        # caller that measured nothing produce a document indistinguishable
        # from one that did, and `NOT_OBSERVED` exists so that saying so is
        # one import rather than four literals.
        # Derived members carried from the render, the measured observation, and
        # the three transport blocks -- which are the only members a render
        # cannot know and a deploy must therefore supply. `transports=None`
        # keeps the rendered values, which is the honest answer for a session-2
        # or session-3 deployment where no transport exists to describe.
        "database": {
            **rendered["database"],
            **(transports or {}),
            "observed": dict(database_observed),
        },
        "template_version": rendered["template_version"],
        "observed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    return validate_deployed_document(document)


def validate_deployed_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ManifestError("a deployed document must be a JSON object")

    config.validate_against_schema(document, "outputs.schema.json")

    if document.get("document_kind") != "deployed":
        raise ManifestError(
            f"expected document_kind 'deployed', got {document.get('document_kind')!r}"
        )

    # The schema constrains the fields it knows. This is the rule that has to
    # hold whatever the schema grows: a deployed document is written to disk on
    # a host and read by tests, and neither is a place for a secret.
    config.assert_no_sensitive_keys(document)

    _refuse_placeholders(document)
    _refuse_incoherent_publication(document)
    return document


def _refuse_incoherent_publication(document: dict[str, Any]) -> None:
    """The two version-5 relations JSON Schema cannot state.

    **An `api` block that says `ready` needs a route that says `ready`.** The
    block describes what a surface serves; the route says whether anything is
    serving it. A document claiming a live API on an unpublished route is
    describing a service reachable by nobody, and every downstream assertion --
    the contract checksums, the row ceiling, the pool size -- would still be
    true of a thing no request can arrive at. The converse is left legal on
    purpose: a route that answers while the deploy could not read what it serves
    is a real state, and the honest record of it is a ready route beside an
    unavailable block.

    **The active key must be one of the keys verifiers accept.** Otherwise
    every token this issuer mints is rejected by every verifier that trusts this
    document, and nothing in the shape of the document says so.
    """
    api = document.get("api", {})
    routes = document.get("routes", {})
    if api.get("status") == "ready" and routes.get("rest", {}).get("status") != "ready":
        raise ManifestError(
            "api.status is 'ready' while routes.rest is "
            f"{routes.get('rest', {}).get('status')!r}. An API surface is served over a "
            "route; a document that publishes the first without the second describes "
            "something no request can reach"
        )

    jwt = document.get("jwt", {})
    active, accepted = jwt.get("active_kid"), jwt.get("verification_kids")
    if active is not None and active not in (accepted or []):
        raise ManifestError(
            f"jwt.active_kid {active!r} is not in jwt.verification_kids {accepted!r}. "
            "Every token signed by the active key would be refused by every verifier "
            "reading this document, and nothing else here would say so"
        )


def _refuse_placeholders(document: dict[str, Any]) -> None:
    """Angle-bracket text is a template that escaped, not an observation.

    A deployed document is meant to record real values. `<commit>` passing
    schema validation because it is a string of the right shape is how a
    deployment reports success against a document nobody filled in.
    """

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif isinstance(node, str) and node.startswith("<") and node.endswith(">"):
            raise ManifestError(f"{path} is an unfilled placeholder: {node!r}")

    walk(document, "")


def write_deployed_document(document: dict[str, Any], path: Path) -> Path:
    """Write atomically at 0600 root.

    0600 rather than 0644: this names the bootstrap state path, the provider
    identity ids and the active secret generation. None of that is a secret, but
    together it is a map of where the secrets are, and there is no reason for an
    unprivileged process on the host to hold it.
    """
    validate_deployed_document(document)

    if path.is_symlink():
        raise ManifestError(f"{path} is a symlink, which is not accepted")

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"

    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".outputs.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise

    descriptor = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    return path

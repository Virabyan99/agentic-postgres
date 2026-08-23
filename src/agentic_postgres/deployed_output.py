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

SCHEMA_VERSION = 13

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
    "verifier_acknowledgements": None,
}

#: The agent plane of a deployment that publishes no MCP surface.
#:
#: Version 12, and it is `API_NOT_PUBLISHED`'s counterpart for the same reason:
#: every project deployed through a session before 8 is in this state, and so is
#: a session-8 project whose agent plane did not come up. Six nulls assembled by
#: hand at a call site would eventually be five.
#:
#: `authorization_spec_conformant` is null here rather than `false`, and the
#: distinction is the honest one. This deployment's bearer profile is not
#: standards-conformant and the deployed block says so (D413) -- but only once
#: there IS a profile. `false` beside `status: unavailable` would report a
#: measurement of a surface that is not running, which is the substitution
#: `NOT_OBSERVED` exists to refuse.
MCP_NOT_PUBLISHED: dict[str, Any] = {
    "status": "unavailable",
    "protocol_revision": None,
    "authorization_spec_conformant": None,
    "accepted_token_use": None,
    "capability_contract_sha256": None,
    "capability_lock_sha256": None,
    "tool_count": None,
}

#: A route that this deployment does not publish. `health` is deliberately not
#: expressible this way: its URL is the same string for every project at every
#: session, so nulling it would delete an address rather than withhold a claim.
ROUTE_NOT_PUBLISHED: dict[str, Any] = {"status": "unavailable", "url": None}

#: The repository of a deployment nothing has asked yet. Version 13.
#:
#: `not_observed` and six nulls, `NOT_OBSERVED`'s discipline rather than a new
#: one: a zero `wal_failed_count` beside a `ready` status would be a claim that
#: archiving is healthy, and a zero here would be indistinguishable from a real
#: measurement that happened to be zero. This is the value every project carries
#: until Run 6 writes an observer, and a project deployed through a session
#: before 10 carries it permanently.
#:
#: `last_failed_wal` is deliberately absent from this block. rig1 measured the
#: segment name pinning to the oldest stuck WAL while `failed_count` climbed
#: 11/15/26 (D535), so a reader watching the name would see a steady value for
#: the whole failure. The count is what moves, so the count is what is published.
BACKUP_NOT_OBSERVED: dict[str, Any] = {
    "status": "not_observed",
    "stanza_created": None,
    "last_full_backup_label": None,
    "last_full_backup_at": None,
    "latest_recoverable_time": None,
    "wal_archived_count": None,
    "wal_failed_count": None,
}

__all__ = [
    "API_NOT_PUBLISHED",
    "BACKUP_NOT_OBSERVED",
    "JWT_NOT_PUBLISHED",
    "MCP_NOT_PUBLISHED",
    "NOT_OBSERVED",
    "PROJECT_STATE_ROOT",
    "RENDERED_ROOT",
    "ROUTE_NOT_PUBLISHED",
    "SCHEMA_VERSION",
    "activated_login_roles",
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
    app_status: str,
    app_docs_status: str,
    storage_status: str,
    mcp_status: str,
    api: dict[str, Any],
    jwt: dict[str, Any],
    mcp: dict[str, Any],
    database_observed: dict[str, Any],
    # Version 13. Optional, and defaulting to `not_observed` rather than being
    # required, because nothing observes the repository until Run 6 -- and a
    # required argument every caller would satisfy with the same constant is a
    # constant with extra steps. The moment an observer exists it passes one.
    backup_state: dict[str, Any] | None = None,
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

    `mcp_status` and `mcp` are version 12's, and they do not default either --
    for that reason and for one more. The rendered branch has named `routes.mcp`
    since version 1 and this branch had never carried it (D395), so every
    deployment on every host has published an agent-plane route nobody could
    read a status for. A default would have let that continue silently through
    the one release that fixes it: the caller that measured nothing would
    produce a document indistinguishable from the caller that measured
    `unavailable`. :data:`MCP_NOT_PUBLISHED` is the honest value and it is
    spelled once.
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
            # Version 9. Both URLs come from the render, which is their one
            # derivation. `app` is `unavailable` until an active project
            # administrator exists (D230) -- a status field rather than the
            # deployment state D135 refused -- and `app_docs` until the second
            # documentation surface is published.
            "app": published_route(rendered["routes"]["app"], app_status),
            "app_docs": published_route(rendered["routes"]["app_docs"], app_docs_status),
            # Version 11, and it follows `app` exactly (D326). `unavailable`
            # until the R2 credential validates, which makes this status the
            # provider-health field -- a dedicated deployment state was
            # considered and refused for `app`'s reason: `published_route`
            # already expresses it and every reader already understands it.
            #
            # Required with no default, like every other status here. A default
            # would let a deploy that observed nothing produce a document
            # indistinguishable from one that did.
            "storage": published_route(rendered["routes"]["storage"], storage_status),
            # Version 12, and it follows `app` and `storage` exactly (D326).
            #
            # The URL comes from the render, which is its one derivation -- and
            # it has come from there since version 1, which is the whole of
            # D395: `routes.mcp` was in the RENDERED document and absent from
            # the DEPLOYED one, so `deployed_output.py`'s explicit key list
            # published five routes out of six. That is D389 in a second place,
            # and it was found by comparing the two route sets AS SETS rather
            # than field by field, before a host trip could find it instead.
            "mcp": published_route(rendered["routes"]["mcp"], mcp_status),
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
        # Version 11's storage settings, carried from the render (D389).
        #
        # `routes.storage` was already here and this block was not, so a deployed
        # document announced the route and published none of the bounds that
        # route enforces. `rendering.py` resolves `max_upload_bytes` and the two
        # TTLs against `STORAGE_DEFAULTS` *there*, and says in place that it does
        # so because "the document is the one thing every plane reads"
        # (ADR 0002) -- and then the document every plane actually reads did not
        # carry them.
        #
        # Found by STO-BOUND-001 on the first host gate. It reads the bound from
        # the deployed document rather than from a constant of its own, exactly
        # as it should, and found nothing to measure. Neither example manifest
        # could have caught it: both set `max_upload_bytes` explicitly, so the
        # RENDERED document carries the field either way, and nothing compared
        # the rendered block with the deployed one (D332's shape).
        #
        # Carried whole rather than key by key, so that v11's schema is not
        # duplicated into a second list to keep in step -- which is the shape
        # that produced this row.
        "storage": dict(rendered["storage"]),
        # Version 13, and carried whole for the reason the line above is: one
        # `$def` serves both branches, so copying it key by key here would be a
        # second list to keep in step -- the shape that produced STO-BOUND-001.
        #
        # The settings and the observation are two blocks, not one. `backup` is
        # derived and identical on both branches; `backup_state` is measured and
        # exists only here, which is how ADR 0012's "a rendered document
        # contains no observed value" stays a property of the schema rather than
        # a rule somebody keeps.
        "backup": dict(rendered["backup"]),
        "backup_state": dict(backup_state) if backup_state else dict(BACKUP_NOT_OBSERVED),
        # Version 12's agent plane, in `api`'s role and deliberately in `api`'s
        # shape: what the surface serves, observed, with a status that forces
        # every other member null.
        #
        # There is no `mcp` block on the RENDERED branch, and the asymmetry is
        # the decision. `storage` is shared by both branches because its members
        # are bounds a manifest resolves and a runtime enforces; every member
        # here is either an observation of a running process (the protocol
        # revision), a digest of an artefact a deploy produces (the lock), or a
        # constant of the release (the accepted token use, ADR 0115). None of
        # them is a thing a manifest decides, so there is nothing for a rendered
        # branch to say -- and a rendered branch that said it anyway would be a
        # second authority for a value only a deployment can know.
        "mcp": dict(mcp),
        "template_version": rendered["template_version"],
        "observed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    return validate_deployed_document(document)


def activated_login_roles(document: dict[str, Any], roles: dict[str, str]) -> set[str]:
    """The roles a deployed document says can log in, derived from the document.

    **Extracted in Session 7 Run 4, and the mutation battery is why.** This
    derivation lived inline in `test_only_the_activated_roles_may_log_in`, a test
    gated on `APG_LIVE_HOST` -- so mutating any clause of it left the whole
    offline suite green. It is a pure function over a dict, so "the suite cannot
    drive this" was never true; only "nothing had" was.

    Every clause is keyed on the EVENT rather than on a session number, which is
    ADR 0096 and the reason D280 cost a run: a proxy fails on the day it and the
    thing it stands for come apart.

    * `migration_user` is Session 3's own activation, on every deployment.
    * An **available access profile** names a role a developer or an application
      reaches the cluster through, and an available profile can log in.
    * A **ready REST route** means something is authenticating as the API
      authenticator. That role is not a profile -- profiles are transports -- so
      without this clause it is activated, correct, and invisible (D211).
    * An **application route present at all** means the auth container is running
      and authenticating as `auth_service`.
    * The **storage credential in `secrets.required_names`** means the active
      generation carries the file, which is the same fact
      `postgres-bootstrap.activate_storage_service` reads when it decides whether
      to credential the role. `routes.storage` was the symmetrical choice and is
      wrong: it means "the document is v11", and v11 was published while
      `CURRENT_SESSION` was still 6 -- so a correct deployment today renders a
      storage route, materializes no storage secret, and leaves the role
      correctly NOLOGIN.
    * The **backup credential in `secrets.required_names`**, for exactly the
      reason one line up, and Session 10 Run 5's addition (D517, ADR 0148).
      `backup_user` had been a NOLOGIN stub since Session 3; the moment it can
      log in this function has to say so, or `test_only_the_activated_roles_-
      may_log_in` reports the product's own deliberate activation as a
      violation -- which is what D301 cost on the first host gate after
      `project_admin`. Keyed on the credential rather than on `backup.enabled`,
      and the difference is load-bearing: `activate_backup_user` credentials the
      role whenever the generation carries the file and never reads the
      manifest's flag. **There is no route to key on** -- a repository is not an
      HTTP surface -- so the symmetrical-looking alternative does not exist here
      at all.

    Returns role NAMES rather than suffixes, so a caller compares the result
    against `pg_roles` without a second mapping step.
    """
    activated = {roles["migration_user"]}

    profiles = (document.get("database") or {}).get("access_profiles") or {}
    activated |= {
        profile["role"] for profile in profiles.values() if profile.get("status") == "available"
    }

    routes = document.get("routes") or {}
    if (routes.get("rest") or {}).get("status") == "ready":
        activated.add(roles["postgrest_authenticator"])
    if routes.get("app") is not None:
        activated.add(roles["auth_service"])

    required = (document.get("secrets") or {}).get("required_names") or []
    if "storage_service_password" in required:
        activated.add(roles["storage_service"])
    if "backup_user_password" in required:
        activated.add(roles["backup_user"])

    return activated


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

    **Version 12 applies the first rule again, to `mcp` and `routes.mcp`.** Not
    generalised into a loop over pairs: the two relations are the same sentence
    about two surfaces, and a table driving them would be one place to forget to
    add the third. Written out, a missing pair is a missing paragraph.
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

    mcp = document.get("mcp", {})
    if mcp.get("status") == "ready" and routes.get("mcp", {}).get("status") != "ready":
        raise ManifestError(
            "mcp.status is 'ready' while routes.mcp is "
            f"{routes.get('mcp', {}).get('status')!r}. An agent plane is served over a "
            "route; a document that publishes the first without the second describes "
            "a tool surface no agent can reach"
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

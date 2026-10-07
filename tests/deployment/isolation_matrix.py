"""The isolation matrix's categories and its classifier (DEP-ISO-001), shared.

Moved verbatim out of `test_session12_isolation_matrix.py` in Session 38 Run 2
(D2162) so that an OFFLINE proof can classify every leaf of a deployed document
built from the fixture renders -- `tests/contract/test_isolation_leaves_offline.py`
-- instead of the live sweep finding each new field one trip late (D1029,
D1853, D2142: three facility flags reached a sweep unclassified).

**A test helper, not a product module** (D2195). The plan named
`src/agentic_postgres/isolation_matrix.py`; nothing in the product classifies
isolation leaves -- only proofs do -- and `test_no_module_is_imported_only_by_its_own_tests`
(D204) refuses a `src` module whose only callers are tests. `tests/deployment/`
already shares helpers this way (`oversized_request.py`).

The categories are explained in the live module's docstring; the comments on
each entry are the record of why it is where it is.
"""

from __future__ import annotations

import re

#: Project scope. Each entry is a full leaf path or a `*`-terminated prefix.
#:
#: Read off both deployed documents rather than recalled: every one of these was
#: observed to differ between `alpha-dev` and `beta-dev`, so the list describes
#: the deployment rather than an intention about it.
#:
#: **And that method has a failure mode this list has already hit** (D702).
#: A field that differs *at the moment you look* is not necessarily
#: project-scoped — it may differ because of a partial rollout, a mid-trip
#: state, or any other accident of when the two documents were written.
#: `runtime.release_path` was placed here for exactly that reason and had to be
#: moved. **A list derived from one observation encodes that observation's
#: accidents**, so each entry needs a reason it is project scope, not just
#: evidence that it differed once.
MUST_DIFFER = (
    # Identity
    "project.key",
    "project.slug",
    "project.domain",
    # The cluster and everything that names it
    "database.name",
    "database.container",
    "database.observed.instance_uuid",
    "database.roles.*",
    "database.access_profiles.*.role",
    "database.pooled.url",
    "database.direct.url",
    "database.pooled.port",
    "database.direct.port",
    "database.statement_timeouts.*",
    # Token authority. Two projects verifying each other's tokens is the
    # sharpest form of shared authority there is.
    "jwt.issuer",
    "jwt.audience",
    "jwt.active_kid",
    "jwt.verification_kids*",
    "jwt.public_jwks_sha256",
    # Networks a project's containers sit on. The edge joins both; nothing else may.
    "edge.project_edge_network",
    "edge.project_internal_network",
    # Published surface
    "routes.*.url",
    # Provider-side project scope. The ACCOUNT is shared and permitted; the
    # project inside it is not.
    "bootstrap.infisical_project_id",
    "bootstrap.runtime_identity_id",
    "bootstrap.state_path",
    # Backups: bucket, stanza and prefix are the three names that decide whose
    # history a restore reads.
    "backup.bucket",
    "backup.stanza",
    "backup.repository_prefix",
    # Version 16 (ADR 0188). The mirror bucket is this project's at the second
    # provider, derived from its key or named by its manifest; two projects
    # sharing one would copy over each other with --remove (D1000).
    "backup.mirror.bucket",
    # Object storage
    "storage.bucket",
    "storage.prefix",
    # On-host state. `runtime.release_path` is NOT here -- see RELEASE_STATE.
    "runtime.state_directory",
    "runtime.compose_model_sha256",
    "mcp.capability_lock_sha256",
    "api.project_openapi_sha256",
)

#: The substrate, and the control. One machine, one edge router, one release.
MUST_MATCH = (
    "host.id",
    "host.os_release",
    "host.public_ipv4",
    # Null on this deployment and asserted anyway: if an IPv6 is ever declared,
    # both projects must see the same one, because there is one machine. D688
    # is the record of that field being null and eight proofs skipping on it.
    "host.public_ipv6",
    "edge.stack_name",
    "edge.control_network",
    "edge.egress_network",
    # Version 17 (ADR 0198). Two projects on one host are deployed from ONE
    # release checkout, and the release lock's digest is a property of that
    # release rather than of either project. Two projects disagreeing about it
    # means two releases are installed on one machine -- which is precisely the
    # class of thing the host leaves above exist to notice, arriving in a field
    # that names the SQL each cluster holds.
    #
    # Classified here rather than at the first host gate, because that is where
    # D1029 found the mirror's four leaves unclassified and it cost a repair.
    "migrations.release_lock_sha256",
)

#: **Release state is deliberately NOT in MUST_MATCH**, and the first draft had
#: it there.
#:
#: `schema_version`, `template_version` and `deployed_through_session` drift
#: legitimately: for most of Session 11 alpha was deployed through 11 while beta
#: was still on 10, which is an ordinary partial rollout and not a broken
#: control. `project.environment` drifts too — one host may carry `alpha-dev`
#: beside `beta-prod`, which is the deployment topology working as designed.
#:
#: The control needs to establish one thing: **these two documents describe two
#: projects on one machine behind one router.** The host identity and the edge
#: stack say that and nothing else does. Widening it to release state would make
#: the control fail during exactly the situation an operator is most likely to be
#: in when they run the matrix.
RELEASE_STATE = (
    # **`runtime.release_path` is the installed release, and it was in
    # MUST_DIFFER until the first host run said otherwise** (D702). It is
    # `/opt/agentic-postgres/releases/<sha>` -- the code both projects run, and
    # identical the moment both are deployed from one release.
    #
    # It was classified as project scope because it **differed** when the matrix
    # was built. It differed because alpha was on Session 11 and beta on Session
    # 10, which is a partial rollout, not an isolation property. The very first
    # run in which both projects were current is the run that caught it.
    "runtime.release_path",
    "schema_version",
    "template_version",
    "document_kind",
    "deployed_through_session",
    "project.environment",
)

#: Carries no authority. Prefix rules rather than an enumeration: these grow
#: with every session and none of them is a claim in either direction.
NOT_AUTHORITY_PREFIXES = (
    # Version 15 (ADR 0186). A declaration about the project's life, not a
    # value it serves with: two permanent projects share it, an ephemeral one
    # differs, and neither says anything about isolation.
    "project.lifecycle.",
    "database.budget.",
    "database.observed.",
    "database.access_profiles.",
    "database.pooled.",
    "database.direct.",
    "database.api_connection_budget",
    "database.auth_connection_budget",
    "database.storage_connection_budget",
    "database.pooler_pool_size",
    "api.",
    "jwt.algorithm",
    "jwt.status",
    "jwt.temporary",
    "mcp.",
    "storage.",
    "backup.enabled",
    "backup.retain_full",
    # Version 16 (ADR 0188): whether a mirror exists and where the provider
    # is. Two projects at one second provider share the endpoint and region,
    # and a project without a mirror differs from one with; neither is a
    # claim about isolation. Added at Session 18's first host gate, which
    # found the four leaves unclassified (D1029).
    "backup.mirror.enabled",
    "backup.mirror.endpoint",
    "backup.mirror.region",
    # Version 17 (ADR 0198). Whether a project has a migration set of its own,
    # where it lives, what its lock digests to and how many migrations it holds.
    # One project declaring a set while the other does not is the ordinary case
    # -- it is what `project.example.yaml` and `project.second.example.yaml` are
    # -- and two projects sharing a set would be two tenants of one application,
    # which is also legitimate. Neither is a claim about isolation.
    #
    # NOT in MUST_DIFFER for that second reason, and the distinction is worth
    # stating: a set is not an identity. `project_set.root` reads like one, and
    # asserting two projects must differ in it would make a supported topology
    # into a failure.
    # The bare leaf as well as the prefix, and the difference is the whole of
    # D1029 repeating. `migrations.project_set.` covers `.root`,
    # `.lock_sha256` and `.count` -- the leaves a project WITH a set renders.
    # A project WITHOUT one renders the bare leaf as an explicit null, and
    # that is ALPHA: the control this session added to prove the boundary. The
    # first host gate of Session 20 reported exactly one unclassified field,
    # and it was the control's.
    "migrations.project_set",
    "migrations.project_set.",
    # Version 19 (ADR 0237): whether the project has the connectors facility.
    # Beta has it and alpha does not, which is the ordinary case, and two
    # projects that both have it share nothing by that fact: a facility, not
    # an identity -- `backup.mirror.enabled`'s reasoning. The first 1.12.0
    # sweep found it unclassified (D1853).
    "connectors.enabled",
    # Version 20 (ADR 0251): whether the project runs the control facility.
    # control-prod has it and alpha and beta do not; a facility, not an
    # identity -- `connectors.enabled`'s reasoning, and the third time a
    # facility flag reached a sweep unclassified (D1029, D1853, D2142).
    "control.enabled",
    "backup_state.",
    "bootstrap.status",
    "routes.",
    "secrets.",
    "tls.",
    "edge.project_network_attached",
    "observed_at",
    "source_commit",
    # Rotation state (ADR 0088), and per-project rather than shared. It is here
    # rather than in MUST_DIFFER because it is a deadline and a record of what
    # each verifier acknowledged, not an identity: two projects rotating in the
    # same window would legitimately carry the same deadline, and asserting they
    # must differ would make a coincidence into a failure.
    "jwt.retire_after",
    "jwt.verifier_acknowledgements",
)


def matches(path: str, pattern: str) -> bool:
    """`a.b.c`, `a.*.c`, `a.b.*` or `a.b*`."""
    if pattern.endswith("*") and "*" not in pattern[:-1]:
        return path.startswith(pattern[:-1])
    expression = "^" + re.escape(pattern).replace(r"\*", "[^.]+") + "$"
    return re.match(expression, path) is not None


def classify(path: str) -> str | None:
    for pattern in MUST_DIFFER:
        if matches(path, pattern):
            return "differ"
    for pattern in MUST_MATCH:
        if matches(path, pattern):
            return "match"
    if path in RELEASE_STATE:
        return "not_authority"
    for prefix in NOT_AUTHORITY_PREFIXES:
        if path == prefix or path.startswith(prefix):
            return "not_authority"
    return None

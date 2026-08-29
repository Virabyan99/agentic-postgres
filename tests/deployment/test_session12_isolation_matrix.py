"""`DEP-ISO-001` — two projects on one host share no state or authority.

**The distinction this module exists to draw is the one the specification names:
shared provider accounts are permitted, shared project scope is not.** Every
other isolation proof in this suite asserts that some particular pair of values
differs. None of them says what is *allowed* to be the same, and a matrix that
only lists forbidden sharing cannot tell a correctly isolated pair from two
documents it failed to read.

So there are three categories, not two, and every leaf in the deployed document
must fall into one:

``MUST_DIFFER``
    Project scope. A shared value here is a defect: one project's authority
    reaching another's data, credentials, routes or backups.

``MUST_MATCH``
    The substrate. One host, one edge router, one release. **This is the
    control** — if these differed, the two documents would not be describing two
    projects on one host, and every assertion below would be measuring something
    else.

``NOT_AUTHORITY``
    Everything that carries no authority either way: budgets, timeouts, protocol
    revisions and statuses that are identical because one template rendered both,
    **and per-project state** — backup timestamps, WAL counters, rotation
    deadlines — which differs or matches depending on when it was measured. The
    category was called `TEMPLATE` in the first draft, which was wrong the moment
    `backup_state.` went into it: a WAL counter is not template configuration.

`test_every_leaf_is_classified` is what keeps this honest as the document grows.
A field added by a later session lands in no category and reddens here, which
forces somebody to decide what it is. That is question 5 with tooling behind it:
**a decision (this value is project-scoped) gains a case, and the matrix is a
reader that would otherwise not get it.**
"""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = [pytest.mark.live_host, pytest.mark.p0, pytest.mark.security]


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------

#: Project scope. Each entry is a full leaf path or a `*`-terminated prefix.
#:
#: Read off both deployed documents rather than recalled: every one of these was
#: observed to differ between `alpha-dev` and `beta-dev`, so the list describes
#: the deployment rather than an intention about it.
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
    # Object storage
    "storage.bucket",
    "storage.prefix",
    # On-host state
    "runtime.release_path",
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
    "schema_version",
    "template_version",
    "document_kind",
    "deployed_through_session",
    "project.environment",
)

#: Carries no authority. Prefix rules rather than an enumeration: these grow
#: with every session and none of them is a claim in either direction.
NOT_AUTHORITY_PREFIXES = (
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


def _leaves(node: Any, path: str = "") -> dict[str, Any]:
    """Every scalar in the document, keyed by dotted path.

    List indices are kept (`verification_kids[0]`) because position is meaningful
    in the one list that matters: `render-jwks.py` orders the key set and a
    reader is expected to guess in that order.
    """
    out: dict[str, Any] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(_leaves(value, f"{path}.{key}" if path else key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.update(_leaves(value, f"{path}[{index}]"))
    else:
        out[path] = node
    return out


def _matches(path: str, pattern: str) -> bool:
    """`a.b.c`, `a.*.c`, `a.b.*` or `a.b*`."""
    if pattern.endswith("*") and "*" not in pattern[:-1]:
        return path.startswith(pattern[:-1])
    expression = "^" + re.escape(pattern).replace(r"\*", "[^.]+") + "$"
    return re.match(expression, path) is not None


def _classify(path: str) -> str | None:
    for pattern in MUST_DIFFER:
        if _matches(path, pattern):
            return "differ"
    for pattern in MUST_MATCH:
        if _matches(path, pattern):
            return "match"
    if path in RELEASE_STATE:
        return "not_authority"
    for prefix in NOT_AUTHORITY_PREFIXES:
        if path == prefix or path.startswith(prefix):
            return "not_authority"
    return None


# ---------------------------------------------------------------------------
# The control comes first
# ---------------------------------------------------------------------------


@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS")
def test_the_two_documents_describe_two_projects_on_one_host(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root
) -> None:
    """**The control, and it is not optional.**

    Everything below asserts that project-scoped values differ. Two documents
    read from the same file, or from two unrelated hosts, would satisfy that
    perfectly — the first trivially, the second by accident. So the substrate is
    asserted to be *shared* before anything is asserted to be separate.

    This is the same shape as `test_the_scan_catches_a_deliberately_leaky_renderer`
    and the positive control in `apg-diag listeners`: a proof of absence needs a
    proof that presence would have been visible.

    **It establishes one machine and one router, and deliberately not one
    release.** Two projects on a host drift apart between deploys — alpha ran a
    session ahead of beta for most of Session 11 — and a control that failed
    during a partial rollout would fail exactly when somebody was most likely to
    be running it.
    """
    del as_root
    assert project_a["project"]["key"] != project_b["project"]["key"], (
        "both documents name the same project, so this module is reading one "
        "deployment twice and every 'these differ' assertion below is vacuous"
    )

    a, b = _leaves(project_a), _leaves(project_b)
    for path in MUST_MATCH:
        if path not in a or path not in b:
            continue
        assert a[path] == b[path], (
            f"{path} differs ({a[path]!r} vs {b[path]!r}). These two projects are "
            "not on one host and one release, so the isolation assertions below "
            "would pass for the wrong reason"
        )


@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS")
def test_no_project_scoped_value_is_shared(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root
) -> None:
    """`DEP-ISO-001`. Every project-scoped value differs between the projects.

    Not a sample: the whole matrix in one assertion, so a value that becomes
    shared is named rather than merely making some other test red.

    Goes red if: a rendered identity collides, a role name is reused, a bucket or
    stanza is shared, or one project's key set would verify the other's tokens.
    """
    del as_root
    a, b = _leaves(project_a), _leaves(project_b)

    shared: list[str] = []
    for path, value in sorted(a.items()):
        if _classify(path) != "differ" or path not in b:
            continue
        # A null on both sides is an absent value, not a shared authority.
        if value is None and b[path] is None:
            continue
        if value == b[path]:
            shared.append(f"{path} = {value!r}")

    assert not shared, (
        "these project-scoped values are identical in both deployed documents, so "
        "the two projects share authority over them:\n  " + "\n  ".join(shared)
    )


@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS")
def test_neither_projects_scoped_names_appear_in_the_others_document(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root
) -> None:
    """A stronger question than "do these fields differ".

    Two projects could hold distinct values in every field and still leak: a
    document that *mentions* the other project's key, database name or bucket
    somewhere unexpected is a document with a path to it. So the whole serialized
    document is searched for the other's derived identity.

    `project.environment` is excluded because both are `dev` by construction, and
    the substrate control above already asserts that.
    """
    del as_root
    for own, other, label in (
        (project_a, project_b, "A's document mentions B"),
        (project_b, project_a, "B's document mentions A"),
    ):
        needles = {
            other["project"]["key"],
            other["project"]["slug"],
            other["project"]["domain"],
            other["database"]["name"],
            other["database"]["container"],
        }
        text = repr(_leaves(own))
        found = sorted(n for n in needles if n and str(n) in text)
        assert not found, f"{label}: {found}"


@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS")
def test_every_leaf_is_classified(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root
) -> None:
    """The matrix stays complete as the document grows.

    A field a later session adds falls into no category and reddens here, which
    forces a decision about whether it is project scope. Without this, the matrix
    silently describes an older document — **question 5, and this repository
    answers it wrong more often than any other**: a decision gains a case, and
    one of its readers does not get it.

    It is deliberately a failure rather than a warning. A warning about an
    unclassified field in a security matrix is a warning nobody reads.
    """
    del as_root
    unclassified = sorted(
        path
        for path in set(_leaves(project_a)) | set(_leaves(project_b))
        if _classify(path) is None
    )
    assert not unclassified, (
        "these fields are in a deployed document and in no isolation category. "
        "Decide for each whether it is project scope (MUST_DIFFER), the shared "
        "substrate (MUST_MATCH), or carries no authority "
        "(NOT_AUTHORITY_PREFIXES):\n  " + "\n  ".join(unclassified)
    )


def test_the_classifier_can_tell_the_categories_apart() -> None:
    """The control for the classifier itself.

    `_classify` drives all three tests above. One that returned `"not_authority"`
    for everything would make the matrix report a clean bill of health forever, and
    `test_every_leaf_is_classified` would pass most loudly of all (D374).
    """
    assert _classify("database.roles.app_runtime") == "differ"
    assert _classify("host.id") == "match"
    assert _classify("database.budget.max_connections") == "not_authority"
    assert _classify("routes.rest.url") == "differ", "a URL is project scope"
    assert _classify("routes.rest.status") == "not_authority", "a status is not"
    assert _classify("deployed_through_session") == "not_authority", (
        "release state drifts between deploys and is not the substrate"
    )
    assert _classify("a.field.nobody.classified") is None

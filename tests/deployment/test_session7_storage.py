"""The object-storage surface, against a deployment (Session 7).

Replaces the four Session 7 placeholders in
``tests/integration/test_future_storage.py`` and adds five requirements beside
them.

**None of this has ever executed, and that is stated here rather than
discovered later.** The storage service sits on ``profiles: [session7]``, no
deployment has started one, and no R2 bucket exists. Every proof below is
``live_host`` and will report ``not_run`` until Run 10's host trip. D211-D214
is the record of four defects that were each hidden by a proof nobody had run,
and D282 is Session 6 writing exactly this paragraph one run before its own
host trip found nine defects. Expect this module to be wrong in places; that is
what the trip is for.

**Two subjects, both holding ``objects:read`` and ``objects:write``.** The
ownership proofs need the second caller to be refused for *ownership* and not
for want of a scope -- a cross-owner test whose second subject lacks the scope
passes while measuring the scope check, and would keep passing with the owner
filter deleted. ``storage_probe_subject`` exists because the ordinary probe
holds neither scope: its docstring says the write proofs work because nothing
in the data plane reads ``scope``, and storage is the first surface where that
stops being true.

**Nothing here prints a URL or an object key.** A presigned URL is a bearer
credential and an object key is the unguessable half of one; ``STO-URL-001`` is
the canary scan that asserts they reach no sink, and a proof that logged one on
failure would be the leak it is looking for. Assertion messages name statuses,
counts and object ids.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# The only values interpolated into a statement here are object ids this module
# has just read out of a response as `object_id`, and role names from a rendered
# outputs document this repository produced. Neither is caller-supplied. The
# same exemption, for the same reason, as `tests/contract/test_storage_plane.py`.
import json
import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import naming

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: How large a probe upload declares itself. Small: these proofs are about
#: authorization and lifecycle, and a large body would measure the network.
PROBE_BYTES = 11
PROBE_BODY = b"hello world"
PROBE_TYPE = "text/plain"


def storage_base(app_base: Callable[[dict[str, Any]], str], document: dict[str, Any]) -> str:
    """The published storage prefix, derived rather than spelled.

    ``naming.STORAGE_PATH_SUFFIX`` is the single authority for where this
    surface sits under the application path -- the same constant the router's
    rule, its strip-prefix middleware and the aggregate OpenAPI document are all
    built from. A literal here would be a second derivation of a published
    route, which is D177.
    """
    return f"{app_base(document)}{naming.STORAGE_PATH_SUFFIX}"


def create_intent(api_call, base: str, token: str, **overrides: Any):
    body: dict[str, Any] = {"declared_bytes": PROBE_BYTES, "content_type": PROBE_TYPE}
    body.update(overrides)
    return api_call(f"{base}/upload-intents", method="POST", token=token, body=body)


# ---------------------------------------------------------------------------
# STO-OWN-001 -- a user cannot reach another user's object
# ---------------------------------------------------------------------------


def test_a_second_subject_cannot_obtain_a_download_url_for_the_first_s_object(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
    second_storage_owner_session: Any,
) -> None:
    """STO-OWN-001, and the refusal has to be the SAME refusal.

    Two assertions, and the second is the one with content. That a stranger is
    refused is the obvious half; that the refusal is **indistinguishable from an
    id that never existed** is what stops an object id being an existence
    oracle -- and object ids travel in URLs, so a caller who could tell "not
    yours" from "no such thing" could enumerate another subject's objects by
    guessing.

    Migration 0014 makes this structural rather than careful: the lookup
    function filters on owner inside the same predicate, so the service never
    learns which of the two cases it had.
    """
    base = storage_base(app_base, project_a)

    created = create_intent(api_call, base, storage_owner_session.token)
    assert created.status == 201, f"the owner could not create an intent: {created.status}"
    owned = json.loads(created.body)["object_id"]

    stranger = api_call(
        f"{base}/objects/{owned}/download-url", token=second_storage_owner_session.token
    )
    absent = api_call(
        f"{base}/objects/{uuid.uuid4()}/download-url",
        token=second_storage_owner_session.token,
    )

    assert stranger.status == 404, f"a second subject reached another's object ({stranger.status})"
    assert stranger.status == absent.status and stranger.body == absent.body, (
        "the refusal for another subject's object differs from the refusal for an id "
        "that does not exist, so an object id is an existence oracle"
    )


def test_the_owner_can_download_its_own_object(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
    completed_object: Callable[..., str],
) -> None:
    """The control for every refusal above, and Run 6's battery is why it exists.

    That run ended with a survivor because **every download test asserted a
    refusal**: mutating the ownership filter to deny everybody left them all
    green. A boundary proof without a positive arm measures a service that says
    no to everything.
    """
    base = storage_base(app_base, project_a)
    identifier = completed_object(storage_owner_session)

    granted = api_call(
        f"{base}/objects/{identifier}/download-url", token=storage_owner_session.token
    )
    assert granted.status == 200, f"the owner was refused its own object: {granted.status}"
    grant = json.loads(granted.body)
    assert grant["size_bytes"] == PROBE_BYTES
    assert grant["expires_in"] > 0


# ---------------------------------------------------------------------------
# STO-KEY-001 -- the key is the server's
# ---------------------------------------------------------------------------


def test_a_request_naming_a_key_or_a_bucket_is_refused(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
) -> None:
    """STO-KEY-001 at the surface, and `extra="forbid"` is what makes it a refusal.

    Without it pydantic accepts an unknown member and **discards it**, so a
    client naming `object_key` would get a 201 and no indication that its field
    went nowhere. Refused rather than ignored, so the client learns.
    """
    base = storage_base(app_base, project_a)
    for field in ("object_key", "key", "bucket", "prefix"):
        answer = create_intent(api_call, base, storage_owner_session.token, **{field: "mine"})
        assert answer.status == 400, (
            f"a request naming {field!r} was not refused ({answer.status}); a "
            "client-supplied key must have nowhere to arrive"
        )


def test_the_generated_key_matches_the_derived_format_and_is_not_echoed(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """The key is `<prefix>v1/<uuid4>` (ADR 0102), and the response does not carry it.

    Read from the **database** rather than from the response, and that is the
    point of the test rather than an implementation detail: the response must
    not contain the key at all. Reading it from the row proves the format; the
    absence from the body proves STO-KEY-001's other half.
    """
    base = storage_base(app_base, project_a)
    created = create_intent(api_call, base, storage_owner_session.token)
    assert created.status == 201, created.status
    body = json.loads(created.body)
    identifier = body["object_id"]

    code, stored, error = psql(
        project_a,
        f"SELECT object_key FROM app_private.storage_objects WHERE id = '{identifier}';",
        role=project_a["database"]["roles"]["object_owner"],
    )
    assert code == 0 and stored, f"could not read the object row back: {error}"

    expected = naming.storage_object_prefix(project_a["project"]["key"])
    pattern = re.escape(expected) + r"v1/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    assert re.match(pattern, stored), (
        "the stored key does not match the derived format. Reported as a pattern "
        "mismatch rather than by printing the key, which is a credential half"
    )

    for member in ("object_key", "key", "bucket"):
        assert member not in body, f"the response echoed {member!r}"


# ---------------------------------------------------------------------------
# STO-COMPLETE-001 -- only a verified object is downloadable
# ---------------------------------------------------------------------------


def test_an_intent_nobody_uploaded_is_not_downloadable(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
) -> None:
    """STO-COMPLETE-001. Pending is not available, and completion is not a formality.

    The intent exists, the caller owns it, and it is still a 404 -- because
    `storage_lookup_for_download` is filtered on `state = 'available'` and
    nothing has verified any bytes.
    """
    base = storage_base(app_base, project_a)
    created = create_intent(api_call, base, storage_owner_session.token)
    assert created.status == 201, created.status
    identifier = json.loads(created.body)["object_id"]

    answer = api_call(
        f"{base}/objects/{identifier}/download-url", token=storage_owner_session.token
    )
    assert answer.status == 404, f"an object nobody uploaded was downloadable ({answer.status})"


def test_completing_an_intent_nobody_uploaded_is_refused(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
) -> None:
    """The provider is asked, and it answers that there is nothing there.

    This is the arm that makes completion a verification rather than a state
    change the client requests: `HeadObject` returns 404, the service maps it to
    `ObjectUnavailable`, and the row stays pending for the cleanup lease.
    """
    base = storage_base(app_base, project_a)
    created = create_intent(api_call, base, storage_owner_session.token)
    identifier = json.loads(created.body)["object_id"]

    answer = api_call(
        f"{base}/upload-intents/{identifier}/complete",
        method="POST",
        token=storage_owner_session.token,
        body={},
    )
    assert answer.status == 404, (
        f"completion succeeded for an object with no bytes at the provider ({answer.status})"
    )


def test_completion_is_idempotent(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
    completed_object: Callable[..., str],
) -> None:
    """A retried completion is a 200, not a conflict (STO-COMPLETE-001).

    Migration 0015 exists for this: a pending-only key lookup 404s the second
    call before it reaches the compare-and-set that makes completion idempotent.
    0014's comment called the CAS idempotent, which was true of the function and
    false of the path through it (D349).
    """
    base = storage_base(app_base, project_a)
    identifier = completed_object(storage_owner_session)

    again = api_call(
        f"{base}/upload-intents/{identifier}/complete",
        method="POST",
        token=storage_owner_session.token,
        body={},
    )
    assert again.status == 200, f"a retried completion was not idempotent: {again.status}"
    assert json.loads(again.body)["state"] == "available"


# ---------------------------------------------------------------------------
# STO-BOUND-001 -- the declared size is bounded
# ---------------------------------------------------------------------------


def test_an_upload_larger_than_the_configured_bound_is_refused(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
) -> None:
    """STO-BOUND-001, against the bound this deployment actually published.

    The limit is read from the deployed document rather than from a constant in
    this file: a test carrying its own copy would pass against a deployment
    configured differently and would be measuring the test.
    """
    base = storage_base(app_base, project_a)
    configured = ((project_a.get("storage") or {}).get("max_upload_bytes")) or 0
    assert configured > 0, (
        "the deployed document publishes no storage.max_upload_bytes, so there is no "
        "bound here to measure"
    )

    answer = create_intent(
        api_call, base, storage_owner_session.token, declared_bytes=configured + 1
    )
    assert answer.status == 422, (
        f"an upload one byte over the published bound was accepted ({answer.status})"
    )

    allowed = create_intent(api_call, base, storage_owner_session.token, declared_bytes=configured)
    assert allowed.status == 201, (
        f"the control failed: an upload AT the bound was refused ({allowed.status}), so "
        "the arm above proves nothing about the bound"
    )


# ---------------------------------------------------------------------------
# STO-TOMB-001 -- a tombstone precedes every later grant
# ---------------------------------------------------------------------------


def test_a_deleted_object_yields_no_further_download_url(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
    completed_object: Callable[..., str],
) -> None:
    """STO-TOMB-001. The tombstone commits before any later grant is authorized.

    The ordering is the database's rather than the service's: the lookup is
    filtered on state in the same statement that reads the row, so a tombstone
    that has committed before it runs means no URL is granted. Deciding it in
    the service -- read the state, then choose -- would leave a window.

    **What this does NOT prove, and the documentation says so too:** a URL
    already issued keeps working. Nothing in this system can revoke a presigned
    URL, and the exposure is bounded by its TTL alone.
    """
    base = storage_base(app_base, project_a)
    identifier = completed_object(storage_owner_session)

    before = api_call(
        f"{base}/objects/{identifier}/download-url", token=storage_owner_session.token
    )
    assert before.status == 200, f"the control failed before the delete: {before.status}"

    removed = api_call(
        f"{base}/objects/{identifier}", method="DELETE", token=storage_owner_session.token
    )
    assert removed.status == 204, removed.status

    after = api_call(f"{base}/objects/{identifier}/download-url", token=storage_owner_session.token)
    assert after.status == 404, (
        f"a download URL was granted after the object was deleted ({after.status})"
    )


def test_deleting_twice_is_the_same_answer(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    storage_owner_session: Any,
) -> None:
    """DELETE is idempotent for the owner, and absence is not distinguished.

    204 for moved, for already tombstoned, for never existed and for another
    subject's alike. Answering 404 on absence would make DELETE non-idempotent
    *and* turn it into the existence oracle the download path refuses to be.
    """
    base = storage_base(app_base, project_a)
    created = create_intent(api_call, base, storage_owner_session.token)
    identifier = json.loads(created.body)["object_id"]

    first = api_call(
        f"{base}/objects/{identifier}", method="DELETE", token=storage_owner_session.token
    )
    second = api_call(
        f"{base}/objects/{identifier}", method="DELETE", token=storage_owner_session.token
    )
    never = api_call(
        f"{base}/objects/{uuid.uuid4()}", method="DELETE", token=storage_owner_session.token
    )

    assert first.status == second.status == never.status == 204, (
        f"delete answered {first.status}, {second.status} and {never.status} for moved, "
        "already-tombstoned and never-existed. They must be one answer"
    )


# ---------------------------------------------------------------------------
# STO-AGENT-001 -- the surface is human-only
# ---------------------------------------------------------------------------


def test_an_agent_token_cannot_reach_the_storage_surface(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    agent_session: Any,
) -> None:
    """STO-AGENT-001. ADR 0100 left `$defs/agent_scope` unwidened, deliberately.

    Object storage is human-only, so `objects:read` and `objects:write` are in
    the human classes and in no agent class. An agent token therefore cannot
    carry them however it is minted -- which makes this a 403 at the scope check
    rather than a rule somebody remembers.

    Asserted by *request* rather than by reading the vocabulary: a test over
    `scope_registry` would prove the schema and say nothing about whether the
    endpoint consults it.
    """
    base = storage_base(app_base, project_a)

    for path, method in (
        ("/upload-intents", "POST"),
        (f"/objects/{uuid.uuid4()}/download-url", "GET"),
        (f"/objects/{uuid.uuid4()}", "DELETE"),
    ):
        body = {"declared_bytes": PROBE_BYTES} if method == "POST" else None
        answer = api_call(f"{base}{path}", method=method, token=agent_session.token, body=body)
        assert answer.status == 403, (
            f"an agent token reached {method} {path} with {answer.status}; the storage "
            "surface is human-only and the refusal must be the scope check"
        )


def test_a_subject_without_the_object_scopes_is_refused(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    owner_session: Any,
) -> None:
    """The ordinary probe holds `notes:read` and `tasks:read` and nothing else.

    This is the arm that makes `storage_probe_subject` worth having: a
    registered, authenticated human without the scope is refused, so the storage
    proofs that succeed are succeeding because of the scope rather than because
    the endpoint checks nothing.
    """
    base = storage_base(app_base, project_a)
    answer = create_intent(api_call, base, owner_session.token)
    assert answer.status == 403, (
        f"a subject holding neither object scope created an upload intent ({answer.status})"
    )


# ---------------------------------------------------------------------------
# STO-SECRET-001 -- the credential matrix, from both sides
# ---------------------------------------------------------------------------


def test_the_storage_runtime_holds_no_signing_key_and_the_auth_runtime_no_r2_key(
    project_a: dict[str, Any],
    sh: Callable[..., str],
    service_container: Callable[[str, str], str],
    as_root: None,
) -> None:
    """STO-SECRET-001, and it is a filesystem property rather than a rule.

    Per-consumer materialization is the mechanism: the `storage` consumer is
    granted no signing key, so `APG_SIGNING_KEY_FILE` is absent from its
    environment and there is nothing on its filesystem to read; the `auth`
    consumer is granted neither R2 half.

    Read from **inside each container** rather than from the generation
    directory on the host. What a container holds is what a container holds
    (D76, D306), and a host-side check would be describing the pointer rather
    than the mount.
    """
    from agentic_postgres import runtime_override

    key = project_a["project"]["key"]

    storage = service_container(key, runtime_override.STORAGE_SERVICE)
    storage_environment = sh("docker", "exec", storage, "env")
    assert "APG_SIGNING_KEY_FILE" not in storage_environment, (
        "the storage runtime is handed a signing key path. It is a verifier and "
        "must never be an issuer (ADR 0101, D320)"
    )
    for half in ("APG_STORAGE_ACCESS_KEY_ID_FILE", "APG_STORAGE_SECRET_ACCESS_KEY_FILE"):
        assert half in storage_environment, f"the storage runtime has no {half}"

    auth = service_container(key, runtime_override.AUTH_SERVICE)
    auth_environment = sh("docker", "exec", auth, "env")
    for half in ("APG_STORAGE_ACCESS_KEY_ID_FILE", "APG_STORAGE_SECRET_ACCESS_KEY_FILE"):
        assert half not in auth_environment, (
            f"the auth runtime is handed {half}. The two credentials are kept apart by "
            "per-consumer materialization, which is what makes this a property of the "
            "filesystem rather than of anyone's discipline"
        )
    # And the file is not merely unreferenced -- it is not there.
    listing = sh("docker", "exec", auth, "sh", "-c", "ls /run/secrets 2>/dev/null || true")
    for name in ("r2_access_key_id", "r2_secret_access_key"):
        assert name not in listing, f"the auth container has {name} on disk"


def test_the_runtime_credential_cannot_administer_its_bucket(
    project_a: dict[str, Any],
    storage_admin_command: Callable[..., Any],
) -> None:
    """STO-CRED-001, and it is asserted by ATTEMPTING rather than by reading a scope.

    Run 5 measured the refusals with the real token: `CreateBucket` 403,
    `ListBuckets` 403, `HeadBucket` on another bucket in the same account 403.
    ADR 0110 then made the separation structural -- the credential that *can*
    administer a bucket is a Cloudflare API token no process here holds, and the
    storage image has no client that speaks that API.

    So what is proved live is the half that can be: the mounted credential
    reaches its own bucket. `verify-credential` writes nothing -- a HeadObject
    on a key that does not exist -- and the operator surface has no
    bucket-administering verb to attempt, which
    `tests/contract/test_storage_admin.py` asserts of the code.
    """
    result = storage_admin_command("verify-credential")
    assert result.returncode == 0, (
        f"the mounted credential does not reach the configured bucket "
        f"(exit {result.returncode}). A bucket-scoped token cannot tell 'absent' from "
        f"'not yours', so this does not say which of the two is wrong: {result.stdout[-400:]}"
    )


# ---------------------------------------------------------------------------
# STO-CLEAN-001 -- the plane converges
# ---------------------------------------------------------------------------


def test_cleanup_collects_a_tombstone_whose_write_window_has_closed(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    storage_owner_session: Any,
    completed_object: Callable[..., str],
    storage_admin_command: Callable[..., Any],
) -> None:
    """STO-CLEAN-001. The sweep is the first caller migration 0014 ever had.

    A completed object's key already holds bytes, so a replayed PUT is refused
    412 and it is collectable the moment it is tombstoned -- no waiting out the
    upload TTL (ADR 0111). That is the arm proved here, because it needs no
    clock manipulation.

    The late-writer arm -- a *pending* object held back until its presigned URL
    expires -- is proved offline against a real cluster in
    `tests/contract/test_storage_plane.py`, where the deadline can be moved.
    Proving it here would mean either waiting out the upload TTL or ageing a row
    by hand, and the second would be this test arranging the condition it claims
    to observe.
    """
    base = storage_base(app_base, project_a)
    identifier = completed_object(storage_owner_session)

    removed = api_call(
        f"{base}/objects/{identifier}", method="DELETE", token=storage_owner_session.token
    )
    assert removed.status == 204, removed.status

    result = storage_admin_command("cleanup", "--yes", "--limit", "50")
    assert result.returncode == 0, f"the sweep failed: {result.stdout[-400:]}"

    code, collected, error = psql(
        project_a,
        "SELECT cleanup_completed_at IS NOT NULL FROM app_private.storage_objects "
        f"WHERE id = '{identifier}';",
        role=project_a["database"]["roles"]["object_owner"],
    )
    assert code == 0, error
    assert collected == "t", (
        "the sweep did not collect a tombstoned, completed object. Its bytes are still "
        "at the provider and there is no orphan scan that would find them later"
    )


# ---------------------------------------------------------------------------
# DEP-ISO-007 -- two projects share nothing
# ---------------------------------------------------------------------------


@pytest.mark.requires_environment("APG_PROJECT_B_OUTPUTS")
def test_two_projects_have_distinct_buckets_prefixes_and_credentials(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    sh: Callable[..., str],
    service_container: Callable[[str, str], str],
    as_root: None,
) -> None:
    """DEP-ISO-007. Distinct at the provider, and distinct in what each holds.

    **Declares `APG_PROJECT_B_OUTPUTS` itself**, which the module gate does not.
    `test_every_test_declares_the_environment_it_consumes` caught this: a test
    that takes `project_b` without declaring the variable **errors** instead of
    skipping, so a host gate run with one project deployed would report a broken
    test rather than an unmeasured claim. Carrying *a* gate is not the same as
    carrying the *right* gate.

    Two projects sharing one R2 credential would mean either project's runtime
    could reach the other's objects, and the bucket name is the only thing
    standing between them -- a name is not an authorization boundary.

    The digests are compared rather than the values: `credential-digest` reports
    a SHA-256 precisely so that a proof like this can assert two credentials
    differ without either one existing outside a container.
    """
    from agentic_postgres import runtime_override

    assert project_a["project"]["key"] != project_b["project"]["key"]

    buckets = {}
    prefixes = {}
    digests = {}
    for document in (project_a, project_b):
        key = document["project"]["key"]
        container = service_container(key, runtime_override.STORAGE_SERVICE)
        environment = sh("docker", "exec", container, "env")
        buckets[key] = _environment_value(environment, "APG_STORAGE_BUCKET")
        prefixes[key] = _environment_value(environment, "APG_STORAGE_PREFIX")
        digests[key] = sh(
            "docker",
            "exec",
            container,
            "sh",
            "-c",
            "sha256sum /run/secrets/r2_access_key_id | cut -d' ' -f1",
        ).strip()

    assert len(set(buckets.values())) == 2, f"both projects use one bucket: {buckets}"
    assert len(set(prefixes.values())) == 2, f"both projects use one prefix: {prefixes}"
    assert len(set(digests.values())) == 2, (
        "both projects hold the same R2 access key. Either runtime could then reach the "
        "other's objects, with only a bucket name between them"
    )


def _environment_value(environment: str, name: str) -> str:
    for line in environment.splitlines():
        variable, _, value = line.partition("=")
        if variable == name:
            return value
    pytest.fail(f"{name} is absent from the container environment")
    raise AssertionError  # unreachable; keeps the return type honest


# ---------------------------------------------------------------------------
# STO-URL-001 -- no URL and no key reaches a sink
# ---------------------------------------------------------------------------


def test_no_presigned_url_or_object_key_reaches_any_sink(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    sh: Callable[..., str],
    service_container: Callable[[str, str], str],
    storage_owner_session: Any,
    as_root: None,
) -> None:
    """STO-URL-001, as a canary rather than as a review.

    A full cycle is driven, then the key and the signature are looked for in
    every place this deployment writes: both service logs, the edge access log,
    the journal, the deployed document and `docker inspect`. The canary is a
    value that exists **only** because this test just created it, so a hit is a
    leak rather than a coincidence.

    The two halves are looked for separately and for different reasons. The
    **signature** is the credential. The **key** is the unguessable half of one
    and is also what an audit record would most plausibly carry, since it looks
    like an identifier rather than a secret.

    Neither is ever printed. On failure the assertion names the sink and the
    number of hits, which is what an operator needs and is the most that can be
    said without repeating the leak into the test output.
    """
    base = storage_base(app_base, project_a)
    created = create_intent(api_call, base, storage_owner_session.token)
    assert created.status == 201, created.status
    body = json.loads(created.body)
    identifier = body["object_id"]

    signature = _query_parameter(body["upload_url"], "X-Amz-Signature")
    assert signature, "the upload URL carries no signature, so this canary is not one"

    code, key, error = psql(
        project_a,
        f"SELECT object_key FROM app_private.storage_objects WHERE id = '{identifier}';",
        role=project_a["database"]["roles"]["object_owner"],
    )
    assert code == 0 and key, error
    # The uuid suffix alone: the prefix is a derived, published, non-secret
    # value that legitimately appears in the deployed document, so searching for
    # the whole key would report a hit on `outputs.json` every time.
    canary = key.rsplit("/", 1)[-1]

    from agentic_postgres import runtime_override

    project_key = project_a["project"]["key"]
    sinks: dict[str, str] = {}
    for service in (runtime_override.STORAGE_SERVICE, runtime_override.AUTH_SERVICE):
        container = service_container(project_key, service)
        sinks[f"{service} log"] = sh("docker", "logs", "--tail", "2000", container)
        sinks[f"{service} inspect"] = sh("docker", "inspect", container)
    sinks["journal"] = sh("sh", "-c", "journalctl --no-pager -n 2000 2>/dev/null || true")
    sinks["deployed document"] = json.dumps(project_a)

    for name, content in sinks.items():
        assert signature not in content, (
            f"a presigned URL's signature appears in the {name}. It is a bearer "
            "credential; anyone reading that sink can perform the upload"
        )
        assert canary not in content, (
            f"an object key appears in the {name} ({content.count(canary)} times). A key "
            "is the unguessable half of a presigned URL and must not be recorded"
        )


def _query_parameter(url: str, name: str) -> str:
    """One query parameter, split by hand.

    `urllib` is refused anywhere near this service's own code by
    `test_the_service_never_constructs_a_network_jwks_client`, and although this
    is a test rather than the service, the habit is kept: two `partition` calls
    cost less than explaining why an exemption here is safe.
    """
    _, _, query = url.partition("?")
    for pair in query.split("&"):
        key, _, value = pair.partition("=")
        if key == name:
            return value
    return ""

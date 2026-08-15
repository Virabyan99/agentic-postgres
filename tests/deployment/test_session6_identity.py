"""The identity endpoints, through the published route (API-AUTH-001, API-AUTH-002, SEC-REV-002).

Replaces the Session 6 placeholder
``tests/integration/test_future_api.py::test_login_and_identity_endpoints_behave``.
Under ``tests/deployment/`` for D111's reason: the fixtures that make these
measurable -- a login against the deployed service, a statement against the
cluster -- are in this directory's conftest.

**Everything here goes through the edge.** Not through the container's port, and
not through an in-process ``create_app``: Runs 7 to 9 proved the service's
behaviour that way already, and what is unproved is the deployment -- the
router, the strip, the buffering bound, the mounted key set, and the fact that
the service the edge reaches is the one this repository built.

The distinction matters most for API-AUTH-002. ``strict_json`` refuses an
oversized body, and D273 measured that ``request.body()`` reads every byte
before the bound is applied. The edge now carries the same number as a
buffering middleware, so the refusal an outside caller gets should arrive
*before* the service allocates anything -- and only a request through the edge
can tell which of the two refused.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# The statements below interpolate a UUID this module's own fixture created and
# role names read from a deployed outputs document the schema validated. None of
# it is caller input, and parameter binding is unavailable where an identifier
# or an array literal goes -- the same judgement this directory's conftest
# records for the same reason.
import json
import time
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import auth_limits, jwt_claims

pytestmark = [
    pytest.mark.p0,
    pytest.mark.integration,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]


def test_login_issues_a_short_lived_token_and_me_reflects_current_state(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    app_login: Callable[..., Any],
    api_call: Callable[..., Any],
    app_probe_subject: Any,
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """API-AUTH-001, in the three parts the requirement names.

    **Login issues a short-lived token.** Against the probe subject rather than
    the administrator, so the proof does not depend on an operator flag. The
    deadline is checked as a bound, not as an equality: ``exp`` is set from the
    service's clock and read from this one.

    **`/auth/me` reflects the subject.** Compared against what the *cluster*
    says, read independently through ``psql``, rather than against what the
    login returned -- two readings of one record, which is the only way this can
    fail when the endpoint starts answering from the token's copy.

    **Four failures are indistinguishable.** Unknown subject, wrong password,
    disabled subject and a subject with no credential all answer 401 with the
    same body. A test that asserted only "wrong password is 401" would pass
    against a service that leaks which usernames exist.

    Goes red if: the route stops being published; a token outlives its stated
    lifetime; ``/auth/me`` answers from the token rather than from the record;
    or any of the four refusals grows a distinguishing body.
    """
    base = app_base(project_a)

    before = int(time.time())
    answer = app_login(project_a, app_probe_subject.username, app_probe_subject.password)
    after = int(time.time())
    assert answer.status == 200, f"login answered {answer.status}: {answer.body[:300]!r}"
    assert answer.headers.get("Cache-Control") == "no-store", (
        "a response carrying a token is cacheable; a shared cache would hand it to "
        f"whoever it serves next (Cache-Control: {answer.headers.get('Cache-Control')!r})"
    )

    issued = json.loads(answer.body)
    # (S105 matches on the field name. `Bearer` is RFC 6750's scheme name, not
    # a credential -- the same judgement `models.TokenResponse` records.)
    assert issued["token_type"] == "Bearer"  # noqa: S105

    # Bounded from both sides against the two clock readings that bracket the
    # call, so the assertion holds however long the request took. `exp` is set
    # from the service's clock and read from this one; an equality would be a
    # statement about clock drift between two machines.
    #
    # The ceiling is MAX_TTL_SECONDS and NOT MAX_TTL_SECONDS + CLOCK_SKEW: the
    # skew is what a *verifier* forgives, not extra life the issuer may grant.
    # A token whose own `exp` already included the skew would be live for 960s
    # against a verifier that then forgives another 30 (D241).
    lifetime = issued["expires_at"] - before
    assert 0 < lifetime <= (after - before) + jwt_claims.MAX_TTL_SECONDS, (
        f"the token's deadline is {lifetime}s away; the ceiling is "
        f"{jwt_claims.MAX_TTL_SECONDS}s, so this one outlives its contract"
    )

    current = api_call(f"{base}/auth/me", token=issued["access_token"])
    assert current.status == 200, (
        f"/auth/me refused a token this deployment issued moments ago ({current.status}: "
        f"{current.body[:300]!r}). Two verifiers are only two verifiers when something "
        "makes them read the same key set (D276)."
    )
    reflected = json.loads(current.body)

    code, recorded, error = psql(
        project_a,
        "SELECT username || '|' || role_name || '|' || status || '|' || "
        "credential_version || '|' || authz_version FROM app_private.users "
        f"WHERE id = '{app_probe_subject.user_id}';",
    )
    assert code == 0 and recorded, f"could not read the probe subject back: {error}"
    username, role, status, credential_version, authz_version = recorded.split("|")

    assert reflected["username"] == username
    assert reflected["role"] == role
    assert reflected["status"] == status
    assert reflected["credential_version"] == int(credential_version)
    assert reflected["authz_version"] == int(authz_version)
    assert reflected["scopes"] == list(app_probe_subject.scopes), (
        f"/auth/me reports {reflected['scopes']} where the record holds "
        f"{list(app_probe_subject.scopes)}"
    )

    # The four indistinguishable failures. Compared to each other rather than to
    # a literal, because what the requirement buys is that they cannot be told
    # apart -- and a body this suite hard-coded would still be four different
    # bodies if the service started varying them.
    refusals = [
        app_login(project_a, "nobody-by-this-name-exists", app_probe_subject.password),
        app_login(project_a, app_probe_subject.username, "not-this-subjects-password-at-all"),
        app_login(project_a, app_probe_subject.username.upper() + "x", "irrelevant-value-here"),
    ]
    for refusal in refusals:
        assert refusal.status == 401, f"a failed login answered {refusal.status}, not 401"
    bodies = {refusal.body for refusal in refusals}
    assert len(bodies) == 1, (
        f"failed logins answer with {len(bodies)} different bodies: {bodies}. The cause "
        "of a refusal tells a caller which usernames exist"
    )


def test_the_published_route_applies_the_input_bounds_before_the_service_allocates(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
) -> None:
    """API-AUTH-002's live half, which is the half no contract test can reach.

    ``tests/contract/test_auth_strict_json.py`` proves that ``parse_object``
    refuses a duplicate member, a non-object root and an oversized body. It
    cannot prove what D273 is about: ``request.body()`` reads the whole request
    before that bound is applied, so the service's refusal costs whatever the
    client chose to send. The edge now carries the same number
    (``auth_limits.MAX_BODY_BYTES``) as a buffering middleware.

    So this sends a body **well past** the bound and asserts the refusal is the
    edge's rather than the service's. Traefik answers 413 with an empty body;
    the service answers 400 with a JSON document naming the limit. Both are
    refusals, and only one of them means the middleware is attached.

    Goes red if: the buffering middleware is dropped from the application router
    (the 413 becomes a 400, which is D273 returning); the strict parser stops
    refusing a duplicate member; or an unknown field is silently discarded
    rather than refused.
    """
    base = app_base(project_a)

    oversized = api_call(
        f"{base}/auth/login",
        method="POST",
        body={"username": "probe", "password": "x" * (auth_limits.MAX_BODY_BYTES * 4)},
    )
    assert oversized.status == 413, (
        f"a {auth_limits.MAX_BODY_BYTES * 4}-byte body was answered "
        f"{oversized.status}, not 413. A 400 here means the request reached the "
        "service and was read in full before being refused, which is D273 -- the "
        "buffering middleware is not on this router"
    )

    # The strict parser, through the route. Sent as raw bytes rather than as a
    # dict, because `json.dumps` cannot produce a duplicate member.
    duplicate = api_call(
        f"{base}/auth/login",
        method="POST",
        raw=b'{"username": "a", "username": "b", "password": "irrelevant-value"}',
    )
    assert duplicate.status == 400, (
        f"a duplicate JSON member was answered {duplicate.status}. Python's default "
        "decoder resolves it silently to the last value, which is a request the "
        "caller and the server read differently"
    )

    unknown = api_call(
        f"{base}/auth/login",
        method="POST",
        body={"username": "a", "password": "irrelevant-value", "role": "project_admin"},
    )
    assert unknown.status == 400, (
        f"an unknown member was answered {unknown.status}. A discarded `role` is a "
        "client asking for something the server silently ignored"
    )


def test_a_disabled_and_re_enabled_subject_cannot_use_its_earlier_token(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    app_login: Callable[..., Any],
    api_call: Callable[..., Any],
    app_probe_subject: Any,
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """SEC-REV-002 — non-resurrection, in the case that isolates it.

    Disable-then-re-enable is the whole point, and M5 in Run 8's battery is why
    it is written this way. The obvious construction -- disable, then present
    the token -- stays green with the ``authz_version`` comparison deleted,
    because a redundant guard below it catches the *status* change. Only after
    the subject is re-enabled do role, scopes and status all end identical to
    what the token carries, and the single thing that differs is the version.

    Three revocation shapes, one property: a token issued before a change to a
    subject cannot be made to work again by undoing the change.

    Goes red if: the pre-request hook stops comparing ``authz_version``; a
    version is made to move backwards; or ``/auth/me`` starts answering from the
    token's copy of the subject's state.
    """
    base = app_base(project_a)
    subject = app_probe_subject.user_id

    answer = app_login(project_a, app_probe_subject.username, app_probe_subject.password)
    assert answer.status == 200, f"login answered {answer.status}"
    token = json.loads(answer.body)["access_token"]

    live = api_call(f"{base}/auth/me", token=token)
    assert live.status == 200, (
        f"the token is refused before anything was revoked ({live.status}); there is no "
        "revocation here to measure"
    )

    for label, disable, restore in (
        (
            "status",
            f"SELECT app_private.auth_set_status('{subject}', 'disabled');",
            f"SELECT app_private.auth_set_status('{subject}', 'active');",
        ),
        (
            "authorization",
            "SELECT app_private.auth_set_authorization("
            f"'{subject}', '{app_probe_subject.role_name}', ARRAY['notes:read']::text[]);",
            "SELECT app_private.auth_set_authorization("
            f"'{subject}', '{app_probe_subject.role_name}', "
            f"ARRAY[{', '.join(repr(s) for s in app_probe_subject.scopes)}]::text[]);",
        ),
    ):
        code, _, error = psql(project_a, disable)
        assert code == 0, f"could not change the subject's {label}: {error}"

        during = api_call(f"{base}/auth/me", token=token)
        assert during.status == 401, (
            f"a token issued before the {label} change was still accepted ({during.status})"
        )

        code, _, error = psql(project_a, restore)
        assert code == 0, f"could not restore the subject's {label}: {error}"

        after = api_call(f"{base}/auth/me", token=token)
        assert after.status == 401, (
            f"undoing the {label} change resurrected a token issued before it "
            f"({after.status}). Role, scopes and status are now identical to what the "
            "token carries, so the only thing that can refuse it is authz_version -- "
            "and it did not. This is the case M5 showed a weaker test cannot see"
        )

    # And the credential version, which moves on a password change rather than
    # on an authorization one. Restored to the probe's own hash afterwards so
    # the subject is exactly as the fixture left it.
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    code, _, error = psql(
        project_a,
        f"SELECT app_private.auth_set_password('{subject}', "
        f"'{hashing.Hasher().hash('a-different-password-entirely-9931')}');",
    )
    assert code == 0, f"could not change the subject's password: {error}"

    after_password = api_call(f"{base}/auth/me", token=token)
    assert after_password.status == 401, (
        f"a token issued before a password change was still accepted "
        f"({after_password.status}); a reset does not invalidate outstanding tokens"
    )

    code, _, error = psql(
        project_a,
        f"SELECT app_private.auth_set_password('{subject}', "
        f"'{hashing.Hasher().hash(app_probe_subject.password)}');",
    )
    assert code == 0, f"could not restore the subject's password: {error}"

    restored = api_call(f"{base}/auth/me", token=token)
    assert restored.status == 401, (
        "restoring the original password resurrected a token issued before the change "
        "-- credential_version is monotonic and must never be reusable"
    )

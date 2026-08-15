"""Administration, and the door it cannot be reached through (API-ADMIN-001, SEC-BOOT-002).

Replaces the Session 6 placeholder
``tests/integration/test_future_api.py::test_admin_endpoints_require_explicit_admin_scope``.

Two requirements that look like one and are not. API-ADMIN-001 is about
**authorization**: an administrator without the scope is refused, so holding the
role never implies holding the authority. SEC-BOOT-002 is about **bootstrap**:
the first administrator is created through a local, root-only path and exactly
once, and no HTTP surface can create one -- which is what makes the
authorization question meaningful in the first place, because an endpoint that
mints administrators makes every scope check decorative.

They are separate registry IDs for the reason ADR 0089 gives: `SEC-BOOT-001`
already means something else -- that the temporary bootstrap *issuer* holds the
only private key -- and one ID for two guarantees is what D47 refused.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, scope_registry

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: The scope that admits the user-administration endpoints. Named here rather
#: than derived, because the point of the requirement is that this exact string
#: is what is checked -- deriving it from the same registry the service reads
#: would make the assertion a tautology (D260's second mutation).
ADMIN_WRITE_SCOPE = "admin_users:write"
ADMIN_READ_SCOPE = "admin_users:read"


def test_the_admin_endpoints_require_the_scope_and_not_the_role(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    app_login: Callable[..., Any],
    api_call: Callable[..., Any],
    admin_session: Any,
    app_probe_subject: Any,
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """API-ADMIN-001 — the role never implies the scope.

    Three callers, and the middle one is the requirement:

    * an ordinary subject, which is refused (the control that the endpoint is
      guarded at all);
    * **a subject holding `project_admin` with the administrative scopes
      removed**, which must also be refused -- this is the case a check written
      against the role name passes;
    * the real administrator, which succeeds (the control that the endpoint is
      reachable, without which every refusal above could be a 404).

    The middle caller is constructed by moving the probe subject *into* the
    administrator role while leaving it the scopes it already had. That is a
    legitimate state: `ROLE_SCOPES` gives `project_admin` a ceiling, and a
    subject's actual scopes come from its own record, so a `project_admin` with
    only `notes:read` is exactly what the requirement is about.

    Goes red if: the guard is rewritten to compare the role; a scope check is
    dropped from any administrative endpoint; or the ceiling is confused with
    the grant.
    """
    base = app_base(project_a)
    admin_role = project_a["database"]["roles"]["project_admin"]

    ceiling = scope_registry.permitted_scopes("project_admin")
    assert ADMIN_WRITE_SCOPE in ceiling, (
        f"{ADMIN_WRITE_SCOPE} is not in project_admin's ceiling {sorted(ceiling)}; this "
        "test is asserting a scope the vocabulary no longer contains (ADR 0079)"
    )

    # 1. An ordinary subject.
    ordinary = app_login(project_a, app_probe_subject.username, app_probe_subject.password)
    assert ordinary.status == 200
    ordinary_token = json.loads(ordinary.body)["access_token"]

    refused = api_call(f"{base}/admin/users", token=ordinary_token)
    assert refused.status == 403, (
        f"an ordinary subject reached /admin/users ({refused.status}); the endpoint is not guarded"
    )

    # 2. The same subject, promoted to the administrator ROLE, with its scopes
    #    unchanged. Restored in the finally, so a failure here does not leave a
    #    subject holding an administrative role.
    code, _, error = psql(
        project_a,
        f"SELECT app_private.auth_set_authorization('{app_probe_subject.user_id}', "
        f"'{admin_role}', ARRAY['notes:read']::text[]);",
    )
    assert code == 0, f"could not promote the probe subject: {error}"
    try:
        promoted = app_login(project_a, app_probe_subject.username, app_probe_subject.password)
        assert promoted.status == 200, f"the promoted subject cannot log in ({promoted.status})"
        promoted_token = json.loads(promoted.body)["access_token"]

        reflected = api_call(f"{base}/auth/me", token=promoted_token)
        assert reflected.status == 200
        assert json.loads(reflected.body)["role"] == admin_role, (
            "the subject was not actually promoted, so the interesting case never ran"
        )
        assert ADMIN_WRITE_SCOPE not in json.loads(reflected.body)["scopes"], (
            "the promotion granted the administrative scope as well, which is the state "
            "this case exists to exclude"
        )

        for method, url in (
            ("GET", f"{base}/admin/users"),
            ("POST", f"{base}/admin/users"),
            ("GET", f"{base}/admin/agents"),
            ("POST", f"{base}/admin/agents"),
        ):
            answer = api_call(
                url,
                method=method,
                token=promoted_token,
                body={} if method == "POST" else None,
            )
            assert answer.status == 403, (
                f"{method} {url} answered {answer.status} for a subject holding "
                f"{admin_role!r} without {ADMIN_WRITE_SCOPE!r}. The role was accepted in "
                "place of the scope, which is exactly what API-ADMIN-001 refuses"
            )
    finally:
        psql(
            project_a,
            f"SELECT app_private.auth_set_authorization('{app_probe_subject.user_id}', "
            f"'{app_probe_subject.role_name}', "
            f"ARRAY[{', '.join(repr(s) for s in app_probe_subject.scopes)}]::text[]);",
        )

    # 3. The real administrator, which must be able to do it -- otherwise every
    #    refusal above is consistent with an endpoint that does not exist.
    assert ADMIN_READ_SCOPE in admin_session.scopes, (
        f"the administrator holds {list(admin_session.scopes)}, without "
        f"{ADMIN_READ_SCOPE!r}; there is no positive control available here"
    )
    allowed = api_call(f"{base}/admin/users", token=admin_session.token)
    assert allowed.status == 200, (
        f"the administrator was refused ({allowed.status}: {allowed.body[:200]!r}). Every "
        "403 above is consistent with an endpoint that is simply absent"
    )


def test_no_http_surface_creates_an_administrator(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    admin_session: Any,
) -> None:
    """SEC-BOOT-002's first half: the bootstrap path is not on the network.

    An unauthenticated caller is refused at every plausible spelling of a
    bootstrap endpoint, and -- the part that matters more -- an **authenticated
    administrator** cannot create a `project_admin` either. The scope ceiling is
    not the guard here; the guard is that role assignment goes through the
    server-side record and the endpoint refuses a role outside what it may set.

    A 404 is accepted for the unauthenticated spellings because the route does
    not exist, which is the strongest possible answer. What is not accepted is a
    401: that would mean something is *there*, waiting for a credential.

    Goes red if: a bootstrap route is added; `POST /admin/users` starts
    accepting an arbitrary role; or the application router stops refusing
    unknown paths.
    """
    base = app_base(project_a)

    for path in ("/auth/bootstrap", "/admin/bootstrap", "/bootstrap", "/admin/users/bootstrap"):
        answer = api_call(f"{base}{path}", method="POST", body={"username": "x"})
        assert answer.status in (404, 405), (
            f"POST {path} answered {answer.status}. A 401 or 403 means a bootstrap "
            "surface exists and is merely guarded; SEC-BOOT-002 is that it does not "
            "exist on the network at all"
        )

    escalation = api_call(
        f"{base}/admin/users",
        method="POST",
        token=admin_session.token,
        body={
            "username": "would-be-second-administrator",
            "display_name": "Escalation probe",
            "role": project_a["database"]["roles"]["project_admin"],
            "scopes": ["admin_users:read", "admin_users:write"],
            "password": "an-entirely-adequate-passphrase-8814",
        },
    )
    assert escalation.status in (400, 403, 422), (
        f"an administrator created a second administrator over HTTP ({escalation.status}: "
        f"{escalation.body[:300]!r}). The bootstrap path is local and once-only precisely "
        "so that administrator creation is not an HTTP capability"
    )


def test_the_local_bootstrap_refuses_a_second_administrator(
    project_a: dict[str, Any],
    as_root: None,
) -> None:
    """SEC-BOOT-002's second half: exactly once, through the local path.

    The command is run for real, against the deployment, with a password on a
    file descriptor so nothing reaches ``ps``. It must refuse -- an administrator
    already exists -- and the refusal is what proves the once-only property on
    *this* deployment rather than in a unit test's fake.

    Run 8 drove the advisory-lock race by hand and recorded that without the lock
    the table ends with two administrators; that measurement is in the run log
    and is **not** repeated here, because racing two bootstraps against a live
    deployment would leave one of the two outcomes behind.

    Goes red if: the refusal is removed; the exit code changes; or the command
    starts accepting a password as an argument.
    """
    del as_root
    outputs = f"/etc/agentic-postgres/projects/{project_a['project']['key']}/outputs.json"

    # Descriptor 0 with the value written to stdin, rather than `--password`,
    # which does not exist: an argument is visible in `ps`, `/proc/<pid>/cmdline`
    # and the shell's history. `sh_status` cannot express this because it
    # attaches no stdin, and a command that read EOF where a password should be
    # would fail for the wrong reason and still look like the refusal under test.
    result = subprocess.run(
        [
            str(REPO_ROOT / "bin" / "auth-admin.sh"),
            "--outputs",
            outputs,
            "bootstrap",
            "--username",
            "second-administrator-probe",
            "--display-name",
            "Second administrator probe",
            "--password-fd",
            "0",
        ],
        input="an-entirely-adequate-passphrase-4471\nan-entirely-adequate-passphrase-4471\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "a second bootstrap succeeded. The deployment now has two administrators, and "
        f"the first one's authority is no longer exclusive:\n{combined}"
    )
    assert "administrator" in combined.lower(), (
        f"the refusal does not say what it refused, which is the message an operator "
        f"reads at the worst possible moment:\n{combined}"
    )

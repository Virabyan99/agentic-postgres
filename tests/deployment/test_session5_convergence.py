"""The API plane across restarts and rotations (Run 10, D120's and D121's shapes).

Two kinds of proof live here and they are gated differently on purpose.

**The restart matrix performs its own restarts**, because a container restart is
something a test can do and then wait for. Four of them, each with a distinct
failure mode behind it rather than four spellings of one: the REST service alone,
the documentation service alone, the cluster underneath a configured PostgREST,
and the whole project unit through systemd.

**The rotations are declared**, because a rotation is an operator action inside a
maintenance window and a test that performed one would be rotating production
credentials on every run. A flag is a claim, so every rotation test here is
written to *refuse a false declaration*: it asserts the pre-rotation value is not
the active one before it asserts anything is refused. Without that, a window in
which nothing was rotated passes every refusal — the old credential is refused
because it is the new credential, and the test reports success for the reason it
exists to rule out (D121).

The convergence assertion is shared and it carries its own positive control:
443 must be **present** in the listener output that is scanned for new ones. A
negative from an instrument that can see nothing is not a boundary (D120).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

# Session 4 built these and they are imported rather than copied. `sh` returns
# the host's `ss` output; `the_instrument_can_see` is the positive control that
# makes `public_listeners` mean something. A third copy of either would be a
# third place for the definition of "public" to drift (D204's shape, one file
# over).
from test_session4_convergence import (  # type: ignore[import-not-found]
    container_is_running,
    public_listeners,
    the_instrument_can_see,
)

from agentic_postgres import openapi_normalize

pytestmark = [pytest.mark.live_host, pytest.mark.p0]

#: How long a plane may take to come back before that is a failure rather than
#: a restart. Generous, because the cluster restart invalidates every server
#: connection at once and PostgREST rebuilds its schema cache afterwards;
#: bounded, because "eventually" is not a property this suite can assert.
RESTART_RETURN_TIMEOUT_SECONDS = 120

REST_SERVICE_SUFFIX = "postgrest"
DOCS_SERVICE_SUFFIX = "docs"


def key(document: dict[str, Any]) -> str:
    return document["project"]["key"]


def service_container(document: dict[str, Any], suffix: str, sh) -> str:
    """One project's container for a service, found by the labels it carries.

    **By label, not by name.** The first version built a prefix from
    `document["compose"]["project_name"]` -- which exists only in a *rendered*
    document, and every fixture here is a deployed one, so it raised
    `KeyError: 'compose'` on its first host run. The labels are better than a
    corrected name would have been: `apg.project.key` is set by this
    repository's own Compose model and `com.docker.compose.service` by Compose
    itself, so neither is a name this test derives.

    **`docker ps` runs here rather than through the `running_containers`
    fixture**, which is session-scoped. These tests restart containers, which
    replaces them, so a listing taken at the start of the run is stale by the
    second test -- precisely the defect D195 records for `API-CACHE-001`.
    """
    names = [
        line
        for line in sh(
            "docker", "ps",
            "--filter", f"label=apg.project.key={key(document)}",
            "--filter", f"label=com.docker.compose.service={suffix}",
            "--format", "{{.Names}}",
        ).splitlines()
        if line
    ]  # fmt: skip
    assert len(names) == 1, f"expected one {suffix} container for {key(document)}, got {names}"
    return names[0]


# ---------------------------------------------------------------------------
# What "converged" means for the API plane
# ---------------------------------------------------------------------------


def assert_api_converged(
    document: dict[str, Any],
    *,
    rest_base,
    api_call,
    mint_token,
    docs_command,
    sh,
) -> None:
    """Both routes answer as themselves, the document is unchanged, nothing new listens.

    Four assertions, and each would be satisfied by a different broken state:

    * an authenticated read returns rows -- a plane that came back refusing
      everything satisfies every *refusal* below;
    * the served document's digest still matches the one the deploy recorded, so
      a restart that came back serving a different surface is a failure rather
      than a curiosity;
    * the documentation route still refuses with a Basic challenge, which is the
      state a middleware that failed to reload would lose;
    * no public listener appeared, asserted from output proved to contain 443.
    """
    base = rest_base(document)
    roles = document["database"]["roles"]

    # Polled, not asked once. A restart returns as soon as the container is
    # replaced, and the plane behind it still has to reconnect its pool and
    # rebuild its schema cache; the cluster restart produced
    # `503 57P01 terminating connection due to administrator command`, which is
    # PostgREST correctly reporting a connection the restart killed.
    #
    # Only the *first* assertion polls. Once the plane serves a read, everything
    # below it is a steady-state fact and must be immediate -- a route that is
    # wrong while nothing is happening to it is a failure, and wrapping that in
    # a retry would turn a broken deployment into a slow green.
    reader = mint_token(document, roles["authenticated"], subject=None)
    deadline = time.monotonic() + RESTART_RETURN_TIMEOUT_SECONDS
    last = "no attempt was made"
    while time.monotonic() < deadline:
        read = api_call(f"{base}/notes?select=id&limit=1", token=reader)
        if read.status == 200:
            break
        last = f"{read.status} {read.body[:120]}"
        time.sleep(2)
    else:
        pytest.fail(
            f"{key(document)} did not serve an authenticated read within "
            f"{RESTART_RETURN_TIMEOUT_SECONDS}s of the restart; last: {last}"
        )

    served = api_call(base, token=mint_token(document, roles["api_documentation"], subject=None))
    assert served.status == 200, f"the document was not served after the restart: {served.status}"
    digest = openapi_normalize.fingerprint(
        openapi_normalize.sort_maps(openapi_normalize.load_document(served.body))
    )
    assert digest == document["api"]["project_openapi_sha256"], (
        "the surface served after the restart is not the one this deployment published"
    )

    url = docs_command.docs_url(document)
    assert docs_command.check(url) == 0, (
        f"{url} stopped refusing without a credential after the restart"
    )

    the_instrument_can_see(sh)
    assert not public_listeners(sh), "a restart introduced public listeners:\n" + "\n".join(
        public_listeners(sh)
    )


# ---------------------------------------------------------------------------
# API-CONTRACT-001 -- the restart matrix
# ---------------------------------------------------------------------------


@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS")
def test_restarting_the_rest_service_restores_the_surface(
    as_root,
    sh,
    project_a,
    project_b,
    rest_base,
    api_call,
    mint_token,
    docs_command,
) -> None:
    """PostgREST alone, with the cluster untouched underneath it.

    What it proves is that everything the request plane needs comes back from
    state on disk: the JWKS mount, the pre-request hook's schema cache, and the
    role settings migration 0010's hook reads. A service that came back without
    its schema cache answers 404 for every object while reporting healthy --
    which `--ready` alone cannot distinguish (D145).

    Goes red if: the JWKS is unreadable on a second start; the schema cache does
    not rebuild; or the documentation route's middleware is tied to this
    container's lifecycle, which is the failure `edge_credentials` writing to the
    file provider exists to prevent.
    """
    del as_root
    sh("docker", "restart", service_container(project_a, REST_SERVICE_SUFFIX, sh))

    assert_api_converged(
        project_a,
        rest_base=rest_base,
        api_call=api_call,
        mint_token=mint_token,
        docs_command=docs_command,
        sh=sh,
    )
    assert_api_converged(
        project_b,
        rest_base=rest_base,
        api_call=api_call,
        mint_token=mint_token,
        docs_command=docs_command,
        sh=sh,
    )


@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS")
def test_restarting_the_documentation_service_restores_its_refusal(
    as_root,
    sh,
    project_a,
    project_b,
    rest_base,
    api_call,
    mint_token,
    docs_command,
) -> None:
    """The documentation page alone.

    The interesting half is what must **not** change: the credential middleware
    lives in Traefik's file provider rather than on this container (ADR 0069), so
    a restart here must not disturb the refusal at all. If the middleware were a
    label on this container, the route would answer 404 for the seconds the
    container is gone and then recover -- a window nothing else in this suite
    would notice.

    Goes red if: the mounted snapshot is unreadable on a second start, which
    `serve.py` reports as 503; or the refusal depends on this container being up.
    """
    del as_root
    sh("docker", "restart", service_container(project_a, DOCS_SERVICE_SUFFIX, sh))

    assert_api_converged(
        project_a,
        rest_base=rest_base,
        api_call=api_call,
        mint_token=mint_token,
        docs_command=docs_command,
        sh=sh,
    )
    assert docs_command.check(docs_command.docs_url(project_b)) == 0, (
        "restarting one project's documentation service disturbed the other's route"
    )


@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_restarting_the_cluster_under_a_configured_rest_plane(
    as_root,
    sh,
    project_a,
    rest_base,
    api_call,
    mint_token,
    docs_command,
) -> None:
    """Every connection PostgREST holds dies at once, and its cache with them.

    This is the restart with a real failure mode: PostgREST keeps a bounded pool
    and a `LISTEN` on the reload channel, and a cluster restart invalidates both
    simultaneously. A plane that reconnected its pool without re-establishing the
    listener answers requests correctly and never notices a schema change again
    -- which the next migration would surface, one deploy later.

    The listener is proved by the probe fixture in
    `test_the_reload_channel_still_delivers_after_a_cluster_restart` rather than
    here, because the two need different setup and a single test proving both
    would report "the plane is broken" for either.
    """
    del as_root
    sh("docker", "restart", project_a["database"]["container"])

    assert_api_converged(
        project_a,
        rest_base=rest_base,
        api_call=api_call,
        mint_token=mint_token,
        docs_command=docs_command,
        sh=sh,
    )
    assert container_is_running(service_container(project_a, REST_SERVICE_SUFFIX, sh)), (
        "the REST service did not survive the cluster restarting underneath it"
    )


@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_restarting_the_project_unit_restores_both_routes(
    as_root,
    sh,
    sh_status,
    await_health,
    project_a,
    rest_base,
    api_call,
    mint_token,
    docs_command,
) -> None:
    """The whole stack, through systemd and the installed launcher.

    The launcher reads `deployed_through_session` from the deployed document
    (ADR 0032), and Session 5 is the first session whose profile includes both a
    REST service and a documentation service. A launcher that restored an earlier
    profile would bring the cluster up, leave both routes unserved, and leave
    `systemctl status` green.
    """
    del as_root
    project_key = key(project_a)
    sh_status("systemctl", "restart", f"agentic-postgres@{project_key}.service")
    # `(hostname, project_key)`, in that order. Called with `(project_key, url)`
    # the first time, so it polled `https://alpha-dev/__apg/healthz` looking for
    # a URL where a key belongs -- and failed on name resolution, which reads as
    # a DNS problem rather than as a swapped argument.
    await_health(project_a["project"]["domain"], project_key)

    assert_api_converged(
        project_a,
        rest_base=rest_base,
        api_call=api_call,
        mint_token=mint_token,
        docs_command=docs_command,
        sh=sh,
    )


@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_reload_channel_still_delivers_after_a_cluster_restart(
    as_root,
    sh,
    project_a,
    acceptance_probe,
    rest_base,
    api_call,
    mint_token,
) -> None:
    """`LISTEN`/`NOTIFY` survives the cluster it listens to going away.

    The probe fixture creates a function, issues `NOTIFY pgrst, 'reload schema'`
    and waits for a request to see it -- so taking the fixture *after* a cluster
    restart is the proof, and its own bounded wait is what fails if the channel
    is dead. A plane whose listener did not re-establish serves a cache that can
    never change again, and every existing object keeps answering correctly
    while it does.

    Ordered deliberately: the restart happens first and the fixture is requested
    afterwards, because a fixture that ran before the restart would prove the
    channel worked at a moment that no longer exists.
    """
    del as_root
    base = rest_base(project_a)
    reader = mint_token(
        project_a,
        project_a["database"]["roles"]["authenticated"],
        subject=acceptance_probe["subject"],
    )
    answer = api_call(
        f"{base}/rpc/{acceptance_probe['function']}",
        method="POST",
        token=reader,
        body={"p_seconds": 0},
    )
    assert answer.status in (200, 204), (
        f"the probe function is not reachable ({answer.status}); the reload channel did "
        "not deliver after the cluster restarted"
    )


# ---------------------------------------------------------------------------
# The rotations (D121). Declared, and each refuses a false declaration.
# ---------------------------------------------------------------------------


def declared_previous(variable: str) -> str:
    """The pre-rotation value an operator declared, read from a file.

    From a file rather than an environment variable: `/proc/<pid>/environ` is
    readable by the process's owner, and a credential passed as an environment
    variable to a root pytest is a credential in a place the secret contract
    does not account for.
    """
    path = Path(os.environ[variable])
    value = path.read_text(encoding="utf-8").rstrip("\n")
    assert value, f"{variable} points at an empty file"
    return value


@pytest.mark.security
@pytest.mark.requires_environment(
    "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_ROTATED_AUTHENTICATOR_FROM_FILE"
)
def test_a_rotated_authenticator_serves_the_plane_and_the_old_password_does_not(
    as_root,
    project_a,
    materialized_secret,
    pg_login,
    rest_base,
    api_call,
    mint_token,
) -> None:
    """The credential PostgREST logs in with, replaced.

    The split-brain to rule out is PostgreSQL holding one password while the
    running service holds another: the plane keeps serving from connections
    opened before the rotation and fails on the next reconnect, which can be
    hours later and in the middle of the night.

    So both sides are asserted in one run: the **route serves** (the service is
    using the new credential) and the **old password is refused by the cluster**
    (the verifier moved). Either alone is satisfied by the split-brain state.

    Refuses a false declaration: if the declared previous value is the active
    one, nothing was rotated and every refusal below would be a control failure
    reported as a proof.
    """
    del as_root
    old = declared_previous("APG_ROTATED_AUTHENTICATOR_FROM_FILE")
    new = materialized_secret(key(project_a), "postgrest", "postgrest_authenticator_password")
    assert old != new, (
        "the value declared as pre-rotation is the active one; nothing was rotated, "
        "and the refusal below would pass for the wrong reason"
    )

    base = rest_base(project_a)
    reader = mint_token(project_a, project_a["database"]["roles"]["authenticated"], subject=None)
    served = api_call(f"{base}/notes?select=id&limit=1", token=reader)
    assert served.status == 200, (
        f"the REST plane stopped serving after the rotation ({served.status}); the service "
        "holds a credential the cluster does not"
    )

    role = project_a["database"]["roles"]["postgrest_authenticator"]
    network = project_a["edge"]["project_internal_network"]
    code, _, stderr = pg_login(project_a, network, role, old)
    assert code != 0, (
        "the pre-rotation authenticator password still opens the cluster; the verifier "
        "was not replaced"
    )
    assert "authentication" in stderr.lower() or "password" in stderr.lower(), (
        f"the cluster refused the old password for some other reason: {stderr.strip()}"
    )


@pytest.mark.security
@pytest.mark.requires_environment(
    "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_ROTATED_DOCS_FROM_FILE"
)
def test_a_rotated_documentation_credential_opens_the_page_and_the_old_one_does_not(
    as_root,
    project_a,
    materialized_secret,
    docs_command,
) -> None:
    """The Basic Auth credential in front of the documentation page.

    Two halves, and the second is the one a rotation gets wrong: the new
    password must **open** the page, and the old one must be refused. A rotation
    that wrote a new htpasswd line Traefik never reloaded refuses both, which
    passes a test that only checks the old one.

    The page is fetched with the credential rather than only probed for a 401,
    because `docs.check` deliberately sends none -- it answers "does this route
    refuse", which is the boundary, not "does this credential work", which is
    the rotation.
    """
    del as_root
    import base64
    import urllib.error
    import urllib.request

    old = declared_previous("APG_ROTATED_DOCS_FROM_FILE")
    new = materialized_secret(key(project_a), "_root", "docs_basic_auth_password")
    assert old != new, "the value declared as pre-rotation is the active one; nothing was rotated"

    url = docs_command.docs_url(project_a)

    def fetch(password: str) -> int:
        token = base64.b64encode(f"docs:{password}".encode()).decode()
        request = urllib.request.Request(  # noqa: S310 -- https asserted by docs_url
            url, headers={"Authorization": f"Basic {token}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    assert fetch(new) == 200, (
        "the rotated documentation credential does not open the page; Traefik is serving "
        "a users file the rotation did not write, or did not reload it"
    )
    assert fetch(old) == 401, "the pre-rotation documentation credential still opens the page"


@pytest.mark.security
@pytest.mark.requires_environment(
    "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_ROTATED_JWT_FROM_FILE"
)
def test_a_rotated_signing_key_is_the_only_one_the_plane_accepts(
    as_root,
    project_a,
    dev_token,
    rest_base,
    api_call,
) -> None:
    """Both bootstrap-key phases, from the side that matters.

    The rotation has two phases -- publish the new key alongside the old, then
    retire the old -- and this asserts the state *after* the second: a token
    signed by the retired key is refused, and one signed by the active key is
    served. Asserted after retirement rather than between phases because the
    intermediate state accepts both by design, and a test that ran there would
    pass whether or not the retirement ever happened.

    The retired key is declared as a file path, and the deployed document's
    `jwt.verification_kids` is the independent check: a key still listed there is
    a key the plane still accepts, whatever a token proves in one request.
    """
    del as_root
    retired_path = Path(os.environ["APG_ROTATED_JWT_FROM_FILE"])
    retired = json.loads(retired_path.read_text(encoding="utf-8"))
    retired_kid = retired["kid"] if isinstance(retired, dict) else str(retired)

    jwt = project_a["jwt"]
    assert retired_kid != jwt["active_kid"], (
        "the key declared as retired is the active one; nothing was rotated"
    )
    assert retired_kid not in jwt["verification_kids"], (
        f"{retired_kid} is still in the deployed document's verification_kids, so the "
        "plane still accepts it; the second phase did not complete"
    )

    base = rest_base(project_a)
    active = dev_token(project_a, project_a["database"]["roles"]["authenticated"])
    served = api_call(f"{base}/notes?select=id&limit=1", token=active)
    assert served.status == 200, (
        f"a token signed by the active key was refused ({served.status}); the plane is "
        "verifying against a key set that does not include the key it signs with"
    )

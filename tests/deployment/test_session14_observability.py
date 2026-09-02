"""`OPS-*` and `CAP-*` live halves — the metrics plane against a real deployment.

Four guarantees, and each is measured against the deployment rather than against
a checkout, because a surface that renders is not a surface that answers.

**`/metrics` is read through the edge, with the credential and without it.** A
401 proves the route exists and the middleware is attached; a 200 with the
credential proves the credential works. Both are needed and they fail
differently — Run 7 found the middleware the metrics router names was defined by
nothing, which Traefik answers with **its own 404** (D204 one route along), and a
proof that only checked for 401 would have read that as a refusal.

**A rule set is read from the store, not inferred from the file.** promtool
parsing a rendered file proves the file is well formed; only the store says the
rules were loaded and what it thinks their state is.

**The quiet half is the harder one** and it is asserted first: on a healthy
deployment the induced-failure rules must be silent. A rule that fires always is
`failed_count > 0` again (D553), and a rule that never fires is
`postgrest --ready` (D145).

**The envelope's configuration-determined numbers are checked against this
deployment.** Not its milliseconds — those describe the machine the rig ran on
and no arithmetic moves them here (ADR 0169). What must reproduce is the shape:
the pooler's limits are what the deployment's own configuration says.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, capacity, edge_credentials, runtime_override

pytestmark = [pytest.mark.p0, pytest.mark.deployment]

# A directory, not a credential. `S105` keys on the NAME, and this one
# contains `SECRET` because that is what the directory is called -- the
# values inside it never reach this module, which reads them through
# `materialized_secret`.
SECRET_ROOT = "/var/lib/agentic-postgres/secrets"  # noqa: S105

#: Which alerts an operator may induce without breaking another proof.
#:
#: **This is a property of the topology, not a preference**, and the first
#: host gate of Session 14 paid for its absence. `ApgCollectorUnreachable` is
#: induced by stopping the collector -- which is also the `/metrics` route's
#: BACKEND. Traefik's docker provider drops a router whose container is gone,
#: so the route answered **404** and four unrelated proofs failed. The alert
#: itself fired correctly; the induction was not contained.
#:
#: `ApgRouteErrorRateHigh` is inducible cleanly: PAUSE a routed backend that
#: is not the collector -- the container stays present, so the router
#: survives and Traefik answers 504 rather than removing the route.
#:
#: The three that are NOT here each break something: `ApgEdgeUnreachable`
#: needs the shared proxy stopped, which is every project's ingress;
#: `ApgStoreScrapeMissing` needs the scrape config gone, which is a hand-edit
#: to a rendered file; and `ApgCertificateExpiringSoon` needs a certificate
#: inside its window, which is not something to arrange on a live deployment.
SAFELY_INDUCIBLE = (
    "ApgRouteErrorRateHigh",
    "ApgAgentPlaneFailing",
)


def fetch(url: str, *, credential: tuple[str, str] | None = None) -> tuple[int, str]:
    """Status and body. Both, because the status alone is not the answer here.

    D768: nothing may read a 404 from `/metrics` as "metrics are not
    configured", and Traefik's own 404 is indistinguishable from a routed one
    without the body or the access log (D186, D187).
    """
    request = urllib.request.Request(url)  # noqa: S310 - https asserted by the document
    if credential is not None:
        token = base64.b64encode(f"{credential[0]}:{credential[1]}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def project_key(outputs: dict[str, Any]) -> str:
    return outputs["project"]["key"]


def declared(variable: str) -> str:
    """An operator-declared value, read from a file rather than the environment.

    `test_session5_convergence` gives the reason and it is unchanged:
    `/proc/<pid>/environ` is readable by the process's owner, so a value
    passed as an environment variable to a root pytest sits in a place the
    secret contract does not account for.
    """
    path = Path(os.environ[variable])
    value = path.read_text(encoding="utf-8").rstrip("\n")
    assert value, f"{variable} points at an empty file"
    return value


# ---------------------------------------------------------------------------
# OPS-METRIC-001 — the reserved route serves, and refuses
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_metrics_route_refuses_without_a_credential(project_a: dict[str, Any]) -> None:
    """401, and it is the route's existence that this proves.

    **A 404 here is the failure Run 7 found**: a router naming a middleware
    nothing defines is not created, and the route answers Traefik's own 404 with
    no `RouterName` in the access log. That is why this asserts 401 rather than
    "not 200" — `not 200` is satisfied by the route being absent.
    """
    url = project_a["routes"]["metrics"]["url"]
    assert url, "the deployed document names no metrics URL"

    status, _body = fetch(url)
    assert status == 401, (
        f"expected a Basic challenge, got {status}. A 404 means the router was not "
        "created -- most likely a middleware nothing defines (D204) -- and must not "
        "be read as 'metrics are not configured' (D768)"
    )


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_metrics_route_serves_this_projects_own_series(
    as_root: None, project_a: dict[str, Any], materialized_secret
) -> None:
    """200 with the credential, and the body is what decides it.

    **Discriminating on the body, never on the status** (D768). A 200 alone
    would not separate *serving this project's metrics* from *serving the
    collector's own* — ADR 0164's own measurement made that distinction with a
    control whose scrape target did not exist, and the control returned 200 with
    zero `traefik_*` series.
    """
    del as_root
    key = project_key(project_a)
    password = materialized_secret(key, "_root", "metrics_basic_auth_password")

    status, body = fetch(
        project_a["routes"]["metrics"]["url"],
        credential=(edge_credentials.METRICS_USER, password),
    )
    assert status == 200, f"the metrics credential did not open the route: {status}"

    assert "# TYPE" in body, "the body is not Prometheus exposition"
    assert body.count("\n") > 5, "the exposition is empty; the collector is serving nothing"


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS")
def test_one_projects_metrics_surface_carries_no_other_projects_series(
    as_root: None,
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    materialized_secret,
) -> None:
    """The isolation the scrape filter exists for (ADR 0167).

    Measured off-host at planning time with a prefix filter admitting twenty of
    another project's series (D774). This is that measurement against the real
    edge, where the two projects genuinely share a proxy.
    """
    del as_root
    key_a, key_b = project_key(project_a), project_key(project_b)
    password = materialized_secret(key_a, "_root", "metrics_basic_auth_password")

    status, body = fetch(
        project_a["routes"]["metrics"]["url"],
        credential=(edge_credentials.METRICS_USER, password),
    )
    assert status == 200, status

    assert key_b not in body, (
        f"project {key_a}'s metrics surface names project {key_b}. The scrape "
        "filter is admitting another project's series"
    )


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_deployed_document_reports_the_metrics_route_it_observed(
    project_a: dict[str, Any],
) -> None:
    """The document and the route agree.

    D395's shape: a route published in one document and absent from the other.
    Here the risk is narrower and worse — a status carried over rather than
    observed, which is a readiness claim about a container nobody looked at.
    """
    published = project_a["routes"]["metrics"]
    assert published["status"] in {"ready", "unavailable"}

    status, _body = fetch(published["url"]) if published["url"] else (None, "")
    if published["status"] == "ready":
        assert status == 401, (
            "the document says the metrics route is ready and it does not challenge"
        )


# ---------------------------------------------------------------------------
# OPS-ALERT-001 — a rule fires, and a healthy deployment is quiet
# ---------------------------------------------------------------------------


def store_query(key: str, expression: str) -> list[dict[str, Any]]:
    """Ask this project's store, from inside the deployment.

    The store is routed nowhere (ADR 0168), so it is reached through the
    container rather than over the edge — which is the point of it having no
    router, and the reason this needs root.
    """
    container = f"apg-{key}-{runtime_override.STORE_SERVICE}-1"
    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "wget",
            "-q",
            "-Y",
            "off",
            "-O",
            "-",
            f"http://127.0.0.1:{runtime_override.STORE_PORT}"
            f"/api/v1/query?query={urllib.parse.quote(expression)}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"could not query the store: {result.stderr}"
    return json.loads(result.stdout)["data"]["result"]


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_store_loaded_the_rules_the_release_rendered(
    as_root: None, project_a: dict[str, Any]
) -> None:
    """Read from the store, not from the file.

    promtool parsing the rendered file proves the file is well formed. Only the
    store says the rules were **loaded** — and a store that failed to load them
    reports every rule quiet, which is what a healthy deployment looks like.
    """
    del as_root
    key = project_key(project_a)
    container = f"apg-{key}-{runtime_override.STORE_SERVICE}-1"
    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "wget",
            "-q",
            "-Y",
            "off",
            "-O",
            "-",
            f"http://127.0.0.1:{runtime_override.STORE_PORT}/api/v1/rules",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    groups = json.loads(result.stdout)["data"]["groups"]
    loaded = {rule["name"] for group in groups for rule in group.get("rules", [])}
    assert loaded, "the store loaded no rules at all"

    for rule in groups[0]["rules"]:
        assert rule.get("health") == "ok", (
            f"{rule['name']} is {rule.get('health')}: {rule.get('lastError')}"
        )


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_nothing_fires_that_nobody_induced(as_root: None, project_a: dict[str, Any]) -> None:
    """**The harder half** (D70), and the one this repository has learned to demand.

    Asserted only after the store is shown to be ingesting: a quiet rule set over
    an empty store is the false quiet half, and it is indistinguishable from the
    real one by the alert query alone.

    **"Nothing is firing" is the wrong sentence, and stating it cost nothing to
    find only because it was found before a trip.** The gate runs `-m live_host`
    ONCE, and `OPS-ALERT-001` needs a failure induced in that same run -- so a
    literal quiet assertion and the firing assertion were mutually exclusive,
    and the claim could never have come back green.

    The precise sentence is *nothing is firing that nobody induced*, and it is
    **stricter** rather than weaker: it also refuses the case D784 measured,
    where inducing one failure fires a different rule, or fires two. With no
    declaration it reduces to the literal quiet half.
    """
    del as_root
    key = project_key(project_a)

    ingesting = store_query(key, "up")
    assert ingesting, (
        "the store has no `up` series, so it is scraping nothing. Every rule "
        "below would be quiet for that reason rather than because the "
        "deployment is well"
    )

    induced = set()
    if os.environ.get("APG_INDUCED_ALERT_FILE"):
        induced = {declared("APG_INDUCED_ALERT_FILE").strip()}

    firing = {row["metric"]["alertname"] for row in store_query(key, 'ALERTS{alertstate="firing"}')}
    unexplained = sorted(firing - induced)
    assert unexplained == [], f"these are firing and nobody induced them: {unexplained}" + (
        f" (declared induced: {sorted(induced)})" if induced else ""
    )


@pytest.mark.live_host
@pytest.mark.requires_environment(
    "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_INDUCED_ALERT_FILE"
)
def test_an_induced_failure_fires_its_own_rule(as_root: None, project_a: dict[str, Any]) -> None:
    """The other half, and it needs an operator to induce something.

    Declaration-gated for the reason every induced failure is: a test cannot
    stop a container and survive to report the result, and a test that could
    would be a test that mutates a deployment to prove a rule.

    The file names which alert was induced. Asserting *that* alert fired rather
    than *an* alert is the difference between proving a rule and proving the
    plane: three of these rules watch different hops, and one firing when
    another was induced is the conflation D784 measured.
    """
    del as_root
    key = project_key(project_a)
    expected = declared("APG_INDUCED_ALERT_FILE").strip()
    assert expected, "the induced-alert declaration is empty"

    # Not a refusal -- the alert may legitimately have fired for a reason
    # nobody arranged. What this catches is an induction that takes another
    # proof down with it, which is how the first host gate of this session
    # produced four failures that were about the induction rather than the
    # deployment.
    if expected not in SAFELY_INDUCIBLE:
        warnings.warn(
            f"{expected} is not in SAFELY_INDUCIBLE. Inducing it may break "
            "other proofs in this same run -- read that module constant "
            "before trusting any other failure in this gate.",
            stacklevel=2,
        )

    firing = store_query(key, 'ALERTS{alertstate="firing"}')
    names = {row["metric"]["alertname"] for row in firing}
    assert expected in names, (
        f"{expected} was declared induced and is not firing; firing now: {sorted(names)}"
    )


# ---------------------------------------------------------------------------
# OPS-REDACT-001 — nothing a caller supplied reaches the telemetry plane
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment(
    "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_SECRET_SENTINEL_FILE"
)
def test_no_planted_value_reaches_the_metrics_surface(
    as_root: None, project_a: dict[str, Any], materialized_secret
) -> None:
    """The canary, extended to the third carrier.

    Session 7's canary exists because a presigned URL reached a log line. The
    metrics surface is a third place a caller's value can arrive — as a LABEL,
    which persists and is published to every reader of the route for as long as
    the series lives (ADR 0167).
    """
    del as_root
    key = project_key(project_a)
    sentinel = declared("APG_SECRET_SENTINEL_FILE").strip()
    assert sentinel, "the sentinel declaration is empty"

    password = materialized_secret(key, "_root", "metrics_basic_auth_password")
    status, body = fetch(
        project_a["routes"]["metrics"]["url"],
        credential=(edge_credentials.METRICS_USER, password),
    )
    assert status == 200, status

    assert sentinel not in body, "the planted sentinel reached the metrics surface"
    # And the credential itself must not be echoed back by the surface it guards.
    assert password not in body, "the metrics credential appears in the metrics body"


# ---------------------------------------------------------------------------
# CAP-ENV-001 — the envelope describes THIS deployment
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_envelopes_configuration_numbers_match_this_deployment(
    as_root: None, project_a: dict[str, Any]
) -> None:
    """The half of the envelope that transfers, checked where it has to hold.

    **Not the milliseconds.** Those describe the machine the rig ran on and no
    arithmetic moves them here (ADR 0169, D794). What must reproduce is the
    configuration the limits follow from: an envelope quoting a `pool_size` this
    deployment does not have is describing a different deployment.

    This is what §7 asks for -- node ids that assert the numbers were measured
    against the thing they claim to describe, rather than a claim that goes
    green because a document exists.
    """
    del as_root
    key = project_key(project_a)
    compose_env = f"/var/lib/agentic-postgres/rendered/{key}/compose.env"
    result = subprocess.run(["cat", compose_env], capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"could not read {compose_env}"

    settings = {}
    for line in result.stdout.splitlines():
        if "=" in line and not line.startswith("#"):
            name, _, value = line.partition("=")
            settings[name.strip()] = value.strip()

    conditions = " ".join(
        condition for measurement in capacity.ENVELOPE for condition in measurement.conditions
    )
    for key_name, phrase in (
        ("PGBOUNCER_POOL_SIZE", "default_pool_size {}"),
        ("PGBOUNCER_MAX_CLIENT_CONN", "max_client_conn {}"),
        ("POSTGREST_POOL_SIZE", "PGRST_DB_POOL {}"),
    ):
        expected = phrase.format(settings[key_name])
        assert expected in conditions, (
            f"the envelope's conditions do not say {expected!r}, but this "
            f"deployment has {key_name}={settings[key_name]}. The envelope "
            "describes a different configuration from the one running"
        )


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_envelope_still_describes_the_release_this_host_runs(as_root: None) -> None:
    """The staleness guard, run where the release actually is.

    Off-host it compares the document to the checkout's lock. Here the question
    is whether the host is running what the envelope was measured against, which
    is the one place the answer can be no for a reason nobody chose.
    """
    del as_root
    result = subprocess.run(
        # `sys.executable`, never the name. The gate runs as root and
        # `python` is not on sudo's PATH -- measured, as
        # `FileNotFoundError: No such file or directory: 'python'` on the
        # first host gate of this session. The interpreter running this test
        # is the venv's, which is the one that can import the module.
        [sys.executable, str(REPO_ROOT / "bin" / "render-capacity-envelope.py"), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

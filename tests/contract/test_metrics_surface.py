"""What the metrics surface may carry, and whose it may carry (ADR 0167).

Run 4. Three properties, and each of them is a place a measurement found the
obvious implementation wrong:

* **The scrape filter is an enumeration, not a prefix.** A project key permits
  hyphens, so `alpha` and `alpha-two` are two lawful keys on one shared edge and
  `apg-alpha-.*` matches both. Measured against the locked Traefik and the
  locked collector: the prefix form admitted twenty of `alpha-two`'s series onto
  `alpha`'s surface, and the enumeration dropped every one.

* **The exposed metric name is not the name the source writes.** The collector's
  Prometheus exporter appends `_total` to a counter and expands a unit
  abbreviation into the name, so `agent.tool_call.duration` in `ms` is served as
  `agent_tool_call_duration_milliseconds`. Run 5's rules are written against the
  exposed names, so the mapping is a declared constant rather than folklore.

* **A series must be refreshed several times before it can expire.** The SDK's
  export interval defaults to 60s and the collector's `metric_expiration` was
  set to 60s, which would have had every series expiring at exactly the cadence
  it was refreshed.

The label-set and cardinality properties are here rather than in
`test_mcp_tracing.py` because a label is a different kind of thing from a span
attribute: a span attribute is written once and read by whoever holds the trace,
while a label is a SERIES -- it persists, it is published to every reader of the
route, and on a swapless host an unbounded one is an OOM (ADR 0165).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import host_config, naming, rendering, runtime_override
from app import mcp_metrics, mcp_telemetry
from app.mcp_tools import TOOL_NAMES

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# The enumeration, and the prefix it replaced
# ---------------------------------------------------------------------------


def test_the_router_enumeration_names_every_router_the_identity_carries() -> None:
    """A route that reaches `identity` and not the enumeration is invisible.

    **Question 5's shape**, and the reason this is a test rather than a comment:
    a decision gains a case and one reader does not move. Here the reader is a
    scrape filter, and it fails SILENTLY -- a router missing from the tuple is a
    route whose metrics simply never appear, which is indistinguishable from a
    route nobody used.

    Derived from `identity` rather than from a second hand-written list, so that
    adding a ninth route breaks this test rather than quietly shipping a surface
    that cannot see it.
    """
    identity = naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="fixture-alpha-dev.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
    )
    from_identity = {
        value
        for field in identity.__dataclass_fields__
        if field.endswith("_router") and isinstance(value := getattr(identity, field), str)
    }

    assert from_identity, "the identity carries no router fields; this test is measuring nothing"
    assert set(naming.project_router_names(identity.key)) == from_identity


def test_the_scrape_filter_admits_this_project_and_refuses_a_prefix_colliding_one() -> None:
    """`alpha-two` is a lawful key, and `apg-alpha-.*` matches its routers.

    The regex is evaluated the way Prometheus evaluates it -- fully anchored,
    against the source labels joined by `;` -- rather than by reading it.

    The control is the prefix form. It must still ADMIT `alpha-two`: a test in
    which both forms refuse it would be reporting the collision as fixed when
    the rig had simply stopped reproducing it.
    """
    ours = naming.project_router_names("alpha")
    theirs = naming.project_router_names("alpha-two")
    beta = naming.project_router_names("beta-project")

    enumerated = re.compile(f"^(?:{rendering._scrape_keep_regex(ours)})$")
    prefix = re.compile(r"^(?:apg-alpha-.*;.*|.*;apg-alpha-.*)$")

    def series(router: str) -> str:
        return f"{router}@docker;{router}@docker"

    # The subject keeps its own.
    for router in ours:
        assert enumerated.match(series(router)), router

    # And refuses both a plainly foreign project and the colliding one.
    for router in theirs + beta:
        assert not enumerated.match(series(router)), router

    # The control reproduces the collision, or this test proves nothing.
    assert any(prefix.match(series(router)) for router in theirs), (
        "the prefix form did not admit alpha-two; the collision this test "
        "exists for was not reproduced, so the enumeration's refusal is unmeasured"
    )


def test_a_series_carrying_neither_a_router_nor_a_service_is_dropped() -> None:
    """Traefik's own and its ENTRYPOINT families describe the shared host.

    An entrypoint is crossed by every project on this machine, so an entrypoint
    counter on a per-project surface publishes every other project's traffic in
    aggregate -- naming no other project while still describing them. Dropped
    for that reason and not for tidiness.
    """
    keep = re.compile(f"^(?:{rendering._scrape_keep_regex(naming.project_router_names('alpha'))})$")

    assert not keep.match(";")  # both labels absent
    assert not keep.match("websecure;")  # an entrypoint label is not a router


def test_a_router_name_that_could_act_as_a_regex_is_refused_not_escaped() -> None:
    """An identity is interpolated into a regex, so the charset is asserted.

    Today `_TRAEFIK_NAME` makes this unreachable. It is here because the guard
    is what turns a future identity gaining a `.` into an error rather than into
    a wildcard that silently admits other projects.
    """
    with pytest.raises(ValueError, match="may not be interpolated"):
        rendering._scrape_keep_regex(("apg-alpha-rest", "apg-.*"))


# ---------------------------------------------------------------------------
# The rendered configuration
# ---------------------------------------------------------------------------


def test_the_rendered_collector_scrapes_the_edge_by_its_registered_alias() -> None:
    """Not by container name: `edge-network.sh` says why in its own words.

    *"A container name is a formatting convention that changes between Compose
    versions"* -- which is why `edge_container` resolves Traefik by Compose
    label. A scrape target cannot resolve a label, so the attachment registers
    a name and the config spells that one.
    """
    rendered = rendering.build_otel_config(naming.project_router_names("alpha")).decode()

    assert f"{host_config.EDGE_PROXY_ALIAS}:{host_config.EDGE_METRICS_PORT}" in rendered
    assert "prometheus:" in rendered
    assert "receivers: [otlp, prometheus]" in rendered


def test_the_edge_proxy_alias_agrees_between_the_shell_and_the_module() -> None:
    """The shell cannot import the module, so the constant is written twice.

    Written twice and guarded once. Without this the two could drift and the
    symptom would be a scrape that never resolves -- a metrics surface serving
    this project's own OTLP series and silently none of its edge ones, which
    looks like a deployment nobody has sent a request to.
    """
    script = (REPO_ROOT / "bin" / "edge-network.sh").read_text(encoding="utf-8")
    declared = re.search(r"^readonly EDGE_PROXY_ALIAS='([^']+)'$", script, re.MULTILINE)

    assert declared, "bin/edge-network.sh declares no EDGE_PROXY_ALIAS"
    assert declared.group(1) == host_config.EDGE_PROXY_ALIAS


def test_the_edge_publishes_metrics_on_an_entrypoint_it_names_explicitly() -> None:
    """An unset `entryPoint` takes the whole SHARED edge down (D775).

    Measured against the locked digest with this file's own entrypoint layout:
    Traefik creates its internal `traefik` entrypoint on :8080, which is `web`
    here, and refuses to start with *"listen tcp :8080: bind: address already
    in use"*. It fails closed, which is the good half; the bad half is that the
    thing that fails is shared by every project.

    Asserted on the static configuration rather than on a running proxy because
    the consequence is a proxy that does not run.
    """
    static = (REPO_ROOT / "infra" / "edge" / "traefik.yaml").read_text(encoding="utf-8")

    assert f"entryPoint: {host_config.EDGE_METRICS_ENTRYPOINT}" in static
    assert (
        f'  {host_config.EDGE_METRICS_ENTRYPOINT}:\n    address: ":{host_config.EDGE_METRICS_PORT}"'
        in static
    )
    # Both label sets are what make a per-project surface possible at all: with
    # them off the exporter publishes seven families, every one entrypoint-scoped
    # and so attributable to no project.
    assert "addRoutersLabels: true" in static
    assert "addServicesLabels: true" in static
    assert "addEntryPointsLabels: false" in static


def test_the_metrics_entrypoint_is_not_published_to_the_host() -> None:
    """80 and 443 stay the only published ports.

    The exposition is unauthenticated, which is safe exactly as long as it is
    reachable only from the project edge networks the proxy is attached to --
    the same shape `ping` has had since Session 2.
    """
    compose = (REPO_ROOT / "infra" / "edge" / "compose.yaml").read_text(encoding="utf-8")

    assert f"{host_config.EDGE_METRICS_PORT}:" not in compose
    assert str(host_config.EDGE_METRICS_PORT) not in compose


# ---------------------------------------------------------------------------
# What a label may be
# ---------------------------------------------------------------------------


def test_no_identity_reaches_the_metrics_surface_as_a_label() -> None:
    """`RECORD_FIELDS` has eight fields and this carrier takes two.

    A span attribute is read by whoever holds the trace; a label is a SERIES,
    published to every reader of the route for as long as it lives. So the six
    that are absent are absent deliberately, and this states which and why.
    """
    assert set(mcp_metrics.METRIC_LABELS) < set(mcp_telemetry.RECORD_FIELDS)

    for forbidden in ("agent_id", "owner_id", "resource", "request_id"):
        assert forbidden not in mcp_metrics.METRIC_LABELS


def test_an_undeclared_label_value_is_folded_rather_than_published() -> None:
    """A label a caller can influence is a series a caller can create.

    On a host with no swap that is not untidiness -- it is an OOM whose victim
    the kernel picks (ADR 0165). Folded rather than dropped, because a call
    nobody counted is a worse answer than a call counted under a name that says
    it was unexpected.
    """
    assert mcp_metrics._label("query_resource", TOOL_NAMES) == "query_resource"
    assert mcp_metrics._label("../../etc/passwd", TOOL_NAMES) == mcp_metrics.LABEL_OTHER
    assert mcp_metrics._label("served", mcp_telemetry.OUTCOMES) == "served"
    assert mcp_metrics._label("anything-else", mcp_telemetry.OUTCOMES) == mcp_metrics.LABEL_OTHER


def test_the_outcome_roster_is_the_one_the_log_record_uses() -> None:
    """One list, not a second copy of it.

    `mcp_metrics` constrains a value against a roster and owns no roster, which
    is why `configure` takes both sets as arguments instead of importing them.
    """
    assert mcp_telemetry.OUTCOMES == (
        mcp_telemetry.OUTCOME_SERVED,
        mcp_telemetry.OUTCOME_REFUSED,
        mcp_telemetry.OUTCOME_FAILED,
    )


# ---------------------------------------------------------------------------
# The exposed names, and the timing that keeps them alive
# ---------------------------------------------------------------------------


def test_every_instrument_declares_what_it_is_called_on_the_surface() -> None:
    """A rule written against the source name matches nothing.

    Measured through the locked collector: a counter gains `_total`, and a unit
    abbreviation is EXPANDED into the name -- `ms` becomes `milliseconds`. Run
    5's rules are written against the right-hand side of this mapping, so a
    changed unit is a silent rename of a series something depends on.
    """
    assert mcp_metrics.EXPOSED_METRIC_NAMES == {
        "agent.tool_calls": "agent_tool_calls_total",
        "agent.tool_call.duration": "agent_tool_call_duration_milliseconds",
    }
    for source, exposed in mcp_metrics.EXPOSED_METRIC_NAMES.items():
        assert exposed.startswith(source.split(".")[0])
        assert "." not in exposed


def test_a_metric_series_is_refreshed_several_times_before_it_can_expire() -> None:
    """One property held in two processes' configuration, and nothing else
    would notice them drifting.

    The SDK's export interval defaults to 60s -- measured in its own source,
    falling back through `OTEL_METRIC_EXPORT_INTERVAL` to `60000` -- and the
    collector's expiration was set to 60s. Left that way, a series would expire
    at exactly the cadence it is refreshed and flap according to which timer
    won, taking any rule over it in and out with it.
    """
    interval = mcp_metrics.METRIC_EXPORT_INTERVAL_SECONDS
    expiration = runtime_override.OTEL_METRIC_EXPIRATION_SECONDS

    assert expiration >= interval * 4, (
        f"an expiration of {expiration}s over an export interval of {interval}s "
        "lets a live emitter's series expire between exports"
    )


def test_the_exposition_expires_a_series_whose_emitter_has_stopped() -> None:
    """The default is five minutes of a dead process reading as current.

    Measured: with the emitter stopped, the default pipeline still served its
    gauge at t+40s, while a configured collector dropped it between t+5s and
    t+10s -- so the two are distinguishable and this is a setting rather than a
    hope.
    """
    rendered = rendering.build_otel_config(naming.project_router_names("alpha")).decode()

    assert f"metric_expiration: {runtime_override.OTEL_METRIC_EXPIRATION_SECONDS}s" in rendered


# ---------------------------------------------------------------------------
# The attachment
# ---------------------------------------------------------------------------


def test_the_attachment_registers_the_alias_on_a_proxy_that_predates_it() -> None:
    """`attach` returns early on an already-attached proxy.

    Every existing deployment's endpoint predates the alias, and an alias can
    only be registered by `connect`. Without a check on the alias itself the gap
    would be SILENT and would look like success: ingress fine, scrape unable to
    resolve, and a metrics surface quietly carrying no edge series at all.
    """
    script = (REPO_ROOT / "bin" / "edge-network.sh").read_text(encoding="utf-8")

    assert "has_alias()" in script
    # Every connect registers it -- a bare `docker network connect` left
    # anywhere is an endpoint the scrape cannot resolve.
    connects = re.findall(r"docker network connect[^\n|]*", script)
    assert connects, "no `docker network connect` in edge-network.sh"
    for call in connects:
        assert "--alias" in call, f"a connect without an alias: {call.strip()}"


def test_edge_network_is_shellcheck_clean() -> None:
    """The alias handling added a branch to three code paths."""
    shellcheck = subprocess.run(
        ["shellcheck", "bin/edge-network.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if shellcheck.returncode == 127:  # pragma: no cover - not installed
        pytest.skip("shellcheck is not installed")
    assert shellcheck.returncode == 0, shellcheck.stdout

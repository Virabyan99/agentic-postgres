"""What a rule may assert, and what it must say about silence (ADR 0168).

Run 5, `OPS-ALERT-001`. The claim has two halves and the second is the harder
one: a rule fires when the failure is induced, **and a healthy deployment
produces none**. A rule that always fires is `failed_count > 0` again (D553); a
rule that never fires is `postgrest --ready` (D145).

Three properties are enforced here, and each is a place a measurement found the
obvious implementation wrong:

* **A threshold is read from the decision that owns it.** `TLS_WARN_DAYS` has
  owned "how many days before a certificate deadline matters" since Session 11,
  and a rule file spelling `21` would be a second authority on it -- one nobody
  grepping for the constant would find.

* **Every rule states what an absent series means** (D769), because a rule over
  a series that does not exist evaluates to nothing and reports healthy for
  ever. Three different things produce an absence here and they are not the same
  event.

* **The two hops have their own rules.** Measured: without `honor_labels`, the
  collector's forwarded `up` is restamped `job=collector` alongside the store's
  own, so one rule matched two series and named whichever it caught. The store
  failing to reach the collector and the collector failing to reach the proxy are
  different sentences with different remedies.

The behavioural half -- that the rules actually fire and actually stay quiet --
is proved against running containers, not here. This module guards the shape
that proof depends on.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from agentic_postgres import diagnosis, naming, rendering, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def rules() -> dict:
    return yaml.safe_load(rendering.build_alert_rules().decode())


@pytest.fixture(scope="module")
def rule_list(rules: dict) -> list[dict]:
    found = [r for group in rules["groups"] for r in group["rules"]]
    assert found, "no rules at all; every assertion below would pass vacuously"
    return found


@pytest.fixture(scope="module")
def store_config() -> dict:
    return yaml.safe_load(rendering.build_prometheus_config().decode())


@pytest.fixture(scope="module")
def store_service() -> dict:
    """The store, from the PARSED Compose model.

    Not a text slice between two service names: the first version of this
    fixture sliced to `\n  auth:` and swept up the comment block belonging to
    `auth`, so a test named "routed nowhere" failed on another service's prose
    -- and would have passed for the wrong reason had the store been last in
    the file. A structural claim is read from the structure.
    """
    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    return model["services"]["store"]


# ---------------------------------------------------------------------------
# A threshold has one owner
# ---------------------------------------------------------------------------


def test_the_certificate_threshold_is_the_one_the_doctor_already_owns(
    rule_list: list[dict],
) -> None:
    """`diagnosis.TLS_WARN_DAYS`, rendered rather than spelled.

    ADR 0167's rule applied inside a rule file: a metric reads from the decision
    that owns its value, and so does a threshold. 21 days is not arbitrary --
    Let's Encrypt renews at 30 days remaining, so it means "renewal should
    already have happened and did not" rather than "renewal is due". A rule file
    with a literal `21` would be a second authority on that sentence.
    """
    cert = next(r for r in rule_list if r["alert"] == "ApgCertificateExpiringSoon")
    assert f"< {diagnosis.TLS_WARN_DAYS}" in cert["expr"]

    # **The assertion above is not enough on its own, and a mutation proved it.**
    # Replacing the rendered constant with the literal `21` produced an
    # identical rule and the test stayed green, because TLS_WARN_DAYS happens to
    # BE 21 -- a test comparing two constants is not testing the thing between
    # them. So move the constant and require the rule to follow it.
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(diagnosis, "TLS_WARN_DAYS", 9)
        moved = yaml.safe_load(rendering.build_alert_rules().decode())
    finally:
        monkeypatch.undo()

    followed = next(
        r
        for group in moved["groups"]
        for r in group["rules"]
        if r["alert"] == "ApgCertificateExpiringSoon"
    )
    assert "< 9" in followed["expr"], (
        "the rule did not follow TLS_WARN_DAYS; it is a second authority on the "
        "threshold rather than a reader of it"
    )
    assert "21" not in followed["expr"]


def test_no_rule_spells_a_threshold_that_has_an_owner_elsewhere(rule_list: list[dict]) -> None:
    """The guard against the previous test being satisfied by coincidence.

    If `TLS_WARN_DAYS` ever moves and one rule is rendered while another was
    hand-written to the old value, the first test still passes. This one refuses
    any *other* appearance of the old literal in an expression.
    """
    for rule in rule_list:
        if rule["alert"] == "ApgCertificateExpiringSoon":
            continue
        assert not re.search(r"\b21\b", rule["expr"]), (
            f"{rule['alert']} spells 21, which is TLS_WARN_DAYS' value"
        )


# ---------------------------------------------------------------------------
# Silence has a stated meaning
# ---------------------------------------------------------------------------


def test_every_rule_says_what_an_absent_series_means() -> None:
    """D769, enforced rather than remembered.

    A rule over a series that does not exist evaluates to nothing and reports
    healthy for ever, and three different things produce an absence here: the
    series was never published, nothing has happened yet, and the emitter
    stopped. A rule that does not say which it means cannot be read correctly by
    whoever is woken by it -- and this repository has shipped both failure modes
    already, in `failed_count > 0` and in `postgrest --ready`.

    Asserted over the rendered text rather than the parsed document, because the
    statement lives in a comment: it is for the person reading the file on the
    host, which is where a rule is read when it matters.
    """
    rendered = rendering.build_alert_rules().decode()
    blocks = rendered.split("      - alert: ")
    assert len(blocks) > 1, "no alert blocks found; this test would pass vacuously"

    # The comment precedes its rule, so each rule's prose is the tail of the
    # block before it.
    for name, preceding in zip(
        [b.split("\n", 1)[0].strip() for b in blocks[1:]], blocks[:-1], strict=True
    ):
        assert "ABSENT SERIES:" in preceding, f"{name} does not say what an absent series means"


def test_the_two_hops_have_their_own_rules(rule_list: list[dict]) -> None:
    """Measured: one `up` rule named the wrong subject.

    Without `honor_labels`, the collector's forwarded `up{job="edge"}` is
    restamped `job=collector` beside the store's own, so `up{job="collector"} ==
    0` matched both and reported "the store cannot reach the collector" when the
    truth was "the collector cannot reach the proxy". Two states, one signal --
    D145's family, and the remedy for each is different.
    """
    by_name = {r["alert"]: r["expr"] for r in rule_list}

    assert 'up{job="collector"} == 0' in by_name["ApgCollectorUnreachable"]
    assert 'up{job="edge"} == 0' in by_name["ApgEdgeUnreachable"]
    # And the absence of the whole scrape config, which is neither of those --
    # measured: a stopped target makes `up` 0, not absent.
    assert 'absent(up{job="collector"})' in by_name["ApgStoreScrapeMissing"]


def test_the_store_keeps_the_labels_its_targets_arrived_with(store_config: dict) -> None:
    """`honor_labels`, and it is what makes the rule above possible.

    The collector is a carrier rather than an origin: most of what it serves was
    scraped from the proxy or pushed by the agent plane, each already carrying
    its own `job`. Without this, every hop collapses into one name.
    """
    scrape = store_config["scrape_configs"][0]
    assert scrape["honor_labels"] is True
    assert scrape["job_name"] == "collector"


# ---------------------------------------------------------------------------
# What is deliberately absent
# ---------------------------------------------------------------------------


def test_no_rule_is_written_over_a_metric_no_deployment_publishes(rule_list: list[dict]) -> None:
    """Run 4 did not build backup, WAL, disk, pooler or connection metrics.

    Each was left out for a reason recorded there -- a second source for a value
    that has one, or a sixth claimant on `max_connections`. **A rule over a
    series nothing publishes is silent in exactly the way a healthy deployment
    is**, so writing one would produce a rule set that looks complete and
    measures a fraction of what it names. That is the more dangerous half of
    `OPS-ALERT-001`, and it is refused here rather than trusted to review.
    """
    unpublished = (
        "pgbackrest",
        "backup_state",
        "wal_",
        "pg_stat_archiver",
        "disk_",
        "pgbouncer",
        "pg_stat_activity",
        "max_connections",
    )
    for rule in rule_list:
        for name in unpublished:
            assert name not in rule["expr"], (
                f"{rule['alert']} reads {name!r}, which no deployment publishes; "
                "it would be silent for ever and look healthy"
            )


def test_nothing_pages_anybody(store_config: dict) -> None:
    """Plan section 4.4, enforced.

    A rule with no measured false-positive rate is not a rule anybody should be
    woken by. There is no Alertmanager in this deployment and no receiver
    configured; routing an alert to a human is a later decision, taken once the
    rules have run somewhere long enough to have a rate.
    """
    assert "alerting" not in store_config
    rendered = rendering.build_prometheus_config().decode()
    assert "alertmanager" not in rendered.lower()


def test_the_store_originates_no_connection_off_the_host(store_service: dict) -> None:
    """ADR 0147's residual is not widened.

    The database container's egress is this deployment's one named way out. A
    store with `remote_write` would be a second, and it would carry every series
    this project produces to wherever it was pointed.
    """
    rendered = rendering.build_prometheus_config().decode()
    for forbidden in ("remote_write", "remote_read"):
        assert forbidden not in rendered


# ---------------------------------------------------------------------------
# The store's shape
# ---------------------------------------------------------------------------


def test_the_store_is_routed_nowhere(store_service: dict) -> None:
    """It answers arbitrary queries over this project's whole metric history.

    ADR 0164 published the COLLECTOR at the edge precisely so this never has to
    be reachable from outside the deployment. A `traefik.` label here would make
    a query interface sit behind one password.
    """
    labels = store_service.get("labels", {})
    assert not any("traefik" in key for key in labels), (
        f"the store carries a Traefik label; it must be routed nowhere: {sorted(labels)}"
    )
    # The edge constrains discovery on this label, so its ABSENCE is what keeps
    # the store invisible to Traefik even if a router were defined by accident.
    assert "apg.traefik.scope" not in labels

    # And nothing may enable an admin surface on the port it does listen on.
    assert not any("enable-admin-api" in arg for arg in store_service.get("command", []))
    assert not any("remote-write-receiver" in arg for arg in store_service.get("command", []))


def test_the_store_carries_an_explicit_memory_limit(store_service: dict) -> None:
    """ADR 0165. A telemetry component sizes itself from the machine it lands on.

    Unbounded on a 7.8 GB rig, a store sizes its caches to a share of that
    machine; on the 3,814 MB host with no swap, the kernel picks the victim.
    """
    assert store_service["mem_limit"] == f"{runtime_override.STORE_MEMORY_LIMIT_MIB}m"


def test_the_store_holds_no_credential(store_service: dict) -> None:
    """It scrapes one target, on this project's own network, over plain HTTP.

    The edge credential guards the ROUTE in front of the collector, and nothing
    in the metrics plane holds it (ADR 0164). A store with `environment:` or
    `secrets:` would be the first thing here that did.
    """
    assert "environment" not in store_service
    assert "secrets" not in store_service


def test_the_store_scrapes_the_collector_by_its_service_name(store_config: dict) -> None:
    """One target, derived from the constant that names the collector service."""
    targets = store_config["scrape_configs"][0]["static_configs"][0]["targets"]
    assert targets == [f"{runtime_override.METRICS_SERVICE}:{runtime_override.OTEL_EXPORTER_PORT}"]


def test_the_stores_volume_is_derived_like_every_other_identity() -> None:
    """ADR 0002. Per project, because two projects sharing a store would be the
    one place their metrics met -- the shape ADR 0164 refused deliberately."""
    assert naming.store_volume_name("alpha") == "apg-alpha-store"
    assert naming.store_volume_name("alpha") != naming.store_volume_name("alpha-two")


def test_a_rules_evaluation_keeps_pace_with_its_data(store_config: dict) -> None:
    """Evaluating faster than data arrives advances a `for:` clock against no
    new evidence; slower delays every alert for nothing."""
    assert (
        store_config["global"]["evaluation_interval"] == store_config["global"]["scrape_interval"]
    )


def test_a_rule_waits_more_than_one_scrape_before_firing(rule_list: list[dict]) -> None:
    """One evaluation would make any momentary blip an alert."""
    assert runtime_override.ALERT_FOR_SECONDS > runtime_override.STORE_SCRAPE_INTERVAL_SECONDS
    for rule in rule_list:
        assert rule["for"] == f"{runtime_override.ALERT_FOR_SECONDS}s"

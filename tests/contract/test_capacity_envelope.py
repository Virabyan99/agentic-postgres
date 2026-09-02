"""What an envelope may claim, and what it must admit (ADR 0169).

Run 6, `CAP-ENV-001`. §7 of the session plan names this **the claim most at risk
of being reported dishonestly**: *"An envelope is a document, and a claim over a
document can go green because the document exists."*

So none of these tests asks whether the document exists. They ask:

* whether every number carries the conditions it was sampled under (D593, D603);
* whether every number says whether it **transfers** — a limit that follows from
  `pool_size` holds anywhere, a figure in milliseconds describes one machine;
* whether the document is still about the release it was measured against, which
  is the guard that stops it floating free (D700's shape, before the fact);
* and whether it still admits what was **not** measured. The day `UNMEASURED` is
  empty is a claim in itself, and it must not be made by omission.

The behavioural half — that the numbers are what a running deployment does — was
measured against the pinned images in rigs. This module guards the honesty of the
document that reports them.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_postgres import capacity

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = REPO_ROOT / "docs" / "capacity-envelope.md"
RENDERER = REPO_ROOT / "bin" / "render-capacity-envelope.py"


# ---------------------------------------------------------------------------
# A number carries its conditions
# ---------------------------------------------------------------------------


def test_every_measurement_states_the_conditions_it_was_sampled_under() -> None:
    """D593 and D603, enforced at construction rather than remembered.

    `process-max` is 1, so a restore is ~1,330 serialised S3 round trips and any
    RTO figure is a sample from a band. A latency without its concurrency, its
    transaction duration and its machine is a number about nothing — and it is
    exactly the kind of number a document makes look authoritative.
    """
    assert capacity.ENVELOPE, "no measurements; every assertion here would pass vacuously"

    for measurement in capacity.ENVELOPE:
        assert measurement.conditions, measurement.subject
        assert measurement.value.strip(), measurement.subject


def test_a_measurement_with_no_conditions_cannot_be_constructed() -> None:
    """The rule above is a constructor invariant, not a review note.

    A conditionless measurement is refused where it is written, so it cannot
    reach the document and be caught later by a test somebody might skip.
    """
    with pytest.raises(ValueError, match="a number about nothing"):
        capacity.Measurement(
            subject="something",
            value="42 ms",
            kind=capacity.MACHINE,
            conditions=(),
        )


def test_every_measurement_declares_whether_it_transfers() -> None:
    """The distinction the envelope turns on, and the one usually got wrong.

    D770 is the standing instance: a store measured 63 MB and rising on a 7.8 GB
    rig and 45.6 MB under a real cap, because an unbounded component sizes itself
    from the machine it lands on. **A number measured off-host and quoted for the
    host describes the wrong machine**, and the only defence is that each number
    says which kind it is.
    """
    for measurement in capacity.ENVELOPE:
        assert measurement.kind in (capacity.CONFIGURATION, capacity.MACHINE)

    kinds = {m.kind for m in capacity.ENVELOPE}
    assert capacity.MACHINE in kinds, (
        "no measurement is marked as machine-determined. Either the envelope has "
        "stopped reporting latency, or something that does not transfer is being "
        "presented as though it does"
    )
    assert capacity.CONFIGURATION in kinds


def test_a_machine_measurement_names_the_machine_it_describes() -> None:
    """The structural half, and the one that cannot be satisfied by wording.

    A number that does not transfer is only readable if the reader knows what it
    is about. So a `MACHINE` measurement must name its machine among its
    conditions, and a `CONFIGURATION` one must not claim a machine at all —
    because that is the sentence a later reader would quote for the host.

    This replaced a scan over the measurement's prose, which could not tell a
    STIPULATED duration ("each request holds a connection for 500 ms" — an
    input) from an OBSERVED latency ("p50 476 ms" — an output). That was D464's
    shape: a text scan standing in for a construct.
    """
    for measurement in capacity.ENVELOPE:
        names_a_machine = any(
            "development machine" in condition or "deployment host" in condition
            for condition in measurement.conditions
        )
        if measurement.kind == capacity.MACHINE:
            assert names_a_machine, (
                f"{measurement.subject!r} does not transfer but names no machine; "
                "a number nobody can attribute is a number that gets quoted for "
                "the wrong one"
            )
        else:
            assert not names_a_machine, (
                f"{measurement.subject!r} claims to transfer while naming a "
                "specific machine among its conditions"
            )


def test_an_observed_latency_is_not_claimed_to_transfer() -> None:
    """The narrowed scan, kept beside the structural test for one mistake.

    A latency is the most quotable number in the document and the least
    transferable, so marking one `CONFIGURATION` would publish a development
    machine's speed as the deployment's. Narrowed to the markers this envelope
    writes an OBSERVED latency with, rather than to any appearance of `ms` —
    which also appears in the stipulated durations that are inputs.

    It is still a text scan standing in for a construct (D464), and the test
    above is the construct.
    """
    for measurement in capacity.ENVELOPE:
        if measurement.kind != capacity.CONFIGURATION:
            continue
        assert not re.search(r"\bp50\b|\bp95\b|percentile", measurement.value), (
            f"{measurement.subject!r} is marked as transferring but quotes an "
            "observed latency, which describes the machine it was measured on"
        )


# ---------------------------------------------------------------------------
# The document is about the release
# ---------------------------------------------------------------------------


def test_the_envelope_is_current() -> None:
    """`--check`, run. Not "the file exists".

    This is the whole of §7's warning: a claim over a document goes green
    because the document exists. The renderer's own check is what distinguishes
    a current envelope from a file somebody left behind.
    """
    result = subprocess.run(
        [sys.executable, str(RENDERER), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_moved_image_makes_the_envelope_stale() -> None:
    """The guard, exercised rather than asserted.

    **Not hypothetical**: `traefik:v3.7` moved twice inside Session 14, three
    days apart (D787). An envelope that floats free of the release it describes
    is D700's stale `backup_state` in a new place — that one published `failing`
    for every project and survived two sessions because it failed safe.
    """
    recorded = capacity.locked_digests()
    assert capacity.stale_against(recorded) == ()

    moved = {**recorded, "POSTGREST_IMAGE": "docker.io/postgrest/postgrest@sha256:" + "0" * 64}
    assert capacity.stale_against(moved) == ("POSTGREST_IMAGE",)


def test_the_renderer_refuses_a_document_whose_images_have_moved() -> None:
    """The guard's WIRING, which is the half that goes untested.

    `stale_against` being right is not the same claim as the command using it.
    A mutation that disabled the call inside `--check` left every other test in
    this module green, because they all exercised the function directly --
    question 5, and the unproved caller was the only thing a gate ever runs.

    The document is restored in a `finally`, and the restoration is verified,
    because a test that leaves a planted digest behind would make every later
    run in the same session fail for a reason nobody planted.
    """
    original = DOCUMENT.read_text(encoding="utf-8")
    marker = "- `POSTGREST_IMAGE` = `"
    line = next(ln for ln in original.splitlines() if ln.startswith(marker))
    planted = marker + "docker.io/postgrest/postgrest@sha256:" + "0" * 64 + "`"

    try:
        DOCUMENT.write_text(original.replace(line, planted), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(RENDERER), "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 5, (
            "the renderer accepted a document describing an image that has moved; "
            f"exit was {result.returncode}"
        )
        # And it must NAME the image. "Stale" sends a reader looking; the image
        # name sends them to the measurement that is now about a past version.
        assert "POSTGREST_IMAGE" in result.stderr, result.stderr
    finally:
        DOCUMENT.write_text(original, encoding="utf-8")

    assert DOCUMENT.read_text(encoding="utf-8") == original


def test_an_image_missing_from_the_document_is_stale_not_current() -> None:
    """An absent digest must not read as an unchanged one.

    D600's shape: a `null` that looks measured is worse than an absent field,
    because `or {}` turned a missing block into a value and wrote it into every
    drill document. Here the missing case is the one that would silently pass.
    """
    partial = {k: v for k, v in capacity.locked_digests().items() if k != "PGBOUNCER_IMAGE"}
    assert "PGBOUNCER_IMAGE" in capacity.stale_against(partial)


def test_the_envelope_pins_only_what_it_measured() -> None:
    """Three images, not the whole lock.

    An envelope that went stale when any unrelated image moved would cry wolf,
    and this repository has a rolling-tag drift that moves three images roughly
    weekly (D540, D787). Pinning nothing would never go stale at all.
    """
    assert set(capacity.MEASURED_AGAINST) == {
        "POSTGRES_IMAGE",
        "PGBOUNCER_IMAGE",
        "POSTGREST_IMAGE",
    }
    assert "TRAEFIK_IMAGE" not in capacity.MEASURED_AGAINST


# ---------------------------------------------------------------------------
# What it admits
# ---------------------------------------------------------------------------


def test_the_envelope_still_says_what_it_did_not_measure() -> None:
    """The honest half, and the one an envelope loses first.

    A document silently missing the scenarios nobody could run reads as a
    document about the whole system. **The day this list is empty is a claim in
    itself** and must be made deliberately, not by deletion.
    """
    assert capacity.UNMEASURED, (
        "the envelope claims everything the plan asked for was measured. MCP "
        "round trips, backup under load and the deployment's own numbers each "
        "need a host; if that has genuinely happened, this test is the place to "
        "say so"
    )
    for item in capacity.UNMEASURED:
        assert item.reason.strip(), item.subject
        assert item.unblocked_by.strip(), item.subject


def test_the_unmeasured_list_names_the_scenarios_the_plan_asked_for() -> None:
    """Run 6's own text: pooled clients, REST, MCP, and backup under load.

    Two of the four were measured. The other two must be named as absent, by
    subject rather than by a general apology — a reader looking for the MCP
    round trip needs to find the word.
    """
    absent = " ".join(
        item.subject.lower() + " " + item.reason.lower() for item in capacity.UNMEASURED
    )
    for subject in ("mcp", "backup"):
        assert subject in absent, f"{subject} was not measured and is not declared absent"


def test_nothing_was_tuned_on_an_off_host_measurement() -> None:
    """The plan asks for tuning after the load scenarios, and this run did none.

    Deliberate, and stated: changing `pool_size` or `query_wait_timeout` on the
    strength of a development machine's latency would be tuning the deployment
    to a measurement that is not about it — ADR 0065/0066's shape, where a
    result reached by a route the product does not take proves the end state is
    reachable rather than that the product reaches it.
    """
    tuning = " ".join(item.subject.lower() for item in capacity.UNMEASURED)
    assert "tuning" in tuning, (
        "the envelope no longer records that nothing was tuned. If a setting was "
        "changed on measured evidence, say which and on what evidence"
    )


def test_the_document_names_the_deployment_host_as_a_different_machine() -> None:
    """Read from the rendered document, because that is what a person reads.

    The module could be right while the renderer dropped the qualification, and
    the document is where the number gets quoted from.
    """
    text = DOCUMENT.read_text(encoding="utf-8")
    assert "3,814 MB" in text
    assert "Does not transfer" in text
    assert "What was not measured" in text

"""`DEP-PRE-001` — a refusal lists every absent item, and never invents one.

These are behavioural, not source-level, and that is the point of ADR 0157's
split: `bin/deploy-project.py` needs root, so every existing test of it is a text
scan over its source. `agentic_postgres.preflight` runs anywhere, so the
assertions here are about what the code *produces* rather than which names appear
in it (D277).

The end-to-end half — that a refused deploy has written nothing to the
filesystem — is a host-mode proof and belongs to Run 9. What is provable offline
is that the report is complete, that the verdicts are honest, and that the exit
code an absence maps to has not moved.
"""

from __future__ import annotations

import pytest

from agentic_postgres import preflight

pytestmark = [pytest.mark.contract, pytest.mark.p0]

HOST = "host.yaml"
PROJECT = "project.alpha.yaml"
STACK = "apg-edge"


def everything_present() -> tuple[preflight.Prerequisite, ...]:
    daemon = preflight.docker_daemon(reachable=True, timed_out=False)
    return (
        daemon,
        preflight.edge_plane(
            daemon=daemon,
            running_names=("apg-edge-traefik", "apg-alpha-dev-postgres"),
            stack_name=STACK,
            host_manifest=HOST,
        ),
        preflight.provider_bootstrap(
            error="",
            state_path="/etc/x/bootstrap-state.json",
            host_manifest=HOST,
            project_manifest=PROJECT,
        ),
        preflight.secret_generation(
            error="", generation_id="gen-0007", project_manifest=PROJECT, session=11
        ),
    )


def nothing_present() -> tuple[preflight.Prerequisite, ...]:
    """The daemon is refused, and the two filesystem reads fail on their own."""
    daemon = preflight.docker_daemon(
        reachable=False, timed_out=False, error="Cannot connect to the Docker daemon"
    )
    return (
        daemon,
        preflight.edge_plane(daemon=daemon, running_names=(), stack_name=STACK, host_manifest=HOST),
        preflight.provider_bootstrap(
            error="bootstrap state is missing",
            state_path="/etc/x/bootstrap-state.json",
            host_manifest=HOST,
            project_manifest=PROJECT,
        ),
        preflight.secret_generation(
            error="no active generation pointer",
            generation_id="",
            project_manifest=PROJECT,
            session=11,
        ),
    )


# ---------------------------------------------------------------------------
# "lists every absent item"
# ---------------------------------------------------------------------------


def test_a_refusal_names_every_item_that_is_not_satisfied() -> None:
    """The half of DEP-PRE-001 that today's fail-one-at-a-time code cannot meet.

    Three round trips on a host where each needs sudo at a TTY is the cost this
    replaces, so the assertion is on the count, not on any one line.
    """
    checks = nothing_present()
    stopped = preflight.blocking(checks)
    assert len(stopped) == 4, f"expected all four to block, got {[c.name for c in stopped]}"

    text = preflight.report(checks)
    for item in checks:
        assert item.name in text, f"{item.name} is absent from the report"


def test_every_absent_item_carries_the_command_that_supplies_it() -> None:
    """An operator should not have to look one up. Undetermined items are
    exempt, and that exemption is asserted separately below."""
    for item in nothing_present():
        if item.verdict == preflight.ABSENT:
            assert item.remedy, f"{item.name} is absent and names no remedy"
            assert item.remedy in preflight.report((item,))


def test_the_remedies_name_the_manifests_the_deploy_was_invoked_with() -> None:
    """Not a `<manifest>` placeholder, which is what the current messages print.

    A copy-pasteable command is the difference between one round trip and two.
    """
    text = preflight.report(nothing_present())
    assert f"--host {HOST}" in text
    assert f"--project {PROJECT}" in text
    assert "<manifest>" not in text


def test_a_satisfied_prerequisite_is_reported_and_does_not_block() -> None:
    checks = everything_present()
    assert preflight.blocking(checks) == ()
    assert preflight.exit_kind(checks) is None

    text = preflight.report(checks)
    assert "all 4 prerequisites are satisfied" in text
    assert "MISSING" not in text
    assert "UNKNOWN" not in text


# ---------------------------------------------------------------------------
# The honest verdict — ADR 0157's reason for existing
# ---------------------------------------------------------------------------


def test_the_edge_is_undetermined_when_the_daemon_could_not_be_asked() -> None:
    """D600's family, caught before it shipped.

    `running_names` is empty when the daemon is unreachable, for a reason that
    has nothing to do with the edge plane. A boolean check would read that
    emptiness as an absence and print a sentence about a container nobody looked
    at — then send an operator to restart a stack that may be running.
    """
    daemon = preflight.docker_daemon(reachable=False, timed_out=False, error="nope")
    edge = preflight.edge_plane(
        daemon=daemon, running_names=(), stack_name=STACK, host_manifest=HOST
    )

    assert edge.verdict == preflight.UNDETERMINED, (
        "an unreachable daemon must not produce a claim about the edge plane"
    )
    assert "not checked" in edge.detail
    assert edge.blocks, "an unverified prerequisite must still stop the deploy"


def test_an_undetermined_item_offers_no_remedy_of_its_own() -> None:
    """The fix is whatever it depended on. A command printed beside a check that
    never ran invites an operator to act on a diagnosis nobody made."""
    daemon = preflight.docker_daemon(reachable=False, timed_out=False, error="nope")
    edge = preflight.edge_plane(
        daemon=daemon, running_names=(), stack_name=STACK, host_manifest=HOST
    )
    assert edge.remedy is None
    assert "supply it with" not in preflight.report((edge,))


def test_a_timeout_and_a_refusal_are_different_verdicts() -> None:
    """D631. A daemon that ACCEPTED the connection is very likely running, and
    "start Docker" is the wrong instruction for one that is wedged."""
    refused = preflight.docker_daemon(reachable=False, timed_out=False, error="connection refused")
    wedged = preflight.docker_daemon(reachable=False, timed_out=True)

    assert refused.verdict == preflight.ABSENT
    assert wedged.verdict == preflight.UNDETERMINED
    assert refused.remedy is not None
    assert wedged.remedy is None
    assert str(preflight.DAEMON_TIMEOUT_SECONDS) in wedged.detail


def test_an_unreadable_state_file_is_undetermined_rather_than_absent() -> None:
    """D636, found by running the thing rather than by reading it.

    `Path.exists()` swallows ENOENT and **raises** EACCES. The secret root is
    `0700 root`, so an unprivileged caller gets EACCES for a generation that is
    present and perfectly healthy. Calling that an absence would send an operator
    to re-run `materialize-secrets.sh` against a generation already there — and
    re-materialising is not free, because it writes a new one.
    """
    unreadable = preflight.secret_generation(
        error="/var/lib/.../active-secret-generation.json could not be read: [Errno 13]",
        generation_id="",
        project_manifest=PROJECT,
        session=11,
        readable=False,
    )
    assert unreadable.verdict == preflight.UNDETERMINED
    assert unreadable.remedy is None
    assert "not checked" in unreadable.detail

    missing = preflight.secret_generation(
        error="no active generation pointer",
        generation_id="",
        project_manifest=PROJECT,
        session=11,
        readable=True,
    )
    assert missing.verdict == preflight.ABSENT, "a genuinely absent pointer is still an absence"
    assert missing.remedy is not None


def test_an_unreadable_bootstrap_state_is_undetermined_rather_than_absent() -> None:
    """The same distinction, on the other filesystem read. Both are `0700 root`."""
    unreadable = preflight.provider_bootstrap(
        error="[Errno 13] Permission denied",
        state_path="/etc/x/bootstrap-state.json",
        host_manifest=HOST,
        project_manifest=PROJECT,
        readable=False,
    )
    assert unreadable.verdict == preflight.UNDETERMINED
    assert unreadable.remedy is None


def test_the_filesystem_checks_still_report_when_the_daemon_is_down() -> None:
    """The reason the report is worth aggregating at all.

    A bootstrap state and a secret generation are filesystem reads: they need
    nothing from the daemon, so a daemon-down run can still tell an operator
    about both instead of stopping at the first failure.
    """
    checks = nothing_present()
    named = {item.name: item for item in checks}
    assert named["provider bootstrap"].verdict == preflight.ABSENT
    assert named["secret generation"].verdict == preflight.ABSENT


# ---------------------------------------------------------------------------
# The exit code has not moved
# ---------------------------------------------------------------------------


def test_a_daemon_absence_still_maps_to_the_prerequisite_code() -> None:
    """ADR 0157: the aggregate reproduces the code each cause produces today, so
    no caller's contract moves. `require_edge_is_up` exits 3 for an unreachable
    daemon and 4 for a stopped edge, and both are preserved."""
    assert preflight.exit_kind(nothing_present()) == preflight.KIND_PREREQUISITE


def test_a_precondition_absence_maps_to_the_precondition_code() -> None:
    daemon = preflight.docker_daemon(reachable=True, timed_out=False)
    checks = (
        daemon,
        preflight.edge_plane(daemon=daemon, running_names=(), stack_name=STACK, host_manifest=HOST),
        preflight.provider_bootstrap(
            error="", state_path="/etc/x", host_manifest=HOST, project_manifest=PROJECT
        ),
        preflight.secret_generation(
            error="", generation_id="g", project_manifest=PROJECT, session=11
        ),
    )
    assert preflight.exit_kind(checks) == preflight.KIND_PRECONDITION


def test_the_exit_kind_follows_the_first_blocker_not_the_last() -> None:
    """The items are ordered as the deploy needs them, so the first blocker is
    the one whose absence explains the rest."""
    checks = nothing_present()
    assert checks[0].name == "docker daemon"
    assert preflight.exit_kind(checks) == checks[0].kind


# ---------------------------------------------------------------------------
# The report itself
# ---------------------------------------------------------------------------


def test_the_report_says_nothing_has_been_changed() -> None:
    """The claim an operator most needs from a refusal, and the one step 0's
    position in `main()` is what makes true."""
    assert "Nothing has been changed" in preflight.report(nothing_present())


def test_a_multi_line_error_is_collapsed_to_one_row() -> None:
    """A daemon's stderr arrives multi-line. A report whose rows wrap is one an
    operator stops reading."""
    item = preflight.docker_daemon(
        reachable=False, timed_out=False, error="line one\nline two\n  line three"
    )
    assert "\n" not in item.detail
    assert item.detail == "line one line two line three"


def test_a_very_long_error_is_bounded() -> None:
    item = preflight.docker_daemon(reachable=False, timed_out=False, error="x" * 500)
    assert len(item.detail) <= 200
    assert item.detail.endswith("...")


def test_the_deploy_runs_the_preflight_before_it_renders() -> None:
    """Source-level, and labelled as such (the house pattern for this file).

    The behavioural proof that a refused deploy wrote nothing is host-mode and
    belongs to Run 9. What is checkable here is the ordering that makes it
    possible: step 0 must appear before the render, or the check is decorative.
    """
    from agentic_postgres import REPO_ROOT

    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    body = source.split("def main(")[1]
    preflight_at = body.index("observe_prerequisites(")
    render_at = body.index('step("1. Render')
    assert preflight_at < render_at, (
        "the preflight runs after the render; it changes nothing only if it runs first"
    )

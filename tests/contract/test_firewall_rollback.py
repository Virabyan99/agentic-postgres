"""Enabling the firewall is gated on an armed rollback, exactly as SSH is.

``ufw --force enable`` with ``default deny incoming`` is the second of the two
steps in this repository that can strand an operator on a remote host, and it is
the one that is easy to forget is dangerous — the allow rules are already in
place by the time it runs, so it *looks* like a formality. It is not: a wrong
SSH port in the manifest, a rule that did not apply, or an interface the rules
do not cover all produce a host that answers nothing.

The implementation plan §3.2 requires the same arm/verify/disarm cycle SSH gets,
and §3 adds a rule that is easy to violate by accident: never two armed windows
at once. With both timers pending, a lost connection gives no way to tell which
change caused it, and the two rollbacks fire in an order nobody chose.

These are static assertions about the script's shape. The behaviour they guard
only manifests on a host, in the one situation where nobody is watching.
"""

from __future__ import annotations

import subprocess

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

SCRIPT = REPO_ROOT / "bin" / "provision-host.sh"


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def apply_body(source: str) -> str:
    return source.split("apply_baseline()", 1)[1]


@pytest.fixture(scope="module")
def firewall_body(apply_body: str) -> str:
    """Just the firewall section.

    Scoped deliberately. ``ufw_rollback_is_armed`` also appears in the
    both-armed guard at the top of ``apply_baseline``, so an ordering assertion
    made against the whole function passes on that earlier occurrence no matter
    where the real check sits — which it did, on the first run of this file.
    """
    banner = "== firewall =="
    assert banner in apply_body, "the firewall section is no longer labelled"
    return apply_body.split(banner, 1)[1]


def test_enable_is_guarded_by_an_arming_check(firewall_body: str) -> None:
    """`ufw --force enable` must not be reachable without the guard."""
    assert "ufw --force enable" in firewall_body
    assert "ufw_rollback_is_armed" in firewall_body, (
        "enabling the firewall checks no rollback timer"
    )
    assert firewall_body.index("ufw_rollback_is_armed") < firewall_body.index(
        "ufw --force enable"
    ), "the firewall is enabled before the arming check runs"


def test_allow_rules_precede_default_deny_which_precedes_enable(firewall_body: str) -> None:
    """The classic lockout is ordering, not gating: deny before allow."""
    allow_ssh = firewall_body.index('ufw allow "${ssh_port}/tcp"')
    default_deny = firewall_body.index("ufw default deny incoming")
    enable = firewall_body.index("ufw --force enable")
    assert allow_ssh < default_deny < enable


def test_it_refuses_to_enable_without_a_rule_covering_the_ssh_port(firewall_body: str) -> None:
    guard = firewall_body.index("refusing to enable the firewall")
    assert guard < firewall_body.index("ufw --force enable")


def test_the_ssh_rule_guard_reads_configured_rules_not_running_ones(firewall_body: str) -> None:
    """`ufw status` lists nothing while ufw is inactive.

    Which is the only state this guard runs in on a fresh host. Reading `status`
    there concludes the SSH allow rule is absent immediately after adding it,
    and --apply dies one line before the branch that would have explained why.
    That is not hypothetical: it is what happened on the first real run.

    `ufw show added` reports configured rules regardless of running state, which
    is what `enable` will put in force.
    """
    guard_line = next(
        line for line in firewall_body.splitlines() if "refusing to enable the firewall" in line
    )
    window = firewall_body[: firewall_body.index(guard_line)]
    check = window[window.rindex("ufw ") :]
    assert "ufw show added" in check, "the SSH-rule guard does not read `ufw show added`"
    assert "ufw status" not in check, "the SSH-rule guard reads `ufw status`, which is empty"


def test_the_port_is_anchored_so_22_does_not_match_122(firewall_body: str) -> None:
    """A substring match would accept a rule for an unrelated port.

    The ``\\$`` is the shell's, not a typo: the pattern is inside a double-quoted
    string, so the dollar has to survive expansion to reach grep.
    """
    assert "grep -qE" in firewall_body, "the guard is a substring match, not an anchored one"
    assert "(^|[[:space:]])${ssh_port}/tcp([[:space:]]|\\$)" in firewall_body


def test_an_already_active_firewall_does_not_demand_a_new_timer(firewall_body: str) -> None:
    """Re-applying is not a new window.

    Without this, every idempotent re-run becomes a two-step ceremony, and an
    operator who has to arm a rollback to change nothing learns to arm it
    without thinking — which is the habit the whole mechanism depends on not
    forming.
    """
    assert "Status: active" in firewall_body
    assert firewall_body.index("Status: active") < firewall_body.index("ufw_rollback_is_armed")


def test_only_one_rollback_window_may_be_armed(apply_body: str) -> None:
    """Plan §3: never two armed windows at once."""
    assert "rollback_is_armed && ufw_rollback_is_armed" in apply_body
    guard = apply_body.index("rollback_is_armed && ufw_rollback_is_armed")
    assert guard < apply_body.index("${SSH_SNIPPET}"), (
        "the both-armed guard runs after SSH has already been hardened"
    )


def test_the_two_confirmations_are_separate_flags(source: str) -> None:
    """They attest to different things and must not be collapsed into one."""
    assert "--confirm-ssh-ok" in source
    assert "--confirm-firewall-ok" in source
    assert "confirm one rollback at a time" in source, (
        "passing both confirmations at once is accepted"
    )


def test_nothing_disarms_a_timer_as_a_side_effect_of_apply(apply_body: str) -> None:
    """A script that cancels its own rollback cancels it when it was wrong."""
    for cancellation in ("systemctl stop apg-", "${ROLLBACK_UNIT}.timer", "${UFW_ROLLBACK_UNIT}"):
        assert f"systemctl stop {cancellation}" not in apply_body


def test_help_documents_both_disarm_steps() -> None:
    result = subprocess.run(
        [str(SCRIPT), "--help"], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )
    assert result.returncode == 0
    assert "--confirm-firewall-ok" in result.stdout
    assert "--confirm-ssh-ok" in result.stdout
    assert "apg-ufw-rollback" in result.stdout, "--help does not name the timer to arm"

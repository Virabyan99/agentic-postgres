"""How the DOCKER-USER policy is *applied*, as opposed to what it says.

``tests/contract/test_host_infrastructure.py`` covers the policy's content
thoroughly — original destination port, default drop, exactly 80 and 443, ICMPv6
on the v6 side. All of that passed while the reconciler could not install a
single rule, because nothing tested the commands it builds.

Five defects lived in that gap, and every one of them either fails loudly on a
host or, worse, succeeds while protecting nothing:

1. the rendered specification was passed to ``iptables`` with no command flag,
   so every apply died on "no command specified";
2. ``-A`` would have been wrong even with the flag, because Docker creates
   DOCKER-USER holding a single ``-j RETURN`` and an appended rule sits after it,
   installed and visible and never evaluated;
3. no ownership comment was ever added, so the removal step that makes
   reconciliation converge matched nothing and every run added another copy;
4. removal fed ``-S`` output back unquoted, which breaks the moment iptables
   renders the comment with quotes;
5. ``status`` reported "(chain absent)" when it merely lacked the privilege to
   look, which tells an operator their firewall is missing when it is fine.

These are static assertions about command construction. That is a weaker
instrument than running the thing, and the reason it is what is here is that
``reconcile`` requires root and a rendered policy under ``/etc``. The behaviour
is proved on the host by ``test_the_live_policy_is_the_installed_policy``; these
keep the specific mistakes above from coming back between host runs.
"""

from __future__ import annotations

import re

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

SCRIPT = REPO_ROOT / "bin" / "docker-firewall.sh"


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def apply_body(source: str) -> str:
    return source.split("apply_rules()", 1)[1].split("\n}", 1)[0]


@pytest.fixture(scope="module")
def remove_body(source: str) -> str:
    return source.split("remove_tagged()", 1)[1].split("\n}", 1)[0]


def _invocations(body: str) -> list[str]:
    """Lines in a function body that invoke iptables via the ${command} handle."""
    return [line.strip() for line in body.splitlines() if '"${command}"' in line]


def test_adding_a_rule_names_a_chain_and_a_command(apply_body: str) -> None:
    """A rule specification with no command flag is not a command.

    `iptables -i eth0 -m conntrack ... -j RETURN` exits non-zero with "no
    command specified", which is exactly how --apply failed on the host.
    """
    adds = _invocations(apply_body)
    assert adds, "apply_rules invokes nothing"
    for line in adds:
        assert re.search(r'-I "\$\{CHAIN\}"', line), (
            f"apply_rules invokes iptables without -I <chain>: {line}"
        )


def test_rules_are_inserted_at_a_position_that_advances(apply_body: str) -> None:
    """Insert at 1, 2, 3... so the file's order survives into the chain.

    Inserting every rule at position 1 would reverse the policy, which puts the
    default DROP first and takes the host off the network.
    """
    assert '-I "${CHAIN}" "${position}"' in apply_body
    assert "position=$((position + 1))" in apply_body, "every rule is inserted at the same position"
    assert "position=1" in apply_body


def test_nothing_appends_to_the_chain(source: str) -> None:
    """`-A DOCKER-USER` lands after Docker's trailing RETURN, where nothing runs."""
    assert '-A "${CHAIN}"' not in source


def test_every_added_rule_carries_the_ownership_comment(apply_body: str) -> None:
    """Without it, removal matches nothing and reconciliation accumulates.

    The script's own header calls convergence-by-tag its central design choice.
    Nothing was stamping the tag.
    """
    for line in _invocations(apply_body):
        assert '--comment "${TAG}"' in line, f"an added rule carries no ownership comment: {line}"


def test_removal_does_not_feed_rule_specifications_back_unquoted(remove_body: str) -> None:
    """`-S` output word-split back into iptables is a guess about quoting.

    If the comment renders quoted, the argument arrives with literal quotes in
    it and the delete matches nothing — silently, since removal ignores errors.
    """
    assert "-S" not in remove_body, "removal reads `-S` output it would have to re-parse"
    assert "--line-numbers" in remove_body


def test_removal_deletes_highest_line_number_first(remove_body: str) -> None:
    """Ascending deletion removes the wrong rules: each delete shifts the rest."""
    assert "sort -rn" in remove_body, "line numbers are not sorted descending before deletion"


def test_removal_matches_the_tag_as_iptables_prints_it(remove_body: str) -> None:
    """`-L` renders a comment as /* tag */, which is stable across versions."""
    assert '"/* ${TAG} */"' in remove_body


def test_reconcile_verifies_the_chain_is_reachable(source: str) -> None:
    """Rules in a chain FORWARD does not jump to are inert and look perfect."""
    assert "require_chain_is_reachable" in source
    main_body = source.split("main()", 1)[1]
    assert main_body.index("apply_rules") < main_body.index("require_chain_is_reachable"), (
        "reachability is checked before the policy is applied, so a fresh host fails wrongly"
    )


def test_ipv4_reachability_is_fatal_and_ipv6_is_advisory(source: str) -> None:
    """The asymmetry is deliberate and worth pinning down.

    Docker only creates the v6 FORWARD reference when it manages ip6tables.
    Making that fatal would leave a unit that runs after every docker start
    permanently failed, taking the v4 policy — the one carrying public traffic —
    down with it. Making v4 advisory would let the whole policy go inert quietly.
    """
    main_body = source.split("main()", 1)[1]
    assert "require_chain_is_reachable iptables required" in main_body
    assert "require_chain_is_reachable ip6tables advisory" in main_body


def test_the_advisory_path_still_says_the_policy_is_not_enforcing(source: str) -> None:
    """A warning nobody can act on is noise; name the consequence."""
    body = source.split("require_chain_is_reachable()", 1)[1].split("\n}", 1)[0]
    assert "WARNING" in body
    assert "not enforcing" in body
    assert "die 6" in body, "the required severity does not fail"


def test_status_distinguishes_absent_from_unreadable(source: str) -> None:
    """iptables needs root to read. "(chain absent)" to a non-root caller is a lie."""
    status_body = source.split('ACTION}" = "status"', 1)[1].split("return 0", 1)[0]
    assert "id -u" in status_body, "status reports absence without checking whether it could look"
    assert "requires root" in status_body


def test_the_help_text_does_not_claim_status_works_without_root(source: str) -> None:
    """The old comment said so, and it was the reason the false negative shipped."""
    assert "Deliberately readable without root" not in source

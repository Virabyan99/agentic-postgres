"""The rotation surface, and the flags it reads (Session 15 Run 6).

D816 is the reason this module exists: `rotate_by_replacement`,
`must_refresh_on_start` and `one_time_initialization` are declared on all 19
secrets and were read by **one** contract test covering **three**. Sixteen were
assumptions, and Run 6's first act was checking them against the world.

**What was measured against the pinned image rather than asserted here**
(D849, D851): that replacing `postgres_init_superuser_password` leaves the
original working and the replacement refused -- new=False, old=True, with the
original still working as the control that this observed a live cluster rather
than a broken container -- and that a database role password rotates end to end
with its rollback rehearsed beforehand and working afterwards.

**What is asserted here is the part a checkout can see**: that the surface
refuses to describe a rotation it cannot perform, that it names the operation
that does work, and that `must_refresh_on_start` is not reported as a difference
while the behaviour it selects between does not exist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT, rotation
from agentic_postgres.secrets_contract import active_secrets, load_secret_contract

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CONTRACT = REPO_ROOT / "secrets.required.yaml"
MATERIALIZER = REPO_ROOT / "bin" / "materialize-secrets.py"


@pytest.fixture(scope="module")
def contract() -> dict:
    return load_secret_contract(CONTRACT)


@pytest.fixture(scope="module")
def raw() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The flags, checked against something other than themselves
# ---------------------------------------------------------------------------


def test_a_value_read_once_is_not_claimed_to_rotate(contract: dict) -> None:
    """The refusal that is the whole point of the surface (D56).

    Both `one_time_initialization` secrets look exactly like the seventeen that
    rotate: same shape, same consumers, same plane. A plan that printed their
    files and services would be describing, in detail, a rotation that does not
    happen -- and an operator who followed it would report one.
    """
    refused = {v.name for v in rotation.plan_all(contract, 15) if not v.rotates}
    declared = {
        s["name"]
        for s in active_secrets(contract, 15)
        if s["one_time_initialization"] or not s["rotate_by_replacement"]
    }
    assert refused == declared, f"the surface and the contract disagree: {refused} vs {declared}"
    assert refused, "no secret is refused, so this asserted nothing"


def test_every_refusal_names_the_operation_that_does_work(contract: dict) -> None:
    """A refusal without a way forward makes an operator guess.

    And the guess for a credential is usually "do it anyway". Both refusals name
    a different, real operation -- a coordinated `ALTER ROLE`, and a new
    repository with a new backup chain -- rather than pointing at documentation.
    """
    for verdict in rotation.plan_all(contract, 15):
        if verdict.rotates:
            continue
        assert verdict.instead, f"{verdict.name} is refused and names no alternative"
        assert len(verdict.instead) > 40, (
            f"{verdict.name}'s alternative is too short to be an instruction: {verdict.instead!r}"
        )


def test_the_two_refusals_do_not_share_one_explanation(contract: dict) -> None:
    """One flag, two different phenomena (D850).

    `postgres_init_superuser_password` is read once and nothing is BOUND to it:
    the cluster keeps whatever initdb set. `pgbackrest_repo_cipher_pass` is the
    opposite -- the value IS bound, to the repository, at `stanza-create` -- so
    replacing it does not leave the system using the old value, it leaves the
    reader holding the wrong one.

    The flag is right about the consequence and imprecise about the mechanism.
    One sentence covering both would be plausible and wrong for one of them,
    which is D278's shape: a repair that works is not evidence its explanation
    is right.
    """
    reasons = {v.name: v.reason for v in rotation.plan_all(contract, 15) if not v.rotates}
    assert len(set(reasons.values())) == len(reasons), (
        f"the refusals share an explanation, so one of them is described by a sentence "
        f"written about the other: {reasons}"
    )
    assert "stanza-create" in reasons["pgbackrest_repo_cipher_pass"]
    assert "initdb" in reasons["postgres_init_superuser_password"]


def test_a_value_from_a_third_party_is_not_offered_as_generatable(contract: dict) -> None:
    """`origin: operator_supplied` (ADR 0103), surfaced where it changes an action.

    These rotate by replacement -- but the replacement comes from a console at
    Cloudflare, not from this command. A plan that said "rotates" without saying
    so would send an operator looking for a `--generate` flag that must never
    exist.
    """
    supplied = {
        s["name"] for s in active_secrets(contract, 15) if s["origin"] == "operator_supplied"
    }
    reported = {v.name for v in rotation.plan_all(contract, 15) if v.operator_supplied}
    assert reported == supplied, f"{reported} vs {supplied}"
    assert supplied, "no operator-supplied secret, so this asserted nothing"

    for verdict in rotation.plan_all(contract, 15):
        if verdict.operator_supplied and verdict.rotates:
            assert "third party" in verdict.reason, (
                f"{verdict.name} is reported as rotating without saying the value cannot "
                "be generated here"
            )


def test_must_refresh_on_start_is_not_reported_while_its_alternative_does_not_exist() -> None:
    """The finding of Run 6's first act (D849), guarded where it would regress.

    The flag selects between failing closed and starting on a cached
    last-known-good value. **The materializer has no cache**: every provider
    failure except a 404 on an optional secret fails the run. So the "true"
    behaviour is the only behaviour and six `false` declarations describe
    leniency that was never built.

    This asserts the absence, and it goes red the day somebody builds the
    fallback -- which is exactly when the flag becomes a real difference and the
    surface should start reporting it.
    """
    source = MATERIALIZER.read_text(encoding="utf-8")
    for word in ("last_known_good", "last-known-good", "cache", "fallback"):
        assert word not in source.lower(), (
            f"the materializer mentions {word!r}: if a last-known-good path now exists, "
            "must_refresh_on_start has become a real difference and rotation.py must "
            "report it instead of explaining why it does not"
        )

    assert "D849" in rotation.MUST_REFRESH_IS_NOT_YET_A_CONTROL
    assert "must_refresh_on_start" not in _rendered_plan(), (
        "the surface reports a flag whose alternative behaviour does not exist"
    )


def _rendered_plan() -> str:
    contract = load_secret_contract(CONTRACT)
    return "\n".join(v.render() for v in rotation.plan_all(contract, 15))


# ---------------------------------------------------------------------------
# The surface itself
# ---------------------------------------------------------------------------


def test_the_surface_writes_nothing_anywhere() -> None:
    """D249's rule: no command here sets a value at the provider.

    Asserted over the source rather than by running it, because "it did not
    write" is not observable from a successful run -- the interesting case is the
    verb somebody adds later. A command that could both decide a rotation and
    perform it would be one mistake away from performing one nobody decided.
    """
    source = (REPO_ROOT / "bin" / "rotate-secret.py").read_text(encoding="utf-8")
    for forbidden in (
        "write_text",
        "open(",
        "InfisicalClient",
        "write_secret",
        "subprocess",
        "os.environ",
    ):
        assert forbidden not in source, (
            f"bin/rotate-secret.py contains {forbidden!r}; the surface reads a committed "
            "file and changes nothing"
        )


def test_a_retired_secret_is_not_in_the_rotation_surface(contract: dict) -> None:
    """Run 1's retirement, read by Run 6 (ADR 0170).

    Planning a rotation for a credential the release no longer issues would name
    a file nothing writes. `plan_all` takes the session for that reason, and the
    bootstrap key is the case: still declared, retired at 15.
    """
    at_14 = {v.name for v in rotation.plan_all(contract, 14)}
    at_15 = {v.name for v in rotation.plan_all(contract, 15)}
    assert "bootstrap_jwt_signing_key" in at_14
    assert "bootstrap_jwt_signing_key" not in at_15, (
        "the retired signing key is still offered for rotation"
    )


def test_every_active_secret_gets_exactly_one_verdict(contract: dict) -> None:
    """No secret is silently absent from the plan.

    The failure this catches is a filter that quietly drops a secret -- which
    would leave an operator believing a credential has no rotation story when
    nobody has written one.
    """
    verdicts = rotation.plan_all(contract, 15)
    names = [v.name for v in verdicts]
    assert len(names) == len(set(names)), "a secret appears twice in the plan"
    assert set(names) == {s["name"] for s in active_secrets(contract, 15)}


def test_the_command_is_registered_and_executable() -> None:
    from tests.contract import test_cli_contract as cli  # type: ignore[import-not-found]

    assert "bin/rotate-secret.sh" in cli.SHELL_COMMANDS
    assert "bin/rotate-secret.py" in cli.PYTHON_COMMANDS
    assert Path(REPO_ROOT / "bin" / "rotate-secret.sh").is_file()


def test_the_wrapper_refuses_nothing_it_cannot_explain() -> None:
    """`--help` names what the command does NOT do, not only what it does.

    The two refusals are the reason it exists, and a usage message that only
    listed flags would make it read like a reporting tool.
    """
    usage = (REPO_ROOT / "bin" / "rotate-secret.sh").read_text(encoding="utf-8")
    assert "changes nothing" in usage
    assert re.search(r"cannot be rotated by replacing them", usage), (
        "the usage does not say the refusals exist, so an operator learns it from output"
    )


def test_a_value_read_once_cannot_also_claim_to_rotate_by_replacement(contract: dict) -> None:
    """The gap a SURVIVING mutation revealed (D852).

    `M1` disabled the `one_time_initialization` branch entirely and the surface
    still refused both secrets -- because every secret declaring it also
    declares `rotate_by_replacement: false`, so the second branch caught them.
    The mutation was uninformative (D493): the property it attacked is
    over-determined by the data, and the refusal is robust for a reason nobody
    wrote down.

    **What it exposed is that nothing requires the two to agree.** The contract
    permits `one_time_initialization: true` beside `rotate_by_replacement: true`,
    which is a contradiction -- a value both read once and rotatable by
    replacement -- and it would produce a plan that reported a rotation for a
    secret whose own declaration says replacement achieves nothing.

    Asserted as an implication rather than an equality, deliberately. A secret
    may legitimately be `rotate_by_replacement: false` without being read once:
    that is "replacement does not rotate this, for some other reason", and
    forcing the converse would make a future entry lie to satisfy a test.
    """
    contradictions = [
        secret["name"]
        for secret in contract["secrets"]
        if secret["one_time_initialization"] and secret["rotate_by_replacement"]
    ]
    assert not contradictions, (
        f"{contradictions} declare a value that is both read once at initialization and "
        "rotatable by replacing it. One of the two is wrong, and the surface would "
        "report a rotation the secret's own declaration says does not happen"
    )

    # And the guard is not vacuous: the antecedent holds for something.
    assert any(s["one_time_initialization"] for s in contract["secrets"]), (
        "no secret is read once, so this implication asserted nothing"
    )

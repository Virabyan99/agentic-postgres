"""The node's capacity arithmetic (Session 31, NODE-READ-001, ADR 0221).

Pure. Nothing here starts a container, reads `/proc` or touches a host: the
probe side lives in `bin/doctor.py` and hands its results in, which is what
lets every case below be written as a fact rather than as a setup.

**What each proof is really guarding is a substitution.** Every one of these
functions has an obvious, wrong, quieter implementation: parse what you can
and default the rest; count a project you cannot read as zero; treat an
unbounded container as a free one. Each of those produces a number that looks
measured, and the number is always reassuring. That is the class this whole
session exists to close (ADR 0195, D600).
"""

from __future__ import annotations

import json

import pytest

from agentic_postgres import capacity_reading
from agentic_postgres.host_config import Declared

pytestmark = [pytest.mark.contract, pytest.mark.p0]


#: The reference host's own `/proc/meminfo`, read in rig 31b on 2026-09-19.
#: A real sample rather than a hand-built one: a fixture invented here would
#: agree with whatever this parser happened to do (§7 question 6).
HOST_MEMINFO = """MemTotal:        3906280 kB
MemFree:          401644 kB
MemAvailable:    2234652 kB
Buffers:           58100 kB
Cached:          1425084 kB
SwapCached:            0 kB
Active:          1638404 kB
SwapTotal:             0 kB
SwapFree:              0 kB
"""

DECLARED = Declared(memory_mb=3814, reserve_memory_mb=2214, disk_gb=38, reserve_disk_gb=8)


def reading(**overrides: object) -> capacity_reading.Reading:
    """A reading of the reference host, with everything measured."""
    base: dict[str, object] = {
        "declared": DECLARED,
        "mem_total": capacity_reading.Figure.measured(3814),
        "mem_available": capacity_reading.Figure.measured(2182),
        "swap_total": capacity_reading.Figure.measured(0),
        "docker_root_free_gb": capacity_reading.Figure.measured(22),
        "docker_root_total_gb": capacity_reading.Figure.measured(37),
        "committed": {"alpha-dev": 304, "beta-dev": 304},
        "unreadable": {},
        "ceilings": {"alpha-dev": 2240, "beta-dev": 2240},
        "unbounded": (),
    }
    base.update(overrides)
    return capacity_reading.Reading(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse_meminfo
# ---------------------------------------------------------------------------


def test_meminfo_is_parsed_to_mebibytes() -> None:
    """kB in, MiB out, floored.

    3906280 kB is 3814.72 MiB and the answer is 3814. A figure that rounded up
    would claim 0.72 MiB the host does not have -- trivial here, and the same
    rounding applied to a disk figure is not.
    """
    parsed = capacity_reading.parse_meminfo(HOST_MEMINFO)
    assert parsed == {"MemTotal": 3814, "MemAvailable": 2182, "SwapTotal": 0}


def test_a_meminfo_missing_memavailable_is_unknown_not_zero() -> None:
    """The mutation this module exists to kill.

    A parser that returned `{"MemAvailable": 0}` for a file that never
    mentioned it would report a host with no memory left -- and it would be
    reporting that about a host it simply failed to read. The two situations
    are opposites and only one of them is an emergency.
    """
    without = "\n".join(
        line for line in HOST_MEMINFO.splitlines() if not line.startswith("MemAvailable")
    )
    assert capacity_reading.parse_meminfo(without) is None


@pytest.mark.parametrize("field", ["MemTotal", "MemAvailable", "SwapTotal"])
def test_any_missing_field_is_unknown(field: str) -> None:
    """All three, not just the one somebody thought of."""
    without = "\n".join(
        line for line in HOST_MEMINFO.splitlines() if not line.startswith(f"{field}:")
    )
    assert capacity_reading.parse_meminfo(without) is None


def test_a_meminfo_in_unexpected_units_is_not_believed() -> None:
    """`kB` is asserted rather than assumed.

    If the kernel ever reported a value in some other unit, dividing it by
    1024 would produce a plausible number that is wrong by a factor nobody
    would notice.
    """
    swapped = HOST_MEMINFO.replace("MemTotal:        3906280 kB", "MemTotal:        3814 MB")
    assert capacity_reading.parse_meminfo(swapped) is None


def test_a_present_file_with_all_three_parses_even_with_junk_around_it() -> None:
    """The control for the three refusals above.

    Without it, a parser that returned `None` unconditionally would pass every
    negative case in this module.
    """
    noisy = "Totally: unrelated\n" + HOST_MEMINFO + "VmallocTotal:   34359738367 kB\n"
    assert capacity_reading.parse_meminfo(noisy) == {
        "MemTotal": 3814,
        "MemAvailable": 2182,
        "SwapTotal": 0,
    }


# ---------------------------------------------------------------------------
# committed_from_documents
# ---------------------------------------------------------------------------


def document(unreclaimable: int | None) -> dict[str, object]:
    budget: dict[str, object] = {"shared_buffers_mb": 128, "max_connections": 56}
    if unreclaimable is not None:
        budget["unreclaimable_mb"] = unreclaimable
    return {"database": {"budget": budget}}


def test_committed_memory_sums_unreclaimable_across_documents_and_excludes_the_candidate() -> None:
    """The candidate's own claim is charged once, as the request, never twice.

    Charging it from its old document as well would refuse redeployments that
    fit -- including one that LOWERED its budget, which is the case where the
    refusal would be most obviously absurd.
    """
    documents = {"alpha-dev": document(304), "beta-dev": document(304), "gamma-dev": document(999)}

    committed, unreadable = capacity_reading.committed_from_documents(
        documents, exclude="gamma-dev"
    )
    assert committed == {"alpha-dev": 304, "beta-dev": 304}
    assert unreadable == {}

    everything, _ = capacity_reading.committed_from_documents(documents, exclude=None)
    assert sum(everything.values()) == 1607, "the control: with nothing excluded, all three count"


def test_a_document_without_the_member_is_unreadable_not_zero() -> None:
    """D600 in arithmetic.

    A project whose claim this program cannot read is a project whose claim it
    does not know. Summing it as nothing makes the host look emptier than it
    is, which admits a candidate that does not fit -- the failure is silent,
    and it lands on the project that was already running.
    """
    committed, unreadable = capacity_reading.committed_from_documents(
        {"alpha-dev": document(304), "beta-dev": document(None)}, exclude=None
    )
    assert committed == {"alpha-dev": 304}
    assert list(unreadable) == ["beta-dev"]
    assert "unreclaimable_mb" in unreadable["beta-dev"]


def test_a_document_with_no_budget_at_all_is_unreadable() -> None:
    committed, unreadable = capacity_reading.committed_from_documents(
        {"alpha-dev": {"database": {}}}, exclude=None
    )
    assert committed == {}
    assert "database.budget" in unreadable["alpha-dev"]


def test_a_non_integer_claim_is_unreadable() -> None:
    """A string that looks like a number is not a number.

    JSON has no integer type distinct from a float, and a document carrying
    `"304"` would sum with `+` in some languages and not in this one.
    """
    committed, unreadable = capacity_reading.committed_from_documents(
        {"alpha-dev": document("304")},  # type: ignore[arg-type]
        exclude=None,
    )
    assert committed == {}
    assert unreadable


# ---------------------------------------------------------------------------
# ceilings_from_inspect
# ---------------------------------------------------------------------------


def inspect_payload(*containers: tuple[str, str, int]) -> str:
    return json.dumps(
        [
            {
                "Name": f"/{name}",
                "Config": {"Labels": {"apg.project.key": key}},
                "HostConfig": {"Memory": limit},
            }
            for name, key, limit in containers
        ]
    )


def test_ceilings_sum_hostconfig_memory_and_ignore_unbounded_containers() -> None:
    """An unbounded container is listed by name, never added as zero.

    Adding it as zero makes the one container that could take the whole host
    look like the cheapest thing on it.
    """
    payload = inspect_payload(
        ("apg-alpha-dev-postgres-1", "alpha-dev", 768 * 1024 * 1024),
        ("apg-alpha-dev-auth-1", "alpha-dev", 384 * 1024 * 1024),
        ("apg-alpha-dev-dbmate-1", "alpha-dev", 0),
        ("apg-beta-dev-postgres-1", "beta-dev", 768 * 1024 * 1024),
    )
    ceilings, unbounded = capacity_reading.ceilings_from_inspect(payload)
    assert ceilings == {"alpha-dev": 1152, "beta-dev": 768}
    assert unbounded == ("apg-alpha-dev-dbmate-1",)


def test_an_unlabelled_container_belongs_to_no_project() -> None:
    """The edge is shared and is nobody's claim."""
    payload = json.dumps(
        [
            {
                "Name": "/apg-edge-proxy",
                "Config": {"Labels": {}},
                "HostConfig": {"Memory": 256 * 1024 * 1024},
            }
        ]
    )
    assert capacity_reading.ceilings_from_inspect(payload) == ({}, ())


def test_an_unparseable_inspect_is_empty_rather_than_wrong() -> None:
    """Ceilings decide nothing, so an unreadable payload costs a report line.

    This is the one figure in the module allowed to degrade quietly, and it is
    allowed because `decide` never reads it.
    """
    assert capacity_reading.ceilings_from_inspect("not json") == ({}, ())
    assert capacity_reading.ceilings_from_inspect('{"not": "a list"}') == ({}, ())


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


def test_a_candidate_that_does_not_fit_is_refused_with_exit_twelve() -> None:
    """The live case, with the numbers rig 31e computed.

    Committed 608, reserve 2214, declared 3814 -> 992 MiB safely available. A
    candidate at `shared_buffers_mb: 896` claims 1072 and does not fit.
    """
    decision = capacity_reading.decide(
        reading(),
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=1072,
        candidate_is_deployed=False,
    )
    assert decision.outcome == "refused"
    assert decision.exit_code == capacity_reading.EXIT_ADMISSION_REFUSED == 12
    assert "1072" in decision.reason and "992" in decision.reason


def test_a_candidate_that_fits_is_admitted() -> None:
    """The control. Without it, a function that refused everything passes."""
    decision = capacity_reading.decide(
        reading(),
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=304,
        candidate_is_deployed=False,
    )
    assert decision.outcome == "admitted"
    assert decision.exit_code == 0


def test_a_redeploy_charges_only_the_other_projects() -> None:
    """Excluding the candidate is what makes a redeploy decidable at all.

    beta-dev redeploying at 1200 MiB is charged against alpha-dev's 304 alone:
    3814 - 2214 - 304 = 1296 available, so it fits. Charged against its own
    committed 304 as well, it would see 992 and be refused -- for memory it is
    about to stop using.

    **The request straddles the two answers deliberately.** An earlier version
    asked for 900, which fits either way, so the proof passed against a
    `committed_from_documents` that ignored `exclude` entirely. A number that
    does not distinguish the two implementations is not measuring the
    exclusion; it is measuring that something returned admitted.
    """
    documents = {"alpha-dev": document(304), "beta-dev": document(304)}
    committed, _ = capacity_reading.committed_from_documents(documents, exclude="beta-dev")
    assert committed == {"alpha-dev": 304}

    decision = capacity_reading.decide(
        reading(committed=committed),
        candidate_key="beta-dev",
        candidate_unreclaimable_mb=1200,
        candidate_is_deployed=True,
    )
    assert decision.outcome == "admitted"

    # The other side of the straddle, stated as a fact rather than left
    # implied: charged twice, the same redeploy is refused.
    both, _ = capacity_reading.committed_from_documents(documents, exclude=None)
    refused = capacity_reading.decide(
        reading(committed=both),
        candidate_key="beta-dev",
        candidate_unreclaimable_mb=1200,
        candidate_is_deployed=True,
    )
    assert refused.outcome == "refused"


def test_no_declaration_refuses_a_new_project_and_admits_a_redeploy() -> None:
    """The asymmetry that keeps this release a minor (D1584).

    Nothing declared means there is no basis on which to admit something new
    -- and a redeploy is already on the host whatever this function says, so
    refusing it would stop something that is running for the sake of a
    declaration nobody has made yet.
    """
    undeclared = reading(declared=None)

    new = capacity_reading.decide(
        undeclared,
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=304,
        candidate_is_deployed=False,
    )
    assert new.outcome == "refused"
    assert "schema_version 3" in new.reason

    redeploy = capacity_reading.decide(
        undeclared,
        candidate_key="alpha-dev",
        candidate_unreclaimable_mb=304,
        candidate_is_deployed=True,
    )
    assert redeploy.outcome == "admitted"


def test_an_unknown_figure_fails_closed_naming_it() -> None:
    """A decision may fail closed; the reading beside it may not.

    Both halves are asserted: the refusal happens, AND the reason names the
    project whose claim could not be read. A refusal that said only "could not
    decide" would send an operator to the wrong file.
    """
    decision = capacity_reading.decide(
        reading(unreadable={"beta-dev": "the deployed document could not be read"}),
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=304,
        candidate_is_deployed=False,
    )
    assert decision.outcome == "refused"
    assert "beta-dev" in decision.reason


def test_an_undetermined_disk_figure_also_fails_closed() -> None:
    """Memory is not the only figure a decision needs."""
    decision = capacity_reading.decide(
        reading(docker_root_free_gb=capacity_reading.Figure.unknown("`docker info` said nothing")),
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=304,
        candidate_is_deployed=False,
    )
    assert decision.outcome == "refused"
    assert "docker info" in decision.reason


def test_disk_is_a_floor_and_the_reserve_is_what_it_protects() -> None:
    """Below the declared reserve, no new project -- whatever memory says."""
    decision = capacity_reading.decide(
        reading(docker_root_free_gb=capacity_reading.Figure.measured(3)),
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=304,
        candidate_is_deployed=False,
    )
    assert decision.outcome == "refused"
    assert "reserve" in decision.reason or "eat into" in decision.reason


def test_the_refusal_prints_the_six_lines() -> None:
    """Six labelled lines, in the order an operator reads them.

    Ordered rather than a set: the whole point is that somebody scanning a
    refusal finds the number they can change without reading prose.
    """
    decision = capacity_reading.decide(
        reading(),
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=1072,
        candidate_is_deployed=False,
    )
    labels = [label for label, _ in decision.lines]
    assert labels == [
        "declared memory",
        "reserved",
        "committed",
        "requested",
        "safe available",
        "suggested action",
    ]

    rendered = capacity_reading.render_decision(decision)
    assert "admission: refused" in rendered
    for label in labels:
        assert label in rendered


def test_the_suggested_action_names_the_fields_that_actually_move_the_figure() -> None:
    """`work_mem_mb` is deliberately absent: it is per sort, not per backend,
    and does not enter `unreclaimable_mb`. An operator told to lower it would
    change a number and watch the refusal repeat."""
    action = capacity_reading.SUGGESTED_ACTION_MEMORY
    assert "database.shared_buffers_mb" in action
    assert "database.maintenance_work_mem_mb" in action
    assert "database.max_connections" in action
    # The QUALIFIED name, because the bare `work_mem_mb` is a substring of
    # `maintenance_work_mem_mb` and can never be absent while the correct
    # field is named -- an assertion that could not fail (§7 question 1).
    assert "database.work_mem_mb" not in action


def test_an_admission_prints_the_same_shape_as_a_refusal() -> None:
    """One report, two outcomes -- so that comparing them is comparing like
    with like rather than reading two different documents."""
    decision = capacity_reading.decide(
        reading(),
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=304,
        candidate_is_deployed=False,
    )
    labels = [label for label, _ in decision.lines]
    for expected in ("declared memory", "reserved", "committed", "requested", "safe available"):
        assert expected in labels


def test_a_figure_cannot_be_unknown_without_a_reason() -> None:
    """The `null` that looks measured, refused at construction (D600)."""
    with pytest.raises(ValueError):
        capacity_reading.Figure.unknown("")

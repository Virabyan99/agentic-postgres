"""Every project service is bounded in processes (`NODE-LIMIT-001`, ADR 0222).

**What this session narrows is not infinity.** Rig 31b read
`/sys/fs/cgroup/system.slice/docker-*.scope/pids.max` for all 22 containers on
the reference host, as `op` with no root, and every one reads **3647** --
systemd's `DefaultTasksMax`, which nobody chose for these services. So the
claim is 3647 -> 128/64, and the ADR says so rather than the more impressive
thing (D1602).

The split is asserted **by walking every service in `compose.yaml`**, not by
checking a list somebody kept. A twenty-first service must land on one side or
the other, and a list would go quiet the first time somebody forgot.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.contract.test_image_contracts import LOCK, requires_docker  # noqa: E402

from agentic_postgres import config, rendering  # noqa: E402

pytestmark = [pytest.mark.contract, pytest.mark.p0]

COMPOSE = REPO_ROOT / "compose.yaml"

#: The nine that run for as long as the project does. Spelled here so that the
#: walk below has something to compare against -- and derived from
#: `config.SERVICE_RESOURCE_DEFAULTS` rather than retyped, so the two cannot
#: disagree about which services are which.
LONG_RUNNING = frozenset(config.SERVICE_RESOURCE_DEFAULTS)


@pytest.fixture(scope="module")
def model() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_every_service_carries_a_pids_limit(model: dict) -> None:
    """All twenty, walked rather than listed.

    A fork storm in any one container on a 2 vCPU, no-swap node is bounded by
    nothing this product does until this holds.
    """
    services = model["services"]
    assert len(services) == 20, f"the service count moved to {len(services)}; check the split"

    without = sorted(name for name, service in services.items() if "pids_limit" not in service)
    assert not without, f"these services are unbounded in processes: {without}"


def test_the_nine_take_theirs_from_the_environment_and_the_eleven_the_literal(
    model: dict,
) -> None:
    """The split, by name, in both directions.

    Both directions because each single direction has a trivial wrong
    implementation that would pass it: every service interpolating would pass
    a check that only the nine do, and every service carrying the literal
    would pass a check that only the eleven do.
    """
    services = model["services"]
    wrong: list[str] = []
    for name, service in sorted(services.items()):
        pids = service["pids_limit"]
        interpolated = isinstance(pids, str) and pids.startswith("${")
        if name in LONG_RUNNING:
            if not interpolated:
                wrong.append(f"{name}: long-running but carries the literal {pids!r}")
            if "cpus" not in service:
                wrong.append(f"{name}: long-running but has no cpus")
        else:
            if interpolated:
                wrong.append(f"{name}: short-lived but interpolates {pids!r}")
            if pids != config.SHORT_LIVED_PIDS_LIMIT:
                wrong.append(f"{name}: short-lived and carries {pids!r}")
            if "cpus" in service:
                wrong.append(f"{name}: short-lived but carries a cpus cap")
    assert not wrong, wrong

    assert len(LONG_RUNNING) == 9
    assert len(services) - len(LONG_RUNNING) == 11


def test_every_interpolation_is_required_and_named_for_its_service(model: dict) -> None:
    """`${X:?required}`, because Compose treats an empty interpolation exactly
    as it treats an unset one (D178). A key that silently resolved to nothing
    would leave the service unbounded and the file looking bounded."""
    for name in sorted(LONG_RUNNING):
        service = model["services"][name]
        upper = name.upper()
        assert service["pids_limit"] == f"${{{upper}_PIDS_LIMIT:?required}}"
        assert service["cpus"] == f"${{{upper}_CPUS:?required}}"


def test_every_key_the_compose_file_interpolates_is_in_the_env_keys() -> None:
    """The render must emit what the model asks for.

    The failure this prevents is the quietest one available: a compose file
    naming `MCP_PIDS_LIMIT` that nothing emits does not fail a render -- it
    fails the deploy, on the host, at the moment Compose is asked to start.
    """
    for name in sorted(LONG_RUNNING):
        upper = name.upper()
        assert f"{upper}_PIDS_LIMIT" in rendering.COMPOSE_ENV_KEYS
        assert f"{upper}_CPUS" in rendering.COMPOSE_ENV_KEYS

    assert set(rendering.SERVICE_RESOURCE_ORDER) == {n.upper() for n in LONG_RUNNING}, (
        "the render order and the defaults table name different services"
    )


def test_every_default_is_a_power_of_two_at_least_sixty_four() -> None:
    """The rule, not the numbers.

    Each default is the larger of 64 and four times a measured peak, rounded
    up to a power of two. Asserting the SHAPE rather than the nine literals is
    what makes the next session's re-measurement a change to one table instead
    of a change to a test that would otherwise have to be edited to agree with
    whatever was measured.
    """
    for name, limits in sorted(config.SERVICE_RESOURCE_DEFAULTS.items()):
        pids = limits["pids_limit"]
        assert isinstance(pids, int), f"{name}: {pids!r} is not an integer"
        assert pids >= 64, f"{name}: {pids} is below the floor of 64"
        assert pids & (pids - 1) == 0, f"{name}: {pids} is not a power of two"

    assert config.SHORT_LIVED_PIDS_LIMIT >= 64
    assert config.SHORT_LIVED_PIDS_LIMIT & (config.SHORT_LIVED_PIDS_LIMIT - 1) == 0


def test_postgres_can_hold_its_connections_and_its_workers() -> None:
    """A cluster cannot be capped below the backends it is configured to accept.

    `max_connections` is 56 and each connection is a process, so a limit at or
    below it is a limit that turns a full connection pool into
    `too many connections` -- naming the role rather than the arithmetic, which
    is the failure ADR 0070 already documents for a different cause. The +32 is
    the postmaster, the background workers, the checkpointer, the WAL writer
    and the autovacuum workers.
    """
    postgres = config.SERVICE_RESOURCE_DEFAULTS["postgres"]["pids_limit"]
    connections = config.DATABASE_BUDGET_DEFAULTS["max_connections"]
    assert isinstance(postgres, int)
    assert postgres >= connections + 32, (
        f"postgres is capped at {postgres} processes and configured for "
        f"{connections} connections plus its own workers"
    )


def test_cpus_is_two_for_postgres_and_one_for_every_sidecar() -> None:
    """No sidecar may take both of this node's cores.

    postgres gets the host's own count rather than `max`, so a bigger host does
    not silently give the cluster more than was measured here.
    """
    for name, limits in sorted(config.SERVICE_RESOURCE_DEFAULTS.items()):
        cpus = limits["cpus"]
        assert isinstance(cpus, str), (
            f"{name}: cpus is {cpus!r}; it must be a STRING, because "
            "`${VAR:?required}` interpolation yields one and that is the form "
            "rig 31a measured Compose accepting"
        )
        assert cpus == ("2.0" if name == "postgres" else "1.0"), f"{name}: cpus {cpus!r}"


def test_the_edge_plane_is_untouched() -> None:
    """The shared edge is nobody's project and is not bounded here.

    Recreating Traefik drops every project's ingress at once, which is its own
    act with its own blast radius. Stated as a test rather than left as an
    absence, so that adding it later is a decision somebody takes rather than
    a line somebody slips in.
    """
    edge = REPO_ROOT / "infra" / "edge" / "compose.yaml"
    assert edge.is_file()
    assert "pids_limit" not in edge.read_text(encoding="utf-8")


def test_the_dev_cluster_carries_the_same_limit_as_the_release(tmp_path: Path) -> None:
    """Conditional, and the condition is currently false.

    `apg dev`'s cluster is a bare `docker run` whose argument list carries no
    `--memory` and no `-c` -- *"Nothing is in this list by accident"*. It sets
    no memory limit, so ADR 0222's rule does not reach it: a `--pids-limit`
    there would be the first resource cap on a developer's throwaway cluster
    and it would be one nobody asked for.

    The INVARIANT is what is asserted: if that argv ever acquires a memory
    cap, it acquires a process cap in the same change. Written this way rather
    than deleted, because the next person to bound the dev cluster's memory is
    exactly the person who will not think about its processes.
    """
    from agentic_postgres import dev_environment

    argv = dev_environment.run_arguments("apg-dev-probe", "postgres:18", tmp_path / "env")
    rendered = " ".join(argv)

    bounded_memory = "--memory" in rendered or "-m" in argv
    bounded_pids = "--pids-limit" in rendered
    assert bounded_pids or not bounded_memory, (
        "the dev cluster bounds memory but not processes; ADR 0222's rule is "
        "that the two move together"
    )


# ---------------------------------------------------------------------------
# The limit against a real container
# ---------------------------------------------------------------------------


@requires_docker
def test_a_container_cannot_fork_past_its_pids_limit() -> None:
    """The mechanism, not the configuration.

    Everything above reads a file. This runs a container with the limit and
    watches it fail to fork, asserting the text rig 31a measured verbatim --
    `fork: retry: Resource temporarily unavailable`, then
    `fork: Resource temporarily unavailable`.
    """
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--pids-limit",
            "8",
            "--entrypoint",
            "bash",
            LOCK["POSTGRES_IMAGE"],
            "-c",
            "i=0; while [ $i -lt 20 ]; do i=$((i+1)); sleep 30 & done; cat /sys/fs/cgroup/pids.max",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    combined = completed.stdout + completed.stderr
    assert "Resource temporarily unavailable" in combined, combined[-500:]
    assert "fork" in combined, combined[-500:]


@requires_docker
def test_the_same_fork_succeeds_with_no_limit() -> None:
    """The control, and without it the proof above is worthless.

    A container that could not fork twenty `sleep`s for some reason that has
    nothing to do with `--pids-limit` -- an image without `bash`, a daemon
    under pressure -- would make the subject pass while measuring nothing.
    """
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--entrypoint",
            "bash",
            LOCK["POSTGRES_IMAGE"],
            "-c",
            "i=0; n=0; while [ $i -lt 20 ]; do i=$((i+1)); sleep 30 & "
            "if [ $? -eq 0 ]; then n=$((n+1)); fi; done; echo spawned=$n; "
            "cat /sys/fs/cgroup/pids.max",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    combined = completed.stdout + completed.stderr
    assert "spawned=20" in combined, combined[-500:]
    assert "Resource temporarily unavailable" not in combined, combined[-500:]

    # **The ceiling is NOT asserted as a literal**, and the first version of
    # this test was wrong to do so. It read `max` here and `19151` on CI --
    # the runner's systemd `DefaultTasksMax` -- and `3647` on the reference
    # host. That IS D1602: a container with no `--pids-limit` is not
    # unbounded, it inherits whatever ambient ceiling the machine sets, and
    # the value is the environment's business.
    #
    # What this control owes the subject beside it is that the ceiling it ran
    # under is nothing like the subject's 8. So that is what it asserts.
    ceiling = completed.stdout.strip().splitlines()[-1].strip()
    if ceiling != "max":
        assert ceiling.isdigit(), (
            f"pids.max read {ceiling!r}, which is neither `max` nor a number"
        )
        assert int(ceiling) > 64, (
            f"the control ran under a ceiling of {ceiling}, which is close "
            "enough to the subject's 8 that the two arms are not comparing "
            "a limit against the absence of one"
        )

"""Session 39's host proofs: the edge's Postgres door, the firewall, a live slot's doors.

`EP-LIVE-003`'s five node ids, run by the sweep as root (claim
`endpoints_host_live`) after `slot3-prod` was created and credentialed through
`/v1` (Run 11) -- so the poolers these proofs read are the ones a customer
reached. None of them changes anything: containers through `docker inspect`,
the firewall through `iptables -S`, the edge's configuration from the files
`bin/edge.sh` rendered.

The live slot's deployed document is `APG_LIVE_SLOT_OUTPUTS` -- the op-readable
copy Sheet K3 made (and S1 re-installs); the control project's is
`APG_CONTROL_OUTPUTS`, and A's and B's are the sweep's usual two.
**None of these five proofs has ever executed.**
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import host_config, naming, runtime_override, slot
from agentic_postgres.evidence import ISOLATED_FIELDS

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_LIVE_SLOT_OUTPUTS",
        "APG_CONTROL_OUTPUTS",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
    ),
]

#: The customer poolers' committed bounds (ADR 0269, D2358): config's tables.
POOLER_MEMORY = 64 * 1024 * 1024
POOLER_PIDS = 64
POOLER_NANO_CPUS = 1_000_000_000


def _document(variable: str) -> dict[str, Any]:
    path = Path(os.environ[variable])
    if not path.is_file():
        pytest.fail(f"{variable} points at {path}, which does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live_slot() -> dict[str, Any]:
    document = _document("APG_LIVE_SLOT_OUTPUTS")
    key = document["project"]["key"]
    assert slot.SLOT_KEY.match(key), f"APG_LIVE_SLOT_OUTPUTS names {key}, not a slot's key"
    public = (document.get("database") or {}).get("public") or {}
    assert public.get("enabled") is True, f"{key}'s document records no public endpoints"
    return document


@pytest.fixture(scope="module")
def control_project() -> dict[str, Any]:
    return _document("APG_CONTROL_OUTPUTS")


def _run(*command: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command), stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, check=False,
    )  # fmt: skip


def _inspect(container: str) -> dict[str, Any]:
    done = _run("docker", "inspect", container)
    assert done.returncode == 0, f"docker inspect {container}: {done.stderr.strip()}"
    (found,) = json.loads(done.stdout)
    return found


def _edge_traefik() -> str:
    label = runtime_override.COMPOSE_PROJECT_LABEL
    listing = _run(
        "docker", "ps", "-q", "--filter", f"label={label}={host_config.EDGE_STACK_NAME}",
        "--filter", "label=com.docker.compose.service=traefik",
    )  # fmt: skip
    ids = listing.stdout.split()
    assert listing.returncode == 0 and len(ids) == 1, (listing.stdout, listing.stderr)
    return ids[0]


def _field(document: dict[str, Any], pointer: tuple[str, ...]) -> Any:
    value: Any = document
    for key in pointer:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def test_the_edge_serves_the_postgres_entrypoint(as_root: None) -> None:
    """ADR 0268 item 1, on the host: the running edge publishes 5432 to its
    container port 8432, the static configuration `bin/edge.sh` rendered names
    the `postgres` entrypoint on `:8432` with the 10 s read deadline, and the
    dynamic baseline carries the `postgres` TLS option offering only
    `postgresql` -- the files the RUNNING edge mounts, read from the host."""
    ports = _inspect(_edge_traefik())["NetworkSettings"]["Ports"] or {}
    bound = {int(b["HostPort"]) for b in ports.get(f"{host_config.EDGE_POSTGRES_PORT}/tcp") or []}
    assert bound == {host_config.EDGE_PUBLIC_POSTGRES_PORT}, ports
    state = Path(host_config.EDGE_STATE_DIR)
    static = yaml.safe_load((state / "traefik.yaml").read_text(encoding="utf-8"))
    entry = static["entryPoints"][host_config.EDGE_POSTGRES_ENTRYPOINT]
    assert entry["address"] == f":{host_config.EDGE_POSTGRES_PORT}", entry
    assert entry["transport"]["respondingTimeouts"]["readTimeout"] == "10s", entry
    dynamic = yaml.safe_load((state / "dynamic" / "baseline.yaml").read_text(encoding="utf-8"))
    option = dynamic["tls"]["options"]["postgres"]
    assert option["alpnProtocols"] == ["postgresql"] and option["sniStrict"] is True, option


@pytest.mark.parametrize("command", ["iptables", "ip6tables"])
def test_the_firewall_admits_exactly_the_three_ports(as_root: None, command: str) -> None:
    """ADR 0268, D2371: the running DOCKER-USER chain admits NEW connections to
    exactly 80, 443 and 5432 by their pre-DNAT port -- read from the kernel, not
    the file it was loaded from."""
    rules = _run(command, "-S", "DOCKER-USER")
    assert rules.returncode == 0 and rules.stdout.strip(), rules.stderr
    ports = {int(p) for p in re.findall(r"--ctorigdstport (\d+)", rules.stdout)}
    assert ports == {80, 443, 5432}, f"{command} DOCKER-USER admits {sorted(ports)}"


def test_the_customer_poolers_are_bounded_and_placed(
    as_root: None, live_slot: dict[str, Any]
) -> None:
    """ADR 0269 items 3-4: both of the slot's customer poolers run healthy, with
    the committed memory, process and CPU bounds, on exactly the project's
    `edge` and `internal` networks, each carrying the TCP router for its own
    name -- `HostSNI` the document's host -- and the userlist directory bound
    read-only."""
    key = live_slot["project"]["key"]
    public = live_slot["database"]["public"]
    edge = naming.compose_name(f"apg-{key}-edge", context="probe")
    internal = naming.compose_name(f"apg-{key}-internal", context="probe")
    routers = {
        naming.CUSTOMER_POOL_SERVICE: (naming.customer_pool_router_name(key), public["pooled"]),
        naming.CUSTOMER_DIRECT_SERVICE: (naming.customer_direct_router_name(key), public["direct"]),
    }
    for service, container in zip(
        (naming.CUSTOMER_POOL_SERVICE, naming.CUSTOMER_DIRECT_SERVICE),
        naming.customer_pooler_containers(key),
        strict=True,
    ):
        found = _inspect(container)
        assert found["State"]["Running"] and found["State"]["Health"]["Status"] == "healthy", (
            container, found["State"],
        )  # fmt: skip
        config = found["HostConfig"]
        assert (config["Memory"], config["PidsLimit"], config["NanoCpus"]) == (
            POOLER_MEMORY, POOLER_PIDS, POOLER_NANO_CPUS,
        ), container  # fmt: skip
        assert set(found["NetworkSettings"]["Networks"]) == {edge, internal}, container
        router, door = routers[service]
        labels = found["Config"]["Labels"]
        assert labels.get(f"traefik.tcp.routers.{router}.rule") == f"HostSNI(`{door['host']}`)", (
            container
        )
        mounts = [
            m
            for m in found["Mounts"]
            if m["Destination"] == runtime_override.CUSTOMER_USERLIST_MOUNT
        ]
        assert len(mounts) == 1 and mounts[0]["RW"] is False, (container, found["Mounts"])


def test_the_database_is_still_unrouted(as_root: None, live_slot: dict[str, Any]) -> None:
    """ADR 0268's line held for a project WITH doors: its `postgres` container
    joins only `internal` and `backup`, carries no `traefik.` label, and
    publishes nothing beyond loopback; the platform's own `pgbouncer` joins no
    `edge` either. The customer reaches the data only through a pooler that
    admits a customer role."""
    key = live_slot["project"]["key"]
    database = _inspect(live_slot["database"]["container"])
    networks = set(database["NetworkSettings"]["Networks"])
    assert networks == {
        naming.compose_name(f"apg-{key}-internal", context="probe"),
        naming.backup_network_name(key),
    }, networks
    labels = database["Config"]["Labels"] or {}
    assert not any(name.startswith("traefik.") for name in labels), sorted(labels)
    bindings = database["HostConfig"].get("PortBindings") or {}
    exposed = [
        b
        for spec in bindings.values()
        for b in spec or []
        if b.get("HostIp") not in ("127.0.0.1", "::1")
    ]
    assert not exposed, bindings
    label = runtime_override.COMPOSE_PROJECT_LABEL
    pooler = _run(
        "docker", "ps", "-q", "--filter", f"label={label}={naming.compose_project_name(key)}",
        "--filter", "label=com.docker.compose.service=pgbouncer",
    )  # fmt: skip
    for container in pooler.stdout.split():
        assert not any("-edge" in n for n in _inspect(container)["NetworkSettings"]["Networks"])


def test_the_slot_was_isolated_from_every_project(
    live_slot: dict[str, Any],
    control_project: dict[str, Any],
    project_a: dict[str, Any],
    project_b: dict[str, Any],
) -> None:
    """The isolation matrix with doors (ISOLATED_FIELDS 20, D2367): no isolated
    value and no derived role of the live slot's document equals A's, B's or the
    control project's -- the two customer roles among them -- the comparison
    compared at least the key, the domain and the database; and the slot's two
    door hosts are present and are no neighbour's domain or door (the
    neighbours have none: their `public` is null, so the pointer alone could
    never collide)."""
    compared: set[tuple[str, ...]] = set()
    collisions = []
    for neighbour in (project_a, project_b, control_project):
        for pointer in ISOLATED_FIELDS:
            mine, theirs = _field(live_slot, pointer), _field(neighbour, pointer)
            if mine is None or theirs is None:
                continue
            compared.add(pointer)
            if mine == theirs:
                collisions.append((neighbour["project"]["key"], ".".join(pointer), mine))
        for role, name in live_slot["database"]["roles"].items():
            if neighbour["database"]["roles"].get(role) == name:
                collisions.append((neighbour["project"]["key"], f"role {role}", name))
    assert not collisions, collisions
    required = {("project", "key"), ("project", "domain"), ("database", "name")}
    assert required <= compared, sorted(required - compared)
    hosts = {
        _field(live_slot, ("database", "public", door, "host")) for door in ("pooled", "direct")
    }
    assert None not in hosts and len(hosts) == 2, hosts
    for neighbour in (project_a, project_b, control_project):
        theirs = {neighbour["project"]["domain"]} | {
            _field(neighbour, ("database", "public", door, "host")) for door in ("pooled", "direct")
        }
        assert not hosts & theirs, (neighbour["project"]["key"], hosts & theirs)

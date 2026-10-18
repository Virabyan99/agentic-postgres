"""The telemetry plane's model (Session 42, ADR 0277, D2573-D2580, D2600-D2605).

Read from the files the host runs: `infra/telemetry/compose.yaml`, the
gateway's config, ClickHouse's `config.d` file, the users file the plane
renders, and the network helper every caller sources. Rig 42a measured each
property these assert (ADR 0277's *Measured*); these keep the files saying it.
"""

from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT, telemetry_plane

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

MODEL_PATH = REPO_ROOT / "infra" / "telemetry" / "compose.yaml"
GATEWAY_PATH = REPO_ROOT / "infra" / "telemetry" / "gateway.yaml"
CLICKHOUSE_CONFIG = REPO_ROOT / "infra" / "telemetry" / "clickhouse" / "config.xml"
NETWORK_HELPER = REPO_ROOT / "bin" / "lib" / "telemetry-network.sh"


def _model() -> dict:
    return yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))


def test_no_port_and_no_router() -> None:
    """No service publishes a port or carries a label of any kind (no router
    can find it); the networks are exactly the three the plane ensures, each
    external; HyperDX alone is on the UI bridge, and only the gateway is on the
    ingest network from the plane's side."""
    model = _model()
    assert model["name"] == telemetry_plane.COMPOSE_PROJECT
    for name, service in model["services"].items():
        assert "ports" not in service and "expose" not in service, name
        assert "labels" not in service, name
        assert service.get("network_mode") is None, name
    networks = {key: value["name"] for key, value in model["networks"].items()}
    assert sorted(networks.values()) == sorted(telemetry_plane.NETWORKS)
    assert all(value.get("external") is True for value in model["networks"].values())
    members = {
        name: {networks[n] for n in service["networks"]}
        for name, service in model["services"].items()
    }
    assert [s for s, nets in members.items() if telemetry_plane.UI_NETWORK in nets] == ["hyperdx"]
    assert [s for s, nets in members.items() if telemetry_plane.INGEST_NETWORK in nets] == [
        "gateway"
    ]
    assert telemetry_plane.NETWORKS == {
        "apg-telemetry-ingest": True, "apg-telemetry": True, "apg-telemetry-ui": False,
    }  # fmt: skip


def test_the_gateway_is_the_pinned_collector() -> None:
    """The gateway runs `OTEL_COLLECTOR_IMAGE` -- the collector every project
    pins -- with a logs-only pipeline into the `clickhouse` exporter: database
    `otel`, user `gateway` with no password, `create_schema`, a 168 h TTL, a
    bounded queue. Never ClickStack's OpAMP-supervised collector (D2573)."""
    gateway = _model()["services"]["gateway"]
    assert gateway["image"] == "${OTEL_COLLECTOR_IMAGE:?required}"
    assert gateway["restart"] == "unless-stopped"
    assert gateway["depends_on"] == {"clickhouse": {"condition": "service_healthy"}}
    config = yaml.safe_load(GATEWAY_PATH.read_text(encoding="utf-8"))
    assert set(config["service"]["pipelines"]) == {"logs"}
    exporter = config["exporters"]["clickhouse"]
    assert (exporter["database"], exporter["username"], exporter["password"]) == (
        "otel",
        "gateway",
        "",
    )
    assert exporter["create_schema"] is True and exporter["ttl"] == "168h"
    assert exporter["sending_queue"]["queue_size"] == 1000
    assert "opamp" not in GATEWAY_PATH.read_text(encoding="utf-8").lower()
    assert config["service"]["pipelines"]["logs"]["processors"][0] == "memory_limiter"


def test_the_store_has_a_ceiling_and_a_ttl() -> None:
    """ClickHouse's own `max_server_memory_usage` is 80 % of its container's
    `mem_limit`, its caches are small, every system log table that would grow
    with no TTL of ours is removed (D2605), and the logs table's TTL is the
    gateway's 168 h."""
    limit = telemetry_plane.memory_mb(_model()["services"]["clickhouse"]["mem_limit"])
    root = ET.fromstring(CLICKHOUSE_CONFIG.read_text(encoding="utf-8"))  # noqa: S314 -- our own file
    assert int(root.findtext("max_server_memory_usage")) == int(limit * 1024 * 1024 * 0.8)
    assert int(root.findtext("mark_cache_size")) == 256 * 1024 * 1024
    assert int(root.findtext("uncompressed_cache_size")) == 0
    removed = {child.tag for child in root if child.get("remove") == "1"}
    for table in (
        "query_log",
        "trace_log",
        "metric_log",
        "text_log",
        "part_log",
        "asynchronous_metric_log",
    ):
        assert table in removed, table
    assert (
        yaml.safe_load(GATEWAY_PATH.read_text("utf-8"))["exporters"]["clickhouse"]["ttl"] == "168h"
    )


def test_no_secret_in_the_compose_file() -> None:
    """HyperDX's session secret reaches it from a mounted file through a
    two-line wrapper -- no value in the model, no `EXPRESS_SESSION_SECRET` in
    its environment -- and the two defaults that send anything off the host are
    turned off (D2578, D2600, D2601). ClickHouse and MongoDB carry no password
    at all (D2578)."""
    text = MODEL_PATH.read_text(encoding="utf-8")
    hyperdx = _model()["services"]["hyperdx"]
    assert "EXPRESS_SESSION_SECRET" not in hyperdx["environment"]
    assert any("cat /run/apg/hyperdx-session" in part for part in hyperdx["entrypoint"])
    mounts = [
        m
        for m in hyperdx["volumes"]
        if isinstance(m, dict) and m["target"] == "/run/apg/hyperdx-session"
    ]
    assert len(mounts) == 1 and mounts[0]["read_only"] is True
    assert mounts[0]["source"] == str(
        telemetry_plane.STATE_DIRECTORY / telemetry_plane.SESSION_SECRET_FILE
    )
    assert hyperdx["environment"]["USAGE_STATS_ENABLED"] == "false"
    assert hyperdx["environment"]["OTEL_SDK_DISABLED"] == "true"
    assert not re.search(
        r"(?i)(password|secret|token)\s*[:=]\s*\S{8,}", text.replace("hyperdx-session", "")
    )
    assert "DEFAULT_CONNECTIONS" not in text


def test_every_image_is_locked() -> None:
    """Every image is a lock variable, and the three new ones are in
    `versions.env` by exact tag and digest (D2609)."""
    lock = dict(
        line.split("=", 1)
        for line in (REPO_ROOT / "versions.env").read_text("utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )
    for name, service in _model()["services"].items():
        variable = re.fullmatch(r"\$\{([A-Z_]+_IMAGE):\?required\}", service["image"])
        assert variable, (name, service["image"])
        assert re.fullmatch(r"\S+:\S+@sha256:[0-9a-f]{64}", lock[variable.group(1)]), name
    assert lock["CLICKHOUSE_IMAGE"].startswith(
        "docker.io/clickhouse/clickhouse-server:26.8.30.8-alpine@"
    )
    assert lock["HYPERDX_IMAGE"].startswith("docker.io/hyperdx/hyperdx:2.41.0@")
    assert lock["MONGO_IMAGE"].startswith("docker.io/library/mongo:5.0.32-focal@")


def test_the_users_admit_only_the_subnet_and_the_gateway_creates_and_inserts() -> None:
    """The rendered users file admits `gateway` and `reader` from the
    telemetry network's subnet only; `default` stays inside the container;
    the gateway holds CREATE DATABASE, CREATE TABLE and INSERT on `otel.*`
    and nothing else (D2603: measured, `create_schema` needs the first two and
    the gateway exits at start without them; SELECT it does not need)."""
    root = ET.fromstring(telemetry_plane.users_xml("192.168.48.0/20"))  # noqa: S314 -- our render
    users = root.find("users")
    assert [ip.text for ip in users.find("default/networks")] == ["::1", "127.0.0.1"]
    for name in ("gateway", "reader"):
        assert [ip.text for ip in users.find(f"{name}/networks")] == ["192.168.48.0/20"], name
        assert users.findtext(f"{name}/password") in ("", None)
    assert [q.text for q in users.find("gateway/grants")] == [
        "GRANT CREATE DATABASE ON otel.*", "GRANT CREATE TABLE ON otel.*", "GRANT INSERT ON otel.*",
    ]  # fmt: skip
    assert [q.text for q in users.find("reader/grants")] == ["GRANT SELECT ON otel.*"]
    with pytest.raises(telemetry_plane.TelemetryError):
        telemetry_plane.users_xml("192.168.48.1/20")


FAKE_DOCKER = r"""#!/usr/bin/env bash
# $FAKE_STATE/networks: "<name> <label> <internal>" per line. $FAKE_CREATE:
#   ok | race (another unit creates it, then this fails) | fail.
S="$FAKE_STATE"; touch "$S/networks"
if [ "$1 $2" = "network inspect" ]; then
  name="${@: -1}"
  line="$(grep "^$name " "$S/networks")" || exit 1
  set -- $line; echo "$2 $3"; exit 0
fi
if [ "$1 $2" = "network create" ]; then
  name="${@: -1}"; internal=false; label=""
  for a in "$@"; do
    case "$a" in --internal) internal=true ;; apg.network=*) label="${a#apg.network=}" ;; esac
  done
  case "${FAKE_CREATE:-ok}" in
    race) echo "$name $label $internal" >> "$S/networks"
          echo "Error response from daemon: network with name $name already exists" >&2; exit 1 ;;
    fail) echo "Error response from daemon: could not find an available address pool" >&2; exit 1 ;;
    *) echo "$name $label $internal" >> "$S/networks"; exit 0 ;;
  esac
fi
exit 99
"""


def _ensure(
    tmp_path: Path, name: str, internal: str, *, create: str = "ok", existing: str = ""
) -> subprocess.CompletedProcess[str]:
    bin_dir, state = tmp_path / "bin", tmp_path / "state"
    bin_dir.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    (bin_dir / "docker").write_text(FAKE_DOCKER, encoding="utf-8")
    (bin_dir / "docker").chmod(0o755)
    (state / "networks").write_text(existing, encoding="utf-8")
    return subprocess.run(
        ["bash", "-c", f". {NETWORK_HELPER}; ensure_telemetry_network {name} {internal}"],
        capture_output=True, text=True, check=False,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "FAKE_STATE": str(state), "FAKE_CREATE": create},
    )  # fmt: skip


def test_the_ingest_network_is_ensured_with_a_reread(tmp_path: Path) -> None:
    """D2563's shape for the plane's networks (D2574): a create lost to
    another unit -- Docker's "already exists" after the other unit made it --
    is read again and succeeds when the network carries the plane's label and
    the wanted `internal` flag. **Controls**: a network of that name WITHOUT
    the label (somebody else's) is refused, so is one with the wrong flag, and
    a create that fails for any other reason returns 9 with Docker's text."""
    won = _ensure(tmp_path / "a", "apg-telemetry-ingest", "yes", create="race")
    assert won.returncode == 0 and "created by another unit" in won.stderr, won.stderr
    fresh = _ensure(tmp_path / "b", "apg-telemetry-ingest", "yes")
    assert fresh.returncode == 0 and fresh.stderr == "", fresh.stderr
    foreign = _ensure(tmp_path / "c", "apg-telemetry-ingest", "yes", create="race",
                      existing="apg-telemetry-ingest <no value> true\n")  # fmt: skip
    assert foreign.returncode == 9, foreign.stderr
    flipped = "apg-telemetry-ui apg-telemetry-ui true\n"
    wrong = _ensure(tmp_path / "d", "apg-telemetry-ui", "no", existing=flipped,
                    create="race")  # fmt: skip
    assert wrong.returncode == 9, wrong.stderr
    failed = _ensure(tmp_path / "e", "apg-telemetry", "yes", create="fail")
    assert failed.returncode == 9 and "address pool" in failed.stderr, failed.stderr

"""The telemetry plane's names, its charge and its state (Session 42, ADR 0277).

The plane is ClickStack on the host (`infra/telemetry/compose.yaml`), one per
host like the edge. What this module owns is what more than one caller needs:

* **the names** -- the compose project, the three networks, the state directory
  -- written once here and held equal to the compose model by a test;
* **the charge** -- the sum of the model's four `mem_limit`s, which admission
  charges for the plane (ADR 0221 as amended by 0277: a component whose use
  follows its load has no unreclaimable figure, so its CEILING is the claim);
* **the state file** `/etc/agentic-postgres/telemetry/state.json`, written by
  `bin/telemetry.py write-state` only after admission admitted the plane, and
  read by `capacity_probe` into `Reading.platform`. Absent means the plane is
  not installed and charges nothing; present and unreadable is UNREADABLE --
  never zero (ADR 0195: a decision fails closed);
* **ClickHouse's users file**, rendered with the telemetry network's real subnet
  (Docker chooses it; on the OVH host every 172.17-31 /16 is taken).
"""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from typing import Any

from agentic_postgres import REPO_ROOT

COMPOSE_PROJECT = "apg-telemetry"
COMPOSE_PATH = REPO_ROOT / "infra" / "telemetry" / "compose.yaml"
STATE_DIRECTORY = Path("/etc/agentic-postgres/telemetry")
STATE_FILE = "state.json"
USERS_FILE = "clickhouse-users.xml"
SESSION_SECRET_FILE = "hyperdx-session"  # noqa: S105 -- a file NAME; the value is never here
#: HyperDX's image runs as `node`, uid/gid 1000 (D2600): the secret file is
#: `0440 root:<this gid>` so the container's user can read it and no other.
SESSION_SECRET_GID = 1000

#: The networks, each ensured by `telemetry.sh` (and the ingest one by every
#: project's runtime too, D2574): name -> whether it is `--internal`.
NETWORKS = {
    "apg-telemetry-ingest": True,
    "apg-telemetry": True,
    "apg-telemetry-ui": False,
}
INGEST_NETWORK = "apg-telemetry-ingest"
TELEMETRY_NETWORK = "apg-telemetry"
UI_NETWORK = "apg-telemetry-ui"
#: The label every plane network carries; a network of that name WITHOUT it is
#: somebody else's, and `ensure` refuses rather than adopting it.
NETWORK_LABEL = "apg.network"

#: The key the charge is recorded under in `Reading.platform`.
CHARGE_KEY = COMPOSE_PROJECT

#: The four services, by the model's own names.
SERVICES = ("clickhouse", "mongo", "gateway", "hyperdx")

_MEMORY = re.compile(r"^([1-9][0-9]*)([mg])$")


class TelemetryError(ValueError):
    """The model, a subnet or a state file is not what the plane writes."""


def memory_mb(value: object) -> int:
    """A compose `mem_limit` (`1152m`, `2g`) in MiB; anything else refused."""
    match = _MEMORY.match(str(value))
    if not match:
        raise TelemetryError(f"mem_limit {value!r} is not <n>m or <n>g")
    number, unit = int(match.group(1)), match.group(2)
    return number * 1024 if unit == "g" else number


def charge_mb(model: dict[str, Any]) -> int:
    """The sum of the four services' `mem_limit`s: the plane's claim.

    Exactly the four services -- a fifth (or a missing one) is refused, so a
    service added to the model without a limit cannot slip past the charge."""
    services = model.get("services") or {}
    if set(services) != set(SERVICES):
        raise TelemetryError(f"the plane's services are {sorted(services)}, not {sorted(SERVICES)}")
    return sum(memory_mb(services[name].get("mem_limit")) for name in SERVICES)


def users_xml(subnet: str) -> str:
    """ClickHouse's users file: `gateway` and `reader` admitted only from the
    telemetry network's subnet, no password (D2578); `default` only inside
    the container (the healthcheck). The gateway's grants are what the
    exporter's `create_schema` needs and nothing else (D2603)."""
    try:
        network = ipaddress.ip_network(subnet, strict=True)
    except ValueError as problem:
        raise TelemetryError(f"{subnet!r} is not a network: {problem}") from problem
    return f"""<clickhouse>
    <!-- Rendered by bin/telemetry.py (ADR 0277) with the subnet Docker gave
         {TELEMETRY_NETWORK}. No password: the store is reachable by two
         containers, and a password would keep nobody out. -->
    <profiles>
        <reader>
            <readonly>2</readonly>
            <max_memory_usage>536870912</max_memory_usage>
        </reader>
    </profiles>
    <users>
        <default>
            <password></password>
            <networks replace="replace">
                <ip>::1</ip>
                <ip>127.0.0.1</ip>
            </networks>
        </default>
        <gateway>
            <password></password>
            <networks><ip>{network}</ip></networks>
            <profile>default</profile>
            <quota>default</quota>
            <grants>
                <query>GRANT CREATE DATABASE ON otel.*</query>
                <query>GRANT CREATE TABLE ON otel.*</query>
                <query>GRANT INSERT ON otel.*</query>
            </grants>
        </gateway>
        <reader>
            <password></password>
            <networks><ip>{network}</ip></networks>
            <profile>reader</profile>
            <quota>default</quota>
            <grants>
                <query>GRANT SELECT ON otel.*</query>
            </grants>
        </reader>
    </users>
</clickhouse>
"""


def state_document(charge: int, images: dict[str, str], started_at: str) -> dict[str, Any]:
    return {
        "schema": 1,
        "charge_mb": charge,
        "images": dict(sorted(images.items())),
        "started_at": started_at,
    }


def read_charge(directory: Path) -> tuple[int | None, str | None]:
    """`(charge, None)` installed; `(None, None)` not installed (no state
    file); `(None, reason)` present and unreadable -- never a zero."""
    path = directory / STATE_FILE
    try:
        # `exists()` raises on EACCES (pathlib swallows only "not there"), and
        # an unprivileged caller meets /etc/agentic-postgres as 0700 root: that
        # is UNREADABLE -- decide refuses -- never a crash, never absent.
        if not path.exists():
            return None, None
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as problem:
        return None, f"{path} could not be read ({problem.strerror})"
    except json.JSONDecodeError:
        return None, f"{path} is not JSON"
    charge = document.get("charge_mb") if isinstance(document, dict) else None
    if not isinstance(charge, int) or isinstance(charge, bool) or charge <= 0:
        return None, f"{path} carries no positive integer charge_mb"
    return charge, None


__all__ = [
    "CHARGE_KEY",
    "COMPOSE_PATH",
    "COMPOSE_PROJECT",
    "INGEST_NETWORK",
    "NETWORKS",
    "NETWORK_LABEL",
    "SERVICES",
    "SESSION_SECRET_FILE",
    "SESSION_SECRET_GID",
    "STATE_DIRECTORY",
    "STATE_FILE",
    "TELEMETRY_NETWORK",
    "UI_NETWORK",
    "USERS_FILE",
    "TelemetryError",
    "charge_mb",
    "memory_mb",
    "read_charge",
    "state_document",
    "users_xml",
]

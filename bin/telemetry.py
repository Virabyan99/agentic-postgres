#!/usr/bin/env python3
"""The telemetry plane's decisions and files (Session 42, ADR 0277).

Invoked by `sudo bin/telemetry.sh`, which owns the Docker side (networks, the
secret, compose). Four verbs:

  admit --host FILE      Does the plane fit? The plane is the candidate, charged
                         at its CEILINGS (the four `mem_limit`s of
                         infra/telemetry/compose.yaml), against the same reading
                         and the same `decide` a project's deploy uses -- its own
                         earlier charge excluded, every project and branch
                         included. Exit 0 admitted, 12 refused (D1954's code).
  render-users --subnet NET --out FILE
                         ClickHouse's users file for that subnet (D2578, D2603).
  write-state --out-dir DIR
                         `state.json` (0644): the charge, the images, the start.
                         Written by telemetry.sh only AFTER `admit` admitted, and
                         read by every later admission as the plane's claim.
  charge                 Print the charge in MiB.

Exit codes: 0 done / admitted, 2 invalid input, 3 missing prerequisite, 12
admission refused.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import (
    REPO_ROOT,
    capacity_probe,
    capacity_reading,
    deployed_output,
    telemetry_plane,
)
from agentic_postgres.config import ManifestError

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
PROBE_TIMEOUT_SECONDS = 60
#: The images the plane runs, by their names in versions.env.
IMAGE_NAMES = ("CLICKHOUSE_IMAGE", "HYPERDX_IMAGE", "MONGO_IMAGE", "OTEL_COLLECTOR_IMAGE")


def run(
    *command: str, timeout: int = PROBE_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str] | None:
    """A daemon query, bounded; `stdin=DEVNULL` (ADR 0218). `None` when it could not complete."""
    try:
        return subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None


def _die(code: int, message: str) -> int:
    print(f"telemetry: {message}", file=sys.stderr)
    return code


def _charge() -> int:
    model = yaml.safe_load(telemetry_plane.COMPOSE_PATH.read_text(encoding="utf-8"))
    return telemetry_plane.charge_mb(model)


def _write(path: Path, text: str) -> None:
    """Written beside, then renamed into place: a reader never sees half a file."""
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(descriptor, text.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def admit(arguments: argparse.Namespace) -> int:
    charge = _charge()
    try:
        reading, ceilings_reason = capacity_probe.read(
            arguments.host, arguments.root, runner=run, exclude_platform=True
        )
    except ManifestError as problem:
        return _die(EXIT_INPUT, str(problem))
    except OSError as problem:
        return _die(EXIT_PREREQUISITE, f"the host manifest could not be read: {problem.strerror}")
    try:
        installed = (arguments.state_dir / telemetry_plane.STATE_FILE).is_file()
    except OSError:
        # Unreadable here is unreadable in the reading too, and decide refuses
        # on that; "not installed" is only the deploy-vs-redeploy wording.
        installed = False
    decision = capacity_reading.decide(
        reading,
        candidate_key=f"{telemetry_plane.CHARGE_KEY} (platform)",
        candidate_unreclaimable_mb=charge,
        candidate_is_deployed=installed,
    )
    for label, value in decision.lines:
        print(f"{label:<17} {value}")
    if ceilings_reason:
        print(f"{'ceilings':<17} unknown ({ceilings_reason})")
    print(f"{'charged at':<17} its ceilings: {charge} MiB (ADR 0277)")
    print(f"{decision.outcome}: {decision.reason}")
    return decision.exit_code


def render_users(arguments: argparse.Namespace) -> int:
    try:
        text = telemetry_plane.users_xml(arguments.subnet)
    except telemetry_plane.TelemetryError as problem:
        return _die(EXIT_INPUT, str(problem))
    _write(arguments.out, text)
    print(f"telemetry: ClickHouse users admitted from {arguments.subnet} -> {arguments.out}")
    return 0


def write_state(arguments: argparse.Namespace) -> int:
    lock = {}
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            name, _, value = line.partition("=")
            lock[name] = value
    missing = [name for name in IMAGE_NAMES if name not in lock]
    if missing:
        return _die(EXIT_PREREQUISITE, f"versions.env lacks {', '.join(missing)}")
    images = {name: lock[name] for name in IMAGE_NAMES}
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    document = telemetry_plane.state_document(_charge(), images, started)
    target = arguments.out_dir / telemetry_plane.STATE_FILE
    _write(target, json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(f"telemetry: charge {document['charge_mb']} MiB recorded in {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bin/telemetry.py", add_help=True)
    verbs = parser.add_subparsers(dest="verb", required=True)
    admitting = verbs.add_parser("admit")
    admitting.add_argument("--host", type=Path, required=True)
    admitting.add_argument("--root", type=Path, default=deployed_output.PROJECT_STATE_ROOT)
    admitting.add_argument("--state-dir", type=Path, default=telemetry_plane.STATE_DIRECTORY)
    users = verbs.add_parser("render-users")
    users.add_argument("--subnet", required=True)
    users.add_argument("--out", type=Path, required=True)
    state = verbs.add_parser("write-state")
    state.add_argument("--out-dir", type=Path, default=telemetry_plane.STATE_DIRECTORY)
    verbs.add_parser("charge")
    arguments = parser.parse_args(argv)
    if arguments.verb == "admit":
        return admit(arguments)
    if arguments.verb == "render-users":
        return render_users(arguments)
    if arguments.verb == "write-state":
        return write_state(arguments)
    print(_charge())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

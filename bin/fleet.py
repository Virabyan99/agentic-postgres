#!/usr/bin/env python3
"""The fleet inventory: every deployed project on this host (`FLEET-INV-001`).

Invoked only by `sudo bin/fleet.sh`, which has already checked root and
resolved an interpreter. Kept as its own program for `doctor.py`'s reason.

**An operator's read, and nothing else** (ADR 0185): no route, no service, no
credential, no reader. It iterates the project state root, validates each
deployed document, and for each project composes three live readings --
`bin/doctor.py --json` run as a subprocess, `systemctl is-enabled` for the two
backup timers, and a count of refusals by reason from `app_private.agent_audit`
over the cluster's container socket. **It writes nothing** (`FLEET-INV-002`).

**The doctor is composed, not re-implemented.** Running its probes in-process
would make this a second caller of every probe's internals; running the
command and reading the document it was given `--json` for is the seam
`doctor.py` exists to offer (D961). What the doctor prints is what the
operator would have seen, and its redaction (ADR 0159) is inherited whole.

Exit codes follow the convention:
  0   every project was read; verdicts are in the report
  2   invalid operator input
  4   the project root does not exist -- nothing has been deployed here
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import REPO_ROOT, deployed_output, fleet
from agentic_postgres.config import ManifestError

EXIT_INPUT = 2
EXIT_STATE = 4

#: One doctor run per project, and its own probes are each bounded (D631).
DOCTOR_TIMEOUT_SECONDS = 600
PROBE_TIMEOUT_SECONDS = 30

#: Refusals by boundary over a window. `denial_reason` is NULL on rows written
#: before migration 0027 (D940) and those are counted under `unclassified`
#: rather than dropped: a count that silently omitted rows would be a smaller
#: number that looked measured. The window is an integer this program
#: validated; no caller text reaches the statement.
DENIALS_SQL = (
    "SELECT coalesce(denial_reason::text, 'unclassified'), count(*) "
    "FROM app_private.agent_audit "
    "WHERE outcome = 'refused' AND started_at >= now() - make_interval(hours => {hours}) "
    "GROUP BY 1 ORDER BY 1"
)

MAX_WINDOW_HOURS = 24 * 365


def run(*command: str, timeout: int) -> subprocess.CompletedProcess[str] | None:
    """Every read, bounded, stdin closed (D673). None when it could not run."""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def project_keys(root: Path) -> list[str]:
    """Every directory under the root, sorted. A directory is a project the
    deploy established (`deploy-project.py` creates exactly one per key), and
    one without a document is reported rather than skipped."""
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def read_document(root: Path, key: str) -> tuple[dict[str, Any] | None, str | None]:
    path = deployed_output.deployed_path(key, root=root)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "no deployed document: the directory exists and outputs.json does not"
    except OSError:
        return None, "the deployed document could not be read"
    except ValueError:
        return None, "the deployed document is not valid JSON"
    try:
        deployed_output.validate_deployed_document(document)
    except ManifestError:
        return None, "the deployed document does not validate against the outputs schema"
    return document, None


def read_doctor(root: Path, key: str) -> tuple[dict[str, Any] | None, str | None]:
    """`bin/doctor.py --json`, as the operator would run it. Exit 0 and 6 both
    carry a document (6 is a check that failed or could not run); anything
    else is the doctor refusing, and the reason is the exit code, never its
    stderr (a third party's bytes are not this report's, ADR 0159)."""
    result = run(
        sys.executable,
        str(REPO_ROOT / "bin" / "doctor.py"),
        "--project",
        key,
        "--json",
        "--root",
        str(root),
        timeout=DOCTOR_TIMEOUT_SECONDS,
    )
    if result is None:
        return None, "the doctor could not be run"
    if result.returncode not in (0, 6):
        return None, f"the doctor exited {result.returncode}"
    # `report`, not `document`: the class guard over deployed-document readers
    # scans every read off a name spelled `document`, and this one is the
    # doctor's report, which has its own shape.
    try:
        report = json.loads(result.stdout)
    except ValueError:
        return None, "the doctor printed no document"
    if not isinstance(report, dict) or report.get("project_key") != key:
        return None, "the doctor's document names another project"
    return report, None


def read_timers(key: str) -> dict[str, str]:
    states: dict[str, str] = {}
    for kind in fleet.TIMER_KINDS:
        result = run(
            "systemctl", "is-enabled", fleet.timer_unit(kind, key), timeout=PROBE_TIMEOUT_SECONDS
        )
        states[kind] = fleet.unit_state(
            None if result is None else result.returncode, "" if result is None else result.stdout
        )
    return states


def read_denials(document: dict[str, Any], window_hours: int) -> dict[str, int] | None:
    """Counts by reason, over the container socket as root -- the route the
    doctor's database probe takes. None when the cluster could not be asked."""
    database = document.get("database") or {}
    container = database.get("container")
    name = database.get("name")
    if not container or not name:
        return None
    result = run(
        "docker",
        "exec",
        "-i",
        str(container),
        "psql",
        "-U",
        "postgres",
        "-d",
        str(name),
        "-X",
        "-qtA",
        "-F",
        "|",
        "-c",
        DENIALS_SQL.format(hours=window_hours),
        timeout=PROBE_TIMEOUT_SECONDS,
    )
    if result is None or result.returncode != 0:
        return None
    counts: dict[str, int] = {}
    for line in result.stdout.splitlines():
        reason, _, count = line.partition("|")
        if not reason:
            continue
        try:
            counts[reason.strip()] = int(count.strip())
        except ValueError:
            return None
    return counts


def inventory(root: Path, *, window_hours: int, now: datetime) -> tuple[fleet.Row, ...]:
    rows: list[fleet.Row] = []
    for key in project_keys(root):
        document, problem = read_document(root, key)
        if document is None:
            rows.append(fleet.invalid_row(key, problem or "unreadable"))
            continue
        doctor, doctor_problem = read_doctor(root, key)
        rows.append(
            fleet.row(
                key,
                document,
                doctor=doctor,
                doctor_problem=doctor_problem,
                timers=read_timers(key),
                denials=read_denials(document, window_hours),
                window_hours=window_hours,
                now=now,
            )
        )
    return tuple(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", type=Path, default=deployed_output.PROJECT_STATE_ROOT)
    parser.add_argument("--window", type=int, default=24)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)

    if not 1 <= arguments.window <= MAX_WINDOW_HOURS:
        print(f"fleet: --window must be 1..{MAX_WINDOW_HOURS} hours.", file=sys.stderr)
        return EXIT_INPUT
    root: Path = arguments.root
    if not root.is_dir():
        print(f"fleet: {root} does not exist; nothing has been deployed here.", file=sys.stderr)
        return EXIT_STATE

    now = datetime.now(UTC).replace(microsecond=0)
    observed_at = now.isoformat().replace("+00:00", "Z")
    rows = inventory(root, window_hours=arguments.window, now=now)
    if arguments.json:
        print(fleet.render_json(rows, observed_at=observed_at, window_hours=arguments.window))
    else:
        print(fleet.render_text(rows, observed_at=observed_at, window_hours=arguments.window))
    return 0


if __name__ == "__main__":
    sys.exit(main())

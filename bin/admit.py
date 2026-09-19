#!/usr/bin/env python3
"""Does this project fit on this node? (`NODE-ADMIT-001`, ADR 0221)

Invoked by `sudo bin/admit.sh`, which has already checked root and resolved an
interpreter. **Root is needed for the reading, not for the decision**:
`/etc/agentic-postgres/projects/<key>/` is `drwx------ root root`, so the
claims of the projects already deployed here are legible to nobody else
(D1606). An unprivileged run does not guess -- it reports every project's claim
as unreadable and refuses, which is the difference between a decision that
fails closed and one that admits everything because it could not see.

**It reads and decides. It renders nothing, writes nothing and starts
nothing.** A refusal must be free: this is the command an operator runs
*before* committing to a deploy, and one that left `.generated/<key>` behind
would have changed the checkout it was refusing to deploy from (D614's shape,
one command earlier). `test_admission.py` asserts the mtime set of a fixture
root is unchanged across a run.

The same `decide` runs at the deploy's step 0, from the same reading, through
the same parser. Two callers, one answer -- because a deploy that admitted
what this command refused would make the command worse than useless.

Exit codes follow the convention (`docs/session-02-operator-guide.md`):
  0   admitted
  2   invalid operator input or manifest
  3   missing local prerequisite
  12  admission refused -- the declared capacity cannot hold this project
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import (
    capacity_probe,
    capacity_reading,
    config,
    deployed_output,
    host_config,
)
from agentic_postgres.config import ManifestError
from agentic_postgres.naming import project_key as derive_project_key

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3

#: Long enough for `docker inspect` over two projects' containers, bounded so a
#: wedged daemon reports a missing ceilings line instead of hanging the command.
PROBE_TIMEOUT_SECONDS = 60


def run(
    *command: str, timeout: int = PROBE_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str] | None:
    """Every probe, bounded. `None` when it could not complete at all.

    `stdin=DEVNULL` for D673's reason and ADR 0218's: no product child reads
    the terminal. Nothing here execs into a container, so `container_exec` is
    not the right helper -- these are daemon queries, not execs.
    """
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


def _die(code: int, message: str) -> int:
    print(f"admit: {message}", file=sys.stderr)
    return code


def _injected(arguments: argparse.Namespace) -> bool:
    return any(
        value is not None
        for value in (
            arguments.declared_memory_mb,
            arguments.reserve_memory_mb,
            arguments.declared_disk_gb,
            arguments.reserve_disk_gb,
        )
    )


def _override(
    arguments: argparse.Namespace,
) -> host_config.Declared | None:
    """A rehearsal moves a threshold; it does not fill a host (ADR 0190).

    Returns `None` when nothing was injected, so the declaration is used as
    written. When anything IS injected the caller marks the printed lines
    `(injected)` -- a rehearsal's reading that could be mistaken for the host's
    is a rehearsal that proves nothing about the host.
    """
    if not _injected(arguments):
        return None

    def apply(declared: host_config.Declared | None) -> host_config.Declared | None:
        if declared is None:
            # Nothing to move. An injection cannot conjure a declaration, for
            # the reason there is no migrator: a number this program chose is
            # not a number the operator declared (ADR 0195).
            return None
        return host_config.Declared(
            memory_mb=arguments.declared_memory_mb
            if arguments.declared_memory_mb is not None
            else declared.memory_mb,
            reserve_memory_mb=arguments.reserve_memory_mb
            if arguments.reserve_memory_mb is not None
            else declared.reserve_memory_mb,
            disk_gb=arguments.declared_disk_gb
            if arguments.declared_disk_gb is not None
            else declared.disk_gb,
            reserve_disk_gb=arguments.reserve_disk_gb
            if arguments.reserve_disk_gb is not None
            else declared.reserve_disk_gb,
        )

    return apply


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=deployed_output.PROJECT_STATE_ROOT)
    parser.add_argument("--json", action="store_true")
    # A rehearsal's injections (ADR 0190). Each overrides one declared number
    # for this run only, and every one of them makes the printed declaration
    # carry `(injected)` -- the `disk_headroom` evidence pattern.
    parser.add_argument("--declared-memory-mb", type=int, default=None)
    parser.add_argument("--reserve-memory-mb", type=int, default=None)
    parser.add_argument("--declared-disk-gb", type=int, default=None)
    parser.add_argument("--reserve-disk-gb", type=int, default=None)
    arguments = parser.parse_args(argv)

    try:
        manifest = config.load_project_manifest(arguments.project)
    except ManifestError as problem:
        return _die(EXIT_INPUT, str(problem))
    except OSError as problem:
        return _die(EXIT_INPUT, f"the project manifest could not be read: {problem.strerror}")

    project = manifest["project"]
    key = derive_project_key(project["slug"], project["environment"])
    budget = config.database_budget(manifest.get("database", {}))
    requested = budget["unreclaimable_mb"]

    try:
        reading, ceilings_reason = capacity_probe.read(
            arguments.host,
            arguments.root,
            runner=run,
            exclude=key,
            declared_override=_override(arguments),
        )
    except ManifestError as problem:
        return _die(EXIT_INPUT, str(problem))
    except OSError as problem:
        return _die(EXIT_PREREQUISITE, f"the host manifest could not be read: {problem.strerror}")

    # A project is "already deployed here" when it has a document, which is the
    # same test the deploy uses to tell a first deploy from a redeploy.
    deployed_here = deployed_output.deployed_path(key, root=arguments.root).is_file()

    decision = capacity_reading.decide(
        reading,
        candidate_key=key,
        candidate_unreclaimable_mb=requested,
        candidate_is_deployed=deployed_here,
    )

    lines = list(decision.lines)
    if _injected(arguments):
        # Marked on every line rather than only the one that moved: an
        # operator reading a rehearsal's output should not have to work out
        # which figure was the host's.
        lines = [
            (label, f"{value}  (injected)")
            if label.startswith(("declared", "reserved", "safe available"))
            else (label, value)
            for label, value in lines
        ]
    if ceilings_reason:
        lines.append(("ceilings", f"unknown ({ceilings_reason})"))
    else:
        total = sum(reading.ceilings.values())
        lines.append(("ceilings", f"{total} MiB of mem_limit -- ceilings, not reservations (D767)"))
    decision = capacity_reading.Decision(
        outcome=decision.outcome, lines=tuple(lines), reason=decision.reason
    )

    if arguments.json:
        print(
            json.dumps(
                {
                    "project_key": key,
                    "outcome": decision.outcome,
                    "exit_code": decision.exit_code,
                    "requested_unreclaimable_mb": requested,
                    "already_deployed_here": deployed_here,
                    "declaration_injected": _injected(arguments),
                    "lines": [{"label": label, "value": value} for label, value in decision.lines],
                    "reason": decision.reason,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(capacity_reading.render_decision(decision))

    return decision.exit_code


if __name__ == "__main__":
    sys.exit(main())

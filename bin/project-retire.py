#!/usr/bin/env python3
"""Retire one deployed project from this host (`FLEET-RETIRE-001`, ADR 0187).

Invoked only by `sudo bin/project-retire.sh`, which has already checked root
and resolved an interpreter. Kept as its own program for `doctor.py`'s reason.

**What it removes**: what the key derives and the state records, on this
host, in `retirement.STEP_ORDER` -- the record first, then the runtime down,
the units disabled, the port allocation released under the volume's identity,
the edge files, the provider identity revoked, the state/secrets/rendered
directories, and with `--destroy-data` the two volumes. **What it never
touches**: the backup repository, the bucket, the cipher pass, the Infisical
project's secrets, the DNS record, the certificate (D957). The plan says so.

**`--defer-provider`** (D2158, ADR 0257): every step but the provider
destroy, which becomes `keep-bootstrap-state` -- the bootstrap state moved to
the slot's directory for `bin/slot.sh revoke`, the local credentials removed.
Only a slot's key may defer (a non-slot project would keep a state no command
revokes), only with the state present, never beside `--operator-credential-file`.
It exists so that the reconciler, which never holds the organisation's
credential, can delete a customer's project.

**Refusals come before anything changes** (ADR 0186): a permanent project
needs `--permanent`, an unexpired ephemeral one needs `--before-expiry`, the
key must be said back with `--confirm`, and the record path must not exist.
`--plan` prints every name and mutates nothing.

Exit codes follow the convention:
  0   retired (or, with --plan, the plan was printed)
  2   invalid input, or a refusal
  3   a prerequisite is missing -- the host manifest, the credential file
  4   no deployed document for that project -- it was never deployed here
  6   a step failed; the report names it and the steps after it did not run
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import REPO_ROOT, bootstrap_state, deployed_output, retirement, slot
from agentic_postgres.config import ManifestError
from agentic_postgres.edge_state import EDGE_DYNAMIC_DIR
from agentic_postgres.secret_generation import SECRET_ROOT

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_STATE = 4
EXIT_STEP = 6

#: Where `--defer-provider` keeps the bootstrap state, and the credential
#: directory it removes; module constants a proof may move.
SLOT_ROOT = slot.SLOT_ROOT
CREDENTIAL_ROOT = bootstrap_state.CREDENTIAL_ROOT

#: A `down` waits for containers; everything else is quick.
STEP_TIMEOUT_SECONDS = 600


def run(*command: str, timeout: int = STEP_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    """Every subprocess, bounded, stdin closed (D673)."""
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def remove_path(path: Path) -> None:
    """Remove one file or one directory tree -- never through a symlink."""
    if path.is_symlink():
        raise OSError(f"{path} is a symlink; refusing to remove through it")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def keep(source: Path, target: Path) -> str | None:
    """Move one file to where it is kept: written new (never over an existing
    one, never through a symlink), 0600 in a 0700 directory, then the source
    removed. A copy and an unlink rather than a rename, so the two may be on
    different filesystems."""
    if source.is_symlink() or not source.is_file():
        return f"{source} is not a file; there is no bootstrap state to keep"
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        source.unlink()
    except OSError as problem:
        return f"could not keep {source} at {target}: {problem}"
    return None


def fail(code: int, message: str) -> int:
    print(f"retire: {message}", file=sys.stderr)
    return code


def load_document(root: Path, key: str) -> dict[str, Any]:
    path = deployed_output.deployed_path(key, root=root)
    if not path.is_file():
        raise SystemExit(
            fail(
                EXIT_STATE, f"{key} has no deployed document at {path}; it was never deployed here."
            )
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        # D1848: a project deployed by the release before this one is still
        # retirable; its document is read by version.
        deployed_output.read_deployed_document(document)
    except (OSError, ValueError, ManifestError) as problem:
        raise SystemExit(
            fail(EXIT_STATE, f"{path} is not a valid deployed document: {problem}")
        ) from None
    return document


def unit_is_enabled(unit: str) -> bool:
    """Only an enabled unit is disabled: `systemctl disable` on an instance of
    an uninstalled template fails, and the timers are absent today (D944)."""
    result = run("systemctl", "is-enabled", unit, timeout=30)
    return result.returncode == 0


def execute(step: retirement.Step) -> str | None:
    """Perform one step; the reason it failed, or None."""
    if step.name == "disable-units":
        for command in step.commands:
            unit = command[-1]
            if not unit_is_enabled(unit):
                print(f"  {unit}: not enabled; nothing to disable")
                continue
            result = run(*command, timeout=60)
            if result.returncode != 0:
                return f"could not disable {unit} (exit {result.returncode})"
            print(f"  {unit}: disabled")
        return None
    if step.name == "remove-volumes":
        for command in step.commands:
            name = command[-1]
            if run("docker", "volume", "inspect", name, timeout=30).returncode != 0:
                return f"volume {name} does not exist; refusing to report it removed"
            result = run(*command, timeout=60)
            if result.returncode != 0:
                return f"could not remove volume {name} (exit {result.returncode})"
            print(f"  {name}: removed")
        return None
    for command in step.commands:
        result = run(*command)
        if result.returncode != 0:
            # The step's own last words, or the operator is left with a number
            # (D980): on the first real retirement step 6 reported "exited 2"
            # and nothing else, and the cause -- a loader refusal two processes
            # down -- had to be reconstructed from the source.
            said = [line for line in (result.stderr or "").splitlines() if line.strip()]
            for line in said[-8:]:
                print(f"    {line}", file=sys.stderr)
            reason = f": {said[-1].strip()}" if said else ""
            return f"{Path(command[0]).name} exited {result.returncode}{reason}"
        print(f"  ran {Path(command[0]).name}")
    for source, target in step.moves:
        problem = keep(source, target)
        if problem is not None:
            return problem
        print(f"  {source} -> {target} (0600)")
    for path in step.paths:
        if not path.exists() and not path.is_symlink():
            print(f"  {path}: already absent")
            continue
        try:
            remove_path(path)
        except OSError as problem:
            return f"could not remove {path}: {problem}"
        print(f"  {path}: removed")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--confirm", default="")
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--permanent", action="store_true")
    parser.add_argument("--before-expiry", action="store_true", dest="before_expiry")
    parser.add_argument("--destroy-data", action="store_true", dest="destroy_data")
    parser.add_argument("--operator-credential-file", type=Path, dest="credential")
    parser.add_argument("--defer-provider", action="store_true", dest="defer_provider")
    parser.add_argument("--root", type=Path, default=deployed_output.PROJECT_STATE_ROOT)
    arguments = parser.parse_args(argv)

    key: str = arguments.project
    if not retirement.PROJECT_KEY.match(key):
        return fail(EXIT_INPUT, f"not a valid project key: {key!r}")
    # The key said back, in full (bootstrap-providers.sh's rule). A --force
    # would be typed reflexively; a name that has to match cannot be.
    if not arguments.confirm:
        return fail(EXIT_INPUT, f"--confirm {key} is required. Nothing was changed.")
    if arguments.confirm != key:
        return fail(
            EXIT_INPUT,
            f"--confirm said {arguments.confirm!r} but this project is {key!r}. "
            "Nothing was changed.",
        )
    if arguments.defer_provider and arguments.credential is not None:
        return fail(
            EXIT_INPUT,
            "--defer-provider and --operator-credential-file are mutually exclusive: the "
            "identity is revoked now or kept for bin/slot.sh revoke, not both. "
            "Nothing was changed.",
        )
    if arguments.defer_provider and not slot.SLOT_KEY.fullmatch(key):
        return fail(
            EXIT_INPUT,
            f"--defer-provider is for a slot's project, and {key!r} is not a slot key: its kept "
            "state would be revoked by no command. Nothing was changed.",
        )
    retired_state = SLOT_ROOT / key / slot.RETIRED_STATE if arguments.defer_provider else None
    if not arguments.host.is_file():
        return fail(EXIT_PREREQUISITE, f"host manifest not found: {arguments.host}")

    document = load_document(arguments.root, key)
    now = datetime.now(UTC)
    why = retirement.refusal(
        dict((document.get("project") or {}).get("lifecycle") or {"kind": "permanent"}),
        permanent=arguments.permanent,
        before_expiry=arguments.before_expiry,
        now=now,
    )
    if why is not None:
        return fail(EXIT_INPUT, f"refusing: {why}. Nothing was changed.")

    try:
        resources = retirement.resources_of(
            key,
            document,
            state_root=arguments.root,
            secret_root=SECRET_ROOT,
            rendered_root=deployed_output.RENDERED_ROOT,
            edge_dynamic_dir=EDGE_DYNAMIC_DIR,
            credential_root=CREDENTIAL_ROOT,
        )
    except ValueError as problem:
        return fail(EXIT_STATE, str(problem))

    if not arguments.plan:
        if arguments.record.exists():
            return fail(EXIT_INPUT, f"{arguments.record} exists; a record is never overwritten.")
        state_file = (
            bootstrap_state.state_path(key)
            if arguments.root == deployed_output.PROJECT_STATE_ROOT
            else arguments.root / key / "bootstrap-state.json"
        )
        if retired_state is not None:
            if not state_file.is_file():
                return fail(
                    EXIT_PREREQUISITE,
                    f"--defer-provider keeps the bootstrap state, and {state_file} does not "
                    "exist: there is nothing to defer. Nothing was changed.",
                )
            if retired_state.exists() or retired_state.is_symlink():
                return fail(
                    EXIT_INPUT,
                    f"{retired_state} exists; a kept state is never overwritten. "
                    "Nothing was changed.",
                )
        elif state_file.exists() and arguments.credential is None:
            return fail(
                EXIT_PREREQUISITE,
                "the project's bootstrap state exists, so --destroy needs "
                "--operator-credential-file (or, for a slot, --defer-provider). "
                "Nothing was changed.",
            )
        if arguments.credential is not None and not arguments.credential.is_file():
            return fail(EXIT_PREREQUISITE, f"credential file not found: {arguments.credential}")

    plan = retirement.steps(
        resources,
        host_manifest=arguments.host,
        root_dir=REPO_ROOT,
        destroy_data=arguments.destroy_data,
        operator_credential_file=arguments.credential,
        retired_state=retired_state,
    )
    print(
        retirement.render_plan(
            resources, plan, record_path=arguments.record, executing=not arguments.plan
        )
    )
    if arguments.plan:
        return 0

    print("")
    for index, step in enumerate(plan, start=1):
        print(f"retire: {index}. {step.name}")
        if step.name == "record":
            document_out = retirement.record(
                resources,
                captured_at=now,
                destroy_data=arguments.destroy_data,
                record_path=arguments.record,
                retired_state=retired_state,
            )
            descriptor = os.open(arguments.record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document_out, handle, indent=2, sort_keys=True)
                handle.write("\n")
            print(f"  wrote {arguments.record} (0600)")
            continue
        problem = execute(step)
        if problem is not None:
            return fail(
                EXIT_STEP,
                f"step {index} ({step.name}) failed: {problem}. The steps after it did not run; "
                f"the record at {arguments.record} says what was intended.",
            )

    print("")
    print(f"retire: {key} is retired from this host.")
    print(
        retirement.record(
            resources,
            captured_at=now,
            destroy_data=arguments.destroy_data,
            record_path=arguments.record,
            retired_state=retired_state,
        )["backups_still_held"]
    )
    if retired_state is not None:
        print(
            f"The runtime identity is NOT revoked: its bootstrap state is kept at {retired_state} "
            "for `sudo bin/slot.sh revoke`."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

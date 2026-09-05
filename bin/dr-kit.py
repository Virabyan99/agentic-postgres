#!/usr/bin/env python3
"""The disaster kit: `export` writes one, `verify` checks one (ADR 0189).

Invoked only by `bin/dr-kit.sh`, which has already resolved an interpreter and,
for `export`, checked root -- the bootstrap state and the deployed document
are root-owned on a host. Kept as its own program for `doctor.py`'s reason.

`export` copies the host and capability manifests and, per project, the
project manifest, `bootstrap-state.json` and the deployed document, and writes
`secrets.txt` from the contract; `dr_kit.plan_export` validates every one of
them on the way in and nothing here opens a secret generation, a credential
file or the provider. The output directory must not exist: a kit is written
whole or not at all, and a directory that already holds something is a kit
somebody may be relying on.

`verify DIR` prints every problem and exits 5 on any. Both verbs print no value,
because neither ever holds one.

Exit codes (runbook section 2 convention):
  0  the kit was written, or verified
  2  invalid operator input
  3  a prerequisite is missing: an unreadable state file, no root on a host
  5  the kit does not verify
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import CURRENT_SESSION, REPO_ROOT, deployed_output, dr_kit, installed_release
from agentic_postgres.secrets_contract import load_secret_contract

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_INVALID = 5


def fail(code: int, message: str) -> int:
    print(f"dr-kit: {message}", file=sys.stderr)
    return code


def release_commit() -> str | None:
    """The checkout's commit, for the kit's record; None outside a release."""
    try:
        return installed_release.resolve_commit(REPO_ROOT)
    except Exception:  # a kit from a bare checkout still verifies
        return None


def export(arguments: argparse.Namespace) -> int:
    output: Path = arguments.output
    if output.exists():
        return fail(
            EXIT_INPUT,
            f"{output} exists; a kit is written into a directory that does not. Choose "
            "another path, or remove the old kit deliberately.",
        )
    contract = load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    try:
        entries = dr_kit.plan_export(
            host_path=arguments.host,
            capabilities_path=arguments.capabilities,
            project_paths=tuple(arguments.project),
            state_root=arguments.state_root,
            contract=contract,
            session=arguments.session,
        )
    except PermissionError as problem:
        return fail(EXIT_PREREQUISITE, f"{problem}; the state root is root-owned on a host")
    except dr_kit.KitError as problem:
        return fail(EXIT_INPUT, str(problem))

    exported_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = dr_kit.kit_manifest(
        entries, exported_at=exported_at, release=release_commit(), session=arguments.session
    )
    # Owner-only from the first byte: the kit carries no value, but it carries
    # every identifier a replacement host adopts by, and it is about to leave
    # this host on whatever medium the operator chose.
    os.makedirs(output, mode=0o700)
    try:
        for entry in entries:
            path = output / entry.relative
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with open(path, "wb", opener=lambda p, f: os.open(p, f, 0o600)) as stream:
                stream.write(entry.content)
        with open(
            output / dr_kit.KIT_MANIFEST,
            "w",
            encoding="utf-8",
            opener=lambda p, f: os.open(p, f, 0o600),
        ) as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except OSError as problem:
        shutil.rmtree(output, ignore_errors=True)
        return fail(EXIT_PREREQUISITE, f"could not write the kit: {problem}; nothing was left")

    problems = dr_kit.verify_kit(output)
    if problems:
        shutil.rmtree(output, ignore_errors=True)
        for problem in problems:
            print(f"dr-kit: {problem}", file=sys.stderr)
        return fail(EXIT_INVALID, "the kit just written does not verify; it was removed")

    print(
        f"dr-kit: wrote {output} ({len(entries)} artifacts, {len(manifest['projects'])} projects)"
    )
    for entry in entries:
        print(f"  {entry.relative}")
    print(
        "dr-kit: no value is in it. Copy it OFF this host now; it is what a replacement "
        "is built from."
    )
    return 0


def verify(arguments: argparse.Namespace) -> int:
    problems = dr_kit.verify_kit(arguments.directory)
    if problems:
        for problem in problems:
            print(f"dr-kit: {problem}", file=sys.stderr)
        return fail(
            EXIT_INVALID, f"{arguments.directory} does not verify ({len(problems)} problem(s))"
        )
    manifest = json.loads((arguments.directory / dr_kit.KIT_MANIFEST).read_text(encoding="utf-8"))
    print(
        f"dr-kit: {arguments.directory} verifies: {len(manifest['artifacts'])} artifacts for "
        f"{', '.join(manifest['projects'])}, exported {manifest['exported_at']} from release "
        f"{manifest.get('release') or 'unknown'}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dr-kit", description=__doc__)
    verbs = parser.add_subparsers(dest="verb", required=True)

    exporter = verbs.add_parser("export", help="write a kit")
    exporter.add_argument("--host", type=Path, required=True)
    exporter.add_argument("--capabilities", type=Path, required=True)
    exporter.add_argument("--project", type=Path, action="append", required=True)
    exporter.add_argument("--output", type=Path, required=True)
    exporter.add_argument("--state-root", type=Path, default=deployed_output.PROJECT_STATE_ROOT)
    exporter.add_argument("--session", type=int, default=CURRENT_SESSION)
    exporter.set_defaults(handler=export)

    verifier = verbs.add_parser("verify", help="check a kit is whole")
    verifier.add_argument("directory", type=Path)
    verifier.set_defaults(handler=verify)

    arguments = parser.parse_args(argv)
    if getattr(arguments, "session", 1) < 1:
        return fail(EXIT_INPUT, "--session must be a positive integer")
    return int(arguments.handler(arguments))


if __name__ == "__main__":
    sys.exit(main())

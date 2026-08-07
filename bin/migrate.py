#!/usr/bin/env python3
"""The migration plane's work. Invoked only by ``bin/migrate.sh``.

Split from the shell for the same reason ``bin/postgres-bootstrap.py`` is: the
script owns the operator surface and the privilege gate, and digest comparison
written in bash is a string comparison somebody eventually relaxes to a prefix.

``freeze-lock`` and ``verify-lock`` share one implementation of what the lock
should contain (``migrations.build_lock``). A gate that verified with different
code than the one that wrote the lock would be checking its own arithmetic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import migrations

EXIT_CONTRACT = 5


def render_set(document: dict) -> list[tuple[str, str, str]]:
    """(version, name, rendered digest) for this project, in applied order."""
    manifest = migrations.load_manifest()
    rendered = []
    for entry in manifest["migrations"]:
        payload = migrations.render_migration(entry, manifest, document)
        rendered.append((entry["version"], entry["name"], migrations.digest(payload)))
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--outputs")
    arguments = parser.parse_args()

    try:
        if arguments.mode == "freeze-lock":
            manifest = migrations.load_manifest()
            lock = migrations.build_lock(manifest)
            migrations.LOCK_PATH.write_text(
                json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(f"migrate: wrote {migrations.LOCK_PATH} ({len(lock['migrations'])} migrations)")
            print("  Review and commit it before the gate runs.")
            return 0

        if arguments.mode == "verify-lock":
            manifest = migrations.load_manifest()
            migrations.verify_lock(manifest, migrations.load_lock())
            print("migrate: the released lock agrees with the manifest and templates")
            return 0

        document = json.loads(Path(arguments.outputs).read_text(encoding="utf-8"))

        # Every path that touches a project verifies the lock first. A render
        # or an apply against a manifest the lock does not cover is the state
        # ADR 0028 exists to prevent, and checking it here means no caller has
        # to remember to.
        manifest = migrations.load_manifest()
        migrations.verify_lock(manifest, migrations.load_lock())

        if arguments.mode == "render":
            for version, name, sha in render_set(document):
                print(f"{version}  {sha[:16]}  {name}")
            return 0

        if arguments.mode in ("status", "up"):
            print(
                f"migrate: {arguments.mode} is executed by dbmate over the project network "
                "as migration_user; the rendered set for this project is:"
            )
            for version, name, sha in render_set(document):
                print(f"  {version}  {sha[:16]}  {name}")
            return 0

    except migrations.MigrationError as error:
        print(f"migrate: {error}", file=sys.stderr)
        return EXIT_CONTRACT

    print(f"migrate: unknown mode {arguments.mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

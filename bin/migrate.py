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
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import migrations, rendering

EXIT_CONTRACT = 5

REPO_ROOT = Path(__file__).resolve().parents[1]


def render_set(document: dict) -> list[tuple[str, str, str]]:
    """(version, name, rendered digest) for this project, in applied order."""
    manifest = migrations.load_manifest()
    rendered = []
    for entry in manifest["migrations"]:
        payload = migrations.render_migration(entry, manifest, document)
        rendered.append((entry["version"], entry["name"], migrations.digest(payload)))
    return rendered


def assert_rendered_files_match(rendered_dir: str) -> None:
    """The files dbmate will read are the payloads this release rendered.

    dbmate is handed a directory, not a list, so what it applies is whatever is
    in that directory. Comparing each file's digest against the manifest written
    beside it -- and the set of files against the set of migrations -- is what
    makes "the rendered payload is the immutable unit" (ADR 0028) a property of
    the thing that runs rather than of the thing that was committed.
    """
    directory = Path(rendered_dir) / "migrations"
    manifest_path = directory / rendering.MIGRATION_MANIFEST_NAME
    if not manifest_path.is_file():
        raise migrations.MigrationError(
            f"no rendered migration manifest at {manifest_path}; "
            "this project was rendered by a release that did not write one."
        )

    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {entry["file"]: entry["sha256"] for entry in recorded["migrations"]}
    found = {path.name for path in directory.glob("*.sql")}

    if found != set(expected):
        raise migrations.MigrationError(
            f"the rendered migration directory does not match its manifest: "
            f"unexpected {sorted(found - set(expected))}, missing {sorted(set(expected) - found)}"
        )

    for filename, sha in sorted(expected.items()):
        actual = migrations.digest((directory / filename).read_text(encoding="utf-8"))
        if actual != sha:
            raise migrations.MigrationError(
                f"{filename} does not match the payload that was rendered "
                f"({actual[:16]} != {sha[:16]}); it was edited after rendering."
            )


def run_dbmate(mode: str, document: dict, rendered_dir: str) -> int:
    """Run one dbmate subcommand through bin/compose.sh, as migration_user.

    Through the wrapper, never `docker` directly: the wrapper is what pins the
    env files, refuses a secret source outside this project's own tree, and
    resolves the model the release committed. A `docker compose run` here would
    be a second way to start a container in this repository, and it would be
    the one nothing audits.
    """
    command = [
        str(REPO_ROOT / "bin" / "compose.sh"),
        rendered_dir,
        "--runtime",
        "--profile",
        "migration",
        "run",
        "--rm",
        "dbmate",
        mode,
    ]
    if mode == "up":
        # Subcommand-only, and it exists on `up` but not on `status` -- measured
        # in tests/contract/test_image_contracts.py. Without it dbmate applies
        # what it can and exits 0 on a partially applied set.
        command.append("--strict")

    print(f"migrate: {mode} as {document['database']['roles']['migration_user']}")
    result = subprocess.run(command, check=False)
    if result.returncode != 0 or mode != "up":
        return result.returncode

    return record_ledger(document, rendered_dir)


def record_ledger(document: dict, rendered_dir: str) -> int:
    """Write what actually ran into app_private.migration_ledger.

    The table has existed since migration 0002 and nothing has ever written to
    it (D62). An empty ledger makes the convergence check the plan asks for --
    "identical ledger checksums" -- a comparison of two absences.

    Written by this program over the container socket as the superuser, *not*
    by the migration plane. dbmate's `schema_migrations` records that a version
    ran; this records which bytes ran, and a migration role that could write its
    own audit record could record bytes it did not execute. migration_user has
    no privilege on this table at all, which is the property that makes the row
    worth reading.
    """
    manifest = migrations.load_manifest()
    templates = {entry["version"]: entry for entry in migrations.build_lock(manifest)["migrations"]}
    rendered = json.loads(
        (Path(rendered_dir) / "migrations" / rendering.MIGRATION_MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
    )

    values = []
    for entry in rendered["migrations"]:
        template = templates[entry["version"]]
        values.append(
            "("
            + ", ".join(
                migrations.quote_literal(value)
                for value in (
                    entry["version"],
                    entry["name"],
                    template["template_sha256"],
                    entry["sha256"],
                )
            )
            + ")"
        )

    # ON CONFLICT DO NOTHING, so a re-run records nothing new and changes no
    # applied_at. That is what makes the second `up` of a convergence check
    # produce an identical ledger rather than a fresh set of timestamps.
    statement = (
        "INSERT INTO app_private.migration_ledger "  # noqa: S608
        "(version, name, template_sha256, rendered_sha256) VALUES "
        + ", ".join(values)
        + " ON CONFLICT (version) DO NOTHING;"
    )

    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            document["database"]["container"],
            "psql",
            "-U",
            "postgres",
            "-d",
            document["database"]["name"],
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-qtA",
            "-f",
            "-",
        ],
        input=statement,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            f"migrate: the ledger could not be recorded: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_CONTRACT

    print(f"migrate: ledger recorded for {len(values)} migrations")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--outputs")
    parser.add_argument("--rendered-dir")
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
            # The rendered set, then the ledger. Both, in that order, and the
            # first is not a substitute for the second: until Run 7 this printed
            # the set and returned 0, so `migrate up` reported success having
            # applied nothing at all (D60). Printing what *should* be applied is
            # only useful next to what a cluster says is applied.
            rendered = render_set(document)
            print(f"migrate: the rendered set for this project ({len(rendered)}):")
            for version, name, sha in rendered:
                print(f"  {version}  {sha[:16]}  {name}")

            if not arguments.rendered_dir:
                print("migrate: --rendered-dir is required for status and up", file=sys.stderr)
                return 2

            assert_rendered_files_match(arguments.rendered_dir)
            return run_dbmate(arguments.mode, document, arguments.rendered_dir)

    except migrations.MigrationError as error:
        print(f"migrate: {error}", file=sys.stderr)
        return EXIT_CONTRACT

    print(f"migrate: unknown mode {arguments.mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

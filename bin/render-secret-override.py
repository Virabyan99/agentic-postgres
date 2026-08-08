#!/usr/bin/env python3
"""Write the Compose grant surface for the generation that is active now.

Invoked by ``bin/project-runtime.sh`` between materialization and ``compose
up``, and by nothing else. It is a separate command rather than inline Python
in the shell for the reason every other split here exists: the block it writes
is a document with a schema-shaped structure, and building YAML by string
concatenation in bash is how an indentation bug becomes a container that starts
without its secret.

It reads a *pointer* and a *contract* and writes *paths*. No secret value is
opened, and the file it writes is a set of filesystem paths that already exist
on this host with ownership the materializer set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import secret_override
from agentic_postgres.secrets_contract import SECRET_ROOT, load_secret_contract

EXIT_INPUT = 2
EXIT_PRECONDITION = 4


def fail(code: int, message: str) -> None:
    print(f"render-secret-override: {message}", file=sys.stderr)
    raise SystemExit(code)


def active_generation(project_key: str) -> str:
    pointer = Path(SECRET_ROOT) / project_key / "active-secret-generation.json"
    if not pointer.exists():
        fail(
            EXIT_PRECONDITION,
            f"no active secret generation for {project_key}; "
            "bin/materialize-secrets.sh has not run on this host.",
        )
    generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
    if not generation:
        fail(EXIT_PRECONDITION, f"{pointer} names no generation.")
    return str(generation)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--session", required=True, type=int)
    parser.add_argument("--rendered-dir", required=True, type=Path)
    arguments = parser.parse_args()

    if arguments.session < 1:
        fail(EXIT_INPUT, "--session must be a positive integer")
    if not arguments.requirements.is_file():
        fail(EXIT_INPUT, f"no secret contract at {arguments.requirements}")
    if not arguments.rendered_dir.is_dir():
        fail(EXIT_PRECONDITION, f"no rendered directory at {arguments.rendered_dir}")

    contract = load_secret_contract(arguments.requirements)
    payload = secret_override.render_secret_override(
        project_key=arguments.project_key,
        generation_id=active_generation(arguments.project_key),
        contract=contract,
        session=arguments.session,
    )

    destination = arguments.rendered_dir / secret_override.OVERRIDE_FILENAME

    # Same write discipline as the runtime override: owner-only, and replaced
    # atomically. A half-written grant surface is a model Compose either
    # rejects or -- worse -- accepts with one service's mount missing.
    handle, staging = tempfile.mkstemp(dir=str(arguments.rendered_dir), prefix=".secrets-override.")
    with os.fdopen(handle, "wb") as stream:
        stream.write(payload)
    os.chmod(staging, 0o600)
    os.replace(staging, destination)

    print(f"render-secret-override: wrote {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

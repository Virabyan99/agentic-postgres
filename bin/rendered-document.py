#!/usr/bin/env python3
"""Resolve a project's rendered document, and say which failure it is.

ADR 0199, D1060. Three shells -- `bin/migrate.sh`, `bin/db.sh` and
`bin/postgres-bootstrap.sh` -- each carried

    [ -f "${document}" ] || die 4 "... the project was never deployed here."

and `[ -f ... ]` answers **false for both** a missing file and one inside a
directory this user cannot traverse. After a root deploy `.generated/<key>` is
root-owned, so `op` got *"the project was never deployed here"* about a project
deployed forty minutes earlier -- measured on the host on 2026-09-10, with beta
as the control.

This exists so there is ONE reader rather than three, and so the reader is in
Python where the errno is available. A shell can distinguish the two cases
(`[ -e ]` beside `[ -r ]`, or `stat`), and that is exactly the sort of thing
each of the three would eventually spell differently -- which is how there came
to be three copies of one wrong answer.

Prints the path on success. Exits:

  0  the document is there and readable; its path is on stdout
  3  it exists and cannot be read, naming the owner and the remedy
  4  it is not there
  5  it is there and is not valid JSON

The path goes to stdout and every diagnostic to stderr, so a caller can
`document="$(... )"` without capturing a message.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import deployed_output
from agentic_postgres.config import ManifestError

EXIT_UNREADABLE = 3
EXIT_ABSENT = 4
EXIT_MALFORMED = 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rendered-document",
        description="Resolve a project's rendered document (ADR 0199).",
        allow_abbrev=False,
    )
    parser.add_argument("--project-key", required=True)
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="read the INSTALLED render under /var/lib rather than the checkout's",
    )
    arguments = parser.parse_args(argv)

    try:
        path, _ = deployed_output.read_rendered_document(
            arguments.project_key, runtime=arguments.runtime
        )
    except deployed_output.RenderedDocumentUnreadable as error:
        print(f"{error}", file=sys.stderr)
        return EXIT_UNREADABLE
    except deployed_output.RenderedDocumentAbsent as error:
        print(f"{error}", file=sys.stderr)
        return EXIT_ABSENT
    except ManifestError as error:
        print(f"{error}", file=sys.stderr)
        return EXIT_MALFORMED

    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

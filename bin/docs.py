#!/usr/bin/env python
"""The documentation route: where it is, and whether it is refusing correctly.

Two operations, and neither reads a credential. See `bin/docs.sh` for why there
is no operation that authenticates: the Basic Auth password is materialized into
the root plane for the edge to hash, the documentation container never receives
it, and a command that logged you in would have to put it in a URL, an argument
or a browser's history -- all three worse than a prompt.

`check` proves the negative half of `SEC-DOCS-001`. It is deliberately not
satisfied by silence: a route that cannot be reached at all is reported as
unreachable rather than as refusing, because "nothing answered" and "it said no"
are the same result to a test that only looks for the absence of a 200.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REQUEST_TIMEOUT_SECONDS = 20


class DocsError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def docs_url(document: dict[str, Any]) -> str:
    if document.get("document_kind") != "deployed":
        raise DocsError(2, "that is a rendered document; the docs route is an observation")
    route = ((document.get("routes") or {}).get("docs")) or {}
    if route.get("status") != "ready" or not route.get("url"):
        raise DocsError(
            5,
            "the deployed document publishes no ready documentation route. Every "
            "project deployed through a session before 5 is in that state.",
        )
    url = route["url"]
    if urlsplit(url).scheme != "https":
        raise DocsError(5, f"routes.docs.url is not https: {url!r}")
    return url


def check(url: str) -> int:
    """Request with no credential. A 401 with a Basic challenge is the success."""
    request = urllib.request.Request(url, method="GET")  # noqa: S310 — https asserted above
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
            print(
                f"docs: the route answered {response.status} WITHOUT a credential. The "
                "documentation is being served to anyone who asks.",
                file=sys.stderr,
            )
            return 6
    except urllib.error.HTTPError as error:
        challenge = error.headers.get("WWW-Authenticate", "")
        if error.code != 401:
            print(
                f"docs: the route answered {error.code}, not 401. It is not serving the "
                "documentation, but it is not refusing with a challenge either.",
                file=sys.stderr,
            )
            return 6
        if "Basic" not in challenge:
            # A 401 without a challenge is a refusal a browser cannot act on,
            # and it is also what a misconfigured middleware chain produces.
            print(
                "docs: the route answered 401 with no Basic challenge "
                f"(WWW-Authenticate: {challenge!r}). A browser has nothing to prompt for.",
                file=sys.stderr,
            )
            return 6
        print(f"docs: {url} refuses without a credential (401, Basic challenge).")
        return 0
    except urllib.error.URLError as error:
        # Reported as unreachable, not as refusing. "Nothing answered" and "it
        # said no" are the same result to a check that only looks for the
        # absence of a 200, and only one of them is the boundary working.
        raise DocsError(3, f"cannot reach the documentation route: {error.reason}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docs", allow_abbrev=False)
    parser.add_argument("--project-outputs", metavar="FILE", required=True)
    parser.add_argument("operation", choices=["url", "check"])
    arguments = parser.parse_args(argv)

    path = Path(arguments.project_outputs)
    try:
        if not path.is_file():
            raise DocsError(2, f"deployed document not found: {path}")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DocsError(2, f"cannot read {path}: {error}") from error

        url = docs_url(document)
        if arguments.operation == "url":
            print(url)
            return 0
        return check(url)
    except DocsError as error:
        print(f"docs: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    raise SystemExit(main())

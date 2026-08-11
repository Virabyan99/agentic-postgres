#!/usr/bin/env python
"""Call the published REST surface. Enumerated operations, and nothing else.

There is no `--url`, no `--method`, no `--header`, no `--path` and no way to
pass an option through to a transfer library. Each operation below names one
path and one method, both derived from the deployed document and the reviewed
surface contract; the caller chooses *which operation*, never *what request*.

That is narrower than a debugging tool wants to be, and the narrowness is the
feature. A broker that will issue any request against a project's API is a
credential holder that will do anything the credential can -- which makes it, in
an incident, indistinguishable from the thing you are investigating.

The token is read from the environment and never printed. `bin/dev-token.sh`
puts it there; this command never mints one, so there is no path here that
touches the signing key at all.

Exit codes (runbook §2 convention):
  0  success
  2  invalid operator input
  3  missing local prerequisite
  5  the deployed document is unusable
  6  the service refused the request
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import api_surface

TOKEN_VARIABLE = "APG_API_TOKEN"  # noqa: S105 — a variable name

REQUEST_TIMEOUT_SECONDS = 30

#: Every operation this command can perform, as (method, path). The paths are
#: the reviewed surface's objects and the document's own root; a path that is
#: not here cannot be reached through this tool whatever the token allows.
OPERATIONS: dict[str, tuple[str, str]] = {
    "openapi": ("GET", "/"),
    "list-notes": ("GET", "/notes"),
    "list-tasks": ("GET", "/tasks"),
    "create-note": ("POST", "/rpc/create_note"),
    "update-task-status": ("POST", "/rpc/update_task_status"),
}


class ApiError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_deployed(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ApiError(2, f"deployed document not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ApiError(2, f"cannot read {path}: {error}") from error
    if document.get("document_kind") != "deployed":
        raise ApiError(2, "that is a rendered document; the REST route is an observation")
    return document


def rest_base(document: dict[str, Any]) -> str:
    rest = ((document.get("routes") or {}).get("rest")) or {}
    if rest.get("status") != "ready" or not rest.get("url"):
        raise ApiError(
            5,
            "the deployed document publishes no ready REST route. Every project "
            "deployed through a session before 5 is in that state.",
        )
    url = rest["url"].rstrip("/")
    if urlsplit(url).scheme != "https":
        raise ApiError(5, f"routes.rest.url is not https: {rest['url']!r}")
    return url


def statuses() -> list[str]:
    """The task statuses, read from the reviewed contract rather than typed here.

    A second copy of the enum is a second authority, and this one would be the
    permissive half: a status this tool accepts and the type does not becomes a
    400 from the database, and one the type has and this does not is an
    operation nobody can perform through the broker.
    """
    return list(api_surface.load_surface()["enums"]["task_status"]["values"])


def perform(url: str, method: str, body: dict[str, Any] | None) -> tuple[int, str]:
    token = os.environ.get(TOKEN_VARIABLE, "")
    if not token:
        raise ApiError(
            3,
            f"{TOKEN_VARIABLE} is empty. Run this under bin/dev-token.sh, which puts a "
            "short-lived token in this process's environment:\n"
            "  sudo bin/dev-token.sh --project-outputs FILE --role authenticated -- "
            "bin/api.sh ...",
        )

    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method)  # noqa: S310 — https asserted
    request.add_header("Accept", "application/json")
    request.add_header("Authorization", f"Bearer {token}")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
        request.add_header("Prefer", "return=representation")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")
    except urllib.error.URLError as error:
        raise ApiError(3, f"cannot reach the REST service: {error.reason}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="api",
        description="Call the published REST surface through enumerated operations.",
        allow_abbrev=False,
    )
    parser.add_argument("--project-outputs", metavar="FILE", required=True)
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--title", metavar="TEXT")
    parser.add_argument("--content", metavar="TEXT")
    parser.add_argument("--task-id", metavar="UUID")
    parser.add_argument("--expected-status", metavar="STATUS")
    parser.add_argument("--new-status", metavar="STATUS")

    arguments = parser.parse_args(argv)

    try:
        document = load_deployed(Path(arguments.project_outputs))
        method, path = OPERATIONS[arguments.operation]
        body: dict[str, Any] | None = None

        if arguments.operation == "create-note":
            if not arguments.title:
                raise ApiError(2, "create-note requires --title")
            body = {"p_title": arguments.title, "p_content": arguments.content or ""}
        elif arguments.operation == "update-task-status":
            allowed = statuses()
            missing = [
                name
                for name, value in (
                    ("--task-id", arguments.task_id),
                    ("--expected-status", arguments.expected_status),
                    ("--new-status", arguments.new_status),
                )
                if not value
            ]
            if missing:
                raise ApiError(2, f"update-task-status requires {', '.join(missing)}")
            for name, value in (
                ("--expected-status", arguments.expected_status),
                ("--new-status", arguments.new_status),
            ):
                if value not in allowed:
                    raise ApiError(2, f"{name} must be one of {allowed}, got {value!r}")
            body = {
                "p_task_id": arguments.task_id,
                "p_expected_status": arguments.expected_status,
                "p_new_status": arguments.new_status,
            }

        # `quote` on nothing the caller supplied -- the path is a constant from
        # OPERATIONS. Applied anyway so that a later operation carrying a
        # segment cannot introduce one without passing through an escape.
        url = rest_base(document) + quote(path)
        status, text = perform(url, method, body)
    except ApiError as error:
        print(f"api: {error}", file=sys.stderr)
        return error.code

    print(text)
    if status >= 400:
        print(f"api: the service answered {status}", file=sys.stderr)
        return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Capture, compare and refuse to approve the reviewed API surface (ADR 0050).

The split this file implements is the whole decision:

``update``  is privileged, runs against a deployed release, fetches the live
            document, normalizes it and **streams the candidate to stdout**.
            There is no output-path option, and that is not an omission: the
            operator's own shell does the redirect, so the candidate lands owned
            by the unprivileged source owner who has to review and commit it,
            even though the capture ran under `sudo`.
``check``   compares, and contains no writer at all. Offline it compares the
            committed snapshot against the committed surface contract. Given a
            deployed document it also fetches the live document and compares
            that. The gate runs only this.

What ``check`` deliberately does *not* compare is the method list. ADR 0060:
`openapi-mode = follow-privileges` filters the path and not the methods on it,
so a role holding `SELECT` is served a document advertising `delete`, `patch`
and `post` — all three of which return 403. The contract's `methods:` is
enforced against the catalog by `API-RPC-001`, where it is true.

Exit codes (runbook §2 convention):
  0  success
  2  invalid operator input
  3  missing local prerequisite
  5  the contracts are out of sync, or no approved snapshot exists yet
  6  the live document disagrees with the approved snapshot
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
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import REPO_ROOT, api_surface, openapi_normalize
from agentic_postgres.config import ManifestError
from agentic_postgres.openapi_normalize import NormalizationError

#: The generated half of ADR 0050's pair. A fixed path, for the reason
#: `api_surface.CONTRACT_PATH` is fixed: a contract that can be pointed
#: somewhere else is a contract that can be pointed at a copy of the thing it
#: constrains.
SNAPSHOT_PATH = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"

#: The environment variable a short-lived documentation token arrives in. D105's
#: rule: never argv. An environment variable is readable by the process's own
#: user through /proc, which argv is readable by *everyone* through `ps`.
TOKEN_VARIABLE = "APG_DOCS_TOKEN"  # noqa: S105 — the variable's name, not a value

#: How long the capture will wait for a document. Long enough for a cold schema
#: cache, short enough that a hung capture fails rather than holding a host lock.
FETCH_TIMEOUT_SECONDS = 30


class ContractError(Exception):
    """Carries the exit code the runbook convention assigns to the failure."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Reading what the deployment published
# ---------------------------------------------------------------------------


def published_address(deployed: dict[str, Any]) -> tuple[str, str]:
    """`(host, basePath)` as the served document will spell them.

    Derived from `routes.rest.url` in the deployed document rather than from a
    manifest, because a manifest describes what was asked for and a deployed
    document describes what happened — D132's rule, applied to the one value the
    whole comparison hangs on.

    The `:443` is measured, not assumed: given `openapi-server-proxy-uri` of
    `https://alpha.example.test/api/rest`, the locked PostgREST published
    `host: "alpha.example.test:443"` and `basePath: "/api/rest"`. A derivation
    that dropped the port would refuse every correct capture.
    """
    routes = deployed.get("routes") or {}
    rest = routes.get("rest") or {}
    if rest.get("status") != "ready" or not rest.get("url"):
        raise ContractError(
            2,
            "the deployed document publishes no ready REST route. A project deployed "
            "through a session before 5 has none, and there is nothing to capture.",
        )

    parts = urlsplit(rest["url"])
    if parts.scheme != "https" or not parts.netloc:
        raise ContractError(5, f"routes.rest.url is not an https URL: {rest['url']!r}")

    host = parts.netloc if ":" in parts.netloc else f"{parts.netloc}:443"
    base_path = parts.path or "/"
    return host, base_path


def load_deployed(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(2, f"deployed document not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(2, f"cannot read {path}: {error}") from error
    if not isinstance(document, dict):
        raise ContractError(2, f"{path} is not an outputs document")
    return document


# ---------------------------------------------------------------------------
# Fetching the live document
# ---------------------------------------------------------------------------


def fetch_live(url: str) -> bytes:
    """GET the served OpenAPI document. No caller-supplied URL, method or header.

    The URL is built from the deployed document; the token comes out of the
    environment and is never echoed. Any failure is reported by class rather
    than by body, because the body of a failed fetch is the one place a
    misconfigured service prints things it should not.
    """
    token = os.environ.get(TOKEN_VARIABLE, "")
    if not token:
        raise ContractError(
            3,
            f"{TOKEN_VARIABLE} is empty. The capture needs a short-lived documentation "
            "token; mint one with bin/dev-token.sh and export it into this process.",
        )

    # Asserted here as well as in `published_address`, because this is the
    # function that opens it: a `file:` URL reaching urlopen would read a local
    # path and normalize it into a candidate, and the caller that built the URL
    # is not always the caller that will be here next session.
    if urlsplit(url).scheme != "https":
        raise ContractError(2, f"refusing to fetch a non-https URL: {url!r}")

    request = urllib.request.Request(url, method="GET")  # noqa: S310 — scheme asserted above
    request.add_header("Accept", "application/openapi+json")
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
            if response.status != 200:
                raise ContractError(6, f"the service answered {response.status}, not 200")
            return response.read()
    except urllib.error.HTTPError as error:
        raise ContractError(
            6,
            f"the service answered {error.code} for the OpenAPI document. A 404 here is "
            "the unresolvable-pre-request-hook shape (D145): the service is up, --ready "
            "returns 0, and every request fails.",
        ) from error
    except urllib.error.URLError as error:
        raise ContractError(3, f"cannot reach the REST service: {error.reason}") from error


# ---------------------------------------------------------------------------
# The comparisons
# ---------------------------------------------------------------------------


def surface_objects(surface: dict[str, Any]) -> set[str]:
    """The reviewed contract's objects, spelled the way a served path spells them.

    `notes` and `rpc/create_note`, matching `openapi_normalize.declared_objects`.
    Both sides spell an object one way on purpose: a comparison whose sides
    disagree about spelling reports a difference that is not one, and the repair
    for that is always to loosen the comparison.
    """
    names = set(surface["relations"])
    names |= {f"rpc/{name}" for name in surface["rpcs"]}
    return names


def compare_snapshot_to_surface(snapshot: dict[str, Any], surface: dict[str, Any]) -> list[str]:
    """Object-level, per ADR 0060. Methods are the catalog's business."""
    problems: list[str] = []
    published = openapi_normalize.declared_objects(snapshot)
    reviewed = surface_objects(surface)

    for name in sorted(published - reviewed):
        problems.append(
            f"the snapshot publishes {name!r}, which the reviewed surface does not name. "
            "An object reaching the published document without a reviewed entry is the "
            "case the contract exists for"
        )
    for name in sorted(reviewed - published):
        problems.append(
            f"the reviewed surface names {name!r}, which the snapshot does not publish. "
            "Either the migration that creates it has not shipped, or its grants keep it "
            "out of the document"
        )

    exposed = surface["exposed_schema"]
    for forbidden in sorted(surface["forbidden_schemas"]):
        marker = f"{forbidden}."
        if any(marker in name for name in published):
            problems.append(f"the snapshot names the forbidden schema {forbidden!r}")
    if f"{exposed}." in json.dumps(snapshot.get("info", {})):
        problems.append("the snapshot's info block names the exposed schema")
    return problems


def load_snapshot() -> dict[str, Any]:
    """The committed snapshot, refused unless it is in canonical form.

    A hand-edited snapshot is the failure this catches. Re-serializing what was
    parsed and comparing it to the bytes on disk means a snapshot somebody
    reformatted, resorted or edited one line of no longer matches what the
    generator would have produced — which is exactly the state in which the
    committed file has stopped being the generated artifact ADR 0050 says it is.
    """
    if not SNAPSHOT_PATH.is_file():
        raise ContractError(
            5,
            f"there is no approved snapshot at {SNAPSHOT_PATH.relative_to(REPO_ROOT)}. "
            "It cannot be written by hand and it cannot be written by this command: it "
            "is captured from a deployed release with --update, reviewed, and committed "
            "by the source owner. Session 5 Run 9 is the run that does that.",
        )
    raw = SNAPSHOT_PATH.read_bytes()
    document = openapi_normalize.load_document(raw)
    if openapi_normalize.canonical_bytes(document) != raw:
        raise ContractError(
            5,
            f"{SNAPSHOT_PATH.name} is not in canonical form. It is a generated artifact; "
            "re-capture it with --update rather than editing it, because a hand-edited "
            "snapshot is a client contract nobody generated.",
        )
    if document.get("host") != openapi_normalize.SENTINEL_HOST:
        raise ContractError(
            5,
            f"{SNAPSHOT_PATH.name} carries host {document.get('host')!r} rather than the "
            f"sentinel {openapi_normalize.SENTINEL_HOST!r}. A snapshot holding a real "
            "project's address is one project's document committed as both projects'.",
        )
    return document


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def command_update(deployed_path: Path) -> int:
    deployed = load_deployed(deployed_path)
    host, base_path = published_address(deployed)

    rest_url = deployed["routes"]["rest"]["url"]
    raw = fetch_live(rest_url.rstrip("/") + "/")
    document = openapi_normalize.load_document(raw)
    candidate = openapi_normalize.normalize(
        document, expected_host=host, expected_base_path=base_path
    )

    # Stream, and only stream. The candidate goes to stdout so the redirect
    # happens in the caller's unprivileged shell; every diagnostic goes to
    # stderr so a redirected capture is the document and nothing else.
    sys.stdout.buffer.write(openapi_normalize.canonical_bytes(candidate))
    sys.stdout.buffer.flush()
    print(
        f"api-contract: captured {len(candidate.get('paths', {}))} paths from {host}. "
        "Review the diff and commit it as the source owner; this command wrote no file.",
        file=sys.stderr,
    )
    return 0


def command_check(deployed_path: Path | None) -> int:
    surface = api_surface.load_surface()
    snapshot = load_snapshot()

    problems = compare_snapshot_to_surface(snapshot, surface)
    if problems:
        print("api-contract: the snapshot and the reviewed surface disagree:", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        return 5

    if deployed_path is None:
        print(
            f"api-contract: the committed snapshot matches the reviewed surface "
            f"({len(openapi_normalize.declared_objects(snapshot))} objects). "
            "No deployed document was given, so the live document was not compared."
        )
        return 0

    deployed = load_deployed(deployed_path)
    host, base_path = published_address(deployed)
    live = openapi_normalize.normalize(
        openapi_normalize.load_document(
            fetch_live(deployed["routes"]["rest"]["url"].rstrip("/") + "/")
        ),
        expected_host=host,
        expected_base_path=base_path,
    )

    if openapi_normalize.canonical_bytes(live) != openapi_normalize.canonical_bytes(snapshot):
        served = openapi_normalize.declared_objects(live)
        approved = openapi_normalize.declared_objects(snapshot)
        print(
            "api-contract: the live document differs from the approved snapshot.",
            file=sys.stderr,
        )
        for name in sorted(served - approved):
            print(f"  - served but not approved: {name}", file=sys.stderr)
        for name in sorted(approved - served):
            print(f"  - approved but not served: {name}", file=sys.stderr)
        if served == approved:
            print(
                "  - the object sets agree, so the difference is in a definition, a "
                "parameter or the PostgREST version. Capture with --update and read "
                "the diff.",
                file=sys.stderr,
            )
        return 6

    recorded = (deployed.get("api") or {}).get("canonical_openapi_sha256")
    actual = openapi_normalize.fingerprint(snapshot)
    if recorded is not None and recorded != actual:
        print(
            f"api-contract: the deployed document records canonical_openapi_sha256 "
            f"{recorded[:16]}..., but the committed snapshot hashes to {actual[:16]}.... "
            "The deployment is serving a surface that was approved at a different commit.",
            file=sys.stderr,
        )
        return 6

    print(
        "api-contract: the live document, the committed snapshot and the reviewed "
        "surface all agree."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="api-contract",
        description="Capture or compare the reviewed API surface (ADR 0050).",
        allow_abbrev=False,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--update",
        action="store_true",
        help="capture a candidate from a deployed release and stream it to stdout",
    )
    mode.add_argument("--check", action="store_true", help="compare; never write")
    parser.add_argument(
        "--project-outputs",
        metavar="FILE",
        help="the project's deployed outputs document",
    )

    arguments = parser.parse_args(argv)

    try:
        if arguments.update:
            if not arguments.project_outputs:
                raise ContractError(2, "--update requires --project-outputs.")
            return command_update(Path(arguments.project_outputs))
        outputs = Path(arguments.project_outputs) if arguments.project_outputs else None
        return command_check(outputs)
    except ContractError as error:
        print(f"api-contract: {error}", file=sys.stderr)
        return error.code
    except (NormalizationError, ManifestError) as error:
        print(f"api-contract: {error}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

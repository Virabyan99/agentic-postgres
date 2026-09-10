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

from agentic_postgres import REPO_ROOT, api_surface, config, deployed_output, openapi_normalize
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
    status = rest.get("status")

    # Version 17's third word gets its own message, and the reason is the whole
    # of ADR 0199: `unobserved` means the deploy did not look, so the remedy is
    # to make it look. Folding it into the sentence below would send an operator
    # to check which session their project was deployed through, when the answer
    # is "redeploy".
    if status == deployed_output.ROUTE_UNOBSERVED["status"]:
        raise ContractError(
            2,
            "the deployed document records routes.rest as `unobserved`: that deploy did "
            "not observe the route, so there is no address to capture from and no claim "
            "that the route is down. Redeploy so the route is observed, then capture.",
        )

    if status != "ready" or not rest.get("url"):
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
        # The status and the URL, and no diagnosis. This said "a 404 here is the
        # unresolvable-pre-request-hook shape (D145)" until Run 9, when a live
        # 404 turned out to be the edge: the container carried none of the
        # identity labels Traefik's provider constraint filters on, so no router
        # existed, while PostgREST answered 200 with a complete document to any
        # peer on its own network (D186).
        #
        # A message naming a divergence number reads as a finding. This one was
        # confident, specific and wrong, and it would have sent a reader to the
        # pre-request hook. What a caller needs is what happened; what it costs
        # them to be told what it *means*, wrongly, is an hour.
        raise ContractError(
            6,
            f"the service answered {error.code} for the OpenAPI document at {url}. "
            "That is the status the edge returned; whether the request reached "
            "PostgREST at all is not visible from here. Compare against the "
            "service directly from a peer on its network before concluding "
            "anything about the service.",
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
        # Three clauses, not two (D1039). The first two are real causes, and an
        # outsider adding an application to this product hit neither: the
        # migration had shipped and the grants were correct. The snapshot simply
        # predated the surface. Trusting the message, they spent their time
        # auditing grants that were fine.
        #
        # The third clause is also the one that says this check can be
        # *unsatisfiable* rather than merely unsatisfied. `--update` reads
        # `routes.rest.url` from a DEPLOYED document; the surface is served only
        # once the migrations are applied; the migrations are applied by the
        # deploy. So on a first bring-up it cannot be made to agree until after
        # that deploy, while the natural reading of the process puts the gate
        # first. "I have made a mistake" and "this cannot be done yet" are
        # different states, and only this message can tell them apart.
        problems.append(
            f"the reviewed surface names {name!r}, which the snapshot does not publish. "
            "Either the migration that creates it has not shipped, or its grants keep it "
            "out of the document, or the snapshot predates this surface -- re-capture it "
            "with `--update --project-outputs FILE` after the deploy that serves it"
        )

    exposed = surface["exposed_schema"]
    for forbidden in sorted(surface["forbidden_schemas"]):
        marker = f"{forbidden}."
        if any(marker in name for name in published):
            problems.append(f"the snapshot names the forbidden schema {forbidden!r}")
    if f"{exposed}." in json.dumps(snapshot.get("info", {})):
        problems.append("the snapshot's info block names the exposed schema")
    return problems


def project_root(project_path: Path) -> Path:
    """The set directory a project manifest names, as an absolute path.

    Takes the MANIFEST rather than the directory, so that `--project` means the
    same thing here as it does to `bin/migrate.sh`: the file an operator already
    has in their hand. A second spelling of the same flag is how one of the two
    eventually gets pointed somewhere else.
    """
    document = config.load_project_manifest(project_path)
    named = config.project_migration_set(document)
    if named is None:
        raise ContractError(
            2,
            f"{project_path} declares no migrations.set, so it has no contract of its own. "
            "A project's reviewed surface lives beside its migration set (ADR 0198); "
            "without one this project publishes exactly the release's surface and "
            "`--check` without --project is the comparison you want.",
        )
    return REPO_ROOT / named


def load_project_snapshot(root: Path) -> dict[str, Any]:
    """A project's own approved snapshot, refused unless canonical.

    `load_snapshot`'s rules, applied to the other file: a snapshot somebody
    reformatted or edited one line of has stopped being the generated artifact
    ADR 0050 says it is. The message names the project's path rather than the
    release's, because the operator reading it did not write the release.
    """
    path = api_surface.project_snapshot_path(root)
    if not path.is_file():
        raise ContractError(
            5,
            f"there is no approved snapshot at {path.relative_to(REPO_ROOT)}. It cannot be "
            "written by hand and it cannot be written by this command: capture it with "
            "`--update --project FILE --project-outputs FILE` after the deploy that serves "
            "this project's set, review it, and commit it.",
        )
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != openapi_normalize.canonical_bytes(document):
        raise ContractError(
            5,
            f"{path.relative_to(REPO_ROOT)} is not in canonical form, so it is not what "
            "the generator produced. Re-capture it; do not edit it.",
        )
    if document.get("host") != openapi_normalize.SENTINEL_HOST:
        raise ContractError(
            5,
            f"{path.name} carries host {document.get('host')!r} rather than the sentinel "
            f"{openapi_normalize.SENTINEL_HOST!r}. A snapshot holding a real project's "
            "address is one deployment's document committed as every deployment's.",
        )
    return document


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


def command_update(deployed_path: Path, project_path: Path | None = None) -> int:
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

    # Where it belongs, on stderr, so a redirected capture is still the document
    # and nothing else. The path is PRINTED rather than written to, because
    # `--update` may run under sudo and the file has to end up owned by the
    # unprivileged source owner who reviews and commits it -- which is the whole
    # reason this command streams instead of writing.
    if project_path is not None:
        destination = api_surface.project_snapshot_path(project_root(project_path))
        print(
            f"api-contract: this candidate belongs at "
            f"{destination.relative_to(REPO_ROOT)} -- the project's own snapshot, "
            "captured from the project's own deployment.",
            file=sys.stderr,
        )

    print(
        f"api-contract: captured {len(candidate.get('paths', {}))} paths from {host}. "
        "Review the diff and commit it as the source owner; this command wrote no file.",
        file=sys.stderr,
    )
    return 0


def command_check(deployed_path: Path | None, project_path: Path | None = None) -> int:
    surface = api_surface.load_surface()

    # With --project, both halves move together: the MERGED surface against the
    # PROJECT's snapshot. Neither on its own is a comparison -- the merged
    # surface against the release's snapshot would report every project object
    # as unpublished, and the release's surface against the project's snapshot
    # would report every project object as unreviewed. That symmetry is why the
    # flag governs both rather than one.
    if project_path is not None:
        root = project_root(project_path)
        surface = api_surface.merged_surface(
            surface, api_surface.load_project_surface(api_surface.project_contract_path(root))
        )
        snapshot = load_project_snapshot(root)
        # The release's snapshot is still loaded, and not as a fallback: the
        # deployed document's `canonical_openapi_sha256` is a RELEASE-wide
        # digest that every project of a release records identically, so the
        # clause below has to keep hold of it after `snapshot` has become the
        # project's.
        release_snapshot = load_snapshot()
    else:
        snapshot = load_snapshot()
        release_snapshot = snapshot

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

    # **The RELEASE's snapshot, even under `--project`.** This clause asks
    # "was this deployment built against the release I am holding?", and
    # `bin/deploy-project.py` answers it by writing `canonical_openapi_sha256`
    # from `SNAPSHOT_PATH` unconditionally -- what a given project actually
    # serves goes in `project_openapi_sha256` beside it. Comparing the
    # release-wide digest against a project's own snapshot compared two
    # different things and fired for every project that HAS a set, which made
    # `--check --project --project-outputs` unable to exit 0 at all.
    #
    # It was invisible offline for the reason the fixture states in its own
    # docstring: a real project snapshot only comes from a deployment of that
    # project, so no offline test can hold one AND a deployed document, and
    # this line had never executed with `project_path` set.
    recorded = (deployed.get("api") or {}).get("canonical_openapi_sha256")
    actual = openapi_normalize.fingerprint(release_snapshot)
    if recorded is not None and recorded != actual:
        print(
            f"api-contract: the deployed document records canonical_openapi_sha256 "
            f"{recorded[:16]}..., but the committed RELEASE snapshot hashes to "
            f"{actual[:16]}.... The deployment was built against a different "
            "commit's approved surface.",
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
    parser.add_argument(
        "--project",
        metavar="FILE",
        help=(
            "the project manifest, when the project declares a migration set of its own: "
            "--check then compares the merged surface against that project's snapshot, and "
            "--update names the path its candidate belongs at (ADR 0198)"
        ),
    )

    arguments = parser.parse_args(argv)

    try:
        project = Path(arguments.project) if arguments.project else None
        if project is not None and not project.is_file():
            raise ContractError(2, f"project manifest not found: {project}")

        if arguments.update:
            if not arguments.project_outputs:
                raise ContractError(2, "--update requires --project-outputs.")
            return command_update(Path(arguments.project_outputs), project)
        outputs = Path(arguments.project_outputs) if arguments.project_outputs else None
        return command_check(outputs, project)
    except ContractError as error:
        print(f"api-contract: {error}", file=sys.stderr)
        return error.code
    except (NormalizationError, ManifestError) as error:
        print(f"api-contract: {error}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

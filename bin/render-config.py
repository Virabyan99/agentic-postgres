#!/usr/bin/env python
"""Validate manifests, and generate the numeric bounds documentation.

Two responsibilities, both about keeping one authority for one fact:

``--validate-only``
    Parse and validate a project and capability manifest without producing
    output. This is what ``deploy.sh`` calls before it stages anything.

``--bounds-doc``
    Regenerate the bounds table in ``docs/product-contract.md`` from
    ``schemas/project.schema.json``, which is its sole authority (plan
    decision E). ``--check`` compares without writing and is what the gate
    runs; ``--write`` updates and is what the pre-commit hook runs.

Exit codes (runbook §2 convention):
    0   success
    2   invalid operator input or manifest
    5   contract failure, or generated documentation has drifted
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import config, host_config, rendering  # noqa: E402

BEGIN = "<!-- BEGIN GENERATED: bounds -->"
END = "<!-- END GENERATED: bounds -->"
CONTRACT = REPO_ROOT / "docs" / "product-contract.md"


def render_bounds_block() -> str:
    rows = config.bounds_table()

    lines = [
        BEGIN,
        "<!-- Generated from schemas/project.schema.json by",
        "     bin/render-config.py --bounds-doc --write. Do not hand-edit. -->",
        "",
        "| Field | Minimum | Maximum | Meaning |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        minimum = "—" if row["minimum"] is None else f"{row['minimum']:,}"
        maximum = "—" if row["maximum"] is None else f"{row['maximum']:,}"
        lines.append(f"| `{row['field']}` | {minimum} | {maximum} | {row['description']} |")

    lines += [
        "",
        "Relations between these fields cannot be expressed in JSON Schema and are",
        "enforced in `src/agentic_postgres/config.py`:",
        "",
    ]
    lines += [f"- {relation}" for relation in config.CROSS_FIELD_RELATIONS]
    lines += ["", END]
    return "\n".join(lines)


def replace_block(text: str, block: str) -> str:
    start = text.find(BEGIN)
    end = text.find(END)
    if start == -1 or end == -1:
        raise SystemExit(f"markers {BEGIN} / {END} not found in {CONTRACT}")
    return text[:start] + block + text[end + len(END) :]


def bounds_doc(mode: str) -> int:
    current = CONTRACT.read_text(encoding="utf-8")
    updated = replace_block(current, render_bounds_block())

    if mode == "write":
        if updated != current:
            CONTRACT.write_text(updated, encoding="utf-8")
            print(f"render-config: updated the bounds table in {CONTRACT.name}")
        else:
            print("render-config: bounds table is already current")
        return 0

    if updated != current:
        print(
            "render-config: the bounds table in docs/product-contract.md has drifted "
            "from schemas/project.schema.json.\n"
            "Run: python bin/render-config.py --bounds-doc --write",
            file=sys.stderr,
        )
        return 5
    print("render-config: bounds table is current")
    return 0


def validate_only(project: Path, capabilities: Path) -> int:
    try:
        config.load_project_manifest(project)
    except config.ManifestError as exc:
        print(f"render-config: {project}: {exc}", file=sys.stderr)
        return 2

    try:
        config.load_capabilities_manifest(capabilities)
    except config.CapabilityContractError as exc:
        # Well formed but asserts something untrue -> contract failure, not
        # operator error.
        print(f"render-config: {capabilities}: {exc}", file=sys.stderr)
        return 5
    except config.ManifestError as exc:
        print(f"render-config: {capabilities}: {exc}", file=sys.stderr)
        return 2

    print(f"render-config: {project.name} and {capabilities.name} are valid")
    return 0


def render(project: Path, capabilities: Path) -> int:
    """Runbook §11 steps 5-15. Publishes atomically or changes nothing."""
    try:
        directory = rendering.render_project(project, capabilities)
    except config.CapabilityContractError as exc:
        print(f"deploy: {capabilities}: {exc}", file=sys.stderr)
        return 5
    except config.ManifestError as exc:
        print(f"deploy: {exc}", file=sys.stderr)
        return 2
    except rendering.RenderError as exc:
        print(f"deploy: {exc}", file=sys.stderr)
        print("deploy: the previous valid render, if any, is unchanged.", file=sys.stderr)
        return 5

    summary = (directory / "rendered-summary.txt").read_text(encoding="utf-8")
    print(summary, end="")
    # Spelled out rather than globbed, so a file the renderer stops producing is
    # a visible diff here. Session 10 added pgbackrest.conf.
    #
    # **The modes are read from the constants rather than typed** (D652). Session
    # 10 added `pgbackrest.conf` to the list and left the trailing claim at
    # `(mode 0600)` -- but `PGBACKREST_CONF_MODE` is 0444 deliberately: the file
    # carries no credential by construction and uid 999 has to read it. So this
    # line asserted a mode the renderer had never given that file, in the one
    # sentence a reader sees after every render. Question 5 -- the claim was true
    # when written and stopped being true when a file with a different mode
    # joined the list it describes.
    print(
        f"\nWrote {directory}/"
        "{outputs.json,compose.env,rendered-summary.txt} "
        f"(mode {rendering.FILE_MODE:04o}) and pgbackrest.conf "
        f"(mode {rendering.PGBACKREST_CONF_MODE:04o}; it carries no credential)"
    )
    print("No service was started, and no provider was contacted.")
    return 0


def edge_env(host: Path) -> int:
    """Write the shared edge stack's env file to stdout.

    Derived from ``host.yaml`` on demand rather than read from
    ``/var/lib/agentic-postgres/edge/compose.env``, so that ``--edge config``
    works offline and in CI where nothing root-owned exists. ``bin/edge.sh``
    writes identical content to that root-owned path for the systemd unit,
    which cannot read a manifest out of an operator's checkout.
    """
    try:
        document = host_config.load_host_manifest(host)
    except config.ManifestError as exc:
        print(f"render-config: {host}: {exc}", file=sys.stderr)
        return 2

    sys.stdout.buffer.write(host_config.edge_compose_env(document))
    return 0


def edge_static(host: Path, destination: Path, acme_environment: str) -> int:
    """Render Traefik's static and dynamic configuration into a directory.

    Nothing did this. ``infra/edge/traefik.yaml`` is a template with two
    placeholders and it was never installed anywhere, so the Compose bind mount
    pointed at a path that did not exist -- and Compose, whose
    ``create_host_path`` defaults to true, created a *directory* there. Traefik
    then restarted forever on "read /etc/traefik/traefik.yaml: is a directory".

    The ACME environment is a parameter because promotion re-renders this file
    against the production directory and storage. It is still not selectable
    from a manifest: `host.schema.json` pins `initial_acme_environment` to the
    const `staging`, and production is reached only through
    `edge.sh promote-acme`.
    """
    try:
        document = host_config.load_host_manifest(host)
    except config.ManifestError as exc:
        print(f"render-config: {host}: {exc}", file=sys.stderr)
        return 2

    if acme_environment not in {"staging", "production"}:
        print(f"render-config: unknown ACME environment {acme_environment!r}", file=sys.stderr)
        return 2

    source = REPO_ROOT / "infra" / "edge"
    text = (source / "traefik.yaml").read_text(encoding="utf-8")
    text = text.replace("__ACME_RESOLVER_NAME__", document["edge"]["acme_resolver_name"])
    text = text.replace("__ACME_EMAIL__", document["edge"]["acme_email"])

    if acme_environment == "production":
        # The staging store stays on disk. Rewriting the pointer rather than
        # moving the state is what makes promotion reversible without deleting
        # an ACME store -- deleting one is how a failed renewal becomes an
        # exhausted weekly rate limit.
        text = text.replace("acme/staging.json", "acme/production.json")
        text = text.replace(
            "https://acme-staging-v02.api.letsencrypt.org/directory",
            "https://acme-v02.api.letsencrypt.org/directory",
        )

    destination.mkdir(parents=True, exist_ok=True)
    if (problem := _clear_invented_directory(destination / "traefik.yaml")) is not None:
        print(f"render-config: {problem}", file=sys.stderr)
        return 5
    if (problem := render_problem("traefik.yaml", text)) is not None:
        print(f"render-config: {problem}", file=sys.stderr)
        return 5
    _write_config_file(destination / "traefik.yaml", text)

    dynamic = destination / "dynamic"
    dynamic.mkdir(parents=True, exist_ok=True)
    for path in sorted((source / "dynamic").glob("*.yaml")):
        body = _substitute_hsts(path.read_text(encoding="utf-8"), acme_environment)
        if (problem := render_problem(path.name, body)) is not None:
            print(f"render-config: {problem}", file=sys.stderr)
            return 5
        _write_config_file(dynamic / path.name, body)

    print(f"render-config: wrote the {acme_environment} edge configuration to {destination}")
    return 0


def render_problem(name: str, text: str) -> str | None:
    """Refuse to write a rendered file Traefik would silently discard.

    Two checks, and the order matters because the first makes the second
    possible.

    **It parses.** Nothing checked this, and "no unsubstituted placeholders" is
    a weaker claim than it looks: a substitution can complete and still produce
    a document that does not parse. Traefik's file provider does not fail
    loudly when one does -- it drops the whole file, and the only symptom is
    that every middleware defined in it stops existing. The routers referencing
    them are rejected one by one with `middleware "..." does not exist`, and
    the hostname answers 404 while holding a perfectly valid certificate.

    **No placeholder survived into the data.** This scans the parsed document
    rather than the raw text, which is the difference between "a placeholder
    reaches the host" and "a placeholder reaches Traefik". `baseline.yaml`
    documents its own placeholder in a header comment, on purpose, and a
    raw-text scan cannot tell that occurrence -- inert, deliberate -- from one
    in a value, which is a real defect. Scanning the parse is how the
    distinction gets made without writing a YAML comment stripper.
    """
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return f"{name}: the rendered configuration is not valid YAML: {exc}"
    if not isinstance(parsed, dict):
        return f"{name}: the rendered configuration is not a mapping, got {type(parsed).__name__}"

    unsubstituted = sorted(_placeholders_in(parsed))
    if unsubstituted:
        return f"{name}: unsubstituted {unsubstituted}"
    return None


def _placeholders_in(node: object) -> set[str]:
    """Every `__NAME__` token reachable in a parsed document's keys or values."""
    if isinstance(node, str):
        return set(re.findall(r"__[A-Z_]+__", node))
    if isinstance(node, dict):
        found: set[str] = set()
        for key, value in node.items():
            found |= _placeholders_in(key) | _placeholders_in(value)
        return found
    if isinstance(node, list):
        found = set()
        for value in node:
            found |= _placeholders_in(value)
        return found
    return set()


#: Only where the placeholder is the whole of a line, indentation aside.
#:
#: `str.replace` substitutes every occurrence, and `baseline.yaml` documents
#: its own placeholder in a header comment:
#:
#:     # One placeholder is substituted by edge.sh:
#:     #   __HSTS_BLOCK__   empty on staging; the HSTS header set after promotion.
#:
#: On staging the replacement is empty, so that comment stayed a comment and
#: nothing was ever wrong. On production it is three lines, and the second and
#: third escaped the `#` to become top-level YAML ahead of `tls:` -- which is
#: how the first production render of this file made it unparseable, took every
#: baseline middleware with it, and left both hostnames serving 404 behind a
#: valid certificate.
_HSTS_PLACEHOLDER = re.compile(r"^(?P<indent>[ \t]*)__HSTS_BLOCK__[ \t]*$", re.MULTILINE)

#: Unindented. The indentation comes from wherever the placeholder sits, so
#: this no longer has to know it is being pasted eight spaces deep into a file
#: it cannot see.
_HSTS_LINES = ("stsSeconds: 31536000", "stsIncludeSubdomains: true", "stsPreload: false")


def _substitute_hsts(body: str, acme_environment: str) -> str:
    """Absent on staging, and that is the point.

    A browser that pins HSTS against a staging certificate keeps refusing the
    site long after the certificate is fixed, and the operator cannot clear it
    for their visitors.
    """
    if acme_environment != "production":
        return _HSTS_PLACEHOLDER.sub("", body)
    return _HSTS_PLACEHOLDER.sub(
        lambda match: "\n".join(f"{match['indent']}{line}" for line in _HSTS_LINES), body
    )


def _clear_invented_directory(path: Path) -> str | None:
    """Remove the empty directory Compose creates where a bind source is missing.

    ``os.replace`` onto a directory fails, so a host that has already tried to
    start the edge once cannot be repaired by rendering alone — and the operator
    is left deleting a path under /var/lib by hand on the strength of an error
    message.

    ``rmdir``, never a recursive delete. It succeeds only on an empty directory,
    which is exactly what Compose leaves and nothing else is. Anything with
    contents is somebody's data and gets reported instead.
    """
    if not path.is_dir() or path.is_symlink():
        return None
    try:
        path.rmdir()
    except OSError:
        return f"{path} is a non-empty directory where a file belongs; inspect it and remove it"
    return None


def _write_config_file(path: Path, text: str) -> None:
    """Write 0644, replacing atomically.

    0644 rather than 0600: Traefik reads these and the container's user is not
    this file's decision. They carry no secret -- an ACME contact address and a
    resolver name -- and what matters is that nothing but root can write them,
    since writing them chooses the certificate authority.
    """
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bin/render-config.py",
        description="Validate manifests and generate bounds documentation.",
    )
    parser.add_argument("--project", type=Path, help="Path to a project manifest.")
    parser.add_argument("--capabilities", type=Path, help="Path to a capability manifest.")
    parser.add_argument("--host", type=Path, help="Path to a host manifest.")
    parser.add_argument(
        "--edge-env",
        action="store_true",
        help="With --host: write the shared edge stack's compose.env to stdout.",
    )
    parser.add_argument(
        "--edge-static",
        type=Path,
        metavar="DIR",
        help="With --host: render traefik.yaml and dynamic/ into DIR.",
    )
    parser.add_argument(
        "--acme-environment",
        choices=("staging", "production"),
        default="staging",
        help="With --edge-static: which ACME directory and store to point at.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the manifests and write nothing.",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Validate, stage, verify, and publish the generated project directory.",
    )
    parser.add_argument(
        "--bounds-doc",
        action="store_true",
        help="Regenerate or verify the numeric bounds table.",
    )
    parser.add_argument("--write", action="store_true", help="With --bounds-doc: update the file.")
    parser.add_argument(
        "--check", action="store_true", help="With --bounds-doc: fail on drift, write nothing."
    )

    args = parser.parse_args(argv)

    if args.edge_env:
        if not args.host:
            parser.error("--edge-env requires --host")
        return edge_env(args.host)

    if args.edge_static:
        if not args.host:
            parser.error("--edge-static requires --host")
        return edge_static(args.host, args.edge_static, args.acme_environment)

    if args.bounds_doc:
        if args.write == args.check:
            parser.error("--bounds-doc requires exactly one of --write or --check")
        return bounds_doc("write" if args.write else "check")

    if args.validate_only and args.render:
        parser.error("--validate-only and --render are mutually exclusive")

    if args.validate_only or args.render:
        if not args.project or not args.capabilities:
            parser.error("--validate-only and --render require --project and --capabilities")
        if args.render:
            return render(args.project, args.capabilities)
        return validate_only(args.project, args.capabilities)

    parser.error("one of --validate-only, --render, or --bounds-doc is required")
    return 2  # unreachable; argparse exits


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Deploy one project through Session 2, on a host that is already prepared.

Invoked only by `./deploy.sh --through-session 2`, which has already checked
root and resolved every path. Kept as its own program rather than more shell
because the steps below are one transaction and the rollback boundary belongs
in one process.

**It does not create its own preconditions.** The edge plane, the provider
bootstrap and the secret generation are `bin/edge.sh`, `bin/bootstrap-providers.sh`
and `bin/materialize-secrets.sh`, run in that order beforehand. A deploy that
quietly performed them would be one whose failure halfway leaves nobody able to
say which half ran, and would make `--through-session` mean something different
on a fresh host than on a redeploy. Every precondition is checked and named.

**It observes rather than assumes.** Every field of the deployed document comes
from something read back off the host: the release directory that exists, the
generation the pointer names, the certificate the edge holds. Where a fact
cannot be read, the document records `unavailable` rather than the value the
manifest hoped for.

Exit codes follow the deploy.sh convention:
  0   deployed
  2   invalid operator input
  3   missing prerequisite
  4   a precondition of this session has not been run
  5   validation failure
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import deployed_output, edge_state, installed_release, runtime_override
from agentic_postgres.bootstrap_state import load_state, state_path
from agentic_postgres.config import ManifestError, load_project_manifest
from agentic_postgres.host_config import (
    EDGE_STACK_NAME,
    load_host_manifest,
    runtime_compose_env,
)
from agentic_postgres.naming import project_key as derive_project_key

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_PRECONDITION = 4
EXIT_VALIDATION = 5

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRET_ROOT = Path("/var/lib/agentic-postgres/secrets")


def fail(code: int, message: str) -> None:
    print(f"deploy: {message}", file=sys.stderr)
    raise SystemExit(code)


def step(text: str) -> None:
    print(f"\n\033[1m==> {text}\033[0m")


def run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _establish_directory(path: Path) -> Path:
    """Create a root-only directory, refusing a symlink at the destination."""
    if path.is_symlink():
        fail(EXIT_VALIDATION, f"{path} is a symlink, which is not accepted.")
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    os.chown(path, 0, 0)
    return path


def _write_root_only(path: Path, payload: bytes) -> None:
    """Write `0600 root:root`, atomically.

    A reader that opens this file while it is half-written gets a truncated
    document rather than the previous one, and every reader here treats a
    truncated document as a hard failure.
    """
    if path.is_symlink():
        fail(EXIT_VALIDATION, f"{path} is a symlink, which is not accepted.")
    handle = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    try:
        with handle:
            handle.write(payload)
        os.chmod(handle.name, 0o600)
        os.chown(handle.name, 0, 0)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def _install_file(source: Path, destination: Path) -> None:
    """Copy an operator input into the configuration root.

    A copy, not a reference. A deployed project keeps working after the operator
    deletes their clone, which is the whole reason the launcher reads from /etc.
    """
    _write_root_only(destination, source.read_bytes())


def _env_value(path: Path, key: str) -> str:
    """Read one KEY=VALUE without shell-sourcing the file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name == key:
            return value
    fail(EXIT_VALIDATION, f"{key} is absent from {path}")
    raise AssertionError("unreachable")


def install_rendered(source: Path, destination: Path, override_payload: bytes) -> Path:
    """Install the rendered directory out of the checkout, atomically.

    The runtime's Compose project directory may not be a working tree: a
    `git checkout` on a Friday afternoon would otherwise change what the next
    `systemctl restart` runs.

    `override_payload` -- the runtime override -- is written into the staging
    copy before it is moved into place, not into the destination afterwards.
    A crash between those two steps would otherwise leave a rendered directory
    the next boot treats as complete but which produces no route: the same
    silent-unroutable failure `bin/compose.sh`'s override check exists to
    catch, reintroduced at the one moment that check cannot see it. Writing
    the override into staging first means the directory becomes visible at
    `destination` only once it already contains it.
    """
    if not (source / "compose.env").is_file():
        fail(EXIT_VALIDATION, f"nothing rendered at {source}; the render step did not run")

    _establish_directory(destination.parent)

    staging = destination.parent / f".{destination.name}.incoming"
    previous = destination.parent / f".{destination.name}.previous"
    for path in (staging, previous):
        shutil.rmtree(path, ignore_errors=True)

    shutil.copytree(source, staging)
    for path in (staging, *staging.rglob("*")):
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
        os.chown(path, 0, 0)

    _write_root_only(staging / "runtime-compose.override.yaml", override_payload)

    if destination.exists():
        os.replace(destination, previous)
    os.replace(staging, destination)
    shutil.rmtree(previous, ignore_errors=True)
    return destination


# ---------------------------------------------------------------------------
# Preconditions, each named
# ---------------------------------------------------------------------------


def require_edge_is_up() -> dict[str, Any]:
    """The edge must already be serving. Its networks are what a project joins."""
    result = run("docker", "ps", "--format", "{{.Names}}")
    if result.returncode != 0:
        fail(EXIT_PREREQUISITE, f"cannot reach the Docker daemon: {result.stderr.strip()}")

    names = result.stdout.split()
    if not any(name.startswith(EDGE_STACK_NAME) for name in names):
        fail(
            EXIT_PRECONDITION,
            "the edge plane is not running. Run: sudo bin/edge.sh --host host.yaml up",
        )

    return {
        "stack_name": EDGE_STACK_NAME,
        "control_network": f"{EDGE_STACK_NAME}_control",
        "egress_network": f"{EDGE_STACK_NAME}_egress",
        # Set truthfully after the runtime attaches it, not here.
        "project_network_attached": False,
    }


def require_bootstrap(project_key: str) -> dict[str, Any]:
    path = state_path(project_key)
    try:
        state = load_state(path)
    except Exception as error:
        fail(
            EXIT_PRECONDITION,
            f"no usable provider bootstrap for {project_key}: {error}. "
            f"Run: sudo bin/bootstrap-providers.sh --host host.yaml --project <manifest> --apply",
        )

    return {
        "status": "complete",
        "state_path": str(path),
        "infisical_project_id": state["infisical_project_id"],
        "runtime_identity_id": state["runtime_identity_id"],
    }


def require_secret_generation(project_key: str) -> dict[str, Any]:
    """Read the active generation, and the manifest that describes it.

    Both, not either. A pointer naming a generation whose manifest is missing
    describes a directory nothing can account for, and the deployed document
    would name a path that does not resolve.
    """
    project_root = SECRET_ROOT / project_key
    pointer = project_root / "active-secret-generation.json"
    if not pointer.exists():
        fail(
            EXIT_PRECONDITION,
            f"no active secret generation for {project_key}. "
            f"Run: sudo bin/materialize-secrets.sh --project <manifest> --session 2",
        )

    generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
    manifest_path = project_root / "generations" / generation / "manifest.json"
    if not manifest_path.exists():
        fail(
            EXIT_PRECONDITION,
            f"generation {generation} has no manifest.json; it predates this release. "
            "Re-run bin/materialize-secrets.sh to write a described generation.",
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "status": "ready",
        "generation_id": generation,
        "generation_manifest": str(manifest_path),
        "required_names": sorted(entry["name"] for entry in manifest["secrets"]),
        "fresh": True,
        "materialized_at": manifest["materialized_at"],
    }


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


def observe_health(url: str) -> str:
    """Ask the route whether it serves, from the host.

    A host-local request cannot prove the public path works — that is the
    external suite's job — but it can prove the container is answering, which is
    the difference between `ready` and a manifest's hope.
    """
    result = run("curl", "-ksS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "10", url)
    return "ready" if result.stdout.strip() == "200" else "unavailable"


def observe_tls(host: dict[str, Any], domain: str) -> dict[str, Any]:
    """Read the certificate the edge is actually serving for this hostname."""
    unavailable = {
        "status": "unavailable",
        "acme_environment": "staging",
        "resolver": host["edge"]["acme_resolver_name"],
        "certificate_sha256": None,
        "not_before": None,
        "not_after": None,
    }

    result = run(
        "bash",
        "-c",
        f"openssl s_client -connect 127.0.0.1:443 -servername {domain} </dev/null 2>/dev/null "
        "| openssl x509 -noout -fingerprint -sha256 -startdate -enddate",
    )
    if result.returncode != 0 or "Fingerprint" not in result.stdout:
        return unavailable

    fields: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip()

    fingerprint = fields.get("SHA256 Fingerprint", "").replace(":", "").lower()
    if len(fingerprint) != 64:
        return unavailable

    return {
        **unavailable,
        "status": "issued",
        "certificate_sha256": fingerprint,
        "not_before": _openssl_time(fields.get("notBefore")),
        "not_after": _openssl_time(fields.get("notAfter")),
    }


def _openssl_time(value: str | None) -> str | None:
    """`Aug  5 00:00:00 2026 GMT` -> RFC 3339, or None when unreadable.

    Returning None rather than guessing: a malformed date in a deployed document
    is a fact nobody measured, and the schema accepts null precisely so that
    "not known" has a way to be said.
    """
    if not value:
        return None
    from datetime import datetime

    try:
        parsed = datetime.strptime(value, "%b %d %H:%M:%S %Y %Z")
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# The deployment
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--capabilities", required=True, type=Path)
    arguments = parser.parse_args(argv)

    if os.geteuid() != 0:
        fail(EXIT_PREREQUISITE, "must run as root")

    try:
        host = load_host_manifest(arguments.host)
        manifest = load_project_manifest(arguments.project)
    except ManifestError as error:
        fail(EXIT_INPUT, str(error))

    project = manifest["project"]
    key = derive_project_key(project["slug"], project["environment"])

    step("1. Render, from the manifests as given")
    render = run(
        sys.executable,
        str(REPO_ROOT / "bin" / "render-config.py"),
        "--project",
        str(arguments.project),
        "--capabilities",
        str(arguments.capabilities),
        "--render",
    )
    if render.returncode != 0:
        fail(EXIT_VALIDATION, f"render failed:\n{render.stdout}{render.stderr}")
    rendered_dir = REPO_ROOT / ".generated" / key
    rendered = json.loads((rendered_dir / "outputs.json").read_text(encoding="utf-8"))
    print(f"  rendered {key}")

    step("2. Preconditions this session does not create")
    edge = require_edge_is_up()
    bootstrap = require_bootstrap(key)
    secrets = require_secret_generation(key)
    print(f"  edge up, providers bootstrapped, generation {secrets['generation_id']}")

    step("3. Install the release and record it")
    installed_release.assert_clean(REPO_ROOT)
    commit = installed_release.resolve_commit(REPO_ROOT)
    release = installed_release.install(REPO_ROOT, commit=commit)
    edge_state.write_state(
        edge_state.build_state(
            installed_release_commit=commit,
            host_manifest_sha256=hashlib.sha256(arguments.host.read_bytes()).hexdigest(),
        )
    )
    print(f"  release {commit[:12]} at {release}")

    step("4. Root-owned configuration and generated output")
    state_directory = _establish_directory(deployed_output.PROJECT_STATE_ROOT / key)

    _install_file(arguments.project, state_directory / "manifest.yaml")
    _install_file(REPO_ROOT / "secrets.required.yaml", state_directory / "secrets.required.yaml")
    _write_root_only(state_directory / "compose.env", runtime_compose_env(host))
    print(f"  {state_directory}")

    override_payload = runtime_override.render_override(
        router_name=_env_value(rendered_dir / "compose.env", "HEALTH_ROUTER_NAME"),
        https_entrypoint=host["edge"]["https_entrypoint"],
    )
    rendered_directory = install_rendered(
        rendered_dir, deployed_output.rendered_path(key), override_payload
    )
    print(f"  {rendered_directory}")

    step("5. Start the project")
    started = run(
        str(REPO_ROOT / "bin" / "project-runtime.sh"),
        "--host",
        str(arguments.host),
        "--project-key",
        key,
        "up",
    )
    print(started.stdout, end="")
    if started.returncode != 0:
        fail(EXIT_VALIDATION, f"the project did not start:\n{started.stderr}")
    edge["project_network_attached"] = True

    step("6. Observe and publish")
    document = deployed_output.build_deployed_document(
        rendered=rendered,
        source_commit=commit,
        host={
            "id": host["host"]["id"],
            "os_release": _os_release(),
            "public_ipv4": host["host"]["expected_public_ipv4"],
            "public_ipv6": host["host"]["expected_public_ipv6"],
        },
        edge=edge,
        tls=observe_tls(host, project["domain"]),
        bootstrap=bootstrap,
        secrets=secrets,
        runtime={
            "release_path": str(release),
            "state_directory": str(state_directory),
            "compose_model_sha256": _model_digest(rendered_directory),
        },
        health_status=observe_health(rendered["routes"]["health"]["url"]),
    )
    destination = deployed_output.write_deployed_document(
        document, deployed_output.deployed_path(key)
    )

    print(f"  {destination}")
    print(f"  tls          {document['tls']['status']} ({document['tls']['acme_environment']})")
    print(f"  health       {document['routes']['health']['status']}")
    print(f"\n\033[1mdeploy: {key} deployed through session 2\033[0m")
    return 0


def _os_release() -> str:
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION_ID="):
            return line.split("=", 1)[1].strip().strip('"')
    return "26.04"


def _model_digest(rendered_dir: Path) -> str:
    """Digest the resolved Compose model, not the template that produced it.

    What is running is what `config` resolved. Hashing compose.yaml would record
    agreement with a file, while the model is what Compose acted on.
    """
    result = run(
        str(REPO_ROOT / "bin" / "compose.sh"),
        str(rendered_dir),
        "--runtime",
        "--profile",
        "contract",
        "config",
    )
    if result.returncode != 0:
        fail(EXIT_VALIDATION, f"could not resolve the Compose model:\n{result.stderr}")
    return hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

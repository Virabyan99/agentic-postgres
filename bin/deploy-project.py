#!/usr/bin/env python3
"""Deploy one project through session N, on a host that is already prepared.

Invoked only by `./deploy.sh --through-session N`, which has already checked
root, validated N against what this release implements, and resolved every
path. Kept as its own program rather than more shell because the steps below
are one transaction and the rollback boundary belongs in one process.

**The session is a parameter, not this file's name.** It was `deploy-session-2.py`
until Session 3, and the name was the least of it: the session it deployed
appeared as a literal `2` in the profile set, in the secret filter and in the
closing message, in three files, none of which had any way to disagree loudly
(D59, ADR 0032). What N selects now is stated once, passed down, and recorded in
the deployed document so that a reboot restores the same deployment.

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

from agentic_postgres import (
    CURRENT_SESSION,
    database_observation,
    deployed_output,
    edge_state,
    installed_release,
    observation,
    rendering,
    runtime_override,
)
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


def _restore_checkout_ownership(path: Path) -> None:
    """Give the operator back the files this render wrote into their checkout.

    The render runs under sudo, so everything it writes into `.generated/` is
    owned by root. The operator's own `bin/session-01-check.sh` then cannot read
    its own rendered output, and six contract tests fail with `PermissionError`
    on a host where nothing is actually wrong.

    The authoritative copy is the root-owned one installed under
    `/var/lib/agentic-postgres/rendered/`; this tree is a by-product of running
    the renderer here, so handing it back costs nothing. Best-effort on purpose:
    a deploy must not fail because it could not tidy up a scratch directory.

    **The lock file counts.** `rendering.project_lock` opens
    `.generated/.locks/<key>.lock` at mode 0600, and under sudo that file is
    root's. It sits outside the rendered directory, so restoring only that
    directory left the lock behind — and the *next* unprivileged render of that
    project died with `PermissionError` on the lock, before it had validated
    anything. Latent since Session 2: alpha-dev had been deployed under sudo and
    nobody re-rendered it as the operator until Run 7 (D65).
    """
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if not (uid and gid):
        return

    targets = [path, *path.rglob("*")]
    locks = rendering.LOCK_ROOT
    if locks.is_dir():
        targets += [locks, *locks.glob("*.lock")]

    for target in targets:
        try:
            os.chown(target, int(uid), int(gid))
        except OSError:
            # Per target, not per run. One unreachable path must not stop the
            # rest from being handed back -- which is what a single try around
            # the whole loop did.
            continue


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


def _is_migration_artifact(path: Path, staging: Path) -> bool:
    """The rendered migration directory, or a file directly inside it.

    Deliberately not `"migrations" in path.parts`: that would widen the mode of
    anything a future render happened to put under a directory of that name at
    any depth, which is how an exemption written for one file becomes a
    property of the tree.
    """
    migrations_dir = staging / "migrations"
    return path == migrations_dir or path.parent == migrations_dir


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
        os.chown(path, 0, 0)
        if _is_migration_artifact(path, staging):
            # The one exception, and it is narrow: dbmate reads these from
            # inside a container as uid 65532, and a 0600 file it cannot open
            # fails as "permission denied" from a service whose whole job is to
            # be the only thing that touches the schema. The parent directory
            # stays 0700 root, so nothing here becomes readable to a host user
            # who could not already traverse into it, and the SQL carries no
            # secret -- it is derived identifiers over reviewed templates.
            os.chmod(path, 0o755 if path.is_dir() else 0o644)
        else:
            os.chmod(path, 0o700 if path.is_dir() else 0o600)

    _write_root_only(staging / "runtime-compose.override.yaml", override_payload)

    if destination.exists():
        os.replace(destination, previous)
    os.replace(staging, destination)
    shutil.rmtree(previous, ignore_errors=True)
    return destination


# ---------------------------------------------------------------------------
# Preconditions, each named
# ---------------------------------------------------------------------------


def require_edge_is_up(host: dict[str, Any]) -> dict[str, Any]:
    """The edge must already be serving. Its networks are what a project joins.

    The network names are *read* from the host manifest, not rebuilt from the
    stack name. `infra/edge/compose.yaml` sets each network's `name:` explicitly
    from that manifest, so Compose's default `<project>_<network>` convention
    does not apply: the real networks are `apg-edge-control` and
    `apg-edge-egress`, while the convention produces `apg-edge_control`.

    Every deployed document recorded the invented pair. Nothing consumed them
    until a test tried to attach a container to one, and `docker run` answered
    `network apg-edge_control not found`. Deriving a name a second time is the
    failure `build_deployed_document` is written to avoid.
    """
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
        "control_network": host["edge"]["control_network"],
        "egress_network": host["edge"]["egress_network"],
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


def observe_database(database: dict[str, Any]) -> dict[str, Any]:
    """Read the cluster this deploy just started, or fail saying it could not.

    There is no third outcome. A partial read is not published as `observed`
    with a null member, and it is not downgraded to `not_observed` either --
    that would record "nobody looked" about a deploy that looked and failed,
    which is the same lie in the other direction.
    """
    container = database["container"]

    def psql(sql: str) -> str:
        result = run(
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            database["name"],
            "-X",
            "-qtA",
            "-c",
            sql,
        )
        if result.returncode != 0:
            fail(EXIT_VALIDATION, f"the cluster refused a query:\n{result.stderr}")
        return result.stdout

    # From inside the container, so the cgroup path is the container's own. The
    # host path varies by cgroup driver and by systemd slice, and reading the
    # wrong one reports the whole machine's memory as the cluster's.
    memory = run("docker", "exec", "-i", container, "cat", "/sys/fs/cgroup/memory.stat")
    if memory.returncode != 0:
        fail(EXIT_VALIDATION, f"could not read the cluster's cgroup memory:\n{memory.stderr}")

    try:
        return database_observation.build_observation(
            server_version=psql("SHOW server_version;"),
            extensions=psql("SELECT extname || ' ' || extversion FROM pg_extension ORDER BY 1;"),
            memory_stat=memory.stdout,
        )
    except ValueError as error:
        fail(EXIT_VALIDATION, f"the cluster's state could not be read: {error}")
        raise  # unreachable; fail() exits


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
        # Read from the ACME store, not asserted. This was the literal
        # `"staging"`, which no promotion could change and nothing ever
        # measured -- so a deploy after `promote-acme` published a staging
        # environment beside the fingerprint of a production certificate.
        "acme_environment": edge_state.acme_environment(),
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

    # Keys are lower-cased on the way in. OpenSSL 3 prints `sha256 Fingerprint=`,
    # not `SHA256 Fingerprint=`, and looking up the capitalised form matched
    # nothing: every deployment recorded `tls: unavailable` while serving a
    # certificate. The guard above passed, because the *word* Fingerprint is
    # there -- only the lookup was wrong, so nothing pointed at the mistake.
    fields: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        fields[key.strip().lower()] = value.strip()

    fingerprint = fields.get("sha256 fingerprint", "").replace(":", "").lower()
    if len(fingerprint) != 64:
        return unavailable

    return {
        **unavailable,
        "status": "issued",
        "certificate_sha256": fingerprint,
        "not_before": _openssl_time(fields.get("notbefore")),
        "not_after": _openssl_time(fields.get("notafter")),
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
    parser.add_argument("--through-session", required=True, type=int)
    arguments = parser.parse_args(argv)

    # deploy.sh has already refused anything above what this release implements.
    # Checked again here rather than trusted, because this program is also what
    # a future caller would reach for, and a session it cannot deploy must not
    # be discovered halfway through by a step that silently does nothing.
    if arguments.through_session < 2 or arguments.through_session > CURRENT_SESSION:
        fail(
            EXIT_INPUT,
            f"--through-session {arguments.through_session} is outside what this release "
            f"deploys (2..{CURRENT_SESSION})",
        )

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
    _restore_checkout_ownership(rendered_dir)
    print(f"  rendered {key}")

    step("2. Preconditions this session does not create")
    edge = require_edge_is_up(host)
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

    # The indirection travels with the code it resolves. Until Run 8 only
    # provisioning installed these, so a host kept executing whatever launcher
    # it was built with: the copy running here was two sessions old and passed
    # `--session 2` to a Session 3 project, wrote a secret generation holding
    # Session 2's secret set, repointed the project at it, and only then failed
    # (D72, ADR 0037).
    refreshed = installed_release.reconcile_launchers(release)
    if refreshed:
        print(f"  launchers refreshed from this release: {', '.join(refreshed)}")

    step("4. Root-owned configuration and generated output")
    state_directory = _establish_directory(deployed_output.PROJECT_STATE_ROOT / key)

    _install_file(arguments.project, state_directory / "manifest.yaml")
    _install_file(REPO_ROOT / "secrets.required.yaml", state_directory / "secrets.required.yaml")
    _write_root_only(state_directory / "compose.env", runtime_compose_env(host))
    print(f"  {state_directory}")

    override_payload = runtime_override.render_override(
        router_name=_env_value(rendered_dir / "compose.env", "HEALTH_ROUTER_NAME"),
        https_entrypoint=host["edge"]["https_entrypoint"],
        # The installed path, not the checkout's. The override is written into
        # the staging copy of the very directory it names, and the name has to
        # be the one Compose will resolve at runtime.
        rendered_directory=str(deployed_output.rendered_path(key)),
    )
    rendered_directory = install_rendered(
        rendered_dir, deployed_output.rendered_path(key), override_payload
    )
    print(f"  {rendered_directory}")

    step("5. Start the project")
    # From the release, not the checkout. Compose records its project directory
    # on every container it starts, and starting from `REPO_ROOT` stamped
    # `/home/<operator>/agentic-postgres` onto them -- the working tree that a
    # `git checkout` can change under a running deployment. That is the same
    # rule the systemd launchers enforce, and the deploy was the one path
    # ignoring it.
    started = run(
        str(release / "bin" / "project-runtime.sh"),
        "--host",
        str(arguments.host),
        "--project-key",
        key,
        "--through-session",
        str(arguments.through_session),
        "up",
    )
    print(started.stdout, end="")
    if started.returncode != 0:
        fail(EXIT_VALIDATION, f"the project did not start:\n{started.stderr}")
    edge["project_network_attached"] = True

    # Re-read, because starting the project changed it. `project-runtime.sh up`
    # runs `materialize-secrets.sh`, which writes a *new* immutable generation
    # and repoints `active-secret-generation.json` at it. The value captured in
    # step 2 was the generation that was active before this deploy, so the
    # document described one the deploy had already superseded, and the pointer
    # and the document disagreed on every run after the first.
    #
    # Step 2 still checks the precondition; this observes the result. A deployed
    # document records what is true when it is written, not what was true when
    # the run began.
    secrets = require_secret_generation(key)

    # The two cluster planes, in the only order they work in: roles, the
    # identity sentinel and pgvector exist before a migration can reference
    # them, and `migration_user` cannot authenticate until bootstrap has given
    # it a credential. Both are idempotent and both are run on every deploy --
    # a redeploy that skipped them would leave a converged release running
    # against an unconverged database and report success (D46, ADR 0033).
    #
    # They are steps of the deploy rather than commands an operator remembers,
    # because neither has a meaning outside one: `migrate up` against a cluster
    # this release did not just start is a different, riskier operation. The
    # preconditions this deploy refuses to create are the ones that can fail on
    # their own -- the edge, the providers, the secrets.
    database_observed = deployed_output.NOT_OBSERVED
    if arguments.through_session >= 3:
        step("6. Bootstrap and migrate the cluster")
        manifest_copy = state_directory / "manifest.yaml"

        bootstrapped = run(
            str(release / "bin" / "postgres-bootstrap.sh"),
            "--project",
            str(manifest_copy),
            "--runtime",
            "--apply",
        )
        print(bootstrapped.stdout, end="")
        if bootstrapped.returncode != 0:
            # Exit code carried, not flattened. 11 is "this volume belongs to a
            # different project", and an operator who sees a generic validation
            # failure will look for a broken deploy instead of a wrong volume.
            fail(
                bootstrapped.returncode if bootstrapped.returncode == 11 else EXIT_VALIDATION,
                f"the cluster bootstrap did not converge:\n{bootstrapped.stderr}",
            )

        migrated = run(
            str(release / "bin" / "migrate.sh"),
            "--project",
            str(manifest_copy),
            "--runtime",
            "up",
        )
        print(migrated.stdout, end="")
        if migrated.returncode != 0:
            fail(EXIT_VALIDATION, f"migrations did not apply:\n{migrated.stderr}")

        database_observed = observe_database(rendered["database"])

    step("7. Observe and publish")
    # Traefik's Docker provider polls, so the router for a container that has
    # only just started is not wired at the instant `compose up --wait` returns.
    # Observing once here recorded `unavailable` for a route that answered 200
    # from two networks seconds later. The wait is bounded and still reports
    # whatever it finds at the deadline.
    print("  waiting for the route and its certificate to settle")
    tls = observation.await_observation(
        lambda: observe_tls(host, project["domain"]),
        lambda observed: observed["status"] == "issued",
    )
    health_status = observation.await_observation(
        lambda: observe_health(rendered["routes"]["health"]["url"]),
        lambda observed: observed == "ready",
    )

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
        tls=tls,
        bootstrap=bootstrap,
        secrets=secrets,
        runtime={
            "release_path": str(release),
            "state_directory": str(state_directory),
            "compose_model_sha256": _model_digest(release, rendered_directory),
        },
        health_status=health_status,
        # Measured above when this deploy started a cluster, and `NOT_OBSERVED`
        # when it did not. A session-2 deployment interrogates nothing, and the
        # honest record of that is four nulls rather than an empty object a
        # reader could mistake for an empty database.
        database_observed=database_observed,
        deployed_through_session=arguments.through_session,
    )
    destination = deployed_output.write_deployed_document(
        document, deployed_output.deployed_path(key)
    )

    print(f"  {destination}")
    print(f"  tls          {document['tls']['status']} ({document['tls']['acme_environment']})")
    print(f"  health       {document['routes']['health']['status']}")
    print(f"  database     {document['database']['observed']['status']}")
    print(f"\n\033[1mdeploy: {key} deployed through session {arguments.through_session}\033[0m")
    return 0


def _os_release() -> str:
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION_ID="):
            return line.split("=", 1)[1].strip().strip('"')
    return "26.04"


def _model_digest(release: Path, rendered_dir: Path) -> str:
    """Digest the resolved Compose model, not the template that produced it.

    What is running is what `config` resolved. Hashing compose.yaml would record
    agreement with a file, while the model is what Compose acted on.

    Resolved through the release's wrapper, for the same reason the project is
    started through it: the digest must describe the model the runtime uses, and
    the checkout's `compose.yaml` is not guaranteed to be that model.
    """
    result = run(
        str(release / "bin" / "compose.sh"),
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

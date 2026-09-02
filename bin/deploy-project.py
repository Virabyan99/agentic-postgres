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
    api_surface,
    backup_report,
    config,
    database_observation,
    deployed_output,
    edge_credentials,
    edge_state,
    installed_release,
    jwt_keys,
    observation,
    openapi_normalize,
    port_allocations,
    preflight,
    rendering,
    runtime_override,
    secrets_contract,
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

#: The session that introduces the REST plane, and with it the first service
#: that verifies a token. Below it there is no signing key materialized and
#: nothing to derive a JWKS from, so the deploy says so rather than deriving
#: from an absence.
REST_PLANE_SESSION = 5

#: The session that starts the auth service, and with it the application API
#: route and its documentation surface. Below it there is no `auth` container to
#: route to, so the deploy records `unavailable` rather than polling a route
#: nothing serves -- the same shape `REST_PLANE_SESSION` has carried since
#: Session 5.
APP_PLANE_SESSION = 6

#: The session that starts the object-storage runtime, and with it the storage
#: route. Below it the `storage` container is not selected -- its Compose entry
#: carries `profiles: [session7]` and `project-runtime.sh` passes
#: `--profile session<n>` only up to `--through-session` -- so there is nothing
#: to route to and `routes.storage` records `unavailable` without polling.
#:
#: The same shape the two constants above carry, and the same reason: a status
#: derived from an absence is a measurement, and a status polled against a
#: container that was never selected is a timeout.
STORAGE_PLANE_SESSION = 7

#: The session that starts the MCP runtime, and with it the agent-plane route.
#: The same shape the three constants above carry.
#:
#: **It is above `CURRENT_SESSION`, and that is deliberate in Run 1.** Nothing
#: selects an `mcp` container yet -- Session 8's Run 7 adds the Compose entry and
#: its `session8` profile -- so `--through-session` cannot legally reach this
#: number and the branch below cannot run. What Run 1 fixes is the *document*:
#: `routes.mcp` has been in every rendered document since version 1 and in no
#: deployed one (D395), and closing that gap needs no container. It needs the
#: deployed branch to carry the field, and the honest status for a deployment
#: that publishes nothing is `unavailable`.
#:
#: There is deliberately no `observe_mcp` beside `observe_storage` yet. A polling
#: loop against a container no profile selects is not a measurement; it is a
#: timeout with a status attached.
AGENT_PLANE_SESSION = 8

#: The session that gives a project a backup repository.
#:
#: Above `CURRENT_SESSION` in Run 3, exactly as `AGENT_PLANE_SESSION` was in
#: Session 8's Run 1, and for the same reason: nothing archives yet. What Run 3
#: fixes is the *document* and the *credential gate*, neither of which needs a
#: pgBackRest binary. The repository is reached for the first time in Run 6.
BACKUP_PLANE_SESSION = 10

#: The session that starts the metrics collector. The `metrics` service
#: carries `profiles: [session14]`, so a deployment through 13 renders the
#: route, names it in the document, and starts nothing behind it.
METRICS_PLANE_SESSION = 14

#: The reviewed OpenAPI snapshot, mirroring `bin/api-contract.py`'s own
#: constant. `test_the_deploy_and_the_contract_command_name_one_snapshot`
#: asserts the two agree -- a deploy recording the digest of one file while
#: the check command compares another is a disagreement nothing else sees.
SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent / "contracts" / "postgrest-openapi.canonical.json"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRET_ROOT = Path("/var/lib/agentic-postgres/secrets")

#: Traefik's file provider, host side. `bin/edge.sh` creates and mounts it
#: read-only; a project writes exactly two files here and owns neither the
#: directory nor the edge.
EDGE_DYNAMIC_DIR = Path("/var/lib/agentic-postgres/edge/dynamic")


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


def _restore_git_index_ownership() -> None:
    """Give the operator back `.git/index` after a privileged `git` refreshed it.

    Step 3 runs `installed_release.assert_clean`, which shells out to `git`. Git
    rewrites `.git/index` whenever a stat check makes the cached one stale --
    and under sudo the replacement lands `-rw------- root:root`. The operator's
    very next `git fetch` then dies with

        fatal: .git/index: index file open failed: Permission denied

    which reads as a broken repository rather than as a permission this deploy
    took. It is not hypothetical: a `sudo` pytest run touched enough mtimes to
    force the rewrite, and the next transport failed (D194).

    Separate from `_restore_checkout_ownership` because it runs *after* step 3
    rather than after step 1, and because the git directory is not a by-product
    of rendering -- it is the operator's own checkout, which nothing here owns.
    Best-effort for the same reason: a deploy that succeeded must not fail
    because it could not hand a file back.
    """
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if not (uid and gid):
        return

    git_dir = REPO_ROOT / ".git"
    if not git_dir.is_dir():
        return

    # The index is the one git rewrites on a read-only command. The others are
    # named because a `git status` may also touch them, and a root-owned one
    # breaks the same transport in the same way.
    for name in ("index", "index.lock", "FETCH_HEAD", "ORIG_HEAD"):
        target = git_dir / name
        if not target.exists():
            continue
        try:
            os.chown(target, int(uid), int(gid))
        except OSError:
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


#: Every router and middleware name the override renders into a label key, as
#: `render_override`'s keyword -> the `compose.env` key it comes from.
#:
#: One table, because there are two call sites: the privileged render and the
#: deploy, both building the same document from the same file. They were two
#: literal argument lists until Run 10 needed five more names, and D250 is what
#: two copies of an argument list does -- a keyword-only parameter added to a
#: producer, one caller updated and the other not, discovered on the host.
#: Adding a name is now an entry here and nothing else.
OVERRIDE_NAME_KEYS: dict[str, str] = {
    "router_name": "HEALTH_ROUTER_NAME",
    "rest_router_name": "REST_ROUTER_NAME",
    "buffering_middleware_name": "API_BUFFERING_MIDDLEWARE_NAME",
    "stripprefix_middleware_name": "API_STRIPPREFIX_MIDDLEWARE_NAME",
    "docs_router_name": "DOCS_ROUTER_NAME",
    "docs_auth_middleware_name": "DOCS_CREDENTIAL_MIDDLEWARE_NAME",
    "docs_stripprefix_middleware_name": "DOCS_STRIPPREFIX_MIDDLEWARE_NAME",
    "app_router_name": "APP_ROUTER_NAME",
    "app_buffering_middleware_name": "APP_BUFFERING_MIDDLEWARE_NAME",
    "app_stripprefix_middleware_name": "APP_STRIPPREFIX_MIDDLEWARE_NAME",
    "app_docs_router_name": "APP_DOCS_ROUTER_NAME",
    "storage_router_name": "STORAGE_ROUTER_NAME",
    "storage_buffering_middleware_name": "STORAGE_BUFFERING_MIDDLEWARE_NAME",
    "storage_stripprefix_middleware_name": "STORAGE_STRIPPREFIX_MIDDLEWARE_NAME",
    "storage_cors_middleware_name": "STORAGE_CORS_MIDDLEWARE_NAME",
    "mcp_router_name": "MCP_ROUTER_NAME",
    "metrics_router_name": "METRICS_ROUTER_NAME",
    "metrics_auth_middleware_name": "METRICS_CREDENTIAL_MIDDLEWARE_NAME",
}


def _override_names(compose_env: Path) -> dict[str, str]:
    """The name arguments `render_override` takes, read from one compose.env.

    `_env_value` fails the deploy on a missing key rather than defaulting, so a
    name this repository derives and forgets to emit is a refusal at step 4
    rather than a router that quietly is not there.
    """
    return {keyword: _env_value(compose_env, key) for keyword, key in OVERRIDE_NAME_KEYS.items()}


def require_mounts_exist(override_payload: bytes, services: Any, when: str) -> None:
    """Refuse to start a service whose bind-mount source is not there (ADR 0133).

    **Docker does not fail on a missing bind-mount source. It creates a
    DIRECTORY.** The service then opens a directory where a file should be, and
    the symptom arrives as a runtime error inside a container -- `IsADirectoryError`
    on a key set, in the case that produced this function -- rather than as
    anything the deploy said.

    Worse, the directory persists: `render-jwks.py` finishes with
    `staging.replace(destination)`, which raises on a directory, so every
    subsequent deploy fails at a step unrelated to the cause. That is how one
    missing file turned into four failed deploys (D463).

    Checked per phase, because the phases are the point: the deferred services'
    artefacts legitimately do not exist at step 5, and refusing on them would
    refuse a correct deploy.
    """
    sources = runtime_override.mount_sources(override_payload, services)

    missing = [source for source in sources if not Path(source).exists()]
    directories = [
        source
        for source in sources
        if Path(source).is_dir() and Path(source).suffix in {".json", ".yaml", ".yml"}
    ]

    if missing or directories:
        detail = ""
        if missing:
            detail += "\n  missing:     " + "\n               ".join(missing)
        if directories:
            detail += "\n  a directory: " + "\n               ".join(directories)
        fail(
            EXIT_VALIDATION,
            f"{when} would start a service whose bind-mount source is not a file:{detail}\n\n"
            "  Docker creates a missing bind-mount source as a DIRECTORY, so the service\n"
            "  would open a directory where a file should be and exit. A source that is\n"
            "  already a directory is the residue of that happening before: remove it with\n"
            "  `rmdir` -- which refuses a non-empty directory and is therefore the safe\n"
            "  verb -- and re-run this deploy (ADR 0133, D463).",
        )


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

    # **The render decides the mode; this decides the owner** (D589).
    #
    # This used to re-impose 0600 on everything except the migration set, which
    # made it a SECOND authority over a decision `rendering.py` had already
    # taken three times -- `FILE_MODE`, `MIGRATION_FILE_MODE`, `SNAPSHOT_MODE`
    # -- and this one won. So the archiver's config was rendered 0444 for a
    # container running as 999 and installed 0600, and pgBackRest refused it
    # with `[041]: unable to open file ... Permission denied` at step 6c and at
    # every archive_command after it (D588, whose repair was incomplete until
    # this one).
    #
    # `shutil.copytree` uses `copy2`, which preserves modes, so the modes are
    # already right when they arrive. What remains is ownership: the destination
    # is root-owned runtime state, and the source is a checkout owned by whoever
    # rendered it.
    #
    # The enclosing directory is 0700 root either way, so a widened file here is
    # readable only by something the daemon bind-mounts it into -- which is the
    # argument `MIGRATION_FILE_MODE` already makes for the SQL, now applied to
    # every artefact rather than re-argued per file.
    shutil.copytree(source, staging)
    for path in (staging, *staging.rglob("*")):
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


def observe_prerequisites(
    project_key: str,
    *,
    host_manifest: str,
    project_manifest: str,
    session: int,
) -> tuple[preflight.Prerequisite, ...]:
    """Probe every prerequisite once, and let `preflight` say what it means.

    The subprocess and the filesystem reads live here; the verdicts live in
    `agentic_postgres.preflight` (ADR 0157), which is `database_observation`'s
    split and for its reason — this file needs root, so nothing in it is
    testable behaviourally.

    **Nothing here writes.** That is the whole of step 0, and it is why the
    `require_*` functions below are untouched: they exit on the first absence
    *and* they return the values `build_deployed_document` is assembled from, so
    duplicating them here would put two authorities over one document.
    """
    reachable = False
    timed_out = False
    error = ""
    names: tuple[str, ...] = ()
    try:
        # `timeout=` is the point (D631): `run()` has none, and a daemon that
        # ACCEPTS a connection and never answers left `docker ps` running past
        # 20s in Run 1 — no output, no absence reported, and a deploy hung
        # before it had done anything.
        probe = subprocess.run(
            ("docker", "ps", "--format", "{{.Names}}"),
            capture_output=True,
            text=True,
            check=False,
            timeout=preflight.DAEMON_TIMEOUT_SECONDS,
        )
        reachable = probe.returncode == 0
        error = probe.stderr
        names = tuple(probe.stdout.split())
    except subprocess.TimeoutExpired:
        timed_out = True
    except OSError as problem:
        error = str(problem)

    daemon = preflight.docker_daemon(reachable=reachable, timed_out=timed_out, error=error)

    edge = preflight.edge_plane(
        daemon=daemon,
        running_names=names,
        stack_name=EDGE_STACK_NAME,
        host_manifest=host_manifest,
    )

    state = state_path(project_key)
    bootstrap_error = ""
    bootstrap_readable = True
    try:
        load_state(state)
    except OSError as problem:
        # BEFORE the broad clause, and D636 is why: `Path.exists()` swallows
        # ENOENT and *raises* EACCES, so a state file this process cannot
        # traverse to is one nobody looked at rather than one that is missing.
        bootstrap_readable = False
        bootstrap_error = f"{state} could not be read: {problem}"
    except Exception as problem:
        # Broad on purpose: `require_bootstrap` catches the same way. Missing,
        # malformed JSON and schema-invalid are one absence to an operator, and
        # all three need the same command.
        bootstrap_error = f"{state}: {problem}"

    bootstrap = preflight.provider_bootstrap(
        error=bootstrap_error,
        state_path=str(state),
        host_manifest=host_manifest,
        project_manifest=project_manifest,
        readable=bootstrap_readable,
    )

    secret_readable, secret_error, generation = _observe_secret_generation(project_key)
    secrets = preflight.secret_generation(
        error=secret_error,
        generation_id=generation,
        project_manifest=project_manifest,
        session=session,
        readable=secret_readable,
    )

    return (daemon, edge, bootstrap, secrets)


def _observe_secret_generation(project_key: str) -> tuple[bool, str, str]:
    """`require_secret_generation`'s two reads, reporting instead of exiting.

    Returns ``(readable, error, generation_id)``. Both the pointer and the
    manifest it names, for the reason that function gives: a pointer naming a
    generation whose manifest is missing describes a directory nothing can
    account for.

    **Every `exists()` here is guarded** (D636). The secret root is `0700 root`,
    so an unprivileged caller gets `EACCES`, and `Path.exists()` raises on it
    rather than answering False. Uncaught, that turns "report the absence" into
    a traceback — which is the one outcome step 0 exists to prevent.
    """
    project_root = SECRET_ROOT / project_key
    pointer = project_root / "active-secret-generation.json"
    try:
        pointer_exists = pointer.exists()
    except OSError as problem:
        return False, f"{pointer} could not be read: {problem}", ""
    if not pointer_exists:
        return True, f"no active generation pointer at {pointer}", ""

    try:
        generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
    except OSError as problem:
        return False, f"{pointer} could not be read: {problem}", ""
    except (ValueError, KeyError) as problem:
        return True, f"{pointer} is malformed: {problem}", ""

    manifest_path = project_root / "generations" / generation / "manifest.json"
    try:
        manifest_exists = manifest_path.exists()
    except OSError as problem:
        return False, f"{manifest_path} could not be read: {problem}", generation
    if not manifest_exists:
        return (
            True,
            f"generation {generation} has no manifest.json; it predates this release",
            generation,
        )
    return True, "", generation


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
            # The same query `cluster_instance_uuid` runs, through the same psql
            # this function already opened. Read here rather than passed in from
            # the caller so that the deployed document's copy and the registry's
            # key come from one place: the cluster.
            instance_uuid=psql("SELECT instance_uuid FROM app_private.project_identity;"),
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


def publish_edge_credentials(
    *,
    project_key: str,
    generation_id: str,
    middleware_name: str,
    metrics_middleware_name: str,
    runtime_image: str,
) -> None:
    """Write the edge credentials and the middlewares that check them.

    **The first caller `edge_credentials` has ever had.** The module was
    complete, tested and referenced by nothing, so the middleware every
    documentation router names did not exist -- and Traefik does not create a
    router whose middleware is undefined. The route answered the edge's own 404,
    which is indistinguishable from an unrouted host from outside (D186, D204).

    The hash is produced **inside the locked runtime image**, not here. `crypt`
    was removed from the standard library in 3.13 and the host's interpreter is
    past that, so the deploy cannot hash anything itself. Measured on the locked
    digest before this was written: `crypt.methods` offers `BLOWFISH`,
    `mksalt(METHOD_BLOWFISH)` yields a 60-character `$2b$12$` hash that
    `assert_bcrypt` accepts and that verifies against its own password -- with a
    `$6$` control refused, which is the format Traefik answers 401 to in a way
    indistinguishable from a wrong password (D165).

    **The password reaches the container on stdin.** Not in `argv`, which is one
    of the four places a secret must not be, and `-i` is required or stdin is
    never attached and the container exits 0 having produced nothing.

    Rewritten on every deploy. bcrypt salts randomly, so the hash differs each
    time while the password does not. A conditional write would be an
    optimisation bought with a branch that is wrong when the generation moved.

    **The hash goes inline into the middleware document** (ADR 0086). This
    docstring used to continue "the file changes, Traefik reloads it, and the
    credential an operator holds keeps working", and the host proved that
    sentence false on the first documentation rotation this project ever
    performed: new password 401, **old password 200**, correct hash on disk
    (D252). The middleware named a `usersFile` *path*, so the parsed
    configuration was identical either way and Traefik never rebuilt the one
    component that re-reads that file. Now the rotation and the document the
    provider parses are the same write.
    """

    def materialized(name: str, what: str) -> Path:
        path = (
            SECRET_ROOT
            / project_key
            / "generations"
            / generation_id
            / secrets_contract.ROOT_PLANE_DIRECTORY
            / name
        )
        if not path.is_file():
            fail(
                EXIT_PRECONDITION,
                f"no {what} at {path}. It is declared in secrets.required.yaml "
                "with a root-plane consumer; re-run bin/materialize-secrets.sh.",
            )
        return path

    source = materialized("docs_basic_auth_password", "documentation credential")
    metrics_source = materialized("metrics_basic_auth_password", "metrics credential")

    hashed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            runtime_image,
            "python",
            "-c",
            # No strip in here, and no escape. The caller sends exactly the
            # password, and a `\\n` written into a `-c` program from Python
            # source is a newline character rather than an escape -- which
            # split this program across two lines and killed it with
            # `unterminated string literal` on its first deploy (D205).
            "import crypt,sys;"
            "print(crypt.crypt(sys.stdin.read(), crypt.mksalt(crypt.METHOD_BLOWFISH)))",
        ],
        input=source.read_text(encoding="utf-8").rstrip("\n"),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if hashed.returncode != 0:
        # stderr, never stdout: the hash is on stdout and a failure message
        # quoting it would put a password hash in the deploy log.
        fail(EXIT_PRECONDITION, f"could not hash the documentation credential: {hashed.stderr}")

    # The second credential, through the same image and the same stdin rule.
    # A separate invocation rather than one that hashes both: bcrypt salts
    # randomly per call, and a helper returning two hashes from one program
    # would put two passwords in one container's stdin for no gain.
    metrics_hashed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            runtime_image,
            "python",
            "-c",
            "import crypt,sys;"
            "print(crypt.crypt(sys.stdin.read(), crypt.mksalt(crypt.METHOD_BLOWFISH)))",
        ],
        input=metrics_source.read_text(encoding="utf-8").rstrip("\n"),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if metrics_hashed.returncode != 0:
        fail(EXIT_PRECONDITION, f"could not hash the metrics credential: {metrics_hashed.stderr}")

    EDGE_DYNAMIC_DIR.mkdir(parents=True, exist_ok=True)
    middleware = EDGE_DYNAMIC_DIR / edge_credentials.middleware_file_name(project_key)
    _write_root_only(
        middleware,
        edge_credentials.render_middleware(
            middleware_name=middleware_name,
            project_key=project_key,
            hashed=hashed.stdout.strip(),
            metrics_middleware_name=metrics_middleware_name,
            metrics_hashed=metrics_hashed.stdout.strip(),
        ),
    )

    # Every project deployed before ADR 0086 left a `<key>.htpasswd` here,
    # holding a bcrypt hash nothing reads any more. Unlinked rather than left:
    # a credential file no rotation reaches is the artifact this project keeps
    # finding, and one that is also invisible to the provider would never be
    # found at all. `missing_ok`, because the second deploy has nothing to
    # remove and that is not an error.
    retired = EDGE_DYNAMIC_DIR / edge_credentials.retired_users_file_name(project_key)
    removed = retired.exists()
    retired.unlink(missing_ok=True)

    # The path, never the contents.
    print(f"  {middleware} (0600, two middlewares, bcrypt inline)")
    if removed:
        print(f"  {retired} removed (ADR 0086: the hash is inline now)")


def observe_docs(url: str) -> str:
    """`ready` when the documentation route **refuses** without a credential.

    The success condition is a 401 carrying a Basic challenge, and it is
    delegated to `bin/docs.py::check` rather than restated here -- that command
    is the operator's way of asking the same question, and two readings of
    "is this route published" is exactly the shape D177 produced for the path.

    Three things are not `ready`, and each has to be distinguishable from the
    others by the message `check` prints:

    * **200 without a credential.** The page is being served to anyone who asks,
      which is worse than an unpublished route and must never record `ready`.
    * **A status that is neither.** Traefik's own 404 for an unrouted host looks
      identical from outside to a routed 404 (D186), so the honest record is
      `unavailable` and the log line says what came back.
    * **401 with no challenge.** A refusal a browser cannot act on, and what a
      middleware chain that half-resolved produces.

    `unavailable` rather than an exception on any failure, for the reason
    `observe_served_document` gives: a deploy that cannot describe its own route
    has still deployed, and the honest record of that is a status rather than a
    traceback that leaves the service running and the document unwritten.
    """
    docs = _load_command("docs.py", "apg_deploy_docs")
    try:
        return "ready" if docs.check(url) == 0 else "unavailable"
    except Exception as error:
        # `check` handles an HTTP response; a connection that never became one
        # -- DNS, TLS, refused -- arrives here. That is the state a project is
        # in between `compose up` and Traefik noticing the container.
        print(f"  no documentation route: {type(error).__name__}: {error}")
        return "unavailable"


def observe_active_administrator(database: dict[str, Any]) -> bool:
    """Whether this project has an active administrator (D230).

    **The gate on publishing `routes.app`.** No public application route may be
    published before an administrator exists, because the first request to reach
    one that has none is the request that decides who the administrator is.

    D135 refused inventing a deployment state for this and D230 kept the
    refusal: it is a *status field*, not a state machine, and every route
    already has one. `routes.app` is `unavailable` until this returns True,
    exactly as `routes.rest` is `unavailable` for a project that declares no
    REST service (ADR 0062).

    Asked of the registry rather than of the service, and as `object_owner`
    through the same definer function `bin/auth-admin.sh list` uses -- so the
    deploy and the operator's own command answer from one place. `auth_list_users`
    returns no verifier and no hash, which is a property of the function rather
    than of this caller remembering.

    **False on every failure, and that is the safe direction.** A migration not
    yet applied, a table that does not exist, a cluster that will not answer:
    each of them means this deploy cannot show an administrator exists, and the
    honest record of "cannot show" is the same as "there is none" for a decision
    about whether to publish.
    """
    #: Neither name is interpolated into this string. `:"name"` becomes a quoted
    #: identifier and `:'name'` a quoted literal, both by psql rather than by an
    #: f-string -- so a role name is never concatenated into SQL here.
    #:
    #: **The SQL goes on stdin, and that is not a style choice.** Measured
    #: against the locked PostgreSQL image: psql performs **no** variable
    #: interpolation on a string passed with `-c`. `SET ROLE :"admin_owner"`
    #: reached the server verbatim and failed with `syntax error at or near ":"`.
    #: On stdin the same two lines interpolate -- `current_user` came back as
    #: the owner, a role nothing names counted 0 rather than erroring, and
    #: `x' OR '1'='1` as the literal counted 0 rather than every row. That is
    #: why `bin/auth-admin.py` reads its SQL from stdin too.
    statement = (
        'SET ROLE :"admin_owner";\n'
        "SELECT count(*) FROM app_private.auth_list_users()\n"
        " WHERE status = 'active' AND role_name = :'admin_role';\n"
    )

    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            database["container"],
            "psql",
            "-U",
            "postgres",
            "-d",
            database["name"],
            "-X",
            "-qtA",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            f"admin_owner={database['roles']['object_owner']}",
            "-v",
            f"admin_role={database['roles']['project_admin']}",
        ],
        input=statement,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        print("  no administrator could be read; routes.app stays unavailable (D230)")
        return False

    counted = result.stdout.strip()
    return counted.isdigit() and int(counted) > 0


def observe_app(url: str, *, administrator: bool) -> str:
    """`ready` when the application route **refuses** an unauthenticated caller.

    Two conditions, and both have to hold. The first is D230's: an active
    administrator exists. The second is the same shape `observe_docs` uses --
    the route answers, and it answers with a refusal. A 401 from
    `<routes.app>/auth/me` proves more than a 200 anywhere would: the router
    matched, the strip worked (FastAPI saw `/auth/me` rather than
    `/api/app/auth/me`, which would be a 404), and the service refused.

    A 404 here is Traefik's own or FastAPI's and the two are indistinguishable
    from outside (D186), so it records `unavailable` and prints what came back.
    """
    if not administrator:
        print("  no active project administrator; routes.app stays unavailable (D230)")
        return "unavailable"

    result = run(
        "curl",
        "-ksS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--max-time",
        "10",
        f"{url}/auth/me",
    )
    status = result.stdout.strip()
    if status == "401":
        return "ready"
    print(f"  the application route answered {status or '(nothing)'} rather than 401")
    return "unavailable"


#: The two halves of the R2 credential, by the names `secrets.required.yaml`
#: gives them. Read from the ACTIVE generation's required set rather than from
#: the manifest, because the manifest says what a deployment wants and the
#: generation says what it has -- which is the same distinction
#: `deployed_output.activated_login_roles` draws for the storage role's password,
#: and for the same reason: v11 was published while `CURRENT_SESSION` was 6.
STORAGE_CREDENTIAL_NAMES: tuple[str, ...] = ("r2_access_key_id", "r2_secret_access_key")


#: The three files the repository needs, by the names `secrets.required.yaml`
#: gives them. Read from the ACTIVE generation's required set for
#: `STORAGE_CREDENTIAL_NAMES`' reason: the manifest says what a deployment wants
#: and the generation says what it has (D76, D306).
#:
#: **Imported rather than declared, since Run 8** (D560). It was written here in
#: Run 6, when the deploy was its only reader; the restore drill is the second,
#: and it needs the same three names to decide which of the database container's
#: mounts to carry forward. Two tuples over one list is D264's shape, so the
#: declaration moved to `config` and this is a re-export for the readers already
#: naming it through this module.
BACKUP_CREDENTIAL_NAMES = config.BACKUP_CREDENTIAL_NAMES


def backup_credentialed_for(secrets: dict[str, Any]) -> bool:
    """Does the active generation carry all three repository files?

    **A function rather than an expression written twice** (Session 10 Run 6).
    Step 6c decides whether to touch the repository at all and step 7 decides
    what to publish about it, and those two must agree: a step 6c that ran
    against a generation step 7 then calls `unconfigured` would have created a
    stanza the document denies exists. Two `all(...)` comprehensions over one
    tuple is how that disagreement arrives, and it is the same shape as two
    arithmetics over one budget (D327).

    All three, never any: a partial set is a repository that authenticates and
    cannot decrypt, or decrypts and cannot authenticate.
    """
    required = secrets.get("required_names") or []
    return all(name in required for name in BACKUP_CREDENTIAL_NAMES)


def observe_backup(
    *,
    enabled: bool,
    credentialed: bool,
    summary: dict[str, Any] | None = None,
    archiver: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """What this deploy can honestly say about the repository. Version 13.

    **Run 6 makes this ask the repository**, which Run 3's version of this
    docstring said it would -- a sentence that would otherwise have become
    D276's shape, a comment describing work nobody wrote.

    The two input gates are unchanged and still come first, because a repository
    with no credential cannot be read at all:

    * backups off in the manifest -> `unconfigured`
    * on, but the active generation is missing one of the three files ->
      `unconfigured`, D326's two-stage convergence, the deploy exits 0

    Past those, ``summary`` is what `bin/backup.py info --json` produced from
    the repository's own report, and `backup_report` maps it. **`ready` is now
    reachable, and Run 3's test asserting it was not has been replaced by a
    stricter one** rather than deleted: what makes it safe is that something
    reads the repository, where Run 3 had only three files existing.

    ``summary`` is None when step 6c did not run -- a deploy through a session
    before 10, or one where the read itself failed. That is `not_observed`, and
    it is deliberately NOT `failing`: nothing was measured, and a status
    asserting a failure nobody observed is the same substitution in the other
    direction.
    """
    if not enabled:
        state = dict(deployed_output.BACKUP_NOT_OBSERVED)
        state["status"] = "unconfigured"
        return state
    if not credentialed:
        print("  no repository credential in the active generation; backup stays unconfigured")
        state = dict(deployed_output.BACKUP_NOT_OBSERVED)
        state["status"] = "unconfigured"
        return state
    if summary is None:
        return dict(deployed_output.BACKUP_NOT_OBSERVED)
    # **`with_archiver`, not `backup_state`** (D701). `summary` here is what
    # `bin/backup.sh info --json` printed, and that command prints an
    # already-computed state block -- so calling `backup_state` on it applied
    # the function to its own output. `status_for` reads `status_code`, the
    # state block has none, and the catch-all `return STATUS_FAILING` ran every
    # time: every deployed document published `failing` whatever the repository
    # actually said, and a redeploy could not correct it.
    #
    # The archiver still folds in, and can still only make the status worse.
    return backup_report.with_archiver(summary, archiver)


def read_backup_repository(release: Path, outputs_path: Path) -> dict[str, Any] | None:
    """The repository's own report, through the operator command that owns it.

    Through `bin/backup.py` rather than by running `docker exec pgbackrest`
    here, so there is ONE place that knows how pgBackRest is reached, which
    stanza it is asked about and which uid it runs as. A second call site is a
    second thing to keep in step with the config, and D543 is the record of how
    unhelpful pgBackRest's own error is when one of them is wrong.

    Returns None rather than raising: this is an observation, and a deploy that
    could not read the repository publishes `not_observed` instead of failing.
    **The failure that DOES fail a deploy is step 6c's `check`**, which has
    already run by the time this is called -- so a repository that is genuinely
    broken has stopped the deploy before it reaches here.
    """
    result = run(
        str(release / "bin" / "backup.sh"),
        "--outputs",
        str(outputs_path),
        "info",
        "--json",
    )
    if not result.stdout.strip():
        print(f"  could not read the repository (exit {result.returncode}); backup not_observed")
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        # Never echo the output. A failing command can print its own
        # configuration, and that carries the bucket and the prefix.
        print("  the repository report was not JSON; backup not_observed")
        return None


def read_archiver(database: dict[str, Any]) -> dict[str, Any] | None:
    """`pg_stat_archiver`, read from the cluster this deploy just started.

    **The archiver and the repository fail independently** (ADR 0150), which is
    why this is a second read rather than something `bin/backup.sh` returns: a
    repository full of good backups can sit behind an archiver that stopped an
    hour ago, and `pgbackrest info` would report `ok` for it. The repository says
    what was saved; this says whether anything still is.

    Returns None rather than failing the deploy. Step 6c has already run `check`
    by the time this is called, so an archiver that is genuinely broken has
    stopped the deploy with a named reason -- and a read that fails here should
    publish "nobody looked" rather than a status nobody measured.
    """
    result = run(
        "docker",
        "exec",
        "-i",
        database["container"],
        "psql",
        "-U",
        "postgres",
        "-d",
        database["name"],
        "-X",
        "-qtA",
        "-F",
        backup_report.ARCHIVER_SEPARATOR,
        "-c",
        backup_report.ARCHIVER_QUERY,
    )
    if result.returncode != 0:
        print("  could not read pg_stat_archiver; the WAL counters stay null")
        return None
    archiver = backup_report.parse_archiver(result.stdout)
    if archiver is None:
        print("  pg_stat_archiver returned nothing readable; the WAL counters stay null")
    return archiver


def observe_storage(url: str, *, credentialed: bool) -> str:
    """`ready` when the storage route **refuses** an unauthenticated caller.

    D326's shape, and `observe_app`'s exactly: a status field rather than the
    deployment state the runbook wanted, `unavailable` until the input exists,
    the command printed, and the deploy exits 0.

    **The gate is the credential**, because a storage container without one
    starts, serves, and answers every request with the 404 its provider errors
    collapse to (`storage_routes._guard`) -- which is indistinguishable from an
    object that is not yours. A route that answers a refusal for the wrong
    reason is exactly the false green this repository keeps producing.

    **The probe is a 401 from a well-formed object id.** It proves four things a
    200 anywhere could not: the storage router matched rather than the
    application router one segment above it (ADR 0108 -- the two overlap, and
    the wrong winner answers 404 from FastAPI, which at the edge is Traefik's
    own 404 for all anyone can see); the strip worked, since the service routes
    `/objects/{id}/download-url` at its root; the process is up; and it refuses.

    The id is a fixed all-zeroes uuid rather than a random one, so the request
    is reproducible and names nothing that could exist. It never reaches the
    ownership filter: authentication fails first.
    """
    if not credentialed:
        print(
            "  no R2 credential in the active generation; routes.storage stays unavailable (D326)"
        )
        return "unavailable"

    result = run(
        "curl",
        "-ksS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--max-time",
        "10",
        f"{url}/objects/00000000-0000-4000-8000-000000000000/download-url",
    )
    status = result.stdout.strip()
    if status == "401":
        return "ready"
    print(f"  the storage route answered {status or '(nothing)'} rather than 401")
    return "unavailable"


def observe_mcp(url: str, *, lock_path: Path, project_key: str) -> tuple[str, dict[str, Any]]:
    """`ready` when the agent plane **refuses** an unauthenticated caller.

    `observe_storage`'s shape and D326's: a status field, `unavailable` until the
    surface answers, and the deploy exits 0 either way.

    **The probe is a 401 from an unauthenticated POST**, and it proves more than
    a 200 anywhere could. That the router matched at all -- `/mcp` is top-level,
    so a miss is Traefik's own 404, a 19-byte body carrying no `RouterName`
    (D186, D187, D353). That nothing was stripped, since the container serves
    `/mcp` at its own root and a strip would forward `/` to a 404. That the
    process is up. And that the token verifier is mounted in front of it: a
    **200 here would mean the boundary is gone**, so any status other than 401 --
    including success -- leaves the route unavailable.

    The block's fields come from the LOCK and from the runtime's own constants,
    never from this file: `protocol_revision` is the framework's (ADR 0123), and
    the two checksums identify the artefacts a reader would otherwise have to
    guess were the same one.
    """
    block = dict(deployed_output.MCP_NOT_PUBLISHED)

    result = run(
        "curl", "-ksS", "-o", "/dev/null", "-w", "%{http_code}",
        "--max-time", "10",
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-d", "{}",
        url,
    )  # fmt: skip
    status = result.stdout.strip()
    if status != "401":
        print(f"  the agent plane answered {status or '(nothing)'} rather than 401")
        return "unavailable", block

    if not lock_path.is_file():
        print(f"  no capability lock at {lock_path}; routes.mcp stays unavailable")
        return "unavailable", block

    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except ValueError as error:
        print(f"  the capability lock is unreadable ({error}); routes.mcp stays unavailable")
        return "unavailable", block

    # Asked of the container, never loaded here (D445, ADR 0093). What the
    # document publishes is then what the process answering requests holds.
    container = mcp_container(project_key)
    if container is None:
        print("  no single running agent-plane container; routes.mcp stays unavailable")
        return "unavailable", block
    reported = agent_plane_constants(container)
    if reported is None:
        return "unavailable", block
    revision, conformant, accepted = reported
    block = {
        "status": "ready",
        "protocol_revision": revision,
        "authorization_spec_conformant": conformant,
        "accepted_token_use": accepted,
        "capability_contract_sha256": lock.get("canonical_sha256"),
        "capability_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "tool_count": lock.get("tool_count"),
    }
    return "ready", block


#: What the agent plane is asked, inside its own container, to report about
#: itself. One line, importing the runtime module that container is serving from.
AGENT_PLANE_PROBE = (
    "import json, app.mcp_runtime as m; "
    "print(json.dumps([m.PROTOCOL_REVISION, m.AUTHORIZATION_SPEC_CONFORMANT, "
    "m.ACCEPTED_TOKEN_USE]))"
)


def agent_plane_constants(container: str) -> tuple[str, bool, str] | None:
    """The runtime's own published constants, read from the RUNNING container.

    **Not from the release**, and the difference is not stylistic. `mcp_runtime`
    imports `fastmcp`, `mcp.types` and the service package, none of which exist
    on the host -- so loading it here would raise `ModuleNotFoundError` at deploy
    time, which is D292 in the command where it costs most. The first version of
    this function did exactly that, and
    `test_no_operator_command_puts_a_service_directory_on_the_path` refused it
    (D445).

    Reaching the service's logic through its container is ADR 0093's rule, and
    the answer is stronger than reading the release: what the document publishes
    is what the process answering requests actually holds (D413).

    `None` when the container cannot answer, so the caller leaves the block
    unpublished rather than filling it with a guess.
    """
    result = run("docker", "exec", "-i", container, "python", "-c", AGENT_PLANE_PROBE)
    if result.returncode != 0:
        print(f"  the agent plane could not report its constants: {result.stderr.strip()[:160]}")
        return None
    try:
        revision, conformant, accepted = json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        print(f"  the agent plane's report is unreadable ({error})")
        return None
    return str(revision), bool(conformant), str(accepted)


def mcp_container(project_key: str) -> str | None:
    """The running agent-plane container for one project, found by label.

    Found rather than predicted: `naming` predicts Compose's container name and
    the model deliberately does not enforce it with `container_name:` (D55).
    """
    result = run(
        "docker", "ps",
        "--filter", f"label=apg.project.key={project_key}",
        "--filter", f"label=com.docker.compose.service={runtime_override.MCP_SERVICE}",
        "--format", "{{.Names}}",
    )  # fmt: skip
    names = [line for line in result.stdout.splitlines() if line.strip()]
    return names[0] if len(names) == 1 else None


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


def cluster_instance_uuid(container: str, database: str) -> str:
    """Read the identity the volume carries, from the cluster that carries it.

    Not from the deployed document, and not from anything the deploy computed:
    this UUID exists precisely because it is a property of the *data*. Reading
    it from a file that describes the data would make the allocation key a
    derivation again, which is the thing ADR 0042 chose against.

    This is also why a publication cannot be part of a first `up`. The UUID does
    not exist until the cluster has bootstrapped an empty volume, and bootstrap
    runs after `compose up --wait` returns.

    **``database`` is a parameter, and the first version hard-coded it to
    ``postgres``** (D113). ``-U postgres -d postgres`` reads perfectly naturally
    and is the maintenance database: ``app_private.project_identity`` is created
    by a migration inside the *project's* database, so the query returned
    "relation does not exist" on a cluster where the row was sitting there the
    whole time. It failed on the first host that ran it and could fail nowhere
    else -- there is no offline path through this function.
    """
    result = subprocess.run(
        [
            "docker", "exec", "-i", container,
            "psql", "-U", "postgres", "-d", database, "-X", "-qtA",
            "-c", "SELECT instance_uuid FROM app_private.project_identity",
        ],
        capture_output=True, text=True, check=False, timeout=60,
    )  # fmt: skip
    if result.returncode != 0:
        fail(
            EXIT_PRECONDITION,
            f"could not read the project identity from {container}: {result.stderr.strip()}. "
            "A publication is keyed by the identity the volume carries, so the cluster has "
            "to be up and bootstrapped before its ports can be reserved.",
        )
    value = result.stdout.strip()
    if not value:
        fail(EXIT_PRECONDITION, f"{container} has no project identity row yet")
    return value


def _live_allocation(project_key: str, instance_uuid: str | None) -> dict[str, Any] | None:
    """This project's live port allocation, or ``None``.

    Matched on the instance UUID when this deploy read one off the cluster, which
    is the identity the registry is actually keyed by. Before outputs version 5
    there was nothing to match on and this searched by project key, refusing
    ambiguity rather than taking a first match (D106) -- two live records for one
    key means the deploy cannot tell which cluster a published port reaches, and
    every assertion downstream would still pass.

    That path is kept for the deployment that reads no cluster: a session-2
    deploy interrogates nothing, so it has no UUID and no business inventing one.
    Released records are excluded either way, so a project whose ports were given
    up publishes `unavailable` rather than a number nothing is serving.
    """
    path = Path(port_allocations.REGISTRY_PATH)
    if not path.is_file():
        return None
    registry = json.loads(path.read_text(encoding="utf-8"))
    live = port_allocations.live_allocations(registry)

    if instance_uuid is not None:
        matched = [a for a in live if a["instance_uuid"] == instance_uuid]
        if matched and matched[0]["project_key"] != project_key:
            fail(
                EXIT_VALIDATION,
                f"the live allocation for instance {instance_uuid} records the project "
                f"key {matched[0]['project_key']!r}, and this deploy is {project_key!r}. "
                "The cluster and the registry disagree about what this project is "
                "called, and publishing an endpoint would resolve that disagreement by "
                "picking one.",
            )
        return matched[0] if matched else None

    keyed = [a for a in live if a["project_key"] == project_key]
    if len(keyed) > 1:
        fail(
            EXIT_VALIDATION,
            f"{len(keyed)} live port allocations record the project key {project_key}. "
            "The registry is keyed by the volume's instance UUID and records the key "
            "only for humans; publishing an endpoint from either would be publishing "
            "a port that may reach the other cluster.",
        )
    return keyed[0] if keyed else None


def render_runtime_only(arguments: argparse.Namespace) -> int:
    """Reserve two ports and publish them in the override. Move nothing (D95).

    The order matters and is the whole point: reserve, render, and stop. The
    allocation stays `reserved` until something has connected to both endpoints,
    which is `database-ports.sh verify`, which happens after a restart this
    command deliberately does not perform. A crashed run therefore leaves a
    reservation that can be proved unadopted rather than an active allocation
    nothing is listening on.
    """
    if os.geteuid() != 0:
        fail(EXIT_PREREQUISITE, "must run as root")

    try:
        host = load_host_manifest(arguments.host)
        manifest = load_project_manifest(arguments.project)
    except ManifestError as error:
        fail(EXIT_INPUT, str(error))

    key = derive_project_key(manifest["project"]["slug"], manifest["project"]["environment"])
    state_directory = deployed_output.PROJECT_STATE_ROOT / key
    if not (state_directory / "outputs.json").is_file():
        fail(
            EXIT_PRECONDITION,
            f"{key} has no deployed document. A runtime render publishes ports for a "
            "project that is already deployed; deploy it first.",
        )

    document = json.loads((state_directory / "outputs.json").read_text(encoding="utf-8"))
    container = document["database"]["container"]
    instance_uuid = cluster_instance_uuid(container, document["database"]["name"])

    access = host["database_access"]
    step("1. Reserve two host-loopback ports")
    reserved = run(
        str(REPO_ROOT / "bin" / "database-ports.sh"),
        "allocate",
        "--host", str(arguments.host),
        "--project-key", key,
        "--instance-uuid", instance_uuid,
    )  # fmt: skip
    print(reserved.stdout, end="")
    if reserved.returncode != 0:
        fail(EXIT_VALIDATION, f"could not reserve ports for {key}:\n{reserved.stderr}")

    shown = run(
        str(REPO_ROOT / "bin" / "database-ports.sh"),
        "show", "--instance-uuid", instance_uuid,
    )  # fmt: skip
    allocation = next(
        (line.split() for line in shown.stdout.splitlines() if instance_uuid in line),
        None,
    )
    if allocation is None:
        fail(EXIT_PRECONDITION, f"no allocation recorded for {key} after reserving one")
    pooled, direct = int(allocation[2]), int(allocation[3])

    step("2. Render the override (which publishes nothing -- ADR 0044)")
    rendered_directory = deployed_output.rendered_path(key)
    compose_env = rendered_directory / "compose.env"
    payload = runtime_override.render_override(
        **_override_names(compose_env),
        https_entrypoint=host["edge"]["https_entrypoint"],
        rendered_directory=str(rendered_directory),
    )
    _write_root_only(rendered_directory / "runtime-compose.override.yaml", payload)
    print(f"  {rendered_directory / 'runtime-compose.override.yaml'}")

    # The allocation names the port a DEVELOPER binds, not one this host opens
    # (ADR 0044). Docker installs no rule and no listener for a container on an
    # internal network, and the transports are reached instead by an SSH forward
    # to the container's own address -- which the broker resolves per call and
    # nothing writes down.
    print(f"  {access['loopback_address']}:{pooled} is the near end of a pooled tunnel")
    print(f"  {access['loopback_address']}:{direct} is the near end of a direct tunnel")
    print("  no host port is opened; nothing is published")

    print("\n\033[1mNothing was started, and no allocation was marked active.\033[0m")
    print("The allocation becomes active once both transports have answered:")
    print(f"  sudo bin/database-ports.sh verify --host <host.yaml> --instance-uuid {instance_uuid}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--capabilities", required=True, type=Path)
    parser.add_argument("--through-session", type=int)
    parser.add_argument("--render-runtime-only", action="store_true", dest="render_runtime_only")
    arguments = parser.parse_args(argv)

    if arguments.render_runtime_only:
        return render_runtime_only(arguments)

    if arguments.through_session is None:
        fail(EXIT_INPUT, "--through-session is required unless --render-runtime-only is given")

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

    # Step 0, and the number matters: everything above this line reads. The
    # render below writes `.generated/<key>`, so a refusal arriving after it has
    # already changed the checkout it was refusing to deploy from (D614).
    step("0. Preflight — read everything, change nothing")
    checks = observe_prerequisites(
        key,
        host_manifest=str(arguments.host),
        project_manifest=str(arguments.project),
        session=arguments.through_session,
    )
    print(preflight.report(checks))
    blocked = preflight.exit_kind(checks)
    if blocked is not None:
        fail(
            EXIT_PREREQUISITE if blocked == preflight.KIND_PREREQUISITE else EXIT_PRECONDITION,
            "the deploy has not started; supply what is listed above and re-run.",
        )

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
    # Both git calls above can rewrite `.git/index` as root. Handed back here
    # rather than at the end, so a later failure still leaves the operator able
    # to run `git fetch` and try again (D194).
    _restore_git_index_ownership()
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
        **_override_names(rendered_dir / "compose.env"),
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

    step("5. Start the data plane, holding back what the bootstrap must precede")
    # From the release, not the checkout. Compose records its project directory
    # on every container it starts, and starting from `REPO_ROOT` stamped
    # `/home/<operator>/agentic-postgres` onto them -- the working tree that a
    # `git checkout` can change under a running deployment. That is the same
    # rule the systemd launchers enforce, and the deploy was the one path
    # ignoring it.
    #
    # `--defer` is ADR 0063. A service that authenticates as a project role
    # cannot start until step 6 has activated that role, and step 6 needs the
    # cluster this step starts -- so neither ordering works alone and the start
    # is split. The deferred set is declared in `runtime_override`, not here: a
    # second list is the one that goes stale when a service is added.
    #
    # The edge is not attached while anything is deferred, which is also §4.1's
    # rule that the route is added last.
    # The UNION of the two deferral reasons (ADR 0133). It was
    # `POST_BOOTSTRAP_SERVICES` alone until Run 10, which meant the agent plane
    # -- correctly absent from that tuple, because it authenticates as no role
    # (D410) -- was started here, eighty lines before the key set and the
    # capability lock it mounts are written. Docker created both sources as
    # directories and the container exited 1 on its first start anywhere (D463).
    deferred = ",".join(runtime_override.DEFERRED_SERVICES)
    require_mounts_exist(
        override_payload,
        [
            name
            for name in runtime_override.override_service_names(override_payload)
            if name not in set(runtime_override.DEFERRED_SERVICES)
        ],
        when="step 5",
    )
    started = run(
        str(release / "bin" / "project-runtime.sh"),
        "--host",
        str(arguments.host),
        "--project-key",
        key,
        "--through-session",
        str(arguments.through_session),
        "--defer",
        deferred,
        "up",
    )
    print(started.stdout, end="")
    if started.returncode != 0:
        fail(EXIT_VALIDATION, f"the project did not start:\n{started.stderr}")

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

    # The documentation credential and its middleware, into the edge's file
    # provider. **After the re-read**, for the reason the JWKS below gives: step
    # 5 materialized a new generation, and hashing the superseded one would
    # publish a credential the operator's own copy no longer matches.
    #
    # Before the edge is attached in 6b, so the middleware exists by the time
    # Traefik first sees a router that names it. Out of order it still converges
    # -- the provider watches the directory -- but the window is a route that
    # 404s for a reason nobody can distinguish from a missing service.
    if arguments.through_session >= REST_PLANE_SESSION:
        publish_edge_credentials(
            project_key=key,
            generation_id=secrets["generation_id"],
            middleware_name=_env_value(
                rendered_directory / "compose.env", "DOCS_CREDENTIAL_MIDDLEWARE_NAME"
            ),
            metrics_middleware_name=_env_value(
                rendered_directory / "compose.env", "METRICS_CREDENTIAL_MIDDLEWARE_NAME"
            ),
            runtime_image=_env_value(release / "versions.env", "PYTHON_RUNTIME_IMAGE"),
        )

    # The verification JWKS, derived from the bootstrap signing key (ADR 0051).
    #
    # **After the re-read, not in step 4.** Step 5 materializes a new generation
    # and repoints the project at it, so a JWKS derived from the generation that
    # was active before this deploy would be read from a directory the deploy has
    # already superseded -- D76's trap, one artifact along. The values are stable
    # across generations, so it would usually be right, which is what would keep
    # it from being noticed.
    #
    # Before the bootstrap and therefore before `resume`, which is when PostgREST
    # first starts and mounts it. A bind mount whose source does not exist is
    # created by Docker as a *directory*, and the symptom of that is a service
    # reading a key set it cannot parse.
    #
    # A project deployed through an earlier session runs nothing that verifies a
    # token and materializes no signing key, so there is nothing to derive.
    if arguments.through_session >= REST_PLANE_SESSION:
        jwks = run(
            # `sys.executable`, not the shebang. Ubuntu ships no bare `python`,
            # and a `#!/usr/bin/env python` line fails with `env: 'python': No
            # such file or directory` -- which is what the first live run of this
            # step did. Every other Python this deploy invokes goes through a
            # `.sh` wrapper with a `python_bin()` resolver; this one is called
            # directly, so it takes the interpreter already running the deploy.
            # That is also stricter than a resolver: it cannot pick a different
            # Python from the one whose imports were validated at startup.
            sys.executable,
            str(release / "bin" / "render-jwks.py"),
            "--project-key",
            key,
            "--generation",
            secrets["generation_id"],
            "--rendered-dir",
            str(deployed_output.rendered_path(key)),
        )
        print(jwks.stdout, end="")
        if jwks.returncode != 0:
            fail(EXIT_VALIDATION, f"the verification JWKS could not be derived:\n{jwks.stderr}")
    else:
        print("  no JWKS: this session runs no service that verifies a token")

    # Session 8, Run 6. The compiled capability lock, into the same rendered
    # directory the key set went to, from where `runtime_override.py` mounts it
    # read-only (ADR 0127).
    #
    # **Written in the run that consumes it.** A mount whose file nothing
    # produces is D381 exactly -- storage was declared the third verifier in
    # four places and handed no key set, and the gap was invisible until a
    # container started somewhere real. The producer and the consumer arrive
    # together or neither does.
    #
    # `--outputs` is the **rendered** document, out of the same directory the
    # lock is written into. It said "the document THIS deploy is about to write"
    # and passed `deployed_path` instead, which is two errors in one sentence
    # (D465): the deployed document is the PREVIOUS deploy's, because step 7
    # writes the new one long after this -- and the two branches carry
    # `routes.rest` in **different shapes**. Rendered it is a string; deployed it
    # is a published-route object. The compiler wants the string, got the object,
    # and wrote a lock whose `upstream` was a dict. The failure then surfaced at
    # container start as `LockError: the lock.upstream is not str`, which is
    # D389's shape: one field, two branches, a consumer reading the wrong one.
    #
    # The upstream it records is the public `routes.rest`, which names the API
    # surface the capabilities were compiled against and is NOT what the runtime
    # dials (ADR 0126).
    if arguments.through_session >= AGENT_PLANE_SESSION:
        lock_path = deployed_output.rendered_path(key) / runtime_override.MCP_LOCK_FILENAME
        compiled = run(
            str(release / "bin" / "mcp-contract.sh"),
            "lock",
            "--outputs",
            str(deployed_output.rendered_path(key) / "outputs.json"),
        )
        if compiled.returncode != 0:
            fail(
                EXIT_VALIDATION,
                f"the capability lock could not be compiled:\n{compiled.stderr}",
            )
        lock_path.write_text(compiled.stdout, encoding="utf-8")
        lock_path.chmod(0o444)
        print(f"  capability lock  {lock_path}")
    else:
        print("  no capability lock: this session runs no agent plane")

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

    require_mounts_exist(override_payload, runtime_override.DEFERRED_SERVICES, when="step 6b")
    step("6b. Start the deferred services and attach the edge")
    # Now, and not in step 5: the roles those services authenticate as exist and
    # can log in as of the bootstrap above (ADR 0063). `resume` materializes
    # nothing -- a second materialization here would repoint the project at a
    # generation whose password the bootstrap did not set.
    resumed = run(
        str(release / "bin" / "project-runtime.sh"),
        "--host",
        str(arguments.host),
        "--project-key",
        key,
        "--through-session",
        str(arguments.through_session),
        "resume",
    )
    print(resumed.stdout, end="")
    if resumed.returncode != 0:
        fail(EXIT_VALIDATION, f"the deferred services did not start:\n{resumed.stderr}")
    edge["project_network_attached"] = True

    # ------------------------------------------------------------------
    # Step 6c -- the repository (Session 10 Run 6, ADR 0149)
    # ------------------------------------------------------------------
    #
    # Here, and not earlier: `backup_user` can log in as of step 6, and the
    # rendered `pgbackrest.conf` and the three secret mounts are in place as of
    # step 5. Here, and not later: step 7 publishes what the repository reports,
    # so the stanza has to exist before anything reads it.
    #
    # `stanza-create` runs UNCONDITIONALLY rather than after a probe. Measured
    # (rig 6): twice in a row exits 0. A probe-then-create would buy nothing and
    # add a window in which the answer can change.
    #
    # **A `check` failure fails the deploy**, and that is the whole point of the
    # step. `check` is the only thing in this system that tests archiving end to
    # end -- it forces a WAL switch and confirms the segment reached the
    # repository. D534 measured what the alternative looks like from outside:
    # `pg_isready` answers *accepting connections* while `failed_count` climbs
    # 11 -> 15 -> 26 and `pg_wal` fills. Before this step, that deployment
    # converged cleanly and published nothing about it.
    # `--outputs` is the **rendered** document, for D465's reason one step up:
    # the deployed document is the PREVIOUS deploy's, because step 7 writes the
    # new one long after this. Unlike `routes.rest`, the `backup` block is ONE
    # shared `$def` referenced from both branches (ADR 0146), so the two agree in
    # shape and only the freshness matters -- which is exactly why 0146 chose a
    # shared definition over a copy per branch (D389).
    backup_summary: dict[str, Any] | None = None
    backup_archiver: dict[str, Any] | None = None
    if (
        rendered["backup"]["enabled"]
        and arguments.through_session >= BACKUP_PLANE_SESSION
        and backup_credentialed_for(secrets)
    ):
        step("6c. Create the backup stanza and prove archiving works")
        created = run(
            str(release / "bin" / "backup.sh"),
            "--outputs",
            str(deployed_output.rendered_path(key) / "outputs.json"),
            "stanza-create",
        )
        print(created.stdout, end="")
        if created.returncode != 0:
            fail(
                EXIT_VALIDATION,
                "the backup stanza could not be created, so this release has a cluster "
                "archiving WAL to a repository that does not exist:\n"
                f"{created.stderr}",
            )

        checked = run(
            str(release / "bin" / "backup.sh"),
            "--outputs",
            str(deployed_output.rendered_path(key) / "outputs.json"),
            "check",
        )
        print(checked.stdout, end="")
        if checked.returncode != 0:
            # Named reason, not a warning. An operator who sees "the deploy
            # failed" here needs to know it is the archiver rather than the
            # release, because the cluster itself is up and answering.
            fail(
                EXIT_VALIDATION,
                "WAL archiving does not work for this project. `pgbackrest check` forces "
                "a WAL switch and confirms the segment reached the repository, and it "
                "did not. The cluster is up and serving -- this is the archiver, and a "
                "cluster that cannot archive fills pg_wal until it stops:\n"
                f"{checked.stderr}",
            )
        backup_summary = read_backup_repository(
            release, deployed_output.rendered_path(key) / "outputs.json"
        )
        # Read here rather than in step 7, so that the repository's report and
        # the archiver's counters describe the same instant. Two reads minutes
        # apart could publish a `ready` repository beside counters taken after
        # something broke -- a document that is internally inconsistent about
        # one system.
        backup_archiver = read_archiver(rendered["database"])

    # The API plane, observed rather than asserted. Until Run 9 these four were
    # hard-coded `unavailable` with a comment saying "Session 5's runs replace
    # these with observations of a running PostgREST" -- which was the honest
    # record while nothing observed them, and is this run's work.
    rest_status = "unavailable"
    docs_status = "unavailable"
    # Version 9's two, and Run 10's. `unavailable` is the value for a deployment
    # through a session that does not start the auth service, and it is the
    # value for one that does and has no administrator yet (D230).
    app_status = "unavailable"
    app_docs_status = "unavailable"
    # Version 11's, and Run 7's. `unavailable` is the value for a deployment
    # through a session that does not select the `storage` container, and it is
    # the value for one that does and whose active generation carries no R2
    # credential (D326).
    storage_status = "unavailable"
    # Version 12's, and Session 8 Run 7's. `unavailable` for a deployment
    # through a session that does not select the `mcp` container, and for one
    # that does and whose route has not converged yet -- which is the first
    # deploy of any project, because the router is created by the same run that
    # starts the service (D326's two-stage shape, as `routes.app` and
    # `routes.storage` both use).
    mcp_status = "unavailable"

    # Version 14's, and it follows `mcp` exactly. `unavailable` for a
    # deployment through a session that does not select the `metrics`
    # container, and for one that does but whose router has not converged
    # yet -- which is every first deploy (D326's two-stage shape).
    #
    # **A 401 is the success condition, not a 200.** The route carries a
    # basic-auth middleware and this deploy holds no credential for it, so
    # a challenge is what a working route looks like from here -- the same
    # condition `observe_docs` already uses, and for the same reason.
    metrics_status = "unavailable"
    jwt_block = dict(deployed_output.JWT_NOT_PUBLISHED)
    api_block = dict(deployed_output.API_NOT_PUBLISHED)
    mcp_block = dict(deployed_output.MCP_NOT_PUBLISHED)

    if arguments.through_session >= REST_PLANE_SESSION:
        jwt_block = observe_jwt(
            rendered,
            deployed_output.rendered_path(key) / runtime_override.JWKS_FILENAME,
            # Read BEFORE this deploy overwrites it. The document on disk is
            # still the previous one at this point in the run, and it is the
            # only record of a rotation's deadline and its acknowledgements.
            previous_jwt_block(key),
        )
        rest_url = rendered["routes"]["rest"]
        # A route is `ready` when something answers on it, which the served
        # document below is the evidence of. Claiming `ready` because a container
        # is healthy would be a record about a process rather than about a route
        # -- and D145 measured `--ready` returning 0 while every request 404'd.
        served = observe_served_document(
            rest_url,
            jwt_block,
            {
                "project": {"key": key},
                "secrets": secrets,
                "database": {"roles": rendered["database"]["roles"]},
            },
        )
        if served is not None:
            rest_status = "ready"
        api_block = observe_api(deployed_output.rendered_path(key), served)

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

    # After the health route, and bounded the same way. Traefik's Docker
    # provider polls, so a router for a container that has only just started is
    # not wired at the instant `compose up --wait` returns -- observing once
    # recorded `unavailable` for a route that answered seconds later, which is
    # the note above this block and applies to every router equally.
    if arguments.through_session >= REST_PLANE_SESSION:
        docs_status = observation.await_observation(
            lambda: observe_docs(rendered["routes"]["docs"]),
            lambda observed: observed == "ready",
        )
        # The second documentation surface (D226). Same container, same
        # credential, same success condition -- a 401 with a Basic challenge --
        # and its own observation, because "the container is up" is not "this
        # router is wired": the two routers are separate labels and Traefik
        # accepts or drops them one at a time (D208).
        app_docs_status = observation.await_observation(
            lambda: observe_docs(rendered["routes"]["app_docs"]),
            lambda observed: observed == "ready",
        )

    if arguments.through_session >= APP_PLANE_SESSION:
        # D230's gate, and the order matters: the administrator is read first,
        # so a project that has none records `unavailable` without spending the
        # observation window polling a route it is not going to publish.
        administrator = observe_active_administrator(rendered["database"])
        app_status = observation.await_observation(
            lambda: observe_app(rendered["routes"]["app"], administrator=administrator),
            lambda observed: observed == "ready",
        )
        if not administrator:
            print(
                "\n  This project has no active administrator, so its application route "
                "is not published.\n  Create one, then re-run this deploy:\n\n"
                f"    sudo bin/auth-admin.sh --outputs {deployed_output.deployed_path(key)} "
                "bootstrap \\\n        --username <name> --display-name <name>\n\n"
                "  A project awaiting its first administrator is not a failed deploy."
            )

    if arguments.through_session >= STORAGE_PLANE_SESSION:
        # The credential is read first, for the reason the administrator above
        # is: a project without one records `unavailable` without spending the
        # observation window polling a route it is not going to publish.
        #
        # From the ACTIVE generation's required set, not from the manifest.
        # A project whose manifest declares storage and whose generation carries
        # no R2 credential is exactly the state a first Session 7 deploy is in,
        # and the two are different facts (D76, D306).
        credentialed = all(name in secrets["required_names"] for name in STORAGE_CREDENTIAL_NAMES)
        storage_status = observation.await_observation(
            lambda: observe_storage(rendered["routes"]["storage"], credentialed=credentialed),
            lambda observed: observed == "ready",
        )
        if not credentialed:
            missing = [
                name for name in STORAGE_CREDENTIAL_NAMES if name not in secrets["required_names"]
            ]
            print(
                "\n  This project has no R2 credential in its active secret generation, so "
                "its storage route\n  is not published. Provision it, then re-run this "
                f"deploy:\n\n    missing: {', '.join(missing)}\n"
                "    see docs/session-07-operator-guide.md for the provider steps\n\n"
                "  A project awaiting its storage credential is not a failed deploy (D326)."
            )

    # The repository, version 13. Unlike the three blocks around it this one
    # publishes for EVERY session rather than behind a `>= BACKUP_PLANE_SESSION`
    # guard, because `backup_state` is required on the deployed branch and its
    # honest value for a deployment that has no repository is a status, not an
    # absence. The guard is inside `observe_backup` instead, where it can say
    # which of the two `unconfigured` reasons applies.
    backup_credentialed = backup_credentialed_for(secrets)
    backup_state = observe_backup(
        enabled=bool(rendered["backup"]["enabled"])
        and arguments.through_session >= BACKUP_PLANE_SESSION,
        credentialed=backup_credentialed,
        # What step 6c read, or None if it did not run. The gate above is the
        # SAME function step 6c used, so the two cannot disagree about whether
        # this project has a repository (see `backup_credentialed_for`).
        summary=backup_summary,
        # And what the archiver said at the same instant (ADR 0150). The two
        # fail independently, so the status needs both.
        archiver=backup_archiver,
    )
    if (
        rendered["backup"]["enabled"]
        and arguments.through_session >= BACKUP_PLANE_SESSION
        and not backup_credentialed
    ):
        missing = [
            name for name in BACKUP_CREDENTIAL_NAMES if name not in secrets["required_names"]
        ]
        print(
            "\n  This project has no backup repository credential in its active secret\n"
            "  generation, so no backup can be taken. Provision it, then re-run this "
            f"deploy:\n\n    missing: {', '.join(missing)}\n"
            "    see docs/session-10-operator-guide.md for the provider steps\n\n"
            "  A project awaiting its repository credential is not a failed deploy (D326)."
        )

    # The agent plane, observed the way `routes.app` and `routes.storage` are.
    #
    # **Two stages, and the first deploy of any project sees the first.** The
    # router is created by the same run that starts the container, so the edge
    # has not attached the backend when this first runs -- the route settles on
    # the redeploy, and `await_observation` is what gives it the window rather
    # than a sleep (D326).
    if arguments.through_session >= METRICS_PLANE_SESSION:
        # The same predicate `docs` uses, and the same reason it is a 401: this
        # deploy holds no metrics credential, so a challenge proves the router
        # exists and the middleware is attached.
        #
        # **D204's failure is what this observes**, and it was found again in
        # Run 7 one route along: a router naming a middleware nothing defines is
        # not created, and the route answers Traefik's own 404 -- which D768
        # says must never be read as "metrics are not configured". A 404 leaves
        # this `unavailable`, which is the honest reading of it.
        metrics_status = observation.await_observation(
            lambda: observe_docs(rendered["routes"]["metrics"]),
            lambda observed: observed == "ready",
        )

    if arguments.through_session >= AGENT_PLANE_SESSION:
        mcp_status, mcp_block = observation.await_observation(
            lambda: observe_mcp(
                rendered["routes"]["mcp"],
                lock_path=(deployed_output.rendered_path(key) / runtime_override.MCP_LOCK_FILENAME),
                project_key=key,
            ),
            lambda observed: observed[0] == "ready",
        )

    # The transports, read out of the host's own allocation registry rather than
    # assumed from the fact that a pooler is running. `active` and nothing less
    # (D112): a reservation means two ports were set aside and nothing has
    # connected to either, and §4.1 puts the off-host scan before the promotion
    # that makes it active. So the first deploy of a project publishes
    # `unavailable`, the operator publishes and verifies, and the next deploy is
    # what records that the endpoints answer.
    transports = deployed_output.observe_transports(
        rendered=rendered,
        loopback_address=host["database_access"]["loopback_address"],
        allocation=_live_allocation(key, database_observed["instance_uuid"]),
    )
    for transport in ("pooled", "direct"):
        block = transports[transport]
        print(
            f"  {transport:<8} {block['status']}"
            + (f" {block['host']}:{block['port']}" if block["status"] == "available" else "")
        )

    document = deployed_output.build_deployed_document(
        rendered=rendered,
        transports=transports,
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
        # Version 5's three publication facts, and the honest values for a
        # deployment that publishes none of them. Session 5's runs replace these
        # with observations of a running PostgREST; until then a deploy that
        # wrote anything else would be claiming a surface it did not start.
        # There is deliberately no default for any of them: a default is how a
        # session-4 deployment would come to describe a session-5 shape.
        rest_status=rest_status,
        # Observed, since Run 9a built the service D128 left open (ADR 0069).
        # `ready` means the route answered 401 with a Basic challenge -- a
        # refusal, not a page -- because a documentation route that serves
        # without a credential is the one outcome that must never be recorded
        # as published.
        docs_status=docs_status,
        # Version 9's two, observed since Run 10. They were literal
        # `unavailable` from Run 4 until this run, exactly as `rest_status` and
        # `docs_status` were literal until the sessions that started those
        # surfaces replaced them.
        #
        # `app` is the application API route. D230: `ready` needs an active
        # project administrator **and** a route that refuses an unauthenticated
        # caller, because the first request to reach a published route with no
        # administrator is the request that decides who the administrator is.
        #
        # `app_docs` is the second documentation surface (D226), observed the
        # same way the first one is: a 401 with a Basic challenge.
        #
        # `publishedRoute` forces a null URL for anything `unavailable`, so
        # neither ever names an address nothing is listening on.
        app_status=app_status,
        app_docs_status=app_docs_status,
        # Version 11. `unavailable` until the R2 credential validates and the
        # route answers (D326), which makes this the provider-health field --
        # `publishedRoute` forces a null URL for it, so an unpublished storage
        # surface names no address.
        storage_status=storage_status,
        # Version 12. `unavailable` until an MCP runtime answers on the route
        # (D326's shape, a third time) -- and until Run 7 there is nothing to
        # answer. `publishedRoute` forces a null URL for it, so an unpublished
        # agent plane names no address.
        mcp_status=mcp_status,
        metrics_status=metrics_status,
        api=api_block,
        jwt=jwt_block,
        # Version 12, in `api_block`'s role: what the agent plane serves, or
        # `MCP_NOT_PUBLISHED` when it serves nothing. Passed explicitly rather
        # than defaulted, so a deploy that measured nothing cannot produce a
        # document indistinguishable from one that did.
        mcp=mcp_block,
        # Measured above when this deploy started a cluster, and `NOT_OBSERVED`
        # when it did not. A session-2 deployment interrogates nothing, and the
        # honest record of that is four nulls rather than an empty object a
        # reader could mistake for an empty database.
        database_observed=database_observed,
        backup_state=backup_state,
        deployed_through_session=arguments.through_session,
    )
    destination = deployed_output.write_deployed_document(
        document, deployed_output.deployed_path(key)
    )

    print(f"  {destination}")
    print(f"  tls          {document['tls']['status']} ({document['tls']['acme_environment']})")
    # Every route in the document, derived from the document rather than listed.
    # It was five hand-written lines and `rest` was not one of them -- the one
    # route the summary omitted was the one Session 5 was about, and nothing
    # noticed for two sessions because a missing line looks like a route that
    # does not exist. Deriving it means a sixth route is printed by existing.
    for name, route in sorted(document["routes"].items()):
        print(f"  {name.replace('_', ' '):12} {route['status']}")
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


# ---------------------------------------------------------------------------
# The API plane, observed (Run 9)
# ---------------------------------------------------------------------------


def _load_command(name: str, alias: str) -> Any:
    """Import one `bin/*.py` command from the installed release.

    Used where the deploy needs logic a command already owns -- minting a token,
    fetching the served document -- rather than growing a second copy. A second
    copy of "how a token is built" would let every observation below be wrong in
    a way that still looked like a working deployment.
    """
    import importlib.util

    source = Path(__file__).resolve().parent / name
    specification = importlib.util.spec_from_file_location(alias, source)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {source}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def previous_jwt_block(key: str) -> dict[str, Any]:
    """The `jwt` block the last deploy wrote, or an empty mapping.

    **The deployed document is the rotation's memory**, and this is where the
    next deploy reads it. Two members cannot be derived from anything on disk:
    `retire_after` is a moment a promotion chose, and
    `verifier_acknowledgements` is what each verifier reported having loaded.
    Both would be lost on every deploy if they were not carried forward, and
    losing an acknowledgement is not a small thing -- it is the record a
    promotion is blocked on (ADR 0088).

    An unreadable or absent document is an empty mapping rather than an error:
    the first deploy of a project has none, and a deploy that could not read the
    previous one has still deployed. What it must not do is invent a deadline.
    """
    path = deployed_output.deployed_path(key)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("jwt") or {}
    except (OSError, ValueError) as error:
        print(f"  the previous deployed document could not be read ({error}); no rotation state")
        return {}


def observe_jwt(
    rendered: dict[str, Any], jwks_path: Path, previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The issuer's public metadata, from the key set this deploy just wrote.

    Every member is something a verifier is entitled to hold: an issuer, an
    audience, an algorithm, key *identifiers* and a digest. No private JWK and no
    reference to one, which is what `SEC-BOOT-001` asserts.

    The kids are read out of the rendered file rather than recomputed here. The
    file is what PostgREST verifies against, so a document naming a different kid
    would be describing a key set nothing is using -- and recomputing from the
    private key would be a second derivation of the value ADR 0051 says has one.

    **`active_kid` is the first key, and that is a fact about `render-jwks.py`'s
    order rather than a convention.** It publishes the auth service's key first
    when the service exists, then the bootstrap issuer's, then any prepared key
    -- so the head of the set is the issuer whose tokens most callers hold. The
    two files agree through that order and nothing else, which is why it is
    stated in both.

    `retire_after` and `verifier_acknowledgements` are carried forward from
    `previous`. Neither is derivable from the key set: a deadline is a moment a
    promotion chose, and an acknowledgement is what a verifier reported. A deploy
    that reset them would silently unblock the next promotion.
    """
    if not jwks_path.is_file():
        return dict(deployed_output.JWT_NOT_PUBLISHED)

    previous = previous or {}
    raw = jwks_path.read_bytes()
    document = json.loads(raw)
    kids = [key["kid"] for key in document["keys"]]

    # A deadline is about a key that is still published. If the set no longer
    # holds two keys the rotation has been retired, and carrying its deadline
    # forward would describe an overlap that has ended -- which
    # `validate_key_state` refuses, and rightly.
    retire_after = previous.get("retire_after") if len(kids) > 1 else None
    acknowledgements = previous.get("verifier_acknowledgements") if len(kids) > 1 else None

    return {
        "status": "ready",
        "issuer": rendered["jwt"]["issuer"],
        "audience": rendered["jwt"]["audience"],
        "algorithm": jwt_keys.ALGORITHM,
        "active_kid": kids[0],
        "verification_kids": kids,
        "public_jwks_sha256": hashlib.sha256(raw).hexdigest(),
        # True until Session 6 replaces the issuer (ADR 0051). `SEC-BOOT-001`
        # compares this against `deployed_through_session` and goes red on the
        # deployment that should have retired it, which is what makes it a
        # value rather than a sentence.
        "temporary": True,
        # Carried forward, not recomputed. A deadline is the moment a promotion
        # chose and nothing on disk remembers it; recomputing it from `now`
        # would move the retirement further away on every deploy, which is a
        # rotation that never completes wearing the shape of one in progress.
        "retire_after": retire_after,
        # Version 9. Null rather than an empty object, and the difference is the
        # whole point: an empty object says every verifier was asked and none has
        # answered, and null says nothing has been asked.
        #
        # Also carried forward, and this is the member that matters most:
        # `promote_rotation` refuses unless every verifier's recorded digest
        # matches the published set, so a deploy that reset this would silently
        # unblock nothing -- it would silently *block* a promotion that had
        # already been earned, and an operator would re-run the acknowledgement
        # step wondering why it did not take.
        "verifier_acknowledgements": acknowledgements,
    }


def observe_served_document(rest_url: str, jwt_block: dict[str, Any], document: dict[str, Any]):
    """The digest of what the route is serving, or `None` with the reason printed.

    Fetched as the **documentation role**, because `follow-privileges` means the
    served document depends on the caller's grants and the one the snapshot is
    reviewed against is that role's (ADR 0050).

    `None` rather than an exception on any failure: a deploy that cannot read its
    own document has published something it cannot describe, and the honest
    record of that is `api.status: unavailable` rather than a failed deploy that
    leaves the service running and the document absent.
    """
    dev_token = _load_command("dev-token.py", "apg_deploy_dev_token")
    api_contract = _load_command("api-contract.py", "apg_deploy_api_contract")

    try:
        key_path = dev_token.signing_key_path(document["project"]["key"], document)
        token = dev_token.mint(
            key_path=key_path,
            role_name=document["database"]["roles"]["api_documentation"],
            # No subject. Migration 0009's hook refuses a documentation token
            # that carries one, so minting a subject would produce a credential
            # rejected by design.
            subject=None,
            ttl=120,
            document={"jwt": jwt_block},
        )
    except Exception as error:
        print(f"  no served document: could not mint a documentation token ({error})")
        return None

    previous = os.environ.get(api_contract.TOKEN_VARIABLE)
    os.environ[api_contract.TOKEN_VARIABLE] = token
    try:
        raw = api_contract.fetch_live(rest_url)
    except Exception as error:
        print(f"  no served document: {error}")
        return None
    finally:
        if previous is None:
            os.environ.pop(api_contract.TOKEN_VARIABLE, None)
        else:
            os.environ[api_contract.TOKEN_VARIABLE] = previous

    return openapi_normalize.fingerprint(
        openapi_normalize.sort_maps(openapi_normalize.load_document(raw))
    )


def observe_api(
    rendered_dir: Path, served_digest: str | None, snapshot: Path | None = None
) -> dict[str, Any]:
    """What the published surface actually serves, and the three checksums.

    **`ready` requires all three**, which the schema enforces and which makes the
    first deploy of a project necessarily `unavailable`: the canonical snapshot
    is captured *from* a running deployment, reviewed by a human and committed,
    so it does not exist until after the deploy that produces it. The redeploy at
    the approved commit is what records `ready` -- the two-deploy shape D112
    already established, arriving here for a second reason.

    The settings come from the rendered `compose.env`, which is what the running
    container was started from. Reading them from the manifest instead would
    describe what was asked for.
    """
    # A parameter with a default rather than a constant read inside, so that
    # both refusal branches below are reachable from a test. They were not:
    # with no snapshot committed the first branch always fired, the second
    # was dead, and a mutation that deleted it stayed green.
    snapshot = SNAPSHOT_PATH if snapshot is None else snapshot
    if not snapshot.is_file():
        print(
            "  api unavailable: no reviewed snapshot at contracts/"
            "postgrest-openapi.canonical.json. Capture one with "
            "`bin/api-contract.sh --update`, review it, commit it, and redeploy"
        )
        return dict(deployed_output.API_NOT_PUBLISHED)

    if served_digest is None:
        return dict(deployed_output.API_NOT_PUBLISHED)

    environment = rendered_dir / "compose.env"
    return {
        "status": "ready",
        "exposed_schema": _env_value(environment, "POSTGREST_EXPOSED_SCHEMA"),
        "max_rows": int(_env_value(environment, "POSTGREST_MAX_ROWS")),
        "request_body_max_bytes": int(_env_value(environment, "API_REQUEST_BODY_MAX_BYTES")),
        "pool_size": int(_env_value(environment, "POSTGREST_POOL_SIZE")),
        "connection_budget_reserved": int(_env_value(environment, "POSTGREST_POOL_SIZE"))
        + config.POSTGREST_RESERVED_CONNECTIONS,
        "api_surface_sha256": api_surface.contract_digest(),
        "canonical_openapi_sha256": openapi_normalize.fingerprint(
            openapi_normalize.load_document(snapshot.read_bytes())
        ),
        "project_openapi_sha256": served_digest,
    }


if __name__ == "__main__":
    raise SystemExit(main())

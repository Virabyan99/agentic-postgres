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
}


def _override_names(compose_env: Path) -> dict[str, str]:
    """The name arguments `render_override` takes, read from one compose.env.

    `_env_value` fails the deploy on a missing key rather than defaulting, so a
    name this repository derives and forgets to emit is a refusal at step 4
    rather than a router that quietly is not there.
    """
    return {keyword: _env_value(compose_env, key) for keyword, key in OVERRIDE_NAME_KEYS.items()}


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


def publish_docs_credential(
    *, project_key: str, generation_id: str, middleware_name: str, runtime_image: str
) -> None:
    """Write the documentation credential and the middleware that checks it.

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
    source = (
        SECRET_ROOT
        / project_key
        / "generations"
        / generation_id
        / secrets_contract.ROOT_PLANE_DIRECTORY
        / "docs_basic_auth_password"
    )
    if not source.is_file():
        fail(
            EXIT_PRECONDITION,
            f"no documentation credential at {source}. It is declared in "
            "secrets.required.yaml with a root-plane consumer; re-run "
            "bin/materialize-secrets.sh.",
        )

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

    EDGE_DYNAMIC_DIR.mkdir(parents=True, exist_ok=True)
    middleware = EDGE_DYNAMIC_DIR / edge_credentials.middleware_file_name(project_key)
    _write_root_only(
        middleware,
        edge_credentials.render_middleware(
            middleware_name=middleware_name,
            project_key=project_key,
            hashed=hashed.stdout.strip(),
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
    print(f"  {middleware} (0600, bcrypt inline)")
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
    deferred = ",".join(runtime_override.POST_BOOTSTRAP_SERVICES)
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
        publish_docs_credential(
            project_key=key,
            generation_id=secrets["generation_id"],
            middleware_name=_env_value(
                rendered_directory / "compose.env", "DOCS_CREDENTIAL_MIDDLEWARE_NAME"
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
    # Version 11's, and it is literal for exactly as long as `app_status` was
    # (Run 4 to Run 10): this run publishes no storage route, so `unavailable`
    # is not a placeholder standing in for an observation -- it IS the
    # observation. Session 7 Run 7 replaces it with one that measures, and
    # D326 is why it is a route status rather than a deployment state.
    storage_status = "unavailable"
    jwt_block = dict(deployed_output.JWT_NOT_PUBLISHED)
    api_block = dict(deployed_output.API_NOT_PUBLISHED)

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
        api=api_block,
        jwt=jwt_block,
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
    print(f"  docs         {document['routes']['docs']['status']}")
    print(f"  app          {document['routes']['app']['status']}")
    print(f"  app docs     {document['routes']['app_docs']['status']}")
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

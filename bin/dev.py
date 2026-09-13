#!/usr/bin/env python3
"""`apg dev` — a disposable local cluster with this release's schema on it.

Invoked only by `bin/dev.sh`, which owns the operator surface: the shell script
is the contract and the Python is the work, the same split
`bin/postgres-bootstrap.sh` and `bin/agent.sh` have.

**What this does that the contract suite's fixtures do not.** Six test modules
each stand a cluster up; only one applies the product's own bootstrap and
applies as the migration user, and none writes either ledger. This applies the
deploy's own statements in the deploy's own order, records `schema_migrations`
and `migration_ledger` the way a deployment carries them, and registers one
development subject — so what a developer meets locally is what a deploy
produces, not an approximation of it (ADR 0203, D1158).

**The decisions are not here.** `agentic_postgres.dev_environment` is pure:
which arguments `docker run` gets, which statements are issued, what `status`
concludes. This file is the part that needs a daemon — running containers,
piping SQL, reading exit codes — which is the part that cannot be tested
without one. A reader looking for *why* something is the way it is should read
the module; a reader looking for *what runs* is in the right place.

**No root, anywhere.** `docker` runs as the invoking user, nothing is written
outside the checkout, and nothing here reads `/var/lib/agentic-postgres` or
`/etc/agentic-postgres`. An environment is a thing a developer owns.

Exit codes (runbook §2 convention):
  0  success
  2  invalid operator input, or an environment that is already up
  3  a missing local prerequisite, or state this user cannot read
  4  the project has not been rendered, or has no environment
  5  a migration, a statement or a seed that did not apply
  9  the daemon or the cluster could not be reached
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import (
    REPO_ROOT,
    bootstrap_statements,
    config,
    deployed_output,
    dev_environment,
    migrations,
    naming,
)

READY_ROUNDS = 2
READY_ATTEMPTS = 90


def fail(code: int, message: str) -> None:
    print(f"dev: {message}", file=sys.stderr)
    raise SystemExit(code)


def docker(*arguments: str, stdin: str | None = None, timeout: int = 300):
    """Every `docker` call this command makes. Never `sudo`, never a shell."""
    return subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        input=stdin,
        timeout=timeout,
        check=False,
    )


def require_daemon() -> None:
    probe = docker("version", "--format", "{{.Server.Version}}", timeout=30)
    if probe.returncode != 0:
        fail(
            dev_environment.EXIT_UNREACHABLE,
            f"the docker daemon could not be reached: {probe.stderr.strip()[:200] or 'no answer'}",
        )


# ---------------------------------------------------------------------------
# The project, and its rendered document
# ---------------------------------------------------------------------------


def project_key_of(project_path: Path) -> str:
    """The key this manifest derives, through `naming` and nothing else.

    ADR 0002: one authority for a derived identity. A key computed here would
    be a second derivation, and D592/D598 are what a second derivation costs.

    `slug` and not `name`, which is what every other caller passes
    (`deploy-project.py:1820`, `materialize-secrets.py:325`, `db.sh:130`). The
    first version of this read `name`, which the manifest does not have, and
    died with `KeyError` on its first real invocation -- the argument for
    calling the shared deriver is also an argument for passing it what the
    other callers pass.
    """
    if not project_path.is_file():
        fail(dev_environment.EXIT_INPUT, f"project manifest not found: {project_path}")
    try:
        manifest = config.load_project_manifest(project_path)
    except config.ManifestError as error:
        fail(dev_environment.EXIT_CONTRACT, f"{project_path} did not load: {error}")
    project = manifest["project"]
    return naming.project_key(project["slug"], project["environment"])


def rendered_document(key: str, project_path: Path, capabilities: str) -> tuple[Path, dict]:
    """The rendered document, or which of the three failures this is (ADR 0199).

    **This command renders nothing.** One renderer, one resolver: an environment
    is a consumer of the render, not a second one (D1173). An unrendered project
    is refused with the command that renders it, spelled out with this
    invocation's own arguments rather than as a general instruction.
    """
    try:
        return deployed_output.read_rendered_document(key, runtime=False)
    except deployed_output.RenderedDocumentAbsent:
        fail(
            dev_environment.EXIT_NOT_RENDERED,
            f"{key} has not been rendered in this checkout. Render it first:\n"
            f"  ./deploy.sh --project {project_path} --capabilities {capabilities} "
            "--render-only",
        )
    except deployed_output.RenderedDocumentUnreadable as error:
        fail(dev_environment.EXIT_PREREQUISITE, str(error))
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# Talking to the cluster
# ---------------------------------------------------------------------------


def as_superuser(container: str, database: str | None, sql: str):
    """A statement batch as `postgres`, over the container's own socket."""
    arguments = ["exec", "-i", container, "psql", "-qtA", "-v", "ON_ERROR_STOP=1", "-U", "postgres"]
    if database:
        arguments += ["-d", database]
    return docker(*arguments, stdin=sql)


def as_migration_user(environment: dev_environment.Environment, env_file: Path, sql: str):
    """One transaction as the role dbmate connects as on a host.

    Over TCP with `--env-file`, never `-e PGPASSWORD=…`: the value would be in
    this process's argument vector, which `ps` reads (D105, D1160). The password
    is not what gets in from inside the container — the image's `pg_hba` trusts
    `127.0.0.1` there — but it IS what gets in from the published port, which is
    where `psql` connects, so the file is the mechanism in both places rather
    than two mechanisms (D1177).
    """
    return docker(
        "exec", "-i", "--env-file", str(env_file), environment.container,
        "psql", "-U", environment.roles["migration_user"], "-h", "127.0.0.1",
        "-d", environment.database, "-qtA", "-v", "ON_ERROR_STOP=1", "-1", "-f", "-",
        stdin=sql,
    )  # fmt: skip


def await_ready(container: str) -> None:
    """Two consecutive `pg_isready` answers, not one.

    The initdb server answers once and goes away; a caller that took the first
    answer would race it. The contract fixture's own loop, for the same reason.
    """
    rounds = 0
    for _ in range(READY_ATTEMPTS):
        probe = docker("exec", container, "pg_isready", "-U", "postgres", timeout=30)
        rounds = rounds + 1 if probe.returncode == 0 else 0
        if rounds >= READY_ROUNDS:
            return
        time.sleep(1)
    fail(
        dev_environment.EXIT_UNREACHABLE,
        f"{container} never became ready after {READY_ATTEMPTS}s; "
        f"`docker logs {container}` says why",
    )


#: How docker says "I looked, and there is no such thing", in either voice.
#:
#: **D1285.** This was one capitalised substring, and docker 29.5.2 writes
#: `error: no such object: <name>` in lower case -- so the match never fired,
#: every absent container came back as "docker could not be asked", and
#: `status_of` told the operator to check whether the daemon was running while
#: the daemon was answering every other call in the same process. ADR 0195's
#: class inverted: the reader HAD the answer and reported that it had not.
#:
#: Matched case-insensitively, and on both spellings, because this wording is
#: an upstream message rather than a contract -- `inspect` says *object* and
#: the typed verbs say *container*, and neither is promised to hold still. The
#: exit code cannot stand in for it: `inspect` exits 1 for an absent object and
#: for an unreachable daemon alike, which is the whole reason this reads stderr.
ABSENT_PHRASES = ("no such object", "no such container")


def container_state(container: str) -> str | None:
    """`docker inspect`'s word for this container, or `None` if it cannot say.

    Three outcomes, two of them returned here (ADR 0195): the container's own
    status, `"absent"` when docker says there is no such thing, and `None` when
    docker could not be asked at all. The caller renders the third differently
    from the second, and an operator acts differently on each -- `apg dev up`
    against an absent container, and a daemon to start against the other.
    """
    probe = docker("inspect", "-f", "{{.State.Status}}", container, timeout=30)
    if probe.returncode != 0:
        stderr = probe.stderr.lower()
        return "absent" if any(phrase in stderr for phrase in ABSENT_PHRASES) else None
    return probe.stdout.strip()


def applied_count(environment: dev_environment.Environment) -> int | None:
    probe = as_superuser(
        environment.container,
        environment.database,
        "SELECT count(*)::text FROM app_private.schema_migrations;",
    )
    if probe.returncode != 0:
        return None
    try:
        return int(probe.stdout.strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# up
# ---------------------------------------------------------------------------


def write_environment_files(directory: Path, database: str) -> tuple[Path, Path, Path, str, str]:
    """The three env files, 0600, in a 0700 directory.

    The passwords are generated per environment and exist only for a container
    `down` destroys. *No production secret* is meant literally and separately:
    no repository key, no cipher pass, no provider token, no deployed document
    from a host ever reaches this directory (ADR 0203 §5).
    """
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(dev_environment.STATE_DIR_MODE)

    superuser_password = dev_environment.generated_password()
    migration_password = dev_environment.generated_password()
    runtime_password = dev_environment.generated_password()

    files = {
        dev_environment.SUPERUSER_ENV: dev_environment.superuser_env_content(
            database, superuser_password
        ),
        dev_environment.MIGRATION_USER_ENV: dev_environment.password_env_content(
            migration_password
        ),
        dev_environment.APP_RUNTIME_ENV: dev_environment.password_env_content(runtime_password),
    }
    written = {}
    for name, content in files.items():
        path = directory / name
        path.write_text(content, encoding="utf-8")
        path.chmod(dev_environment.STATE_FILE_MODE)
        written[name] = path

    return (
        written[dev_environment.SUPERUSER_ENV],
        written[dev_environment.MIGRATION_USER_ENV],
        written[dev_environment.APP_RUNTIME_ENV],
        migration_password,
        runtime_password,
    )


def up(arguments: argparse.Namespace) -> int:
    project_path = Path(arguments.project)
    key = project_key_of(project_path)
    rendered_dir, document = rendered_document(key, project_path, arguments.capabilities)
    require_daemon()

    container = dev_environment.container_name(key)
    directory = dev_environment.state_dir(key)

    # Three outcomes on the existing state, not two (ADR 0195). Already up is
    # an input error and says what to run; a state whose container is gone is
    # cleaned up and reported, because a developer who deleted a container by
    # hand should not have to know that leaves a file behind.
    try:
        existing = dev_environment.read_state(key)
    except dev_environment.StateAbsent:
        existing = None
    except dev_environment.StateUnreadable as error:
        fail(dev_environment.EXIT_PREREQUISITE, str(error))
    except dev_environment.DevEnvironmentError as error:
        fail(dev_environment.EXIT_CONTRACT, str(error))

    if existing is not None:
        if container_state(existing.container) == "running":
            fail(
                dev_environment.EXIT_INPUT,
                f"{existing.container} is already up (since {existing.started_at}); "
                "`apg dev reset` rebuilds it, `apg dev down` removes it",
            )
        print(f"dev: stale state from {existing.started_at}; removing it")
        remove(key, quiet=True)

    database = document["database"]["name"]
    roles = document["database"]["roles"]
    superuser_env, migration_env, _runtime_env, migration_password, runtime_password = (
        write_environment_files(directory, database)
    )
    image = dev_environment.locked_image()

    # `run_arguments` is the WHOLE argument list, `run` included -- so that one
    # test can read everything this command tells docker, rather than reading a
    # tail and trusting the verb in front of it.
    started = docker(*dev_environment.run_arguments(container, image, superuser_env))
    if started.returncode != 0:
        fail(
            dev_environment.EXIT_UNREACHABLE,
            f"the cluster did not start: {started.stderr.strip()[:200]}",
        )
    print(f"dev: {container} started on {image.split('@')[0]}")
    await_ready(container)

    port_probe = docker("port", container, "5432", timeout=30)
    port = None
    if port_probe.returncode == 0 and ":" in port_probe.stdout:
        port = int(port_probe.stdout.splitlines()[0].rsplit(":", 1)[1])

    environment = dev_environment.Environment(
        project_key=key,
        container=container,
        database=database,
        roles=dict(roles),
        port=port,
        subject_id=None,
        image=image,
        release_commit=str(document.get("source_commit") or ""),
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        rendered_dir=str(rendered_dir.parent),
    )

    # The roles and the owner membership, then the extension home: the pre-state
    # the cluster needs before the bootstrap can grant anything on it.
    pre_state = dev_environment.role_statements(document) + dev_environment.owner_grant_statements(
        document
    )
    result = as_superuser(container, database, "\n".join(pre_state))
    if result.returncode != 0:
        fail(dev_environment.EXIT_CONTRACT, f"the roles could not be created: {result.stderr}")
    result = as_superuser(
        container, database, dev_environment.extensions_schema_statement(document)
    )
    if result.returncode != 0:
        fail(dev_environment.EXIT_CONTRACT, f"the extensions schema: {result.stderr}")

    # **The bootstrap FIRST, then the migrations** — the deploy's order, read
    # from `bin/deploy-project.py` step 6 and measured in rig 22b: 32 of 32 in
    # this order, 0 of 32 in the contract fixture's, because the migration user
    # cannot write its own `schema_migrations` row until the bootstrap has
    # granted it `app_private`.
    statements = bootstrap_statements.build_statements(document, str(uuid.uuid4()))
    result = as_superuser(container, database, "\n".join(statements))
    if result.returncode != 0:
        fail(
            dev_environment.EXIT_CONTRACT,
            f"the bootstrap statements did not apply: {result.stderr.strip()[:400]}",
        )
    result = as_superuser(
        container,
        database,
        "\n".join(
            dev_environment.activation_statements(document, migration_password, runtime_password)
        ),
    )
    if result.returncode != 0:
        fail(dev_environment.EXIT_CONTRACT, f"the roles were not activated: {result.stderr}")
    print(f"dev: bootstrap applied, {len(dev_environment.ACTIVATED_ROLES)} roles activated")

    try:
        planned = dev_environment.planned_migrations(rendered_dir.parent)
    except migrations.MigrationError as error:
        fail(dev_environment.EXIT_CONTRACT, str(error))

    applied: list[str] = []
    for entry in planned:
        body = dev_environment.migration_transaction(
            rendered_dir.parent / "migrations" / entry["file"], entry["version"]
        )
        result = as_migration_user(environment, migration_env, body)
        if result.returncode != 0:
            fail(
                dev_environment.EXIT_CONTRACT,
                f"{entry['name']} cannot be applied by {roles['migration_user']}, which is "
                f"the role dbmate connects as on a host.\n{result.stderr.strip()[-600:]}\n"
                f"(applied before this: {applied})",
            )
        applied.append(entry["name"])
    print(f"dev: {len(applied)} migrations applied as {roles['migration_user']}")

    result = as_superuser(
        container,
        database,
        migrations.ledger_insert_statement(document, rendered_dir.parent, REPO_ROOT),
    )
    if result.returncode != 0:
        fail(dev_environment.EXIT_CONTRACT, f"the ledger was not recorded: {result.stderr}")

    vocabulary = dev_environment.subject_vocabulary(document)
    result = as_superuser(
        container, database, dev_environment.subject_statement(document, vocabulary)
    )
    if result.returncode != 0:
        fail(dev_environment.EXIT_CONTRACT, f"the development subject: {result.stderr}")
    subject = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else None

    environment = dev_environment.Environment(
        **{**{f: getattr(environment, f) for f in environment.__dataclass_fields__},
           "subject_id": subject}
    )  # fmt: skip
    dev_environment.write_state(environment)
    dev_environment.write_applied_seeds(key, [])

    print()
    print(f"  container   {container}")
    print(f"  database    {database}  on 127.0.0.1:{port}")
    print(f"  migrations  {len(applied)}, ledger recorded")
    print(f"  subject     {subject}  ({len(vocabulary)} scopes)")
    print(f"  roles       {roles['migration_user']}, {roles['app_runtime']}")
    print(f"  passwords   in {directory} (0600); nothing here prints one")
    return 0


# ---------------------------------------------------------------------------
# status, down, reset
# ---------------------------------------------------------------------------


def status(arguments: argparse.Namespace) -> int:
    key = project_key_of(Path(arguments.project))
    try:
        environment = dev_environment.read_state(key)
    except dev_environment.StateAbsent:
        verdict, sentence = dev_environment.status_of(None, None, None, 0)
        print(f"dev: {sentence}")
        return dev_environment.EXIT_NOT_RENDERED
    except dev_environment.StateUnreadable as error:
        fail(dev_environment.EXIT_PREREQUISITE, str(error))
    except dev_environment.DevEnvironmentError as error:
        fail(dev_environment.EXIT_CONTRACT, str(error))

    state = container_state(environment.container)
    count = applied_count(environment) if state == "running" else None
    try:
        planned = len(dev_environment.planned_migrations(Path(environment.rendered_dir)))
    except (migrations.MigrationError, OSError):
        planned = -1

    verdict, sentence = dev_environment.status_of(environment, state, count, planned)
    print(f"dev: {sentence}")
    return {
        dev_environment.RUNNING: 0,
        dev_environment.ABSENT: dev_environment.EXIT_NOT_RENDERED,
        dev_environment.STOPPED: dev_environment.EXIT_CONTRACT,
        dev_environment.UNKNOWN: dev_environment.EXIT_PREREQUISITE,
    }[verdict]


def remove(key: str, *, quiet: bool = False) -> None:
    """The container, its anonymous volume and the state directory.

    `-v`, because without it the volume the image declares at
    `/var/lib/postgresql` outlives the container — measured in rig 22a, where
    `rm -f` left the count unchanged and `rm -f -v` dropped it by one.
    """
    container = dev_environment.container_name(key)
    removed = docker("rm", "-f", "-v", container, timeout=90)
    if removed.returncode == 0 and not quiet:
        print(f"dev: removed container {container} and its volume")

    directory = dev_environment.state_dir(key)
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
        if not quiet:
            print(f"dev: removed {directory}")


def down(arguments: argparse.Namespace) -> int:
    """Idempotent, and it says which of the two happened.

    Exit 0 either way: `down` on nothing is a success, because the state a
    caller asked for is the state they get. What it must not do is claim to
    have removed something it did not.
    """
    key = project_key_of(Path(arguments.project))
    container = dev_environment.container_name(key)
    directory = dev_environment.state_dir(key)
    had_container = container_state(container) not in (None, "absent")
    had_state = directory.exists()

    remove(key, quiet=True)

    if had_container or had_state:
        parts = []
        if had_container:
            parts.append(f"container {container} and its volume")
        if had_state:
            parts.append(str(directory))
        print(f"dev: removed {' and '.join(parts)}")
    else:
        print(f"dev: nothing to remove for {key}")
    return 0


def reset(arguments: argparse.Namespace) -> int:
    """`down`, then `up`. The same two functions, in that order, and no third path.

    A reset that kept the container would carry role passwords, settings and
    the superuser's state across resets, and would be a second bring-up path
    with defects of its own. Two paths to one state is the defect class this
    project keeps producing (ADR 0203 §8, D1174).
    """
    down(arguments)
    return up(arguments)


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------


def running_environment(key: str) -> dev_environment.Environment:
    """The environment, or the reason this verb cannot act on it.

    Three outcomes, and the exits are `status`'s: a verb that reported "no
    environment" about one this user merely cannot read would send a developer
    to create a second (D1060, ADR 0195).
    """
    try:
        environment = dev_environment.read_state(key)
    except dev_environment.StateAbsent as error:
        fail(dev_environment.EXIT_NOT_RENDERED, f"{error}")
    except dev_environment.StateUnreadable as error:
        fail(dev_environment.EXIT_PREREQUISITE, str(error))
    except dev_environment.DevEnvironmentError as error:
        fail(dev_environment.EXIT_CONTRACT, str(error))

    if container_state(environment.container) != "running":
        fail(
            dev_environment.EXIT_CONTRACT,
            f"{environment.container} is not running; `apg dev up` or `apg dev reset` builds it",
        )
    return environment


def project_set_root(document: dict, key: str) -> str:
    """The project root the rendered document names, or a refusal.

    Read from the DOCUMENT and not the manifest, for ADR 0002's reason: the
    document is the one authority for what this project applies, and a second
    reader of the manifest would be a second derivation path.
    """
    block = (document.get("migrations") or {}).get("project_set")
    if not block:
        fail(
            dev_environment.EXIT_PREREQUISITE,
            f"{key} declares no migrations.set, so it has no seeds directory. A seed "
            "lives beside a project's own migration set, under projects/<slug>/seeds/ "
            "(ADR 0198, ADR 0203)",
        )
    return str(block["root"])


def seed(arguments: argparse.Namespace) -> int:
    project_path = Path(arguments.project)
    key = project_key_of(project_path)
    _rendered, document = rendered_document(key, project_path, arguments.capabilities)
    require_daemon()
    environment = running_environment(key)

    root = Path(project_set_root(document, key))
    try:
        manifest = dev_environment.load_seeds_manifest(root)
        entry = dev_environment.seed_entry(manifest, arguments.name)
    except dev_environment.DevEnvironmentError as error:
        fail(dev_environment.EXIT_INPUT, str(error))

    # Applied once. A second application would write the rows twice, and the
    # cluster a developer then reasons about is one no sequence of commands
    # produces -- `reset` is the way back, and it is one line.
    applied = dev_environment.read_applied_seeds(key)
    if arguments.name in applied:
        fail(
            dev_environment.EXIT_INPUT,
            f"{arguments.name!r} has already been applied to this environment; "
            "`apg dev reset` rebuilds it and applies nothing",
        )

    try:
        text = dev_environment.verify_seed(root, entry)
        dev_environment.lint_seed(text)
        set_manifest = migrations.project_set_from(document).load_manifest()
        rendered = dev_environment.render_seed(text, set_manifest, document)
    except (dev_environment.DevEnvironmentError, migrations.MigrationError) as error:
        fail(dev_environment.EXIT_CONTRACT, str(error))

    if not environment.subject_id:
        fail(
            dev_environment.EXIT_CONTRACT,
            "this environment records no development subject, so a seed's rows would "
            "belong to nobody and every write would raise AP401; `apg dev reset`",
        )

    result = as_migration_user(
        environment,
        dev_environment.state_dir(key) / dev_environment.MIGRATION_USER_ENV,
        dev_environment.seed_transaction(rendered, environment.subject_id),
    )
    if result.returncode != 0:
        fail(
            dev_environment.EXIT_CONTRACT,
            f"{arguments.name} did not apply:\n{result.stderr.strip()[-600:]}",
        )

    dev_environment.write_applied_seeds(key, [*applied, arguments.name])
    print(f"dev: applied seed {arguments.name} as {environment.roles['migration_user']}")
    print(f"     {entry['description']}")
    print(f"     rows belong to subject {environment.subject_id}")
    return 0


# ---------------------------------------------------------------------------
# psql
# ---------------------------------------------------------------------------


def psql(arguments: argparse.Namespace) -> int:
    """An interactive session, as the developer's own role, with the subject set.

    `os.execvp`, not a subprocess: the exit code a developer sees is `psql`'s
    own, and a wrapper that captured it would be a second thing to interpret.
    Everything before the exec is the refusal surface.
    """
    key = project_key_of(Path(arguments.project))
    require_daemon()
    environment = running_environment(key)

    try:
        argv = dev_environment.psql_arguments(
            environment, arguments.role, dev_environment.state_dir(key), arguments.rest
        )
    except dev_environment.DevEnvironmentError as error:
        fail(dev_environment.EXIT_INPUT, str(error))

    print(
        f"dev: {environment.container} as "
        f"{environment.roles[dev_environment.PSQL_ROLES[arguments.role]]}, "
        f"subject {environment.subject_id}",
        file=sys.stderr,
    )
    os.execvp("docker", ["docker", *argv])  # noqa: S606 -- a fixed argv, no shell
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bin/dev.sh", add_help=False)
    parser.add_argument("verb", choices=("up", "status", "down", "reset", "seed", "psql"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--capabilities", default="capabilities.example.yaml")
    parser.add_argument("--name", default=None)
    parser.add_argument("--as", dest="role", default="app-runtime")
    parser.add_argument("rest", nargs="*")
    arguments = parser.parse_args(argv)

    if arguments.verb == "seed" and not arguments.name:
        parser.error("seed requires a seed NAME")

    verbs = {
        "up": up,
        "status": status,
        "down": down,
        "reset": reset,
        "seed": seed,
        "psql": psql,
    }
    try:
        return verbs[arguments.verb](arguments)
    except dev_environment.StateUnreadable as error:
        fail(dev_environment.EXIT_PREREQUISITE, str(error))
    except dev_environment.DevEnvironmentError as error:
        fail(dev_environment.EXIT_CONTRACT, str(error))
    raise AssertionError("unreachable")


if __name__ == "__main__":
    sys.exit(main())

"""`apg dev`'s decisions, with no daemon behind them. ADR 0203.

**What the local environment is.** One container, on the locked PostgreSQL
image by digest, carrying this release's schema, this project's migration set
and one development subject. No PostgREST, no auth service, no JWT: a token
alone reaches nothing a developer wants -- the issuer names a role, the auth
service names a subject, and every owner-scoped policy reads `app.user_id`
(D1157), so a REST loop is three containers and the production key flow. What a
developer gets instead is the database, reached with `apg dev psql` and seeded
with `apg dev seed`.

**Everything here is a function of the rendered document.** No `subprocess`, no
`docker`, no clock it reads itself -- the daemon work is `bin/dev.py`'s, and
keeping the decisions here is what lets every one of them be tested without a
daemon. It is also what stops a second implementation from appearing: the
statements this module plans are `bootstrap_statements.build_statements` and
`migrations.ledger_insert_statement`, the same two the deploy issues, because
F-005 is what a hand-written second copy costs.

**Three rules that are not style.**

*The state is dot-prefixed.* `.generated/.dev/<key>/` -- `evidence.load_rendered`
skips dot-prefixed directories (`evidence.py:206`) and `bin/session-01-check.sh`
checks only the directories it published, so the environment never enters the
collision count and never dirties the tree (D1173).

*No credential is ever an argument.* Two generated passwords live in mode-0600
env files and reach `psql` through `docker exec --env-file`, never through
`-e NAME=VALUE`, which puts the value in the HOST's argument vector where `ps`
reads it (D105, D1160). Measured on docker 29.5.2: `--env-file` works on both
`run` and `exec`, and the password is genuinely required from anywhere but the
container's own loopback (rig 22a-3, D1177).

*The container is given nothing.* No `--network`, no `-v`, no `--mount`, no
`-c`. A correct environment still shows ONE mount -- the anonymous volume the
image declares at `/var/lib/postgresql` -- so a proof asserting *no mounts*
would be red on a correct environment and green on nothing (D1161); `down` uses
`docker rm -f -v`, because without `-v` that volume outlives the container.
"""

from __future__ import annotations

import base64
import json
import os
import pwd
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_postgres import REPO_ROOT, api_surface, migrations, scope_registry

#: Where an environment keeps what it knows about itself.
#:
#: Dot-prefixed, which is load-bearing: `evidence.load_rendered` skips a
#: dot-prefixed directory under `.generated/`, so a running environment cannot
#: turn up in an isolation collision count or in an evidence document (D1173).
STATE_ROOT = REPO_ROOT / ".generated" / ".dev"

CONTAINER_PREFIX = "apg-dev-"

#: The three files an environment writes. The two env files hold generated
#: passwords for a container `down` destroys; `state.json` holds no secret and
#: is 0600 anyway, because it sits in the same 0700 directory and a reader that
#: had to reason about which file is which would eventually reason wrong.
SUPERUSER_ENV = "superuser.env"
MIGRATION_USER_ENV = "migration-user.env"
APP_RUNTIME_ENV = "app-runtime.env"
STATE_FILE = "state.json"
SEEDS_FILE = "seeds-applied.json"

STATE_DIR_MODE = 0o700
STATE_FILE_MODE = 0o600

#: The two roles this environment activates, and no others.
#:
#: `migration_user` applies the migrations, as the deploy does. `app_runtime` is
#: what `apg dev psql` connects as: measured in rig 22b-2, it reaches `api.*`
#: and its rows are the subject's, while the `authenticated` role -- the one
#: that LOOKS like the request role -- cannot open a connection at all
#: ("permission denied for database"), because PostgREST switches into it and
#: never logs in (D1179).
ACTIVATED_ROLES = ("migration_user", "app_runtime")

#: The development subject, and what it can do.
SUBJECT_USERNAME = "dev"
SUBJECT_DISPLAY_NAME = "Development subject"

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_NOT_RENDERED = 4
EXIT_CONTRACT = 5
EXIT_UNREACHABLE = 9

RUNNING, STOPPED, ABSENT, UNKNOWN = "running", "stopped", "absent", "unknown"


class DevEnvironmentError(Exception):
    """Anything this module refuses."""


class StateAbsent(DevEnvironmentError):
    """No environment has been created for this project."""


class StateUnreadable(DevEnvironmentError):
    """There is state and this user cannot read it.

    Distinct from `StateAbsent` for ADR 0195's reason, and for D1060's: a
    directory this user cannot traverse answers `is_file()` false exactly as a
    missing one does, and reporting *"no environment"* about an environment that
    exists sends a developer to create a second one.
    """

    def __init__(self, path: Path, owner: str) -> None:
        me = _current_user()
        super().__init__(
            f"cannot read {path}: it is owned by {owner} and this user is {me}. "
            f"`sudo chown -R {me}:{me} {path.parent}` hands it back."
        )
        self.path = path
        self.owner = owner


@dataclass(frozen=True, slots=True)
class Environment:
    """What one environment is, as the state file records it.

    `port` and `subject_id` are nullable because `up` learns them after the
    container is running, and a state written before them would have to be
    rewritten -- but a state file that exists with nulls in it is also what a
    half-finished `up` leaves, which `status` reports rather than guesses at.
    """

    project_key: str
    container: str
    database: str
    roles: dict[str, str]
    port: int | None
    subject_id: str | None
    image: str
    release_commit: str
    started_at: str
    rendered_dir: str


def _current_user() -> str:
    try:
        return pwd.getpwuid(os.geteuid()).pw_name
    except KeyError:
        return f"uid {os.geteuid()}"


def _owner_of(path: Path) -> str:
    """The owning user of the nearest ancestor that can answer. ADR 0195."""
    for candidate in (path, *path.parents):
        try:
            return pwd.getpwuid(candidate.stat().st_uid).pw_name
        except (OSError, KeyError):
            continue
    return "unknown"


# ---------------------------------------------------------------------------
# Where things live
# ---------------------------------------------------------------------------


def container_name(project_key: str) -> str:
    """One container per project key, named so `docker ps` reads as English.

    Derived rather than recorded, so the name a `down` removes is the name an
    `up` created even when the state file is gone -- which is the case `down`
    exists to clean up.
    """
    return f"{CONTAINER_PREFIX}{project_key}"


def state_dir(project_key: str, repo_root: Path = REPO_ROOT) -> Path:
    return repo_root / ".generated" / ".dev" / project_key


def locked_image(lock: Path | None = None) -> str:
    """`POSTGRES_IMAGE` from `versions.env`, digest and all.

    The same parse `capacity.locked_digests` does, over the same file: the image
    is named BY DIGEST, so an environment and the contract suite and a
    deployment are all on one set of bytes (ADR 0004).
    """
    text = (lock or (REPO_ROOT / "versions.env")).read_text(encoding="utf-8")
    for line in text.splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "POSTGRES_IMAGE" and not name.lstrip().startswith("#"):
            return value.strip()
    raise DevEnvironmentError(f"no POSTGRES_IMAGE in {lock or 'versions.env'}")


# ---------------------------------------------------------------------------
# The state file: three outcomes, never two
# ---------------------------------------------------------------------------


def read_state(project_key: str, repo_root: Path = REPO_ROOT) -> Environment:
    """The recorded environment, or WHICH failure this is.

    Absent, unreadable, or parsed -- ADR 0195, and D1060 is the live cost of
    folding the first two together.
    """
    directory = state_dir(project_key, repo_root)
    path = directory / STATE_FILE
    try:
        if not path.is_file():
            raise StateAbsent(
                f"no development environment for {project_key!r}; `apg dev up` creates one"
            )
        raw = path.read_text(encoding="utf-8")
    except PermissionError as error:
        raise StateUnreadable(path, _owner_of(path)) from error

    try:
        recorded = json.loads(raw)
    except ValueError as error:
        raise DevEnvironmentError(
            f"{path} is not readable JSON ({error}); `apg dev down` removes it"
        ) from error

    known = {field for field in Environment.__dataclass_fields__}
    missing = sorted(known - set(recorded))
    if missing:
        raise DevEnvironmentError(
            f"{path} was written by a different version of this command and is missing "
            f"{missing}; `apg dev down` removes it and `up` writes a current one"
        )
    return Environment(**{field: recorded[field] for field in known})


def write_state(environment: Environment, repo_root: Path = REPO_ROOT) -> Path:
    """The state file, 0600, in a 0700 directory, both created if absent."""
    directory = state_dir(environment.project_key, repo_root)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, STATE_DIR_MODE)
    path = directory / STATE_FILE
    path.write_text(json.dumps(asdict(environment), indent=2, sort_keys=True) + "\n", "utf-8")
    os.chmod(path, STATE_FILE_MODE)
    return path


def read_applied_seeds(project_key: str, repo_root: Path = REPO_ROOT) -> list[str]:
    path = state_dir(project_key, repo_root) / SEEDS_FILE
    try:
        if not path.is_file():
            return []
        return list(json.loads(path.read_text(encoding="utf-8")))
    except PermissionError as error:
        raise StateUnreadable(path, _owner_of(path)) from error
    except ValueError:
        return []


def write_applied_seeds(project_key: str, names: list[str], repo_root: Path = REPO_ROOT) -> Path:
    path = state_dir(project_key, repo_root) / SEEDS_FILE
    path.write_text(json.dumps(sorted(set(names)), indent=2) + "\n", encoding="utf-8")
    os.chmod(path, STATE_FILE_MODE)
    return path


# ---------------------------------------------------------------------------
# What `docker` is told
# ---------------------------------------------------------------------------


def run_arguments(container: str, image: str, superuser_env: Path) -> list[str]:
    """The whole `docker run`. Nothing is in this list by accident.

    No `--network`, so the container joins the default bridge and nothing else.
    No `-v` and no `--mount`, so its only mount is the anonymous volume the
    image declares. No `-c`, so `wal_level` is the image's `replica` rather
    than something this command chose (D1175). One `-p`, bound to
    `127.0.0.1` with an ephemeral port -- measured in rig 22a: this records
    `HostIp 127.0.0.1`, while `-p 0:5432` records `0.0.0.0` AND `::`.

    The superuser password arrives through `--env-file` and never as `-e
    NAME=VALUE`, which would put it in this process's own argument vector.
    """
    return [
        "run",
        "-d",
        "--name",
        container,
        "--env-file",
        str(superuser_env),
        "-p",
        "127.0.0.1:0:5432",
        image,
    ]


def superuser_env_content(database: str, password: str) -> str:
    """The image's own two variables. `POSTGRES_DB` so `initdb` makes the
    database this project's document names, rather than `up` creating it after."""
    return f"POSTGRES_PASSWORD={password}\nPOSTGRES_DB={database}\n"


def password_env_content(password: str) -> str:
    return f"PGPASSWORD={password}\n"


def generated_password() -> str:
    return secrets.token_hex(24)


# ---------------------------------------------------------------------------
# The statements
# ---------------------------------------------------------------------------


def role_statements(document: dict[str, Any]) -> list[str]:
    """Create every role the document names, NOLOGIN, before anything else.

    The bootstrap creates them too and is idempotent, but the database has to
    exist first and `CREATE DATABASE ... OWNER` needs the owner to exist -- so
    this is the short pre-state the contract fixture has always built, in the
    fixture's own order.
    """
    roles = document["database"]["roles"]
    return [
        f"CREATE ROLE {migrations.quote_identifier(role)} NOLOGIN;"
        for role in sorted(set(roles.values()))
    ]


def owner_grant_statements(document: dict[str, Any]) -> list[str]:
    """The membership that makes `SET LOCAL ROLE` the only route to the owner.

    `INHERIT FALSE` is what makes the migration-user path real: with `INHERIT
    TRUE` the migration user would hold the owner's rights merely by connecting,
    and D285's defect -- a `RESET ROLE` above a statement needing ownership --
    would be invisible here exactly as it was invisible to four sessions of
    superuser rigs (ADR 0026, D266).
    """
    roles = document["database"]["roles"]
    owner = migrations.quote_identifier(roles["object_owner"])
    user = migrations.quote_identifier(roles["migration_user"])
    return [f"GRANT {owner} TO {user} WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;"]


def extensions_schema_statement(document: dict[str, Any]) -> str:
    """`extensions`, owned by the object owner, before the first migration.

    The deploy's `postgres-bootstrap` establishes this; on a fresh cluster the
    schema has to exist before a migration references it, and the owner has to
    own it or a migration creating an extension there fails as the owner.
    """
    owner = migrations.quote_identifier(document["database"]["roles"]["object_owner"])
    return f"CREATE SCHEMA IF NOT EXISTS extensions AUTHORIZATION {owner};"


def activation_statements(
    document: dict[str, Any], migration_password: str, runtime_password: str
) -> list[str]:
    """`LOGIN PASSWORD` for exactly the two roles this environment activates.

    Exactly two, and the control that matters is what is NOT here: `object_owner`
    stays NOLOGIN, so the owner's authority is reachable only through `SET LOCAL
    ROLE` from the migration user, which is the mechanism every migration in
    this release is written against (ADR 0026).

    Both passwords are quoted as literals through `migrations.quote_literal`,
    the same function the renderer uses, so a value that could change the
    statement's shape cannot reach it.
    """
    roles = document["database"]["roles"]
    passwords = {"migration_user": migration_password, "app_runtime": runtime_password}
    return [
        f"ALTER ROLE {migrations.quote_identifier(roles[role])} LOGIN PASSWORD "
        f"{migrations.quote_literal(passwords[role])};"
        for role in ACTIVATED_ROLES
    ]


def placeholder_verifier() -> str:
    """A well-formed argon2id encoding of random bytes, with no password behind it.

    `app_private.user_credentials` carries `CHECK (password_hash LIKE
    '$argon2id$%')`, measured refusing `'x'` in rig 22b. The environment has no
    login path -- no auth service, no issuer -- so there is no password to hash,
    and an operator command may import only the standard library,
    `agentic_postgres` and `yaml` (D292, ADR 0093), so there is no `argon2` to
    hash with either.

    A verifier for no password is therefore the honest row, and it is written
    here rather than smuggled into a helper so that a reader meets the decision
    (ADR 0203 §6). The encoding has no padding, which is argon2's own.
    """
    salt = base64.b64encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")
    digest = base64.b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    return f"$argon2id$v=19$m=65536,t=3,p=4${salt}${digest}"


def subject_vocabulary(document: dict[str, Any], repo_root: Path = REPO_ROOT) -> tuple[str, ...]:
    """The scopes the development subject holds: the merged surface's whole data class.

    Derived, never enumerated (ADR 0200): `scope_registry.vocabulary` over the
    release surface merged with the project's, which is what the issuer's
    ceiling would admit on this deployment. A project with no set has no project
    surface and uses the release's alone -- the same rule
    `bin/agent.py::merged_surface_for` follows, read from the DOCUMENT here
    because the document is the one authority for what this project applies
    (ADR 0002).
    """
    release = api_surface.load_surface()
    block = (document.get("migrations") or {}).get("project_set")
    project = None
    if block:
        surface_path = api_surface.project_contract_path(repo_root / block["root"])
        if surface_path.is_file():
            project = api_surface.load_project_surface(surface_path)
    merged = api_surface.merged_surface(release, project)
    return tuple(sorted(scope_registry.vocabulary(merged)))


def subject_statement(document: dict[str, Any], vocabulary: tuple[str, ...]) -> str:
    """One subject, through the product's own `app_private.auth_create_user`.

    `role_name` is the document's **`authenticated`** role in full, which is
    what the auth service's `_role_name` stores. Nothing in the database refuses
    a role name this deployment does not derive -- rig 22b-2 created a subject
    with `'nobody'` and got a uuid back -- so deriving it correctly is this
    command's job and is asserted by this command's own proof (D1176).
    """
    roles = document["database"]["roles"]
    scopes = ", ".join(migrations.quote_literal(scope) for scope in vocabulary)
    return (
        "SELECT app_private.auth_create_user("
        f"{migrations.quote_literal(SUBJECT_USERNAME)}, "
        f"{migrations.quote_literal(SUBJECT_DISPLAY_NAME)}, "
        f"{migrations.quote_literal(roles['authenticated'])}, "
        f"ARRAY[{scopes}]::text[], "
        f"{migrations.quote_literal(placeholder_verifier())});"
    )


# ---------------------------------------------------------------------------
# The migrations
# ---------------------------------------------------------------------------


def planned_migrations(rendered_dir: Path) -> list[dict[str, Any]]:
    """The rendered payloads, verified against their manifest, in manifest order.

    `migrations.verify_rendered_directory` -- the same check `bin/migrate.py`
    runs before dbmate reads the directory. Not a second reading of the same
    files: a dev cluster built from a second verification would be a second
    verification nobody compares (ADR 0028, ADR 0203).
    """
    return migrations.verify_rendered_directory(rendered_dir)


def transaction_body(payload: str, version: str) -> str:
    """One migration payload's `up` half plus its own `schema_migrations` row.

    **The row goes inside the migration's own transaction**, which is where
    dbmate puts it -- so a migration that fails leaves no row, and a dev
    cluster's `schema_migrations` has production's shape and `migrate.sh status`
    can read it the same way.

    That is also why the bootstrap has to run FIRST. Rig 22b measured it: with
    the bootstrap applied at the contract fixture's position (after the first
    migration), every migration failed at this INSERT with *permission denied
    for schema app_private*, because the migration user reaches that schema only
    after the bootstrap grants it. 32 of 32 in the deploy's order, 0 of 32 in
    the fixture's.

    Takes the payload rather than a path, so that the one caller with a rendered
    FILE and the one with a rendered STRING send the same bytes. The contract
    fixture renders from templates and `apg dev` reads the rendered directory;
    what they must agree on is this transformation, and they do because there is
    one of it.
    """
    body = payload.split("-- migrate:down", 1)[0].replace("-- migrate:up", "", 1)
    return (
        body.rstrip()
        + "\n\nINSERT INTO app_private.schema_migrations (version) VALUES "
        + f"({migrations.quote_literal(version)});\n"
    )


def migration_transaction(path: Path, version: str) -> str:
    """`transaction_body` over a rendered file. What `apg dev up` applies."""
    return transaction_body(path.read_text(encoding="utf-8"), version)


# ---------------------------------------------------------------------------
# What `status` says
# ---------------------------------------------------------------------------


def status_of(
    state: Environment | None,
    container_status: str | None,
    applied: int | None,
    planned: int,
) -> tuple[str, str]:
    """`(status, sentence)` -- and `unknown` is a real answer, not a failure.

    Four outcomes and not three, because "there is no environment" and "there is
    an environment and I could not ask it anything" are different facts and a
    developer acts differently on each (ADR 0195). `container_status` is
    `docker inspect`'s word, or `None` when docker could not say.
    """
    if state is None:
        return ABSENT, "no development environment; `apg dev up` creates one"
    if container_status is None:
        return UNKNOWN, (
            f"state records container {state.container}, and docker could not be asked "
            "about it; is the daemon running?"
        )
    if container_status != "running":
        return STOPPED, (
            f"{state.container} is {container_status}; `apg dev reset` rebuilds it "
            "(`down` then `up`, the same code)"
        )
    if applied is None:
        return UNKNOWN, (
            f"{state.container} is running and its cluster could not be asked how many "
            "migrations it carries"
        )
    if applied != planned:
        return STOPPED, (
            f"{state.container} is running and carries {applied} of {planned} migrations; "
            "`apg dev reset` rebuilds it"
        )
    port = state.port if state.port is not None else "an unrecorded port"
    return RUNNING, (
        f"{state.container} is running on 127.0.0.1:{port}, database {state.database}, "
        f"{applied} migrations, subject {state.subject_id}"
    )


__all__ = [
    "ABSENT",
    "ACTIVATED_ROLES",
    "APP_RUNTIME_ENV",
    "CONTAINER_PREFIX",
    "MIGRATION_USER_ENV",
    "RUNNING",
    "SEEDS_FILE",
    "STATE_DIR_MODE",
    "STATE_FILE",
    "STATE_FILE_MODE",
    "STATE_ROOT",
    "STOPPED",
    "SUBJECT_DISPLAY_NAME",
    "SUBJECT_USERNAME",
    "SUPERUSER_ENV",
    "UNKNOWN",
    "DevEnvironmentError",
    "Environment",
    "StateAbsent",
    "StateUnreadable",
    "activation_statements",
    "container_name",
    "extensions_schema_statement",
    "generated_password",
    "locked_image",
    "migration_transaction",
    "owner_grant_statements",
    "password_env_content",
    "placeholder_verifier",
    "planned_migrations",
    "read_applied_seeds",
    "read_state",
    "role_statements",
    "run_arguments",
    "state_dir",
    "status_of",
    "subject_statement",
    "subject_vocabulary",
    "superuser_env_content",
    "write_applied_seeds",
    "write_state",
]

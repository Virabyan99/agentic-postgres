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
import re
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    migrations,
    scope_registry,
    sql_surface,
)

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


# ---------------------------------------------------------------------------
# The seed door (D1170, ADR 0203 §7)
# ---------------------------------------------------------------------------

#: Where a project keeps its seeds, beside its migration set.
SEEDS_DIRECTORY = "seeds"
SEEDS_MANIFEST = "manifest.json"

#: A seed's name. Lowercase, hyphenated, bounded -- and, decisively, a name that
#: cannot be a path: no separator, no dot, no `..`. `bin/db.sh sql` takes a NAME
#: checked against an allowlist "before anything touches the filesystem, so
#: `../../etc/anything` is refused as not allowlisted rather than resolved and
#: then rejected". This is the same door and the same reason (D1170).
SEED_NAME = re.compile(r"^[a-z][a-z0-9-]{0,39}$")

#: A seed's file: a basename under the seeds directory, ending `.sql`.
SEED_FILE = re.compile(r"^[a-z][a-z0-9-]{0,39}\.sql$")

SEED_MANIFEST_SCHEMA_VERSION = 1

#: What a SEED may not do that a migration may: create anything at all.
#:
#: A seed writes ROWS. Everything a schema change needs -- a table, a view, a
#: function, a grant -- belongs in the project's migration set, where it is
#: frozen under a lock, version-ordered, and applied by a deploy. A seed that
#: could create an object would be an unversioned migration that runs on a
#: developer's cluster and on no deployment, which is the shape of every
#: "works on my machine" schema this product exists to make impossible.
SEED_DDL = re.compile(
    r"\b(CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|COMMENT|VACUUM|ANALYZE)\b", re.IGNORECASE
)


def seeds_root(project_root: Path, repo_root: Path = REPO_ROOT) -> Path:
    """`projects/<slug>/seeds/`, from the project root the document names."""
    return repo_root / project_root / SEEDS_DIRECTORY


def load_seeds_manifest(project_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """The seed manifest, validated as the allowlist it is.

    Every refusal here is a boundary rather than a style rule, and the shapes
    are checked BEFORE any name is joined to a path: a manifest naming
    `../../etc/passwd` is refused for naming it, not for where it resolves.
    """
    path = seeds_root(project_root, repo_root) / SEEDS_MANIFEST
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DevEnvironmentError(
            f"{path} does not exist, so this project declares no seeds. A seed is a "
            f"reviewed file in {seeds_root(project_root, repo_root)} named by that manifest."
        ) from error
    except ValueError as error:
        raise DevEnvironmentError(f"{path} is not readable JSON: {error}") from error

    version = document.get("schema_version")
    if version != SEED_MANIFEST_SCHEMA_VERSION:
        raise DevEnvironmentError(
            f"{path} declares schema_version {version!r}; this release reads "
            f"{SEED_MANIFEST_SCHEMA_VERSION} and will not guess at the difference"
        )

    seeds = document.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        raise DevEnvironmentError(f"{path} declares no seeds")

    seen: set[str] = set()
    for entry in seeds:
        name = entry.get("name")
        if not isinstance(name, str) or not SEED_NAME.fullmatch(name):
            raise DevEnvironmentError(
                f"{path}: {name!r} is not a seed name. Lowercase letters, digits and "
                "hyphens, starting with a letter -- a name that cannot be a path"
            )
        if name in seen:
            raise DevEnvironmentError(f"{path}: {name!r} is declared twice")
        seen.add(name)

        file = entry.get("file")
        if not isinstance(file, str) or not SEED_FILE.fullmatch(file):
            raise DevEnvironmentError(
                f"{path}: {name!r} names file {file!r}. A basename ending .sql, inside "
                f"{SEEDS_DIRECTORY}/ -- never a path, a traversal or a dotfile"
            )

        checksum = entry.get("sha256")
        if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise DevEnvironmentError(
                f"{path}: {name!r} records sha256 {checksum!r}, which is not 64 lowercase "
                "hex characters. The digest is what makes the file reviewed rather than "
                "merely present"
            )
        if not isinstance(entry.get("description"), str) or not entry["description"].strip():
            raise DevEnvironmentError(
                f"{path}: {name!r} carries no description. A seed writes rows into a "
                "developer's cluster and the manifest is where they read what it does"
            )
    return document


def seed_entry(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    """One seed by name, or a refusal naming the ones there are.

    The name is never joined to a path on the way here. A caller that passed
    `../../etc/passwd` is told it is not a declared seed, which is the answer
    `bin/db.sh sql` gives for the same input and for the same reason.
    """
    for entry in manifest["seeds"]:
        if entry["name"] == name:
            return entry
    declared = ", ".join(sorted(entry["name"] for entry in manifest["seeds"]))
    raise DevEnvironmentError(f"{name!r} is not a declared seed. This project declares: {declared}")


def verify_seed(project_root: Path, entry: dict[str, Any], repo_root: Path = REPO_ROOT) -> str:
    """The seed's text, or a refusal because its digest moved.

    The whole digest, compared whole. A prefix comparison would accept a file
    whose first bytes are unchanged, which is every edit made to the end of a
    file -- and the end of a seed is where the rows are.
    """
    path = seeds_root(project_root, repo_root) / entry["file"]
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise DevEnvironmentError(
            f"{path} is named by the seed manifest and does not exist"
        ) from error

    actual = migrations.digest(text)
    if actual != entry["sha256"]:
        raise DevEnvironmentError(
            f"{path} does not match the digest the manifest records "
            f"({actual[:16]} != {entry['sha256'][:16]}); it was edited after it was "
            "reviewed. Re-review it and record the new digest"
        )
    return text


def lint_seed(text: str) -> None:
    """What a seed may contain. Every refusal is a boundary.

    Two rules, and the second is a seed's own. The first is the project set's
    whole table -- `migrations.FORBIDDEN_STATEMENTS`, because a seed runs
    through the same plane, as the same `migration_user`, under the same `SET
    LOCAL ROLE`, so the platform's state is no more addressable from a seed than
    from a migration. The second is that a seed **creates nothing**: it writes
    rows, and everything else belongs in the migration set where it is frozen,
    ordered and applied by a deploy.

    The role preamble is the set's, and it must come FIRST: a statement above it
    would run as the migration user, which owns nothing, and the failure would
    name a privilege rather than an ordering.
    """
    applied = sql_surface.sql_only(text)

    for pattern, description in migrations.FORBIDDEN_STATEMENTS:
        match = pattern.search(applied)
        if match is not None:
            raise DevEnvironmentError(
                f"this seed {description}: {match.group(0).strip()!r}. A seed runs as the "
                "object owner through the platform's own migration plane; the platform's "
                "state is not addressable from it"
            )

    ddl = SEED_DDL.search(applied)
    if ddl is not None:
        raise DevEnvironmentError(
            f"this seed contains {ddl.group(0).strip()!r}. A seed writes ROWS: a table, a "
            "view, a function or a grant belongs in the project's migration set, where it "
            "is frozen under a lock and applied by a deploy -- a seed that created an "
            "object would be an unversioned migration running on one developer's cluster"
        )

    roles = migrations.SET_ROLE.findall(applied)
    for statement in roles:
        if statement.strip() != migrations.PROJECT_ROLE_PREAMBLE:
            raise DevEnvironmentError(
                f"this seed sets a role other than the owner preamble: "
                f"{statement.strip()!r}. The only permitted form is "
                f"{migrations.PROJECT_ROLE_PREAMBLE!r}"
            )
    if roles:
        first = next(
            line.strip()
            for line in applied.splitlines()
            if line.strip() and not line.strip().startswith("--")
        )
        if not first.startswith(migrations.PROJECT_ROLE_PREAMBLE):
            raise DevEnvironmentError(
                f"this seed's first statement is {first[:60]!r}, not the owner preamble. "
                "A statement above it runs as the migration user, which owns nothing, and "
                "the failure names a privilege rather than an ordering"
            )


def render_seed(text: str, set_manifest: dict[str, Any], document: dict[str, Any]) -> str:
    """The seed, with the SET's declared placeholders resolved and nothing else.

    The same renderer and the same allowlist a migration gets
    (`PROJECT_PLACEHOLDER_SOURCES`), so a seed can name the request roles and
    its own database and none of the platform's other identities. An unresolved
    `{{x}}` is a hard failure, as it is everywhere else -- a capable template
    engine's failure mode is a plausible wrong answer (ADR 0028).
    """
    declared = list(set_manifest["placeholders"])
    values = migrations.resolve_placeholders(set_manifest, document, declared)
    return migrations.render(text, values)


def seed_transaction(rendered: str, subject_id: str) -> str:
    """The seed, with the development subject asserted before it runs.

    `set_config(..., true)` -- transaction-local, so the identity cannot outlive
    the transaction the seed is applied in. Without it every owner-scoped write
    raises `AP401 no request identity for this transaction` (measured in rig
    22b), because the tables' policies read `app.user_id` and nothing has set
    it. This is what makes the seeded rows the subject's, which is what makes
    them visible to `apg dev psql`.
    """
    return (
        f"SELECT set_config('app.user_id', {migrations.quote_literal(subject_id)}, true);\n"
        + rendered
    )


# ---------------------------------------------------------------------------
# psql (D1157, D1179)
# ---------------------------------------------------------------------------

#: The two roles `apg dev psql` will connect as, and what each is for.
#:
#: `app_runtime` is the default and is what a developer wants: it reaches
#: `api.*` and its rows are the subject's, which is the loop the environment
#: exists to give them. `migration_user` is for applying SQL the way a migration
#: would, reaching the owner through `SET LOCAL ROLE`.
#:
#: `authenticated` is deliberately not offered: it cannot open a connection at
#: all ("permission denied for database"), because PostgREST switches into it
#: and never logs in (D1179, rig 22b-2).
PSQL_ROLES = {"app-runtime": "app_runtime", "migration-user": "migration_user"}

PSQL_ENV_FILES = {"app_runtime": APP_RUNTIME_ENV, "migration_user": MIGRATION_USER_ENV}


def psql_arguments(
    environment: Environment,
    role_key: str,
    state_directory: Path,
    extra: list[str] | None = None,
) -> list[str]:
    """The whole `docker exec` for an interactive session. No password in it.

    `--env-file` again, for D1160's reason, and `-it` so the session is a
    terminal. `PGOPTIONS` carries the development subject: measured in rig
    22b-2, `api.notes` returns the subject's row with it, nothing without it,
    and nothing with another subject's id -- which is row-level security doing
    its work on a cluster a developer can break.

    The subject is asserted for BOTH roles. As the application role a developer
    sees the subject's rows; as the migration user they apply SQL the way a
    migration would, and a migration with no request identity raises `AP401`.
    """
    if role_key not in PSQL_ROLES:
        raise DevEnvironmentError(
            f"{role_key!r} is not a role this command connects as. "
            f"Choose one of: {', '.join(sorted(PSQL_ROLES))}"
        )
    role_suffix = PSQL_ROLES[role_key]
    arguments = [
        "exec",
        "-it",
        "--env-file",
        str(state_directory / PSQL_ENV_FILES[role_suffix]),
    ]
    if environment.subject_id:
        arguments += ["-e", f"PGOPTIONS=-c app.user_id={environment.subject_id}"]
    arguments += [
        environment.container,
        "psql",
        "-U",
        environment.roles[role_suffix],
        "-h",
        "127.0.0.1",
        "-d",
        environment.database,
    ]
    return arguments + list(extra or [])


__all__ = [
    "ABSENT",
    "ACTIVATED_ROLES",
    "APP_RUNTIME_ENV",
    "CONTAINER_PREFIX",
    "MIGRATION_USER_ENV",
    "PSQL_ENV_FILES",
    "PSQL_ROLES",
    "RUNNING",
    "SEEDS_DIRECTORY",
    "SEEDS_FILE",
    "SEEDS_MANIFEST",
    "SEED_DDL",
    "SEED_FILE",
    "SEED_MANIFEST_SCHEMA_VERSION",
    "SEED_NAME",
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
    "lint_seed",
    "load_seeds_manifest",
    "locked_image",
    "migration_transaction",
    "owner_grant_statements",
    "password_env_content",
    "placeholder_verifier",
    "planned_migrations",
    "psql_arguments",
    "read_applied_seeds",
    "read_state",
    "render_seed",
    "role_statements",
    "run_arguments",
    "seed_entry",
    "seed_transaction",
    "seeds_root",
    "state_dir",
    "status_of",
    "subject_statement",
    "subject_vocabulary",
    "superuser_env_content",
    "verify_seed",
    "write_applied_seeds",
    "write_state",
]

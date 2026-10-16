"""The reconciler's closed table: what each operation type runs, as argv LISTS (ADR 0256).

**No input accepts a command** (D2154, ADR 0050/0178 moved to root). A claimed
operation is a row a customer's request wrote; what reaches root from it is:

* its `type`, one of `STEPS`' keys -- the closed table. A type outside it is
  finished `failed invalid_request` with nothing run;
* its `arguments`, validated against `schemas/operation-arguments.schema.json`
  (`invalid`) BEFORE anything runs -- the same file the control mode's request
  models mirror, so a row is validated twice;
* and of those arguments, **only `profile` and `admin_username` may appear in
  an argv** (`ARGV_MEMBERS`), each checked again here against its pattern. The
  display name and the handoff hash reach only a database, as `psql`
  variables set on psql's STDIN (`psql_input`) -- never a process argument.

Every builder returns a list for `subprocess.run` without a shell; a proof
parses this module and `bin/reconciler.py` and refuses `shell=True`,
`os.system`, `os.popen` and a string command (D2154's AST guard).

The SQL the reconciler sends is here too, every value a `:'variable'`.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import jsonschema

from agentic_postgres import REPO_ROOT, compute_profiles, operations, slot

__all__ = [
    "ADMIN_ID_SQL",
    "ADOPT_SQL",
    "ALTER_PASSWORD_SQL",
    "ARGV_MEMBERS",
    "BACKUP_SEQUENCE",
    "BACKUP_VERBS",
    "CLAIM_SQL",
    "COMMANDS",
    "CUSTOMER_DOORS",
    "EXPORT_SCHEMAS",
    "FINISH_SQL",
    "INSTANCE_UUID_SQL",
    "INTERRUPTED_SQL",
    "MARK_DELETED_SQL",
    "OPEN_HANDOFF_SQL",
    "PROGRESS_SQL",
    "RECORD_SLOTS_SQL",
    "RESULT_MEMBERS",
    "STEPS",
    "admission_reading",
    "admit_argv",
    "backup_argv",
    "bootstrap_argv",
    "credentials_argv",
    "deploy_argv",
    "disable_argv",
    "dump_argv",
    "enable_argv",
    "invalid",
    "profile_name",
    "psql_input",
    "result",
    "retire_argv",
    "running_argv",
    "runtime_argv",
    "runtime_render_argv",
    "storage_container_argv",
    "verify_argv",
]

#: Type -> its steps, in order, each with the progress recorded when it starts
#: (ADR 0256 §8: 10/30/40/60/70/90, 100 at the finish). Every executed type
#: (eleven since Session 40: the four branch types, D2434), no other --
#: `EXECUTED_TYPES`, a test holds the two equal (D2447 corrected the count). A
#: branch operation is ONE `branch-runtime.sh` child, so its steps are check,
#: runtime and record; how far a runtime got is its `branch.json` (D2471).
STEPS: dict[str, tuple[tuple[str, int], ...]] = {
    "project.create": (
        ("allocate", 10),
        ("admit", 10),
        ("deploy-1", 30),
        ("admin", 40),
        ("ports", 60),
        ("deploy-2", 60),
        ("unit", 70),
        ("backup", 90),
        ("registry", 90),
    ),
    # D2155: the timers first (a timer firing would start a stopped project),
    # then the boot unit, then the containers stopped and kept.
    "project.sleep": (("schedule", 10), ("unit", 30), ("stop", 60)),
    # The reverse: the same containers started, then the unit, then the timers.
    "project.wake": (("start", 10), ("unit", 60), ("schedule", 90)),
    # D2157/D2160: admission on the candidate manifest before anything changes.
    "project.resize": (("admit", 10), ("deploy", 30), ("registry", 90)),
    # D2164: the archive, then the upload inside the storage container.
    "project.export": (("dump", 10), ("upload", 60)),
    # D2158: the retirement (provider deferred), the tombstone, the registry.
    "project.delete": (("retire", 10), ("tombstone", 80), ("registry", 90)),
    # Session 39 (ADR 0269, D2330): the door and its role read from the
    # deployed document, the verifier set in the project's database, both
    # poolers' userlists rewritten from `pg_authid`.
    "credential.rotate": (("check", 10), ("alter", 40), ("sync", 70)),
    # Session 40 (ADR 0271): the parent checked (a slot, awake), then ONE child
    # -- `branch-runtime.sh`, whose own order is the property (record, restore,
    # recover, persist, re-key, userlists, doors, attach) -- then the reading
    # recorded. `restore.create` is `branch.create` with a point (D2434).
    "branch.create": (("check", 10), ("runtime", 20), ("record", 95)),
    "restore.create": (("check", 10), ("runtime", 20), ("record", 95)),
    "branch.reset": (("check", 10), ("runtime", 20), ("record", 95)),
    "branch.delete": (("check", 10), ("runtime", 30), ("record", 95)),
}

#: What a finished operation may record (D2151): the service's table, which
#: the control set's `control_result_members` repeats and enforces.
RESULT_MEMBERS: dict[str, frozenset[str]] = operations.RESULT_MEMBERS

#: The only argument members that may reach a process argument (D2154).
ARGV_MEMBERS = frozenset(
    # Session 40: a branch's name, its point and its expiry -- each a value the
    # schema bounds to a name or an RFC 3339 instant. The verifiers never: they
    # reach `branch-runtime.sh` as JSON on stdin (ADR 0271, D2449).
    {"profile", "admin_username", "branch", "target_time", "expires_at"}
)

#: Every command an operation may run, by the name its argv starts with: the
#: existing `bin/` commands, `systemctl`, and two `docker` READS -- whether the
#: database container runs, and which container is the project's storage
#: (ADR 0256 §6). Every `docker exec` goes through `container_exec.run`.
COMMANDS = frozenset(
    {
        "admit.sh",
        "deploy.sh",
        "auth-admin.sh",
        "database-ports.sh",
        "systemctl",
        "backup.sh",
        "project-runtime.sh",
        "project-retire.sh",
        "docker",
        # Session 39 (ADR 0269): the userlists from `pg_authid`, and the SIGHUP.
        "customer-credentials.sh",
        # Session 40 (ADR 0271): a branch's whole life on this host.
        "branch-runtime.sh",
    }
)

#: The schemas an export carries: the customer's, never `app_private` (D2164,
#: rig 38d: `-n app -n api` lists no `app_private`; without `-n` it does) --
#: and since Session 39 `public`, where `customer_admin` creates the
#: customer's own tables (D2333, ADR 0259 amended, rig 39c's `pg_dump -n public`).
EXPORT_SCHEMAS = ("app", "api", "public")

#: Session 39 (ADR 0269): a credential's role -> the door of `database.public`
#: whose `user` names it. The argument is the suffix; the role's NAME is the
#: deployed document's.
CUSTOMER_DOORS = {"customer_app": "pooled", "customer_admin": "direct"}

#: A container name as Compose writes one, read from a deployed document or
#: from `docker ps` -- never one a value chose.
_CONTAINER = re.compile(r"[a-z0-9][a-z0-9_.-]{0,127}")

#: The schema's patterns, fullmatched again where a member reaches an argv.
_USERNAME = re.compile(r"[a-z][a-z0-9_.-]{2,62}")

#: The three backup commands a creation runs after its unit is enabled: the
#: first full backup, the schedule, the mirror (D2173's hand acts).
BACKUP_SEQUENCE: tuple[tuple[str, ...], ...] = (
    ("backup", "--type", "full"),
    ("schedule", "enable"),
    ("mirror",),
)

# ---------------------------------------------------------------------------
# The control database (every function granted to nobody, run as the
# superuser through `container_exec.run`, D2093)
# ---------------------------------------------------------------------------

CLAIM_SQL = "SELECT row_to_json(c) FROM app.control_claim_operation(:'worker') c;"
PROGRESS_SQL = (
    "SELECT app.control_advance_operation(:'id'::uuid, :'step', :'progress'::integer, "
    "nullif(:'project_key', ''));"
)
FINISH_SQL = (
    "SELECT app.control_finish_operation(:'id'::uuid, :'status', nullif(:'error_code', ''), "
    ":'result'::jsonb, nullif(:'secret', ''));"
)
#: D2167: the registry row of a deleted project kept, marked.
MARK_DELETED_SQL = "SELECT app.control_mark_deleted(:'key');"

INTERRUPTED_SQL = (
    "SELECT coalesce(json_agg(r ORDER BY r.started_at, r.id), '[]'::json) "
    "FROM app.control_interrupted_operations() r;"
)
RECORD_SLOTS_SQL = "SELECT app.control_record_slots(:'slots'::jsonb);"
#: Session 40 (ADR 0271, ADR 0272, ADR 0273): the reconciler's three writes of
#: the control set's branch and backups readings, each granted to nobody.
RECORD_BRANCHES_SQL = "SELECT app.control_record_branches(:'branches'::jsonb);"
RECORD_BACKUPS_SQL = "SELECT app.control_record_backups(:'readings'::jsonb);"
REQUEST_EXPIRY_SQL = "SELECT coalesce(app.control_request_expiry(:'key', :'branch')::text, '');"
ADOPT_SQL = (
    "SELECT app.control_adopt_project(:'key', :'organization'::uuid, :'slug', :'environment', "
    ":'domain', :'template_version', :'source_commit', nullif(:'region', ''), :'profile', "
    "nullif(:'slot', ''), nullif(:'app_route', ''), nullif(:'display_name', ''), "
    "nullif(:'endpoints', '')::jsonb);"
)

# ---------------------------------------------------------------------------
# The project's own database, as its superuser (ADR 0260, D2173)
# ---------------------------------------------------------------------------

#: The administrator `auth-admin bootstrap` just created, by its username.
ADMIN_ID_SQL = (
    "SELECT id FROM app_private.users WHERE username = :'username' AND status = 'active';"
)
#: The handoff (D2163): a reset the administrator opens for themself, keyed by
#: the HASH of a token only the requester's CLI holds; consumable for 24 hours.
OPEN_HANDOFF_SQL = (
    "SELECT app_private.auth_open_password_reset(:'user'::uuid, :'user'::uuid, :'hash', "
    "now() + interval '24 hours');"
)
#: Session 39 (ADR 0269, D2330): the customer's verifier set as the role's
#: password -- both values psql variables on stdin, the role an identifier
#: (`:"role"`), the verifier a literal (`:'verifier'`). PostgreSQL stores a
#: value already shaped as a SCRAM verifier as it is, and no password exists.
ALTER_PASSWORD_SQL = "ALTER ROLE :\"role\" PASSWORD :'verifier';"  # noqa: S105 -- a statement; the value is a variable

#: The identity the volume carries -- read the way `deploy-project.py`'s
#: `cluster_instance_uuid` reads it, never from a printed line (D2173).
INSTANCE_UUID_SQL = "SELECT instance_uuid FROM app_private.project_identity;"


def psql_input(sql: str, variables: dict[str, str]) -> str:
    """`sql` preceded by one `\\set name 'value'` per variable, for psql's stdin.

    A value set this way is in no process argument (D2154: the display name and
    the handoff hash reach only a database). Inside psql's single quotes a
    backslash is an escape and a quote is doubled, so both are escaped; a
    newline becomes the `\\n` escape, so a value can never end the line it is
    set on. Names are identifiers this module chose.
    """
    lines = []
    for name, value in variables.items():
        if not re.fullmatch(r"[a-z_]+", name):
            raise ValueError(f"not a variable name: {name!r}")
        escaped = (
            value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("'", "''")
        )
        lines.append(f"\\set {name} '{escaped}'")
    return "\n".join([*lines, sql, ""])


# ---------------------------------------------------------------------------
# Validation and results
# ---------------------------------------------------------------------------


def _schema() -> dict[str, Any]:
    return json.loads((REPO_ROOT / operations.ARGUMENT_SCHEMA_PATH).read_text(encoding="utf-8"))


def invalid(operation_type: str, arguments: Any) -> str | None:
    """None when `{type, arguments}` validates against the schema file, else a
    reason that names the type and never echoes an argument's value."""
    validator = jsonschema.Draft202012Validator(_schema())
    if validator.is_valid({"type": operation_type, "arguments": arguments}):
        return None
    return f"the arguments do not match {operations.ARGUMENT_SCHEMA_PATH} for {operation_type}"


def result(operation_type: str, members: dict[str, Any]) -> dict[str, Any]:
    """`members` as a result, refused here when the type does not declare one
    of them -- the same refusal `control_finish_operation` makes."""
    undeclared = sorted(set(members) - RESULT_MEMBERS[operation_type])
    if undeclared:
        raise ValueError(f"{operation_type} declares no result member {', '.join(undeclared)}")
    return dict(members)


# ---------------------------------------------------------------------------
# The argv builders. `checkout` is the reconciler's own checkout (its working
# directory); every path below is derived from it, a slot key, or a project key.
# ---------------------------------------------------------------------------


def profile_name(value: str) -> str:
    """A compute profile, or ValueError: it reaches the slot's manifest, which
    every command is handed by path (D2154's `profile`)."""
    if value not in compute_profiles.PROFILE_NAMES:
        raise ValueError(f"not a compute profile: {value!r}")
    return value


def _username(value: str) -> str:
    if not _USERNAME.fullmatch(value):
        raise ValueError("not an administrator username the schema allows")
    return value


def _host(checkout: Path) -> str:
    return str(checkout / "host.yaml")


def admit_argv(checkout: Path, manifest: Path) -> list[str]:
    """Admission for the slot's manifest at its requested profile (D2160)."""
    return [
        str(checkout / "bin" / "admit.sh"),
        "--host", _host(checkout),
        "--project", str(manifest),
        "--json",
    ]  # fmt: skip


def deploy_argv(checkout: Path, manifest: Path, *, through_session: int) -> list[str]:
    return [
        str(checkout / "deploy.sh"),
        "--host", _host(checkout),
        "--project", str(manifest),
        "--capabilities", str(checkout / "capabilities.yaml"),
        "--through-session", str(int(through_session)),
    ]  # fmt: skip


def runtime_render_argv(checkout: Path, manifest: Path) -> list[str]:
    """The port reservation and override (`--render-runtime-only`); what it
    PRINTS is never executed -- `verify_argv` is built instead (D2173)."""
    return [
        str(checkout / "deploy.sh"),
        "--host", _host(checkout),
        "--project", str(manifest),
        "--capabilities", str(checkout / "capabilities.yaml"),
        "--render-runtime-only",
    ]  # fmt: skip


def bootstrap_argv(checkout: Path, outputs: Path, username: str, descriptor: int) -> list[str]:
    """The first administrator, its password read from an inherited pipe (ADR
    0260). The username is the display name too: the customer's project name is
    an argument that reaches no argv (D2154)."""
    name = _username(username)
    return [
        str(checkout / "bin" / "auth-admin.sh"),
        "--outputs", str(outputs),
        "bootstrap",
        "--username", name,
        "--display-name", name,
        "--password-fd", str(int(descriptor)),
    ]  # fmt: skip


def verify_argv(checkout: Path, instance_uuid: str) -> list[str]:
    return [
        str(checkout / "bin" / "database-ports.sh"),
        "verify",
        "--host", _host(checkout),
        "--instance-uuid", str(uuid.UUID(instance_uuid)),
    ]  # fmt: skip


def enable_argv(key: str) -> list[str]:
    """The project's boot unit, enabled -- not started: the deploy started it."""
    if not slot.SLOT_KEY.fullmatch(key):
        raise ValueError(f"not a slot key: {key!r}")
    return ["systemctl", "enable", f"agentic-postgres-project@{key}.service"]


#: Every backup command an operation runs: a creation's three, and sleep's
#: (the timers disabled) -- wake's `schedule enable` is the creation's.
BACKUP_VERBS: tuple[tuple[str, ...], ...] = (*BACKUP_SEQUENCE, ("schedule", "disable"))


def backup_argv(checkout: Path, outputs: Path, verb: tuple[str, ...]) -> list[str]:
    if verb not in BACKUP_VERBS:
        raise ValueError(f"not a backup step: {verb!r}")
    return [str(checkout / "bin" / "backup.sh"), "--outputs", str(outputs), *verb]


def _key(key: str) -> str:
    if not slot.SLOT_KEY.fullmatch(key):
        raise ValueError(f"not a slot key: {key!r}")
    return key


def _container(name: str) -> str:
    if not _CONTAINER.fullmatch(name):
        raise ValueError("not a container name")
    return name


def credentials_argv(checkout: Path, outputs: Path) -> list[str]:
    """Both customer poolers' userlists from `pg_authid`, then SIGHUP (ADR 0269)."""
    return [str(checkout / "bin" / "customer-credentials.sh"), "sync", "--outputs", str(outputs)]


def admission_reading(stdout: str) -> dict[str, int] | None:
    """`{"requested_mb", "safe_available_mb"}` out of `admit.sh --json`'s own
    lines (D2362, ADR 0270) -- the numbers its decision was taken on -- or None
    when they cannot be read. Never a number the reconciler computed."""
    try:
        decision = json.loads(stdout)
        lines = {line["label"]: line["value"] for line in decision["lines"]}
    except (ValueError, TypeError, KeyError):
        return None
    reading = {}
    for member, label in (("requested_mb", "requested"), ("safe_available_mb", "safe available")):
        value = lines.get(label)
        found = re.match(r"(-?[0-9]+) MiB", value) if isinstance(value, str) else None
        if found is None:
            return None
        reading[member] = int(found.group(1))
    return reading


def disable_argv(key: str) -> list[str]:
    """The boot unit disabled -- not stopped: `project-runtime.sh stop` stops the
    containers and the unit stays active (D2155)."""
    return ["systemctl", "disable", f"agentic-postgres-project@{_key(key)}.service"]


def runtime_argv(checkout: Path, key: str, through_session: int, action: str) -> list[str]:
    """`project-runtime.sh … stop|start` (D2155, D2192): the containers kept,
    nothing materialized, rendered or built."""
    if action not in ("stop", "start"):
        raise ValueError(f"not a runtime action: {action!r}")
    return [
        str(checkout / "bin" / "project-runtime.sh"),
        "--host", _host(checkout),
        "--project-key", _key(key),
        "--through-session", str(int(through_session)),
        action,
    ]  # fmt: skip


def retire_argv(checkout: Path, key: str, record: Path) -> list[str]:
    """D2158: every retirement step but the provider's, the data destroyed."""
    return [
        str(checkout / "bin" / "project-retire.sh"),
        "--host", _host(checkout),
        "--project", _key(key),
        "--confirm", key,
        "--record", str(record),
        "--permanent",
        "--destroy-data",
        "--defer-provider",
    ]  # fmt: skip


def running_argv(container: str) -> list[str]:
    """Whether the project's database container runs: `true`, `false`, or no answer."""
    return ["docker", "inspect", "--format", "{{.State.Running}}", _container(container)]


def storage_container_argv(key: str) -> list[str]:
    """The project's storage container, found by its Compose labels the way
    `auth-admin.py` finds `auth` (`apg.project.key`, D293)."""
    return [
        "docker", "ps",
        "--filter", f"label=apg.project.key={_key(key)}",
        "--filter", "label=com.docker.compose.service=storage",
        "--format", "{{.Names}}",
    ]  # fmt: skip


def dump_argv(database: str) -> list[str]:
    """`pg_dump` of the customer's schemas, for `container_exec.run` in the
    database container (D2164): custom format, no owner, no privileges."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database):
        raise ValueError("not a database name")
    schemas = [part for name in EXPORT_SCHEMAS for part in ("-n", name)]
    return [
        "pg_dump", "-U", "postgres", "-Fc", *schemas,
        "--no-owner", "--no-privileges", "-d", database,
    ]  # fmt: skip


# ---------------------------------------------------------------------------
# Session 40: branches (ADR 0271, ADR 0272, ADR 0273)
# ---------------------------------------------------------------------------

_INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z")


def _branch(name: str) -> str:
    from agentic_postgres import naming

    return naming.validate_branch_name(name)


def _instant(value: str) -> str:
    if not _INSTANT.fullmatch(value):
        raise ValueError("not an RFC 3339 UTC instant")
    return value


def _runtime(checkout: Path) -> str:
    return str(checkout / "bin" / "branch-runtime.sh")


def branch_create_argv(
    checkout: Path,
    outputs: Path,
    arguments: dict[str, Any],
    *,
    operation: str,
    requested_by: str,
) -> list[str]:
    """`branch-runtime.sh create` for `branch.create` and `restore.create`: the
    branch name, the point, the expiry and the member it is set for -- the
    row's own `requested_by`, never an argument (ADR 0272). The verifiers are
    NOT here: `branch_verifiers_input` carries them on stdin."""
    argv = [
        _runtime(checkout), "create",
        "--parent-outputs", str(outputs),
        "--branch", _branch(arguments["branch"]),
        "--verifiers-stdin",
        "--operation", str(uuid.UUID(operation)),
        "--host", _host(checkout),
    ]  # fmt: skip
    if arguments.get("target_time"):
        argv += ["--target-time", _instant(arguments["target_time"])]
    if arguments.get("expires_at"):
        argv += [
            "--expires-at", _instant(arguments["expires_at"]),
            "--expires-for", str(uuid.UUID(requested_by)),
        ]  # fmt: skip
    return argv


def branch_reset_argv(
    checkout: Path, outputs: Path, arguments: dict[str, Any], *, operation: str
) -> list[str]:
    argv = [
        _runtime(checkout), "reset",
        "--parent-outputs", str(outputs),
        "--branch", _branch(arguments["branch"]),
        "--verifiers-stdin",
        "--operation", str(uuid.UUID(operation)),
        "--host", _host(checkout),
    ]  # fmt: skip
    if arguments.get("target_time"):
        argv += ["--target-time", _instant(arguments["target_time"])]
    return argv


def branch_delete_argv(checkout: Path, key: str, branch: str) -> list[str]:
    return [
        _runtime(checkout), "delete", "--parent-key", _key(key), "--branch", _branch(branch)
    ]  # fmt: skip


def branch_start_argv(checkout: Path) -> list[str]:
    """`start --all` at the reconciler's start: every recorded branch back (D2439)."""
    return [_runtime(checkout), "start", "--all"]


def branch_verifiers_input(arguments: dict[str, Any]) -> str:
    """The branch's two verifiers as `branch-runtime`'s stdin: JSON, never an argv."""
    return json.dumps(
        {"customer_app": arguments["app_verifier"], "customer_admin": arguments["admin_verifier"]}
    )


def branch_reading(found: dict[str, Any], unreadable: dict[str, str]) -> list[dict[str, Any]]:
    """`control_record_branches`' payload from `branch_record.records()`: each
    readable record's members, and each unreadable one as `undetermined` (ADR
    0195) -- a branch the control plane must not call gone because its record
    could not be read."""
    rows: list[dict[str, Any]] = []
    for record in found.values():
        rows.append(
            {
                "project_key": record.project_key,
                "name": record.branch,
                "state": record.state,
                "requested_point": record.requested_point,
                "reached_point": record.reached_point,
                "timeline": record.timeline,
                "parent_commit": record.parent_commit,
                "pool_host": record.pool_host,
                "direct_host": record.direct_host,
                "expires_at": record.expires_at,
                "expires_for": record.expires_for,
                "created_at": record.created_at,
            }
        )
    for name in unreadable:
        key, separator, branch = name.partition("_")
        if separator and branch and branch != "*":
            rows.append({"project_key": key, "name": branch, "state": "undetermined"})
    return rows


def expired_branches(found: dict[str, Any], now: str) -> list[tuple[str, str]]:
    """`(key, branch)` for each READY branch whose recorded expiry has passed;
    the control set decides whether to request its deletion (ADR 0272)."""
    return sorted(
        (record.project_key, record.branch)
        for record in found.values()
        if record.state == "ready" and record.expires_at and record.expires_at <= now
    )


def _status(check: Any) -> str:
    return str(getattr(check, "verdict", "unknown")).lower()


def backups_reading(
    key: str,
    *,
    info: dict[str, Any] | None,
    usage: dict[str, Any] | None,
    archiver: dict[str, Any] | None,
    mirror: Any,
    sleeping: bool,
) -> dict[str, Any]:
    """One project's backups reading for `control_record_backups` (ADR 0273):
    the doctor's own classifiers over `backup.sh info --json` and the archiver
    query, the mirror's from the copy record (D2461), the window's bounds -- the
    oldest stop plus a second (D2465) and the last archived time (D2456).

    **The oldest stop is read from `backup.sh usage --json`** (D2501, D2540):
    `info --json` is the deployed document's closed `backup_state` block and
    never carried it, so reading it there made every window `could_not_determine`.
    Every key read here from `info` or `usage` is a key its producer prints --
    `tests/contract/test_backups_reading_from_the_producer.py` holds that."""
    from agentic_postgres import backup_report, diagnosis

    repository = diagnosis.repository(
        status=(info or {}).get("status"),
        last_full_backup_at=(info or {}).get("last_full_backup_at"),
    )
    archived = diagnosis.archiver(
        failing=None if archiver is None else backup_report.archiving_is_failing(archiver),
        last_archived_time=(archiver or {}).get("last_archived_time"),
    )
    earliest = backup_report.earliest_point((usage or {}).get("oldest_backup_stop"))
    latest = backup_report_instant((archiver or {}).get("last_archived_time"))
    # `mirror` is None when nothing read it -- a sleeping slot's reading, and
    # any project without a copy record reader. Its status is then `unknown`
    # and it has no detail to give; before Session 41 this line took `.detail`
    # of None, so a sleeping slot raised out of the reconciler's loop (D2541).
    reasons = [
        c.detail for c in (repository, archived, mirror) if c is not None and _status(c) != "ok"
    ]
    return {
        "project_key": key,
        "repository_status": _status(repository),
        "archiver_status": _status(archived),
        "mirror_status": _status(mirror),
        "earliest": earliest.isoformat() if earliest else None,
        "latest": latest,
        "last_full_at": (info or {}).get("last_full_backup_at"),
        "sleeping": sleeping,
        "reason": ("; ".join(reasons)[:300] or None),
    }


def backup_report_instant(value: str | None) -> str | None:
    """The archiver's `last_archived_time` text as an ISO instant, or None."""
    from agentic_postgres import restore_drill

    parsed = restore_drill.instant(value)
    return parsed.isoformat() if parsed else None

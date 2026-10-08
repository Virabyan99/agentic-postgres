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
    "ARGV_MEMBERS",
    "BACKUP_SEQUENCE",
    "BACKUP_VERBS",
    "CLAIM_SQL",
    "COMMANDS",
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
    "admit_argv",
    "backup_argv",
    "bootstrap_argv",
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
#: (ADR 0256 §8: 10/30/40/60/70/90, 100 at the finish). The six executed types,
#: no other -- `EXECUTED_TYPES`, a test holds the two equal.
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
}

#: What a finished operation may record (D2151): the service's table, which
#: the control set's `control_result_members` repeats and enforces.
RESULT_MEMBERS: dict[str, frozenset[str]] = operations.RESULT_MEMBERS

#: The only argument members that may reach a process argument (D2154).
ARGV_MEMBERS = frozenset({"profile", "admin_username"})

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
    }
)

#: The schemas an export carries: the customer's, never `app_private` (D2164,
#: rig 38d: `-n app -n api` lists no `app_private`; without `-n` it does).
EXPORT_SCHEMAS = ("app", "api")

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
ADOPT_SQL = (
    "SELECT app.control_adopt_project(:'key', :'organization'::uuid, :'slug', :'environment', "
    ":'domain', :'template_version', :'source_commit', nullif(:'region', ''), :'profile', "
    "nullif(:'slot', ''), nullif(:'app_route', ''), nullif(:'display_name', ''));"
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

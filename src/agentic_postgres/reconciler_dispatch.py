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
    "CLAIM_SQL",
    "COMMANDS",
    "FINISH_SQL",
    "INSTANCE_UUID_SQL",
    "INTERRUPTED_SQL",
    "OPEN_HANDOFF_SQL",
    "PROGRESS_SQL",
    "RECORD_SLOTS_SQL",
    "RESULT_MEMBERS",
    "STEPS",
    "admit_argv",
    "backup_argv",
    "bootstrap_argv",
    "deploy_argv",
    "enable_argv",
    "invalid",
    "profile_name",
    "psql_input",
    "result",
    "runtime_render_argv",
    "verify_argv",
]

#: Type -> its steps, in order, each with the progress recorded when it starts
#: (ADR 0256 §8: 10/30/40/60/70/90, 100 at the finish). Run 7 adds the other
#: five executed types; until then a claimed row of one of them is refused.
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
}

#: What a finished operation may record (D2151): the service's table, which
#: the control set's `control_result_members` repeats and enforces.
RESULT_MEMBERS: dict[str, frozenset[str]] = operations.RESULT_MEMBERS

#: The only argument members that may reach a process argument (D2154).
ARGV_MEMBERS = frozenset({"profile", "admin_username"})

#: Every command an operation may run, by the name its argv starts with: the
#: existing `bin/` commands and `systemctl` (ADR 0256 §6).
COMMANDS = frozenset(
    {"admit.sh", "deploy.sh", "auth-admin.sh", "database-ports.sh", "systemctl", "backup.sh"}
)

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
    ":'result'::jsonb);"
)
INTERRUPTED_SQL = (
    "SELECT coalesce(json_agg(r ORDER BY r.started_at, r.id), '[]'::json) "
    "FROM app.control_interrupted_operations() r;"
)
RECORD_SLOTS_SQL = "SELECT app.control_record_slots(:'slots'::jsonb);"
ADOPT_SQL = (
    "SELECT app.control_adopt_project(:'key', :'organization'::uuid, :'slug', :'environment', "
    ":'domain', :'template_version', :'source_commit', nullif(:'region', ''), :'profile', "
    ":'slot', nullif(:'app_route', ''), :'display_name');"
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


def backup_argv(checkout: Path, outputs: Path, verb: tuple[str, ...]) -> list[str]:
    if verb not in BACKUP_SEQUENCE:
        raise ValueError(f"not a backup step: {verb!r}")
    return [str(checkout / "bin" / "backup.sh"), "--outputs", str(outputs), *verb]

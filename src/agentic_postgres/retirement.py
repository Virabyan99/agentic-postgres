"""What retiring a project removes, in what order, and what it never touches (ADR 0187).

`FLEET-RETIRE-001`, `FLEET-RETIRE-002`, `FLEET-EXPIRE-001`. The plan lives
here and the execution lives in `bin/project-retire.py`, which is
`diagnosis`'s split and `fleet`'s: the command needs root and a host, so
everything that can be reasoned about is put where it can be exercised.

**A retirement removes what its key derives and its state records, on this
host, and never a backup.** Every name below is either derived through
`naming` from the project key or read off the deployed document the deploy
wrote for that key (ADR 0002); nothing is typed. What a retirement never
reaches: the backup repository, the bucket, the cipher pass, the Infisical
project's secrets, the DNS record, the certificate. The record says so in
words, because the operator's next step is at a console this code cannot see.

**The order is a contract** (D956). The port allocation is keyed by the
identity the volume carries, so the release comes before any volume is
removed; the provider destroy reads the installed manifest and the bootstrap
state out of the state directory, so it comes before that directory is
removed; and the record is written before anything at all, because a record
captured afterwards is a list of things that no longer exist.

**Expiry is read, never acted on** (ADR 0186). `refusal` decides whether a
retirement may proceed from the lifecycle the document carries and the flags
a human typed; nothing here reads a clock except to compare against a value
the caller passed in.

Nothing here reads a file, runs a process, reads a clock or touches the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agentic_postgres import fleet, naming
from agentic_postgres.edge_credentials import middleware_file_name, retired_users_file_name

__all__ = [
    "PROJECT_KEY",
    "STEP_ORDER",
    "Resources",
    "Step",
    "record",
    "refusal",
    "render_plan",
    "resources_of",
    "steps",
]

#: The project key's shape -- the outputs schema's `projectKey` pattern and
#: `bin/project-runtime.sh`'s `PROJECT_KEY_PATTERN`, restated so a key is
#: validated before it becomes a path component. A test asserts the three agree.
PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{4,47}$")

#: The steps, in the only order they may run. Each name is a contract test's
#: anchor; the executor walks this tuple and nothing else.
STEP_ORDER = (
    "record",
    "down",
    "disable-units",
    "release-ports",
    "edge-files",
    "provider-destroy",
    "remove-directories",
    "remove-volumes",
)


@dataclass(frozen=True)
class Resources:
    """Everything a retirement of one project names, derived once."""

    key: str
    compose_project: str
    edge_network: str
    internal_network: str
    backup_network: str
    postgres_volume: str
    store_volume: str
    unit: str
    timers: tuple[str, ...]
    state_directory: Path
    secrets_directory: Path
    rendered_directory: Path
    installed_manifest: Path
    edge_files: tuple[Path, ...]
    instance_uuid: str | None
    deployed_through_session: int
    source_commit: str
    lifecycle: dict[str, object]
    backup_bucket: str | None
    backup_stanza: str | None
    infisical_project_id: str | None
    runtime_identity_id: str | None


@dataclass(frozen=True)
class Step:
    name: str
    what: str
    #: Commands to run, in order, each an argv. Empty for steps the executor
    #: performs with the filesystem rather than a subprocess.
    commands: tuple[tuple[str, ...], ...] = ()
    #: Paths the step removes. Empty for command steps.
    paths: tuple[Path, ...] = ()


def resources_of(
    key: str,
    document: dict[str, object],
    *,
    state_root: Path,
    secret_root: Path,
    rendered_root: Path,
    edge_dynamic_dir: Path,
) -> Resources:
    """Every name, from the key through `naming` or off the deployed document.

    The document has already passed `validate_deployed_document`, and its
    `project.key` equals ``key`` (the caller checks; a document under one key
    naming another is the thing a retirement must never act on).
    """
    if not PROJECT_KEY.match(key):
        raise ValueError(f"not a project key: {key!r}")
    project = _block(document, "project")
    if project.get("key") != key:
        raise ValueError(f"the document under {key!r} names project {project.get('key')!r}")
    edge = _block(document, "edge")
    database = _block(document, "database")
    observed = database.get("observed") if isinstance(database.get("observed"), dict) else {}
    backup = _block(document, "backup")
    bootstrap = _block(document, "bootstrap")

    return Resources(
        key=key,
        compose_project=naming.compose_project_name(key),
        edge_network=str(edge.get("project_edge_network")),
        internal_network=str(edge.get("project_internal_network")),
        backup_network=naming.backup_network_name(key),
        postgres_volume=naming.postgres_volume_name(key),
        store_volume=naming.store_volume_name(key),
        unit=f"agentic-postgres-project@{key}.service",
        timers=tuple(fleet.timer_unit(kind, key) for kind in fleet.TIMER_KINDS),
        state_directory=state_root / key,
        secrets_directory=secret_root / key,
        rendered_directory=rendered_root / key,
        installed_manifest=state_root / key / "manifest.yaml",
        edge_files=(
            edge_dynamic_dir / middleware_file_name(key),
            edge_dynamic_dir / retired_users_file_name(key),
        ),
        instance_uuid=_text(observed.get("instance_uuid")),  # type: ignore[union-attr]
        deployed_through_session=int(document.get("deployed_through_session") or 0),
        source_commit=str(document.get("source_commit")),
        lifecycle=dict(project.get("lifecycle") or {"kind": fleet.PERMANENT}),  # type: ignore[arg-type]
        backup_bucket=_text(backup.get("bucket")),
        backup_stanza=_text(backup.get("stanza")),
        infisical_project_id=_text(bootstrap.get("infisical_project_id")),
        runtime_identity_id=_text(bootstrap.get("runtime_identity_id")),
    )


def refusal(
    lifecycle: dict[str, object], *, permanent: bool, before_expiry: bool, now: datetime
) -> str | None:
    """Why this retirement may not proceed, or None (ADR 0186, ADR 0187).

    A permanent project needs `--permanent`; an ephemeral project that has not
    expired needs `--before-expiry`; an expired one needs neither. A flag that
    does not apply is refused too -- a flag that changes nothing is a flag the
    next operator will type reflexively (D374's shape at the terminal).
    """
    reading = fleet.lifecycle_of({"lifecycle": lifecycle}, now)
    kind, expires_at, expired = reading["kind"], reading["expires_at"], reading["expired"]
    if kind == fleet.PERMANENT:
        if before_expiry:
            return "--before-expiry does not apply: the project is permanent"
        if not permanent:
            return "the project is permanent; pass --permanent to retire it"
        return None
    if permanent:
        return "--permanent does not apply: the project is ephemeral"
    if not expired and not before_expiry:
        return (
            f"the project is ephemeral and expires at {expires_at}; "
            "pass --before-expiry to retire it now"
        )
    if expired and before_expiry:
        return f"--before-expiry does not apply: the project expired at {expires_at}"
    return None


def steps(
    resources: Resources,
    *,
    host_manifest: Path,
    root_dir: Path,
    destroy_data: bool,
    operator_credential_file: Path | None,
) -> tuple[Step, ...]:
    """The steps in `STEP_ORDER`, each with the commands or paths it performs.

    `root_dir` is the checkout whose commands are composed: the retirement
    runs the operator surface that exists (`project-runtime.sh down`,
    `database-ports.sh release`, `bootstrap-providers.sh --destroy`) rather
    than re-implementing any of it.
    """
    r = resources
    bin_dir = root_dir / "bin"
    destroy: list[str] = [
        str(bin_dir / "bootstrap-providers.sh"),
        "--host",
        str(host_manifest),
        "--project",
        str(r.installed_manifest),
        "--destroy",
        "--confirm",
        r.key,
    ]
    if operator_credential_file is not None:
        destroy += ["--operator-credential-file", str(operator_credential_file)]

    release: tuple[tuple[str, ...], ...] = ()
    if r.instance_uuid:
        release = (
            (
                str(bin_dir / "database-ports.sh"),
                "release",
                "--project-key",
                r.key,
                "--instance-uuid",
                r.instance_uuid,
            ),
        )

    volumes = (r.postgres_volume, r.store_volume) if destroy_data else ()
    by_name = {
        "record": Step("record", "write the retirement record, before anything changes"),
        "down": Step(
            "down",
            f"detach the edge and stop {r.compose_project}; the volumes are preserved",
            commands=(
                (
                    str(bin_dir / "project-runtime.sh"),
                    "--host",
                    str(host_manifest),
                    "--project-key",
                    r.key,
                    "--through-session",
                    str(r.deployed_through_session),
                    "down",
                ),
            ),
        ),
        "disable-units": Step(
            "disable-units",
            f"disable {r.unit} and both backup timers, where they are enabled",
            commands=tuple(("systemctl", "disable", "--now", unit) for unit in (r.unit, *r.timers)),
        ),
        "release-ports": Step(
            "release-ports",
            (
                f"release the port allocation under the volume's identity {r.instance_uuid}"
                if r.instance_uuid
                else "no instance uuid in the document; no allocation to release"
            ),
            commands=release,
        ),
        "edge-files": Step(
            "edge-files",
            "remove this project's two edge files (the second only if a pre-0086 deploy left it)",
            paths=r.edge_files,
        ),
        "provider-destroy": Step(
            "provider-destroy",
            "revoke the runtime identity and unlink the credential files; every secret stays",
            commands=(tuple(destroy),),
        ),
        "remove-directories": Step(
            "remove-directories",
            "remove the state, secrets and rendered directories",
            paths=(r.state_directory, r.secrets_directory, r.rendered_directory),
        ),
        "remove-volumes": Step(
            "remove-volumes",
            (
                f"remove volumes {r.postgres_volume} and {r.store_volume} (--destroy-data)"
                if destroy_data
                else f"keep volumes {r.postgres_volume} and {r.store_volume}"
            ),
            commands=tuple(("docker", "volume", "rm", name) for name in volumes),
        ),
    }
    return tuple(by_name[name] for name in STEP_ORDER)


def record(
    resources: Resources, *, captured_at: datetime, destroy_data: bool, record_path: Path
) -> dict[str, object]:
    """What the operator declared before removing anything -- the shape
    `APG_REMOVED_PROJECT_FILE` reads (`DEP-REMOVE-001`), plus what still holds
    the project's backups, in a sentence, because the next step is at a console."""
    r = resources
    held = (
        f"The backup repository for {r.key} stays in bucket {r.backup_bucket} under "
        f"stanza {r.backup_stanza}, readable with the cipher pass held by Infisical "
        f"project {r.infisical_project_id}. Nothing in this retirement deleted them; "
        "deleting the bucket and the Infisical project are console actions."
    )
    return {
        "project_key": r.key,
        "captured_at": captured_at.astimezone(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "lifecycle": dict(r.lifecycle),
        "release": {
            "source_commit": r.source_commit,
            "deployed_through_session": r.deployed_through_session,
        },
        "destroy_data": destroy_data,
        "resources": {
            "compose_project": r.compose_project,
            "networks": [r.edge_network, r.internal_network, r.backup_network],
            "volumes": [r.postgres_volume, r.store_volume],
            "units": [r.unit, *r.timers],
            "directories": [
                str(p) for p in (r.state_directory, r.secrets_directory, r.rendered_directory)
            ],
            "edge_files": [str(p) for p in r.edge_files],
            "port_allocation_instance_uuid": r.instance_uuid,
            "runtime_identity_id": r.runtime_identity_id,
        },
        "backups_still_held": held,
        "record_path": str(record_path),
    }


def render_plan(
    resources: Resources, plan: tuple[Step, ...], *, record_path: Path, executing: bool
) -> str:
    r = resources
    life = fleet.lifecycle_of({"lifecycle": r.lifecycle}, datetime.now(UTC))
    lines = [
        f"retire {r.key}: {'executing' if executing else 'plan only, nothing changes'}",
        f"  lifecycle   {life['kind']}"
        + (f" until {life['expires_at']}" if life["expires_at"] else "")
        + (" EXPIRED" if life["expired"] else ""),
        f"  release     {r.source_commit[:7]} through session {r.deployed_through_session}",
        f"  record      {record_path}",
        "",
    ]
    for index, step in enumerate(plan, start=1):
        lines.append(f"{index}. {step.name}: {step.what}")
        for command in step.commands:
            lines.append("     $ " + " ".join(command))
        for path in step.paths:
            lines.append(f"     - {path}")
    lines.append("")
    lines.append(
        f"never touched: bucket {r.backup_bucket}, stanza {r.backup_stanza}, the cipher pass, "
        f"Infisical project {r.infisical_project_id}, the DNS record, the certificate"
    )
    return "\n".join(lines)


def _block(document: dict[str, object], name: str) -> dict[str, object]:
    value = document.get(name)
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    return None if value is None else str(value)

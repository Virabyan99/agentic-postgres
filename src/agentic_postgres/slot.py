"""Customer slots: the manifest a slot is prepared with, and its derived state (ADR 0257).

A slot is a project the operator prepares in advance -- buckets, tokens, the
Infisical project and identity, the DNS record, the secrets -- so that a
customer's creation consumes nothing at a provider (D2150). The operator
DECLARES slots in `host.yaml` (schema 4, `slots.declared`); **a slot's state is
never written anywhere** (D2149). It is derived here from what exists on the
host, by `state()`, from readings `read()` takes -- each with three outcomes:
present, absent, and *could not determine* (ADR 0195), the third never folded
into either of the others.

The readings, and the files they read under `SLOT_ROOT/<key>/`:

* **prepared** -- `manifest.yaml` (written by `bin/slot.sh prepare`), the
  project's `bootstrap-state.json` (written by `bootstrap-providers --apply`)
  and an active secret generation (written by `materialize-secrets`);
* **dns** -- the slot's A record is the host's address and it has no AAAA
  (D2148; read by `bin/slot.py`, which runs `dig`);
* **allocated** -- a deployed document for the key, or the `allocated` marker
  the reconciler writes when it takes the slot (its content the operation's
  id);
* **quarantined** -- the marker an interrupted creation leaves (D2152);
* **consumed** -- the tombstone a deletion writes and **no command removes**.

`state()` is pure. `read()` reads files and nothing else; it runs no process
and touches no network. `dns_reading()` runs `dig` and nothing else does;
`observe()` is the one walk over the declared slots that `bin/slot.sh status`
prints and the reconciler records into `app.control_slots` (D2160) -- one
reader, two consumers, so the two cannot disagree about a slot.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_postgres import bootstrap_state, deployed_output, host_config, naming
from agentic_postgres.secret_generation import SECRET_ROOT, manifest_path

__all__ = [
    "ALLOCATED",
    "CONSUMED",
    "MANIFEST",
    "QUARANTINED",
    "RETIRED_STATE",
    "REVOKED",
    "SLOT_KEY",
    "SLOT_PROFILE",
    "SLOT_ROOT",
    "STATES",
    "Readings",
    "dns_reading",
    "observe",
    "read",
    "slot_directory",
    "slot_manifest",
    "state",
]

#: A slot key (D2180): host.schema.json's slots.declared[].key pattern, which
#: the control set's control_slots.key CHECK repeats; a test holds the three equal.
SLOT_KEY = re.compile(r"^slot[1-9][0-9]{0,2}-[a-z][a-z0-9-]{1,15}$")

#: Where every slot's files live: root-owned, 0700 directories of 0600 files.
SLOT_ROOT = Path("/etc/agentic-postgres/slots")

#: `host.yaml` declares; these files are what was DONE (D2149, D2152, D2158).
MANIFEST = "manifest.yaml"
ALLOCATED = "allocated"
QUARANTINED = "quarantined"
CONSUMED = "consumed"
RETIRED_STATE = "retired-bootstrap-state.json"
REVOKED = "revoked"

#: The seven states (D2149); the control set's `control_slots.state` CHECK
#: lists the same, and a test holds the two equal.
STATES: tuple[str, ...] = (
    "declared",
    "prepared",
    "ready",
    "allocated",
    "quarantined",
    "consumed",
    "undetermined",
)

#: A slot is prepared at the smallest profile (D2145); a creation re-writes the
#: manifest with the profile the customer asked for (Run 6).
SLOT_PROFILE = "small"

#: The resolver asked, and how long it may take (D2148: the C1 gate's check).
RESOLVER = "1.1.1.1"
DIG_TIMEOUT_SECONDS = 20

_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def slot_directory(key: str, *, root: Path = SLOT_ROOT) -> Path:
    """`root/<key>`, for a key `naming` would derive -- never a path a value chose."""
    if not SLOT_KEY.fullmatch(key):
        raise ValueError(f"not a slot key: {key!r}")
    return root / key


def slot_manifest(host: dict[str, Any], slot: host_config.DeclaredSlot) -> dict[str, Any]:
    """The project manifest a slot is prepared with (D2150).

    Every member is copied from the host's `slots.defaults` or the slot's
    declaration, or derived from its key through `naming`; nothing is typed.
    Lifecycle `permanent`; REST, the application API, storage and backups
    enabled, the backup with its mirror; connectors off; no migration set (a
    customer's own SQL is not this session's); `compute: small`. The profile
    owns every memory and pool member, so none is written here (D2198).
    """
    defaults = host_config.slot_defaults(host)
    if defaults is None:
        raise ValueError("the host manifest declares no slots.defaults")
    key = slot.key
    slug, environment = key.split("-", 1)
    sql = naming.sql_key(key)
    storage: dict[str, Any] = {
        "enabled": True,
        "account_id": defaults["storage"]["account_id"],
    }
    if defaults["storage"].get("jurisdiction") not in (None, "default"):
        storage["jurisdiction"] = defaults["storage"]["jurisdiction"]
    mirror: dict[str, Any] = {
        "enabled": True,
        "endpoint": defaults["backup"]["mirror"]["endpoint"],
        "region": defaults["backup"]["mirror"]["region"],
    }
    if slot.mirror_bucket:
        mirror["bucket"] = slot.mirror_bucket
    backup: dict[str, Any] = {
        "enabled": True,
        "stanza": key,
        "repository_prefix": f"pgbackrest/{key}/",
        "retain_full": 2,
        "account_id": defaults["backup"]["account_id"],
        "mirror": mirror,
    }
    if defaults["backup"].get("jurisdiction") not in (None, "default"):
        backup["jurisdiction"] = defaults["backup"]["jurisdiction"]
    return {
        "schema_version": 10,
        "project": {
            "slug": slug,
            "environment": environment,
            "domain": slot.domain,
            "lifecycle": {"kind": "permanent"},
        },
        "database": {
            "name": sql,
            "pooled_public": False,
            "pooled_public_cidrs": [],
            "max_client_connections": 100,
            "pool_size": 16,
        },
        "api": {
            "public_base_path": "/api",
            "max_rows": 500,
            "rest": {
                "enabled": True,
                "anonymous_access": "deny_data",
                "allowed_cors_origins": [f"https://{slot.domain}"],
            },
            "app": {"enabled": True},
        },
        "mcp": {"public_base_path": "/mcp", "profile": {}},
        "storage": storage,
        "backup": backup,
        "compute": {"profile": SLOT_PROFILE},
    }


@dataclass(frozen=True)
class Readings:
    """What exists for one declared slot: True, False, or None -- *could not
    determine* (a file that could not be stat'ed, a DNS answer not obtained)."""

    manifest: bool | None
    bootstrap_state: bool | None
    secret_generation: bool | None
    dns: bool | None
    deployed_document: bool | None
    allocated: bool | None
    quarantined: bool | None
    consumed: bool | None


def state(readings: Readings) -> tuple[str, str]:
    """`(state, reason)` for a DECLARED slot. Pure.

    The tombstone first (a consumed slot is consumed whatever else is left),
    then the quarantine, then occupancy, then preparation, then DNS. A reading
    that could not be taken at the step that decides is `undetermined`, with
    the reading named -- never the state the other readings would suggest.
    """
    r = readings
    for flag, name, reason in (
        (
            r.consumed,
            "consumed",
            "the tombstone is present: a deleted project's slot is never reissued",
        ),
        (
            r.quarantined,
            "quarantined",
            "an interrupted creation left it; the operator decides (D2152)",
        ),
    ):
        if flag is None:
            return "undetermined", f"the {name} marker could not be read"
        if flag:
            return name, reason
    if r.deployed_document is None or r.allocated is None:
        return "undetermined", "whether a project occupies it could not be read"
    if r.deployed_document:
        return "allocated", "a project is deployed under its key"
    if r.allocated:
        return "allocated", "the reconciler has taken it for a creation"
    prepared = {
        "the slot manifest": r.manifest,
        "the bootstrap state": r.bootstrap_state,
        "an active secret generation": r.secret_generation,
    }
    unread = [name for name, value in prepared.items() if value is None]
    if unread:
        return "undetermined", f"could not read {', '.join(unread)}"
    missing = [name for name, value in prepared.items() if not value]
    if missing:
        return "declared", f"not prepared: no {', '.join(missing)}"
    if r.dns is None:
        return "undetermined", "the DNS record could not be read"
    if not r.dns:
        return "prepared", "the DNS record is missing or does not name this host"
    return "ready", "prepared, and its DNS record names this host"


def _exists(path: Path) -> bool | None:
    """Present, absent, or None when the question could not be answered."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except NotADirectoryError:
        return False
    except OSError:
        return None
    return True


def _active_generation(key: str, secret_root: Path) -> bool | None:
    pointer = secret_root / key / "active-secret-generation.json"
    present = _exists(pointer)
    if not present:
        return present
    try:
        generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(generation, str) or "/" in generation or generation in ("", ".", ".."):
        return None
    return _exists(manifest_path(key, generation, root=secret_root))


def read(
    key: str,
    *,
    dns: bool | None,
    slot_root: Path = SLOT_ROOT,
    state_root: Path = bootstrap_state.STATE_ROOT,
    secret_root: Path = SECRET_ROOT,
) -> Readings:
    """Every file reading for one slot; `dns` is the caller's (it runs `dig`)."""
    directory = slot_directory(key, root=slot_root)
    return Readings(
        manifest=_exists(directory / MANIFEST),
        bootstrap_state=_exists(state_root / key / "bootstrap-state.json"),
        secret_generation=_active_generation(key, secret_root),
        dns=dns,
        deployed_document=_exists(deployed_output.deployed_path(key, root=state_root)),
        allocated=_exists(directory / ALLOCATED),
        quarantined=_exists(directory / QUARANTINED),
        consumed=_exists(directory / CONSUMED),
    )


def dns_reading(domain: str, expected_ipv4: str | None) -> tuple[bool | None, str]:
    """`(True, …)` the A record is exactly this host and there is no AAAA;
    `(False, …)` it is not; `(None, …)` it could not be read (D2148)."""
    dig = shutil.which("dig")
    if dig is None:
        return None, "dig is not installed"
    if expected_ipv4 is None:
        return None, "the host manifest declares no host.expected_public_ipv4 to compare with"
    answers: dict[str, list[str]] = {}
    for record in ("A", "AAAA"):
        try:
            done = subprocess.run(  # noqa: S603 -- an argv list of constants and a declared domain
                [dig, f"@{RESOLVER}", "+short", "+time=5", "+tries=2", record, domain],
                capture_output=True,
                text=True,
                check=False,
                timeout=DIG_TIMEOUT_SECONDS,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired) as problem:
            return None, f"dig {record} {domain} did not answer ({type(problem).__name__})"
        if done.returncode != 0:
            return None, f"dig {record} {domain} exited {done.returncode}"
        answers[record] = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    addresses = [line for line in answers["A"] if _IPV4.match(line)]
    if answers["AAAA"]:
        return False, f"{domain} has an AAAA record ({', '.join(answers['AAAA'])}); none is wanted"
    if addresses != [expected_ipv4]:
        shown = ", ".join(answers["A"]) or "no A record"
        return False, f"{domain} resolves to {shown}, not {expected_ipv4} alone"
    return True, f"{domain} A {expected_ipv4}, no AAAA"


def observe(
    host: dict[str, Any],
    *,
    dns: Callable[[str, str | None], tuple[bool | None, str]],
    slot_root: Path = SLOT_ROOT,
    state_root: Path = bootstrap_state.STATE_ROOT,
    secret_root: Path = SECRET_ROOT,
) -> list[dict[str, Any]]:
    """Every declared slot's derived state, in declaration order:
    `{key, domain, region_id, state, reason}`. `dns` is `dns_reading` or a
    proof's stand-in; a DNS reason is carried into the slot's reason whenever
    the DNS reading is what decided it."""
    region = host_config.region(host)
    expected = host["host"].get("expected_public_ipv4")
    rows = []
    for entry in host_config.declared_slots(host):
        answer, dns_reason = dns(entry.domain, expected)
        readings = read(
            entry.key,
            dns=answer,
            slot_root=slot_root,
            state_root=state_root,
            secret_root=secret_root,
        )
        state_word, reason = state(readings)
        if state_word in ("prepared", "undetermined") and answer is not True and "DNS" in reason:
            reason = f"{reason}: {dns_reason}"
        rows.append(
            {
                "key": entry.key,
                "domain": entry.domain,
                "region_id": None if region is None else region.id,
                "state": state_word,
                "reason": reason,
            }
        )
    return rows

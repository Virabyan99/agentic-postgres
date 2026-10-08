#!/usr/bin/env python3
"""Customer slots on this host: prepare one, read them all, revoke a used one (ADR 0257).

Invoked by `sudo bin/slot.sh`. Three verbs, **none of which holds a provider
credential beyond the one `bootstrap-providers` already reads** (D2150):

* `prepare --host F --slot KEY` writes `/etc/agentic-postgres/slots/<KEY>/manifest.yaml`
  (0600, in a 0700 directory) from the host's `slots.defaults`, the slot's
  declaration and the `small` profile, through the product's own
  `config.load_project_manifest`. It refuses a slot that is not declared, is
  already prepared, is occupied, or is consumed. The provider half -- buckets,
  tokens, the Infisical project and identity, the DNS record, the secrets -- is
  the operator's provisioning sheet, which runs the existing commands against
  this manifest; a wrapper that pretended to do the console half would be the
  first fake-complete command.
* `status [--json]` prints every declared slot's derived state and why
  (`agentic_postgres.slot.state`). Exit 0 when every state was determined, 6
  when any is `undetermined` -- never read as ready (ADR 0195).
* `revoke --slot KEY --operator-credential-file F --confirm KEY` revokes the
  Infisical identity of a CONSUMED slot: the bootstrap state its deletion kept
  (D2158) is put back where `bootstrap-providers` reads it, `--destroy` runs,
  and a `revoked` marker records it. The retired copy is never removed.

The DNS reading (D2148): `dig @1.1.1.1` for the slot's A and AAAA records; the A
record must be exactly the host's `host.expected_public_ipv4` and there must be
no AAAA. No `dig`, or no answer, is *could not determine*.

Exit codes:
  0  done; or every slot's state determined
  2  invalid input, or a --confirm that does not match
  3  a prerequisite is missing: root, the host manifest, its slots, a file
  5  refused: the slot is not declared, or not in the state the verb needs
  6  a slot's state could not be determined; or the revocation failed
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from agentic_postgres import (  # noqa: E402
    bootstrap_state,
    config,
    host_config,
    naming,
    slot,
)
from agentic_postgres.config import ManifestError  # noqa: E402
from agentic_postgres.secret_generation import SECRET_ROOT as DEFAULT_SECRET_ROOT  # noqa: E402

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5
EXIT_UNKNOWN = 6

#: The roots this command reads and writes; module globals so a proof can move them.
SLOT_ROOT = slot.SLOT_ROOT
STATE_ROOT = bootstrap_state.STATE_ROOT
SECRET_ROOT = DEFAULT_SECRET_ROOT

#: The DNS reading (D2148) -- `slot.dns_reading`, named here so a proof can
#: replace it on this command alone.
dns_reading = slot.dns_reading
#: `bootstrap-providers --destroy` contacts Infisical; bounded.
REVOKE_TIMEOUT_SECONDS = 300


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: a slot's files, its bootstrap state and its secrets are root's.",
        )


def load_host(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise OperatorError(EXIT_PREREQUISITE, f"host manifest not found: {path}")
    try:
        host = host_config.load_host_manifest(path)
    except (OSError, ValueError) as problem:
        raise OperatorError(EXIT_INPUT, f"the host manifest is refused: {problem}") from problem
    if host_config.slot_defaults(host) is None:
        raise OperatorError(
            EXIT_PREREQUISITE,
            f"{path} declares no slots (host schema 4, `slots`): there is nothing to act on.",
        )
    return host


def declared(host: dict[str, Any], key: str) -> host_config.DeclaredSlot:
    if not slot.SLOT_KEY.fullmatch(key):
        raise OperatorError(EXIT_INPUT, f"not a slot key: {key!r}")
    for entry in host_config.declared_slots(host):
        if entry.key == key:
            return entry
    raise OperatorError(EXIT_REFUSED, f"{key} is not declared in the host manifest's slots.")


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


def prepare(host_path: Path, key: str) -> int:
    require_root()
    host = load_host(host_path)
    entry = declared(host, key)
    directory = slot.slot_directory(key, root=SLOT_ROOT)
    readings = slot.read(
        key, dns=None, slot_root=SLOT_ROOT, state_root=STATE_ROOT, secret_root=SECRET_ROOT
    )
    for flag, why in (
        (readings.consumed, "it is consumed: a deleted project's slot is never reissued"),
        (readings.quarantined, "it is quarantined by an interrupted creation (D2152)"),
        (readings.deployed_document, "a project is deployed under its key"),
        (readings.allocated, "the reconciler has taken it"),
        (readings.manifest, f"it is already prepared ({directory / slot.MANIFEST})"),
    ):
        if flag is None:
            raise OperatorError(EXIT_UNKNOWN, f"cannot prepare {key}: a reading failed ({why})")
        if flag:
            raise OperatorError(EXIT_REFUSED, f"refusing to prepare {key}: {why}. Nothing changed.")

    document = slot.slot_manifest(host, entry)
    SLOT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, delete=False, prefix=".manifest.", suffix=".yaml"
    )
    candidate = Path(handle.name)
    try:
        with handle:
            handle.write(
                f"# Slot {key}, prepared by bin/slot.sh prepare on "
                f"{datetime.now(UTC).isoformat(timespec='seconds')} (ADR 0257).\n"
                "# From the host manifest's slots.defaults and this slot's declaration; no\n"
                "# member is a credential. A creation re-writes `compute` (Run 6).\n"
            )
            yaml.safe_dump(document, handle, sort_keys=False)
        os.chmod(candidate, 0o600)
        # The product's verdict on what was built, before it is installed.
        config.load_project_manifest(candidate)
    except (OSError, ManifestError) as problem:
        candidate.unlink(missing_ok=True)
        raise OperatorError(
            EXIT_REFUSED, f"the slot manifest for {key} is refused by the loader: {problem}"
        ) from problem
    os.replace(candidate, directory / slot.MANIFEST)

    backup = document["backup"]
    print(f"slot: prepared {key} -- {directory / slot.MANIFEST} (0600)")
    print(f"  domain             {entry.domain}")
    print(f"  profile            {document['compute']['profile']}")
    print(f"  backup bucket      {naming.backup_bucket_name(key, backup.get('bucket'))}")
    print(
        "  mirror bucket      "
        f"{naming.backup_mirror_bucket_name(key, backup['mirror'].get('bucket'))}"
    )
    print(f"  Infisical project  {key}  (identity {key}-runtime)")
    print("Next, on the provisioning sheet: the buckets and tokens, the DNS record,")
    print(f"`bootstrap-providers.sh --project {directory / slot.MANIFEST} --plan`, then --apply,")
    print("`materialize-secrets`, and `slot.sh status` until it reads ready.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def status(host_path: Path, *, as_json: bool) -> int:
    require_root()
    host = load_host(host_path)
    rows = slot.observe(
        host, dns=dns_reading, slot_root=SLOT_ROOT, state_root=STATE_ROOT, secret_root=SECRET_ROOT
    )
    if as_json:
        print(json.dumps({"slots": rows}, indent=2))
    elif not rows:
        print("slot: no slot is declared in the host manifest")
    else:
        width = max(len(row["key"]) for row in rows)
        for row in rows:
            print(f"{row['key']:<{width}}  {row['state']:<12}  {row['reason']}")
    undetermined = any(row["state"] == "undetermined" for row in rows)
    return EXIT_UNKNOWN if undetermined else EXIT_OK


# ---------------------------------------------------------------------------
# revoke
# ---------------------------------------------------------------------------


def revoke(host_path: Path, key: str, *, credential: Path, confirm: str) -> int:
    if confirm != key:
        raise OperatorError(
            EXIT_INPUT, f"--confirm must be the slot's key exactly ({key}). Nothing changed."
        )
    require_root()
    if not credential.is_file():
        raise OperatorError(EXIT_PREREQUISITE, f"credential file not found: {credential}")
    host = load_host(host_path)
    declared(host, key)
    directory = slot.slot_directory(key, root=SLOT_ROOT)
    readings = slot.read(
        key, dns=None, slot_root=SLOT_ROOT, state_root=STATE_ROOT, secret_root=SECRET_ROOT
    )
    if readings.consumed is not True:
        raise OperatorError(
            EXIT_REFUSED, f"{key} is not consumed: only a deleted project's slot is revoked."
        )
    retired = directory / slot.RETIRED_STATE
    marker = directory / slot.REVOKED
    if marker.exists():
        raise OperatorError(EXIT_REFUSED, f"{key} was already revoked ({marker}).")
    if not retired.is_file():
        raise OperatorError(
            EXIT_REFUSED, f"{key} kept no bootstrap state ({retired}): there is nothing to revoke."
        )
    manifest = directory / slot.MANIFEST
    if not manifest.is_file():
        raise OperatorError(EXIT_PREREQUISITE, f"the slot manifest is missing: {manifest}")
    live = STATE_ROOT / key / "bootstrap-state.json"
    if live.exists() or live.is_symlink():
        raise OperatorError(
            EXIT_REFUSED,
            f"{live} exists: a project holds this key's bootstrap state; refusing to revoke it.",
        )
    identity = json.loads(retired.read_text(encoding="utf-8")).get("runtime_identity_id")

    # Put the kept state where `bootstrap-providers` reads it -- a copy; the
    # retired file stays the record whatever happens next.
    live.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(live, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(retired.read_bytes())
    command = [
        str(REPO_ROOT / "bin" / "bootstrap-providers.sh"),
        "--host",
        str(host_path),
        "--project",
        str(manifest),
        "--destroy",
        "--confirm",
        key,
        "--operator-credential-file",
        str(credential),
    ]
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=REVOKE_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
        outcome: int | None = done.returncode
        said = (done.stdout or "") + (done.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as problem:
        outcome, said = None, f"{type(problem).__name__}"
    for line in said.strip().splitlines()[-12:]:
        print(f"  {line}")
    if outcome != 0 or live.exists():
        live.unlink(missing_ok=True)
        raise OperatorError(
            EXIT_UNKNOWN,
            f"the revocation of {key} did not complete (bootstrap-providers "
            f"{'did not answer' if outcome is None else f'exited {outcome}'}); the retired "
            f"state is kept at {retired}. Read the provider console before re-running.",
        )
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "revoked_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "runtime_identity_id": identity,
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    print(f"slot: revoked the runtime identity of {key}; recorded in {marker}")
    print("The Infisical project, the buckets, the backup repository and the DNS record stay.")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="slot.sh", add_help=False)
    parser.add_argument("verb", choices=("prepare", "status", "revoke"))
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--slot", dest="key")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--operator-credential-file", type=Path, dest="credential")
    parser.add_argument("--confirm", default="")
    try:
        arguments = parser.parse_args(argv)
    except SystemExit:
        return EXIT_INPUT
    try:
        if arguments.verb == "status":
            if arguments.key or arguments.credential or arguments.confirm:
                raise OperatorError(EXIT_INPUT, "status takes --host and --json only.")
            return status(arguments.host, as_json=arguments.as_json)
        if not arguments.key:
            raise OperatorError(EXIT_INPUT, f"{arguments.verb} needs --slot KEY.")
        if arguments.as_json:
            raise OperatorError(EXIT_INPUT, "--json applies to status only.")
        if arguments.verb == "prepare":
            if arguments.credential or arguments.confirm:
                raise OperatorError(EXIT_INPUT, "prepare takes --host and --slot only.")
            return prepare(arguments.host, arguments.key)
        if arguments.credential is None:
            raise OperatorError(EXIT_INPUT, "revoke needs --operator-credential-file FILE.")
        return revoke(
            arguments.host,
            arguments.key,
            credential=arguments.credential,
            confirm=arguments.confirm,
        )
    except OperatorError as error:
        print(f"slot: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())

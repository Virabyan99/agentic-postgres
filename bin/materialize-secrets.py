#!/usr/bin/env python
"""Write one immutable generation of secret files, then make it active.

Invoked by ``bin/materialize-secrets.sh``, which is the documented entry point.
Split out because the fetch, the write, the fsync and the activation are one
transaction, and a shell script that shelled out per secret would put the
rollback boundary between the write and the activation.

The value path is deliberately short and has no branches: API response ->
Python string -> ``os.write`` to a file descriptor opened ``0o400``. It is never
formatted into a message, never passed to a subprocess, and never returned from
a function that anything logs.

Exit codes match the shell convention: 0 success, 2 invalid input, 3 missing
prerequisite, 8 a secret could not be fetched or written.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from agentic_postgres.bootstrap_state import BootstrapStateError, load_state, state_path
from agentic_postgres.config import load_project_manifest
from agentic_postgres.host_config import load_host_manifest
from agentic_postgres.infisical_client import Credential, InfisicalClient, InfisicalError
from agentic_postgres.naming import project_key as derive_project_key
from agentic_postgres.secret_generation import build_manifest, write_manifest
from agentic_postgres.secrets_contract import (
    SECRET_ROOT,
    active_secrets,
    consumer_directory,
    load_secret_contract,
    secret_source_path,
)

HOST_MANIFEST = Path("/etc/agentic-postgres/host.yaml")
CREDENTIAL_ROOT = Path("/etc/agentic-postgres/credentials")

EXIT_INVALID = 2
EXIT_PREREQUISITE = 3
EXIT_SECRET = 8


class MaterializeError(RuntimeError):
    """Something failed. The message names the secret, never its value."""


def fail(code: int, message: str) -> None:
    print(f"materialize-secrets: {message}", file=sys.stderr)
    raise SystemExit(code)


def generation_id() -> str:
    """A random, unordered generation name.

    Not a timestamp. A timestamp would make generation directories sort into an
    apparent history and invite code that picks "the latest" by name instead of
    reading the active pointer, which is the only thing that actually says which
    generation is in use.
    """
    return secrets.token_hex(8)


def write_secret_file(path: Path, value: str, *, uid: int, gid: int, mode: int) -> None:
    """Create a file that is never readable by anyone but its consumer.

    Opened with the final mode rather than chmod-ed afterwards: between a
    default-mode create and a chmod there is a window in which the value is
    world-readable, and that window is on a host with other processes on it.
    """
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.write(descriptor, value.encode("utf-8"))
        os.fchown(descriptor, uid, gid)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_directory(path: Path) -> None:
    """A rename is only durable once the directory entry itself is synced."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def activate(project_root: Path, generation: str) -> None:
    """Point the project at a generation, atomically.

    Written to a temporary file in the same directory and renamed. A partial
    write here would leave a project with no readable pointer, and the next
    start would have no way to tell which generation was good.
    """
    pointer = project_root / "active-secret-generation.json"
    document = json.dumps({"generation_id": generation}, indent=2, sort_keys=True) + "\n"

    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=project_root, delete=False, prefix=".active."
    )
    try:
        handle.write(document)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()

    staged = Path(handle.name)
    os.chmod(staged, 0o600)
    os.chown(staged, 0, 0)
    staged.replace(pointer)
    fsync_directory(project_root)


def load_credential(key: str) -> Credential:
    directory = CREDENTIAL_ROOT / key
    return Credential.from_files(
        directory / "infisical-client-id",
        directory / "infisical-client-secret",
    )


def plan(key: str, contract: dict[str, Any], session: int) -> int:
    """Report what would be written. Contacts nothing."""
    generation = "<new-generation>"
    print(f"project        {key}")
    print(f"secret root    {SECRET_ROOT}/{key}")
    print(f"generation     {generation}")
    print()
    files = 0
    for secret in active_secrets(contract, session=session):
        for consumer in secret["consumers"]:
            destination = secret_source_path(key, generation, consumer)
            print(
                f"  {secret['name']:<34} -> {destination}  "
                f"({consumer['mode']} {consumer['uid']}:{consumer['gid']})"
            )
            files += 1
    print()
    # The number a rotation has to reach, printed rather than counted in prose
    # (D108). The operator guide's rotation procedure is written against this
    # figure; a number in a document is a number that was right once.
    print(f"{files} files would be written for {len(active_secrets(contract, session))} secrets.")
    print("No provider was contacted and nothing was written.")
    return 0


def materialize(key: str, contract: dict[str, Any], session: int) -> int:
    project_root = Path(SECRET_ROOT) / key
    project_root.mkdir(parents=True, exist_ok=True)
    os.chmod(project_root, 0o700)
    os.chown(project_root, 0, 0)

    generations = project_root / "generations"
    generations.mkdir(exist_ok=True)
    os.chmod(generations, 0o700)

    try:
        host = load_host_manifest(HOST_MANIFEST)
    except (OSError, ValueError) as exc:
        fail(EXIT_PREREQUISITE, f"could not read {HOST_MANIFEST}: {exc}")

    # `infisical` is a top-level sibling of `host`, not a child of it.
    infisical = host["infisical"]

    # The project id, environment and folder come from **bootstrap state**, not
    # from host.yaml. host.yaml describes the host; the Infisical project is a
    # thing bootstrap created for this one project and recorded the id of. That
    # is also the only reading of them that stays correct with two projects on
    # one host, which is the arrangement Session 2 exists to prove.
    try:
        state = load_state(state_path(key))
    except BootstrapStateError as exc:
        fail(
            EXIT_PREREQUISITE,
            f"{exc}. Run bin/bootstrap-providers.sh --apply for {key} first: "
            "there is no recorded provider project to read secrets from.",
        )

    client = InfisicalClient(infisical["api_url"])

    try:
        client.login(load_credential(key))
    except InfisicalError as exc:
        fail(EXIT_PREREQUISITE, f"provider login failed: {exc}")

    generation = generation_id()
    staging = generations / f".{generation}.staging"
    target = generations / generation

    written = 0
    try:
        staging.mkdir(mode=0o700)
        os.chown(staging, 0, 0)

        for secret in active_secrets(contract, session=session):
            try:
                value = client.read_secret(
                    name=secret["provider_key"],
                    project_id=state["infisical_project_id"],
                    environment=state["environment_slug"],
                    secret_path=secret["provider_path"],
                )
            except InfisicalError as exc:
                fail(EXIT_SECRET, f"could not read {secret['name']}: {exc}")

            for consumer in secret["consumers"]:
                # `consumer_directory`, not `consumer["service"]`: a root-plane
                # consumer has no service, and its file lands in `_root/` owned
                # 0:0 -- a directory name no Compose service can have, so the
                # two cannot collide (ADR 0054).
                service_directory = staging / consumer_directory(consumer)
                service_directory.mkdir(mode=0o700, exist_ok=True)
                os.chown(service_directory, consumer["uid"], consumer["gid"])

                write_secret_file(
                    service_directory / consumer["target_file"],
                    value,
                    uid=consumer["uid"],
                    gid=consumer["gid"],
                    mode=int(consumer["mode"], 8),
                )
                written += 1

            # Dropped as soon as it is written. Holding every value until the
            # end would keep them all resident for the whole run for no reason.
            del value

        # Written into the staging directory, so the manifest is part of the
        # generation rather than an annotation added to it afterwards. The
        # deployed document points at this path; without it a deployment claims
        # secrets are ready and names a file that does not exist.
        write_manifest(
            build_manifest(
                project_key=key,
                generation_id=generation,
                secrets=list(active_secrets(contract, session=session)),
            ),
            staging / "manifest.json",
        )

        fsync_directory(staging)
        staging.rename(target)
        fsync_directory(generations)
        activate(project_root, generation)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        client.logout()

    print(f"materialize-secrets: wrote {written} file(s) in generation {generation}")
    print(f"materialize-secrets: {project_root}/active-secret-generation.json now points at it")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True, description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--plan", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.session < 1:
        fail(EXIT_INVALID, "--session must be a positive integer")

    try:
        manifest = load_project_manifest(arguments.project)
        contract = load_secret_contract(arguments.requirements)
    except (OSError, ValueError) as exc:
        fail(EXIT_INVALID, str(exc))

    project = manifest["project"]
    key = derive_project_key(project["slug"], project["environment"])

    if arguments.plan:
        return plan(key, contract, arguments.session)

    if os.geteuid() != 0:
        fail(EXIT_PREREQUISITE, "must run as root")

    # The project manifest's environment is deliberately not passed through: the
    # Infisical environment slug is a provider coordinate recorded by bootstrap,
    # and the two are not required to be the same string.
    return materialize(key, contract, arguments.session)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Allocate, verify, show and release host-loopback database ports (ADR 0042).

The logic is in ``agentic_postgres.port_allocations``, which opens no file and
no socket. What lives here is everything that touches the host: the lock, the
bind probe, and the atomic write.

**The lock covers probe *and* write.** A port that was free when it was probed
and taken when the file was written is precisely the race a lock exists for, and
`deploy.sh` is run by hand — a re-run after a slow first attempt is the normal
operator response, so two of them overlapping is not hypothetical.

**A probe binds, it does not connect.** Asking "can I connect to this port"
answers a different question: nothing listening means the connect fails, which
looks identical to the port being free while something is bound to a different
address on it. `SO_REUSEADDR` is deliberately *not* set, because it would let
the probe succeed against a socket in TIME_WAIT that a container is about to
reclaim.

Exit codes follow the convention (D42):
  0   success
  2   invalid operator input
  3   missing prerequisite, or not root
  4   missing runtime state
  5   the registry is invalid, or the request cannot be satisfied
  6   a check failed
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import config, host_config, port_allocations
from agentic_postgres.port_allocations import AllocationError

EXIT_INVALID = 2
EXIT_PREREQUISITE = 3
EXIT_MISSING_STATE = 4
EXIT_VALIDATION = 5
EXIT_CHECK_FAILED = 6

LOCK_PATH = Path("/run/lock/agentic-postgres-database-ports.lock")


def fail(code: int, message: str) -> int:
    print(f"database-ports: {message}", file=sys.stderr)
    return code


class HostLock:
    """One writer at a time, for the whole probe-and-write sequence.

    `/run/lock` rather than the registry's own directory: a lock file beside the
    thing it protects gets swept up by anything that tidies that directory, and
    `flock` on the registry itself would mean holding an open descriptor on a
    file being replaced by rename.
    """

    def __init__(self, path: Path = LOCK_PATH) -> None:
        self.path = path
        self._handle: Any = None

    def __enter__(self) -> HostLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self._handle.close()
            raise AllocationError(
                f"another database-ports run holds {self.path}. Allocation probes and "
                "writes under one lock; waiting is correct, racing is not"
            ) from error
        return self

    def __exit__(self, *_: object) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()


def bindable(port: int, address: str) -> bool:
    """Can this process bind the port, right now, on the publication address?

    Both families are tried where the address is v6, because a v4-only bind
    proves nothing about `::1`.
    """
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    probe = socket.socket(family, socket.SOCK_STREAM)
    try:
        probe.bind((address, port))
    except OSError as error:
        if error.errno in (errno.EADDRINUSE, errno.EACCES, errno.EADDRNOTAVAIL):
            return False
        raise
    finally:
        probe.close()
    return True


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return port_allocations.empty_registry()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise AllocationError(f"{path} is unreadable or not JSON: {error}") from error
    return port_allocations.validate(document)


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    """Validate, then replace by rename. Never rewritten in place.

    One host-global file whose corruption reaches every project, so the write
    that produces it is the one place worth being careful: a partial write here
    is a registry that a later allocation reads as authoritative.
    """
    port_allocations.validate(registry)
    path.parent.mkdir(parents=True, exist_ok=True)

    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".database-ports.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(registry, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise

    directory = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def access_settings(host_manifest: Path) -> tuple[str, tuple[int, int]]:
    document = host_config.load_host_manifest(host_manifest)
    access = document["database_access"]
    return access["loopback_address"], (access["port_range_start"], access["port_range_end"])


def command_show(arguments: argparse.Namespace) -> int:
    registry = load_registry(arguments.registry)
    allocations = registry["allocations"]
    if arguments.instance_uuid:
        allocation = port_allocations.find(registry, arguments.instance_uuid)
        if allocation is None:
            return fail(EXIT_MISSING_STATE, f"no allocation for {arguments.instance_uuid}")
        allocations = [allocation]

    if not allocations:
        print("no allocations")
        return 0

    print(f"{'project':24} {'state':9} {'pooled':>7} {'direct':>7}  instance")
    for allocation in sorted(allocations, key=lambda a: a["pooled_port"]):
        print(
            f"{allocation['project_key']:24} {allocation['state']:9} "
            f"{allocation['pooled_port']:>7} {allocation['direct_port']:>7}  "
            f"{allocation['instance_uuid']}"
        )
    return 0


def command_allocate(arguments: argparse.Namespace) -> int:
    address, port_range = access_settings(arguments.host)

    with HostLock():
        registry = load_registry(arguments.registry)

        existing = port_allocations.find(registry, arguments.instance_uuid)
        if existing is not None and existing["state"] in port_allocations.LIVE_STATES:
            print(
                f"reusing {existing['state']} allocation: "
                f"pooled {existing['pooled_port']}, direct {existing['direct_port']}"
            )
            return 0

        low, high = port_range
        usable = {port for port in range(low, high + 1) if bindable(port, address)}

        updated, allocation = port_allocations.allocate(
            registry,
            instance_uuid=arguments.instance_uuid,
            project_key=arguments.project_key,
            port_range=port_range,
            usable=usable,
        )
        if not arguments.plan:
            write_registry(arguments.registry, updated)

    verb = "would reserve" if arguments.plan else "reserved"
    print(f"{verb} pooled {allocation['pooled_port']}, direct {allocation['direct_port']}")
    print(f"  on {address}, for {allocation['project_key']} ({allocation['instance_uuid']})")
    if arguments.plan:
        print("Nothing was written.")
    return 0


def command_verify(arguments: argparse.Namespace) -> int:
    """Check what is actually listening, then promote the reservation.

    The check is a *connect*, not a bind: at this point something is supposed to
    be serving, so success means the endpoint answered. That is the opposite of
    the allocation probe, and the two are not interchangeable — which is why
    they are different functions with different names rather than one with a
    flag.
    """
    address, _ = access_settings(arguments.host)

    with HostLock():
        registry = load_registry(arguments.registry)
        allocation = port_allocations.find(registry, arguments.instance_uuid)
        if allocation is None:
            return fail(EXIT_MISSING_STATE, f"no allocation for {arguments.instance_uuid}")

        unreachable = []
        for transport in ("pooled_port", "direct_port"):
            port = allocation[transport]
            try:
                with socket.create_connection((address, port), timeout=5):
                    pass
            except OSError as error:
                unreachable.append(f"{transport.removesuffix('_port')} {port}: {error}")

        if unreachable:
            for line in unreachable:
                print(f"  unreachable: {line}", file=sys.stderr)
            return fail(
                EXIT_CHECK_FAILED,
                f"{allocation['project_key']} has a reservation nothing is serving; "
                "leaving it reserved rather than marking it active",
            )

        if arguments.plan:
            print(f"both transports answer on {address}; would mark active")
            return 0

        write_registry(
            arguments.registry,
            port_allocations.activate(registry, instance_uuid=arguments.instance_uuid),
        )

    print(f"both transports answer on {address}; allocation is active")
    return 0


def command_release(arguments: argparse.Namespace) -> int:
    with HostLock():
        registry = load_registry(arguments.registry)
        updated = port_allocations.release(
            registry,
            instance_uuid=arguments.instance_uuid,
            project_key=arguments.project_key,
        )
        if not arguments.plan:
            write_registry(arguments.registry, updated)

    print(f"{'would release' if arguments.plan else 'released'} {arguments.project_key}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="database-ports.py",
        description="Allocate and verify host-loopback database ports (ADR 0042).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # `--registry` sits on each subcommand rather than before it. argparse
    # accepts a top-level option only ahead of the subcommand, and
    # `show --registry X` is the order anybody would type.
    def registry_option(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--registry", type=Path, default=Path(port_allocations.REGISTRY_PATH))

    def common(sub: argparse.ArgumentParser, *, needs_key: bool) -> None:
        registry_option(sub)
        sub.add_argument("--instance-uuid", required=True, dest="instance_uuid")
        if needs_key:
            sub.add_argument("--project-key", required=True, dest="project_key")
        sub.add_argument("--plan", action="store_true")

    allocate = subparsers.add_parser("allocate", help="reserve two ports for one identity")
    allocate.add_argument("--host", type=Path, required=True)
    common(allocate, needs_key=True)
    allocate.set_defaults(handler=command_allocate)

    verify = subparsers.add_parser("verify", help="check both endpoints, then mark active")
    verify.add_argument("--host", type=Path, required=True)
    common(verify, needs_key=False)
    verify.set_defaults(handler=command_verify)

    release = subparsers.add_parser("release", help="give up two ports, identity confirmed")
    common(release, needs_key=True)
    release.set_defaults(handler=command_release)

    show = subparsers.add_parser("show", help="print the registry")
    registry_option(show)
    show.add_argument("--instance-uuid", dest="instance_uuid", default=None)
    show.set_defaults(handler=command_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except AllocationError as error:
        return fail(EXIT_VALIDATION, str(error))
    except config.ManifestError as error:
        return fail(EXIT_INVALID, str(error))
    except PermissionError as error:
        return fail(EXIT_PREREQUISITE, f"{error}. Allocation writes host state and needs root.")


if __name__ == "__main__":
    raise SystemExit(main())

"""What a deploy read off a running cluster, and how it says it read nothing.

The deployed document's `database.observed` block is the only part of that
document a render cannot produce, so it is the only part that can be wrong in
the way this project keeps producing: a value that looked measured and was not.
Three shapes of that failure are avoidable here and are avoided by construction.

* **`not_observed` is a state, not a zero.** `deployed_output.NOT_OBSERVED`
  carries nulls, and the schema forbids a value beside `status: not_observed`.
  A deployment that interrogated no cluster cannot accidentally publish `{}` and
  have a reader take it for an empty database.
* **Extensions come from `pg_extension`, not `pg_available_extensions`.** What a
  cluster *could* install is not what is installed, and the difference is the
  entire content of DBX-PG-001.
* **Memory is three numbers.** `anon`, `shmem` and `file` are averaged into
  nonsense by any single total: two of them are unreclaimable and one is page
  cache the kernel drops on demand. D52's budget is stated in the same three
  terms, so a single number could not be compared against it at all.

The parsing lives here and the subprocesses live in `bin/deploy-project.py`,
which is what makes any of it testable without a host.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "build_observation",
    "parse_extensions",
    "parse_instance_uuid",
    "parse_memory_stat",
    "parse_server_version",
]

#: Lowercase, matching `port_allocations._UUID` and both schemas. Normalising a
#: mixed-case value here instead would make two spellings of one identity
#: comparable in this module and different in the registry it exists to be
#: matched against, which is a mismatch with no error message.
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

#: cgroup v2 keys, and only these three. `memory.current` is deliberately not
#: read: it is the sum, and the sum is the number that hides which half grew.
_MEMORY_KEYS = {"anon": "anon_mb", "shmem": "shmem_mb", "file": "file_mb"}

_BYTES_PER_MB = 1024 * 1024


def parse_server_version(raw: str) -> str:
    """`SHOW server_version` output, trimmed to what the schema will accept.

    PostgreSQL reports things like `18.1 (Debian 18.1-1.pgdg13+3)`. The build
    suffix is a packaging fact about an image whose digest is already locked, and
    the schema's pattern anchors on a numeric version, so the first token is
    both sufficient and the only part that would survive validation.
    """
    version = raw.strip().split()[0] if raw.strip() else ""
    if not version or not version[0].isdigit():
        raise ValueError(f"not a server version: {raw!r}")
    return version


def parse_extensions(raw: str) -> dict[str, str]:
    """`name version` lines from pg_extension into a mapping.

    An empty result is a real answer -- a cluster with no extensions -- but it
    is not the answer here: `plpgsql` is installed in every database PostgreSQL
    creates, so an empty mapping means the query did not run, and saying so is
    better than publishing `{}`.
    """
    extensions: dict[str, str] = {}
    for line in raw.strip().splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            raise ValueError(f"not an extension row: {line!r}")
        extensions[parts[0]] = parts[1]
    if not extensions:
        raise ValueError("pg_extension returned no rows; plpgsql is always present")
    return extensions


def parse_memory_stat(raw: str) -> dict[str, int]:
    """cgroup v2 `memory.stat` into the three MiB figures the schema names."""
    values: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in _MEMORY_KEYS:
            values[_MEMORY_KEYS[parts[0]]] = int(parts[1]) // _BYTES_PER_MB

    missing = sorted(set(_MEMORY_KEYS.values()) - set(values))
    if missing:
        raise ValueError(f"memory.stat is missing {missing}; this is not cgroup v2 output")
    return values


def parse_instance_uuid(raw: str) -> str:
    """`SELECT instance_uuid FROM app_private.project_identity`, validated.

    The identity the volume carries, and the key the port registry is actually
    keyed by. Validated rather than trusted because it is about to be compared
    against the registry for equality: a value with a trailing newline, a
    different case, or the word `(0 rows)` in it compares unequal to the record
    that describes the same cluster, and the broker's answer to "these do not
    match" is to refuse -- which would be right, about the wrong thing.
    """
    value = raw.strip()
    if not _UUID.match(value):
        raise ValueError(
            f"not a lowercase instance UUID: {raw!r}. The port registry matches on "
            "this string, so a value that is nearly one is worse than none"
        )
    return value


def build_observation(
    *, server_version: str, extensions: str, memory_stat: str, instance_uuid: str
) -> dict[str, Any]:
    """The `observed` block, from four raw command outputs.

    Every member is required and none defaults. A partial observation is not
    published as a whole one: if any of the four could not be read, the caller
    gets an exception and decides, rather than this function quietly filling a
    null into a document whose `status` says `observed`.

    `instance_uuid` joined in version 5 (ADR 0053) and belongs here rather than
    beside the derived members for the reason the whole block exists: it is not
    derivable. It is generated once against an empty volume and recovered on
    every bootstrap since, so it is the one identifier in this system bound to
    the data rather than to the configuration that produced it.
    """
    return {
        "status": "observed",
        "server_version": parse_server_version(server_version),
        "extensions": parse_extensions(extensions),
        "memory": parse_memory_stat(memory_stat),
        "instance_uuid": parse_instance_uuid(instance_uuid),
    }

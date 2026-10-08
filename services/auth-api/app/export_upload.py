"""A project export's upload: stdin into the project's own bucket, one URL out (ADR 0259).

Run by the reconciler inside the project's STORAGE container, never served:

    docker exec -i <storage container> python -m app.export_upload --operation <uuid>

with the `pg_dump -Fc` archive on stdin (D2164). It reads the storage settings
the storage lifespan reads (`storage_client.load_config`: the endpoint, the
bucket, the prefix and the two mounted credential files), writes the archive
ONCE with the adapter's own `put_object` (first-write-only) at
`<prefix>exports/<operation>.dump`, and prints ONE line: a presigned GET valid
`EXPORT_URL_SECONDS`. No credential leaves the container; the URL is the
bounded exception ADR 0259 names, and nothing here logs it.

The adapter is the only provider path (ADR 0124's allowlist is not widened,
D2190): this module never reaches the boto client.

Exit codes: 0 uploaded, the URL printed; 2 invalid input (no operation id, an
empty archive); 3 not the storage mode, or its settings could not be read; 5
the provider refused the write (a second write to the key is its 412).
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from typing import Any, BinaryIO

from app import storage_client
from app.storage_client import R2Adapter, StorageError

#: The download URL's life (D2164): fifteen minutes, read once by its requester.
EXPORT_URL_SECONDS = 900

#: The mode this runs in: the storage container's, whose settings it reads.
STORAGE_MODE = "storage"


def export_key(prefix: str, operation: str) -> str:
    """`<prefix>exports/<operation>.dump`, the operation a canonical uuid."""
    return f"{prefix}exports/{uuid.UUID(operation)}.dump"


def main(
    argv: list[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    environ: dict[str, str] | None = None,
    adapter: Any = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.export_upload", add_help=False)
    parser.add_argument("--operation", required=True)
    try:
        arguments = parser.parse_args(argv)
        operation = str(uuid.UUID(arguments.operation))
    except (SystemExit, ValueError):
        print("export_upload: --operation is one operation id", file=sys.stderr)
        return 2
    env = dict(os.environ if environ is None else environ)
    if env.get("APP_MODE") != STORAGE_MODE:
        print("export_upload: runs in the storage container only", file=sys.stderr)
        return 3
    try:
        config = storage_client.load_config(env)
    except RuntimeError as error:
        print(f"export_upload: {error}", file=sys.stderr)
        return 3
    body = (stdin if stdin is not None else sys.stdin.buffer).read()
    if not body:
        print("export_upload: the archive on stdin is empty", file=sys.stderr)
        return 2
    target = adapter if adapter is not None else R2Adapter(config)
    key = export_key(config.prefix, operation)
    try:
        target.put_object(key, body)
    except StorageError as error:
        print(f"export_upload: {error}", file=sys.stderr)
        return 5
    print(target.presign_get(key, expires_in=EXPORT_URL_SECONDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

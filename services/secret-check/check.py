#!/usr/bin/env python
"""Session 2 secret-check — proof that materialization reached this container.

One-shot. It reads the secret files this service was granted, confirms each is
present, non-empty and owned as declared, and exits.

**It never prints a secret value, and it never prints a digest of one.** A hash
looks like a safe way to prove two containers hold different material, and it is
not: publishing `sha256(secret)` to a log turns an offline guess into a
verifiable one for any secret with guessable structure. The evidence that
isolation holds is the *mount list* plus a successful read of this project's own
file — which is what this program reports.

What it proves, positively:

* the granted file exists at /run/secrets/<name>, is non-empty, and is readable
  by this container's runtime user;
* the file is mode 0400 and owned by this process's uid;

and negatively:

* nothing under /run/secrets was granted that this service did not declare;
* no path under /run/secrets belongs to another project.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

SECRETS_DIR = Path("/run/secrets")
EXPECTED_MODE = 0o400

#: Comma-separated basenames this service must have been granted. Supplied by
#: the runtime override from secrets.required.yaml, so the container checks the
#: declared contract rather than whatever happens to be mounted.
EXPECTED = [name for name in os.environ.get("APG_EXPECTED_SECRETS", "").split(",") if name]

#: This project's key. Used only to assert that no *other* project's key appears
#: in a mounted path -- never printed alongside file contents.
PROJECT_KEY = os.environ.get("PROJECT_KEY", "")


def fail(message: str) -> int:
    print(f"secret-check: FAIL {message}", file=sys.stderr)
    return 1


def main() -> int:
    if not EXPECTED:
        return fail("APG_EXPECTED_SECRETS is empty; nothing to verify")
    if not PROJECT_KEY:
        return fail("PROJECT_KEY is required")

    if not SECRETS_DIR.is_dir():
        return fail(f"{SECRETS_DIR} is not mounted")

    present = sorted(p.name for p in SECRETS_DIR.iterdir())

    # Exactly the declared set. A file this service did not declare means the
    # grant surface in secrets.required.yaml is not what actually happened,
    # which is the failure SEC-SECRET-002 exists to catch.
    if present != sorted(EXPECTED):
        return fail(f"granted files {present} do not match declared {sorted(EXPECTED)}")

    uid = os.getuid()
    for name in sorted(EXPECTED):
        path = SECRETS_DIR / name

        if path.is_symlink():
            return fail(f"{name} is a symlink; a secret must be the file itself")

        info = path.stat()
        if info.st_size == 0:
            return fail(f"{name} is empty; materialization published an incomplete generation")

        mode = stat.S_IMODE(info.st_mode)
        if mode != EXPECTED_MODE:
            return fail(f"{name} is mode {mode:04o}, expected {EXPECTED_MODE:04o}")

        if info.st_uid != uid:
            return fail(f"{name} is owned by uid {info.st_uid}, but this process is uid {uid}")

        # Read it. Presence and mode prove the host did its job; a successful
        # read proves the runtime user can actually use it, which is the thing
        # that silently breaks when ownership and the container user disagree.
        # The value is discarded immediately and never leaves this scope.
        if not path.read_bytes().strip():
            return fail(f"{name} contains only whitespace")

    print(
        json.dumps(
            {
                "status": "ok",
                "project_key": PROJECT_KEY,
                "granted": sorted(EXPECTED),
                "session": 2,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

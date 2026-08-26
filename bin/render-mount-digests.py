#!/usr/bin/env python3
"""Write the digest of what each service bind-mounts, for the files as they are now.

Invoked by ``bin/project-runtime.sh`` immediately before ``compose up``, and by
nothing else. It is a separate command rather than inline Python in the shell
for the reason ``bin/render-secret-override.py`` is: the block it writes is a
document, and building YAML by string concatenation in bash is how an
indentation bug becomes a container that starts wrong.

**Why it exists at all** (D591). ``install_rendered`` ends in
``os.replace(staging, destination)`` -- a new directory with new inodes -- and
``project-runtime up`` runs ``up -d --build --wait`` with no
``--force-recreate``. Compose's config hash covers the service *definition*, and
a bind mount's source path is the identical string on every deploy, so nothing
looks changed and a running container keeps its open handle on a **deleted
inode**. Measured on the host: the installed ``pgbackrest.conf`` was
``-r--r--r--`` dated 06:14 while the running container saw ``-rw------- 0 root
root`` dated 05:36. Three deploys went to that one defect, and two consecutive
correct fixes could not reach it.

Compose hashes labels into the config hash. So a service whose mounted *content*
changed is recreated, and one whose content did not is left alone -- which is
the whole difference between this and ``--force-recreate``, which restarts the
world on every deploy including everything nothing touched.

It reads the runtime override for the mount inventory (derived, never declared)
and the mounted files for their bytes. **No value it reads is written out**: the
output is one hex digest per service and nothing else, which matters because
some of what a service mounts is a credential.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import runtime_override

EXIT_INPUT = 2
EXIT_PRECONDITION = 4


def fail(code: int, message: str) -> None:
    print(f"render-mount-digests: {message}", file=sys.stderr)
    raise SystemExit(code)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--rendered-dir", required=True, type=Path)
    parser.add_argument("--help", "-h", action="store_true", dest="help")
    arguments = parser.parse_args()

    if arguments.help:
        print(__doc__)
        return 0

    rendered_dir: Path = arguments.rendered_dir
    if not rendered_dir.is_dir():
        fail(EXIT_PRECONDITION, f"no rendered directory at {rendered_dir}")

    source = rendered_dir / "runtime-compose.override.yaml"
    if not source.is_file():
        # The runtime override is what names the mounts. Without it there is no
        # inventory to digest, and a project with no override is one that cannot
        # be routed either -- `bin/compose.sh` refuses that separately.
        fail(EXIT_PRECONDITION, f"no runtime override at {source}")

    payload = runtime_override.render_mount_override(source.read_bytes())
    destination = rendered_dir / runtime_override.MOUNT_OVERRIDE_FILENAME

    # The same write discipline as the other two overrides: owner-only, replaced
    # atomically. A half-written document is one Compose either rejects or --
    # worse -- accepts with one service's label missing, which would silently
    # restore exactly the defect this exists to close.
    handle, staging = tempfile.mkstemp(dir=str(rendered_dir), prefix=".mounts-override.")
    with os.fdopen(handle, "wb") as stream:
        stream.write(payload)
    os.chmod(staging, 0o600)
    os.replace(staging, destination)

    services = runtime_override.mounted_paths_by_service(source.read_bytes())
    print(f"render-mount-digests: wrote {destination} ({len(services)} services with bind mounts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

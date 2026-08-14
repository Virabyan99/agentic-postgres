#!/usr/bin/env bash
#
# Resolve or verify the immutable image and version lock.
#
# Two modes with deliberately different trust levels:
#
#   --update  may reach the network. Resolves every candidate to an immutable
#             digest and confirms the declared platform exists in the index.
#   --check   makes no network call at all. Everything it verifies is derivable
#             from two files on disk, so it is safe in CI without registry
#             credentials and cannot pass merely because a registry is up.
#
# The lock format is documented in docs/decisions/0004-version-lock-format.md.
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input
#   3  missing local prerequisite
#   5  lock is invalid, incomplete, or out of sync

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly CANDIDATES="${ROOT_DIR}/versions.in.yaml"
readonly LOCK="${ROOT_DIR}/versions.env"

usage() {
  cat <<'USAGE'
Usage: bin/lock-versions.sh (--update [--packages-only] | --check | --help)

  --update   Resolve every image in versions.in.yaml to an immutable digest
             for the declared target platform and rewrite versions.env.
             Requires Docker Buildx and network access.

             --packages-only  Resolve the `packages:` entries and carry every
             image digest through from the existing versions.env unchanged.
             Needs no Docker and does not re-resolve a tag.

  --check    Verify versions.env is well formed, complete, and in sync with
             versions.in.yaml. Makes no network call. Modifies nothing.
  --help     Show this message.

A release candidate may not depend on a floating tag. If a digest cannot be
resolved for the target platform, that is a blocking condition -- do not
substitute a tag.

Why --packages-only exists (D238, ADR 0083). A plain --update rewrites the
whole file, so adding one package pin also re-resolves ten images -- and four
of them are pinned by tags that move: pgvector:pg18, traefik:v3.7,
node:22-alpine, python:3.12-slim. Session 6 Run 2 measured that coupling and
found no drift on the day. Run 7 added one package and TWO images moved, which
would have shipped an unmeasured PostgreSQL and base-image upgrade inside a run
about authentication. --packages-only makes locking a dependency a change to
the dependency.

It carries a digest forward only when versions.in.yaml still names the same
tagged reference. An image whose candidate has been edited cannot be carried
forward -- the old digest would then describe something nobody asked for -- and
that is a blocking condition rather than a silent re-resolve.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'lock-versions: %s\n' "$*" >&2
  exit "$code"
}

# Reached from bin/session-02-check.sh, which runs as root in host mode, so the
# same PATH problem applies here even though this is a developer tool most of
# the time: sudo resets PATH to secure_path and Ubuntu ships no bare `python`.
# Resolving is cheaper than reasoning about which callers are privileged today.
python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3, python)."
  fi
}

require_python() {
  python_bin >/dev/null
}

update() {
  local packages_only="${1:-no}"

  # Docker is needed only to resolve images. --packages-only touches none, so
  # requiring buildx for it would make the narrow command harder to run than
  # the wide one.
  if [ "${packages_only}" != "yes" ]; then
    command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."
    docker buildx version >/dev/null 2>&1 \
      || die 3 "docker buildx is unavailable; --update cannot resolve digests."
  else
    [ -f "$LOCK" ] \
      || die 2 "--packages-only carries image digests forward from versions.env, which does not exist."
  fi

  "$(python_bin)" - "$CANDIDATES" "$LOCK" "${packages_only}" <<'PY'
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import yaml

candidates_path, lock_path = Path(sys.argv[1]), Path(sys.argv[2])
packages_only = sys.argv[3] == "yes"
spec = yaml.safe_load(candidates_path.read_text(encoding="utf-8"))
platform = spec["target_platform"]


def carried_forward():
    """Every `NAME=reference@digest` already in the lock, by name.

    Read with a plain split rather than by sourcing the file, for the reason
    the lock's own header gives: it is passed to Compose with --env-file and is
    not shell.
    """
    existing = {}
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        existing[name] = value
    return existing


locked = carried_forward() if packages_only else {}

lines = [
    "# GENERATED by bin/lock-versions.sh --update. Do not edit by hand.",
    "# Do not shell-source this file; bin/compose.sh passes it with --env-file.",
    "#",
    "# The digest is authoritative. The tag is retained only so an operator can",
    "# read what the digest refers to.",
    "APG_LOCK_FORMAT=%d" % spec["lock_format"],
    "APG_VERSIONS_IN_SHA256=%s" % sha256(candidates_path.read_bytes()).hexdigest(),
    "APG_LOCKED_AT=%s" % datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "TARGET_PLATFORM=%s" % platform,
    "PYTHON_VERSION=%s" % spec["python"]["version"],
    "COMPOSE_MINIMUM_VERSION=%s" % spec["compose"]["minimum_version"],
]

blocked = []
for name, reference in sorted(spec["images"].items()):
    if packages_only:
        # Carried through byte for byte, and only when the candidate still
        # names the same tagged reference. If versions.in.yaml has been edited
        # to a new tag, the recorded digest describes the OLD image, and
        # writing it under the new tag's name would be a lock that lies -- so
        # that blocks rather than falling back to a re-resolve, which would
        # reintroduce exactly the coupling this flag exists to remove.
        previous = locked.get(name)
        if previous is None:
            blocked.append(f"{name}: absent from versions.env; --packages-only cannot carry it forward")
        elif previous.rsplit("@", 1)[0] != reference:
            blocked.append(
                f"{name}: versions.in.yaml now names {reference!r} but the lock holds "
                f"{previous.rsplit('@', 1)[0]!r}; run --update without --packages-only"
            )
        else:
            print(f"  carried  {name} -> {previous.rsplit('@', 1)[-1]}", file=sys.stderr)
            lines.append(f"{name}={previous}")
        continue

    proc = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", reference,
         "--format", "{{json .Manifest}}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        blocked.append(f"{name}: cannot resolve {reference}")
        continue

    manifest = json.loads(proc.stdout)
    digest = manifest["digest"]
    entries = manifest.get("manifests") or []
    platforms = {
        f"{m['platform']['os']}/{m['platform']['architecture']}"
        for m in entries if "platform" in m
    }
    if platforms and platform not in platforms:
        blocked.append(f"{name}: {reference} has no {platform} (has {sorted(platforms)})")
        continue

    print(f"  resolved {name} -> {digest}", file=sys.stderr)
    lines.append(f"{name}={reference}@{digest}")

# Packages, dereferenced (ADR 0077). A `packages:` entry used to be copied
# through as a string, which is how a version that never existed survived four
# sessions of a green lock check (D201). Each entry now names its registry and
# its package, and resolves to the digest of exactly one published artifact: the
# sdist on PyPI, the tarball on npm. A fictional version cannot be locked,
# because there is no artifact to name.
def resolve_package(name, entry):
    registry, package, version = entry["registry"], entry["package"], entry["version"]

    if registry == "pypi":
        url = f"https://pypi.org/pypi/{package}/{version}/json"
    elif registry == "npm":
        url = f"https://registry.npmjs.org/{package.replace('/', '%2f')}/{version}"
    else:
        return None, f"{name}: unknown registry {registry!r}"

    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            document = json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, (
                f"{name}: {registry} has no {package} {version}. The version does not "
                "exist; this is D201's condition and it blocks"
            )
        return None, f"{name}: {registry} returned HTTP {error.code} for {package} {version}"
    except OSError as error:
        return None, f"{name}: cannot reach {registry} ({error})"

    if registry == "pypi":
        # The sdist: exactly one per release, and what every wheel is built
        # from. Choosing among wheels would make the lock record a preference;
        # the sdist makes it record a fact.
        sdists = [f for f in document.get("urls", []) if f.get("packagetype") == "sdist"]
        if len(sdists) != 1:
            return None, (
                f"{name}: {package} {version} publishes {len(sdists)} sdists; the lock "
                "records one canonical artifact per version and cannot choose"
            )
        return f"sha256:{sdists[0]['digests']['sha256']}", None

    dist = document.get("dist") or {}
    integrity = dist.get("integrity")
    if not integrity or "-" not in integrity:
        return None, f"{name}: {package} {version} publishes no dist.integrity"
    algorithm, value = integrity.split("-", 1)
    return f"{algorithm}:{value}", None


for name, entry in sorted(spec["packages"].items()):
    digest, problem = resolve_package(name, entry)
    if problem is not None:
        blocked.append(problem)
        continue
    print(f"  resolved {name} -> {digest[:24]}...", file=sys.stderr)
    lines.append(f"{name}={entry['version']}")
    lines.append(f"{name}_DIGEST={digest}")

# Feature floors, plus the resolved version each is compared against. The
# resolved version comes from the *tag* rather than from a registry label,
# because the tag is what versions.in.yaml selects and what a reviewer reads.
# `v3.5` -> `3.5`.
for floor_name, minimum in sorted(spec.get("feature_floors", {}).items()):
    prefix = floor_name[: -len("_MINIMUM_VERSION")]
    reference = spec["images"].get(f"{prefix}_IMAGE")
    if reference is None:
        blocked.append(f"{floor_name}: no matching {prefix}_IMAGE in versions.in.yaml")
        continue
    tag = reference.rsplit(":", 1)[-1].lstrip("vV")
    if not tag or not tag[0].isdigit():
        blocked.append(f"{floor_name}: {prefix}_IMAGE tag {tag!r} is not a version")
        continue
    lines.append(f"{floor_name}={minimum}")
    lines.append(f"{prefix}_VERSION={tag}")

if blocked:
    # One message for two kinds of blockage, so it names the rule rather than
    # one instance of it: an image that will not resolve must not be replaced by
    # a floating tag, and a package version that will not resolve must not be
    # written down anyway. The second half is D201.
    print("lock-versions: BLOCKED. Nothing is written. A reference that cannot be",
          file=sys.stderr)
    print("resolved is not locked by recording it: not a floating tag for an image,",
          file=sys.stderr)
    print("and not a bare version string for a package.", file=sys.stderr)
    for item in blocked:
        print(f"  {item}", file=sys.stderr)
    raise SystemExit(5)

# Atomic replacement, same directory so the rename cannot cross filesystems.
handle, temporary = tempfile.mkstemp(dir=lock_path.parent, prefix=".versions.env.")
with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
    stream.write("\n".join(lines) + "\n")
os.chmod(temporary, 0o644)
os.replace(temporary, lock_path)
how = "carried forward" if packages_only else "resolved"
print(
    f"lock-versions: wrote {lock_path.name} ({len(spec['images'])} images {how})",
    file=sys.stderr,
)
PY
}

check() {
  "$(python_bin)" - "$CANDIDATES" "$LOCK" <<'PY'
import re
import sys
from hashlib import sha256
from pathlib import Path

import yaml

candidates_path, lock_path = Path(sys.argv[1]), Path(sys.argv[2])
problems: list[str] = []

if not lock_path.is_file():
    print("lock-versions: versions.env is missing; run --update", file=sys.stderr)
    raise SystemExit(5)

KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
IMAGE = re.compile(
    r"^(?P<repo>[a-z0-9.\-]+(?::\d+)?/[a-z0-9._/\-]+)"
    r":(?P<tag>[A-Za-z0-9._\-]+)"
    r"@sha256:(?P<digest>[0-9a-f]{64})$"
)
FLOATING = {"latest", "main", "master", "edge", "stable", "nightly", "dev", "test"}

# 1. Parse strictly. Duplicate keys and malformed lines are rejected outright.
values: dict[str, str] = {}
for number, raw in enumerate(lock_path.read_text(encoding="utf-8").splitlines(), start=1):
    line = raw.rstrip("\n")
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        problems.append(f"line {number}: not a KEY=VALUE assignment: {line!r}")
        continue
    key, value = line.split("=", 1)
    if not KEY.match(key):
        problems.append(f"line {number}: invalid variable name {key!r}")
        continue
    if key in values:
        problems.append(f"line {number}: duplicate variable {key!r}")
        continue
    if value != value.strip() or value.startswith(("'", '"')):
        problems.append(f"line {number}: {key} value must be unquoted and untrimmed")
    values[key] = value

spec = yaml.safe_load(candidates_path.read_text(encoding="utf-8"))

# 2. The candidate file's digest. This alone catches any edit to versions.in.yaml.
expected_digest = sha256(candidates_path.read_bytes()).hexdigest()
if values.get("APG_VERSIONS_IN_SHA256") != expected_digest:
    problems.append(
        "versions.in.yaml has changed since the lock was generated "
        f"(recorded {values.get('APG_VERSIONS_IN_SHA256', '<absent>')[:16]}..., "
        f"actual {expected_digest[:16]}...); run --update"
    )

# 3. Required metadata.
for required in ("APG_LOCK_FORMAT", "APG_LOCKED_AT", "TARGET_PLATFORM",
                 "PYTHON_VERSION", "COMPOSE_MINIMUM_VERSION"):
    if required not in values:
        problems.append(f"missing required lock variable {required}")

platform = spec["target_platform"]
if values.get("TARGET_PLATFORM") != platform:
    problems.append(
        f"TARGET_PLATFORM is {values.get('TARGET_PLATFORM')!r}, "
        f"versions.in.yaml declares {platform!r}"
    )

if values.get("PYTHON_VERSION") != spec["python"]["version"]:
    problems.append("PYTHON_VERSION does not match versions.in.yaml")

pinned = (Path(candidates_path.parent / ".python-version").read_text(encoding="utf-8").strip())
if values.get("PYTHON_VERSION") != pinned:
    problems.append(f"PYTHON_VERSION {values.get('PYTHON_VERSION')!r} != .python-version {pinned!r}")

# 4. Every candidate image is locked, with a matching repository and tag.
for name, reference in sorted(spec["images"].items()):
    locked = values.get(name)
    if locked is None:
        problems.append(f"{name} is declared in versions.in.yaml but absent from versions.env")
        continue

    match = IMAGE.match(locked)
    if match is None:
        problems.append(f"{name} is not registry/repo:tag@sha256:<64 lowercase hex>: {locked!r}")
        continue
    if match.group("tag").lower() in FLOATING:
        problems.append(f"{name} uses the floating tag {match.group('tag')!r}")
    if locked.rsplit("@", 1)[0] != reference:
        problems.append(
            f"{name} locks {locked.rsplit('@', 1)[0]!r} but versions.in.yaml "
            f"selects {reference!r}; run --update"
        )
    if "/" not in reference.split(":", 1)[0]:
        problems.append(f"{name} repository is not fully qualified: {reference!r}")

# 4c. Packages, and the half of ADR 0077 that runs offline. `--check` cannot
#     reach a registry -- deliberately, so it cannot pass merely because one is
#     up -- so what it verifies is that a digest is *present and well formed*.
#     That is not proof the artifact exists today; it is proof that whoever ran
#     `--update` found one, which a copied version string could never be.
DIGEST = re.compile(r"^(sha256|sha512):[A-Za-z0-9+/=_\-]{32,}$")
REGISTRIES = ("pypi", "npm")

for name, entry in sorted(spec["packages"].items()):
    if not isinstance(entry, dict):
        problems.append(
            f"{name} is a bare version string. Since lock format 2 a package declares "
            "its registry and package name so the lock can dereference it (ADR 0077)"
        )
        continue

    missing = {"registry", "package", "version"} - set(entry)
    if missing:
        problems.append(f"{name} is missing {sorted(missing)} in versions.in.yaml")
        continue
    if entry["registry"] not in REGISTRIES:
        problems.append(f"{name} declares registry {entry['registry']!r}, not one of {REGISTRIES}")

    if values.get(name) != str(entry["version"]):
        problems.append(f"{name} does not match versions.in.yaml")

    digest_name = f"{name}_DIGEST"
    digest = values.get(digest_name)
    if digest is None:
        problems.append(
            f"{digest_name} is absent from versions.env. A package version with no artifact "
            "digest is a string nothing dereferenced, which is D201; run --update"
        )
    elif not DIGEST.match(digest):
        problems.append(f"{digest_name} is not <algorithm>:<value>: {digest!r}")


def as_version(text):
    """`3.5` -> (3, 5). Non-numeric components sort as 0 rather than raising."""
    parts = []
    for component in str(text).split("."):
        digits = "".join(c for c in component if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


# 4b. Feature floors. Offline and comparative: it cannot prove the locked image
#     supports a configuration key, but it does prove nobody lowered the version
#     below the one that does. The live-host sentinel test is the actual proof.
for floor_name, minimum in sorted(spec.get("feature_floors", {}).items()):
    prefix = floor_name[: -len("_MINIMUM_VERSION")]
    resolved_name = f"{prefix}_VERSION"

    if values.get(floor_name) != str(minimum):
        problems.append(f"{floor_name} does not match versions.in.yaml; run --update")
        continue

    resolved = values.get(resolved_name)
    if resolved is None:
        problems.append(f"{resolved_name} is absent from versions.env; run --update")
        continue

    locked_image = values.get(f"{prefix}_IMAGE", "")
    tag = locked_image.rsplit("@", 1)[0].rsplit(":", 1)[-1].lstrip("vV")
    if tag != resolved:
        problems.append(
            f"{resolved_name} is {resolved!r} but {prefix}_IMAGE is tagged {tag!r}; run --update"
        )
        continue

    if as_version(resolved) < as_version(minimum):
        problems.append(
            f"{prefix} is locked at {resolved} but {floor_name} requires {minimum}: "
            "the locked version does not support a feature this deployment depends on"
        )

# 5. No image variable may exist in the lock that the candidate file does not
#    declare -- otherwise a stale entry survives a deliberate removal.
declared = set(spec["images"]) | set(spec["packages"])
declared |= {f"{name}_DIGEST" for name in spec["packages"]}
declared |= set(spec.get("feature_floors", {}))
declared |= {
    f"{name[: -len('_MINIMUM_VERSION')]}_VERSION" for name in spec.get("feature_floors", {})
}
metadata = {"APG_LOCK_FORMAT", "APG_VERSIONS_IN_SHA256", "APG_LOCKED_AT",
            "TARGET_PLATFORM", "PYTHON_VERSION", "COMPOSE_MINIMUM_VERSION"}
for name in sorted(set(values) - declared - metadata):
    problems.append(f"{name} is in versions.env but not declared in versions.in.yaml")

if problems:
    print("lock-versions: the version lock is not valid:", file=sys.stderr)
    for item in problems:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(5)

print(f"lock-versions: versions.env is current ({len(spec['images'])} images, "
      f"platform {platform}).")
PY
}

main() {
  if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    usage >&2
    die 2 "exactly one of --update, --check, or --help is required."
  fi

  case "$1" in
    --help) [ "$#" -eq 1 ] || die 2 "--help takes no argument."; usage; return 0 ;;
    --update)
      require_python
      [ -f "$CANDIDATES" ] || die 2 "missing ${CANDIDATES}"
      case "${2:-}" in
        "") update no ;;
        --packages-only) update yes ;;
        *) usage >&2; die 2 "unknown argument: $2" ;;
      esac
      ;;
    --check)
      [ "$#" -eq 1 ] || die 2 "--check takes no argument."
      require_python
      [ -f "$CANDIDATES" ] || die 2 "missing ${CANDIDATES}"
      check
      ;;
    *) usage >&2; die 2 "unknown argument: $1" ;;
  esac
}

main "$@"

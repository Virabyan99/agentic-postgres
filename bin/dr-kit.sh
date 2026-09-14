#!/usr/bin/env bash
#
# The disaster kit (ADR 0189): what an operator holds OFF the host, so that a
# replacement can be built and adopted on the day this host is gone.
#
#   export   Write a kit: the host and capability manifests and, per project,
#            the project manifest, bootstrap-state.json, the deployed document
#            and secrets.txt -- every secret's NAME, provider path and origin,
#            and no value. Root, because the state and the document are
#            root-owned on a host.
#   verify   Check a kit is whole: every artifact present with the digest it
#            was exported with, every manifest loading, every project directory
#            naming the project it holds. No root.
#
# What is NOT in a kit, by construction: a secret value, a credential file, a
# token. Where each value lives is what secrets.txt says. An operator who wants
# a value in the kit is asking for a second secret store with no rotation, no
# audit and no owner (ADR 0189).
#
# Exit codes (runbook section 2 convention):
#   0  the kit was written, or verified
#   2  invalid operator input
#   3  a prerequisite is missing, or export without root
#   5  the kit does not verify

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
       --output DIR --project project.alpha.yaml [--project project.beta.yaml ...]
  bin/dr-kit.sh verify DIR

`export` takes one `--project` per project, repeated, and at least one.
`verify` takes none and refuses one -- the flag belongs to `export` alone, which
is why it is written on `export`'s own line and never as an option block entry
of this command's (D1316). A line whose first word is `--project` reads as a
flag the command takes in every mode, and `bin/apg.sh` derives its APG_PROJECT
default by looking for exactly that; `dr-kit verify` would then be handed a flag
it refuses. So `dr-kit` takes no default project, deliberately.

The kit is written into DIR, which must not exist, owner-only. Copy it off the
host afterwards: it is the operator's, and docs/node-loss-runbook.md is the
order it is used in.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'dr-kit: %s\n' "$*" >&2
  exit "$code"
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3)."
  fi
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "a verb is required: export or verify."
  fi
  case "$1" in
    --help | -h) usage; return 0 ;;
    export)
      # Root unless the operator points --state-root somewhere readable (a
      # proof does; a host never). The Python side reports an unreadable
      # state as a prerequisite failure rather than an absent project.
      if [ "$(id -u)" -ne 0 ] && ! printf '%s\n' "$@" | grep -q -- '^--state-root$'; then
        die 3 "export needs root: the bootstrap state and the deployed document are root-owned."
      fi
      ;;
    verify) ;;
    *) usage >&2; die 2 "unknown verb: $1 (export or verify)." ;;
  esac
  PYTHONPATH="${ROOT_DIR}/src" exec "$(python_bin)" "${ROOT_DIR}/bin/dr-kit.py" "$@"
}

main "$@"

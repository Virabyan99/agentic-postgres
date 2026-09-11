#!/usr/bin/env bash
#
# A project's own agent surface: scaffold one capability entry (ADR 0201).
#
#   init      Stream ONE capability entry to standard output, derived from the
#             merged reviewed surface -- the same operations table the compiler
#             resolves against, so the scaffold cannot express what the
#             compiler cannot emit (D1137). Writes no file: redirect it
#             yourself, as yourself, and READ it before it is reviewed.
#
# There is exactly one verb here, and the other three an adopter looks for
# already live where they belong (D707: renaming a surface buys nothing):
#
#   validate  bin/mcp-contract.sh check --project FILE
#   test      bin/render-evaluation-report.py --check --project FILE
#   dry-run   the runtime's own, per call (ADR 0182)
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input, including an operation the surface does not name
#   3  missing local prerequisite
#   5  a manifest or surface that does not load

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/agent.sh init --project FILE --operation NAME [--relation NAME] [--kind read|write]
       bin/agent.sh init --head

  init               Scaffold one capability entry for the project's own
                     capability manifest (projects/<slug>/capabilities.yaml)
                     and stream it to standard output. A relation scaffolds a
                     read grouped under query_resource; a reviewed RPC
                     scaffolds a write with every argument redacted and
                     approval required.
  --project FILE     The project manifest; its migrations.set names the
                     reviewed surface the entry is derived from.
  --operation NAME   A relation or RPC the merged reviewed surface names. One
                     it does not name is refused, with the ones it does.
  --relation NAME    For a write: the relation whose write scope the entry
                     requires. A write's scope is a review decision, so the
                     scaffold takes it and never guesses it.
  --kind read|write  Optional; may only confirm the kind the object derives.
  --head             Print the manifest's fixed head (the schema modeline,
                     schema_version, capabilities:) instead of an entry.
  --help             Show this message.

A manifest is `init --head > projects/<slug>/capabilities.yaml`, then one
`init --operation ... >> the same file` per entry. Validate it with
`bin/mcp-contract.sh check --project FILE`; compile its contract with
`bin/mcp-contract.sh compile --project FILE > projects/<slug>/contracts/mcp-capabilities.canonical.json`.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'agent: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible to a privileged call (D80).
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

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "the verb init is required."
  fi

  local command=""
  local -a arguments=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      init)
        [ -z "${command}" ] || die 2 "only one verb at a time."
        command="$1"
        shift
        ;;
      --project|--operation|--relation|--kind)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        if [ "$1" = "--project" ]; then
          [ -f "$2" ] || die 2 "project manifest not found: $2"
        fi
        arguments+=("$1" "$2")
        shift 2
        ;;
      --head)
        arguments+=("$1")
        shift
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${command}" ] || die 2 "the verb init is required."

  exec "$(python_bin)" "${ROOT_DIR}/bin/agent.py" "${command}" "${arguments[@]+"${arguments[@]}"}"
}

main "$@"

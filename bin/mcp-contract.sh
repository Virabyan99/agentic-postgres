#!/usr/bin/env bash
#
# Compile or compare the agent capability contract (ADR 0119, ADR 0120).
#
# bin/api-contract.sh's shape, applied to the agent surface, and for its reason
# (ADR 0050): a gate that can approve its own subject is not a gate.
#
#   compile   Compile the capability manifest against the reviewed API surface
#             and the approved OpenAPI snapshot, and STREAM the candidate to
#             standard output. It writes no file. There is no output-path option
#             and that is the design: the redirect happens in the caller's own
#             shell, so a candidate lands where a human has to read it before
#             committing it.
#
#   check     Compare, and have no code path that writes a contract at all. It
#             compiles the committed manifest and compares the result
#             byte-for-byte against the committed contract. The gate runs only
#             this, and it needs no host, no root and no network.
#
#   lock      Resolve the approved contract for one project, from that project's
#             rendered outputs. Also stdout-only, for compile's reason.
#
# The compiler READS the OpenAPI document and never enumerates from it. Every
# question starts from a declared capability; nothing iterates the served paths
# looking for things to expose. That asymmetry is AGT-DRIFT-001, and adding an
# API operation must therefore expose nothing.
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input
#   3  missing local prerequisite
#   5  the contracts are out of sync, or no approved contract exists yet

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/mcp-contract.sh check [--capabilities FILE] [--project FILE]
       bin/mcp-contract.sh compile [--capabilities FILE] > candidate.json
       bin/mcp-contract.sh lock --outputs FILE --project FILE [--capabilities FILE] > lock.json

  check              Compare. Never writes. Compiles the manifest against the
                     reviewed API surface and the approved OpenAPI snapshot, and
                     compares the result against the committed contract. With
                     --project, also applies that project's mcp.profile to the
                     approved contract and exits 5 if it would widen any bound
                     (ADR 0183): a profile is refused here, at compile time.
  compile            Compile a candidate and stream it to standard output.
                     Writes no file; redirect it yourself, as yourself.
  lock               Resolve the approved contract for one project and stream
                     the deployed lock to standard output. The project's
                     mcp.profile narrows it; a version 1 manifest declares none
                     and compiles the lock it always did.
  --capabilities FILE
                     The capability manifest. Defaults to
                     capabilities.example.yaml, which is the reviewed set; a
                     host passes its own capabilities.yaml.
  --outputs FILE     A rendered outputs.json, for `lock`. The upstream address
                     is read from routes.rest rather than rebuilt, so this never
                     becomes a second derivation of an address naming owns.
  --project FILE     The project manifest. Optional for `check`; REQUIRED for
                     `lock`, so a deploy cannot compile a lock that ignores a
                     profile and report success.
  --help             Show this message.

The contract is a generated artifact. It cannot be written by hand and `check`
will refuse one that has been: re-compile it instead.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'mcp-contract: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible to a privileged call. This is the trap five
# Session 2 scripts walked into and the Session 1 gate walked into again (D80).
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
    die 2 "one of check, compile or lock is required."
  fi

  local command=""
  local capabilities=""
  local outputs=""
  local project=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      check|compile|lock)
        [ -z "${command}" ] || die 2 "only one command at a time."
        command="$1"
        shift
        ;;
      --capabilities)
        [ "$#" -ge 2 ] || die 2 "--capabilities requires a file."
        capabilities="$2"
        shift 2
        ;;
      --outputs)
        [ "$#" -ge 2 ] || die 2 "--outputs requires a file."
        outputs="$2"
        shift 2
        ;;
      --project)
        [ "$#" -ge 2 ] || die 2 "--project requires a file."
        project="$2"
        shift 2
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${command}" ] || die 2 "one of check, compile or lock is required."
  if [ "${command}" = "lock" ] && [ -z "${outputs}" ]; then
    die 2 "lock requires --outputs."
  fi
  # Required rather than defaulted (ADR 0183): a lock compiled without the
  # project's profile is a lock that ignores it, and it would report success.
  if [ "${command}" = "lock" ] && [ -z "${project}" ]; then
    die 2 "lock requires --project: the project's mcp.profile narrows the lock."
  fi
  if [ "${command}" = "compile" ] && [ -n "${project}" ]; then
    die 2 "compile takes no --project: the canonical contract is project-neutral."
  fi

  local -a arguments=()
  if [ -n "${capabilities}" ]; then
    [ -f "${capabilities}" ] || die 2 "capability manifest not found: ${capabilities}"
    arguments+=(--capabilities "${capabilities}")
  fi
  arguments+=("${command}")
  if [ -n "${outputs}" ]; then
    [ -f "${outputs}" ] || die 2 "rendered outputs not found: ${outputs}"
    arguments+=(--outputs "${outputs}")
  fi
  if [ -n "${project}" ]; then
    [ -f "${project}" ] || die 2 "project manifest not found: ${project}"
    arguments+=(--project "${project}")
  fi

  exec "$(python_bin)" "${ROOT_DIR}/bin/mcp-contract.py" "${arguments[@]}"
}

main "$@"

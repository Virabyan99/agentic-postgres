#!/usr/bin/env bash
#
# Canonical operator entry point (runbook §2 "Canonical deploy.sh grammar").
#
#   ./deploy.sh --project <project.yaml> --capabilities <capabilities.yaml> --render-only
#
# During Session 1 --render-only is mandatory. Invoking this script without it
# is not a mistake to be corrected silently: deployment genuinely begins in a
# later session, so the script exits 10 and says so.
#
# Exit codes (runbook §2 convention):
#   0   success
#   2   invalid operator input or manifest
#   3   missing local prerequisite
#   5   contract, lock, collision, or generated-output validation failure
#   10  capability intentionally unavailable in the current session

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: ./deploy.sh --project FILE --capabilities FILE --render-only
       sudo ./deploy.sh --host FILE --project FILE --capabilities FILE \
            --through-session 2

  --project FILE       Path to a project manifest (non-secret).
  --capabilities FILE  Path to a capability manifest (non-secret).
  --host FILE          Path to the host manifest. Required to deploy.
  --render-only        Validates inputs, stages outputs, validates the Compose
                       model, publishes the staged set atomically, and starts
                       no services. Needs no root and no host.
  --through-session N  Deploy everything up to and including session N. Needs
                       root and a provisioned host.
  --help               Show this message.

--render-only remains the whole of what runs in a checkout: it starts no
container, provisions no provider and opens no database connection.

--through-session expects the host to be ready already. It does not bring up
the edge plane, bootstrap providers, or materialize secrets -- those are
bin/edge.sh, bin/bootstrap-providers.sh and bin/materialize-secrets.sh, run in
that order first. A deploy that silently performed them would make its own
preconditions, and a failure halfway would leave nobody able to say which half.

Never pass a secret value as a command-line argument.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'deploy: %s\n' "$*" >&2
  exit "$code"
}

main() {
  local project="" capabilities="" host="" render_only=0 through_session=""

  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "no arguments given."
  fi

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help)
        usage
        return 0
        ;;
      --render-only)
        render_only=1
        shift
        ;;
      --project)
        [ "$#" -ge 2 ] || die 2 "--project requires a file path."
        project="$2"
        shift 2
        ;;
      --capabilities)
        [ "$#" -ge 2 ] || die 2 "--capabilities requires a file path."
        capabilities="$2"
        shift 2
        ;;
      --project=*)
        project="${1#--project=}"
        shift
        ;;
      --capabilities=*)
        capabilities="${1#--capabilities=}"
        shift
        ;;
      --host)
        [ "$#" -ge 2 ] || die 2 "--host requires a file path."
        host="$2"
        shift 2
        ;;
      --host=*)
        host="${1#--host=}"
        shift
        ;;
      --through-session)
        # -n as well as $#: an empty value is a malformed argument, not an
        # absent one, and falling through to "nothing to do" would answer a
        # question the operator plainly did not ask.
        [ "$#" -ge 2 ] && [ -n "$2" ] || die 2 "--through-session requires a session number."
        through_session="$2"
        shift 2
        ;;
      --through-session=*)
        through_session="${1#--through-session=}"
        [ -n "${through_session}" ] || die 2 "--through-session requires a session number."
        shift
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${project}" ] || die 2 "--project is required."
  [ -n "${capabilities}" ] || die 2 "--capabilities is required."

  # Manifest paths are given relative to the caller's cwd, so absolutize them
  # before changing directory. Everything after this point runs from the
  # repository root regardless of where the operator invoked the script.
  case "${project}" in /*) ;; *) project="${PWD}/${project}" ;; esac
  case "${capabilities}" in /*) ;; *) capabilities="${PWD}/${capabilities}" ;; esac
  [ -n "${host}" ] && case "${host}" in /*) ;; *) host="${PWD}/${host}" ;; esac
  cd "${ROOT_DIR}"

  if [ "${render_only}" -eq 1 ] && [ -n "${through_session}" ]; then
    die 2 "--render-only and --through-session ask for different things; pass one."
  fi

  if [ "${render_only}" -ne 1 ] && [ -z "${through_session}" ]; then
    die 10 "nothing to do: pass --render-only, or --through-session N to deploy."
  fi

  if [ -n "${through_session}" ]; then
    case "${through_session}" in
      ''|*[!0-9]*) die 2 "--through-session takes a session number, got: ${through_session}" ;;
    esac
    # Refused rather than clamped. Clamping to what this release can do would
    # deploy less than the operator asked for and report success.
    [ "${through_session}" -le 2 ] \
      || die 10 "this release deploys through session 2; asked for ${through_session}."
    [ -n "${host}" ] || die 2 "--through-session requires --host."
    [ -f "${host}" ] || die 2 "host manifest not found: ${host}"

    command -v python3 >/dev/null 2>&1 || [ -x "${ROOT_DIR}/.venv/bin/python" ] \
      || die 3 "no Python interpreter found."

    [ -f "${project}" ] || die 2 "project manifest not found: ${project}"
    [ -f "${capabilities}" ] || die 2 "capability manifest not found: ${capabilities}"

    [ "$(id -u)" -eq 0 ] || die 3 "--through-session requires root: it writes host state."

    exec "${ROOT_DIR}/bin/deploy-session-2.py" \
      --host "${host}" \
      --project "${project}" \
      --capabilities "${capabilities}"
  fi

  # Step 4 of the runbook §11 order: verify local prerequisites before doing
  # anything that could touch generated state.
  command -v python >/dev/null 2>&1 \
    || die 3 "python is not on PATH. Activate the repository virtual environment."

  [ -f "${project}" ] || die 2 "project manifest not found: ${project}"
  [ -f "${capabilities}" ] || die 2 "capability manifest not found: ${capabilities}"

  # Steps 5-15 are one transaction and belong in one process. Splitting them
  # across shell and Python would put the rollback boundary in the wrong place.
  exec python "${ROOT_DIR}/bin/render-config.py" \
    --project "${project}" \
    --capabilities "${capabilities}" \
    --render
}

main "$@"

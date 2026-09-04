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

# The highest session this release can deploy, read from the package rather
# than declared here. One value, one place: the gate already fails when the
# tree's implementations and CURRENT_SESSION disagree, so binding this to the
# same constant means a release cannot be asked to deploy a session it does not
# implement, and cannot refuse one it does.
max_deployable_session() {
  "$(python_bin)" -c '
import sys
sys.path.insert(0, sys.argv[1] + "/src")
from agentic_postgres import CURRENT_SESSION
print(CURRENT_SESSION)
' "${ROOT_DIR}"
}

usage() {
  cat <<'USAGE'
Usage: ./deploy.sh --project FILE --capabilities FILE --render-only
       sudo ./deploy.sh --host FILE --project FILE --capabilities FILE \
            --through-session N

  --project FILE       Path to a project manifest (non-secret).
  --capabilities FILE  Path to a capability manifest (non-secret).
  --host FILE          Path to the host manifest. Required to deploy.
  --render-runtime-only
                       Reserve this project's two host-loopback ports and write
                       the runtime override that publishes them, without moving
                       a container. Needs --host and root. Re-runnable: it marks
                       no allocation active and publishes no readiness.
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

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so an
# operator's activated venv is invisible under --through-session.
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
  local project="" capabilities="" host="" render_only=0 through_session=""
  local render_runtime_only=0

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
      --render-runtime-only)
        render_runtime_only=1
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

  if [ "${render_runtime_only}" -eq 1 ]; then
    [ "${render_only}" -eq 1 ] && die 2 \
      "--render-only needs no host and no root; --render-runtime-only needs both. Pass one."
    [ -n "${through_session}" ] && die 2 \
      "--render-runtime-only reserves and renders; --through-session deploys. Pass one."
    [ -n "${host}" ] || die 2 "--render-runtime-only requires --host."
    [ "$(id -u)" -eq 0 ] || die 3 \
      "--render-runtime-only writes the root-owned runtime override and the host port registry."

    # Reserve and publish-in-the-file, and move no container. This is the step
    # that makes a publication recoverable: it can fail on its own and be re-run
    # on its own, and the two things most likely to go wrong -- the allocation
    # and the loopback binding -- are both cheaper to get wrong here than after
    # a container has moved (D95, ADR 0042).
    #
    # What it deliberately does NOT do: materialize a secret, rotate a password,
    # mark an allocation active, or publish `ready`. Every one of those is a
    # claim about a running system, and nothing is running differently when this
    # returns.
    PYTHONPATH="${ROOT_DIR}/src" exec "$(python_bin)" \
      "${ROOT_DIR}/bin/deploy-project.py" \
      --host "${host}" \
      --project "${project}" \
      --capabilities "${capabilities}" \
      --render-runtime-only
  fi

  if [ "${render_only}" -ne 1 ] && [ -z "${through_session}" ]; then
    die 10 "nothing to do: pass --render-only, --render-runtime-only, or --through-session N."
  fi

  if [ -n "${through_session}" ]; then
    case "${through_session}" in
      ''|*[!0-9]*) die 2 "--through-session takes a session number, got: ${through_session}" ;;
    esac
    # Refused rather than clamped. Clamping to what this release can do would
    # deploy less than the operator asked for and report success.
    #
    # The ceiling is read from the release, not written here. A literal in this
    # script is a second declaration of which session the tree implements, and
    # the two disagree the moment either is edited -- which is exactly what
    # happened: `CURRENT_SESSION` moved to 3 in Run 6 and this line still said
    # 2, so the release that implements Session 3 refused to deploy it (D59).
    local deployable
    deployable="$(max_deployable_session)" \
      || die 3 "could not read this release's session; the package is not importable."
    [ "${through_session}" -le "${deployable}" ] \
      || die 10 "this release deploys through session ${deployable}; asked for ${through_session}."
    [ -n "${host}" ] || die 2 "--through-session requires --host."
    [ -f "${host}" ] || die 2 "host manifest not found: ${host}"

    [ -f "${project}" ] || die 2 "project manifest not found: ${project}"
    [ -f "${capabilities}" ] || die 2 "capability manifest not found: ${capabilities}"

    # A terminal on stdin with stdout or stderr redirected is the one shape
    # that hangs: sudo's use_pty runs the command in the background of its pty
    # when the standard streams are not all terminals, and the first child that
    # reads the terminal -- the bootstrap's `docker exec -i` -- is stopped with
    # SIGTTIN and waits forever, its own 30-second timeout unable to fire in a
    # stopped process (D972, measured on 2026-09-04: three processes in state
    # T, nothing applied). Refused here, before root, so the operator learns it
    # from a sentence rather than from a deploy that never returns. Fully
    # non-interactive callers (no terminal anywhere) are not this shape.
    if [ -t 0 ] && { [ ! -t 1 ] || [ ! -t 2 ]; }; then
      die 2 "--through-session with stdin at a terminal and stdout or stderr redirected stops at the first docker exec -i under sudo (D972). Run it unredirected; the terminal is the log."
    fi

    [ "$(id -u)" -eq 0 ] || die 3 "--through-session requires root: it writes host state."

    # Run through the resolver rather than the shebang. `#!/usr/bin/env python3`
    # would select the system interpreter, which has neither yaml nor
    # jsonschema -- the failure would be a ModuleNotFoundError from inside a
    # deployment, after the render had already run.
    exec "$(python_bin)" "${ROOT_DIR}/bin/deploy-project.py" \
      --host "${host}" \
      --project "${project}" \
      --capabilities "${capabilities}" \
      --through-session "${through_session}"
  fi

  # Step 4 of the runbook §11 order: verify local prerequisites before doing
  # anything that could touch generated state.
  [ -f "${project}" ] || die 2 "project manifest not found: ${project}"
  [ -f "${capabilities}" ] || die 2 "capability manifest not found: ${capabilities}"

  # Steps 5-15 are one transaction and belong in one process. Splitting them
  # across shell and Python would put the rollback boundary in the wrong place.
  exec "$(python_bin)" "${ROOT_DIR}/bin/render-config.py" \
    --project "${project}" \
    --capabilities "${capabilities}" \
    --render
}

main "$@"

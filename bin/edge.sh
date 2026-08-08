#!/usr/bin/env bash
#
# The shared edge plane: Traefik and the Docker socket proxy.
#
# One edge serves every project on the host, which is what makes two projects
# on one host possible at all -- two proxies cannot both hold ports 80 and 443.
# The cost is that edge operations are blast-radius operations, and that shapes
# most of what is here.
#
# Two things are deliberately hard:
#
# ACME promotion. `promote-acme --to production` is the only path from staging
# to production certificates, it refuses unless staging already worked, and it
# demands the host id back. Let's Encrypt's production limits are 50 issuances
# per registered domain per week and 5 duplicate certificates per week, and the
# way people exhaust them is deleting state and re-requesting in a loop. So
# production is never a default and is never reached by re-running an earlier
# command.
#
# Volume removal. `down` never passes -v, and bin/compose.sh refuses -v in edge
# scope regardless. ACME state is a bind mount under EDGE_STATE_DIR precisely so
# that no Compose lifecycle verb can remove it.
#
# Exit codes:
#   0  success
#   2  invalid operator input
#   3  missing prerequisite, or not root for an action that needs it
#   9  the edge could not be brought to the requested state

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly EDGE_STATE_DIR="/var/lib/agentic-postgres/edge"
readonly EDGE_STATE_FILE="/etc/agentic-postgres/edge-state.json"
readonly ACME_DIR="${EDGE_STATE_DIR}/acme"

ACTION=""
HOST_MANIFEST=""
PROMOTE_TO=""
CONFIRM=""

usage() {
  cat <<'USAGE'
Usage: bin/edge.sh --host FILE <up|down|restart|reconcile|status>
       bin/edge.sh --host FILE promote-acme --to production --confirm HOST_ID

  up          Start the edge plane and attach it to every deployed project.
  down        Stop it. ACME state is preserved; volumes are never removed.
  restart     down then up, then reconcile attachments.
  reconcile   Re-attach the proxy to every deployed project's edge network.
  status      Report what is running and which ACME environment is active.
              Redacted, and readable without root.

  promote-acme --to production --confirm HOST_ID
              Move from staging to production certificates. Refuses unless a
              staging certificate already exists for every configured hostname,
              because a promotion that fails validation burns a weekly rate
              limit that takes seven days to come back.

  --host FILE The host manifest. Required.

There is no --to staging: staging is where the edge starts, and going back is
a re-render, not a command.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'edge: %s\n' "$*" >&2
  exit "$code"
}

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --host)
        [ "$#" -ge 2 ] || die 2 "--host requires a value."
        HOST_MANIFEST="$2"
        shift 2
        ;;
      --to)
        [ "$#" -ge 2 ] || die 2 "--to requires a value."
        PROMOTE_TO="$2"
        shift 2
        ;;
      --confirm)
        [ "$#" -ge 2 ] || die 2 "--confirm requires a value."
        CONFIRM="$2"
        shift 2
        ;;
      up|down|restart|reconcile|status|promote-acme)
        [ -z "${ACTION}" ] || die 2 "only one action may be given."
        ACTION="$1"
        shift
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${ACTION}" ] || { usage >&2; die 2 "an action is required."; }
  [ -n "${HOST_MANIFEST}" ] || die 2 "--host is required."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"
}

# Interpreter resolution, in this order and for these reasons:
#
#   1. the repository's own venv, because sudo resets PATH to secure_path and a
#      venv the operator activated is therefore invisible to this script;
#   2. python3, because Ubuntu ships no bare `python` and has not for years;
#   3. python, for a machine where the venv is already on PATH.
#
# Assuming a bare `python` is a standing trap this repository documents, and
# five Session 2 scripts walked into it. It fails only on a host, only under
# sudo, and reports `python: command not found` from inside a heredoc.
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

host_id() {
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${HOST_MANIFEST}" <<'PYTHON'
import sys
from pathlib import Path

from agentic_postgres.host_config import load_host_manifest

print(load_host_manifest(Path(sys.argv[1]))["host"]["id"])
PYTHON
}

# Delegated, the way host_id above already is. This was four lines of shell,
# and bin/deploy-project.py had its own answer -- the literal "staging",
# which no promotion could change. Two answers to "which ACME environment is
# this host on" is one too many, and the second one was wrong for the entire
# life of every deployed document written after a promotion.
acme_environment() {
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${ACME_DIR}" <<'PYTHON'
import sys
from pathlib import Path

from agentic_postgres.edge_state import acme_environment

print(acme_environment(acme_directory=Path(sys.argv[1])), end="")
PYTHON
}

compose() {
  "${ROOT_DIR}/bin/compose.sh" --edge --host "${HOST_MANIFEST}" "$@"
}

require_root() {
  [ "$(id -u)" -eq 0 ] || die 3 "$1 requires root."
}

# The certificate store is the thing an operator most wants to "just delete and
# retry", and doing so is exactly what exhausts the weekly limit. Checked before
# every promotion.
staging_certificate_exists() {
  [ -s "${ACME_DIR}/staging.json" ] || return 1
  command -v jq >/dev/null 2>&1 || die 3 "jq is not installed."
  local count
  count="$(jq '[.. | objects | select(has("certificate")) ] | length' \
    "${ACME_DIR}/staging.json" 2>/dev/null || printf '0')"
  [ "${count}" -gt 0 ]
}

do_up() {
  require_root "up"
  install -d -m 0700 -o root -g root "${EDGE_STATE_DIR}" "${ACME_DIR}"
  # Traefik refuses to start if the ACME store is group- or world-readable, and
  # it is right to. Set explicitly rather than left to umask.
  [ -e "${ACME_DIR}/staging.json" ] || : > "${ACME_DIR}/staging.json"
  chmod 0600 "${ACME_DIR}/staging.json"

  # Before compose, because the model bind-mounts traefik.yaml and dynamic/ and
  # Compose creates a missing bind source as a *directory*. That is how Traefik
  # came to restart forever on "read /etc/traefik/traefik.yaml: is a directory":
  # nothing had ever rendered the template, and the mount silently invented one
  # in its place.
  #
  # Rendered against whatever ACME environment the store already reflects, so a
  # restart after promote-acme does not quietly demote the edge to staging.
  "$(python_bin)" "${ROOT_DIR}/bin/render-config.py" \
    --host "${HOST_MANIFEST}" --edge-static "${EDGE_STATE_DIR}" \
    --acme-environment "$(acme_environment)" \
    || die 9 "could not render the edge configuration."

  if ! compose --runtime up -d --wait; then
    # Print why before dying. "did not become healthy" names the symptom and
    # nothing else, and every failure of this command so far has been diagnosed
    # by an operator running `docker logs` by hand and pasting the result
    # somewhere. The reason is already on the host; there is no case where
    # withholding it helps.
    printf '\n--- why: last lines from each edge container ---\n' >&2
    compose --runtime ps --all --format '{{.Name}} {{.State}}' >&2 2>/dev/null || true
    local container
    for container in $(compose --runtime ps --all --quiet 2>/dev/null); do
      printf '\n== %s ==\n' \
        "$(docker inspect "${container}" --format '{{.Name}} {{.State.Status}}' 2>/dev/null)" >&2
      docker logs --tail 15 "${container}" 2>&1 | tail -15 >&2 || true
    done
    printf '\n' >&2
    die 9 "the edge plane did not become healthy."
  fi
  "${ROOT_DIR}/bin/edge-network.sh" reconcile
  printf 'edge: up, ACME environment %s\n' "$(acme_environment)"
}

do_down() {
  require_root "down"
  # No -v, ever. bin/compose.sh refuses it in edge scope as well, so this is
  # belt and braces on the one operation that could destroy a week of rate
  # limit in a keystroke.
  compose --runtime down || die 9 "the edge plane did not stop cleanly."
  printf 'edge: down. ACME state under %s is preserved.\n' "${ACME_DIR}"
}

do_status() {
  printf 'edge stack       apg-edge\n'
  printf 'acme environment %s\n' "$(acme_environment)"
  printf 'state directory  %s\n' "${EDGE_STATE_DIR}"

  if [ -f "${EDGE_STATE_FILE}" ] && command -v jq >/dev/null 2>&1; then
    printf 'installed release %s\n' \
      "$(jq -r '.installed_release_commit // "none"' "${EDGE_STATE_FILE}")"
  fi

  # Container state only. No certificate contents, no resolver email, no
  # request logs -- status is the command an operator runs while someone is
  # watching their screen.
  compose ps 2>/dev/null || printf 'containers        (not running)\n'
}

do_promote() {
  require_root "promote-acme"

  [ "${PROMOTE_TO}" = "production" ] \
    || die 2 "promote-acme requires --to production. There is no path back to staging."

  local expected
  expected="$(host_id)"
  [ -n "${CONFIRM}" ] || die 2 "promote-acme requires --confirm ${expected}"
  [ "${CONFIRM}" = "${expected}" ] \
    || die 2 "--confirm did not match this host's id. Expected ${expected}."

  if [ "$(acme_environment)" = "production" ]; then
    printf 'edge: already on production certificates. Nothing to do.\n'
    return 0
  fi

  staging_certificate_exists || die 3 \
    "no staging certificate exists yet. Promotion would spend a production rate limit
     on a configuration that has not been shown to work. Fix DNS or port 80, confirm
     a staging certificate is issued, then promote."

  install -d -m 0700 -o root -g root "${ACME_DIR}"
  : > "${ACME_DIR}/production.json"
  chmod 0600 "${ACME_DIR}/production.json"

  # Re-render the static configuration against the production directory, then
  # restart. The staging store is left in place: it costs nothing, and it is the
  # evidence that the configuration worked before production was ever asked.
  # This said it re-rendered the static configuration and did not: --edge-env
  # only writes compose.env, so promotion changed the ACME store on disk while
  # leaving Traefik pointed at the staging directory.
  "$(python_bin)" "${ROOT_DIR}/bin/render-config.py" \
    --host "${HOST_MANIFEST}" --edge-static "${EDGE_STATE_DIR}" \
    --acme-environment production \
    || die 9 "could not render the production edge configuration."

  compose --runtime restart || die 9 "the edge plane did not restart."
  printf 'edge: promoted to production ACME. Staging state kept at %s.\n' \
    "${ACME_DIR}/staging.json"
  printf 'If issuance fails, do NOT delete production.json and retry in a loop:\n'
  printf 'failed validations are limited to 5 per hour per hostname.\n'
}

main() {
  parse_arguments "$@"
  cd "${ROOT_DIR}"

  case "${ACTION}" in
    up) do_up ;;
    down) do_down ;;
    restart)
      do_down
      do_up
      ;;
    reconcile)
      require_root "reconcile"
      "${ROOT_DIR}/bin/edge-network.sh" reconcile
      ;;
    status) do_status ;;
    promote-acme) do_promote ;;
  esac
}

main "$@"

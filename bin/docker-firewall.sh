#!/usr/bin/env bash
#
# Reconcile the DOCKER-USER ingress policy.
#
# Invoked by /usr/local/libexec/agentic-postgres/firewall, which
# agentic-postgres-docker-firewall.service runs after docker.service. Docker
# rewrites its own chains on every daemon start, so this has to be re-runnable
# and has to converge, not accumulate.
#
# Convergence is by tag, not by flush. Every rule this script owns carries a
# comment matching --tag; reconcile removes exactly those and re-adds the
# current policy. Flushing DOCKER-USER instead would be simpler and would also
# delete rules Docker or another operator put there, which is how a "fix" to
# one thing silently disables another.
#
# The rules themselves come from /etc/agentic-postgres/docker-user-rules.v{4,6},
# rendered by bin/provision-host.sh from the templates under infra/host/. This
# script does not generate policy; it applies what was rendered, so what is
# running can be diffed against a file.
#
# Exit codes:
#   0  success
#   2  invalid operator input
#   3  missing prerequisite (not root, iptables absent, rules not rendered)
#   6  the policy could not be applied

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly RULES_DIR="/etc/agentic-postgres"
readonly CHAIN="DOCKER-USER"

TAG="agentic-postgres"
ACTION=""

usage() {
  cat <<'USAGE'
Usage: bin/docker-firewall.sh [--tag TAG] <reconcile|clear|status>

Applies the DOCKER-USER policy rendered into /etc/agentic-postgres/ by
bin/provision-host.sh --apply.

  reconcile  Remove this tool's rules and re-add the rendered policy.
  clear      Remove this tool's rules and add nothing.
  status     Print the current chain for both families. Changes nothing.

  --tag TAG  Comment marking the rules this tool owns. Default:
             agentic-postgres. Rules without it are never touched.

Reconciliation is idempotent: running it twice leaves the same chain. It must
be, because Docker rebuilds its chains on every daemon restart and this runs
again afterwards.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'docker-firewall: %s\n' "$*" >&2
  exit "$code"
}

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --tag)
        [ "$#" -ge 2 ] || die 2 "--tag requires a value."
        TAG="$2"
        shift 2
        ;;
      reconcile|clear|status)
        [ -z "${ACTION}" ] || die 2 "only one action may be given."
        ACTION="$1"
        shift
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${ACTION}" ] || { usage >&2; die 2 "an action is required."; }

  # The tag becomes an iptables comment and a grep pattern. Restricting it to a
  # plain identifier keeps both unambiguous.
  case "${TAG}" in
    *[!a-zA-Z0-9_-]* | "") die 2 "--tag must be alphanumeric with hyphens or underscores: ${TAG}" ;;
  esac
}

require_prerequisites() {
  [ "$(id -u)" -eq 0 ] || die 3 "must run as root to modify ${CHAIN}."
  command -v iptables >/dev/null 2>&1 || die 3 "iptables is not installed."
  command -v ip6tables >/dev/null 2>&1 || die 3 "ip6tables is not installed."
}

# Ensure the chain exists. Docker creates DOCKER-USER, but this unit can run
# before any container has ever started, and on a host where the IPv6 chain in
# particular may not exist yet.
ensure_chain() {
  local command="$1"
  "${command}" -n -L "${CHAIN}" >/dev/null 2>&1 || "${command}" -N "${CHAIN}" 2>/dev/null || true
}

# Remove every rule carrying our comment. Deleted by rule specification rather
# than by line number: numbers shift as each deletion lands, and a loop over
# stale numbers deletes the wrong rules.
remove_tagged() {
  local command="$1" rule
  ensure_chain "${command}"

  while IFS= read -r rule; do
    [ -n "${rule}" ] || continue
    # The rule specification must word-split into separate arguments here; that
    # is what makes it a rule rather than one long string.
    # shellcheck disable=SC2086
    "${command}" -D ${rule#-A } 2>/dev/null || true
  done < <("${command}" -S "${CHAIN}" 2>/dev/null | grep -F -- "--comment \"${TAG}" || true)
}

apply_rules() {
  local command="$1" file="$2" line
  [ -f "${file}" ] || die 3 "policy is not rendered: ${file}. Run bin/provision-host.sh --apply."

  while IFS= read -r line; do
    case "${line}" in
      ""|"#"*) continue ;;
    esac
    # The rendered rule must word-split into arguments, as above.
    # shellcheck disable=SC2086
    "${command}" ${line} \
      || die 6 "${command} rejected a rendered rule: ${line}"
  done < "${file}"
}

main() {
  parse_arguments "$@"

  # §8.5: every command works when invoked from anywhere.
  cd "${ROOT_DIR}"

  if [ "${ACTION}" = "status" ]; then
    # Deliberately readable without root: an operator asking what is running
    # should not need privilege they would then be holding for the next command.
    for command in iptables ip6tables; do
      command -v "${command}" >/dev/null 2>&1 || continue
      printf '== %s %s ==\n' "${command}" "${CHAIN}"
      "${command}" -S "${CHAIN}" 2>/dev/null || printf '(chain absent)\n'
    done
    return 0
  fi

  require_prerequisites

  remove_tagged iptables
  remove_tagged ip6tables

  if [ "${ACTION}" = "clear" ]; then
    printf 'docker-firewall: removed rules tagged %s. The chain now has no policy of ours.\n' \
      "${TAG}"
    return 0
  fi

  apply_rules iptables "${RULES_DIR}/docker-user-rules.v4"
  apply_rules ip6tables "${RULES_DIR}/docker-user-rules.v6"

  printf 'docker-firewall: reconciled %s for both address families.\n' "${CHAIN}"
}

main "$@"

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

# Remove every rule carrying our comment, by line number, highest first.
#
# Deleting by rule specification means feeding `-S` output back to iptables
# unquoted, and how `-S` renders a comment is not something to bet a firewall
# on: quoted, it word-splits into an argument containing literal quotes and the
# delete silently matches nothing. `-L -n --line-numbers` renders the comment as
# /* tag */, which is stable, and a number needs no quoting at all.
#
# Descending order is what makes line numbers usable. Each deletion shifts every
# position after it, so removing from the bottom up leaves the positions still
# to be removed exactly where they were.
remove_tagged() {
  local command="$1" number
  ensure_chain "${command}"

  while IFS= read -r number; do
    [ -n "${number}" ] || continue
    "${command}" -D "${CHAIN}" "${number}" 2>/dev/null || true
  done < <(
    "${command}" -L "${CHAIN}" -n --line-numbers 2>/dev/null \
      | awk -v marker="/* ${TAG} */" 'index($0, marker) { print $1 }' \
      | sort -rn
  )
}

apply_rules() {
  local command="$1" file="$2" line position=1
  [ -f "${file}" ] || die 3 "policy is not rendered: ${file}. Run bin/provision-host.sh --apply."

  while IFS= read -r line; do
    case "${line}" in
      ""|"#"*) continue ;;
    esac
    # -I at an increasing position, not a bare rule specification. Two reasons,
    # and the first one is why --apply died on a real host: a specification with
    # no command is not a command, so `iptables -i eth0 ...` is rejected with
    # "no command specified".
    #
    # The second is why -A would have been wrong even with the command present.
    # Docker creates DOCKER-USER holding a single `-j RETURN`, so an appended
    # rule sits after it and is never evaluated: the policy would be installed,
    # visible in -S, and dead. Inserting at 1, 2, 3... puts the file's rules
    # ahead of that RETURN, in file order.
    #
    # The comment is what makes reconciliation converge. Without it nothing
    # identifies the rules this tool owns, remove_tagged matches none, and every
    # run adds another copy of the whole policy. It goes first because a match
    # module is self-contained and the rendered line ends in its own -j.
    #
    # The rendered rule must word-split into separate arguments; that is what
    # makes it a rule rather than one long string.
    # shellcheck disable=SC2086
    "${command}" -I "${CHAIN}" "${position}" -m comment --comment "${TAG}" ${line} \
      || die 6 "${command} rejected a rendered rule: ${line}"
    position=$((position + 1))
  done < "${file}"
}

# A chain nothing jumps to is a policy that is not enforcing. Docker adds the
# FORWARD reference itself, but ensure_chain will happily create an orphan
# DOCKER-USER on a host where the daemon has not done so yet -- and the result
# looks entirely correct in `iptables -S DOCKER-USER`.
#
# Fatal for IPv4 and advisory for IPv6, which is a real asymmetry and not a
# convenience. Docker only creates the v6 FORWARD reference when it is managing
# ip6tables, and whether it does depends on the daemon version and on whether
# IPv6 networking is enabled at all. This runs from a unit after every
# docker.service start, so treating an absent v6 reference as fatal would leave
# reconciliation permanently failed -- and take the v4 policy, which is the one
# carrying the public traffic, down with it. The v6 policy is still applied; a
# host that later gains v6 Docker networking gets it already in place.
require_chain_is_reachable() {
  local command="$1" severity="$2"

  if "${command}" -S FORWARD 2>/dev/null | grep -qE -- "-j ${CHAIN}( |\$)"; then
    return 0
  fi

  if [ "${severity}" = "required" ]; then
    die 6 "${CHAIN} exists but ${command} FORWARD does not jump to it; the policy is inert."
  fi

  printf 'docker-firewall: WARNING %s FORWARD does not jump to %s.\n' "${command}" "${CHAIN}" >&2
  printf 'docker-firewall: the IPv6 policy is installed but not enforcing.\n' >&2
}

main() {
  parse_arguments "$@"

  # §8.5: every command works when invoked from anywhere.
  cd "${ROOT_DIR}"

  if [ "${ACTION}" = "status" ]; then
    for command in iptables ip6tables; do
      command -v "${command}" >/dev/null 2>&1 || continue
      printf '== %s %s ==\n' "${command}" "${CHAIN}"
      if ! "${command}" -S "${CHAIN}" 2>/dev/null; then
        # "absent" and "you are not root" are different answers and iptables
        # needs root to read. Reporting the first when the second is true tells
        # an operator their firewall policy is missing when it is running fine.
        if [ "$(id -u)" -ne 0 ]; then
          printf '(cannot read: iptables requires root; re-run under sudo)\n'
        else
          printf '(chain absent)\n'
        fi
      fi
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

  # Checked after applying, not before: on a host where Docker has not started
  # yet the reference legitimately does not exist, and the policy still needs to
  # be in place for when it does. Checking here reports a chain that will never
  # see a packet, which is the failure worth shouting about.
  require_chain_is_reachable iptables required
  require_chain_is_reachable ip6tables advisory

  printf 'docker-firewall: reconciled %s for both address families.\n' "${CHAIN}"
}

main "$@"

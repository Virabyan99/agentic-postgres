#!/usr/bin/env bash
#
# The read-only diagnostic surface (ADR 0071).
#
# This exists so that an agent -- or an operator in a hurry -- can answer "what
# is this deployment doing right now" without holding root over it. Every
# question this host has needed answering during a live run is here, and nothing
# else is.
#
# **Docker access is root access.** The daemon socket can mount the host
# filesystem, so "let the agent run docker" and "give the agent root" are the
# same sentence. That is the whole reason this file is a fixed verb list rather
# than a wrapper that forwards arguments: the sudoers rule names this script, and
# this script names what may be asked.
#
# Four properties make that mean something:
#
#   * the verbs are a fixed set of *names*, not a passthrough. A wrapper that
#     forwarded its arguments to `docker` would be the same door with a lock
#     painted on it (bin/db.sh's rule, applied to a different daemon).
#   * a project is validated against the deployments that exist on this host,
#     not against a pattern. A string that is not a deployed project never
#     reaches a command.
#   * the SQL is an allowlist of *named queries*. There is no path that takes
#     SQL from an argument or from stdin.
#   * nothing here mutates. No restart, no stop, no rm, no exec with a caller's
#     command, no write to any path. A diagnostic that can change the thing it
#     is describing is not a diagnostic.
#
# What it deliberately cannot show: a secret value, a container's environment,
# or `docker inspect` output beyond labels. `logs` passes its output through a
# redaction filter, which is belt to the braces of those services not logging
# credentials in the first place.
#
# Exit codes:
#   0   success
#   2   invalid operator input
#   3   not root
#   4   no such deployed project
#   5   the verb, service or query is not in the allowlist
#
# **This file imports nothing from the repository.** It is installed as a copy
# at /usr/local/bin/apg-diag and reached through a sudoers rule naming that
# path, so it keeps answering when the checkout is broken, mid-deploy, or at a
# release the operator is about to roll back -- which is exactly when the
# questions it answers get asked.
#
# This command changes nothing. See ADR 0071.

# First executable line: this reads container output, and tracing would print
# every expanded argument of every command it runs.
set +x
set -euo pipefail

readonly PROJECT_ROOT="/etc/agentic-postgres/projects"
readonly SECRET_ROOT="/var/lib/agentic-postgres/secrets"
readonly EDGE_CONTAINER="apg-edge-traefik-1"

# The complete verb set. Adding one is a reviewable diff.
readonly VERBS="containers labels logs routes listeners edge-log catalog generation"

# The services a caller may name. Not derived from what is running: a container
# that appeared under a name nobody deployed is exactly what an operator would
# want to see in `containers`, and exactly what should not become an argument.
readonly SERVICES="postgres pgbouncer postgrest docs edge-probe dbmate"

# The complete set of queries `catalog` will run, by name. There is no wildcard,
# no directory scan, and no way to supply SQL.
readonly QUERIES="connection-limits role-settings migration-ledger extensions"

readonly MAX_LOG_LINES=200

die() {
  local code="$1"
  shift
  printf 'apg-diag: %s\n' "$*" >&2
  exit "$code"
}

usage() {
  cat <<'USAGE'
Usage: sudo apg-diag <verb> [arguments]

Read-only. Changes nothing, reveals no secret value.

  containers                     Every agentic-postgres container: name, status,
                                 health and networks.
  labels <project> <service>     The apg.* and traefik.* labels on one container.
                                 Environment is never shown.
  logs <project> <service> [n]   The last n (default 40, max 200) log lines,
                                 with credential-shaped strings redacted.
  routes <project>               The status code each published route answers,
                                 from this host.
  listeners                      Every listening socket, with the loopback ones
                                 marked. 443 is asserted present: a scan that
                                 can see nothing looks like a clean one.
  edge-log [n]                   Recent edge access-log entries, reduced to the
                                 fields that identify a route.
  catalog <project> <query>      One named read-only query. See below.
  generation <project>           The active secret generation identifier. The
                                 identifier, never a value.

Queries: connection-limits, role-settings, migration-ledger, extensions

This command deploys nothing, restarts nothing and rotates nothing. Those stay
with a human at a terminal (ADR 0071).
USAGE
}

require_root() {
  [ "$(id -u)" -eq 0 ] || die 3 "requires root: it reads container state and root-owned files."
}

# A project is validated against what is deployed, not against a pattern. A
# regex would accept `../../etc` for as long as somebody kept the regex right.
resolve_project() {
  local key="$1"
  [ -n "${key}" ] || die 2 "a project key is required."
  [ -d "${PROJECT_ROOT}/${key}" ] || die 4 "no deployed project named '${key}'."
  printf '%s' "${key}"
}

allowlisted() {
  local needle="$1" haystack="$2" what="$3"
  local item
  for item in ${haystack}; do
    [ "${item}" = "${needle}" ] && return 0
  done
  die 5 "'${needle}' is not an allowlisted ${what}. Allowed: ${haystack}"
}

# The Compose project a deployment's containers belong to.
#
# Anchored on `database.container`, which the deployed document publishes, and
# then read off that container's own Compose label. Not derived from the project
# key: the container name and the Compose project name are both derived
# identities, and re-deriving one here would make this script a second authority
# on a name (ADR 0002).
#
# **Not `apg.project.key`.** That label is on three of thirteen services --
# edge-probe, postgrest and docs, the three that carry Traefik labels -- so it
# means "this container is routed", not "this container belongs to this
# project". Filtering on it found half a deployment and no cluster at all
# (D210).
compose_project_for() {
  local key="$1" container project
  container="$(python3 -c '
import json, sys
print(json.load(open(sys.argv[1]))["database"]["container"])
' "${PROJECT_ROOT}/${key}/outputs.json")"
  project="$(docker inspect "${container}" \
    --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
  [ -n "${project}" ] || die 4 "${key}'s cluster container (${container}) is not running."
  printf '%s' "${project}"
}

# One container, found by two labels Compose sets on everything it creates.
# Not by name: a name is a string this script would have to build, and a label
# is a fact the daemon already holds.
container_for() {
  local key="$1" service="$2" project names
  project="$(compose_project_for "${key}")"
  names="$(docker ps -a \
    --filter "label=com.docker.compose.project=${project}" \
    --filter "label=com.docker.compose.service=${service}" \
    --format '{{.Names}}')"
  [ -n "${names}" ] || die 4 "no ${service} container for ${key}."
  printf '%s' "${names}" | head -1
}

# Belt to the braces. These services do not log credentials -- PostgREST logs at
# error level with query logging off, and PostgreSQL logs connections rather
# than passwords -- but a diagnostic that hands its output to somebody else
# should not depend on that staying true.
redact() {
  sed -E \
    -e 's/(password|secret|token|pgpass)([=: ]+)[^ "]+/\1\2<redacted>/gi' \
    -e 's/eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/<redacted-jwt>/g' \
    -e 's/\b[0-9a-f]{32,}\b/<redacted-hex>/g'
}

verb_containers() {
  local key project directory
  printf '%-34s %-26s %s\n' NAME STATUS NETWORKS

  # Per deployed project, so the listing is complete for each one rather than
  # complete for whichever label happens to be universal. A project whose
  # cluster is not running says so, which is more useful than omitting it.
  for directory in "${PROJECT_ROOT}"/*/; do
    [ -d "${directory}" ] || continue
    key="$(basename "${directory}")"
    printf '\n-- %s\n' "${key}"
    project="$(compose_project_for "${key}" 2>/dev/null || true)"
    if [ -z "${project}" ]; then
      printf '   (no running cluster container; the project may be stopped)\n'
      continue
    fi
    docker ps -a --filter "label=com.docker.compose.project=${project}" \
      --format '{{.Names}}\t{{.Status}}\t{{.Networks}}' \
      | while IFS=$'\t' read -r name status networks; do
          printf '%-34s %-26s %s\n' "${name}" "${status}" "${networks}"
        done
  done
}

verb_labels() {
  local key service container
  key="$(resolve_project "${1:-}")"
  service="${2:-}"
  allowlisted "${service}" "${SERVICES}" service
  container="$(container_for "${key}" "${service}")"

  # `.Config.Labels` only. `docker inspect` with no format prints the
  # environment, the mounts and the command line, which is three of the four
  # places a secret must not be.
  docker inspect "${container}" \
    --format '{{range $k,$v := .Config.Labels}}{{$k}}={{$v}}{{"\n"}}{{end}}' \
    | grep -E '^(apg\.|traefik\.)' | sort
}

verb_logs() {
  local key service lines container
  key="$(resolve_project "${1:-}")"
  service="${2:-}"
  allowlisted "${service}" "${SERVICES}" service
  lines="${3:-40}"
  case "${lines}" in
    ''|*[!0-9]*) die 2 "line count must be a positive integer." ;;
  esac
  [ "${lines}" -le "${MAX_LOG_LINES}" ] || die 2 "at most ${MAX_LOG_LINES} lines."

  container="$(container_for "${key}" "${service}")"
  docker logs --tail "${lines}" "${container}" 2>&1 | redact
}

verb_routes() {
  local key document url name status
  key="$(resolve_project "${1:-}")"
  document="${PROJECT_ROOT}/${key}/outputs.json"
  [ -f "${document}" ] || die 4 "${key} has published no deployed document."

  printf '%-10s %-6s %s\n' ROUTE CODE URL
  for name in health rest docs; do
    url="$(python3 -c '
import json, sys
document = json.load(open(sys.argv[1]))
route = document["routes"].get(sys.argv[2]) or {}
print(route.get("url") or "")
' "${document}" "${name}")"
    if [ -z "${url}" ]; then
      printf '%-10s %-6s %s\n' "${name}" "-" "(unpublished)"
      continue
    fi
    status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${url}" || printf 'none')"
    printf '%-10s %-6s %s\n' "${name}" "${status}" "${url}"
  done
}

verb_listeners() {
  local output
  output="$(ss -H -lntu)"
  printf '%s\n' "${output}"
  # The positive control, and the reason this verb prints it rather than
  # summarising. A scan that can see nothing produces the same empty answer as a
  # host with nothing listening, and only one of those is a boundary.
  if printf '%s\n' "${output}" | grep -qE '[:.]443( |$)'; then
    printf '\napg-diag: 443 is present, so this listing can see a listener.\n'
  else
    printf '\napg-diag: WARNING -- 443 is absent from this listing. Either the edge is\n'
    printf 'apg-diag: down or this instrument is not seeing what it should; do not read\n'
    printf 'apg-diag: the absence of anything else as a boundary.\n'
  fi
}

verb_edge_log() {
  local lines="${1:-20}"
  case "${lines}" in
    ''|*[!0-9]*) die 2 "line count must be a positive integer." ;;
  esac
  [ "${lines}" -le "${MAX_LOG_LINES}" ] || die 2 "at most ${MAX_LOG_LINES} lines."

  # Reduced to the fields that identify a route. A raw access line is 1.5 kB of
  # JSON, and the four fields below are the ones that separate Traefik's own 404
  # from a routed one (D186).
  docker logs --tail "${lines}" "${EDGE_CONTAINER}" 2>&1 \
    | python3 -c '
import json, sys

row = "{:<7}{:<28}{:<26}{}"
print(row.format("STATUS", "ROUTER", "SERVICE URL", "HOST"))
for line in sys.stdin:
    try:
        entry = json.loads(line)
    except ValueError:
        continue
    if "DownstreamStatus" not in entry:
        continue
    print(row.format(
        entry.get("DownstreamStatus", "-"),
        entry.get("RouterName", "(none)"),
        entry.get("ServiceURL", "(none)"),
        entry.get("RequestHost", ""),
    ))
' | redact
}

verb_catalog() {
  local key query container database sql
  key="$(resolve_project "${1:-}")"
  query="${2:-}"
  allowlisted "${query}" "${QUERIES}" query

  container="$(container_for "${key}" postgres)"
  database="$(python3 -c '
import json, sys
print(json.load(open(sys.argv[1]))["database"]["name"])
' "${PROJECT_ROOT}/${key}/outputs.json")"

  # Named queries, chosen here. Nothing a caller supplies reaches psql.
  case "${query}" in
    connection-limits)
      sql="SELECT rolname, rolconnlimit FROM pg_roles
           WHERE rolname LIKE 'apg%' ORDER BY rolname;" ;;
    role-settings)
      sql="SELECT r.rolname, s.setconfig FROM pg_db_role_setting s
           JOIN pg_roles r ON r.oid = s.setrole ORDER BY r.rolname;" ;;
    migration-ledger)
      sql="SELECT version, name FROM app_private.migration_ledger ORDER BY version;" ;;
    extensions)
      sql="SELECT extname, extversion FROM pg_extension ORDER BY extname;" ;;
    *)
      die 5 "'${query}' is not an allowlisted query." ;;
  esac

  docker exec -i "${container}" psql -U postgres -d "${database}" -X -qA -c "${sql}"
}

verb_generation() {
  local key pointer
  key="$(resolve_project "${1:-}")"
  pointer="${SECRET_ROOT}/${key}/active-secret-generation.json"
  [ -f "${pointer}" ] || die 4 "${key} has no active secret generation."
  # The identifier and the timestamp. Never a directory listing, and never a
  # file under it: this verb exists to answer "which generation is live", and
  # the answer to "what is in it" is not this command's to give.
  python3 -c '
import json, sys
pointer = json.load(open(sys.argv[1]))
print("generation:", pointer.get("generation_id"))
print("recorded:  ", pointer.get("materialized_at", "unknown"))
' "${pointer}"
}

main() {
  local verb="${1:-}"
  case "${verb}" in
    ''|--help|-h) usage; exit 0 ;;
  esac
  allowlisted "${verb}" "${VERBS}" verb
  require_root
  shift

  case "${verb}" in
    containers) verb_containers "$@" ;;
    labels)     verb_labels "$@" ;;
    logs)       verb_logs "$@" ;;
    routes)     verb_routes "$@" ;;
    listeners)  verb_listeners "$@" ;;
    edge-log)   verb_edge_log "$@" ;;
    catalog)    verb_catalog "$@" ;;
    generation) verb_generation "$@" ;;
    *)          die 5 "'${verb}' is not an allowlisted verb." ;;
  esac
}

main "$@"

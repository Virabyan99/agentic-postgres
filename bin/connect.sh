#!/usr/bin/env bash
#
# Developer connection helper. Runs on a developer's machine, unprivileged.
#
# It reaches a deployed project's database over an SSH local forward, and it
# obtains what it needs from the host through one privileged, enumerated
# operation -- /usr/local/libexec/agentic-postgres/database-access -- rather than
# by reading root-owned files under sudo. The authorization decision is on the
# host, in the release that deployed the project (ADR 0043). Nothing here decides
# what this caller may have; it asks, and it is told, or it is refused.
#
# Six commands, and the split between them is deliberate:
#
#   tunnel     opens a forward and records it
#   status     says which forwards are live, and quarantines the ones that are not
#   stop       closes one this process family opened, by recorded identity
#   print-env  prints connection variables, and no secret
#   psql       an interactive session over an existing tunnel
#   exec       runs a command with the connection environment set
#
# `psql`, `print-env` and `exec` require a tunnel that is already open. They do
# not open one. A command that silently opened and closed a forward would make
# "is the tunnel up" unanswerable, and the failure mode of the alternative --
# a command that leaves a forward behind when it dies -- is a port on a
# developer's machine that reaches a production database an hour later.
#
# NO COMMAND HERE PRINTS A PASSWORD. The source specification asks only that
# passwords are not printed "by default"; this is stricter and there is no flag
# to loosen it. `exec` puts the credential in a 0600 file and names it to the
# child through PGPASSFILE, so a password reaches a client without passing
# through a terminal, a shell history, a log or an argument vector. Recorded as
# plan divergence D105.
#
# LEAST PRIVILEGE BY DEFAULT. Every command defaults to `runtime_direct`: the
# application role, over the direct transport. `migration_direct` carries
# authority over the schema and is never reached by defaulting, by falling back,
# or by asking for a direct transport -- it is selected by name, and saying its
# name prints a warning.
#
# Exit codes follow the convention (D42, D87):
#   0  success
#   2  invalid operator input
#   3  missing prerequisite (a tool, a directory this will not trust)
#   4  missing runtime state (no tunnel, no state file)
#   5  a contract failure -- state that exists and cannot be acted on
#   6  refused
#   9  the host could not be reached
# The broker's own exit status is passed through unchanged when it answers.

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

# The one privileged path on the host. Fixed here rather than configurable: a
# caller-supplied path to a privileged program is the whole attack.
readonly BROKER="/usr/local/libexec/agentic-postgres/database-access"

readonly PROJECT_KEY_PATTERN='^[a-z][a-z0-9-]{4,47}$'
readonly PROFILES="runtime_pooled runtime_direct migration_direct"
readonly DEFAULT_PROFILE="runtime_direct"
readonly PRIVILEGED_PROFILE="migration_direct"

# Loopback only. A forward bound to 0.0.0.0 publishes someone else's database on
# the developer's network, which is the same mistake ADR 0040 is about, made on
# the other end of the tunnel.
readonly LOCAL_BIND="127.0.0.1"

COMMAND=""
PROJECT_KEY=""
PROFILE="${DEFAULT_PROFILE}"
SSH_DESTINATION=""
SSH_PORT="22"
LOCAL_PORT=""
STOP_ALL=0
SSH_OPTIONS=()
CHILD=()

usage() {
  cat <<'USAGE'
Usage: bin/connect.sh tunnel    --project KEY --ssh USER@HOST [--profile NAME]
                                [--ssh-port N] [--local-port N] [--ssh-option OPT]
       bin/connect.sh status    [--project KEY]
       bin/connect.sh stop      --project KEY [--profile NAME] | --all
       bin/connect.sh print-env --project KEY [--profile NAME]
       bin/connect.sh psql      --project KEY [--profile NAME]
       bin/connect.sh exec      --project KEY [--profile NAME] -- COMMAND [ARGS...]

  tunnel     Open an SSH local forward to one access profile's endpoint and
             record it. The local bind is 127.0.0.1 and nothing else.
  status     Report which recorded tunnels are live. A record whose process is
             gone, or is no longer the process that was recorded, is moved to a
             quarantine directory rather than deleted or believed.
  stop       Close a tunnel this helper opened. The recorded process identity --
             start time and full argument vector -- must match before anything
             is signalled. Nothing is ever matched by process name.
  print-env  Print PG* variables and a password-free DATABASE_URL for an open
             tunnel. Prints no credential.
  psql       Interactive psql over an open tunnel.
  exec       Run a command with the connection environment set, including
             PGPASSFILE pointing at a 0600 file that exists for the child's
             lifetime and is removed afterwards.

  --project KEY     The deployed project key.
  --profile NAME    runtime_pooled | runtime_direct | migration_direct.
                    Default: runtime_direct -- the application role over the
                    direct transport. migration_direct carries authority over
                    the schema; it is never reached by default or by fallback,
                    and selecting it prints a warning.
  --ssh USER@HOST   The deployment host. Recorded with the tunnel, so later
                    commands do not ask for it again.
  --ssh-port N      Default 22.
  --ssh-option OPT  Passed to ssh as -o OPT. Options that disable host-key
                    verification are refused.
  --local-port N    Default: the number the port registry allocated to this
                    project, so a documented command reads the same for
                    everyone. Nothing is published on it at the far end (ADR
                    0044) -- it is the near end of the forward, and it is
                    allocated so two projects' tunnels never collide. If it is
                    busy this fails rather than choosing another silently.
  --all             stop only: every recorded tunnel.

Host-key verification is required. StrictHostKeyChecking=no, and a
UserKnownHostsFile of /dev/null, are refused rather than passed on.

No secret is accepted as an argument, and no command prints one.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'connect: %s\n' "$*" >&2
  exit "$code"
}

warn() { printf 'connect: %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

refuse_unverified_host_key() {
  local option="$1" folded
  folded="$(printf '%s' "${option}" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
  case "${folded}" in
    stricthostkeychecking=no|stricthostkeychecking=off|stricthostkeychecking=accept-new)
      die 2 "refusing -o ${option}: host-key verification is what makes this tunnel a private channel rather than a hopeful one."
      ;;
    userknownhostsfile=/dev/null)
      die 2 "refusing -o ${option}: a discarded known-hosts file accepts a new key every time, which is StrictHostKeyChecking=no spelled differently."
      ;;
  esac
}

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --project)
        [ "$#" -ge 2 ] || die 2 "--project requires a value."
        PROJECT_KEY="$2"; shift 2 ;;
      --profile)
        [ "$#" -ge 2 ] || die 2 "--profile requires a value."
        PROFILE="$2"; shift 2 ;;
      --ssh)
        [ "$#" -ge 2 ] || die 2 "--ssh requires a value."
        SSH_DESTINATION="$2"; shift 2 ;;
      --ssh-port)
        [ "$#" -ge 2 ] || die 2 "--ssh-port requires a value."
        SSH_PORT="$2"; shift 2 ;;
      --ssh-option)
        [ "$#" -ge 2 ] || die 2 "--ssh-option requires a value."
        refuse_unverified_host_key "$2"
        SSH_OPTIONS+=("-o" "$2"); shift 2 ;;
      --local-port)
        [ "$#" -ge 2 ] || die 2 "--local-port requires a value."
        LOCAL_PORT="$2"; shift 2 ;;
      --all) STOP_ALL=1; shift ;;
      --)
        shift
        CHILD=("$@")
        break ;;
      -*) usage >&2; die 2 "unknown argument: $1" ;;
      *) usage >&2; die 2 "unexpected argument: $1" ;;
    esac
  done
}

validate_common() {
  if [ -n "${PROJECT_KEY}" ] \
    && ! printf '%s' "${PROJECT_KEY}" | grep -Eq "${PROJECT_KEY_PATTERN}"; then
    die 2 "not a valid project key: ${PROJECT_KEY}"
  fi

  local known=0 candidate
  for candidate in ${PROFILES}; do
    [ "${candidate}" = "${PROFILE}" ] && known=1
  done
  [ "${known}" -eq 1 ] || die 2 "not an access profile: ${PROFILE} (one of: ${PROFILES})"

  case "${SSH_PORT}" in
    ''|*[!0-9]*) die 2 "--ssh-port is not a number: ${SSH_PORT}" ;;
  esac
  if [ -n "${LOCAL_PORT}" ]; then
    case "${LOCAL_PORT}" in
      ''|*[!0-9]*) die 2 "--local-port is not a number: ${LOCAL_PORT}" ;;
    esac
    [ "${LOCAL_PORT}" -ge 1024 ] || die 2 "--local-port must be unprivileged: ${LOCAL_PORT}"
  fi

  if [ "${PROFILE}" = "${PRIVILEGED_PROFILE}" ]; then
    warn "${PRIVILEGED_PROFILE} was selected. This credential owns the schema; ordinary application work does not need it."
  fi
}

require_project() {
  [ -n "${PROJECT_KEY}" ] || die 2 "--project is required."
}

need() {
  command -v "$1" >/dev/null 2>&1 || die 3 "$1 is not installed; ${2}"
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
#
# $XDG_RUNTIME_DIR is a per-user directory the system creates 0700 and clears at
# logout, which is what a record of an open forward wants. When it is absent --
# a login without a session manager, a container, macOS -- the fallback is a
# directory under TMPDIR that this script will use only if it already satisfies
# the properties the runtime directory would have given it for free. An existing
# directory of the right name that is not ours, or is not 0700, is refused: on a
# shared machine that is another user's directory, and writing a tunnel record
# into it tells them which host to reach and on which port.

state_root() {
  local base
  if [ -n "${XDG_RUNTIME_DIR-}" ] && [ -d "${XDG_RUNTIME_DIR}" ]; then
    base="${XDG_RUNTIME_DIR}/agentic-postgres"
  else
    base="${TMPDIR:-/tmp}/agentic-postgres-$(id -u)"
  fi

  if [ -e "${base}" ]; then
    [ -L "${base}" ] && die 3 "${base} is a symlink, which is not accepted."
    [ -d "${base}" ] || die 3 "${base} exists and is not a directory."
    local owner mode
    owner="$(stat -c '%u' "${base}" 2>/dev/null || stat -f '%u' "${base}")"
    mode="$(stat -c '%a' "${base}" 2>/dev/null || stat -f '%OLp' "${base}")"
    [ "${owner}" = "$(id -u)" ] || die 3 "${base} is owned by uid ${owner}, not by you."
    [ "${mode}" = "700" ] || die 3 "${base} is mode ${mode}; refusing to record a tunnel in a directory others can read."
  else
    mkdir -p "${base}"
    chmod 700 "${base}"
  fi

  mkdir -p "${base}/tunnels" "${base}/quarantine"
  chmod 700 "${base}/tunnels" "${base}/quarantine"
  printf '%s' "${base}"
}

state_file() {
  printf '%s/tunnels/%s__%s.json' "$(state_root)" "$1" "$2"
}

# A record whose process is gone, or is no longer the process that was recorded,
# is moved aside rather than deleted. Deleted, the evidence that something died
# unexpectedly goes with it; trusted, a recycled PID gets signalled.
quarantine() {
  local file="$1" reason="$2" stamp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  mv "${file}" "$(state_root)/quarantine/$(basename "${file}").${stamp}"
  warn "quarantined $(basename "${file}"): ${reason}"
}

# The recorded identity, not the process name. `pkill -f ssh` on a developer's
# machine kills their editor's remote session, their deploy, and the tunnel --
# and reports success.
process_matches() {
  local pid="$1" started="$2" args="$3" now_started now_args
  kill -0 "${pid}" 2>/dev/null || return 1
  now_started="$(ps -p "${pid}" -o lstart= 2>/dev/null || true)"
  now_args="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
  [ -n "${now_started}" ] || return 1
  [ "${now_started# }" = "${started# }" ] || return 1
  [ "${now_args# }" = "${args# }" ] || return 1
  return 0
}

read_state() {
  local file="$1"
  [ -f "${file}" ] || die 4 "no tunnel recorded for ${PROJECT_KEY}/${PROFILE}. Open one with: bin/connect.sh tunnel --project ${PROJECT_KEY} --profile ${PROFILE} --ssh USER@HOST"
  [ -L "${file}" ] && die 3 "${file} is a symlink, which is not accepted."
  cat "${file}"
}

require_live_tunnel() {
  local file record pid started args
  file="$(state_file "${PROJECT_KEY}" "${PROFILE}")"
  record="$(read_state "${file}")"
  pid="$(printf '%s' "${record}" | jq -r '.pid')"
  started="$(printf '%s' "${record}" | jq -r '.started')"
  args="$(printf '%s' "${record}" | jq -r '.args')"

  if ! process_matches "${pid}" "${started}" "${args}"; then
    quarantine "${file}" "the recorded process is gone or is not the one recorded"
    die 4 "the recorded tunnel for ${PROJECT_KEY}/${PROFILE} is no longer running."
  fi
  printf '%s' "${record}"
}

# ---------------------------------------------------------------------------
# The host
# ---------------------------------------------------------------------------

# BatchMode so a missing key fails instead of prompting inside a pipeline;
# StrictHostKeyChecking=yes explicitly rather than by default, because the
# default is `ask` and `ask` under BatchMode is a refusal with a message about
# terminals; ExitOnForwardFailure so a forward that cannot bind is a failed
# command rather than a connected session with no forward -- which is the
# failure that looks exactly like the database being down.
SSH_BASE_OPTIONS=(
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o ExitOnForwardFailure=yes
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3
)
readonly SSH_BASE_OPTIONS

# Runs one enumerated broker operation on the host. Arguments are validated
# before they get here: the project key against a pattern and the profile
# against a fixed list, so what crosses to the remote shell is drawn from a
# closed set.
broker() {
  local operation="$1" destination="$2"
  local status=0

  ssh "${SSH_BASE_OPTIONS[@]}" -o ClearAllForwardings=yes \
    ${SSH_OPTIONS[@]+"${SSH_OPTIONS[@]}"} \
    -p "${SSH_PORT}" "${destination}" -- \
    sudo -n "${BROKER}" "${PROJECT_KEY}" "${operation}" "${PROFILE}" || status=$?

  if [ "${status}" -eq 255 ]; then
    die 9 "ssh could not reach ${destination}:${SSH_PORT}."
  fi
  return "${status}"
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

command_tunnel() {
  require_project
  [ -n "${SSH_DESTINATION}" ] || die 2 "--ssh USER@HOST is required to open a tunnel."
  need ssh "it is the transport."
  need jq "the broker answers in JSON."

  local endpoint status=0
  endpoint="$(broker endpoint "${SSH_DESTINATION}")" || status=$?
  [ "${status}" -eq 0 ] || exit "${status}"

  # The far end is the CONTAINER (ADR 0044). Nothing is published; the host
  # reaches the container because it is the gateway of that bridge, and the
  # outside world reaches neither. The near end is the ALLOCATED port, which is
  # stable across redeploy, restart and reboot -- so a saved command keeps
  # working even though the address it forwards to does not.
  local remote_host remote_port role database allocated
  remote_host="$(printf '%s' "${endpoint}" | jq -r '.host')"
  remote_port="$(printf '%s' "${endpoint}" | jq -r '.port')"
  allocated="$(printf '%s' "${endpoint}" | jq -r '.local_port')"
  role="$(printf '%s' "${endpoint}" | jq -r '.role')"
  database="$(printf '%s' "${endpoint}" | jq -r '.database')"
  [ -n "${remote_port}" ] && [ "${remote_port}" != "null" ] \
    || die 5 "the broker returned no port for ${PROJECT_KEY}/${PROFILE}."
  [ -n "${allocated}" ] && [ "${allocated}" != "null" ] \
    || die 5 "the broker returned no allocated local port for ${PROJECT_KEY}/${PROFILE}."

  local local_port="${LOCAL_PORT:-${allocated}}"
  local file
  file="$(state_file "${PROJECT_KEY}" "${PROFILE}")"

  if [ -f "${file}" ]; then
    local existing pid started args
    existing="$(cat "${file}")"
    pid="$(printf '%s' "${existing}" | jq -r '.pid')"
    started="$(printf '%s' "${existing}" | jq -r '.started')"
    args="$(printf '%s' "${existing}" | jq -r '.args')"
    if process_matches "${pid}" "${started}" "${args}"; then
      printf 'connect: a tunnel for %s/%s is already open on %s:%s (pid %s)\n' \
        "${PROJECT_KEY}" "${PROFILE}" "${LOCAL_BIND}" \
        "$(printf '%s' "${existing}" | jq -r '.local_port')" "${pid}"
      return 0
    fi
    quarantine "${file}" "a record was left behind by a tunnel that is no longer running"
  fi

  ssh "${SSH_BASE_OPTIONS[@]}" ${SSH_OPTIONS[@]+"${SSH_OPTIONS[@]}"} \
    -p "${SSH_PORT}" -N \
    -L "${LOCAL_BIND}:${local_port}:${remote_host}:${remote_port}" \
    "${SSH_DESTINATION}" &
  local pid=$!

  # ExitOnForwardFailure makes a bind failure an exit rather than a warning, so
  # a process that is still alive a moment later is one that got its forward.
  # This is the only place a sleep is defensible here: the alternative is
  # reporting a tunnel that has already died, which is exactly the class of
  # false green this project keeps producing.
  sleep 1
  if ! kill -0 "${pid}" 2>/dev/null; then
    wait "${pid}" 2>/dev/null || true
    die 9 "the forward did not come up. ${LOCAL_BIND}:${local_port} may already be in use, or the host refused the forward."
  fi

  local started args
  started="$(ps -p "${pid}" -o lstart=)"
  args="$(ps -p "${pid}" -o args=)"

  local previous_umask
  previous_umask="$(umask)"
  umask 077
  jq -n \
    --arg project "${PROJECT_KEY}" \
    --arg profile "${PROFILE}" \
    --arg destination "${SSH_DESTINATION}" \
    --arg ssh_port "${SSH_PORT}" \
    --arg bind "${LOCAL_BIND}" \
    --arg local_port "${local_port}" \
    --arg remote_host "${remote_host}" \
    --arg remote_port "${remote_port}" \
    --arg role "${role}" \
    --arg database "${database}" \
    --arg pid "${pid}" \
    --arg started "${started}" \
    --arg args "${args}" \
    '{project: $project, profile: $profile, ssh_destination: $destination,
      ssh_port: ($ssh_port|tonumber), bind: $bind,
      local_port: ($local_port|tonumber), remote_host: $remote_host,
      remote_port: ($remote_port|tonumber), role: $role, database: $database,
      pid: ($pid|tonumber), started: $started, args: $args}' > "${file}"
  umask "${previous_umask}"

  printf 'connect: %s/%s is forwarded to %s:%s (pid %s)\n' \
    "${PROJECT_KEY}" "${PROFILE}" "${LOCAL_BIND}" "${local_port}" "${pid}"
  printf 'connect: close it with: bin/connect.sh stop --project %s --profile %s\n' \
    "${PROJECT_KEY}" "${PROFILE}"
}

command_status() {
  need jq "tunnel records are JSON."
  local root file any=0
  root="$(state_root)"
  for file in "${root}"/tunnels/*.json; do
    [ -e "${file}" ] || continue
    any=1
    local record pid project profile port
    record="$(cat "${file}")"
    project="$(printf '%s' "${record}" | jq -r '.project')"
    profile="$(printf '%s' "${record}" | jq -r '.profile')"
    if [ -n "${PROJECT_KEY}" ] && [ "${project}" != "${PROJECT_KEY}" ]; then
      continue
    fi
    pid="$(printf '%s' "${record}" | jq -r '.pid')"
    port="$(printf '%s' "${record}" | jq -r '.local_port')"
    if process_matches "${pid}" \
      "$(printf '%s' "${record}" | jq -r '.started')" \
      "$(printf '%s' "${record}" | jq -r '.args')"; then
      printf '  live      %-24s %-16s %s:%s  pid %s\n' \
        "${project}" "${profile}" "${LOCAL_BIND}" "${port}" "${pid}"
    else
      printf '  stale     %-24s %-16s %s:%s\n' \
        "${project}" "${profile}" "${LOCAL_BIND}" "${port}"
      quarantine "${file}" "the recorded process is gone or is not the one recorded"
    fi
  done
  [ "${any}" -eq 1 ] || printf '  (no tunnels recorded)\n'
}

command_stop() {
  need jq "tunnel records are JSON."
  if [ "${STOP_ALL}" -eq 0 ]; then
    require_project
  fi

  local root file stopped=0
  root="$(state_root)"
  for file in "${root}"/tunnels/*.json; do
    [ -e "${file}" ] || continue
    local record project profile pid
    record="$(cat "${file}")"
    project="$(printf '%s' "${record}" | jq -r '.project')"
    profile="$(printf '%s' "${record}" | jq -r '.profile')"
    if [ "${STOP_ALL}" -eq 0 ]; then
      [ "${project}" = "${PROJECT_KEY}" ] || continue
      [ "${profile}" = "${PROFILE}" ] || continue
    fi
    pid="$(printf '%s' "${record}" | jq -r '.pid')"

    if process_matches "${pid}" \
      "$(printf '%s' "${record}" | jq -r '.started')" \
      "$(printf '%s' "${record}" | jq -r '.args')"; then
      kill "${pid}"
      rm -f "${file}"
      printf 'connect: closed %s/%s (pid %s)\n' "${project}" "${profile}" "${pid}"
      stopped=$((stopped + 1))
    else
      quarantine "${file}" "refusing to signal pid ${pid}: it is not the process this record describes"
    fi
  done

  if [ "${stopped}" -eq 0 ]; then
    die 4 "no live tunnel matched."
  fi
}

connection_environment() {
  local record="$1"
  local port role database
  port="$(printf '%s' "${record}" | jq -r '.local_port')"
  role="$(printf '%s' "${record}" | jq -r '.role')"
  database="$(printf '%s' "${record}" | jq -r '.database')"

  printf 'PGHOST=%s\n' "${LOCAL_BIND}"
  printf 'PGPORT=%s\n' "${port}"
  printf 'PGUSER=%s\n' "${role}"
  printf 'PGDATABASE=%s\n' "${database}"
  # The channel's confidentiality is SSH's, and the far end of the forward is
  # the host's own loopback. `disable` is what is actually happening; `require`
  # here would claim a TLS session that does not exist.
  printf 'PGSSLMODE=disable\n'
  printf 'PGAPPNAME=agentic-postgres-connect\n'
  printf 'DATABASE_URL=postgresql://%s@%s:%s/%s\n' \
    "${role}" "${LOCAL_BIND}" "${port}" "${database}"
  printf 'APG_PROJECT_KEY=%s\n' "$(printf '%s' "${record}" | jq -r '.project')"
  printf 'APG_ACCESS_PROFILE=%s\n' "$(printf '%s' "${record}" | jq -r '.profile')"
}

command_print_env() {
  require_project
  need jq "tunnel records are JSON."
  local record
  record="$(require_live_tunnel)"
  connection_environment "${record}"
  printf '\n'
  printf '# No password is printed. Run a client through bin/connect.sh exec,\n'
  printf '# which sets PGPASSFILE to a 0600 file for the child process only.\n'
}

# Deliberately a global, and this is not a style preference. An EXIT trap runs
# after the function that set up the credential has returned, so a `local` here
# would be out of scope by the time the trap fired: the trap would expand to the
# empty string, `rm -f ""` would succeed doing nothing, and the credential file
# would survive on disk while every visible sign said it had been cleaned up.
PGPASS_PATH=""

cleanup_credential() {
  if [ -n "${PGPASS_PATH}" ]; then
    rm -f "${PGPASS_PATH}"
  fi
}

# Writes the credential into a private file and names it through PGPASSFILE.
#
# `printf` is a shell builtin, so the value never becomes an argument vector any
# other process can read from /proc. The file is created under umask 077 in a
# directory this script already refused to use unless it was 0700 and ours, and
# it is removed by the EXIT trap whether the child succeeded, failed or was
# interrupted.
write_pgpass() {
  local record="$1" path="$2"
  local port role database password status=0
  port="$(printf '%s' "${record}" | jq -r '.local_port')"
  role="$(printf '%s' "${record}" | jq -r '.role')"
  database="$(printf '%s' "${record}" | jq -r '.database')"
  SSH_DESTINATION="$(printf '%s' "${record}" | jq -r '.ssh_destination')"
  SSH_PORT="$(printf '%s' "${record}" | jq -r '.ssh_port')"

  password="$(broker password "${SSH_DESTINATION}")" || status=$?
  [ "${status}" -eq 0 ] || exit "${status}"
  [ -n "${password}" ] || die 8 "the broker returned an empty credential."

  # A colon or a backslash in a password is a field separator to libpq unless it
  # is escaped. Unescaped, the line parses into different fields and the failure
  # is "no password supplied", which sends the reader to the wrong place.
  local escaped
  escaped="$(printf '%s' "${password}" | sed -e 's/\\/\\\\/g' -e 's/:/\\:/g')"

  local previous_umask
  previous_umask="$(umask)"
  umask 077
  printf '%s:%s:%s:%s:%s\n' "${LOCAL_BIND}" "${port}" "${database}" "${role}" "${escaped}" \
    > "${path}"
  umask "${previous_umask}"
  chmod 600 "${path}"
}

command_psql() {
  require_project
  need jq "tunnel records are JSON."
  need psql "it is what this command runs."
  local record
  record="$(require_live_tunnel)"

  PGPASS_PATH="$(state_root)/tunnels/.pgpass.$$"
  trap cleanup_credential EXIT INT TERM
  write_pgpass "${record}" "${PGPASS_PATH}"

  PGPASSFILE="${PGPASS_PATH}" \
  PGHOST="${LOCAL_BIND}" \
  PGPORT="$(printf '%s' "${record}" | jq -r '.local_port')" \
  PGUSER="$(printf '%s' "${record}" | jq -r '.role')" \
  PGDATABASE="$(printf '%s' "${record}" | jq -r '.database')" \
  PGAPPNAME="agentic-postgres-connect" \
    psql
}

command_exec() {
  require_project
  need jq "tunnel records are JSON."
  [ "${#CHILD[@]}" -gt 0 ] || die 2 "exec requires a command after --."
  local record
  record="$(require_live_tunnel)"

  PGPASS_PATH="$(state_root)/tunnels/.pgpass.$$"
  trap cleanup_credential EXIT INT TERM
  write_pgpass "${record}" "${PGPASS_PATH}"

  local line name value
  while IFS= read -r line; do
    name="${line%%=*}"
    value="${line#*=}"
    export "${name}=${value}"
  done < <(connection_environment "${record}")
  export PGPASSFILE="${PGPASS_PATH}"

  # Not exec: the trap has to survive the child so the credential file is
  # removed. The child's exit status is returned unchanged.
  "${CHILD[@]}"
}

# ---------------------------------------------------------------------------

main() {
  case "${1-}" in
    --help|-h) usage; return 0 ;;
    "") usage >&2; die 2 "a command is required." ;;
    tunnel|status|stop|print-env|psql|exec) COMMAND="$1"; shift ;;
    prisma-studio)
      die 2 "prisma-studio is not a command here. Run it through: bin/connect.sh exec --project KEY -- npx prisma studio"
      ;;
    *) usage >&2; die 2 "unknown command: $1" ;;
  esac

  parse_arguments "$@"
  validate_common
  cd "${ROOT_DIR}"

  case "${COMMAND}" in
    tunnel) command_tunnel ;;
    status) command_status ;;
    stop) command_stop ;;
    print-env) command_print_env ;;
    psql) command_psql ;;
    exec) command_exec ;;
  esac
}

main "$@"

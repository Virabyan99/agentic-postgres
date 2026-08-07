#!/usr/bin/env bash
#
# The only supported way to invoke Compose in this repository.
#
# It exists because of one Compose behaviour: shell environment variables have
# *higher* interpolation precedence than --env-file values. So a stray
# COMPOSE_PROJECT_NAME or PYTHON_RUNTIME_IMAGE in an operator's shell would
# silently override the generated identity or the locked digest, and the model
# would render successfully against the wrong resources.
#
# The defence is an allowlist, not a denylist. `env -u` requires enumerating
# every name that could collide, which is unbounded and cannot be proven
# complete. `env -i` plus an explicit list of variables to keep is bounded, and
# a test proves an inherited COMPOSE_PROJECT_NAME does not reach Compose.
#
# Session 2 adds two scopes and one privilege gate (ADR 0013). What did NOT
# change: with no flags, every container-starting subcommand is still refused
# with exit 10. Starting a container became possible, but never by default and
# never without root.
#
# Usage:
#   bin/compose.sh <generated-project-dir> [compose arguments...]
#   sudo bin/compose.sh <generated-project-dir> --runtime <subcommand> [...]
#   bin/compose.sh --edge --host <host.yaml> [compose arguments...]
#   sudo bin/compose.sh --edge --host <host.yaml> --runtime <subcommand> [...]
#
# Exit codes (runbook §2 convention):
#   0   success (or Compose's own status)
#   2   invalid operator input
#   3   missing local prerequisite, unreachable Docker daemon, or --runtime
#       without root
#   5   the env files are not disjoint, or a secret source is outside the
#       project's own secret root
#   10  a container-starting subcommand was requested without --runtime, or a
#       subcommand outside the runtime allowlist was requested with it

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly LOCK_ENV="${ROOT_DIR}/versions.env"
readonly PROJECT_MODEL="${ROOT_DIR}/compose.yaml"
readonly EDGE_MODEL="${ROOT_DIR}/infra/edge/compose.yaml"

# Subcommands that create or start a container. Refused unless --runtime is
# given AND the caller is root. The first eight are unchanged from Session 1;
# what changed there is that there is now a documented way through it. `watch`
# and `scale` were added after an audit against the currently installed
# Compose found both start containers and neither was refused (ADR 0022).
readonly FORBIDDEN="up run start create restart exec attach cp watch scale"

# What --runtime actually permits. Deliberately smaller than FORBIDDEN's
# complement: exec, attach, run and cp reach inside a running container and
# nothing in Session 2's documented path needs them. An operator who does can
# say so in an ADR.
readonly RUNTIME_ALLOWED="up down restart build ps config logs"

# Subcommands that need a reachable daemon. `config` is rendered entirely by
# the client, so it deliberately is not in this list.
readonly NEEDS_DAEMON="ps top logs events port images kill down stop rm wait up restart build"

# Compose global flags that consume the following token as their value, so
# that token must never be mistaken for the subcommand. A flag written
# --flag=value needs no entry: the value is inside the same token and is
# already matched by first_subcommand's `-*` case below. Missing an entry
# here is not cosmetic -- for a value-taking flag ahead of a
# container-starting subcommand it can defeat FORBIDDEN and RUNTIME_ALLOWED
# entirely, which is how `--profile session2 up` bypassed both (ADR 0021).
readonly SUBCOMMAND_VALUE_FLAGS="--profile --file -f --env-file --project-name -p --project-directory --parallel --progress --ansi"

# Everything the Docker client legitimately needs, and nothing else. Each entry
# earns its place: HOME locates ~/.docker/config.json and therefore the active
# context; without it `docker compose` cannot find the daemon at all.
#
# Session 2 deliberately did NOT extend this list. Under sudo and under systemd
# the wrapper reads what it needs from its own environment and forwards none of
# it, and anything the runtime path requires is *set* below rather than
# inherited. Setting a value is strictly stronger than allowlisting one.
readonly KEEP_VARS="PATH HOME USER DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG DOCKER_CERT_PATH DOCKER_TLS_VERIFY"

# Where a project's secret generations may live. A `file:` secret source
# anywhere else is refused before anything starts.
readonly SECRET_ROOT="/var/lib/agentic-postgres/secrets"
readonly PROJECT_STATE_ROOT="/etc/agentic-postgres/projects"

# Subcommands whose effect on a running container makes a secret-source check
# worth paying for before they run.
readonly VALIDATES_SECRETS="up restart"

# Subcommands that start containers and therefore need the runtime override
# to already exist. down, ps, logs, config and build must stay usable without
# it -- a project whose override is missing (a partially installed rendered
# directory, or one deployed by an older release) must still be inspectable
# and tearable-down, which is exactly when an operator needs them.
readonly OVERRIDE_REQUIRED="up restart"

RUNTIME=0
EDGE=0
HOST_MANIFEST=""
PROJECT_DIR=""
TEMP_ENV=""
MODEL=""
PROJECT_NAME=""
OVERRIDE_PATH=""
declare -a COMPOSE_ARGS=()
declare -a ENV_FILE_ARGS=()
declare -a MODEL_FILE_ARGS=()

usage() {
  cat <<'USAGE'
Usage:
  bin/compose.sh <generated-project-dir> [compose arguments...]
  sudo bin/compose.sh <generated-project-dir> --runtime <subcommand> [...]
  bin/compose.sh --edge --host <host.yaml> [compose arguments...]
  sudo bin/compose.sh --edge --host <host.yaml> --runtime <subcommand> [...]

  <generated-project-dir>  A directory produced by ./deploy.sh --render-only,
                           containing compose.env.
  --edge                   Operate on the shared host edge plane
                           (infra/edge/compose.yaml) instead of a project.
  --host FILE              Required with --edge. The host manifest.
  --runtime                Permit container-starting subcommands. Requires root.

Examples:
  bin/compose.sh .generated/<project-key> --profile contract config
  bin/compose.sh .generated/<project-key> ps --quiet
  sudo bin/compose.sh .generated/<project-key> --runtime up -d --wait edge-probe
  sudo bin/compose.sh --edge --host host.yaml --runtime up -d --wait

Without --runtime, up, run, start, create, restart, exec, attach and cp are
refused. Environment variables are stripped to an explicit allowlist so that
nothing inherited from the caller can override a locked or generated value.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'compose: %s\n' "$*" >&2
  exit "$code"
}

# Interpreter resolution. Ubuntu ships no bare `python`, and sudo resets PATH to
# secure_path, so an operator's activated venv is invisible to anything invoked
# through it.
#
# This script is not itself a root command, which is exactly how it was missed:
# bin/edge.sh resolves an interpreter correctly and then calls this, which did
# not. The contract scan was scoped to what runs as root rather than to what
# root reaches.
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

cleanup() {
  if [ -n "${TEMP_ENV}" ]; then
    rm -f "${TEMP_ENV}"
  fi
}
trap cleanup EXIT

# Read one KEY=VALUE from an env file without shell-sourcing it. Sourcing would
# execute whatever the file contains; these files are generated, but the whole
# point of this wrapper is not to trust that.
read_var() {
  sed -n "s/^$2=//p" "$1" | head -n 1
}

# LC_ALL=C, and it is load-bearing. Under a UTF-8 locale `sort` collates with
# rules that treat `_` as ignorable at the primary level; `comm` then decides the
# input is not sorted, says so on stderr, and carries on -- producing an answer
# that can omit real overlaps. A disjointness check that reports "no overlap"
# because it gave up halfway is worse than no check, because the guarantee is
# still being claimed. Byte order is identical everywhere and is what `comm`
# expects.
#
# This surfaced only on the deployment host, which runs en_US.UTF-8 while the
# development machine does not.
env_keys() {
  sed -n 's/^\([A-Z][A-Z0-9_]*\)=.*/\1/p' "$1" | LC_ALL=C sort
}

# Every pair of env files must define disjoint variables, so no --env-file
# ordering can let one silently override another (runbook §7.2). Runtime mode
# has three files, so this is three comparisons rather than one.
assert_disjoint() {
  local overlap
  overlap="$(LC_ALL=C comm -12 <(env_keys "$1") <(env_keys "$2") || true)"
  if [ -n "${overlap}" ]; then
    printf 'compose: these variables are defined in both %s and %s:\n%s\n' "$1" "$2" "${overlap}" >&2
    die 5 "env files must define disjoint variables."
  fi
}

# Build the allowlisted environment once, so there is exactly one place the
# child environment is constructed and one thing for a test to assert about.
compose_env() {
  local -a preserved=()
  local name
  for name in ${KEEP_VARS}; do
    if [ -n "${!name-}" ]; then
      preserved+=("${name}=${!name}")
    fi
  done
  # Set, not inherited: BuildKit must be on, and neither it nor its progress
  # format may depend on the operator's shell.
  preserved+=("DOCKER_BUILDKIT=1" "BUILDKIT_PROGRESS=plain")
  printf '%s\n' "${preserved[@]}"
}

run_compose() {
  local -a preserved=()
  mapfile -t preserved < <(compose_env)
  env -i "${preserved[@]}" \
    docker compose \
    --project-name "${PROJECT_NAME}" \
    "${ENV_FILE_ARGS[@]}" \
    "${MODEL_FILE_ARGS[@]}" \
    "$@"
}

# Runtime mode may not mount a secret from outside the project's own generation
# tree. Checked against the *resolved* model rather than the committed one, so
# an override file cannot introduce a path the reviewed model never showed.
assert_secret_sources_are_project_scoped() {
  local project_key="$1" resolved expected source
  expected="${SECRET_ROOT}/${project_key}/"

  resolved="$(run_compose config 2>/dev/null)" || return 0

  while IFS= read -r source; do
    [ -n "${source}" ] || continue
    case "${source}" in
      "${expected}"*) ;;
      *) die 5 "secret source ${source} is outside ${expected}" ;;
    esac
  done < <(printf '%s\n' "${resolved}" | sed -n 's/^[[:space:]]*file:[[:space:]]*//p')
}

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --edge) EDGE=1; shift ;;
      --runtime) RUNTIME=1; shift ;;
      --host)
        [ "$#" -ge 2 ] || die 2 "--host requires a file path."
        HOST_MANIFEST="$2"; shift 2 ;;
      --host=*) HOST_MANIFEST="${1#--host=}"; shift ;;
      *) break ;;
    esac
  done

  if [ "${EDGE}" -eq 0 ]; then
    if [ "$#" -lt 1 ]; then
      usage >&2
      die 2 "a generated project directory is required."
    fi
    PROJECT_DIR="$1"
    shift
    # The runbook writes --runtime after the project directory, so accept it in
    # both positions rather than making an operator remember which.
    while [ "$#" -gt 0 ] && [ "$1" = "--runtime" ]; do
      RUNTIME=1
      shift
    done
  fi

  COMPOSE_ARGS=("$@")
}

configure_edge_scope() {
  [ -n "${HOST_MANIFEST}" ] || die 2 "--edge requires --host FILE."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"
  [ -f "${EDGE_MODEL}" ] || die 3 "missing ${EDGE_MODEL}"

  MODEL="${EDGE_MODEL}"
  MODEL_FILE_ARGS=(--file "${MODEL}")

  # Derived from host.yaml so that `--edge config` works offline and in CI,
  # where the root-owned /var/lib/agentic-postgres/edge/compose.env does not
  # exist. umask keeps the temporary file owner-only.
  TEMP_ENV="$(umask 077 && mktemp)"

  # Resolved first, so a missing interpreter is reported as a missing
  # interpreter. Folding both failures into one message told an operator their
  # host manifest was invalid when the real answer was that nothing could run
  # the validator -- a diagnosis that sends the reader to the wrong file.
  local interpreter
  interpreter="$(python_bin)"
  "${interpreter}" "${ROOT_DIR}/bin/render-config.py" \
    --host "${HOST_MANIFEST}" --edge-env > "${TEMP_ENV}" \
    || die 2 "host manifest is not valid: ${HOST_MANIFEST}"

  assert_disjoint "${LOCK_ENV}" "${TEMP_ENV}"
  ENV_FILE_ARGS+=(--env-file "${TEMP_ENV}")

  PROJECT_NAME="$(read_var "${TEMP_ENV}" EDGE_STACK_NAME)"
  [ -n "${PROJECT_NAME}" ] || die 2 "EDGE_STACK_NAME could not be derived."
}

configure_project_scope() {
  [ -d "${PROJECT_DIR}" ] || die 2 "not a directory: ${PROJECT_DIR}"

  local project_env="${PROJECT_DIR}/compose.env"
  [ -f "${project_env}" ] \
    || die 2 "no compose.env in ${PROJECT_DIR}; run ./deploy.sh --render-only first"
  [ -f "${PROJECT_MODEL}" ] || die 3 "missing ${PROJECT_MODEL}"

  MODEL="${PROJECT_MODEL}"
  MODEL_FILE_ARGS=(--file "${MODEL}")

  assert_disjoint "${LOCK_ENV}" "${project_env}"
  ENV_FILE_ARGS+=(--env-file "${project_env}")

  PROJECT_NAME="$(read_var "${project_env}" COMPOSE_PROJECT_NAME)"
  [ -n "${PROJECT_NAME}" ] || die 2 "COMPOSE_PROJECT_NAME is absent from ${project_env}"

  PROJECT_KEY="$(read_var "${project_env}" PROJECT_KEY)"

  # The host-derived half of a project's environment. Written by deploy.sh and
  # exists only after a Session 2 deployment, which is why this is conditional
  # rather than required: ordinary validation must work without a host.
  local runtime_env="${PROJECT_STATE_ROOT}/${PROJECT_KEY}/compose.env"

  # The override carrying the fully rendered router label keys. deploy.sh
  # writes it into the rendered directory alongside the rendered compose.env --
  # the same directory PROJECT_DIR already names -- not under PROJECT_STATE_ROOT.
  # Required under --runtime, but that is enforced in main(), after the
  # privilege check: an unprivileged caller must be refused for lacking root
  # before anything else is said about the project.
  OVERRIDE_PATH="${PROJECT_DIR}/runtime-compose.override.yaml"

  if [ "${RUNTIME}" -eq 1 ] && [ -f "${runtime_env}" ]; then
    assert_disjoint "${LOCK_ENV}" "${runtime_env}"
    assert_disjoint "${project_env}" "${runtime_env}"
    ENV_FILE_ARGS+=(--env-file "${runtime_env}")
  fi
  if [ "${RUNTIME}" -eq 1 ] && [ -f "${OVERRIDE_PATH}" ]; then
    MODEL_FILE_ARGS+=(--file "${OVERRIDE_PATH}")
  fi
}

# Finds the Compose subcommand in COMPOSE_ARGS. Skips flags, and skips the
# separate value of any flag listed in SUBCOMMAND_VALUE_FLAGS, so that value
# is never returned in place of the subcommand that follows it (ADR 0021).
first_subcommand() {
  local argument skip_value=0
  for argument in "${COMPOSE_ARGS[@]+"${COMPOSE_ARGS[@]}"}"; do
    if [ "${skip_value}" -eq 1 ]; then
      skip_value=0
      continue
    fi
    case "${argument}" in
      --*=*) ;;
      -*)
        if in_list "${argument}" "${SUBCOMMAND_VALUE_FLAGS}"; then
          skip_value=1
        fi
        ;;
      *) printf '%s' "${argument}"; return 0 ;;
    esac
  done
}

in_list() {
  local needle="$1" item
  shift
  for item in $1; do
    [ "${needle}" = "${item}" ] && return 0
  done
  return 1
}

main() {
  parse_arguments "$@"

  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."
  [ -f "${LOCK_ENV}" ] || die 3 "missing ${LOCK_ENV}; run bin/lock-versions.sh --update"

  ENV_FILE_ARGS=(--env-file "${LOCK_ENV}")
  PROJECT_KEY=""

  if [ "${EDGE}" -eq 1 ]; then
    configure_edge_scope
  else
    configure_project_scope
  fi

  local subcommand
  subcommand="$(first_subcommand)"

  if [ "${RUNTIME}" -eq 1 ]; then
    [ "$(id -u)" -eq 0 ] || die 3 "--runtime requires root; Docker access is root-equivalent."
    if ! in_list "${subcommand}" "${RUNTIME_ALLOWED}"; then
      die 10 "'${subcommand}' is not permitted in --runtime mode; allowed: ${RUNTIME_ALLOWED}"
    fi
    # A project cannot be routed without its override: no traefik.enable, no
    # router labels. Missing it here must fail loudly rather than start a
    # container that --wait reports healthy and the edge 404s on. Checked only
    # in project scope -- --edge has no override.
    if [ "${EDGE}" -eq 0 ] && in_list "${subcommand}" "${OVERRIDE_REQUIRED}"; then
      [ -f "${OVERRIDE_PATH}" ] \
        || die 3 "no runtime override for ${PROJECT_KEY} at ${OVERRIDE_PATH}; the project is unroutable without it."
    fi
  elif in_list "${subcommand}" "${FORBIDDEN}"; then
    die 10 "'${subcommand}' would start or create a container; this requires --runtime with root."
  fi

  # Refused in BOTH scopes, for two different reasons that arrive at the same
  # rule (ADR 0030).
  #
  # In edge scope: ACME state is a bind mount, so `down -v` cannot reach it --
  # but refusing the flag removes the question entirely, and a deleted
  # production ACME file is how a failed renewal becomes an exhausted Let's
  # Encrypt rate limit.
  #
  # In project scope, from Session 3: POSTGRES_VOLUME_NAME finally holds
  # something. `down -v` is the one command that destroys a database while
  # looking like a stop -- same word an operator types to free a port, same
  # muscle memory, and no confirmation. Volume removal exists in exactly one
  # place, and it is not this one: an explicit disposable-project command that
  # refuses any key but the declared disposable one.
  local argument
  for argument in "${COMPOSE_ARGS[@]+"${COMPOSE_ARGS[@]}"}"; do
    case "${argument}" in
      -v|--volumes)
        if [ "${EDGE}" -eq 1 ]; then
          die 2 "--volumes is refused in edge mode; it endangers ACME state."
        fi
        die 2 "--volumes is refused in project mode; it would destroy the database volume."
        ;;
    esac
  done

  if in_list "${subcommand}" "${NEEDS_DAEMON}"; then
    docker info >/dev/null 2>&1 \
      || die 3 "the Docker daemon is unreachable, which '${subcommand}' requires. ('config' does not.)"
  fi

  if [ "${RUNTIME}" -eq 1 ] && [ "${EDGE}" -eq 0 ] \
    && in_list "${subcommand}" "${VALIDATES_SECRETS}"; then
    assert_secret_sources_are_project_scoped "${PROJECT_KEY}"
  fi

  local -a preserved=()
  mapfile -t preserved < <(compose_env)

  # -p is passed even though the model also sets `name`, so the project name is
  # explicit at both layers and a mismatch is visible rather than silent.
  exec env -i "${preserved[@]}" \
    docker compose \
    --project-name "${PROJECT_NAME}" \
    "${ENV_FILE_ARGS[@]}" \
    "${MODEL_FILE_ARGS[@]}" \
    "${COMPOSE_ARGS[@]+"${COMPOSE_ARGS[@]}"}"
}

main "$@"

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
# Usage:
#   bin/compose.sh <generated-project-dir> [compose arguments...]
#
# Exit codes (runbook §2 convention):
#   0   success (or Compose's own status)
#   2   invalid operator input
#   3   missing local prerequisite, or the Docker daemon is unreachable
#   5   the two env files are not disjoint
#   10  a container-starting subcommand was requested

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly LOCK_ENV="${ROOT_DIR}/versions.env"
readonly MODEL="${ROOT_DIR}/compose.yaml"

# Subcommands that would create or start a container. Session 1 starts nothing.
readonly FORBIDDEN="up run start create restart exec attach cp"

# Subcommands that need a reachable daemon. `config` is rendered entirely by
# the client, so it deliberately is not in this list.
readonly NEEDS_DAEMON="ps top logs events port images kill down stop rm wait"

# Everything the Docker client legitimately needs, and nothing else. Each entry
# earns its place: HOME locates ~/.docker/config.json and therefore the active
# context; without it `docker compose` cannot find the daemon at all.
readonly KEEP_VARS="PATH HOME USER DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG DOCKER_CERT_PATH DOCKER_TLS_VERIFY"

usage() {
  cat <<'USAGE'
Usage: bin/compose.sh <generated-project-dir> [compose arguments...]

  <generated-project-dir>  A directory produced by ./deploy.sh --render-only,
                           containing compose.env.

Examples:
  bin/compose.sh .generated/<project-key> --profile contract config
  bin/compose.sh .generated/<project-key> ps --quiet

Session 1 refuses up, run, start, create, restart, exec, attach, and cp.
Environment variables are stripped to an explicit allowlist so that nothing
inherited from the caller can override a locked or generated value.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'compose: %s\n' "$*" >&2
  exit "$code"
}

# Read one KEY=VALUE from an env file without shell-sourcing it. Sourcing would
# execute whatever the file contains; these files are generated, but the whole
# point of this wrapper is not to trust that.
read_var() {
  local file="$1" key="$2"
  sed -n "s/^${key}=//p" "${file}" | head -n 1
}

env_keys() {
  sed -n 's/^\([A-Z][A-Z0-9_]*\)=.*/\1/p' "$1" | sort
}

main() {
  case "${1-}" in
    --help|-h)
      usage
      return 0
      ;;
    "")
      usage >&2
      die 2 "a generated project directory is required."
      ;;
  esac

  local project_dir="$1"
  shift

  [ -d "${project_dir}" ] || die 2 "not a directory: ${project_dir}"
  local project_env="${project_dir}/compose.env"
  [ -f "${project_env}" ] || die 2 "no compose.env in ${project_dir}; run ./deploy.sh --render-only first"
  [ -f "${LOCK_ENV}" ] || die 3 "missing ${LOCK_ENV}; run bin/lock-versions.sh --update"
  [ -f "${MODEL}" ] || die 3 "missing ${MODEL}"

  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."

  # Find the first non-flag argument: that is the Compose subcommand.
  local subcommand="" argument
  for argument in "$@"; do
    case "${argument}" in
      -*) ;;
      *) subcommand="${argument}"; break ;;
    esac
  done

  local forbidden
  for forbidden in ${FORBIDDEN}; do
    if [ "${subcommand}" = "${forbidden}" ]; then
      die 10 "'${subcommand}' would start or create a container; Session 1 starts nothing. Deployment begins in Session 2."
    fi
  done

  local needs
  for needs in ${NEEDS_DAEMON}; do
    if [ "${subcommand}" = "${needs}" ]; then
      docker info >/dev/null 2>&1 \
        || die 3 "the Docker daemon is unreachable, which '${subcommand}' requires. ('config' does not.)"
      break
    fi
  done

  # Runbook §7.2: the two env files must define disjoint namespaces, so neither
  # can silently shadow the other regardless of --env-file ordering.
  local overlap
  overlap="$(comm -12 <(env_keys "${LOCK_ENV}") <(env_keys "${project_env}") || true)"
  if [ -n "${overlap}" ]; then
    printf 'compose: these variables are defined in both env files:\n%s\n' "${overlap}" >&2
    die 5 "versions.env and compose.env must define disjoint variables."
  fi

  local project_name
  project_name="$(read_var "${project_env}" COMPOSE_PROJECT_NAME)"
  [ -n "${project_name}" ] || die 2 "COMPOSE_PROJECT_NAME is absent from ${project_env}"

  # Build the allowlist as explicit NAME=VALUE assignments for `env -i`.
  local -a preserved=()
  local name
  for name in ${KEEP_VARS}; do
    if [ -n "${!name-}" ]; then
      preserved+=("${name}=${!name}")
    fi
  done

  # -p is passed even though compose.yaml also sets `name`, so the project name
  # is explicit at both layers and a mismatch is visible rather than silent.
  exec env -i "${preserved[@]}" \
    docker compose \
    --project-name "${project_name}" \
    --env-file "${LOCK_ENV}" \
    --env-file "${project_env}" \
    --file "${MODEL}" \
    "$@"
}

main "$@"

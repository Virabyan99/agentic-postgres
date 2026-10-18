#!/usr/bin/env bash
#
# Sourced, never run: the telemetry plane's networks, ensured (Session 42,
# ADR 0277, D2563, D2574).
#
# `bin/telemetry.sh up` ensures all three; every project's runtime ensures the
# INGEST one before its collector starts, so a project never waits for the
# plane. Two units can therefore create the same network at once -- the shape
# of D2558 -- and the loser's `docker network create` fails with "already
# exists". So a failed create is not the verdict: the network is read AGAIN, and
# a network of that name carrying OUR label and the wanted `internal` flag is
# the state wanted. A network of that name without the label is somebody
# else's, and is refused rather than adopted.
#
# Defines: ensure_telemetry_network NAME yes|no
#   (yes = --internal). Returns 0 when the network holds; prints Docker's text
#   and returns 9 otherwise.

readonly TELEMETRY_NETWORK_LABEL='apg.network'

telemetry_network_holds() {
  local name="$1" internal="$2" seen
  seen="$(docker network inspect --format \
    "{{index .Labels \"${TELEMETRY_NETWORK_LABEL}\"}} {{.Internal}}" "${name}" 2>/dev/null)" || return 1
  [ "${seen}" = "${name} $([ "${internal}" = yes ] && echo true || echo false)" ]
}

ensure_telemetry_network() {
  local name="$1" internal="$2" output
  local -a args=(--label "${TELEMETRY_NETWORK_LABEL}=${name}")
  [ "${internal}" = yes ] && args+=(--internal)
  if telemetry_network_holds "${name}" "${internal}"; then
    return 0
  fi
  if output="$(docker network create "${args[@]}" "${name}" 2>&1)"; then
    return 0
  fi
  if telemetry_network_holds "${name}" "${internal}"; then
    printf 'telemetry-network: %s was created by another unit (%s)\n' "${name}" "${output}" >&2
    return 0
  fi
  printf '%s\n' "${output}" >&2
  printf 'telemetry-network: %s exists without this plane'"'"'s label or with the wrong internal flag, or could not be created\n' "${name}" >&2
  return 9
}

#!/usr/bin/env bash
#
# One front door over the commands that already exist.
#
#   bin/apg.sh <verb> [arguments...]     runs bin/<verb>.sh, unchanged
#   bin/apg.sh --list                    every verb, derived
#   bin/apg.sh --help                    this message
#
# **This dispatcher holds no list of verbs, and that is the decision** (ADR 0002).
# A dispatcher that enumerated them would be a second authority for which
# commands exist, beside `bin/` itself and beside `SHELL_COMMANDS` in
# tests/contract/test_cli_contract.py -- and the failure mode of a stale second
# list is a verb that silently stops being reachable. So a verb IS a script:
# `apg doctor` resolves `bin/doctor.sh` by construction, and a command added to
# `bin/` is reachable the moment it lands, with nothing to remember.
#
# **It rewrites nothing and moves nothing.** Every `bin/*.sh` keeps working
# exactly as before; this adds a name, not a layer. `exec` replaces this process,
# so the verb's exit code, stdout, stderr and signal behaviour are its own and
# this script cannot alter them.
#
# **The verb is pattern-checked before it becomes a path.** `apg ../../etc/thing`
# must not resolve, and a check that built the path first and tested for
# existence afterwards would be relying on nothing accidentally being there.
# `installed_release.validate_commit` carries the same rule for the same reason:
# validate before the value is used as a path component, never after.
#
# **`deploy` is the one verb whose script is not in `bin/`.** It is `./deploy.sh`
# at the repository root, where it has lived since Session 1 because it is the
# renderer and the deploy entry point rather than an operator subcommand. Named
# here with its reason rather than reached by a wildcard: a category-shaped
# exemption would be a loophole, and one named case is a decision somebody can
# disagree with (D694).
#
# Not installed onto PATH, deliberately -- see `usage`.
#
# Exit codes: this script itself uses 0 (help, list) and 2 (no verb, unknown
# verb, malformed verb). Everything else is the verb's own.

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

#: A verb is lowercase alphanumerics and hyphens, starting with a letter. No
#: dots, so `..` cannot appear; no slashes, so no path can be smuggled in.
#:
#: **An anchored bash REGEX, and the first version was a `case` glob** -- which
#: looks identical and is not. In glob syntax `*` is not a quantifier on the
#: preceding bracket expression: it matches any string, `/` and `.` included. So
#: `[a-z][a-z0-9-]*` as a glob accepted `ab../../etc/passwd`, measured, against a
#: control where the two forms disagreed on exactly that one input.
#:
#: Nothing was reachable through it -- the `-f` test below refused the path that
#: did not exist -- and that is precisely the arrangement this file's own header
#: says not to build: a validation that passes and a file check that saves it is
#: relying on nothing accidentally being there. shellcheck's SC2254 is what
#: pointed at it.
readonly VERB_PATTERN='^[a-z][a-z0-9-]*$'

usage() {
  cat <<'USAGE'
Usage: bin/apg.sh <verb> [arguments...]
       bin/apg.sh --list
       bin/apg.sh --help

One front door over the operator commands in bin/. A verb is the name of the
script that implements it, so `apg doctor --verbose` runs `bin/doctor.sh
--verbose` and every argument reaches it untouched.

  --list    Print every verb this checkout provides, one per line, derived from
            bin/ rather than from a list kept here.

This is not installed onto PATH, and that is a decision rather than an omission.
Installing it would mean a copy outside the release, and a host that keeps
running whichever copy it was provisioned with is the failure ADR 0037 records
for the systemd launchers -- a two-session-old launcher deployed a project
through the wrong session and only then failed. Run it as `bin/apg.sh` from a
checkout, or add your own alias, which is yours to keep current.

Run `bin/apg.sh <verb> --help` for what a verb does. This adds no options of its
own to any verb and changes none of their exit codes.
USAGE
}

#: Where a verb's script lives, or empty if the verb resolves to nothing.
#:
#: Two roots, and the second has exactly one member. Resolution is by
#: construction rather than by search: there is no glob here whose result could
#: depend on what else happens to be in the directory.
script_for() {
  local verb="$1"

  if [ "${verb}" = "deploy" ]; then
    printf '%s' "${ROOT_DIR}/deploy.sh"
    return 0
  fi

  local candidate="${ROOT_DIR}/bin/${verb}.sh"
  if [ -f "${candidate}" ]; then
    printf '%s' "${candidate}"
    return 0
  fi

  return 1
}

#: Every verb, derived. `deploy` is added because its script is elsewhere.
list_verbs() {
  {
    printf 'deploy\n'
    for path in "${ROOT_DIR}"/bin/*.sh; do
      local name
      name="$(basename "${path}" .sh)"
      [ "${name}" = "apg" ] && continue
      printf '%s\n' "${name}"
    done
  } | sort
}

refuse_unknown() {
  local verb="$1"
  printf 'apg: no such verb: %s\n' "${verb}" >&2
  printf 'apg: run "bin/apg.sh --list" for every verb this checkout provides.\n' >&2
  exit 2
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    exit 2
  fi

  case "$1" in
    --help | -h | help)
      usage
      exit 0
      ;;
    --list)
      list_verbs
      exit 0
      ;;
  esac

  local verb="$1"
  shift

  # Checked before it becomes a path component, never after.
  if ! [[ "${verb}" =~ ${VERB_PATTERN} ]]; then
    printf 'apg: %s is not a verb name.\n' "${verb}" >&2
    printf 'apg: a verb is lowercase letters, digits and hyphens, starting with a letter.\n' >&2
    exit 2
  fi

  local script
  script="$(script_for "${verb}")" || refuse_unknown "${verb}"

  exec "${script}" "$@"
}

main "$@"

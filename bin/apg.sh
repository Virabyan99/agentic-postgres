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
# **It rewrites nothing and moves nothing, with ONE exception it announces.**
# Every `bin/*.sh` keeps working exactly as before; this adds a name, not a
# layer. `exec` replaces this process, so the verb's exit code, stdout, stderr
# and signal behaviour are its own and this script cannot alter them.
#
# The exception is `APG_PROJECT` (ADR 0207 §2). When it is set, the verb's own
# `--help` names `--project` as a flag, and the arguments carry none, this
# appends `--project "$APG_PROJECT"` -- and says so on stderr, in one line,
# every time it does. **Which verbs take the flag is DERIVED by reading their
# help, never kept here**: a list would be the second authority the paragraph
# above exists to refuse, and it would go stale the first time a verb grew the
# flag. Measured 2026-09-14: 18 of 65 verbs name it, and reading one verb's
# help costs about 15 ms.
#
# The derivation deliberately UNDER-applies, and that is the safe direction. A
# missed default is a command that behaves exactly as it did yesterday; a wrong
# match is a command that stops working. Sixteen `session-NN-check` gates accept
# `--project` while documenting only `--project-a-outputs`, so they receive
# nothing (D1317). `dr-kit` was the one verb whose usage named a flag only one
# of its two subcommands took, and its usage was corrected rather than exempted
# here (D1316) -- a usage block that names a flag the command does not take is a
# `DX-002` failure on its own terms, and an exemption list would hide it.
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
# verb, malformed verb, an unreadable `APG_PROJECT`). Everything else is the
# verb's own.

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

APG_PROJECT -- a default project manifest, with three rules:

  * only when the verb takes a manifest. The verb's own `--help` is read, and
    the default is appended only if that text documents `--project FILE`. Which
    verbs those are is derived at the moment you run one, never kept in a list
    here, so a verb that grows the flag tomorrow is covered tomorrow. A verb
    that documents `--project KEY` takes a deployed project's key rather than a
    path and is left alone -- handing it this value would not be refused, it
    would be answered wrongly.
  * only when you gave none. An explicit `--project` anywhere in your
    arguments wins, in either spelling, and nothing is appended or printed.
    `--help` and `-h` also suppress it: a help request that grew a flag would
    print a sentence about a file you never mentioned.
  * always announced. Every time it is applied you get one line on stderr,
    `apg: --project <path> (from APG_PROJECT)`. A default you cannot see is a
    default that deploys the wrong project one day.

A value naming no readable file is refused with exit 2 before the verb runs.

  export APG_PROJECT=project.alpha.yaml
  bin/apg.sh dev up                 # runs bin/dev.sh up --project project.alpha.yaml

**`sudo` drops it** unless you pass `--preserve-env=APG_PROJECT`, and the
announcement line is how you know whether it reached the verb: no line means no
default was applied, whatever your shell has exported.
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

#: Whether `--project "$APG_PROJECT"` should be appended to this invocation.
#:
#: Three conditions, and the third is the one that carries ADR 0002: the set of
#: verbs that take the flag is READ FROM THE VERB, at the moment it is run.
#:
#: **The help is captured into a variable, not piped into a matcher.** A
#: `"$script" --help | grep -q` would report grep's answer for a verb whose help
#: failed outright, and this file's whole argument is against a check that
#: passes because nothing was there to fail it.
#:
#: **The match is line-anchored AND it reads the metavariable.** A loose search
#: for the string finds `--project-a-outputs` in sixteen session gates and prose
#: mentions in a dozen more -- 48 verbs against the 17 that document the flag.
#: Line-anchoring alone still overshoots, because `--project` does not mean the
#: same thing everywhere: 13 verbs spell it `--project FILE` and take a manifest
#: path, and 4 spell it `--project KEY` and take a deployed project's key
#: (`connect`, `doctor`, `project-retire`, `upgrade`). Handing a KEY-taking verb
#: a path is not refused -- `upgrade check --project project.alpha.yaml` derives
#: `/var/lib/agentic-postgres/rendered/project.alpha.yaml/outputs.json` and
#: reports on it -- which is a wrong answer, the worst of the three outcomes
#: (D1328).
#:
#: So the rule is the verb's own word: **a verb receives the default when its
#: help documents `--project FILE`.** `APG_PROJECT` is a manifest path, the
#: readability check below is a file check, and this is what keeps those two
#: agreeing with what the verb will do with the value. It is still derived from
#: the verb and still kept nowhere.
#:
#: Both spellings count as "you already gave one". The verbs measured refuse
#: `--project=FILE` and accept `--project FILE`, so `=` is not a spelling this
#: product supports -- but recognising too little would append a SECOND
#: `--project` to an invocation that already had one, and the operator's own
#: error message is better than that (D1318).
default_project_applies() {
  local script="$1"
  shift

  [ -n "${APG_PROJECT:-}" ] || return 1

  local argument
  for argument in "$@"; do
    case "${argument}" in
      --project | --project=*) return 1 ;;
      --help | -h) return 1 ;;
    esac
  done

  local help_text
  help_text="$("${script}" --help 2>/dev/null)" || return 1
  printf '%s\n' "${help_text}" | grep -Eq '^[[:space:]]*--project[[:space:]]+FILE([[:space:]]|$)'
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

  if default_project_applies "${script}" "$@"; then
    # Refused BEFORE exec, because after it this process is gone and the verb
    # would report a missing manifest the operator never typed.
    if [ ! -r "${APG_PROJECT}" ]; then
      printf 'apg: APG_PROJECT names %s, which is not a readable file.\n' "${APG_PROJECT}" >&2
      printf 'apg: point it at a project manifest this checkout can read, or unset it.\n' >&2
      exit 2
    fi
    printf 'apg: --project %s (from APG_PROJECT)\n' "${APG_PROJECT}" >&2
    # Appended rather than prepended: a verb with subcommands reads its verb
    # word first, so `dev up` must stay `dev up`.
    exec "${script}" "$@" --project "${APG_PROJECT}"
  fi

  exec "${script}" "$@"
}

main "$@"

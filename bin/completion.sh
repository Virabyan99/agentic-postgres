#!/usr/bin/env bash
#
# Print a bash completion script for the dispatcher. Install nothing.
#
#   bin/apg.sh completion bash >> ~/.bashrc     or source it per shell
#
# **The printed script keeps no list of anything, and that is the same decision
# `bin/apg.sh` makes** (ADR 0002, ADR 0207 §2). It asks the dispatcher for the
# verbs at the moment you press TAB, and it asks the verb for its flags the same
# way. Nothing is baked in, so a verb added to `bin/` completes the moment it
# lands and a flag renamed in a usage block is renamed in the completion with
# it. The alternative -- generating a list into the script -- is a second
# authority that goes stale silently, which is the failure this repository's
# front door was built to avoid.
#
# **One value is embedded, and it is a path**: the checkout this was printed
# from. A completion function is sourced into a shell whose working directory is
# not ours, so a relative path would complete against whatever the user happened
# to `cd` into. Print it again from another checkout to point it there.
#
# What it costs, measured 2026-09-14: about 21 ms to complete a verb's flags
# (one `--help`), and about 200 ms to complete a verb name, because the
# dispatcher's `--list` forks once per script in `bin/` (D1319).
#
# **The printed script does not `set -e`.** It is sourced into an interactive
# shell, and a completion function that killed the shell on a non-zero grep
# would be a worse bug than any it could fix.
#
# Exit codes: 0 (the script, or --help), 2 (a shell this does not speak).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/apg.sh completion bash
       bin/apg.sh completion --help

Print a bash completion script for `bin/apg.sh` on standard output.
This installs nothing and writes no file; where it goes is yours to decide.

  bash      Print the script. Source it, or append it to your shell's rc file.
  --help    Show this message.

The printed script derives what it offers at completion time -- verbs from
`bin/apg.sh --list`, a verb's flags from that verb's own `--help` -- so it
carries no list that can go stale. It registers itself for `bin/apg.sh` and for
`apg`, so an alias of your own is completed too.

Only bash is supported. zsh's `bashcompinit` can usually source a script of this
shape, but that is not something this repository has measured, so it is not
something this command claims.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'completion: %s\n' "$*" >&2
  exit "$code"
}

#: The script itself. `__APG_ROOT__` is substituted after the heredoc, so the
#: text below stays a literal -- no expansion here can reach the user's shell.
print_bash_completion() {
  local template
  template="$(
    cat <<'COMPLETION'
# bash completion for the agentic-postgres dispatcher.
# Printed by `bin/apg.sh completion bash`. Derives everything at completion
# time; edit the checkout, not this text.

_apg_complete() {
  local current previous_word offered

  current="${COMP_WORDS[COMP_CWORD]}"
  COMPREPLY=()

  # The first word after the dispatcher is a verb.
  if [ "${COMP_CWORD}" -le 1 ]; then
    offered="$("__APG_ROOT__/bin/apg.sh" --list 2>/dev/null)" || return 0
    mapfile -t COMPREPLY < <(compgen -W "${offered}" -- "${current}")
    return 0
  fi

  # Anything that is not being typed as a flag is left to bash, whose default
  # is a path -- which is what a manifest argument actually wants.
  case "${current}" in
    -*) ;;
    *) return 0 ;;
  esac

  previous_word="${COMP_WORDS[1]}"
  offered="$("__APG_ROOT__/bin/apg.sh" "${previous_word}" --help 2>/dev/null |
    grep -oE -- '--[a-z][a-z-]*' | sort -u)" || return 0
  mapfile -t COMPREPLY < <(compgen -W "${offered}" -- "${current}")
  return 0
}

complete -F _apg_complete "__APG_ROOT__/bin/apg.sh"
complete -F _apg_complete bin/apg.sh
complete -F _apg_complete apg
COMPLETION
  )"
  printf '%s\n' "${template//__APG_ROOT__/${ROOT_DIR}}"
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "a shell is required: bash."
  fi

  case "$1" in
    --help | -h | help)
      usage
      exit 0
      ;;
    bash)
      print_bash_completion
      exit 0
      ;;
    *)
      usage >&2
      die 2 "unsupported shell: $1. The one this command speaks is bash."
      ;;
  esac
}

main "$@"

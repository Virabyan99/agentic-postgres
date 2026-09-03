#!/usr/bin/env bash
#
# What rotating a declared secret would do (ADR 0174).
#
# Reads the committed contract and changes nothing: no provider call, no
# credential, no file written, no service touched. It answers one question per
# secret -- if you replaced this value, what would happen -- and the useful
# answers are the two refusals.
#
# **No verb here sets a value.** That is D249's rule, which
# `rotate-signing-key.sh` already keeps: a secret is written by hand at the
# provider and picked up by the next deploy. A command that could both decide a
# rotation and perform it would be one mistake away from performing one nobody
# decided.
#
# Not root, and no TTY: it reads a committed file.
#
# Exit codes (runbook §2 convention):
#   0  the plan was produced
#   2  invalid operator input
#   3  missing local prerequisite

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/rotate-secret.sh
  bin/rotate-secret.sh --secret-name <name>
  bin/rotate-secret.sh --session <n>

  --secret-name NAME  Plan one secret. Omit for every secret this session issues.
  --session N     Plan the secrets a deploy through session N materializes.
  --help          Show this message.

Reads secrets.required.yaml and changes nothing. Two of the declared secrets
cannot be rotated by replacing them, and both look exactly like the ones that
can -- that is what this exists to say before somebody replaces one and reports
a rotation that did not happen.
USAGE
}

for argument in "$@"; do
  case "${argument}" in
    --help | -h)
      usage
      exit 0
      ;;
  esac
done

exec python3 "${ROOT_DIR}/bin/rotate-secret.py" "$@"

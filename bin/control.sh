#!/usr/bin/env bash
#
# The control plane's operator verbs (ADR 0251, D2068): what only the person who
# holds root on the host may do to the control project's registry and accounts.
#
# Three verbs. `adopt` writes one project into the registry from that project's
# DEPLOYED document; `registry` compares every registry row with every deployed
# document and says, per project, whether they agree; `totp-reset` removes one
# person's second factor. Each calls a function the control set grants to
# nobody (D2093), as the cluster's superuser, through the control project's
# database container.
#
# The control project is FOUND, never named: the one deployed document under
# /etc/agentic-postgres/projects/ that records the control facility enabled.
# `--confirm` must be that project's key, exactly.
#
# Root, because the deployed documents are root-owned and the registry is
# written through the database container as its superuser.
#
# Exit codes (runbook section 2 convention):
#   0  adopted, reset, or every project agrees
#   2  invalid operator input (a malformed key or organisation, a wrong --confirm)
#   3  missing local prerequisite, not root, no deployed document for the key,
#      or no deployed project enables the control facility
#   5  the database refused the call, two deployed projects enable the facility,
#      or the registry and a deployed document disagree
#   6  something could not be read -- reported, never read as agreement

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/control.sh adopt --project KEY --organization ORG_ID --confirm CONTROL_KEY
  sudo bin/control.sh registry [--json]
  sudo bin/control.sh totp-reset --username NAME --confirm CONTROL_KEY

  adopt       Write project KEY into the control project's registry, under the
              organisation ORG_ID (a uuid the management API printed when the
              organisation was created). slug, environment, domain,
              template_version and source_commit are read from KEY's deployed
              document, never typed. Adopting a key again refreshes its row.
  registry    One line per project: "agrees", "differs: <field>[, <field>]",
              "not in the registry", "no deployed document", or "could not
              determine: <reason>". --json prints the same as a document.
              Exit 0 when all agree, 5 on a difference, 6 when anything could
              not be determined.
  totp-reset  Remove one person's second factor, so they can enrol again at
              their next login. Prints whether a factor was removed.

CONTROL_KEY is the key of the one deployed project whose document records the
control facility enabled (control-prod); --confirm must equal it exactly. The
documents are read from /etc/agentic-postgres/projects/KEY/outputs.json, and
the control project's database container and database come from its document.
A registry row is removed only by a root psql DELETE.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'control: %s\n' "$*" >&2
  exit "$code"
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3)."
  fi
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "a verb is required: adopt, registry or totp-reset."
  fi
  # --help anywhere is a read: no root, no docker, no document.
  local argument
  for argument in "$@"; do
    case "${argument}" in
      --help | -h)
        usage
        return 0
        ;;
    esac
  done
  case "$1" in
    adopt | registry | totp-reset) ;;
    *) die 2 "unknown verb: $1. One of: adopt registry totp-reset" ;;
  esac
  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."
  exec "$(python_bin)" "${ROOT_DIR}/bin/control.py" "$@"
}

main "$@"

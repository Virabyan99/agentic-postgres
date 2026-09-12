#!/usr/bin/env bash
#
# A local web UI for one deployment, bound to loopback, holding nothing but the
# human's own short-lived token (ADR 0205). Reached as `apg studio`.
#
# Studio is a CLIENT of the surfaces a deployment already publishes. It logs in
# through `POST /auth/login` as the person running it, keeps the token in this
# process's memory, and makes every upstream request itself from an enumerated
# table. **The browser never holds the token**: it holds a launch cookie, and a
# request without it -- or with a foreign `Host`, a foreign `Origin`, or no
# `X-Apg-Studio` header -- is refused before anything else happens.
#
# **There is no SQL box and there is no bind flag.** The query builder sends a
# relation, columns, operators and values as structure, and this process turns
# them into one PostgREST `GET` over the reviewed surface as the human's own
# token -- so PostgreSQL's row policies decide what comes back, exactly as they
# do for any other caller. `127.0.0.1` is a constant in the source; binding
# anywhere else would need TLS a workstation process cannot get from the edge,
# and a switch that turned the decision off would be the decision.
#
# At launch Studio fetches the served REST document AS THE HUMAN and answers one
# of four ways, the same four a generated client's `init()` answers:
#
#   ok               the deployment serves the surface this checkout describes
#   stale_contract   it serves a different one; both digests are printed, and
#                    the schema and query views are refused until you
#                    regenerate. The audit, agent and session views stay --
#                    they are release operations, not project ones.
#   unreachable      the REST route did not answer
#   unreadable       it answered with something this cannot read -- including a
#                    document published at a host the deployed document does
#                    not name, which is refused rather than accepted
#
# The password comes from a prompt or from a `0600` file. There is no
# `--password` flag and no environment variable is read for one: a value in an
# argument is in `ps` and in a shell history.
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input, including a password file others can read
#   3  a missing local prerequisite
#   4  the project has not been rendered, naming the command that renders it
#   5  the deployed document publishes no usable route, or an http route to a
#      host that is not loopback
#   6  the deployment refused this credential
#   9  the deployment could not be reached

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/studio.sh --project FILE --outputs FILE [--username NAME]
                     [--password-file FILE] [--capabilities FILE]

  --project FILE       The project manifest. Its derived key names the project,
                       and its contracts are what the schema and query views
                       show.
  --outputs FILE       The DEPLOYED document for that project: the address book
                       and nothing else (ADR 0158). A route that is not `ready`
                       is exit 5, and so is an `http` route to anything but
                       127.0.0.1 or localhost.
  --username NAME      The human logging in. Prompted when absent and there is
                       a TTY; required when there is not.
  --password-file FILE A regular file at mode 0600 or stricter holding the
                       password. Absent means a prompt. A password is never
                       taken as a command-line argument and no environment
                       variable is read for one: a value in an argument is in
                       ps and in your shell history.
  --capabilities FILE  Used to compile the project's lock, and to spell out the
                       render command when a project has not been rendered.
                       Default capabilities.example.yaml.
  --help               Show this message.

Studio prints one URL carrying a per-launch key. Open it once: it sets an
HttpOnly, SameSite=Strict cookie and redirects. Stop Studio with Ctrl-C, and it
ends the login session it began -- or says that it could not tell which session
was its own and ended none.

The four surface answers are ok, stale_contract, unreachable and unreadable.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'studio: %s\n' "$*" >&2
  exit "${code}"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible to a privileged call (D80). One rule for
# every command here, not a per-command judgement.
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

main() {
  local -a arguments=()
  # **Every path is collected and checked after the parse, never during it.**
  # Checked inline, `--project missing.yaml --nope` reports the missing file and
  # never reaches the unknown flag -- which sends an operator looking for a path
  # when what is wrong is a word they typed. Shape errors first, then the
  # filesystem. (`--password-file`'s MODE is the Python's to check, where the
  # message can say what the mode is.)
  local -a paths=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      --project|--outputs|--capabilities|--password-file)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        paths+=("$1" "$2")
        arguments+=("$1" "$2")
        shift 2
        ;;
      --username)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        arguments+=("$1" "$2")
        shift 2
        ;;
      --password)
        die 2 "there is no --password flag: a password in an argument is in ps and in your
shell history. Use --password-file with a 0600 file, or let Studio prompt."
        ;;
      -*)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
      *)
        usage >&2
        die 2 "studio takes no positional arguments, and got '$1'."
        ;;
    esac
  done

  local index=0
  while [ "${index}" -lt "${#paths[@]}" ]; do
    [ -f "${paths[$((index + 1))]}" ] \
      || die 2 "${paths[${index}]}: file not found: ${paths[$((index + 1))]}"
    index=$((index + 2))
  done

  exec "$(python_bin)" "${ROOT_DIR}/bin/studio.py" "${arguments[@]+"${arguments[@]}"}"
}

main "$@"

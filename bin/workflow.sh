#!/usr/bin/env bash
#
# A project's workflows: scaffold one, compile them against the project's lock,
# and start, read or stop a run (ADR 0228, ADR 0229).
#
#   init      Print a definition skeleton to standard output, derived from the
#             project's own lock -- so the scaffold cannot name a capability
#             the compiler would refuse. Writes no file: redirect it yourself,
#             as yourself, and READ it before it is reviewed.
#   validate  Compile every definition under projects/<slug>/workflows/ (or one
#             named file) against that project's lock, and refuse naming the
#             first step that cannot be compiled. No host, no root, no render.
#   run       Start a run of an installed definition, as the agent whose token
#             is in APG_AGENT_TOKEN. Prints the run id.
#   dry-run   `run` with dry_run set: every write step is performed and rolled
#             back by the plane (ADR 0182), and every read runs unchanged.
#   status    Read one run: its status, its steps and their outcomes.
#   cancel    Ask for a run to stop. A step already in flight upstream cannot
#             be recalled, so what this records is an intent the next claim
#             honours.
#
# `init` and `validate` read a project MANIFEST and reach nothing. The other
# four call the deployment named by a rendered outputs document and carry a
# token from the environment, the way `bin/api.sh` does -- this command holds
# no token, no SQL and no route the auth service does not publish.
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input
#   3  a missing local prerequisite, or a verb this checkout does not serve yet
#   5  a definition that does not compile, or a run the service refused

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/workflow.sh init --project FILE [--name NAME]
       bin/workflow.sh validate --project FILE [--file PATH] [--capabilities FILE]
       bin/workflow.sh run NAME --project-outputs FILE [--input JSON] [--definition-version N]
       bin/workflow.sh dry-run NAME --project-outputs FILE [--input JSON]
       bin/workflow.sh status RUN_ID --project-outputs FILE
       bin/workflow.sh cancel RUN_ID --project-outputs FILE

  init               Print a workflow definition skeleton derived from the
                     project's lock: two steps, the first read capability it
                     serves and the first write that does not require
                     approval. Writes no file.
  validate           Compile the project's definitions against its lock and
                     say so, or exit 5 naming the file, the step and why.
  run NAME           Start a run of the installed definition NAME.
  dry-run NAME       The same, with dry_run set on every write.
  status RUN_ID      Read one run and its steps.
  cancel RUN_ID      Request that a run stop at its next step boundary.
  --project FILE     The project manifest. Its lock is what a definition is
                     compiled against, and its migrations.set names the
                     directory the definitions are read from.
  --file PATH        Validate one definition file instead of the directory.
  --capabilities FILE  The release capability manifest the project's lock is
                     joined with. Default capabilities.example.yaml.
  --project-outputs FILE  The rendered outputs document of the deployment to
                     call. The app route is read from it; nothing is derived.
  --input JSON       The run's input document, as JSON. Default {}.
  --definition-version N  Which version of the definition to run. Default 1.
  --help             Show this message. Each verb takes it too.

A definition is a project artefact: reviewed in the checkout, installed by the
deploy at step 6d, and immutable per (name, version). Fix one forward by
publishing a new version, never by editing an installed one.

The token comes from APG_AGENT_TOKEN and is never an argument: a value in an
argument vector is a value `ps` can read.
USAGE
}

verb_usage() {
  case "$1" in
    init)
      cat <<'USAGE'
Usage: bin/workflow.sh init --project FILE [--name NAME]

Print one workflow definition skeleton to standard output, derived from the
project's own compiled lock. The skeleton names two capabilities the lock
really serves -- the first read, and the first write that does not require
approval -- so a definition written from it compiles before it is edited.

  --project FILE   The project manifest whose lock the skeleton is derived
                   from. Required.
  --name NAME      The definition's name. Default `example-workflow`. Must
                   match ^[a-z][a-z0-9-]{0,62}$, which is the name column's
                   own constraint.
  --capabilities FILE  The release capability manifest to join with. Default
                   capabilities.example.yaml.

Writes no file. Redirect it into projects/<slug>/workflows/<name>.yaml, read
it, then `bin/workflow.sh validate --project FILE`.
USAGE
      ;;
    validate)
      cat <<'USAGE'
Usage: bin/workflow.sh validate --project FILE [--file PATH] [--capabilities FILE]

Compile every definition under the project's workflows/ directory against the
lock that project compiles, and exit 5 on the first one that cannot be
compiled, naming the file, the step and the reason.

  --project FILE   The project manifest. Required.
  --file PATH      Compile one file instead of the whole directory. The file
                   need not live under the project, which is how a definition
                   is checked before it is moved into place.
  --capabilities FILE  The release capability manifest to join with. Default
                   capabilities.example.yaml.

Needs no host, no root and no render: the lock is computed from the approved
contract and the project's own, and is discarded. A project that declares no
workflows/ directory is reported as declaring none, not as having zero.
USAGE
      ;;
    run | dry-run)
      cat <<'USAGE'
Usage: bin/workflow.sh run NAME --project-outputs FILE [--input JSON]
       bin/workflow.sh dry-run NAME --project-outputs FILE [--input JSON]

Start a run of an installed definition and print its run id. `dry-run` is the
same request with dry_run set: the plane performs every write and rolls it
back (ADR 0182), and every read runs unchanged.

  NAME             The installed definition's name.
  --project-outputs FILE  The rendered outputs document of the deployment to
                   call. The app route is read from it.
  --input JSON     The run's input document. Default {}.
  --definition-version N  Default 1.

The run is started AS THE AGENT whose token is in APG_AGENT_TOKEN, and the
agent's stored scopes are what authorise it -- not the token's. An agent
narrowed since its token was minted is refused.
USAGE
      ;;
    status)
      cat <<'USAGE'
Usage: bin/workflow.sh status RUN_ID --project-outputs FILE

Read one run: its status, the definition and version it is a run of, each
step's position, name, status, attempt and outcome, and the reason a stopped
run stopped.

  RUN_ID           The run id `run` printed.
  --project-outputs FILE  The rendered outputs document of the deployment.

A run belongs to the agent that started it, and a token for another agent
reads nothing here.
USAGE
      ;;
    cancel)
      cat <<'USAGE'
Usage: bin/workflow.sh cancel RUN_ID --project-outputs FILE

Request that a run stop. A step already in flight upstream cannot be recalled,
so what this records is an intent the NEXT claim honours -- the run's status
does not become `cancelled` until the worker reaches a step boundary.

  RUN_ID           The run id to stop.
  --project-outputs FILE  The rendered outputs document of the deployment.

Cancelling a run that has already finished is reported as such rather than
treated as an error.
USAGE
      ;;
    *)
      usage
      ;;
  esac
}

die() {
  local code="$1"
  shift
  printf 'workflow: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible to a privileged call (D80). This command
# never runs under sudo and resolves the interpreter the same way anyway: one
# rule, not a per-command judgement.
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
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "a verb is required: init, validate, run, dry-run, status or cancel."
  fi

  local command=""
  local subject=""
  local -a arguments=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help | -h)
        # **Before the verb is dispatched, not after** (D1395, D1402, D1405).
        # A verb's help is a READ: it takes no project, no token and no host,
        # and it is answered here so that no parser downstream can refuse it
        # for a missing required argument.
        if [ -n "${command}" ]; then
          verb_usage "${command}"
        else
          usage
        fi
        exit 0
        ;;
      init | validate | run | dry-run | status | cancel)
        [ -z "${command}" ] || die 2 "only one verb at a time."
        command="$1"
        shift
        ;;
      --project | --capabilities | --file | --project-outputs)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        [ -f "$2" ] || die 2 "$1 names no file: $2"
        arguments+=("$1" "$2")
        shift 2
        ;;
      --name | --input | --definition-version)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        arguments+=("$1" "$2")
        shift 2
        ;;
      -*)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
      *)
        # The one positional: a definition NAME for run and dry-run, a RUN_ID
        # for status and cancel. Taken wherever it was typed, and never joined
        # to a path.
        [ -z "${subject}" ] || die 2 "only one name or run id at a time."
        subject="$1"
        shift
        ;;
    esac
  done

  [ -n "${command}" ] || die 2 "a verb is required: init, validate, run, dry-run, status or cancel."

  if [ -n "${subject}" ]; then
    arguments+=("--subject" "${subject}")
  fi

  exec "$(python_bin)" "${ROOT_DIR}/bin/workflow.py" "${command}" "${arguments[@]+"${arguments[@]}"}"
}

main "$@"

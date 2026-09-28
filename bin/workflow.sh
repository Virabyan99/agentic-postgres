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
#   approvals List the approvals waiting for a human (Session 33, ADR 0230).
#   approve   Approve one parked step of a run; --confirm must repeat the run.
#   reject    Reject one parked step: a rejection is a cancel, and the steps
#             that succeeded are compensated.
#   inspect   Print one run's provenance whole (ADR 0234).
#
# `init` and `validate` read a project MANIFEST and reach nothing. The other
# eight call the deployment named by a rendered outputs document and carry a
# token from the environment, the way `bin/api.sh` does -- this command holds
# no token, no SQL and no route the auth service does not publish. `run`,
# `dry-run`, `status` and `cancel` take an AGENT's token (APG_AGENT_TOKEN);
# `approvals`, `approve`, `reject` and `inspect` take a HUMAN's (APG_API_TOKEN,
# `bin/api.sh`'s variable), because an agent may not decide its own approval.
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input, including a --confirm that does not repeat --run
#   3  a missing local prerequisite, or an auth service that cannot be reached
#   5  a definition that does not compile, or a request the service refused

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/workflow.sh init --project FILE [--name NAME]
       bin/workflow.sh validate --project FILE [--file PATH] [--capabilities FILE]
       bin/workflow.sh run --definition NAME@VERSION --project-outputs FILE [--input JSON]
       bin/workflow.sh dry-run --definition NAME@VERSION --project-outputs FILE [--input JSON]
       bin/workflow.sh status --run RUN_ID --project-outputs FILE
       bin/workflow.sh cancel --run RUN_ID --project-outputs FILE
       bin/workflow.sh approvals --project-outputs FILE [--limit N]
       bin/workflow.sh approve --run RUN_ID --step NAME --confirm RUN_ID --project-outputs FILE
       bin/workflow.sh reject --run RUN_ID --step NAME --confirm RUN_ID --project-outputs FILE
       bin/workflow.sh inspect --run RUN_ID --project-outputs FILE

  init               Print a workflow definition skeleton derived from the
                     project's lock: two steps, the first read capability it
                     serves and the first write that does not require
                     approval. Writes no file.
  validate           Compile the project's definitions against its lock and
                     say so, or exit 5 naming the file, the step and why.
  run                Start a run of an installed definition.
  dry-run            The same, with dry_run set on every write.
  status             Read one run and its steps.
  cancel             Request that a run stop at its next step boundary.
  approvals          List what waits for a human's decision, oldest first.
  approve            Approve one parked step. Final.
  reject             Reject one parked step: the run is cancelled and its
                     succeeded steps are compensated. Final.
  inspect            Print one run's provenance: every attempt joined to its
                     audit rows, every approval and who decided it.
  --project FILE     The project manifest. Its lock is what a definition is
                     compiled against, and its migrations.set names the
                     directory the definitions are read from.
  --file PATH        Validate one definition file instead of the directory.
  --capabilities FILE  The release capability manifest the project's lock is
                     joined with. Default capabilities.example.yaml.
  --project-outputs FILE  The rendered outputs document of the deployment to
                     call. The app route is read from it; nothing is derived.
  --definition NAME@VERSION  Which installed definition to run. One string
                     rather than two flags: a definition is identified by the
                     pair, and a caller that could give one without the other
                     could ask for "the latest", which no table here has.
  --run RUN_ID       The run to read, cancel, decide or inspect.
  --input JSON       The run's input document, as JSON. Default {}.
  --step NAME        The parked step a decision is for.
  --confirm RUN_ID   The run id again. A decision is final, so approve and
                     reject refuse (exit 2) unless it repeats --run.
  --limit N          How many approvals to list, 1-100. Default 50.
  --help             Show this message. Each verb takes it too.

A definition is a project artefact: reviewed in the checkout, installed by the
deploy at step 6d, and immutable per (name, version). Fix one forward by
publishing a new version, never by editing an installed one.

The token comes from APG_AGENT_TOKEN and is never an argument: a value in an
argument vector is a value `ps` can read. A run is started AS THE AGENT that
token was minted for, and the AGENT'S STORED scopes are what authorise it --
not the token's -- so an agent narrowed since is refused.

approvals, approve, reject and inspect take a HUMAN administrator's access
token from APG_API_TOKEN instead: an agent token is refused by those routes,
so the agent whose run waits cannot decide it. Deciding needs
admin_workflows:approve and inspecting needs admin_audit:read, and the run's
owner may not decide their own agent's run.
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
Usage: bin/workflow.sh run --definition NAME@VERSION --project-outputs FILE [--input JSON]
       bin/workflow.sh dry-run --definition NAME@VERSION --project-outputs FILE [--input JSON]

Start a run of an installed definition and print its run id. `dry-run` is the
same request with dry_run set -- one route, not a second address: the plane
performs every write and rolls it back (ADR 0182), and every read runs
unchanged.

  --definition NAME@VERSION  The installed definition, by name and version.
  --project-outputs FILE  The outputs document of the deployment to call. The
                   app route is READ from it, never rebuilt.
  --input JSON     The run's input document, a JSON object. Every key is a name
                   the definition's own {{input.<key>}} references can read.
                   Default {}.

The run is started AS THE AGENT whose token is in APG_AGENT_TOKEN, and the
agent's stored scopes are what authorise it -- not the token's. An agent
narrowed since its token was minted is refused.
USAGE
      ;;
    status)
      cat <<'USAGE'
Usage: bin/workflow.sh status --run RUN_ID --project-outputs FILE

Read one run: its status, the definition and version it is a run of, the lock
digest validate compiled against, and each step's position, name, status,
attempt, outcome and request id -- which is what correlates a step to the
plane's own audit row.

  --run RUN_ID     The run id `run` printed.
  --project-outputs FILE  The outputs document of the deployment.

A run belongs to the agent that started it, and a token for another agent
reads nothing here.
USAGE
      ;;
    cancel)
      cat <<'USAGE'
Usage: bin/workflow.sh cancel --run RUN_ID --project-outputs FILE

Request that a run stop. A step already in flight upstream cannot be recalled,
so what this records is an intent the NEXT claim honours -- the run's status
does not become `cancelled` until the worker reaches a step boundary.

  --run RUN_ID     The run id to stop.
  --project-outputs FILE  The outputs document of the deployment.

Cancelling a run that has already finished is reported as such rather than
treated as an error.
USAGE
      ;;
    approvals)
      cat <<'USAGE'
Usage: bin/workflow.sh approvals --project-outputs FILE [--limit N]

List the approvals waiting for a human, oldest first: the run, the definition
and its version, the step, the capability and tool, the agent and its owner,
and when the approval was requested and expires. Never an argument value or
the run's input -- what the step does is in the reviewed definition.

  --project-outputs FILE  The outputs document of the deployment.
  --limit N        1-100. Default 50.

Takes a human administrator's token from APG_API_TOKEN holding
admin_workflows:approve.
USAGE
      ;;
    approve | reject)
      cat <<'USAGE'
Usage: bin/workflow.sh approve --run RUN_ID --step NAME --confirm RUN_ID --project-outputs FILE
       bin/workflow.sh reject --run RUN_ID --step NAME --confirm RUN_ID --project-outputs FILE

Decide one parked step. A decision is FINAL, so --confirm must repeat --run
or nothing is sent (exit 2). Approving makes the step claimable at once and
the plane serves that one write; rejecting cancels the run, and the steps that
succeeded and declare a compensation are undone in reverse.

  --run RUN_ID     The run.
  --step NAME      The parked step the approval is for.
  --confirm RUN_ID The run id again.
  --project-outputs FILE  The outputs document of the deployment.

Takes a human administrator's token from APG_API_TOKEN holding
admin_workflows:approve. The run's owner is refused (approver_is_owner); a
decided approval is approval_already_decided; one past its window is
approval_expired.
USAGE
      ;;
    inspect)
      cat <<'USAGE'
Usage: bin/workflow.sh inspect --run RUN_ID --project-outputs FILE

Print one run's provenance whole: the run, every step with every attempt
joined to its audit rows by request id, and every approval with the human who
decided it. Any agent's run, a revoked agent's stopped run included. The run's
input is reported by its keys only.

  --run RUN_ID     The run.
  --project-outputs FILE  The outputs document of the deployment.

Takes a human administrator's token from APG_API_TOKEN holding
admin_audit:read.
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
    die 2 "a verb is required: init, validate, run, dry-run, status, cancel, approvals, approve, reject or inspect."
  fi

  local command=""
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
      init | validate | run | dry-run | status | cancel | approvals | approve | reject | inspect)
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
      --name | --input | --definition | --run | --step | --confirm | --limit)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        arguments+=("$1" "$2")
        shift 2
        ;;
      -*)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
      *)
        # **No positional argument at all.** Every value this command takes is
        # behind a named flag, so a definition reference and a run id can never
        # be swapped by position -- and a mistyped verb is an unknown argument
        # rather than a run id nobody meant.
        usage >&2
        die 2 "unexpected argument: $1"
        ;;
    esac
  done

  [ -n "${command}" ] || die 2 "a verb is required: init, validate, run, dry-run, status, cancel, approvals, approve, reject or inspect."

  exec "$(python_bin)" "${ROOT_DIR}/bin/workflow.py" "${command}" "${arguments[@]+"${arguments[@]}"}"
}

main "$@"

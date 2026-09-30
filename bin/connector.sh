#!/usr/bin/env bash
#
# A project's connectors: scaffold one, compile them against the project's lock
# and definitions, read and change a deployment's, and hand a sender its key
# (ADR 0236, ADR 0237).
#
#   init      Print a connector skeleton to standard output, derived from the
#             project's own definitions -- so it compiles as it stands. Writes
#             no file: redirect it yourself, and READ it before it is reviewed.
#   validate  Compile every connector under projects/<slug>/connectors/ (or one
#             named file) against that project's lock and definitions, and
#             refuse naming the first member that cannot be compiled. No host,
#             no root, no render.
#   status    Print every connector of a deployment whole: its binding, its
#             counts, its last error token and its dead letters. Never an
#             endpoint, a payload or a key.
#   enable    Enable one connector; an inbound or scheduled one binds the agent
#             it will act as. --confirm must repeat --name.
#   disable   Disable one connector: unbind it, stop its schedule, hold its
#             pending deliveries. --confirm must repeat --name.
#   key       ROOT. Derive one connector's key from the project's active secret
#             generation into a NEW file, mode 0600. Never printed.
#
# `status`, `enable` and `disable` call the deployment named by a rendered
# outputs document with a HUMAN administrator's token from APG_API_TOKEN, the
# way `bin/api.sh` does -- this command holds no token, no SQL and no route the
# auth service does not publish.
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input, including a --confirm that does not repeat
#      --name and a key --output that already exists
#   3  a missing local prerequisite, or an auth service that cannot be reached
#   4  key: not root, or no active secret generation or master to read
#   5  a connector that does not compile, a request the service refused, or a
#      key for a project or connector that has none

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/connector.sh init --kind outbound|inbound|scheduled --project FILE [--name NAME]
       bin/connector.sh validate --project FILE [--file PATH] [--capabilities FILE]
       bin/connector.sh status --project-outputs FILE [--dead-limit N]
       bin/connector.sh enable --name NAME --confirm NAME [--agent AGENT_ID] --project-outputs FILE
       bin/connector.sh disable --name NAME --confirm NAME --project-outputs FILE
       sudo bin/connector.sh key --project FILE --name NAME --output FILE

  init               Print a connector skeleton of one kind, derived from the
                     project's own definitions. Writes no file.
  validate           Compile the project's connectors against its lock and
                     definitions and say so, or exit 5 naming the file and
                     the member.
  status             Print every connector of the deployment, whole.
  enable             Enable one connector, binding the agent it acts as.
  disable            Disable one connector.
  key                Write one connector's derived key to a new 0600 file.
  --project FILE     The project manifest. Its migrations.set names the
                     directory the connectors and definitions are read from.
  --kind KIND        init: outbound, inbound or scheduled.
  --file PATH        Validate one connector file instead of the directory.
  --capabilities FILE  The release capability manifest the project's lock is
                     joined with. Default capabilities.example.yaml.
  --project-outputs FILE  The rendered outputs document of the deployment to
                     call. The app route is read from it; nothing is derived.
  --name NAME        The connector.
  --confirm NAME     The connector's name again. enable and disable refuse
                     (exit 2) unless it repeats --name.
  --agent AGENT_ID   enable: the agent an inbound or scheduled connector acts
                     as. Its stored scopes must EQUAL the definition's. Omit it
                     for an outbound connector, which acts as nobody.
  --dead-limit N     status: dead letters per connector, 1-20. Default 20.
  --output FILE      key: a path that does not exist yet.
  --help             Show this message. Each verb takes it too.

A connector is a project artefact: reviewed in the checkout, installed
DISABLED by the deploy at step 6e, and immutable per (name, version). Its
endpoint is the deployment's, in the project manifest -- never in the file.

status, enable and disable take a HUMAN administrator's access token from
APG_API_TOKEN, never as an argument. status needs admin_connectors:read;
enable and disable need admin_connectors:write. No administrator holds either
until an operator grants it.

key runs as root and writes the key to a file, never to standard output: a
sender outside the deployment must hold it, and a terminal's transcript is
where a printed secret ends up. Every connector's key changes at once when
APG_CONNECTOR_SIGNING_KEY is replaced and the project redeployed.
USAGE
}

verb_usage() {
  case "$1" in
    init)
      cat <<'USAGE'
Usage: bin/connector.sh init --kind outbound|inbound|scheduled --project FILE [--name NAME]

Print one connector skeleton to standard output. An inbound one names the
first definition of the project's set that reads an input and declares
exactly the members it reads; a scheduled one names the first definition and
gives exactly the keys it reads; an outbound one names a placeholder event.
Each compiles as printed, and each TODO is a decision a scaffold cannot make.

  --kind KIND      outbound, inbound or scheduled. Required.
  --project FILE   The project manifest. Required.
  --name NAME      The connector's name. Default example-<kind>. Must match
                   ^[a-z][a-z0-9-]{0,62}$, the name column's own constraint.
  --capabilities FILE  The release capability manifest to join with.

Writes no file. Redirect it into projects/<slug>/connectors/<name>.yaml, read
it, then `bin/connector.sh validate --project FILE`.
USAGE
      ;;
    validate)
      cat <<'USAGE'
Usage: bin/connector.sh validate --project FILE [--file PATH] [--capabilities FILE]

Compile every connector under the project's connectors/ directory against the
lock the project compiles and the definitions its set installs, and exit 5 on
the first one that cannot be compiled, naming the file and the member.

  --project FILE   The project manifest. Required.
  --file PATH      Compile one file instead of the whole directory.
  --capabilities FILE  The release capability manifest to join with.

Needs no host, no root and no render. A project that declares no connectors/
directory is reported as declaring none, not as having zero.
USAGE
      ;;
    status)
      cat <<'USAGE'
Usage: bin/connector.sh status --project-outputs FILE [--dead-limit N]

Print every connector of the deployment whole: its kind and version, whether
it is enabled and by whom, the bound agent and the binding as it stands now,
whether an endpoint is declared, its pending, delivered and dead counts, the
oldest pending delivery's age, its last error token, its receipts and up to N
dead letters. Never an endpoint, a payload or a key.

  --project-outputs FILE  The outputs document of the deployment.
  --dead-limit N   1-20. Default 20.

Takes a human administrator's token from APG_API_TOKEN holding
admin_connectors:read.
USAGE
      ;;
    enable)
      cat <<'USAGE'
Usage: bin/connector.sh enable --name NAME --confirm NAME [--agent AGENT_ID] --project-outputs FILE

Enable one connector. An inbound or scheduled one starts runs AS the agent
named by --agent, which must be active, bound to no other connector, and hold
EXACTLY its definition's scopes. An outbound one acts as nobody: name no
agent, and it needs an endpoint in the project manifest.

  --name NAME      The connector.
  --confirm NAME   The name again, or nothing is sent (exit 2).
  --agent AGENT_ID The agent, for an inbound or scheduled connector.
  --project-outputs FILE  The outputs document of the deployment.

Takes a human administrator's token from APG_API_TOKEN holding
admin_connectors:write. A refusal names its reason: agent_not_active,
agent_already_bound, agent_scopes_differ, no_endpoint or agent_not_needed.
USAGE
      ;;
    disable)
      cat <<'USAGE'
Usage: bin/connector.sh disable --name NAME --confirm NAME --project-outputs FILE

Disable one connector: its agent is unbound, its schedule cleared, and its
pending deliveries held rather than sent until it is enabled again.

  --name NAME      The connector.
  --confirm NAME   The name again, or nothing is sent (exit 2).
  --project-outputs FILE  The outputs document of the deployment.

Takes a human administrator's token from APG_API_TOKEN holding
admin_connectors:write.
USAGE
      ;;
    key)
      cat <<'USAGE'
Usage: sudo bin/connector.sh key --project FILE --name NAME --output FILE

Derive one connector's key from the master in the project's ACTIVE secret
generation -- the one the running auth container mounts -- and write it to a
NEW file, mode 0600. The key is printed nowhere. Hand the file to the sender
out of band; a sender signs with it (inbound) or verifies with it (outbound).

  --project FILE   The project manifest. The project must enable the
                   connectors facility and its set must declare NAME.
  --name NAME      The connector.
  --output FILE    A path that does not exist yet. An existing one is refused
                   and never replaced.

Runs as root: the generation is root's. The path read is derived from
active-secret-generation.json and the secret contract, never typed.
Replacing APG_CONNECTOR_SIGNING_KEY and redeploying changes EVERY connector's
key of the project at once.
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
  printf 'connector: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible to a privileged call (D80). `key` runs
# under sudo, so the interpreter is resolved from the checkout first.
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
    die 2 "a verb is required: init, validate, status, enable, disable or key."
  fi

  local command=""
  local -a arguments=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help | -h)
        # Before the verb is dispatched (D1395, D1402, D1405): a verb's help is
        # a READ and takes no project, no token, no host and no root.
        if [ -n "${command}" ]; then
          verb_usage "${command}"
        else
          usage
        fi
        exit 0
        ;;
      init | validate | status | enable | disable | key)
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
      --kind | --name | --confirm | --agent | --dead-limit | --output)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        arguments+=("$1" "$2")
        shift 2
        ;;
      -*)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
      *)
        # No positional argument at all: a name and a confirmation can never
        # be swapped by position.
        usage >&2
        die 2 "unexpected argument: $1"
        ;;
    esac
  done

  [ -n "${command}" ] || die 2 "a verb is required: init, validate, status, enable, disable or key."

  exec "$(python_bin)" "${ROOT_DIR}/bin/connector.py" "${command}" "${arguments[@]+"${arguments[@]}"}"
}

main "$@"

#!/usr/bin/env bash
#
# Generate a typed client for one project, from the contracts it was reviewed
# against (ADR 0204). Reached as `apg generate`.
#
# The client is a claim about a surface. It embeds the digests of the four
# artefacts it was generated from, and at `init()` it fetches the served REST
# document AS THE CALLER, normalizes it the way this project's capture does, and
# refuses every later call unless the fingerprint matches. It reads no deployed
# document: one is `0600 root` on a host, a client holds none, and a client that
# learned the live hash from a file rather than from the service would be
# trusting the same artefact that can be ahead of the deployment (ADR 0158,
# D1153).
#
# **Generation is not hooked to a migration**, and that is measured rather than
# chosen (D1208): a client is generated from the SNAPSHOT, and a project's
# snapshot is captured only after a deploy, so a migration alone moves nothing
# this command reads. The step that changes its input is the capture --
# `bin/api-contract.sh --update` -- and that command prints this one as the next
# step.
#
# Exit codes (runbook §2 convention):
#   0  success, or --check found no drift
#   2  invalid operator input
#   3  a missing local prerequisite
#   4  the project has not been rendered, naming the command that renders it
#   5  a contract that could not produce a client, or --check found drift

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

die() {
  local code="$1"
  shift
  printf 'generate: %s\n' "$*" >&2
  exit "${code}"
}

usage() {
  cat <<'USAGE'
Usage: bin/generate.sh --project FILE [--capabilities FILE] [--out DIR] [--check]

  --project FILE       The project manifest. Its derived key names the rendered
                       document this command requires, and its migration set (if
                       it declares one) decides which surface and snapshot the
                       client is generated from.
  --capabilities FILE  The release capability manifest, joined with the
                       project's to compile the lock. Default
                       capabilities.example.yaml.
  --out DIR            Where to write. Default projects/<slug>/clients/typescript
                       for a project that declares a migration set, and
                       clients/typescript under the checkout root for one that
                       does not. Must be inside this checkout.
  --check              Compare what this contract generates against what is on
                       disk. Writes nothing. Exit 5 names the first file that
                       differs, or is missing.
  --help               Show this message.

What it writes: contract.ts (the four digests, and the only file that carries
one), canonical.ts, types.ts, client.ts, agent.ts, package.json, tsconfig.json,
README.md and generated.json (the IR, which --check and the next generation's
version derivation both read).

The package has no runtime dependency and holds no credential: nothing that
identifies a caller or a deployment is written into a generated file, and the
emitter refuses its own output if one appears.

Call init() before anything else. It has four answers, and the difference
between them is the point: ok, stale_contract (naming both digests), unreachable
(the service did not answer, so nothing is known about its surface) and
unparsable. An unreachable service is never reported as a stale contract.
USAGE
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "--project is required."
  fi

  local project=""
  local capabilities=""
  local out=""
  local -a arguments=()

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help | -h)
        usage
        exit 0
        ;;
      --project)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        [ -z "${project}" ] || die 2 "--project was given twice."
        [ -f "$2" ] || die 2 "project manifest not found: $2"
        project="$2"
        shift 2
        ;;
      --capabilities)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        [ -z "${capabilities}" ] || die 2 "--capabilities was given twice."
        [ -f "$2" ] || die 2 "capability manifest not found: $2"
        capabilities="$2"
        shift 2
        ;;
      --out)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        # Refused HERE, because a second --out is the shape where one value is
        # silently discarded and the developer reads the wrong directory's diff.
        [ -z "${out}" ] || die 2 "--out was given twice."
        out="$2"
        shift 2
        ;;
      --check)
        arguments+=("--check")
        shift
        ;;
      -*)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
      *)
        usage >&2
        die 2 "this command takes no positional argument, and got '$1'."
        ;;
    esac
  done

  [ -n "${project}" ] || die 2 "--project is required."

  arguments+=("--project" "${project}")
  [ -n "${capabilities}" ] && arguments+=("--capabilities" "${capabilities}")
  [ -n "${out}" ] && arguments+=("--out" "${out}")

  exec "$(python_bin)" "${ROOT_DIR}/bin/generate.py" "${arguments[@]}"
}

# One rule for resolving the interpreter, the same one `bin/dev.sh` uses, rather
# than a per-command judgement.
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

main "$@"

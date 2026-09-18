# shellcheck shell=bash
#
# The D972 refusal, as a function (ADR 0218).
#
# NOT A COMMAND. This file is sourced, never executed: it has no shebang, mode
# 644, and lives under `bin/lib/` so that `test_cli_contract`'s non-recursive
# `iterdir` over `bin/` does not see it as a command and
# `test_shell_script_preamble`'s shebang / `set -euo pipefail` / `BASH_SOURCE`
# rules do not apply to it.
#
# It expects the sourcing script to have defined `die STATUS MESSAGE`. Every
# `bin/*.sh` and `deploy.sh` defines one (deploy.sh:91), and a script that
# sources this without one gets a "command not found" at the moment of
# refusal, which is loud.
#
# **Why this is a belt and not the repair.** Since ADR 0218 no product child
# reads the terminal: `container_exec.run()` closes stdin unless input is
# supplied, so the mechanism this refuses cannot occur. The refusal is kept on
# the three commands that reach a container most directly -- `deploy.sh`,
# `bin/db.sh`, `bin/apg-diag.sh` -- because an operator who types the mixed
# shape is better served by a sentence than by a command that works for a
# reason they cannot see. It is deliberately NOT extended to commands whose
# children cannot read the terminal: `sudo bin/doctor.sh --project alpha-dev
# --json > file` at a terminal works today and a guard here would refuse it
# (D1538).

# Refuse the one shape that stops: a terminal on stdin with stdout or stderr
# redirected. sudo's use_pty runs the command in the background of its pty when
# the standard streams are not all terminals, and a child that reads the
# terminal is stopped with SIGTTIN and waits forever, its own timeout unable to
# fire in a stopped process (D972, measured 2026-09-04: three processes in
# state T, nothing applied; re-measured 2026-09-18 in rigs 30a/30a2). Fully
# non-interactive callers (no terminal anywhere) are not this shape.
refuse_mixed_terminal_shape() {
  _apg_guard_name="${1:?refuse_mixed_terminal_shape needs the name it refuses for}"
  if [ -t 0 ] && { [ ! -t 1 ] || [ ! -t 2 ]; }; then
    die 2 "${_apg_guard_name} with stdin at a terminal and stdout or stderr redirected stops at the first docker exec -i under sudo (D972). Run it unredirected; the terminal is the log."
  fi
}

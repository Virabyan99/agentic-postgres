# 0218 — No product child reads the terminal

- **Status:** Accepted
- **Date:** 2026-09-18
- **Session:** 30, Run 2 (D1537, D1538, D1544, D1548)
- **Affects:** `OPS-EXEC-001` (new, Session 30). No schema, no migration, no
  deployed-document field. Every `docker exec` and every `compose run` the
  product performs.
- **Related:** ADR 0093 (a `bin/` command imports only `agentic_postgres` and
  `yaml`), ADR 0195 (a report may not substitute an answer for not knowing),
  D972, D1501, D1504, D1505.

## Context

Since D972 (measured 2026-09-04) this product has known that one of its own
commands stops when run under `sudo` with **stdin at a terminal and stdout or
stderr redirected**. The repair applied at the time was a guard: `deploy.sh`
refuses that shape with a sentence naming D972.

Three things have since shown the guard to be the wrong shape of repair.

- **It is on one command.** D1504 said fourteen callers; the real inventory,
  read at `5444c71`, is **39 call sites in 15 files** — two shell files (four
  sites), eleven `bin/*.py` (thirty-two), two `src/` builders (three) — and
  **`deploy.sh` is not one of them.** It contains the string only in its guard's
  comment and its guard's message, and reaches the pattern one layer down
  through `exec "$(python_bin)" bin/deploy-project.py`. D1504's "fourteenth"
  came from matching the refusal text (D1537).
- **A guard everywhere would refuse working commands.** Four modules already
  pass `stdin=subprocess.DEVNULL` to every exec — `doctor.py:67`,
  `fleet.py:63`, `restore.py:97`, `rehearse.py:76` — and cannot stop under any
  shape. `sudo bin/doctor.sh --project alpha-dev --json > file` at a terminal
  works today, and a guard on `doctor.sh` would refuse it (D1538).
- **D1505's hang was not a `docker exec` at all.** `migrate.py:137`'s
  `run_dbmate` reaches dbmate through `bin/compose.sh … run --rm dbmate` with
  `subprocess.run(command, check=False)` and fully inherited stdio (D1544).

A rule about the *shape a human types* is a rule about a symptom. The
mechanism is a child process reading a terminal it was not given.

### What was measured, with controls, on 2026-09-18

**Rig 30a2** — a throwaway container, `sudo` with `Defaults use_pty`, a
terminal on stdin and stdout redirected, one variable at a time:

| child reads stdin | `-i` | result |
|---|---|---|
| no | no | exit 0 |
| no | **yes** | exit 0 |
| yes | no | exit 0 |
| **yes** | **yes** | **hung; killed at 15 s** |

**Rig 30b2** — `docker compose run` (compose 5.1.3), two services, same shape:

| service command | flags | result |
|---|---|---|
| `true` (never reads stdin) | — | exit 0 |
| `true` | `-T` | exit 0 |
| `true` | detached | exit 0 |
| **`cat` (reads stdin)** | — | **hung; killed at 30 s** |
| `cat` | `-T` + `< /dev/null` | exit 0 |

And the pair ADR 0218 rests on, from rig 30a, through the product's own layer:

| Python call | result |
|---|---|
| `subprocess.run(['docker','exec','-i',C,'cat'])` | **hung** |
| the same with `stdin=subprocess.DEVNULL` | exit 0 |

**The class is exactly: a child that reads stdin, handed a terminal.** Neither
`-i` alone nor a reading child alone stops anything; `docker compose run`
allocates a pseudo-tty but does **not** itself read the terminal. Measured
twice, by two different mechanisms, agreeing.

### What this does not explain

**D1505's stop at `migrate.py:137` did not reproduce.** dbmate does not read
stdin, and rig 30b2's `quiet` arm — a non-reading child under exactly that
shape — completed. The stop D1505 recorded is real and its mechanism is **not
established**; D1544's stated mechanism (*compose allocating a pseudo-tty and
reading it*) is falsified. `run_dbmate` is repaired here anyway, because
nothing reads that stdin and closing it costs nothing, but this ADR claims no
explanation it did not measure.

### A note on how three of this run's premises were wrong

D1548 recorded that WSL's sudo has no `use_pty`, from a grep that ran without
`sudo` against a 0440 file. It has it, and so does the production host
(`/etc/sudoers:Defaults use_pty`). D1542 recorded that an orphaned proof
"cannot read as passed" as an existing property; nothing checks it. Each was a
read that could not read, reported as an answer — ADR 0195's class, three times
in one run. It is named here because the guard this ADR chooses is an **AST
scan over the tree**, which has the property those greps lacked: it cannot
return "absent" when it failed to look.

## Decision

1. **`src/agentic_postgres/container_exec.py` builds and runs every `docker
   exec` the product performs.** `run()` passes `stdin=subprocess.DEVNULL`
   unless `input=` is supplied, and passes `-i` **exactly when** it is — in
   which case stdin is a pipe carrying that input and is never the terminal.
   `-t` is never requested.

2. **`run_dbmate` passes `stdin=subprocess.DEVNULL` and `-T`** after `run`
   (compose's *disable pseudo-tty allocation*).

3. **The two shell commands that exec directly close stdin on the line** —
   `bin/db.sh`'s no-stdin verbs and `bin/apg-diag.sh`'s query get `< /dev/null`.

4. **`deploy.sh` keeps its D972 refusal**, moved — not retyped — into
   `bin/lib/tty-guard.sh` and sourced, with the message's bytes asserted equal
   before and after. It is **not** extended to commands whose children cannot
   read the terminal: a guard that refuses `sudo bin/doctor.sh … > file` would
   break a working command to prevent a hang that cannot occur there.

5. **The one exception is named:** `dev_environment.psql_arguments`' interactive
   `apg dev psql`, which is gated on `sys.stdin.isatty()` and is a developer's
   terminal by design.

6. **The class is guarded against its definition, not its instances.** An AST
   proof asserts that every `subprocess.run/Popen/check_output/call` under
   `bin/` and `src/` whose argv literal begins with `docker` or names
   `compose.sh` either lives in `container_exec.py` or carries `stdin=` or
   `input=`. Its controls: the scan finds the helper's own call, and catches a
   synthetic module with an inherited stdin.

## Consequences

**Makes easy:** any command may be piped, redirected or run from a script
without a human knowing which of 39 sites it reaches. The operator guide stops
needing `script(1)` as a workaround for a product defect.

**Makes hard:** a future `docker exec` that genuinely wants an interactive
terminal must be added to `container_exec` deliberately and named in this ADR,
rather than written inline. That is the intent.

**Costs:** seven modules define their own `psql()`/`docker()`/`in_container()`
and become one-line wrappers or are deleted with their callers re-pointed —
each with a grep of the name **and** of the moved text (D979, D1187). 39 sites
move in one run.

**Enforced by:** `tests/contract/test_container_exec.py` (the argv rule, the
closed stdin, the fed input, no tty, the scan and its two controls);
`test_printed_commands.py:107-152` (the existing D972 refusal, unchanged);
`test_database_commands.py::test_every_shell_docker_exec_closes_or_supplies_stdin`.

## Alternatives considered

**Put D972's guard on all thirteen files.** Refused: it refuses working shapes
(D1538's `doctor.sh` case), it is a rule about a symptom, and it would not have
covered `migrate.py`'s compose run at all.

**A sentence in the operator guide telling operators to use `script(1)`.**
Documentation is not a control — the sentence Session 29 wrote about a
different defect, applied here. D1505 reproduced the hang 25 minutes after the
row recording it was committed.

**Set `stdin=DEVNULL` at each of the 39 sites without a helper.** It would work
today and decay immediately: the 40th site is written by someone who did not
read this ADR. A helper plus a scan makes the 40th site fail a test.

**Do nothing, since no child currently hangs in production.** False comfort:
`deploy-project.py`'s `run()`, its bare `subprocess.run` at `:1745`,
`backup.py:246` and `:291`, `restore-test.py:120` and both shell files inherit
the terminal today, and `backup.py:291` is where D1501's seven-minute stop
happened.

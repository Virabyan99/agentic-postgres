# 0157 — A preflight reports every absent prerequisite, and says so when it did not look

- **Status:** accepted
- **Date:** 2026-08-27
- **Session:** 11, Run 2 (`DEP-PRE-001`)
- **Related:** **D614** (the three checks run after the render and fail one at a
  time), **D631** (the daemon call has no timeout and hangs on accept-then-
  silence), **D600** (a `null` that looks measured is worse than an absent
  field), ADR 0063/0133 (the deploy does not create its own preconditions),
  ADR 0096 (re-derive from the event, do not restate).

## Context

`DEP-PRE-001` asks that *a missing prerequisite stops deployment before it
changes anything, and lists every absent item.* Neither half held.

**The checks run too late.** `require_edge_is_up`, `require_bootstrap` and
`require_secret_generation` are step **2** of `bin/deploy-project.py`. Step **1**
has already run the render, which writes `.generated/<key>` and hands its
ownership back. A deploy refused for a missing secret generation has therefore
already changed the checkout.

**And they fail one at a time.** Each calls `fail()`, which exits. An operator
missing three things learns about one, supplies it, and learns about the next —
three round trips on a host where every one of them needs `sudo` at a TTY.

There is a third problem, and it is the one that decides the shape. The four
things worth checking are not independent: **the edge check is a question you
ask the Docker daemon.** If the daemon cannot be reached, the honest answer to
"is the edge plane running" is *nobody looked* — and the obvious implementation,
a list of booleans, has no way to say that. It would report the edge as absent
and send an operator to restart a stack that was never examined.

That is D600's family exactly: a value that looks measured and is not. D600 wrote
`null` into five drill evidence documents and passed a whole host gate green.
Here it would print a sentence about a container nobody asked about.

## Decision

**A step 0 preflight**, before the render, which reads and reports and changes
nothing — and **three verdicts, not two.**

| Verdict | Meaning |
|---|---|
| `present` | Measured, and it is there |
| `absent` | Measured, and it is not there |
| `undetermined` | **Not measured**, because something it depends on was not there |

An `undetermined` item names what stopped it — *"not checked: the Docker daemon
could not be reached"* — and carries no remedy of its own, because the remedy is
the thing it depended on. It blocks the deploy exactly as an absence does: a
deploy cannot proceed on a prerequisite nobody verified.

Four items, in the order the deploy needs them:

1. **the Docker daemon** — `prerequisite`
2. **the edge plane** — `precondition`, and `undetermined` whenever (1) is not present
3. **the provider bootstrap** — `precondition`, a filesystem read, always determinable
4. **the active secret generation** — `precondition`, likewise

**The daemon call takes an explicit timeout** (D631). Measured in Run 1: a
missing socket, a closed port and an unroutable address all fail in ≤0.03 s with
usable stderr, but a listener that *accepts and never answers* left `docker ps`
running past 20 s — because `run()` passes no `timeout=`. A wedged dockerd, a
DROPping firewall and a daemon under load all present that way. An expired call
is `undetermined`, not `absent`: a daemon that accepted the connection may well
be there, and "start Docker" is the wrong advice for one that is running badly.

**The exit code is the one the first blocking item would have produced on its
own** — the daemon maps to `3` (missing prerequisite), the other three to `4` (a
precondition of this session has not been run). This reproduces today's codes
exactly for every cause that produces one today, so the aggregate report is added
without any caller's contract moving.

**Step 2's `require_*` stay exactly where they are.** They are not duplicated and
not deleted. They remain the second line, and — more importantly — they *return
the values the deployed document is built from*. A preflight that returned those
values would be a second authority over them, and the document would be built
from whichever ran last.

**The logic lives in `src/agentic_postgres/preflight.py`; the subprocess lives in
`bin/deploy-project.py`.** That is `database_observation`'s split, for
`database_observation`'s stated reason: *"the parsing lives here and the
subprocesses live in `bin/deploy-project.py`, which is what makes any of it
testable without a host."* Every existing test of this file is a source-level
text scan, because the file needs root; a pure module is testable behaviourally
and its mutants can actually be killed.

## Consequences

- An operator missing three things is told three things, once, with the command
  that supplies each — and the commands name the manifest paths they were invoked
  with rather than a `<manifest>` placeholder.
- **A refused deploy has written nothing.** The preflight precedes the render, and
  everything before it — argument parsing, the root check, manifest loading, key
  derivation — was already read-only.
- **"The edge is not running" is now a sentence this program can only print when
  it asked.** The undetermined verdict is what makes that true by construction
  rather than by the author remembering.
- A deploy on a healthy host pays one extra `docker ps` — 0.12 s measured — and
  three stats.
- The report is printed on refusal **and** on success, so a passing preflight is
  visible in a deploy log rather than silent. An operator reading a failed deploy
  further down can see what was true at the start.

## What the battery established, including what it did not

Nine arms, **9 killed, 0 survived, 0 defective** — every control green in the
same invocation, and every arm `FAILED` rather than `ERROR`, so each assertion
was actually reached (D386).

The arms worth naming are the ones that guard this ADR's own reasoning rather
than its arithmetic:

- **M1 (the edge stops distinguishing "nobody asked" from "not running") and M3
  (an undetermined prerequisite stops blocking): both KILLED.** These are the two
  ways the three-verdict design could be silently reverted to a boolean, and both
  are held.
- **M6 (an undetermined item starts offering a remedy): KILLED.** The absence of
  a remedy beside an unmeasured check is asserted, not merely intended.
- **M2 (a wedged daemon is reported as absent): KILLED**, with
  `test_the_edge_is_undetermined_…` as the control — a test that calls
  `docker_daemon` on the *refusal* path and therefore cannot reach the timeout
  branch the mutation edits.

**The controls were chosen to be unreachable by their arms**, which is D499's
rule after four instances. `test_a_multi_line_error_is_collapsed_to_one_row`
carries three arms because `_one_line` is touched by none of them.

## What running it found that reading it did not

**D636, and it is the reason this ADR gained a fourth state on two checks that
were specified with three.** A smoke run of `observe_prerequisites` as an
unprivileged user did not report absences — it **raised**:

    PermissionError: [Errno 13] Permission denied:
      '/var/lib/agentic-postgres/secrets/.../active-secret-generation.json'

`Path.exists()` swallows `ENOENT`, `ENOTDIR`, `EBADF` and `ELOOP`, and **raises
`EACCES`**. Both state roots are `0700 root`. The deploy runs as root so this
never bites in production — which is exactly what makes it the kind of defect
this project keeps producing: correct for as long as its wrong answer happens to
coincide with the right one.

Two things follow, and the second matters more than the first. Every `exists()`
in the probe is now guarded. And an unreadable file is **`undetermined`, not
`absent`** — because "run `materialize-secrets.sh`" is the wrong instruction for
a generation that is present and merely unreadable, and re-materialising is not
free: it writes a *new* generation. The vocabulary this ADR introduced for the
daemon turned out to be the right vocabulary for a `stat` as well.

## What this does not decide

**Whether the manifests should be batched too.** `load_host_manifest` and
`load_project_manifest` still fail one at a time, above the preflight. They are
*invalid operator input* (exit `2`), not *missing prerequisites* (exit `3`/`4`),
and `DEP-PRE-001` is about the latter. Batching them is defensible and is a
different requirement; doing it here would have widened this decision to cover a
class it was not measured against.

**Whether `undetermined` should ever be non-blocking.** Today every non-`present`
verdict blocks. A future check that is genuinely advisory — disk headroom below a
soft threshold, say — would need this reopened, and `OPS-001`'s `doctor.sh` is
where that pressure will come from first.

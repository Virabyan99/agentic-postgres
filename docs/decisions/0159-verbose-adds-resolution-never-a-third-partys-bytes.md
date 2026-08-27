# 0159 — `--verbose` adds resolution, never a third party's bytes

- **Status:** accepted
- **Date:** 2026-08-27
- **Session:** 11, Run 4 (`OPS-001`)
- **Related:** **D622** (a denylist tests the denylist), `storage_client.redact`
  (*half-redacting is worse than not logging*), **D374** (a test can check a
  string its target cannot contain), ADR 0158, ADR 0106 (the image never
  assembles a URL), §6 (*no secret value may enter logs*).

## Context

`OPS-001` asks for a diagnostic that reports every required check **without
secrets**, and Run 3 shipped the checks. A `--verbose` is the obvious next thing
and it is also the obvious way to undo the requirement: the most useful thing to
show behind a failing check is what the failing command said, and what a failing
command says is exactly where a credential surfaces.

`pgbackrest` errors name repository paths. `psql` errors quote connection
strings. `curl` echoes URLs. None of these is a secret *by design*, and all of
them are places one has appeared.

The tempting design is a redaction filter over subprocess output. This
repository has already rejected that reasoning once, in
`storage_client.redact`'s docstring:

> Half-redacting is worse than not logging: a URL missing only
> `X-Amz-Signature` still names the bucket, the key and the account.

And D622 names the second problem: a filter is a **denylist against a third
party's future output**, so a test of it is a test of the denylist. It passes
because the pattern matches the string the test chose, which says nothing about
the string `pgbackrest` 2.60 will emit.

## Decision

**Verbose prints only values this program produced.** Parsed integers, booleans,
timestamps read out of a catalog view, and constants from this repository. Never
a byte a subprocess emitted, never an environment variable, never a path under
the secret root.

Structurally, not by rule:

- `Check` gains `evidence: tuple[tuple[str, str], ...]`, and it is populated by
  `diagnosis._pairs(**values)` — which takes *values* and does the `str()`
  itself. A caller cannot hand it a pre-formatted string, so "only what this
  program produced" is a property of the construction rather than a habit each
  probe has to keep.
- **`verbose` reaches the renderer and nothing else.** There is no verbose branch
  in any probe in `bin/doctor.py`. A probe cannot print more when verbose because
  a probe does not know about verbose.
- The probes never put `.stdout` or `.stderr` into a `Check`. That is asserted by
  an AST scan, not left to review.

What verbose therefore adds is **resolution**: the numbers a verdict was computed
from, so an operator can see *why* a check said what it said rather than being
asked to trust it. `disk headroom` shows `cluster_kb`, `available_kb` and both
thresholds; `tls` shows the days remaining and the constant it was compared
against. In workstation mode it adds each tool's resolved path — from
`command -v`, which is a lookup rather than a dump of what is set.

**A failing third party is reported as a verdict, not as a transcript.** The
information an operator loses is real, and the replacement is the exit code plus
the command they can run themselves — which they have, because every probe here
is a command that already exists.

### The line, drawn precisely

"Never a third party's bytes" is the slogan, and taken literally it forbids
printing an unhealthy container's name — which arrives as `docker ps` stdout and
is the single most useful thing that check can say. So the rule is stated by
channel rather than by origin:

**May travel into a `Check`:**

- integers and booleans the probe parsed;
- **fields extracted from structured output whose shape this repository knows** —
  a `pg_stat_archiver` row, a `docker ps --format` line, a `df` column, the JSON
  `bin/backup.sh info --json` emits. Each has a defined position, is read by
  position, and holds a value of a known kind.

**Never travels, at any verbosity:**

- a command's **stderr**, in any branch;
- **unstructured stdout** — an `openssl s_client` handshake, an error page, a
  usage message;
- argv, environment, and any path under the secret root.

A container name is a name `naming` derived and Compose was given; a
`last_archived_time` is a timestamp out of the product's own catalog view. Those
are the product's structured output being read back, not a third party's prose.
A `pgbackrest` error string is prose, and prose is where a credential appears.

**This is what the redaction test measures**: the sentinel goes into every
stderr and into the unstructured stdout, while the structured channels carry
realistic values — so the test asserts the actual rule instead of certifying a
stricter one nobody implemented.

## Consequences

- Adding a check means adding its evidence, and the evidence can only be values.
  A future probe that wants to show a stderr has to change this ADR first.
- **The redaction proof is a sentinel scan, not a pattern assertion** (D622). The
  test plants a random sentinel in every place a value could come from — the
  deployed document, the environment, and every subprocess's stdout *and* stderr
  — runs the real probes against a stubbed subprocess layer, and asserts the
  sentinel appears nowhere in verbose output. Its **control is a deliberately
  leaky renderer** that the same scan catches, which is what stops the test from
  passing because it was scanning nothing (D374).
- `test_commands_do_not_echo_a_planted_environment_variable` gains `--verbose`.
  That test was written when `doctor.sh` had one mode, and a mode added later is
  a mode it was not covering — Question 5's shape, caught by asking it.

## What this does not decide

**Whether a failing probe should be able to say more on request.** A
`--explain <check>` that ran one command and showed its output under an explicit
second opt-in is a defensible future thing, and it is a different decision: it
would be an operator asking for a transcript, not a flag that produces one as a
side effect of asking for detail. Nothing here forecloses it.

**Whether the workstation mode's tool paths are worth anything on a host.** They
are a developer-machine answer to a developer-machine question ("which `docker`
is this?"), and deployed mode does not print them.

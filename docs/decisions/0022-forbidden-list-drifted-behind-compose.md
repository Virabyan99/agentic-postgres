# 0022 — The forbidden list drifted behind the Compose surface it covers

- **Status:** Accepted
- **Date:** 2026-08-06
- **Session:** 2
- **Affects:** `bin/compose.sh`, `test_the_forbidden_list_is_unchanged_from_session_one`

## Context

`bin/compose.sh`'s `FORBIDDEN` constant is the default refusal: without
`--runtime`, every subcommand in it is refused with exit 10 before Compose is
ever invoked (runbook §2, ADR 0013's "Session 2's largest security control").
It was set once, in Session 1, to the eight subcommands that create or start
a container in the Compose surface as it existed then:

```sh
readonly FORBIDDEN="up run start create restart exec attach cp"
```

`test_the_forbidden_list_is_unchanged_from_session_one` pins exactly that
list, verbatim, and its docstring calls the result "the inherited contract."
The test enforces that the list does not shrink. It does not, and cannot by
construction, notice that the list needs to *grow* — Compose itself is not
static, and a subcommand added to Compose after Session 1 that creates or
starts a container is invisible to a test that only ever compares the file
against its own past self.

That is exactly what happened. `docker compose watch` ("rebuild/refresh
containers when files are updated") and `docker compose scale`
("scale services") were both audited against the currently installed Compose
(v5.1.3) while investigating a report that `watch` was missing from
`FORBIDDEN`. `watch`'s own `--help` text documents that it starts containers.
`scale` was confirmed empirically: running `docker compose scale web=2`
against a service with zero existing containers pulled the image, created a
network, and created and started two containers — a full `up`-equivalent
side effect from a subcommand whose name gives no hint of it. (`docker
compose scale --help`'s `--no-deps: Don't start linked services` flag is the
same fact documented from the other direction: there would be nothing to
decline starting if `scale` didn't start something by default.)

Neither subcommand was in `FORBIDDEN`. Without `--runtime`, `main()`'s
`elif in_list "${subcommand}" "${FORBIDDEN}"` branch is the *only* thing
standing between an operator and a real `docker compose <subcommand>`
invocation — reaching the `elif`'s false branch falls through to the
unconditional `exec` at the bottom of `main()` with no root check and no
`--runtime` flag anywhere in the call. `bin/compose.sh <dir> watch` and
`bin/compose.sh <dir> scale web=2` both started containers this way: the
exact guarantee `FORBIDDEN` exists to provide, defeated by nothing more than
Compose having grown since the list was written.

This is the second defect of this shape in this file. ADR 0021 found that
`first_subcommand` didn't know about every flag Compose accepts ahead of a
subcommand, so a value-taking flag it didn't recognize let a forbidden
subcommand through unexamined. This ADR finds that `FORBIDDEN` didn't know
about every subcommand Compose accepts, so a subcommand it didn't list let
itself through unexamined. Both are the same failure at one remove: the
wrapper's refusal logic was written against a snapshot of what Compose
accepts, and Compose's accepted surface is neither closed nor owned by this
repository.

## Decision

Add `watch` and `scale` to `FORBIDDEN`:

```sh
readonly FORBIDDEN="up run start create restart exec attach cp watch scale"
```

Neither is added to `RUNTIME_ALLOWED`. A subcommand present in `FORBIDDEN`
and absent from `RUNTIME_ALLOWED` is refused in both modes: without
`--runtime` by the `elif in_list "${subcommand}" "${FORBIDDEN}"` branch
(exit 10, "would start or create a container"), and with `--runtime` by the
`in_list "${subcommand}" "${RUNTIME_ALLOWED}"` check (exit 10, "not
permitted in --runtime mode"). This is the same treatment `exec`, `attach`,
`run`, and `cp` already get, for the same reason: nothing in Session 2's
documented path needs `watch` or `scale`, and an operator who does can say
so in an ADR of their own.

`test_the_forbidden_list_is_unchanged_from_session_one` is retired in name
and in claim. It is renamed and its docstring rewritten to say what it now
pins — that `FORBIDDEN` matches the currently audited Compose
container-starting surface — and to cite this ADR for why the list grew from
eight entries to ten. The list itself is a strict widening: every subcommand
the old list refused, the new list still refuses; nothing already forbidden
is loosened.

The audit that produced this list is manual, against one installed Compose
version, and is recorded here rather than automated: Compose has no
machine-readable "these subcommands create or start containers" manifest to
diff against. A future Compose release could add another one. This ADR does
not close that gap — it only fixes the two instances found by this audit —
and says so plainly rather than implying the list is now permanently
complete.

## Consequences

- `bin/compose.sh <dir> watch` and `bin/compose.sh <dir> scale ...` are
  refused with exit 10 by default, matching every other container-starting
  subcommand.
- `bin/compose.sh <dir> --runtime watch` and `--runtime scale`, even as
  root, are refused with exit 10 ("not permitted in --runtime mode") rather
  than succeeding — `RUNTIME_ALLOWED` is unchanged.
- The renamed test asserts the ten-item list and documents, in its
  docstring, that the list is an audit result tied to this ADR rather than
  an immutable inheritance from Session 1.
- New tests confirm `watch` and `scale` are refused without `--runtime`
  (exit 10, the `FORBIDDEN` message) via the real script. Confirming the
  `--runtime`-as-root-equivalent refusal (exit 10, the `RUNTIME_ALLOWED`
  message) via a real subprocess is not possible as a non-root test process:
  `main()`'s privilege check (`--runtime requires root`, exit 3) runs
  unconditionally before the `RUNTIME_ALLOWED` check, for every subcommand,
  so a non-root caller can never observe the allowlist message at all. That
  test instead sources `bin/compose.sh`'s real definitions and runs the
  literal `RUNTIME_ALLOWED` conditional directly, bypassing only the
  privilege check line, the same technique already used to test
  `OVERRIDE_REQUIRED` for the same reason.
- Nothing about `RUNTIME_ALLOWED`, `NEEDS_DAEMON`, or `VALIDATES_SECRETS`
  changes. `watch` and `scale` were never reachable through any of those
  paths and still are not.

## Alternatives considered

**Derive `FORBIDDEN` from `docker compose --help` at run time, or from some
other machine-readable Compose manifest.** Rejected: Compose does not
publish which subcommands create or start containers versus which merely
inspect or remove them; that judgment has to be made by reading each
subcommand's behavior, which is exactly the audit this ADR records. A
runtime-derived list would also make the refusal depend on whatever Compose
version happens to be installed on a given host, silently changing behavior
across a Compose upgrade with no review step — the opposite of the auditable,
committed list this repository has used since Session 1.

**Leave `FORBIDDEN` as the Session 1 list and add a separate, narrower
denylist for subcommands discovered later.** Rejected: two lists serving the
same purpose is two places a reviewer has to check, and the residual defect
this ADR closes is exactly a subcommand that fell through the gap between
"the list we wrote" and "what Compose actually accepts" — adding a second
list does not close that gap, it just moves where the next miss can happen.

**Leave it.** Rejected: `watch` and `scale` starting containers with no
`--runtime` and no root is a live instance of the defect ADR 0013 calls
"Session 2's largest security control," reachable by any caller today.

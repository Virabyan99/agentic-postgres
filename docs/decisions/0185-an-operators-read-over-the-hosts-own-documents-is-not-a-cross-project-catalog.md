# 0185 — An operator's read over the host's own documents is not a cross-project catalog

- **Status:** accepted
- **Date:** 2026-09-04
- **Session:** 17, Run 1 (`FLEET-INV-001`, `FLEET-INV-002`, D945–D948)
- **Related:** `docs/product-contract.md` §5 (the non-goals), **D709** (every
  registry field is already published per project), **D945** (the brief's
  inventory against the contract's non-goal), **D947** (nothing reads more than
  one document at once), **D948** (denial rates and the metrics credential),
  **ADR 0158** (the deployed document is the address book, not the diagnosis),
  **ADR 0071** (read-only diagnosis by an enumerated verb), **ADR 0002** (an
  identity is derived once), `docs/plans/stage-2-plan.md` §9's first stop
  condition.

## Context

The stage plan's Session 17 brief asks for *"a thin, file-based,
non-authoritative registry aggregating the deployed documents that already
exist, with a cross-project inventory view showing health, backups and
agent-denial rates."* The product contract's §5, frozen since Session 12, lists
among things that are *"not deferred — outside the product"*: **"a shared,
multi-tenant control plane, or any cross-project shared catalog"** and
**"cross-project reporting or aggregation."** Read literally, the brief builds
the non-goal.

Measured at planning time (D945–D948):

- Every field the brief asks the registry to record is already published, per
  project, in `/etc/agentic-postgres/projects/<key>/outputs.json` (D709).
- **Nothing in the tree reads more than one project's document at once**
  except `apg-diag containers`, whose loop over `PROJECT_ROOT` is root,
  read-only, and container-only. `doctor.sh` is per-project and text-only.
- The "denial rate" exists as `agent_tool_calls_total{outcome, tool}` on the
  `/metrics` route, behind the project's metrics Basic Auth credential — and
  the alert rules deliberately do not alert on `refused`, because *"a refusal
  is the boundary working."* An inventory that scraped the route would hold a
  credential, which the brief itself forbids.
- The stage plan's own §9 stops the session if *"the registry needs authority
  it is forbidden — to read a project's data, to hold a credential, or to be
  consulted before a request is authorized."*

So the question is not whether to build a registry. It is **which side of the
non-goal an operator's inventory falls on**, and the contract did not say.

## Decision

**The non-goal protects the surface a project serves. An operator's read over
the deployed documents already on the host's own disk is not a cross-project
catalog, and it keeps four properties that make that true by construction:**

1. **No route.** Nothing the inventory produces is reachable over HTTP, from a
   container, or from any project's network. It is a command run as root at a
   terminal, like `doctor.sh --project` and `apg-diag`.
2. **No service, no daemon, no schedule.** It runs when an operator runs it and
   holds no state between runs. There is nothing to be *lost*, so *"can be
   deleted and reconstructed"* is vacuous and is asserted as **writes nothing**
   (`FLEET-INV-002`, measured by mtime).
3. **No credential.** It reads the documents as root, runs the doctor's probes
   in-process, and reads denial counts from `app_private.agent_audit` over the
   container socket — the route `doctor.py` already takes. It never presents
   the metrics credential, an agent secret, or a token to anything.
4. **No reader.** No command, unit, route or service in the release consumes a
   fleet artefact. The inventory is the end of a chain, never a link in one;
   in particular it is never consulted before a request is authorized.

**What it reports is derived once and printed under its own key.** Identity and
release come from the document (`naming` derived them; the inventory re-derives
nothing, ADR 0002). Health is doctor's live verdicts, never the document's
status blocks (ADR 0158). Backups are the timer state and the age of the last
full backup, never `backup_state.status` (D700, D944). Denials are **counts by
`denial_reason` over a window**, because the taxonomy (ADR 0178) is the
operator's question and a rate erases it — and because the alert plane has
already decided a refusal is not an alarm.

**The contract's wording gains one paragraph** saying what the two non-goals
protect and that this read is not the catalog they name. The non-goals
themselves do not move.

## Consequences

- `bin/doctor.py --json` exists (this run), so the inventory composes a
  document rather than parsing a table — the alternative was a second parser
  of one report, D486's shape.
- The four properties are the offline half of `FLEET-INV-002`, each a guard: a
  scan that no service, unit or route names the inventory; a run against a
  fixture root that diffs mtimes; a redaction scan over the inventory's output
  identical to the doctor's.
- If a future session wants any of the four to fall — a route, a schedule, a
  credential, a reader — that is the stop condition, and the answer is a Stage
  3 specification for a control plane, not a wider inventory. This ADR is the
  line, and it is here so that crossing it is a decision somebody takes rather
  than a feature somebody adds.
- The inventory's per-project rows are exactly as stale as the doctor's live
  probes are fresh: nothing is cached, and a row is computed when the command
  runs. An inventory that cached would need property 2 relaxed.

# Stage 5 decision report

Written at Session 35 Run 11 (2026-10-03) and **filled from
`evidence/session-35.json` and `capacity.ENVELOPE`, with the counts a release
moves read from the tree at the tagged commit** (D1890, D992's rule applied a
third time). The filling script (`~/s35r11/s35-r11-fill.py`) reads every
number out of its source and asserts it, and refuses a placeholder left
behind, so no blank can be completed from memory. §6 alone is written by the
executor from §1–§5, and it is marked as that reading.

**The document says: 198 claims, 192 passed, 1 failed,
5 not_run**, at `source_commit f7fb96d3dd6c` with the offline half
measured at `f7fb96d3dd6c` — the deployed and tagged commit (`1.13.0`).

---

## 1. What 1.13.0 is

`template_version` 1.13.0, `CURRENT_SESSION` 35. A minor under ADR
0162: it adds released migration 0037 (`app.require_approval`, granted to
nobody), project manifest schema 8 (`migrations.approvals_required`, default
0), the proposal and approval records under `projects/<slug>/proposals/`, the
host gate in deploy step 6, mem_limit on four more services per project and on
the edge, and `apg-diag`'s reach into three more logs. Outputs, the capability
manifest and both locks keep their schemas. `upgrade plan` priced it on the
host before either deploy: **bump minor, requires minor, verdict ok, 2 leaves differing** on alpha and **bump minor, requires minor, verdict ok, 4 leaves differing**
on beta with the added migration declared, `requires patch` without it.

What 1.13.0 closes is Stage 4, whose six sessions are: 30 the inheritance, the
rotation and the two decisions; 31 the node as a finite resource; 32 the durable
step substrate and workflow execution; 33 gates, compensation and provenance;
34 governed connectivity; 35 change governance, hardening and this release.

## 2. What was measured

| Measure | Value | Source |
|---|---|---|
| Claims | 198 | `evidence_claims.CLAIMS` |
| Passed | **192** | `evidence/session-35.json` |
| `not_run` | **5** — `api_authorization`, `bootstrap_identity`, `credential_rotation_planes`, `port_allocation`, `replacement_host_restore` | the same document; §3 |
| Failed | **1** — `documented_path` | the same document; §3 |
| Suites | host 1,082 / 1 / 7; external 25 / 0 / 8; offline 6,897 / 0 / 3 (passed / failed / skipped) | the same document's `suites` |
| Requirements in the registry | 291 | `tests/acceptance-registry.yaml` |
| Requirements a claim reports on | 267 | the union of every claim's `requirements` in the document |
| Claims declared offline | 60 | `evidence_claims.OFFLINE_CLAIMS` (ADR 0202) |
| Migrations released and applied | 37 | `migrations/released.lock.json`; both ledgers read on the trip |
| Architecture decisions | 245 | `docs/decisions/`; 0216–0245 are Stage 4's |
| Divergences measured | D1–D1944 | Stage 4's are D1537–D1944; Session 35's D1857–D1944 |
| The walk of the documentation | **not walked for 1.13.0** — Sheet W (c), the operator's decision of 2026-10-01 (D1935), deferring it until after Stage 5; the sweep read the Session 25 record, so `documented_path` is `failed` by decision | the plan's Sheet W |
| A deploy's downtime, per class (alpha / beta, through the edge) | rest 10.2 s (bound 11.4 s) / 11.5 s (bound 12.7 s); auth 16.4 s (bound 17.7 s) / 12.7 s (bound 13.9 s); storage 16.4 s (bound 17.7 s) / 12.7 s (bound 14.0 s); mcp 14.8 s (bound 16.1 s) / 14.2 s (bound 15.4 s); docs 12.5 s (bound 13.8 s) / 11.9 s (bound 13.1 s) | `capacity.ENVELOPE`, Session 35 rows |
| Recreating the edge | 24.4 s observed on all four targets (bound 27.1 s), both projects at once | `capacity.ENVELOPE` |
| A database restart (induced by the rehearsal) | rest 3.1 s unreachable (bound 4.4 s, every answer a 503); auth, storage, mcp and docs no window; every dependent reconnected in 6.9 s | `capacity.ENVELOPE` |
| The neighbour, one project's REST saturated | beta-dev p50/p95/p99 49.58/107.78/156.62 ms (n 953), 0 errors, 0 x 429 (57,706 requests at 472.94 req/s on alpha) / alpha-dev p50/p95/p99 50.37/98.34/133.94 ms (n 957), 0 errors, 0 x 429 (490.85 req/s on beta) | `capacity.ENVELOPE`, phases C and D |
| The neighbour, both idle | alpha-dev p50/p95/p99 41.84/53.96/76.82 ms (n 481); beta-dev p50/p95/p99 41.18/53.0/77.46 ms (n 480) | phase A |
| The neighbour, 24 workflow runs on beta | alpha-dev p50/p95/p99 41.15/55.36/74.23 ms (n 967) | phase B |
| `auth` memory while runs execute (D1711) | median 63.13 MB, max 73.38 MB over 104 samples inside a run; outside 62.91 / 73.61 MB (1108 samples) -- against ADR 0226's 96 MiB under-load criterion | `capacity.ENVELOPE` |
| The host | 3814 MiB RAM, no swap, 2 vCPU; 2073 MiB available with both projects and the edge running; caps summed 6432 MiB across 3 compose projects (ceilings, not reservations, D767); 608 MiB committed across 2 projects of 1600 MiB claimable | Sheet F4b's E0 transcript and `doctor capacity` |

## 3. What stayed `not_run` or `failed`, and why

| Claim | Status | Why |
|---|---|---|
| `documented_path` | failed | **By decision.** Sheet W (c): no walk of 1.13.0; the walk is deferred until after Stage 5 (D1935). The sweep read the Session 25 record, eleven undocumented steps, so the claim reports what that record says. |
| `api_authorization` | not_run | As `bootstrap_identity`: the remaining rotations are owed. |
| `bootstrap_identity` | not_run | The rotation trio needs FOUR rotations; one was performed (2026-09-19, ADR 0224). |
| `credential_rotation_planes` | not_run | As `bootstrap_identity`: the remaining rotations are owed. |
| `port_allocation` | not_run | Awaits an event, not a run: `--after-reboot` needs a reboot this trip did not take. |
| `replacement_host_restore` | not_run | **By decision** (D1028): a rehearsal ends at the restore. |

## 4. What Stage 4 built against its specification

The stage plan's §3 collapsed the specification's twenty-four sessions to six.
Each paragraph below says what the session built and how its claims stand in
the merged document of the release that closes the stage.

**Session 30 — inheritance, the rotation and the two decisions.** The B2 mirror repaired (ADR 0220), every container exec through one helper with the class guarded at zero (ADR 0218), `release-reading --ref`, ADR 0216 (no public Postgres endpoint in Stage 4) and ADR 0217 (nothing may need a hosted trust model to be safe), and **the signing key rotated on both projects on 2026-09-19** -- the first credential this product ever moved on a deployment (ADR 0224). *Claims added: 6 (5 declared offline) -- 6 passed in the merged document.*

**Session 31 — the node as a finite resource.** `host.yaml` schema 3 declares the machine; deploy step 0 charges a candidate against what the other projects commit and refuses at exit 12 (ADR 0221/0222); `pids_limit` and `cpus` on every service; the collector and Prometheus bounded and read back by `doctor capacity|usage`. *Claims added: 10 (6 declared offline) -- 10 passed in the merged document.*

**Session 32 — the durable step substrate and workflow execution.** Workflow definitions compiled from the lock and installed by deploy step 6d; runs and steps in `app_private` behind definer functions; the worker is a loop inside `auth` holding nothing the invoking agent does not (ADR 0226-0229); one idempotency key per step; the `worker-restart` rehearsal. *Claims added: 13 (8 declared offline) -- 13 passed in the merged document.*

**Session 33 — gates, compensation and provenance.** Approval steps park on the plane's own refusal and resume on a person's decision; compensation in reverse; provenance joined to the plane's audit by request id; the audit's filters and cursor (ADR 0230-0234). *Claims added: 14 (10 declared offline) -- 14 passed in the merged document.*

**Session 34 — governed connectivity.** `app.emit_event` granted to nobody, the outbox, signed outbound delivery with dead letters, the signed inbound route, scheduled connectors and the event wait, behind a facility one manifest enables (ADR 0235-0241). *Claims added: 16 (11 declared offline) -- 16 passed in the merged document.*

**Session 35 — change governance, hardening and the release.** The database refuses an agent's direct call to a gated function (`app.require_approval`, ADR 0242); a project set's change is proposed and approved on the workstation and applied only when the committed proposal names it (ADR 0243); every running container bounded (ADR 0244); `apg-diag` reads every service's log, redacted (ADR 0245); deploy downtime and the noisy neighbour measured into the envelope. *Claims added: 10 (7 declared offline) -- 10 passed in the merged document.*

**Deferred with hosting, by the operator's decision of 2026-09-18** (ADR 0216,
ADR 0217): the specification's sessions 50, 51, 52, 57, 58, 59 and 60 —
organisations, members, roles, `apg login`, remote lifecycle, hosted Studio,
support grants, a control-plane store, a public endpoint. **Cut, each with its
row**: a candidate stack or blue/green (D1524 — measured instead, §2's deploy
windows), load-shedding classes (D1520), `apg tune` (D1535), the §13–§14
technologies (D1530), the control-plane failure contract (D1534), and the
`PolicyProposal`/`WorkflowProposal`/`UpgradeProposal` family (D1523 — Session
35 built the project-set proposal only).

## 5. The hosted question, priced against Stage 4's readings

The stage plan's §6 lists what a Stage 5 reading pays to take up the hosted
platform. Each item, with the fact Stage 4 measured that bears on it:

| Precondition | Where it stands | The reading that bears on it |
|---|---|---|
| **The rotation performed** | Once of four: the signing key was rotated on both projects on 2026-09-19 (ADR 0224); the trio of rotation claims stays `not_run` | `bootstrap_identity` not_run, `api_authorization` not_run, `credential_rotation_planes` not_run |
| **The tenancy non-goal changed by an ADR** | Not taken; `product-contract.md` §5 and ADR 0216/0217 stand | two projects on one host share exactly the edge; the isolation matrix's 18 pointers hold on both (`project_isolation` passed) |
| **A registry that is authoritative** (ADR 0185) | Not built | the fleet is still an operator's read of two deployed documents |
| **A threat model for external users** | Not written; `docs/threat-model.md` models an operator and their agents | THR-CHANGE (Session 35) and THR-NOISY-NEIGHBOUR are the newest rows; a hosted reading adds every row a stranger's credential implies |
| **TLS for the PostgreSQL protocol, a listener, the isolation matrix extended to it** | Not built; there is no public Postgres endpoint (ADR 0042/0044/0216) | — |
| **A credential that travels, rotating on a schedule** | One master per project for connectors (D1784); rotation is an operator act | the same rotation reading |
| **One ADR superseding 0042, 0043 and 0044 together** | Not written | — |
| **Capacity for more than two projects** | Declared and enforced at deploy step 0 | the host declares 3814 MiB with 1600 MiB claimable by projects; two projects commit 608 MiB (304 each); admission refuses at exit 12 whatever would not fit; every running container is capped, the caps summing to 6432 MiB against 3814 MiB of RAM |
| **What one tenant's load does to another** | Measured once, as a sample (Session 35) | beta-dev p50/p95/p99 49.58/107.78/156.62 ms (n 953), 0 errors, 0 x 429 (57,706 requests at 472.94 req/s on alpha) against an idle 41.18/53.0/77.46 ms (beta, phase A) |
| **The price of any change to the shared ingress** | Measured | 24.4 s observed on all four targets (bound 27.1 s), both projects at once |
| **What a hosted operator would carry forever** | Nothing in `app_private` is pruned (D1886) | the retention bill on beta after five sessions: workflow_definition 7 (oldest 2026-09-26), workflow_run 133 (oldest 2026-09-26), workflow_step 372 (oldest 2026-09-26), workflow_worker 1 (oldest 2026-10-02), workflow_approval 29 (oldest 2026-09-28), workflow_attempt 327 (oldest 2026-09-28), connector 4 (oldest 2026-09-30), connector_event 9 (oldest 2026-09-30), connector_delivery 9 (oldest 2026-09-30), connector_receipt 10 (oldest 2026-09-30) |

## 6. Recommendation

*This section is the executor's reading of §1–§5, written for the operator, who
accepts or rewrites it before it is committed (the recommendation is a
decision, and decisions here are the operator's).*

**Close Stage 4 on this evidence, and do not start the hosted platform as
Stage 5's first work. Pay the appliance's operating debt first, and take the
hosted question as an explicit ADR when — and only if — the operator wants a
customer.**

**What the evidence supports.** Every claim is answered: 198 claims,
192 passed, 1 failed by decision, 5 `not_run`, and each of
the six not-passed names an event or a decision rather than a gap (§3). The
stage's failure mode — a second principal holding more than the identity it
acts for — was tested on a deployment at every step: the worker, the approval,
the connector and now the database guard each passed live, the last of them by
the database refusing an agent's own token with no row written. The appliance
is bounded (every container capped), admits only what fits, and its change
process now leaves a committed record of what was applied and who approved it.

**What the measurements say about sharing one host.** Two projects coexist
with headroom and with a cost a tenant would notice: saturating one project's
REST moves the other's p95 from about 54 to about 100 ms with no errors, and
workflow runs move nothing. But the edge is shared, and recreating it is an
outage of every project on the host for about 24 seconds; every deploy takes
a project's API away for ten to seventeen seconds by design. Those are fine for
one operator and their own projects. They are not yet something to sell.

**What it is silent on.** Every hosted precondition in §5 except the first is
unbuilt, and the first is a quarter done (one rotation of four). Nothing
measured here argues for a public endpoint, and ADR 0216/0217 stand.

**What Stage 5 inherits, in the order the executor would take it.**

1. **The retention plane** (D1886, D1700, D1775). After five sessions beta
   carries 133 workflow runs, 372 steps, 327 attempts, 29 approvals and 9 deliveries, and nothing prunes any of it — a deployment's
   own record grows without bound. It is the first debt because every later
   feature adds to it. One definer function per table under ADR 0213's shape,
   in FK order, with a doctor reading.
2. **The three remaining rotations**, so the rotation trio of claims can move,
   and a rotation schedule rather than an act — the precondition every hosted
   reading starts from.
3. **The shared edge's window** — whether an edge change can avoid taking every
   project away at once (a second Traefik, or a reload rather than a
   recreation), measured against the 24-second reading.
4. **The smaller operating items §10 carries**: the `apg.*` INFO lines that
   never reach `docker logs` (D1918), a `delete_note` RPC so a sentinel can be
   removed without root SQL (D1547), and why a deploy recreates what it does
   (D1581, D1941).
5. **The hosted question as an ADR**, superseding 0042, 0043 and 0044 together,
   taken only when the operator wants a customer — with the walk of the
   documentation, which the operator scheduled for after Stage 5 (D1935), as
   the reading a stranger's experience gives.

**The sentence, if only one is read**: Stage 4 made the appliance a governed
runtime for agents that one operator can run, change and measure safely on a
small host; the numbers say it shares that host well and its edge badly, and
the next stage should make it cheaper to operate before it is offered to
anyone else.

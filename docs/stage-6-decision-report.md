# Stage 6 decision report

Written at Stage 5's close (Session 47, 2026-10-31), **by hand from the sources
each row names**. The Session 47 plan's Run 15 asked for a filling script that
reads every number out of `evidence/session-47.json`, `capacity.ENVELOPE` and
the tree at the tagged commit (the Stage 5 report's method). **There is no
tagged commit and no `evidence/session-47.json`**: the operator closed Stage 5
on 2026-10-31 without the rest of the sitting (§1, §3; Session 47's D3140). So every number below
names its source: a section of `docs/scope-closure.md`, a session plan's
**Done.** paragraph or row, or the sitting's raw notes (WSL
`~/s47/run13/NOTES.md`). §6 alone is the executor's reading, and it is marked
as that.

**The newest merged evidence is still Session 46's**: `evidence/session-46.json`,
**348 claims, 343 passed, 5 failed**, at the tagged 1.24.0 (`55467b5`). Session
47 measured its **offline half only: 175 claims, 175 passed**, at `d076b85`
(Run 12's **Done.**).

---

## 1. What 1.25.0 is

`template_version` 1.25.0, `CURRENT_SESSION` 47 (Run 12, `d076b85`; the
record commit `8e0f3b6` on top). A minor under ADR 0162, priced on the host by
`upgrade.sh plan` before any deploy (Sheet R1): **minor, requires patch,
verdict ok, changes `[image_digest]`** on alpha-dev and beta-dev, and the same
on control-prod once its domain edit was set aside, with **the control set
10 → 11** (migration 0011, the operation step log). Released migrations stay
**39**; requirements **441 → 459**; claims **348 → 366**, **175** declared
offline (Run 12).

What it adds is Session 47's: the console rebuilt for a newcomer (ADRs
0295–0298 — fixed-route modules, a tracker that survives a refresh, a sentence
and a next action for every refusal word, copy controls, Connect snippets that
were executed before they shipped, help, a getting-started checklist), the
operation step log (ADR 0296), and **the move of every customer-facing name to
`nomipg.com`** (ADR 0299).

**Where it stands, said plainly:**

- **Deployed on all five projects** — alpha-dev, beta-dev, control-prod,
  `slot3-prod`, `slot10-prod` — at `8e0f3b6`, whose CI (contract 41067264932,
  site 41071614715) is green. Every customer-facing name answers under
  `nomipg.com` (DM1–DM3); the old zone's apex and `www.` answer 301 and its
  `control.` 308 to the same path (N2), until 2027-10-29 (the plan's §10).
- **Not tagged.** D1425 — deploy, sweep and tag on one commit — is not met,
  because no sweep ran. **No 1.25.0 package exists**: PyPI still serves
  `agentic-postgres-cli` 1.24.0.
- **For a customer**: the console, the API and the database doors they reach
  are 1.25.0 under `nomipg.com`. The CLI they install is 1.24.0. It has no
  default endpoint (D2963), so it works when given
  `--endpoint https://control.nomipg.com/api/v1`. But its package text names
  the old domain, it does not print the snippets' `where` lines (D3030), and
  **a CLI that holds a session at the old endpoint cannot log out** (D3135:
  the 308 is refused by the client, and login refuses while a session is held).
- **For the next session**: the deployed commit is `8e0f3b6`; `main` is past it
  with the close's documents only. The cheapest tag is a sweep of the deployed
  `8e0f3b6` and the tag on it (Session 46 tagged `55467b5` with `main` past it
  the same way). A commit that changes the product needs a redeploy of every
  project before its sweep. Whichever commit is tagged, the release that
  publishes the CLI is the one that makes the package name `nomipg.com`.

## 2. What Stage 5 measured

| Measure | Value | Source |
|---|---|---|
| Claims | 366, 175 declared offline | Session 47 Run 12 **Done.** |
| The newest merged evidence | 348 claims: 343 passed, 5 failed (§3) | `evidence/session-46.json`; scope-closure §39 |
| Session 47's halves | offline 175/175 at `d076b85`; host and external **not run** | Run 12 **Done.**; NOTES, *the operator's decision* |
| Requirements in the registry | 459 (441 at Session 46) | Run 12 **Done.** |
| Architecture decisions | 299; 0246–0299 are Stage 5's | Run 1 **Done.** (0295–0299); the stage plan's Status (294 at Session 46) |
| Divergences measured | D1945–D3141 | the stage plan's Status; Session 47 §1 and NOTES |
| Merged evidence per session | 36: 206/204 · 37: 219/217 · 38: 239/232 · 39: 253/248 · 40: 267/263 · 41: 284/280 · 42: 302/301 · 43: 322/320 · 44: 331/328 · 45: 339/338 · 46: 348/343 (claims / passed) | scope-closure §29–§39 |
| The host | OVH, 6 vCPU, 11,671 MiB, 95 GiB declared, no swap (upgraded 2026-10-18); 9,457 MiB claimable by projects | scope-closure §35 (D2628); NOTES H1 |
| Memory free during the 1.25.0 release | 7,460 MiB available after beta-dev's deploy, 7,446 after alpha-dev's | NOTES R2a, R2b |
| The 1.25.0 release windows (no database restart) | rest never down on any of the four probed; auth 8.5–9.9 s; console 7.3 s | NOTES R2a–R2e |
| Earlier release windows | a new commit recreates auth, mcp and storage ~8–14 s, the same commit nothing (S36); auth 8.2–10.3 s, console 8.0 s, rest never (S45, no restart); rest 4.0–4.7 s when every database restarted for the apt repin (S44) | scope-closure §29, §37; CLAUDE.md MEASURED |
| A project's creation | 1,375.9 s (slot6, `backup` 1,259.1 s of it), 1,565.5 s (the S46 journey), 1,708.4 s (slot9); `backup` is 92 % of a creation while the progress reads 90 | Session 47 §0 and D2995; Run 1 **Done.** (D2989) |
| A branch | create 571.5 s, restore to a point 486.9 s, reset 474.5 s, delete 4.5–7.8 s — each a full physical restore from the parent's repository | D2995 (Session 42's readings); ADR 0271 |
| A `tmp` branch's expiry after `expires_at` | 57.8 s (S40), 125.2 s (S42), 52.3 s (S43), 137.7 s (S44), 253.3 s (S45) — the spread unexplained | scope-closure §33; CLAUDE.md MEASURED |
| Sleep and wake | sleep 19.6 s, wake 20.1 s (S42); wake 17.2 s (S44), 19.2 s (S45) | CLAUDE.md MEASURED |
| Idle sleep | requested 18.7 min after the project went quiet (S41); 1,200.4 s after the setting (S42) | scope-closure §34; CLAUDE.md MEASURED |
| A reboot | every unit back by itself: boot+69 s (S42), +79 (S43), +87 (S44), +97 (S45), +81 (S46, eight units) | CLAUDE.md MEASURED; scope-closure §39 |
| The telemetry plane | charged 3,552 MiB on the host | scope-closure §35 (ADR 0277) |
| The SQL relay | `memory.peak` 35.4 MiB on the host; a cancel in 2.03 s; `SELECT 1` 224 ms against psql's 160 ms (S45) | scope-closure §37; CLAUDE.md MEASURED |
| The browser walk (a driver) | invitation link to a working connection string 26.1 s (S43); at 1.25.0 W0′ 110.8 s, first contentful paint 4,860 / 1,816 / 1,304 ms, the first cold | scope-closure §36; NOTES W0′ |
| The first person's walk | goal 1 reached — account, factor, organisation, a project created in the console, their own application connected — in 30 minutes by their clock; **11 steps no page told them** | scope-closure §39; D2936 |
| The second person's walk | all six goals in 53 minutes on `slot12-prod`, **no undocumented step**, no terminal, no document opened; the creation 23 minutes | their confirmed record, D3141 (§5) |
| The filtered host check at 1.25.0 (V1, `-k`, writes no evidence) | 413 passed, 2 failed, 8 skipped, 64 min 22 s; the failures D1935 (by decision) and the relay-log proof's control (an ordering fact after DM3 recreated the relay) | NOTES V1 |
| The external preflight at 1.25.0 (X0) | 48 passed, 48 skipped (7 for no IPv6 on the host, 41 awaiting the lifecycle and journey records), 305 s | NOTES X0 attempt 2 |
| Slots | 13 declared; `slot1`–`slot9` and `slot11` consumed (one per re-earning or walk); `slot3`, `slot10`, `slot12` allocated (kept); `slot13` declared, never prepared | NOTES A1″ |

## 3. What stayed `failed` or `not_run`, and why

| Claim or item | Status | Why |
|---|---|---|
| `appliance_documented_path` | failed | **By decision** (D1935): the clone walk is deferred; every trip reads it failed. |
| `documented_path` | failed in `session-46.json` | The first person's 11 undocumented steps (D2936). **The second person's confirmed record reads clean** under `apg dx-record check --path hosted` (D3141), but no sweep has run that could read it into evidence. |
| `plans_live`, `journey_live`, `console_create_live` | failed in `session-46.json` | A proof's **order** in the journey mode, not the product (D2940 (3), (4)). The fixes were built at Session 46's close and carried (D2945); the slot that would re-earn them (`slot13-prod`) was never prepared: **the operator closed the stage without PL, J1, J9 or the lifecycle**. |
| **Session 47's live half** | not run | No sweep, no external half, no merge. Its **seven external claims** — among them `domain_live`, `console_reload_live`, `operation_steps_live`, `notifications_started_live`, `console_look_live`, `console_create_reearned_live`, `support_bundle_reearned_live` (D3123, D3124) — have never been executed live. Every earlier live claim was last read at 1.24.0. |
| **The Ledger** | not moved at the close | 44 rows: 25 `beta`, 8 `planned`, 8 `not_offered`, 1 `not_metered`, **2 `trial`** (`projects_self_service` on `console_create_reearned_live`, `support_bundle` on `support_bundle_reearned_live`, both `target_session` 47 since D3123). `plan_free` and `plan_premium` are `beta` naming the failed `plans_live` — the workstation's reading against `session-46.json` fails them by decision (D2945), and a session-01 gate on the workstation fails on that one test (Run 12). D2878 (five `planned` rows at target 38) and D2875 (`support_access`) are unmoved. **The stage closes with two rows `trial`**, against ADR 0261's close rule. |
| **D3138 — the MSS clamp** | in place, unverified across a reboot | A path-MTU black hole: the console timed out for any visitor whose path is below 1,500 bytes and whose router sends no ICMP. The host sysctl could not reach the edge's namespace (`userland-proxy` false), so the fix is a TCPMSS clamp of 1400 on forwarded TCP, installed as `apg-mss-clamp.service`. No reboot has read it back. How long visitors met the fault before 2026-10-31 is not determined. |
| **Bot Fight Mode** on the proxied `nomipg.com` | on, its effect on the proofs unread | It acts on the site, the class of D2728; `site_live` has not run against it. |

## 4. What Stage 5 built against its plan

The stage plan's §3 priced seven sessions; the operator's splits (D2510,
D2591–D2593, D2808–D2811, D2945) made twelve. Each row says what the session
built and how its release stands.

| Session | Built | ADRs | Release, merged evidence |
|---|---|---|---|
| **36** — preconditions | The hosted boundary (0042/0043/0044/0216/0217 superseded), the Reality Ledger, the retention plane; the rotation trio performed on alpha; what a deploy recreates, measured | 0246–0250 | 1.14.0 tagged `2538ac0`; 206/204 |
| **37** — the control plane | `control-prod`, organisations, invitations, TOTP, API keys, `/v1` frozen, the registry; a boot of three projects survives Infisical's rate limit | 0251–0255 | 1.15.0 tagged `c3eec1d`; 219/217 |
| **38** — managed projects, the move | The reconciler, slots, profiles, sleep/wake/export, the creator's handoff by hash, `trial`; the move to OVH and a self-hosted secret store | 0256–0267 | 1.16.0 tagged `efaef09`; 239/232 |
| **39** — public endpoints | TLS Postgres on 5432 routed by name; two customer roles and poolers per project; four drivers verified | 0268–0270 | 1.17.0 tagged `b0249ce`; 253/248 |
| **40** — branches | A branch restored from the parent's repository, re-keyed; expiry; the backups surface; `slot.sh redeploy` | 0271–0273 | 1.18.0 tagged `8cc3440`; 267/263 |
| **41** — plans, usage, idle sleep | Free and Premium, `plan_limit_reached`, usage, notifications, idle sleep; Session 40's two product repairs | 0274–0276 | 1.19.0 tagged `601a0ea`; 284/280 |
| **42** — telemetry, insights | The host upgraded; ClickStack bounded on the host; `pg_stat_statements` and Query Insights; ten monitoring readings | 0277–0279 | 1.20.0 tagged `77303e4`; 302/301 |
| **43** — web-first | The public site on Pages, the invitation as a link, onboarding and TOTP in the browser, the console, the CLI on PyPI | 0280–0284 | 1.21.0 tagged `012ac06`; 322/320 |
| **44** — the SQL editor | The customer's own client in the page through a relay that holds nothing | 0285–0287 | 1.22.0 tagged `224b660`; 331/328 |
| **45** — the visual pass | One look, two self-hosted typefaces; notifications re-earned; an absent request series read with its witnesses | 0288–0289 | 1.23.0 tagged `4f4b207`; 339/338 |
| **46** — the walk, the release | The first person's walk; the console creates a project; the support bundle; `apg control status`; the journey; the old host retired | 0290–0294 | 1.24.0 tagged `55467b5`; 348/343 |
| **47** — the console for a newcomer, `nomipg.com` | The console rebuilt (eleven first-party modules, the tracker, every refusal worded, copy, Connect, help, the checklist, WCAG floors); the step log; the domain move; the second person's walk | 0295–0299 | **1.25.0 deployed, not tagged**; offline 175/175 |

**Cut or `planned`, each with its row** (the stage plan's §6): PostgreSQL 19
(D1947), promotion (D1962) and in-place restore for a customer (D1963),
temporary support grants (D1971), public signup and email (D1951), billing in
any form (D1967), a management SDK (D1952), storage quotas and egress metering
(D1955, D1966), a recommendation engine for Query Insights (D1965), a second
edge (D1975), autoscaling, HA, multi-region and an SLA.

**What the stage taught, in its own sentences** (scope-closure §29–§39): a
customer operation is only as proven as the slowest thing it touches on the
real host; a proof that has never run live carries its author's belief; a
record must be one attempt's; price a deferral by what reads the deferred
thing. Session 47 added two: a value served since Session 39 had never been
true (the psycopg snippet never verified a certificate, D3020), and a site that
answers every test machine can still time out for a stranger (D3138).

## 5. The Stage 6 question, priced against Stage 5's evidence

The vision (`future_stage_specs/agentic-postgres-stage-6-vision.md`, outside
the repository) proposes **Database State & Branching**: about 26 sessions,
depth-first, one VPS, branches, checkpoints, lineage, reset, protection,
promotion, masking, evaluation branches, storage accounting and garbage
collection over a replaceable storage backend. Its §54 asks for Stage 5's
evidence before it is frozen; the review of 2026-10-18 (§4–§5, same folder)
lists what it assumes that does not exist. Each premise, with the reading that
bears on it:

| Premise | Where it stands | The reading that bears on it |
|---|---|---|
| **Branches exist and are cheap enough to deepen** | Built (ADR 0271) as a full physical restore of the parent's repository, its own compose project, database and poolers only; one branch on Free | create 571.5 s, reset 474.5 s (D2995); `tmp` expiry 52–253 s late, unexplained (§2) |
| **A storage substrate for fast branches** | Not chosen. The review read one ext4 disk; copy-on-write needs a second disk or a reinstall (review §4.4, §5.3) | the host declares 95 GiB (D2628); nothing measured on ZFS, btrfs or LVM thin |
| **Promotion, masking, preview environments, hosted Studio** | Promotion cut (D1962); the only masking is on agent tool output; no preview environments; Studio is local only | the review's §4.5: the vision describes them as Stage 5's |
| **A customer can create what Stage 6 branches** | Yes, but only into a **hand-prepared slot**: five DNS records, two R2 buckets with tokens, a B2 bucket and key, a secret-store project with six values — the operator's work each time | ten slots consumed across the stage, one per re-earning or walk (§2); the review's §4.1 |
| **Customers configure the agentic layer** (evaluation branches, branch-aware agent policy) | No: agents, workflows, connectors and migration sets are files the operator deploys; `/v1` has no route for them | the review's §4.2 and §5.2 — a product decision |
| **A hosted migration artefact** (migration rehearsal) | No: customers migrate over the direct door themselves; only the direct door's role may create tables (D3045) | the review's §4.3 |
| **Demand for branches** | Not measured by either walk, which asked for one. The first person's branch was refused by a provisioning defect (D2933); the second person, on a slot made with all five records, made one without help | D2936; D3141 |
| **What newcomers needed** | The console and the documents, not depth | the first person's 11; the operator's verdict (*"looks and feels terrible while using"*, D2936); Session 47 rebuilt the console for them |

**The first person's findings** (Session 46, D2936, summarised; their own files
stay outside the repository). They reached goal 1 and found usage and the
slowest queries. The 11 steps no page told them fall under: the handoff token
and `apg project claim`; no progress while a project was created (one
percentage that sat still, D2949); the creation vanishing from the page after
a refresh; the overview saying there was no project while one was being made;
what notifications are for; how to connect as a newcomer, for their client and
operating system; no copy controls and no busy state on buttons (a second
creation could be started, D2951); and the SQL editor's layout and its state
after connecting. Beside the 11, they found no support page, and their branch
was refused (D2933). Session 47 answered each with a screen (the design
brief's mapping, `docs/design/session-47/`).

**The second person's findings** (Session 47, `slot12-prod`, kept, theirs).

Their confirmed record (`~/s47/person/record.json`, outside the repository;
Session 47's D3141) reads **clean** under `apg dx-record check --path hosted`:
**no undocumented step**, the first walk of either kind that records none. They
reached **all six goals in 53 minutes** -- an account in 2, the factor and an
organisation in 3, the creation pressed at 6 and finished 23 minutes later,
their own note application connected through the pooled and direct strings 37
minutes in, then their own SQL, usage, the support page, a branch and the
slowest queries -- with no terminal and no document opened. In their words,
summarised: every step was described on the page and everything worked in one
go. The longest single wait was the creation (23 minutes, inside the 23-28
minutes measured for the journey); the next, from the project's creation to a
working connection (14 minutes), is their own application's setup and is not
broken down in the notes. **`documented_path` is not moved by this**: no sweep
read the record (D3140); it is the input Stage 6's sweep reads.

## 6. Recommendation

*This section is the executor's reading of §1–§5, written for the operator, who
accepts or rewrites it before Stage 6 is planned (the recommendation is a
decision, and decisions here are the operator's).* **Accepted by the operator,
unchanged, on 2026-10-31** (*"I accept your recommendation for Stage 6"*).

**Open Stage 6 with one session that finishes Stage 5's release, then settle
the review's five decisions, and only then freeze the vision's roadmap — with
the storage substrate measured first and slot preparation priced as part of
it.**

**What the evidence supports.** The hosted product exists end to end on one
host and two people who did not build it have used it: the first reached a
connected application in 30 minutes through 11 undocumented steps; the second,
after the console was rebuilt, created a project and connected their own
application, and the operator relays that everything worked. The stage's
failure mode — a surface claiming more than the node does — was guarded by the
Ledger, whose rows name the claims that make them true; at this close two rows
still name claims that have not passed. What the evidence does **not** support is calling 1.25.0
released: it is deployed and unswept, three claims stay failed by a proof's
order, Session 47's seven live claims have never run, and two Ledger rows
close the stage `trial`.

**What Stage 6's first session owes, before any new feature:**

1. **The three claims re-earned** — `plans_live`, `journey_live`,
   `console_create_live` — on `slot13-prod` under `nomipg.com` in the order
   D2970 fixed: the plan refusal while the slot is ready, the journey with J9
   inside it, the lifecycle in one attempt, detached; Session 47's seven
   external claims read in the same sweep.
2. **A tagged release and the CLI published**, deploy, sweep and tag on one
   commit (D1425) — at the deployed `8e0f3b6` unless a product change lands first — so the package names
   `nomipg.com` and prints its `where` lines; then the Ledger moved from that
   evidence (D2884, D2878, D2875) with no row `trial`.
3. **D3138 read across a reboot**: at B1, `apg-mss-clamp.service` active and
   exactly one TCPMSS line in the mangle table's FORWARD chain, then the console
   read from a sub-1500-byte path.
4. **D3135**: a way for the CLI to move its endpoint, or a logout that follows
   the same control plane's 308 — in that release, since a PyPI version cannot
   be re-uploaded.
5. **D3128** (the operator documents that still name the old zone), **D3125**
   (the two-click reach, the breadcrumb and the switchers, owed tests), D3136
   (walk state naming the old endpoint), and `site_live` read under Bot Fight
   Mode.

**How the vision's priorities rank against the evidence.**

1. **The review's five decisions come first** (§5 there): what a customer's
   "database" is; whether customers manage the agentic layer through `/v1`;
   the branch storage substrate; the vision's account of Stage 5 corrected
   against this report; no billing, and two reference SaaS applications, in or
   out. Each changes the roadmap's shape, and none can be measured away.
2. **The storage substrate, measured early** (the vision's Block I, sessions
   1–4). Today's branch is a full restore taking minutes; every depth the
   vision asks for — trees, checkpoints, reset generations, garbage collection
   — prices differently on copy-on-write, and the host has not been measured
   on any.
3. **Slot preparation automated** is not in the vision and is the cost Stage 5
   paid most often: every re-earning and every walk consumed a slot prepared by
   hand across three providers. A branch-heavy Stage 6 multiplies that unless
   it is priced first.
4. **The vision's branch and recovery core** (its Blocks II–IV) is consistent
   with what Stage 5 built: a branch restored from the parent's repository
   (ADR 0271), and no in-place restore for a customer (D1963).
   **Promotion** re-opens a decision Stage 5 cut (D1962) and should be its own
   ADR, not an inheritance.
5. **Evaluation branches, branch-aware agent policy and migration rehearsal**
   (Block V) wait on decision 2 above: for a hosted customer they have no
   surface today.
6. **The console** stays a priority the walks set, not the vision: Stage 6's
   branch surfaces should meet the bar Session 47 built (the tracker, every
   refusal worded, copy, help), and the second person's findings decide what
   is still owed.

**The sentence, if only one is read**: Stage 5 made a hosted managed-Postgres
product on one host that a stranger can use; Stage 6 should first finish
releasing it, then decide what a customer's database is before it makes that
database's state deep.

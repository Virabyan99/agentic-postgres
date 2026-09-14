# Stage 4 decision report

Written at Session 25 Run 5 (2026-09-14) from three sources: the ledger
([scope-closure.md](scope-closure.md)) re-audited row by row in that run, the
Stage 3 plan's §6 bill against the tree, and the evidence document of the
Stage 3 release. **Every number marked *[filled at the trip's close]* is filled
from `evidence/session-25.json` when Run 8 ends, and not before** (D992's rule,
applied a second time): a decision report written before the evidence is a
plan, and a report whose blanks are quietly filled with the numbers the plan
predicted is worse than a plan.

---

## 1. What 1.6.0 is

`template_version` 1.6.0, `CURRENT_SESSION` 25. The compatibility promise a
`1.x` release makes is the one the product contract has carried since Session
13 (ADR 0162, D991): a minor may add a manifest field, a migration, a contract
entry, a capability or a secret with a migrator or a default, and the
operator's manifests still validate unchanged.

**Session 25 is a minor that adds none of those five.** It adds two operator
commands (`apg completion`, `apg dx-record`), one environment variable the
dispatcher reads (`APG_PROJECT`), and one optional generated document per
project (`projects/<slug>/docs/mcp-tool-catalog.md`, written only when asked
for). No manifest, outputs, capability, lock or secret schema moves, and no
released migration is added — the first release in four sessions of which that
is true. **A project that adopts 1.6.0 and sets no `APG_PROJECT` renders
byte-identical artefacts and deploys the same containers**, and that sentence
is what Run 7's `upgrade plan` on the host is asked to confirm. A `major`
required there is the plan's §9 stop condition.

What 1.6.0 closes is Stage 3, whose six sessions are: 20 the tenant extension
point, 21 the agent plane opened to a tenant's domain, 22 `apg dev`, 23 the
generated client, 24 Studio, 25 the hardening pass and the second walk.

## 2. What was measured

| Measure | Value | Source |
|---|---|---|
| Claims | 126 | `evidence_claims.CLAIMS` (122 at Session 24's close, four added in Session 25) |
| Passed | *[filled at the trip's close]* | `evidence/session-25.json` |
| `not_run` | *[filled at the trip's close]* — the plan predicts **6** with the walk clean and the outsider's document located, **7** with one missing, **8** with both | the same document; §3 says why each |
| Failed | *[filled at the trip's close]* — 0 is the release condition, and **a `failed` `documented_path` is reported as failed** | the same document |
| Requirements in the registry | 219 | 211 P0, 8 P1, 0 P2 |
| Requirements a claim reports on | 195 | 24 belong to no claim (D697), unchanged for the fifth session |
| Migrations released and applied | 32 | fix-forward only; Session 25 adds none |
| Architecture decisions | 207 | 0200–0207 are Stage 3's |
| Divergences measured | D1–D1350 | D1087–D1350 are Stage 3's; D1303–D1350 Session 25's |
| Claims declared offline | 11 | Sessions 22's four, 23's two, 24's two, 25's three (ADR 0202) |
| The second walk's record | *[filled at the trip's close]* — clean, or the list it named | `bin/apg.sh dx-record check` over Run 6's record |
| `upgrade plan` on alpha | *[filled at the trip's close]* — expected `minor` | Run 7's sweep, `test_session25_release.py` |

## 3. What stayed `not_run`, and why

Nine claims were `not_run` at Session 24's close, and this stage's last trip is
where six of them are decided. Each reason below is **as it stands today**; the
trip reduces the list and Run 8 rewrites this section from the document.

| Claim | Why, today |
|---|---|
| `documented_path` | Session 12's, and **ANSWERED for the first time in this stage**. A walk by a reader whose context holds only the release and the task statement (ADR 0207) writes a record; `--dx-record-file` hands it to the sweep. If the record is clean the claim passes; if it is not, the claim is **`failed`** and names the list. `not_run` is no longer an available answer once a record is declared, and the answer is never softened. *[filled at the trip's close]* |
| `fresh_host` | Session 12's, and it needs one file nobody has yet found: a deployed document from a host that started empty. All four archived documents on the workstation name `apg-vps-01`, which `DEP-001` refuses by name. After D1326 it no longer has to be at outputs v18 — the proof reads an archived deployed document by version, three ways, the shape `dr_kit.verify_deployed_document` has used since Session 18. If the operator does not locate one, the claim stays `not_run` with *the operator did not locate the document* as the reason. *[filled at the trip's close]* |
| `honest_readers` | Expected to pass **in both halves for the first time**. D1302 recorded that it could not: `test_render_atomicity.py` carried a bare `skipif(geteuid() == 0)` and the gate runs as root, so the claim skipped on every sweep that could have recorded it. Session 25 Run 3b lifted the fixture, and D1310 is why it cost no second sweep — the repair was shown offline, in a container running as uid 0, which is the identity the gate has. *[filled at the trip's close]* |
| `stage_release` | This session's own host claim, deliberately not declared offline: whether both projects RUN the release the tree names, and what upgrading to it would cost, are facts about a deployment. *[filled at the trip's close]* |
| `bootstrap_identity`, `api_authorization`, `credential_rotation_planes` | D860. The blocker was removed in Session 15 (ADR 0170 retired the bootstrap issuer's key and the slot has been free since); what is missing is a **rotation performed**, which is an operator sequence with an irreversible `promote` and not a run's action. Offered again on Run 7's sheet as an optional, separately numbered block. If declined, the ledger's §2 records the date, and it is the first item on Stage 4's bill. |
| `replacement_host_restore` | `not_run` **by decision** (D1028): a rehearsal ends at the restore. Nothing about Stage 3 changes that, and it is listed so it is not read as a gap. |
| the five D478 names | `port_allocation`, `deployment_convergence` and the rest, each awaiting an event rather than a run. Unchanged. |

## 4. The three blockers Stage 3 was given, and what became of each

The Stage 3 plan's §6 named three things standing between the artefact and a
hosted reading. **Two are removed, with claim ids**, and the third is priced
here against the tree rather than described.

| Blocker | Position | What proves it |
|---|---|---|
| **A tenant has no schema of its own** | **Removed, Session 20** (ADR 0198, ADR 0199). A project owns `projects/<slug>/`: its own migration set, applied by the role that will apply it, in its own ordering space with its own migrations table since ADR 0206. | `tenant_extension_point`, `task_domain` |
| **An agent cannot address a tenant's domain** | **Removed, Session 21** (ADR 0200, ADR 0201). The scope vocabulary is derived from the reviewed surface, the runtime registers its roster from the compiled lock, and a project's own capability manifest is joined into that lock. | `agent_tenant_surface`, `agent_tenant_read`, `agent_scaffold`, `agent_lock_reported` |
| **There is no public endpoint a customer could be given** | **Not removed, and not attempted.** `runtime_override.publication()` still raises: the seam exists and refuses, which is the honest state of a decision nobody has taken (D1084). | — |

**What the third costs, against the tree.** The stage plan priced it as a
decision before it is an implementation, and the tree agrees. The bill, in the
order the work would have to be done:

1. **The rotation performed** (D860). A credential that travels rotates first,
   and this one has never rotated because it has never travelled. An operator
   sequence with an irreversible `promote`; three claims move with it.
2. **A retention policy for `agent_audit` and `agent_idempotency`** (D1255).
   Nothing prunes either. A hosted reading makes both a customer's data and
   makes the growth somebody else's problem; the policy is a released migration
   carrying a decision about how long a denial must remain readable.
3. **The audit endpoint's filters** (D1248). A window, an outcome/boundary
   filter and a cursor — one migration over 0032's reader plus one endpoint
   change. Priced in Session 24 §10 and not built.
4. **Tenancy across customers**, which the product contract's §5 lists as a
   non-goal. Changing that is an ADR before it is a line of code.
5. **A registry that is authoritative rather than an operator's read** (ADR
   0185 drew that line deliberately).

The first three are owed whatever the answer to the fourth is, which is why
they are numbered before it.

## 5. What the DX layer's evidence says about the hosted question

Stage 3's four DX sessions each shipped a surface a developer runs on their own
machine, and each closed on claims a checkout can answer. What follows is one
paragraph per surface: what its claims prove holds under a hosted reading, and
what they do not.

**`apg dev` (Session 22, ADR 0203).** `dev_environment`, `dev_isolation` and
`dev_churn` prove the local cluster is built from the render and the release —
the same locked image, the same migrations, applied by the role that will apply
them on a deployment — and that it holds no production secret and reaches no
deployment. Under a hosted reading that is the property that matters: a
developer's machine is not a tenant of anything, and nothing about `apg dev`
would have to change if the deployment were somebody else's. What it does not
say is anything about a shared cluster, a quota, or a developer's environment
costing a hosted operator money.

**`apg generate` (Session 23, ADR 0204).** `generated_client`,
`generated_client_toolchain` and `generated_client_hash` prove the emitted
package is a claim about the surface it was generated from, checked by `init()`
against the document the deployment actually serves, **as the caller** — which
is the sentence that carries under hosting, because PostgREST serves a
different document to every role and a hosted product's callers are more
various, not less. What they do not say is anything about distributing a client
to somebody who is not the project's owner.

**`apg studio` (Session 24, ADR 0205).** `studio_boundary`, `studio_surface`,
`studio_revocation` and `audit_boundary_reported` prove the page is a client and
nothing more: one loopback process holding the human's token in memory, a
browser holding a launch cookie and never the token, an enumerated forwarder
table, no SQL box hidden or otherwise, and no third-party code. **The DX layer
holds nothing the human does not hold** — the stage plan's §8 invariant — and
`SEC-DX-001`'s matrix now names a collectible proof for that invariant on each
of the three surfaces rather than asserting it. Under a hosted reading this is
the load-bearing one: a page that held authority the human did not would become
an authority the moment the human was a customer. What it does not say is
anything about multi-tenancy, billing, accounts, or a port anybody but the human
at that machine can reach.

**Across all three**, the evidence is silent on exactly the questions §4's
blocker three asks, and that silence is deliberate rather than an omission: no
proof in this repository claims a property about a customer, because there is no
customer in the model.

## 6. Recommendation

*Written at the close from `evidence/session-25.json`.*

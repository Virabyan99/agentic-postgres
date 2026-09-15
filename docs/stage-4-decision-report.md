# Stage 4 decision report

Written at Session 25 Run 5 (2026-09-14) from three sources: the ledger
([scope-closure.md](scope-closure.md)) re-audited row by row in that run, the
Stage 3 plan's §6 bill against the tree, and the evidence document of the
Stage 3 release. **Filled at Run 8's close (2026-09-15) from `evidence/session-25.json` and
nothing else** (D992's rule, applied a second time): a decision report written
before the evidence is a plan, and a report whose blanks are quietly filled
with the numbers the plan predicted is worse than a plan. The filling script
reads each number out of the document and asserts it, so a placeholder cannot
be completed from memory.

**The document says: 126 claims, 119 passed, 1 failed,
6 not_run**, at `source_commit de2aabffcf9d`
with the offline half measured at `13c4b390111e`.

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
| Passed | **119** | `evidence/session-25.json` |
| `not_run` | **6** — the plan predicted 6 with the walk clean and the document located. The document WAS located and the walk was NOT clean, so the arithmetic landed on 6 by a different route: `fresh_host` passed, and `documented_path` is a `failed` rather than a seventh `not_run` | the same document; §3 says why each |
| Failed | **1: `documented_path`** — 0 was written here as the release condition and that was wrong; see §6. It is reported as failed, not softened, and it is **the first `failed` claim in this project's twenty-five sessions** (D1373) | the same document |
| Requirements in the registry | 219 | 211 P0, 8 P1, 0 P2 |
| Requirements a claim reports on | 195 | 24 belong to no claim (D697), unchanged for the fifth session |
| Migrations released and applied | 32 | fix-forward only; Session 25 adds none |
| Architecture decisions | 207 | 0200–0207 are Stage 3's |
| Divergences measured | D1–D1377 | D1087–D1377 are Stage 3's; D1303–D1377 Session 25's, of which D1351–D1377 are the two walks, the trip and their repairs |
| Claims declared offline | 11 | Sessions 22's four, 23's two, 24's two, 25's three (ADR 0202) |
| The second walk's record | **not clean: eleven undocumented steps**, `reached_success_criterion: false`, on release `a4b9685`, slug `reading-room`. Four of five readings clean; the gate green on the walker's own tree | `bin/apg.sh dx-record check` over Run 6's record |
| `upgrade plan` on alpha | **`minor`**, `requires patch`, `verdict ok`, `reasons []`, **one leaf differing** (`template_version`) — the same on beta. Read at the sheet's step before the deploy; after it, the planner correctly reports nothing left to do (D1372) | the operator's sheet, Run 7 |

## 3. What stayed `not_run`, and why

Nine claims were `not_run` at Session 24's close. The trip decided four of
them and left **6**, with one claim moving to `failed` rather than to
`passed`. This section is rewritten from the document.

| Claim | Why, today |
|---|---|
| `documented_path` | **FAILED**, and that is the answer rather than the absence of one. Two walks were run (ADR 0207 allows two). The first, on `040f733`, recorded six undocumented steps and found that two of the adopter's seven goals are unreachable offline (D1357). The second, on the repaired `a4b9685`, recorded **eleven** — two of them against the first repair's own prose, and one a product defect the repaired page walked the reader into (D1359). Both records were handed to the sweep; the second is the one the claim reports. **It is the first `failed` claim this project has ever written**, and producing it required repairing the gate, which could not emit the status at all (D1373). |
| `fresh_host` | **PASSED**, `not_run` since Session 12. The document was found on the outsider's own appliance — a Hetzner host that started empty, brought up 2026-09-08 by a reader who had not seen this codebase — inside the DR kit that bring-up exported (D1370). `document_kind: deployed`, outputs **v16**, `host.id` `apg-snippets-01`, independent of `project_a`'s host by construction rather than by argument. **D1326 is what made it readable**: at v16 it sits exactly on `KIT_FIRST_OUTPUTS_VERSION`, and before that row it would have been refused by version with the file sitting on a host nobody had looked at. |
| `honest_readers` | **PASSED**, in both halves, for the first time. D1302 recorded that it could not; Run 3b lifted the fixture both modules now import, and D1310 is why it cost no second sweep — the repair was shown offline in a container running as uid 0, the identity the gate has. |
| `stage_release` | **PASSED**, on the second sweep. Both of its live proofs were red on the first: one rendered its candidate from the reviewed set rather than from the operator's manifest (D1371), and one asked for a reading that is only true before the deploy the sweep runs after (D1372). Both were written in Run 5 and first executed on the host — §7's second question, answered the expensive way. |
| `bootstrap_identity`, `api_authorization`, `credential_rotation_planes` | **`not_run`. The rotation was offered on Run 7's sheet and DECLINED on 2026-09-15**, recorded as declined and never as failed. D860's blocker was removed in Session 15; what is still missing is a rotation *performed*, an operator sequence with an irreversible `promote`. **It is the first item on Stage 4's bill**, and the argument for taking it there rather than here is that a credential path built, tested offline and never exercised deserves its own session with its own rehearsal — not the last slot of a release day. |
| `replacement_host_restore` | `not_run` **by decision** (D1028): a rehearsal ends at the restore. Nothing about Stage 3 changes that, and it is listed so it is not read as a gap. |
| `port_allocation`, `deployment_convergence` | **`not_run`**, each awaiting an event rather than a run: `deployment_convergence` needs a redeploy declared with `--redeploy-before-file`, which this trip did not perform. Unchanged, and named so they are not read as gaps. |

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

**Stage 4 is justified on this evidence, and the release condition this document
was written with is the thing to change first.**

§2 said *0 failed is the release condition*. That was written in Run 5, before
the trip, and it is wrong in a way worth keeping on the page rather than
editing out. `1.6.0` ships with **one failed claim**, and the failure is the
most useful measurement Stage 3 produced: `documented_path` is `failed` because
two readers who had never seen this repository followed its documentation and
recorded seventeen things it did not tell them between them. A release
condition of *0 failed* would have been met by never declaring a record at all
— which is exactly what the previous twelve sessions did, and why the status
had never been emitted. **The condition should be that every claim is
answered, and that a failed one is reported as failed.** On that condition this
release passes: 126 claims, 119 passed, 1 failed, 6 `not_run`, and every one of
the six has a reason that names an event rather than an omission.

**What this document supports.** Stage 4's case rests on the artefact being
adoptable, recoverable and inspectable by someone who did not build it. Three
of those are now measured rather than asserted: `fresh_host` passed on a
deployment a stranger built on an empty host (§3), the DR kit exported at this
release verifies off-host as well as on it, and the agent plane, the generated
client and Studio each carry live claims that passed on two projects. The
walks are what make the first of those trustworthy — not because they
succeeded, but because they did not, and the record says so with node ids.

**What it is silent on.** Everything §5 lists, and the silence is deliberate:
no proof here claims a property about a customer, because there is no customer
in the model. **The public-endpoint decision (D1084) is Stage 4's first ADR and
is not a consequence of any number in this document.** Nothing measured in
Stage 3 argues for or against it; a reader looking for support here for a
hosted product will find an appliance that one operator runs well, and that is
a different claim.

**Three things Stage 4 inherits, in the order they should be taken.**

1. **The rotation** (D860, §3). Declined at four trips now, most recently
   2026-09-15. It is a credential path that has been built, tested offline and
   **never performed on a deployment**, which is the class §7 of `CLAUDE.md`
   says this project keeps producing. It should be the first act, with its own
   rehearsal, not an appendix to a release day.
2. **A walk of this release's documentation, before anything is added to it.**
   Session 25 repaired seventeen documentation findings and **nine of them were
   repaired after the last cold reader had gone** — measured by proofs where
   they were product defects, and by the judgement of the session that wrote
   them where they were prose. That is the weaker half of this document's
   adoptability case and it is named here rather than left to be discovered.
3. **The Docker question on the host** (D1375). Session 25 is the first release
   whose offline mode requires a daemon, and the host's `op` cannot reach one.
   Either the host gains a way to run that mode or the mode stops being
   something a host is asked to run. It should not be settled by adding a group
   membership in a hurry.

**The sentence, if only one is read**: the Stage 3 artefact does what it says
on a deployment, and the one thing it does not do — hand a stranger a
documented path they can follow without finding gaps — is now measured, named
and failing, which is a better position to start Stage 4 from than a green
document that had never asked.

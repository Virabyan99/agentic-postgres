# Stage 3 decision report

Written at Session 18 Run 5 (2026-09-06) from three sources: the evidence
document of the Stage 2 release candidate, the ledger
([scope-closure.md](scope-closure.md)), and the Stage 3 consolidated
specification's premises checked against the tree on 2026-09-05 (D992). Every
number marked **[filled at the trip's close]** is filled from
`evidence/session-18.json` when Run 6 ends, and not before: a decision report
written before the evidence is a plan.

---

## 1. What 1.0.0 is

`template_version` 1.0.0, `CURRENT_SESSION` 18. The compatibility promise a
major version makes is the one the product contract has carried since Session
13 (ADR 0162, D991): a `1.x` release may add a manifest field, a migration, a
contract entry, a capability or a secret with a migrator or a default, and the
operator's manifests still validate unchanged; the next change that removes or
retypes any of the five, or that an operator must act on before an upgrade,
needs `2.0`. Session 18 itself bumped the project manifest to schema 4 and
the outputs document to v16, both additive with migrators, inside the major.

## 2. What was measured

| Measure | Value | Source |
|---|---|---|
| Claims | 101 | `evidence_claims.CLAIMS` (97 at Session 17's close, four added in Session 18) |
| Passed | **93** (2026-09-06, deployed release 054f54e) | `evidence/session-18.json` |
| `not_run` | **8** | the same document; §3 says why each |
| Failed | **0** | 0 is the release condition |
| Requirements in the registry | 171 | 163 P0, 8 P1, 0 P2 |
| Requirements a claim reports on | 147 | 24 belong to no claim (D697, unchanged) |
| Migrations released and applied | 30 | fix-forward only |
| Architecture decisions | 194 | 0188–0194 are Session 18's |
| Divergences measured | D1–D1032 | D984–D1032 are Session 18's; D1023–D1032 the trip's |
| Restore from the mirror alone | 151 s in rig 18 (D1002); **247 s on the replacement** (237 s restore of the 03:43 incremental plus WAL to 06:43 UTC, 9 s recovery), the original identity on timeline 2 | the restore record; D593: a sample from a band, `process-max` 1 |
| Rehearsal readings on the production host | **eight**, every one read or recorded and reversed, in two minutes | the rehearsal records |

## 3. What stayed `not_run`, and why

Seven claims were `not_run` at Session 17's close. Two are what Session 18
arranges: `fresh_host` (a deployed document from a host that started empty,
the replacement) and `documented_path` (a record from a person who did not
build this, the outsider's afternoon). **Neither closed.** No outsider was
available, and deploying a new project on a host to be deleted the same day,
with two buckets, two tokens and a DNS record made to be deleted, was judged
scaffolding by the operator; both stay `not_run` for the want they had before.
The eighth is `replacement_host_restore`, `not_run` by decision: a rehearsal
ends at the restore, because adoption cannot give the restored copy a
backup credential of its own (D1028); its identity half is in the restore
record. Five are untouched by design and stay: `api_authorization`
and `bootstrap_identity` need a rotation performed, `credential_rotation_planes`
the same, `deployment_convergence` a redeploy window declared, and
`port_allocation` a witness of the allocation on a fresh host. None is a
defect in the artefact; each is an operator event nobody has arranged, and the
ledger's §2 prices each.

## 4. The Stage 3 specification's premises, against the tree

Checked on 2026-09-05 (D990, D992), each one a sentence:

| Premise | Holds? | What the tree says |
|---|---|---|
| There is a coordinator whose loss is rehearsed | **No** | The word occurs in the stage plan only, where a coordinator is declared non-authoritative. The nearest real dependency is the secret provider, whose loss a deploy feels at step 5 and nothing running feels at all (D976, D990). |
| Stage 2 is Sessions 13–24 | **No** | Stage 2 is Sessions 13–18; the stage plan's audit folded the rest (D704–D718). |
| A PostgreSQL 19 baseline | **No** | The tree runs PostgreSQL 18.4 pinned by digest in `versions.env`; no proof reads a 19-only feature. |
| `apg dev` replicates from a database with no public port | **Not built, and the premise is sound** | Both transports are host-loopback by decision (ADR 0042); a replica would reach the direct transport over the same SSH forward `connect.sh` opens. Nothing replicates today. |
| Recovery is restore-based with a real RTO | **Yes** | A restore from the mirror alone is 151 s in the rig; the replacement's figure is the trip's. There is no failover and none is claimed. |
| Detection precedes automation | **Yes** | Eight rehearsals read readers that exist; none induces a failover (ADR 0190). |

## 5. Template, or control plane?

The ledger's §6 records the question and does not resolve it. This report
answers it as a recommendation, from what the evidence shows rather than
from the stated direction.

**What the artefact is today**: one deployment per project on an owned host,
with the isolation measured over 179 leaves, a rehearsed restore, a documented
path whose commands resolve, and -- since Session 18 -- a second copy of every
backup at a second provider, a kit that rebuilds a host without a secret
value, and a rehearsal verb over the failures the readers can name. Every one
of those is a property of a **template**: it is proved by deploying the thing
again, elsewhere, from documents.

**What a control plane would need that nothing here has**: a coordinator
(there is none, §4), tenancy across customers (the product contract's §5 lists
it as a non-goal), a registry that is authoritative rather than an operator's
read (ADR 0185 drew that line deliberately), and a failover the readers could
automate (ADR 0190 refuses to claim one).

**Recommendation.** Ship 1.0.0 as the template it is, and put the control-plane
question to a Stage 3 specification that starts from §4's premises corrected --
no coordinator, no PostgreSQL 19, no public port -- rather than from the
current specification's. The one property that survives either answer is
`documented_path`'s (ledger §6): a deployment that needs nothing living in one
person's head. Under the hosted reading it matters more, not less, and the
trip's outsider is the cheapest measurement of it there is. **The afternoon
did not happen**; what it exists to find was found anyway, by the operator
walking the runbook and the README on the replacement: three documented
lines that do not work as written (D1023, D1024, D1025) and two commands
that had never executed live (D1026, D1027). An insider found five; an
outsider would find more.

## 6. What this report does not decide

It does not tune `process-max` (D593), does not choose a retention for the
agent audit (undecided, ledger §5), does not add a second version axis (D704),
and does not read a green checkout as a working deployment: every number in §2
comes from `evidence/session-18.json` or says it is not yet there.

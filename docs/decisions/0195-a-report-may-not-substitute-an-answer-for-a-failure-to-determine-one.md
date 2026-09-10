# 0195 — A report may not substitute an answer for a failure to determine one

- **Status:** accepted
- **Date:** 2026-09-10
- **Session:** 19, Run 2 (D1042, D1048, D1050, D1052, D1053)
- **Related:** **D600** (a `null` that looks measured is worse than an absent
  field), **D145/D548** (`postgrest --ready` returns 0 while every request
  404s; `pgbackrest info` exits 0 for a missing stanza), **D701** (a status
  computed twice is wrong the second time), **D941** (read the cluster, never
  the migrator's summary line), **ADR 0158** (the deployed document is the
  address book, not the diagnosis).

## Context

An outsider brought this product up on an empty host and recorded twenty-five
findings. Six of them are one defect wearing different clothes: **a check whose
failure path returns one of the answers it was supposed to choose between.**

| Check | What it said when it failed | What was true |
|---|---|---|
| is a rollback timer armed? | "no rollback timer is armed" | one was, with nine minutes left |
| which ACME environment? | `staging` | production, with a trusted certificate |
| is this a DR kit? | "this is not a kit" | it was, and verified under `sudo` |
| did the migration apply? | exit 0, "ledger recorded" | nothing was applied |
| is the REST route up? | `unavailable` | serving, and correctly refusing anonymously |
| was the hashing permit released early? | "the permit was released" | the hash had simply finished |

`except OSError: return "staging"`. `grep -q` losing a SIGPIPE race and reading
as false. A count printed from the set that was not applied. In each case the
operator was not told *"I could not determine this"* — they were told something
definite and wrong, and the definite wrong answer was always the one that looks
routine.

Three of the six were dangerous rather than annoying. The interlock guarded the
only two steps that can lock an operator out of the host. The ACME answer
invites a second promotion, which spends a rate limit that takes seven days to
return. The migration one let an operator believe a release shipped when it had
not.

This is not a new observation for this project. D600 already says a `null` that
looks measured is worse than an absent field, and the ledger's §7 has carried
the pattern since Session 5. It kept being recorded per-instance and repaired
per-instance, and the class went on producing new members.

## Decision

**A reader has three outcomes, not two: the answer, the other answer, and *I
could not determine it*. The third is reported and never folded into one of the
first two.**

With one distinction, which is the part that makes the rule usable:

- **A decision may fail closed.** A deploy asking "has this host been promoted
  to production ACME?" is entitled to treat an unreadable store as *not
  promoted*: the consequence of guessing wrong in the other direction is worse,
  and the caller acts rather than reports. `acme_environment()` keeps that
  behaviour and its docstring now says that is what it is for.
- **A report may not.** `edge.sh status` exists to tell a human what is
  observed. For that caller, "I could not read the ACME store" and "you are on
  staging" are different facts and only one of them is true. Reports call a
  separate reader, `observe_acme_environment()`, which returns `None` when it
  could not determine the answer, and the surface prints `unknown` with the
  reason.

Where a value is constrained by a published schema — `routes.*.status` and
`tls.acme_environment` are both enums in `outputs.schema.json` — the document
keeps its vocabulary and the **printed** surface carries the distinction. A
third enum member is an outputs schema version with a migrator and a guarded
reader for every consumer (D600), which is a decision of its own and not a word
change.

The voice to copy is already in the tree, in `bin/backup.sh`:

> "pgBackRest did not answer within 300s. That bound is chosen rather than
> measured — nothing here has ever timed a full backup against R2 — and a
> backup may still be running inside the container."

It reports that it did not get an answer, admits its threshold is arbitrary,
says why, and warns that work may still be in flight. Nothing is claimed that
was not observed.

## Consequences

- `edge.sh status` can report `production`, which it could not do on any host at
  any time before this. The function's own docstring already described that
  symptom arriving through a different path — a literal `"staging"` written into
  `observe_tls` — which had been repaired once; the permission path reintroduced
  it. Fixing one reader of a rule and not the others is question 5 of the defect
  pattern, and this ADR is the answer to it for this class.
- `dr-kit verify` distinguishes an unreadable kit from an invalid one, and the
  export writes the kit owned by the operator it instructs to copy it away.
- Two guards enforce the class rather than the instances: no command in
  `bin/provision-host.sh` is piped into `grep -q` under `pipefail`, and
  `edge_state` carries both readers with the reporting one able to answer
  `None`.
- The rule is not "never fail closed". A deploy that refuses on an unreadable
  input is behaving correctly, and this ADR would be misread if it produced a
  round of changes making decisions optimistic.
- `routes.*.status` keeps `unavailable` for a route that was merely unobserved.
  That is recorded as **D1048** and left for the session that next versions the
  outputs document; the deploy's printed summary now says which of the two it
  means.

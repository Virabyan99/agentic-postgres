# 0250 — A secret's age is the provider's update time, read, never acted on

- **Status:** Accepted
- **Date:** 2026-10-03
- **Session:** 36, Run 6 (D1997, D2019, D2022, D2023)
- **Affects:** `OPS-ROTATE-001`, `OPS-ROTATE-002` (registered by Run 8).
  `schemas/secret-contract.schema.json` (`max_age_days`), `secrets.required.yaml`,
  `src/agentic_postgres/infisical_client.py` (`read_secret_times`,
  `SecretTimes`), `src/agentic_postgres/secret_age.py`,
  `src/agentic_postgres/diagnosis.py` (`secret_age_report`), `bin/doctor.py`
  and `bin/doctor.sh` (`secrets`), `tests/contract/test_secret_age.py`.
- **Related:** ADR 0088 and 0174 (the rotation procedures), ADR 0159 (no third
  party's bytes in the doctor's output), ADR 0195 (three outcomes), ADR 0213
  and 0221 (a reading takes no threshold it invented), ADR 0224 (the signing
  key's rotation).

## Context

The Stage 5 plan (D1974) asks for a rotation *schedule*: each declared secret
gets a `max_age_days`, and the doctor reads each secret's age. A schedule needs
an age, and **no per-secret time existed anywhere in this product** (D1997): a
generation id is random, a generation's manifest carries one
`materialized_at` for the whole set, and every deploy materializes a new
generation with identical values — so the age of a generation is the age of
the last deploy, not of any value.

Sheet E0 found that the provider's response to the read the materializer
already makes carries `secret.version`, `secret.createdAt` and
`secret.updatedAt` (D2019). Run 6 then read them, never a value, for all 22
declared secrets on both projects (D2022, `~/s36/s36-r6.txt`):

- the four secrets with **known** rotations read `version` = 1 + their rotation
  count and `updatedAt` = the last rotation: the auth signing key on both
  projects (`2`, 2026-09-19, ADR 0224); alpha's documentation password and
  PostgREST authenticator (`3`, 2026-08-28 — rotated 2026-08-13 and again in
  Session 11's window);
- **the control**: the 37 secrets never rotated read `version` 1 with
  `updatedAt` equal to `createdAt`, on both projects;
- three reads answered 404 — the prepared signing key, which exists only during
  a rotation, on both projects, and alpha's `connector_signing_key`, a facility
  alpha does not have.

So `updatedAt` moves with each value replacement and with nothing that happened
to the other 37. **What was not measured** is whether an edit that is not a
value replacement — a comment, a tag, a reminder set in the provider's console
— also moves it. Nothing in this product makes such an edit; a person in the
provider's console could. If it does, the reading reports a value YOUNGER than
it is. The day-2 rotation X2 is the next measurement: `updatedAt` must move
and `version` increment.

## Decision

**A secret may declare `max_age_days` (1–3650) in `secrets.required.yaml`;
absent means no reading, not an unlimited age.** It is declared for the three
credentials the rotation trio proves — `postgrest_authenticator_password`,
`docs_basic_auth_password`, `app_runtime_password` — at 90 days, and for
nothing else yet. Which secrets a schedule should cover beyond those is the
operator's to decide, one declaration at a time.

**`sudo bin/doctor.sh secrets --project KEY` reads, for each declaring secret
the project holds, the provider's `updatedAt`**, through
`InfisicalClient.read_secret_times` — the same GET `read_secret` makes, with the
response reduced inside the function to `version`, `createdAt` and `updatedAt`.
**It returns no value**; it is a separate function, not a flag on
`read_secret`, so no call site can ask for the value and the time together.

**Three outcomes, each with its reason** (ADR 0195): `ok`; `overdue` — more
days than declared since the last replacement, a **WARN** that exits 0;
`unknown` — no time, an unparseable one, one without a timezone, one in the
future (beyond 5 minutes of clock skew), a 404 (*"the provider holds no such
secret"*), a status, an unreachable provider, a failed login, no host manifest
or no bootstrap state — exit 6. Only the provider's STATUS reaches a reason,
never its message, and the update time is re-rendered from the parsed value
rather than printed as the provider sent it (ADR 0159).

**A reading, never an act.** Nothing rotates a secret because it is old; an
`overdue` is a sentence an operator reads, and the rotation remains the
operator's procedure (operator guide §9, §15).

**The doctor now holds secret material in one reading** (D2023). Its help said
it *"never reads a secret"* and *"reads no secret material"*. The `secrets`
reading logs in to the provider with the project's runtime credential — the
root-only files `materialize-secrets` reads — so the sentences now say what is
true: the doctor never reads a secret VALUE; one reading holds a credential,
and every other mode holds none.

## Alternatives rejected

**Record each secret's time in the generation manifest at materialization.**
That would read the age of the value the running containers hold rather than
the provider's newest — arguably the better question — but it changes the
deploy path and the generation schema for a reading, and a deploy that
materializes identical values would need the provider's time anyway. Kept as
the shape a later session can take if the two ever disagree.

**A separate command instead of a doctor reading.** Rejected: the doctor is
where an operator reads a project's state, it already has the verdicts and the
renderings, and a fourth reading is cheaper to find than a new command. The
cost — the doctor holding a credential in one mode — is stated, not hidden.

**`overdue` as a PROBLEM.** Rejected: a slipped schedule is not an unwell
deployment, and a PROBLEM exits 6 — a reading that failed a host that works
(ADR 0213's lesson).

## Consequences

**Makes easy:** a schedule is a declaration in the contract and a reading the
operator runs; the rotation trio's three credentials carry one from today.

**Makes hard:** the reading is only as true as the provider's `updatedAt`; a
non-value edit in the provider's console may make a value read younger than it
is, until X2 or a later measurement says otherwise.

**Enforced by:** `tests/contract/test_secret_age.py` (a planted value and a
planted client secret absent from every return and every rendering; the three
outcomes; the bounds), and on the host the live proof
`test_every_declared_secret_age_is_read` (Run 8 registers it).

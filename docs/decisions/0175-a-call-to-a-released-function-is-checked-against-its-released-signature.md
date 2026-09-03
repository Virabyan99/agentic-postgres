# 0175 — A call to a released function is checked against its released signature

- **Status:** accepted
- **Date:** 2026-09-03
- **Session:** 15, Run 8 (D857–D859)
- **Related:** **D857** (the four stale call sites), **§7 question 5** (a decision
  moves, its writer moves, one reader does not), **D697** and **D687** (the same
  shape, guarded as a class rather than per instance), **D464** (a text scan
  standing in for a construct, and why this one narrows its claim instead of
  keeping an exception list), ADR 0172 (the parameter this run's defect came
  from).

## Context

Run 4 added `p_expires_at` to `app_private.auth_create_agent` with no `DEFAULT`,
so the six-argument form stopped resolving. The product got the change:
`repository.py:create_agent` passes seven placeholders, and `POST /admin/agents`
works on the deployment. **Four proof call sites did not** — three fixtures in
`tests/deployment/` and one in `conftest.py`, each calling the SQL function
directly and deliberately, so that a proof about the agent plane is not
conditional on the endpoint that makes agents.

The result was 21 errors and one skip in the Session 15 host gate, after 13
minutes of host time, in a suite that had been green offline throughout Runs
4–7. **Nothing offline could have caught it**: those fixtures only execute
against a live host, and their failure was inside a fixture body rather than in
its graph, so `--setup-plan` — the cheap half of the never-executed-proof
problem — would have resolved them without complaint.

This is question 5, which §7 already names as the one this project answers wrong
most often. It is now the ninth instance.

## Decision

**A contract test checks every call to a released `app_private` function against
the arity that function's migrations declare.**

The claim is deliberately narrow, and the narrowness is the design:

- It reads **arity only**, not types. Types would need a resolver for
  PostgreSQL's overload rules and would fail on `unknown` literals — exactly the
  `HINT: You might need to add explicit type casts` the deployment produced.
  Arity is what the four defects had wrong, and it is decidable from the text.
- It asks only about functions **the migrations actually declare**. A test that
  creates its own `pre_request` or `writes_a_row`, and the bootstrap plane's
  `project_identity`, are outside the claim rather than inside an exception
  list. This removed four would-be exceptions at a stroke.
- It scans **`tests/`, `bin/`, `services/` and `src/`**, so the product and its
  proofs are held to the same statement. A guard watching only the tests would
  have covered half this class.

## Alternatives

**Make the deployment fixtures call `POST /admin/agents` instead of the SQL
function.** Rejected, and the fixtures' own docstrings say why: the endpoint is
sometimes the subject under test, and a proof about the agent plane that depends
on the endpoint that makes agents cannot distinguish a broken plane from a
broken creation path.

**Give `p_expires_at` a `DEFAULT NULL`** so the six-argument form keeps
resolving. Rejected: an expiry that defaults silently is a credential with a
lifetime nobody chose, and the column carries no `DEFAULT` for the same reason
(ADR 0172). Making every caller state it is the safer contract; what was missing
was a way to find the callers, which is what this ADR adds.

**Accept that host-only proofs break on the host.** This is the status quo and
it costs a trip each time. The defect was detectable in a checkout the whole
time — the information was in the migrations and in the call sites, and nothing
compared them.

## Consequences

- A stale call site fails in a checkout, in seconds, instead of on the host
  after a deploy.
- One exemption exists and is named in the test:
  `test_storage_plane.py`'s deliberate call to the retired three-argument
  `storage_claim_cleanup_batch`, whose subject *is* a retired signature. A guard
  that refused it would be refusing the proof that the retirement worked.
- **It is still a text scan standing in for a construct** (D464), and the honest
  statement of its limit is that it counts arguments rather than resolving a
  call. Two mutations were run to establish it fires — one on a fixture and one
  on the product — with a control the guard cannot reach, which stayed green.
- It does not know about types, defaults, or `OUT` parameters, and a change to
  any of those passes it. The next defect in this family will be one of those.

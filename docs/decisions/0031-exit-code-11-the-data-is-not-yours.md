# 0031 — Exit code 11: the data is not yours

- **Status:** Accepted
- **Date:** 2026-08-07
- **Session:** 3
- **Affects:** DX-002, DBX-PG-003

## Context

The Session 3 runbook proposes replacing the exit-code convention with ranges:
`10–19` config, `20–29` secrets, `30–39` readiness, `40–49` identity, `50–59`
bootstrap, `60–69` migration, `70–79` security, `80–89` evidence.

What exists is a frozen single-value convention, asserted by
`tests/contract/test_cli_contract.py` and documented in
`docs/session-02-operator-guide.md`:

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Invalid operator input or manifest |
| `3` | Missing prerequisite, or not root |
| `4` | Missing runtime state — the project was never deployed here |
| `5` | Contract, lock, collision, or generated-output validation failure |
| `6` | A host or gate check failed |
| `7` | The provider rejected an operation, or state disagrees with it |
| `8` | A secret could not be fetched or written |
| `9` | The service could not be brought to the requested state |
| `10` | Capability intentionally unavailable in the current session |

Every script and every test in the repository shares it. Ranges would replace a
working shared vocabulary with ninety codes, of which Session 3 would define
perhaps eight and the remaining eighty-two would mean nothing — while `10`,
which has a precise meaning today and is asserted against four stub commands,
would land inside the "config" range.

So the convention stands (D42). The question that remains is whether Session 3's
new failures fit inside it, and one does not.

Session 3 introduces a stop condition with no existing code: **an existing data
volume whose recorded project identity does not match the project being
deployed** (ADR 0030). Each candidate is wrong in a way that would mislead:

- `4` is *missing* runtime state. Here the state is present — that is the
  problem.
- `5` is a validation failure. Nothing is malformed; both identities are
  perfectly well-formed and they disagree.
- `6` is "a check failed", which is true of every nonzero exit and tells an
  operator nothing about what to do next.
- `7` is a provider disagreement. There is no provider involved.
- `9` is "could not be brought to the requested state", which is technically
  accurate and actively harmful here: it reads as transient, and the correct
  operator response to a transient failure is to retry. Retrying this is how the
  wrong volume gets adopted.

The remaining Session 3 failures do fit: `4` missing runtime state, `5`
contract, checksum, ledger or render disagreement, `6` a gate check failed, `8`
a secret failure, `9` a service that would not start.

## Decision

Exactly one code is added.

| Code | Meaning |
|---|---|
| `11` | Project-identity mismatch against an existing volume — the data is not yours |

It is raised only by the identity comparison of ADR 0030, only on a mismatch of
the immutable fields, and never for any other reason. It is terminal: no command
retries it, no command offers to resolve it, and no flag converts it into a
success.

The convention is otherwise unchanged. `10` keeps its meaning and keeps its
assertions against the remaining stubs.

## Consequences

`tests/contract/test_cli_contract.py`'s frozen table gains one row. This is one
of exactly four ADR-backed changes to currently-passing tests in Session 3
(§9.9 of the Session 3 plan); anything else turning red is a stop condition, not
a fix.

A single-purpose exit code is a strong claim: it means that if an operator ever
sees `11`, there is exactly one thing that happened and one page that explains
it. That is only true as long as nobody widens it. `11` must not become "an
identity problem" — the moment it also covers a missing sentinel, an
unreadable state file, or a failed comparison, it stops answering the question
it was created to answer.

The message accompanying it records the expected and observed **non-secret**
identities, so an operator can tell which volume they have without the exit code
having to carry the detail.

Enforced by:

- `tests/contract/test_cli_contract.py` — the exit-code table (Run 5)
- `DBX-PG-003` — an existing data volume is bound to one project identity and a
  mismatch is refused (Run 5 offline, Run 8 live)

## Alternatives considered

**Adopt the runbook's ranges.** Room to grow, and a code's decade tells you its
subsystem. It discards a convention every script and test already shares, for a
scheme in which almost every value is undefined, and it collides with `10`.

**Reuse `5`.** No new code, and a mismatch is arguably a contract violation. It
would put "your manifest is inconsistent" and "this volume belongs to another
project" behind one number, and those have nothing in common in what the
operator must do next.

**Reuse `9` and rely on the message.** Fewest moving parts. `9` reads as
transient and invites a retry, and retrying is precisely the action that must
not be taken.

**Use `1`.** Conventional for "general error" and currently unused. It is unused
deliberately — an uncaught error, a failed `set -e`, and an unhandled signal all
produce `1`, so a meaning assigned to it could never be distinguished from a
crash.

# 0017 — A stub that becomes real stops returning 10

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** DX-002

## Context

Session 1 shipped four commands that document a future capability and refuse to
pretend otherwise: `bootstrap-providers.sh`, `connect.sh`, `migrate.sh`,
`restore-test.sh`. `tests/contract/test_cli_contract.py` asserts, for each, that
a bare invocation exits `10` and that stderr names the owning session.

Session 2 implements `bootstrap-providers.sh`. Once it is real, a bare
invocation is not "unavailable this session" — it is a missing `--host` and a
missing `--project`, which the exit-code convention says is `2`. So the existing
test must change, and it is a currently-passing test.

That is the situation the bright-line rule was written for, and the rule is
right to catch it: "the stub grew up" is exactly what someone would say while
quietly deleting an assertion that had become inconvenient. The distinction that
makes this legitimate is not that the change is small. It is that the property
being asserted survives, applied to a smaller set.

## Decision

`bin/bootstrap-providers.sh` leaves `FUTURE_STUBS`. The three remaining stubs
stay, and `test_future_stub_exits_ten` continues to run against them unchanged.

In its place, `bootstrap-providers.sh` gains the command-contract tests every
implemented command carries, and they are stricter than the one it left:

| Invocation | Exit | Why |
|---|---|---|
| `--help` | `0` | Documents itself, as `DX-002` requires. |
| *(no arguments)* | `2` | Missing required input, not "unavailable". |
| `--apply` without root | `3` | Missing privilege, refused before any provider call. |
| `--destroy` without `--confirm <project_key>` | `2` | A destructive action needs the name said back. |
| `--plan` twice | `0`, no changes | Convergence is the property, not idempotence by luck. |

**The general rule.** A stub may leave `FUTURE_STUBS` only in the session that
implements it, only together with real command-contract tests, and only in a
commit that leaves every other stub's assertion untouched. Emptying
`FUTURE_STUBS` is not a way to make `test_future_stub_exits_ten` pass.

## Consequences

`DX-002` keeps meaning what it meant: every operator command documents itself,
obeys the exit-code convention, works from any directory, and never prints the
environment. It now means that for one more command, more strictly.

What this makes harder, deliberately: there is no longer a single place that
says "these commands are not real yet" for `bootstrap-providers.sh`. Its status
is readable only from its behaviour and its tests, which is the correct place
for it to be readable from once it is real.

Enforced by:

- `tests/contract/test_cli_contract.py::test_future_stub_exits_ten` (three stubs)
- `tests/contract/test_cli_contract.py::test_bootstrap_providers_is_no_longer_a_stub`
- `tests/contract/test_root_script_policy.py::test_root_commands_refuse_a_non_root_apply`
- `tests/contract/test_root_script_policy.py::test_destructive_commands_require_confirmation`

## Alternatives considered

**Keep it in `FUTURE_STUBS` and make a bare invocation still return 10.** The
command would lie about its own input handling forever, and `2` would become
unreachable for the one case it exists to describe.

**Delete `test_future_stub_exits_ten` now that one stub has graduated.** Removes
the assertion for the three commands that still need it, which is the failure
mode the bright-line rule names outright.

**Introduce a `--session-2` flag so the old behaviour is still reachable.** Two
behaviours in one command, selected by a flag nobody would pass, tested by
nobody. A dead branch that returns `10` is worse than no branch.

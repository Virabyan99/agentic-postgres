# 0267 — The runtime wrapper permits `stop` and `start`

- **Status:** Accepted
- **Date:** 2026-10-10
- **Session:** 38, Run 12 (`docs/plans/session-38-implementation-plan.md`,
  D2314)
- **Affects:** `bin/compose.sh` (`RUNTIME_ALLOWED` and `NEEDS_DAEMON` gain
  `start`; `RUNTIME_ALLOWED` gains `stop`),
  `tests/contract/test_compose_contract.py`,
  `tests/contract/test_project_runtime_stop_start.py`.
- **Amends:** the runtime allowlist of ADR 0021/0022/0034. Their rules stand:
  nothing that reaches inside a container, creates one outside the reviewed
  model, or injects a value is permitted.
- **Related:** ADR 0259 (sleep keeps the containers; wake starts the same
  ones), D2155, D2192.

## Context

Sleep and wake (ADR 0259) are `bin/project-runtime.sh stop` and `start`:
the edge detached, then `compose.sh --runtime … stop`; and `compose.sh
--runtime … start --wait --wait-timeout 120`, then the edge attached. The
runtime wrapper's allowlist was `up down restart build ps config logs run`,
and its contract test asserted `start` absent. So `compose.sh` refused both
with exit 10 and `project-runtime.sh` exited 9 -- on the host, the first time
either ran (Run 12, operation `4b00a0fe`, the slot's sleep: the timers and the
boot unit disabled, the edge detached, the containers left running).

`tests/contract/test_project_runtime_stop_start.py` runs `project-runtime.sh`
for real against a RECORDER standing in for `compose.sh`; the recorder
accepts every subcommand, so the module was green while the wrapper it
replaces refused both. Run 9's lifecycle rehearsal used a loopback stand-in
with no host. Neither half had met the other.

## Measured (2026-10-10, WSL, Compose v5.1.3; OVH runs v5.6.0)

A one-service project with a health check: `up -d --wait`, then `stop`
(exit 0, the container `exited`, kept), then `start --wait --wait-timeout
120` (exit 0 in 6.2 s, **the same container id**, `healthy`).

## Decision

`stop` and `start` join `RUNTIME_ALLOWED`; `start` joins `NEEDS_DAEMON`, so
an unreachable daemon is reported as such. `start` creates nothing: it starts
what `up` already created from the reviewed model, with the mounts and the
secret generation it had -- the property ADR 0259 needs, and the reason
`OVERRIDE_REQUIRED` and `VALIDATES_SECRETS` are left as they are (the
override and the secret sources were checked when `up` created the
containers; `start` changes neither). `stop` is a subset of `down`'s effect.
`exec`, `attach`, `cp`, `create`, `watch` and `scale` stay refused.

**The class is guarded, not the instance**: a test reads `project-runtime.sh`
and `compose.sh` together and requires every subcommand the first hands the
second under `--runtime` to be in the allowlist, and the real allowlist
conditional is run against `stop` and `start`.

## Consequences

- Sleep and wake work through the product; the proof is Run 12's lifecycle
  on the host (sleep: the edge's 404; wake: the first answer after `start`).
- A future runtime verb added to `project-runtime.sh` without the wrapper's
  permission fails the guard offline instead of on a customer's project.

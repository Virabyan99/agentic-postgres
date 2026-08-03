# 0013 — Compose wrapper scopes, the runtime gate, and three env files

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** `CFG-015`, `DEP-EDGE-001`, `DEP-EDGE-002`, `DEP-EDGE-003`, `SEC-SECRET-002`, `SEC-NET-001`

Amends plan decision **M** (the `compose.env` key set) and plan decision **T**
(the environment allowlist) from Session 1.

## Context

`bin/compose.sh` was Session 1's largest security control and its most absolute
one: eight subcommands refused with exit `10`, unconditionally, because Session
1 started nothing. Session 2's entire purpose is starting something.

The naive change is to delete the refusal. That throws away the property worth
keeping — which is not "containers never start" but "**containers never start by
accident**". A `docker compose up` typed in the wrong directory, or a CI job that
inherited a stale `COMPOSE_PROJECT_NAME`, should still fail loudly.

Three further problems arrive at the same time:

- the shared edge plane is a *different model* (`infra/edge/compose.yaml`) with a
  different project name and different env, but it must not be reachable by
  passing an arbitrary `--file`;
- the project probe's Traefik router labels have the router name **in the label
  key** (`traefik.http.routers.<name>.rule`). Interpolation inside a label key is
  not portable to the Compose version floor of `2.24.0`, and the VPS gets
  whatever Docker's repository ships while this workstation runs `v5.1.3`;
- the values those labels need — the ACME resolver, the baseline middleware
  chain — come from `host.yaml`, which is **not** one of the five digested render
  inputs. Putting them in `.generated/{key}/compose.env` would make a rendered
  file depend on which machine produced it and break `CFG-004`.

## Decision

**Refusal stays the default.** With no flags, all eight subcommands of
`FORBIDDEN` still exit `10`. The list is byte-for-byte what Session 1 shipped,
and a test asserts that separately from asserting the behaviour.

**`--runtime` is the documented way through, and it requires root.** The check
order is privilege first, then allowlist: what an unprivileged caller may do
does not depend on which subcommand they asked for. `--runtime` permits exactly
`up down restart build ps config logs`. It does **not** permit `exec`, `attach`,
`run`, `cp`, `start` or `create` — those reach inside a running container and
nothing in Session 2's documented path needs them. Granting them needs an ADR.

**`--edge` selects a scope, not a file.** The edge model is a fixed path in the
repository. Callers may not inject a `--file`, an `--env-file`, a project name,
or a protected interpolation variable; the wrapper builds all of those.

**Edge mode refuses `-v` / `--volumes`.** ACME state is a bind mount, so
`down -v` cannot actually reach it — refusing the flag removes the question
rather than relying on that staying true. A deleted production ACME file is
exactly how a failed renewal becomes an exhausted Let's Encrypt rate limit.

**Three env files, pairwise disjoint, split by provenance:**

| File | Provenance | Passed when |
|---|---|---|
| `versions.env` | the lock | always |
| `.generated/{key}/compose.env` | the project manifest | project scope |
| `/var/lib/agentic-postgres/projects/{key}/compose.env` | `host.yaml`, root-owned | `--runtime`, if present |

Disjointness is asserted for every pair, not just the first, so no `--env-file`
ordering can let one silently override another. The project file grows from four
keys to eight — `PROJECT_KEY`, `PROJECT_ENVIRONMENT`, `PROJECT_DOMAIN`,
`HEALTH_ROUTER_NAME` — and the rule that keeps it honest is that **every key in
it is derived from the project manifest alone**.

**Fully rendered label keys live in the root-owned runtime override.** The
committed `compose.yaml` carries the probe's identity labels and its network
hint but **not** `traefik.enable` and not the router labels. The side effect is
worth more than the cause: without `traefik.enable` the committed model is inert
to Traefik, so exposure becomes an act of deployment rather than a property of a
file in the repository.

**The environment allowlist is unchanged.** `KEEP_VARS` is Session 1's eight
variables. Under `sudo` and under systemd the wrapper reads what it needs from
its own environment and forwards none of it; `DOCKER_BUILDKIT` and
`BUILDKIT_PROGRESS` are **set** by the wrapper rather than allowlisted. Setting a
value is strictly stronger than allowlisting an inherited one, and it keeps
decision **T**'s bounded-and-provable property exactly as it was.

**Runtime mode validates secret sources before starting anything.** Every
`file:` source in the *resolved* model — resolved, so an override cannot
introduce a path the reviewed model never showed — must sit under
`/var/lib/agentic-postgres/secrets/{project_key}/`.

## Consequences

Makes easy:

- The accident case still fails: a bare `up` in a checkout exits `10` with a
  message naming the flag it would need.
- CI validates the edge model with no host and no root, because `--edge config`
  derives its env from `host.yaml` rather than reading root-owned state.
- Adding a host-derived value to a project's runtime environment cannot
  accidentally land in a rendered, digested file — there is nowhere in
  `COMPOSE_ENV_KEYS` for it to go.

Makes hard:

- Every runtime operation needs `sudo`, and the operator is deliberately not in
  the `docker` group. That is the point: Docker access is root-equivalent, and a
  group membership makes it invisible.
- The wrapper is now ~330 lines and does real argument parsing. Mitigated by
  routing every invocation through one environment-construction function, so
  there is one place to audit and one thing to assert about.
- `--runtime` beyond the allowlist cannot be tested without a root test process.
  The allowlist itself is asserted from the script source instead, and the
  privilege refusal is asserted at runtime.

## Alternatives considered

**Delete the refusal now that Session 2 starts containers.** Rejected: it
discards the property worth keeping. "Never by accident" survives Session 2;
"never at all" was only ever a proxy for it.

**A separate `bin/compose-runtime.sh`.** Rejected: two scripts means two
environment-construction paths, and the second one is where the allowlist quietly
diverges. One wrapper with a gate keeps a single audit surface.

**Let callers pass `--file` for the edge model.** Rejected: an injectable model
path makes every other control advisory, because the caller chooses what is
being validated.

**Put the host-derived values in `.generated/{key}/compose.env` and add
`host.yaml` as a sixth digested input.** Rejected, though it is coherent: it
would make a project's rendered output differ between hosts, so two operators
rendering the same manifest would get different bytes — and `CFG-004` would be
asserting a machine-specific fact.

**Interpolate the router name into the label key and require a newer Compose.**
Rejected: it raises the floor to satisfy a formatting convenience, on a host
whose Compose version is chosen by Docker's package repository rather than by us.

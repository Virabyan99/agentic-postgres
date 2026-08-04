# 0018 — A check that cannot reach the daemon reports that, not a verdict

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** `tests/contract/test_compose_contract.py::test_no_container_is_running`, `bin/session-01-check.sh` step 7, D13, ADR 0014

## Context

`bin/session-01-check.sh` must exit `0` on the VPS checkout (implementation plan
§2.4 and Run 5). On the deployment host it does not:

```
FAILED test_no_container_is_running[fixture-alpha-dev]
  compose: the Docker daemon is unreachable, which 'ps' requires.
```

The operator account is deliberately **not** in the `docker` group.
`bin/provision-host.sh` says so where it installs Docker, and the reason is that
group membership is root-equivalent: anyone in it can start a container that
mounts the host filesystem. Session 2's entire secret model assumes the operator
is not root.

So on the host this test asks the daemon a question the operator is not
permitted to ask, and reports the refusal as `assert 3 == 0`.

The failure is indistinguishable, in the gate's output, from a fixture container
actually running. That is the same defect this session already fixed twice: the
`DOCKER-USER` `status` action printed `(chain absent)` when it merely lacked the
privilege to read, and the listener check reported a loopback DNS stub as a
public exposure because it discarded the bind address. Reporting "I could not
look" as "I looked and here is the answer" is the shape of all three.

Four resolutions were considered.

**Add the operator to the `docker` group.** Rejected. It grants root by another
name and contradicts the provisioning script's stated policy.

**Run `bin/session-01-check.sh` under `sudo` on the host.** Rejected. The gate
renders fixtures, writes `evidence/` and `.generated/`, and would leave a
root-owned checkout behind that the operator can no longer manage. It also runs
the whole suite as root to answer one question.

**Stop running the Session 1 gate on the VPS.** Rejected. It contradicts §2.4,
and the gate proves things about the checkout that are worth proving there —
that the transported commit is clean and renders identically to the machine it
was tested on.

**Skip precisely when the daemon is unreachable.** Accepted, below.

## Decision

`test_no_container_is_running` skips **only** when `bin/compose.sh` reports the
Docker daemon unreachable, with a reason naming what went unproven and what
proves it instead. Every other failure — a non-zero exit for any other cause,
or a non-empty container list — still fails.

The claim does not go unproven on the host. It moves to the session that owns
the host: `bin/session-02-check.sh --mode host` runs as root and asserts the
running-container set directly, including that nothing but the edge publishes a
port. This is the same division ADR 0014 already made for step 7 of the gate,
where the Session 2 gate took over the broader claim about running containers.

Two constraints on the skip:

1. **It must be a capability probe, not an environment variable.** D10b reserves
   `skipif` on a named environment variable for `live_host` and `external`
   tests, where the operator declares the environment. This is not that: nothing
   is being declared, and a variable saying "no daemon here" could be set on a
   machine that has one. The probe asks the daemon.

2. **A skip must be visible.** `bin/write-session-evidence.py` printed passed,
   failed and errors but not skipped, so a suite that silently stopped checking
   something would still read as a clean run. `evidence.parse_junit` already
   collects the count; the summary now prints it.

The same rule applies to **step 7 of `bin/session-01-check.sh`**, which asks the
same question in shell rather than in pytest and died on the same refusal. It
now distinguishes the two outcomes in its printed result, and still validates
every rendered model, since `config` needs no daemon. Fixing only the pytest
test would have left the gate failing on the host for a reason this ADR had just
finished explaining was not a failure.

## Consequences

On a machine with a reachable daemon — every development machine, CI, and the
host when run as root — nothing changes. On the VPS as the operator, the gate
reports one skipped test with its reason rather than a failure that means
something else.

The risk accepted is that a fixture container could be running on the host and
this particular test would not say so. It is bounded: Session 2 starts no
fixture container on the host at all, and the Session 2 host gate enumerates
every running container as root.

The risk **not** accepted is a broad "skip if compose fails" rule. A guard test
asserts that a non-empty container list still fails, so the skip cannot grow
into a way of making the test quiet.

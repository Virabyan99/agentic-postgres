# 0040 — A loopback publication is not a public port

Status: proposed
Date: 2026-08-08
Session: 4, Run 1
Affects: SEC-NET-001, SEC-NET-002, DBX-PG-002, SEC-DBX-001, CFG-010

Accepted in Run 5, the run that first publishes a port. Drafted now because it
is the constraint Runs 2–4 are designed against, and because the measurement it
rests on had to be made before anything was built rather than after.

## Context

Two Session 2 requirements say, in the flat form the runbook wrote them:

- **SEC-NET-001** — "No public route reaches the direct PostgreSQL endpoint:
  nothing listens on it, no forwarded path carries it…"
- **SEC-NET-002** — "Only the edge publishes a host port…"

Three currently-passing P0 tests enforce them literally:

- `test_no_project_service_publishes_a_host_port` — scans the Compose model for
  any `ports:` key at all;
- `test_only_traefik_publishes_host_ports` — the same, from the other side;
- `test_only_the_edge_publishes_container_ports` — scans running containers on
  the host.

Session 4's entire purpose is a pooled transport a developer can reach. Every
one of those three becomes false. The temptation is to relax them, which is the
one thing this repository does not do: a currently-passing test may not be
weakened to make a new one pass, and ADR 0017's standing rule is that a
replacement assertion must be *stricter* than the one it replaces.

The statements are not wrong. They are **unversioned**: they were written when
"publishes a host port" and "is reachable from the internet" were the same
sentence, because nothing but Traefik published anything. Session 4 separates
them, so the requirement text has to separate them too.

### What was measured before this was written

A throwaway PostgreSQL 18 cluster, the locked image, publishing
`127.0.0.1:<port>:5432` on Docker 29.5.2:

| Path | Source the server sees | `pg_hba.conf` line matched | Wrong password |
|---|---|---|---|
| Through the published loopback port | `172.17.0.1` (bridge gateway) | 128 — `host all all all scram-sha-256` | **rejected** |
| The container's own loopback | `127.0.0.1` | 119 — `host all all 127.0.0.1/32 trust` | **accepted** |

The second row is the control, and it is the reason the first row means
anything. Had the probe simply reported "the wrong password was rejected", a
broken probe would have produced the same output. The two rows differ, from the
same server, in the same second, and the server's own log names the line number
for each.

This is the fact the whole session turns on. If a published port had landed on
the trust line, publishing one would have granted unauthenticated superuser
access to every process on the host — while every credential test in the suite
continued to pass, because they all authenticate correctly.

## Decision

**A publication is not a public reachability. The two are separated in the
requirement text, and the tests assert the property the old ones were reaching
for rather than the proxy they happened to use.**

1. `SEC-NET-002` becomes: *only the edge publishes a port on a non-loopback
   address, and every other publication carries an explicit loopback
   `host_ip`.* `SEC-NET-001` keeps "no public route reaches the direct
   endpoint" and drops "nothing listens on it", which was never the property
   worth having — an off-host scan finding the port closed is.

2. The model-side test does not count publications. It reads each publication's
   `host_ip` and fails when it is absent, `0.0.0.0`, `::`, or any address that
   is not in `127.0.0.0/8` or `::1`. **A publication with no `host_ip` is
   refused**, which is strictly more than the old test could say: the old one
   admitted every future `ports:` entry the moment anyone added a legitimate
   one.

3. The host-side test reads the live publication table the same way, so a
   loopback binding in the model and a wildcard binding in an override cannot
   disagree silently.

4. The negative proof is external: an off-host full-TCP scan finds both
   allocated ports closed while 443 is open. Deployed output may not report
   `ready` before that scan has run.

5. The DOCKER-USER policy is untouched. Loopback traffic does not traverse
   `FORWARD`, so `test_policy_permits_exactly_eighty_and_four_four_three` still
   holds and still means what it said.

6. **`database.pooled_public` becomes an unsupported profile rather than a
   configurable one.** The manifest has carried it since Session 1, with an
   allowlist and a rule that a default route is not an allowlist — which is
   `CFG-010`, a Session 1 P0. A narrow allowlist is still a public bind, so the
   requirement is versioned here too: `pooled_public` must be false, the
   allowlist must be empty, and the refusal names `bin/connect.sh` so an
   operator who wanted the feature is told what replaces it. The field stays
   declarable on purpose, because an unknown-key error reads like a typo and
   this is a decision.

## Consequences

The three replaced tests each gain a case they did not have: a publication
without `host_ip`, a publication on `0.0.0.0`, and a publication on the host's
public address are all now expressible and all fail. The old tests could not
distinguish those from each other, because they never got as far as looking at
an address.

The image's HBA default is now load-bearing in a way it was not. Session 4 ships
without rendering a `pg_hba.conf` — the measurement above says the published
path already lands on `scram-sha-256` — but that is a fact about Docker's NAT
behaviour, so it is asserted by a test that runs wherever Docker does, including
in the host gate, rather than recorded here in prose.

An operator who publishes a port by hand, outside the runtime override, defeats
this. That is detected rather than prevented: the host-side test reads the live
table, not the file that was supposed to produce it.

## Alternatives considered

**Publish nothing; forward straight to the container IP over SSH.**
`ssh -L 15432:<container-ip>:5432` needs no publication at all, and with
`PermitOpen` the forward can be pinned. Rejected because a container IP is not
stable across recreation, so the forward target would have to be re-resolved per
connection by something trusted, and `PermitOpen` would have to be rewritten
every time a container was recreated. A stable loopback allocation is auditable
by reading one file and testable from off-host; the alternative is neither.

**Keep the tests and grant Session 4 an exemption list.** Rejected on sight.
An exemption list is the mechanism by which the next exemption is cheap.

**Bind the pooler to the host's private interface instead of loopback, so the
tunnel is unnecessary on the LAN.** Rejected: this host has no private LAN worth
the assumption, and "reachable from one more network than you meant" is exactly
the failure the external scan exists to catch.

## Proofs

Written in Run 4 (model) and Run 5 (host and external). Named here so the ADR
can be checked against them:

- `tests/contract/test_compose_contract.py::test_every_publication_binds_an_explicit_loopback_address`
- `tests/contract/test_compose_contract.py::test_only_the_edge_publishes_a_non_loopback_address`
- `tests/deployment/test_session4_host.py::test_the_live_publications_all_bind_loopback`
- `tests/external/test_session4_public_edge.py::test_the_allocated_ports_are_closed_from_off_host`
- `tests/contract/test_image_contracts.py::test_a_published_loopback_port_does_not_match_the_trust_line`

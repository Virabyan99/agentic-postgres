# 0044 — There is no publication

Status: accepted
Date: 2026-08-10
Session: 4, Run 9
Supersedes in part: [0040](0040-a-loopback-publication-is-not-a-public-port.md)
Amends: [0042](0042-host-port-allocation-is-state-keyed-by-the-volumes-identity.md)
Affects: SEC-DBX-001, DBX-PORT-001, DBX-005, DX-DB-001, DX-DB-002

## Context

ADR 0040 decided that each project publishes its two database transports on a
host-loopback port, and that a loopback publication is not a public port. ADR
0042 made those ports durable state keyed by the identity the volume carries.
Runs 4 and 8 built both.

Run 9 tried to publish one and could not. **Docker does not publish a port for a
container attached only to an `internal: true` network.** It accepts the request
and records `HostConfig.PortBindings`, and it installs no DNAT rule and no
listener. Measured against a control in the same output: Traefik, on non-internal
networks, shows `0.0.0.0:443->8443/tcp` and a matching `-A DOCKER … -j DNAT`;
`pgbouncer` on `apg-alpha-dev-internal` shows a bare `6432/tcp` and no rule
anywhere (D115).

`internal: true` is not incidental. It is what `DBX-PG-002` and `SEC-NET-001`
rest on — the network with no route off the host — and what makes Session 2's
and Session 3's negative proofs inherited rather than re-derived.

So two things this project had already decided were in conflict, and the cheapest
resolution — moving the containers onto a non-internal network — pays for a
Session 4 convenience with a Session 2 isolation property.

One further fact, measured rather than assumed, because the first attempt at this
paragraph asserted the opposite of what was true: **the host can reach a container
on an internal network.** It holds `172.23.0.1/16` on the bridge and routes to the
subnet directly. `internal: true` isolates the network from the outside world, not
from its own gateway.

## Decision

**Nothing is published. The tunnel targets the container endpoint on the host's
own bridge.**

1. `bin/connect.sh` forwards to the container's address and port:
   `ssh -L 127.0.0.1:<local>:<container-ip>:<container-port>`. The SSH server is
   the host, the host is the gateway of that bridge, and no host port exists.

2. **The container address is resolved by the broker, per call, and is never
   written down.** A container IP changes when the container is recreated, and a
   recorded one is a value that is right until the next restart — which is the
   defect this project produces most often. The broker reads it from Docker at
   the moment it answers.

3. **ADR 0042's allocation survives, reinterpreted.** It no longer names a port
   the host publishes; it names the **local** port a developer binds, which is
   what "an allocation that moves silently breaks every developer's saved tunnel"
   was always about. The registry, the `instance_uuid` key, two ports per
   project, durability across redeploy and reboot, and `reserved → active` all
   keep their meaning. `verify` connects to the container endpoints from the
   host, which is a real connect to the real service.

4. **The deployed document records the local endpoint, not the tunnel target.**
   `endpoint.host` is the loopback the developer binds and `endpoint.port` is the
   allocated port. The ephemeral container address stays out of published state.

5. `runtime_override` may not write a `ports:` entry at all. The function that
   built one becomes a refusal, so the capability is absent rather than unused.

## Consequences

**The most dangerous operation in Session 4 stops existing.** §4.1 was written
because a publication can silently turn a private database public and the failure
is invisible from inside — every authentication test passes either way. That
class of failure is now structurally impossible rather than guarded against.

**`SEC-DBX-001` stays a real measurement and changes what it proves.** It was
"the published ports are closed from off-host". It becomes "no database transport
is reachable from off-host", scanning the allocated range and 5432/6432 alike. It
goes red the day a publication is introduced, which is the property worth having;
it is not vacuous merely because the expected answer is now structural.

**ADR 0040 is superseded in its publication clause and stands in the rest.** Its
threat model, its refusal of `0.0.0.0`, `::`, host networking and a publication
without `host_ip`, and its versioning of `CFG-010` are all unaffected — there is
simply nothing left to bind wrongly. The measured HBA table it carries is
untouched.

**A developer needs SSH to reach a database, always.** There is no host port to
reach even from the host without a container address, so `bin/db.sh`'s
`docker exec` path remains the operator's route and `bin/connect.sh` remains the
developer's. That is a narrowing, and it is the point.

**Run 4's work is kept, not discarded.** The allocator, the registry, the lock,
the atomic write and the `reserved`/`active` distinction are unchanged. What is
removed is the override's publication block and the code that built it.

## Alternatives considered

**Attach the pooler to a non-internal network.** Cheapest, and it works. Rejected:
`internal: true` is what two sessions of negative proofs rest on, and every one of
them would have to be re-derived rather than inherited. It also moves against
where Sessions 5–12 go — the REST, MCP and auth surfaces are reached through
Traefik on the edge network, and nothing in the roadmap wants the cluster
reachable from the host network.

**A forwarder that straddles the two networks.** Keeps the cluster internal and
adds a process in front of the credential path, which is the place this session
has been most careful about adding components. Rejected as unnecessary once the
host proved able to reach the bridge directly: it would exist only to move bytes
the host can already move.

**Publish through Traefik's TCP router with SNI.** Would give a public,
TLS-terminated pooled endpoint, which is a product decision Session 4 explicitly
does not make — `pooled_public` was refused outright in ADR 0040 and `CFG-010`
was versioned to say so. Recorded here as the direction any future public pooler
would have to take, not as an option for this session.

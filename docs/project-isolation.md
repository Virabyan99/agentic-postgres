# Project isolation

Two projects on one host share one edge plane and nothing else. This is what
that means, and how each part of it is proved.

Cited by `Documentation=` in `agentic-postgres-project@.service`. The
requirement is `DEP-ISO-002`; the broader claim about state and authority is
`DEP-ISO-001`, owned by Session 12.

## What is shared, and why

Exactly one thing: the **edge plane** — Traefik and the Docker socket proxy.
Two proxies cannot both hold ports 80 and 443, so a shared edge is what makes
two projects on one host possible at all.

The cost is that edge operations have a blast radius covering every project,
which is why `bin/edge.sh promote-acme` demands the host id back and why
`bin/edge.sh down` never passes `-v`.

Everything else is per project:

| Resource | Scope |
|---|---|
| Edge network (`edge`) | Per project. Traefik joins every one. |
| Internal network (`internal`) | Per project. Traefik joins **none**. |
| Compose project name, volumes, database name, roles | Per project, derived by `naming.derive` |
| Route (hostname) | Per project |
| Secret generations under `/var/lib/agentic-postgres/secrets/<key>/` | Per project, root-owned |
| systemd unit | `agentic-postgres-project@<key>.service` |

## Attachment is a separate operation, and the order matters

Compose cannot express "attach the shared edge to a network that did not exist
when the edge was written". Adding a project would otherwise mean editing and
restarting the edge, dropping every other project's ingress for the duration.

So `bin/edge-network.sh` attaches and detaches idempotently, and the ordering in
`bin/project-runtime.sh` is asymmetric on purpose:

```
up:    materialize secrets -> compose up -> attach the edge
down:  detach the edge     -> compose down
```

Attaching last means a route never points at a container that is not yet
serving. Detaching first means the edge network has no endpoint when Compose
tries to remove it — otherwise removal fails, the network survives, and the next
start finds a network it did not create and cannot reconcile.

## How each claim is proved

All of these live in `tests/deployment/test_session2_isolation.py` and run on the
host with both projects deployed.

| Claim | Proof |
|---|---|
| Each hostname reaches its own project | `GET https://<domain>/__apg/healthz` returns that project's key |
| Neither hostname serves the other | Both directions, explicitly |
| An unclaimed hostname is not served | Host header `unclaimed.invalid` → 404, so there is no catch-all router |
| Traefik joins both edge networks and neither internal one | `docker inspect` of the Traefik container, by network **name** |
| Neither project joins the other's networks | Per container, by project label; both "on its own" and "not on the other's" |
| Each project holds only its own secret generation | By mount path, never by comparing digests |
| Stopping one leaves the other routed | `systemctl stop` B, check A, start B, and assert B came back |

Two of these exist to keep the others honest.

**`test_the_two_projects_are_actually_distinct`** — two names for one project
would pass every routing assertion above.

**`test_the_recorded_networks_are_project_scoped`** — every network assertion
names a field out of the deployed document. Before
[ADR 0023](decisions/0023-isolation-proofs-read-the-edges-network-not-the-projects.md)
those fields held `edge.egress_network`, which is copied from the host manifest
and identical for every project, so all three network assertions passed while
measuring nothing. One of them compared network names against the project
*key* (`alpha-dev`) while every network name begins `apg-`, so the comprehension
was always empty and the assertion could not fail. This test is what notices if
that returns.

**The one deliberately mutating test** stops project B and restarts it, then
asserts B came back — so a failure to restore cannot pass silently. Isolation
that only holds while both projects are healthy is not isolation.

## Identity collisions

`evidence.collision_count` compares fifteen parsed semantic fields plus all
thirteen derived role names, pairwise, across every rendered project. Never
duplicate strings; never a digest.

A pair where **both** values are `None` is not a collision
([ADR 0016](decisions/0016-absence-is-not-a-collision.md)). Every Session 2
project disables object storage (Session 7) and backups (Session 10), so four of
the isolated fields are `null` for all of them. `null` means "this project has
no bucket", and two projects that both have no bucket are not sharing one.

Roles get no such exemption: `naming.derive` produces all thirteen
unconditionally, so a `None` there is a bug rather than a disabled facility.

## What this does not claim

Isolation here comes from the **deployment topology**, not from application
correctness. Nothing in Session 2 prevents a project's own code from being
wrong; it prevents one project's wrongness from reaching another's network,
route, volume or secret.

Session 12 owns the rest of `DEP-ISO-001`, and its placeholder in
`tests/contract/test_future_deployment.py` is untouched.

## See also

- [Host baseline](host-baseline.md)
- [Secret handling](secret-handling.md)
- [ADR 0009 — one edge plane is shared](decisions/0009-host-and-edge-plane.md)
- [ADR 0016 — two projects that both lack a facility do not collide](decisions/0016-absence-is-not-a-collision.md)
- [ADR 0020 — configuration in /etc, generated output in /var/lib](decisions/0020-project-state-roots.md)
- [ADR 0023 — the isolation proofs read the edge's network, not the project's](decisions/0023-isolation-proofs-read-the-edges-network-not-the-projects.md)

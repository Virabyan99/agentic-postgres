# 0009 — Host configuration is separate, and one edge plane is shared

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** `DEP-HOST-001`, `DEP-FW-001`, `DEP-EDGE-001`, `DEP-EDGE-002`, `DEP-EDGE-003`, `DEP-ISO-002`, `OPS-TLS-001`, `SEC-NET-001`

## Context

Session 2 introduces facts that belong to a *machine* rather than to a project:
which OS release is supported, which SSH sources are allowed, which ACME
account issues certificates, which Docker networks the ingress stack owns.
Session 1 had exactly one configuration authority — `project.yaml`, per
[0002](0002-configuration-authority.md) — and the obvious move is to extend it.

That move is wrong, and the reason is the determinism contract. Session 1
asserts that `.generated/{project_key}/outputs.json` is byte-identical for the
same inputs, where "the inputs" are the four files digested into
`outputs.inputs`. A host fact reaching a rendered document would make the render
depend on which machine ran it, and `CFG-004` would be asserting something
false.

The second question is whether each project gets its own Traefik. One per
project is the isolated-looking answer, and it does not work: two Traefik
containers cannot both bind host ports 80 and 443, so the second project would
need different ports, which means no ACME HTTP-01 and no ordinary HTTPS URL.

## Decision

**`host.yaml` is a separate manifest with its own schema and its own loader.**
It is never digested into a rendered document, is never an input to
`naming.derive`, and is not committed — only `host.example.yaml` is. The host
copy of record lives at `/etc/agentic-postgres/host.yaml`, root-owned, `0600`,
installed by `provision-host.sh --apply` from the operator's copy.

**One Traefik edge plane is shared by every project on the host.** It owns
ingress and nothing else: no project state, no project authorization, no
project secret. That is what makes sharing acceptable.

**Project edge networks remain distinct, and Traefik is attached to each one
explicitly.** Traefik straddles the boundary; nothing else does. It is attached
to **no** project *internal* network, ever, and `edge.sh reconcile` both asserts
that and repairs attachment after any container recreation — Docker network
membership added by `docker network connect` does not survive recreation, so
without reconciliation the routes come back up only until the next restart.

**Host-derived values never enter `.generated/`.** Values the project Compose
model needs that come from `host.yaml` — the ACME resolver name, the baseline
middleware chain — are rendered into the root-owned
`/var/lib/agentic-postgres/projects/{project_key}/compose.env` at deploy time
and passed as a third `--env-file` in `--runtime` mode only. See
[0012](0012-output-document-kinds.md) for the matching split in `outputs.json`.

**The supported-release allowlist is a property of the implementation.**
`host.yaml` may narrow it; it can never widen it. The authority is the
`osRelease` enum in `schemas/host.schema.json`, per [0007](0007-bounds-authority.md).

**`ssh.allowed_source_cidrs` is required and non-empty, and `0.0.0.0/0` is a
permitted value.** An operator with no static source address must write that
choice down rather than omit the field, and `provision-host.sh` reports it as a
deviation on every run. The SSH boundary is key-only authentication with
`PermitRootLogin no` and `MaxAuthTries 3`, asserted against `sshd -T` for the
real operator tuple; the CIDR restriction was always defence in depth.

## Consequences

Makes easy:

- Two projects get real HTTPS on real hostnames with one certificate resolver
  and one ACME account, which is the only shape that works on one IPv4 address.
- A project manifest stays portable: it names no machine, so moving a project to
  another host changes `host.yaml` and nothing else.
- `CFG-004` stays true, and the rendered document stays reproducible in CI.

Makes hard:

- Traefik is a shared failure domain. Restarting it interrupts every project's
  ingress. Accepted: the alternative does not function, and `OPS-TLS-001`
  measures the restart path rather than pretending it is not there.
- Two configuration files exist where Session 1 had one. Mitigated by keeping
  them strictly disjoint in *scope*: no key appears in both, and the loaders are
  separate.
- Attachment reconciliation is now a required step after every edge change and
  every boot, not an optional nicety. `agentic-postgres-edge.service` owns it.

Residual risk, stated rather than designed away: the socket proxy narrows
Traefik's Docker API authority but is not an absolute host-security boundary,
because the proxy process itself still has the Docker socket mounted. The threat
model says so and `DEP-EDGE-003` tests the narrowing, not an absolute.

## Alternatives considered

**Extend `project.yaml` with a `host:` block.** Rejected: it breaks `CFG-004`,
and it makes every project manifest specific to one machine.

**One Traefik per project.** Rejected: only one container can bind `:443`. The
second project would need a non-standard port, losing ACME HTTP-01 and ordinary
URLs — the thing Session 2 exists to produce.

**Traefik on the host, outside Docker.** Rejected: it loses the Docker provider,
so routes would come from a file that something has to generate and reload, and
it puts a network-facing daemon outside the container boundary and outside the
`DOCKER-USER` policy.

**Mount `/var/run/docker.sock` into Traefik directly.** Rejected: read access to
the Docker socket is root-equivalent on the host. The socket proxy costs one
container and removes every write verb from the ingress component's reach.

**Host facts as environment variables rather than a manifest.** Rejected: they
would be unvalidatable, undiffable, and invisible in review — and inherited
environment is the exact attack `bin/compose.sh` was built to stop.

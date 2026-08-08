# 0023 — The isolation proofs read the edge's network, not the project's

- **Status:** Accepted
- **Date:** 2026-08-07
- **Session:** 2
- **Affects:** `schemas/outputs.schema.json`,
  `src/agentic_postgres/deployed_output.py`,
  `tests/deployment/test_session2_isolation.py::test_traefik_joins_both_edge_networks_and_neither_internal_one`,
  `tests/deployment/test_session2_isolation.py::test_neither_project_joins_the_others_network`

## Context

`DEP-ISO-002` claims that two projects on one host share no route, no network
and no secret. The network half of that claim is what Run 7 exists to prove,
and the implementation plan states it directly: "Traefik attached to both edge
networks and neither internal network".

Two tests carry it, and both read `edge.egress_network` from the deployed
document to name the network in question.

`edge.egress_network` is not a project's network. `require_edge_is_up` in
`bin/deploy-session-2.py` copies it out of the **host** manifest:

```python
return {
    "stack_name": EDGE_STACK_NAME,
    "control_network": host["edge"]["control_network"],
    "egress_network": host["edge"]["egress_network"],
    "project_network_attached": False,
}
```

Those are the shared edge stack's own two networks — `apg-edge-control` and
`apg-edge-egress` — and every project on the host records the identical pair.
A project's own networks are `apg-<key>-edge` and `apg-<key>-internal`, named
in the rendered document under `compose.networks`, written into the rendered
`compose.env` as `EDGE_NETWORK_NAME` and `INTERNAL_NETWORK_NAME`, and read
from there by `bin/edge-network.sh`'s `project_edge_network` — which is what
actually gets attached. The deploy log says so in as many words:
`edge-network: attached to apg-beta-dev-edge`.

Nothing detected this while one project was deployed, because with one project
there is nothing for a shared value to collide with. Deploying the second made
it visible in one line: both documents reported `edge net apg-edge-egress`.

Three assertions are affected, and all three are vacuous:

**1. Traefik is attached to each project's edge network.**

```python
for project in (project_a, project_b):
    edge = project["edge"]["egress_network"]
    assert edge in networks, f"Traefik is not attached to {edge}; that project has no ingress"
```

This asserts `apg-edge-egress in networks` twice. Traefik is of course on its
own egress network, so the loop passes without once naming
`apg-alpha-dev-edge` or `apg-beta-dev-edge` — the attachments whose absence
the failure message calls "that project has no ingress". The test would pass
against a host where `edge-network.sh attach` had never run.

**2. Traefik is attached to neither project's internal network.**

```python
internal = sorted(
    name
    for name in networks
    if any(name.startswith(project["project"]["key"]) for project in (project_a, project_b))
    and not name.endswith("-edge")
)
assert not internal
```

The project keys are `alpha-dev` and `beta-dev`; every network name begins
`apg-`. `startswith` is therefore false for every network on the host, the
comprehension is always empty, and `assert not internal` cannot fail. This one
is independent of the field defect — a second bug in the same statement — and
it would have stayed invisible for the same reason: an empty result reads
exactly like a clean result.

**3. Neither project joins the other's network.**

```python
assert other["edge"]["egress_network"] not in networks, (
    f"{name} is attached to {other['project']['key']}'s edge network"
)
```

`other["edge"]["egress_network"]` and `own`'s are the same string, so this
asserts that a project's containers are not attached to the shared edge
stack's egress network. That is true, and it is not the claim: nothing here
checks that alpha's containers are off `apg-beta-dev-edge`.

The `assert names` guard above it is real and does work — it fails if no
container carries the project label. That is the only part of these two tests
that was measuring anything.

This is the same shape as ADR 0020's finding, from the other end. There, a
consumer read a path no producer wrote. Here, a consumer reads a field a
producer *does* write — with a value that answers a different question than
the one being asked. A missing field fails loudly; a plausible wrong one
passes quietly, which is worse.

## Decision

The deployed document gains the project's own network names, and the two
tests read those.

`edge` gains two required fields:

```json
"project_edge_network":     { "$ref": "#/$defs/composeName" },
"project_internal_network": { "$ref": "#/$defs/composeName" }
```

They are **carried** from the rendered document's `compose.networks`, in
`build_deployed_document`, alongside `database` and `template_version` — not
re-derived from the project key, and not measured. That module's docstring
already gives the reason, and `require_edge_is_up` gives it again from
experience: "Deriving a name a second time is the failure
`build_deployed_document` is written to avoid." An earlier version of this
code rebuilt `apg-edge_control` from the stack name by convention and shipped
a document naming a network that did not exist. The rendered document is the
one authority for what `compose.env` will say, and `compose.env` is what
`edge-network.sh` reads.

`egress_network` and `control_network` keep their names and their meaning.
They are correct as host facts, and the deployed document is right to record
which edge plane a project was attached to. What was wrong was reading them
as if they were project-scoped. Renaming them to `edge_egress_network` was
considered and rejected below.

Both tests are rewritten to assert what their names claim:

- Traefik is attached to `project_edge_network` for **each** project — two
  distinct networks, and the assertion now fails if `attach` did not run.
- Traefik is attached to **neither** `project_internal_network`. The scan is
  by explicit name rather than by prefix guesswork, so there is no string
  convention left to get wrong.
- Each project's containers are attached to their own `project_edge_network`
  and not to the other's.

A fourth assertion is added, and it is the one that keeps this ADR honest:
the two projects' `project_edge_network` values must differ, and must differ
from `egress_network`. Without it, a future regression that pointed both
fields back at one shared value would restore exactly the vacuum this ADR
closes, and every assertion above would go on passing.

## Consequences

- Every existing deployed document is invalid against the schema until it is
  rewritten, because the two fields are required. `./deploy.sh
  --through-session 2` re-publishes; this is the same re-publish the ACME
  promotion already requires for `tls.certificate_sha256`, so both projects
  are re-deployed once and satisfy both.
- The isolation tests can now fail. That is the change: before this they
  could not, whatever the host was doing.
- `tests/contract/test_deployed_output.py` needs no new keys in its
  `OBSERVED["edge"]` fixture — the fields are carried from the rendered
  fixture, not observed, so the contract test exercises the carrying path as
  written.
- The claim registered for `DEP-ISO-002` is unchanged. What changes is
  whether the test that carries it measures anything.

## Alternatives considered

**Rename `egress_network` to `edge_egress_network` and leave the tests
reading it.** Rejected: it makes the misreading less likely without making it
impossible, and it does not give the tests the value they actually need. The
project's network name would still be absent from the document.

**Have the tests derive `apg-{key}-edge` themselves.** Rejected for the
reason `require_edge_is_up` records: a second derivation path for a name is
how `apg-edge_control` got published. A test that reconstructs the network
name agrees with the code only for as long as both copies of the convention
stay in step, and the failure when they diverge is a test that passes against
a network nobody is using.

**Read `compose.env` from the test.** Rejected: it would prove the test can
read the same file `edge-network.sh` reads, which is a weaker claim than the
document being right — and the deployed document is what the external gate,
the evidence merge and the operator all consume. If it names the wrong
network, that is worth failing over.

**Fix only the `startswith` bug and leave the field alone.** Rejected: it
closes one of three vacuous assertions and leaves the two that matter most,
while making the file look reviewed.

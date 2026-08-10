# 0047 — An absence proof expires when a later session supplies the thing

Status: accepted
Date: 2026-08-10
Session: 4, Run 10
Generalises: [0046](0046-a-nologin-stub-is-a-fact-with-an-expiry-date.md)
Affects: SEC-NET-001, DBX-MIG-001, SEC-OWNER-001

## Context

Run 10 ran the whole host suite and the whole external suite for the first time
since Run 4, and each surfaced the same defect in a different requirement.

**On the host (D124, ADR 0046).** `test_only_the_migration_user_may_log_in`
asserted that the only role with LOGIN is `migration_user`. Session 4 Run 5
activated `app_runtime`, which is what the session is for.

**From outside (D125, this ADR).**
`test_the_deployed_document_still_reports_no_direct_endpoint` and
`test_the_pooled_endpoint_is_equally_absent` asserted
`status == "unavailable"` and `url is None`. Session 4 publishes both transports
in the deployed document — as the near end of a developer's tunnel (ADR 0044) —
so both assertions were false about a correct Session 4 deployment.

Two instances is a pattern, and the pattern has a name: **a session proves a
guarantee by asserting the absence of the thing that would violate it, and the
next session supplies the thing.** The absence was never the guarantee. It was a
proxy that happened to be equivalent while the feature did not exist.

The second instance is the more instructive one, because of *when* it was found.
Session 3 dropped the external mode — correctly, on D45's reasoning that a mode
measuring nothing would still write evidence saying it had run. The consequence
nobody drew: **these two proofs had not executed since Session 2.** They were
false from Run 4 of Session 4 onward and reported as covered throughout.

## Decision

**An absence proof is rewritten as the property it stands for, in the session
that falsifies it, and the replacement holds for every session at once.**

For `SEC-NET-001`, the property is not "the document reports no endpoint". It is
**the document reports no endpoint the world can dial.** The two tests become one
parametrized over both transports:

- `unavailable` still means `url is None` and `host is None` — a status with a
  URL beside it is a document contradicting itself;
- `available` must carry a **loopback** address in the `host` field *and* in the
  URL, because those are two places one address is written and this repository
  has watched such a pair drift;
- no URL carries a credential, asserted against the bytes rather than trusted to
  the schema pattern that forbids it;
- the URL's port equals the endpoint's port.

It holds against a Session 2, 3 or 4 deployment without being told which, and it
gets stronger rather than weaker as the product grows: today no transport could
be published publicly without failing it.

**Three rules follow, and they are the point of this ADR:**

1. **Prefer the property to its proxy.** "Nothing is listening" is a fact about
   today. "Nothing reachable is listening" is the guarantee.
2. **Derive the expected set from the deployed document** where one exists, as
   ADR 0046 does for roles and this does for endpoints. The document is written
   by the deploy, so the test widens exactly in step with what was deployed.
3. **A session that supplies a thing an earlier session proved absent runs that
   earlier session's whole suite**, in every environment that suite has. Not the
   part being worked on.

## Consequences

**Sessions 5 through 12 will hit this again**, and the shape is now predictable:
the auth service, PostgREST, FastMCP and the agent roles are all things earlier
sessions assert the absence of. Each of those absences should be read as a
proxy, and rewritten before it fails rather than after.

**Dropping a gate mode has a cost that D45 did not price.** Session 3 removed the
external mode because it measured nothing new — sound at the time, and it also
stopped running two proofs that later became wrong. A mode that measures nothing
*today* is still the only thing that runs the assertions belonging to it. The
correction is not to reinstate vacuous modes; it is that **restoring a mode is
also a review of every proof that mode owns**, which is what Run 10 has now done
for the four external ones.

**`SEC-NET-001` is unchanged as a requirement**, and its description still reads
correctly: no public route reaches the direct PostgreSQL endpoint. What changed
is that one of its five proofs now measures that instead of measuring a
precondition of it.

## Alternatives considered

**Delete the two document tests and rely on the port scan.** The scan is the
stronger proof and it passes. Rejected: the scan proves *this* deployment's
allocated ports are closed from *this* vantage point. The document assertion
proves the system does not intend to publish a reachable address at all, which is
the thing that would still be true if the scanner sat behind a firewall — and
catching a public `host` in a document is cheaper than discovering it by scan.

**Gate them on `deployed_through_session`.** A branch per session, forever,
inside a security proof. Rejected on the same grounds as everywhere else in this
repository: the deployed document already says what was deployed, and a test that
reads the document needs no branch.

**Leave them failing until Session 5.** Rejected. A red proof is indistinguishable
from a broken one after a week, and `SEC-NET-001` is a P0 boundary requirement.

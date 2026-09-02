# Architecture Decision Records

An ADR records a decision that is expensive to reverse, together with the
context that made it the right call. It is not a design document and not a
status report.

## When an ADR is required

- Changing anything frozen in runbook §4 (product shape, requirement ID
  prefixes, the example domain, configuration authority, the generated
  endpoint rule, the acceptance-test lifecycle, the evidence lifecycle).
- Removing or weakening a P0 requirement.
- Changing the deterministic naming algorithm, the generated output schema,
  or the version-lock format.
- Resolving an ambiguity that is not already closed in
  `docs/plans/session-01-implementation-plan.md` §2.

That last rule is the important one. An ambiguity discovered during
implementation does not get settled inline in whichever file happened to
surface it. It comes back here.

## Numbering

Sequential, zero-padded to four digits, never reused. A superseded ADR keeps
its number and gains a `Superseded by` line; it is not deleted, because the
reasoning that led to the original choice is usually the reason the
replacement is correct.

## Template

```markdown
# NNNN — Short imperative title

- **Status:** Proposed | Accepted | Superseded by [NNNN](NNNN-slug.md)
- **Date:** YYYY-MM-DD
- **Session:** N
- **Affects:** requirement IDs, or "none"

## Context

What forced a decision. Include the constraint that made the obvious option
wrong, if there was one.

## Decision

The commitment, stated so that a reader can tell whether a given piece of
code complies with it.

## Consequences

What this makes easy, what it makes hard, and what it forecloses. Name the
tests that enforce it.

## Alternatives considered

Each with the reason it was not chosen. "We didn't think of it" is a valid
entry when discovered later.
```

## Index

Every file matching `NNNN-*.md` in this directory must appear below. An
unlisted ADR is one nobody reads, and `0004` went unlisted for a session.

| ADR | Title | Session | Status |
|---|---|---|---|
| [0001](0001-product-shape.md) | Product shape is a one-project-per-deployment appliance | 1 | Accepted |
| [0002](0002-configuration-authority.md) | Configuration authority and transactional rendering | 1 | Accepted |
| [0003](0003-example-domain.md) | Frozen example domain | 1 | Accepted |
| [0004](0004-version-lock-format.md) | Version lock format and offline verification | 1 | Accepted |
| [0005](0005-route-reservation.md) | Reserved routes and segment-wise overlap | 1 | Accepted |
| [0006](0006-capability-scopes.md) | Approved scope vocabulary lives in the capability schema | 1 | Accepted |
| [0007](0007-bounds-authority.md) | The project schema is the sole authority for numeric bounds | 1 | Accepted |
| [0008](0008-sensitive-key-policy.md) | Sensitive key detection by terminal token, never substring | 1 | Accepted |
| [0009](0009-host-and-edge-plane.md) | Host configuration is separate, and one edge plane is shared | 2 | Accepted |
| [0010](0010-secret-materialization.md) | Secrets are individual files in immutable generations | 2 | Accepted |
| [0011](0011-provider-bootstrap-state.md) | Provider ownership is recorded by ID, and convergence is keyed narrowly | 2 | Accepted |
| [0012](0012-output-document-kinds.md) | Two output document kinds under one versioned schema | 2 | Accepted |
| [0013](0013-compose-wrapper-scopes.md) | Compose wrapper scopes, the runtime gate, and three env files | 2 | Accepted |
| [0014](0014-gate-scope-and-session-derivation.md) | The Session 1 gate measures Session 1's claims, at the session the tree targets | 2 | Accepted |
| [0015](0015-reserved-health-route.md) | The platform health route is reserved | 2 | Accepted |
| [0016](0016-absence-is-not-a-collision.md) | Two projects that both lack a facility do not collide | 2 | Accepted |
| [0017](0017-stub-lifecycle.md) | A stub that becomes real stops returning 10 | 2 | Accepted |
| [0018](0018-daemon-access-is-not-a-verdict.md) | A check that cannot reach the daemon reports that, not a verdict | 2 | Accepted |
| [0019](0019-query-strings-cannot-be-dropped.md) | Traefik cannot drop query strings, so the path goes instead | 2 | Accepted |
| [0020](0020-project-state-roots.md) | Configuration in /etc, generated output in /var/lib | 2 | Accepted |
| [0021](0021-flag-values-mistaken-for-subcommands.md) | A Compose flag's value can be mistaken for the subcommand | 2 | Accepted |
| [0022](0022-forbidden-list-drifted-behind-compose.md) | The forbidden list drifted behind the Compose surface it covers | 2 | Accepted |
| [0023](0023-isolation-proofs-read-the-edges-network-not-the-projects.md) | The isolation proofs read the edge's network, not the project's | 2 | Accepted |
| [0024](0024-a-contract-test-asserted-the-absence-of-a-real-host-path.md) | A contract test asserted the absence of a real host path | 2 | Accepted |
| [0025](0025-evidence-names-the-claim-not-the-suite.md) | Evidence names the claim, not the suite that ran | 2 | Accepted |
| [0026](0026-bootstrap-authority-is-separate-from-migration-authority.md) | Bootstrap authority is separate from migration authority | 3 | Accepted |
| [0027](0027-the-output-schema-gains-a-version-and-a-migration-path.md) | The output schema gains a version, and a migration path with it | 3 | Accepted |
| [0028](0028-source-migrations-are-templates-the-immutable-unit-is-the-rendered-payload.md) | Source migrations are templates; the immutable unit is the rendered payload | 3 | Accepted |
| [0029](0029-request-identity-is-a-trusted-transaction-local-claim.md) | Request identity is a trusted transaction-local claim, not an authenticated one | 3 | Accepted |
| [0030](0030-a-project-volume-carries-an-identity-and-a-mismatch-is-never-adopted.md) | A project volume carries an identity, and a mismatch is never adopted | 3 | Accepted |
| [0031](0031-exit-code-11-the-data-is-not-yours.md) | Exit code 11: the data is not yours | 3 | Accepted |
| [0032](0032-the-session-a-release-deploys-is-read-not-repeated.md) | The session a release deploys through is read, not repeated | 3 | Accepted |
| [0033](0033-a-declared-grant-surface-that-nothing-rendered.md) | A declared grant surface that nothing rendered | 3 | Accepted |
| [0034](0034-the-migration-plane-runs-a-container-and-assembles-its-own-url.md) | The migration plane runs a container, and assembles its own URL | 3 | Accepted |
| [0035](0035-a-check-that-could-not-fail.md) | A check that could not fail | 3 | Accepted |
| [0036](0036-the-provider-bootstrap-seeds-what-the-contract-declares.md) | The provider bootstrap seeds what the contract declares | 3 | Accepted |
| [0037](0037-an-installed-launcher-resolves-a-release-and-nothing-else.md) | An installed launcher resolves a release and nothing else | 3 | Accepted |
| [0038](0038-the-deployed-document-records-the-generation-it-verified.md) | The deployed document records the generation it verified, not the one that is current | 3 | Accepted |
| [0039](0039-a-claim-belongs-to-the-session-that-introduced-it.md) | A claim belongs to the session that introduced it | 3 | Accepted |
| [0040](0040-a-loopback-publication-is-not-a-public-port.md) | A loopback publication is not a public port | 4 | Accepted, superseded in part |
| [0041](0041-two-transports-three-access-profiles.md) | Two transports, three access profiles | 4 | Accepted |
| [0042](0042-host-port-allocation-is-state-keyed-by-the-volumes-identity.md) | Host port allocation is state, keyed by the identity the volume carries | 4 | Accepted, amended |
| [0043](0043-the-access-broker-is-a-release-reached-through-a-trampoline.md) | The access broker is a release, reached through a trampoline | 4 | Accepted, amended |
| [0044](0044-there-is-no-publication.md) | There is no publication | 4 | Accepted |
| [0045](0045-a-claim-is-shaped-by-where-it-can-be-measured.md) | A claim is shaped by where it can be measured | 4 | Accepted |
| [0046](0046-a-nologin-stub-is-a-fact-with-an-expiry-date.md) | A NOLOGIN stub is a fact with an expiry date | 4 | Accepted |
| [0047](0047-an-absence-proof-expires-when-a-later-session-supplies-the-thing.md) | An absence proof expires when a later session supplies the thing | 4 | Accepted |
| [0048](0048-the-example-domain-the-migrations-shipped.md) | The example domain the migrations shipped, and the one four documents describe | 5 | Accepted |
| [0049](0049-one-scope-vocabulary.md) | One scope vocabulary, and it lives in the capability schema | 5 | Accepted |
| [0050](0050-a-reviewed-api-surface-is-a-generated-artifact.md) | A reviewed API surface is a generated artifact with an update/check split | 5 | Accepted |
| [0051](0051-the-bootstrap-issuer-is-temporary-and-carries-its-own-expiry.md) | The bootstrap issuer is temporary, asymmetric, and carries its own expiry | 5 | Accepted |
| [0052](0052-the-pre-request-function-is-the-one-private-object-a-request-role-may-reach.md) | The pre-request function is the one private object a request role may reach | 5 | Accepted |
| [0053](0053-outputs-version-5.md) | Outputs version 5: the deployed document carries the public surface and the identity the broker needs | 5 | Accepted |
| [0054](0054-a-secret-may-be-consumed-by-the-root-plane.md) | A secret may be consumed by the root plane, and says so | 5 | Accepted |
| [0055](0055-the-contract-declares-what-kind-of-value-a-secret-is.md) | The contract declares what kind of value a secret is | 5 | Accepted |
| [0056](0056-a-consumer-declares-the-format-its-file-is-written-in.md) | A consumer declares the format its file is written in | 5 | Accepted |
| [0057](0057-the-public-error-contract-is-a-sqlstate-the-function-chooses.md) | The public error contract is a SQLSTATE the function chooses | 5 | Accepted |
| [0058](0058-a-bound-the-published-document-cannot-carry-is-not-a-bound.md) | A bound the published document cannot carry is not a bound | 5 | Accepted |
| [0059](0059-a-route-boundary-is-a-segment-boundary.md) | A route boundary is a segment boundary, and the obvious spelling is not one | 5 | Accepted |
| [0060](0060-a-published-method-is-not-a-granted-one.md) | A published method is not a granted one, and the snapshot records what is served | 5 | Accepted |
| [0061](0061-a-published-route-names-the-page-not-the-root.md) | A published route names the page, not the root above it | 5 | Accepted |
| [0062](0062-a-required-interpolation-has-two-spellings.md) | A required interpolation has two spellings, and which one is not a style choice | 5 | Accepted |
| [0063](0063-a-service-that-authenticates-as-a-project-role-starts-after-the-bootstrap-plane.md) | A service that authenticates as a project role starts after the bootstrap plane | 5 | Accepted |
| [0064](0064-a-sensitive-key-may-name-a-file-when-the-file-is-public.md) | A sensitive-looking key may name a file, when the file is public and the path is declared | 5 | Accepted |
| [0065](0065-a-version-is-not-a-configuration.md) | A version is not a configuration, and a measured set records both | 5 | Accepted |
| [0066](0066-a-rig-is-a-second-configuration-of-the-product.md) | A rig is a second configuration of the product, and the two must be tied together | 5 | Accepted |
| [0067](0067-a-validated-value-must-reach-the-plane-that-applies-it.md) | A validated value must reach the plane that applies it | 5 | Accepted |
| [0068](0068-the-pre-request-hook-carries-the-roles-statement-timeout.md) | The pre-request hook carries the role's statement timeout | 5 | Accepted |
| [0069](0069-the-documentation-page-is-a-first-party-build-under-our-own-csp.md) | The documentation page is a first-party build under our own CSP | 5 | Accepted |
| [0070](0070-the-connection-budget-is-divided-not-granted-twice.md) | The connection budget is divided, not granted twice | 5 | Accepted |
| [0071](0071-a-read-only-diagnostic-surface-for-an-unprivileged-agent.md) | A read-only diagnostic surface for an unprivileged agent | 5 | Accepted |
| [0072](0072-a-service-identity-that-can-log-in-is-published.md) | A service identity that can log in is published | 5 | Accepted |
| [0073](0073-a-rendered-fixture-is-current-or-it-is-absent.md) | A rendered fixture is current, or it is absent | 5 | Accepted |
| [0074](0074-a-session-scoped-proof-reads-the-session-from-the-deployment.md) | A session-scoped proof reads the session from the deployment | 5 | Accepted |
| [0075](0075-a-proof-names-a-secret-not-the-file-it-lands-in.md) | A proof names a secret, not the file it lands in | 6 | Accepted |
| [0076](0076-the-bootstrap-signing-key-rotates-by-cutover.md) | The bootstrap signing key rotates by cutover, and the overlap is unbuilt | 6 | Accepted |
| [0077](0077-a-package-entry-is-dereferenced-like-an-image.md) | A package entry is dereferenced like an image | 6 | Accepted |
| [0078](0078-the-claim-contract-and-its-two-verifiers.md) | The claim contract, and what each of its two verifiers enforces | 6 | Accepted |
| [0079](0079-the-scope-vocabulary-has-two-closed-classes.md) | The scope vocabulary has two closed classes, in one authority | 6 | Accepted |
| [0080](0080-a-check-constraint-passes-when-its-expression-is-null.md) | A CHECK constraint passes when its expression is NULL | 6 | Accepted |
| [0081](0081-the-frozen-argon2id-profile-is-checked-on-the-stored-hash.md) | The frozen Argon2id profile is checked on the stored hash | 6 | Accepted |
| [0082](0082-the-auth-memory-limit-is-a-derived-claimant.md) | The auth service's memory limit is a derived claimant | 6 | Accepted |
| [0083](0083-the-lock-names-what-it-can-dereference-and-what-is-a-choice.md) | The lock names what it can dereference, and what is actually a choice | 6 | Accepted |
| [0084](0084-the-pure-contract-lives-in-the-build-context.md) | The pure contract lives in the build context, and the repository imports it | 6 | Accepted |
| [0085](0085-a-route-lives-with-its-backend-and-that-is-the-cheaper-failure.md) | A route lives with its backend, and that is the cheaper failure | 6 | Accepted |
| [0086](0086-a-rotated-credential-has-to-change-the-parsed-configuration.md) | A rotated credential has to change the parsed configuration | 6 | Accepted |
| [0087](0087-both-documentation-surfaces-strip-the-root-and-the-page-redirects.md) | Both documentation surfaces strip the root, and the page redirects | 6 | Accepted |
| [0088](0088-a-verifier-acknowledges-by-being-recreated.md) | A verifier acknowledges by being recreated | 6 | Accepted |
| [0089](0089-a-claim-is-built-from-its-own-sessions-requirement-ids.md) | A claim is built from its own session's requirement IDs | 6 | Accepted |
| [0090](0090-an-expiry-clause-is-keyed-to-the-event-not-to-the-session.md) | An expiry clause is keyed to the event, not to the session | 6 | Accepted |
| [0091](0091-a-released-migration-that-cannot-apply-is-corrected-in-place.md) | A released migration that cannot apply is corrected in place | 6 | Accepted |
| [0092](0092-the-auth-service-reaches-the-cluster-directly.md) | The auth service reaches the cluster directly | 6 | Accepted |
| [0093](0093-an-operator-command-reaches-service-logic-through-a-container.md) | An operator command reaches service logic through a container | 6 | Accepted |
| [0094](0094-a-tokens-kid-is-derived-from-the-key-that-signed-it.md) | A token's `kid` is derived from the key that signed it | 6 | Accepted |
| [0095](0095-a-subject-in-a-token-is-the-identity-registrys-to-assert.md) | A subject in a token is the identity registry's to assert | 6 | Accepted |
| [0096](0096-a-boundary-assertion-is-re-derived-not-relaxed.md) | A boundary assertion is re-derived, not relaxed | 6 | Accepted |
| [0097](0097-a-structural-refusal-is-400-and-says-nothing.md) | A structural refusal is 400 and says nothing | 6 | Accepted |
| [0098](0098-the-issuers-published-set-is-not-the-verifiers-set.md) | The issuer's published set is not the verifier's set | 6 | Accepted |
| [0099](0099-the-budget-is-divided-four-ways-and-the-remainder-covers-the-pool.md) | The budget is divided four ways, and the remainder must cover the pooler's pool | 7 | Accepted |
| [0100](0100-the-scope-vocabulary-has-three-classes-and-they-partition-it.md) | The scope vocabulary has three classes, and they partition the union | 7 | Accepted |
| [0101](0101-one-image-two-modes-and-the-secret-contract-is-the-boundary.md) | One image, two modes, and the secret contract is the boundary | 7 | Accepted |
| [0102](0102-the-object-key-is-one-derivation-over-the-prefix-naming-owns.md) | The object key is one derivation over the prefix `naming` owns | 7 | Accepted |
| [0103](0103-where-a-value-comes-from-is-not-what-kind-of-value-it-is.md) | Where a value comes from is not what kind of value it is | 7 | Accepted |
| [0104](0104-the-lease-is-the-correctness-mechanism-and-the-row-lock-is-not.md) | The lease is the correctness mechanism, and the row lock is not | 7 | Accepted |
| [0105](0105-the-bucket-carries-the-namespace-every-other-derived-name-carries.md) | The bucket carries the namespace every other derived name carries | 7 | Accepted |
| [0106](0106-the-account-is-an-operator-input-and-the-endpoint-is-derived-from-it.md) | The account is an operator input, and the endpoint is derived from it | 7 | Accepted |
| [0107](0107-the-addressing-style-is-path-because-it-is-the-only-invariant-one.md) | The addressing style is `path`, because it is the only invariant one | 7 | Accepted |
| [0108](0108-a-nested-route-is-ordered-by-rule-length-and-the-ordering-is-derived.md) | A nested route is ordered by rule length, and the ordering is derived | 7 | Accepted |
| [0109](0109-the-cors-middleware-is-a-label-and-it-instructs-a-browser-rather-than-controlling-access.md) | The CORS middleware is a label, and it instructs a browser rather than controlling access | 7 | Accepted |
| [0110](0110-the-bucket-administering-credential-is-not-an-s3-credential.md) | The bucket-administering credential is not an S3 credential | 7 | Accepted |
| [0111](0111-an-object-is-collectable-only-once-nothing-can-still-write-to-its-key.md) | An object is collectable only once nothing can still write to its key | 7 | Accepted |
| [0112](0112-the-application-reference-is-one-document-and-it-describes-the-surface.md) | The application reference is one document, and it describes the surface | 7 | Accepted |
| [0113](0113-a-verifier-that-issues-nothing-reads-its-key-set-from-the-rendered-file.md) | A verifier that issues nothing reads its key set from the rendered file | 7 | Accepted |
| [0114](0114-the-application-api-accepts-only-access-tokens.md) | The application API accepts only access tokens | 7 | Accepted |
| [0115](0115-the-agent-plane-accepts-only-agent-tokens.md) | The agent plane accepts only agent tokens | 8 | Accepted |
| [0116](0116-session-8-activates-the-agent-reader-role.md) | Session 8 activates the agent-reader role | 8 | Accepted |
| [0117](0117-an-agent-request-runs-under-its-owners-identity.md) | An agent request runs under its owner's identity | 8 | Accepted |
| [0118](0118-the-agent-planes-rpcs-are-reviewed-and-unpublished.md) | The agent plane's RPCs are reviewed and unpublished | 8 | Accepted |
| [0119](0119-an-operation-id-is-derived-because-postgrest-publishes-none.md) | An operation id is derived, because PostgREST publishes none | 8 | Accepted |
| [0120](0120-a-tool-may-be-backed-by-more-than-one-capability.md) | A tool may be backed by more than one capability | 8 | Accepted |
| [0121](0121-the-agent-plane-is-a-third-mode-of-the-one-application-image.md) | The agent plane is a third mode of the one application image | 8 | Accepted |
| [0122](0122-the-verifier-roster-is-a-table-and-every-verifier-is-in-it.md) | The verifier roster is a table, and every verifier is in it | 8 | Accepted |
| [0123](0123-the-published-protocol-revision-is-the-highest-the-runtime-implements.md) | The published protocol revision is the highest the runtime implements | 8 | Accepted |
| [0124](0124-the-transport-guard-is-about-the-trust-anchor-not-the-transport.md) | The transport guard is about the trust anchor, not the transport | 8 | Accepted |
| [0125](0125-the-agent-plane-forwards-the-callers-own-token-and-resolves-context-once.md) | The agent plane forwards the caller's own token, and resolves context once | 8 | Accepted |
| [0126](0126-the-runtime-dials-the-internal-upstream-and-the-lock-names-the-public-surface.md) | The runtime dials the internal upstream; the lock names the public surface | 8 | Accepted |
| [0127](0127-a-caller-value-is-a-value-and-the-request-is-built-from-the-lock.md) | A caller value is a value, and the request is built from the lock | 8 | Accepted |
| [0128](0128-the-agent-plane-publishes-one-path-and-its-health-is-private-by-absence.md) | The agent plane publishes one path, and its health is private by absence | 8 | Accepted |
| [0129](0129-the-four-budgets-are-bounded-independently-and-concurrency-is-a-share-of-the-pool.md) | The four budgets are bounded independently, and concurrency is a share of the pool | 8 | Accepted |
| [0130](0130-a-refusal-reaches-the-caller-only-through-tool-error.md) | A refusal reaches the caller only through ToolError | 8 | Accepted |
| [0131](0131-the-agent-plane-memory-limit-is-a-choice-with-a-measured-floor.md) | The agent plane's memory limit is a choice with a measured floor, and it gets no validator | 8 | Accepted |
| [0132](0132-session-eights-requirements-gain-live-proofs-and-four-new-ids-carry-the-deployed-guarantees.md) | Session 8's requirements gain live proofs, and four new ids carry the deployed guarantees | 8 | Accepted |
| [0133](0133-a-service-is-deferred-for-two-reasons-and-the-deploy-proves-its-mounts-exist.md) | A service is deferred for two reasons, and the deploy proves its mounts exist | 8 | Accepted |
| [0134](0134-a-grant-assertion-reads-the-catalog-and-a-reach-assertion-sets-the-role.md) | A grant assertion reads the catalog, and a reach assertion sets the role | 8 | Accepted |
| [0135](0135-an-audit-record-is-written-by-a-definer-function-as-the-caller.md) | An audit record is written by a definer function, as the caller, and the hook cannot write one | 9 | Accepted |
| [0136](0136-an-agent-plane-function-that-writes-takes-arguments-and-is-post-only.md) | An agent-plane function that writes takes arguments, and GET refuses it | 9 | Accepted |
| [0137](0137-session-9-activates-the-agent-writer-role-and-the-anchor-must-not-expire.md) | Session 9 activates agent_writer, and an anchor that expires is not an anchor | 9 | Accepted |
| [0138](0138-the-write-agents-ceiling-gains-meta-read.md) | A write agent may hold meta:read | 9 | Accepted |
| [0139](0139-a-write-refusal-is-translated-from-the-products-errcode-never-relayed.md) | A write refusal is translated from the product's own errcode, never relayed | 9 | Accepted |
| [0140](0140-discovery-filters-tool-names-and-hiding-a-name-is-not-a-boundary.md) | Discovery filters tool names, and hiding a name is not a boundary | 9 | Accepted |
| [0141](0141-a-write-fails-closed-on-its-audit-record-and-a-read-does-not.md) | A write fails closed on its audit record, and a read does not | 9 | Accepted |
| [0142](0142-the-audit-record-has-one-reader-and-it-is-a-definer-function.md) | The audit record has one reader, it is a definer function, and reading it is its own scope | 9 | Accepted |
| [0143](0143-a-query-string-is-parsed-strictly-like-a-request-body.md) | A query string is parsed strictly, for the same measured reason a request body is | 9 | Accepted |
| [0144](0144-the-archiver-is-installed-into-the-database-image-not-copied-into-it.md) | The archiver is installed into the database image, not copied into it | 10 | Accepted |
| [0145](0145-the-backup-repository-is-a-bucket-of-its-own.md) | The backup repository is a bucket of its own, with its own credential and its own key | 10 | Accepted |
| [0146](0146-outputs-version-13.md) | Outputs version 13, and why the observation is a block of its own | 10 | Accepted |
| [0147](0147-the-database-reaches-its-repository-over-an-egress-network-of-its-own.md) | The database reaches its repository over an egress network of its own | 10 | Accepted |
| [0148](0148-what-a-backup-identity-holds-and-the-fifth-claimant.md) | What a backup identity holds, and the fifth claimant on one budget | 10 | Accepted |
| [0149](0149-the-backup-command-and-what-a-repository-can-honestly-report.md) | The backup command, step 6c, and what a repository can honestly report | 10 | Accepted |
| [0150](0150-a-broken-archiver-is-visible-without-taking-the-database-down.md) | A broken archiver is visible, and it does not take the database down | 10 | Accepted |
| [0151](0151-the-restore-drill-is-disposable-by-construction.md) | The restore drill is disposable by construction, not by care | 10 | Accepted |
| [0152](0152-what-a-restore-drill-can-honestly-report.md) | What a restore drill can honestly report | 10 | Accepted |
| [0153](0153-the-archiver-reads-its-credential-from-a-config-include.md) | The archiver reads its credential from a config include, not from an environment | 10 | Accepted |
| [0154](0154-the-render-decides-a-rendered-files-mode-and-the-install-decides-its-owner.md) | The render decides a rendered file's mode; the install decides its owner | 10 | Accepted |
| [0155](0155-a-deploy-recreates-a-container-whose-mounted-content-changed.md) | A deploy recreates a container whose mounted content changed | 10 | Accepted |
| [0156](0156-a-refusal-that-arrives-mid-write-is-still-a-refusal.md) | A refusal that arrives mid-write is still a refusal | 10 | Accepted |
| [0157](0157-a-preflight-reports-every-absent-prerequisite-and-changes-nothing.md) | A preflight reports every absent prerequisite, and says so when it did not look | 11 | Accepted |
| [0158](0158-the-deployed-document-is-the-address-book-not-the-diagnosis.md) | The deployed document is the address book, not the diagnosis | 11 | Accepted |
| [0159](0159-verbose-adds-resolution-never-a-third-partys-bytes.md) | `--verbose` adds resolution, never a third party's bytes | 11 | Accepted |
| [0160](0160-the-request-id-flows-outward-and-no-caller-value-is-trusted.md) | The request id flows outward, and no caller value is ever trusted | 11 | Accepted |
| [0161](0161-the-database-row-records-the-request-and-a-malformed-header-is-not-a-refusal.md) | The `database` row records the request, and a malformed header is not a refusal | 11 | Accepted |
| [0162](0162-what-a-template-version-bump-permits-and-what-rollback-means.md) | What a `template_version` bump permits, and what rollback does not mean | 13 | Accepted |
| [0163](0163-a-skipped-proof-is-not-a-failed-one.md) | A skipped proof is not a failed one | 13 | Accepted |
| [0164](0164-the-project-metrics-surface-is-per-project-parameterless-and-not-public.md) | The project metrics surface is per project, parameterless, and not public | 14 | Accepted |
| [0165](0165-a-telemetry-component-carries-an-explicit-memory-limit.md) | A telemetry component carries an explicit memory limit, because its default is a share of somebody else's machine | 14 | Accepted |
| [0166](0166-the-trace-id-is-the-request-id-and-a-span-carries-only-what-it-was-given.md) | The trace id is the request id, and a span carries only what it was given | 14 | Accepted |
| [0167](0167-a-metric-reads-from-the-decision-that-owns-its-value-and-its-scope-is-an-enumeration.md) | A metric reads from the decision that owns its value, and its scope is an enumeration | 14 | Accepted |

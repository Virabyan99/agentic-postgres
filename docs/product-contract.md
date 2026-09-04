# Product contract

This document freezes what the product is, what it is not, and which
guarantees are release-blocking. It is the reference every later session is
measured against.

Two of its sections are **generated** and must not be hand-edited. See
"Generated sections" at the end for why, and for how to regenerate them.

---

## 1. Product definition

A reusable, isolated, one-project-per-deployment PostgreSQL appliance and
template. One deployment serves exactly one project. Project isolation is a
property of the deployment topology, not of application correctness.

A deployment provides, when complete:

- A PostgreSQL database with row-level ownership enforced in the database.
- Pooled and direct connection endpoints, each with a documented use.
- A REST surface (PostgREST) and an application API (FastAPI) behind a single
  edge router.
- A narrow, explicitly enumerated agent capability surface (MCP) that is a
  strict subset of the API surface.
- Object storage scoped to the project.
- Point-in-time backup and a rehearsed, verified restore path.

See [0001 — Product shape](decisions/0001-product-shape.md).

## 2. The intended boundary — "low-effort wins toward Neon / Prisma Postgres"

This project is not attempting to be Neon or Prisma Postgres. It is
attempting to capture the parts of their developer experience that are cheap
to reproduce on a single owned host, and to be explicit about the parts that
are not.

**In the boundary — worth reproducing:**

- One command renders a complete, valid project configuration from a single
  non-secret manifest.
- Pooled and direct connection strings that work with unmodified Prisma,
  `psql`, and standard drivers, with the pooled/direct distinction made
  explicit rather than discovered through a migration failure.
- Migrations that run against the direct endpoint without special
  configuration.
- Deterministic, collision-free project identities, so a second project on
  the same host cannot reach the first.
- A restore that is rehearsed rather than assumed.

**Outside the boundary — deliberately not reproduced:**

- Autoscaling, scale-to-zero, and compute/storage separation.
- Instant branching and copy-on-write database forks.
- A hosted control plane, web console, or multi-region availability.
- Managed failover. Recovery here is restore-based and has a real RTO.

The honest summary: this gives a small team most of the *ergonomics* of a
managed Postgres on infrastructure they control, and none of the *elasticity*.

## 3. Requirement catalog

Requirement IDs are stable and are used identically in this document, in
`tests/acceptance-registry.yaml`, in `docs/threat-model.md`, in test markers,
and in the roadmap.

| Prefix | Area |
|---|---|
| `DEP` | Deployment, bootstrap, and project isolation |
| `CFG` | Manifests, naming, rendering, and generated configuration |
| `DBX` | Database endpoints and client compatibility |
| `SEC` | Authorization, credentials, and security boundaries |
| `API` | PostgREST and FastAPI contracts |
| `AGT` | MCP and agent behavior |
| `STO` | Object storage |
| `REC` | Backup and recovery |
| `OPS` | Health, diagnostics, logging, and operations |
| `DX` | Developer experience and documentation |

Priorities:

- **P0** — release-blocking. May not exist only as prose; each has at least
  one collectible Pytest node ID.
- **P1** — important, not release-blocking. Deferral requires evidence.
- **P2** — optional capability.

<!-- BEGIN GENERATED: requirements -->
<!-- Generated from tests/acceptance-registry.yaml by
     bin/render-acceptance-matrix.py --write. Do not hand-edit. -->

**P0 — 143 requirements**

| ID | Session | Guarantee |
|---|---:|---|
| `CFG-001` | 1 | A project manifest validates against schema and semantics, and contains no secret material. |
| `CFG-002` | 1 | Ambiguous YAML is rejected outright rather than resolved silently. Default PyYAML keeps the last value for a duplicate key. |
| `CFG-003` | 1 | Every identity is derived deterministically and per-context, and no PostgreSQL role can exceed 63 bytes regardless of input length. |
| `CFG-004` | 1 | Identical inputs render byte-identical output, in the same process and across processes, with no timestamp anywhere in the document. |
| `CFG-005` | 1 | Generated output conforms to its schema, records real input digests, and represents nonexistent endpoints as unavailable rather than as placeholders. |
| `CFG-006` | 1 | Every generated file is mode 0600, independent of the process umask. |
| `CFG-007` | 1 | A render that fails validation or publication leaves the previous valid render byte-identical and removes its staging directory. |
| `CFG-008` | 1 | The renderer refuses symlinked inputs and output targets. |
| `CFG-009` | 1 | Secret-bearing keys are rejected in manifests and in output, without false positives for safe reference names such as password_secret_ref. |
| `CFG-010` | 1 | A publicly exposed pooler is not a supported profile: pooled_public must be false and its allowlist empty, and the refusal names the supported path. See ADR 0040. |
| `CFG-011` | 1 | Route trees may not collide with a reserved route or with each other, and overlap is decided segment-wise rather than by string prefix. |
| `CFG-012` | 1 | Two similar projects render fully disjoint identities, compared over parsed semantic fields rather than by duplicate-string search. |
| `CFG-013` | 1 | The capability surface is exactly the reviewed set and no more, is compiled against a live backing contract rather than trusted, cannot declare a backend it does not reach, and cannot express SQL or a raw query. |
| `CFG-014` | 1 | Container images are pinned to immutable digests for one declared platform, Python dependencies are hash-locked, and drift is detected offline. |
| `CFG-015` | 1 | The Compose model renders the exact resource names published in outputs.json, cannot be overridden by inherited environment variables, and refuses to start a container in Session 1. |
| `DX-002` | 1 | Operator commands document themselves, obey the exit-code convention, work from any directory, and never print the environment. |
| `DX-003` | 1 | The repository has its required shape, generated output stays out of Git, and no deployable source file hard-codes a fixture identity. |
| `CFG-016` | 2 | The deployed document is a distinct owner-only document kind that records observed host state, cannot be produced by migrating a rendered one, and is never accepted where a rendered document is required. |
| `DEP-ISO-002` | 2 | Two projects sharing one host and one edge share no route, network, or ingress attachment, and stopping one leaves the other served. |
| `DEP-PROV-001` | 2 | Provider ownership is recorded by identifier rather than by name, and re-applying the bootstrap converges without creating a second identity. |
| `DEP-REL-001` | 2 | What systemd runs is an immutable root-owned release identified by commit, never a checkout, so switching a branch cannot change what starts next boot. |
| `OPS-HEALTH-001` | 2 | Every deployed project answers the reserved health route with its own project key, through the edge only, and no unrouted path is served. |
| `SEC-DOCKER-001` | 2 | The publicly reachable proxy reads the Docker API through an allowlisting socket proxy that refuses every write, and the daemon itself is reachable over no network socket. |
| `SEC-HOST-001` | 2 | The host admits key-based SSH only, refuses root and password logins as OpenSSH actually resolves them, patches itself without rebooting itself, and exposes no public listener beyond SSH and the edge. |
| `SEC-LOG-001` | 2 | No request query-string value and no request header value reaches the edge access log, proved by sending a value nothing else could produce and then looking for it in a log known to be recording the request. |
| `SEC-NET-001` | 2 | No public route reaches the direct PostgreSQL endpoint: nothing listens on it, no forwarded path carries it, and a full-TCP connect scan from another network finds it closed while 443 is open. |
| `SEC-NET-002` | 2 | Only the edge publishes a host port, and forwarded public traffic to anything else is dropped by a DOCKER-USER policy that matches the pre-DNAT destination port rather than the container's. |
| `SEC-SECRET-001` | 2 | Secret values appear in no image, repository file, Compose output, log, or evidence file, proved by searching for a real value rather than by asserting that none was written. |
| `SEC-SECRET-002` | 2 | A materialized secret is a mode 0400 file owned by its declared consumer, mounted into that service and no other, proved by the mount list rather than by comparing digests of what each service read. |
| `SEC-TLS-001` | 2 | The public origin serves TLS 1.2 or better with a certificate a default trust store accepts, permanently redirects plaintext, and serves the exact certificate the deployed document records. |
| `DBX-MIG-001` | 3 | Bootstrap authority and migration authority are distinct and least privileged. Proved from the membership option columns, not from the role's own INHERIT attribute. See ADR 0026. |
| `DBX-MIG-002` | 3 | Rendering a migration twice from one input produces identical bytes, and those bytes agree with the committed released lock. See ADR 0028. |
| `DBX-MIG-003` | 3 | An applied migration cannot be silently edited, removed, or reordered; the preflight refuses on any disagreement between its five sources. |
| `DBX-PG-001` | 3 | The locked PostgreSQL 18 image runs with pgvector present at the locked version, in the extensions schema rather than in public. |
| `DBX-PG-002` | 3 | PostgreSQL publishes no host port, joins no edge network, and carries no Traefik label. It is reachable only on its own project network. |
| `DBX-PG-003` | 3 | An existing data volume is bound to one project identity, and a mismatch is refused with exit 11 rather than adopted. See ADR 0030. |
| `DEP-BOOT-001` | 3 | A project restarted by systemd, or restored after a reboot, comes back from the release its deployed document records, through the session that document records, with its cluster identity and applied migrations intact. |
| `DEP-ISO-003` | 3 | Two deployed projects have isolated clusters, volumes, roles, credentials and identity sentinels, and neither project's credential authenticates against the other. |
| `SEC-DB-001` | 3 | No runtime role holds SUPERUSER, CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS. Read from the catalog, never inferred from how a role was created. |
| `SEC-DB-002` | 3 | The public, app and app_private schema boundaries match the contract. No API role can address `app`. `app_private` is nameable by exactly the two roles PostgREST impersonates, which reach one function in it and no data at all (ADR 0052); every other role, including the ones no token can name, cannot address it. |
| `SEC-DEFAULT-001` | 3 | Default EXECUTE on newly created functions is revoked from PUBLIC, for every function in `api` rather than for a named pair -- and the published document follows a PUBLIC grant, so a function that kept the default would be advertised to an anonymous caller. |
| `SEC-FUNC-001` | 3 | An API role cannot execute a function it was not explicitly granted. |
| `SEC-OWNER-001` | 3 | Objects are owned by a non-login role that no service connects as. |
| `SEC-RLS-001` | 3 | A user can neither read nor mutate another user's rows. |
| `SEC-VIEW-001` | 3 | A security-invoker view preserves the underlying row policy. |
| `DBX-001` | 4 | Prisma Migrate runs through the direct endpoint. |
| `DBX-002` | 4 | Prisma Client operates through the pooled endpoint. |
| `DBX-003` | 4 | psql connects through both the direct and pooled endpoints. |
| `DBX-005` | 4 | The direct endpoint is not publicly reachable. |
| `DBX-POOL-001` | 4 | The pooler runs in transaction mode with explicit, bounded limits and non-zero prepared-statement tracking, read from its own configuration rather than from the file that was meant to produce it. |
| `DBX-POOL-002` | 4 | More clients than the server-connection budget complete their transactions, and the number of server connections is observed never to exceed it. |
| `DBX-POOL-003` | 4 | A protocol-level named prepared statement is reusable after the pooler has moved the client to a different backend, proved by observing the backend change rather than by assuming it. |
| `DBX-PORT-001` | 4 | Host-loopback allocations are stable across redeploy, restart and reboot, two projects never share one, and an allocation is matched by the instance UUID the volume carries. See ADR 0042. |
| `DEP-ISO-004` | 4 | Two projects have distinct pooled and direct ports, credentials, pooler configuration and user lists, and neither project's credential opens the other. |
| `DX-DB-001` | 4 | The connection helper opens and cleans a verified tunnel for each transport, refuses an unverified host key, and prints no credential. |
| `DX-DB-002` | 4 | The access broker enforces project and profile authorization and returns nothing to an unauthorized caller. Past the trampoline it decides authorization before reading anything about the project, so "no such project" and "not yours" are one refusal: the same exit code and the same message, naming neither the project nor the profile. The trampoline itself has to resolve the release from the deployed document before there is any policy to consult, so project-key existence stays visible to an account already named in the sudoers rule -- sudo is the coarse gate, the policy is the fine one. Narrowed from "no distinction anywhere" by ADR 0043's amendment on acceptance, because the original claim was true of the broker and could never be true of the trampoline. |
| `SEC-DBX-001` | 4 | Neither transport is reachable from a non-loopback address; every publication carries an explicit loopback host_ip and only the edge publishes a public port. See ADR 0040. |
| `SEC-DBX-002` | 4 | The application runtime role holds no ownership, no base-schema addressability and no DDL, and cannot become any other role. |
| `SEC-DBX-003` | 4 | Transaction-local claim state, and deliberately set session-level state, are both absent for the next client of a released pooled connection. |
| `SEC-DBX-004` | 4 | A rotated application credential is replaced in both planes: the generation the project points at opens the pooled and the direct transport, and the generation it replaced opens neither. The split-brain state - PostgreSQL holding one password while the pooler holds another - passes a test of either transport taken alone, so all four combinations are measured in one run. See the Session 4 plan, section 4.3. |
| `API-CACHE-001` | 5 | An API migration reloads the schema cache and updates OpenAPI. |
| `API-CONTRACT-001` | 5 | The live OpenAPI, normalized, equals the committed snapshot, and the snapshot equals the reviewed API-surface allowlist; an unlisted object in the api schema fails the gate. |
| `API-ERR-001` | 5 | The public error contract is stable and discloses no SQL, role name, schema path, internal hint, or another owner's row. |
| `API-LIMIT-001` | 5 | Row limits and timeouts are enforced by the server, not the client. |
| `API-REST-001` | 5 | HTTP reads reproduce the database's row-level result exactly: a caller sees its own rows and none of another's, and the same query run directly against the database agrees. |
| `API-RPC-001` | 5 | The write surface is exactly the named RPCs; generic table and view writes are refused, ownership is derived rather than accepted, and each call changes at most one row. |
| `API-SCHEMA-001` | 5 | Only the api schema is exposed, matching a committed allowlist. |
| `DEP-ISO-005` | 5 | Two projects have distinct routes, authenticator credentials, issuers, audiences, keys, snapshots and documentation credentials, and neither's token or credential works against the other. |
| `DX-API-001` | 5 | The request broker performs an authorized call without a token reaching argv, stdout, shell history, a log, or evidence. |
| `SEC-ANON-001` | 5 | The anonymous role cannot reach protected resources. |
| `SEC-API-001` | 5 | From a network that is not the host: the REST route answers over HTTPS with the approved surface, the documentation route refuses without a credential, and nothing else of the API plane is reachable. |
| `SEC-BOOT-001` | 5 | The temporary bootstrap issuer signs with a private key no service holds, verifiers hold public material only, and the deployed document records the issuer as temporary against the session it was deployed through. A replaced signing key is accepted by nothing - by the plane and by the deployed document's verification_kids, which are two readings - and a rotated authenticator password opens the cluster for the running service and no longer opens it for the value it replaced. The signing key is replaced by cutover, not by a two-phase overlap: ADR 0076 measured that the overlap functions exist and nothing calls them. |
| `SEC-DOCS-001` | 5 | The documentation credential never reaches the documentation service, the served bytes carry no credential, and no API token is served to a browser. A rotated credential opens the page and the value it replaced does not. |
| `SEC-PRIV-001` | 5 | No API role can address the app or app_private schemas. |
| `SEC-ROLE-001` | 5 | Role switching cannot exceed the authenticator's granted memberships: a token naming an unactivated, privileged, or foreign-project role is refused. |
| `API-ADMIN-001` | 6 | Admin endpoints require an explicit scope, not a role name. Proved with the case a role check passes: a subject holding `project_admin` with the administrative scopes removed is refused, between an ordinary subject that is refused and the real administrator that is not -- without the third caller every refusal is consistent with an endpoint that does not exist. |
| `API-AUTH-001` | 6 | Login issues a short-lived token and `/auth/me` reflects CURRENT state rather than the token's copy of it, compared against an independent reading of the same record through the cluster. The four ways a login can fail -- unknown subject, wrong password, disabled subject, no credential -- are compared to each other rather than to a literal, because what the requirement buys is that they cannot be told apart. |
| `API-AUTH-002` | 6 | Strict input: duplicate JSON members, unknown fields, non-object roots, oversized bodies and unapproved JOSE headers are refused before any domain logic runs. The live half is the one no contract test can reach: `request.body()` reads every byte before the service's bound is applied (D273), so the edge carries the same number as a buffering middleware and an oversized request must be refused with 413 by Traefik rather than with 400 by the service. |
| `DEP-ISO-006` | 6 | Project A's tokens and admin session are refused by project B, and the two share no key, issuer, audience or role name. The refusal is read twice -- as a status, with B's own 401 to an unauthenticated request as the control that something is listening, and as a mechanism, by checking that the `kid` A's token names is absent from what B publishes. A distinct ID from DEP-ISO-003, whose reuse would resolve this claim to Session 3 and turn three earlier sessions' evidence red (ADR 0089). |
| `SEC-BOOT-002` | 6 | The first administrator is created only through the local protected path, exactly once, under a project advisory lock, and no public bootstrap endpoint exists -- an authenticated administrator cannot create a second one over HTTP either. A distinct ID from SEC-BOOT-001, which is about the temporary bootstrap ISSUER holding the only private key: one ID for two guarantees is what D47 refused (ADR 0089). The advisory-lock race itself was driven by hand in Run 8 and is recorded in the run log rather than raced against a live deployment. |
| `SEC-CRED-001` | 6 | Raw passwords and agent secrets never reach storage, logs, evidence, process arguments, image layers or database error detail. Measured against a value the test PLANTS, on both the success and the failure path: a scan for a password-shaped string finds nothing in a system that stores hashes and would pass equally against one that logs every password it receives. |
| `SEC-CRED-002` | 6 | The Argon2id profile is the frozen one, read back FROM THE ENCODED HASH rather than from the constructor's arguments. ADR 0081 measured that `PasswordHasher.verify()` returns True for a hash produced at a weaker profile and that `check_needs_rehash` reports the mismatch to nobody, so the profile is parsed out of the PHC string before the password is checked -- by a hand-written parser, because asking argon2 what argon2 just did is the same authority twice. |
| `SEC-JWT-001` | 6 | The negative matrix, asked of both verifiers. Wrong issuer, audience, algorithm, token type, `kid` or expiry is refused -- by the auth service, which signs, and by PostgREST, which verifies independently from a JWKS file it read at startup. The two are only two verifiers when something makes them read the same key set: until Run 10 nothing did, and every token the service issued would have been refused (D276). The expiry case carries the measured 30-second leeway rather than the nominal deadline (D241), so a token is live for 930s and not 900. |
| `SEC-KEY-001` | 6 | Verifying services hold public material only. The property is now per-service rather than global: the auth service IS an issuer and must hold its own key at 0400, while every other running container holds none and the bootstrap issuer's key stays in the root plane. The key set is compared in four readings -- the deployed document, what the issuer publishes, what the deploy wrote, and the bytes inside the PostgREST container -- because a JWKS replaced at a stable path leaves a running verifier holding the old inode (D278). |
| `SEC-KEY-002` | 6 | Prepare, acknowledge, promote, retire: promotion is blocked until every verifier has acknowledged the prepared public generation, and retirement may not run before the deadline. The transition itself is NOT exercised in Session 6 and that is a decision (ADR 0088): the transition is the first rotation the machinery exists for, and Session 6 builds the machinery rather than driving it. What the live proofs assert is everything that holds without starting one -- the deployed key state satisfies the model's own validator, no rotation is in flight, the acknowledgement record is null rather than empty, and the published set holds exactly the key that signs. That last one replaced a two-key assertion when ADR 0170 retired the bootstrap issuer: until Session 15 two live issuers filled the two-key ceiling, which was the reason no rotation could be prepared at all (D683). The slot is now free, so the ceiling is no longer the reason -- the scope of Session 6 is. |
| `SEC-REV-002` | 6 | Non-resurrection. Disable then re-enable, an authorization change then reverted, and a password change then reverted all leave a previously issued token refused. The re-enable case is the isolating one: role, scopes and status all end identical to what the token carries, so the only thing that can refuse it is `authz_version` -- Run 8's M5 showed the obvious construction stays green with that comparison deleted. A distinct ID from SEC-REV-001, which is Session 9's and is about denial through MCP (ADR 0089). |
| `DEP-ISO-007` | 7 | Two projects have distinct buckets, distinct object prefixes and distinct R2 credentials. Compared by digest, because credential-digest reports a SHA-256 precisely so a proof can assert two credentials differ without either existing outside a container. |
| `STO-AGENT-001` | 7 | Object storage is human-only (ADR 0100). An agent token is refused at every endpoint, and so is a registered human without the object scopes -- the second arm being what proves the successful proofs succeed because of the scope rather than because nothing is checked. |
| `STO-CRED-001` | 7 | The mounted credential reaches its own bucket and the operator surface has no bucket-administering verb to attempt (ADR 0110). Run 5 measured the refusals with the real token; the separation is now structural rather than scoped. |
| `STO-KEY-001` | 7 | Object keys are generated server-side and client keys are refused rather than ignored. The generated key matches the derived format (ADR 0102) and appears in no response body. |
| `STO-OWN-001` | 7 | A user cannot obtain a download URL for another user's object, and the refusal is indistinguishable from an id that never existed. The positive arm is not decoration: Run 6's mutation battery survived because every download proof asserted a refusal, so denying everybody left them all green. |
| `STO-PUBLIC-001` | 7 | From off-host, every storage endpoint refuses an anonymous caller with 401 and never 404 -- authentication precedes the ownership filter, so an anonymous prober cannot distinguish a real object id from an invented one. The container's own port is not publicly reachable, and the published path is the derived one. Measured with 443 asserted open and the route asserted answering first, because a negative from an instrument that can see nothing is not a boundary. A separate id from SEC-API-001 rather than a widening of it: a claim is measured in exactly one environment (ADR 0045) and widening would move a Session 5 claim into Session 7 through max() (ADR 0089). |
| `STO-SECRET-001` | 7 | The storage runtime holds no signing key and the auth runtime holds no R2 credential, read from inside each container rather than from the generation directory. Per-consumer materialization is what makes this a property of the filesystem rather than of anyone's discipline. |
| `STO-TOMB-001` | 7 | A committed tombstone precedes every later grant, and DELETE answers identically for moved, already-tombstoned and never-existed. What it does not claim is revocation of a URL already issued: nothing in this system can withdraw a presigned URL. |
| `STO-URL-001` | 7 | Neither a presigned URL's signature nor an object key reaches any sink: both service logs, both container inspections, the journal, or the deployed document. A canary created by the proof itself, so a hit is a leak rather than a coincidence. |
| `AGT-BUDGET-001` | 8 | Four budgets are enforced server-side and are bounded by four different mechanisms: rows by the lock's ceiling, which a caller's limit may only lower; serialized bytes by a runtime constant a caller cannot express at all; elapsed time by the tool's own timeout; and concurrency by a semaphore sized as a share of PostgREST's pool. A result exceeding a budget is refused rather than truncated, because a truncated page that does not say so is a wrong answer. Widened from two budgets to four in Run 9 (ADR 0132): Run 8 built the other two, and a description that outlives its node ids is D175's failure mode in the one file that is supposed to be authoritative. |
| `AGT-CRED-001` | 8 | The MCP container holds no database credential and no signing material, read off the RUNNING container rather than off the model that produced it -- D389 is a session lost to a value being right in the rendered document and forbidden in the deployed one. Its share of the connection budget is zero (D407) and that is asserted after a real read, so the plane has done the work that would open a connection if it were ever going to. |
| `AGT-DRIFT-001` | 8 | Adding an API operation does not expose an agent capability without an explicit capabilities.yaml change. Written the only way that means anything: a real operation is added to BOTH the reviewed surface and the approved OpenAPI snapshot, and the compiled bytes are asserted not to move. |
| `AGT-PLANE-001` | 8 | The agent plane is published at exactly one path, the deployed document says so, and the tool_count it publishes is the compiled contract's while a caller's own tools/list carries only the names that caller's scopes reach -- two numbers answering two questions (ADR 0140). Its health surface is private by the ABSENCE of a route rather than by a check -- both paths answer 200 on the container's own socket and sit outside the verifier (D442) -- and a request carrying any Origin is refused by this repository's own middleware, because the pinned framework has none (D441, ADR 0128). |
| `AGT-PUBLIC-001` | 8 | What a stranger reaches of the agent plane, measured from a network that is not the deployment host. The route answers and refuses an anonymous caller 401 without naming a tool; the health paths -- which answer 200 on the container's socket and are behind no verifier -- are not reachable at all; and the container's own port is not published. A separate id from SEC-API-001 for the reason STO-PUBLIC-001 was: widening a Session 5 id would withdraw a Session 5 claim from Session 5's evidence (ADR 0132). |
| `AGT-READ-001` | 8 | An agent read through MCP returns exactly the rows the identical PostgREST request returns for the same principal, because the adapter forwards the caller's own token and adds no filtering of its own. Stated as the property rather than as a comparison against a human's result, which D418 established is `permission denied` and must stay so: the report is agent-only, and a second opinion about which rows an owner may see would disagree with the database's the moment a policy moved. |
| `AGT-SCOPE-001` | 8 | Tool discovery is filtered by the caller's scopes, and a resource a caller cannot reach is refused when called rather than merely hidden from the list. The scope sets are a disjunction of conjunctions (D421), so a tool requiring two scopes is not advertised to a caller holding one. |
| `AGT-SQL-001` | 8 | No agent input accepts SQL, a SQL fragment, a raw query string, a path or a runtime-selected operation. Every part of an upstream request except the caller's values comes from the deployed lock, and each value is escaped for the one position it occupies -- percent-encoded as a scalar, and backslash-escaped and quoted as an `in` member, which is the rule measured against the locked PostgREST rather than the one convention suggests. |
| `AGT-TOKEN-001` | 8 | The agent plane accepts only `token_use: "agent"` and refuses before any lookup (ADR 0115), which is ADR 0114's mirror. Proved with two REAL tokens this deployment signed for subjects its registry holds, differing only in `token_use`, so the refusal is a property of the discriminator rather than of two arbitrary strings -- D417 is the standing reminder that a refusal can come from a missing GRANT and look identical. |
| `SEC-INJ-001` | 8 | An injection payload stays data and does not alter query structure. Asserted from the attacker's side, with full control of every input a caller supplies: a value cannot introduce a parameter, a fragment or a second list member; a column and an operator are refused against the lock's allowlist rather than escaped, because an identifier has no safe encoding. The control arm proves a benign value still produces a working filter. |
| `AGT-AUDIT-001` | 9 | Read, write, denied and failed attempts are audited with redaction, and ONE MCP write leaves TWO records that agree (D480, ADR 0135). An agent_plane row records what was attempted -- including a denial that never reached the database -- and a database row records what actually changed, including a write that reached PostgREST without going near the agent plane. A database row can only ever say `committed`, because a row written inside the transaction it describes is rolled back with it (D489). Metadata is not audited at all, which keeps discovery from depending on the audit table. Redaction is the capability lock's and the record stores what it is given. |
| `AGT-AUDITFAIL-001` | 9 | A write fails closed when its audit record cannot be created, and a read does NOT -- the asymmetry is the decision rather than an omission (ADR 0141, D483). Failing a read closed would couple every agent read's availability to the audit table. On the deployment the failure is arranged by withdrawing a real grant, so the write path fails through the real transport, the real function and the real privilege; "did not happen" is asserted against app.notes rather than against the shape of the refusal, because a tool that errored after committing would satisfy any assertion about the response. A failing `complete` never changes an outcome that already happened. |
| `AGT-WRITE-001` | 9 | A read-only agent can neither discover nor invoke a write, and the two are proved SEPARATELY because hiding a name is not a boundary (ADR 0140). Discovery filtering is disclosure control -- measured: a hidden tool is still callable by name and runs -- so the boundary is the call-time scope check, and both levels are asserted. Holding one write scope does not carry the other. The positive arm writes a real row under the agent's OWNER's identity (ADR 0117), without which every refusal below could be a broken credential. |
| `SEC-PARAM-001` | 9 | Tool parameters cannot override agent identity, role, or scope -- and the guarantee is STRUCTURAL rather than validated (D473, ADR 0135). Identity comes from the app.agent_id and app.user_id GUCs the pre-request hook sets from the token, and neither audit function declares a principal, an owner, a role or a scope, so there is no argument for a caller to lie in. Asserted as an absence: a validated form would be a list of forbidden names, which is a list that silently stops being complete. |
| `SEC-REV-001` | 9 | A token issued before revocation is denied on its next read and write through both MCP and PostgREST. Session 9 PROVES this rather than building it: migration 0018's agent_claims_are_current is the authoritative check and PATCH /admin/agents/{agent_id} is the revocation route, both since earlier sessions (D471, D472). The proof takes the product's own route -- the claims are captured while the agent is active and replayed unchanged after the PATCH -- and the positive arm runs first, so a hook that refused everything cannot pass. Both doors are asserted: the existing token stops, and the unchanged secret cannot be exchanged for a fresh one. |
| `REC-EVID-001` | 10 | Restore evidence records backup set, requested and achieved recovery point, RTO, schema version, and test outcomes. |
| `REC-PITR-001` | 10 | A timestamp-targeted restore into a disposable volume succeeds. |
| `REC-SAFE-001` | 10 | The restore path never mounts, overwrites, or mutates the active volume. |
| `REC-SMOKE-001` | 10 | The restored instance passes schema, RLS read, and write-RPC checks. |
| `DEP-002` | 11 | Re-running deployment converges without destroying data, and the redeploy demonstrably ran: the active secret generation differs from the one recorded before the window. |
| `DEP-PRE-001` | 11 | A missing prerequisite stops deployment before it changes anything, and lists every absent item with the command that supplies it. What could not be checked is reported separately from what was found missing (ADR 0157). |
| `OPS-001` | 11 | The diagnostic command reports every required check without secrets, reading the deployed document for identities only and every verdict from a live read (ADR 0158). A check that could not run is reported as unknown and exits non-zero. |
| `DEP-001` | 12 | A fresh project deploys on an empty host from documentation alone. |
| `DEP-ISO-001` | 12 | Two projects on one host share no state or authority; shared provider accounts are permitted, shared project scope is not. |
| `DEP-REMOVE-001` | 12 | Removing one project does not affect another. |
| `DX-001` | 12 | A developer who did not build the primitive completes the documented path without source edits or undocumented commands. |
| `REL-CLI-001` | 13 | Every operator command is reachable through one front door whose verb set is derived rather than kept, which refuses a name before it becomes a path and adds no path, privilege or exit code of its own. |
| `REL-COMPAT-001` | 13 | An incompatible manifest, capability or secret-format change is refused before any mutation, and the refusal is proved against the tree as well as the exit code. See ADR 0162. |
| `REL-PLAN-001` | 13 | A deployed project produces a complete upgrade plan without changing its deployment, and a comparison that could not be made is undetermined rather than reported as no changes. |
| `REL-VER-001` | 13 | The platform version is semver, parsed by this release rather than by a PEP 440 parser that rewrites it, and the version a deployed project runs is machine-readable from the host without changing anything. |
| `CAP-ENV-001` | 14 | A capacity envelope whose every number states the conditions it was sampled under and whether it transfers to another machine, which scenarios were not measured and what unblocks each, and which image digests its numbers describe. The configuration-determined numbers are checked against the deployment they claim to describe, so the claim cannot go green because a document exists (ADR 0169). |
| `OPS-ALERT-001` | 14 | An induced failure fires its own rule and a healthy deployment fires none. Every rule states what it means by an absent series, because a rule over a series that does not exist evaluates to nothing and reports healthy for ever; no rule is written over a metric no deployment publishes, for the same reason. The two hops that carry a project's metrics have separate rules, because one rule over both names the wrong subject (ADR 0168). |
| `OPS-METRIC-001` | 14 | The reserved /metrics route serves a Prometheus surface for a deployed project and refuses anyone without the credential. The surface carries this project's series and no other project's: the scrape filter is an enumeration of the routers naming derives, never a prefix over the project key, because a key may contain a hyphen and a prefix admits a different project. Discriminated on the body rather than the status -- a 404 from this route means the router was not created, and must never be read as metrics not being configured (ADR 0005, ADR 0164, ADR 0167). |
| `OPS-REDACT-001` | 14 | No token, URL, object key or caller value reaches the telemetry plane, on any of its three carriers. A span attaches no exception message or stacktrace, both SDK defaults being reversed; a metric label is drawn from a closed set and an unexpected value is folded rather than published, because a label is a series and a series is memory; and a value planted where nothing else could produce it does not appear on the deployed surface (ADR 0166, ADR 0167). |
| `IDN-AGENT-001` | 15 | An agent credential carries an expiry that is enforced at VERIFICATION rather than at issuance - an expiry consulted only when a credential is minted constrains the mint and nothing else - and the check sits after the hash comparison so an expired credential costs the same Argon2 verification as a wrong secret and is indistinguishable from an unknown agent. D503 is closed: revoked to active is refused, because it was measured to restore the ORIGINAL secret and so freed no credential, and reinstatement is rotation, which issues a new secret and clears the revocation in one operation. That pairing is the decision - rotating a revoked agent previously left it revoked with the new secret refused, so refusing the transition alone would have stranded every agent revoked by mistake (ADR 0172). |
| `IDN-RESET-001` | 15 | An administrator resets a subject's password without learning it: the response carries a one-time token and no password, because none exists until the subject chooses one when they spend it. credential_version moves, so every access token issued before the reset is refused - and every refresh session the subject had is ended in the same transaction, because a refresh token names a session rather than a credential and a chain obtained with the old password would otherwise keep minting access tokens (D845). The reset is single use, expires in an hour because the value is in transit between two people, and every refusal answers identically. The password is screened before the token is spent, so a refused password leaves the subject able to try again rather than holding a spent token and an unchanged credential (ADR 0173). |
| `IDN-ROT-001` | 15 | The rotation surface says what replacing a declared secret would achieve and refuses when the answer is nothing. Seventeen secrets rotate by replacement and two do not, and the two look exactly like the seventeen - same shape, same consumers, same plane - so a plan that printed their files would be describing in detail a rotation that does not happen, which is D56. Each refusal names the operation that does work rather than only refusing, and the two do not share an explanation because one flag covers two different phenomena: one value is read once and nothing is bound to it, the other IS bound, to a repository, at stanza-create (D850). must_refresh_on_start is deliberately not reported: it selects between failing closed and a cached last-known-good start, and the materializer has no cache, so six false declarations describe leniency that does not exist (D849). No verb in the surface writes anything, anywhere (ADR 0174). |
| `IDN-SESSION-001` | 15 | A client maintains a session across the access token's lifetime without retaining the password, and a refresh token is single-use: presenting one twice ends the whole family. Before this session a token lived at most 930 seconds and nothing renewed it, so any client staying logged in had to keep the password and replay it - a credential-retention defect rather than a convenience one (D813). Reuse is detected because at most one token per family is live, which a partial unique index enforces for every writer, and the family is revoked in the same transaction as the detection because a service that found a leaked chain and died before revoking it would have left the chain live (ADR 0171). |
| `IDN-SESSION-002` | 15 | A subject's sessions are listable and individually terminable, and a terminated session's refresh token is refused from that moment - ending a session reaches the credential rather than only a row somebody reads. Both operations are scoped to the owner in SQL rather than in the service, so a caller naming another subject's session id gets the same answer as one naming a session that does not exist. A session carries no caller-supplied string - no device, no address, no user agent - so a listing identifies it by its id and its times and cannot name a machine (D829). |
| `AGT-APPROVE-001` | 16 | A capability declaring requires_approval is refused before anything is dialled, with its own taxonomy reason and its own caller-facing token, and the refusal is audited. The refusal is the guarantee (D870): no pending state, no second principal, no notification plane. The declaration folds as a restriction across the capabilities behind a tool - any one requiring approval requires it - which is the opposite polarity from the dry-run permission (D925). The live half shows the declaration, the enum member and the token on the deployment; the refusal itself is proved against a lock that declares it, because no reviewed capability does (ADR 0182). |
| `AGT-CAPVER-001` | 16 | Every capability declares a semver and a lifecycle at the manifest version that introduces them, and both are read: a retired capability is refused by the compiler and again by the lock loader, a deprecated one is carried into the lock with its state, and the version a tool's sole capability declares reaches the audit row of every call it serves, beside the lock's own contract hash (ADR 0177, ADR 0178). Since Run 9 the version has a reader with consequences - a hand-written evaluation case is bound to the version it was written against and a capability that moves without its cases fails the gate (ADR 0184). No warning is issued for a deprecated capability; the plan's "refused or warned" was measured as refused-or-carried (D935). |
| `AGT-DENIAL-001` | 16 | Every denial the agent plane issues carries one member of a closed taxonomy - an enum in the catalog, mirrored by the runtime and compared against it - the reason is recorded in agent_audit.denial_reason on the refused row and on no other, and no reason is free text: a refusal site naming a member the catalog does not know is refused at the site rather than surfacing as an audit outage. The taxonomy is derived from the refusal sites, not designed beside them, and `credential` is not a member because this runtime holds none (ADR 0178, D886). |
| `AGT-DRYRUN-001` | 16 | A dry run attempts the write and rolls it back inside a subtransaction, so every CHECK, every policy and the compare-and-swap fire and a rehearsal's refusal is the refusal the real call would have produced; it changes nothing, spends no idempotency key, returns the row it would have written with a created row's id nulled and row_count 0, and is audited as dry_run rather than as a write. A rehearsal against a capability that does not declare support is refused as an input the lock does not permit (ADR 0182). |
| `AGT-IDEM-001` | 16 | A replayed agent write carrying the same idempotency key performs the work once and returns the row the first call produced - re-read, not stored, so the plane holds no caller value - and is audited as replayed; a different key with the same body performs the work twice. The claim is taken inside the write's own transaction, because a separate claiming request cannot deduplicate; a key reused for different arguments or a different tool is refused with its own errcode; every agent write requires a key and a human write never carries one (ADR 0181). |
| `AGT-PROFILE-001` | 16 | A project profile may only narrow the compiled contract, in the seven bounds the runtime reads from the lock and nothing else. A profile that would widen any bound, name a tool the contract does not compile, bound a field the tool's kind does not carry, or introduce a bound the contract's version does not declare is refused at compile time - by the contract check in a checkout and by the deploy's lock step, which requires the manifest - and never at request time. Nothing is clamped. The lock records the profile it was compiled under and the runtime refuses a lock whose tools disagree with it (ADR 0183, D867). |
| `AGT-QUOTA-001` | 16 | A windowed quota bounds an agent across requests: counted inside agent_audit_begin so the fifth budget costs no extra round trip, held in one durable row per agent so the bound survives a process restart, refused by the database writing its own refused row with budget_exceeded rather than raising, and independent of ADR 0129's four per-request budgets. The runtime tells a quota refusal from an audit outage by the function's NULL return, never by the absence of a record id (ADR 0180, D907). |
| `AGT-RISK-001` | 16 | Every capability carries a risk classification from a closed, ordered vocabulary; the manifest refuses a metadata capability that claims more than low and a write that claims low; a tool backed by several capabilities is classified as the riskiest of them, never the first; and a lock at a version that requires the classification is refused at startup without it. The classification is carried, aggregated and enforced as a declaration. It selects no runtime behaviour today (D934): the plan's "a high-risk capability's denial differs observably from a low-risk one's" describes a plane nothing in the runtime reads, and this entry asserts what the tree does rather than what the plan proposed. |
| `EVAL-HARNESS-001` | 16 | Every enabled capability has positive and adversarial evaluation cases. The derived cases are generated from the compiled contract, one adversarial case per frozen field, and carry an expectation - permitted, refused or bounded - and never a denial reason; the reasons are observed when the cases run, and the derived adversarial cases are asserted not to be all refused by the same first check. Hand-written cases are counted separately and bound to the capability version they were written against, so a capability changed without its cases fails the gate and CI. The report the cases are derived for carries the contract's digest, and the deployment publishes the same digest for the contract it serves (ADR 0184, D868). |

**P1 — 6 requirements**

| ID | Session | Guarantee |
|---|---:|---|
| `DBX-004` | 4 | Node and Python drivers round-trip a query through the pooler. |
| `STO-BOUND-001` | 7 | An upload declaring more than the deployment's published bound is refused, and one at the bound is accepted. The limit is read from the deployed document rather than restated, so the proof cannot pass against a differently configured deployment. |
| `STO-CLEAN-001` | 7 | The cleanup sweep collects a tombstoned object whose write window has closed and records completion only after the provider has been asked. The late-writer arm is proved offline against a real cluster, where the deadline can be moved without the proof arranging the condition it observes. |
| `STO-COMPLETE-001` | 7 | Only an object verified against the provider becomes downloadable, and a retried completion is a 200 rather than a conflict. Idempotence is a separate arm because migration 0014's CAS was idempotent as a function and not as a path through it (D349). |
| `REC-WAL-001` | 10 | A WAL archiving failure produces a visible non-zero signal. |
| `OPS-LOG-001` | 11 | One request ID spans ingress, API, agent and audit records. The runtime mints it and stamps it on the response, where Traefik's access log keeps it as downstream_X-Request-Id; migration 0022 puts the same value on the database-source audit row. No caller-supplied id is ever adopted (ADR 0160). |

Full node IDs are in [the acceptance matrix](acceptance-matrix.md).

<!-- END GENERATED: requirements -->

## 4. Numeric bounds

Bounds are declared once, in `schemas/project.schema.json`, because that is
the only copy that is machine-consumed at validation time. The table below is
generated from it. Cross-field *relations* cannot be expressed in JSON Schema
and live in `src/agentic_postgres/config.py`; they are listed separately.

<!-- BEGIN GENERATED: bounds -->
<!-- Generated from schemas/project.schema.json by
     bin/render-config.py --bounds-doc --write. Do not hand-edit. -->

| Field | Minimum | Maximum | Meaning |
|---|---:|---:|---|
| `api.app.memory_limit_mb` | 192 | 2,048 | The auth container's memory limit, in MiB. This minimum is a floor on the field; the real bound is ADR 0082's cross-field relation, which requires `hash_concurrency` x `memory_cost` plus the service's process overhead to fit -- so a manifest declaring too little fails validation rather than being killed by the OOM killer at the first burst of logins. Measured in Run 7: 67.1 MiB resident per concurrent hash at the frozen profile, linear in concurrency (131.1 at two, 259.0 at four), against a no-hash control that moved the resident figure by 0.0; and 60.9 MiB for the process with every dependency imported and an application object built. |
| `api.app.pool_size` | 1 | 100 | Connections the auth service's psycopg pool may hold. Charged to the cluster's budget whether or not the service is enabled, for the reason `resolve_api_connection_budget` gives about REST: a division that depended on whether a service happened to be on would move when somebody toggled it. |
| `api.max_rows` | 1 | 10,000 | Global PostgREST row-return ceiling. |
| `api.rest.pool_acquisition_timeout_seconds` | 1 | 60 | How long a request waits for a connection before failing. Bounded above for the reason the pooler's queue timeout is: a request that waits without limit turns a capacity problem into a hang, and a hang has no error message to act on. |
| `api.rest.pool_max_idle_seconds` | 5 | 3,600 | How long an unused pooled connection is kept. Must be less than pool_max_lifetime_seconds. |
| `api.rest.pool_max_lifetime_seconds` | 60 | 86,400 | How long a pooled connection is reused before it is retired. Bounded above so a rotated credential cannot be held indefinitely by a long-lived connection -- the same reason database.server_lifetime_seconds is bounded. |
| `api.rest.pool_size` | 1 | 100 | PostgREST's own connection pool, against the DIRECT transport rather than the pooler: it needs prepared statements and a LISTEN/NOTIFY channel for the schema cache, neither of which survives transaction pooling. Counted against database.max_connections together with the pooler's server pool and an administration reserve. |
| `api.rest.request_body_max_bytes` | 1,024 | 10,485,760 | Largest accepted request body. Bounded above because the edge buffers what it accepts, and equal to request_body_memory_bytes for P0 so an accepted body stays in memory rather than spilling to proxy disk -- a spilled body is a request payload written to a filesystem nobody is auditing. |
| `api.rest.request_body_memory_bytes` | 1,024 | 10,485,760 | How much of a request body the edge holds in memory. Must equal request_body_max_bytes; the pair exists because the two are separately configurable at the edge and a smaller memory limit is how bodies reach disk. |
| `backup.retain_full` | 1 | 12 | Full backup chains retained, rendered into the repository's `repo1-retention-full`. Two is what docs/source-specification.md section 12.1 asks for. This bound existed from Session 1 and was read by NO code until Session 10 -- no default resolution, no propagation, absent from outputs.json (D519) -- so a manifest could set it to 7 and nothing would retain seven chains. |
| `database.idle_transaction_timeout_seconds` | 10 | 600 | How long a client may hold a server connection inside an idle transaction. Cannot be disabled here, because in transaction pooling one idle transaction holds a server connection out of the pool for as long as it lasts. |
| `database.maintenance_work_mem_mb` | 16 | 512 | VACUUM and index-build working memory. Charged in full against the guardrail because one maintenance operation can hold it for a long time. |
| `database.max_client_connections` | 1 | 10,000 | PgBouncer client connection ceiling. |
| `database.max_connections` | 10 | 200 | PostgreSQL max_connections on the cluster itself, not the pooler's ceiling. Deliberately small: Session 4's answer to connection count is a pooler, and a large per-cluster limit would make the pooler decorative. 56 since Session 7, and the six are what the storage service costs (ADR 0099) -- at 50 the budget divided exactly three ways with nothing spare, and a fourth claimant pushed the application's remainder below the pooler's own pool. |
| `database.max_prepared_statements` | 1 | 1,000 | How many protocol-level named prepared statements the pooler tracks per connection. Must be non-zero: at 0 a named statement is unusable the moment transaction pooling moves the client to a different backend, which was measured against the locked image rather than read from its documentation. This is the setting a failing client test must never be 'fixed' by lowering. |
| `database.memory_limit_mb` | 128 | 4,096 | The container mem_limit. NOT the same number as the guardrail: a container limit caps page cache too, so a limit set equal to the unreclaimable budget makes the cluster live in permanent cache reclaim. Measured at 512 MiB with these defaults, two clusters pegged their limit with several hundred reclaim events and no OOM kill. Must exceed the derived unreclaimable budget. |
| `database.pool_size` | 1 | 1,000 | Server-side pool size. Must not exceed max_client_connections. |
| `database.query_wait_timeout_seconds` | 1 | 120 | How long a client may wait for a server connection before the pooler gives up. Bounded above so a saturated pool fails rather than stalling: an unbounded queue turns a capacity problem into a hang, and a hang has no error message to act on. |
| `database.server_lifetime_seconds` | 60 | 86,400 | How long a server connection is reused before the pooler retires it. Bounded above so that a rotated credential cannot be held indefinitely by a long-lived backend, and below so that recycling does not become the dominant cost. |
| `database.shared_buffers_mb` | 16 | 1,024 | PostgreSQL shared_buffers. Counts in full against the memory guardrail: it is shared memory, which no swap can relieve and no cache reclaim can shrink. |
| `database.shm_size_mb` | 64 | 1,024 | The container /dev/shm size. PostgreSQL's dynamic shared memory for parallel query lands here, and Docker's 64 MiB default is below the default shared_buffers. Must be at least shared_buffers_mb. |
| `database.work_mem_mb` | 1 | 64 | Per-sort-node working memory. Allocated on demand, so it does not multiply by max_connections in practice; the guardrail charges a flat per-backend anonymous allowance instead. See the Session 3 plan 3.3. |
| `mcp.max_response_bytes` | 1,024 | 10,485,760 | Schema version 1 only, and READ BY NOTHING (D929). Its maximum is ten times the runtime's `MAX_SERIALIZED_BYTES`, so even a reader could not have honoured it. Version 2 replaces it with `mcp.profile.<tool>.max_response_bytes`, bounded at the runtime's ceiling (ADR 0183). |
| `mcp.max_result_rows` | 1 | 1,000 | Schema version 1 only, and READ BY NOTHING (D929): declared as the agent read row ceiling since Session 1, it reaches neither Compose, the lock nor the runtime. Version 2 replaces it with `mcp.profile.<tool>.max_rows`, which the lock compiler reads (ADR 0183). Must not exceed api.max_rows. |
| `mcp.profile.<tool>.max_affected_rows` | 1 | 100 | At most the write's compiled `max_affected_rows`. Writes only. |
| `mcp.profile.<tool>.max_concurrent_calls` | 1 | 32 | At most the tool's compiled `max_concurrent_calls`. Reads and writes only. |
| `mcp.profile.<tool>.max_response_bytes` | 1,024 | 1,048,576 | At most the tool's compiled `max_response_bytes`. Reads and writes only; the maximum is the runtime's `MAX_SERIALIZED_BYTES`, as in the capability schema (ADR 0179). |
| `mcp.profile.<tool>.max_rows` | 1 | 1,000 | At most EVERY resource's compiled `max_rows` behind a read tool -- `query_resource` has two and they may disagree, so a per-tool value is checked against each. Reads only. Must not exceed api.max_rows. |
| `mcp.profile.<tool>.timeout_ms` | 100 | 30,000 | At most the tool's compiled `timeout_ms`. Applies to every kind. |
| `storage.download_url_ttl_seconds` | 60 | 3,600 | Presigned download URL lifetime. Shorter than the upload default because an upload is one deliberate act by the holder and a download URL is the one that ends up pasted somewhere. |
| `storage.max_upload_bytes` | 1 | 5,368,709,120 | Largest accepted upload. P0 default is 25 MiB. |
| `storage.memory_limit_mb` | 128 | 2,048 | The storage container's memory limit. 384 is the application API's figure, INHERITED RATHER THAN MEASURED. A second application container's memory floor is listed as 'must be measured' in this session's feasibility table and cannot be until there is an adapter to measure; it is a manifest field precisely so the number stays visible and overridable while it is provisional, rather than being a literal nobody knows is unmeasured. ADR 0082 is the shape that measurement has to take -- one profile per process with a no-work control, because ru_maxrss is a high-water mark already set by earlier work and reports the same plausible number for every row. |
| `storage.pool_size` | 1 | 64 | The storage service's cluster pool (Session 7, ADR 0099). Charged against database.max_connections as pool_size + 2 reserved, whether or not storage is enabled -- a division that moved when somebody toggled a flag would make the bootstrap plane's arithmetic depend on a flag it does not read. Raising it lowers what is left for the application, and the bootstrap refuses when that remainder falls below database.pool_size, because the pooler cannot fill a pool larger than the role's own CONNECTION LIMIT. |
| `storage.upload_url_ttl_seconds` | 60 | 3,600 | Presigned upload URL lifetime. A presigned URL is a bearer credential with a short life, so this is the residual exposure of one issued URL -- it is not revoked by a later tombstone, and the documentation says so plainly rather than implying otherwise. |

Relations between these fields cannot be expressed in JSON Schema and are
enforced in `src/agentic_postgres/config.py`:

- `database.pool_size` must not exceed `database.max_client_connections`
- `mcp.max_result_rows` must not exceed `api.max_rows` (schema version 1)
- Every `mcp.profile.<tool>.max_rows` must not exceed `api.max_rows` (schema version 2)
- `api.public_base_path` and `mcp.public_base_path` must not overlap segment-wise
- Neither base path may overlap a reserved route
- `database.pooled_public` must be false and `database.pooled_public_cidrs` empty; a public pooler is not a supported profile (ADR 0040)
- `database.query_wait_timeout_seconds` must be less than `database.idle_transaction_timeout_seconds`
- `database.shm_size_mb` must be at least `database.shared_buffers_mb`
- `database.memory_limit_mb` must exceed the derived unreclaimable budget
- The derived unreclaimable budget must not exceed the per-project memory guardrail
- `api.rest.request_body_max_bytes` must equal `api.rest.request_body_memory_bytes`
- `api.rest.pool_max_idle_seconds` must be less than `api.rest.pool_max_lifetime_seconds`
- `api.rest.pool_size` plus its reserved connections, `api.app.pool_size` plus its own, `storage.pool_size` plus its own, `database.pool_size`, and the administration reserve must fit `database.max_connections`
- What `database.max_connections` leaves the application after every service's commitment and the operational headroom must cover `database.pool_size`; the pooler cannot fill a pool larger than the application role's own `CONNECTION LIMIT`, and the refusal it produces names the role rather than the arithmetic
- `api.app.memory_limit_mb` must fit the frozen Argon2id profile: `hash_concurrency` x `memory_cost` plus the service's process overhead
- `api.rest.allowed_cors_origins` must contain the project's own HTTPS origin when the REST service is enabled
- `api.rest.statement_timeouts` may name only roles the platform derives
- The derived REST prefix and the PostgREST documentation prefix must not overlap segment-wise, and neither may overlap the MCP prefix

<!-- END GENERATED: bounds -->

## 5. Non-goals

These are not deferred. They are outside the product.

- A shared, multi-tenant control plane, or any cross-project shared catalog.
- A hosted web console or SaaS offering.
- Autoscaling, scale-to-zero, or compute/storage separation.
- Database branching or copy-on-write forks.
- Automatic failover or multi-region replication.
- Arbitrary SQL execution by an agent, under any authentication.
- General-purpose ORM support beyond the endpoint contract in `DBX`.
- Cross-project reporting or aggregation.

What the first and last of those protect is **the surface a project serves**:
nothing a project's users, agents or routes can reach may see another project,
and no shared catalog sits in any request's path. An operator's read over the
deployed documents already on a host's own disk — run as root at a terminal,
holding no credential, served to nobody and read by nothing — is not that
catalog, and ADR 0185 says where the line is.

The agent constraint is the load-bearing one. An agent's reachable surface is
exactly the set of capabilities enumerated in `capabilities.yaml`, each bound
to one pre-existing operation with an approved shape. There is no path by
which an agent submits a query, a fragment, a column list, or a path.

## 6. Session 12 success criterion, and what was reached

Session 12 succeeds when, on a host that has never run this software:

| # | Criterion | Outcome |
|---|---|---|
| 1 | A new team member follows `docs/new-team-member.md` end to end without editing source code. | **Not reached.** The path's *offline* half is proved — every command it names exists and is executable, every session number it passes is one this release accepts, and no step asks a reader to edit a shipped file. **Nobody who did not build this has walked it.** `DX-001` reports `not_run`, and an offline half may not stand in for a live one. |
| 2 | Two projects deploy to the same host and neither can reach the other's data, roles, secrets, storage objects, or backups — proven by `DEP-ISO-001`, not asserted. | **Reached.** `DEP-ISO-001` is closed and measured live over both deployed projects, by a matrix that asserts what is *permitted* to be shared before it asserts what is not. |
| 3 | Every P0 requirement has at least one **active** test. None remains `future`. | **Reached.** There are no `future` placeholders left in the repository. |
| 4 | A point-in-time restore to a specified timestamp is performed against a disposable target and the restored data is verified by query. | **Reached.** `point_in_time_recovery`, `recovery_evidence` and `restore_verification` all passed against the live deployment. |
| 5 | An agent with a read-only capability set cannot discover or invoke any write, and every attempt — allowed, denied, or failed — is audited with redaction. | **Reached.** |
| 6 | `bin/session-12-check.sh` exits `0` from a clean tracked tree. | **Not reached, and gated on the others.** Offline mode exits `0`; host mode exits **`5`** — the evidence was written and four claims in it are not `passed`. It cannot exit `0` until those four do, and three of them need an *event* rather than code. |

**Four of six reached.** The two that were not are not defects in the artifact:
criterion 1 needs a person who did not build it, and criterion 6 is the sum of
that plus the bootstrap-issuer retirement (D683). `docs/scope-closure.md` is the
full ledger.

**This is recorded rather than reconciled.** A success criterion quietly
softened to match what was achieved is worth less than one that says plainly
which half was reached.

## 7. Change control

**Removing or weakening a P0 requirement** requires explicit approval and an
ADR recording what guarantee is being given up and who accepted the risk.
Deleting the test is not weakening the requirement — it is hiding it, and the
registry check fails on a P0 row with no node ID.

**Adding P0 scope** requires, in the same change: a requirement ID, an owning
session, a registry entry, and at least one collectible node ID. A P0
requirement may enter as a `future` placeholder, but the placeholder body must
fail if executed. A requirement with no test is not P0.

**Deferring P1 or P2** requires documented evidence of why, and a target
session. "Not yet" without a session is not a deferral.

**Any ambiguity discovered during implementation** is resolved in
`docs/plans/session-01-implementation-plan.md` §2 or in a new ADR — never
inline in the file that happened to surface it.

## Generated sections

Sections 3 and 4 are generated. The reason is drift: a P0 requirement listed
here but absent from `tests/acceptance-registry.yaml` is a guarantee nobody
tests, and hand-maintaining both copies guarantees that eventually happens.
Generating this table from the registry makes the failure structurally
impossible rather than merely detectable.

Regenerate:

```bash
python bin/render-config.py --bounds-doc --write        # section 4  (Run 2)
python bin/render-acceptance-matrix.py --requirements --write   # section 3  (Run 5)
```

Both have `--check` modes, run by CI and by `bin/session-01-check.sh`, which
fail on drift and never write.

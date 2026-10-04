# Threat model

Every row maps a claimed security property to a control, a way to detect
failure, an explicitly accepted residual risk, and executable proof.

The table below is **hand-authored** — attacker capability and residual risk are
analysis, not derivable data. What *is* machine-checked is referential
integrity: `tests/contract/test_acceptance_registry.py` parses the
`Acceptance requirement IDs` and `Acceptance test node IDs` columns and fails if
either names something absent from `tests/acceptance-registry.yaml` or from a
real pytest collection. The analysis itself is not parsed.

The column headers are contract. Changing them breaks the parser, which is
intentional: a silently renamed column would turn the integrity check into a
no-op.

## Threats

| Threat ID | Attacker capability | Protected asset | Prevention | Detection | Residual risk | Acceptance requirement IDs | Acceptance test node IDs | Target session |
|---|---|---|---|---|---|---|---|---:|
| `THR-AGENT-TOKEN` | Holds a valid, unexpired agent access token obtained from a compromised client | Project data reachable by that agent's scopes | Short token expiry plus an authoritative active-agent check inside the PostgREST `db-pre-request` transaction | The audit log records every attempt with its request ID; denials are recorded, not dropped | Data the agent could legitimately read before revocation is already disclosed. Revocation limits future access, not past access | `SEC-REV-001`, `AGT-AUDIT-001` | `tests/contract/test_auth_endpoints.py::test_a_revoked_agents_existing_token_stops_at_the_authoritative_check` | 9 |
| `THR-AGENT-SQL` | Full control of MCP tool inputs | The entire database beyond the agent's approved surface | Frozen resource, column, and operator allowlists; structured filters from a closed enum; no field accepts SQL, a fragment, or a query string | Capability/OpenAPI drift fails the smoke test; injection payloads appear in the audit log as data | A logic error inside an approved RPC is still reachable. The allowlist bounds the surface, not the correctness of what is on it | `AGT-SQL-001`, `SEC-INJ-001`, `AGT-DRIFT-001` | `tests/contract/test_mcp_tools.py::test_no_tool_input_accepts_sql_a_fragment_or_a_query_string`, `tests/security/test_session8_agent_injection.py::test_a_payload_in_a_filter_value_does_not_change_the_request_structure` | 8 |
| `THR-CROSS-USER` | A valid credential for user A | User B's rows | PostgreSQL row-level security on every owned table, security-invoker views, narrow write RPCs | Denials surface as empty result sets and authorization errors, logged without token contents | A shared row deliberately visible to both users is out of scope for RLS by definition | `SEC-RLS-001`, `SEC-VIEW-001` | `tests/security/test_session3_authorization.py::test_user_a_cannot_read_user_b_rows` | 3 |
| `THR-PRIV-ESC` | Ability to call any exposed function | Ownership and grant hierarchy | Non-login object owner, fixed safe `search_path` on every `SECURITY DEFINER` function, revoked default `PUBLIC` execute, explicit per-role grants | Default-privilege and ungranted-function tests fail loudly on regression | A `SECURITY DEFINER` function with a logic flaw still runs as its owner. Ownership is constrained; correctness is not | `SEC-FUNC-001`, `SEC-DEFAULT-001`, `SEC-OWNER-001` | `tests/security/test_session3_authorization.py::test_an_api_role_cannot_execute_an_ungranted_function` | 3 |
| `THR-SERVICE-COMPROMISE` | Code execution inside one runtime container | Everything that container's credentials reach | Distinct least-privilege role per boundary; no shared service role; no superuser or `BYPASSRLS` at runtime | Per-identity privilege tests assert each role's reachable surface | The compromised service's own legitimate surface is fully exposed. Segmentation limits blast radius, not the breach | `SEC-PRIV-001`, `SEC-ANON-001` | `tests/deployment/test_session5_api_authorization.py::test_the_private_schemas_are_unreachable_through_postgrest` | 5 |
| `THR-JWT-FORGERY` | Full read access to a verifying service's configuration and mounted files | The ability to mint tokens for any identity | Asymmetric signing; the private key exists only in the auth service; verifiers receive public material | Secret-mount inspection; invalid algorithm and key tests | Compromise of the auth service itself yields signing capability. This is the trust root and is not further reducible in the MVP | `SEC-KEY-001`, `SEC-JWT-001` | `tests/deployment/test_session6_tokens.py::test_no_verifier_holds_private_signing_material`, `tests/deployment/test_session6_tokens.py::test_both_verifiers_refuse_the_same_bad_tokens` | 6 |
| `THR-SECRET-DISCLOSURE` | Read access to the repository, built images, logs, or process arguments | Every credential in the deployment | Individual secret files in immutable generations, owned by the consuming UID; no persistent production `.env`; redaction in logs; secrets never passed as command-line arguments | Repository, image, `docker inspect`, Compose-output, journal, and container-log scans for a real sentinel value | A secret held in process memory is recoverable by anyone who can already read that process. Secret-zero — the control-plane credential and one per-project client secret — still lives on the host, root-only | `SEC-SECRET-001`, `SEC-SECRET-002`, `CFG-009` | `tests/security/test_session2_secrets.py::test_the_sentinel_is_absent_from_image_history`, `tests/security/test_session2_secret_model.py::test_no_service_takes_a_secret_through_the_environment` | 2 |
| `THR-PUBLIC-INGRESS` | Can reach the host's public addresses from any network | Every service port that is not meant to be public | Only the edge publishes a host port; a `DOCKER-USER` policy matching the pre-DNAT destination port drops forwarded traffic to anything else; UFW defaults to deny incoming | Full-TCP connect scan from an unrelated network, with 443 as the positive control; live comparison of the running chain against the installed policy | A published port added later is covered only if the firewall policy is re-reconciled. The `DOCKER-USER` chain protects forwarded traffic, not processes bound directly on the host | `SEC-NET-001`, `SEC-NET-002`, `SEC-HOST-001` | `tests/external/test_session2_public_edge.py::test_no_service_port_is_publicly_reachable_over_ipv4`, `tests/deployment/test_session2_host.py::test_the_docker_user_chain_matches_the_original_destination_port` | 2 |
| `THR-EDGE-DAEMON` | Code execution inside the publicly reachable reverse proxy | The Docker daemon, and therefore every container and the host | Traefik holds no Docker socket; it reads the API through a proxy whose allowlist enables five read sections and denies everything else, on an internal-only network; the daemon listens on no TCP socket | A live probe on the control network asserting a permitted read returns 200 and a container-create returns 403 | A read-only view of the Docker API still discloses container names, labels, and network topology to a compromised proxy | `SEC-DOCKER-001` | `tests/deployment/test_session2_host.py::test_the_socket_proxy_refuses_a_write_call`, `tests/contract/test_compose_contract.py::test_the_socket_proxy_denies_every_unneeded_api_section` | 2 |
| `THR-EDGE-LOGGING` | Read access to the edge access log, by operator error or log shipping | Bearer tokens and credentials carried in request headers and query strings | Traefik drops query parameters and all headers by default, keeping two by name | A request carrying a random sentinel in both a query parameter and a header, followed by a search of the log, with a positive control proving the log is recording those requests | Anything a client puts in a *path* is still logged. Paths are not a credential channel by convention, not by enforcement | `SEC-LOG-001` | `tests/deployment/test_session2_edge.py::test_no_query_string_reaches_the_access_log` | 2 |
| `THR-CHECKOUT-SWAP` | Write access to the operator's clone on the deployment host | What runs at the next boot or restart | systemd units execute only `/usr/local/libexec` launchers, which resolve a root-owned immutable release under `/opt/agentic-postgres/releases/{commit}`; the checkout is a transport artifact and is never executed | Every `Exec*` line of every installed unit is asserted to point into libexec; the release is asserted root-owned, non-group-writable, and free of `.git` | Root on the host can replace the release. This bounds what a non-root operator edit can change, not what root can | `DEP-REL-001` | `tests/security/test_session2_installed_release.py::test_the_installed_unit_executes_only_a_libexec_launcher` | 2 |
| `THR-CROSS-PROJECT` | Full control of one project deployed on a shared host | A neighbouring project's data, credentials, and backups | Deterministic project-scoped namespacing of every network, volume, role, database, issuer, audience, secret namespace, bucket prefix, and backup stanza | Two-project isolation matrix; destructive-removal test | Host-level compromise defeats every project on the host. Isolation is project-scoped, not hypervisor-grade | `CFG-012`, `DEP-ISO-001`, `DEP-ISO-002`, `DEP-REMOVE-001` | `tests/contract/test_render_isolation.py::test_collision_count_is_zero`, `tests/deployment/test_session2_isolation.py::test_neither_hostname_serves_the_other_project` | 12 |
| `THR-DATA-LOSS` | None — this is node loss or operator error, not an adversary | Availability and durability of project data | Encrypted pgBackRest repository, continuous WAL archiving, retained full-backup chains | Backup and WAL archive failures produce a non-zero operational signal | Data written after the last archived WAL segment is unrecoverable. The window is bounded by archive frequency, not eliminated | `REC-PITR-001`, `REC-SMOKE-001`, `REC-WAL-001` | `tests/recovery/test_future_pitr.py::test_timestamp_targeted_restore_succeeds` | 10 |
| `THR-BACKUP-COMPROMISE` | Read access to the backup repository credentials | Every historical copy of the database | Backup credentials separate from application credentials; repository encryption key stored separately from repository credentials; application services hold neither | Credential-scope checks assert application services cannot reach the backup bucket | Backups in the same provider account do not survive account-level compromise. This is documented in operations guidance and explicitly accepted for the MVP | `REC-EVID-001`, `SEC-SECRET-001` | `tests/recovery/test_future_pitr.py::test_restore_evidence_records_the_required_fields` | 10 |
| `THR-NOISY-NEIGHBOUR` | A project's own workload, run without malice: an agent's tool calls, a connection storm, a fork storm, a runaway query | The neighbouring project's latency, and the host's stability | `pids_limit` on every service, `mem_limit` on every long-running one (the edge's two included since Session 35, ADR 0244), `cpus` on the nine long-running ones and the edge's two, `max_connections` summed across six claimants per cluster, and admission against a capacity the host declares -- a deploy that would not fit is refused before it renders | `apg doctor capacity` and `apg doctor usage` on each project; the store's series, every one of which names its project | **Measured in Session 35 (2026-10-02, 1.13.0, both projects on the 3,814 MB host; `capacity.ENVELOPE`):** with one project's REST saturated from inside its own network (8 threads, ~473-491 req/s, all 200), the neighbour's REST through the edge went from p50/p95 ~41/~54 ms idle to 49.58/107.78 ms and 50.37/98.34 ms, with no error and no 429; 24 concurrent workflow runs on beta did not move alpha at all (41.15/55.36 ms), and beta's `auth` held a median 63.13 MB while they ran, the same as idle. The two projects share the CPU (2 vCPU) and the edge: recreating the edge takes BOTH away for ~24.4 s. The figures are a sample at one load, not a bound. Disk I/O is bounded by nothing at all: there is no `blkio` limit, and a project writing continuously shares one device with the other's WAL | `NODE-LIMIT-001`, `NODE-ADMIT-001` | `tests/contract/test_process_limits.py::test_a_container_cannot_fork_past_its_pids_limit`, `tests/contract/test_admission.py::test_a_candidate_that_does_not_fit_is_refused_with_exit_twelve` | 31 |
| `THR-WORKER` | A compromised `auth` process, or an operator with root running SQL against the four `app_private` workflow tables | Every agent's ability to act, and the notes and tasks a run may write | The loop holds the auth service's own role, pool and token issuance and nothing more (ADR 0226); a step's token is minted through the same status, expiry and scope checks an agent's own mint passes, held for one call and discarded; the four tables grant no privilege to any request role; every step is an ordinary plane call under the plane's scope check, audit, budget and idempotency claim; a definition names capabilities from a closed vocabulary and takes no SQL, path or query; revocation stops the run at its next step boundary | The doctor's `workflow` check -- counts by status, the oldest overdue lease and the heartbeat's age and holder; the `worker-restart` rehearsal; `agent_audit` rows correlated to a step by the request id the PLANE minted, which the step records (D1696) | The auth process already holds the signing key, so a compromise of it was always total -- what the loop adds is the ability to spend an ACTIVE agent's quota on that agent's own capabilities, and nothing else. An operator with root can insert a run row by hand and the loop will execute it as the named agent; the same operator can already mint any token, so this widens no boundary. A step already claimed when an agent is revoked is refused at the token, not after the call | `WF-WORK-001`, `WF-STATE-001`, `WF-REVOKE-001` | `tests/contract/test_workflow_worker.py::test_one_token_per_step_attempt_and_none_outlives_the_step`, `tests/contract/test_workflow_substrate.py::test_no_role_holds_a_privilege_on_the_four_tables` | 32 |
| `THR-APPROVAL` | An agent that wants a gated write to happen without a human's decision; a human administrator approving their own agent's work; a captured or replayed approval; a stale approval | Every write a capability declares `requires_approval` | The plane refuses a gated write unless the step token carries `apg_approval` naming the tool AND the idempotency key presented, and never with `dry_run` (ADR 0231); only `auth` signs, and it adds the claim only from an approved, unexpired decision it reads from the database itself; `/auth/agent-token` never adds it; a decision is a human access token holding `admin_workflows:approve` (administrative, `project_admin` alone), refused for the run's owner and, as an agent token, refused by `authenticate` (ADR 0232); a decision is final (`approval_already_decided`) and expires (`approval_expired`); a replayed claim re-reads the one write by its key (ADR 0181) | The refused first call's `approval_required` row in `agent_audit`; the `workflow_approval` record (who, when, which run and step); the provenance reader; the doctor's pending-approval count and the oldest one's age | **Since 1.13.0 a project's gated RPC refuses an agent's direct call in the database** (`app.require_approval`, migration 0037, ADR 0242; AGT-APPROVE-003/004): an agent holding the scope and its own token is refused `PT403` and writes nothing (rig 33b's 200 and written row were D1721). A profile-added approval on a release tool remains a plane control (D1869); the guard binds a call to a decision, a tool and a key, and does not make the project function idempotent (D1871). The approver sees who and what capability, never the argument values (D1720). The signing key's compromise was always total. | `AGT-APPROVE-001`, `AGT-APPROVE-002`, `WF-GATE-001`, `WF-APPROVE-001` | `tests/contract/test_approval_claim.py::test_the_plane_refuses_a_claim_for_another_tool_or_key`, `tests/contract/test_workflow_gates.py::test_the_runs_owner_cannot_decide`, `tests/deployment/test_session33_gates.py::test_the_runs_owner_cannot_approve` | 33 |
| `THR-CONNECTOR-INPUT` | Anyone on the internet who can reach the project's domain and does not hold a connector's key; a sender who holds it and sends a body the connector did not declare | The project's database, the authority of the agent bound to the connector, every tenant's rows | `POST /connectors/{name}` reads nothing but the raw bytes and two headers until an HMAC-SHA256 under the connector's DERIVED key verifies over `<t>.<delivery-id>.<body>` inside ±300 s (ADR 0237); one fixed 401 for every failure; no database call before it (proved with a repository that raises); then a closed body declaration (names, types, bounds, no extras); then a run of ONE installed definition as an agent whose stored scopes EQUAL the definition's, re-checked at acceptance (ADR 0236); the body becomes the run's `input` and reaches a tool only through a compiled argument reference; the edge's 16 KiB body cap and 20/s rate limit apply to a sender like any caller | The auth service's structured request line (the route template and the status; no body, no header value) -- written at INFO, which no handler prints, so it reaches no log today (D1918); `connector_receipt` for every accepted delivery; the run and its audit rows; `apg connector status` | A key holder can start as many runs as the edge's rate limit allows, each bounded by the agent's budgets and quota. A refused request is in no database, by design -- a refusal that wrote a row would be a write an unauthenticated caller could cause -- and it is in no log either: `apg-diag` reads the auth log since Session 35 (ADR 0245), but the per-request line is never printed (D1918). The key's compromise is the connector's authority, exactly. | `CONN-IN-001`, `CONN-IN-002` | `tests/contract/test_connector_routes.py::test_no_database_call_precedes_the_signature`, `tests/contract/test_connector_routes.py::test_every_signature_failure_is_one_fixed_document`, `tests/contract/test_connector_routes.py::test_a_body_outside_the_declaration_names_the_member`, `tests/deployment/test_session34_connectivity.py::test_a_wrongly_signed_request_leaves_no_receipt_and_no_run` | 34 |
| `THR-WEBHOOK-REPLAY` | A party that captured one correctly signed request (a proxy log, a misconfigured sender) and sends it again, now or later, with or without a new delivery id | Exactly-once acceptance of each delivery | The delivery id is INSIDE the signed bytes, so a new id breaks the signature; the same id is refused 409 `delivery_replayed` by `connector_receipt`'s primary key `(connector_id, delivery_id)`, recorded in the same transaction that enqueues the run; a request older than 300 s fails the signature window whatever its id (ADR 0237) | One receipt per delivery id; the 409 in the auth service's request log | Receipts are never pruned in Stage 4 (the retention story is D1700's). A sender that re-uses one delivery id across distinct events loses the second, which `docs/connectors.md` says. | `CONN-IN-001`, `CONN-IN-002` | `tests/contract/test_connector_routes.py::test_a_replayed_delivery_is_refused`, `tests/deployment/test_session34_connectivity.py::test_a_replayed_delivery_is_refused_once`, `tests/deployment/test_session34_connectivity.py::test_a_stale_timestamp_is_refused` | 34 |
| `THR-DELIVERY` | An outbound endpoint (or anyone who can read its logs) learning more than the event it was sent; a receiver redirecting the worker elsewhere; a flood of failing deliveries starving the worker | The project's credentials, other events, other connectors' keys, the worker's availability | A delivery carries the event's name, version, id, time and payload -- a payload the project's reviewed SQL chose (the example sends a note id, never the embedding) -- and a signature under THAT connector's derived key; no bearer, no cookie, no project credential is sent; the endpoint is read from a root-owned manifest, may carry no userinfo, query or fragment, and appears in no record, status or log; a redirect is never followed (rig 34b: the default `urllib` opener follows a 301/302/303 as a GET that still carries `X-Apg-Signature`, D1812); at most one delivery per loop iteration and only when due, so a failing endpoint costs `max + 1` attempts and a dead letter, never a hot loop (ADR 0238, the `delivery-retry-storm` rehearsal) | `apg connector status` (counts, the oldest pending age, the last error token, dead letters without payloads); the doctor's `workflow` line | The endpoint is whatever the operator declares: an internal service name would receive the signed body (rig 34d measured that a container on both networks reaches a sink on an `internal: true` network by alias). The payload is visible to the receiver by design; at-least-once means a receiver MUST de-duplicate on `X-Apg-Delivery`. | `CONN-OUT-001`, `CONN-OUT-002`, `CONN-STORM-001` | `tests/contract/test_connector_delivery.py::test_a_redirect_is_not_followed`, `tests/contract/test_connector_delivery.py::test_no_record_carries_the_url_the_payload_or_the_key`, `tests/deployment/test_session34_connectivity.py::test_an_owners_write_is_delivered_once_and_signed`, `tests/contract/test_rehearsal.py::test_the_storm_observes_three_attempts_and_a_dead_letter` | 34 |
| `THR-CHANGE` | A contributor or operator -- or an accident -- applying a project migration set nobody reviewed, or one edited after it was reviewed, to a deployment | The project's data and its reviewed contract | A host applies a project set with a pending version only when a COMMITTED proposal names the set's digest (the sha256 of the set's lock, which binds every template and its canonical render), and, under `approvals_required: 1`, a committed approval names the proposal's bytes by a second declared name (ADR 0243); the proposal carries the lint, the destructive findings (named, never refused), a from-empty apply through `apg dev up`, the set's final `api` surface against the reviewed contract, and the approval-gate check (ADR 0242); nothing is written into a host checkout (D971, D1852) | `migrate.sh --runtime status`'s proposal line; deploy step 6's refusal sentence; the committed history of `projects/<slug>/proposals/` | **The names are declared, not authenticated**: one person can commit both records, and root can do anything (D1864). A from-empty apply says nothing about existing rows. A capability-contract change is reported, not refused (D1866). A set with nothing pending needs no proposal, so the record guards the act of applying, never a state. | `GOV-PROPOSE-001`, `GOV-APPROVE-001`, `GOV-APPLY-001`, `GOV-APPLY-002` | `tests/contract/test_change_proposal.py::test_the_digest_is_the_renders_lock_sha256`, `tests/contract/test_change_proposal.py::test_approve_names_the_proposal_by_its_bytes`, `tests/contract/test_proposal_gate.py::test_a_pending_set_without_a_proposal_is_refused`, `tests/contract/test_proposal_gate.py::test_an_unapproved_proposal_is_refused_when_approvals_are_required`, `tests/deployment/test_session35_governance.py::test_the_applied_set_is_the_proposed_one` | 35 |

## Studio: a page in the operator's browser, on the operator's machine

`apg studio` (ADR 0205) puts a **token-holding process** and a **web page** on
the same machine, which is a shape none of the rows above has. Its table row
lands with the `STU-*` requirements it cites; the analysis is here because it is
what a reader needs before the row makes sense.

**What a hostile page can do.** Any page in the same browser can make that
browser send requests to `http://127.0.0.1:<port>` — it does not need to know
the port, because it can try all of them. So loopback is not a boundary and is
not treated as one. Five checks run in the process before anything else, and
each closes a different way in:

| Control | What it stops |
|---|---|
| the launch cookie is `HttpOnly`, `SameSite=Strict` | a cross-site request carries no cookie at all, so it is 401 before anything else runs. `Strict` rather than `Lax`: a top-level navigation from a hostile page is still cross-site |
| `X-Apg-Studio` is required on every `/__apg/` call | not a CORS-simple header, so setting it requires a preflight |
| `OPTIONS` is answered **405 by this server** | no preflight can succeed, so the header above cannot be set cross-origin. `http.server` would otherwise answer 501 with none of these headers — a refusal nobody here wrote is a refusal nobody here can reason about |
| the `Host` header must be the address the process bound | a DNS-rebinding attempt resolves an attacker's name to `127.0.0.1` and arrives with that name in `Host`; it is answered 421 |
| an `Origin` that is present and foreign is 403 | absent is not foreign — a same-origin navigation sends none |

A refused request's **body is never read**: a `POST` announcing a megabyte with
one byte sent is answered and closed rather than waited on.

**PostgREST's own CORS answer is measured and irrelevant, in that order.** Rig
24b sent `GET /notes` through the edge with `Origin: http://127.0.0.1:1`:

```
-> 200
   (no Access-Control-* header in the response)
   all response headers: Connection, Content-Length, Content-Location,
                         Content-Range, Content-Type, Date, Server
```

No `Access-Control-Allow-Origin` at all, so a browser gives a cross-origin
reader nothing. That is worth knowing and it is **not** what protects anything
here, because Studio's page never talks to PostgREST: it talks to the process on
loopback, which makes the upstream request itself. A design that relied on a
third party's default header would be relying on a default.

**What a hostile LOCAL process can do — the residual.** Any process running as
the same user can read the terminal's scrollback, `/proc/<pid>/cmdline`, or the
port list, and so can obtain the launch URL and with it the cookie value. That
process could then drive the page's endpoints as the logged-in human.

This is **accepted and not closed.** A local process running as you can already
read your files, your SSH keys and your shell history; a launch URL is not the
weakest thing available to it. It is the same residual Jupyter accepts for the
same reason, and it is bounded twice: by the process's lifetime (the launch ends
when you press Ctrl-C, and the session it opened is revoked) and by the token's
own 900 seconds plus 30 of skew. What it is **not** bounded by is the page —
there is no idle timeout, and adding one would be a control on the wrong side.

**What the page can never obtain, hostile or not**, is the token itself. It is
held in the process's memory, never written, never printed, never put in a
response header or an asset. The request log is a method and a path with the
query string and the launch key removed, because a default logger writes the
request line and a request line carries both.

**Studio adds no verifier.** It holds a token the auth service signed and
verifies nothing; the four verifiers are unchanged, and only auth signs.

## Notes on residual risk

Three of these are worth restating outside the table, because they are the ones
most likely to be misread as "handled":

**Revocation is forward-looking.** `SEC-REV-001` proves a token stops working on
its next request. It does not un-disclose anything the agent already read. If
disclosure matters more than continued access, revocation is not the control —
scope reduction before issuance is.

**The backup account boundary is not a disaster-recovery boundary.** Backups
stored in the same provider account as the application protect against node
loss and operator error. They do not protect against compromise of that account.
Source specification §12.2 states this and the MVP accepts it; an independent
backup account is listed as post-MVP work.

**Allowlists bound the surface, not the correctness of what is on it.** Every
agent-facing control here constrains *which* operations are reachable. None of
them makes an approved operation correct. A flawed RPC on the allowlist is
reachable by design.

**The agent audit table grows without bound, and so does the idempotency
table.** Nothing prunes either. `app_private.agent_audit` gains a row per agent
request — served and refused both, which is the point — and
`app_private.agent_idempotency` a row per claimed key. This is **stated rather
than handled**: no retention policy exists, none is enforced, and the counts on
the deployment are unmeasured until the next host trip. Studio's audit view
makes the shape visible without solving it — it serves the newest 500 rows and
says in its header that the page is the newest 500, which is honest about what
it cannot count but is not a bound on the table. A retention policy is a
released migration carrying a decision about how long a denial must remain
readable, and that decision has not been taken.

**The DX layer's review is a matrix, and fourteen of its cells are reasons rather
than proofs.** `tests/security/test_dx_surfaces_hardening.py` holds
`HARDENING_MATRIX`: every invariant Stage 3's §8 table lists, against each of
the three developer surfaces (`apg dev`, `apg generate`, `apg studio`) —
forty-eight cells, each carrying the node id of the proof that holds it or the
reason the invariant does not reach that surface. A cell marked *not applicable*
carries its reason **in the source**, beside the cell, because a blank is
indistinguishable from an oversight and telling those apart is what a review is
for. Two guards keep it honest: every node id it names must be collected by the
sweep that records the claim (D1242 — about fifty proofs here once turned out to
be collected by no sweep at all), and every invariant in that table must appear
as a key for all three surfaces, read out of the plan rather than compared
against a copy of it.

What the matrix does **not** say is that the invariants hold. It says which
proof is claimed to hold each one, and that the proof runs in the sweep that
would record it. A cell whose proof is weak looks exactly like a cell whose
proof is strong.

## Hosted threats, written before their controls (Stage 5)

ADR 0246 makes Stage 5 a hosted product: people who do not operate the node
hold accounts, API keys, database credentials and projects they did not
deploy. The threats below are theirs. **They are a list, not table rows, on
purpose**: a row in the table must name a registered requirement
(`test_every_threat_row_names_at_least_one_requirement`), and none of these
controls exists yet. A row with an invented requirement would be a control that
looks measured. **Each item moves into the table, as a `THR-*` row with its
requirement and its negative test, in the run that registers the requirement**
— and every building session adds its own items in its first run (D1527's
discipline, carried into Stage 5).

Each names the session that builds its control and the negative test it owes.
Signup abuse is not here: Stage 5 is invite-only (D1951). Support-grant misuse
is not here either: no support grant is built, and the Reality Ledger says why
— *"the operator of this single node has root on it; support access is not
technically bounded in this beta"* (D1971).

1. **Invitation abuse and enumeration** (Session 37, ADR 0252). An attacker
   guesses, replays or reuses an invitation token, or learns from the refusal
   whether an address or organisation exists. Owed: a used, expired, revoked or
   unknown token is refused with one byte-identical answer
   (`test_control_invitations.py::test_every_invalid_token_gets_the_same_answer`);
   a token is single-use under concurrency
   (`::test_one_of_two_concurrent_acceptances_succeeds` -- rig 37b measured the
   second of two concurrent acceptances wait for the first and update no row);
   the token is stored only as its SHA-256
   (`::test_a_token_is_shown_once_and_stored_hashed`); a taken username leaves
   the token unspent (`::test_a_taken_username_leaves_the_token_unspent`); and
   live, through the public endpoint only
   (`tests/external/test_session37_control.py::test_an_invitation_is_accepted_once`).
2. **API-key compromise and replay** (Session 37, ADR 0253). A leaked
   management key is used after its owner is removed or the key revoked, used
   against a project of another organisation, or used to mint its own
   successor. Owed: a revoked key, and a key whose member left, are refused on
   the next request
   (`test_control_keys.py::test_a_revoked_key_and_a_departed_owners_key_are_refused`);
   a key mints no key, invitation or factor (`::test_a_key_mints_nothing`); a
   key of organisation A is refused on every resource of organisation B
   (`::test_a_key_reaches_no_other_organisation`); and live
   (`tests/external/test_session37_control.py::test_a_departed_members_key_stops`).
3. **Organisation privilege escalation** (Session 37, ADR 0252). A `member` or
   `viewer` grants itself `admin`, mints a key with a scope it does not hold, or
   an `admin` acts without the second factor `owner` and `admin` require. Owed:
   each role refused every operation above it
   (`test_control_roles.py::test_every_route_and_role_answers_as_the_matrix_says`);
   an admin cannot make an owner (`::test_an_admin_cannot_make_an_owner`); the
   last owner stays (`::test_the_last_owner_stays`); a key's scopes never
   exceed its minter's
   (`test_control_keys.py::test_scopes_are_bounded_by_the_vocabulary_and_the_role`,
   `::test_a_demotion_narrows_a_key`); an `owner` or `admin` without a factor
   reaches only enrolment
   (`test_control_sessions.py::test_an_owner_without_a_factor_reaches_only_enrolment`);
   and live
   (`tests/external/test_session37_control.py::test_login_enforces_the_second_factor`).
4. **Project and branch enumeration** (Sessions 37, 40). A caller learns that a
   project or branch of another organisation exists from a status code, a
   timing or an error body. Owed: a foreign id and a missing id return the same
   answer -- Session 37's half for organisations, members and projects
   (`test_control_roles.py::test_a_foreign_id_and_a_missing_id_look_the_same`),
   and a non-member reads no row of an organisation in the database itself
   (`test_control_set.py::test_a_non_member_sees_nothing`). The branch half is
   Session 40's.
5. **Endpoint confusion and gateway attacks** (Session 39). A plaintext
   connection, a wrong or absent SNI, or one project's hostname used to reach
   another project's database through the shared Postgres port. Owed: plaintext
   refused; a wrong SNI refused; project A's credential refused at project B's
   endpoint (the isolation matrix extended to the listener).
6. **Wake-on-connect abuse** (Session 39). Unauthenticated connections used to
   keep a sleeping project awake or to make the node wake many projects at once.
   Owed: the measured rule for what wakes a project, and a wake that admission
   would refuse is refused — or, if Session 39's rig refuses wake-on-connect,
   the Ledger says `planned` and the client sees `project_sleeping`.
7. **Project-creation and branch-creation exhaustion** (Sessions 38, 40). A
   member creates projects or branches until the node or the slots run out.
   Owed: the entitlement refused as `plan_limit_reached` before an operation
   exists; capacity refused as `capacity_exhausted` with *"No resources were
   created"*; neither code produced by the other's reader.
8. **Plan-limit bypass and usage tampering** (Session 41). A caller raises its
   own limits, creates concurrently past a limit, or writes its own usage.
   Owed: a limit enforced under concurrency; no customer surface writes a usage
   sample or an entitlement.
9. **Restore abuse** (Session 40). A restore aimed at another project's
   repository, at a recovery point outside the window, or at the parent's live
   volume. Owed: a foreign repository refused; the parent untouched; a branch
   refuses the parent's credentials after its re-key.
10. **Control-plane / data-plane credential confusion** (Sessions 37, 38, 39).
    A control-plane session or API key presented to a project's data or admin
    plane, or a project credential presented to `/api/v1`. Owed: each refused
    at the other plane; the control plane holds no credential that opens a
    project (ADR 0246's boundary sentence). Session 37's half: the control mode
    reads no other project's document, URL or secret
    (`test_control_boundary.py::test_the_control_mode_reads_no_other_projects_credential`);
    a member's key is refused by alpha's app and REST routes
    (`tests/external/test_session37_control.py::test_a_key_lists_projects_and_opens_no_project`);
    and the control project's `auth` container serves no release admin route
    (`tests/deployment/test_session37_control.py::test_the_control_mode_serves_no_release_admin_route`).
    Sessions 38 and 39 owe the halves their surfaces add.
11. **Project-deletion races and slot reuse** (Session 38). A deletion that
    leaves a route, a role or a repository a later project inherits, or an
    operation that runs against a project mid-deletion. Owed: a deleted
    project's names derive nothing a new one is given; a slot is single-use.
12. **Connector abuse by a customer** (Session 42). A customer-defined
    connector used to reach another project, an internal address, or the
    node's own services. Owed: the connector planes' existing refusals hold for
    a customer's definitions, and an endpoint stays the manifest's.
13. **Observability poisoning and ClickStack exhaustion** (Session 41). A
    customer writes log lines or query text that forge another project's
    telemetry, or floods the telemetry store until the node's own readings
    fail. Owed: every series and line names its project from the platform, not
    from the payload; ClickStack bounded in memory, processes and CPU and
    charged by admission.
14. **Cross-project leakage through any new surface** (every session). Any
    console page, `/api/v1` operation, snippet, notification, usage figure or
    diagnostics bundle that carries another project's data. Owed: each session
    extends the isolation matrix to the surface it adds. Session 37's: the
    control project's deployed document shares no isolated value with either
    neighbour's
    (`tests/deployment/test_session37_control.py::test_the_control_project_is_isolated_from_both`),
    and a caller sees only their own organisations' rows
    (`test_control_set.py::test_a_caller_sees_only_their_own_organisations`).
15. **Storage exhaustion** (Session 38). One project fills the shared disk until
    its neighbours' databases or backups stop. Owed: the measured reading and
    the refusal admission makes; until a per-project disk quota exists, the
    Ledger says storage is `planned`, not limited.
16. **TOTP seed disclosure** (Session 37, ADR 0252). A dump of the control
    project's database, or a backup read with its cipher pass, reveals every
    enrolled second-factor seed, so the factor stops being a second factor for
    whoever holds the copy. Owed: seeds reachable only through definer
    functions granted to the control project's identity service
    (`test_control_set.py::test_no_request_role_can_execute_a_control_function`);
    a seed shown once at enrolment and never logged
    (`test_control_sessions.py::test_no_seed_reaches_a_log_line`). Residual:
    seeds are plaintext at rest, because computing the code needs the key;
    encrypting them is `planned`, and ADR 0252 says so.

## Scope

This model covers the deployed system. **From Stage 5 (ADR 0246) external users
are in scope.** Denial of service is in scope for the creation paths and the
public Postgres port as admission and rate limits — still not as an
availability SLA. It deliberately excludes:

- Physical and hypervisor-level attacks on the host.
- Compromise of the container registry or the base images themselves; that is
  mitigated separately by digest pinning (`CFG-014`), which proves you got the
  bytes you asked for, not that those bytes are trustworthy.
- Supply-chain compromise of a locked Python dependency.
- Denial of service as availability. Rate limiting and admission are
  protective controls here, not authorization controls, and no availability
  SLA is claimed — the creation paths and the public Postgres port are in scope
  as limits, above, and nothing else is.
- Availability under a neighbour's load. `THR-NOISY-NEIGHBOUR` is in the table
  above and its claim is narrow on purpose: **a neighbour's load is bounded,
  not a claim about availability**. Session 31 gives every project service a
  ceiling in memory, processes and CPU, and refuses a deploy that would not fit
  beside what is already here. Session 35 measured what a neighbour feels
  under one load (a saturated REST path moves the other project's p95 from
  ~54 to ~100 ms, with no error; workflow runs move nothing) and recorded it
  in the capacity envelope as a sample, not a bound. Disk I/O has no ceiling
  at all -- there is no `blkio` limit and the two projects share one device.

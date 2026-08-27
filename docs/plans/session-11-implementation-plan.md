# Session 11 — Deployment convergence, operational diagnosis, and a README that is true

A deploy that reports every missing prerequisite before it touches anything, a
diagnostic command that answers whether a *deployed* system is well, one request
id that survives from the edge's access log to a durable audit row, and a README
that a stranger can follow on an empty machine.

**No prerequisite discovered halfway. No check that prints a secret. No
correlation that is only half a join. No documentation that describes a release
this repository has not shipped for eight sessions.**

---

## 0. Where Session 11 actually starts

Session 10 closed with `evidence/session-10.json` merged at `3ab7051`: **53
claims, 51 passed, 2 failed**, and `314362c` adds D511's repair on top. Local and
host are identical, everything is pushed, and every gate is green. Both projects
run Session 10 with **21 migrations**, outputs **v13**, **156 ADRs**, 16
containers, an encrypted pgBackRest repository per project, a WAL stream and a
restore drill that has been run against a real deployment. `CURRENT_SESSION` is
**10** (`src/agentic_postgres/__init__.py:47`).

**The two red claims are the rotation window**, red for a fifth session:
`api_authorization` (`SEC-ANON-001`, `SEC-PRIV-001`, `SEC-ROLE-001`,
`SEC-DOCS-001`) and `bootstrap_identity` (`SEC-BOOT-001`), whose every unrun node
id is an `APG_ROTATED_*` proof (`src/agentic_postgres/evidence_claims.py:139-140`).

**There is no Session 11 runbook.** The prior sessions had one; Sessions 11 and 12
do not. What this session has instead is the user's session summary — quoted
verbatim into §1's first column and never edited, the same discipline Session 10
applied to the digest-pinned `docs/source-specification.md` — plus §17's Session 11
paragraph.

**The current codebase is the source of truth, not the summary.** That is the
standing instruction for these last two sessions, and it is what makes §1 longer
than usual: this session's subject is the operator surface, and nine sessions have
been building an operator surface. Most of what the summary asks for exists.

### Three decisions taken before the plan was written

1. **The fresh-host rehearsal runs on a disposable local VM**, not the live VPS
   and not a second rented one. `62.238.99.122` already runs two projects and is
   not empty; a third project there would prove *"a fresh project on a working
   host"*, which is a strictly narrower claim than `DEP-001` makes. A throwaway
   Ubuntu VM is genuinely empty and genuinely destroyable.
2. **Migration 0022 is in scope.** D500 — the `database`-source audit row carries
   no `request_id` — is closed here, because without it `OPS-LOG-001`'s audit leg
   is half a join: the two rows describing one MCP write would still be matched by
   agent, tool and time.
3. **The rotation window is closed here, as its own run.** It is the oldest
   carried-in item, it is a rotation exercise rather than a code change, and this
   is the operations session.

### Five things that are already true and change the shape of the work

1. **`deploy.sh` is already the orchestrator the summary asks for.** `deploy.sh`
   (257 lines) hands off to `bin/deploy-project.py` (2,395 lines), which runs an
   ordered convergence: render → preconditions → install the release → root-owned
   configuration → start the data plane holding back the deferred set → **6**
   bootstrap and migrations → **6b** the deferred services → **6c** stanza and
   `pgbackrest check` → **7** publish the deployed document → **8** observe. It
   waits for readiness through `observe_health`, `observe_docs`, `observe_app`,
   `observe_api`, `observe_mcp` and `observe_tls`, and it applies dbmate
   migrations from the rendered set it installed.
2. **`bin/doctor.sh` is still Session 1.** 150 lines of tool presence, interpreter
   version and repository shape. Its own header says so: *"runbook §8.6 OPS-001
   later extends it to a deployed system."* Nothing has.
3. **The request id already exists for three of its four legs.** The MCP runtime
   mints a uuid4 per HTTP request (`services/auth-api/app/mcp_authorization.py:144`),
   forwards it as `X-Request-Id` on every upstream call
   (`mcp_query.py:78` defines the header, `mcp_upstream.py:205, 340` send it),
   logs it structurally through the `apg.mcp`
   logger (`mcp_telemetry.py:63, 97`), and writes it to the `agent_plane` audit
   row. Traefik's JSON access log already **keeps** `X-Request-ID` by name
   (`infra/edge/traefik.yaml:94-107`), and `edge-probe` already mints one when a
   caller sends none (`services/edge-probe/probe.py:58`).
4. **The connection surface, the reference page and the examples are done.**
   `bin/connect.sh` is 697 lines across six commands and prints no password under
   any flag (D105); `services/docs` serves a vendored Scalar bundle from a
   first-party server chosen for the CSP (ADR 0069) across two surfaces (ADR
   0087); `services/clients/{psql,psycopg,node-pg,prisma}` are the examples.
5. **`README.md` says "Status: Session 3 of 12 complete."** It lists `bin/connect.sh`
   as Session 4 and unavailable, object storage as Session 7, backups as Session
   10 — all three deployed and proved. The exit criterion of this session is that
   a developer can follow the README, and the README describes a release this
   repository stopped being eight sessions ago.

---

## 1. Divergences from the session summary

Six columns, the house shape. The "Summary says" column quotes the Session 11
brief verbatim. Rows are predictions made at plan time; each is confirmed,
corrected or replaced during implementation, and anything found *during*
implementation is appended with the next free number.

**Next free number after this table is D672.**

| # | Summary says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D606** | "`deploy.sh` should progress from a development helper to an idempotent orchestrator that validates prerequisites, renders configuration, starts services, waits for readiness, applies migrations, reloads API metadata, runs smoke tests, and prints usable connection information without exposing secrets." | **All of it exists except the first clause.** `bin/deploy-project.py` is an eight-step convergence with a deferred-service split (ADR 0063/0133), a backup check that fails the deploy with a named reason (step 6c), a schema-cache reload channel, and an `observe_*` family that waits on every surface. | **Session 11 adds the preflight and nothing else to `deploy.sh`.** The remaining clauses are recorded here as already-satisfied and are not re-specified. | A plan that re-specified a built orchestrator would produce a run whose only possible outcome is churn on a file eight sessions have converged. The summary was written before the sessions that built it. | — |
| **D607** | "runs smoke tests" | **Step 8's `observe_*` family is the in-deploy smoke.** `bin/smoke-test.sh` is a separate, deliberately thin delegator to `pytest -m "contract and not future"`, and its own header forbids it growing a second definition of "the tests that matter now". | Neither changes. The plan states which artefact is "the smoke test" so a later reader does not add a third. | Two definitions of the same thing is the defect this repository names most often. The one that matters at deploy time is the one the deploy runs. | — |
| **D608** | "document `bin/connect.sh`" | **It is documented in three pages** — `docs/database-connections.md`, `docs/client-compatibility.md`, `docs/pool-operations.md` — and its own 50-line header states the six-command split and the no-password rule. | No work beyond linking it from the README and the new index. | — | — |
| **D609** | "Produce permission-safe `outputs.json`" | **Every rendered file has been `0600` since Session 1**, it is a tested contract, and ADR 0154 settled the remaining question (the render decides a rendered file's mode, the install decides its owner). The *deployed* document is `0600 root` for a stated reason (`deployed_output.py:661-667`). | Done. Recorded so the run does not re-open it. | — | 0154 |
| **D610** | "FastAPI Scalar page" | **The page exists and is deliberately not served by FastAPI.** `services/docs` is a first-party static server serving a fixed table of paths, because the Content-Security-Policy has to be ours — the Scalar bundle names `fonts.scalar.com` and `proxy.scalar.com` and `withDefaultFonts` defaults true (D202). | Done, and the summary's framing is corrected rather than followed. | ADR 0069 chose the build over an upstream image for this reason. Re-serving it from FastAPI would put the CSP back in a third party's hands. | 0069, 0087 |
| **D611** | "documentation index" | **`docs/` holds 30+ files and has no `README.md` and no `index.md`.** The README links a subset, and the subset it links is the Session 3 subset. | **A `docs/README.md` index**, generated is better than hand-kept if the run finds a source for it; hand-kept with a contract test that every `docs/*.md` appears exactly once, if not. | An index that goes stale is worse than none: it tells a reader the set is complete. The precedent is `docs/decisions/README.md`, which is indexed and checked. | — |
| **D612** | "admin scripts, examples" | **Both exist.** `bin/auth-admin.sh`, `bin/storage-admin.sh`, `bin/api.sh`, `bin/backup.sh`, `bin/restore-test.sh`, `bin/apg-diag.sh`; examples in `services/clients/{psql,psycopg,node-pg,prisma}`. | No new command. The work is that the README and the index name them. | — | — |
| **D613** | "runbooks" | **Nine operator guides exist** (`session-02` … `session-10`), plus `api-operations.md`, `backup-operations.md`, `pool-operations.md`, `database-connections.md`, `migrations.md`, `secret-handling.md`, `provider-bootstrap.md`, `host-baseline.md`. What does not exist is Session 11's. | `docs/session-11-operator-guide.md`, **derived by diff from Session 10's, never retyped.** | D505 and D507 were both flags lost to retyping the previous session's guide, and D602 was a step the page anticipated and never gave. Three failures, one cause. | — |
| **D614** | "complete prerequisite reporting … a missing prerequisite stops deployment before it changes anything, and lists every absent item" (`DEP-PRE-001`) | **Neither half holds.** The three checks — `require_edge_is_up`, `require_bootstrap`, `require_secret_generation` (`bin/deploy-project.py:441, 475, 494`) — run at **step 2, after step 1 has already rendered** into `.generated/<key>` and restored its ownership, and each calls `fail( defines the header;  send it)` on the first miss, so an operator missing three things learns about one, fixes it, and learns about the next. | **A step 0 preflight** that collects every absent prerequisite, reports them all with the command that supplies each, and returns before the render. Step 2's `require_*` stay exactly where they are as the second line — they also *return* the values the deployed document needs, which a preflight must not duplicate. | The two halves are separate claims and fail separately: "changed nothing" is proved by an unchanged filesystem, "listed everything" is proved by a report naming three absences when three are absent. One node id could report the first and be silent about the second. | needed |
| **D615** | "`doctor.sh`" | **Still Session 1.** Local tools, interpreter minor version against `.python-version`, repository paths, and the version lock. It does not know a deployment exists. | **A deployed mode**, checking: containers and their health, TLS and route resolution, the database and PgBouncer, migration status, backup and WAL freshness, R2 reachability, and disk headroom. The Session 1 checks stay exactly as they are and remain the default. | `OPS-001` is the requirement, and the command's own header has named it as the successor since Session 1. Widening the default would break `test_doctor_exits_zero_on_a_bare_invocation` in a checkout with no deployment. | needed |
| **D616** | — | **The deployed document is `0600 root`** (`deployed_output.write_deployed_document`, and the docstring says why: it is a map of where the secrets are). **And `tests/contract/test_root_script_policy.py:179-181` asserts `bin/doctor.sh` is not root-reachable** — *"a developer command nothing privileged calls."* A deployed mode needs to read a root-only file, and the read-only diagnostic account (`apg-agent`) reaches the host only through `apg-diag`'s eight allowlisted verbs. | **Decide in Run 3, do not discover on the host.** Three shapes: (a) `doctor.sh --project <key>` requires root, like `bin/backup.sh info`; (b) the deployed checks move to `bin/doctor.py` and `apg-diag` gains a `doctor` verb, which puts `doctor.sh` into the root-reachable closure and **flips the assertion above**; (c) the deployed mode reads the *rendered* document and asks the daemon for the rest. The ADR names one and says what the other two cost. | This is Question 5's shape before it happens: a decision (*doctor is unprivileged*) that was complete when written and becomes incomplete the moment doctor learns about deployments. Flipping a passing contract test needs an ADR and a docstring that says so (§6 non-negotiables). | needed |
| **D617** | "disk/WAL checks" | **Nothing measures host disk anywhere**, and `docs/host-baseline.md` records no disk figure at all — Session 10's §3 flagged this as unmeasured and it stayed unmeasured. For WAL there *is* an authority: `pg_stat_archiver`. | Disk headroom is measured and its threshold is **published, not typed** — derived from what a restore actually needs, which Session 10 measured (a restore materialises a second copy of the cluster). WAL freshness reads `last_archived_time` and `last_failed_time`, **never `failed_count`**. | **D553.** `pg_stat_archiver.failed_count` stood at **26 on a healthy, fully caught-up cluster**, because every project fails to archive until its stanza exists. `failed_count > 0` is the obvious status and would mark every project failing forever. A cumulative counter cannot answer a point-in-time question. | — |
| **D618** | "R2 access" | **`bin/backup.sh info [--json]` and `bin/backup.sh check` already exist**, and ADR 0149 already decided what a repository can honestly report. | **`doctor.sh` calls them; it does not re-implement them.** And it reads the *state field*, never the exit code. | **D548:** `pgbackrest info` **exits 0 for a stanza that does not exist.** Same defect as `postgrest --ready` returning 0 while every request 404s (D145), five sessions apart, in a different third party. The state was in a field, never in the exit code — both times. | 0149 |
| **D619** | "structured logs, request ID propagation" | **Three of four legs exist.** MCP mints, forwards, logs and records the id; Traefik keeps the header in its access log; `edge-probe` mints when absent. **What is missing:** the MCP boundary *always* mints and ignores any inbound `X-Request-Id`, so a caller's id never survives the hop; and the auth/storage HTTP routes emit no structured line at all — only `apg.mcp` does. | The MCP boundary **honours an offered id and mints only when none is offered**, validating it as a uuid before it is trusted. A structured per-request line in the auth/storage layer, in `mcp_telemetry`'s shape. | Without the first, the id in Traefik's log and the id in the audit row are two different uuids for one call, and `OPS-LOG-001` cannot be proved from a real request. The column is already `uuid` and not free text precisely so a caller cannot write a sentence into it (`migrations/templates/0019-…:85-86`) — validation is the enforcement of a decision already taken. | needed |
| **D620** | "audit records" (`OPS-LOG-001`: ingress, API, agent, **audit**) | **The `database`-source audit row carries no `request_id`** — D500. `api.create_note` and `api.update_task_status` insert `('database', …)` rows with the column omitted (`0019-…:253-260, 313-319`). Measured (Session 9 rig6): a forwarded header *does* reach the database in `current_setting('request.headers')::jsonb`. | **Migration 0022**, in scope by decision. Both write RPCs read the header and set `request_id`. | Migration 0020's own comment states the terms: *"the deployment test that asserts the `database` row's `request_id` IS NULL stays green and stays the thing that will fail on the day the repair lands."* This is that day, and flipping it is authorised by the run's ADR with the reason in the test's docstring. | needed |
| **D621** | "request ID propagation" across "ingress" | **D478: the request id stops short of ingress deliberately.** Traefik cannot mint one — v3.5 has no first-party request-id middleware and this deployment loads no plugins. | **Narrowed, not reversed.** Nothing at ingress mints. Ingress *records* the id the caller sent, which the access log already keeps by name; the runtime mints only when the caller offered nothing, and in that case the ingress line for that request carries no id and the plan says so. | An honest four-leg correlation for a caller that supplies an id beats a four-leg correlation that requires a plugin nobody has audited. The gap is stated rather than papered over: this is D600's family — a value that *looks* correlated is worse than one that is visibly absent. | needed |
| **D622** | "verbose-mode redaction tests" | Nothing verbose exists yet to test. The tempting proof is a denylist of secret-looking strings. | **A sentinel scan over the whole output.** The rig plants a known random value in every place a secret lives — the active generation, the deployed document, the environment — runs `doctor.sh` in every mode including verbose, and asserts no sentinel appears anywhere in stdout or stderr. The **control** is a deliberately leaky build that the same scan catches. | **D374:** a test can check a string its target cannot contain, and it passed for an unrelated reason — worse than a weak assertion. A denylist tests the denylist. | — |
| **D623** | "Documentation is finalized around actual commands and observed behavior" / "A developer follows the README from a clean environment without undocumented commands" | **`README.md` says "Status: Session 3 of 12 complete."** It lists `bin/connect.sh` as *"Session 4"* and unavailable, object storage as *"Session 7"*, backups as *"Session 10"*, and closes with a "Session 3 preview". Eight sessions of drift in the one document the exit criterion names. | **Rewritten to Session 11's truth** in Run 7: status, the ordered deploy sequence, the operator-guide table, what is genuinely unavailable, and the exit-code convention (which is already correct). **Derived by diff from what the tree does**, and every command in it executed before the run closes. | This is the exit criterion's own artifact. A rehearsal against a stale README measures the rehearsal, not the product. | — |
| **D624** | "A fresh-host rehearsal by following only the README" | **The VPS is not fresh.** `62.238.99.122` runs 16 containers and two projects on Session 10 with live backups. | **A disposable local VM** (Ubuntu, clean image, destroyed after), provisioned from `bin/provision-host.sh` following only the README. Recorded as a decision in §0 so a later reader does not read `DEP-001` as having been proved on the production host. | The claim is *"an empty host"*. A third project on a working host proves something weaker, and quietly narrowing a P0's meaning to fit the machine available is how a claim stops meaning what its id says. | — |
| **D625** | — | **A rehearsal cannot take a production certificate.** Failed ACME validations cap at **5/hour/hostname** and the standing rule is *never retry in a loop*; the VM has no public DNS record pointing at it. | The rehearsal runs against the **staging** resolver, which `infra/edge/traefik.yaml` already configures, and stops before promotion. The plan says so before the run, not during it. | A week lost to a rate limit is the documented cost, and it has already been paid once in this project's history. | — |
| **D626** | "Re-running deploy is non-destructive and convergent" (`DEP-002`) | **Three convergence modules exist and none of them measures a redeploy.** `test_session3_convergence.py`, `test_session4_convergence.py` and `test_session5_convergence.py` measure container restart, unit restart, reboot recovery and credential rotation — every one a *restart* or a *rotation*. Nothing runs `deploy.sh --through-session N` twice and checks the rows. | A new proof: write a sentinel row through the product's own route, redeploy, read it back — **with a control that the redeploy actually ran**, because a redeploy that silently did nothing preserves every row. | Question 1: *what would have to break for this to go red?* Without the control, a no-op deploy is indistinguishable from a convergent one, and the test would be green for the wrong reason forever. | — |
| **D627** | — | **`.github/workflows/ci.yml:134` still asserts `CURRENT_SESSION == 2`.** D525 recorded it in Session 10; it is now wrong by **eight** sessions, and has reddened nothing. | **Recorded again, not silently bumped.** The repair is to derive the number the way `bin/session-01-check.sh` does, and it belongs with ADR 0019's unbuilt CI job. If Session 11 takes it, it takes it as a named run item with the derivation, not as a literal edit. | A literal that has been wrong for eight sessions and reddened nothing is evidence about the *job*, not about the number. Bumping it destroys the evidence — which is exactly what D525 said, and it is still true. | — |
| **D628** | — | **The rotation window has kept two claims red for five sessions.** Every unrun node id under `api_authorization` and `bootstrap_identity` is an `APG_ROTATED_*` proof (`tests/conftest.py:117-128`), consumed by `test_session4_convergence.py:455` and `test_session5_convergence.py:437, 498, 549`. | Closed in Run 10, as its own run. Three rotations; each proof is given the value the window **replaced**, so the file is written **before** the rotation. | The known trap is D253 and it has no code fix: **a rotated credential does not reach a running process on its own.** A container that mounts one needs `project-runtime.sh … down` before the deploy, because `resume` runs `compose up` without `--force-recreate`. ADR 0155 closed the *content-digest* half; the credential half is still a step. | — |
| **D629** | — | **A deployed-document reader is guarded as a class** (D600). `test_no_operator_command_reads_a_key_the_deployed_document_does_not_have` (`tests/contract/test_container_selectors.py:280`) scans every such module against `$defs.deployedDocument` in the schema. | `doctor.sh`'s deployed mode is one of those readers from its first line. It derives from `project.key` through `naming` and reads no key the schema does not have. **If a check needs a value the document does not carry, that is an outputs-version question, not a `.get(…, {})`.** | **D600 is the dangerous member of its family**: a `release` read from a block no document kind has, wrapped in `or {}`, wrote `null` into every drill evidence document and passed the whole host gate with all five recovery claims green. The repair was the class, not the field. | 0146 |
| **D630** | Run 1 item 4: "what `pg_stat_archiver` looks like on a healthy cluster and on one whose archive command is broken, so the freshness threshold is derived rather than guessed." | **Already measured, and already implemented.** D534 measured it over 60s with a control — `archive_command=/bin/false` gave `failed_count` 11→15→26 with `archived_count` **0** and `pg_wal` 5→6→11, against a `/bin/true` control that stayed flat at 4. D553 refined it. And `backup_report.archiving_is_failing` **already ships the predicate this run was going to derive**, with rig 7 arm G's three rows in its own docstring: *"Timestamps, never the counter."* | **No rig. `doctor.sh` calls `archiving_is_failing`; it does not re-derive a threshold.** D617's "reads `last_archived_time` and `last_failed_time`, never `failed_count`" is not a thing to build — it is a thing to import. | **This is D57/D262's pattern, caught instead of paid for.** Session 8 re-measured how PostgreSQL grants `EXECUTE`; Session 3 had measured it three sessions earlier in more detail. The §5 grep is the only thing standing between this plan and a run spent re-deriving a shipped function, and here it earned its place on the first run of the session. | 0150 |
| **D631** | Run 1 item 1: "a preflight that cannot reach the daemon must report that as an absence rather than crash." | **`deploy-project.run()` passes no `timeout=`** (`bin/deploy-project.py:159-161`), and *refusal is not the failure mode that matters.* Measured: a non-existent socket, a closed local port and an unroutable address **all fail in ≤0.03s** with a usable stderr — the easy cases are already fine. A listener that **accepts the connection and never answers** hangs `docker ps` **past 20s**, with no output and nothing to report. | **The preflight's daemon call takes an explicit timeout**, and an expired call is reported as an absence with its own wording — "could not reach the Docker daemon within Ns" is a different sentence from "the daemon refused". | A wedged dockerd, a firewall that DROPs, and a daemon under load all present as accept-then-silence, and that is precisely the case a deploy is run during. **The first blackhole arm did not construct a blackhole** — `10.255.255.1` came back in 0.03s — and the rig was rewritten to accept the connection itself and *measure the accept* before trusting the timing. D605's rule, applied to the rig that was written to obey it. | needed |
| **D632** | Run 1 item 2: whether the forwarded header is readable inside a `SECURITY DEFINER` function with a restricted `search_path`. | **It is, and the absent case is SQL `NULL` rather than the empty string.** Measured through PostgREST at the pinned digest, through a role switch, **behind a `db-pre-request` hook** that sets three GUCs of its own: `x-request-id` reads back exactly; a capitalised lookup key reads `NULL` **in the same request** the lowercase one succeeds; a header sent as `x-ReQuEsT-iD` on the wire still reads under the lowercase key. From `psql`, with no request at all, `current_setting('request.headers', true)` is `NULL` and does not raise. The hook sees the header too, and does not disturb it. | Migration 0022 reads `current_setting('request.headers', true)` — **two-argument form** — and looks up `'x-request-id'`, lowercase, **with no `nullif(…, '')`**. | The repository's standing idiom is `nullif(current_setting(…), '')`, because an unset GUC reads as the empty string. **That is true of a GUC the hook sets and false of a jsonb key lookup**, which returns SQL `NULL` for an absent key — measured, both ways, in one call. Copying the idiom here would guard a case that does not occur and hide the one that does. | — |
| **D633** | Migration 0020's note: closing D500 "means replacing both write RPCs", framed as a correlation improvement. | **An unguarded cast does not merely fail to correlate — it destroys the write.** Measured: a function that inserts a row and *then* casts a caller-supplied `X-Request-Id: not-a-uuid` raises `22P02`, PostgREST answers **400**, and the table holds **zero rows**. The note is gone. The well-formed control committed 1 note and 1 audit row in the same invocation, and a `NULL` candidate (no header at all) casts to `NULL` at 200 — so only the *malformed* path is dangerous. A regex shape-test before the cast returns 200 with `NULL`. | **Migration 0022 guards the value before it reaches the cast.** A header that is not a uuid records `NULL` and the write proceeds. | **Two independent reasons, and either alone is sufficient.** The audit record's convenience must never be able to fail the operation it audits — ADR 0141 makes a *write* fail closed on *its own* audit record, which is not the same as letting a caller's malformed header roll back a user's note. And ADR 0139 requires a write refusal to be **translated** from the product's own `PT` errcode, never relayed: a raw `22P02`/400 is the relayed status that ADR exists to forbid. **Question 5 in its purest form** — migration 0019 chose `uuid` so a caller could not write prose into the column, and that decision was complete while the only writer was the runtime. It became incomplete the moment the value came from a header the caller controls. | needed |
| **D634** | Run 1 item 3: "what disk a container reports for a bind-mounted volume, and whether the number a check reads is the number that fills up." | **The container's reading is faithful, and `/` is faithful here for a reason that does not generalise.** Measured: a 512 MiB ballast (`stat` confirmed **536,870,912 bytes** before anything was read back) moved the container's view of the named volume by **exactly 524,288 1K-blocks** — and moved `df /` by the *same* number, because the overlay and the volume sit on one device on this machine. | **The check reads the mount point the database writes to, never `/`.** | D374's family: a proof that passes for an unrelated reason. A check reading `/` is correct here and would be reading a different filesystem the moment a host puts `postgres-data` on its own device — and it would keep reporting a number, which is worse than reporting none. | — |
| **D635** | — | **The host-versus-container half is not answerable on this machine.** `docker info` reports a root dir of `/var/lib/docker` and this shell **cannot stat it**: Docker Desktop runs the daemon inside its own VM, so a host `df` and a container `df` here are measurements of two different kernels. The rig reported `n/a` rather than a number. | **The comparison moves to Run 9's host trip**, where dockerd runs natively. Run 3 writes the check against the container-side reading, which is measured and faithful; the host cross-check becomes a `host`-mode node id. | D605 once more, one layer up: the environment is where a construction silently fails. **A number measured here and published as "the host's" would be a value that looked measured and was not** — §7's whole defect pattern, and the one this project produces most. Reporting `n/a` is the honest output of a rig that cannot answer. | — |
| **D636** | ADR 0157 as drafted: the two filesystem checks are "always determinable", because "a filesystem read needs nothing from the daemon". | **`Path.exists()` raises on `EACCES`.** It swallows `ENOENT`, `ENOTDIR`, `EBADF` and `ELOOP` and lets a permission error through. Both state roots are `0700 root`, so a smoke run of `observe_prerequisites` as an unprivileged user did not report four verdicts — it **raised `PermissionError`** on the third and printed nothing at all. | **Every `exists()` in the probe is guarded, and an unreadable file is `undetermined` rather than `absent`.** The vocabulary the ADR introduced for the daemon turned out to be the right vocabulary for a `stat`. | The deploy runs as root, so this could never bite in production — which is precisely §7's pattern: *correct for exactly as long as its wrong answer coincides with the right one*. The honest verdict matters more than the crash: "run `materialize-secrets.sh`" is the wrong instruction for a generation that is present and merely unreadable, and re-materialising is **not free** — it writes a *new* generation. **Found by running the thing, not by reading it**, one step 0 into a run whose whole subject is reading before acting. | 0157 |
| **D637** | D600's repair: *"the repair was the class, not the field"* — `test_no_operator_command_reads_a_key_the_deployed_document_does_not_have` scans every reader against the schema. | **The class guard's reader list is hand-maintained.** `DEPLOYED_DOCUMENT_READERS` is a four-entry tuple, and a new reader is covered only if somebody remembers to add it — which is the same failure mode the guard exists to prevent, one level up. **`test_cli_contract` solves exactly this problem one file over**: `test_every_command_in_bin_is_covered_by_this_module` diffs `bin/` against its own lists and fails on anything unlisted. It caught `bin/doctor.py` within a minute of the file existing. | **`bin/doctor.py` is added to the tuple, and the weakness is written down rather than repaired.** Discovery was tried and rejected: **33** files under `bin/` and `src/` read some `document["…"]`, and nearly all read a manifest, a bootstrap state or an OpenAPI document. | A scan matching those would trade a precise guard for a vague one — the exact trade `_top_level_document_reads` already refuses one level down, in a comment. **What is genuinely missing is a completeness check, not a discovery scan**, and `test_cli_contract`'s is the model: it needs a way to say "these files are handed a deployed document" that is cheaper to keep true than the tuple. Nobody has one. | 0158 |
| **D638** | The plan's Run 3: *"containers and health, TLS and route resolution, database and PgBouncer, migration status, backup and WAL freshness, R2 access, and disk headroom"* — seven families, read as seven live checks. | **Four of the seven already have a `status` field in the deployed document**, and echoing them would have been the obvious implementation: `backup_state.status`, `tls.status`, `mcp.status` and `database.observed` are all published, all well-formed, and all recorded **at deploy time**. A project deployed three weeks ago whose archiver died yesterday publishes `backup_state.status: ok` until its next deploy. | **The document supplies identities; every verdict is a live read** (ADR 0158). `test_the_doctor_reads_no_status_block_off_the_deployed_document` asserts it as a class over `bin/doctor.py`'s AST. | The schema settles it rather than taste: `backupState` carries `wal_archived_count` and `wal_failed_count` and **no timestamps**, so a doctor reading the document for archiver health has only the cumulative counter D553 measured at **26 on a healthy, fully-caught-up cluster**. The document is *structurally incapable* of answering the question it appears to answer — and a check built on it would have been green, plausible, and wrong for as long as nobody redeployed. | 0158 |
| **D639** | D622: *"the rig plants a known random value in every place a secret lives … and asserts no sentinel appears anywhere in stdout or stderr."* | **The first rig returned non-zero for every stubbed command, so every probe took its early-return branch.** Nothing reached a parsing path, nothing reached a formatting path, and the leak scan was reading seven "could not be measured" strings. **It passed.** | **Every structured channel now answers realistically** — a `docker ps --format` line, a `pg_stat_archiver` row, a `df` table, `backup.sh info --json` — and `test_every_probe_reached_its_parsing_path` asserts the report contains no `UNKNOWN`. A probe that stops parsing fails the premise before the leak scan is consulted. | **D605, in the file written to obey it**: *a rig that CONSTRUCTS a condition must MEASURE that it constructed it.* Caught only because a separate assertion about container names failed for the *right* reason — the leak tests themselves were green and would have stayed green. This is the same shape as ADR 0156's *"six green tests measuring nothing"*, and it is now two sessions running. | 0159 |
| **D640** | ADR 0159 as first drafted: *"never a byte a third party emitted."* | **Taken literally it forbids the most useful line the tool prints.** An unhealthy container's name arrives as `docker ps` stdout; a `last_archived_time` arrives as `psql` output. Both are bytes a third party emitted, and neither is a place a credential can appear. | **The rule is stated by CHANNEL, not by origin.** Integers, booleans, and fields read *by position* out of structured output whose shape this repository knows may travel. A command's **stderr**, its **unstructured stdout**, its argv and the environment never do. | The distinction is where credentials actually live: prose. `pgbackrest`'s error strings name repository paths and S3 keys; a `--format` column holds a name `naming` derived. A rule that banned both would have been obeyed by deleting the diagnosis — and the first version of the redaction test would have **certified a stricter rule than the code implements**, which is a green test measuring something nobody built. | 0159 |
| **D641** | — | **`test_commands_do_not_echo_a_planted_environment_variable` was written when `doctor.sh` had one mode**, and it invokes each command bare. `--verbose` — the one flag whose entire purpose is to print more — was outside it. | The test takes invocations rather than command names, and `bin/doctor.sh --verbose` is one of them. | **Question 5, caught by asking it rather than by a leak.** The decision *"no command echoes its environment"* was complete when every command had one mode; it became incomplete the moment one grew a second. Five instances in Session 7, three more in Session 9 — and the cheapest place to find the ninth was a guard that already existed and was quietly covering less than its name claimed. | 0159 |
| **D642** | This plan's Run 5: *"the MCP HTTP boundary honours an inbound `X-Request-Id` and mints only when absent."* | **The code had already refused that, with a reason.** `mcp_authorization._Held`'s docstring: *"It is this process's own mint and never a caller value — nothing reads a request id off an inbound header, because an id a caller chose would let two agents' records collide on purpose."* The plan proposed reversing a documented decision without citing it. | **The decision stands and the plan is wrong.** Nothing reads an inbound id. | The stated reason is sharper than it looks: `request_id` is not a key, so a collision corrupts nothing — what it does is let one agent **stamp its actions with another agent's id**, so an operator reading the trail by request sees a second agent's writes inside a first agent's request. Audit-trail poisoning, by a caller, into the record that answers *who did that*. And D633 measured the other half one run earlier. **Two distinct defects from caller-controlled values in this field, in two runs.** | 0160 |
| **D643** | D478: *"the request id stops short of ingress, deliberately"* — read as a gap needing an inbound header to close. | **It closes on the way OUT, and D141 had already written down the measurement nobody made.** Session 5: *"whether `X-Request-ID` can be retained as a **response** field is measured against the locked digest before it is written, not read from a page."* Nothing measured it in six sessions. Rig E, against the locked `traefik:v3.7`: Traefik emits **three** namespaces — `request_`, `origin_`, `downstream_` — and the **shipped** policy keeps `downstream_X-Request-Id`. Controls: `request_Accept` dropped (drop-by-default in force) and `RequestPath` dropped (the `names:` block applied). | **The runtime stamps the id on the response; the edge needs no change at all.** | The ingress leg closes without trusting one byte a caller sent, and without a Traefik edit — so no edge restart and no ACME exposure on the host trip. The config's `X-Request-ID` matching the wire's `X-Request-Id` is Traefik folding case, **measured** rather than assumed (D274). | 0160 |
| **D644** | — | **`create_app` returning a wrapped ASGI callable breaks the application contract.** The first implementation returned `StampRequestId(application)` — the same plain-ASGI wrapping `create_mcp_app` uses. `bin/app-contract.py` calls `.openapi()` on that result and six test modules read `.routes`. | **`add_middleware`, and `create_app` still returns the `FastAPI`.** Ordering is explicit: Starlette makes the last-added outermost, so the log is added first and the stamp second. | Caught by running the existing suite rather than by review, and it would have failed at the *contract generation* step — `bin/app-contract.sh --check` — which is one of the things a gate runs and a reader trusts. A test now asserts the return type directly, so the next person who reaches for the ASGI wrapper is told why it is not used here. | 0160 |
| **D645** | — | **`test_the_id_does_not_survive_the_request` passed for an unrelated reason.** It called the app through `asyncio.run(...)` and then asserted `current_request_id() is None` from the test's own frame — but `asyncio.run` builds a fresh `Context` per call, so that assertion read a variable nothing had ever set. It was green whether or not `_CURRENT.reset` ran. | **Observed inside the same coroutine that set it**, immediately after the middleware returns — the only vantage point from which the reset is observable at all. | **Found by the battery as a SURVIVOR**, which is what a surviving mutation is for: M4 deleted the reset and the test stayed green. D374's shape — *a test can check a string its target cannot contain* — and it would have sat green forever guarding nothing. | 0160 |
| **D646** | — | **D498 is closed.** *"The id's propagation was proved and its uniqueness was not, because every offline test arranges a fixed id — a mutation replacing `uuid4()` with a constant left the whole suite green."* | Two arms now fail it: `test_two_requests_get_two_different_ids` drives two real requests, and `test_minting_twice_gives_two_values` is the narrow form that survives if the ASGI arms are ever removed. **Battery M2 is D498's exact mutation**, and it dies. | Two agents whose records share a request id are two agents an operator cannot tell apart — the same harm a caller-chosen id would do (D642), arriving from inside rather than outside. A uniqueness claim nothing could falsify was worth exactly nothing. | 0160 |
| **D647** | This plan's Run 6, and ADR 0161 as first drafted: the guard is a property of the two write RPCs. | **Two copies of one rule is how D500 happened in the first place.** 0019 asked *"does this path record a request id"* of the `agent_plane` writer and not of the `database` writer, and the answer diverged for two sessions. Writing the header read into both RPC bodies would set the same trap for a third write RPC, whose author would inherit whichever copy they read. | **One helper — `app_private.agent_request_id()` — called by both.** `STABLE`, `SECURITY INVOKER`, `REVOKE ALL … FROM PUBLIC`, granted to nobody: it needs no privilege of its own and executes as the owner of the `SECURITY DEFINER` function that calls it. A test asserts neither RPC reads `request.headers` itself. | **Question 5 answered in advance rather than after the fact**, which is the first time this session has managed that. The pattern's five instances in Session 7 and three in Session 9 were all found *after* a decision's second caller had already diverged. | 0161 |
| **D648** | — | **The rendered fixture is what a cluster receives, and the battery's first design mutated only the template.** The contract tests read `.generated/*/migrations/`, so an arm that edits `migrations/templates/` without re-rendering measures the *previous* bytes — every arm would report a survivor for a mutation that never reached the code under test. | **The render runs inside the battery loop**, once per arm, and again on restore. An arm whose mutated template fails to render is reported as **defective** rather than as a kill: a renderer refusing the input says nothing about whether the tests would have caught it. | D269's shape — *an unapplied mutation reports as "expected FAIL got PASS", which reads as a weak test and means the mutation never happened.* Caught while writing the battery rather than by reading its output, because the same trap cost Run 4 an ERROR-versus-FAILED false kill one run earlier. | — |
| **D649** | ADR 0160: *"a caller may still send `X-Request-Id` … and **it is used for nothing**."* | **Migration 0022 uses it.** A caller reaching PostgREST directly — bypassing the MCP plane, which ADR 0135 already contemplates — supplies the header that becomes its own `database` row's `request_id`. ADR 0160's sentence was true of the *runtime*, not of the database. | **Recorded as a stated residual in ADR 0161, not silently reconciled.** The caller cannot forge `agent_id` or `owner_id` — both come from GUCs the pre-request hook set, which is the whole of `SEC-PARAM-001` — so this is ADR 0135's conceded *"an agent can add noise to its own audit record"*, and the noise is **visible**: such a row still carries its own `agent_id`, so an operator joining by request id sees the mismatch rather than being fooled by it. | It is strictly narrower than D642's refusal and consistent with it: D642 refused letting a caller's id become **the runtime's own**, because the `agent_plane` row is this deployment's authoritative record of what it did. **The operator guide must say to check `agent_id` beside `request_id`**, and that sentence exists because this row was written rather than because somebody noticed later. | 0161 |
| **D650** | This plan's Run 7: the README is *"derived by diff, not retyped"* (D505, D507, D602), which reads as a discipline sufficient to avoid those defects. | **The derived README still contained four lines a reader could not run**, and every one was found by *executing* the command rather than by reading it: `migrate.sh --project` takes a manifest **FILE** and the draft passed a key; `connect.sh tunnel` also requires `--ssh USER@HOST`; `restore-test.sh` takes `--project-dir`, not `--outputs`, and prose said otherwise; and one line told a reader to run `--help` instead of the command. | **Fixed, and the class is guarded**: `test_every_flag_the_readme_shows_appears_in_that_commands_usage` runs each named command's `--help` and refuses a flag it does not document. The README also now states, in one paragraph, that four commands name a project four different ways. | *Deriving by diff avoids losing what the previous page said; it does not check what the current page claims.* D505 and D507 were flags **lost**; these were flags **invented or omitted**, which the same discipline does not catch. **The scan catches inventions and cannot catch omissions** — an absence is not a token — and that half is Run 8's rehearsal, said in the test's own docstring so nobody reads it as covering both. | — |
| **D651** | The README, every session since Session 1: *"All three generated files are mode `0600`."* | **Four files are generated and one is `0444`.** `PGBACKREST_CONF_MODE = 0o444` deliberately — `build_pgbackrest_conf` omits every credential option by construction and uid 999 must read the file. The README's claim was true when three files were generated and false from the moment Session 10 added a fourth. | The README states both modes and why the second is not the first. | Found by running `find -printf '%m'` over the rendered directory rather than by reading the sentence, which is the same method that found D650 four lines earlier. | 0154 |
| **D652** | `bin/render-config.py`'s closing line — the one sentence printed after **every** render: *"Wrote …/{outputs.json,compose.env,pgbackrest.conf,rendered-summary.txt} (mode 0600)."* | **It names `pgbackrest.conf` and claims a mode the renderer has never given it.** Session 10 added the filename to the list and left the trailing `(mode 0600)` untouched, so every render since has printed a false statement about a file it had just written `0444`. | **The modes are read from `rendering.FILE_MODE` and `rendering.PGBACKREST_CONF_MODE`, never typed**, and a test asserts the two constants differ — otherwise it could not tell a derived claim from a typed one (D374). | **Question 5, in the most-read sentence this repository emits.** The claim was true when written and stopped being true when a file with a different mode joined the list it describes. It survived a full session and a host trip because nobody compares a message against a `stat`. | — |
| **D653** | `test_the_catalog_says_what_the_surface_deliberately_lacks` asserts `OPS-LOG-001` appears in the catalog's absence list — *"the request id does not span ingress."* | **Runs 5 and 6 closed both halves of that absence**, so the catalog correctly stopped saying it and the test correctly went red. It is the third sentence to leave that list, after *"No writes"* (Session 9 Run 3) and *"No durable audit from the runtime"* (Run 6) — **and each of the three was noticed by this same test firing.** | **Replaced by a stricter one**, authorised by ADR 0160/0161: the catalog must describe the span it now has, say that an inbound `X-Request-Id` is ignored, **and** carry D649's caveat that an operator correlating by request id reads `agent_id` beside it. Three ways to fail against the old one's one. | A test that only ever watches a list shrink is a test that stops meaning anything as the product grows into it. This one earns its keep precisely because it fires on the run that closes each absence — but the replacement has to be the positive claim, or the absence list becomes the only thing anybody asserts about the document. | 0160, 0161 |
| **D654** | Run 4 added `--verbose` to `bin/doctor.sh` and the run closed with lint, shellcheck and the affected suites green. | **`bin/doctor.sh` with no arguments exited 1 after four lines**, and had done since that commit. `check_command`'s last statement was `[ -n "${VERBOSE}" ] && printf …`; under `set -e` a function whose last command returns 1 returns 1, so the script died on the first tool it found while `VERBOSE` was empty. **`--verbose` was unaffected** — there the test succeeds — and `--verbose` is the mode Run 4 exercised. | An `if` block, and `test_doctor_reaches_its_own_conclusion` parametrised over **both** modes: exit in `(0, 3)`, a summary line, and the repository-shape section reached. | **Question 1 had no answer for this command's default path.** `test_cli_contract` checks `--help`, which returns before any check runs; the planted-environment test reads the output and not the status. So the README's *"confirm the workstation is ready"* step was broken for a whole run, on my own machine, and **only a rehearsal that ran it found it.** This is the same shape as D639 one run earlier — a mode exercised, a mode not — which makes it twice in five runs. | — |
| **D655** | README, *"Local bootstrap"*: `sudo apt-get install -y shellcheck jq`. | **The step before it is `git clone`, and a stock Ubuntu Server image has no `git`.** Measured: `bash: line 1: git: command not found` on the README's own first instruction. | `git` joins the install line. | The tool list was written for a machine that already had git, which every machine this repository has ever been developed on does. **A prerequisite you have never lacked is one you cannot see**, and it is the first line of the path a stranger follows. | — |
| **D656** | README: *"`--render-only` needs no host and no root, starts nothing, and contacts no provider."* Every clause true. | **It needs Docker.** The render validates the staged Compose model before publishing, so on a machine without it the command exits **5** with `compose: docker is not installed` — and publishes nothing. The README never asks for Docker, and `bin/doctor.sh` requires `docker`, `docker compose` and `docker buildx`. | The README asks for Docker and says why, and the `--render-only` paragraph names the dependency and the exit code. | Three true statements about what a command does *not* need read as a complete statement of what it needs. The absent fourth clause is the one that stops a newcomer. | — |
| **D657** | README: `bin/smoke-test.sh   # fast: active contract tests only`. | **Measured on a developer machine: 4,152 tests, 291 seconds**, and it starts real containers. "Fast" is true only against the gate. | The README states the measured count and duration, says Docker must be running, and shows the single-module invocation for use while working. | A newcomer reading *"fast"* runs it expecting seconds, waits five minutes, and learns the document's adjectives are not measurements. **The number was never measured before it was written down** — which is the same defect as a bound that is validated and reaches nothing (D519), in prose. | — |
| **D658** | This plan's Run 8: *"Provision a clean VM following only the README."* | **The rehearsal split cleanly in two, and only the first half is answerable without a VM.** Half A — clone, tools, interpreter, environment, `doctor.sh`, render, inspect — ran in a clean `ubuntu:24.04` container and produced D654–D657. Half B — `provision-host.sh`, the edge, providers, secrets, `--through-session` — hardens SSH, installs UFW rules and systemd units, and needs a real machine: a privileged container running systemd is a *different thing*, and a rehearsal against it would measure the proxy. | **Half A is done and its four findings are repaired. Half B needs a VM the operator supplies**, and is raised rather than faked. | D605's rule at the environment layer: *a rig that constructs a condition must measure that it constructed it.* A container cannot construct "a fresh host", and reporting a host rehearsal from one would be a value that looked measured and was not — §7's whole pattern, in the run written to find exactly that. | — |
| **D659** | `docs/session-02-operator-guide.md` step 1 and `docs/host-baseline.md`: three `--apply` passes, the second of which installs the SSH snippet. `host.yaml` names `ssh.operator_user`. | **`provision-host.sh` never creates that user, and no document says to.** The snippet sets `PermitRootLogin no`; the script writes a sudoers rule naming the operator and uses it as the `sshd -T` probe user, and creates nothing. On a fresh host where root is the only login — which is every provider's default — **pass 2 removes the only way in.** `useradd`, `adduser`, `authorized_keys`, `deployer` and "create the operator" appear in **none** of README.md, `session-02-operator-guide.md`, `host-baseline.md` or `new-team-member.md`. | **The step is written into the operator guide and the README**, before pass 2, with the key installation and the sudo grant. | **Measured, not inferred**: after pass 2 on the rehearsal host, `ssh root@…` is refused. I have access only because I created `deployer` first — a step I took because I read the script, not because anything told me to. The live host has `op`, created by hand long ago by somebody who never wrote it down. **A prerequisite you have never lacked is one you cannot see** (D655's lesson, at ten times the cost). The rollback timer is what stands between this and a dead machine, which is exactly what it is for. | needed |
| **D660** | The README's deploy sequence opens `sudo bin/provision-host.sh --host host.yaml`. The operator guide's *"Inputs you supply"* lists four manifests. | **Neither says how the repository or `host.yaml` reach the host**, nor that you must be inside the repository to run any of it. The transport is one line in `docs/handoff.md` — phrased as a *constraint* (*"no GitHub credential exists on the VPS"*) rather than an instruction — and in `CLAUDE.md`, which is the internal handoff and not operator documentation. | The `git bundle` + `scp` transport, with its per-release name and the commit confirmation, becomes a numbered step in the operator guide. | D602's shape — *a step the page anticipated and never gave* — at the very first action of the host path. Every prior trip started from a host that already had the repository. | — |
| **D661** | `docs/host-baseline.md`, the security baseline table: *"SSH \| Key-only. `PermitRootLogin no`, `PasswordAuthentication no` … **Source addresses restricted by `ssh.allowed_source_cidrs`.**"* | **Nothing restricts source addresses.** `allowed_source_cidrs` is schema-required, CIDR-validated and inspected for default routes — and consumed by no firewall rule and no sshd directive. `provision-host.sh` runs `ufw allow 22/tcp` with no source. The snippet has no `Match Address` block. **The code already knows**: `host_config.py`'s own docstring says *"the controls that actually carry the SSH boundary are key-only authentication, `PermitRootLogin no` and `MaxAuthTries`"*. | The baseline table's clause is corrected to match the code, which was right all along. | D519's family — a field validated and reaching nothing — but in a **security** document, where a reader is deciding what protects the machine. The manifest comment gets it right (*"defence in depth, not the boundary"*); the page an operator reads first does not. | — |
| **D662** | `host.example.yaml`'s header: *"Real deployment configuration uses the actual host address; **provision-host.sh --check proves the configured address is genuinely assigned to the host** before any mutation."* | **It does not.** `--check` ran against the unedited example — `expected_public_ipv4: 203.0.113.10` — on a host at 204.168.206.188 and reported 18 deviations, **none about the address**. The field's only uses are the `sshd -T` probe value and publication into the deployed document; `public_interface: auto` resolves from the **default route**, not from the declared address. | The claim is struck, or the check is written. **Writing it is cheap** — `ip -4 -o addr` against the declared value — and it catches "you pointed the manifest at the wrong host", which is a real operator mistake with a manifest that ships full of placeholders. | D274: *does the proof ask for what the artifact itself asks for?* The file asserts a safety check about itself that nothing performs, in the header of the one file every operator copies. | — |
| **D663** | **D655**, one run earlier: *"A stock Ubuntu Server image has no `git`. The README never asks for it."* | **The second clause is true and the first is wrong.** This Hetzner Ubuntu 26.04 image ships `git`. D655 was measured against `ubuntu:24.04`, the **container** image, which is far more minimal than any server image — and I generalised from one to the other in the sentence that stated the reason. | The repair stands (`git` belongs in the install line: the README asks a reader to clone and never asks for the tool). **The stated reason is corrected here.** | **D531's lesson, exactly**: *a prediction that reaches the right conclusion by the wrong mechanism is the thing this project is worst at noticing — it reads as a confirmed measurement forever after, and the mechanism is the part a future reader reuses.* One run later, in a row written under that discipline. | — |
| **D664** | Run 8's own prediction, made from reading `provision-host.sh`: it imports `agentic_postgres.config`, which needs `yaml` and `jsonschema`, so the `python3` fallback cannot work on a fresh host. | **Wrong.** Ubuntu's cloud image carries **PyYAML 6.0.3 and jsonschema 4.19.2** in the system interpreter, because cloud-init depends on them. `provision-host.sh` ran end to end on system `python3` with no venv anywhere. | Nothing to repair. **Recorded because a prediction that did not survive contact is evidence too**, and the next reader would otherwise re-derive the same wrong conclusion from the same imports. | The reasoning was sound and the premise was unmeasured. This is what §5 step 2 is for, and it is the cheap direction of being wrong. | — |
| **D665** | The arming command `provision-host.sh` prints after skipping SSH hardening. | **I retyped it from the ufw example and dropped its trailing backup-path argument.** The script then refused: *"SKIPPED SSH hardening: no rollback timer is armed"* — correctly, on a timer unit that existed under the right name. Two observations: the guard is real and discriminating, and **`--confirm-ssh-ok` still reported "SSH rollback disarmed" for hardening that never ran**, which is a message an operator could read as confirmation. | The second attempt **extracted the command from the tool's own output** instead of retyping it. The confirm-path message is worth narrowing to say what it confirmed. | **D505/D507's exact failure mode, committed by me, inside the session about it** — and caught by the product rather than by me. That the guard held is the more important half; a rollback that can be armed wrongly and still satisfy its check is the version of this that ends in a dead host. | — |
| **D666** | `docs/session-02-operator-guide.md` step 2: `bin/edge.sh --host host.yaml status   # redacted; readable without root`. | **Run without root, as documented, it reports `containers (not running)` while both containers are Up and healthy.** One line: `compose ps 2>/dev/null \|\| printf 'containers (not running)'`. Every failure of `compose ps` becomes that sentence — permission denied, no daemon, a malformed project — and `2>/dev/null` discards the reason. The commonest failure is the documented invocation itself: an unprivileged operator cannot reach `/var/run/docker.sock`. **Measured on the rehearsal host**: `docker ps` showed both healthy, `status` said not running. | A failed read reports **`(could not be read -- re-run with sudo)`**, and `test_status_never_reports_an_absence_it_did_not_measure` asserts the wording, because the wording is what an operator acts on. The third party's own text stays unprinted (ADR 0159). | **D145 and D548's shape, in this repository's own code**: `postgrest --ready` returns 0 while every request 404s; `pgbackrest info` exits 0 for a stanza that does not exist. Both were third parties. This one is ours, it is the exact thing ADR 0157's `undetermined` and ADR 0158's `unknown` were written to refuse, and **it predates both by nine sessions**. An operator who reads "not running" restarts an edge that is serving. | 0157, 0158 |
| **D667** | This run's own framing of leg 2 as *"edge + staging ACME"*, and the plan's *"Staging ACME; stop before promotion."* | **The edge requests no certificate.** `infra/edge/dynamic/baseline.yaml` carries no `certresolver` and no `Host()` rule; the only ACME reference in the edge Compose model is the state-directory mount. A certificate is requested when a **project** router with a TLS resolver exists — which is leg 3. *"The edge starts on staging ACME certificates"* means it is **configured for** staging, not that it obtains one. | **Leg 2 needs no DNS record**, and ran without one. The DNS requirement moves to leg 3, where the first project router appears. | Worth five minutes to establish, because the alternative was asking the operator for a DNS record the run did not need — and then reading a successful `edge.sh up` as evidence that ACME worked, which it is not. `443` answers **404** after leg 2: Traefik's own, with nothing routed, and §7's standing warning is that a routed 404 and Traefik's own are identical from outside. | — |
| **D668** | Run 2's step 0 preflight (ADR 0157) shipped with a mutation battery and offline tests, and its own `**Done.**` said *"that a refused deploy leaves the filesystem byte-identical needs root and a host, and it is Run 9's."* | **It ran on a real fresh host, and it was right first time.** `sudo ./deploy.sh --through-session 10` with the edge up and no providers: *"2 of 4 prerequisites are not satisfied. Nothing has been changed"*, `docker daemon` and `edge plane` **ok**, both absences reported **together**, each with a copy-pasteable command carrying the actual manifest paths — and `.generated/` empty afterwards. Exit **4** with root, **3** without. | Nothing to repair. Recorded because **a host-only proof that has never executed is this project's most expensive standing item**, and this one cost nothing to execute: the preflight refuses before touching provider state, so it needed none. | The first measurement of that exit code read **0** — the `$?` trap CLAUDE.md documents, hit for the third time in this session. Re-measured three ways with the status captured on the host: 4, 3, 4. **A wrong number that looks plausible is worse than no number**, and the difference between "my code is broken" and "my measurement was" is one careful re-run. | 0157 |
| **D669** | §0's decision 1 and §2: `DEP-001`'s live node id is *"the rehearsal"* — a fresh project deploying on an empty host — and Run 8's text scoped a deploy. | **Legs 1 and 2 are done; leg 3 is not, by decision.** Leg 3 needs a scratch Infisical project, two R2 buckets with their own tokens, and a DNS record, and it exercises the commands the live host already runs on every deploy. The findings-per-cost is the opposite of legs 1 and 2, which found nine things between them precisely because they touch code a working host never re-runs. And §9's stop condition 5 is explicit: *"a rehearsal that touches live provider state is not a rehearsal."* | **`DEP-001` is not claimed by Session 11.** Its placeholder stays `future`-marked, its offline half is proved and its live half carries to Session 12, where `DX-001` — *a developer who did not build this completes the documented path* — is a superset of it. | **The narrowing is written down rather than assumed**, which is the whole difference between a scoped decision and a quiet one. What Session 11 delivers instead is a documented path that is materially better than the one Session 12 would otherwise have tested: eleven divergence rows from the rehearsal, including a lockout that would have stopped `DX-001` at step 2 and a `status` command that reported a healthy edge as down. | — |
| **D670** | This plan's §2: *"Claims are a separate act… Session 11's claims are registered in `evidence_claims.CLAIMS` in the run that publishes."* Run 9 activates the node ids, so registering the claims beside them looked like one job. | **It is not, and the suite enforces the ordering.** `test_every_claim_belongs_to_a_session_the_release_has_reached` refuses any claim whose `claim_session` exceeds `CURRENT_SESSION` — which is **10** until Run 11 moves it — so all four Session 11 claims were rejected the moment they were added: *"deployment_preflight belongs to session 11, which this release has not reached."* | **Node ids in Run 9, claims in Run 11.** The intent is left in `CLAIMS` as a comment naming the four and why `DEP-001` is not among them, so Run 11 adds them rather than rediscovering them. | The guard is doing exactly what its docstring says: *a claim owned by a future session would be unprovable and permanently absent from the evidence of every session that can run.* §2 had already said "the run that publishes"; I read it as a note about sequencing rather than a constraint, and the test read it as a constraint. **The plan was right and I was the one who had to be told.** | — |
| **D671** | This plan's Run 9: *"Read each one's assertions before the trip, not at the terminal."* | **The first draft of `test_session11_operations.py` would have produced three more never-executed defective proofs**, and none of it was visible from reading the tests. `mcp_route`, `mcp_rpc` and `mcp_writer_session` are **module-local** to the Session 8 and 9 modules, not conftest fixtures, so every MCP-based test would have ERRORed on a missing fixture. `materialized_secret` takes **three** arguments, not two. `mint_token` requires a positional `role_name` I omitted. `api_call` returns a frozen `ApiResponse` dataclass and I unpacked it as a tuple. | **Rewritten against the fixtures that exist**, and `OPS-LOG-001` split rather than duplicated: its `agent_plane` ↔ `database` join is already asserted by Run 6's flipped test, and the leg with no proof anywhere — **ingress** — needs no agent, because `StampRequestId` wraps every application response. The audit is `pytest --setup-plan`, which resolves the whole fixture graph without running a body. | **Four wrong assumptions, caught by reading fixtures instead of tests.** This is the item CLAUDE.md calls the most expensive on its list — *nothing knows which proofs have never executed*, five defective across two trips — and the cheap half of the answer turns out to be one command. `--collect-only` would have caught none of them: it parses and resolves nothing. | — |

---

## 2. What Session 11 adds to the acceptance registry

The five requirement ids already exist and point at placeholders in
`tests/contract/test_future_deployment.py`:

| ID | Priority | What it must prove |
|---|---|---|
| `DEP-001` | P0 | A fresh project deploys on an empty host from documentation alone |
| `DEP-002` | P0 | Re-running deployment converges without destroying data |
| `DEP-PRE-001` | P0 | A missing prerequisite stops deployment before it changes anything, and lists every absent item |
| `OPS-001` | P0 | The diagnostic command reports every required check without secrets |
| `OPS-LOG-001` | P1 | One request ID propagates across ingress, API, agent, and audit records |

**Replace the placeholders; keep the ids and their descriptions**, rewriting a
description only to a *stricter* statement of the same property (ADR 0096, D422).

**Node ids are split where a description is broader than one test can carry**
(ADR 0089, D70 — a requirement whose description exceeds its node ids is a claim
the evidence file reports as passed):

| ID | Node ids it gains | Why split |
|---|---|---|
| `DEP-PRE-001` | *changes nothing* · *lists every absent item* | Two properties, two failure modes. A preflight that returns early and says one thing satisfies the first and not the second. |
| `OPS-001` | *coverage* · *redaction* · *shape offline* · *live host* | The redaction claim is not the coverage claim, and a check family present in a checkout is not a check family that ran against a deployment. |
| `OPS-LOG-001` | *agent-plane leg* · *database leg* | They fail for different reasons and one of them is migration 0022. Bundled, a green result would not say which leg worked. |
| `DEP-001` | *offline: every command the README names exists and resolves* · *live: the rehearsal* | The offline half is cheap, runs every gate, and catches the drift that made D623 possible. It is not a substitute for the live half. |
| `DEP-002` | one live node id, plus its control | The control is an assertion inside the same test, not a claim of its own. |

**Claims are a separate act.** Under ADR 0045 a requirement complete in a checkout
is not a claim; every claim needs at least one node id marked `live_host` or
`external`. Session 11's proposed claim keys, registered in
`evidence_claims.CLAIMS` in the run that publishes, with their rows in
`tests/contract/test_evidence_claims.py::CLAIM_INTRODUCED_IN`:

- `deployment_preflight` → `DEP-PRE-001`
- `deployment_convergence` → `DEP-001`, `DEP-002`
- `operational_diagnosis` → `OPS-001`
- `log_correlation` → `OPS-LOG-001`

**Grep the registry before adding any id.** ADR 0089 / D279: three of Session 6's
six "new" ids were already taken, and because `claim_session` derives from
`max( defines the header;  send it)`, one would have turned three earlier sessions' evidence red while the
other vanished from the gate.

**`claims_through_session` is cumulative**, so Session 11 still owes every Session
4–10 external claim — `transport_boundary`, `connection_tooling`,
`public_api_boundary`, `public_storage_boundary`, `public_agent_boundary`. The
external gate mode is not optional.

**And Run 10 turns two existing claims green** without adding an id:
`api_authorization` and `bootstrap_identity`.

---

## 3. Environment feasibility

| Requirement | Status | Note |
|---|---|---|
| A disposable VM with Docker and systemd | **Operator, out of band.** | Ubuntu, clean image. `bin/provision-host.sh` is what configures it, following only the README. |
| Public DNS for the VM | **Will not exist.** | So no production certificate. See the next row. |
| An ACME cycle on the VM | **Staging only.** | `infra/edge/traefik.yaml` already configures a staging resolver. Failed validations cap at **5/hour/hostname**; never retry in a loop. The rehearsal stops before promotion. |
| Infisical reachable from the VM | **Unmeasured.** | The control-plane identity holds org admin (standing open item). The rehearsal should use a scratch project, not the live one. |
| R2 reachable from the VM | **Unmeasured.** | The rehearsal's backup plane needs its own bucket and token, or it stops at the step before and says so. Decide in Run 8's preparation, not during it. |
| VM memory against `HOST_MEMORY_GUARDRAIL_MB = 1600` per project | **Sizing input.** | One project, so one guardrail. The VPS runs 4 GB with two projects and 16 containers. |
| VM disk for a full deploy plus a backup | **Unmeasured, and this is D617's other half.** | The rehearsal is the first thing that will ever measure it, which makes it an input to `doctor.sh`'s disk threshold rather than a consequence of it. |
| `doctor.sh` reading the deployed document | **Blocked on D616's decision.** | `0600 root`. Root, a broker, or a different source — Run 3 decides. |
| Running any of it over SSH without a TTY | **No.** | `sudo` on a host needs a TTY. `op` cannot reach the Docker daemon: `migrate.sh status/up`, `deploy.sh --through-session` and `--mode host` all need a human. `--mode offline` and `--mode external` do not. |
| Migration 0022 against two live projects | Available, and it is the deploy that applies it. | Fix-forward only; the down block raises AP900. |

**The unmeasured boundary that stays unmeasured:** how a deployment behaves under
concurrent load. `doctor.sh` reports state, not throughput, and the agent plane's
round trip is still untimed against any deployment (standing open item).

---

## 4. Safety plan for irreversible operations

Four operations cannot be undone by re-running a command.

**1. Releasing migration 0022.** Released migrations are fix-forward and every
down block raises AP900. It replaces the body of two `SECURITY DEFINER` functions
in a released write plane, so the risk is not the column — it is the two RPCs. The
safety is that the change is **additive to a nullable column**: a row that cannot
determine its request id writes `NULL`, exactly as every row does today, and the
write itself must not be able to fail for a correlation reason. `bin/migrate.sh
freeze-lock` in the same commit.

**2. The rotation window.** Three rotations against the live host, each of which
invalidates a credential in use. The safety is ordering and it is documented in
`docs/api-operations.md`: the proof's input file is written **before** the
rotation, because a window in which nothing rotated passes every refusal check —
the old credential is refused because it *is* the new one. After the signing-key
phase, **all four verifiers are recreated** (PostgREST, auth, storage, the agent
plane); ADR 0155 makes a mount-content change recreate a container, but the
credential half is still a step and D253 is the record of what it costs when it is
skipped.

**3. Provisioning the VM.** `bin/provision-host.sh` hardens a host, and its two
rollback timers exist so that hardening cannot lock the operator out. They are
part of the README path being rehearsed; if the rehearsal skips them the rehearsal
is not the README.

**4. Destroying the VM.** Deliberate, and the only irreversible step whose whole
point is to be irreversible. It happens after the run's divergence rows are
written, not before.

**The standing rules apply unchanged.** No secret value in source control, Compose
interpolation, process arguments, image layers or logs. `--render-only` keeps
working with no host and no root. Nothing privileged that mutates is piped over
SSH. `host.yaml`, `capabilities.yaml` and the project manifests are never
committed.

---

## 5. Build order

Runs are the unit. Each ends with the offline gate green on a clean tree, and
CLAUDE.md §5's procedure applies to every one: read the plan text and its
divergence rows, **measure anything the plan asserts about a third party with a
control that proves the rig can tell success from failure**, write the ADR if the
measurement decides something, implement, then try to break the tests.

**Runs 1–7 are offline. Run 8 is the VM. Runs 9–11 are the host trip.**

> **A host trip takes several rounds, not one.** Session 10's Run 11 cost seven
> deploy attempts. Budget for it here rather than discovering it at the terminal.

### Run 1 — Measure first

Throwaway rigs in `/tmp`, each with a control. **Grep the plans before each one**
— nothing indexes the ~605 measured facts by subject.

1. **What a preflight can observe before it writes.** Which of step 2's three
   checks can be answered without side effects, and what each costs. The trap: the
   Docker check *is* a daemon round trip, and a preflight that cannot reach the
   daemon must report that as an absence rather than crash.
2. **Whether `current_setting('request.headers')::jsonb ->> 'x-request-id'` is
   readable inside a `SECURITY DEFINER` function on the pinned image.** rig6
   measured that the header *arrives*; nothing has measured the read from inside a
   definer function with `SET search_path`. Control: a request with no such header
   reads `NULL`, not the empty string — the `nullif(current_setting(…), '')`
   idiom exists in this repository because an unset GUC reads as `''`, and header
   extraction may or may not behave the same way.
3. **What disk a container reports for a bind-mounted volume**, and whether the
   number a check reads is the number that fills up.
4. **What `pg_stat_archiver` looks like on a healthy cluster and on one whose
   archive command is broken**, so the freshness threshold is derived rather than
   guessed. D553 is the standing warning.

**A rig that CONSTRUCTS a condition must MEASURE that it constructed it** (D605).

**Done.** Four items, three rigs, six divergence rows (**D630–D635**). No code
changed; this run's whole output is measurements and the decisions they force.

*What it measured.*

**Item 4 never needed a rig** (D630). The §5 grep found D534's 60-second
measurement with its `/bin/true` control, D553's refinement, and — decisively —
`backup_report.archiving_is_failing`, which already ships the exact predicate
this run was going to derive, with rig 7 arm G's three rows quoted in its own
docstring. Session 10 built it. `doctor.sh` imports it. **The grep step earned
its place on the first run of the session**, and the alternative was a run spent
re-deriving a shipped function.

**Item 1 found a hang, but not where the plan looked** (D631). The easy failures
are already clean: a missing socket, a closed port and an unroutable address all
return in ≤0.03s with usable stderr. The dangerous one is *accept-then-silence* —
a wedged daemon, a DROPping firewall — where `docker ps` was still running after
20s, because `run()` passes no `timeout=`. **The first attempt at that arm proved
nothing**: `10.255.255.1` came back in 0.03s, which is a rejection, not a
blackhole. The rig was rewritten to hold the accepted connection itself and to
*print whether it had accepted one* before reporting any timing. D605's rule
applied to a rig written in obedience to D605.

**Item 2 answered cleanly and then produced the run's real finding.** The header
is readable exactly where migration 0022 needs it — through PostgREST, through a
role switch, behind a `db-pre-request` hook, inside `SECURITY DEFINER` with
`SET search_path = pg_catalog, pg_temp` — under the **lowercase** key only, with
a capitalised lookup and a never-sent key both reading `NULL` in the same request
as the internal negative control (D632). The absent case is SQL `NULL`, **not**
the empty string, so the repository's `nullif(…, '')` idiom does not belong here.

Then D633: **an unguarded cast does not fail to correlate, it destroys the
write.** A malformed `X-Request-Id` on a function that inserts a row and then
casts left the table with **zero rows** and answered 400. Migration 0022 was
scoped as a correlation improvement; it is one refactor away from letting any
caller roll back their own note with a header. Two ADRs already forbid the naive
version — 0141 (a write fails closed on *its own* audit record, which is not this)
and 0139 (a refusal is translated, never a relayed status; `22P02`/400 is exactly
the relayed status). **Question 5 in its purest form:** 0019 chose `uuid` so a
caller could not write prose into the column, and that decision was complete while
the only writer was the runtime.

**Item 3 split in half** (D634, D635). The container's reading is faithful — a
512 MiB ballast, `stat`-confirmed at 536,870,912 bytes before anything was read
back, moved the volume's available blocks by exactly 524,288. But `df /` moved by
the *same* number, because the overlay and the volume are one device here: a check
reading `/` would be right on this machine for a reason that does not generalise
(D374's family). And the host-versus-container comparison **is not answerable
here at all** — Docker Desktop runs the daemon in its own VM, so the two `df`
readings are of two kernels, and the rig reported `n/a` rather than a number.
That comparison is Run 9's.

*What it changes downstream.* Run 2 gains a timeout and a distinct message for an
unreachable daemon. Run 3 reads a mount point rather than `/`, imports
`archiving_is_failing`, and carries a host-mode node id for the disk cross-check.
**Run 6 gains a guard it was not scoped to have, and D633 is the reason** — the
ADR there now has to say what a malformed header records, not merely where a good
one comes from.

### Run 2 — `DEP-PRE-001`: the preflight

A step 0 in `bin/deploy-project.py` that collects every absent prerequisite and
reports them together, with the supplying command for each, and returns before the
render. Step 2's `require_*` stay where they are and keep returning the values the
deployed document needs.

Tests: three absences produce three lines; the filesystem is byte-identical before
and after a refused run (including `.generated/<key>` and the git index); a
present prerequisite is not reported. **Mutation battery** with a control the
mutations cannot reach.

**Amended by D631.** The daemon call takes an explicit `timeout=` and reports an
expired call in its own words — a daemon that *accepts and never answers* hangs
`docker ps` past 20s today, and "report the absence rather than crash" is not
satisfied by hanging. A refusal already fails fast and needs nothing.

**Proposed ADR 0157** — *a preflight reports every absent prerequisite and changes
nothing.*

**Done.** `src/agentic_postgres/preflight.py` (pure), `observe_prerequisites` and
`_observe_secret_generation` in `bin/deploy-project.py` (the probing), step 0 in
`main()` above the render, `tests/contract/test_preflight.py` (17 tests),
**ADR 0157**, and one divergence row (**D636**).

*What it measured.* Nine mutation arms, **9 killed, 0 survived, 0 defective** —
every control green in the same invocation and every arm `FAILED` rather than
`ERROR`, so each assertion was reached. The controls were picked to be
unreachable by their arms (D499): M2 mutates the daemon's *timeout* branch and is
controlled by a test that only exercises the *refusal* branch;
`test_a_multi_line_error_is_collapsed_to_one_row` carries three arms because
`_one_line` is touched by none of them.

*What the design turned into.* The plan asked for an aggregating check. The thing
that actually decided its shape was a dependency the plan did not name: **the edge
check is a question you ask the Docker daemon.** A list of booleans cannot
distinguish *"the edge plane is not running"* from *"nobody could ask"*, and would
print the first while meaning the second — D600's family, and it would have sent
an operator to restart a stack nobody examined. Hence three verdicts, and
`undetermined` blocks a deploy exactly as an absence does.

*What running it found that reading it did not* (D636). The first unprivileged
smoke run **raised `PermissionError`** instead of printing a report:
`Path.exists()` swallows `ENOENT` and **raises `EACCES`**, and both state roots
are `0700 root`. The deploy runs as root, so it could never have failed in
production — §7's pattern exactly. The repair was not just a `try`: an unreadable
file is `undetermined`, because "run `materialize-secrets.sh`" is the wrong
instruction for a generation that is present and merely unreadable, and
re-materialising writes a **new** generation. **The state introduced for the
daemon turned out to be the right state for a `stat`**, which is the strongest
evidence the three-verdict decision was correct rather than ornamental.

*What is deliberately not proved here.* That a refused deploy leaves the
filesystem byte-identical. That needs root and a host, and it is Run 9's — the
offline half asserts only the ordering that makes it possible. `DEP-PRE-001`'s
placeholder is untouched and still `future`-marked; **activation is Run 9's**,
because a requirement activated before its live half has ever executed is how
evidence starts lying.

### Run 3 — `OPS-001` part 1: `doctor.sh` learns about deployments

Decide D616 first and write its ADR before any code. Then the deployed checks:
containers and health, TLS and route resolution, database and PgBouncer, migration
status, backup and WAL freshness, R2 reachability, disk headroom.

Reuse, do not rebuild: `bin/backup.sh info --json` (ADR 0149), `bin/migrate.sh
status`, `bin/apg-diag.sh`'s verbs, `deployed_output`'s readers. Derive every name
from `project.key` through `naming` (ADR 0002). Read state **fields**, never exit
codes (D548, D145).

**Amended by D630, D634 and D635.** WAL freshness **imports**
`backup_report.archiving_is_failing` rather than deriving a threshold — Session 10
already shipped it. The disk check reads **the mount point the database writes
to, never `/`**: the two coincide on a developer machine, so a check reading `/`
passes there for a reason that does not generalise. And the host-versus-container
cross-check is a **`host`-mode node id**, because Docker Desktop's daemon lives in
its own VM and this machine physically cannot compare the two.

**Proposed ADR 0158** — *the diagnostic command's two modes, and which of them
needs privilege.*

**Done.** `src/agentic_postgres/diagnosis.py` (pure verdicts), `bin/doctor.py`
(the probes), `bin/doctor.sh --project` (the operator surface),
`tests/contract/test_diagnosis.py` (21 tests), **ADR 0158**, and two divergence
rows (**D637**, **D638**).

*What D616 decided.* **Option (a), and the assertion is kept rather than
flipped.** `sudo bin/doctor.sh --project <key>` runs the deployed checks *only*;
no arguments runs the workstation checks, unchanged. `test_root_script_policy`'s
claim — that no privileged **script** invokes `doctor.sh` — is still true, because
an operator typing `sudo` is not a script. What stopped being true is the
comment's premise, so a **stricter** test was added beside it:
`test_the_deployed_mode_cannot_reach_the_bare_python` asserts the `--project`
branch dispatches and `exec`s before any workstation check. That matters
concretely: under `sudo`, `secure_path` hides an activated venv, and
`check_python_minor` would report a false failure on every host. Option (b) —
an `apg-diag doctor` verb — was declined and its reason written into the ADR:
it is an authority decision about what an unprivileged account may see, D380 has
been open on that question for three sessions, and bundling it here would decide
it by accident. The checks live in `bin/doctor.py` so that verb stays cheap later.

*What the run actually turned on* (D638). The plan read as seven live checks.
**Four of the seven already have a `status` field in the deployed document**, and
echoing them was the obvious implementation — well-formed, plausible, and a
description of a moment that has passed. The schema is what settles it:
`backupState` has the two counters and **no timestamps**, so a document-based
archiver verdict is forced onto the counter D553 measured at 26 on a healthy
cluster. Hence ADR 0158's rule, and hence a test that asserts it over
`doctor.py`'s AST rather than trusting the author.

*What it measured.* Nine mutation arms, **9 killed, 0 survived, 0 defective**.
M1 — *an unknown check starts exiting 0* — is the one that matters: it is the
single edit that would turn the command back into D600.

*What it found on the way* (D637). D600's repair was "guard the class, not the
field", and the class guard's reader list is **hand-maintained** — a new reader
is covered only if somebody remembers. `test_cli_contract` solves exactly this
one file over, and its completeness check caught `bin/doctor.py` within a minute
of the file existing. Discovery for the document guard was tried and rejected:
33 files read some `document["…"]` and nearly all read a manifest. Written down,
not repaired.

*What is deliberately not proved here.* Every probe. Not one of these checks has
run against a deployment — they are **Question 2's shape**, and Run 9 is the
first time they execute. The offline half proves the verdicts and the command's
shape; nothing yet proves a `docker ps` filter matches a real project's
containers or that the `du`/`df` parsing survives a real `busybox` versus GNU
`df`. Read them before the trip.

### Run 4 — `OPS-001` part 2: verbose mode and redaction

A `--verbose` that prints more must not print more *secret*. The proof is D622's
sentinel scan with a deliberately leaky control build. Exit codes follow the
convention: `3` a missing local prerequisite, `4` missing runtime state, `6` a
check failed.

**Done.** `--verbose` in both modes, `Check.evidence` and `diagnosis._pairs`,
`tests/contract/test_doctor_redaction.py` (13 tests), **ADR 0159**, and three
divergence rows (**D639**, **D640**, **D641**).

*What the rule turned out to be* (D640). "Never a third party's bytes" was the
draft, and taken literally it forbids the most useful line the tool prints: an
unhealthy container's name arrives as `docker ps` stdout. So the rule is stated
**by channel rather than by origin** — integers, booleans and fields read *by
position* out of structured output may travel; a command's **stderr**, its
**unstructured stdout**, its argv and the environment never do. That is where
credentials actually live: prose. Had the draft stood, the redaction test would
have **certified a stricter rule than the code implements**.

*How it is enforced.* Structurally, not by review. `verbose` reaches the renderer
and no probe, so a probe cannot print more when verbose because it never learns
of it. `_pairs(**values)` takes *values* and does the `str()` itself, so a caller
cannot hand it something it was given. An AST scan refuses `.stdout`/`.stderr`
reaching any `diagnosis.*` call — which cost `probe_migrations` one extra line,
deliberately: `int(x.stdout)` cannot leak, but a rule a scan can check without
judgement is worth more than an exemption.

*What running it found* (D639). **The first rig returned non-zero for every
stubbed command**, so every probe took its early-return branch, nothing reached a
formatting path, and the leak scan was reading seven *"could not be measured"*
strings. **It passed.** It was caught only because a separate assertion about
container names failed for the right reason. D605 in the file written to obey it,
and the same shape as ADR 0156's *"six green tests measuring nothing"* — two
sessions running. `test_every_probe_reached_its_parsing_path` is now the premise,
and M5 of the battery kills it.

*What the battery established.* Five arms, **5 killed, 0 survived, 0 defective** —
and the first pass reported **M1 as ERROR rather than FAILED**, which is D386's
false kill. The mutation was malformed (a duplicate keyword argument), so the
module never imported and red meant "syntax error", not "leak detected". A
battery reading only red-versus-green would have counted it a kill. Repaired and
re-run.

*Also caught* (D641). `test_commands_do_not_echo_a_planted_environment_variable`
was written when `doctor.sh` had one mode. It now takes invocations, and
`--verbose` is one of them.

### Run 5 — `OPS-LOG-001` part 1: the id survives the hop

`AgentContextMiddleware._resolve` honours an inbound `X-Request-Id`, validating it
as a uuid, and mints only when none is offered. A structured per-request line in
the auth and storage HTTP layers in `mcp_telemetry`'s shape.

D621 is narrowed here and the narrowing is written into the ADR: nothing at
ingress mints, and a request that arrives without an id has no ingress leg — which
is stated rather than filled with a plausible value (D600).

**Proposed ADR 0159** — *a request id is honoured when offered and minted when
not; nothing at ingress mints one.*

> **Renumbered to ADR 0160.** Run 4's redaction decision took 0159. Run 6's
> proposed 0160 becomes **0161**.

**Done.** `services/auth-api/app/request_id.py`, `StampRequestId` on both planes,
`StructuredRequestLog` on the auth/storage plane, `_resolve` reading the stamp,
`tests/contract/test_request_id_stamping.py` (14 tests), **ADR 0160**, and five
divergence rows (**D642**–**D646**).

***This run's plan text was wrong, and the code said so before I did*** (D642).
The plan proposed honouring an inbound `X-Request-Id`. `mcp_authorization._Held`
had already refused that in a docstring, with a reason: *"an id a caller chose
would let two agents' records collide on purpose."* That reason is sharper than
it reads — `request_id` is not a key, so a collision corrupts nothing; what it
does is let one agent **stamp its actions with another agent's id**. D633
measured the other half one run earlier. Two distinct defects from
caller-controlled values in this one field, in two runs.

*So the id flows outward instead* (D643). And D141 had already written down the
measurement that makes that work, in Session 5: *"whether `X-Request-ID` can be
retained as a **response** field is measured against the locked digest before it
is written."* **Nobody measured it for six sessions.** Rig E did: Traefik emits
`request_`, `origin_` and `downstream_` namespaces, and the **shipped** policy
keeps `downstream_X-Request-Id` — with `request_Accept` and `RequestPath` dropped
as controls proving the arms are about the real configuration. **The edge needs
no change**, so the ingress leg closes with no Traefik edit, no edge restart and
no ACME exposure on the trip.

*What the suite caught* (D644). The first implementation returned
`StampRequestId(application)` from `create_app`, which changes what `create_app`
**is**: `bin/app-contract.py` calls `.openapi()` on it and six modules read
`.routes`. It would have failed at contract generation — a gate step. Repaired
with `add_middleware`, and a test now asserts the return type so the next person
reaching for the ASGI wrapper is told why.

*What the battery caught* (D645). **M4 SURVIVED**, and that is the run's most
useful result. `test_the_id_does_not_survive_the_request` called the app through
`asyncio.run` and then asked `current_request_id()` from the test's own frame —
but `asyncio.run` builds a fresh `Context`, so the assertion read a variable
nothing had ever set. It was green whether or not the reset ran. D374's shape,
and it would have guarded nothing forever. Now observed inside the same coroutine
that set it. Final: **6 arms, 6 killed, 0 survived, 0 defective.**

*And D498 is closed* (D646). Session 9 proved propagation and never proved
uniqueness; battery M2 is that exact mutation — `mint()` returning a constant —
and it now dies twice.

### Run 6 — `OPS-LOG-001` part 2: migration 0022

Both write RPCs read the forwarded header and set `request_id` on the `database`
row. The deployment test that asserts it `IS NULL` is **replaced by a stricter
one**, authorised by this run's ADR, with the reason in the new test's docstring
(§6 non-negotiables). `bin/migrate.sh freeze-lock`. Migration 0020's comment is
the contract for this run and should be read before it starts.

**Amended by D633, and this is the run's hardest constraint.** The value is
**guarded before it reaches the cast**: measured, an unguarded `candidate::uuid`
on a malformed caller-supplied header raises `22P02`, answers 400, and **rolls the
write back to zero rows**. A header that is not a uuid records `NULL` and the
write proceeds. The ADR must therefore say what a *malformed* header records, not
only where a good one comes from — and it inherits two existing decisions rather
than making a new one: ADR 0141 (a write fails closed on **its own** audit record,
which a caller's bad header is not) and ADR 0139 (a refusal is translated from the
product's `PT` errcode, never a relayed `22P02`).

The read itself is settled by D632: `current_setting('request.headers', true)`,
two-argument form, lowercase `'x-request-id'`, and **no `nullif(…, '')`** — an
absent jsonb key is SQL `NULL`, not the empty string.

**Proposed ADR 0161** — *the `database`-source audit row records the request that
caused it.* (Renumbered: Run 4 took 0159 and Run 5 took 0160.)

**And the id it records is the runtime's, never the header's** (D642, ADR 0160).
The forwarded `X-Request-Id` is how the value *reaches* the database — that part
of D500 is unchanged — but what the runtime forwards is its own mint, so the
`database` row, the `agent_plane` row and Traefik's `downstream_X-Request-Id` are
one value. A caller that sends its own header still reaches
`current_setting('request.headers')` and is still used for nothing.

**Done.** `migrations/templates/0022-database-row-request-id.sql`,
`app_private.agent_request_id()`, both write RPCs replaced, the manifest entry,
the frozen lock (**22 migrations**), the flipped deployment proof,
`tests/contract/test_database_row_request_id.py` (16 tests), **ADR 0161**, and
three divergence rows (**D647**–**D649**).

**D500 is closed.** The two rows for one MCP write now join on `request_id`, and
that value is the one Traefik logged as `downstream_X-Request-Id` on the way out.
Four legs, one value.

*What the run actually decided.* Not the read — D632 settled that (lowercase key,
two-argument `current_setting`, and **no** `nullif(…, '')`, which is the idiom
this repository uses everywhere and which guards nothing here). Not the guard
either — D633 settled that, having measured an unguarded cast rolling a caller's
own write back to **zero rows**. What was left was **where the rule lives**
(D647): one helper both RPCs call, rather than the expression written twice.
D500 exists precisely because 0019 asked a question of one path and not the
other, and two copies would set that trap again for a third write RPC.

*The test that had to flip.* Migration 0020 named it in advance — *"the thing
that will fail on the day the repair lands"* — and §6 requires the replacement be
stricter. The old assertion (`request_id IS NULL`) could fail exactly one way,
and only after somebody had made the repair. The new one asserts the join and
fails three ways: a missing id, a mismatched id, or an id no `agent-plane` row
shares.

*What the battery needed before it could measure anything* (D648). The contract
tests read the **rendered** migration, so an arm that mutates the template
without re-rendering measures the previous bytes — every arm a survivor for a
mutation that never happened. The render runs inside the loop, and an arm whose
mutated template fails to render is reported **defective** rather than killed.
Final: **7 arms, 7 killed, 0 survived, 0 defective.**

*What it opened* (D649). ADR 0160 said a caller's header *"is used for nothing"*.
Migration 0022 uses it — a caller reaching PostgREST directly supplies the header
that becomes its own `database` row's id. Recorded rather than reconciled: the
caller cannot forge `agent_id` or `owner_id`, so this is ADR 0135's conceded
case, and the noise is visible because the row still names its author. **The
operator guide must say to check `agent_id` beside `request_id`.**

### Run 7 — The README and the documentation index

README rewritten to Session 11's truth. `docs/README.md` index. Both **derived by
diff** from what the tree does (D505, D507, D602). Every command the README names
is executed before the run closes — that is `DEP-001`'s offline node id, and it is
what stops D623 from happening a second time.

**Done.** `README.md` rewritten, `docs/README.md` created,
`tests/contract/test_documentation_index.py` (14 tests), the stale request-id
paragraph in `docs/mcp-tool-catalog.md` corrected with D649's caveat,
`bin/render-config.py`'s closing message repaired, one catalog test replaced by a
stricter one, and four divergence rows (**D650**–**D653**).

*What the README said.* **"Status: Session 3 of 12 complete"**, for eight
sessions — naming `bin/connect.sh` as unavailable while it was 697 lines of
working code, object storage as a future session, and a restore rehearsal as
future after it had been run against a real deployment. Nothing failed, because
nothing checked. `test_the_readme_states_the_session_the_release_implements` is
the assertion that would have caught it in Session 4.

*What "derived by diff" did not save me from* (D650). The plan's instruction —
derive, never retype — is a defence against **losing** what the previous page
said. It is no defence at all against what the *current* page claims. The derived
README still had four lines a reader could not run, and every one was found by
**executing** the command: `migrate.sh --project` wants a manifest file, not a
key; `connect.sh tunnel` also needs `--ssh USER@HOST`; `restore-test.sh` takes
`--project-dir` and the prose said `--outputs`. The class is now guarded for
inventions; **omissions are still only catchable by running the path**, which is
Run 8.

*Two claims that were false the moment a fourth file appeared* (D651, D652). The
README said every generated file is `0600`; `pgbackrest.conf` is `0444`, by a
reasoned decision (it carries no credential by construction and uid 999 reads
it). Worse, **`render-config.py`'s closing line said the same thing** — the one
sentence printed after every render named `pgbackrest.conf` and claimed `0600`
for it, and had done since Session 10 added the filename and left the mode. The
modes are now read from the constants. Found with `find -printf '%m'`, not by
reading.

*The catalog test that fired* (D653). `OPS-LOG-001` was in the catalog's
*deliberately absent* list, and Runs 5 and 6 closed it — the third sentence to
leave that list, each one noticed by this same test going red. Replaced by the
positive claim, including the caveat D649 obliged: **correlating by `request_id`
means reading `agent_id` beside it.**

*What is deliberately not claimed.* `DEP-001` stays `future`-marked. A README that
passes fourteen offline assertions is not a README a stranger has followed on a
clean machine, and the difference between those two is the entire point of Run 8.

### Run 8 — The disposable-VM rehearsal

Provision a clean VM following **only** the README. Every assumption the README
does not state becomes a divergence row, and every fix lands in the README rather
than in a private note. Staging ACME; stop before promotion.

This run decides whether Run 7's README is true, and it is the run most likely to
generate rows.

**Done — with leg 3 deliberately not run, and `DEP-001` not claimed** (D669).

Half A, and half B's legs 1 and 2. **Eleven divergence rows, D655–D669**, of
which nine are defects in this repository's documentation or code and two are
corrections to my own earlier findings.

**What Session 11 does not get from this run:** `DEP-001`'s live half. Its
placeholder stays `future`-marked and it carries to Session 12, where `DX-001`
is a superset of it. Leg 3 was declined because it needs a scratch Infisical
project, two R2 buckets with tokens and a DNS record, in order to exercise the
commands the live host already runs on every deploy — the opposite of the
findings-per-cost that legs 1 and 2 had — and because §9's stop condition 5 says
a rehearsal touching live provider state is not a rehearsal.

**What it does deliver** is a documented path materially better than the one
Session 12 would otherwise have tested: a fresh host no longer locks its
operator out at step 2, the transport step exists, the security baseline no
longer claims a control it does not have, and `edge.sh status` no longer reports
a healthy edge as down.

**One free measurement on the way out** (D668): Run 2's preflight ran on the real
host and was right first time — both absences together, copy-pasteable remedies,
nothing written, exit 4. A host-only proof that had never executed, executed at
no cost, because refusing before touching anything is exactly what it does.

---

**Half B, leg 2 done** — the edge plane, on the same fresh host. `edge.sh up`
exits 0; `traefik:v3.7` and `docker-socket-proxy:0.3.0` are both **healthy**;
`apg-edge-control` and `apg-edge-egress` created; ACME environment **staging**;
no certificate requested, which is correct. From outside, `:80` answers 301 and
`:443` answers 404 — Traefik's own, with nothing routed. Two rows, **D666** and
**D667**.

**It needed no DNS record** (D667), and establishing that was worth the five
minutes: the edge's dynamic configuration has no `certresolver` and no `Host()`
rule, so nothing requests a certificate until a *project* router exists. The
guide's *"the edge starts on staging ACME certificates"* means configured for
staging, not holding one. The DNS requirement belongs to leg 3.

**D666 is a defect in this repository's own code, and the sharpest kind.**
`bin/edge.sh status`, run without root exactly as the operator guide documents
it, reported `containers (not running)` while both were Up and healthy —
because `compose ps 2>/dev/null || printf '(not running)'` turns *every* failure
into that sentence, and an unprivileged caller cannot reach the Docker socket.
It is D145's and D548's shape, it is precisely what ADR 0157's `undetermined`
and ADR 0158's `unknown` exist to refuse, and **it predates both by nine
sessions**. Repaired, asserted, and verified on the machine that exposed it.

---

**Half B, leg 1 done** — on a genuinely fresh Hetzner **Ubuntu 26.04** host
(204.168.206.188), measured before anything touched it: 5 minutes' uptime, no
shell history, no non-system users, **zero apt history entries**. The canonical
release rather than the 24.04 fallback, and the same 3814 MB / 38 GB shape as the
live host.

`provision-host.sh --check` now exits **0** — *"the host meets the Session 2
baseline"*, 27 ok checks, no deviations — across the documented three passes
(18 deviations → 4 → 1 → 0). Seven divergence rows, **D659–D665**.

**D659 is the finding of the session.** The documented path locks an operator out
of a fresh host, and empirically: root is refused on that machine now, and the
only reason I still have access is an account **no document tells anyone to
create**.

*What worked exactly as written*, which is worth saying because most of it did:
the three-pass split, both rollback timers arming and disarming, the refusal to
harden while no timer is armed (**measured twice** — once by my own mistake), the
`sshd -T` policy verification, and `ufw show added` rather than `ufw status`. The
machinery is sound. The gaps are all in what the pages *say*.

---

**Half A done.** The README's local path — clone, tools, interpreter,
environment, `doctor.sh`, render, inspect, checks — followed literally in a clean
`ubuntu:24.04` container by somebody who had read nothing else. Four divergence
rows (**D654**–**D657**), all repaired, plus **D658** for the half a container
cannot answer.

*The construction, stated so it can be judged.* Base `ubuntu:24.04` plus only
what a stock Ubuntu Server carries and a bare container does not — `sudo`,
`ca-certificates`, `curl`. **`git` deliberately not pre-installed.** The
repository arrives by cloning the local checkout rather than a URL: a stated
deviation, not a finding, since it exercises `git clone` without putting a
credential in the container.

*What it found, in order of how badly it reads.*

**D654 is mine, and it is the worst of the four.** `bin/doctor.sh` with no
arguments exited **1 after four lines** — and had done since Run 4, when I added
`--verbose`. `[ -n "${VERBOSE}" ] && printf` was the last statement of
`check_command`, so under `set -e` the function returned 1 whenever `VERBOSE` was
empty. `--verbose` worked, and `--verbose` is the mode Run 4 exercised. The
README's *"confirm the workstation is ready"* step was broken for a whole run, on
my own machine, and **nothing in a 4,152-test suite was watching that command's
default path**. Question 1, unanswered. Now parametrised over both modes.

**D655**: the README's first instruction is `git clone` and its tool list does not
include `git`. A stock server image has none. *A prerequisite you have never
lacked is one you cannot see.*

**D656**: *"`--render-only` needs no host and no root"* — three true clauses
reading as a complete list. It needs **Docker**, and without it exits 5 having
published nothing.

**D657**: `# fast: active contract tests only`. Measured: **4,152 tests, 291
seconds**, starting real containers. The number was never measured before it was
written down.

*Second pass.* The corrected README was followed again end to end: the render
succeeds, prints the repaired mode line, and the modes on disk are what it says.
`doctor.sh` still failed in that pass **because the container clones the
committed tree and the fix was uncommitted** — a rig artifact, verified as such
rather than assumed.

*What is deliberately not claimed.* The second pass's `smoke-test.sh` failures are
**not attributed to anything**. That rig shares the host's Docker socket, which is
a difference I did not isolate, and the same suite is green on this machine
(4,152 passed). Reporting an unisolated failure as a finding would be the
opposite of what this run is for.

### Run 9 — `DEP-001` / `DEP-002`: the host trip

The live proofs on `62.238.99.122`. `DEP-002` writes a sentinel row through the
product's own route, redeploys `--through-session 11`, reads it back, and asserts
in the same test that the redeploy ran. The deployed `doctor.sh` and the
end-to-end request-id correlation are measured here too.

**Question 2 applies to everything in this run**: every proof written in Runs 2–6
that only runs on a host will be executing for the first time. That is the shape
that produced **five defective never-executed proofs across two trips**. Read each
one's assertions before the trip, not at the terminal.

### Run 10 — The rotation window

Three rotations; each proof given the value the window replaced; the file written
**before**. All four verifiers recreated after the signing-key phase. Commands are
in `docs/api-operations.md`, and D253's warning is read first.

Turns `api_authorization` and `bootstrap_identity` green.

### Run 11 — The gate, the evidence, and the close

`bin/session-11-check.sh` in three modes (`offline`, `host`, `external`), both
halves merged, `evidence/session-11.json` written, `CURRENT_SESSION` moved to 11,
`docs/session-11-operator-guide.md` derived by diff, §11's handoff written.

---

## 6. The surface Session 11 builds, described once

**The preflight.** One report, every absence, each with the command that supplies
it. It writes nothing, starts nothing and opens no database connection. Exit `4`
— missing bootstrap/runtime prerequisite — which the convention already defines.

**`bin/doctor.sh`.** Two modes. The default is Session 1's and does not change: a
checkout's tools, interpreter and shape, exit `3`. The deployed mode takes a
project and reports the check families of D615, exit `6` when a check fails and
`4` when there is no deployment to check. `--verbose` adds detail and no secret.
Both modes print no environment.

**The request-id contract.** The caller may offer `X-Request-Id`; the edge records
what it was offered; the runtime honours a valid uuid and mints one otherwise;
every upstream call in that request carries it; both audit rows record it. Nobody
downstream of the runtime mints.

**The README.** Status, prerequisites, the ordered deploy sequence, the
operator-guide table, what is genuinely unavailable, and the exit-code convention.
Every command in it exists and resolves, checked offline on every gate.

---

## 7. Evidence and claims

| Claim | offline | host | external |
|---|---|---|---|
| `deployment_preflight` | shape and refusal | the refusal against a real host | — |
| `deployment_convergence` | every README command resolves | **`DEP-002` only** — the redeploy, on the live host | — |
| `operational_diagnosis` | check inventory and redaction | every check against a live deployment | — |
| `log_correlation` | the runtime's honour-or-mint logic | one id across four records | — |
| `api_authorization`, `bootstrap_identity` | — | the rotation window | — |

**`DEP-001` is not in this table** (D669). Its offline half is proved and its
live half — a fresh project deploying on an empty host — was not run: Run 8
stopped after the host baseline and the edge plane. The placeholder stays
`future`-marked, and Session 12 inherits it alongside `DX-001`. Registering the
claim on the offline half alone would be a claim whose id promises a deployment
nobody performed, which is what ADR 0045 and D70 exist to prevent.

A claim's verdict is computed from the registry's node ids and JUnit results,
never hand-entered. **A skip is not a pass.** A filtered (`-k`) run writes
nothing. The host and external halves must describe the **same release** or the
merge refuses.

---

## 8. Security invariant matrix

| Invariant | Control | Proof |
|---|---|---|
| The diagnostic command prints no secret in any mode | It reads state fields and calls existing commands' `--json` surfaces; it never reads a generation directory | D622's sentinel scan across every mode, with a leaky control build |
| A request id is a uuid and never caller-supplied prose | The column is `uuid` (migration 0019); the runtime validates before trusting | An inbound header carrying a sentence is rejected and a fresh id is minted; the row holds the minted one |
| The preflight gains no write path to state it reads | It calls no command that mutates and opens no transaction | The filesystem is byte-identical across a refused run |
| A deployed-document reader reads only keys the schema has | `naming` derives; `$defs.deployedDocument` bounds | `test_no_operator_command_reads_a_key_the_deployed_document_does_not_have` (D600's class test) covers `doctor.sh` from its first commit |
| The audit record still cannot be forged | Migration 0022 changes what a row *records*, not who may write one; identity still comes from the GUCs the pre-request hook set | `SEC-PARAM-001`'s existing proofs, unchanged and re-run |
| A rotation leaves no process serving the old credential | Every verifier is recreated after the published set changes | The rotation window's own refusal proofs, given the replaced value |

---

## 9. Risks and stop conditions

**Stop and ask** in these cases:

1. **The VM diverges from the VPS in a way that makes the rehearsal a lie.** A
   rehearsal on a machine that differs in kernel, storage driver or network in a
   way the deploy depends on proves something about the VM. D605 is the standing
   example — `SO_RCVBUF` reproduced a defect on one kernel and not another. If the
   rehearsal hits a divergence it cannot attribute, stop.
2. **Migration 0022's header read is not available inside a definer function.**
   Run 1 measures it. If it is not, `OPS-LOG-001`'s database leg has no repair in
   this session and the plan says so rather than inventing one.
3. **D616 has no answer that does not flip a passing contract test.** Flipping one
   needs an ADR and is allowed; discovering it mid-run is not. If all three shapes
   cost something the session should not pay, stop.
4. **The rotation window's second or third rotation fails after the first
   succeeded.** A half-rotated deployment is the one state nobody has rehearsed.
   Stop with the terminal open.
5. **The R2 or Infisical account cannot safely serve a scratch project.** The
   control-plane identity holds org admin; a rehearsal that touches live provider
   state is not a rehearsal.

**Risks that are accepted and written down:**

- `doctor.sh` grows large, and a large diagnostic is a place for a check that
  looks measured and is not. Every check answers §7's five questions in its own
  docstring, and the ones that only run on a host are read before the trip.
- The offline half of `DEP-001` is a text-adjacent check, and D464 is the standing
  example of a text scan producing a false positive. It asserts that commands
  *resolve and exit as documented*, not that strings appear.
- `tests/deployment/conftest.py` is past 2,100 lines and this session adds to it.
- A contract test that invokes commands bare can run the suite recursively. Measure
  each new test's cost, not only its assertion.

---

## 10. Open items carried in

CLAUDE.md §9 in full, unchanged except for what this session closes. The ones that
bear directly on this session's work:

- **Nothing knows which proofs have never executed.** Seven sessions, five
  defective never-executed proofs across two trips. Runs 2–6 all produce host-only
  proofs; Run 9 is where they first execute. This is the item most likely to cost
  this session a round.
- **`process-max` is 1** — a restore is ~1330 serialised S3 round trips and RTO is
  a band, not a number (D593, D603). If `doctor.sh` reports anything about restore
  time, it reports the band.
- **`apg-diag` cannot read `auth`, `storage` or `mcp` logs** (D380). It sent an
  operator to a terminal in Sessions 7, 8 and 9. Run 5 adds structured logs to two
  of those three services, which makes the gap sharper, not smaller.
- **`archive_timeout` is a constant nothing publishes.** If `doctor.sh`'s WAL
  freshness threshold derives from it, this becomes an outputs-v14 question — and
  ADR 0146 refused a version bump inside the session that shipped v13. It does not
  refuse one in the session after.
- **`requirements-dev.in` pins nothing** and has reddened the gate seven times.
  `bin/lock-dev-deps.sh --update`, committed **separately**.
- **The IPv6 scan** — eight `APG_PUBLIC_IPV6` proofs, never run.
- **`revoked → active` answers 200** (D503) — stated as terminal, unenforced, and
  nobody has decided whether it should be.

---

## 11. Session 12 handoff

Session 12 is the final session: `DEP-ISO-001`, `DEP-REMOVE-001` and `DX-001`,
whose placeholders are in `tests/contract/test_future_deployment.py`.

It receives from Session 11 a README that has been executed on an empty machine, a
`doctor.sh` that answers whether a deployment is well, a deploy that refuses
completely rather than partially, and one request id that spans four records.

**It also inherits `DEP-001`'s live half** (D669). Session 11 proved the offline
half — every command the README names exists, resolves and answers — and ran the
host path as far as the baseline and the edge plane, on a genuinely fresh Ubuntu
26.04 machine. It did not deploy a project there. Leg 3 needed a scratch
Infisical project, two R2 buckets and a DNS record in order to exercise commands
the live host already runs on every deploy, and §9's stop condition 5 refuses a
rehearsal that touches live provider state.

`DX-001` is a superset of what is left, so the two are best done together — and
they are now being attempted against documentation that a fresh host has already
corrected eleven times. The most consequential: **`provision-host.sh` names an
operator user it does not create**, and its second pass installs
`PermitRootLogin no`. Before Session 11, `DX-001` would have locked its developer
out of their own machine at step 2 and called it a documentation problem.

It receives three narrowings. **`DEP-001` was proved on a disposable VM, not on
the production host**, and `DX-001` — a developer who did not build this — is the
test that decides whether the rehearsal generalised. **The ingress leg of the
request id exists only when a caller offers one**, which is a property of the
design and not a gap to be filled by a plugin without an ADR. **`doctor.sh`'s
disk threshold was derived from one measurement on one machine**, which makes it a
measurement rather than a bound.

And it inherits the two things Session 11 could not close: whichever of §9's stop
conditions fired, and the item that has now cost seven sessions — **nothing knows
which proofs have never executed.** Session 12 is the last chance to build it, and
it is still the most expensive item on the list.

---

## Appendix — what to consult, and what to measure instead

**Consult:** `docs/decisions/README.md` (156 ADRs, indexed; next free **0157**) —
for this session especially **0002** (single-authority derivation), **0013**
(the Compose wrapper's scopes), **0017** (the stub lifecycle, now complete),
**0043** (the authorization decision lives on the host), **0060** (why the REST
document advertises verbs that 403), **0063/0133** (why a service is deferred, and
the two reasons), **0069/0087** (why the documentation server is first-party, and
why two surfaces share one process), **0088** (four verifiers, recreate all of
them), **0096** (re-derive from the event, do not restate), **0134** (a grant
assertion reads the catalog; a reach assertion sets the role), **0135/0141** (who
writes an audit row, and when a write fails closed on it), **0146** (why the
observation is a block of its own), **0149/0150** (what a repository can honestly
report, and how a broken archiver stays visible), **0154** (the render decides a
mode, the install decides an owner), **0155** (a deploy recreates a container whose
mounted content changed). Behind them: 0045/0089 (what a claim is) and 0065/0066
(*a proof that reaches the right end state by a route the product does not take
proves the end state is reachable, not that the product reaches it*).

`docs/session-10-operator-guide.md` as the parent of this session's — **by diff**.
`docs/plans/session-10-implementation-plan.md` §5 Run 11 for what a trip costs.
§1 of this document for everything else.

**Measure instead of consulting**, every time: what a preflight can observe
without writing, what a header extraction returns inside a definer function, what
a container reports for a bind-mounted volume's free space, what `pg_stat_archiver`
says on a cluster whose archiver is broken, what a clean VM lacks that this
repository assumes, and **whether a proof has ever run.**

**Before measuring how a third party behaves, grep the plans for it.** Nothing
indexes the ~605 measured facts in the divergence tables by subject, so the
pointer has to be a `grep`.

**Never write a measurement you did not run** (D267).

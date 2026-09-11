# 0200 — The scope vocabulary's data class is derived from the reviewed surface, and the roster is compiled, not enumerated

- **Status:** accepted
- **Date:** 2026-09-11
- **Session:** 21, Run 1 (D1124–D1126, D1129, D1130, D1135, D1140)
- **Amends:** **ADR 0006** (the vocabulary lives in the schema — the schema
  keeps the two classes it enumerates and the *shape* of the third; the third's
  members are computed), **ADR 0079 / ADR 0100** (the ceiling and the three
  classes — the ceiling becomes a function of the vocabulary, and the partition
  is asserted per surface), **ADR 0127** (the lock is the answer — and now the
  whole of it, roster included), **ADR 0183**'s roster sentence under *what a
  profile cannot do*.
- **Related:** ADR 0003 (the example domain, unchanged — it is no longer what
  closes the vocabulary), ADR 0050 (nothing exists in `api` the reviewed
  contract does not name), ADR 0120 (a tool is one or more capabilities), ADR
  0140 (a hidden tool is still callable), ADR 0141 (`begin` before the scope
  check), ADR 0177 (a field arrives at its version), ADR 0196 (the task
  domain restored because retirement was blocked by the six-tool roster), ADR
  0198 (a project owns a migration set and a surface), D486, D933, D1056,
  D1083.

## Context

The agent plane is closed to a tenant's domain twice over, and both closures
work as designed (D1056, D1083). `mcp_lock` refuses a lock whose tools are not
exactly six names written into the module; `required_scopes` binds to a
five-member enum that cannot name an application's relation. Session 20 gave a
project its own tables (ADR 0198); this is where a project's tools reach them.

### What the tree does, measured at `5a43f12`

**The roster is written in four places, by decision.** `mcp_lock.py:70`
derives `EXPECTED_TOOL_NAMES` from three name tuples; `mcp_tools.py:127` writes
`TOOL_NAMES` out again — *"two lists that must agree, not one list read
twice"* (D486) — and registers six tools with six typed Python signatures;
`capability_compiler.PLANNED_TOOLS` is the reviewed answer the compiled set is
compared against. Two tests read the *source text* of the runtime modules:
`test_mcp_catalog` asserts `tool_count == 6` and the string *"exactly six"* in
the catalog prose; `test_api_migrations::test_retiring_the_task_tools_is_blocked_by_the_roster`
asserts `mcp_lock.py` contains `names != EXPECTED_TOOL_NAMES`, with a failure
message that names this decision in advance: *"if that is deliberate, D933 may
be closed and ADR 0196 revisited."* (D1124.)

**The vocabulary has five readers beyond the schema, and one is in a container
that has never seen the lock.** `scope_registry` reads the two enums;
`services/auth-api/app/scopes.py` hardcodes `notes:*` and `tasks:*` into four
role ceilings; `service.py:207` and `:411` refuse an agent record or a request
whose scopes exceed the ceiling; `bin/dev-token.py` reads the ceiling; two test
modules assert the five names. (D1125.) The lock is mounted into the `mcp`
container only (`runtime_override.py:834`), and the auth service — the issuer —
has no lock and no schema (ADR 0084). (D1126.)

**Rig 21c measured which gates on the issue path know the vocabulary.** In the
auth-endpoints fixtures' in-process service on the pinned cluster:

| Arm | Result |
|---|---|
| create an `agent_writer` with `note_embeddings:write` | **422**, *"a agent_writer may not hold ['note_embeddings:write']; the ceiling is [...]"* |
| control: create an `agent_reader` with `notes:read, tasks:read` | 201 |
| the control's RECORD forced to `{meta:read, note_embeddings:write}` by superuser `UPDATE` (`is_scope_set` accepts a sorted array), then the token exchange | **422**, *"the stored record grants ['note_embeddings:write'], which a agent_reader token may not carry"* |
| the pre-request hook with hand-made claims carrying that scope, matching the record | **rc 0**, `app.user_id` established |
| control: the hook with claims NOT matching the record | rc 1, `AP401: the request identity is no longer current` |

So the verifier (`claims.py`: a sorted, deduplicated array of strings), the
hook (array equality against the record) and the SQL (`is_scope_set`: sorted,
deduplicated, no NULL) are **vocabulary-agnostic**. The ceiling is the only
vocabulary gate on the issue path, and it is a static map in a container the
lock never reaches.

**Rig 21b reproduced D933 as the control for the change.** `create_note`
disabled compiles five tools and `load_lock` refuses: *"the lock serves
[five], not [six]"*; `update_task_status` disabled, the same; `query_tasks`
disabled compiles six (two capabilities behind `query_resource`) and loads —
ADR 0196's asymmetry, measured.

**Rig 21a measured whether the pinned FastMCP 3.4.0 can register a tool whose
parameters are data**, through the in-memory client (ADR 0140 M4: `list_tools`
runs the pipeline):

| Arm | Result |
|---|---|
| a closure with an `inspect.Signature` built from a name list, and nothing else | **`KeyError: 'p_note_id'`** at registration: pydantic reads `get_type_hints()`, i.e. `__annotations__`, and a `Signature` is not consulted for types |
| the same closure with `__annotations__` set as well | `tools/list` carries exactly the derived names, `additionalProperties: false`; an undeclared argument is **refused** by pydantic (*unexpected keyword argument*); a missing one is refused (*missing required keyword only argument*); `timeout=0.1` fires around a 2 s sleep |
| control: the decorator over a static typed function | identical behaviour |
| `FunctionTool(name=, parameters=<explicit JSON schema>, fn=)` via `add_tool` | the schema is **advertised** — `tools/list` shows it, `additionalProperties: false` — and **not enforced**: an undeclared argument reaches the handler, a missing one reaches the handler |

The fourth arm is the trap: a tool constructed with an explicit schema looks
bounded to every client and bounds nothing. (D1140.)

### Why the closure was right, and why it stops being

ADR 0006 refused a pattern-validated vocabulary because *"a pattern says a
scope is well-formed; it cannot say a scope was approved"*, and refused
deriving from the served OpenAPI because *"a vocabulary that changes when an
unrelated service is redeployed is not a contract."* Both objections stand.
Neither applies to deriving from the **reviewed surface file** —
`contracts/postgrest-api-surface.yaml` and a project's own under ADR 0198 —
which is hand-written, digested into every lock as
`compiled_from.api_surface_sha256`, compared against the served document by
`api-contract.sh --check`, and changes on a reviewed edit and on nothing else
(D1135). A relation the reviewed surface publishes IS an approved resource,
and ADR 0050 already makes that file the authority for what exists in `api`.

ADR 0127 wanted the surface *enumerated, not discovered*, and six was the
shape of the only contract there was. What the number protected was that a
lock could not serve a tool nobody reviewed. That property does not need a
constant; it needs the lock to be the compiler's, and only the compiler's.

## Decision

### 1. The data class is a function of a reviewed surface

```
vocabulary(surface) = { f"{r}:read", f"{r}:write" for r in surface.relations }
                    ∪ { "meta:read" }
```

computed by one function in `scope_registry`, over the *merged* surface when
a project declares one (ADR 0198's `merged_surface`). The storage and
administrative classes stay **enumerated** in `$defs/storage_scope` and
`$defs/administrative_scope`, exactly as ADR 0100 left them.
`assert_classes_partition_the_vocabulary(surface)` asserts the partition per
surface.

**The derived class can never name an administrative or storage scope**, and
that is a property rather than a hope: `api_surface` refuses, at load and at
merge, a relation whose name is the resource half of any enumerated scope
(`objects`, `admin_users`, `admin_agents`, `admin_audit`), so no reviewed
surface can produce a colliding name, and the partition check would refuse the
collision if one ever reached it.

`$defs/agent_scope` — the five-member enum — becomes the vocabulary a manifest
at capability schema **≤ 3** may name (ADR 0177's shape: the ≤3 gate keeps the
`$ref` to the enum, which is a subset of every derived vocabulary because the
release's relations always exist). At schema **4** `required_scopes` items bind
to a *shape* (`^([a-z][a-z0-9_]{0,62}:(read|write)|meta:read)$`) and the
compiler approves each name against the derived vocabulary. The schema is
still the sole authority for what it enumerates, and the reviewed surface is
the authority for the third class's members.

**No data-scope literal survives in `src/` or `services/`** outside the schema
and the example manifest. That is the guard that replaces
`test_scope_vocabulary_lives_only_in_the_schema`, and it is stricter: it
forbids the copy ADR 0006 was written to prevent.

### 2. The ceiling is a function of the vocabulary, and the issuer reads it from the lock

`services/auth-api/app/scopes.py` keeps the one declaration of *which classes a
role's token may carry* (`ROLE_CLASSES`: `authenticated` data + storage;
`agent_reader` the `:read` half of data + `meta:read`; `agent_writer` data +
`meta:read`; `project_admin` data + storage + administrative;
`api_documentation` `meta:read`; `anon` none) and names no data scope.
`ceiling(role_suffix, vocabulary)` computes the set.

**Lock schema 4 carries a `vocabulary` block** — the derived data class, and the
two enumerated classes verbatim from the schema at compile time — **and the
auth container mounts the same lock read-only**, under the same variable, at
the same path. The issuer computes its ceilings at startup from it. ADR 0155
does the rest: a lock whose bytes changed recreates both containers on the next
deploy. The environment changes by one mount; it holds no credential.

### 3. What a contract change does to an issued token's scopes

A scope stops existing only when a reviewed surface drops a relation, which is
a project migration, a contract edit and a redeploy. An agent record that
still holds the name is then **refused at its next token issue** — the ceiling
no longer admits it (rig 21c's second arm is exactly that refusal) — and **inert
at call time** — no lock capability requires it, and the runtime's call-time
check holds the caller's scopes against the lock's `required_scopes`. A deploy
moves no agent's `authz_version`: the deploy writes no agent record, and the
issue path is the boundary. Nothing is silently widened, nothing is silently
kept.

### 4. The roster is compiled, not enumerated

`EXPECTED_TOOL_NAMES`, `mcp_tools.TOOL_NAMES` and `PLANNED_TOOLS` go. The
runtime registers **from the lock, by kind and shape, never by name**:

| Kind | Shape | Parameters |
|---|---|---|
| metadata | the pair the runtime answers itself: `list_resources`, `describe_resource` | as today; **both required in every lock** |
| read, `reads: relation` | resource-selecting (`query_resource`'s) | `resource, columns, filters, order_by, limit` |
| read, `reads: rpc` | an argument-free RPC (`run_report`'s) | none |
| write | one reviewed RPC | the lock's argument list, plus `idempotency_key` and `dry_run` |

A read over an RPC **with** arguments has no shape and the compiler refuses
it, naming the two read shapes and the remedy (publish the query as a view):
an RPC argument is a caller value in a request body, which is a write's shape
(D486, D470). Three shapes derived from the lock is a runtime that registers
from data; a fourth invented for a case no reviewed surface yet has is D267's
shape one level up. (D1129.)

Registration builds each closure's `inspect.Signature` **and**
`__annotations__` from the lock — rig 21a's first arm is why both — and never
an explicit `parameters` schema, which advertises a bound it does not enforce
(rig 21a's fourth arm).

**The loader's refusal becomes structural** (D1130). The runtime cannot
recompile (ADR 0084), so it cannot compare a lock to the contract; what it can
check is what a compiler writes: kinds in the three; exactly the metadata pair;
every read carrying at least one resource and a `reads` word the resources
agree with; every write carrying an argument list and a `post` operation;
`tool_count` equal to the list; and at lock schema 4 a **`tools_sha256`** — the
compiler's digest over the canonical bytes of the tool list as compiled, after
the profile — recomputed at load and refused on mismatch. A tool added, removed
or edited by hand is a digest the compiler did not write. *Enumerated, not
discovered* is kept as *compiled, not edited*.

**D933 closes for both things it blocked.** A five-tool lock loads; a project
that must not expose a release write leaves it out (ADR 0201 says where); the
task tools could now be retired — and are not, because ADR 0196's restoration
stands on its own reason.

Nothing about `bounded`, the audit order (ADR 0141: `begin` before the scope
check), the call-time scope check, `build_write_request`, redaction or the
budgets moves: they already read the lock per tool.

## Alternatives

**Keep the enum and widen it per tenant, in the schema.** ADR 0006's own
reason against: the schema would carry a copy of every project's relations,
and a copy is the thing that goes stale. Rejected.

**Derive from the served OpenAPI document.** ADR 0006 rejected it and this ADR
agrees (D1135): a served document moves when a service is redeployed; the
reviewed surface moves when a person edits it.

**Keep `EXPECTED_TOOL_NAMES` and let a project's tools be a second roster.**
Two rosters, one runtime, and every guard written against the first. Rejected
as D486's arrangement inverted — a second list that must agree with a
constant, forever.

**Compare the lock to the contract at startup.** The runtime cannot compile
(ADR 0084, standard library only), and shipping the compiler into the image
would ship `src/` into a container that holds a caller's token. Rejected; the
digest is the compiler's signature on the list.

**Register with an explicit `parameters` schema per tool.** Measured in rig
21a: advertised, not enforced. Rejected on the measurement.

**Allow a read over an RPC with arguments.** A new input class with no
reviewed example; refused rather than designed blind (D1129).

## Consequences

- `scope_registry.vocabulary(surface)`, `agent_requestable_scopes(surface)`,
  `approved_scopes(surface)`, `assert_classes_partition_the_vocabulary(surface)`,
  `ROLE_CLASSES`, `permitted_scopes(role, surface)`; `api_surface` refuses a
  reserved relation name at load and at merge.
- Capability schema 4; compiled-contract and lock schema 4 (`vocabulary`,
  `tools_sha256`, `reads`); `mcp_lock.SUPPORTED_SCHEMA_VERSIONS` and
  `capability_compiler.COMPILED_SCHEMA_VERSIONS` gain 4.
- The auth service mounts the lock; `settings.py` requires `APG_MCP_LOCK_FILE`
  in the auth settings too.
- **Tests replaced by stricter ones under this ADR**, which is the one route
  the non-negotiables admit: `test_the_data_class_is_still_exactly_the_five_adr_0003_closes`
  (→ the release surface derives exactly those five, so nothing widened, AND
  the merged example surface derives seven); `test_scope_vocabulary_lives_only_in_the_schema`
  (→ no data-scope literal outside the schema and the example manifest);
  `test_a_lock_missing_one_of_the_six_is_refused` (→ a five-tool lock loads,
  a lock missing a metadata tool is refused); `test_a_lock_with_a_seventh_tool_is_refused`
  (→ a tool the compiler did not digest is refused, and the same seventh tool
  compiled from a manifest that declares it loads); `test_the_compiled_tools_are_the_six_that_were_planned`
  (→ the compiled set is the manifest's enabled capabilities grouped by
  `tool`, read independently); `test_mcp_catalog`'s `== 6` and *"exactly six"*
  (→ the count the contract carries, rendered); `test_retiring_the_task_tools_is_blocked_by_the_roster`
  (→ `…is_no_longer_blocked_by_the_roster`: the example manifest without
  `update_task_status` compiles to five and loads).
- `docs/mcp-tool-catalog.md` renders its count; `README.md`'s *"the agent
  plane serves this product's example domain, and not yours"* paragraph is
  rewritten to what closes the plane now (the reviewed surface and the
  compiler) and how a project opens it (ADR 0201).
- ADR 0196's asymmetry argument becomes historical; the restoration stands
  because two of six tools addressed a table nothing could populate, which was
  true regardless of the roster.

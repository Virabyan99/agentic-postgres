# 0204 — A generated client is a claim about the surface it was generated from, and its proof reads the served surface as the caller

- **Status:** accepted
- **Date:** 2026-09-12
- **Session:** 23, Run 1 (D1200–D1204, D1206–D1210, D1212–D1215)
- **Related:** ADR 0050 (a reviewed surface is a generated artefact with an
  update/check split — the client repeats its `--check` at the caller), ADR
  0065/0066 (a rig is a second configuration of the product and must be tied
  to it), ADR 0087 (both documentation surfaces strip the root), ADR 0093 (an
  operator command reaches service logic through a container), ADR 0119 (an
  operation id is derived), ADR 0120 (a tool may be backed by more than one
  capability), ADR 0125 (the plane forwards the caller's own token;
  `stateless_http`, no handshake), ADR 0127 (a caller value is a value; the
  request is built from the lock), ADR 0130 (a refusal reaches the caller only
  through `ToolError`), ADR 0139 (a write refusal is translated from the
  product's errcode), ADR 0158 (the deployed document is the address book, not
  the diagnosis), ADR 0162 (what a bump permits), ADR 0181 (an idempotency key
  is claimed in the write's own transaction), ADR 0182 (a dry-run attempts the
  write and rolls it back), ADR 0183 (a profile only narrows), ADR 0195 (three
  outcomes, the third reported), ADR 0198/0200/0201 (a project's set, surface,
  snapshot, vocabulary and capability manifest), ADR 0202 (an offline claim is
  declared), ADR 0203 (the dev environment is the database); D105 (nothing
  prints a token), D486 (a second copy of a value is a compared pair with a
  contract test between them), D600, D700 (a deploy-time snapshot goes stale
  in both directions), D930, D1114 (a proof calls the product's own command),
  D1152/D1153 (the plane can be behind the file the document was rendered
  from).

## Context

Nothing in this product generates code. A developer who wants to call
`api.notes` from TypeScript reads `docs/api-surface.md`, types the path, and
learns the row shape from `contracts/postgrest-openapi.canonical.json` by eye;
one who wants to call a tool reads `docs/mcp-tool-catalog.md` and hand-rolls a
JSON-RPC body. Neither can tell, before the first request fails, whether the
surface they wrote against is the one being served.

That is D700's shape at the client. `backup_state` in the deployed document is
a deploy-time snapshot, and the rule this project settled on for it was that a
recorded observation is evidence about the moment it was recorded and must say
so. A generated client is worse than a recorded observation, because it is
*held by someone who did not generate it* and it goes stale in both
directions: the surface can move under the client, and the client can be
regenerated from a contract the deployment has not caught up to.

So the question Run 1 had to answer was not *what do we embed* — it was **what
can a client check at runtime, as itself, with only what it legitimately
holds.** The stage plan proposed a candidate (the docs route's served OpenAPI
digest plus `list_resources`' lock digest) and said the first measurement
should settle it. It did, and it settled it differently.

### What was measured, 2026-09-12, at `d6f6e94` and re-run at the branch point

**The `authenticated` role is served exactly the capture** (rig 23a, D1200,
D1211). PostgREST on the pinned digest, beside an `apg dev` cluster of 33
migrations, configured from `compose.yaml`'s own `postgrest.environment`
values, `GET /` with `Accept: application/openapi+json`:

| role | status | bytes | normalized fingerprint | objects |
|---|---|---|---|---|
| `anon` | 200 | 2404 | `1da00c119b984b82…` | none |
| `authenticated` | 200 | 16035 | **`808ac715c09aeebc…`** | all 7 |
| `api_documentation` | 200 | 16035 | **`808ac715c09aeebc…`** | all 7 |

`808ac715c09aeebc…` **is** `projects/example/contracts/postgrest-openapi.canonical.json`'s
own fingerprint, recomputed at the branch point. So the live surface, read as
the ordinary caller, normalizes to the committed snapshot under **strict
equality** — not containment, not an object-set comparison. `anon` serves a
document with zero paths and a different fingerprint, which is the control
that the arm is reading privileges and not a constant. The pre-request hook
does not refuse the root document.

This removes the stage plan's candidate. The client does not need the docs
route — which is behind Basic auth (`bin/docs.sh`'s header), a password a
client may not hold — and it does not need the deployed document, which is
`0600 root` on a host and which ADR 0158 reserves for the address book.

**No route or tool serves the lock digest** (D1201). `mcp_tools.list_resources`
returns exactly `{contract_id, resources}`, measured; `tools/list` returns
names and input schemas; the runtime records which lock it loaded only in a log
line. And D1152/D1153 proved a plane can serve a different roster than the
file the document was rendered from, for eight minutes, while every reader said
otherwise. So the agent half of the check needs a field that does not exist
yet, reported **by the process that loaded the lock**.

**The canonical form reproduces in JavaScript, with one documented exception**
(rig 23b, D1203). `JSON.stringify(sortKeysDeep(x), null, 2) + "\n"` on the
pinned Node reproduces `openapi_normalize.canonical_bytes` byte for byte for
four of the five committed contracts — the release REST snapshot
(`85adb686223e`), the release MCP contract (`80a41ab0b986`), the project REST
snapshot (`808ac715c09a`), the project MCP contract (`3d7d6e6d513a`). It
**differs** for `contracts/app-openapi.canonical.json` (`f21bf4a8da90` against
`3007d815448e`) on exactly two lines, and only those two: line 494
`"minimum": 1.0` and line 1745 `"exclusiveMinimum": 0.0`, which JavaScript
prints as `1` and `0` because it has one number type. Both are Pydantic floats
that reached the document through FastAPI.

**The toolchain** (rig 23c, D1204, D1212). The pinned `NODE_RUNTIME_IMAGE` is
Node v22.23.2 with npm 10.9.8: it runs a `.ts` file directly with no flag,
`fetch` is a global function. `typescript`'s current stable is **7.0.2**, not
the 5.9.x line — the native compiler. In the pinned image, on musl,
`npm install --package-lock-only --ignore-scripts` produces a lockfile of 22
entries (the package plus 20 optional per-platform binaries), **every one
carrying an `integrity` hash**, and `npm ci --ignore-scripts` installs it and
`tsc --version` answers `Version 7.0.2`. A type error is reported as
`bad.ts(4,7): error TS2322` — with **exit status 1 under 7.0.2 where 5.9.3
exits 2**.

**Nothing in the tree computes an API change class, but the operator surface
already accepts one** (rig 23d, D1206, D1213). `compatibility.CHANGE_CLASSES`
names `api_operation_added` (minor), `api_operation_removed` and
`api_operation_changed` (major), `capability_added` (minor), and
`required_level` separates them as written — with an unclassified name raising
rather than defaulting to `patch`. No caller *computes* any of the three: the
only other mentions in `src/`, `bin/` and `tests/` are
`bin/upgrade.py:100–102`, which lists all three as classes an operator may
**declare** with `--also`. So a generator that classifies its own diff produces
exactly the vocabulary `upgrade plan --also` already takes, and the agreement
the stage plan asked for is an agreement by construction rather than a second
scheme.

## Decision

**A generated client embeds the digests of the artefacts it was generated
from, and checks at runtime only what it can read as itself.**

1. **Four inputs, one IR.** `client_ir.build(...)` reads exactly the merged
   reviewed surface, the project's (or, for a project declaring no set, the
   release's) PostgREST snapshot, the application snapshot, and the project's
   compiled lock. It reads no deployed document, no host file, and no
   `capabilities.yaml` (D930: the lock is compiled from the committed
   contract). Every emitter reads the IR and nothing else.

2. **`init()` is the whole defence, and it reads the served REST document as
   the caller.** It fetches `GET /` with `Accept: application/openapi+json`
   against the REST base URL it was handed, with the caller's own token,
   normalizes it the way the capture does, fingerprints it in the JavaScript
   canonical form, and compares to the embedded `rest_openapi_sha256` under
   **strict equality**. A mismatch refuses every later call. Equality is the
   right relation because rig 23a measured it, and because an object-set
   comparison lets a definition or a parameter move with the set unchanged —
   `bin/api-contract.py:457`'s own message says so.

3. **`basePath` is the one field the client asserts** (D1207). The capture
   validates `host`, `basePath` and `schemes` against the deployed document
   before substituting the sentinels. A client holds no deployed document; it
   holds a URL it is already connected to, and the served `host` carries
   `:443` (`fixture-alpha-dev.test:443`) where `new URL(restUrl).host` omits a
   default port. So the client substitutes `host` and `schemes` unread,
   asserts `basePath` equals the path of the URL it was given, and **refuses
   any residue** of the real values elsewhere in the document.

4. **Three outcomes, the third reported** (ADR 0195). `init()` answers
   `ok`, or `stale_contract` **naming both digests**, or — distinctly —
   `unreachable` when the service did not answer and `unparsable` when it
   answered something that is not the document. An unreachable service is
   never reported as a stale contract, and a refusal to determine is never
   folded into either answer.

5. **The agent half reads what the process loaded, not what a file says.**
   `list_resources` gains a `lock` member — `{tools_sha256, tool_count}` —
   taken from the lock object the running runtime loaded. It is the digest the
   lock **carried**, never recomputed at the edge; it is `null` when the loaded
   lock carries none (`CapabilityLock.tools_sha256` is `str | None`, and there
   is no `schema_version` field on it — D1215). The generated
   `listResources()` compares it to the embedded `tools_sha256` and refuses
   when they differ. This closes D1153 from the side that cannot lie: a plane
   that did not load the lock cannot report its digest.

6. **The application digest is embedded and not checked** (D1209). The client
   wraps three authentication operations only — login, refresh, me — and the
   application document is not served to a caller on a route a client holds.
   `app_openapi_sha256` is therefore provenance: it says which document the
   three operations were generated from, and a test asserts nothing reads it
   at runtime. The admin and storage halves are not wrapped.

7. **The version is ADR 0162's classes over the IR diff, and the artefact's
   own number.** `classify_changes(old_ir, new_ir)` returns only names in
   `compatibility.CHANGE_CLASSES`; the package version is the previous one
   bumped by `compatibility.required_level(...)`, starting at `1.0.0`. The
   client's number is the **artefact's**, not the template's: a client
   regenerated from an unchanged contract does not move.

8. **The canonical form has a second implementation, and it is guarded, not
   trusted** (D1203). `canonical.ts` is compared against
   `openapi_normalize.fingerprint` for every committed REST and MCP snapshot
   in the tree, in the toolchain image, by a test that fails on a difference.
   The `app-openapi` float divergence is **recorded as a refusal**: the
   emitter refuses to make the application document part of a runtime
   comparison, which is why point 6 embeds that digest without checking it.
   Two canonical serializers already exist in Python for one rule; a third in
   another language is admissible only with a comparison between them.

9. **A generated file may never contain** a credential, a token, a password, a
   signing key, a URL carrying userinfo, a call the contracts do not name, or
   a filter operator outside the capability schema's set. The emitter refuses
   each, and a test scans every emitted byte for them.

10. **The client is committed and drift-checked; the hook is a printed next
    step** (D1208). `projects/example/clients/typescript/` holds the emitter's
    output byte for byte; `apg generate --check` writes nothing and the gate
    refuses drift. Generation is **not** hooked to a migration: a client is
    generated from the snapshot, and a project's snapshot is captured only
    after a deploy, so a migration alone moves nothing the generator reads.
    The step that changes the generator's input is the capture, and the capture
    and the compile each **print** the generate command as a next step.

11. **No Python client** (D1205). The criterion the stage plan set — that the
    IR carries without a second reader of the contracts — is a property of two
    modules and is assertable without building the second client:
    `client_typescript.py` imports `client_ir` and the standard library only,
    and names no path under `contracts/` or `projects/`. A test asserts that by
    AST. What would make the Python client one module is exactly that
    assertion continuing to hold.

**The toolchain is pinned at `typescript` 7.0.2** and hash-locked by a
`package-lock.json` every entry of which carries an integrity hash, built with
`npm ci --ignore-scripts`. A typecheck proof asserts a **non-zero** exit *and*
the error line naming the file and the TS code — never the bare number, which
differs by major version (D1212).

## Consequences

**Easy.** A developer holds a package that cannot silently address a surface
that has moved: the first call after a drift names both digests. The client is
dependency-free, so it runs wherever `fetch` does. The generator is pure and
offline — every proof of it runs in a checkout, which is why `generated_client`
and `generated_client_toolchain` are declared offline claims (ADR 0202).

**Hard.** Two digests must be kept honest by different mechanisms: the REST one
by a served document, the lock one by a field a container reports. A project
that regenerates its client without redeploying gets a client that refuses
until the deploy lands — correct, and it will read as a bug the first time.
The `app-openapi` float divergence means the JavaScript canonical form is not
universal, and the boundary has to stay written down or someone will extend the
comparison to that document and find it red.

**Foreclosed.** A client that learns the live hash from the deployed document
(the stage plan's own stop condition). Generating from the host's
`capabilities.yaml`. A bare `tsc` exit-code assertion.

**Enforced by** `GEN-IR-001`, `GEN-EMIT-001`, `GEN-HASH-001`, `GEN-TYPES-001`,
`GEN-VERSION-001`, `GEN-TOOLCHAIN-001`, `GEN-CMD-001`, `GEN-ENV-001` and
`AGT-META-001`. `GEN-HASH-001` and `AGT-META-001` are **host** claims
(`generated_client_hash`, `agent_lock_reported`): a checkout cannot answer
whether a deployment serves the surface a client was generated for, so both are
`not_run` at this session's close and Session 24's trip collects them.

## Alternatives considered

**Read the deployed document for the live hash.** Refused. ADR 0158 reserves
it for the address book, it is `0600 root` on a host, and a client does not
hold one. It is also the stage plan's named stop condition for this session.

**Read the docs route's served OpenAPI digest.** Refused. The route is behind
Basic auth; a client may not hold that password. Rig 23a made it unnecessary:
the `authenticated` role is served a document with the same fingerprint
(`808ac715c09aeebc…` for both arms), so the ordinary caller's own read answers
the same question.

**Compare declared object sets instead of fingerprints.** Refused. A
definition, a parameter or a type can move with the object set unchanged —
`bin/api-contract.py:457` already says so in its own failure message. Rig 23a
measured strict equality, so there is no reason to ask for less.

**Normalize `host` and `schemes` strictly, as the capture does.** Refused
(D1207). The served `host` carries `:443`; `new URL(...).host` omits a default
port; a client comparing them would refuse every correct deployment. The
residue check keeps the substitution honest instead.

**Make PostgREST a verb of `apg dev`.** Refused (D1211, ADR 0203 stands). The
measurement needs a second configuration of the product, and ADR 0065/0066's
rule is that a rig is tied to the product by **reading its configuration** —
so the rig takes `compose.yaml`'s own `postgrest.environment` block rather than
becoming a supported command whose second Compose model nobody audits.

**Pin `typescript` on the 5.9 line.** Considered, and both arms were measured
green in the pinned image (rig 23c). 7.0.2 was chosen because it is current
stable, because the lockfile it produces hash-locks all 22 entries, and because
`lock-versions.sh --update --packages-only` would resolve to it anyway — a pin
two majors behind what the locker resolves is D540's shape. The cost is
recorded: the `tsc` exit status on a type error is 1, not 2.

**Set the `Idempotency-Key` header in the client** (D1202). Refused, because
the caller never sets that header: an agent supplies `idempotency_key` as a
**tool argument**, and the runtime sets the header toward PostgREST. A client
helper that set a header would be generating a request the product does not
make.

# Generated clients

`apg generate` writes a typed TypeScript client over the surface your project
publishes. It is defined by ADR 0204, and the sentence that decides everything
else in it is: **a generated client is a claim about the surface it was
generated from.** Not a convenience wrapper, not an SDK that adapts — a claim,
with a digest in it, that the client checks before it does anything.

That is why `init()` exists, why the client refuses to run until it has an
answer, and why the version of the generated package moves on its own rather
than on yours.

---

## 1. What it reads

Four committed artefacts, and nothing live:

| Input | What it contributes |
|---|---|
| `contracts/postgrest-api-surface.yaml`, merged with your project's | which relations, columns and functions exist at all — the **reviewed** surface, not what the database happens to expose |
| `contracts/postgrest-openapi.canonical.json` (your project's, if it has one) | the types, and the fingerprint `init()` will check |
| `contracts/app-openapi.canonical.json` | the three application operations the client wraps |
| the compiled capability lock | the agent tools, their arguments and their scopes |

**The deployed document is not an input** (ADR 0158). `generate` reads the
*rendered* document for one purpose only — to refuse a project this checkout has
not rendered, and to name the command that renders it. A client that learned a
live address at generation time would carry one deployment's accident into every
copy of the package.

```bash
bin/apg.sh generate --project project.yaml
bin/apg.sh generate --project project.yaml --check     # writes nothing; exit 5 on drift
bin/apg.sh generate --project project.yaml --out DIR   # anywhere inside the checkout
```

Without `--out`, a project declaring a migration set gets
`projects/<slug>/clients/typescript/`; one that declares none gets
`clients/typescript/` at the checkout root, over the release's surface alone.

---

## 2. The files

Ten, and every one is regenerated whole:

| File | What is in it |
|---|---|
| `contract.ts` | the four digests, the two contract ids, the version — **the only file carrying a digest** |
| `canonical.ts` | this repository's normalization, in JavaScript, so the client can compute the served fingerprint itself |
| `types.ts` | the relations' row and column types, the RPC argument interfaces, the enums, `FilterOperator`, `PtCode`, `AgentRefusal` |
| `client.ts` | `createClient`, `init()`, one method per published object, the three application operations |
| `agent.ts` | `createAgentClient`, one method per tool, `listResources()`, `idempotencyKey()` |
| `smoke.ts` | what the toolchain image runs to prove the package executes, not merely typechecks |
| `generated.json` | the intermediate representation: what `--check` compares against and what the next generation diffs for its version |
| `package.json`, `tsconfig.json`, `README.md` | the package, and its own account of itself |

**Do not edit them.** `--check` compares byte for byte and names the first file
that differs — the first rather than all of them, because the second difference
is almost always a consequence of the first.

---

## 3. `init()`, and its four answers

```ts
import { createClient } from "./client.ts";

const client = createClient({ restUrl, appUrl, token });
const started = await client.init();
if (started.kind !== "ok") throw new Error(started.kind);
```

`init()` fetches the REST service's OpenAPI document **as the caller** — with
your token, through the route you actually use — normalizes it with
`canonical.ts`, and compares the fingerprint with `CONTRACT.restOpenapiSha256`.
Until it answers `ok`, every other method returns `{ kind: "not_initialised" }`
without making a request.

| answer | what it means | what it carries |
|---|---|---|
| `ok` | the service is serving the surface this client was generated from | — |
| `stale_contract` | it is serving a **different** surface | `expected` and `served`, both digests |
| `unreachable` | the service did not answer | `reason` |
| `unparsable` | it answered something that is not that document | `reason` |

**`unreachable` is never reported as `stale_contract`** (ADR 0195). A client
that could not reach a service knows nothing about that service's contract, and
reporting one as the other would send you to re-capture a snapshot that was
already right.

Reading it as the caller is the part that is easy to get wrong and was measured
rather than assumed. PostgREST serves a *different document to every role*: to
the anonymous role it serves zero paths. A client that checked the digest as
`anon`, or read the deployed document instead, would be checking a surface no
caller ever sees (D1114, ADR 0158).

## 4. The two result unions

Every call answers; nothing throws for a refusal.

```ts
type Outcome<T> =
  | { kind: "ok"; status: number; body: T }
  | { kind: "refused"; status: number; code: PtCode | string; message: string }
  | { kind: "transport"; reason: string }
  | { kind: "not_initialised" };
```

`refused` carries the SQLSTATE the **database** raised — `PT401` not authorized,
`PT403` forbidden, `PT404` absent, `PT409` conflict, `PT412` an idempotency key
already used, `PT422` invalid — so a caller branches on the decision rather than
on an HTTP status that several decisions share. `transport` is the answer when
there was no answer, and it holds a reason, never a status it did not receive.

The agent half has its own, because a refusal from an agent plane is a different
object:

```ts
type AgentOutcome =
  | { kind: "ok"; content: unknown; structured: unknown }
  | { kind: "refused"; token: AgentRefusal | null; message: string }
  | { kind: "transport"; reason: string };
```

`AgentRefusal` is the closed set of tokens an agent may be told —
`approval_required`, `budget_exceeded`, `input_not_permitted`,
`resource_unknown`, `row_not_found`, `scope_not_held`, `write_conflict` — and
`token: null` is the honest answer when the refusal carried none. Nothing
upstream of the plane is relayed to a caller (D433), and the client does not
invent a token to fill the field.

`listResources()` answers a union of its own, `LockReport`, because it checks a
second digest:

| answer | when |
|---|---|
| `ok` | the running plane reports the lock this client was generated from; carries `toolsSha256`, `toolCount`, `resources` |
| `stale_contract` | it reports a **different** lock; carries `expected` and `reported` |
| `unconfirmable` | the plane answered without a lock digest at all — its lock predates schema 4 |
| `refused` / `transport` | as above |

**`unconfirmable` is not a failure and not a pass.** A deployment whose lock is
below schema 4 cannot say which lock it loaded, and a client that guessed either
way would be reporting a determination it did not make.

---

## 5. The version

The generated package's version is **the artefact's own number**, and it is
derived, never typed. Each generation diffs the new intermediate representation
against `generated.json` — the one the previous generation wrote — and applies
ADR 0162's change classes:

| what moved | class | version |
|---|---|---|
| a relation, an RPC or a tool **added** | `api_operation_added` / `capability_added` | minor |
| a relation gains a **column** | `api_operation_added` | minor |
| a tool gains an **alternative** discovery scope set | `capability_added` | minor |
| a published object or tool **removed** | `api_operation_removed` | major |
| a column **retyped or dropped**, an argument list changed | `api_operation_changed` | major |
| nothing | — | **unchanged** |

Worked: the example client is `1.0.0`. Adding `note_embeddings` to your project
and recapturing gives `api_operation_added` and `1.1.0`; dropping a column from
`notes` gives `api_operation_changed` and `2.0.0`; recapturing a snapshot whose
bytes moved but whose surface did not leaves it at the number it had.

That last row is not a detail. The first version of the rule bumped the patch
number on every regeneration, because "no changes" classifies as `patch` — so
the very first `--check` ever run failed on a client the command had just
written (D1224). **An unchanged contract keeps its version.**

---

## 6. Typechecking it

The client has no runtime dependency and no `node_modules` of its own. The
toolchain is a hash-locked image that carries the compiler and the type
definitions, addressed by path, and it runs with **no network**:

```bash
set -a; . ./versions.env; set +a
docker build --build-arg "BASE_IMAGE=${NODE_RUNTIME_IMAGE}" \
  -t apg-client-typescript services/clients/typescript
docker run --rm --network none \
  -v "$PWD/projects/example/clients/typescript:/work:ro" apg-client-typescript
```

`--network none` is the runner's default rather than an option a later caller
can forget, and the reason is measured: `npx tsc` resolves from the working
directory, finds nothing — a generated client has no `node_modules` by design —
and **fetches** (D1225). Every typecheck would have been a silent network call,
in a claim that is declared offline.

The image typechecks under `--strict` and then *runs* `smoke.ts`. Both, because
a compiler is not the last word: the first emitted package typechecked at exit 0
and could not be executed at all, because its import specifiers named `.js`
files that a package which is never compiled does not have (D1226). It costs
about a second and a half on a development machine with the image cached; the
[capacity envelope](capacity-envelope.md) carries that number with the
conditions it was sampled under.

---

## 7. What this is not

* **It is not an ORM, and not a query builder.** There are no joins, no
  transactions, no lazy relations and no expression language. Each published
  object gets one method; the filter operators are the capability schema's
  eight and no others; a column outside a relation's list is not a value the
  types accept. If a call is not in the reviewed surface it cannot be
  constructed, which is the property the generation exists to give.
* **It is not a holder of a credential.** Nothing that identifies a caller or a
  deployment is written into a generated file — no URL, no key, no token — and
  the emitter refuses its own output if one appears. The token you pass lives in
  a closure and never reaches a URL, a log or an error message.
* **It is not a browser bundle.** `canonical.ts` uses `node:crypto`. A browser
  build would need Web Crypto's asynchronous `subtle.digest` and a bundler
  nobody has pinned. The boundary is recorded rather than hidden, for the first
  person who wants one.
* **There is no Python client.** The intermediate representation is
  language-neutral and a second emitter is one module over it, but building one
  to be deleted is not a decision this session took (D1205).
* **Nothing regenerates automatically.** The capture and the compile each print
  the command, and the gate refuses a stale client — but the regeneration is
  yours to run. An adopter who ignores both holds a client whose `init()` will
  refuse, which is the designed outcome and not a gap.

---

## 8. What to do when

**`init()` answers `stale_contract`.** The deployment is serving a surface this
client was not generated from, and the two digests in the answer say so.
Normally the deployment moved ahead of you: regenerate from the commit the
deployment is actually at, which the deployed document's release names — not
from your working tree, which may be further ahead still. If the deployment is
the one behind, the client is right and the deploy has not happened yet.

**`init()` answers `unreachable`.** Nothing is known about the surface. Check
the URL and the route before you touch a snapshot: this is the answer a
misspelled host gives, and re-capturing a contract because of it is the mistake
the third answer exists to prevent.

**`listResources()` answers `unconfirmable`.** The deployment's lock predates
capability lock schema 4, which is the first schema that carries
`tools_sha256`. Deploy the project at a release that compiles a schema-4 lock;
until then the plane cannot confirm which roster it loaded, and neither can you.

**`generate --check` fails in the gate.** Either a contract moved and the client
was not regenerated — run the same command without `--check` and read the diff —
or a generated file was edited by hand, which the byte comparison cannot tell
apart from the first and does not try to.

**A typecheck fails after a regeneration.** That is the point. The contract
moved and your code names something it no longer publishes; the compiler is
telling you at build time what `init()` would otherwise tell a caller at
runtime, and what an untyped client would not have told anybody until a request
came back refused.

---

## 9. Where the rules are

| Rule | Where |
|---|---|
| A generated client is a claim about the surface it was generated from | ADR 0204 |
| The deployed document is the address book, not the diagnosis | ADR 0158 |
| A reader has three outcomes, and the third is reported | ADR 0195 |
| A caller value is a value, never syntax | ADR 0127 |
| What a version bump permits | ADR 0162 |
| A project owns its migration set and its capabilities | ADR 0198, ADR 0201 |
| The tokens an agent may be told | ADR 0178 |
| What the command itself refuses, flag by flag | `bin/apg.sh generate --help` |

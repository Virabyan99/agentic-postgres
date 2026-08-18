# 0112 — The application reference is one document, and it describes the surface

Status: accepted
Date: 2026-08-18
Session: 7, Run 9
Affects: ADR 0060, ADR 0069, ADR 0087, ADR 0101, D274, D333,
`bin/app-contract.py`, `services/auth-api/app/openapi_docs.py`,
`services/auth-api/app/storage_routes.py`, `services/docs/app.html`,
`contracts/app-openapi.canonical.json`

## Context

The application surface is served by two containers from one image (ADR 0101):
`auth` answers under `{api.public_base_path}/app`, and `storage` answers under
the same path plus `naming.STORAGE_PATH_SUFFIX`. A visitor sees one API.

`bin/app-contract.py` captured `create_app("auth").openapi()` and nothing else,
so the reviewed reference described the auth half and did not know the storage
half existed. Run 9 aggregated them, and aggregating them is what made anybody
look at what the storage half published.

## What was measured

`create_app("storage").openapi()`, read operation by operation against what the
routes actually return:

| operation | published before | actually returns |
|---|---|---|
| `POST /upload-intents` | `200` | **201**, plus 400, 401, 403, 422 |
| `POST /upload-intents/{id}/complete` | `200`, `422` | 200, plus 400, 401, 403, **404**, **409**, 422 |
| `GET /objects/{id}/download-url` | `200`, `422` | 200, plus 400, 401, 403, **404** |
| `DELETE /objects/{id}` | `200`, `422` | **204**, plus 400, 401, 403 |

Three separate defects, and each was independently wrong:

1. **`200` for operations that answer 201 and 204.** FastAPI defaults to 200 for
   a handler returning a bare `Response`.
2. **No failure response documented at all.** A reference saying every call
   succeeds is worse than no reference.
3. **A `422` in FastAPI's `HTTPValidationError` shape, which this service never
   emits.** FastAPI adds a 422 to any operation with a parameter; the storage
   routes take one `str` path parameter, which accepts every string, so its
   validation layer never rejects anything. A malformed object id is refused by
   the route's own `_object_id` as `MalformedRequest` — **400**, in the house
   shape.

`openapi_docs.py` exists to prevent precisely this and says so in its own
docstring, which records the same measurement being made for the auth router in
Session 6: *"the document FastAPI generates from the signatures alone is nine
paths, no request bodies, and a single `200` apiece."* It was written for one
router and never applied to the other.

**That is D333's question, and this is its second instance in this session.**
*When a decision is implemented, ask which of its callers got the
implementation.* Run 8 found `generate_secret_value` with one caller while a
second path called `token_hex` inline; this is the same shape in the
documentation plane, and it survived three runs because nothing aggregated the
document until now.

## Decision

**One reviewed document, covering both halves, describing what the surface
does.**

*The aggregate.* `bin/app-contract.py` merges the two documents `create_app`
produces. The storage half's paths are prefixed with
`naming.STORAGE_PATH_SUFFIX` — read, never spelled, because it is the same
constant the router's rule, its strip-prefix middleware and the published route
are all built from, and a literal would be a second derivation of a published
route (D177). A schema defined differently by the two halves is a **`ContractError`**,
not a merge: four response schemas appear in both today, byte-identical, and
this asserts that rather than trusting it. A silent merge would describe one
schema and serve the other, and whichever half merged second would win.

*The responses.* Every storage route now carries `status_code=`,
`openapi_extra=` and `responses=`, built from the same `errors.py` constants the
code returns. `responses=` rather than `openapi_extra` for every status, because
Session 6 measured that `responses=` **replaces** while `openapi_extra`
**deep-merges** — and a merged `$ref` alongside its siblings is a schema nothing
can satisfy.

*The unreachable 422 is pruned, in `create_app`.* An operation keeps its 422
when its route declared one and loses it otherwise. **Derived, not listed**: a
route that later gains a genuine `InvalidRequest` path keeps its documentation
by declaring it, and no list has to be kept in step. Pruned in `create_app`
rather than at capture time so that there is exactly one document — a prune
applied only when capturing would mean `create_app(mode).openapi()` and the
committed snapshot described different surfaces, and every test reading the
first would be measuring something nobody serves.

*The file is renamed* from `contracts/auth-openapi.canonical.json` to
`contracts/app-openapi.canonical.json`. It no longer holds the auth document,
the constant that names it was already `CANONICAL_APP_OPENAPI`, and the rendered
artefact was already `app-openapi.json`.

## Alternatives rejected

**Two documents and two pages.** It matches the containers and not the surface.
A caller does not know or care that two processes answer; it would have to read
two references to learn what one API does, and the second would be the one
nobody found.

**Declare a 422 on the routes that FastAPI gives one to.** This is what the auth
surface does, and it only works there by coincidence: every auth route with a
path parameter happens to have a genuine `InvalidRequest` path. Doing it here
would mean publishing a response the service cannot produce, which is ADR 0060's
complaint — a document that misdescribes a surface — arriving through the fix
rather than through the omission.

**Leave FastAPI's 422 in place.** Same objection, without the intent.

**Generate the reference at deploy time.** ADR 0069's rule stands: what the page
serves is what somebody approved. The candidate is a pure function of the
checkout, so review costs a diff and nothing else.

## Consequences

`test_the_application_page_does_not_repeat_the_rest_surfaces_warning` is
**replaced by a stricter form**, which this ADR authorises. It asserted
`"403" not in note`, using the status code as a proxy for the REST document's
verb warning. The proxy acquired a false positive the moment the page gained the
storage half: the upload note has to say that a provider answers **403** to a
request omitting `If-None-Match`, which is a fact about R2 and nothing to do
with `follow-privileges`. A proxy that has acquired a false positive is not a
test to relax — it is a test to replace with the thing it was standing for, and
the REST warning's fingerprint is the three uppercase verbs plus the phrase
naming where that document comes from. Both are now checked, which catches a
verbatim copy exactly as before and is not fooled by an unrelated status code.

The application page gains a storage section, and it carries the four rules a
reader cannot infer from a schema: a presigned URL is a bearer credential, **a
delete does not revoke one already issued**, an upload URL must be sent
`If-None-Match: *`, and one 404 covers absent, foreign, pending and deleted
alike. The non-revocation is the one a reader would otherwise assume the other
way round, which is why it is stated rather than left to the document.

The aggregate is 13 operations where it was 9. `bin/app-contract.sh --check`
compares it byte for byte, and `--update` still streams a candidate the operator
redirects themselves — deployment never approves.

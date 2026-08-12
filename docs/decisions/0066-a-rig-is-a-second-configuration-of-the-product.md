# 0066 — A rig is a second configuration of the product, and the two must be tied together

Status: accepted
Date: 2026-08-12
Session: 5, Run 9
Amends: [0052](0052-the-request-plane-and-its-search-path.md)
Affects: SEC-ANON-001, API-REST-001, API-RPC-001, API-LIMIT-001

## Context

`PGRST_DB_PRE_REQUEST` was set nowhere in the product. Zero occurrences in
`compose.yaml`, zero in `src/agentic_postgres/`.

Migration 0008 creates `app_private.postgrest_pre_request()`, migration 0009
replaces it, both grant `EXECUTE` on it by name to exactly the three request
roles, and 0008 ends with `NOTIFY pgrst, 'reload schema'` under a comment that
begins *"`db-pre-request` names a function that did not exist a moment ago"*.
Every part of the identity plane was built, granted, commented and reloaded.
Nothing ever told PostgREST to call it.

The consequence is total rather than partial: `app.user_id` is never set, so
`app.current_user_id()` returns NULL, every row policy denies, and every write
RPC raises `AP401: no request identity for this transaction`. The first live run
of Run 8's proofs produced exactly that, four times.

Measured on the locked image with a control — same nine migrations, same token
carrying `sub` and `role`, one setting different:

| arm | `POST /rpc/create_note` | `GET /notes` |
|---|---|---|
| `PGRST_DB_PRE_REQUEST` set | **200**, `owner_id` = the token's `sub` | the row |
| unset (as shipped) | **401** `AP401: no request identity` | `[]` |

The unset arm reproduced the deployed failure byte for byte.

**Why no test caught it.** `tests/contract/test_api_behaviour.py` builds a
PostgREST rig and sets `PGRST_DB_PRE_REQUEST` on it *itself*, at line 227. The
hook's behaviour is thoroughly tested — against a container configured with a
setting the product does not apply. The rig was not wrong; it was complete. The
product was the incomplete one, and nothing compared them.

This is the third instance in one run of a single shape. ADR 0065 (D188): a
constant measured against a rig that did not set `openapi-security-active`,
which the product does. D189: a test fixture captured from a cluster built
without the repository's own `COMMENT ON` statements. And now the reverse
direction — a setting the rig has and the product lacks.

## Decision

**`PGRST_DB_PRE_REQUEST: app_private.postgrest_pre_request` in `compose.yaml`**,
schema-qualified because `app_private` is on no request role's `search_path`
(ADR 0052), and in the environment because `db-config` is `false` so an
`ALTER ROLE ... SET` cannot supply it.

**And the structural rule, which is the point of writing this down:**
`test_every_setting_the_behaviour_rig_configures_is_configured_by_the_product`
parses the `PGRST_*` names the rig passes to `docker run` and asserts each one
is either set by `compose.yaml` or listed in an explicit exemption table with a
reason. A rig that configures something the product does not is now a test
failure naming the setting.

The exemptions are the settings that are genuinely rig-only — an address the
rig binds, a secret the rig invents — and each carries a one-line reason. An
exemption is a decision a reviewer sees; an absence is not.

## Alternatives

**Fix the setting and move on.** Rejected. Three instances of one shape in one
run is a pattern, and the two already found were caught by accident: D188 by a
capture refusing, D189 by a control on a re-capture. Nothing was watching for
the third and nothing would watch for the fourth.

**Assert the product's `PGRST_*` set against a hand-written list.** Rejected: a
second list drifts from both. The rig is already a maintained statement of what
a working PostgREST needs, and tying the product to it makes the rig's
completeness do the work.

**Compare in the other direction too — refuse a product setting the rig lacks.**
Rejected *for now*, and worth stating because it is the symmetric case ADR 0065
covers: the rig legitimately omits routing, CORS and pool settings that have no
bearing on behaviour. Requiring symmetry would produce a long exemption list
that nobody reads, which is how a rule stops being enforcement.

## Consequences

- The identity plane works. Four of Run 9's eight failures had this one cause.
- A deployment made before this change has a hook that never ran. Nothing is
  corrupt: no identity was ever established, so no row was written under a wrong
  owner. The failure mode was refusal, not confusion.
- The rig at `tests/contract/test_api_behaviour.py` is now load-bearing in a
  second way: adding a `PGRST_*` to it obliges the product to set it or exempt
  it. That is intended, and the test says so where a reader of the rig will
  find it.

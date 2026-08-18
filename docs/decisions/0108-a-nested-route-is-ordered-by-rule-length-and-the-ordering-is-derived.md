# 0108 — A nested route is ordered by rule length, and the ordering is derived

Status: accepted
Date: 2026-08-18
Session: 7, Run 7
Affects: STO-OWN-001, STO-URL-001, DEP-ISO-002

## Context

Every route this project has published so far has been a **sibling** of every
other one: `/api/rest`, `/api/app`, `/docs/rest`, `/docs/app`. No request has
ever matched two routers, so no ordering has ever mattered and none has ever
been measured.

`/api/app/storage` is the first **nested** route. It lies inside `/api/app`,
which the auth service has served since Session 6 Run 10, and every request to
the storage surface matches both routers:

```
apg-<key>-app      Host(`d`) && (Path(`/api/app`)         || PathPrefix(`/api/app/`))
apg-<key>-storage  Host(`d`) && (Path(`/api/app/storage`) || PathPrefix(`/api/app/storage/`))
```

If the wrong one wins, `POST /api/app/storage/upload-intents` arrives at the auth
service as `/storage/upload-intents` and FastAPI answers **404** — which at the
edge is indistinguishable from a missing route, from a missing container, and
from Traefik's own 404 (D186, D187). The failure mode of getting this wrong is
the one this repository is worst at diagnosing.

### What was measured

A throwaway rig on the locked Traefik digest, two backends that echo which one
they are and what path they received, routed by the same label shapes
`runtime_override.py` renders, behind the same
`Label(`apg.traefik.scope`,`managed`)` constraint the edge uses.

**Traefik's default priority is the rule string's length, exactly.** Read back
from Traefik's own API rather than inferred from behaviour:

| router | rule length | priority |
|---|---|---|
| `rig-app` | 68 | 68 |
| `rig-storage` | 84 | 84 |

The storage rule is the application rule with `/storage` inserted into both
matchers, so it is **exactly 16 characters longer, for every project and every
domain** — both rules carry the same `Host()` clause, so the domain cancels.
The nested route wins by construction, not by luck.

**Priority is length, not specificity, and that is the trap.** With a control:

| router | rule | length | request | reached |
|---|---|---|---|---|
| `rig-short` | ``PathPrefix(`/api/app/deep`)`` | 50 | `/api/app/deep/x` | **the app backend** |
| `rig-long` | ``Path(`/api/app/deeper`) \|\| PathPrefix(`/api/app/deeper/`)`` | 82 | `/api/app/deeper/x` | its own backend |

`rig-short` is **strictly more specific** than the application router and still
loses to it, because it is written in fewer characters. A storage rule written
the concise way — one `PathPrefix`, which is what anyone reaching for brevity
would write — would be shorter than the parent's and would never match a single
request. Nothing would error; the storage service would simply never be reached,
and the symptom would be a 404 from the auth service.

**The boundary is not a 404 here, and that is the second difference.** D162
measured that `PathPrefix` is a string prefix, and the house answer has been the
two-matcher pair. For a sibling route the proof is a 404: `/api/restaurant` is
routed by nobody. For a **nested** route the sibling is caught by the parent:

```
/api/app/storagex        -> the app backend, path /storagex
/api/app/storage-extra   -> the app backend, path /storage-extra
/api/app/storage2        -> the app backend, path /storage2
/api/application         -> 404, Traefik's own          (the control)
```

So a boundary test for this route **cannot** assert a status code. `/storagex`
reaches FastAPI, which answers 404, and from outside that is the same 404 as
Traefik's — the same indistinguishability D186 records, arriving through a door
the existing tests do not cover. The boundary is a claim about **which service
answered**, and only the access log's `RouterName` or a distinguishable body
settles it.

## Decision

**The storage router's precedence is derived from its rule, and no explicit
`priority` is set on any router.**

**The two-matcher construction is load-bearing for the nested route**, and not
only for the segment boundary it was adopted for. `_storage_labels` says so in
its docstring, and a contract test asserts the *interpolated* storage rule is
strictly longer than the *interpolated* application rule.

**The boundary proof names the service, never the status code.** The offline
test asserts the rule shapes; the host proof reads `RouterName` from the access
log.

## Alternatives

**Pin explicit priorities on both routers.** Rejected, and the arithmetic is
why. Setting one requires setting the other, because a number above "whatever
the app router's default happens to be" is a number that depends on the
project's domain length. That means renumbering five routers — health, rest,
docs, app, app_docs — and changing the deployed behaviour of four routes that
work, in a run about a fifth. The ordering is already correct by construction;
an explicit priority would be a second authority for it, and D264 is what two
authorities for one value cost.

**Give storage its own top-level path, `/api/storage`.** Rejected: it is a
surface of the application API, shares its issuer and audience, and `naming.py`
already derives `route_storage` from `route_app` (Run 1). Moving it would make
the two routes siblings and this ADR unnecessary — at the cost of a published
path that says the storage plane is a separate API, which it is not.

## Consequences

* A future route nested under an existing one inherits this question and does
  **not** inherit the answer. The invariant asserted here is about these two
  rules; a third route needs its own assertion.
* The test asserts lengths of **interpolated** rules. The raw label values hold
  `${API_APP_PATH:?required}` and `${API_STORAGE_PATH:?required}`, which differ
  by four characters for a reason that has nothing to do with the paths — a test
  comparing those would pass, and would be measuring the spelling of two
  variable names.
* Traefik's computed priority is observable at `/api/http/routers`. The host
  proof reads it, so a change in Traefik's default ordering is caught as a
  changed number rather than as a route that stopped working.

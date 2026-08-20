# 0121 — The agent plane is a third mode of the one application image

Status: accepted
Date: 2026-08-20
Session: 8, Run 4
Affects: ADR 0083, ADR 0101, ADR 0113, D201, D321, D406, D423, D424,
`versions.in.yaml`, `services/auth-api/Dockerfile`,
`services/auth-api/app/settings.py`, `compose.yaml`, `services/mcp/`

## Context

ADR 0101 runs the auth service and the storage service from **one image, two
modes selected by `APP_MODE`**, and `compose.yaml` states the reason at the
service it introduced:

> one build context, because a second service directory could not import the
> JWT verifier, the strict request parser or the error vocabulary any more than
> either can reach `src/`.

Run 4 adds the MCP runtime, which is the **fourth verifier** (ADR 0113) and
therefore needs exactly those three things: `LocalKeySet.from_path` to read the
rendered key set, a strict claims parser to enforce ADR 0115's `token_use`, and
the error vocabulary a refusal is spelled in. A `services/mcp/` directory has
existed since Session 1, holding a `.gitkeep` and nothing else.

So the question is not "which layout is tidier". It is whether a fourth verifier
can be given the third verifier's key-set mechanism at all from a second image —
and, underneath that, whether the framework it needs can live beside the one the
other two modes already run.

## What was measured

Against the locked `python:3.12-slim` digest
(`sha256:229a2c5b…`), on Docker 29.5.2. Every arm has a control.

**The locked FastMCP version installs and does not import.**

| arm | result |
|---|---|
| `pip install fastmcp==2.14.1` | **succeeds** |
| `import fastmcp` after it | **`ModuleNotFoundError: No module named 'pydantic_settings'`** |
| the same, with `mcp<2` constrained | **imports**, mcp 1.29.0, pydantic-settings 2.15.0 |
| CONTROL — `fastmcp==999.999.999` | refused, *"No matching distribution found"* |

The cause, read rather than guessed: fastmcp 2.14.1 declares `mcp>=1.24.0` with
no ceiling; pip resolves **mcp 2.0.0**, which no longer carries
`pydantic-settings`; and fastmcp 2.14.1 imports `pydantic_settings` directly
without declaring it. **The entry did not rot through a change here.** It rotted
because an upstream floor had no ceiling, and it survived from Session 1 to
Session 8 because nothing ever built from it — D201's condition, and now D201's
outcome, arriving through a version that *does* exist.

**The version that can be adopted is bounded by FastAPI, and the boundary was
bisected rather than assumed.** `fastmcp-slim[server]` moved to
`starlette>=1.0.1` at 3.4.1; `fastapi==0.121.2` requires
`starlette<0.50.0,>=0.40.0`.

| candidate | with `fastapi==0.121.2` |
|---|---|
| 3.4.0 | **resolves** |
| 3.4.1 – 3.4.7 | `ResolutionImpossible` |
| CONTROL — 3.4.7 + `pydantic==1.10.0` | `ResolutionImpossible` |
| CONTROL — 3.4.5 alone | resolves |

3.4.5 is the number the runbook asserts. It exists — the plan predicted it was
fabricated (D406) and it is not — and it **cannot be installed beside this
repository's FastAPI**.

**3.4.0 co-resolves with the entire pinned set, for real rather than
`--dry-run`**: fastapi 0.121.2, pydantic 2.13.4, pydantic-settings 2.14.2,
uvicorn 0.50.2, pyjwt 2.13.0, cryptography 50.0.0, `psycopg[binary]` 3.3.4,
psycopg-pool 3.3.1, argon2-cffi 25.1.0, boto3/botocore 1.43.72. Every one
imports; `pip check` is clean; it resolves mcp 1.29.0 and starlette 0.49.3.

**The framework's own surface, measured against a running server** (Rig H):

- `TokenVerifier.verify_token(self, token: str) -> AccessToken | None` — the
  verifier is handed the **raw compact token string**, which is what Run 5 needs
  to forward.
- No `Authorization` header → **401**; a bad token → **401**; a good token →
  **200**. The refusal branch discriminates.
- `AccessToken` carries `token, client_id, subject, scopes, expires_at, claims,
  resource`.
- `http_app(path=…)` returns a Starlette application, so the runtime is mounted
  the way every other service here is served.

## Decision

**The MCP runtime is a third `APP_MODE` of the one application image, and
`FASTMCP_VERSION` is `3.4.0`.**

1. `APP_MODES` becomes `{auth, storage, mcp}`. The mode stays **required and
   never defaulted**, for the reason ADR 0101 already gives.
2. The image installs FastMCP at the locked version, and the Dockerfile's
   trailing import control names it — because "it installs" and "it imports" are
   two claims, which is the whole of ADR 0083 and is exactly what 2.14.1 failed.
3. `services/mcp/` is **deleted**. A directory that cannot hold the code is a
   directory that will eventually hold a second copy of it.
4. `3.4.0` is pinned as a **measured ceiling**, not as a preference, and the
   reason is recorded at the entry: it is the last release that can share a
   process with this repository's FastAPI.

## Alternatives rejected

**A separate `services/mcp` image at fastmcp 3.4.7.** It cannot import
`LocalKeySet`, so the fourth verifier would get a **second key-set parser** —
two authorities for one document (D264), in the exact place D381 already cost
this project a container that started and verified nothing. `compose.yaml`
made this argument for storage; nothing about MCP weakens it.

**Adopt `latest` and bump FastAPI to 0.141.1.** Measured: 0.141.1 is what
co-resolves with fastmcp 3.4.7. It is a twenty-minor-release upgrade to the
**auth service** — the one that hashes passwords and signs tokens — bought
inside a run about the agent plane, and Session 6 Run 7 declined that same bump
with a measured version behind its refusal. **This is D321 with a different
package**: a plain `--update` once moved `pgvector:pg18` and `python:3.12-slim`
and would have shipped an unmeasured PostgreSQL upgrade inside an unrelated
session. Refused for D321's reason, and the lock was updated with
`--packages-only` so it could not happen by accident.

**Keep 2.14.1 and constrain `mcp<2`.** It works — measured. But it pins a
dependency of a dependency this repository does not otherwise name, which is a
second authority for somebody else's resolution, and it adopts a superseded
major to avoid a bump that turns out to be free at 3.4.0.

**Give the MCP mode the shared database settings.** Refused, and the refusal is
D407's boundary made executable: the MCP runtime holds **no database
credential**, so `APG_DATABASE_*`, `APG_POOL_SIZE` and a passfile are not merely
unread in this mode — they are **forbidden**, and `load` refuses to start if one
is present. This is the same shape as storage refusing a signing key. A mode
that tolerated a database credential would make the considered zero in ADR
0099's connection budget an accident waiting for a caller.

## Consequences

- **The auth and storage containers carry FastMCP they do not import.** That is
  the price of one image and it is the same price ADR 0101 already accepted for
  boto3 in the auth container. It is bounded by the same thing: the credential
  boundary is the secret contract's per-consumer materialization, not the image.
- **`FASTMCP_VERSION` is now load-bearing in a way it never was.** Raising it
  past 3.4.0 breaks the one-image model, so a future bump is a decision about
  ADR 0101 rather than a dependency refresh. The reason is written at the lock
  entry, where whoever raises it will be standing.
- **The lock now has an entry that has been run.** Every other `packages:` entry
  earned its number from a resolver; this one has been imported, served over
  HTTP and had its refusal branch exercised.
- ADR 0113's mechanism reaches the fourth verifier unchanged, which is what
  "nothing new is designed" was supposed to mean.

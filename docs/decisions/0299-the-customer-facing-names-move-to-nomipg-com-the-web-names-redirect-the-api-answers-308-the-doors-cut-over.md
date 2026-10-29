# 0299 — The customer-facing names move to nomipg.com: the web names redirect, the API answers 308, the doors cut over

- **Status:** Accepted
- **Date:** 2026-10-29
- **Session:** 47, Run 1 (`docs/plans/session-47-implementation-plan.md`, D2943,
  D2946 (1)(6)(7), D2962–D2966, D2973; rows D2983–D2985, D2988; rigs 47b, 47c)
- **Affects:** `src/agentic_postgres/site_build.py` (`INVITATION_ADDRESS`,
  `CONTROL_DOMAIN`, `SITE_URL`, `ALLOWED_ORIGINS`), `services/console/public/index.html`
  and `accept.html`, `bin/login.sh`, `bin/build-cli.py`, `naming.py` (a docstring),
  `project.control.example.yaml` (a comment), `tests/contract/test_site.py:146-147`
  (rewritten to read the constant), the tests that pin the old name; on the host:
  `host.yaml` (both copies), **each moved slot's own manifest**, the control
  manifest; the two Cloudflare zones. Runs 10 and 13 (Sheets N0–N3, H0, L1, M0).
- **Related:** ADRs 0268 (the doors), 0281 (the cookies), 0283 (the site), 0286 (the
  relay's zone), D2719 (proxied site CNAMEs), D2728.

## Context

The operator bought `nomipg.com` (D2943) and chose, at planning, **the domain
only** — the product keeps its name, `agentic-postgres-cli` and `apg` theirs — the
old web names redirecting for twelve months, the API, relay and doors cutting
over at the release, and the secret store keeping its name (D2946).

## Measured

- **Rig 47b** (`~/s47/rigs/47b/`): a project manifest and the control example
  rendered `--render-only` twice under a rig-only slug, only `project.domain`
  differing (control: the same domain twice diffs empty). What moves:
  `project.domain`, `jwt.issuer`, every `routes.*` URL, `inputs.project_sha256`,
  and in `compose.env` `PROJECT_DOMAIN`, `JWT_ISSUER`, `CUSTOMER_POOL_HOST`,
  `CUSTOMER_DIRECT_HOST`, `POSTGREST_CORS_ORIGINS`, and for the control project
  `APG_CONSOLE_ORIGIN`, `APG_SQL_RELAY_HOST`, `APG_SQL_RELAY_ZONE`,
  `APG_CONSOLE_SQL_RELAY_ORIGIN`. **No identity moves** — no key, role, network,
  volume, bucket or stanza. A manifest whose domain moved without its
  `api.rest.allowed_cors_origins` is **refused at render, exit 2** (*"does not
  contain 'https://<domain>'"*). `slot.sh redeploy` deploys from the slot's **own**
  manifest, `/etc/agentic-postgres/slots/<key>/manifest.yaml` (`bin/slot.py:391-448`),
  not from `host.yaml`; a slot's `allocated` state reads that file's presence and
  a deployed document, never its content (`slot.state`). The edge issues one
  HTTP-01 certificate per router host (`infra/edge/traefik.yaml:134-143`).
- **Rig 47c, urllib** (`~/s47/rigs/47c/`, Python 3.12.15 in `python:3.12-slim` and
  3.14.4 alike): a POST answered **301 is followed as a body-less GET**; a POST
  answered **308 is not followed** (`HTTPError 308`); control: the direct POST,
  200 with its body.
- **Rig 47c, Cloudflare** (read-only, the API): both zones `free`; neither has an
  `http_request_dynamic_redirect` entrypoint yet; Free allows 10 Single Redirect
  rules per zone, wildcards, no regex, codes 301/302/307/308; Email Routing
  `ready` on the old zone, `unconfigured` on `nomipg.com`; the Pages project
  `agentic-postgres-site` serves the old apex and `www.`.

## Decision

1. **Moving** (customer-facing): the apex and `www.` (proxied CNAMEs to Pages,
   D2719), `control.`, `sql.`, the mail records (MX ×3, SPF, DKIM — Email Routing),
   and each customer slot's five names (`slotN.`, `pool.`, `direct.`, `*.pool.`,
   `*.direct.`). **Staying** in the old zone: `secrets.` (the store keeps its
   name), `alpha-db.` and `beta-db.` (the operator's appliance projects, not
   customer-facing), `snippets-db.` (not ours). The old zone stays registered.
2. **The web names redirect; the API refuses to be followed.** On the old zone,
   Single Redirect rules, path and query preserved: the apex and `www.` → the same
   URL on `nomipg.com`, **301**; **`control.` → the same URL on `control.nomipg.com`,
   308, for every path** — a browser follows a 308 for a page exactly as a 301,
   and the 1.24.0 CLI, whose saved context names the old API, **fails loudly**
   instead of turning a POST into a GET that answers 200 (rig 47c). The old
   `control.` record becomes **proxied and redirect-only** (D2966) — it reaches
   nothing. `sql.` and the doors are not HTTP and are not redirected: they cut over
   at their project's redeploy. The rules are removed on **2027-10-29**.
3. **A domain moves on the host in three places, with backups**: `host.yaml`
   (`/etc` and `/home/op`, D2930) for each slot's `domain`; **each slot's own
   manifest** — `project.domain` and `api.rest.allowed_cors_origins` together,
   the latter by replacing the old origin with the new, as `slot.prepare` writes
   it; the control manifest's `project.domain`. Then the project is redeployed.
4. **What a move ends, said before it**: the issuer moves, so **every token a moved
   project issued stops verifying at its redeploy** — the console's sessions (whose
   `__Host-` cookies are the old origin's anyway), and the sessions of a customer
   application on `slot3-prod` or `slot10-prod`. Sheet M0 tells `slot10-prod`'s
   person so. Every saved CLI context logs in again (Sheet L1; the agent's from
   WSL).
5. **The order of the cutover** (Run 13): N0 the new zone's records (the
   operator's explicit word first, D2946's rule for every Cloudflare DNS write),
   read back by `dig @1.1.1.1`; N1 Pages custom domains and Email Routing on
   `nomipg.com`; the bump pushed (the site moves; D2973's window); H0; the
   redeploys one project at a time, each read under its new names before the next;
   N2 the redirects, read back by `curl -sI`; L1; N3 the stale old records.
6. **A guard that names a literal reads the constant**: `test_site.py:146-147`,
   a regex over `agenticpostgresql.com` that would check nothing after the move,
   reads `site_build`'s own domain constant (D2962). `capacity.py`'s three
   measurement records keep the old name: they say what was measured.

## Consequences

- Customers read one domain; the operator's own names do not move.
- The old site and console addresses keep working for a year; the old API name
  answers every call with a 308 a client must act on.
- Every redeploy of a moved project is also a sign-out of its users.
- Certificates are issued per name at the first request after its record exists;
  a name without a record cannot be issued and must not be routed (D2933's rule:
  five records before `ready`).

## Alternatives considered

- **301 for every old name** — measured to turn the CLI's POSTs into GETs.
- **Keep the API on both names** — two origins for the console's cookies and its
  `Origin` check (ADR 0281), and two issuers; refused.
- **Rename the product too** — the operator's answer was the domain only.

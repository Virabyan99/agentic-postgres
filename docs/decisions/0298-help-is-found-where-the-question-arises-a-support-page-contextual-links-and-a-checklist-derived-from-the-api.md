# 0298 — Help is found where the question arises: a support page, contextual links, and a checklist derived from the API

- **Status:** Accepted
- **Date:** 2026-10-29
- **Session:** 47, Run 1 (`docs/plans/session-47-implementation-plan.md`, D2958,
  D2971, D2976)
- **Affects:** `site/pages/docs/support.md` (new), `src/agentic_postgres/site_build.py`
  (`DOCS_GROUPS`), `services/console/public/app.js` and `nav.js` (`#/help`, each
  page's help link, the Overview checklist), `services/console/public/pages.json`.
  Tests: `test_site`, `test_console_pages`, a new check in the console set that
  every help link is a route the site build produces. Runs 7–8.
- **Related:** ADRs 0195, 0281 (no cross-origin call), 0283 (the site), 0292 (the
  support bundle).

## Context

The person: *"I didn't find any support page."* The console has none; the support
bundle sits in a project's Settings. The planning prompt asked for a
getting-started checklist that follows a customer from the invitation to a
connected application.

## Decision

1. **A support page on the site**, `site/pages/docs/support.md`, in `DOCS_GROUPS`:
   how to get help (`invite@` the product's domain, ADR 0299), what to send, how
   to make and send a support bundle (ADR 0292), and the refusals page.
2. **`#/help` in the console**: the same, with links to the site's docs groups,
   reachable from the top bar on every page.
3. **Every console page carries one contextual help link** to the site route
   that documents it. A help link is a **navigation**, never a fetch, so the
   console's `connect-src` does not change. A test reads every help link in
   `app.js` and `nav.js` and fails on one that is not a route the site build
   produces.
4. **The Overview's getting-started checklist is derived from API state only**:
   *second factor enabled* (`GET /v1/me`'s `second_factor.enabled`), *an
   organisation* (`GET /v1/organizations`), *a project* or *a project being
   created* (`GET /v1/projects`, ADR 0296's open operations), *a password made for
   a door* (a succeeded `credential.rotate` in the organisation's operations), *a
   connection seen* (the project's `GET /v1/projects/{key}/usage` sample
   `customer_connections` above 0 — a sample, so a connection that came and went
   between samples may read 0, and the item says *"not seen yet"*, never *"none"*). A reading the console could not make is
   shown as *not read*, never as done or not done (ADR 0195). **Nothing is
   stored**: a checklist that remembered in the tab would forget on another device.
5. **No new Ledger row** (D2971): `#/help` maps to `support_bundle` and `console`;
   the tracker and the activity view to `projects_self_service`.

## Consequences

- A customer stuck on any page is one click from the page that explains it.
- The checklist may say *not read* when usage is unavailable; that is its correct
  answer.
- Site routes become a dependency of the console; renaming a docs page is a red
  test until the link moves.

## Alternatives considered

- **A chat widget or a ticketing provider** — a third party in the page.
- **A checklist with ticks the customer sets** — storage, and a state the API
  does not know.

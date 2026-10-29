# 0295 — The console gains features inside first-party rules: fixed-route modules, no build step, its own stylesheet budget

- **Status:** Accepted
- **Date:** 2026-10-29
- **Session:** 47, Run 1 (`docs/plans/session-47-implementation-plan.md`, D2946 (5),
  D2947, D2955–D2957, D2967, D2968, D2978; rows D2986; rig 47a)
- **Supersedes, in part:** [ADR 0288](0288-the-site-and-the-console-share-one-look-self-hosted-typefaces-one-token-block-presentation-in-stylesheets-only.md)
  — **decision 8** (*"the console gets hooks, not features"*) whole; the **joint**
  30,720 B stylesheet budget (`tests/contract/test_look.py:61`); the **freeze** of
  the walk drivers' anchors (`test_console_look.py::test_the_drivers_anchors_are_unchanged`
  stays a test, re-counted under decision 5 below); and the Consequences line that
  forecloses copy buttons. Every other decision of ADR 0288 stands.
- **Affects:** `services/console/public/` (new modules `ui.js`, `nav.js`,
  `messages.js`, `progress.js`; `app.js`, `app.css`, `index.html`, `pages.json`),
  `services/auth-api/app/connection_snippets.py` (three clients added, D2991),
  `services/console/serve.py` (`ROUTES`),
  `tests/contract/test_console_server.py` (`LISTED`),
  `tests/contract/test_console_scram.py::test_every_script_parses`,
  `tests/contract/test_look.py` (the budget), `tests/contract/test_console_look.py`
  (`ANCHORS`), the three walk drivers (`console_walk.py`, `journey_walk.py`,
  `sql_walk.py`), `tests/contract/test_connection_snippets.py` (the executions) and
  `tests/external/browser/console_look.py`. Runs 4–9.
- **Related:** ADRs 0280 (the fixed-route static server), 0281 (the cookies and the
  Origin), 0285–0287 (the editor and its relay), 0288, 0291 (the token shown once).

## Context

The first person to use the hosted console (Session 46, 2026-10-28, D2936) found
eleven steps no page gave them, and the operator agreed the console *"looks and
feels terrible while using"*. Every one of the person's findings — a progress
tracker, a state that survives a refresh, a copy button with feedback, a disabled
form during a creation, Connect steps for a newcomer, the editor's state at the
top — needs new script, new text or a new view. ADR 0288 decision 8 forbade all
three for Session 45, deliberately, so the visual pass could not move the walk
drivers; its Consequences named copy buttons and operation rows as Stage 6
candidates. The budget it set (`site.css` + `app.css` ≤ 30,720 B) had 1,827 B
left at `ec75870`.

The planning prompt asked whether a build step or a library should enter. The
operator's answer (D2946 (5)): supersede decision 8, **build-free**.

## Measured

Rig 47a (`~/s47/rigs/47a/`, 2026-10-29): the console's own policy —
`serve.security_headers("wss://sql.nomipg.com")`, imported from the checkout,
never retyped — over rig pages served by a fixed table, in the pinned Playwright
image (`v1.63.0-noble@sha256:72bd171a…`), at 390 × 844 and 1280 × 800:

| Capability | Reading (both widths) |
|---|---|
| A static ES-module `import` of a second routed file | loaded |
| `CSS.supports("selector(:has(a))")` and a `:has()` rule in a routed stylesheet | true; applied (`rgb(0, 128, 0)`) |
| An SVG icon as static markup in a `<template>`, cloned by script | `svg` in the SVG namespace, 16 × 16 |
| `<progress>` | `value` 40, `position` 0.4 |
| `<dialog>.showModal()` / `close()` | open, `:modal` true; closed |
| An `aria-live="polite"` region written by script | text set |
| `navigator.clipboard.writeText` from a click (permission granted), read back | the exact string |
| `scrollWidth` vs `innerWidth` | equal (390, 1280) |
| A `Tab` from a fresh load | lands on the first link |
| **Control:** an inline `<script>` under the same policy | did not run |

D2892's reading — *a string-evaluated Playwright wait is refused under this policy*
— was **not reproduced** (row D2986): both an expression string and an arrow-function
string passed to `wait_for_function` ran. The rule built on it costs nothing and
stays (decision 5).

## Decision

1. **The console may gain views, flows, text and script.** What the person needs
   is product, and it is built as product: each new view in `pages.json` with its
   `/v1` calls and its Ledger rows (`test_every_console_page_maps_to_a_reachable_row`
   unchanged), each new call a named `/v1` route.
2. **What stays, unchanged**: no framework, no npm, no bundler, no minifier, **no
   build step** — the files in `services/console/public/` are the files served;
   no third-party byte; the policy string of ADR 0288 decision 3, with the relay's
   origin following the control domain only (ADR 0299); no `style=` attribute and
   no `.style` in script; **no script-built SVG** — every icon is static markup in
   a `<template>` of `index.html`, cloned (rig 47a); the self-hosted typefaces and
   the shared token block, byte-equal between the two stylesheets; **light only**
   (`test_look.py::test_there_is_no_dark_theme` stays — a dark theme would be one
   more token set under `prefers-color-scheme`, and is a Stage 6 candidate, D2967).
3. **Fixed-route modules.** `app.js` is split into static ES modules, each a
   `ROUTES` entry of `serve.py` and an entry of `test_console_server.py`'s `LISTED`
   and `test_every_script_parses`'s set, widened in the same commit (D2908's
   method): `ui.js` (the components), `nav.js` (the shell, the switchers, the
   breadcrumb), `messages.js` (ADR 0297), and the **DOM-free** `progress.js` (ADR 0296), tested
   in the pinned Node image. Connect's snippets are the server's (decision 7,
   D2991), not a console module. Static `import` only — no dynamic `import()`, no `eval`, no
   `Function`.
4. **Two budgets.** `site.css` ≤ **30,720 B** (unchanged for the site);
   `app.css` ≤ **40,960 B**; each measured alone. The token block they share is
   still held byte-equal.
5. **The drivers move with the DOM.** `ANCHORS` stays a test. A commit that changes
   a label, a button or a selector a driver reads rewrites that driver and re-counts
   `ANCHORS` **in the same commit**, and the driver is rehearsed against a local
   console before the commit is pushed (D2968). Drivers wait by locator only.
6. **One component set** (`ui.js`), each built once: a **copy button** (the value
   written by `navigator.clipboard.writeText`, the label *Copied* for two seconds,
   the same word written once into the page's single `aria-live` region); a **busy
   button** (disabled and relabelled while its promise runs, so a second click
   sends nothing); a code block, which **always** carries a copy button; a toast
   region; a dialog (`<dialog>.showModal()`); tabs; a chip (ADR 0288's
   `STATE_CHIPS`, unchanged: an unknown state never looks `ready`); a skeleton; an
   empty state with its next action; a callout. **Every action button is a busy
   button and every value a customer copies is in a code block.**
7. **Connect's snippets are the server's, and executed before they ship** (D2956,
   D2991). `services/auth-api/app/connection_snippets.py` — rig 39c's
   measurements, served by `GET /v1/projects/{key}/connections` — holds one
   template per client: today psql, Prisma, node-pg and psycopg; Run 6 adds
   Drizzle, Go `pgx` and an `.env` block, each with a line saying which file it
   goes in. The password is always the placeholder in what the server serves; the
   console fills it **only inside the shown-once panel**, in the page.
   `tests/contract/test_connection_snippets.py` runs each new client's text in its
   client's image, pinned by digest, against a TLS Postgres rig with
   `sslmode=verify-full`. A snippet nobody ran does not ship.
8. **The editor's state is at the top** (D2957): a state bar (door, role, state,
   *Disconnect*); the credentials form hidden while connected; the statement above
   the results; results with a sticky header, the row count and the time. ADR
   0285's rules hold — the password read once, the input cleared, never stored.
   `sql.js`'s decisions are not edited except by a test that moves with a clause of
   this ADR.
9. **The look is proved in a browser** as ADR 0288 decision 9 proves the site:
   `tests/external/browser/console_look.py` reads every signed-in console page at
   both widths — no overflow, every request to the page's own origin or the relay,
   the focus ring on `Tab`. No axe, no Lighthouse: third-party test tools the rules
   do not need. **The design itself is the operator's to approve** (Sheet D1)
   before any of decisions 3–8 is built.

## Consequences

- The person's findings become buildable; the walk drivers stop being a reason
  not to change the page, and become a cost each DOM change pays in its own
  commit.
- The console's script grows from six files to ten; every one is listed by
  name in three places, so an unlisted file is a red test, not a silent 404.
- The console stylesheet may grow by 32,318 B over today's 8,642 B; the site's
  limit does not move.
- A dark theme, a framework and a build step remain closed; each would need its
  own ADR.

## Alternatives considered

- **A vendored, hash-pinned build step** (e.g. a bundler run by CI, shipping only
  first-party output) — priced at planning; refused by the operator (D2946 (5)):
  it adds a toolchain whose output a reviewer cannot read as served.
- **A small framework vendored as a file** — a third-party byte in the browser;
  refused by ADR 0288 and by D2946.
- **Keeping decision 8 and styling harder** — every finding but the look needs
  script or text; styling cannot add a progress tracker.

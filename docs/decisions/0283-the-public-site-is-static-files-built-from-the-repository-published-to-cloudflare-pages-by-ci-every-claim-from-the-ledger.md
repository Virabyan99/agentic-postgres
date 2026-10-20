# 0283 — The public site is static files built from the repository, published to Cloudflare Pages by CI, every claim from the Ledger

- **Status:** Accepted
- **Date:** 2026-10-19
- **Session:** 43, Run 1 (`docs/plans/session-43-implementation-plan.md`,
  D2650, D2651, D2653, D2654, D2662, D2663, D2664, D2674, D2676, D2687; rig
  43c; Sheets C0, C1, C3)
- **Affects:** `site/` (new: `site/pages/*.md`, `site/static/`),
  `src/agentic_postgres/site_build.py` and `bin/build-site.py` (new, Run 7),
  `.github/workflows/site.yml` (new, Run 7), the Cloudflare zone
  `agenticpostgresql.com`, the Pages project `agentic-postgres-site` (Sheet C4),
  the GitHub environment `site`, `docs/managed-projects.md`,
  `docs/control-plane.md`, `docs/monitoring.md` (their customer halves move to
  the site). Requirements `SITE-BUILD-001`, `SITE-CLAIM-001`,
  `SITE-DEPLOY-001`, `SITE-LIVE-001`.
- **Scopes:** the rule *"DNS records stay grey-cloud"* (CLAUDE.md §6). That rule
  covers every record that names a host of ours. It does not cover a record
  that Cloudflare Pages creates for the public site (Decision 6).
- **Related:** ADR 0069 (a container's own CSP), ADR 0093 (a `bin/` command
  imports only `agentic_postgres` and `yaml`), ADR 0254 (the Ledger), ADR 0268
  (the public Postgres door, which needs the host's own address), ADR 0274
  (plans), ADR 0280 (the console), D1951 (no email system), D2596 (no
  third-party script, no tracker).

## Context

Session 43 is the first public page this product has (D2591). Its brief asks
for a landing page, hosted customer documentation, a quickstart, pricing and a
way to request an invitation, published to Cloudflare Pages on the apex and
`www`. Three facts shaped the decision when it was planned:

- The zone held a foreign Worker route, `*.agenticpostgresql.com/*` →
  `forgeai-sandbox`, and a proxied wildcard `AAAA * → 100::` that sent every
  unlisted name into it. `www.` answered that Worker's JSON 404.
- The customer documentation was half of three operator pages, with `bin/`
  and `sudo` in it.
- Nothing in the tree renders Markdown, and the pricing table has no price.

## Measured

- **Sheet C0** (2026-10-19, the agent through the Cloudflare API, the
  operator's decision D2650). Zone `5f7560988cc4d6d45c29425f6365ef0e`,
  `active`, Free Website. Exactly one Worker route,
  `d1d4ee079f7343fe8c0ab6abf691ef9e` (`*.agenticpostgresql.com/*` →
  `forgeai-sandbox`), and exactly one AAAA record,
  `eff5ae89635ee0bd496cda5085030871` (`*.agenticpostgresql.com` → `100::`,
  proxied). Both were deleted (200, 200). Read again: no route, no AAAA, 28
  records. Those are 23 A records, all `proxied: false`, plus Sheet C1's three
  MX and two TXT records, all DNS-only. The script `forgeai-sandbox` was read
  present and left alone. `nslookup www.agenticpostgresql.com 1.1.1.1` →
  *Non-existent domain*; `curl https://www.agenticpostgresql.com/` → exit 6.
- **Sheet C1** (the operator, 2026-10-19): Email Routing `ready`; the rule
  `invite@agenticpostgresql.com` → the operator's inbox, enabled; catch-all
  disabled. The zone holds `MX route1/2/3.mx.cloudflare.net`, `TXT v=spf1
  include:_spf.mx.cloudflare.net ~all` and DKIM `cf2024-1._domainkey`, all
  DNS-only. A test mail from another account arrived.
- **Sheet C3** (the operator, 2026-10-19): the GitHub environment `site`
  (branch `main` only, secret `CLOUDFLARE_API_TOKEN` — Account · Cloudflare
  Pages · Edit, this account — and variable `CLOUDFLARE_ACCOUNT_ID`) and the
  environment `pypi` (release tags only, no secret). Read back by `gh api
  …/environments`: both present, `custom_branch_policies: true`.
- **wrangler 4.147.0** (2026-10-02) is the newest release at least 14 days
  old.
- **Rig 43c** (D2676, D2687; 2026-10-19, WSL `~/s43/rigs/43c/`,
  `~/s43/rigs/43c.txt`). A throwaway project `apg-rig-43c` (subdomain
  `apg-rig-43c.pages.dev`) was created and deployed by `npx --yes
  wrangler@4.147.0` in `NODE_RUNTIME_IMAGE`, with a temporary Pages · Edit token
  passed by environment name. Wrangler uploaded `index.html`, `a/index.html`,
  `404.html` and `_headers`. **Reads taken immediately after a deploy are not
  readings**: the first pass saw 522s alternating with 200s. The settled passes
  waited for five consecutive 200s on `/` (about 24 s) and read each path twice:
  - The `Content-Security-Policy` from `_headers` (`/*`) is on `/`, `/a/` and
    `/missing`, both rounds. `X-Rig: a` (the rule `/a/*`) is on `/a/` only, the
    control.
  - `/missing` → **404** with `404.html`'s body (and `cache-control:
    no-store`).
  - `Referrer-Policy: no-referrer` in `_headers` **replaces** Pages' default
    `strict-origin-when-cross-origin` (seen on the first pass), and
    `! Access-Control-Allow-Origin` **detaches** Pages' default
    `access-control-allow-origin: *` (also seen on the first pass).
  - Pages adds `x-content-type-options: nosniff`, `cache-control: public,
    max-age=0, must-revalidate`, an `etag`, `server: cloudflare` and
    Cloudflare's **Network Error Logging** headers: `report-to` (group
    `cf-nel`, endpoint `https://a.nel.cloudflare.com/report/v4?s=…`) and `nel:
    {"report_to":"cf-nel","success_fraction":0.0,"max_age":604800}`. A fourth
    pass with `! Report-To` and `! NEL` in `_headers` **did not detach them**:
    they are added by Cloudflare's edge after the project's headers.
  - No body held a `<script`. The project was deleted and read gone (`8000007`).

## Decision

1. **The site is static files built from the repository.** Its pages are
   `site/pages/**/*.md`; `bin/build-site.py --out DIR [--check]` is the only
   builder, and `--out` inside the repository is refused. `--check` builds
   twice and compares every byte, and two builds of one tree are byte-equal:
   no timestamp, sorted iteration, `\n` endings.
2. **An in-house Markdown subset** (`site_build.py`) and no dependency. The
   subset is front matter (`title`, `ledger: [ids]`, optional `description`),
   ATX headings `#`–`###`, paragraphs, one-level `-` and `1.` lists, fenced
   code, inline code, `**strong**`, `*em*`, links (relative, `#…`,
   `https://`, or `mailto:invite@agenticpostgresql.com`) and pipe tables.
   **Anything else is a build error naming the file and line, raw HTML
   included.** Output is escaped by `html.escape`.
3. **Every claim comes from the Ledger.** Every page names its Ledger rows,
   and the build refuses a row that is not `REACHABLE`. It also refuses any
   `reality_ledger.FORBIDDEN_WORDS` member, `bin/`, `sudo`, `ssh `, `git
   clone` or `--session`. The **pricing page** is generated from `plans.PLANS`
   (each entitlement's value and unit, *"enforced"* or *"shown, not
   enforced"*, the plan's status in words) and `plans.BETA_SENTENCE` verbatim.
   It prints **no price, no currency sign, no "per month"**. The **Ledger page**
   is generated from `reality_ledger.load()`: every row's concept, status and
   `customer_text`. No `/v1/ledger` route is added (D2674).
4. **The customer documentation moves to the site.** `site/pages/docs/` holds
   getting started, connecting, branches, backups, plans and usage, insights
   and monitoring, the CLI and refusals, with commands written `apg <family>
   <verb>`. `docs/managed-projects.md` becomes a pointer, and the customer
   halves of `control-plane.md` and `monitoring.md` shrink to a sentence that
   points there. Their operator halves stay.
5. **CI publishes, and only after the full check** (D2653).
   `.github/workflows/site.yml` runs on `workflow_run` of `contract` completed
   on `main`. Its job runs only if that run concluded `success`, checks out
   **that run's `head_sha`**, builds, and uploads with `npx --yes
   wrangler@4.147.0 pages deploy … --project-name agentic-postgres-site
   --branch main --commit-hash <sha>`. It runs in environment `site` with
   `permissions: contents: read`, and every action is pinned by SHA.
6. **The grey-cloud rule's scope.** *A record that names the production host
   stays DNS-only. A record that Cloudflare Pages creates for the public site
   is proxied and names no host of ours.* The rule exists for the host's ACME
   HTTP-01 and its Postgres door (ADR 0268), which need the host's own address.
   A static site that Cloudflare serves has neither. The apex and `www` are
   attached as Pages custom domains (Sheet C4) and read back `proxied: true`,
   with every A record read still `false`. A guard asserts that the site's
   build and workflow name no host address and no zone name but the apex,
   `www` and `control`.
7. **The headers are the site's own** (`_headers`, `/*`). The CSP is the
   console's (ADR 0280) with `connect-src 'none'` and `img-src 'self'`: the
   site fetches nothing and draws no data URI. The other headers are
   `Referrer-Policy: no-referrer` (it replaces Pages' default, rig 43c),
   `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `!
   Access-Control-Allow-Origin` to detach Pages' `*`. A `404.html` ships, and
   the build refuses a site without one. **Cloudflare's NEL headers are
   recorded, not removable** (D2687). They are not a script and the page makes
   no request because of them; the browser reports failed fetches only
   (`success_fraction` 0.0) to Cloudflare, which already serves every byte.
   Sheet C4 reads them again on the custom domain, where the zone's own setting
   may differ.
8. **Nothing third-party** (D2596): no font, script, stylesheet, image or
   tracker from another host. Traffic is read from Pages' own numbers, and
   Cloudflare Web Analytics only by a later operator decision.
9. **The invitation address is the product's** (D2654):
   `invite@agenticpostgresql.com`, one constant (`INVITATION_ADDRESS`),
   forwarded by Email Routing to the operator's inbox. The product sends no
   mail and stores nothing (D1951 unchanged). The operator's own address
   appears nowhere in the tree.
10. **The zone answers only what the product publishes.** The foreign route and
    the wildcard are gone (Sheet C0). A route someone recreates is a
    divergence row, not a retry.

## Alternatives

- **Pages building from the connected Git repository** on Cloudflare's
  builder: it deploys on every push, before CI's verdict, from a build
  environment this repository does not pin. Rejected (D2653).
- **A static-site generator** (a Markdown library or a framework): a
  dependency tree to lock for a few pages, and a grammar wider than any test.
  Rejected; the subset's whole grammar is one file and its test.
- **The documentation served by the docs container on the control host**: it
  puts the public's first page on the production host's edge and certificate.
  Rejected.
- **A form that collects an email address**: stored personal data with no
  email system to answer it. Rejected; a `mailto:` stores nothing.

## Consequences

- The site is deployed on every green push to `main`, so it can be ahead of
  the deployed release. The Ledger guard keeps it honest about *rows*, not
  about *which commit the host runs*. Its footer names `VERSION`.
- A sentence a stranger reads has one source and one check: the Ledger row it
  names, and a word scan in the build itself.
- Messages to `invite@` are personal data that the operator's inbox holds and
  the product never sees.

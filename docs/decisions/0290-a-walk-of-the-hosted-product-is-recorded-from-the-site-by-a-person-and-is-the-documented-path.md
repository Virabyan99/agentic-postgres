# 0290 — A walk of the hosted product is recorded from the site, by a person, and is the documented path

- **Status:** Accepted
- **Date:** 2026-10-24
- **Session:** 46, Run 1 (`docs/plans/session-46-implementation-plan.md`, D2862,
  D2863, D2866–D2868, D2871, D2883, D2889; Run 1's rows D2891, D2893; rig 46b)
- **Affects:** `src/agentic_postgres/dx_record.py` (a second record path,
  `hosted`, beside the clone's; Run 6), `bin/dx-record.py` (`check` reads either
  path; `digest` refuses a hosted record), `docs/hosted-walk.md` (new: the
  arrangement and the statement), `tests/external/test_session46_walk.py` (new,
  `APG_WALK_RECORD_FILE`), `src/agentic_postgres/evidence_claims.py`
  (`documented_path` → `DX-002`; a new claim `appliance_documented_path` →
  `DX-001`), `tests/acceptance-registry.yaml` (`DX-002`, Run 8).
- **Amends:** **ADR 0207** — §1's *"a person who has never seen this repository
  is not available"* and its Consequences' first bullet (*"`documented_path` …
  is answered by Run 6's walk and by nothing else"*). Everything else in 0207
  stands: its clone record, its four readings and its rules are now the
  **appliance's** documented path, claim `appliance_documented_path`.
- **Related:** ADR 0163 (three statuses), ADR 0195 (three outcomes), ADR 0202
  (an offline claim is declared), ADR 0252 (accounts by invitation), ADR 0260
  (the handoff by hash), ADR 0261 (the Ledger), ADR 0282 (the invitation link),
  ADR 0283 (the site, its digest), ADR 0291 (the console creates a project);
  D478 (a claim closed by its author's hands), D600, D1306, D1935 (the
  documentation walk deferred until after Stage 5).

## Context

`documented_path` has read `DX-001` since Session 12: *a developer who did not
build the primitive completes the documented path without source edits or
undocumented commands*. ADR 0207 made it answerable by a **model session
holding a clone of the release and a task statement**, because a person was not
available, and named a person's walk *"a second and stronger record"*. The
operator deferred the walk until after Stage 5 (D1935); it has been `failed`
since, on the Session 25 record.

Stage 5 changed what the documented path is. A customer of the hosted product
never clones anything: they hold **the site's URL and an invitation link**, and
the path is the site's pages (`site/pages/`), the console and, optionally, the
packaged CLI. On 2026-10-24 the operator answered the question ADR 0207 could
not (D2862): **a person they recruit walks**, from the site and an account
invitation, with no terminal required (ADR 0291 makes creation a browser step).

The clone record cannot describe that walk, and each of its readings says why
(D2867): `followed_by.context` must name a clone (`dx_record.py:316`);
`documents_read` is repository files digested against a checkout
(`:113-138`, `:427-448`); the documented commands are `bin/*.sh`, `./deploy.sh`
and `bin/apg.sh <verb>` forms (`:161-163`); the success criterion is the
workstation path (ADR 0207 §4); and the proof is a host-mode proof run as root.

### Measured (rig 46b, 2026-10-24, at `1b2e3e1`, no network)

- `bin/build-site.py --out DIR` writes **23 files, 16 HTML pages**, every page
  carrying one `<meta name="apg-site-digest">`, equal to `site_build.digest()`
  (`dce4308c…` at `1b2e3e1`). **Control:** a `git archive` of the same commit
  with one letter changed in a prose line of `site/pages/index.md` builds a
  page whose digest differs (`a6939bcb…`). A changed byte inside a link is
  refused by the builder itself (*"links to another origin"*, exit 3).
- **16 routes**: `/`, `/404`, `/docs/` and its ten pages, `/ledger/`,
  `/pricing/`, `/quickstart/`.
- The pages' `<pre><code>` blocks: **24 blocks, 42 distinct `apg` lines, 30
  distinct `apg <noun> <verb>` prefixes**; the other lines in them are `pipx`
  (×3), `uv` (×1) and one connection-string template. **Every `apg` line
  carries placeholders** — `KEY`, `NAME`, `ADMIN`, `OPERATION`, `./app-password`,
  a sample time — so a person's honest command never equals a documented line
  byte for byte (D2893).
- **The digest's inputs are wider than the plan named** (D2891):
  `site_build.digest_inputs()` (`site_build.py:677-689`) is every file under
  `site/`, the five shared assets under `services/console/public/` (four font
  files and `favicon.svg`, ADR 0288), `services/auth-api/app/plans.py` (the
  service's table; `src/agentic_postgres/plans.py` only loads it), the Ledger,
  `VERSION` and `site_build.py`.

## Decision

1. **A record has a `path`.** Absent, it is `clone` and is read exactly as
   today — no field, check or message of ADR 0207's moves. `"hosted"` selects
   the second path below. Any other value is a shape problem.
2. **The hosted record's fields** (all required unless marked):

   | Member | What it answers |
   |---|---|
   | `path` | `"hosted"` |
   | `followed_by` | ADR 0207's four strings; `kind` **must be `person`**; `context` must name **"site"**, **"invitation"** and **"statement"** |
   | `started_at`, `completed_at` | ISO 8601 UTC: the link opened, the walk ended |
   | `release` | The release the site's banner names (`Release 1.24.0`), equal to `VERSION` at the reading's checkout |
   | `site_commit` | 40 hex: the commit whose build the person read |
   | `site_digest` | 64 hex: the page's `apg-site-digest` meta, copied from a page the person had open |
   | `documents_read` | A list of site routes, each one the build produces |
   | `commands_run` | Every command typed in a terminal, in order — empty when the walk was browser-only |
   | `files_edited` | Must be empty: a hosted walk edits no product file |
   | `goals` | The statement's goals, in its order: `{goal, reached, at, note}` — `at` ISO or null; `note` required when `reached` is false |
   | `timeline` | `{link_opened, account_created, factor_enrolled, organization_created, creation_accepted, connection_string}`, each ISO or **null meaning not noted**, never a zero (D2866, D600) |
   | `undocumented_steps` | Every step a page did not give, in the person's words |
   | `reached_success_criterion` | Must equal `goals[0].reached` (the working connection string) |
   | `blocked_by` | ADR 0207's rule, unchanged: required when the criterion was not reached, refused when it was |
   | `transcribed_by` | `{kind: "agent", identity}`: who typed the person's notes into JSON |
   | `confirmed_by_walker_at` | ISO 8601 UTC, not before `completed_at`: when the person read the JSON and said it is theirs |

3. **The readings, each total over a malformed record** (`dx_record`'s rule):
   - **the site** — `site_digest` equals `site_build.digest()` at the reading's
     checkout, else *the site moved after the walk* (the clone path's
     `stale_documents`, one level up); the live proof also holds `site_commit`
     an ancestor of, or equal to, the checkout's `HEAD`;
   - **the routes** — every `documents_read` entry is a route the build
     produces (a route the person typed wrongly is reported, never dropped);
   - **the commands** — an `apg` command matches when **one documented line has
     its `apg <noun> <verb>` and every flag it used** (values free; rig 46b's
     placeholders); any other command matches a documented code line after
     whitespace is normalised; anything else is unnamed. A third-party client
     the person used with their connection string is a goal's `note`, not a
     command: the record holds no connection string;
   - **no secret** — the record is refused if any string in it holds a
     connection string with a password, an invitation link (`/accept#`), an
     `otpauth://` URI or a 43-character base64url run (a handoff token's
     shape). **The transcriber refuses them first; the reader refuses them
     again** (D2868: the person's notes are carried, never their secrets);
   - **the hands** — `followed_by.kind` is `person`, `transcribed_by.kind` is
     `agent`, and `confirmed_by_walker_at` is present and not before
     `completed_at`.
4. **The claim** (ADR 0163): `documented_path` **passes** on a hosted record
   from a qualifying walk whose readings are clean, whose `undocumented_steps`
   is empty and whose criterion was reached; it **fails** on any unnamed
   command, edited file or undocumented step, and that is never softened; it is
   **`not_run`** when no record was declared or the record does not describe a
   qualifying walk (a `kind` that is not `person`, no confirmation). A goal after
   the first that was not reached, with its `note`, is reported and does not by
   itself fail the claim — *the person stopped* is not *a page was wrong*; a
   page that was wrong is an undocumented step.
5. **`documented_path` moves to `DX-002`** (external mode,
   `APG_WALK_RECORD_FILE`, `tests/external/test_session46_walk.py`). Its node
   ids change and its `CLAIM_INTRODUCED_IN` row does not: the claim keeps its
   name and its question — *did somebody who did not build this get through the
   documented path* — for the product customers now get. **`DX-001` keeps its
   proof under a new claim, `appliance_documented_path`** (host mode,
   `APG_DX_RECORD_FILE`), `failed` on the Session 25 record until a person walks
   the clone (D1935) — said so in the Ledger, never hidden by the rename.
6. **Who walks, and what they hold** (D2868, D2889). A person who did not build
   Stage 5, holding **only** the site's URL, `docs/hosted-walk.md`'s statement
   (between its markers) and an account invitation link. **The operator mints
   the invitation** (`apg org invite --account`, as the registry administrator,
   whose factor is the operator's phone) and **sends link and statement by
   their own email**; the agent never sees the link. The person writes their
   own notes in the statement's plain-text form; the agent transcribes them
   **verbatim**; the person reads the JSON and confirms; only then does it
   reach the gate. **Neither the operator, the agent nor a driver walks for
   this claim** — ADR 0207's Consequences, kept.
7. **The site is frozen for the walk** (D2883). From the bump's push until
   `confirmed_by_walker_at`, no commit changes a file
   `site_build.digest_inputs()` returns — **that function is the list**, never a
   typed copy of it (D2891). A repair after the walk is `site/`- or
   `docs/`-only, and a second walker's record names its own `site_commit`.
8. **No time bound** (D2866). Creation alone takes 1,375.9–1,708.4 s on this
   host (the envelope, Sessions 42–45); the criterion is *reached*, never
   *within twenty minutes*. The record's `timeline` is what the envelope and the
   Stage 6 report read.
9. **The journey is not a walk** (D2871). The agent's driver
   (`tests/external/browser/journey_walk.py`) walks the same pages in Chromium
   for `journey_live`, starting from a membership invitation the probe owner
   mints; it moves `JRN-001`, never `documented_path`.

## Alternatives rejected

- **Reuse the clone record with a different `context`.** Every reading would
  be answering a question about files no hosted customer touches; a
  `documents_read` of repository paths would digest pages the person never saw.
- **Count the agent's journey as the walk.** ADR 0207 §1's residual is exactly
  this: an agent reads faster and skips less, and the author's driver shares
  the author's beliefs (D673). The operator chose a person.
- **Match commands byte for byte.** Rig 46b: every documented `apg` line has a
  placeholder, so every honest command would read as undocumented — a reader
  wrong in the alarming direction is still wrong.
- **Rename `documented_path` to the clone and add a new claim for the hosted
  walk.** The claim's question is the product's; the product is now hosted.
  The appliance's walk keeps a claim of its own so its failure stays visible.

## Consequences

- `documented_path` becomes answerable by a person for the first time, and is
  answered by nothing else; `appliance_documented_path` stays `failed` until
  somebody walks the clone, and the Ledger says which walk each claim reads.
- The site's digest inputs are frozen across the sitting; a docs-page repair
  between the bump and the walk is impossible by rule, not by care.
- The walk record carries a person's notes through the agent's hands, which is
  `THR-WALK-RECORD` (threat item 30): transcribed verbatim, confirmed, holding
  no secret.
- `dx-record digest` has nothing to compute for a hosted record (the digest is
  the page's) and says so with exit 2; `check` reads either path.

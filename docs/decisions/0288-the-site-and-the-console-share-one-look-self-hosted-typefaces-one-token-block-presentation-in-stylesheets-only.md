# 0288 — The site and the console share one look: self-hosted typefaces, one token block, presentation in stylesheets only

- **Status:** Accepted
- **Date:** 2026-10-23
- **Session:** 45, Run 1 (`docs/plans/session-45-implementation-plan.md`,
  D2810, D2812–D2831, D2843, D2844, D2847, D2848; rigs 45a, 45b)
- **Affects:** `services/console/public/fonts/` (new: two `woff2`, two OFL
  licences), `services/console/public/favicon.svg` (new),
  `services/console/serve.py` (`ROUTES`, content types, `DIRECTIVES`),
  `services/console/public/{index,accept}.html`, `app.css`, `app.js` (class
  names and wrappers through `h` only), `site/static/site.css`,
  `site/templates/base.html`, `src/agentic_postgres/site_build.py`
  (`SHARED_ASSETS`, `CONTENT_SECURITY_POLICY`, `NAVIGATION`, `DOCS_GROUPS`,
  `CONTAINERS`, the generated blocks), `site/pages/**`. Tests moved:
  `tests/contract/test_site.py` (`POLICY`, `test_no_third_party_asset`,
  `test_the_site_names_no_host_address`),
  `tests/contract/test_repository_contract.py` (`test_no_tracked_file_uses_crlf`),
  `.gitattributes` (`*.woff2 binary`),
  `tests/contract/test_console_server.py` (`ADR_0280_POLICY`, `POLICY`,
  `LISTED`, `test_the_image_bakes_only_its_own_files`). New:
  `tests/contract/test_look.py`, `tests/contract/test_site_look.py`,
  `tests/contract/test_console_look.py`, `tests/external/browser/site_look.py`,
  `tests/external/test_session45_look.py`. Requirements `UI-TOKENS-001`,
  `UI-FONTS-001`, `UI-SITE-001`, `UI-CONSOLE-001`, `UI-LIVE-001` (Run 8);
  `SITE-DEPLOY-001`, `SITE-BUILD-001`, `CON-SERVE-001` made stricter.
- **Amends:** **ADR 0280** decision 4 — the policy constant's `font-src 'none'`
  becomes `font-src 'self'`, and the fixed route table gains exactly five paths
  (four under `/console/fonts/`, `/console/favicon.svg`). **ADR 0285** decision
  4 — the deployed string it prints, by the same one directive. **ADR 0283**
  decision 7 — the site's policy, by the same one directive — and decision 2,
  whose Markdown subset gains a closed set of containers and generated blocks
  (decision 6 below); raw HTML stays refused. Decision 8 (*"no font … from
  another host"*) is unchanged in substance: the fonts are files of this
  repository.
- **Related:** ADR 0002 (derive once), ADR 0069 (the documentation page has
  served `font-src 'self'` since Session 5, `services/docs/serve.py`), ADR 0195 (an unknown state never
  looks known), ADR 0261 (the Ledger), D2596 (no third-party byte), the
  operator's design brief `docs/design/session-45/design-brief.md`.

## Context

The operator's design brief (*"the honest instrument"*) restyles the public site
and the console inside the current rules: no framework, no bundler, no npm, no
script on the site, no byte from another origin, appearance only. Two of its
requirements meet the tree's guards head on:

- **Self-hosted typefaces.** Both policies say `font-src 'none'` (site
  `site_build.py:62-74`, console `serve.py:85-95`), and a font from the
  repository meets **six** pins, not the two D2810 named (D2813): (a)
  `test_site.py`'s `POLICY`; (b) `test_no_third_party_asset`'s `"url(" not in
  site.css` — `@font-face` needs `url()`; (c) `test_console_server.py`'s
  `ADR_0280_POLICY` and `POLICY` (and `test_the_policy_admits_the_relay_alone`,
  which compares them); (d) `LISTED` — a font is a route; (e)
  `test_the_image_bakes_only_its_own_files` — `public/`'s names must equal the
  routed files', and a `fonts/` directory is a name; (f)
  `test_the_site_names_no_host_address` reads every file under `site/` as UTF-8,
  and a `woff2` there raises. The brief's *"contract tests must pass
  unchanged"* cannot hold for (a)–(e); it can for (f) if the fonts live
  elsewhere.
- **Presentation without inline style.** Both policies have `style-src 'self'`
  with no `'unsafe-inline'`, so a `style=` attribute is refused; the site's
  `img-src 'self'` has no `data:`; the console's element helper `h` cannot make
  SVG (`app.js:52-67`). The brief's logo, chips, bar and hatched restore window
  must be drawn some other way.

Four of the brief's questions were the operator's and were answered at planning
(D2812): pricing keeps its two per-plan tables (D2818); the console gets hooks
only (D2828); the *What exists* filter is CSS-only (D2819); D2805 is ADR 0289's.

## Measured

**Rig 45a — the typefaces** (2026-10-23, WSL `~/s45/rigs/45a/rig.txt`). The
inputs were fetched at **one `google/fonts` commit,
`e7db6ca603fd4862010383ff17ffd6cc4ffac1c0`** (the default branch `main`'s head,
committed 2026-10-23T02:02:18Z), each HTTP 200, each git blob id equal to the
one read at planning:

| Input (at the pinned commit) | sha256 | Bytes |
|---|---|---|
| `ofl/schibstedgrotesk/SchibstedGrotesk[wght].ttf` | `6ceeadf6be8e1fd7687011c7fa38ed0edd1abe967a0b73d97caec183552e823d` | 176,068 |
| `ofl/schibstedgrotesk/OFL.txt` | `3b4f3063b6ac7c1e403e2c4a5e8ef3a58190ff83ed7b15af66511858699139ce` | 4,406 |
| `ofl/jetbrainsmono/JetBrainsMono[wght].ttf` | `48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda` | 187,208 |
| `ofl/jetbrainsmono/OFL.txt` | `b2fe5e8987594e9ffd1d2ca52a2f5d73eb8335243893c5d6254b5ad69269591d` | 4,399 |

Both `METADATA.pb` say `license: "OFL"`; the axes are `wght` 400–900 (Schibsted
Grotesk) and 100–800 (JetBrains Mono). The tools ran in the pinned
`PYTHON_RUNTIME_IMAGE` with `fonttools==4.67.0 brotli==1.2.1` installed in the
throwaway container only — no lock moved, nothing the product runs. Google's
`latin` range was read from its own CSS API (`fonts.googleapis.com/css2`, a
Chrome User-Agent, the `latin` block):
`U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304,
U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215,
U+FEFF, U+FFFD`. The recipe:

```
export SOURCE_DATE_EPOCH=1792720938   # the pinned commit's time (D2844)
fonttools varLib.instancer 'JetBrainsMono[wght].ttf' wght=400:500 -o JetBrainsMono-400-500.ttf
pyftsubset 'SchibstedGrotesk[wght].ttf' --unicodes=<latin> --layout-features='*' --flavor=woff2 --output-file=schibsted-grotesk.woff2
pyftsubset JetBrainsMono-400-500.ttf    --unicodes=<latin> --layout-features='*' --flavor=woff2 --output-file=jetbrains-mono.woff2
```

JetBrains Mono's axis was limited to 400–500 because that subset is **28.1%**
smaller than the whole axis (29,084 against 40,460 B; the plan's rule was
*more than 10%*). The outputs — the files committed in Run 3:

| Output (`services/console/public/fonts/`) | sha256 | Bytes |
|---|---|---|
| `schibsted-grotesk.woff2` | `b29bc789f8a864ac7e25e71e8b997056fa0bee0fe8799ff56923dc28a2671d06` | 49,112 |
| `jetbrains-mono.woff2` | `61a4199a67c39cf39239c0b5b3a89f01f53e244c4e4d60d77ae85f557aa16a5b` | 29,232 |
| `OFL-schibsted-grotesk.txt` | `3b4f3063…` (the input, unchanged) | 4,406 |
| `OFL-jetbrains-mono.txt` | `b2fe5e89…` (the input, unchanged) | 4,399 |

The two typefaces are **78,344 B**. Read back with fontTools: Schibsted Grotesk
`woff2`, 318 glyphs, 225 code points, `fvar` `wght` 400/400/900; JetBrains Mono
`woff2`, 413 glyphs, 228 code points, `fvar` `wght` 400/400/500; `gvar`, `GSUB`
and `GPOS` present in both. Neither misses a glyph of A–Z, a–z, 0–9 and
`£€—–’“”…`, nor any non-ASCII character the site, the console, the Ledger or
the plan table holds today (`£§·—…€`). **Controls:** the Schibsted subset run
twice is byte-equal; Lexend (`ofl/lexend/Lexend[wght].ttf`, OFL) through the
same command hashes `b9441676…`, equal to neither — the pin reads the file, not
its name. **D2844:** `varLib.instancer` stamps `head.modified` with the time of
saving, so two unpinned runs differed in `head` and nowhere else; with
`SOURCE_DATE_EPOCH` set to the upstream commit's time two fresh containers
produced byte-equal files, and that build is the one committed.

**Rig 45b — the browser** (2026-10-23, WSL `~/s45/rigs/45b/rig.txt`; the pinned
Playwright image, Chromium 153.0.8010.12; a server in the rig sending the
site's policy with only `font-src` varied; violations read by a listener
installed outside the page's policy and by the console):

- **`font-src 'self'`** with `@font-face` to same-origin `woff2` served
  `font/woff2` + `nosniff`: both faces `loaded`, no violation, every request
  same-origin. **Control** `font-src 'none'`: both `error`, two `font-src`
  violations. Playwright's `request` event lists the blocked fonts too: it
  records the attempt, which is the stricter reading for the look walk.
- **An SVG by presentation attributes** (`fill`, `stroke`, `rx`, a `<pattern>`,
  `fill="url(#…)"`) under `style-src 'self'`: no violation. **Control:** one
  `style="fill:red"` — a `style-src-attr` violation, and the computed fill
  unchanged.
- **The filter** `main:has(#status-planned:checked) tbody
  tr:not(:has(.chip-planned)) { display: none }`, the class on a chip inside the
  cell: *Planned* shows only the planned rows, *In the beta* only the beta row;
  **control** *All* shows every row.
- **At 390 × 844:** a closed `<details>` hides its list and an open one shows it;
  `scrollWidth` 390 against `innerWidth` 390, and 600 against 390 with a 600 px
  element (the control). **Focus:** `Tab` lands on `summary` and then a link,
  each `outline: solid 2px rgb(31, 79, 163)` and `:focus-visible`; a **mouse**
  click on the link focuses it with `:focus-visible` false and no outline — the
  ring is the keyboard's, so the walk presses `Tab`.

## Decision

1. **Two typefaces, made once, pinned.** Schibsted Grotesk (variable, `wght`
   400–900) for all text and JetBrains Mono (variable, `wght` 400–500) for
   commands, code, connection strings, role names and refusal words, both
   SIL OFL 1.1, made by the recipe above from the pinned commit. **The four
   output hashes are pinned by `test_look.py::test_the_fonts_are_the_recorded_files`**,
   each licence beside its font (`::test_each_font_has_its_licence`). A new
   upstream version is a deliberate act: rig 45a again, this table, the pins.
   Threat item 27 (`THR-UI-FONT`) is the risk.
2. **One copy of every shared asset, in the console's tree** (D2814):
   `services/console/public/fonts/` (the four files) and
   `services/console/public/favicon.svg`. The console's image bakes only its
   build context, so the bytes live there; **the site builder copies them**
   (`site_build.SHARED_ASSETS`, the five relative paths listed — never a glob)
   to `/fonts/…` and `/favicon.svg` in the build and adds them to
   `digest_inputs()`. The console routes them at `/console/fonts/…` and
   `/console/favicon.svg` as `font/woff2`, `text/plain; charset=utf-8` and
   `image/svg+xml`. `test_site.py::test_the_build_carries_the_shared_assets`
   holds the build's copies byte-equal to the console's. Nothing binary is
   under `site/`, so pin (f) is not moved.
3. **`font-src 'self'` on both policies, and nothing else in either string
   moves.** The site:

   ```
   default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self';
   connect-src 'none'; font-src 'self'; base-uri 'none'; form-action 'none';
   frame-ancestors 'none'
   ```

   The console, as deployed (ADR 0285's function of the relay origin):

   ```
   default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
   connect-src 'self' wss://sql.agenticpostgresql.com; font-src 'self';
   base-uri 'none'; form-action 'none'; frame-ancestors 'none'
   ```

   `'self'` names the serving origin and no other host; there is still no
   `'unsafe-inline'` anywhere.
4. **The pins move exactly so, each to an equal or stricter form** (D2813;
   (g) D2847; (h) D2848):
   - (a) `test_site.py` `POLICY` — `font-src 'self'`, the rest of the string
     byte-equal.
   - (b) `test_no_third_party_asset` — *every `url(…)` in `site.css` is one of
     the `/fonts/` paths the build carries, and `@import` is refused*: an
     allowlist of the measured set, never a subset check (CLAUDE.md §6). The
     same rule for `app.css` and `/console/fonts/` is
     `test_look.py::test_every_url_is_one_of_the_fonts`.
   - (c) `test_console_server.py` `ADR_0280_POLICY` and `POLICY` —
     `font-src 'self'` in both; `test_the_policy_admits_the_relay_alone` is
     untouched and still finds `connect-src` the only directive that differs.
   - (d) `LISTED` — gains exactly the five routed paths.
   - (e) `test_the_image_bakes_only_its_own_files` — walks `public/`
     recursively and compares the **relative paths** of every file with the
     routed files' (its two `COPY` lines unchanged): stricter than today, since
     a stray file in a subdirectory now fails it too.
   - (f) not moved (decision 2).
   - **(g), found in Run 3 and decided by the operator (D2847):**
     `test_the_site_names_no_host_address` ALSO decodes every file of the
     BUILD as UTF-8 (`test_site.py:125`), not only the files under `site/`, so
     the build's two `woff2` raised there. It now reads every text file of the
     build as before (`.html`, `.css`, `.txt`, `.svg`, `_headers`) and asserts
     that the files it does not decode are **exactly** the two typefaces in
     `SHARED_ASSETS` (whose bytes `test_look.py` pins): stricter than before,
     since an unexpected binary in the build now fails it. This ADR's first
     reading said no seventh test moves; that was wrong, and is recorded here
     rather than corrected silently.
   - **(h), found in Run 3 and decided by the operator (D2848):**
     `test_repository_contract.py::test_no_tracked_file_uses_crlf` reads every
     TRACKED file's bytes and refuses any `\r`; compressed `woff2` data holds
     0x0D by chance. It now skips exactly the two typefaces by path
     (`BINARY_FILES`), asserts they exist and are the only files skipped, and
     scans every other tracked file as before — a new binary still meets it
     (battery: a tracked stray file holding `\r` FAILED it). `.gitattributes`
     gains `*.woff2 binary`, so git never normalises or diffs a font as text.
     Every other whole-tree scan in the suite filters by suffix or skips an
     undecodable file (swept at the same stop).

   Any other test that would have to move is §9's stop, never an edit.
   `test_the_fonts_are_served_as_fonts` (each font route → 200, `font/woff2`,
   the policy, the committed bytes) is new.
5. **One token block, light only, two files.** The brief's colours, status
   palette, dark-surface values, radii and spacing steps are custom properties
   between `/* tokens: begin */` and `/* tokens: end */` at the top of
   `site/static/site.css` and of `services/console/public/app.css`;
   `test_look.py::test_the_two_stylesheets_share_one_token_block` holds the two
   blocks byte-equal (the builder has no include, so duplication is guarded,
   not avoided). The `@font-face` rules follow the block, since their URLs are
   the one thing that differs. **Both files are `color-scheme: light`** and
   their dark blocks are removed (D2825): a dark theme the brief did not design
   would be a second, unreviewed palette (`::test_there_is_no_dark_theme`).
   Every text pair the stylesheets use meets **4.5:1** by the WCAG formula
   computed from the parsed tokens (`::test_every_text_pair_meets_4_5`, the
   pairs listed in the test); every interactive selector declares
   `:focus-visible` with `outline: 2px solid var(--focus)`
   (`::test_every_interactive_element_shows_focus`); the two stylesheets
   together stay **≤ 30,720 B** (`::test_the_stylesheets_fit_the_budget`) —
   the fonts are measured in the envelope, never budgeted.
6. **The site's layout comes from a closed vocabulary, and its numbers from
   the builder** (D2821, ADR 0283 decision 2 amended). Two extensions to the
   Markdown subset, both closed sets: **containers** — `::: <name>` opens and
   `:::` closes a `<div class="<name>">` around ordinary Markdown, the name
   from `CONTAINERS` (`hero`, `lead`, `actions`, `features`, `feature`,
   `steps`, `band`, `band-dark`, `note`, `warning`, `doors`), one level of
   nesting, an unknown name a `SiteError`; and **generated blocks** — a line
   that is exactly `@restore-example`, `@ledger-summary`, `@ledger-examples`,
   `@plan-summary` or `@docs-index`, or `@chips <row> …` naming only rows in
   the page's own `ledger:` list, replaced by builder HTML from the Ledger,
   `plans.PLANS` or `DOCS_GROUPS`. `@pricing` and `@ledger` may now be followed
   by Markdown, but stay the body's first line. **All prose stays Markdown**, so
   `check_page` still reads every sentence a person wrote; raw HTML is still
   refused. Every chip, count, bar and example is generated (the brief's rule,
   ADR 0283 decision 3):
   - **Chips** carry `STATUS_WORDS` unchanged; sentence case is
     `::first-letter` in CSS (D2816). `available` takes the beta colours, and
     every status in `reality_ledger.STATUSES` has a chip class.
   - **The stacked bar** is an inline SVG whose `<rect>`s carry `x`/`width`
     attributes, with `role="img"` and an `aria-label` of the counts; a segment
     and a legend entry exist only for a status with at least one row, and the
     counts sum to the Ledger's total (D2817).
   - **The *What exists* filter** is CSS only (D2819): one radio per status
     present plus *All* (checked), each label carrying its own count; the
     status class sits on a chip `<span>` inside the *Today* cell, never on
     `<tr>`/`<td>`, so the literal `<tr><td>` reads of `test_site.py` see what
     they saw; without `:has()` every row shows. There is no dynamic *"Showing
     N"*: the line reads *"43 concepts"*.
   - **`@ledger-examples`** takes, per status present, the first row in YAML
     order whose concept and text hold no forbidden word (D2843), only on the
     home page.
   - **`@restore-example`** is a static block labelled *Example project*
     (`shop-backend`, a `ready` chip, the two doors, a hatched window from Mon
     19 Oct 02:00 to Fri 23 Oct 08:40 UTC and a fixed marker) whose command is
     `site/pages/docs/branches.md`'s line with the marker's time; a guard holds
     the command, minus its values, equal to that line (D2831).
   - **Pricing keeps two tables** (D2818): Free's section has the accent wash
     and a 4 px accent top border, Premium's a 4 px `--border-control` one; the
     plan's chip is the existing `PLAN_STATUS_WORDS` paragraph styled as a
     caption; the enforcement marker is a CSS `::before` on the fourth cell by a
     class on that `<td>`. **The template's chrome holds no `<p>`**, so the
     pricing page's first `<p>` is still `plans.BETA_SENTENCE` (the live proof's
     read).
   - **Navigation** (D2823): the four items Quickstart, Docs, Pricing, What
     exists — the wordmark links home — then *Console* and the invitation
     button; `aria-current="page"` on the item whose route is a prefix of the
     page's (`/` never a prefix); the same items in a `<details>` menu below
     900 px with counts from the builder. **`DOCS_GROUPS`** (D2822) puts every
     docs page in exactly one of the brief's four groups — the SQL editor in
     *Use a project* after *Connecting* — and previous/next follow it. Heading
     ids are de-duplicated (`-2`, `-3`), and *On this page* lists every `h2`.
   - The brief's copy rule replaces `A · B · C` strings (D2824): *"Agentic
     Postgres {VERSION}, beta"*, *"{title}, Agentic Postgres"*.
7. **Every SVG uses presentation attributes only, and no page carries
   `style=`** (D2820). A guard reads every built page and both console HTML
   files and refuses the attribute. The console's logo is static markup in
   `index.html` and `accept.html`, outside `#main`, never built by `app.js`; the
   favicon is a file.
8. **The console gets hooks, not features** (D2828, D2829, the operator's
   choice). Class names and wrapper elements through `h`, the current tab marked
   `aria-current="page"`, the shown-once panel's amber border, refusals in the
   warning callout, right-aligned numeric columns (`table()` takes an optional
   set of keys), forms, the sign-in panel. **Project state is a chip from
   `STATE_CHIPS`** (D2827), which maps the nine `control_states.STATES` to the
   brief's colours and **any other value to `state-unknown`** — the dark *not
   metered* chip, whose colours a guard holds different from `state-ready`'s:
   a state the console cannot name never looks like `ready` (ADR 0195). The
   text inside every chip is the state word as today. **`sql.js`, `pg.js`,
   `scram.js` and `api.js` are not edited**; the editor is styled by structural
   selectors; no `code.secret`, `role=status`, textarea, heading, label or
   button text is added or changed, so the two walk drivers read what they read
   (`test_console_look.py::test_the_drivers_anchors_are_unchanged`). Not built,
   each a Stage 6 candidate: the restore-window bar from data, relative ages,
   the refusal link, operation-id rows, the confirm button disabled until the
   name matches, a phone-width console menu.
9. **The look is proved in a browser** (D2830): `tests/external/browser/site_look.py`
   in the pinned Playwright image reads every site route and the console's
   sign-in at 390 × 844 and 1280 × 800 — `scrollWidth ≤ innerWidth`, every
   attempted request's origin the page's own, both families `loaded`, a `Tab`
   landing on the 2 px `rgb(31, 79, 163)` ring — into one 0600 record pinned
   to the deployed commit and the site's digest (`ui_look_live`). **The side by
   side comparison with the prototypes is the operator's**, recorded in the
   sitting's notes, never a test.

## Consequences

- Both origins now ask for exactly two more kinds of file — fonts and an icon —
  and from themselves only; the policies still name no host but the relay.
- A changed font byte, a token edited in one file and not the other, a pair
  below 4.5:1, a dark block, a `url()` to anywhere but the fonts, a `style=`
  attribute, an unknown container or a typed count each fail offline.
- The site's pages gain layout without gaining HTML: a reviewer reads Markdown
  and a dozen words of vocabulary, and the claim check still reads every
  sentence.
- **The look is the stylesheets'**: the console's script gained no route, no
  request and no text, and the walk drivers' anchors are a test.
- The fonts are third-party code reaching a browser's parser; the pin proves
  which bytes, not that they are benign (threat item 27).
- What it forecloses for now: copy buttons, the hero slider, a combined pricing
  table, a dynamic row count, docs search — each needs a script or a new flow,
  and each is named in Session 45's §10 as a Stage 6 candidate.

## Alternatives considered

- **Google Fonts' CDN** — refused by D2596 and by the brief; it would also add
  a host to both policies.
- **The system font stack, as today** — the brief chose the typefaces; the
  rules allow them once they are our own files.
- **Static weights instead of the variable fonts** — four or five files per
  family and the brief's 650/750 weights mapped down; the variable files are
  two files and 78 KB together.
- **The fonts under `site/static/`, copied into the console's image** — the
  image bakes only its own build context, and `test_site.py` reads `site/` as
  text; one copy where the constraint is, a copy step where there is none.
- **An include in the builder for the shared tokens** — a new mechanism for one
  block; duplication with a byte-equality test is smaller and as safe.
- **`'unsafe-inline'` for styles, or `data:` images on the site** — each would
  weaken a policy to save a stylesheet rule; presentation attributes and a
  favicon file do the same work (rig 45b).
- **One pricing table, a dynamic filter count, the console's extra patterns** —
  the operator's choices at planning (D2812): each would move a pinned shape or
  add logic to a visual pass.

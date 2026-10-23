# Planning prompt: Session 45 visual pass (Option 1)

You are planning the visual pass for agenticpostgresql.com (the site) and control.agenticpostgresql.com/console/ (the console). This is Option 1 from the earlier analysis: a visual pass inside the current rules. Produce a Markdown plan first; do not implement until the plan is approved.

## What you are given

1. **This brief.** It is the design specification. Where it gives an exact value (hex, px, weight), use that value.
2. **Five prototype files** from a design tool: `Main.dc.html` (home), `Docs.dc.html` (a docs page, Connecting), `Pricing.dc.html`, `Ledger.dc.html` (What exists), `Mobile.dc.html` (home at 390 px wide with the menu).

The prototype files are a **visual reference, not code to copy.** They were written for a prototyping runtime, and they break several project rules on purpose. When reading them:

- `<x-dc>`, `<helmet>`, `<sc-for>`, `<sc-if>`, `{{...}}` holes and the `<script type="text/x-dc">` block are the prototype runtime's notation. They mean "repeat this", "show this when", and "this value comes from data". Ignore the mechanism; take the layout, spacing, colours and type.
- The Google Fonts `<link>` must not be used. Fonts are self-hosted (see Typography).
- All styles are inline in the prototype. In the product they become classes in the one CSS file.
- The interactive parts (draggable restore window, copy buttons, step switcher, ledger filter, mobile menu toggle) use script. In the product they become static or CSS-only versions (see "Interactive parts without JavaScript").
- Sample values are examples: the project name `shop-backend`, the backup times Mon 19 Oct 02:00 to Fri 23 Oct 08:40 UTC, and "read 3 minutes ago". They must be labelled as an example on the site, or replaced.

## Hard constraints (verify each against the repo before planning)

Restate each with its source (decision, ADR, test file) in the plan, and flag anything below that conflicts with the repo.

- **Site pipeline:** pages stay as Markdown in `site/pages/`, built by the project's own builder into static HTML through one template, published to Cloudflare Pages by CI (ADR 0283). The builder's Reality Ledger claim check must keep passing; no page may claim more than the ledger says.
- **No third-party anything** (D2596): no external scripts, fonts, stylesheets, images, trackers or CDNs. Every byte served comes from the repo. The CSP stays strict; if it needs `font-src 'self'` added, say so explicitly.
- **Console code rules:** plain hand-written JavaScript, the existing element-building helper, no `innerHTML` or any HTML-from-string, no npm, no build step. Contract tests must pass unchanged. If a test would need to change, stop and list it as an open question instead.
- **No behaviour changes.** This pass changes appearance only: CSS, fonts, the logo, the site template, and class names or wrapper elements in the console where the CSS needs a hook. No new features, endpoints, copy claims or flows.
- **Small and readable.** One CSS file for the site and one for the console (they may share a tokens section by duplication or by an included file if the builder already supports that). Target a combined total under about 30 KB uncompressed, excluding fonts.
- Existing test-preservation rules apply: no test may be deleted or weakened.

## The design idea: "the honest instrument"

The product's strongest trait is that it never overclaims: the What exists ledger, one-word refusals, readings that name their source and age, nothing shown as zero when it was not read. The design should look like a precise measuring instrument, not a marketing page.

Principles:

1. **Status is information, shown the same way everywhere.** Every feature mention carries its ledger status as a chip, with one fixed colour per status across the site and console.
2. **Show the real thing instead of decoration.** No illustrations, gradients, glows, stock imagery or identical card grids. The hero shows a restore window; sections show real commands and real tables.
3. **One bold element per page; everything else quiet.** On the home page, the hero restore window is that element.
4. **Navigation is predictable.** The same four main items on every page, the current page marked, Console set apart from them, and one primary action: Request an invitation.
5. **Limits sit next to the feature,** not in footnotes (for example "A branch is not backed up" in the Branches section).

Avoid these on purpose: all-caps labels, tracked-out eyebrow text above headings, `→` arrows appended to links, `A · B · C` meta strings (write "Agentic Postgres 1.22.0, beta" instead of "1.22.0 · beta"), drop shadows on panels, gradient fills, emoji, and coloured left-border callouts.

## Design tokens

Define these as CSS custom properties at the top of each CSS file. Names are suggestions.

### Colour

| Token | Hex | Use |
|---|---|---|
| `--ground` | `#F4F6F5` | Page background |
| `--surface` | `#FFFFFF` | Panels, tables, inputs, alternating section bands |
| `--surface-sunk` | `#F8FAF9` | Table header rows |
| `--surface-hover` | `#E8EDEB` | Sidebar hover, inline code background, count pills |
| `--ink` | `#142027` | Main text, headings, dark bands, dark code blocks |
| `--ink-body` | `#26333B` | Long-form docs body text |
| `--text-2` | `#3D4A52` | Secondary paragraphs, lead text |
| `--text-3` | `#55626B` | Captions, metadata, table header text |
| `--rule` | `#D3DBD8` | Section borders, header bottom border, footer rule |
| `--rule-soft` | `#E1E7E5` | Row dividers inside panels and tables |
| `--border-control` | `#C3CDCA` | Panel and input borders, secondary button borders |
| `--accent` | `#0B6B4F` | Primary button, links, "in the beta", current-page marker |
| `--accent-hover` | `#084E3A` | Link and primary button hover |
| `--accent-tint` | `#DCEFE6` | "In the beta" chip background, current sidebar item |
| `--accent-wash` | `#F1F8F4` | Highlighted pricing column |
| `--focus` | `#1F4FA3` | Focus ring |

On dark (`--ink`) surfaces: text `#E6ECEA`, muted text `#9FB0AB`, dividers `#2A3A43`, prompt `$` and dark-band button background `#6FCF9F` with button text `#0B2A1F`, code comments `#8FA59E`, secondary dark button border `#3A4B54`.

Status palette (chip = text on background; bar = solid fill for the stacked bar):

| Status (ledger "Today") | Chip text | Chip background | Bar fill |
|---|---|---|---|
| in the beta | `#0B6B4F` | `#DCEFE6` | `#0B6B4F` |
| being verified | `#1F4FA3` | `#E1E9F7` | `#1F4FA3` |
| planned | `#7A4F00` | `#F6EBD3` | `#E3B65A` |
| not offered | `#3F4A51` | `#E6EAEC` | `#AEB8BE` |
| not metered | `#FFFFFF` | `#5D6A72` | `#5D6A72` |

Restore window hatching: stripes `#CFE7DB` and `#DCEFE6` every 6 px, border `#A9D2BF`, full-backup tick and marker `#0B6B4F` / `#142027`.

Warning callout (for example "a sleeping project refuses connections"): background `#F6EBD3`, text `#3B2A00`, no border.

All text pairs above meet WCAG AA 4.5:1 at the sizes used. Include a contrast check of each pair in the plan's acceptance criteria.

### Typography

- **Schibsted Grotesk** for all text (headings, body, UI). Self-host as woff2 from the repo. Prefer the variable font (weight axis 400 to 900) so weights 650 and 750 work; if only static files are used, ship 400, 500, 600, 700 and map 650→600 and 750→700.
- **JetBrains Mono** 400 and 500, only for commands, code, connection strings, role names and refusal words. Never for labels or decoration.
- Both are SIL Open Font License: commit the licence files next to the fonts. Subset to Latin, use `font-display: swap`, serve from the same origin, and set fallbacks: `'Schibsted Grotesk', system-ui, sans-serif` and `'JetBrains Mono', ui-monospace, monospace`.
- Sentence case everywhere. Body line length under about 75 characters.

| Role | Size / line height | Weight | Letter spacing |
|---|---|---|---|
| Home hero heading | 68 px / 1.02 (phone: 38 to 46 px) | 750 | −0.035em |
| Page heading (Pricing, What exists) | 60 px / 1.02 (phone: 44 px) | 750 | −0.035em |
| Docs page heading | 48 px / 1.05 (phone: 38 px) | 750 | −0.03em |
| Section heading (home) | 40 px / 1.1 | 700 | −0.025em |
| Docs section heading | 28 px | 700 | −0.02em |
| Feature heading | 24 px | 700 | −0.015em |
| Lead paragraph | 20 px / 1.55 | 400 | 0 |
| Body (marketing) | 17 to 18 px / 1.55 to 1.6 | 400 | 0 |
| Body (docs) | 17 px / 1.7 | 400 | 0 |
| UI text, nav | 15 to 16 px | 500 | 0 |
| Caption, metadata | 13 to 14 px | 400 | 0 |
| Code block | 13.5 to 14 px / 1.75 | 400 | 0 |
| Wordmark | 19 px | 700 | −0.01em |

### Spacing, shape, borders

- Spacing steps: 4, 8, 12, 16, 20, 24, 32, 40, 48, 56, 64, 88, 96 px. Home sections use 96 px vertical padding; page tops use 80 px.
- Radius by hierarchy, not one value everywhere: chips 4 px; buttons, inputs and code blocks 8 px; panels 10 to 12 px; large panels (hero instrument, pricing table) 14 to 16 px; filter pills fully rounded.
- Borders do the separating. No box shadows on panels. Feature blocks are separated by a 2 px `--ink` top rule, not by card outlines.
- Focus: `outline: 2px solid var(--focus); outline-offset: 3px` on `:focus-visible` for every interactive element.
- Motion: none beyond hover colour changes. Respect `prefers-reduced-motion` anyway.
- No dark theme in this pass.

### Layout

- Marketing container: max width 1200 px, side padding 32 px (16 px on phones).
- Docs container: max width 1360 px, three columns: sidebar 240 to 280 px, article max 760 px, "On this page" 200 px. Main column has a 1 px `--rule` left border and 48 px left padding.
- Breakpoints: at 1100 px hide the "On this page" column; at 900 px collapse every grid to one column, hide inline nav links (use the menu), and reduce headings to the phone sizes. The site must work at 390 px wide with no horizontal page scroll; wide tables scroll inside their own box.

## Components

Build each once as a CSS class and reuse it on the site and in the console.

- **Logo.** Inline SVG, 28 × 28: a rounded square (`rx` 6, 2 px `--ink` stroke, no fill) with two vertical bars 4 × 14 px, `rx` 1, at x 8 and x 16, y 7; the left bar `--accent`, the right bar `--ink`. The two bars stand for the two doors. Next to it, the wordmark "Agentic Postgres". Also produce a favicon from the same mark.
- **Beta bar.** Full-width `--ink` strip above the header, 14 px text: left "Invite-only beta. Every organisation is on the Free plan, at no cost."; right "Release 1.22.0" in muted. The version comes from the builder, not hard-coded.
- **Header.** Logo; four links (Quickstart, Docs, Pricing, What exists); then right-aligned "Console" (plain link) and "Request an invitation" (primary button, `mailto:invite@agenticpostgresql.com`). The current page link is `--accent` with a 2 px bottom marker and `aria-current="page"`. Below 900 px the four links move into a menu (see below).
- **Buttons.** Primary: `--accent` background, white text, 600 weight, 8 px radius, padding 12–15 px × 18–22 px. Secondary: white background, `--ink` text, 1 px `--border-control`. On dark bands: `#6FCF9F` background, `#0B2A1F` text. Minimum 44 px touch height. Link-style actions are plain 600-weight accent links with no arrow.
- **Status chip.** 13 px, 600 weight, 4 × 9 px padding, 4 px radius, colours from the status table. Text is the status name in sentence case ("In the beta"). On the site, chips must be generated by the builder from the ledger, never typed by hand, so the claim check covers them.
- **Code block, dark** (commands): `--ink` background, 10 to 12 px radius, a header row with "Terminal" on the left in muted text, `$ ` prompt in `#6FCF9F`, comment lines in `#8FA59E`. Long lines wrap.
- **Code block, light** (connection strings, literal values): white with `--border-control`, header row with a caption such as "Pooled, as the application role". In the connection string, the role, password placeholder and host may be tinted with accent green, planned amber and verify blue.
- **Inline code.** Mono, about 0.88 em, `--surface-hover` background, 2 × 6 px padding, 4 px radius.
- **Spec rows.** Small bordered panel of label–value rows (for example pooled → `customer_app`), 1 px `--rule-soft` dividers.
- **Door panels** (docs Connecting): two side-by-side white panels, "Pooled / for your application" and "Direct / for migrations", each with Host, Role, Pooler rows.
- **Note and warning callouts.** Note: `--ground` background, 8 px radius, 15 px `--text-3`. Warning: the amber callout from the colour section with a bold first sentence.
- **Ledger table.** Three columns (Concept 1.1fr, Today 170 px, What you get 2.8fr), header row on `--surface-sunk`, 20 × 28 px cell padding, `--rule-soft` row dividers, the whole table inside a white 16 px-radius panel. At phone width each row stacks.
- **Pricing table.** Real `<table>` with caption. Columns: Limit, Free, Premium. The Free column has `--accent-wash` background and a 4 px `--accent` top border with an "Your plan" chip; Premium has a 4 px `--border-control` top border, muted values and a "Not available yet" chip. Each value carries an enforcement marker: solid 9 px `--ink` dot = "Enforced", hollow ring = "Shown, not enforced". Values generated from the product's plan table, as today.
- **Stacked status bar.** 28 px tall, 6 px radius, 2 px gaps, one segment per status sized by count, followed by a legend of 12 px swatches with "In the beta, 25" style labels. It has a text alternative (`role="img"` and `aria-label` listing the counts). Counts are computed by the builder from the ledger at build time.
- **Numbered steps.** Use numbers only where the content is a real sequence (Quickstart). A 32 px circle with the number, a bold title, and a short description, with each step's commands in a code block.
- **Docs sidebar.** Groups with a bold 14 px group title: **Start** (Quickstart, Getting started, The command-line client), **Use a project** (Projects, Connecting, Branches, Backups), **Watch and plan** (Plans and usage, Query Insights and monitoring), **Reference** (What a refusal means, What exists). Items are 15 px, 7 × 12 px padding, 6 px radius; the current item has `--accent-tint` background and accent text. Under the groups, the management API address in small mono. The prototype shows a search field: leave it out unless it already exists, since it would be new behaviour.
- **Previous / next.** Two white bordered panels at the foot of each docs page, "Previous" / "Next" caption above the page title.
- **Feedback line.** Every page keeps "Something here wrong or missing? Write to invite@agenticpostgresql.com" above the footer, after a rule.
- **Footer.** Four link columns (Start; Use a project; Understand it: Pricing, What exists, What a refusal means; Contact), then a rule and "Agentic Postgres 1.22.0, beta".

## Site pages

Copy comes from the existing Markdown pages unless noted. Any new sentence must pass the ledger claim check; if the checker cannot vouch for a sentence, use the existing wording instead.

### Home (`Main.dc.html`)

In order:

1. Beta bar and header.
2. **Hero**, two columns (1.05fr / 1fr, 64 px gap). Left: heading "Hosted PostgreSQL 18 that only claims what it has proven." (confirm the checker accepts it; fallback "Your team's own PostgreSQL 18 projects, described exactly as they are."), lead paragraph, primary "Request an invitation", secondary "Read the quickstart", and "Already invited? Open the console". Right: the **restore window instrument**, a white panel showing an example project header with a "ready" chip, the two doors as spec tiles, the hatched restore window bar with day labels underneath, "Last full backup" and "Latest restore point" captions, and a sunk box with "Restore into a new branch at …", the matching `apg branch create … --at … --wait` command, and "The project itself is never overwritten." Label it as an example project.
3. **What every project gives you**: white band; four blocks in a 2 × 2 grid, each with a 2 px ink top rule, title, status chip, paragraph, one limit or spec, and a link to its docs page: Two connections, both over TLS; Branches you can restore to a moment; Continuous off-site backups; Numbers that name their source.
4. **From invitation to connection string**: the four Quickstart steps, each with its commands (see "Interactive parts").
5. **43 concepts. 25 of them work today.**: white band; heading and both numbers from the builder; stacked status bar with legend; four example ledger rows (one per status); dark button "See all 43 in What exists".
6. **Free during the beta**: short text plus a four-row comparison (Active projects, Branches per project, Compute sizes, Storage) and a link to Pricing.
7. **Dark invitation band**: "The beta is invite-only." with the existing invitation text, the mint "Email for an invitation" button and "I have an account, open the console".
8. Footer.

### Docs pages (`Docs.dc.html`)

One shared template for Quickstart, the docs index and all nine docs pages: breadcrumb ("Docs / Use a project"), H1, lead, optional row of status chips for the concepts the page covers (generated from the ledger), body, previous/next, feedback line. Docs body headings get `id`s so the "On this page" column can link to them; the builder can generate both the ids and that list from the Markdown headings. Tables in docs (doors, CLI families, exit codes, refusals, monitoring readings) use the ledger-table style. The docs index page lists the four sidebar groups with each page's one-line description.

### Pricing (`Pricing.dc.html`)

Heading "Free while it is a beta.", lead, the pricing table, then three notes with ink top rules: "Enforced and shown", "Notices at 80%", "From the terminal" (with `apg plan list / show / notify-me`). Footer line "The plans here are generated from the product's own plan table."

### What exists (`Ledger.dc.html`)

Heading, lead including "generated from the same file the product checks itself against", status filter (see below), "Showing N of 43 concepts", the ledger table, and a closing line about `not_available` naming the row, linking to What a refusal means. Table text stays exactly as generated today.

## Interactive parts without JavaScript

The site currently ships no script; keep it that way unless the plan proposes a first-party script with its own decision record. Static or CSS-only versions:

- **Restore window (hero):** static. Draw the bar with CSS, place the marker at a fixed example moment, and show the fixed matching command. No slider and no copy button.
- **Quickstart steps (home):** an ordered list showing all four steps, each with its own code block. The prototype's click-to-switch panel is not needed.
- **Ledger filter:** CSS-only with a group of visually styled radio inputs and `:has()` rules that hide non-matching rows (each row carries its status as a class). Without `:has()` support, all rows show. If the planner judges this too clever, drop the filter and group the table by status instead; both are acceptable.
- **Copy buttons:** leave out in this pass.
- **Mobile menu:** `<details>` and `<summary>` ("Menu"), opening a full-width list of the main links, each with a short description on the right (Quickstart "4 steps", Docs "9 pages", Pricing "Free in the beta", What exists "43 concepts", Console "for members"), then a full-width "Request an invitation" button, as in `Mobile.dc.html`. Counts come from the builder.

## The console

The prototype does not include console screens; apply the same tokens and components to every existing console view. Start the plan with an inventory of the console's views and elements from `app.js`, then map each to the patterns below.

**Layout.**
- **Top bar:** logo and wordmark, organisation name and switcher (if one exists), and the signed-in user with sign out. It has a 1 px `--rule` bottom border and sits on `--ground`.
- **Left navigation (240 px):** for the selected project, in this order: Overview, Connect, Branches, Backups, Usage, Insights, Monitoring, Plan, Notifications, Settings. Then, separately, the organisation-level Members and keys. The current item uses the docs-sidebar style.
- **Content area:** max width 1100 px, page heading 32 to 40 px, 700 weight.
- **Phone width:** the left navigation becomes a `<details>` menu, as on the site.

**Patterns**, all reusing the site components:

- **Project state chip.** State comes from operations and is never guessed. Map the states as follows:
  - **Green ("in the beta" colours):** ready.
  - **Blue ("verify" colours):** creating, starting, updating, suspending, deleting, as in-progress states.
  - **Amber ("planned" colours):** sleeping.
  - **Grey ("not offered" colours):** deleted.
  - **Unknown:** uses the dark "not metered" chip and must never look like ready.
- **Operation row.** An operation's id in mono, its status chip (pending, running with the step, succeeded, failed with the error word), and its timestamp.
- **Shown-once secret panel.** Used for a new password, connection string, invitation link, management key or export link. It has an amber `#E3B65A` 2 px border, white background, and the heading "Shown once". The value goes in a light code block, with the console's existing copy control if it already has one, and a plain sentence on what happens if it is lost. This must look clearly different from ordinary panels.
- **Readings list** (Monitoring and Usage). Each reading is a row with the name, the value, its age ("read 3 minutes ago") and its source in `--text-3`. A reading that could not be determined shows "not read" and the reason in place of a value, never a blank or zero. There are no colours for good or bad, matching the docs ("no threshold, no colour and no alert").
- **Restore window** (Backups). The same hatched bar as the home hero, with real data and how recently it was read. When it could not be determined, show the reason instead of the bar.
- **Refusal message.** A warning callout headed by the refusal word in mono (for example `plan_limit_reached`), followed by the meaning from the refusals table and a link to What a refusal means.
- **Destructive confirmation** (delete a project, delete a branch). A panel with a 2 px `#7A4F00` border, a sentence saying exactly what will be lost, a labelled input for typing the key or name, and the confirm button disabled until it matches. If that logic doesn't exist, keep the current behaviour and style it only.
- **Tables** (Insights statements, branches, members, keys, notifications). Use the ledger-table style. Numeric columns are right-aligned with tabular figures (`font-variant-numeric: tabular-nums`), and statement text is in mono.
- **Forms.** Labels sit above inputs at 14 px and 600 weight. Inputs have a 1 px `--border-control` border, 8 px radius, 11 × 12 px padding, and a white background. Errors go below the field in the warning colours.
- **Empty states.** One sentence saying what to do next, with the command or action (for example how to create the first project with `apg project create`).
- **Sign-in screens** (create account, sign in, second factor with QR). A single centred 420 px white panel on `--ground`, with the logo above it. The QR code sits on white with 16 px padding.
- **SQL editor.** Restyle only through CSS (fonts, borders, colours). Do not touch its scripts.

Where the CSS needs a hook the console does not have, add class names or wrapper elements through the existing element helper. No other script changes.

## What the plan must contain

1. The constraint check above, with sources, and any conflicts.
2. An inventory: site template and pages, builder touch points (components generated from the ledger and plan table, heading ids, counts, version), console views.
3. Work items in order. Each one lists the files touched, what changes, and how it is tested. Suggested order:
   1. tokens and fonts;
   2. the site template, header and footer;
   3. builder-generated components;
   4. each site page;
   5. the console shell (top bar, navigation);
   6. the console patterns, view by view;
   7. phone widths;
   8. acceptance checks.
4. The CSP change needed for self-hosted fonts, if any.
5. Acceptance criteria:
   - all existing tests and contract tests pass unchanged, and the ledger claim check passes;
   - no request leaves the origin (checked in the browser network panel);
   - every text colour pair passes 4.5:1;
   - visible keyboard focus everywhere;
   - no horizontal scroll at 390 px;
   - each page compared side by side with its prototype screen.
6. Size budget results (CSS and fonts).
7. Open questions for me, kept short. In particular, anything that would need a new decision record (for example a small first-party script for copy buttons or the hero slider) goes here as a Stage 6 candidate, not into this pass.

Keep everything out of scope that belongs to Option 2: no framework, no bundler, no npm, no new behaviour.

# Console UX patterns: Neon, Convex, and others for contrast

**Session 47 Run 1 (D2977).** Gathered by a research sub-agent on 2026-10-29 from the
sources each row cites, and read whole before it was committed. **The *Adopt?* column
is an input to Run 2's design brief, not a decision**: the brief decides, and Sheet D1
approves. Where a *Why* cell assumes a console without script ("no script menu", "plain
form control"), ADR 0295 has since allowed the console script inside first-party rules;
the pattern stands, the constraint it names does not. Nothing here is copied — no
markup, wording, icon, asset or brand.

**Method.** I read public documentation, changelogs and help pages of Neon and Convex (primary) and Supabase, Vercel and PlanetScale (contrast) on 2026-10-29, using web search plus page fetches. Every row below cites a URL I actually fetched that day. **This file records patterns only.** No markup, wording, icons, assets or branding was copied. UI labels of a few words appear only where they are needed to identify a pattern. **No screenshot was viewed.** Every description comes from page text. Where a page offered only image alt text or a caption, the row says so. Docs describe intended behaviour, not a live console, so a few rows note gaps where a page was silent.

**Recommendation key.** Recommendations are judged against our console:

- no framework, no npm, no third-party bytes, light theme only;
- fixed-route static pages;
- a project creation of about 25 minutes, most of it the first backup;
- a free plan of 1 project and 1 branch.

**Adopt** means take the pattern as it is. **Adapt** means take the idea and change it. **Skip** means it does not fit.

---

## 1. Project creation and how its progress is shown

| Pattern | Product | Source (URL) | Read | Adopt? | Why |
|---|---|---|---|---|---|
| A short creation form: name, region and engine version, with sensible defaults. The project comes with a default branch, database and owner role, and creation lands the user on the project's overview page. | Neon | https://neon.com/faqs/create-new-neon-project | 2026-10-29 | Adopt | Fewest decisions before the long wait. We should also say which defaults the user gets. |
| Creation failures are written as a short decision list: hit the plan's project cap (delete one, upgrade, or ask support), regional incident (check the status page, retry, or pick another region), unclear error (ask the community with the request ID). | Neon | https://neon.com/faqs/create-new-neon-project | 2026-10-29 | Adopt | The same three-way triage fits our refusal and failure pages, and the request ID is something we already have. |
| The create form shows optional add-on services only when the chosen region supports them. | Neon | https://neon.com/docs/changelog/2026-09-18 | 2026-10-29 | Skip | We have one region and no optional services. |
| A deployment's detail page lists its phases as separate named steps, each with its own duration and a total. Each step is an accordion that expands to show its log. | Vercel | https://vercel.com/docs/deployments/troubleshoot-a-build | 2026-10-29 | Adopt | This fits a 25-minute creation best: show named steps with their elapsed time so the backup step is visibly the long one. The data can come from the server, so it survives a page refresh. |
| A step that waits on an outside resource is held in a visible "provisioning" state. It lists each item with its own status and marks a failed or timed-out item as such, so the failed phase is obvious. | Vercel | https://vercel.com/docs/deployments/troubleshoot-a-build | 2026-10-29 | Adapt | Per-item status inside a step suits our first backup. Do not copy the option to skip the step, because a project without its first backup must not be offered as done. |
| When a run fails before any log exists, the page shows the error message in place of the missing log, not a blank panel. | Vercel | https://vercel.com/docs/deployments/troubleshoot-a-build | 2026-10-29 | Adopt | Never show an empty log box. Say what failed and that no log exists. |
| Help for a failed run points to the specific failing line, not the last line, because the last line is often a generic exit message. | Vercel | https://vercel.com/docs/deployments/troubleshoot-a-build | 2026-10-29 | Adapt | Show the failing step's own reason on the progress page, and keep the raw log behind a disclosure. |
| The deployments list filters by branch, date range, environment and status. | Vercel | https://vercel.com/docs/deployments/managing-deployments | 2026-10-29 | Skip | We have one project and one branch on Free, so a status badge on the single row is enough. |
| Before an in-place upgrade the dashboard shows an estimated duration and lists blockers. It explains that duration depends on data size and disk throughput. | Supabase | https://supabase.com/docs/guides/platform/upgrading | 2026-10-29 | Adapt | Show an expected range for creation taken from our measured times (for example, "usually 20-30 minutes"), and say what drives it (the first backup), before the user clicks create. |
| A long-running import's status moved from the terminal into the dashboard, so the user no longer has to keep the command line open. | Convex | https://ship.convex.dev/changelog/vol-4-snapshot-import-status-in-dashboard | 2026-10-29 | Adopt | The principle holds for us: progress belongs to the server and the page, not to a browser tab that must stay open. The entry did not describe how progress is drawn. |

## 2. The connect dialog

| Pattern | Product | Source (URL) | Read | Adopt? | Why |
|---|---|---|---|---|---|
| One Connect control in the project navigation opens a modal. Selectors for branch, database and role assemble the connection string as you change them. | Neon | https://neon.com/docs/connect/connect-from-any-app | 2026-10-29 | Adapt | Keep one Connect entry point that is always visible. With 1 branch and fixed roles, selectors shrink to a role choice (app and admin), which is a plain form control, not a script widget. |
| Pooled versus direct is a single toggle, on (pooled) by default. The docs stress that the toggle only changes which string is displayed and does not turn the pooler on or off. | Neon | https://neon.com/docs/connect/connection-pooling | 2026-10-29 | Adopt | Our two hostnames (pool and direct) map exactly onto this toggle. Say explicitly that both always exist. |
| The pooled/direct explanation is task-based. Pooled is for app traffic, serverless and many short connections. Direct is for migrations, dumps, replication, long analytics and anything that needs session state. Session features that break under transaction pooling are listed. | Neon | https://neon.com/docs/connect/connection-pooling | 2026-10-29 | Adopt | Put a two-line "use this for..." under each option, and link the full caveat list. |
| The same split is explained by port (standard port direct, alternate port through the bouncer). It gives the same use-it-for list and names the transaction-mode caveats (temporary tables, LISTEN/NOTIFY, session advisory locks, SET). | PlanetScale | https://planetscale.com/docs/postgres/connecting/pgbouncer.md | 2026-10-29 | Adapt | This confirms the explanation is industry-standard. We separate by hostname, not port, so copy the reasoning, not the port framing. |
| Three connection methods (direct, session pooler, transaction pooler), each tied to where your code runs. Network-version caveats are part of the choice. | Supabase | https://supabase.com/docs/guides/database/connecting-to-postgres | 2026-10-29 | Skip | Three modes is more than we offer. Two is clearer. |
| The connection string shown carries a password placeholder, and the docs warn to percent-encode reserved characters when the user substitutes it. | Supabase | https://supabase.com/docs/guides/database/connecting-to-postgres | 2026-10-29 | Adapt | If we ever show a string without the secret, mark the placeholder visibly and give the encoding warning. If our generated passwords contain no reserved characters, say that. |
| A decision guide on choosing a connection starts from where the code runs (language, persistent server, serverless/edge, browser) and ends at a driver plus pooled or direct. It warns against stacking client-side pooling on the server pooler. | Neon | https://neon.com/docs/connect/choose-connection.md | 2026-10-29 | Adopt | A static decision list fits a fixed-route docs page linked from the dialog. |
| A diagram labels the parts of a connection string (user, password, host, database, sslmode). | Neon | https://neon.com/docs/get-started/connect-neon | 2026-10-29 | Adopt | A labelled string is cheap static HTML and helps people who copy pieces into a GUI client. |
| Framework snippets offered in Neon's docs: serverless driver, Next.js, Drizzle, Prisma, Python psycopg2, Go, .NET, Ruby, Rust, psql. The page did not say which of these the modal itself lists. | Neon | https://neon.com/docs/get-started/connect-neon | 2026-10-29 | Adapt | Ship the brief's set (psql, Node pg, Prisma, Drizzle, psycopg, Go pgx, .env) as static tabs or a select, generated server-side or from one template. Tell Prisma/Drizzle users that migrations use the direct string. |
| A "How are you connecting?" picker reformats the string per language or framework and lists which files to edit. An "Other" choice gives a generic string. | PlanetScale | https://planetscale.com/docs/concepts/connection-strings | 2026-10-29 | Adopt | "Which file to put this in" is the step first users miss, and an "Other" fallback avoids dead ends. |
| The password is shown only once, at creation, because only a hash is stored. The UI asks the user to copy it before leaving. If it is lost, the remedy is to create or reset a new one. | PlanetScale | https://planetscale.com/docs/postgres/tutorials/planetscale-postgres-quickstart.md | 2026-10-29 | Adopt | This matches our shown-once token model. State "shown once" before reveal, and give the reset path in the same place. |
| Named credentials: each password gets a human name and is listed on a settings page with rename and delete. Deleting disconnects its clients, and the docs say how long open connections may take to drop. | PlanetScale | https://planetscale.com/docs/concepts/connection-strings | 2026-10-29 | Adapt | We have fixed roles, not ad-hoc passwords. Still, state what a rotation does to live connections and how fast. |
| Reset password sits in a role's row menu, behind a confirmation dialog. It then shows a generated value. The docs tell the user the old one stops working on the next connection and list everywhere to update it (.env, secret manager). | Neon | https://neon.com/docs/manage/roles | 2026-10-29 | Adopt | Confirm, show once, then show a short "update these places" checklist. |
| Copy controls and "copied" feedback: none of the fetched pages described these in text (no screenshots viewed). | All | (none) | 2026-10-29 | Adapt | Not evidenced. Build it ourselves: a button beside each value, an accessible "Copied" status line (aria-live) and a text fallback when the clipboard is unavailable. |

## 3. Branch UX

| Pattern | Product | Source (URL) | Read | Adopt? | Why |
|---|---|---|---|---|---|
| A branch is created from the Branches page. The parent is preselected, the name is optional, and the user chooses what data to start from (current, a past point in time, schema only, anonymized). | Neon | https://neon.com/docs/manage/branches | 2026-10-29 | Adapt | Keep "parent + point in time" (we already do restore-to-branch). Drop schema-only and anonymized, which we do not have. |
| Branches created in the console default to auto-delete after a short period (1 day preselected; 1 hour and 7 days offered), and the user can turn it off. | Neon | https://neon.com/docs/manage/branches | 2026-10-29 | Adapt | This suits our temporary-branch expiry. Preselect an expiry and show it in the list. |
| The branch list shows name, parent, compute and status, data size, creator and last active, with a tag on the default branch. | Neon | https://neon.com/docs/manage/branches | 2026-10-29 | Adopt | The same columns, fewer of them, fit a static table. Tag the main branch. |
| Row actions (rename, set default, protect, set expiration, delete) live in one overflow menu on the branch page. Protected and root branches refuse delete and reset. | Neon | https://neon.com/docs/manage/branches | 2026-10-29 | Adapt | Without a script menu, use plain buttons on the branch page. Disable refused actions and add a one-line reason, not a hidden control. |
| Reset from parent overwrites the branch with the parent's latest state. Live connections drop briefly and reconnect, and the connection details stay the same. If the branch has children, an error dialog offers to delete them first. | Neon | https://neon.com/docs/guides/reset-from-parent | 2026-10-29 | Adopt | Say in the confirmation what is lost, that connections blip and that strings do not change. Make the blocking condition actionable. |
| Plan limits on branches are stated per plan, and creation is blocked at the cap while existing branches are untouched. Neon's two pages disagree on Free's number (3 "root branches" on one, 10 per project on the other). | Neon | https://neon.com/docs/introduction/plans ; https://neon.com/docs/manage/branches | 2026-10-29 | Adapt | Show "1 of 1 branches" on the list itself, so a refusal never comes as a surprise. Neon's inconsistency is a warning to state ours from one source. |
| Production and development branches are labelled differently in the branch dropdown and the list. Production carries a badge. | PlanetScale | https://planetscale.com/docs/postgres/branching.md ; https://planetscale.com/docs/postgres/dashboard.md | 2026-10-29 | Adopt | A text badge (not colour alone) on the main branch everywhere a branch name appears. |
| No "reset" exists. The nearest options are restore-a-backup-to-a-new-branch or delete and recreate. | PlanetScale | https://planetscale.com/docs/postgres/branching.md | 2026-10-29 | Skip | We already have reset. This is contrast only. |

## 4. Empty states and first-run onboarding

| Pattern | Product | Source (URL) | Read | Adopt? | Why |
|---|---|---|---|---|---|
| The first time a new project's SQL editor opens, it is prefilled with sample SQL that creates and fills a small demo table, so "Run" works on the first click. | Neon | https://neon.com/docs/get-started/query-with-neon-sql-editor ; https://neon.com/docs/get-started/signing-up.md | 2026-10-29 | Adopt | Cheap, static, and turns an empty editor into a first success. Use our own SQL and wording. |
| The branch Overview lists every service with its status, disabled ones included, so the page doubles as "what you could still add". | Neon | https://neon.com/docs/changelog/2026-08-07 | 2026-10-29 | Adapt | Our version is a short "next steps" list on the project page (connect, run a query, create a branch), each with its done/not-done state read from the server, so it survives refresh. |
| First run happens in the CLI: one command logs in through the browser, creates the project, writes the URLs locally and keeps syncing. | Convex | https://docs.convex.dev/quickstart/nodejs | 2026-10-29 | Skip | Our first run is console-first by decision. The CLI path stays secondary. |
| The project list is cards, each with an overflow menu for settings and delete. | Convex | https://docs.convex.dev/dashboard/projects | 2026-10-29 | Skip | With a Free limit of 1 project, a list of cards is overhead. Go straight to the project. |
| Neither Neon nor Convex docs described a dedicated empty-project or getting-started checklist page. Neon's console tour starts after creation. Convex's projects page says nothing on empty states. | Neon, Convex | https://neon.com/docs/get-started/signing-up.md ; https://docs.convex.dev/dashboard/projects | 2026-10-29 | Adapt | This gap is ours to fill. A short server-rendered checklist on the project page is the recommendation. |

## 5. Navigation and information architecture

| Pattern | Product | Source (URL) | Read | Adopt? | Why |
|---|---|---|---|---|---|
| The sidebar is split into project-level items above and branch-level items below. The branch picker sits between the two, so every branch-scoped page shows which branch it applies to. | Neon | https://neon.com/docs/changelog/2026-08-07 | 2026-10-29 | Adapt | Show the current branch name as a fixed header line on branch-scoped pages. A picker is unnecessary at 1 branch. |
| Account-level items (switch or create organization, account settings, status, help) are gathered into one profile menu at top right. | Neon | https://neon.com/docs/changelog/2026-09-18 | 2026-10-29 | Adapt | Put sign-out, account, status and help in one fixed corner, as links, not a script menu. |
| Settings are split into tabs. Project-wide settings carry a label saying they apply to all branches. | Neon | https://neon.com/docs/changelog/2026-09-18 | 2026-10-29 | Adopt | A scope label ("applies to the whole project" or "this branch only") prevents a whole class of mistakes. |
| The project name at the top is a type-to-filter switcher whose rows expand to that project's pages and deployments. | Convex | https://docs.convex.dev/dashboard/projects | 2026-10-29 | Skip | Needs script and serves many projects. We have one. |
| The deployment switcher shows each entry's kind (production, a person's dev, a preview) above its name. | Convex | https://docs.convex.dev/dashboard/deployments | 2026-10-29 | Adapt | Lead every environment or branch label with its kind as text. |
| A command palette (Ctrl/Cmd+K or "/") searches projects, deployments, documents and pages. | Convex | https://ship.convex.dev/changelog/item-382-quickly-search-and-navigate-between-projects-deplo ; https://docs.convex.dev/dashboard/teams | 2026-10-29 | Skip | Heavy for a handful of fixed routes. |
| Navigation is scoped to one organization at a time, reopens the last active one, and gives projects and organizations separate sidebars. Usage banners are consolidated at the top and notifications are filtered to the active organization. | Supabase | https://supabase.com/changelog/33670-upcoming-breaking-change-to-dashboard-navigation.md | 2026-10-29 | Adapt | Take "one banner slot at the top" and "remember where I was". Skip the multi-organization machinery. |
| Horizontal tabs are replaced by a resizable, hideable sidebar with the same links at team and project level, ordered by frequency. On mobile, a floating bottom bar replaces the navigation. | Vercel | https://vercel.com/changelog/new-dashboard-navigation-available | 2026-10-29 | Adapt | Order by frequency and keep the same links at every level. On a phone, use a plain top or bottom link list in CSS, not a draggable bar. |

## 6. The SQL editor

| Pattern | Product | Source (URL) | Read | Adopt? | Why |
|---|---|---|---|---|---|
| Branch and database selectors sit above the editor, defaulted to the main branch and database. | Neon | https://neon.com/docs/get-started/signing-up.md | 2026-10-29 | Adapt | Put a fixed "connected to: branch / database / role" line above the editor. Ours connects with the customer's own credential, so name the role too. |
| The editor connects as a short-lived role whose permissions depend on the person and the server chosen (primary for read-write, replica for read-only). Switching database or server reconnects and clears the output. | PlanetScale | https://planetscale.com/docs/postgres/web-console.md | 2026-10-29 | Adopt | Say plainly that changing the target reconnects and clears results. Show the connection state (connecting, connected, disconnected) beside the target line. |
| Browser query access to production is off by default and must be enabled by an admin. Access then depends on the person's role. | PlanetScale | https://planetscale.com/docs/postgres/web-console.md | 2026-10-29 | Skip | Our editor speaks with the customer's own credential, so the credential is the gate. A second toggle would add nothing. |
| Results appear below the editor. Multiple statements give numbered result tabs in run order. Expand, export (CSV/JSON/XLSX) and copy controls appear only when there are results. | Neon | https://neon.com/docs/get-started/query-with-neon-sql-editor | 2026-10-29 | Adapt | Numbered results per statement and copy-as-CSV are cheap without libraries. Skip XLSX (no third-party bytes). |
| A left pane holds saved queries and history. History entries are size-capped and truncated. | Neon | https://neon.com/docs/get-started/query-with-neon-sql-editor | 2026-10-29 | Adapt | Keep a session-only history in the page. Persistent saved queries are later work. |
| psql-style meta-commands (list tables, describe table, help) work in the browser editor. | Neon ; PlanetScale | https://neon.com/docs/get-started/query-with-neon-sql-editor ; https://planetscale.com/docs/postgres/web-console.md | 2026-10-29 | Adapt | People type these by habit. Support a few, or answer them with a one-line pointer to the equivalent SQL. |
| The option that executes a statement to measure it is labelled to make clear it really runs the statement. A tooltip warns that data-modifying statements will change data. | Neon | https://neon.com/docs/changelog (index) ; https://neon.com/docs/get-started/query-with-neon-sql-editor | 2026-10-29 | Adopt | Wherever an action has side effects that are not obvious, the label itself must say so. |
| An AI assistant writes SQL in a diff view the user accepts or rejects, and explains errors. | Supabase ; Neon | https://supabase.com/blog/supabase-studio-3-0 ; https://neon.com/docs/get-started/query-with-neon-sql-editor | 2026-10-29 | Skip | Out of scope, and it would put a third party in the page. |
| Clearing or deleting a table requires typing its name. Deleting production rows needs a confirmation. An optional setting requires confirmation for any dashboard edit. | Convex | https://docs.convex.dev/dashboard/deployments/data ; https://docs.convex.dev/dashboard/deployments/deployment-settings | 2026-10-29 | Adapt | Use type-to-confirm for project and branch delete, not for every SQL statement. |

## 7. Notifications, activity feeds, usage and limit warnings

| Pattern | Product | Source (URL) | Read | Adopt? | Why |
|---|---|---|---|---|---|
| Web notifications live in a popover with an unread counter. An item read on the web is not re-sent by email, and items can be archived (kept 365 days). | Vercel | https://vercel.com/docs/notifications | 2026-10-29 | Adapt | Take the read state that suppresses email. Render the inbox as a plain page, not a popover. |
| Critical notifications cannot be fully turned off: the user can drop one channel but not both web and email. | Vercel | https://vercel.com/docs/notifications | 2026-10-29 | Adopt | A sensible rule for our project-ready, project-failed and limit notices. |
| The notification types are grouped (account, deployment, domain, usage, integrations), and a table names who receives each. | Vercel | https://vercel.com/docs/notifications | 2026-10-29 | Adopt | A small static table of "what we tell you and when" belongs in our docs. |
| Each deployment has a history page: an audit list of configuration changes (deploys, index changes, environment variable changes). Usage-limit warnings, exceedances, disables, re-enables and limit edits are logged there too. | Convex | https://docs.convex.dev/dashboard/deployments/history ; https://docs.convex.dev/production/usage-limits | 2026-10-29 | Adopt | One activity list per project that includes limit events, read from the server, is exactly what our control records can feed. |
| Spending alerts go to organization admins at 80% and 100% of a threshold they set. The feature was renamed from "limits" to "notifications" because it does not stop anything. | Neon | https://neon.com/docs/changelog/2026-07-31 | 2026-10-29 | Adapt | Name a notice for what it does. A Free cap that refuses is a "limit"; a heads-up is a "notice". We have no spend, so apply this to storage and branch counts. |
| Two thresholds: a warning that only emails, and a disable that pauses every team project until the limit is raised. | Convex | https://docs.convex.dev/dashboard/teams ; https://docs.convex.dev/production/usage-limits | 2026-10-29 | Adapt | A warn-then-refuse pair fits. State on the usage page which line is which. |
| A usage page shows consumption against plan limits with daily charts and per-project views. | Convex | https://docs.convex.dev/dashboard/teams | 2026-10-29 | Adapt | Use numbers and bars in CSS, no chart library. "N of M" lines are enough. |
| Free projects are paused after low activity. Email warns about a week before and again on pause. The dashboard offers a resume action with a countdown of days left to restore. | Supabase | https://supabase.com/docs/guides/platform/project-pausing ; https://supabase.com/docs/guides/platform/upgrading | 2026-10-29 | Adapt | We have idle sleep. Show "asleep since..." and what wakes it, with a countdown only if something real expires. |
| Over a Free quota, a grace period runs first. After it, a lasting dashboard warning remains even if usage drops. The page lists the next actions (reduce usage, upgrade, wait for the cycle reset). | Supabase | https://supabase.com/docs/guides/platform/billing-faq | 2026-10-29 | Adapt | Always list next actions with a warning. Skip lingering warnings after the condition clears, which confuse people. |
| Free compute is suspended when the monthly quota is used. Writes fail at the storage cap while the data is kept. Each consequence is paired with "until the next period or until you upgrade". | Neon | https://neon.com/docs/introduction/plans | 2026-10-29 | Adopt | Pair every consequence with when it ends and what lifts it, and link the plans page. |

## 8. Help, support and contextual docs

| Pattern | Product | Source (URL) | Read | Adopt? | Why |
|---|---|---|---|---|---|
| Help lives in the profile menu and opens a support center. It first asks which organization needs help, then lists only the channels that organization's plan allows (assistant, docs, tickets, community). | Neon | https://neon.com/docs/introduction/support | 2026-10-29 | Adapt | One help page that shows only the channels open to this user (invite email and docs). Never list a channel they cannot use. |
| The support policy says to check the status page before opening a request. | Neon | https://neon.com/docs/introduction/support | 2026-10-29 | Adopt | Put a status link beside the contact address. |
| The Health page lists named "insights" (a specific problem). Each carries a chart, the events behind it and a link to the doc that explains how to fix it. Problems are stated with numbers and timestamps, not alarm words. | Convex | https://docs.convex.dev/dashboard/deployments/health | 2026-10-29 | Adopt | The tone and shape fit: fact, evidence, link to the fix. A paid-plan feature is marked as such in place. |
| A plain support landing page with a few cards (community, sales) and a status link near the top. | Vercel | https://vercel.com/help | 2026-10-29 | Adapt | Keep it this small. Swap sales for our invite email. |
| Support channels are Discord for general questions, email for specific issues and a separate security address. | Convex | https://docs.convex.dev/production/contact | 2026-10-29 | Adopt | We need the security address line too. |
| Support tiers are written out by plan, with priority levels reserved for production issues. | PlanetScale | https://planetscale.com/docs/support.md | 2026-10-29 | Skip | Invite-only, no tiers. |

## 9. Errors and refusals with a next action

| Pattern | Product | Source (URL) | Read | Adopt? | Why |
|---|---|---|---|---|---|
| A connection-errors page names each error, gives the likely cause, then lists fixes from quickest to most involved, and ends with status page or support as the fallback. | Neon | https://neon.com/docs/connect/connection-errors.md | 2026-10-29 | Adopt | The best template for our refusal copy: what happened, why, and what to do (ordered), then who to ask. |
| Client errors are documented as records: severity, SQLSTATE code, message, optional hint, then "when" and "resolution". Severity is explained (fatal ends the connection, an error fails only the request). | PlanetScale | https://planetscale.com/docs/postgres/connecting/client-error-reference.md | 2026-10-29 | Adopt | Show a stable code beside every console refusal, so the docs page can be keyed by it. |
| An error page entry shows a sample message, the cause, example code and the fix, and links related resources. | Convex | https://docs.convex.dev/error | 2026-10-29 | Adapt | Keyed error docs are good. Our console errors should link to their entry directly. |
| A rate-limit refusal says how to react: when the caller is still ramping up, the message says the allowed rate is rising, so a retry will succeed shortly. | Vercel | https://vercel.com/docs/limits | 2026-10-29 | Adopt | A refusal that says whether waiting will help is the most useful sentence we can write. Apply it to "project still creating" and "TOTP step". |
| A paused deployment returns a named error to visitors. The owner gets an email with details and next steps: compare usage with the guidelines, upgrade or reduce, contact support if it persists. | Vercel | https://vercel.com/kb/guide/why-is-my-account-deployment-blocked | 2026-10-29 | Adapt | The owner-facing half is right. Our visitors are the customer's own clients, so a Postgres error is all they see. |
| A plan-cap failure is answered with three exits: delete something (with its recovery window), upgrade, or ask for a higher limit. | Neon | https://neon.com/faqs/create-new-neon-project | 2026-10-29 | Adopt | Our "plan limit reached" should name the counted thing ("1 of 1 projects"), then offer delete or ask for more by email. No dead end. |
| Deleting a project reminds the user what is not released (custom domains stay reserved). | Neon | https://neon.com/docs/changelog (index, first 100k characters) | 2026-10-29 | Adopt | Delete confirmations should list what survives the delete as well as what is lost. |

---

## Sources that could not be read

- https://convex.dev/pricing/faq. The fetch timed out (300 s) and was not described.
- https://www.convex.dev/pricing/faq. The fetch timed out (300 s) and was not described.
- https://discord-questions.convex.dev/m/1495431213480022046 returned HTTP 429. Convex's in-dashboard limit wording, seen only in a search snippet, is therefore not cited.
- https://planetscale.com/docs/onboarding/connect-to-your-database. The fetch returned the docs landing page, not the connect content. Not cited for connect behaviour.
- https://supabase.com/docs/guides/getting-started. Read, but it held no project-creation content. Supabase's creation progress screen is not documented in anything I read.
- https://docs.convex.dev/dashboard. Read, but it is a one-paragraph overview. The sub-pages were used instead.
- https://neon.com/docs/changelog. Only the first 100,000 of about 838,000 characters were read.
- Not fetched directly, so their content is not relied on: https://neon.com/docs/changelog/2026-10-23, the PlanetScale CLI branch page (a wait-until-ready flag was seen only in a search snippet, so that row was dropped), and the third-party blogs that appeared in search results.
- No screenshot was viewed on any page. Image alt text was seen on a few pages (Neon's connection-details modal, Vercel's deployment pages), and no layout claim is based on it.

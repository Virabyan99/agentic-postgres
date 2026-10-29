# Session 47 — the console's design brief

**Run 2 of `docs/plans/session-47-implementation-plan.md` (D2947–D2958, D2976, D2978).**
The rules it lives under are ADR 0295 (features inside first-party rules), 0296 (long
operations), 0297 (refusals and notices), 0298 (help and the checklist), and the parts of
ADR 0288 that stand (one token block, the self-hosted typefaces, light only, no `style=`).
The research it borrows patterns from is `research.md` beside this file; the console's
current words and calls are `inventory.md`.

**The prototype** is `prototypes/console.html`: ten screens of first-party HTML, CSS and
script on the console's own token block (byte-equal) and typefaces, example data only.
It is published to the operator as a private page,
**https://claude.ai/artifact/YYuCFX7YiqkTfEdu8jh2jG**, with the two typefaces inlined
(the page's host admits no other font source; the bytes are the console's own — sha256
`b29bc789…`, `61a4199a…`). Screenshots of every screen at 390 × 844 and 1280 × 800, from
the pinned Playwright image, are in WSL `~/s47/run2/shots/` (20 files; no overflow at
either width, the typeface loaded, no console error, no request off the page's origin).
The prototype is a design, not the build: Runs 4–9 rebuild it as the console's own
modules under ADR 0295, with the CSS in `app.css` and no inline script.

---

## 1. Who it is for, and the one job

A newcomer — the first person was a developer who had never used the product; the
operator names students as a likely next one — who holds an invitation and wants **a
working connection string in their own application**. Every screen answers *where am I,
what is happening, what do I do next*. The console's voice is the site's (Session 45's
copy rules, kept): plain, active, specific; a control says exactly what it does; a
message says what happened and what to do, with no apology.

## 2. Information architecture

- **Top bar**: the mark (to the Projects page), *Help*, *Notifications* with its unread
  count, and the account menu (signed-in name, account and second factor, help, sign out).
- **Left navigation**, top to bottom: the **organisation switcher**, the **project
  switcher** (with the project's state chip), the **project's pages** — Overview, Connect,
  SQL editor, Branches (with *1 of 1*), Backups, Usage, Slowest queries, Monitoring,
  Settings — and the **organisation's** — Projects, Activity, Plan and usage,
  Notifications, Members and keys. The current page is marked (`aria-current`).
- **Every page is at most two clicks from any other**: one to open a switcher or the
  menu, one to choose.
- **Below 900 px** the navigation folds into one *Menu* disclosure at the top of the page,
  which names the current page beside it; the top bar keeps only the mark, *Help*, the
  bell and the account.
- *Planned differently from the plan's §5 Run 2 text*: the switchers sit at the top of the
  left navigation, not in the top bar. With one organisation and one project on Free,
  the switchers are a "where am I" label first and a control second; beside the page list
  they read as its heading, and the top bar stays short enough for a phone.

## 3. One page template

Every page, in this order: a **breadcrumb** (*Organisation / Project / Page*); the
**title** with a state chip where the page has a state; **one line saying what the page
is for**; on the right, **a help link** to the site page that documents it (ADR 0298) and
**the page's one primary action**. Then the content, in cards. A page that waits shows a
**skeleton** of its own shape (never a blank page and never *Loading…*); a page with
nothing to show has an **empty state** that names the next action.

## 4. Components (ADR 0295 decision 6)

| Component | Behaviour | Where the prototype shows it |
|---|---|---|
| Copy button | Copies the value; reads *Copied* for 2 s; announced once in the page's single `aria-live` region; if the clipboard refuses, the text is selected instead | Every code block; the support address |
| Busy button | Disabled, with a spinner and a label of what it is doing, until the request returns — a second click sends nothing | *Create project*, *Make a password*, *Run*, every Settings action |
| Code block | Dark panel, a file or context label, copy always | Connect, the token, the claim command |
| Shown-once panel | Amber border; says what the value is, whether you need it, and that it is shown once; closing it leaves a one-line record | The handoff token; a door's password |
| Tracker | Named steps, done / current / to come, each step's time, the whole's elapsed and typical time; an indeterminate bar on the current step, no percent | Creation, screens 3–4 |
| Banner | One per page, at the top: a limit that is near or reached, with its link | Projects, Notifications |
| Callout | A refusal or an explanation, with its actions as buttons and the API's word in small mono under it | New project while one is being created |
| Chip | State words from `STATE_CHIPS` (ADR 0288 unchanged): an unknown state never looks *Ready* | Project switcher, tables, titles |
| Tabs | Real tab semantics; one panel | Connect's clients |
| Segmented choice | Two cards as radio buttons, each with two lines of *use it for* | Connect's doors |
| Dialog | `<dialog>`, modal; destructive ones need the name typed | Delete project |
| Toast | Bottom-right, 3 s, also announced | Settings actions |
| Checklist | Steps with done / current / not yet; each read from the API | Projects page |
| Feed | Pip, sentence with a link, time | Activity, Notifications |

## 5. Tokens

The ADR 0288 block is unchanged and byte-equal. Session 47 adds, light only, three
colours for destructive actions (`--danger-text #8A2B16`, `--danger-bg #FBE9E4`,
`--danger-border #B5482F`) and `--nav-width 248px`. Run 9's `TEXT_PAIRS` holds every new
text pair at 4.5:1 or more (`#8A2B16` on `#FFFFFF` and on `#FBE9E4`; white on `#B5482F`).
**Light only** (D2946 (2)); a dark set would be one more block, not built.

## 6. The screens

1. **Projects, while a project is being created.** The pending project is a row, with
   its current step in words and *Follow*; the getting-started checklist shows *Create a
   project* as current; *New project* is disabled and the banner says why (*1 of 1,
   notes-app already counts*).
2. **New project.** Three fields with hints (the administrator is the project's own
   sign-in, not the console account); *What happens next*: **usually 23 to 28 minutes,
   most of it the first full backup**, you can close the page, Projects and Notifications
   will show it. Submitting disables the form and the button.
3. **Creation, just started.** The handoff token in a shown-once panel that says first
   **you do not need it to connect**; the terminal command behind a disclosure marked
   optional; *I've saved it, or I don't need it* leaves a one-line record. The tracker: the
   nine steps in plain words, each step's time, the current one with its own elapsed and
   typical time, *stops by itself after 30 min on one step*.
4. **The same page after a refresh.** Everything read again from the API; one sentence:
   the token was shown once and cannot be shown again, and you do not need it.
5. **New project while one is being created.** The refusal before the form: what is true
   (*Free holds one project and notes-app is being created*), what would change it, two
   actions, *nothing was recorded*, and the word `plan_limit_reached` in small type for
   support. (This is the person's second create, answered correctly — D2981.)
6. **Connect.** Three numbered steps: **choose a door** (pooled recommended, direct for
   migrations, dumps, `LISTEN`, advisory locks — both always exist); **make a password**
   (made in the browser, only its fingerprint sent, shown once, replacing the old one); **copy
   the code for your tool** — psql, Node (pg), Prisma, Drizzle, Python (psycopg), Go
   (pgx), `.env` — each saying **which file it goes in** and how to install the driver.
   The connection string's parts labelled. *No psql yet?* links to per-OS install pages
   and to the browser editor.
7. **SQL editor.** **The state bar at the top**: connected or not, door, user, database,
   *Disconnect*. While connected the credentials form is gone; while disconnected it is the
   only thing shown. A first statement that changes nothing is filled in; results show the
   row count and the time, with *Copy as CSV*; session limits stated beside *Run*.
8. **Notifications.** One sentence on what they are and that nothing is emailed; the
   latest, each a sentence with a link (*Follow it*, *Connect to it*, *See plans*); and
   **what makes a notification** — started, finished, asleep, expired, limit near.
9. **Project settings.** One row per setting, each saying what it does and its scope;
   every action a busy button with a toast that says where to follow it; the support
   bundle described (*no data or passwords*); delete in its own card, confirmed by typing
   the name.
10. **Help.** Ask a person (`invite@nomipg.com`, copyable), what to send (the key, what the
    page said and its word, a support bundle), never a password; the docs, by task.

## 7. The person's findings, each answered

Their notes' eleven *not on any page* items (D2936), then the rest of their feedback.

| # | The person's finding | Answered on | How |
|---|---|---|---|
| 1 | *What `apg project claim …` means* | 3 | Behind *Using it from a terminal (optional)*, after the sentence saying when you would |
| 2 | *What to do with the handoff token* | 3, 4 | *You do not need it to connect*, first; *shown once*; after a refresh, said again |
| 3 | *No loading state or progress tracker, only "backup (90%)"* | 3, 4 | Named steps, each time, elapsed and typical; no percent |
| 4 | *After a refresh no record; then `capacity_exhausted`* | 1, 4, 5 | The creation is read from the API (ADR 0296); the refusal is the plan's and says so (D2981) |
| 5 | *Overview said no project while one was being created* | 1 | A pending row with its step; the checklist's current item |
| 6 | *What the Notifications tab should show* | 8 | A sentence and the five kinds |
| 7 | *Connect: no steps for newcomers, for every OS* | 6 | Three steps; seven clients with the file and the install line; per-OS psql pages |
| 8 | *Generate password confusing; no copy for the pool string* | 6 | Step 2 explained; copy on every value |
| 9 | *SQL editor: what goes where; messages at the bottom; the password stays* | 7 | State bar at the top; form only while disconnected; the purpose line |
| 10 | *Didn't understand goal 2 ("your own SQL")* | 7 | The editor says *Run SQL you write yourself*; the walk's statement reworded (D2959) |
| 11 | *Didn't find any support page* | 10 | *Help* in the top bar on every page; the site's support page (ADR 0298) |
| — | *Input fields should disappear during creation* (double create) | 2, 1 | The form and button disabled while it runs; *New project* disabled while one is open |
| — | *No copied state, no auto-disable on buttons* | all | Copy and busy buttons everywhere |
| — | *Notifications when created and when finished* | 8 | *Started* (new, ADR 0297) and *Finished* |
| — | *A limit warning linking to pricing* | 1, 5, 8 | The banner and the refusal both link to the plans |
| — | *Connect, password and the editor together are confusing* | 6, 7 | Connect is the one place passwords are made; the editor points back to it |

## 8. Floors (Run 9 proves them)

WCAG 2.2 AA: text pairs ≥ 4.5:1; a visible 2 px focus ring on every control; every input
labelled; targets ≥ 24 px (controls are 32–44 px); state never by colour alone (chips and
steps carry words, and screen-reader text says *done / in progress / to come*);
`prefers-reduced-motion` stops the bar, the skeleton and the spinner. 390 and 1280 with no
page-level horizontal scroll (only code blocks and tables scroll, in their own boxes).

## 9. What the prototype does not decide

- **Snippets are the server's** (D2991): `connection_snippets.py` already serves psql,
  Prisma, node-pg and psycopg as rig 39c measured them; the prototype's psql, Prisma, Node
  and psycopg texts follow it. **Drizzle, Go (pgx) and `.env` are new and unmeasured**:
  Run 6 adds them to the server's module and executes each against a TLS rig before it
  ships (D2956). Which user each door shows comes from the `/v1` connection document.
- The other project pages (Branches, Backups, Usage, Slowest queries, Monitoring) and the
  organisation's (Activity, Plan and usage, Members and keys) keep their content and take
  the template, the components and the empty states; they are not drawn here.
- Numbers on screen are examples. *23 to 28 minutes* is the three measured creations
  (1,375.9 s, 1,565.5 s, 1,708.4 s); Run 3's `operation_steps` holds the served values.

## Approval

*(Sheet D1: the operator's words and the date go here; revisions are listed above them.)*

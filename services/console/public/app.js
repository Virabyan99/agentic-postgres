// The console's views (ADR 0280). Two pages share this file: `/accept`, where
// an invitation link becomes an account (ADR 0282), and `/console/`, whose
// views are fragment routes (`#/`, `#/projects/<key>/connect`, ...). The
// components are `ui.js`'s, the shell `nav.js`'s, the refusals' words
// `messages.js`'s, a long operation's progress `progress.js`'s (ADR 0295).
//
// Rules this file keeps, each held by tests/contract/test_console_pages.py:
// every value from the server is set with `textContent` or a DOM property,
// never parsed as markup; nothing is written to browser storage or cookies (the
// session is two HttpOnly cookies this code cannot read); a secret -- a
// password, a key, an invitation link, an export link, the factor's seed --
// lives in one view's variables, is shown once, and is never put in a URL or
// a fragment route. A feature the Ledger does not offer has no control here.

import { call, Refusal, relayOrigin } from "/console/api.js";
import { connectionString, csv, fillPassword, guide, parts, STRING_TAKEN_BY } from "/console/copies.js";
import { CLAIM_SENTENCE, claimLine, createProject } from "/console/create.js";
import { closeSentence, refusal, said, sentence, SESSION_LIMITS } from "/console/messages.js";
import { CREATE_ON_POOLED, DIRECT_DOOR_HINT, needsDirectDoor } from "/console/messages.js";
import { begin, current, frame, isCurrent, loadContext, mayCreate, narrow, PAGES, setPage, show, useActions } from "/console/nav.js";
import { connect } from "/console/pg.js";
import {
  checklist, checklistComplete, creationBlocked, CURRENT, describe, DONE, entitlementTitle, entitlementUse, entitlementValue,
  formatDuration, instantOf, limitText, NOT_NEEDED, NOT_READ, NOT_YET, noticeEntitlement, operationSeconds, plainNotice,
  recentNotices, STOPPED, stepStates, TERMINAL, typicalRange, usageRows, usageTotals, zoneName,
} from "/console/progress.js";
import { newPassword, verifier } from "/console/scram.js";
import { DEADLINE_SENTENCE, doors, openDoor, runStatement } from "/console/sql.js";
import {
  banner, busyButton, button, callout, card, cellChoice, choice, codeBlock, confirmDialog, copyButton, emptyState, field, h, inlineCopy, link, once,
  siteDomain, siteLink, skeleton, stateChip, table, tabs, value, when,
} from "/console/ui.js";

const KEY = /^[a-z][a-z0-9-]{1,62}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
// The server's BRANCH_PATTERN (services/auth-api/app/models.py); `main` is the project.
const BRANCH = /^[a-z][a-z0-9]{1,11}$/;
const ROLES = ["owner", "admin", "member", "viewer"];
const PROFILES = ["small", "standard", "large"];
const KEY_SCOPES = ["organizations:read", "members:read", "projects:read", "projects:write", "operations:read"];

// Each operation type in the customer's words: the tracker's title and the
// activity list's first column.
const OPERATION_TITLES = {
  "project.create": "Creating a project",
  "project.sleep": "Putting a project to sleep",
  "project.wake": "Waking a project",
  "project.resize": "Resizing a project",
  "project.export": "Exporting a database",
  "project.delete": "Deleting a project",
  "credential.rotate": "Setting a new password",
  "branch.create": "Creating a branch",
  "restore.create": "Restoring to a branch",
  "branch.reset": "Resetting a branch",
  "branch.delete": "Deleting a branch",
};

// An operation's status in words: the tracker's and the activity list's.
const OPERATION_STATUS = {
  pending: "Waiting to start", running: "Running", succeeded: "Finished", failed: "Failed", cancelled: "Cancelled",
};

// -- operations ----------------------------------------------------------------

function pause(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

// Reads the operation every 2 s until it is terminal, as `apg operation wait`,
// saying what it is doing in words -- never a percentage (ADR 0296). It stops,
// answering null, as soon as the person leaves the page (`turn`), so a page no
// one is reading reads nothing -- an export's link is taken by one read (D3005).
async function waitFor(operationId, status, turn) {
  for (;;) {
    const row = await call("GET", `/operations/${encodeURIComponent(operationId)}`);
    if (!isCurrent(turn)) {
      return null;
    }
    status.textContent = describe(row, Date.now());
    if (TERMINAL.has(row.status)) {
      return row;
    }
    await pause(2000);
    if (!isCurrent(turn)) {
      return null;
    }
  }
}

// The tracker of an operation started on this page, linked once it is recorded.
function followLink(operation) {
  return h("p", { className: "small" }, link(`#/operations/${operation.id}`, "Follow it on its own page"),
    "; it keeps going if you leave this one.");
}

// A finished operation that did not succeed, in the words of its error code
// (ADR 0297): what happened, what to do, the word in small type.
function outcome(row) {
  if (row.status === "succeeded") {
    return h("p", {}, "Done.");
  }
  if (row.status === "cancelled") {
    return h("p", { className: "refusal" }, "The operation was cancelled before it finished; nothing more will happen.");
  }
  if (typeof row.error_code === "string" && row.error_code) {
    return said(row.error_code, row.result);
  }
  return h("p", { className: "refusal" }, "The operation failed, and the server recorded no reason.");
}

// What an operation acts on, in a few words.
function subjectWords(row) {
  const subject = row.subject || {};
  if (typeof subject.name === "string") {
    return subject.name;
  }
  if (typeof subject.branch === "string") {
    return `${subject.branch} on ${value(row.project_key)}`;
  }
  return value(row.project_key);
}

// -- the second factor, shared by onboarding and sign-in --------------------

// Begins enrolment, shows the QR and the base32 text under it, confirms with a
// code. Resolves once confirmed: confirming ends every session (the server's
// rule), so the caller signs in again with the NEXT code.
function enrolFactor() {
  return new Promise((resolve) => {
    const status = h("div", {});
    narrow(h("h1", {}, "Set up your second factor"), status);
    call("POST", "/me/totp").then((enrolment) => {
      const [codeLabel, code] = field("Code from your app", {
        inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6,
      });
      const message = h("div", {});
      const confirm = busyButton("Confirm", async () => {
        message.replaceChildren();
        try {
          await call("POST", "/me/totp/confirm", { totp_code: code.value.trim() });
        } catch (error) {
          message.replaceChildren(refusal(error));
          return;
        }
        enrolment = null;
        resolve();
      }, { busy: "Confirming…" });
      status.replaceChildren(
        h("p", {}, "Scan this with your authenticator app, then enter the code it shows."),
        h("img", { src: enrolment.otpauth_qr, alt: "QR code for your authenticator app", className: "qr" }),
        h("p", {}, "Or type this key into the app: ", h("code", { className: "secret" }, enrolment.secret)),
        codeLabel, confirm, message,
      );
    }).catch((error) => status.replaceChildren(refusal(error)));
  });
}

async function signIn(username, password, totpCode) {
  const body = { username, password };
  if (totpCode) {
    body.totp_code = totpCode;
  }
  return call("POST", "/sessions", body);
}

// -- /accept: an invitation link becomes an account ---------------------------

async function acceptPage() {
  // The token leaves the address bar BEFORE the first request (ADR 0282): a
  // fragment is never sent, and now it is not in the history either.
  const token = location.hash.length > 1 ? location.hash.slice(1) : "";
  history.replaceState(null, "", "/accept");
  if (!/^[A-Za-z0-9_-]+$/.test(token)) {
    narrow(h("h1", {}, "Invitation"), h("p", {}, "This link holds no invitation. Open the link you were sent."));
    return;
  }
  let me = null;
  try {
    me = await call("GET", "/me");
  } catch (error) {
    me = null;
  }
  if (me) {
    joinAsSignedIn(token, me);
  } else {
    createAccount(token);
  }
}

function joinAsSignedIn(token, me) {
  const message = h("div", {});
  narrow(
    h("h1", {}, "Join with your account"),
    h("p", {}, "You are signed in as ", h("strong", {}, me.username), "."),
    busyButton("Join", async () => {
      try {
        await call("POST", "/invitations/accept", { invitation_token: token });
        location.assign("/console/");
      } catch (error) {
        message.replaceChildren(refusal(error));
      }
    }, { busy: "Joining…" }),
    message,
  );
}

function createAccount(token) {
  const [userLabel, username] = field("Username", { autocomplete: "username", required: true });
  const [displayLabel, display] = field("Display name", { autocomplete: "name" });
  const [passLabel, password] = field("Password", { type: "password", autocomplete: "new-password" });
  const [againLabel, again] = field("Password again", { type: "password", autocomplete: "new-password" });
  const message = h("div", {});
  const create = busyButton("Create your account", async () => {
    message.replaceChildren();
    if (password.value !== again.value) {
      message.replaceChildren(h("p", { className: "refusal" }, "The two passwords differ."));
      return;
    }
    const name = username.value.trim();
    const secret = password.value;
    try {
      await call("POST", "/invitations/accept", {
        invitation_token: token, username: name,
        display_name: display.value.trim() || name, password: secret,
      });
      await signIn(name, secret);
      const self = await call("GET", "/me");
      if (self.second_factor.required && !self.second_factor.enabled) {
        await enrolFactor();
        await signInWithNextCode(name, secret);
      }
    } catch (error) {
      message.replaceChildren(refusal(error));
      return;
    } finally {
      password.value = "";
      again.value = "";
    }
    location.assign("/console/");
  }, { busy: "Creating your account…" });
  narrow(
    h("h1", {}, "Create your account"),
    h("p", {}, "You were invited. Choose a username and a password."),
    userLabel, displayLabel, passLabel, againLabel, create, message,
  );
}

// After a factor is confirmed every session has ended; the next code signs in.
function signInWithNextCode(username, password) {
  return new Promise((resolve) => {
    const [codeLabel, code] = field("The next code from your app", {
      inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6,
    });
    const message = h("div", {});
    narrow(
      h("h1", {}, "Sign in"),
      h("p", {}, "Your second factor is on. Wait for the next code in your app and enter it."),
      codeLabel,
      busyButton("Sign in", async () => {
        try {
          await signIn(username, password, code.value.trim());
        } catch (error) {
          message.replaceChildren(refusal(error));
          return;
        }
        resolve();
      }, { busy: "Signing in…" }),
      message,
    );
  });
}

// -- /console/: sign-in, the views ---------------------------------------------

function signInView() {
  const [userLabel, username] = field("Username", { autocomplete: "username" });
  const [passLabel, password] = field("Password", { type: "password", autocomplete: "current-password" });
  const [codeLabel, code] = field("Code from your app", {
    inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6,
  });
  codeLabel.hidden = true;
  const message = h("div", {});
  narrow(
    h("h1", {}, "Sign in"),
    userLabel, passLabel, codeLabel,
    busyButton("Sign in", async () => {
      message.replaceChildren();
      try {
        await signIn(username.value.trim(), password.value, code.value.trim() || undefined);
      } catch (error) {
        if (error instanceof Refusal && error.code === "second_factor_required") {
          codeLabel.hidden = false;
        }
        message.replaceChildren(refusal(error));
        return;
      }
      password.value = "";
      location.hash = "#/";
      route();
    }, { busy: "Signing in…" }),
    message,
  );
}

async function signOut() {
  try {
    await call("DELETE", "/sessions/current");
  } finally {
    location.hash = "#/sign-in";
    route();
  }
}

useActions({ signOut });

// The organisation's creations still running (ADR 0296), or null when they
// could not be read -- said, never shown as none.
async function openCreations(organization) {
  try {
    const served = await call("GET", `/operations?organization=${encodeURIComponent(organization)}&status=open`);
    return (served.operations || []).filter((operation) => operation.type === "project.create");
  } catch (error) {
    return null;
  }
}

// What a creation is doing now, in a few words: its current step and how
// long it has run, and how long one usually takes.
function creationNow(operation) {
  const now = Date.now();
  const running = stepStates(operation, now).find((step) => step.state === CURRENT);
  const elapsed = formatDuration(operationSeconds(operation, now));
  const typical = typicalRange(operation.expected);
  return (running ? running.label : "Waiting to start") + (elapsed ? `, ${elapsed} so far` : "") +
    (typical ? `; usually ${typical}` : "");
}

// The next action of an organisation with no project (the brief's §3): create
// the first one when the person may and it can start now; the members page,
// which says who can, when they may not; nothing while a creation cannot start
// (the page says why beside New project). Its name differs from New project,
// the page's own action, so each link names one control.
function firstProjectAction(organization, blocked) {
  if (!organization) {
    return null;
  }
  if (!mayCreate(organization)) {
    return link(`#/org/${organization.id}/settings`, "See who can create one");
  }
  return blocked ? null : link(`#/org/${organization.id}/new-project`, "Create your first project");
}

// An organisation's projects, and the ones being created, as one table; with
// neither, an empty state with `next`, the action that makes the first.
function projectList(projects, creating, next) {
  const rows = [
    ...(creating || []).map((operation) => ({
      project: h("span", {}, h("strong", {}, subjectWords(operation)),
        h("span", { className: "small muted sub" }, "Being created: " + creationNow(operation))),
      state: stateChip("creating"),
      profile: value((operation.subject || {}).profile),
      open: link(`#/operations/${operation.id}`, "Follow"),
    })),
    ...projects.map((project) => ({
      project: link(`#/projects/${project.key}`, project.key),
      state: stateChip(project.state),
      profile: value(project.profile),
      open: link(`#/projects/${project.key}/connect`, "Connect"),
    })),
  ];
  return [
    rows.length
      ? table([["project", "Project"], ["state", "State"], ["profile", "Size"], ["open", ""]], rows)
      : emptyState("No project yet. A project is a PostgreSQL database with two connection doors, backed up from the start.", next),
    creating === null ? h("p", { className: "muted" }, "Projects being created could not be read just now.") : null,
  ];
}

// The organisation's plan document, or null when it could not be read.
function readPlan(organization) {
  return call("GET", `/organizations/${organization}/plan`).catch(() => null);
}

// One organisation's readings for its Projects page, each read from the API on
// every load (ADR 0296, ADR 0298): its projects (a refusal of these refuses the
// page), its open creations, its plan, all its operations and its projects'
// usage over the longest window the API serves. Each of the last four is null
// when it could not be read -- said by what draws it, never shown as none.
async function readOrganization(organization) {
  const id = encodeURIComponent(organization);
  const [projects, creating, plan, operations, usage] = await Promise.all([
    call("GET", "/projects?organization=" + id).then((served) => served.projects || []),
    openCreations(organization),
    readPlan(organization),
    call("GET", "/operations?organization=" + id).then((served) => served.operations || []).catch(() => null),
    call("GET", `/organizations/${organization}/usage?hours=720`).then((served) => served.projects || []).catch(() => null),
  ]);
  return { projects, creating, plan, operations, usage };
}

function planName(plan) {
  const name = plan && typeof plan.plan === "string" ? plan.plan : "";
  return name ? name.charAt(0).toUpperCase() + name.slice(1) : "Your";
}

function count(number, word, words) {
  return `${number} ${number === 1 ? word : words}`;
}

// The links every limit says: the site's plans and the organisation's own page.
function planLinks(organization) {
  return [h("a", { href: siteLink("/pricing/") }, "See plans"), " · ", h("a", { href: `#/org/${organization}/plan` }, "Your plan")];
}

// A limit the customer can see coming (ADR 0297 decision 6): from the plan's
// `projects_active` alone, when it is full or one short of full.
function projectLimitBanner(organization, plan, creating) {
  const counted = plan && plan.projects_active;
  if (!counted || typeof counted.held !== "number" || typeof counted.limit !== "number") {
    return null;
  }
  const { held, limit } = counted;
  if (held < limit && !(limit > 1 && held === limit - 1)) {
    return null;
  }
  const open = (creating || []).find((operation) => operation.subject && typeof operation.subject.name === "string");
  let why = "One more project fills it.";
  if (held >= limit) {
    why = open
      ? `${open.subject.name} is being created, so it already counts. A new project cannot start.`
      : "A new project cannot start until one is deleted, or on a plan with more projects.";
  }
  return banner(h("strong", {}, `${planName(plan)} plan: ${held} of ${count(limit, "project", "projects")}.`), " ", why, " ",
    planLinks(organization));
}

function isFull(blocked) {
  return blocked.held !== null && blocked.limit !== null && blocked.held >= blocked.limit;
}

// Why New project cannot start now (D2951), in a sentence.
function blockedWords(blocked, plan) {
  const name = blocked.name || "A project";
  if (blocked.reason === "creating" && isFull(blocked)) {
    return `${planName(plan)} plan holds ${count(blocked.limit, "project", "projects")}, and ${name} is being created.`;
  }
  if (blocked.reason === "creating") {
    return `${name} is being created. Another project can start once it has finished.`;
  }
  return `${planName(plan)} plan holds ${count(blocked.limit, "project", "projects")}, and all of them are in use.`;
}

// The New project action of an organisation the person may create in: a link,
// or -- while a creation is open or the plan is full -- a disabled button that
// says why beside it.
function newProjectAction(organization, blocked, plan) {
  if (!organization || !["owner", "admin", "member"].includes(organization.role)) {
    return null;
  }
  if (blocked) {
    return h("button", { type: "button", disabled: true, title: blockedWords(blocked, plan) }, "New project");
  }
  return link(`#/org/${organization.id}/new-project`, "New project");
}

// -- the getting-started checklist (ADR 0298 decision 4) ----------------------

const CHECKLIST_TITLES = {
  factor: "Turn on a second factor",
  organization: "Join or create an organisation",
  project: "Create a project",
  password: "Make a password for a door",
  connection: "Connect your application",
};
const CHECK_WORDS = {
  [DONE]: "done", [CURRENT]: "in progress", [NOT_YET]: "not yet", [NOT_READ]: "not read",
  [NOT_NEEDED]: "not required for your role",
};
// Each state's mark, so no state is told by its colour alone (the brief's §8).
const CHECK_MARKS = { [DONE]: "✓", [NOT_NEEDED]: "–" };

// What one item says under its title, and where it leads.
function checkDetail(item, state, me, organizations, readings) {
  const projects = readings.flatMap((reading) => reading.projects || []);
  const creating = readings.flatMap((reading) => reading.creating || []);
  if (state === NOT_READ) {
    return ["Not read just now; this page reads it again when you open it.", null];
  }
  if (item === "factor") {
    if (state === DONE) {
      return ["On", null];
    }
    if (state === NOT_NEEDED) {
      return ["Not required for your role.", null];
    }
    return [me.second_factor && me.second_factor.required ? "Your role needs one; the console asks for it when you sign in." : "Not on. The console asks for one when your role needs it.", null];
  }
  if (item === "organization") {
    if (state === DONE) {
      return [organizations.map((organization) => organization.name).join(", "), null];
    }
    return ["Accept an invitation, or make your own.", link("#/new", "Create one")];
  }
  if (item === "project") {
    if (state === DONE) {
      return [projects.map((project) => project.key).join(", "), null];
    }
    if (state === CURRENT) {
      const first = creating[0];
      return [`${subjectWords(first)} is being created`, link(`#/operations/${first.id}`, "Follow")];
    }
    const where = organizations.find((organization) => mayCreate(organization));
    return ["Not yet.", where ? link(`#/org/${where.id}/new-project`, "New project") : null];
  }
  if (item === "password") {
    if (state === DONE) {
      return ["Made", null];
    }
    const ready = projects.find((project) => project.state === "ready");
    return ready ? ["Not yet.", link(`#/projects/${ready.key}/connect`, "Connect")] : ["Once the project is ready.", null];
  }
  if (state === DONE) {
    return ["Seen", null];
  }
  return ["Not seen yet.", h("a", { href: siteLink("/docs/connecting/") }, "How")];
}

// From the invitation to a connected application, each step read from the API
// on this load -- the same on any device; nothing is remembered in the tab. Gone
// once every step is done.
function checklistCard(me, organizations, readings) {
  const states = checklist({
    me, organizations,
    projects: readings.map((reading) => reading.projects),
    creating: readings.map((reading) => reading.creating),
    operations: readings.map((reading) => reading.operations),
    usage: readings.map((reading) => reading.usage),
  });
  if (checklistComplete(states)) {
    return null;
  }
  return card(h("h2", {}, "Getting started"),
    h("p", { className: "small muted" }, "From your invitation to a connected application. Each step is read from your account, so it is the same on any device."),
    h("ol", { className: "checklist" }, states.map(({ item, state }) => {
      const [detail, action] = checkDetail(item, state, me, organizations, readings);
      return h("li", { className: state === DONE ? "done" : state === CURRENT ? "current" : state === NOT_READ ? "unread" : state === NOT_NEEDED ? "skip" : "todo" },
        h("span", { className: "mark", "aria-hidden": "true" }, CHECK_MARKS[state] || ""),
        h("div", {}, h("strong", {}, CHECKLIST_TITLES[item]), h("span", { className: "sr" }, `, ${CHECK_WORDS[state]}`),
          h("span", { className: "sub" }, detail)),
        action || h("span", {}));
    })));
}

// One organisation on the Projects page: its limit, its projects and the ones
// being created, and what can be done next.
function organizationSection(organization, reading) {
  const blocked = creationBlocked(reading);
  return h("section", { className: "card" },
    h("h2", {}, organization.name, " ", h("small", {}, organization.role)),
    projectLimitBanner(organization.id, reading.plan, reading.creating),
    projectList(reading.projects, reading.creating, firstProjectAction(organization, blocked)),
    h("p", { className: "card-actions" },
      newProjectAction(organization, blocked, reading.plan),
      link(`#/org/${organization.id}`, "Open this organisation")),
    blocked && !isFull(blocked) && mayCreate(organization) ? h("p", { className: "small muted" }, blockedWords(blocked, reading.plan)) : null);
}

async function overview(me, turn) {
  const organizations = (await call("GET", "/organizations")).organizations;
  const readings = await Promise.all(organizations.map((organization) => readOrganization(organization.id)));
  if (!isCurrent(turn)) {
    return;
  }
  frame(me, "Projects", { action: link("#/new", "New organisation") },
    checklistCard(me, organizations, readings),
    organizations.length === 0
      ? emptyState("You belong to no organisation yet. Ask for an invitation, or make one.", link("#/new", "New organisation"))
      : organizations.map((organization, index) => organizationSection(organization, readings[index])),
  );
}

async function organizationView(me, org, turn) {
  const reading = await readOrganization(org);
  if (!isCurrent(turn)) {
    return;
  }
  const here = current().organization;
  const blocked = creationBlocked(reading);
  frame(me, "Projects", { action: newProjectAction(here, blocked, reading.plan) },
    projectLimitBanner(org, reading.plan, reading.creating),
    blocked && !isFull(blocked) && mayCreate(here) ? h("p", { className: "muted" }, blockedWords(blocked, reading.plan)) : null,
    checklistCard(me, current().organizations, [reading]),
    card(projectList(reading.projects, reading.creating, firstProjectAction(here, blocked))),
    h("p", {}, link(`#/org/${org}/activity`, "Everything that happened in this organisation")));
}

// The next action of an organisation whose activity or notifications are
// empty: to start the first operation there is to create a project.
function firstOperationAction(org) {
  const here = current().organization;
  return here && mayCreate(here)
    ? link(`#/org/${org}/new-project`, "Create a project")
    : link(`#/org/${org}`, "See the projects");
}

async function activityView(me, org) {
  const served = await call("GET", "/operations?organization=" + encodeURIComponent(org));
  const rows = (served.operations || []).map((operation) => ({
    when: when(operation.created_at),
    what: OPERATION_TITLES[operation.type] || value(operation.type),
    subject: subjectWords(operation),
    status: OPERATION_STATUS[operation.status] || value(operation.status),
    open: link(`#/operations/${operation.id}`, TERMINAL.has(operation.status) ? "Details" : "Follow"),
  }));
  frame(me, "Activity",
    rows.length
      ? card(table([["when", "When"], ["what", "What"], ["subject", "On"], ["status", "Status"], ["open", ""]], rows))
      : emptyState("Nothing has happened in this organisation yet. Creating a project, a branch or a password each appears here as an operation you can follow.",
        firstOperationAction(org)));
}

// The tracker's content for one reading of the operation: the steps, done /
// current / to come, with the time each took; the whole's elapsed and typical
// time; the server's limit; the outcome once it is over.
// A step's usual time, in words.
function usually(seconds) {
  return seconds < 1 ? "usually under a second" : `usually about ${formatDuration(seconds)}`;
}

// Where a finished operation leads (the brief's screens 3-4): a created
// project to Connect -- and, optionally, the claim with its key -- a deleted
// one back to the projects, an export to its link (shown once: the requester's
// read takes it, D3005), the rest to what they changed.
function onward(row) {
  if (row.status !== "succeeded") {
    return [outcome(row)];
  }
  const key = row.project_key;
  if (row.type === "project.create") {
    return [h("p", {}, "Your project ", h("code", {}, value(key)), " is ready. ", link(`#/projects/${key}/connect`, "Connect to it")),
      h("p", { className: "small muted" }, "Optional: to claim its administrator from a terminal, run ", h("code", {}, claimLine(key)), ".")];
  }
  if (row.type === "project.delete") {
    return [h("p", {}, "The project was deleted. ", link("#/", "Back to your projects"))];
  }
  if (row.type === "project.export") {
    return typeof row.download_url === "string"
      ? [h("p", {}, "The export is ready."), once("The download link:", row.download_url)]
      : [h("p", {}, "The export is ready. Its download link was shown once, to the page that asked for it.")];
  }
  if (row.type === "credential.rotate") {
    return [h("p", {}, "The new password is set. ", link(`#/projects/${key}/connect`, "Go to Connect"))];
  }
  if ((typeof row.type === "string" && row.type.startsWith("branch.")) || row.type === "restore.create") {
    return [h("p", {}, "Done. ", link(`#/projects/${key}/branches`, "See the branches"))];
  }
  return [h("p", {}, "Done. ", key ? link(`#/projects/${key}`, "Open the project") : null)];
}

// The tracker's content for one reading of the operation: the steps, done /
// current / to come, each with its time; the whole's start, elapsed and typical
// time; the server's bound (D3000); the outcome once it is over. No percentage
// anywhere: the current step has an indeterminate bar (ADR 0296 decision 5).
// `shownHere` is true on the page that showed a creation's token; anywhere
// else the tracker says once that it was shown and is not needed (decision 6).
function trackerParts(row, shownHere) {
  const now = Date.now();
  const states = stepStates(row, now);
  const elapsed = formatDuration(operationSeconds(row, now));
  const typical = typicalRange(row.expected);
  const limit = limitText(row.expected);
  const over = TERMINAL.has(row.status);
  const began = row.started_at || row.created_at || null;
  const words = { [DONE]: "done", [CURRENT]: "in progress", [STOPPED]: "stopped here", "to come": "to come" };
  const steps = states.map((step) => {
    let time = "";
    if (step.state === CURRENT) {
      time = (step.seconds !== null ? `about ${formatDuration(step.seconds)} so far` : "just started") +
        (step.typical_seconds !== null ? `, ${usually(step.typical_seconds)}` : "");
    } else if ((step.state === DONE || step.state === STOPPED) && step.seconds !== null) {
      time = formatDuration(step.seconds);
    } else if (step.state === "to come" && step.typical_seconds !== null) {
      time = usually(step.typical_seconds);
    }
    return h("li", { className: step.state === "to come" ? "todo" : step.state },
      h("span", { className: "mark", "aria-hidden": "true" }, step.state === DONE ? "✓" : step.state === STOPPED ? "!" : ""),
      h("div", {}, h("strong", {}, step.label), h("span", { className: "sr" }, `, ${words[step.state]}`),
        step.state === CURRENT ? h("div", { className: "indeterminate", "aria-hidden": "true" }) : null),
      h("span", { className: "time" }, time));
  });
  return [
    row.type === "project.create" && !shownHere
      ? callout("", null, h("p", {}, h("strong", {}, "The handoff token was shown once, when the creation started, and cannot be shown again."),
        " You do not need it to connect."))
      : null,
    card(h("p", { className: "meta-row" },
      h("span", {}, h("b", {}, OPERATION_STATUS[row.status] || value(row.status))),
      h("span", {}, "On ", h("b", {}, subjectWords(row))),
      began ? h("span", {}, "Started ", h("b", {}, when(began, "absolute"))) : null,
      elapsed ? h("span", {}, over ? "Took about " : "Running for about ", h("b", {}, elapsed)) : null,
      typical ? h("span", {}, "Usually ", h("b", {}, typical)) : null),
    limit && !over ? h("p", { className: "small muted" }, `If it has not finished ${limit} after it started, the server stops it.`) : null),
    states.length
      ? card(h("h2", {}, "Steps"), h("ol", { className: "steps" }, steps))
      : row.step ? h("p", {}, "Step: ", h("code", {}, row.step)) : null,
    over ? onward(row) : null,
  ];
}

// Reads the operation every 2 s while the page that shows it is current, and
// redraws the tracker from each reading; the last reading is answered. A read
// that fails is said and tried again -- never drawn as a state.
async function follow(id, turn, parts, first) {
  let row = first || null;
  for (;;) {
    if (row) {
      parts.tracker.replaceChildren(...trackerParts(row, parts.shownHere).flat().filter(Boolean));
      if (TERMINAL.has(row.status)) {
        return row;
      }
      await pause(2000);
    }
    if (!isCurrent(turn)) {
      return row;
    }
    try {
      row = await call("GET", `/operations/${encodeURIComponent(id)}`);
      parts.note.textContent = "";
    } catch (error) {
      parts.note.textContent = "The operation could not be read just now; this page tries again in two seconds.";
      if (!row) {
        await pause(2000);
      }
    }
    if (!isCurrent(turn)) {
      return row;
    }
  }
}

// `#/operations/<id>` (ADR 0296 decision 5): read from the API on every load,
// then every 2 s while it runs and this page is open. Nothing is kept that a
// refresh could lose.
async function operationView(me, id, turn) {
  const row = await call("GET", `/operations/${encodeURIComponent(id)}`);
  // A creation names its slot's key before the project is registered: until it
  // succeeds there is no project to read, only its organisation (D3005).
  const creating = row.type === "project.create" && row.status !== "succeeded";
  await loadContext(call, { organization: row.organization_id, projectKey: creating ? null : row.project_key });
  if (!isCurrent(turn)) {
    return;
  }
  setPage("operation");
  const parts = { tracker: h("div", { className: "stack" }), note: h("p", { className: "muted" }), shownHere: false };
  frame(me, OPERATION_TITLES[row.type] || "Operation", parts.tracker, parts.note);
  await follow(id, turn, parts, row);
}

function newOrganization(me) {
  const [nameLabel, name] = field("Name", { maxLength: 64 });
  const message = h("div", {});
  frame(me, "New organisation", card(nameLabel,
    busyButton("Create", async () => {
      try {
        const created = await call("POST", "/organizations", { name: name.value.trim() });
        location.hash = `#/org/${created.id}/settings`;
      } catch (error) {
        message.replaceChildren(refusal(error));
      }
    }, { busy: "Creating…" }), message));
}

// The handoff token's panel (ADR 0291; ADR 0296 decision 6; the brief's
// screen 3): what the token is, that it is NOT needed to connect, that it is
// shown once; the terminal claim behind a disclosure marked optional. Closing
// it replaces the whole panel -- the token with it -- by a one-line record.
function tokenPanel(token, administrator) {
  const panel = h("section", { className: "token-panel" },
    h("h2", {}, "Save the administrator's handoff token now, if you want it"),
    h("p", {}, "This token lets someone using the command line take over the project's administrator account",
      administrator ? [" (", h("code", {}, administrator), ")"] : null, ". ",
      h("strong", {}, "You do not need it to connect"), ", from the console or from your application. ",
      "It is shown once, now, and never again."),
    once("The handoff token:", token),
    h("details", {},
      h("summary", {}, "Using it from a terminal (optional)"),
      h("p", { className: "small" }, CLAIM_SENTENCE),
      codeBlock(claimLine(null), { label: "Terminal" })),
    h("p", {}, button("I've saved it, or I don't need it", () => panel.replaceWith(
      h("p", { className: "once-done" }, "The handoff token was shown once and is not shown again. You do not need it to connect.")))));
  return panel;
}

// Why New project cannot start here now (the brief's screen 5): the refusal
// the server would give, said before the form, with what would change it.
function blockedCallout(org, blocked, plan) {
  const full = isFull(blocked);
  return callout("warn", blockedWords(blocked, plan),
    h("p", {}, full
      ? `A new project can start once ${blocked.reason === "creating" ? blocked.name || "it" : "one"} is deleted, or on a plan with more projects. Nothing was recorded.`
      : "A new project can start once the creation has finished. Nothing was recorded."),
    h("p", { className: "card-actions" },
      blocked.operation ? link(`#/operations/${blocked.operation}`, `Follow ${blocked.name || "it"}`) : null,
      planLinks(org)),
    full ? h("p", {}, h("code", { className: "word" }, "plan_limit_reached")) : null);
}

// Session 46 (ADR 0291), Session 47 (ADR 0296, ADR 0297): a project created
// here. The form is refused before it is filled while the organisation has a
// creation open or its plan full (D2951); the fields and the button are
// disabled while the request runs. The token is made and digested by
// create.js; it reaches this view only through `accepted`, the moment the
// creation is recorded -- before the ~25-minute wait. Then the address becomes
// the creation's tracker (`#/operations/<id>`, without a new route turn, so a
// refresh resumes it from the API) and the token is drawn once, in its panel,
// above the tracker; it is dropped with the panel.
async function newProjectView(me, org, turn) {
  const [plan, creating] = await Promise.all([readPlan(org), openCreations(org)]);
  if (!isCurrent(turn)) {
    return;
  }
  const blocked = creationBlocked({ creating, plan });
  const [nameLabel, name] = field("Name", { maxLength: 48 }, "Letters, digits, spaces, dots, dashes and underscores. Only your organisation sees it.");
  const [profileLabel, profile] = choice("Profile", PROFILES, "small");
  const [adminLabel, admin] = field("Administrator's username", { maxLength: 63, autocomplete: "off" },
    "The first user of the project's own sign-in (its API), not your console account.");
  const inputs = [name, profile, admin];
  const message = h("div", {});
  const parts = { tracker: h("div", { className: "stack" }, skeleton()), note: h("p", { className: "muted" }), shownHere: true };
  const create = busyButton("Create project", async () => {
    message.replaceChildren();
    inputs.forEach((input) => { input.disabled = true; });
    try {
      await createProject({
        call,
        wait: (id) => follow(id, turn, parts, null),
        accepted: (token, operation) => {
          history.pushState(null, "", `#/operations/${operation.id}`);
          setPage("operation");
          frame(me, OPERATION_TITLES["project.create"], tokenPanel(token, admin.value.trim()), parts.tracker, parts.note);
        },
        organization: org,
        name: name.value.trim(),
        profile: profile.value,
        adminUsername: admin.value.trim(),
      });
    } catch (error) {
      inputs.forEach((input) => { input.disabled = false; });
      message.replaceChildren(refusal(error, { organization: org }));
    }
  }, { busy: "Starting the creation…" });
  if (blocked) {
    inputs.forEach((input) => { input.disabled = true; });
    create.disabled = true;
  }
  frame(me, "New project",
    projectLimitBanner(org, plan, creating),
    blocked ? blockedCallout(org, blocked, plan) : null,
    card(nameLabel, profileLabel, h("p", { className: "small muted" }, "You can change the size later, in the project's Settings."),
      adminLabel, create, message),
    card(h("h2", {}, "What happens next"),
      h("p", {}, "A new project takes a while: most of it is the first full backup, which makes sure your data can be restored from the start. ",
        "The page shows each step, and how long it usually takes, as soon as the creation is recorded."),
      h("p", {}, "You can close the page. The project shows on ", link(`#/org/${org}`, "Projects"), " while it is being created, and ",
        link(`#/org/${org}/notifications`, "Notifications"), " says when it started and when it finished.")));
}

// -- a project's views --------------------------------------------------------

async function projectOverviewView(me, key) {
  const project = await call("GET", `/projects/${key}`);
  const pages = [["connect", "/connect"], ["sql-editor", "/sql"], ["branches", "/branches"], ["backups", "/backups"],
    ["project-usage", "/usage"], ["insights", "/insights"], ["monitoring", "/monitoring"], ["project-settings", "/settings"]];
  frame(me, "Overview", { chip: stateChip(project.state), action: link(`#/projects/${key}/connect`, "Get the connection string") },
    card(h("dl", { className: "facts" },
      h("div", {}, h("dt", {}, "Key"), h("dd", {}, inlineCopy(key))),
      h("div", {}, h("dt", {}, "Size"), h("dd", {}, value(project.profile))),
      h("div", {}, h("dt", {}, "Region"), h("dd", {}, value(project.region))),
      h("div", {}, h("dt", {}, "Release"), h("dd", {}, value(project.template_version))))),
    card(h("ul", { className: "links" }, pages.map(([page, suffix]) => h("li", {},
      h("a", { href: `#/projects/${key}${suffix}` }, PAGES[page].label), h("span", { className: "muted" }, " — " + PAGES[page].purpose))))));
}

// -- Connect (D2956, D2991; the brief's screen 6) -------------------------------
//
// Three steps: choose a door, make its password, copy the code for your tool.
// Rules held by tests/contract/test_console_connect.py: every value drawn here
// carries its copy control (`inlineCopy`, `codeBlock`), never a bare `code`;
// the snippets are the server's, drawn as served and in the order served; and
// the password is filled into them only inside the shown-once panel
// (`heldCode`), from the rotation that made it, and leaves with that panel.

// Each door: its title, the role a new password is made for (ADR 0269), its
// step-2 button and the shown-once panel's heading (both read by the walk
// drivers), and two lines of what to use it for (drawn fresh on every visit).
const DOOR_WORDS = {
  pooled: {
    title: "Pooled", role: "customer_app",
    make: "Make a new password for the pooled door", made: "Your new password for the pooled door",
    uses: () => ["For your application: many short connections share a few to the database.",
      "Use it for web servers, serverless functions, scripts and other application traffic."],
  },
  direct: {
    title: "Direct", role: "customer_admin",
    make: "Make a new password for the direct door", made: "Your new password for the direct door",
    uses: () => ["One session per connection, kept for as long as you hold it.",
      ["Use it for migrations, ", h("code", {}, "pg_dump"), ", ", h("code", {}, "LISTEN"), ", advisory locks and long analytics."]],
  },
};

// A served client's name as a tab says it; a client this table does not name
// is shown by its own name, never dropped.
const CLIENT_LABELS = {
  "psql": "psql", "prisma": "Prisma", "node-pg": "Node (pg)", "psycopg": "Python (psycopg)",
  "drizzle": "Drizzle", "go-pgx": "Go (pgx)", "env": ".env",
};

function clientLabel(client) {
  return Object.hasOwn(CLIENT_LABELS, client) ? CLIENT_LABELS[client] : client;
}

// Which file the code goes in and what to install, when the server says (its `where`).
function guideLine(served, client) {
  const found = guide(served, client);
  if (!found) {
    return null;
  }
  if (found.text) {
    return h("p", { className: "where" }, found.text);
  }
  return h("p", { className: "where" },
    found.file ? h("span", {}, h("strong", {}, "Where it goes: "), found.file) : null,
    found.install ? h("span", {}, h("strong", {}, "What to install: "), found.install) : null);
}

// The server's snippets as served: the placeholder where a password goes.
function snippetTabs(served) {
  const clients = Object.keys(served.snippets || {});
  if (!clients.length) {
    return emptyState("The server serves no code for this project's doors; the connection string below works with any PostgreSQL client.",
      h("a", { href: siteLink("/docs/connecting/") }, "Connecting, in the documentation"));
  }
  return tabs(clients.map((client) => ({
    label: clientLabel(client),
    panel: [codeBlock(served.snippets[client], { label: clientLabel(client) }), guideLine(served, client)],
  })), "Your tool");
}

// The same snippets with a door's new password, inside the shown-once panel
// only: each placeholder of THIS door filled (copies.js decides which), the
// others left as served.
function heldCode(served, name, password) {
  const user = served[name].user;
  const others = ["pooled", "direct"].filter((other) => other !== name).map((other) => served[other].user);
  const clients = Object.keys(served.snippets || {});
  return h("div", { className: "held" },
    h("p", {}, h("strong", {}, `This code holds your new ${name} password.`), " Copy what you need now: it is shown once, and leaves when you leave this page."),
    tabs(clients.map((client) => {
      const text = fillPassword(served.snippets[client], { placeholder: served.password, user, others, password });
      const holds = text !== served.snippets[client];
      return {
        label: clientLabel(client),
        panel: [codeBlock(text, { label: holds ? `${clientLabel(client)}, with the password` : clientLabel(client), secret: holds }),
          guideLine(served, client)],
      };
    }), "Your tool, with the new password"));
}

// The names a list holds, as a sentence: "A, B and C".
function listed(names) {
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : names.join("");
}

// Beside the connection string (D3019): the served clients that take it as it
// is -- `STRING_TAKEN_BY`, measured by executing it -- and every other served
// client pointed to its own tab in step 3.
function stringNote(served) {
  const clients = Object.keys(served.snippets || {});
  const takers = clients.filter((client) => STRING_TAKEN_BY.includes(client)).map(clientLabel);
  const others = clients.filter((client) => !STRING_TAKEN_BY.includes(client)).map(clientLabel);
  return h("p", { className: "small" },
    takers.length ? h("strong", {}, `This string works as it is with ${listed(takers)}.`) : null,
    others.length ? ` For ${listed(others)}, copy the code from its own tab in step 3: this string is not enough for them.` : null);
}

// What a door's connection string is made of, each part with its copy control.
function doorAnatomy(served, name) {
  const door = served[name];
  return h("div", { className: "stack" },
    codeBlock(connectionString(door), { label: `The ${name} door, without its password` }),
    stringNote(served),
    h("dl", { className: "parts" }, parts(door).map((part) => h("div", {},
      h("dt", {}, part.label, h("span", { className: "sub" }, part.about)),
      h("dd", {}, inlineCopy(part.value))))),
    h("p", { className: "small muted" }, "The password goes after the user: ",
      h("code", {}, "postgresql://user:password@host:port/database"), ". Make one in step 2."));
}

// Step 2 for one door: what making a password does, the busy button, and the
// shown-once panel when it is made. The rotation is the one the CLI makes
// (ADR 0269): the password is made here, only its SCRAM verifier is sent.
function doorPassword(key, served, name, turn, held, refresh) {
  const door = served[name];
  const answer = h("div", { className: "stack" });
  const make = async () => {
    const status = h("p", { className: "muted" }, "Setting a new password…");
    answer.replaceChildren(status);
    held.replaceChildren();
    refresh();
    let password = newPassword();
    try {
      const accepted = await call("POST", `/projects/${key}/credentials`, { role: DOOR_WORDS[name].role, verifier: await verifier(password) });
      // No link to the tracker here: the password is shown on THIS page once the
      // rotation succeeds, and a person who left would never see it.
      const final = await waitFor(accepted.operation.id, status, turn);
      if (final === null) {
        return;
      }
      if (final.status !== "succeeded") {
        answer.replaceChildren(outcome(final));
        return;
      }
      const forget = async () => {
        held.replaceChildren();
        answer.replaceChildren(h("p", { className: "once-done" },
          `The ${name} door's password was shown once and is not shown again. If it is lost, make a new one.`));
        refresh();
      };
      answer.replaceChildren(h("div", { className: "once" },
        h("h3", {}, DOOR_WORDS[name].made),
        h("p", {}, "Copy it now, into your password manager or your application's settings.",
          h("strong", {}, " Shown once: this page forgets it when you leave, and it cannot be shown again."),
          " The previous password no longer works."),
        codeBlock(password, { label: `Password for ${door.user}`, secret: true }),
        codeBlock(connectionString(door, password), { label: "The connection string with it", secret: true }),
        stringNote(served),
        h("p", { className: "small" }, "It is filled into the code in step 3 for as long as this page stays open."),
        busyButton("I have saved the password", forget, { busy: "Forgetting it…" })));
      held.replaceChildren(heldCode(served, name, password));
      refresh();
    } catch (error) {
      answer.replaceChildren(refusal(error));
    } finally {
      password = null;
    }
  };
  return h("div", { className: "stack" },
    busyButton(DOOR_WORDS[name].make, make, { busy: "Making the password…" }),
    h("p", { className: "small muted" }, "The door's user: ", inlineCopy(door.user)),
    answer);
}

async function connectView(me, key, turn) {
  const served = await call("GET", `/projects/${key}/connections`);
  const names = ["pooled", "direct"];
  let chosen = "pooled";
  const plain = snippetTabs(served);
  const perDoor = {};
  // Only the chosen door's step 2 and anatomy are shown; step 3 shows the
  // door's shown-once code while the page holds a new password, else the
  // snippets as served. Choosing a door changes nothing anywhere but here.
  const refresh = () => {
    for (const name of names) {
      perDoor[name].password.hidden = name !== chosen;
      perDoor[name].anatomy.hidden = name !== chosen;
      perDoor[name].held.hidden = name !== chosen || !perDoor[name].held.firstChild;
    }
    plain.hidden = Boolean(perDoor[chosen].held.firstChild);
  };
  for (const name of names) {
    const held = h("div", {});
    perDoor[name] = { held, password: doorPassword(key, served, name, turn, held, refresh), anatomy: doorAnatomy(served, name) };
  }
  const segment = h("div", { className: "segment", role: "radiogroup", "aria-label": "Door to show" },
    names.map((name) => h("label", {},
      h("input", { type: "radio", name: "door", value: name, checked: name === chosen, onchange: () => { chosen = name; refresh(); } }),
      h("span", { className: "title" }, DOOR_WORDS[name].title, name === "pooled" ? h("span", { className: "chip state-ready" }, "Recommended") : null),
      DOOR_WORDS[name].uses().map((line) => h("span", { className: "desc" }, line)))));
  refresh();
  frame(me, "Connect",
    card(h("ol", { className: "steps-num" },
      h("li", {}, h("div", {},
        h("h2", {}, "Choose a door"), segment,
        h("p", { className: "small muted" }, "Both doors always exist, both with TLS. Choosing one only changes what this page shows."))),
      h("li", {}, h("div", {},
        h("h2", {}, "Make a password for this door"),
        h("p", { className: "small" }, "Your browser makes the password; only its fingerprint (a SCRAM verifier) is sent, so the platform never holds it. It is shown once. Making a new one replaces the old one, and connections using the old one stop working."),
        names.map((name) => perDoor[name].password))),
      h("li", {}, h("div", {},
        h("h2", {}, "Copy the code for your tool"), plain, names.map((name) => perDoor[name].held))))),
    h("div", { className: "grid-2" },
      card(h("h2", {}, "What the connection string means"), names.map((name) => perDoor[name].anatomy)),
      card(h("h2", {}, "No psql yet?"),
        h("p", { className: "small" }, "psql is PostgreSQL's own terminal client. The documentation says how to install it and connect with it, step by step."),
        h("ul", { className: "links" },
          h("li", {}, h("a", { href: siteLink("/docs/connecting/") }, "Connecting, in the documentation")),
          h("li", {}, link(`#/projects/${key}/sql`, "Or use the SQL editor in your browser"))))));
}

// -- branches ---------------------------------------------------------------------

// The plan's branch limit against the project's live branches (ADR 0297
// decision 6): a banner when the project holds all it may. The plan's number
// is the `branches_total` entitlement `GET .../plan` serves.
function branchLimitBanner(organization, plan, held) {
  const entitlement = plan && Array.isArray(plan.entitlements)
    ? plan.entitlements.find((entry) => entry.name === "branches_total")
    : null;
  const limit = entitlement && typeof entitlement.value === "number" ? entitlement.value : null;
  if (limit === null || held < limit) {
    return null;
  }
  return banner(h("strong", {}, `${planName(plan)} plan: ${held} of ${count(limit, "branch", "branches")} on this project.`),
    " A new branch cannot be made until one is deleted. ", planLinks(organization));
}

async function branchesView(me, key, turn) {
  const organization = current().organization;
  const [served, plan] = await Promise.all([call("GET", `/projects/${key}/branches`),
    organization ? readPlan(organization.id) : Promise.resolve(null)]);
  const result = h("div", { className: "stack" });
  const [nameLabel, name] = field("Branch name", { maxLength: 12 });
  // D3013: a date and time picker in the browser's own zone, converted here to
  // the instant the API takes (`instantOf`); the zone is said beside it.
  const zone = zoneName();
  const [atLabel, at] = field("Restore to (optional)", { type: "datetime-local", step: 1 },
    `A date and time in your browser's time zone${zone ? `, ${zone}` : ""}; it is sent as that instant. Leave it empty to branch from now. Reset uses it too.`);
  // The restore time as the API takes it: null for none, false when it cannot be read.
  const target = () => (at.value ? instantOf(at.value) || false : null);
  const unreadable = () => result.replaceChildren(h("p", { className: "refusal" },
    "The restore time could not be read as a date and time; nothing was sent."));
  // A deletion started in its dialog, followed here while the page is open
  // (D3015: the reading stops when the page is left).
  async function follow(answer, what) {
    result.replaceChildren();
    const status = h("p", { className: "muted" }, what + "…");
    result.append(status, followLink(answer.operation));
    try {
      const final = await waitFor(answer.operation.id, status, turn);
      if (final !== null) {
        result.append(outcome(final));
      }
    } catch (error) {
      result.append(refusal(error));
    }
  }
  // Two passwords made here; only their verifiers leave (D2449, D2660).
  async function request(route, body, what) {
    result.replaceChildren();
    const status = h("p", { className: "muted" }, what + "…");
    result.append(status);
    let app = newPassword();
    let admin = newPassword();
    try {
      const answer = await call("POST", route, { ...body, app_verifier: await verifier(app), admin_verifier: await verifier(admin) });
      result.append(
        once("customer_app's password (the pooled door):", app),
        once("customer_admin's password (the direct door):", admin),
        h("p", { className: "muted" }, "They work once the operation succeeds."),
        followLink(answer.operation),
      );
      const final = await waitFor(answer.operation.id, status, turn);
      if (final !== null) {
        result.append(outcome(final));
      }
    } catch (error) {
      result.append(refusal(error, { organization: organization ? organization.id : null }));
    } finally {
      app = null;
      admin = null;
    }
  }
  // D3088: each branch's deletion is confirmed in a dialog by typing its name.
  const dialogs = [];
  const deletion = (branch) => {
    const [start, modal] = confirmDialog({
      opener: "Delete…",
      title: `Delete the branch ${branch.name}?`,
      sentence: "A branch is not backed up: its data is gone once it is deleted. This cannot be undone.",
      name: branch.name,
      busy: "Deleting…",
      quiet: true,
      work: () => call("DELETE", `/projects/${key}/branches/${encodeURIComponent(branch.name)}`),
      done: (answer) => follow(answer, `Deleting ${branch.name}`),
      refused: (error) => refusal(error),
    });
    start.setAttribute("aria-label", `Delete the branch ${branch.name}`);
    dialogs.push(modal);
    return start;
  };
  const rows = served.branches.map((branch) => ({
    ...branch,
    reached_point: when(branch.reached_point, "absolute"),
    expires_at: when(branch.expires_at),
    state: stateChip(branch.state),
    actions: h("span", { className: "row-actions" },
      busyButton("Reset", async () => {
        const instant = target();
        if (instant === false) {
          unreadable();
          return;
        }
        await request(`/projects/${key}/branches/${encodeURIComponent(branch.name)}/reset`,
          instant ? { target_time: instant } : {}, `Resetting ${branch.name}`);
      }, { busy: "Resetting…" }),
      deletion(branch)),
  }));
  frame(me, "Branches",
    organization ? branchLimitBanner(organization.id, plan, served.branches.length) : null,
    card(rows.length
      ? table([["name", "Name"], ["state", "State"], ["reached_point", "Reached"], ["expires_at", "Expires"],
        ["pool_host", "Pooled host"], ["actions", ""]], rows)
      : emptyState("No branch yet. A branch is a copy of this project's database to try things on; it is not backed up.",
        button("Make a branch", () => name.focus(), { className: "secondary" })),
    h("p", { className: "muted" }, value(served.notice)),
    dialogs),
    card(h("h2", {}, "New branch"), nameLabel, atLabel,
      busyButton("Create the branch", async () => {
        const branch = name.value.trim();
        if (!BRANCH.test(branch) || branch === "main") {
          result.replaceChildren(h("p", { className: "refusal" }, "A branch name is 2 to 12 lowercase letters and digits, starting with a letter, and not main."));
          return;
        }
        const instant = target();
        if (instant === false) {
          unreadable();
          return;
        }
        if (instant) {
          await request(`/projects/${key}/restores`, { branch, target_time: instant }, `Restoring into ${branch}`);
        } else {
          await request(`/projects/${key}/branches`, { branch }, `Branching into ${branch}`);
        }
      }, { busy: "Creating the branch…" })),
    result);
}

async function backupsView(me, key) {
  const served = await call("GET", `/projects/${key}/backups`);
  let body;
  if (served.status === "window") {
    body = [h("p", {}, "Restorable from ", h("strong", {}, when(served.earliest, "absolute")), " to ",
      h("strong", {}, when(served.latest, "absolute")), "."),
    h("p", {}, "Last full backup ", when(served.last_full_at), "; read ", when(served.observed_at), "."),
      served.message ? h("p", { className: "muted" }, served.message) : null];
  } else if (served.status === "sleeping") {
    body = [h("p", {}, "The project is sleeping. ", value(served.message))];
  } else if (served.status === "could_not_determine" && !("observed_at" in served)) {
    // Before a first reading: the one undetermined answer that names no
    // reading's time at all (`backups_document`, ADR 0273).
    body = [emptyState("No backup reading has been recorded for this project yet. The window it can be restored to appears here once the server records the first one.",
      button("Read it again", () => route(), { className: "secondary" }))];
  } else {
    body = [h("p", { className: "refusal" }, "The restore window could not be determined: ", value(served.reason))];
  }
  frame(me, "Backups", card(...body));
}

// D3090: a usage figure as words -- the size in human units with its exact
// bytes as the element's title, or "not read" when the server read none.
function amount(words, detail) {
  return detail ? h("data", { value: detail.replace(/\D/g, ""), title: detail }, words) : h("span", {}, words);
}

function usageSection(document) {
  // Before data: no sample in the window -- the server's own "could not
  // determine" (`_usage`, ADR 0275), never shown as zeros.
  if (!(document.samples && document.samples.present > 0) && typeof document.project_key === "string") {
    return h("section", { className: "card" },
      h("h2", {}, document.project_key),
      emptyState("No usage sample was recorded for this project in this window. The server records samples while the project is awake; they appear here as it does.",
        link(`#/projects/${document.project_key}/connect`, "Connect your application")));
  }
  if (document.status === "could_not_determine") {
    return h("p", { className: "refusal" }, `${document.project_key}: usage could not be determined: ${value(document.reason)}`);
  }
  const figures = document.figures || {};
  // D3090: each figure by its plain name, in human units (`progress.js`).
  const rows = usageRows(figures).map((row) => ({
    title: row.title,
    latest: row.latest_at
      ? h("span", {}, amount(row.latest, row.latest_detail), h("span", { className: "sub muted small" }, "read ", when(row.latest_at)))
      : amount(row.latest, row.latest_detail),
    max: amount(row.max, row.max_detail),
  }));
  const window_ = document.window || {};
  return h("section", { className: "card" },
    h("h2", {}, value(document.project_key)),
    h("p", { className: "muted" }, "From ", when(window_.from, "absolute"), " to ", when(window_.to, "absolute"),
      `; ${document.samples.present} of ${document.samples.expected} samples recorded. A figure the server could not read is said as not read, never as zero.`),
    table([["title", "Figure"], ["latest", "Latest"], ["max", "Highest in this period"]], rows, new Set(["latest", "max"])),
    h("dl", { className: "facts" }, usageTotals(document).map((total) =>
      h("div", {}, h("dt", {}, total.title), h("dd", {}, total.value)))),
    // D3078: "Storage: 4.1 of 5 GB", from the figure each limit is read against.
    (document.entitlements || []).length
      ? table([["use", "Your plan's limits"], ["enforced", "Enforced"]],
        document.entitlements.map((limit) => ({
          use: entitlementUse(limit, figures),
          enforced: limit.enforced ? "enforced" : "shown, not enforced during the beta",
        })))
      : null);
}

async function projectUsageView(me, key) {
  frame(me, "Usage", usageSection(await call("GET", `/projects/${key}/usage?hours=24`)));
}

async function insightsView(me, key) {
  const served = await call("GET", `/projects/${key}/insights?hours=24&limit=20`);
  let body;
  if (served.status === "could_not_determine") {
    body = [h("p", { className: "refusal" }, "Insights could not be determined: ", value(served.reason))];
  } else if (!(served.statements || []).length) {
    body = [emptyState("No statement of yours ran in the last 24 hours. The statements your roles run appear here, slowest in total first.",
      link(`#/projects/${key}/sql`, "Run one in the SQL editor"))];
  } else {
    body = [table([["total_ms", "Total ms"], ["calls", "Calls"], ["mean_ms", "Mean ms"], ["rows_per_call", "Rows/call"],
      ["cache_hit_ratio", "Cache"], ["role", "Role"], ["query", "Statement"]],
    served.statements.map((statement) => ({ ...statement, query: h("code", {}, statement.query) })),
    new Set(["total_ms", "calls", "mean_ms", "rows_per_call", "cache_hit_ratio"]))];
  }
  frame(me, "Slowest queries", card(...body, h("p", { className: "muted" }, value(served.tuning))));
}

async function monitoringView(me, key) {
  const served = await call("GET", `/projects/${key}/monitoring`);
  const signals = served.signals || [];
  const rows = signals.map((signal) => ({
    name: signal.name,
    reading: "unread" in signal
      ? `not read: ${signal.unread}`
      : h("span", {}, `${signal.value} ${signal.unit}, `, when(signal.observed_at)),
    source: signal.source,
  }));
  // Before data: no signal has a reading yet -- each still names why, below.
  const before = signals.every((signal) => "unread" in signal);
  frame(me, "Monitoring",
    before
      ? emptyState("No reading has been taken for this project yet. Each one appears here, naming where it comes from, once the server reads it.",
        button("Read them again", () => route(), { className: "secondary" }))
      : null,
    rows.length
      ? card(h("p", { className: "muted" }, "Read ", when(served.read_at), ". Each reading names where it comes from."),
        table([["name", "Signal"], ["reading", "Reading"], ["source", "Source"]], rows))
      : null);
}

// Session 46 (ADR 0292): the support bundle as the server recorded it -- what
// it last saw and when, never "now"; a stale or missing reading says so.
function supportBundle(served) {
  const fresh = served.status === "read" || served.status === "asleep";
  const line = served.status === "read" ? ["Read ", when(served.read_at), "."] : value(served.reason);
  const rows = (served.checks || []).map((check) => ({
    name: check.name,
    verdict: check.stale ? `${check.verdict} (stale)` : check.verdict,
    detail: check.detail,
    age: `${value(check.age_seconds)} s ago`,
  }));
  return [h("p", { className: fresh ? "muted" : "refusal" }, line),
    ...(rows.length ? [table([["name", "Check"], ["verdict", "Verdict"], ["detail", "Detail"], ["age", "Read"]], rows)] : [])];
}

async function projectSettingsView(me, key, turn) {
  const project = await call("GET", `/projects/${key}`);
  const result = h("div", { className: "stack" });
  // Each operation is followed here while the page is open, and on its own
  // page (D2975) from the link; leaving this page stops this page's reading.
  async function follow(answer, status) {
    result.append(followLink(answer.operation));
    const final = await waitFor(answer.operation.id, status, turn);
    if (final !== null) {
      result.append(outcome(final));
    }
    return final;
  }
  async function operate(method, path, body, what) {
    result.replaceChildren();
    const status = h("p", { className: "muted" }, what + "…");
    result.append(status);
    try {
      return await follow(await call(method, path, body), status);
    } catch (error) {
      result.append(refusal(error));
      return null;
    }
  }
  // D3088 (the brief's screen 9): the deletion in its own card, confirmed in a
  // dialog by typing the project's key; the request is the dialog's busy
  // button, and the operation is followed below once the dialog closes.
  const [deleteStart, deleteDialog] = confirmDialog({
    opener: "Delete project…",
    title: `Delete ${key}?`,
    sentence: "Everything in it is deleted: the database, its branches and its backups. This cannot be undone.",
    name: key,
    busy: "Deleting…",
    work: () => call("DELETE", `/projects/${key}`),
    done: (answer) => {
      result.replaceChildren();
      const status = h("p", { className: "muted" }, "Deleting…");
      result.append(status);
      follow(answer, status).catch((error) => result.append(refusal(error)));
    },
    refused: (error) => refusal(error),
  });
  const [idleLabel, idle] = choice("Sleep when idle", [
    { value: "never", label: "never" }, { value: "15", label: "after 15 minutes" },
    { value: "30", label: "after 30 minutes" }, { value: "60", label: "after 60 minutes" }], "never");
  const [profileLabel, profile] = choice("Compute size", PROFILES, project.profile);
  const bundle = h("div", {});
  try {
    bundle.append(...supportBundle(await call("GET", `/projects/${key}/diagnostics`)));
  } catch (error) {
    bundle.append(refusal(error));
  }
  frame(me, "Settings", { chip: stateChip(project.state) },
    card(h("p", {}, "State ", stateChip(project.state), `, size ${value(project.profile)}, region ${value(project.region)}.`),
      idleLabel,
      busyButton("Save idle sleep", async () => {
        result.replaceChildren();
        try {
          const minutes = idle.value === "never" ? null : Number(idle.value);
          const answer = await call("PUT", `/projects/${key}/idle-sleep`, { minutes });
          result.append(h("p", {}, "Saved. ", value(answer.note)));
        } catch (error) {
          result.append(refusal(error));
        }
      }, { busy: "Saving…" }),
      profileLabel,
      busyButton("Resize", () => operate("PUT", `/projects/${key}/compute`, { profile: profile.value }, "Resizing"), { busy: "Resizing…" })),
    card(h("h2", {}, "Sleep and wake"),
      busyButton("Sleep", () => operate("POST", `/projects/${key}/sleep`, undefined, "Putting to sleep"), { busy: "Putting to sleep…" }),
      busyButton("Wake", () => operate("POST", `/projects/${key}/wake`, undefined, "Waking"), { busy: "Waking…" })),
    card(h("h2", {}, "Export"),
      busyButton("Export the database", async () => {
        const final = await operate("POST", `/projects/${key}/export`, undefined, "Exporting");
        if (final && final.status === "succeeded" && typeof final.download_url === "string") {
          const result_ = final.result || {};
          result.append(
            once("The download link:", final.download_url),
            h("p", { className: "muted" }, `${value(result_.size_bytes)} bytes, sha256 ${value(result_.sha256)}.`));
        }
      }, { busy: "Exporting…" })),
    card(h("p", {}, h("strong", {}, "Support bundle"),
      " — the checks the server last ran on this project's node, each with when it was read. ",
      "To send it to whoever helps you: ",
      h("code", {}, `apg project diagnostics --project-key ${key} --output FILE`), "."),
    bundle),
    h("section", { className: "card danger-zone" }, h("h2", {}, `Delete ${key}`),
      h("p", {}, "Deletes the database, its branches and its backups. This cannot be undone."),
      deleteStart, deleteDialog),
    result);
}

// -- an organisation's views --------------------------------------------------

const PLAN_STATUS = { active: "active", unavailable_during_beta: "not available during the beta" };

async function planView(me, org) {
  const [plans, held] = await Promise.all([call("GET", "/plans"), call("GET", `/organizations/${org}/plan`)]);
  const message = h("div", {});
  // D3078: each entitlement by its title and its value in words, never its key.
  const entitlementRows = (document) => document.entitlements.map((entitlement) => ({
    title: entitlementTitle(entitlement),
    value: entitlementValue(entitlement),
    enforced: entitlement.enforced ? "enforced" : "shown, not enforced",
  }));
  // A plan's status as words; one this table does not hold is said as served.
  const status = (word) => (Object.hasOwn(PLAN_STATUS, word) ? PLAN_STATUS[word] : value(word));
  frame(me, "Plan and usage",
    card(h("p", {}, `This organisation is on the ${planName(held)} plan (${status(held.status)}); projects held ${held.projects_active.held} of ${held.projects_active.limit}.`),
      h("p", {}, link(`#/org/${org}/usage`, "Each project's usage in the last 24 hours"), " · ",
        h("a", { href: siteLink("/pricing/") }, "Compare the plans"))),
    plans.plans.map((document) => h("section", { className: "card" },
      h("h2", {}, `${planName(document)} (${status(document.status)})`),
      table([["title", "Entitlement"], ["value", "Limit"], ["enforced", ""]], entitlementRows(document)),
      document.status !== "active" ? busyButton("Notify me", async () => {
        try {
          const answer = await call("POST", `/organizations/${org}/plan-interest`, { plan: document.plan });
          message.replaceChildren(h("p", {}, answer.recorded ? "Recorded. " : "Already recorded. ", value(answer.note)));
        } catch (error) {
          message.replaceChildren(refusal(error));
        }
      }, { busy: "Recording…" }) : null)),
    message,
    h("p", { className: "muted" }, value(plans.note)));
}

async function orgUsageView(me, org) {
  const served = await call("GET", `/organizations/${org}/usage?hours=24`);
  frame(me, "Usage",
    served.projects.length
      ? served.projects.map(usageSection)
      : emptyState("No project of this organisation recorded usage in the last 24 hours. Each project's size, branches and connections appear here once it does.",
        link(`#/org/${org}`, "See the projects")));
}

// What makes a notification (ADR 0297 decision 5; the brief's screen 8).
const NOTICE_KINDS = [
  ["Started", "A project creation, a branch, a restore or a branch reset began."],
  ["Finished", "An operation succeeded, or failed and said why."],
  ["Asleep", "A project went to sleep after its idle time."],
  ["Expired", "A branch reached its expiry time and was deleted."],
  ["Limit near", "A project passed 80% of a limit your plan shows."],
];

// One notification in plain words, with a link onward: the operation that
// wrote it (`#/operations/<id>`, D2953), or -- when it names none -- the page
// that acts on it: its project, else the organisation's activity. A kind this
// page does not know reads the server's own text, and still links onward.
function noticeWords(notice, org, entitlements) {
  const title = OPERATION_TITLES[notice.operation_type] || "An operation";
  const key = typeof notice.project === "string" ? notice.project : null;
  const on = key ? ` on ${key}` : "";
  const operation = (words) => (typeof notice.operation_id === "string" && notice.operation_id
    ? link(`#/operations/${notice.operation_id}`, words)
    : link(key ? `#/projects/${key}` : `#/org/${org}/activity`, key ? `Open ${key}` : "See the activity"));
  if (notice.kind === "operation_started") {
    return [h("strong", {}, `${title}${on} started.`), " ", operation("Follow it")];
  }
  if (notice.kind === "operation_succeeded" && notice.operation_type === "project.create" && key) {
    return [h("strong", {}, `Your project ${key} is ready.`), " ", link(`#/projects/${key}/connect`, "Connect to it")];
  }
  if (notice.kind === "operation_succeeded") {
    return [h("strong", {}, `${title}${on} finished.`), " ", operation("Details")];
  }
  if (notice.kind === "operation_failed") {
    return [h("strong", {}, `${title}${on} failed.`), " ", operation("See what happened")];
  }
  if (notice.kind === "idle_sleep") {
    return [h("strong", {}, `${key || "A project"} went to sleep after its idle time.`), " ",
      key ? link(`#/projects/${key}/settings`, "Wake it from Settings") : link(`#/org/${org}`, "See the projects")];
  }
  if (notice.kind === "branch_expired") {
    return [h("strong", {}, `A branch${on} reached its expiry time and was deleted.`), " ",
      key ? link(`#/projects/${key}/branches`, "See the branches") : link(`#/org/${org}`, "See the projects")];
  }
  if (notice.kind === "limit_approaching") {
    // D3078: the server's sentence names the entitlement by its key; it is
    // said by its title, with the plan's limit, from the plan the page read.
    const named = noticeEntitlement(notice.text, entitlements);
    const said = plainNotice(notice.text, entitlements).replace(/\.\s*$/, "");
    return [h("strong", {}, named ? `${entitlementTitle(named)} on ${key || "a project"} is near your plan's limit.` : `${key || "A project"} is near a limit your plan shows.`),
      " ", said ? `${said}.` : "", named ? ` The limit is ${entitlementValue(named)}.` : "", " ", planLinks(org)];
  }
  return [value(plainNotice(notice.text, entitlements)), " ", operation("Details")];
}

// How many the page asks for: the newest, as `apg notifications list` does.
const NOTICES_READ = 50;

// The brief's screen 8: what notifications are and that nothing is emailed;
// a limit near or reached, as on Projects; the latest, each a sentence with a
// link and its time, under how many arrived in the last 24 hours (D3001: a
// count of what the API served -- there is no read state to count unread
// against); then what makes one.
async function notificationsView(me, org) {
  const [served, plan] = await Promise.all([
    call("GET", `/organizations/${org}/notifications?limit=${NOTICES_READ}`),
    readPlan(org),
  ]);
  const notices = served.notifications || [];
  frame(me, "Notifications",
    card(h("p", {}, "A notification is written here when something happens to one of this organisation's projects: an operation starts or finishes, a project goes to sleep, a branch expires, or a limit is near. ",
      h("strong", {}, "Nothing is emailed"), ": this page is where they appear.")),
    projectLimitBanner(org, plan, null),
    notices.length
      ? card(h("h2", {}, "Latest"),
        h("p", { className: "small muted" }, recentNotices(notices, Date.now(), NOTICES_READ),
          " The server does not record which ones you have read, so nothing here is marked unread."),
        h("ul", { className: "feed" }, notices.map((notice) => h("li", {},
          h("span", {}, noticeWords(notice, org, plan ? plan.entitlements : null)), when(notice.created_at)))))
      : emptyState("No notification yet. One appears here when a project's creation, a branch, a restore or a reset starts, and when an operation finishes.",
        firstOperationAction(org)),
    card(h("h2", {}, "What makes a notification"),
      h("dl", { className: "kinds" }, NOTICE_KINDS.map(([kind, meaning]) => [h("dt", {}, kind), h("dd", {}, meaning)]))));
}

// The organisation's invitations: refused, none yet (with where to make one),
// or the table with `revoke` on each still open.
function invitationList(served, start, revoke) {
  if (served.refused) {
    return refusal(served.refused);
  }
  const invitations = served.invitations || [];
  if (!invitations.length) {
    return emptyState("No invitation yet. An invitation is a link that works once, for the role you choose above.",
      button("Choose a role", start, { className: "secondary" }));
  }
  return table([["role", "Role"], ["issued_at", "Issued"], ["expires_at", "Expires"], ["accepted_at", "Accepted"], ["revoked_at", "Revoked"], ["actions", ""]],
    invitations.map((invitation) => ({
      ...invitation,
      issued_at: when(invitation.issued_at),
      expires_at: when(invitation.expires_at),
      accepted_at: when(invitation.accepted_at),
      revoked_at: when(invitation.revoked_at),
      actions: invitation.accepted_at || invitation.revoked_at ? "" : revoke(invitation),
    })));
}

// The organisation's management keys, the same way.
function keyList(served, start, revoke) {
  if (served.refused) {
    return refusal(served.refused);
  }
  const keys = served.keys || [];
  if (!keys.length) {
    return emptyState("No management key yet. A key lets a script or the command-line client act for this organisation, with only the scopes you choose below.",
      button("Name a new key", start, { className: "secondary" }));
  }
  return table([["name", "Name"], ["scopes", "Scopes"], ["last_used_at", "Last used"], ["revoked_at", "Revoked"], ["actions", ""]],
    keys.map((key) => ({
      ...key,
      scopes: key.scopes.join(", "),
      last_used_at: key.last_used_at ? when(key.last_used_at) : "never",
      revoked_at: when(key.revoked_at),
      actions: key.revoked_at ? "" : revoke(key),
    })));
}

async function orgSettingsView(me, org) {
  // A list this person may not read is said as its refusal, never drawn as
  // an empty one (ADR 0195): a viewer's "no invitation" would be a guess.
  const [members, invitations, keys] = await Promise.all([
    call("GET", `/organizations/${org}/members`),
    call("GET", `/organizations/${org}/invitations`).catch((error) => ({ refused: error })),
    call("GET", `/organizations/${org}/keys`).catch((error) => ({ refused: error })),
  ]);
  const result = h("div", { className: "stack" });
  const act = (work) => async () => {
    result.replaceChildren();
    try {
      await work();
      route();
    } catch (error) {
      result.append(refusal(error));
    }
  };
  const memberRows = members.members.map((member) => {
    const role = cellChoice(`Role of ${member.username}`, ROLES, member.role);
    return {
      ...member,
      role,
      actions: h("span", { className: "row-actions" },
        busyButton("Change role", act(() => call("PATCH", `/organizations/${org}/members/${member.user_id}`, { role: role.value })), { busy: "Changing…" }),
        busyButton("Remove", act(() => call("DELETE", `/organizations/${org}/members/${member.user_id}`)), { busy: "Removing…" })),
    };
  });
  const [inviteRoleLabel, inviteRole] = choice("Role", ROLES, "member");
  const [keyNameLabel, keyName] = field("Key name", { maxLength: 64 });
  const scopes = KEY_SCOPES.map((scope) => h("input", { type: "checkbox", value: scope }));
  const keyDialogs = [];
  frame(me, "Members and keys",
    card(h("h2", {}, "Members"),
      table([["username", "Username"], ["display_name", "Name"], ["role", "Role"], ["actions", ""]], memberRows)),
    card(h("h2", {}, "Invite someone"),
      inviteRoleLabel,
      busyButton("Make an invitation link", async () => {
        result.replaceChildren();
        try {
          const minted = await call("POST", "/invitations", { organization_id: org, role: inviteRole.value });
          result.append(once("Send this link to the person you invite:", minted.accept_url),
            h("p", { className: "muted" }, "It expires ", when(minted.expires_at), " and works once."));
        } catch (error) {
          result.append(refusal(error));
        }
      }, { busy: "Making the link…" }),
      invitationList(invitations, () => inviteRole.focus(), (invitation) => busyButton("Revoke",
        act(() => call("DELETE", `/organizations/${org}/invitations/${invitation.id}`)), { busy: "Revoking…" }))),
    card(h("h2", {}, "Management keys"),
      keyList(keys, () => keyName.focus(), (apiKey) => {
        // D3094 (the operator, 2026-10-30): a revoked key cannot be restored --
        // whatever uses it stops at once -- so its revocation is confirmed by
        // typing the key's name. Members and invitations stay one click: both
        // are redone by inviting again.
        const [start, modal] = confirmDialog({
          opener: "Revoke…",
          title: `Revoke the key ${apiKey.name}?`,
          sentence: "Anything using this key stops working at once. A revoked key cannot be restored: make a new one instead.",
          name: apiKey.name,
          action: "Revoke",
          busy: "Revoking…",
          quiet: true,
          work: () => call("DELETE", `/organizations/${org}/keys/${apiKey.key_id}`),
          done: () => route(),
          refused: (error) => refusal(error),
        });
        start.setAttribute("aria-label", `Revoke the key ${apiKey.name}`);
        keyDialogs.push(modal);
        return start;
      }),
      keyDialogs,
      keyNameLabel,
      h("fieldset", {}, h("legend", {}, "Scopes"), KEY_SCOPES.map((scope, index) => h("label", { className: "inline" }, scopes[index], " ", scope))),
      busyButton("Make a key", async () => {
        result.replaceChildren();
        try {
          const chosen = scopes.filter((box) => box.checked).map((box) => box.value);
          const minted = await call("POST", `/organizations/${org}/keys`, { name: keyName.value.trim(), scopes: chosen });
          result.append(once("The key:", minted.key));
        } catch (error) {
          result.append(refusal(error));
        }
      }, { busy: "Making the key…" })),
    result);
}

// -- help (ADR 0298 decisions 2 and 3; D2958; the brief's screen 10) --------------
//
// Ask a person at `invite@` the site's own domain -- derived from this page's
// host, never typed (ADR 0299) -- with what to send and what never to send;
// then the documentation by task, each link a route the site build produces
// (test_console_pages reads them). The site's support page is this page's own
// help link, `PAGES.help` in nav.js: the one place Run 12 points at
// /docs/support/ when it applies the parked site pages.

// The documentation by task, grouped as the site's docs are (DOCS_GROUPS).
const HELP_TASKS = [
  ["Start", [["From your invitation to a connected application", "/quickstart/"],
    ["Accounts, organisations, roles and invitations", "/docs/getting-started/"],
    ["Work from a terminal with the command-line client", "/docs/cli/"]]],
  ["Use a project", [["Create, sleep, resize, export or delete a project", "/docs/projects/"],
    ["Connect your application, with code for each language", "/docs/connecting/"],
    ["Run SQL in the browser", "/docs/sql-editor/"],
    ["Make a branch, or restore to a point in time", "/docs/branches/"],
    ["Backups, and how far back you can restore", "/docs/backups/"]]],
  ["Watch and plan", [["Plans, usage and notifications", "/docs/plans-and-usage/"],
    ["Slowest queries and monitoring", "/docs/insights-and-monitoring/"]]],
  ["When something is refused", [["What each refusal means, and what to do", "/docs/refusals/"],
    ["All the documentation", "/docs/"]]],
];

// Up to `most` of the current organisation's projects, as `draw` makes each.
function someProjects(draw, most) {
  const projects = (current().projects || []).slice(0, most);
  return projects.length ? [": ", projects.map((project, index) => [index ? ", " : "", draw(project.key)])] : null;
}

function helpView(me) {
  const address = `invite@${siteDomain()}`;
  frame(me, "Help",
    card(h("h2", {}, "Ask a person"),
      h("p", {}, "Write to the people who run this service. A person reads every message."),
      h("p", {}, inlineCopy(address)),
      h("p", { className: "small" }, h("a", { href: `mailto:${address}` }, "Write an email"), " from your own mail app, or copy the address.")),
    card(h("h2", {}, "What to send"),
      h("ul", {},
        h("li", {}, "The project's key, if it is about a project", someProjects((key) => inlineCopy(key), 3), "."),
        h("li", {}, "What you did, and what the page said. The word in small type under a message, such as ",
          h("code", {}, "plan_limit_reached"), ", tells whoever helps exactly what the server answered."),
        h("li", {}, "A support bundle, from the project's Settings page",
          someProjects((key) => link(`#/projects/${key}/settings`, key), 3),
          ". It holds the server's latest health checks for the project and its recent operations, and no data and no passwords.")),
      callout("warn", null, h("p", {}, h("strong", {}, "Never send a password, a key, or a link you were shown once."),
        " Nobody here will ask for one."))),
    card(h("h2", {}, "Read the documentation"),
      HELP_TASKS.map(([group, tasks]) => [h("h3", {}, group),
        h("ul", { className: "links" }, tasks.map(([task, path]) => h("li", {}, h("a", { href: siteLink(path) }, task))))])));
}

// -- the SQL editor (Session 44, ADR 0285; D2957, the brief's screen 7) ----------
//
// The state bar at the top says whether the editor is connected, to which
// door, as which user and to which database, with Disconnect; its status line
// says what last happened, every close in messages.js's words (D3012). While
// connected the credentials form is gone; while not, it is the only thing
// below the bar (ADR 0295 decision 8). The password is read once, the input
// cleared, never stored (ADR 0285).

// The open editor session, if any: closed -- and its password with it -- on
// every navigation, on Disconnect and when the page is hidden (D2756).
let editor = null;

function closeEditor() {
  if (editor) {
    const closing = editor;
    editor = null;
    closing.close();
  }
}

window.addEventListener("pagehide", closeEditor);

// A first statement to try, which changes nothing.
const FIRST_STATEMENT = "select now(), current_user;";

function rowsWords(count) {
  return `${count.toLocaleString("en-GB")} ${count === 1 ? "row" : "rows"}`;
}

function took(milliseconds) {
  return milliseconds < 1000 ? `${Math.round(milliseconds)} ms` : `${(milliseconds / 1000).toFixed(1)} s`;
}

// A statement's results as the session yields them, with any refusal seen on
// its way to `runStatement` -- which words it exactly as before (sql.js and
// pg.js are untouched): the page needs only the refusal's code and message to
// know whether to offer the direct door (D3045).
async function* watching(results, seen) {
  try {
    yield* results;
  } catch (error) {
    seen(error);
    throw error;
  }
}

// One result: how many rows and how long, Copy as CSV (built in the page,
// copies.js), then the rows in a box of their own with a sticky header.
function resultView(result, milliseconds) {
  const shaped = result.columns.length > 0;
  return h("section", { className: "result" },
    h("div", { className: "result-meta" },
      h("span", {}, shaped ? h("strong", {}, rowsWords(result.rows.length)) : h("strong", {}, result.command || "Done"),
        ` in ${took(milliseconds)}`),
      shaped ? copyButton(csv(result.columns, result.rows), { label: "Copy as CSV" }) : null),
    shaped
      ? h("div", { className: "results" }, h("table", {},
        h("thead", {}, h("tr", {}, result.columns.map((name) => h("th", { scope: "col" }, name)))),
        h("tbody", {}, result.rows.map((cells) => h("tr", {}, cells.map((cell) => h("td", {}, cell === null ? "NULL" : cell)))))))
      : null,
    result.truncated ? h("p", { className: "muted" }, result.truncated) : null,
    result.notices.map((notice) => h("p", { className: "muted" }, notice)));
}

async function sqlView(me, key) {
  const found = await doors(call, key);
  if (!found.offered) {
    frame(me, "SQL editor", h("p", {}, sentence("not_available")));
    return;
  }
  const relay = await relayOrigin();
  const status = h("p", { className: "status", role: "status", "aria-live": "polite" });
  const state = h("strong", {});
  const details = h("dl", {});
  const results = h("div", { className: "stack" });
  const say = (text) => { status.textContent = text; };
  let running = false;
  let connectedTo = null;
  const [doorLabel, doorChoice] = choice("Door", found.doors.map((door) => ({ value: door.name, label: `${door.name} — ${door.user}` })), "pooled");
  // D3045: the door choice says which door creates tables.
  doorChoice.setAttribute("aria-describedby", "door-hint");
  const doorField = h("div", { className: "field" }, doorLabel, h("p", { className: "hint", id: "door-hint" }, DIRECT_DOOR_HINT));
  const [passwordField, password] = field("Password", { type: "password", autocomplete: "off" },
    ["The password you made for this door on ", link(`#/projects/${key}/connect`, "Connect"),
      ". It is used once to connect, then cleared from this page; it is never stored."]);
  const statement = h("textarea", { id: "statement", rows: 6, spellcheck: false, value: FIRST_STATEMENT });
  const disconnect = busyButton("Disconnect", async () => {
    closeEditor();
    showConnected(null, "Disconnected. The password is not kept: enter it again to connect.");
  }, { busy: "Disconnecting…", className: "secondary" });
  const bar = h("div", { className: "statebar off" },
    h("span", { className: "dot", "aria-hidden": "true" }), state, details, h("span", { className: "grow" }), disconnect, status);
  const connectButton = busyButton("Connect", async () => {
    closeEditor();
    const door = found.doors.find((candidate) => candidate.name === doorChoice.value);
    say("Connecting…");
    const opened = await openDoor({
      call, connect, relay, key, door, closeSentence,
      readPassword: () => {
        const typed = password.value;
        password.value = "";
        return typed;
      },
    });
    if (!opened.opened) {
      showConnected(null, opened.say);
      return;
    }
    const session = opened.session;
    editor = session;
    // A close the page did not ask for -- the relay's 30 minutes, 5 idle
    // minutes, a lost network -- is said the moment it happens.
    session.socket.addEventListener("close", (event) => {
      if (editor === session) {
        editor = null;
        showConnected(null, closeSentence(event.code));
      }
    });
    showConnected(door, `Connected to the ${door.name} door as ${door.user}.`);
  }, { busy: "Connecting…" });
  const connectForm = h("form", {
    className: "card",
    onsubmit: (event) => {
      event.preventDefault();
      connectButton.click();
    },
  }, h("h2", {}, "Connect the editor"), doorField, passwordField, connectButton);
  // A creation refused on the pooled door (D3045): what happened, and one
  // action -- disconnect, choose the direct door, and ask for ITS password,
  // which the person enters (nothing is filled in; ADR 0285). The statement
  // stays in the editor for when they are connected again.
  const directDoorOffer = () => callout("warn", null,
    h("p", {}, CREATE_ON_POOLED.sentence),
    h("p", { className: "card-actions" }, button(CREATE_ON_POOLED.action, () => {
      closeEditor();
      doorChoice.value = "direct";
      showConnected(null, "Disconnected from the pooled door. Enter the direct door's password, then connect.");
      password.focus();
    })));
  const cancel = busyButton("Cancel", async () => {
    if (running && editor) {
      await editor.cancel();
    }
  }, { busy: "Cancelling…", className: "secondary", disabled: true, enabled: () => running });
  const run = busyButton("Run", async () => {
    const session = editor;
    if (!session) {
      say("Connect first.");
      return;
    }
    results.replaceChildren();
    say("Running…");
    running = true;
    cancel.disabled = false;
    const began = performance.now();
    let failed;
    let refused = null;
    const watched = { query: (text) => watching(session.query(text), (error) => { refused = error; }) };
    try {
      failed = await runStatement(watched, statement.value,
        (result) => results.append(resultView(result, performance.now() - began)), closeSentence);
    } finally {
      running = false;
      cancel.disabled = true;
    }
    if (editor !== session) {
      return; // the session closed while it ran, and its ending is already said
    }
    if (failed && session.reader && session.reader.failure) {
      closeEditor();
      showConnected(null, failed);
      return;
    }
    say(failed || `Done in ${took(performance.now() - began)}.`);
    if (failed && needsDirectDoor(refused, connectedTo)) {
      results.append(directDoorOffer());
    }
  }, { busy: "Running…" });
  const work = h("div", { className: "card stack" },
    h("label", { htmlFor: "statement" }, "Statement"), statement,
    h("div", { className: "run-row" }, run, cancel,
      h("p", { className: "small muted" }, SESSION_LIMITS, " ", DEADLINE_SENTENCE)),
    results);
  // The one place the editor's state is drawn (ADR 0295 decision 8).
  function showConnected(door, words) {
    const connected = door !== null;
    connectedTo = connected ? door.name : null;
    connectForm.hidden = connected;
    work.hidden = !connected;
    disconnect.hidden = !connected;
    bar.classList.toggle("off", !connected);
    state.textContent = connected ? "Connected" : "Not connected";
    details.replaceChildren(...(connected
      ? [["Door", door.name], ["User", door.user], ["Database", door.database]].map(([term, shown]) => h("div", {}, h("dt", {}, term), h("dd", {}, shown)))
      : []));
    if (!connected) {
      results.replaceChildren();
    }
    say(words);
  }
  showConnected(null, "Choose a door, enter the password you made for it on Connect, then connect.");
  frame(me, "SQL editor",
    bar,
    connectForm,
    work,
    h("p", { className: "small muted" }, "The editor is your own client: it reaches your database through a relay that keeps nothing it carries. ",
      h("a", { href: siteLink("/docs/sql-editor/") }, "How the editor connects")));
}

// -- the router ----------------------------------------------------------------

const VIEWS = [
  [/^#\/projects\/([^/]+)$/, projectOverviewView, KEY],
  [/^#\/projects\/([^/]+)\/connect$/, connectView, KEY],
  [/^#\/projects\/([^/]+)\/sql$/, sqlView, KEY],
  [/^#\/projects\/([^/]+)\/branches$/, branchesView, KEY],
  [/^#\/projects\/([^/]+)\/backups$/, backupsView, KEY],
  [/^#\/projects\/([^/]+)\/usage$/, projectUsageView, KEY],
  [/^#\/projects\/([^/]+)\/insights$/, insightsView, KEY],
  [/^#\/projects\/([^/]+)\/monitoring$/, monitoringView, KEY],
  [/^#\/projects\/([^/]+)\/settings$/, projectSettingsView, KEY],
  [/^#\/org\/([^/]+)$/, organizationView, UUID],
  [/^#\/org\/([^/]+)\/activity$/, activityView, UUID],
  [/^#\/org\/([^/]+)\/plan$/, planView, UUID],
  [/^#\/org\/([^/]+)\/usage$/, orgUsageView, UUID],
  [/^#\/org\/([^/]+)\/notifications$/, notificationsView, UUID],
  [/^#\/org\/([^/]+)\/settings$/, orgSettingsView, UUID],
  [/^#\/org\/([^/]+)\/new-project$/, newProjectView, UUID],
  [/^#\/operations\/([^/]+)$/, operationView, UUID],
];

// Each view's page (`pages.json`'s id, `nav.js`'s PAGES) and what its route's
// argument names: a project, an organisation, or an operation (whose view
// reads its own context, so the operation is read once per reading).
const PLACES = new Map([
  [projectOverviewView, ["project-overview", "project"]], [connectView, ["connect", "project"]],
  [sqlView, ["sql-editor", "project"]], [branchesView, ["branches", "project"]],
  [backupsView, ["backups", "project"]], [projectUsageView, ["project-usage", "project"]],
  [insightsView, ["insights", "project"]], [monitoringView, ["monitoring", "project"]],
  [projectSettingsView, ["project-settings", "project"]], [organizationView, ["organization", "organization"]],
  [activityView, ["activity", "organization"]], [planView, ["plan", "organization"]],
  [orgUsageView, ["organization-usage", "organization"]], [notificationsView, ["notifications", "organization"]],
  [orgSettingsView, ["organization-settings", "organization"]], [newProjectView, ["new-project", "organization"]],
  [operationView, ["operation", "operation"]],
]);

async function route() {
  closeEditor();
  const turn = begin();
  if (location.hash === "#/sign-in") {
    signInView();
    return;
  }
  let me;
  try {
    me = await call("GET", "/me");
  } catch (error) {
    signInView();
    return;
  }
  if (me.second_factor.required && !me.second_factor.enabled) {
    await enrolFactor();
    location.hash = "#/sign-in";
    signInView();
    return;
  }
  show(skeleton());
  try {
    if (location.hash === "#/new" || location.hash === "#/help") {
      await loadContext(call);
      if (!isCurrent(turn)) {
        return;
      }
      setPage(location.hash === "#/new" ? "new-organization" : "help");
      if (location.hash === "#/new") {
        newOrganization(me);
      } else {
        helpView(me);
      }
      return;
    }
    for (const [pattern, view, argument] of VIEWS) {
      const found = location.hash.match(pattern);
      if (found) {
        const [page, names] = PLACES.get(view);
        if (!argument.test(found[1])) {
          await loadContext(call);
          setPage("missing");
          frame(me, "Not found", h("p", {}, "That address names nothing here."));
          return;
        }
        if (names !== "operation") {
          await loadContext(call, names === "project" ? { projectKey: found[1] } : { organization: found[1] });
          if (!isCurrent(turn)) {
            return;
          }
          setPage(page);
        }
        await view(me, found[1], turn);
        return;
      }
    }
    await loadContext(call);
    if (!isCurrent(turn)) {
      return;
    }
    setPage("overview");
    await overview(me, turn);
  } catch (error) {
    frame(me, "Something was refused", refusal(error));
  }
}

if (location.pathname === "/accept") {
  acceptPage();
} else {
  window.addEventListener("hashchange", route);
  route();
}

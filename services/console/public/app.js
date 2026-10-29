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
import { CLAIM_SENTENCE, claimLine, createProject } from "/console/create.js";
import { refusal, sentence } from "/console/messages.js";
import { begin, current, frame, isCurrent, loadContext, mayCreate, narrow, PAGES, setPage, show, useActions } from "/console/nav.js";
import { connect } from "/console/pg.js";
import { CURRENT, describe, DONE, formatDuration, limitText, operationSeconds, STOPPED, stepStates, TERMINAL, typicalRange } from "/console/progress.js";
import { newPassword, verifier } from "/console/scram.js";
import { DEADLINE_SENTENCE, doors, openDoor, runStatement } from "/console/sql.js";
import {
  busyButton, button, card, choice, codeBlock, emptyState, field, h, inlineCopy, link, once, siteDomain, siteLink,
  skeleton, stateChip, table, value,
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

// -- operations ----------------------------------------------------------------

// Reads the operation every 2 s until it is terminal, as `apg operation wait`,
// saying what it is doing in words -- never a percentage (ADR 0296).
async function waitFor(operationId, status) {
  for (;;) {
    const row = await call("GET", `/operations/${encodeURIComponent(operationId)}`);
    status.textContent = describe(row, Date.now());
    if (TERMINAL.has(row.status)) {
      return row;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

function outcome(row) {
  if (row.status === "succeeded") {
    return h("p", {}, "Done.");
  }
  const reason = row.result && row.result.reason ? ` (${row.result.reason})` : "";
  return h("p", { className: "refusal" }, `The operation ${row.status}: `, h("code", {}, value(row.error_code)), reason);
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
// long it has run.
function creationNow(operation) {
  const now = Date.now();
  const running = stepStates(operation, now).find((step) => step.state === CURRENT);
  const elapsed = formatDuration(operationSeconds(operation, now));
  return (running ? running.label : "Waiting to start") + (elapsed ? `, ${elapsed} so far` : "");
}

// An organisation's projects, and the ones being created, as one table.
function projectList(projects, creating) {
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
      : emptyState("No project yet."),
    creating === null ? h("p", { className: "muted" }, "Projects being created could not be read just now.") : null,
  ];
}

async function overview(me) {
  const organizations = (await call("GET", "/organizations")).organizations;
  const sections = [];
  for (const organization of organizations) {
    const projects = (await call("GET", "/projects?organization=" + encodeURIComponent(organization.id))).projects;
    const creating = await openCreations(organization.id);
    sections.push(h("section", { className: "card" },
      h("h2", {}, organization.name, " ", h("small", {}, organization.role)),
      projectList(projects, creating),
      h("p", { className: "card-actions" },
        ["owner", "admin", "member"].includes(organization.role)
          ? link(`#/org/${organization.id}/new-project`, "New project")
          : null,
        link(`#/org/${organization.id}`, "Open this organisation")),
    ));
  }
  frame(me, "Projects", { action: link("#/new", "New organisation") },
    organizations.length === 0 ? emptyState("You belong to no organisation yet. Ask for an invitation, or make one.") : sections,
  );
}

async function organizationView(me, org) {
  const [served, creating] = await Promise.all([
    call("GET", "/projects?organization=" + encodeURIComponent(org)), openCreations(org)]);
  const here = current().organization;
  frame(me, "Projects", { action: mayCreate(here) ? link(`#/org/${org}/new-project`, "New project") : null },
    card(projectList(served.projects, creating)),
    h("p", {}, link(`#/org/${org}/activity`, "Everything that happened in this organisation")));
}

async function activityView(me, org) {
  const served = await call("GET", "/operations?organization=" + encodeURIComponent(org));
  const rows = (served.operations || []).map((operation) => ({
    when: value(operation.created_at),
    what: OPERATION_TITLES[operation.type] || value(operation.type),
    subject: subjectWords(operation),
    status: value(operation.status),
    open: link(`#/operations/${operation.id}`, TERMINAL.has(operation.status) ? "Details" : "Follow"),
  }));
  frame(me, "Activity",
    rows.length
      ? card(table([["when", "When"], ["what", "What"], ["subject", "On"], ["status", "Status"], ["open", ""]], rows))
      : emptyState("Nothing has happened in this organisation yet."));
}

// The tracker's content for one reading of the operation: the steps, done /
// current / to come, with the time each took; the whole's elapsed and typical
// time; the server's limit; the outcome once it is over.
function trackerParts(row) {
  const now = Date.now();
  const states = stepStates(row, now);
  const elapsed = formatDuration(operationSeconds(row, now));
  const typical = typicalRange(row.expected);
  const limit = limitText(row.expected);
  const over = TERMINAL.has(row.status);
  const words = { [DONE]: "done", [CURRENT]: "in progress", [STOPPED]: "stopped here", "to come": "to come" };
  const steps = states.map((step) => {
    let time = "";
    if (step.state === CURRENT && step.seconds !== null) {
      time = `about ${formatDuration(step.seconds)} so far`;
    } else if ((step.state === DONE || step.state === STOPPED) && step.seconds !== null) {
      time = formatDuration(step.seconds);
    } else if (step.state === "to come" && step.typical_seconds !== null) {
      time = step.typical_seconds < 1 ? "usually under a second" : `usually ${formatDuration(step.typical_seconds)}`;
    }
    return h("li", { className: step.state === "to come" ? "todo" : step.state },
      h("span", { className: "mark", "aria-hidden": "true" }, step.state === DONE ? "✓" : ""),
      h("div", {}, h("strong", {}, step.label), h("span", { className: "sr" }, `, ${words[step.state]}`),
        step.state === CURRENT ? h("div", { className: "indeterminate", "aria-hidden": "true" }) : null),
      h("span", { className: "time" }, time));
  });
  return [
    h("p", { className: "meta-row" },
      h("span", {}, "Status ", h("b", {}, value(row.status))),
      h("span", {}, "On ", h("b", {}, subjectWords(row))),
      elapsed ? h("span", {}, over ? "Took about " : "Running for about ", h("b", {}, elapsed)) : null,
      typical ? h("span", {}, "Usually ", h("b", {}, typical)) : null),
    states.length
      ? card(h("ol", { className: "steps" }, steps))
      : h("p", {}, "Step: ", h("code", {}, value(row.step))),
    limit && !over ? h("p", { className: "muted" }, `If it has not finished ${limit} after it started, the server stops it.`) : null,
    row.type === "project.create"
      ? h("p", { className: "muted" }, "The handoff value for the administrator was shown once, when the creation was recorded, and cannot be shown again. You do not need it to connect.")
      : null,
    over ? outcome(row) : null,
    over && row.status === "succeeded" && row.project_key ? h("p", {}, link(`#/projects/${row.project_key}`, "Open the project")) : null,
    over && typeof row.download_url === "string" ? once("The download link:", row.download_url) : null,
  ];
}

// `#/operations/<id>` (ADR 0296 decision 5): read from the API on every load,
// then every 2 s while it runs and this page is open. Nothing is kept that a
// refresh could lose.
async function operationView(me, id, turn) {
  let row = await call("GET", `/operations/${encodeURIComponent(id)}`);
  // A creation names its slot's key before the project is registered: until it
  // succeeds there is no project to read, only its organisation.
  const creating = row.type === "project.create" && row.status !== "succeeded";
  await loadContext(call, { organization: row.organization_id, projectKey: creating ? null : row.project_key });
  if (!isCurrent(turn)) {
    return;
  }
  setPage("operation");
  const tracker = h("div", { className: "stack" });
  const note = h("p", { className: "muted" });
  const draw = () => tracker.replaceChildren(...trackerParts(row).filter(Boolean));
  draw();
  frame(me, OPERATION_TITLES[row.type] || "Operation", tracker, note);
  while (!TERMINAL.has(row.status)) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    if (!isCurrent(turn)) {
      return;
    }
    try {
      row = await call("GET", `/operations/${encodeURIComponent(id)}`);
      note.textContent = "";
    } catch (error) {
      note.textContent = "The operation could not be read just now; this page tries again in two seconds.";
      continue;
    }
    if (!isCurrent(turn)) {
      return;
    }
    draw();
  }
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

// Session 46 (ADR 0291): a project created here. The token is made and
// digested by create.js; it reaches this view only through `accepted`, is drawn
// once in the shown-once panel the moment the creation is recorded -- before the
// ~25-minute wait -- and is dropped with the panel.
function newProjectView(me, org) {
  const [nameLabel, name] = field("Name", { maxLength: 48 });
  const [profileLabel, profile] = choice("Profile", PROFILES, "small");
  const [adminLabel, admin] = field("Administrator's username", { maxLength: 63, autocomplete: "off" });
  const status = h("p", { className: "muted" });
  const result = h("div", { className: "stack" });
  const create = busyButton("Create project", async () => {
    result.replaceChildren();
    try {
      const final = await createProject({
        call,
        wait: (id) => waitFor(id, status),
        accepted: (token, operation) => {
          const panel = h("div", {},
            once("The project administrator's handoff token:", token),
            h("p", {}, "Operation ", h("code", {}, operation.id), " is recorded. ", CLAIM_SENTENCE),
            h("p", {}, h("code", {}, claimLine(null))),
            button("I have saved it", () => panel.remove()));
          result.append(panel,
            h("p", {}, link(`#/operations/${operation.id}`, "Follow it on its own page"), "; it keeps going if you close this one."));
        },
        organization: org,
        name: name.value.trim(),
        profile: profile.value,
        adminUsername: admin.value.trim(),
      });
      if (final.status !== "succeeded") {
        result.append(outcome(final));
        return;
      }
      const key = final.project_key;
      result.append(
        h("p", {}, "Your project ", h("code", {}, value(key)), " is ready. ", link(`#/projects/${key}/connect`, "Connect to it")),
        h("p", { className: "muted" }, "To claim its administrator from a terminal: ", h("code", {}, claimLine(key))));
    } catch (error) {
      result.append(refusal(error));
    }
  }, { busy: "Creating…" });
  frame(me, "New project", card(nameLabel, profileLabel, adminLabel, create, status), result);
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

function door(found) {
  return `postgresql://${found.user}@${found.host}:${found.port}/${found.database}?sslmode=verify-full`;
}

function withPassword(found, password) {
  return `postgresql://${found.user}:${encodeURIComponent(password)}@${found.host}:${found.port}/${found.database}?sslmode=verify-full`;
}

async function connectView(me, key) {
  const served = await call("GET", `/projects/${key}/connections`);
  const result = h("div", { className: "stack" });
  const rotate = (role, doorName) => async () => {
    result.replaceChildren();
    const status = h("p", { className: "muted" }, "Setting a new password…");
    result.append(status);
    let password = newPassword();
    try {
      const answer = await call("POST", `/projects/${key}/credentials`, { role, verifier: await verifier(password) });
      const final = await waitFor(answer.operation.id, status);
      if (final.status !== "succeeded") {
        result.append(outcome(final));
        return;
      }
      const found = served[doorName];
      result.append(
        once(`The new password for ${role}:`, password),
        codeBlock(withPassword(found, password), { label: "The connection string with it", secret: true }),
        codeBlock(`psql "${withPassword(found, password)}"`, { label: "Or with psql", secret: true }),
        h("p", { className: "muted" }, "The previous password no longer works."),
      );
    } catch (error) {
      result.append(refusal(error));
    } finally {
      password = null;
    }
  };
  frame(me, "Connect",
    card(h("p", {}, "Two doors, both TLS (", h("code", {}, "sslmode=verify-full"), ") on port 5432."),
      ["pooled", "direct"].map((name) => h("div", { className: "door" },
        h("p", {}, h("strong", {}, `The ${name} door`), ", as ", h("code", {}, served[name].user)),
        inlineCopy(door(served[name]))))),
    card(h("p", {}, "The password is not stored anywhere you can read it back. Set a new one to see it once:"),
      busyButton("New password for the pooled door (customer_app)", rotate("customer_app", "pooled"), { busy: "Setting a new password…" }),
      busyButton("New password for the direct door (customer_admin)", rotate("customer_admin", "direct"), { busy: "Setting a new password…" }),
      h("p", {}, link(`#/projects/${key}/sql`, "Open the SQL editor"))),
    result);
}

async function branchesView(me, key) {
  const served = await call("GET", `/projects/${key}/branches`);
  const result = h("div", { className: "stack" });
  const [nameLabel, name] = field("Branch name", { maxLength: 12 });
  const [atLabel, at] = field("Restore to (optional, e.g. 2026-10-20T09:30:00Z)", {});
  const [confirmLabel, confirm] = field("To delete a branch, type its name here first", { maxLength: 12 });
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
      );
      result.append(outcome(await waitFor(answer.operation.id, status)));
    } catch (error) {
      result.append(refusal(error));
    } finally {
      app = null;
      admin = null;
    }
  }
  const rows = served.branches.map((branch) => ({
    ...branch,
    state: stateChip(branch.state),
    actions: h("span", { className: "row-actions" },
      busyButton("Reset", () => request(`/projects/${key}/branches/${encodeURIComponent(branch.name)}/reset`,
        at.value.trim() ? { target_time: at.value.trim() } : {}, `Resetting ${branch.name}`), { busy: "Resetting…" }),
      busyButton("Delete", async () => {
        if (confirm.value !== branch.name) {
          result.replaceChildren(h("p", { className: "refusal" }, `Type ${branch.name} in the field below first; a branch is not backed up, and nothing was sent.`));
          return;
        }
        result.replaceChildren();
        const status = h("p", { className: "muted" }, "Deleting…");
        result.append(status);
        try {
          const answer = await call("DELETE", `/projects/${key}/branches/${encodeURIComponent(branch.name)}`);
          result.append(outcome(await waitFor(answer.operation.id, status)));
        } catch (error) {
          result.append(refusal(error));
        }
      }, { busy: "Deleting…" })),
  }));
  frame(me, "Branches",
    card(rows.length
      ? table([["name", "Name"], ["state", "State"], ["reached_point", "Reached"], ["expires_at", "Expires"],
        ["pool_host", "Pooled host"], ["actions", ""]], rows)
      : emptyState("No branch yet. Make one below."),
    h("p", { className: "muted" }, value(served.notice)),
    confirmLabel),
    card(h("h2", {}, "New branch"), nameLabel, atLabel,
      busyButton("Create the branch", async () => {
        const branch = name.value.trim();
        if (!BRANCH.test(branch) || branch === "main") {
          result.replaceChildren(h("p", { className: "refusal" }, "A branch name is 2 to 12 lowercase letters and digits, starting with a letter, and not main."));
          return;
        }
        const target = at.value.trim();
        if (target) {
          await request(`/projects/${key}/restores`, { branch, target_time: target }, `Restoring into ${branch}`);
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
    body = [h("p", {}, "Restorable from ", h("strong", {}, served.earliest), " to ", h("strong", {}, served.latest), "."),
      h("p", {}, `Last full backup ${value(served.last_full_at)}; read ${value(served.observed_at)}.`),
      served.message ? h("p", { className: "muted" }, served.message) : null];
  } else if (served.status === "sleeping") {
    body = [h("p", {}, "The project is sleeping. ", value(served.message))];
  } else {
    body = [h("p", { className: "refusal" }, "The restore window could not be determined: ", value(served.reason))];
  }
  frame(me, "Backups", card(...body));
}

const USAGE_FIGURES = ["database_bytes", "repository_bytes", "branch_count", "branch_bytes", "customer_connections"];

function usageSection(document) {
  if (document.status === "could_not_determine") {
    return h("p", { className: "refusal" }, `${document.project_key}: usage could not be determined: ${value(document.reason)}`);
  }
  const figures = document.figures || {};
  const rows = USAGE_FIGURES.map((name) => {
    const figure = figures[name] || {};
    return { name, latest: figure.latest === null || figure.latest === undefined ? "not read in this window" : `${figure.latest} at ${figure.latest_at}`, max: figure.max };
  });
  return h("section", { className: "card" },
    h("h2", {}, value(document.project_key)),
    h("p", { className: "muted" }, `From ${document.window.from} to ${document.window.to}; ${document.samples.present} of ${document.samples.expected} samples recorded.`),
    table([["name", "Figure"], ["latest", "Latest"], ["max", "Window maximum"]], rows, new Set(["max"])),
    h("p", {}, "Requests answered below 400: ", document.requests ? String(document.requests.increase) : "not read in this window"),
    (document.entitlements || []).length
      ? table([["name", "Limit"], ["value", "Value"], ["against", "Against"], ["enforced", "Enforced"]],
        document.entitlements.map((limit) => ({ ...limit, enforced: limit.enforced ? "enforced" : "shown, not enforced during the beta" })))
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
    body = [emptyState("No statement of yours ran in this window.")];
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
  const rows = (served.signals || []).map((signal) => ({
    name: signal.name,
    reading: "unread" in signal ? `not read: ${signal.unread}` : `${signal.value} ${signal.unit} (at ${signal.observed_at})`,
    source: signal.source,
  }));
  frame(me, "Monitoring",
    card(h("p", { className: "muted" }, `Read at ${value(served.read_at)}. Each reading names where it comes from.`),
      table([["name", "Signal"], ["reading", "Reading"], ["source", "Source"]], rows)));
}

// Session 46 (ADR 0292): the support bundle as the server recorded it -- what
// it last saw and when, never "now"; a stale or missing reading says so.
function supportBundle(served) {
  const fresh = served.status === "read" || served.status === "asleep";
  const said = served.status === "read" ? `Read at ${value(served.read_at)}.` : value(served.reason);
  const rows = (served.checks || []).map((check) => ({
    name: check.name,
    verdict: check.stale ? `${check.verdict} (stale)` : check.verdict,
    detail: check.detail,
    age: `${value(check.age_seconds)} s ago`,
  }));
  return [h("p", { className: fresh ? "muted" : "refusal" }, said),
    ...(rows.length ? [table([["name", "Check"], ["verdict", "Verdict"], ["detail", "Detail"], ["age", "Read"]], rows)] : [])];
}

async function projectSettingsView(me, key) {
  const project = await call("GET", `/projects/${key}`);
  const result = h("div", { className: "stack" });
  async function operate(method, path, body, what) {
    result.replaceChildren();
    const status = h("p", { className: "muted" }, what + "…");
    result.append(status);
    try {
      const answer = await call(method, path, body);
      const final = await waitFor(answer.operation.id, status);
      result.append(outcome(final));
      return final;
    } catch (error) {
      result.append(refusal(error));
      return null;
    }
  }
  const [idleLabel, idle] = choice("Sleep when idle", [
    { value: "never", label: "never" }, { value: "15", label: "after 15 minutes" },
    { value: "30", label: "after 30 minutes" }, { value: "60", label: "after 60 minutes" }], "never");
  const [profileLabel, profile] = choice("Compute size", PROFILES, project.profile);
  const [confirmLabel, confirm] = field(`Type ${key} to delete the project`, {});
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
    card(h("h2", {}, "Delete"),
      confirmLabel,
      busyButton("Delete the project", async () => {
        if (confirm.value !== key) {
          result.replaceChildren(h("p", { className: "refusal" }, "Type the project's key exactly; nothing was sent."));
          return;
        }
        await operate("DELETE", `/projects/${key}`, undefined, "Deleting");
      }, { busy: "Deleting…" })),
    result);
}

// -- an organisation's views --------------------------------------------------

async function planView(me, org) {
  const [plans, held] = await Promise.all([call("GET", "/plans"), call("GET", `/organizations/${org}/plan`)]);
  const message = h("div", {});
  const entitlementRows = (document) => document.entitlements.map((entitlement) => ({
    ...entitlement,
    value: Array.isArray(entitlement.value) ? entitlement.value.join(", ") : value(entitlement.value),
    enforced: entitlement.enforced ? "enforced" : "shown, not enforced",
  }));
  frame(me, "Plan and usage",
    card(h("p", {}, `This organisation is on ${held.plan} (${held.status}); projects held ${held.projects_active.held} of ${held.projects_active.limit}.`),
      h("p", {}, link(`#/org/${org}/usage`, "Each project's usage in the last 24 hours"), " · ",
        h("a", { href: siteLink("/pricing/") }, "Compare the plans"))),
    plans.plans.map((document) => h("section", { className: "card" },
      h("h2", {}, `${document.plan} (${document.status})`),
      table([["name", "Entitlement"], ["value", "Value"], ["unit", "Unit"], ["enforced", ""]], entitlementRows(document)),
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
    served.projects.length ? served.projects.map(usageSection) : emptyState("No project in this window."));
}

async function notificationsView(me, org) {
  const served = await call("GET", `/organizations/${org}/notifications?limit=50`);
  frame(me, "Notifications",
    served.notifications.length
      ? card(table([["created_at", "When"], ["project", "Project"], ["kind", "Kind"], ["text", "What happened"]], served.notifications))
      : emptyState("Nothing yet. A notification is written when a project finishes an operation, falls asleep, or nears a limit."));
}

async function orgSettingsView(me, org) {
  const [members, invitations, keys] = await Promise.all([
    call("GET", `/organizations/${org}/members`),
    call("GET", `/organizations/${org}/invitations`).catch(() => ({ invitations: [] })),
    call("GET", `/organizations/${org}/keys`).catch(() => ({ keys: [] })),
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
    const [, role] = choice("", ROLES, member.role);
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
            h("p", { className: "muted" }, `It expires ${minted.expires_at} and works once.`));
        } catch (error) {
          result.append(refusal(error));
        }
      }, { busy: "Making the link…" }),
      table([["role", "Role"], ["issued_at", "Issued"], ["expires_at", "Expires"], ["accepted_at", "Accepted"], ["revoked_at", "Revoked"], ["actions", ""]],
        invitations.invitations.map((invitation) => ({
          ...invitation,
          actions: invitation.accepted_at || invitation.revoked_at ? "" :
            busyButton("Revoke", act(() => call("DELETE", `/organizations/${org}/invitations/${invitation.id}`)), { busy: "Revoking…" }),
        })))),
    card(h("h2", {}, "Management keys"),
      table([["name", "Name"], ["scopes", "Scopes"], ["last_used_at", "Last used"], ["revoked_at", "Revoked"], ["actions", ""]],
        keys.keys.map((key) => ({
          ...key,
          scopes: key.scopes.join(", "),
          actions: key.revoked_at ? "" : busyButton("Revoke", act(() => call("DELETE", `/organizations/${org}/keys/${key.key_id}`)), { busy: "Revoking…" }),
        }))),
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

// -- help (ADR 0298; Run 7 completes it) ------------------------------------------

function helpView(me) {
  const address = `invite@${siteDomain()}`;
  const docs = [["Getting started", "/docs/getting-started/"], ["Connecting your application", "/docs/connecting/"],
    ["The SQL editor", "/docs/sql-editor/"], ["Branches", "/docs/branches/"], ["Backups", "/docs/backups/"],
    ["Plans and usage", "/docs/plans-and-usage/"], ["What a refusal means", "/docs/refusals/"], ["All the documentation", "/docs/"]];
  frame(me, "Help",
    card(h("h2", {}, "Ask a person"),
      h("p", {}, "Write to the people who run this service; a person reads every message."),
      inlineCopy(address),
      h("p", {}, h("a", { href: `mailto:${address}` }, "Write an email"))),
    card(h("h2", {}, "What to send"),
      h("ul", {},
        h("li", {}, "The project's key, if it is about a project."),
        h("li", {}, "What the page said, and the word in small type under it."),
        h("li", {}, "The support bundle, from the project's Settings page.")),
      h("p", {}, "Never send a password, a key or a link you were shown once: nobody here will ask for one.")),
    card(h("h2", {}, "Read the documentation"),
      h("ul", { className: "links" }, docs.map(([title, path]) => h("li", {}, h("a", { href: siteLink(path) }, title))))));
}

// -- the SQL editor (Session 44, ADR 0285) -------------------------------------

// The open editor session, if any: closed -- and its password with it -- on
// every navigation, on Disconnect and when the page is hidden (D2756).
let editor = null;

function closeEditor() {
  if (editor) {
    editor.close();
    editor = null;
  }
}

window.addEventListener("pagehide", closeEditor);

function resultView(result) {
  return h("section", { className: "result" },
    result.columns.length
      ? h("table", {},
        h("thead", {}, h("tr", {}, result.columns.map((name) => h("th", {}, name)))),
        h("tbody", {}, result.rows.map((cells) => h("tr", {}, cells.map((cell) => h("td", {}, cell === null ? "NULL" : cell))))))
      : null,
    result.truncated ? h("p", { className: "muted" }, result.truncated) : null,
    result.command ? h("p", { className: "muted" }, result.command) : null,
    result.notices.map((notice) => h("p", { className: "muted" }, notice)));
}

async function sqlView(me, key) {
  const found = await doors(call, key);
  if (!found.offered) {
    frame(me, "SQL editor", h("p", {}, sentence("not_available")));
    return;
  }
  const relay = await relayOrigin();
  const status = h("p", { className: "muted", role: "status" }, "Not connected.");
  const results = h("div", {});
  const [doorLabel, doorChoice] = choice("Door", found.doors.map((door) => ({ value: door.name, label: `${door.name} — ${door.user}` })), "pooled");
  const [passwordLabel, password] = field("Password", { type: "password", autocomplete: "off" });
  const statement = h("textarea", { rows: 8, placeholder: "Write a statement", spellcheck: false });
  const say = (text) => { status.textContent = text; };
  const connectForm = h("form", {
    onsubmit: async (event) => {
      event.preventDefault();
      closeEditor();
      const door = found.doors.find((candidate) => candidate.name === doorChoice.value);
      say("Connecting…");
      const opened = await openDoor({
        call, connect, relay, key, door,
        readPassword: () => {
          const typed = password.value;
          password.value = "";
          return typed;
        },
      });
      if (!opened.opened) {
        say(opened.say);
        return;
      }
      editor = opened.session;
      say(`Connected to the ${door.name} door as ${door.user}.`);
    },
  }, doorLabel, passwordLabel, h("button", { type: "submit" }, "Connect"),
  button("Disconnect", () => { closeEditor(); say("Not connected."); }));
  const run = async () => {
    if (!editor) {
      say("Connect first.");
      return;
    }
    results.replaceChildren();
    say("Running…");
    const failed = await runStatement(editor, statement.value, (result) => results.append(resultView(result)));
    say(failed || "Done.");
    if (failed && editor && editor.reader && editor.reader.failure) {
      closeEditor();
    }
  };
  frame(me, "SQL editor",
    h("p", {}, "Your own client: it connects as your database role with the password you type here, which stays in this page."),
    connectForm,
    statement,
    h("p", {}, button("Run", run), " ", button("Cancel", () => { if (editor) editor.cancel(); })),
    h("p", { className: "muted" }, DEADLINE_SENTENCE),
    status,
    results);
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
    await overview(me);
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

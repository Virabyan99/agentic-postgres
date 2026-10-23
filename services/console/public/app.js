// The console's views (ADR 0280). Two pages share this file: `/accept`, where
// an invitation link becomes an account (ADR 0282), and `/console/`, whose
// views are fragment routes (`#/`, `#/projects/<key>/connect`, ...).
//
// Rules this file keeps, each held by tests/contract/test_console_pages.py:
// every value from the server is set with `textContent` or a DOM property,
// never parsed as markup; nothing is written to browser storage or cookies (the
// session is two HttpOnly cookies this code cannot read); a secret -- a
// password, a key, an invitation link, an export link, the factor's seed --
// lives in one view's variables, is shown once, and is never put in a URL or
// a fragment route. A feature the Ledger does not offer has no control here.

import { call, Refusal, relayOrigin } from "/console/api.js";
import { connect } from "/console/pg.js";
import { newPassword, verifier } from "/console/scram.js";
import { DEADLINE_SENTENCE, doors, openDoor, runStatement } from "/console/sql.js";

// What each refusal means, in the words the documentation uses.
const REFUSALS = {
  authentication_failed: "The username or the password is not right, or the session has ended.",
  authorization_failed: "Your role in this organisation does not allow this.",
  second_factor_required: "Enter the six-digit code from your authenticator app.",
  second_factor_invalid: "That code is wrong, or it was already used. Wait for the next one.",
  invitation_invalid: "This invitation is used, expired, revoked or unknown. Ask for a new one.",
  username_taken: "That username is taken. Choose another; the invitation is still good.",
  factor_enabled: "A second factor is already enabled for this account.",
  human_session_required: "Only a signed-in person may do this, not a management key.",
  not_found: "Nothing by that name here, or it is not yours to see.",
  plan_limit_reached: "The organisation already holds its plan's projects; nothing was recorded.",
  capacity_exhausted: "No room on this server; nothing was recorded.",
  conflict: "Another operation is in flight; nothing was recorded.",
  branch_limit_reached: "The project already has its plan's branches, or one is being made; nothing was recorded.",
  not_available: "That is not offered yet.",
  invalid_request: "The request named something this cannot act on.",
  console_unconfigured: "The console is not configured on this server.",
};

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const KEY = /^[a-z][a-z0-9-]{1,62}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
// The server's BRANCH_PATTERN (services/auth-api/app/models.py); `main` is the project.
const BRANCH = /^[a-z][a-z0-9]{1,11}$/;
const ROLES = ["owner", "admin", "member", "viewer"];
const PROFILES = ["small", "standard", "large"];
const KEY_SCOPES = ["organizations:read", "members:read", "projects:read", "projects:write", "operations:read"];

const main = document.getElementById("main");

// -- building blocks ---------------------------------------------------------

// One element, its properties and its children -- strings become text nodes.
function h(tag, properties, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(properties || {})) {
    if (name.startsWith("on")) {
      element.addEventListener(name.slice(2), value);
    } else {
      element[name] = value;
    }
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined && child !== false) {
      element.append(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
    }
  }
  return element;
}

// Flattened, as `h` flattens its children: a view hands over a list of
// sections as one argument, and `replaceChildren` would print an array as the
// text "[object HTMLElement]" instead of inserting its elements (D2713).
function show(...nodes) {
  main.replaceChildren(...nodes.flat().filter((node) => node !== null && node !== undefined && node !== false));
}

function refusal(error) {
  if (error instanceof Refusal) {
    const sentence = REFUSALS[error.code] || "The server refused this.";
    const named = error.body && error.body.row ? [" (Ledger row ", h("code", {}, error.body.row), ")"] : [];
    return h("p", { className: "refusal", role: "alert" }, h("code", {}, error.code), " ", sentence, ...named);
  }
  return h("p", { className: "refusal", role: "alert" }, "The server could not be reached.");
}

function field(label, properties) {
  const input = h("input", properties);
  return [h("label", {}, label, input), input];
}

function choice(label, options, selected) {
  const select = h("select", {}, options.map((option) => h("option", { value: option.value ?? option, selected: (option.value ?? option) === selected }, option.label ?? option)));
  return [h("label", {}, label, select), select];
}

function button(text, onclick, properties) {
  return h("button", { type: "button", onclick, ...(properties || {}) }, text);
}

function link(route, text) {
  return h("a", { href: route }, text);
}

// A secret, shown once: in a <code> element with a Copy button. It lives in
// this element only, and is gone when the view is left.
function once(label, secret) {
  return h("div", { className: "once" },
    h("p", {}, label, h("strong", {}, " Shown once — copy it now.")),
    h("code", { className: "secret" }, secret),
    button("Copy", () => navigator.clipboard.writeText(secret)));
}

function value(text) {
  return text === null || text === undefined ? "—" : String(text);
}

function table(columns, rows) {
  return h("table", {},
    h("thead", {}, h("tr", {}, columns.map(([, title]) => h("th", {}, title)))),
    h("tbody", {}, rows.map((row) => h("tr", {}, columns.map(([name]) => h("td", {}, row[name] instanceof Node ? row[name] : value(row[name])))))));
}

// Reads the operation every 2 s until it is terminal, as `apg operation wait`.
async function waitFor(operationId, status) {
  for (;;) {
    const row = await call("GET", `/operations/${encodeURIComponent(operationId)}`);
    status.textContent = `Operation ${row.status}` + (row.step ? `, ${row.step}` : "") + (row.progress !== undefined && row.progress !== null ? ` (${row.progress}%)` : "");
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

// -- the second factor, shared by onboarding and sign-in --------------------

// Begins enrolment, shows the QR and the base32 text under it, confirms with a
// code. Resolves once confirmed: confirming ends every session (the server's
// rule), so the caller signs in again with the NEXT code.
function enrolFactor() {
  return new Promise((resolve) => {
    const status = h("div", {});
    show(h("h1", {}, "Set up your second factor"), status);
    call("POST", "/me/totp").then((enrolment) => {
      const [codeLabel, code] = field("Code from your app", {
        inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6,
      });
      const message = h("div", {});
      const confirm = button("Confirm", async () => {
        message.replaceChildren();
        try {
          await call("POST", "/me/totp/confirm", { totp_code: code.value.trim() });
        } catch (error) {
          message.replaceChildren(refusal(error));
          return;
        }
        enrolment = null;
        resolve();
      });
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
    show(h("h1", {}, "Invitation"), h("p", {}, "This link holds no invitation. Open the link you were sent."));
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
  show(
    h("h1", {}, "Join with your account"),
    h("p", {}, "You are signed in as ", h("strong", {}, me.username), "."),
    button("Join", async () => {
      try {
        await call("POST", "/invitations/accept", { invitation_token: token });
        location.assign("/console/");
      } catch (error) {
        message.replaceChildren(refusal(error));
      }
    }),
    message,
  );
}

function createAccount(token) {
  const [userLabel, username] = field("Username", { autocomplete: "username", required: true });
  const [displayLabel, display] = field("Display name", { autocomplete: "name" });
  const [passLabel, password] = field("Password", { type: "password", autocomplete: "new-password" });
  const [againLabel, again] = field("Password again", { type: "password", autocomplete: "new-password" });
  const message = h("div", {});
  const create = button("Create your account", async () => {
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
  });
  show(
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
    show(
      h("h1", {}, "Sign in"),
      h("p", {}, "Your second factor is on. Wait for the next code in your app and enter it."),
      codeLabel,
      button("Sign in", async () => {
        try {
          await signIn(username, password, code.value.trim());
        } catch (error) {
          message.replaceChildren(refusal(error));
          return;
        }
        resolve();
      }),
      message,
    );
  });
}

// -- /console/: sign-in, the frame, the views ---------------------------------

function signInView() {
  const [userLabel, username] = field("Username", { autocomplete: "username" });
  const [passLabel, password] = field("Password", { type: "password", autocomplete: "current-password" });
  const [codeLabel, code] = field("Code from your app", {
    inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6,
  });
  codeLabel.hidden = true;
  const message = h("div", {});
  show(
    h("h1", {}, "Sign in"),
    userLabel, passLabel, codeLabel,
    button("Sign in", async () => {
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
    }),
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

// The frame every signed-in view is drawn in: who, where, and the way back.
function frame(me, title, ...body) {
  show(
    h("header", { className: "bar" },
      link("#/", "Overview"),
      h("span", {}, "Signed in as ", h("strong", {}, me.username), " ", button("Sign out", signOut))),
    h("h1", {}, title),
    ...body,
  );
}

function projectNav(key) {
  const views = [["connect", "Connect"], ["sql", "SQL"], ["branches", "Branches"], ["backups", "Backups"], ["usage", "Usage"],
    ["insights", "Insights"], ["monitoring", "Monitoring"], ["settings", "Settings"]];
  return h("nav", { className: "tabs" }, views.map(([view, text]) => link(`#/projects/${key}/${view}`, text)));
}

function orgNav(org) {
  const views = [["plan", "Plan"], ["usage", "Usage"], ["settings", "Members and keys"]];
  return h("nav", { className: "tabs" }, views.map(([view, text]) => link(`#/org/${org}/${view}`, text)));
}

async function overview(me) {
  const organizations = (await call("GET", "/organizations")).organizations;
  const sections = [];
  for (const organization of organizations) {
    const projects = (await call("GET", "/projects?organization=" + encodeURIComponent(organization.id))).projects;
    sections.push(h("section", {},
      h("h2", {}, organization.name, " ", h("small", {}, organization.role)),
      orgNav(organization.id),
      projects.length === 0
        ? h("p", {}, "No project yet.")
        : h("ul", {}, projects.map((project) => h("li", {},
          link(`#/projects/${project.key}/connect`, project.key), " ", value(project.state), " · ", value(project.profile)))),
    ));
  }
  frame(me, "Overview",
    organizations.length === 0 ? h("p", {}, "You belong to no organisation yet.") : sections,
    h("p", {}, link("#/new", "New organisation")),
    h("p", { className: "muted" },
      "Creating a project is done with the command-line client in this beta: ",
      h("code", {}, "apg project create"), " then ", h("code", {}, "apg project claim"), "."),
  );
}

function newOrganization(me) {
  const [nameLabel, name] = field("Name", { maxLength: 64 });
  const message = h("div", {});
  frame(me, "New organisation", nameLabel,
    button("Create", async () => {
      try {
        const created = await call("POST", "/organizations", { name: name.value.trim() });
        location.hash = `#/org/${created.id}/settings`;
      } catch (error) {
        message.replaceChildren(refusal(error));
      }
    }), message);
}

// -- a project's views --------------------------------------------------------

function door(found) {
  return `postgresql://${found.user}@${found.host}:${found.port}/${found.database}?sslmode=verify-full`;
}

function withPassword(found, password) {
  return `postgresql://${found.user}:${encodeURIComponent(password)}@${found.host}:${found.port}/${found.database}?sslmode=verify-full`;
}

async function connectView(me, key) {
  const served = await call("GET", `/projects/${key}/connections`);
  const result = h("div", {});
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
        h("p", {}, "The connection string with it:"),
        h("code", { className: "secret" }, withPassword(found, password)),
        h("p", {}, "Or with psql:"),
        h("code", { className: "secret" }, `psql "${withPassword(found, password)}"`),
        h("p", { className: "muted" }, "The previous password no longer works."),
      );
    } catch (error) {
      result.append(refusal(error));
    } finally {
      password = null;
    }
  };
  frame(me, key, projectNav(key),
    h("p", {}, "Two doors, both TLS (", h("code", {}, "sslmode=verify-full"), ") on port 5432."),
    table([["door", "Door"], ["role", "Role"], ["string", "Connection string"]], [
      { door: "pooled", role: served.pooled.user, string: h("code", {}, door(served.pooled)) },
      { door: "direct", role: served.direct.user, string: h("code", {}, door(served.direct)) },
    ]),
    h("p", {}, "The password is not stored anywhere you can read it back. Set a new one to see it once:"),
    button("New password for the pooled door (customer_app)", rotate("customer_app", "pooled")),
    button("New password for the direct door (customer_admin)", rotate("customer_admin", "direct")),
    h("p", {}, link(`#/projects/${key}/sql`, "Open the SQL editor")),
    result);
}

async function branchesView(me, key) {
  const served = await call("GET", `/projects/${key}/branches`);
  const result = h("div", {});
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
    actions: h("span", {},
      button("Reset", () => request(`/projects/${key}/branches/${encodeURIComponent(branch.name)}/reset`,
        at.value.trim() ? { target_time: at.value.trim() } : {}, `Resetting ${branch.name}`)),
      button("Delete", async () => {
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
      })),
  }));
  frame(me, `${key}: branches`, projectNav(key),
    table([["name", "Name"], ["state", "State"], ["reached_point", "Reached"], ["expires_at", "Expires"],
      ["pool_host", "Pooled host"], ["actions", ""]], rows),
    h("p", { className: "muted" }, value(served.notice)),
    confirmLabel,
    h("h2", {}, "New branch"), nameLabel, atLabel,
    button("Create the branch", () => {
      const branch = name.value.trim();
      if (!BRANCH.test(branch) || branch === "main") {
        result.replaceChildren(h("p", { className: "refusal" }, "A branch name is 2 to 12 lowercase letters and digits, starting with a letter, and not main."));
        return;
      }
      const target = at.value.trim();
      if (target) {
        request(`/projects/${key}/restores`, { branch, target_time: target }, `Restoring into ${branch}`);
      } else {
        request(`/projects/${key}/branches`, { branch }, `Branching into ${branch}`);
      }
    }),
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
  frame(me, `${key}: backups`, projectNav(key), ...body);
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
  return h("section", {},
    h("h2", {}, value(document.project_key)),
    h("p", { className: "muted" }, `From ${document.window.from} to ${document.window.to}; ${document.samples.present} of ${document.samples.expected} samples recorded.`),
    table([["name", "Figure"], ["latest", "Latest"], ["max", "Window maximum"]], rows),
    h("p", {}, "Requests answered below 400: ", document.requests ? String(document.requests.increase) : "not read in this window"),
    (document.entitlements || []).length
      ? table([["name", "Limit"], ["value", "Value"], ["against", "Against"], ["enforced", "Enforced"]],
        document.entitlements.map((limit) => ({ ...limit, enforced: limit.enforced ? "enforced" : "shown, not enforced during the beta" })))
      : null);
}

async function projectUsageView(me, key) {
  frame(me, `${key}: usage (24 h)`, projectNav(key), usageSection(await call("GET", `/projects/${key}/usage?hours=24`)));
}

async function insightsView(me, key) {
  const served = await call("GET", `/projects/${key}/insights?hours=24&limit=20`);
  let body;
  if (served.status === "could_not_determine") {
    body = [h("p", { className: "refusal" }, "Insights could not be determined: ", value(served.reason))];
  } else if (!(served.statements || []).length) {
    body = [h("p", {}, "No statement of yours ran in this window.")];
  } else {
    body = [table([["total_ms", "Total ms"], ["calls", "Calls"], ["mean_ms", "Mean ms"], ["rows_per_call", "Rows/call"],
      ["cache_hit_ratio", "Cache"], ["role", "Role"], ["query", "Statement"]],
    served.statements.map((statement) => ({ ...statement, query: h("code", {}, statement.query) })))];
  }
  frame(me, `${key}: Query Insights (24 h)`, projectNav(key), ...body, h("p", { className: "muted" }, value(served.tuning)));
}

async function monitoringView(me, key) {
  const served = await call("GET", `/projects/${key}/monitoring`);
  const rows = (served.signals || []).map((signal) => ({
    name: signal.name,
    reading: "unread" in signal ? `not read: ${signal.unread}` : `${signal.value} ${signal.unit} (at ${signal.observed_at})`,
    source: signal.source,
  }));
  frame(me, `${key}: monitoring`, projectNav(key),
    h("p", { className: "muted" }, `Read at ${value(served.read_at)}. Each reading names where it comes from.`),
    table([["name", "Signal"], ["reading", "Reading"], ["source", "Source"]], rows));
}

async function projectSettingsView(me, key) {
  const project = await call("GET", `/projects/${key}`);
  const result = h("div", {});
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
  frame(me, `${key}: settings`, projectNav(key),
    h("p", {}, `State ${value(project.state)}, size ${value(project.profile)}, region ${value(project.region)}.`),
    idleLabel,
    button("Save idle sleep", async () => {
      result.replaceChildren();
      try {
        const minutes = idle.value === "never" ? null : Number(idle.value);
        const answer = await call("PUT", `/projects/${key}/idle-sleep`, { minutes });
        result.append(h("p", {}, "Saved. ", value(answer.note)));
      } catch (error) {
        result.append(refusal(error));
      }
    }),
    profileLabel,
    button("Resize", () => operate("PUT", `/projects/${key}/compute`, { profile: profile.value }, "Resizing")),
    h("h2", {}, "Sleep and wake"),
    button("Sleep", () => operate("POST", `/projects/${key}/sleep`, undefined, "Putting to sleep")),
    button("Wake", () => operate("POST", `/projects/${key}/wake`, undefined, "Waking")),
    h("h2", {}, "Export"),
    button("Export the database", async () => {
      const final = await operate("POST", `/projects/${key}/export`, undefined, "Exporting");
      if (final && final.status === "succeeded" && typeof final.download_url === "string") {
        const result_ = final.result || {};
        result.append(
          once("The download link:", final.download_url),
          h("p", { className: "muted" }, `${value(result_.size_bytes)} bytes, sha256 ${value(result_.sha256)}.`));
      }
    }),
    h("h2", {}, "Delete"),
    confirmLabel,
    button("Delete the project", () => {
      if (confirm.value !== key) {
        result.replaceChildren(h("p", { className: "refusal" }, "Type the project's key exactly; nothing was sent."));
        return;
      }
      operate("DELETE", `/projects/${key}`, undefined, "Deleting");
    }),
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
  frame(me, "Plan", orgNav(org),
    h("p", {}, `This organisation is on ${held.plan} (${held.status}); projects held ${held.projects_active.held} of ${held.projects_active.limit}.`),
    plans.plans.map((document) => h("section", {},
      h("h2", {}, `${document.plan} (${document.status})`),
      table([["name", "Entitlement"], ["value", "Value"], ["unit", "Unit"], ["enforced", ""]], entitlementRows(document)),
      document.status !== "active" ? button("Notify me", async () => {
        try {
          const answer = await call("POST", `/organizations/${org}/plan-interest`, { plan: document.plan });
          message.replaceChildren(h("p", {}, answer.recorded ? "Recorded. " : "Already recorded. ", value(answer.note)));
        } catch (error) {
          message.replaceChildren(refusal(error));
        }
      }) : null)),
    message,
    h("p", { className: "muted" }, value(plans.note)));
}

async function orgUsageView(me, org) {
  const served = await call("GET", `/organizations/${org}/usage?hours=24`);
  frame(me, "Usage (24 h)", orgNav(org),
    served.projects.length ? served.projects.map(usageSection) : h("p", {}, "No project in this window."));
}

async function orgSettingsView(me, org) {
  const [members, invitations, keys] = await Promise.all([
    call("GET", `/organizations/${org}/members`),
    call("GET", `/organizations/${org}/invitations`).catch(() => ({ invitations: [] })),
    call("GET", `/organizations/${org}/keys`).catch(() => ({ keys: [] })),
  ]);
  const result = h("div", {});
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
      actions: h("span", {},
        button("Change role", act(() => call("PATCH", `/organizations/${org}/members/${member.user_id}`, { role: role.value }))),
        button("Remove", act(() => call("DELETE", `/organizations/${org}/members/${member.user_id}`)))),
    };
  });
  const [inviteRoleLabel, inviteRole] = choice("Role", ROLES, "member");
  const [keyNameLabel, keyName] = field("Key name", { maxLength: 64 });
  const scopes = KEY_SCOPES.map((scope) => h("input", { type: "checkbox", value: scope }));
  frame(me, "Members and keys", orgNav(org),
    h("h2", {}, "Members"),
    table([["username", "Username"], ["display_name", "Name"], ["role", "Role"], ["actions", ""]], memberRows),
    h("h2", {}, "Invite someone"),
    inviteRoleLabel,
    button("Make an invitation link", async () => {
      result.replaceChildren();
      try {
        const minted = await call("POST", "/invitations", { organization_id: org, role: inviteRole.value });
        result.append(once("Send this link to the person you invite:", minted.accept_url),
          h("p", { className: "muted" }, `It expires ${minted.expires_at} and works once.`));
      } catch (error) {
        result.append(refusal(error));
      }
    }),
    table([["role", "Role"], ["issued_at", "Issued"], ["expires_at", "Expires"], ["accepted_at", "Accepted"], ["revoked_at", "Revoked"], ["actions", ""]],
      invitations.invitations.map((invitation) => ({
        ...invitation,
        actions: invitation.accepted_at || invitation.revoked_at ? "" :
          button("Revoke", act(() => call("DELETE", `/organizations/${org}/invitations/${invitation.id}`))),
      }))),
    h("h2", {}, "Management keys"),
    table([["name", "Name"], ["scopes", "Scopes"], ["last_used_at", "Last used"], ["revoked_at", "Revoked"], ["actions", ""]],
      keys.keys.map((key) => ({
        ...key,
        scopes: key.scopes.join(", "),
        actions: key.revoked_at ? "" : button("Revoke", act(() => call("DELETE", `/organizations/${org}/keys/${key.key_id}`))),
      }))),
    keyNameLabel,
    h("fieldset", {}, h("legend", {}, "Scopes"), KEY_SCOPES.map((scope, index) => h("label", { className: "inline" }, scopes[index], " ", scope))),
    button("Make a key", async () => {
      result.replaceChildren();
      try {
        const chosen = scopes.filter((box) => box.checked).map((box) => box.value);
        const minted = await call("POST", `/organizations/${org}/keys`, { name: keyName.value.trim(), scopes: chosen });
        result.append(once("The key:", minted.key));
      } catch (error) {
        result.append(refusal(error));
      }
    }),
    result);
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
    frame(me, key, projectNav(key), h("p", {}, REFUSALS.not_available));
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
  frame(me, key, projectNav(key),
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
  [/^#\/projects\/([^/]+)\/connect$/, connectView, KEY],
  [/^#\/projects\/([^/]+)\/sql$/, sqlView, KEY],
  [/^#\/projects\/([^/]+)\/branches$/, branchesView, KEY],
  [/^#\/projects\/([^/]+)\/backups$/, backupsView, KEY],
  [/^#\/projects\/([^/]+)\/usage$/, projectUsageView, KEY],
  [/^#\/projects\/([^/]+)\/insights$/, insightsView, KEY],
  [/^#\/projects\/([^/]+)\/monitoring$/, monitoringView, KEY],
  [/^#\/projects\/([^/]+)\/settings$/, projectSettingsView, KEY],
  [/^#\/org\/([^/]+)\/plan$/, planView, UUID],
  [/^#\/org\/([^/]+)\/usage$/, orgUsageView, UUID],
  [/^#\/org\/([^/]+)\/settings$/, orgSettingsView, UUID],
];

async function route() {
  closeEditor();
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
  try {
    if (location.hash === "#/new") {
      newOrganization(me);
      return;
    }
    for (const [pattern, view, argument] of VIEWS) {
      const found = location.hash.match(pattern);
      if (found) {
        if (!argument.test(found[1])) {
          frame(me, "Not found", h("p", {}, "That address names nothing here."));
          return;
        }
        await view(me, found[1]);
        return;
      }
    }
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

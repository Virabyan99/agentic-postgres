// The console's shell (ADR 0295 decision 3; the design brief's §2 and §3): the
// top bar (Help, Notifications, the account menu with Sign out), the left
// navigation (the organisation and project switchers, the project's pages, the
// organisation's pages), the breadcrumb, and the one page template -- title,
// one line saying what the page is for, a help link to the site's page about
// it, the page's primary action -- around a view's own content. Below 900 px
// the navigation folds into one Menu disclosure.
//
// What the switchers list is read in `loadContext` from the calls the
// overview already makes (`GET /v1/organizations`, `GET /v1/projects`) and,
// on a project's page, `GET /v1/projects/{key}`. A reading that fails leaves
// its switcher empty and the page still drawn: the view says what it could
// not read, the shell never does.

import { busyButton, h, siteLink, stateChip } from "/console/ui.js";

const main = document.getElementById("main");
const shell = document.getElementById("shell");
const side = document.getElementById("side");
const top = document.getElementById("top");
const narrowScreen = window.matchMedia("(max-width: 900px)");

// Every page: its label in the navigation and the breadcrumb, the group whose
// navigation item it marks, the one line saying what it is for, and the site
// page that documents it.
export const PAGES = {
  "overview": { label: "Projects", group: null, item: "organization", purpose: "Every project in your organisations, and what is being created.", help: "/docs/projects/" },
  "new-organization": { label: "New organisation", group: null, purpose: "An organisation holds projects and the people who share them.", help: "/docs/getting-started/" },
  "organization": { label: "Projects", group: "organization", item: "organization", purpose: "This organisation's projects, and what is being created.", help: "/docs/projects/" },
  "new-project": { label: "New project", group: "organization", item: "organization", purpose: "A PostgreSQL database with two connection doors, backed up from the start.", help: "/docs/projects/" },
  "activity": { label: "Activity", group: "organization", item: "activity", purpose: "Every operation in this organisation, newest first.", help: "/docs/projects/" },
  "operation": { label: "Operation", group: "organization", item: "activity", purpose: "What this operation is doing, step by step. This page reads it again every two seconds.", help: "/docs/projects/" },
  "plan": { label: "Plan and usage", group: "organization", item: "plan", purpose: "What this organisation's plan includes, and what it holds now.", help: "/docs/plans-and-usage/" },
  "organization-usage": { label: "Usage", group: "organization", item: "plan", purpose: "Each project's size, branches and connections over the last 24 hours.", help: "/docs/plans-and-usage/" },
  "notifications": { label: "Notifications", group: "organization", item: "notifications", purpose: "What happened to this organisation's projects. Nothing is emailed.", help: "/docs/plans-and-usage/" },
  "organization-settings": { label: "Members and keys", group: "organization", item: "organization-settings", purpose: "Who belongs to this organisation, the invitations, and the management keys.", help: "/docs/getting-started/" },
  "project-overview": { label: "Overview", group: "project", item: "project-overview", purpose: "This project's state, and where to go next.", help: "/docs/projects/" },
  "connect": { label: "Connect", group: "project", item: "connect", purpose: "Connect psql, your application or a database tool to this project, in three steps.", help: "/docs/connecting/" },
  "sql-editor": { label: "SQL editor", group: "project", item: "sql-editor", purpose: "Run SQL you write yourself, as your own database role, from this page.", help: "/docs/sql-editor/" },
  "branches": { label: "Branches", group: "project", item: "branches", purpose: "Copies of this project's database to try things on, and restores to a point in time.", help: "/docs/branches/" },
  "backups": { label: "Backups", group: "project", item: "backups", purpose: "The window this project can be restored to.", help: "/docs/backups/" },
  "project-usage": { label: "Usage", group: "project", item: "project-usage", purpose: "This project's size, branches and connections over the last 24 hours.", help: "/docs/plans-and-usage/" },
  "insights": { label: "Slowest queries", group: "project", item: "insights", purpose: "The statements your roles ran in the last 24 hours, slowest in total first.", help: "/docs/insights-and-monitoring/" },
  "monitoring": { label: "Monitoring", group: "project", item: "monitoring", purpose: "Ten readings about this project, each naming where it comes from.", help: "/docs/insights-and-monitoring/" },
  "project-settings": { label: "Settings", group: "project", item: "project-settings", purpose: "Sleep, size, export, the support bundle and deletion.", help: "/docs/projects/" },
  // The site's support page (ADR 0298 decision 1, D2958) is PARKED until Run
  // 12 applies it: this entry's help path is the console's ONE link to it, and
  // moves to "/docs/support/" in the same change -- test_console_pages fails
  // until it does, once the site builds that route.
  "help": { label: "Help", group: null, purpose: "Ask a person, or read the documentation.", help: "/docs/" },
  "missing": { label: "Not found", group: null, purpose: "", help: "/docs/" },
};

const PROJECT_ITEMS = [
  ["project-overview", ""], ["connect", "/connect"], ["sql-editor", "/sql"], ["branches", "/branches"],
  ["backups", "/backups"], ["project-usage", "/usage"], ["insights", "/insights"],
  ["monitoring", "/monitoring"], ["project-settings", "/settings"],
];
const ORGANIZATION_ITEMS = [
  ["organization", ""], ["activity", "/activity"], ["plan", "/plan"], ["notifications", "/notifications"],
  ["organization-settings", "/settings"],
];
const CREATORS = ["owner", "admin", "member"];

// Where the person is: the page, the organisations they belong to, the
// current organisation and its projects, the current project.
let context = { page: "overview", organizations: [], organization: null, projects: null, project: null, projectKey: null };
let actions = { signOut: null };
let generation = 0;

// A route begins: every view's loop that started under an earlier one stops.
export function begin() {
  generation += 1;
  return generation;
}

export function isCurrent(turn) {
  return turn === generation;
}

export function useActions(given) {
  actions = { ...actions, ...given };
}

export function current() {
  return context;
}

export function setPage(page) {
  context.page = Object.hasOwn(PAGES, page) ? page : "missing";
}

// May the signed-in person create a project in this organisation?
export function mayCreate(organization) {
  return Boolean(organization) && CREATORS.includes(organization.role);
}

// Reads what the switchers list. `organization` is the route's, or the
// project's own when the route names a project; with neither, the first.
export async function loadContext(call, { organization = null, projectKey = null } = {}) {
  const next = { page: context.page, organizations: [], organization: null, projects: null, project: null, projectKey };
  try {
    next.organizations = (await call("GET", "/organizations")).organizations || [];
  } catch (error) {
    next.organizations = [];
  }
  let wanted = organization;
  if (projectKey) {
    try {
      next.project = await call("GET", `/projects/${projectKey}`);
      wanted = next.project.organization_id || null;
    } catch (error) {
      next.project = null;
    }
  }
  next.organization = wanted
    ? next.organizations.find((candidate) => candidate.id === wanted) || null
    : next.organizations[0] || null;
  if (next.organization) {
    try {
      next.projects = (await call("GET", "/projects?organization=" + encodeURIComponent(next.organization.id))).projects || [];
    } catch (error) {
      next.projects = null;
    }
  }
  context = next;
  return context;
}

// -- drawing ---------------------------------------------------------------------

// Flattened, as `h` flattens its children: a view hands over a list of
// sections as one argument, and `replaceChildren` would print an array as the
// text "[object HTMLElement]" instead of inserting its elements (D2713).
export function show(...nodes) {
  main.replaceChildren(...nodes.flat().filter((node) => node !== null && node !== undefined && node !== false));
}

// A sign-in, enrolment or invitation view: one narrow panel on the ground,
// with no navigation (ADR 0288).
export function narrow(...nodes) {
  if (shell) {
    shell.classList.add("bare");
  }
  if (side) {
    side.replaceChildren();
  }
  if (top) {
    top.replaceChildren();
  }
  show(h("div", { className: "panel-narrow" }, nodes));
}

function item(href, text, marked) {
  return h("a", marked ? { href, ariaCurrent: "page" } : { href }, text);
}

function initials(name) {
  const letters = String(name || "").replace(/[^A-Za-z0-9]/g, "");
  return (letters.slice(0, 2) || "?").toUpperCase();
}

// Notifications carries no count (D3001): the server keeps no read state and
// this console keeps nothing, so an unread count cannot be read -- and a number
// on this link would be read as one. The Notifications page says how many
// arrived in the last 24 hours, worded as exactly that.
function topBar(me) {
  const organization = context.organization;
  return [
    h("a", { className: "top-link", href: "#/help" }, h("span", { "aria-hidden": "true" }, "?"), h("span", { className: "label" }, "Help")),
    organization ? h("a", { className: "top-link", href: `#/org/${organization.id}/notifications` }, h("span", { className: "label" }, "Notifications")) : null,
    h("details", { className: "account" },
      h("summary", { "aria-label": "Your account" }, initials(me.username)),
      h("div", { className: "menu" },
        h("span", {}, "Signed in as ", h("strong", {}, me.username)),
        h("a", { href: "#/help" }, "Help and support"),
        busyButton("Sign out", async () => {
          if (actions.signOut) {
            await actions.signOut();
          }
        }, { busy: "Signing out…" }))),
  ];
}

function organizationSwitcher() {
  const chosen = context.organization;
  return h("div", { className: "switch" },
    h("span", { className: "switch-label" }, "Organisation"),
    h("details", {},
      h("summary", {}, chosen ? chosen.name : "Choose an organisation"),
      h("div", { className: "menu" },
        context.organizations.map((organization) => item(`#/org/${organization.id}`,
          [organization.name, " ", h("span", { className: "scope" }, organization.role)],
          Boolean(chosen) && organization.id === chosen.id)),
        h("a", { href: "#/new" }, "Create an organisation"))));
}

function projectSwitcher() {
  const chosen = context.projectKey;
  const projects = context.projects || [];
  const organization = context.organization;
  if (!chosen && !projects.length) {
    return null;
  }
  const state = context.project ? context.project.state : null;
  return h("div", { className: "switch" },
    h("span", { className: "switch-label" }, "Project"),
    h("details", {},
      h("summary", {}, chosen ? [h("span", {}, chosen), " ", stateChip(state || "unknown")] : "Choose a project"),
      h("div", { className: "menu" },
        projects.map((project) => item(`#/projects/${project.key}`,
          [project.key, " ", h("span", { className: "scope" }, String(project.state))], project.key === chosen)),
        mayCreate(organization) ? h("a", { href: `#/org/${organization.id}/new-project` }, "Create a project") : null)));
}

function group(name, items, base) {
  const marked = PAGES[context.page] ? PAGES[context.page].item : null;
  return h("nav", { className: "nav-group", "aria-label": name },
    h("p", { className: "nav-title" }, name),
    items.map(([page, suffix]) => item(base + suffix, PAGES[page].label, page === marked)));
}

function navigation() {
  const page = PAGES[context.page] || PAGES.missing;
  const details = h("details", { className: "side" },
    h("summary", {}, h("span", {}, "Menu"), h("span", { className: "where-now" }, page.label)),
    h("div", { className: "side-inner" },
      organizationSwitcher(),
      projectSwitcher(),
      context.projectKey ? group("Project", PROJECT_ITEMS, `#/projects/${context.projectKey}`) : null,
      context.organization ? group("Organisation", ORGANIZATION_ITEMS, `#/org/${context.organization.id}`) : null));
  details.open = !narrowScreen.matches;
  return details;
}

narrowScreen.addEventListener("change", () => {
  const details = side ? side.querySelector("details.side") : null;
  if (details) {
    details.open = !narrowScreen.matches;
  }
});

function breadcrumb(title) {
  const page = PAGES[context.page] || PAGES.missing;
  const steps = [];
  if (page.group && context.organization) {
    steps.push(h("li", {}, h("a", { href: `#/org/${context.organization.id}` }, context.organization.name)));
  }
  if (page.group === "project" && context.projectKey && context.page !== "project-overview") {
    steps.push(h("li", {}, h("a", { href: `#/projects/${context.projectKey}` }, context.projectKey)));
  } else if (page.group === "project" && context.projectKey) {
    steps.push(h("li", {}, context.projectKey));
  }
  steps.push(h("li", { "aria-current": "page" }, title));
  return h("ol", { className: "crumbs", "aria-label": "You are here" }, steps);
}

// A view's options, when its first part is a plain object rather than a node:
// `action` (the page's one primary action) and `chip` (beside the title).
function optionsOf(parts) {
  const first = parts[0];
  if (first && !(first instanceof Node) && typeof first === "object" && !Array.isArray(first)) {
    return [first, parts.slice(1)];
  }
  return [{}, parts];
}

// The frame every signed-in view is drawn in: where you are, what this page is
// for, and its content.
export function frame(me, title, ...body) {
  const [options, parts] = optionsOf(body.flat().filter((node) => node !== null && node !== undefined && node !== false));
  const page = PAGES[context.page] || PAGES.missing;
  if (shell) {
    shell.classList.remove("bare");
  }
  if (top) {
    top.replaceChildren(...topBar(me).filter(Boolean));
  }
  if (side) {
    side.replaceChildren(navigation());
  }
  show(h("div", { className: "content" },
    breadcrumb(title),
    h("div", { className: "page-head" },
      h("div", {},
        h("div", { className: "title-row" }, h("h1", {}, title), options.chip || null),
        page.purpose ? h("p", {}, page.purpose) : null),
      h("div", { className: "head-actions" },
        h("a", { className: "help-link", href: siteLink(page.help) }, "Help with this page"),
        options.action || null)),
    h("div", { className: "page-body" }, parts)));
}

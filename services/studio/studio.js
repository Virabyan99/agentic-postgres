// apg studio, the page. One file, no framework, no dependency (ADR 0205).
//
// This page holds NO credential. Every call below goes to the process that
// served it, on loopback, and that process makes the upstream request with the
// token it holds in memory. The cookie the browser sends is a per-launch key,
// HttpOnly and SameSite=Strict; the custom header below is what a cross-origin
// page could not set without a preflight, and preflights are refused.
//
// Nothing here decides anything. A relation the surface does not name, an
// operator outside the contract, a confirmation that is not an agent's id --
// all of them are refused by the process, because a control the page enforces
// is not a boundary (ADR 0140). The query builder below therefore sends
// STRUCTURE -- a relation, a list of columns, [column, operator, value]
// triples -- and never a path: a path this file composed would be a path the
// process trusted, and the process trusts nothing that arrives on a socket.
//
// The audit view's filter boxes hide rows in this document and nowhere else.
// They do not become query parameters, because a filter applied upstream of a
// count would let a reader ask for `outcome=served` and never learn there were
// refusals (D1248). The process refuses such a parameter with 400, so the
// arrangement is enforced rather than merely intended.

"use strict";

const HEADER = "X-Apg-Studio";

// Every value rendered below goes through `textContent`, never `innerHTML`:
// rows come from a database somebody else may have written into, and a page
// that builds markup out of them is a page that executes them.
async function ask(path, options) {
  const settings = Object.assign({ credentials: "same-origin" }, options || {});
  settings.headers = Object.assign({ Accept: "application/json" }, settings.headers || {});
  settings.headers[HEADER] = "1";
  const response = await fetch(path, settings);
  // A refusal carries a sentence the reader needs -- a 422 from the revocation
  // control says which confirmation was expected -- so the body is read at
  // every status and only an unparsable one becomes `unavailable`.
  try {
    const body = await response.json();
    if (body && typeof body === "object") {
      body.http_status = response.status;
      return body;
    }
  } catch (error) {
    // falls through to the shape below
  }
  return { status: "unavailable", code: response.status };
}

async function post(path, payload) {
  return ask(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function text(tag, value, className) {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function cell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function table(headings, rows, decorate) {
  const element = document.createElement("table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const heading of headings) headRow.appendChild(text("th", heading));
  head.appendChild(headRow);
  element.appendChild(head);

  const body = document.createElement("tbody");
  rows.forEach(function (row, index) {
    const line = document.createElement("tr");
    for (const value of row) line.appendChild(text("td", cell(value)));
    if (decorate) decorate(line, index);
    body.appendChild(line);
  });
  element.appendChild(body);
  return element;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

// ---------------------------------------------------------------------------
// the surface answer
// ---------------------------------------------------------------------------

// The four answers, spelled the way `bin/studio.sh --help` spells them. The
// page BRANCHES on them rather than summarising: a stale contract is not an
// error and an unreachable route is not a stale contract.
function renderSurface(state) {
  const line = document.getElementById("surface");
  const detail = document.getElementById("surface-detail");
  const answer = state.surface.answer;
  line.className = "surface " + answer;

  if (answer === "ok") {
    line.textContent = "surface ok — the deployment serves the contract this checkout describes";
    detail.textContent = "rest_openapi_sha256 " + state.surface.served_sha256;
    detail.hidden = false;
    return true;
  }
  if (answer === "stale_contract") {
    line.textContent = "surface stale_contract — the schema and query views are refused";
    // Two causes and one answer, so the page names both (D1275). The document
    // PostgREST serves is scoped to the caller's grants: an administrator holds
    // nothing in `api` and is served the anonymous document, which is not a
    // stale capture and must not be reported as one.
    detail.textContent =
      "served " + state.surface.served_sha256 + "; expected " + state.surface.expected_sha256 +
      ". Either the capture has moved — regenerate with bin/apg.sh generate --project " +
      "<manifest> — or this subject's role is not the one it was taken for: the served " +
      "document is scoped to the caller's grants, and an administrator is served the " +
      "anonymous document.";
    detail.hidden = false;
    return false;
  }
  line.textContent = "surface " + answer;
  detail.textContent = state.surface.reason || "";
  detail.hidden = false;
  return false;
}

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

function renderSchema(schema) {
  const state = document.getElementById("schema-state");
  state.textContent =
    schema.relations.length + " relations, " + schema.rpcs.length + " RPCs, " +
    Object.keys(schema.enums).length + " enums — from this checkout's contracts, " +
    "confirmed by the deployment";

  const container = document.getElementById("schema");
  clear(container);

  for (const relation of schema.relations) {
    const section = document.createElement("section");
    section.className = "relation";
    section.appendChild(text("h3", relation.name));
    section.appendChild(text("p", relation.methods.join(", "), "muted"));
    section.appendChild(
      table(
        ["column", "type", "format", "nullable"],
        relation.columns.map((column) => [
          column.name, column.type, column.format, column.nullable ? "yes" : "no",
        ]),
      ),
    );
    container.appendChild(section);
  }

  if (schema.rpcs.length) {
    container.appendChild(text("h3", "RPCs"));
    container.appendChild(
      table(
        ["name", "path", "arguments"],
        schema.rpcs.map((rpc) => [
          rpc.name,
          rpc.path,
          rpc.arguments
            .map((argument) => argument.name + ": " + argument.type + (argument.required ? "" : "?"))
            .join(", "),
        ]),
      ),
    );
  }

  const names = Object.keys(schema.enums);
  if (names.length) {
    container.appendChild(text("h3", "enums"));
    container.appendChild(
      table(["name", "members"], names.map((name) => [name, schema.enums[name].join(", ")])),
    );
  }
}

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

const query = { schema: null, relation: null };

function relationOf(name) {
  return query.schema.relations.filter((relation) => relation.name === name)[0];
}

function addFilterRow() {
  const rows = document.getElementById("filter-rows");
  const row = document.createElement("div");
  row.className = "filter-row";

  const column = document.createElement("select");
  column.className = "filter-column";
  for (const item of query.relation.columns) {
    column.appendChild(new Option(item.name, item.name));
  }

  const operator = document.createElement("select");
  operator.className = "filter-operator";
  for (const name of query.schema.filter_operators) {
    operator.appendChild(new Option(name, name));
  }

  const value = document.createElement("input");
  value.type = "text";
  value.className = "filter-value";
  value.placeholder = "value";

  const remove = text("button", "−");
  remove.type = "button";
  remove.addEventListener("click", function () {
    rows.removeChild(row);
  });

  row.appendChild(column);
  row.appendChild(operator);
  row.appendChild(value);
  row.appendChild(remove);
  rows.appendChild(row);
}

function chooseRelation(name) {
  query.relation = relationOf(name);

  const columns = document.getElementById("query-columns");
  clear(columns);
  columns.appendChild(text("legend", "columns"));
  const boxes = document.createElement("div");
  boxes.className = "checkboxes";
  for (const column of query.relation.columns) {
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = column.name;
    box.className = "column-box";
    box.checked = true;
    label.appendChild(box);
    label.appendChild(document.createTextNode(" " + column.name));
    boxes.appendChild(label);
  }
  columns.appendChild(boxes);

  const order = document.getElementById("query-order");
  clear(order);
  order.appendChild(new Option("(none)", ""));
  for (const column of query.relation.columns) {
    order.appendChild(new Option(column.name, column.name));
  }

  clear(document.getElementById("filter-rows"));
  clear(document.getElementById("query-rows"));
  document.getElementById("query-outcome").textContent = "";
}

function buildQuery() {
  const select = [];
  for (const box of document.querySelectorAll(".column-box")) {
    if (box.checked) select.push(box.value);
  }
  const filters = [];
  for (const row of document.querySelectorAll(".filter-row")) {
    filters.push([
      row.querySelector(".filter-column").value,
      row.querySelector(".filter-operator").value,
      row.querySelector(".filter-value").value,
    ]);
  }
  const column = document.getElementById("query-order").value;
  const asked = {
    relation: query.relation.name,
    select: select,
    filters: filters,
    limit: Number(document.getElementById("query-limit").value),
  };
  if (column) asked.order = [column, document.getElementById("query-direction").value];
  return asked;
}

async function runQuery(event) {
  event.preventDefault();
  const outcome = document.getElementById("query-outcome");
  const container = document.getElementById("query-rows");
  clear(container);
  outcome.textContent = "running…";

  const answer = await post("/__apg/query", buildQuery());
  if (answer.status !== "ok") {
    // The process never relays an upstream body (D433), so what a reader gets
    // here is the KIND of no and, for an invalid one, PostgREST's own machine
    // code. Its prose is deliberately absent.
    outcome.textContent =
      "the query was not served: " + answer.status +
      (answer.reason ? " — " + answer.reason : "") +
      (answer.code ? " (" + answer.code + ")" : "");
    return;
  }

  const rows = answer.rows || [];
  outcome.textContent = rows.length + " row(s)";
  if (!rows.length) return;
  const headings = Object.keys(rows[0]);
  container.appendChild(table(headings, rows.map((row) => headings.map((name) => row[name]))));
}

function renderQueryForm(schema) {
  query.schema = schema;
  const state = document.getElementById("query-state");
  const form = document.getElementById("query-form");
  if (!schema.relations.length) {
    state.textContent = "this surface names no relation to query.";
    return;
  }
  const relation = document.getElementById("query-relation");
  clear(relation);
  for (const item of schema.relations) relation.appendChild(new Option(item.name, item.name));
  relation.addEventListener("change", function () {
    chooseRelation(relation.value);
  });
  document.getElementById("add-filter").addEventListener("click", addFilterRow);
  form.addEventListener("submit", runQuery);
  chooseRelation(schema.relations[0].name);
  state.textContent =
    "reads only. Every name below came from the surface the deployment confirmed, and the " +
    "process builds the request — this form sends no URL.";
  form.hidden = false;
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

const audit = { rows: [], header: "", columns: [] };
const AUDIT_FILTERS = [
  ["audit-agent", "agent_id"],
  ["audit-tool", "tool"],
  ["audit-outcome", "outcome"],
  ["audit-boundary", "denial_reason"],
  ["audit-when", "started_at"],
];

function applyAuditFilters() {
  const wanted = AUDIT_FILTERS.map(([id, field]) => [
    field,
    document.getElementById(id).value.trim().toLowerCase(),
  ]).filter(([, value]) => value !== "");

  let shown = 0;
  const lines = document.querySelectorAll("#audit-rows tbody tr");
  audit.rows.forEach(function (row, index) {
    const keep = wanted.every(
      ([field, value]) => cell(row[field]).toLowerCase().indexOf(value) !== -1,
    );
    lines[index].hidden = !keep;
    if (keep) shown += 1;
  });

  // The page's own count, said as the page's own: the header above it still
  // says how many rows the PAGE holds and that the page is the newest 500.
  document.getElementById("audit-filter-state").textContent =
    wanted.length === 0
      ? "no view filter — every row of this page is shown"
      : shown + " of this page's " + audit.rows.length +
        " rows match the view filter. The filter hides rows here; it did not " +
        "narrow what was read.";
}

function renderAudit(answer) {
  const header = document.getElementById("audit-header");
  const container = document.getElementById("audit-rows");
  clear(container);

  if (answer.status !== "ok") {
    header.textContent = "the audit view was not served: " + answer.status;
    document.getElementById("audit-filter-state").textContent = "";
    audit.rows = [];
    return;
  }

  audit.rows = answer.rows || [];
  audit.header = answer.header;
  header.textContent = answer.header;

  if (!audit.rows.length) return;

  // EVERY column the endpoint returned, in the order the first row names them,
  // with `denial_reason` moved to the end so the boundary has a column of its
  // own rather than being one key among many.
  const keys = Object.keys(audit.rows[0]).filter((key) => key !== "denial_reason");
  audit.columns = keys.concat(["denial_reason"]);

  container.appendChild(
    table(
      audit.columns,
      audit.rows.map((row) => audit.columns.map((key) => row[key])),
      function (line, index) {
        if (audit.rows[index].outcome === "refused") line.className = "refused";
        line.lastChild.className = "boundary";
      },
    ),
  );

  for (const [id] of AUDIT_FILTERS) {
    document.getElementById(id).addEventListener("input", applyAuditFilters);
  }
  applyAuditFilters();
}

// ---------------------------------------------------------------------------
// Capabilities
// ---------------------------------------------------------------------------

function renderCapabilities(answer) {
  const state = document.getElementById("capabilities-state");
  const note = document.getElementById("capabilities-note");
  const container = document.getElementById("capabilities");
  clear(container);

  if (answer.status === "unavailable") {
    state.textContent = "the capabilities view is unavailable (" + answer.code + ")";
    return;
  }

  state.textContent = answer.tools.length + " tools; tools_sha256 " + answer.tools_sha256;
  note.textContent = answer.note;
  container.appendChild(
    table(
      ["tool", "kind", "arguments", "scopes"],
      answer.tools.map((tool) => [
        tool.name,
        tool.kind,
        tool.arguments
          .map((argument) => argument.name + ": " + argument.type + (argument.required ? "" : "?"))
          .join(", "),
        tool.scopes.map((set) => set.join(" + ")).join("  |  "),
      ]),
    ),
  );
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

function revokeControl(agentId, refresh) {
  const holder = document.createElement("div");
  const open = text("button", "Revoke");
  open.type = "button";

  const confirm = document.createElement("div");
  confirm.className = "confirm";
  confirm.hidden = true;
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "type the agent id to confirm";
  input.size = 38;
  const send = text("button", "revoke");
  send.type = "button";
  const message = text("span", "", "confirm-message");

  open.addEventListener("click", function () {
    confirm.hidden = !confirm.hidden;
  });
  send.addEventListener("click", async function () {
    // The confirmation is checked by the PROCESS. This control exists so a
    // person has to type the id; it is not what makes the typing necessary.
    const answer = await post("/__apg/revoke", { agent_id: agentId, confirm: input.value });
    if (answer.status === "ok") {
      message.textContent = "revoked";
      refresh();
      return;
    }
    message.textContent = answer.reason || answer.status;
  });

  confirm.appendChild(input);
  confirm.appendChild(send);
  confirm.appendChild(message);
  holder.appendChild(open);
  holder.appendChild(confirm);
  return holder;
}

function renderAgents(answer, refresh) {
  const state = document.getElementById("agents-state");
  const container = document.getElementById("agents");
  clear(container);

  if (answer.status !== "ok") {
    state.textContent = "the agent roster was not served: " + answer.status;
    return;
  }

  const rows = answer.body || [];
  state.textContent = rows.length + " agent(s)";
  if (!rows.length) return;

  const keys = Object.keys(rows[0]);
  const element = table(keys.concat(["revoke"]), rows.map((row) => keys.map((key) => row[key])));
  const lines = element.querySelectorAll("tbody tr");
  rows.forEach(function (row, index) {
    const holder = document.createElement("td");
    holder.appendChild(revokeControl(row.agent_id, refresh));
    lines[index].appendChild(holder);
  });
  container.appendChild(element);
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

function renderSession(state, me, sessions) {
  const own = document.getElementById("session-own");
  own.textContent = state.own_session_known
    ? "This launch knows which session it opened and ends it when the process stops."
    : "This launch could not determine which session was its own and will end none; " +
      "the rows below are every session this subject has.";

  const meBox = document.getElementById("session-me");
  clear(meBox);
  if (me.status === "ok") {
    const body = me.body || {};
    const keys = Object.keys(body);
    meBox.appendChild(table(keys, [keys.map((key) => body[key])]));
  } else {
    meBox.appendChild(text("p", "the identity view was not served: " + me.status, "muted"));
  }

  const box = document.getElementById("session-rows");
  clear(box);
  if (sessions.status !== "ok") {
    box.appendChild(text("p", "the session list was not served: " + sessions.status, "muted"));
    return;
  }
  const rows = sessions.body || [];
  if (!rows.length) {
    box.appendChild(text("p", "no session rows", "muted"));
    return;
  }
  const keys = Object.keys(rows[0]);
  box.appendChild(table(keys, rows.map((row) => keys.map((key) => row[key]))));
}

// ---------------------------------------------------------------------------
// the views
// ---------------------------------------------------------------------------

const VIEWS = [
  ["schema", "Schema"],
  ["query", "Query"],
  ["audit", "Audit"],
  ["capabilities", "Capabilities"],
  ["agents", "Agents"],
  ["session", "Session"],
];

const loaded = {};

function show(name, load) {
  for (const [id] of VIEWS) {
    document.getElementById("view-" + id).hidden = id !== name;
    const button = document.getElementById("tab-" + id);
    if (button) button.setAttribute("aria-current", id === name ? "true" : "false");
  }
  if (!loaded[name]) {
    loaded[name] = true;
    load(name);
  }
}

function buildNav(load) {
  const nav = document.getElementById("views");
  for (const [id, label] of VIEWS) {
    const button = text("button", label);
    button.type = "button";
    button.id = "tab-" + id;
    button.addEventListener("click", function () {
      show(id, load);
    });
    nav.appendChild(button);
  }
}

async function main() {
  const state = await ask("/__apg/state");
  if (state.status === "unavailable") {
    document.getElementById("identity").textContent =
      "the studio process did not answer (" + state.code + ")";
    return;
  }

  document.getElementById("identity").textContent =
    "as " + state.subject + " on " + state.project +
    (state.own_session_known ? "" : " — this launch could not determine its own session");

  const usable = renderSurface(state);

  async function load(name) {
    if (name === "schema" || name === "query") {
      if (!usable) {
        document.getElementById(name + "-state").textContent =
          "not shown: this view describes a contract the deployment did not confirm (" +
          state.surface.answer + ").";
        return;
      }
      const schema = await ask("/__apg/schema");
      if (schema.status === "unavailable" || schema.status === "refused") {
        document.getElementById(name + "-state").textContent =
          "the " + name + " view is unavailable (" + (schema.code || schema.reason) + ")";
        return;
      }
      if (name === "schema") renderSchema(schema);
      else renderQueryForm(schema);
      return;
    }
    if (name === "audit") {
      renderAudit(await ask("/__apg/audit"));
      return;
    }
    if (name === "capabilities") {
      // Not gated on the surface answer, and that is deliberate: this is the
      // checkout's compiled lock, which no answer above was ever about.
      renderCapabilities(await ask("/__apg/capabilities"));
      return;
    }
    if (name === "agents") {
      const refresh = async function () {
        renderAgents(await ask("/__apg/agents"), refresh);
      };
      await refresh();
      return;
    }
    if (name === "session") {
      renderSession(state, await ask("/__apg/me"), await ask("/__apg/sessions"));
    }
  }

  buildNav(load);
  show("schema", load);
}

document.addEventListener("DOMContentLoaded", main);

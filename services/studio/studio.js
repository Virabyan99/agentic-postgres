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
// is not a boundary (ADR 0140).

"use strict";

const HEADER = "X-Apg-Studio";

async function ask(path, options) {
  const settings = Object.assign({ credentials: "same-origin" }, options || {});
  settings.headers = Object.assign({ Accept: "application/json" }, settings.headers || {});
  settings.headers[HEADER] = "1";
  const response = await fetch(path, settings);
  if (!response.ok) {
    return { status: "unavailable", code: response.status };
  }
  return response.json();
}

function text(tag, value, className) {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function table(headings, rows) {
  const element = document.createElement("table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const heading of headings) headRow.appendChild(text("th", heading));
  head.appendChild(headRow);
  element.appendChild(head);

  const body = document.createElement("tbody");
  for (const row of rows) {
    const line = document.createElement("tr");
    for (const cell of row) line.appendChild(text("td", cell === null ? "" : String(cell)));
    body.appendChild(line);
  }
  element.appendChild(body);
  return element;
}

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
    detail.textContent =
      "served " + state.surface.served_sha256 + "; expected " + state.surface.expected_sha256 +
      ". Regenerate with: bin/apg.sh generate --project <manifest>";
    detail.hidden = false;
    return false;
  }
  line.textContent = "surface " + answer;
  detail.textContent = state.surface.reason || "";
  detail.hidden = false;
  return false;
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
  const schemaState = document.getElementById("schema-state");
  if (!usable) {
    schemaState.textContent =
      "not shown: the schema view describes a contract the deployment did not confirm.";
    return;
  }

  const schema = await ask("/__apg/schema");
  if (schema.status === "unavailable") {
    schemaState.textContent = "the schema view is unavailable (" + schema.code + ")";
    return;
  }

  schemaState.textContent =
    schema.relations.length + " relations, " + schema.rpcs.length + " RPCs, " +
    schema.tools.length + " tools — from this checkout's contracts, confirmed by the deployment";

  const container = document.getElementById("schema");
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
}

document.addEventListener("DOMContentLoaded", main);

// The console's one door to the management API (ADR 0280, ADR 0281).
//
// The ONLY file that calls fetch. Every request carries `X-Apg-Console: 1`
// (which no other origin can send without a preflight that nothing answers),
// travels same-origin with the session's two HttpOnly cookies -- this file
// never sees either -- and speaks JSON. A 401 is answered once by a refresh
// and one retry, the command-line client's rule; after that the caller is
// shown the sign-in view.

const CONSOLE_HEADER = "X-Apg-Console";

let environment = null;

// The API's public path (`/api/v1` on the control project), served by the
// console's own server from what the render derived -- never typed here.
async function served() {
  if (environment === null) {
    const answer = await fetch("/console/env.json", { credentials: "same-origin", cache: "no-store" });
    if (!answer.ok) {
      throw new Refusal(answer.status, "console_unconfigured");
    }
    environment = await answer.json();
  }
  return environment;
}

async function base() {
  return (await served()).api;
}

// The SQL relay's origin (`wss://sql.<zone>`, Session 44, ADR 0285): the one
// other origin the console's policy names, served beside the API path.
export async function relayOrigin() {
  return (await served()).sql_relay;
}

export class Refusal extends Error {
  constructor(status, code, body) {
    super(code);
    this.status = status;
    this.code = code;
    this.body = body || null;
  }
}

async function send(method, path, body) {
  const headers = { [CONSOLE_HEADER]: "1" };
  const init = { method, headers, credentials: "same-origin", cache: "no-store", redirect: "error" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  return fetch((await base()) + path, init);
}

async function decode(answer) {
  if (answer.status === 204) {
    return null;
  }
  let data = null;
  try {
    data = await answer.json();
  } catch (error) {
    data = null;
  }
  if (!answer.ok) {
    const code = data && typeof data.error === "string" ? data.error : "unexpected_answer";
    throw new Refusal(answer.status, code, data);
  }
  return data;
}

// One call. `path` is below the API's public path: "/me", "/projects/<key>".
export async function call(method, path, body) {
  let answer = await send(method, path, body);
  if (answer.status === 401 && !path.startsWith("/sessions")) {
    const refreshed = await send("POST", "/sessions/refresh");
    if (refreshed.ok) {
      answer = await send(method, path, body);
    }
  }
  return decode(answer);
}

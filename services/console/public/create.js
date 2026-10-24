// A project created in the console (Session 46, ADR 0291): the decisions,
// DOM-free, so Node can drive them (tests/contract/test_console_create.py).
// `app.js` passes `call` (api.js) and `wait` (its waitFor) and draws what this
// hands back; this file imports nothing.
//
// The handoff token is made here and only its SHA-256 is sent -- the CLI's
// rule (ADR 0260). It is handed to `accepted` the moment the server records
// the creation, BEFORE the wait: a creation takes about 25 minutes, and a tab
// closed during it must already have shown the token. It is held in this
// call's variables and nowhere else, and dropped when the call returns.

// 32 bytes from the platform's generator, base64url without padding: the
// CLI's `secrets.token_urlsafe(32)` (rig 46a).
export function newToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

// SHA-256 hex of the token's UTF-8: the CLI's `hashlib.sha256(token.encode()).hexdigest()`.
export async function digest(token) {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

// The claim, from a terminal. The key is not known at acceptance (a creation's
// project is named once its slot is allocated, D2895), so it reads KEY until then.
export function claimLine(key) {
  return `apg project claim --project-key ${key || "KEY"} --token-file FILE`;
}

export const CLAIM_SENTENCE =
  "Claiming the project's administrator is optional: the connection string and the SQL editor need none. " +
  "To claim it, save the token to a file only you can read (chmod 600), then, once the project is ready, run:";

// Records the creation and follows it. `accepted(token, operation)` is called
// once, as soon as the server answers 202 and before `wait`; a refusal is the
// server's own error, thrown unchanged, and `accepted` is never called for it.
export async function createProject({ call, wait, accepted, organization, name, profile, adminUsername }) {
  let token = newToken();
  try {
    const body = {
      organization,
      name,
      profile,
      admin_username: adminUsername,
      handoff_sha256: await digest(token),
    };
    const answer = await call("POST", "/projects", body);
    accepted(token, answer.operation);
    token = null;
    return await wait(answer.operation.id);
  } finally {
    token = null;
  }
}

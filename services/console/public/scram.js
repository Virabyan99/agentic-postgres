// A database password made in the browser, and only its SCRAM-SHA-256 verifier
// sent (ADR 0280, D2660): what `bin/cloud.py` does on a workstation
// (`agentic_postgres.scram.verifier`), so the control plane keeps holding
// nothing that opens a project's data (ADR 0246).
//
// PostgreSQL's parameters, as the Python module's: 4096 iterations, a 16-byte
// salt, `SCRAM-SHA-256$4096:<salt>$<StoredKey>:<ServerKey>` (RFC 5802, RFC 7677).
// WebCrypto's PBKDF2 was read equal to Python's in Chromium (rig 43a).
//
// Since Session 44 (ADR 0285) the SQL editor's wire client (`pg.js`) proves a
// password with the same primitives, so `base64`, `hmac` and `scramKeys` are
// exported rather than written twice.

export const ITERATIONS = 4096;
export const SALT_BYTES = 16;
// The CLI's `secrets.token_urlsafe(32)`: 32 random bytes, base64url, unpadded.
export const PASSWORD_BYTES = 32;

const encoder = new TextEncoder();

export function base64(bytes) {
  let binary = "";
  for (const byte of new Uint8Array(bytes)) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function base64url(bytes) {
  return base64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function newPassword() {
  return base64url(crypto.getRandomValues(new Uint8Array(PASSWORD_BYTES)));
}

export async function hmac(key, text) {
  const imported = await crypto.subtle.importKey(
    "raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  return crypto.subtle.sign("HMAC", imported, typeof text === "string" ? encoder.encode(text) : text);
}

// RFC 5802's keys for `password`: SaltedPassword, ClientKey, StoredKey, ServerKey.
export async function scramKeys(password, salt, iterations) {
  const material = await crypto.subtle.importKey(
    "raw", encoder.encode(password), "PBKDF2", false, ["deriveBits"],
  );
  const salted = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations }, material, 256,
  );
  const clientKey = await hmac(salted, "Client Key");
  const storedKey = await crypto.subtle.digest("SHA-256", clientKey);
  const serverKey = await hmac(salted, "Server Key");
  return { salted, clientKey, storedKey, serverKey };
}

// The verifier for `password`; a fresh salt unless `saltBytes` is given (a
// proof reproduces one -- `test_console_scram.py` -- nothing else should).
export async function verifier(password, saltBytes) {
  if (!password) {
    throw new Error("an empty password has no verifier");
  }
  const salt = saltBytes || crypto.getRandomValues(new Uint8Array(SALT_BYTES));
  if (salt.length !== SALT_BYTES) {
    throw new Error("the salt must be 16 bytes");
  }
  const { storedKey, serverKey } = await scramKeys(password, salt, ITERATIONS);
  return `SCRAM-SHA-256$${ITERATIONS}:${base64(salt)}$${base64(storedKey)}:${base64(serverKey)}`;
}

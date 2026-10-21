// The SQL editor's client (Session 44, ADR 0285, D2732): the customer's own
// PostgreSQL client, running in the console page. PostgreSQL's frontend/backend
// protocol 3.0 over a binary WebSocket to the relay (ADR 0286), which carries
// the bytes to the project's door. Written here: no third-party file enters the
// console (D2596).
//
// What it speaks, by the protocol documentation's sections (PostgreSQL 18,
// chapter 54 "Frontend/Backend Protocol"):
//   54.2.1 Start-up: StartupMessage (user, database, application_name), then
//          AuthenticationSASL, AuthenticationSASLContinue, AuthenticationSASLFinal,
//          AuthenticationOk, ParameterStatus, BackendKeyData, ReadyForQuery.
//   54.3   SASL Authentication: SCRAM-SHA-256 only, no channel binding (`n,,`).
//          The server's signature is verified BEFORE AuthenticationOk is
//          accepted; a server-first message whose nonce does not extend ours or
//          whose iteration count is below 4096 is refused (D2767). Any other
//          authentication request is refused.
//   54.2.2 Simple Query: Query, then RowDescription, DataRow (text format),
//          CommandComplete, EmptyQueryResponse, ErrorResponse, NoticeResponse,
//          ReadyForQuery. COPY: CopyInResponse answered with CopyFail;
//          CopyOutResponse read and dropped (CopyData, CopyDone) with a notice;
//          CopyBothResponse closes the session.
//   54.2.8 Canceling Requests: a CancelRequest sent as the first message of ITS
//          OWN relay session, so it arrives encrypted -- the only cancel the
//          door passes (ADR 0268, rig 44b) -- and the next statement waits for
//          that session to close (D2766).
//
// The password is read once, inside `authenticate`, and is never stored on the
// connection, in storage, in a URL or in any request but this socket. No
// statement text lives here: the person types every statement.
//
// Bounds (ADR 0285 decisions 7-8): a message over 1 MiB (or under 4 bytes)
// closes the connection with a named error; a statement keeps at most 1,000
// rows and 2 MiB of row text, then sends one cancel and marks the result
// `truncated` -- that cancel's own 57014 is the cap, never an error; a statement
// still running 60 s after it was sent is cancelled.

import { base64, hmac, scramKeys } from "/console/scram.js";

export const PROTOCOL_3_0 = 196608;
export const CANCEL_REQUEST_CODE = 80877102;
export const APPLICATION_NAME = "apg-console-editor";
export const MIN_ITERATIONS = 4096;
export const MAX_MESSAGE_BYTES = 1 << 20;
export const MAX_ROWS = 1000;
export const MAX_ROW_BYTES = 2 << 20;
export const STATEMENT_DEADLINE_SECONDS = 60;
export const CANCEL_WAIT_SECONDS = 5;
export const CONNECT_SECONDS = 15;
const QUERY_CANCELED = "57014";

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export class PgError extends Error {
  constructor(message, fields = {}) {
    super(message);
    this.name = "PgError";
    this.code = fields.code || null;
    this.severity = fields.severity || null;
    this.detail = fields.detail || null;
    this.hint = fields.hint || null;
    this.position = fields.position || null;
    this.closeCode = fields.closeCode || null;
    this.deadline = Boolean(fields.deadline);
  }
}

function int32(value) {
  const bytes = new Uint8Array(4);
  new DataView(bytes.buffer).setInt32(0, value);
  return bytes;
}

function cstring(text) {
  const bytes = encoder.encode(text);
  const out = new Uint8Array(bytes.length + 1);
  out.set(bytes);
  return out;
}

function concat(parts) {
  const out = new Uint8Array(parts.reduce((total, part) => total + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function message(type, ...parts) {
  const body = concat(parts);
  return concat([encoder.encode(type), int32(body.length + 4), body]);
}

export function startupMessage(user, database) {
  const parameters = concat([
    cstring("user"), cstring(user), cstring("database"), cstring(database),
    cstring("application_name"), cstring(APPLICATION_NAME), new Uint8Array([0]),
  ]);
  return concat([int32(parameters.length + 8), int32(PROTOCOL_3_0), parameters]);
}

export function cancelRequest(pid, key) {
  return concat([int32(16), int32(CANCEL_REQUEST_CODE), int32(pid), int32(key)]);
}

function fromBase64(text) {
  const binary = atob(text);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

// The client-final message and the signature the server must answer with, for
// `serverFirst` after `clientFirstBare` (RFC 5802 section 3). Pure, so a proof
// compares it with Python's computation for a fixed exchange.
export async function clientFinal(password, clientFirstBare, serverFirst) {
  const nonce = clientFirstBare.split("r=")[1];
  const attributes = Object.fromEntries(
    serverFirst.split(",").map((part) => [part.slice(0, 1), part.slice(2)]),
  );
  const iterations = Number(attributes.i);
  if (!attributes.r || !attributes.r.startsWith(nonce) || attributes.r.length <= nonce.length) {
    throw new PgError("the server's nonce does not extend this client's; nothing was sent");
  }
  if (!attributes.s) {
    throw new PgError("the server sent no salt; nothing was sent");
  }
  if (!Number.isInteger(iterations) || iterations < MIN_ITERATIONS) {
    throw new PgError(`the server asked for ${attributes.i} iterations, fewer than ${MIN_ITERATIONS}; nothing was sent`);
  }
  const keys = await scramKeys(password, fromBase64(attributes.s), iterations);
  const withoutProof = `c=biws,r=${attributes.r}`;
  const authMessage = `${clientFirstBare},${serverFirst},${withoutProof}`;
  const signature = new Uint8Array(await hmac(keys.storedKey, authMessage));
  const clientKey = new Uint8Array(keys.clientKey);
  const proof = clientKey.map((byte, index) => byte ^ signature[index]);
  return {
    message: `${withoutProof},p=${base64(proof)}`,
    serverSignature: base64(await hmac(keys.serverKey, authMessage)),
  };
}

class Reader {
  constructor() {
    this.buffer = new Uint8Array(0);
    this.offset = 0;
    this.wake = null;
    this.failure = null;
  }

  push(chunk) {
    const rest = this.buffer.subarray(this.offset);
    const next = new Uint8Array(rest.length + chunk.length);
    next.set(rest);
    next.set(chunk, rest.length);
    this.buffer = next;
    this.offset = 0;
    if (this.wake) this.wake();
  }

  fail(error) {
    if (!this.failure) this.failure = error;
    if (this.wake) this.wake();
  }

  async next() {
    for (;;) {
      if (this.failure) throw this.failure;
      const available = this.buffer.length - this.offset;
      if (available >= 5) {
        const view = new DataView(this.buffer.buffer, this.buffer.byteOffset + this.offset);
        const length = view.getInt32(1);
        if (length < 4 || length > MAX_MESSAGE_BYTES) {
          this.fail(new PgError(`a message of ${length} bytes is outside the editor's bound of 4 bytes to 1 MiB; the connection was closed`));
          throw this.failure;
        }
        if (available >= 1 + length) {
          const type = String.fromCharCode(this.buffer[this.offset]);
          const body = this.buffer.slice(this.offset + 5, this.offset + 1 + length);
          this.offset += 1 + length;
          return { type, body };
        }
      }
      await new Promise((resolve) => { this.wake = resolve; });
      this.wake = null;
    }
  }
}

function strings(body, offset = 0) {
  const out = [];
  while (offset < body.length && body[offset] !== 0) {
    const end = body.indexOf(0, offset);
    out.push(decoder.decode(body.subarray(offset, end)));
    offset = end + 1;
  }
  return out;
}

function fields(body) {
  const found = {};
  let offset = 0;
  while (offset < body.length && body[offset] !== 0) {
    const key = String.fromCharCode(body[offset]);
    const end = body.indexOf(0, offset + 1);
    found[key] = decoder.decode(body.subarray(offset + 1, end));
    offset = end + 1;
  }
  return {
    severity: found.V || found.S || null,
    code: found.C || null,
    message: found.M || "",
    detail: found.D || null,
    hint: found.H || null,
    position: found.P || null,
  };
}

function columns(body) {
  const view = new DataView(body.buffer, body.byteOffset);
  const count = view.getInt16(0);
  const out = [];
  let offset = 2;
  for (let index = 0; index < count; index++) {
    const end = body.indexOf(0, offset);
    out.push({ name: decoder.decode(body.subarray(offset, end)), type: view.getInt32(end + 7) });
    offset = end + 19;
  }
  return out;
}

function row(body) {
  const view = new DataView(body.buffer, body.byteOffset);
  const count = view.getInt16(0);
  const out = new Array(count);
  let offset = 2;
  for (let index = 0; index < count; index++) {
    const length = view.getInt32(offset);
    offset += 4;
    if (length < 0) {
      out[index] = null;
    } else {
      out[index] = decoder.decode(body.subarray(offset, offset + length));
      offset += length;
    }
  }
  return out;
}

function closeError(event) {
  return new PgError(`the relay closed the session (${event.code})`, { closeCode: event.code });
}

function opened(socket) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new PgError("the relay did not answer"));
      socket.close();
    }, CONNECT_SECONDS * 1000);
    socket.onopen = () => { clearTimeout(timer); resolve(); };
    // A refused handshake fires `error` and, in some runtimes, never `close`.
    socket.onerror = () => { clearTimeout(timer); reject(new PgError("the relay refused the session", { closeCode: 1006 })); };
    socket.onclose = (event) => { clearTimeout(timer); reject(closeError(event)); };
  });
}

async function authenticate(socket, reader, password) {
  const code = (body) => new DataView(body.buffer, body.byteOffset).getInt32(0);
  let next = await reader.next();
  if (next.type === "E") throw new PgError(fields(next.body).message, fields(next.body));
  if (next.type !== "R" || code(next.body) !== 10) {
    const asked = next.type === "R" ? `authentication ${code(next.body)}` : `message ${next.type}`;
    throw new PgError(`the server asked for ${asked}; this client speaks only SCRAM-SHA-256`);
  }
  if (!strings(next.body, 4).includes("SCRAM-SHA-256")) {
    throw new PgError("the server does not offer SCRAM-SHA-256; this client speaks nothing else");
  }
  const nonce = base64(crypto.getRandomValues(new Uint8Array(18)));
  const clientFirstBare = `n=,r=${nonce}`;
  const first = encoder.encode(`n,,${clientFirstBare}`);
  socket.send(message("p", cstring("SCRAM-SHA-256"), int32(first.length), first));
  next = await reader.next();
  if (next.type === "E") throw new PgError(fields(next.body).message, fields(next.body));
  if (next.type !== "R" || code(next.body) !== 11) throw new PgError("the server skipped SASLContinue");
  const final = await clientFinal(password, clientFirstBare, decoder.decode(next.body.subarray(4)));
  socket.send(message("p", encoder.encode(final.message)));
  next = await reader.next();
  if (next.type === "E") throw new PgError(fields(next.body).message, fields(next.body));
  if (next.type !== "R" || code(next.body) !== 12) {
    throw new PgError("the server did not prove it knows the password; refused before AuthenticationOk");
  }
  if (decoder.decode(next.body.subarray(4)) !== `v=${final.serverSignature}`) {
    throw new PgError("the server's signature did not verify; refused before AuthenticationOk");
  }
  next = await reader.next();
  if (next.type === "E") throw new PgError(fields(next.body).message, fields(next.body));
  if (next.type !== "R" || code(next.body) !== 0) throw new PgError("the server did not accept the proof");
}

// One connection to `host` through `relay` (`wss://sql.<zone>`), as `user`.
export async function connect({ relay, host, user, database, password, deadlineSeconds = STATEMENT_DEADLINE_SECONDS }) {
  const url = `${relay}/v1/door/${host}`;
  const socket = new WebSocket(url);
  socket.binaryType = "arraybuffer";
  await opened(socket);
  const reader = new Reader();
  socket.onmessage = (event) => reader.push(new Uint8Array(event.data));
  socket.onclose = (event) => reader.fail(closeError(event));
  socket.onerror = () => reader.fail(new PgError("the relay connection failed", { closeCode: 1006 }));
  socket.send(startupMessage(user, database));
  try {
    await authenticate(socket, reader, password);
  } catch (error) {
    socket.close(1000);
    throw error;
  }
  const connection = new Connection(socket, reader, url, deadlineSeconds);
  for (;;) {
    const next = await reader.next();
    if (next.type === "S") {
      const [name, value] = strings(next.body);
      connection.parameters[name] = value;
    } else if (next.type === "K") {
      const view = new DataView(next.body.buffer, next.body.byteOffset);
      connection.pid = view.getInt32(0);
      connection.key = view.getInt32(4);
    } else if (next.type === "E") {
      socket.close(1000);
      throw new PgError(fields(next.body).message, fields(next.body));
    } else if (next.type === "Z") {
      return connection;
    }
  }
}

function newResult(described) {
  return { columns: described, rows: [], command: null, notices: [], truncated: false, bytes: 0 };
}

class Connection {
  constructor(socket, reader, url, deadlineSeconds) {
    this.socket = socket;
    this.reader = reader;
    this.url = url;
    this.deadlineSeconds = deadlineSeconds;
    this.parameters = {};
    this.pid = null;
    this.key = null;
    this.busy = false;
    this.pendingCancel = null;
  }

  // Every result of `text`, in order; an ErrorResponse is thrown after the
  // results before it, once the server is ready again.
  async *query(text) {
    if (this.busy) throw new PgError("a statement is already running");
    if (text.includes("\0")) throw new PgError("a statement cannot hold a NUL character");
    const bytes = encoder.encode(text);
    if (bytes.length + 6 > MAX_MESSAGE_BYTES) throw new PgError("a statement longer than 1 MiB is not sent");
    if (this.pendingCancel) await this.pendingCancel;
    this.busy = true;
    let ready = false;
    let failure = null;
    let capped = false;
    let deadline = false;
    let current = newResult(null);
    const timer = setTimeout(() => { deadline = true; this.cancel(); }, this.deadlineSeconds * 1000);
    try {
      this.socket.send(message("Q", bytes, new Uint8Array([0])));
      while (!ready) {
        const next = await this.reader.next();
        switch (next.type) {
          case "T":
            current = newResult(columns(next.body));
            break;
          case "D":
            if (current.truncated) break;
            if (current.rows.length >= MAX_ROWS || current.bytes + next.body.length > MAX_ROW_BYTES) {
              current.truncated = true;
              capped = true;
              this.cancel();
            } else {
              current.bytes += next.body.length;
              current.rows.push(row(next.body));
            }
            break;
          case "C":
            current.command = strings(next.body)[0];
            yield current;
            current = newResult(null);
            break;
          case "I":
            yield { ...current, empty: true };
            current = newResult(null);
            break;
          case "E":
            failure = fields(next.body);
            break;
          case "N":
            current.notices.push(fields(next.body));
            break;
          case "G":
            this.socket.send(message("f", cstring("the SQL editor sends no COPY data")));
            break;
          case "H":
            current.notices.push({ severity: "NOTICE", message: "COPY output is not shown in the editor" });
            break;
          case "S": {
            const [name, value] = strings(next.body);
            this.parameters[name] = value;
            break;
          }
          case "d":
          case "c":
          case "A":
            break;
          case "Z":
            ready = true;
            break;
          default:
            this.close();
            throw new PgError(`the server sent a message this client does not speak (${next.type}); the connection was closed`);
        }
      }
    } finally {
      clearTimeout(timer);
      if (!ready && !this.reader.failure) {
        // The caller stopped reading early: end the statement and drain to ReadyForQuery.
        this.cancel();
        for (;;) {
          const next = await this.reader.next();
          if (next.type === "Z") break;
        }
      }
      this.busy = false;
    }
    if (current.columns && (current.rows.length || current.truncated)) yield current;
    if (failure && !(failure.code === QUERY_CANCELED && capped && !deadline)) {
      throw new PgError(failure.message, { ...failure, deadline: deadline && failure.code === QUERY_CANCELED });
    }
  }

  // One cancel at a time, each its own relay session; resolves when that session closes.
  cancel() {
    if (!this.pendingCancel) {
      this.pendingCancel = this.sendCancel().finally(() => { this.pendingCancel = null; });
    }
    return this.pendingCancel;
  }

  async sendCancel() {
    const socket = new WebSocket(this.url);
    socket.binaryType = "arraybuffer";
    try {
      await opened(socket);
    } catch {
      return false;
    }
    const closed = new Promise((resolve) => {
      const timer = setTimeout(() => { socket.close(1000); resolve(false); }, CANCEL_WAIT_SECONDS * 1000);
      socket.onclose = () => { clearTimeout(timer); resolve(true); };
      socket.onerror = () => { clearTimeout(timer); resolve(false); };
    });
    socket.send(cancelRequest(this.pid, this.key));
    return closed;
  }

  close() {
    try {
      this.socket.send(message("X"));
    } catch {
      // already closed
    }
    this.socket.close(1000);
  }
}

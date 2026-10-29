// The SQL editor's decisions (Session 44, ADR 0285; rig 44e): state in, decision
// out, no DOM. It imports nothing -- `app.js` passes `call` (api.js) and
// `connect` (pg.js) in -- so a test runs it in Node with stand-ins for both.
//
// What it decides: whether a project offers the editor at all (its doors, from
// the connections answer -- the page types no host, D2738); whether a door may
// be opened now (only the control API can say a project is asleep: a sleeping
// door and a wrong name fail alike in the handshake, D2737); and the sentence
// for every way a session can end -- a close of the socket in the words the
// page hands in (`closeSentence`, messages.js's, since Session 47 Run 6, D3012).
// The password is read by `readPassword` at the moment of connecting and
// handed to `connect` and nothing else (D2756).

export const DEADLINE_SENTENCE = "A statement still running after 60 seconds is cancelled.";
export const TRUNCATED_SENTENCE = "Showing the first 1,000 rows; the rest were not read.";

const ASLEEP = new Set(["sleeping", "suspending", "starting"]);
const OPEN = new Set(["ready", "updating"]);
const NAMED = new Set(["creating", "deleting", "deleted"]);

// What the page says instead of opening a socket; null when the door may open.
export function stateSentence(state) {
  if (OPEN.has(state)) return null;
  if (ASLEEP.has(state)) return "This project is asleep. Wake it from Settings, then connect.";
  if (NAMED.has(state)) return `The project is ${state}; nothing was opened.`;
  return "The project's state could not be read; nothing was opened.";
}

// The two doors from the connections answer, or `offered: false` where the
// project has none (`409 not_available`, the Connect page's own answer).
export async function doors(call, key) {
  let answer;
  try {
    answer = await call("GET", `/projects/${encodeURIComponent(key)}/connections`);
  } catch (error) {
    if (error.status === 409 && error.code === "not_available") return { offered: false };
    throw error;
  }
  const pick = (name, found) => ({ name, host: found.host, port: found.port, user: found.user, database: found.database });
  return { offered: true, doors: [pick("pooled", answer.pooled), pick("direct", answer.direct)] };
}

// The sentence for a session that ended or never began. A close of the
// relay's socket is worded by the page's `closeSentence` (messages.js's
// CLOSES, ADR 0297, D3012), handed in as `call` and `connect` are: this file
// words no close code itself.
export function endSentence(error, closeSentence) {
  if (error && error.closeCode && closeSentence) return closeSentence(error.closeCode);
  if (error && (error.code === "08P01" || error.code === "28P01")) return "The database refused the password.";
  if (error && error.code) return `${error.message} (${error.code})`;
  return error && error.message ? error.message : "The session ended.";
}

// Read the project's state, then -- only if it may -- the password, then connect.
export async function openDoor({ call, connect, relay, key, door, readPassword, closeSentence }) {
  let project;
  try {
    project = await call("GET", `/projects/${encodeURIComponent(key)}`);
  } catch {
    return { opened: false, say: stateSentence("unknown") };
  }
  const say = stateSentence(project.state);
  if (say) return { opened: false, say };
  const password = readPassword();
  try {
    const session = await connect({ relay, host: door.host, user: door.user, database: door.database, password });
    return { opened: true, session };
  } catch (error) {
    return { opened: false, say: endSentence(error, closeSentence) };
  }
}

// One statement's results, as plain values the page renders as text.
export async function runStatement(session, text, onResult, closeSentence) {
  try {
    for await (const result of session.query(text)) {
      onResult({
        columns: result.columns ? result.columns.map((column) => column.name) : [],
        rows: result.rows,
        command: result.command,
        notices: result.notices.map((notice) => notice.message),
        truncated: result.truncated ? TRUNCATED_SENTENCE : null,
      });
    }
    return null;
  } catch (error) {
    if (error.deadline) return "The statement ran for 60 seconds and was cancelled.";
    return endSentence(error, closeSentence);
  }
}

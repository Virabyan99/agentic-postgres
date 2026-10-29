// What a person copies from Connect and the SQL editor, made DOM-free (Session
// 47 Run 6, ADR 0295 decisions 6-8) so Node can drive it
// (tests/contract/test_console_connect.py). It imports nothing and holds no
// snippet text: the snippets are the server's (`GET .../connections`, D2991),
// and this file only fills the server's own placeholder with a password the
// page made, inside the page.
//
// What it decides: a door's connection string and its labelled parts; which
// of a snippet's placeholders belong to which door; and a result as CSV.

// The connection string of a door, from the members the server served; with
// the password only when the caller hands one (the shown-once panel).
export function connectionString(door, password) {
  const secret = password ? `:${encodeURIComponent(password)}` : "";
  return `postgresql://${door.user}${secret}@${door.host}:${door.port}/${door.database}?sslmode=verify-full`;
}

// The served clients that take `connectionString`'s text exactly as it is
// (D3019, Session 47 Run 9): measured by tests/contract/test_connection_
// snippets.py, each connected with the server's CA where it reads roots by
// default, and refused the same text for a name the certificate does not
// carry. Connect says so beside the string and points every other client to
// its own tab: libpq (psql, psycopg) reads ~/.postgresql/root.crt without
// `sslrootcert`, and node-postgres reads `sslrootcert=system` as a file.
export const STRING_TAKEN_BY = ["node-pg", "drizzle", "go-pgx"];

// The parts of a door's connection string, each a value a person copies, with
// what it is. The password is not a part: it is made on this page, shown once.
export function parts(door) {
  return [
    { name: "user", label: "User", value: door.user, about: "The database role this door signs in as." },
    { name: "host", label: "Host", value: door.host, about: "This door's name; the certificate is issued for it." },
    { name: "port", label: "Port", value: String(door.port), about: "Both doors listen on the same port." },
    { name: "database", label: "Database", value: door.database, about: "The project's database." },
    { name: "tls", label: "TLS", value: "sslmode=verify-full", about: "Encrypted, and the server's name is checked." },
  ];
}

function named(line, user) {
  return new RegExp(`(^|[^A-Za-z0-9_])${user.replace(/[^A-Za-z0-9_]/g, "\\$&")}($|[^A-Za-z0-9_])`).test(line);
}

// Each placeholder belongs to the door whose user its own line names, or --
// when its line names none -- the door named by the nearest line above it
// (a client's configuration names its user before its password). A line that
// names both doors, or a placeholder no line above attributes, is left as it
// is. Only `user`'s placeholders are filled; `others` are the other doors'
// users. In a URL the password is percent-encoded.
export function fillPassword(text, { placeholder, user, others, password }) {
  if (!password || !placeholder || typeof text !== "string" || !text.includes(placeholder)) {
    return text;
  }
  const doorOf = (line) => {
    const mine = named(line, user);
    const theirs = others.some((other) => other && named(line, other));
    return mine && !theirs ? "mine" : theirs && !mine ? "theirs" : mine ? "both" : null;
  };
  let above = null;
  return text.split("\n").map((line) => {
    const own = doorOf(line);
    const door = own || above;
    if (own) {
      above = own;
    }
    if (!line.includes(placeholder) || door !== "mine") {
      return line;
    }
    return line.split(placeholder).join(line.includes("://") ? encodeURIComponent(password) : password);
  }).join("\n");
}

// Where a served client's snippet goes and what to install, from the
// connection document's `where` member when it carries one: `{file, install}`
// or a sentence. Absent, it is null and the page draws no line.
export function guide(served, client) {
  const where = served && served.where && typeof served.where === "object" ? served.where[client] : null;
  if (typeof where === "string") {
    return { file: null, install: null, text: where };
  }
  if (!where || typeof where !== "object") {
    return null;
  }
  const file = typeof where.file === "string" ? where.file : null;
  const install = typeof where.install === "string" ? where.install : null;
  return file || install ? { file, install, text: null } : null;
}

// A result as CSV (RFC 4180): a header row, then one line per row, CRLF
// between lines. A field holding a comma, a quote, a line break or a leading
// or trailing space is quoted, its quotes doubled; NULL is an empty unquoted
// field and an empty string an empty quoted one, as PostgreSQL's COPY writes them.
export function csv(columns, rows) {
  const field = (cell) => {
    if (cell === null || cell === undefined) {
      return "";
    }
    const text = String(cell);
    return text === "" || /[",\r\n]|^\s|\s$/.test(text) ? `"${text.replaceAll("\"", "\"\"")}"` : text;
  };
  return [columns, ...rows].map((row) => row.map(field).join(",")).join("\r\n") + "\r\n";
}

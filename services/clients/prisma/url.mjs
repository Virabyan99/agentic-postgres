// Assembling a PostgreSQL URL inside the container, from a credential that
// arrived as a file.
//
// Prisma is the one client here that cannot take a password any other way: it
// has no PGPASSFILE support and no per-field connection options, so the value
// has to end up inside a URL. ADR 0034 settled how that is done -- for dbmate,
// in Session 3 -- and this is the same rule applied a second time: the URL is
// built at run time, inside the process that uses it, from a file mounted into
// the container. No connection string carrying a password exists in this
// repository, in the Compose model, in an image layer, or in an argument vector.
//
// EVERY BYTE OF THE PASSWORD IS PERCENT-ENCODED, not just the bytes that look
// dangerous. Session 3 measured what selective encoding costs: a base64
// credential containing `/` parsed as a path separator and dbmate reported
// `invalid port` -- a message naming neither the password nor the file it came
// from. Total encoding cannot be wrong for an input nobody thought of, and the
// provider chooses this value, not this repository.

import { readFileSync } from "node:fs";

const PROTECTED_SCHEMAS = new Set([
  "api",
  "app",
  "app_private",
  "extensions",
  "public",
  "pg_catalog",
  "information_schema",
]);

// Every byte, as %XX. encodeURIComponent leaves `!'()*-._~` and the
// alphanumerics alone, which is correct for a URL and is not what is wanted
// here: the property being bought is that no byte of the value can be read as
// URL syntax by any parser, including one that disagrees about which bytes are
// safe.
export function percentEncodeAll(value) {
  return Array.from(Buffer.from(value, "utf8"))
    .map((byte) => `%${byte.toString(16).padStart(2, "0").toUpperCase()}`)
    .join("");
}

export function readSecret(path) {
  // `.replace(/\n+$/, "")` strips trailing newlines and nothing else, matching
  // what `$(cat ...)` does in the pooler's entrypoint and what
  // bin/postgres-bootstrap.py's `.rstrip("\n")` does to the same file. The
  // three readings must agree byte for byte or the role is set to one value and
  // this presents another.
  const raw = readFileSync(path, "utf8").replace(/\n+$/, "");
  if (!raw) throw new Error(`${path} is empty`);
  return raw;
}

/**
 * Build a URL for one transport.
 *
 * `schema` is only ever supplied for the migration URL, and it is refused if it
 * names one of the protected schemas. This is the unprivileged half of plan
 * §4.4's rule: the privileged half creates and drops the disposable schema and
 * records its identity, and this half refuses to point a migration at anything
 * that is not one.
 */
export function databaseUrl({ transport, applicationName, role, secretFile, schema }) {
  for (const [name, value] of Object.entries({ transport, applicationName, role, secretFile })) {
    if (!value) throw new Error(`databaseUrl: ${name} is required`);
  }
  if (!["pooled", "direct"].includes(transport)) {
    throw new Error(`databaseUrl: transport must be pooled or direct, not ${transport}`);
  }

  const host = process.env.PGHOST;
  const port = process.env.PGPORT;
  const database = process.env.PGDATABASE;
  if (!host || !port || !database) {
    throw new Error("databaseUrl: PGHOST, PGPORT and PGDATABASE are required");
  }

  // Refused rather than stripped. `?pgbouncer=true` tells Prisma the far end
  // cannot hold a prepared statement, and it is how a prepared-statement test
  // is made to pass by disabling prepared statements. This pooler runs
  // max_prepared_statements above zero; if that ever stops being true, the
  // fixture must fail rather than quietly become a test of the fallback.
  if (process.env.APG_PRISMA_PGBOUNCER_FLAG) {
    throw new Error(
      "databaseUrl: ?pgbouncer=true is refused. The pooler runs max_prepared_statements " +
        "above zero; setting the flag would turn DBX-002 into a test of the fallback path " +
        "while the report still said Prisma works through the pooler.",
    );
  }

  const parameters = new URLSearchParams({
    // Honest rather than lax, and the same reasoning as dbmate's: this
    // connection crosses a Docker network declared `internal: true`, which has
    // no route off the host, and the cluster serves no TLS certificate for any
    // peer to verify. Over a tunnel, SSH is the encrypted channel.
    sslmode: "disable",
    application_name: applicationName,
  });

  if (schema !== undefined) {
    if (!/^[a-z][a-z0-9_]{2,47}$/.test(schema)) {
      throw new Error(`databaseUrl: not a usable schema name: ${schema}`);
    }
    if (PROTECTED_SCHEMAS.has(schema)) {
      throw new Error(
        `databaseUrl: refusing to migrate into the protected schema ${schema}. ` +
          "Prisma Migrate creates and drops objects; this fixture points at a disposable " +
          "schema created for it and at nothing else.",
      );
    }
    parameters.set("schema", schema);
  }

  const password = percentEncodeAll(readSecret(secretFile));
  return `postgresql://${role}:${password}@${host}:${port}/${database}?${parameters.toString()}`;
}

// Prisma Migrate through the DIRECT transport (DBX-001).
//
// The configuration here is the one an application actually ships, not a
// simplified one: `url` is the pooled runtime URL and `directUrl` is the direct
// migration URL. That is the whole content of the claim -- Prisma Client uses
// one and Prisma Migrate uses the other, from a single schema.prisma, with no
// operator step in between. Setting both to the direct URL would make DBX-001
// true by construction and prove nothing about `directUrl`.
//
// Which means this mode needs both credentials, and that is deliberate rather
// than incidental: a fixture that only held the migration credential would be
// testing a configuration nobody deploys.
//
// `migrate deploy`, not `migrate dev`. `dev` needs a shadow database it may
// create and drop, and `migration_user` holds no database CREATE by design --
// so `dev` cannot run against this deployment at all, and `deploy` is the
// production command in any case.
//
// Exit codes: 0 applied, 2 bad input, and the Prisma CLI's own status otherwise.

import { spawnSync } from "node:child_process";
import { databaseUrl } from "./url.mjs";

function required(name) {
  const value = process.env[name];
  if (!value) {
    console.error(`client-prisma: ${name} is required`);
    process.exit(2);
  }
  return value;
}

const schema = required("APG_DISPOSABLE_SCHEMA");
const migrationRole = required("APG_MIGRATION_ROLE");
const runtimeRole = required("PGUSER");
const pooledHost = required("APG_POOLED_HOST");
const pooledPort = required("APG_POOLED_PORT");
const directHost = required("APG_DIRECT_HOST");
const directPort = required("APG_DIRECT_PORT");

// The two URLs differ in host, in port, in role and in credential. Built
// separately, from separate endpoint values, so that none of those four can be
// shared by accident -- the failure that would matter most is a `directUrl`
// that quietly pointed at the pooler, which would migrate through transaction
// pooling and break DDL and advisory-lock semantics while appearing to work.
const directUrl = withEndpoint(directHost, directPort, () =>
  databaseUrl({
    transport: "direct",
    applicationName: "apg-client-prisma-migrate",
    role: migrationRole,
    secretFile: "/run/secrets/migration_user_password",
    schema,
  }),
);

const pooledUrl = withEndpoint(pooledHost, pooledPort, () =>
  databaseUrl({
    transport: "pooled",
    applicationName: "apg-client-prisma-runtime",
    role: runtimeRole,
    secretFile: "/run/secrets/app_runtime_password",
  }),
);

if (directHost === pooledHost && directPort === pooledPort) {
  console.error(
    "client-prisma: the direct and pooled endpoints are the same. DBX-001 is a claim " +
      "about two transports; proving it against one would be true by construction.",
  );
  process.exit(2);
}

function withEndpoint(host, port, build) {
  const previous = { host: process.env.PGHOST, port: process.env.PGPORT };
  process.env.PGHOST = host;
  process.env.PGPORT = port;
  try {
    return build();
  } finally {
    for (const [name, value] of [
      ["PGHOST", previous.host],
      ["PGPORT", previous.port],
    ]) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }
}

console.log(`client-prisma: migrating into the disposable schema ${schema} as ${migrationRole}`);

// Passed through the child's environment and never on its command line. A URL
// carrying a percent-encoded password in argv is readable from /proc by anyone
// sharing the uid, which in a container is every process in it.
const result = spawnSync("node_modules/.bin/prisma", ["migrate", "deploy"], {
  stdio: "inherit",
  env: { ...process.env, DATABASE_URL: pooledUrl, DIRECT_URL: directUrl },
});

if (result.error) {
  console.error(`client-prisma: ${result.error.message}`);
  process.exit(6);
}

// The same closing line every other fixture prints, and it is a contract rather
// than a courtesy: the harness asserts on it because an exit status of 0 from a
// CLI that was never reached would look identical to success. Run 9 found the
// gap from the other side -- this mode exited 0, having genuinely applied the
// migration, and the assertion failed for want of a line nobody had written.
if (result.status === 0) {
  console.log("client-prisma: every check passed");
}
process.exit(result.status ?? 6);

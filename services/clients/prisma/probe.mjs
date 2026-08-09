// Client compatibility fixture: Prisma Client through the pooled transport.
//
// The fourth client, and the one with the most between it and the boundary.
// What it proves that the other three do not:
//
//   * DBX-002 -- Prisma Client operates through the pooler, with prepared
//     statements ENABLED. The pooler runs `max_prepared_statements` above zero
//     (measured in Run 1), so `?pgbouncer=true` -- Prisma's flag for telling it
//     the far end cannot keep a prepared statement -- is not needed and is
//     REFUSED here. The plan's rule is that a prepared-statement test may not be
//     made to pass by disabling prepared statements, and this is the fixture
//     that rule was written for: setting that flag would turn a real capability
//     test into a test of the fallback, and the report would still say Prisma
//     works through the pooler.
//
//   * The claim mechanism through an ORM. Prisma has no API for a session GUC,
//     so the claim is set with $executeRaw inside $transaction -- an interactive
//     transaction, which is what keeps the SET LOCAL and the query on the same
//     pooled server connection. Under transaction pooling that is the only
//     construction that can work, and it is what an application actually writes.
//
// Every value is a tagged-template parameter. Prisma's $queryRaw and $executeRaw
// tagged forms send parameters over the extended query protocol; the
// $queryRawUnsafe and $executeRawUnsafe forms interpolate, and neither appears
// in this file.
//
// Exit codes: 0 every check passed, 2 bad input, 6 a check failed.

import { PrismaClient } from "@prisma/client";
import { databaseUrl } from "./url.mjs";

const TRANSPORT = required("APG_TRANSPORT");
const USER_A = required("APG_USER_A");
const USER_B = required("APG_USER_B");
const APPLICATION_NAME = `apg-client-prisma-${TRANSPORT}`;

function required(name) {
  const value = process.env[name];
  if (!value) {
    console.error(`client-prisma: ${name} is required`);
    process.exit(2);
  }
  return value;
}

function fail(label, expected, got) {
  console.error(`client-prisma: ${label}: expected ${expected}, got ${got}`);
  process.exit(6);
}

function expect(label, expected, got) {
  if (String(got) !== String(expected)) fail(label, expected, got);
  console.log(`  ok    ${label}`);
}

const url = databaseUrl({
  transport: TRANSPORT,
  applicationName: APPLICATION_NAME,
  role: process.env.PGUSER,
  secretFile: "/run/secrets/app_runtime_password",
});

const prisma = new PrismaClient({ datasources: { db: { url } } });

async function main() {
  console.log(
    `client-prisma: ${process.env.PGDATABASE} over the ${TRANSPORT} transport as ${process.env.PGUSER}`,
  );

  // 1. The application name survives Prisma's connection handling and the
  //    pooler. Read back from the server, which is the only place it counts.
  const named = await prisma.$queryRaw`
    SELECT application_name FROM pg_stat_activity WHERE pid = pg_backend_pid()`;
  expect("application_name reaches the server", APPLICATION_NAME, named[0].application_name);

  // 2 and 3. A write under each user's claim. $transaction with a callback is
  //          an interactive transaction: the SET LOCAL and the insert run on one
  //          server connection, which is what transaction pooling requires and
  //          what an application would write.
  for (const [label, userId, title] of [
    ["user A", USER_A, "prisma fixture note (A)"],
    ["user B", USER_B, "prisma fixture note (B)"],
  ]) {
    const owner = await prisma.$transaction(async (tx) => {
      await tx.$executeRaw`SELECT set_config('app.user_id', ${userId}, true)`;
      const created = await tx.$queryRaw`SELECT (api.create_note(${title})).owner_id AS owner_id`;
      return created[0].owner_id;
    });
    expect(`${label} writes under its own claim`, userId, owner);
  }

  // 4. Isolation as a pair of counts. Either alone is satisfiable by something
  //    other than a working policy: an empty table, or no policy at all.
  for (const [label, userId] of [
    ["user A", USER_A],
    ["user B", USER_B],
  ]) {
    const counted = await prisma.$transaction(async (tx) => {
      await tx.$executeRaw`SELECT set_config('app.user_id', ${userId}, true)`;
      return tx.$queryRaw`
        SELECT count(*) FILTER (WHERE owner_id = ${userId}::uuid) AS mine,
               count(*) FILTER (WHERE owner_id <> ${userId}::uuid) AS theirs
          FROM api.notes`;
    });
    const { mine, theirs } = counted[0];
    if (Number(mine) < 1) fail(`${label} sees its own rows`, ">= 1", mine);
    expect(`${label} sees none of the other user's rows`, "0", String(theirs));
  }

  // 5. No claim, no rows. After the writes, so an empty table is not what makes
  //    it pass.
  const unclaimed = await prisma.$transaction(
    async (tx) => tx.$queryRaw`SELECT count(*) AS visible FROM api.notes`,
  );
  expect("a transaction with no claim sees nothing", "0", String(unclaimed[0].visible));

  // 6. A prepared statement is reusable across the pooler. Prisma issues named
  //    prepared statements by default; running the same parameterized query
  //    twice in separate transactions crosses at least one pooled server
  //    handover in a saturated pool. This check does not PROVE the handover
  //    happened -- that requires observing the backend pid change, which Run 9
  //    does under load. What it proves here is the thing that fails first if
  //    max_prepared_statements were zero: the second execution errors with
  //    "prepared statement ... already exists".
  for (const attempt of [1, 2]) {
    const repeated = await prisma.$queryRaw`SELECT ${attempt}::int AS attempt`;
    expect(`a named prepared statement is reusable (attempt ${attempt})`, attempt, repeated[0].attempt);
  }

  // 7. The private schema is not addressable. Attempted, not asked of the
  //    catalog: D103 measured has_table_privilege returning true for app.notes
  //    while the read is denied.
  let reachable = true;
  try {
    await prisma.$queryRaw`SELECT count(*) FROM app.notes`;
  } catch (error) {
    reachable = false;
    if (!/schema "?app"?/.test(String(error.message))) {
      fail("app is refused for the documented reason", "permission denied for schema app", error.message);
    }
  }
  if (reachable) fail("app.notes is not readable", "permission denied", "rows returned");
  console.log("  ok    app.notes is not readable, whatever the table privilege says");

  await prisma.$disconnect();
  console.log("client-prisma: every check passed");
}

main().catch(async (error) => {
  await prisma.$disconnect().catch(() => {});
  console.error(`client-prisma: ${error.message}`);
  process.exit(6);
});

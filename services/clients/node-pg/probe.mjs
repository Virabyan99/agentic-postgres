// Client compatibility fixture: node-postgres.
//
// The same six checks as services/clients/psql/probe.sh, through a driver that
// is not libpq. That is the point of running both: psql answers "what does the
// protocol offer", and this answers "what does a driver that reimplements the
// protocol actually do with it".
//
// THE CREDENTIAL IS NOT AN ENVIRONMENT VARIABLE. node-postgres depends on
// `pgpass` (1.0.5 in the committed lock file, a transitive dependency of pg
// 8.16.3), which reads `process.env.PGPASSFILE` when no password is supplied.
// So this fixture passes no password at all and lets the driver find the file
// the entrypoint wrote -- the same file `bin/connect.sh exec` provides. That
// was read off the resolved dependency tree rather than assumed: a driver
// without pgpass support would need PGPASSWORD, and PGPASSWORD is banned from
// this model outright.
//
// Exit codes: 0 every check passed, 2 bad input, 6 a check failed.

import pg from "pg";

const TRANSPORT = required("APG_TRANSPORT");
const USER_A = required("APG_USER_A");
const USER_B = required("APG_USER_B");
const APPLICATION_NAME = `apg-client-node-pg-${TRANSPORT}`;

function required(name) {
  const value = process.env[name];
  if (!value) {
    console.error(`client-node-pg: ${name} is required`);
    process.exit(2);
  }
  return value;
}

function fail(label, expected, got) {
  console.error(`client-node-pg: ${label}: expected ${expected}, got ${got}`);
  process.exit(6);
}

function expect(label, expected, got) {
  // Compared with Object.is on strings, never on a truthy value. A count that
  // arrives as the string "0" is truthy in JavaScript, which is precisely the
  // way an isolation check passes while measuring nothing.
  if (String(got) !== String(expected)) {
    fail(label, expected, got);
  }
  console.log(`  ok    ${label}`);
}

if (!["pooled", "direct"].includes(TRANSPORT)) {
  console.error(`client-node-pg: APG_TRANSPORT must be pooled or direct, not ${TRANSPORT}`);
  process.exit(2);
}

// PGHOST, PGPORT, PGUSER and PGDATABASE come from the environment the way libpq
// reads them; pg honours all four. `application_name` is set here rather than
// left to the caller because it is what makes a pooled server connection
// attributable in pg_stat_activity.
const client = new pg.Client({ application_name: APPLICATION_NAME });

// Every statement below is parameterized. There is no string concatenation into
// SQL anywhere in this file, and a claim is set with set_config(..., true)
// rather than `SET LOCAL`, because SET takes no parameters -- which is the
// reason a driver that only offered SET would have to interpolate.
async function claim(userId) {
  await client.query("SELECT set_config('app.user_id', $1, true)", [userId]);
}

async function main() {
  await client.connect();
  console.log(
    `client-node-pg: ${process.env.PGDATABASE} over the ${TRANSPORT} transport as ${process.env.PGUSER}`,
  );

  // 1. The application name survives the transport. Read back from the server,
  //    not from the object that set it.
  const named = await client.query(
    "SELECT application_name FROM pg_stat_activity WHERE pid = pg_backend_pid()",
  );
  expect("application_name reaches the server", APPLICATION_NAME, named.rows[0].application_name);

  // 2 and 3. A write under each user's claim, each inside an explicit
  //          transaction. Explicit because the claim is transaction-local: in
  //          autocommit every statement is its own transaction, so the claim
  //          would be gone before the insert that depends on it.
  for (const [label, userId, title] of [
    ["user A", USER_A, "node-pg fixture note (A)"],
    ["user B", USER_B, "node-pg fixture note (B)"],
  ]) {
    await client.query("BEGIN");
    await claim(userId);
    const created = await client.query("SELECT (api.create_note($1)).owner_id AS owner_id", [
      title,
    ]);
    await client.query("COMMIT");
    expect(`${label} writes under its own claim`, userId, created.rows[0].owner_id);
  }

  // 4. Isolation as a pair of counts. "None of the other user's" alone would be
  //    satisfied by an empty table; "some of my own" alone would be satisfied by
  //    no policy at all.
  for (const [label, userId] of [
    ["user A", USER_A],
    ["user B", USER_B],
  ]) {
    await client.query("BEGIN");
    await claim(userId);
    const counted = await client.query(
      `SELECT count(*) FILTER (WHERE owner_id = $1::uuid) AS mine,
              count(*) FILTER (WHERE owner_id <> $1::uuid) AS theirs
         FROM api.notes`,
      [userId],
    );
    await client.query("COMMIT");
    const { mine, theirs } = counted.rows[0];
    if (Number(mine) < 1) fail(`${label} sees its own rows`, ">= 1", mine);
    expect(`${label} sees none of the other user's rows`, "0", theirs);
  }

  // 5. No claim, no rows. Run after the writes, so an empty table cannot be
  //    what makes it pass.
  await client.query("BEGIN");
  const unclaimed = await client.query("SELECT count(*) AS visible FROM api.notes");
  await client.query("COMMIT");
  expect("a transaction with no claim sees nothing", "0", unclaimed.rows[0].visible);

  // 6. The private schema is not addressable. Proved by attempting the read,
  //    not by asking the catalog: D103 measured has_table_privilege returning
  //    true for app.notes while the read is denied, because the boundary is the
  //    schema and the table grant is what makes the security-invoker views work.
  await client.query("BEGIN");
  let reachable = true;
  try {
    await client.query("SELECT count(*) FROM app.notes");
  } catch (error) {
    reachable = false;
    if (!/schema "?app"?/.test(error.message)) {
      fail("app is refused for the documented reason", "permission denied for schema app", error.message);
    }
  }
  await client.query("ROLLBACK");
  if (reachable) fail("app.notes is not readable", "permission denied", "rows returned");
  console.log("  ok    app.notes is not readable, whatever the table privilege says");

  await client.end();
  console.log("client-node-pg: every check passed");
}

main().catch((error) => {
  console.error(`client-node-pg: ${error.message}`);
  process.exit(6);
});

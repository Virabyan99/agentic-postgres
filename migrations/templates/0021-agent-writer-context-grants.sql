-- migrate:up
-- The two grants that make `agent_writer` an AGENT rather than only a writer.
--
-- **This is 0021 and not an edit to 0019** (ADR 0091). 0019 and 0020 are both
-- released and both applied on both clusters; a released migration is
-- fix-forward only, whatever it left undone.
--
-- **Why it exists is D508, and it is CLAUDE.md §6 question 5 for the second
-- time in three migrations.** ADR 0118 decided that the agent plane's RPCs are
-- reviewed and unpublished -- `REVOKE ALL ... FROM PUBLIC`, granted to
-- `agent_reader` alone, named under `agent_rpcs` and granted to nobody the
-- OpenAPI document is built as. That decision was correct when it was made and
-- 0018 implemented it exactly: `agent_reader` was then the ONLY agent role.
--
-- Session 9 activated a second one. 0019 gave `agent_writer` everything a
-- WRITE needs -- `USAGE ON SCHEMA app_private`, `EXECUTE` on the pre-request
-- hook, `EXECUTE` on both comparison helpers, `EXECUTE` on both audit
-- functions -- and its own comment says why, quoting the count that made the
-- omission visible: *"grep -c agent_writer on 0018 returns ZERO"*. It then
-- asked that question of the write path and not of the agent path, and
-- `api.mcp_agent_context()` kept the grant list ADR 0118 gave it.
--
-- **Measured on alpha-dev at release f3004fd, as the role and not as a
-- superuser** (ADR 0065/0066), with `agent_reader` making the same call as the
-- control:
--
--     SET LOCAL ROLE <agent_writer>;  SELECT * FROM api.mcp_agent_context();
--       ERROR:  permission denied for function mcp_agent_context
--     SET LOCAL ROLE <agent_reader>;  SELECT * FROM api.mcp_agent_context();
--       (0 rows)                      -- reached it; simply matched nothing
--
-- The control is what makes the first line evidence: without it, "permission
-- denied" cannot be told from a function that is broken for everybody.
--
-- **What that cost is every request, not every write.** ADR 0125 resolves the
-- caller's context ONCE PER REQUEST in `on_request`, before discovery and
-- before execution, and `api.mcp_agent_context()` is the statement it sends. A
-- write agent was therefore refused **before** its scope was checked, before
-- its audit record was opened and before `api.create_note` was reached -- which
-- is why the host gate saw `upstream refused with status 403` on every write,
-- why `app_private.agent_audit` held no row for any of them, and why PostgREST
-- logged nothing: a 403 is not a 5xx.
--
-- **`api.owner_activity_report()` is granted here too, and that is the half a
-- repair aimed only at the observed failure would have missed.** It backs the
-- `run_report` capability, whose `required_scopes` are `[notes:read,
-- tasks:read]`; both are inside `agent_writer`'s ceiling
-- (`notes:read, notes:write, tasks:read, tasks:write, meta:read`), so a write
-- agent may hold them, `discoverable_by` will offer the tool, and the call
-- would have been refused by the same missing grant one step further on.
-- Fixing only what the gate showed would have left the next defect hidden
-- behind the one being fixed, which is what Session 8's trip did seven times.
--
-- **What is NOT here.** No new function, no new table, no widened ceiling and
-- no third agent role. `agent_writer` receives exactly what `agent_reader`
-- already holds on these two functions and nothing beside it: ADR 0118's
-- decision is unchanged and is now applied to both of its subjects rather than
-- to the one that existed when it was written. `app_private.auth_list_agent_audit`
-- is deliberately NOT granted -- ADR 0142 gives the audit record one reader,
-- `auth_service`, and an agent must not read the record that attributes it.
SET LOCAL ROLE {{object_owner}};

-- Both functions are already `REVOKE ALL ... FROM PUBLIC` from 0018, and a
-- targeted REVOKE is not repeated here: it takes nothing from a named grantee
-- (D267) and restating it would suggest this migration changes who may not
-- call these, which it does not. It adds one grantee to each.
GRANT EXECUTE ON FUNCTION api.mcp_agent_context() TO {{agent_writer}};
GRANT EXECUTE ON FUNCTION api.owner_activity_report() TO {{agent_writer}};

RESET ROLE;

-- Nothing in `api` was created, dropped or re-signatured -- two existing
-- functions gained a grantee -- so this is not the stale-schema case the other
-- NOTIFYs in this repository answer.
--
-- It is issued as a PRECAUTION and not on a measurement: PostgREST caches
-- catalog state at startup and on reload, and whether that cache holds function
-- PRIVILEGES has not been measured here. If it does not, this NOTIFY costs one
-- reload of a cache that loads in about 3 ms on this cluster; if it does, its
-- absence would leave a grant that is live in PostgreSQL and invisible over
-- HTTP -- a state whose two halves disagree, which is the more expensive
-- mistake. **Whoever measures it should record the result and delete this
-- paragraph.**
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

-- migrate:up
-- The agent write and audit plane: a durable record, two functions that write
-- it, and the grants the write role never received.
--
-- **This is 0019 and not an edit to 0018 or 0007** (ADR 0091). Two clusters
-- hold both, and a released migration that applies perfectly well is not edited.
--
-- **The two write RPCs below were written from 0007's bodies, not from memory
-- of them** (D270). `api.create_note` and `api.update_task_status` are replaced
-- here to add one conditional INSERT each; everything else -- the AP401 guard,
-- the FOR UPDATE lock, the expected-status comparison, the AP404/AP409/AP422
-- contract and ADR 0057's rule that the SQLSTATE carries the status while
-- nothing caller-reachable carries a HINT or a DETAIL -- is 0007's text
-- unchanged. `CREATE OR REPLACE` on the same signature, so 0007's grants and
-- 0005's REVOKEs survive; dropping and creating would silently revoke
-- `authenticated` and `agent_writer` and look like a permissions problem.
--
-- **What is NOT here: role membership.** The authenticator's membership in the
-- agent-writer role is `GRANT role TO role`, which needs authority the
-- migration plane does not hold (D102, D266). `bin/postgres-bootstrap.py` grants
-- it, and Run 2 is where that happens. This migration grants the privileges;
-- that one decides whether any token may name the role. **They are separate on
-- purpose and this migration must land first** -- privileges granted to a role
-- nothing can assume are inert, while a membership granted before the
-- privileges exist produces a request that fails on the hook instead of on the
-- boundary (D475).
--
-- **What is NOT here: mcp_audit_service.** ADR 0135 decides it stays
-- unactivated rather than deferring the question again: the definer route below
-- needs no service identity, so activating one would put a login role in
-- production to write records that something else writes. It is in no
-- placeholder list and receives no grant here.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The record
-- ---------------------------------------------------------------------------
--
-- Two enums rather than CHECK constraints, for 0007's reason and 0011's: only
-- an enum reaches the generated document, a CHECK appears nowhere in it
-- (ADR 0058), and **a CHECK passes when its expression is NULL** (ADR 0080).
-- In `app_private` rather than `api` because this table is published to nobody
-- -- 0007 put `task_status` in `api` precisely because the served document
-- prints a type's schema-qualified name, and a type in a forbidden schema would
-- print that schema's name in a public artifact. Nothing here is served.
--
-- **`source` is the column that keeps two honest records from looking like one
-- confused one** (ADR 0135). They answer different questions and they see
-- different events:
--
--   `agent_plane` -- what was ATTEMPTED. Written by the runtime before it
--   forwards and closed after. Sees a call refused for a missing scope, which
--   never reaches this database at all.
--
--   `database`    -- what actually CHANGED. Written inside the write RPC's own
--   transaction. Sees a write that reached PostgREST directly without going
--   near the agent plane, which an agent token can do because that is how the
--   plane forwards it (D480).
CREATE TYPE app_private.agent_audit_source AS ENUM ('agent_plane', 'database');

-- `started` is only ever an `agent_plane` row mid-flight. `committed` is only
-- ever a `database` row, and it is the only outcome such a row can carry --
-- measured, and it is the finding that shaped this table (D489): a row written
-- inside the transaction it describes is rolled back with that transaction, so
-- a failed write cannot leave one. There is no arrangement of exception blocks
-- or subtransactions that keeps it; a handler discards its savepoint just as
-- surely as an aborting transaction does. Recording a failed write durably
-- would need an autonomous transaction, which is a second connection, which is
-- the credential this plane does not hold.
CREATE TYPE app_private.agent_audit_outcome AS ENUM
  ('started', 'served', 'refused', 'failed', 'committed');

CREATE TABLE app_private.agent_audit (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source       app_private.agent_audit_source  NOT NULL,
  -- Both NOT NULL, for the reason 0018 gives about `owner_id`: the hook sets
  -- `app.agent_id` and `app.user_id` together or sets neither, so a row that
  -- could not name its principal is a row that must not exist. The functions
  -- below refuse before they reach this constraint, so the NOT NULL is the
  -- second line rather than the error a caller sees.
  agent_id     uuid        NOT NULL,
  owner_id     uuid        NOT NULL,
  tool         text        NOT NULL CHECK (tool <> ''),
  -- The runtime's per-request id (Run 6). `uuid` rather than free text so that
  -- a caller cannot write a sentence into a column an operator will read.
  request_id   uuid,
  -- Already redacted by the runtime, per the capability lock's `audit.redact`.
  -- This column stores what it is given and redacts nothing itself: the lock is
  -- the authority, and a second redaction here would be a second authority over
  -- one rule.
  parameters   jsonb,
  outcome      app_private.agent_audit_outcome NOT NULL,
  row_count    integer     CHECK (row_count IS NULL OR row_count >= 0),
  elapsed_ms   integer     CHECK (elapsed_ms IS NULL OR elapsed_ms >= 0),
  started_at   timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

COMMENT ON TABLE app_private.agent_audit IS
  'Durable agent attribution (ADR 0135). Append-only to every request role: no '
  'role holds INSERT, UPDATE, DELETE or SELECT on it, and the only paths in are '
  'the definer functions below. A `database` row records a committed change and '
  'can record nothing else, because a row written inside the transaction it '
  'describes is rolled back with it (D489); an `agent_plane` row records the '
  'attempt, including the denials and failures that never reach this database.';

-- The admin query endpoint (Run 7) reads by owner and by agent, most recent
-- first. Both indexes exist for that one reader; neither is speculative.
CREATE INDEX agent_audit_owner_started_idx
  ON app_private.agent_audit (owner_id, started_at DESC);
CREATE INDEX agent_audit_agent_started_idx
  ON app_private.agent_audit (agent_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- Writing the record
-- ---------------------------------------------------------------------------
--
-- **Neither function takes a principal, an owner, a role or a scope**, and that
-- absence is the whole of SEC-PARAM-001. Identity is read from the GUCs the
-- pre-request hook set for this transaction -- measured inside a VOLATILE
-- SECURITY DEFINER function on the pinned image, with the control that an unset
-- GUC reads as the empty string rather than NULL, which is why every read here
-- is spelled `nullif(current_setting(...), '')` exactly as 0018 spells it.
--
-- There is no argument for a caller to lie in. A tool name and a parameter
-- document are the only things a caller supplies, and both are what is being
-- audited rather than who is doing it.
CREATE FUNCTION api.agent_audit_begin(
  p_tool       text,
  p_request_id uuid  DEFAULT NULL,
  p_parameters jsonb DEFAULT NULL
)
  RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  acting_agent uuid := nullif(current_setting('app.agent_id', true), '')::uuid;
  acting_owner uuid := nullif(current_setting('app.user_id',  true), '')::uuid;
  new_id       uuid;
BEGIN
  -- Defence in depth rather than the boundary: `authenticated` holds no EXECUTE
  -- on this function, so a human token cannot reach it at all. This refuses the
  -- case where that grant is one day widened by accident.
  IF acting_agent IS NULL OR acting_owner IS NULL THEN
    RAISE EXCEPTION 'AP403: this operation requires an agent identity'
      USING ERRCODE = 'PT403';
  END IF;

  INSERT INTO app_private.agent_audit
    (source, agent_id, owner_id, tool, request_id, parameters, outcome)
  VALUES
    ('agent_plane', acting_agent, acting_owner, p_tool, p_request_id, p_parameters, 'started')
  RETURNING id INTO new_id;

  RETURN new_id;
END $fn$;

-- Closes one record. **Scoped to the calling agent's own rows**, so an agent
-- cannot close, and therefore cannot silently terminate, another agent's
-- record -- the `agent_id` comparison is against the GUC and not against an
-- argument, for the same reason `begin` takes no principal.
--
-- Returns boolean rather than raising when nothing matched. A record that has
-- already been closed, or that belongs to somebody else, is indistinguishable
-- from one that never existed, and distinguishing them would make this function
-- an oracle for other agents' record ids.
CREATE FUNCTION api.agent_audit_complete(
  p_audit_id   uuid,
  p_outcome    text,
  p_elapsed_ms integer DEFAULT NULL,
  p_row_count  integer DEFAULT NULL
)
  RETURNS boolean
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  acting_agent uuid := nullif(current_setting('app.agent_id', true), '')::uuid;
  closed       integer;
BEGIN
  IF acting_agent IS NULL THEN
    RAISE EXCEPTION 'AP403: this operation requires an agent identity'
      USING ERRCODE = 'PT403';
  END IF;

  -- `committed` is refused here: it belongs to a `database` row, which this
  -- function does not write. Accepting it would let the agent plane label its
  -- own attempt as a change that happened.
  IF p_outcome NOT IN ('served', 'refused', 'failed') THEN
    RAISE EXCEPTION 'AP422: an outcome is served, refused or failed'
      USING ERRCODE = 'PT422';
  END IF;

  UPDATE app_private.agent_audit
     SET outcome      = p_outcome::app_private.agent_audit_outcome,
         elapsed_ms   = p_elapsed_ms,
         row_count    = p_row_count,
         completed_at = now()
   WHERE id       = p_audit_id
     AND agent_id = acting_agent
     AND source   = 'agent_plane'
     AND outcome  = 'started';

  GET DIAGNOSTICS closed = ROW_COUNT;
  RETURN closed = 1;
END $fn$;

COMMENT ON FUNCTION api.agent_audit_begin(text, uuid, jsonb) IS
  'Opens one agent_plane audit record and returns its id. Takes no principal: '
  'the agent and its owner come from the GUCs the pre-request hook set, which '
  'is what makes SEC-PARAM-001 structural rather than validated.';
COMMENT ON FUNCTION api.agent_audit_complete(uuid, text, integer, integer) IS
  'Closes one agent_plane audit record belonging to the calling agent. Returns '
  'false rather than raising when nothing matched, so it cannot be used to '
  'discover another agent''s record ids.';

-- ---------------------------------------------------------------------------
-- The write RPCs, replaced -- 0007's bodies plus one conditional INSERT each
-- ---------------------------------------------------------------------------
--
-- The INSERT fires only when `app.agent_id` is set, which the hook does only on
-- the agent branch. **A human caller sets no `app.agent_id` and is unaffected**
-- -- same rows, same errors, same timing, no audit row.
--
-- This is what makes an agent write unauditable by no route (D480): the row is
-- written by the operation itself, so a caller that skips the agent plane and
-- posts to `/rpc/create_note` directly still leaves one. It is also why the row
-- can only say `committed` -- every failure path below RAISEs, and the RAISE
-- takes the row with it (D489).
CREATE OR REPLACE FUNCTION api.create_note(p_title text, p_content text DEFAULT '')
  RETURNS api.notes
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller uuid := app.current_user_id();
  acting_agent uuid := nullif(current_setting('app.agent_id', true), '')::uuid;
  created api.notes;
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: no request identity for this transaction'
      USING ERRCODE = 'PT401';
  END IF;

  INSERT INTO app.notes (owner_id, title, content)
  VALUES (caller, p_title, p_content)
  RETURNING id, owner_id, title, content, created_at, updated_at INTO created;

  IF acting_agent IS NOT NULL THEN
    INSERT INTO app_private.agent_audit
      (source, agent_id, owner_id, tool, outcome, row_count, completed_at)
    VALUES
      ('database', acting_agent, caller, 'create_note', 'committed', 1, now());
  END IF;

  RETURN created;
END $fn$;

CREATE OR REPLACE FUNCTION api.update_task_status(
  p_task_id uuid,
  p_expected_status api.task_status,
  p_new_status api.task_status
)
  RETURNS api.tasks
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller uuid := app.current_user_id();
  acting_agent uuid := nullif(current_setting('app.agent_id', true), '')::uuid;
  observed api.task_status;
  updated api.tasks;
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: no request identity for this transaction'
      USING ERRCODE = 'PT401';
  END IF;

  IF p_new_status = p_expected_status THEN
    RAISE EXCEPTION 'AP422: a status transition must change the status'
      USING ERRCODE = 'PT422';
  END IF;

  -- FOR UPDATE, so a concurrent caller blocks here rather than reading the same
  -- expected status and both proceeding. Without the lock the comparison below
  -- is advisory and the last writer still wins, which is the thing
  -- `p_expected_status` exists to prevent.
  SELECT t.status INTO observed
    FROM app.tasks t
   WHERE t.id = p_task_id AND t.owner_id = caller
     FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no such task' USING ERRCODE = 'PT404';
  END IF;

  IF observed <> p_expected_status THEN
    RAISE EXCEPTION 'AP409: the task is not in the expected status'
      USING ERRCODE = 'PT409';
  END IF;

  UPDATE app.tasks
     SET status = p_new_status, updated_at = now()
   WHERE id = p_task_id AND owner_id = caller
  RETURNING id, owner_id, note_id, title, description, status, created_at, updated_at
       INTO updated;

  IF acting_agent IS NOT NULL THEN
    INSERT INTO app_private.agent_audit
      (source, agent_id, owner_id, tool, outcome, row_count, completed_at)
    VALUES
      ('database', acting_agent, caller, 'update_task_status', 'committed', 1, now());
  END IF;

  RETURN updated;
END $fn$;

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- **This block runs as the object owner** (D285, ADR 0091). The `RESET ROLE` is
-- at the end of the migration, below every statement that requires ownership.
--
-- Targeted revokes rather than the blanket form, for 0018's reason: two
-- functions are created here and each is EXECUTABLE BY PUBLIC the moment it
-- exists (D57, re-measured as D262), `anon` holds USAGE on schema `api` since
-- 0001, and `openapi-mode = follow-privileges` follows a PUBLIC grant and would
-- advertise them in the document an anonymous caller receives.
REVOKE ALL ON FUNCTION api.agent_audit_begin(text, uuid, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.agent_audit_complete(uuid, text, integer, integer) FROM PUBLIC;

-- **The grants agent_writer never received** (D475). 0018 gave the agent-reader
-- role what a request role needs -- USAGE on the private schema, EXECUTE on the
-- hook, EXECUTE on both comparison helpers -- and named five roles because a
-- sixth did not exist as a request role yet. `agent_writer` appears nowhere in
-- 0018. Without these, Run 2's membership produces a request refused by
-- `permission denied for function postgrest_pre_request` rather than by the
-- boundary: EXECUTE requires schema USAGE, and the hook runs AFTER the role
-- switch (measured in 0008), so it runs as this role.
--
-- This is D417's shape one session later, and 0018 already wrote the rule down:
-- *both comparison helpers, to every role that runs the hook*. `role` and
-- `token_use` are independent claims, so every combination of physical role and
-- hook branch is reachable by a request.
GRANT USAGE ON SCHEMA app_private TO {{agent_writer}};

GRANT EXECUTE ON FUNCTION app_private.postgrest_pre_request() TO {{agent_writer}};

GRANT EXECUTE ON FUNCTION
  app_private.agent_claims_are_current(uuid, text, text[], integer) TO {{agent_writer}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_claims_are_current(uuid, text, text[], integer, integer) TO {{agent_writer}};

-- The agent-reader role reaches the read plane and is audited for it, so both
-- audit functions go to both agent roles. Neither goes to `authenticated`,
-- `anon`, `project_admin` or `api_documentation`: a human operation is not
-- audited here, and a function granted to `api_documentation` would appear in
-- the served document (ADR 0118).
GRANT EXECUTE ON FUNCTION api.agent_audit_begin(text, uuid, jsonb)
  TO {{agent_reader}}, {{agent_writer}};
GRANT EXECUTE ON FUNCTION api.agent_audit_complete(uuid, text, integer, integer)
  TO {{agent_reader}}, {{agent_writer}};

-- The agent-writer role reads through the api views like every other request
-- role, and 0007 already granted it SELECT on both and EXECUTE on both write
-- RPCs. Nothing about the table itself is granted to anybody: no request role
-- holds SELECT, INSERT, UPDATE or DELETE on app_private.agent_audit, and the
-- definer functions above are the only paths in. That is 0014's arrangement for
-- the storage plane and ADR 0052's for the identity registry.

RESET ROLE;

-- The schema cache is a copy, and a migration that changes the API without
-- saying so leaves PostgREST serving the previous surface until something
-- restarts it. Every migration that changes the API ends here.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

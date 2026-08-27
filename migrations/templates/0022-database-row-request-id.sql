-- migrate:up
-- The `database`-source audit row records the request that caused it (D500).
--
-- **This is 0022 and not an edit to 0019** (ADR 0091). 0019 is released and
-- applied on both clusters; a released migration is fix-forward only, whatever
-- it left undone. 0020's own comment set the terms for this one:
--
--     "Closing D500 means replacing both write RPCs, which is a change to what
--      the product WRITES; this migration only adds a way to READ what is
--      already written. Bundling them would make one migration two decisions,
--      and the deployment test that asserts the `database` row's `request_id`
--      IS NULL stays green and stays the thing that will fail on the day the
--      repair lands."
--
-- This is that day. `test_the_request_id_is_recorded_and_is_this_planes_own_mint`
-- is replaced by a stricter assertion in the same commit, authorised by ADR 0161.
--
-- **The value is the runtime's own mint, never a caller's** (ADR 0160). The MCP
-- plane stamps one id per HTTP request and forwards it on every upstream call,
-- so the id that arrives here is the same one Traefik logged as
-- `downstream_X-Request-Id` on the way out. Four legs, one value.
--
-- ---------------------------------------------------------------------------
-- How the header reads, measured rather than assumed (D632)
-- ---------------------------------------------------------------------------
--
-- Measured in Session 11 Run 1 through PostgREST at the pinned digest, through
-- a role switch, behind a `db-pre-request` hook, inside a SECURITY DEFINER
-- function with `SET search_path = pg_catalog, pg_temp` -- which is this
-- function's exact situation and not an approximation of it:
--
--   * the key is **lowercase** `x-request-id`. A capitalised lookup read NULL in
--     the same request the lowercase one succeeded, and a header sent on the
--     wire as `x-ReQuEsT-iD` still read under the lowercase key.
--   * an absent key is SQL **NULL**, not the empty string. So the repository's
--     `nullif(current_setting(...), '')` idiom is NOT used here: it guards a GUC
--     the hook sets, and a jsonb key lookup is a different case. Copying it
--     would guard something that does not happen and hide something that does.
--   * the two-argument `current_setting` is required. Called from psql with no
--     request at all the GUC does not exist, and the one-argument form RAISES.
--     These functions are reachable from psql.
--
-- ---------------------------------------------------------------------------
-- Why the value is guarded before it is cast (D633)
-- ---------------------------------------------------------------------------
--
-- **An unguarded cast does not fail to correlate. It destroys the write.**
-- Measured, same rig: a function that inserts a row and then casts a malformed
-- caller-supplied header raises 22P02, PostgREST answers 400, and the table is
-- left with **zero rows**. The note is gone. The well-formed control committed
-- both rows in the same invocation, and a *missing* header is harmless because
-- NULL::uuid is NULL -- only the malformed path is dangerous, and any caller can
-- take it.
--
-- Two existing decisions forbid the naive version, so this makes no new one:
--
--   * **ADR 0141** makes a write fail closed on ITS OWN audit record. A caller's
--     malformed header is not this deployment's audit record failing; it is
--     caller input. A correlation field must never be able to destroy the
--     operation it annotates.
--   * **ADR 0139** requires a write refusal to be TRANSLATED from the product's
--     own `PT` errcode and never relayed. A raw 22P02 surfacing as 400 is
--     exactly the relayed status that ADR exists to forbid, and the agent plane
--     cannot classify it because it is not a PT code.
--
-- A shape test rather than `BEGIN ... EXCEPTION`: an exception block opens a
-- subtransaction on every agent write, and a regex is a comparison. Recorded
-- because the exception block is what a reader reaches for first.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- One helper, called by both RPCs
-- ---------------------------------------------------------------------------
--
-- **A function rather than the expression twice**, and that is CLAUDE.md §7's
-- question 5 answered in advance rather than after the fact. A third write RPC
-- added in a later session gets this rule by calling it; the alternative is that
-- it gets whichever of the two copies its author happened to read. D500 exists
-- because 0019 asked a question of one path and not the other.
--
-- SECURITY INVOKER and no grants: it needs no privilege of its own, and running
-- inside a SECURITY DEFINER caller it executes as that function's owner. Request
-- roles never call it directly, so there is nothing to grant and nothing that
-- could be reached by granting it. STABLE, because `current_setting` does not
-- change within a transaction.
CREATE OR REPLACE FUNCTION app_private.agent_request_id()
  RETURNS uuid
  LANGUAGE plpgsql
  STABLE
  SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  raw       text;
  candidate text;
BEGIN
  -- Two-argument form: this is reachable from psql, where the GUC is unset.
  raw := current_setting('request.headers', true);
  IF raw IS NULL THEN
    RETURN NULL;
  END IF;

  candidate := (raw::jsonb) ->> 'x-request-id';
  IF candidate IS NULL THEN
    RETURN NULL;
  END IF;

  -- The shape test, before the cast. Anything that is not a uuid records NULL
  -- and the caller's write proceeds (D633).
  IF candidate !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
  THEN
    RETURN NULL;
  END IF;

  RETURN candidate::uuid;
END $fn$;

COMMENT ON FUNCTION app_private.agent_request_id() IS
  'The request id for this transaction, or NULL. Reads the forwarded '
  'X-Request-Id from current_setting(''request.headers''), lowercase, and '
  'returns NULL for anything absent or malformed rather than raising: a '
  'correlation field must never destroy the write it annotates (D633, ADR 0161).';

REVOKE ALL ON FUNCTION app_private.agent_request_id() FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Both write RPCs, replaced
-- ---------------------------------------------------------------------------
--
-- CREATE OR REPLACE, and the signatures are unchanged -- so nothing in `api` is
-- created, dropped or re-signatured, and no grant moves. The bodies below are
-- 0019's verbatim except for the one column added to each INSERT.
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
      (source, agent_id, owner_id, tool, request_id, outcome, row_count, completed_at)
    VALUES
      ('database', acting_agent, caller, 'create_note',
       app_private.agent_request_id(), 'committed', 1, now());
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
  -- expected status and both proceeding. Unchanged from 0019.
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
      (source, agent_id, owner_id, tool, request_id, outcome, row_count, completed_at)
    VALUES
      ('database', acting_agent, caller, 'update_task_status',
       app_private.agent_request_id(), 'committed', 1, now());
  END IF;

  RETURN updated;
END $fn$;

RESET ROLE;

-- Two functions in `api` were REPLACED, with identical signatures and unchanged
-- privileges. PostgREST's schema cache holds signatures, and neither moved --
-- but 0021 issued this same NOTIFY as a precaution on the same open question
-- (whether that cache holds anything else), and the asymmetry is the same: the
-- cost is one reload of a cache that loads in about 3 ms, and the alternative is
-- a body live in PostgreSQL and stale over HTTP.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

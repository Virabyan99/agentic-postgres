-- migrate:up
-- ADR 0196. `0005` created `api.create_task`; `0007` revoked and dropped it,
-- correctly -- ADR 0048 found a second create the reviewed domain never
-- sanctioned. Nothing replaced it, and nothing in this repository has ever
-- needed a task to exist, so nothing noticed until an outsider built an
-- application on 1.0.0 and could not create one.
--
-- Rig 19 measured what the tree denied: `api.create_task` functions in the
-- catalog, 0; holders of INSERT on `app.tasks`, `object_owner` only, which is
-- NOLOGIN and reachable only by migrations. So no role any service connects as
-- can create a task, on any surface this product publishes, and two of the
-- agent plane's six tools address a permanently empty table.
--
-- `0003`'s comment -- "the runtime identity works on these tables directly" --
-- has been FALSE since `0006` revoked ALL ON SCHEMA app from the runtime identity
-- (D1058). A released template's bytes are the unit `verify_lock` checks, so
-- that comment is fix-forward like everything else here: recorded, not edited.
--
-- This is not 0005's function returned. It is a new migration whose entry in
-- the reviewed contract is made deliberately rather than inherited, carrying
-- 0007's error contract (the SQLSTATE is the status; nothing caller-reachable
-- carries a HINT or a DETAIL, because PostgREST publishes both verbatim) and
-- 0007's column list.
SET LOCAL ROLE {{object_owner}};

-- Every reason 0005 and 0007 gave still applies and is not repeated here: no
-- `owner_id` parameter, because a signature that took one would let a caller
-- satisfy the INSERT policy by naming somebody else; SECURITY DEFINER because
-- an INVOKER body running `INSERT INTO app.tasks` would need the caller to
-- hold USAGE on schema `app`, which dissolves the boundary 0004 exists to
-- keep; safe only because 0003's tables carry FORCE row level security, so the
-- owner's own writes are still policy-checked against the caller's claim;
-- `search_path` pinned to catalog and pg_temp with every object qualified.
CREATE FUNCTION api.create_task(p_title text, p_note_id uuid DEFAULT NULL)
  RETURNS api.tasks
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller uuid := app.current_user_id();
  created api.tasks;
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: no request identity for this transaction'
      USING ERRCODE = 'PT401';
  END IF;

  -- Checked against the caller's own ownership, not merely against existence.
  -- A foreign key alone would accept another user's note id. The two cases are
  -- one answer for `update_task_status`'s reason (0007): a caller that can tell
  -- a foreign id from a fictional one enumerates the table one 404 at a time.
  IF p_note_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.notes n WHERE n.id = p_note_id AND n.owner_id = caller
  ) THEN
    RAISE EXCEPTION 'AP404: no such note' USING ERRCODE = 'PT404';
  END IF;

  -- `status` and `description` take 0007's defaults ('pending', ''). A creator
  -- that accepted a status would make ADR 0003's operation 4 -- the
  -- compare-and-swap -- optional, because a caller could arrive at any state
  -- without ever transitioning through it.
  INSERT INTO app.tasks (owner_id, note_id, title)
  VALUES (caller, p_note_id, p_title)
  RETURNING id, owner_id, note_id, title, description, status, created_at, updated_at
       INTO created;

  RETURN created;
END $fn$;

COMMENT ON FUNCTION api.create_task(text, uuid) IS
  'Creates one task owned by the request identity, optionally against one of '
  'the caller''s own notes. There is no owner parameter. ADR 0196.';

-- Explicit, per function, immediately after creation. This -- not the
-- ALTER DEFAULT PRIVILEGES in 0001 -- is what carries SEC-DEFAULT-001 on the
-- locked image (D57), and PostgREST's `openapi-mode = follow-privileges`
-- follows a PUBLIC grant too, so a function left with its default EXECUTE is
-- advertised in the document an anonymous caller receives.
REVOKE ALL ON FUNCTION api.create_task(text, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION api.create_task(text, uuid)
  TO {{authenticated}}, {{agent_writer}};

-- 0009's rule, and the reason the snapshot can publish this at all: the
-- documentation role reads the surface under `follow-privileges`, so a function
-- it cannot execute is a function the generated OpenAPI document does not
-- name. Every published function in this schema is granted here explicitly.
GRANT EXECUTE ON FUNCTION api.create_task(text, uuid)
  TO {{api_documentation}};

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

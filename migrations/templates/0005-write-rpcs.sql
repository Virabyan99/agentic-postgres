-- migrate:up
-- Two write paths, each deriving ownership instead of accepting it.
SET LOCAL ROLE {{object_owner}};

-- There is no `owner_id` parameter, and that absence is the security property.
-- A signature that took one would let a caller satisfy the INSERT policy by
-- naming somebody else -- the policy would pass, because the row really would
-- be owned by whoever the caller said.
--
-- SECURITY DEFINER, and the reasoning is measured rather than instinctive.
-- The instinct is that INVOKER is the safer default, and for most functions it
-- is. Here it does not work and would not be safer if it did: a SECURITY
-- INVOKER body running `INSERT INTO app.notes` needs the *caller* to hold
-- USAGE on schema `app`, and granting that dissolves the boundary that makes
-- `app` unaddressable -- the invariant 0004 exists to keep. Measured: an
-- INVOKER version raises "permission denied for schema app" for exactly this
-- reason.
--
-- DEFINER is safe here only because of 0003. The tables carry FORCE row-level
-- security, so the owner's own writes are still policy-checked, and the
-- policies key on the caller's transaction-local claim rather than on
-- `current_user`. Verified end to end: a DEFINER insert lands under the
-- caller's claim, and the caller still sees only its own rows afterwards.
-- Without FORCE, this function would be an ownership-laundering primitive.
--
-- `SET search_path` is pinned to catalog and pg_temp, with every object named
-- schema-qualified in the body. On a SECURITY DEFINER function that is not
-- hygiene, it is the whole thing: without it a caller who can create a
-- temporary object shadows an unqualified name and executes it as the owner.
--
-- Parameters are `p_`-prefixed. Unprefixed `title` is ambiguous against the
-- column of the same name in `RETURNING`, and plpgsql resolves that by
-- raising -- which is a migration that fails at run time, not at apply time.
CREATE OR REPLACE FUNCTION api.create_note(p_title text, p_body text DEFAULT '')
  RETURNS api.notes
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller uuid := app.current_user_id();
  created api.notes;
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: no request identity for this transaction'
      USING HINT = 'SET LOCAL app.user_id before calling this function.';
  END IF;

  INSERT INTO app.notes (owner_id, title, body)
  VALUES (caller, p_title, p_body)
  RETURNING id, owner_id, title, body, created_at, updated_at INTO created;

  RETURN created;
END $fn$;

-- Returns `api.notes`, not `app.notes`. The return type is resolved by the
-- caller, so naming the private table's row type here would require USAGE on
-- `app` to so much as call the function -- the same leak by a quieter route.
CREATE OR REPLACE FUNCTION api.create_task(p_title text, p_note_id uuid DEFAULT NULL)
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
      USING HINT = 'SET LOCAL app.user_id before calling this function.';
  END IF;

  -- Checked against the caller's own ownership, not merely against existence.
  -- A foreign key alone would accept another user's note id, and the error
  -- distinguishing "not yours" from "does not exist" is itself a read.
  IF p_note_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.notes n WHERE n.id = p_note_id AND n.owner_id = caller
  ) THEN
    RAISE EXCEPTION 'AP404: no such note' USING HINT = 'The note does not exist.';
  END IF;

  INSERT INTO app.tasks (owner_id, note_id, title)
  VALUES (caller, p_note_id, p_title)
  RETURNING id, owner_id, note_id, title, done, created_at, updated_at INTO created;

  RETURN created;
END $fn$;

-- Explicit, per function, immediately after creation. This -- not the
-- ALTER DEFAULT PRIVILEGES in 0001 -- is what actually carries
-- SEC-DEFAULT-001 and SEC-FUNC-001 on the locked image: the default-privileges
-- statement reports success and stores nothing there, while this is measured
-- to leave `has_function_privilege('public', ...)` false. See D57.
REVOKE ALL ON FUNCTION api.create_note(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.create_task(text, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION api.create_note(text, text) TO {{authenticated}}, {{agent_writer}};
GRANT EXECUTE ON FUNCTION api.create_task(text, uuid) TO {{authenticated}}, {{agent_writer}};

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

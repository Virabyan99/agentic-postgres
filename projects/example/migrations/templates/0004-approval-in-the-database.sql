-- migrate:up
-- The example project's gated write checks the approval in the database too.
--
-- D1721, ADR 0242. `set_note_embedding` is the capability this project marks
-- `requires_approval`, and until now only the agent PLANE enforced that: an
-- agent holding `note_embeddings:write` could call `POST /rpc/set_note_embedding`
-- through PostgREST with its own token and write (rig 33b). The release's
-- migration 0037 creates `app.require_approval`, granted to nobody; this
-- function can call it because it runs as the object owner (SECURITY DEFINER,
-- created under the preamble below).
--
-- `CREATE OR REPLACE` with 0003's signature, `search_path` and body copied
-- byte for byte, plus ONE statement, the first after `BEGIN`. The signature is
-- unchanged, so the project's reviewed surface and its OpenAPI snapshot do not
-- move, and PostgreSQL keeps the function's OID -- and with it the grants 0001
-- and 0002 made and 0001's comment. No grant is restated: a restated grant
-- would hide a replace that dropped one, and the cluster proof reads
-- `has_function_privilege` instead. Fix forward: 0003 is frozen and applied
-- (D912).
--
-- **Why first.** Nothing -- not the identity check, not the ownership check,
-- not the upsert, not the event -- runs for an agent that holds no approved
-- decision. A guard placed after the ownership check would tell an unapproved
-- agent which note ids its owner holds. `approval_gate.unguarded` refuses a
-- gated RPC whose first statement is anything else.
--
-- **The tool name is the capability's**: `set_note_embedding` is the name the
-- plane's `apg_approval` claim carries and the name the approval row records.
--
-- The note's owner calling directly is served (a person's own write passes the
-- guard), and the approval workflow's released call -- the step token's claim
-- with the plane's `Idempotency-Key` -- is served once.
SET LOCAL ROLE {{object_owner}};

CREATE OR REPLACE FUNCTION api.set_note_embedding(p_note_id uuid, p_embedding extensions.vector)
  RETURNS api.note_embeddings
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller uuid := app.current_user_id();
  written api.note_embeddings;
BEGIN
  PERFORM app.require_approval('set_note_embedding');
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: no request identity for this transaction'
      USING ERRCODE = 'PT401';
  END IF;

  -- Checked against the caller's own ownership, not merely against existence.
  -- The foreign key would accept another owner's note id and the row policy
  -- would then refuse the INSERT with a message about row security, which is a
  -- worse answer to the same question.
  IF NOT EXISTS (
    SELECT 1 FROM app.notes n WHERE n.id = p_note_id AND n.owner_id = caller
  ) THEN
    RAISE EXCEPTION 'AP404: no such note' USING ERRCODE = 'PT404';
  END IF;

  INSERT INTO app.note_embeddings (note_id, owner_id, embedding)
  VALUES (p_note_id, caller, p_embedding)
  ON CONFLICT (note_id) DO UPDATE
    SET embedding = EXCLUDED.embedding, updated_at = now()
  RETURNING note_id, owner_id, embedding, updated_at INTO written;
  PERFORM app.emit_event('note_embedding.set', 1, pg_catalog.jsonb_build_object('note_id', p_note_id));

  RETURN written;
END $fn$;

RESET ROLE;

-- The schema cache is a copy; the signature did not change, but the reload is
-- what every migration that touches the API surface does, and it is free.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: this migration plane is fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

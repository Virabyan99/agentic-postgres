-- migrate:up
-- The example project's write now says what happened: `note_embedding.set@1`.
--
-- D1781, ADR 0235. An event is written by a REVIEWED definer function, in the
-- transaction that made it happen, through `app.emit_event` -- which the
-- release's migration 0036 grants to nobody. This function can call it
-- because it runs as the object owner (SECURITY DEFINER, created under the
-- preamble below), and the owner may execute its own function whatever the
-- grants say. No request role gains anything here, and no trigger exists
-- anywhere: a write that rolls back rolls its event back with it.
--
-- `CREATE OR REPLACE` with 0001's signature, `search_path` and body copied
-- byte for byte, plus ONE line after the upsert. The signature is unchanged,
-- so the project's reviewed surface and its OpenAPI snapshot do not move, and
-- PostgreSQL keeps the function's OID -- and with it the grants 0001 and 0002
-- made and 0001's comment. That is measured, not assumed:
-- `test_the_example_sets_third_migration_keeps_the_signature` reads
-- `has_function_privilege` for `authenticated` and `agent_writer` after this
-- applies. Fix forward: 0001 is frozen and applied (D912).
--
-- The payload names the note and NEVER carries the embedding: 768 floats the
-- capability redacts from every audit row are not a value an event may
-- deliver to a receiver the operator configured (the redaction rule, applied
-- to an event). A subscriber that wants the vector reads it with its own
-- grant.
--
-- The event is recorded only when something listens (D1782): with no enabled
-- outbound connector and no parked wait this line changes nothing at all.
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

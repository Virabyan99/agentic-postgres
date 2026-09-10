-- migrate:up
-- The example project's own domain: a vector beside each of the caller's notes.
--
-- This is what a tenant's migration looks like. It is not part of the release:
-- it lives under `projects/example/`, it is frozen under its own lock, and the
-- release's reviewed contract does not name a single object in it. The release
-- applies it after its own set, through the same dbmate plane, as the same
-- `migration_user`, under the same `SET LOCAL ROLE` (ADR 0198).
--
-- It is also the pgvector example D698 and D714 recorded as never registered,
-- arriving as what it always was -- a project's migration rather than a
-- platform capability.
--
-- Everything below is bounded by `migrations.lint_project_set`, which refuses
-- this set before anything renders it if it names `app_private`, creates or
-- alters a role, schema or extension, sets a role other than the preamble
-- below, drops an object the release publishes, reads a placeholder outside the
-- request-role allowlist, creates a table in `app` without FORCE row level
-- security, or carries a `down` block that does not raise AP900.
SET LOCAL ROLE {{object_owner}};

-- `extensions.vector`, not `vector`. The type lives in the `extensions` schema
-- (migration 0001 creates it, ADR 0028's separation), and this migration may
-- USE the type while the lint forbids it from CREATE EXTENSION -- the schema is
-- the platform's to own and the type is a tenant's to use.
--
-- 768 dimensions because that is what the small sentence-transformer models
-- emit; a project choosing another number changes this one line. The dimension
-- is part of the column type, so changing it later is a new migration.
CREATE TABLE app.note_embeddings (
  note_id    uuid PRIMARY KEY REFERENCES app.notes(id) ON DELETE CASCADE,
  owner_id   uuid NOT NULL,
  embedding  extensions.vector(768) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- `owner_id` is carried on this table rather than joined from `app.notes`, and
-- that is a row-security decision rather than a denormalization. A policy that
-- reached through the foreign key would be a subquery against another table
-- whose own policy applies -- so the row would be visible or not depending on
-- the evaluation order of two policies, which is not something to reason about
-- once, let alone on every read.
--
-- ENABLE and then FORCE, both, and the second is the load-bearing one. ENABLE
-- alone leaves the table's OWNER exempt, and every write function this product
-- publishes is SECURITY DEFINER running as exactly that owner -- so ENABLE
-- without FORCE turns `set_note_embedding` below into an ownership-laundering
-- primitive, which is migration 0005's own comment about why it is safe. The
-- lint refuses this set if FORCE is missing.
ALTER TABLE app.note_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.note_embeddings FORCE ROW LEVEL SECURITY;

CREATE POLICY note_embeddings_owner ON app.note_embeddings
  USING (owner_id = app.current_user_id())
  WITH CHECK (owner_id = app.current_user_id());

COMMENT ON TABLE app.note_embeddings IS
  'The example project''s own table. Owned per row by the request identity, '
  'FORCE row level security, and named in projects/example''s contract rather '
  'than in the release''s.';

-- The read surface. `security_invoker` so the caller's own policy applies;
-- without it the view runs as its owner and returns every row -- migration
-- 0004's rule, which a project's view obeys for the same reason the release's
-- does.
CREATE VIEW api.note_embeddings
  WITH (security_invoker = true, security_barrier = true) AS
  SELECT note_id, owner_id, embedding, updated_at
    FROM app.note_embeddings;

-- The write path, in migration 0031's shape: no owner parameter, SECURITY
-- DEFINER because an INVOKER body cannot reach `app`, `search_path` pinned with
-- every object qualified, and the SQLSTATE carrying the status because
-- PostgREST publishes HINT and DETAIL to the caller verbatim (ADR 0057).
CREATE FUNCTION api.set_note_embedding(p_note_id uuid, p_embedding extensions.vector)
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

  RETURN written;
END $fn$;

COMMENT ON FUNCTION api.set_note_embedding(uuid, extensions.vector) IS
  'Writes or replaces the embedding for one of the caller''s own notes. There '
  'is no owner parameter.';

REVOKE ALL ON FUNCTION api.set_note_embedding(uuid, extensions.vector) FROM PUBLIC;

GRANT SELECT ON api.note_embeddings TO {{authenticated}};
GRANT EXECUTE ON FUNCTION api.set_note_embedding(uuid, extensions.vector)
  TO {{authenticated}};

-- Without these two the project's snapshot never publishes either object.
-- PostgREST reads the document as `api_documentation` under
-- `openapi-mode = follow-privileges`, so a relation it cannot select and a
-- function it cannot execute are absent from the generated artifact -- which
-- would make the project's own contract comparison a comparison against
-- nothing. Migration 0009's rule, and F-007's finding.
GRANT SELECT ON api.note_embeddings TO {{api_documentation}};
GRANT EXECUTE ON FUNCTION api.set_note_embedding(uuid, extensions.vector)
  TO {{api_documentation}};

RESET ROLE;

-- The schema cache is a copy, and a migration that changes the API without
-- saying so leaves PostgREST serving the previous surface until something
-- restarts it.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: this migration plane is fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

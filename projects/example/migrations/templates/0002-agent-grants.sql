-- migrate:up
-- The grant that makes this project's tool answer, rather than refuse upstream.
--
-- D1156. Session 21 opened the agent plane to a tenant's domain: the lock
-- carries `note_embeddings:read` and `note_embeddings:write`, the runtime
-- registers the tools, and the scope vocabulary is derived from the merged
-- surface (ADR 0200, ADR 0201). What none of that can do is grant anything.
-- A capability compiler reads a reviewed surface; a snapshot is captured as
-- `api_documentation`; neither sees a GRANT, and neither should -- a grant is
-- an authorization decision and PostgreSQL is the authority that takes it.
--
-- So until a project grants its objects to the two agent roles, an agent
-- holding `note_embeddings:read` is served the tool and refused by the
-- database, which is the correct refusal arriving at a confusing moment. The
-- release does this for its own objects: migration 0004 grants `api.notes` and
-- 0007 grants `api.tasks` to {{agent_reader}} and {{agent_writer}}. This set is
-- the worked example of a tenant's, so it carries the same two lines for its
-- own view and write function.
--
-- Fix forward: 20260914120001 is frozen and applied, so this is a second
-- migration rather than an edit to the first (D912). It sorts after it, and
-- after the release's newest, which is what this set's lock records as
-- follows_release_version.
SET LOCAL ROLE {{object_owner}};

GRANT SELECT ON api.note_embeddings TO {{agent_reader}}, {{agent_writer}};
GRANT EXECUTE ON FUNCTION api.set_note_embedding(uuid, extensions.vector)
  TO {{agent_writer}};

-- The reader is not granted EXECUTE on the write function, and neither role is
-- granted anything on the underlying table. `api.note_embeddings` is a
-- security_invoker view over a FORCE row-level-security table, so a grant here
-- widens who may ask and never whose rows come back: an agent reads its own
-- caller's rows or none, by the same policy a signed-in request reads them
-- under.

RESET ROLE;

-- The schema cache is a copy, and a migration that changes who may reach the
-- API without saying so leaves PostgREST answering from the previous grants
-- until something restarts it.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: this migration plane is fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

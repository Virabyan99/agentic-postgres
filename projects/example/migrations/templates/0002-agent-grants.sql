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

-- **And the TABLE, which 20260914120001 did not grant to anybody** (D1189).
--
-- `api.note_embeddings` is declared `security_invoker = true`, so PostgreSQL
-- checks the CALLER's privileges on what the view reads -- and what it reads is
-- `app.note_embeddings`. The first migration granted the view to
-- {{authenticated}} and the documentation role and stopped there, so every
-- caller was refused with `permission denied for table note_embeddings`: not
-- the view it had been granted, the table underneath it. The release does both
-- halves for its own objects in one line (migration 0004: `GRANT SELECT ON
-- app.notes, app.tasks TO {{authenticated}}, {{agent_reader}},
-- {{agent_writer}}`), and this set had only half of the pattern.
--
-- Measured in rig 22f: granted the view and not the table, `SET ROLE
-- {{authenticated}}` reads `api.notes` (2 rows) and is refused on
-- `api.note_embeddings`; the agent roles are refused the same way, which is
-- why Run 2's grant alone would not have made the live tenant read pass.
--
-- **This widens who may ASK and never whose rows come back.** The table keeps
-- FORCE row level security and its owner-scoped policy, so a caller reads its
-- own rows or none -- which is the property the view exists to preserve and the
-- one this grant cannot weaken.
GRANT SELECT ON app.note_embeddings
  TO {{authenticated}}, {{agent_reader}}, {{agent_writer}};

-- The documentation role reads the surface under `openapi-mode =
-- follow-privileges`, so it needs the same pair for the view to appear in the
-- generated document at all (F-007, migration 0009's rule).
GRANT SELECT ON app.note_embeddings TO {{api_documentation}};

-- The reader is not granted EXECUTE on the write function: a read scope and a
-- write scope are two decisions, and the compiler treats them as two.

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

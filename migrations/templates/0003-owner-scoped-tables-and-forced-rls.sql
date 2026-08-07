-- migrate:up
-- The domain tables, under FORCE row-level security.
SET LOCAL ROLE {{object_owner}};

-- Request identity is a transaction-local claim, not an authenticated one
-- (ADR 0029). This function is the single place that reads it, so the policies
-- below cannot each invent their own interpretation of a missing claim.
--
-- STABLE, not IMMUTABLE: the value changes within a session. `true` as the
-- second argument to current_setting means "return NULL if unset" rather than
-- raising -- and NULL is what makes every policy below deny by default, since
-- `owner_id = NULL` is never true.
CREATE OR REPLACE FUNCTION app.current_user_id() RETURNS uuid
  LANGUAGE sql
  STABLE
  SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
  SELECT nullif(current_setting('app.user_id', true), '')::uuid;
$$;

COMMENT ON FUNCTION app.current_user_id() IS
  'The caller''s asserted identity for this transaction. Session 3 trusts it and '
  'does not verify it: anything holding a database credential can assert any '
  'value. SEC-RLS-001 proves rows are isolated GIVEN a claim, not that the claim '
  'is authentic. Session 6 makes it authentic by changing who sets the GUC; the '
  'policies do not move.';

CREATE TABLE IF NOT EXISTS app.notes (
  id          uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id    uuid         NOT NULL,
  title       text         NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  body        text         NOT NULL DEFAULT '',
  created_at  timestamptz  NOT NULL DEFAULT now(),
  updated_at  timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.tasks (
  id          uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id    uuid         NOT NULL,
  note_id     uuid         REFERENCES app.notes(id) ON DELETE CASCADE,
  title       text         NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  done        boolean      NOT NULL DEFAULT false,
  created_at  timestamptz  NOT NULL DEFAULT now(),
  updated_at  timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notes_owner_id_idx ON app.notes (owner_id);
CREATE INDEX IF NOT EXISTS tasks_owner_id_idx ON app.tasks (owner_id);
CREATE INDEX IF NOT EXISTS tasks_note_id_idx  ON app.tasks (note_id);

-- ENABLE makes policies apply. FORCE makes them apply to the table's owner as
-- well, and that is the half that matters here: without it, every statement run
-- by object_owner -- which is what a migration and any maintenance script runs
-- as -- silently bypasses every policy below. "RLS is on" is true with ENABLE
-- alone and means much less than it sounds.
ALTER TABLE app.notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.notes FORCE ROW LEVEL SECURITY;
ALTER TABLE app.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tasks FORCE ROW LEVEL SECURITY;

-- One policy per table per command, all keyed on the same claim. USING governs
-- which rows are visible; WITH CHECK governs which rows may be written, and
-- both are needed: USING alone would let a caller UPDATE a row it can see into
-- one owned by somebody else.
CREATE POLICY notes_owner_select ON app.notes
  FOR SELECT USING (owner_id = app.current_user_id());
CREATE POLICY notes_owner_insert ON app.notes
  FOR INSERT WITH CHECK (owner_id = app.current_user_id());
CREATE POLICY notes_owner_update ON app.notes
  FOR UPDATE USING (owner_id = app.current_user_id())
              WITH CHECK (owner_id = app.current_user_id());
CREATE POLICY notes_owner_delete ON app.notes
  FOR DELETE USING (owner_id = app.current_user_id());

CREATE POLICY tasks_owner_select ON app.tasks
  FOR SELECT USING (owner_id = app.current_user_id());
CREATE POLICY tasks_owner_insert ON app.tasks
  FOR INSERT WITH CHECK (owner_id = app.current_user_id());
CREATE POLICY tasks_owner_update ON app.tasks
  FOR UPDATE USING (owner_id = app.current_user_id())
              WITH CHECK (owner_id = app.current_user_id());
CREATE POLICY tasks_owner_delete ON app.tasks
  FOR DELETE USING (owner_id = app.current_user_id());

-- The runtime identity works on these tables directly; it is granted USAGE on
-- `app` in 0001. The API roles are not, and 0004 grants them table SELECT
-- *without* schema USAGE, which is what lets the views work while direct
-- access stays denied.
GRANT SELECT, INSERT, UPDATE, DELETE ON app.notes, app.tasks TO {{app_runtime}};

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

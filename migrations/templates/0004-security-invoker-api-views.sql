-- migrate:up
-- The read surface: views that carry the caller's authority, not the owner's.
SET LOCAL ROLE {{object_owner}};

-- security_invoker = true is the entire point of this migration.
--
-- A view's default in PostgreSQL is to run as its *owner*, which here is
-- object_owner -- the role that owns the tables. A default view over an
-- RLS-protected table therefore returns every row to every caller, and does it
-- silently: the query succeeds, the policy is still "enabled", and the data is
-- gone. Combined with FORCE on the tables (0003), security_invoker means the
-- policy is evaluated against whoever ran the SELECT.
--
-- SEC-VIEW-001 is the proof, and it has to compare two users' results rather
-- than assert the reloption -- a view can be correct in the catalog and wrong
-- in what it returns if the underlying table lost FORCE.
CREATE OR REPLACE VIEW api.notes
  WITH (security_invoker = true, security_barrier = true) AS
  SELECT id, owner_id, title, body, created_at, updated_at
    FROM app.notes;

CREATE OR REPLACE VIEW api.tasks
  WITH (security_invoker = true, security_barrier = true) AS
  SELECT id, owner_id, note_id, title, done, created_at, updated_at
    FROM app.tasks;

COMMENT ON VIEW api.notes IS
  'Read surface for notes. security_invoker means the caller''s row policy '
  'applies; without it the view would run as its owner and return every row.';

-- Read-only, and only SELECT. Writes go through the RPCs in 0005, which derive
-- ownership rather than accepting it -- a grant of INSERT here would let a
-- caller name any owner_id it liked and satisfy the policy by lying.
GRANT SELECT ON api.notes, api.tasks TO {{authenticated}}, {{agent_reader}}, {{agent_writer}};

-- SELECT on the BASE tables, and deliberately no USAGE on schema `app`.
--
-- A security_invoker view evaluates the underlying table's privileges as the
-- caller, so without this the view raises "permission denied for table notes"
-- and the whole read surface is dead. The obvious fix -- granting USAGE on
-- `app` -- would also make `SELECT * FROM app.notes` work directly, and the
-- invariant table's negative proof is that a caller "cannot address `app`
-- directly".
--
-- Measured: schema USAGE is resolved when the view is created, by its owner,
-- not at query time by the caller. So table SELECT without schema USAGE gives
-- exactly the wanted pair -- `api.notes` returns the caller's rows, and
-- `app.notes` raises "permission denied for schema app". Both halves are
-- asserted by SEC-DB-002; neither is safe to infer from the other.
--
-- Granting SELECT here is not a widening: the tables carry FORCE row-level
-- security, so a caller reaching them sees only rows its claim owns.
GRANT SELECT ON app.notes, app.tasks TO {{authenticated}}, {{agent_reader}}, {{agent_writer}};

-- `anon` gets nothing. It exists so that an unauthenticated request has a role
-- to be, not so that it can read: every grant to it is a deliberate later act.
RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

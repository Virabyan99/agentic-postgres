-- migrate:up
-- The application runtime role reaches data through `authenticated`, and by no
-- other path (SEC-DBX-002, ADR 0041).
--
-- Session 3 granted this role direct reach: USAGE on app and app_private, and
-- SELECT/INSERT/UPDATE/DELETE on the two base tables. That was defensible then
-- -- nothing connected as it, and the tables carry FORCE row-level security so
-- the rows were still policy-bound. Session 4 hands this credential to an
-- actual application, and direct table reach is the difference between "a
-- compromised application sees its own rows" and "a compromised application
-- sees the shape of everything and can write anywhere the policy allows".
--
-- Revoked here rather than edited into 0001 and 0003, because an applied
-- migration is immutable: the preflight refuses on any disagreement between
-- its five sources, and rewriting history is the thing it exists to catch.
SET LOCAL ROLE {{object_owner}};

-- THE SCHEMA REVOKE IS THE ONE THAT HOLDS. Measured, because the obvious test
-- for this migration fails while the property is true:
--
--   has_table_privilege(app_runtime, 'app.notes', 'SELECT')  ->  true
--   SET ROLE app_runtime; SELECT * FROM app.notes            ->  denied
--
-- Both are correct. The api views are SECURITY INVOKER, so `authenticated` must
-- hold SELECT on the base tables for them to work at all, and `app_runtime`
-- inherits that membership. What it does not inherit is USAGE on the schema,
-- and without USAGE the grant cannot be exercised — the object cannot be named.
--
-- So the table-level revokes below are defence in depth and the schema-level
-- ones are the boundary. A test that asserted the catalog bit would fail here,
-- and the tempting fix — revoking SELECT from `authenticated` — would silently
-- break every api view instead.
REVOKE ALL ON ALL TABLES IN SCHEMA app FROM {{app_runtime}};
REVOKE ALL ON ALL SEQUENCES IN SCHEMA app FROM {{app_runtime}};
REVOKE ALL ON SCHEMA app FROM {{app_runtime}};
REVOKE ALL ON SCHEMA app_private FROM {{app_runtime}};

-- Default privileges too. A revoke of what exists says nothing about the next
-- table 0007 creates, and a default privilege granted in 0001 would hand it
-- over silently. This is the half of a revocation that is easy to forget and
-- impossible to notice: the grant appears on an object nobody has created yet.
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app
  REVOKE ALL ON TABLES FROM {{app_runtime}};
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app
  REVOKE ALL ON SEQUENCES FROM {{app_runtime}};
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app_private
  REVOKE ALL ON TABLES FROM {{app_runtime}};

-- What remains is what `authenticated` holds: USAGE on api, SELECT on the
-- security-invoker views, EXECUTE on the write RPCs. Those grants are 0001,
-- 0004 and 0005's and are not repeated here -- repeating them would make this
-- migration a second authority on the API surface, and the two would agree
-- until one of them changed.
--
-- The membership itself is a role attribute, so it is the bootstrap plane's
-- (`GRANT authenticated TO app_runtime WITH INHERIT TRUE, SET FALSE, ADMIN
-- FALSE`). INHERIT TRUE because an application must not have to `SET ROLE` to
-- do its job; SET FALSE so it cannot become `authenticated` deliberately and
-- thereby escape whatever a later session attaches to its own identity; ADMIN
-- FALSE so it cannot grant the membership onward.

-- PUBLIC is not a synonym for "nobody". A grant to PUBLIC reaches this role no
-- matter what is revoked from it by name, so the revocation is not complete
-- until PUBLIC is checked too. 0001 already revoked function EXECUTE from
-- PUBLIC; these two are the schema-level pair.
REVOKE ALL ON SCHEMA app, app_private FROM PUBLIC;

COMMENT ON SCHEMA app IS
  'Base tables. Reachable by the object owner and, through SET ROLE, by the '
  'migration plane. The application runtime role holds nothing here: it reads '
  'and writes through api views and RPCs as a member of authenticated '
  '(SEC-DBX-002).';

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

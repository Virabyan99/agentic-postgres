-- migrate:up
-- Schemas, the extension home, and a default-deny privilege posture.
--
-- Every migration in this set runs as the owner and returns the role before
-- dbmate records the version, so the ledger row is written by migration_user
-- while every object is owned by object_owner (ADR 0026).
SET LOCAL ROLE {{object_owner}};

-- Three of the four schemas. Each has one job.
--   app          owner-scoped domain tables. No API role addresses it.
--   app_private  platform state: identity sentinel, ledger. Nothing else.
--   api          the only schema a client-facing role ever names.
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS app_private;
CREATE SCHEMA IF NOT EXISTS api;

-- The fourth, `extensions`, is NOT created here, and neither is pgvector.
--
-- Measured, not assumed: pgvector is not a trusted extension, so CREATE
-- EXTENSION requires superuser and object_owner is deliberately not one.
-- Putting it in a migration produces "permission denied to create extension"
-- on a fresh cluster -- which is the migration plane asking for authority the
-- whole point of ADR 0026 is that it does not have.
--
-- Bootstrap creates the schema OWNED BY object_owner and installs the
-- extension into it over the Unix socket as the OS postgres user (plan 6.1).
-- That ownership is what lets the grant below be a migration's business at all.
-- Extensions live outside `public` so an unqualified call cannot resolve to
-- one.

-- `public` keeps existing because dropping it breaks extensions that assume
-- it, but nothing may create in it. PostgreSQL 15 already revoked CREATE from
-- PUBLIC; this is explicit so the posture does not depend on a server default.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA app, app_private, api FROM PUBLIC;

-- Default-deny for functions -- attempted here, and NOT relied upon.
--
-- PostgreSQL grants EXECUTE to PUBLIC on every newly created function, so a
-- function added by a later migration is callable by every role until someone
-- revokes it. This is the statement that is supposed to fix that once.
--
-- Measured against the locked image, it does not. The statement reports
-- `ALTER DEFAULT PRIVILEGES` and leaves `pg_default_acl` empty, and a function
-- created afterwards by object_owner still has PUBLIC EXECUTE -- both through
-- `SET ROLE` and with an explicit `FOR ROLE`. It is issued anyway, as defence
-- in depth on any version where it does work, with `FOR ROLE` stated
-- explicitly so the target does not depend on what "current role" means inside
-- a `SET LOCAL ROLE` block.
--
-- What actually carries SEC-DEFAULT-001 is the explicit `REVOKE ALL ON
-- FUNCTION ... FROM PUBLIC` beside every `CREATE FUNCTION` in this set, which
-- is measured to work. See D57.
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app, app_private, api
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- USAGE only, and only where a role has business being at all. `api` is the
-- single schema the client-facing roles can name; `app` and `app_private` are
-- unreachable to them, which is half of SEC-DB-002.
GRANT USAGE ON SCHEMA api TO {{anon}}, {{authenticated}}, {{agent_reader}}, {{agent_writer}};
GRANT USAGE ON SCHEMA extensions TO {{anon}}, {{authenticated}}, {{agent_reader}}, {{agent_writer}};
GRANT USAGE ON SCHEMA app, app_private TO {{app_runtime}};

RESET ROLE;

-- migrate:down
-- Released platform migrations are fix-forward only (ADR 0028). A rollback of
-- a schema that already holds rows is not a rollback; it is data loss wearing
-- the word "down". The remedy for a mistake is a new migration.
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

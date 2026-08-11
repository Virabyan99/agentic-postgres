-- migrate:up
-- The documentation role: the grants that make `follow-privileges` publish the
-- whole surface, and the hook clause that makes those grants unusable (D158).
--
-- The pair is the design, and neither half is safe alone.
--
-- Measured on the locked PostgREST, against a role holding view SELECT and
-- EXECUTE on the write RPC, with the grant read back out of
-- `information_schema.role_table_grants` rather than assumed:
--
--   * a role holding only view SELECT gets a **complete** document in which
--     every read is 403 and no write RPC appears at all -- so `EXECUTE` is not
--     optional if the published document is to describe the write surface;
--   * a role holding `EXECUTE` **wrote a row** when its token carried a
--     subject. That is Run 5's finding and it is the reason this migration
--     exists in the shape it does.
--
-- So the role gets the grants, and the hook refuses to establish an identity
-- for it. `EXECUTE` publishes the RPC and can never perform it.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The grants
-- ---------------------------------------------------------------------------
--
-- Exactly the read surface plus EXECUTE on the two write RPCs, and nothing
-- else. No INSERT, UPDATE or DELETE on the views: the role is not meant to be
-- able to write, and the hook is what makes sure of it -- but a grant it does
-- not hold is one fewer thing depending on the hook being right.
GRANT USAGE ON SCHEMA api TO {{api_documentation}};
GRANT SELECT ON api.notes, api.tasks TO {{api_documentation}};

GRANT EXECUTE ON FUNCTION api.create_note(text, text)
  TO {{api_documentation}};
GRANT EXECUTE ON FUNCTION api.update_task_status(uuid, api.task_status, api.task_status)
  TO {{api_documentation}};

-- The same pair every request role holds (ADR 0052). PostgREST runs
-- `db-pre-request` after the role switch, so a role that cannot execute the
-- hook cannot make a request at all -- including the one that fetches the
-- document this role exists to fetch.
GRANT USAGE ON SCHEMA app_private TO {{api_documentation}};
GRANT EXECUTE ON FUNCTION app_private.postgrest_pre_request()
  TO {{api_documentation}};

-- The closed default privileges, restated for the new grantee. Migration 0008
-- closed them for `anon` and `authenticated`; a role added afterwards would
-- otherwise inherit whatever a later `CREATE TABLE` in `app_private` grants.
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app_private
  REVOKE ALL ON TABLES FROM {{api_documentation}};
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app_private
  REVOKE ALL ON SEQUENCES FROM {{api_documentation}};

-- ---------------------------------------------------------------------------
-- The hook, replaced
-- ---------------------------------------------------------------------------
--
-- Migration 0008's function with one clause added at the top. Restated in full
-- rather than patched, because `CREATE OR REPLACE FUNCTION` replaces the whole
-- body and a reader comparing this against 0008 must be able to see everything
-- that runs -- not a diff they have to reconstruct across two files.
--
-- `current_user::text` and NOT `pg_catalog.current_user`. This is migration
-- 0008's `nullif` lesson in a second place: `current_user` is a SQL construct
-- the parser rewrites, not a function to look up, and qualifying it produces a
-- hook that fails on every request while the service stays healthy. Measured
-- both ways before this was written; the cast is what works.
CREATE OR REPLACE FUNCTION app_private.postgrest_pre_request() RETURNS void
  LANGUAGE plpgsql
  SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  -- Empty is absent (migration 0008). `nullif` is deliberately unqualified.
  raw text := nullif(pg_catalog.current_setting('request.jwt.claims', true), '');
  claims jsonb;
  subject text;
BEGIN
  -- The documentation role has no request identity, ever.
  --
  -- Its whole purpose is to be shown the published surface, and every object on
  -- that surface is guarded by a row policy keyed on `app.user_id`. Leaving it
  -- unset is what makes the write RPCs it advertises fail: measured, a bare
  -- documentation token calling `create_note` comes back **403 "new row
  -- violates row-level security policy"**, because ownership is derived from an
  -- identity that is not there.
  --
  -- A token that carries a subject is refused rather than ignored. Ignoring it
  -- would be the same outcome today and a silent one: the difference between
  -- "this credential cannot act" and "this credential's request was quietly
  -- reinterpreted" is the difference between a refusal somebody can debug and a
  -- permission that comes back when a policy changes.
  IF current_user::text = {{api_documentation_name}} THEN
    IF raw IS NOT NULL AND (raw::jsonb ->> 'sub') IS NOT NULL THEN
      RAISE EXCEPTION 'AP401: the documentation role has no request identity'
        USING ERRCODE = 'PT401';
    END IF;
    RETURN;
  END IF;

  IF raw IS NULL THEN
    -- An anonymous request: a role to be, and no identity.
    RETURN;
  END IF;

  BEGIN
    claims := raw::jsonb;
  EXCEPTION WHEN others THEN
    -- Fails closed. "Unreadable" and "absent" look identical one line later and
    -- mean opposite things about who is asking.
    RAISE EXCEPTION 'AP401: the request identity could not be read'
      USING ERRCODE = 'PT401';
  END;

  subject := claims ->> 'sub';
  IF subject IS NULL OR subject = '' THEN
    RETURN;
  END IF;

  -- Shape-checked here rather than left to the cast in the row policy, which
  -- returned a raw `invalid input syntax for type uuid` to the caller.
  IF subject !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
  THEN
    RAISE EXCEPTION 'AP401: the request identity could not be read'
      USING ERRCODE = 'PT401';
  END IF;

  -- Transaction-local, so one request's asserted identity cannot become the
  -- next one's on a pooled connection.
  PERFORM pg_catalog.set_config('app.user_id', subject, true);
END $fn$;

COMMENT ON FUNCTION app_private.postgrest_pre_request() IS
  'PostgREST db-pre-request. Runs after the role switch, inside the request '
  'transaction, which is read-only on a GET -- so it writes nothing. Refuses '
  'the documentation role an identity, reads the validated claims once, '
  'refuses a malformed subject, and establishes app.user_id as a '
  'transaction-local setting. ADR 0052, D158.';

RESET ROLE;

-- The published surface moves: the documentation role's grants are what make
-- `openapi-mode = follow-privileges` include the write RPCs in the document it
-- is served. A PostgREST holding a cache from before this migration would serve
-- that role a document missing them.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

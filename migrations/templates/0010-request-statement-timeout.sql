-- migrate:up
-- The carrier: a role's `statement_timeout` reaches the request that runs as it
-- (D198, ADR 0068).
--
-- Outputs v7 and ADR 0067 got the manifest's timeouts onto the roles, and the
-- deployed cluster carries them: `pg_roles.rolconfig` shows `2s` on `anon` and
-- `5s` on `authenticated`. A REST request was still unbounded, because
-- **PostgreSQL processes a role's settings only at login**, and PostgREST logs
-- in as the authenticator and reaches the request role with `SET LOCAL ROLE`,
-- which is not a login.
--
-- Measured on the locked images, arm by arm, with the product's own
-- configuration as the control:
--
--   * db-config=false, hoisting off  -- `statement_timeout=0`, a 5-second
--     statement returns 200 after 5.0s. This is the deployment, reproduced.
--   * db-config=true                 -- bounded at 2.0s, and bounded whether or
--     not `db-hoisted-tx-settings` names `statement_timeout`, so the hoist list
--     is not the operative variable and `db-config` is. Rejected: `db-config`
--     is `false` deliberately, so that the reviewed Compose file is the only
--     authority on PostgREST's configuration.
--   * the setting on the *authenticator* -- bounded, because that role does log
--     in. Rejected: one timeout for every request role, which is not what the
--     manifest declares.
--   * this hook                      -- bounded at 2.0s with `db-config` left
--     `false`.
--
-- The value is still the document's. This reads what the bootstrap plane wrote
-- from `database.statement_timeouts` and applies it for one transaction; it
-- decides nothing and holds no copy, so there is still exactly one authority
-- for what a role's timeout is (ADR 0002).
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The hook, replaced
-- ---------------------------------------------------------------------------
--
-- Migration 0009's function with one block added at the top, restated in full
-- for 0009's reason: `CREATE OR REPLACE FUNCTION` replaces the whole body, and
-- a reader comparing this against 0009 must be able to see everything that
-- runs rather than reconstruct a diff across two files.
--
-- **Before the two early returns**, deliberately. The documentation role and an
-- anonymous request both return early, and both are requests that can hold a
-- connection; a bound applied after them would be a bound on exactly the
-- callers who authenticated.
--
-- `SECURITY INVOKER`, and no `SECURITY DEFINER` helper. Measured: a plain role
-- can read `pg_db_role_setting` directly, so a definer function would be a
-- privilege boundary bought for nothing -- and the first draft of it was
-- *wrong* in a way that reads as correct, because `SECURITY DEFINER` makes
-- `current_user` the function's owner, so the lookup asked for the owner's
-- timeout, found none, set nothing, and looked exactly like a hook that had run
-- and found nothing to do.
--
-- `current_user::text` and NOT `pg_catalog.current_user`, which is migration
-- 0009's lesson and applies to the new block as well: `current_user` is a SQL
-- construct the parser rewrites, not a function to look up.
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
  bound text;
BEGIN
  -- The role's own bound, carried into this transaction.
  --
  -- `LIMIT 1` because `setconfig` is an array and a role could in principle
  -- carry the entry twice; taking the first is arbitrary and taking none would
  -- be worse. `set_config(..., true)` is transaction-local, so one request's
  -- bound cannot become the next one's on a pooled connection -- the same
  -- reason `app.user_id` below is local.
  --
  -- A role with no entry leaves this NULL and nothing is set, which is the
  -- correct outcome: the platform bounds what the document names and does not
  -- invent a bound for what it does not.
  SELECT split_part(entry, '=', 2) INTO bound
  FROM pg_db_role_setting setting
  JOIN pg_roles role ON role.oid = setting.setrole
  CROSS JOIN LATERAL unnest(setting.setconfig) AS entry
  WHERE role.rolname = current_user::text
    AND entry LIKE 'statement_timeout=%'
  LIMIT 1;

  IF bound IS NOT NULL THEN
    PERFORM pg_catalog.set_config('statement_timeout', bound, true);
  END IF;

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
  'transaction, which is read-only on a GET -- so it writes nothing. Carries '
  'the role''s statement_timeout into the transaction, because PostgreSQL '
  'applies a role setting only at login and this role never logs in; refuses '
  'the documentation role an identity, reads the validated claims once, '
  'refuses a malformed subject, and establishes app.user_id as a '
  'transaction-local setting. ADR 0052, ADR 0068, D158, D198.';

RESET ROLE;

-- The function's body changed and PostgREST caches nothing about it, but the
-- reload costs nothing and every prior migration that replaced this function
-- issued one. Consistency here is worth more than the saved round trip.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

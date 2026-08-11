-- migrate:up
-- The hook PostgREST runs on every request, and the single private object a
-- request role may reach (ADR 0052, D138).
--
-- This is the largest authorization change in Session 5 and it arrives in a
-- diff that reads as one `GRANT USAGE`. Migration 0006 took `USAGE ON SCHEMA
-- app_private` away from the runtime role one session ago, because D103
-- measured that schema USAGE -- not the table grant -- is the boundary that
-- does the work. This migration gives that USAGE to every HTTP caller including
-- the anonymous one, because PostgREST runs `db-pre-request` **after** the role
-- switch, so the impersonated role needs EXECUTE, and EXECUTE needs USAGE.
--
-- Measured rather than inferred: with a token naming `authenticated`, the hook
-- observed `current_user = <authenticated>` and `session_user =
-- <postgrest_authenticator>`. The switch has already happened when it runs.
SET LOCAL ROLE {{object_owner}};

-- WRITES NOTHING, AND THAT IS A CONSTRAINT RATHER THAN A STYLE.
--
-- PostgREST runs this inside the request's own transaction, and that
-- transaction is READ ONLY on a GET. Measured: an early version of this
-- function kept an audit row, and every read of the API answered
-- **405 "cannot execute INSERT in a read-only transaction"** -- a write hidden
-- in a hook turning the entire read surface off. If this function ever needs to
-- record something, it needs a different mechanism, not a table.
--
-- SECURITY INVOKER: definer rights would change what the body may do, not who
-- may call it. EXECUTE still requires schema USAGE either way, which is why the
-- grant below is unavoidable and why ADR 0052 bounds it by name instead.
CREATE OR REPLACE FUNCTION app_private.postgrest_pre_request() RETURNS void
  LANGUAGE plpgsql
  SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  -- Empty is absent. `current_setting(..., true)` returns NULL for a setting
  -- that was never set and the empty string for one PostgREST set to nothing,
  -- and treating those two differently is how a request with no claims becomes
  -- a request whose claims are the string ''.
  --
  -- `nullif` is deliberately NOT written as `pg_catalog.nullif`. It is a SQL
  -- construct the parser rewrites into a CASE, not a function to look up, and
  -- qualifying it produces `function pg_catalog.nullif(text, unknown) does not
  -- exist` -- measured, on a hook that then failed on every request and took
  -- the entire API down with it while the service stayed healthy. Being a
  -- construct is also why it needs no qualification: nothing on a search_path
  -- can shadow it.
  raw text := nullif(pg_catalog.current_setting('request.jwt.claims', true), '');
  claims jsonb;
  subject text;
BEGIN
  IF raw IS NULL THEN
    -- An anonymous request. It has a role to be and no identity, which is the
    -- honest state: every policy keys on `app.user_id` and denies when it is
    -- absent, so this returns without establishing one.
    RETURN;
  END IF;

  -- Parsed once, here, and never re-read downstream. Two readers of one claim
  -- set are two chances to disagree about what a malformed one means.
  BEGIN
    claims := raw::jsonb;
  EXCEPTION WHEN others THEN
    -- Fails closed. A request whose claims cannot be read is refused, not
    -- treated as anonymous: "unreadable" and "absent" look identical one line
    -- later and mean opposite things about who is asking.
    RAISE EXCEPTION 'AP401: the request identity could not be read'
      USING ERRCODE = 'PT401';
  END;

  subject := claims ->> 'sub';
  IF subject IS NULL OR subject = '' THEN
    RETURN;
  END IF;

  -- Shape-checked here rather than left to the cast in `app.current_user_id()`.
  -- Measured: a token carrying `"sub": "not-a-uuid"` reached the row policy and
  -- came back to the caller as **400 `invalid input syntax for type uuid:
  -- "not-a-uuid"`** -- a raw PostgreSQL cast error, produced by a policy, on
  -- every request. Refusing it here makes it one 401 from one place.
  IF subject !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
  THEN
    RAISE EXCEPTION 'AP401: the request identity could not be read'
      USING ERRCODE = 'PT401';
  END IF;

  -- Transaction-local. `set_config(..., true)` is `SET LOCAL`, so the value
  -- cannot outlive the request on a pooled connection -- which is the failure
  -- D101's pooler notes describe from the other side: one request's asserted
  -- identity becoming the next one's is the most dangerous single failure
  -- available in this design.
  PERFORM pg_catalog.set_config('app.user_id', subject, true);
END $fn$;

COMMENT ON FUNCTION app_private.postgrest_pre_request() IS
  'PostgREST db-pre-request. Runs after the role switch, inside the request '
  'transaction, which is read-only on a GET -- so it writes nothing. Reads the '
  'validated claims once, refuses a malformed subject, and establishes '
  'app.user_id as a transaction-local setting. ADR 0052.';

-- The grant, by name, and nothing else.
--
-- PUBLIC first: a grant to PUBLIC reaches every role no matter what is granted
-- by name afterwards, so the enumeration below is only an enumeration if this
-- runs. 0001's ALTER DEFAULT PRIVILEGES was measured not to store anything on
-- this image (D57).
REVOKE ALL ON FUNCTION app_private.postgrest_pre_request() FROM PUBLIC;

-- `anon` and `authenticated` only. The two agent roles are Session 9's and are
-- deliberately not granted to the authenticator, so PostgREST cannot become
-- either of them -- and a USAGE grant to a role that can never make a request
-- would widen the private schema to buy nothing.
GRANT USAGE ON SCHEMA app_private TO {{anon}}, {{authenticated}};
GRANT EXECUTE ON FUNCTION app_private.postgrest_pre_request()
  TO {{anon}}, {{authenticated}};

-- The closed default privileges stay closed, restated for `app_private` because
-- this migration is the one that made the schema nameable. A private helper
-- added by a later migration must not become reachable by having been created.
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app_private
  REVOKE ALL ON TABLES FROM {{anon}}, {{authenticated}};
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app_private
  REVOKE ALL ON SEQUENCES FROM {{anon}}, {{authenticated}};

COMMENT ON SCHEMA app_private IS
  'Platform state, plus the one function an HTTP request role may reach. The '
  'request roles hold USAGE here and EXECUTE on postgrest_pre_request() and '
  'nothing else; the enumeration is asserted, not assumed (ADR 0052).';

RESET ROLE;

-- This migration adds no object to `api`, so the published surface does not
-- move -- but `db-pre-request` names a function that did not exist a moment
-- ago, and a PostgREST holding a cache from before it was created answers every
-- request with `function ... does not exist`. Measured: an unresolvable hook
-- does not stop the service and does not skip the hook; it starts, reports a
-- warm schema cache, and 404s every request.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

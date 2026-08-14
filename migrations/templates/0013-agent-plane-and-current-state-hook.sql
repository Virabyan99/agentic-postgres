-- migrate:up
-- Two things, and they are in one migration because they are one property.
--
-- The hook stops trusting a signature. Until now `postgrest_pre_request` read
-- `sub`, shape-checked it and established `app.user_id`; everything else in the
-- token was taken on the strength of the signature being valid. A signature
-- says the token was issued. It does not say the subject still exists, is still
-- active, still holds that role, or still holds those scopes -- and every one
-- of those can change after issuance. From here the hook compares
-- `credential_version`, `authz_version`, `role` and sorted `scope` against
-- current state, inside the request's own transaction, and refuses on any
-- mismatch. That is SEC-REV-001's mechanism at the second verifier.
--
-- And agents get their access plane, in the shape 0012 gave humans.
--
-- **This is 0013, and the plan called it 0012** (D261): Run 8's functions had to
-- exist before Run 8's code could call them, so the numbers moved by one.
--
-- **The authenticator's `project_admin` membership is NOT here** (D266). The
-- plan puts it in this migration; `GRANT role TO role` needs authority the
-- migration plane does not hold (D102), and the three request-role memberships
-- that already exist are granted by `bin/postgres-bootstrap.py` with exactly
-- `ADMIN FALSE, INHERIT FALSE, SET TRUE`. A fourth granted here would be a
-- second authority for role membership, verified by nothing.
--
-- Every construct below was measured against the locked image before it was
-- written, each with a control.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- What the hook is allowed to ask
-- ---------------------------------------------------------------------------
--
-- The hook is SECURITY INVOKER and runs as the impersonated role -- measured in
-- 0008: `current_user` is the request role and `session_user` is the
-- authenticator, because PostgREST runs `db-pre-request` AFTER the switch. So
-- the hook cannot read `app_private.users`: 0006 took that reach away and 0011
-- never gave it back.
--
-- This is the definer helper that closes the gap, and its signature is the
-- security decision. It takes the whole claim tuple and returns a boolean. It
-- does NOT return the subject's role, scopes or versions, and that asymmetry is
-- deliberate: a function that answered "what are subject X's scopes" would let
-- any authenticated caller enumerate every other subject's authority through a
-- hook it cannot avoid running. Answering "do these five values match" makes a
-- probe cost a correct guess of all five.
--
-- Returns false rather than raising for a subject that does not exist. The hook
-- turns false into one refusal with one code; a raise here would make "no such
-- subject" arrive with a different SQLSTATE from "stale version", which is the
-- distinction 0012's lookup already declines to publish.
CREATE FUNCTION app_private.auth_claims_are_current(
  p_user_id            uuid,
  p_role_name          text,
  p_scopes             text[],
  p_credential_version integer,
  p_authz_version      integer
) RETURNS boolean
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT EXISTS (
      SELECT 1 FROM app_private.users u
      WHERE u.id                 = p_user_id
        AND u.status             = 'active'
        AND u.role_name          = p_role_name
        AND u.credential_version = p_credential_version
        AND u.authz_version      = p_authz_version
        AND u.scopes             = p_scopes
    )
  $fn$;

COMMENT ON FUNCTION app_private.auth_claims_are_current(uuid, text, text[], integer, integer) IS
  'True when every claim still matches current state. Returns a BOOLEAN and not '
  'the subject: a function answering "what are X''s scopes" would let any '
  'authenticated caller enumerate every other subject''s authority through a '
  'hook it cannot avoid running. Array equality on scopes is exact, which is '
  'why 0011 requires them sorted and deduplicated -- an unsorted stored value '
  'would refuse a token that is correct.';

-- ---------------------------------------------------------------------------
-- The hook, extended
-- ---------------------------------------------------------------------------
--
-- `CREATE OR REPLACE` on the same signature, so the grants 0008 made survive.
-- Replacing the function by dropping and creating would silently revoke
-- `anon` and `authenticated`'s EXECUTE and take every request down -- and it
-- would look like a permissions problem rather than a migration.
--
-- **It replaces the WHOLE body, and the body is now defined in four files**
-- (D270). This one was first written against 0008's text and silently dropped
-- everything 0010 added -- the statement-timeout carry, and the clause that
-- refuses the documentation role an identity rather than ignoring one. Seven
-- tests caught it, `test_the_effective_hook_is_the_last_migration_that_defines_it`
-- among them, which exists because only the last definition runs. Anything
-- editing this function reads 0010's body first, not 0008's.
--
-- Still writes nothing. 0008's measurement stands: PostgREST runs this inside
-- the request transaction, which is READ ONLY on a GET, and an early version
-- that kept an audit row turned the entire read surface into
-- 405 "cannot execute INSERT in a read-only transaction".
CREATE OR REPLACE FUNCTION app_private.postgrest_pre_request() RETURNS void
  LANGUAGE plpgsql
  SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  -- Empty is absent (0008). `nullif` is deliberately unqualified: it is a SQL
  -- construct the parser rewrites into a CASE, and `pg_catalog.nullif(text,
  -- unknown)` does not exist -- measured, on a hook that then failed every
  -- request and took the API down while the service stayed healthy.
  raw text := nullif(pg_catalog.current_setting('request.jwt.claims', true), '');
  claims jsonb;
  subject text;
  bound text;
  token_role text;
  token_scopes text[];
  credential_version integer;
  authz_version integer;
BEGIN
  -- The role's own bound, carried into this transaction (0010). PostgreSQL
  -- applies a role setting at login and this role never logs in.
  --
  -- BEFORE the two early returns, deliberately: the documentation role and an
  -- anonymous request both return early and both can hold a connection, so a
  -- bound applied after them would bound exactly the callers who authenticated.
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

  -- The documentation role has no request identity, ever (0009, 0010). A token
  -- that carries a subject is REFUSED rather than ignored: ignoring it is the
  -- same outcome today and a silent one, and the difference between "this
  -- credential cannot act" and "this credential's request was quietly
  -- reinterpreted" is the difference between a refusal somebody can debug and a
  -- permission that comes back when a policy changes.
  --
  -- It also returns before the current-state comparison below, and must: a role
  -- that reads the published shape of the API and none of its data is not a
  -- subject in the identity registry, so looking one up would refuse every
  -- documentation request.
  --
  -- `current_user::text`, unqualified. `pg_catalog.current_user` is `missing
  -- FROM-clause entry for table "pg_catalog"` -- it is a reserved keyword, not
  -- a function to look up -- and `{{api_documentation_name}}` is the LITERAL
  -- placeholder, because `{{api_documentation}}` renders a quoted identifier
  -- and would compare against a column that does not exist (D268).
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

  IF subject !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
  THEN
    RAISE EXCEPTION 'AP401: the request identity could not be read'
      USING ERRCODE = 'PT401';
  END IF;

  token_role         := claims ->> 'role';
  credential_version := (claims ->> 'credential_version')::integer;
  authz_version      := (claims ->> 'authz_version')::integer;

  -- `jsonb_array_elements_text` over a value that is not an array raises, and
  -- the handler turns that into the same 401 as everything else. A token whose
  -- `scope` is a space-delimited string -- which is what most of the world's
  -- JWTs carry -- is therefore refused rather than misread.
  BEGIN
    SELECT pg_catalog.array_agg(value ORDER BY value)
      INTO token_scopes
      FROM pg_catalog.jsonb_array_elements_text(claims -> 'scope') AS value;
  EXCEPTION WHEN others THEN
    RAISE EXCEPTION 'AP401: the request identity could not be read'
      USING ERRCODE = 'PT401';
  END;

  -- Every claim, against current state, inside this transaction. A token whose
  -- subject was disabled, whose password was reset, whose role was changed or
  -- whose scopes were narrowed is refused HERE -- not at its next expiry, and
  -- not only by the auth service, which is a different process a request to
  -- PostgREST never touches.
  IF NOT app_private.auth_claims_are_current(
       subject::uuid, token_role, token_scopes, credential_version, authz_version)
  THEN
    RAISE EXCEPTION 'AP401: the request identity is no longer current'
      USING ERRCODE = 'PT401',
            HINT = 'Obtain a new token. The subject, its role, its scopes or its '
                   'credential changed after this one was issued.';
  END IF;

  -- Transaction-local, so one request's asserted identity cannot become the
  -- next one's on a pooled connection.
  PERFORM pg_catalog.set_config('app.user_id', subject, true);
END $fn$;

COMMENT ON FUNCTION app_private.postgrest_pre_request() IS
  'PostgREST db-pre-request. Runs after the role switch, inside the request '
  'transaction, which is read-only on a GET -- so it writes nothing. Carries '
  'the role''s statement_timeout into the transaction; refuses the '
  'documentation role an identity; reads the validated claims once; and -- '
  'from Session 6 -- compares credential_version, authz_version, role and '
  'sorted scope against current state, refusing any mismatch. That last part '
  'is what makes a disable, a reset or a scope change take effect on the next '
  'request rather than at the next expiry. ADR 0052, ADR 0068, ADR 0078, '
  'SEC-REV-001.';

-- ---------------------------------------------------------------------------
-- Agents
-- ---------------------------------------------------------------------------
--
-- The same shape as 0012's human functions, and the differences are the
-- lifecycle's. An agent has no password to change, so there is no
-- `credential_version`: rotating a secret replaces the row in
-- `agent_credentials` and moves `authz_version`, because there is nothing a
-- second counter would distinguish (0011).
CREATE FUNCTION app_private.auth_lookup_agent(p_agent_id uuid)
  RETURNS TABLE (
    agent_id      uuid,
    role_name     text,
    scopes        text[],
    status        app_private.agent_status,
    authz_version integer,
    secret_hash   text
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT a.id, a.role_name, a.scopes, a.status, a.authz_version, c.secret_hash
    FROM app_private.agents a
    LEFT JOIN app_private.agent_credentials c ON c.agent_id = a.id
    WHERE a.id = p_agent_id
  $fn$;

COMMENT ON FUNCTION app_private.auth_lookup_agent(uuid) IS
  'By id, not by name. An agent presents an identifier it was given, and a '
  'lookup by name would make a guessable string the first half of the '
  'credential. No row for an unknown id -- never an exception, for the reason '
  'auth_lookup_user gives.';

CREATE FUNCTION app_private.auth_create_agent(
  p_name        text,
  p_description text,
  p_role_name   text,
  p_scopes      text[],
  p_owner_id    uuid,
  p_secret_hash text
) RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  new_id uuid;
BEGIN
  INSERT INTO app_private.agents (name, description, role_name, scopes, owner_id)
  VALUES (p_name, p_description, p_role_name, p_scopes, p_owner_id)
  RETURNING id INTO new_id;

  INSERT INTO app_private.agent_credentials (agent_id, secret_hash)
  VALUES (new_id, p_secret_hash);

  RETURN new_id;
END $fn$;

CREATE FUNCTION app_private.auth_rotate_agent_secret(
  p_agent_id    uuid,
  p_secret_hash text
) RETURNS integer
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  version integer;
BEGIN
  UPDATE app_private.agent_credentials
  SET secret_hash = p_secret_hash, issued_at = pg_catalog.now()
  WHERE agent_id = p_agent_id;

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  -- The version moves with the secret. An agent token issued before a rotation
  -- names the old `authz_version` and is refused by the hook -- which is what
  -- makes "rotate again" the documented recovery for a lost secret rather than
  -- a second live credential.
  UPDATE app_private.agents
  SET authz_version = authz_version + 1, updated_at = pg_catalog.now()
  WHERE id = p_agent_id
  RETURNING authz_version INTO version;

  RETURN version;
END $fn$;

COMMENT ON FUNCTION app_private.auth_rotate_agent_secret(uuid, text) IS
  'One transaction, and it moves authz_version. There is deliberately no way '
  'to read a secret back: the column holds an Argon2id verifier, the plaintext '
  'is shown once by the endpoint that created it, and a lost one is rotated '
  'rather than recovered. The absence is a tested property, not an omission.';

CREATE FUNCTION app_private.auth_set_agent_authorization(
  p_agent_id  uuid,
  p_role_name text,
  p_scopes    text[]
) RETURNS integer
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  version integer;
BEGIN
  UPDATE app_private.agents
  SET role_name = p_role_name, scopes = p_scopes,
      authz_version = authz_version + 1, updated_at = pg_catalog.now()
  WHERE id = p_agent_id
  RETURNING authz_version INTO version;
  RETURN version;
END $fn$;

CREATE FUNCTION app_private.auth_set_agent_status(
  p_agent_id uuid,
  p_status   app_private.agent_status
) RETURNS integer
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  version integer;
BEGIN
  UPDATE app_private.agents
  SET status = p_status, authz_version = authz_version + 1, updated_at = pg_catalog.now()
  WHERE id = p_agent_id
  RETURNING authz_version INTO version;
  RETURN version;
END $fn$;

CREATE FUNCTION app_private.auth_list_agents()
  RETURNS TABLE (
    agent_id      uuid,
    name          text,
    description   text,
    role_name     text,
    scopes        text[],
    status        app_private.agent_status,
    authz_version integer,
    owner_id      uuid,
    created_at    timestamptz
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT a.id, a.name, a.description, a.role_name, a.scopes, a.status,
           a.authz_version, a.owner_id, a.created_at
    FROM app_private.agents a
    ORDER BY pg_catalog.lower(pg_catalog.normalize(a.name))
  $fn$;

RESET ROLE;

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- The blanket revoke first, and it is load-bearing rather than tidy: a newly
-- created function is EXECUTABLE BY PUBLIC, and the `ALTER DEFAULT PRIVILEGES`
-- form that reads like the fix records nothing at all for functions. Measured
-- in Session 3 (D57) and again on this image in Run 8.
--
-- **It takes nothing away from a named grantee** (D267). `REVOKE ... FROM
-- PUBLIC` removes PUBLIC's entry and leaves every `GRANT ... TO <role>` intact
-- -- measured, with the control being an explicit `REVOKE ... FROM <role>`,
-- which does remove it. So 0012's eight grants to `auth_service` survive this
-- line and are not restated below.
--
-- The first draft of this file restated all eight, under a comment claiming
-- they had been "measured by applying this file to a cluster carrying 0012 and
-- watching the service lose its access plane". **That measurement was never
-- run.** It was caught by reading the sentence back, not by a test, and the row
-- exists because a fabricated measurement in a comment is worse than no comment
-- -- the next reader has no way to tell it from the dozens here that are real.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC;

-- `project_admin` becomes a request role in Run 9, so it needs what the other
-- three have had since 0008. The hook is re-granted to ALL FOUR rather than to
-- the new one alone: `CREATE OR REPLACE` preserves the existing grants, so
-- three of these four are already true -- and a `GRANT` of a privilege a role
-- holds is a no-op, while a list naming only the new role would read as though
-- the other three had been considered and left out.
GRANT EXECUTE ON FUNCTION app_private.postgrest_pre_request()
  TO {{anon}}, {{authenticated}}, {{api_documentation}}, {{project_admin}};

-- `project_admin` is a request role from Run 9 onward, so it needs what the
-- other three have. USAGE and EXECUTE, and nothing else.
GRANT USAGE ON SCHEMA app_private TO {{project_admin}};

-- The comparison helper, to every role that runs the hook. It is a definer
-- function returning a boolean over a tuple the caller must already know.
GRANT EXECUTE ON FUNCTION
  app_private.auth_claims_are_current(uuid, text, text[], integer, integer)
  TO {{anon}}, {{authenticated}}, {{api_documentation}}, {{project_admin}};

-- The agent plane, to the auth service alone.
GRANT EXECUTE ON FUNCTION app_private.auth_lookup_agent(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_create_agent(text, text, text, text[], uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_rotate_agent_secret(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_set_agent_authorization(uuid, text, text[]) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_set_agent_status(uuid, app_private.agent_status) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_list_agents() TO {{auth_service}};

-- 0012's eight grants to `auth_service` are NOT restated here. They survive the
-- revoke above (D267), and restating them would be eight statements that do
-- nothing, in a file where every other line does something.
-- `test_the_service_keeps_its_access_plane_after_0013` is what holds that,
-- because it is a claim about a PostgreSQL behaviour rather than about this
-- file, and the next reader should not have to take it from a comment.

-- Still not granted, to anybody: the bootstrap pair from 0012.
--
--   app_private.auth_bootstrap_administrator(...)
--   app_private.auth_bootstrap_lock_key()

REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;

-- Every prior migration that replaced this function issued one, and the
-- consistency is worth more than the saved round trip.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

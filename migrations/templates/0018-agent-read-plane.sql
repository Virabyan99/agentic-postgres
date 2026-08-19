-- migrate:up
-- The agent read plane: the hook learns what an agent is, and two read
-- functions the agent role may call.
--
-- **This is 0018 and not an edit to 0013** (ADR 0091). Two clusters hold 0013,
-- and a released migration that applies perfectly well is not edited.
--
-- **The hook below was written from 0013's body, not from memory of it**
-- (D270). `postgrest_pre_request` is defined in four files and only the last
-- one runs, so a redefinition assembled from an older body silently deletes
-- everything the versions between added -- here, the statement-timeout carry
-- (0010), the documentation-role clause (0009) and the current-state comparison
-- (0013). All three are below, unchanged, and the diff against 0013 is one
-- branch.
--
-- **What is NOT here: role membership.** The authenticator's membership in the
-- agent-reader role is `GRANT role TO role`, which needs authority the
-- migration plane does not hold (D102, D266). `bin/postgres-bootstrap.py` grants
-- it with exactly `ADMIN FALSE, INHERIT FALSE, SET TRUE`, like the other four.
-- A membership granted here would be a second authority for the one thing that
-- decides which roles a token may name.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- What the hook is allowed to ask about an agent
-- ---------------------------------------------------------------------------
--
-- 0013's `auth_claims_are_current` for humans, and this is its twin -- with one
-- deliberate difference in the return type, argued below.
--
-- The signature is the security decision, exactly as it is in 0013. It takes
-- the whole claim tuple and matches on all of it. It does not take an agent id
-- alone and it does not answer "what are agent X's scopes": a function shaped
-- that way would let any caller who reaches the hook enumerate every agent's
-- authority, and the hook is not a thing a request can decline to run.
--
-- **It returns the OWNER rather than a boolean, and that is the difference.**
-- 0013 returns a boolean because the hook already holds the subject it is about
-- to establish -- `sub` is the human's own id. An agent's `sub` is the agent's
-- id, and the identity the request must run under is its owner's (ADR 0117), a
-- value the hook cannot derive from the token. So the answer has to carry it.
--
-- The disclosure that adds is bounded by the same rule as 0013's: a caller
-- learns one uuid, and only by presenting a correct guess of the agent id, its
-- role, its exact sorted scope set and its current `authz_version`. A wrong
-- guess of any one of them returns NULL.
--
-- NULL is unambiguous. `app_private.agents.owner_id` is `uuid NOT NULL` and has
-- been since 0011, so a NULL here means "no agent matched" and can mean nothing
-- else. There is deliberately no second out-parameter saying whether a row was
-- found: two ways to spell the same failure is how one of them stops being
-- checked.
--
-- `credential_version` is not a parameter and the absence is the point. An agent
-- has no password, so 0011 gives it no such column; the token carries `0` by
-- convention (D397) so that "not a human" is a value rather than an absence.
-- The hook checks that convention itself, above -- here there is nothing to
-- compare it against, and inventing a column to compare it to would make a
-- convention into state that could drift.
CREATE FUNCTION app_private.agent_claims_are_current(
  p_agent_id      uuid,
  p_role_name     text,
  p_scopes        text[],
  p_authz_version integer
) RETURNS uuid
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT a.owner_id
    FROM app_private.agents a
    WHERE a.id            = p_agent_id
      AND a.status        = 'active'
      AND a.role_name     = p_role_name
      AND a.authz_version = p_authz_version
      AND a.scopes        = p_scopes
  $fn$;

COMMENT ON FUNCTION app_private.agent_claims_are_current(uuid, text, text[], integer) IS
  '0013''s auth_claims_are_current, for agents. Returns the agent''s OWNER on a '
  'full tuple match and NULL otherwise -- the owner rather than a boolean '
  'because an agent request runs under its owner''s identity (ADR 0117) and the '
  'token does not carry it. owner_id is NOT NULL since 0011, so NULL means "no '
  'agent matched" and nothing else. Array equality on scopes is exact, which is '
  'why 0011 requires them sorted and deduplicated. A revoked, disabled or '
  're-authorized agent stops on the NEXT request, not at the token''s expiry.';

-- ---------------------------------------------------------------------------
-- The hook
-- ---------------------------------------------------------------------------
--
-- 0013's body with one branch added, and everything else byte-for-byte what
-- 0013 left. The branch is where `token_use` is read and where the two
-- principal classes part company.
--
-- **The discriminator is `token_use`, not `current_user`** (ADR 0117). Branching
-- on the physical role would be the mechanism D393 was: a boundary standing on
-- something that happens to correlate today, changing silently the day it stops
-- correlating. `token_use` is minted as a discriminator and is the only claim
-- in the token that is one -- Run 1 measured an agent token and a human token
-- carrying the same twelve claims, the same issuer, the same audience and the
-- same key.
--
-- Still writes nothing. 0008's measurement stands: PostgREST runs this inside
-- the request transaction, which is READ ONLY on a GET.
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
  token_use text;
  credential_version integer;
  authz_version integer;
  agent_owner uuid;
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
  token_use          := claims ->> 'token_use';
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

  -- Session 8's branch, and everything about it is stated rather than implied.
  --
  -- An agent token is discriminated by `token_use`, which is the only claim
  -- minted to discriminate. `credential_version` must be 0: the convention that
  -- says "not a human" is checked here rather than trusted, so a token claiming
  -- to be an agent while carrying a human's credential version is refused.
  --
  -- The identity established is the agent's OWNER (ADR 0117). Every RLS policy
  -- in 0003 keys on `app.user_id` and none of them moves: an agent sees exactly
  -- the rows its owner sees, because it presents the same claim its owner would.
  -- `app.agent_id` is set beside it so that a function can tell WHICH principal
  -- asked -- it is never what a policy reads.
  --
  -- A human token naming an agent role, and an agent token naming a human role,
  -- are both refused by the tuple comparisons rather than by a rule of their
  -- own: `role` is compared against the stored `role_name` on both sides, and a
  -- registry holds each subject exactly once.
  IF token_use = 'agent' THEN
    IF credential_version <> 0 THEN
      RAISE EXCEPTION 'AP401: the request identity is no longer current'
        USING ERRCODE = 'PT401',
              HINT = 'An agent token carries credential_version 0. Obtain a new token.';
    END IF;

    agent_owner := app_private.agent_claims_are_current(
                     subject::uuid, token_role, token_scopes, authz_version);

    IF agent_owner IS NULL THEN
      RAISE EXCEPTION 'AP401: the request identity is no longer current'
        USING ERRCODE = 'PT401',
              HINT = 'Obtain a new token. The agent, its role, its scopes or its '
                     'secret changed after this one was issued.';
    END IF;

    -- Transaction-local, both of them, for the reason the human branch says.
    PERFORM pg_catalog.set_config('app.agent_id', subject, true);
    PERFORM pg_catalog.set_config('app.user_id', agent_owner::text, true);
    RETURN;
  END IF;

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
  'documentation role an identity; reads the validated claims once; and '
  'compares role, sorted scope and the version counters against current state, '
  'refusing any mismatch. From Session 8 it branches on token_use: an agent '
  'token is matched against app_private.agents and establishes its OWNER as '
  'app.user_id, plus app.agent_id beside it, so an agent sees exactly the rows '
  'its owner sees through policies that did not move. ADR 0052, ADR 0068, '
  'ADR 0078, ADR 0117, SEC-REV-001.';

-- ---------------------------------------------------------------------------
-- What an agent may read
-- ---------------------------------------------------------------------------
--
-- The request's own agent context, and it takes NO argument. A function
-- answering "describe agent X" would be the enumeration oracle every definer
-- function here is shaped to avoid; this one can only describe the caller,
-- because the only identity it reads is the one the hook established in this
-- transaction.
--
-- SECURITY DEFINER because `app_private.agents` is unreachable by every request
-- role and stays that way (ADR 0052): the agent role gets EXECUTE on this
-- function and no privilege on the table behind it.
--
-- Returns ZERO ROWS rather than raising when the caller is not an agent. A
-- human calling it has asked a question with no answer, not made an error, and
-- an exception here would be a second way for the API to say "you are not an
-- agent" -- one that a client would have to parse a SQLSTATE to distinguish
-- from a refusal.
--
-- `owner_id` is returned. It is the caller's own owner and the caller is
-- already running as it, so this discloses to an agent only the identity every
-- row it can read already carries.
CREATE FUNCTION api.mcp_agent_context()
  RETURNS TABLE (
    agent_id      uuid,
    role_name     text,
    scopes        text[],
    authz_version integer,
    owner_id      uuid
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT a.id, a.role_name, a.scopes, a.authz_version, a.owner_id
    FROM app_private.agents a
    WHERE a.id = nullif(pg_catalog.current_setting('app.agent_id', true), '')::uuid
      AND a.status = 'active'
  $fn$;

COMMENT ON FUNCTION api.mcp_agent_context() IS
  'The calling agent''s own context: id, role, scopes, authz_version and owner. '
  'No argument, so it cannot describe anybody else. Zero rows when the caller '
  'is not an agent -- a question with no answer rather than an error. Reads '
  'app.agent_id, which only app_private.postgrest_pre_request sets and only '
  'for the duration of one transaction.';

-- The one named read report (docs/capability-plan.md), and `run_report`'s
-- backing operation.
--
-- **SECURITY INVOKER, and that is the whole design.** A definer report would
-- read every owner's rows and hand a caller totals it has no right to; as
-- invoker, the same RLS that constrains a row constrains a count of rows, and
-- the function needs no policy of its own. It is also what makes AGT-READ-001
-- meaningful: a human and their agent get identical numbers because they run
-- the identical query under the identical claim.
--
-- It reads `api.notes` and `api.tasks`, not `app.notes` and `app.tasks`. The
-- API roles hold SELECT on the base tables and deliberately no USAGE on schema
-- `app` (0004) -- which is exactly what makes a security_invoker VIEW work and
-- direct access fail. A function body naming `app.notes` would need that schema
-- USAGE and would therefore have to widen the boundary in order to count rows.
--
-- Scalar subqueries rather than joins: `notes` and `tasks` are independent
-- aggregates, and a join between them would multiply one by the other.
CREATE FUNCTION api.owner_activity_report()
  RETURNS TABLE (
    notes_total       bigint,
    tasks_total       bigint,
    tasks_pending     bigint,
    tasks_in_progress bigint,
    tasks_completed   bigint,
    tasks_cancelled   bigint,
    latest_note_at    timestamptz,
    latest_task_at    timestamptz
  )
  LANGUAGE sql
  STABLE
  SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT
      (SELECT pg_catalog.count(*) FROM api.notes),
      (SELECT pg_catalog.count(*) FROM api.tasks),
      (SELECT pg_catalog.count(*) FROM api.tasks WHERE status = 'pending'),
      (SELECT pg_catalog.count(*) FROM api.tasks WHERE status = 'in_progress'),
      (SELECT pg_catalog.count(*) FROM api.tasks WHERE status = 'completed'),
      (SELECT pg_catalog.count(*) FROM api.tasks WHERE status = 'cancelled'),
      (SELECT pg_catalog.max(updated_at) FROM api.notes),
      (SELECT pg_catalog.max(updated_at) FROM api.tasks)
  $fn$;

COMMENT ON FUNCTION api.owner_activity_report() IS
  'The caller''s own activity, counted under the caller''s own RLS. '
  'SECURITY INVOKER: a definer report would count every owner''s rows. Reads '
  'the api views rather than the base tables, because the API roles hold table '
  'SELECT without schema USAGE on app -- the arrangement that lets a '
  'security_invoker view work while direct access stays denied (0004). Backs '
  'the run_report agent tool; a human with the same claim gets the same '
  'numbers, which is what AGT-READ-001 compares.';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- **This block runs as the object owner** (D285, ADR 0091). The `RESET ROLE` is
-- at the end of the migration, below every statement that requires ownership:
-- `REVOKE` and `GRANT EXECUTE ON FUNCTION` both do, and resetting first runs
-- them as the connected role -- `migration_user` on a host, which owns nothing.
-- That is the defect that took a live project down in Session 6.
--
-- Targeted revokes rather than `REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ... FROM
-- PUBLIC`. Three functions are created here and each is EXECUTABLE BY PUBLIC
-- the moment it exists (D57, re-measured as D262); naming them is the same
-- protection with a smaller blast radius, and it is 0005's and 0007's form for
-- functions in `api`. The blanket form would also sweep `app_private`'s other
-- functions, whose PUBLIC entries 0012 and 0013 already removed and own.
--
-- `api.mcp_agent_context` matters most here: `anon` holds USAGE on schema `api`
-- since 0001, so a function left with its default grant is callable by an
-- unauthenticated request -- and Run 5 of Session 5 measured the second
-- consequence, that `openapi-mode = follow-privileges` follows a PUBLIC grant
-- and advertises such a function in the document an anonymous caller receives.
REVOKE ALL ON FUNCTION
  app_private.agent_claims_are_current(uuid, text, text[], integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.mcp_agent_context() FROM PUBLIC;
REVOKE ALL ON FUNCTION api.owner_activity_report() FROM PUBLIC;

-- The agent-reader role becomes a request role in this session, so it needs
-- what the other four have had since 0008 and 0013: USAGE on the private
-- schema, and EXECUTE on the hook. Without both, PostgREST's `db-pre-request`
-- fails for every agent request -- `EXECUTE` requires schema `USAGE`, and the
-- hook runs AFTER the role switch (measured in 0008), so it runs as this role.
GRANT USAGE ON SCHEMA app_private TO {{agent_reader}};

-- The hook, re-granted to ALL FIVE rather than to the new role alone. `CREATE
-- OR REPLACE` preserves existing grants, so four of these five are already
-- true and a `GRANT` of a held privilege is a no-op -- while a list naming only
-- the new role would read as though the other four had been considered and left
-- out. 0013 grants the same way and for the same reason.
GRANT EXECUTE ON FUNCTION app_private.postgrest_pre_request()
  TO {{anon}}, {{authenticated}}, {{api_documentation}}, {{project_admin}}, {{agent_reader}};

-- **Both comparison helpers, to every role that runs the hook.** 0013 states
-- that rule for its own helper and this migration obeys it in both directions,
-- which the first draft did not -- it granted the agent helper to the agent role
-- alone, reasoning that "a human request never reaches this branch". The
-- reasoning is right and the conclusion was wrong, because the mirror is what
-- matters: a token's `role` claim decides which role PostgREST becomes, and
-- `token_use` decides which branch the hook takes. Those are two independent
-- values, so **every combination of role and branch is reachable by a request**.
--
-- Measured, first run of the rig: a HUMAN token naming the agent role was
-- refused with `permission denied for function auth_claims_are_current` instead
-- of `AP401`, because 0013 granted that helper to four roles and the agent role
-- is a fifth. The refusal was correct and its reason was false -- **D393
-- exactly**, arriving through a missing grant rather than through a missing row.
-- A 42501 also reaches the caller as a different failure from every other
-- refusal the hook issues, so a client cannot treat "your token is stale" as one
-- outcome.
--
-- So the agent helper goes to all five, and 0013's human helper is extended to
-- the one role that did not exist as a request role when 0013 was written. Both
-- refusals are then the hook's own `AP401`, on a tuple comparison, for every
-- principal at every door.
GRANT EXECUTE ON FUNCTION
  app_private.agent_claims_are_current(uuid, text, text[], integer)
  TO {{anon}}, {{authenticated}}, {{api_documentation}}, {{project_admin}}, {{agent_reader}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_claims_are_current(uuid, text, text[], integer, integer)
  TO {{agent_reader}};

-- The two read functions, to the agent-reader role and to nobody else
-- (ADR 0118). Not to `authenticated`, and not to `api_documentation`.
--
-- **The first draft granted the report to `authenticated` and the rig argued for
-- it**: AGT-READ-001 compares an agent's read against "the equivalent PostgREST
-- result", and a human who gets `permission denied` produces no equivalent
-- result to compare against. That argument is about the proof, and the answer is
-- on the product's side of the line.
--
-- **ADR 0003's example domain is FROZEN.** It is `notes`, `tasks`,
-- `create_note` and `update_task_status`, amended once by ADR 0048. A read RPC
-- that `authenticated` may call is a fifth human operation, and adding one is
-- superseding ADR 0003 -- which is a decision about what the product is, not a
-- convenience for a test. So the report stays agent-only, and the equivalence
-- AGT-READ-001 needs is proved against the ROW surface instead: the agent's
-- counts must equal the rows the same principal reads through `api.notes` and
-- `api.tasks`. That is the stronger statement of the two, because it ties the
-- report to the data rather than to a second function that could be wrong in
-- the same direction.
--
-- `api_documentation` therefore holds nothing here either, and that is what
-- keeps both functions out of the published document: `openapi-mode =
-- follow-privileges` reads it as that role. The agent surface is the capability
-- lock, not the REST document. Both are named in
-- `contracts/postgrest-api-surface.yaml` under `agent_rpcs` -- reviewed, and
-- deliberately not advertised.
GRANT EXECUTE ON FUNCTION api.mcp_agent_context() TO {{agent_reader}};
GRANT EXECUTE ON FUNCTION api.owner_activity_report() TO {{agent_reader}};

-- Still not granted, to anybody: the bootstrap pair from 0012, and every
-- agent-administering function from 0013, which belong to the auth service.

RESET ROLE;

-- The schema cache is a copy, and a migration that changes the API without
-- saying so leaves PostgREST serving the previous surface until something
-- restarts it. Every migration that changes the API ends here.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

-- migrate:up
-- The agent credential's lifecycle: an expiry that is enforced, and a
-- revocation that cannot be undone by flipping a flag back (ADR 0172).
--
-- **D503 is closed here**, and the measurement is what decided it. Before this
-- migration, `revoked -> active` answered 200 and handed the ORIGINAL secret its
-- authority back -- measured end to end through the running service: exchange
-- 200 fresh, 401 revoked, **200 again after re-activation**, with
-- `authz_version` at 1, 2, 3. Revocation freed no credential; it flipped a flag.
--
-- And rotation was not a way back (D839): rotating a revoked agent answered 200,
-- replaced the secret, moved `authz_version`, and **left the agent revoked** with
-- the new secret refused. So the only path from `revoked` to a working agent was
-- the one that restored the old secret, which is why this migration changes both
-- functions rather than only forbidding the transition.
--
-- ---------------------------------------------------------------------------
-- Why four functions are DROPPED rather than replaced
-- ---------------------------------------------------------------------------
--
-- **`CREATE OR REPLACE` cannot widen a `RETURNS TABLE`.** Measured against the
-- pinned image: adding one column raises **42P13**, with an identical replace
-- accepted as the control. So a released function that must return one more
-- value is dropped and recreated.
--
-- **A DROP takes the grant with it** -- also measured: `probe_service` was a
-- grantee before the DROP and `information_schema.routine_privileges` was empty
-- after the recreate. Every grant below is therefore re-issued, and forgetting
-- one is silent here and a `permission denied for function` at runtime.
--
-- This is fix-forward and not an amendment (ADR 0091): 0013 is unchanged on
-- disk and on every cluster that applied it, and this migration is the next
-- statement in the history rather than a rewrite of an earlier one.

SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The expiry
-- ---------------------------------------------------------------------------
--
-- Nullable, and **existing rows keep NULL**, which every reader below treats as
-- "does not expire". Backfilling a deadline onto credentials already in use
-- would expire agents whose operators were never told the rule changed, at a
-- moment this repository chose rather than one they did. The expiry applies from
-- the next credential each agent is issued.
--
-- No DEFAULT on the column, and that is deliberate rather than an omission:
-- `ADD COLUMN ... DEFAULT` backfills every existing row, which is exactly the
-- retroactive expiry the paragraph above refuses. The value is supplied by the
-- two functions that write a credential, so it is the service's decision and is
-- visible in the call.
ALTER TABLE app_private.agent_credentials
  ADD COLUMN expires_at timestamptz;

COMMENT ON COLUMN app_private.agent_credentials.expires_at IS
  'When this secret stops being accepted. NULL means it does not expire, which '
  'is every credential issued before Session 15 -- backfilling a deadline onto '
  'a live credential would expire agents nobody warned. Enforced at '
  'VERIFICATION rather than at issuance (ADR 0172): an expiry consulted only '
  'when a credential is minted constrains the mint and nothing else.';

-- ---------------------------------------------------------------------------
-- Verification reads the expiry, and the DATABASE decides whether it has passed
-- ---------------------------------------------------------------------------
--
-- `secret_expired` is a boolean rather than the timestamp, so there is one clock
-- in the decision. The service comparing a returned deadline against its own
-- clock would be a second authority for "has this passed", which is the shape
-- ADR 0171 refuses for a refresh token's deadline and refuses here for the same
-- reason.
DROP FUNCTION app_private.auth_lookup_agent(uuid);

CREATE FUNCTION app_private.auth_lookup_agent(p_agent_id uuid)
  RETURNS TABLE (
    agent_id       uuid,
    role_name      text,
    scopes         text[],
    status         app_private.agent_status,
    authz_version  integer,
    secret_hash    text,
    secret_expired boolean
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT a.id, a.role_name, a.scopes, a.status, a.authz_version, c.secret_hash,
           c.expires_at IS NOT NULL AND c.expires_at <= pg_catalog.now()
    FROM app_private.agents a
    LEFT JOIN app_private.agent_credentials c ON c.agent_id = a.id
    WHERE a.id = p_agent_id
  $fn$;

COMMENT ON FUNCTION app_private.auth_lookup_agent(uuid) IS
  'By id, not by name, and still one row or none -- never an exception, because '
  'a raise would make "no such agent" distinguishable by the shape of the '
  'failure. `secret_expired` is computed here so the deadline is compared '
  'against the database''s clock and not the service''s (ADR 0172).';

-- ---------------------------------------------------------------------------
-- A revoked agent is not reinstated by flipping the flag back
-- ---------------------------------------------------------------------------
--
-- Same signature and same return, so this one is a REPLACE. Only the transition
-- `revoked -> active` is refused; `active -> revoked`, `revoked -> revoked` and
-- `active -> active` behave exactly as before, and a refused call leaves the row
-- untouched -- all four measured.
--
-- `PT409` because the row is not in a state this operation can move it from,
-- which is the errcode 0007 already uses for that, and the message names the
-- operation that does work rather than only refusing.
CREATE OR REPLACE FUNCTION app_private.auth_set_agent_status(
  p_agent_id uuid,
  p_status   app_private.agent_status
) RETURNS integer
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  current_status app_private.agent_status;
  version integer;
BEGIN
  SELECT status INTO current_status FROM app_private.agents WHERE id = p_agent_id;

  -- An unknown agent still returns NULL rather than raising, which is what the
  -- service's "no such agent" path already reads. Raising here would make an
  -- absent agent distinguishable from a present one before any check.
  IF current_status IS NULL THEN
    RETURN NULL;
  END IF;

  IF current_status = 'revoked' AND p_status = 'active' THEN
    RAISE EXCEPTION 'AP409: a revoked agent is reinstated by rotating its secret'
      USING ERRCODE = 'PT409',
            HINT = 'POST /admin/agents/{agent_id}/rotate-secret issues a new '
                   'secret and clears the revocation in one operation.';
  END IF;

  UPDATE app_private.agents
  SET status = p_status, authz_version = authz_version + 1, updated_at = pg_catalog.now()
  WHERE id = p_agent_id
  RETURNING authz_version INTO version;
  RETURN version;
END $fn$;

COMMENT ON FUNCTION
  app_private.auth_set_agent_status(uuid, app_private.agent_status) IS
  'Refuses `revoked -> active` alone (ADR 0172). Measured before the guard '
  'existed: re-activation returned 200 and the ORIGINAL secret authenticated '
  'again, so revocation freed no credential. The way back is rotation, which '
  'replaces the secret and clears the revocation in one operation -- so an '
  'agent never becomes active while holding the secret its revocation was the '
  'response to.';

-- ---------------------------------------------------------------------------
-- Rotation: a new secret, an expiry, and the revocation cleared
-- ---------------------------------------------------------------------------
--
-- The signature gains a parameter, so this is a DROP rather than a replace: a
-- new argument list would otherwise create an OVERLOAD, and two functions of the
-- same name differing in arity is a call site's problem rather than a
-- migration's.
DROP FUNCTION app_private.auth_rotate_agent_secret(uuid, text);

CREATE FUNCTION app_private.auth_rotate_agent_secret(
  p_agent_id    uuid,
  p_secret_hash text,
  p_expires_at  timestamptz
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
  SET secret_hash = p_secret_hash,
      issued_at   = pg_catalog.now(),
      expires_at  = p_expires_at
  WHERE agent_id = p_agent_id;

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  -- The revocation is cleared HERE, in the same transaction as the new secret.
  -- Two operations would leave a window in which the agent is active and its
  -- live secret is the one the revocation was the response to, which is the
  -- entire state ADR 0172 removes.
  UPDATE app_private.agents
  SET status = 'active', authz_version = authz_version + 1, updated_at = pg_catalog.now()
  WHERE id = p_agent_id
  RETURNING authz_version INTO version;

  RETURN version;
END $fn$;

COMMENT ON FUNCTION
  app_private.auth_rotate_agent_secret(uuid, text, timestamptz) IS
  'One transaction: a new secret, its deadline, and the revocation cleared. '
  'Clearing it here is what makes refusing `revoked -> active` safe -- without '
  'it, an agent revoked by mistake would be permanently dead and recoverable '
  'only by creating a new one with a new id, new grants and a new owner record '
  '(D839). There is still no way to read a secret back.';

-- ---------------------------------------------------------------------------
-- Creation carries the deadline too
-- ---------------------------------------------------------------------------
DROP FUNCTION app_private.auth_create_agent(text, text, text, text[], uuid, text);

CREATE FUNCTION app_private.auth_create_agent(
  p_name        text,
  p_description text,
  p_role_name   text,
  p_scopes      text[],
  p_owner_id    uuid,
  p_secret_hash text,
  p_expires_at  timestamptz
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

  INSERT INTO app_private.agent_credentials (agent_id, secret_hash, expires_at)
  VALUES (new_id, p_secret_hash, p_expires_at);

  RETURN new_id;
END $fn$;

-- ---------------------------------------------------------------------------
-- The listing publishes the deadline
-- ---------------------------------------------------------------------------
--
-- An expiry nobody can see is an outage with a countdown. This is the surface an
-- operator diagnosing "my agent stopped working" reads, and without the column
-- the answer is indistinguishable from a wrong secret -- which is by design at
-- the exchange and unhelpful at the console.
DROP FUNCTION app_private.auth_list_agents();

CREATE FUNCTION app_private.auth_list_agents()
  RETURNS TABLE (
    agent_id          uuid,
    name              text,
    description       text,
    role_name         text,
    scopes            text[],
    status            app_private.agent_status,
    authz_version     integer,
    owner_id          uuid,
    created_at        timestamptz,
    updated_at        timestamptz,
    secret_expires_at timestamptz
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT a.id, a.name, a.description, a.role_name, a.scopes, a.status,
           a.authz_version, a.owner_id, a.created_at, a.updated_at, c.expires_at
    FROM app_private.agents a
    LEFT JOIN app_private.agent_credentials c ON c.agent_id = a.id
    ORDER BY a.created_at, a.id
  $fn$;

COMMENT ON FUNCTION app_private.auth_list_agents() IS
  'Still returns no secret and no hash -- the absence is a property of this '
  'function rather than of a handler remembering to strip them. It now '
  'publishes `secret_expires_at`, because an expiry an operator cannot see is '
  'an outage with a countdown (ADR 0172).';

-- ---------------------------------------------------------------------------
-- Privileges, re-issued because the DROPs took them
-- ---------------------------------------------------------------------------
--
-- Measured, not assumed: a grantee present before `DROP FUNCTION` was absent
-- from `information_schema.routine_privileges` after the recreate. Three of the
-- four functions below were granted by 0013 and would silently stop being
-- callable without these lines.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_private.auth_lookup_agent(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_rotate_agent_secret(uuid, text, timestamptz) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_create_agent(text, text, text, text[], uuid, text, timestamptz)
  TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_list_agents() TO {{auth_service}};

REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

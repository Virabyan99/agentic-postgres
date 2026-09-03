-- migrate:up
-- Admin-controlled password reset, where the administrator never learns the
-- password (ADR 0173), and the sessions a reset would otherwise outlive.
--
-- ---------------------------------------------------------------------------
-- What this is contrasted against, and it already exists
-- ---------------------------------------------------------------------------
--
-- `PATCH /admin/users/{user_id}` with a `password` member has set passwords
-- since Session 6, and an administrator using it **chooses the value and
-- therefore knows it**. That is the right operation for provisioning -- somebody
-- has to set the first one -- and it is the wrong one for recovery, because the
-- ordinary case of "this person cannot get in" should not end with an operator
-- holding a credential that opens somebody else's account.
--
-- This plane adds the other half: the administrator issues a one-time token,
-- the SUBJECT chooses the password, and the administrator sees neither.
--
-- ---------------------------------------------------------------------------
-- And the sessions
-- ---------------------------------------------------------------------------
--
-- `auth_set_password` already moves `credential_version`, which refuses every
-- token issued before it -- that is 0012's design and this migration does not
-- restate it. What it did not reach is the refresh plane Run 2 built: a chain
-- obtained with the OLD password would keep minting access tokens after the
-- password changed, because a refresh token names a session rather than a
-- credential.
--
-- `auth_revoke_user_sessions` is that repair. It was written in Run 3 and
-- **removed before it shipped** (D837), because it had no caller and 0011's
-- rule -- *"a grant issued now would be a grant nobody can audit against a
-- caller that does not exist"* -- is a rule this session had just turned into a
-- contract test. This is the run where the caller exists.
--
-- It is called from inside `auth_consume_password_reset` rather than granted to
-- {{auth_service}} separately: one transaction sets the password, moves the
-- version and ends the sessions, so there is no interval in which the password
-- has changed and the old chains are still live.

SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- Ending every session a subject has
-- ---------------------------------------------------------------------------
CREATE FUNCTION app_private.auth_revoke_user_sessions(
  p_user_id uuid,
  p_reason  app_private.refresh_revocation
) RETURNS integer
  LANGUAGE sql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    WITH ended AS (
      UPDATE app_private.refresh_families
         SET revoked_at = pg_catalog.now(), revoked_reason = p_reason
       WHERE user_id = p_user_id
         AND revoked_at IS NULL
      RETURNING id
    )
    SELECT pg_catalog.count(*)::integer FROM ended
  $fn$;

COMMENT ON FUNCTION
  app_private.auth_revoke_user_sessions(uuid, app_private.refresh_revocation) IS
  'Ends every live session a subject has. Not granted to the auth service: its '
  'only caller is auth_consume_password_reset, which calls it in the same '
  'transaction as the password change so there is no interval in which the '
  'password has moved and the old refresh chains are still live.';

-- ---------------------------------------------------------------------------
-- The reset itself
-- ---------------------------------------------------------------------------
--
-- Single-use, hashed, expiring -- the same three properties a refresh token has,
-- and for the same reasons. The stored value is a hex SHA-256 because the
-- subject presents the token ALONE, so the row is found BY it (ADR 0171).
--
-- `issued_by` is a real foreign key. A reset is an administrative act on
-- somebody else's account and the record of who performed it is the point: an
-- unattributable reset is indistinguishable from a compromise.
CREATE TABLE app_private.password_resets (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL
                REFERENCES app_private.users (id) ON DELETE CASCADE,
  issued_by   uuid        NOT NULL
                REFERENCES app_private.users (id) ON DELETE RESTRICT,
  token_hash  text        NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  issued_at   timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  consumed_at timestamptz,

  CONSTRAINT password_resets_expiry_follows_issue CHECK (expires_at > issued_at)
);

CREATE UNIQUE INDEX password_resets_hash_key
  ON app_private.password_resets (token_hash);

-- At most one live reset per subject, for the reason the refresh plane has the
-- same index: two outstanding resets means two values open the account and
-- neither presentation looks unusual. Issuing a second SUPERSEDES the first,
-- which `auth_open_password_reset` does explicitly rather than leaving to a
-- constraint violation an administrator would have to interpret.
CREATE UNIQUE INDEX password_resets_one_live_per_user
  ON app_private.password_resets (user_id) WHERE consumed_at IS NULL;

COMMENT ON TABLE app_private.password_resets IS
  'One-time password resets. The administrator issues one and never learns the '
  'password the subject then chooses (ADR 0173). `issued_by` is NOT NULL and a '
  'real foreign key: an unattributable reset is indistinguishable from a '
  'compromise. ON DELETE RESTRICT on the issuer, because deleting an '
  'administrator must not quietly erase who reset whose password.';

-- ---------------------------------------------------------------------------
-- Issuing
-- ---------------------------------------------------------------------------
CREATE FUNCTION app_private.auth_open_password_reset(
  p_user_id    uuid,
  p_issued_by  uuid,
  p_token_hash text,
  p_expires_at timestamptz
) RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
DECLARE
  v_reset uuid;
BEGIN
  -- The subject must exist. Returning NULL rather than raising, because the
  -- route answers 404 for an unknown user and a raise would make this the one
  -- administrative path that fails differently.
  PERFORM 1 FROM app_private.users WHERE id = p_user_id;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  -- Supersede any outstanding reset. Explicit, because the partial unique index
  -- would otherwise refuse the insert with 23505 and an administrator would be
  -- told "conflict" about a state they cannot see.
  UPDATE app_private.password_resets
     SET consumed_at = pg_catalog.now()
   WHERE user_id = p_user_id AND consumed_at IS NULL;

  INSERT INTO app_private.password_resets (user_id, issued_by, token_hash, expires_at)
  VALUES (p_user_id, p_issued_by, p_token_hash, p_expires_at)
  RETURNING id INTO v_reset;

  RETURN v_reset;
END;
$fn$;

COMMENT ON FUNCTION
  app_private.auth_open_password_reset(uuid, uuid, text, timestamptz) IS
  'Issues a one-time reset and supersedes any outstanding one. Changes no '
  'credential and ends no session: issuing a reset is not itself a revocation, '
  'and an administrator who wants the subject out NOW disables the account, '
  'which is a different act with a different record.';

-- ---------------------------------------------------------------------------
-- Consuming
-- ---------------------------------------------------------------------------
--
-- **Returns facts, not a verdict**, exactly as `auth_consume_refresh_token`
-- does, and the guard names the same kind of conditions: unconsumed and
-- unexpired. There is no family to revoke on reuse here -- a replayed reset is
-- simply refused, because the token is the whole credential and there is no
-- chain behind it to invalidate.
CREATE FUNCTION app_private.auth_consume_password_reset(
  p_token_hash    text,
  p_password_hash text
) RETURNS TABLE (
  consumed           boolean,
  found              boolean,
  was_consumed       boolean,
  expires_at         timestamptz,
  user_id            uuid,
  credential_version integer,
  sessions_ended     integer
)
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
DECLARE
  v_user    uuid;
  v_version integer;
  v_ended   integer;
BEGIN
  UPDATE app_private.password_resets r
     SET consumed_at = pg_catalog.now()
   WHERE r.token_hash   = p_token_hash
     AND r.consumed_at IS NULL
     AND r.expires_at   > pg_catalog.now()
  RETURNING r.user_id INTO v_user;

  IF NOT FOUND THEN
    RETURN QUERY
      SELECT false, true, r.consumed_at IS NOT NULL, r.expires_at, r.user_id,
             NULL::integer, NULL::integer
        FROM app_private.password_resets r
       WHERE r.token_hash = p_token_hash;

    IF NOT FOUND THEN
      RETURN QUERY SELECT false, false, false, NULL::timestamptz, NULL::uuid,
                          NULL::integer, NULL::integer;
    END IF;
    RETURN;
  END IF;

  -- The password, and the version that refuses every token issued before it.
  -- 0012's function, called rather than restated: `credential_version` has one
  -- writer and this is not a second one (ADR 0002).
  v_version := app_private.auth_set_password(v_user, p_password_hash);

  -- And the sessions. A refresh chain obtained with the OLD password would keep
  -- minting access tokens after this, because a refresh token names a session
  -- rather than a credential -- so the reset has to reach the session plane or
  -- it has not finished.
  v_ended := app_private.auth_revoke_user_sessions(v_user, 'credential_changed');

  RETURN QUERY SELECT true, true, false, NULL::timestamptz, v_user, v_version, v_ended;
END;
$fn$;

COMMENT ON FUNCTION app_private.auth_consume_password_reset(text, text) IS
  'One transaction: the reset is spent, the password is set, '
  'credential_version moves, and every refresh chain the subject had is ended '
  'with `credential_changed`. Splitting these would leave an interval in which '
  'the password had changed and a chain obtained with the old one still minted '
  'access tokens (ADR 0173).';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- Two functions, not three. `auth_revoke_user_sessions` is reached only from
-- inside `auth_consume_password_reset`, so it needs no grant -- and a grant it
-- does not need is a capability the service does not hold.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
  app_private.auth_open_password_reset(uuid, uuid, text, timestamptz) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_consume_password_reset(text, text) TO {{auth_service}};

REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

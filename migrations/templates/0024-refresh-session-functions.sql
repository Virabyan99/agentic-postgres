-- migrate:up
-- The session plane's callable surface: four SECURITY DEFINER functions and
-- their grants, arriving with the endpoints that call them (D830).
--
-- 0023 created the tables and deliberately granted nothing, because 0011 set the
-- terms for its successors: *"a grant issued now would be a grant nobody can
-- audit against a caller that does not exist."* Run 3 is the caller, so this is
-- the commit where the grants become auditable.
--
-- ---------------------------------------------------------------------------
-- Where the atomicity is, and where the meaning is
-- ---------------------------------------------------------------------------
--
-- **The transition is here; what a refusal MEANS is in `app.refresh_sessions`.**
-- That division is deliberate and it has one overlap, stated rather than
-- discovered: the guard on the consuming UPDATE names the same three facts that
-- `classify` refuses on -- consumed, revoked, expired. A contract test asserts
-- the correspondence, in the way `jwt_claims.sql_required_claims()` is asserted
-- against 0011's literal, so the two cannot drift into disagreeing about what a
-- live token is.
--
-- The duplication is not avoidable by putting the whole decision in one place.
-- Only consumption RACES, so only consumption needs the database; but a guard
-- that checked consumption alone would CONSUME an expired token before refusing
-- it, and the next presentation of that token would then read as a replay and
-- revoke the family. **A false reuse alarm on a legitimate late retry is worse
-- than the duplication**, so the guard carries all three and the correspondence
-- is tested.
--
-- What was measured against the pinned image (D826, ADR 0171): under the
-- deployment's `read committed`, two concurrent presentations resolve to one
-- winner and an EMPTY RESULT for the loser, which blocks until the winner
-- commits. `FOUND` is therefore the whole race outcome, and no advisory lock,
-- no `SELECT ... FOR UPDATE` and no retry loop is added on top of it.

SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- Opening a session
-- ---------------------------------------------------------------------------
--
-- One family, one first token, one round trip. The service has already
-- authenticated: this function trusts `p_user_id` exactly as
-- `auth_record_login` does, and for the same reason -- the identity was
-- established by the caller before this was reached, and re-deriving it here
-- would be a second authority for it (ADR 0002).
CREATE FUNCTION app_private.auth_open_session(
  p_user_id    uuid,
  p_token_hash text,
  p_expires_at timestamptz
) RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
DECLARE
  v_family uuid;
BEGIN
  INSERT INTO app_private.refresh_families (user_id)
  VALUES (p_user_id)
  RETURNING id INTO v_family;

  INSERT INTO app_private.refresh_tokens (family_id, token_hash, expires_at)
  VALUES (v_family, p_token_hash, p_expires_at);

  RETURN v_family;
END;
$fn$;

COMMENT ON FUNCTION app_private.auth_open_session(uuid, text, timestamptz) IS
  'Creates a session and its first refresh token. No status check and no '
  'credential check: the caller authenticated the subject before reaching '
  'here, and asking again would be a second authority for an answer that was '
  'already given (ADR 0002).';

-- ---------------------------------------------------------------------------
-- Presenting a refresh token
-- ---------------------------------------------------------------------------
--
-- **Returns facts, not a verdict.** `rotated` says whether the transition
-- happened; the other columns describe the row as it stands for a caller that
-- did not win. `app.refresh_sessions.classify` turns those into one of five
-- outcomes, and the precedence between them lives there and nowhere else.
--
-- **The family is revoked HERE when a consumed token is presented**, rather than
-- by a second call from the service after it has classified. That is the one
-- action this function takes on its own reading of a fact, and the reason is a
-- crash window: a service that detected a replay, logged it, and died before
-- issuing the revocation would have found a leaked chain and left it live. The
-- detection and the response are one transaction or they are a promise.
CREATE FUNCTION app_private.auth_consume_refresh_token(
  p_token_hash text,
  p_new_hash   text,
  p_expires_at timestamptz
) RETURNS TABLE (
  rotated        boolean,
  found          boolean,
  was_consumed   boolean,
  family_revoked boolean,
  expires_at     timestamptz,
  family_id      uuid,
  user_id        uuid
)
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
DECLARE
  v_token   uuid;
  v_family  uuid;
  v_user    uuid;
BEGIN
  -- The atomic attempt. Three conditions, and they are the three
  -- `classify` refuses on; the contract test asserts that correspondence.
  UPDATE app_private.refresh_tokens t
     SET consumed_at = pg_catalog.now()
    FROM app_private.refresh_families f
   WHERE t.token_hash   = p_token_hash
     AND t.consumed_at IS NULL
     AND t.expires_at   > pg_catalog.now()
     AND f.id           = t.family_id
     AND f.revoked_at  IS NULL
  RETURNING t.id, t.family_id, f.user_id
       INTO v_token, v_family, v_user;

  IF FOUND THEN
    -- Consume-then-insert, and the partial unique index refuses the reverse
    -- (D827). The successor is written after its parent is retired, so the
    -- invariant "one live token per family" holds at every statement boundary.
    INSERT INTO app_private.refresh_tokens (family_id, parent_id, token_hash, expires_at)
    VALUES (v_family, v_token, p_new_hash, p_expires_at);

    UPDATE app_private.refresh_families
       SET last_used_at = pg_catalog.now()
     WHERE id = v_family;

    RETURN QUERY SELECT true, true, false, false,
                        p_expires_at, v_family, v_user;
    RETURN;
  END IF;

  -- The attempt failed. Nothing that made it fail can un-fail: a consumed token
  -- stays consumed, a revoked family stays revoked, an expired token stays
  -- expired. So reading the row now reports the same state the guard rejected.
  RETURN QUERY
    SELECT false,
           true,
           t.consumed_at IS NOT NULL,
           f.revoked_at  IS NOT NULL,
           t.expires_at,
           t.family_id,
           f.user_id
      FROM app_private.refresh_tokens t
      JOIN app_private.refresh_families f ON f.id = t.family_id
     WHERE t.token_hash = p_token_hash;

  IF NOT FOUND THEN
    -- No row carries this digest. Not a replay: a value nobody issued is a
    -- guess, and treating it as one would let anyone revoke a family by
    -- posting arbitrary strings.
    RETURN QUERY SELECT false, false, false, false,
                        NULL::timestamptz, NULL::uuid, NULL::uuid;
    RETURN;
  END IF;

  -- A consumed token was presented. The chain leaked; close it, in this
  -- transaction, whatever the service does next.
  UPDATE app_private.refresh_families f
     SET revoked_at     = pg_catalog.now(),
         revoked_reason = 'reuse_detected'
    FROM app_private.refresh_tokens t
   WHERE t.token_hash    = p_token_hash
     AND f.id            = t.family_id
     AND t.consumed_at  IS NOT NULL
     AND f.revoked_at   IS NULL;
END;
$fn$;

COMMENT ON FUNCTION app_private.auth_consume_refresh_token(text, text, timestamptz) IS
  'Returns FACTS, not a verdict: `rotated` says whether the transition '
  'happened and the rest describe the row for a caller that did not win. '
  'app.refresh_sessions.classify names the outcome, and the precedence lives '
  'there alone. The one action taken on a fact here is revoking the family '
  'when a consumed token is presented -- detection and response are one '
  'transaction, because a service that found a leaked chain and died before '
  'revoking it would have left the chain live.';

-- ---------------------------------------------------------------------------
-- Listing and terminating
-- ---------------------------------------------------------------------------
--
-- **Both take `p_user_id` and filter on it**, so a caller cannot read or end
-- another subject's session by naming its id. The service knows the subject
-- from the presented access token; passing the family id alone would make this
-- an unauthenticated object reference, which is the shape ADR 0029 refuses
-- everywhere else in this schema.
CREATE FUNCTION app_private.auth_list_sessions(p_user_id uuid)
  RETURNS TABLE (
    family_id      uuid,
    created_at     timestamptz,
    last_used_at   timestamptz,
    revoked_at     timestamptz,
    revoked_reason app_private.refresh_revocation
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT f.id, f.created_at, f.last_used_at, f.revoked_at, f.revoked_reason
    FROM app_private.refresh_families f
    WHERE f.user_id = p_user_id
    ORDER BY f.last_used_at DESC, f.id
  $fn$;

COMMENT ON FUNCTION app_private.auth_list_sessions(uuid) IS
  'Every session this subject has, live or ended. Carries no caller-supplied '
  'string because none is stored (D829): a session is its id and its times, so '
  'a listing cannot name a device. Revoked families are included rather than '
  'hidden -- a session that ended in `reuse_detected` is the row its owner most '
  'needs to see.';

CREATE FUNCTION app_private.auth_revoke_session(
  p_user_id   uuid,
  p_family_id uuid,
  p_reason    app_private.refresh_revocation
) RETURNS boolean
  LANGUAGE sql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    WITH ended AS (
      UPDATE app_private.refresh_families
         SET revoked_at = pg_catalog.now(), revoked_reason = p_reason
       WHERE id = p_family_id
         AND user_id = p_user_id
         AND revoked_at IS NULL
      RETURNING id
    )
    SELECT EXISTS (SELECT 1 FROM ended)
  $fn$;

COMMENT ON FUNCTION
  app_private.auth_revoke_session(uuid, uuid, app_private.refresh_revocation) IS
  'Ends one session, scoped to its owner. Returns false for an unknown family, '
  'for another subject''s family and for one already ended -- three cases that '
  'are one answer on purpose, because distinguishing them would tell a caller '
  'whether a family id it guessed belongs to somebody.';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- The revoke runs BEFORE the grants, for 0012's measured reason: a function is
-- PUBLIC-executable the moment it is created, and `ALTER DEFAULT PRIVILEGES`
-- does not cover functions here. The reverse order leaves a window inside one
-- transaction and a reader who has to work out that it does not matter.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
  app_private.auth_open_session(uuid, text, timestamptz) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_consume_refresh_token(text, text, timestamptz) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_list_sessions(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_revoke_session(uuid, uuid, app_private.refresh_revocation)
  TO {{auth_service}};

-- `auth_revoke_user_sessions` is deliberately NOT here, and its absence is
-- 0011's rule applied to this run rather than quoted at the previous one. Ending
-- every session a subject has is what a password reset needs -- a reset
-- otherwise leaves a refresh chain outliving the password it was obtained with
-- -- and Run 5 is where that caller arrives. Granting EXECUTE on it now would be
-- a grant nobody can audit, which is exactly what 0023's contract test refuses
-- one migration earlier (D830, D837).
--
-- No table grant, and that is the property rather than an omission. The service
-- holds EXECUTE on five functions and `SELECT` on none of these tables, so
-- "the auth service cannot read a token digest it was not handed" is a fact of
-- the catalog rather than of the service's code.
REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

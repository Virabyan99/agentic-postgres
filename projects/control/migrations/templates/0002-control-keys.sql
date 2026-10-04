-- migrate:up
-- Management API keys, and removing a member (ADR 0253, ADR 0252).
--
-- A key is `apg_<key_id>_<secret>`: `key_id` is 16 lowercase hex, the lookup;
-- the secret is 256 random bits and only its SHA-256 is stored, compared by the
-- control mode with `hmac.compare_digest` -- never Argon2id, because a key is
-- presented on every request and rig 37c measured Argon2id at ~230 ms and
-- 64 MiB per verification against two in flight (D2052).
--
-- **A key belongs to a member of an organisation and is worth no more than
-- them.** Its effective scopes are its own intersected with what its owner's
-- CURRENT role grants, computed by the control mode on every request from
-- `control_key_lookup`, which joins the role as it is now -- NULL once the
-- member has left. So a key outlives nothing: removing the member revokes it
-- here, and even a key that escaped revocation finds no role to act as.
--
-- **No foreign key from a key to its membership** (D2094). A membership is
-- deleted when its member leaves, and a revoked key is history worth keeping,
-- so the key references the organisation and the account separately and the
-- removal function revokes before it deletes.
SET LOCAL ROLE {{object_owner}};

CREATE TABLE app.control_keys (
  key_id          text PRIMARY KEY CHECK (key_id ~ '^[0-9a-f]{16}$'),
  secret_sha256   text NOT NULL CHECK (secret_sha256 ~ '^[0-9a-f]{64}$'),
  organization_id uuid NOT NULL REFERENCES app.control_organizations(id),
  user_id         uuid NOT NULL REFERENCES app.control_accounts(user_id),
  name            text NOT NULL CHECK (length(name) BETWEEN 1 AND 64),
  -- Session 37's vocabulary is exactly the scopes a Session 37 route checks
  -- (D2052); each later session widens this CHECK with its own route.
  scopes          text[] NOT NULL CHECK (
    array_length(scopes, 1) IS NOT NULL
    AND scopes <@ ARRAY['organizations:read', 'members:read', 'projects:read', 'operations:read']
  ),
  created_at      timestamptz NOT NULL DEFAULT now(),
  last_used_at    timestamptz NULL,
  revoked_at      timestamptz NULL
);

ALTER TABLE app.control_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_keys FORCE ROW LEVEL SECURITY;

-- A key is visible to its owner, within its scoped organisation, and -- at
-- authentication -- to whoever names its id, which is what the presented key
-- carries before anyone knows who presented it.
CREATE POLICY control_keys_read ON app.control_keys
  FOR SELECT TO {{object_owner}}
  USING (
    user_id = app.current_user_id()
    OR organization_id::text = current_setting('app.control_org', true)
    OR key_id = current_setting('app.control_key_id', true)
  );
CREATE POLICY control_keys_insert ON app.control_keys
  FOR INSERT TO {{object_owner}}
  WITH CHECK (
    user_id = app.current_user_id()
    AND organization_id::text = current_setting('app.control_org', true)
  );
CREATE POLICY control_keys_update ON app.control_keys
  FOR UPDATE TO {{object_owner}}
  USING (
    user_id = app.current_user_id()
    OR organization_id::text = current_setting('app.control_org', true)
    OR key_id = current_setting('app.control_key_id', true)
  );

CREATE FUNCTION app.control_mint_key(
  p_user uuid, p_org uuid, p_key_id text, p_secret_sha256 text, p_name text, p_scopes text[]
) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  -- Any member may mint their own keys (D2053); the scopes are bounded by the
  -- CHECK above and, per request, by the owner's role.
  PERFORM app.control_require_role(p_org, 'viewer');
  INSERT INTO app.control_keys (key_id, secret_sha256, organization_id, user_id, name, scopes)
  VALUES (p_key_id, p_secret_sha256, p_org, p_user, p_name, p_scopes);
END;
$$;
COMMENT ON FUNCTION app.control_mint_key(uuid, uuid, text, text, text, text[]) IS
  'Records a key minted by a member for themselves, by id and the SHA-256 of its secret; the key is shown once and never stored (ADR 0253).';

CREATE FUNCTION app.control_list_keys(p_user uuid, p_org uuid)
  RETURNS TABLE (
    key_id text, user_id uuid, name text, scopes text[], created_at timestamptz,
    last_used_at timestamptz, revoked_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_role app.control_role;
BEGIN
  PERFORM app.control_enter(p_user);
  v_role := app.control_require_role(p_org, 'viewer');
  -- Viewers and members see their own keys; admins and owners every key of
  -- the organisation (D2053). Never a hash.
  RETURN QUERY
    SELECT k.key_id, k.user_id, k.name, k.scopes, k.created_at, k.last_used_at, k.revoked_at
      FROM app.control_keys k
     WHERE k.organization_id = p_org
       AND (k.user_id = p_user OR app.control_role_rank(v_role) >= app.control_role_rank('admin'))
     ORDER BY k.created_at, k.key_id;
END;
$$;
COMMENT ON FUNCTION app.control_list_keys(uuid, uuid) IS
  'The organisation''s keys the caller may see: their own, or all of them for an admin or owner; never a hash (ADR 0253).';

CREATE FUNCTION app.control_revoke_key(p_user uuid, p_org uuid, p_key_id text) RETURNS boolean
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_role app.control_role;
BEGIN
  PERFORM app.control_enter(p_user);
  v_role := app.control_require_role(p_org, 'viewer');
  UPDATE app.control_keys SET revoked_at = now()
   WHERE key_id = p_key_id AND organization_id = p_org AND revoked_at IS NULL
     AND (user_id = p_user OR app.control_role_rank(v_role) >= app.control_role_rank('admin'));
  RETURN FOUND;
END;
$$;
COMMENT ON FUNCTION app.control_revoke_key(uuid, uuid, text) IS
  'Revokes a key: the caller''s own, or any of the organisation''s for an admin or owner (D2053). False when there is none to revoke.';

CREATE FUNCTION app.control_key_lookup(p_key_id text)
  RETURNS TABLE (
    secret_sha256 text, organization_id uuid, user_id uuid, scopes text[], revoked boolean,
    member_role app.control_role
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_key app.control_keys%ROWTYPE;
  v_role app.control_role;
BEGIN
  PERFORM app.control_enter(NULL);
  PERFORM set_config('app.control_key_id', coalesce(p_key_id, ''), true);
  SELECT * INTO v_key FROM app.control_keys k WHERE k.key_id = p_key_id;
  IF NOT FOUND THEN
    RETURN;
  END IF;
  -- The owner's role as it is NOW, read as the owner: NULL once they left.
  PERFORM set_config('app.user_id', v_key.user_id::text, true);
  SELECT m.role INTO v_role FROM app.control_memberships m
   WHERE m.organization_id = v_key.organization_id AND m.user_id = v_key.user_id;
  RETURN QUERY SELECT v_key.secret_sha256, v_key.organization_id, v_key.user_id, v_key.scopes,
    v_key.revoked_at IS NOT NULL, v_role;
END;
$$;
COMMENT ON FUNCTION app.control_key_lookup(text) IS
  'One key by its id, with its owner''s CURRENT role (NULL when they left): what the control mode authenticates a presented key against, on every request (ADR 0253).';

CREATE FUNCTION app.control_key_used(p_key_id text) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(NULL);
  PERFORM set_config('app.control_key_id', coalesce(p_key_id, ''), true);
  -- At most once a minute: a key on a busy client must not turn every request
  -- into a row update.
  UPDATE app.control_keys SET last_used_at = now()
   WHERE key_id = p_key_id
     AND (last_used_at IS NULL OR last_used_at < now() - interval '1 minute');
END;
$$;
COMMENT ON FUNCTION app.control_key_used(text) IS
  'Stamps a key''s last use, at most once a minute (ADR 0253).';

CREATE FUNCTION app.control_remove_member(p_user uuid, p_org uuid, p_target uuid) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_mine   app.control_role;
  v_target app.control_role;
BEGIN
  PERFORM app.control_enter(p_user);
  v_mine := app.control_require_role(p_org, 'admin');
  PERFORM 1 FROM app.control_memberships
   WHERE organization_id = p_org AND role = 'owner' FOR UPDATE;
  SELECT m.role INTO v_target FROM app.control_memberships m
   WHERE m.organization_id = p_org AND m.user_id = p_target;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: not_found';
  END IF;
  IF v_target = 'owner' AND v_mine <> 'owner' THEN
    RAISE EXCEPTION 'AP403: authorization_failed';
  END IF;
  IF v_target = 'owner' AND (
    SELECT count(*) FROM app.control_memberships
     WHERE organization_id = p_org AND role = 'owner'
  ) = 1 THEN
    RAISE EXCEPTION 'AP409: last_owner';
  END IF;
  -- Revoke first, then delete: the keys stay as history and stop now.
  UPDATE app.control_keys SET revoked_at = now()
   WHERE organization_id = p_org AND user_id = p_target AND revoked_at IS NULL;
  DELETE FROM app.control_memberships WHERE organization_id = p_org AND user_id = p_target;
END;
$$;
COMMENT ON FUNCTION app.control_remove_member(uuid, uuid, uuid) IS
  'Removes a member and revokes their keys in the organisation, in one transaction: admin and above, only an owner removes an owner, the last owner stays (D2053).';

REVOKE ALL ON FUNCTION app.control_mint_key(uuid, uuid, text, text, text, text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_keys(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_revoke_key(uuid, uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_key_lookup(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_key_used(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_remove_member(uuid, uuid, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.control_mint_key(uuid, uuid, text, text, text, text[]) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_keys(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_revoke_key(uuid, uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_key_lookup(text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_key_used(text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_remove_member(uuid, uuid, uuid) TO {{auth_service}};

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

-- migrate:up
-- The control plane's people: accounts, organisations, memberships,
-- invitations and second factors (ADR 0251, ADR 0252).
--
-- This is the control project's OWN migration set, not the release's: every
-- table below exists only on the deployment whose manifest enables the
-- `control` facility. It is linted like every set -- nothing in the platform's
-- private schema, FORCE row level security on every table in `app`, an AP900
-- down -- with the one widening ADR 0251 makes for this facility: the identity
-- service's role may be granted EXECUTE on functions in `app` and USAGE on
-- `app`, and nothing else (D2046, D2073).
--
-- **Who calls these functions.** Only the control project's `auth` container
-- in APP_MODE=control, connected as `{{auth_service}}`. No request role is
-- granted anything here and nothing is created in `api`, so the control
-- project's PostgREST publishes none of it and its agent vocabulary gains
-- nothing. The identity registry stays the authority on WHO a person is; this
-- set records what they belong to.
--
-- **How a row is scoped: design G** (rig 37b, ADR 0251). Every table forces
-- row level security, so even these SECURITY DEFINER functions -- which run as
-- the owner -- see only what the policies allow. The policies read two things:
-- `app.current_user_id()` (the caller, set by `app.control_enter` from the
-- function's own `p_user`), and `app.control_org`, an organisation scope a
-- function sets ONLY after it has read the caller's own membership row
-- (`app.control_require_role`). Rig 37b measured that a setting made inside a
-- function survives its return for the rest of the transaction (D2074), so
-- `app.control_enter` RESETS every scope first: no function inherits another's
-- authority. A policy on memberships that read memberships was measured to
-- raise `infinite recursion detected in policy` (42P17); no policy here reads
-- its own table.
--
-- **Refusals** are raised as `APnnn: <word>` and mapped by the control mode:
-- AP401 invitation_invalid (one answer for used, expired, revoked and unknown),
-- AP403 authorization_failed, AP404 not_found (a foreign organisation and a
-- missing one look the same, D2053), AP409 last_owner / factor_enabled.
SET LOCAL ROLE {{object_owner}};

-- The four roles of an organisation (D2053), and their order, written once.
CREATE TYPE app.control_role AS ENUM ('owner', 'admin', 'member', 'viewer');

CREATE FUNCTION app.control_role_rank(p_role app.control_role) RETURNS integer
  LANGUAGE sql IMMUTABLE STRICT
  SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE p_role
    WHEN 'viewer' THEN 1
    WHEN 'member' THEN 2
    WHEN 'admin' THEN 3
    WHEN 'owner' THEN 4
  END;
$$;
COMMENT ON FUNCTION app.control_role_rank(app.control_role) IS
  'The organisation role matrix as one order (ADR 0252, D2053): viewer 1, member 2, admin 3, owner 4. Every role check compares ranks.';

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

-- A display copy of an identity-registry user who has entered the control
-- plane, written at acceptance and at login. The registry is the authority;
-- this row is what an organisation's member list shows.
CREATE TABLE app.control_accounts (
  user_id      uuid PRIMARY KEY,
  username     text NOT NULL UNIQUE,
  display_name text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app.control_organizations (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL CHECK (length(name) BETWEEN 1 AND 64),
  created_by uuid NOT NULL REFERENCES app.control_accounts(user_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app.control_memberships (
  organization_id uuid NOT NULL REFERENCES app.control_organizations(id),
  user_id         uuid NOT NULL REFERENCES app.control_accounts(user_id),
  role            app.control_role NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, user_id)
);

-- Two kinds in one table (D2051): an ACCOUNT invitation names no organisation
-- and no role; a MEMBERSHIP invitation names both. Only the token's SHA-256 is
-- stored -- the token is shown once, in the 201 that minted it -- and its life
-- is at most 168 hours.
CREATE TABLE app.control_invitations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash      text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  organization_id uuid NULL REFERENCES app.control_organizations(id),
  role            app.control_role NULL,
  issued_by       uuid NOT NULL,
  issued_at       timestamptz NOT NULL DEFAULT now(),
  expires_at      timestamptz NOT NULL,
  accepted_at     timestamptz NULL,
  accepted_by     uuid NULL,
  revoked_at      timestamptz NULL,
  CHECK ((organization_id IS NULL) = (role IS NULL)),
  CHECK (expires_at > issued_at AND expires_at <= issued_at + interval '168 hours')
);

-- The second factor (ADR 0252). The seed is the one stored secret that must be
-- readable -- computing a code needs the key -- so it is reachable only
-- through the functions below, granted to the identity service alone, and its
-- plaintext at rest is ADR 0252's stated residual risk. `last_step` is the
-- replay guard: a code is accepted only for a step after it.
CREATE TABLE app.control_totp (
  user_id    uuid PRIMARY KEY REFERENCES app.control_accounts(user_id),
  seed       bytea NOT NULL CHECK (length(seed) = 20),
  enabled_at timestamptz NULL,
  last_step  bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE app.control_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_accounts FORCE ROW LEVEL SECURITY;
ALTER TABLE app.control_organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_organizations FORCE ROW LEVEL SECURITY;
ALTER TABLE app.control_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE app.control_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_invitations FORCE ROW LEVEL SECURITY;
ALTER TABLE app.control_totp ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_totp FORCE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- Policies (design G). All `TO {{object_owner}}`: the definer functions are
-- the only readers, and nobody else holds a privilege on these tables.
-- ---------------------------------------------------------------------------

-- Memberships read nothing but the caller and the scope -- never themselves.
CREATE POLICY control_memberships_read ON app.control_memberships
  FOR SELECT TO {{object_owner}}
  USING (
    user_id = app.current_user_id()
    OR organization_id::text = current_setting('app.control_org', true)
  );
CREATE POLICY control_memberships_insert ON app.control_memberships
  FOR INSERT TO {{object_owner}}
  WITH CHECK (organization_id::text = current_setting('app.control_org', true));
CREATE POLICY control_memberships_update ON app.control_memberships
  FOR UPDATE TO {{object_owner}}
  USING (organization_id::text = current_setting('app.control_org', true))
  WITH CHECK (organization_id::text = current_setting('app.control_org', true));
CREATE POLICY control_memberships_delete ON app.control_memberships
  FOR DELETE TO {{object_owner}}
  USING (organization_id::text = current_setting('app.control_org', true));

-- An organisation is visible to its members.
CREATE POLICY control_organizations_read ON app.control_organizations
  FOR SELECT TO {{object_owner}}
  USING (
    id IN (
      SELECT m.organization_id FROM app.control_memberships m
      WHERE m.user_id = app.current_user_id()
    )
  );
CREATE POLICY control_organizations_insert ON app.control_organizations
  FOR INSERT TO {{object_owner}}
  WITH CHECK (created_by = app.current_user_id());

-- An account is visible to itself and, once a function has scoped an
-- organisation, to that organisation's member list.
CREATE POLICY control_accounts_read ON app.control_accounts
  FOR SELECT TO {{object_owner}}
  USING (
    user_id = app.current_user_id()
    OR user_id IN (
      SELECT m.user_id FROM app.control_memberships m
      WHERE m.organization_id::text = current_setting('app.control_org', true)
    )
  );
CREATE POLICY control_accounts_insert ON app.control_accounts
  FOR INSERT TO {{object_owner}}
  WITH CHECK (user_id = app.current_user_id());
CREATE POLICY control_accounts_update ON app.control_accounts
  FOR UPDATE TO {{object_owner}}
  USING (user_id = app.current_user_id())
  WITH CHECK (user_id = app.current_user_id());

-- An invitation is visible within its scoped organisation, to the issuer of an
-- account invitation, and -- at acceptance -- to whoever presents the hash of
-- its token, which is the only way to name it without being a member.
CREATE POLICY control_invitations_read ON app.control_invitations
  FOR SELECT TO {{object_owner}}
  USING (
    organization_id::text = current_setting('app.control_org', true)
    OR (organization_id IS NULL AND issued_by = app.current_user_id())
    OR token_hash = current_setting('app.control_token_hash', true)
  );
CREATE POLICY control_invitations_insert ON app.control_invitations
  FOR INSERT TO {{object_owner}}
  WITH CHECK (
    issued_by = app.current_user_id()
    AND (
      organization_id IS NULL
      OR organization_id::text = current_setting('app.control_org', true)
    )
  );
CREATE POLICY control_invitations_update ON app.control_invitations
  FOR UPDATE TO {{object_owner}}
  USING (
    organization_id::text = current_setting('app.control_org', true)
    OR (organization_id IS NULL AND issued_by = app.current_user_id())
    OR token_hash = current_setting('app.control_token_hash', true)
  );

-- A second factor is its owner's alone.
CREATE POLICY control_totp_own ON app.control_totp
  FOR ALL TO {{object_owner}}
  USING (user_id = app.current_user_id())
  WITH CHECK (user_id = app.current_user_id());

-- ---------------------------------------------------------------------------
-- The two helpers every caller-scoped function starts with. Not definer, not
-- granted: they run inside a definer function, as the owner.
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_enter(p_user uuid) RETURNS void
  LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  -- Every scope is reset FIRST: a setting outlives the function that made it
  -- (D2074), and a function must hold only the authority it reads itself.
  PERFORM set_config('app.control_org', '', true);
  PERFORM set_config('app.control_token_hash', '', true);
  PERFORM set_config('app.control_key_id', '', true);
  PERFORM set_config('app.user_id', coalesce(p_user::text, ''), true);
END;
$$;
COMMENT ON FUNCTION app.control_enter(uuid) IS
  'Resets every control scope and sets the caller (ADR 0251, D2074). The first statement of every caller-scoped control function.';

CREATE FUNCTION app.control_require_role(p_org uuid, p_minimum app.control_role)
  RETURNS app.control_role
  LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_role app.control_role;
BEGIN
  -- The caller's OWN membership row: visible by `user_id`, before any scope.
  SELECT m.role INTO v_role
    FROM app.control_memberships m
   WHERE m.organization_id = p_org
     AND m.user_id = app.current_user_id();
  IF NOT FOUND THEN
    -- A foreign organisation and a missing one give one answer (D2053).
    RAISE EXCEPTION 'AP404: not_found';
  END IF;
  IF app.control_role_rank(v_role) < app.control_role_rank(p_minimum) THEN
    RAISE EXCEPTION 'AP403: authorization_failed';
  END IF;
  -- Only now, having read the caller's membership, is the organisation scoped.
  PERFORM set_config('app.control_org', p_org::text, true);
  RETURN v_role;
END;
$$;
COMMENT ON FUNCTION app.control_require_role(uuid, app.control_role) IS
  'Reads the caller''s own membership of p_org, refuses a non-member (AP404) or a role below p_minimum (AP403), and only then sets app.control_org (design G, ADR 0251).';

-- ---------------------------------------------------------------------------
-- Accounts and organisations
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_record_account(p_user uuid, p_username text, p_display text)
  RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  INSERT INTO app.control_accounts (user_id, username, display_name)
  VALUES (p_user, p_username, p_display)
  ON CONFLICT (user_id) DO UPDATE
    SET username = EXCLUDED.username, display_name = EXCLUDED.display_name;
END;
$$;
COMMENT ON FUNCTION app.control_record_account(uuid, text, text) IS
  'Upserts the caller''s display copy of their identity-registry user (ADR 0252). Called at acceptance and at login.';

CREATE FUNCTION app.control_caller_roles(p_user uuid)
  RETURNS TABLE (organization_id uuid, role app.control_role)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT m.organization_id, m.role FROM app.control_memberships m
     WHERE m.user_id = p_user
     ORDER BY m.organization_id;
END;
$$;
COMMENT ON FUNCTION app.control_caller_roles(uuid) IS
  'Every organisation the caller belongs to and their role in it: what decides whether they must hold a second factor (ADR 0252).';

CREATE FUNCTION app.control_create_organization(p_user uuid, p_name text) RETURNS uuid
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_id uuid := gen_random_uuid();
BEGIN
  PERFORM app.control_enter(p_user);
  -- No RETURNING: the new organisation is not visible to its creator until the
  -- membership below exists, and RETURNING would be checked against the read
  -- policy. The id is chosen here instead.
  INSERT INTO app.control_organizations (id, name, created_by) VALUES (v_id, p_name, p_user);
  -- The creator is the one caller who may scope an organisation without a
  -- membership to read: they are making the first one.
  PERFORM set_config('app.control_org', v_id::text, true);
  INSERT INTO app.control_memberships (organization_id, user_id, role)
  VALUES (v_id, p_user, 'owner');
  RETURN v_id;
END;
$$;
COMMENT ON FUNCTION app.control_create_organization(uuid, text) IS
  'Creates an organisation and makes the caller its owner, in one transaction (ADR 0252).';

CREATE FUNCTION app.control_list_organizations(p_user uuid)
  RETURNS TABLE (id uuid, name text, role app.control_role, created_at timestamptz)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.name, m.role, o.created_at
      FROM app.control_organizations o
      JOIN app.control_memberships m ON m.organization_id = o.id AND m.user_id = p_user
     ORDER BY o.created_at, o.id;
END;
$$;
COMMENT ON FUNCTION app.control_list_organizations(uuid) IS
  'The caller''s organisations and their role in each (ADR 0252).';

CREATE FUNCTION app.control_get_organization(p_user uuid, p_org uuid)
  RETURNS TABLE (id uuid, name text, role app.control_role, created_at timestamptz)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.name, m.role, o.created_at
      FROM app.control_organizations o
      JOIN app.control_memberships m ON m.organization_id = o.id AND m.user_id = p_user
     WHERE o.id = p_org;
END;
$$;
COMMENT ON FUNCTION app.control_get_organization(uuid, uuid) IS
  'One organisation of the caller''s, or no row -- the same no row for a foreign organisation and a missing one (D2053).';

CREATE FUNCTION app.control_list_members(p_user uuid, p_org uuid)
  RETURNS TABLE (
    user_id uuid, username text, display_name text, role app.control_role,
    created_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(p_org, 'viewer');
  RETURN QUERY
    SELECT m.user_id, a.username, a.display_name, m.role, m.created_at
      FROM app.control_memberships m
      JOIN app.control_accounts a ON a.user_id = m.user_id
     WHERE m.organization_id = p_org
     ORDER BY m.created_at, m.user_id;
END;
$$;
COMMENT ON FUNCTION app.control_list_members(uuid, uuid) IS
  'An organisation''s members, for any member of it; AP404 for anyone else (ADR 0252).';

CREATE FUNCTION app.control_set_member_role(
  p_user uuid, p_org uuid, p_target uuid, p_role app.control_role
) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_mine   app.control_role;
  v_target app.control_role;
BEGIN
  PERFORM app.control_enter(p_user);
  v_mine := app.control_require_role(p_org, 'admin');
  -- The owners are locked before they are counted, so two owners demoting each
  -- other at once cannot both pass the last-owner rule.
  PERFORM 1 FROM app.control_memberships
   WHERE organization_id = p_org AND role = 'owner' FOR UPDATE;
  SELECT m.role INTO v_target FROM app.control_memberships m
   WHERE m.organization_id = p_org AND m.user_id = p_target;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: not_found';
  END IF;
  -- Only an owner touches an owner, and only an owner makes one (D2053).
  IF (v_target = 'owner' OR p_role = 'owner') AND v_mine <> 'owner' THEN
    RAISE EXCEPTION 'AP403: authorization_failed';
  END IF;
  IF v_target = 'owner' AND p_role <> 'owner' AND (
    SELECT count(*) FROM app.control_memberships
     WHERE organization_id = p_org AND role = 'owner'
  ) = 1 THEN
    RAISE EXCEPTION 'AP409: last_owner';
  END IF;
  -- The column is quoted: the project lint reads an unquoted `SET role` as a
  -- role switch and refuses it, which is the boundary working (D2095).
  UPDATE app.control_memberships SET "role" = p_role
   WHERE organization_id = p_org AND user_id = p_target;
END;
$$;
COMMENT ON FUNCTION app.control_set_member_role(uuid, uuid, uuid, app.control_role) IS
  'Changes a member''s role: admin and above; only an owner touches or makes an owner; the last owner stays (AP409 last_owner, D2053).';

-- `control_remove_member` is created in 0002, after the keys table: removing a
-- member revokes their keys in the organisation, in the same transaction.

-- ---------------------------------------------------------------------------
-- Invitations (D2051)
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_mint_invitation(
  p_user uuid, p_org uuid, p_role app.control_role, p_token_hash text,
  p_expires_at timestamptz
) RETURNS uuid
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_id   uuid := gen_random_uuid();
  v_mine app.control_role;
BEGIN
  PERFORM app.control_enter(p_user);
  IF p_org IS NOT NULL THEN
    -- A membership invitation: an owner or admin of that organisation, for a
    -- role at or below their own -- only an owner invites an owner.
    v_mine := app.control_require_role(p_org, 'admin');
    IF p_role = 'owner' AND v_mine <> 'owner' THEN
      RAISE EXCEPTION 'AP403: authorization_failed';
    END IF;
  END IF;
  -- An ACCOUNT invitation (no organisation) is minted by the control project's
  -- registry administrator. That authority is a scope on their token, which the
  -- database cannot read: the control mode checks it before calling, and the
  -- row records who issued it.
  INSERT INTO app.control_invitations
    (id, token_hash, organization_id, role, issued_by, expires_at)
  VALUES (v_id, p_token_hash, p_org, p_role, p_user, p_expires_at);
  RETURN v_id;
END;
$$;
COMMENT ON FUNCTION app.control_mint_invitation(uuid, uuid, app.control_role, text, timestamptz) IS
  'Records an invitation by the SHA-256 of its token, which is shown once and never stored (D2051).';

CREATE FUNCTION app.control_list_invitations(p_user uuid, p_org uuid)
  RETURNS TABLE (
    id uuid, role app.control_role, issued_by uuid, issued_at timestamptz,
    expires_at timestamptz, accepted_at timestamptz, revoked_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(p_org, 'admin');
  -- Never the hash: a hash is as good as the token for acceptance.
  RETURN QUERY
    SELECT i.id, i.role, i.issued_by, i.issued_at, i.expires_at, i.accepted_at, i.revoked_at
      FROM app.control_invitations i
     WHERE i.organization_id = p_org
     ORDER BY i.issued_at, i.id;
END;
$$;
COMMENT ON FUNCTION app.control_list_invitations(uuid, uuid) IS
  'An organisation''s invitations for its admins and owners, never with a token hash (D2051).';

CREATE FUNCTION app.control_revoke_invitation(p_user uuid, p_org uuid, p_id uuid) RETURNS boolean
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(p_org, 'admin');
  UPDATE app.control_invitations SET revoked_at = now()
   WHERE id = p_id AND organization_id = p_org
     AND accepted_at IS NULL AND revoked_at IS NULL;
  RETURN FOUND;
END;
$$;
COMMENT ON FUNCTION app.control_revoke_invitation(uuid, uuid, uuid) IS
  'Revokes an unspent invitation of the organisation; false when there is none to revoke.';

CREATE FUNCTION app.control_accept_invitation(p_token_hash text, p_user uuid)
  RETURNS TABLE (organization_id uuid, role app.control_role)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_org   uuid;
  v_role  app.control_role;
  v_spent boolean;
BEGIN
  PERFORM app.control_enter(p_user);
  -- The token's hash is the only name an outsider has for the row.
  PERFORM set_config('app.control_token_hash', coalesce(p_token_hash, ''), true);
  -- ONE conditional UPDATE (D2051): single use under concurrency by
  -- construction -- rig 37b measured the second of two concurrent acceptances
  -- wait for the first and update no row.
  UPDATE app.control_invitations AS i
     SET accepted_at = now(), accepted_by = p_user
   WHERE i.token_hash = p_token_hash
     AND i.accepted_at IS NULL
     AND i.revoked_at IS NULL
     AND i.expires_at > now()
  RETURNING i.organization_id, i.role INTO v_org, v_role;
  -- Read before the PERFORM below, which sets FOUND itself.
  v_spent := FOUND;
  PERFORM set_config('app.control_token_hash', '', true);
  IF NOT v_spent THEN
    -- Used, expired, revoked and unknown: one answer.
    RAISE EXCEPTION 'AP401: invitation_invalid';
  END IF;
  IF v_org IS NOT NULL THEN
    PERFORM set_config('app.control_org', v_org::text, true);
    -- An existing member keeps their role: an invitation never changes one.
    INSERT INTO app.control_memberships (organization_id, user_id, role)
    VALUES (v_org, p_user, v_role)
    ON CONFLICT ON CONSTRAINT control_memberships_pkey DO NOTHING;
  END IF;
  RETURN QUERY SELECT v_org, v_role;
END;
$$;
COMMENT ON FUNCTION app.control_accept_invitation(text, uuid) IS
  'Spends an invitation once and, for a membership invitation, creates the membership (D2051). AP401 invitation_invalid for every token that cannot be spent. The caller''s account row must exist (control_record_account, same transaction).';

-- ---------------------------------------------------------------------------
-- The second factor (ADR 0252)
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_totp_begin(p_user uuid, p_seed bytea) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  IF EXISTS (
    SELECT 1 FROM app.control_totp WHERE user_id = p_user AND enabled_at IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'AP409: factor_enabled';
  END IF;
  INSERT INTO app.control_totp (user_id, seed) VALUES (p_user, p_seed)
  ON CONFLICT (user_id) DO UPDATE
    SET seed = EXCLUDED.seed, last_step = 0, created_at = now()
    WHERE app.control_totp.enabled_at IS NULL;
END;
$$;
COMMENT ON FUNCTION app.control_totp_begin(uuid, bytea) IS
  'Stores a new, not yet enabled seed for the caller, replacing an unconfirmed one; AP409 factor_enabled when one is enabled (ADR 0252).';

CREATE FUNCTION app.control_totp_seed(p_user uuid)
  RETURNS TABLE (seed bytea, enabled boolean, last_step bigint)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT t.seed, t.enabled_at IS NOT NULL, t.last_step
      FROM app.control_totp t WHERE t.user_id = p_user;
END;
$$;
COMMENT ON FUNCTION app.control_totp_seed(uuid) IS
  'The caller''s seed, whether it is enabled, and the last accepted step -- what the control mode verifies a code against (ADR 0252).';

CREATE FUNCTION app.control_totp_confirm(p_user uuid, p_step bigint) RETURNS boolean
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  UPDATE app.control_totp SET enabled_at = now(), last_step = p_step
   WHERE user_id = p_user AND enabled_at IS NULL AND last_step < p_step;
  RETURN FOUND;
END;
$$;
COMMENT ON FUNCTION app.control_totp_confirm(uuid, bigint) IS
  'Enables the caller''s seed at the step the control mode verified; false when there is no unconfirmed seed or the step is not new.';

CREATE FUNCTION app.control_totp_accept_step(p_user uuid, p_step bigint) RETURNS boolean
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  -- Atomic: the step is recorded by the statement that accepts it, so a code
  -- presented twice -- at once or in turn -- is accepted once (ADR 0252).
  UPDATE app.control_totp SET last_step = p_step
   WHERE user_id = p_user AND enabled_at IS NOT NULL AND last_step < p_step;
  RETURN FOUND;
END;
$$;
COMMENT ON FUNCTION app.control_totp_accept_step(uuid, bigint) IS
  'Records a verified step as used; false for a step at or below the last accepted -- a replay (ADR 0252).';

-- The operator's reset for a lost device. SECURITY INVOKER and granted to
-- nobody: only the bootstrap superuser can execute it, and the superuser is
-- the one role row security does not bind, so the function needs no scope of
-- its own (`sudo bin/control.sh totp-reset`, D2068).
CREATE FUNCTION app.control_totp_reset(p_username text) RETURNS boolean
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  DELETE FROM app.control_totp
   WHERE user_id = (SELECT a.user_id FROM app.control_accounts a WHERE a.username = p_username);
  RETURN FOUND;
END;
$$;
COMMENT ON FUNCTION app.control_totp_reset(text) IS
  'Removes one person''s second factor. Granted to nobody; run by root through bin/control.sh totp-reset (ADR 0252, D2068).';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- Revoked from PUBLIC first, function by function: default privileges do not
-- cover functions here (migration 0001's measured note, D57), so a function is
-- PUBLIC-executable the moment it is created.
REVOKE ALL ON FUNCTION app.control_role_rank(app.control_role) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_enter(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_require_role(uuid, app.control_role) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_record_account(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_caller_roles(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_create_organization(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_organizations(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_organization(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_members(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_set_member_role(uuid, uuid, uuid, app.control_role) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_mint_invitation(uuid, uuid, app.control_role, text, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_invitations(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_revoke_invitation(uuid, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_accept_invitation(text, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_totp_begin(uuid, bytea) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_totp_seed(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_totp_confirm(uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_totp_accept_step(uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_totp_reset(text) FROM PUBLIC;

-- The schema, so the role can name these functions at all (D2073: rig 37b
-- measured `permission denied for schema app` without it). It reads no table:
-- the role holds no table privilege anywhere in this set.
GRANT USAGE ON SCHEMA app TO {{auth_service}};

GRANT EXECUTE ON FUNCTION app.control_record_account(uuid, text, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_caller_roles(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_create_organization(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_organizations(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_organization(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_members(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_set_member_role(uuid, uuid, uuid, app.control_role) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_mint_invitation(uuid, uuid, app.control_role, text, timestamptz) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_invitations(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_revoke_invitation(uuid, uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_accept_invitation(text, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_totp_begin(uuid, bytea) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_totp_seed(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_totp_confirm(uuid, bigint) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_totp_accept_step(uuid, bigint) TO {{auth_service}};

-- There is no GRANT for `control_totp_reset`, `control_enter`,
-- `control_require_role` or `control_role_rank`, and that absence is the
-- decision (ADR 0251): the first is the operator's, the other three run only
-- inside the functions above.

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

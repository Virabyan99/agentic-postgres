-- migrate:up
-- The access plane for human subjects: the only way `auth_service` reaches the
-- identity registry, and the reason 0011 granted it schema USAGE and nothing
-- else.
--
-- 0011 said so in its own text -- "the service reaches this data through
-- SECURITY DEFINER functions that arrive in the same commit as the code that
-- calls them, which is Run 8's" -- and this is that commit. A grant issued in
-- 0011 would have been a grant nobody could audit against a caller that did not
-- exist.
--
-- **This is 0012, and the plan called Run 9's migration 0012** (D261). Run 8's
-- functions have to exist before Run 8's code can call them, so the numbers move
-- by one: the pre-request hook's extension is 0013.
--
-- Every construct below was measured against the locked `pgvector/pgvector:pg18`
-- image (server 18.4) before it was written, each with a control in the same
-- run. Two of those measurements changed what this file says, and both are
-- noted where they land.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The bootstrap lock key
-- ---------------------------------------------------------------------------
--
-- Derived from `project_identity`, not passed in. A caller-supplied key would
-- be a second authority for a project-scoped identifier, and the failure would
-- be silent: two callers with different keys take different locks and both
-- proceed, which is precisely the outcome the lock exists to prevent.
--
-- Advisory locks are per-database, and each project has its own database, so a
-- constant would in fact be sufficient today. It is derived anyway because the
-- sentence this implements is "a project-scoped advisory lock", and a constant
-- that happens to be adequate is a constant somebody has to re-derive the
-- adequacy of.
CREATE FUNCTION app_private.auth_bootstrap_lock_key() RETURNS bigint
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT pg_catalog.hashtext(i.project_key)::bigint
    FROM app_private.project_identity i
    WHERE i.singleton
  $fn$;

COMMENT ON FUNCTION app_private.auth_bootstrap_lock_key() IS
  'The project-scoped advisory lock key, derived from project_identity rather '
  'than supplied by the caller: two callers with different keys take different '
  'locks and both proceed, which is the exact failure the lock prevents.';

-- ---------------------------------------------------------------------------
-- Reading a subject
-- ---------------------------------------------------------------------------
--
-- `auth_lookup_user` returns the verifier along with the subject, and that is
-- deliberate rather than convenient: the Argon2 comparison happens in the
-- service, at the frozen profile (ADR 0081), because the database has no
-- Argon2id at that profile and adding one would be a second hasher whose
-- parameters nothing checks.
--
-- It returns AT MOST ONE ROW and never raises for an unknown username. An
-- exception here would make "no such user" distinguishable from "wrong
-- password" by the shape of the failure, and the service's whole login path
-- exists to make those two indistinguishable. The absence is data, not an
-- error.
--
-- The lookup is by the SAME normalised expression the unique index uses. A
-- plain `WHERE username = p_username` would be a second definition of identity:
-- `Ada` could log in and `ADA` could not, against a table that considers them
-- the same account.
--
-- **The one-argument `normalize` is not a shorthand; it is the only spelling
-- that can be schema-qualified** (D263). `normalize(x, NFC)` -- which 0011's
-- index is written with -- takes a KEYWORD second argument, in a grammar that
-- exists only for the bare name: `pg_catalog.normalize(x, NFC)` fails with
-- `column "nfc" does not exist`. Measured, by writing it that way first.
--
-- So the choice was to bend this schema's definer-hygiene rule -- 0005: "a
-- caller who can create a temporary object shadows an unqualified name and
-- executes it as the owner" -- or to find a qualifiable spelling. Measured:
-- `pg_catalog.normalize(x)` equals `normalize(x, NFC)`, and the planner still
-- uses `users_username_normalised_key` for it, against a control predicate that
-- plans as a sequential scan. Nothing is bent and nothing is slower.
CREATE FUNCTION app_private.auth_lookup_user(p_username text)
  RETURNS TABLE (
    user_id            uuid,
    role_name          text,
    scopes             text[],
    status             app_private.user_status,
    credential_version integer,
    authz_version      integer,
    password_hash      text
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT u.id, u.role_name, u.scopes, u.status,
           u.credential_version, u.authz_version, c.password_hash
    FROM app_private.users u
    LEFT JOIN app_private.user_credentials c ON c.user_id = u.id
    WHERE pg_catalog.lower(pg_catalog.normalize(u.username))
        = pg_catalog.lower(pg_catalog.normalize(p_username))
  $fn$;

COMMENT ON FUNCTION app_private.auth_lookup_user(text) IS
  'At most one row, and no row for an unknown username -- never an exception. '
  'A raise here would make "no such user" distinguishable from "wrong password" '
  'by the shape of the failure. LEFT JOIN, so a subject with no credential row '
  'returns a NULL hash rather than vanishing: that is a different fault and the '
  'service verifies against its dummy either way.';

-- The state `/auth/me` reflects, and the state migration 0013''s hook will
-- compare a token against. No verifier here: nothing on this path needs one,
-- and a function that returned it would be one more place a hash can be read.
CREATE FUNCTION app_private.auth_user_state(p_user_id uuid)
  RETURNS TABLE (
    username           text,
    display_name       text,
    role_name          text,
    scopes             text[],
    status             app_private.user_status,
    credential_version integer,
    authz_version      integer,
    last_login_at      timestamptz
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT u.username, u.display_name, u.role_name, u.scopes, u.status,
           u.credential_version, u.authz_version, u.last_login_at
    FROM app_private.users u
    WHERE u.id = p_user_id
  $fn$;

CREATE FUNCTION app_private.auth_record_login(p_user_id uuid) RETURNS void
  LANGUAGE sql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    UPDATE app_private.users SET last_login_at = pg_catalog.now()
    WHERE id = p_user_id
  $fn$;

COMMENT ON FUNCTION app_private.auth_record_login(uuid) IS
  'Deliberately does NOT move updated_at. That column tracks changes to what a '
  'subject IS; a login changes nothing about the subject, and a reviewer '
  'reading updated_at should not have to ask which kind of event moved it.';

-- ---------------------------------------------------------------------------
-- Administering a subject
-- ---------------------------------------------------------------------------
--
-- The vocabulary is not checked here, and that is a division rather than a gap.
-- The table enforces SHAPE -- sorted, deduplicated, non-empty, no NULL element
-- (0011, ADR 0080) -- and the auth service enforces MEANING against
-- `scope_registry` (ADR 0079), which is a Python mapping onto the capability
-- schema and cannot be restated in SQL without becoming a second authority.
--
-- `authz_version` moves on every change to role, scopes or status, and
-- `credential_version` on every password change. Both are incremented in the
-- same statement as the change, so there is no window in which the row is new
-- and the version is old. That is SEC-REV-001's mechanism and it is why neither
-- column is ever set by a caller: a parameter would let the caller replay one.
CREATE FUNCTION app_private.auth_create_user(
  p_username      text,
  p_display_name  text,
  p_role_name     text,
  p_scopes        text[],
  p_password_hash text
) RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  new_id uuid;
BEGIN
  INSERT INTO app_private.users (username, display_name, role_name, scopes)
  VALUES (p_username, p_display_name, p_role_name, p_scopes)
  RETURNING id INTO new_id;

  INSERT INTO app_private.user_credentials (user_id, password_hash)
  VALUES (new_id, p_password_hash);

  RETURN new_id;
END $fn$;

COMMENT ON FUNCTION app_private.auth_create_user(text, text, text, text[], text) IS
  'Subject and verifier in one transaction. Two calls would admit a subject '
  'with no credential, which is a row that can never log in and that nothing '
  'downstream distinguishes from one whose password was removed.';

CREATE FUNCTION app_private.auth_set_authorization(
  p_user_id   uuid,
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
  UPDATE app_private.users
  SET role_name     = p_role_name,
      scopes        = p_scopes,
      authz_version = authz_version + 1,
      updated_at    = pg_catalog.now()
  WHERE id = p_user_id
  RETURNING authz_version INTO version;

  RETURN version;  -- NULL when no such subject; the caller decides what that means
END $fn$;

CREATE FUNCTION app_private.auth_set_status(
  p_user_id uuid,
  p_status  app_private.user_status
) RETURNS integer
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  version integer;
BEGIN
  -- The version moves even when the status is unchanged, and that is not
  -- waste: `disable` then `enable` has to leave a subject whose old tokens are
  -- refused, and a version that only moved on a *transition* would leave the
  -- second call as a no-op if the first was repeated. SEC-REV-001 is about the
  -- pair, not about either half.
  UPDATE app_private.users
  SET status        = p_status,
      authz_version = authz_version + 1,
      updated_at    = pg_catalog.now()
  WHERE id = p_user_id
  RETURNING authz_version INTO version;

  RETURN version;
END $fn$;

CREATE FUNCTION app_private.auth_set_password(
  p_user_id       uuid,
  p_password_hash text
) RETURNS integer
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  version integer;
BEGIN
  UPDATE app_private.user_credentials
  SET password_hash = p_password_hash, updated_at = pg_catalog.now()
  WHERE user_id = p_user_id;

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  UPDATE app_private.users
  SET credential_version = credential_version + 1,
      updated_at         = pg_catalog.now()
  WHERE id = p_user_id
  RETURNING credential_version INTO version;

  RETURN version;
END $fn$;

COMMENT ON FUNCTION app_private.auth_set_password(uuid, text) IS
  'One transaction, so a stored hash and its credential_version cannot '
  'disagree. A token issued before the change carries the older version and is '
  'refused by the hook -- which is what makes a password reset invalidate '
  'outstanding tokens rather than merely changing what a new login checks.';

-- A read for the administration surface. Returns no verifier, for the reason
-- `auth_user_state` returns none.
CREATE FUNCTION app_private.auth_list_users()
  RETURNS TABLE (
    user_id            uuid,
    username           text,
    display_name       text,
    role_name          text,
    scopes             text[],
    status             app_private.user_status,
    credential_version integer,
    authz_version      integer,
    created_at         timestamptz,
    last_login_at      timestamptz
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT u.id, u.username, u.display_name, u.role_name, u.scopes, u.status,
           u.credential_version, u.authz_version, u.created_at, u.last_login_at
    FROM app_private.users u
    ORDER BY pg_catalog.lower(pg_catalog.normalize(u.username))
  $fn$;

-- ---------------------------------------------------------------------------
-- The first administrator
-- ---------------------------------------------------------------------------
--
-- Measured, with a control, before this was written. Two connections driven
-- through the interleaving by hand rather than raced by threads -- a flaky
-- reproduction is a measurement that will one day report the bug is fixed:
--
--   without the lock: A and B each read "no administrator", each insert, and
--   after both commit the table holds TWO administrators.
--
--   with it: B blocks at `pg_advisory_xact_lock` and cannot read at all until A
--   commits; on retry it is refused by the existence check, which is the second
--   line and the one that reports something useful.
--
-- `pg_advisory_XACT_lock`, not the session form. Also measured: a session lock
-- is still held after COMMIT, so through a transaction-mode pooler it would be
-- stranded on whichever backend ran the statement. `bin/auth-admin.sh` connects
-- directly rather than through PgBouncer, and uses the transaction form anyway
-- -- a lock whose correctness depends on the caller's transport is not a lock.
--
-- A partial unique index would be the stronger construction and does not fit:
-- it would forbid the SECOND administrator, which `POST /admin/users` creates
-- legitimately. What is being serialised is the bootstrap, not the role.
CREATE FUNCTION app_private.auth_bootstrap_administrator(
  p_username      text,
  p_display_name  text,
  p_role_name     text,
  p_scopes        text[],
  p_password_hash text
) RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  new_id uuid;
BEGIN
  PERFORM pg_catalog.pg_advisory_xact_lock(app_private.auth_bootstrap_lock_key());

  IF EXISTS (
    SELECT 1 FROM app_private.users
    WHERE role_name = p_role_name AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'AP409: an active administrator already exists'
      USING HINT = 'Inspect administrator state through the protected CLI. Do '
                   'not re-run this with a new password until the state is known.';
  END IF;

  new_id := app_private.auth_create_user(
    p_username, p_display_name, p_role_name, p_scopes, p_password_hash
  );
  RETURN new_id;
END $fn$;

COMMENT ON FUNCTION app_private.auth_bootstrap_administrator(text, text, text, text[], text) IS
  'One-time, under a project-scoped transaction advisory lock. Measured: '
  'without the lock two concurrent callers both read "no administrator" and '
  'both insert. The existence check is the second line, not the first -- it is '
  'what the loser is refused by, and it reports something an operator can act '
  'on. AP409 is deliberately not a retry-and-hope: a lost bootstrap output is '
  'recovered by inspecting state, never by bootstrapping again.';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- **This block runs as the object owner, and the `RESET ROLE` that used to sit
-- above it now sits below it** (D285, ADR 0091). `REVOKE ALL ON ALL FUNCTIONS`
-- and `GRANT EXECUTE ON FUNCTION` both require ownership of every function
-- they touch. Reset first and they run as the *connected* role -- which on a
-- host is `migration_user`, and which owns nothing -- so the migration fails on
-- its own first revoke with `permission denied for function is_scope_set
-- (42501)`. 0011 already had these two in the right order; 0012 and 0013 did
-- not, and nothing caught it because every offline proof applied migrations as
-- a SUPERUSER, which bypasses the ownership check entirely.
--
-- **A newly created function is EXECUTABLE BY PUBLIC.** Measured on this
-- server, with a control (D262): `proacl` is NULL on every function above,
-- NULL means the built-in default, and the built-in default includes PUBLIC.
-- The `ALTER DEFAULT PRIVILEGES ... REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`
-- that 0011 uses for TABLES and SEQUENCES **records nothing at all** for
-- functions -- `pg_default_acl` stays empty and the next function created is
-- still PUBLIC-executable, in both the `FUNCTIONS` and `ROUTINES` spellings.
-- The control is a GRANT for tables in the same rig, which does store a row.
--
-- So the revoke below is not belt-and-braces. It is the only thing standing
-- between these functions and every role in the cluster that holds USAGE on
-- `app_private` -- and it runs BEFORE the grant, because the reverse order
-- leaves a window in a migration that is one transaction and a reader who has
-- to work out that it does not matter.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_private.auth_lookup_user(text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_user_state(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_record_login(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_create_user(text, text, text, text[], text)
  TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_set_authorization(uuid, text, text[])
  TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_set_status(uuid, app_private.user_status) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_set_password(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_list_users() TO {{auth_service}};

-- NOT granted to `auth_service`, and the omission is the design. The bootstrap
-- is an operator at a terminal on the host, connecting directly as the object
-- owner; a service that could call it is a service that could create the first
-- administrator in response to a request, which is the public bootstrap
-- endpoint §4 says does not exist. `auth_bootstrap_lock_key` is likewise not
-- granted: nothing outside the bootstrap needs the key, and a caller that can
-- read it can take the lock.
--
--   app_private.auth_bootstrap_administrator(...)
--   app_private.auth_bootstrap_lock_key()

REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

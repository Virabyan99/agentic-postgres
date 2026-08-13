-- migrate:up
-- The identity registry: who a subject is, what it may become, and what the
-- claim contract says a token has to carry (ADR 0078, D218).
--
-- **Created from nothing.** The Session 6 runbook describes this as extending an
-- existing `app_private.users` with `role_name`, `scopes` and `last_login_at`,
-- preserving "existing IDs, username rules, display-name rules, status values,
-- and timestamps", through a nullable-add -> backfill -> validate -> NOT NULL
-- sequence. There is no such table and there never has been: `app_private` holds
-- `project_identity`, `migration_ledger` and the pre-request hook, and nothing
-- else. So every column here is NOT NULL from creation, and the backfill is
-- struck rather than written against zero rows -- a backfill test that passes on
-- an empty table passes for a reason that is not correctness (D218).
--
-- **No foreign key to `app.notes.owner_id`.** That column holds whatever the
-- `app.user_id` claim carried, which ADR 0029 states in its title is *trusted,
-- not authenticated*. A foreign key would silently redefine it as a reference to
-- this table, and every row written before this migration would have to be
-- either deleted or invented.
--
-- Every SQL construct below was measured against the locked image before it was
-- written, with a control in the same run. Three of those measurements changed
-- what this file says; they are noted where they land.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- Status vocabularies
-- ---------------------------------------------------------------------------
--
-- Enums rather than text with a CHECK, matching `api.task_status` from 0007.
-- Separate types for users and agents because the words differ in kind: a user
-- is `disabled` by an administrator and can be re-enabled; an agent credential
-- is `revoked`, which is terminal for that credential. Sharing one type would
-- invite a query that treated them as the same event, and SEC-REV-001 is the
-- proof that they are not.
CREATE TYPE app_private.user_status AS ENUM ('active', 'disabled');
CREATE TYPE app_private.agent_status AS ENUM ('active', 'revoked');

-- ---------------------------------------------------------------------------
-- The scope-shape helper
-- ---------------------------------------------------------------------------
--
-- ADR 0078 requires a token's `scope` to be a sorted, deduplicated array of
-- non-null strings. The database holds the same line, so a row written by
-- anything other than the auth service is refused rather than trusted.
--
-- It is a function because the obvious spelling is not accepted:
--
--   CHECK (scopes = ARRAY(SELECT DISTINCT unnest(scopes) ORDER BY 1))
--   ERROR:  cannot use subquery in check constraint
--
-- Measured. A CHECK may *call* a function whose body contains the subquery.
--
-- `coalesce(..., false)` and the explicit NULL-element test are the two clauses
-- that matter, and both come from a measurement that went the wrong way. The
-- first draft was `SELECT a = ARRAY(SELECT DISTINCT unnest(a) ORDER BY 1)`, and
-- it **accepted `ARRAY['a', NULL]`**: array comparison with a NULL element is
-- NULL, and a CHECK constraint PASSES when its expression is NULL. Three-valued
-- logic, in the one place where "unknown" has to mean "no". So this function
-- cannot return NULL for any reason, including one nobody has thought of yet.
--
-- IMMUTABLE and STRICT so it is usable in a constraint at all; the pinned
-- `search_path` is the same one every function in this schema carries, because a
-- resolvable name is the whole attack surface of a definer.
CREATE FUNCTION app_private.is_scope_set(a text[]) RETURNS boolean
  LANGUAGE sql
  IMMUTABLE
  STRICT
  PARALLEL SAFE
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT coalesce(
      array_position(a, NULL) IS NULL
        AND a = ARRAY(SELECT DISTINCT pg_catalog.unnest(a) ORDER BY 1),
      false)
  $fn$;

COMMENT ON FUNCTION app_private.is_scope_set(text[]) IS
  'True when the array is sorted, deduplicated and free of NULL elements. Never '
  'returns NULL: a CHECK constraint passes when its expression is NULL, so a '
  'NULL-returning shape would admit exactly the rows it exists to refuse. '
  'Measured against ARRAY[''a'', NULL], which the first draft accepted. ADR 0078.';

-- ---------------------------------------------------------------------------
-- Human subjects
-- ---------------------------------------------------------------------------
--
-- `username` uniqueness is case-insensitive AND Unicode-normalised, through a
-- unique index on `lower(normalize(username, NFC))`. Both functions are
-- IMMUTABLE on this server -- read out of `pg_proc.provolatile`, not assumed --
-- which is what makes the expression indexable.
--
-- Measured with a control: `Ada` and `ADA` collide; `jose` + U+0301 and
-- U+00E9-composed `josé` collide; `Grace` inserts. Without the normalisation,
-- two visually identical usernames are two accounts, and the second one to
-- register is the one an administrator cannot tell apart from the first.
--
-- `role_name` is the derived database role a token for this subject names. Text
-- rather than a foreign key to anything: roles are cluster-global objects the
-- bootstrap plane owns (D102), and this schema does not get to reference them.
-- What constrains it is the auth service's registry (ADR 0079), which is a
-- check the *issuer* performs -- stated here so the absence is deliberate.
--
-- The two version columns are ADR 0078's, and they are the mechanism behind
-- SEC-REV-001. `credential_version` moves when the password changes;
-- `authz_version` moves when the role or scopes change, or when the subject is
-- disabled and re-enabled. Both are monotonic and neither is ever reused, which
-- is why a re-enabled subject cannot present a token issued before the disable.
CREATE TABLE app_private.users (
  id                  uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  username            text          NOT NULL CHECK (username <> ''),
  display_name        text          NOT NULL CHECK (display_name <> ''),
  role_name           text          NOT NULL CHECK (role_name <> ''),
  scopes              text[]        NOT NULL
                        CHECK (app_private.is_scope_set(scopes))
                        CHECK (array_length(scopes, 1) IS NOT NULL),
  status              app_private.user_status NOT NULL DEFAULT 'active',
  credential_version  integer       NOT NULL DEFAULT 1 CHECK (credential_version >= 1),
  authz_version       integer       NOT NULL DEFAULT 1 CHECK (authz_version >= 1),
  created_at          timestamptz   NOT NULL DEFAULT now(),
  updated_at          timestamptz   NOT NULL DEFAULT now(),
  last_login_at       timestamptz
);

-- NOT NULL beside every `<> ''`, and that pairing is not decoration: a NULL
-- passes `CHECK (v <> '')` for the same reason the scope helper had to stop
-- returning NULL. Measured on this server.
CREATE UNIQUE INDEX users_username_normalised_key
  ON app_private.users (lower(normalize(username, NFC)));

COMMENT ON TABLE app_private.users IS
  'Human subjects. Created in Session 6 from nothing -- the runbook''s '
  '"preserve inherited rows" has no subject, and a backfill over zero rows '
  'proves nothing (D218). No foreign key reaches app.notes.owner_id: that '
  'column is trusted, not authenticated (ADR 0029).';

COMMENT ON COLUMN app_private.users.authz_version IS
  'Monotonic, and never reused. Moves on any change to role, scopes or status, '
  'so a token issued before a disable is refused after a re-enable -- which is '
  'SEC-REV-001 and is not implied by any check on status alone.';

-- ---------------------------------------------------------------------------
-- Human credentials, in their own table
-- ---------------------------------------------------------------------------
--
-- Separate from `users` so that reading a subject cannot read its verifier by
-- accident. Every query that wants the hash has to name this table, which makes
-- "did this code path touch the credential" a grep rather than a review.
--
-- One row per user, enforced by the primary key being the user id rather than by
-- a unique constraint on a surrogate: two credential rows for one subject is a
-- state in which "the current password" is a question with two answers.
CREATE TABLE app_private.user_credentials (
  user_id       uuid         PRIMARY KEY
                  REFERENCES app_private.users (id) ON DELETE CASCADE,
  password_hash text         NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
  updated_at    timestamptz  NOT NULL DEFAULT now()
);

COMMENT ON TABLE app_private.user_credentials IS
  'Argon2id verifiers, one per subject. The CHECK asserts the encoded prefix so '
  'a row holding a bcrypt hash, a raw password or an empty string is refused at '
  'write time -- the profile itself is read back out of the encoded hash by '
  'SEC-CRED-002, not from the hasher''s constructor arguments.';

-- ---------------------------------------------------------------------------
-- Agents
-- ---------------------------------------------------------------------------
--
-- Same shape, different lifecycle. An agent has no password to change, so it
-- carries no `credential_version`: a rotated agent secret replaces the row in
-- `agent_credentials` and moves `authz_version`, and there is nothing a
-- separate counter would distinguish.
CREATE TABLE app_private.agents (
  id             uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  name           text          NOT NULL CHECK (name <> ''),
  description    text          NOT NULL DEFAULT '',
  role_name      text          NOT NULL CHECK (role_name <> ''),
  scopes         text[]        NOT NULL
                   CHECK (app_private.is_scope_set(scopes))
                   CHECK (array_length(scopes, 1) IS NOT NULL),
  status         app_private.agent_status NOT NULL DEFAULT 'active',
  authz_version  integer       NOT NULL DEFAULT 1 CHECK (authz_version >= 1),
  owner_id       uuid          NOT NULL REFERENCES app_private.users (id),
  created_at     timestamptz   NOT NULL DEFAULT now(),
  updated_at     timestamptz   NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX agents_name_normalised_key
  ON app_private.agents (lower(normalize(name, NFC)));

COMMENT ON TABLE app_private.agents IS
  'Non-human subjects, owned by a human one. `owner_id` is NOT NULL and a real '
  'foreign key -- unlike app.notes.owner_id, which predates this table and '
  'holds a claim value. An agent with no owner is an authority nobody is '
  'accountable for.';

CREATE TABLE app_private.agent_credentials (
  agent_id     uuid         PRIMARY KEY
                 REFERENCES app_private.agents (id) ON DELETE CASCADE,
  secret_hash  text         NOT NULL CHECK (secret_hash LIKE '$argon2id$%'),
  issued_at    timestamptz  NOT NULL DEFAULT now()
);

COMMENT ON TABLE app_private.agent_credentials IS
  'One-time agent secrets, hashed. There is no retrieval path and no plaintext '
  'column: a secret shown once and lost is rotated, not recovered, and the '
  'absence of a way to read one back is a tested property rather than an '
  'omission.';

-- ---------------------------------------------------------------------------
-- The claim contract, as the database holds it
-- ---------------------------------------------------------------------------
--
-- One row, forever, by the same construction `project_identity` uses: a primary
-- key on a constant rather than a trigger, because a trigger can be disabled by
-- anyone who can ALTER the table.
--
-- `required_claims` is the list migration 0012's hook will check a token
-- against. It is written here as a literal and tied to
-- `agentic_postgres.jwt_claims.REQUIRED_CLAIMS` by a contract test that renders
-- `sql_required_claims()` and compares the two -- so the module stays the one
-- authority for the shape and this row cannot drift from it silently. The
-- alternative, a manifest placeholder, would put the claim list in the deployed
-- document, where it is not a per-project value and does not belong.
CREATE TABLE app_private.auth_contract_state (
  singleton        boolean   PRIMARY KEY DEFAULT true CHECK (singleton),
  required_claims  text[]    NOT NULL
                     CHECK (app_private.is_scope_set(required_claims))
                     CHECK (array_length(required_claims, 1) IS NOT NULL),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_private.auth_contract_state (required_claims) VALUES (
  ARRAY['aud', 'authz_version', 'credential_version', 'exp', 'iat', 'iss',
        'jti', 'nbf', 'role', 'scope', 'sub', 'token_use']::text[]
);

COMMENT ON TABLE app_private.auth_contract_state IS
  'The claim contract as the database holds it (ADR 0078). Sorted, because '
  'is_scope_set requires it -- the wire order lives in jwt_claims and this is '
  'the set, not the sequence. A contract test compares this literal against '
  'jwt_claims.sql_required_claims() so the two cannot drift.';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- `auth_service` gets schema USAGE and nothing else. No table grant, no
-- sequence grant, no function grant beyond what a later migration adds
-- deliberately: the service reaches this data through SECURITY DEFINER
-- functions that arrive in the same commit as the code that calls them, which
-- is Run 8's. A grant issued now would be a grant nobody can audit against a
-- caller that does not exist.
GRANT USAGE ON SCHEMA app_private TO {{auth_service}};

-- Restated for the new grantee, as 0009 restated them for the documentation
-- role: a role added after 0008 closed these would otherwise inherit whatever a
-- later CREATE TABLE in this schema grants.
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app_private
  REVOKE ALL ON TABLES FROM {{auth_service}};
ALTER DEFAULT PRIVILEGES FOR ROLE {{object_owner}} IN SCHEMA app_private
  REVOKE ALL ON SEQUENCES FROM {{auth_service}};

-- The blanket revoke every migration in this schema ends with. It covers the
-- five tables created above, which the ALTER DEFAULT PRIVILEGES statements
-- deliberately do not: those apply to objects created *after* them.
REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

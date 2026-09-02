-- migrate:up
-- The session plane's state: refresh families and the single-use tokens in them.
--
-- **This is new construction, not an extension** (D812). Across the twenty-two
-- migrations before it there is no refresh route, no session table and no
-- refresh column; the string `refresh_token` appears in this repository in
-- exactly one place, `config.SENSITIVE_KEY_DENYLIST`, where it is listed as a
-- value that must never be logged. The only thing this deployment knew about
-- refresh tokens was that they had to be redacted.
--
-- **Why it exists is a credential-handling defect, not a convenience one**
-- (D813). `claims.MAX_TTL_SECONDS` is 900 and the auth service issues at the
-- ceiling, plus 30 s of skew -- so a token is live for at most 930 seconds and
-- nothing renews it. A client that stays logged in for an hour therefore has to
-- keep the *password* and replay it four times. The short TTL is correct; what
-- was missing is the half that makes it affordable to keep.
--
-- ADR 0171 holds the decisions. The two that were MEASURED against the pinned
-- image before this file was written are restated where they take effect below,
-- because a decision recorded only in a document is a decision the next reader
-- of this table does not have.
--
-- ---------------------------------------------------------------------------
-- What this migration deliberately does NOT do
-- ---------------------------------------------------------------------------
--
-- No function, and no grant to {{auth_service}} beyond the schema USAGE it has
-- held since 0011. That file set the terms for its own successors:
--
--     "the service reaches this data through SECURITY DEFINER functions that
--      arrive in the same commit as the code that calls them. A grant issued
--      now would be a grant nobody can audit against a caller that does not
--      exist."
--
-- The endpoints are Run 3, so the functions and their grants are Run 3 (D830).
-- Until then these tables are reachable by their owner alone.

SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- Why a family is revoked, as a type rather than free text
-- ---------------------------------------------------------------------------
--
-- An enum for `api.task_status`'s reason (0007) and `user_status`'s (0011): a
-- reason nobody can spell wrong is a reason an operator can filter on. The
-- values are the four ways a session can end, and `reuse_detected` is the one
-- that is an ALARM rather than a lifecycle event -- an operator reading this
-- column is reading the difference between "somebody logged out" and "a token
-- was presented twice".
CREATE TYPE app_private.refresh_revocation AS ENUM (
  'logged_out',
  'reuse_detected',
  'credential_changed',
  'administrative'
);

-- ---------------------------------------------------------------------------
-- The family, which IS the session
-- ---------------------------------------------------------------------------
--
-- One object and not two (ADR 0171). A family is created at login, extended by
-- each rotation, and ended by logout, by a credential change, or by a replay --
-- which is exactly what a person means by a session, so the listing and
-- termination surface Run 3 builds is a family surface rather than a second
-- table keyed beside this one.
--
-- **No caller-supplied string is stored** (D829): no user agent, no address, no
-- device label. A session is identified by its id, when it began and when it was
-- last used. That costs a listing the ability to say "Firefox, in Berlin", and
-- it keeps the rule the agent plane already keeps -- a caller value is not
-- recorded -- which a display string would break however harmless it looks.
CREATE TABLE app_private.refresh_families (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid        NOT NULL
                   REFERENCES app_private.users (id) ON DELETE CASCADE,
  created_at     timestamptz NOT NULL DEFAULT now(),
  last_used_at   timestamptz NOT NULL DEFAULT now(),
  revoked_at     timestamptz,
  revoked_reason app_private.refresh_revocation,

  -- The two revocation columns move together or not at all. A reason with no
  -- moment does not say when the session ended, and a moment with no reason
  -- loses the distinction between a logout and an alarm -- which is the whole
  -- value of the column beside it.
  CONSTRAINT refresh_families_revocation_is_complete
    CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL))
);

CREATE INDEX refresh_families_user_live_idx
  ON app_private.refresh_families (user_id) WHERE revoked_at IS NULL;

COMMENT ON TABLE app_private.refresh_families IS
  'A session. A chain of single-use refresh tokens sharing an ancestor, created '
  'at login and ended by logout, a credential change or a replay (ADR 0171). It '
  'carries no caller-supplied string -- no user agent, no address -- so a '
  'session is identified by its id and its times, and the listing surface '
  'cannot name a device.';

COMMENT ON COLUMN app_private.refresh_families.revoked_reason IS
  'Why the session ended. `reuse_detected` is an ALARM and the other three are '
  'lifecycle: it records that a consumed token was presented again, which means '
  'the chain leaked. An operator filtering this column is separating "somebody '
  'logged out" from "somebody replayed a token".';

-- ---------------------------------------------------------------------------
-- The tokens, single-use, one live per family
-- ---------------------------------------------------------------------------
--
-- **The stored value is a deterministic SHA-256, and that differs from both of
-- its neighbours in this schema on purpose** (D828). `user_credentials` and
-- `agent_credentials` both CHECK for `$argon2id$`, and this one does not,
-- because a salted hash cannot be looked up: an agent presents `agent_id` AND a
-- secret, and a person presents a username AND a password, so those rows are
-- found by an identifier and the hash is only verified. **A refresh token
-- presents only itself.** The row has to be found BY the stored value, which a
-- per-row salt turns into a full scan with a KDF per row.
--
-- The token is 32 bytes of `os.urandom`, so the property a KDF buys -- making a
-- guessable secret expensive to guess -- is not one this value needs. What it
-- needs is that the database never holds the presented value, and a digest gives
-- that. The CHECK states the shape so a row holding a raw token, an argon2
-- string or an empty value is refused at write time rather than discovered when
-- a lookup quietly matches nothing.
CREATE TABLE app_private.refresh_tokens (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id   uuid        NOT NULL
                REFERENCES app_private.refresh_families (id) ON DELETE CASCADE,

  -- The chain, and the reason a family is not just a bag of tokens. ON DELETE
  -- SET NULL rather than CASCADE: deleting an ancestor must not silently delete
  -- the descendants that are the record of what happened after it.
  parent_id   uuid        REFERENCES app_private.refresh_tokens (id) ON DELETE SET NULL,

  token_hash  text        NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  issued_at   timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  consumed_at timestamptz,

  CONSTRAINT refresh_tokens_expiry_follows_issue CHECK (expires_at > issued_at)
);

-- One hash, one token. Without this a digest collision -- or, far more likely, a
-- bug that reused a value -- would make two rows answer to one presented token
-- and the reuse alarm would fire against whichever the planner reached first.
CREATE UNIQUE INDEX refresh_tokens_hash_key
  ON app_private.refresh_tokens (token_hash);

-- ---------------------------------------------------------------------------
-- The invariant reuse detection rests on, and it was MEASURED (D827)
-- ---------------------------------------------------------------------------
--
-- At most one unconsumed token per family. **If two could be live at once, a
-- thief and the legitimate client would each hold a valid token and neither
-- presentation would look like a replay** -- there would be nothing to detect,
-- and every guarantee above this line would be a comment.
--
-- An index rather than a rule in the service, so it holds for every writer
-- including one nobody has written yet.
--
-- It also makes the rotation ORDER a catalog constraint, which is the part that
-- was measured against the pinned image rather than assumed. In one transaction:
--
--   consume-then-insert  -> accepted
--   insert-then-consume  -> REFUSED, 23505
--
-- So a rotation that issued the successor before retiring its parent cannot be
-- written by accident. It fails at the database in every environment, rather
-- than passing review and being correct only where somebody remembered.
CREATE UNIQUE INDEX refresh_tokens_one_live_per_family
  ON app_private.refresh_tokens (family_id) WHERE consumed_at IS NULL;

COMMENT ON TABLE app_private.refresh_tokens IS
  'Single-use refresh tokens, stored as a hex SHA-256 because the client '
  'presents the token alone and a salted hash cannot be looked up (ADR 0171). '
  'At most one is live per family, which is the invariant reuse detection rests '
  'on: two live tokens would mean a thief and the owner each held a valid one '
  'and neither replay was visible.';

COMMENT ON COLUMN app_private.refresh_tokens.consumed_at IS
  'When this token was exchanged. Terminal and never cleared. Under the '
  'deployment''s `read committed`, two concurrent presentations resolve to one '
  'winner and an EMPTY RESULT for the loser -- measured, with the loser '
  'blocking until the winner commits. Under `repeatable read` the same '
  'statement raises 40001 instead, which means the same thing and looks like a '
  'transient error a client should retry: retrying a replay presents it again. '
  'The plane is specified against read committed (ADR 0171).';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- None issued. See the header: the functions the auth service will call arrive
-- with the code that calls them, in Run 3. This is the blanket revoke every
-- migration in this schema ends with, and it covers the two tables above.
REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

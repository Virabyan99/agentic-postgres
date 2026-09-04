-- migrate:up
-- A caller-supplied idempotency key, claimed in the write's own transaction
-- (ADR 0181).
--
-- ---------------------------------------------------------------------------
-- Why the claim is HERE and not in a call of its own
-- ---------------------------------------------------------------------------
--
-- This is a different argument from 0028's and the difference matters. The
-- quota went into `agent_audit_begin` because a separate request would COST a
-- fifth round trip on a path nobody has timed (D904). The key goes into the
-- write function because a separate request would be WRONG: two calls in two
-- transactions can both pass a check and both write. Atomicity is the entire
-- guarantee, and it is only available where the write is. That argument holds
-- at any price.
--
-- ---------------------------------------------------------------------------
-- What was measured, and the arm that decided this file's shape
-- ---------------------------------------------------------------------------
--
-- Two overlapping claims of one key at `read committed`, ADR 0171's pattern:
--
--   loser's INSERT ... ON CONFLICT DO NOTHING RETURNING   BLOCKED 576 ms (the
--                                                         winner held 750 ms,
--                                                         the loser started
--                                                         150 ms in) and
--                                                         RETURNING gave NO ROW
--   the loser's next SELECT, same transaction             SEES the winner's row
--   final table                                           ONE row, the winner's
--   CONTROL, the same pair with no unique constraint      no block (1 ms), TWO
--                                                         rows
--
-- So the loser waits, learns it lost by getting nothing back, and can read the
-- winner's outcome in its own transaction. The control shows the rig can tell
-- blocking from not-blocking.
--
-- **The ENUM arm is what decided this file rather than two files.** dbmate wraps
-- a migration in one transaction, and:
--
--   ALTER TYPE ... ADD VALUE then INSERT using it, one transaction
--       ERROR: unsafe use of new value "replayed" -- and the whole transaction
--       rolls back, so the member is not added either
--   ADD VALUE + CREATE FUNCTION ... LANGUAGE plpgsql whose body names it
--       COMMITS. plpgsql does not resolve the literal at creation.
--   CONTROL, the same with LANGUAGE sql, which IS fully parsed at creation
--       ERROR: unsafe use of new value "reviewed", rolled back
--
-- Every function below is plpgsql, so the ADD VALUE and the bodies that name
-- `replayed` commit together. **And the control that makes that answer
-- trustworthy rather than lucky**: a plpgsql body naming a member that does NOT
-- EXIST is created without complaint, where the SQL-language form is refused.
-- Creation-time validation proves nothing here; the path is exercised by a test
-- that runs it.
--
-- `sha256(bytea)` is a built-in on the locked image -- the fingerprint needs no
-- extension. The control, pgcrypto's `digest()`, does not exist.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- A replay is its own outcome, and not `served` with a zero row count
-- ---------------------------------------------------------------------------
--
-- The arithmetic would encode the same fact, and D495 is why it does not: one
-- value carrying two meanings is the defect this repository produces most. "A
-- write that served nothing" is not something an operator should have to infer
-- from a coincidence, and `served, row_count 0` is currently impossible for a
-- write only by accident -- `invoke_write` refuses any response that is not
-- exactly one row.
ALTER TYPE app_private.agent_audit_outcome ADD VALUE 'replayed';

-- ---------------------------------------------------------------------------
-- The dedupe state
-- ---------------------------------------------------------------------------
--
-- **`row_id` is NOT NULL**, and that is a property of the order rather than an
-- aspiration. Both writes know their row's id BEFORE they write it -- a note's
-- is minted here, a task's is the caller's own argument -- so the claim carries
-- it from the start and there is never a window in which a committed claim
-- points at nothing. The alternative, claiming with NULL and updating after,
-- would put a state in the table that only a crash could leave behind, which is
-- the kind of state nobody tests and everybody eventually reads.
--
-- `arguments_sha256` and not the arguments. A hash is not a caller value, so
-- the lock's `audit.redact` remains the single authority over caller values
-- (D479) rather than gaining a second store with different needs.
--
-- **NO foreign key on `agent_id`, and this is the opposite of 0028's choice.**
-- The first draft had `REFERENCES app_private.agents (id) ON DELETE CASCADE`, by
-- analogy with the quota table, and a live cluster refused the first agent write
-- that reached it. Two things are wrong with it and only the second is serious:
--
--   * it makes an agent write FAIL for a reason unrelated to the write -- a
--     referential check on a row the write does not own -- which is precisely
--     why `agent_audit.agent_id` has carried no foreign key since 0019;
--   * the CASCADE would delete a live agent's dedupe state with the agent, so a
--     key still in flight would be **re-executable**. Cascading away the record
--     that prevents a double write is a correctness hazard, not a tidiness one.
--
-- The distinction against 0028 is real rather than an inconsistency: a quota is
-- a LIVE BOUND and is meaningless without its agent, so cascading is right
-- there. A claim is a record that a call happened, and it has to outlive the
-- agent exactly as the audit row does.
CREATE TABLE app_private.agent_idempotency (
  agent_id         uuid        NOT NULL,
  idempotency_key  text        NOT NULL CHECK (idempotency_key <> ''),
  tool             text        NOT NULL CHECK (tool <> ''),
  arguments_sha256 text        NOT NULL CHECK (arguments_sha256 ~ '^[0-9a-f]{64}$'),
  row_id           uuid        NOT NULL,
  replay_count     integer     NOT NULL DEFAULT 0 CHECK (replay_count >= 0),
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (agent_id, idempotency_key)
);

COMMENT ON TABLE app_private.agent_idempotency IS
  'One claim per (agent, key): which tool, a hash of the arguments, and the id '
  'of the row the call produced (ADR 0181). The OUTCOME is not stored -- a '
  'replay re-reads the row, which stores no caller value and reports the row''s '
  'current state rather than a snapshot claiming to be current.';

-- ---------------------------------------------------------------------------
-- The key, read from the header exactly as 0022 reads the request id
-- ---------------------------------------------------------------------------
--
-- Measured in Session 11 through PostgREST at the pinned digest, through a role
-- switch, behind the `db-pre-request` hook, inside a SECURITY DEFINER function
-- with `SET search_path = pg_catalog, pg_temp` -- this function's exact
-- situation and not an approximation of it (D632). Lowercase key; the
-- two-argument `current_setting` because these functions are reachable from
-- psql, where the GUC does not exist and the one-argument form RAISES.
--
-- **The guard is INVERTED from `agent_request_id()`'s, deliberately.** That one
-- returns NULL for anything malformed and lets the write proceed, because a
-- correlation field must never destroy the operation it annotates (D633). This
-- one RAISES, because ignoring a malformed key performs the write WITHOUT the
-- guarantee the caller asked for -- a silent downgrade from at-most-once to
-- at-least-once, which is the failure this migration exists to prevent. Same
-- mechanism, opposite failure mode, and the reason is that one field describes
-- the write while the other governs whether it happens.
CREATE FUNCTION app_private.agent_idempotency_key()
  RETURNS text
  LANGUAGE plpgsql
  STABLE
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  raw text;
  candidate text;
BEGIN
  raw := current_setting('request.headers', true);
  IF raw IS NULL THEN
    RETURN NULL;
  END IF;

  candidate := (raw::jsonb) ->> 'idempotency-key';
  IF candidate IS NULL THEN
    RETURN NULL;
  END IF;

  -- Bounded and printable. A key is an opaque token a caller minted, so the
  -- shape test is about what may be STORED and later read by an operator, not
  -- about what the value means: no control characters, and a length a column
  -- and a console can both carry.
  IF candidate !~ '^[\x21-\x7e]{8,255}$' THEN
    RAISE EXCEPTION 'AP412: the idempotency key must be 8 to 255 printable ASCII characters'
      USING ERRCODE = 'PT412';
  END IF;

  RETURN candidate;
END $fn$;

COMMENT ON FUNCTION app_private.agent_idempotency_key() IS
  'The Idempotency-Key header for this transaction, or NULL when absent. '
  'RAISES PT412 on a malformed value rather than returning NULL: unlike a '
  'request id, ignoring this field would perform the write without the '
  'guarantee the caller asked for (ADR 0181, and D633 inverted).';

REVOKE ALL ON FUNCTION app_private.agent_idempotency_key() FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- The claim
-- ---------------------------------------------------------------------------
--
-- Returns NULL when THIS call claimed the key -- proceed and do the work -- and
-- the prior row's id when it is a replay. One statement decides it, which is
-- what makes two concurrent identical calls safe: the loser blocks on the
-- unique index and its RETURNING is empty.
--
-- A key presented with a different tool or a different fingerprint is refused.
-- `PT412` and not `PT409`: 409 is already the compare-and-swap conflict, one
-- errcode cannot carry two sentences, and "re-read and retry" is exactly the
-- wrong advice for a key bound to different arguments -- the right move is a new
-- key. `PT412` was measured to cross HTTP as 412 with its code in the body, by
-- an arm added to the proof that already measured the other four.
CREATE FUNCTION app_private.agent_idempotency_claim(
  p_agent       uuid,
  p_key         text,
  p_tool        text,
  p_fingerprint text,
  p_row_id      uuid
)
  RETURNS uuid
  LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  claimed uuid;
  prior   app_private.agent_idempotency;
BEGIN
  INSERT INTO app_private.agent_idempotency
    (agent_id, idempotency_key, tool, arguments_sha256, row_id)
  VALUES
    (p_agent, p_key, p_tool, p_fingerprint, p_row_id)
  ON CONFLICT (agent_id, idempotency_key) DO NOTHING
  RETURNING row_id INTO claimed;

  IF claimed IS NOT NULL THEN
    RETURN NULL;
  END IF;

  -- The winner has committed by the time this runs -- the INSERT above blocked
  -- on its uncommitted index entry -- so this SELECT sees a settled row.
  SELECT * INTO prior
    FROM app_private.agent_idempotency
   WHERE agent_id = p_agent AND idempotency_key = p_key;

  IF prior.tool <> p_tool OR prior.arguments_sha256 <> p_fingerprint THEN
    RAISE EXCEPTION 'AP412: this idempotency key was used for a different call'
      USING ERRCODE = 'PT412';
  END IF;

  UPDATE app_private.agent_idempotency
     SET replay_count = replay_count + 1
   WHERE agent_id = p_agent AND idempotency_key = p_key;

  RETURN prior.row_id;
END $fn$;

COMMENT ON FUNCTION app_private.agent_idempotency_claim(uuid, text, text, text, uuid) IS
  'Claims one key for one call. NULL means this call claimed it and should do '
  'the work; a uuid means the key was already spent and names the row to '
  're-read. Raises PT412 when the key is bound to a different call (ADR 0181).';

REVOKE ALL ON FUNCTION
  app_private.agent_idempotency_claim(uuid, text, text, text, uuid) FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Both write RPCs, replaced
-- ---------------------------------------------------------------------------
--
-- CREATE OR REPLACE, signatures unchanged -- so nothing in `api` is created,
-- dropped or re-signatured, no grant moves, and the HUMAN REST SURFACE IS
-- UNTOUCHED. 0022 did exactly this for the same reason.
--
-- **A human caller is unaffected**, which is 0019's own property: the claim is
-- taken only when `app.agent_id` is set, and the hook sets that only on the
-- agent branch. A human sending the header gets no idempotency. That is a
-- stated limitation and not an oversight -- extending it would change the human
-- REST contract, which this run is not for.
--
-- **An agent write REQUIRES a key**, refused here rather than only in the
-- runtime. 0019 built these functions so that a caller skipping the agent plane
-- and posting to `/rpc/create_note` directly still leaves an audit row; the same
-- reasoning applies to the guarantee, and a check that lives only in the
-- runtime is a check an agent can route around.
--
-- The fingerprint is `jsonb` and not `json`: jsonb normalises key order, so the
-- same arguments hash the same however they arrived.
CREATE OR REPLACE FUNCTION api.create_note(p_title text, p_content text DEFAULT '')
  RETURNS api.notes
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller uuid := app.current_user_id();
  acting_agent uuid := nullif(current_setting('app.agent_id', true), '')::uuid;
  idem_key text;
  replayed_id uuid;
  new_id uuid := gen_random_uuid();
  created api.notes;
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: no request identity for this transaction'
      USING ERRCODE = 'PT401';
  END IF;

  IF acting_agent IS NOT NULL THEN
    idem_key := app_private.agent_idempotency_key();
    IF idem_key IS NULL THEN
      RAISE EXCEPTION 'AP412: an agent write requires an Idempotency-Key header'
        USING ERRCODE = 'PT412';
    END IF;

    replayed_id := app_private.agent_idempotency_claim(
      acting_agent, idem_key, 'create_note',
      encode(sha256(convert_to(
        jsonb_build_object('p_title', p_title, 'p_content', p_content)::text, 'UTF8')), 'hex'),
      new_id);

    IF replayed_id IS NOT NULL THEN
      SELECT n.id, n.owner_id, n.title, n.content, n.created_at, n.updated_at
        INTO created
        FROM app.notes n
       WHERE n.id = replayed_id AND n.owner_id = caller;

      IF NOT FOUND THEN
        -- The claim names a row this caller cannot see. Not reachable by any
        -- path the product takes, and loud rather than quiet because the only
        -- ways here are a deleted row or a key crossing an ownership boundary.
        RAISE EXCEPTION 'AP404: no such note' USING ERRCODE = 'PT404';
      END IF;

      INSERT INTO app_private.agent_audit
        (source, agent_id, owner_id, tool, request_id, outcome, row_count, completed_at)
      VALUES
        ('database', acting_agent, caller, 'create_note',
         app_private.agent_request_id(), 'replayed', 0, now());

      RETURN created;
    END IF;
  END IF;

  INSERT INTO app.notes (id, owner_id, title, content)
  VALUES (new_id, caller, p_title, p_content)
  RETURNING id, owner_id, title, content, created_at, updated_at INTO created;

  IF acting_agent IS NOT NULL THEN
    INSERT INTO app_private.agent_audit
      (source, agent_id, owner_id, tool, request_id, outcome, row_count, completed_at)
    VALUES
      ('database', acting_agent, caller, 'create_note',
       app_private.agent_request_id(), 'committed', 1, now());
  END IF;

  RETURN created;
END $fn$;

CREATE OR REPLACE FUNCTION api.update_task_status(
  p_task_id uuid,
  p_expected_status api.task_status,
  p_new_status api.task_status
)
  RETURNS api.tasks
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller uuid := app.current_user_id();
  acting_agent uuid := nullif(current_setting('app.agent_id', true), '')::uuid;
  idem_key text;
  replayed_id uuid;
  observed api.task_status;
  updated api.tasks;
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: no request identity for this transaction'
      USING ERRCODE = 'PT401';
  END IF;

  IF p_new_status = p_expected_status THEN
    RAISE EXCEPTION 'AP422: a status transition must change the status'
      USING ERRCODE = 'PT422';
  END IF;

  -- **The claim comes before the compare-and-swap**, and the order is the
  -- point. A replayed transition would otherwise fail its own CAS -- the status
  -- it expected is the status it already set -- and the caller would read
  -- `PT409` for a write that had in fact succeeded. That is the exact confusion
  -- an idempotency key is supplied to remove.
  IF acting_agent IS NOT NULL THEN
    idem_key := app_private.agent_idempotency_key();
    IF idem_key IS NULL THEN
      RAISE EXCEPTION 'AP412: an agent write requires an Idempotency-Key header'
        USING ERRCODE = 'PT412';
    END IF;

    replayed_id := app_private.agent_idempotency_claim(
      acting_agent, idem_key, 'update_task_status',
      encode(sha256(convert_to(jsonb_build_object(
        'p_task_id', p_task_id,
        'p_expected_status', p_expected_status::text,
        'p_new_status', p_new_status::text)::text, 'UTF8')), 'hex'),
      p_task_id);

    IF replayed_id IS NOT NULL THEN
      SELECT t.id, t.owner_id, t.note_id, t.title, t.description, t.status,
             t.created_at, t.updated_at
        INTO updated
        FROM app.tasks t
       WHERE t.id = replayed_id AND t.owner_id = caller;

      IF NOT FOUND THEN
        RAISE EXCEPTION 'AP404: no such task' USING ERRCODE = 'PT404';
      END IF;

      INSERT INTO app_private.agent_audit
        (source, agent_id, owner_id, tool, request_id, outcome, row_count, completed_at)
      VALUES
        ('database', acting_agent, caller, 'update_task_status',
         app_private.agent_request_id(), 'replayed', 0, now());

      RETURN updated;
    END IF;
  END IF;

  -- FOR UPDATE, so a concurrent caller blocks here rather than reading the same
  -- expected status and both proceeding. Unchanged from 0019.
  SELECT t.status INTO observed
    FROM app.tasks t
   WHERE t.id = p_task_id AND t.owner_id = caller
     FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no such task' USING ERRCODE = 'PT404';
  END IF;

  IF observed <> p_expected_status THEN
    RAISE EXCEPTION 'AP409: the task is not in the expected status'
      USING ERRCODE = 'PT409';
  END IF;

  UPDATE app.tasks
     SET status = p_new_status, updated_at = now()
   WHERE id = p_task_id AND owner_id = caller
  RETURNING id, owner_id, note_id, title, description, status, created_at, updated_at
       INTO updated;

  IF acting_agent IS NOT NULL THEN
    INSERT INTO app_private.agent_audit
      (source, agent_id, owner_id, tool, request_id, outcome, row_count, completed_at)
    VALUES
      ('database', acting_agent, caller, 'update_task_status',
       app_private.agent_request_id(), 'committed', 1, now());
  END IF;

  RETURN updated;
END $fn$;

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- Nothing in `api` changed signature, so no grant is re-issued. **No grant of
-- any kind on `app_private.agent_idempotency`**: no request role reads it,
-- writes it or knows it exists, and the only path in is the definer function
-- above. That is 0019's rule for `agent_audit` and 0028's for `agent_quota`.
REVOKE ALL ON app_private.agent_idempotency FROM PUBLIC;

RESET ROLE;

-- Two functions in `api` were REPLACED with identical signatures, so nothing
-- PostgREST caches about them moved -- but 0021 and 0022 both issued this NOTIFY
-- as a precaution on the same open question, and the asymmetry is unchanged: one
-- reload of a cache that loads in about 3 ms, against a body live in PostgreSQL
-- and stale over HTTP.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

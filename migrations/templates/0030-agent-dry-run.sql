-- migrate:up
-- A dry-run attempts the write and rolls it back (ADR 0182).
--
-- ---------------------------------------------------------------------------
-- Whose validation, which is the question the run's plan does not answer
-- ---------------------------------------------------------------------------
--
-- A dry-run that skips the write skips every CHECK on `app.notes`, every row
-- policy, and `update_task_status`'s own compare-and-swap -- so it would report
-- success for a title the table refuses, which is the single thing a caller
-- most wants a dry-run to tell them. That is not a dry-run; it is a spell-check
-- of the request.
--
-- ---------------------------------------------------------------------------
-- What was measured, and it is the first time D489 could be worked WITH
-- ---------------------------------------------------------------------------
--
--   a plpgsql BEGIN/EXCEPTION block that INSERTs then raises a sentinel
--       the INSERT is ROLLED BACK (notes rows = 0) and the surrounding
--       transaction still COMMITS its audit row (audit rows = 1, dry_run)
--   the RETURNING variable after that rollback
--       SURVIVES, complete, with the values the write would have stored
--   CONTROL, the same function without the sentinel
--       writes for real: one note, a real id
--   a genuine CHECK violation inside the block ('' and 201 characters)
--       PROPAGATES -- "violates check constraint notes_title_check" -- and is
--       not swallowed by the handler
--   after those two failures
--       no note AND NO AUDIT ROW: the aborting transaction took it, D489 exactly
--   the dry-run inside an explicit transaction that then does more work
--       the transaction is intact and commits
--
-- So a dry-run can attempt the REAL write, let every constraint the product owns
-- fire, roll it back, and still keep its own record. D489 denied that to both of
-- this session's earlier runs -- the quota refusal (ADR 0180) and the
-- idempotency conflict (ADR 0181) each had to avoid `RAISE` to keep an audit
-- row. Here the rollback is scoped to a SUBTRANSACTION rather than the whole
-- one, which is the difference.
--
-- **The re-raise is the load-bearing half.** `WHEN OTHERS` swallowing everything
-- would turn a CHECK violation into a successful dry-run, which is the exact
-- inversion of what the caller asked for. The handler matches the sentinel and
-- nothing else.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- Two enums gain a member each
-- ---------------------------------------------------------------------------
--
-- `dry_run` on the outcome, because a dry-run recorded as a write would make
-- every write count in the audit table a lie. `served` with a zero row count
-- would encode the same fact and is refused for D495's reason, exactly as
-- `replayed` was one run earlier.
--
-- `approval_required` on the denial reason, derived from a real refusal site as
-- ADR 0178's eight were. The refusal itself lives in the runtime -- a tool whose
-- contract declares `requires_approval` is refused before anything is dialled --
-- and this is the vocabulary its audit row is written in.
--
-- Both are `ALTER TYPE ... ADD VALUE` in a migration whose plpgsql bodies name
-- the new value, which Run 6 measured commits in ONE transaction where a
-- `LANGUAGE sql` body does not.
ALTER TYPE app_private.agent_audit_outcome ADD VALUE 'dry_run';
ALTER TYPE app_private.agent_denial_reason ADD VALUE 'approval_required';

-- ---------------------------------------------------------------------------
-- The header, read exactly as 0029 reads the idempotency key
-- ---------------------------------------------------------------------------
--
-- A boolean, so the parse is narrow on purpose: the header is present and reads
-- `true`, or it is not a dry-run. Anything else RAISES rather than being read as
-- false -- a caller who asked for a rehearsal and got a live write because their
-- header said `TRUE ` or `1` would have no way to know, and this is the one
-- misreading that costs a row.
CREATE FUNCTION app_private.agent_dry_run()
  RETURNS boolean
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
    RETURN false;
  END IF;

  candidate := (raw::jsonb) ->> 'dry-run';
  IF candidate IS NULL THEN
    RETURN false;
  END IF;

  IF candidate NOT IN ('true', 'false') THEN
    RAISE EXCEPTION 'AP412: the dry-run header is the literal true or false'
      USING ERRCODE = 'PT412';
  END IF;

  RETURN candidate = 'true';
END $fn$;

COMMENT ON FUNCTION app_private.agent_dry_run() IS
  'Whether this request is a rehearsal (ADR 0182). Absent is false; anything '
  'that is not the literal true or false RAISES, because a caller who asked '
  'for a rehearsal and got a live write has no way to find out.';

REVOKE ALL ON FUNCTION app_private.agent_dry_run() FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Both write RPCs, replaced
-- ---------------------------------------------------------------------------
--
-- CREATE OR REPLACE, signatures unchanged for the third time in this session --
-- so nothing in `api` is created, dropped or re-signatured, no grant moves, and
-- the human REST surface is untouched.
--
-- **The dry-run branch runs BEFORE the idempotency claim** (ADR 0182). A
-- dry-run changes nothing, and dedupe state is something: burning a key on a
-- rehearsal would make the real call that follows a replay of a write that never
-- happened. It still REQUIRES a key, for 0029's reasons unchanged -- the rule
-- stays "every agent write carries a key" with no exception a caller has to
-- remember, and the forwarded-header rosters stay two exact sets.
--
-- **A human caller may rehearse too**, because the block is not inside the
-- agent branch. A human sending no header is unaffected, which is 0019's own
-- property and the reason nothing about the REST surface changes.
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

  IF app_private.agent_dry_run() THEN
    IF acting_agent IS NOT NULL AND app_private.agent_idempotency_key() IS NULL THEN
      RAISE EXCEPTION 'AP412: an agent write requires an Idempotency-Key header'
        USING ERRCODE = 'PT412';
    END IF;

    BEGIN
      INSERT INTO app.notes (id, owner_id, title, content)
      VALUES (new_id, caller, p_title, p_content)
      RETURNING id, owner_id, title, content, created_at, updated_at INTO created;

      RAISE EXCEPTION 'APDRYRUN' USING ERRCODE = 'P0001';
    EXCEPTION WHEN sqlstate 'P0001' THEN
      -- Only OUR sentinel. Anything else -- a CHECK violation, a policy, a
      -- trigger -- is re-raised so the caller reads the refusal the real call
      -- would have produced. Swallowing it would turn a constraint failure into
      -- a successful rehearsal.
      IF sqlerrm <> 'APDRYRUN' THEN
        RAISE;
      END IF;
    END;

    -- **The id is nulled.** It belongs to a row that does not exist and never
    -- will, and publishing it is D600's defect with a fresh coat: a plausible
    -- uuid nothing holds, in the field a client is most likely to keep. Nothing
    -- was created, so nothing has an identity.
    created.id := NULL;

    IF acting_agent IS NOT NULL THEN
      INSERT INTO app_private.agent_audit
        (source, agent_id, owner_id, tool, request_id, outcome, row_count, completed_at)
      VALUES
        ('database', acting_agent, caller, 'create_note',
         app_private.agent_request_id(), 'dry_run', 0, now());
    END IF;

    RETURN created;
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

  -- A rehearsal of a transition takes the same `FOR UPDATE` the real one does
  -- and releases it at the rollback. Brief, real, and stated rather than
  -- discovered: a caller rehearsing contends with a caller performing.
  IF app_private.agent_dry_run() THEN
    IF acting_agent IS NOT NULL AND app_private.agent_idempotency_key() IS NULL THEN
      RAISE EXCEPTION 'AP412: an agent write requires an Idempotency-Key header'
        USING ERRCODE = 'PT412';
    END IF;

    BEGIN
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

      RAISE EXCEPTION 'APDRYRUN' USING ERRCODE = 'P0001';
    EXCEPTION WHEN sqlstate 'P0001' THEN
      IF sqlerrm <> 'APDRYRUN' THEN
        RAISE;
      END IF;
    END;

    -- The id is the CALLER'S OWN argument here, not a minted one, so nulling it
    -- would remove a fact the caller already holds rather than withhold one it
    -- does not. The row it names still exists; what did not happen is the
    -- transition, and `row_count` 0 with outcome `dry_run` is what says so.
    IF acting_agent IS NOT NULL THEN
      INSERT INTO app_private.agent_audit
        (source, agent_id, owner_id, tool, request_id, outcome, row_count, completed_at)
      VALUES
        ('database', acting_agent, caller, 'update_task_status',
         app_private.agent_request_id(), 'dry_run', 0, now());
    END IF;

    RETURN updated;
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

RESET ROLE;

-- Two functions in `api` were REPLACED with identical signatures, so nothing
-- PostgREST caches about them moved -- but 0021, 0022 and 0029 all issued this
-- NOTIFY on the same open question, and the asymmetry is unchanged.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

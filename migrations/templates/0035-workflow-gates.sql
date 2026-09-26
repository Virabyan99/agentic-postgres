-- migrate:up
-- Gates, compensation, the attempt history, provenance and the audit reader
-- (ADR 0230, ADR 0231, ADR 0233, ADR 0234).
--
-- 0034 built durable pending state and left the second principal to this
-- migration. What arrives here is everything the database holds for it: a
-- human's decision on a parked step (`workflow_approval`), every attempt of
-- every step rather than the last one (`workflow_attempt`), the reverse-ordered
-- undo of a failed or cancelled run (the `compensating` status and the rows
-- `workflow_begin_compensation` appends), one document that answers *what did
-- this run do and who let it* (`workflow_provenance`), and D1248's filters on
-- the audit's one reader.
--
-- ---------------------------------------------------------------------------
-- What this migration does NOT do
-- ---------------------------------------------------------------------------
--
-- **No 0034 signature moves.** Five of its functions are replaced in place --
-- the claim, the finish, the park, the agent's status read and the counts --
-- with the SAME argument and result types, so every grant 0034 issued stands
-- and every caller keeps working. The one function whose arity moves is the
-- audit reader, which is 0032's and is dropped and re-created below for the
-- reason 0032 itself gives.
--
-- **Approval is decided by the plane, not here** (ADR 0230). Nothing in this
-- file knows which capability needs a human. The plane refuses a gated write
-- with `approval_required`; the worker records that refusal here and parks;
-- a human's decision is recorded here; and the worker's next mint reads the
-- decision back through `workflow_approval_for_token`. The lock stays the one
-- authority on WHAT needs approval.
--
-- **Approval is a control on the governed path, not in the database** (ADR
-- 0231, D1721). A project RPC granted to `agent_writer` checks no approval,
-- and rig 33b measured an agent's own token served by PostgREST directly. This
-- file does not claim otherwise and changes no `api` object, so there is no
-- `NOTIFY pgrst`.
--
-- **No RLS, no new errcode.** 0034's posture holds for the two new tables
-- (D1647): no request role holds a privilege, every path is a definer
-- function. The refusals reuse PT403, PT404, PT409 and PT422.
--
-- ---------------------------------------------------------------------------
-- The enum value, and why it is safe in this transaction
-- ---------------------------------------------------------------------------
--
-- `ALTER TYPE ... ADD VALUE 'compensating'` inside dbmate's transaction is
-- usable ONLY inside plpgsql bodies, which resolve literals at execution. Rig
-- 33e measured both halves on 18.4 under the pinned dbmate: the value added and
-- a plpgsql definer function returning and inserting it APPLIED, and ran after
-- commit; the same value named in a column DEFAULT in the same migration was
-- `55P04 unsafe use of new value` and rolled the whole migration back (0029's
-- and 0030's precedent). So the value appears below in function bodies and
-- nowhere else. The new `workflow_approval_status` type is CREATED here, and a
-- type created in the same transaction may use its own values freely.
SET LOCAL ROLE {{object_owner}};

ALTER TYPE app_private.workflow_run_status ADD VALUE 'compensating';

CREATE TYPE app_private.workflow_approval_status AS ENUM
  ('pending', 'approved', 'rejected', 'expired');

-- ---------------------------------------------------------------------------
-- The columns compensation needs
-- ---------------------------------------------------------------------------
--
-- `phase` separates a run's forward steps from the undo rows appended when it
-- fails. `compensates` names the forward POSITION an undo row reverses, which
-- is how the claim finds the compensation block in the compiled body. On the
-- run, `compensation_cause` is where the run goes when its undo is over
-- (`failed` or `cancelled`), and `compensation_outcome` says whether every undo
-- held -- `complete` or `incomplete`, and never *rolled back* (ADR 0233).
ALTER TABLE app_private.workflow_step
  ADD COLUMN phase text NOT NULL DEFAULT 'forward'
    CHECK (phase IN ('forward', 'compensation')),
  ADD COLUMN compensates integer
    CHECK (compensates IS NULL OR compensates >= 1);

ALTER TABLE app_private.workflow_run
  ADD COLUMN compensation_cause app_private.workflow_run_status,
  ADD COLUMN compensation_outcome text
    CHECK (compensation_outcome IS NULL OR compensation_outcome IN ('complete', 'incomplete'));

-- ---------------------------------------------------------------------------
-- The decision
-- ---------------------------------------------------------------------------
--
-- Its own table because the decider is a HUMAN, a `users` row, and every row of
-- `agent_audit` names an agent (ADR 0135: `agent_id uuid NOT NULL`). One table
-- per principal is how this schema already separates `users` from `agents`.
--
-- Append-only in effect: nothing UPDATEs a decided row, because the decide
-- function's predicate is `status = 'pending'` and the expire function's is the
-- same. The CHECK ties a decision to its decider and its time, so a row cannot
-- read `approved` with nobody named.
--
-- `requested_request_id` is the PLANE's id of the refused first call (D1696),
-- which is what joins this row to the `approval_required` audit row.
CREATE TABLE app_private.workflow_approval (
  id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id               uuid        NOT NULL REFERENCES app_private.workflow_run (id),
  step_id              uuid        NOT NULL UNIQUE REFERENCES app_private.workflow_step (id),
  tool                 text        NOT NULL CHECK (tool <> ''),
  capability           text        NOT NULL
    CHECK (capability ~ '^[a-z][a-z0-9_]*@[0-9]+\.[0-9]+\.[0-9]+$'),
  idempotency_key      text        NOT NULL CHECK (idempotency_key ~ '^[\x21-\x7e]{8,255}$'),
  requested_request_id uuid,
  requested_at         timestamptz NOT NULL DEFAULT now(),
  expires_at           timestamptz NOT NULL,
  status               app_private.workflow_approval_status NOT NULL DEFAULT 'pending',
  decided_by           uuid        REFERENCES app_private.users (id),
  decided_at           timestamptz,
  CHECK ((status IN ('approved', 'rejected')) = (decided_by IS NOT NULL AND decided_at IS NOT NULL))
);

CREATE INDEX workflow_approval_status_requested_idx
  ON app_private.workflow_approval (status, requested_at);

COMMENT ON TABLE app_private.workflow_approval IS
  'A human''s decision on one parked step (ADR 0230). Its own table because the '
  'decider is a users row and every agent_audit row names an agent (ADR 0135). '
  'Nothing updates a decided row. requested_request_id is the plane''s id of '
  'the refused first call, which joins this row to its approval_required audit '
  'row. No role holds a privilege on it; every path is a definer function.';

-- ---------------------------------------------------------------------------
-- Every attempt
-- ---------------------------------------------------------------------------
--
-- `workflow_step.request_id` holds the LAST attempt's id and a claim clears it
-- (0034, D1696), so without this table an earlier attempt's audit rows are
-- reachable only by agent and time -- a summary of the other attempts, which is
-- the one thing provenance may not be (ADR 0234). Appended by the replaced
-- finish and park and by `workflow_request_approval`; never updated.
CREATE TABLE app_private.workflow_attempt (
  step_id     uuid        NOT NULL REFERENCES app_private.workflow_step (id),
  attempt     integer     NOT NULL CHECK (attempt >= 1),
  event       text        NOT NULL CHECK (event IN ('finished', 'parked', 'approval_requested')),
  outcome     app_private.workflow_step_outcome,
  request_id  uuid,
  reason      text,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (step_id, attempt, event)
);

COMMENT ON TABLE app_private.workflow_attempt IS
  'One row per attempt event of one step: finished, parked, or '
  'approval_requested (ADR 0234). request_id is the plane''s id for that '
  'attempt''s call, NULL when the attempt made none, and it is what provenance '
  'joins to agent_audit. Append-only; no role holds a privilege on it.';

-- ---------------------------------------------------------------------------
-- The index a keyset page needs
-- ---------------------------------------------------------------------------
--
-- Rig 33d: over 1,000 rows sharing one `started_at`, a page ordered
-- `started_at DESC, id DESC` is a Sort over a Seq Scan without this and an
-- Index Only Scan with it. 0033 declined an index on this table for the PRUNE,
-- which is a Seq Scan by choice over rows older than a horizon; a keyset page
-- is not a prune, and it is read by a person waiting for it.
CREATE INDEX agent_audit_started_id_idx
  ON app_private.agent_audit (started_at DESC, id DESC);

-- ---------------------------------------------------------------------------
-- Beginning compensation, and the grant that is absent
-- ---------------------------------------------------------------------------
--
-- Appends ONE undo row per SUCCEEDED forward step whose compiled element
-- declares a `compensation`, in REVERSE position order, at positions 1000 + n,
-- named `undo-<forward position>` and keyed `wf-<run>-undo-<forward
-- position>` -- a key per (run, undo), never per attempt, for 0034's reason
-- (D1646). Rows are appended when the run fails or is cancelled, not at
-- enqueue: the rows are then a record of what was actually compensated
-- rather than a plan of what might have been (ADR 0233).
--
-- With nothing to compensate the run takes its cause directly, so a run whose
-- failed step was its first reads exactly as it did under 0034.
--
-- A run that is no longer queued or running is returned unchanged: two claims
-- racing to apply one cancel must not append the undo rows twice, and the row
-- lock taken first is what makes the second see `compensating`.
--
-- **Granted to NOBODY.** It is called only from the definer functions below,
-- which run as its owner. A grant to `auth_service` would let the role the HTTP
-- routes run as start an undo of an agent's work on its own say.
CREATE FUNCTION app_private.workflow_begin_compensation(
  p_run   uuid,
  p_cause app_private.workflow_run_status
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  current_status app_private.workflow_run_status;
  appended       integer;
BEGIN
  IF p_cause IS NULL OR p_cause::text NOT IN ('failed', 'cancelled') THEN
    RAISE EXCEPTION 'AP422: a compensation is caused by a failure or a cancel'
      USING ERRCODE = 'PT422';
  END IF;

  SELECT r.status INTO current_status
    FROM app_private.workflow_run r
   WHERE r.id = p_run
     FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no such run' USING ERRCODE = 'PT404';
  END IF;
  IF current_status::text NOT IN ('queued', 'running') THEN
    RETURN current_status::text;
  END IF;

  INSERT INTO app_private.workflow_step
    (run_id, position, name, retry_max, backoff_seconds, timeout_seconds,
     idempotency_key, phase, compensates)
  SELECT s.run_id,
         1000 + (row_number() OVER (ORDER BY s.position DESC))::integer,
         'undo-' || s.position::text,
         coalesce((e.element -> 'compensation' -> 'retry' ->> 'max')::integer, 0),
         coalesce((e.element -> 'compensation' -> 'retry' ->> 'backoff_seconds')::integer, 30),
         coalesce((e.element -> 'compensation' ->> 'timeout_seconds')::integer, s.timeout_seconds),
         'wf-' || s.run_id::text || '-undo-' || s.position::text,
         'compensation',
         s.position
    FROM app_private.workflow_step s
    JOIN app_private.workflow_run r ON r.id = s.run_id
    JOIN app_private.workflow_definition d ON d.id = r.definition_id
    CROSS JOIN LATERAL (SELECT (d.body -> 'steps') -> (s.position - 1) AS element) e
   WHERE s.run_id = p_run
     AND s.phase = 'forward'
     AND s.status = 'succeeded'
     AND jsonb_typeof(e.element -> 'compensation') = 'object';
  GET DIAGNOSTICS appended = ROW_COUNT;

  IF appended > 0 THEN
    UPDATE app_private.workflow_run
       SET status = 'compensating', compensation_cause = p_cause
     WHERE id = p_run;
    RETURN 'compensating';
  END IF;

  UPDATE app_private.workflow_run
     SET status = p_cause, finished_at = pg_catalog.now()
   WHERE id = p_run;
  RETURN p_cause::text;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_begin_compensation(
  uuid, app_private.workflow_run_status) IS
  'Appends one undo row per succeeded forward step that declares a compensation, '
  'in reverse position order at 1000 + n, and sets the run compensating with its '
  'cause; with nothing to undo the run takes the cause directly (ADR 0233). A run '
  'no longer queued or running is returned unchanged. Granted to NOBODY: only '
  'the definer functions of this migration call it.';

-- ---------------------------------------------------------------------------
-- Claiming a step (replaced; 0034's signature and result)
-- ---------------------------------------------------------------------------
--
-- 0034's three phases, in 0034's order, with three changes:
--
--   1. a requested cancel hands the run to `workflow_begin_compensation` rather
--      than setting `cancelled` directly -- a rejection is a cancel (ADR 0230)
--      and the undo follows it (ADR 0233);
--   2. a run past its timeout is failed through the same function, and **only
--      when no call is in flight** -- the cancel phase's own rule. 0034 failed a
--      timed-out run under a live lease; with compensation that would begin the
--      undo while a forward call was still upstream, and a forward write that
--      landed after the undo rows were appended would be undone by nothing.
--      The in-flight call's lease bounds the wait (D1744);
--   3. the selection takes EITHER a forward step, under 0034's predicate, from a
--      queued or running run with no cancel requested, OR an undo row from a
--      compensating run once every undo row before it is FINISHED -- succeeded
--      or failed, because each undo is independent and a failed one must not
--      stop the rest.
--
-- An undo row's `step` is the forward element's `compensation` block with the
-- row's own name merged in, so the worker calls it exactly as it calls any
-- write. `prior` is forward results only: an undo's result is not an input to
-- anything.
CREATE OR REPLACE FUNCTION app_private.workflow_claim_step(
  p_holder               text,
  p_lease_margin_seconds integer
) RETURNS TABLE (
  step_id         uuid,
  run_id          uuid,
  step_position   integer,
  step_name       text,
  attempt         integer,
  agent_id        uuid,
  dry_run         boolean,
  step            jsonb,
  input           jsonb,
  prior           jsonb,
  timeout_seconds integer,
  idempotency_key text
)
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  chosen uuid;
  due    uuid;
BEGIN
  IF p_holder IS NULL OR p_holder = '' THEN
    RAISE EXCEPTION 'AP422: a claim requires a holder'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_lease_margin_seconds IS NULL OR p_lease_margin_seconds < 0 THEN
    RAISE EXCEPTION 'AP422: a lease margin is zero or more seconds'
      USING ERRCODE = 'PT422';
  END IF;

  FOR due IN
    SELECT r.id
      FROM app_private.workflow_run r
     WHERE r.cancel_requested_at IS NOT NULL
       AND r.status IN ('queued', 'running')
       AND NOT EXISTS (
             SELECT 1 FROM app_private.workflow_step s
              WHERE s.run_id = r.id
                AND s.status = 'claimed'
                AND s.lease_until >= pg_catalog.now())
  LOOP
    PERFORM app_private.workflow_begin_compensation(due, 'cancelled');
  END LOOP;

  FOR due IN
    SELECT r.id
      FROM app_private.workflow_run r
     WHERE r.status = 'running'
       AND r.started_at IS NOT NULL
       AND r.started_at
           + pg_catalog.make_interval(secs => r.timeout_seconds) < pg_catalog.now()
       AND NOT EXISTS (
             SELECT 1 FROM app_private.workflow_step s
              WHERE s.run_id = r.id
                AND s.status = 'claimed'
                AND s.lease_until >= pg_catalog.now())
  LOOP
    UPDATE app_private.workflow_run SET stopped_reason = 'timed_out' WHERE id = due;
    PERFORM app_private.workflow_begin_compensation(due, 'failed');
  END LOOP;

  SELECT s.id INTO chosen
    FROM app_private.workflow_step s
    JOIN app_private.workflow_run r ON r.id = s.run_id
   WHERE (
           s.status = 'queued'
        OR (s.status = 'parked' AND s.resume_after <= pg_catalog.now())
        OR (s.status = 'claimed' AND s.lease_until < pg_catalog.now())
         )
     AND (
           (s.phase = 'forward'
            AND r.status IN ('queued', 'running')
            AND r.cancel_requested_at IS NULL
            AND NOT EXISTS (
                  SELECT 1 FROM app_private.workflow_step earlier
                   WHERE earlier.run_id = s.run_id
                     AND earlier.phase = 'forward'
                     AND earlier.position < s.position
                     AND earlier.status <> 'succeeded'))
        OR (s.phase = 'compensation'
            AND r.status = 'compensating'
            AND NOT EXISTS (
                  SELECT 1 FROM app_private.workflow_step earlier
                   WHERE earlier.run_id = s.run_id
                     AND earlier.phase = 'compensation'
                     AND earlier.position < s.position
                     AND earlier.status NOT IN ('succeeded', 'failed')))
         )
   ORDER BY r.created_at, s.position
   LIMIT 1
     FOR UPDATE OF s SKIP LOCKED;

  IF chosen IS NULL THEN
    RETURN;
  END IF;

  UPDATE app_private.workflow_step s
     SET status = 'claimed',
         claimed_by = p_holder,
         lease_until = pg_catalog.now()
                       + pg_catalog.make_interval(
                           secs => s.timeout_seconds + p_lease_margin_seconds),
         attempt = s.attempt + 1,
         request_id = NULL,
         resume_after = NULL,
         started_at = coalesce(s.started_at, pg_catalog.now())
   WHERE s.id = chosen;

  UPDATE app_private.workflow_run r
     SET status = 'running',
         started_at = coalesce(r.started_at, pg_catalog.now())
    FROM app_private.workflow_step s
   WHERE s.id = chosen AND r.id = s.run_id AND r.status = 'queued';

  RETURN QUERY
  SELECT s.id,
         s.run_id,
         s.position,
         s.name,
         s.attempt,
         r.agent_id,
         r.dry_run,
         CASE
           WHEN s.phase = 'compensation'
             THEN (((d.body -> 'steps') -> (s.compensates - 1)) -> 'compensation')
                  || jsonb_build_object('name', s.name)
           ELSE (d.body -> 'steps') -> (s.position - 1)
         END,
         r.input,
         coalesce(
           (SELECT jsonb_object_agg(done.name, coalesce(done.result, 'null'::jsonb))
              FROM app_private.workflow_step done
             WHERE done.run_id = s.run_id
               AND done.phase = 'forward'
               AND done.status = 'succeeded'),
           '{}'::jsonb),
         s.timeout_seconds,
         s.idempotency_key
    FROM app_private.workflow_step s
    JOIN app_private.workflow_run r ON r.id = s.run_id
    JOIN app_private.workflow_definition d ON d.id = r.definition_id
   WHERE s.id = chosen;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_claim_step(text, integer) IS
  'Claims at most one step, after applying requested cancels and failing '
  'timed-out runs -- both only where no call is in flight, and both through '
  'workflow_begin_compensation (ADR 0227, ADR 0233). A forward step is claimable '
  'when every earlier forward position has succeeded; an undo row of a '
  'compensating run when every earlier undo row is finished. The returned '
  'position and name are step_position and step_name (`position` is a '
  'col_name_keyword). The second argument is a MARGIN over the step''s own '
  'timeout (D1687). The LEASE PREDICATE is the correctness mechanism and SKIP '
  'LOCKED is throughput (ADR 0104).';

-- ---------------------------------------------------------------------------
-- Finishing a step (replaced; 0034's signature and result)
-- ---------------------------------------------------------------------------
--
-- A FORWARD step keeps 0034's branches, with two changes. The failure branch
-- hands the run to `workflow_begin_compensation`, so a run with nothing to undo
-- reads `failed` exactly as before. And a forward step that finishes on a run
-- no longer queued or running -- a late finish by a holder whose lease had
-- expired after the run moved on -- records the step and leaves the run where
-- it is; 0034 could have marked such a run `succeeded` over its `failed`.
--
-- An UNDO row records its outcome, and when no undo row of the run is
-- unfinished the run takes its `compensation_cause` with `compensation_outcome`
-- `complete` if every undo succeeded and `incomplete` otherwise. A refused mint
-- during compensation stops the run `incomplete`: the agent can no longer act,
-- so the rest cannot be undone as it.
--
-- **Every finish that took effect appends one attempt row** (ADR 0234). A
-- holder that lost its lease appends nothing: the attempt number belongs to the
-- successor now.
CREATE OR REPLACE FUNCTION app_private.workflow_finish_step(
  p_step       uuid,
  p_holder     text,
  p_outcome    app_private.workflow_step_outcome,
  p_result     jsonb,
  p_reason     text,
  p_request_id uuid
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  target     app_private.workflow_step;
  run_row    app_private.workflow_run;
  run_status text;
  unfinished integer;
BEGIN
  UPDATE app_private.workflow_step s
     SET status = CASE
                    WHEN p_outcome IN ('succeeded', 'replayed', 'dry_run') THEN 'succeeded'
                    ELSE 'failed'
                  END::app_private.workflow_step_status,
         outcome = p_outcome,
         result = p_result,
         reason = p_reason,
         request_id = p_request_id,
         claimed_by = NULL,
         lease_until = NULL,
         finished_at = pg_catalog.now()
   WHERE s.id = p_step AND s.claimed_by = p_holder AND s.status = 'claimed'
  RETURNING * INTO target;

  IF NOT FOUND THEN
    RETURN 'lease_lost';
  END IF;

  INSERT INTO app_private.workflow_attempt (step_id, attempt, event, outcome, request_id, reason)
  VALUES (target.id, target.attempt, 'finished', p_outcome, p_request_id, p_reason);

  SELECT * INTO run_row FROM app_private.workflow_run WHERE id = target.run_id FOR UPDATE;

  IF p_outcome = 'abandoned' THEN
    -- Nothing was done, in either phase: the step goes back to `queued` with its
    -- attempt already spent (0034's rule).
    UPDATE app_private.workflow_step
       SET status = 'queued', outcome = NULL, finished_at = NULL
     WHERE id = target.id;
    RETURN run_row.status::text;
  END IF;

  IF target.phase = 'compensation' THEN
    IF p_outcome = 'token_refused' THEN
      UPDATE app_private.workflow_run
         SET status = 'stopped',
             stopped_reason = 'agent_not_active',
             compensation_outcome = 'incomplete',
             finished_at = pg_catalog.now()
       WHERE id = target.run_id;
      RETURN 'stopped';
    END IF;

    SELECT count(*) INTO unfinished
      FROM app_private.workflow_step s
     WHERE s.run_id = target.run_id
       AND s.phase = 'compensation'
       AND s.status NOT IN ('succeeded', 'failed');

    IF unfinished = 0 AND run_row.status::text = 'compensating' THEN
      UPDATE app_private.workflow_run r
         SET status = r.compensation_cause,
             compensation_outcome = CASE
               WHEN EXISTS (
                      SELECT 1 FROM app_private.workflow_step s
                       WHERE s.run_id = r.id
                         AND s.phase = 'compensation'
                         AND s.status <> 'succeeded')
                 THEN 'incomplete'
               ELSE 'complete'
             END,
             finished_at = pg_catalog.now()
       WHERE r.id = target.run_id
      RETURNING r.status::text INTO run_status;
      RETURN run_status;
    END IF;
    RETURN run_row.status::text;
  END IF;

  IF run_row.status::text NOT IN ('queued', 'running') THEN
    RETURN run_row.status::text;
  END IF;

  IF p_outcome IN ('succeeded', 'replayed', 'dry_run') THEN
    SELECT count(*) INTO unfinished
      FROM app_private.workflow_step s
     WHERE s.run_id = target.run_id AND s.phase = 'forward' AND s.status <> 'succeeded';
    IF unfinished = 0 THEN
      UPDATE app_private.workflow_run
         SET status = 'succeeded', finished_at = pg_catalog.now()
       WHERE id = target.run_id;
      RETURN 'succeeded';
    END IF;
    RETURN run_row.status::text;
  ELSIF p_outcome = 'token_refused' THEN
    -- The agent stopped being able to act. `stopped`, not `failed`, and no
    -- undo: an undo is a call AS the agent, which is exactly what just failed.
    UPDATE app_private.workflow_run
       SET status = 'stopped',
           stopped_reason = 'agent_not_active',
           finished_at = pg_catalog.now()
     WHERE id = target.run_id;
    RETURN 'stopped';
  END IF;

  UPDATE app_private.workflow_run SET stopped_reason = p_reason WHERE id = target.run_id;
  RETURN app_private.workflow_begin_compensation(target.run_id, 'failed');
END $fn$;

COMMENT ON FUNCTION app_private.workflow_finish_step(
  uuid, text, app_private.workflow_step_outcome, jsonb, text, uuid) IS
  'Closes one step held by one holder, appends its attempt row, and returns the '
  'RUN''s new status (ADR 0227, ADR 0233, ADR 0234). A forward failure begins '
  'compensation; a run with nothing to undo is failed as under 0034. An undo row '
  'ends the run at its compensation_cause, complete or incomplete, once no undo '
  'is unfinished. token_refused stops the run; abandoned returns the step to '
  'queued; a holder that lost its lease gets ''lease_lost'' and appends nothing.';

-- ---------------------------------------------------------------------------
-- Parking a step (replaced; 0034's signature and result)
-- ---------------------------------------------------------------------------
--
-- 0034's body, plus the attempt row. A `wait` step's park carries the reason
-- `waiting`, which is what `workflow_gate_state` reads to say the wait has been
-- served -- so a reclaim after a crash finishes the wait rather than starting
-- it again (ADR 0233).
CREATE OR REPLACE FUNCTION app_private.workflow_park(
  p_step         uuid,
  p_holder       text,
  p_reason       text,
  p_resume_after timestamptz,
  p_request_id   uuid
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  parked_attempt integer;
BEGIN
  UPDATE app_private.workflow_step s
     SET status = 'parked',
         claimed_by = NULL,
         lease_until = NULL,
         resume_after = p_resume_after,
         reason = p_reason,
         request_id = p_request_id
   WHERE s.id = p_step AND s.claimed_by = p_holder AND s.status = 'claimed'
  RETURNING s.attempt INTO parked_attempt;
  IF NOT FOUND THEN
    RETURN 'lease_lost';
  END IF;

  INSERT INTO app_private.workflow_attempt (step_id, attempt, event, outcome, request_id, reason)
  VALUES (p_step, parked_attempt, 'parked', NULL, p_request_id, p_reason);
  RETURN 'parked';
END $fn$;

COMMENT ON FUNCTION app_private.workflow_park(uuid, text, text, timestamptz, uuid) IS
  'Defers one step until a time, releasing its lease, and appends its attempt row '
  '(ADR 0227, ADR 0234). Park is the backoff and a parked step is the pause; a '
  'wait step parks once with the reason waiting. A holder that lost its lease '
  'gets ''lease_lost'' and appends nothing.';

-- ---------------------------------------------------------------------------
-- The agent's own read and the counts (replaced; 0034's signatures)
-- ---------------------------------------------------------------------------
--
-- The status document gains each step's phase and the forward position it
-- compensates, the run's compensation cause and outcome, and -- on a step that
-- has one -- the approval's status and expiry. **Never the decider**: this is
-- the AGENT's read, and it does not name a human (ADR 0230). A pending approval
-- past its expiry reads `expired` here, the same word the gate reads.
CREATE OR REPLACE FUNCTION app_private.workflow_run_status(
  p_run   uuid,
  p_agent uuid
) RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  document jsonb;
BEGIN
  SELECT jsonb_build_object(
           'run_id', r.id,
           'definition', d.name,
           'definition_version', d.version,
           'lock_tools_sha256', d.lock_tools_sha256,
           'status', r.status,
           'stopped_reason', r.stopped_reason,
           'compensation_cause', r.compensation_cause,
           'compensation_outcome', r.compensation_outcome,
           'dry_run', r.dry_run,
           'input', r.input,
           'created_at', r.created_at,
           'started_at', r.started_at,
           'finished_at', r.finished_at,
           'cancel_requested_at', r.cancel_requested_at,
           'steps', coalesce(
             (SELECT jsonb_agg(jsonb_build_object(
                       'position', s.position,
                       'name', s.name,
                       'phase', s.phase,
                       'compensates', s.compensates,
                       'status', s.status,
                       'attempt', s.attempt,
                       'outcome', s.outcome,
                       'reason', s.reason,
                       'request_id', s.request_id,
                       'resume_after', s.resume_after,
                       'result', s.result,
                       'started_at', s.started_at,
                       'finished_at', s.finished_at,
                       'approval', CASE
                         WHEN a.id IS NULL THEN NULL
                         ELSE jsonb_build_object(
                                'status', CASE
                                  WHEN a.status = 'pending' AND a.expires_at <= pg_catalog.now()
                                    THEN 'expired'
                                  ELSE a.status::text
                                END,
                                'expires_at', a.expires_at)
                       END)
                     ORDER BY s.position)
                FROM app_private.workflow_step s
                LEFT JOIN app_private.workflow_approval a ON a.step_id = s.id
               WHERE s.run_id = r.id),
             '[]'::jsonb))
    INTO document
    FROM app_private.workflow_run r
    JOIN app_private.workflow_definition d ON d.id = r.definition_id
   WHERE r.id = p_run AND r.agent_id = p_agent;

  IF document IS NULL THEN
    RAISE EXCEPTION 'AP404: no such run'
      USING ERRCODE = 'PT404';
  END IF;

  RETURN document;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_run_status(uuid, uuid) IS
  'The AGENT''S OWN run, whole: the run row with its compensation cause and '
  'outcome, every step in order with its phase and, where one exists, its '
  'approval''s status and expiry -- never the decider, because this is the '
  'agent''s read and it names no human (ADR 0230). Another agent''s run is '
  'PT404, the same as a missing one.';

-- `approvals_pending` counts the decisions a human could take NOW: pending,
-- unexpired, on a run still running. The oldest one's age is the number an
-- operator reads; there is NO threshold (D1441), for 0034's reason.
CREATE OR REPLACE FUNCTION app_private.workflow_counts()
  RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  worker app_private.workflow_worker;
BEGIN
  SELECT * INTO worker FROM app_private.workflow_worker WHERE singleton;

  RETURN jsonb_build_object(
    'definitions', (SELECT count(*) FROM app_private.workflow_definition),
    'runs', coalesce(
      (SELECT jsonb_object_agg(status, total)
         FROM (SELECT status::text AS status, count(*) AS total
                 FROM app_private.workflow_run GROUP BY status) counted),
      '{}'::jsonb),
    'steps', coalesce(
      (SELECT jsonb_object_agg(status, total)
         FROM (SELECT status::text AS status, count(*) AS total
                 FROM app_private.workflow_step GROUP BY status) counted),
      '{}'::jsonb),
    'oldest_claimed_lease_age_seconds',
      (SELECT floor(extract(epoch FROM pg_catalog.now() - min(s.lease_until)))::bigint
         FROM app_private.workflow_step s
        WHERE s.status = 'claimed' AND s.lease_until < pg_catalog.now()),
    'heartbeat_age_seconds',
      CASE WHEN worker.seen_at IS NULL THEN NULL
           ELSE floor(extract(epoch FROM pg_catalog.now() - worker.seen_at))::bigint
      END,
    'heartbeat_holder', worker.holder,
    'approvals_pending',
      (SELECT count(*)
         FROM app_private.workflow_approval a
         JOIN app_private.workflow_run r ON r.id = a.run_id
        WHERE a.status = 'pending'
          AND a.expires_at > pg_catalog.now()
          AND r.status = 'running'),
    'oldest_pending_approval_age_seconds',
      (SELECT floor(extract(epoch FROM pg_catalog.now() - min(a.requested_at)))::bigint
         FROM app_private.workflow_approval a
         JOIN app_private.workflow_run r ON r.id = a.run_id
        WHERE a.status = 'pending'
          AND a.expires_at > pg_catalog.now()
          AND r.status = 'running')
  );
END $fn$;

COMMENT ON FUNCTION app_private.workflow_counts() IS
  'Runs and steps by status, the oldest OVERDUE lease''s age, the heartbeat''s '
  'age and holder, and the approvals a human could decide now with the oldest '
  'one''s age. Numbers and NO verdict (D1441). Carries no URL, key, token or '
  'caller value.';

-- ---------------------------------------------------------------------------
-- The gate: requesting, reading, expiring
-- ---------------------------------------------------------------------------
--
-- `workflow_request_approval` is called by the worker after the PLANE refused
-- the step's first call with `approval_required` (ADR 0230). It parks the step
-- until the approval's expiry -- **the expiry IS the park's time**, so no timer
-- is added -- and records the plane's request id of the refused call. The
-- compiled element must declare `approval`: the database refuses to open a
-- gate the reviewed definition did not ask for.
CREATE FUNCTION app_private.workflow_request_approval(
  p_step                  uuid,
  p_holder                text,
  p_request_id            uuid,
  p_expires_after_seconds integer
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  target  app_private.workflow_step;
  element jsonb;
  expiry  timestamptz;
BEGIN
  IF p_expires_after_seconds IS NULL OR p_expires_after_seconds NOT BETWEEN 60 AND 3600 THEN
    RAISE EXCEPTION 'AP422: an approval expires after 60 to 3600 seconds'
      USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO target
    FROM app_private.workflow_step s
   WHERE s.id = p_step AND s.claimed_by = p_holder AND s.status = 'claimed'
     FOR UPDATE;
  IF NOT FOUND THEN
    RETURN 'lease_lost';
  END IF;

  IF EXISTS (SELECT 1 FROM app_private.workflow_approval a WHERE a.step_id = p_step) THEN
    RAISE EXCEPTION 'AP409: an approval was already requested for this step'
      USING ERRCODE = 'PT409';
  END IF;

  SELECT (d.body -> 'steps') -> (target.position - 1) INTO element
    FROM app_private.workflow_run r
    JOIN app_private.workflow_definition d ON d.id = r.definition_id
   WHERE r.id = target.run_id;
  IF target.phase <> 'forward'
     OR jsonb_typeof(element -> 'approval') IS DISTINCT FROM 'object'
     OR coalesce(element ->> 'tool', '') = '' THEN
    RAISE EXCEPTION 'AP422: this step declares no approval'
      USING ERRCODE = 'PT422';
  END IF;

  expiry := pg_catalog.now() + pg_catalog.make_interval(secs => p_expires_after_seconds);

  INSERT INTO app_private.workflow_approval
    (run_id, step_id, tool, capability, idempotency_key, requested_request_id, expires_at)
  VALUES
    (target.run_id, target.id, element ->> 'tool',
     (element ->> 'capability') || '@' || (element ->> 'capability_version'),
     target.idempotency_key, p_request_id, expiry);

  UPDATE app_private.workflow_step
     SET status = 'parked',
         claimed_by = NULL,
         lease_until = NULL,
         resume_after = expiry,
         reason = 'approval_required',
         request_id = p_request_id
   WHERE id = target.id;

  INSERT INTO app_private.workflow_attempt (step_id, attempt, event, outcome, request_id, reason)
  VALUES (target.id, target.attempt, 'approval_requested', 'refused', p_request_id,
          'approval_required');

  RETURN 'parked';
END $fn$;

COMMENT ON FUNCTION app_private.workflow_request_approval(uuid, text, uuid, integer) IS
  'Records a pending approval for a step the plane refused with '
  'approval_required, carrying the plane''s request id of that call, and parks '
  'the step until the approval''s expiry (ADR 0230). Only a forward step whose '
  'compiled element declares approval; one request per step (PT409). A holder '
  'that lost its lease gets ''lease_lost''.';

-- The worker's ONE read at a gate: the approval's state, and whether a wait
-- step's park has been served. `pending` past its expiry reads `expired`.
CREATE FUNCTION app_private.workflow_gate_state(
  p_step   uuid,
  p_holder text
) RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  approval jsonb;
BEGIN
  IF NOT EXISTS (
       SELECT 1 FROM app_private.workflow_step s
        WHERE s.id = p_step AND s.claimed_by = p_holder AND s.status = 'claimed') THEN
    RAISE EXCEPTION 'AP404: no such step' USING ERRCODE = 'PT404';
  END IF;

  SELECT jsonb_build_object(
           'id', a.id,
           'status', CASE
             WHEN a.status = 'pending' AND a.expires_at <= pg_catalog.now() THEN 'expired'
             ELSE a.status::text
           END,
           'expires_at', a.expires_at)
    INTO approval
    FROM app_private.workflow_approval a
   WHERE a.step_id = p_step;

  RETURN jsonb_build_object(
    'approval', approval,
    'waited', EXISTS (
      SELECT 1 FROM app_private.workflow_attempt t
       WHERE t.step_id = p_step AND t.event = 'parked' AND t.reason = 'waiting'));
END $fn$;

COMMENT ON FUNCTION app_private.workflow_gate_state(uuid, text) IS
  'The worker''s one read at a gate, for a step it holds: the approval (none, '
  'pending, approved, rejected, or expired -- a pending one past its expiry) and '
  'whether a wait step''s park has been served (ADR 0230, ADR 0233).';

CREATE FUNCTION app_private.workflow_expire_approval(
  p_step   uuid,
  p_holder text
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  expired integer;
BEGIN
  IF NOT EXISTS (
       SELECT 1 FROM app_private.workflow_step s
        WHERE s.id = p_step AND s.claimed_by = p_holder AND s.status = 'claimed') THEN
    RETURN 'lease_lost';
  END IF;

  UPDATE app_private.workflow_approval a
     SET status = 'expired'
   WHERE a.step_id = p_step
     AND a.status = 'pending'
     AND a.expires_at <= pg_catalog.now();
  GET DIAGNOSTICS expired = ROW_COUNT;
  RETURN CASE WHEN expired = 1 THEN 'expired' ELSE 'not_expired' END;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_expire_approval(uuid, text) IS
  'Marks a pending approval past its expiry expired, for a step the caller holds '
  '(ADR 0230). Returns expired or not_expired; only a pending row changes, so a '
  'decided approval is never rewritten.';

-- ---------------------------------------------------------------------------
-- The decision
-- ---------------------------------------------------------------------------
--
-- **Every check is made before the first write, so a refusal changes nothing**
-- (ADR 0230). In order: the approval of the run's step named `p_step_name`
-- (none is the same `no such run` a missing run gets); the run's OWNER may not
-- decide (`approver_is_owner`, ADR 0232 -- D1638 keeps an administrator apart
-- from a tenant's agents, and this keeps an administrator apart from their
-- own); a decided approval is final (`approval_already_decided`); an expired
-- one cannot be decided (`approval_expired`); and a run no longer running has
-- nobody waiting on the decision, which is the same `no such run`.
--
-- Approve sets the step's `resume_after` to now, so the next claim takes it at
-- once. **Reject is a cancel**: it requests the run's cancel, and the next
-- claim applies it through the path every cancel takes -- the undo follows.
CREATE FUNCTION app_private.workflow_decide_approval(
  p_run       uuid,
  p_step_name text,
  p_user      uuid,
  p_decision  text
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  target app_private.workflow_approval;
  run_row app_private.workflow_run;
BEGIN
  IF p_decision IS NULL OR p_decision NOT IN ('approve', 'reject') THEN
    RAISE EXCEPTION 'AP422: a decision is approve or reject'
      USING ERRCODE = 'PT422';
  END IF;

  SELECT a.* INTO target
    FROM app_private.workflow_approval a
    JOIN app_private.workflow_step s ON s.id = a.step_id
   WHERE a.run_id = p_run AND s.name = p_step_name
     FOR UPDATE OF a;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no such run' USING ERRCODE = 'PT404';
  END IF;

  SELECT * INTO run_row FROM app_private.workflow_run WHERE id = p_run;

  IF run_row.owner_id = p_user THEN
    RAISE EXCEPTION 'AP403: approver_is_owner' USING ERRCODE = 'PT403';
  END IF;
  IF target.status <> 'pending' THEN
    RAISE EXCEPTION 'AP409: approval_already_decided' USING ERRCODE = 'PT409';
  END IF;
  IF target.expires_at <= pg_catalog.now() THEN
    RAISE EXCEPTION 'AP409: approval_expired' USING ERRCODE = 'PT409';
  END IF;
  IF run_row.status::text <> 'running' THEN
    RAISE EXCEPTION 'AP404: no such run' USING ERRCODE = 'PT404';
  END IF;

  IF p_decision = 'approve' THEN
    UPDATE app_private.workflow_approval
       SET status = 'approved', decided_by = p_user, decided_at = pg_catalog.now()
     WHERE id = target.id AND status = 'pending';
    UPDATE app_private.workflow_step
       SET resume_after = pg_catalog.now()
     WHERE id = target.step_id AND status = 'parked';
    RETURN 'approved';
  END IF;

  UPDATE app_private.workflow_approval
     SET status = 'rejected', decided_by = p_user, decided_at = pg_catalog.now()
   WHERE id = target.id AND status = 'pending';
  UPDATE app_private.workflow_run
     SET cancel_requested_at = coalesce(cancel_requested_at, pg_catalog.now())
   WHERE id = p_run;
  RETURN 'rejected';
END $fn$;

COMMENT ON FUNCTION app_private.workflow_decide_approval(uuid, text, uuid, text) IS
  'Records a human''s decision on one pending approval, final and before its '
  'expiry (ADR 0230, ADR 0232). Refuses the run''s owner (approver_is_owner), a '
  'decided approval (approval_already_decided) and an expired one '
  '(approval_expired), each before any write. Approve makes the step claimable '
  'at once; reject requests the run''s cancel, which the next claim applies.';

-- What waits for a human, oldest first. **No argument value, no input, no
-- result** (ADR 0230, D1720): a capability's `audit.redact` would otherwise be
-- bypassed, and D1638 keeps an administrator out of tenant rows. The approver
-- reads the reviewed definition for what the step does.
CREATE FUNCTION app_private.workflow_pending_approvals(p_limit integer)
  RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
  IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100 THEN
    RAISE EXCEPTION 'AP422: a page is 1 to 100 approvals' USING ERRCODE = 'PT422';
  END IF;

  RETURN coalesce(
    (SELECT jsonb_agg(page.document ORDER BY page.requested_at, page.id)
       FROM (SELECT a.id,
                    a.requested_at,
                    jsonb_build_object(
                      'run_id', r.id,
                      'definition', d.name,
                      'definition_version', d.version,
                      'step', s.name,
                      'position', s.position,
                      'capability', a.capability,
                      'tool', a.tool,
                      'agent_id', r.agent_id,
                      'owner_id', r.owner_id,
                      'requested_at', a.requested_at,
                      'expires_at', a.expires_at) AS document
               FROM app_private.workflow_approval a
               JOIN app_private.workflow_step s ON s.id = a.step_id
               JOIN app_private.workflow_run r ON r.id = a.run_id
               JOIN app_private.workflow_definition d ON d.id = r.definition_id
              WHERE a.status = 'pending'
                AND a.expires_at > pg_catalog.now()
                AND r.status = 'running'
              ORDER BY a.requested_at, a.id
              LIMIT p_limit) page),
    '[]'::jsonb);
END $fn$;

COMMENT ON FUNCTION app_private.workflow_pending_approvals(integer) IS
  'Pending, unexpired approvals on running runs, oldest first: who, which run, '
  'definition and step, which capability and tool, and until when -- and no '
  'argument value, input or result (ADR 0230, D1720).';

-- What the SIGNER reads before it adds `apg_approval` to a step token (ADR
-- 0231): the tool and the key of an APPROVED approval whose run belongs to this
-- agent and is still running. Zero rows means refuse. **The decision window is
-- not re-checked once a decision is taken** (D1745): the expiry bounds how long
-- a human may take to decide, and an approved step that parks on a retryable
-- conflict must be able to mint again -- re-checking would turn that retry into
-- a refused mint, which the worker reads as the agent no longer being able to
-- act. What bounds an approved call is the step's own retry and the run's
-- timeout, and the claim binds ONE write through its key.
CREATE FUNCTION app_private.workflow_approval_for_token(
  p_approval uuid,
  p_agent    uuid
) RETURNS TABLE (tool text, idempotency_key text)
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
  RETURN QUERY
  SELECT a.tool, a.idempotency_key
    FROM app_private.workflow_approval a
    JOIN app_private.workflow_run r ON r.id = a.run_id
   WHERE a.id = p_approval
     AND a.status = 'approved'
     AND r.agent_id = p_agent
     AND r.status = 'running';
END $fn$;

COMMENT ON FUNCTION app_private.workflow_approval_for_token(uuid, uuid) IS
  'The tool and idempotency key of an APPROVED approval on a running run of this '
  'agent, or no row (ADR 0231). Read by the signer before it adds apg_approval to '
  'one step token, so the claim''s content comes from a decided row and never '
  'from the caller.';

-- ---------------------------------------------------------------------------
-- Provenance
-- ---------------------------------------------------------------------------
--
-- One document for one run, read by an AUDITOR (`admin_audit:read`, ADR 0234):
-- every step in position order with EVERY attempt, each attempt joined to its
-- `agent_audit` rows by the plane's request id (D1696), and every approval with
-- its decider. **Never `parameters`, never a step's `result`, and the run's
-- input by KEY only** (D1746): the input may carry values a capability's
-- `audit.redact` keeps out of the audit record, and provenance must not put back
-- what the audit left out. Two things the brief asked for are reported ABSENT
-- with a reason rather than filled (ADR 0195): no per-call record names a
-- profile, and the lock a call ran under is the audit row's `contract_hash`.
CREATE FUNCTION app_private.workflow_provenance(p_run uuid)
  RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  document jsonb;
BEGIN
  SELECT jsonb_build_object(
           'run', jsonb_build_object(
             'run_id', r.id,
             'agent_id', r.agent_id,
             'owner_id', r.owner_id,
             'input_keys', coalesce(
               (SELECT jsonb_agg(k ORDER BY k) FROM jsonb_object_keys(r.input) k),
               '[]'::jsonb),
             'dry_run', r.dry_run,
             'status', r.status,
             'stopped_reason', r.stopped_reason,
             'compensation_cause', r.compensation_cause,
             'compensation_outcome', r.compensation_outcome,
             'created_at', r.created_at,
             'started_at', r.started_at,
             'finished_at', r.finished_at,
             'cancel_requested_at', r.cancel_requested_at),
           'definition', jsonb_build_object(
             'name', d.name,
             'version', d.version,
             'source_sha256', d.source_sha256,
             'lock_tools_sha256', d.lock_tools_sha256),
           'profile', jsonb_build_object(
             'value', NULL,
             'reason', 'no per-call record names a profile'),
           'steps', coalesce(
             (SELECT jsonb_agg(jsonb_build_object(
                       'position', s.position,
                       'name', s.name,
                       'phase', s.phase,
                       'compensates', s.compensates,
                       'kind', e.element ->> 'kind',
                       'tool', e.element ->> 'tool',
                       'capability', CASE
                         WHEN e.element ? 'capability'
                           THEN (e.element ->> 'capability') || '@'
                                || (e.element ->> 'capability_version')
                       END,
                       'idempotency_key', s.idempotency_key,
                       'status', s.status,
                       'outcome', s.outcome,
                       'reason', s.reason,
                       'attempts', coalesce(
                         (SELECT jsonb_agg(jsonb_build_object(
                                   'attempt', t.attempt,
                                   'event', t.event,
                                   'outcome', t.outcome,
                                   'reason', t.reason,
                                   'request_id', t.request_id,
                                   'recorded_at', t.recorded_at,
                                   'audit', coalesce(
                                     (SELECT jsonb_agg(jsonb_build_object(
                                               'source', au.source,
                                               'outcome', au.outcome,
                                               'denial_reason', au.denial_reason,
                                               'row_count', au.row_count,
                                               'elapsed_ms', au.elapsed_ms,
                                               'capability_version', au.capability_version,
                                               'contract_hash', au.contract_hash,
                                               'started_at', au.started_at,
                                               'completed_at', au.completed_at)
                                             ORDER BY au.started_at, au.id)
                                        FROM app_private.agent_audit au
                                       WHERE t.request_id IS NOT NULL
                                         AND au.request_id = t.request_id),
                                     '[]'::jsonb))
                                 ORDER BY t.attempt, t.recorded_at)
                            FROM app_private.workflow_attempt t
                           WHERE t.step_id = s.id),
                         '[]'::jsonb))
                     ORDER BY s.position)
                FROM app_private.workflow_step s
                CROSS JOIN LATERAL (
                  SELECT CASE
                           WHEN s.phase = 'compensation'
                             THEN ((d.body -> 'steps') -> (s.compensates - 1)) -> 'compensation'
                           ELSE (d.body -> 'steps') -> (s.position - 1)
                         END AS element) e
               WHERE s.run_id = r.id),
             '[]'::jsonb),
           'approvals', coalesce(
             (SELECT jsonb_agg(jsonb_build_object(
                       'step', s.name,
                       'capability', a.capability,
                       'tool', a.tool,
                       'status', CASE
                         WHEN a.status = 'pending' AND a.expires_at <= pg_catalog.now()
                           THEN 'expired'
                         ELSE a.status::text
                       END,
                       'requested_at', a.requested_at,
                       'requested_request_id', a.requested_request_id,
                       'expires_at', a.expires_at,
                       'decided_by', a.decided_by,
                       'decided_by_username', u.username,
                       'decided_at', a.decided_at)
                     ORDER BY a.requested_at, a.id)
                FROM app_private.workflow_approval a
                JOIN app_private.workflow_step s ON s.id = a.step_id
                LEFT JOIN app_private.users u ON u.id = a.decided_by
               WHERE a.run_id = r.id),
             '[]'::jsonb))
    INTO document
    FROM app_private.workflow_run r
    JOIN app_private.workflow_definition d ON d.id = r.definition_id
   WHERE r.id = p_run;

  IF document IS NULL THEN
    RAISE EXCEPTION 'AP404: no such run' USING ERRCODE = 'PT404';
  END IF;
  RETURN document;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_provenance(uuid) IS
  'One run, for an auditor (ADR 0234): the run, its definition''s digests, every '
  'step with every attempt joined to its agent_audit rows by the plane''s request '
  'id, and every approval with its decider. Never parameters, never a result, '
  'and the input by key only (D1746). The profile is reported absent with a '
  'reason (ADR 0195).';

-- ---------------------------------------------------------------------------
-- The audit reader, re-created at a new arity, and its counter
-- ---------------------------------------------------------------------------
--
-- 0032 said it would take this (D1248): a window, an outcome, a denial reason
-- and a cursor are four more arguments, and `CREATE OR REPLACE` cannot change a
-- `RETURNS TABLE` or an argument list, so the reader is dropped and re-created.
-- The result is 0032's, column for column, so a `SELECT *` caller reads the
-- same mapping; the one caller, `repository.py`, moves in the same commit and
-- ADR 0175's guard sees it.
--
-- **plpgsql, so an unknown outcome or reason is PT422 and never an empty page**:
-- a reader that answered a typo with zero rows would report *no refusals* about
-- a window it never filtered. A half-given cursor is PT422 for the same reason.
--
-- **The keyset is `(started_at, id)`** -- rig 33d measured 1,000 rows sharing
-- one `started_at` walked once each with the id tie-break, and the control
-- without it stopped after one page.
DROP FUNCTION app_private.auth_list_agent_audit(uuid, uuid, integer);

CREATE FUNCTION app_private.auth_list_agent_audit(
  p_agent_id           uuid,
  p_owner_id           uuid,
  p_since              timestamptz,
  p_until              timestamptz,
  p_outcome            text,
  p_denial_reason      text,
  p_before_started_at  timestamptz,
  p_before_id          uuid,
  p_limit              integer
)
  RETURNS TABLE (
    id            uuid,
    source        app_private.agent_audit_source,
    agent_id      uuid,
    owner_id      uuid,
    tool          text,
    request_id    uuid,
    parameters    jsonb,
    outcome       app_private.agent_audit_outcome,
    row_count     integer,
    elapsed_ms    integer,
    started_at    timestamptz,
    completed_at  timestamptz,
    denial_reason app_private.agent_denial_reason
  )
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
  IF p_outcome IS NOT NULL
     AND p_outcome <> ALL (enum_range(NULL::app_private.agent_audit_outcome)::text[]) THEN
    RAISE EXCEPTION 'AP422: unknown outcome' USING ERRCODE = 'PT422';
  END IF;
  IF p_denial_reason IS NOT NULL
     AND p_denial_reason <> ALL (enum_range(NULL::app_private.agent_denial_reason)::text[]) THEN
    RAISE EXCEPTION 'AP422: unknown denial reason' USING ERRCODE = 'PT422';
  END IF;
  IF (p_before_started_at IS NULL) <> (p_before_id IS NULL) THEN
    RAISE EXCEPTION 'AP422: a cursor names a time and an id together' USING ERRCODE = 'PT422';
  END IF;

  RETURN QUERY
  SELECT r.id, r.source, r.agent_id, r.owner_id, r.tool, r.request_id,
         r.parameters, r.outcome, r.row_count, r.elapsed_ms,
         r.started_at, r.completed_at, r.denial_reason
    FROM app_private.agent_audit r
   WHERE (p_agent_id IS NULL OR r.agent_id = p_agent_id)
     AND (p_owner_id IS NULL OR r.owner_id = p_owner_id)
     AND (p_since IS NULL OR r.started_at >= p_since)
     AND (p_until IS NULL OR r.started_at < p_until)
     AND (p_outcome IS NULL OR r.outcome::text = p_outcome)
     AND (p_denial_reason IS NULL OR r.denial_reason::text = p_denial_reason)
     AND (p_before_started_at IS NULL
          OR (r.started_at, r.id) < (p_before_started_at, p_before_id))
   ORDER BY r.started_at DESC, r.id DESC
   LIMIT p_limit;
END $fn$;

COMMENT ON FUNCTION app_private.auth_list_agent_audit(
  uuid, uuid, timestamptz, timestamptz, text, text, timestamptz, uuid, integer) IS
  'The only read path to app_private.agent_audit (ADR 0142), returning the '
  'boundary that refused (ADR 0178), filtered by agent, owner, a half-open window '
  '[since, until), an outcome and a denial reason, and paged by the keyset '
  '(started_at, id) descending (ADR 0234, rig 33d). An unknown outcome or reason '
  'and a half-given cursor are PT422, never an empty page. Every filter narrows a '
  'read the scope already authorised. Granted to auth_service alone; the bound on '
  'p_limit is the route''s.';

-- **The window's counts, ignoring the outcome and reason filters and the
-- cursor.** This is D1248's own objection answered rather than overruled: a
-- viewer asking for `outcome=committed` gets a page with no refusal on it AND
-- this document on the same response, which says how many refusals the window
-- holds. A filter can narrow what is shown; it cannot hide that refusals exist.
CREATE FUNCTION app_private.auth_count_agent_audit(
  p_agent_id uuid,
  p_owner_id uuid,
  p_since    timestamptz,
  p_until    timestamptz
) RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  document jsonb;
BEGIN
  WITH windowed AS (
    SELECT r.outcome, r.denial_reason
      FROM app_private.agent_audit r
     WHERE (p_agent_id IS NULL OR r.agent_id = p_agent_id)
       AND (p_owner_id IS NULL OR r.owner_id = p_owner_id)
       AND (p_since IS NULL OR r.started_at >= p_since)
       AND (p_until IS NULL OR r.started_at < p_until)
  )
  SELECT jsonb_build_object(
           'total', (SELECT count(*) FROM windowed),
           'by_outcome', coalesce(
             (SELECT jsonb_object_agg(o.outcome, o.total)
                FROM (SELECT outcome::text AS outcome, count(*) AS total
                        FROM windowed GROUP BY outcome) o),
             '{}'::jsonb),
           'by_denial_reason', coalesce(
             (SELECT jsonb_object_agg(d.reason, d.total)
                FROM (SELECT denial_reason::text AS reason, count(*) AS total
                        FROM windowed WHERE denial_reason IS NOT NULL
                       GROUP BY denial_reason) d),
             '{}'::jsonb))
    INTO document;
  RETURN document;
END $fn$;

COMMENT ON FUNCTION app_private.auth_count_agent_audit(uuid, uuid, timestamptz, timestamptz) IS
  'The audit window''s counts by outcome and by denial reason, over the same '
  'agent, owner and window predicate as the reader and NOTHING else -- not its '
  'outcome or reason filter, not its cursor -- so a filtered page cannot hide '
  'that refusals exist (D1248, ADR 0234). Granted to auth_service alone.';

-- ---------------------------------------------------------------------------
-- The privileges, and the one that is absent
-- ---------------------------------------------------------------------------
--
-- `REVOKE ALL FROM PUBLIC` on every function this file creates, for 0020's
-- reason (D57, D262): a function is PUBLIC-executable the moment it exists. The
-- re-created reader is revoked and re-granted because its DROP took 0032's
-- grants with it (rig 24c measured the gap between the CREATE and the GRANT).
--
-- The five functions replaced in place KEEP 0034's grants: a `CREATE OR
-- REPLACE` does not touch a function's ACL, and re-granting them here would
-- leave it unclear which migration owns the privilege.
--
-- **`workflow_begin_compensation` is granted to nobody**, and that absence is
-- the decision -- stated here so a reader looking for the grant finds the
-- reason instead of a gap.
--
-- Schema USAGE on `app_private` is 0011's and is not re-granted (D337). This
-- block runs as the object owner and `RESET ROLE` is BELOW it (D285).
REVOKE ALL ON FUNCTION app_private.workflow_begin_compensation(
  uuid, app_private.workflow_run_status) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  app_private.workflow_request_approval(uuid, text, uuid, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_gate_state(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_expire_approval(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  app_private.workflow_decide_approval(uuid, text, uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_pending_approvals(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_approval_for_token(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_provenance(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.auth_list_agent_audit(
  uuid, uuid, timestamptz, timestamptz, text, text, timestamptz, uuid, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  app_private.auth_count_agent_audit(uuid, uuid, timestamptz, timestamptz) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
  app_private.workflow_request_approval(uuid, text, uuid, integer) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.workflow_gate_state(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.workflow_expire_approval(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.workflow_decide_approval(uuid, text, uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.workflow_pending_approvals(integer) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.workflow_approval_for_token(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.workflow_provenance(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.auth_list_agent_audit(
  uuid, uuid, timestamptz, timestamptz, text, text, timestamptz, uuid, integer)
  TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.auth_count_agent_audit(uuid, uuid, timestamptz, timestamptz) TO {{auth_service}};

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

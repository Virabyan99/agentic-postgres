-- migrate:up
-- What the Stage 4 record keeps, and what an operator must do to make a run, a
-- delivery or an agent disappear (ADR 0248, which extends ADR 0213; D1985-D1989).
--
-- 0034, 0035 and 0036 added ten `app_private` tables and nothing that removes a
-- row from any of them: every foreign key among them is `NO ACTION` (0034: *"No
-- trigger, no schedule, no `ON DELETE`"*). On beta at Session 35's close: 133
-- runs, 372 steps, 327 attempts, 29 approvals, 83 revoked probe agents a run
-- pins (D1700), and 7 approvals `pending` forever on runs that had ended
-- (D1775). From Stage 5 strangers write these rows.
--
-- ---------------------------------------------------------------------------
-- What this migration does NOT do, and it is still the larger half
-- ---------------------------------------------------------------------------
--
-- **Nothing here deletes a row on its own.** ADR 0213's rule is kept whole:
-- retention is an act an operator performs, on a horizon the operator states,
-- with the counts in front of them. There is no timer, no trigger, no `ON
-- DELETE`, no default horizon. The three prunes are granted to NOBODY -- the
-- object owner and a superuser reach them, which is the hand that already holds
-- `docker exec ... psql -U postgres`, and `bin/record.sh` is that hand made a
-- command (root, a stated horizon, a typed confirmation).
--
-- The one function that does write on its own is the withdrawal, and what it
-- writes is a STATUS, never a deletion: a `pending` approval whose run has
-- ended becomes `withdrawn` (0038's value). Granted to `auth_service`, called by
-- the worker on an idle iteration, so the 7 on beta resolve within one poll of
-- the deploy and every later one within one poll of its run ending.
--
-- ---------------------------------------------------------------------------
-- Prunes by AGGREGATE, never per table (D1986), and the order is load-bearing
-- ---------------------------------------------------------------------------
--
-- A step, an approval, an attempt and a receipt have no meaning without their
-- run, so each prune deletes a ROOT and its children together, in foreign-key
-- order, inside one function. A prune per table would let an operator delete a
-- run's steps and keep the run -- a record no reader can explain.
--
-- **Measured in rig 36b** on a cluster with 0001-0037 applied: the run prune as
-- sequential `DELETE ... = ANY (victims)` in the order attempts -> approvals ->
-- receipts -> steps -> runs removed exactly the ended runs' rows; **the control,
-- runs deleted first, failed with `23503 ... workflow_step_run_id_fkey`**. The
-- victims are chosen once, into an array, so every DELETE reads the same set.
-- `p_limit` bounds the ROOTS (runs, deliveries, agents) -- the unit an operator
-- reads in the returned count -- and `LIMIT NULL` is no limit (measured).
--
-- **Never pruned**: workflow definitions and connectors (installed
-- configuration, deploy steps 6d/6e), the worker singleton, humans (`users` is
-- referenced from six places and deleting a person is an identity question, not
-- a retention one), a run `queued`, `running` or `compensating`, a `pending`
-- delivery.
--
-- ---------------------------------------------------------------------------
-- The refusals
-- ---------------------------------------------------------------------------
--
-- 0033's three, for 0033's reasons: a NULL horizon matches nothing and would
-- read *there was nothing to prune*; a future horizon deletes rows written while
-- the operator was deciding; a bound below one row is not a bound. The future
-- refusal's sentence here says *must be in the past* -- 0033's reads *is in the
-- past* for the same case, and a released migration is not amended (D912), so
-- the clearer sentence lands in the new functions only.
--
-- **`workflow_run_prune` refuses one more horizon: anything newer than
-- `now() - 600 s`** (D1988). An inbound connector's receipt IS its replay
-- protection (0036's primary key), the route refuses a signature outside
-- +/-300 s, and a run can end two seconds after its receipt arrived. Deleting a
-- receipt with its run inside the signature window would re-open a replay the
-- route refuses today; the bound is the window, doubled.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The withdrawal (D1775, D1987)
-- ---------------------------------------------------------------------------
--
-- Pending approvals whose run is `succeeded`, `failed`, `cancelled` or
-- `stopped` become `withdrawn`. Not `compensating`: a compensating run is still
-- in flight, and its approval -- if it has one -- is the worker's to close
-- through `workflow_expire_approval` on the terms 0035 wrote.
--
-- **Measured in rig 36d**: 10,000 approvals across 2,000 runs, half ended, 2,000
-- pending -- the first call withdrew 1,000 in 82.7 ms; every later call found
-- nothing in 0.8-1.4 ms, a bitmap scan of 0035's
-- `workflow_approval_status_requested_idx`. Cheap enough for every idle poll; no
-- index is added.
--
-- Granted to `auth_service` and shipped with its caller in the same commit
-- (D1680): the worker loop, the role the loop already runs as (0034). It holds
-- nothing an agent does not -- no token is minted from a `withdrawn` approval
-- (`workflow_approval_for_token` requires `approved` on a `running` run).
CREATE FUNCTION app_private.workflow_withdraw_ended_approvals()
  RETURNS bigint
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  moved bigint;
BEGIN
  UPDATE app_private.workflow_approval a
     SET status = 'withdrawn'
    FROM app_private.workflow_run r
   WHERE a.run_id = r.id
     AND a.status = 'pending'
     AND r.status IN ('succeeded', 'failed', 'cancelled', 'stopped');
  GET DIAGNOSTICS moved = ROW_COUNT;
  RETURN moved;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_withdraw_ended_approvals() IS
  'Moves every pending approval whose run has ended (succeeded, failed, '
  'cancelled, stopped) to withdrawn and returns how many (ADR 0248, D1775). A '
  'status, never a deletion; names no person. Granted to auth_service alone: '
  'the workflow worker calls it on an idle iteration.';

-- ---------------------------------------------------------------------------
-- The run prune
-- ---------------------------------------------------------------------------
CREATE FUNCTION app_private.workflow_run_prune(
  p_before timestamptz,
  p_limit  integer DEFAULT NULL
) RETURNS bigint
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  victims uuid[];
BEGIN
  IF p_before IS NULL THEN
    RAISE EXCEPTION 'AP422: a retention horizon is required'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_before > pg_catalog.now() THEN
    RAISE EXCEPTION 'AP422: a retention horizon must be in the past'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_before > pg_catalog.now() - interval '600 seconds' THEN
    RAISE EXCEPTION 'AP422: a retention horizon inside the inbound replay window'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_limit IS NOT NULL AND p_limit < 1 THEN
    RAISE EXCEPTION 'AP422: a prune bound is at least one row'
      USING ERRCODE = 'PT422';
  END IF;

  SELECT pg_catalog.array_agg(q.id) INTO victims
    FROM (SELECT r.id
            FROM app_private.workflow_run r
           WHERE r.status IN ('succeeded', 'failed', 'cancelled', 'stopped')
             AND r.finished_at < p_before
           ORDER BY r.finished_at
           LIMIT p_limit) q;
  IF victims IS NULL THEN
    RETURN 0;
  END IF;

  DELETE FROM app_private.workflow_attempt
   WHERE step_id IN (SELECT s.id FROM app_private.workflow_step s
                      WHERE s.run_id = ANY (victims));
  DELETE FROM app_private.workflow_approval WHERE run_id = ANY (victims);
  DELETE FROM app_private.connector_receipt WHERE run_id = ANY (victims);
  DELETE FROM app_private.workflow_step WHERE run_id = ANY (victims);
  DELETE FROM app_private.workflow_run WHERE id = ANY (victims);
  RETURN pg_catalog.cardinality(victims);
END $fn$;

COMMENT ON FUNCTION app_private.workflow_run_prune(timestamptz, integer) IS
  'Deletes ended runs (succeeded, failed, cancelled, stopped) that finished '
  'before a horizon the OPERATOR states, with their attempts, approvals, '
  'receipts and steps, and returns how many RUNS it removed (ADR 0248). Refuses '
  'a horizon inside the inbound replay window (now() - 600 s, D1988). Never a '
  'queued, running or compensating run. Granted to nobody; nothing calls it on '
  'a schedule. With p_limit, call it again until it returns zero.';

-- ---------------------------------------------------------------------------
-- The delivery prune
-- ---------------------------------------------------------------------------
--
-- Then the events left with no delivery. **The guard on awaited events is
-- belt-and-braces** (D1989, read in Run 1): 0036 never serves a parked wait from
-- a stored event -- *"An event emitted before the park does not serve it"* --
-- and the only other readers of `connector_event` reach it through a delivery.
-- Kept because it costs one `NOT EXISTS`. A step's `await_event` holds
-- `name@version`, so the comparison is built from the event's two columns
-- (D2008).
CREATE FUNCTION app_private.connector_delivery_prune(
  p_before timestamptz,
  p_limit  integer DEFAULT NULL
) RETURNS bigint
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  victims uuid[];
BEGIN
  IF p_before IS NULL THEN
    RAISE EXCEPTION 'AP422: a retention horizon is required'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_before > pg_catalog.now() THEN
    RAISE EXCEPTION 'AP422: a retention horizon must be in the past'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_limit IS NOT NULL AND p_limit < 1 THEN
    RAISE EXCEPTION 'AP422: a prune bound is at least one row'
      USING ERRCODE = 'PT422';
  END IF;

  SELECT pg_catalog.array_agg(q.id) INTO victims
    FROM (SELECT d.id
            FROM app_private.connector_delivery d
           WHERE d.status IN ('delivered', 'dead')
             AND coalesce(d.delivered_at, d.dead_at) < p_before
           ORDER BY coalesce(d.delivered_at, d.dead_at)
           LIMIT p_limit) q;
  IF victims IS NULL THEN
    RETURN 0;
  END IF;

  DELETE FROM app_private.connector_delivery WHERE id = ANY (victims);
  DELETE FROM app_private.connector_event e
   WHERE e.emitted_at < p_before
     AND NOT EXISTS (SELECT 1 FROM app_private.connector_delivery d
                      WHERE d.event_id = e.id)
     AND NOT EXISTS (
       SELECT 1
         FROM app_private.workflow_step s
         JOIN app_private.workflow_run r ON r.id = s.run_id
        WHERE s.status = 'parked'
          AND s.await_served_at IS NULL
          AND r.status NOT IN ('succeeded', 'failed', 'cancelled', 'stopped')
          AND s.await_event = e.name || '@' || e.version);
  RETURN pg_catalog.cardinality(victims);
END $fn$;

COMMENT ON FUNCTION app_private.connector_delivery_prune(timestamptz, integer) IS
  'Deletes delivered and dead outbound deliveries that ended before a horizon '
  'the OPERATOR states, then the events older than it that no delivery and no '
  'parked wait of a live run names, and returns how many DELIVERIES it removed '
  '(ADR 0248). Never a pending delivery. Granted to nobody; nothing calls it on '
  'a schedule.';

-- ---------------------------------------------------------------------------
-- The agent prune
-- ---------------------------------------------------------------------------
--
-- A revoked agent that no run and no connector names, last changed before the
-- horizon. `updated_at` moves on every status change (0025), so it is no
-- earlier than the revocation. Its credentials and quota go by their own `ON
-- DELETE CASCADE` (0011, 0028); its audit and idempotency rows keep the id, the
-- audit's convention (they carry no foreign key). **A revoked agent is dormant,
-- not dead** -- `auth_rotate_agent_secret` (0025) returns the SAME id to
-- `active` -- so this is the operator's decision that it will not come back,
-- stated with a horizon.
CREATE FUNCTION app_private.agent_prune(
  p_before timestamptz,
  p_limit  integer DEFAULT NULL
) RETURNS bigint
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  victims uuid[];
BEGIN
  IF p_before IS NULL THEN
    RAISE EXCEPTION 'AP422: a retention horizon is required'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_before > pg_catalog.now() THEN
    RAISE EXCEPTION 'AP422: a retention horizon must be in the past'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_limit IS NOT NULL AND p_limit < 1 THEN
    RAISE EXCEPTION 'AP422: a prune bound is at least one row'
      USING ERRCODE = 'PT422';
  END IF;

  SELECT pg_catalog.array_agg(q.id) INTO victims
    FROM (SELECT a.id
            FROM app_private.agents a
           WHERE a.status = 'revoked'
             AND a.updated_at < p_before
             AND NOT EXISTS (SELECT 1 FROM app_private.workflow_run r
                              WHERE r.agent_id = a.id)
             AND NOT EXISTS (SELECT 1 FROM app_private.connector c
                              WHERE c.agent_id = a.id)
           ORDER BY a.updated_at
           LIMIT p_limit) q;
  IF victims IS NULL THEN
    RETURN 0;
  END IF;

  DELETE FROM app_private.agents WHERE id = ANY (victims);
  RETURN pg_catalog.cardinality(victims);
END $fn$;

COMMENT ON FUNCTION app_private.agent_prune(timestamptz, integer) IS
  'Deletes revoked agents last changed before a horizon the OPERATOR states that '
  'no run and no connector names, with their credentials and quota (CASCADE), '
  'and returns how many it removed (ADR 0248). Never an active agent. Audit and '
  'idempotency rows keep the id. Granted to nobody; nothing calls it on a '
  'schedule.';

-- ---------------------------------------------------------------------------
-- The reading (D1985)
-- ---------------------------------------------------------------------------
--
-- One row per prunable relation -- its rows and its oldest time -- and one row
-- counting the pending approvals on ended runs, which is what the withdrawal
-- exists to keep at zero. `bin/record.sh --project KEY size` prints it, as the
-- superuser through the container, before and after every prune.
--
-- **Granted to nobody**, unlike 0033's `agent_record_size()`: that one adds no
-- audience because `auth_service` already pages through the audit, but no
-- request-reachable identity reads the ten Stage 4 tables whole, and the counts
-- of a record nobody reaches are the operator's. The doctor does not read it:
-- its twelve checks are positional, and one reader per question (D1985).
CREATE FUNCTION app_private.record_size()
  RETURNS TABLE (
    relation  text,
    row_count bigint,
    oldest    timestamptz
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
  SELECT 'agent_audit', pg_catalog.count(*), pg_catalog.min(started_at)
    FROM app_private.agent_audit
  UNION ALL
  SELECT 'agent_idempotency', pg_catalog.count(*), pg_catalog.min(created_at)
    FROM app_private.agent_idempotency
  UNION ALL
  SELECT 'workflow_run', pg_catalog.count(*), pg_catalog.min(created_at)
    FROM app_private.workflow_run
  UNION ALL
  SELECT 'workflow_step', pg_catalog.count(*), pg_catalog.min(started_at)
    FROM app_private.workflow_step
  UNION ALL
  SELECT 'workflow_attempt', pg_catalog.count(*), pg_catalog.min(recorded_at)
    FROM app_private.workflow_attempt
  UNION ALL
  SELECT 'workflow_approval', pg_catalog.count(*), pg_catalog.min(requested_at)
    FROM app_private.workflow_approval
  UNION ALL
  SELECT 'connector_event', pg_catalog.count(*), pg_catalog.min(emitted_at)
    FROM app_private.connector_event
  UNION ALL
  SELECT 'connector_delivery', pg_catalog.count(*), pg_catalog.min(created_at)
    FROM app_private.connector_delivery
  UNION ALL
  SELECT 'connector_receipt', pg_catalog.count(*), pg_catalog.min(received_at)
    FROM app_private.connector_receipt
  UNION ALL
  SELECT 'agents (revoked)', pg_catalog.count(*), pg_catalog.min(updated_at)
    FROM app_private.agents WHERE status = 'revoked'
  UNION ALL
  SELECT 'workflow_approval (pending on an ended run)', pg_catalog.count(*),
         pg_catalog.min(a.requested_at)
    FROM app_private.workflow_approval a
    JOIN app_private.workflow_run r ON r.id = a.run_id
   WHERE a.status = 'pending'
     AND r.status IN ('succeeded', 'failed', 'cancelled', 'stopped')
$fn$;

COMMENT ON FUNCTION app_private.record_size() IS
  'How much record this deployment carries and how far back it goes, one row '
  'per prunable relation plus the pending approvals on ended runs (ADR 0248). '
  'No verdict: nobody has measured a size at which a deployment is unwell '
  '(D1441). Granted to nobody; bin/record.sh reads it as the superuser.';

-- ---------------------------------------------------------------------------
-- The grants, and the four that are absent
-- ---------------------------------------------------------------------------
--
-- `REVOKE ALL FROM PUBLIC` on all five for 0020's reason (D57, D262): a new
-- function is executable by PUBLIC the moment it exists. There is no GRANT for
-- any prune or for the size reading, and that absence is the decision. The one
-- grant is the withdrawal's, to the role its caller runs as.
REVOKE ALL ON FUNCTION app_private.workflow_withdraw_ended_approvals() FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_run_prune(timestamptz, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_delivery_prune(timestamptz, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.agent_prune(timestamptz, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.record_size() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_private.workflow_withdraw_ended_approvals() TO {{auth_service}};

RESET ROLE;

-- Nothing in `api` moved, so no NOTIFY: no table, no column and no `api` object
-- is created here, and `app_private` is not the exposed schema.

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

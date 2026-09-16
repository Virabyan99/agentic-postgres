-- migrate:up
-- What the agent record keeps, and what an operator must do to make a row
-- disappear (ADR 0213, D1255).
--
-- Three released migrations say this table grows without bound and none of them
-- decided anything about it. 0020: *"What is NOT here: retention. Nothing prunes
-- `app_private.agent_audit`, exactly as nothing prunes secret generations."*
-- 0032 repeats it verbatim one column later. 0028 solved its own case by
-- keeping one row per agent and wrote down that the answer does not generalise.
-- ADR 0135, ADR 0142 and ADR 0181 each name retention in their consequences and
-- each leave it to the next run. This is the next run.
--
-- ---------------------------------------------------------------------------
-- What this migration does NOT do, and it is the larger half
-- ---------------------------------------------------------------------------
--
-- **Nothing here deletes a row.** There is no timer, no trigger, no scheduled
-- job, no `ON DELETE` rule and no default horizon. A migration that silently
-- deleted an audit record would destroy the evidence ADR 0135 exists to keep,
-- on a schedule nobody chose, and an operator would learn that it happened by
-- looking for a row that is gone.
--
-- What it adds is two functions that perform a deletion **when an operator asks
-- for one, with a horizon the operator states**, and the counts an operator
-- needs to decide whether to ask. `bin/doctor.sh --project <key>` reads those
-- counts as its eleventh check.
--
-- ---------------------------------------------------------------------------
-- The grant, and why it is to nobody
-- ---------------------------------------------------------------------------
--
-- **Measured in rig 28b**, on a cluster carrying every released migration and
-- the example project's set, with history in both tables: the ACL on both
-- `app_private.agent_audit` and `app_private.agent_idempotency` is the object
-- owner's and nobody else's, and a `DELETE` attempted by `SET ROLE` into
-- `auth_service`, `agent_writer`, `agent_reader` and `authenticated` is refused
-- with *permission denied for table* in all four.
--
-- So granting these functions to nobody **preserves the posture exactly** rather
-- than narrowing it: today no reachable identity can delete a row, and after
-- this migration no reachable identity can delete a row. A `SECURITY DEFINER`
-- function granted to `auth_service` -- the only candidate, since it is the
-- audit record's one reader (ADR 0142) -- would put a delete authority behind
-- an identity that is reachable over HTTP, which is 0020's reason for refusing
-- to put a DELETE path in the reader and is not weakened by the delete being
-- one function further away.
--
-- The functions are therefore executable by the object owner and by a superuser
-- and by nothing else. The hand that reaches them is the hand that already holds
-- `docker exec ... psql -U postgres` on the host: a human at a TTY, running one
-- statement, reading what it returns. That is the whole of the retention policy
-- this release ships, and ADR 0213 says why a smaller answer would have been a
-- worse one.
--
-- ---------------------------------------------------------------------------
-- The two tables are NOT the same question, and rig 28b is why
-- ---------------------------------------------------------------------------
--
-- `app_private.agent_audit` is evidence. Deleting an old row loses history and
-- nothing else: no live behaviour depends on a row being present, the table
-- carries no foreign key in either direction (measured: the only FK among the
-- three agent tables is `agent_quota.agent_id`, `ON DELETE CASCADE` to
-- `agents`), and the reader returns a page of what remains.
--
-- `app_private.agent_idempotency` is a **live guarantee**, and pruning it is a
-- correctness decision wearing a disk decision's clothes. Measured in rig 28b,
-- with the control in the same run: a write replayed with its claim still
-- present is deduplicated -- `app.notes` stays at one row -- and the same write
-- replayed after the claim is deleted **writes a second row and reports
-- success**. No error, no signal, nothing an operator or a caller could read.
-- At-most-once becomes at-least-once for every key older than the horizon, which
-- is the exact failure 0029 was written to prevent.
--
-- **And there is no safe subset.** The obvious one -- prune the claims of agents
-- that are no longer active -- does not survive its own measurement:
-- `auth_rotate_agent_secret` (0025) clears a revocation and returns the SAME
-- agent id to `active`, so a revoked agent's keys are dormant rather than dead.
-- There is no predicate over this table that means *this claim can never be
-- replayed*, so there is no prune of it that is free. `agent_idempotency_prune`
-- exists so that an operator who has decided to accept the downgrade can perform
-- it in one statement that says what it did, rather than by hand against a table
-- whose meaning is not obvious from its columns.
--
-- ---------------------------------------------------------------------------
-- Both prunes are sequential scans, and no index is added
-- ---------------------------------------------------------------------------
--
-- Measured: `EXPLAIN` on `DELETE FROM app_private.agent_audit WHERE started_at <
-- ...` is a `Seq Scan`, and so is the idempotency prune by `created_at`. 0019's
-- two indexes are `(owner_id, started_at DESC)` and `(agent_id, started_at
-- DESC)` -- built for the reader, neither leading with the timestamp -- and
-- `agent_idempotency` has only its primary key.
--
-- **No index is added here**, deliberately. 0019 wrote *"Both indexes exist for
-- that one reader; neither is speculative"*, and a third index would be paid on
-- every write the plane makes to buy a scan for an operation performed by hand,
-- rarely, at a moment the operator chose -- and a prune that removes most of a
-- table reads most of it whatever the plan says.
--
-- **And the scan is not what costs**, measured rather than assumed: on a cluster
-- carrying 20,004 audit rows spread over fourteen days, the unbounded prune
-- removed 9,921 of them in 141 ms and a bounded one removed 500 in 147 ms. The
-- bounded form is not the faster one -- the `ctid` subquery pays for itself --
-- which is the opposite of what this file said before the rig ran (D1461).
--
-- ---------------------------------------------------------------------------
-- The arity, decided once (ADR 0175)
-- ---------------------------------------------------------------------------
--
-- Two arguments each, and the second is the bound on one call. A released
-- function's argument list is expensive to move, and both of these are reachable
-- only by a hand that can also read this file.
--
-- **`p_limit` bounds how many rows one transaction touches, not how long it
-- takes**, and that distinction is the measurement's and not this file's
-- original guess. An unbounded prune takes a `ROW EXCLUSIVE` lock and a tuple
-- lock on every row it deletes, and holds them until it commits; on a table
-- nobody has pruned since the deployment was created, that is every row older
-- than the horizon at once, and the operator who most wants to prune is the one
-- whose table is largest. A bounded call returns the number it removed, so
-- *call it again until it returns zero* is a procedure an operator can run
-- without guessing at a number -- and each pass commits.
--
-- `NULL` means unbounded, which is the shape `auth_list_agent_audit`'s two
-- filters already use in this schema.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The audit record
-- ---------------------------------------------------------------------------
--
-- `p_before` is required and must be in the past. Both refusals are the same
-- kind of guard and neither is defensive decoration:
--
-- * a `NULL` horizon compared with `<` matches nothing, so the function would
--   return 0 and an operator would read *there was nothing to prune* when what
--   happened is *you did not say from when*. That is D600's shape at the call
--   site -- a value that looks measured and is not.
-- * a horizon in the future deletes rows written between the moment the operator
--   formed the intent and the moment the statement ran, including rows written
--   by calls that are still in flight. Refusing it costs nothing an operator
--   wanted.
--
-- `PT422` for both, because the argument is the thing that is wrong. The message
-- carries no caller value: the horizon is the operator's own and printing it
-- back adds nothing, and this file follows 0007's rule that nothing
-- caller-reachable carries a HINT or a DETAIL with a value in it.
CREATE FUNCTION app_private.agent_audit_prune(
  p_before timestamptz,
  p_limit  integer DEFAULT NULL
) RETURNS bigint
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  removed bigint;
BEGIN
  IF p_before IS NULL THEN
    RAISE EXCEPTION 'AP422: a retention horizon is required'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_before > pg_catalog.now() THEN
    RAISE EXCEPTION 'AP422: a retention horizon is in the past'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_limit IS NOT NULL AND p_limit < 1 THEN
    RAISE EXCEPTION 'AP422: a prune bound is at least one row'
      USING ERRCODE = 'PT422';
  END IF;

  -- The bounded form selects the victims first and deletes by `ctid`, which is
  -- how a `LIMIT` is applied to a `DELETE` in PostgreSQL at all -- `DELETE ...
  -- LIMIT` is not accepted, measured on the pinned 18.4. `ctid` is safe here for
  -- the reason it usually is not: the subquery and the delete are one statement
  -- in one snapshot, so no concurrent update can move a row between them.
  -- `started_at` is the row's own opening time; a row
  -- whose call never completed carries a NULL `completed_at` and is pruned on
  -- the same footing as one that did, because an abandoned attempt is as much
  -- of the record as a served one (0019's table comment).
  IF p_limit IS NULL THEN
    DELETE FROM app_private.agent_audit WHERE started_at < p_before;
  ELSE
    DELETE FROM app_private.agent_audit
    WHERE ctid IN (
      SELECT a.ctid FROM app_private.agent_audit a
      WHERE a.started_at < p_before
      LIMIT p_limit
    );
  END IF;
  GET DIAGNOSTICS removed = ROW_COUNT;
  RETURN removed;
END $fn$;

COMMENT ON FUNCTION app_private.agent_audit_prune(timestamptz, integer) IS
  'Deletes agent audit rows older than a horizon the OPERATOR states, and '
  'returns how many it removed (ADR 0213). Granted to nobody: the object owner '
  'and a superuser can execute it and no request role can reach it, which is '
  'the posture the table already had. Nothing calls this on a schedule -- an '
  'audit row disappears because a person decided it should. With p_limit, call '
  'it again until it returns zero.';

-- ---------------------------------------------------------------------------
-- The idempotency claims
-- ---------------------------------------------------------------------------
--
-- Same shape, different meaning, and the comment says so where an operator will
-- read it rather than only in the ADR. This is the function whose effect is not
-- visible in its own result: it returns a count of rows removed, and what it
-- actually did is re-arm every one of those keys.
CREATE FUNCTION app_private.agent_idempotency_prune(
  p_before timestamptz,
  p_limit  integer DEFAULT NULL
) RETURNS bigint
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  removed bigint;
BEGIN
  IF p_before IS NULL THEN
    RAISE EXCEPTION 'AP422: a retention horizon is required'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_before > pg_catalog.now() THEN
    RAISE EXCEPTION 'AP422: a retention horizon is in the past'
      USING ERRCODE = 'PT422';
  END IF;
  IF p_limit IS NOT NULL AND p_limit < 1 THEN
    RAISE EXCEPTION 'AP422: a prune bound is at least one row'
      USING ERRCODE = 'PT422';
  END IF;

  IF p_limit IS NULL THEN
    DELETE FROM app_private.agent_idempotency WHERE created_at < p_before;
  ELSE
    DELETE FROM app_private.agent_idempotency
    WHERE ctid IN (
      SELECT k.ctid FROM app_private.agent_idempotency k
      WHERE k.created_at < p_before
      LIMIT p_limit
    );
  END IF;
  GET DIAGNOSTICS removed = ROW_COUNT;
  RETURN removed;
END $fn$;

COMMENT ON FUNCTION app_private.agent_idempotency_prune(timestamptz, integer) IS
  'Deletes idempotency claims older than a horizon the OPERATOR states, and '
  'returns how many it removed (ADR 0213). EVERY ROW THIS REMOVES RE-ARMS ITS '
  'KEY: a caller replaying a pruned key performs the write a second time and is '
  'told it succeeded, with no error on either side. Measured in rig 28b with '
  'the control -- the same replay is deduplicated while the claim is present. '
  'At-most-once holds only for the window the operator keeps, and there is no '
  'predicate that means a claim can never be replayed: a revoked agent returns '
  'to active with the same id when its secret is rotated (0025). Granted to '
  'nobody, and nothing calls it on a schedule.';

-- ---------------------------------------------------------------------------
-- The reading
-- ---------------------------------------------------------------------------
--
-- What `bin/doctor.sh --project <key>` reads. One row, four numbers and two
-- timestamps, so that growth is a thing an operator SEES rather than a thing
-- they are told about in a migration comment they will never open.
--
-- **It is `STABLE` and it deletes nothing**, so it is granted to the audit
-- record's existing reader as well: `auth_service` already reads whole audit
-- rows through `auth_list_agent_audit` (ADR 0142, 0020's grant), so a count of
-- the rows it can already page through adds no audience and no fact. What it
-- does not do is publish anything into `api` -- the audit record is published to
-- nobody, and an object in `api` is an object the generated document can name
-- (0020's reason, unchanged).
--
-- The doctor does not need the grant -- it reads as the superuser, over the
-- container socket, exactly as its other probes do -- and the grant is here so
-- that the count is available to the identity that already holds the rows,
-- rather than only to root.
CREATE FUNCTION app_private.agent_record_size()
  RETURNS TABLE (
    audit_rows            bigint,
    audit_oldest          timestamptz,
    idempotency_rows      bigint,
    idempotency_oldest    timestamptz
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
  SELECT
    (SELECT pg_catalog.count(*) FROM app_private.agent_audit),
    (SELECT pg_catalog.min(started_at) FROM app_private.agent_audit),
    (SELECT pg_catalog.count(*) FROM app_private.agent_idempotency),
    (SELECT pg_catalog.min(created_at) FROM app_private.agent_idempotency)
$fn$;

COMMENT ON FUNCTION app_private.agent_record_size() IS
  'How much agent record this deployment is carrying, and how far back it goes '
  '(ADR 0213). Four values, no verdict: nobody has measured a row count at '
  'which this deployment is unwell, and a threshold invented in the command '
  'that runs as root on production could fail a host that works (D1441). The '
  'doctor reports these numbers and reports that it could not read them, and '
  'reports nothing in between.';

-- ---------------------------------------------------------------------------
-- The grants, and the two that are absent
-- ---------------------------------------------------------------------------
--
-- `REVOKE ALL FROM PUBLIC` on all three for 0020's reason (D57, D262): a new
-- function is executable by PUBLIC the moment it exists, so a function created
-- and not revoked is granted to every role in the cluster. There is no `GRANT`
-- for either prune, and that absence is the decision -- stated here so that a
-- reader looking for the grant finds the reason instead of a gap.
REVOKE ALL ON FUNCTION
  app_private.agent_audit_prune(timestamptz, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  app_private.agent_idempotency_prune(timestamptz, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.agent_record_size() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_private.agent_record_size() TO {{auth_service}};

RESET ROLE;

-- Nothing in `api` moved, so no NOTIFY: 0020's and 0032's closing note applies
-- unchanged. `app_private` is not the exposed schema, and announcing a schema
-- reload for a change PostgREST cannot see is a notification a reader would
-- have to explain.

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

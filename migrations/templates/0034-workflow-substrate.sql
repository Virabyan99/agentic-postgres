-- migrate:up
-- The durable step substrate: four tables nobody may read, and nine functions
-- (ADR 0227, ADR 0226, ADR 0228, ADR 0229).
--
-- Three released migrations named a workflow and refused to build one. 0019's
-- write path raises `approval_required` with the sentence *"a workflow needs
-- durable pending state, a second principal and a notification plane, none of
-- which exists"*, and `mcp_errors.py:51-55` repeats it. This migration builds
-- the first of those three. The second principal is Session 33's and the
-- notification plane is Session 34's, and the refusal stays a refusal until
-- both arrive -- `workflow_definition`'s compiler refuses a capability whose
-- tool declares `requires_approval`, so nothing here routes around it.
--
-- ---------------------------------------------------------------------------
-- What this migration does NOT do
-- ---------------------------------------------------------------------------
--
-- **No RLS, and that is a decision with a measurement behind it** (D1647, rig
-- 32d). The stage plan asked for `FORCE ROW LEVEL SECURITY` on these tables.
-- No `app_private` table in this tree has RLS: `FORCE ROW LEVEL SECURITY`
-- appears only on `app.notes` and `app.tasks` (0003, 0007), and the posture
-- every table in this schema has is *no request role holds any table
-- privilege* (0019), with access through `SECURITY DEFINER` functions.
--
-- FORCE RLS applies to a table's OWNER, which is the role every definer
-- function here runs as. Rig 32d measured what that means: a throwaway
-- `app_private` table under `FORCE ROW LEVEL SECURITY` with no policy, read by
-- a definer function granted to `auth_service`, **returns zero rows and exits
-- 0**. It does not raise. A forced table with no policy fails SILENTLY, in the
-- reassuring direction, which is the worst shape a control can have -- and a
-- permissive policy for the owner would be a policy nothing else evaluates.
--
-- The same rig measured the posture this file adopts instead: the definer
-- function reads every row as `auth_service`; a direct `SELECT` as
-- `auth_service` is *permission denied for table*; and `agent_writer`,
-- `agent_reader`, `authenticated`, `anon` and `storage_service` are each
-- *permission denied for function*.
--
-- **Nothing here is on a timer.** No trigger, no schedule, no `ON DELETE`
-- rule. A step moves because a worker claimed it, and the worker is a loop in
-- the auth process (ADR 0226) that asks for work rather than being pushed it.
--
-- **Nothing here is in `api`.** No schema reachable over HTTP is touched, so
-- there is no `NOTIFY pgrst` -- 0033's closing note applies unchanged, and
-- announcing a schema reload for a change PostgREST cannot see is a
-- notification a reader would have to explain.
--
-- **No new errcode.** The refusals below use `PT403`, `PT404` and `PT409`,
-- which the release already raises. These functions are called by the worker
-- over psycopg, never through PostgREST, so none of them enters
-- `mcp_errors.UPSTREAM_WRITE_REFUSALS` -- and that map's guard is a SUBSET
-- check over every template, which only grows more permissive as templates add
-- codes.
--
-- ---------------------------------------------------------------------------
-- The lease, and which half of it is the correctness mechanism
-- ---------------------------------------------------------------------------
--
-- Both halves of ADR 0104 carry forward from 0016 unchanged, and rig 32e
-- re-measured them for a step across two concurrent sessions:
--
--   * the LEASE PREDICATE is the correctness mechanism. The tool call happens
--     outside the claim's transaction, so a claim has to survive the
--     transaction that made it, and a row lock is released at COMMIT and at
--     crash.
--   * `FOR UPDATE SKIP LOCKED` is throughput and nothing else.
--
-- Measured: a holder inside an open claim transaction is skipped; after it
-- commits and while its lease stands, a second claimant takes NOTHING; once
-- the lease expires the second claimant takes the row with `attempt` 2 and a
-- new holder; and the first holder's late finish, scoped `WHERE claimed_by =
-- <it>`, updates 0 rows. The control -- the same statement with the lease
-- predicate removed -- lets a second claimant take a row thirty seconds into a
-- thirty-second lease.
--
-- **`pg_catalog.now()` is the TRANSACTION START time**, not the statement
-- time, and the claim and the reclaim predicate therefore read the same clock.
-- That is what makes work done inside a claim transaction irrelevant to the
-- lease it just took. Rig 32e found this by taking a 2 s lease and sleeping
-- 3 s inside the transaction, which expired the lease before the commit.
--
-- ---------------------------------------------------------------------------
-- The key, and what a replay actually is
-- ---------------------------------------------------------------------------
--
-- **One key per (run, step), never per attempt** (D1646, ADR 0181). It is
-- derived at enqueue and stored on the step row, so every attempt presents the
-- same bytes. A key per attempt would make a retry after a crash write a
-- SECOND row -- the defect 0029 exists to prevent, arriving through the door
-- 0029 left open.
--
-- Rig 32c measured the semantics through `api.create_note` on a cluster
-- carrying every released migration: the same key with the same arguments
-- twice returns the SAME row id, `app.notes` holds ONE row, `replay_count` is
-- 1, and the audit reads `committed` then `replayed`. The same key with
-- different arguments is `AP412`. A fresh key writes a second row. **A replay
-- is re-read, not refused**, and `PT412` is therefore the control rather than
-- the proof.
--
-- The key's shape is 0029's own: `'wf-' || run_id || '-' || step name` is 40
-- to 103 printable ASCII characters, inside `^[\x21-\x7e]{8,255}$`, and the
-- CHECK below is the same pattern so a key this function derives cannot fail
-- the header parser that will later read it.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The vocabularies
-- ---------------------------------------------------------------------------
--
-- Enums rather than text with a CHECK, for 0019's reason: the database refuses
-- an unknown value at the column, so a typo in the worker is a failed
-- transaction rather than a row nobody can classify.
--
-- `stopped` is a run status distinct from `failed` because the two are
-- different operator actions: `failed` means a step refused and the run is
-- over, `stopped` means the agent stopped being able to act and the run is
-- over. Collapsing them would hide the one an operator can fix by
-- reauthorising an agent.
CREATE TYPE app_private.workflow_run_status AS ENUM
  ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'stopped');

CREATE TYPE app_private.workflow_step_status AS ENUM
  ('queued', 'claimed', 'parked', 'succeeded', 'failed');

-- `replayed` is here and the WORKER never writes it, which is stated rather
-- than left to be discovered (D1671, ADR 0195). The plane's result for a write
-- is `{tool, row_count, row, dry_run}` (`mcp_tools.py:644-652`) and `row_count`
-- is the row count of a composite-returning function, which is 1 either way --
-- so a replay and a first write are INDISTINGUISHABLE to the caller. Rig 32c
-- confirmed it: both calls returned the same row id. The word `replayed` lives
-- in `app_private.agent_audit.outcome` on the `database`-source row, which no
-- HTTP result carries.
--
-- The value is kept because the SUBSTRATE may one day be told (an operator
-- reconciling by hand, or Session 33's provenance reader joining the audit by
-- request id), and because deleting a value from an enum needs a migration
-- while leaving an unused one costs nothing. What it must not become is a
-- value the worker guesses at.
CREATE TYPE app_private.workflow_step_outcome AS ENUM
  ('succeeded', 'replayed', 'dry_run', 'failed', 'refused', 'token_refused', 'abandoned');

-- ---------------------------------------------------------------------------
-- The definition
-- ---------------------------------------------------------------------------
--
-- A reviewed project artefact, installed by a deploy and immutable per
-- `(name, version)` (ADR 0228). `body` is the COMPILED document -- steps
-- already resolved to their tools against the project's lock -- not the YAML,
-- because the YAML is a source file and the compiled body is what a run
-- executes. `source_sha256` is over the YAML bytes, so re-installing a name
-- and version whose source changed is a conflict rather than a silent
-- overwrite (D912's rule for a definition).
--
-- `lock_tools_sha256` is a RECORD, never a gate. The loop holds no lock and
-- the plane enforces the lock on every call, so comparing it at run time would
-- be a second authority over one rule. `status` reports it so a reader can see
-- whether the lock moved since `validate` ran.
CREATE TABLE app_private.workflow_definition (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name              text        NOT NULL CHECK (name ~ '^[a-z][a-z0-9-]{0,62}$'),
  version           integer     NOT NULL CHECK (version >= 1),
  body              jsonb       NOT NULL,
  source_sha256     text        NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
  lock_tools_sha256 text        NOT NULL CHECK (lock_tools_sha256 ~ '^[0-9a-f]{64}$'),
  required_scopes   text[]      NOT NULL,
  installed_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (name, version)
);

COMMENT ON TABLE app_private.workflow_definition IS
  'A compiled workflow, installed by a deploy and immutable per (name, '
  'version) (ADR 0228). The body is the COMPILED document, with every step '
  'already resolved to the tool that serves its capability; source_sha256 is '
  'over the YAML the compiler read, so re-installing a changed source under an '
  'existing name and version is a conflict rather than an overwrite. '
  'lock_tools_sha256 is a record of what validate compiled against and is '
  'never compared at run time: the plane enforces the lock on every call.';

-- ---------------------------------------------------------------------------
-- The run
-- ---------------------------------------------------------------------------
--
-- `agent_id` is a real foreign key into `app_private.agents`, unlike
-- `app.notes.owner_id` which predates that table and holds a claim value
-- (0011's comment). A run with no agent is an authority nobody is accountable
-- for, and this table is where the agent is the whole point.
--
-- `owner_id` is copied from the agent row at enqueue rather than joined at
-- read time. The agent's owner is what the audit row will carry, and a run
-- that outlived a change of owner should report the owner it acted for.
--
-- `cancel_requested_at` rather than a `cancelling` status: a cancel arriving
-- while a step is in flight cannot stop that step -- the tool call is already
-- upstream -- so what it does is record an intent the NEXT claim honours. A
-- status would claim the run had already stopped.
CREATE TABLE app_private.workflow_run (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  definition_id       uuid        NOT NULL REFERENCES app_private.workflow_definition (id),
  agent_id            uuid        NOT NULL REFERENCES app_private.agents (id),
  owner_id            uuid        NOT NULL,
  input               jsonb       NOT NULL DEFAULT '{}'::jsonb,
  dry_run             boolean     NOT NULL DEFAULT false,
  status              app_private.workflow_run_status NOT NULL DEFAULT 'queued',
  stopped_reason      text,
  timeout_seconds     integer     NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 3600),
  cancel_requested_at timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  started_at          timestamptz,
  finished_at         timestamptz
);

-- The claim's own ordering, and the only index this table needs. The claim
-- reads runs in `('queued','running')` oldest first; nothing else queries it
-- by anything but the primary key.
CREATE INDEX workflow_run_status_created_idx
  ON app_private.workflow_run (status, created_at);

COMMENT ON TABLE app_private.workflow_run IS
  'One execution of a definition, by one agent, holding nothing that agent '
  'does not hold (ADR 0229). cancel_requested_at is an intent the next claim '
  'honours rather than a status, because a cancel cannot recall a tool call '
  'already upstream. stopped is distinguished from failed: failed means a step '
  'refused, stopped means the agent stopped being able to act.';

-- ---------------------------------------------------------------------------
-- The step
-- ---------------------------------------------------------------------------
--
-- `idempotency_key` carries 0029's own CHECK, so a key this schema derives
-- cannot fail the header parser that reads it back. Both uniqueness
-- constraints exist: `(run_id, position)` is the claim's ordering and
-- `(run_id, name)` is what makes a step reference by name resolvable and
-- what makes the derived key unique within its run.
--
-- `claimed_by`, `lease_until` and `resume_after` are all NULL for a step
-- nobody holds, and a finished step keeps its `request_id`, `outcome` and
-- `reason` -- the step row IS the record of what happened, and correlation to
-- the plane's audit is `request_id` on both sides (D1667).
CREATE TABLE app_private.workflow_step (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          uuid        NOT NULL REFERENCES app_private.workflow_run (id),
  position        integer     NOT NULL CHECK (position >= 1),
  name            text        NOT NULL CHECK (name ~ '^[a-z][a-z0-9_-]{0,62}$'),
  status          app_private.workflow_step_status NOT NULL DEFAULT 'queued',
  attempt         integer     NOT NULL DEFAULT 0 CHECK (attempt >= 0),
  retry_max       integer     NOT NULL CHECK (retry_max BETWEEN 0 AND 5),
  backoff_seconds integer     NOT NULL CHECK (backoff_seconds BETWEEN 1 AND 300),
  timeout_seconds integer     NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 600),
  idempotency_key text        NOT NULL CHECK (idempotency_key ~ '^[\x21-\x7e]{8,255}$'),
  claimed_by      text,
  lease_until     timestamptz,
  resume_after    timestamptz,
  request_id      uuid,
  outcome         app_private.workflow_step_outcome,
  reason          text,
  result          jsonb,
  started_at      timestamptz,
  finished_at     timestamptz,
  UNIQUE (run_id, position),
  UNIQUE (run_id, name)
);

-- The claim's predicate reads `status` and `resume_after` together: a parked
-- step becomes claimable at a time, and a claimed one becomes claimable when
-- its lease expires.
CREATE INDEX workflow_step_status_resume_idx
  ON app_private.workflow_step (status, resume_after);

COMMENT ON TABLE app_private.workflow_step IS
  'One step of one run, and the lease that makes a crash survivable (ADR '
  '0227). idempotency_key is derived at enqueue from the run and the step and '
  'never from the attempt, so every attempt presents the same bytes and the '
  'upstream deduplicates a retry rather than writing a second row (ADR 0181). '
  'request_id is minted per attempt and is what correlates this row to '
  'app_private.agent_audit.';

-- ---------------------------------------------------------------------------
-- The heartbeat
-- ---------------------------------------------------------------------------
--
-- One row, enforced by a boolean primary key with a CHECK that it is true --
-- the standard singleton, and it is a singleton because there is exactly one
-- loop per project by construction: the auth image's entrypoint is one uvicorn
-- process with no `--workers` (measured, rig 32a: `docker top` reads one
-- process), and the task is created once in its lifespan.
--
-- `holder` is `<nodename>:<pid>:<monotonic tick>` and `started_at` is reset
-- when it changes, so **a restart is visible as a NEW holder**. That is what
-- the `worker-restart` rehearsal reads, and it is the reason the holder is not
-- just a hostname: two containers on one host would share one.
CREATE TABLE app_private.workflow_worker (
  singleton  boolean     PRIMARY KEY DEFAULT true CHECK (singleton),
  holder     text        NOT NULL CHECK (holder <> ''),
  started_at timestamptz NOT NULL,
  seen_at    timestamptz NOT NULL
);

COMMENT ON TABLE app_private.workflow_worker IS
  'One row: which loop is running and when it last asked for work. A restart '
  'is visible as a new holder, which is what the worker-restart rehearsal '
  'reads (ADR 0193, ADR 0226). It carries no URL, key, token or caller value '
  '-- a nodename, a pid and a monotonic tick.';

-- ---------------------------------------------------------------------------
-- Installing a definition, and the grant that is absent
-- ---------------------------------------------------------------------------
--
-- Re-installing an identical `(name, version, source_sha256)` returns the
-- existing id: a deploy is idempotent and re-running one must not be a
-- conflict. Re-installing the same name and version with a DIFFERENT source is
-- `PT409`, which refuses the deploy -- the migration-set discipline applied to
-- a definition (D912). Fixing a definition forward means a new version.
--
-- **Granted to nobody**, 0033's pattern. The deploy and `apg dev up` call it
-- as the bootstrap superuser through the container; a grant to `auth_service`
-- -- the only candidate, since that is the role the routes run as -- would put
-- a definition-writing authority behind an identity reachable over HTTP, which
-- is 0020's reason for keeping a DELETE out of the audit reader and is not
-- weakened by the write being a definition rather than a deletion.
CREATE FUNCTION app_private.workflow_install_definition(
  p_name              text,
  p_version           integer,
  p_body              jsonb,
  p_source_sha256     text,
  p_lock_tools_sha256 text,
  p_required_scopes   text[]
) RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  existing app_private.workflow_definition;
  new_id   uuid;
BEGIN
  SELECT * INTO existing
    FROM app_private.workflow_definition
   WHERE name = p_name AND version = p_version;

  IF FOUND THEN
    IF existing.source_sha256 <> p_source_sha256 THEN
      RAISE EXCEPTION
        'AP409: workflow definition % version % is installed with a different source',
        p_name, p_version
        USING ERRCODE = 'PT409',
              HINT = 'A definition is immutable once installed. Publish a new version.';
    END IF;
    RETURN existing.id;
  END IF;

  INSERT INTO app_private.workflow_definition
    (name, version, body, source_sha256, lock_tools_sha256, required_scopes)
  VALUES
    (p_name, p_version, p_body, p_source_sha256, p_lock_tools_sha256, p_required_scopes)
  RETURNING id INTO new_id;

  RETURN new_id;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_install_definition(
  text, integer, jsonb, text, text, text[]) IS
  'Installs one compiled definition, idempotently (ADR 0228). An identical '
  'source under an existing (name, version) returns the existing id; a '
  'different source raises PT409 and refuses the deploy. Granted to NOBODY: '
  'the deploy calls it as the bootstrap superuser, and a grant to the role the '
  'HTTP routes run as would put a definition-writing authority behind an '
  'identity reachable over the network.';

-- ---------------------------------------------------------------------------
-- Enqueueing a run
-- ---------------------------------------------------------------------------
--
-- **The agent's stored scopes are what authorise the run, not the token's**
-- (ADR 0229). A token carries the agent's scopes at issue; the row carries
-- them now, and the row is the authority the hook itself consults (0018). So
-- an agent whose authorisation was narrowed between minting a token and
-- starting a run is refused here, with the same containment test the compiler
-- used to compute `required_scopes` in the first place.
--
-- `scope_not_held` is the message, and the word is deliberate: it is one of
-- the nine denial boundaries (`mcp_errors.DENIAL_REASONS`), so the route can
-- map this refusal onto vocabulary the caller already reads rather than
-- inventing a tenth.
CREATE FUNCTION app_private.workflow_enqueue(
  p_agent   uuid,
  p_name    text,
  p_version integer,
  p_input   jsonb,
  p_dry_run boolean
) RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  agent      app_private.agents;
  definition app_private.workflow_definition;
  new_run    uuid;
  step       jsonb;
  ordinal    integer := 0;
BEGIN
  SELECT * INTO agent FROM app_private.agents WHERE id = p_agent;
  IF NOT FOUND OR agent.status <> 'active' THEN
    -- One refusal for "no such agent" and "not active", for 0013's reason: an
    -- agent that has been revoked must not be distinguishable from one that
    -- never existed.
    RAISE EXCEPTION 'AP403: this operation requires an active agent identity'
      USING ERRCODE = 'PT403';
  END IF;

  SELECT * INTO definition
    FROM app_private.workflow_definition
   WHERE name = p_name AND version = p_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no such definition'
      USING ERRCODE = 'PT404';
  END IF;

  IF NOT (definition.required_scopes <@ agent.scopes) THEN
    RAISE EXCEPTION 'AP403: scope_not_held'
      USING ERRCODE = 'PT403',
            HINT = 'The agent does not hold every scope this definition''s steps require.';
  END IF;

  INSERT INTO app_private.workflow_run
    (definition_id, agent_id, owner_id, input, dry_run, timeout_seconds)
  VALUES
    (definition.id, agent.id, agent.owner_id, coalesce(p_input, '{}'::jsonb), p_dry_run,
     (definition.body ->> 'timeout_seconds')::integer)
  RETURNING id INTO new_run;

  -- One step row per element of the compiled body, in the body's own order.
  -- The key is derived HERE and stored, which is what makes it per (run, step)
  -- rather than per attempt: the worker reads it off the row and never
  -- computes one.
  FOR step IN SELECT * FROM jsonb_array_elements(definition.body -> 'steps')
  LOOP
    ordinal := ordinal + 1;
    INSERT INTO app_private.workflow_step
      (run_id, position, name, retry_max, backoff_seconds, timeout_seconds, idempotency_key)
    VALUES
      (new_run,
       ordinal,
       step ->> 'name',
       coalesce((step -> 'retry' ->> 'max')::integer, 0),
       coalesce((step -> 'retry' ->> 'backoff_seconds')::integer, 30),
       (step ->> 'timeout_seconds')::integer,
       'wf-' || new_run::text || '-' || (step ->> 'name'));
  END LOOP;

  IF ordinal = 0 THEN
    RAISE EXCEPTION 'AP409: this definition compiles to no steps'
      USING ERRCODE = 'PT409';
  END IF;

  RETURN new_run;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_enqueue(uuid, text, integer, jsonb, boolean) IS
  'Starts one run as one agent, and derives one idempotency key per (run, '
  'step) (ADR 0227, ADR 0229). The agent''s STORED scopes authorise the run, '
  'not the token''s, so an agent narrowed between minting a token and starting '
  'a run is refused here. An unknown agent and a revoked one are one refusal, '
  'for 0013''s reason.';

-- ---------------------------------------------------------------------------
-- Claiming a step
-- ---------------------------------------------------------------------------
--
-- Three things in one transaction, in this order, and the order is the point:
--
--   1. cancels requested on runs with nothing in flight are applied. A run
--      whose step is claimed under an unexpired lease is left alone -- the
--      call is upstream and cancelling the run would report it stopped while
--      it was still happening.
--   2. runs past their own timeout are failed. Before the claim, so a run that
--      has overrun cannot take one more step.
--   3. ONE step is claimed.
--
-- The claim selects the lowest position of its run whose earlier positions are
-- all `succeeded` -- so a run is sequential by construction and no second
-- mechanism is needed to make it so.
--
-- **The caller supplies a MARGIN, not a lease** (D1687). The lease is
-- `s.timeout_seconds + p_lease_margin_seconds`, computed here, because the two
-- halves are known in two different places: the step's own timeout is in the
-- row this function is about to select, and the margin is a function of the
-- WORKER's HTTP client (`workflow_worker.lease_margin_seconds`). A caller
-- passing an absolute lease could not have read the step's timeout yet -- it
-- arrives in this function's own result -- so it would have to pass the
-- CEILING, 600 plus a margin, and a worker that died mid-call would leave its
-- step unclaimable for ten minutes. The margin is the only half a caller can
-- honestly know before the claim.
CREATE FUNCTION app_private.workflow_claim_step(
  p_holder               text,
  p_lease_margin_seconds integer
) RETURNS TABLE (
  step_id         uuid,
  run_id          uuid,
  step_position   integer,
  step_name       text,
  attempt         integer,
  -- **Returned, not only written** (D1686). The UPDATE below mints a fresh
  -- `request_id` for this attempt and the column's own comment calls it *what
  -- correlates this row to the plane's audit* -- which only holds if the
  -- caller can READ it and put it in the request's `X-Request-Id`. Writing it
  -- and withholding it would have left the worker minting a second id of its
  -- own, and the two sides of the correlation would have carried different
  -- values with nothing to say so.
  request_id      uuid,
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
BEGIN
  IF p_holder IS NULL OR p_holder = '' THEN
    RAISE EXCEPTION 'AP422: a claim requires a holder'
      USING ERRCODE = 'PT422';
  END IF;
  -- Zero is legal and negative is not: a margin of zero leases the step for
  -- exactly its own timeout, which is what a proof driving an expiry wants,
  -- and a negative one would lease it for less than the call it is about to
  -- make.
  IF p_lease_margin_seconds IS NULL OR p_lease_margin_seconds < 0 THEN
    RAISE EXCEPTION 'AP422: a lease margin is zero or more seconds'
      USING ERRCODE = 'PT422';
  END IF;

  UPDATE app_private.workflow_run r
     SET status = 'cancelled', finished_at = pg_catalog.now()
   WHERE r.cancel_requested_at IS NOT NULL
     AND r.status IN ('queued', 'running')
     AND NOT EXISTS (
           SELECT 1 FROM app_private.workflow_step s
            WHERE s.run_id = r.id
              AND s.status = 'claimed'
              AND s.lease_until >= pg_catalog.now());

  UPDATE app_private.workflow_run r
     SET status = 'failed',
         stopped_reason = 'timed_out',
         finished_at = pg_catalog.now()
   WHERE r.status = 'running'
     AND r.started_at IS NOT NULL
     AND r.started_at
         + pg_catalog.make_interval(secs => r.timeout_seconds) < pg_catalog.now();

  SELECT s.id INTO chosen
    FROM app_private.workflow_step s
    JOIN app_private.workflow_run r ON r.id = s.run_id
   WHERE r.status IN ('queued', 'running')
     AND r.cancel_requested_at IS NULL
     AND (
           s.status = 'queued'
        OR (s.status = 'parked' AND s.resume_after <= pg_catalog.now())
        OR (s.status = 'claimed' AND s.lease_until < pg_catalog.now())
         )
     AND NOT EXISTS (
           SELECT 1 FROM app_private.workflow_step earlier
            WHERE earlier.run_id = s.run_id
              AND earlier.position < s.position
              AND earlier.status <> 'succeeded')
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
         request_id = gen_random_uuid(),
         resume_after = NULL,
         started_at = coalesce(s.started_at, pg_catalog.now())
   WHERE s.id = chosen;

  UPDATE app_private.workflow_run r
     SET status = 'running',
         started_at = coalesce(r.started_at, pg_catalog.now())
    FROM app_private.workflow_step s
   WHERE s.id = chosen AND r.id = s.run_id AND r.status = 'queued';

  -- Every column qualified, and the two renamed ones are the reason the
  -- signature above does not simply mirror the table: `position` is a
  -- col_name_keyword and is a syntax error as a bare OUT parameter, and
  -- `name` is renamed beside it so the pair reads as one decision rather
  -- than as one workaround.
  RETURN QUERY
  SELECT s.id,
         s.run_id,
         s.position,
         s.name,
         s.attempt,
         s.request_id,
         r.agent_id,
         r.dry_run,
         (d.body -> 'steps') -> (s.position - 1),
         r.input,
         coalesce(
           (SELECT jsonb_object_agg(done.name, coalesce(done.result, 'null'::jsonb))
              FROM app_private.workflow_step done
             WHERE done.run_id = s.run_id AND done.status = 'succeeded'),
           '{}'::jsonb),
         s.timeout_seconds,
         s.idempotency_key
    FROM app_private.workflow_step s
    JOIN app_private.workflow_run r ON r.id = s.run_id
    JOIN app_private.workflow_definition d ON d.id = r.definition_id
   WHERE s.id = chosen;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_claim_step(text, integer) IS
  'Claims at most one step, and applies the two things that must happen before '
  'a claim: a requested cancel on a run with nothing in flight, and a run past '
  'its own timeout (ADR 0227). The returned position and name are '
  'step_position and step_name: `position` is a col_name_keyword and is a '
  'syntax error as a bare OUT parameter. The LEASE PREDICATE is the correctness '
  'mechanism and SKIP LOCKED is throughput (ADR 0104, rig 32e). A step is '
  'claimable only when every earlier position of its run has succeeded, which '
  'is what makes a run sequential without a second mechanism. The second '
  'argument is a MARGIN, not a lease: the lease is the step''s own '
  'timeout_seconds plus it, because the step''s timeout is in the row this '
  'function selects and the margin is a function of the caller''s HTTP client '
  '(D1687). A caller passing an absolute lease would have to pass the ceiling.';

-- ---------------------------------------------------------------------------
-- Finishing a step
-- ---------------------------------------------------------------------------
--
-- `WHERE claimed_by = p_holder` is the whole of the lease's safety, and zero
-- rows is `lease_lost` rather than an error -- `storage_finish_cleanup`'s rule
-- (0016, `storage_repository.py:216-230`). A worker whose lease expired while
-- its call was in flight has done real work and lost the row to a successor;
-- that is a fact to report, not a failure to raise.
--
-- Returns the RUN's new status, so the caller learns in one round trip whether
-- the run is over.
CREATE FUNCTION app_private.workflow_finish_step(
  p_step    uuid,
  p_holder  text,
  p_outcome app_private.workflow_step_outcome,
  p_result  jsonb,
  p_reason  text
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  target      app_private.workflow_step;
  run_status  app_private.workflow_run_status;
  unfinished  integer;
BEGIN
  UPDATE app_private.workflow_step s
     SET status = CASE
                    WHEN p_outcome IN ('succeeded', 'replayed', 'dry_run') THEN 'succeeded'
                    ELSE 'failed'
                  END::app_private.workflow_step_status,
         outcome = p_outcome,
         result = p_result,
         reason = p_reason,
         claimed_by = NULL,
         lease_until = NULL,
         finished_at = pg_catalog.now()
   WHERE s.id = p_step AND s.claimed_by = p_holder AND s.status = 'claimed'
  RETURNING * INTO target;

  IF NOT FOUND THEN
    RETURN 'lease_lost';
  END IF;

  IF p_outcome IN ('succeeded', 'replayed', 'dry_run') THEN
    SELECT count(*) INTO unfinished
      FROM app_private.workflow_step s
     WHERE s.run_id = target.run_id AND s.status <> 'succeeded';
    IF unfinished = 0 THEN
      UPDATE app_private.workflow_run
         SET status = 'succeeded', finished_at = pg_catalog.now()
       WHERE id = target.run_id
      RETURNING status INTO run_status;
    ELSE
      SELECT status INTO run_status FROM app_private.workflow_run WHERE id = target.run_id;
    END IF;
  ELSIF p_outcome = 'token_refused' THEN
    -- The agent stopped being able to act. `stopped`, not `failed`: nothing
    -- refused the work, and an operator's next move is to reauthorise rather
    -- than to read a step's reason.
    UPDATE app_private.workflow_run
       SET status = 'stopped',
           stopped_reason = 'agent_not_active',
           finished_at = pg_catalog.now()
     WHERE id = target.run_id
    RETURNING status INTO run_status;
  ELSIF p_outcome = 'abandoned' THEN
    -- The worker ran out of lease before it started the call, so nothing
    -- happened at all. The step goes back to `queued` and the next claim takes
    -- it with its attempt already incremented -- the retry that costs nothing
    -- because no work was done.
    UPDATE app_private.workflow_step
       SET status = 'queued', outcome = NULL, finished_at = NULL
     WHERE id = target.id;
    SELECT status INTO run_status FROM app_private.workflow_run WHERE id = target.run_id;
  ELSE
    UPDATE app_private.workflow_run
       SET status = 'failed',
           stopped_reason = p_reason,
           finished_at = pg_catalog.now()
     WHERE id = target.run_id
    RETURNING status INTO run_status;
  END IF;

  RETURN run_status::text;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_finish_step(
  uuid, text, app_private.workflow_step_outcome, jsonb, text) IS
  'Closes one step held by one holder and returns the RUN''s new status (ADR '
  '0227). A holder that lost its lease gets ''lease_lost'', which is a fact '
  'and not an error: the work happened and a successor holds the row. '
  'token_refused stops the run rather than failing it, because nothing refused '
  'the work; abandoned returns the step to queued, because nothing was done.';

-- ---------------------------------------------------------------------------
-- Parking a step
-- ---------------------------------------------------------------------------
--
-- **Park IS the backoff, and a parked step IS the pause.** There is no sleep
-- anywhere in the worker and no second mechanism for waiting: a retryable
-- failure sets a time, and the claim's predicate is what brings the step back.
-- The same mechanism is what a `wait` step will be in Session 33 -- a park
-- with no `resume_after` -- which is why the column is nullable and the claim
-- tests it with `<=` rather than treating NULL as ready.
CREATE FUNCTION app_private.workflow_park(
  p_step         uuid,
  p_holder       text,
  p_reason       text,
  p_resume_after timestamptz
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  parked integer;
BEGIN
  UPDATE app_private.workflow_step s
     SET status = 'parked',
         claimed_by = NULL,
         lease_until = NULL,
         resume_after = p_resume_after,
         reason = p_reason
   WHERE s.id = p_step AND s.claimed_by = p_holder AND s.status = 'claimed';
  GET DIAGNOSTICS parked = ROW_COUNT;
  IF parked = 0 THEN
    RETURN 'lease_lost';
  END IF;
  RETURN 'parked';
END $fn$;

COMMENT ON FUNCTION app_private.workflow_park(uuid, text, text, timestamptz) IS
  'Defers one step until a time, releasing its lease (ADR 0227). Park is the '
  'backoff and a parked step is the pause -- there is no sleep in the worker '
  'and no second waiting mechanism. A holder that lost its lease gets '
  '''lease_lost'', exactly as finishing does.';

-- ---------------------------------------------------------------------------
-- Cancelling, and reading
-- ---------------------------------------------------------------------------
--
-- Both take the agent and refuse a run that is not that agent's with `PT404`
-- -- the SAME refusal a missing run gets, so neither leaks the existence of
-- another agent's run (ADR 0229).
CREATE FUNCTION app_private.workflow_cancel(
  p_run   uuid,
  p_agent uuid
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  target app_private.workflow_run;
BEGIN
  SELECT * INTO target
    FROM app_private.workflow_run
   WHERE id = p_run AND agent_id = p_agent;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no such run'
      USING ERRCODE = 'PT404';
  END IF;

  IF target.status = 'queued' THEN
    UPDATE app_private.workflow_run
       SET status = 'cancelled',
           cancel_requested_at = pg_catalog.now(),
           finished_at = pg_catalog.now()
     WHERE id = p_run
    RETURNING status INTO target.status;
  ELSIF target.status = 'running' THEN
    -- An intent the next claim honours. The step in flight is upstream and
    -- cannot be recalled.
    UPDATE app_private.workflow_run
       SET cancel_requested_at = coalesce(cancel_requested_at, pg_catalog.now())
     WHERE id = p_run
    RETURNING status INTO target.status;
  END IF;

  RETURN target.status::text;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_cancel(uuid, uuid) IS
  'Cancels the AGENT''S OWN run: a queued one at once, a running one at its '
  'next claim (ADR 0229). Another agent''s run and a missing run are the same '
  'PT404, so neither leaks the other''s existence. A terminal run is returned '
  'unchanged rather than refused -- cancelling something already over is not '
  'an error.';

CREATE FUNCTION app_private.workflow_run_status(
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
                       'status', s.status,
                       'attempt', s.attempt,
                       'outcome', s.outcome,
                       'reason', s.reason,
                       'request_id', s.request_id,
                       'resume_after', s.resume_after,
                       'result', s.result,
                       'started_at', s.started_at,
                       'finished_at', s.finished_at)
                     ORDER BY s.position)
                FROM app_private.workflow_step s
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
  'The AGENT''S OWN run, whole: the run row, every step in order, and the '
  'lock digest validate compiled against so a reader can see whether the lock '
  'moved since (ADR 0228). input and result are returned because they are the '
  'agent''s own. Another agent''s run is PT404, the same as a missing one.';

-- ---------------------------------------------------------------------------
-- The heartbeat and the counts
-- ---------------------------------------------------------------------------
--
-- `started_at` is reset only when the holder CHANGES, which is what makes a
-- restart observable: the rehearsal reads the holder before the kill and after
-- the restart, and a new holder with a fresh `started_at` is the evidence the
-- loop came back rather than never stopped.
CREATE FUNCTION app_private.workflow_heartbeat(p_holder text)
  RETURNS void
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
  IF p_holder IS NULL OR p_holder = '' THEN
    RAISE EXCEPTION 'AP422: a heartbeat requires a holder'
      USING ERRCODE = 'PT422';
  END IF;

  INSERT INTO app_private.workflow_worker (singleton, holder, started_at, seen_at)
  VALUES (true, p_holder, pg_catalog.now(), pg_catalog.now())
  ON CONFLICT (singleton) DO UPDATE
     SET holder = excluded.holder,
         seen_at = excluded.seen_at,
         started_at = CASE
                        WHEN app_private.workflow_worker.holder = excluded.holder
                          THEN app_private.workflow_worker.started_at
                        ELSE excluded.started_at
                      END;
END $fn$;

COMMENT ON FUNCTION app_private.workflow_heartbeat(text) IS
  'Records that a loop asked for work. started_at moves only when the HOLDER '
  'changes, which is what makes a restart observable to the worker-restart '
  'rehearsal (ADR 0193, ADR 0226).';

-- Counts and ages, and NO verdict -- `agent_record_size`'s shape and its
-- reason (D1441): nobody has measured a run count at which a deployment is
-- unwell, and a threshold invented in a command that runs as root on
-- production could fail a host that works. The doctor's twelfth check reports
-- these numbers and reports that it could not read them, and reports nothing
-- in between (ADR 0195).
CREATE FUNCTION app_private.workflow_counts()
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
    'heartbeat_holder', worker.holder
  );
END $fn$;

COMMENT ON FUNCTION app_private.workflow_counts() IS
  'Runs and steps by status, the oldest OVERDUE lease''s age, and the '
  'heartbeat''s age and holder. Numbers and NO verdict (D1441, '
  'agent_record_size''s shape): nobody has measured a run count at which a '
  'deployment is unwell. Carries no URL, key, token or caller value.';

-- ---------------------------------------------------------------------------
-- The privileges, and the one that is absent
-- ---------------------------------------------------------------------------
--
-- `REVOKE ALL FROM PUBLIC` on all nine, for 0020's reason (D57, D262): a
-- function is PUBLIC-executable the moment it exists, so one created and not
-- revoked is granted to every role in the cluster -- and `ALTER DEFAULT
-- PRIVILEGES ... REVOKE ... FROM PUBLIC` records nothing at all for functions.
--
-- Eight are granted to `{{auth_service}}`, which is the role the loop and the
-- three routes run as, and to nothing else. **`workflow_install_definition`
-- gets no GRANT, and that absence is the decision** -- stated here so that a
-- reader looking for the grant finds the reason instead of a gap.
--
-- Schema USAGE on `app_private` is 0011's and is not re-granted (D337): a
-- second GRANT USAGE would leave it unclear which migration owns that
-- privilege.
--
-- **This block runs as the object owner and `RESET ROLE` is BELOW it** (D285,
-- ADR 0091): REVOKE and GRANT both require ownership of the function, and on a
-- host the connected role is `migration_user`, which owns nothing.
REVOKE ALL ON FUNCTION app_private.workflow_install_definition(
  text, integer, jsonb, text, text, text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  app_private.workflow_enqueue(uuid, text, integer, jsonb, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_claim_step(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_finish_step(
  uuid, text, app_private.workflow_step_outcome, jsonb, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  app_private.workflow_park(uuid, text, text, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_cancel(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_run_status(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_heartbeat(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.workflow_counts() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
  app_private.workflow_enqueue(uuid, text, integer, jsonb, boolean) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.workflow_claim_step(text, integer) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.workflow_finish_step(
  uuid, text, app_private.workflow_step_outcome, jsonb, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.workflow_park(uuid, text, text, timestamptz) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.workflow_cancel(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.workflow_run_status(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.workflow_heartbeat(text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.workflow_counts() TO {{auth_service}};

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

-- migrate:up
-- Plans and entitlements, usage samples, in-app notifications and idle sleep
-- (Session 41; ADR 0274, ADR 0275, ADR 0276).
--
-- **A plan's limit is checked before an operation row exists, under the
-- organisation's row lock** (D2521, D2538). `app.control_plan_limits` is the
-- SQL twin of `services/auth-api/app/plans.py` (a test holds them equal);
-- `control_request_operation` locks the organisation's row and counts its
-- projects not deleted plus its open creations against `projects_active`, and
-- a project's live branches plus its open branch creations against
-- `branches_total`, refusing `AP409: plan_limit_reached` /
-- `AP409: branch_limit_reached`. Rig 41d measured why the lock needs a policy of
-- its own: `control_organizations` had SELECT and INSERT policies only, and
-- under FORCE row security a definer's `SELECT ... FOR UPDATE` returned NO row --
-- so the function raises when it locked nothing.
--
-- **Usage is a recorded sample** (ADR 0275): `app.control_usage_samples`,
-- written every 300 s by `control_record_usage` -- granted to nobody, reached
-- as root through `container_exec` like `control_record_backups` -- each figure
-- the reading or NULL and named in `unread`; the document a member reads is
-- computed here, once, by `control_usage_document`.
--
-- **A notification is written where an operation ends** (ADR 0275):
-- `control_finish_operation` is 0004's, byte for byte, plus one marked block
-- that inserts a fixed template -- the type, the project key, the origin and
-- the error code; never the result, never the secret, never a caller value.
--
-- **Idle sleep is a trigger** (ADR 0276): `control_projects.idle_sleep_minutes`
-- (15, 30, 60 or NULL = never), set by a member; `control_request_idle_sleep`,
-- granted to nobody, inserts ONE `project.sleep` with `origin = 'idle'` only
-- over a window of samples that are all present and quiet. No customer backend
-- is QUIET; a failed read is unread, and an unread sample is not idle (D2539).
--
-- The seven released migrations are untouched (D912): what they created and
-- this file changes is ALTERed, or replaced with the same signature, or -- a
-- reader whose RETURNS TABLE widens -- dropped and created again (0007's shape).
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- Plans (ADR 0274)
-- ---------------------------------------------------------------------------

ALTER TABLE app.control_organizations
  ADD COLUMN plan text NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'premium'));

-- The organisation's row is LOCKED by a creation's request, inside the scope
-- the request just checked; nothing updates it through this policy (D2538).
CREATE POLICY control_organizations_lock ON app.control_organizations
  FOR UPDATE TO {{object_owner}}
  USING (id::text = current_setting('app.control_org', true))
  WITH CHECK (false);

CREATE TABLE app.control_plan_limits (
  plan        text NOT NULL CHECK (plan IN ('free', 'premium')),
  entitlement text NOT NULL CHECK (entitlement IN ('projects_active', 'branches_total')),
  value       integer NOT NULL CHECK (value >= 0),
  PRIMARY KEY (plan, entitlement)
);
-- `services/auth-api/app/plans.py`, the two entitlements SQL enforces.
INSERT INTO app.control_plan_limits (plan, entitlement, value) VALUES
  ('free', 'projects_active', 1),
  ('free', 'branches_total', 1),
  ('premium', 'projects_active', 3),
  ('premium', 'branches_total', 3);
ALTER TABLE app.control_plan_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_plan_limits FORCE ROW LEVEL SECURITY;
CREATE POLICY control_plan_limits_read ON app.control_plan_limits
  FOR SELECT TO {{object_owner}} USING (true);

-- *Notify me* (D2522): one row per organisation and plan; asking twice is one row.
CREATE TABLE app.control_plan_interest (
  organization_id uuid NOT NULL REFERENCES app.control_organizations(id),
  plan            text NOT NULL CHECK (plan = 'premium'),
  requested_by    uuid NOT NULL,
  requested_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, plan)
);
ALTER TABLE app.control_plan_interest ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_plan_interest FORCE ROW LEVEL SECURITY;
CREATE POLICY control_plan_interest_scoped ON app.control_plan_interest
  FOR ALL TO {{object_owner}}
  USING (organization_id::text = current_setting('app.control_org', true))
  WITH CHECK (organization_id::text = current_setting('app.control_org', true));

-- ---------------------------------------------------------------------------
-- Idle sleep's setting and the origin it requests under (ADR 0276)
-- ---------------------------------------------------------------------------

ALTER TABLE app.control_projects
  ADD COLUMN idle_sleep_minutes integer NULL CHECK (idle_sleep_minutes IN (15, 30, 60)),
  ADD COLUMN idle_sleep_set_by  uuid NULL,
  ADD CONSTRAINT control_projects_idle_sleep_names_its_member
    CHECK (idle_sleep_minutes IS NULL OR idle_sleep_set_by IS NOT NULL);

-- A member's setting is written inside the organisation's scope, by
-- control_set_idle_sleep alone; the registry has no other write policy.
CREATE POLICY control_projects_idle_sleep ON app.control_projects
  FOR UPDATE TO {{object_owner}}
  USING (organization_id::text = current_setting('app.control_org', true))
  WITH CHECK (organization_id::text = current_setting('app.control_org', true));

ALTER TABLE app.control_operations DROP CONSTRAINT control_operations_origin_check;
ALTER TABLE app.control_operations DROP CONSTRAINT control_operations_expiry_deletes_a_branch;
-- Each requested kind keeps a constraint of its own, so a refusal names the
-- kind it refused: 0006's `expiry` one, recreated with the same name and
-- meaning (an expiry only deletes a branch), and `idle`'s beside it.
ALTER TABLE app.control_operations
  ADD CONSTRAINT control_operations_origin_check CHECK (origin IN ('member', 'expiry', 'idle')),
  ADD CONSTRAINT control_operations_expiry_deletes_a_branch
    CHECK (origin <> 'expiry' OR type = 'branch.delete'),
  ADD CONSTRAINT control_operations_idle_sleeps_a_project
    CHECK (origin <> 'idle' OR type = 'project.sleep');

-- ---------------------------------------------------------------------------
-- A branch's reason and door (ADR 0271 as amended, D2514, D2515)
-- ---------------------------------------------------------------------------

ALTER TABLE app.control_branches
  ADD COLUMN reason text NULL CHECK (reason IS NULL OR length(reason) <= 300),
  ADD COLUMN door   text NULL CHECK (door IN ('ready', 'pending', 'unknown'));

-- ---------------------------------------------------------------------------
-- Usage samples (ADR 0275)
-- ---------------------------------------------------------------------------

CREATE TABLE app.control_usage_samples (
  project_key            text NOT NULL REFERENCES app.control_projects(key),
  observed_at            timestamptz NOT NULL DEFAULT now(),
  state                  text NOT NULL CHECK (state IN ('active', 'sleeping')),
  database_bytes         bigint NULL CHECK (database_bytes >= 0),
  repository_bytes       bigint NULL CHECK (repository_bytes >= 0),
  branch_count           integer NULL CHECK (branch_count >= 0),
  branch_bytes           bigint NULL CHECK (branch_bytes >= 0),
  customer_connections   integer NULL CHECK (customer_connections >= 0),
  -- The edge's counter AS READ, summed over codes below 400 (D2525, D553).
  requests_counter       bigint NULL CHECK (requests_counter >= 0),
  -- Rows created since the previous sample, from durable rows (D1643).
  agent_calls            integer NULL CHECK (agent_calls >= 0),
  workflow_runs          integer NULL CHECK (workflow_runs >= 0),
  -- The newest backend_start/state_change of a customer-role backend; NULL
  -- with the name absent from `unread` is "none present" -- quiet (D2539).
  last_customer_activity timestamptz NULL,
  unread                 text[] NOT NULL DEFAULT '{}' CHECK (unread <@ ARRAY[
    'database_bytes', 'repository_bytes', 'branch_count', 'branch_bytes',
    'customer_connections', 'requests_counter', 'agent_calls', 'workflow_runs',
    'last_customer_activity'
  ]::text[]),
  reason                 text NULL CHECK (reason IS NULL OR length(reason) <= 300),
  PRIMARY KEY (project_key, observed_at)
);
ALTER TABLE app.control_usage_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_usage_samples FORCE ROW LEVEL SECURITY;
CREATE POLICY control_usage_samples_read ON app.control_usage_samples
  FOR SELECT TO {{object_owner}}
  USING (project_key IN (SELECT p.key FROM app.control_projects p));

-- ---------------------------------------------------------------------------
-- Notifications (ADR 0275)
-- ---------------------------------------------------------------------------

CREATE TABLE app.control_notifications (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES app.control_organizations(id),
  project_key     text NULL,
  kind            text NOT NULL CHECK (kind IN (
    'operation_succeeded', 'operation_failed', 'idle_sleep', 'branch_expired',
    'limit_approaching'
  )),
  -- Only a `limit_approaching` notice names an entitlement: the daily index's key.
  entitlement     text NULL CHECK (entitlement IN ('storage_gb', 'agent_calls_per_day')),
  text            varchar(300) NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT control_notifications_entitlement_is_a_limit_notice
    CHECK ((kind = 'limit_approaching') = (entitlement IS NOT NULL))
);
-- At most one limit notice per entitlement, organisation and UTC day.
CREATE UNIQUE INDEX control_notifications_one_limit_notice_a_day
  ON app.control_notifications (organization_id, entitlement, ((created_at AT TIME ZONE 'UTC')::date))
  WHERE kind = 'limit_approaching';
CREATE INDEX control_notifications_newest ON app.control_notifications (organization_id, created_at DESC);
ALTER TABLE app.control_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_notifications FORCE ROW LEVEL SECURITY;
CREATE POLICY control_notifications_read ON app.control_notifications
  FOR SELECT TO {{object_owner}}
  USING (organization_id::text = current_setting('app.control_org', true));

-- ---------------------------------------------------------------------------
-- The request, with the plan's limits (D2521, D2538); same signature
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.control_request_operation(
  p_user uuid, p_org uuid, p_project text, p_type text, p_arguments jsonb
) RETURNS TABLE (operation_id uuid, created boolean)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_existing uuid;
  v_id uuid;
  v_expires timestamptz;
  v_plan text;
  v_limit integer;
  v_count integer;
BEGIN
  PERFORM app.control_enter(p_user);
  -- The types the reconciler executes; the route refuses the rest first.
  IF p_type NOT IN (
    'project.create', 'project.delete', 'project.sleep', 'project.wake', 'project.resize',
    'project.export', 'credential.rotate', 'branch.create', 'branch.reset', 'branch.delete',
    'restore.create'
  ) OR jsonb_typeof(p_arguments) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'AP422: invalid_request';
  END IF;
  -- D2165, in SQL as well as in the route: the two deletions are admin and
  -- above, every other write member and above.
  PERFORM app.control_require_role(
    p_org,
    CASE WHEN p_type IN ('project.delete', 'branch.delete') THEN 'admin' ELSE 'member' END::app.control_role
  );
  IF p_type IN ('project.create', 'branch.create', 'restore.create') THEN
    -- The organisation's row, locked inside the scope the role check set: a
    -- second request for the organisation waits here and then counts the
    -- first (D2521). Locking nothing is refused, never ignored (D2538).
    SELECT o.plan INTO v_plan FROM app.control_organizations o WHERE o.id = p_org FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'AP500: the organisation row could not be locked';
    END IF;
  END IF;
  IF p_type = 'project.create' THEN
    IF p_project IS NOT NULL THEN
      RAISE EXCEPTION 'AP422: invalid_request';
    END IF;
    -- `projects_active` (ADR 0274): the organisation's projects not deleted --
    -- a sleeping one holds its slot -- plus its open creations not yet in the
    -- registry. Checked BEFORE the existing-row answer: on Free a creation
    -- asked while one is open is the plan's refusal.
    SELECT l.value INTO v_limit FROM app.control_plan_limits l
     WHERE l.plan = v_plan AND l.entitlement = 'projects_active';
    SELECT (SELECT count(*) FROM app.control_projects p
             WHERE p.organization_id = p_org AND p.deleted_at IS NULL)
         + (SELECT count(*) FROM app.control_operations o
             WHERE o.organization_id = p_org AND o.type = 'project.create'
               AND o.status IN ('pending', 'running')
               AND (o.project_key IS NULL OR NOT EXISTS (
                 SELECT 1 FROM app.control_projects p WHERE p.key = o.project_key)))
      INTO v_count;
    IF v_limit IS NULL OR v_count >= v_limit THEN
      RAISE EXCEPTION 'AP409: plan_limit_reached';
    END IF;
    SELECT o.id INTO v_existing FROM app.control_operations o
     WHERE o.organization_id = p_org AND o.type = 'project.create'
       AND o.status IN ('pending', 'running');
  ELSE
    -- The organisation's own project, not deleted; anything else is the one
    -- `not_found` (D2053).
    PERFORM 1 FROM app.control_projects p
     WHERE p.key = p_project AND p.organization_id = p_org AND p.deleted_at IS NULL;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'AP404: not_found';
    END IF;
    -- A branch's expiry: at least 15 minutes and at most 7 days after the
    -- request (ADR 0272); the route checks the same bounds first.
    IF p_arguments ? 'expires_at' THEN
      IF p_type NOT IN ('branch.create', 'restore.create', 'branch.reset') THEN
        RAISE EXCEPTION 'AP422: invalid_request';
      END IF;
      v_expires := (p_arguments ->> 'expires_at')::timestamptz;
      IF v_expires < now() + interval '15 minutes' OR v_expires > now() + interval '7 days' THEN
        RAISE EXCEPTION 'AP422: invalid_request';
      END IF;
    END IF;
    -- `branches_total` (ADR 0274; D2430's rule, its number now the plan's),
    -- before any row exists: recorded branches not deleted plus creations
    -- already asked for.
    IF p_type IN ('branch.create', 'restore.create') THEN
      SELECT l.value INTO v_limit FROM app.control_plan_limits l
       WHERE l.plan = v_plan AND l.entitlement = 'branches_total';
      SELECT (SELECT count(*) FROM app.control_branches b
               WHERE b.project_key = p_project AND b.state <> 'deleted')
           + (SELECT count(*) FROM app.control_operations o
               WHERE o.project_key = p_project AND o.type IN ('branch.create', 'restore.create')
                 AND o.status IN ('pending', 'running'))
        INTO v_count;
      IF v_limit IS NULL OR v_count >= v_limit THEN
        RAISE EXCEPTION 'AP409: branch_limit_reached';
      END IF;
    END IF;
    -- A reset or a deletion names a recorded live branch of this project.
    IF p_type IN ('branch.reset', 'branch.delete') THEN
      PERFORM 1 FROM app.control_branches b
       WHERE b.project_key = p_project AND b.name = p_arguments ->> 'branch'
         AND b.state <> 'deleted';
      IF NOT FOUND THEN
        RAISE EXCEPTION 'AP404: not_found';
      END IF;
    END IF;
    -- A project with a live branch is not deleted (D2438): delete the branch first.
    IF p_type = 'project.delete' THEN
      PERFORM 1 FROM app.control_branches b
       WHERE b.project_key = p_project AND b.state <> 'deleted';
      IF FOUND THEN
        RAISE EXCEPTION 'AP409: conflict';
      END IF;
    END IF;
    SELECT o.id INTO v_existing FROM app.control_operations o
     WHERE o.project_key = p_project AND o.status IN ('pending', 'running');
  END IF;
  IF v_existing IS NOT NULL THEN
    RETURN QUERY SELECT v_existing, false;
    RETURN;
  END IF;
  BEGIN
    INSERT INTO app.control_operations (organization_id, project_key, type, requested_by, arguments)
    VALUES (p_org, p_project, p_type, p_user, p_arguments)
    RETURNING id INTO v_id;
  EXCEPTION WHEN unique_violation THEN
    -- A concurrent request won the index; answer with its row (D2166).
    SELECT o.id INTO v_existing FROM app.control_operations o
     WHERE o.status IN ('pending', 'running')
       AND ((p_type = 'project.create' AND o.type = 'project.create' AND o.organization_id = p_org)
            OR (p_type <> 'project.create' AND o.project_key = p_project));
    RETURN QUERY SELECT v_existing, false;
    RETURN;
  END;
  RETURN QUERY SELECT v_id, true;
END;
$$;
COMMENT ON FUNCTION app.control_request_operation(uuid, uuid, text, text, jsonb) IS
  'Records a member''s request: the role, then, under the organisation''s row lock, the plan''s projects_active and branches_total (AP409 plan_limit_reached / branch_limit_reached before any row, ADR 0274, D2521, D2538), the branch rules of 0006, one open operation per project and one open creation per organisation (D2166).';

-- ---------------------------------------------------------------------------
-- The finish, with its notification (ADR 0275); same signature
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.control_finish_operation(
  p_id uuid, p_status text, p_error_code text, p_result jsonb, p_result_secret text DEFAULT NULL
) RETURNS void
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_type text;
  v_status text;
  v_undeclared text[];
  -- 0008: the notification (ADR 0275) --
  v_org uuid;
  v_key text;
  v_origin text;
  v_minutes integer;
  -- 0008: end --
BEGIN
  SELECT o.type, o.status INTO v_type, v_status
    FROM app.control_operations o WHERE o.id = p_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: not_found';
  END IF;
  IF v_status <> 'running' THEN
    -- A terminal row is never rewritten, and a pending one was never claimed.
    RAISE EXCEPTION 'AP409: not_running';
  END IF;
  IF p_status NOT IN ('succeeded', 'failed') OR (p_status = 'failed') <> (p_error_code IS NOT NULL) THEN
    RAISE EXCEPTION 'AP422: invalid_outcome';
  END IF;
  IF p_result IS NOT NULL AND jsonb_typeof(p_result) <> 'object' THEN
    RAISE EXCEPTION 'AP422: undeclared_result';
  END IF;
  SELECT array_agg(k ORDER BY k) INTO v_undeclared
    FROM jsonb_object_keys(coalesce(p_result, '{}'::jsonb)) AS k
   WHERE NOT (k = ANY (app.control_result_members(v_type)));
  IF v_undeclared IS NOT NULL THEN
    RAISE EXCEPTION 'AP422: undeclared_result';
  END IF;
  UPDATE app.control_operations o
     SET status = p_status, error_code = p_error_code, result = p_result,
         result_secret = p_result_secret, finished_at = now(),
         progress = CASE WHEN p_status = 'succeeded' THEN 100 ELSE o.progress END
   WHERE o.id = p_id;
  -- 0008: the notification (ADR 0275) --
  -- In the finish's own transaction, from a fixed template: the type, the
  -- project key, the origin and the error code -- never p_result, never the
  -- secret, never a caller value. The idle minutes are the project's own
  -- CHECKed setting.
  SELECT o.organization_id, o.project_key, o.origin INTO v_org, v_key, v_origin
    FROM app.control_operations o WHERE o.id = p_id;
  IF v_origin = 'idle' THEN
    SELECT p.idle_sleep_minutes INTO v_minutes FROM app.control_projects p WHERE p.key = v_key;
  END IF;
  INSERT INTO app.control_notifications (organization_id, project_key, kind, text)
  VALUES (
    v_org, v_key,
    CASE
      WHEN p_status = 'failed' THEN 'operation_failed'
      WHEN v_origin = 'idle' THEN 'idle_sleep'
      WHEN v_origin = 'expiry' THEN 'branch_expired'
      ELSE 'operation_succeeded'
    END,
    v_type || ' on ' || coalesce(v_key, 'a new project') || ' ' || p_status
      || CASE
           WHEN p_status = 'failed' THEN ' (' || p_error_code || ')'
           WHEN v_origin = 'idle' THEN ' (requested because it was idle for '
             || coalesce(v_minutes::text, 'its set') || ' minutes; while it sleeps its backups '
             || 'stop; wake it with apg project wake)'
           WHEN v_origin = 'expiry' THEN ' (requested because the branch expired)'
           ELSE ''
         END
  );
  -- 0008: end --
END;
$$;
COMMENT ON FUNCTION app.control_finish_operation(uuid, text, text, jsonb, text) IS
  'Finishes a RUNNING operation: succeeded, or failed with an error code; a result member its type does not declare is refused, and only a succeeded export may carry a secret (D2151, D2164); and writes ONE notification in the same transaction from a fixed template (ADR 0275). Granted to nobody.';

-- ---------------------------------------------------------------------------
-- The branch reading, with reason and door (D2514, D2515); same signature
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.control_record_branches(p_branches jsonb) RETURNS integer
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_count integer;
BEGIN
  IF jsonb_typeof(p_branches) IS DISTINCT FROM 'array' OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(p_branches) AS b
     WHERE jsonb_typeof(b) <> 'object'
        OR NOT (b ? 'project_key' AND b ? 'name' AND b ? 'state')
        OR EXISTS (
          SELECT 1 FROM jsonb_object_keys(b) AS k WHERE k NOT IN (
            'project_key', 'name', 'state', 'requested_point', 'reached_point', 'timeline',
            'parent_commit', 'pool_host', 'direct_host', 'expires_at', 'expires_for', 'created_at',
            'reason', 'door'
          )
        )
  ) THEN
    RAISE EXCEPTION 'AP422: invalid_branches';
  END IF;
  -- The reading is the host's whole truth: a recorded branch it no longer
  -- names is deleted, with the moment it was first seen gone.
  UPDATE app.control_branches c
     SET state = 'deleted', deleted_at = now(), observed_at = now()
   WHERE c.state <> 'deleted'
     AND NOT EXISTS (
       SELECT 1 FROM jsonb_array_elements(p_branches) AS b
        WHERE b ->> 'project_key' = c.project_key AND b ->> 'name' = c.name
     );
  INSERT INTO app.control_branches AS c (
    project_key, name, state, requested_point, reached_point, timeline, parent_commit,
    pool_host, direct_host, expires_at, expires_for, created_at, observed_at, deleted_at,
    reason, door
  )
  SELECT b ->> 'project_key', b ->> 'name', b ->> 'state',
         (b ->> 'requested_point')::timestamptz, (b ->> 'reached_point')::timestamptz,
         (b ->> 'timeline')::integer, b ->> 'parent_commit', b ->> 'pool_host',
         b ->> 'direct_host', (b ->> 'expires_at')::timestamptz, (b ->> 'expires_for')::uuid,
         (b ->> 'created_at')::timestamptz, now(), NULL, b ->> 'reason', b ->> 'door'
    FROM jsonb_array_elements(p_branches) AS b
  ON CONFLICT (project_key, name) DO UPDATE
    SET state = EXCLUDED.state, requested_point = EXCLUDED.requested_point,
        reached_point = EXCLUDED.reached_point, timeline = EXCLUDED.timeline,
        parent_commit = EXCLUDED.parent_commit, pool_host = EXCLUDED.pool_host,
        direct_host = EXCLUDED.direct_host, expires_at = EXCLUDED.expires_at,
        expires_for = EXCLUDED.expires_for, created_at = EXCLUDED.created_at,
        observed_at = now(), deleted_at = NULL, reason = EXCLUDED.reason,
        door = EXCLUDED.door;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;
COMMENT ON FUNCTION app.control_record_branches(jsonb) IS
  'Replaces the branch reading with what the reconciler read of every branch.json on the host: [{project_key, name, state, ..., reason, door}]; a branch it no longer names is deleted. Granted to nobody (D2450, D2514).';

-- The two branch readers widen by reason and door: dropped and created again.
DROP FUNCTION app.control_list_branches(uuid, text);
DROP FUNCTION app.control_get_branch(uuid, text, text);

CREATE FUNCTION app.control_list_branches(p_user uuid, p_key text)
  RETURNS TABLE (
    name text, state text, requested_point timestamptz, reached_point timestamptz,
    timeline integer, pool_host text, direct_host text, expires_at timestamptz,
    created_at timestamptz, observed_at timestamptz, reason text, door text
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'viewer');
  RETURN QUERY
    SELECT b.name, b.state, b.requested_point, b.reached_point, b.timeline, b.pool_host,
           b.direct_host, b.expires_at, b.created_at, b.observed_at, b.reason, b.door
      FROM app.control_branches b
     WHERE b.project_key = p_key AND b.state <> 'deleted'
     ORDER BY b.name;
END;
$$;
COMMENT ON FUNCTION app.control_list_branches(uuid, text) IS
  'A project''s live branches as the reconciler last recorded them, with the last failure''s reason and the door''s state, viewer and above; the project resolved first (D2451, D2514).';

CREATE FUNCTION app.control_get_branch(p_user uuid, p_key text, p_branch text)
  RETURNS TABLE (
    name text, state text, requested_point timestamptz, reached_point timestamptz,
    timeline integer, pool_host text, direct_host text, expires_at timestamptz,
    created_at timestamptz, observed_at timestamptz, reason text, door text
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'viewer');
  RETURN QUERY
    SELECT b.name, b.state, b.requested_point, b.reached_point, b.timeline, b.pool_host,
           b.direct_host, b.expires_at, b.created_at, b.observed_at, b.reason, b.door
      FROM app.control_branches b
     WHERE b.project_key = p_key AND b.name = p_branch AND b.state <> 'deleted';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: not_found';
  END IF;
END;
$$;
COMMENT ON FUNCTION app.control_get_branch(uuid, text, text) IS
  'One live branch of a project with its reason and door, viewer and above; a missing branch of the caller''s own project is the same not_found as a foreign or missing project (D2451, D2514).';

-- ---------------------------------------------------------------------------
-- The reconciler's three new writers (granted to nobody; reached as root)
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_record_usage(p_samples jsonb) RETURNS integer
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_count integer;
BEGIN
  IF jsonb_typeof(p_samples) IS DISTINCT FROM 'array' OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(p_samples) AS s
     WHERE jsonb_typeof(s) <> 'object'
        OR NOT (s ? 'project_key' AND s ? 'state')
        OR EXISTS (
          SELECT 1 FROM jsonb_object_keys(s) AS k WHERE k NOT IN (
            'project_key', 'state', 'database_bytes', 'repository_bytes', 'branch_count',
            'branch_bytes', 'customer_connections', 'requests_counter', 'agent_calls',
            'workflow_runs', 'last_customer_activity', 'unread', 'reason'
          )
        )
        OR (s ? 'unread' AND jsonb_typeof(s -> 'unread') <> 'array')
  ) THEN
    RAISE EXCEPTION 'AP422: invalid_samples';
  END IF;
  INSERT INTO app.control_usage_samples (
    project_key, observed_at, state, database_bytes, repository_bytes, branch_count,
    branch_bytes, customer_connections, requests_counter, agent_calls, workflow_runs,
    last_customer_activity, unread, reason
  )
  SELECT s ->> 'project_key', now(), s ->> 'state',
         (s ->> 'database_bytes')::bigint, (s ->> 'repository_bytes')::bigint,
         (s ->> 'branch_count')::integer, (s ->> 'branch_bytes')::bigint,
         (s ->> 'customer_connections')::integer, (s ->> 'requests_counter')::bigint,
         (s ->> 'agent_calls')::integer, (s ->> 'workflow_runs')::integer,
         (s ->> 'last_customer_activity')::timestamptz,
         coalesce(ARRAY(SELECT jsonb_array_elements_text(s -> 'unread')), '{}'::text[]),
         s ->> 'reason'
    FROM jsonb_array_elements(p_samples) AS s;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;
COMMENT ON FUNCTION app.control_record_usage(jsonb) IS
  'Records one usage sample per project, with now() as its instant (ADR 0275): [{project_key, state, <figures>, last_customer_activity, unread, reason}]; a figure not read is null and named in unread. Granted to nobody.';

CREATE FUNCTION app.control_request_idle_sleep(p_project text) RETURNS uuid
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_project app.control_projects%ROWTYPE;
  v_last record;
  v_since timestamptz;
  v_needed integer;
  v_quiet boolean;
  v_id uuid;
BEGIN
  SELECT * INTO v_project FROM app.control_projects
   WHERE key = p_project AND deleted_at IS NULL AND idle_sleep_minutes IS NOT NULL;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  IF EXISTS (SELECT 1 FROM app.control_operations
              WHERE project_key = p_project AND status IN ('pending', 'running')) THEN
    RETURN NULL;
  END IF;
  v_since := now() - make_interval(mins => v_project.idle_sleep_minutes);
  -- Asleep already, or an operation finished inside the window (a wake
  -- restarts it): not now.
  SELECT o.type, o.finished_at INTO v_last FROM app.control_operations o
   WHERE o.project_key = p_project AND o.status = 'succeeded'
   ORDER BY o.finished_at DESC LIMIT 1;
  IF FOUND AND (v_last.type = 'project.sleep' OR v_last.finished_at > v_since) THEN
    RETURN NULL;
  END IF;
  -- Every sample the window should hold, contiguous, awake, both signals READ
  -- and quiet: no sub-400 request (the counter unmoved) and no customer-role
  -- activity inside the window -- none present (NULL, read) is quiet (D2539).
  v_needed := ceil(v_project.idle_sleep_minutes * 60 / 300.0);
  WITH s AS (
    SELECT observed_at, state, requests_counter, last_customer_activity, unread,
           lag(observed_at) OVER (ORDER BY observed_at) AS previous
      FROM app.control_usage_samples
     WHERE project_key = p_project AND observed_at > v_since
  )
  SELECT count(*) >= v_needed
     AND bool_and(state = 'active')
     AND bool_and(NOT (unread && ARRAY['requests_counter', 'last_customer_activity']::text[]))
     AND bool_and(requests_counter IS NOT NULL)
     AND max(requests_counter) = min(requests_counter)
     AND bool_and(last_customer_activity IS NULL OR last_customer_activity < v_since)
     AND min(observed_at) <= v_since + interval '450 seconds'
     AND max(observed_at) >= now() - interval '450 seconds'
     AND bool_and(previous IS NULL OR observed_at - previous <= interval '450 seconds')
    INTO v_quiet FROM s;
  IF NOT coalesce(v_quiet, false) THEN
    RETURN NULL;
  END IF;
  INSERT INTO app.control_operations
    (organization_id, project_key, type, status, requested_by, arguments, origin)
  VALUES (v_project.organization_id, p_project, 'project.sleep', 'pending',
          v_project.idle_sleep_set_by, '{}'::jsonb, 'idle')
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;
COMMENT ON FUNCTION app.control_request_idle_sleep(text) IS
  'An idle project''s sleep, ONE row, on behalf of the member who set its idle-sleep minutes, origin idle, only over a window of samples all present, awake, read and quiet; NULL and nothing otherwise, and while any operation for the project is open (ADR 0276, rig 41d, D2539). Granted to nobody.';

CREATE FUNCTION app.control_record_limit_notice(p_project text, p_entitlement text) RETURNS uuid
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_org uuid;
  v_plan text;
  v_id uuid;
BEGIN
  IF p_entitlement NOT IN ('storage_gb', 'agent_calls_per_day') THEN
    RAISE EXCEPTION 'AP422: invalid_entitlement';
  END IF;
  SELECT p.organization_id, o.plan INTO v_org, v_plan
    FROM app.control_projects p JOIN app.control_organizations o ON o.id = p.organization_id
   WHERE p.key = p_project AND p.deleted_at IS NULL;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  INSERT INTO app.control_notifications (organization_id, project_key, kind, entitlement, text)
  VALUES (
    v_org, p_project, 'limit_approaching', p_entitlement,
    p_project || ' is past 80% of the ' || v_plan || ' plan''s ' || p_entitlement
      || ' (shown, not enforced during the beta)'
  )
  ON CONFLICT DO NOTHING
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;
COMMENT ON FUNCTION app.control_record_limit_notice(text, text) IS
  'A limit_approaching notice for a read-not-enforced entitlement, at most one per entitlement, organisation and UTC day (ADR 0275); NULL when one exists or the project does not. Granted to nobody.';

-- ---------------------------------------------------------------------------
-- The members' readers and writers (definer; granted to the identity service)
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_list_plans(p_user uuid)
  RETURNS TABLE (plan text, entitlement text, value integer)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT l.plan, l.entitlement, l.value FROM app.control_plan_limits l
     ORDER BY l.plan, l.entitlement;
END;
$$;
COMMENT ON FUNCTION app.control_list_plans(uuid) IS
  'The limits SQL enforces, per plan: the twin of services/auth-api/app/plans.py (ADR 0274). Any account.';

CREATE FUNCTION app.control_get_org_plan(p_user uuid, p_org uuid)
  RETURNS TABLE (plan text, projects_active integer, interest text[])
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(p_org, 'viewer');
  RETURN QUERY
    SELECT o.plan,
           (SELECT count(*)::integer FROM app.control_projects p
             WHERE p.organization_id = p_org AND p.deleted_at IS NULL),
           coalesce((SELECT array_agg(i.plan ORDER BY i.plan) FROM app.control_plan_interest i
                      WHERE i.organization_id = p_org), '{}'::text[])
      FROM app.control_organizations o WHERE o.id = p_org;
END;
$$;
COMMENT ON FUNCTION app.control_get_org_plan(uuid, uuid) IS
  'An organisation''s plan, its projects counted as projects_active counts them, and the plans it asked to be told about; viewer and above (ADR 0274).';

CREATE FUNCTION app.control_register_interest(p_user uuid, p_org uuid, p_plan text)
  RETURNS boolean
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_created boolean;
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(p_org, 'member');
  IF p_plan IS DISTINCT FROM 'premium' THEN
    RAISE EXCEPTION 'AP422: invalid_request';
  END IF;
  INSERT INTO app.control_plan_interest (organization_id, plan, requested_by)
  VALUES (p_org, p_plan, p_user)
  ON CONFLICT (organization_id, plan) DO NOTHING;
  GET DIAGNOSTICS v_created = ROW_COUNT;
  RETURN v_created;
END;
$$;
COMMENT ON FUNCTION app.control_register_interest(uuid, uuid, text) IS
  '*Notify me*: ONE interest row per organisation and plan, only for a plan unavailable during the beta; true when this request made it. Member and above (D2522).';

CREATE FUNCTION app.control_set_idle_sleep(p_user uuid, p_key text, p_minutes integer)
  RETURNS integer
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'member');
  IF p_minutes IS NOT NULL AND p_minutes NOT IN (15, 30, 60) THEN
    RAISE EXCEPTION 'AP422: invalid_request';
  END IF;
  UPDATE app.control_projects p
     SET idle_sleep_minutes = p_minutes,
         idle_sleep_set_by = CASE WHEN p_minutes IS NULL THEN NULL ELSE p_user END
   WHERE p.key = p_key AND p.deleted_at IS NULL;
  RETURN p_minutes;
END;
$$;
COMMENT ON FUNCTION app.control_set_idle_sleep(uuid, text, integer) IS
  'A project''s idle-sleep minutes (15, 30, 60, or NULL = never) and the member who set them, whom an idle sleep is requested for; member and above (ADR 0276).';

-- One project's usage over [p_from, p_to], computed once, here (ADR 0275).
-- Invoker-rights and granted to nobody: the definer readers below call it
-- after resolving the project, so row security already shows only the caller's.
CREATE FUNCTION app.control_usage_document(p_key text, p_from timestamptz, p_to timestamptz)
  RETURNS jsonb
  LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_figures jsonb := '{}'::jsonb;
  v_figure text;
  v_one jsonb;
  v_present integer;
  v_requests bigint := 0;
  v_resets integer := 0;
  v_previous bigint;
  v_row record;
  v_state text := 'absent';
  v_at timestamptz;
  v_active numeric := 0;
  v_sleeping numeric := 0;
  v_event record;
  v_project app.control_projects%ROWTYPE;
BEGIN
  SELECT count(*) INTO v_present FROM app.control_usage_samples
   WHERE project_key = p_key AND observed_at > p_from AND observed_at <= p_to;
  -- The gauges: the newest figure READ, when, the window's maximum, and how
  -- many samples could not read it.
  FOREACH v_figure IN ARRAY ARRAY[
    'database_bytes', 'repository_bytes', 'branch_count', 'branch_bytes', 'customer_connections'
  ] LOOP
    EXECUTE format(
      'SELECT jsonb_build_object('
      '  ''latest'', (SELECT %1$I FROM app.control_usage_samples WHERE project_key = $1'
      '     AND observed_at > $2 AND observed_at <= $3 AND %1$I IS NOT NULL'
      '     ORDER BY observed_at DESC LIMIT 1),'
      '  ''latest_at'', (SELECT observed_at FROM app.control_usage_samples WHERE project_key = $1'
      '     AND observed_at > $2 AND observed_at <= $3 AND %1$I IS NOT NULL'
      '     ORDER BY observed_at DESC LIMIT 1),'
      '  ''max'', (SELECT max(%1$I) FROM app.control_usage_samples WHERE project_key = $1'
      '     AND observed_at > $2 AND observed_at <= $3),'
      '  ''unread_samples'', (SELECT count(*) FROM app.control_usage_samples WHERE project_key = $1'
      '     AND observed_at > $2 AND observed_at <= $3 AND %1$I IS NULL))',
      v_figure
    ) INTO v_one USING p_key, p_from, p_to;
    v_figures := v_figures || jsonb_build_object(v_figure, v_one);
  END LOOP;
  -- The counter: increases between consecutive READ samples; a decrease is a
  -- reset, counted from zero (D553).
  FOR v_row IN
    SELECT requests_counter AS value FROM app.control_usage_samples
     WHERE project_key = p_key AND observed_at > p_from AND observed_at <= p_to
       AND requests_counter IS NOT NULL
     ORDER BY observed_at
  LOOP
    IF v_previous IS NOT NULL THEN
      IF v_row.value >= v_previous THEN
        v_requests := v_requests + (v_row.value - v_previous);
      ELSE
        v_resets := v_resets + 1;
        v_requests := v_requests + v_row.value;
      END IF;
    END IF;
    v_previous := v_row.value;
  END LOOP;
  -- Active and sleeping seconds, from the operation history (never sampled).
  SELECT * INTO v_project FROM app.control_projects WHERE key = p_key;
  IF FOUND THEN
    v_state := 'active';
    v_at := v_project.adopted_at;
    FOR v_event IN
      SELECT o.type, o.finished_at FROM app.control_operations o
       WHERE o.project_key = p_key AND o.status = 'succeeded'
         AND o.type IN ('project.sleep', 'project.wake', 'project.delete')
       ORDER BY o.finished_at
    LOOP
      IF v_event.finished_at > v_at THEN
        IF v_state = 'active' THEN
          v_active := v_active + greatest(0, extract(epoch FROM
            least(v_event.finished_at, p_to) - greatest(v_at, p_from)));
        ELSIF v_state = 'sleeping' THEN
          v_sleeping := v_sleeping + greatest(0, extract(epoch FROM
            least(v_event.finished_at, p_to) - greatest(v_at, p_from)));
        END IF;
        v_at := v_event.finished_at;
      END IF;
      v_state := CASE v_event.type
        WHEN 'project.sleep' THEN 'sleeping' WHEN 'project.wake' THEN 'active' ELSE 'absent' END;
    END LOOP;
    IF v_state = 'active' AND v_project.deleted_at IS NULL THEN
      v_active := v_active + greatest(0, extract(epoch FROM p_to - greatest(v_at, p_from)));
    ELSIF v_state = 'sleeping' AND v_project.deleted_at IS NULL THEN
      v_sleeping := v_sleeping + greatest(0, extract(epoch FROM p_to - greatest(v_at, p_from)));
    END IF;
  END IF;
  RETURN jsonb_build_object(
    'project_key', p_key,
    'window', jsonb_build_object('from', p_from, 'to', p_to),
    'samples', jsonb_build_object(
      'expected', floor(extract(epoch FROM p_to - p_from) / 300)::integer,
      'present', v_present),
    'figures', v_figures,
    'requests', CASE WHEN v_previous IS NULL THEN NULL
                     ELSE jsonb_build_object('increase', v_requests, 'resets', v_resets) END,
    'agent_calls', (SELECT sum(agent_calls) FROM app.control_usage_samples
                     WHERE project_key = p_key AND observed_at > p_from AND observed_at <= p_to),
    'workflow_runs', (SELECT sum(workflow_runs) FROM app.control_usage_samples
                       WHERE project_key = p_key AND observed_at > p_from AND observed_at <= p_to),
    'active_seconds', round(v_active),
    'sleeping_seconds', round(v_sleeping)
  );
END;
$$;
COMMENT ON FUNCTION app.control_usage_document(text, timestamptz, timestamptz) IS
  'One project''s usage over a window: samples expected and present, each gauge''s latest read value, maximum and unread count, the request counter''s increases with resets read, agent calls and workflow runs summed, active and sleeping seconds from the history (ADR 0275). Called by the definer readers; granted to nobody.';

CREATE FUNCTION app.control_project_usage(p_user uuid, p_key text, p_hours integer)
  RETURNS jsonb
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'viewer');
  IF p_hours IS NULL OR p_hours < 1 OR p_hours > 720 THEN
    RAISE EXCEPTION 'AP422: invalid_request';
  END IF;
  RETURN app.control_usage_document(p_key, now() - make_interval(hours => p_hours), now());
END;
$$;
COMMENT ON FUNCTION app.control_project_usage(uuid, text, integer) IS
  'A live project''s usage over the last 1..720 hours, viewer and above; a foreign and a missing project are the one not_found (ADR 0275, THR-CTL-ENUMERATION''s rule).';

CREATE FUNCTION app.control_org_usage(p_user uuid, p_org uuid, p_hours integer)
  RETURNS jsonb
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_from timestamptz;
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(p_org, 'viewer');
  IF p_hours IS NULL OR p_hours < 1 OR p_hours > 720 THEN
    RAISE EXCEPTION 'AP422: invalid_request';
  END IF;
  v_from := now() - make_interval(hours => p_hours);
  RETURN jsonb_build_object(
    'organization_id', p_org,
    'window', jsonb_build_object('from', v_from, 'to', now()),
    'projects', coalesce((
      SELECT jsonb_agg(app.control_usage_document(p.key, v_from, now()) ORDER BY p.key)
        FROM app.control_projects p
       WHERE p.organization_id = p_org AND (p.deleted_at IS NULL OR p.deleted_at > v_from)
    ), '[]'::jsonb)
  );
END;
$$;
COMMENT ON FUNCTION app.control_org_usage(uuid, uuid, integer) IS
  'An organisation''s projects'' usage over the last 1..720 hours (every project live in the window, a deleted one included), viewer and above (ADR 0275).';

CREATE FUNCTION app.control_list_notifications(p_user uuid, p_org uuid, p_limit integer)
  RETURNS TABLE (id uuid, project_key text, kind text, text varchar, created_at timestamptz)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(p_org, 'viewer');
  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 200 THEN
    RAISE EXCEPTION 'AP422: invalid_request';
  END IF;
  RETURN QUERY
    SELECT n.id, n.project_key, n.kind, n.text, n.created_at
      FROM app.control_notifications n
     WHERE n.organization_id = p_org
     ORDER BY n.created_at DESC, n.id
     LIMIT p_limit;
END;
$$;
COMMENT ON FUNCTION app.control_list_notifications(uuid, uuid, integer) IS
  'An organisation''s newest notifications (at most 200), viewer and above; no read state, no deletion (ADR 0275).';

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION app.control_list_branches(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_branch(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_record_usage(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_request_idle_sleep(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_record_limit_notice(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_usage_document(text, timestamptz, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_plans(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_org_plan(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_register_interest(uuid, uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_set_idle_sleep(uuid, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_project_usage(uuid, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_org_usage(uuid, uuid, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_notifications(uuid, uuid, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.control_list_branches(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_branch(uuid, text, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_plans(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_org_plan(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_register_interest(uuid, uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_set_idle_sleep(uuid, text, integer) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_project_usage(uuid, text, integer) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_org_usage(uuid, uuid, integer) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_notifications(uuid, uuid, integer) TO {{auth_service}};

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

-- migrate:up
-- Long operations made visible (Session 47; ADR 0296, ADR 0297).
--
-- 1. `control_operation_steps`: when each step of an operation FIRST began,
--    written by `control_advance_operation` (the reconciler's, granted to
--    nobody) and read only through the two operation readers. FORCE RLS; its one
--    policy follows `control_operations`' own membership filter.
-- 2. The two operation readers serve `steps` and a `subject` -- what the
--    operation acts on and nothing else: never `arguments` (D2895), never the
--    handoff digest, an administrator's name or a verifier.
-- 3. Notifications: the kind `operation_started`, written by
--    `control_request_operation` for a creation, a branch, a restore and a reset;
--    every notice an operation writes names it (`operation_id`,
--    `operation_type`). The two functions below are 0008's text with one marked
--    insertion each (`test_0011s_finish_is_0008s_but_for_the_operation`).
--
-- The ten released migrations are untouched (D912). A changed RETURNS TABLE is
-- a new function, so each reader is dropped and created again, wider, with its
-- grant made again -- 0007's shape.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The step log (ADR 0296 decision 1)
-- ---------------------------------------------------------------------------

CREATE TABLE app.control_operation_steps (
  operation_id uuid NOT NULL REFERENCES app.control_operations(id) ON DELETE CASCADE,
  step         text NOT NULL CHECK (step ~ '^[a-z][a-z0-9-]{0,31}$'),
  started_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (operation_id, step)
);
ALTER TABLE app.control_operation_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_operation_steps FORCE ROW LEVEL SECURITY;
REVOKE ALL ON app.control_operation_steps FROM PUBLIC;
CREATE POLICY control_operation_steps_read ON app.control_operation_steps
  FOR SELECT TO {{object_owner}}
  USING (operation_id IN (SELECT o.id FROM app.control_operations o));

CREATE OR REPLACE FUNCTION app.control_advance_operation(
  p_id uuid, p_step text, p_progress integer, p_project_key text DEFAULT NULL
) RETURNS void
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  UPDATE app.control_operations o
     SET step = p_step, progress = p_progress,
         project_key = coalesce(o.project_key, p_project_key)
   WHERE o.id = p_id AND o.status = 'running'
     AND (p_project_key IS NULL OR o.project_key IS NULL OR o.project_key = p_project_key);
  IF NOT FOUND THEN
    -- Not running, or naming a different project than the row already does.
    RAISE EXCEPTION 'AP409: not_running';
  END IF;
  -- 0011: when the step FIRST began; a repeated step keeps its time.
  INSERT INTO app.control_operation_steps (operation_id, step)
    VALUES (p_id, p_step) ON CONFLICT DO NOTHING;
END;
$$;
COMMENT ON FUNCTION app.control_advance_operation(uuid, text, integer, text) IS
  'Records a running operation''s step and progress, and -- once, for a creation -- the project key its slot gave it; logs when each step first began (ADR 0296). Granted to nobody (D2151).';

-- ---------------------------------------------------------------------------
-- The two readers, wider by steps and subject (ADR 0296 decision 2)
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_operation_subject(p_type text, p_arguments jsonb) RETURNS jsonb
  LANGUAGE sql IMMUTABLE
  SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
    WHEN p_type = 'project.create' THEN jsonb_build_object(
      'name', p_arguments -> 'name', 'profile', p_arguments -> 'profile')
    WHEN p_type = 'project.resize' THEN jsonb_build_object('profile', p_arguments -> 'profile')
    WHEN p_type IN ('branch.create', 'restore.create', 'branch.reset', 'branch.delete')
      THEN jsonb_build_object('branch', p_arguments -> 'branch')
    ELSE '{}'::jsonb
  END;
$$;
COMMENT ON FUNCTION app.control_operation_subject(text, jsonb) IS
  'What an operation acts on, from a closed allowlist of argument members per type (ADR 0296): never the handoff digest, an administrator''s name or a verifier. Executable by no role; the two readers call it as their owner.';

DROP FUNCTION app.control_list_operations(uuid, uuid);
DROP FUNCTION app.control_get_operation(uuid, uuid);

CREATE FUNCTION app.control_list_operations(p_user uuid, p_org uuid)
  RETURNS TABLE (
    id uuid, organization_id uuid, project_key text, type text, status text,
    progress integer, error_code text, created_at timestamptz, started_at timestamptz,
    finished_at timestamptz, requested_by uuid, step text, result jsonb, origin text,
    steps jsonb, subject jsonb
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.organization_id, o.project_key, o.type, o.status, o.progress, o.error_code,
           o.created_at, o.started_at, o.finished_at, o.requested_by, o.step, o.result, o.origin,
           coalesce((SELECT jsonb_agg(jsonb_build_object('step', s.step, 'started_at', s.started_at)
                                      ORDER BY s.started_at, s.step)
                       FROM app.control_operation_steps s WHERE s.operation_id = o.id),
                    '[]'::jsonb),
           app.control_operation_subject(o.type, o.arguments)
      FROM app.control_operations o
     WHERE o.organization_id = p_org
     ORDER BY o.created_at DESC, o.id;
END;
$$;
COMMENT ON FUNCTION app.control_list_operations(uuid, uuid) IS
  'An organisation''s operations, newest first, each naming its origin (D2480), the steps it began (ADR 0296) and its subject. Never the arguments or the result secret (D2164, D2895).';

CREATE FUNCTION app.control_get_operation(p_user uuid, p_id uuid)
  RETURNS TABLE (
    id uuid, organization_id uuid, project_key text, type text, status text,
    progress integer, error_code text, created_at timestamptz, started_at timestamptz,
    finished_at timestamptz, requested_by uuid, step text, result jsonb, origin text,
    steps jsonb, subject jsonb
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.organization_id, o.project_key, o.type, o.status, o.progress, o.error_code,
           o.created_at, o.started_at, o.finished_at, o.requested_by, o.step, o.result, o.origin,
           coalesce((SELECT jsonb_agg(jsonb_build_object('step', s.step, 'started_at', s.started_at)
                                      ORDER BY s.started_at, s.step)
                       FROM app.control_operation_steps s WHERE s.operation_id = o.id),
                    '[]'::jsonb),
           app.control_operation_subject(o.type, o.arguments)
      FROM app.control_operations o
     WHERE o.id = p_id;
END;
$$;
COMMENT ON FUNCTION app.control_get_operation(uuid, uuid) IS
  'One operation of the caller''s organisations, or no row (ADR 0254), naming its origin (D2480), the steps it began (ADR 0296) and its subject. Never the arguments or the result secret: control_take_result_secret hands that out once (D2164).';

-- ---------------------------------------------------------------------------
-- Notifications name their operation; a long request says it started (ADR 0297)
-- ---------------------------------------------------------------------------

ALTER TABLE app.control_notifications
  ADD COLUMN operation_id uuid NULL,
  ADD COLUMN operation_type text NULL CHECK (operation_type IN (
    'project.create', 'project.delete', 'project.sleep', 'project.wake', 'project.resize',
    'project.export', 'branch.create', 'branch.reset', 'branch.delete', 'restore.create',
    'credential.rotate'
  )),
  ADD CONSTRAINT control_notifications_operation_named
    CHECK ((operation_id IS NULL) = (operation_type IS NULL));
ALTER TABLE app.control_notifications DROP CONSTRAINT control_notifications_kind_check;
ALTER TABLE app.control_notifications ADD CONSTRAINT control_notifications_kind_check
  CHECK (kind IN (
    'operation_started', 'operation_succeeded', 'operation_failed', 'idle_sleep',
    'branch_expired', 'limit_approaching'
  ));
-- The request's definer writes as the owner, so FORCE RLS needs this floor: a
-- started notice, in the organisation the role check scoped, for an operation
-- the caller has just asked for.
CREATE POLICY control_notifications_started ON app.control_notifications
  FOR INSERT TO {{object_owner}}
  WITH CHECK (
    kind = 'operation_started'
    AND organization_id::text = current_setting('app.control_org', true)
    AND operation_id IN (
      SELECT o.id FROM app.control_operations o
       WHERE o.requested_by = app.current_user_id() AND o.status = 'pending'
    )
  );

-- The request, saying it started; 0008's text plus one marked block

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
  -- 0011: the start, said (ADR 0297) --
  -- A long operation's request writes ONE notice in its own transaction, from
  -- a fixed template of the type and the key -- never an argument.
  IF p_type IN ('project.create', 'branch.create', 'restore.create', 'branch.reset') THEN
    INSERT INTO app.control_notifications
      (organization_id, project_key, kind, text, operation_id, operation_type)
    VALUES (p_org, p_project, 'operation_started',
            p_type || ' on ' || coalesce(p_project, 'a new project') || ' started',
            v_id, p_type);
  END IF;
  -- 0011: end --
  RETURN QUERY SELECT v_id, true;
END;
$$;
COMMENT ON FUNCTION app.control_request_operation(uuid, uuid, text, text, jsonb) IS
  'Records a member''s request: the role, then, under the organisation''s row lock, the plan''s projects_active and branches_total (AP409 plan_limit_reached / branch_limit_reached before any row, ADR 0274, D2521, D2538), the branch rules of 0006, one open operation per project and one open creation per organisation (D2166); a creation, a branch, a restore and a reset write an operation_started notice (ADR 0297).';

-- The finish, naming its operation; 0008's text with two members added

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
  INSERT INTO app.control_notifications (organization_id, project_key, kind, text, operation_id, operation_type)
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
         END,
    p_id, v_type
  );
  -- 0008: end --
END;
$$;
COMMENT ON FUNCTION app.control_finish_operation(uuid, text, text, jsonb, text) IS
  'Finishes a RUNNING operation: succeeded, or failed with an error code; a result member its type does not declare is refused, and only a succeeded export may carry a secret (D2151, D2164); and writes ONE notification in the same transaction from a fixed template (ADR 0275), naming the operation (ADR 0297). Granted to nobody.';

DROP FUNCTION app.control_list_notifications(uuid, uuid, integer);
CREATE FUNCTION app.control_list_notifications(p_user uuid, p_org uuid, p_limit integer)
  RETURNS TABLE (
    id uuid, project_key text, kind text, text varchar, created_at timestamptz,
    operation_id uuid, operation_type text
  )
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
    SELECT n.id, n.project_key, n.kind, n.text, n.created_at, n.operation_id, n.operation_type
      FROM app.control_notifications n
     WHERE n.organization_id = p_org
     ORDER BY n.created_at DESC, n.id
     LIMIT p_limit;
END;
$$;
COMMENT ON FUNCTION app.control_list_notifications(uuid, uuid, integer) IS
  'An organisation''s newest notifications (at most 200), each naming its operation when one wrote it (ADR 0297), viewer and above; no read state, no deletion (ADR 0275).';

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION app.control_operation_subject(text, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_operations(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_operation(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_notifications(uuid, uuid, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.control_list_operations(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_operation(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_notifications(uuid, uuid, integer) TO {{auth_service}};

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

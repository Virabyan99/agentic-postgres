-- migrate:up
-- Operations a member requests and the reconciler executes (Session 38;
-- ADR 0256, ADR 0257, ADR 0259, ADR 0260).
--
-- **Two writers, two doors.** A member REQUESTS an operation through the
-- control mode: `control_request_operation`, SECURITY DEFINER, granted to the
-- identity service, checks the caller's role here as well as in the route
-- (D2165, the D2106 two-layer rule) and inserts a `pending` row. The
-- reconciler -- root, on the host -- EXECUTES it: it claims, advances and
-- finishes rows through functions that are SECURITY INVOKER and granted to
-- nobody (D2093), reached the way `bin/control.sh` reaches this database, by
-- the bootstrap superuser over the container socket. Nothing in this file
-- gives the identity service a way to move an operation past `pending` or
-- `cancelled`.
--
-- **Serialisation is the bound on creation** (D2166): at most one
-- non-terminal operation per project and one non-terminal `project.create` per
-- organisation, each a partial unique index; with the slot stock (D2160) that
-- is the whole bound -- no time window is built.
--
-- **The one credential-shaped value** (D2164, ADR 0259): an export's download
-- URL, `result_secret`, written by the reconciler, returned ONCE to the member
-- who requested it and erased in the same statement
-- (`control_take_result_secret`). It is a presigned GET valid at most 900 s,
-- to one object.
--
-- **Slots** (D2149, D2160): `app.control_slots` is what the reconciler last
-- observed of the host's slots -- a reading, written whole by
-- `control_record_slots`, never a declaration. The control mode reads only how
-- many are `ready` and when they were observed.
--
-- The three released migrations are untouched (D912): what they created and
-- this file changes is ALTERed or dropped and re-created here.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The operations table, widened
-- ---------------------------------------------------------------------------

ALTER TABLE app.control_operations
  ALTER COLUMN status SET DEFAULT 'pending',
  ADD COLUMN claimed_by    text NULL CHECK (claimed_by ~ '^[A-Za-z0-9._:@-]{1,128}$'),
  ADD COLUMN attempt       integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
  ADD COLUMN step          text NULL CHECK (step ~ '^[a-z][a-z0-9-]{0,31}$'),
  ADD COLUMN result        jsonb NULL CHECK (jsonb_typeof(result) = 'object'),
  ADD COLUMN result_secret text NULL,
  ADD CONSTRAINT control_operations_arguments_object CHECK (jsonb_typeof(arguments) = 'object'),
  -- The operation outcomes (errors.OPERATION_ERROR_CODES); a refusal the API
  -- answers before a row exists is never one of these.
  ADD CONSTRAINT control_operations_error_code_check CHECK (error_code IN (
    'capacity_exhausted', 'invalid_request', 'operation_failed', 'interrupted',
    'could_not_determine'
  )),
  ADD CONSTRAINT control_operations_failed_has_a_code CHECK (
    (status = 'failed') = (error_code IS NOT NULL)
  ),
  ADD CONSTRAINT control_operations_secret_only_on_export CHECK (
    result_secret IS NULL OR (type = 'project.export' AND status = 'succeeded')
  );

-- D2166: one non-terminal creation per organisation, one non-terminal
-- operation per project.
CREATE UNIQUE INDEX control_operations_one_creation_per_organization
  ON app.control_operations (organization_id)
  WHERE type = 'project.create' AND status IN ('pending', 'running');
CREATE UNIQUE INDEX control_operations_one_per_project
  ON app.control_operations (project_key)
  WHERE status IN ('pending', 'running');

-- A member inserts only their own `pending` row, in the organisation a
-- function scoped after reading their membership; a member updates only their
-- own rows, or -- scoped the same way -- their organisation's. The functions
-- below decide WHICH update; the policies are the floor under them.
CREATE POLICY control_operations_insert ON app.control_operations
  FOR INSERT TO {{object_owner}}
  WITH CHECK (
    requested_by = app.current_user_id()
    AND organization_id::text = current_setting('app.control_org', true)
    AND status = 'pending'
  );
CREATE POLICY control_operations_update ON app.control_operations
  FOR UPDATE TO {{object_owner}}
  USING (
    requested_by = app.current_user_id()
    OR organization_id::text = current_setting('app.control_org', true)
  );

-- ---------------------------------------------------------------------------
-- The registry, widened (D2161, D2167, D2180)
-- ---------------------------------------------------------------------------

ALTER TABLE app.control_projects
  -- The customer's name for the project: a display name, never a key (D2180).
  ADD COLUMN display_name text NULL CHECK (display_name ~ '^[A-Za-z0-9 ._-]{1,48}$'),
  ADD COLUMN slot         text NULL CHECK (slot ~ '^slot[1-9][0-9]{0,2}-[a-z][a-z0-9-]{1,15}$'),
  ADD COLUMN region_id    text NULL CHECK (region_id ~ '^[a-z][a-z0-9-]{1,31}$'),
  ADD COLUMN profile      text NULL CHECK (profile IN ('small', 'standard', 'large')),
  -- The project's `routes.app`, copied from its deployed document, so a client
  -- can find the project it was handed (D2163's claim, Run 8).
  ADD COLUMN app_route    text NULL CHECK (app_route ~ '^https://[a-z0-9.-]+(:[0-9]+)?/[A-Za-z0-9/_.-]*$'),
  ADD COLUMN deleted_at   timestamptz NULL;
ALTER TABLE app.control_projects DROP CONSTRAINT control_projects_adopted_from_check;
ALTER TABLE app.control_projects ADD CONSTRAINT control_projects_adopted_from_check
  CHECK (adopted_from IN ('deployed_document', 'reconciler'));

-- ---------------------------------------------------------------------------
-- Slots: the reconciler's last reading of the host (D2149, D2160)
-- ---------------------------------------------------------------------------

CREATE TABLE app.control_slots (
  key         text PRIMARY KEY CHECK (key ~ '^slot[1-9][0-9]{0,2}-[a-z][a-z0-9-]{1,15}$'),
  -- `slot.state()`'s seven (D2149).
  state       text NOT NULL CHECK (state IN (
    'declared', 'prepared', 'ready', 'allocated', 'quarantined', 'consumed', 'undetermined'
  )),
  region_id   text NULL CHECK (region_id ~ '^[a-z][a-z0-9-]{1,31}$'),
  observed_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE app.control_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_slots FORCE ROW LEVEL SECURITY;

-- Slot names are not secret: any authenticated caller's function may read
-- them. No write policy -- only root writes the reading.
CREATE POLICY control_slots_read ON app.control_slots
  FOR SELECT TO {{object_owner}}
  USING (app.current_user_id() IS NOT NULL);

-- ---------------------------------------------------------------------------
-- What a finished operation may record (D2151): the members each type declares
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_result_members(p_type text) RETURNS text[]
  LANGUAGE sql IMMUTABLE STRICT
  SET search_path = pg_catalog, pg_temp
AS $$
  SELECT ARRAY['reason', 'refusal', 'step', 'steps'] || CASE p_type
    WHEN 'project.create' THEN ARRAY['profile', 'project_key', 'region']
    WHEN 'project.resize' THEN ARRAY['profile']
    WHEN 'project.export' THEN ARRAY['expires_at', 'sha256', 'size_bytes']
    ELSE ARRAY[]::text[]
  END;
$$;
COMMENT ON FUNCTION app.control_result_members(text) IS
  'The result members a finished operation of this type may record -- operations.RESULT_MEMBERS, which a test holds equal. Not granted: it runs inside control_finish_operation.';

-- ---------------------------------------------------------------------------
-- The member's functions: SECURITY DEFINER, granted to the identity service
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_request_operation(
  p_user uuid, p_org uuid, p_project text, p_type text, p_arguments jsonb
) RETURNS TABLE (operation_id uuid, created boolean)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_existing uuid;
  v_id uuid;
BEGIN
  PERFORM app.control_enter(p_user);
  -- The types Session 38 executes; the route refuses the rest first.
  IF p_type NOT IN (
    'project.create', 'project.delete', 'project.sleep', 'project.wake', 'project.resize',
    'project.export'
  ) OR jsonb_typeof(p_arguments) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'AP422: invalid_request';
  END IF;
  -- D2165, in SQL as well as in the route: delete is admin and above, every
  -- other write member and above.
  PERFORM app.control_require_role(
    p_org, CASE WHEN p_type = 'project.delete' THEN 'admin' ELSE 'member' END::app.control_role
  );
  IF p_type = 'project.create' THEN
    IF p_project IS NOT NULL THEN
      RAISE EXCEPTION 'AP422: invalid_request';
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
  'Records a pending operation for a member (member and above; delete admin and above, D2165), or answers the non-terminal one already holding its project or its organisation''s creation (created false, D2166).';

CREATE FUNCTION app.control_cancel_operation(p_user uuid, p_id uuid) RETURNS boolean
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_org uuid;
  v_requested_by uuid;
  v_role app.control_role;
BEGIN
  PERFORM app.control_enter(p_user);
  SELECT o.organization_id, o.requested_by INTO v_org, v_requested_by
    FROM app.control_operations o WHERE o.id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: not_found';
  END IF;
  v_role := app.control_require_role(v_org, 'viewer');
  -- The requester, or an admin or owner of the organisation (D2067).
  IF v_requested_by <> p_user AND app.control_role_rank(v_role) < app.control_role_rank('admin') THEN
    RAISE EXCEPTION 'AP403: authorization_failed';
  END IF;
  UPDATE app.control_operations o SET status = 'cancelled', finished_at = now()
   WHERE o.id = p_id AND o.status = 'pending';
  IF NOT FOUND THEN
    -- Running or terminal: only a pending row is cancelled.
    RAISE EXCEPTION 'AP409: conflict';
  END IF;
  RETURN true;
END;
$$;
COMMENT ON FUNCTION app.control_cancel_operation(uuid, uuid) IS
  'Cancels a PENDING operation: its requester, or an admin or owner of its organisation. A running or finished one is AP409 conflict.';

CREATE FUNCTION app.control_take_result_secret(p_user uuid, p_id uuid) RETURNS text
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_secret text;
BEGIN
  PERFORM app.control_enter(p_user);
  -- Read and erased in ONE statement, for the requester alone (D2164).
  UPDATE app.control_operations o SET result_secret = NULL
    FROM (
      SELECT i.id, i.result_secret FROM app.control_operations i
       WHERE i.id = p_id AND i.requested_by = p_user AND i.result_secret IS NOT NULL
       FOR UPDATE
    ) AS taken
   WHERE o.id = taken.id
  RETURNING taken.result_secret INTO v_secret;
  RETURN v_secret;
END;
$$;
COMMENT ON FUNCTION app.control_take_result_secret(uuid, uuid) IS
  'An export''s download URL, returned once to the member who requested it and erased in the same statement; NULL for anyone else or the second time (D2164, ADR 0259).';

CREATE FUNCTION app.control_ready_slot_count(p_user uuid)
  RETURNS TABLE (ready_slots integer, observed timestamptz)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT (count(*) FILTER (WHERE s.state = 'ready'))::integer, max(s.observed_at)
      FROM app.control_slots s;
END;
$$;
COMMENT ON FUNCTION app.control_ready_slot_count(uuid) IS
  'How many slots the reconciler last observed ready, and when -- the API''s no_slot reading, taken before any row is written (D2160). observed is NULL when nothing was ever recorded.';

CREATE FUNCTION app.control_project_operations(p_user uuid, p_key text DEFAULT NULL)
  RETURNS TABLE (
    project_key text, type text, status text, error_code text, created_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.project_key, o.type, o.status, o.error_code, o.created_at
      FROM app.control_operations o
     WHERE o.project_key IS NOT NULL AND (p_key IS NULL OR o.project_key = p_key)
     ORDER BY o.created_at, o.id;
END;
$$;
COMMENT ON FUNCTION app.control_project_operations(uuid, text) IS
  'The operation history of the caller''s organisations'' projects, oldest first -- what control_states.project_state derives a state from (D2159).';

-- The four readers, re-created wider. A changed RETURNS TABLE is a new
-- function, so each is dropped and created again, and its grant made again.
DROP FUNCTION app.control_list_projects(uuid, uuid);
DROP FUNCTION app.control_get_project(uuid, text);
DROP FUNCTION app.control_list_operations(uuid, uuid);
DROP FUNCTION app.control_get_operation(uuid, uuid);

CREATE FUNCTION app.control_list_projects(p_user uuid, p_org uuid DEFAULT NULL)
  RETURNS TABLE (
    key text, organization_id uuid, slug text, environment text, domain text,
    template_version text, source_commit text, adopted_at timestamptz, adopted_from text,
    display_name text, region_id text, profile text, app_route text, deleted_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT p.key, p.organization_id, p.slug, p.environment, p.domain, p.template_version,
           p.source_commit, p.adopted_at, p.adopted_from, p.display_name, p.region_id,
           p.profile, p.app_route, p.deleted_at
      FROM app.control_projects p
     WHERE p_org IS NULL OR p.organization_id = p_org
     ORDER BY p.key;
END;
$$;
COMMENT ON FUNCTION app.control_list_projects(uuid, uuid) IS
  'The registry rows of the caller''s organisations, optionally one organisation''s (ADR 0251), with Session 38''s members.';

CREATE FUNCTION app.control_get_project(p_user uuid, p_key text)
  RETURNS TABLE (
    key text, organization_id uuid, slug text, environment text, domain text,
    template_version text, source_commit text, adopted_at timestamptz, adopted_from text,
    display_name text, region_id text, profile text, app_route text, deleted_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT p.key, p.organization_id, p.slug, p.environment, p.domain, p.template_version,
           p.source_commit, p.adopted_at, p.adopted_from, p.display_name, p.region_id,
           p.profile, p.app_route, p.deleted_at
      FROM app.control_projects p
     WHERE p.key = p_key;
END;
$$;
COMMENT ON FUNCTION app.control_get_project(uuid, text) IS
  'One registry row of the caller''s organisations, or no row -- the same for a foreign project and a missing one (D2053).';

CREATE FUNCTION app.control_list_operations(p_user uuid, p_org uuid)
  RETURNS TABLE (
    id uuid, organization_id uuid, project_key text, type text, status text,
    progress integer, error_code text, created_at timestamptz, started_at timestamptz,
    finished_at timestamptz, requested_by uuid, step text, result jsonb
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.organization_id, o.project_key, o.type, o.status, o.progress, o.error_code,
           o.created_at, o.started_at, o.finished_at, o.requested_by, o.step, o.result
      FROM app.control_operations o
     WHERE o.organization_id = p_org
     ORDER BY o.created_at DESC, o.id;
END;
$$;
COMMENT ON FUNCTION app.control_list_operations(uuid, uuid) IS
  'An organisation''s operations, newest first. Never the result secret (D2164).';

CREATE FUNCTION app.control_get_operation(p_user uuid, p_id uuid)
  RETURNS TABLE (
    id uuid, organization_id uuid, project_key text, type text, status text,
    progress integer, error_code text, created_at timestamptz, started_at timestamptz,
    finished_at timestamptz, requested_by uuid, step text, result jsonb
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.organization_id, o.project_key, o.type, o.status, o.progress, o.error_code,
           o.created_at, o.started_at, o.finished_at, o.requested_by, o.step, o.result
      FROM app.control_operations o
     WHERE o.id = p_id;
END;
$$;
COMMENT ON FUNCTION app.control_get_operation(uuid, uuid) IS
  'One operation of the caller''s organisations, or no row (ADR 0254). Never the result secret: control_take_result_secret hands that out once (D2164).';

-- ---------------------------------------------------------------------------
-- The reconciler's functions: SECURITY INVOKER, granted to nobody (D2093,
-- D2151). Only the bootstrap superuser executes them, through the reconciler
-- and `bin/control.sh`, and the superuser is the one role row security does
-- not bind.
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_claim_operation(p_worker text)
  RETURNS TABLE (
    id uuid, organization_id uuid, project_key text, type text, arguments jsonb,
    attempt integer, requested_by uuid
  )
  LANGUAGE sql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
  -- The oldest pending row nobody holds: the row lock and SKIP LOCKED make two
  -- claimers take distinct rows without waiting for each other (D2191); the
  -- outer recheck refuses a row that stopped being pending meanwhile.
  UPDATE app.control_operations o
     SET status = 'running', started_at = now(), claimed_by = p_worker,
         attempt = o.attempt + 1
   WHERE o.id = (
           SELECT c.id FROM app.control_operations c
            WHERE c.status = 'pending'
            ORDER BY c.created_at, c.id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
         )
     AND o.status = 'pending'
  RETURNING o.id, o.organization_id, o.project_key, o.type, o.arguments, o.attempt,
            o.requested_by;
$$;
COMMENT ON FUNCTION app.control_claim_operation(text) IS
  'Claims the oldest pending operation for p_worker, or returns no row. Granted to nobody: the reconciler''s, run as the superuser (D2151, ADR 0256).';

CREATE FUNCTION app.control_advance_operation(
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
END;
$$;
COMMENT ON FUNCTION app.control_advance_operation(uuid, text, integer, text) IS
  'Records a running operation''s step and progress, and -- once, for a creation -- the project key its slot gave it. Granted to nobody (D2151).';

CREATE FUNCTION app.control_finish_operation(
  p_id uuid, p_status text, p_error_code text, p_result jsonb, p_result_secret text DEFAULT NULL
) RETURNS void
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_type text;
  v_status text;
  v_undeclared text[];
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
END;
$$;
COMMENT ON FUNCTION app.control_finish_operation(uuid, text, text, jsonb, text) IS
  'Finishes a RUNNING operation: succeeded, or failed with an error code; a result member its type does not declare is refused, and only a succeeded export may carry a secret. Granted to nobody (D2151, D2164).';

CREATE FUNCTION app.control_interrupted_operations()
  RETURNS TABLE (
    id uuid, organization_id uuid, project_key text, type text, step text, attempt integer,
    claimed_by text, started_at timestamptz
  )
  LANGUAGE sql STABLE SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
  SELECT o.id, o.organization_id, o.project_key, o.type, o.step, o.attempt, o.claimed_by,
         o.started_at
    FROM app.control_operations o
   WHERE o.status = 'running'
   ORDER BY o.started_at, o.id;
$$;
COMMENT ON FUNCTION app.control_interrupted_operations() IS
  'Every operation still running -- at the reconciler''s start, each was interrupted and is finished failed, never resumed (D2152). Granted to nobody.';

CREATE FUNCTION app.control_record_slots(p_slots jsonb) RETURNS integer
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_count integer;
BEGIN
  IF jsonb_typeof(p_slots) IS DISTINCT FROM 'array' OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(p_slots) AS s
     WHERE jsonb_typeof(s) <> 'object'
        OR EXISTS (
          SELECT 1 FROM jsonb_object_keys(s) AS k WHERE k NOT IN ('key', 'state', 'region_id')
        )
  ) THEN
    RAISE EXCEPTION 'AP422: invalid_slots';
  END IF;
  -- The reading is replaced whole: a slot no longer declared is no longer here.
  DELETE FROM app.control_slots;
  INSERT INTO app.control_slots (key, state, region_id, observed_at)
    SELECT s ->> 'key', s ->> 'state', s ->> 'region_id', now()
      FROM jsonb_array_elements(p_slots) AS s;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;
COMMENT ON FUNCTION app.control_record_slots(jsonb) IS
  'Replaces the slot reading with what slot.state() observed: [{key, state, region_id}]. Granted to nobody (D2160).';

CREATE FUNCTION app.control_mark_deleted(p_key text) RETURNS boolean
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  UPDATE app.control_projects p SET deleted_at = now()
   WHERE p.key = p_key AND p.deleted_at IS NULL;
  RETURN FOUND;
END;
$$;
COMMENT ON FUNCTION app.control_mark_deleted(text) IS
  'Marks a registry row deleted; the row stays as the record of what existed (D2167). Granted to nobody.';

-- The adoption, re-created with the Session 38 members (D2161, D2167). Every
-- new parameter defaults to NULL, so an operator's adoption passes what the
-- deployed document carries and nothing else; a row the reconciler made
-- (`p_slot` given) is `adopted_from = 'reconciler'`. A re-adoption never
-- erases a member it does not name, never changes who made the row, and never
-- revives a deleted project.
DROP FUNCTION app.control_adopt_project(text, uuid, text, text, text, text, text);
CREATE FUNCTION app.control_adopt_project(
  p_key text, p_org uuid, p_slug text, p_environment text, p_domain text,
  p_template_version text, p_source_commit text,
  p_region text DEFAULT NULL, p_profile text DEFAULT NULL, p_slot text DEFAULT NULL,
  p_app_route text DEFAULT NULL, p_display_name text DEFAULT NULL
) RETURNS text
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  INSERT INTO app.control_projects AS p
    (key, organization_id, slug, environment, domain, template_version, source_commit,
     adopted_from, region_id, profile, slot, app_route, display_name)
  VALUES
    (p_key, p_org, p_slug, p_environment, p_domain, p_template_version, p_source_commit,
     CASE WHEN p_slot IS NULL THEN 'deployed_document' ELSE 'reconciler' END,
     p_region, p_profile, p_slot, p_app_route, p_display_name)
  ON CONFLICT (key) DO UPDATE
    SET organization_id = EXCLUDED.organization_id, slug = EXCLUDED.slug,
        environment = EXCLUDED.environment, domain = EXCLUDED.domain,
        template_version = EXCLUDED.template_version, source_commit = EXCLUDED.source_commit,
        region_id = coalesce(EXCLUDED.region_id, p.region_id),
        profile = coalesce(EXCLUDED.profile, p.profile),
        slot = coalesce(EXCLUDED.slot, p.slot),
        app_route = coalesce(EXCLUDED.app_route, p.app_route),
        display_name = coalesce(EXCLUDED.display_name, p.display_name),
        adopted_at = now()
    WHERE p.deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP409: deleted';
  END IF;
  RETURN p_key;
END;
$$;
COMMENT ON FUNCTION app.control_adopt_project(text, uuid, text, text, text, text, text, text, text, text, text, text) IS
  'Adopts (or re-adopts) a project into the registry from its deployed document: by root through bin/control.sh adopt (D2068), or by the reconciler after an operation''s last deploy (D2167). Granted to nobody.';

DROP FUNCTION app.control_registry_rows();
CREATE FUNCTION app.control_registry_rows()
  RETURNS TABLE (
    key text, organization_id uuid, slug text, environment text, domain text,
    template_version text, source_commit text, adopted_at timestamptz, adopted_from text,
    display_name text, slot text, region_id text, profile text, app_route text,
    deleted_at timestamptz
  )
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN QUERY
    SELECT p.key, p.organization_id, p.slug, p.environment, p.domain, p.template_version,
           p.source_commit, p.adopted_at, p.adopted_from, p.display_name, p.slot, p.region_id,
           p.profile, p.app_route, p.deleted_at
      FROM app.control_projects p
     ORDER BY p.key;
END;
$$;
COMMENT ON FUNCTION app.control_registry_rows() IS
  'Every registry row, deleted ones included, for bin/control.sh registry to compare with the deployed documents. Granted to nobody (D2068, D2167).';

-- ---------------------------------------------------------------------------
-- The key vocabulary gains `projects:write` (D2165)
-- ---------------------------------------------------------------------------

ALTER TABLE app.control_keys DROP CONSTRAINT control_keys_scopes_check;
ALTER TABLE app.control_keys ADD CONSTRAINT control_keys_scopes_check CHECK (
  array_length(scopes, 1) IS NOT NULL
  AND scopes <@ ARRAY[
    'organizations:read', 'members:read', 'projects:read', 'operations:read', 'projects:write'
  ]
);

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION app.control_result_members(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_request_operation(uuid, uuid, text, text, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_cancel_operation(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_take_result_secret(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_ready_slot_count(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_project_operations(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_projects(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_project(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_operations(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_operation(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_claim_operation(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_advance_operation(uuid, text, integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_finish_operation(uuid, text, text, jsonb, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_interrupted_operations() FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_record_slots(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_mark_deleted(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_adopt_project(text, uuid, text, text, text, text, text, text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_registry_rows() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.control_request_operation(uuid, uuid, text, text, jsonb) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_cancel_operation(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_take_result_secret(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_ready_slot_count(uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_project_operations(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_projects(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_project(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_operations(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_operation(uuid, uuid) TO {{auth_service}};

-- There is no GRANT for `control_claim_operation`, `control_advance_operation`,
-- `control_finish_operation`, `control_interrupted_operations`,
-- `control_record_slots`, `control_mark_deleted`, `control_adopt_project`,
-- `control_registry_rows` or `control_result_members`, and that absence is the
-- decision (D2093, ADR 0256).

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

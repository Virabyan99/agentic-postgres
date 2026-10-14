-- migrate:up
-- Branches, restores to a branch, a branch's expiry, and the backups surface
-- (Session 40; ADR 0271, ADR 0272, ADR 0273).
--
-- **What a branch is, the control plane records; it never derives** (D2450).
-- `app.control_branches` is what the reconciler last read of each branch's
-- `branch.json` on the host, written whole by `control_record_branches` --
-- granted to nobody, reached as root through `container_exec`, like
-- `control_record_slots`. A member reads it through `control_list_branches`
-- and `control_get_branch`, which resolve the PROJECT first, so a foreign
-- project's branch, a missing project's and a missing branch of the caller's
-- own project are the one `not_found` (D2451).
--
-- **The backups surface is a recorded reading with its age** (ADR 0273):
-- `app.control_backup_readings`, one row per project, written by
-- `control_record_backups` every 900 s; the API serves a reading older than
-- 1,800 s, or one whose statuses could not be determined, as
-- `could_not_determine` -- never as a window.
--
-- **One live branch per project** (D2430): `control_request_operation` counts
-- the project's recorded live branches and its non-terminal `branch.create` /
-- `restore.create` rows, and refuses a second with `AP409:
-- branch_limit_reached` BEFORE any row exists. A branch's reset and deletion
-- name a recorded live branch (`AP404: not_found` otherwise); a project with a
-- live branch cannot be deleted (`AP409: conflict`, D2438). `branch.delete` is
-- admin and above, as `project.delete`; every other branch write member.
--
-- **A branch's expiry is a trigger** (ADR 0272, measured in rig 40d): the
-- `origin` column -- `member` for every row a person requests, `expiry` only
-- for a `branch.delete` -- and `control_request_expiry`, granted to nobody,
-- which inserts ONE deletion on behalf of the member whose operation set the
-- expiry, and nothing while any operation for the project is open.
--
-- The five released migrations are untouched (D912): what they created and
-- this file changes is ALTERed, or replaced with the same signature. 0003's
-- comment on the type CHECK names `src/agentic_postgres/operations.py`; the
-- table is `services/auth-api/app/operations.py` (D2447) -- an applied
-- migration's comment, so it is noted here and not edited.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- Who requested a row: a member, or a branch's expiry (ADR 0272)
-- ---------------------------------------------------------------------------

ALTER TABLE app.control_operations
  ADD COLUMN origin text NOT NULL DEFAULT 'member' CHECK (origin IN ('member', 'expiry')),
  ADD CONSTRAINT control_operations_expiry_deletes_a_branch
    CHECK (origin = 'member' OR type = 'branch.delete');

-- ---------------------------------------------------------------------------
-- The branches, as the reconciler last read them (D2450)
-- ---------------------------------------------------------------------------

CREATE TABLE app.control_branches (
  project_key     text NOT NULL REFERENCES app.control_projects(key),
  name            text NOT NULL CHECK (name ~ '^[a-z][a-z0-9]{1,11}$' AND name <> 'main'),
  -- `branch_record.STATES`, plus `undetermined` (a record that could not be
  -- read, ADR 0195) and `deleted` (no record any more).
  state           text NOT NULL CHECK (state IN (
    'creating', 'ready', 'stopped', 'failed', 'deleting', 'undetermined', 'deleted'
  )),
  requested_point timestamptz NULL,
  reached_point   timestamptz NULL,
  timeline        integer NULL CHECK (timeline IS NULL OR timeline >= 1),
  parent_commit   text NULL CHECK (parent_commit IS NULL OR parent_commit ~ '^[0-9a-f]{40}$'),
  pool_host       text NULL CHECK (pool_host IS NULL OR length(pool_host) <= 253),
  direct_host     text NULL CHECK (direct_host IS NULL OR length(direct_host) <= 253),
  expires_at      timestamptz NULL,
  expires_for     uuid NULL,
  created_at      timestamptz NULL,
  observed_at     timestamptz NOT NULL DEFAULT now(),
  deleted_at      timestamptz NULL,
  PRIMARY KEY (project_key, name),
  CONSTRAINT control_branches_expiry_names_its_member
    CHECK ((expires_at IS NULL) = (expires_for IS NULL)),
  CONSTRAINT control_branches_deleted_has_a_moment
    CHECK ((state = 'deleted') = (deleted_at IS NOT NULL))
);
ALTER TABLE app.control_branches ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_branches FORCE ROW LEVEL SECURITY;

-- A branch is readable where its project is: the subquery reads
-- `control_projects` under ITS row security, which shows the caller's
-- organisations' rows only.
CREATE POLICY control_branches_read ON app.control_branches
  FOR SELECT TO {{object_owner}}
  USING (project_key IN (SELECT p.key FROM app.control_projects p));

-- ---------------------------------------------------------------------------
-- The backups readings (ADR 0273)
-- ---------------------------------------------------------------------------

CREATE TABLE app.control_backup_readings (
  project_key       text PRIMARY KEY REFERENCES app.control_projects(key),
  observed_at       timestamptz NOT NULL DEFAULT now(),
  -- The doctor's three classifiers' verdicts (`diagnosis.repository`,
  -- `archiver`, `mirror`): OK, WARN, PROBLEM, or UNKNOWN.
  repository_status text NOT NULL CHECK (repository_status IN ('ok', 'warn', 'problem', 'unknown')),
  archiver_status   text NOT NULL CHECK (archiver_status IN ('ok', 'warn', 'problem', 'unknown')),
  mirror_status     text NOT NULL CHECK (mirror_status IN ('ok', 'warn', 'problem', 'unknown')),
  -- The oldest kept set's stop PLUS ONE SECOND (D2465), and the archiver's
  -- last archived time (D2456). NULL when not read.
  earliest          timestamptz NULL,
  latest            timestamptz NULL,
  last_full_at      timestamptz NULL,
  sleeping          boolean NOT NULL DEFAULT false,
  -- Why a status is not `ok`, in the reconciler's words: a fixed sentence or
  -- a classifier's own, never a value from the repository or a credential.
  reason            text NULL CHECK (reason IS NULL OR length(reason) <= 300)
);
ALTER TABLE app.control_backup_readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_backup_readings FORCE ROW LEVEL SECURITY;

CREATE POLICY control_backup_readings_read ON app.control_backup_readings
  FOR SELECT TO {{object_owner}}
  USING (project_key IN (SELECT p.key FROM app.control_projects p));

-- ---------------------------------------------------------------------------
-- The members' readers (D2451): the project first, then its branches
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_project_organization(p_key text) RETURNS uuid
  LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_org uuid;
BEGIN
  -- Row security shows the caller's organisations' rows only, so a foreign
  -- project, a missing one and a deleted one are the one `not_found` (D2053).
  SELECT p.organization_id INTO v_org
    FROM app.control_projects p
   WHERE p.key = p_key AND p.deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: not_found';
  END IF;
  RETURN v_org;
END;
$$;
COMMENT ON FUNCTION app.control_project_organization(text) IS
  'The organisation of a live project the caller''s row security shows, or AP404 -- the one answer for a foreign, a missing and a deleted project. Called inside the definer readers after control_enter.';

CREATE FUNCTION app.control_list_branches(p_user uuid, p_key text)
  RETURNS TABLE (
    name text, state text, requested_point timestamptz, reached_point timestamptz,
    timeline integer, pool_host text, direct_host text, expires_at timestamptz,
    created_at timestamptz, observed_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'viewer');
  RETURN QUERY
    SELECT b.name, b.state, b.requested_point, b.reached_point, b.timeline, b.pool_host,
           b.direct_host, b.expires_at, b.created_at, b.observed_at
      FROM app.control_branches b
     WHERE b.project_key = p_key AND b.state <> 'deleted'
     ORDER BY b.name;
END;
$$;
COMMENT ON FUNCTION app.control_list_branches(uuid, text) IS
  'A project''s live branches as the reconciler last recorded them, viewer and above; the project resolved first (D2451).';

CREATE FUNCTION app.control_get_branch(p_user uuid, p_key text, p_branch text)
  RETURNS TABLE (
    name text, state text, requested_point timestamptz, reached_point timestamptz,
    timeline integer, pool_host text, direct_host text, expires_at timestamptz,
    created_at timestamptz, observed_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'viewer');
  RETURN QUERY
    SELECT b.name, b.state, b.requested_point, b.reached_point, b.timeline, b.pool_host,
           b.direct_host, b.expires_at, b.created_at, b.observed_at
      FROM app.control_branches b
     WHERE b.project_key = p_key AND b.name = p_branch AND b.state <> 'deleted';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: not_found';
  END IF;
END;
$$;
COMMENT ON FUNCTION app.control_get_branch(uuid, text, text) IS
  'One live branch of a project, viewer and above; a missing branch of the caller''s own project is the same not_found as a foreign or missing project (D2451).';

CREATE FUNCTION app.control_get_backups(p_user uuid, p_key text)
  RETURNS TABLE (
    observed_at timestamptz, repository_status text, archiver_status text,
    mirror_status text, earliest timestamptz, latest timestamptz,
    last_full_at timestamptz, sleeping boolean, reason text
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'viewer');
  RETURN QUERY
    SELECT r.observed_at, r.repository_status, r.archiver_status, r.mirror_status,
           r.earliest, r.latest, r.last_full_at, r.sleeping, r.reason
      FROM app.control_backup_readings r
     WHERE r.project_key = p_key;
END;
$$;
COMMENT ON FUNCTION app.control_get_backups(uuid, text) IS
  'A project''s newest recorded backups reading, or no row when none was recorded; viewer and above (ADR 0273). The API decides whether it is a window.';

-- ---------------------------------------------------------------------------
-- The request, with the four branch types (D2430, D2433, D2438); same signature
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
    -- One live branch per project (D2430), before any row exists: a recorded
    -- branch that is not deleted, or a creation already asked for.
    IF p_type IN ('branch.create', 'restore.create') THEN
      PERFORM 1 FROM app.control_branches b
       WHERE b.project_key = p_project AND b.state <> 'deleted';
      IF FOUND THEN
        RAISE EXCEPTION 'AP409: branch_limit_reached';
      END IF;
      PERFORM 1 FROM app.control_operations o
       WHERE o.project_key = p_project AND o.type IN ('branch.create', 'restore.create')
         AND o.status IN ('pending', 'running');
      IF FOUND THEN
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

-- ---------------------------------------------------------------------------
-- What a finished operation may record (D2151, D2362, ADR 0271)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.control_result_members(p_type text) RETURNS text[]
  LANGUAGE sql IMMUTABLE STRICT
  SET search_path = pg_catalog, pg_temp
AS $$
  SELECT ARRAY['reason', 'refusal', 'step', 'steps'] || CASE p_type
    WHEN 'project.create' THEN ARRAY['profile', 'project_key', 'region']
    WHEN 'project.resize' THEN ARRAY['admission', 'profile']
    WHEN 'project.export' THEN ARRAY['expires_at', 'sha256', 'size_bytes']
    WHEN 'credential.rotate' THEN ARRAY['role']
    WHEN 'branch.create' THEN ARRAY['branch', 'direct_host', 'pool_host', 'reached_point', 'target_time', 'timeline']
    WHEN 'restore.create' THEN ARRAY['branch', 'direct_host', 'pool_host', 'reached_point', 'target_time', 'timeline']
    WHEN 'branch.reset' THEN ARRAY['branch', 'direct_host', 'pool_host', 'reached_point', 'target_time', 'timeline']
    WHEN 'branch.delete' THEN ARRAY['branch']
    ELSE ARRAY[]::text[]
  END;
$$;

-- ---------------------------------------------------------------------------
-- The reconciler's three (granted to nobody; reached as root, D2160)
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_record_branches(p_branches jsonb) RETURNS integer
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
            'parent_commit', 'pool_host', 'direct_host', 'expires_at', 'expires_for', 'created_at'
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
    pool_host, direct_host, expires_at, expires_for, created_at, observed_at, deleted_at
  )
  SELECT b ->> 'project_key', b ->> 'name', b ->> 'state',
         (b ->> 'requested_point')::timestamptz, (b ->> 'reached_point')::timestamptz,
         (b ->> 'timeline')::integer, b ->> 'parent_commit', b ->> 'pool_host',
         b ->> 'direct_host', (b ->> 'expires_at')::timestamptz, (b ->> 'expires_for')::uuid,
         (b ->> 'created_at')::timestamptz, now(), NULL
    FROM jsonb_array_elements(p_branches) AS b
  ON CONFLICT (project_key, name) DO UPDATE
    SET state = EXCLUDED.state, requested_point = EXCLUDED.requested_point,
        reached_point = EXCLUDED.reached_point, timeline = EXCLUDED.timeline,
        parent_commit = EXCLUDED.parent_commit, pool_host = EXCLUDED.pool_host,
        direct_host = EXCLUDED.direct_host, expires_at = EXCLUDED.expires_at,
        expires_for = EXCLUDED.expires_for, created_at = EXCLUDED.created_at,
        observed_at = now(), deleted_at = NULL;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;
COMMENT ON FUNCTION app.control_record_branches(jsonb) IS
  'Replaces the branch reading with what the reconciler read of every branch.json on the host: [{project_key, name, state, ...}]; a branch it no longer names is deleted. Granted to nobody (D2450).';

CREATE FUNCTION app.control_record_backups(p_readings jsonb) RETURNS integer
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_count integer;
BEGIN
  IF jsonb_typeof(p_readings) IS DISTINCT FROM 'array' OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(p_readings) AS r
     WHERE jsonb_typeof(r) <> 'object'
        OR NOT (r ? 'project_key' AND r ? 'repository_status' AND r ? 'archiver_status'
                AND r ? 'mirror_status')
        OR EXISTS (
          SELECT 1 FROM jsonb_object_keys(r) AS k WHERE k NOT IN (
            'project_key', 'repository_status', 'archiver_status', 'mirror_status',
            'earliest', 'latest', 'last_full_at', 'sleeping', 'reason'
          )
        )
  ) THEN
    RAISE EXCEPTION 'AP422: invalid_readings';
  END IF;
  INSERT INTO app.control_backup_readings AS c (
    project_key, observed_at, repository_status, archiver_status, mirror_status,
    earliest, latest, last_full_at, sleeping, reason
  )
  SELECT r ->> 'project_key', now(), r ->> 'repository_status', r ->> 'archiver_status',
         r ->> 'mirror_status', (r ->> 'earliest')::timestamptz, (r ->> 'latest')::timestamptz,
         (r ->> 'last_full_at')::timestamptz, coalesce((r ->> 'sleeping')::boolean, false),
         r ->> 'reason'
    FROM jsonb_array_elements(p_readings) AS r
  ON CONFLICT (project_key) DO UPDATE
    SET observed_at = now(), repository_status = EXCLUDED.repository_status,
        archiver_status = EXCLUDED.archiver_status, mirror_status = EXCLUDED.mirror_status,
        earliest = EXCLUDED.earliest, latest = EXCLUDED.latest,
        last_full_at = EXCLUDED.last_full_at, sleeping = EXCLUDED.sleeping,
        reason = EXCLUDED.reason;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;
COMMENT ON FUNCTION app.control_record_backups(jsonb) IS
  'Records each project''s backups reading, with now() as its age (ADR 0273): [{project_key, repository_status, archiver_status, mirror_status, earliest, latest, last_full_at, sleeping, reason}]. Granted to nobody.';

CREATE FUNCTION app.control_request_expiry(p_project text, p_branch text) RETURNS uuid
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_id uuid;
  v_branch app.control_branches%ROWTYPE;
BEGIN
  SELECT * INTO v_branch FROM app.control_branches
   WHERE project_key = p_project AND name = p_branch AND state = 'ready'
     AND expires_at IS NOT NULL AND expires_at <= now();
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  IF EXISTS (SELECT 1 FROM app.control_operations
              WHERE project_key = p_project AND status IN ('pending', 'running')) THEN
    RETURN NULL;
  END IF;
  INSERT INTO app.control_operations
    (organization_id, project_key, type, status, requested_by, arguments, origin)
    SELECT p.organization_id, p_project, 'branch.delete', 'pending', v_branch.expires_for,
           jsonb_build_object('branch', p_branch), 'expiry'
      FROM app.control_projects p WHERE p.key = p_project AND p.deleted_at IS NULL
    RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;
COMMENT ON FUNCTION app.control_request_expiry(text, text) IS
  'An expired ready branch''s deletion, ONE row, on behalf of the member whose operation set the expiry, origin expiry; NULL and nothing while any operation for the project is open (ADR 0272, rig 40d). Granted to nobody.';

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION app.control_project_organization(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_branches(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_branch(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_backups(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_record_branches(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_record_backups(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_request_expiry(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.control_list_branches(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_branch(uuid, text, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_backups(uuid, text) TO {{auth_service}};

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

-- migrate:up
-- Session 46 (ADR 0292; D2874, D2894, D2897): the support bundle -- the
-- doctor's verdicts on each deployed slot, recorded by the reconciler (which
-- runs the doctor as root and drops its evidence before anything is sent
-- here) and read by a member of the project's organisation. The control plane
-- reaches no project and runs no doctor (ADR 0246).
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The readings: one row per check per project, a project's set replaced whole
-- ---------------------------------------------------------------------------

CREATE TABLE app.control_diagnostic_readings (
  project_key text NOT NULL REFERENCES app.control_projects(key),
  -- The doctor's own check name (`containers`, `route health`, `tls`, ...), or
  -- `state` for a sleeping slot's one row.
  check_name  text NOT NULL CHECK (length(check_name) BETWEEN 1 AND 64),
  -- The doctor's order, so the bundle reads as `sudo bin/doctor.sh` does.
  position    smallint NOT NULL CHECK (position >= 0),
  -- `diagnosis`'s vocabulary, and `asleep` for a stopped database.
  verdict     text NOT NULL CHECK (verdict IN ('ok', 'warn', 'problem', 'unknown', 'asleep')),
  -- The check's sentence as the reconciler reduced it: a host path and an
  -- opaque run replaced inside it, at most 300 characters.
  detail      text NOT NULL CHECK (length(detail) <= 300),
  read_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_key, check_name)
);
ALTER TABLE app.control_diagnostic_readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_diagnostic_readings FORCE ROW LEVEL SECURITY;
CREATE POLICY control_diagnostic_readings_read ON app.control_diagnostic_readings
  FOR SELECT TO {{object_owner}}
  USING (project_key IN (SELECT p.key FROM app.control_projects p));

-- ---------------------------------------------------------------------------
-- The reconciler's writer (granted to nobody; reached as root)
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_record_diagnostics(p_readings jsonb) RETURNS integer
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_count integer := 0;
  v_added integer;
  v_reading jsonb;
  v_key text;
BEGIN
  IF jsonb_typeof(p_readings) IS DISTINCT FROM 'array' OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(p_readings) AS r
     WHERE jsonb_typeof(r) <> 'object'
        OR jsonb_typeof(r -> 'project_key') IS DISTINCT FROM 'string'
        OR EXISTS (
          SELECT 1 FROM jsonb_object_keys(r) AS k WHERE k NOT IN ('project_key', 'checks', 'asleep')
        )
        -- Exactly one of the two shapes: a sleeping slot, or its checks.
        OR (r ? 'asleep') = (r ? 'checks')
        OR (r ? 'asleep' AND r -> 'asleep' IS DISTINCT FROM 'true'::jsonb)
        OR (r ? 'checks' AND (
              jsonb_typeof(r -> 'checks') IS DISTINCT FROM 'array'
              OR jsonb_array_length(r -> 'checks') NOT BETWEEN 1 AND 32
              OR EXISTS (
                SELECT 1 FROM jsonb_array_elements(r -> 'checks') AS c
                 WHERE jsonb_typeof(c) <> 'object'
                    OR jsonb_typeof(c -> 'name') IS DISTINCT FROM 'string'
                    OR jsonb_typeof(c -> 'detail') IS DISTINCT FROM 'string'
                    OR NOT (c ->> 'verdict' = ANY (ARRAY['ok', 'warn', 'problem', 'unknown']))
                    OR EXISTS (
                      SELECT 1 FROM jsonb_object_keys(c) AS k
                       WHERE k NOT IN ('name', 'verdict', 'detail')
                    )
              )
            ))
  ) THEN
    RAISE EXCEPTION 'AP422: invalid_readings';
  END IF;
  FOR v_reading IN SELECT r FROM jsonb_array_elements(p_readings) AS r LOOP
    v_key := v_reading ->> 'project_key';
    DELETE FROM app.control_diagnostic_readings WHERE project_key = v_key;
    IF v_reading ? 'asleep' THEN
      INSERT INTO app.control_diagnostic_readings (project_key, check_name, position, verdict, detail)
      VALUES (v_key, 'state', 0, 'asleep',
              'The project sleeps; its checks run again once it is woken.');
    ELSE
      INSERT INTO app.control_diagnostic_readings (project_key, check_name, position, verdict, detail)
      SELECT v_key, c.value ->> 'name', (c.ordinality - 1)::smallint, c.value ->> 'verdict',
             c.value ->> 'detail'
        FROM jsonb_array_elements(v_reading -> 'checks') WITH ORDINALITY AS c;
    END IF;
    GET DIAGNOSTICS v_added = ROW_COUNT;
    v_count := v_count + v_added;
  END LOOP;
  RETURN v_count;
END;
$$;
COMMENT ON FUNCTION app.control_record_diagnostics(jsonb) IS
  'Replaces each named project''s diagnostic readings, read_at now() (ADR 0292): [{project_key, checks: [1..32 of {name, verdict, detail}]} or {project_key, asleep: true}]; any other member, an evidence member included, is AP422 and nothing is written. Granted to nobody.';

-- ---------------------------------------------------------------------------
-- The member's reader
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_project_diagnostics(p_user uuid, p_key text)
  RETURNS TABLE (check_name text, verdict text, detail text, read_at timestamptz)
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'member');
  RETURN QUERY
    SELECT r.check_name, r.verdict, r.detail, r.read_at
      FROM app.control_diagnostic_readings r
     WHERE r.project_key = p_key
     ORDER BY r.position, r.check_name;
END;
$$;
COMMENT ON FUNCTION app.control_project_diagnostics(uuid, text) IS
  'A project''s recorded diagnostic readings in the doctor''s order, member and above (ADR 0292); no row when none was recorded. The API decides whether they are stale. A foreign and a missing project are the one not_found.';

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION app.control_record_diagnostics(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_project_diagnostics(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.control_project_diagnostics(uuid, text) TO {{auth_service}};

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

-- migrate:up
-- The project registry and the operations table (ADR 0251, ADR 0254).
--
-- **The registry is the control plane's own record, written by root.** A row
-- is adopted from a project's DEPLOYED DOCUMENT by `sudo bin/control.sh adopt`
-- (D2068) through `control_adopt_project`, which is granted to nobody: no
-- route lets a customer decide what exists. ADR 0185 is superseded for the
-- control plane by this table and stands for everything else.
--
-- **No function inserts an operation** (D2054). The table is the shape Session
-- 38 fills; `GET /v1/operations` reads it, empty. An operation type is
-- accepted only when its Reality Ledger row is `available` or `beta`
-- (ADR 0254), and in Session 37 none is: `POST /v1/projects` answers
-- `409 not_available` in the control mode and writes no row here.
SET LOCAL ROLE {{object_owner}};

CREATE TABLE app.control_projects (
  key              text PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9-]{2,30}-[a-z][a-z0-9-]{1,15}$'),
  organization_id  uuid NOT NULL REFERENCES app.control_organizations(id),
  slug             text NOT NULL,
  environment      text NOT NULL,
  domain           text NOT NULL,
  template_version text NOT NULL,
  source_commit    text NOT NULL,
  adopted_at       timestamptz NOT NULL DEFAULT now(),
  adopted_from     text NOT NULL CHECK (adopted_from = 'deployed_document')
);

CREATE TABLE app.control_operations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES app.control_organizations(id),
  project_key     text NULL,
  -- The closed type table of `src/agentic_postgres/operations.py` (D2054).
  type            text NOT NULL CHECK (type IN (
    'project.create', 'project.delete', 'project.sleep', 'project.wake', 'project.resize',
    'project.export', 'branch.create', 'branch.reset', 'branch.delete', 'restore.create',
    'credential.rotate'
  )),
  status          text NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
  progress        integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  requested_by    uuid NOT NULL,
  arguments       jsonb NOT NULL,
  error_code      text NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  started_at      timestamptz NULL,
  finished_at     timestamptz NULL
);

ALTER TABLE app.control_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_projects FORCE ROW LEVEL SECURITY;
ALTER TABLE app.control_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_operations FORCE ROW LEVEL SECURITY;

-- Readable by the members of the owning organisation. No write policy: the
-- registry is written only by root, whom row security does not bind, and
-- nothing writes an operation yet.
CREATE POLICY control_projects_read ON app.control_projects
  FOR SELECT TO {{object_owner}}
  USING (
    organization_id IN (
      SELECT m.organization_id FROM app.control_memberships m
      WHERE m.user_id = app.current_user_id()
    )
  );
CREATE POLICY control_operations_read ON app.control_operations
  FOR SELECT TO {{object_owner}}
  USING (
    organization_id IN (
      SELECT m.organization_id FROM app.control_memberships m
      WHERE m.user_id = app.current_user_id()
    )
  );

CREATE FUNCTION app.control_list_projects(p_user uuid, p_org uuid DEFAULT NULL)
  RETURNS TABLE (
    key text, organization_id uuid, slug text, environment text, domain text,
    template_version text, source_commit text, adopted_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT p.key, p.organization_id, p.slug, p.environment, p.domain, p.template_version,
           p.source_commit, p.adopted_at
      FROM app.control_projects p
     WHERE p_org IS NULL OR p.organization_id = p_org
     ORDER BY p.key;
END;
$$;
COMMENT ON FUNCTION app.control_list_projects(uuid, uuid) IS
  'The registry rows of the caller''s organisations, optionally one organisation''s (ADR 0251).';

CREATE FUNCTION app.control_get_project(p_user uuid, p_key text)
  RETURNS TABLE (
    key text, organization_id uuid, slug text, environment text, domain text,
    template_version text, source_commit text, adopted_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT p.key, p.organization_id, p.slug, p.environment, p.domain, p.template_version,
           p.source_commit, p.adopted_at
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
    finished_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.organization_id, o.project_key, o.type, o.status, o.progress, o.error_code,
           o.created_at, o.started_at, o.finished_at
      FROM app.control_operations o
     WHERE o.organization_id = p_org
     ORDER BY o.created_at DESC, o.id;
END;
$$;
COMMENT ON FUNCTION app.control_list_operations(uuid, uuid) IS
  'An organisation''s operations, newest first -- empty in Session 37, when no type is accepted (ADR 0254).';

CREATE FUNCTION app.control_get_operation(p_user uuid, p_id uuid)
  RETURNS TABLE (
    id uuid, organization_id uuid, project_key text, type text, status text,
    progress integer, error_code text, created_at timestamptz, started_at timestamptz,
    finished_at timestamptz
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.organization_id, o.project_key, o.type, o.status, o.progress, o.error_code,
           o.created_at, o.started_at, o.finished_at
      FROM app.control_operations o
     WHERE o.id = p_id;
END;
$$;
COMMENT ON FUNCTION app.control_get_operation(uuid, uuid) IS
  'One operation of the caller''s organisations, or no row (ADR 0254).';

-- The operator's two, SECURITY INVOKER and granted to nobody: only the
-- bootstrap superuser executes them, through `sudo bin/control.sh` (D2068),
-- and the superuser is the one role row security does not bind.
CREATE FUNCTION app.control_adopt_project(
  p_key text, p_org uuid, p_slug text, p_environment text, p_domain text,
  p_template_version text, p_source_commit text
) RETURNS text
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  INSERT INTO app.control_projects AS p
    (key, organization_id, slug, environment, domain, template_version, source_commit,
     adopted_from)
  VALUES
    (p_key, p_org, p_slug, p_environment, p_domain, p_template_version, p_source_commit,
     'deployed_document')
  ON CONFLICT (key) DO UPDATE
    SET organization_id = EXCLUDED.organization_id, slug = EXCLUDED.slug,
        environment = EXCLUDED.environment, domain = EXCLUDED.domain,
        template_version = EXCLUDED.template_version, source_commit = EXCLUDED.source_commit,
        adopted_at = now();
  RETURN p_key;
END;
$$;
COMMENT ON FUNCTION app.control_adopt_project(text, uuid, text, text, text, text, text) IS
  'Adopts (or re-adopts) a project into the registry from its deployed document. Granted to nobody; run by root through bin/control.sh adopt (D2068).';

CREATE FUNCTION app.control_registry_rows()
  RETURNS TABLE (
    key text, organization_id uuid, slug text, environment text, domain text,
    template_version text, source_commit text, adopted_at timestamptz
  )
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN QUERY
    SELECT p.key, p.organization_id, p.slug, p.environment, p.domain, p.template_version,
           p.source_commit, p.adopted_at
      FROM app.control_projects p
     ORDER BY p.key;
END;
$$;
COMMENT ON FUNCTION app.control_registry_rows() IS
  'Every registry row, for bin/control.sh registry to compare with the deployed documents. Granted to nobody (D2068).';

REVOKE ALL ON FUNCTION app.control_list_projects(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_project(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_list_operations(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_operation(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_adopt_project(text, uuid, text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_registry_rows() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.control_list_projects(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_project(uuid, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_list_operations(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_operation(uuid, uuid) TO {{auth_service}};

-- There is no GRANT for `control_adopt_project`, `control_registry_rows` or
-- `control_totp_reset`, and that absence is the decision (ADR 0251).

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

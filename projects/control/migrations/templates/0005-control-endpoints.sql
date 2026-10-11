-- migrate:up
-- A project's public endpoints in the registry, the customer's credential
-- rotation, and admission's reading in a resize's result (Session 39; ADR
-- 0268, ADR 0269, ADR 0270).
--
-- **The registry copies the address; it never derives one** (D2351, ADR 0158).
-- `endpoints` is the deployed document's `database.public`, written by
-- `control_adopt_project` -- root's `bin/control.sh adopt` and the
-- reconciler's refresh after an operation's deploy -- and read by a member
-- through `control_project_endpoints`. NULL is "never recorded"; a document
-- whose project has no doors records `{"enabled": false, ...}`, which the API
-- answers exactly as it answers NULL: `not_available`.
--
-- **`credential.rotate` is requested like every other write** (D2330):
-- `control_request_operation` gains the type, member and above, and the row
-- carries `{role, verifier}` -- a SCRAM verifier, never a password; the route
-- and the reconciler each validate it against the argument schema. Nothing in
-- this set can read a customer's password, because none exists here.
--
-- **A resize's result may carry `admission`** (D2362, ADR 0270): the reading
-- the reconciler's own `admit.sh --json` printed, so a proof can compare a
-- resize's outcome with the reading that decided it through `/v1`.
--
-- The four released migrations are untouched (D912): what they created and
-- this file changes is ALTERed, or replaced with the same signature, or
-- dropped and re-created here.
SET LOCAL ROLE {{object_owner}};

ALTER TABLE app.control_projects
  ADD COLUMN endpoints jsonb NULL CHECK (endpoints IS NULL OR jsonb_typeof(endpoints) = 'object');

-- ---------------------------------------------------------------------------
-- The adoption, re-created with the endpoints (D2351)
-- ---------------------------------------------------------------------------

-- As 0004's: every new parameter defaults to NULL, a re-adoption never erases
-- a member it does not name, never changes who made the row, never revives a
-- deleted project. An adoption that names the endpoints replaces them whole.
DROP FUNCTION app.control_adopt_project(text, uuid, text, text, text, text, text, text, text, text, text, text);
CREATE FUNCTION app.control_adopt_project(
  p_key text, p_org uuid, p_slug text, p_environment text, p_domain text,
  p_template_version text, p_source_commit text,
  p_region text DEFAULT NULL, p_profile text DEFAULT NULL, p_slot text DEFAULT NULL,
  p_app_route text DEFAULT NULL, p_display_name text DEFAULT NULL,
  p_endpoints jsonb DEFAULT NULL
) RETURNS text
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  INSERT INTO app.control_projects AS p
    (key, organization_id, slug, environment, domain, template_version, source_commit,
     adopted_from, region_id, profile, slot, app_route, display_name, endpoints)
  VALUES
    (p_key, p_org, p_slug, p_environment, p_domain, p_template_version, p_source_commit,
     CASE WHEN p_slot IS NULL THEN 'deployed_document' ELSE 'reconciler' END,
     p_region, p_profile, p_slot, p_app_route, p_display_name, p_endpoints)
  ON CONFLICT (key) DO UPDATE
    SET organization_id = EXCLUDED.organization_id, slug = EXCLUDED.slug,
        environment = EXCLUDED.environment, domain = EXCLUDED.domain,
        template_version = EXCLUDED.template_version, source_commit = EXCLUDED.source_commit,
        region_id = coalesce(EXCLUDED.region_id, p.region_id),
        profile = coalesce(EXCLUDED.profile, p.profile),
        slot = coalesce(EXCLUDED.slot, p.slot),
        app_route = coalesce(EXCLUDED.app_route, p.app_route),
        display_name = coalesce(EXCLUDED.display_name, p.display_name),
        endpoints = coalesce(EXCLUDED.endpoints, p.endpoints),
        adopted_at = now()
    WHERE p.deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP409: deleted';
  END IF;
  RETURN p_key;
END;
$$;
COMMENT ON FUNCTION app.control_adopt_project(text, uuid, text, text, text, text, text, text, text, text, text, text, jsonb) IS
  'Adopts (or re-adopts) a project into the registry from its deployed document, with its database.public as endpoints (D2351): by root through bin/control.sh adopt (D2068), or by the reconciler after an operation''s last deploy (D2167). Granted to nobody.';

-- ---------------------------------------------------------------------------
-- The member's reader (D2351)
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_project_endpoints(p_user uuid, p_key text) RETURNS jsonb
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_org uuid;
  v_endpoints jsonb;
BEGIN
  PERFORM app.control_enter(p_user);
  -- Row security shows the caller's organisations' rows only, so a foreign
  -- project, a missing one and a deleted one are the one `not_found` (D2053).
  SELECT p.organization_id, p.endpoints INTO v_org, v_endpoints
    FROM app.control_projects p
   WHERE p.key = p_key AND p.deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: not_found';
  END IF;
  PERFORM app.control_require_role(v_org, 'viewer');
  RETURN v_endpoints;
END;
$$;
COMMENT ON FUNCTION app.control_project_endpoints(uuid, text) IS
  'A project''s recorded endpoints (the deployed document''s database.public), viewer and above; NULL when never recorded. No password: none exists in this plane (ADR 0269).';

-- ---------------------------------------------------------------------------
-- The request, with credential.rotate (D2330); same signature, so the grant stands
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
BEGIN
  PERFORM app.control_enter(p_user);
  -- The types the reconciler executes; the route refuses the rest first.
  IF p_type NOT IN (
    'project.create', 'project.delete', 'project.sleep', 'project.wake', 'project.resize',
    'project.export', 'credential.rotate'
  ) OR jsonb_typeof(p_arguments) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'AP422: invalid_request';
  END IF;
  -- D2165, in SQL as well as in the route: delete is admin and above, every
  -- other write (a credential rotation included) member and above.
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

-- ---------------------------------------------------------------------------
-- What a finished operation may record (D2151, D2362)
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
    ELSE ARRAY[]::text[]
  END;
$$;

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION app.control_adopt_project(text, uuid, text, text, text, text, text, text, text, text, text, text, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_project_endpoints(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.control_project_endpoints(uuid, text) TO {{auth_service}};

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

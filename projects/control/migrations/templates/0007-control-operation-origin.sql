-- migrate:up
-- An operation read names who requested it: a member, or a branch's expiry
-- (Session 40; ADR 0272, D2480).
--
-- `control_operations.origin` (0006) is written by `control_request_expiry`
-- alone as `expiry`, and by every other insert as `member`. Until this set the
-- two readers a member reaches -- `control_list_operations` and
-- `control_get_operation` -- named neither, so a customer could not tell the
-- deletion its own expiry requested from one a member asked for, and the live
-- proof that the trigger fired (BR-LIVE-001) had nothing to read through `/v1`.
--
-- The six released migrations are untouched (D912). A changed RETURNS TABLE is
-- a new function, so each reader is dropped and created again, wider by the one
-- column, and its grant made again -- 0004's shape.
SET LOCAL ROLE {{object_owner}};

DROP FUNCTION app.control_list_operations(uuid, uuid);
DROP FUNCTION app.control_get_operation(uuid, uuid);

CREATE FUNCTION app.control_list_operations(p_user uuid, p_org uuid)
  RETURNS TABLE (
    id uuid, organization_id uuid, project_key text, type text, status text,
    progress integer, error_code text, created_at timestamptz, started_at timestamptz,
    finished_at timestamptz, requested_by uuid, step text, result jsonb, origin text
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.organization_id, o.project_key, o.type, o.status, o.progress, o.error_code,
           o.created_at, o.started_at, o.finished_at, o.requested_by, o.step, o.result, o.origin
      FROM app.control_operations o
     WHERE o.organization_id = p_org
     ORDER BY o.created_at DESC, o.id;
END;
$$;
COMMENT ON FUNCTION app.control_list_operations(uuid, uuid) IS
  'An organisation''s operations, newest first, each naming its origin (member | expiry, D2480). Never the result secret (D2164).';

CREATE FUNCTION app.control_get_operation(p_user uuid, p_id uuid)
  RETURNS TABLE (
    id uuid, organization_id uuid, project_key text, type text, status text,
    progress integer, error_code text, created_at timestamptz, started_at timestamptz,
    finished_at timestamptz, requested_by uuid, step text, result jsonb, origin text
  )
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM app.control_enter(p_user);
  RETURN QUERY
    SELECT o.id, o.organization_id, o.project_key, o.type, o.status, o.progress, o.error_code,
           o.created_at, o.started_at, o.finished_at, o.requested_by, o.step, o.result, o.origin
      FROM app.control_operations o
     WHERE o.id = p_id;
END;
$$;
COMMENT ON FUNCTION app.control_get_operation(uuid, uuid) IS
  'One operation of the caller''s organisations, or no row (ADR 0254), naming its origin (member | expiry, D2480). Never the result secret: control_take_result_secret hands that out once (D2164).';

REVOKE ALL ON FUNCTION app.control_list_operations(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_get_operation(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.control_list_operations(uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_get_operation(uuid, uuid) TO {{auth_service}};

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

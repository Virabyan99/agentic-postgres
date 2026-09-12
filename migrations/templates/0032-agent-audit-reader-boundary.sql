-- migrate:up
-- The reader returns the boundary that refused (ADR 0178).
--
-- **This is the same defect 0020 exists to fix, one column later.** 0019 built
-- two indexes for a reader nobody created; 0027 added a column no reader
-- returns. `app_private.agent_audit.denial_reason` has recorded which boundary
-- refused since 0027, and `auth_list_agent_audit` -- created by 0020, before
-- the column existed, and never widened -- returns twelve columns that are not
-- it. `GET /admin/audit` is the ONE read path to the record (ADR 0142), so a
-- person reading a refusal sees that it was refused and not what refused it,
-- which is the single fact ADR 0178 exists to record. D1247, found by building
-- the first reader that shows a whole row to a person.
--
-- Measured before this file was written (rig 24c, Session 24 Run 1, on a
-- cluster carrying all thirty-one released migrations and the example set):
-- `pg_get_function_result` lists twelve columns and no `denial_reason`;
-- `SELECT denial_reason FROM app_private.auth_list_agent_audit(NULL, NULL, 10)`
-- is `column "denial_reason" does not exist`.
--
-- ---------------------------------------------------------------------------
-- Why DROP and CREATE rather than CREATE OR REPLACE
-- ---------------------------------------------------------------------------
--
-- Because PostgreSQL refuses the alternative. Measured on the pinned 18.4, with
-- the widened `RETURNS TABLE` and nothing else changed:
--
--   ERROR:  cannot change return type of existing function
--
-- A `RETURNS TABLE` is part of the function's result type, so adding a column
-- to it is a new signature as far as `CREATE OR REPLACE` is concerned. There is
-- no form of this migration that does not drop.
--
-- **The arity does not move.** Three arguments before, three after
-- (`pronargs` 3 and 3, measured either side of the apply), so ADR 0175's guard
-- is untouched and every call site -- `repository.py`'s
-- `SELECT * FROM app_private.auth_list_agent_audit(%s, %s, %s)`, the only one --
-- keeps working without being edited. That is the whole reason the widening is
-- a column on the result and not a fourth parameter: a filter would move the
-- arity, and every caller with it (ADR 0175, D857).
--
-- **`SELECT *` is what makes the service's half free.** The repository names no
-- columns, so the new one arrives at the route as a key in the row mapping;
-- what the route does with it is the route's change, in the same commit.
--
-- ---------------------------------------------------------------------------
-- Why the grant is re-issued
-- ---------------------------------------------------------------------------
--
-- A DROP takes its grants with it, and this is measured rather than recalled.
-- In rig 24c, between the CREATE and the GRANT below, the auth service was
-- answered:
--
--   ERROR:  permission denied for function auth_list_agent_audit
--
-- and after the GRANT it read both rows. 0027 re-granted for the same reason
-- and wrote it down; 0020's own comment explains why the grantee is
-- `auth_service` and nobody else, and that argument is unchanged -- this
-- migration widens a result, not an audience.
--
-- The `REVOKE ... FROM PUBLIC` is re-issued for the reason 0020 gives: a newly
-- created function is EXECUTABLE BY PUBLIC the moment it exists (D57, D262),
-- and the function this file drops had that revoked. Dropping and recreating
-- without it would hand the audit record to every role in the cluster.
--
-- ---------------------------------------------------------------------------
-- What is NOT here
-- ---------------------------------------------------------------------------
--
-- **No new filter and no window.** The stage plan wants `/admin/audit`
-- filterable by outcome, boundary and time; that is a fourth, fifth and sixth
-- argument, which is the arity move this file is written to avoid, plus a
-- cursor design nobody has priced (D1248). It is stated in Session 24's §10 and
-- not taken. The viewer fetches a page and renders it whole.
--
-- **No retention.** 0020 said it and it is still true: nothing prunes this
-- table, a DELETE path here would be a second write authority over a table
-- whose append-only property is stated in its own comment, and the decision
-- belongs to whoever owns the compliance meaning of the record (D1255).
SET LOCAL ROLE {{object_owner}};

DROP FUNCTION app_private.auth_list_agent_audit(uuid, uuid, integer);

-- Byte for byte 0020's function with one column appended to the result and one
-- to the SELECT list. Everything else -- `STABLE`, `SECURITY DEFINER`, the
-- `search_path`, the two `IS NULL OR` filters, the `started_at DESC, id DESC`
-- tiebreak that keeps a row from appearing in no page, the unclamped
-- `p_limit` whose one authority is the route -- is 0020's, and 0020's comments
-- are the argument for each of them.
--
-- `denial_reason` is LAST, after `completed_at`, because a `SELECT *` caller
-- reads a mapping and an ordered reader reads positions: appending is the only
-- placement that cannot move a column under a caller that indexes by number.
CREATE FUNCTION app_private.auth_list_agent_audit(
  p_agent_id uuid,
  p_owner_id uuid,
  p_limit    integer
)
  RETURNS TABLE (
    id            uuid,
    source        app_private.agent_audit_source,
    agent_id      uuid,
    owner_id      uuid,
    tool          text,
    request_id    uuid,
    parameters    jsonb,
    outcome       app_private.agent_audit_outcome,
    row_count     integer,
    elapsed_ms    integer,
    started_at    timestamptz,
    completed_at  timestamptz,
    denial_reason app_private.agent_denial_reason
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT r.id, r.source, r.agent_id, r.owner_id, r.tool, r.request_id,
           r.parameters, r.outcome, r.row_count, r.elapsed_ms,
           r.started_at, r.completed_at, r.denial_reason
    FROM app_private.agent_audit r
    WHERE (p_agent_id IS NULL OR r.agent_id = p_agent_id)
      AND (p_owner_id IS NULL OR r.owner_id = p_owner_id)
    ORDER BY r.started_at DESC, r.id DESC
    LIMIT p_limit
  $fn$;

COMMENT ON FUNCTION app_private.auth_list_agent_audit(uuid, uuid, integer) IS
  'The only read path to app_private.agent_audit (ADR 0142), returning the '
  'boundary that refused (ADR 0178). Granted to auth_service alone, which '
  'reaches it from GET /admin/audit behind the admin_audit:read scope. Both '
  'filters are optional and neither widens what the caller may see: an '
  'administrator holding the scope may read the whole record, so p_agent_id '
  'and p_owner_id narrow a permitted read rather than authorize one. The bound '
  'on p_limit is the route''s and is not restated here. denial_reason is '
  'non-null exactly on refused rows, by 0027''s CHECK -- and NULL on a refusal '
  'written before 0027 existed, which that constraint is NOT VALID for (D940).';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- Both statements run as the object owner, which owns the function this file
-- just created (D285, ADR 0091), and the `RESET ROLE` is at the end of the file
-- where every migration in this set has it.
REVOKE ALL ON FUNCTION
  app_private.auth_list_agent_audit(uuid, uuid, integer) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
  app_private.auth_list_agent_audit(uuid, uuid, integer) TO {{auth_service}};

RESET ROLE;

-- Nothing in `api` moved, so no NOTIFY: 0020's closing note applies unchanged.
-- `app_private` is not the exposed schema, and announcing a schema reload for a
-- change PostgREST cannot see is a notification a reader would have to explain.

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

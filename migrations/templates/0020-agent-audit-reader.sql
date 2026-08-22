-- migrate:up
-- The one reader of the audit record, and the grant that makes it reachable.
--
-- **This is 0020 and not an edit to 0019** (ADR 0091). 0019 is released and its
-- `released.lock.json` entry is frozen; a released migration that applies
-- perfectly well is not edited, whether or not any cluster has run it yet.
--
-- **Why this migration exists at all is a defect in 0019, and it is D501.**
-- 0019 created `app_private.agent_audit` and two indexes, and its own comment
-- above them says what they are for: *"The admin query endpoint (Run 7) reads
-- by owner and by agent, most recent first. Both indexes exist for that one
-- reader; neither is speculative."* The reader was not created and
-- `auth_service` was granted nothing. `services/auth-api/app/repository.py`'s
-- header states the constraint the omission runs into -- *"Fourteen function
-- calls and no table names. `auth_service` holds schema USAGE on `app_private`
-- and nothing else"* -- so `GET /admin/audit` had no statement it was allowed
-- to send. **CLAUDE.md §6 question 5 asked of 0019: which of this decision's
-- callers got it?** The indexes did. The grant did not.
--
-- **A SECURITY DEFINER function rather than a SELECT grant**, and the table's
-- own COMMENT is what forbids the alternative: *"Append-only to every request
-- role: no role holds INSERT, UPDATE, DELETE or SELECT on it, and the only
-- paths in are the definer functions below."* Granting `auth_service` SELECT
-- would make that sentence false and would put a second kind of access to this
-- table beside the definer route. This is 0014's arrangement for the storage
-- plane and ADR 0052's for the identity registry, applied to the one table
-- Session 9 added. See ADR 0142.
--
-- **What is NOT here: a request_id on the `database`-source row** (D500). The
-- header measurement from rig6 says the repair is available -- a forwarded
-- `X-Request-Id` does reach the database in
-- `current_setting('request.headers')::jsonb` -- and it is deliberately not
-- taken in this migration. Closing D500 means replacing both write RPCs, which
-- is a change to what the product WRITES; this migration only adds a way to
-- READ what is already written. Bundling them would make one migration two
-- decisions, and the deployment test that asserts the `database` row's
-- `request_id` IS NULL stays green and stays the thing that will fail on the
-- day the repair lands.
--
-- **What is NOT here: retention.** Nothing prunes `app_private.agent_audit`,
-- exactly as nothing prunes secret generations. Naming it in ADR 0135's
-- consequences did not make it decided, and a reader is not the place to decide
-- it: a `DELETE` path would be a second write authority over a table whose
-- append-only property is stated in its own comment.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The reader
-- ---------------------------------------------------------------------------
--
-- `STABLE` and not `VOLATILE`, because it writes nothing -- and unlike
-- `agent_audit_begin` that is a property worth stating rather than inheriting:
-- ADR 0136's whole category exists because PostgREST refuses a WRITING function
-- over GET, and this function is not in `api`, is not served by PostgREST, and
-- is reached only by `auth_service` over its own pool. It is in the private
-- schema for the reason 0011 gives about the identity registry: the audit
-- record is published to nobody, and an object in `api` is an object the
-- generated document can name.
--
-- **Three arguments, and none of them names a principal.** `p_agent_id` and
-- `p_owner_id` are FILTERS over a record an administrator is already
-- authorized to read in full -- the endpoint above this is gated on
-- `admin_audit:read`, which lives in `project_admin`'s ceiling alone -- so
-- neither argument widens what the caller may see and neither can be used to
-- become somebody. That is a different question from SEC-PARAM-001, which is
-- about the AGENT plane's functions taking no identity argument, and the
-- distinction is worth stating so the next reader does not read this signature
-- as a counterexample to it.
--
-- **`p_limit` is applied and not clamped**, and that is one authority rather
-- than two. The route validates the caller's `limit` into its documented range
-- and answers 422 outside it, so the caller is told rather than silently served
-- a different query than it asked for. A second clamp here would be a second
-- bound over one rule, and the two drift the moment either moves -- which is
-- the shape D495 and D463 are both instances of. The route is the authority;
-- this function is granted to one role whose only caller is that route.
--
-- The ORDER BY is `started_at DESC, id DESC`. The tiebreak is not decoration:
-- `started_at` defaults to `now()`, which is transaction time, so two rows
-- written by one transaction share it exactly and a bare `started_at DESC`
-- would order them arbitrarily -- and an arbitrary order under a LIMIT is a
-- row that appears in no page.
CREATE FUNCTION app_private.auth_list_agent_audit(
  p_agent_id uuid,
  p_owner_id uuid,
  p_limit    integer
)
  RETURNS TABLE (
    id           uuid,
    source       app_private.agent_audit_source,
    agent_id     uuid,
    owner_id     uuid,
    tool         text,
    request_id   uuid,
    parameters   jsonb,
    outcome      app_private.agent_audit_outcome,
    row_count    integer,
    elapsed_ms   integer,
    started_at   timestamptz,
    completed_at timestamptz
  )
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT r.id, r.source, r.agent_id, r.owner_id, r.tool, r.request_id,
           r.parameters, r.outcome, r.row_count, r.elapsed_ms,
           r.started_at, r.completed_at
    FROM app_private.agent_audit r
    WHERE (p_agent_id IS NULL OR r.agent_id = p_agent_id)
      AND (p_owner_id IS NULL OR r.owner_id = p_owner_id)
    ORDER BY r.started_at DESC, r.id DESC
    LIMIT p_limit
  $fn$;

COMMENT ON FUNCTION app_private.auth_list_agent_audit(uuid, uuid, integer) IS
  'The only read path to app_private.agent_audit (ADR 0142). Granted to '
  'auth_service alone, which reaches it from GET /admin/audit behind the '
  'admin_audit:read scope. Both filters are optional and neither widens what '
  'the caller may see: an administrator holding the scope may read the whole '
  'record, so p_agent_id and p_owner_id narrow a permitted read rather than '
  'authorize one. The bound on p_limit is the route''s and is not restated '
  'here.';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- **This block runs as the object owner** (D285, ADR 0091). `REVOKE ALL ON
-- FUNCTION` and `GRANT EXECUTE ON FUNCTION` both require ownership, and the
-- `RESET ROLE` is at the end of the file where 0011, 0013 and 0019 all have it.
--
-- The targeted revoke rather than the blanket form (D57, re-measured as D262
-- and again in Session 8 Run 8): a newly created function is EXECUTABLE BY
-- PUBLIC the moment it exists, and the `ALTER DEFAULT PRIVILEGES` form that
-- reads like the fix records nothing at all for functions. It takes nothing
-- away from a named grantee (D267), so no earlier grant to `auth_service` is
-- restated below -- 0012's eight, 0013's five and 0017's one all survive this
-- line, and restating them would be fourteen statements that do nothing.
REVOKE ALL ON FUNCTION
  app_private.auth_list_agent_audit(uuid, uuid, integer) FROM PUBLIC;

-- **One grantee, and the omissions are the design.** Not `project_admin`: an
-- administrator reaches this through the auth service's endpoint, which is
-- where the scope is checked, and a request role holding EXECUTE could reach
-- the audit record over PostgREST with no scope check at all. Not either agent
-- role: an agent must not read its own record, still less another's -- ADR
-- 0135's stated threat is that an agent can add noise to the record under a
-- true identity, and reading it back is not part of that and must not become
-- part of it. Not `api_documentation`: this function is not in `api` and could
-- not be served, and granting it would be the one thing that could change that.
GRANT EXECUTE ON FUNCTION
  app_private.auth_list_agent_audit(uuid, uuid, integer) TO {{auth_service}};

-- The table itself stays as 0019 left it: no role holds SELECT, INSERT, UPDATE
-- or DELETE on app_private.agent_audit, and the definer functions are the only
-- paths in and now the only path out.
REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;

RESET ROLE;

-- Nothing in `api` moved, so the schema cache is not stale and no NOTIFY is
-- issued. Every migration that has one touches the exposed schema; issuing one
-- here would announce a reload for a change PostgREST cannot see, which is a
-- notification a reader would later have to explain.

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

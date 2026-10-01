-- migrate:up
-- Approval in the database: the guard a gated project function calls first
-- (ADR 0242).
--
-- Since 0035 an approval is a PLANE control: the agent plane refuses a tool
-- whose capability declares `requires_approval` until a person decides, and the
-- released call carries a signed `apg_approval {id, tool, key}` claim that only
-- `auth` adds, only from a decision it read itself (ADR 0231). The database
-- never looked, so an agent holding the tool's scope could call the same RPC
-- through PostgREST with its OWN token and write (rig 33b, D1721). This is the
-- check a reviewed function makes before it does anything at all.
--
-- ---------------------------------------------------------------------------
-- Why `app`, and why nobody
-- ---------------------------------------------------------------------------
--
-- **An `api` function is either forgeable or refused** (D1867). Granted to a
-- request role it is `POST /rpc/require_approval`, an endpoint any caller can
-- reach; granted to nobody it is a function the `api` grant guards refuse as
-- one no role can call -- D1779 measured exactly this for the emitter. A
-- project body may not name `app_private`, so the guard cannot live there
-- either. `app` is the schema 0036 already proved: PostgREST does not expose
-- it, no request role holds USAGE on it, and a function there that is GRANTED
-- TO NOBODY can be called only by a function already running as the object
-- owner -- a project set's reviewed definer RPC (rig 35a: every login and
-- request role refused `42501` with `has_function_privilege` false, and
-- `POST /rpc/rig_require_approval` answered `404 PGRST202`).
--
-- ---------------------------------------------------------------------------
-- Why a human passes
-- ---------------------------------------------------------------------------
--
-- With no `app.agent_id` for the transaction the caller is a PERSON, and the
-- guard returns. Approvals are made BY people; a person's own write through the
-- reviewed surface was never what an approval gates, and the owner's direct
-- call is served (rig 35a: 200, `app.agent_id` empty).
--
-- For an agent, the claim must be an object naming THIS tool, the request's
-- `Idempotency-Key` must be present and equal the claim's key, the claim's id
-- must be a uuid, and an `approved` decision with that id, tool and key must
-- exist on a `running` run of THIS agent -- the signer's own predicate
-- (`workflow_approval_for_token`, 0035) plus the tool and the key. Rig 35a
-- measured the claim arriving in `request.jwt.claims` exactly as `step_token`
-- minted it, and the plane's header arriving in `request.headers` equal to
-- its key. A malformed key is refused `PT412` by `agent_idempotency_key()`
-- before the guard decides, which is that function's own contract (0029).
--
-- **Every refusal is ONE sentence**, `AP403: approval_required` with SQLSTATE
-- `PT403` -- PostgREST answers 403 -- and never says which member failed: a
-- caller probing the guard learns nothing from the answer it gets.
--
-- ---------------------------------------------------------------------------
-- What this migration does NOT do
-- ---------------------------------------------------------------------------
--
-- **Nothing moves in `api`**, so there is no `NOTIFY pgrst`. No table, column
-- or enum moves; no 0035 or 0036 function is replaced.
--
-- **It gates nothing by itself.** A project function opts in by calling it as
-- its first statement; the example set's `0004` does so for
-- `set_note_embedding`, and `approval_gate.unguarded` refuses a gated RPC tool
-- whose function does not (ADR 0242).
--
-- **A profile-added approval on a RELEASE tool stays a plane control**
-- (D1869): the database cannot read a deployment's profile.
--
-- **It does not make the caller idempotent** (D1871). The decision is not
-- consumed: the same approved claim and key called twice is served twice, and
-- consuming it would turn the worker's own crash replay into a terminal step
-- failure and a compensation.
--
-- **A human's `Dry-Run` header still writes** (D1870); an agent's direct
-- call, dry or not, now stops here.
--
-- `STABLE`, because everything it reads is: two GUCs, two tables, and
-- `agent_idempotency_key()`, itself declared `STABLE` (0029).
SET LOCAL ROLE {{object_owner}};

CREATE FUNCTION app.require_approval(p_tool text)
  RETURNS void
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  acting_agent uuid := nullif(pg_catalog.current_setting('app.agent_id', true), '')::uuid;
  claim        jsonb;
  request_key  text;
BEGIN
  IF acting_agent IS NULL THEN
    RETURN;
  END IF;

  claim := nullif(pg_catalog.current_setting('request.jwt.claims', true), '')::jsonb
             -> 'apg_approval';
  request_key := app_private.agent_idempotency_key();

  IF claim IS NULL
     OR pg_catalog.jsonb_typeof(claim) <> 'object'
     OR (claim ->> 'tool') IS DISTINCT FROM p_tool
     OR request_key IS NULL
     OR (claim ->> 'key') IS DISTINCT FROM request_key
     OR coalesce(claim ->> 'id', '')
          !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'AP403: approval_required' USING ERRCODE = 'PT403';
  END IF;

  IF NOT EXISTS (
       SELECT 1
         FROM app_private.workflow_approval a
         JOIN app_private.workflow_run r ON r.id = a.run_id
        WHERE a.id = (claim ->> 'id')::uuid
          AND a.status = 'approved'
          AND a.tool = p_tool
          AND a.idempotency_key = request_key
          AND r.agent_id = acting_agent
          AND r.status = 'running') THEN
    RAISE EXCEPTION 'AP403: approval_required' USING ERRCODE = 'PT403';
  END IF;
END $fn$;

COMMENT ON FUNCTION app.require_approval(text) IS
  'The database half of approval (ADR 0242). Granted to NOBODY: a gated project '
  'function, running as the owner, calls it first. Returns for a caller with no '
  'agent identity; for an agent, only when the apg_approval claim names the tool, '
  'the Idempotency-Key equals the claim''s key, and an approved decision for that '
  'tool and key exists on a running run of that agent. Otherwise PT403 '
  'approval_required, one sentence for every cause.';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- REVOKE from PUBLIC and grant to NOBODY: only an owner-run function may call
-- the guard, exactly as only one may call the emitter (0036).
REVOKE ALL ON FUNCTION app.require_approval(text) FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

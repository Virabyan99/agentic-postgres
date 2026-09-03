-- migrate:up
-- What refused, which capability version was live, and which contract said so
-- (ADR 0178).
--
-- ---------------------------------------------------------------------------
-- Why a reason is a TYPE and not a string
-- ---------------------------------------------------------------------------
--
-- The agent plane's standing rule is that no caller value reaches an operator's
-- console. A free-text denial reason breaks it in the quietest available way:
-- the text would be written by the runtime today and by whatever raised the
-- error tomorrow, and an operator reading `agent_audit` cannot tell one from the
-- other. An enum is refused by the catalog rather than discouraged by a
-- convention, and adding a member is a migration somebody reviews.
--
-- ---------------------------------------------------------------------------
-- The eight members, and the two that are NOT here
-- ---------------------------------------------------------------------------
--
-- Derived from the refusal sites in `mcp_tools`, `mcp_query` and `mcp_upstream`
-- rather than designed beside them (ADR 0178). The session plan proposed
-- `scope, allowlist, budget, drift, credential`; four of those are real.
--
-- **`credential` is not a member.** The MCP runtime holds no credential of any
-- kind -- no signing key, no database credential -- so it cannot describe the
-- runtime's own. And if it meant the CALLER's, `mcp_upstream`'s own measurement
-- refuses it: a 401 upstream is "no Authorization", "an unknown agent" or "a
-- forged signature", and a 403 is a human token -- four states behind two
-- statuses. Naming one `credential` is the guess D433 forbids, and it is worse
-- in a durable record than in a response, because whoever reads it later cannot
-- re-derive what was true.
--
-- `upstream_refused` is the honest form of it: this plane asked and was told no,
-- which is the whole of what it knows.
--
-- **`not_in_allowlist` and `input_malformed` are separate**, although a caller
-- sees one token for both. To an operator they are opposite events: the first is
-- an agent reaching for something this deployment froze, and the second is a
-- client bug. Collapsing them would bury the interesting one inside the noisy
-- one, which is the failure a taxonomy exists to prevent.

SET LOCAL ROLE {{object_owner}};

CREATE TYPE app_private.agent_denial_reason AS ENUM (
  'scope_not_held',
  'not_in_allowlist',
  'input_malformed',
  'budget_exceeded',
  'contract_drift',
  'upstream_refused',
  'audit_unavailable',
  'write_rejected'
);

COMMENT ON TYPE app_private.agent_denial_reason IS
  'The boundary that refused, never the cause it could not distinguish (ADR '
  '0178). Mirrored by mcp_errors.DENIAL_REASONS, which a contract test compares '
  'against this template so neither file becomes a second authority.';

-- ---------------------------------------------------------------------------
-- Three columns
-- ---------------------------------------------------------------------------
--
-- All three nullable, and each for a different reason worth stating.
--
-- `capability_version` is NULL when the deployed lock is schema version 1, where
-- capabilities declare no version at all (ADR 0177). A default of '0.0.0' would
-- make a deployment that does not version its capabilities indistinguishable
-- from one that versions them all at zero -- D600, in a column an operator reads
-- months later.
--
-- `contract_hash` is NULL for the same reason and one more: it is the lock's
-- `canonical_sha256`, so a row carrying one names the exact contract that was
-- live. That is what makes an old record still legible after the contract moves.
--
-- `denial_reason` is NULL for every outcome that is not a refusal, and the CHECK
-- below makes that a property rather than a habit.
ALTER TABLE app_private.agent_audit
  ADD COLUMN capability_version text
    CHECK (capability_version IS NULL
           OR capability_version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'),
  ADD COLUMN contract_hash text
    CHECK (contract_hash IS NULL OR contract_hash ~ '^[0-9a-f]{64}$'),
  ADD COLUMN denial_reason app_private.agent_denial_reason;

-- A refused row carries a reason and nothing else does. Written as an
-- equivalence rather than two one-way checks: a `served` row with a reason is
-- as wrong as a `refused` row without one, and stating it once means neither
-- direction can be relaxed without the other being noticed.
ALTER TABLE app_private.agent_audit
  ADD CONSTRAINT agent_audit_reason_iff_refused
  CHECK ((outcome = 'refused') = (denial_reason IS NOT NULL));

COMMENT ON COLUMN app_private.agent_audit.capability_version IS
  'The semver the capability declared in the deployed lock, or NULL at lock '
  'schema version 1 where capabilities declare none (ADR 0177).';
COMMENT ON COLUMN app_private.agent_audit.contract_hash IS
  'The lock''s canonical_sha256: which compiled contract was live when this '
  'happened, so the record stays legible after the contract moves.';
COMMENT ON COLUMN app_private.agent_audit.denial_reason IS
  'Which boundary refused (ADR 0178). Present exactly when outcome is refused.';

-- ---------------------------------------------------------------------------
-- The two functions, replaced rather than amended
-- ---------------------------------------------------------------------------
--
-- **Neither new parameter carries a DEFAULT**, and that is deliberate after
-- D857. Session 15 Run 4 added a defaulted-looking parameter, the product
-- followed, four proofs did not, and the whole class was invisible until a host
-- gate found it thirteen minutes in. ADR 0175 now checks every call to a
-- released `app_private` function against the arity its migrations declare --
-- so a required parameter is the SAFE choice here, because forgetting it is
-- caught offline. A defaulted one would let a caller omit the capability version
-- forever and leave the column quietly NULL, which is D816's unverified field
-- wearing a different hat.
--
-- The values may still be NULL. The caller must DECIDE that they are.
DROP FUNCTION api.agent_audit_begin(text, uuid, jsonb);

CREATE FUNCTION api.agent_audit_begin(
  p_tool               text,
  p_request_id         uuid,
  p_parameters         jsonb,
  p_capability_version text,
  p_contract_hash      text
)
  RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  acting_agent uuid := nullif(current_setting('app.agent_id', true), '')::uuid;
  acting_owner uuid := nullif(current_setting('app.user_id',  true), '')::uuid;
  new_id       uuid;
BEGIN
  IF acting_agent IS NULL OR acting_owner IS NULL THEN
    RAISE EXCEPTION 'AP403: this operation requires an agent identity'
      USING ERRCODE = 'PT403';
  END IF;

  INSERT INTO app_private.agent_audit
    (source, agent_id, owner_id, tool, request_id, parameters, outcome,
     capability_version, contract_hash)
  VALUES
    ('agent_plane', acting_agent, acting_owner, p_tool, p_request_id,
     p_parameters, 'started', p_capability_version, p_contract_hash)
  RETURNING id INTO new_id;

  RETURN new_id;
END $fn$;

DROP FUNCTION api.agent_audit_complete(uuid, text, integer, integer);

CREATE FUNCTION api.agent_audit_complete(
  p_audit_id      uuid,
  p_outcome       text,
  p_elapsed_ms    integer,
  p_row_count     integer,
  p_denial_reason text
)
  RETURNS boolean
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  acting_agent uuid := nullif(current_setting('app.agent_id', true), '')::uuid;
  closed       integer;
BEGIN
  IF acting_agent IS NULL THEN
    RAISE EXCEPTION 'AP403: this operation requires an agent identity'
      USING ERRCODE = 'PT403';
  END IF;

  IF p_outcome NOT IN ('served', 'refused', 'failed') THEN
    RAISE EXCEPTION 'AP422: an outcome is served, refused or failed'
      USING ERRCODE = 'PT422';
  END IF;

  -- Refused before the UPDATE rather than by the table's CHECK, so the caller
  -- gets this repository's own errcode and message instead of a constraint name
  -- (ADR 0139's rule about translating a refusal rather than relaying one). The
  -- CHECK stays as the second line: it is what holds if this branch is ever
  -- wrong, and it holds against every path in, not only this one.
  IF (p_outcome = 'refused') <> (p_denial_reason IS NOT NULL) THEN
    RAISE EXCEPTION 'AP422: a refused record carries a denial reason and no other record may'
      USING ERRCODE = 'PT422';
  END IF;

  UPDATE app_private.agent_audit
     SET outcome       = p_outcome::app_private.agent_audit_outcome,
         elapsed_ms    = p_elapsed_ms,
         row_count     = p_row_count,
         denial_reason = p_denial_reason::app_private.agent_denial_reason,
         completed_at  = now()
   WHERE id       = p_audit_id
     AND agent_id = acting_agent
     AND source   = 'agent_plane'
     AND outcome  = 'started';

  GET DIAGNOSTICS closed = ROW_COUNT;
  RETURN closed = 1;
END $fn$;

COMMENT ON FUNCTION api.agent_audit_begin(text, uuid, jsonb, text, text) IS
  'Opens one agent_plane audit record and returns its id. Takes no principal: '
  'the agent and its owner come from the GUCs the pre-request hook set. The '
  'capability version and contract hash are REQUIRED arguments and may be NULL '
  'values -- the caller decides, and ADR 0175 checks that it did (ADR 0178).';

COMMENT ON FUNCTION api.agent_audit_complete(uuid, text, integer, integer, text) IS
  'Closes one record, scoped to the calling agent''s own rows. A refused '
  'outcome carries a denial reason from app_private.agent_denial_reason and no '
  'other outcome may (ADR 0178).';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- Re-granted because the functions were replaced: a DROP takes its grants with
-- it, and a function nothing may execute is a plane that fails closed on its
-- first call. The grantees are 0019's, unchanged -- this migration widens
-- nothing.
--
-- **Targeted revokes, not the blanket form**, and 0019 wrote the reason down:
-- schema `api` is not `app_private`. Each new function is EXECUTABLE BY PUBLIC
-- the moment it exists (D57, re-measured as D262), `anon` has held USAGE on
-- schema `api` since 0001, and `openapi-mode = follow-privileges` follows a
-- PUBLIC grant -- so it would advertise them in the document an anonymous caller
-- receives. `REVOKE ... ON ALL FUNCTIONS IN SCHEMA api` would additionally strip
-- PUBLIC from every OTHER function in the schema, which is a change to the
-- published surface made by a migration about an audit table.
REVOKE ALL ON FUNCTION
  api.agent_audit_begin(text, uuid, jsonb, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  api.agent_audit_complete(uuid, text, integer, integer, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION api.agent_audit_begin(text, uuid, jsonb, text, text)
  TO {{agent_reader}}, {{agent_writer}};
GRANT EXECUTE ON FUNCTION api.agent_audit_complete(uuid, text, integer, integer, text)
  TO {{agent_reader}}, {{agent_writer}};

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

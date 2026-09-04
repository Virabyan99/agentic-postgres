-- migrate:up
-- The fifth budget: a bound on an agent that outlives the request (ADR 0180).
--
-- ---------------------------------------------------------------------------
-- Why it is counted here and not in a call of its own
-- ---------------------------------------------------------------------------
--
-- The agent plane holds no database credential (D407), so every database
-- interaction is an upstream PostgREST request made as the caller -- and a write
-- is already FOUR of them, a read three, each holding a connection from a pool
-- shared with human callers. None of it has ever been timed against the
-- deployment. A quota checked in a request of its own would be a fifth, a
-- 25-33% increase in round trips on a path whose latency nobody knows.
--
-- `agent_audit_begin` already runs on every audited call, and ADR 0141 already
-- put it BEFORE the scope check so that a denial is audited. A quota refusal is
-- a denial. So the place that costs nothing is also the only place the refusal
-- can be recorded -- the constraint and the existing decision point at the same
-- function.
--
-- ---------------------------------------------------------------------------
-- What was measured, at `read committed`, which is what the deployment runs
-- ---------------------------------------------------------------------------
--
-- Two overlapping transactions, with a control proving the race was real
-- (ADR 0171's pattern):
--
--   two INSERT ... ON CONFLICT DO UPDATE ... RETURNING   final count 2, both ok
--   the loser                                            BLOCKED until the
--                                                        winner committed:
--                                                        0.94s against a 0.75s
--                                                        hold
--   CONTROL, the same two as a plain INSERT              the loser raised 23505
--
-- So there is no lost update and the verdict is the RETURNED COUNT rather than
-- an error code. `repeatable read` is rejected for ADR 0171's reason: its loser
-- gets 40001, and the ordinary response to a serialization failure is a retry --
-- retrying a quota increment is how a caller exceeds its quota.
--
-- The growth question was measured too (D903), and then designed away (D910).
-- The plan said the table's growth is "a latency problem before it is a disk
-- one"; measured, the upsert is FLAT from 100 to 200,000 rows (0.0093 to 0.0084
-- ms) while the table goes 64 kB to 22 MB, against a control at 659x -- so it
-- was a disk problem. The table now holds one row per agent, so it is neither.

SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The bound lives on the agent, because the requirement bounds an agent
-- ---------------------------------------------------------------------------
--
-- `AGT-QUOTA-001` is *"a windowed quota bounds an AGENT across requests"* --
-- not a capability. A per-capability bound is ADR 0179's shape and is decided by
-- the manifest; this one is decided by whoever issued the agent, and it belongs
-- beside the scopes and the status that are already decided there.
--
-- **Both nullable, and NULL means unbounded.** Not a default: this deployment
-- has agents today with no quota, and giving them a number nobody chose would be
-- inventing a bound and calling it a policy. An operator sets one deliberately,
-- which is the same rule ADR 0177 applies to a capability's lifecycle.
ALTER TABLE app_private.agents
  ADD COLUMN quota_calls integer
    CHECK (quota_calls IS NULL OR quota_calls >= 1),
  ADD COLUMN quota_window_seconds integer
    CHECK (quota_window_seconds IS NULL OR quota_window_seconds BETWEEN 1 AND 86400),
  -- Neither or both. A window with no bound counts nothing, and a bound with no
  -- window is a number with no meaning -- and either alone would read as a
  -- quota that is configured.
  ADD CONSTRAINT agents_quota_is_whole
    CHECK ((quota_calls IS NULL) = (quota_window_seconds IS NULL));

COMMENT ON COLUMN app_private.agents.quota_calls IS
  'Calls this agent may make per window, or NULL for unbounded (ADR 0180). '
  'Counted at api.agent_audit_begin, so a REFUSED call consumes it too.';
COMMENT ON COLUMN app_private.agents.quota_window_seconds IS
  'The window length. Windows are fixed and epoch-aligned, not sliding: a '
  'sliding window needs the timestamps of individual calls, which is a second '
  'copy of what agent_audit already records.';

-- ---------------------------------------------------------------------------
-- ONE ROW PER AGENT, and the window boundary is a reset
-- ---------------------------------------------------------------------------
--
-- **Not one row per window**, which was this migration's first shape and is the
-- reason ADR 0180 spent a section on retention. Nothing ever reads a past
-- window: the quota consults the current one and no other, and `agent_audit`
-- already holds the per-call history if anybody wants to count. A row per window
-- therefore accumulates state that exists only to be pruned -- and then needs a
-- pruning verb, a caller for it, and a horizon somebody chooses.
--
-- Keyed on the agent alone, the table is bounded by the number of agents this
-- deployment has issued. **Retention stops being a question rather than being
-- answered**, and D903's measurement -- that growth costs disk and not latency --
-- stops mattering because there is no growth.
--
-- Measured, with a control that removes the window comparison so the reset
-- cannot pass by accident: two calls in one window count to 2 in one row; a call
-- in the next window resets to 1 and adds no row; two CONCURRENT calls in one
-- window count to 2 with no lost update; and without the comparison a new window
-- does NOT reset, which is what proves arm 2 measured the guard.
CREATE TABLE app_private.agent_quota (
  agent_id     uuid        PRIMARY KEY
                 REFERENCES app_private.agents (id) ON DELETE CASCADE,
  window_start timestamptz NOT NULL,
  calls        integer     NOT NULL CHECK (calls >= 1)
);

COMMENT ON TABLE app_private.agent_quota IS
  'The fifth budget''s durable state (ADR 0180). ONE ROW PER AGENT: the window '
  'boundary resets the count rather than adding a row, so the table is bounded '
  'by the number of agents and there is nothing to prune. ON DELETE CASCADE '
  'because a removed agent''s counter bounds nothing -- unlike its audit rows, '
  'which are attribution and outlive it.';

-- ---------------------------------------------------------------------------
-- `begin`, now counting
-- ---------------------------------------------------------------------------
--
-- **The signature does not change**, and that is worth the sentence: a quota
-- refusal is signalled by RETURNING NULL, not by a new out-parameter and not by
-- raising.
--
-- Raising was the first instinct and it is wrong. The audit row is INSERTed in
-- this transaction, so a RAISE rolls it back -- D489's rule, which is why a
-- `database` row can only ever record a commit. The refusal would be unrecorded,
-- which is the one thing ADR 0141 put `begin` before the scope check to prevent.
--
-- NULL is unambiguous here. This function has never returned it: a caller with
-- no agent identity is refused with PT403 above, so the only paths out are a
-- record id or an error. The runtime parses strictly and already refuses
-- anything that is not a string; `null` is now the one other thing it accepts,
-- and it means exactly one thing.
DROP FUNCTION api.agent_audit_begin(text, uuid, jsonb, text, text);

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
  bound        integer;
  window_size  integer;
  window_at    timestamptz;
  used         integer;
  new_id       uuid;
BEGIN
  IF acting_agent IS NULL OR acting_owner IS NULL THEN
    RAISE EXCEPTION 'AP403: this operation requires an agent identity'
      USING ERRCODE = 'PT403';
  END IF;

  SELECT quota_calls, quota_window_seconds
    INTO bound, window_size
    FROM app_private.agents
   WHERE id = acting_agent;

  IF bound IS NOT NULL THEN
    -- Fixed and epoch-aligned. Two callers in the same second land in the same
    -- window without consulting each other, which is what makes the counter a
    -- single contended row rather than a set of overlapping ones.
    window_at := to_timestamp(
      floor(extract(epoch FROM clock_timestamp()) / window_size) * window_size
    );

    -- The CASE is the window boundary: same window, increment; new window,
    -- start again. `window_start` is written unconditionally, so the row always
    -- names the window its count belongs to and the two can never disagree.
    INSERT INTO app_private.agent_quota (agent_id, window_start, calls)
    VALUES (acting_agent, window_at, 1)
    ON CONFLICT (agent_id)
    DO UPDATE SET
      calls = CASE
                WHEN app_private.agent_quota.window_start = EXCLUDED.window_start
                THEN app_private.agent_quota.calls + 1
                ELSE 1
              END,
      window_start = EXCLUDED.window_start
    RETURNING calls INTO used;

    IF used > bound THEN
      -- **The refusal is recorded by this transaction**, complete, so the
      -- runtime has nothing to close. `completed_at` is set here for the same
      -- reason: a `started` row nobody will ever complete would look like a call
      -- still in flight.
      INSERT INTO app_private.agent_audit
        (source, agent_id, owner_id, tool, request_id, parameters, outcome,
         capability_version, contract_hash, denial_reason, completed_at)
      VALUES
        ('agent_plane', acting_agent, acting_owner, p_tool, p_request_id,
         p_parameters, 'refused', p_capability_version, p_contract_hash,
         'budget_exceeded', now());

      RETURN NULL;
    END IF;
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

COMMENT ON FUNCTION api.agent_audit_begin(text, uuid, jsonb, text, text) IS
  'Opens one agent_plane audit record and returns its id, or counts the call '
  'against the agent''s window and returns NULL when it is over (ADR 0180). A '
  'NULL return means the refusal has ALREADY been recorded, complete, by this '
  'call -- there is nothing for the caller to close.';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- Targeted, for 0019's reason: schema `api` is not `app_private`, `anon` holds
-- USAGE on it since 0001, and `openapi-mode = follow-privileges` follows a
-- PUBLIC grant. The grantees are 0019's, unchanged.
--
-- **No grant of any kind on `app_private.agent_quota`.** No request role reads
-- it, writes it or knows it exists; the only path in is this definer function.
-- That is 0019's rule for `agent_audit`, and a counter an agent could read is a
-- counter an agent could reason about evading.
REVOKE ALL ON FUNCTION
  api.agent_audit_begin(text, uuid, jsonb, text, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION api.agent_audit_begin(text, uuid, jsonb, text, text)
  TO {{agent_reader}}, {{agent_writer}};

REVOKE ALL ON app_private.agent_quota FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

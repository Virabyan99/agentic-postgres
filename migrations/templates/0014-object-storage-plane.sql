-- migrate:up
-- The object-storage plane: one table, its state machine, the cleanup lease, and
-- the six SECURITY DEFINER functions that are the only way `storage_service`
-- reaches any of it.
--
-- Session 7's migration is **0014**, not the runbook's 0012 (D312). Thirteen are
-- released and applied on both projects.
--
-- **This file does not touch the pre-request hook.** The hook is defined in four
-- migrations -- 0008, 0009, 0010 and 0013 -- and only the last one runs, so a
-- 0014 that redefined it from an older body would silently delete 0010's
-- statement-timeout carry, 0009's documentation-role clause and 0013's
-- current-state comparison (D270). Storage needs none of that: it is reached by
-- the storage service over its own connection, not by PostgREST through a
-- request role.
--
-- Two behaviours were measured against the locked `pgvector/pgvector:pg18`
-- digest (server 18.4) before this file was written, each with a control in the
-- same run, and both are recorded in ADR 0104. They decide the shape of the
-- cleanup claim below.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The state machine
-- ---------------------------------------------------------------------------
--
-- An enum rather than text with a CHECK, matching `api.task_status` from 0007
-- and the two status enums 0011 added. The transitions are one-way:
--
--   pending ---> available ---> tombstoned
--      |                            ^
--      +----------------------------+
--
-- There is no path back. An object that failed verification is tombstoned and a
-- new intent is created; reusing a row would mean reusing an object key, and the
-- key's uniqueness is what makes a replayed presigned PUT unable to overwrite a
-- completed object.
CREATE TYPE app_private.storage_object_state
  AS ENUM ('pending', 'available', 'tombstoned');

COMMENT ON TYPE app_private.storage_object_state IS
  'One-way: pending -> available -> tombstoned, and pending -> tombstoned for an '
  'intent that expired or failed verification. Nothing returns to pending -- a '
  'reused row would mean a reused object key, and key uniqueness is what stops a '
  'replayed presigned PUT overwriting a completed object.';

-- ---------------------------------------------------------------------------
-- The objects
-- ---------------------------------------------------------------------------
--
-- **Every CHECK below was written with ADR 0080 in front of it: a CHECK
-- constraint PASSES when its expression evaluates to NULL.** That is three-valued
-- logic, not a quirk, and it is why the column-level checks are paired with NOT
-- NULL wherever the check is meant to be total. Where a column is deliberately
-- nullable -- `verified_bytes`, `completed_at`, the lease pair -- the column
-- check is intentionally partial and the *coherence* constraints below carry the
-- real rule. Each of those is written so its expression can never be NULL:
-- `state` is NOT NULL, and `x IS NOT NULL` and `(a IS NULL) = (b IS NULL)` are
-- total by construction.
--
-- `owner_id` REFERENCES `app_private.users`. This is the one foreign key in the
-- storage plane and it is deliberate, in contrast to 0011's refusal to point at
-- `app.notes.owner_id`: that column holds a *claim value* which ADR 0029 states
-- in its own title is trusted rather than authenticated. An object's owner is a
-- registered subject the auth service created, so the reference is to a real
-- identity and the database can enforce it. ON DELETE RESTRICT rather than
-- CASCADE: deleting a subject who still owns objects would orphan bytes at the
-- provider that nothing would ever collect.
CREATE TABLE app_private.storage_objects (
  id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id                  uuid        NOT NULL
                              REFERENCES app_private.users (id) ON DELETE RESTRICT,
  object_key                text        NOT NULL CHECK (object_key <> ''),
  state                     app_private.storage_object_state
                              NOT NULL DEFAULT 'pending',
  content_type              text        NOT NULL CHECK (content_type <> ''),
  -- What the client SAID it would upload, bounded by the manifest's
  -- max_upload_bytes at the service. Kept apart from what was verified, because
  -- the whole point of completion is that the two can disagree.
  declared_bytes            bigint      NOT NULL CHECK (declared_bytes > 0),
  -- What HeadObject reported. NULL until completion, and the NULL is why the
  -- column check is partial: `NULL > 0` is NULL and a CHECK passes on NULL, so
  -- this line bounds a present value and says nothing about an absent one. The
  -- coherence constraint below is what forbids an available object without it.
  verified_bytes            bigint      CHECK (verified_bytes > 0),
  created_at                timestamptz NOT NULL DEFAULT now(),
  -- The upload intent's deadline. An intent past this is collectable whether or
  -- not anything ever PUT to the URL, which is what makes an abandoned upload
  -- converge rather than accumulate.
  intent_expires_at         timestamptz NOT NULL,
  completed_at              timestamptz,
  tombstoned_at             timestamptz,
  -- The cleanup lease (ADR 0104). A pair, and the constraint below keeps them a
  -- pair: a holder with no expiry is a lease nothing can reclaim, and an expiry
  -- with no holder is a claim nobody made.
  cleanup_lease_holder      text        CHECK (cleanup_lease_holder <> ''),
  cleanup_lease_expires_at  timestamptz,
  cleanup_attempts          integer     NOT NULL DEFAULT 0 CHECK (cleanup_attempts >= 0),
  cleanup_completed_at      timestamptz,

  -- An available object has been verified against the provider. Total: `state`
  -- is NOT NULL and both operands of the OR are IS NOT NULL tests.
  CONSTRAINT storage_objects_available_is_verified CHECK (
    state <> 'available' OR (completed_at IS NOT NULL AND verified_bytes IS NOT NULL)
  ),
  -- A pending object has not been. Without this, `complete` could be made to
  -- write verified_bytes without moving the state, and a later reader would see
  -- a verified size on an object that is not downloadable.
  CONSTRAINT storage_objects_pending_is_unverified CHECK (
    state <> 'pending' OR (completed_at IS NULL AND verified_bytes IS NULL)
  ),
  CONSTRAINT storage_objects_tombstoned_has_a_time CHECK (
    state <> 'tombstoned' OR tombstoned_at IS NOT NULL
  ),
  -- `(a IS NULL) = (b IS NULL)` is never NULL, so this constraint is total for
  -- every combination including two NULLs. Written this way rather than as
  -- `(a IS NULL AND b IS NULL) OR (a IS NOT NULL AND b IS NOT NULL)` because the
  -- shorter form cannot be misread into a partial one.
  CONSTRAINT storage_objects_lease_is_a_pair CHECK (
    (cleanup_lease_holder IS NULL) = (cleanup_lease_expires_at IS NULL)
  ),
  -- Only a tombstoned object is ever collected, so only a tombstoned object may
  -- carry cleanup state. This is what stops a bug in the claim query leasing a
  -- live object and deleting bytes a user can still download.
  CONSTRAINT storage_objects_only_tombstones_are_collected CHECK (
    state = 'tombstoned' OR (cleanup_lease_holder IS NULL AND cleanup_completed_at IS NULL)
  )
);

-- The object key is globally unique within the project, which is what makes a
-- replayed presigned PUT unable to reach a second row. The service composes it
-- from `naming`'s prefix and a uuid4 suffix (ADR 0102), so a collision would
-- mean the generator repeated itself; the index turns that from silent
-- overwriting into a refused insert.
CREATE UNIQUE INDEX storage_objects_object_key_key
  ON app_private.storage_objects (object_key);

-- The owner's own objects, which is every read the download path makes.
CREATE INDEX storage_objects_owner_state_idx
  ON app_private.storage_objects (owner_id, state);

-- The cleanup queue. Partial, because the collectable set is a small fraction of
-- the table and a full index would be mostly rows the claim never looks at.
CREATE INDEX storage_objects_cleanup_queue_idx
  ON app_private.storage_objects (cleanup_lease_expires_at NULLS FIRST, created_at)
  WHERE state = 'tombstoned' AND cleanup_completed_at IS NULL;

-- Expired intents, for the sweep that tombstones them.
CREATE INDEX storage_objects_expiring_intents_idx
  ON app_private.storage_objects (intent_expires_at)
  WHERE state = 'pending';

COMMENT ON TABLE app_private.storage_objects IS
  'One row per object, created at upload-intent time and never returning to an '
  'earlier state. The owner is a registered subject -- this is the one foreign '
  'key in the storage plane, unlike app.notes.owner_id which holds a trusted '
  'claim rather than an authenticated identity (ADR 0029). Every CHECK here was '
  'written against ADR 0080: a CHECK passes when its expression is NULL, so the '
  'coherence constraints are shaped to be total while the column checks are '
  'deliberately partial where the column is nullable.';

COMMENT ON COLUMN app_private.storage_objects.verified_bytes IS
  'What HeadObject reported, NULL until completion. Separate from '
  'declared_bytes because completion exists to detect that the two disagree.';

COMMENT ON COLUMN app_private.storage_objects.cleanup_lease_expires_at IS
  'The lease is the correctness mechanism and the row lock is not (ADR 0104). '
  'The provider DELETE happens outside this transaction, so a claim has to '
  'survive the transaction that made it -- a row lock is released at COMMIT and '
  'at crash, and only a stored timestamp outlives the connection that wrote it.';

COMMENT ON COLUMN app_private.storage_objects.cleanup_attempts IS
  'Incremented on CLAIM, not on success. An object that repeatedly kills its '
  'worker is then visible rather than invisible; counting successes would leave '
  'the pathological case indistinguishable from the untouched one.';

-- ---------------------------------------------------------------------------
-- The contract state row
-- ---------------------------------------------------------------------------
--
-- The same shape as 0011's `auth_contract_state`: a single-row sentinel the
-- service reads to confirm the plane it is talking to is the one it was built
-- for. `singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton)` admits
-- exactly one row -- `true` -- because a second insert collides on the key and
-- `false` is refused by the check.
CREATE TABLE app_private.storage_contract_state (
  singleton         boolean     PRIMARY KEY DEFAULT true CHECK (singleton),
  plane_version     integer     NOT NULL CHECK (plane_version >= 1),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_private.storage_contract_state (plane_version) VALUES (1);

COMMENT ON TABLE app_private.storage_contract_state IS
  'One row, enforced by the primary key and the CHECK together. plane_version is '
  'what a service reads to refuse a database whose storage plane is older than '
  'the code -- the same sentinel shape auth_contract_state uses.';

-- ---------------------------------------------------------------------------
-- The access plane
-- ---------------------------------------------------------------------------
--
-- Six functions, and they are the only way `storage_service` reaches the table.
-- The role is granted USAGE on `app_private` by the bootstrap plane and EXECUTE
-- on exactly these six below; it holds no privilege on the table itself, so a
-- defect in the service cannot read another owner's row even by writing its own
-- SQL.
--
-- Every one of them: owned by the object owner (this file runs as it), `SET
-- search_path = pg_catalog, pg_temp`, fully qualified names throughout, and an
-- explicit revoke from PUBLIC in the privileges block below -- because a newly
-- created function is PUBLIC-executable and `ALTER DEFAULT PRIVILEGES … REVOKE
-- EXECUTE ON FUNCTIONS FROM PUBLIC` records nothing at all for functions
-- (D57, D262, measured twice in this repository three sessions apart).
--
-- **Every owner-scoped function takes the owner as a parameter and filters on
-- it.** None of them derives the owner from a session setting: the storage
-- service connects as itself over its own pool, so there is no request identity
-- to read, and a function that trusted one would be trusting whatever the last
-- caller set.

-- The upload intent. Returns the id; the caller already knows the key because it
-- generated it (ADR 0102 puts the derivation in the service, where the build
-- context can reach it).
CREATE FUNCTION app_private.storage_create_upload_intent(
  p_owner_id uuid,
  p_object_key text,
  p_content_type text,
  p_declared_bytes bigint,
  p_ttl_seconds integer
) RETURNS uuid
  LANGUAGE sql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    INSERT INTO app_private.storage_objects
      (owner_id, object_key, content_type, declared_bytes, intent_expires_at)
    VALUES
      (p_owner_id, p_object_key, p_content_type, p_declared_bytes,
       pg_catalog.now() + pg_catalog.make_interval(secs => p_ttl_seconds))
    RETURNING id
  $fn$;

COMMENT ON FUNCTION app_private.storage_create_upload_intent(uuid, text, text, bigint, integer) IS
  'Creates a pending object. The key is generated by the service and passed in, '
  'never chosen by a client -- the request model has no key or bucket field at '
  'all, which is what STO-KEY-001 asserts. A duplicate key raises rather than '
  'returning the existing row: two intents on one key would let a replayed PUT '
  'reach a completed object.';

-- Completion, and it is a compare-and-set.
--
-- `WHERE state = 'pending'` is the whole idempotence argument. Completing twice
-- updates zero rows the second time, and the function returns the CURRENT state
-- rather than raising -- so the caller can tell "I just completed this" from
-- "this was already complete" from "this is tombstoned" without a second query
-- and without an exception carrying that distinction into an HTTP status.
--
-- The provider HeadObject happens in the service, OUTSIDE any transaction, and
-- its result arrives here as a parameter. Holding a transaction open across a
-- third-party call would tie a connection -- out of a budget ADR 0099 divides to
-- the last unit -- to R2's latency.
CREATE FUNCTION app_private.storage_complete_upload(
  p_id uuid,
  p_owner_id uuid,
  p_verified_bytes bigint
) RETURNS app_private.storage_object_state
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
  DECLARE
    v_state app_private.storage_object_state;
  BEGIN
    UPDATE app_private.storage_objects
       SET state = 'available',
           verified_bytes = p_verified_bytes,
           completed_at = pg_catalog.now()
     WHERE id = p_id
       AND owner_id = p_owner_id
       AND state = 'pending'
    RETURNING state INTO v_state;

    IF FOUND THEN
      RETURN v_state;
    END IF;

    -- Nothing matched. Either it is already in another state, or it is not this
    -- owner's, or it does not exist -- and the three are answered identically,
    -- with NULL, for the reason the download lookup gives.
    SELECT o.state INTO v_state
      FROM app_private.storage_objects o
     WHERE o.id = p_id AND o.owner_id = p_owner_id;

    RETURN v_state;
  END;
  $fn$;

COMMENT ON FUNCTION app_private.storage_complete_upload(uuid, uuid, bigint) IS
  'Compare-and-set on state = pending, which is what makes completion '
  'idempotent: a second call updates zero rows and returns the state the object '
  'is already in. Returns NULL for absent, foreign or unknown alike. The '
  'HeadObject that produced p_verified_bytes ran outside any transaction.';

-- The download lookup, and the ownership filter here IS the linearization point
-- for STO-OWN-001.
--
-- Returns no row for: an object that does not exist, an object owned by somebody
-- else, a pending object, and a tombstoned object. **All four are the same
-- answer**, and that is the requirement rather than a simplification: a caller
-- that could tell "not yours" from "no such id" can enumerate another user's
-- object ids, and a caller that could tell "tombstoned" from "absent" learns
-- that something was once there.
CREATE FUNCTION app_private.storage_lookup_for_download(
  p_id uuid,
  p_owner_id uuid
) RETURNS TABLE (object_key text, content_type text, verified_bytes bigint)
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT o.object_key, o.content_type, o.verified_bytes
      FROM app_private.storage_objects o
     WHERE o.id = p_id
       AND o.owner_id = p_owner_id
       AND o.state = 'available'
  $fn$;

COMMENT ON FUNCTION app_private.storage_lookup_for_download(uuid, uuid) IS
  'Owned and available only. Absent, foreign, pending and tombstoned all return '
  'zero rows and are indistinguishable to the caller -- STO-OWN-001. This filter '
  'is the linearization point: a tombstone that has committed before this runs '
  'means no URL is granted, and the ordering is the database''s rather than the '
  'service''s.';

-- The tombstone. Idempotent for the same reason completion is, and it commits
-- before any later grant can be authorized because the later grant reads the
-- state this sets.
CREATE FUNCTION app_private.storage_tombstone(
  p_id uuid,
  p_owner_id uuid
) RETURNS boolean
  LANGUAGE sql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    WITH tombstoned AS (
      UPDATE app_private.storage_objects
         SET state = 'tombstoned',
             tombstoned_at = pg_catalog.now()
       WHERE id = p_id
         AND owner_id = p_owner_id
         AND state <> 'tombstoned'
      RETURNING id
    )
    SELECT pg_catalog.count(*) > 0 FROM tombstoned
  $fn$;

COMMENT ON FUNCTION app_private.storage_tombstone(uuid, uuid) IS
  'True when this call moved the object, false when it was already tombstoned, '
  'absent or another owner''s -- the three are not distinguished. A pending '
  'object may be tombstoned directly: an abandoned intent has to be collectable '
  'without ever having been completed.';

-- The cleanup claim (ADR 0104), and the two halves of it do different jobs.
--
-- The PREDICATE is the lease: `cleanup_lease_expires_at IS NULL OR < now()`.
-- That is what makes the claim correct, and it is what a crashed worker loses
-- its hold by. **A row lock cannot do this job** -- the provider DELETE happens
-- outside this transaction, and a lock is released at COMMIT and at crash, so
-- only a stored timestamp outlives the connection that wrote it.
--
-- The `FOR UPDATE SKIP LOCKED` is throughput, and nothing else. Measured on this
-- server with a control: without it a second worker claiming a batch blocks on
-- the first worker's rows until `lock_timeout` kills it; with it, it takes the
-- next rows. Removing it leaves the plane CORRECT and serial. Removing the
-- lease predicate leaves it fast and wrong, and no offline test would notice,
-- because no offline test spans two transactions with a network call between.
CREATE FUNCTION app_private.storage_claim_cleanup_batch(
  p_holder text,
  p_limit integer,
  p_lease_seconds integer
) RETURNS TABLE (id uuid, object_key text, attempts integer)
  LANGUAGE sql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    UPDATE app_private.storage_objects o
       SET cleanup_lease_holder = p_holder,
           cleanup_lease_expires_at =
             pg_catalog.now() + pg_catalog.make_interval(secs => p_lease_seconds),
           cleanup_attempts = o.cleanup_attempts + 1
     WHERE o.id IN (
             SELECT c.id
               FROM app_private.storage_objects c
              WHERE c.state = 'tombstoned'
                AND c.cleanup_completed_at IS NULL
                AND (c.cleanup_lease_expires_at IS NULL
                     OR c.cleanup_lease_expires_at < pg_catalog.now())
              ORDER BY c.cleanup_lease_expires_at NULLS FIRST, c.created_at
              LIMIT p_limit
                FOR UPDATE SKIP LOCKED
           )
    RETURNING o.id, o.object_key, o.cleanup_attempts
  $fn$;

COMMENT ON FUNCTION app_private.storage_claim_cleanup_batch(text, integer, integer) IS
  'The lease predicate is the correctness mechanism; SKIP LOCKED is throughput '
  'and nothing else (ADR 0104). Both were measured on the locked image with '
  'controls. cleanup_attempts is incremented here, on claim, so an object that '
  'repeatedly kills its worker is visible. Deletion is AT LEAST ONCE by '
  'construction: a worker may delete and crash before recording it.';

-- Finishing, which is the only place `cleanup_completed_at` is set.
--
-- The holder is checked, so a worker whose lease expired while it was working
-- cannot mark an object done that a second worker has since claimed. It returns
-- false in that case rather than raising: the losing worker did real work and
-- its object is genuinely gone from the provider, so the honest report is "I no
-- longer hold this", not "something failed".
CREATE FUNCTION app_private.storage_finish_cleanup(
  p_id uuid,
  p_holder text
) RETURNS boolean
  LANGUAGE sql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    WITH finished AS (
      UPDATE app_private.storage_objects
         SET cleanup_completed_at = pg_catalog.now(),
             cleanup_lease_holder = NULL,
             cleanup_lease_expires_at = NULL
       WHERE id = p_id
         AND cleanup_lease_holder = p_holder
         AND cleanup_completed_at IS NULL
      RETURNING id
    )
    SELECT pg_catalog.count(*) > 0 FROM finished
  $fn$;

COMMENT ON FUNCTION app_private.storage_finish_cleanup(uuid, text) IS
  'False when this worker no longer holds the lease -- its lease expired and '
  'somebody else claimed the object. Not an error: the work was done, and the '
  'second worker''s delete is a no-op against an absent key. Clears the lease '
  'pair together, which the paired-lease constraint requires.';

-- The intent sweep. Pending objects past their deadline become tombstones, which
-- is what puts them in front of the cleanup claim above.
--
-- Bounded by `p_limit` for the reason every sweep here is: an unbounded UPDATE
-- on a table that has grown is a statement whose duration nobody chose.
CREATE FUNCTION app_private.storage_expire_intents(p_limit integer)
  RETURNS integer
  LANGUAGE sql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    WITH expired AS (
      UPDATE app_private.storage_objects
         SET state = 'tombstoned',
             tombstoned_at = pg_catalog.now()
       WHERE id IN (
               SELECT c.id
                 FROM app_private.storage_objects c
                WHERE c.state = 'pending'
                  AND c.intent_expires_at < pg_catalog.now()
                ORDER BY c.intent_expires_at
                LIMIT p_limit
                  FOR UPDATE SKIP LOCKED
             )
      RETURNING id
    )
    SELECT pg_catalog.count(*)::integer FROM expired
  $fn$;

COMMENT ON FUNCTION app_private.storage_expire_intents(integer) IS
  'An abandoned upload converges rather than accumulating: a pending object past '
  'intent_expires_at becomes a tombstone and is collected like any other. This '
  'is what STO-COMPLETE-001 rests on -- an intent nobody completed never becomes '
  'downloadable, and it does not stay in the table forever either.';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- **This block runs as the object owner, and `RESET ROLE` is BELOW it**
-- (D285, ADR 0091). `REVOKE ALL ON ALL FUNCTIONS` and `GRANT EXECUTE ON
-- FUNCTION` both require ownership of every function they touch. Reset first and
-- they run as the connected role -- on a host that is `migration_user`, which
-- owns nothing -- and the migration fails on its own first revoke with
-- `permission denied for function (42501)`. 0012 and 0013 both had this wrong
-- and nothing caught it, because every offline rig applied migrations as a
-- superuser, which bypasses the ownership check entirely.
--
-- **A newly created function is EXECUTABLE BY PUBLIC** and the
-- `ALTER DEFAULT PRIVILEGES … REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC` that 0011
-- uses for tables and sequences records NOTHING for functions (D57, D262 -- the
-- same fact measured twice, three sessions apart). So the revoke below is the
-- only thing standing between these six functions and every role holding USAGE
-- on `app_private`, and it runs BEFORE the grants rather than after.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC;

-- **USAGE on the schema, and it is not a formality.** Without it every EXECUTE
-- grant below is unreachable: PostgreSQL refuses the call with `permission
-- denied for schema app_private` before it ever looks at the function's ACL, so
-- a role holding all seven EXECUTE grants can call none of them.
--
-- 0011 granted this to `auth_service` in the migration that created the registry,
-- one file before the functions arrived. Storage has one file for both, and the
-- line was missing from the first draft -- caught by a test that CALLED the
-- function rather than by one that read `pg_proc.proacl`, which was correct and
-- would have stayed green. This is D288/D289/D291's class exactly: adding a
-- service means touching every list that enumerates roles, and nothing
-- enumerates the lists.
GRANT USAGE ON SCHEMA app_private TO {{storage_service}};

GRANT EXECUTE ON FUNCTION
  app_private.storage_create_upload_intent(uuid, text, text, bigint, integer)
  TO {{storage_service}};
GRANT EXECUTE ON FUNCTION
  app_private.storage_complete_upload(uuid, uuid, bigint) TO {{storage_service}};
GRANT EXECUTE ON FUNCTION
  app_private.storage_lookup_for_download(uuid, uuid) TO {{storage_service}};
GRANT EXECUTE ON FUNCTION
  app_private.storage_tombstone(uuid, uuid) TO {{storage_service}};
GRANT EXECUTE ON FUNCTION
  app_private.storage_claim_cleanup_batch(text, integer, integer) TO {{storage_service}};
GRANT EXECUTE ON FUNCTION
  app_private.storage_finish_cleanup(uuid, text) TO {{storage_service}};
GRANT EXECUTE ON FUNCTION
  app_private.storage_expire_intents(integer) TO {{storage_service}};

-- NOT granted, and the omissions are the design:
--
--   * no privilege of ANY kind on app_private.storage_objects. The service holds
--     EXECUTE on seven functions and nothing else, so a defect in it cannot read
--     another owner's row even by composing its own SQL. `has_table_privilege`
--     is not how this is proved -- D103 recorded it returning true for a table
--     the role could not actually read -- so the proof attempts the read.
--   * nothing is granted to `auth_service`. One image runs both modes (ADR
--     0101) and the database is where that boundary is real: the auth role
--     cannot call a storage function, and the storage role cannot call an auth
--     one.
--   * nothing is granted to the request roles. Storage is not reached through
--     PostgREST and has no pre-request hook involvement at all (D270).

REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

-- migrate:up
-- The predicate 0014's cleanup claim was missing: an object is collectable only
-- once nothing can still write to its key.
--
-- **Found by writing the first caller.** Run 3 released the cleanup plane and
-- Run 8 wrote the worker that uses it, which is when this became visible --
-- D348's shape for the second time in one session, and the reason the rule was
-- written down: *a plane is complete when a caller can be written against it,
-- not when its tests pass.* Every Run 3 test called the claim with an object it
-- had tombstoned a moment earlier and got it back, which is exactly the
-- behaviour that is wrong.
--
-- **The defect.** `storage_tombstone` moves a PENDING object, deliberately --
-- an abandoned intent has to be collectable without ever having been completed.
-- But a pending object carries a presigned PUT minted for `intent_expires_at`,
-- and **a tombstone does not revoke it**: a presigned URL is a bearer credential
-- and nothing in this system can withdraw one. So:
--
--   T+0    intent created, upload URL valid until T+900
--   T+10   DELETE /objects/{id}   -> tombstoned
--   T+11   cleanup claims it, DELETEs at the provider (204, absent), finishes
--   T+20   the holder PUTs to the URL -> 200, first write, bytes land
--
-- The row now reads `tombstoned` with `cleanup_completed_at` set, so the claim
-- will never return it again -- and section 4 of the session plan forbids an
-- orphan scan, on the ground that a reconciler which lists and deletes untracked
-- objects can delete data a human put there to recover something. So nothing in
-- this system would ever find those bytes. They are billed forever.
--
-- Measured before this file was written, against the locked
-- `pgvector/pgvector:pg18` digest with all fifteen released migrations applied
-- as `migration_user`: `storage_claim_cleanup_batch` returns a pending object
-- tombstoned one statement earlier with `intent_expires_at` an hour away. The
-- two controls in the same run came out the other way -- an expired intent is
-- claimed, and a completed object is claimed -- so the rig could tell a claim
-- that collects from one that does not.
--
-- **Why this is 0016 and not an edit to 0014.** ADR 0091's three conditions,
-- checked rather than assumed, exactly as 0015 checked them. Condition 1 holds:
-- no cluster has 0014, both deployed projects being on 13. **Condition 2 fails**:
-- 0014 applies perfectly well. The ADR says in as many words that a migration
-- which merely did the wrong thing does not qualify, and this is the second time
-- in one session that its own answer has been a new file.
--
-- See ADR 0111.
SET LOCAL ROLE {{object_owner}};

-- The old signature goes. It is NOT left in place as an overload.
--
-- Two functions answering "which objects are collectable" would be two
-- authorities for one rule, and the three-argument one is the version with the
-- defect -- so leaving it reachable would leave the defect reachable by a caller
-- that simply passed fewer arguments. `storage_service` holds EXECUTE on it
-- today; the DROP takes the grant with it, which is what makes the removal
-- total rather than advisory.
DROP FUNCTION app_private.storage_claim_cleanup_batch(text, integer, integer);

-- The claim, with the write window closed.
--
-- **Both halves of ADR 0104 are carried forward unchanged**, and this file was
-- written from 0014's body rather than from memory of it -- D270 is the record
-- of a hook redefined from an older copy that silently deleted two later
-- additions, and a redefinition is exactly where that happens:
--
--   * the LEASE PREDICATE is the correctness mechanism. The provider DELETE
--     happens outside this transaction, so a claim has to survive the
--     transaction that made it, and a row lock is released at COMMIT and at
--     crash.
--   * `FOR UPDATE SKIP LOCKED` is throughput and nothing else.
--
-- **The new clause is the disjunction, and each side is a different argument.**
--
-- `completed_at IS NOT NULL` -- the object reached `available`, so its key
-- already holds bytes. Every upload URL this service mints carries
-- `If-None-Match: *`, measured in Run 5 to return **412 PreconditionFailed** on
-- the second write, with the arm that matters being a caller who OMITS the
-- header and gets **403 SignatureDoesNotMatch** rather than an unconditional
-- write. So the condition is cryptographic rather than cooperative and no
-- replayed PUT can reach a completed key. Collecting immediately is correct, and
-- making an ordinary delete wait out the whole upload TTL would be a cost with
-- nothing bought.
--
-- `intent_expires_at < now() - grace` -- the object never completed, so its key
-- is empty and its presigned PUT would be a FIRST write, which succeeds. The
-- only thing that stops it is the URL's own expiry, and that is
-- `intent_expires_at` by construction: the service presigns with the same TTL it
-- writes into the row.
--
-- **`p_write_grace_seconds` is a parameter and not a constant here on purpose.**
-- Its correct value is a fact about the PROVIDER's tolerance for a
-- slightly-stale signature -- PostgREST was measured to allow 30 seconds of
-- leeway on `exp` where its documentation implies none (D241), and a signature
-- validator that did the same would make a bare `< now()` wrong. That
-- measurement belongs beside the adapter that made it, in the service, where it
-- can carry the run that produced it. A number baked in here would be a second
-- authority a migration away from its evidence, and changing it would need
-- another migration.
--
-- A negative grace is REFUSED rather than clamped. Clamping with `greatest(x, 0)`
-- would turn a caller's bug into silence, and the bug it would hide is precisely
-- the reintroduction of this defect: a negative grace collects objects whose
-- upload window is still open.
CREATE FUNCTION app_private.storage_claim_cleanup_batch(
  p_holder text,
  p_limit integer,
  p_lease_seconds integer,
  p_write_grace_seconds integer
) RETURNS TABLE (id uuid, object_key text, attempts integer)
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
  BEGIN
    IF p_write_grace_seconds IS NULL OR p_write_grace_seconds < 0 THEN
      RAISE EXCEPTION 'AP422: the write grace must be zero or more seconds'
        USING HINT = 'A negative grace collects objects whose upload URL is still live.';
    END IF;

    RETURN QUERY
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
                -- The write window, and the only line 0014 did not have.
                AND (c.completed_at IS NOT NULL
                     OR c.intent_expires_at
                        < pg_catalog.now()
                          - pg_catalog.make_interval(secs => p_write_grace_seconds))
              ORDER BY c.cleanup_lease_expires_at NULLS FIRST, c.created_at
              LIMIT p_limit
                FOR UPDATE SKIP LOCKED
           )
    RETURNING o.id, o.object_key, o.cleanup_attempts;
  END;
  $fn$;

COMMENT ON FUNCTION app_private.storage_claim_cleanup_batch(text, integer, integer, integer) IS
  'An object is collectable only once nothing can still write to its key '
  '(ADR 0111). Completed: the key holds bytes and a replayed PUT is refused 412 '
  'by the signed If-None-Match, so it is collectable at once. Never completed: '
  'the key is empty and a presigned PUT would be a FIRST write, so it is '
  'collectable only past intent_expires_at plus the caller''s grace. 0014 had '
  'neither clause and would delete an object whose upload URL was still live, '
  'orphaning a late write under a key no row would ever return -- and there is '
  'no orphan scan by design. Both halves of ADR 0104 are unchanged: the lease '
  'predicate is correctness, SKIP LOCKED is throughput. A negative grace is '
  'refused rather than clamped, because clamping would hide exactly the bug it '
  'was asked about.';

-- Privileges. **This block runs as the object owner and `RESET ROLE` is BELOW
-- it** (D285, ADR 0091): `REVOKE` and `GRANT EXECUTE` both require ownership of
-- the function, and on a host the connected role is `migration_user`, which owns
-- nothing. 0012 and 0013 shipped with these two lines the other way round and no
-- offline rig could see it, because every one of them applied migrations as a
-- superuser.
--
-- The revoke is explicit and beside the CREATE. A newly created function is
-- PUBLIC-executable and `ALTER DEFAULT PRIVILEGES … REVOKE … FROM PUBLIC`
-- records nothing at all for functions -- D57, measured in Session 3 and
-- re-measured three sessions later as D262 by somebody who did not know the
-- first measurement existed.
--
-- Schema USAGE is 0014's and is not re-granted here (D337): a second GRANT USAGE
-- would leave it unclear which migration owns that privilege.
REVOKE ALL ON FUNCTION
  app_private.storage_claim_cleanup_batch(text, integer, integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  app_private.storage_claim_cleanup_batch(text, integer, integer, integer)
  TO {{storage_service}};

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

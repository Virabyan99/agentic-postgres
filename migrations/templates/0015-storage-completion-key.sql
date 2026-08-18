-- migrate:up
-- The one function 0014 needed and did not have.
--
-- **Why this is 0015 and not an edit to 0014.** ADR 0091 permits correcting a
-- released migration in place, and its three conditions were checked here
-- rather than assumed. Condition 1 holds: no cluster has 0014, both deployed
-- projects being on 13. **Condition 2 fails**: 0014 applies perfectly well. It
-- is not broken, it is incomplete -- and ADR 0091 says exactly this case in as
-- many words, that "a migration that merely did the wrong thing does not
-- qualify". So the rule's own answer is a new migration, and the fact that
-- editing 0014 would have been harmless today is not the test.
--
-- **What was missing.** Completion must ask the provider how many bytes
-- actually arrived before it moves an object to `available`, and to ask it needs
-- the object's key. 0014 exposes the key in exactly two places:
--
--   storage_lookup_for_download  filtered on state = 'available'
--   storage_claim_cleanup_batch  filtered on state = 'tombstoned'
--
-- Neither can see a PENDING row, so there was no way to reach the key of the
-- object being completed. The alternative -- returning the key from
-- `storage_create_upload_intent` and having the client hand it back -- is
-- refused by STO-KEY-001: the request model has no key field precisely so that
-- a client-supplied key can never reach a presign, and adding one to make
-- completion work would give the whole property away to save a function.
--
-- Found in Run 6 by writing the completion path and having nowhere to get the
-- key from. Nothing offline could have caught it earlier: every Run 3 test
-- calls the functions that exist.
SET LOCAL ROLE {{object_owner}};

-- The state predicate is `pending OR available`, and NOT `pending` alone. That
-- was the first version of this function and it broke idempotency, which is
-- STO-COMPLETE-001 -- caught by the endpoint test, not by reading:
--
--   * first completion  pending   -> key -> HeadObject -> CAS -> available, 200
--   * retry             available -> NULL under a pending-only filter -> 404
--
-- 0014's own comment says the CAS "is what makes completion idempotent", and
-- that is true of the FUNCTION and was false of the ENDPOINT, because the
-- endpoint could not reach the CAS a second time. A claim about a component is
-- not a claim about the path through it.
--
-- `tombstoned` stays excluded, deliberately: completing a tombstoned object
-- would resurrect it, and the one-way state machine is the whole design.
CREATE FUNCTION app_private.storage_completion_key(
  p_id uuid,
  p_owner_id uuid
) RETURNS text
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $fn$
    SELECT o.object_key
      FROM app_private.storage_objects o
     WHERE o.id = p_id
       AND o.owner_id = p_owner_id
       AND o.state IN ('pending', 'available')
  $fn$;

COMMENT ON FUNCTION app_private.storage_completion_key(uuid, uuid) IS
  'The key of an object this owner may still complete -- pending, or already '
  'available so that a retried completion is idempotent (STO-COMPLETE-001). '
  'Tombstoned is excluded: completing one would resurrect it. For the '
  'HeadObject completion performs outside any transaction (ADR 0104). Owner and '
  'state are one predicate, so absent, foreign and tombstoned all return zero '
  'rows and are indistinguishable -- the obscuring '
  'storage_lookup_for_download provides, for STO-OWN-001''s reason: an object '
  'id travels in a URL, and a function answering differently for a stranger''s '
  'id would make it an existence oracle. '
  'STABLE rather than VOLATILE: it reads and decides nothing.';

-- EXECUTE and nothing else, to the one role, exactly as 0014's seven are.
--
-- D337 is why the grant alone is not the whole story and why the test calls the
-- function rather than reading an ACL: `storage_service` held EXECUTE on seven
-- functions and NO USAGE on the schema, so every one of those grants reached
-- nothing and an ACL test stayed green. 0014 fixed the USAGE; this file relies
-- on it and does not re-grant it, because a second GRANT USAGE would make it
-- unclear which migration owns that privilege.
-- The revoke comes first and is explicit. A newly created function is
-- PUBLIC-executable, and `ALTER DEFAULT PRIVILEGES … REVOKE … FROM PUBLIC`
-- records nothing at all for functions -- D57, measured in Session 3, and
-- re-measured three sessions later as D262 by somebody who did not know the
-- first measurement existed. The house pattern puts the revoke beside the
-- CREATE because of it.
--
-- Order is not what makes this correct: a named grant SURVIVES a later
-- `REVOKE … FROM PUBLIC` and falls only to an explicit revoke from the role
-- (D267). Revoking first is simply the order that reads as intended.
REVOKE ALL ON FUNCTION app_private.storage_completion_key(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  app_private.storage_completion_key(uuid, uuid) TO {{storage_service}};

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

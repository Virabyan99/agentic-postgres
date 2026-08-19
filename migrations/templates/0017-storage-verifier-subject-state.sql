-- migrate:up
-- The privilege the third verifier needs, and was never given (D385).
--
-- **Found by the first host run of the storage surface.** Every authenticated
-- storage request answered `500 Internal Server Error` -- plain text, from
-- Starlette's default handler, because the exception escaped before this
-- service's error middleware could shape it:
--
--   psycopg.errors.InsufficientPrivilege:
--     permission denied for function auth_user_state
--
-- Thirteen deployment proofs failed on it and every one had the same cause.
--
-- **Why storage calls it at all.** ADR 0098 makes storage the THIRD verifier: it
-- verifies the tokens `auth` issues, which means it runs the same
-- `AuthService.authenticate`, including the current-state comparison that makes
-- a stale token useless. That comparison is `app_private.auth_user_state`, and
-- it is not optional -- it is the whole of ADR 0095's model, where a token is
-- checked against the record rather than trusted for its lifetime.
--
-- Traced rather than assumed: `authenticate` calls exactly ONE repository
-- method, `state(user_id)`, which is this function. There is no second missing
-- grant waiting behind it. `require_scope` is pure Python and the `Principal` is
-- built from what this returns.
--
-- **Why it was missing.** 0012 created the auth access plane for its only caller
-- at the time and granted the whole set to the auth service role -- correctly.
-- In Session 7 a second service became a caller of `authenticate`, and the grant
-- did not move with it. D333's question for the fifth time in one session:
-- *when a decision is implemented, which of its callers got the implementation?*
-- D381 was the same shape three runs earlier -- storage declared a verifier in
-- four places and handed no key set.
--
-- **Why no offline test could see it.** Nothing offline authenticates as
-- `storage_service` against a real cluster.
-- `test_the_auth_role_can_execute_the_functions_the_service_calls` exists, does
-- exactly the right thing, and checks the auth role; there was no storage twin.
-- Run 12 adds one, and it is the test that would have caught this.
--
-- **This grants ONE function, not the set.** `auth_service` holds eleven
-- functions here, including `auth_create_user`, `auth_set_password` and
-- `auth_set_status` -- the administrator surface. Storage verifies tokens and
-- has no business creating a subject or changing anyone's password, so it is
-- given the single read its verification path performs. Granting the set would
-- be the convenient fix and would hand a storage compromise the ability to mint
-- and re-authorize identities.
--
-- No `REVOKE ... FROM PUBLIC` here: 0012 revoked it for this function and owns
-- that privilege. A second revoke would leave it unclear which migration does
-- (D337). Schema USAGE is 0014's, likewise not re-granted.
--
-- **This block runs as the object owner, and the role is reset below it** (D285,
-- ADR 0091): `GRANT EXECUTE` requires ownership of the function, and on a host
-- the connected role is `migration_user`, which owns nothing. 0012 and 0013
-- shipped with these two lines the other way round and no offline rig could see
-- it, because every one of them applied migrations as a superuser.
--
-- (The phrasing above avoids the literal reset spelling on purpose:
-- `test_every_up_block_assumes_and_returns_the_owner_role` compares the FIRST
-- occurrence of each, and this file explains itself before it acts, so a
-- mention in the header would sort ahead of the statement it describes. 0016
-- writes it out only because its commentary sits below the code.)
--
-- This is 0017 and not an edit to 0012, because ADR 0091's conditions are
-- checked rather than assumed: two clusters hold 0012, so it is released and
-- fix-forward regardless of anything else.
SET LOCAL ROLE {{object_owner}};

GRANT EXECUTE ON FUNCTION app_private.auth_user_state(uuid) TO {{storage_service}};

COMMENT ON FUNCTION app_private.auth_user_state(uuid) IS
  'The subject''s current authorization state, compared against a presented '
  'token on every request (ADR 0095). Executable by the auth service and, since '
  '0017, by the storage service -- the two runtimes that verify tokens '
  '(ADR 0098, ADR 0113). It is a read: neither caller may change a subject '
  'through it, and the administrator functions in this schema stay granted to '
  'the auth service alone.';

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

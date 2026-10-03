-- migrate:up
-- An approval nobody will decide gets a word of its own (ADR 0248, D1775, D1987).
--
-- **One statement, and a file of its own, because rig 36a measured that it has
-- to be.** On the pinned 18.4, `ALTER TYPE ... ADD VALUE` is accepted inside a
-- transaction but the new value cannot be USED in the transaction that added it:
-- `ERROR: unsafe use of new value "c" of enum type t` (SQLSTATE 55P04, *"New
-- enum values must be committed before they can be used"*), and the type rolls
-- back with it. dbmate runs each file in one transaction, so a single file that
-- added the value and then wrote a function or a row using it would fail -- and
-- measured, dbmate 2.34.1 prints `Applied: ... in 2.4ms` BEFORE it reports the
-- error, exits 2 and records no ledger row (D941's class: read the ledger, never
-- the migrator's line). Two files, two transactions: this one adds the value,
-- 0039 uses it. Both measured green, and so is `apg dev up`'s `psql -1` per file.
--
-- **Why `withdrawn` and not the stage plan's `cancelled`**: `cancelled` already
-- names a RUN status, and a run cancelled is not an approval cancelled -- the
-- run may have succeeded, failed or stopped. `withdrawn` says what happened to
-- the request: the run that asked for it no longer waits for an answer.
--
-- **Nothing here writes a row.** 0039's `workflow_withdraw_ended_approvals()`
-- moves the pending approvals of ended runs, called by the worker on an idle
-- iteration. The CHECK on `workflow_approval` (`decided_by` and `decided_at` set
-- exactly for `approved` and `rejected`) holds for `withdrawn` unchanged: a
-- withdrawal is not a decision and names no person. No 0035 function is
-- replaced (D1987), and every reader of the status passes an unknown value
-- through as text or filters on `pending`/`approved`, read in Run 1.
SET LOCAL ROLE {{object_owner}};

ALTER TYPE app_private.workflow_approval_status ADD VALUE 'withdrawn';

RESET ROLE;

-- Nothing in `api` moved, so no NOTIFY: `app_private` is not the exposed schema.

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

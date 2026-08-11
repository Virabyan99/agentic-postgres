-- migrate:up
-- ADR 0048. Four source-controlled documents described this surface and six
-- applied migrations implemented a different one, for two sessions, and nothing
-- recorded it. This migration makes the catalog agree with the documents.
--
-- What moves: `notes.body` becomes `content`; `tasks` gains `description` and a
-- bounded `status` derived from `done`, which is dropped; `api.create_task` is
-- retired in favour of `api.update_task_status`, which is ADR 0003's operation
-- 4 and the one the shipped migrations never had. `note_id` stays -- ADR 0048's
-- one approved extension.
--
-- Released migrations are immutable, so none of this is an edit to 0003, 0004
-- or 0005. It is additive plus two drops, applied through the ordinary wrapper.
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- The bounded status, as an enum, in `api`
-- ---------------------------------------------------------------------------
-- Two decisions here, both measured against the locked PostgREST rather than
-- reasoned about (ADR 0058).
--
-- **An enum rather than a CHECK constraint on text.** ADR 0003 froze four
-- values and said a bounded status is what makes "change one task's status" a
-- safe capability. Both spellings bound the column; only one of them reaches
-- the document this session exists to publish. Measured on v14.16 against a
-- table carrying both: the enum column appears as
-- `{"type":"string","format":"api.task_status","enum":["pending", ...]}` and
-- the CHECK-constrained text column appears as `{"type":"string",
-- "format":"text"}` -- the constraint is nowhere in the OpenAPI document. A
-- bound a caller cannot see is a bound the generated contract cannot carry.
--
-- **In `api` rather than in `app`.** The `format` string is the type's
-- schema-qualified name, so a type in `app` publishes the string
-- `app.task_status` in a document served to the internet -- a schema this
-- contract's `forbidden_schemas` exists to keep unaddressable, named in the
-- artifact. It also sidesteps a question nobody has measured: whether reading
-- an enum column through a security-invoker view needs USAGE on the type's
-- schema. In `api` the request roles already hold it, so the answer cannot
-- matter.
CREATE TYPE api.task_status AS ENUM ('pending', 'in_progress', 'completed', 'cancelled');

COMMENT ON TYPE api.task_status IS
  'The four task states frozen by ADR 0003. Published in OpenAPI as an enum, '
  'which is why this is a type and not a CHECK constraint.';

-- ---------------------------------------------------------------------------
-- The write surface comes down first
-- ---------------------------------------------------------------------------
-- `api.create_note` returns `api.notes`, so it depends on that view's composite
-- type and the view cannot be dropped under it. Order is forced: functions,
-- then views, then columns, then back up.
--
-- And the function is DROPped rather than REPLACEd. `CREATE OR REPLACE
-- FUNCTION` cannot rename a parameter, and the parameter names are the wire
-- format -- PostgREST maps JSON body keys straight onto them (D149). A
-- `create_note` publishing `content` on the read surface while requiring
-- `p_body` on the write surface is two names for one field.
REVOKE ALL ON FUNCTION api.create_note(text, text) FROM {{authenticated}}, {{agent_writer}};
REVOKE ALL ON FUNCTION api.create_task(text, uuid) FROM {{authenticated}}, {{agent_writer}};
DROP FUNCTION api.create_note(text, text);
DROP FUNCTION api.create_task(text, uuid);

DROP VIEW api.notes;
DROP VIEW api.tasks;

-- ---------------------------------------------------------------------------
-- The columns
-- ---------------------------------------------------------------------------
ALTER TABLE app.notes RENAME COLUMN body TO content;

ALTER TABLE app.tasks ADD COLUMN description text NOT NULL DEFAULT '';
ALTER TABLE app.tasks ADD COLUMN status api.task_status;

-- FORCE ROW LEVEL SECURITY IS OFF FOR EXACTLY ONE STATEMENT, AND THAT IS THE
-- DANGEROUS PART OF THIS MIGRATION.
--
-- `app.tasks` carries FORCE (0003), so the row policies apply to the table's
-- owner as well -- which is the whole reason a SECURITY DEFINER write RPC is
-- safe. The policies key on `app.current_user_id()`, and inside a migration
-- there is no request identity, so the claim is NULL and every policy denies.
--
-- An `UPDATE ... SET status = ...` here would therefore match **zero rows and
-- report success**: no error, no warning, and a `done` column that looks
-- migrated on an empty table. That is this repository's signature defect with a
-- data migration wrapped around it, so the derivation runs with FORCE off and
-- the state is restored and then *read back* below rather than assumed.
--
-- dbmate wraps a migration in a transaction, so a failure between these two
-- statements rolls the first one back rather than leaving the table exposed.
ALTER TABLE app.tasks NO FORCE ROW LEVEL SECURITY;

UPDATE app.tasks
   SET status = CASE WHEN done THEN 'completed'::api.task_status
                     ELSE 'pending'::api.task_status END;

ALTER TABLE app.tasks FORCE ROW LEVEL SECURITY;

-- Total, or this migration fails. ADR 0048 requires the derivation to map every
-- existing row, and the honest way to say that is to look. `SET NOT NULL` would
-- catch a NULL too, and it would report it as a constraint violation on a
-- column rather than as a derivation that did not cover the data.
DO $$
DECLARE undecided bigint;
BEGIN
  SELECT count(*) INTO undecided FROM app.tasks WHERE status IS NULL;
  IF undecided > 0 THEN
    RAISE EXCEPTION 'AP900: % task rows have no derived status', undecided
      USING HINT = 'The done -> status derivation must be total. Do not default them.';
  END IF;
END $$;

-- Read back, because the restoration above is a claim like any other. A
-- migration that left FORCE off would leave every SECURITY DEFINER write in
-- this schema able to write any row, and nothing else would notice.
DO $$ BEGIN
  IF NOT (SELECT relforcerowsecurity FROM pg_catalog.pg_class
           WHERE oid = 'app.tasks'::regclass) THEN
    RAISE EXCEPTION 'AP900: app.tasks left the derivation without FORCE row level security';
  END IF;
END $$;

ALTER TABLE app.tasks ALTER COLUMN status SET NOT NULL;
ALTER TABLE app.tasks ALTER COLUMN status SET DEFAULT 'pending';
ALTER TABLE app.tasks DROP COLUMN done;

-- ---------------------------------------------------------------------------
-- The read surface, rebuilt over the new columns
-- ---------------------------------------------------------------------------
-- Recreated rather than replaced, and the reason is a trap worth naming. A view
-- stores its references by attribute number, so `ALTER TABLE ... RENAME COLUMN
-- body TO content` leaves `api.notes` working -- and still publishing an output
-- column called `body`, over a base column now called `content`. A read surface
-- that looks migrated and is not.
CREATE VIEW api.notes
  WITH (security_invoker = true, security_barrier = true) AS
  SELECT id, owner_id, title, content, created_at, updated_at
    FROM app.notes;

CREATE VIEW api.tasks
  WITH (security_invoker = true, security_barrier = true) AS
  SELECT id, owner_id, note_id, title, description, status, created_at, updated_at
    FROM app.tasks;

COMMENT ON VIEW api.notes IS
  'Read surface for notes. security_invoker means the caller''s row policy '
  'applies; without it the view would run as its owner and return every row.';
COMMENT ON VIEW api.tasks IS
  'Read surface for tasks. `status` is api.task_status, whose four values are '
  'frozen by ADR 0003 and published in the generated OpenAPI document.';

GRANT SELECT ON api.notes, api.tasks TO {{authenticated}}, {{agent_reader}}, {{agent_writer}};

-- ---------------------------------------------------------------------------
-- The write surface, rebuilt
-- ---------------------------------------------------------------------------
-- Every reason 0005 gave still applies and is not repeated: no owner_id
-- parameter, SECURITY DEFINER because an INVOKER body cannot reach `app`,
-- safe only because the base tables carry FORCE, search_path pinned to catalog
-- and pg_temp with every object qualified.
--
-- What is new is the error contract (ADR 0057). Session 3 raised `AP401` as a
-- plain message and the SQLSTATE stayed `P0001`, which the locked PostgREST
-- answers with **HTTP 400** -- and it publishes `HINT` and `DETAIL` to the
-- caller verbatim, so 0005's "SET LOCAL app.user_id before calling this
-- function" was on its way to becoming a public sentence about a GUC no HTTP
-- caller can set. Measured, both halves.
--
-- So: the SQLSTATE carries the status, and nothing caller-reachable carries a
-- HINT or a DETAIL.
CREATE FUNCTION api.create_note(p_title text, p_content text DEFAULT '')
  RETURNS api.notes
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller uuid := app.current_user_id();
  created api.notes;
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: no request identity for this transaction'
      USING ERRCODE = 'PT401';
  END IF;

  INSERT INTO app.notes (owner_id, title, content)
  VALUES (caller, p_title, p_content)
  RETURNING id, owner_id, title, content, created_at, updated_at INTO created;

  RETURN created;
END $fn$;

-- ADR 0003's operation 4, deliberately not "update a task".
--
-- `p_expected_status` is what makes it optimistic rather than last-writer-wins:
-- two agents racing on one task produce one success and one AP409, instead of
-- one silently overwriting the other's transition.
--
-- The lookup keys on `id AND owner_id`, so "not yours" and "does not exist" are
-- the same answer. Distinguishing them is itself a read of another owner's
-- data: a caller that can tell a foreign task id from a fictional one can
-- enumerate the table one 404 at a time.
CREATE FUNCTION api.update_task_status(
  p_task_id uuid,
  p_expected_status api.task_status,
  p_new_status api.task_status
)
  RETURNS api.tasks
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller uuid := app.current_user_id();
  observed api.task_status;
  updated api.tasks;
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: no request identity for this transaction'
      USING ERRCODE = 'PT401';
  END IF;

  IF p_new_status = p_expected_status THEN
    RAISE EXCEPTION 'AP422: a status transition must change the status'
      USING ERRCODE = 'PT422';
  END IF;

  -- FOR UPDATE, so a concurrent caller blocks here rather than reading the same
  -- expected status and both proceeding. Without the lock the comparison below
  -- is advisory and the last writer still wins, which is the thing
  -- `p_expected_status` exists to prevent.
  SELECT t.status INTO observed
    FROM app.tasks t
   WHERE t.id = p_task_id AND t.owner_id = caller
     FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no such task' USING ERRCODE = 'PT404';
  END IF;

  IF observed <> p_expected_status THEN
    RAISE EXCEPTION 'AP409: the task is not in the expected status'
      USING ERRCODE = 'PT409';
  END IF;

  UPDATE app.tasks
     SET status = p_new_status, updated_at = now()
   WHERE id = p_task_id AND owner_id = caller
  RETURNING id, owner_id, note_id, title, description, status, created_at, updated_at
       INTO updated;

  RETURN updated;
END $fn$;

COMMENT ON FUNCTION api.create_note(text, text) IS
  'Creates one note owned by the request identity. There is no owner parameter.';
COMMENT ON FUNCTION api.update_task_status(uuid, api.task_status, api.task_status) IS
  'ADR 0003 operation 4: one task, one transition, refused if the task is not '
  'already in the expected status.';

-- Explicit, per function, immediately after creation. This -- not the
-- ALTER DEFAULT PRIVILEGES in 0001 -- is what carries SEC-DEFAULT-001 on the
-- locked image (D57), and Run 5 measured a second consequence: PostgREST's
-- `openapi-mode = follow-privileges` follows a PUBLIC grant too, so a function
-- left with its default EXECUTE is advertised in the document an anonymous
-- caller receives.
REVOKE ALL ON FUNCTION api.create_note(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.update_task_status(uuid, api.task_status, api.task_status) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION api.create_note(text, text)
  TO {{authenticated}}, {{agent_writer}};
GRANT EXECUTE ON FUNCTION api.update_task_status(uuid, api.task_status, api.task_status)
  TO {{authenticated}}, {{agent_writer}};

RESET ROLE;

-- The schema cache is a copy, and a migration that changes the API without
-- saying so leaves PostgREST serving the previous surface until something
-- restarts it. Every migration that changes the API ends here.
NOTIFY pgrst, 'reload schema';

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

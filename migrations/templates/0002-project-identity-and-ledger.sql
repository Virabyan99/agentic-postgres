-- migrate:up
-- The identity sentinel (ADR 0030) and the migration ledger.
SET LOCAL ROLE {{object_owner}};

-- Exactly one row, forever. The single-row constraint is a primary key on a
-- constant rather than a trigger: a trigger can be disabled by anyone who can
-- ALTER the table, and a second identity row is precisely the state that would
-- let a volume claim to belong to two projects.
CREATE TABLE IF NOT EXISTS app_private.project_identity (
  singleton            boolean      PRIMARY KEY DEFAULT true CHECK (singleton),
  project_key          text         NOT NULL CHECK (project_key <> ''),
  database_name        text         NOT NULL CHECK (database_name <> ''),
  compose_project_name text         NOT NULL CHECK (compose_project_name <> ''),
  instance_uuid        uuid         NOT NULL,
  bound_at             timestamptz  NOT NULL DEFAULT now()
);

COMMENT ON TABLE app_private.project_identity IS
  'Binds this volume to one project instance. Compared on the immutable fields '
  'only -- project key, database name, Compose project name, instance UUID. '
  'Never the source commit, manifest checksum or template version: those change '
  'on every legitimate redeploy, and a check that fires on a valid volume is one '
  'operators learn to override. A mismatch stops with exit 11 and is never adopted.';

-- The platform's own ledger, separate from dbmate's schema_migrations table.
-- dbmate records that a version ran; this records *what bytes* ran, which is
-- the claim ADR 0028 makes immutable. One without the other cannot detect an
-- edited template that was re-applied under its original version.
CREATE TABLE IF NOT EXISTS app_private.migration_ledger (
  version              text         PRIMARY KEY,
  name                 text         NOT NULL,
  template_sha256      char(64)     NOT NULL,
  rendered_sha256      char(64)     NOT NULL,
  applied_at           timestamptz  NOT NULL DEFAULT now(),
  applied_by           text         NOT NULL DEFAULT current_user
);

COMMENT ON COLUMN app_private.migration_ledger.rendered_sha256 IS
  'Digest of the payload this database actually executed, which is per project '
  'and therefore cannot live in the committed lock. The preflight compares it '
  'against the source manifest and the rendered set.';

-- No role but the owner and the migration plane sees any of this. `app_private`
-- has no USAGE grant to an API role at all, so this is defence in depth rather
-- than the boundary itself.
REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

-- migrate:up
-- Governed connectivity: the event emitter, the outbox, connectors, receipts
-- and the event wait (ADR 0235, ADR 0236, ADR 0237, ADR 0238, ADR 0239).
--
-- 0034 built durable pending state and 0035 the gates. What arrives here is
-- the first thing that happens BECAUSE of something rather than because an
-- agent asked: a reviewed function records a versioned event inside its
-- caller's transaction (`app.emit_event`), a parked `wait` of the same owner
-- is served by it, and an enabled outbound connector receives one delivery the
-- worker sends later. An inbound connector's signed request and a scheduled
-- connector's interval each start a RUN of an installed definition as the
-- agent an administrator bound to it -- the substrate's own enqueue, so every
-- step still goes through the plane's scope check, budgets, audit and key.
--
-- ---------------------------------------------------------------------------
-- What this migration does NOT do
-- ---------------------------------------------------------------------------
--
-- **Nothing moves in `api`.** The emitter lives in `app`, a schema PostgREST
-- does not expose and no request role holds USAGE on (rig 34a: every request
-- role and `auth_service` meet `42501 permission denied for schema app`, and
-- `POST /rpc/emit_event` is PostgREST's `PGRST202`). It is GRANTED TO NOBODY:
-- only a function already running as the object owner -- the release's own, or
-- a project set's reviewed definer RPC -- can call it (ADR 0235, D1779). So
-- there is no `NOTIFY pgrst`.
--
-- **No trigger writes an event, anywhere.** An event is what a reviewed
-- function says happened, in the transaction that made it happen; a rolled-back
-- caller rolls its event back (rig 34a: 3 rows before, 3 after).
--
-- **An event is recorded only when something listens** (D1782). No outbound
-- subscriber, no row -- a log nobody reads is retention with no reader (ADR
-- 0213's shape, and D1700/D1775 already owe one).
--
-- **No endpoint leaves this schema except through the claim.** The URL is a
-- per-deployment value the deploy writes into the connector row (D1786); only
-- `connector_claim_delivery` returns it, for one attempt, and never for a
-- rehearsal. No status, no count and no error carries it.
--
-- **No 0034 or 0035 signature moves.** `workflow_gate_state` and
-- `workflow_counts` are replaced in place with the SAME argument and result
-- types, so 0035's grants stand. Neither 0034 nor 0035 is amended (D912).
--
-- **No RLS, no new errcode.** The four new tables take 0034's posture (D1647):
-- no role holds a privilege, every path is a definer function. The refusals
-- reuse PT401, PT403, PT404, PT409 and PT422, each message a token the auth
-- service reads for one word.
SET LOCAL ROLE {{object_owner}};

CREATE TYPE app_private.connector_kind AS ENUM ('outbound', 'inbound', 'scheduled');

CREATE TYPE app_private.delivery_status AS ENUM ('pending', 'delivered', 'dead');

-- ---------------------------------------------------------------------------
-- The connector: what the project file declares, and where this deployment sends
-- ---------------------------------------------------------------------------
--
-- `body` is the COMPILED file (ADR 0236): an inbound connector's closed `body`
-- declaration under the key `body`, a scheduled connector's literal `input`
-- under `input`. Never an endpoint -- that is `endpoint`, written by the deploy
-- from the installed manifest (D1786). One agent, one connector: the partial
-- unique index is `agent_already_bound`.
CREATE TABLE app_private.connector (
  id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name               text        NOT NULL UNIQUE CHECK (name ~ '^[a-z][a-z0-9-]{0,62}$'),
  version            integer     NOT NULL CHECK (version BETWEEN 1 AND 9999),
  kind               app_private.connector_kind NOT NULL,
  body               jsonb       NOT NULL,
  source_sha256      text        NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
  event              text        CHECK (event IS NULL OR event ~ '^[a-z][a-z0-9_.]{0,254}@[0-9]{1,3}$'),
  endpoint           text,
  definition_name    text,
  definition_version integer,
  required_scopes    text[]      NOT NULL DEFAULT '{}',
  every_seconds      integer     CHECK (every_seconds IS NULL OR every_seconds BETWEEN 60 AND 86400),
  retry_max          integer     CHECK (retry_max IS NULL OR retry_max BETWEEN 0 AND 10),
  backoff_seconds    integer     CHECK (backoff_seconds IS NULL OR backoff_seconds BETWEEN 1 AND 3600),
  enabled            boolean     NOT NULL DEFAULT false,
  agent_id           uuid        REFERENCES app_private.agents (id),
  enabled_by         uuid        REFERENCES app_private.users (id),
  enabled_at         timestamptz,
  disabled_by        uuid        REFERENCES app_private.users (id),
  disabled_at        timestamptz,
  next_fire_at       timestamptz,
  installed_at       timestamptz NOT NULL DEFAULT now(),
  CHECK (
    (kind = 'outbound'
       AND event IS NOT NULL AND retry_max IS NOT NULL AND backoff_seconds IS NOT NULL
       AND definition_name IS NULL AND every_seconds IS NULL AND agent_id IS NULL)
    OR (kind = 'inbound'
       AND definition_name IS NOT NULL AND definition_version IS NOT NULL
       AND event IS NULL AND endpoint IS NULL AND every_seconds IS NULL)
    OR (kind = 'scheduled'
       AND definition_name IS NOT NULL AND definition_version IS NOT NULL
       AND every_seconds IS NOT NULL AND event IS NULL AND endpoint IS NULL)
  )
);

CREATE UNIQUE INDEX connector_agent_key
  ON app_private.connector (agent_id) WHERE agent_id IS NOT NULL;

COMMENT ON TABLE app_private.connector IS
  'One installed connector (ADR 0236): installed DISABLED by the deploy, enabled '
  'by an administrator, bound to at most one agent. The endpoint is this '
  'deployment''s and leaves this table only through the delivery claim.';

-- ---------------------------------------------------------------------------
-- The outbox: one event, one delivery per subscriber
-- ---------------------------------------------------------------------------
--
-- `agent_id` carries no foreign key, the audit's convention (0019): an event
-- outlives nothing it names. `owner_id` is NULL for the rehearsal's event
-- alone, and the CHECK says so rather than a nil uuid looking measured (D600).
CREATE TABLE app_private.connector_event (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text        NOT NULL,
  version    integer     NOT NULL CHECK (version BETWEEN 1 AND 999),
  owner_id   uuid,
  agent_id   uuid,
  payload    jsonb       NOT NULL,
  emitted_at timestamptz NOT NULL DEFAULT now(),
  CHECK (owner_id IS NOT NULL OR name = 'apg.rehearsal')
);

CREATE TABLE app_private.connector_delivery (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id        uuid        NOT NULL REFERENCES app_private.connector_event (id),
  connector_id    uuid        NOT NULL REFERENCES app_private.connector (id),
  status          app_private.delivery_status NOT NULL DEFAULT 'pending',
  attempts        integer     NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  max_attempts    integer     NOT NULL CHECK (max_attempts BETWEEN 1 AND 11),
  backoff_seconds integer     NOT NULL CHECK (backoff_seconds BETWEEN 1 AND 3600),
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  claimed_by      text,
  lease_until     timestamptz,
  last_status     integer,
  last_error      text        CHECK (last_error IS NULL OR last_error ~
                    '^(http_[0-9]{3}|timeout|connect_failed|tls_failed|dns_failed|unknown)$'),
  rehearsal       boolean     NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now(),
  delivered_at    timestamptz,
  dead_at         timestamptz
);

CREATE INDEX connector_delivery_status_next_idx
  ON app_private.connector_delivery (status, next_attempt_at);

COMMENT ON TABLE app_private.connector_delivery IS
  'The outbox proper: one row per (event, subscriber), at-least-once, a fixed '
  'backoff, dead after max_attempts (ADR 0238). last_error is a fixed token and '
  'never a message; no row carries the endpoint.';

-- ---------------------------------------------------------------------------
-- Receipts: exactly-once acceptance of an inbound delivery
-- ---------------------------------------------------------------------------
--
-- The primary key IS the replay refusal (ADR 0237): a delivery id is inside
-- the signed bytes, so a new id breaks the signature and the same id meets
-- this key. Written in the transaction that enqueues the run, so a refused
-- enqueue leaves no receipt.
CREATE TABLE app_private.connector_receipt (
  connector_id uuid        NOT NULL REFERENCES app_private.connector (id),
  delivery_id  uuid        NOT NULL,
  received_at  timestamptz NOT NULL DEFAULT now(),
  run_id       uuid        REFERENCES app_private.workflow_run (id),
  PRIMARY KEY (connector_id, delivery_id)
);

-- ---------------------------------------------------------------------------
-- The event wait's four columns (ADR 0239)
-- ---------------------------------------------------------------------------
ALTER TABLE app_private.workflow_step
  ADD COLUMN await_event     text CHECK (await_event IS NULL OR await_event ~ '^[a-z][a-z0-9_.]{0,254}@[0-9]{1,3}$'),
  ADD COLUMN await_match     jsonb,
  ADD COLUMN await_payload   jsonb,
  ADD COLUMN await_served_at timestamptz;

-- The emitter's UPDATE reads only the unserved waits, so the index holds only
-- them.
CREATE INDEX workflow_step_await_idx
  ON app_private.workflow_step (await_event)
  WHERE await_event IS NOT NULL AND await_served_at IS NULL;

-- ---------------------------------------------------------------------------
-- The emitter (ADR 0235)
-- ---------------------------------------------------------------------------
--
-- Identity from the GUCs the pre-request hook set -- `app.user_id` is the
-- human, or an agent's OWNER, and `app.agent_id` the agent -- never from a
-- parameter (SEC-PARAM-001's rule). Two things, in the caller's transaction:
--
--   1. every parked wait of the SAME OWNER awaiting `name@version` whose
--      resolved match the payload contains is served, and made claimable now;
--   2. if an ENABLED outbound connector subscribes and has an endpoint, one
--      event and one delivery per such connector are recorded.
--
-- Returns the event's id, or NULL when no delivery was recorded.
CREATE FUNCTION app.emit_event(p_name text, p_version integer, p_payload jsonb)
  RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  caller       uuid := app.current_user_id();
  acting_agent uuid := nullif(pg_catalog.current_setting('app.agent_id', true), '')::uuid;
  reference    text;
  recorded     uuid;
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'AP401: an event needs a request identity' USING ERRCODE = 'PT401';
  END IF;
  IF p_name IS NULL
     OR p_name !~ '^[a-z][a-z0-9_]{0,62}(\.[a-z][a-z0-9_]{0,62}){0,3}$' THEN
    RAISE EXCEPTION 'AP422: event_name_invalid' USING ERRCODE = 'PT422';
  END IF;
  IF p_version IS NULL OR p_version NOT BETWEEN 1 AND 999 THEN
    RAISE EXCEPTION 'AP422: event_version_invalid' USING ERRCODE = 'PT422';
  END IF;
  IF p_payload IS NULL
     OR jsonb_typeof(p_payload) <> 'object'
     OR octet_length(p_payload::text) > 8192 THEN
    RAISE EXCEPTION 'AP422: event_payload_invalid'
      USING ERRCODE = 'PT422',
            HINT = 'A payload is a JSON object of at most 8,192 bytes.';
  END IF;
  reference := p_name || '@' || p_version;

  UPDATE app_private.workflow_step s
     SET await_payload = p_payload,
         await_served_at = pg_catalog.now(),
         resume_after = pg_catalog.now()
    FROM app_private.workflow_run r
   WHERE r.id = s.run_id
     AND s.status = 'parked'
     AND s.await_event = reference
     AND s.await_served_at IS NULL
     AND r.status = 'running'
     AND r.owner_id = caller
     AND p_payload @> coalesce(s.await_match, '{}'::jsonb);

  IF NOT EXISTS (
       SELECT 1 FROM app_private.connector c
        WHERE c.enabled AND c.kind = 'outbound' AND c.event = reference
          AND c.endpoint IS NOT NULL) THEN
    RETURN NULL;
  END IF;

  INSERT INTO app_private.connector_event (name, version, owner_id, agent_id, payload)
  VALUES (p_name, p_version, caller, acting_agent, p_payload)
  RETURNING id INTO recorded;

  INSERT INTO app_private.connector_delivery (event_id, connector_id, max_attempts, backoff_seconds)
  SELECT recorded, c.id, c.retry_max + 1, c.backoff_seconds
    FROM app_private.connector c
   WHERE c.enabled AND c.kind = 'outbound' AND c.event = reference
     AND c.endpoint IS NOT NULL;

  RETURN recorded;
END $fn$;

COMMENT ON FUNCTION app.emit_event(text, integer, jsonb) IS
  'Records a versioned event in the caller''s transaction (ADR 0235). Granted to '
  'NOBODY: only a definer function running as the owner can call it. Serves the '
  'same owner''s matching waits and records one delivery per enabled outbound '
  'subscriber with an endpoint; returns NULL when nothing listens.';

-- ---------------------------------------------------------------------------
-- The binding rule, written once (ADR 0236, D1783)
-- ---------------------------------------------------------------------------
--
-- An agent bound to an inbound or scheduled connector holds EXACTLY the
-- definition's scopes -- rig 34c measured a tool call served with the tool's
-- own scope alone, so `meta:read` is not part of the equality. Called by
-- enable, accept, fire and status, and granted to nobody.
CREATE FUNCTION app_private.connector_scopes_match(p_agent uuid, p_required text[])
  RETURNS boolean
  LANGUAGE sql
  STABLE
  SET search_path = pg_catalog, pg_temp
AS $fn$
  SELECT EXISTS (
    SELECT 1 FROM app_private.agents a
     WHERE a.id = p_agent
       AND a.scopes @> p_required
       AND a.scopes <@ p_required);
$fn$;

-- ---------------------------------------------------------------------------
-- Installing (the deploy's call, as the bootstrap superuser; granted to nobody)
-- ---------------------------------------------------------------------------
--
-- A connector is immutable per (name, version) -- the definition's rule (ADR
-- 0228) -- except for its endpoint, which is the deployment's, not the file's.
-- A higher version replaces the body; if what the connector DOES changed (its
-- kind, its event, its definition or the scopes that definition needs) it is
-- left DISABLED and unbound, because the agent an administrator bound was
-- bound to the old one.
-- The parameter list is written without column alignment on purpose: ADR
-- 0175's signature walk reads an argument list within 400 characters (D1450),
-- and the aligned form of these thirteen was longer than that, so the walk
-- skipped the declaration and then called every reference to it stale (D1821).
CREATE FUNCTION app_private.connector_install(
  p_name text, p_version integer, p_kind app_private.connector_kind, p_body jsonb,
  p_source_sha256 text, p_event text, p_endpoint text, p_definition_name text,
  p_definition_version integer, p_required_scopes text[], p_every_seconds integer,
  p_retry_max integer, p_backoff_seconds integer
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  existing app_private.connector;
  changed  boolean;
BEGIN
  SELECT * INTO existing FROM app_private.connector WHERE name = p_name FOR UPDATE;
  IF NOT FOUND THEN
    INSERT INTO app_private.connector
      (name, version, kind, body, source_sha256, event, endpoint, definition_name,
       definition_version, required_scopes, every_seconds, retry_max, backoff_seconds)
    VALUES
      (p_name, p_version, p_kind, p_body, p_source_sha256, p_event, p_endpoint,
       p_definition_name, p_definition_version, coalesce(p_required_scopes, '{}'),
       p_every_seconds, p_retry_max, p_backoff_seconds);
    RETURN 'installed';
  END IF;

  IF p_version < existing.version THEN
    RAISE EXCEPTION 'AP409: a newer version of this connector is installed'
      USING ERRCODE = 'PT409';
  END IF;

  IF p_version = existing.version THEN
    IF p_source_sha256 <> existing.source_sha256 THEN
      RAISE EXCEPTION 'AP409: this connector version is installed with other content'
        USING ERRCODE = 'PT409',
              HINT = 'A connector is immutable per name and version. Publish a new version.';
    END IF;
    IF existing.endpoint IS DISTINCT FROM p_endpoint THEN
      UPDATE app_private.connector SET endpoint = p_endpoint WHERE id = existing.id;
      RETURN 'endpoint_updated';
    END IF;
    RETURN 'unchanged';
  END IF;

  changed := existing.kind <> p_kind
          OR existing.event IS DISTINCT FROM p_event
          OR existing.definition_name IS DISTINCT FROM p_definition_name
          OR existing.definition_version IS DISTINCT FROM p_definition_version
          OR NOT (existing.required_scopes @> coalesce(p_required_scopes, '{}')
                  AND existing.required_scopes <@ coalesce(p_required_scopes, '{}'));

  UPDATE app_private.connector
     SET version = p_version, kind = p_kind, body = p_body, source_sha256 = p_source_sha256,
         event = p_event, endpoint = p_endpoint, definition_name = p_definition_name,
         definition_version = p_definition_version,
         required_scopes = coalesce(p_required_scopes, '{}'),
         every_seconds = p_every_seconds, retry_max = p_retry_max,
         backoff_seconds = p_backoff_seconds,
         enabled = CASE WHEN changed THEN false ELSE enabled END,
         agent_id = CASE WHEN changed THEN NULL ELSE agent_id END,
         next_fire_at = CASE WHEN changed THEN NULL ELSE next_fire_at END,
         installed_at = pg_catalog.now()
   WHERE id = existing.id;
  RETURN CASE WHEN changed THEN 'replaced_disabled' ELSE 'replaced' END;
END $fn$;

COMMENT ON FUNCTION app_private.connector_install(
  text, integer, app_private.connector_kind, jsonb, text, text, text, text, integer, text[],
  integer, integer, integer) IS
  'The deploy''s call (step 6e), as the bootstrap superuser; granted to nobody '
  '(ADR 0236). Installs DISABLED; immutable per name and version except for the '
  'endpoint; a higher version that changes what the connector does is left '
  'disabled and unbound.';

-- ---------------------------------------------------------------------------
-- Delivering (the worker's second pass, ADR 0238)
-- ---------------------------------------------------------------------------
--
-- The claim first retires any pending delivery whose lease expired on its
-- LAST attempt -- it is dead, not due -- and then leases at most one due
-- delivery. A rehearsal's delivery is claimable whatever the connector's
-- state and its endpoint is never returned: the worker sends it to the
-- container's discard port instead (the `delivery-retry-storm` rehearsal).
CREATE FUNCTION app_private.connector_claim_delivery(
  p_holder        text,
  p_lease_seconds integer
) RETURNS TABLE (
  delivery_id    uuid,
  connector_name text,
  endpoint       text,
  rehearsal      boolean,
  event_id       uuid,
  event_name     text,
  event_version  integer,
  emitted_at     timestamptz,
  payload        jsonb,
  attempt        integer,
  max_attempts   integer
)
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  picked uuid;
BEGIN
  IF p_holder IS NULL OR p_holder = '' THEN
    RAISE EXCEPTION 'AP422: holder_required' USING ERRCODE = 'PT422';
  END IF;
  IF p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 1 AND 600 THEN
    RAISE EXCEPTION 'AP422: lease_invalid' USING ERRCODE = 'PT422';
  END IF;

  UPDATE app_private.connector_delivery d
     SET status = 'dead', dead_at = pg_catalog.now(), claimed_by = NULL, lease_until = NULL,
         last_error = coalesce(d.last_error, 'unknown')
   WHERE d.status = 'pending'
     AND d.claimed_by IS NOT NULL
     AND d.lease_until < pg_catalog.now()
     AND d.attempts >= d.max_attempts;

  SELECT d.id INTO picked
    FROM app_private.connector_delivery d
    JOIN app_private.connector c ON c.id = d.connector_id
   WHERE d.status = 'pending'
     AND d.attempts < d.max_attempts
     AND ((d.claimed_by IS NULL AND d.next_attempt_at <= pg_catalog.now())
          OR (d.claimed_by IS NOT NULL AND d.lease_until < pg_catalog.now()))
     AND (d.rehearsal OR (c.enabled AND c.endpoint IS NOT NULL))
   ORDER BY d.next_attempt_at, d.id
   LIMIT 1
   FOR UPDATE OF d SKIP LOCKED;
  IF picked IS NULL THEN
    RETURN;
  END IF;

  UPDATE app_private.connector_delivery d
     SET claimed_by = p_holder,
         lease_until = pg_catalog.now() + pg_catalog.make_interval(secs => p_lease_seconds),
         attempts = d.attempts + 1
   WHERE d.id = picked;

  RETURN QUERY
    SELECT d.id, c.name, CASE WHEN d.rehearsal THEN NULL ELSE c.endpoint END, d.rehearsal,
           e.id, e.name, e.version, e.emitted_at, e.payload, d.attempts, d.max_attempts
      FROM app_private.connector_delivery d
      JOIN app_private.connector c ON c.id = d.connector_id
      JOIN app_private.connector_event e ON e.id = d.event_id
     WHERE d.id = picked;
END $fn$;

COMMENT ON FUNCTION app_private.connector_claim_delivery(text, integer) IS
  'Leases at most one due delivery for one attempt (ADR 0238). The ONLY function '
  'that returns an endpoint, and never a rehearsal''s. A lease that expired on '
  'the last attempt is dead, not due.';

CREATE FUNCTION app_private.connector_finish_delivery(
  p_delivery  uuid,
  p_holder    text,
  p_delivered boolean,
  p_status    integer,
  p_error     text
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  held app_private.connector_delivery;
BEGIN
  SELECT * INTO held FROM app_private.connector_delivery d
   WHERE d.id = p_delivery AND d.claimed_by = p_holder AND d.status = 'pending'
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN 'lease_lost';
  END IF;

  IF p_delivered THEN
    UPDATE app_private.connector_delivery
       SET status = 'delivered', delivered_at = pg_catalog.now(), last_status = p_status,
           last_error = NULL, claimed_by = NULL, lease_until = NULL
     WHERE id = p_delivery;
    RETURN 'delivered';
  END IF;

  IF p_error IS NULL
     OR p_error !~ '^(http_[0-9]{3}|timeout|connect_failed|tls_failed|dns_failed|unknown)$' THEN
    RAISE EXCEPTION 'AP422: error_token_invalid'
      USING ERRCODE = 'PT422',
            HINT = 'A delivery records a fixed token, never a message (ADR 0238).';
  END IF;

  IF held.attempts >= held.max_attempts THEN
    UPDATE app_private.connector_delivery
       SET status = 'dead', dead_at = pg_catalog.now(), last_status = p_status,
           last_error = p_error, claimed_by = NULL, lease_until = NULL
     WHERE id = p_delivery;
    RETURN 'dead';
  END IF;

  UPDATE app_private.connector_delivery
     SET next_attempt_at = pg_catalog.now()
                           + pg_catalog.make_interval(secs => held.backoff_seconds),
         last_status = p_status, last_error = p_error, claimed_by = NULL, lease_until = NULL
   WHERE id = p_delivery;
  RETURN 'pending';
END $fn$;

COMMENT ON FUNCTION app_private.connector_finish_delivery(uuid, text, boolean, integer, text) IS
  'Records one attempt''s result (ADR 0238): delivered; or pending again after the '
  'fixed backoff; or dead once max_attempts are spent. A holder that lost its '
  'lease gets ''lease_lost''. The error is a fixed token.';

-- ---------------------------------------------------------------------------
-- The schedule (ADR 0236, D1799)
-- ---------------------------------------------------------------------------
--
-- The interval table is the connector row's own `next_fire_at`. A due connector
-- is advanced from NOW, so missed fires coalesce to one: a worker that was down
-- fires once, not a backlog. A binding that no longer holds (the agent widened
-- or revoked, the definition gone) advances and enqueues nothing; the status
-- document computes `binding` on read, so the refusal is reported where an
-- operator looks and no row is written for a skip. Takes no holder: nothing
-- here records one, and a parameter nothing reads is a declared field with no
-- reader (D816, D1819).
CREATE FUNCTION app_private.connector_fire_due()
  RETURNS integer
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  due   app_private.connector;
  fired integer := 0;
BEGIN
  FOR due IN
    SELECT * FROM app_private.connector c
     WHERE c.enabled AND c.kind = 'scheduled' AND c.agent_id IS NOT NULL
       AND c.next_fire_at <= pg_catalog.now()
     ORDER BY c.next_fire_at
     FOR UPDATE SKIP LOCKED
  LOOP
    UPDATE app_private.connector
       SET next_fire_at = pg_catalog.now() + pg_catalog.make_interval(secs => due.every_seconds)
     WHERE id = due.id;
    CONTINUE WHEN NOT app_private.connector_scopes_match(due.agent_id, due.required_scopes);
    BEGIN
      PERFORM app_private.workflow_enqueue(
        due.agent_id, due.definition_name, due.definition_version,
        coalesce(due.body -> 'input', '{}'::jsonb), false);
      fired := fired + 1;
    EXCEPTION WHEN SQLSTATE 'PT403' OR SQLSTATE 'PT404' OR SQLSTATE 'PT409' THEN
      -- The agent was revoked or the definition is gone: one connector's
      -- refusal must not stop the others' fires.
      NULL;
    END;
  END LOOP;
  RETURN fired;
END $fn$;

COMMENT ON FUNCTION app_private.connector_fire_due() IS
  'Enqueues one run per due, enabled, bound scheduled connector as its agent and '
  'advances next_fire_at from now, so missed fires coalesce to one (ADR 0236). '
  'A binding that no longer holds advances and fires nothing.';

-- ---------------------------------------------------------------------------
-- Inbound (the route's calls, after the signature, ADR 0237)
-- ---------------------------------------------------------------------------
CREATE FUNCTION app_private.connector_inbound(p_name text)
  RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  found_connector app_private.connector;
BEGIN
  SELECT * INTO found_connector FROM app_private.connector c
   WHERE c.name = p_name AND c.kind = 'inbound';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no_such_connector' USING ERRCODE = 'PT404';
  END IF;
  RETURN jsonb_build_object(
    'connector_id', found_connector.id,
    'body_declaration', coalesce(found_connector.body -> 'body', '{}'::jsonb));
END $fn$;

COMMENT ON FUNCTION app_private.connector_inbound(text) IS
  'An installed inbound connector''s id and closed body declaration, read by the '
  'route only after the signature holds (ADR 0237).';

-- ONE transaction: the receipt, the enqueue and the receipt's run id. A
-- refused enqueue (the agent revoked, the definition gone) raises out of this
-- function and takes the receipt with it, so a sender may retry the SAME
-- delivery id once the refusal is repaired.
CREATE FUNCTION app_private.connector_accept(
  p_name     text,
  p_delivery uuid,
  p_input    jsonb
) RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  bound app_private.connector;
  run   uuid;
BEGIN
  SELECT * INTO bound FROM app_private.connector c
   WHERE c.name = p_name AND c.kind = 'inbound';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no_such_connector' USING ERRCODE = 'PT404';
  END IF;
  IF NOT bound.enabled OR bound.agent_id IS NULL THEN
    RAISE EXCEPTION 'AP409: connector_disabled' USING ERRCODE = 'PT409';
  END IF;
  IF NOT app_private.connector_scopes_match(bound.agent_id, bound.required_scopes) THEN
    RAISE EXCEPTION 'AP409: agent_scopes_differ' USING ERRCODE = 'PT409';
  END IF;

  INSERT INTO app_private.connector_receipt (connector_id, delivery_id)
  VALUES (bound.id, p_delivery)
  ON CONFLICT DO NOTHING;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP409: delivery_replayed' USING ERRCODE = 'PT409';
  END IF;

  run := app_private.workflow_enqueue(
    bound.agent_id, bound.definition_name, bound.definition_version,
    coalesce(p_input, '{}'::jsonb), false);

  UPDATE app_private.connector_receipt
     SET run_id = run
   WHERE connector_id = bound.id AND delivery_id = p_delivery;
  RETURN run;
END $fn$;

COMMENT ON FUNCTION app_private.connector_accept(text, uuid, jsonb) IS
  'Accepts one signed inbound delivery exactly once and starts a run of the '
  'connector''s definition as its bound agent, in one transaction (ADR 0236, '
  'ADR 0237). Refuses no_such_connector, connector_disabled, agent_scopes_differ '
  'and delivery_replayed; a refused enqueue leaves no receipt.';

-- ---------------------------------------------------------------------------
-- Enabling and disabling (an administrator's calls, ADR 0236)
-- ---------------------------------------------------------------------------
CREATE FUNCTION app_private.connector_enable(p_name text, p_agent uuid, p_user uuid)
  RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  target  app_private.connector;
  agent   app_private.agents;
  missing text[];
  extra   text[];
BEGIN
  SELECT * INTO target FROM app_private.connector c WHERE c.name = p_name FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no_such_connector' USING ERRCODE = 'PT404';
  END IF;

  IF target.kind = 'outbound' THEN
    IF p_agent IS NOT NULL THEN
      RAISE EXCEPTION 'AP422: agent_not_needed'
        USING ERRCODE = 'PT422',
              HINT = 'An outbound connector acts as nobody; it is bound to no agent.';
    END IF;
    IF target.endpoint IS NULL THEN
      RAISE EXCEPTION 'AP409: no_endpoint'
        USING ERRCODE = 'PT409',
              HINT = 'Declare connectors.endpoints.<name> in the project manifest and redeploy.';
    END IF;
  ELSE
    SELECT * INTO agent FROM app_private.agents a WHERE a.id = p_agent;
    IF NOT FOUND OR agent.status <> 'active' THEN
      RAISE EXCEPTION 'AP409: agent_not_active' USING ERRCODE = 'PT409';
    END IF;
    IF EXISTS (SELECT 1 FROM app_private.connector c
                WHERE c.agent_id = p_agent AND c.id <> target.id) THEN
      RAISE EXCEPTION 'AP409: agent_already_bound' USING ERRCODE = 'PT409';
    END IF;
    IF NOT app_private.connector_scopes_match(p_agent, target.required_scopes) THEN
      SELECT coalesce(array_agg(s ORDER BY s), '{}') INTO missing
        FROM unnest(target.required_scopes) s WHERE NOT (s = ANY (agent.scopes));
      SELECT coalesce(array_agg(s ORDER BY s), '{}') INTO extra
        FROM unnest(agent.scopes) s WHERE NOT (s = ANY (target.required_scopes));
      RAISE EXCEPTION 'AP409: agent_scopes_differ'
        USING ERRCODE = 'PT409',
              DETAIL = pg_catalog.format('missing %s; extra %s', missing, extra),
              HINT = 'The bound agent must hold exactly the definition''s scopes.';
    END IF;
  END IF;

  UPDATE app_private.connector
     SET enabled = true,
         agent_id = CASE WHEN target.kind = 'outbound' THEN NULL ELSE p_agent END,
         enabled_by = p_user,
         enabled_at = pg_catalog.now(),
         disabled_by = NULL,
         disabled_at = NULL,
         next_fire_at = CASE WHEN target.kind = 'scheduled' THEN pg_catalog.now() END
   WHERE id = target.id;
  RETURN 'enabled';
END $fn$;

COMMENT ON FUNCTION app_private.connector_enable(text, uuid, uuid) IS
  'Enables one connector and records who did (ADR 0236). An inbound or scheduled '
  'connector binds an active agent holding EXACTLY its definition''s scopes and '
  'no other connector; an outbound one needs an endpoint and no agent.';

-- A NULL user is the bootstrap superuser: the trip's cleanup disables as
-- `postgres`, and the status document reads that as the operator (Run 10).
-- Pending deliveries stay where they are, held rather than sent: the claim
-- requires an enabled connector.
CREATE FUNCTION app_private.connector_disable(p_name text, p_user uuid)
  RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
  UPDATE app_private.connector
     SET enabled = false, agent_id = NULL, next_fire_at = NULL,
         disabled_by = p_user, disabled_at = pg_catalog.now()
   WHERE name = p_name;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no_such_connector' USING ERRCODE = 'PT404';
  END IF;
  RETURN 'disabled';
END $fn$;

COMMENT ON FUNCTION app_private.connector_disable(text, uuid) IS
  'Disables one connector, unbinds its agent and clears its schedule; pending '
  'deliveries are held, not sent (ADR 0236).';

-- ---------------------------------------------------------------------------
-- The status document (ADR 0236, ADR 0195)
-- ---------------------------------------------------------------------------
--
-- Never `endpoint`, `payload` or `body`, at any depth: `endpoint_declared` says
-- whether there is one, and a dead letter names its event and its token. The
-- binding is computed on READ, so a widened agent shows `agent_scopes_differ`
-- here without any pass having written it.
CREATE FUNCTION app_private.connector_status(p_dead_limit integer)
  RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
  IF p_dead_limit IS NULL OR p_dead_limit NOT BETWEEN 1 AND 20 THEN
    RAISE EXCEPTION 'AP422: dead_limit_invalid' USING ERRCODE = 'PT422';
  END IF;

  RETURN jsonb_build_object('connectors', coalesce((
    SELECT jsonb_agg(jsonb_build_object(
             'name', c.name,
             'version', c.version,
             'kind', c.kind::text,
             'enabled', c.enabled,
             'agent_id', c.agent_id,
             'event', c.event,
             'definition', CASE WHEN c.definition_name IS NULL THEN NULL
                                ELSE c.definition_name || '@' || c.definition_version END,
             'every_seconds', c.every_seconds,
             'next_fire_at', c.next_fire_at,
             'endpoint_declared', c.endpoint IS NOT NULL,
             'enabled_by', c.enabled_by,
             'enabled_at', c.enabled_at,
             'disabled_by', c.disabled_by,
             'disabled_at', c.disabled_at,
             'binding', CASE
               WHEN c.kind = 'outbound' THEN 'not_applicable'
               WHEN c.agent_id IS NULL THEN 'unbound'
               WHEN NOT EXISTS (SELECT 1 FROM app_private.agents a
                                 WHERE a.id = c.agent_id AND a.status = 'active')
                 THEN 'agent_not_active'
               WHEN NOT app_private.connector_scopes_match(c.agent_id, c.required_scopes)
                 THEN 'agent_scopes_differ'
               ELSE 'ok' END,
             'deliveries', jsonb_build_object(
               'pending', (SELECT count(*) FROM app_private.connector_delivery d
                            WHERE d.connector_id = c.id AND d.status = 'pending'),
               'delivered', (SELECT count(*) FROM app_private.connector_delivery d
                              WHERE d.connector_id = c.id AND d.status = 'delivered'),
               'dead', (SELECT count(*) FROM app_private.connector_delivery d
                         WHERE d.connector_id = c.id AND d.status = 'dead')),
             'oldest_pending_age_seconds',
               (SELECT floor(extract(epoch FROM pg_catalog.now() - min(d.created_at)))::bigint
                  FROM app_private.connector_delivery d
                 WHERE d.connector_id = c.id AND d.status = 'pending'),
             'last_error',
               (SELECT d.last_error FROM app_private.connector_delivery d
                 WHERE d.connector_id = c.id AND d.last_error IS NOT NULL
                 ORDER BY coalesce(d.dead_at, d.next_attempt_at) DESC, d.id DESC
                 LIMIT 1),
             'receipts', (SELECT count(*) FROM app_private.connector_receipt r
                           WHERE r.connector_id = c.id),
             'dead_letters', coalesce((
               SELECT jsonb_agg(jsonb_build_object(
                        'delivery_id', dead.id,
                        'event', dead.event,
                        'attempts', dead.attempts,
                        'last_error', dead.last_error,
                        'dead_at', dead.dead_at) ORDER BY dead.dead_at DESC)
                 FROM (SELECT d.id, e.name || '@' || e.version AS event, d.attempts,
                              d.last_error, d.dead_at
                         FROM app_private.connector_delivery d
                         JOIN app_private.connector_event e ON e.id = d.event_id
                        WHERE d.connector_id = c.id AND d.status = 'dead'
                        ORDER BY d.dead_at DESC
                        LIMIT p_dead_limit) dead), '[]'::jsonb))
           ORDER BY c.name)
      FROM app_private.connector c), '[]'::jsonb));
END $fn$;

COMMENT ON FUNCTION app_private.connector_status(integer) IS
  'Every connector with its counts, its binding, its last error token and up to '
  'p_dead_limit dead letters (ADR 0236). Never an endpoint, a payload or a body.';

-- ---------------------------------------------------------------------------
-- The rehearsal's one delivery (granted to nobody, ADR 0238, D1801)
-- ---------------------------------------------------------------------------
CREATE FUNCTION app_private.connector_rehearse_delivery(p_connector text)
  RETURNS uuid
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  target   app_private.connector;
  recorded uuid;
  made     uuid;
BEGIN
  SELECT * INTO target FROM app_private.connector c
   WHERE c.name = p_connector AND c.kind = 'outbound';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no_such_connector' USING ERRCODE = 'PT404';
  END IF;
  INSERT INTO app_private.connector_event (name, version, owner_id, agent_id, payload)
  VALUES ('apg.rehearsal', 1, NULL, NULL, '{"rehearsal": true}'::jsonb)
  RETURNING id INTO recorded;
  INSERT INTO app_private.connector_delivery
    (event_id, connector_id, max_attempts, backoff_seconds, rehearsal)
  VALUES (recorded, target.id, 3, 2, true)
  RETURNING id INTO made;
  RETURN made;
END $fn$;

COMMENT ON FUNCTION app_private.connector_rehearse_delivery(text) IS
  'Induces one rehearsal delivery for an installed outbound connector: three '
  'attempts, two seconds apart, sent to the container''s discard port and never '
  'to the endpoint (ADR 0238). Granted to nobody; the rehearsal runs it as the '
  'bootstrap superuser.';

-- ---------------------------------------------------------------------------
-- The event wait (ADR 0239)
-- ---------------------------------------------------------------------------
--
-- Records what the step waits for, then parks it through `workflow_park` --
-- called, not copied, so the attempt row is written exactly as every other park
-- writes it. An event emitted before the park does not serve it: a wait waits
-- for what happens after it began.
CREATE FUNCTION app_private.workflow_await_event(
  p_step         uuid,
  p_holder       text,
  p_event        text,
  p_match        jsonb,
  p_resume_after timestamptz
) RETURNS text
  LANGUAGE plpgsql
  VOLATILE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
  IF p_event IS NULL OR p_event !~ '^[a-z][a-z0-9_.]{0,254}@[0-9]{1,3}$' THEN
    RAISE EXCEPTION 'AP422: event_reference_invalid' USING ERRCODE = 'PT422';
  END IF;
  IF p_match IS NULL OR jsonb_typeof(p_match) <> 'object' THEN
    RAISE EXCEPTION 'AP422: match_invalid' USING ERRCODE = 'PT422';
  END IF;

  UPDATE app_private.workflow_step s
     SET await_event = p_event, await_match = p_match,
         await_payload = NULL, await_served_at = NULL
   WHERE s.id = p_step AND s.claimed_by = p_holder AND s.status = 'claimed';
  IF NOT FOUND THEN
    RETURN 'lease_lost';
  END IF;
  RETURN app_private.workflow_park(p_step, p_holder, 'awaiting_event', p_resume_after, NULL);
END $fn$;

COMMENT ON FUNCTION app_private.workflow_await_event(uuid, text, text, jsonb, timestamptz) IS
  'Parks a wait step on an event until p_resume_after, recording the event and '
  'its resolved match (ADR 0239). The emitter serves it for the run''s owner only.';

-- ---------------------------------------------------------------------------
-- The gate read and the counts (replaced; 0035's signatures)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app_private.workflow_gate_state(
  p_step   uuid,
  p_holder text
) RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  approval jsonb;
  held     app_private.workflow_step;
BEGIN
  SELECT * INTO held FROM app_private.workflow_step s
   WHERE s.id = p_step AND s.claimed_by = p_holder AND s.status = 'claimed';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'AP404: no such step' USING ERRCODE = 'PT404';
  END IF;

  SELECT jsonb_build_object(
           'id', a.id,
           'status', CASE
             WHEN a.status = 'pending' AND a.expires_at <= pg_catalog.now() THEN 'expired'
             ELSE a.status::text
           END,
           'expires_at', a.expires_at)
    INTO approval
    FROM app_private.workflow_approval a
   WHERE a.step_id = p_step;

  RETURN jsonb_build_object(
    'approval', approval,
    'waited', EXISTS (
      SELECT 1 FROM app_private.workflow_attempt t
       WHERE t.step_id = p_step AND t.event = 'parked' AND t.reason = 'waiting'),
    'event', CASE WHEN held.await_event IS NULL THEN NULL
                  ELSE jsonb_build_object(
                         'served', held.await_served_at IS NOT NULL,
                         'payload', held.await_payload)
             END);
END $fn$;

COMMENT ON FUNCTION app_private.workflow_gate_state(uuid, text) IS
  'The worker''s one read at a gate, for a step it holds: the approval, whether a '
  'time wait was served, and -- since 0036 -- whether an event wait was served '
  'and with what payload (ADR 0230, ADR 0233, ADR 0239).';

CREATE OR REPLACE FUNCTION app_private.workflow_counts()
  RETURNS jsonb
  LANGUAGE plpgsql
  STABLE
  SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
  worker app_private.workflow_worker;
BEGIN
  SELECT * INTO worker FROM app_private.workflow_worker WHERE singleton;

  RETURN jsonb_build_object(
    'definitions', (SELECT count(*) FROM app_private.workflow_definition),
    'runs', coalesce(
      (SELECT jsonb_object_agg(status, total)
         FROM (SELECT status::text AS status, count(*) AS total
                 FROM app_private.workflow_run GROUP BY status) counted),
      '{}'::jsonb),
    'steps', coalesce(
      (SELECT jsonb_object_agg(status, total)
         FROM (SELECT status::text AS status, count(*) AS total
                 FROM app_private.workflow_step GROUP BY status) counted),
      '{}'::jsonb),
    'oldest_claimed_lease_age_seconds',
      (SELECT floor(extract(epoch FROM pg_catalog.now() - min(s.lease_until)))::bigint
         FROM app_private.workflow_step s
        WHERE s.status = 'claimed' AND s.lease_until < pg_catalog.now()),
    'heartbeat_age_seconds',
      CASE WHEN worker.seen_at IS NULL THEN NULL
           ELSE floor(extract(epoch FROM pg_catalog.now() - worker.seen_at))::bigint
      END,
    'heartbeat_holder', worker.holder,
    'approvals_pending',
      (SELECT count(*)
         FROM app_private.workflow_approval a
         JOIN app_private.workflow_run r ON r.id = a.run_id
        WHERE a.status = 'pending'
          AND a.expires_at > pg_catalog.now()
          AND r.status = 'running'),
    'oldest_pending_approval_age_seconds',
      (SELECT floor(extract(epoch FROM pg_catalog.now() - min(a.requested_at)))::bigint
         FROM app_private.workflow_approval a
         JOIN app_private.workflow_run r ON r.id = a.run_id
        WHERE a.status = 'pending'
          AND a.expires_at > pg_catalog.now()
          AND r.status = 'running'),
    'deliveries_pending',
      (SELECT count(*) FROM app_private.connector_delivery d WHERE d.status = 'pending'),
    'deliveries_dead',
      (SELECT count(*) FROM app_private.connector_delivery d WHERE d.status = 'dead'),
    'oldest_pending_delivery_age_seconds',
      (SELECT floor(extract(epoch FROM pg_catalog.now() - min(d.created_at)))::bigint
         FROM app_private.connector_delivery d
        WHERE d.status = 'pending'),
    'connectors_enabled',
      (SELECT count(*) FROM app_private.connector c WHERE c.enabled)
  );
END $fn$;

COMMENT ON FUNCTION app_private.workflow_counts() IS
  'Runs and steps by status, the oldest OVERDUE lease''s age, the heartbeat''s '
  'age and holder, the approvals a human could decide now, and -- since 0036 -- '
  'deliveries pending and dead, the oldest pending one''s age and the connectors '
  'enabled. Numbers and NO verdict (D1441). Carries no URL, key, token or '
  'caller value.';

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------
--
-- REVOKE first on every new function, then the grants to `auth_service`.
-- Granted to NOBODY: the emitter (only an owner-run function may call it), the
-- installer and the rehearsal (the deploy and the rehearsal run them as the
-- bootstrap superuser), and the scope rule (only these functions call it).
-- 0035's grants on the two replaced functions stand, their signatures unmoved.
REVOKE ALL ON FUNCTION app.emit_event(text, integer, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_scopes_match(uuid, text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_install(
  text, integer, app_private.connector_kind, jsonb, text, text, text, text, integer, text[],
  integer, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_claim_delivery(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  app_private.connector_finish_delivery(uuid, text, boolean, integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_fire_due() FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_inbound(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_accept(text, uuid, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_enable(text, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_disable(text, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_status(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_private.connector_rehearse_delivery(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  app_private.workflow_await_event(uuid, text, text, jsonb, timestamptz) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_private.connector_claim_delivery(text, integer) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.connector_finish_delivery(uuid, text, boolean, integer, text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.connector_fire_due() TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.connector_inbound(text) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.connector_accept(text, uuid, jsonb) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.connector_enable(text, uuid, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.connector_disable(text, uuid) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app_private.connector_status(integer) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION
  app_private.workflow_await_event(uuid, text, text, jsonb, timestamptz) TO {{auth_service}};

RESET ROLE;

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

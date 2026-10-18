-- migrate:up
-- Session 42 (ADR 0278, ADR 0279; D2569-D2572): Query Insights, DB time and
-- monitoring, all from samples the reconciler writes here -- the control plane
-- reaches no project database and no telemetry store (ADR 0246).
SET LOCAL ROLE {{object_owner}};

-- ---------------------------------------------------------------------------
-- Insight samples (ADR 0278)
-- ---------------------------------------------------------------------------

-- One row per statement per sample: the extension's counters AS READ (D553 --
-- a cumulative counter answers no point-in-time question; the document below
-- computes increases), for the project's customer-facing roles only, the text
-- the extension normalised, cut to 2000 characters. Kept 7 days: the writer
-- deletes older rows in its own transaction.
CREATE TABLE app.control_insight_samples (
  project_key      text NOT NULL REFERENCES app.control_projects(key),
  observed_at      timestamptz NOT NULL,
  queryid          bigint NOT NULL,
  role             text NOT NULL CHECK (role ~ '^[a-z_][a-z0-9_]{0,62}$'),
  calls            bigint NOT NULL CHECK (calls >= 0),
  total_exec_ms    double precision NOT NULL CHECK (total_exec_ms >= 0),
  rows             bigint NOT NULL CHECK (rows >= 0),
  shared_blks_hit  bigint NOT NULL CHECK (shared_blks_hit >= 0),
  shared_blks_read bigint NOT NULL CHECK (shared_blks_read >= 0),
  query            varchar(2000) NOT NULL,
  stats_reset      timestamptz NULL,
  PRIMARY KEY (project_key, observed_at, queryid, role)
);
ALTER TABLE app.control_insight_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.control_insight_samples FORCE ROW LEVEL SECURITY;
CREATE POLICY control_insight_samples_read ON app.control_insight_samples
  FOR SELECT TO {{object_owner}}
  USING (project_key IN (SELECT p.key FROM app.control_projects p));

-- ---------------------------------------------------------------------------
-- DB time on the usage samples (ADR 0275 as amended by ADR 0278, D2570)
-- ---------------------------------------------------------------------------

-- The customer-facing roles' summed total_exec_time AS READ, and the
-- extension's stats_reset beside it, so a reset is read rather than subtracted.
ALTER TABLE app.control_usage_samples
  ADD COLUMN db_time_ms       double precision NULL CHECK (db_time_ms >= 0),
  ADD COLUMN statements_reset timestamptz NULL;
ALTER TABLE app.control_usage_samples DROP CONSTRAINT control_usage_samples_unread_check;
ALTER TABLE app.control_usage_samples ADD CONSTRAINT control_usage_samples_unread_check
  CHECK (unread <@ ARRAY[
    'database_bytes', 'repository_bytes', 'branch_count', 'branch_bytes',
    'customer_connections', 'requests_counter', 'agent_calls', 'workflow_runs',
    'last_customer_activity', 'db_time_ms'
  ]::text[]);

-- 0008's writer, the two keys added (a test diffs the bodies).
CREATE OR REPLACE FUNCTION app.control_record_usage(p_samples jsonb) RETURNS integer
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_count integer;
BEGIN
  IF jsonb_typeof(p_samples) IS DISTINCT FROM 'array' OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(p_samples) AS s
     WHERE jsonb_typeof(s) <> 'object'
        OR NOT (s ? 'project_key' AND s ? 'state')
        OR EXISTS (
          SELECT 1 FROM jsonb_object_keys(s) AS k WHERE k NOT IN (
            'project_key', 'state', 'database_bytes', 'repository_bytes', 'branch_count',
            'branch_bytes', 'customer_connections', 'requests_counter', 'agent_calls',
            'workflow_runs', 'last_customer_activity', 'unread', 'reason',
            'db_time_ms', 'statements_reset'
          )
        )
        OR (s ? 'unread' AND jsonb_typeof(s -> 'unread') <> 'array')
  ) THEN
    RAISE EXCEPTION 'AP422: invalid_samples';
  END IF;
  INSERT INTO app.control_usage_samples (
    project_key, observed_at, state, database_bytes, repository_bytes, branch_count,
    branch_bytes, customer_connections, requests_counter, agent_calls, workflow_runs,
    last_customer_activity, unread, reason,
    db_time_ms, statements_reset
  )
  SELECT s ->> 'project_key', now(), s ->> 'state',
         (s ->> 'database_bytes')::bigint, (s ->> 'repository_bytes')::bigint,
         (s ->> 'branch_count')::integer, (s ->> 'branch_bytes')::bigint,
         (s ->> 'customer_connections')::integer, (s ->> 'requests_counter')::bigint,
         (s ->> 'agent_calls')::integer, (s ->> 'workflow_runs')::integer,
         (s ->> 'last_customer_activity')::timestamptz,
         coalesce(ARRAY(SELECT jsonb_array_elements_text(s -> 'unread')), '{}'::text[]),
         s ->> 'reason',
         (s ->> 'db_time_ms')::double precision, (s ->> 'statements_reset')::timestamptz
    FROM jsonb_array_elements(p_samples) AS s;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;
COMMENT ON FUNCTION app.control_record_usage(jsonb) IS
  'Records one usage sample per project, with now() as its instant (ADR 0275, ADR 0278): [{project_key, state, <figures>, db_time_ms, statements_reset, last_customer_activity, unread, reason}]; a figure not read is null and named in unread. Granted to nobody.';

-- ---------------------------------------------------------------------------
-- The reconciler's insight writer (granted to nobody; reached as root)
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_record_insights(p_sample jsonb) RETURNS integer
  LANGUAGE plpgsql SECURITY INVOKER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_count integer;
  v_key text := p_sample ->> 'project_key';
BEGIN
  IF jsonb_typeof(p_sample) IS DISTINCT FROM 'object'
     OR v_key IS NULL
     OR jsonb_typeof(p_sample -> 'statements') IS DISTINCT FROM 'array'
     OR EXISTS (
       SELECT 1 FROM jsonb_object_keys(p_sample) AS k
        WHERE k NOT IN ('project_key', 'stats_reset', 'statements'))
     OR EXISTS (
       SELECT 1 FROM jsonb_array_elements(p_sample -> 'statements') AS s
        WHERE jsonb_typeof(s) <> 'object'
           OR NOT (s ? 'queryid' AND s ? 'role' AND s ? 'calls' AND s ? 'total_exec_ms'
                   AND s ? 'rows' AND s ? 'shared_blks_hit' AND s ? 'shared_blks_read'
                   AND s ? 'query')
           OR EXISTS (
             SELECT 1 FROM jsonb_object_keys(s) AS k WHERE k NOT IN (
               'queryid', 'role', 'calls', 'total_exec_ms', 'rows', 'shared_blks_hit',
               'shared_blks_read', 'query')))
     OR jsonb_array_length(p_sample -> 'statements') > 50
  THEN
    RAISE EXCEPTION 'AP422: invalid_samples';
  END IF;
  INSERT INTO app.control_insight_samples (
    project_key, observed_at, queryid, role, calls, total_exec_ms, rows,
    shared_blks_hit, shared_blks_read, query, stats_reset
  )
  SELECT v_key, now(), (s ->> 'queryid')::bigint, s ->> 'role', (s ->> 'calls')::bigint,
         (s ->> 'total_exec_ms')::double precision, (s ->> 'rows')::bigint,
         (s ->> 'shared_blks_hit')::bigint, (s ->> 'shared_blks_read')::bigint,
         left(s ->> 'query', 2000), (p_sample ->> 'stats_reset')::timestamptz
    FROM jsonb_array_elements(p_sample -> 'statements') AS s;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  -- INSIGHT_KEEP_DAYS (ADR 0278): 7.
  DELETE FROM app.control_insight_samples
   WHERE project_key = v_key AND observed_at < now() - interval '7 days';
  RETURN v_count;
END;
$$;
COMMENT ON FUNCTION app.control_record_insights(jsonb) IS
  'Records one project''s insight sample with now() as its instant (ADR 0278): {project_key, stats_reset, statements: [at most 50 of {queryid, role, calls, total_exec_ms, rows, shared_blks_hit, shared_blks_read, query}]}, the text cut to 2000; deletes the key''s samples older than 7 days. Granted to nobody.';

-- ---------------------------------------------------------------------------
-- The usage document, DB time added (0008's body plus one marked block)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.control_usage_document(p_key text, p_from timestamptz, p_to timestamptz)
  RETURNS jsonb
  LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_figures jsonb := '{}'::jsonb;
  v_figure text;
  v_one jsonb;
  v_present integer;
  v_requests bigint := 0;
  v_resets integer := 0;
  v_previous bigint;
  v_row record;
  v_state text := 'absent';
  v_at timestamptz;
  v_active numeric := 0;
  v_sleeping numeric := 0;
  v_event record;
  v_project app.control_projects%ROWTYPE;
  v_db_ms double precision := 0;
  v_db_resets integer := 0;
  v_db_previous double precision;
  v_db_previous_reset timestamptz;
  v_db_read boolean := false;
BEGIN
  SELECT count(*) INTO v_present FROM app.control_usage_samples
   WHERE project_key = p_key AND observed_at > p_from AND observed_at <= p_to;
  -- The gauges: the newest figure READ, when, the window's maximum, and how
  -- many samples could not read it.
  FOREACH v_figure IN ARRAY ARRAY[
    'database_bytes', 'repository_bytes', 'branch_count', 'branch_bytes', 'customer_connections'
  ] LOOP
    EXECUTE format(
      'SELECT jsonb_build_object('
      '  ''latest'', (SELECT %1$I FROM app.control_usage_samples WHERE project_key = $1'
      '     AND observed_at > $2 AND observed_at <= $3 AND %1$I IS NOT NULL'
      '     ORDER BY observed_at DESC LIMIT 1),'
      '  ''latest_at'', (SELECT observed_at FROM app.control_usage_samples WHERE project_key = $1'
      '     AND observed_at > $2 AND observed_at <= $3 AND %1$I IS NOT NULL'
      '     ORDER BY observed_at DESC LIMIT 1),'
      '  ''max'', (SELECT max(%1$I) FROM app.control_usage_samples WHERE project_key = $1'
      '     AND observed_at > $2 AND observed_at <= $3),'
      '  ''unread_samples'', (SELECT count(*) FROM app.control_usage_samples WHERE project_key = $1'
      '     AND observed_at > $2 AND observed_at <= $3 AND %1$I IS NULL))',
      v_figure
    ) INTO v_one USING p_key, p_from, p_to;
    v_figures := v_figures || jsonb_build_object(v_figure, v_one);
  END LOOP;
  -- The counter: increases between consecutive READ samples; a decrease is a
  -- reset, counted from zero (D553).
  FOR v_row IN
    SELECT requests_counter AS value FROM app.control_usage_samples
     WHERE project_key = p_key AND observed_at > p_from AND observed_at <= p_to
       AND requests_counter IS NOT NULL
     ORDER BY observed_at
  LOOP
    IF v_previous IS NOT NULL THEN
      IF v_row.value >= v_previous THEN
        v_requests := v_requests + (v_row.value - v_previous);
      ELSE
        v_resets := v_resets + 1;
        v_requests := v_requests + v_row.value;
      END IF;
    END IF;
    v_previous := v_row.value;
  END LOOP;
  -- Session 42 (ADR 0278, D2570): DB time, the same reading as the counter --
  -- increases between consecutive READ samples; a decrease OR a moved
  -- statements_reset is a reset, counted from zero.
  FOR v_row IN
    SELECT db_time_ms AS value, statements_reset AS reset FROM app.control_usage_samples
     WHERE project_key = p_key AND observed_at > p_from AND observed_at <= p_to
       AND db_time_ms IS NOT NULL
     ORDER BY observed_at
  LOOP
    IF v_db_read THEN
      IF v_row.value >= v_db_previous AND v_row.reset IS NOT DISTINCT FROM v_db_previous_reset THEN
        v_db_ms := v_db_ms + (v_row.value - v_db_previous);
      ELSE
        v_db_resets := v_db_resets + 1;
        v_db_ms := v_db_ms + v_row.value;
      END IF;
    END IF;
    v_db_read := true;
    v_db_previous := v_row.value;
    v_db_previous_reset := v_row.reset;
  END LOOP;
  -- Active and sleeping seconds, from the operation history (never sampled).
  SELECT * INTO v_project FROM app.control_projects WHERE key = p_key;
  IF FOUND THEN
    v_state := 'active';
    v_at := v_project.adopted_at;
    FOR v_event IN
      SELECT o.type, o.finished_at FROM app.control_operations o
       WHERE o.project_key = p_key AND o.status = 'succeeded'
         AND o.type IN ('project.sleep', 'project.wake', 'project.delete')
       ORDER BY o.finished_at
    LOOP
      IF v_event.finished_at > v_at THEN
        IF v_state = 'active' THEN
          v_active := v_active + greatest(0, extract(epoch FROM
            least(v_event.finished_at, p_to) - greatest(v_at, p_from)));
        ELSIF v_state = 'sleeping' THEN
          v_sleeping := v_sleeping + greatest(0, extract(epoch FROM
            least(v_event.finished_at, p_to) - greatest(v_at, p_from)));
        END IF;
        v_at := v_event.finished_at;
      END IF;
      v_state := CASE v_event.type
        WHEN 'project.sleep' THEN 'sleeping' WHEN 'project.wake' THEN 'active' ELSE 'absent' END;
    END LOOP;
    IF v_state = 'active' AND v_project.deleted_at IS NULL THEN
      v_active := v_active + greatest(0, extract(epoch FROM p_to - greatest(v_at, p_from)));
    ELSIF v_state = 'sleeping' AND v_project.deleted_at IS NULL THEN
      v_sleeping := v_sleeping + greatest(0, extract(epoch FROM p_to - greatest(v_at, p_from)));
    END IF;
  END IF;
  RETURN jsonb_build_object(
    'project_key', p_key,
    'window', jsonb_build_object('from', p_from, 'to', p_to),
    'samples', jsonb_build_object(
      'expected', floor(extract(epoch FROM p_to - p_from) / 300)::integer,
      'present', v_present),
    'figures', v_figures,
    'requests', CASE WHEN v_previous IS NULL THEN NULL
                     ELSE jsonb_build_object('increase', v_requests, 'resets', v_resets) END,
    'db_time', CASE WHEN NOT v_db_read THEN NULL
                    ELSE jsonb_build_object('increase_ms', round(v_db_ms::numeric, 3),
                                            'resets', v_db_resets) END,
    'agent_calls', (SELECT sum(agent_calls) FROM app.control_usage_samples
                     WHERE project_key = p_key AND observed_at > p_from AND observed_at <= p_to),
    'workflow_runs', (SELECT sum(workflow_runs) FROM app.control_usage_samples
                       WHERE project_key = p_key AND observed_at > p_from AND observed_at <= p_to),
    'active_seconds', round(v_active),
    'sleeping_seconds', round(v_sleeping)
  );
END;
$$;
COMMENT ON FUNCTION app.control_usage_document(text, timestamptz, timestamptz) IS
  'One project''s usage over a window: samples expected and present, each gauge''s latest read value, maximum and unread count, the request counter''s and DB time''s increases with resets read, agent calls and workflow runs summed, active and sleeping seconds from the history (ADR 0275, ADR 0278). Called by the definer readers; granted to nobody.';

-- ---------------------------------------------------------------------------
-- Query Insights (ADR 0278, D2571): numbers, never advice
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_project_insights(p_user uuid, p_key text, p_hours integer, p_limit integer)
  RETURNS jsonb
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_from timestamptz;
  v_to timestamptz := now();
  v_present integer;
  v_resets integer;
  v_statements jsonb;
  v_tuning text := 'To change a query plan, write a migration in your project''s set and run apg migrate propose (docs/change-governance.md, Proposing).';
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'viewer');
  IF p_hours IS NULL OR p_hours < 1 OR p_hours > 168 OR p_limit IS NULL OR p_limit < 1 OR p_limit > 50 THEN
    RAISE EXCEPTION 'AP422: invalid_request';
  END IF;
  v_from := v_to - make_interval(hours => p_hours);
  SELECT count(DISTINCT observed_at) INTO v_present FROM app.control_insight_samples
   WHERE project_key = p_key AND observed_at > v_from AND observed_at <= v_to;
  IF v_present < 2 THEN
    RETURN jsonb_build_object(
      'project_key', p_key,
      'status', 'could_not_determine',
      'reason', CASE WHEN v_present = 0 THEN 'no insight sample was recorded in the window'
                     ELSE 'one sample cannot show an increase; the window needs two' END,
      'window', jsonb_build_object('from', v_from, 'to', v_to),
      'samples', jsonb_build_object('expected', floor(p_hours * 3600 / 300)::integer,
                                    'present', v_present),
      'statements', NULL,
      'tuning', v_tuning);
  END IF;
  -- A reset: the extension's stats_reset moved between two consecutive samples.
  SELECT count(*) INTO v_resets FROM (
    SELECT t.stats_reset, lag(t.stats_reset) OVER (ORDER BY t.observed_at) AS previous,
           row_number() OVER (ORDER BY t.observed_at) AS n
      FROM (SELECT DISTINCT observed_at, stats_reset FROM app.control_insight_samples
             WHERE project_key = p_key AND observed_at > v_from AND observed_at <= v_to) t
  ) x WHERE x.n > 1 AND x.stats_reset IS DISTINCT FROM x.previous;
  -- Per statement and role: the increase between consecutive samples that hold
  -- it; a statement's first sample in the window counts nothing; a decrease or
  -- a moved stats_reset is a reset, counted from zero (D553).
  WITH d AS (
    SELECT s.*, row_number() OVER w AS n,
           lag(s.calls) OVER w AS p_calls, lag(s.total_exec_ms) OVER w AS p_ms,
           lag(s.rows) OVER w AS p_rows, lag(s.shared_blks_hit) OVER w AS p_hit,
           lag(s.shared_blks_read) OVER w AS p_read, lag(s.stats_reset) OVER w AS p_reset
      FROM app.control_insight_samples s
     WHERE s.project_key = p_key AND s.observed_at > v_from AND s.observed_at <= v_to
    WINDOW w AS (PARTITION BY s.queryid, s.role ORDER BY s.observed_at)
  ), i AS (
    SELECT d.queryid, d.role, d.query, d.observed_at,
           (d.n > 1 AND (d.calls < d.p_calls OR d.stats_reset IS DISTINCT FROM d.p_reset)) AS reset,
           d.n, d.calls, d.p_calls, d.total_exec_ms, d.p_ms, d.rows, d.p_rows,
           d.shared_blks_hit, d.p_hit, d.shared_blks_read, d.p_read
      FROM d
  ), c AS (
    SELECT i.queryid, i.role, i.query, i.observed_at,
           CASE WHEN i.n = 1 THEN 0 WHEN i.reset THEN i.calls ELSE i.calls - i.p_calls END AS calls,
           CASE WHEN i.n = 1 THEN 0 WHEN i.reset THEN i.total_exec_ms
                ELSE greatest(i.total_exec_ms - i.p_ms, 0) END AS total_ms,
           CASE WHEN i.n = 1 THEN 0 WHEN i.reset THEN i.rows
                ELSE greatest(i.rows - i.p_rows, 0) END AS rows,
           CASE WHEN i.n = 1 THEN 0 WHEN i.reset THEN i.shared_blks_hit
                ELSE greatest(i.shared_blks_hit - i.p_hit, 0) END AS hit,
           CASE WHEN i.n = 1 THEN 0 WHEN i.reset THEN i.shared_blks_read
                ELSE greatest(i.shared_blks_read - i.p_read, 0) END AS rd
      FROM i
  ), a AS (
    SELECT c.queryid, c.role, (array_agg(c.query ORDER BY c.observed_at DESC))[1] AS query,
           sum(c.calls) AS calls, sum(c.total_ms) AS total_ms, sum(c.rows) AS rows,
           sum(c.hit) AS hit, sum(c.rd) AS rd
      FROM c GROUP BY c.queryid, c.role
  ), top AS (
    SELECT * FROM a WHERE a.calls > 0 ORDER BY a.total_ms DESC, a.queryid LIMIT p_limit
  )
  SELECT coalesce(jsonb_agg(jsonb_build_object(
           'query', top.query,
           'role', top.role,
           'calls', top.calls,
           'total_ms', round(top.total_ms::numeric, 3),
           'mean_ms', round((top.total_ms / top.calls)::numeric, 3),
           'rows', top.rows,
           'rows_per_call', round(top.rows::numeric / top.calls, 3),
           'shared_blks_read_per_call', round(top.rd::numeric / top.calls, 3),
           'cache_hit_ratio', CASE WHEN top.hit + top.rd = 0 THEN NULL
                                   ELSE round(top.hit::numeric / (top.hit + top.rd), 4) END
         ) ORDER BY top.total_ms DESC, top.queryid), '[]'::jsonb)
    INTO v_statements FROM top;
  RETURN jsonb_build_object(
    'project_key', p_key,
    'status', 'read',
    'reason', NULL,
    'window', jsonb_build_object('from', v_from, 'to', v_to),
    'samples', jsonb_build_object('expected', floor(p_hours * 3600 / 300)::integer,
                                  'present', v_present),
    'resets', v_resets,
    'statements', v_statements,
    'tuning', v_tuning);
END;
$$;
COMMENT ON FUNCTION app.control_project_insights(uuid, text, integer, integer) IS
  'A live project''s statements over the last 1..168 hours, at most 1..50, viewer and above: per statement and role the increase of calls, time, rows and block reads, its mean, its rows per call, its reads per call and its cache hit ratio, ordered by time; the window, samples expected and present, resets; a fixed tuning sentence; never a finding, a recommendation, a confidence or a severity; fewer than two samples is could_not_determine with the reason (ADR 0278). A foreign and a missing project are the one not_found.';

-- ---------------------------------------------------------------------------
-- Monitoring (ADR 0279): each signal from the table it names, nothing new
-- ---------------------------------------------------------------------------

CREATE FUNCTION app.control_project_monitoring(p_user uuid, p_key text)
  RETURNS jsonb
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_sample app.control_usage_samples%ROWTYPE;
  v_backup app.control_backup_readings%ROWTYPE;
  v_hour jsonb;
  v_signals jsonb := '{}'::jsonb;
  v_figure text;
  v_value jsonb;
  v_at timestamptz;
  v_insights timestamptz;
BEGIN
  PERFORM app.control_enter(p_user);
  PERFORM app.control_require_role(app.control_project_organization(p_key), 'viewer');
  -- state: the newest usage sample's state.
  SELECT * INTO v_sample FROM app.control_usage_samples
   WHERE project_key = p_key ORDER BY observed_at DESC LIMIT 1;
  v_signals := v_signals || jsonb_build_object('state', CASE WHEN v_sample.project_key IS NULL
    THEN jsonb_build_object('value', NULL, 'observed_at', NULL, 'unread', 'no usage sample has been recorded')
    ELSE jsonb_build_object('value', v_sample.state, 'observed_at', v_sample.observed_at) END);
  -- The three gauges: the newest sample that READ each.
  FOREACH v_figure IN ARRAY ARRAY['database_bytes', 'repository_bytes', 'customer_connections'] LOOP
    EXECUTE format(
      'SELECT to_jsonb(%1$I), observed_at FROM app.control_usage_samples'
      ' WHERE project_key = $1 AND %1$I IS NOT NULL ORDER BY observed_at DESC LIMIT 1',
      v_figure
    ) INTO v_value, v_at USING p_key;
    v_signals := v_signals || jsonb_build_object(v_figure, CASE WHEN v_at IS NULL
      THEN jsonb_build_object('value', NULL, 'observed_at', NULL, 'unread', 'no usage sample read it')
      ELSE jsonb_build_object('value', v_value, 'observed_at', v_at) END);
  END LOOP;
  -- The last hour's requests and DB time: the usage document's own increases.
  v_hour := app.control_usage_document(p_key, now() - interval '1 hour', now());
  v_signals := v_signals || jsonb_build_object(
    'requests_last_hour', CASE WHEN v_hour -> 'requests' = 'null'::jsonb
      THEN jsonb_build_object('value', NULL, 'observed_at', NULL, 'unread', 'no sample in the last hour read the request counter')
      ELSE jsonb_build_object('value', v_hour -> 'requests' -> 'increase', 'observed_at', now()) END,
    'db_time_last_hour', CASE WHEN v_hour -> 'db_time' = 'null'::jsonb
      THEN jsonb_build_object('value', NULL, 'observed_at', NULL, 'unread', 'no sample in the last hour read DB time')
      ELSE jsonb_build_object('value', v_hour -> 'db_time' -> 'increase_ms', 'observed_at', now()) END);
  -- The backups reading (ADR 0273).
  SELECT * INTO v_backup FROM app.control_backup_readings WHERE project_key = p_key;
  IF v_backup.project_key IS NULL THEN
    v_signals := v_signals || jsonb_build_object(
      'backup_status', jsonb_build_object('value', NULL, 'observed_at', NULL, 'unread', 'no backups reading has been recorded'),
      'latest_recoverable_time', jsonb_build_object('value', NULL, 'observed_at', NULL, 'unread', 'no backups reading has been recorded'),
      'last_full_backup_at', jsonb_build_object('value', NULL, 'observed_at', NULL, 'unread', 'no backups reading has been recorded'));
  ELSE
    v_signals := v_signals || jsonb_build_object(
      'backup_status', jsonb_build_object('value', v_backup.repository_status, 'observed_at', v_backup.observed_at),
      'latest_recoverable_time', jsonb_build_object('value', v_backup.latest, 'observed_at', v_backup.observed_at),
      'last_full_backup_at', jsonb_build_object('value', v_backup.last_full_at, 'observed_at', v_backup.observed_at));
  END IF;
  -- When insights were last sampled.
  SELECT max(observed_at) INTO v_insights FROM app.control_insight_samples WHERE project_key = p_key;
  v_signals := v_signals || jsonb_build_object('insights_sampled_at', CASE WHEN v_insights IS NULL
    THEN jsonb_build_object('value', NULL, 'observed_at', NULL, 'unread', 'no insight sample has been recorded')
    ELSE jsonb_build_object('value', v_insights, 'observed_at', v_insights) END);
  RETURN jsonb_build_object('project_key', p_key, 'read_at', now(), 'signals', v_signals);
END;
$$;
COMMENT ON FUNCTION app.control_project_monitoring(uuid, text) IS
  'A live project''s signals, viewer and above, each from the table services/auth-api/app/signals.py names for it -- the newest usage sample, the last hour''s usage document, the backups reading, the newest insight sample -- with its observed_at, or unread with the reason; nothing read anywhere else (ADR 0279). A foreign and a missing project are the one not_found.';

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION app.control_record_usage(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_record_insights(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_usage_document(text, timestamptz, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_project_insights(uuid, text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.control_project_monitoring(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.control_project_insights(uuid, text, integer, integer) TO {{auth_service}};
GRANT EXECUTE ON FUNCTION app.control_project_monitoring(uuid, text) TO {{auth_service}};

-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: project migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;

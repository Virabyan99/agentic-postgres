"""What the locked PostgREST does, measured against a real cluster.

Everything ADR 0057 and ADR 0058 decide is a property of this image, not of this
repository, so none of it can be read out of documentation. Each test below is a
fact the migrations were written from:

- which SQLSTATE becomes which HTTP status, and that `HINT` and `DETAIL` reach
  the caller verbatim (ADR 0057);
- that an enum column publishes its values and a CHECK constraint publishes
  nothing (ADR 0058);
- that `openapi-mode = follow-privileges` follows a **PUBLIC** grant, so a
  function left with PostgreSQL's default EXECUTE is advertised to an anonymous
  caller;
- that `db-pre-request` runs after the role switch, inside the request
  transaction, which is read-only on a GET;
- and that an unresolvable hook neither fails open nor stops the service: it
  starts, warms its schema cache, and 404s every request (D139).

The schema here is deliberately small and is **not** the released migration set.
These are questions about the image; applying the real migrations would measure
this repository's SQL against the same image and answer a different question, in
a suite that runs without a deployment. `tests/deployment/` is where the real
surface is proved.

The JWT secret is symmetric and lives in this file. It is a throwaway for a
container that exists for the duration of one module and publishes on an
ephemeral loopback port; the product's issuer is asymmetric and its private half
never reaches a service (ADR 0051).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_image_contracts import LOCK, requires_docker

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.database]

#: Long enough for PostgREST to accept it. Not a credential: see the module note.
PROBE_JWT_SECRET = "a-measurement-only-symmetric-secret-of-at-least-32-bytes"  # noqa: S105

OWNER_A = "11111111-1111-4111-8111-111111111111"
OWNER_B = "22222222-2222-4222-8222-222222222222"

#: One probe function per candidate mechanism, so a status is attributed to the
#: thing that produced it rather than to a function that does several things.
PROBE_SCHEMA = """
CREATE ROLE probe_owner NOLOGIN NOINHERIT;
CREATE ROLE probe_anon NOLOGIN NOINHERIT;
CREATE ROLE probe_web NOLOGIN NOINHERIT;
CREATE ROLE probe_unreachable NOLOGIN NOINHERIT;
CREATE ROLE probe_auth LOGIN NOINHERIT PASSWORD 'probe-authenticator';
GRANT probe_anon TO probe_auth WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
GRANT probe_web  TO probe_auth WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

CREATE SCHEMA api AUTHORIZATION probe_owner;
CREATE SCHEMA app AUTHORIZATION probe_owner;
CREATE SCHEMA app_private AUTHORIZATION probe_owner;
SET ROLE probe_owner;

CREATE FUNCTION app.claimed_owner() RETURNS uuid
  LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp
AS $$ SELECT nullif(current_setting('app.user_id', true), '')::uuid; $$;

CREATE TYPE api.probe_status AS ENUM ('pending', 'in_progress', 'completed', 'cancelled');

CREATE TABLE app.rows (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id uuid NOT NULL,
  title text NOT NULL,
  as_enum api.probe_status NOT NULL DEFAULT 'pending',
  as_checked_text text NOT NULL DEFAULT 'pending'
    CHECK (as_checked_text IN ('pending', 'in_progress', 'completed', 'cancelled'))
);
ALTER TABLE app.rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.rows FORCE ROW LEVEL SECURITY;
CREATE POLICY p_sel ON app.rows FOR SELECT USING (owner_id = app.claimed_owner());
CREATE POLICY p_ins ON app.rows FOR INSERT WITH CHECK (owner_id = app.claimed_owner());

CREATE VIEW api.rows WITH (security_invoker = true, security_barrier = true) AS
  SELECT id, owner_id, title, as_enum, as_checked_text FROM app.rows;

CREATE FUNCTION api.e_default() RETURNS void LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp AS $$
BEGIN RAISE EXCEPTION 'AP401: probe'
  USING HINT = 'HINTCANARY set app.user_id', DETAIL = 'DETAILCANARY app.rows policy'; END $$;

CREATE FUNCTION api.e_pt401() RETURNS void LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp AS $$
BEGIN RAISE EXCEPTION 'AP401: probe' USING ERRCODE = 'PT401'; END $$;

CREATE FUNCTION api.e_pt404() RETURNS void LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp AS $$
BEGIN RAISE EXCEPTION 'AP404: probe' USING ERRCODE = 'PT404'; END $$;

CREATE FUNCTION api.e_pt409() RETURNS void LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp AS $$
BEGIN RAISE EXCEPTION 'AP409: probe' USING ERRCODE = 'PT409'; END $$;

CREATE FUNCTION api.e_pt422() RETURNS void LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp AS $$
BEGIN RAISE EXCEPTION 'AP422: probe' USING ERRCODE = 'PT422'; END $$;

-- Session 16 Run 6. `PT412` is the idempotency-key conflict, and it exists as a
-- fifth code because ONE errcode cannot carry two sentences: `PT409` is already
-- the compare-and-swap conflict, and "re-read and retry" is precisely the wrong
-- advice for a key already bound to different arguments. The probe is here
-- rather than in a throwaway rig because rig4 measured `PTxxx -> xxx` over four
-- codes, and a fifth is an EXTENSION of that rule rather than an instance of it
-- -- an extension nobody exercised is an assumption.
CREATE FUNCTION api.e_pt412() RETURNS void LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp AS $$
BEGIN RAISE EXCEPTION 'AP412: probe' USING ERRCODE = 'PT412'; END $$;

CREATE FUNCTION api.e_28000() RETURNS void LANGUAGE plpgsql
  SET search_path = pg_catalog, pg_temp AS $$
BEGIN RAISE EXCEPTION 'AP401: probe' USING ERRCODE = '28000'; END $$;

-- Granted to nobody by name. PostgreSQL's default PUBLIC EXECUTE is the whole
-- point: whether it reaches the published document is the measurement.
CREATE FUNCTION api.left_public() RETURNS text LANGUAGE sql
  SET search_path = pg_catalog, pg_temp AS $$ SELECT 'reachable' $$;

CREATE FUNCTION api.revoked_from_public() RETURNS text LANGUAGE sql
  SET search_path = pg_catalog, pg_temp AS $$ SELECT 'granted by name' $$;

CREATE FUNCTION app_private.pre_request() RETURNS void
  LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $$
DECLARE raw text := nullif(current_setting('request.jwt.claims', true), '');
BEGIN
  RAISE LOG 'PREREQUEST current_user=% session_user=%', current_user, session_user;
  IF raw IS NULL THEN RETURN; END IF;
  IF (raw::jsonb ->> 'sub') IS NOT NULL THEN
    PERFORM pg_catalog.set_config('app.user_id', raw::jsonb ->> 'sub', true);
  END IF;
END $$;

CREATE TABLE app_private.hook_audit (at timestamptz DEFAULT clock_timestamp());

-- The working hook plus an audit row, which is exactly the shape the real
-- pre-request function started as. SECURITY DEFINER and no row policy on the
-- target, so nothing about *privilege* can stop the write; what stops it is the
-- only thing left.
CREATE FUNCTION app_private.writes_a_row() RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
DECLARE raw text := nullif(current_setting('request.jwt.claims', true), '');
BEGIN
  INSERT INTO app_private.hook_audit DEFAULT VALUES;
  IF raw IS NOT NULL AND (raw::jsonb ->> 'sub') IS NOT NULL THEN
    PERFORM pg_catalog.set_config('app.user_id', raw::jsonb ->> 'sub', true);
  END IF;
END $$;

RESET ROLE;
GRANT USAGE ON SCHEMA api TO probe_anon, probe_web;
GRANT SELECT, INSERT ON api.rows TO probe_web;
GRANT SELECT, INSERT ON app.rows TO probe_web;
REVOKE ALL ON FUNCTION api.revoked_from_public() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api.revoked_from_public() TO probe_web;
GRANT USAGE ON SCHEMA app_private TO probe_anon, probe_web;
GRANT EXECUTE ON FUNCTION app_private.pre_request() TO probe_anon, probe_web;
GRANT EXECUTE ON FUNCTION app_private.writes_a_row() TO probe_anon, probe_web;
GRANT INSERT ON app.rows TO probe_anon;
"""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def token(**claims: Any) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps(claims, separators=(",", ":")).encode())
    signature = hmac.new(
        PROBE_JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    return f"{header}.{payload}.{_b64(signature)}"


class ApiRig:
    """A cluster and a PostgREST in front of it, on a private network."""

    def __init__(self, network: str, database: str, work: Path) -> None:
        self.network = network
        self.database = database
        self.work = work
        self.service = ""
        self.port = 0

    def psql(self, statement: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "docker", "exec", "-i", self.database, "psql", "-U", "postgres",
                "-d", "postgres", "-X", "-v", "ON_ERROR_STOP=1", "-qtA", "-f", "-",
            ],
            input=statement, capture_output=True, text=True, check=False, timeout=180,
        )  # fmt: skip

    def start_service(self, *, pre_request: str | None) -> bool:
        """(Re)start PostgREST, returning whether it warmed a schema cache."""
        if self.service:
            subprocess.run(
                ["docker", "rm", "-f", self.service], capture_output=True, check=False, timeout=120
            )
        self.service = f"apg-api-probe-rest-{secrets.token_hex(4)}"
        command = [
            "docker", "run", "-d", "--name", self.service, "--network", self.network,
            "-p", "127.0.0.1:0:3000",
            "-e", "PGRST_DB_URI=postgres://probe_auth:probe-authenticator@postgres:5432/postgres",
            "-e", "PGRST_DB_SCHEMAS=api",
            "-e", "PGRST_DB_ANON_ROLE=probe_anon",
            "-e", "PGRST_DB_CONFIG=false",
            "-e", "PGRST_DB_EXTRA_SEARCH_PATH=",
            "-e", "PGRST_DB_HOISTED_TX_SETTINGS=",
            "-e", "PGRST_OPENAPI_MODE=follow-privileges",
            "-e", f"PGRST_JWT_SECRET={PROBE_JWT_SECRET}",
            "-e", "PGRST_SERVER_HOST=0.0.0.0",
            # Both, because D153 measured that `--ready` needs its own
            # configuration and refuses a wildcard `server-host` without an
            # explicit admin host of its own.
            "-e", "PGRST_ADMIN_SERVER_HOST=127.0.0.1",
            "-e", "PGRST_ADMIN_SERVER_PORT=3001",
        ]  # fmt: skip
        if pre_request is not None:
            command += ["-e", f"PGRST_DB_PRE_REQUEST={pre_request}"]
        command.append(LOCK["POSTGREST_IMAGE"])
        started = subprocess.run(command, capture_output=True, text=True, check=False, timeout=300)
        assert started.returncode == 0, started.stderr

        warm = False
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if "Schema cache loaded in" in self.logs():
                warm = True
                break
            time.sleep(1)

        mapping = subprocess.run(
            ["docker", "port", self.service, "3000"],
            capture_output=True, text=True, check=False, timeout=60,
        )  # fmt: skip
        if mapping.returncode == 0 and mapping.stdout.strip():
            self.port = int(mapping.stdout.strip().splitlines()[0].rsplit(":", 1)[-1])
        return warm

    def logs(self) -> str:
        result = subprocess.run(
            ["docker", "logs", self.service],
            capture_output=True, text=True, check=False, timeout=60,
        )  # fmt: skip
        return result.stdout + result.stderr

    def server_log(self) -> str:
        result = subprocess.run(
            ["docker", "logs", self.database],
            capture_output=True, text=True, check=False, timeout=60,
        )  # fmt: skip
        return result.stdout + result.stderr

    def call(
        self, method: str, path: str, *, bearer: str | None = None, body: Any = None
    ) -> tuple[int | None, dict[str, str], str]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method
        )
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if bearer is not None:
            request.add_header("Authorization", f"Bearer {bearer}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return response.status, dict(response.headers), response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read().decode()

    def status(self, method: str, path: str, **kwargs: Any) -> int | None:
        return self.call(method, path, **kwargs)[0]


@pytest.fixture(scope="module")
def api_rig(tmp_path_factory: pytest.TempPathFactory):
    suffix = secrets.token_hex(4)
    network = f"apg-api-probe-net-{suffix}"
    database = f"apg-api-probe-db-{suffix}"
    work = tmp_path_factory.mktemp("api-probe")

    server_env = work / "server.env"
    server_env.write_text(f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n", encoding="utf-8")
    server_env.chmod(0o600)

    created = subprocess.run(
        ["docker", "network", "create", network],
        capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert created.returncode == 0, created.stderr

    rig = ApiRig(network, database, work)
    started = subprocess.run(
        [
            "docker", "run", "-d", "--name", database,
            "--network", network, "--network-alias", "postgres",
            "--env-file", str(server_env),
            LOCK["POSTGRES_IMAGE"], "-c", "log_min_messages=log",
        ],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert started.returncode == 0, started.stderr

    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            ready = subprocess.run(
                ["docker", "exec", database, "pg_isready", "-q", "-U", "postgres"],
                capture_output=True,
                check=False,
                timeout=60,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("the probe cluster never became ready")
        time.sleep(2)

        applied = rig.psql(PROBE_SCHEMA)
        assert applied.returncode == 0, applied.stderr
        assert rig.start_service(pre_request="app_private.pre_request"), rig.logs()
        yield rig
    finally:
        if rig.service:
            subprocess.run(
                ["docker", "rm", "-f", rig.service], capture_output=True, check=False, timeout=120
            )
        subprocess.run(
            ["docker", "rm", "-f", database], capture_output=True, check=False, timeout=120
        )
        subprocess.run(
            ["docker", "network", "rm", network], capture_output=True, check=False, timeout=120
        )


# ---------------------------------------------------------------------------
# ADR 0057 — which SQLSTATE becomes which status
# ---------------------------------------------------------------------------


@requires_docker
def test_the_rig_serves_requests_at_all(api_rig: ApiRig) -> None:
    """The control. Without it every refusal below could mean a broken rig."""
    status, _, body = api_rig.call("GET", "/rows", bearer=token(role="probe_web", sub=OWNER_A))
    assert status == 200, body


@requires_docker
def test_a_bare_raise_is_a_bad_request(api_rig: ApiRig) -> None:
    """What Session 3 would have published.

    `RAISE EXCEPTION 'AP401: …'` leaves the SQLSTATE at `P0001`, and 400 tells a
    caller nothing about needing to authenticate and carries no challenge.
    """
    status, headers, body = api_rig.call(
        "POST", "/rpc/e_default", bearer=token(role="probe_web"), body={}
    )
    assert status == 400, body
    assert json.loads(body)["code"] == "P0001"
    assert "WWW-Authenticate" not in headers


@requires_docker
def test_a_hint_and_a_detail_reach_the_caller_verbatim(api_rig: ApiRig) -> None:
    """The measurement ADR 0057 turns on.

    Migration 0005 raised `AP401` with `HINT = 'SET LOCAL app.user_id before
    calling this function.'` -- written for a developer at a psql prompt, in a
    session where nothing served HTTP. Published, it is a public sentence naming
    an internal GUC in answer to an unauthenticated request.
    """
    _, _, body = api_rig.call("POST", "/rpc/e_default", bearer=token(role="probe_web"), body={})
    answered = json.loads(body)
    assert answered["hint"] == "HINTCANARY set app.user_id"
    assert answered["details"] == "DETAILCANARY app.rows policy"


@requires_docker
@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("e_pt401", 401),
        ("e_pt404", 404),
        ("e_pt409", 409),
        ("e_pt412", 412),
        ("e_pt422", 422),
    ],
)
def test_a_pt_sqlstate_carries_its_status(api_rig: ApiRig, probe: str, expected: int) -> None:
    status, _, body = api_rig.call("POST", f"/rpc/{probe}", bearer=token(role="probe_web"), body={})
    assert status == expected, body
    assert json.loads(body)["code"] == probe.removeprefix("e_").upper()


@requires_docker
def test_the_unauthorized_status_carries_a_challenge(api_rig: ApiRig) -> None:
    """An empty successful response is not a refusal, and neither is a 401 that
    does not say what to present. `SEC-ANON-001` asserts this header."""
    _, headers, _ = api_rig.call("POST", "/rpc/e_pt401", bearer=token(role="probe_web"), body={})
    assert headers.get("WWW-Authenticate", "").startswith("Bearer")


@requires_docker
def test_the_semantically_exact_sqlstate_is_the_wrong_status(api_rig: ApiRig) -> None:
    """`28000` is "invalid authorization specification" and answers **403**.

    Which says "authenticated and not permitted" to a caller that presented no
    identity at all, and carries no challenge. Semantics lost to the status code
    that actually ships, which is why ADR 0057 chose `PT401`.
    """
    status, headers, _ = api_rig.call(
        "POST", "/rpc/e_28000", bearer=token(role="probe_web"), body={}
    )
    assert status == 403
    assert "WWW-Authenticate" not in headers


# ---------------------------------------------------------------------------
# ADR 0058 — what the published document can carry
# ---------------------------------------------------------------------------


@requires_docker
def test_an_enum_publishes_its_values_and_a_check_constraint_publishes_nothing(
    api_rig: ApiRig,
) -> None:
    """One table, two spellings of the same bound, one document.

    Both bound the column in the database. Only one of them is visible to a
    client, to the reviewer comparing the snapshot, and to Session 8's
    capability catalog.
    """
    status, _, body = api_rig.call("GET", "/", bearer=token(role="probe_web"))
    assert status == 200, body
    properties = json.loads(body)["definitions"]["rows"]["properties"]

    assert properties["as_enum"]["enum"] == [
        "pending",
        "in_progress",
        "completed",
        "cancelled",
    ]
    assert "enum" not in properties["as_checked_text"], (
        "a CHECK constraint now reaches the document; ADR 0058 chose an enum "
        "because it did not, and that reasoning needs re-measuring"
    )


@requires_docker
def test_the_published_format_names_the_types_schema(api_rig: ApiRig) -> None:
    """Which is why the type lives in `api` and not beside the table.

    A type in `app` would print the string `app.probe_status` in a document
    served to the internet -- a schema the surface contract's `forbidden_schemas`
    exists to keep unaddressable, named in the artifact.
    """
    _, _, body = api_rig.call("GET", "/", bearer=token(role="probe_web"))
    properties = json.loads(body)["definitions"]["rows"]["properties"]
    assert properties["as_enum"]["format"] == "api.probe_status"


@requires_docker
def test_follow_privileges_follows_a_public_grant(api_rig: ApiRig) -> None:
    """The reason every `CREATE FUNCTION` needs a `REVOKE … FROM PUBLIC` beside it.

    PostgreSQL grants EXECUTE to PUBLIC on every new function, and D57 measured
    `ALTER DEFAULT PRIVILEGES` to store nothing on this image. So a function
    nobody granted is advertised in the document an **anonymous** caller
    receives, and is callable by them.
    """
    status, _, body = api_rig.call("GET", "/")
    assert status == 200, body
    anonymous_paths = set(json.loads(body)["paths"])

    assert "/rpc/left_public" in anonymous_paths, (
        "PUBLIC no longer reaches the published document; the REVOKE beside every "
        "CREATE FUNCTION is now defence in depth rather than the boundary"
    )
    assert "/rpc/revoked_from_public" not in anonymous_paths
    assert api_rig.status("POST", "/rpc/left_public", body={}) == 200


@requires_docker
def test_a_role_with_no_grant_sees_no_relation(api_rig: ApiRig) -> None:
    """The other half: relations do follow privileges, so the document an
    anonymous caller gets carries no table it cannot read.

    The key is absent rather than empty when nothing qualifies, which is worth
    asserting the way it is: a test reading `["definitions"]` and comparing to
    `{}` would raise rather than fail, and a raise in a suite that also skips on
    a missing daemon is a result nobody reads twice.
    """
    _, _, body = api_rig.call("GET", "/")
    document = json.loads(body)
    assert document.get("definitions", {}) == {}
    assert not [path for path in document["paths"] if path.startswith("/rows")]


# ---------------------------------------------------------------------------
# The pre-request hook (ADR 0052, D139)
# ---------------------------------------------------------------------------


@requires_docker
def test_the_hook_runs_after_the_role_switch(api_rig: ApiRig) -> None:
    """ADR 0052's premise, and the reason the grant it bounds is unavoidable.

    If the hook ran as the authenticator, the impersonated role would need no
    `EXECUTE` and `app_private` could stay closed to every HTTP caller.
    """
    api_rig.call("GET", "/rows", bearer=token(role="probe_web", sub=OWNER_A))
    observed = [line for line in api_rig.server_log().splitlines() if "PREREQUEST" in line]
    assert observed, "the hook did not run"
    assert any(
        "current_user=probe_web" in line and "session_user=probe_auth" in line for line in observed
    ), observed[-3:]


@requires_docker
def test_the_hook_runs_inside_a_read_only_transaction_on_a_read(api_rig: ApiRig) -> None:
    """So a hook that writes turns the entire read surface off.

    Measured the hard way: an early version of `postgrest_pre_request` kept an
    audit row, and every GET came back 405 "cannot execute INSERT in a read-only
    transaction". The hook is not a place to record anything.
    """
    assert api_rig.start_service(pre_request="app_private.writes_a_row"), api_rig.logs()
    try:
        status, _, body = api_rig.call("GET", "/rows", bearer=token(role="probe_web", sub=OWNER_A))
        assert status == 405, body
        assert json.loads(body)["code"] == "25006"

        # The control: the same hook, the same write, on a path whose
        # transaction is not read-only. Without this, a hook that failed for any
        # other reason would read as proof of the property above.
        written, _, detail = api_rig.call(
            "POST", "/rows", bearer=token(role="probe_web", sub=OWNER_A),
            body={"owner_id": OWNER_A, "title": "written"},
        )  # fmt: skip
        assert written in (200, 201), f"the hook's write failed where one is allowed: {detail}"
    finally:
        assert api_rig.start_service(pre_request="app_private.pre_request")


@requires_docker
def test_an_unresolvable_hook_starts_and_then_refuses_everything(api_rig: ApiRig) -> None:
    """D139, answered in both directions.

    The dangerous half would have been failing **open** -- a service that could
    not resolve its hook and skipped it, which is a public API with claim
    validation silently disabled and every other check green. It does not do
    that.

    What it does instead is the other shape this project keeps producing: it
    starts, reports a warm schema cache, passes `--ready`, and answers every
    request with a 404. A green container beside a broken API.
    """
    assert api_rig.start_service(pre_request="app_private.no_such_hook"), (
        "the service refused to start; the ordering risk D139 describes is gone "
        "and the deploy sequencing can be simplified"
    )
    try:
        assert "Schema cache loaded in" in api_rig.logs()

        status, _, body = api_rig.call("GET", "/rows", bearer=token(role="probe_web", sub=OWNER_A))
        assert status == 404, body
        answered = json.loads(body)
        assert answered["code"] == "42883"
        assert "no_such_hook" in answered["message"]

        ready = subprocess.run(
            ["docker", "exec", api_rig.service, "postgrest", "--ready"],
            capture_output=True, text=True, check=False, timeout=60,
        )  # fmt: skip
        assert ready.returncode == 0, (
            "`--ready` now fails when the hook cannot resolve; the healthcheck "
            "proves more than D156 records and that note should be revisited"
        )
    finally:
        assert api_rig.start_service(pre_request="app_private.pre_request")


@requires_docker
def test_a_token_naming_an_ungranted_role_is_refused(api_rig: ApiRig) -> None:
    """`SEC-ROLE-001`'s mechanism, measured.

    The set of roles a token can name is the set granted to the authenticator.
    A role that exists and was not granted is 403; one that does not exist is
    401 -- both refused, and the difference discloses only whether a name is a
    role, which the deployed document already publishes for the two that matter.
    """
    assert api_rig.status("GET", "/rows", bearer=token(role="probe_unreachable")) == 403
    assert api_rig.status("GET", "/rows", bearer=token(role="postgres")) == 403
    assert api_rig.status("GET", "/rows", bearer=token(role="no_such_role_at_all")) == 401


@requires_docker
def test_a_forged_token_is_refused_before_any_role_is_assumed(api_rig: ApiRig) -> None:
    forged = token(role="probe_web")[:-4] + "AAAA"
    status, headers, body = api_rig.call("GET", "/rows", bearer=forged)
    assert status == 401, body
    assert json.loads(body)["code"] == "PGRST301"
    assert "Bearer" in headers.get("WWW-Authenticate", "")


@requires_docker
def test_row_isolation_survives_the_http_path(api_rig: ApiRig) -> None:
    """The claim the hook establishes is the one the policy reads.

    Not a restatement of `SEC-RLS-001`, which proves isolation given a claim set
    directly in SQL. This proves the claim arrives from a token, through a hook,
    into a policy, without anything in between widening it.
    """
    api_rig.call(
        "POST", "/rows",
        bearer=token(role="probe_web", sub=OWNER_A), body={"owner_id": OWNER_A, "title": "A"},
    )  # fmt: skip
    _, _, mine = api_rig.call("GET", "/rows", bearer=token(role="probe_web", sub=OWNER_A))
    _, _, theirs = api_rig.call("GET", "/rows", bearer=token(role="probe_web", sub=OWNER_B))
    assert any(row["owner_id"] == OWNER_A for row in json.loads(mine))
    assert all(row["owner_id"] == OWNER_B for row in json.loads(theirs))


@requires_docker
def test_a_subject_that_is_not_a_uuid_reaches_the_policy_as_a_cast_error(
    api_rig: ApiRig,
) -> None:
    """Which is why the real hook shape-checks the subject before setting it.

    Unchecked, a malformed `sub` travels all the way to the row policy and comes
    back as a raw PostgreSQL cast error on every request -- 400 `invalid input
    syntax for type uuid`, produced by a policy, naming a type the caller never
    mentioned. The hook here is deliberately the naive version, so this measures
    the failure the real one prevents rather than asserting the fix.
    """
    status, _, body = api_rig.call("GET", "/rows", bearer=token(role="probe_web", sub="not-a-uuid"))
    assert status == 400, body
    assert json.loads(body)["code"] == "22P02"

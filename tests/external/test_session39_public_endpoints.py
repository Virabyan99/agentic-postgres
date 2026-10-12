"""Session 39's public Postgres door, from off the host (ADR 0268, ADR 0269).

The claims `public_port_scan` (EP-LIVE-002) and `public_endpoints_live`
(EP-LIVE-001). Run from the workstation, never the host, with no SSH: what is
measured is what the internet meets on the host's public address and the live
slot's two public names.

**EP-LIVE-001 is a customer's view of `slot3-prod`** (Run 11 step 3 created and
credentialed it with `s39-lifecycle.py --create-only`): its doors as `/v1`
serves them (`routes.control`, as the probe owner), its two passwords from
`APG_CUSTOMER_CREDENTIAL_DIR/<key>/` (0700/0600, written by
`bin/endpoint.sh credential`), and every connection through the public names on
5432 with the server's certificate VERIFIED against the workstation's roots --
given to every client as a FILE (`/certs/ca.crt` in a container), because the
locked Postgres image carries no bundle of its own (D2392). psql and the three
driver images (built from `services/clients/*` exactly as compose builds them,
rig 39c's scripts) run in containers through `_docker`, the module's one
process door; libpq-level checks run in process (psycopg). **Prisma's `migrate
deploy` refuses a `public` that holds tables it did not make** (P3005, D2393):
Run 11's `s39-endpoints.sh` migrates first, so here it finds its own history.

**The edge publishes 22's neighbours 80, 443 and 5432 and nothing else.** 5432
is the edge's `postgres` entrypoint: it answers only a TLS connection that names
a project's public host by SNI, and routes it to that project's customer
pooler. These proofs need no project with a door -- they are about what 5432
does for everybody else: a plaintext peer, a peer naming no project, a peer
naming a project that has no door. Each is refused, and none reaches a backend.

They replace `test_session4_public_transports.py`'s *"5432 is closed"* (D2338):
5432 is now open by design, so the stricter statement is what it answers.
"""

# ruff: noqa: F811, E501 -- the imported names are pytest fixtures, and the three
# driver scripts at the end are embedded verbatim (rig 39c's).

from __future__ import annotations

import ast
import json
import os
import socket
import ssl
import stat
import struct
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from tests.external.redaction import Secret
from tests.external.test_session38_public_lifecycle import (  # noqa: F401 -- fixtures
    Recorder,
    _only,
    control,
    endpoint,
    owner,
    probe,
)

from agentic_postgres import REPO_ROOT, naming

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_PUBLIC_IPV4", "APG_PROJECT_A_OUTPUTS"),
]

#: What the public address answers on, and nothing else (ADR 0268, ADR 0246
#: item 2): SSH, the edge's HTTP and HTTPS, and the edge's Postgres door.
OPEN_PORTS = (22, 80, 443, 5432)

#: Ports that would mean the platform leaked: the platform pooler's and the
#: database's own ports, the edge's container ports, the socket proxy, a second
#: cluster. The project's allocated loopback ports are added from its document.
CLOSED_PORTS = (5433, 6432, 8080, 8082, 8089, 8432, 8443, 9000, 2375, 2376)

CONNECT_TIMEOUT = 5.0

#: The `postgres` entrypoint's read deadline is 10 s (rig 39a: plaintext refused
#: in 11.4 s). A peer is never held much past it.
DEADLINE_BOUND = 20.0

#: libpq's SSLRequest: length 8, code 1234.5679 (80877103).
SSL_REQUEST = struct.pack("!ii", 8, 80877103)


def port_is_open(host: str, port: int) -> bool:
    """Full TCP connect, not a SYN probe (`test_session2_public_edge`'s reason)."""
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def startup_message(user: str, database: str) -> bytes:
    """A protocol 3.0 StartupMessage, in plaintext -- what `sslmode=disable` sends."""
    body = struct.pack("!i", 196608)
    for key, value in (("user", user), ("database", database)):
        body += key.encode() + b"\0" + value.encode() + b"\0"
    body += b"\0"
    return struct.pack("!i", len(body) + 4) + body


@pytest.fixture(scope="module")
def public_ipv4() -> str:
    return os.environ["APG_PUBLIC_IPV4"]


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# EP-LIVE-002 -- the public address, scanned
# ---------------------------------------------------------------------------


def test_only_the_four_ports_answer(public_ipv4: str, project_a: dict[str, Any]) -> None:
    """22, 80, 443 and 5432 accept a connection; every port that would mean a
    platform leak does not -- including the project's own allocated loopback
    transports, read from its document. The open half is the control: a scanner
    that reports everything closed proves nothing (`test_session2_public_edge`).
    """
    shut = [port for port in OPEN_PORTS if not port_is_open(public_ipv4, port)]
    assert not shut, f"{public_ipv4}: expected open, found closed: {shut}"
    database = project_a["database"]
    allocated = [database[name]["port"] for name in ("pooled", "direct") if database[name]["port"]]
    leaked = [port for port in (*CLOSED_PORTS, *allocated) if port_is_open(public_ipv4, port)]
    assert not leaked, f"{public_ipv4} accepted a connection on {leaked}"


def test_plaintext_is_refused(public_ipv4: str, project_a: dict[str, Any]) -> None:
    """A StartupMessage with no TLS -- `sslmode=disable` -- never reaches an
    authentication exchange: the gateway routes nothing without a TLS name, and
    after its read deadline answers bytes that are not Postgres's `R` and
    closes. Bounded: a plaintext peer is not held past the deadline (D2326)."""
    started = time.monotonic()
    received = b""
    with socket.create_connection((public_ipv4, 5432), timeout=CONNECT_TIMEOUT) as peer:
        peer.settimeout(DEADLINE_BOUND)
        peer.sendall(startup_message(project_a["database"]["roles"]["app_runtime"], "postgres"))
        try:
            while chunk := peer.recv(4096):
                received += chunk
        except (TimeoutError, ConnectionResetError):
            pass
    elapsed = time.monotonic() - started
    assert not received.startswith(b"R"), (
        f"a plaintext peer reached authentication: {received[:40]!r}"
    )
    assert not received.startswith(b"E"), f"a plaintext peer reached a backend: {received[:80]!r}"
    assert elapsed < DEADLINE_BOUND, f"a plaintext peer was held {elapsed:.1f} s"


@pytest.mark.parametrize("server_name", ["absent", "nobody.invalid", "alpha-pool"])
def test_a_wrong_or_absent_sni_is_refused(
    public_ipv4: str, project_a: dict[str, Any], server_name: str
) -> None:
    """The gateway speaks Postgres's TLS -- it answers `SSLRequest` with `S`,
    which is the control that this port is the door and not a dead socket -- and
    then refuses the handshake of a peer that names no project (`sniStrict`), a
    name no project has, or the name a project WITHOUT endpoints would have
    (alpha's `pool.<domain>`: no router, so no certificate)."""
    names = {
        "absent": None,
        "nobody.invalid": "nobody.invalid",
        "alpha-pool": f"pool.{project_a['project']['domain']}",
    }
    with socket.create_connection((public_ipv4, 5432), timeout=CONNECT_TIMEOUT) as peer:
        peer.settimeout(DEADLINE_BOUND)
        peer.sendall(SSL_REQUEST)
        assert peer.recv(1) == b"S", "5432 did not answer SSLRequest: this is not the gateway"
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_alpn_protocols(["postgresql"])
        with pytest.raises((ssl.SSLError, ConnectionResetError, OSError)):
            with context.wrap_socket(peer, server_hostname=names[server_name]) as tls:
                tls.do_handshake()


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof: nothing here reaches the host by any
    path but its public address. Read from this file's own text and syntax: no
    SSH library, no `ssh` argv, no destination; and the ONE process door is
    `_docker`, whose argv starts `docker` -- every `subprocess` call in the
    module is inside it (the drivers run in containers, D2350)."""
    text = Path(__file__).read_text(encoding="utf-8")
    # Each needle split so this list never spells what it forbids (D2398: the
    # first version held the quoted word in its own text and failed on itself).
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    tree = ast.parse(text)
    callers = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
            ):
                callers.append(function.name)
    assert callers and set(callers) == {"_docker"}, callers


# ---------------------------------------------------------------------------
# EP-LIVE-001 -- a customer's view of the live slot's two names
# ---------------------------------------------------------------------------

#: The workstation's public roots: every client is given this ONE file (D2392).
ROOTS = Path("/etc/ssl/certs/ca-certificates.crt")

#: The driver images, as compose builds them (`services/clients/*`).
DRIVERS = {"node-pg": "NODE_RUNTIME_IMAGE", "psycopg": "PYTHON_RUNTIME_IMAGE",
           "prisma": "NODE_RUNTIME_IMAGE"}  # fmt: skip


def _lock() -> dict[str, str]:
    return {
        name: value
        for name, _, value in (
            line.partition("=")
            for line in (REPO_ROOT / "versions.env").read_text("utf-8").splitlines()
            if "=" in line and not line.startswith("#")
        )
    }


def _docker(*argv: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """The module's one process door (`test_this_module_uses_no_ssh`)."""
    assert argv and argv[0] in ("run", "build", "rmi"), argv
    return subprocess.run(
        ["docker", *argv], stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def slot_creds() -> tuple[str, dict[str, Secret]]:
    """(key, {role: password}) from the credential directory: exactly one
    project's, 0700/0600, each file one line -- never printed: each password a
    `Secret`, so a failing test's arguments print no value (D2416)."""
    root = Path(os.environ["APG_CUSTOMER_CREDENTIAL_DIR"])
    assert stat.S_IMODE(root.stat().st_mode) == 0o700, f"{root} is not 0700"
    projects = [p for p in root.iterdir() if p.is_dir()]
    assert len(projects) == 1, [p.name for p in projects]
    passwords = {}
    for role in ("customer_app", "customer_admin"):
        path = projects[0] / role
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
        passwords[role] = Secret(path.read_text(encoding="utf-8").strip())
    return projects[0].name, passwords


@pytest.fixture(scope="module")
def doors(endpoint: str, owner: str, slot_creds: tuple[str, dict[str, str]]) -> dict[str, Any]:
    """The live slot's doors as `/v1` serves them -- the product's address book."""
    recorder = Recorder()
    status, served = recorder.json(
        "GET", f"{endpoint}/projects/{slot_creds[0]}/connections", None, owner
    )
    assert status == 200, (status, served.get("error"))
    _only(recorder, endpoint)
    return served


def _connect(door: dict[str, Any], user: str, password: str, **extra: Any) -> psycopg.Connection:
    return psycopg.connect(
        host=door["host"], port=door["port"], dbname=door["database"], user=user,
        password=password, sslmode="verify-full", sslrootcert=str(ROOTS),
        connect_timeout=15, autocommit=True, **extra,
    )  # fmt: skip


def _refused(door: dict[str, Any], user: str, password: str, **extra: Any) -> str:
    try:
        with _connect(door, user, password, **extra):
            pass
    except psycopg.OperationalError as error:
        return str(error)
    raise AssertionError(f"{user} was admitted at {door['host']}")


@pytest.fixture(scope="module")
def images() -> Iterator[dict[str, str]]:
    """The three driver images, built once from the checkout; removed after."""
    lock = _lock()
    built = {}
    for name, base in DRIVERS.items():
        tag = f"s39x-{name}"
        done = _docker("build", "-q", "-t", tag, "--build-arg", f"BASE_IMAGE={lock[base]}",
                       str(REPO_ROOT / "services" / "clients" / name))  # fmt: skip
        assert done.returncode == 0, f"{name}: {done.stderr[-400:]}"
        built[name] = tag
    yield built
    _docker("rmi", *built.values())


def _driver(image: str, script: str, suffix: str, environment: dict[str, str],
            entrypoint: str) -> subprocess.CompletedProcess:  # fmt: skip
    """One driver script in its image, the roots mounted as /certs/ca.crt."""
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as handle:
        handle.write(script)
    try:
        os.chmod(handle.name, 0o644)
        envs = [part for k, v in environment.items() for part in ("-e", f"{k}={v}")]
        return _docker("run", "--rm", "--network", "host", "-v", f"{ROOTS}:/certs/ca.crt:ro",
                       "-v", f"{handle.name}:/app/s39x{suffix}:ro", *envs,
                       "--entrypoint", entrypoint, image,
                       *(["-u"] if entrypoint == "python" else []), f"/app/s39x{suffix}")  # fmt: skip
    finally:
        os.unlink(handle.name)


@pytest.mark.requires_environment(
    "APG_CUSTOMER_CREDENTIAL_DIR", "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE"
)
def test_prisma_migrates_through_the_direct_name(
    doors: dict[str, Any], slot_creds: tuple[str, dict[str, str]], images: dict[str, str]
) -> None:
    """Prisma's `migrate deploy` through `direct.<domain>` -- a session, as the
    administrator role -- with strict certificate acceptance, then its Client
    through `pool.<domain>` WITHOUT `pgbouncer=true` (six writes, four parallel
    reads, prepared statements kept by the pooler)."""
    _, passwords = slot_creds

    def url(door: dict[str, Any], role: str) -> str:
        return (f"postgresql://{door['user']}:{passwords[role]}@{door['host']}:{door['port']}/"
                f"{door['database']}?schema=public&sslmode=require&sslcert=/certs/ca.crt"
                "&sslaccept=strict")  # fmt: skip

    environment = {"DATABASE_URL": url(doors["pooled"], "customer_app"),
                   "DIRECT_URL": url(doors["direct"], "customer_admin")}  # fmt: skip
    envs = [part for k, v in environment.items() for part in ("-e", f"{k}={v}")]
    migrated = _docker("run", "--rm", "--network", "host", "-v", f"{ROOTS}:/certs/ca.crt:ro", *envs,
                       "--entrypoint", "/app/node_modules/.bin/prisma", images["prisma"],
                       "migrate", "deploy", "--schema", "/app/prisma/schema.prisma")  # fmt: skip
    assert migrated.returncode == 0, migrated.stdout[-600:] + migrated.stderr[-600:]
    client = _driver(images["prisma"], PRISMA_CLIENT, ".mjs", environment, "node")
    assert "RESULT prisma-client-pooled ok" in client.stdout, client.stdout[-600:]
    assert f"user={doors['pooled']['user']}" in client.stdout, client.stdout[-300:]
    assert "pgbouncer" not in environment["DATABASE_URL"]


@pytest.mark.requires_environment(
    "APG_CUSTOMER_CREDENTIAL_DIR", "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE"
)
def test_psql_reaches_both_names(
    doors: dict[str, Any], slot_creds: tuple[str, dict[str, str]]
) -> None:
    """psql -- the locked image's, the roots given as a file -- with
    `sslmode=verify-full`, through `pool.<domain>` as the application role and
    `direct.<domain>` as the administrator role: each `current_user` is that
    door's role. The control: the same login with NO trust file is refused,
    so verification is what was exercised."""
    _, passwords = slot_creds
    image = _lock()["POSTGRES_IMAGE"]

    def psql(door: dict[str, Any], role: str, roots: str) -> subprocess.CompletedProcess:
        conninfo = (f"host={door['host']} port={door['port']} dbname={door['database']} "
                    f"user={door['user']} sslmode=verify-full sslrootcert={roots} connect_timeout=15")  # fmt: skip
        return _docker("run", "--rm", "--network", "host", "-v", f"{ROOTS}:/certs/ca.crt:ro",
                       "-e", f"PGPASSWORD={passwords[role]}", "--entrypoint", "psql", image,
                       conninfo, "-XAtc", "select current_user")  # fmt: skip

    for door, role in ((doors["pooled"], "customer_app"), (doors["direct"], "customer_admin")):
        done = psql(door, role, "/certs/ca.crt")
        assert (done.returncode, done.stdout.strip()) == (0, door["user"]), done.stderr[-300:]
    control = psql(doors["pooled"], "customer_app", "system")
    assert control.returncode != 0 and "certificate" in control.stderr.lower(), control.stderr[
        -300:
    ]


@pytest.mark.requires_environment(
    "APG_CUSTOMER_CREDENTIAL_DIR", "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE"
)
def test_the_four_drivers_reach_the_pooled_name(
    doors: dict[str, Any], slot_creds: tuple[str, dict[str, str]], images: dict[str, str]
) -> None:
    """node-postgres through both names (a named prepared statement twice on the
    pooled one), psycopg through the pooled name with server-side prepares and
    `cancel_safe()` cancelling a 20 s statement through the gateway, and libpq
    in process -- each verifying the server, each its door's role."""
    _, passwords = slot_creds
    pooled, direct = doors["pooled"], doors["direct"]
    environment = {
        "DB": pooled["database"], "PH": pooled["host"], "PP": str(pooled["port"]), "PU": pooled["user"],
        "DH": direct["host"], "DP": str(direct["port"]), "DU": direct["user"],
        "APW": passwords["customer_app"], "DPW": passwords["customer_admin"],
    }  # fmt: skip
    node = _driver(images["node-pg"], NODE_PG, ".mjs", environment, "node")
    assert (
        "RESULT node-pg-pooled ok" in node.stdout and "RESULT node-pg-direct ok" in node.stdout
    ), node.stdout[-600:]
    python = _driver(images["psycopg"], PSYCOPG, ".py", environment, "python")
    assert "RESULT psycopg-pooled-prepared ok" in python.stdout, python.stdout[-600:]
    assert "RESULT psycopg-cancel-safe ok" in python.stdout, python.stdout[-600:]
    with _connect(pooled, pooled["user"], passwords["customer_app"]) as connection:
        assert connection.execute("select current_user").fetchone()[0] == pooled["user"]


@pytest.mark.requires_environment(
    "APG_CUSTOMER_CREDENTIAL_DIR", "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE"
)
def test_the_admin_writes_only_in_public(
    doors: dict[str, Any], slot_creds: tuple[str, dict[str, str]]
) -> None:
    """ADR 0269 item 2 through the real doors: the administrator creates a table
    with a vector column in `public` and the application role writes rows in it
    (default privileges) but cannot create one; the administrator is refused
    `app_private`, `CREATE SCHEMA` and `CREATE EXTENSION`."""
    _, passwords = slot_creds
    pooled, direct = doors["pooled"], doors["direct"]
    with _connect(direct, direct["user"], passwords["customer_admin"]) as admin:
        admin.execute("create table if not exists public.s39_external_probe("
                      "id bigserial primary key, emb extensions.vector(3))")  # fmt: skip
        for statement in ("select count(*) from app_private.users", "create schema s39_not_mine",
                          "create extension pg_trgm"):  # fmt: skip
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                admin.execute(statement)
    with _connect(pooled, pooled["user"], passwords["customer_app"]) as app:
        app.execute("insert into public.s39_external_probe(emb) values (%s)", ("[1,2,3]",))
        assert app.execute("select count(*) from public.s39_external_probe").fetchone()[0] >= 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("create table public.s39_not_mine(x int)")


@pytest.mark.requires_environment(
    "APG_CUSTOMER_CREDENTIAL_DIR", "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE"
)
def test_no_platform_role_passes_either_door(
    doors: dict[str, Any], slot_creds: tuple[str, dict[str, str]]
) -> None:
    """One role per door (ADR 0269 item 3): the superuser, the slot's own
    platform roles (derived, never typed) and the OTHER door's customer role are
    each refused at both names -- each with the password the customer holds, so
    a refusal is the userlist's and never a wrong password's alone. The control:
    each door's own role, the same password, is admitted."""
    key, passwords = slot_creds
    platform = naming.database_roles(naming.sql_key(key))
    strangers = ["postgres", platform["app_runtime"], platform["migration_user"],
                 platform["postgrest_authenticator"]]  # fmt: skip
    for door, own, other in (
        (doors["pooled"], "customer_app", doors["direct"]["user"]),
        (doors["direct"], "customer_admin", doors["pooled"]["user"]),
    ):
        for user in (*strangers, other):
            _refused(door, user, passwords[own])
        with _connect(door, door["user"], passwords[own]) as admitted:
            assert admitted.execute("select current_user").fetchone()[0] == door["user"]


@pytest.mark.requires_environment("APG_CONTROL_OUTPUTS")
def test_a_project_without_endpoints_has_no_door(
    public_ipv4: str, project_a: dict[str, Any]
) -> None:
    """Alpha and the control project have no public endpoints: a client asking
    for their would-be names on the host's address -- `hostaddr` given, so no
    DNS record is needed -- is refused before any authentication (no router, no
    certificate), whatever role it names. **Not beta** (D2399): the external
    gate exports no project B document, so a proof gated on one would skip in
    every sweep; the control project's document is the one it does export."""
    control = json.loads(Path(os.environ["APG_CONTROL_OUTPUTS"]).read_text(encoding="utf-8"))
    for document in (project_a, control):
        for host in naming.endpoint_hosts(document["project"]["domain"]):
            try:
                psycopg.connect(host=host, hostaddr=public_ipv4, port=5432, dbname="postgres",
                                user=document["database"]["roles"]["app_runtime"], password="x",  # noqa: S106
                                sslmode="verify-full", sslrootcert=str(ROOTS),
                                connect_timeout=15).close()  # fmt: skip
            except psycopg.OperationalError as error:
                text = str(error).lower()
                assert "password" not in text and "authentication" not in text, (host, text)
            else:
                raise AssertionError(f"{host} answered a login")


NODE_PG = """import pg from "pg";
import { readFileSync } from "node:fs";
const ca = readFileSync("/certs/ca.crt", "utf8");
const e = process.env;
async function run(label, cfg, fn) {
  const c = new pg.Client(cfg);
  try { await c.connect(); console.log(`RESULT ${label} ok`, JSON.stringify(await fn(c))); }
  catch (err) { console.log(`RESULT ${label} refused`, err.code || "", err.message); }
  finally { try { await c.end(); } catch {} }
}
const base = { database: e.DB, ssl: { ca, rejectUnauthorized: true } };
await run("node-pg-pooled", { ...base, host: e.PH, port: +e.PP, user: e.PU, password: e.APW }, async (c) => {
  const q = { name: "s39q", text: "select $1::int + 1 as n", values: [1] };
  await c.query(q); const b = await c.query(q);
  return [(await c.query("select current_user")).rows[0], b.rows[0]];
});
await run("node-pg-direct", { ...base, host: e.DH, port: +e.DP, user: e.DU, password: e.DPW },
  async (c) => (await c.query("select current_user")).rows[0]);
"""

PSYCOPG = """import os, threading, time
import psycopg
e = os.environ
ci = (f"host={e['PH']} port={e['PP']} dbname={e['DB']} user={e['PU']} password={e['APW']} "
      "sslmode=verify-full sslrootcert=/certs/ca.crt connect_timeout=15")
try:
    with psycopg.connect(ci, autocommit=True) as c:
        for _ in range(3):
            n = c.execute("select %s::int + 1", (1,), prepare=True).fetchone()[0]
        print("RESULT psycopg-pooled-prepared ok", c.execute("select current_user").fetchone()[0], n)
except Exception as err:
    print("RESULT psycopg-pooled-prepared refused", type(err).__name__, str(err).strip())
c = psycopg.connect(ci, autocommit=True)
threading.Timer(3, c.cancel_safe).start(); t0 = time.time()
try:
    c.execute("select pg_sleep(20)")
    print(f"RESULT psycopg-cancel-safe refused not cancelled after {time.time()-t0:.1f} s")
except psycopg.errors.QueryCanceled:
    print(f"RESULT psycopg-cancel-safe ok cancelled after {time.time()-t0:.1f} s")
except Exception as err:
    print(f"RESULT psycopg-cancel-safe refused {type(err).__name__}: {err}")
c.close()
"""

PRISMA_CLIENT = """import { PrismaClient } from "@prisma/client";
const p = new PrismaClient();
try {
  for (let i = 0; i < 6; i++) await p.fixtureRow.create({ data: { label: "s39x-" + i } });
  const who = await p.$queryRaw`select current_user::text as u`;
  const again = await Promise.all([1, 2, 3, 4].map(() => p.fixtureRow.findMany({ where: { label: "s39x-1" } })));
  console.log(`RESULT prisma-client-pooled ok user=${who[0].u} parallel=${again.map((r) => r.length).join(",")}`);
} catch (err) {
  console.log(`RESULT prisma-client-pooled refused ${err.code || ""} ${(err.message || "").split("\\n").filter(Boolean).slice(-2).join(" | ")}`);
} finally { await p.$disconnect(); }
"""

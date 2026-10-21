"""The console's wire client: exact bytes, SCRAM equal to Python's, PostgreSQL decides.

Session 44 (ADR 0285, D2732): `SQL-CLIENT-001`. `services/console/public/pg.js`
is run by Node 22 (`NODE_RUNTIME_IMAGE`) as the browser loads it -- the
console's files mounted at `/console/` with a `package.json` saying `module`, so
`import ... from "/console/scram.js"` resolves exactly as it does in the page.

Two halves. **Pure** (`--network none`): the startup message's bytes against
Python's; the client-final proof against Python's `hashlib`/`hmac` for a fixed
exchange; a fake server in the same Node process (a stand-in `WebSocket`) that
asks for another authentication, forges its signature, or sends a message
outside the bound. **Live** (the bridge network, the relay reached as `host.docker.internal`): PostgreSQL 18.4 from
`POSTGRES_IMAGE`, PgBouncer from `PGBOUNCER_IMAGE` in front of it in transaction
and session mode with TLS for its clients (the door's shape: the edge
terminates TLS in production, PgBouncer here), and the relay from Run 2 served
in this process -- so every byte crosses the relay and a pooler, as an editor
session's do. Node's WebSocket is given the console's `Origin` by the driver
(undici's `headers` init, measured in Run 4); `pg.js` itself has no test seam.
"""

# ruff: noqa: E501 -- the embedded JavaScript drivers keep one statement per line,
# as Node reads them; wrapping them for Python's line length would change nothing
# they do and make them harder to read beside the protocol.

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_image_contracts import LOCK, requires_docker
from tests.contract.test_sql_relay import ORIGIN, ZONE, Authority, Loop, relay_module

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security, requires_docker]

PUBLIC = REPO_ROOT / "services" / "console" / "public"
NODE = LOCK["NODE_RUNTIME_IMAGE"]
POOL = f"pool.slot3.{ZONE}"
DIRECT = f"direct.slot3.{ZONE}"
PASSWORD = "a-fixed-password-for-the-proof"  # noqa: S105 -- a fixture, never a credential


def _console(tmp_path: Path, driver: str) -> Path:
    """The console's scripts at what the container will see as /console/."""
    directory = tmp_path / "console"
    directory.mkdir(parents=True)
    for script in PUBLIC.glob("*.js"):
        shutil.copy(script, directory / script.name)
    (directory / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (directory / "driver.js").write_text(driver, encoding="utf-8")
    return directory


def _node(tmp_path: Path, driver: str, *, network: str = "none", timeout: int = 120) -> Any:
    directory = _console(tmp_path, driver)
    # The live half reaches the relay this process serves as `host.docker.internal`:
    # `--network host` would be Docker Desktop's VM, not this machine (measured).
    gateway = ["--add-host", "host.docker.internal:host-gateway"] if network == "bridge" else []
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", network, *gateway, "-v", f"{directory}:/console:ro",
         NODE, "node", "/console/driver.js"],
        capture_output=True, text=True, check=False, timeout=timeout,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


#: Retries a TCP connect to each port from a container on the bridge network, the
#: way the driver will reach the relay. On Docker Desktop a port newly bound in WSL
#: answers at `host.docker.internal` only once WSL's localhost forwarding registers
#: it -- the first gate shard met that race (D2793); CI's Docker Engine answers at once.
REACH = r"""
const net = require("node:net");
const ports = process.argv.slice(1).map(Number);
const once = (port) => new Promise((resolve) => {
  const socket = net.connect({ host: "host.docker.internal", port }, () => { socket.end(); resolve(true); });
  socket.on("error", () => resolve(false));
  socket.setTimeout(2000, () => { socket.destroy(); resolve(false); });
});
(async () => {
  for (const port of ports) {
    let ok = false;
    for (let attempt = 0; attempt < 120 && !ok; attempt++) {
      ok = await once(port);
      if (!ok) await new Promise((r) => setTimeout(r, 500));
    }
    if (!ok) { console.log(`unreachable ${port}`); process.exit(1); }
  }
  console.log("reachable");
})();
"""


def _reachable(ports: list[int]) -> None:
    done = subprocess.run(
        ["docker", "run", "--rm", "--add-host", "host.docker.internal:host-gateway", NODE,
         "node", "-e", REACH, *map(str, ports)],
        capture_output=True, text=True, check=False, timeout=180,
    )  # fmt: skip
    assert done.stdout.strip() == "reachable", (done.stdout, done.stderr[-500:])


# A stand-in WebSocket for the pure half: `script(socket, sent)` answers what the
# client sends. Installed as the global before pg.js runs, as the browser's is.
FAKE = r"""
class FakeSocket {
  static script = null;
  constructor(url) {
    this.url = url; this.sent = []; this.readyState = 0;
    setTimeout(() => { this.readyState = 1; this.onopen && this.onopen(); }, 0);
  }
  send(bytes) { this.sent.push(new Uint8Array(bytes)); FakeSocket.script(this, this.sent.length - 1, new Uint8Array(bytes)); }
  deliver(bytes) { setTimeout(() => this.onmessage && this.onmessage({ data: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length) }), 0); }
  close(code) { if (this.readyState === 3) return; this.readyState = 3; setTimeout(() => this.onclose && this.onclose({ code: code || 1000 }), 0); }
}
globalThis.WebSocket = FakeSocket;
const enc = new TextEncoder();
const int32 = (n) => { const b = new Uint8Array(4); new DataView(b.buffer).setInt32(0, n); return b; };
const cat = (...parts) => { const out = new Uint8Array(parts.reduce((a, p) => a + p.length, 0)); let o = 0; for (const p of parts) { out.set(p, o); o += p.length; } return out; };
const msg = (type, body) => cat(enc.encode(type), int32(body.length + 4), body);
const auth = (code, rest = new Uint8Array(0)) => msg("R", cat(int32(code), rest));
const ready = () => cat(msg("K", cat(int32(7), int32(42))), msg("Z", enc.encode("I")));
const attempt = async (f) => { try { return { ok: await f() }; } catch (e) { return { error: e.message }; } };
"""


def test_the_startup_message_is_exact(tmp_path: Path) -> None:
    driver = (
        'import { startupMessage, cancelRequest } from "/console/pg.js";\n'
        "const hex = (b) => Buffer.from(b).toString('hex');\n"
        'console.log(JSON.stringify({ startup: hex(startupMessage("apg_slot3_prod_customer_app", "slot3_prod")),'
        " cancel: hex(cancelRequest(123456, -98765)) }));\n"
    )
    out = _node(tmp_path, driver)
    params = (
        b"".join(
            name + b"\0" + value + b"\0"
            for name, value in (
                (b"user", b"apg_slot3_prod_customer_app"),
                (b"database", b"slot3_prod"),
                (b"application_name", b"apg-console-editor"),
            )
        )
        + b"\0"
    )
    expected = (len(params) + 8).to_bytes(4, "big") + (196608).to_bytes(4, "big") + params
    assert out["startup"] == expected.hex()
    cancel = b"".join(n.to_bytes(4, "big", signed=True) for n in (16, 80877102, 123456, -98765))
    assert out["cancel"] == cancel.hex()


def _python_final(password: str, first_bare: str, server_first: str) -> tuple[str, str]:
    attributes = dict(part.split("=", 1) for part in server_first.split(","))
    salted = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), base64.b64decode(attributes["s"]), int(attributes["i"])
    )
    client_key = hmac.new(salted, b"Client Key", "sha256").digest()
    without_proof = f"c=biws,r={attributes['r']}"
    auth_message = f"{first_bare},{server_first},{without_proof}".encode()
    signature = hmac.new(hashlib.sha256(client_key).digest(), auth_message, "sha256").digest()
    proof = bytes(a ^ b for a, b in zip(client_key, signature, strict=True))
    server_key = hmac.new(salted, b"Server Key", "sha256").digest()
    return (
        f"{without_proof},p={base64.b64encode(proof).decode()}",
        base64.b64encode(hmac.new(server_key, auth_message, "sha256").digest()).decode(),
    )


def test_the_scram_proof_equals_pythons(tmp_path: Path) -> None:
    first_bare = "n=,r=fyko+d2lbbFgONRv9qkxdawL"
    salt = base64.b64encode(bytes(range(16))).decode()
    exchanges = [
        f"r=fyko+d2lbbFgONRv9qkxdawL3rfcNHYJY1ZVvWVs7j,s={salt},i=4096",
        f"r=fyko+d2lbbFgONRv9qkxdawLserver,s={base64.b64encode(b'another-salt-16b').decode()},i=8192",
    ]
    refused = [
        f"r=fyko+d2lbbFgONRv9qkxdawL3rfc,s={salt},i=4095",  # below PostgreSQL's 4096 (D2767)
        f"r=someone-elses-nonce,s={salt},i=4096",  # does not extend ours
        f"r=fyko+d2lbbFgONRv9qkxdawL,s={salt},i=4096",  # adds nothing to ours
    ]
    driver = (
        'import { clientFinal } from "/console/pg.js";\n'
        f"const exchanges = {json.dumps(exchanges)}; const refused = {json.dumps(refused)};\n"
        "const out = { finals: [], refused: [] };\n"
        f'for (const s of exchanges) out.finals.push(await clientFinal("{PASSWORD}", "{first_bare}", s));\n'
        "for (const s of refused) {\n"
        f'  try {{ await clientFinal("{PASSWORD}", "{first_bare}", s); out.refused.push("accepted"); }}\n'
        "  catch (e) { out.refused.push(e.message); }\n"
        "}\n"
        "console.log(JSON.stringify(out));\n"
    )
    out = _node(tmp_path, driver)
    for exchange, final in zip(exchanges, out["finals"], strict=True):
        message, signature = _python_final(PASSWORD, first_bare, exchange)
        assert final == {"message": message, "serverSignature": signature}
    # The control: two exchanges, two different proofs -- not one constant twice.
    assert out["finals"][0]["message"] != out["finals"][1]["message"]
    assert "fewer than 4096" in out["refused"][0]
    assert all("nonce" in reason for reason in out["refused"][1:]), out["refused"]


def _scram_server(signature: str) -> str:
    """A fake server that runs a real SCRAM exchange in Node (the client's own
    clientFinal is NOT used to build its answer) and signs with `signature`:
    `good` or `forged`."""
    return (
        FAKE
        + r"""
import { connect } from "/console/pg.js";
import { scramKeys } from "/console/scram.js";
"""
        + r"""
const SALT = new Uint8Array(16).fill(5);
let clientFirstBare = "", serverFirst = "";
const hm = async (k, d) => new Uint8Array(await crypto.subtle.sign("HMAC", await crypto.subtle.importKey("raw", k, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]), enc.encode(d)));
const b64 = (b) => Buffer.from(b).toString("base64");
FakeSocket.script = async (socket, index, bytes) => {
  if (index === 0) { socket.deliver(auth(10, cat(enc.encode("SCRAM-SHA-256\0"), new Uint8Array([0])))); return; }
  const text = new TextDecoder().decode(bytes.slice(5));
  if (index === 1) {
    clientFirstBare = text.slice(text.indexOf("n=,r="));
    serverFirst = `r=${clientFirstBare.slice(5)}SERVER,s=${b64(SALT)},i=4096`;
    socket.deliver(auth(11, enc.encode(serverFirst)));
    return;
  }
  if (index === 2) {
    const keys = await scramKeys("PASSWORD", SALT, 4096);
    const authMessage = `${clientFirstBare},${serverFirst},${text.split(",p=")[0]}`;
    let v = b64(await hm(new Uint8Array(keys.serverKey), authMessage));
    if ("SIGNATURE" === "forged") v = (v[0] === "A" ? "B" : "A") + v.slice(1);
    socket.deliver(cat(auth(12, enc.encode(`v=${v}`)), auth(0), ready()));
  }
};
const out = await attempt(async () => { const c = await connect({ relay: "wss://relay.test", host: "pool.slot3.example.test", user: "u", database: "d", password: "PASSWORD" }); return [c.pid, c.key]; });
console.log(JSON.stringify(out));
""".replace("PASSWORD", PASSWORD).replace("SIGNATURE", signature)
    )


def test_a_forged_server_signature_is_refused(tmp_path: Path) -> None:
    forged = _node(tmp_path / "f", _scram_server("forged"))
    assert forged == {
        "error": "the server's signature did not verify; refused before AuthenticationOk"
    }
    good = _node(tmp_path / "g", _scram_server("good"))  # the control
    assert good == {"ok": [7, 42]}


@pytest.mark.parametrize(
    ("first", "expected"),
    [
        ("auth(5, new Uint8Array([1, 2, 3, 4]))", "authentication 5"),  # MD5
        ("auth(3)", "authentication 3"),  # cleartext
        ("auth(0)", "authentication 0"),  # trust: no proof at all
        (
            'auth(10, cat(enc.encode("SCRAM-SHA-256-PLUS\\0"), new Uint8Array([0])))',
            "does not offer SCRAM-SHA-256",
        ),
        ('msg("Z", enc.encode("I"))', "message Z"),
    ],
)
def test_only_scram_is_spoken(tmp_path: Path, first: str, expected: str) -> None:
    driver = (
        FAKE
        + 'import { connect } from "/console/pg.js";\n'
        + "let answered = 0;\n"
        + f"FakeSocket.script = (socket, index) => {{ if (index === 0) socket.deliver({first}); else answered += 1; }};\n"
        + 'const out = await attempt(() => connect({ relay: "wss://r", host: "h", user: "u", database: "d", password: "p" }));\n'
        + "console.log(JSON.stringify({ ...out, answered }));\n"
    )
    out = _node(tmp_path, driver)
    assert expected in out.get("error", ""), out
    assert out["answered"] == 0, "the client sent something after a refused authentication request"


def test_a_message_outside_the_bound_closes_the_connection(tmp_path: Path) -> None:
    driver = (
        FAKE
        + 'import { connect, MAX_MESSAGE_BYTES } from "/console/pg.js";\n'
        + "FakeSocket.script = (socket, index) => { if (index === 0) socket.deliver(cat(enc.encode('R'), int32(MAX_MESSAGE_BYTES + 1))); };\n"
        + "const big = await attempt(() => connect({ relay: 'wss://r', host: 'h', user: 'u', database: 'd', password: 'p' }));\n"
        + "FakeSocket.script = (socket, index) => { if (index === 0) socket.deliver(cat(enc.encode('R'), int32(3))); };\n"
        + "const small = await attempt(() => connect({ relay: 'wss://r', host: 'h', user: 'u', database: 'd', password: 'p' }));\n"
        + "console.log(JSON.stringify({ big, small }));\n"
    )
    out = _node(tmp_path, driver)
    assert (
        "outside the editor's bound" in out["big"]["error"]
        and "1048577 bytes" in out["big"]["error"]
    )
    assert (
        "outside the editor's bound" in out["small"]["error"] and "3 bytes" in out["small"]["error"]
    )


# -- the live half -------------------------------------------------------------


@pytest.fixture(scope="module")
def door(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """PostgreSQL 18.4, two PgBouncers (transaction, session) with TLS for their
    clients, and the relay in this process in front of each. Removed with their
    volumes (D2098)."""
    directory = tmp_path_factory.mktemp("console-pg")
    authority = Authority(directory, "door-ca")
    authority.issue((POOL, DIRECT), "door")  # door.crt and door.key, beside the inis
    password = secrets.token_urlsafe(24)
    network = f"apg-console-pg-{secrets.token_hex(4)}"
    names: list[str] = []

    def docker(*args: str, check: bool = True) -> str:
        done = subprocess.run(
            ["docker", *args], capture_output=True, text=True, check=False, timeout=600
        )
        if check:
            assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    docker("network", "create", network)
    loop = Loop()
    servers = []
    try:
        pg = f"{network}-pg"
        names.append(pg)
        docker("run", "-d", "--name", pg, "--network", network, "--network-alias", "pg",
               "-e", f"POSTGRES_PASSWORD={secrets.token_urlsafe(16)}", "-e", "POSTGRES_DB=slot3_prod",
               LOCK["POSTGRES_IMAGE"])  # fmt: skip
        deadline = time.monotonic() + 120
        while subprocess.run(["docker", "exec", pg, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                             capture_output=True, check=False).returncode:  # fmt: skip
            assert time.monotonic() < deadline, "PostgreSQL did not become ready"
            time.sleep(1)
        setup = (
            f"CREATE ROLE editor LOGIN PASSWORD '{password}' CONNECTION LIMIT 2;"
            "CREATE TABLE public.t (x int); GRANT SELECT, INSERT ON public.t TO editor;"
            "CREATE TABLE public.secret (x int);"
        )
        docker(
            "exec",
            pg,
            "psql",
            "-U",
            "postgres",
            "-d",
            "slot3_prod",
            "-v",
            "ON_ERROR_STOP=1",
            "-qc",
            setup,
        )
        verifier = docker("exec", pg, "psql", "-U", "postgres", "-d", "slot3_prod", "-qtAc",
                          "SELECT rolpassword FROM pg_authid WHERE rolname = 'editor'")  # fmt: skip
        (directory / "userlist").write_text(f'"editor" "{verifier}"\n', encoding="utf-8")
        ports = {}
        for mode in ("transaction", "session"):
            ini = (
                "[databases]\nslot3_prod = host=pg port=5432 dbname=slot3_prod\n[pgbouncer]\n"
                "listen_addr = 0.0.0.0\nlisten_port = 6432\nunix_socket_dir = /tmp\n"
                "auth_type = scram-sha-256\nauth_file = /cfg/userlist\n"
                f"pool_mode = {mode}\ndefault_pool_size = 2\nmax_db_connections = 2\n"
                "max_client_conn = 100\nignore_startup_parameters = extra_float_digits\n"
                "client_tls_sslmode = require\nclient_tls_cert_file = /cfg/door.crt\n"
                "client_tls_key_file = /cfg/door.key\n"
            )
            (directory / f"{mode}.ini").write_text(ini, encoding="utf-8")
        for path in directory.iterdir():
            os.chmod(path, 0o644)
        os.chmod(directory, 0o755)  # noqa: S103 -- read by the poolers' uid 70
        for mode in ("transaction", "session"):
            name = f"{network}-{mode}"
            names.append(name)
            docker("run", "-d", "--name", name, "--network", network, "--user", "70:70",
                   "-p", "127.0.0.1::6432", "-v", f"{directory}:/cfg:ro", "--entrypoint",
                   "/usr/bin/pgbouncer", LOCK["PGBOUNCER_IMAGE"], f"/cfg/{mode}.ini")  # fmt: skip
            ports[mode] = int(docker("port", name, "6432/tcp").rsplit(":", 1)[1])
        time.sleep(2)
        os.environ["SSL_CERT_FILE"] = str(authority.pem)
        relays = {}
        lines: list[str] = []
        for mode in ("transaction", "session"):
            config = relay_module.Configuration(8080, ORIGIN, ZONE, "127.0.0.1", ports[mode])
            server = loop.run(
                relay_module.Relay(config, log=lines.append).serve("0.0.0.0", 0)  # noqa: S104 -- reached from a container
            )
            servers.append(server)
            relays[mode] = f"ws://host.docker.internal:{server.sockets[0].getsockname()[1]}"
        _reachable([int(url.rsplit(":", 1)[1]) for url in relays.values()])
        yield {"relays": relays, "password": password, "lines": lines}
    finally:
        os.environ.pop("SSL_CERT_FILE", None)

        async def stop() -> None:
            for server in servers:
                server.close()
                await server.wait_closed()

        with contextlib.suppress(Exception):
            loop.run(stop(), timeout=10)
        loop.close()
        for name in names:
            subprocess.run(["docker", "rm", "-fv", name], capture_output=True, check=False)
        subprocess.run(["docker", "network", "rm", network], capture_output=True, check=False)


LIVE = r"""
const Base = globalThis.WebSocket;
globalThis.WebSocket = class extends Base { constructor(url) { super(url, { headers: { Origin: "ORIGIN" } }); } };
import { connect, PgError } from "/console/pg.js";
const RELAYS = RELAYS_JSON, PASSWORD = "THE_PASSWORD";
const all = async (c, text) => { const results = []; try { for await (const r of c.query(text)) results.push({ columns: r.columns && r.columns.map((x) => x.name), rows: r.rows, command: r.command, truncated: r.truncated, notices: r.notices.map((n) => n.message) }); return { results }; } catch (e) { return { results, error: { code: e.code, message: e.message, position: e.position, deadline: e.deadline } }; } };
const timed = async (f) => { const t = performance.now(); const out = await f(); return { ...out, seconds: +((performance.now() - t) / 1000).toFixed(2) }; };
const out = {};
for (const [mode, relay] of Object.entries(RELAYS)) {
  const r = {};
  // A step that throws is recorded as that step's failure, so its own test fails on it.
  const step = async (name, f) => { try { r[name] = await f(); } catch (e) { r[name] = { step_failed: true, error: { code: e.code || null, message: String(e.message), deadline: false } }; } };
  const open = (extra = {}) => connect({ relay, host: "POOL", user: "editor", database: "slot3_prod", password: PASSWORD, ...extra });
  try { await open({ password: "not-the-password" }); r.wrong_password = "accepted"; } catch (e) { r.wrong_password = { code: e.code, message: e.message }; }
  let c = null;
  await step("opened", async () => { c = await open(); return true; });
  if (c) {
    await step("identity", () => all(c, "SELECT current_user, current_setting('application_name')"));
    await step("rows", () => all(c, "SELECT 1 AS one, NULL AS nothing, 'x' AS two; SELECT generate_series(1, 3) AS n; ;"));
    await step("division", () => all(c, "SELECT 1 AS before; SELECT 1/0"));
    await step("after_error", () => all(c, "SELECT 2 AS after"));
    await step("syntax", () => all(c, "SELEC 1"));
    await step("denied", () => all(c, "SELECT * FROM public.secret"));
    await step("copy_out", () => all(c, "COPY (SELECT 1) TO STDOUT"));
    await step("copy_in", () => all(c, "COPY public.t FROM STDIN"));
    await step("after_copy", () => all(c, "SELECT 3 AS after_copy"));
    const sleeping = timed(() => all(c, "SELECT pg_sleep(30)"));
    await new Promise((res) => setTimeout(res, 1000));
    await step("cancel_closed", () => c.cancel());
    await step("cancelled", () => sleeping);
    await step("uncancelled", () => timed(() => all(c, "SELECT pg_sleep(1)")));
    await step("cap_fast", () => timed(() => all(c, "SELECT generate_series(1, 200000) AS n")));
    await step("cap_live", () => timed(() => all(c, "SELECT g, pg_sleep(0.0005) FROM generate_series(1, 200000) g")));
    await step("cap_bytes", () => timed(() => all(c, "SELECT repeat('x', 4096) FROM generate_series(1, 1000)")));
    await step("after_cap", () => all(c, "SELECT 4 AS after_cap"));
    await step("connections", () => all(c, "SELECT count(*) FROM pg_stat_activity WHERE usename = current_user"));
    c.close();
  }
  await step("deadline", async () => { const short = await open({ deadlineSeconds: 2 }); try { return await timed(() => all(short, "SELECT pg_sleep(30)")); } finally { short.close(); } });
  out[mode] = r;
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def live(door: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    driver = (
        LIVE.replace("ORIGIN", ORIGIN)
        .replace("RELAYS_JSON", json.dumps(door["relays"]))
        .replace("THE_PASSWORD", door["password"])
        .replace("POOL", POOL)
    )
    try:
        return _node(tmp_path_factory.mktemp("live"), driver, network="bridge", timeout=600)
    except AssertionError as failed:
        # The relay's own lines (no payload in them, D2743) say why a session ended.
        raise AssertionError(f"{failed}\nrelay: {door['lines'][-10:]}") from None


MODES = ("transaction", "session")


def _rows(result: dict[str, Any]) -> list[list[Any]]:
    return [r["rows"] for r in result["results"]]


@pytest.mark.parametrize("mode", MODES)
def test_a_query_returns_its_rows(live: dict[str, Any], mode: str) -> None:
    r = live[mode]
    assert _rows(r["identity"]) == [[["editor", "apg-console-editor"]]]
    assert r["rows"].get("error") is None
    first, second = r["rows"]["results"][:2]
    assert (first["columns"], first["rows"], first["command"]) == (
        ["one", "nothing", "two"], [["1", None, "x"]], "SELECT 1",
    )  # fmt: skip
    assert (second["columns"], second["rows"], second["command"]) == (
        ["n"], [["1"], ["2"], ["3"]], "SELECT 3",
    )  # fmt: skip


@pytest.mark.parametrize("mode", MODES)
def test_an_error_names_its_code(live: dict[str, Any], mode: str) -> None:
    r = live[mode]
    assert _rows(r["division"]) == [[["1"]]] and r["division"]["error"]["code"] == "22012"
    assert r["division"]["error"]["message"] == "division by zero"
    assert _rows(r["after_error"]) == [[["2"]]]  # the connection is usable after
    assert r["syntax"]["error"]["code"] == "42601" and r["syntax"]["error"]["position"] == "1"
    assert r["denied"]["error"]["code"] == "42501"  # PostgreSQL decides (no grant)
    # A wrong password through PgBouncer is PgBouncer's answer, never 28P01 (D2765).
    assert r["wrong_password"]["code"] == "08P01", r["wrong_password"]


@pytest.mark.parametrize("mode", MODES)
def test_copy_is_refused(live: dict[str, Any], mode: str) -> None:
    r = live[mode]
    out, into = r["copy_out"], r["copy_in"]
    assert out.get("error") is None and out["results"][0]["command"] == "COPY 1"
    assert "COPY output is not shown in the editor" in out["results"][0]["notices"]
    assert into["error"]["code"] == "57014"
    assert "the SQL editor sends no COPY data" in into["error"]["message"]
    assert _rows(r["after_copy"]) == [[["3"]]]


@pytest.mark.parametrize("mode", MODES)
def test_a_cancel_stops_the_statement(live: dict[str, Any], mode: str) -> None:
    r = live[mode]
    assert r["cancelled"]["error"]["code"] == "57014", r["cancelled"]
    assert r["cancelled"]["error"]["deadline"] is False
    assert r["cancelled"]["seconds"] < 6
    assert r["cancel_closed"] is True
    # The control: uncancelled, a statement runs to its end.
    assert r["uncancelled"].get("error") is None and r["uncancelled"]["seconds"] >= 1
    # The 60 s deadline, set to 2 here: the same cancel, named as the deadline's.
    assert r["deadline"]["error"]["code"] == "57014" and r["deadline"]["error"]["deadline"] is True
    assert 1.9 < r["deadline"]["seconds"] < 8


@pytest.mark.parametrize("mode", MODES)
def test_the_row_cap_cancels(live: dict[str, Any], mode: str) -> None:
    r = live[mode]
    for name in ("cap_fast", "cap_live"):
        result = r[name]
        assert result.get("error") is None, (name, result)  # the cap's own cancel is no error
        (only,) = result["results"]
        assert len(only["rows"]) == 1000 and only["truncated"] is True, name
    assert r["cap_live"]["seconds"] < 20  # cancelled, not 100 s of pg_sleep
    (wide,) = r["cap_bytes"]["results"]
    assert wide["truncated"] is True and 400 < len(wide["rows"]) < 520  # 2 MiB of 4 KiB rows
    assert _rows(r["after_cap"]) == [[["4"]]]
    assert int(r["connections"]["results"][0]["rows"][0][0]) <= 2  # the role's limit

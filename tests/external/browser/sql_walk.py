"""The editor walk: a member signs in and uses the SQL editor on both doors, in a real Chromium.

Session 44 (ADR 0285, ADR 0286; D2736, D2743, D2750, D2758). Run inside the
pinned Playwright image by `~/s44/run6/s44-sql.sh` (never collected: no `test_`
prefix). It signs in as the probe owner (no new account, no rotation, D2758),
opens a project's SQL editor, and on the **pooled door** (`customer_app`, its
password from the creds file): reads `current_user` and `current_database()`,
sends the statement carrying the marker the host proof greps the relay's log
for (D2743), counts the role's connections (D2736), asks for a table in
`app_private` and records what PostgreSQL answered, cancels a `pg_sleep(30)`
with the page's Cancel button, reads 5,000 rows through the 1,000-row cap, and
times 20 `SELECT 1`; on the **direct door** (`customer_admin`) reads
`current_user` and the count. Then the relay's refusals from raw clients (a
foreign `Origin`, a name outside the grammar, a door name with no router), and
sign out. It writes ONE record the external proofs read through
`APG_SQL_EDITOR_RECORD_FILE`.

**The record holds no secret** (D2416, D2420): the console password, the TOTP
seed, both database passwords and the cookies stay in variables, and the
record's JSON is searched for each before it is written -- exit 6 if one is
there. The marker is not a secret; it is the canary.

`--rehearse` answers every `/api/v1` call from fixtures inside the page and the
relay's WebSocket from a fake PostgreSQL backend (a real SCRAM exchange against
the creds files, canned answers, a cancel by its own socket), so the editor's
DOM, `pg.js` in Chromium and this driver all run with no host. `--leak` makes a
fixture put a database password into the page, which the self-check must refuse.
`--dry` (E0) connects each door, runs one statement on each and the refusals.

Exit codes: 0 walked; 2 usage; 4 a step failed (the record says which);
6 the record would have held a secret.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import re
import secrets
import socket
import ssl
import statistics
import struct
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from console_walk import fresh_code, seed_of, totp, write_private
from playwright.sync_api import Page, Route, WebSocketRoute, sync_playwright

CODE = re.compile(r"\(([0-9A-Z]{5})\)$")
#: What the status line says while the editor is still working.
TRANSITIONAL = ("Connecting…", "Running…")


class Walk:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.record: dict[str, Any] = {"version": 1, "session": 44, "base": self.base, "steps": []}
        self.held: list[str] = []  # every secret value, for the self-check only

    def step(self, name: str, work: Any) -> Any:
        started = time.monotonic()
        try:
            result = work()
        except Exception as error:  # the record names the failed step, never a value
            self.record["steps"].append(
                {
                    "name": name,
                    "outcome": "failed",
                    "error": type(error).__name__,
                    "start": started,
                    "end": time.monotonic(),
                }
            )
            raise
        self.record["steps"].append(
            {"name": name, "outcome": "ok", "start": started, "end": time.monotonic()}
        )
        return result

    def self_check(self) -> None:
        text = json.dumps(self.record)
        leaked = [index for index, value in enumerate(self.held) if value and value in text]
        if leaked:
            print(
                f"sql_walk: the record would hold {len(leaked)} secret value(s); not written",
                file=sys.stderr,
            )
            raise SystemExit(6)


# ---------------------------------------------------------------------------
# --rehearse: the API answered inside the page, the door by a fake backend
# ---------------------------------------------------------------------------


def _message(kind: bytes, body: bytes) -> bytes:
    return kind + struct.pack("!i", len(body) + 4) + body


def _auth(code: int, rest: bytes = b"") -> bytes:
    return _message(b"R", struct.pack("!i", code) + rest)


def _error(code: str, text: str) -> bytes:
    return _message(b"E", b"SERROR\0VERROR\0C" + code.encode() + b"\0M" + text.encode() + b"\0\0")


def _rows(names: list[str], rows: list[list[str]], tag: str) -> bytes:
    described = b"".join(
        n.encode() + b"\0" + struct.pack("!ihihih", 0, 0, 25, -1, -1, 0) for n in names
    )
    out = _message(b"T", struct.pack("!h", len(names)) + described)
    for row in rows:
        cells = b"".join(struct.pack("!i", len(c.encode())) + c.encode() for c in row)
        out += _message(b"D", struct.pack("!h", len(row)) + cells)
    return out + _message(b"C", tag.encode() + b"\0")


READY = _message(b"Z", b"I")


class FakeBackend:
    """PostgreSQL's side of an editor session, as the rehearsal needs it."""

    def __init__(self, users: dict[str, str]) -> None:
        self.users = users  # user -> password, from the creds files
        self.sessions: dict[tuple[int, int], dict[str, Any]] = {}

    def handle(self, ws: WebSocketRoute) -> None:
        state: dict[str, Any] = {"stage": "startup", "ws": ws}
        ws.on_message(
            lambda message: self.receive(
                state, message if isinstance(message, bytes) else message.encode()
            )
        )

    def receive(self, state: dict[str, Any], data: bytes) -> None:
        ws = state["ws"]
        if state["stage"] == "startup":
            length, code = struct.unpack("!ii", data[:8])
            if length == 16 and code == 80877102:  # a CancelRequest on its own socket
                pid, key = struct.unpack("!ii", data[8:16])
                target = self.sessions.get((pid, key))
                if target and target.get("sleeping"):
                    target["sleeping"] = False
                    target["ws"].send(
                        _error("57014", "canceling statement due to user request") + READY
                    )
                ws.close()
                return
            fields = data[8:].split(b"\0")
            params = dict(zip(fields[0::2], fields[1::2], strict=False))
            state["user"] = params.get(b"user", b"").decode()
            state["database"] = params.get(b"database", b"").decode()
            state["stage"] = "sasl"
            ws.send(_auth(10, b"SCRAM-SHA-256\0\0"))
            return
        kind, body = data[:1], data[5:]
        if state["stage"] == "sasl":
            first = body[body.index(b"\0") + 5 :].decode()
            state["first_bare"] = first[3:]
            nonce = (
                state["first_bare"].split("r=", 1)[1]
                + base64.b64encode(secrets.token_bytes(18)).decode()
            )
            state["salt"] = secrets.token_bytes(16)
            state["server_first"] = f"r={nonce},s={base64.b64encode(state['salt']).decode()},i=4096"
            state["stage"] = "final"
            ws.send(_auth(11, state["server_first"].encode()))
            return
        if state["stage"] == "final":
            final = body.decode()
            without_proof, proof = final.rsplit(",p=", 1)
            password = self.users.get(state["user"], secrets.token_urlsafe(16))
            salted = hashlib.pbkdf2_hmac("sha256", password.encode(), state["salt"], 4096)
            client_key = hmac.new(salted, b"Client Key", "sha256").digest()
            stored = hashlib.sha256(client_key).digest()
            message = f"{state['first_bare']},{state['server_first']},{without_proof}".encode()
            signature = hmac.new(stored, message, "sha256").digest()
            recovered = bytes(
                a ^ b for a, b in zip(base64.b64decode(proof), signature, strict=True)
            )
            if hashlib.sha256(recovered).digest() != stored:
                ws.send(_error("08P01", "SASL authentication failed"))
                ws.close()
                return
            server_key = hmac.new(salted, b"Server Key", "sha256").digest()
            verifier = base64.b64encode(hmac.new(server_key, message, "sha256").digest())
            pid, key = secrets.randbelow(2**31), secrets.randbelow(2**31)
            self.sessions[(pid, key)] = state
            state["stage"] = "ready"
            ws.send(
                _auth(12, b"v=" + verifier)
                + _auth(0)
                + _message(b"K", struct.pack("!ii", pid, key))
                + READY
            )
            return
        if kind == b"X":
            ws.close()
            return
        if kind == b"Q":
            self.query(state, body.rstrip(b"\0").decode())

    def query(self, state: dict[str, Any], text: str) -> None:
        ws = state["ws"]
        if "current_database()" in text:
            ws.send(
                _rows(
                    ["current_user", "current_database"],
                    [[state["user"], state["database"]]],
                    "SELECT 1",
                )
                + READY
            )
        elif "pg_stat_activity" in text:
            ws.send(_rows(["count"], [["1"]], "SELECT 1") + READY)
        elif "app_private" in text:
            ws.send(_error("42501", "permission denied for schema app_private") + READY)
        elif "pg_sleep" in text:
            state["sleeping"] = True  # answered by the cancel
        elif "generate_series" in text:
            ws.send(
                _rows(["generate_series"], [[str(n)] for n in range(1, 5001)], "SELECT 5000")
                + READY
            )
        elif text.startswith("SELECT current_user"):
            ws.send(_rows(["current_user"], [[state["user"]]], "SELECT 1") + READY)
        else:
            ws.send(_rows(["?column?"], [["1"]], "SELECT 1") + READY)


class Fixtures:
    """Every `/api/v1` answer the editor walk meets, shaped from the control snapshot."""

    def __init__(
        self, project: str, probe: dict[str, str], doors: dict[str, str], leak: str
    ) -> None:
        self.project, self.probe, self.doors, self.leak = project, probe, doors, leak
        self.signed_in = False

    def handle(self, route: Route) -> None:
        request = route.request
        path = urlsplit(request.url).path.split("/api/v1", 1)[1]
        body = json.loads(request.post_data) if request.post_data else {}
        method = request.method
        status, answer, headers = 404, {"error": "not_found"}, {}
        if (method, path) == ("GET", "/me"):
            status, answer = (
                (
                    200,
                    {
                        "username": self.probe["username"],
                        "second_factor": {"required": True, "enabled": True},
                    },
                )
                if self.signed_in
                else (401, {"error": "authentication_failed"})
            )
        elif (method, path) == ("POST", "/sessions"):
            if body.get("password") != self.probe["password"]:
                status, answer = 401, {"error": "authentication_failed"}
            elif body.get("totp_code") != totp(seed_of(self.probe["totp_seed"]), time.time()):
                status, answer = 401, {"error": "second_factor_required"}
            else:
                self.signed_in = True
                status, answer = 200, {"expires_at": int(time.time()) + 900, "token_use": "access"}
                headers["set-cookie"] = (
                    f"__Host-apg_access={secrets.token_urlsafe(24)}; "
                    "HttpOnly; Secure; SameSite=Strict; Path=/"
                )
        elif (method, path) == ("GET", "/organizations"):
            name = self.leak or "probe-s37"
            status, answer = (
                200,
                {
                    "organizations": [
                        {
                            "id": "31121d7b-1aa3-4206-8f13-d81157c1beaf",
                            "name": name,
                            "role": "owner",
                        }
                    ]
                },
            )
        elif method == "GET" and path == "/projects":
            status, answer = (
                200,
                {"projects": [{"key": self.project, "state": "ready", "profile": "small"}]},
            )
        elif method == "GET" and path == f"/projects/{self.project}":
            status, answer = 200, {"key": self.project, "state": "ready", "profile": "small"}
        elif method == "GET" and path == f"/projects/{self.project}/connections":
            door = {
                "port": 5432,
                "database": "slot3_prod",
                "sslmode": "verify-full",
                "connection_limit": 2,
            }
            status, answer = (
                200,
                {
                    "project": self.project,
                    "pooled": {
                        **door,
                        "host": "pool.slot3.rehearsal.test",
                        "user": self.doors["pooled"],
                    },
                    "direct": {
                        **door,
                        "host": "direct.slot3.rehearsal.test",
                        "user": self.doors["direct"],
                    },
                    "password": "<password from your file>",
                    "snippets": {},
                },
            )
        elif (method, path) == ("DELETE", "/sessions/current"):
            self.signed_in = False
            route.fulfill(
                status=204, headers={"set-cookie": "__Host-apg_access=; Max-Age=0; Path=/; Secure"}
            )
            return
        route.fulfill(
            status=status,
            body=json.dumps(answer),
            headers={"content-type": "application/json", **headers},
        )


# ---------------------------------------------------------------------------
# The relay, from raw clients (no browser: a browser cannot send a foreign Origin)
# ---------------------------------------------------------------------------


def _handshake(host: str, path: str, origin: str) -> tuple[ssl.SSLSocket, bytes, bytes]:
    raw = socket.create_connection((host, 443), timeout=30)
    tls = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    request = (
        f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {base64.b64encode(secrets.token_bytes(16)).decode()}\r\n"
        f"Sec-WebSocket-Version: 13\r\nOrigin: {origin}\r\n\r\n"
    )
    tls.sendall(request.encode())
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = tls.recv(4096)
        if not chunk:
            break
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    return tls, head.split(b"\r\n", 1)[0], rest


def relay_status(host: str, path: str, origin: str) -> int:
    tls, status, _ = _handshake(host, path, origin)
    tls.close()
    return int(status.split()[1])


def relay_close_code(host: str, path: str, origin: str) -> int | None:
    """Upgrade, then read frames until the relay closes; its close code."""
    tls, status, buffer = _handshake(host, path, origin)
    if int(status.split()[1]) != 101:
        tls.close()
        return None
    deadline = time.monotonic() + 45
    try:
        while time.monotonic() < deadline:
            while len(buffer) < 2:
                buffer += tls.recv(4096)
            opcode, length = buffer[0] & 0x0F, buffer[1] & 0x7F
            offset = 2
            if length == 126:
                length, offset = struct.unpack("!H", buffer[2:4])[0], 4
            while len(buffer) < offset + length:
                buffer += tls.recv(4096)
            payload, buffer = buffer[offset : offset + length], buffer[offset + length :]
            if opcode == 0x8:
                return struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else None
    finally:
        tls.close()
    return None


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------


def settle(page: Page, *, timeout: float = 90) -> str:
    """The status line once the editor has finished what it was asked."""
    status = page.get_by_role("status")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = status.inner_text().strip()
        if text and text not in TRANSITIONAL:
            return text
        page.wait_for_timeout(50)
    raise TimeoutError("the editor did not settle")


def tables(page: Page) -> list[list[list[str]]]:
    out = []
    for table in page.locator("#main section.result table").all():
        out.append(
            [
                [cell.inner_text() for cell in row.locator("td").all()]
                for row in table.locator("tbody tr").all()
            ]
        )
    return out


def walk(arguments: argparse.Namespace) -> int:
    probe = json.loads(Path(arguments.probe_file).read_text(encoding="utf-8"))
    probe["password"] = Path(probe["password_file"]).read_text(encoding="utf-8").strip()
    creds = Path(arguments.creds_dir)
    passwords = {
        role: (creds / role).read_text(encoding="utf-8").strip()
        for role in ("customer_app", "customer_admin")
    }
    walker = Walk(arguments.base)
    walker.held += [probe["password"], probe["totp_seed"], *passwords.values()]
    walker.record.update(
        {
            "project": arguments.project,
            "source_commit": arguments.source_commit,
            "mode": "rehearsal" if arguments.rehearse else "live",
            "dry": bool(arguments.dry),
            "account": probe["username"],
        }
    )
    marker = f"apg-s44-{secrets.token_hex(6)}"
    walker.record["marker"] = marker
    exit_code = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        walker.record["chromium"] = browser.version
        context = browser.new_context()
        backend = None
        if arguments.rehearse:
            doors = {
                "pooled": "apg_slot3_prod_customer_app",
                "direct": "apg_slot3_prod_customer_admin",
            }
            leak = passwords["customer_app"] if arguments.leak else ""
            context.route(
                f"{walker.base}/api/v1/**", Fixtures(arguments.project, probe, doors, leak).handle
            )
            backend = FakeBackend(
                {
                    doors["pooled"]: passwords["customer_app"],
                    doors["direct"]: passwords["customer_admin"],
                }
            )
            context.route_web_socket(re.compile(r"^wss://sql\.rehearsal\.test/"), backend.handle)
        page = context.new_page()
        try:
            started = time.monotonic()

            def sign_in() -> None:
                page.goto(f"{walker.base}/console/#/sign-in")
                page.get_by_label("Username").fill(probe["username"])
                page.get_by_label("Password").fill(probe["password"])
                page.get_by_role("button", name="Sign in").click()
                page.get_by_label("Code from your app").wait_for()
                code, _ = fresh_code(seed_of(probe["totp_seed"]))
                page.get_by_label("Code from your app").fill(code)
                page.get_by_role("button", name="Sign in").click()
                page.get_by_role("heading", name="Overview").wait_for()

            walker.step("sign in", sign_in)
            # What the page showed, as the console walk records it: a fixture that put a
            # secret into the page would put it here, and the self-check refuses that.
            walker.record["overview"] = [h.inner_text() for h in page.locator("#main h2").all()]
            walker.held += [cookie["value"] for cookie in context.cookies()]
            environment = context.request.get(f"{walker.base}/console/env.json").json()
            walker.record["relay"] = environment.get("sql_relay")
            connections = {}

            def open_editor() -> None:
                with page.expect_response(
                    lambda r: r.url.endswith(f"/projects/{arguments.project}/connections")
                ) as answered:
                    page.goto(f"{walker.base}/console/#/projects/{arguments.project}/sql")
                connections.update(answered.value.json())
                page.get_by_role("button", name="Connect", exact=True).wait_for()

            walker.step("open the editor", open_editor)
            walker.record["doors"] = {
                name: {
                    key: connections[name][key]
                    for key in ("host", "port", "user", "database", "connection_limit")
                }
                for name in ("pooled", "direct")
            }

            def connect_door(name: str, password: str) -> str:
                page.get_by_label("Door").select_option(name)
                page.get_by_label("Password").fill(password)
                page.get_by_role("button", name="Connect", exact=True).click()
                said = settle(page)
                walker.record.setdefault("password_field_cleared", []).append(
                    page.get_by_label("Password").input_value() == ""
                )
                if not said.startswith("Connected"):
                    raise RuntimeError("not connected")
                return said

            def run(text: str) -> dict[str, Any]:
                page.locator("#main textarea").fill(text)
                began = time.monotonic()
                page.get_by_role("button", name="Run").click()
                said = settle(page)
                found = CODE.search(said)
                return {
                    "status": said if not found else None,
                    "code": found.group(1) if found else None,
                    "seconds": round(time.monotonic() - began, 3),
                    "tables": tables(page),
                    "truncated": page.get_by_text("Showing the first 1,000 rows").count() > 0,
                }

            readings: dict[str, Any] = {}
            walker.record["pooled"] = readings
            walker.step(
                "connect the pooled door", lambda: connect_door("pooled", passwords["customer_app"])
            )
            readings["identity"] = walker.step(
                "pooled: who am I", lambda: run("SELECT current_user, current_database()")
            )
            walker.record["sign_in_to_first_result_seconds"] = round(time.monotonic() - started, 1)
            readings["marker"] = walker.step(
                "pooled: the marker", lambda: run(f"SELECT 1 /* {marker} */")
            )
            readings["connections"] = walker.step(
                "pooled: the role's connections",
                lambda: run("SELECT count(*) FROM pg_stat_activity WHERE usename = current_user"),
            )
            if not arguments.dry:
                readings["app_private"] = walker.step(
                    "pooled: app_private refused",
                    lambda: run("SELECT * FROM app_private.migration_ledger LIMIT 1"),
                )

                def cancel() -> dict[str, Any]:
                    page.locator("#main textarea").fill("SELECT pg_sleep(30)")
                    began = time.monotonic()
                    page.get_by_role("button", name="Run").click()
                    page.wait_for_timeout(1000)
                    page.get_by_role("button", name="Cancel").click()
                    said = settle(page)
                    found = CODE.search(said)
                    return {
                        "code": found.group(1) if found else None,
                        "seconds": round(time.monotonic() - began, 3),
                    }

                readings["cancel"] = walker.step("pooled: Cancel stops pg_sleep(30)", cancel)
                readings["cap"] = walker.step(
                    "pooled: 5,000 rows capped", lambda: run("SELECT generate_series(1, 5000)")
                )
                readings["cap"]["rows"] = (
                    len(readings["cap"].pop("tables")[0]) if readings["cap"].get("tables") else 0
                )
                timings = [
                    walker.step(f"pooled: SELECT 1 #{i + 1}", lambda: run("SELECT 1"))["seconds"]
                    for i in range(20)
                ]
                readings["select1_seconds"] = timings
                readings["select1_median"] = statistics.median(timings)
            walker.step("disconnect", lambda: page.get_by_role("button", name="Disconnect").click())
            direct: dict[str, Any] = {}
            walker.record["direct"] = direct
            walker.step(
                "connect the direct door",
                lambda: connect_door("direct", passwords["customer_admin"]),
            )
            direct["identity"] = walker.step("direct: who am I", lambda: run("SELECT current_user"))
            direct["connections"] = walker.step(
                "direct: the role's connections",
                lambda: run("SELECT count(*) FROM pg_stat_activity WHERE usename = current_user"),
            )
            walker.step(
                "disconnect the direct door",
                lambda: page.get_by_role("button", name="Disconnect").click(),
            )
            if not arguments.rehearse:
                relay = urlsplit(walker.record["relay"]).hostname
                pooled_host = walker.record["doors"]["pooled"]["host"]
                zone = pooled_host.split(".", 2)[2]
                walker.record["refusals"] = walker.step(
                    "the relay's refusals",
                    lambda: {
                        "foreign_origin": relay_status(
                            relay, f"/v1/door/{pooled_host}", "https://evil.example"
                        ),
                        "outside_the_grammar": relay_status(relay, f"/v1/door/{zone}", walker.base),
                        "unrouted_door": relay_close_code(
                            relay, f"/v1/door/pool.slot99.{zone}", walker.base
                        ),
                    },
                )

            def sign_out() -> None:
                page.goto(f"{walker.base}/console/")
                page.get_by_role("button", name="Sign out").click()
                page.get_by_role("heading", name="Sign in").wait_for()

            walker.step("sign out", sign_out)
            walker.record["seconds"] = round(time.monotonic() - started, 1)
        except Exception as error:
            failed = walker.record["steps"][-1]["name"] if walker.record["steps"] else "-"
            print(
                f"sql_walk: step {failed!r} failed: {str(error).splitlines()[0][:300]}",
                file=sys.stderr,
            )
            exit_code = 4
        finally:
            browser.close()
    walker.record["exit"] = exit_code
    walker.self_check()
    write_private(
        Path(arguments.record), json.dumps(walker.record, indent=1, sort_keys=True) + "\n"
    )
    print(f"sql_walk: {walker.record['mode']} walk exit {exit_code}; record {arguments.record}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sql_walk", allow_abbrev=False)
    parser.add_argument(
        "--probe-file", required=True, help="the probe owner's file (~/s37/probe.json)"
    )
    parser.add_argument(
        "--creds-dir", required=True, help="customer_app and customer_admin, one password each"
    )
    parser.add_argument("--record", required=True)
    parser.add_argument("--base", required=True, help="the console's origin")
    parser.add_argument("--project", default="slot3-prod")
    parser.add_argument(
        "--source-commit", required=True, help="the control project's deployed commit"
    )
    parser.add_argument(
        "--dry", action="store_true", help="E0: one statement per door and the refusals"
    )
    parser.add_argument("--rehearse", action="store_true")
    parser.add_argument(
        "--leak",
        action="store_true",
        help="rehearsal: a fixture puts a database password in the page",
    )
    arguments = parser.parse_args(argv)
    if arguments.leak and not arguments.rehearse:
        parser.error("--leak is a rehearsal fixture")
    return walk(arguments)


if __name__ == "__main__":
    raise SystemExit(main())

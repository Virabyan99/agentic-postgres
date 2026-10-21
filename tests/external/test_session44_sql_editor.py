"""Session 44's customer proofs: the SQL editor and its relay, from the outside.

`SQL-LIVE-001` (claim `sql_editor_live`) reads the editor walk's record
(`APG_SQL_EDITOR_RECORD_FILE`, written by `tests/external/browser/sql_walk.py`
in a real Chromium against the deployed console): a member signed in, opened
`slot3-prod`'s editor, and on each door PostgreSQL answered as that door's role;
a table in `app_private` was refused BY POSTGRESQL; the page's Cancel stopped a
`pg_sleep(30)`; 5,000 rows arrived capped at 1,000; the role's connections stayed
inside its limit; the times were recorded. `SQL-LIVE-002` (claim
`sql_relay_live`) asks the relay itself, now, through its public name, with raw
clients a browser could not be (a foreign `Origin`, a name outside the grammar, a
door name nothing routes) and reads the console's policy naming the relay.
**No SSH, no process door** (D2174). **None of these proofs has ever executed.**
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

import ast
import base64
import json
import os
import re
import secrets
import socket
import ssl
import stat
import struct
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from tests.external.test_session38_public_lifecycle import (  # noqa: F401 -- fixtures
    control,
    endpoint,
)

from agentic_postgres import naming

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_SQL_EDITOR_RECORD_FILE", "APG_CONTROL_OUTPUTS"),
]

#: The project the walk used: the KEPT customer project.
PROJECT = "slot3-prod"
#: The walk's steps that must all have run, in the driver's names.
STEPS = (
    "sign in",
    "open the editor",
    "connect the pooled door",
    "pooled: who am I",
    "pooled: the marker",
    "pooled: the role's connections",
    "pooled: app_private refused",
    "pooled: Cancel stops pg_sleep(30)",
    "pooled: 5,000 rows capped",
    "disconnect",
    "connect the direct door",
    "direct: who am I",
    "direct: the role's connections",
    "disconnect the direct door",
    "sign out",
)
USER_AGENT = {"User-Agent": "agentic-postgres-proof"}  # D2728


@pytest.fixture(scope="module")
def console_origin(endpoint: str) -> str:
    return naming.console_origin(str(urlsplit(endpoint).hostname))


@pytest.fixture(scope="module")
def relay_host(console_origin: str) -> str:
    return naming.sql_relay_host(str(urlsplit(console_origin).hostname))


@pytest.fixture(scope="module")
def walk(control: dict[str, Any], console_origin: str) -> dict[str, Any]:
    """The editor walk's record: private, live, Session 44's, at the console's
    origin, about the commit the control project is deployed at, walked whole."""
    path = Path(os.environ.get("APG_SQL_EDITOR_RECORD_FILE", ""))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert (document.get("session"), document.get("mode")) == (44, "live"), (
        document.get("session"), document.get("mode"),
    )  # fmt: skip
    assert document.get("base") == console_origin, (document.get("base"), console_origin)
    assert document.get("source_commit") == control["source_commit"], (
        f"the walk ran against {document.get('source_commit')}, the control project is at "
        f"{control['source_commit']}: a record from another release"
    )
    assert document.get("project") == PROJECT, document.get("project")
    assert document.get("dry") is False, "a dry run's record (E0), not the walk's (E1)"
    return document


# -- SQL-LIVE-001: the walk -----------------------------------------------------


def test_the_editor_walk_reached_every_step(walk: dict[str, Any]) -> None:
    ran = {step["name"]: step["outcome"] for step in walk["steps"]}
    assert walk["exit"] == 0, walk["exit"]
    for name in STEPS:
        assert ran.get(name) == "ok", (name, ran.get(name))
    assert sum(1 for name in ran if name.startswith("pooled: SELECT 1 #")) == 20
    assert all(outcome == "ok" for outcome in ran.values()), ran
    assert re.fullmatch(r"apg-s44-[0-9a-f]{12}", walk["marker"]), walk["marker"]


def test_each_door_answered_as_its_role(walk: dict[str, Any]) -> None:
    """`current_user` on each door is that door's role from the connections
    answer -- `apg_<key>_customer_app` pooled, `…_customer_admin` direct (ADR
    0269) -- and the database is the door's; the password field was empty again
    each time the page read it (D2756)."""
    doors = walk["doors"]
    key_sql = PROJECT.replace("-", "_")
    assert doors["pooled"]["user"] == f"apg_{key_sql}_customer_app", doors["pooled"]["user"]
    assert doors["direct"]["user"] == f"apg_{key_sql}_customer_admin", doors["direct"]["user"]
    (pooled,) = walk["pooled"]["identity"]["tables"]
    assert pooled == [[doors["pooled"]["user"], doors["pooled"]["database"]]], pooled
    (direct,) = walk["direct"]["identity"]["tables"]
    assert direct == [[doors["direct"]["user"]]], direct
    assert walk["password_field_cleared"] == [True, True], walk["password_field_cleared"]
    assert walk["pooled"]["marker"]["tables"] == [[["1"]]]


def test_postgres_decided_the_refusal(walk: dict[str, Any]) -> None:
    """The customer's role asked for `app_private`: PostgreSQL refused it with a
    SQLSTATE of its own -- an access rule (class 42) or a missing schema (3F) --
    and no row came back. Whatever code it was is the record's, not a guess."""
    refused = walk["pooled"]["app_private"]
    code = refused["code"]
    assert code is not None and re.fullmatch(r"[0-9A-Z]{5}", code), refused
    assert code[:2] in ("42", "3F"), code
    assert refused["tables"] == [], refused["tables"]


def test_the_cancel_stopped_the_statement(walk: dict[str, Any]) -> None:
    cancel = walk["pooled"]["cancel"]
    assert cancel["code"] == "57014", cancel
    assert cancel["seconds"] < 15, cancel  # pg_sleep(30), cancelled ~1 s in


def test_the_rows_were_capped(walk: dict[str, Any]) -> None:
    cap = walk["pooled"]["cap"]
    assert cap["rows"] == 1000 and cap["truncated"] is True, cap
    assert cap["code"] is None, cap  # the cap's own cancel is no error (D2766)


def test_the_role_stayed_inside_its_limit(walk: dict[str, Any]) -> None:
    """D2736: the editor adds no claimant -- the role's own connection count,
    read by the editor during its session, within the door's limit."""
    for door in ("pooled", "direct"):
        ((count,),) = walk[door]["connections"]["tables"][0]
        limit = walk["doors"][door]["connection_limit"]
        assert 1 <= int(count) <= limit, (door, count, limit)


def test_the_times_were_recorded(walk: dict[str, Any]) -> None:
    """D2750's readings, named as the workstation's: 20 round trips through the
    editor, their median, sign-in to the first result, the whole walk."""
    times = walk["pooled"]["select1_seconds"]
    assert len(times) == 20 and all(0 < value < 30 for value in times), times
    assert 0 < walk["pooled"]["select1_median"] < 30
    assert 0 < walk["sign_in_to_first_result_seconds"] < walk["seconds"]
    assert walk["chromium"], walk.get("chromium")


# -- SQL-LIVE-002: the relay, asked now ---------------------------------------


def _handshake(host: str, path: str, origin: str) -> tuple[ssl.SSLSocket, int, bytes]:
    raw = socket.create_connection((host, 443), timeout=30)
    tls = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    tls.sendall(
        (
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {base64.b64encode(secrets.token_bytes(16)).decode()}\r\n"
            f"Sec-WebSocket-Version: 13\r\nOrigin: {origin}\r\n\r\n"
        ).encode()
    )
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = tls.recv(4096)
        if not chunk:
            break
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    return tls, int(head.split(b"\r\n", 1)[0].split()[1]), rest


def _pooled(control: dict[str, Any]) -> tuple[str, str]:
    """slot3's pooled door name and its zone, derived as the console derives them."""
    zone = naming.sql_relay_zone(str(urlsplit(control["routes"]["control"]).hostname))
    return f"pool.slot3.{zone}", zone


def test_a_foreign_origin_is_refused_live(
    relay_host: str, control: dict[str, Any], console_origin: str
) -> None:
    pooled, _zone = _pooled(control)
    tls, status, _ = _handshake(relay_host, f"/v1/door/{pooled}", "https://evil.example")
    tls.close()
    assert status == 403, status
    tls, status, _ = _handshake(relay_host, f"/v1/door/{pooled}", console_origin)  # the control
    tls.close()
    assert status == 101, status


def test_a_name_outside_the_grammar_is_refused_live(
    relay_host: str, control: dict[str, Any], console_origin: str
) -> None:
    _pooled_name, zone = _pooled(control)
    for door in (zone, f"control.{zone}", "15.204.231.45", f"pool.slot3.{zone}:5432", "localhost"):
        tls, status, _ = _handshake(relay_host, f"/v1/door/{door}", console_origin)
        tls.close()
        assert status == 400, (door, status)


def test_an_unrouted_door_is_unreachable_live(
    relay_host: str, control: dict[str, Any], console_origin: str
) -> None:
    """A name in the grammar that nothing routes closes 4502 -- the same
    handshake refusal a sleeping door gives (ADR 0268 :73), and never *asleep*."""
    _pooled_name, zone = _pooled(control)
    tls, status, buffer = _handshake(relay_host, f"/v1/door/pool.slot99.{zone}", console_origin)
    assert status == 101, status
    code = None
    deadline = time.monotonic() + 45
    try:
        while code is None and time.monotonic() < deadline:
            while len(buffer) < 2:
                buffer += tls.recv(4096)
            opcode, length = buffer[0] & 0x0F, buffer[1] & 0x7F
            while len(buffer) < 2 + length:
                buffer += tls.recv(4096)
            payload, buffer = buffer[2 : 2 + length], buffer[2 + length :]
            if opcode == 0x8:
                code = struct.unpack("!H", payload[:2])[0]
                assert b"asleep" not in payload, payload
    finally:
        tls.close()
    assert code == 4502, code


def test_the_console_policy_names_the_relay(console_origin: str, relay_host: str) -> None:
    request = urllib.request.Request(f"{console_origin}/console/", headers=USER_AGENT)  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as answer:  # noqa: S310 -- https, derived
        policy = answer.headers.get("Content-Security-Policy", "")
    connect = [part.strip() for part in policy.split(";") if part.strip().startswith("connect-src")]
    assert connect == [f"connect-src 'self' wss://{relay_host}"], connect
    request = urllib.request.Request(f"{console_origin}/console/env.json", headers=USER_AGENT)  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as answer:  # noqa: S310
        assert json.loads(answer.read())["sql_relay"] == f"wss://{relay_host}"


def test_the_relay_certificate_names_its_host(relay_host: str) -> None:
    with socket.create_connection((relay_host, 443), timeout=30) as raw:
        with ssl.create_default_context().wrap_socket(raw, server_hostname=relay_host) as tls:
            names = [
                value
                for kind, value in tls.getpeercert().get("subjectAltName", ())
                if kind == "DNS"
            ]
    assert relay_host in names, names
    request = urllib.request.Request(f"https://{relay_host}/__apg/healthz", headers=USER_AGENT)
    with urllib.request.urlopen(request, timeout=30) as answer:  # noqa: S310
        assert answer.status == 200 and json.loads(answer.read()) == {"status": "ok"}


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof: nothing here reaches the host but by
    its public names. Read from this file's own text and syntax."""
    text = Path(__file__).read_text(encoding="utf-8")
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    tree = ast.parse(text)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "subprocess" not in imported, imported

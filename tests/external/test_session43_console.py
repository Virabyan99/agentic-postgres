"""Session 43's customer proofs: the console walked in a browser, its policy, the site.

The claims `console_walk_live` (CON-LIVE-001), `console_csrf_live` (CON-LIVE-002)
and `site_live` (SITE-LIVE-001); ADR 0280-0283, D2668, D2675, D2687. Run from
the workstation, never the host, with no SSH, AFTER the walk (Sheet W1):
`tests/external/browser/console_walk.py` drove a real Chromium from an
invitation link to a working connection string and wrote ONE record
(`APG_CONSOLE_RECORD_FILE`, 0600) -- statuses, times, flags and headers, never
a value (its own self-check refuses to write one) -- and the rotated
`customer_app` password beside it in the file the record names (0600).

**These proofs read that record and ask the deployment again** through the
control project's `routes.control`, the console's origin and the site's two
names; the connection proof opens the pooled door on 5432. The CSRF readings
were taken by the driver with the walker's REAL session (Playwright's
`context.request` shares the context's cookies, so no cookie value ever left
it); the forged-cookie request below is this module's own. **None of these
proofs has ever executed.**
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

import ast
import importlib.util
import json
import os
import stat
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import psycopg
import pytest
from tests.external.redaction import Secret
from tests.external.test_session38_public_lifecycle import (  # noqa: F401 -- fixtures
    TIMEOUT,
    Recorder,
    _only,
    control,
    endpoint,
    owner,
    probe,
    recorder,
)
from tests.external.test_session39_public_endpoints import ROOTS

from agentic_postgres import naming, site_build

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONSOLE_RECORD_FILE", "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE"
    ),
]

#: The walk's steps, in the order the driver takes them (ADR 0280; D2675's
#: three paints first, each in a fresh context).
STEPS = (
    "paint 1",
    "paint 2",
    "paint 3",
    "open the invitation link",
    "create the account",
    "enrol the second factor",
    "sign in with the next code",
    "the live CSRF readings",
    "rotate customer_app from Connect",
    "reload: the password is gone",
    "sign out",
)

#: The project the walk rotated: the KEPT customer project (§2 of CLAUDE.md).
PROJECT = "slot3-prod"

#: ADR 0281: the two session cookies.
COOKIES = ("__Host-apg_access", "__Host-apg_refresh")

#: D2687: a read before propagation is not a reading.
SETTLED = 5


def _console_policy() -> dict[str, str]:
    """`services/console/serve.py`'s headers, loaded from the file the image copies."""
    specification = importlib.util.spec_from_file_location(
        "apg_console_serve_policy", REPO_ROOT / "services" / "console" / "serve.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return dict(module.SECURITY_HEADERS)


def _get(recorder: Recorder, url: str, headers: dict[str, str] | None = None,
         method: str = "GET") -> tuple[int, dict[str, str], bytes]:  # fmt: skip
    """One request through the recorder's opener (no redirect followed), with
    the answer's headers -- `Recorder.send` keeps only status and body."""
    parts = urlsplit(url)
    recorder.seen.append((parts.scheme, parts.hostname or ""))
    request = urllib.request.Request(url, method=method)  # noqa: S310
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with recorder.opener.open(request, timeout=TIMEOUT) as response:
            return (
                response.status,
                {k.lower(): v for k, v in response.headers.items()},
                response.read(),
            )
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()


def _settled(recorder: Recorder, url: str) -> tuple[dict[str, str], bytes]:
    """D2687: five consecutive 200s, then the reading (the last of them);
    bounded at a minute, never an unbounded retry."""
    streak, deadline = 0, time.monotonic() + 60
    while time.monotonic() < deadline:
        status, headers, body = _get(recorder, url)
        streak = streak + 1 if status == 200 else 0
        if streak >= SETTLED:
            return headers, body
        time.sleep(1)
    pytest.fail(f"{url} did not answer {SETTLED} consecutive 200s within a minute")


class _Page(HTMLParser):
    """The parts of a built page these proofs read."""

    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.assets: list[str] = []
        self.links: list[str] = []
        self.sections: dict[str, list[list[str]]] = {}
        self.paragraphs: list[str] = []
        self._section: str | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._paragraph: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "meta" and "name" in values:
            self.meta[values["name"]] = values.get("content", "")
        if tag in ("script", "img") and "src" in values:
            self.assets.append(values["src"])
        if tag == "link" and "href" in values:
            self.assets.append(values["href"])
        if tag == "a" and "href" in values:
            self.links.append(values["href"])
        if tag == "h2":
            self._section = values.get("id")
            self.sections.setdefault(str(self._section), [])
        if tag == "tr":
            self._row = []
        if tag == "td" and self._row is not None:
            self._cell = []
        if tag == "p":
            self._paragraph = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        if tag == "tr" and self._row is not None:
            if self._row and self._section is not None:
                self.sections[self._section].append(self._row)
            self._row = None
        if tag == "p" and self._paragraph is not None:
            self.paragraphs.append("".join(self._paragraph).strip())
            self._paragraph = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
        if self._paragraph is not None:
            self._paragraph.append(data)


def _parse(body: bytes) -> _Page:
    page = _Page()
    page.feed(body.decode("utf-8"))
    return page


@pytest.fixture(scope="module")
def console_origin(endpoint: str) -> str:
    """The console's origin, derived from the control route's host (ADR 0280)."""
    return naming.console_origin(str(urlsplit(endpoint).hostname))


@pytest.fixture(scope="module")
def walk(control: dict[str, Any], console_origin: str) -> dict[str, Any]:
    """The walk's record: private, live, Session 43's, at the console's origin,
    about the commit the control project is deployed at, and walked to its end."""
    recorded = os.environ.get("APG_CONSOLE_RECORD_FILE", "")
    path = Path(recorded)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert (document.get("session"), document.get("mode")) == (43, "live"), (
        document.get("session"), document.get("mode"),
    )  # fmt: skip
    assert document.get("base") == console_origin, (document.get("base"), console_origin)
    assert document.get("source_commit") == control["source_commit"], (
        f"the walk ran against {document.get('source_commit')}, the control project is at "
        f"{control['source_commit']}: a record from another release"
    )
    assert document.get("project") == PROJECT, document.get("project")
    assert "dry" not in document, "a dry run's record (W0), not the walk's (W1)"
    return document


@pytest.fixture(scope="module")
def rotated() -> Secret:
    """The password the page showed, from the 0600 file the record names --
    beside the record, never inside it; a `Secret`, so no failure prints it."""
    recorded = Path(os.environ.get("APG_CONSOLE_RECORD_FILE", ""))
    document = json.loads(recorded.read_text(encoding="utf-8"))
    path = recorded.with_name(str(document.get("password_file")))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
    return Secret(path.read_text(encoding="utf-8").strip("\n"))


# ---------------------------------------------------------------------------
# CON-LIVE-001: the walk
# ---------------------------------------------------------------------------


def test_the_walk_reached_every_step(walk: dict[str, Any]) -> None:
    """Every step, in order, each `ok`, and the driver's own exit 0: a link to
    an account, a confirmed factor, a session, Connect, the rotation, sign-out."""
    assert walk.get("exit") == 0, walk.get("exit")
    assert [(s["name"], s["outcome"]) for s in walk["steps"]] == [(n, "ok") for n in STEPS]
    assert walk.get("address_bar_clean") is True, "the token stayed in the address bar"
    assert walk.get("overview"), "the overview named no organisation"


def test_the_password_was_shown_once(walk: dict[str, Any]) -> None:
    """The page showed the password inside its connection string, and a reload
    of the same view no longer held it (ADR 0280: shown once, dropped on leaving)."""
    assert walk.get("string_holds_the_password") is True
    assert walk.get("password_gone_after_reload") is True
    assert walk.get("string_parameters", {}).get("sslmode") == "verify-full", walk.get(
        "string_parameters"
    )


def test_the_string_from_the_page_connects(
    walk: dict[str, Any], endpoint: str, owner: str, rotated: Secret, recorder: Recorder
) -> None:
    """The string's door is the one `/v1` serves for the project, and the
    password the page showed opens it over TLS, verified against the system
    roots -- `SELECT 1` as `customer_app`."""
    status, served = recorder.json("GET", f"{endpoint}/projects/{PROJECT}/connections", None, owner)
    assert status == 200, (status, served.get("error"))
    _only(recorder, endpoint)
    pooled = served["pooled"]
    shown = (walk["pooled_host"], walk["string_port"], walk["string_user"],
             walk["string_database"])  # fmt: skip
    assert shown == (pooled["host"], pooled["port"], pooled["user"], pooled["database"]), (
        shown, pooled,
    )  # fmt: skip
    with psycopg.connect(
        host=pooled["host"], port=pooled["port"], dbname=pooled["database"],
        user=pooled["user"], password=rotated, sslmode="verify-full",
        sslrootcert=str(ROOTS), connect_timeout=15, autocommit=True,
    ) as connection:  # fmt: skip
        assert connection.execute("select 1").fetchone() == (1,)


def test_the_times_were_recorded(walk: dict[str, Any]) -> None:
    """Three first paints, each in a fresh context (D2675), and the link-to-
    string time; every step's monotonic times in order."""
    paints = walk.get("paint") or []
    assert len(paints) == 3, paints
    for reading in paints:
        assert isinstance(reading.get("fcp"), (int, float)) and reading["fcp"] > 0, reading
    seconds = walk.get("link_to_string_seconds")
    assert isinstance(seconds, (int, float)) and seconds > 0, seconds
    previous = 0.0
    for step in walk["steps"]:
        assert previous <= step["start"] <= step["end"], step
        previous = step["end"]


# ---------------------------------------------------------------------------
# CON-LIVE-002: the policy and the CSRF rule, live
# ---------------------------------------------------------------------------


def test_the_public_answers_carry_the_policy(
    walk: dict[str, Any], console_origin: str, recorder: Recorder
) -> None:
    """`/console/` and `/accept` answer the server's exact headers -- as the
    browser read them during the walk, and as this proof reads them now."""
    policy = {name.lower(): value for name, value in _console_policy().items()}
    for path in ("/console/", "/accept"):
        seen = walk["headers"][path]
        for name in ("content-security-policy", "x-frame-options", "referrer-policy",
                     "x-content-type-options", "cache-control"):  # fmt: skip
            assert seen.get(name) == policy[name], (path, name, seen.get(name))
        status, headers, _ = _get(recorder, f"{console_origin}{path}")
        assert status == 200, (path, status)
        for name, value in policy.items():
            assert headers.get(name) == value, (path, name, headers.get(name))
        assert "access-control-allow-origin" not in headers, (path, headers)
    _only(recorder, console_origin)


def test_a_cookie_alone_is_refused_live(
    walk: dict[str, Any], endpoint: str, recorder: Recorder
) -> None:
    """The walker's real cookie without `X-Apg-Console` read 401 (the driver's
    reading); a forged access cookie WITH the header reads 401 (this proof's)."""
    assert walk["csrf"]["no_header"] == 401, walk["csrf"]
    status, headers, _ = _get(recorder, f"{endpoint}/me", {
        "Cookie": "__Host-apg_access=x", "X-Apg-Console": "1", "Accept": "application/json",
    })  # fmt: skip
    assert status == 401, status
    assert "access-control-allow-origin" not in headers, headers
    _only(recorder, endpoint)


def test_a_foreign_origin_write_is_refused_live(walk: dict[str, Any]) -> None:
    """A sign-out with the real cookie and the header but another `Origin` read
    401, and the session SURVIVED it (the control: `/me` 200 after); the page's
    own sign-out read 204 and left neither cookie."""
    csrf = walk["csrf"]
    assert (csrf["foreign_origin_logout"], csrf["after_forged_logout"]) == (401, 200), csrf
    assert csrf.get("sign_out") == 204, csrf
    assert walk.get("cookies_after_sign_out") == 0, walk.get("cookies_after_sign_out")


def test_the_cookies_were_strict(walk: dict[str, Any]) -> None:
    """Both session cookies, by name and flags only -- never a value."""
    assert walk["cookies"] == [
        {"name": name, "httpOnly": True, "secure": True, "sameSite": "Strict"} for name in COOKIES
    ], walk["cookies"]


# ---------------------------------------------------------------------------
# SITE-LIVE-001: the site is this commit's build
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built() -> dict[str, bytes]:
    return site_build.build()


def _routes(built: dict[str, bytes]) -> list[str]:
    return sorted("/" + name.removesuffix("index.html") for name in built
                  if name.endswith("index.html"))  # fmt: skip


def test_the_site_is_the_commits_build(built: dict[str, bytes], recorder: Recorder) -> None:
    """Every page on the apex and on `www` IS this tree's build, byte for byte --
    so nothing between the build and the reader rewrote it (D2720: the zone's
    email obfuscation injected a same-origin script, which a check of hosts
    alone passes) -- names the build digest recomputed from this tree, and
    carries the site's policy; the 404 page is the build's."""
    digest = site_build.digest()
    origins = (site_build.SITE_URL, "https://www.agenticpostgresql.com")
    for origin in origins:
        for route in _routes(built):
            headers, body = _settled(recorder, f"{origin}{route}")
            assert body == built[route.lstrip("/") + "index.html"], (origin, route, len(body))
            assert _parse(body).meta.get("apg-site-digest") == digest, (origin, route)
            assert headers.get("content-security-policy") == site_build.CONTENT_SECURITY_POLICY, (
                origin, route, headers.get("content-security-policy"),
            )  # fmt: skip
            assert "access-control-allow-origin" not in headers, (origin, route)
        status, _, body = _get(recorder, f"{origin}/missing-{digest[:8]}/")
        assert status == 404 and body == built["404.html"], (origin, status)
    assert {host for _, host in recorder.hosts()} == {urlsplit(o).hostname for o in origins}


def test_the_site_loads_nothing_else(built: dict[str, bytes], recorder: Recorder) -> None:
    """Every asset a live page names is the site's own and answers 200; every
    absolute link is one of the origins the build allows."""
    for route in _routes(built):
        url = f"{site_build.SITE_URL}{route}"
        _, body = _settled(recorder, url)
        page = _parse(body)
        for asset in page.assets:
            target = urljoin(url, asset)
            assert urlsplit(target).hostname == urlsplit(site_build.SITE_URL).hostname, asset
            status, _, _ = _get(recorder, target)
            assert status == 200, (target, status)
        for link in page.links:
            if link.startswith("https://"):
                assert link.startswith(site_build.ALLOWED_ORIGINS), (route, link)
            else:
                assert link.startswith(("/", "#", "mailto:" + site_build.INVITATION_ADDRESS)), link


def test_the_pricing_page_matches_the_api(endpoint: str, owner: str, recorder: Recorder) -> None:
    """The live pricing page's plans are `GET /v1/plans`' -- each entitlement's
    value and whether it is enforced -- and its first sentence the API's note."""
    status, served = recorder.json("GET", f"{endpoint}/plans", None, owner)
    assert status == 200, (status, served.get("error"))
    _, body = _settled(recorder, f"{site_build.SITE_URL}/pricing/")
    page = _parse(body)
    assert page.paragraphs[0] == served["note"], (page.paragraphs[:1], served["note"])
    for plan in served["plans"]:
        expected = [
            [entitlement["name"].replace("_", " "),
             ", ".join(entitlement["value"]) if isinstance(entitlement["value"], list)
             else str(entitlement["value"]),
             "" if entitlement["unit"] == "text" else entitlement["unit"],
             "enforced" if entitlement["enforced"] else "shown, not enforced"]
            for entitlement in plan["entitlements"]
        ]  # fmt: skip
        assert page.sections.get(site_build.slug(plan["plan"])) == expected, plan["plan"]
    _only(recorder, endpoint, site_build.SITE_URL)


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof: nothing here reaches the host by any
    path but `routes.control`, the console's origin, the site and 5432. Read
    from this file's own text and syntax: no SSH library, no `ssh` argv, no
    destination -- and no process door at all."""
    text = Path(__file__).read_text(encoding="utf-8")
    # Each needle split so this list never spells what it forbids (D2398).
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    tree = ast.parse(text)
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}  # fmt: skip
    assert "subprocess" not in imported, imported

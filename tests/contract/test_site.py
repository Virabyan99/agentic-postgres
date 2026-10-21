"""The public site: built from the tree alone, its claims from the Ledger, nothing third-party.

Session 43 (ADR 0283): `SITE-BUILD-001` and `SITE-CLAIM-001`. The site is
built by `agentic_postgres.site_build` exactly as `bin/build-site.py` and CI
build it; each refusal is also driven with a page that should be refused, so a
guard that reads nothing cannot pass.
"""

from __future__ import annotations

import dataclasses
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT, naming, plans, reality_ledger, site_build

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

BUILD = REPO_ROOT / "bin" / "build-site.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "site.yml"
POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)


@pytest.fixture(scope="module")
def built() -> dict[str, bytes]:
    return site_build.build()


def _html(built: dict[str, bytes]) -> dict[str, str]:
    return {name: data.decode("utf-8") for name, data in built.items() if name.endswith(".html")}


def _page(body: str, ledger: tuple[str, ...] = ("postgresql",)) -> site_build.Page:
    return site_build.Page(
        source=site_build.PAGES_ROOT / "synthetic.md", route="/synthetic/", title="t",
        description="d", ledger=ledger, body=body, body_line=5,
    )  # fmt: skip


# ---------------------------------------------------------------------------
# SITE-BUILD-001
# ---------------------------------------------------------------------------


def test_two_builds_are_byte_equal(tmp_path: Path) -> None:
    """Through the command: `--check` builds twice and compares, and `--out`
    writes the same bytes the module builds."""
    done = subprocess.run([sys.executable, str(BUILD), "--check"],
                          capture_output=True, text=True, check=False)  # fmt: skip
    assert done.returncode == 0 and "byte-equal" in done.stdout, done.stderr
    out = tmp_path / "site"
    done = subprocess.run([sys.executable, str(BUILD), "--out", str(out)],
                          capture_output=True, text=True, check=False)  # fmt: skip
    assert done.returncode == 0, done.stderr
    written = {path.relative_to(out).as_posix(): path.read_bytes()
               for path in out.rglob("*") if path.is_file()}  # fmt: skip
    assert written == site_build.build()
    inside = subprocess.run([sys.executable, str(BUILD), "--out", str(REPO_ROOT / "site-x")],
                            capture_output=True, text=True, check=False)  # fmt: skip
    assert inside.returncode == 2 and not (REPO_ROOT / "site-x").exists()


def test_the_pricing_page_follows_the_plans(monkeypatch: pytest.MonkeyPatch) -> None:
    """The page is `PLANS`: a value changed in the table is the value printed."""
    free = plans.PLANS["free"]
    seven = dataclasses.replace(free.entitlements["projects_active"], value=7)
    changed = dataclasses.replace(
        free, entitlements={**free.entitlements, "projects_active": seven}
    )
    original = site_build.build()["pricing/index.html"].decode("utf-8")
    assert "<td>projects active</td><td>1</td>" in original
    monkeypatch.setitem(plans.PLANS, "free", changed)
    page = site_build.build()["pricing/index.html"].decode("utf-8")
    assert "<td>projects active</td><td>7</td>" in page
    assert "<td>projects active</td><td>1</td>" not in page
    assert plans.BETA_SENTENCE in page


def test_no_price_is_printed(built: dict[str, bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    page = built["pricing/index.html"].decode("utf-8")
    for mark in site_build.PRICE_MARKS:
        assert mark not in page, mark
    # The control: a price in the table is refused by the build itself.
    monkeypatch.setattr(plans, "BETA_SENTENCE", "Free costs $0 per month.")
    with pytest.raises(site_build.SiteError, match="pricing page prints"):
        site_build.build()


def test_the_ledger_page_is_the_rows(built: dict[str, bytes]) -> None:
    page = built["ledger/index.html"].decode("utf-8")
    rows = reality_ledger.load()["rows"]
    assert page.count("<tr>") == len(rows) + 1
    for row in rows:
        assert f"<td>{site_build.html.escape(row['concept'])}</td>" in page, row["id"]
        text = site_build.html.escape(" ".join(row["customer_text"].split()))
        assert text in page, row["id"]


@pytest.mark.parametrize(
    "line",
    ['<img src="https://example.com/x.png">', "<script>alert(1)</script>", "Text <b>bold</b>",
     "<!-- a comment -->", "</p>"],
)  # fmt: skip
def test_raw_html_is_refused(line: str) -> None:
    with pytest.raises(site_build.SiteError, match="raw HTML"):
        site_build.render_markdown(site_build.PAGES_ROOT / "x.md", line)
    # The control: inside a code span it is text, escaped.
    rendered = site_build.render_markdown(site_build.PAGES_ROOT / "x.md", f"`{line}`")
    assert rendered == f"<p><code>{site_build.html.escape(line)}</code></p>\n"


def test_the_site_names_no_host_address(built: dict[str, bytes]) -> None:
    """No address of the host, no IPv4 literal, and no name under the zone but
    the apex, `www` and `control` -- in the build, its sources or the workflow
    (D2651: the records this site owns name no host of ours)."""
    texts = {name: data.decode("utf-8") for name, data in built.items()}
    texts.update({str(path): path.read_text(encoding="utf-8")
                  for path in site_build.SITE_ROOT.rglob("*") if path.is_file()})  # fmt: skip
    texts["site.yml"] = WORKFLOW.read_text(encoding="utf-8")
    for name, text in texts.items():
        assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text), f"{name} holds an IPv4 literal"
        for host in re.findall(r"\b((?:[a-z0-9-]+\.)+)agenticpostgresql\.com", text):
            assert host in ("www.", "control."), f"{name} names {host}agenticpostgresql.com"


def test_the_published_names_are_naming_s() -> None:
    """The console and the API addresses the site prints are the ones `naming`
    derives for the control example's route shape, so they cannot drift."""
    manifest = yaml.safe_load((REPO_ROOT / "project.control.example.yaml").read_text("utf-8"))
    identity = naming.derive(
        slug=manifest["project"]["slug"], environment=manifest["project"]["environment"],
        domain=site_build.CONTROL_DOMAIN, api_base_path=manifest["api"]["public_base_path"],
        mcp_base_path=manifest["mcp"]["public_base_path"],
    )  # fmt: skip
    assert site_build.CONTROL_ENDPOINT == identity.route_control
    assert site_build.CONSOLE_URL == naming.console_origin(site_build.CONTROL_DOMAIN) + "/console/"


# ---------------------------------------------------------------------------
# SITE-CLAIM-001
# ---------------------------------------------------------------------------


def test_every_page_names_reachable_rows() -> None:
    ledger = reality_ledger.load()
    statuses = {row["id"]: row["status"] for row in ledger["rows"]}
    pages = site_build.pages()
    assert len(pages) >= 12
    for page in pages:
        if page.ledger == ("*",):
            assert page.route == "/ledger/", page.route
            continue
        assert page.ledger, page.route
        for row in page.ledger:
            assert statuses.get(row) in reality_ledger.REACHABLE, (page.route, row)
    # `passkeys` since Session 44 (D2745): `sql_editor` became reachable at the bump,
    # and the example is a row that stays planned.
    for unreachable in ("passkeys", "billing", "no_such_row"):
        with pytest.raises(site_build.SiteError, match="names the Ledger row"):
            site_build.check_page(_page("A sentence.", (unreachable,)), ledger)
    with pytest.raises(site_build.SiteError, match="only the Ledger page"):
        site_build.check_page(_page("A sentence.", ("*",)), ledger)


@pytest.mark.parametrize("command", ["sudo deploy", "bin/cloud.py", "ssh op@host", "git clone x",
                                     "--session 43"])  # fmt: skip
def test_no_page_holds_an_operator_command(command: str) -> None:
    ledger = reality_ledger.load()
    for page in site_build.pages():
        for operator in site_build.OPERATOR_TEXT:
            assert operator not in page.body, (page.route, operator)
    with pytest.raises(site_build.SiteError, match="operator's command"):
        site_build.check_page(_page(f"Run `{command}` first."), ledger)


def test_no_forbidden_word(built: dict[str, bytes]) -> None:
    """No page claims a §59 word. The Ledger page's CONCEPT column names a row
    such as *Autoscaling* precisely to say it is not offered, so there the scan
    reads what the customer is told -- its other two columns (D2708)."""
    for name, text in _html(built).items():
        if name == "ledger/index.html":
            cells = re.findall(r"<tr><td>[^<]*</td>(<td>.*?</td><td>.*?</td>)</tr>", text)
            assert len(cells) == len(reality_ledger.load()["rows"])
            text = " ".join(cells)
        lowered = text.lower()
        for word in reality_ledger.FORBIDDEN_WORDS:
            assert word not in lowered, (name, word)
    with pytest.raises(site_build.SiteError, match="uses"):
        site_build.check_page(_page("It is production-ready."), reality_ledger.load())


def test_no_third_party_asset(built: dict[str, bytes]) -> None:
    """Every `src=`/`href=` in the built HTML and every `url(` in the CSS is
    the site's own, `#`, the invitation mailto, or an allowed https origin."""
    found = 0
    for name, text in _html(built).items():
        for target in re.findall(r'\b(?:src|href)="([^"]+)"', text):
            found += 1
            if target.startswith("mailto:"):
                assert target.split("?", 1)[0] == f"mailto:{site_build.INVITATION_ADDRESS}", name
            elif target.startswith("https://"):
                assert any(target == origin or target.startswith(origin + "/")
                           for origin in site_build.ALLOWED_ORIGINS), (name, target)  # fmt: skip
            else:
                assert target.startswith(("/", "#")) and not target.startswith("//"), (name, target)
        assert "<script" not in text and "<iframe" not in text, name
    assert found > 50, "the scan read almost nothing"
    assert "url(" not in built["site.css"].decode("utf-8") and "@import" not in built[
        "site.css"
    ].decode("utf-8")
    with pytest.raises(site_build.SiteError, match="another origin"):
        site_build.render_markdown(site_build.PAGES_ROOT / "x.md", "[x](https://cdn.example/x.js)")


def test_the_headers_file_carries_the_policy(built: dict[str, bytes]) -> None:
    headers = built["_headers"].decode("utf-8")
    assert headers.startswith("/*\n")
    assert f"  Content-Security-Policy: {POLICY}\n" in headers
    assert "  Referrer-Policy: no-referrer\n" in headers
    assert "  ! Access-Control-Allow-Origin\n" in headers
    assert site_build.CONTENT_SECURITY_POLICY == POLICY
    assert "404.html" in built, "Pages serves the index for a missing path without a 404 page"


def test_the_live_proofs_name_themselves_to_the_site() -> None:
    """D2728: the live site proofs' recorder sends the proof's own User-Agent --
    Cloudflare Pages refuses urllib's default `Python-urllib/3.x` (403, error
    1010), which is how `site_live` failed on its first live run. Read off the
    wire: a loopback server records the header each request arrives with,
    through both the recorder's own `send` and the opener the console module's
    `_get` uses."""
    import http.server
    import threading

    from tests.external.test_session38_public_lifecycle import (
        USER_AGENT,
        Recorder,
    )

    arrived: list[str | None] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            arrived.append(self.headers.get("User-Agent"))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            return None

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        recorder = Recorder()
        assert recorder.send("GET", url)[0] == 200
        with recorder.opener.open(url, timeout=10) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
    assert arrived == [USER_AGENT, USER_AGENT]
    assert USER_AGENT == "agentic-postgres-proof"
    assert not USER_AGENT.startswith("Python-urllib")

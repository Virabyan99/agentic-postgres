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
#: ADR 0283 item 7's policy as ADR 0288 moved it: `font-src 'self'`, the rest
#: byte-equal (D2813 (a)).
POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'none'; font-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
#: The build's only files that are not text (ADR 0288, D2847): the two
#: typefaces, whose bytes `test_look.py` pins by sha256.
BINARY = ("fonts/jetbrains-mono.woff2", "fonts/schibsted-grotesk.woff2")
TEXT_SUFFIXES = (".html", ".css", ".txt", ".svg")


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


#: ADR 0299: the zone the site moved from. It still holds the operator's own
#: names (`secrets.`, `alpha-db.`, `beta-db.`), so a name of ours under it is
#: refused exactly as under the site's own zone.
FORMER_ZONE = "agenticpostgresql.com"


def _site_zone() -> str:
    """The site's zone, read from the build's own constants (D2962): the control
    domain without its first label, which `SITE_URL` must be the apex of."""
    zone = naming.sql_relay_zone(site_build.CONTROL_DOMAIN)
    assert site_build.SITE_URL == f"https://{zone}", (site_build.SITE_URL, zone)
    return zone


def _named_hosts_of_ours(text: str) -> list[str]:
    """Every name under the site's zone or the former one but the apex, `www`
    and `control` (D2651: the records this site owns name no host of ours)."""
    found: list[str] = []
    for zone in dict.fromkeys((_site_zone(), FORMER_ZONE)):
        for prefix in re.findall(rf"\b((?:[a-z0-9-]+\.)+){re.escape(zone)}\b", text):
            if prefix not in ("www.", "control."):
                found.append(prefix + zone)
    return found


def test_the_host_reading_reads_the_sites_own_zone() -> None:
    """D2962: the reading `test_the_site_names_no_host_address` runs is the
    build's zone's -- a host of ours under it is found, the three names the site
    may print are not, and the former zone is read too. A regex over a typed
    domain would pass every page vacuously once the domain moved."""
    zone = _site_zone()
    assert _named_hosts_of_ours(f"see secrets.{zone} and pool.slot3.{zone}.") == [
        f"secrets.{zone}",
        f"pool.slot3.{zone}",
    ]
    allowed = f"https://{zone}/ https://www.{zone}/ https://control.{zone}/console/"
    assert _named_hosts_of_ours(allowed) == []
    assert _named_hosts_of_ours(f"secrets.{FORMER_ZONE}") == [f"secrets.{FORMER_ZONE}"]


def test_the_site_names_no_host_address(built: dict[str, bytes]) -> None:
    """No address of the host, no IPv4 literal, and no name under the zone but
    the apex, `www` and `control` -- in the build, its sources or the workflow
    (D2651: the records this site owns name no host of ours). Every text file
    of the build is read; the files it cannot read as text are exactly the two
    typefaces, so an unexpected binary fails here (ADR 0288, D2847)."""
    binary = sorted(name for name in built
                    if name != "_headers" and not name.endswith(TEXT_SUFFIXES))  # fmt: skip
    assert (
        binary
        == sorted(BINARY)
        == sorted(a for a in site_build.SHARED_ASSETS if a.endswith(".woff2"))
    )
    texts = {name: data.decode("utf-8") for name, data in built.items() if name not in BINARY}
    texts.update({str(path): path.read_text(encoding="utf-8")
                  for path in site_build.SITE_ROOT.rglob("*") if path.is_file()})  # fmt: skip
    texts["site.yml"] = WORKFLOW.read_text(encoding="utf-8")
    for name, text in texts.items():
        assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text), f"{name} holds an IPv4 literal"
        # D2962: the zone is the build's own constant's, never a typed domain.
        assert _named_hosts_of_ours(text) == [], f"{name} names a host of ours"


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
    """Every `src=`/`href=` in the built HTML is the site's own, `#`, the
    invitation mailto, or an allowed https origin; every `url(…)` in the CSS is
    one of the typefaces the build carries, and nothing is imported (ADR 0288,
    D2813 (b): an allowlist of the measured set, not a weaker scan)."""
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
    css = built["site.css"].decode("utf-8")
    assert "@import" not in css
    urls = [u.strip("\"'") for u in re.findall(r"url\(([^)]*)\)", css)]
    assert sorted(urls) == sorted("/" + name for name in BINARY), urls
    for url in urls:
        assert url.lstrip("/") in built and url.lstrip("/") in site_build.SHARED_ASSETS, url
    assert css.count("url(") == len(urls)
    with pytest.raises(site_build.SiteError, match="another origin"):
        site_build.render_markdown(site_build.PAGES_ROOT / "x.md", "[x](https://cdn.example/x.js)")


def test_the_build_carries_the_shared_assets(built: dict[str, bytes]) -> None:
    """ADR 0288 (D2814): the typefaces, their licences and the favicon live
    once, in the console's tree; the build carries each, byte-equal, at the
    same relative path, and the digest covers it -- and every page links the
    favicon from the site's own origin."""
    assert len(site_build.SHARED_ASSETS) == 5
    inputs = site_build.digest_inputs()
    for relative in site_build.SHARED_ASSETS:
        source = site_build.CONSOLE_PUBLIC / relative
        assert built[relative] == source.read_bytes(), relative
        assert source in inputs, relative
    for name, text in _html(built).items():
        assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml">' in text, name


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


# ---------------------------------------------------------------------------
# Session 47 Run 8 (ADR 0298; D2956, D2958, D2991, D3020-D3024): the pages that
# say what the console and the server do are held to the console's and the
# server's own text, never a second copy of it.
# ---------------------------------------------------------------------------

#: The example project whose code the connecting page shows.
EXAMPLE_DOORS = {
    "enabled": True,
    "pooled": {"host": "pool.shop.example.com", "port": 5432,
               "user": "shop_prod_customer_app", "database": "shop_prod"},
    "direct": {"host": "direct.shop.example.com", "port": 5432,
               "user": "shop_prod_customer_admin", "database": "shop_prod"},
}  # fmt: skip
CONSOLE = REPO_ROOT / "services" / "console" / "public"


def _body(route: str) -> str:
    return next(page.body for page in site_build.pages() if page.route == route)


def _section(body: str, heading: str) -> str:
    assert f"\n## {heading}\n" in body, heading
    return body.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _fenced(text: str) -> list[str]:
    return re.findall(r"^```[a-z]*\n(.*?)\n```$", text, flags=re.MULTILINE | re.DOTALL)


def _js_round(value: float) -> int:
    """JavaScript's `Math.round`, which `progress.js` words a range with."""
    return int(value + 0.5)


def test_the_connecting_page_shows_the_code_the_server_serves() -> None:
    """D2991: the server's snippets are the one text. The connecting page's code
    for each client is `connection_snippets.snippets()` for the example doors,
    every client in `CLIENTS`' order, and each with its `where` line as served;
    no other block on the page names a door. The control: the section is read,
    so a page with no code at all fails here rather than passing empty."""
    from agentic_postgres import service_source

    module = service_source.load("connection_snippets")
    served = module.snippets(EXAMPLE_DOORS)
    where = module.where()
    body = _body("/docs/connecting/")
    section = _section(body, "3. Copy the code for your tool")
    hosts = (EXAMPLE_DOORS["pooled"]["host"], EXAMPLE_DOORS["direct"]["host"])
    shown = [block for block in _fenced(section) if any(host in block for host in hosts)]
    assert len(shown) == len(module.CLIENTS) == 7, len(shown)
    assert shown == [served[client] for client in module.CLIENTS]
    for client in module.CLIENTS:
        guide = where[client]
        line = f"Where it goes: {guide['file']}. What to install: {guide['install']}."
        assert section.count(line) == 1, client
    outside = body.replace(section, "")
    assert not any(host in block for block in _fenced(outside) for host in hosts)
    assert module.PASSWORD_PLACEHOLDER in section


def test_the_quickstart_says_what_the_creation_tracker_says() -> None:
    """ADR 0296: the creation's step count, first and last step, usual time and
    bound are the server's `operation_steps`, worded as `progress.js` words
    them -- the quickstart cannot drift from the tracker it describes."""
    from agentic_postgres import service_source

    expected = service_source.load("operation_steps").expected("project.create")
    labels = [step["label"] for step in expected["steps"]]
    low, high = expected["typical_seconds"]["low"], expected["typical_seconds"]["high"]
    usual = f"about {max(1, _js_round(low / 60))} to {max(1, _js_round(high / 60))} minutes"
    body = _body("/quickstart/")
    assert f"{len(labels)} named steps, from *{labels[0]}* to *{labels[-1]}*" in body
    assert f"usually takes {usual}**" in body
    assert f"has not finished {round(expected['bound_seconds'] / 60)} minutes after" in body


def test_the_sql_editor_page_says_what_the_editor_says() -> None:
    """D2957: the editor's limits and every way a session ends are the
    console's own sentences -- `sql.js`'s deadline, `messages.js`'s session
    limits and each of its `CLOSES` -- on the page, so a sentence the console
    changes is a page that moves with it. The control: `CLOSES` parses to the
    relay's codes."""
    body = _body("/docs/sql-editor/")
    sql = (CONSOLE / "sql.js").read_text(encoding="utf-8")
    messages = (CONSOLE / "messages.js").read_text(encoding="utf-8")
    deadline = re.search(r'DEADLINE_SENTENCE = "([^"]+)"', sql)
    limits = re.search(r'SESSION_LIMITS = "([^"]+)"', messages)
    assert deadline and limits
    assert deadline.group(1) in body and limits.group(1) in body
    closes = messages.split("export const CLOSES = {", 1)[1].split("\n};", 1)[0]
    codes = re.findall(r"^  (\d{4}): \{", closes, flags=re.MULTILINE)
    sentences = re.findall(r'sentence: "([^"]+)"', closes)
    assert codes == ["1000", "1006", "1011", "4400", "4408", "4413", "4429", "4502"]
    assert len(sentences) == len(codes)
    for sentence in sentences:
        assert f"| {sentence} |" in body, sentence


def test_the_support_page_gives_the_address_the_build_derives() -> None:
    """ADR 0298: the support page is in the docs groups and gives the address a
    person writes to for help through `@contact` -- `INVITATION_ADDRESS`, never
    typed in the page -- and the block takes nothing after it."""
    built = site_build.build()["docs/support/index.html"].decode("utf-8")
    address = site_build.INVITATION_ADDRESS
    href = f"mailto:{address}?subject={site_build.SUPPORT_SUBJECT}"
    assert f'<a href="{href}">{address}</a>' in built
    assert "/docs/support/" in site_build.docs_order()
    source = (site_build.PAGES_ROOT / "docs" / "support.md").read_text(encoding="utf-8")
    assert "\n@contact\n" in source and address not in source
    page = next(p for p in site_build.pages() if p.route == "/docs/support/")
    resolve = site_build._blocks_for(page, reality_ledger.load(), site_build.pages())
    with pytest.raises(site_build.SiteError, match="takes nothing after it"):
        resolve(page.source, 1, "@contact someone@example.com")


# ---------------------------------------------------------------------------
# Session 47 Run 12: the domain moved on every page (D3063), the count (D3049)
# ---------------------------------------------------------------------------


def test_no_page_names_the_former_zone(built: dict[str, bytes]) -> None:
    """D3063: with both parks applied, seven page literals still typed the old
    zone -- and `_named_hosts_of_ours` admits `control.` under either zone, so
    it could not see them. No page source and no built text file names the
    former zone at all."""
    texts = {name: data.decode("utf-8") for name, data in built.items() if name not in BINARY}
    texts.update({str(path): path.read_text(encoding="utf-8")
                  for path in site_build.PAGES_ROOT.rglob("*.md")})  # fmt: skip
    assert len(texts) > 30, len(texts)
    named = sorted(name for name, body in texts.items() if FORMER_ZONE in body)
    assert named == [], named


def test_every_endpoint_and_console_link_on_a_page_is_the_builds() -> None:
    """D3063: a page cannot substitute a constant, so each `--endpoint` it types
    must BE `site_build.CONTROL_ENDPOINT` and each console link
    `site_build.CONSOLE_URL` -- the control: a planted old endpoint is found."""
    endpoint = re.compile(r"--endpoint (\S+)")
    console = re.compile(r"\((https://control\.[^)\s]+/console/)\)")
    seen = {"endpoint": 0, "console": 0}
    for path in sorted(site_build.PAGES_ROOT.rglob("*.md")):
        body = path.read_text(encoding="utf-8")
        for found in endpoint.findall(body):
            assert found == site_build.CONTROL_ENDPOINT, (str(path), found)
            seen["endpoint"] += 1
        for found in console.findall(body):
            assert found == site_build.CONSOLE_URL, (str(path), found)
            seen["console"] += 1
    assert seen["endpoint"] >= 4 and seen["console"] >= 2, seen
    planted = f"apg login password --endpoint https://control.{FORMER_ZONE}/api/v1"
    assert endpoint.findall(planted) != [site_build.CONTROL_ENDPOINT]


def test_the_quickstart_counts_only_its_steps(built: dict[str, bytes]) -> None:
    """D3049: the nav's *N steps* is the number of `## ` headings inside the
    quickstart's `::: steps` block -- *Or, from a terminal*, after the block, is
    an alternative, not a step. The control: a synthetic page with a heading
    outside its block counts only the inside ones."""
    synthetic = "## Before\n\n::: steps\n## One\n\ntext\n\n## Two\n:::\n\n## After\n"
    assert site_build.quickstart_steps(synthetic) == 2
    page = next(p for p in site_build.pages() if p.route == "/quickstart/")
    steps = site_build.quickstart_steps(page.body)
    headings = sum(1 for line in page.body.splitlines() if line.startswith("## "))
    assert 0 < steps < headings, (steps, headings)
    home = built["index.html"].decode("utf-8")
    assert f"{steps} steps" in home and f"{headings} steps" not in home

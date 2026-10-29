"""The console's pages: calls in the snapshot, rows reachable, no SQL, no storage, no markup.

Session 43 (ADR 0280): `CON-LEDGER-001`'s three page halves and
`CON-SCRAM-001`'s storage half. Read from the files the image bakes
(`services/console/public/`), because they are what a browser runs.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, reality_ledger, site_build

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

PUBLIC = REPO_ROOT / "services" / "console" / "public"
SNAPSHOT = REPO_ROOT / "contracts" / "control-openapi.canonical.json"
METHODS = "GET|POST|PUT|PATCH|DELETE"

#: `call(...)` and `operate(...)` in the views and `send(...)` inside `api.js`:
#: method and path literal (a string or a template), up to the first `+` or `,`.
CALL = re.compile(rf'\b(?:call|send|operate)\(\s*"({METHODS})",\s*(?:"([^"]*)"|`([^`]*)`)')

#: SQL's SHAPE, not its vocabulary: the plan's `\b(select|...|create|...)\s`
#: also matched the page's own sentence "Create your account" (D2696).
SQL = re.compile(
    r"\b(select\s+[\w*,\s]+\s+from|insert\s+into|update\s+\w+\s+set|delete\s+from|"
    r"create\s+(table|role|schema|function|index|view|extension)|"
    r"drop\s+(table|role|schema|function|database)|alter\s+(table|role|system))\b",
    re.IGNORECASE,
)


def _scripts() -> dict[str, str]:
    """Each script's CODE: its full-line `//` comments removed -- the only
    comments these files use (asserted), so a sentence explaining what the
    code never does is not read as the code doing it."""
    scripts = {}
    for path in sorted(PUBLIC.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert "/*" not in text, f"{path.name} uses a block comment; this reader removes none"
        lines = [line for line in text.splitlines() if not line.lstrip().startswith("//")]
        scripts[path.name] = "\n".join(lines)
    return scripts


def _called() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for text in _scripts().values():
        for method, plain, template in CALL.findall(text):
            path = plain or re.sub(r"\$\{[^}]*\}", "{x}", template)
            found.add((method, "/v1" + path.split("?", 1)[0]))
    return found


def _operations() -> dict[str, set[str]]:
    paths = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["paths"]
    return {path: {method.upper() for method in operations} for path, operations in paths.items()}


def _matches(path: str, pattern: str) -> bool:
    expression = "^" + re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(pattern)) + "$"
    return re.match(expression, path.replace("{x}", "VALUE")) is not None


def _pages() -> dict[str, Any]:
    return json.loads((PUBLIC / "pages.json").read_text(encoding="utf-8"))


def test_every_called_path_is_in_the_snapshot() -> None:
    """Every call a script makes, and every call `pages.json` lists, is an
    operation the reviewed control snapshot has -- and the two lists agree, so
    `pages.json` (what the guards read) cannot drift from the scripts."""
    operations = _operations()
    called = _called()
    assert len(called) >= 8, f"the extraction found only {sorted(called)}"
    listed = {tuple(entry.split(" ", 1)) for view in _pages()["views"] for entry in view["calls"]}
    for method, path in sorted(called | listed):
        known = [pattern for pattern in operations if _matches(path, pattern)]
        assert known, f"{method} {path} is in no path of the control snapshot"
        assert any(method in operations[pattern] for pattern in known), f"{method} {path}"
    assert {(m, p.replace("{x}", "")) for m, p in called} <= {
        (m, re.sub(r"\{[^}]*\}", "", p)) for m, p in listed
    }, sorted(called - listed)


def test_no_page_names_an_unreachable_row() -> None:
    rows = {row["id"]: row["status"] for row in reality_ledger.load()["rows"]}
    for view in _pages()["views"]:
        for row in view["ledger"]:
            assert rows.get(row) in reality_ledger.REACHABLE, (view["id"], row, rows.get(row))


def test_no_script_holds_sql() -> None:
    for name, text in _scripts().items():
        assert not SQL.search(text), f"{name}: {SQL.search(text).group(0)!r}"
    # The control: the shape is recognised, and the page's own words are not it.
    assert SQL.search("SELECT id FROM app.projects") and SQL.search("drop table x")
    assert not SQL.search("Create your account") and not SQL.search("Delete the project")


def test_no_script_writes_storage() -> None:
    """The session is two HttpOnly cookies no script can read (ADR 0281), and
    a password, a key or a seed lives in one view's variables, never in
    storage a later script could read (D2660)."""
    for name, text in _scripts().items():
        for store in ("localStorage", "sessionStorage", "indexedDB", "document.cookie", "caches."):
            assert store not in text, f"{name} touches {store}"


def test_no_markup_is_built_from_a_value() -> None:
    """Every server value is set as text or a DOM property; no script parses
    markup at all, which is a shorter rule than "only from literals"."""
    for name, text in _scripts().items():
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
                     "new Function"):  # fmt: skip
            assert sink not in text, f"{name} uses {sink}"


def test_only_pg_js_opens_a_websocket() -> None:
    """ADR 0285: the editor's wire client is the one script that opens a socket --
    to the relay's origin, the one other origin the policy names."""
    openers = sorted(name for name, text in _scripts().items() if "WebSocket(" in text)
    assert openers == ["pg.js"], openers
    assert "new WebSocket(url)" in _scripts()["pg.js"]
    for name, text in _scripts().items():
        for other in ("EventSource(", "RTCPeerConnection", "sendBeacon", "XMLHttpRequest"):
            assert other not in text, f"{name} uses {other}"


def test_only_api_js_calls_fetch() -> None:
    callers = sorted(name for name, text in _scripts().items() if "fetch(" in text)
    assert callers == ["api.js"], callers
    api = _scripts()["api.js"]
    assert '"X-Apg-Console"' in api and 'credentials: "same-origin"' in api
    assert 'redirect: "error"' in api


#: One entry of `nav.js`'s PAGES table: its id, label, purpose and help path.
PAGE_ENTRY = re.compile(
    r'^  "([a-z-]+)": \{ label: "([^"]+)", group: [^,]+,(?: item: "[a-z-]+",)? '
    r'purpose: "([^"]*)", help: "([^"]+)" \},$',
    re.MULTILINE,
)


def test_every_view_has_a_page_and_a_built_help_route() -> None:
    """Session 47 (ADR 0295, ADR 0298; the brief's page template): every
    signed-in view in `pages.json` has an entry in the shell's PAGES table --
    a label, one line of purpose, and a help path -- and every site path a
    console module links to (each page's help, a refusal's next action, the
    Help page's documents) is a route the site build produces. The shell draws
    each page's help link from that table, through the site's derived origin."""
    nav = _scripts()["nav.js"]
    pages = {page: (label, purpose, help_path) for page, label, purpose, help_path
             in PAGE_ENTRY.findall(nav)}  # fmt: skip
    assert len(pages) >= 20, f"the PAGES table parsed to {sorted(pages)}"
    for view in _pages()["views"]:
        if view["id"] in ("accept", "sign-in"):
            continue
        assert view["id"] in pages, f"{view['id']} has no entry in nav.js's PAGES"
        label, purpose, _ = pages[view["id"]]
        assert label and purpose.endswith("."), view["id"]
    built = {
        "/" + name[: -len("index.html")]
        for name in site_build.build()
        if name.endswith("index.html")
    }
    assert "/docs/" in built and "/pricing/" in built, sorted(built)[:10]
    linked = {help_path for _, _, help_path in pages.values()}
    for name in ("app.js", "messages.js"):
        linked |= set(
            re.findall(r'"(/(?:docs|pricing|quickstart|ledger)/[^"]*)"', _scripts()[name])
        )
    assert len(linked) >= 8, sorted(linked)
    for path in sorted(linked):
        assert path in built, f"a console page links to {path}, which the site does not build"
    assert (
        'h("a", { className: "help-link", href: siteLink(page.help) }, "Help with this page")'
        in nav
    )
    # The site's origin is this host's minus its first label -- never a typed domain.
    for name, text in _scripts().items():
        assert "agenticpostgresql" not in text and "nomipg" not in text, name


def _built_routes() -> set[str]:
    return {
        "/" + name[: -len("index.html")]
        for name in site_build.build()
        if name.endswith("index.html")
    }


def _source(route: str) -> str:
    """The Markdown the site builds `route` from: `site/pages/<route>.md`, or
    its directory's `index.md`."""
    pages = REPO_ROOT / "site" / "pages"
    stem = route.strip("/")
    for candidate in (pages / f"{stem}.md", pages / stem / "index.md"):
        if stem and candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise AssertionError(f"no source page for {route}")


#: The word a page's documentation says it by, where the page's own label is
#: not that word: the page is the organisation's list of operations, the
#: site calls them operations; the console's *Plan and usage* is the site's
#: *Plans and usage*; *Slowest queries* is the site's *Query Insights*.
TOPIC = {
    "activity": "operation", "operation": "operation", "plan": "Plans and usage",
    "insights": "Query Insights", "project-overview": "project", "new-project": "Creating",
}  # fmt: skip


def test_each_help_link_points_at_the_page_that_documents_it() -> None:
    """Session 47 Run 7 (ADR 0298 decision 3, D2958): a page's *Help with this
    page* goes to the site page about THAT page -- read from the page the site
    builds the route from, which must say the console page's label (or the word
    `TOPIC` declares it by). The control: *Members and keys* is said on the
    getting-started page, and not on the CLI page Run 4 first pointed it at."""
    nav = _scripts()["nav.js"]
    pages = {page: (label, help_path) for page, label, _, help_path in PAGE_ENTRY.findall(nav)}
    checked = 0
    for page, (label, help_path) in sorted(pages.items()):
        if page in ("help", "missing"):
            continue  # the support route has its own test below
        topic = TOPIC.get(page, label)
        assert topic.lower() in _source(help_path).lower(), (page, help_path, topic)
        checked += 1
    assert checked >= 18, checked
    assert "members and keys" not in _source("/docs/cli/").lower()
    assert pages["organization-settings"][1] == "/docs/getting-started/"


def test_the_help_page_asks_a_person_and_links_the_support_route_the_site_builds() -> None:
    """D2958 (the brief's screen 10): `#/help` gives `invite@` the site's own
    domain -- derived, never typed -- with a copy control, what to send (the
    project's key, what the page said and its word, a support bundle from
    Settings), and that a password is never sent; and the documentation by
    task. The site's support page is PARKED until Run 12 (`/docs/support/`):
    the Help page's own help link is the console's ONE link to it, and it must
    be `/docs/support/` exactly when the site builds that route, `/docs/` until
    then -- so applying the park without moving the link is a red test."""
    built = _built_routes()
    nav = _scripts()["nav.js"]
    pages = {page: help_path for page, _, _, help_path in PAGE_ENTRY.findall(nav)}
    assert pages["help"] == ("/docs/support/" if "/docs/support/" in built else "/docs/")
    app = _scripts()["app.js"]
    view = app[app.index("function helpView(me) {") :]
    view = view[: view.index("\n}\n")]
    assert "const address = `invite@${siteDomain()}`;" in view
    assert "inlineCopy(address)" in view and "mailto:${address}" in view
    for words in ("The project's key", "what the page said", "A support bundle", "Settings",
                  "Never send a password"):  # fmt: skip
        assert words in view, words
    tasks = app[
        app.index("const HELP_TASKS = [") : app.index("];", app.index("const HELP_TASKS = ["))
    ]
    routes = re.findall(r'"(/[a-z/-]*)"\]', tasks)
    assert len(routes) >= 10 and set(routes) <= built, sorted(set(routes) - built)
    assert "/support/" not in "".join(routes)  # the one link to it is PAGES.help's


#: Each view that can be empty, and the functions its empty states are drawn
#: in (the view first, then the helpers it calls), with how many it draws.
EMPTY_VIEWS = {
    "overview": (("overview", "organizationSection", "projectList"), 2),
    "organization": (("organizationView", "projectList"), 1),
    "branches": (("branchesView",), 1),
    "backups": (("backupsView",), 1),
    "project-usage": (("projectUsageView", "usageSection"), 1),
    "organization-usage": (("orgUsageView", "usageSection"), 2),
    "insights": (("insightsView",), 1),
    "monitoring": (("monitoringView",), 1),
    "activity": (("activityView",), 1),
    "notifications": (("notificationsView",), 1),
    "organization-settings": (("orgSettingsView", "invitationList", "keyList"), 2),
}  # fmt: skip

#: An empty state drawn with its sentence alone -- no next action.
BARE_EMPTY = re.compile(r'emptyState\(\s*(?:"[^"]*"|`[^`]*`)\s*\)')


def _function(text: str, name: str) -> str:
    """One top-level function of a script, from its declaration to its closing
    brace at column 0."""
    found = re.search(rf"^(?:async )?function {name}\(", text, re.MULTILINE)
    assert found, f"no function {name}"
    rest = text[found.start() :]
    return rest[: rest.index("\n}\n") + 2]


def test_every_view_that_can_be_empty_says_what_will_appear_and_its_next_action() -> None:
    """The brief's §3 (Session 47 Run 7): a page with nothing to show has an
    empty state -- one sentence saying what will appear, and one action --
    on every view that can be empty: Projects with no project, Branches,
    Backups before a first reading, Usage, Slowest queries and Monitoring
    before data, Activity, Notifications, Members and keys. Each such view's
    functions draw at least the declared number, the view calls its helpers,
    and no empty state anywhere is drawn without an action."""
    app = _scripts()["app.js"]
    for view, (functions, least) in EMPTY_VIEWS.items():
        bodies = [_function(app, name) for name in functions]
        for index, helper in enumerate(functions[1:], start=1):
            # Called, or handed on (`served.projects.map(usageSection)`), by an earlier one.
            reached = re.compile(rf"\b{helper}\b")
            assert any(reached.search(body) for body in bodies[:index]), (view, helper)
        drawn = sum(body.count("emptyState(") for body in bodies)
        assert drawn >= least, f"{view} draws {drawn} empty state(s), fewer than {least}"
    assert app.count("emptyState(") >= 12
    assert not BARE_EMPTY.findall(app), BARE_EMPTY.findall(app)
    # The control: the shape of an empty state without an action is recognised.
    assert BARE_EMPTY.search('emptyState("No branch yet.")')
    assert not BARE_EMPTY.search('emptyState("No branch yet.", button("Make a branch", go))')
    ui = _scripts()["ui.js"]
    assert 'h("div", { className: "empty" }, h("p", {}, sentence), action || null)' in ui


def test_every_view_waits_under_a_skeleton() -> None:
    """The brief's §3: a page that waits shows a skeleton of its own shape --
    never a blank page and never *Loading* -- drawn by the router before any
    view's first read; and no page says *Loading*."""
    app = _scripts()["app.js"]
    router = _function(app, "route")
    assert router.index("show(skeleton());") < router.index("await view(me, found[1], turn);")
    assert router.index("show(skeleton());") < router.index("await overview(me, turn);")
    assert router.index("show(skeleton());") < router.index("helpView(me);")
    for name, text in _scripts().items():
        assert "Loading" not in text, name


def test_the_notifications_link_carries_no_count_and_no_read_state_is_kept() -> None:
    """D3001 (Session 47 Run 7): the server keeps no read state (its route:
    *"In-app only; no read state"*) and the console keeps nothing (ADR 0281,
    `test_no_script_writes_storage`), so an unread count cannot be read. The
    top bar's Notifications link is its label alone; the Notifications page
    counts what the API served in the last 24 hours (`progress.js`
    `recentNotices`), worded as exactly that, and says nothing is marked
    unread. No script keeps a seen or read mark of its own."""
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["paths"]
    route = snapshot["/v1/organizations/{organization}/notifications"]["get"]
    assert "no read state" in route["description"]
    nav = _scripts()["nav.js"]
    bar = _function(nav, "topBar")
    assert (
        'organization ? h("a", { className: "top-link", '
        "href: `#/org/${organization.id}/notifications` }, "
        'h("span", { className: "label" }, "Notifications")) : null,'
    ) in bar
    for word in ("length", "unread", "recent", "badge", "notices"):
        assert word not in bar.lower(), word
    app = _scripts()["app.js"]
    view = _function(app, "notificationsView")
    assert "recentNotices(notices, Date.now(), NOTICES_READ)" in view
    assert "nothing here is marked unread" in view
    for name, text in _scripts().items():
        for mark in ("lastSeen", "last_seen", "markRead", "seenAt", "readIds", "unreadCount"):
            assert mark not in text, f"{name} keeps a read mark: {mark}"


def _notice_kinds() -> list[str]:
    """The notification kinds the control set allows: the newest migration's
    CHECK on `control_notifications.kind`."""
    templates = REPO_ROOT / "projects" / "control" / "migrations" / "templates"
    newest = None
    for path in sorted(templates.glob("*.sql")):
        found = re.search(r"CHECK \(kind IN \(([^)]*)\)", path.read_text(encoding="utf-8"))
        if found and "operation_succeeded" in found.group(1):
            newest = found.group(1)
    assert newest, "no migration names the notification kinds"
    return re.findall(r"'([a-z_]+)'", newest)


def test_every_notification_kind_is_a_sentence_with_a_link() -> None:
    """D2953 (ADR 0297 decision 5): each kind the control set can write is
    worded by `noticeWords` -- read from the newest migration's CHECK, never
    typed -- and every branch links onward: to the operation that wrote it
    when it names one, else to the page that acts on it."""
    kinds = _notice_kinds()
    assert {"operation_started", "operation_succeeded", "operation_failed"} <= set(kinds), kinds
    words = _function(_scripts()["app.js"], "noticeWords")
    for kind in kinds:
        assert f'notice.kind === "{kind}"' in words, kind
    branches = words.split("\n  if (")[1:]
    assert len(branches) >= len(kinds)
    for branch in [*branches, words[words.rindex("\n  return ") :]]:
        assert "link(" in branch or "operation(" in branch or "planLinks(" in branch, branch[:120]
    fallback = words[
        words.index("const operation = ") : words.index('if (notice.kind === "operation_started")')
    ]
    assert "#/operations/${notice.operation_id}" in fallback and "#/org/${org}/activity" in fallback

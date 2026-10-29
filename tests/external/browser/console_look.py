"""The console's look walk: every signed-in page at two widths, read in a real Chromium.

Session 47 Run 9 (ADR 0295 decision 9, modelled on ADR 0288 decision 9's
`site_look.py`; the design brief's §8 floors). Run inside the pinned Playwright
image (never collected: no `test_` prefix). It signs in through the console's
own form as the probe owner (`~/s37/probe.json`: no new account, nothing
written -- every page is READ, no button is pressed), and for each signed-in
view `services/console/public/pages.json` names (its routes derived from that
file, never typed: `{organization}` the account's first organisation as
`GET /v1/organizations` answered the page, `{key}` `--project`, `{operation}`
the newest operation `GET /v1/operations` answered), at 390 x 844 and 1280 x
800, it waits for the page's `h1` with no skeleton left, `document.fonts.ready`
and a short settle (never `networkidle`, D2858; the tracker polls), and
records:

- `scrollWidth` against `innerWidth` (no page-level sideways scroll; a code
  block or a table scrolls in its own box);
- every request the page ATTEMPTED (Playwright's `request` event fires for a
  request the policy then blocks too, rig 45b) and its origin, each of which
  must be the console's own or the SQL relay's;
- the CSP violations the page reported;
- after a click on the page's corner, four `Tab`s: each focused element's
  outline and whether it matches `:focus-visible` (the 2 px `rgb(31, 79, 163)`
  ring);
- Playwright's accessibility snapshot of the page (`aria_snapshot`), written
  beside the screenshots, its sha256 and every form control or button in it
  that has no name.

Once per run, under `reduced_motion="reduce"` and without it, the computed
animation of the spinner, the skeleton and the tracker's bar (`.indeterminate
::after`) -- elements made by this script inside the page, read through the
console's own stylesheet: the brief's §8 says reduced motion stops all three.

**The record holds no secret** (D2416): the probe's password and TOTP seed and
the session cookies stay in variables, and the record's JSON is searched for
each before it is written -- exit 6 if one is there. It is written 0600, one
walk per record. No axe, no Lighthouse (ADR 0295 decision 9).

`--rehearse` answers every `/api/v1` call from fixtures inside the page (the
sign-in included), so the console's real files, served by its real image, run
with no host; `--plant-foreign` (rehearsal only) adds one image from a
third-party host to the console page, which the record must name. `--dry`
reads the pages and writes no record.

Exit codes: 0 walked; 2 usage; 4 a page could not be read; 6 the record would
have held a secret.
"""

# ruff: noqa: E501 -- the rehearsal's fixtures keep one served document per
# statement, shaped as the control mode serves it.

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import secrets
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from console_walk import fresh_code, seed_of, totp, write_private
from playwright.sync_api import Page, Route, sync_playwright

VIEWPORTS = ((390, 844), (1280, 800))
FOREIGN = "https://third-party.invalid/planted.png"
SETTLE_MS = 600  # after the page's own shape and the fonts: a late request is still attempted
TABS = 4
#: The views a person signed in reaches: every view `pages.json` names but these two.
SIGNED_OUT = ("accept", "sign-in")
INIT = """window.__violations = [];
document.addEventListener('securitypolicyviolation',
  (e) => window.__violations.push(e.effectiveDirective));"""
RING = """() => {
  const e = document.activeElement; const s = getComputedStyle(e);
  return {tag: e.tagName, role: e.getAttribute('role'), style: s.outlineStyle, width: s.outlineWidth,
          color: s.outlineColor, focus_visible: e.matches(':focus-visible')};
}"""
READY = """() => { const m = document.querySelector('#main');
  return !!(m && m.querySelector('h1') && !m.querySelector('.skeleton')); }"""
#: The three moving things the brief names, made inside the page from the
#: console's own class names, and their computed animation names.
MOTION = """() => {
  const made = ['spinner', 'sk', 'indeterminate'].map((name) => {
    const element = document.createElement('div');
    element.className = name;
    document.body.append(element);
    return element;
  });
  const read = {
    spinner: getComputedStyle(made[0]).animationName,
    skeleton: getComputedStyle(made[1]).animationName,
    bar: getComputedStyle(made[2], '::after').animationName,
  };
  made.forEach((element) => element.remove());
  return read;
}"""
#: Roles a person operates; one with no name in the snapshot is unnamed.
CONTROL_ROLES = ("button", "checkbox", "combobox", "link", "listbox", "radio", "searchbox",
                 "slider", "spinbutton", "switch", "tab", "textbox")  # fmt: skip
UNNAMED = re.compile(rf"^\s*- ({'|'.join(CONTROL_ROLES)})(?:\s*\[[^\]]*\])?\s*:?\s*$")


def unnamed_controls(snapshot: str) -> list[str]:
    """Each line of an `aria_snapshot` naming a control with no accessible name."""
    return [line.strip() for line in snapshot.splitlines() if UNNAMED.match(line)]


def routes(
    pages: dict[str, Any], organization: str, key: str, operation: str | None
) -> list[tuple[str, str]]:
    """(view id, fragment) for every signed-in view, from `pages.json`'s paths."""
    found = []
    for view in pages["views"]:
        if view["id"] in SIGNED_OUT:
            continue
        path = view["path"]
        if "{operation}" in path and operation is None:
            continue  # said in the record: no operation to read
        fragment = path.split("/console/", 1)[1]
        fragment = (
            fragment.replace("{organization}", organization)
            .replace("{key}", key)
            .replace("{operation}", operation or "")
        )
        found.append((view["id"], fragment))
    return found


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


# ---------------------------------------------------------------------------
# --rehearse: every /api/v1 answer, shaped as the control mode serves it
# ---------------------------------------------------------------------------


def _module(name: str) -> Any:
    path = Path("/repo/services/auth-api/app") / f"{name}.py"
    specification = importlib.util.spec_from_file_location(f"apg_look_{name}", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module  # a dataclass reads its own module
    specification.loader.exec_module(module)
    return module


class Fixtures:
    """The probe owner's organisation holding one ready project with a branch,
    a backup window, a day's usage, a statement, monitoring readings, members
    and keys, six notifications and one creation under way -- every page has
    something to draw at both widths. Nothing here is a secret but the probe's
    own password and seed, which only the sign-in compares."""

    ORG = "31121d7b-1aa3-4206-8f13-d81157c1beaf"
    OPERATION = "5a1d2b7c-9e11-4c3a-9a4e-0b5c6f0e8d0e"

    def __init__(self, project: str, probe: dict[str, str]) -> None:
        self.project, self.probe = project, probe
        self.signed_in = False
        self.now = datetime.now(UTC)
        snippets, steps = _module("connection_snippets"), _module("operation_steps")
        door = {"port": 5432, "database": project.replace("-", "_"), "sslmode": "verify-full"}
        self.pooled = {**door, "host": f"pool.{project.split('-')[0]}.rehearsal.test",
                       "user": f"apg_{project.replace('-', '_')}_customer_app", "connection_limit": 20}  # fmt: skip
        self.direct = {**door, "host": f"direct.{project.split('-')[0]}.rehearsal.test",
                       "user": f"apg_{project.replace('-', '_')}_customer_admin", "connection_limit": 5}  # fmt: skip
        self.connections = {
            "project": project, "pooled": self.pooled, "direct": self.direct,
            "password": snippets.PASSWORD_PLACEHOLDER,
            "snippets": snippets.snippets({"enabled": True, "pooled": self.pooled, "direct": self.direct}),
            "where": snippets.where(),
        }  # fmt: skip
        self.expected = steps.expected("project.create")
        self.plans = _module("plans")

    def ago(self, seconds: float) -> str:
        return (self.now - timedelta(seconds=seconds)).isoformat()

    def operation(self) -> dict[str, Any]:
        names = [step["step"] for step in (self.expected or {}).get("steps", [])]
        begun = [
            {"step": name, "started_at": self.ago(600 - 60 * n)} for n, name in enumerate(names[:3])
        ]
        return {
            "id": self.OPERATION, "type": "project.create", "status": "running",
            "organization_id": self.ORG, "subject": {"name": "notes-app"},
            "step": names[2] if len(names) > 2 else None, "steps": begun, "expected": self.expected,
            "created_at": self.ago(610), "started_at": self.ago(600), "finished_at": None,
        }  # fmt: skip

    def answer(
        self, method: str, path: str, query: dict[str, list[str]], body: dict[str, Any]
    ) -> tuple[int, Any]:
        org, key = self.ORG, self.project
        if (method, path) == ("GET", "/me"):
            if not self.signed_in:
                return 401, {"error": "authentication_failed"}
            return 200, {"username": self.probe["username"],
                         "second_factor": {"required": True, "enabled": True}}  # fmt: skip
        if (method, path) == ("POST", "/sessions"):
            if body.get("password") != self.probe["password"]:
                return 401, {"error": "authentication_failed"}
            if body.get("totp_code") != totp(seed_of(self.probe["totp_seed"]), time.time()):
                return 401, {"error": "second_factor_required"}
            self.signed_in = True
            return 200, {"expires_at": int(time.time()) + 900, "token_use": "access"}
        if path == "/sessions/refresh":
            return (
                (200, {"expires_at": int(time.time()) + 900})
                if self.signed_in
                else (401, {"error": "authentication_failed"})
            )
        if path == "/organizations":
            return 200, {"organizations": [{"id": org, "name": "probe-s37", "role": "owner",
                                            "created_at": self.ago(40 * 86400)}]}  # fmt: skip
        if path == "/projects":
            return 200, {"projects": [{"key": key, "organization_id": org, "state": "ready",
                                       "profile": "small", "region": "us-east"}]}  # fmt: skip
        if path == "/operations":
            return 200, {"operations": [self.operation()]}
        if path == "/plans":
            return 200, {"plans": [self.plan_document(name) for name in self.plans.PLAN_NAMES],
                         "note": self.plans.BETA_SENTENCE}  # fmt: skip
        if path == f"/operations/{self.OPERATION}":
            return 200, self.operation()
        if path == f"/projects/{key}":
            return 200, {"key": key, "organization_id": org, "state": "ready", "profile": "small",
                         "region": "us-east", "template_version": "1.25.0", "idle_sleep_minutes": 20}  # fmt: skip
        if path == f"/projects/{key}/connections":
            return 200, self.connections
        if path == f"/projects/{key}/branches":
            return 200, {"branches": [{"name": "tmp", "state": "ready", "reached_point": self.ago(5400),
                                       "expires_at": (self.now + timedelta(hours=20)).isoformat(),
                                       "pool_host": f"pool.tmp.{self.pooled['host'].split('.', 1)[1]}"}],
                         "notice": "A branch is not backed up; deleting it, or losing the server, loses it."}  # fmt: skip
        if path == f"/projects/{key}/backups":
            return 200, {"project": key, "status": "window", "earliest": self.ago(13 * 86400),
                         "latest": self.ago(90), "last_full_at": self.ago(3 * 86400),
                         "observed_at": self.ago(300)}  # fmt: skip
        if path == f"/projects/{key}/usage":
            return 200, self.usage()
        if path == f"/projects/{key}/insights":
            return 200, {"status": "read", "tuning": "Numbers only; the console gives no advice.",
                         "statements": [{"total_ms": 1834.2, "calls": 412, "mean_ms": 4.45, "rows_per_call": 1.0,
                                         "cache_hit_ratio": 0.998, "role": "customer_app",
                                         "query": "SELECT id, body FROM notes WHERE owner = $1 ORDER BY created_at DESC LIMIT $2"}]}  # fmt: skip
        if path == f"/projects/{key}/monitoring":
            return 200, {"read_at": self.ago(60), "signals": [
                {"name": "connections", "value": 3, "unit": "connections", "observed_at": self.ago(60), "source": "pg_stat_activity"},
                {"name": "database_bytes", "value": 41000000, "unit": "bytes", "observed_at": self.ago(60), "source": "pg_database_size"},
                {"name": "cache_hit_ratio", "unread": "no sample yet", "source": "pg_stat_database"}]}  # fmt: skip
        if path == f"/projects/{key}/diagnostics":
            return 200, {
                "project_key": key,
                "status": "read",
                "read_at": self.ago(120),
                "checks": [],
                "operations": [],
            }
        if path.startswith(f"/organizations/{org}/"):
            return self.organization(path.split("/", 3)[3])
        return 404, {"error": "not_found"}

    def plan_document(self, name: str) -> dict[str, Any]:
        """One plan as `/v1/plans` serves it (`control_service._plan_document`'s shape)."""
        plan = self.plans.PLANS[name]
        return {"plan": name, "status": plan.status, "entitlements": [
            {"name": entitlement, "value": list(spec.value) if isinstance(spec.value, tuple) else spec.value,
             "unit": spec.unit, "enforced": spec.enforced, "reader": spec.reader}
            for entitlement, spec in plan.entitlements.items()]}  # fmt: skip

    def usage(self) -> dict[str, Any]:
        figures = {
            "database_bytes": {"latest": 4.1e9, "latest_at": self.ago(300), "max": 4.2e9},
            "repository_bytes": {"latest": 9.6e8, "latest_at": self.ago(300), "max": 9.6e8},
            "branch_count": {"latest": 1, "latest_at": self.ago(300), "max": 1},
            "branch_bytes": {"latest": 3.1e7, "latest_at": self.ago(300), "max": 3.1e7},
            "customer_connections": {"latest": 3, "latest_at": self.ago(300), "max": 7},
        }
        return {"project_key": self.project, "status": "read", "plan": "free",
                "samples": {"present": 286, "expected": 288},
                "window": {"from": self.ago(86400), "to": self.ago(0)}, "figures": figures,
                "requests": {"increase": 18342},
                "entitlements": [{"name": "storage_gb", "value": 5, "enforced": False, "against": "database_bytes"},
                                 {"name": "agent_calls_per_day", "value": 10000, "enforced": False,
                                  "against": "agent_calls"}]}  # fmt: skip

    def organization(self, tail: str) -> tuple[int, Any]:
        org, key = self.ORG, self.project
        plans = self.plans
        if tail == "plan":
            return 200, {"organization": org, **self.plan_document("free"),
                         "projects_active": {"held": 1, "limit": 1}, "interest": [], "note": plans.BETA_SENTENCE}  # fmt: skip
        if tail.startswith("usage"):
            return 200, {"organization": org, "projects": [self.usage()]}
        if tail.startswith("notifications"):
            notice = lambda n, kind, text, age, op=None: {  # noqa: E731
                "id": f"n{n}", "project": key, "kind": kind, "text": text, "created_at": self.ago(age),
                "operation_id": self.OPERATION if op else None, "operation_type": op}  # fmt: skip
            return 200, {"organization": org, "notifications": [
                notice(1, "operation_started", f"project.create on {key} started", 600, "project.create"),
                notice(2, "operation_succeeded", "branch.create succeeded", 3600, "branch.create"),
                notice(3, "operation_failed", "project.resize failed", 7200, "project.resize"),
                notice(4, "idle_sleep", f"{key} went to sleep", 20000),
                notice(5, "limit_approaching",
                       f"{key} is past 80% of the free plan's storage_gb (shown, not enforced during the beta)", 40000),
                notice(6, "branch_expired", "branch tmp expired", 3 * 86400)]}  # fmt: skip
        if tail == "members":
            return 200, {"members": [
                {"user_id": "u1", "username": self.probe["username"], "display_name": "Probe Owner", "role": "owner"},
                {"user_id": "u2", "username": "member-s37", "display_name": "A Member", "role": "member"}]}  # fmt: skip
        if tail == "invitations":
            return 200, {"invitations": [{"id": "i1", "role": "member", "created_at": self.ago(7200),
                                          "expires_at": (self.now + timedelta(days=6)).isoformat(),
                                          "accepted_at": None, "revoked_at": None}]}  # fmt: skip
        if tail == "keys":
            return 200, {"keys": [{"key_id": "k1", "name": "deploy", "scopes": ["projects:read"],
                                   "created_at": self.ago(86400), "last_used_at": None}]}  # fmt: skip
        return 404, {"error": "not_found"}

    def handle(self, route: Route) -> None:
        request = route.request
        parts = urlsplit(request.url)
        path = parts.path.split("/api/v1", 1)[1]
        body = json.loads(request.post_data) if request.post_data else {}
        status, answer = self.answer(request.method, path, parse_qs(parts.query), body)
        headers = {"content-type": "application/json"}
        if (request.method, path, status) == ("POST", "/sessions", 200):
            headers["set-cookie"] = (
                f"__Host-apg_access={secrets.token_urlsafe(24)}; HttpOnly; Secure; SameSite=Strict; Path=/"
            )
        route.fulfill(status=status, body=json.dumps(answer), headers=headers)


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------


def sign_in(page: Page, base: str, probe: dict[str, str]) -> None:
    """The console's own form, as `sql_walk` signs in."""
    page.goto(f"{base}/console/#/sign-in")
    page.get_by_label("Username").fill(probe["username"])
    page.get_by_label("Password").fill(probe["password"])
    page.get_by_role("button", name="Sign in").click()
    page.get_by_label("Code from your app").wait_for()
    code, _ = fresh_code(seed_of(probe["totp_seed"]))
    page.get_by_label("Code from your app").fill(code)
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("heading", level=1, name="Projects", exact=True).wait_for()


def read(page: Page, url: str, shots: Path | None, name: str) -> dict[str, Any]:
    attempted: list[str] = []
    page.on("request", lambda request: attempted.append(request.url))
    page.goto(url, wait_until="load")
    page.wait_for_function(READY, timeout=60_000)
    page.evaluate("document.fonts.ready.then(() => 1)")
    page.wait_for_timeout(SETTLE_MS)
    snapshot = page.locator("body").aria_snapshot()
    reading: dict[str, Any] = {
        "url": url,
        "title": page.locator("#main h1").first.inner_text().strip(),
        "scroll": page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]"),
        "requests": sorted(set(attempted)),
        "origins": sorted({origin(u) for u in attempted}),
        "violations": page.evaluate("window.__violations"),
        "snapshot_sha256": hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
        "snapshot_lines": len(snapshot.splitlines()),
        "unnamed_controls": unnamed_controls(snapshot),
    }
    page.mouse.click(1, 1)
    rings = []
    for _ in range(TABS):
        page.keyboard.press("Tab")
        rings.append(page.evaluate(RING))
    reading["focus"] = rings
    if shots is not None:
        target = shots / f"{name}.png"
        page.screenshot(path=str(target), full_page=True)
        (shots / f"{name}.aria.yaml").write_text(snapshot, encoding="utf-8")
        reading["screenshot"] = str(target)
    return reading


def walk(arguments: argparse.Namespace) -> int:
    base = arguments.base.rstrip("/")
    probe = json.loads(Path(arguments.probe_file).read_text(encoding="utf-8"))
    held = [probe["password"], probe["totp_seed"]]
    pages = json.loads(Path(arguments.pages).read_text(encoding="utf-8"))
    record: dict[str, Any] = {
        "version": 1, "session": 47, "kind": "console_look",
        "mode": "rehearsal" if arguments.rehearse else "live", "base": base,
        "project": arguments.project, "source_commit": arguments.source_commit,
        "dry": arguments.dry, "account": probe["username"], "pages": [], "started": time.time(),
    }  # fmt: skip
    exit_code = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        record["chromium"] = browser.version
        # ONE context and ONE sign-in for both widths: a second sign-in within
        # the same TOTP step is a replayed code (D2860); each page sets its width.
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        context.add_init_script(INIT)
        if arguments.rehearse:
            context.route(f"{base}/api/v1/**", Fixtures(arguments.project, probe).handle)
        if arguments.plant_foreign:
            # Rehearsal control: the console page gains one third-party image.
            def plant(route: Route) -> None:
                response = route.fetch()
                body = response.text().replace("</main>", f'</main><img src="{FOREIGN}" alt="">', 1)
                route.fulfill(response=response, body=body)

            context.route(f"{base}/console/", plant)
        page = context.new_page()
        answered: dict[str, Any] = {}
        wanted = ("/api/v1/organizations", "/api/v1/operations")
        page.on("response", lambda r: answered.setdefault(urlsplit(r.url).path, r)
                if urlsplit(r.url).path in wanted else None)  # fmt: skip
        try:
            sign_in(page, base, probe)
            page.wait_for_timeout(SETTLE_MS)
            organizations = answered["/api/v1/organizations"].json()["organizations"]
            operations = answered.get("/api/v1/operations")
            served = operations.json().get("operations", []) if operations and operations.ok else []
            environment = page.request.get(f"{base}/console/env.json").json()
        except Exception as error:  # the record names the step, never a value
            record["sign_in"] = {"error": type(error).__name__}
            organizations, served, environment = [], [], {}
            exit_code = 4
        held += [cookie["value"] for cookie in context.cookies()]
        record["relay"] = environment.get("sql_relay")
        allowed = {
            base,
            *([origin(environment["sql_relay"])] if environment.get("sql_relay") else []),
        }
        record["allowed_origins"] = sorted(allowed)
        operation = served[0]["id"] if served else None
        record["operation_read"] = operation is not None
        views = (
            routes(pages, organizations[0]["id"], arguments.project, operation)
            if organizations
            else []
        )
        record["views"] = [view for view, _ in views]
        for width, height in VIEWPORTS:
            for view, fragment in views:
                name = f"{width}-{view}"
                reader = context.new_page()
                reader.set_viewport_size({"width": width, "height": height})
                try:
                    reading = read(reader, f"{base}/console/{fragment}", arguments.shots, name)
                    reading["foreign"] = [o for o in reading["origins"] if o not in allowed]
                except Exception as error:  # the record names the page, never a value
                    reading = {"url": f"{base}/console/{fragment}", "error": type(error).__name__}
                    exit_code = 4
                reading.update({"view": view, "viewport": [width, height]})
                record["pages"].append(reading)
                reader.close()
        page.close()
        context.close()
        # Reduced motion, read once each way, through the console's own stylesheet.
        motion = {}
        for preference in ("reduce", "no-preference"):
            context = browser.new_context(reduced_motion=preference)
            if arguments.rehearse:
                context.route(f"{base}/api/v1/**", Fixtures(arguments.project, probe).handle)
            page = context.new_page()
            page.goto(f"{base}/console/#/sign-in", wait_until="load")
            page.wait_for_function("() => document.styleSheets.length > 0")
            motion[preference] = page.evaluate(MOTION)
            context.close()
        record["motion"] = motion
        browser.close()
    record["exit"] = exit_code
    record["seconds"] = round(time.time() - record.pop("started"), 1)
    text = json.dumps(record, indent=1, sort_keys=True) + "\n"
    if any(value and value in text for value in held):
        print("console_look: the record would hold a secret; nothing written", file=sys.stderr)
        return 6
    if arguments.dry:
        print(
            f"console_look: dry walk exit {exit_code}; {len(record['pages'])} pages read, no record"
        )
        return exit_code
    write_private(Path(arguments.record), text)
    print(f"console_look: {record['mode']} walk exit {exit_code}; record {arguments.record}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="console_look", allow_abbrev=False)
    parser.add_argument("--base", required=True, help="the console's origin")
    parser.add_argument(
        "--probe-file", required=True, help="the probe owner's file (~/s37/probe.json)"
    )
    parser.add_argument("--pages", default="/repo/services/console/public/pages.json")
    parser.add_argument("--project", default="slot3-prod")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--shots", type=Path, default=None)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--rehearse", action="store_true")
    parser.add_argument("--plant-foreign", action="store_true")
    parser.add_argument("--dry", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.plant_foreign and not arguments.rehearse:
        print("console_look: --plant-foreign is a rehearsal's control", file=sys.stderr)
        return 2
    if not arguments.dry and (arguments.record is None or arguments.record.exists()):
        print(
            "console_look: give a --record that does not exist yet (one walk per record)",
            file=sys.stderr,
        )
        return 2
    if not arguments.dry and not arguments.rehearse and not arguments.source_commit:
        print(
            "console_look: a live record names the deployed commit (--source-commit)",
            file=sys.stderr,
        )
        return 2
    return walk(arguments)


if __name__ == "__main__":
    raise SystemExit(main())

"""The journey: a membership link to a project made, connected and read, in Chromium.

Session 46 (ADR 0290 §9, ADR 0291, D2871, D2872; `JRN-001`). Run inside the
pinned Playwright image by Run 7's launcher (never collected: no `test_`
prefix). From the membership invitation link the probe owner minted (D2871) it
makes an account (J1-J3), its own organisation (J4) and, as that
organisation's owner, its second factor from the page's own text (J5); then the
console's *New project* -- the token read from the shown-once panel into a 0600
file, the panel dismissed (J6) -- the creation followed to `succeeded` (J7),
`customer_app`'s password set on Connect (J8), the SQL editor's `SELECT 1` (J10),
the five readings (J11), the support bundle's checks (J12), and sign-out (J13).
J9 (the string connects) is the live proof's; J14 the lifecycle record's.

**One record** (`journey_record.Journey`), written 0600 into `--out`, holds no
secret: the link, the password, the seed, the token and the cookies are held
and searched for before it is written (exit 6). The three a later step needs
go to their own 0600 files: `handoff-token` (the lifecycle's claim,
`--token-file`), `password` (J9's connection), `totp-seed` (the lifecycle's
sign-in as this account, D2872). Every request the journey's page attempted is
recorded by origin and must stay on the console's and the relay's (exit 5).

`--rehearse` answers every `/api/v1` call from a stand-in inside the browser and
the editor's socket with `sql_walk`'s fake PostgreSQL; `--leak` makes the
stand-in put the account's password into the page (exit 6); `--plant-foreign`
adds one request to a foreign origin (exit 5). `--dry` stops after J5, before
anything consumes a slot.

Exit codes: 0 walked and the record is clean; 2 usage; 4 a step failed (the
record says which); 5 the record has a problem (`journey_record.problems`);
6 the record would have held a secret.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import secrets
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from console_walk import STEP_SECONDS, fresh_code, seed_of, totp, write_private
from journey_record import BUNDLE_CHECKS, DRY_STEPS, Journey, now, problems
from playwright.sync_api import Page, Route, sync_playwright
from sql_walk import FakeBackend, settle, tables

REHEARSAL_RELAY = "wss://sql.rehearsal.test"
REHEARSAL_SITE = "https://site.rehearsal.test"
FOREIGN = "https://foreign.rehearsal.test"
DIGEST_META = re.compile(r'<meta name="apg-site-digest" content="([0-9a-f]{64})">')
#: A creation's steps as the stand-in serves them (the plane's own are
#: `operation_steps.STEPS["project.create"]`; the tracker draws whatever is served).
CREATION_STEPS = [
    ("allocate", "Reserving a server slot"),
    ("admit", "Checking there is room on the server"),
    ("deploy-1", "Starting the database"),
    ("admin", "Creating your administrator"),
    ("ports", "Opening the two connection doors"),
    ("deploy-2", "Starting the API and storage"),
    ("unit", "Making it start again after a reboot"),
    ("backup", "Taking the first full backup"),
    ("registry", "Recording the project"),
]
#: The operation the console shows as its tracker's address (ADR 0296 decision 5).
TRACKER = re.compile(r"#/operations/([0-9a-f-]{36})$")


def ago(seconds: float) -> str:
    """A time `seconds` before now, in the plane's ISO form."""
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


# ---------------------------------------------------------------------------
# --rehearse: the control API answered inside the browser
# ---------------------------------------------------------------------------


class Fixtures:
    """Every `/api/v1` answer the journey meets, shaped from the control
    snapshot and the views that read it. State moves as the real plane's
    does: a member needs no factor, an owner does; a creation runs, then
    succeeds with its key; the support bundle is unread before its first pass."""

    def __init__(self, leak: bool) -> None:
        self.leak = leak
        self.seed = secrets.token_bytes(20)
        self.secret = base64.b32encode(self.seed).decode("ascii").rstrip("=")
        self.account: dict[str, str] | None = None
        self.signed_in = False
        self.factor = False
        self.confirm_step: int | None = None
        self.organizations = [
            {
                "id": "31121d7b-1aa3-4206-8f13-d81157c1beaf",
                "name": "probe-s37",
                "role": "member",
                "created_at": now(),
            }
        ]
        self.operation = str(uuid.uuid4())
        self.polls = 0
        self.key = "slot11-prod"
        self.created_in: str | None = None
        self.bundle_reads = 0
        self.doors = {
            "pooled": "apg_slot11_prod_customer_app",
            "direct": "apg_slot11_prod_customer_admin",
        }
        self.digest_seen = ""

    def owner(self) -> bool:
        return any(org["role"] == "owner" for org in self.organizations)

    def answer(
        self, method: str, path: str, body: dict[str, Any]
    ) -> tuple[int, Any, dict[str, str]]:
        headers: dict[str, str] = {}
        key = self.key
        if (method, path) == ("GET", "/me"):
            if not self.signed_in or not self.account:
                return 401, {"error": "authentication_failed"}, headers
            return (
                200,
                {
                    "username": self.account["username"],
                    "second_factor": {"required": self.owner(), "enabled": self.factor},
                },
                headers,
            )
        if (method, path) == ("POST", "/invitations/accept"):
            self.account = {"username": body["username"], "password": body["password"]}
            return 200, {"username": body["username"], "role": "member"}, headers
        if (method, path) == ("POST", "/sessions"):
            ok = bool(self.account) and body.get("password") == self.account["password"]
            if ok and self.factor:
                step = int(time.time()) // STEP_SECONDS
                ok = (
                    body.get("totp_code") == totp(self.seed, time.time())
                    and step != self.confirm_step
                )
                if not ok:
                    return 401, {"error": "second_factor_required"}, headers
            if not ok:
                return 401, {"error": "authentication_failed"}, headers
            self.signed_in = True
            headers["set-cookie"] = (
                f"__Host-apg_access={secrets.token_urlsafe(24)}; "
                "HttpOnly; Secure; SameSite=Strict; Path=/"
            )
            return 200, {"expires_at": int(time.time()) + 900, "token_use": "access"}, headers
        if (method, path) == ("POST", "/sessions/refresh"):
            return (
                (200, {"expires_at": int(time.time()) + 900}, headers)
                if self.signed_in
                else (401, {"error": "authentication_failed"}, headers)
            )
        if (method, path) == ("POST", "/me/totp"):
            svg = "%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%2F%3E"
            return (
                201,
                {
                    "secret": self.secret,
                    "otpauth_uri": "otpauth://totp/x",
                    "otpauth_qr": f"data:image/svg+xml;charset=utf-8,{svg}",
                },
                headers,
            )
        if (method, path) == ("POST", "/me/totp/confirm"):
            if body.get("totp_code") != totp(self.seed, time.time()):
                return 422, {"error": "second_factor_invalid"}, headers
            self.factor, self.confirm_step = True, int(time.time()) // STEP_SECONDS
            self.signed_in = False  # confirming ends every session (the server's rule)
            return 200, {"enabled": True, "sessions_ended": 1}, headers
        if not self.signed_in:
            return 401, {"error": "authentication_failed"}, headers
        if (method, path) == ("GET", "/organizations"):
            listed = [dict(org) for org in self.organizations]
            if self.leak and self.account:
                listed[0]["name"] = self.account["password"]
            return 200, {"organizations": listed}, headers
        if (method, path) == ("POST", "/organizations"):
            created = {
                "id": str(uuid.uuid4()),
                "name": body["name"],
                "role": "owner",
                "created_at": now(),
            }
            self.organizations.append(created)
            return 201, created, headers
        if (method, path) == ("GET", "/operations"):
            return 200, {"operations": []}, headers
        if (method, path) == ("GET", "/projects"):
            return 200, {"projects": [self._project()] if self.polls >= 3 else []}, headers
        if (method, path) == ("POST", "/projects"):
            assert set(body) == {
                "organization",
                "name",
                "profile",
                "admin_username",
                "handoff_sha256",
            }, sorted(body)
            assert re.fullmatch(r"[0-9a-f]{64}", body["handoff_sha256"])
            self.created_in = body["organization"]
            return (
                202,
                {"operation": {"id": self.operation, "status": "pending", "project_key": None}},
                headers,
            )
        if (method, path) == ("GET", f"/operations/{self.operation}"):
            # Shaped as the plane serves an operation since Session 47 Run 3
            # (ADR 0296): its step log, its subject and what is expected of it.
            self.polls += 1
            done = self.polls >= 3
            began = [("allocate", 30), ("admit", 29), ("deploy-1", 28)]
            if done:
                began += [(step, 5) for step, _ in CREATION_STEPS[3:]]
            return (
                200,
                {
                    "id": self.operation,
                    "organization_id": self.created_in,
                    "type": "project.create",
                    "status": "succeeded" if done else "running",
                    "step": "registry" if done else "deploy-1",
                    "progress": 100 if done else 30,
                    "project_key": key,
                    "error_code": None,
                    "created_at": ago(31),
                    "started_at": ago(30),
                    "finished_at": ago(0) if done else None,
                    "steps": [
                        {"step": step, "started_at": ago(seconds)} for step, seconds in began
                    ],
                    "subject": {"name": "Journey s46", "profile": "small"},
                    "expected": {
                        "steps": [
                            {"step": step, "label": label, "typical_seconds": 1.0}
                            for step, label in CREATION_STEPS
                        ],
                        "typical_seconds": {"low": 1375.9, "high": 1708.4},
                        "bound_seconds": 1800,
                    },
                },
                headers,
            )
        if (method, path) == ("GET", "/operations/credential-rehearsal"):
            return 200, {"id": "credential-rehearsal", "status": "succeeded"}, headers
        if (method, path) == ("GET", f"/projects/{key}"):
            return 200, self._project(), headers
        if (method, path) == ("GET", f"/projects/{key}/connections"):
            door = {
                "port": 5432,
                "database": "slot11_prod",
                "sslmode": "verify-full",
                "connection_limit": 2,
            }
            return (
                200,
                {
                    "project": key,
                    "pooled": {
                        **door,
                        "host": "pool.slot11.rehearsal.test",
                        "user": self.doors["pooled"],
                    },
                    "direct": {
                        **door,
                        "host": "direct.slot11.rehearsal.test",
                        "user": self.doors["direct"],
                    },
                    "password": "<password from your file>",
                    "snippets": {},
                },
                headers,
            )
        if (method, path) == ("POST", f"/projects/{key}/credentials"):
            assert body["role"] == "customer_app" and body["verifier"].startswith(
                "SCRAM-SHA-256$4096:"
            )
            return 202, {"operation": {"id": "credential-rehearsal", "status": "pending"}}, headers
        if (method, path) == ("GET", f"/projects/{key}/usage"):
            return (
                200,
                {
                    "project_key": key,
                    "status": "read",
                    "window": {"from": now(), "to": now()},
                    "samples": {"present": 0, "expected": 288},
                    "figures": {},
                    "requests": None,
                    "entitlements": [],
                },
                headers,
            )
        if (method, path) == ("GET", f"/projects/{key}/insights"):
            return 200, {"status": "read", "statements": [], "tuning": "Numbers only."}, headers
        if (method, path) == ("GET", f"/projects/{key}/monitoring"):
            return (
                200,
                {
                    "read_at": now(),
                    "signals": [
                        {
                            "name": "connections",
                            "unread": "no sample yet",
                            "source": "the reconciler",
                        }
                    ],
                },
                headers,
            )
        if (method, path) == ("GET", "/plans"):
            return (
                200,
                {
                    "plans": [
                        {
                            "plan": "free",
                            "status": "active",
                            "entitlements": [
                                {
                                    "name": "projects_active",
                                    "value": 1,
                                    "unit": "projects",
                                    "enforced": True,
                                }
                            ],
                        }
                    ],
                    "note": "Free in the beta.",
                },
                headers,
            )
        if method == "GET" and path.endswith("/plan") and path.startswith("/organizations/"):
            # As the plane counts (D2981): the probe's organisation holds slot3,
            # the journey's holds its creation from the moment it is recorded.
            org = path.split("/")[2]
            held = int(org in (self.organizations[0]["id"], self.created_in))
            return (
                200,
                {
                    "plan": "free",
                    "status": "active",
                    "entitlements": [],
                    "projects_active": {"held": held, "limit": 1},
                },
                headers,
            )
        if (
            method == "GET"
            and path.endswith("/notifications")
            and path.startswith("/organizations/")
        ):
            return 200, {"notifications": []}, headers
        if (method, path) == ("GET", f"/projects/{key}/diagnostics"):
            self.bundle_reads += 1
            if self.bundle_reads < 2:
                return (
                    200,
                    {
                        "status": "could_not_determine",
                        "reason": "no reading yet",
                        "checks": [],
                        "operations": [],
                    },
                    headers,
                )
            checks = [
                {
                    "name": f"check-{n:02d}",
                    "verdict": "ok",
                    "detail": "fine",
                    "read_at": now(),
                    "age_seconds": 40 + n,
                    "stale": False,
                }
                for n in range(1, BUNDLE_CHECKS + 1)
            ]
            return (
                200,
                {"status": "read", "read_at": now(), "checks": checks, "operations": []},
                headers,
            )
        return 404, {"error": "not_found"}, headers

    def _project(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "organization_id": self.created_in,
            "state": "ready",
            "profile": "small",
            "region": "us-east-rehearsal",
            "source_commit": "c" * 40,
        }

    def handle(self, route: Route) -> None:
        request = route.request
        path = urlsplit(request.url).path.split("/api/v1", 1)[1]
        body = json.loads(request.post_data) if request.post_data else {}
        if (request.method, path) == ("DELETE", "/sessions/current"):
            self.signed_in = False
            route.fulfill(
                status=204, headers={"set-cookie": "__Host-apg_access=; Max-Age=0; Path=/; Secure"}
            )
            return
        status, answer, headers = self.answer(request.method, path, body)
        route.fulfill(
            status=status,
            body=json.dumps(answer),
            headers={"content-type": "application/json", **headers},
        )


# ---------------------------------------------------------------------------
# The journey
# ---------------------------------------------------------------------------


def read_site_digest(browser: Any, site: str, rehearse: bool) -> str:
    """The `apg-site-digest` meta of the site's home page, read in a context of
    its own so the journey's origin reading holds the console's alone."""
    context = browser.new_context()
    if rehearse:
        page_body = '<!doctype html><meta name="apg-site-digest" content="' + "0" * 64 + '">'
        context.route(
            f"{site}/**",
            lambda route: route.fulfill(status=200, body=page_body, content_type="text/html"),
        )
    page = context.new_page()
    page.goto(f"{site}/", wait_until="load")
    found = DIGEST_META.search(page.content())
    context.close()
    if not found:
        raise RuntimeError("the site's home page carries no apg-site-digest meta")
    return found.group(1)


def heading(page: Page, *names: str, timeout: float = 30_000) -> str:
    """Wait for one of the level-1 headings the console draws, and say which."""
    wanted = page.get_by_role("heading", level=1, name=names[0], exact=True)
    for name in names[1:]:
        wanted = wanted.or_(page.get_by_role("heading", level=1, name=name, exact=True))
    wanted.first.wait_for(timeout=timeout)
    return wanted.first.inner_text().strip()


def walk(arguments: argparse.Namespace) -> int:
    out = Path(arguments.out)
    link = Path(arguments.link_file).read_text(encoding="utf-8").strip()
    parts = urlsplit(link)
    base = (arguments.base or f"{parts.scheme}://{parts.netloc}").rstrip("/")
    relay = REHEARSAL_RELAY if arguments.rehearse else arguments.relay
    site = REHEARSAL_SITE if arguments.rehearse else arguments.site
    journey = Journey(base, relay, site, "rehearsal" if arguments.rehearse else "live")
    journey.held += [link, parts.fragment]
    username = f"journey-s46-{secrets.token_hex(3)}"
    password = base64.urlsafe_b64encode(secrets.token_bytes(24)).decode("ascii").rstrip("=")
    journey.held.append(password)
    record = journey.record
    record.update(
        account=username,
        organization_name=arguments.organization,
        token_file="handoff-token",  # noqa: S106 -- a file's name, not its content
        password_file="password",  # noqa: S106 -- a file's name, not its content
        seed_file="totp-seed",
        account_password_file="account-password",  # noqa: S106 -- a file's name, not its content
    )
    fixtures = Fixtures(arguments.leak) if arguments.rehearse else None
    exit_code = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        record["chromium"] = browser.version
        context = browser.new_context()
        context.on("request", lambda request: journey.saw(request.url))
        backend = None
        if fixtures is not None:
            context.route(f"{base}/api/v1/**", fixtures.handle)
            backend = FakeBackend({})
            context.route_web_socket(re.compile(r"^wss://sql\.rehearsal\.test/"), backend.handle)
            if arguments.plant_foreign:

                def plant(route: Route) -> None:
                    served = route.fetch()
                    text = served.text().replace(
                        "</body>", f'<img src="{FOREIGN}/planted.png"></body>'
                    )
                    route.fulfill(response=served, body=text)

                context.route(f"{base}/console/", plant)
        page = context.new_page()
        try:

            def j01() -> None:
                record["site_digest"] = read_site_digest(browser, site, arguments.rehearse)
                page.goto(link.replace(f"{parts.scheme}://{parts.netloc}", base))
                heading(page, "Create your account")
                record["address_bar_clean"] = "#" not in page.url and parts.fragment not in page.url

            journey.step("j01", j01)

            def j02() -> None:
                page.get_by_label("Username").fill(username)
                page.get_by_label("Display name").fill(username)
                page.get_by_label("Password", exact=True).fill(password)
                page.get_by_label("Password again").fill(password)
                page.get_by_role("button", name="Create your account").click()
                heading(page, "Projects")
                write_private(out / "account-password", password + "\n")

            journey.step("j02", j02)
            journey.held += [cookie["value"] for cookie in context.cookies()]

            def j03() -> None:
                named = [h.inner_text() for h in page.locator("#main h2").all()]
                if not named:
                    raise RuntimeError("the overview named no organisation")
                record["joined"] = named

            journey.step("j03", j03)

            def j04() -> str:
                page.get_by_role("link", name="New organisation").click()
                heading(page, "New organisation")
                page.get_by_label("Name", exact=True).fill(arguments.organization)
                page.get_by_role("button", name="Create", exact=True).click()
                page.wait_for_url(re.compile(r"#/org/[0-9a-f-]{36}/settings$"))
                return urlsplit(page.url).fragment.split("/")[2]

            organization = journey.step("j04", j04)
            record["organization"] = organization
            seed_holder: dict[str, bytes] = {}

            def j05() -> None:
                heading(page, "Set up your second factor")
                page.locator("img.qr").wait_for()
                secret = page.locator("code.secret").first.inner_text().strip()
                seed = seed_of(secret)
                journey.held += [secret, seed.hex()]
                seed_holder["seed"] = seed
                write_private(out / "totp-seed", secret + "\n")
                code, step = fresh_code(seed)
                page.get_by_label("Code from your app").fill(code)
                page.get_by_role("button", name="Confirm").click()
                heading(page, "Sign in")
                page.get_by_label("Username").fill(username)
                page.get_by_label("Password", exact=True).fill(password)
                page.get_by_role("button", name="Sign in").click()
                page.get_by_label("Code from your app").wait_for()
                next_code, _ = fresh_code(seed, after_step=step)
                page.get_by_label("Code from your app").fill(next_code)
                page.get_by_role("button", name="Sign in").click()
                heading(page, "Projects")

            journey.step("j05", j05)
            journey.held += [cookie["value"] for cookie in context.cookies()]
            if arguments.dry:
                record["dry"] = True
            else:
                run_the_rest(arguments, journey, page, context, backend, organization, out)
        except Exception as error:
            # Playwright's message names a selector and a timeout, never a value
            # this journey typed; the record keeps the type alone.
            failed = record["steps"][-1]["step"] if record["steps"] else "-"
            print(
                f"journey_walk: step {failed} failed: {str(error).splitlines()[0][:300]}",
                file=sys.stderr,
            )
            exit_code = 4
        finally:
            browser.close()
    record["completed_at"] = now()
    record["exit"] = exit_code
    if journey.leaks():
        print(
            f"journey_walk: the record would hold {journey.leaks()} secret value(s); not written",
            file=sys.stderr,
        )
        return 6
    found = problems(record, dry=bool(arguments.dry)) if exit_code == 0 else []
    record["problems"] = found
    write_private(out / "record.json", json.dumps(record, indent=1, sort_keys=True) + "\n")
    if exit_code == 0 and found:
        print(f"journey_walk: the record has {len(found)} problem(s): {found}", file=sys.stderr)
        exit_code = 5
    print(f"journey_walk: {record['mode']} journey exit {exit_code}; record {out / 'record.json'}")
    return exit_code


def run_the_rest(
    arguments: argparse.Namespace,
    journey: Journey,
    page: Page,
    context: Any,
    backend: FakeBackend | None,
    organization: str,
    out: Path,
) -> None:
    """J6-J13: the steps that consume a slot."""
    record = journey.record
    base = record["base"]

    def j06() -> str:
        section = page.locator("section").filter(
            has=page.get_by_role(
                "heading", level=2, name=re.compile(re.escape(arguments.organization))
            )
        )
        section.get_by_role("link", name="New project").click()
        heading(page, "New project")
        page.get_by_label("Name", exact=True).fill(arguments.project_name)
        page.get_by_label("Profile").select_option("small")
        page.get_by_label("Administrator's username", exact=True).fill(arguments.admin_username)
        page.get_by_role("button", name="Create project").click()
        page.locator(".once code.secret").wait_for(timeout=120_000)
        token = page.locator(".once code.secret").first.inner_text().strip()
        journey.held.append(token)
        write_private(out / "handoff-token", token + "\n")
        # Session 47 Run 5 (ADR 0296 decision 5): on acceptance the address IS
        # the creation's tracker, so the operation is read from it.
        tracked = TRACKER.search(page.url)
        if not tracked:
            raise RuntimeError("the accepted creation's address is not its tracker")
        record["token_length"] = len(token)
        page.get_by_role("button", name="I've saved it, or I don't need it").click()
        page.locator("#main .once-done").wait_for()
        record["token_gone_after_dismissal"] = token not in page.content()
        return tracked.group(1)

    record["operation_id"] = journey.step("j06", j06)
    accepted = time.monotonic()

    def j07() -> str:
        done = page.get_by_role("link", name="Connect to it").or_(page.locator("#main p.refusal"))
        done.first.wait_for(timeout=arguments.create_timeout * 1000)
        if page.locator("#main p.refusal").count():
            raise RuntimeError("the creation did not succeed")
        return (
            page.locator("#main p", has_text="is ready").locator("code").first.inner_text().strip()
        )

    key = journey.step("j07", j07)
    record["project_key"] = key
    record["create_seconds"] = round(time.monotonic() - accepted, 1)

    def j08() -> tuple[str, str]:
        # Session 47 Run 6 (D2956): Connect's step 2, the pooled door chosen by default.
        page.goto(f"{base}/console/#/projects/{key}/connect")
        page.get_by_role("button", name="Make a new password for the pooled door").click()
        page.get_by_role("heading", name="Your new password for the pooled door").wait_for(
            timeout=300_000
        )
        shown = page.locator("#main .once code.secret").all()
        return shown[0].inner_text().strip(), shown[1].inner_text().strip()

    rotated, string = journey.step("j08", j08)
    journey.held += [rotated, string]
    write_private(out / "password", rotated + "\n")
    parts = urlsplit(string)
    record["string_parameters"] = {name: value[0] for name, value in parse_qs(parts.query).items()}
    record["string"] = {
        "host": parts.hostname,
        "port": parts.port,
        "user": parts.username,
        "database": parts.path.lstrip("/"),
        "holds_the_password": rotated in string,
    }
    if backend is not None:
        backend.users[str(parts.username)] = rotated

    def j10() -> list[list[str]]:
        page.goto(f"{base}/console/#/projects/{key}/sql")
        page.get_by_role("button", name="Connect", exact=True).wait_for()
        page.get_by_label("Door").select_option("pooled")
        page.get_by_label("Password", exact=True).fill(rotated)
        page.get_by_role("button", name="Connect", exact=True).click()
        if not settle(page).startswith("Connected"):
            raise RuntimeError("the editor did not connect")
        page.locator("#main textarea").fill("SELECT 1")
        page.get_by_role("button", name="Run").click()
        settle(page)
        rows = tables(page)
        page.get_by_role("button", name="Disconnect").click()
        if not rows or rows[0] != [["1"]]:
            raise RuntimeError("SELECT 1 did not answer 1")
        return rows[0]

    record["editor_rows"] = journey.step("j10", j10)

    def j11() -> dict[str, Any]:
        views: dict[str, Any] = {}
        for name, route, title in (
            ("usage", f"#/projects/{key}/usage", "Usage"),
            ("insights", f"#/projects/{key}/insights", "Slowest queries"),
            ("monitoring", f"#/projects/{key}/monitoring", "Monitoring"),
            ("plan", f"#/org/{organization}/plan", "Plan and usage"),
            ("notifications", f"#/org/{organization}/notifications", "Notifications"),
        ):
            page.goto(f"{base}/console/{route}")
            said = heading(page, title, "Something was refused")
            # Session 47 (ADR 0295): the page template draws the title, the
            # purpose and the help link; what the VIEW drew is `.page-body`.
            body = page.locator("#main .page-body").inner_text().strip()
            views[name] = {"read": said == title and bool(body), "words": len(body.split())}
        if not all(view["read"] for view in views.values()):
            raise RuntimeError(f"a view rendered nothing: {views}")
        return views

    record["views"] = journey.step("j11", j11)

    def j12() -> dict[str, Any]:
        deadline = time.monotonic() + arguments.bundle_timeout
        first = True
        while True:
            # ONE navigation inside the wait: a reload after the goto would drop
            # the body the wait captured (rehearsal, Network.getResponseBody).
            with page.expect_response(
                lambda r: urlsplit(r.url).path.endswith(f"/projects/{key}")
            ) as got:
                if first:
                    page.goto(f"{base}/console/#/projects/{key}/settings")
                else:
                    page.reload(wait_until="load")
            first = False
            record["source_commit"] = got.value.json().get("source_commit")
            heading(page, "Settings")
            page.locator("#main strong", has_text="Support bundle").wait_for()
            rows = page.locator("#main table tbody tr").all()
            cells = [[c.inner_text().strip() for c in r.locator("td").all()] for r in rows]
            ages = [row[3] if len(row) > 3 else "" for row in cells]
            aged = sum(1 for age in ages if re.fullmatch(r"\d+ s ago", age))
            if len(rows) >= BUNDLE_CHECKS or time.monotonic() > deadline:
                said = page.locator("#main strong", has_text="Support bundle").count() == 1
                shown = [
                    {"name": row[0], "verdict": row[1], "detail": row[2], "age": row[3]}
                    for row in cells
                    if len(row) == 4
                ]
                return {"checks": len(rows), "aged": aged, "said": said, "rows": shown}
            time.sleep(arguments.bundle_interval)

    record["support_bundle"] = journey.step("j12", j12)

    def j13() -> None:
        page.goto(f"{base}/console/")
        heading(page, "Projects")
        # Session 47 (ADR 0295): Sign out is in the account menu.
        page.locator("details.account > summary").click()
        page.get_by_role("button", name="Sign out").click()
        heading(page, "Sign in")
        record["cookies_after_sign_out"] = len(
            [c for c in context.cookies() if c["name"].startswith("__Host-apg_")]
        )

    journey.step("j13", j13)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="journey_walk", allow_abbrev=False)
    parser.add_argument("--link-file", required=True, help="the membership invitation link (0600)")
    parser.add_argument("--out", required=True, help="an existing directory for the four files")
    parser.add_argument("--base", help="the console's origin (default: the link's)")
    parser.add_argument("--relay", default="wss://sql.agenticpostgresql.com")
    parser.add_argument("--site", default="https://agenticpostgresql.com")
    parser.add_argument("--organization", default="lifecycle-s46")
    parser.add_argument("--project-name", default="Journey s46")
    parser.add_argument("--admin-username", default="journey.admin")
    parser.add_argument("--create-timeout", type=int, default=3900)
    parser.add_argument("--bundle-timeout", type=int, default=1800)
    parser.add_argument("--bundle-interval", type=int, default=60)
    parser.add_argument("--dry", action="store_true", help=f"stop after {DRY_STEPS[-1][0]}")
    parser.add_argument("--rehearse", action="store_true")
    parser.add_argument("--leak", action="store_true", help="rehearsal: a fixture leaks a password")
    parser.add_argument("--plant-foreign", action="store_true", help="rehearsal: a foreign request")
    arguments = parser.parse_args(argv)
    if (arguments.leak or arguments.plant_foreign) and not arguments.rehearse:
        parser.error("--leak and --plant-foreign are rehearsal fixtures")
    out = Path(arguments.out)
    if not out.is_dir():
        parser.error(f"{out} is not a directory")
    taken = [
        name
        for name in ("record.json", "handoff-token", "password", "totp-seed", "account-password")
        if (out / name).exists()
    ]
    if taken:
        parser.error(f"{out} already holds {taken}; one journey per directory")
    return walk(arguments)


if __name__ == "__main__":
    raise SystemExit(main())

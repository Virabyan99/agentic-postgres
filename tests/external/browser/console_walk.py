"""The browser walk: an invitation link to a working connection string, in a real Chromium.

Session 43 (ADR 0280, D2668, D2669, D2675). Run inside the pinned Playwright
image by `~/s43/run8/s43-walk.sh` (never collected: no `test_` prefix). It
opens the invitation link, creates an account, enrols the second factor from
the page's own QR text, signs in, takes the live CSRF readings with its real
session (statuses only), rotates a project's `customer_app` password from the
Connect page, reads the password and the pooled string once, reloads to see
them gone, signs out, and writes ONE record the external proofs read through
`APG_CONSOLE_RECORD_FILE`. Since Session 47 Run 6 (D2956) Connect is three
steps: the record also names the client tabs served, how many snippets held
the new password (inside the shown-once box) and how many values outside it
did (0), and that *I have saved the password* removed it before the reload.

**The record holds no secret** (D2416): every password, the TOTP seed, the
invitation token and the cookie values stay in variables, and before the
record is written its JSON is searched for each -- exit 6 if one is there. The
rotated password goes only to `--password-out` (0600), for the connection proof.

`--rehearse` answers every `/api/v1` call from fixtures inside the page (the
DOM path, the TOTP timing, the self-check); `--leak` makes a fixture put the
account's password into the page, which the self-check must refuse (exit 6).

Exit codes: 0 walked; 2 usage; 4 a step failed (the record says which);
6 the record would have held a secret.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import importlib.util
import json
import os
import secrets
import struct
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Page, Route, sync_playwright

STEP_SECONDS = 30
#: The server's snippet module, standard library only (its own docstring):
#: the rehearsal serves what it builds. The checkout is beside this driver.
SNIPPETS = (
    Path(__file__).resolve().parents[3] / "services" / "auth-api" / "app" / "connection_snippets.py"
)


def snippet_module() -> Any:
    spec = importlib.util.spec_from_file_location("connection_snippets", SNIPPETS)
    assert spec is not None and spec.loader is not None, SNIPPETS
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def totp(seed: bytes, at: float) -> str:
    counter = struct.pack(">Q", int(at) // STEP_SECONDS)
    digest = hmac.new(seed, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def seed_of(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def fresh_code(seed: bytes, *, after_step: int | None = None) -> tuple[str, int]:
    """A code with at least 5 s of its window left, from a step after `after_step`."""
    while True:
        now = time.time()
        step = int(now) // STEP_SECONDS
        if (after_step is None or step > after_step) and STEP_SECONDS - (now % STEP_SECONDS) >= 5:
            return totp(seed, now), step
        time.sleep(0.5)


def write_private(path: Path, content: str | bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    data = content.encode("utf-8") if isinstance(content, str) else content
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


class Walk:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.record: dict[str, Any] = {"version": 1, "session": 43, "base": self.base, "steps": []}
        self.held: list[str] = []  # every secret value, for the self-check only

    def step(self, name: str, work: Any) -> Any:
        started = time.monotonic()
        try:
            result = work()
        except Exception as error:  # the record names the failed step, never a value
            self.record["steps"].append({"name": name, "outcome": "failed",
                                         "error": type(error).__name__,
                                         "start": started, "end": time.monotonic()})  # fmt: skip
            raise
        self.record["steps"].append({"name": name, "outcome": "ok", "start": started,
                                     "end": time.monotonic()})  # fmt: skip
        return result

    def self_check(self) -> None:
        text = json.dumps(self.record)
        leaked = [index for index, value in enumerate(self.held) if value and value in text]
        if leaked:
            print(f"console_walk: the record would hold {len(leaked)} secret value(s); not written",
                  file=sys.stderr)  # fmt: skip
            raise SystemExit(6)


# ---------------------------------------------------------------------------
# --rehearse: the API answered inside the page
# ---------------------------------------------------------------------------


class Fixtures:
    """Every `/api/v1` answer the walk meets, shaped from the control snapshot."""

    def __init__(self, project: str, leak: bool) -> None:
        self.project = project
        self.leak = leak
        self.seed = secrets.token_bytes(20)
        self.secret = base64.b32encode(self.seed).decode("ascii").rstrip("=")
        self.account: dict[str, Any] | None = None
        self.factor = False
        self.confirm_step: int | None = None
        # Loaded once, before the browser starts: a stand-in that read the file
        # on every request could fail inside the route handler mid-walk.
        self.snippets = snippet_module()

    def handle(self, route: Route) -> None:
        request = route.request
        path = urlsplit(request.url).path.split("/api/v1", 1)[1]
        body = json.loads(request.post_data) if request.post_data else {}
        method = request.method
        status, answer, headers = 404, {"error": "not_found"}, {}
        if (method, path) == ("GET", "/me"):
            status, answer = (401, {"error": "authentication_failed"}) if not self.account else (
                200, {"username": self.account["username"],
                      "second_factor": {"required": True, "enabled": self.factor}})  # fmt: skip
        elif (method, path) == ("POST", "/invitations/accept"):
            self.account = {"username": body["username"], "password": body["password"]}
            status, answer = 200, {"username": body["username"], "role": "admin"}
        elif (method, path) == ("POST", "/sessions"):
            ok = self.account and body.get("password") == self.account["password"]
            if ok and self.factor:
                code = body.get("totp_code")
                step = int(time.time()) // STEP_SECONDS
                ok = code == totp(self.seed, time.time()) and step != self.confirm_step
            status, answer = (200, {"expires_at": int(time.time()) + 900, "token_use": "access"}) \
                if ok else (401, {"error": "second_factor_required"})  # fmt: skip
            if ok:
                # Random, as a real session token is: a fixed word could equal
                # text the record legitimately holds and trip the self-check.
                headers["set-cookie"] = (f"__Host-apg_access={secrets.token_urlsafe(24)}; "
                                         "HttpOnly; Secure; SameSite=Strict; Path=/")  # fmt: skip
        elif (method, path) == ("POST", "/me/totp"):
            svg = "%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%2F%3E"
            qr = f"data:image/svg+xml;charset=utf-8,{svg}"
            status, answer = 201, {"secret": self.secret, "otpauth_uri": "otpauth://totp/x",
                                   "otpauth_qr": qr}  # fmt: skip
        elif (method, path) == ("POST", "/me/totp/confirm"):
            if body.get("totp_code") == totp(self.seed, time.time()):
                self.factor, self.confirm_step = True, int(time.time()) // STEP_SECONDS
                status, answer = 200, {"enabled": True, "sessions_ended": 1}
            else:
                status, answer = 422, {"error": "second_factor_invalid"}
        elif (method, path) == ("GET", "/organizations"):
            name = self.account["password"] if self.leak and self.account else "probe-s37"
            status, answer = (
                200,
                {
                    "organizations": [
                        {
                            "id": "31121d7b-1aa3-4206-8f13-d81157c1beaf",
                            "name": name,
                            "role": "admin",
                        }
                    ]
                },
            )
        elif method == "GET" and path == "/operations":
            status, answer = 200, {"operations": []}
        elif method == "GET" and path == "/projects":
            status, answer = 200, {"projects": [{"key": self.project, "state": "ready",
                                                 "profile": "small"}]}  # fmt: skip
        elif method == "GET" and path == f"/projects/{self.project}/connections":
            door = {"port": 5432, "user": "customer_app", "database": "slot3",
                    "sslmode": "verify-full", "connection_limit": 2}  # fmt: skip
            pooled = {**door, "host": f"pool.{self.project}.example.test"}
            direct = {
                **door,
                "user": "customer_admin",
                "host": f"direct.{self.project}.example.test",
            }
            # The server's own snippets and `where` lines (Session 47 Run 6),
            # built by its module from these doors -- never retyped here.
            served = self.snippets
            status, answer = 200, {
                "project": self.project, "pooled": pooled, "direct": direct,
                "password": served.PASSWORD_PLACEHOLDER,
                "snippets": served.snippets({"enabled": True, "pooled": pooled, "direct": direct}),
                **({"where": served.where()} if hasattr(served, "where") else {})}  # fmt: skip
        elif method == "POST" and path == f"/projects/{self.project}/credentials":
            assert body["role"] == "customer_app" and body["verifier"].startswith(
                "SCRAM-SHA-256$4096:"
            )
            status, answer = 202, {"operation": {"id": "op-rehearsal", "status": "pending"}}
        elif method == "GET" and path == "/operations/op-rehearsal":
            status, answer = 200, {"id": "op-rehearsal", "status": "succeeded"}
        elif (method, path) == ("DELETE", "/sessions/current"):
            route.fulfill(
                status=204, headers={"set-cookie": "__Host-apg_access=; Max-Age=0; Path=/; Secure"}
            )
            return
        route.fulfill(status=status, body=json.dumps(answer),
                      headers={"content-type": "application/json", **headers})  # fmt: skip


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------


def paint(browser: Any, base: str) -> dict[str, float | None]:
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{base}/console/", wait_until="load")
    page.wait_for_timeout(300)
    numbers = page.evaluate(
        "() => ({fcp: (performance.getEntriesByName('first-contentful-paint')[0] || {})"
        ".startTime ?? null,"
        " dcl: performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd})"
    )
    context.close()
    return numbers


def headers_of(page: Page, url: str) -> dict[str, str | None]:
    response = page.goto(url, wait_until="load")
    assert response is not None
    wanted = ("content-security-policy", "x-frame-options", "referrer-policy",
              "x-content-type-options", "cache-control")  # fmt: skip
    return {name: response.headers.get(name) for name in wanted}


def walk(arguments: argparse.Namespace) -> int:
    link = Path(arguments.link_file).read_text(encoding="utf-8").strip()
    token = urlsplit(link).fragment
    walker = Walk(arguments.base or f"{urlsplit(link).scheme}://{urlsplit(link).netloc}")
    walker.held += [token, link]
    walker.record["project"] = arguments.project
    walker.record["mode"] = "rehearsal" if arguments.rehearse else "live"
    # The commit the control project was deployed at, as the trip's script read
    # it from the deployed document: the proofs refuse a record of another release.
    walker.record["source_commit"] = arguments.source_commit
    walker.record["password_file"] = Path(arguments.password_out).name
    fixtures = Fixtures(arguments.project, arguments.leak) if arguments.rehearse else None
    username = f"walk-s43-{secrets.token_hex(3)}"
    password = base64.urlsafe_b64encode(secrets.token_bytes(24)).decode("ascii").rstrip("=")
    walker.held.append(password)
    walker.record["account"] = username
    exit_code = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        walker.record["chromium"] = browser.version
        walker.record["paint"] = [walker.step(f"paint {i + 1}", lambda: paint(browser, walker.base))
                                  for i in range(3)]  # fmt: skip
        context = browser.new_context()
        if fixtures is not None:
            context.route(f"{walker.base}/api/v1/**", fixtures.handle)
        page = context.new_page()
        try:
            # Read in a page of their own: a link to `/accept` opened in a page
            # already AT `/accept` is a same-document (fragment) navigation, and
            # the page's script would not run again.
            probe = context.new_page()
            walker.record["headers"] = {
                "/console/": headers_of(probe, f"{walker.base}/console/"),
                "/accept": headers_of(probe, f"{walker.base}/accept"),
            }
            probe.close()
            started = time.monotonic()

            def open_link() -> None:
                page.goto(
                    link.replace(f"{urlsplit(link).scheme}://{urlsplit(link).netloc}", walker.base)
                )
                page.get_by_role("heading", name="Create your account").wait_for()
                walker.record["address_bar_clean"] = "#" not in page.url and token not in page.url

            walker.step("open the invitation link", open_link)

            def create() -> None:
                page.get_by_label("Username").fill(username)
                page.get_by_label("Display name").fill(username)
                page.get_by_label("Password", exact=True).fill(password)
                page.get_by_label("Password again").fill(password)
                page.get_by_role("button", name="Create your account").click()
                page.locator("img.qr").wait_for()
                if arguments.qr_out:
                    # W0: the QR alone, for the operator's phone (the seed is in
                    # it: 0600, in the 0700 directory, shredded after the scan).
                    write_private(Path(arguments.qr_out), page.locator("img.qr").screenshot())

            walker.step("create the account", create)
            secret = page.locator("code.secret").first.inner_text().strip()
            seed = seed_of(secret)
            walker.held += [secret, seed.hex()]

            def enrol() -> int:
                code, step = fresh_code(seed)
                page.get_by_label("Code from your app").fill(code)
                page.get_by_role("button", name="Confirm").click()
                page.get_by_label("The next code from your app").wait_for()
                return step

            confirm_step = walker.step("enrol the second factor", enrol)

            def sign_in() -> None:
                code, _ = fresh_code(seed, after_step=confirm_step)
                page.get_by_label("The next code from your app").fill(code)
                page.get_by_role("button", name="Sign in").click()
                page.get_by_role("heading", level=1, name="Projects", exact=True).wait_for()

            walker.step("sign in with the next code", sign_in)
            walker.record["overview"] = [h.inner_text() for h in page.locator("#main h2").all()]
            cookies = context.cookies()
            walker.held += [cookie["value"] for cookie in cookies]
            walker.record["cookies"] = sorted(
                ({"name": c["name"], "httpOnly": c["httpOnly"], "secure": c["secure"],
                  "sameSite": c["sameSite"]} for c in cookies),
                key=lambda c: c["name"])  # fmt: skip

            def csrf() -> None:
                api = f"{walker.base}/api/v1"
                readings = {
                    "no_header": context.request.get(f"{api}/me").status,
                    "foreign_origin_logout": context.request.delete(
                        f"{api}/sessions/current",
                        headers={"X-Apg-Console": "1", "Origin": "https://evil.example"}).status,
                    "after_forged_logout": context.request.get(
                        f"{api}/me", headers={"X-Apg-Console": "1"}).status,
                }  # fmt: skip
                walker.record["csrf"] = readings

            walker.step("the live CSRF readings", csrf)
            if arguments.dry:
                walker.record["dry"] = True
            else:

                def rotate() -> tuple[str, str]:
                    # Session 47 Run 6 (D2956): Connect is three steps; the pooled
                    # door is chosen by default, its step 2 makes customer_app's password.
                    page.goto(f"{walker.base}/console/#/projects/{arguments.project}/connect")
                    make = page.get_by_role(
                        "button", name="Make a new password for the pooled door"
                    )
                    make.wait_for()
                    walker.record["clients"] = [
                        tab.inner_text().strip() for tab in page.locator("#main [role=tab]").all()
                    ]
                    make.click()
                    page.get_by_role(
                        "heading", name="Your new password for the pooled door"
                    ).wait_for(timeout=300_000)
                    shown = page.locator("#main .once code.secret").all()
                    return shown[0].inner_text().strip(), shown[1].inner_text().strip()

                rotated, string = walker.step("rotate customer_app from Connect", rotate)
                walker.held += [rotated, string]
                walker.record["link_to_string_seconds"] = round(time.monotonic() - started, 1)
                walker.record["string_holds_the_password"] = rotated in string
                parts = urlsplit(string)
                walker.record["string_parameters"] = {
                    key: value[0] for key, value in parse_qs(parts.query).items()}  # fmt: skip
                walker.record["pooled_host"] = parts.hostname
                walker.record["string_port"] = parts.port
                walker.record["string_user"] = parts.username
                walker.record["string_database"] = parts.path.lstrip("/")
                # The snippets that hold it: inside the shown-once box only (D2956).
                held = page.locator("#main .held code.secret").all()
                walker.record["snippets_holding_the_password"] = sum(
                    1 for code in held if rotated in (code.text_content() or "")
                )
                walker.record["password_outside_the_panel"] = page.evaluate(
                    "(p) => [...document.querySelectorAll('#main code')].filter((c) =>"
                    " !c.closest('.once, .held') && c.textContent.includes(p)).length",
                    rotated,
                )

                def saved_gone() -> None:
                    page.get_by_role("button", name="I have saved the password").click()
                    page.locator("#main .once-done").wait_for()
                    walker.record["password_gone_after_saved"] = rotated not in page.content()

                walker.step("saved: the password is gone", saved_gone)

                def reload_gone() -> None:
                    page.reload(wait_until="load")
                    page.get_by_role(
                        "button", name="Make a new password for the pooled door"
                    ).wait_for()
                    walker.record["password_gone_after_reload"] = rotated not in page.content()

                walker.step("reload: the password is gone", reload_gone)
                write_private(Path(arguments.password_out), rotated + "\n")

            def sign_out() -> None:
                page.goto(f"{walker.base}/console/")

                def is_sign_out(response: Any) -> bool:
                    return (response.request.method == "DELETE"
                            and response.url.endswith("/sessions/current"))  # fmt: skip

                page.get_by_role("heading", level=1, name="Projects", exact=True).wait_for()
                # Session 47 (ADR 0295): Sign out is in the account menu.
                page.locator("details.account > summary").click()
                with page.expect_response(is_sign_out) as ended:
                    page.get_by_role("button", name="Sign out").click()
                page.get_by_role("heading", name="Sign in").wait_for()
                walker.record["csrf"]["sign_out"] = ended.value.status
                walker.record["cookies_after_sign_out"] = len(
                    [c for c in context.cookies() if c["name"].startswith("__Host-apg_")]
                )

            walker.step("sign out", sign_out)
        except Exception as error:
            # Playwright's message names a selector and a timeout, never a value
            # this walk typed; the record keeps the type alone.
            failed = walker.record["steps"][-1]["name"] if walker.record["steps"] else "-"
            print(f"console_walk: step {failed!r} failed: {str(error).splitlines()[0][:300]}",
                  file=sys.stderr)  # fmt: skip
            exit_code = 4
        finally:
            browser.close()
    walker.record["exit"] = exit_code
    walker.self_check()
    write_private(
        Path(arguments.record), json.dumps(walker.record, indent=1, sort_keys=True) + "\n"
    )
    print(f"console_walk: {walker.record['mode']} walk exit {exit_code}; record {arguments.record}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="console_walk", allow_abbrev=False)
    parser.add_argument("--link-file", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--password-out", required=True)
    parser.add_argument("--project", default="slot3-prod")
    parser.add_argument(
        "--source-commit",
        required=True,
        help="the control project's deployed commit (its outputs' source_commit)",
    )
    parser.add_argument("--base", help="the console's origin (default: the link's)")
    parser.add_argument("--dry", action="store_true", help="stop before the rotation")
    parser.add_argument("--qr-out", help="W0: the factor's QR, as a PNG (0600)")
    parser.add_argument("--rehearse", action="store_true")
    parser.add_argument("--leak", action="store_true", help="rehearsal: a fixture leaks a password")
    arguments = parser.parse_args(argv)
    if arguments.leak and not arguments.rehearse:
        parser.error("--leak is a rehearsal fixture")
    return walk(arguments)


if __name__ == "__main__":
    raise SystemExit(main())

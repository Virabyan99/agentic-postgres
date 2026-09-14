#!/usr/bin/env python3
"""Studio: a loopback client of a deployment's own surfaces (ADR 0205).

Reached as `apg studio`. `bin/studio.sh` decides every argument error before
this runs; what is left here is the process itself -- the one that holds the
human's token, makes every upstream request from an enumerated table, and
serves three first-party files to a browser on `127.0.0.1`.

**The browser never holds the token.** It holds a launch cookie, and the four
checks in `studio.request_checks` are what make that cookie worth anything: a
foreign `Host` is 421, a missing cookie 401, a foreign `Origin` 403, an
`OPTIONS` 405, and a `/__apg/` call without `X-Apg-Studio` 403. Every decision
above is `src/agentic_postgres/studio.py`'s, so that a battery can reach it
without a socket; this file is the I/O.

**Four inputs, and the deployed document is the address book and nothing else**
(ADR 0158). The IR comes from the same four committed inputs `apg generate`
reads; the document supplies two URLs and the address the REST document spells
itself with (ADR 0050, D1260), and no route, digest or diagnosis is taken from
it.

Exit codes (runbook §2 convention):
  0  success
  2  invalid operator input
  3  a missing local prerequisite
  4  the project has not been rendered, naming the command that renders it
  5  a deployed document that publishes no usable route
  6  the deployment refused this credential
  9  the deployment could not be reached
"""

from __future__ import annotations

import argparse
import getpass
import http.server
import json
import secrets
import signal
import socketserver
import ssl
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from hashlib import sha256
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    capability_manifest,
    client_ir,
    config,
    deployed_output,
    naming,
    scope_registry,
    studio,
    template_version,
)

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_NOT_RENDERED = 4
EXIT_NO_ROUTE = 5
EXIT_REFUSED = 6
EXIT_UNREACHABLE = 9

APP_SNAPSHOT = REPO_ROOT / "contracts" / "app-openapi.canonical.json"
CANONICAL_MCP = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
RELEASE_SNAPSHOT = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"

#: Every upstream call, including the ones a page provoked. Long enough for a
#: cold PostgREST and short enough that a hung deployment does not look like a
#: hung browser.
UPSTREAM_TIMEOUT_SECONDS = 10


def fail(code: int, message: str) -> None:
    print(f"studio: {message}", file=sys.stderr)
    raise SystemExit(code)


def announce(message: str) -> None:
    """One line on stdout. Never a token, a key or a caller value (D105, D1256)."""
    print(f"studio: {message}", flush=True)


# ---------------------------------------------------------------------------
# the four inputs, as `apg generate` reads them
# ---------------------------------------------------------------------------


def project_key_of(project_path: Path) -> str:
    try:
        manifest = config.load_project_manifest(project_path)
    except config.ManifestError as error:
        fail(EXIT_INPUT, f"{project_path} did not load: {error}")
    project = manifest["project"]
    return naming.project_key(project["slug"], project["environment"])


def build_ir(project_path: Path, capabilities_path: Path) -> client_ir.IR:
    """The IR, from the same four committed inputs `bin/generate.py` reads.

    **A second copy of that sequence, and the pair is compared** (D486):
    `test_studio_command.py::test_the_ir_studio_builds_is_the_one_generate_wrote`
    asserts Studio's four digests equal the committed `generated.json`'s for the
    example project, so the two cannot drift without a proof going red.

    The alternative -- extracting the sequence into the package and having both
    commands call it -- is the better shape and is not this session's: it would
    rewrite a released command's error paths (`generate.py`'s `fail()` exits
    with codes this file does not share), and a refactor of `apg generate` for
    the convenience of `apg studio` is a change to the wrong command.
    """
    key = project_key_of(project_path)

    # The RENDERED document, for one reason: to refuse a project this checkout
    # has not rendered, naming the command that renders it (D975). Not the
    # deployed one -- that is the address book, and it is read elsewhere.
    try:
        deployed_output.read_rendered_document(key, runtime=False)
    except deployed_output.RenderedDocumentAbsent:
        fail(
            EXIT_NOT_RENDERED,
            f"{key} has not been rendered in this checkout. Render it first:\n"
            f"  ./deploy.sh --project {project_path} "
            f"--capabilities {capabilities_path} --render-only",
        )
    except deployed_output.RenderedDocumentUnreadable as error:
        fail(EXIT_PREREQUISITE, str(error))

    try:
        manifest = config.load_project_manifest(project_path)
        inputs = capability_manifest.project_inputs(manifest)
    except config.ManifestError as error:
        fail(EXIT_INPUT, f"cannot read the project manifest: {error}")
    except FileNotFoundError as error:
        fail(EXIT_PREREQUISITE, f"missing input: {error}")

    try:
        canonical = capability_manifest.load_contract_document(CANONICAL_MCP)
    except config.CapabilityContractError as error:
        # **EXIT_INPUT and not 5**: in this command 5 is EXIT_NO_ROUTE, which is
        # an answer about a deployment. An unreadable file in the checkout is
        # not that answer, and reusing the code would make two conditions
        # indistinguishable to a caller reading the number (D1359, ADR 0195).
        fail(EXIT_INPUT, str(error))
    sources: dict[str, str] = {}
    vocabulary_surface = None
    root = None

    if inputs is not None:
        try:
            capabilities = config.load_capabilities_manifest(capabilities_path)
            canonical = capability_manifest.compile_joint_contract(capabilities, inputs)
        except config.ManifestError as error:
            fail(EXIT_INPUT, f"cannot compile the joint contract: {error}")
        vocabulary_surface = inputs.surface
        root = inputs.root
        sources = {
            "project_capabilities_sha256": sha256(
                capability_manifest.project_capabilities_path(root).read_bytes()
            ).hexdigest(),
            "project_contract_sha256": sha256(
                capability_manifest.project_contract_path(root).read_bytes()
            ).hexdigest(),
        }
        surface = inputs.surface
        snapshot_path = api_surface.project_snapshot_path(root)
    else:
        surface = api_surface.load_surface()
        snapshot_path = RELEASE_SNAPSHOT

    if not snapshot_path.is_file():
        fail(
            EXIT_PREREQUISITE,
            f"{snapshot_path} is not there, so there is no approved surface to show. "
            "Capture it with `bin/api-contract.sh --update` after the deploy that serves it",
        )

    try:
        lock = capability_compiler.compile_lock(
            canonical=canonical,
            project_key=key,
            # Not an address: the lock's `upstream` is the RUNTIME's one URL and
            # Studio is not the runtime. Studio's addresses come from the
            # deployed document and from nowhere else.
            upstream="https://studio.invalid/api/rest",
            sources={
                "capabilities_sha256": sha256(capabilities_path.read_bytes()).hexdigest(),
                "api_surface_sha256": api_surface.contract_digest(),
                "canonical_openapi_sha256": sha256(RELEASE_SNAPSHOT.read_bytes()).hexdigest(),
                "project_manifest_sha256": sha256(project_path.read_bytes()).hexdigest(),
                **sources,
            },
            profile=None,
            vocabulary=scope_registry.vocabulary_block(vocabulary_surface),
        )
    except (KeyError, config.ManifestError) as error:
        fail(EXIT_INPUT, f"cannot compile the lock: {error}")

    try:
        return client_ir.build(
            surface=surface,
            snapshot=json.loads(snapshot_path.read_text(encoding="utf-8")),
            app_snapshot=json.loads(APP_SNAPSHOT.read_text(encoding="utf-8")),
            lock=lock,
            project_root=str(root.relative_to(REPO_ROOT)) if root else None,
            pt_sources=client_ir.project_pt_sources(root),
            app_snapshot_bytes=APP_SNAPSHOT.read_bytes(),
            template_version=template_version(),
        )
    except client_ir.ClientIrError as error:
        fail(EXIT_INPUT, str(error))
        raise AssertionError("unreachable") from error


# ---------------------------------------------------------------------------
# the credential (D105)
# ---------------------------------------------------------------------------


def read_password(password_file: Path | None, username: str) -> str:
    """The human's password, from a `0600` file or a TTY, and from nowhere else.

    **No flag carries it and no environment variable is read for it.** A value
    in an argument is in `ps` and in a shell history; a value in the environment
    is in `/proc/<pid>/environ` and in `docker inspect` for anything this
    process later starts. `bin/dev-token.sh`'s rule, unchanged: a credential
    reaches a process through its environment or a `0600` file, and Studio takes
    the narrower half of that because it has a TTY to ask at.
    """
    if password_file is not None:
        try:
            info = password_file.stat()
        except OSError as error:
            fail(EXIT_INPUT, f"cannot read {password_file}: {error}")
        if not stat.S_ISREG(info.st_mode):
            fail(EXIT_INPUT, f"{password_file} is not a regular file.")
        if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            fail(
                EXIT_INPUT,
                f"{password_file} is mode {info.st_mode & 0o777:04o}; it must be 0600 or "
                "stricter. A password file others can read is a password others have.",
            )
        return password_file.read_text(encoding="utf-8").strip("\n")

    if not sys.stdin.isatty():
        fail(
            EXIT_INPUT,
            "no TTY to prompt at and no --password-file. Studio reads a password from a "
            "prompt or from a 0600 file, and from nothing else -- not an argument, not the "
            "environment.",
        )
    return getpass.getpass(f"password for {username}: ")


# ---------------------------------------------------------------------------
# upstream
# ---------------------------------------------------------------------------


class Upstream:
    """Every request this process makes, and the bearer it makes them with.

    The token lives here, in memory, and is never written, printed or handed to
    the page. `classify` is where ADR 0139 and D433 land: a status becomes one
    of four words and the upstream body is never relayed -- a 403 from
    PostgREST carrying a column name would otherwise reach a browser through a
    tool that promised not to do that.
    """

    def __init__(self, rest_url: str, app_url: str) -> None:
        self.rest_url = rest_url
        self.app_url = app_url
        self._token = ""
        self._refresh_token = ""
        self._expires_at = 0
        self._lock = threading.Lock()
        self.calls: list[str] = []

    # -- the credential ------------------------------------------------------
    def login(self, username: str, password: str) -> None:
        status, body = self.request(
            "POST", f"{self.app_url}/auth/login", {"username": username, "password": password}
        )
        if status == 401:
            # ADR 0097: the endpoint fails identically four ways and so does
            # this line. An unknown subject, a wrong password, a disabled
            # subject and a locked one are one sentence here.
            fail(EXIT_REFUSED, "the deployment refused this credential.")
        if status == 0:
            # A transport failure, not an answer. `body` carries urllib's own
            # reason and nothing a caller sent, so it is safe to print and it is
            # the only thing that tells an operator whether to check the route,
            # the network or the deployment.
            fail(
                EXIT_UNREACHABLE,
                f"could not reach {self.app_url}: {body.decode('utf-8', 'replace')[:200]}",
            )
        if status != 200:
            fail(EXIT_UNREACHABLE, f"the deployment answered {status} to a login.")
        issued = json.loads(body)
        with self._lock:
            self._token = issued["access_token"]
            self._refresh_token = issued.get("refresh_token", "")
            self._expires_at = int(issued.get("expires_at", 0))

    def bearer(self) -> str:
        """The access token, refreshed when it is close to expiring (D1252).

        Lock-guarded because the server is threaded: two page requests arriving
        together must not both refresh, which would spend two links of a
        rotating family and invalidate one of them.
        """
        with self._lock:
            remaining = self._expires_at - int(time.time())
            if remaining >= studio.STUDIO_REFRESH_BEFORE_SECONDS or not self._refresh_token:
                return self._token
            token = self._refresh_token
        status, body = self.request(
            "POST", f"{self.app_url}/auth/refresh", {"refresh_token": token}, authenticated=False
        )
        if status == 200:
            issued = json.loads(body)
            with self._lock:
                self._token = issued["access_token"]
                self._refresh_token = issued.get("refresh_token", "")
                self._expires_at = int(issued.get("expires_at", 0))
        with self._lock:
            return self._token

    # -- the wire ------------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
        accept: str = "application/json",
    ) -> tuple[int, bytes]:
        self.calls.append(f"{method} {urllib.parse.urlsplit(url).path}")
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=payload, method=method)  # noqa: S310
        request.add_header("Accept", accept)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        if authenticated:
            request.add_header("Authorization", f"Bearer {self.bearer()}")
        context = None
        if urllib.parse.urlsplit(url).scheme == "https":
            context = ssl.create_default_context()
        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=UPSTREAM_TIMEOUT_SECONDS, context=context
            ) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as error:
            return 0, str(getattr(error, "reason", error)).encode("utf-8")

    @staticmethod
    def classify(status: int) -> str:
        """A status becomes one of four words, and the body is never relayed.

        D433's rule: this process asked somebody else and was told no, and the
        only honest thing to pass on is which KIND of no it was. A relayed body
        would put an upstream's prose -- a column name, a constraint, a role --
        into a page this tool is responsible for.
        """
        if status == 0:
            return "upstream_failed"
        if 200 <= status < 300:
            return "ok"
        if status in (401, 403):
            return "refused"
        if status >= 500:
            return "upstream_failed"
        return "invalid"


# ---------------------------------------------------------------------------
# the server
# ---------------------------------------------------------------------------


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(state: dict[str, Any]) -> type[http.server.BaseHTTPRequestHandler]:
    """The handler, closed over one launch's state.

    A factory rather than class attributes, so two Studios in one test process
    cannot share a launch key -- which is the shape of a defect that would only
    ever appear in a test and would make the test wrong rather than the product.
    """

    assets = {
        "/": (studio.ASSET_ROOT / "index.html", "text/html; charset=utf-8"),
        "/studio.js": (studio.ASSET_ROOT / "studio.js", "text/javascript; charset=utf-8"),
        "/studio.css": (studio.ASSET_ROOT / "studio.css", "text/css; charset=utf-8"),
    }
    served = {path: (source.read_bytes(), kind) for path, (source, kind) in assets.items()}

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "apg-studio"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            """A method, a path without its query, a status. Nothing else (D1256)."""
            sys.stderr.write(f"apg-studio {studio.redact_for_log(self.command, self.path)}\n")

        # -- answering -------------------------------------------------------
        def send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for name, value in studio.SECURITY_HEADERS.items():
                self.send_header(name, value)
            if status >= 400:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status: int, payload: dict[str, Any]) -> None:
            self.send(status, json.dumps(payload).encode("utf-8"), "application/json")

        # -- the five checks, first, on every request ------------------------
        def refused(self) -> bool:
            status = studio.request_checks(
                method=self.command,
                path=self.path.split("?", 1)[0],
                host=self.headers.get("Host"),
                bound=state["bound"],
                cookie=self.headers.get("Cookie"),
                expected_cookie=state["key"],
                origin=self.headers.get("Origin"),
                own_origin=f"http://{state['bound']}",
                custom_header=self.headers.get(studio.CUSTOM_HEADER),
            )
            if status is None:
                return False
            # `self.rfile` is untouched: a refused POST's body is never read,
            # measured in rig 24a against a declared megabyte.
            self.send_json(status, {"status": "refused"})
            return True

        def body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 64 * 1024:
                return {}
            try:
                document = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}
            return document if isinstance(document, dict) else {}

        def query(self) -> dict[str, str]:
            raw = self.path.split("?", 1)
            if len(raw) == 1:
                return {}
            return {
                key: values[0]
                for key, values in urllib.parse.parse_qs(raw[1], keep_blank_values=False).items()
            }

        # -- routing ---------------------------------------------------------
        def do_GET(self) -> None:
            if self.refused():
                return
            path = self.path.split("?", 1)[0]

            if path.startswith("/open/"):
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header(
                    "Set-Cookie",
                    f"{studio.LAUNCH_COOKIE}={state['key']}; HttpOnly; SameSite=Strict; Path=/",
                )
                self.send_header("Content-Length", "0")
                for name, value in studio.SECURITY_HEADERS.items():
                    self.send_header(name, value)
                self.end_headers()
                return

            if path in served:
                body, kind = served[path]
                self.send(200, body, kind)
                return

            if path == "/__apg/state":
                self.send_json(200, state["state"]())
                return
            if path == "/__apg/schema":
                if state["surface"].answer != "ok":
                    self.send_json(
                        409,
                        {
                            "status": "refused",
                            "reason": state["surface"].answer,
                            "detail": state["surface"].reason,
                        },
                    )
                    return
                self.send_json(200, studio.schema_view(state["ir"]))
                return
            if path == "/__apg/capabilities":
                # Ungated, and that is the decision (D1274). The surface answer
                # is about the REST document; this view is about the compiled
                # lock, which no request this process makes confirms. Refusing
                # it because a REST contract is stale would report one
                # contract's staleness as another's.
                self.send_json(200, studio.capabilities_view(state["ir"]))
                return
            if path == "/__apg/me":
                self.relay("GET", f"{state['upstream'].app_url}/auth/me")
                return
            if path == "/__apg/sessions":
                self.relay("GET", f"{state['upstream'].app_url}/auth/sessions")
                return
            if path == "/__apg/agents":
                self.relay("GET", f"{state['upstream'].app_url}/admin/agents")
                return
            if path == "/__apg/audit":
                self.audit()
                return
            self.send_json(404, {"status": "not_found"})

        def do_POST(self) -> None:
            if self.refused():
                return
            path = self.path.split("?", 1)[0]
            if path == "/__apg/query":
                self.query_view()
                return
            if path == "/__apg/revoke":
                self.revoke()
                return
            self.send_json(404, {"status": "not_found"})

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_OPTIONS(self) -> None:
            """405, and it must be OURS.

            `BaseHTTPRequestHandler` answers an unimplemented method with **501
            and none of this server's headers** -- measured, before this method
            existed: `Content-Type: text/html`, no Content-Security-Policy, no
            `Connection: close`. That is the framework refusing on its own
            terms, which is exactly the arrangement ADR 0140 is about: a refusal
            nobody here wrote is a refusal nobody here can reason about.

            A preflight has to be refused by US, with our headers, so that
            `X-Apg-Studio` stays a header a cross-origin page cannot set.
            """
            self.refused()

        def do_PUT(self) -> None:
            self.refused() or self.send_json(404, {"status": "not_found"})

        def do_DELETE(self) -> None:
            self.refused() or self.send_json(404, {"status": "not_found"})

        # -- the operations --------------------------------------------------
        def relay(self, method: str, url: str) -> None:
            status, body = state["upstream"].request(method, url)
            outcome = state["upstream"].classify(status)
            if outcome != "ok":
                self.send_json(200, {"status": outcome})
                return
            try:
                payload = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json(200, {"status": "upstream_failed"})
                return
            self.send_json(200, {"status": "ok", "body": payload})

        def audit(self) -> None:
            supplied = self.query()
            unknown = set(supplied) - {"agent_id", "owner_id"}
            if unknown:
                # The forwarder takes the endpoint's own two filters and no
                # more. An `outcome` or a `since` here would be a filter applied
                # UPSTREAM of the page's count, which is what D1248 refuses: a
                # viewer could then ask for `outcome=served` and never learn
                # there were refusals.
                self.send_json(
                    400,
                    {
                        "status": "invalid",
                        "reason": f"this view takes agent_id and owner_id; not {sorted(unknown)}",
                    },
                )
                return
            parameters = {**supplied, "limit": str(studio.AUDIT_PAGE_LIMIT)}
            url = f"{state['upstream'].app_url}/admin/audit?{urllib.parse.urlencode(parameters)}"
            status, body = state["upstream"].request("GET", url)
            outcome = state["upstream"].classify(status)
            if outcome != "ok":
                self.send_json(200, {"status": outcome})
                return
            try:
                payload = json.loads(body)
                rows = payload["audit"]
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError):
                self.send_json(200, {"status": "upstream_failed"})
                return
            self.send_json(
                200,
                {
                    "status": "ok",
                    "rows": rows,
                    "total": len(rows),
                    "header": studio.audit_view_header(len(rows), len(rows)),
                    "page_limit": studio.AUDIT_PAGE_LIMIT,
                },
            )

        def query_view(self) -> None:
            if state["surface"].answer != "ok":
                self.send_json(409, {"status": "refused", "reason": state["surface"].answer})
                return
            asked = self.body()
            try:
                path = studio.rest_query(
                    state["ir"],
                    relation=str(asked.get("relation", "")),
                    select=list(asked.get("select") or []),
                    filters=[
                        (str(item[0]), str(item[1]), item[2] if len(item) > 2 else None)
                        for item in (asked.get("filters") or [])
                        if isinstance(item, list) and len(item) >= 2
                    ],
                    order=(
                        (str(asked["order"][0]), str(asked["order"][1]))
                        if isinstance(asked.get("order"), list) and len(asked["order"]) == 2
                        else None
                    ),
                    limit=asked.get("limit", 100),
                )
            except studio.StudioError as error:
                self.send_json(422, {"status": "invalid", "reason": str(error)})
                return

            status, body = state["upstream"].request("GET", f"{state['upstream'].rest_url}{path}")
            outcome = state["upstream"].classify(status)
            if outcome != "ok":
                answer: dict[str, Any] = {"status": outcome}
                if outcome == "invalid":
                    # ADR 0139: PostgREST's own machine code and nothing else.
                    # The message is the upstream's prose and does not travel.
                    try:
                        answer["code"] = json.loads(body).get("code")
                    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                        answer["code"] = None
                self.send_json(200, answer)
                return
            try:
                rows = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json(200, {"status": "upstream_failed"})
                return
            self.send_json(200, {"status": "ok", "rows": rows})

        def revoke(self) -> None:
            asked = self.body()
            try:
                path, payload = studio.revoke_request(
                    str(asked.get("agent_id", "")), str(asked.get("confirm", ""))
                )
            except studio.StudioError as error:
                # 422 BEFORE any upstream request exists to have changed
                # anything, which is what makes "Nothing was changed." true.
                self.send_json(422, {"status": "invalid", "reason": str(error)})
                return
            status, _ = state["upstream"].request(
                "PATCH", f"{state['upstream'].app_url}{path}", payload
            )
            self.send_json(200, {"status": state["upstream"].classify(status)})

    return Handler


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="studio", add_help=False)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--outputs", required=True, type=Path)
    parser.add_argument(
        "--capabilities", type=Path, default=REPO_ROOT / "capabilities.example.yaml"
    )
    parser.add_argument("--username", default=None)
    parser.add_argument("--password-file", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse(argv)

    # (2) the address book. `document` MEANS the deployed document in a bin/
    # command (D1184).
    try:
        document = json.loads(arguments.outputs.read_text(encoding="utf-8"))
    except OSError as error:
        fail(EXIT_INPUT, f"cannot read {arguments.outputs}: {error}")
    except json.JSONDecodeError as error:
        fail(EXIT_INPUT, f"{arguments.outputs} is not JSON: {error}")
    try:
        book = studio.address_book(document)
    except studio.StudioError as error:
        fail(error.exit_code, str(error))

    # (3) the IR, from the four committed inputs.
    ir = build_ir(arguments.project, arguments.capabilities)

    # (4) the login.
    username = arguments.username or ""
    if not username:
        if not sys.stdin.isatty():
            fail(EXIT_INPUT, "--username is required when there is no TTY to ask at.")
        username = input("username: ").strip()
    password = read_password(arguments.password_file, username)

    upstream = Upstream(book.rest_url, book.app_url)
    since = time.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00", time.gmtime())
    upstream.login(username, password)
    del password

    # (5) which session was this launch's (D1252, ADR 0195).
    status, body = upstream.request("GET", f"{book.app_url}/auth/sessions")
    own = None
    if status == 200:
        try:
            own = studio.own_session(json.loads(body), since)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            own = None

    # (6) the surface, as the human, exactly as a generated client's init().
    status, fetched = upstream.request(
        "GET", f"{book.rest_url}/", accept="application/openapi+json"
    )
    surface = studio.surface_answer(
        ir,
        fetched if status == 200 else None,
        None if status == 200 else f"the REST route answered {status or 'nothing'}",
        expected_host=book.expected_host,
        expected_base_path=book.expected_base_path,
    )
    if surface.answer == "ok":
        announce(f"surface ok {surface.served_sha256[:16]}…")
    elif surface.answer == "stale_contract":
        announce(
            f"surface stale_contract served {surface.served_sha256[:16]}… expected "
            f"{surface.expected_sha256[:16]}…"
        )
        # **Two causes, one answer, and both named** (D1275). The capture may be
        # stale -- or this subject's role may simply not be the capture's.
        # PostgREST serves a document scoped to the caller's grants, measured in
        # rig 24d: `project_admin` is served the same one-path document as
        # `anon`, because the administrative role holds nothing in `api`. An
        # operator told only the first would regenerate a capture that was right.
        announce(
            f"  either the capture moved -- run bin/apg.sh generate --project "
            f"{arguments.project} -- or {username} holds a role this surface is not "
            "granted to; an administrator is served the anonymous document"
        )
    else:
        announce(f"surface {surface.answer}: {surface.reason}")

    # (7) the socket. One address, no flag (D1245).
    key = secrets.token_urlsafe(32)
    state: dict[str, Any] = {
        "key": key,
        "ir": ir,
        "surface": surface,
        "upstream": upstream,
        "own_session": own,
    }
    server = Server((studio.BIND_ADDRESS, 0), make_handler(state))
    port = server.server_address[1]
    state["bound"] = f"{studio.BIND_ADDRESS}:{port}"
    state["state"] = lambda: {
        "surface": {
            "answer": surface.answer,
            "served_sha256": surface.served_sha256,
            "expected_sha256": surface.expected_sha256,
            "reason": surface.reason,
        },
        "subject": username,
        "project": project_key_of(arguments.project),
        "own_session_known": own is not None,
        "digests": {
            "rest_openapi_sha256": ir.digests.rest_openapi_sha256,
            "tools_sha256": ir.digests.tools_sha256,
        },
        "max_rows": studio.STUDIO_MAX_ROWS,
        "audit_page_limit": studio.AUDIT_PAGE_LIMIT,
    }

    announce(f"open http://{state['bound']}/open/{key}")
    announce(f"as {username} on {project_key_of(arguments.project)}")

    def shut_down(signum: int, frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shut_down)
    signal.signal(signal.SIGINT, shut_down)
    try:
        server.serve_forever()
    finally:
        server.server_close()

    # (9) end the session this launch began, or say that it could not be
    # determined (ADR 0195). A session a tool opened and could not close is a
    # credential with nobody's name on it.
    if own is not None:
        upstream.request("DELETE", f"{book.app_url}/auth/sessions/{own}")
        announce("ended the session it began")
    else:
        announce(
            "could not determine which session was its own and ended none; "
            "GET /auth/sessions lists them"
        )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

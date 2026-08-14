"""What the locked Traefik does with the configuration this repository ships.

Every claim here was a documentation claim first, and ADR 0019 exists because
one of those took the edge plane down. So the rig loads **the shipped
`baseline.yaml`** and **the middleware `edge_credentials` generates**, not a
hand-written copy of either: a test written against a copy proves the copy.

The four findings the design rests on:

- `PathPrefix` is **not** segment-aware. A router ruled ``PathPrefix(`/api/rest`)``
  answers `/api/restaurant`. The shipped rule is a pair.
- `customResponseHeaders` with an empty value **removes** the header, and the
  chain runs on responses the edge generates itself -- a 413 from the buffering
  middleware carries `Cache-Control: no-store`. It does not run when no router
  matched at all.
- `buffering.maxRequestBodyBytes` is inclusive: the limit passes, one byte more
  is 413.
- Traefik accepts a bcrypt htpasswd hash and refuses every other format with a
  401 that looks exactly like a wrong password.
"""

from __future__ import annotations

import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml
from tests.contract.test_image_contracts import LOCK, requires_docker

from agentic_postgres import REPO_ROOT, edge_credentials

pytestmark = [pytest.mark.contract, pytest.mark.p0]

PROJECT_KEY = "probe-dev"
DOCS_PASSWORD = "documentation-probe-password"  # noqa: S105 — a throwaway for one container

#: An upstream that reports what reached it, and sets the two headers the edge
#: is supposed to overwrite and remove.
UPSTREAM = """
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Echo(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _answer(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        payload = json.dumps({
            "path": self.path,
            "body_bytes": len(body),
            "headers": {k.lower(): v for k, v in self.headers.items()},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Server", "UPSTREAMSERVERCANARY/1.0")
        self.send_header("Cache-Control", "public, max-age=600")
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _answer
    do_POST = _answer

    def log_message(self, *args):
        return


HTTPServer(("0.0.0.0", 8080), Echo).serve_forever()
"""

#: The static configuration. Deliberately minimal -- no ACME, no socket proxy --
#: because what is under test is the dynamic policy, and a rig that needed the
#: real static file would need a certificate authority to answer.
STATIC = """
api:
  dashboard: false
  insecure: false
entryPoints:
  web:
    address: ":8080"
providers:
  file:
    directory: /etc/traefik/dynamic
    watch: true
log:
  level: INFO
  format: json
accessLog:
  format: json
  fields:
    defaultMode: keep
    headers:
      defaultMode: drop
      names:
        X-Request-ID: keep
        User-Agent: keep
    names:
      RequestPath: drop
"""

#: The rules under test, written the way the runtime override writes them.
MAX_BODY = 1024
ROUTERS = f"""
http:
  middlewares:
    probe-buffering:
      buffering:
        maxRequestBodyBytes: {MAX_BODY}
        memRequestBodyBytes: {MAX_BODY}
  routers:
    exact:
      rule: "Host(`probe.test`) && (Path(`/api/rest`) || PathPrefix(`/api/rest/`))"
      entryPoints: [web]
      middlewares: [apg-baseline, probe-buffering]
      service: upstream
    naive:
      rule: "Host(`probe.test`) && PathPrefix(`/naive/rest`)"
      entryPoints: [web]
      service: upstream
    docs:
      rule: "Host(`probe.test`) && (Path(`/docs/rest`) || PathPrefix(`/docs/rest/`))"
      entryPoints: [web]
      middlewares: [apg-baseline, {PROJECT_KEY}-docs]
      service: upstream
  services:
    upstream:
      loadBalancer:
        servers:
          - url: "http://upstream:8080"
"""


def bcrypt_hash(password: str) -> str:
    """Produced in the locked runtime image, because the host cannot.

    `crypt` was removed from the standard library in 3.13, so this is not a
    stylistic choice: on any host running a current Python there is no in-process
    way to make the one hash format Traefik accepts.
    """
    result = subprocess.run(
        ["docker", "run", "--rm", "-i", LOCK["PYTHON_RUNTIME_IMAGE"], "python", "-"],
        input=(f"import crypt\nprint(crypt.crypt({password!r}, crypt.METHOD_BLOWFISH), end='')\n"),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _headers(message) -> dict[str, str]:
    """Lowercased keys.

    `HTTPMessage` is case-insensitive and a plain dict built from one is not, so
    a header assertion written against one server's capitalisation passes or
    fails on a property of the sender rather than of the policy under test.
    Traefik sends `Www-Authenticate`; the RFC spells it `WWW-Authenticate`.
    """
    return {key.lower(): value for key, value in message.items()}


class Edge:
    def __init__(self, port: int, container: str, dynamic: Path | None = None) -> None:
        self.port = port
        self.container = container
        #: The directory the file provider watches, so a test can rewrite what
        #: it parses. `None` for a rig that has no business doing that.
        self.dynamic = dynamic

    def call(self, path: str, *, host: str = "probe.test", body: bytes | None = None,
             credential: tuple[str, str] | None = None):  # fmt: skip
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body,
            method="POST" if body is not None else "GET",
        )
        request.add_header("Host", host)
        if credential is not None:
            import base64

            raw = base64.b64encode(":".join(credential).encode()).decode()
            request.add_header("Authorization", f"Basic {raw}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return response.status, _headers(response.headers), response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, _headers(error.headers), error.read().decode()
        except OSError as error:
            # A port that is bound before Traefik is listening resets the
            # connection. Returned rather than raised so the readiness poll can
            # ask again; every assertion below compares against a real status,
            # so a rig that never came up fails on the comparison rather than
            # passing because nothing answered.
            return None, {}, f"<transport error: {error}>"

    def status(self, path: str, **kwargs) -> int | None:
        return self.call(path, **kwargs)[0]

    def logs(self) -> str:
        result = subprocess.run(
            ["docker", "logs", self.container],
            capture_output=True, text=True, check=False, timeout=60,
        )  # fmt: skip
        return result.stdout + result.stderr


@pytest.fixture(scope="module")
def edge(tmp_path_factory: pytest.TempPathFactory):
    suffix = secrets.token_hex(4)
    network = f"apg-edge-probe-net-{suffix}"
    traefik = f"apg-edge-probe-{suffix}"
    upstream = f"apg-edge-upstream-{suffix}"
    work = tmp_path_factory.mktemp("edge-probe")
    dynamic = work / "dynamic"
    dynamic.mkdir()

    # The shipped baseline, with its one placeholder resolved the way the
    # staging render resolves it.
    baseline = (REPO_ROOT / "infra/edge/dynamic/baseline.yaml").read_text(encoding="utf-8")
    baseline = "\n".join(
        "" if line.strip() == "__HSTS_BLOCK__" else line for line in baseline.splitlines()
    )
    (dynamic / "baseline.yaml").write_text(baseline, encoding="utf-8")
    (dynamic / "routers.yaml").write_text(STATIC and ROUTERS, encoding="utf-8")

    # The generated middleware, carrying the hash inline (ADR 0086). There is no
    # separate credential file to write any more.
    middleware_file = dynamic / edge_credentials.middleware_file_name(PROJECT_KEY)
    middleware_file.write_bytes(
        edge_credentials.render_middleware(
            middleware_name=f"{PROJECT_KEY}-docs",
            project_key=PROJECT_KEY,
            hashed=bcrypt_hash(DOCS_PASSWORD),
        )
    )
    # A stray `.htpasswd` in the same directory, hashed the way a host tool
    # would do it. Nothing generates one now, and the property it proves is
    # still worth holding: the provider must ignore the extension rather than
    # discard the directory's whole configuration over a file it cannot parse.
    (dynamic / "wrong-format.htpasswd").write_text(
        f"docs:{'$6$rounds=5000$abcdefgh$' + 'x' * 43}\n", encoding="utf-8"
    )
    (work / "traefik.yaml").write_text(STATIC, encoding="utf-8")

    subprocess.run(
        ["docker", "network", "create", network],
        capture_output=True, check=False, timeout=120,
    )  # fmt: skip
    script = work / "upstream.py"
    script.write_text(UPSTREAM, encoding="utf-8")

    started = subprocess.run(
        [
            "docker", "run", "-d", "--name", upstream, "--network", network,
            "--network-alias", "upstream", "-v", f"{script}:/upstream.py:ro",
            LOCK["PYTHON_RUNTIME_IMAGE"], "python", "/upstream.py",
        ],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert started.returncode == 0, started.stderr

    started = subprocess.run(
        [
            "docker", "run", "-d", "--name", traefik, "--network", network,
            "-p", "127.0.0.1:0:8080",
            "-v", f"{work / 'traefik.yaml'}:/etc/traefik/traefik.yaml:ro",
            "-v", f"{dynamic}:/etc/traefik/dynamic:ro",
            LOCK["TRAEFIK_IMAGE"],
        ],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert started.returncode == 0, started.stderr

    try:
        mapping = subprocess.run(
            ["docker", "port", traefik, "8080"],
            capture_output=True, text=True, check=False, timeout=60,
        )  # fmt: skip
        assert mapping.returncode == 0, mapping.stderr
        port = int(mapping.stdout.strip().splitlines()[0].rsplit(":", 1)[-1])
        rig = Edge(port, traefik, dynamic)

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if rig.status("/api/rest") == 200:
                break
            time.sleep(1)
        else:
            pytest.fail(f"the edge never served the probe route:\n{rig.logs()[-3000:]}")
        yield rig
    finally:
        for name in (traefik, upstream):
            subprocess.run(
                ["docker", "rm", "-f", name], capture_output=True, check=False, timeout=120
            )
        subprocess.run(
            ["docker", "network", "rm", network], capture_output=True, check=False, timeout=120
        )


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------


@requires_docker
@pytest.mark.parametrize("path", ["/api/rest", "/api/rest/", "/api/rest/notes"])
def test_the_rest_route_serves_its_own_segment_and_below(edge: Edge, path: str) -> None:
    assert edge.status(path) == 200


@requires_docker
@pytest.mark.parametrize("path", ["/api/restaurant", "/api/rest-extra", "/api/rest2", "/api"])
def test_the_rest_route_does_not_serve_a_sibling_that_shares_a_spelling(
    edge: Edge, path: str
) -> None:
    """The reason the rule is a pair rather than a `PathPrefix`."""
    assert edge.status(path) == 404


@requires_docker
def test_a_bare_path_prefix_would_have_served_them(edge: Edge) -> None:
    """The control, and the whole finding.

    Without this the test above is satisfied by any rule that happens to 404 --
    including one that is broken. The `naive` router is ruled
    ``PathPrefix(`/naive/rest`)``, which is how the boundary would have been
    written from the documentation, and it answers a path nobody routed to it.
    """
    assert edge.status("/naive/restaurant") == 200, (
        "PathPrefix is segment-aware after all; the shipped rule can be simplified "
        "and this finding needs re-recording"
    )
    assert edge.status("/naive/rest-extra") == 200


# ---------------------------------------------------------------------------
# The response policy
# ---------------------------------------------------------------------------


@requires_docker
def test_the_response_policy_overwrites_the_upstreams_headers(edge: Edge) -> None:
    """`Cache-Control` is replaced and `Server` is removed.

    The upstream sets both deliberately. An API response is per-caller by
    construction -- every row is selected by a row policy keyed on the
    requester -- so a shared cache holding one holds one caller's data under a
    URL another caller will ask for.
    """
    _, headers, _ = edge.call("/api/rest/notes")
    assert headers.get("cache-control") == "no-store"
    assert "server" not in headers, headers.get("server")
    assert "UPSTREAMSERVERCANARY" not in str(headers)


@requires_docker
def test_the_policy_reaches_a_response_the_edge_generates_itself(edge: Edge) -> None:
    """The half that would have been assumed.

    A 413 never reaches a service, so a response-header middleware attached
    beside the upstream would miss it. Attached to the router, it does not.
    """
    status, headers, _ = edge.call("/api/rest/notes", body=b"x" * (MAX_BODY + 1))
    assert status == 413
    assert headers.get("cache-control") == "no-store"


@requires_docker
def test_the_policy_does_not_reach_a_response_no_router_matched(edge: Edge) -> None:
    """Recorded rather than papered over.

    A chain is a property of a router, so a path no router matched gets
    Traefik's bare 404. An entry-point-level chain was measured not to change
    this. That response belongs to no project and discloses nothing, which is
    why the boundary is acceptable -- but it is a boundary, and "every response"
    is true of every response this deployment routes rather than of every packet
    the port answers.
    """
    _, headers, _ = edge.call("/nowhere")
    assert "cache-control" not in headers


# ---------------------------------------------------------------------------
# The body-size boundary (D143)
# ---------------------------------------------------------------------------


@requires_docker
def test_a_body_at_the_limit_reaches_the_upstream(edge: Edge) -> None:
    """The limit is inclusive, and the upstream is asked how much it got.

    Asserting only the status would pass against a middleware that truncated the
    body and forwarded what was left.
    """
    status, _, body = edge.call("/api/rest/notes", body=b"x" * MAX_BODY)
    assert status == 200, body
    import json

    assert json.loads(body)["body_bytes"] == MAX_BODY


@requires_docker
def test_one_byte_over_the_limit_is_refused_before_the_upstream(edge: Edge) -> None:
    status, _, body = edge.call("/api/rest/notes", body=b"x" * (MAX_BODY + 1))
    assert status == 413
    assert "body_bytes" not in body, "the upstream saw a request that should not have reached it"


# ---------------------------------------------------------------------------
# The documentation credential
# ---------------------------------------------------------------------------


@requires_docker
def test_the_documentation_route_refuses_without_a_credential(edge: Edge) -> None:
    status, headers, _ = edge.call("/docs/rest")
    assert status == 401
    assert headers.get("www-authenticate", "").startswith("Basic")
    assert PROJECT_KEY in headers["www-authenticate"], "the realm does not name the project"


@requires_docker
@pytest.mark.parametrize("credential", [("docs", "wrong"), ("nobody", DOCS_PASSWORD), ("docs", "")])
def test_a_wrong_credential_is_refused(edge: Edge, credential: tuple[str, str]) -> None:
    assert edge.status("/docs/rest", credential=credential) == 401


@requires_docker
def test_the_generated_credential_opens_the_route(edge: Edge) -> None:
    """The positive case, so the refusals mean something.

    The hash was produced by `crypt.METHOD_BLOWFISH` in the locked runtime image
    and validated by `edge_credentials.assert_bcrypt` before being written.
    """
    assert edge.status("/docs/rest", credential=("docs", DOCS_PASSWORD)) == 200


@requires_docker
def test_the_credential_does_not_reach_the_upstream(edge: Edge) -> None:
    """`removeHeader: true`, which is the whole of SEC-DOCS-001's first clause.

    The documentation service is the one container that must never hold this
    credential, and the only thing standing between it and the header is this
    setting.
    """
    import json

    _, _, body = edge.call("/docs/rest", credential=("docs", DOCS_PASSWORD))
    assert "authorization" not in json.loads(body)["headers"]


@requires_docker
def test_a_rotated_credential_replaces_the_one_before_it(edge: Edge) -> None:
    """D252, as a test that goes red if the indirection comes back.

    This is the defect the host found on the first documentation rotation this
    project ever performed: the new password 401, **the old password 200**, and
    the correct hash on disk the whole time. The middleware named a `usersFile`
    path, so the parsed configuration was byte-identical before and after, and
    Traefik rebuilt nothing -- a middleware re-reads that file only when it is
    rebuilt.

    Measured both ways before ADR 0086 was written. With a `usersFile` the
    rewrite has no effect at all; with the hash inline the new credential is
    live and the old one is refused. So the assertion below is on *both* halves:
    a test that only checked the new password would pass against a middleware
    that had started accepting two.

    The rig is restored afterwards, because the fixture is module-scoped and
    every other credential test here holds the original password.
    """
    assert edge.dynamic is not None
    document = edge.dynamic / edge_credentials.middleware_file_name(PROJECT_KEY)
    before = document.read_bytes()

    rotated = "documentation-probe-rotated"
    try:
        document.write_bytes(
            edge_credentials.render_middleware(
                middleware_name=f"{PROJECT_KEY}-docs",
                project_key=PROJECT_KEY,
                hashed=bcrypt_hash(rotated),
            )
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if edge.status("/docs/rest", credential=("docs", rotated)) == 200:
                break
            time.sleep(1)
        else:
            pytest.fail("the rotated credential never became live")

        assert edge.status("/docs/rest", credential=("docs", DOCS_PASSWORD)) == 401, (
            "the credential before the rotation still opens the route -- this is D252, "
            "and it is what a usersFile does"
        )
    finally:
        document.write_bytes(before)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if edge.status("/docs/rest", credential=("docs", DOCS_PASSWORD)) == 200:
                break
            time.sleep(1)
        else:
            pytest.fail("the rig's original credential was not restored")


@requires_docker
def test_the_credential_file_is_not_read_as_configuration(edge: Edge) -> None:
    """A `.htpasswd` beside the YAML, which the file provider must ignore.

    If it parsed one, the directory's whole configuration would be discarded --
    the failure `render_problem` exists to prevent, arriving through a file that
    is not configuration at all. The route below working *is* the assertion: the
    middleware it uses is defined in that directory.
    """
    assert edge.status("/api/rest") == 200
    log = edge.logs()
    for noise in ("htpasswd", "error while building configuration"):
        assert noise not in log.lower(), log[-2000:]


# ---------------------------------------------------------------------------
# The access log (D141)
# ---------------------------------------------------------------------------


@requires_docker
def test_no_query_string_or_credential_reaches_the_access_log(edge: Edge) -> None:
    """The outcome, as ADR 0019 rewrote the claim.

    `accessLog.fields.queryParameters` does not exist, so the query string is
    kept out by dropping `RequestPath` entirely. Asserted by sending a sentinel
    through both channels a token realistically travels in.
    """
    edge.call("/api/rest/notes?token=QUERYSENTINEL7f3a")
    edge.call("/docs/rest", credential=("docs", "HEADERSENTINEL7f3a"))
    time.sleep(1)

    log = edge.logs()
    assert "QUERYSENTINEL7f3a" not in log
    assert "HEADERSENTINEL7f3a" not in log
    # And the control: the log is not simply empty.
    assert '"RouterName"' in log


# ---------------------------------------------------------------------------
# Offline: what the generated middleware says
# ---------------------------------------------------------------------------


#: A valid-shaped bcrypt hash for the offline assertions. Not a real password's
#: hash and never sent anywhere -- `assert_bcrypt` checks the format, and these
#: tests are about what the document says.
SHAPED_HASH = "$2b$12$" + "a" * 53


def test_the_generated_middleware_carries_the_hash_inline() -> None:
    """ADR 0086, and this replaces the `usersFile` assertion it supersedes.

    Stricter rather than merely different: the old test asserted that a path
    ended in `.htpasswd`, which was true throughout D252 -- the defect was that
    the path was a path. This asserts the credential is *in* the document the
    file provider parses, which is the property that makes a rotation take
    effect, and it fails if anyone reintroduces the indirection.
    """
    document = yaml.safe_load(
        edge_credentials.render_middleware(
            middleware_name="m", project_key=PROJECT_KEY, hashed=SHAPED_HASH
        )
    )
    basic = document["http"]["middlewares"]["m"]["basicAuth"]
    assert basic["users"] == [f"{edge_credentials.DOCS_USER}:{SHAPED_HASH}"]
    assert "usersFile" not in basic, "the indirection D252 was caused by is back"
    assert basic["removeHeader"] is True


def test_the_inline_entry_carries_no_trailing_newline() -> None:
    """A newline inside the scalar becomes part of the hash Traefik compares,
    which is a 401 on a correct password -- D165's symptom from a new cause."""
    entry = edge_credentials.htpasswd_entry(SHAPED_HASH)
    assert entry == entry.strip()
    assert "\n" not in entry


def test_the_generated_middleware_defines_no_router_and_no_service() -> None:
    """ADR 0085: a file-provider service can only address a backend by DNS, and
    the Compose service name resolves to whichever project the edge attached to
    first -- measured, ten of ten to project A with project B unreachable. A
    router here would serve one tenant's requests from another tenant's
    container."""
    document = yaml.safe_load(
        edge_credentials.render_middleware(
            middleware_name="m", project_key=PROJECT_KEY, hashed=SHAPED_HASH
        )
    )
    assert set(document["http"]) == {"middlewares"}


def test_a_hash_that_is_not_bcrypt_is_refused() -> None:
    """Every other format fails as a 401 on a correct password.

    `$6$` is what `crypt.crypt` produces by default and what a host `mkpasswd`
    hands you, so this is the mistake that is actually available to make.
    """
    from agentic_postgres.config import ManifestError

    for rejected in (
        "$6$rounds=5000$abcdefgh$" + "x" * 43,
        "{SHA}RCKHgd6ynYLg18AHVWxkQBo+HKA=",
        "plaintext",
        "",
    ):
        with pytest.raises(ManifestError, match="not bcrypt"):
            edge_credentials.htpasswd_entry(rejected)


def test_the_refusal_does_not_echo_the_hash() -> None:
    """A message quoting it would put it in whatever log the deploy writes to,
    and nothing rate-limits a file."""
    from agentic_postgres.config import ManifestError

    secret = "$6$rounds=5000$SENSITIVE$" + "x" * 43
    with pytest.raises(ManifestError) as raised:
        edge_credentials.htpasswd_entry(secret)
    assert "SENSITIVE" not in str(raised.value)


def test_a_user_name_cannot_forge_a_second_field() -> None:
    from agentic_postgres.config import ManifestError

    with pytest.raises(ManifestError):
        edge_credentials.htpasswd_entry("$2b$12$" + "a" * 53, user="docs:admin")

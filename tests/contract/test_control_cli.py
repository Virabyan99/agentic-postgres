"""`apg login|logout|context|org|project|compute|operation` against the real control app.

CTL-CLI-001 (D2066), and Session 38's verbs (D2169, D2163): `project create|
claim|status|sleep|wake|export|delete`, `compute get|set`, `operation
show|list|wait|cancel`. The reconciler does not run here: its half -- an
operation claimed and finished -- is written as the superuser, the way the
reconciler writes it; the project's own `/auth/reset-password` and a provider's
download URL are a loopback stand-in that records what reached it (`Elsewhere`).

The control app is served by `uvicorn.Server` on `127.0.0.1:<free port>` over
`control_cluster`, and **every command runs as a subprocess against it** --
`bin/login.sh`, `bin/org.sh` and the rest, exactly as a person types them --
never a fake server and never an in-process call (CLAUDE.md §7 question 6).
Each proof gets its own `HOME`, so its state directory is its own.

What is proved is the client's half: a 0700 directory of 0600 files, a secret
read only from a checked private file or a TTY and written only to `--output`
or a terminal, https except loopback, a logout the server hears, and the
endpoint read from the context. What the routes do is the Run 4/5 modules'.
"""

# ruff: noqa: S608 -- every interpolated value is an id, a key or a token this
# module minted, against a throwaway cluster.

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import control_cluster as cc
import pytest

from agentic_postgres import REPO_ROOT
from app import operations

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

BIN = REPO_ROOT / "bin"


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.served_app(cluster, tmp_path_factory.mktemp("control-cli")) as pair:
                yield pair
    except RuntimeError as exc:
        pytest.skip(str(exc))


class Person:
    """One person at one terminal: a HOME of their own and the five commands."""

    def __init__(self, home: Path, endpoint: str) -> None:
        self.home = home
        self.endpoint = endpoint
        self.state = home / ".config" / "apg"

    def run(
        self, command: str, *argv: str, stdin: str | None = None, trust: Path | None = None
    ) -> subprocess.CompletedProcess:
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
        }
        if trust is not None:
            # The one certificate a TLS stand-in serves, trusted by OpenSSL's
            # own variable -- the client's code path is the production one.
            environment["SSL_CERT_FILE"] = str(trust)
        return subprocess.run(
            [str(BIN / f"{command}.sh"), *argv],
            input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL,
            capture_output=True, text=True, env=environment, timeout=120, check=False,
        )  # fmt: skip

    def private(self, name: str, text: str, mode: int = 0o600) -> Path:
        path = self.home / name
        path.write_text(text + "\n", encoding="utf-8")
        path.chmod(mode)
        return path

    def login(self, username: str, *, stdin: str | None = None) -> subprocess.CompletedProcess:
        password = self.private(f"{username}.password", cc.PASSWORD)
        argv = ["password", "--endpoint", self.endpoint, "--username", username,
                "--password-file", str(password)]  # fmt: skip
        if stdin is not None:
            argv.append("--totp-code-stdin")
        return self.run("login", *argv, stdin=stdin)


@pytest.fixture
def person(served: Any, tmp_path: Path) -> Person:
    endpoint, _ = served
    home = tmp_path / "home"
    home.mkdir()
    return Person(home, endpoint)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _post(url: str, body: dict[str, Any]) -> int:
    request = urllib.request.Request(  # noqa: S310 -- a loopback test server
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )  # fmt: skip
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def _get(url: str, bearer: str) -> int:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def _member(served: Any, username: str) -> tuple[str, str]:
    """A plain account that is a `member` of a fresh organisation; (user, org)."""
    _, drive = served
    owner = drive.account(f"{username}-owner")
    org = drive.organization(owner, f"{username}'s organisation")
    user = drive.account(username)
    drive.member(org, user, "member")
    return user, org


def test_the_state_directory_is_private(person: Person, served: Any) -> None:
    """A login creates `$HOME/.config/apg` 0700 holding `context.json` and
    `session.json` 0600; the session holds the refresh token alone and nothing
    on disk holds an access token. A directory widened to 0755, or replaced by a
    symlink, is refused (exit 3) rather than repaired; the control: put back,
    it is read again."""
    _member(served, "state-member")
    login = person.login("state-member")
    assert login.returncode == 0, login.stderr
    assert _mode(person.state) == 0o700
    assert sorted(p.name for p in person.state.iterdir()) == ["context.json", "session.json"]
    for name in ("context.json", "session.json"):
        assert _mode(person.state / name) == 0o600, name
    session = json.loads((person.state / "session.json").read_text())
    assert list(session) == ["refresh_token"]
    context = json.loads((person.state / "context.json").read_text())
    assert context["endpoint"] == person.endpoint and context["session"] is True
    for name in ("context.json", "session.json"):
        assert "eyJ" not in (person.state / name).read_text(), f"an access token in {name}"

    person.state.chmod(0o755)
    widened = person.run("context", "show")
    assert widened.returncode == 3 and "mode 0755" in widened.stderr, widened.stderr
    person.state.chmod(0o700)
    assert person.run("context", "show").returncode == 0

    moved = person.home / "elsewhere"
    person.state.rename(moved)
    person.state.symlink_to(moved)
    linked = person.run("context", "show")
    assert linked.returncode == 3 and "symlink" in linked.stderr, linked.stderr


def test_a_symlinked_or_wide_file_is_refused(person: Person, served: Any) -> None:
    """A key file at 0644, a symlink to a 0600 key file, a password file at
    0640, and a context file replaced by a symlink: each exit 3, and no context
    is written by a refused login. The control: the same key in a 0600 regular
    file logs in, and the context names the file, never the key."""
    _member(served, "file-member")
    assert person.login("file-member").returncode == 0
    key_path = person.home / "key"
    created = person.run("org", "key-create", "--name", "cli", "--scopes", "projects:read",
                         "--output", str(key_path))  # fmt: skip
    assert created.returncode == 0, created.stderr
    key = key_path.read_text().strip()
    assert person.run("logout").returncode == 0
    (person.state / "context.json").unlink()

    wide = person.private("wide-key", key, 0o644)
    refused = person.run("login", "key", "--endpoint", person.endpoint, "--key-file", str(wide))
    assert refused.returncode == 3 and "mode 0644" in refused.stderr, refused.stderr
    link = person.home / "linked-key"
    link.symlink_to(key_path)
    refused = person.run("login", "key", "--endpoint", person.endpoint, "--key-file", str(link))
    assert refused.returncode == 3 and "symlink" in refused.stderr, refused.stderr
    loose = person.private("loose.password", cc.PASSWORD, 0o640)
    refused = person.run("login", "password", "--endpoint", person.endpoint,
                         "--username", "file-member", "--password-file", str(loose))  # fmt: skip
    assert refused.returncode == 3 and "mode 0640" in refused.stderr, refused.stderr
    assert not (person.state / "context.json").exists(), "a refused login wrote a context"

    served_key = person.run("login", "key", "--endpoint", person.endpoint,
                            "--key-file", str(key_path))  # fmt: skip
    assert served_key.returncode == 0, served_key.stderr
    context_text = (person.state / "context.json").read_text()
    assert key not in context_text and str(key_path) in context_text

    real = person.state / "context.json"
    kept = person.home / "context-copy.json"
    real.rename(kept)
    real.symlink_to(kept)
    shown = person.run("context", "show")
    assert shown.returncode == 3 and "symlink" in shown.stderr, shown.stderr


def test_a_secret_is_read_only_from_a_private_file_or_a_tty(person: Person, served: Any) -> None:
    """With no TTY: no password file is exit 3; a second factor arrives on
    stdin (`--totp-code-stdin`) and its absence is the server's refusal with
    the flag named. A key and an invitation go to `--output` (0600) and never to
    stdout; an `--output` that exists is refused before anything is minted; a
    seed is refused to a pipe BEFORE the server stores one. Nothing secret is in
    any command's argv: they carry only file paths."""
    from app import totp

    _, drive = served
    owner = drive.account("secret-owner")
    org = drive.organization(owner, "secret's organisation")
    seed = drive.enable_factor(owner)

    no_file = person.run("login", "password", "--endpoint", person.endpoint,
                         "--username", "secret-owner")  # fmt: skip
    assert no_file.returncode == 3 and "no TTY" in no_file.stderr, no_file.stderr
    without_code = person.login("secret-owner")
    assert without_code.returncode == 5, without_code.stderr
    assert "second_factor_required" in without_code.stderr
    assert "--totp-code-stdin" in without_code.stderr
    code = totp.totp(seed, int(time.time()))
    with_code = person.login("secret-owner", stdin=code + "\n")
    assert with_code.returncode == 0, with_code.stderr
    assert json.loads((person.state / "context.json").read_text())["organization"] == org

    invitation = person.home / "invitation"
    minted = person.run("org", "invite", "--role", "member", "--output", str(invitation))
    assert minted.returncode == 0, minted.stderr
    token = invitation.read_text().strip()
    assert _mode(invitation) == 0o600 and token and token not in minted.stdout
    key_path = person.home / "owner-key"
    created = person.run("org", "key-create", "--name", "k", "--scopes", "projects:read",
                         "--output", str(key_path))  # fmt: skip
    assert created.returncode == 0, created.stderr
    assert _mode(key_path) == 0o600 and key_path.read_text().strip() not in created.stdout

    before = drive.cluster.query("SELECT count(*) FROM app.control_keys;")
    again = person.run("org", "key-create", "--name", "k2", "--scopes", "projects:read",
                       "--output", str(key_path))  # fmt: skip
    assert again.returncode == 2 and "already exists" in again.stderr, again.stderr
    assert drive.cluster.query("SELECT count(*) FROM app.control_keys;") == before

    _member(served, "seed-member")
    other = Person(person.home / "seed", person.endpoint)
    other.home.mkdir()
    assert other.login("seed-member").returncode == 0
    piped = other.run("login", "totp-enroll")
    assert piped.returncode == 2 and "terminal" in piped.stderr, piped.stderr
    seeds = "SELECT count(*) FROM app.control_totp t JOIN app.control_accounts a USING (user_id) "
    seeds += "WHERE a.username = 'seed-member';"
    assert drive.cluster.query(seeds) == ["0"], "a seed was stored for a pipe"
    seed_file = other.home / "seed.txt"
    enrolled = other.run("login", "totp-enroll", "--output", str(seed_file))
    assert enrolled.returncode == 0, enrolled.stderr
    uri, secret = seed_file.read_text().split()
    assert uri.startswith("otpauth://totp/") and secret not in enrolled.stdout
    assert _mode(seed_file) == 0o600 and drive.cluster.query(seeds) == ["1"]


def test_plain_http_is_refused_except_loopback(person: Person, served: Any) -> None:
    """`http://` to any host but 127.0.0.1 or localhost is exit 3 before a
    connection -- for a login, and for a context file edited to one. https to a
    host with nothing listening is exit 6, a different answer. The control:
    http to the loopback server logs in."""
    _member(served, "http-member")
    for endpoint in ("http://control.example.test/api/v1", "http://10.0.0.1:8080/v1"):
        refused = person.run("login", "key", "--endpoint", endpoint,
                             "--key-file", str(person.private("k", "apg_x", 0o600)))  # fmt: skip
        assert refused.returncode == 3 and "plain http" in refused.stderr, refused.stderr
        refused = person.run(
            "login", "password", "--endpoint", endpoint, "--username", "http-member",
            "--password-file", str(person.private("p", cc.PASSWORD)),
        )  # fmt: skip
        assert refused.returncode == 3 and "plain http" in refused.stderr, refused.stderr
    unreachable = person.run("login", "password", "--endpoint", "https://127.0.0.1:9/v1",
                             "--username", "http-member",
                             "--password-file", str(person.private("p2", cc.PASSWORD)))  # fmt: skip
    assert unreachable.returncode == 6 and "could not be reached" in unreachable.stderr

    assert person.login("http-member").returncode == 0
    context_path = person.state / "context.json"
    context = json.loads(context_path.read_text())
    context["endpoint"] = "http://10.0.0.1:8080/v1"
    context_path.write_text(json.dumps(context))
    edited = person.run("project", "list")
    assert edited.returncode == 3 and "plain http" in edited.stderr, edited.stderr


def test_logout_revokes_the_session(person: Person, served: Any) -> None:
    """`logout` sends the refresh token to `DELETE /v1/sessions/current` and only
    then removes `session.json`: the token it held is refused by the server
    afterwards. A key context is forgotten and the key NOT revoked -- it still
    reads. The control: before logout the same token is one the server honours
    (exchanged here, and its successor is what logout ends)."""
    _member(served, "logout-member")
    assert person.login("logout-member").returncode == 0
    held = json.loads((person.state / "session.json").read_text())["refresh_token"]
    assert _post(f"{person.endpoint}/sessions/refresh", {"refresh_token": held}) == 200
    # The exchange above consumed `held`; the client's next command finds out.
    shown = person.run("project", "list")
    assert shown.returncode == 3 and "log in again" in shown.stderr, shown.stderr

    assert person.login("logout-member").returncode == 0
    listed = person.run("project", "list")
    assert listed.returncode == 0, listed.stderr
    held = json.loads((person.state / "session.json").read_text())["refresh_token"]
    out = person.run("logout", "--json")
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {"ended": "session"}
    assert not (person.state / "session.json").exists()
    assert _post(f"{person.endpoint}/sessions/refresh", {"refresh_token": held}) == 401

    assert person.login("logout-member").returncode == 0
    key_path = person.home / "key"
    assert person.run("org", "key-create", "--name", "k", "--scopes", "projects:read",
                      "--output", str(key_path)).returncode == 0  # fmt: skip
    assert person.run("logout").returncode == 0
    assert person.run("login", "key", "--endpoint", person.endpoint,
                      "--key-file", str(key_path)).returncode == 0  # fmt: skip
    forgot = person.run("logout")
    assert forgot.returncode == 0 and "NOT revoked" in forgot.stdout, forgot.stdout
    assert not (person.state / "context.json").exists()
    assert _get(f"{person.endpoint}/projects", key_path.read_text().strip()) == 200


def test_project_list_reads_the_endpoint_from_the_context(person: Person, served: Any) -> None:
    """After a login, `project list|use|show` take no endpoint: it is the
    context's, and so is the organisation. A person's session and a key read
    the same records; a project of another organisation is the server's
    `not_found` (exit 5). The control that the endpoint really comes from the
    context: pointed at a port nothing listens on, the same command is exit 6."""
    _, drive = served
    _, org = _member(served, "list-member")
    other_owner = drive.account("list-other-owner")
    other = drive.organization(other_owner, "another")
    for key, organization in (("listed-prod", org), ("hidden-prod", other)):
        drive.cluster.query(
            f"SELECT app.control_adopt_project('{key}', '{organization}', "
            f"'{key.split('-')[0]}', 'prod', '{key}.test', '1.15.0', 'abc');"
        )
    assert person.login("list-member").returncode == 0
    listed = person.run("project", "list", "--json")
    assert listed.returncode == 0, listed.stderr
    assert [p["key"] for p in json.loads(listed.stdout)] == ["listed-prod"]
    assert person.run("project", "use", "--project-key", "listed-prod").returncode == 0
    shown = person.run("project", "show", "--json")
    assert shown.returncode == 0 and json.loads(shown.stdout)["domain"] == "listed-prod.test"
    hidden = person.run("project", "show", "--project-key", "hidden-prod")
    assert hidden.returncode == 5 and "not_found" in hidden.stderr, hidden.stderr

    key_path = person.home / "key"
    assert person.run("org", "key-create", "--name", "k",
                      "--scopes", "projects:read,organizations:read",
                      "--output", str(key_path)).returncode == 0  # fmt: skip
    assert person.run("logout").returncode == 0
    assert person.run("login", "key", "--endpoint", person.endpoint,
                      "--key-file", str(key_path)).returncode == 0  # fmt: skip
    by_key = person.run("project", "list", "--json")
    assert by_key.returncode == 0, by_key.stderr
    assert [p["key"] for p in json.loads(by_key.stdout)] == ["listed-prod"]

    context_path = person.state / "context.json"
    context = json.loads(context_path.read_text())
    context["endpoint"] = "http://127.0.0.1:9/v1"
    context_path.write_text(json.dumps(context))
    gone = person.run("project", "list")
    assert gone.returncode == 6 and "could not be reached" in gone.stderr, gone.stderr


# ---------------------------------------------------------------------------
# Session 38 Run 8: the operations' verbs (D2169, D2163)
# ---------------------------------------------------------------------------


class Elsewhere:
    """Somewhere that is not the control plane -- a project's own address, a
    provider's download URL: records every request, answers from `routes`."""

    def __init__(self, tls_directory: Path | None = None) -> None:
        self.requests: list[tuple[str, str, bytes]] = []
        self.routes: dict[tuple[str, str], tuple[int, dict[str, str], bytes]] = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.requests.append((self.command, self.path, body))
                status, headers, payload = outer.routes.get(
                    (self.command, self.path.split("?")[0]), (404, {}, b"{}")
                )
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = _answer

            def log_message(self, *_arguments: Any) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        scheme = "http"
        self.certificate: Path | None = None
        if tls_directory is not None:
            import ssl

            self.certificate = _self_signed(tls_directory)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(self.certificate, tls_directory / "key.pem")
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
            scheme = "https"
        self.base = f"{scheme}://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def answer(
        self, method: str, path: str, status: int, payload: bytes = b"{}", **headers: str
    ) -> None:
        self.routes[(method, path)] = (status, headers, payload)


def _self_signed(directory: Path) -> Path:
    """A certificate for 127.0.0.1 (an IP SAN) and its key, written to `directory`."""
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    (directory / "key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path = directory / "certificate.pem"
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return path


@pytest.fixture(scope="module")
def elsewhere() -> Any:
    place = Elsewhere()
    yield place
    place.server.shutdown()


@pytest.fixture(scope="module")
def project_address(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """A project's own address over TLS: the registry's `app_route` is https."""
    place = Elsewhere(tmp_path_factory.mktemp("project-tls"))
    yield place
    place.server.shutdown()


@pytest.fixture
def accepting(monkeypatch: pytest.MonkeyPatch) -> None:
    """The six types accepted, for this proof only: the served app runs in this
    process, so the module the routes read is the one patched."""
    monkeypatch.setattr(operations, "ACCEPTED_TYPES", operations.EXECUTED_TYPES)


def _ready_slot(drive: Any) -> None:
    reading = [{"key": "slot1-prod", "state": "ready", "region_id": "eu-hel-1"}]
    drive.cluster.query(f"SELECT app.control_record_slots('{json.dumps(reading)}'::jsonb)")


def _adopt(drive: Any, organization: str, key: str, app_route: str) -> None:
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{organization}', '{key.split('-')[0]}', "
        f"'prod', '{key}.test', '1.16.0', 'abc', 'eu-hel-1', 'small', NULL, '{app_route}')"
    )


def _finish(drive: Any, operation: str, status: str, code: str | None = None,
            result: dict[str, Any] | None = None, *, secret: str | None = None,
            project_key: str | None = None) -> None:  # fmt: skip
    """The reconciler's half, as the superuser: running, then finished."""
    drive.cluster.query(
        "UPDATE app.control_operations SET status = 'running', started_at = now(), "
        f"attempt = attempt + 1 WHERE id = '{operation}'"
    )
    if project_key:
        drive.cluster.query(
            f"SELECT app.control_advance_operation('{operation}', 'registry', 90, '{project_key}')"
        )

    def literal(value: str | None) -> str:
        return "NULL" if value is None else "'" + value.replace("'", "''") + "'"

    document = json.dumps(result) if result is not None else None
    drive.cluster.query(
        f"SELECT app.control_finish_operation('{operation}', {literal(status)}, "
        f"{literal(code)}, {literal(document)}::jsonb, {literal(secret)})"
    )


def _pending(drive: Any, where: str) -> str:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        rows = drive.cluster.query(
            f"SELECT id FROM app.control_operations WHERE status = 'pending' AND {where}"
        )
        if rows:
            return rows[0]
        time.sleep(0.2)
    raise AssertionError(f"no pending operation where {where}")


def _created(person: Person) -> tuple[dict[str, Any], str]:
    """`project create`, its operation, and the handoff token it kept."""
    made = person.run("project", "create", "--name", "Shop backend", "--profile", "small",
                      "--admin-username", "shop.admin", "--json")  # fmt: skip
    assert made.returncode == 0, made.stderr
    operation = json.loads(made.stdout)["operation"]
    token = (person.state / "handoffs" / operation["id"]).read_text().strip()
    return operation, token


def test_only_the_hash_reaches_the_control_plane(
    person: Person, served: Any, accepting: None
) -> None:
    """ADR 0260: `create` mints the token, keeps it in `handoffs/<operation>`,
    and sends its SHA-256 alone -- the control plane's row carries the hash and
    nothing of the token, and no output prints it."""
    _, drive = served
    _member(served, "hash-member")
    _ready_slot(drive)
    assert person.login("hash-member").returncode == 0
    operation, token = _created(person)
    assert len(token) == 43
    stored = drive.cluster.query(
        "SELECT arguments ->> 'handoff_sha256', arguments::text FROM app.control_operations "
        f"WHERE id = '{operation['id']}'"
    )[0]
    digest, arguments = stored.split("|", 1)
    assert digest == hashlib.sha256(token.encode()).hexdigest()
    assert token not in arguments
    assert drive.cluster.query(
        "SELECT count(*) FROM app.control_operations WHERE "
        f"position('{token}' in arguments::text || coalesce(result::text, '')) > 0"
    ) == ["0"]
    # A refused creation keeps no token: a second one while the first is in flight.
    again = person.run("project", "create", "--name", "Second", "--profile", "small",
                       "--admin-username", "shop.admin")  # fmt: skip
    assert again.returncode == 5 and "conflict" in again.stderr, again.stderr
    assert sorted(p.name for p in (person.state / "handoffs").iterdir()) == [operation["id"]]


def test_the_handoff_token_is_private_and_removed_after_claim(
    person: Person, served: Any, accepting: None, project_address: Elsewhere
) -> None:
    """The token file is 0600 in a 0700 directory; `claim` presents it to the
    PROJECT's own `/auth/reset-password` (its address read from the registry),
    with the password from a 0600 file -- and removes it only once the project
    accepted it. The control: a project that refuses leaves the file in place."""
    _, drive = served
    _, org = _member(served, "claim-member")
    _ready_slot(drive)
    assert person.login("claim-member").returncode == 0
    operation, token = _created(person)
    handoffs = person.state / "handoffs"
    assert _mode(handoffs) == 0o700 and _mode(handoffs / operation["id"]) == 0o600
    key = "slot1-prod"
    elsewhere = project_address
    _adopt(drive, org, key, f"{elsewhere.base}/{org}/api/app")
    _finish(drive, operation["id"], "succeeded", result={"project_key": key}, project_key=key)
    password = person.private("chosen.password", "the administrator's own choice")
    reset = f"/{org}/api/app/auth/reset-password"

    elsewhere.answer("POST", reset, 401, b'{"error": "authentication_failed"}')
    refused = person.run(
        "project", "claim", "--project-key", key, "--password-file", str(password),
        trust=elsewhere.certificate,
    )  # fmt: skip
    assert refused.returncode == 5 and "authentication_failed" in refused.stderr, refused.stderr
    assert (handoffs / operation["id"]).exists(), "a refused claim removed the token"

    elsewhere.answer("POST", reset, 200, b'{"credential_version": 2}')
    claimed = person.run(
        "project", "claim", "--project-key", key, "--password-file", str(password),
        trust=elsewhere.certificate,
    )  # fmt: skip
    assert claimed.returncode == 0, claimed.stderr
    sent = [json.loads(body) for method, path, body in elsewhere.requests if path == reset]
    assert sent[-1] == {"reset_token": token, "password": "the administrator's own choice"}
    assert not (handoffs / operation["id"]).exists()
    assert token not in claimed.stdout + claimed.stderr


def test_export_downloads_once_without_following_a_redirect(
    person: Person, served: Any, accepting: None, elsewhere: Elsewhere
) -> None:
    """`export` waits for its operation, fetches the one-time URL, checks the
    archive's SHA-256 against the result and writes it 0600; the URL is printed
    nowhere. A redirect is refused (exit 6) and nothing is written; so is an
    archive that is not the one recorded."""
    _, drive = served
    _, org = _member(served, "export-member")
    key = "slot2-prod"
    _adopt(drive, org, key, "https://slot2.test/api/app")
    assert person.login("export-member").returncode == 0
    archive = b"PGDMP\x01 the customer's schemas"
    elsewhere.answer("GET", "/exports/good.dump", 200, archive)
    elsewhere.answer("GET", "/exports/moved.dump", 302, b"", Location="/exports/good.dump")
    result = {
        "sha256": hashlib.sha256(archive).hexdigest(),
        "size_bytes": len(archive),
        "expires_at": "2026-10-08T12:15:00+00:00",
    }
    for name, url, recorded, expected in (
        ("good", f"{elsewhere.base}/exports/good.dump", result, 0),
        ("moved", f"{elsewhere.base}/exports/moved.dump", result, 6),
        ("altered", f"{elsewhere.base}/exports/good.dump", {**result, "sha256": "0" * 64}, 6),
    ):
        output = person.home / f"{name}.dump"
        running = subprocess.Popen(
            [str(BIN / "project.sh"), "export", "--project-key", key, "--output", str(output),
             "--timeout", "60", "--interval", "1"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(person.home),
                 "LANG": "C.UTF-8"},
        )  # fmt: skip
        operation = _pending(drive, f"project_key = '{key}' AND type = 'project.export'")
        _finish(drive, operation, "succeeded", result=recorded, secret=url)
        out, err = running.communicate(timeout=90)
        assert running.returncode == expected, (name, err)
        assert url not in out + err, name
        if expected == 0:
            assert output.read_bytes() == archive and _mode(output) == 0o600
            assert drive.cluster.query(
                f"SELECT count(*) FROM app.control_operations WHERE id = '{operation}' "
                "AND result_secret IS NULL"
            ) == ["1"], "the URL was taken once"
        else:
            assert not output.exists(), name


def test_operation_wait_reads_each_outcome(
    person: Person, served: Any, accepting: None, elsewhere: Elsewhere
) -> None:
    """`wait`: succeeded 0; failed 5 with its error code and reason; still
    pending at its own timeout 7; a server that answers 5xx is 6 -- never read
    as any outcome (ADR 0195)."""
    _, drive = served
    _, org = _member(served, "wait-member")
    key = "slot3-prod"
    _adopt(drive, org, key, "https://slot3.test/api/app")
    assert person.login("wait-member").returncode == 0

    def requested() -> str:
        slept = person.run("project", "sleep", "--project-key", key, "--json")
        assert slept.returncode == 0, slept.stderr
        return json.loads(slept.stdout)["operation"]["id"]

    first = requested()
    _finish(drive, first, "succeeded", result={"steps": []})
    done = person.run("operation", "wait", "--operation", first, "--interval", "1")
    assert done.returncode == 0 and "succeeded" in done.stdout, done.stderr

    second = requested()
    _finish(
        drive, second, "failed", "operation_failed", {"reason": "project-runtime stop exited 1"}
    )
    failed = person.run("operation", "wait", "--operation", second, "--interval", "1")
    assert failed.returncode == 5, failed.stderr
    assert "operation_failed" in failed.stderr and "project-runtime stop exited 1" in failed.stderr

    third = requested()
    pending = person.run("operation", "wait", "--operation", third, "--timeout", "2",
                         "--interval", "1")  # fmt: skip
    assert pending.returncode == 7 and "still pending" in pending.stderr, pending.stderr
    cancelled = person.run("operation", "cancel", "--operation", third)
    assert cancelled.returncode == 0, cancelled.stderr

    key_path = person.home / "ops-key"
    assert person.run("org", "key-create", "--name", "ops", "--scopes", "operations:read",
                      "--output", str(key_path)).returncode == 0  # fmt: skip
    assert person.run("logout").returncode == 0
    assert person.run("login", "key", "--endpoint", person.endpoint,
                      "--key-file", str(key_path)).returncode == 0  # fmt: skip
    context_path = person.state / "context.json"
    context = json.loads(context_path.read_text())
    context["endpoint"] = f"{elsewhere.base}/v1"
    context_path.write_text(json.dumps(context))
    elsewhere.answer("GET", f"/v1/operations/{first}", 503, b'{"error": "unavailable"}')
    broken = person.run("operation", "wait", "--operation", first, "--interval", "1")
    assert broken.returncode == 6, broken.stderr


def test_compute_sleep_wake_and_delete_answer_with_an_operation(
    person: Person, served: Any, accepting: None
) -> None:
    """Each write answers 202 with an operation of its own type; a resize
    carries the restart sentence; `delete` refuses a `--confirm` that is not the
    key before anything is sent. `compute get` reads the profile."""
    _, drive = served
    _, org = _member(served, "writes-member")
    key = "slot4-prod"
    _adopt(drive, org, key, "https://slot4.test/api/app")
    assert person.login("writes-member").returncode == 0
    got = person.run("compute", "get", "--project-key", key, "--json")
    assert got.returncode == 0 and json.loads(got.stdout)["profile"] == "small", got.stderr

    resized = person.run("compute", "set", "--project-key", key, "--profile", "standard", "--json")
    assert resized.returncode == 0, resized.stderr
    answer = json.loads(resized.stdout)
    assert answer["operation"]["type"] == "project.resize" and "restart" in answer["message"]
    _finish(drive, answer["operation"]["id"], "succeeded", result={"profile": "standard"})
    for verb, kind in (("wake", "project.wake"), ("sleep", "project.sleep")):
        written = person.run("project", verb, "--project-key", key, "--json")
        assert written.returncode == 0, written.stderr
        operation = json.loads(written.stdout)["operation"]
        assert operation["type"] == kind
        _finish(drive, operation["id"], "succeeded", result={})

    before = drive.cluster.query(
        f"SELECT count(*) FROM app.control_operations WHERE project_key = '{key}'"
    )
    wrong = person.run("project", "delete", "--project-key", key, "--confirm", "slot4")
    assert wrong.returncode == 2 and "nothing was sent" in wrong.stderr, wrong.stderr
    assert (
        drive.cluster.query(
            f"SELECT count(*) FROM app.control_operations WHERE project_key = '{key}'"
        )
        == before
    )
    status = person.run("project", "status", "--project-key", key, "--json")
    assert status.returncode == 0 and json.loads(status.stdout)["state"] == "sleeping"

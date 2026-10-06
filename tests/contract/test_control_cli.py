"""`apg login|logout|context|org|project` against the real control app (CTL-CLI-001, D2066).

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

from __future__ import annotations

import json
import os
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import control_cluster as cc
import pytest

from agentic_postgres import REPO_ROOT

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
        self, command: str, *argv: str, stdin: str | None = None
    ) -> subprocess.CompletedProcess:
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
        }
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

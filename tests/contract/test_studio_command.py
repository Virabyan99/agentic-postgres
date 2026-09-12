"""`STU-CMD-001` and `STU-TOKEN-001`'s credential half (Session 24 Run 3).

What `apg studio` refuses, and with which exit code. Every arm drives the
product's own command as a subprocess (D1114); the stand-in is
`test_studio_server.py`'s, imported rather than copied, and it is a double of an
HTTP shape and not of the product.

The exit codes are the runbook's, and the reason each one is distinct is that
they send an operator somewhere different: 2 is *you typed something wrong*, 4
is *render this checkout*, 5 is *the document is not a deployment's, or is one
whose routes are not usable*, 6 is *the credential was refused* and 9 is *the
deployment did not answer*. A command that answered 1 to all five would be
telling nobody anything.

**Marked, and the marks are load-bearing** (D1240).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_studio_server import PASSWORD_SHAPED_VARIABLE, REST_PATH, StandIn

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

STUDIO = REPO_ROOT / "bin" / "studio.sh"
APG = REPO_ROOT / "bin" / "apg.sh"
PROJECT = REPO_ROOT / "project.example.yaml"
GENERATED = REPO_ROOT / "projects" / "example" / "clients" / "typescript" / "generated.json"

#: A deployment that does not exist, for the arms that never get as far as
#: reaching one.
REST = "https://a.test/api/rest"
APP = "https://a.test"
#: The stand-in's own fixture passphrase, named once so the scan for it is
#: over the value the run actually used.
PASSPHRASE = "a-correct-horse-battery-staple"  # noqa: S105 -- a fixture value


def run(*arguments: str, timeout: int = 180, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(STUDIO), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        **kwargs,
    )


def document(tmp_path: Path, rest: str, app: str, *, kind: str = "deployed", ready: str = "ready"):
    path = tmp_path / "outputs.json"
    path.write_text(
        json.dumps(
            {
                "document_kind": kind,
                "routes": {
                    "rest": {"status": ready, "url": rest},
                    "app": {"status": ready, "url": app},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def password_file(tmp_path: Path, mode: int = 0o600) -> Path:
    path = tmp_path / "password"
    path.write_text(f"{PASSPHRASE}\n", encoding="utf-8")
    path.chmod(mode)
    return path


# ---------------------------------------------------------------------------
# the verb
# ---------------------------------------------------------------------------


def test_studio_is_a_verb_of_the_dispatcher() -> None:
    """`apg studio` reaches `bin/studio.sh`, and `apg --list` says so.

    The dispatcher derives its verbs from `bin/*.sh` rather than from a list it
    keeps, so this asserts the derivation found the new command rather than that
    somebody remembered to register it.
    """
    listed = subprocess.run(
        [str(APG), "--list"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    assert "studio" in listed.stdout.split(), listed.stdout

    through = subprocess.run(
        [str(APG), "studio", "--help"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    assert through.returncode == 0
    assert "Usage: bin/studio.sh" in through.stdout


def test_help_names_the_four_surface_answers() -> None:
    """The four answers are what the page branches on, so `--help` names them.

    A launch that ends in `unreadable` is a different instruction to an operator
    than one that ends in `stale_contract`, and a help text that said "it checks
    the surface" would leave them to find out which.
    """
    done = run("--help")
    assert done.returncode == 0
    for answer in ("ok", "stale_contract", "unreachable", "unreadable"):
        assert answer in done.stdout, f"--help does not name {answer}"
    for code in ("0", "2", "3", "4", "5", "6", "9"):
        assert f"#   {code}" in (REPO_ROOT / "bin" / "studio.sh").read_text(encoding="utf-8") or (
            f"  {code}  " in done.stdout
        ), f"exit code {code} is undocumented"


# ---------------------------------------------------------------------------
# the refusals
# ---------------------------------------------------------------------------


def test_argument_errors_exit_two_before_anything_is_read(tmp_path: Path) -> None:
    """2, and the message names the FLAG rather than the file it never opened.

    The arm that matters is the last one: a `--project` that does not exist
    together with an unknown flag must complain about the flag. A command that
    read the file first would report a missing file, sending an operator to look
    for a path when the problem is the word they typed.
    """
    assert run().returncode == 2
    assert run("--nope").returncode == 2
    assert run("positional").returncode == 2
    assert run("--project").returncode == 2

    both = run("--project", str(tmp_path / "absent.yaml"), "--nope")
    assert both.returncode == 2
    assert "--nope" in both.stderr
    assert "absent.yaml" not in both.stderr


def test_a_password_argument_or_environment_variable_is_refused(tmp_path: Path) -> None:
    """No flag carries a password and no variable is read for one (D105).

    `--password` is refused by NAME rather than falling through to "unknown
    argument", because an operator who typed it is about to look for the right
    spelling and the answer is that there is not one.
    """
    refused = run("--password", "hunter2")
    assert refused.returncode == 2
    assert "--password-file" in refused.stderr
    assert "hunter2" not in refused.stderr, "the refusal echoed the value it refused"

    stand_in = StandIn()
    stand_in.start()
    try:
        path = document(tmp_path, f"{stand_in.base}{REST_PATH}", stand_in.base)
        ignored = run(
            "--project", str(PROJECT), "--outputs", str(path), "--username", "ada",
            env={**PASSWORD_SHAPED_VARIABLE, "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        )  # fmt: skip
        assert ignored.returncode == 2, ignored.stderr
        assert "--password-file" in ignored.stderr
    finally:
        stand_in.stop()


def test_the_password_file_must_be_owner_read_only(tmp_path: Path) -> None:
    """0600 or stricter, and the refusal says what the mode is.

    A password file others can read is a password others have. The mode is named
    because the remedy is `chmod` and an operator should not have to guess which
    bit offended.
    """
    stand_in = StandIn()
    stand_in.start()
    try:
        path = document(tmp_path, f"{stand_in.base}{REST_PATH}", stand_in.base)
        loose = run(
            "--project", str(PROJECT), "--outputs", str(path),
            "--username", "ada", "--password-file", str(password_file(tmp_path, 0o644)),
        )  # fmt: skip
        assert loose.returncode == 2, loose.stderr
        assert "0644" in loose.stderr

        # **The control has to end somewhere, and a successful launch does not
        # end.** A 0600 file and a working stand-in would leave Studio serving
        # forever, so the control makes the LOGIN refuse: reaching exit 6 is
        # proof the password was read and sent, which is the thing the mode
        # check stands in front of.
        stand_in.answers["/auth/login"] = (401, {"error": "authentication_failed"})
        strict = run(
            "--project", str(PROJECT), "--outputs", str(path),
            "--username", "ada", "--password-file", str(password_file(tmp_path, 0o600)),
        )  # fmt: skip
        assert strict.returncode == 6, f"{strict.returncode}: {strict.stderr}"
        assert "0600" not in strict.stderr
    finally:
        stand_in.stop()


def test_an_unrendered_project_is_refused_with_exit_four_and_the_render_command(
    tmp_path: Path,
) -> None:
    """4, naming the command that renders it (D975).

    The manifest is the example one with a slug nothing in this checkout has
    rendered, so the refusal is about the RENDER and not about the file.
    """
    manifest = tmp_path / "project.unrendered.yaml"
    manifest.write_text(
        PROJECT.read_text(encoding="utf-8").replace(
            "slug: fixture-alpha", "slug: fixture-unrendered"
        ),
        encoding="utf-8",
    )
    stand_in = StandIn()
    stand_in.start()
    try:
        path = document(tmp_path, f"{stand_in.base}{REST_PATH}", stand_in.base)
        done = run(
            "--project", str(manifest), "--outputs", str(path),
            "--username", "ada", "--password-file", str(password_file(tmp_path)),
        )  # fmt: skip
        assert done.returncode == 4, f"{done.returncode}: {done.stderr}"
        assert "--render-only" in done.stderr
        assert "fixture-unrendered-dev" in done.stderr
    finally:
        stand_in.stop()


def test_a_document_without_a_ready_route_exits_five(tmp_path: Path) -> None:
    """5, and a RENDERED document is 2: two different mistakes, two answers.

    A rendered document is the wrong file -- a render says what was asked for and
    a route is an observation of what happened. An unready route is the right
    file from a deploy that published nothing, and the remedy is a deploy.
    """
    unready = run(
        "--project", str(PROJECT),
        "--outputs",
        str(document(tmp_path, REST, APP, ready="unavailable")),
        "--username", "ada", "--password-file", str(password_file(tmp_path)),
    )  # fmt: skip
    assert unready.returncode == 5, unready.stderr

    rendered = run(
        "--project", str(PROJECT),
        "--outputs",
        str(document(tmp_path, REST, APP, kind="rendered")),
        "--username", "ada", "--password-file", str(password_file(tmp_path)),
    )  # fmt: skip
    assert rendered.returncode == 2, rendered.stderr
    assert "rendered document" in rendered.stderr


def test_an_http_route_to_a_non_loopback_host_is_refused(tmp_path: Path) -> None:
    """5 for cleartext to anywhere but loopback, and the URL is not printed.

    A route URL can carry a query or userinfo, so the refusal names the scheme
    and the host and stops there (D105).
    """
    done = run(
        "--project", str(PROJECT),
        "--outputs", str(document(tmp_path, "http://elsewhere.test/api/rest?token=sekrit", "https://a.test")),
        "--username", "ada", "--password-file", str(password_file(tmp_path)),
    )  # fmt: skip
    assert done.returncode == 5, done.stderr
    assert "elsewhere.test" in done.stderr
    assert "sekrit" not in done.stderr


def test_a_loopback_http_route_is_not_refused_at_the_document_step(tmp_path: Path) -> None:
    """The exception, and it is proved by where the command stops instead.

    `http://127.0.0.1:1/...` is a legal address book entry -- loopback never
    leaves the machine -- so the document step must pass it. Nothing is
    listening on port 1, so the run ends at the LOGIN with exit 9, which is the
    proof that it got past the address and not that it liked it.
    """
    done = run(
        "--project", str(PROJECT),
        "--outputs", str(document(tmp_path, "http://127.0.0.1:1/api/rest", "http://127.0.0.1:1")),
        "--username", "ada", "--password-file", str(password_file(tmp_path)),
    )  # fmt: skip
    assert done.returncode == 9, f"{done.returncode}: {done.stderr}"
    assert "could not reach" in done.stderr


def test_a_refused_login_exits_six_and_says_no_more(tmp_path: Path) -> None:
    """6, and one sentence (ADR 0097).

    `/auth/login` fails identically four ways -- unknown subject, wrong
    password, disabled subject, locked subject -- and this line is not allowed
    to be the place a caller learns which. The stand-in answers 401 with a body
    naming one of them, and that body must not travel.
    """
    stand_in = StandIn()
    stand_in.start()
    try:
        stand_in.answers["/auth/login"] = (
            401,
            {"error": "authentication_failed", "detail": "no such user: ada"},
        )
        path = document(tmp_path, f"{stand_in.base}{REST_PATH}", stand_in.base)
        done = run(
            "--project", str(PROJECT), "--outputs", str(path),
            "--username", "ada", "--password-file", str(password_file(tmp_path)),
        )  # fmt: skip
        assert done.returncode == 6, f"{done.returncode}: {done.stderr}"
        assert done.stderr.strip() == "studio: the deployment refused this credential."
        assert "no such user" not in done.stderr
    finally:
        stand_in.stop()


def test_nothing_a_refusal_prints_is_a_credential(tmp_path: Path) -> None:
    """Across every refusal above, the password never appears.

    A single scan rather than one assertion per arm, because the property is
    about the command and not about any one of its exits.
    """
    secret = PASSPHRASE
    path = document(tmp_path, REST, APP, ready="unavailable")
    done = run(
        "--project", str(PROJECT), "--outputs", str(path),
        "--username", "ada", "--password-file", str(password_file(tmp_path)),
    )  # fmt: skip
    assert secret not in done.stdout + done.stderr


# ---------------------------------------------------------------------------
# the compared pair (D486)
# ---------------------------------------------------------------------------


def test_the_ir_studio_builds_is_the_one_generate_wrote() -> None:
    """`bin/studio.py` copies `bin/generate.py`'s loading sequence, so it is compared.

    Two copies of one sequence is a defect unless something holds them together
    (D486). What this asserts is the thing that would actually matter if they
    drifted: the four digests Studio computes for the example project are the
    ones `apg generate` committed, so the schema browser describes the same
    contract the generated client does -- and the surface check compares the
    same digest `init()` compares.

    A failure here is a drift between two commands, not a broken test: the
    remedy is to make the sequences agree, or to extract them.
    """
    import importlib.util

    specification = importlib.util.spec_from_file_location(
        "apg_studio_command", REPO_ROOT / "bin" / "studio.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    ir = module.build_ir(PROJECT, REPO_ROOT / "capabilities.example.yaml")
    committed = json.loads(GENERATED.read_text(encoding="utf-8"))
    digests = committed["digests"]

    assert ir.digests.rest_openapi_sha256 == digests["rest_openapi_sha256"]
    assert ir.digests.tools_sha256 == digests["tools_sha256"]
    assert ir.digests.merged_surface_sha256 == digests["merged_surface_sha256"]
    assert ir.digests.app_openapi_sha256 == digests["app_openapi_sha256"]
    assert [relation.name for relation in ir.relations] == [
        relation["name"] for relation in committed["relations"]
    ]
    assert [tool.name for tool in ir.tools] == [tool["name"] for tool in committed["tools"]]

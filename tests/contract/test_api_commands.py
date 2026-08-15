"""`bin/dev-token.sh`, `bin/api.sh` and `bin/docs.sh`: what they refuse.

Three properties carry this file, and each of them is the kind a test passes by
not exercising the path that would break it -- so each is asserted twice, once
against the source and once against the running command.

**No token becomes an argument or reaches standard output** (D105). `dev-token`
does not emit one at all: it signs, puts the value in a child's environment
through `execve`, and becomes that child. `execve` and not `env VAR=... cmd`,
because the second puts the token in `env`'s own argument vector where `ps`
shows it to every user on the host.

**No caller-supplied URL, method, header, path, role or subject.** `api.sh`
enumerates five operations; `docs.sh` two; `dev-token` three roles and a bounded
lifetime. The subject is derived from the project rather than accepted, because
a caller who can name a subject can read any owner's rows through a row policy
that is working exactly as designed.

**No operation authenticates to the documentation route.** `docs.sh check`
proves the negative half of `SEC-DOCS-001` -- the route refuses -- and there is
deliberately no operation that would have to read the Basic Auth password to
prove the positive half.

The live halves of all three run in Run 9, against a deployment. What is here is
everything provable without one, which is most of the surface these commands
were narrowed for.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, api_surface

pytestmark = [pytest.mark.contract, pytest.mark.p0]

DEV_TOKEN = REPO_ROOT / "bin" / "dev-token.sh"
API = REPO_ROOT / "bin" / "api.sh"
DOCS = REPO_ROOT / "bin" / "docs.sh"

SOURCES = {
    "dev-token": REPO_ROOT / "bin" / "dev-token.py",
    "api": REPO_ROOT / "bin" / "api.py",
    "docs": REPO_ROOT / "bin" / "docs.py",
}


def run(command: Path, *args: str, env: dict[str, str] | None = None, cwd: Path | None = None):
    return subprocess.run(
        [str(command), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=None if env is None else {**os.environ, **env},
    )


@pytest.fixture
def deployed(tmp_path: Path) -> Path:
    """A deployed document with both routes ready, and the roles v6 declares."""
    document: dict[str, Any] = {
        "schema_version": 6,
        "document_kind": "deployed",
        "project": {"key": "fixture-alpha-dev"},
        "routes": {
            "rest": {"status": "ready", "url": "https://alpha.example.test/api/rest"},
            "docs": {"status": "ready", "url": "https://alpha.example.test/docs"},
        },
        "database": {
            "roles": {
                "anon": "apg_a_anon",
                "authenticated": "apg_a_authenticated",
                "api_documentation": "apg_a_api_documentation",
            }
        },
        "jwt": {"issuer": "https://alpha.example.test/api/app/auth", "audience": "urn:a"},
        "secrets": {"generation_id": "20260811T120000Z"},
    }
    path = tmp_path / "outputs.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# D105: no command prints or accepts a credential
# ---------------------------------------------------------------------------


def test_no_command_offers_a_flag_that_prints_a_token() -> None:
    """The rule that is stricter than the specification it comes from.

    "Avoids printing passwords by default" implies a flag, and a flag that
    prints one is a credential in a scrollback buffer, a shell history, a screen
    share and a support ticket. Goes red if any of these grows `--print-token`,
    `--show`, `--echo` or an `--output` that a token could reach.
    """
    for command in (DEV_TOKEN, API, DOCS):
        help_text = run(command, "--help").stdout.lower()
        for flag in ("--print", "--show", "--echo", "--reveal", "--output"):
            assert flag not in help_text, f"{command.name} documents {flag}"


def test_dev_token_states_that_it_cannot_give_you_a_token() -> None:
    """A refusal an operator can act on, rather than a missing feature.

    Somebody reading `--help` because they wanted the token in their clipboard
    needs to find out that no such thing exists and why, not to conclude the
    flag is elsewhere.
    """
    # Whitespace-normalized, because the sentence wraps and a raw substring
    # scan would be asserting the line width rather than the wording.
    help_text = " ".join(run(DEV_TOKEN, "--help").stdout.lower().split())
    assert "there is no option that prints it" in help_text
    assert "reaches the command through its environment" in help_text


def test_dev_token_passes_the_token_through_execve_and_not_through_argv() -> None:
    """`env VAR=... command` would put the token in `env`'s argument vector.

    Asserted on the source because the difference is invisible from outside: both
    spellings run the child with the variable set, and only one of them shows the
    value in `ps` to every user on the host.
    """
    source = SOURCES["dev-token"].read_text(encoding="utf-8")
    assert "os.execvpe(" in source, "the token must cross into the child through execve"
    for spelling in ("shell=True", '"env"', "'env'"):
        assert spelling not in source, f"dev-token reaches for {spelling}"


def test_dev_token_never_writes_the_token_to_a_stream() -> None:
    """The value reaches exactly one place: the environment handed to `execve`.

    Parsed rather than scanned line by line. The line-based version of this test
    was written first and a mutation walked straight through it: a `print(...)`
    spread over four lines has the interpolation on a line that contains neither
    `print(` nor `file=`, so the scan looked at the wrong lines and stayed green
    while the command printed the credential.

    Goes red if the `token` local is ever an argument to `print` or to anything
    that writes, however the call is formatted.
    """
    import ast

    source = SOURCES["dev-token"].read_text(encoding="utf-8")
    tree = ast.parse(source)

    writers = {"print", "write", "warn", "log", "info", "debug", "error"}
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = getattr(function, "id", None) or getattr(function, "attr", None)
        if name not in writers:
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            rendered = ast.dump(argument)
            if "'token'" in rendered or "Name(id='token'" in rendered:
                offenders.append(ast.unparse(node)[:120])

    assert not offenders, f"dev-token writes the token to a stream: {offenders}"


def test_the_token_writing_scan_would_catch_a_real_one() -> None:
    """Guard the guard, because the previous version of the scan did not.

    The mutation that defeated the line-based test is the one asserted here: a
    multi-line `print` whose interpolation sits on its own line.
    """
    import ast

    planted = ast.parse(
        "def f(token):\n"
        "    print(\n"
        "        'minted ',\n"
        "        f'token={token}',\n"
        "        file=sys.stderr,\n"
        "    )\n"
    )
    found = False
    for node in ast.walk(planted):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
            for argument in [*node.args, *(k.value for k in node.keywords)]:
                if "Name(id='token'" in ast.dump(argument):
                    found = True
    assert found, "the scan above would not catch a token printed over several lines"


def test_the_commands_do_not_echo_a_planted_token(deployed: Path) -> None:
    planted = "APG_CANARY_TOKEN_9Zk4Vx"
    for command, args in (
        (API, ("--project-outputs", str(deployed), "list-notes")),
        (DOCS, ("--project-outputs", str(deployed), "url")),
    ):
        result = run(command, *args, env={"APG_API_TOKEN": planted, "APG_DOCS_TOKEN": planted})
        assert planted not in result.stdout + result.stderr, command.name


# ---------------------------------------------------------------------------
# Enumerated operations, and nothing else
# ---------------------------------------------------------------------------


def test_api_accepts_no_url_method_header_or_path(deployed: Path) -> None:
    """The narrowness is the feature.

    A broker that will issue any request against a project's API is a credential
    holder that will do anything the credential can -- which makes it, in an
    incident, indistinguishable from the thing being investigated.
    """
    for flag in ("--url", "--method", "--header", "--path", "--data", "--curl"):
        result = run(API, "--project-outputs", str(deployed), "list-notes", flag, "x")
        assert result.returncode == 2, f"{flag} was not refused"


def test_api_refuses_an_operation_it_does_not_name(deployed: Path) -> None:
    result = run(API, "--project-outputs", str(deployed), "delete-everything")
    assert result.returncode == 2
    assert "delete-everything" in result.stderr


def test_the_api_operations_reach_only_reviewed_objects(deployed: Path) -> None:
    """Every path this command can request names an object the contract declares.

    Goes red if an operation is added for something the reviewed surface does
    not name -- which is the same failure `API-CONTRACT-001` catches on the
    other side, arriving here first because a tool is easier to edit than a
    migration.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("apg_api", SOURCES["api"])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    surface = api_surface.load_surface()
    allowed = {"/"} | {f"/{name}" for name in surface["relations"]}
    allowed |= {f"/rpc/{name}" for name in surface["rpcs"]}

    for operation, (method, path) in module.OPERATIONS.items():
        assert path in allowed, f"{operation} requests {path}, which the contract does not name"
        assert method in {"GET", "POST"}, operation


def test_a_status_must_be_one_the_contract_declares(deployed: Path) -> None:
    """Read from the contract rather than typed into the command.

    A second copy of the enum is a second authority, and this one would be the
    permissive half: a status the tool accepts and the type does not is a 400
    from the database with the tool's name on it.
    """
    declared = api_surface.load_surface()["enums"]["task_status"]["values"]
    assert "archived" not in declared  # the control for the refusal below

    result = run(
        API, "--project-outputs", str(deployed), "update-task-status",
        "--task-id", "11111111-1111-4111-8111-111111111111",
        "--expected-status", "pending", "--new-status", "archived",
    )  # fmt: skip
    assert result.returncode == 2
    assert "archived" in result.stderr


def test_docs_offers_no_operation_that_authenticates(deployed: Path) -> None:
    """There is no `docs.sh open`, and that is the design.

    Logging in would mean reading the Basic Auth password and putting it in a
    URL, an argument or a browser's history -- all three worse than a prompt.
    The credential reaches the edge as a hash and the documentation container
    not at all.
    """
    help_text = run(DOCS, "--help").stdout
    assert "url" in help_text and "check" in help_text
    # Asserted as refusals rather than as absent words: the help text says "open
    # the URL and let the browser ask", which is the recommendation, and a
    # substring scan would flag the sentence that explains the design.
    for refused in ("login", "open", "authenticate", "fetch"):
        assert run(DOCS, "--project-outputs", str(deployed), refused).returncode == 2, refused
    for flag in ("--password", "--user", "--credential"):
        assert flag not in help_text, flag


def test_docs_url_reads_no_credential_and_needs_no_privilege(deployed: Path) -> None:
    result = run(DOCS, "--project-outputs", str(deployed), "url")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "https://alpha.example.test/docs"


# ---------------------------------------------------------------------------
# Nothing about the token is chosen by the caller
# ---------------------------------------------------------------------------


def test_dev_token_refuses_a_role_it_does_not_enumerate(deployed: Path) -> None:
    """A tool that will ask for any role probes for the boundary rather than
    staying inside it. `object_owner` is the one that matters: the authenticator
    is not a member, so the request would be a 403 somebody went looking for.
    """
    result = run(
        DEV_TOKEN, "--project-outputs", str(deployed), "--role", "object_owner", "--", "true"
    )
    assert result.returncode == 2
    assert "object_owner" in result.stderr or "role" in result.stderr.lower()


def test_dev_token_accepts_no_subject(deployed: Path) -> None:
    """Derived from the project, not supplied.

    A caller-supplied subject is a caller who can read any owner's rows through
    a row policy that is working exactly as designed.
    """
    assert "--subject" not in run(DEV_TOKEN, "--help").stdout
    result = run(
        DEV_TOKEN, "--project-outputs", str(deployed), "--role", "authenticated",
        "--subject", "22222222-2222-4222-8222-222222222222", "--", "true",
    )  # fmt: skip
    assert result.returncode == 2


def test_dev_token_bounds_the_lifetime(deployed: Path) -> None:
    for ttl in ("0", "-1", "86400"):
        result = run(
            DEV_TOKEN, "--project-outputs", str(deployed), "--role", "docs",
            "--ttl-seconds", ttl, "--", "true",
        )  # fmt: skip
        assert result.returncode in {2, 3}, ttl


def test_dev_token_requires_a_command(deployed: Path) -> None:
    """There is nowhere else for a token to go, so a missing command is a
    missing destination rather than a missing convenience."""
    result = run(DEV_TOKEN, "--project-outputs", str(deployed), "--role", "docs")
    assert result.returncode == 2
    assert "command" in result.stderr.lower()


def test_dev_token_mints_the_documentation_role_without_a_subject() -> None:
    """Migration 0009's rule, expressed at the minting end.

    The hook refuses a documentation token that carries a subject, with 401, so
    minting one would produce a credential rejected by design -- which reads as
    a broken tool rather than as the boundary working.
    """
    source = SOURCES["dev-token"].read_text(encoding="utf-8")
    assert 'None if arguments.role == "docs"' in source


def test_dev_token_refuses_without_root(deployed: Path) -> None:
    """The signing key is 0400 owned by root, which is what makes "no service
    holds it" a filesystem fact rather than a rule somebody keeps."""
    if os.geteuid() == 0:
        pytest.skip("running as root; the refusal cannot be observed")
    result = run(DEV_TOKEN, "--project-outputs", str(deployed), "--role", "docs", "--", "true")
    assert result.returncode == 3
    assert "root" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Deployed documents, not manifests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["api", "docs", "dev-token"])
def test_a_rendered_document_is_refused(command: str, tmp_path: Path) -> None:
    """A manifest describes what was asked for; a deployed document describes
    what happened. The two files share a basename, so this is the realistic
    mistake -- D132's rule, applied to the commands that read the routes."""
    rendered = tmp_path / "outputs.json"
    rendered.write_text(
        json.dumps(
            {
                "schema_version": 6,
                "document_kind": "rendered",
                "project": {"key": "fixture-alpha-dev"},
                "routes": {"rest": "https://a.test/api/rest", "docs": "https://a.test/docs"},
            }
        ),
        encoding="utf-8",
    )
    runners = {
        "api": (API, ("--project-outputs", str(rendered), "list-notes")),
        "docs": (DOCS, ("--project-outputs", str(rendered), "url")),
        "dev-token": (
            DEV_TOKEN,
            ("--project-outputs", str(rendered), "--role", "docs", "--", "true"),
        ),
    }
    binary, args = runners[command]
    result = run(binary, *args)
    assert result.returncode != 0
    # `dev-token` refuses on root before it reads the document, which is correct
    # ordering -- an unprivileged caller learns the cheapest reason first.
    assert result.returncode in {2, 3}, result.stderr


@pytest.mark.parametrize("command", [API, DOCS, DEV_TOKEN])
def test_a_missing_document_is_refused(command: Path) -> None:
    result = run(command, "--project-outputs", "/does/not/exist.json", "url")
    assert result.returncode == 2


@pytest.mark.parametrize("command", [API, DOCS, DEV_TOKEN])
def test_help_works_from_another_directory(command: Path, tmp_path: Path) -> None:
    assert run(command, "--help", cwd=tmp_path).returncode == 0


# ---------------------------------------------------------------------------
# ADR 0094 / D294: the `kid` names the key that signed the token
# ---------------------------------------------------------------------------


def _dev_token_module() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("apg_dev_token", SOURCES["dev-token"])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _header_of(token: str) -> dict[str, Any]:
    segment = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


@pytest.fixture
def two_keys(tmp_path: Path) -> tuple[Path, Path]:
    """Two RSA keys, because a project deployed through session 6 holds two.

    Generated rather than committed: a `kid` is a thumbprint of the key, so a
    fixture key would let this file assert a constant against itself.
    """
    generated = []
    for name in ("signing", "other"):
        path = tmp_path / f"{name}.pem"
        result = subprocess.run(
            ["openssl", "genrsa", "-out", str(path), "2048"],
            capture_output=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        generated.append(path)
    return generated[0], generated[1]


def test_the_minted_kid_is_the_thumbprint_of_the_key_that_signed_it(
    two_keys: tuple[Path, Path],
) -> None:
    """ADR 0094, and the isolating case is a document naming the OTHER key.

    This is the defect that left `routes.rest` `unavailable` on alpha-dev.
    `render-jwks.py` publishes the auth service's key first from Session 6,
    `observe_jwt` takes `active_kid = kids[0]`, and this command signs with the
    *bootstrap* key -- so the token was signed by one key and labelled with the
    other's identifier, and the locked PostgREST, which selects by `kid`, refused
    it with 401 `PGRST301`.

    A test that only compared the header's `kid` against the signing key's
    thumbprint would have passed under the old spelling too, whenever the two
    coincided -- which is every single-key deployment and was every offline
    fixture. So the document handed in here names the *other* key. That
    difference is the measurement: no reading of `active_kid` satisfies it.
    """
    dev_token = _dev_token_module()
    signing_key, other_key = two_keys

    signing_kid = dev_token.key_id(signing_key)
    other_kid = dev_token.key_id(other_key)
    assert signing_kid != other_kid, "two distinct keys produced one thumbprint"

    token = dev_token.mint(
        key_path=signing_key,
        role_name="apg_a_api_documentation",
        subject=None,
        ttl=300,
        document={
            "jwt": {
                "issuer": "https://alpha.example.test/api/app/auth",
                "audience": "urn:a",
                # What a session-6 deployed document actually says: the head of
                # the published set is the auth service's key, which this
                # command does not hold and cannot sign with.
                "active_kid": other_kid,
                "verification_kids": [other_kid, signing_kid],
            }
        },
    )

    header = _header_of(token)
    assert header["kid"] == signing_kid, (
        f"the token is labelled {header['kid']} and was signed by a key whose thumbprint is "
        f"{signing_kid}; a verifier that selects by kid answers 401 PGRST301 to that"
    )
    assert header["kid"] != other_kid, "the kid came from the document rather than from the key"


def test_the_minted_signature_verifies_under_the_key_its_kid_names(
    two_keys: tuple[Path, Path], tmp_path: Path
) -> None:
    """The property, asserted against what the command produced (D277).

    The test above compares two derived strings, which exercises this module's
    arithmetic as much as the command's. This one takes the token apart,
    resolves its `kid` to a key the way a verifier does, and asks openssl
    whether that key signed it -- with the other key as the control that the
    verification is capable of failing.
    """
    dev_token = _dev_token_module()
    signing_key, other_key = two_keys
    by_kid = {dev_token.key_id(signing_key): signing_key, dev_token.key_id(other_key): other_key}

    token = dev_token.mint(
        key_path=signing_key,
        role_name="apg_a_anon",
        subject=None,
        ttl=300,
        document={"jwt": {"active_kid": dev_token.key_id(other_key)}},
    )
    header_segment, claims_segment, signature_segment = token.split(".")
    signing_input = f"{header_segment}.{claims_segment}".encode("ascii")
    signature = base64.urlsafe_b64decode(signature_segment + "=" * (-len(signature_segment) % 4))

    def verifies(key: Path) -> bool:
        public = tmp_path / f"{key.stem}.pub"
        extracted = subprocess.run(
            ["openssl", "rsa", "-in", str(key), "-pubout", "-out", str(public)],
            capture_output=True, check=False, timeout=60,
        )  # fmt: skip
        assert extracted.returncode == 0, extracted.stderr
        signature_file = tmp_path / f"{key.stem}.sig"
        signature_file.write_bytes(signature)
        checked = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(public),
             "-signature", str(signature_file)],
            input=signing_input, capture_output=True, check=False, timeout=60,
        )  # fmt: skip
        return checked.returncode == 0

    named = by_kid[_header_of(token)["kid"]]
    assert verifies(named), (
        "the token names a kid whose key did not sign it -- which is what a verifier answers 401 to"
    )
    unnamed = other_key if named == signing_key else signing_key
    assert not verifies(unnamed), "openssl verified a signature made by a different key"


@pytest.mark.parametrize("role", ["anon", "authenticated", "api_documentation"])
def test_every_role_carries_a_kid(role: str, two_keys: tuple[Path, Path]) -> None:
    """A `kid` is never omitted, and the reason is outside PostgREST.

    Measured: PostgREST accepts a token carrying no `kid` at all -- it tries
    every published key -- so omitting the member would have cured the 401 too.
    The auth service's own verifier does not: `PERMITTED_HEADER_MEMBERS` and the
    loop below it in `services/auth-api/app/tokens.py` require `alg`, `kid` and
    `typ`, so a token minted without one is refused by the other verifier in the
    same system (ADR 0094).
    """
    dev_token = _dev_token_module()
    signing_key, _ = two_keys
    token = dev_token.mint(
        key_path=signing_key,
        role_name=f"apg_a_{role}",
        subject=None,
        ttl=300,
        document={"jwt": {}},
    )
    header = _header_of(token)
    assert header["kid"] == dev_token.key_id(signing_key)
    assert set(header) == {"alg", "kid", "typ"}, (
        f"the auth service refuses an unapproved header member: {sorted(header)}"
    )

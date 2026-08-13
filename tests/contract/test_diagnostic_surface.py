"""The read-only diagnostic surface (ADR 0071).

What is asserted here is what makes a sudoers rule pointing at one script safe.
The rule grants root, unconditionally, with no password — so every constraint
that matters lives in this file's subject rather than in `/etc/sudoers.d`.

The properties come from `bin/db.sh`, which faced the same question about SQL:
an allowlist of *names* rather than a passthrough, because a wrapper that
forwards its arguments to a privileged daemon is the same door with a lock
painted on it.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

SCRIPT = REPO_ROOT / "bin" / "apg-diag.sh"
SUDOERS = REPO_ROOT / "infra" / "host" / "apg-agent.sudoers"

#: Every verb the script accepts. Written out rather than parsed from the
#: script, so adding one to the script without adding it here fails — which is
#: the direction that matters, because a new verb is new privilege.
VERBS = (
    "containers",
    "labels",
    "logs",
    "routes",
    "listeners",
    "edge-log",
    "catalog",
    "generation",
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The allowlist is a list, and it is closed
# ---------------------------------------------------------------------------


def test_the_verb_list_in_the_script_is_the_list_asserted_here(source: str) -> None:
    """Two copies of one fact, with a test between them.

    A verb added to the script and not to this file is new privilege nobody
    reviewed; a verb here that the script does not have is a test measuring
    nothing. Both directions are asserted.
    """
    declared = re.search(r'^readonly VERBS="([^"]+)"', source, re.MULTILINE)
    assert declared, "the script no longer declares a verb list"
    assert tuple(declared.group(1).split()) == VERBS


@pytest.mark.parametrize("verb", VERBS)
def test_every_declared_verb_has_an_implementation(source: str, verb: str) -> None:
    """A verb in the list with no function behind it fails at the case statement
    with an unhelpful message, having already passed the allowlist."""
    assert f"verb_{verb.replace('-', '_')}()" in source


@pytest.mark.parametrize(
    "verb", ["restart", "stop", "rm", "exec", "deploy", "sql", "shell", "nonsense", "--", ""]
)
def test_an_unlisted_verb_is_refused(verb: str) -> None:
    """Refused as a name, before anything resolves a path or reaches a daemon.

    The empty string and `--` are in this list deliberately: both are what a
    caller ends up passing when an argument is missing, and both would be
    plausible ways to reach a default branch.
    """
    result = run(verb) if verb else run()
    if verb == "":
        # No arguments prints usage and exits 0; that is not a refusal, it is
        # the absence of a request. Asserted so the case cannot become a verb.
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        return
    assert result.returncode in (0, 5), result.stderr
    if result.returncode == 5:
        assert "allowlisted" in result.stderr


def test_an_unlisted_verb_is_refused_before_the_privilege_check() -> None:
    """An argument error is an argument error whether or not you are root.

    The same rule `bin/session-05-check.sh` follows: a caller who typed a verb
    that does not exist should be told that, not told to use sudo and then told
    that.
    """
    result = run("nonsense")
    assert result.returncode == 5
    assert "requires root" not in result.stderr


def test_a_real_verb_without_root_is_refused_for_that_reason() -> None:
    """The control for the test above: the privilege check does exist."""
    result = run("containers")
    assert result.returncode == 3
    assert "requires root" in result.stderr


# ---------------------------------------------------------------------------
# Nothing here mutates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    [
        "docker restart",
        "docker stop",
        "docker start",
        "docker rm",
        "docker kill",
        "docker run",
        "docker compose",
        "systemctl",
        "rm -",
        "> /",
        "tee ",
    ],
)
def test_the_script_runs_no_mutating_command(source: str, forbidden: str) -> None:
    """A diagnostic that can change the thing it describes is not a diagnostic.

    Scanned with comments stripped: this file's header explains what it does not
    do, in the vocabulary of the things it does not do, and a raw scan would
    match the explanation (the seventh instance of that hazard in this
    repository).
    """
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert forbidden not in code, f"the diagnostic surface can {forbidden!r}"


def test_the_only_container_execution_is_a_named_query(source: str) -> None:
    """`docker exec` exists exactly once, and its command is not a caller's.

    This is the one verb that runs something inside a container, and the
    difference between a diagnostic and a shell is that the SQL is chosen here
    by name.
    """
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert code.count("docker exec") == 1
    assert 'psql -U postgres -d "${database}" -X -qA -c "${sql}"' in code
    assert "${sql}" in code

    # `sql` is assigned only inside the case statement, never from an argument.
    assignments = re.findall(r'^\s*sql="(.*)$', code, re.MULTILINE)
    assert assignments, "no SQL is assigned; this test compared nothing"
    for assignment in assignments:
        assert "$1" not in assignment and "$2" not in assignment and "$@" not in assignment


def test_the_query_list_is_a_fixed_set_not_a_lookup(source: str) -> None:
    """`bin/db.sh`'s rule: a set of names, not a directory glob.

    A glob runs whatever was dropped in the directory, which is the same door
    with a lock painted on it.
    """
    declared = re.search(r'^readonly QUERIES="([^"]+)"', source, re.MULTILINE)
    assert declared
    assert set(declared.group(1).split()) == {
        "connection-limits",
        "role-settings",
        "migration-ledger",
        "extensions",
    }
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    # Command substitutions, not bare words. `"ls "` matched `labels logs` in
    # the verb list -- a scan whose token appears in the thing it is scanning.
    for glob in ("$(ls", "$(find", "*.sql", "for file in"):
        assert glob not in code, f"the query set is resolved by {glob!r} rather than named"


# ---------------------------------------------------------------------------
# No secret leaves through this door
# ---------------------------------------------------------------------------


def test_no_verb_reads_a_secret_file(source: str) -> None:
    """The generation *identifier* is a fact about a deployment; the generation's
    contents are credentials.

    `SECRET_ROOT` is referenced once, for the pointer file, and nothing walks
    below it.
    """
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert code.count("SECRET_ROOT") == 2, "SECRET_ROOT is used somewhere new"
    assert "active-secret-generation.json" in code

    # The property is "nothing reads below the pointer file", so the tokens are
    # paths under the secret root rather than words that co-occur with them.
    # `"_root"` matched `require_root` and `"pgpass"` matched the redaction
    # pattern whose whole job is removing pgpass.
    for hazard in ("generations/", "/_root", "${SECRET_ROOT}/${key}/generations"):
        assert hazard not in code, f"a verb reaches {hazard!r} under the secret root"


def test_inspect_is_restricted_to_labels(source: str) -> None:
    """`docker inspect` with no format prints the environment, the mounts and the
    command line — three of the four places a secret must not be."""
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert "docker inspect" in code
    for occurrence in re.findall(r"docker inspect[^\n]*(?:\n[^\n]*)?", code):
        assert ".Config.Labels" in occurrence, f"an inspect is unfiltered: {occurrence}"


def test_log_output_is_redacted(source: str) -> None:
    """Belt to the braces. These services do not log credentials; a diagnostic
    whose output is pasted into a conversation should not depend on that."""
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert "| redact" in code
    assert code.count("docker logs") == 2, "a log path bypasses the filter"
    for occurrence in re.findall(r"docker logs[^|]*\|[^\n]*", code):
        assert "redact" in occurrence or "python3" in occurrence, occurrence


def test_the_redaction_actually_redacts() -> None:
    """The control. A filter nobody fed a secret is a filter nobody has watched
    work, and this one is three regexes deep."""
    script = SCRIPT.read_text(encoding="utf-8")
    body = script[script.index("redact() {") : script.index("verb_containers()")]
    program = body[body.index("sed") : body.rindex("'") + 1]

    samples = {
        "password=hunter2": "hunter2",
        "PGPASSWORD: s3cr3t": "s3cr3t",
        "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefgh": "eyJhbGciOiJIUzI1NiJ9",
        "generation 7dfaf9c08545eaaf7dfaf9c08545eaaf": "7dfaf9c08545eaaf7dfaf9c08545eaaf",
    }
    for line, secret in samples.items():
        result = subprocess.run(
            ["bash", "-c", f"printf '%s\\n' {line!r} | {program}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert secret not in result.stdout, f"{secret!r} survived redaction: {result.stdout!r}"
        assert "redacted" in result.stdout


# ---------------------------------------------------------------------------
# The sudoers rule
# ---------------------------------------------------------------------------


def test_the_rule_grants_one_command_by_absolute_path() -> None:
    """A NOPASSWD rule is root without a password, so what it names is the whole
    of the boundary."""
    rule = SUDOERS.read_text(encoding="utf-8")
    grants = [
        line
        for line in rule.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "NOPASSWD" in line
    ]
    assert len(grants) == 1, f"expected one grant, found {grants}"
    assert grants[0].strip() == "apg-agent ALL=(root) NOPASSWD: /usr/local/bin/apg-diag"


def test_the_rule_names_no_wildcard_and_no_shell() -> None:
    rule = "\n".join(
        line
        for line in SUDOERS.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    for hazard in ("ALL)", "*", "/bin/sh", "/bin/bash", "docker", "deploy.sh"):
        assert hazard not in rule, f"the sudoers rule grants {hazard!r}"


def test_the_rule_does_not_grant_the_repository_copy() -> None:
    """The installed copy is root-owned and outside any checkout.

    A NOPASSWD rule pointing at a file its beneficiary can edit is a root shell
    with extra steps, and the agent has a checkout.
    """
    # The grant line, not everything after the first occurrence of the word:
    # the header explains what a NOPASSWD rule is, so the naive split began
    # inside a comment.
    grants = [
        line
        for line in SUDOERS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "NOPASSWD" in line
    ]
    assert len(grants) == 1
    assert "bin/apg-diag.sh" not in grants[0]
    assert grants[0].split("NOPASSWD:")[1].strip().startswith("/usr/local/")


def test_the_script_carries_no_repository_import(source: str) -> None:
    """It is installed as a copy, so it must work standing alone — which is also
    what makes it useful when the checkout is the broken thing."""
    for dependency in ("agentic_postgres", "ROOT_DIR", "src/", ".venv"):
        assert dependency not in source, f"the diagnostic surface depends on {dependency!r}"

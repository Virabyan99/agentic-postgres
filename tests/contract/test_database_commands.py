"""Command contracts for the two Session 3 database commands.

Offline. Neither command is exercised against a cluster here -- they refuse
before reaching one, which is the half that can be proved in a checkout and the
half an operator meets first.

The ordering assertion is the one worth stating plainly: **an argument error
must exit 2 before the privilege check exits 3.** An operator who mistyped a
flag should learn that without first being told to obtain root and try again,
and the natural way to write these scripts -- gate on root, then parse -- gets
it backwards.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

BOOTSTRAP = REPO_ROOT / "bin" / "postgres-bootstrap.sh"
DB = REPO_ROOT / "bin" / "db.sh"
MIGRATE = REPO_ROOT / "bin" / "migrate.sh"
COMMANDS = (BOOTSTRAP, DB, MIGRATE)

MANIFEST = ("--project", "project.example.yaml")


def run(command: Path, *args: str, cwd: Path | None = None):
    return subprocess.run(
        [str(command), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd or REPO_ROOT,
        timeout=120,
    )


@pytest.fixture
def root_is_irrelevant() -> bool:
    """Opt out of the module's root guard, for a test that only reads source.

    The guard below is right about the tests it was written for and wrong about
    these: reading a file cannot exercise a different branch under root, so
    skipping them there reports "could not look" about something that was
    perfectly visible.

    It mattered because three of them are ``DBX-PG-003``'s offline proofs, and
    the Session 3 host gate necessarily runs as root. A skip is not a pass, so
    ``database_isolation`` came out ``failed`` on a host where all nine of its
    live proofs had just passed — a claim that could not be proved in the only
    mode that measures it (D79).

    An opt-out rather than a narrowing: leaving the default as "skip under root"
    means a privilege test that nobody remembered to classify keeps today's safe
    behaviour, and the tests that opt out say so in their own signature.
    """
    return True


@pytest.fixture(autouse=True)
def _refuse_to_run_as_root(request: pytest.FixtureRequest) -> None:
    """These assertions are about what happens *without* root.

    Run as root they would exercise the opposite branch and pass for the wrong
    reason, so the suite says it could not look rather than reporting a verdict
    (ADR 0018).
    """
    if "root_is_irrelevant" in request.fixturenames:
        return
    if os.geteuid() == 0:
        pytest.skip("this suite asserts the unprivileged refusals")


def test_the_root_opt_out_is_only_used_by_tests_that_read_source(root_is_irrelevant) -> None:
    """Guard the opt-out. It is one word away from disabling the guard.

    It opts out itself, and has to: a guard that skips in the environment the
    thing it guards was introduced for would be watching nothing there.

    A test that invokes a command and opts out would run its privileged branch
    under root and pass for the wrong reason -- which is exactly what the guard
    exists to prevent, reintroduced by the mechanism that narrows it. Read with
    ``ast`` rather than by regex: a call inside a comprehension or a ``with``
    body is still a call.
    """
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        argument_names = {argument.arg for argument in node.args.args}
        if "root_is_irrelevant" not in argument_names:
            continue
        called = {
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        assert "run" not in called, (
            f"{node.name} opts out of the root guard and invokes a command. "
            "Under root it would exercise the privileged branch and pass for "
            "the wrong reason."
        )


# ---------------------------------------------------------------------------
# Self-documentation and input validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_help_exits_zero_and_describes_itself(command: Path) -> None:
    result = run(command, "--help")
    assert result.returncode == 0, result.stderr
    assert "Usage:" in result.stdout
    assert "--project" in result.stdout


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_no_arguments_exits_two(command: Path) -> None:
    """Not 10. Neither command is a stub, and `10` means "not this session"."""
    assert run(command).returncode == 2


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
@pytest.mark.parametrize(
    "args",
    [
        pytest.param(("--bogus",), id="unknown-flag"),
        pytest.param(("--project",), id="flag-without-value"),
        pytest.param(("--project", "does-not-exist.yaml"), id="missing-manifest"),
    ],
)
def test_invalid_input_exits_two(command: Path, args: tuple[str, ...]) -> None:
    assert run(command, *args).returncode == 2


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_an_argument_error_is_reported_before_the_privilege_check(command: Path) -> None:
    """The ordering this module exists for.

    `--apply` and `sql` both need root. With a bad flag beside them the answer
    must still be 2, not 3: the flag is wrong whether or not the operator is
    root, and telling them to sudo first sends them to get privilege for a
    command that was never going to run.
    """
    privileged = {
        BOOTSTRAP: ("--apply",),
        DB: ("sql", "bootstrap.sql"),
        MIGRATE: ("up",),
    }[command]
    result = run(command, "--bogus", *privileged)
    assert result.returncode == 2, f"got {result.returncode}: {result.stderr}"


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_a_privileged_invocation_without_root_exits_three(command: Path) -> None:
    privileged = {BOOTSTRAP: ("--apply",), DB: ("status",), MIGRATE: ("up",)}[command]
    result = run(command, *MANIFEST, *privileged)
    assert result.returncode == 3, f"got {result.returncode}: {result.stderr}"
    assert "root" in result.stderr


# ---------------------------------------------------------------------------
# bin/migrate.sh left FUTURE_STUBS (D48, ADR 0017)
# ---------------------------------------------------------------------------


def test_migrate_is_no_longer_a_stub() -> None:
    """ADR 0017's rule, applied a second time.

    A stub may leave ``FUTURE_STUBS`` only in the session that implements it,
    only together with real command-contract tests, and only in a commit that
    leaves every other stub's assertion untouched. The replacement assertions
    must be *stricter* than the one removed -- ``test_future_stub_exits_ten``
    asserted one exit code for a bare invocation; what replaces it is every
    test in this module that parametrizes over MIGRATE, plus the subcommand
    surface below.
    """
    from tests.contract.test_cli_contract import FUTURE_STUBS

    assert "bin/migrate.sh" not in FUTURE_STUBS
    assert "bin/connect.sh" in FUTURE_STUBS, "another stub's assertion was removed"
    assert "bin/restore-test.sh" in FUTURE_STUBS, "another stub's assertion was removed"

    result = run(MIGRATE)
    assert result.returncode == 2, "a bare invocation is a missing subcommand, not 'unavailable'"


def test_migrate_offers_no_down() -> None:
    """Released platform migrations are fix-forward only (ADR 0028).

    Refused by name rather than merely absent from the parser, so an operator
    reaching for `down` is told why instead of being told the flag is unknown.
    """
    for word in ("down", "rollback"):
        result = run(MIGRATE, *MANIFEST, word)
        assert result.returncode == 2
        assert "fix-forward" in result.stderr, result.stderr


def test_migrate_lock_commands_take_no_project() -> None:
    """The lock covers the committed set, not one project (ADR 0028).

    Requiring `--project` here would invite an operator to believe the lock is
    per project, which is precisely what it is not.
    """
    result = run(MIGRATE, "verify-lock")
    assert result.returncode == 0, result.stderr


def test_verify_lock_agrees_with_the_committed_tree() -> None:
    result = run(MIGRATE, "verify-lock")
    assert result.returncode == 0
    assert "agrees" in result.stdout


def test_freeze_lock_is_the_only_writer() -> None:
    """The gate verifies the lock and never creates it."""
    source = MIGRATE.read_text(encoding="utf-8")
    assert "freeze-lock" in source
    helper = (REPO_ROOT / "bin" / "migrate.py").read_text(encoding="utf-8")
    writes = [line for line in helper.splitlines() if "LOCK_PATH.write_text" in line]
    assert len(writes) == 1, f"the lock is written in {len(writes)} places"


def test_render_needs_no_root() -> None:
    """A read that required privilege is one an operator runs as root by habit.

    `status` was in this test until Run 7 and passed for a reason that has
    stopped being true: it printed the rendered set and connected to nothing.
    It now runs dbmate against the ledger, which is a container, which needs
    root. The distinction this test keeps is between what reports on this
    release -- `render`, `verify-lock` -- and what reports on a cluster.
    """
    result = run(MIGRATE, *MANIFEST, "render")
    assert result.returncode == 0, result.stderr


def test_the_subcommands_that_reach_a_cluster_refuse_without_root() -> None:
    """Both of them. `status` reading the ledger is still starting a container."""
    for subcommand in ("status", "up"):
        result = run(MIGRATE, *MANIFEST, subcommand)
        assert result.returncode == 3, f"{subcommand}: {result.stdout}{result.stderr}"
        assert "root" in result.stderr


def test_render_reports_a_digest_per_migration() -> None:
    """One line per migration, counted against the manifest rather than a literal.

    The name says "per migration", so the assertion should too. It said `== 5`
    until a sixth migration existed.
    """
    import json

    manifest = json.loads(
        (REPO_ROOT / "migrations" / "manifest.json").read_text(encoding="utf-8")
    )
    result = run(MIGRATE, *MANIFEST, "render")
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(manifest["migrations"]), result.stdout


def test_two_subcommands_at_once_are_refused_by_migrate() -> None:
    result = run(MIGRATE, *MANIFEST, "status", "render")
    assert result.returncode == 2
    assert "one subcommand" in result.stderr


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_it_works_from_any_directory(command: Path, tmp_path: Path) -> None:
    """Runbook §8.5. Both resolve the repository from their own location."""
    assert run(command, "--help", cwd=tmp_path).returncode == 0


# ---------------------------------------------------------------------------
# bootstrap: --check is the default and changes nothing
# ---------------------------------------------------------------------------


def test_check_is_the_default_mode() -> None:
    """Following bin/provision-host.sh. A default that changes things is one
    an operator triggers while trying to find out what it would do."""
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'MODE="check"' in source
    assert source.index('MODE="check"') < source.index("parse_args")


def test_bootstrap_names_no_flag_that_adopts_a_volume(root_is_irrelevant) -> None:
    """ADR 0030: a mismatch is refused, and there is no override.

    Asserted on the operator surface rather than on the comparison logic,
    because the way this rule dies is a flag added for one incident.
    """
    source = BOOTSTRAP.read_text(encoding="utf-8")
    for forbidden in ("--force", "--adopt", "--take-ownership", "--ignore-identity"):
        assert forbidden not in source, f"{forbidden} would let a volume be adopted"


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_neither_command_can_remove_a_volume(command: Path) -> None:
    """Volume removal exists in exactly one place, and it is not these."""
    source = command.read_text(encoding="utf-8")
    for forbidden in ("docker volume rm", "volume prune", "down -v", "--volumes"):
        assert forbidden not in source, f"{command.name} contains {forbidden!r}"


def test_the_exit_code_for_a_foreign_volume_is_eleven(root_is_irrelevant) -> None:
    """ADR 0031. Documented on the command that raises it, and nowhere else
    reused: `11` answers exactly one question."""
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "11" in source
    helper = (REPO_ROOT / "bin" / "postgres-bootstrap.py").read_text(encoding="utf-8")
    assert "EXIT_IDENTITY_MISMATCH = 11" in helper
    assert helper.count("EXIT_IDENTITY_MISMATCH") >= 2


def test_identity_comparison_uses_only_immutable_fields(root_is_irrelevant) -> None:
    """ADR 0030: not the source commit, manifest checksum, or template version.

    Those change on every legitimate redeploy, and a check that fires on a
    valid volume is one operators learn to override.
    """
    helper = (REPO_ROOT / "bin" / "postgres-bootstrap.py").read_text(encoding="utf-8")
    assert 'IDENTITY_FIELDS = ("project_key", "database_name", "compose_project_name",' in helper
    for volatile in ("source_commit", "manifest_sha256", "template_version"):
        assert f'"{volatile}"' not in helper.split("IDENTITY_FIELDS", 1)[1].split(")", 1)[0]


# ---------------------------------------------------------------------------
# db.sh: the narrow SQL door
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "anything.sql",
        "../../../etc/passwd",
        "/etc/passwd",
        "bootstrap.sql.bak",
        "",
    ],
)
def test_sql_refuses_a_name_outside_the_allowlist(name: str) -> None:
    """Checked as an exact name before anything touches the filesystem.

    A traversal string is refused as "not allowlisted" rather than resolved
    and then rejected, so there is no window in which it is a path.
    """
    result = run(DB, *MANIFEST, "sql", name)
    assert result.returncode in (2, 5), f"got {result.returncode}: {result.stderr}"
    assert "allowlist" in result.stderr.lower() or "requires" in result.stderr.lower()


def test_sql_requires_a_name() -> None:
    result = run(DB, *MANIFEST, "sql")
    assert result.returncode == 2
    assert "requires" in result.stderr


def test_the_allowlist_is_a_fixed_set_not_a_glob() -> None:
    """A directory glob executes whatever was dropped in the directory."""
    source = DB.read_text(encoding="utf-8")
    assert "readonly ALLOWED_SQL=" in source
    for globbing in ("*.sql", "$(ls", "find "):
        assert globbing not in source, f"db.sh resolves artifacts with {globbing!r}"


def test_no_subcommand_takes_sql_from_an_argument_or_stdin() -> None:
    """`sql NAME`, never `sql "SELECT ..."`. The door is a name, not a payload."""
    source = DB.read_text(encoding="utf-8")
    assert "--command" not in source
    assert "read -r" not in source


def test_two_subcommands_at_once_are_refused() -> None:
    result = run(DB, *MANIFEST, "status", "identity")
    assert result.returncode == 2
    assert "one subcommand" in result.stderr


def test_the_verifier_refuses_an_artifact_the_manifest_never_named(tmp_path: Path) -> None:
    """Unnamed is not "unverified" -- it means the renderer did not produce it."""
    import json

    artifact = tmp_path / "bootstrap.sql"
    artifact.write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "rendered-manifest.json").write_text(
        json.dumps({"artifacts": {}}), encoding="utf-8"
    )
    result = subprocess.run(
        [str(REPO_ROOT / "bin" / "db-verify.py"), "--artifact", str(artifact)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "not named by the rendered manifest" in result.stderr


def test_the_verifier_refuses_an_edited_artifact(tmp_path: Path) -> None:
    import json
    from hashlib import sha256

    artifact = tmp_path / "bootstrap.sql"
    artifact.write_text("SELECT 1;\n", encoding="utf-8")
    recorded = sha256(artifact.read_bytes()).hexdigest()
    (tmp_path / "rendered-manifest.json").write_text(
        json.dumps({"artifacts": {"bootstrap.sql": recorded}}), encoding="utf-8"
    )
    artifact.write_text("DROP SCHEMA app CASCADE;\n", encoding="utf-8")

    result = subprocess.run(
        [str(REPO_ROOT / "bin" / "db-verify.py"), "--artifact", str(artifact)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "does not match the manifest" in result.stderr


def test_the_verifier_accepts_a_matching_artifact(tmp_path: Path) -> None:
    """The positive case, so the refusals above are not passing vacuously."""
    import json
    from hashlib import sha256

    artifact = tmp_path / "bootstrap.sql"
    artifact.write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "rendered-manifest.json").write_text(
        json.dumps({"artifacts": {"bootstrap.sql": sha256(artifact.read_bytes()).hexdigest()}}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(REPO_ROOT / "bin" / "db-verify.py"), "--artifact", str(artifact)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Both handle credentials
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_tracing_is_disabled_as_the_first_executable_line(command: Path) -> None:
    """`set -x` would print every expanded argument, including a credential."""
    lines = [
        line.strip()
        for line in command.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert lines[0] == "set +x", f"{command.name} starts with {lines[0]!r}"


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_docker_exec_forwards_stdin(command: Path) -> None:
    """`docker exec` without `-i` discards stdin and exits 0 having run nothing.

    A silent success indistinguishable from a real one, which is exactly the
    failure this project keeps producing. Every exec here passes `-i`.
    """
    source = command.read_text(encoding="utf-8")
    for line in source.splitlines():
        if "docker exec" in line and not line.strip().startswith("#"):
            assert "docker exec -i" in line, f"{command.name}: {line.strip()}"

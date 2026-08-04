"""What a script that runs as root, or touches a credential, may not do.

Session 2 is the first session with scripts that run as root and handle real
secrets. The rules they follow are not visible in any one file, so they are
asserted here across all of them.

The static scans are deliberately narrow. A scan broad enough to be certain
would flag every legitimate use and be turned off within a month; these look for
the specific constructions that leak, and each one has a guard test proving it
would catch a real instance.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

#: Commands that run as root, or that read a credential, or both.
ROOT_COMMANDS = (
    "bin/bootstrap-providers.sh",
    "bin/docker-firewall.sh",
    "bin/edge.sh",
    "bin/edge-network.sh",
    "bin/materialize-secrets.sh",
    "bin/project-runtime.sh",
    "bin/provision-host.sh",
    "bin/session-02-check.sh",
)

#: Commands that refuse to act without root, and the flag that triggers it.
PRIVILEGED_INVOCATIONS = (
    ("bin/provision-host.sh", ("--host", "host.example.yaml", "--apply")),
    ("bin/provision-host.sh", ("--host", "host.example.yaml", "--check")),
    ("bin/edge.sh", ("--host", "host.example.yaml", "up")),
    ("bin/edge.sh", ("--host", "host.example.yaml", "down")),
    ("bin/docker-firewall.sh", ("reconcile",)),
    ("bin/project-runtime.sh", ("--host", "host.example.yaml", "--project-key", "alpha-dev", "up")),
)

#: Flags that would put a secret value into argv, and therefore into `ps`.
SECRET_ARGUMENT = re.compile(
    r"--(client-secret|password|token|api-key|access-key|private-key|secret-value)(?![a-z-])"
)

#: Constructions that execute or expand file contents.
#:
#: Anchored at a command position rather than matched anywhere in the line. A
#: bare ``source `` substring also matches a local variable named ``source``,
#: which is a false positive that would train someone to add an exemption
#: instead of looking.
DANGEROUS_SHELL = (
    (r"(^|;|\||&&)\s*eval\b", "eval executes whatever it was handed"),
    (r"(^|;|\||&&)\s*source\s", "sourcing a file executes it"),
    (r"(^|;|\||&&)\s*\.\s+/(etc|var|run)/", "sourcing a system or state file executes it"),
    (r"(^|;|\||&&)\s*set\s+-x\b", "tracing prints every expanded argument"),
    (r"\bprintenv\b", "dumps the environment"),
    (r"\bdeclare\s+-p\b", "dumps variables"),
)


def source_of(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def code_of(relative: str) -> str:
    """Source with comments and the usage heredoc removed.

    Every scan below is about what a script *does*. Prose explaining why the
    script does not use ``eval`` would otherwise fail the test asserting it does
    not use ``eval``, and the usage text legitimately names commands the script
    does not run -- ``bin/session-02-check.sh --help`` tells the operator to use
    ``./deploy.sh`` instead, which must not read as the gate deploying.
    """
    lines: list[str] = []
    in_usage = False
    for line in source_of(relative).splitlines():
        if "<<'USAGE'" in line:
            in_usage = True
            continue
        if in_usage:
            if line.strip() == "USAGE":
                in_usage = False
            continue
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_the_usage_stripper_actually_strips() -> None:
    """Guard the guard: if this stopped working, several scans below would be
    reading documentation instead of code and would pass on anything."""
    code = code_of("bin/session-02-check.sh")
    assert "Usage: bin/session-02-check.sh" not in code
    assert 'MODE=""' in code, "the stripper removed real code"


def run(relative: str, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [str(REPO_ROOT / relative), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env=None if env is None else {**os.environ, **env},
    )


# ---------------------------------------------------------------------------
# Privilege
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("relative", "args"), PRIVILEGED_INVOCATIONS, ids=lambda v: str(v))
def test_root_commands_refuse_without_root(relative: str, args: tuple[str, ...]) -> None:
    """Exit 3, and before anything is changed.

    A command that got partway and then discovered it needed root would leave
    the host in a state neither the operator nor the next run expects.
    """
    if os.geteuid() == 0:
        pytest.skip("running as root; the refusal cannot be observed")

    result = run(relative, *args)
    assert result.returncode == 3, (
        f"{relative} {' '.join(args)} exited {result.returncode}, expected 3\n{result.stderr}"
    )
    assert "root" in result.stderr.lower()


@pytest.mark.parametrize("relative", ROOT_COMMANDS)
def test_every_root_command_checks_the_effective_uid(relative: str) -> None:
    """Grepped as well as exercised: a command whose only root-requiring path is
    not covered by the table above would otherwise pass silently."""
    assert "id -u" in code_of(relative), f"{relative} never checks whether it is root"


# ---------------------------------------------------------------------------
# Destructive actions need the name said back
# ---------------------------------------------------------------------------


def test_destroy_requires_the_project_key_said_back() -> None:
    result = run(
        "bin/bootstrap-providers.sh",
        "--host",
        "host.example.yaml",
        "--project",
        "project.example.yaml",
        "--destroy",
    )
    # Non-root refusal (3) is also acceptable and arrives first; what must not
    # happen is a destroy that proceeds.
    assert result.returncode in {2, 3}, result.stderr
    assert result.returncode != 0


def test_acme_promotion_requires_the_host_id_said_back() -> None:
    result = run("bin/edge.sh", "--host", "host.example.yaml", "promote-acme", "--to", "production")
    assert result.returncode in {2, 3}, result.stderr
    assert "confirm" in result.stderr.lower() or "root" in result.stderr.lower()


def test_there_is_no_force_flag_for_a_destructive_action() -> None:
    """A ``--force`` is typed reflexively; a name that must match is not."""
    for relative in ROOT_COMMANDS:
        assert "--force)" not in code_of(relative), f"{relative} accepts a --force flag"


def test_acme_promotion_has_no_path_back_to_staging() -> None:
    """Deleting production ACME state and re-requesting is what exhausts the
    weekly rate limit, so there is deliberately no command that does it."""
    code = code_of("bin/edge.sh")
    assert "--to production" in source_of("bin/edge.sh")
    assert '"${PROMOTE_TO}" = "production"' in code


# ---------------------------------------------------------------------------
# Secrets never reach argv, the environment, or a trace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", ROOT_COMMANDS)
def test_no_script_documents_a_secret_argument(relative: str) -> None:
    help_text = run(relative, "--help").stdout.lower()
    match = SECRET_ARGUMENT.search(help_text)
    assert match is None, f"{relative} documents a secret argument: {match.group(0)}"


@pytest.mark.parametrize("relative", ROOT_COMMANDS)
def test_no_script_passes_a_secret_in_arguments(relative: str) -> None:
    match = SECRET_ARGUMENT.search(code_of(relative))
    assert match is None, f"{relative} passes a secret in argv: {match.group(0)}"


def test_the_secret_argument_scan_would_catch_a_real_one() -> None:
    """Guard the guard, including the near-misses it must not flag."""
    for caught in ("--client-secret VALUE", "--password x", "--api-key k"):
        assert SECRET_ARGUMENT.search(caught), caught
    for allowed in (
        "--operator-credential-file FILE",
        "--secrets-namespace REF",
        "--sentinel-file FILE",
        "--client-secret-id ID",
    ):
        assert not SECRET_ARGUMENT.search(allowed), allowed


@pytest.mark.parametrize("relative", ROOT_COMMANDS)
def test_no_script_uses_a_construction_that_expands_file_contents(relative: str) -> None:
    code = code_of(relative)
    offenders = [
        f"{match.group(0).strip()!r} ({why})"
        for pattern, why in DANGEROUS_SHELL
        if (match := re.search(pattern, code, re.MULTILINE))
    ]
    assert not offenders, f"{relative} uses: {offenders}"


def test_the_dangerous_shell_scan_catches_real_uses_and_not_variable_names() -> None:
    """Guard the guard, in both directions.

    The false positive is the one that matters: a variable named ``source`` is
    not the ``source`` builtin, and a scan that cannot tell them apart teaches
    people to add exemptions rather than to look.
    """
    caught = {
        'eval "$(cmd)"': "eval",
        "  source /etc/thing": "source",
        ". /var/lib/agentic-postgres/state.env": "sourcing",
        "set -x": "tracing",
    }
    for line, expectation in caught.items():
        assert any(
            re.search(pattern, line, re.MULTILINE)
            for pattern, why in DANGEROUS_SHELL
            if expectation in why or expectation in pattern
        ), line

    for allowed in (
        "local origin name",
        "  local source name",
        'echo "resource"',
        "set -euo pipefail",
    ):
        assert not any(
            re.search(pattern, allowed, re.MULTILINE) for pattern, _ in DANGEROUS_SHELL
        ), allowed


def test_credential_handling_scripts_disable_tracing_explicitly() -> None:
    """``set +x`` at the top, not merely the absence of ``set -x``.

    A caller can export ``SHELLOPTS=xtrace``, and bash honours it. Without an
    explicit disable, every expanded argument in the script goes to stderr.
    """
    for relative in ("bin/materialize-secrets.sh", "bin/bootstrap-providers.sh"):
        assert "set +x" in code_of(relative), (
            f"{relative} handles credentials without disabling tracing; "
            "an inherited SHELLOPTS=xtrace would print every expanded argument"
        )


@pytest.mark.parametrize("relative", ["bin/materialize-secrets.sh", "bin/bootstrap-providers.sh"])
def test_tracing_cannot_be_inherited_into_a_credential_script(relative: str) -> None:
    """Exercised, not just grepped: run with xtrace forced on.

    The ``set +x`` line traces itself and nothing can prevent that, so the
    assertion is that it is the *only* traced line. Anything after it means the
    disable is not the first executable statement, and every argument the
    script expands from that point on is going to stderr.
    """
    result = run(relative, "--help", env={"SHELLOPTS": "xtrace"})
    traced = [line for line in result.stderr.splitlines() if line.startswith("+")]
    assert traced == ["+ set +x"], f"{relative} traced more than its own disable:\n" + "\n".join(
        traced[:10]
    )


def test_the_trace_check_would_notice_a_missing_disable(tmp_path: Path) -> None:
    """Guard the guard: prove an unprotected script does trace under SHELLOPTS."""
    script = tmp_path / "unprotected.sh"
    script.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nsecret=value\nprintf 'done\\n'\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = subprocess.run(
        [str(script)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SHELLOPTS": "xtrace"},
    )
    traced = [line for line in result.stderr.splitlines() if line.startswith("+")]
    assert any("secret=value" in line for line in traced), (
        "SHELLOPTS=xtrace did not trace an unprotected script, so the test above proves nothing"
    )


@pytest.mark.parametrize("relative", ROOT_COMMANDS)
def test_no_script_echoes_a_planted_environment_variable(relative: str) -> None:
    planted = "APG_CANARY_VALUE_bH3x9Qf2"
    result = run(relative, "--help", env={"APG_CANARY": planted})
    assert planted not in result.stdout + result.stderr, f"{relative} leaked its environment"


# ---------------------------------------------------------------------------
# Env files are read, never executed
# ---------------------------------------------------------------------------


def test_state_files_are_parsed_rather_than_sourced() -> None:
    """A compose.env under /var/lib is written by another process.

    Sourcing it executes it. Reading it with grep does not, and the difference
    is a root shell.
    """
    code = code_of("bin/edge-network.sh")
    assert "grep -m1 '^EDGE_NETWORK_NAME='" in code
    assert '. "${state}"' not in code
    assert "source" not in code


def test_no_dotenv_is_written_under_the_secret_root() -> None:
    """Compose reads a dotenv without being asked; a generated one is a leak."""
    pattern = re.compile(r"/var/lib/agentic-postgres/secrets\S*/\.env\b")
    offenders = [relative for relative in ROOT_COMMANDS if pattern.search(source_of(relative))]
    assert not offenders, f"a dotenv is written under the secret root by: {offenders}"


# ---------------------------------------------------------------------------
# Ordering that cannot be expressed anywhere else
# ---------------------------------------------------------------------------


def test_the_project_runtime_attaches_after_starting_and_detaches_before_stopping() -> None:
    """Both orders are asymmetric and both matter.

    Attaching before the containers are healthy points a live route at
    something that is not serving. Tearing down before detaching leaves an
    endpoint on the edge network, and Compose then cannot remove it -- reported
    as a network error rather than as the missing detach it is.
    """
    code = code_of("bin/project-runtime.sh")

    # Compared by position in the whole script rather than by splitting on
    # "up)", which also matches the `up|down|status)` arm of the argument
    # parser and silently measures the wrong block.
    def at(needle: str) -> int:
        index = code.find(needle)
        assert index >= 0, f"{needle!r} is absent from bin/project-runtime.sh"
        return index

    assert at("materialize-secrets.sh") < at("--profile session2 up")
    assert at("--profile session2 up") < at("attach --project-key")
    assert at("detach --project-key") < at("--profile session2 down")


def test_teardown_never_removes_volumes() -> None:
    for relative in ("bin/project-runtime.sh", "bin/edge.sh"):
        code = code_of(relative)
        for flag in (" -v", " --volumes"):
            assert f"down{flag}" not in code, f"{relative} removes volumes on teardown"


def test_the_firewall_reconciles_by_tag_rather_than_flushing() -> None:
    """Flushing DOCKER-USER would also delete rules Docker put there."""
    code = code_of("bin/docker-firewall.sh")
    assert "-F DOCKER-USER" not in code, "the firewall flushes the whole chain"
    assert "--comment" in code or "RULE_TAG" in code


# ---------------------------------------------------------------------------
# The gate verifies and does not deploy
# ---------------------------------------------------------------------------


def test_the_session_two_gate_does_not_deploy() -> None:
    """Plan divergence D20. A gate that deploys the system it measures cannot
    be re-run to confirm a fix."""
    code = code_of("bin/session-02-check.sh")

    # Matched as *invocations*, not as mentions. The gate legitimately names
    # deploy.sh as a shellcheck target, and naming a file is not running it.
    for deploying in (
        r"^\s*\./deploy\.sh",
        r"^\s*\S*/deploy\.sh\s+--",
        r"--through-session",
        r"provision-host\.sh[^\n]*--apply",
        r"edge\.sh[^\n]*\b(up|down|restart|promote-acme)\b",
        r"project-runtime\.sh[^\n]*\bup\b",
        r"materialize-secrets\.sh",
    ):
        match = re.search(deploying, code, re.MULTILINE)
        assert match is None, (
            f"the Session 2 gate performs a deployment step: {match.group(0).strip()!r}"
        )

    assert "provision-host.sh --host" in code and "--check" in code, (
        "the gate should verify the host baseline read-only"
    )


def test_the_deployment_scan_would_catch_a_real_invocation() -> None:
    """Guard the guard: the patterns above must reject what they describe."""
    assert re.search(r"^\s*\./deploy\.sh", "  ./deploy.sh --through-session 2", re.MULTILINE)
    assert re.search(r"provision-host\.sh[^\n]*--apply", "bin/provision-host.sh --host h --apply")
    assert re.search(r"edge\.sh[^\n]*\b(up|down|restart|promote-acme)\b", "bin/edge.sh --host h up")
    # ...and must not reject naming the file as a lint target.
    assert not re.search(r"^\s*\./deploy\.sh", "shellcheck deploy.sh bin/*.sh", re.MULTILINE)


def test_the_session_two_gate_does_not_replace_the_session_one_gate() -> None:
    assert (REPO_ROOT / "bin" / "session-01-check.sh").is_file()
    code = code_of("bin/session-02-check.sh")
    assert "session-01-check.sh" not in code, (
        "the Session 2 gate invokes the Session 1 gate; they are separate exit criteria "
        "and running one from the other hides which failed"
    )


def test_every_mode_of_the_gate_is_reachable() -> None:
    for mode in ("offline", "host", "external"):
        assert f"mode_{mode}" in code_of("bin/session-02-check.sh")

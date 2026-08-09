"""`bin/connect.sh`, the developer connection helper (D88, ADR 0017).

It left ``FUTURE_STUBS`` in this run, so what replaces
``test_future_stub_exits_ten`` is this module. That test asserted one exit code
for a bare invocation. These assert the things the helper exists to get right,
and most of them run end to end: a recorded tunnel is a real process this module
starts, and the host is a fake ``ssh`` on ``PATH``. So "the credential reaches
the child through a 0600 file and is removed afterwards" is measured rather than
read off the source.

Two properties get the most attention, because they are the two whose failure is
silent:

*Nothing prints a password.* Not by default, not behind a flag. The check is
that the exact byte sequence the fake host returns does not appear in anything
the helper writes to a terminal.

*A tunnel is stopped by recorded identity, never by name.* The test for that
records a *live* process under a *wrong* identity and asserts the helper leaves
it alone — which is the PID-reuse case, and the reason ``pkill -f ssh`` is not
an implementation of this command.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CONNECT = str(REPO_ROOT / "bin" / "connect.sh")
SOURCE = (REPO_ROOT / "bin" / "connect.sh").read_text(encoding="utf-8")

PROJECT = "agentic-alpha-dev"
ROLE = "apg_agentic_alpha_dev_app_runtime"
DATABASE = "agentic_alpha_dev"
LOCAL_PORT = 15433

#: Deliberately awkward. A colon is libqp's field separator in a pgpass line and
#: a backslash is its escape; a password carrying both is the case where an
#: unescaped write parses into different fields and fails as "no password
#: supplied", which sends the reader to entirely the wrong place.
FAKE_PASSWORD = r"pa:ss\wo:rd-9Xq2"  # noqa: S105


def run(*args: str, env: dict[str, str] | None = None, cwd: Path | None = None):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=None if env is None else {**os.environ, **env},
    )


@pytest.fixture
def runtime(tmp_path: Path) -> Path:
    """An $XDG_RUNTIME_DIR the helper will accept."""
    path = tmp_path / "xdg"
    path.mkdir()
    return path


def state_dir(runtime: Path) -> Path:
    path = runtime / "agentic-postgres" / "tunnels"
    path.mkdir(parents=True, exist_ok=True)
    (runtime / "agentic-postgres").chmod(0o700)
    path.chmod(0o700)
    return path


def process_identity(pid: int) -> tuple[str, str]:
    """`lstart` and `args`, read exactly the way the helper reads them."""
    started = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True, check=True
    ).stdout.rstrip("\n")
    args = subprocess.run(
        ["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True, check=True
    ).stdout.rstrip("\n")
    return started, args


def write_record(runtime: Path, *, pid: int, started: str, args: str, profile: str) -> Path:
    path = state_dir(runtime) / f"{PROJECT}__{profile}.json"
    path.write_text(
        json.dumps(
            {
                "project": PROJECT,
                "profile": profile,
                "ssh_destination": "op@host.test",
                "ssh_port": 22,
                "bind": "127.0.0.1",
                "local_port": LOCAL_PORT,
                "remote_host": "127.0.0.1",
                "remote_port": LOCAL_PORT,
                "role": ROLE,
                "database": DATABASE,
                "pid": pid,
                "started": started,
                "args": args,
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


@pytest.fixture
def sleeper():
    """A live process to stand in for an ssh forward. Reaped whatever happens."""
    started: list[subprocess.Popen] = []

    def spawn() -> subprocess.Popen:
        process = subprocess.Popen(["sleep", "300"])
        started.append(process)
        return process

    yield spawn

    for process in started:
        if process.poll() is None:
            process.send_signal(signal.SIGKILL)
        process.wait()


@pytest.fixture
def fake_host(tmp_path: Path) -> Path:
    """An `ssh` on PATH that answers the two broker operations.

    It is not a mock of ssh. It is a stand-in for the *host*: the helper runs
    the real ssh binary's interface, and what comes back is what the broker
    would have written to that stream.
    """
    directory = tmp_path / "bin"
    directory.mkdir()
    script = directory / "ssh"
    script.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *' endpoint '*)\n"
        f'    printf \'{{"host":"127.0.0.1","port":{LOCAL_PORT},"role":"{ROLE}",\'\n'
        f'    printf \'"database":"{DATABASE}","transport":"direct"}}\\n\'\n'
        "    ;;\n"
        "  *' password '*)\n"
        "    printf '%s' \"${APG_FAKE_PASSWORD}\"\n"
        "    ;;\n"
        "  *)\n"
        '    echo "fake ssh: unexpected invocation: $*" >&2\n'
        "    exit 64\n"
        "    ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return directory


def helper_env(runtime: Path, fake_host: Path | None = None) -> dict[str, str]:
    environment = {"XDG_RUNTIME_DIR": str(runtime)}
    if fake_host is not None:
        environment["PATH"] = f"{fake_host}{os.pathsep}{os.environ['PATH']}"
        environment["APG_FAKE_PASSWORD"] = FAKE_PASSWORD
    return environment


# ---------------------------------------------------------------------------
# The command surface
# ---------------------------------------------------------------------------


def test_help_documents_every_command() -> None:
    result = run(CONNECT, "--help")
    assert result.returncode == 0, result.stderr
    for command in ("tunnel", "status", "stop", "print-env", "psql", "exec"):
        assert command in result.stdout, f"--help does not mention {command}"


def test_a_bare_invocation_is_missing_input_not_an_unavailable_capability() -> None:
    result = run(CONNECT)
    assert result.returncode == 2
    assert "required" in result.stderr.lower()


@pytest.mark.parametrize(
    ("arguments", "expected_fragment"),
    [
        (("bogus",), "unknown command"),
        (("tunnel", "--bogus"), "unknown argument"),
        (("tunnel", "--project"), "requires a value"),
        (("tunnel", "--project", "Bad_Key"), "not a valid project key"),
        (("tunnel", "--project", PROJECT, "--profile", "superuser"), "not an access profile"),
        (("tunnel", "--project", PROJECT, "--ssh-port", "http"), "not a number"),
        (("tunnel", "--project", PROJECT, "--local-port", "443"), "unprivileged"),
        (("tunnel", "--project", PROJECT), "--ssh"),
        (("stop",), "--project is required"),
        (("exec", "--project", PROJECT, "--"), "requires a command"),
    ],
)
def test_invalid_input_is_refused_with_two(
    arguments: tuple[str, ...], expected_fragment: str
) -> None:
    result = run(CONNECT, *arguments)
    assert result.returncode == 2, f"got {result.returncode}: {result.stderr}"
    assert expected_fragment in result.stderr


def test_prisma_studio_is_redirected_rather_than_silently_unknown() -> None:
    """The source specification names it as a mode. It is a client, and clients
    run through `exec` -- saying so is more use than "unknown command"."""
    result = run(CONNECT, "prisma-studio")
    assert result.returncode == 2
    assert "exec" in result.stderr


# ---------------------------------------------------------------------------
# Host-key verification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "option",
    [
        "StrictHostKeyChecking=no",
        "stricthostkeychecking=NO",
        "StrictHostKeyChecking=off",
        "StrictHostKeyChecking=accept-new",
        "StrictHostKeyChecking = no",
        "UserKnownHostsFile=/dev/null",
    ],
)
def test_an_option_that_disables_host_key_verification_is_refused(option: str) -> None:
    """`accept-new` is refused with the other two, and that is the point of
    listing it: it trusts the first key it sees, which on a first connection is
    every key. A tunnel whose far end is not verified is a private channel to
    somebody."""
    result = run(CONNECT, "tunnel", "--project", PROJECT, "--ssh-option", option)
    assert result.returncode == 2, f"got {result.returncode}: {result.stderr}"
    assert "refusing" in result.stderr.lower()


def test_an_ordinary_ssh_option_is_still_accepted(runtime: Path) -> None:
    """Guard the guard. A refusal that rejected every option would pass the test
    above while making the flag useless, and nothing would say so."""
    result = run(
        CONNECT,
        "print-env",
        "--project",
        PROJECT,
        "--ssh-option",
        "Compression=yes",
        env=helper_env(runtime),
    )
    assert result.returncode != 2, result.stderr


def test_the_helper_asks_for_verification_explicitly() -> None:
    """`ask` is the default and is a refusal under BatchMode with a message
    about terminals, which reads as a broken script rather than an unknown
    host."""
    assert "-o StrictHostKeyChecking=yes" in SOURCE
    assert "-o ExitOnForwardFailure=yes" in SOURCE
    assert "-o BatchMode=yes" in SOURCE


def test_a_forward_binds_loopback_and_nothing_else() -> None:
    assert 'readonly LOCAL_BIND="127.0.0.1"' in SOURCE
    assert '-L "${LOCAL_BIND}:${local_port}:${remote_host}:${remote_port}"' in SOURCE


# ---------------------------------------------------------------------------
# Least privilege
# ---------------------------------------------------------------------------


def test_the_default_profile_is_the_runtime_role_over_the_direct_transport(
    runtime: Path,
) -> None:
    """Observed through the failure, which names the profile it was going to use."""
    result = run(CONNECT, "print-env", "--project", PROJECT, env=helper_env(runtime))
    assert result.returncode == 4
    assert "--profile runtime_direct" in result.stderr


def test_selecting_migration_authority_prints_a_warning(runtime: Path) -> None:
    result = run(
        CONNECT,
        "print-env",
        "--project",
        PROJECT,
        "--profile",
        "migration_direct",
        env=helper_env(runtime),
    )
    assert "owns the schema" in result.stderr


def test_no_command_substitutes_a_migration_credential_for_a_direct_transport() -> None:
    """The two direct profiles share a transport and nothing else.

    The profile is carried through to the broker verbatim; there is no branch
    anywhere that maps a transport back to a profile, which is the shape that
    would let "they asked for direct" become "so give them migration_direct".
    """
    assert 'readonly DEFAULT_PROFILE="runtime_direct"' in SOURCE
    assert 'PROFILE="${DEFAULT_PROFILE}"' in SOURCE
    assert '"${PROJECT_KEY}" "${operation}" "${PROFILE}"' in SOURCE

    # `PROFILE` is assigned exactly twice: once to the default, once from
    # `--profile`. A third assignment would be somewhere a profile is derived
    # rather than chosen, and derivation is how "direct" becomes
    # "migration_direct".
    assignments = re.findall(r"^\s*PROFILE=", SOURCE, re.MULTILINE)
    assert len(assignments) == 2, f"PROFILE is assigned {len(assignments)} times, expected 2"


# ---------------------------------------------------------------------------
# Tunnel state
# ---------------------------------------------------------------------------


def test_a_state_directory_others_can_read_is_refused(runtime: Path) -> None:
    """On a shared machine a directory of this name that is not 0700 is somebody
    else's, and a tunnel record tells them which host to reach on which port."""
    base = runtime / "agentic-postgres"
    base.mkdir()
    base.chmod(0o755)
    result = run(CONNECT, "status", env=helper_env(runtime))
    assert result.returncode == 3
    assert "mode 755" in result.stderr


def test_status_on_a_host_with_no_tunnels_says_so(runtime: Path) -> None:
    result = run(CONNECT, "status", env=helper_env(runtime))
    assert result.returncode == 0, result.stderr
    assert "no tunnels recorded" in result.stdout


def test_a_live_tunnel_is_reported_live(runtime: Path, sleeper) -> None:
    process = sleeper()
    started, args = process_identity(process.pid)
    write_record(runtime, pid=process.pid, started=started, args=args, profile="runtime_direct")

    result = run(CONNECT, "status", env=helper_env(runtime))
    assert result.returncode == 0, result.stderr
    assert "live" in result.stdout
    assert PROJECT in result.stdout


def test_a_record_whose_process_is_gone_is_quarantined_rather_than_deleted(
    runtime: Path, sleeper
) -> None:
    """Deleted, the evidence that a tunnel died unexpectedly goes with it."""
    process = sleeper()
    started, args = process_identity(process.pid)
    process.send_signal(signal.SIGKILL)
    process.wait()
    record = write_record(
        runtime, pid=process.pid, started=started, args=args, profile="runtime_direct"
    )

    result = run(CONNECT, "status", env=helper_env(runtime))
    assert result.returncode == 0, result.stderr
    assert "stale" in result.stdout
    assert not record.exists()
    quarantined = list((runtime / "agentic-postgres" / "quarantine").iterdir())
    assert len(quarantined) == 1
    assert record.name in quarantined[0].name


def test_stop_will_not_signal_a_process_that_is_not_the_one_recorded(
    runtime: Path, sleeper
) -> None:
    """The PID-reuse case, which is the whole reason identity is recorded.

    A live process is recorded under a *wrong* argument vector -- exactly what a
    reused PID looks like. `stop` must leave it alone. An implementation that
    signalled by PID alone, or matched by process name, kills it here.
    """
    process = sleeper()
    started, _ = process_identity(process.pid)
    write_record(
        runtime,
        pid=process.pid,
        started=started,
        args="ssh -N -L 127.0.0.1:15433:127.0.0.1:15433 op@host.test",
        profile="runtime_direct",
    )

    result = run(CONNECT, "stop", "--project", PROJECT, env=helper_env(runtime))
    assert result.returncode == 4
    time.sleep(0.2)
    assert process.poll() is None, "connect.sh signalled a process it had not verified"
    assert "refusing to signal" in result.stderr


def test_stop_closes_a_tunnel_whose_identity_matches(runtime: Path, sleeper) -> None:
    process = sleeper()
    started, args = process_identity(process.pid)
    record = write_record(
        runtime, pid=process.pid, started=started, args=args, profile="runtime_direct"
    )

    result = run(CONNECT, "stop", "--project", PROJECT, env=helper_env(runtime))
    assert result.returncode == 0, result.stderr
    assert not record.exists()
    process.wait(timeout=5)
    assert process.returncode is not None


def test_nothing_is_ever_matched_by_process_name(code_only) -> None:
    """`pkill -f ssh` on a developer's machine kills their editor's remote
    session, their deploy and the tunnel, and reports success.

    Asserted over code with comments stripped, because the comment in
    `process_matches` says exactly that -- and a scan that counted its own
    explanation as a violation would have to be weakened until it counted
    nothing.
    """
    code = code_only(SOURCE)
    for forbidden in ("pkill", "pgrep", "killall"):
        assert forbidden not in code, f"connect.sh uses {forbidden}"


# ---------------------------------------------------------------------------
# What reaches a terminal, and what reaches a child
# ---------------------------------------------------------------------------


def test_print_env_prints_connection_variables_and_no_credential(
    runtime: Path, sleeper, fake_host: Path
) -> None:
    process = sleeper()
    started, args = process_identity(process.pid)
    write_record(runtime, pid=process.pid, started=started, args=args, profile="runtime_direct")

    result = run(CONNECT, "print-env", "--project", PROJECT, env=helper_env(runtime, fake_host))
    assert result.returncode == 0, result.stderr

    assert "PGHOST=127.0.0.1" in result.stdout
    assert f"PGPORT={LOCAL_PORT}" in result.stdout
    assert f"PGUSER={ROLE}" in result.stdout
    assert f"PGDATABASE={DATABASE}" in result.stdout
    assert f"DATABASE_URL=postgresql://{ROLE}@127.0.0.1:{LOCAL_PORT}/{DATABASE}" in result.stdout

    combined = result.stdout + result.stderr
    assert FAKE_PASSWORD not in combined
    assert "PGPASSWORD" not in combined
    # It does not even fetch one: a command that prints no credential should not
    # be asking the host for one, or a rotation would show up in its logs.
    assert "PGPASSFILE" not in result.stdout.split("#")[0]


def test_the_url_print_env_emits_could_not_carry_a_password(
    runtime: Path, sleeper, fake_host: Path
) -> None:
    """The same rule `postgresUrl` states in the output schema: the userinfo
    component admits one identifier and no colon."""
    process = sleeper()
    started, args = process_identity(process.pid)
    write_record(runtime, pid=process.pid, started=started, args=args, profile="runtime_direct")

    result = run(CONNECT, "print-env", "--project", PROJECT, env=helper_env(runtime, fake_host))
    url = next(line for line in result.stdout.splitlines() if line.startswith("DATABASE_URL="))
    assert re.fullmatch(
        r"DATABASE_URL=postgresql://[a-z_][a-z0-9_]*@[a-z0-9.]+:[0-9]+/[a-z_][a-z0-9_]*", url
    ), url


def test_exec_hands_the_credential_to_a_child_through_a_private_file(
    runtime: Path, sleeper, fake_host: Path, tmp_path: Path
) -> None:
    """End to end, with a fake host: the credential reaches the client and
    nothing else.

    What is asserted is everything the file has to be at the moment the child
    can see it -- present, 0600, correctly escaped -- and that it is gone
    afterwards. A trap that expanded to an empty path would leave the file on
    disk while every visible sign said it had been cleaned up, which is exactly
    what a `local` variable in an EXIT trap does.
    """
    process = sleeper()
    started, args = process_identity(process.pid)
    write_record(runtime, pid=process.pid, started=started, args=args, profile="runtime_direct")

    captured = tmp_path / "captured"
    result = run(
        CONNECT,
        "exec",
        "--project",
        PROJECT,
        "--",
        "sh",
        "-c",
        f'cat "$PGPASSFILE" > {captured}; stat -c %a "$PGPASSFILE" >> {captured}; '
        f'printf "%s\\n" "$PGPASSFILE" >> {captured}',
        env=helper_env(runtime, fake_host),
    )
    assert result.returncode == 0, result.stderr

    lines = captured.read_text(encoding="utf-8").splitlines()
    # 127.0.0.1:15433:database:role:pa\:ss\\wo\:rd-9Xq2
    assert lines[0] == rf"127.0.0.1:{LOCAL_PORT}:{DATABASE}:{ROLE}:pa\:ss\\wo\:rd-9Xq2"
    assert lines[1] == "600"
    assert not Path(lines[2]).exists(), "the credential file outlived the child"

    assert FAKE_PASSWORD not in result.stdout + result.stderr


def test_exec_returns_the_child_status(runtime: Path, sleeper, fake_host: Path) -> None:
    process = sleeper()
    started, args = process_identity(process.pid)
    write_record(runtime, pid=process.pid, started=started, args=args, profile="runtime_direct")

    result = run(
        CONNECT,
        "exec",
        "--project",
        PROJECT,
        "--",
        "sh",
        "-c",
        "exit 17",
        env=helper_env(runtime, fake_host),
    )
    assert result.returncode == 17


def test_the_credential_is_written_by_a_builtin_and_never_becomes_an_argument() -> None:
    """`printf` is a shell builtin, so the value never appears in an argument
    vector any other process can read out of /proc. A `echo | tee` or an
    `openssl` call here would publish it for the length of the write."""
    body = SOURCE.split("write_pgpass() {")[1].split("\n}")[0]
    assert "printf '%s:%s:%s:%s:%s\\n'" in body
    assert "umask 077" in body
    assert "chmod 600" in body


def test_the_password_operation_is_reached_from_exactly_one_place() -> None:
    """Every other route to a credential would be another route to a leak."""
    assert SOURCE.count("broker password") == 1
    assert "broker password" in SOURCE.split("write_pgpass() {")[1].split("\n}")[0]


def test_the_broker_path_is_fixed_rather_than_configurable() -> None:
    """A caller-supplied path to a privileged program is the whole attack."""
    assert 'readonly BROKER="/usr/local/libexec/agentic-postgres/database-access"' in SOURCE
    assert "--broker" not in SOURCE

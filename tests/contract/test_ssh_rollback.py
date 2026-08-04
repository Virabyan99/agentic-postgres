"""The SSH rollback launcher, which runs when nobody is watching.

``bin/provision-host.sh`` refuses to harden SSH unless a transient timer firing
this script is already armed. That makes it the last thing standing between a
bad ``sshd_config`` and a server reachable only through a provider console — and
it runs unattended, ten minutes after the operator has stopped paying attention
or has been disconnected.

Its failure modes are therefore not "returns a bad exit code". They are:

* restoring something that is not a backup, leaving a host with no sshd_config
  at all — strictly worse than the state that triggered the rollback;
* ``restart`` instead of ``reload``, dropping the session an operator may be
  using to fix things by hand;
* rolling itself back on failure, leaving nothing to diagnose.

Each of those is asserted here. The happy path needs a live sshd and is exercised
on the host; these are the refusals, which are the parts that matter most and
which nothing on a host would notice being wrong until the day they are needed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

LAUNCHER = REPO_ROOT / "libexec" / "agentic-postgres-ssh-rollback"


def run(*args: str):
    return subprocess.run(
        [str(LAUNCHER), *args], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )


def code() -> str:
    return "\n".join(
        line
        for line in LAUNCHER.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


# ---------------------------------------------------------------------------
# It exists, and provision-host.sh points at where it will be
# ---------------------------------------------------------------------------


def test_the_launcher_exists_and_is_executable_in_the_git_index() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", "libexec/agentic-postgres-ssh-rollback"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.startswith("100755"), result.stdout.strip() or "not tracked"


def test_provision_host_names_the_path_this_installs_to() -> None:
    """The instruction an operator copy-pastes must name a real file.

    This is the specific bug this module was written after: provision-host.sh
    printed an arm command pointing at a launcher that did not exist, so
    following the documented procedure exactly would arm a timer that failed
    when it fired — and the failure would be discovered during a lockout.
    """
    provision = (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")
    assert "ssh-rollback" in provision

    # The installed name is the long filename with the prefix stripped.
    assert LAUNCHER.name == "agentic-postgres-ssh-rollback"
    assert "install_launchers" in provision, "nothing installs the launcher onto the host"


def test_provision_host_installs_launchers_before_hardening_ssh() -> None:
    """Ordering: the timer cannot be armed before the file it fires exists.

    Anchored on the write of the sshd snippet rather than on a mention of
    ``rollback_is_armed``, because the function name also appears in an earlier
    guard that has nothing to do with this ordering. A test that can be
    satisfied by an unrelated occurrence of its own search string is measuring
    the wrong thing.
    """
    provision = (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")
    body = provision.split("apply_baseline()", 1)[1]
    assert body.index("install_launchers") < body.index("${SSH_SNIPPET}"), (
        "the sshd snippet is written before the rollback launcher is installed"
    )


# ---------------------------------------------------------------------------
# The reload is the point of no return
# ---------------------------------------------------------------------------
#
# The timer is the last line of defence, not the first. Reloading a merged
# configuration and finding out from a failed login that it was wrong is the
# scenario the timer exists to survive — but it is one an operator should
# almost never reach, because the merged policy can be read before it is
# loaded and backed out for free.


def provision_source() -> str:
    return (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")


def ssh_apply_section() -> str:
    body = provision_source().split("apply_baseline()", 1)[1]
    return body.split("== ssh ==", 1)[1].split("== docker ==", 1)[0]


def test_the_resolved_policy_is_verified_before_the_reload() -> None:
    """`sshd -t` is syntax. It says nothing about who can still authenticate."""
    section = ssh_apply_section()
    assert "verify_resolved_sshd_policy" in section, "nothing checks the merged policy"
    assert section.index("verify_resolved_sshd_policy") < section.index("systemctl reload"), (
        "the configuration is reloaded before its resolved policy is checked"
    )


def test_a_wrong_policy_removes_the_snippet_instead_of_loading_it() -> None:
    """On-disk state must not claim a hardening that was never loaded.

    Leaving the file behind after refusing means the next reload — a package
    upgrade, an unrelated `systemctl reload ssh` — applies the configuration
    this run just decided was wrong, at a moment nobody is watching.
    """
    section = ssh_apply_section()
    verify_index = section.index("verify_resolved_sshd_policy")
    tail = section[verify_index:]
    removal = tail.index('rm -f "${SSH_SNIPPET}"')
    assert removal < tail.index("systemctl reload"), "a rejected snippet is left on disk"


def test_a_syntax_failure_also_removes_the_snippet() -> None:
    section = ssh_apply_section()
    between = section[section.index("sshd -t") : section.index("verify_resolved_sshd_policy")]
    assert 'rm -f "${SSH_SNIPPET}"' in between


def test_the_probe_resolves_match_blocks() -> None:
    """Without -C, a `Match User op` that disables pubkey auth is invisible.

    Match applies wherever it appears, so being first in the include order is no
    protection against it — which is exactly why the resolved value, not the
    file's contents, is what gets checked.
    """
    body = provision_source().split("verify_resolved_sshd_policy()", 1)[1].split("\n}", 1)[0]
    assert "sshd -T -C" in body
    assert "user=${operator}" in body


def test_check_and_apply_enforce_the_same_policy_list() -> None:
    """Two lists under one name is two policies, and only one of them is tested."""
    source = provision_source()
    assert source.count("SSHD_REQUIRED_POLICY=(") == 1
    assert source.count('"${SSHD_REQUIRED_POLICY[@]}"') == 2, (
        "the baseline check and the safety gate do not both read the shared policy list"
    )


def test_the_policy_list_covers_the_directives_that_decide_access() -> None:
    source = provision_source()
    block = source.split("SSHD_REQUIRED_POLICY=(", 1)[1].split(")", 1)[0]
    for directive in (
        "pubkeyauthentication yes",
        "passwordauthentication no",
        "permitrootlogin no",
    ):
        assert directive in block, f"the shared policy list omits {directive!r}"


# ---------------------------------------------------------------------------
# It refuses rather than guesses
# ---------------------------------------------------------------------------


def test_help_exits_zero_and_documents_the_disarm_step() -> None:
    result = run("--help")
    assert result.returncode == 0
    assert "confirm-ssh-ok" in result.stdout, "--help does not say how to disarm the timer"


def test_a_missing_argument_is_refused() -> None:
    result = run()
    assert result.returncode == 2
    assert "required" in result.stderr


def test_a_nonexistent_backup_is_refused(tmp_path: Path) -> None:
    result = run(str(tmp_path / "absent"))
    assert result.returncode == 2
    assert "does not exist" in result.stderr


def test_a_directory_without_sshd_config_is_refused(tmp_path: Path) -> None:
    """Restoring this would leave the host with no server configuration at all.

    The rollback would then have made things worse than the failure it was
    firing to undo, unattended, with nobody to notice.
    """
    empty = tmp_path / "not-a-backup"
    empty.mkdir()
    (empty / "ssh_config").write_text("# client config, not server\n", encoding="utf-8")

    result = run(str(empty))
    assert result.returncode == 2
    assert "sshd_config" in result.stderr


def test_a_symlinked_backup_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "sshd_config").write_text("Port 22\n", encoding="utf-8")
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)

    result = run(str(link))
    assert result.returncode == 2
    assert "symlink" in result.stderr


def test_it_does_not_search_for_a_backup() -> None:
    """The directory is an argument. Picking "the most recent" backup would be a
    decision, and guessing wrong here is indistinguishable from doing nothing."""
    body = code()
    for guessing in ("ls -t", "find /var/backups", "*/ssh", "head -n 1"):
        assert guessing not in body, f"the rollback guesses which backup to use via {guessing!r}"


# ---------------------------------------------------------------------------
# What it does when it does act
# ---------------------------------------------------------------------------


def test_it_reloads_and_never_restarts() -> None:
    """A restart drops every existing session, including the one an operator may
    be using to fix this by hand."""
    body = code()
    assert "systemctl reload" in body
    assert "systemctl restart" not in body, "the rollback restarts sshd, dropping live sessions"


def test_it_validates_the_restored_configuration_before_reloading() -> None:
    body = code()
    assert "sshd -t" in body
    assert body.index("sshd -t") < body.index("systemctl reload"), (
        "the rollback reloads before checking that what it restored is valid"
    )


def test_it_preserves_the_configuration_that_failed() -> None:
    """The broken config is the only thing anyone will want to read afterwards,
    and this is the last moment it exists."""
    assert "failed-config" in code()


def test_it_does_not_roll_itself_back_on_failure() -> None:
    """A rollback that undoes itself leaves nothing to diagnose and a host in
    the state that caused the lockout."""
    body = code()
    tail = body.split("RESTORED configuration", 1)[-1]
    assert "cp -a" not in tail, "the rollback restores something else after failing"


def test_it_requires_root() -> None:
    body = code()
    assert "id -u" in body and "must run as root" in body

"""Host templates, systemd units, and the immutable-release launchers.

None of this runs a host. What it asserts is the shape of what *would* be
installed, and the assertions are chosen around the three failures that are
expensive to discover on a live machine:

* a systemd unit that executes a working tree, so `git checkout` changes what
  runs at the next boot;
* a `DOCKER-USER` policy written with `--dport`, which matches the container's
  port rather than the port the client asked for, and therefore permits nothing
  it intends to permit and blocks nothing it intends to block;
* an SSH snippet that sorts after an earlier include and is silently overridden.

The launchers are shell-checked by the gate along with `bin/*.sh`, so this
module asserts semantics rather than syntax.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

INFRA_HOST = REPO_ROOT / "infra" / "host"
SYSTEMD = REPO_ROOT / "systemd"
LIBEXEC = REPO_ROOT / "libexec"

UNITS = (
    "agentic-postgres-docker-firewall.service",
    "agentic-postgres-edge.service",
    "agentic-postgres-project@.service",
)
#: Launchers that resolve an installed release and exec a script inside it.
#:
#: ``agentic-postgres-ssh-rollback`` is deliberately absent. It is a launcher by
#: location only: it restores files and reloads sshd, and resolves no release,
#: so the release-indirection assertions below do not apply to it. It has its
#: own module, tests/contract/test_ssh_rollback.py, because what matters about
#: it is different -- it runs unattended during a lockout.
LAUNCHERS = (
    "agentic-postgres-edge",
    "agentic-postgres-project",
    "agentic-postgres-firewall",
)


def unit_text(name: str) -> str:
    return (SYSTEMD / name).read_text(encoding="utf-8")


def rule_lines(name: str) -> list[str]:
    return [
        line.strip()
        for line in (INFRA_HOST / name).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# ---------------------------------------------------------------------------
# Docker daemon baseline
# ---------------------------------------------------------------------------


def test_daemon_config_is_valid_json_and_minimal() -> None:
    document = json.loads((INFRA_HOST / "daemon.json").read_text(encoding="utf-8"))
    assert document["live-restore"] is True
    assert document["log-driver"] == "local"
    assert document["log-opts"] == {"max-size": "10m", "max-file": "5"}
    assert document["userland-proxy"] is False


def test_daemon_config_enables_no_remote_api_and_no_experimental_feature() -> None:
    """A TCP listener on the Docker socket is root on this host, to anyone."""
    document = json.loads((INFRA_HOST / "daemon.json").read_text(encoding="utf-8"))
    assert "hosts" not in document, "daemon.json declares a listener"
    assert "tls" not in document
    assert document.get("experimental") is not True
    assert "userns-remap" not in document, (
        "user-namespace remapping complicates bind-mounted secret ownership and "
        "needs its own compatibility exercise (runbook Phase 8)"
    )


def test_daemon_config_does_not_disable_docker_iptables() -> None:
    """`iptables: false` would leave containers unreachable and DOCKER-USER unused.

    It is the most commonly suggested fix for "UFW does not block my container",
    and it breaks Docker networking rather than fixing the firewall.
    """
    document = json.loads((INFRA_HOST / "daemon.json").read_text(encoding="utf-8"))
    assert document.get("iptables") is not False
    assert document.get("ip6tables") is not False


# ---------------------------------------------------------------------------
# DOCKER-USER policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["docker-user-rules.v4", "docker-user-rules.v6"])
def test_policy_matches_the_original_destination_port(name: str) -> None:
    """The detail that decides whether this policy does anything at all.

    DNAT has already rewritten the destination by the time a packet reaches
    FORWARD, so `--dport 80` matches the *container's* port. `--ctorigdstport`
    is the port the client actually asked for.
    """
    lines = rule_lines(name)
    port_rules = [line for line in lines if "80" in line or "443" in line]
    assert port_rules, f"{name} permits nothing"
    for line in port_rules:
        assert "--ctorigdstport" in line, f"{name} uses a post-DNAT port match: {line}"
        assert "--dport" not in line, f"{name} uses --dport, which matches the container port"


@pytest.mark.parametrize("name", ["docker-user-rules.v4", "docker-user-rules.v6"])
def test_policy_ends_in_a_default_drop(name: str) -> None:
    """An allowlist whose last rule is not a drop is a list of suggestions."""
    lines = rule_lines(name)
    assert lines[-1].endswith("-j DROP"), f"{name} does not end in a default drop"
    assert "-j REJECT" not in "\n".join(lines), (
        f"{name} rejects rather than drops; a reject response confirms the port exists"
    )


@pytest.mark.parametrize("name", ["docker-user-rules.v4", "docker-user-rules.v6"])
def test_policy_permits_exactly_eighty_and_four_four_three(name: str) -> None:
    ports = set()
    for line in rule_lines(name):
        match = re.search(r"--ctorigdstport (\d+)", line)
        if match:
            ports.add(int(match.group(1)))
    assert ports == {80, 443}, f"{name} permits {sorted(ports)}"


@pytest.mark.parametrize("name", ["docker-user-rules.v4", "docker-user-rules.v6"])
def test_policy_allows_established_traffic_first(name: str) -> None:
    """Otherwise every reply to an outbound connection is dropped."""
    first = rule_lines(name)[0]
    assert "RELATED,ESTABLISHED" in first, f"{name} does not return established traffic first"


def test_ipv6_policy_permits_icmpv6() -> None:
    """Dropping ICMPv6 breaks path MTU discovery and neighbour discovery.

    The symptom is a connection that completes and then hangs on the first large
    response, which looks like an application fault for a long time.
    """
    lines = "\n".join(rule_lines("docker-user-rules.v6"))
    assert "ipv6-icmp" in lines
    assert "--limit" in lines, "unrestricted ICMPv6 is a flood amplifier"


@pytest.mark.parametrize("name", ["docker-user-rules.v4", "docker-user-rules.v6"])
def test_rate_units_are_written_the_way_iptables_echoes_them(name: str) -> None:
    """A rendered rule has to survive a round trip through iptables as text.

    ``--limit 10/second`` and ``--limit 10/sec`` mean the same thing going in,
    and ``iptables -S`` returns the short form either way. Writing the long one
    makes the installed file and the running chain differ as text while being
    identical in effect, which fails the live comparison that proves the kernel
    is running this exact policy.

    Caught on a real host, where the v4 policy matched perfectly and v6 differed
    by one word. The alternative was normalising spellings inside the live
    comparison, and every entry in such a table is a difference that check has
    agreed in advance not to notice.
    """
    text = "\n".join(rule_lines(name))
    for long_form, short_form in (("/second", "/sec"), ("/minute", "/min")):
        assert long_form not in text, (
            f"{name} writes {long_form!r}; iptables reports it as {short_form!r}"
        )


def test_the_public_interface_is_a_substituted_placeholder() -> None:
    """A hard-coded eth0 is wrong on roughly half of all providers."""
    for name in ("docker-user-rules.v4", "docker-user-rules.v6"):
        text = (INFRA_HOST / name).read_text(encoding="utf-8")
        assert "__PUBLIC_INTERFACE__" in text
        assert not re.search(r"-i (eth|ens|enp)\w*", text), f"{name} hard-codes an interface"


# ---------------------------------------------------------------------------
# SSH
# ---------------------------------------------------------------------------


def test_ssh_snippet_sorts_first() -> None:
    """OpenSSH takes the first obtained value and includes lexicographically.

    A file named 60-... loses to an earlier cloud-init snippet, silently.
    """
    assert (INFRA_HOST / "00-agentic-postgres-ssh.conf").is_file()


def test_ssh_snippet_sets_the_policy_that_carries_the_boundary() -> None:
    """With 0.0.0.0/0 as an accepted source CIDR, these ARE the boundary."""
    text = (INFRA_HOST / "00-agentic-postgres-ssh.conf").read_text(encoding="utf-8")
    for directive in (
        "PubkeyAuthentication yes",
        "PasswordAuthentication no",
        "KbdInteractiveAuthentication no",
        "PermitRootLogin no",
        "PermitEmptyPasswords no",
        "MaxAuthTries 3",
        "LoginGraceTime 30",
    ):
        assert directive in text, f"the SSH snippet does not set {directive!r}"


def test_ssh_snippet_keeps_local_forwarding_for_session_four() -> None:
    """Session 4 tunnels the direct database endpoint. `no` forecloses that."""
    text = (INFRA_HOST / "00-agentic-postgres-ssh.conf").read_text(encoding="utf-8")
    assert "AllowTcpForwarding local" in text
    assert "GatewayPorts no" in text


def test_ssh_snippet_pins_no_cipher_list() -> None:
    """A hand-pinned list is frozen at the day it was written."""
    text = (INFRA_HOST / "00-agentic-postgres-ssh.conf").read_text(encoding="utf-8")
    for keyword in ("Ciphers ", "MACs ", "KexAlgorithms "):
        assert f"\n{keyword}" not in text, f"the snippet pins {keyword.strip()}"


def test_ssh_port_is_substituted_not_hard_coded() -> None:
    text = (INFRA_HOST / "00-agentic-postgres-ssh.conf").read_text(encoding="utf-8")
    assert "Port __SSH_PORT__" in text


def test_unattended_upgrades_does_not_reboot_automatically() -> None:
    """An unattended reboot takes every project down at a time nobody chose."""
    text = (INFRA_HOST / "20auto-upgrades").read_text(encoding="utf-8")
    assert 'APT::Periodic::Update-Package-Lists "1";' in text
    assert 'APT::Periodic::Unattended-Upgrade "1";' in text
    assert "Automatic-Reboot" not in text


# ---------------------------------------------------------------------------
# systemd units
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", UNITS)
def test_units_execute_only_installed_release_launchers(name: str) -> None:
    """Runbook §4.2: an installed unit never executes an operator's checkout.

    This is the assertion that keeps `git checkout` from changing what runs at
    the next boot.
    """
    for line in unit_text(name).splitlines():
        stripped = line.strip()
        if not stripped.startswith(("ExecStart", "ExecStop", "ExecReload")):
            continue
        command = stripped.split("=", 1)[1].strip()
        assert command.startswith("/usr/local/libexec/agentic-postgres/"), (
            f"{name} executes something other than a launcher: {command}"
        )


@pytest.mark.parametrize("name", UNITS)
def test_units_reference_no_repository_path(name: str) -> None:
    text = unit_text(name)
    for forbidden in ("/home/", "~/", "./bin/", "$PWD"):
        assert forbidden not in text, f"{name} references a working tree: {forbidden}"


#: `Documentation=file:/opt/agentic-postgres/releases/<commit>/<path>`. The
#: release directory is a checkout of a commit, so the tail is a repository
#: path and can be checked here.
DOCUMENTATION_URL = re.compile(
    r"^Documentation=file:/opt/agentic-postgres/releases/[^/]+/(?P<path>\S+)$", re.MULTILINE
)


@pytest.mark.parametrize("name", UNITS)
def test_every_documentation_url_names_a_file_that_exists(name: str) -> None:
    """A consumer with no producer, in the place an operator looks first.

    `systemctl status` prints this line. All three units carried one for a
    document that did not exist for six runs, so the one pointer a stuck
    operator is handed at 3am led nowhere. The paths are also in
    `test_repository_contract.REQUIRED_PATHS`, which stops the file being
    deleted; this stops the *reference* drifting away from it.
    """
    text = unit_text(name)
    matches = DOCUMENTATION_URL.findall(text)
    assert matches, f"{name} carries no Documentation= line an operator could follow"
    for relative in matches:
        assert (REPO_ROOT / relative).is_file(), f"{name} documents a missing path: {relative}"


def test_the_firewall_unit_runs_after_docker() -> None:
    """Docker creates DOCKER-USER when it starts and flushes its chains on restart.

    Anything that wrote the policy earlier in boot wrote it into a chain that
    did not exist yet, or one about to be recreated.
    """
    text = unit_text("agentic-postgres-docker-firewall.service")
    assert "After=docker.service" in text
    assert "Requires=docker.service" in text
    assert "PartOf=docker.service" in text


def test_the_edge_unit_requires_the_firewall() -> None:
    """A failure to apply ingress policy must stop ingress, not just log."""
    text = unit_text("agentic-postgres-edge.service")
    assert "agentic-postgres-docker-firewall.service" in text
    assert "Requires=docker.service agentic-postgres-docker-firewall.service" in text


def test_the_edge_unit_reconciles_attachments_after_every_start() -> None:
    """`docker network connect` membership does not survive container recreation.

    Without this the routes come back after a restart and vanish the next time
    the container is replaced, which is an intermittent failure with a slow
    diagnosis.
    """
    text = unit_text("agentic-postgres-edge.service")
    assert "ExecStartPost=/usr/local/libexec/agentic-postgres/edge reconcile" in text


def test_the_edge_unit_never_removes_volumes_on_stop() -> None:
    text = unit_text("agentic-postgres-edge.service")
    assert "ExecStop=/usr/local/libexec/agentic-postgres/edge down" in text
    assert "-v" not in text.split("ExecStop=")[1].splitlines()[0]


def test_the_project_unit_materializes_before_starting() -> None:
    """Order is the contract: a container must never start against a stale set."""
    text = unit_text("agentic-postgres-project@.service")
    lines = [line for line in text.splitlines() if line.startswith("ExecStart=")]
    assert "materialize" in lines[0], "the project unit starts before materializing"
    assert "up" in lines[1]


def test_the_project_unit_detaches_before_teardown() -> None:
    text = unit_text("agentic-postgres-project@.service")
    assert "ExecStop=/usr/local/libexec/agentic-postgres/project %i detach" in text


def test_the_project_unit_does_not_restart_itself() -> None:
    """Docker's on-failure policy handles a crash without rotating a generation.

    Restart= here would re-run materialization on every crash and could rotate a
    secret generation nobody asked to rotate.
    """
    assert "Restart=no" in unit_text("agentic-postgres-project@.service")


def test_units_parse(tmp_path: Path) -> None:
    """`systemd-analyze verify` if it is available; a parse check otherwise.

    CI runners have systemd-analyze. A developer machine may not, and the check
    that matters -- that these are valid unit files -- should not be skipped
    silently when it is missing.
    """
    for name in UNITS:
        text = unit_text(name)
        assert text.startswith("[Unit]\n"), f"{name} does not begin with [Unit]"
        assert "\n[Service]\n" in text, f"{name} has no [Service] section"
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "[")):
                continue
            assert "=" in stripped, f"{name} has a directive with no value: {line!r}"


#: Errors `systemd-analyze verify` reports off-host that say nothing about
#: whether the unit is correct. Both are facts about the *machine running the
#: test*: this is not the deployment host, so Docker is not a unit here and the
#: launchers are not installed at their target path.
#:
#: Classified rather than tolerated by exit code. `verify` returns non-zero for
#: a genuine syntax error and for a missing dependency alike, so accepting any
#: non-zero would accept a unit that does not parse.
_EXPECTED_OFF_HOST = (
    re.compile(r"Unit \S+\.(service|target) not found"),
    re.compile(r"Command /usr/local/libexec/agentic-postgres/\S+ is not executable"),
)


def test_systemd_analyze_accepts_the_units() -> None:
    """The real check, run when the tool exists.

    Deliberately not skipped when the *dependencies* are absent -- only when the
    tool itself is. A unit that fails to parse must fail here on a developer
    machine, not first on the VPS.
    """
    if subprocess.run(["which", "systemd-analyze"], capture_output=True, check=False).returncode:
        pytest.skip("systemd-analyze is not installed on this machine")

    result = subprocess.run(
        ["systemd-analyze", "verify", *[str(SYSTEMD / name) for name in UNITS]],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if result.returncode == 0:
        return

    unexplained = [
        line
        for line in result.stderr.splitlines()
        if line.strip() and not any(pattern.search(line) for pattern in _EXPECTED_OFF_HOST)
    ]
    assert not unexplained, "systemd-analyze reported real problems:\n" + "\n".join(unexplained)


# ---------------------------------------------------------------------------
# Launchers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", LAUNCHERS)
def test_launchers_exist_and_are_executable_in_the_git_index(name: str) -> None:
    """Asserted against the git index, per plan decision Q.

    These are extensionless, so `bin/*.sh` globs miss them and editing one
    through the \\\\wsl$ share strips the bit invisibly.
    """
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", f"libexec/{name}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.startswith("100755 "), (
        f"libexec/{name} is not 100755 in the git index: {result.stdout.strip()!r}"
    )


@pytest.mark.parametrize("name", LAUNCHERS)
def test_launchers_are_strict_and_refuse_non_root(name: str) -> None:
    text = (LIBEXEC / name).read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text
    assert "id -u" in text and "must run as root" in text


@pytest.mark.parametrize("name", LAUNCHERS)
def test_launchers_validate_the_release_commit_before_using_it_as_a_path(
    name: str,
) -> None:
    """State is root-owned, but a corrupted value must still not select a path."""
    text = (LIBEXEC / name).read_text(encoding="utf-8")
    assert "[!0-9a-f]" in text, f"{name} does not validate the commit is hexadecimal"
    assert "-eq 40" in text, f"{name} does not validate the commit length"


@pytest.mark.parametrize("name", LAUNCHERS)
def test_launchers_refuse_symlinked_state_and_release_paths(name: str) -> None:
    """Runbook §7: scripts must refuse symlinked state and release paths."""
    text = (LIBEXEC / name).read_text(encoding="utf-8")
    assert text.count("is a symlink") >= 2, f"{name} does not refuse symlinks"


@pytest.mark.parametrize("name", LAUNCHERS)
def test_launchers_check_the_release_is_root_owned(name: str) -> None:
    """A release writable by anyone else changes what a root unit executes."""
    text = (LIBEXEC / name).read_text(encoding="utf-8")
    assert "expected root" in text


def test_the_project_launcher_validates_its_instance_name() -> None:
    """%i arrives through a filename, so it is operator input.

    Without validation, `systemctl start agentic-postgres-project@../../etc` is
    a question with an answer nobody wants.
    """
    text = (LIBEXEC / "agentic-postgres-project").read_text(encoding="utf-8")
    assert "PROJECT_KEY_PATTERN" in text
    assert "^[a-z][a-z0-9-]{4,47}$" in text
    assert "not a valid project key" in text


def test_launcher_names_match_the_paths_the_units_invoke() -> None:
    """`libexec/agentic-postgres-edge` installs as `.../agentic-postgres/edge`."""
    invoked = set()
    for name in UNITS:
        invoked.update(
            re.findall(r"/usr/local/libexec/agentic-postgres/([a-z-]+)", unit_text(name))
        )
    available = {name.removeprefix("agentic-postgres-") for name in LAUNCHERS}
    assert invoked <= available, f"units invoke launchers that do not exist: {invoked - available}"


# ---------------------------------------------------------------------------
# ADR 0037 — an installed launcher may resolve a release and nothing else
# ---------------------------------------------------------------------------
#
# One copy of each launcher serves every project on the host, including projects
# deployed through different releases, and until Run 8 the only thing that ever
# installed one was `bin/provision-host.sh`. So the copy that actually ran was
# whatever the host was built with: a launcher fixed in Run 7 was still passing
# `--session 2` to two Session 3 projects in Run 8 (D72).
#
# Two halves close it. The deploy now installs the launchers from the release,
# which is asserted in tests/contract/test_installed_release.py; and an installed
# launcher may no longer contain anything a release could change, which is what
# makes overwriting a shared file from one project's deploy safe. This block is
# the second half, and it is structural rather than textual on purpose -- the
# question is not whether the word "session" appears, it is whether the file can
# hold an answer that belongs to a release.


def test_the_project_trampoline_delegates_to_the_release() -> None:
    text = (LIBEXEC / "agentic-postgres-project").read_text(encoding="utf-8")
    assert 'readonly RELEASE_LAUNCHER="libexec/project-launcher"' in text
    assert 'exec "${launcher}" "$@"' in text


@pytest.mark.parametrize("name", LAUNCHERS)
def test_an_installed_launcher_holds_no_answer_a_release_owns(code_only, name: str) -> None:
    """The session, the profile set and the secret contract are release facts.

    Asserted over code with comments stripped, because the comment above each of
    these files explains exactly why they must not appear -- and a scan that
    counted the explanation as a violation would have to be weakened until it
    counted nothing.
    """
    source = code_only((LIBEXEC / name).read_text(encoding="utf-8"))
    for forbidden in ("--session", "--through-session", "--profile", "secrets.required.yaml"):
        assert forbidden not in source, (
            f"libexec/{name} names {forbidden}, which is a property of a release. "
            "One copy of this file serves projects deployed through releases it "
            "has never seen; it may resolve a release, not answer for one."
        )


def test_the_release_side_launcher_is_not_installed_anywhere() -> None:
    """`libexec/project-launcher` must never reach /usr/local/libexec.

    A copy outside a release would be a second answer to the question the split
    exists to have exactly one answer to. The prefix is what keeps it out, so the
    prefix is what is asserted -- in the installer and in the module the deploy
    calls, which are two different implementations of the same rule.
    """
    assert (LIBEXEC / "project-launcher").is_file()
    assert not (LIBEXEC / "project-launcher").name.startswith("agentic-postgres-")

    provision = (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")
    assert '"${ROOT_DIR}"/libexec/agentic-postgres-*' in provision

    from agentic_postgres import installed_release

    assert installed_release.LAUNCHER_PREFIX == "agentic-postgres-"
    installed = {
        path.name.removeprefix("agentic-postgres-") for path in LIBEXEC.glob("agentic-postgres-*")
    }
    assert "project-launcher" not in installed


def test_the_release_side_launcher_is_executable_in_the_git_index() -> None:
    """Extensionless, so `bin/*.sh` globs miss it and the \\\\wsl$ share strips
    the bit invisibly. The trampoline refuses a launcher that is not executable,
    which turns a stripped bit into a project that will not start at boot."""
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", "libexec/project-launcher"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.startswith("100755 "), (
        f"libexec/project-launcher is not 100755 in the git index: {result.stdout.strip()!r}"
    )


def test_the_release_side_launcher_reads_the_session_from_the_document() -> None:
    """What moved out of the trampoline has to have landed somewhere."""
    text = (LIBEXEC / "project-launcher").read_text(encoding="utf-8")
    assert ".deployed_through_session" in text
    assert "--through-session" in text
    assert '--session "${session}"' in text
    assert "set -euo pipefail" in text
    assert "must run as root" in text

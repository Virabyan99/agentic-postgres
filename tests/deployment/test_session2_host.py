"""Host baseline, ingress policy, and the Docker control plane, on a live host.

These are not placeholders. Each body is the real measurement; the module is
skipped in a checkout because ``APG_LIVE_HOST`` is unset, not because anything
here is unwritten. ``apply_environment_gate`` in ``tests/conftest.py`` explains
why that distinction is enforced rather than trusted.

Every assertion reads the state of the running host, never a template under
``infra/``. Those templates are already asserted offline by
``tests/contract/test_host_infrastructure.py``; re-reading them here would prove
the repository agrees with itself while the host did something else entirely.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres.host_config import EDGE_STACK_NAME
from agentic_postgres.listeners import parse_listeners

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST"),
]

# The ownership comment bin/docker-firewall.sh stamps on every rule it manages.
# Its default --tag; whether `iptables -S` renders it quoted varies, so both
# spellings are accepted where it is matched.
TAG = "agentic-postgres"

SSH_DIRECTIVES = [
    ("permitrootlogin", "no"),
    ("passwordauthentication", "no"),
    ("kbdinteractiveauthentication", "no"),
    ("pubkeyauthentication", "yes"),
    ("permitemptypasswords", "no"),
    ("x11forwarding", "no"),
    ("allowagentforwarding", "no"),
    ("permittunnel", "no"),
]


@pytest.fixture(scope="module")
def sshd_config(sh) -> dict[str, str]:
    """The configuration sshd actually resolved, not the file it was handed.

    ``sshd -T`` is the only honest source. OpenSSH takes the first obtained
    value across a lexicographic include order, so reading
    ``sshd_config.d/00-agentic-postgres.conf`` reports what we asked for rather
    than what won.
    """
    settings: dict[str, str] = {}
    for line in sh("sshd", "-T").splitlines():
        key, _, value = line.strip().partition(" ")
        if key:
            settings.setdefault(key.lower(), value)
    return settings


# ---------------------------------------------------------------------------
# SEC-HOST-001 — the host baseline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("directive", "expected"), SSH_DIRECTIVES)
def test_sshd_resolved_the_expected_policy(
    sshd_config: dict[str, str], directive: str, expected: str
) -> None:
    assert directive in sshd_config, f"{directive} is not reported by this OpenSSH build"
    assert sshd_config[directive] == expected, (
        f"sshd resolved {directive}={sshd_config[directive]!r}, expected {expected!r}; "
        "an earlier include is winning"
    )


def test_sshd_limits_authentication_attempts(sshd_config: dict[str, str]) -> None:
    assert int(sshd_config["maxauthtries"]) <= 3, sshd_config["maxauthtries"]


def test_password_authentication_is_refused_in_practice(sshd_config, sh_status) -> None:
    """Guard the guard: a resolved directive is a claim, a refused login is proof.

    With ``0.0.0.0/0`` as the accepted source CIDR, key-only authentication is
    the SSH boundary rather than one layer of it, so it is worth proving by
    attempting the thing that must fail.
    """
    code, _, stderr = sh_status(
        "ssh",
        "-p",
        sshd_config["port"],
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "PreferredAuthentications=password,keyboard-interactive",
        "-o",
        "ConnectTimeout=10",
        "nonexistent-operator@127.0.0.1",
        "true",
    )
    assert code != 0, "a password-only SSH attempt succeeded"
    lowered = stderr.lower()
    assert "permission denied" in lowered or "no supported authentication" in lowered, stderr


def test_unattended_upgrades_is_enabled_and_does_not_reboot(sh, sh_status) -> None:
    code, stdout, _ = sh_status("systemctl", "is-enabled", "unattended-upgrades.service")
    assert code == 0 and stdout.strip() == "enabled", stdout

    config = sh("apt-config", "dump")
    assert 'APT::Periodic::Unattended-Upgrade "1"' in config, (
        "unattended upgrades are not scheduled"
    )
    assert 'Unattended-Upgrade::Automatic-Reboot "true"' not in config, (
        "the host reboots itself; Session 2 requires a reboot to be a decision"
    )


def test_only_ssh_and_the_edge_listen_on_a_public_address(sshd_config: dict[str, str], sh) -> None:
    """Anything else listening publicly is an ingress path nothing accounts for.

    Parsed by ``agentic_postgres.listeners``, the same code
    ``bin/provision-host.sh --check`` uses. This module had its own
    implementation, which read a fixed column index and classified loopback by
    string prefix; two parsers for one question is two chances to disagree about
    what "public" means, and they did.

    UDP/68 is permitted by name. The DHCP client genuinely binds the public
    interface, and it is how this host holds its address — but allowing it is a
    decision, not a rounding error, so it is written down rather than absorbed by
    ignoring UDP altogether. Ignoring UDP wholesale would hide a real UDP
    service the day one appears.
    """
    allowed = {("tcp", int(sshd_config["port"])), ("tcp", 80), ("tcp", 443), ("udp", 68)}

    offenders = [
        listener
        for listener in parse_listeners(sh("ss", "-H", "-lntup"))
        if not listener.is_loopback and (listener.protocol, listener.port) not in allowed
    ]
    assert not offenders, "unexpected public listeners:\n" + "\n".join(
        f"  {item.protocol}/{item.port} on {item.address}" for item in offenders
    )


# ---------------------------------------------------------------------------
# SEC-NET-002 — nothing but the edge is forwarded
# ---------------------------------------------------------------------------


def test_only_the_edge_publishes_container_ports(running_containers: list[dict[str, Any]]) -> None:
    offenders = [
        (container["Names"], container.get("Ports", ""))
        for container in running_containers
        if "->" in (container.get("Ports") or "")
        and not container["Names"].startswith(EDGE_STACK_NAME)
    ]
    assert not offenders, f"non-edge containers publish host ports: {offenders}"


@pytest.mark.requires_environment("APG_EDGE_DEPLOYED")
def test_the_edge_publishes_exactly_eighty_and_four_four_three(
    running_containers: list[dict[str, Any]],
) -> None:
    published: set[int] = set()
    for container in running_containers:
        if not container["Names"].startswith(EDGE_STACK_NAME):
            continue
        published.update(
            int(match) for match in re.findall(r":(\d+)->", container.get("Ports") or "")
        )
    assert published == {80, 443}, f"the edge publishes {sorted(published)}"


@pytest.mark.parametrize("command", ["iptables", "ip6tables"])
def test_the_docker_user_chain_ends_in_a_drop(as_root, sh, command: str) -> None:
    del as_root
    rules = [line.strip() for line in sh(command, "-S", "DOCKER-USER").splitlines()]
    assert rules, f"{command} DOCKER-USER is empty"
    assert any(rule.startswith("-A DOCKER-USER") and rule.endswith("-j DROP") for rule in rules), (
        f"{command} DOCKER-USER has no default drop:\n" + "\n".join(rules)
    )


@pytest.mark.parametrize("command", ["iptables", "ip6tables"])
def test_the_docker_user_chain_matches_the_original_destination_port(
    as_root, sh, command: str
) -> None:
    """``--dport`` here would match the container port, not the published one.

    DNAT has already rewritten the destination by the time a packet reaches
    FORWARD, so a policy written with ``--dport 80`` permits nothing it means to
    permit while reading correctly. The matcher itself is the assertion.
    """
    del as_root
    rules = sh(command, "-S", "DOCKER-USER")
    assert "--ctorigdstport" in rules, (
        f"{command} DOCKER-USER does not match the pre-DNAT destination port:\n{rules}"
    )


@pytest.mark.parametrize(
    ("command", "installed"),
    [("iptables", "docker-user-rules.v4"), ("ip6tables", "docker-user-rules.v6")],
)
def test_the_live_policy_is_the_installed_policy(as_root, sh, command: str, installed: str) -> None:
    """The chain in the kernel matches the file the unit reconciles from.

    Read-only on purpose. Restarting the reconciliation unit would prove
    idempotence more directly, but a verification pass that mutates the system
    it measures cannot be re-run to confirm a fix — which is the objection this
    plan raised to the runbook's deploying gate, and it applies here too.
    """
    del as_root
    expected = [
        line.strip()
        for line in Path(f"/etc/agentic-postgres/{installed}")
        .read_text(encoding="utf-8")
        .split("\n")
        if line.strip() and not line.strip().startswith("#")
    ]
    live = [line.strip() for line in sh(command, "-S", "DOCKER-USER").splitlines()]

    # Neither equality nor a suffix match. `-S` prefixes every rule with
    # `-A DOCKER-USER`, and iptables prints matches in its own canonical order
    # rather than the order they were given — so the ownership comment, passed
    # first on the command line, comes back sitting just before the `-j`. A
    # rendered spec is therefore neither equal to a live rule nor the tail of
    # one; it is what remains after the comment match is taken out.
    #
    # This is the second wrong comparison here. The first assumed set equality
    # and could never have passed; the second assumed argument order survives
    # iptables, and failed against a chain that was completely correct. Both
    # would have been caught by looking at one line of real `-S` output.
    def without_ownership(rule: str) -> str:
        return re.sub(rf'\s-m comment --comment "?{re.escape(TAG)}"?', "", rule)

    normalised = [without_ownership(rule) for rule in live]
    ours = [rule for rule in live if without_ownership(rule) != rule]

    missing = [spec for spec in expected if f"-A DOCKER-USER {spec}" not in normalised]
    assert not missing, (
        f"installed rules absent from the running {command} chain: {missing}\n"
        f"live chain:\n" + "\n".join(live)
    )

    assert len(ours) == len(expected), (
        f"{command} DOCKER-USER carries {len(ours)} tagged rules for {len(expected)} rendered "
        f"ones; reconciliation is accumulating or dropping rules:\n" + "\n".join(ours)
    )

    # Order decides the policy. The established-traffic RETURN has to precede
    # the port RETURNs, and every one of them has to precede the DROP.
    positions = [normalised.index(f"-A DOCKER-USER {spec}") for spec in expected]
    assert positions == sorted(positions), (
        f"{command} DOCKER-USER applies the rendered rules out of order:\n" + "\n".join(live)
    )


@pytest.mark.parametrize("command", ["iptables", "ip6tables"])
def test_the_docker_user_chain_is_reachable_from_forward(as_root, sh, command: str) -> None:
    """A chain nothing jumps to is a policy that is not enforcing.

    `iptables -S DOCKER-USER` looks identical whether or not FORWARD references
    the chain, so this is invisible in every other check here.
    """
    del as_root
    forward = sh(command, "-S", "FORWARD")
    assert "-j DOCKER-USER" in forward, (
        f"{command} FORWARD does not jump to DOCKER-USER; the policy is inert:\n{forward}"
    )


def test_ufw_denies_incoming_by_default(as_root, sh) -> None:
    del as_root
    status = sh("ufw", "status", "verbose")
    assert "Status: active" in status, status
    assert re.search(r"Default:\s+deny \(incoming\)", status), status


# ---------------------------------------------------------------------------
# SEC-DOCKER-001 — the Docker control plane
# ---------------------------------------------------------------------------


def test_the_daemon_exposes_no_tcp_socket(sh) -> None:
    offenders = [
        line.strip()
        for line in sh("ss", "-H", "-lntp").splitlines()
        if re.search(r":(2375|2376)\s", line)
    ]
    assert not offenders, f"the Docker daemon is listening on TCP: {offenders}"


def test_the_daemon_runs_the_configuration_we_installed(as_root, sh) -> None:
    del as_root
    info = json.loads(sh("docker", "info", "--format", "{{json .}}"))
    assert info["LiveRestoreEnabled"] is True, (
        "live-restore is off; a daemon restart kills projects"
    )
    assert info.get("Debug") is False


@pytest.mark.requires_environment("APG_EDGE_DEPLOYED")
def test_traefik_holds_no_docker_socket(
    as_root, sh, running_containers: list[dict[str, Any]]
) -> None:
    del as_root
    traefik = [c for c in running_containers if "traefik" in c["Names"]]
    assert traefik, "no Traefik container is running"
    for container in traefik:
        mounts = json.loads(
            sh("docker", "inspect", "--format", "{{json .Mounts}}", container["ID"])
        )
        sockets = [m["Source"] for m in mounts if m["Source"].endswith("docker.sock")]
        assert not sockets, f"{container['Names']} mounts the Docker socket directly: {sockets}"


@pytest.mark.requires_environment("APG_EDGE_DEPLOYED")
def test_the_socket_proxy_refuses_a_write_call(as_root, sh_status, probe_image: str) -> None:
    """An allowlist is a claim until something is refused by it.

    The permitted read and the refused write run from the same client on the
    same network, so a failure to reach the proxy at all cannot be mistaken for
    a successful denial.
    """
    del as_root
    network = f"{EDGE_STACK_NAME}_control"
    script = (
        "import urllib.request,urllib.error,sys\n"
        "def code(url, method):\n"
        "    req = urllib.request.Request(url, method=method)\n"
        "    try:\n"
        "        return urllib.request.urlopen(req, timeout=10).status\n"
        "    except urllib.error.HTTPError as exc:\n"
        "        return exc.code\n"
        "base = 'http://docker-socket-proxy:2375'\n"
        "print(code(base + '/containers/json', 'GET'), "
        "code(base + '/containers/create', 'POST'))\n"
    )
    exit_code, stdout, stderr = sh_status(
        "docker", "run", "--rm", "--network", network, probe_image, "python", "-c", script
    )
    assert exit_code == 0, stdout + stderr

    read_status, write_status = (int(value) for value in stdout.split())
    assert read_status == 200, f"the proxy refused a permitted read: {read_status}"
    assert write_status == 403, f"the proxy answered a container-create with {write_status}"


# ---------------------------------------------------------------------------
# DEP-PROV-001 — ownership is recorded by ID, and convergence is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.requires_environment("APG_PROJECT_A_OUTPUTS")
def test_bootstrap_state_is_root_only_and_records_provider_ids(
    as_root, project_a: dict[str, Any]
) -> None:
    del as_root
    state_path = Path(project_a["bootstrap"]["state_path"])
    assert state_path.is_file(), f"{state_path} does not exist"
    mode = oct(state_path.stat().st_mode & 0o777)
    assert mode == "0o600", mode
    assert state_path.stat().st_uid == 0

    state = json.loads(state_path.read_text(encoding="utf-8"))
    for field in ("infisical_project_id", "runtime_identity_id"):
        assert state.get(field), f"{field} is unrecorded; ownership would be adopted by name"


@pytest.mark.requires_environment("APG_PROJECT_A_OUTPUTS")
def test_reapplying_the_bootstrap_reports_no_change(
    as_root, sh_status, project_a: dict[str, Any]
) -> None:
    """Convergence, proved by a second plan finding nothing to do.

    The manifest comes from the project's state directory, not from the release.
    A release is a pristine copy of the repository and has never contained a
    `project.yaml`; the operator's manifest is copied to
    `<state>/manifest.yaml` by the deploy, which is the copy that outlives the
    operator's checkout. This test named a path nothing creates, so it failed
    with `project manifest not found` on a converged bootstrap.
    """
    del as_root
    release = Path(project_a["runtime"]["release_path"])
    state = Path(project_a["runtime"]["state_directory"])
    code, stdout, stderr = sh_status(
        str(release / "bin" / "bootstrap-providers.sh"),
        "--host",
        "/etc/agentic-postgres/host.yaml",
        "--project",
        str(state / "manifest.yaml"),
        "--plan",
    )
    assert code == 0, stdout + stderr
    assert "no changes" in stdout.lower(), f"a second plan proposes work:\n{stdout}"


# ---------------------------------------------------------------------------
# CFG-016 — the deployed document describes the host truthfully
# ---------------------------------------------------------------------------


@pytest.mark.requires_environment("APG_PROJECT_A_OUTPUTS")
def test_the_deployed_document_is_owner_only() -> None:
    path = Path(os.environ["APG_PROJECT_A_OUTPUTS"])
    mode = oct(path.stat().st_mode & 0o777)
    assert mode == "0o600", mode


@pytest.mark.requires_environment("APG_PROJECT_A_OUTPUTS")
def test_the_deployed_document_names_the_release_that_is_running(
    project_a: dict[str, Any],
) -> None:
    release = Path(project_a["runtime"]["release_path"])
    assert release.is_dir(), f"{release} is not installed"
    assert release.stat().st_uid == 0, "the installed release is not root-owned"
    assert project_a["source_commit"] == release.name, (
        f"the document claims commit {project_a['source_commit']} but runs from {release.name}"
    )


@pytest.mark.requires_environment("APG_PROJECT_A_OUTPUTS")
def test_the_deployed_host_facts_are_real(project_a: dict[str, Any], sh) -> None:
    host = project_a["host"]
    ipaddress.ip_address(host["public_ipv4"])
    if host["public_ipv6"] is not None:
        ipaddress.ip_address(host["public_ipv6"])

    configured = sh("ip", "-json", "addr", "show")
    assert host["public_ipv4"] in configured, (
        f"{host['public_ipv4']} is not configured on this host"
    )

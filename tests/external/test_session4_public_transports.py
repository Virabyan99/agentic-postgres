"""What the public internet can reach, and what the helper can.

SEC-DBX-001, DBX-005, DX-DB-001 and DX-DB-002.

Run from a network that is not the deployment host. That separation is the whole
point and it is not a formality: a scan run *on* the host traverses loopback and
the host's own routing table, so it reports "closed" for ports the world can
reach and "open" for ports only the host can. Neither answer is about the public
boundary, and ADR 0040's entire content is that a loopback publication and a
public port are different things.

The two helper tests here are the other reason this module is off-host.
``bin/connect.sh`` is a developer's program: it reaches the host over SSH and
asks a privileged broker for a credential. Running it on the host would exercise
neither the transport nor the ``sudo -n`` rule.

**Every test states what would have to break for it to go red**, because every
test here is deselected in an offline gate and D70 is what an unmanaged
deselected test costs.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_PUBLIC_IPV4", "APG_PROJECT_A_OUTPUTS"),
]

CONNECT = str(REPO_ROOT / "bin" / "connect.sh")
CONNECT_TIMEOUT = 5.0


def port_is_open(host: str, port: int, family: int = socket.AF_INET) -> bool:
    """Full TCP connect, not a SYN probe.

    A half-open scan reports what a firewall did to a SYN. A completed
    three-way handshake reports that something is listening and willing to talk,
    which is the claim under test.
    """
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.settimeout(CONNECT_TIMEOUT)
            return probe.connect_ex((host, port)) == 0
    except OSError:
        return False


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def public_ipv4() -> str:
    return os.environ["APG_PUBLIC_IPV4"]


@pytest.fixture(scope="module")
def allocated_ports(project_a: dict[str, Any]) -> dict[str, int]:
    """The two published ports, taken from the deployed document.

    Read from the document rather than from a constant, because the whole point
    of an allocation is that the numbers are not known in advance. A test that
    scanned a fixed pair would keep passing after an allocation moved, and would
    be scanning ports nothing had ever published.
    """
    ports = {
        "pooled": project_a["database"]["pooled"]["port"],
        "direct": project_a["database"]["direct"]["port"],
    }
    for transport, port in ports.items():
        assert isinstance(port, int), (
            f"the deployed document reports no {transport} port; this project has not "
            "published its transports, so there is nothing here to prove closed"
        )
    return ports


# ---------------------------------------------------------------------------
# SEC-DBX-001 and DBX-005 — a loopback publication is not a public port
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("transport", ["pooled", "direct"])
def test_neither_transport_is_reachable_from_a_non_loopback_address(
    public_ipv4: str, allocated_ports: dict[str, int], transport: str
) -> None:
    """SEC-DBX-001. The negative half of ADR 0040, measured from outside.

    Not satisfied by the model-side check that every publication carries a
    loopback ``host_ip``: that proves what was configured. This proves what is
    reachable, and the two have differed before.

    Goes red if: a publication is written with ``0.0.0.0``, ``::`` or a public
    interface address; the Docker publish path bypasses the ``DOCKER-USER``
    rules; or a firewall change opens the allocated range. Parametrized so a
    failure names which transport leaked.
    """
    port = allocated_ports[transport]
    assert not port_is_open(public_ipv4, port), (
        f"{public_ipv4}:{port} accepted a connection from off-host: the {transport} "
        "transport is published to the world"
    )


def test_the_direct_endpoint_is_not_publicly_reachable(
    public_ipv4: str, allocated_ports: dict[str, int]
) -> None:
    """DBX-005, and the positive control that makes it mean something.

    443 is asserted **open** from the same place, in the same run. Without it a
    scan from a network that cannot route to the host at all would report every
    port closed and this would pass while measuring nothing — which is the exact
    shape of a false green this project has produced before.

    Goes red if: the direct PostgreSQL port becomes reachable from off-host; or
    if 443 stops answering, in which case the negative result is untrustworthy
    and the test says so rather than passing.
    """
    assert port_is_open(public_ipv4, 443), (
        f"443 is closed at {public_ipv4}, so this scanner cannot reach the host at all "
        "and every 'closed' result below is meaningless"
    )
    assert not port_is_open(public_ipv4, allocated_ports["direct"]), (
        f"the direct PostgreSQL endpoint is reachable at {public_ipv4}:{allocated_ports['direct']}"
    )
    # 5432 as well: the container port, in case a publication were ever written
    # without going through the allocator.
    assert not port_is_open(public_ipv4, 5432)


# ---------------------------------------------------------------------------
# DX-DB-001 and DX-DB-002 — the helper and the broker, over SSH
# ---------------------------------------------------------------------------


def connect(*arguments: str):
    return subprocess.run(
        [CONNECT, *arguments], capture_output=True, text=True, check=False, timeout=120
    )


#: The installed trampoline. Named by the same fixed path the sudoers rule names
#: and `bin/connect.sh` invokes -- a third spelling here would be a third thing
#: that has to agree.
BROKER = "/usr/local/libexec/agentic-postgres/database-access"


def broker(destination: str, project_key: str, operation: str, profile: str):
    """One enumerated broker operation, over SSH, as the developer's account.

    Invoked directly rather than through `bin/connect.sh`, because what is under
    test is the broker's answer and the helper would translate it. Host-key
    verification stays on: a tunnel to an unverified host is a private channel
    to somebody.
    """
    return subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            destination,
            "--",
            "sudo",
            "-n",
            BROKER,
            project_key,
            operation,
            profile,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


@pytest.mark.requires_environment("APG_PUBLIC_IPV4", "APG_PROJECT_A_OUTPUTS", "APG_SSH_DESTINATION")
def test_the_connection_helper_opens_and_cleans_a_verified_tunnel(project_a) -> None:
    """DX-DB-001. A verified tunnel, and no credential anywhere in the output.

    The whole lifecycle, in order, because each step's failure looks like the
    next step's: open, observe it live, read an environment out of it, close it,
    and observe that it is gone.

    Goes red if: the forward does not come up, which ``ExitOnForwardFailure``
    turns into a failed command rather than a connected session with no forward;
    ``status`` reports a tunnel that is not running; ``print-env`` emits a
    password or a URL carrying one; or ``stop`` leaves the record behind, which
    would mean the next run reuses a record for a process that no longer exists.
    """
    destination = os.environ["APG_SSH_DESTINATION"]
    project_key = project_a["project"]["key"]

    opened = connect(
        "tunnel", "--project", project_key, "--profile", "runtime_direct", "--ssh", destination
    )
    assert opened.returncode == 0, f"tunnel failed: {opened.stderr}"
    try:
        assert "is forwarded to 127.0.0.1:" in opened.stdout

        status = connect("status", "--project", project_key)
        assert status.returncode == 0
        assert "live" in status.stdout, f"the tunnel is not reported live:\n{status.stdout}"

        printed = connect("print-env", "--project", project_key, "--profile", "runtime_direct")
        assert printed.returncode == 0, printed.stderr
        assert "PGHOST=127.0.0.1" in printed.stdout
        assert "DATABASE_URL=postgresql://" in printed.stdout

        # No credential, stated three ways: no password variable, no userinfo
        # password in the URL, and no PGPASSFILE that a reader could then cat.
        assert "PGPASSWORD" not in printed.stdout + printed.stderr
        url = next(line for line in printed.stdout.splitlines() if line.startswith("DATABASE_URL="))
        assert ":" not in url.split("//", 1)[1].split("@", 1)[0], (
            f"the printed URL carries a password: {url}"
        )
    finally:
        stopped = connect("stop", "--project", project_key, "--profile", "runtime_direct")

    assert stopped.returncode == 0, f"stop failed: {stopped.stderr}"
    after = connect("status", "--project", project_key)
    assert "live" not in after.stdout, f"a tunnel survived stop:\n{after.stdout}"


@pytest.mark.requires_environment("APG_PUBLIC_IPV4", "APG_PROJECT_A_OUTPUTS", "APG_SSH_DESTINATION")
def test_the_access_broker_returns_nothing_to_an_unauthorized_caller(project_a) -> None:
    """DX-DB-002. Refused, and told nothing by the refusal.

    Asked for a profile the policy does not grant this account. The refusal must
    be exit ``6`` with a message naming neither the project nor the profile —
    and, past the trampoline, identical to the refusal for a project that does
    not exist. That identity is what stops an authorized-to-invoke caller
    enumerating other people's projects by exit code.

    The amendment ADR 0043 took on acceptance is why the *trampoline's* failures
    are excluded from this: it has to read the deployed document to find the
    release the policy lives in, so a project with no document exits 4 there,
    before any policy exists to consult. Sudo is the coarse gate; this test is
    about the fine one.

    Goes red if: the policy stops being consulted; the broker starts answering
    for a profile it was not granted; or a refusal begins naming what was asked
    for. It would NOT go red if the policy simply granted everything, so the
    positive control runs first: a granted profile answers.
    """
    destination = os.environ["APG_SSH_DESTINATION"]
    project_key = project_a["project"]["key"]

    # The positive control, first and against the same path. Without it, a
    # broker that refused everything -- a missing policy file, a trampoline that
    # cannot resolve its release -- would satisfy every assertion below.
    granted = broker(destination, project_key, "endpoint", "runtime_direct")
    assert granted.returncode == 0, (
        f"the granted profile was not answered ({granted.returncode}): "
        f"{granted.stderr.strip()}. Every refusal below would then prove nothing."
    )
    answer = json.loads(granted.stdout)
    assert answer["profile"] == "runtime_direct"
    assert "password" not in granted.stdout.lower(), "the endpoint answer carries a credential"

    refused = broker(destination, project_key, "endpoint", "migration_direct")
    assert refused.returncode == 6, (
        f"expected 6 (refused), got {refused.returncode}. "
        f"stdout: {refused.stdout!r} stderr: {refused.stderr!r}"
    )
    assert refused.stdout.strip() == "", "a refused caller was told something on stdout"
    assert project_key not in refused.stderr, "the refusal names the project"
    assert "migration_direct" not in refused.stderr, "the refusal names the profile"

    absent = broker(destination, "no-such-project-here", "endpoint", "runtime_direct")
    # The trampoline answers this one, so it is 4 rather than 6 -- see the
    # amendment referenced above. What is asserted is that it, too, hands back
    # nothing on stdout: a caller learns that a project key is not deployed, and
    # nothing about any project that is.
    assert absent.stdout.strip() == ""
    assert absent.returncode != 0

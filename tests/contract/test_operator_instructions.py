"""Commands a script tells an operator to run must work where they will run them.

``provision-host.sh`` prints the command that disarms a rollback timer. It
printed it as ``sudo bin/provision-host.sh …`` — a relative path, which fails
with ``command not found`` from anywhere but the checkout.

That is not a cosmetic complaint. The operator reads that line immediately after
opening a *new* session to verify the change, so they are in their home
directory by construction, and they are reading it during a ten-minute countdown
after which the rollback fires. It failed exactly that way on the deployment
host: three attempts, all ``command not found``, with the timer running.

Pulling on it found the real defect. ``--host`` was validated against the
caller's working directory and then read after ``main`` had ``cd``'d to the
checkout, so a relative ``--host host.yaml`` from another directory validates one
file and provisions from another — silently, if the checkout happens to have one.
"""

from __future__ import annotations

import re

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "provision-host.sh"


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_printed_commands_do_not_use_a_relative_script_path(source: str) -> None:
    """`sudo bin/…` only works from the checkout. The reader is rarely there."""
    offenders = [
        line.strip() for line in source.splitlines() if re.search(r"(note|printf).*sudo bin/", line)
    ]
    assert not offenders, "an operator instruction names a relative script path:\n" + "\n".join(
        offenders
    )


def test_the_disarm_instructions_are_printed_as_absolute_paths(source: str) -> None:
    for flag in ("--confirm-ssh-ok", "--confirm-firewall-ok"):
        instruction = next(
            (line for line in source.splitlines() if "Then run:" in line and flag in line), None
        )
        assert instruction is not None, f"nothing tells the operator how to run {flag}"
        assert "${ROOT_DIR}/bin/provision-host.sh" in instruction, (
            f"the {flag} instruction is not an absolute path: {instruction.strip()}"
        )


def test_the_host_manifest_is_resolved_before_the_working_directory_changes(source: str) -> None:
    """Otherwise --host is validated against one file and read from another."""
    assert 'readlink -f -- "${HOST_MANIFEST}"' in source, (
        "the host manifest path is never made absolute"
    )
    resolve = source.index('readlink -f -- "${HOST_MANIFEST}"')
    change_directory = source.index('cd "${ROOT_DIR}"')
    assert resolve < change_directory, (
        "the manifest is resolved after the working directory changes, which is too late"
    )


def test_the_manifest_is_resolved_inside_argument_parsing(source: str) -> None:
    """The only place the caller's directory is still known."""
    parse_body = source.split("parse_arguments()", 1)[1].split("\n}", 1)[0]
    assert "readlink -f" in parse_body

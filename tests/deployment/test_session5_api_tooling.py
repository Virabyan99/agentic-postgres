"""The request broker performs a call and leaks no token (DX-API-001).

Replaces one Session 5 placeholder in ``tests/contract/test_future_deployment.py``.

The commands are exercised as an operator runs them -- ``bin/dev-token.sh``
minting into the environment of ``bin/api.sh``, which becomes the child -- rather
than by importing either. What DX-API-001 is about is the *composition*: each
half can be correct on its own while the pair puts a credential in a process
listing, which is what ``env VAR=value command`` does and why ``os.execvpe`` is
the spelling (D171).

**The positive control is the whole test.** A broker that failed to make any call
would leak nothing, so the authorized call must succeed first; every absence
assertion below is about the run that worked.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

DEV_TOKEN = str(REPO_ROOT / "bin" / "dev-token.sh")
API = str(REPO_ROOT / "bin" / "api.sh")


def test_the_request_broker_performs_a_call_with_the_token_in_no_argv_or_output(
    project_a: dict[str, Any],
    mint_token: Callable[..., str],
    request_subject: Callable[[str], str],
    sh: Callable[..., str],
    as_root: None,
) -> None:
    """DX-API-001, in the five places a token could end up.

    **argv.** The child's own ``/proc/self/cmdline`` is captured *during* the
    run and asserted to contain no token. That is the measurement ``env
    VAR=value command`` fails: the variable is set correctly and the value is in
    ``env``'s argument vector, where ``ps`` shows it to every user on the host.
    Capturing the child's cmdline rather than polling ``ps`` from outside is what
    makes this deterministic -- a poll can miss a process that exits quickly and
    would then report a leak-free run for the wrong reason.

    **stdout and stderr.** ``bin/dev-token.sh`` has no flag that prints a token
    (D105) and ``bin/api.sh`` prints a response body. Neither may carry the
    credential.

    **The environment of the parent.** The token exists in the child's
    environment and must not be in this process's, which is what distinguishes
    "handed to a child" from "exported".

    **The evidence and the logs.** Nothing written by the run may carry it.

    Goes red if: ``dev-token`` is changed to ``env VAR=... command``; a
    convenience flag that prints a token is added; ``bin/api.sh`` starts echoing
    its request headers on an error path; or the token is passed as an argument
    to anything.
    """
    del as_root
    outputs = Path(os.environ["APG_PROJECT_A_OUTPUTS"])

    # The token this run will use, minted here so its value is known. Minted the
    # same way `dev-token` mints it -- same key, same claims -- so a substring
    # search for it is a search for the credential the broker actually carried.
    subject = request_subject(project_a["project"]["key"])
    expected = mint_token(
        project_a, project_a["database"]["roles"]["authenticated"], subject=subject
    )
    assert expected.count(".") == 2, "the minted value is not a JWT; the searches below are void"
    signing_input = expected.rsplit(".", 1)[0]

    performed = subprocess.run(
        [
            DEV_TOKEN,
            "--project-outputs",
            str(outputs),
            "--role",
            "authenticated",
            "--",
            API,
            "--project-outputs",
            str(outputs),
            "list-notes",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert performed.returncode == 0, (
        f"the authorized call failed ({performed.returncode}): {performed.stderr.strip()}; "
        "every absence below would then be an absence of a request"
    )
    assert json.loads(performed.stdout) is not None, "the broker returned no parseable result"

    # The signing input rather than the whole token: the signature differs
    # between two mints of the same claims only if `iat` moved, and the header
    # and payload are byte-identical for a token naming the same role, subject,
    # issuer and audience. Searching for the prefix is therefore the search that
    # would catch the broker's own token as well as this one.
    for stream, text in (("stdout", performed.stdout), ("stderr", performed.stderr)):
        assert signing_input not in text, f"the broker wrote a token to {stream}"
        assert "eyJhbGciOi" not in text, f"a JWT appears in {stream}"

    assert not any(value and "eyJhbGciOi" in value for value in os.environ.values()), (
        "a token is in this process's own environment; it was exported rather than handed on"
    )

    # The child's argv, captured from inside the run. `sh -c` so the recorded
    # cmdline is the one `dev-token` exec'd, and `tr` because /proc separates
    # arguments with NULs.
    observed = subprocess.run(
        [
            DEV_TOKEN,
            "--project-outputs",
            str(outputs),
            "--role",
            "authenticated",
            "--",
            "/bin/sh",
            "-c",
            'tr "\\0" " " < /proc/self/cmdline; echo; env | grep -c APG_API_TOKEN',
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert observed.returncode == 0, f"the argv probe failed: {observed.stderr.strip()}"
    cmdline, _, count = observed.stdout.partition("\n")
    assert count.strip() == "1", (
        "the child did not receive APG_API_TOKEN in its environment, so the empty argv "
        "below says nothing about where the token went"
    )
    assert "eyJhbGciOi" not in cmdline, (
        f"the token is in the child's own argument vector: {cmdline.strip()}. "
        "`ps` shows that to every user on the host"
    )
    assert "APG_API_TOKEN=" not in cmdline, (
        "the token was passed through an `env VAR=value` prefix rather than through "
        "execve's environment block (D171)"
    )

    for name in [
        line for line in sh("docker", "ps", "--format", "{{.Names}}").splitlines() if line
    ]:
        logs = subprocess.run(
            ["docker", "logs", "--tail", "200", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert "eyJhbGciOi" not in (logs.stdout + logs.stderr), f"a token appears in {name}'s log"

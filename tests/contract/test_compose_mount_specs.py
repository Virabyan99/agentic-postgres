"""Every mount spec in `compose.yaml` is one Docker will accept.

**Found on the host, on the deploy that finally reached the auth container**
(D287). The service declared

    tmpfs: [/tmp:rw,mode=0700,uid=65532,gid=65532]

and Docker refused it with

    invalid mount path: 'gid=65532' mount path must be absolute

because that is a YAML **flow sequence**, where commas separate items. It parses
as four entries -- `/tmp:rw`, `mode=0700`, `uid=65532`, `gid=65532` -- and the
last three are read as mount paths. `pgbouncer` writes the same options as a
block sequence, where commas are literal, and has worked since Session 4.

Five services carried the flow form: `auth` and the four `client-*` fixtures.
The client fixtures never failed because the rigs launch them with `docker run`
and translated flags, never through Compose -- so the one service that Compose
actually starts was the one nobody had started.

**`docker compose config` does not catch this**, which is why the offline gate
did not. The document is valid YAML and valid Compose: `tmpfs` is a list of
strings, and four strings are as acceptable as one. Only the daemon rejects it,
at container-create time, on a host. So the check has to be on the *meaning* of
the parsed value rather than on the document validating.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

COMPOSE = REPO_ROOT / "compose.yaml"


@pytest.fixture(scope="module")
def services() -> dict[str, Any]:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert document.get("services"), "compose.yaml declares no services"
    return document["services"]


def test_every_tmpfs_entry_is_an_absolute_path(services: dict[str, Any]) -> None:
    """The defect, stated as the property Docker enforces.

    Goes red if a `tmpfs` list is written as a flow sequence with options, which
    is the only way this repository has produced a non-path entry.
    """
    offenders: dict[str, list[str]] = {}
    for name, service in services.items():
        entries = service.get("tmpfs") or []
        if isinstance(entries, str):
            entries = [entries]
        wrong = [entry for entry in entries if not entry.startswith("/")]
        if wrong:
            offenders[name] = wrong

    assert not offenders, (
        f"these services declare a tmpfs entry that is not an absolute path: {offenders}. "
        "In a YAML flow sequence -- tmpfs: [/tmp:rw,mode=0700] -- the commas separate "
        "ITEMS, so the options become mount paths and Docker refuses the container with "
        "`invalid mount path`. Write it as a block sequence, as pgbouncer does."
    )


def test_a_tmpfs_carrying_options_is_written_as_a_block_sequence(services: dict[str, Any]) -> None:
    """The narrower, structural half.

    The test above is the property; this one names the shape that violates it,
    so a reader who trips it is told what to write rather than only what is
    wrong. Checked against the source text because the parsed document cannot
    distinguish a flow sequence from a block one -- by then the damage is done
    and, for a single-entry list with no comma, invisible.
    """
    del services
    offenders = [
        line.strip()
        for line in COMPOSE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("tmpfs:") and "[" in line and "," in line
    ]
    assert not offenders, (
        f"a tmpfs flow sequence carries options: {offenders}. The commas separate items "
        "here, not mount options"
    )


def test_every_volume_and_secret_target_is_absolute(services: dict[str, Any]) -> None:
    """The same class, in the two other places a path reaches the daemon.

    Written because the defect was not really about `tmpfs`: it was about a
    string this repository composes being handed to a parser with its own idea
    of what a comma means. `volumes:` in the short form and `secrets:` targets
    are the other two, and both are refused by the daemon rather than by
    `compose config`.
    """
    offenders: dict[str, list[str]] = {}
    for name, service in services.items():
        wrong: list[str] = []
        for entry in service.get("volumes") or []:
            if isinstance(entry, str):
                parts = entry.split(":")
                # A named volume or a path, then the container path. An
                # interpolation is left alone: its value arrives at deploy time.
                if len(parts) >= 2 and not parts[1].startswith(("/", "$")):
                    wrong.append(entry)
            elif isinstance(entry, dict) and not str(entry.get("target", "/")).startswith("/"):
                wrong.append(str(entry))
        for entry in service.get("secrets") or []:
            if isinstance(entry, dict):
                target = str(entry.get("target", ""))
                if target and not target.startswith("/"):
                    wrong.append(str(entry))
        if wrong:
            offenders[name] = wrong

    assert not offenders, f"these services declare a non-absolute mount target: {offenders}"

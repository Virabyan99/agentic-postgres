"""Session 40's customer proofs: the kept slot's branches, from off the host.

The claim `branch_live` (BR-LIVE-001; ADR 0271-0273). Run from the workstation,
never the host, with no SSH, AFTER `s40-branches.py --delete-only`: the
instrument drove `slot3-prod`'s branches through `/v1` and its public names with
the product's own commands -- the backups surface read; a branch `tmp` created
with the minimum expiry and deleted by the reconciler's own request; two marked
rows written through the parent's direct name, the instant T1 between them; a
branch `dev` restored to T1; Prisma's `migrate deploy` over dev's direct name; the
parent's passwords tried at dev's names; a second branch `qa` refused; dev reset
to the end of the archive; dev back after the reboot; dev deleted -- and wrote
`APG_BRANCH_RECORD_FILE` (0600): operation ids and origins, the points, the rows
each side held, the exits at each name. Never a password, a token or a URL that
authorises anything.

**These proofs read that record and ask the deployment again**: every
operation it names read back through `routes.control` as the probe owner (the
fixtures and `Recorder` are Session 38's module's), and the deleted branch's
names tried now, live, at the public address -- refused before any login.
**None of these eight proofs has ever executed.**
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

import ast
import json
import os
import secrets
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from tests.external.test_session38_public_lifecycle import (  # noqa: F401 -- fixtures
    Recorder,
    _only,
    control,
    endpoint,
    owner,
    probe,
    recorder,
)

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE", "APG_BRANCH_RECORD_FILE"
    ),
]

#: The workstation's public roots: the one file every client is given (D2392).
ROOTS = Path("/etc/ssl/certs/ca-certificates.crt")

#: The kept slot, the branches' parent (plan §0).
PARENT = "slot3-prod"


def instant(text: str) -> datetime:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def branches(control: dict[str, Any], endpoint: str, probe: dict[str, Any]) -> dict[str, Any]:
    """The branches' record: private, finished through the deletion, the probe
    owner's, at the control project's endpoint, about the commit that is
    deployed (§7, D2442)."""
    path = Path(os.environ["APG_BRANCH_RECORD_FILE"])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
    document = json.loads(path.read_text(encoding="utf-8"))
    # Session 41 re-runs these against its own record (D2518).
    assert document.get("session") in (40, 41) and document.get("kind") == "branches", (
        document.get("session"), document.get("kind"),
    )  # fmt: skip
    assert document.get("project_key") == PARENT, document.get("project_key")
    assert document.get("phase") == "deleted" and document.get("finished") is True, (
        f"the branches did not run to their deletion: {document.get('phase')} "
        f"{document.get('stopped')}"
    )
    assert "stopped" not in document, document["stopped"]
    assert document["endpoint"].rstrip("/") == endpoint, document["endpoint"]
    assert document["username"] == probe["username"], document["username"]
    assert document.get("source_commit") == control["source_commit"], (
        f"the record's parent was deployed at {document.get('source_commit')}, the control "
        f"project is at {control['source_commit']}: a record from another release"
    )
    return document


def _operation(recorder: Recorder, endpoint: str, owner: str, operation: str) -> dict[str, Any]:
    status, row = recorder.json("GET", f"{endpoint}/operations/{operation}", None, owner)
    assert status == 200, (operation, status, row.get("error"))
    return row


def _kept(branches: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [row for row in branches["operations"] if row["type"] == kind]


def test_the_backups_surface_reads_a_window(
    recorder: Recorder, endpoint: str, owner: str, branches: dict[str, Any]
) -> None:
    """ADR 0273: before any branch the surface read a WINDOW -- `earliest`
    before `latest`, every status `ok` -- and at the restore its window held T1;
    asked now, it is a window still, read within the last 30 minutes."""
    observations = branches["observations"]
    before = observations["backups_before"]
    assert before["status"] == "window", before
    assert instant(before["earliest"]) < instant(before["latest"]), before
    assert set(before["statuses"].values()) == {"ok"}, before
    at_restore = observations["window_at_restore"]
    t1 = instant(observations["marks"]["T1"])
    assert instant(at_restore["earliest"]) <= t1 <= instant(at_restore["latest"]), (at_restore, t1)
    status, now = recorder.json("GET", f"{endpoint}/projects/{PARENT}/backups", None, owner)
    assert status == 200 and now["status"] == "window", (status, now)
    _only(recorder, endpoint)


def test_an_expired_branch_was_deleted_by_the_reconciler(
    recorder: Recorder, endpoint: str, owner: str, branches: dict[str, Any]
) -> None:
    """ADR 0272: the branch created with an expiry was deleted by an operation
    the instrument never sent -- `origin = expiry`, on behalf of the member who
    set it (the creation's own requester), succeeded -- read back through `/v1`
    now; the record says the branch was gone from the list after it."""
    observed = branches["observations"]["tmp_expired"]
    assert observed["this_instrument_sent_it"] is False and observed["listed_after"] == 0, observed
    created = _operation(
        recorder, endpoint, owner, branches["observations"]["tmp_created"]["operation"]
    )
    expired = _operation(recorder, endpoint, owner, observed["operation"])
    assert (created["type"], created["origin"], created["status"]) == (
        "branch.create", "member", "succeeded",
    ), created  # fmt: skip
    assert (expired["type"], expired["origin"], expired["status"]) == (
        "branch.delete", "expiry", "succeeded",
    ), expired  # fmt: skip
    assert expired["requested_by"] == created["requested_by"], (expired, created)
    assert (expired.get("result") or {}).get("branch") == "tmp", expired
    assert branches["observations"]["tmp_created"]["expires_at"], branches["observations"][
        "tmp_created"
    ]
    _only(recorder, endpoint)


def test_the_branch_holds_the_point_before_the_change(
    recorder: Recorder, endpoint: str, owner: str, branches: dict[str, Any]
) -> None:
    """ADR 0271, restore to a point: row 1 was committed before T1 and row 2
    after it; `dev`, restored to T1, held row 1 alone while `main` held both;
    the restore's operation, read back, is a `restore.create` naming T1, and the
    branch's provenance names the point asked for and a reached point between
    the two rows, on a timeline of its own."""
    observations = branches["observations"]
    marks = observations["marks"]
    row1, t1, row2 = instant(marks["row1_at"]), instant(marks["T1"]), instant(marks["row2_at"])
    assert row1 < t1 < row2, marks
    assert observations["rows_at_T1"] == {"dev": [0, "1"], "main": [0, "1,2"]}, observations
    (restore,) = _kept(branches, "restore.create")
    read = _operation(recorder, endpoint, owner, restore["id"])
    assert (read["status"], read["origin"]) == ("succeeded", "member"), read
    assert instant((read.get("result") or {})["target_time"]) == t1, read
    provenance = observations["dev_provenance"]
    assert instant(provenance["requested_point"]) == t1, provenance
    assert row1 <= instant(provenance["reached_point"]) < row2, provenance
    assert provenance["timeline"] >= 2, provenance
    _only(recorder, endpoint)


def test_a_migration_reached_the_branch_through_its_direct_name(branches: dict[str, Any]) -> None:
    """Prisma's `migrate deploy` over dev's DIRECT name applied the run's own
    migration (D2485): its table exists on `dev` and not on `main` -- a branch
    is a separate database, and nothing written to it reaches the parent."""
    observations = branches["observations"]
    assert observations["migrate_deploy"]["exit"] == 0, observations["migrate_deploy"]
    tables = observations["migration_tables"]
    assert tables["table"] == observations["migrate_deploy"]["migration"], tables
    assert (tables["dev"], tables["main"]) == ([0, "true"], [0, "false"]), tables


def test_the_parents_password_opens_no_branch_door(branches: dict[str, Any]) -> None:
    """ADR 0271 item 5, the re-key: the parent's own customer passwords were
    refused at BOTH of dev's names, and dev's own -- generated by the CLI for
    the branch -- admitted at both as the door's role; after the reset the
    branch's earlier password was refused too."""
    observations = branches["observations"]
    seen = observations["passwords_at_dev"]
    assert seen["parent_pool_exit"] != 0 and seen["parent_direct_exit"] != 0, seen
    doors = branches["doors"]
    assert seen["dev_own"]["app"] == [0, doors["pooled"]["user"]], seen
    assert seen["dev_own"]["admin"] == [0, doors["direct"]["user"]], seen
    reset = observations["reset"]
    assert reset["old_password_exit"] != 0 and reset["rows"] == [0, "1,2"], reset


def test_the_second_branch_was_refused_before_a_row(
    recorder: Recorder, endpoint: str, owner: str, branches: dict[str, Any]
) -> None:
    """D2430: with `dev` live, `qa` was refused `branch_limit_reached` (exit 5)
    with the project's operations unchanged and no password kept; asked now,
    the creations of the run are exactly the two the record names."""
    second = branches["observations"]["second_branch"]
    assert (second["exit"], second["branch_limit_reached"]) == (5, True), second
    assert second["operations_before"] == second["operations_after"], second
    assert second["files_kept"] == 0, second
    organization = branches["organization_id"]
    status, listed = recorder.json(
        "GET", f"{endpoint}/operations?organization={organization}", None, owner
    )
    assert status == 200, status
    # D2506: the window starts at the FIRST attempt's start -- a resumed or
    # `--continue-live` record moves `started_at` past a creation it adopted.
    first = branches.get("window_started_at") or branches["started_at"]
    start, end = instant(first), instant(branches["live_at"])
    during = sorted(row["id"] for row in listed["operations"]
                    if row.get("project_key") == PARENT
                    and row["type"] in ("branch.create", "restore.create")
                    and start <= instant(row["created_at"]) <= end)  # fmt: skip
    recorded = sorted(row["id"] for row in branches["operations"]
                      if row["type"] in ("branch.create", "restore.create"))  # fmt: skip
    assert during == recorded and len(recorded) == 2, (during, recorded)
    _only(recorder, endpoint)


def test_a_deleted_branch_has_no_door(
    recorder: Recorder, endpoint: str, owner: str, branches: dict[str, Any]
) -> None:
    """ADR 0271: after `branch delete dev` both of its names refused the login
    and it left the project's branch list; asked NOW, the branch list names no
    live `dev`, and each of its names is refused at the public address BEFORE
    authentication -- the edge holds no router for it -- whatever is offered."""
    deleted = branches["observations"]["deleted"]
    assert deleted["pool_exit"] != 0 and deleted["direct_exit"] != 0, deleted
    assert deleted["listed_after"] == 0, deleted
    (operation,) = [
        row for row in _kept(branches, "branch.delete") if row["id"] == deleted["operation"]
    ]
    read = _operation(recorder, endpoint, owner, operation["id"])
    assert (read["status"], read["origin"]) == ("succeeded", "member"), read
    status, listed = recorder.json("GET", f"{endpoint}/projects/{PARENT}/branches", None, owner)
    assert status == 200, status
    assert not [b for b in listed["branches"] if b["name"] == "dev" and b["state"] != "deleted"], (
        listed
    )
    _only(recorder, endpoint)
    provenance = branches["observations"]["dev_provenance"]
    for door, host in (("pooled", provenance["pool_host"]), ("direct", provenance["direct_host"])):
        target = branches["doors"][door]
        try:
            psycopg.connect(
                host=host, port=target["port"], dbname=target["database"], user=target["user"],
                password=secrets.token_urlsafe(16), sslmode="verify-full", sslrootcert=str(ROOTS),
                connect_timeout=15,
            ).close()  # fmt: skip
        except psycopg.OperationalError as error:
            text = str(error).lower()
            assert "password" not in text and "authentication" not in text, (host, text)
        else:
            raise AssertionError(f"{host} answered a login after its branch was deleted")


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof: nothing here reaches the host by any
    path but its public address and `routes.control`. Read from this file's own
    text and syntax: no SSH library, no `ssh` argv, no destination -- and no
    process door at all: this module runs no subprocess."""
    text = Path(__file__).read_text(encoding="utf-8")
    # Each needle split so this list never spells what it forbids (D2398).
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    tree = ast.parse(text)
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}  # fmt: skip
    assert "subprocess" not in imported, imported

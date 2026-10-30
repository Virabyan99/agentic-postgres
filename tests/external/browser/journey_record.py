"""The journey's record, and the reading that decides it (Sessions 46-47, JRN-001, JRN-002).

**Pure: no browser import.** `journey_walk.py` drives Chromium and writes the
record through `Journey`; `problems` reads it. The offline suite holds the
reading (`tests/contract/test_journey_driver.py`) where Playwright is not
installed, and the live proofs (`tests/external/test_session46_journey.py`)
call the same function on the record the trip wrote -- one reading, not two.

The journey is the agent's, never the person's walk (ADR 0290 §9, D2871): it
starts from a MEMBERSHIP invitation the probe owner mints, makes its own
organisation, and creates a project in the console on the session's fresh slot
(Session 46's `slot11-prod`, Session 47's `slot13-prod`), which the lifecycle
then continues (`--from-journey`, D2872). It moves `JRN-001`, `CON-CREATE-002`
and `CTL-DIAG-002`, never `documented_path`. **Since Session 47** the driver
reloads the page while the creation runs (`CON-RELOAD-001`) and the record
carries that reading (`reload`), judged by its proof, never here (D3065).

**The record holds no secret** (D2416): the driver keeps every password, the
factor's seed, the handoff token, the link and the cookies in `Journey.held`,
and `leaks` finds any of them in the record before it is written. The three
secrets later steps need go to their own 0600 files beside the record, named by
`token_file`, `password_file` and `seed_file`.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
from urllib.parse import urlsplit

T = TypeVar("T")

#: The steps the driver takes, in order. **J9** (the string connects) is not the
#: driver's: the trip's launcher reads it from the workstation with the proof
#: module's own connection (`read_the_string`, from the 0600 password file) after
#: the driver exits and before the lifecycle deletes the project, into
#: `CONNECTED_FILE` (D2945); **J14** (the project deleted, its names refused) is
#: the lifecycle record's, which continues from this journey's creation (D2872).
STEPS: tuple[tuple[str, str], ...] = (
    ("j01", "the membership link opened the console"),
    ("j02", "the account was made, signed in"),
    ("j03", "the overview named the organisation it joined"),
    ("j04", "a new organisation, the walker its owner"),
    ("j05", "the owner's factor enrolled, signed in again with the next code"),
    ("j06", "a new project accepted in the console, its token shown once"),
    ("j07", "the creation followed to succeeded"),
    ("j08", "Connect: customer_app's password set, the string read once"),
    ("j10", "the SQL editor answered SELECT 1 on the pooled door"),
    ("j11", "usage, insights, monitoring, plan and notifications each read"),
    ("j12", "the support bundle listed the checks with their ages"),
    ("j13", "signed out"),
)

#: J9's reading, 0600, beside the record (D2945).
CONNECTED_FILE = "connected.json"

#: The session this driver writes, and the sessions whose records it reads
#: (D3065): Session 46's record (kept, `evidence/session-46.json`) and this one.
#: WIDENED by a row, never derived from the record.
SESSION = 47
SESSIONS = (46, 47)

#: Since Session 47 (`CON-RELOAD-001`): what the reload during the creation
#: read -- the tracker resumed at its own address, the Overview listed the
#: creation. Each a boolean READING; whether it found the creation is the
#: proof's to judge, so a `false` is a record, an absent one a problem.
RELOAD_READINGS = ("tracker", "overview")
RELOAD_SINCE = 47

#: A `--dry` journey stops before the creation: a slot is consumed by J6 alone.
DRY_STEPS = STEPS[:5]

#: The five views J11 reads, each a reading or *not read*, never a blank.
VIEWS = ("usage", "insights", "monitoring", "plan", "notifications")

#: What the support bundle lists: the doctor's twelve checks (`diagnosis.diagnose`).
BUNDLE_CHECKS = 12

#: The members a finished (not dry) record must carry for the proofs.
FINISHED_MEMBERS = (
    "operation_id",
    "project_key",
    "organization",
    "source_commit",
    "site_digest",
    "token_file",
    "password_file",
    "seed_file",
    "string_parameters",
    "views",
    "support_bundle",
)

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def origin_of(url: str) -> str:
    """`scheme://host[:port]` for a network URL; the bare scheme for one that
    names no host (`data:`, `blob:`), which stays inside the page."""
    parts = urlsplit(url)
    if parts.scheme in ("data", "blob", "about"):
        return f"{parts.scheme}:"
    return f"{parts.scheme}://{parts.netloc}"


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Journey:
    """The record as the driver writes it, and the secrets it must never hold."""

    def __init__(self, base: str, relay: str, site: str, mode: str) -> None:
        self.record: dict[str, Any] = {
            "version": 1,
            "session": SESSION,
            "base": base.rstrip("/"),
            "relay": relay.rstrip("/"),
            "site": site.rstrip("/"),
            "mode": mode,
            "started_at": now(),
            "steps": [],
            "origins": [],
        }
        self.held: list[str] = []

    def step(self, code: str, work: Callable[[], T]) -> T:
        names = dict(STEPS)
        if code not in names:
            raise ValueError(f"{code} is not a journey step")
        started = time.monotonic()
        entry: dict[str, Any] = {"step": code, "name": names[code], "at": now()}
        try:
            result = work()
        except Exception as error:  # the record names the step, never a value
            entry.update(outcome="failed", error=type(error).__name__,
                         seconds=round(time.monotonic() - started, 1))  # fmt: skip
            self.record["steps"].append(entry)
            raise
        entry.update(outcome="ok", seconds=round(time.monotonic() - started, 1))
        self.record["steps"].append(entry)
        return result

    def saw(self, url: str) -> None:
        """Every request the page attempted -- Playwright's `request` event fires
        for one the policy then blocks too (rig 45b) -- by origin."""
        origin = origin_of(url)
        if origin not in self.record["origins"]:
            self.record["origins"].append(origin)

    def leaks(self) -> int:
        text = json.dumps(self.record)
        return sum(1 for value in self.held if value and value in text)


def allowed_origins(record: dict[str, Any]) -> set[str]:
    """The console's origin, the relay's (the editor's one other origin, ADR
    0285) and what never leaves the page."""
    return {str(record.get("base")), str(record.get("relay")), "data:", "blob:", "about:"}


def problems(record: Any, *, dry: bool = False) -> list[str]:
    """Everything that keeps a record from being a journey. Total over a
    malformed record: each problem named, never a raise."""
    if not isinstance(record, dict):
        return [f"the record is a {type(record).__name__}, not an object"]
    found: list[str] = []
    session = record.get("session")
    if type(session) is not int or session not in SESSIONS:
        found.append(f"session is {session!r}, not one of {list(SESSIONS)}")
    expected = [code for code, _ in (DRY_STEPS if dry else STEPS)]
    steps = record.get("steps") if isinstance(record.get("steps"), list) else []
    taken = [s.get("step") for s in steps if isinstance(s, dict)]
    for code in expected:
        if code not in taken:
            found.append(f"{code} ({dict(STEPS)[code]}) is missing")
    if [code for code in taken if code in expected] != [c for c in expected if c in taken]:
        found.append(f"the steps are out of order: {taken}")
    for step in steps:
        if isinstance(step, dict) and step.get("outcome") != "ok":
            found.append(f"{step.get('step')} ended {step.get('outcome')!r}")
    origins = record.get("origins") if isinstance(record.get("origins"), list) else []
    if not origins:
        found.append("no request was recorded: the origin reading saw nothing")
    for origin in origins:
        if origin not in allowed_origins(record):
            found.append(f"a request left the console's origins: {origin}")
    if record.get("exit") != 0:
        found.append(f"the driver exited {record.get('exit')!r}")
    if dry:
        if record.get("dry") is not True:
            found.append("a dry reading of a record that is not a dry run's")
        return found
    if record.get("dry"):
        found.append("a dry run's record, not the journey's")
    for member in FINISHED_MEMBERS:
        if member not in record:
            found.append(f"{member} is absent")
    if not _UUID.match(str(record.get("operation_id", ""))):
        found.append(f"operation_id is {record.get('operation_id')!r}, not an operation's id")
    if not _SHA1.match(str(record.get("source_commit", ""))):
        found.append("source_commit is not a commit (40 hex)")
    if not _SHA256.match(str(record.get("site_digest", ""))):
        found.append("site_digest is not the site's digest (64 hex)")
    parameters = record.get("string_parameters")
    if not isinstance(parameters, dict) or parameters.get("sslmode") != "verify-full":
        found.append("the connection string did not ask for sslmode=verify-full")
    views = record.get("views") if isinstance(record.get("views"), dict) else {}
    for view in VIEWS:
        reading = views.get(view)
        if not isinstance(reading, dict) or reading.get("read") is not True:
            found.append(f"the {view} view rendered no reading and no 'not read'")
    bundle = record.get("support_bundle") if isinstance(record.get("support_bundle"), dict) else {}
    if bundle.get("checks") != BUNDLE_CHECKS or bundle.get("aged") != BUNDLE_CHECKS:
        found.append(
            f"the support bundle listed {bundle.get('checks')!r} checks, "
            f"{bundle.get('aged')!r} with an age; the doctor has {BUNDLE_CHECKS}"
        )
    if type(session) is int and session >= RELOAD_SINCE:
        reload = record.get("reload") if isinstance(record.get("reload"), dict) else {}
        unread = [name for name in RELOAD_READINGS if type(reload.get(name)) is not bool]
        if unread:
            found.append(f"the reload during the creation was not read: {unread}")
    return found

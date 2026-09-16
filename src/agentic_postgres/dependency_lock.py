"""Whether the environment satisfies the development lock (D297, D1430).

**`bin/lock-dev-deps.sh --check` verifies the LOCK and not the ENVIRONMENT, and
the difference has killed a gate three times.** Session 6's host gate printed
`lock-dev-deps: requirements-dev.txt is current` and then died in collection
with four `ModuleNotFoundError`s — `cryptography`, `argon2`, `fastapi`, `jwt` —
because Run 7 had added nine packages to the lock and the host's venv predated
them. Session 7 repeated it with `boto3`: *4 errors, 3421 deselected*. Each time
the gate's own environment line was green, each time the failure arrived in
collection, and each time the message named a module rather than a cause or a
remedy.

**Session 6 deferred this deliberately, and its reason was about TIMING**: a
gate step that compares installed distributions against the lock is *"a new
authority over the environment, and adding one in the run that is about to
collect evidence is how a gate change gets attributed to the evidence."* That is
a rule about *when*. It has been read as *whether* for twenty-two sessions
(D1430), and Session 28 takes it in a run that collects no evidence.

**What this is not.** It does not resolve anything, reach a network, or decide
what the lock should contain — `lock-dev-deps.sh --check` owns that and is
unchanged. It reads two lists and compares them. An installed distribution the
lock does not pin is **not** a disagreement: a virtual environment legitimately
carries `pip`, `setuptools` and whatever the interpreter's own tooling installs,
and a check that refused those would be a check nobody could keep green.
"""

from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

from agentic_postgres import REPO_ROOT

LOCK_PATH = REPO_ROOT / "requirements-dev.txt"

#: The remedy, spelled exactly as `bin/lock-dev-deps.sh --help` already spells
#: it. **The remedy is the point of this check**, not the detection: a
#: `ModuleNotFoundError` in collection is already a detection, and what it left
#: an operator with was a module name. Three gate deaths, and none of the three
#: messages said what to run.
INSTALL_COMMAND = "python -m pip install --require-hashes -r requirements-dev.txt"

#: `name==version`, at the start of a line, in a hash-locked requirements file.
#: Everything else in such a file is a `--hash` continuation, a `# via` comment
#: or the cutoff marker.
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s\\;]+)")

__all__ = [
    "INSTALL_COMMAND",
    "LOCK_PATH",
    "canonical",
    "disagreements",
    "installed_versions",
    "pinned_versions",
]


def canonical(name: str) -> str:
    """A distribution name in the one spelling both sides can be compared in.

    PEP 503: names are case-insensitive and `-`, `_` and `.` are equivalent, so
    `ruff`, `Ruff`, `typing_extensions` and `typing-extensions` are two names
    between them. Comparing the raw strings finds disagreements that are
    spellings, which is how a check like this gets turned off.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned_versions(path: Path = LOCK_PATH) -> dict[str, str]:
    """What the lock pins, by canonical name."""
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _PIN.match(line)
        if match:
            pins[canonical(match.group(1))] = match.group(2)
    return pins


def installed_versions() -> dict[str, str]:
    """What this interpreter can actually import, by canonical name.

    `importlib.metadata` rather than `pip freeze`: it reads the environment this
    process is running in, which is the only environment whose answer matters —
    a subprocess could resolve a different interpreter, and resolving a
    different interpreter is half of what D297 was.
    """
    found: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata["Name"]
        if name:
            found[canonical(name)] = distribution.version
    return found


def disagreements(
    pins: dict[str, str] | None = None, present: dict[str, str] | None = None
) -> list[str]:
    """Every way this environment fails to satisfy the lock, each with its cause.

    Two kinds, named separately because the operator does the same thing about
    both and would otherwise have to work out which they are looking at:

    * **absent** — the distribution is pinned and not installed. This is the
      shape that killed the gate three times.
    * **a different version** — installed, at a version the lock does not pin.
      It produces no `ModuleNotFoundError` at all, so nothing detects it today;
      it arrives as behaviour, which is worse.

    An installed distribution the lock does not mention is deliberately not
    reported — see this module's docstring.

    **Both arguments are canonicalised here as well as at their sources.** The
    readers above already do it, so this is for the caller who passes a dict of
    their own: a comparison that reported `typing_extensions` missing while
    `typing-extensions` was installed would be reporting a spelling, and a check
    that reports spellings gets turned off.
    """
    pins = pinned_versions() if pins is None else {canonical(k): v for k, v in pins.items()}
    present = (
        installed_versions() if present is None else {canonical(k): v for k, v in present.items()}
    )

    problems: list[str] = []
    for name in sorted(pins):
        want = pins[name]
        have = present.get(name)
        if have is None:
            problems.append(f"{name}=={want} is pinned and NOT INSTALLED")
        elif have != want:
            problems.append(f"{name} is installed at {have}; the lock pins {want}")
    return problems


def refusal(problems: list[str]) -> str:
    """The sentence a gate prints, with the remedy in it.

    Every one of the three gate deaths this check exists for ended in a message
    that named a module and nothing else. This names the cause, the count and
    the command — and says explicitly that the lock itself is not the thing that
    is wrong, because the gate has just printed a green line about it.
    """
    listed = "\n".join(f"  {problem}" for problem in problems)
    return (
        f"this environment does not satisfy requirements-dev.txt "
        f"({len(problems)} disagreement(s)):\n{listed}\n\n"
        f"The LOCK is fine -- that is what the line above checked. What is out of date "
        f"is this interpreter's site-packages. Run:\n\n    {INSTALL_COMMAND}\n\n"
        "This check exists because the same gap died in collection three times with "
        "only a ModuleNotFoundError to go on (D297, D384, D1430)."
    )

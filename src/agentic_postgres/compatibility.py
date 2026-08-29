"""What a ``template_version`` bump permits (ADR 0162).

Pure. Nothing here reads a file, runs a process or touches the network: every
function takes what was observed and returns what to say about it. That is
``preflight``'s split and its reason -- a module that shells out is testable only
where a shell is, and its mutants cannot be killed.

**Semver is parsed here rather than by ``packaging``**, and the reasons were
measured (ADR 0162, Session 13 Run 3):

    0.1.0-dev     PEP 440 accepts it and REWRITES it to `0.1.0.dev0`
    1.0.0-rc.1    likewise, to `1.0.0rc1`
    1.0.0.rc1     PEP 440 accepts what semver refuses
    1.2           likewise
    01.2.3        likewise, and silently normalises it to `1.2.3`

Ordering is where the two grammars agree, which is exactly why reaching for the
installed parser is tempting. The failure is not in the comparison; it is that a
round trip returns a string the document does not contain, and that the validity
question -- the one a refusal rests on -- is answered by the wrong grammar in
three of nine measured cases. `packaging` is also absent from
`requirements-dev.in`; it is in the lock only transitively.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "CHANGE_CLASSES",
    "LEVELS",
    "MAJOR",
    "MINOR",
    "OPERATOR_DIGESTS",
    "PATCH",
    "RELEASE_DIGESTS",
    "SEMVER_PATTERN",
    "CompatibilityError",
    "Version",
    "bump_between",
    "parse",
    "required_level",
    "sufficient",
]


class CompatibilityError(ValueError):
    """A version could not be parsed, or a change class is not one of ours."""


#: Semver 2.0.0, the grammar from semver.org, anchored.
#:
#: `\Z` rather than `$`, for `installed_release.COMMIT_PATTERN`'s reason: in
#: Python `$` also matches immediately before a trailing newline, so a value read
#: from a file with a stray newline would validate and then not round-trip.
SEMVER_PATTERN = (
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"
)

_SEMVER = re.compile(SEMVER_PATTERN + r"\Z")

PATCH = "patch"
MINOR = "minor"
MAJOR = "major"

#: Ordered from least to most permissive. A change needing `minor` is satisfied
#: by `minor` or `major`, and that ordering is the whole of `sufficient`.
LEVELS = (PATCH, MINOR, MAJOR)

#: The two input digests that are the OPERATOR's. An upgrade must not move them:
#: if one does, the operator edited a manifest, which is a different operation.
OPERATOR_DIGESTS = ("project_sha256", "capabilities_sha256")

#: The three that are the RELEASE's. These move on almost every release, so a
#: difference here is a trigger for a closer comparison and never a verdict.
RELEASE_DIGESTS = (
    "secrets_contract_sha256",
    "versions_lock_sha256",
    "source_specification_sha256",
)

#: Every change this release knows how to classify, and the smallest bump that
#: permits it (ADR 0162 §2). A class absent from here is refused rather than
#: assumed harmless: an unclassified change is one nobody has decided about.
CHANGE_CLASSES: dict[str, str] = {
    # patch -- no interface moves.
    "implementation": PATCH,
    "image_digest": PATCH,
    # minor -- additive; the operator's manifests still validate unchanged.
    "migration_added": MINOR,
    "api_operation_added": MINOR,
    "capability_added": MINOR,
    "secret_optional_added": MINOR,
    "document_schema_migratable": MINOR,
    # major -- the operator must act before the upgrade.
    "operator_manifest_invalidated": MAJOR,
    "api_operation_removed": MAJOR,
    "api_operation_changed": MAJOR,
    "secret_required_added": MAJOR,
    "document_schema_needs_operator_input": MAJOR,
}


@dataclass(frozen=True, order=False)
class Version:
    """A parsed semver 2.0.0 version.

    ``build`` is carried and deliberately ignored by every comparison, which is
    semver's own rule: build metadata does not participate in precedence.
    """

    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += f"-{self.prerelease}"
        if self.build:
            text += f"+{self.build}"
        return text

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


def parse(value: str) -> Version:
    """Parse a semver 2.0.0 string, or raise.

    Round-trips: ``str(parse(v)) == v`` for every accepted ``v``. That is the
    property `packaging` does not have for the values this repository publishes,
    and it is asserted rather than described.
    """
    if not isinstance(value, str):
        raise CompatibilityError(f"template_version must be a string, got {type(value).__name__}")
    match = _SEMVER.match(value)
    if match is None:
        raise CompatibilityError(
            f"not a semver 2.0.0 version: {value!r}. "
            "The grammar is semver.org's, not PEP 440's -- `1.2`, `01.2.3` and "
            "`1.0.0.rc1` are refused here and accepted by `packaging`."
        )
    major, minor, patch, prerelease, build = match.groups()
    return Version(int(major), int(minor), int(patch), prerelease, build)


def bump_between(installed: str, candidate: str) -> str | None:
    """The level of the bump from ``installed`` to ``candidate``.

    ``None`` when the candidate is not ahead of the installed version -- equal,
    or behind. The caller decides what that means; this does not guess, because
    "same version" and "going backwards" are different situations and only the
    caller knows which one it is looking at.

    A change in the prerelease alone, at one core version, counts as ``patch``:
    ``0.1.0-dev -> 0.1.0`` moves no core component, and calling it "no bump"
    would let a release cross out of prerelease while claiming nothing changed.
    """
    left = parse(installed)
    right = parse(candidate)

    if right.core > left.core:
        if right.major != left.major:
            return MAJOR
        if right.minor != left.minor:
            return MINOR
        return PATCH

    if right.core == left.core and right.prerelease != left.prerelease:
        # Semver's precedence: a prerelease sorts BEFORE its release, so
        # `0.1.0-dev -> 0.1.0` is forward and `0.1.0 -> 0.1.0-dev` is not.
        if left.prerelease is not None and right.prerelease is None:
            return PATCH
        if left.prerelease is not None and right.prerelease is not None:
            return PATCH if right.prerelease > left.prerelease else None
        return None

    return None


def required_level(changes: list[str]) -> str:
    """The smallest bump that permits every change in ``changes``.

    An empty list is ``patch``: a release with no classified change still moves
    its version, because a release that publishes nothing new is still a release
    and the deployed document records which one is installed.

    An unknown class raises. **An unclassified change is not a harmless one** --
    it is one nobody has decided about, and defaulting it to `patch` would make
    this function answer a question it was never asked.
    """
    unknown = sorted(set(changes) - set(CHANGE_CLASSES))
    if unknown:
        raise CompatibilityError(
            f"unclassified change(s): {unknown}. Add each to CHANGE_CLASSES with the "
            "bump it requires, or the rule is silent about it rather than permissive."
        )
    return max((CHANGE_CLASSES[name] for name in changes), key=LEVELS.index, default=PATCH)


def sufficient(*, proposed: str | None, required: str) -> bool:
    """Is a ``proposed`` bump at least as large as the ``required`` one?

    ``proposed`` is ``None`` when the candidate is not ahead of the installed
    version, which is never sufficient for anything -- including for `patch`,
    because a release that changed nothing still has to say so by moving.
    """
    if required not in LEVELS:
        raise CompatibilityError(f"unknown level: {required!r}. Expected one of {list(LEVELS)}.")
    if proposed is None:
        return False
    if proposed not in LEVELS:
        raise CompatibilityError(f"unknown level: {proposed!r}. Expected one of {list(LEVELS)}.")
    return LEVELS.index(proposed) >= LEVELS.index(required)

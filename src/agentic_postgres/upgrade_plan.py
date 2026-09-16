"""What an upgrade would do, computed before anything is mutated (ADR 0162).

Pure, for ``preflight``'s reason: nothing here reads a file, runs a process or
touches the network. ``bin/upgrade.py`` owns the subprocesses and the paths.

**The comparison is `rendered(installed)` against `rendered(candidate)`**, and
that was a correction rather than a preference (D732, D733). The obvious
left-hand side is the *deployed* document -- it sounds authoritative -- and it is
the wrong one twice over:

    it shares 41% of its leaf vocabulary with a rendered document, and six of
    the seven routes are a STRING on one side and an OBJECT on the other, so a
    leaf diff across the kinds reports every route changed on every run;

    it carries no `inputs` block at all, so the five digests that answer "did the
    inputs change" -- the question a plan exists to ask -- are only on the
    rendered side.

Measured against that: **a rendered-vs-rendered diff has a noise floor of zero.**
Two renders of one unchanged project produced 108 identical leaves, against a
control that planted two changes and found exactly two. The deployed document
carries 24 observation-shaped leaves (`observed_at`, seven route statuses,
`generation_id`, `instance_uuid`) that differ on every comparison by design.

The installed rendered document lives at
``deployed_output.rendered_path(key)/outputs.json``: ``install_rendered`` puts it
there on every deploy, which is what makes the left-hand side available at all.

**Three verdicts, not two** -- ADR 0157's decision applied to a new subject,
which per ADR 0021 is not a new decision. A plan that cannot say *"I could not
look"* reports "no changes detected" for a left-hand side nobody read.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentic_postgres import REPO_ROOT, compatibility

__all__ = [
    "BLOCKED",
    "COMMIT_GIT_UNAVAILABLE",
    "COMMIT_NOT_A_WORKING_TREE",
    "COMMIT_READ",
    "OK",
    "UNDETERMINED",
    "CommitReading",
    "Difference",
    "Plan",
    "UpgradePlanError",
    "build_plan",
    "classify_document_changes",
    "differences",
    "leaves",
    "read_checkout_commit",
]


class UpgradePlanError(ValueError):
    """A plan could not be computed from what it was given."""


#: The candidate may be installed.
OK = "ok"
#: It may not: something is incompatible, or the bump does not cover it.
BLOCKED = "blocked"
#: Nobody looked. **Blocks exactly as BLOCKED does** -- a plan cannot proceed on
#: a comparison that was never made, which is ADR 0157's whole point.
UNDETERMINED = "undetermined"


#: The commit was read from the checkout.
COMMIT_READ = "read"
#: There is a `git`, and this directory is not a working tree of one. **An
#: adopter's tarball fork is in exactly this state**, and so is a checkout
#: copied to a host with `scp` or unpacked from a `git bundle`'s worktree
#: export -- which is not a rare case here, it is how this product's own
#: transport works (D504).
COMMIT_NOT_A_WORKING_TREE = "not_a_git_working_tree"
#: No `git` on PATH at all. A deployed host is not obliged to have one.
COMMIT_GIT_UNAVAILABLE = "git_unavailable"


@dataclass(frozen=True)
class CommitReading:
    """Which commit a checkout is, or why that could not be determined.

    **ADR 0195 in a dataclass.** The question has three answers and the third
    is reported rather than folded: a reader that returned `None` for both *not
    a working tree* and *no git* would make an adopter's tarball fork
    indistinguishable from a broken environment, and a reader that returned the
    empty string would make either indistinguishable from a match.

    This exists because of F-020 (D1423): `upgrade check` compared versions and
    digests and never commits, so a host checkout one commit behind the
    workstation read as identical. Reporting the commit is the repair; reporting
    *I could not determine it* is the half that makes the repair honest for the
    checkout an adopter actually has.
    """

    commit: str | None
    outcome: str

    @property
    def determined(self) -> bool:
        return self.outcome == COMMIT_READ

    def render(self) -> str:
        """One line for a human, never a bare `None` (D600, D1394)."""
        if self.determined and self.commit:
            return self.commit
        if self.outcome == COMMIT_NOT_A_WORKING_TREE:
            return "(undetermined: this checkout is not a git working tree)"
        return "(undetermined: no git available here)"


def read_checkout_commit(root: Path = REPO_ROOT) -> CommitReading:
    """The commit this checkout is at, with the third outcome (ADR 0195).

    S607 suppressed for the reason `evidence.git_output` gives and no other:
    the arguments are literals from this module and never operator input. S603
    is NOT suppressed here and the neighbouring reader does suppress it --
    ruff does not raise it for this call and an unused directive is an error,
    so the difference is ruff's rather than a judgement of mine.

    `check=False` with the outcome derived from the return code, because a
    non-zero `rev-parse` is the ANSWER here rather than an error: it is how a
    directory says it is not a working tree.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return CommitReading(commit=None, outcome=COMMIT_GIT_UNAVAILABLE)
    if result.returncode != 0:
        return CommitReading(commit=None, outcome=COMMIT_NOT_A_WORKING_TREE)
    commit = result.stdout.strip()
    if not commit:
        return CommitReading(commit=None, outcome=COMMIT_NOT_A_WORKING_TREE)
    return CommitReading(commit=commit, outcome=COMMIT_READ)


def leaves(node: Any, path: str = "") -> dict[str, Any]:
    """Every scalar in a document, keyed by dotted path.

    List indices are kept (``verification_kids[0]``) because position is
    meaningful in the one list that matters: ``render-jwks.py`` orders the key
    set and a reader is expected to guess in that order.

    Moved here from ``tests/deployment/test_session12_isolation_matrix.py`` in
    Session 13 Run 4 so that a second copy did not have to exist (D725). **The
    matrix's classification lists did NOT move with it**: `MUST_DIFFER` /
    `MUST_MATCH` / `RELEASE_STATE` are a judgement about *two projects*, and a
    diff between *two releases of one project* is a different question over the
    same leaves. Sharing the walker is right; sharing the categories would be
    D702 -- a list derived from one observation, reused where its accidents do
    not hold.
    """
    out: dict[str, Any] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(leaves(value, f"{path}.{key}" if path else key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.update(leaves(value, f"{path}[{index}]"))
    else:
        out[path] = node
    return out


@dataclass(frozen=True)
class Difference:
    """One leaf that is not the same on both sides.

    ``ABSENT`` rather than ``None`` for a missing side: ``None`` is a value a
    document can legitimately carry -- `jwt.retire_after` is `null` whenever no
    rotation is in flight -- so using it to mean "not present" would make those
    two indistinguishable. That is D600's family.
    """

    ABSENT = "<absent>"

    path: str
    installed: Any
    candidate: Any

    @property
    def added(self) -> bool:
        return self.installed == self.ABSENT

    @property
    def removed(self) -> bool:
        return self.candidate == self.ABSENT


def differences(installed: dict[str, Any], candidate: dict[str, Any]) -> tuple[Difference, ...]:
    """Every leaf that differs, in path order, additions and removals included."""
    left = leaves(installed)
    right = leaves(candidate)
    found: list[Difference] = [
        Difference(path, left[path], right[path])
        for path in left.keys() & right.keys()
        if left[path] != right[path]
    ]
    found += [
        Difference(path, left[path], Difference.ABSENT) for path in left.keys() - right.keys()
    ]
    found += [
        Difference(path, Difference.ABSENT, right[path]) for path in right.keys() - left.keys()
    ]
    return tuple(sorted(found, key=lambda item: item.path))


def classify_document_changes(found: tuple[Difference, ...]) -> tuple[str, ...]:
    """The change classes two rendered documents can establish *by themselves*.

    **Deliberately not every class in ADR 0162's table.** A new migration lives in
    `migrations/released.lock.json` and an API change lives in `contracts/`;
    neither is visible in a rendered document, so neither is guessed here. The
    caller measures those and passes them to ``build_plan`` as ``also``.

    A function that inferred `migration_added` from, say, a `schema_version`
    move would be answering a question it cannot see the evidence for -- which is
    the shape this repository keeps producing.
    """
    classes: set[str] = set()
    by_path = {item.path: item for item in found}

    if "inputs.versions_lock_sha256" in by_path:
        classes.add("image_digest")
    for digest in ("inputs.source_specification_sha256", "inputs.secrets_contract_sha256"):
        if digest in by_path:
            classes.add("implementation")

    # A name in `secrets.required_names` IS a required secret -- that is what the
    # list is. So a gained member is `secret_required_added`, which ADR 0162
    # makes major, and this is derivable where the optional/required distinction
    # generally is not.
    if any(item.path.startswith("secrets.required_names") and item.added for item in found):
        classes.add("secret_required_added")

    if any(item.path.startswith("capabilities.") and item.added for item in found):
        classes.add("capability_added")

    return tuple(sorted(classes))


@dataclass(frozen=True)
class Plan:
    """What an upgrade would do, and whether it may proceed.

    ``verdict`` is one of ``OK``, ``BLOCKED``, ``UNDETERMINED``. ``reasons`` is
    never empty when the verdict is not ``OK``: a refusal that does not say why
    sends an operator to read source.
    """

    verdict: str
    installed_version: str | None
    candidate_version: str | None
    bump: str | None
    required: str | None
    changes: tuple[str, ...] = ()
    differences: tuple[Difference, ...] = ()
    operator_digests_moved: tuple[str, ...] = ()
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def blocks(self) -> bool:
        return self.verdict != OK


def _undetermined(reason: str) -> Plan:
    return Plan(
        verdict=UNDETERMINED,
        installed_version=None,
        candidate_version=None,
        bump=None,
        required=None,
        reasons=(reason,),
    )


def build_plan(
    installed: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    *,
    also: tuple[str, ...] = (),
) -> Plan:
    """Compare two rendered documents and say whether the upgrade may proceed.

    ``installed`` is ``None`` when there is nothing installed to compare against,
    or when it could not be read. That is ``UNDETERMINED`` and it **blocks**: a
    missing left-hand side is not "no changes detected" (ADR 0162 §4).

    ``also`` carries change classes the caller measured outside these documents --
    a new released migration, an API contract move. They are classified by the
    same table and cannot be spelled differently: an unknown one raises.
    """
    if candidate is None:
        return _undetermined("the candidate release produced no rendered document")
    if installed is None:
        return _undetermined(
            "no installed rendered document to compare against; nobody looked, "
            "so this is not 'no changes'"
        )

    for name, document in (("installed", installed), ("candidate", candidate)):
        if document.get("document_kind") != "rendered":
            return _undetermined(
                f"the {name} document is {document.get('document_kind')!r}, not 'rendered'. "
                "A deployed document carries no `inputs` block and shares 41% of its leaf "
                "vocabulary with a rendered one (D732, D733)."
            )

    installed_version = installed.get("template_version")
    candidate_version = candidate.get("template_version")
    reasons: list[str] = []

    try:
        bump = compatibility.bump_between(str(installed_version), str(candidate_version))
    except compatibility.CompatibilityError as error:
        return _undetermined(f"a template_version could not be parsed: {error}")

    found = differences(installed, candidate)
    changes = tuple(sorted(set(classify_document_changes(found)) | set(also)))

    try:
        required = compatibility.required_level(list(changes))
    except compatibility.CompatibilityError as error:
        raise UpgradePlanError(str(error)) from None

    moved = tuple(
        digest
        for digest in compatibility.OPERATOR_DIGESTS
        if any(item.path == f"inputs.{digest}" for item in found)
    )
    if moved:
        reasons.append(
            "the operator's own inputs moved: "
            + ", ".join(moved)
            + ". An upgrade changes the release, not the manifests you supply; "
            "re-run with the manifests this deployment was rendered from, or "
            "deploy the manifest change as its own operation."
        )

    if bump is None:
        reasons.append(
            f"the candidate is not ahead of what is installed "
            f"({installed_version!r} -> {candidate_version!r}). A release that "
            "publishes nothing new still has to say so by moving its version."
        )
    elif not compatibility.sufficient(proposed=bump, required=required):
        reasons.append(
            f"this is a {bump} bump and the changes require {required}: " + ", ".join(changes)
        )

    return Plan(
        verdict=BLOCKED if reasons else OK,
        installed_version=installed_version,
        candidate_version=candidate_version,
        bump=bump,
        required=required,
        changes=changes,
        differences=found,
        operator_digests_moved=moved,
        reasons=tuple(reasons),
    )

#!/usr/bin/env python3
"""Compute an upgrade plan. Invoked only by ``bin/upgrade.sh`` (ADR 0162).

The logic is in ``agentic_postgres.upgrade_plan``, which opens no file. What
lives here is everything that touches the host: reading the installed rendered
document under the root-owned project state root, and printing.

**This program never writes.** `deploy.sh --through-session` performs an upgrade;
this says what one would do. Keeping the two apart is what makes "a plan before
any mutation" a property rather than a promise -- a planner that could also
mutate would be trusted to choose, and the choice is the operator's.

Exit codes follow the convention (D42):
  0   the plan may proceed
  2   invalid operator input
  3   missing local prerequisite
  4   no installed rendered document for that project -- never deployed here
  6   the plan is blocked, or could not be computed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import deployed_output, template_version, upgrade_plan  # noqa: E402

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_MISSING = 4
EXIT_BLOCKED = 6


def fail(code: int, message: str) -> None:
    print(f"upgrade: {message}", file=sys.stderr)
    raise SystemExit(code)


def read_document(path: Path, *, what: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(EXIT_MISSING, f"no {what} rendered document at {path}")
    except PermissionError:
        fail(
            EXIT_PREREQUISITE,
            f"cannot read the {what} rendered document at {path}. "
            "The project state root is root-owned; run under sudo on a host.",
        )
    except json.JSONDecodeError as error:
        fail(EXIT_BLOCKED, f"the {what} rendered document at {path} is not valid JSON: {error}")
    raise AssertionError("unreachable")


def installed_path(project_key: str) -> Path:
    return deployed_output.rendered_path(project_key) / "outputs.json"


def look_for(path: Path) -> str:
    """Is it there? -- with the third answer, because `exists()` does not have it.

    **`Path.exists()` RAISES on a permission error.** It swallows `ENOENT`,
    `ENOTDIR`, `EBADF` and `ELOOP` and lets `EACCES` through, so probing a file
    under the root-owned project state root as an unprivileged user does not
    return `False` -- it raises `PermissionError`, and the first version of this
    command exited 1 with a traceback where an operator expected a verdict.

    Which is ADR 0157's distinction exactly, in the command that cites it:
    *not there* and *could not look* are different, and only one of them is this
    project never having been deployed here.
    """
    try:
        return "present" if path.is_file() else "absent"
    except PermissionError:
        return "undetermined"


#: Change classes an operator may declare with `--also`, because **no pair of
#: rendered documents can establish them.**
#:
#: A rendered document records no migration count and no API contract digest, and
#: `migrations/released.lock.json` describes only the checkout in hand -- never
#: the release that produced the *installed* document. So this command can read
#: how many migrations THIS checkout has released and cannot read how many the
#: installed one had, which makes "a migration was added" undecidable from here.
#:
#: **Declared rather than guessed.** Inferring it from a `schema_version` move,
#: or from the checkout's own lock, would be answering a question whose evidence
#: is not in the room -- and it would be wrong in the direction that matters,
#: because `migration_added` is what makes a bump irreversible by image rollback.
DECLARABLE = (
    "migration_added",
    "api_operation_added",
    "api_operation_removed",
    "api_operation_changed",
    "secret_optional_added",
    "document_schema_migratable",
    "document_schema_needs_operator_input",
    "operator_manifest_invalidated",
)


def render_plan_text(plan: upgrade_plan.Plan, project_key: str) -> str:
    lines = [
        f"upgrade plan for {project_key}",
        f"  installed   {plan.installed_version}",
        f"  candidate   {plan.candidate_version}",
        f"  bump        {plan.bump or '(not ahead)'}",
        f"  requires    {plan.required or '(not computed)'}",
        f"  verdict     {plan.verdict.upper()}",
    ]
    if plan.changes:
        lines.append("\n  changes")
        lines += [f"    {name}" for name in plan.changes]
    if plan.differences:
        lines.append(f"\n  {len(plan.differences)} leaf/leaves differ")
        for item in plan.differences[:40]:
            lines.append(f"    {item.path}")
            lines.append(f"      {item.installed!r} -> {item.candidate!r}")
        if len(plan.differences) > 40:
            lines.append(f"    ... and {len(plan.differences) - 40} more")
    if plan.reasons:
        lines.append("\n  this plan may not proceed:")
        lines += [f"    - {reason}" for reason in plan.reasons]
    else:
        lines.append("\n  nothing blocks this upgrade.")
        lines.append("  Run ./deploy.sh --through-session N to perform it.")
    return "\n".join(lines)


def as_json(plan: upgrade_plan.Plan, project_key: str) -> dict[str, Any]:
    return {
        "project": project_key,
        "verdict": plan.verdict,
        "installed_version": plan.installed_version,
        "candidate_version": plan.candidate_version,
        "bump": plan.bump,
        "requires": plan.required,
        "changes": list(plan.changes),
        "operator_digests_moved": list(plan.operator_digests_moved),
        "differences": [
            {"path": item.path, "installed": item.installed, "candidate": item.candidate}
            for item in plan.differences
        ],
        "reasons": list(plan.reasons),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bin/upgrade.sh", add_help=False)
    parser.add_argument("verb", choices=["check", "plan", "verify"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--installed", type=Path, default=None)
    parser.add_argument("--candidate", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--also",
        action="append",
        default=[],
        choices=DECLARABLE,
        help="A change class no pair of rendered documents can establish. Repeatable.",
    )
    arguments = parser.parse_args(argv)

    project_key = arguments.project
    source = arguments.installed or installed_path(project_key)

    installed: dict[str, Any] | None
    presence = "present" if arguments.installed is not None else look_for(source)

    if presence == "undetermined":
        fail(
            EXIT_PREREQUISITE,
            f"cannot tell whether {source} exists: permission denied. The project "
            "state root is root-owned; run under sudo on a host. This is not the "
            "same as the project not being deployed here.",
        )
    if presence == "absent":
        # An absent left-hand side is `check`'s finding rather than its failure:
        # it reports UNDETERMINED and exits 4, which is a different thing from a
        # plan that was computed and came out blocked.
        installed = None
    else:
        installed = read_document(source, what="installed")

    if arguments.verb == "check":
        # `check` asks whether a comparison can be made at all, and that question
        # has an answer with no candidate document: what is installed, what this
        # release is, and whether the two are the same kind of thing. Requiring a
        # render here would make the cheapest verb the one with a prerequisite.
        payload = {
            "project": project_key,
            "verdict": upgrade_plan.UNDETERMINED if installed is None else upgrade_plan.OK,
            "installed_version": (installed or {}).get("template_version"),
            "installed_document": str(source),
            "installed_kind": (installed or {}).get("document_kind"),
            "release_version": template_version(),
            "reasons": []
            if installed is not None
            else [
                f"nothing installed for {project_key} at {source}; nobody looked, "
                "so this is not 'no changes'"
            ],
        }
        if arguments.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"upgrade check for {project_key}")
            print(f"  installed   {payload['installed_version']}  ({payload['installed_kind']})")
            print(f"  this release {payload['release_version']}")
            print(f"  verdict     {payload['verdict'].upper()}")
            for reason in payload["reasons"]:
                print(f"    - {reason}")
        return EXIT_OK if installed is not None else EXIT_MISSING

    if arguments.candidate is not None:
        candidate = read_document(arguments.candidate, what="candidate")
    else:
        # Rendering here would make this command write to `.generated/`, and this
        # command does not write. The operator renders with
        # `./deploy.sh --render-only` and passes the result.
        fail(
            EXIT_INPUT,
            "--candidate is required: this command renders nothing, because it "
            "writes nothing. Run ./deploy.sh --project ... --render-only first "
            "and pass .generated/<key>/outputs.json.",
        )
        raise AssertionError("unreachable")

    also: tuple[str, ...] = tuple(arguments.also)
    if arguments.verb == "verify":
        # `verify` asks a narrower question and asks it the other way round: is
        # what is installed what this checkout renders? So the candidate is the
        # left-hand side of "did we arrive", and any difference at all is the
        # answer.
        found = upgrade_plan.differences(installed or {}, candidate)
        payload = {
            "project": project_key,
            "verdict": upgrade_plan.OK if not found else upgrade_plan.BLOCKED,
            "template_version": template_version(),
            "differences": [
                {"path": item.path, "installed": item.installed, "candidate": item.candidate}
                for item in found
            ],
        }
        if arguments.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        elif found:
            print(f"verify: {len(found)} leaf/leaves differ from what this checkout renders")
            for item in found[:40]:
                print(f"  {item.path}: {item.installed!r} -> {item.candidate!r}")
        else:
            print(f"verify: {project_key} matches what this checkout renders.")
        return EXIT_OK if not found else EXIT_BLOCKED

    try:
        plan = upgrade_plan.build_plan(installed, candidate, also=also)
    except upgrade_plan.UpgradePlanError as error:
        fail(EXIT_BLOCKED, str(error))
        raise AssertionError("unreachable") from None

    if arguments.json:
        print(json.dumps(as_json(plan, project_key), indent=2, sort_keys=True))
    else:
        print(render_plan_text(plan, project_key))

    if plan.verdict == upgrade_plan.UNDETERMINED and installed is None:
        return EXIT_MISSING
    return EXIT_OK if not plan.blocks else EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())

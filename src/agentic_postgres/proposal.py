"""The proposal and approval records of a project's migration set (ADR 0243).

`bin/migrate.sh propose` writes `projects/<slug>/proposals/<set_digest>.json`:
what a reviewer reads before the set may reach a host -- the set's versions,
its lint result, its destructive statements, its apply on an empty cluster,
its final `api` surface against the reviewed contract, the approval-gate
check, the harness's cases and the capability contract's digest. `bin/migrate.sh
approve` writes `<set_digest>.approval.json` beside it, naming the proposal
FILE's own sha256, so an edited proposal invalidates its approval. Run 4's host
gate reads both and raises one of the four sentences below.

**The names are DECLARED, not authenticated** (D1864). There is no operator
identity in this product: the one resolver maps `SUDO_UID` to a Unix name and
says, in its own docstring, that *an identity supplied on a command line is not
an identity* -- and the host has one operator account. So every record says
`declared_by`, never `approved_by` or `author`, and carries `NOTE`: the records
stop an unreviewed or altered set reaching a host; they do not authenticate a
reviewer.

Pure logic: nothing here reads or writes a file. `bin/migrate.py` writes the
bytes `record_bytes` returns, with `O_EXCL`.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

#: Where a project's records live, beside its `migrations/` and `contracts/`.
PROPOSALS_SUBDIR = "proposals"

RECORD_SCHEMA_VERSION = 1
PROPOSAL_KIND = "migration_set_proposal"
APPROVAL_KIND = "migration_set_approval"

#: The sentence every record and every page repeats (ADR 0243).
NOTE = "The names in this record are declared, not authenticated (ADR 0243)."

#: A declared name: a letter, then letters, digits, space, `.`, `_`, `'`, `-`;
#: 2 to 64 characters. A name, not a credential: nothing here checks it.
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 ._'-]{1,63}$")

#: A set digest: the sha256 of the set's lock bytes, in full.
DIGEST = re.compile(r"^[0-9a-f]{64}$")

#: The four sentences the host gate raises (D1865), exactly; Run 4 raises them.
GATE_NO_PROPOSAL = "no proposal for this set {digest16}"
GATE_OTHER_SET = "the proposal names another set"
GATE_NO_APPROVAL = "approvals_required is 1 and the proposal has no approval"
GATE_BAD_APPROVAL = "the approval does not name this proposal, or names its proposer"

#: What `approve` says when the approver's name is the proposer's.
SECOND_NAME = "an approval needs a second name (ADR 0243)"


class ProposalError(ValueError):
    """A record, a name or a digest this release will not write or accept."""


def fold(name: str) -> str:
    """A name compared without case or spacing: `"Ada  Lovelace"` is `"ada lovelace"`."""
    return " ".join(name.split()).casefold()


def require_name(name: str) -> str:
    """The name as given, or ProposalError naming the rule it breaks."""
    # `fullmatch`: with `match`, `$` also matches before a trailing newline,
    # and `"ada\n"` would be a name.
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ProposalError(
            f"--by {name!r} is not a declared name: a letter, then letters, digits, spaces "
            "or . _ ' -, 2 to 64 characters"
        )
    return name


def require_digest(digest: str) -> str:
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
        raise ProposalError(
            f"{digest!r} is not a set digest: the 64 lowercase hex characters of the "
            "set's lock sha256, as the proposal's file name carries it"
        )
    return digest


def proposal_path(project_root: Path, digest: str) -> Path:
    """`projects/<slug>/proposals/<digest>.json` under ``project_root``."""
    return project_root / PROPOSALS_SUBDIR / f"{require_digest(digest)}.json"


def approval_path(project_root: Path, digest: str) -> Path:
    """`projects/<slug>/proposals/<digest>.approval.json` under ``project_root``."""
    return project_root / PROPOSALS_SUBDIR / f"{require_digest(digest)}.approval.json"


def record_bytes(record: dict[str, Any]) -> bytes:
    """Sorted keys, two-space indent, a trailing newline: the bytes a record is."""
    return (json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def build_proposal(
    *,
    project_slug: str,
    set_digest: str,
    set_root: str,
    versions: list[dict[str, str]],
    follows_release_version: str | None,
    follows_release_version_source: str | None,
    template_version: str,
    release_lock_sha256: str,
    destructive: list[dict[str, str]],
    dev_apply: dict[str, Any],
    surface: dict[str, list[dict[str, Any]]],
    approval_gate: list[dict[str, str]],
    harness: dict[str, Any],
    capability_contract_sha256: str | dict[str, str],
    declared_by: str,
    declared_at: str,
) -> dict[str, Any]:
    """The proposal record, every reading named (ADR 0243).

    `lint` is always `passed`: `propose` refuses a set the lint refuses and
    writes nothing. `dev_apply` carries its limits verbatim -- from empty, by
    psql as `migration_user`, over no existing rows (D1861) -- because a
    reading of an empty cluster cannot say what a change does to real data.
    `harness` counts cases ASKED, never outcomes (D1860).
    """
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "kind": PROPOSAL_KIND,
        "project_slug": project_slug,
        "set_digest": require_digest(set_digest),
        "set": {
            "root": set_root,
            "versions": versions,
            "follows_release_version": follows_release_version,
            "follows_release_version_source": follows_release_version_source,
        },
        "release": {
            "template_version": template_version,
            "release_lock_sha256": release_lock_sha256,
        },
        "lint": "passed",
        "destructive": destructive,
        "dev_apply": {
            **dev_apply,
            "from_empty": True,
            "applied_by": "psql as migration_user",
            "existing_rows": "none",
        },
        "surface": surface,
        "approval_gate": approval_gate,
        "harness": harness,
        "capability_contract_sha256": capability_contract_sha256,
        "declared_by": require_name(declared_by),
        "declared_at": declared_at,
        "note": NOTE,
    }


def read_proposal(data: bytes) -> dict[str, Any]:
    """A proposal record's content, or ProposalError saying why it is not one."""
    try:
        record = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ProposalError(f"the proposal is not a JSON document ({error})") from error
    if not isinstance(record, dict) or record.get("kind") != PROPOSAL_KIND:
        raise ProposalError(f"the file is not a {PROPOSAL_KIND} record")
    if record.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise ProposalError(
            f"the proposal is schema_version {record.get('schema_version')!r}; this release "
            f"reads {RECORD_SCHEMA_VERSION}"
        )
    require_digest(record.get("set_digest"))
    require_name(record.get("declared_by"))
    return record


def build_approval(proposal_data: bytes, declared_by: str, declared_at: str) -> dict[str, Any]:
    """The approval of one proposal FILE: its own sha256, never its parsed content.

    Refuses the proposer's own name, folded (`"Ada"` is `"ada "`): an approval
    needs a second name. That the second name is a second PERSON is what this
    record cannot know and says so (D1864).
    """
    proposal = read_proposal(proposal_data)
    require_name(declared_by)
    if fold(declared_by) == fold(proposal["declared_by"]):
        raise ProposalError(SECOND_NAME)
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "kind": APPROVAL_KIND,
        "proposal_sha256": sha256(proposal_data).hexdigest(),
        "set_digest": proposal["set_digest"],
        "declared_by": declared_by,
        "declared_at": declared_at,
        "note": NOTE,
    }


def check_names(proposal: dict[str, Any], approval: dict[str, Any]) -> None:
    """The two-name rule, for a reader holding both records (Run 4's gate).

    Raises ProposalError with GATE_BAD_APPROVAL when the approval's declared
    name folds to the proposer's.
    """
    if fold(str(approval.get("declared_by", ""))) == fold(str(proposal.get("declared_by", ""))):
        raise ProposalError(GATE_BAD_APPROVAL)


__all__ = [
    "APPROVAL_KIND",
    "DIGEST",
    "GATE_BAD_APPROVAL",
    "GATE_NO_APPROVAL",
    "GATE_NO_PROPOSAL",
    "GATE_OTHER_SET",
    "NAME",
    "NOTE",
    "PROPOSALS_SUBDIR",
    "PROPOSAL_KIND",
    "RECORD_SCHEMA_VERSION",
    "SECOND_NAME",
    "ProposalError",
    "approval_path",
    "build_approval",
    "build_proposal",
    "check_names",
    "fold",
    "proposal_path",
    "read_proposal",
    "record_bytes",
    "require_digest",
    "require_name",
]

"""The Reality Ledger: what each product concept is today, read by a program.

ADR 0247, `LEDGER-001`. The ledger is `docs/reality-ledger.yaml`; this module
loads it, validates it against `schemas/reality-ledger.schema.json`, answers the
guard's questions about it, and renders `docs/reality-ledger.md`
(`bin/render-reality-ledger.py`).

Every guard question returns the list of rows that fail it, never a boolean, so
a refusal can name what it refused. Evidence is resolved in two halves. In
every checkout, a name must be a claim `evidence_claims.CLAIMS` names or a
`capacity.ENVELOPE` subject. Where the checkout holds an evidence document
(`evidence/*` is gitignored, so CI's does not -- D2021), a claim must also be
`passed` in the NEWEST `evidence/session-NN.json` by session number. A claim
that did not pass is not evidence, and a half that could not be read is
reported as unread, never as held (ADR 0195).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from agentic_postgres import REPO_ROOT, capacity
from agentic_postgres.evidence_claims import CLAIMS

LEDGER_PATH = REPO_ROOT / "docs" / "reality-ledger.yaml"
SCHEMA_PATH = REPO_ROOT / "schemas" / "reality-ledger.schema.json"
PAGE_PATH = REPO_ROOT / "docs" / "reality-ledger.md"
EVIDENCE_DIR = REPO_ROOT / "evidence"

STATUSES = ("available", "beta", "planned", "not_metered", "not_offered")

#: The statuses a customer can reach. Only these may carry `evidence` and
#: `controls`; every other status carries neither (ADR 0247, D2009).
REACHABLE = frozenset({"available", "beta"})

#: The specification's §59 list, lower-cased. A release may not say these
#: about itself; the guard reads every row's `customer_text` for them
#: (ADR 0247 item 4). Session 42 extends the guard to the console's served
#: strings and the API's.
FORBIDDEN_WORDS = (
    "production-ready",
    "enterprise-grade",
    "highly available",
    "fault tolerant",
    "multi-region",
    "serverless",
    "autoscaling",
    "zero downtime",
)

_EVIDENCE_NAME = re.compile(r"^session-(\d+)\.json$")


class LedgerError(ValueError):
    """The ledger does not validate."""


def load(path: Path = LEDGER_PATH) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise LedgerError(f"{path.name}: the ledger is not a mapping")
    return document


def validate(document: dict[str, Any]) -> None:
    """The schema, then what a schema cannot say: ids are unique."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    if errors:
        rendered = "; ".join(
            f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise LedgerError(f"{SCHEMA_PATH.name}: {rendered}")
    ids = [row["id"] for row in document["rows"]]
    duplicated = sorted({identifier for identifier in ids if ids.count(identifier) > 1})
    if duplicated:
        raise LedgerError(f"rows share an id: {duplicated}")


def newest_evidence(directory: Path = EVIDENCE_DIR) -> tuple[Path, dict[str, Any]] | None:
    """The merged evidence document with the highest session number, or `None`
    when this checkout holds none -- `evidence/*` is gitignored (runbook §6.1),
    so a fresh clone, CI's included, has nothing to read (D2021)."""
    found = [
        (int(match.group(1)), path)
        for path in directory.glob("session-*.json")
        if (match := _EVIDENCE_NAME.match(path.name))
    ]
    if not found:
        return None
    _, path = max(found)
    return path, json.loads(path.read_text(encoding="utf-8"))


def _is_subject(name: str) -> bool:
    return any(measurement.subject == name for measurement in capacity.ENVELOPE)


def known(name: str) -> bool:
    """A claim `evidence_claims.CLAIMS` names, or an envelope subject. Readable
    in every checkout; whether the claim PASSED needs an evidence document."""
    return name in CLAIMS or _is_subject(name)


def resolves(name: str, evidence: dict[str, Any]) -> bool:
    """A claim `passed` in this evidence document, or an envelope subject."""
    if _is_subject(name):
        return True
    reported = evidence.get("claims", {}).get(name)
    return name in CLAIMS and isinstance(reported, dict) and reported.get("status") == "passed"


def evidence_problems(document: dict[str, Any], evidence: dict[str, Any] | None) -> list[str]:
    """Rows whose evidence does not hold, each with the reason.

    With `evidence=None` (no document in this checkout) the status rules and the
    names are checked and the PASSED half is not -- the caller reports that it
    was not read, never that it held (ADR 0195)."""
    problems: list[str] = []
    for row in document["rows"]:
        names = list(row["evidence"])
        if row["status"] in REACHABLE and not names:
            problems.append(f"{row['id']}: {row['status']} with no evidence")
        if row["status"] not in REACHABLE and names:
            problems.append(f"{row['id']}: {row['status']} carries evidence {names}")
        labelled = [("evidence", name) for name in names]
        if row["today_evidence"] is not None:
            labelled.append(("today_evidence", row["today_evidence"]))
        for field, name in labelled:
            if not known(name):
                problems.append(
                    f"{row['id']}: {field} {name!r} is no claim and no envelope subject"
                )
            elif evidence is not None and not resolves(name, evidence):
                problems.append(f"{row['id']}: {field} {name!r} did not pass")
    return problems


def unreachable_rows_with_controls(document: dict[str, Any]) -> list[str]:
    """The fake-complete guard: a control on a concept a customer cannot reach."""
    return [
        f"{row['id']}: {row['status']} with controls {row['controls']}"
        for row in document["rows"]
        if row["status"] not in REACHABLE and row["controls"]
    ]


def forbidden_words_in(document: dict[str, Any]) -> list[str]:
    """Rows whose `customer_text` uses a §59 word, case-insensitively."""
    problems: list[str] = []
    for row in document["rows"]:
        text = row["customer_text"].lower()
        for word in FORBIDDEN_WORDS:
            if re.search(rf"(?<![a-z0-9-]){re.escape(word)}(?![a-z0-9-])", text):
                problems.append(f"{row['id']}: customer_text uses {word!r}")
    return problems


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def render(document: dict[str, Any]) -> str:
    rows = document["rows"]
    lines: list[str] = [
        "# Reality Ledger",
        "",
        "**Generated by `bin/render-reality-ledger.py --write` from",
        "`docs/reality-ledger.yaml`. Do not edit by hand.**",
        "",
        "What each product concept is **today** (ADR 0247). A program reads the YAML",
        "this page is rendered from: a concept is `available` or `beta` only when a",
        "claim that proves it passed on a sweep, a concept a customer cannot reach",
        "carries no control, and no customer sentence below uses a word the release",
        "may not use. `not_offered` means cut by decision, not postponed;",
        "`not_metered` means nothing reads it.",
        "",
        "| Concept | Status | Built in session |",
        "|---|---|---|",
    ]
    for row in rows:
        target = "—" if row["target_session"] is None else str(row["target_session"])
        lines.append(f"| [{_cell(row['concept'])}](#{row['id']}) | `{row['status']}` | {target} |")
    lines += ["", "---", ""]
    for row in rows:
        lines += [
            f'<a id="{row["id"]}"></a>',
            "",
            f"## {row['concept']}",
            "",
            f"`{row['id']}` · **{row['status']}** · since Session {row['since_session']}",
            "",
            f"**What a customer reads.** {_cell(row['customer_text'])}",
            "",
            f"**Today.** {_cell(row['today'])}",
            "",
        ]
        if row["today_evidence"] is not None:
            lines += [f"*Proved by:* `{row['today_evidence']}`.", ""]
        if row["evidence"]:
            names = ", ".join(f"`{name}`" for name in row["evidence"])
            lines += [f"*Customer-facing evidence:* {names}.", ""]
        lines += [
            f"**Stage 5.** {_cell(row['stage5_reality'])}",
            "",
            f"**Eventually (not promised).** {_cell(row['eventual'])}",
            "",
        ]
        if row["controls"]:
            controls = ", ".join(f"`{control}`" for control in row["controls"])
            lines += [f"*Controls:* {controls}.", ""]
    return "\n".join(lines).rstrip() + "\n"

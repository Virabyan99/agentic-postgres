"""The SQL reader is quote-aware (Session 42, D2544, D2565).

`sql_surface.sql_only` cut every line at its first `--`, and its docstring
promised that no template held `--` inside a string literal. When one did, the
closing quote went with the cut and every later reader -- the lint, the
destructive reading, the published surface -- read the rest of the file as one
string (Session 41 measured 10 destructive findings where 12 were due). The
reader is now a character scanner with three states -- code, a `'...'`
literal (`''` is a quote), a `"..."` identifier -- and drops `--` to the end
of the line only in code. The class guard replaces the docstring's promise:
every template the product reads ends its scan in code.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from agentic_postgres import migrations, sql_surface

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "projects" / "example"

#: Every template the product reads: the release's and every project set's.
TEMPLATES = sorted(
    [*(REPO_ROOT / "migrations" / "templates").glob("*.sql"),
     *(REPO_ROOT / "projects").glob("*/migrations/templates/*.sql")]
)  # fmt: skip


def _set_with(tmp_path: Path, up: str) -> migrations.MigrationSet:
    """The example set copied, with ONE more migration whose up section is `up`
    (test_change_proposal.py's shape)."""
    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root)
    manifest_path = root / "migrations" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = copy.deepcopy(manifest["migrations"][-1])
    entry.update(version="20261001120099", name="scratch", template="templates/0099-scratch.sql")
    manifest["migrations"].append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (root / "migrations" / "templates" / "0099-scratch.sql").write_text(
        "-- migrate:up\nSET LOCAL ROLE {{object_owner}};\n"
        f"{up}\nRESET ROLE;\n-- migrate:down\n"
        "DO $$ BEGIN RAISE EXCEPTION 'AP900: fix-forward only'; END $$;\n",
        encoding="utf-8",
    )
    return migrations.MigrationSet(label="project", root=root / "migrations")


def _scratch(tmp_path: Path, up: str) -> list[tuple[str, str]]:
    found = migrations.destructive_findings(_set_with(tmp_path, up))
    return [(f.kind, f.object) for f in found if f.version == "20261001120099"]


def test_a_dash_dash_inside_a_literal_is_kept(tmp_path: Path) -> None:
    """D2544: a `--` inside a literal is part of the literal, so the statement
    after it is still read -- the drop is found."""
    assert sql_surface.sql_only("SELECT 'a -- b'; -- a comment") == "SELECT 'a -- b'; "
    up = "INSERT INTO app.notes (title) VALUES ('a -- b');\nDROP TABLE app.scratch;"
    assert ("drop_table", "app.scratch") in _scratch(tmp_path, up)


def test_a_comment_after_a_literal_is_dropped(tmp_path: Path) -> None:
    """The control: a comment in code is still a comment -- a `DROP` in one is
    not a finding -- and `''` inside a literal, and `--` inside a quoted
    identifier, are read as what they are."""
    assert _scratch(tmp_path, "SELECT 'x'; -- DROP TABLE app.y;") == []
    assert sql_surface.sql_only("SELECT 'it''s -- fine', \"odd--name\" -- gone\nFROM t") == (
        "SELECT 'it''s -- fine', \"odd--name\" \nFROM t"
    )
    assert sql_surface.sql_only("a -- one\nb -- two\nc") == "a \nb \nc"


def test_every_template_ends_its_scan_outside_a_literal() -> None:
    """The class guard (D2565): the scanner's final state is code for every
    template the product reads -- the reader's own state, where the old
    docstring held a promise. A template that ended inside a literal would be
    one this reader misreads from that quote on."""
    assert len(TEMPLATES) > 40, TEMPLATES
    unbalanced = {
        path.relative_to(REPO_ROOT).as_posix(): state
        for path in TEMPLATES
        if (state := sql_surface.scan_end_state(path.read_text(encoding="utf-8"))) != "code"
    }
    assert unbalanced == {}, unbalanced

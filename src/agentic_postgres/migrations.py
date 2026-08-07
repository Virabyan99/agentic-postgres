"""Migration manifest, the purpose-built renderer, and the released lock.

ADR 0028. Two artifacts exist and only one of them is immutable.

`migrations/templates/*.sql` are **templates**: they carry `{{placeholder}}`
markers where a project-scoped identifier goes, because every role name and the
database name are derived per project by Session 1's naming rules. The bytes
PostgreSQL executes are the *rendered payload*, and that is what a checksum
describes. Checksumming the template would mean two projects record the same
digest for different SQL, and a change to a naming rule would pass unnoticed
because the source bytes did not move.

**The renderer is deliberately incapable.** It performs one operation:
replacing `{{name}}` with a value resolved from the rendered `outputs.json`
document, quoted according to a type declared in the manifest. There is no
conditional, no loop, no expression, no partial application, no filter and no
current-deployment metadata. Two renders of one input are byte-identical, and
that is checkable offline with no cluster.

The reason it is not Jinja2 -- which is already a transitive dependency -- is
Run 7 of Session 2. `render-config.py` performed a substitution that also
matched the comment documenting the placeholder, and produced a Traefik file
that Traefik silently discarded. The failure mode of a capable template engine
is not an error; it is a plausible wrong answer. So: explicit delimiters, a
closed set of names, a declared type per name, and a hard failure on anything
left over.

**What the lock records.** `released.lock.json` is committed, and the projects
it must cover are described by gitignored manifests -- so it cannot hold a
per-project rendered checksum. It holds three things per migration instead: the
template digest, the declared placeholder set, and the digest of the payload
rendered against a synthetic *canonical identity*. Together those pin the
template, the substitution surface, and the renderer's own behaviour. The
per-project rendered digest is recorded in the database ledger when the
migration is applied, and the preflight compares the two. That split is why the
plan describes five sources rather than four.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from agentic_postgres import REPO_ROOT, config

MIGRATIONS_ROOT = REPO_ROOT / "migrations"
MANIFEST_PATH = MIGRATIONS_ROOT / "manifest.json"
LOCK_PATH = MIGRATIONS_ROOT / "released.lock.json"

#: Explicit, two-character delimiters that appear in no SQL this project
#: writes. A bare `$name` would collide with dollar-quoting, and `%s` with
#: client-side parameter binding -- both of which appear in real migrations.
PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")

#: Anything resembling an unresolved marker after rendering. Broader than
#: PLACEHOLDER on purpose: `{{Name}}` and `{{ name }}` are typos that the
#: substitution pass would silently leave in place, and SQL containing braces
#: it did not mean is not something to discover on a host.
RESIDUE = re.compile(r"\{\{|\}\}")

#: The two types a placeholder may have. `identifier` is quoted as a SQL
#: identifier; `literal` is quoted as a string literal. There is no `raw`, and
#: adding one would make the renderer capable of emitting arbitrary SQL from a
#: manifest -- which is the thing it exists not to do.
PLACEHOLDER_TYPES = frozenset({"identifier", "literal"})


class MigrationError(ValueError):
    """The manifest, a template, or the lock is not usable as declared."""


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Read and validate the ordered source of record."""
    if not path.is_file():
        raise MigrationError(f"the migration manifest is missing: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise MigrationError(f"{path} is not valid JSON: {error}") from error

    config.validate_against_schema(document, "migration-manifest.schema.json")
    _assert_manifest_semantics(document, path.parent)
    return document


def _assert_manifest_semantics(document: dict[str, Any], root: Path) -> None:
    versions = [entry["version"] for entry in document["migrations"]]

    duplicates = sorted({v for v in versions if versions.count(v) > 1})
    if duplicates:
        raise MigrationError(f"duplicate migration versions: {duplicates}")

    if versions != sorted(versions):
        raise MigrationError(
            f"migrations are not in ascending version order: {versions}. "
            "Order is the applied order; a manifest that sorts differently than it "
            "reads is one where a reviewer and dbmate disagree about what runs first."
        )

    declared = set(document["placeholders"])
    for entry in document["migrations"]:
        template = root / entry["template"]
        if not template.is_file():
            raise MigrationError(f"{entry['version']}: template is missing: {template}")

        used = set(PLACEHOLDER.findall(template.read_text(encoding="utf-8")))
        promised = set(entry["placeholders"])

        unknown = sorted(used - declared)
        if unknown:
            raise MigrationError(
                f"{entry['version']}: template uses placeholders the manifest does not "
                f"declare: {unknown}"
            )
        undeclared = sorted(used - promised)
        if undeclared:
            raise MigrationError(
                f"{entry['version']}: template uses {undeclared}, which this migration's "
                "own placeholder list omits"
            )
        # Declared-but-unused is an error, not a tidiness complaint: it usually
        # means a substitution was removed from the SQL and the declaration was
        # left behind, and the next reader takes the declaration as evidence
        # that the value still reaches the migration.
        unused = sorted(promised - used)
        if unused:
            raise MigrationError(
                f"{entry['version']}: declares placeholders its template never uses: {unused}"
            )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def quote_identifier(value: str) -> str:
    """Quote as a SQL identifier, refusing anything that is not already one.

    The refusal is the point. Every identifier reaching here was derived by
    `naming`, which validates it; a value that fails this check means something
    other than `naming` produced it, and quoting it anyway would turn a naming
    bug into valid SQL against the wrong object.
    """
    if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
        raise MigrationError(f"not a bare lowercase SQL identifier: {value!r}")
    if len(value.encode("utf-8")) > 63:
        raise MigrationError(f"identifier exceeds 63 bytes and would be truncated: {value!r}")
    return '"' + value + '"'


def quote_literal(value: str) -> str:
    if not isinstance(value, str):
        raise MigrationError(f"literal placeholder is not a string: {value!r}")
    if "\x00" in value:
        raise MigrationError("literal placeholder contains a NUL byte")
    return "'" + value.replace("'", "''") + "'"


def resolve_placeholders(
    manifest: dict[str, Any], outputs: dict[str, Any], names: list[str]
) -> dict[str, str]:
    """Resolve declared placeholders from a rendered outputs document.

    Values come from `outputs.json` and nowhere else. That document is already
    the single authority for every derived identity (ADR 0002), so a renderer
    that consulted `naming` directly would be a second derivation path with the
    same failure mode ADR 0023 records.
    """
    resolved: dict[str, str] = {}
    for name in names:
        specification = manifest["placeholders"][name]
        value: Any = outputs
        for step in specification["source"].split("."):
            if not isinstance(value, dict) or step not in value:
                raise MigrationError(
                    f"placeholder {name!r} reads {specification['source']!r}, "
                    "which the rendered document does not have"
                )
            value = value[step]

        if specification["type"] == "identifier":
            resolved[name] = quote_identifier(value)
        else:
            resolved[name] = quote_literal(value)
    return resolved


def render(template_text: str, values: dict[str, str]) -> str:
    """Substitute, then refuse anything left over.

    The residue check is what makes a typo loud. `{{ owner }}` with spaces does
    not match the substitution pattern, so without this it would reach the
    database as literal text inside otherwise valid SQL.
    """
    missing = sorted(set(PLACEHOLDER.findall(template_text)) - set(values))
    if missing:
        raise MigrationError(f"no value supplied for placeholders: {missing}")

    rendered = PLACEHOLDER.sub(lambda match: values[match.group(1)], template_text)

    residue = RESIDUE.search(rendered)
    if residue is not None:
        line = rendered[: residue.start()].count("\n") + 1
        raise MigrationError(
            f"unresolved placeholder syntax survives rendering at line {line}. "
            "A marker the substitution pattern did not match is a typo, not a literal."
        )
    return rendered


def render_migration(
    entry: dict[str, Any],
    manifest: dict[str, Any],
    outputs: dict[str, Any],
    root: Path = MIGRATIONS_ROOT,
) -> str:
    template = (root / entry["template"]).read_text(encoding="utf-8")
    values = resolve_placeholders(manifest, outputs, entry["placeholders"])
    return render(template, values)


def digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The released lock
# ---------------------------------------------------------------------------


def canonical_outputs(manifest: dict[str, Any]) -> dict[str, Any]:
    """A synthetic document that resolves every declared placeholder.

    Built from the manifest's own `source` paths so that adding a placeholder
    cannot leave the canonical identity behind -- which would otherwise show up
    as a lock that silently stopped covering the new substitution.
    """
    document: dict[str, Any] = {}
    for name, specification in manifest["placeholders"].items():
        steps = specification["source"].split(".")
        node = document
        for step in steps[:-1]:
            node = node.setdefault(step, {})
        node[steps[-1]] = f"canonical_{name}" if specification["type"] == "identifier" else name
    return document


def build_lock(manifest: dict[str, Any], root: Path = MIGRATIONS_ROOT) -> dict[str, Any]:
    """Produce the lock's content. `bin/migrate.sh freeze-lock` writes it.

    Separated from the command so that verifying a lock and creating one share
    exactly one implementation. A gate that verified with different code than
    the one that wrote it would be checking its own arithmetic.
    """
    canonical = canonical_outputs(manifest)
    entries = []
    for entry in manifest["migrations"]:
        template_text = (root / entry["template"]).read_text(encoding="utf-8")
        entries.append(
            {
                "version": entry["version"],
                "name": entry["name"],
                "template": entry["template"],
                "template_sha256": digest(template_text),
                "placeholders": sorted(entry["placeholders"]),
                "canonical_render_sha256": digest(
                    render(
                        template_text,
                        resolve_placeholders(manifest, canonical, entry["placeholders"]),
                    )
                ),
            }
        )
    return {"schema_version": 1, "migrations": entries}


def load_lock(path: Path = LOCK_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise MigrationError(
            f"the released lock is missing: {path}. It is produced by "
            "`bin/migrate.sh freeze-lock` from a clean tree, reviewed, and committed "
            "before the gate runs; the gate verifies it and never writes it."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def verify_lock(
    manifest: dict[str, Any], lock: dict[str, Any], root: Path = MIGRATIONS_ROOT
) -> None:
    """Refuse on any disagreement, naming which kind it is.

    The three failures are distinguished because the operator response differs:
    an edited template is a mistake to revert, a removed migration is history
    being rewritten, and a changed canonical digest with an unchanged template
    means the *renderer* moved under a set of templates nobody touched.
    """
    expected = build_lock(manifest, root)

    have = {entry["version"]: entry for entry in lock.get("migrations", [])}
    want = {entry["version"]: entry for entry in expected["migrations"]}

    removed = sorted(set(have) - set(want))
    if removed:
        raise MigrationError(
            f"the lock records migrations the manifest no longer has: {removed}. "
            "An applied migration is immutable; the remedy for a mistake is a new "
            "migration, never a deletion."
        )
    added = sorted(set(want) - set(have))
    if added:
        raise MigrationError(
            f"migrations are absent from the released lock: {added}. Nothing may be "
            "applied to a non-disposable target before its entry is committed."
        )

    for version in sorted(want):
        for field in ("template", "template_sha256", "placeholders", "canonical_render_sha256"):
            if have[version].get(field) != want[version][field]:
                raise MigrationError(
                    f"{version}: {field} disagrees with the released lock. "
                    f"locked={have[version].get(field)!r} actual={want[version][field]!r}"
                )


__all__ = [
    "LOCK_PATH",
    "MANIFEST_PATH",
    "MIGRATIONS_ROOT",
    "MigrationError",
    "build_lock",
    "canonical_outputs",
    "digest",
    "load_lock",
    "load_manifest",
    "quote_identifier",
    "quote_literal",
    "render",
    "render_migration",
    "resolve_placeholders",
    "verify_lock",
]

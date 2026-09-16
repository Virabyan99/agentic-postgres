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
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from agentic_postgres import REPO_ROOT, config, sql_surface

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


#: Where a project's own set may live, relative to the repository root. The
#: shape is fixed by ADR 0198 and the project schema's pattern agrees with it;
#: a set outside the checkout would be SQL applied by a release that does not
#: contain it, which is the state `installed_release.assert_clean` exists to
#: refuse (D1087).
PROJECT_SETS_DIRECTORY = "projects"

#: The only outputs paths a PROJECT template's placeholders may read.
#:
#: The release's own manifest may read anything the outputs document holds --
#: it is reviewed with the release. A project's may read the six request roles
#: and the database name, and nothing else: not `app_runtime`, not
#: `migration_user`, not `backup_user`, not a container name, not a URL. The
#: point is not that those values are secret; it is that a project's SQL has no
#: business naming the platform's own identities, and a placeholder is the only
#: way a value reaches a template at all.
PROJECT_PLACEHOLDER_SOURCES = frozenset(
    {
        "database.roles.object_owner",
        "database.roles.authenticated",
        "database.roles.anon",
        "database.roles.agent_reader",
        "database.roles.agent_writer",
        "database.roles.api_documentation",
        "database.name",
    }
)

#: The one role preamble a project template may set. `SET LOCAL ROLE` and not
#: `SET ROLE`: local is scoped to the transaction dbmate wraps the migration in,
#: so a template that forgot to `RESET ROLE` cannot leak the owner's authority
#: into whatever runs next on that connection.
PROJECT_ROLE_PREAMBLE = "SET LOCAL ROLE {{object_owner}}"

#: What a project's `down` block must raise. The same refusal every released
#: platform migration carries: this plane is fix-forward (D912), and a project
#: that shipped a working rollback would be one `dbmate down` away from dropping
#: a tenant's table on a host.
PROJECT_DOWN_SENTINEL = "AP900"

SET_ROLE = re.compile(r"\bSET\s+(?:LOCAL\s+)?ROLE\b[^;]*", re.IGNORECASE)

#: What a project's SQL may not contain, and why, for each pattern.
#:
#: **Public since Session 22** (ADR 0203), because a project's SEED runs through
#: the same plane as its migrations, as the same `migration_user`, under the same
#: `SET LOCAL ROLE` -- so the boundary is the same boundary and there is one
#: table of it. `dev_environment.lint_seed` reads this and adds the rule a seed
#: has and a migration does not: a seed creates nothing at all.
FORBIDDEN_STATEMENTS = (
    (re.compile(r"\bapp_private\b", re.IGNORECASE), "names the app_private schema"),
    (re.compile(r"\b(CREATE|ALTER|DROP)\s+ROLE\b", re.IGNORECASE), "creates or alters a role"),
    (re.compile(r"\b(CREATE|ALTER|DROP)\s+SCHEMA\b", re.IGNORECASE), "creates or alters a schema"),
    (
        re.compile(r"\b(CREATE|ALTER|DROP)\s+EXTENSION\b", re.IGNORECASE),
        "creates or alters an extension",
    ),
    (
        re.compile(r"\bALTER\s+DEFAULT\s+PRIVILEGES\b", re.IGNORECASE),
        "alters default privileges",
    ),
    (re.compile(r"\bSECURITY\s+LABEL\b", re.IGNORECASE), "sets a security label"),
    (re.compile(r"\bCREATE\s+(OR\s+REPLACE\s+)?RULE\b", re.IGNORECASE), "creates a rule"),
    (re.compile(r"\bCREATE\s+PUBLICATION\b", re.IGNORECASE), "creates a publication"),
    (re.compile(r"\bCREATE\s+SUBSCRIPTION\b", re.IGNORECASE), "creates a subscription"),
    (re.compile(r"\bCOPY\b[^;]*\bFROM\s+PROGRAM\b", re.IGNORECASE), "runs a program"),
)

#: A table created in `app` -- the schema whose FORCE row-level security is what
#: makes every SECURITY DEFINER write in this product safe (ADR 0003, 0005).
_CREATE_APP_TABLE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?app\.(\w+)", re.IGNORECASE
)
_FORCE_RLS = re.compile(
    r"\bALTER\s+TABLE\s+app\.(\w+)\s+FORCE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE
)
_ENABLE_RLS = re.compile(
    r"\bALTER\s+TABLE\s+app\.(\w+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE
)


class MigrationError(ValueError):
    """The manifest, a template, or the lock is not usable as declared."""


class ProjectSetError(MigrationError):
    """A project's migration set is not something this release may apply.

    Its own class because the remedy differs from every other MigrationError
    here: those are a mistake in the release, which the release fixes; this is a
    refusal addressed to an adopter about their own file, and the operator
    reading it did not write the code that raised it.
    """


@dataclass(frozen=True)
class MigrationSet:
    """One directory of migrations, its manifest and its lock.

    Frozen, and carrying its own paths rather than deriving them at each use,
    because D1088 is what happens when a location is a default instead of a
    value: `migrations.py` was already parameterised by root and path -- every
    function took one -- and the hardcoding an adopter hit lived in the eleven
    CALLERS that used the default. A value that must be passed cannot be
    defaulted by accident.

    ``label`` is `release` or `project`, and it is not decoration: `verify_lock`
    applies the version rule to a project lock and not to the release's, and
    `record_ledger` needs to say which set a digest came from.
    """

    label: str
    root: Path

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def lock_path(self) -> Path:
        return self.root / "released.lock.json"

    @property
    def is_project(self) -> bool:
        return self.label == "project"

    def load_manifest(self) -> dict[str, Any]:
        return load_manifest(self.manifest_path)

    def load_lock(self) -> dict[str, Any]:
        return load_lock(self.lock_path)


def release_set() -> MigrationSet:
    """The release's own set. Always present, always applied first."""
    return MigrationSet(label="release", root=MIGRATIONS_ROOT)


def project_set_from(document: dict[str, Any], repo_root: Path = REPO_ROOT) -> MigrationSet | None:
    """The project's set, if the rendered document names one.

    Reads the DEPLOYED DOCUMENT and not the project manifest, for ADR 0002's
    reason: `outputs.json` is the one place every derived fact is read from, and
    a second reader of the manifest would be a second derivation path. A version
    16 document has no `migrations` block at all and answers None, which is what
    every project without a set answers too.
    """
    block = (document.get("migrations") or {}).get("project_set")
    if not block:
        return None
    root = repo_root / block["root"]
    return MigrationSet(label="project", root=root / "migrations")


def sets_for(document: dict[str, Any], repo_root: Path = REPO_ROOT) -> tuple[MigrationSet, ...]:
    """Every set this project applies, in the order it applies them.

    **The release's first, always.** A project's versions are required to sort
    after the release lock's newest at freeze (`follows_release_version`), so
    this order is also the version order dbmate will use -- and rig 20a measured
    what happens when it is not: `up --strict` exits 2 having applied nothing,
    naming both versions (D1098).

    Every caller that means *every migration this project applies* calls this.
    Every caller that means *the release's migrations* keeps `load_manifest()`
    and says so in a comment -- that distinction is the whole of D1088, and an
    uncommented default is where it comes back.
    """
    project = project_set_from(document, repo_root)
    return (release_set(),) if project is None else (release_set(), project)


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


def newest_release_version(root: Path = MIGRATIONS_ROOT) -> str:
    """The newest version the release's own manifest declares.

    Read from the manifest rather than from the lock so that `freeze-lock` on a
    release that has just gained a migration computes the same answer before and
    after its own lock is written.
    """
    versions = [entry["version"] for entry in load_manifest(root / "manifest.json")["migrations"]]
    return max(versions)


def build_lock(
    manifest: dict[str, Any],
    root: Path = MIGRATIONS_ROOT,
    *,
    follows_release_version: str | None = None,
) -> dict[str, Any]:
    """Produce the lock's content. `bin/migrate.sh freeze-lock` writes it.

    Separated from the command so that verifying a lock and creating one share
    exactly one implementation. A gate that verified with different code than
    the one that wrote it would be checking its own arithmetic.

    ``follows_release_version`` makes this a PROJECT lock: schema version 2, and
    the release version every migration in this set must sort after. It is
    recorded rather than recomputed at verify time, deliberately -- the release
    gains migrations after a project freezes, and a check that compared against
    the release's CURRENT newest would invalidate every project lock the day a
    platform migration shipped. What the rule actually needs is that the freeze
    was done under it, and the recorded value is that evidence (ADR 0198).
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
    if follows_release_version is None:
        return {"schema_version": 1, "migrations": entries}
    return {
        "schema_version": 2,
        "follows_release_version": follows_release_version,
        "migrations": entries,
    }


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
    follows = lock.get("follows_release_version")
    expected = build_lock(manifest, root, follows_release_version=follows)

    if follows is not None:
        _assert_follows_release_version(manifest, follows)

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


def _assert_follows_release_version(manifest: dict[str, Any], follows: str) -> None:
    """Every version in a project set sorts after the recorded release version.

    **This no longer prevents anything the cluster would refuse** (ADR 0206,
    D1288). It was written when the two sets rendered into ONE directory and
    applied through ONE `dbmate` invocation against ONE
    `app_private.schema_migrations`, so their versions shared a single ordering
    space: there, a project version below an applied release version was an
    `up --strict` refusal on a deployed cluster and a silent apply on a fresh
    one, which is the same set producing two different schemas (rig 20a,
    D1098). Since ADR 0206 a project set renders to its own directory and
    applies against `app_private.project_schema_migrations`, and **each set is
    ordered against its own applied set only.**

    **What this docstring used to say was false, and Session 24's trip is where
    it was refuted.** It read: *"The direction is not symmetric and that is the
    whole rule ... So the rule constrains only what a project may author, and
    never what the release may."* It conflated *authored later* with *sorts
    higher*. Versions are authoring-date stamps, so a project set stamped ahead
    of the release's own clock -- stamped that way to clear THIS rule -- left
    the release a window in which anything it authored sorted BELOW an applied
    project migration. Session 24's migration `0032` landed in that window and
    beta refused the deploy at step 6 having applied nothing. The demand was
    never one-directional: with one shared ordering space the two climb past
    each other indefinitely, and no pair of stamping rules satisfies both for an
    arbitrary sequence of releases. That is why the repair was structural rather
    than a re-stamp.

    **So what survives here is a record, not a guard.** It says which release a
    set was reviewed against, and refuses a set whose versions disagree with its
    own record. ADR 0206 kept it deliberately: removing a released guard is a
    separate decision from the one that ADR took.

    **What it should do when a set was frozen against an EARLIER release is
    undecided, and it is the on-ramp session's.** Today the only way forward is
    to re-freeze the project lock, which moves `follows_release_version` to the
    release in hand; nothing has decided whether that is the intended workflow
    or a leftover of the ordering space ADR 0206 removed. Said here because a
    reader who meets the refusal has no other place to find it.
    """
    if not re.fullmatch(r"[0-9]{14}", follows):
        raise ProjectSetError(
            f"follows_release_version is not a 14-digit version stamp: {follows!r}"
        )
    offending = sorted(
        entry["version"] for entry in manifest["migrations"] if entry["version"] <= follows
    )
    if offending:
        raise ProjectSetError(
            f"these project migrations do not sort after the release version this set was "
            f"frozen against ({follows}): {offending}. Since ADR 0206 the two sets render "
            "into separate directories and apply into separate tables, so this is no "
            "longer an ordering a cluster would refuse: follows_release_version is the "
            "record of which release this set was reviewed against, and these versions "
            "disagree with that record.\n\n"
            "If these migrations are NOT yet applied anywhere, re-stamp them above "
            f"{follows} and freeze again.\n\n"
            "If they ARE applied -- a set authored against an EARLIER release -- then "
            "there is no supported way forward today, and this refusal is the product "
            "being honest rather than helpful. Re-freezing does not help: "
            "`freeze-lock --project` records THIS checkout's newest release version, so "
            "it would compute the same floor and refuse again. Re-stamping is worse: it "
            "amends applied migrations (D912 forbids it), and ADR 0206's one-time ledger "
            "move matches rows BY VERSION, so re-stamped versions would move nothing and "
            "the deploy would then re-apply SQL against objects that already exist. "
            "Nothing in this release lets a set declare the release it was actually "
            "frozen against. That gap is recorded in docs/scope-closure.md as the "
            "on-ramp question and is a product decision, not an operator error (D1288)."
        )


# ---------------------------------------------------------------------------
# The lint (TEN-SET-002)
# ---------------------------------------------------------------------------


def lint_project_set(project: MigrationSet, release: MigrationSet | None = None) -> None:
    """Refuse a project set before anything renders it. ADR 0198.

    **Every refusal here is a boundary, not a style rule.** The product's whole
    security argument is that PostgreSQL is the final authorization authority
    and that `app_private` -- the pre-request hook, the agent audit, the quota
    and idempotency tables -- is unreachable from anything a caller can address.
    A project's SQL runs as `object_owner` through the same plane as the
    release's, so without this it could revoke the hook, grant itself a role, or
    drop a platform view, and the deploy would apply it without comment.

    The refusals are stated as a list rather than as a policy engine on purpose.
    A lint that could be configured is a lint an adopter would configure, and
    §9's stop conditions say so directly: if a set needs `app_private`, a role,
    or the pre-request hook to do something an adopter reasonably wants, that is
    a product decision for a later session, recorded -- not an exception here.
    """
    release = release or release_set()
    manifest = project.load_manifest()

    # The placeholder allowlist. Checked against the manifest's declared
    # SOURCES rather than against placeholder names, because the name is the
    # adopter's to choose and the source is what actually reaches the SQL.
    for name, specification in manifest["placeholders"].items():
        source = specification["source"]
        if source not in PROJECT_PLACEHOLDER_SOURCES:
            raise ProjectSetError(
                f"{project.root}: placeholder {name!r} reads {source!r}, which a project set "
                f"may not read. Allowed: {sorted(PROJECT_PLACEHOLDER_SOURCES)}. A project's "
                "SQL names the request roles and its own database, and none of the platform's "
                "other identities."
            )

    release_surface = sql_surface.final_surface(release.load_manifest(), release.root)
    release_owns = sql_surface.published_names(release_surface)

    for entry in manifest["migrations"]:
        template = (project.root / entry["template"]).read_text(encoding="utf-8")
        applied = sql_surface.statements(template)
        where = f"{project.root}: {entry['version']} ({entry['template']})"

        for pattern, description in FORBIDDEN_STATEMENTS:
            match = pattern.search(applied)
            if match is not None:
                raise ProjectSetError(
                    f"{where} {description}: {match.group(0).strip()!r}. A project set runs as "
                    "the object owner through the platform's own migration plane; the platform's "
                    "state is not addressable from it."
                )

        for statement in SET_ROLE.findall(applied):
            if statement.strip() != PROJECT_ROLE_PREAMBLE:
                raise ProjectSetError(
                    f"{where} sets a role other than the owner preamble: "
                    f"{statement.strip()!r}. The only permitted form is "
                    f"{PROJECT_ROLE_PREAMBLE!r} -- LOCAL, so the authority cannot outlive the "
                    "transaction dbmate wraps this migration in."
                )

        for name in sql_surface.DROP_VIEW.findall(applied) + sql_surface.DROP_FUNCTION.findall(
            applied
        ):
            if name in release_owns:
                raise ProjectSetError(
                    f"{where} drops api.{name}, which the release's own surface publishes. "
                    "A project adds to the published surface and never removes from it: the "
                    "release's contract names that object, and a cluster where it is missing "
                    "serves a document the release cannot honour."
                )

        # A table in `app` without FORCE. Not merely ENABLE: without FORCE the
        # policies do not apply to the table's OWNER, and every write RPC in
        # this product is SECURITY DEFINER running as exactly that owner. A
        # tenant table with ENABLE alone turns its own write function into an
        # ownership-laundering primitive, which is 0005's own comment.
        created = set(_CREATE_APP_TABLE.findall(applied))
        forced = set(_FORCE_RLS.findall(applied))
        enabled = set(_ENABLE_RLS.findall(applied))
        missing = sorted(created - forced)
        if missing:
            detail = ", ".join(
                f"app.{name} ({'ENABLE without FORCE' if name in enabled else 'no row security'})"
                for name in missing
            )
            raise ProjectSetError(
                f"{where} creates a table in app without FORCE ROW LEVEL SECURITY: {detail}. "
                "FORCE is what makes the row policies apply to the table's owner, and every "
                "write function this product publishes is SECURITY DEFINER running as that "
                "owner. Without it the function can write any row (migration 0005's comment)."
            )

        down = sql_surface.down_section(template)
        if not down.strip():
            raise ProjectSetError(
                f"{where} has no `{sql_surface.DOWN_MARKER}` section. dbmate would treat a "
                f"rollback as an empty success; this plane is fix-forward, so the section must "
                f"exist and must raise {PROJECT_DOWN_SENTINEL}."
            )
        if PROJECT_DOWN_SENTINEL not in sql_surface.sql_only(down):
            raise ProjectSetError(
                f"{where} has a `down` block that does not raise {PROJECT_DOWN_SENTINEL}. "
                "A project that shipped a working rollback would be one `dbmate down` away "
                "from dropping a tenant's table on a host."
            )


__all__ = [
    "LOCK_PATH",
    "MANIFEST_PATH",
    "MIGRATIONS_ROOT",
    "PROJECT_PLACEHOLDER_SOURCES",
    "PROJECT_SETS_DIRECTORY",
    "MigrationError",
    "MigrationSet",
    "ProjectSetError",
    "build_lock",
    "canonical_outputs",
    "digest",
    "lint_project_set",
    "load_lock",
    "load_manifest",
    "newest_release_version",
    "project_set_from",
    "quote_identifier",
    "quote_literal",
    "release_set",
    "render",
    "render_migration",
    "resolve_placeholders",
    "sets_for",
    "verify_lock",
]
# ---------------------------------------------------------------------------
# The rendered set, read by whoever applies it (ADR 0028, ADR 0203)
# ---------------------------------------------------------------------------


def verify_rendered_directory(rendered_dir: Path) -> list[dict[str, Any]]:
    """The migrations a rendered directory holds, verified against its manifest.

    **The bodies dbmate will read are the payloads this release rendered.**
    dbmate is handed a directory, not a list, so what it applies is whatever is
    in that directory. Comparing each file's digest against the manifest written
    beside it -- and the set of files against the set of migrations -- is what
    makes "the rendered payload is the immutable unit" (ADR 0028) a property of
    the thing that runs rather than of the thing that was committed.

    Returns the manifest's entries **in manifest order**, which is the order
    they are to be applied in; `bin/migrate.py::assert_rendered_files_match`
    keeps its name and its `None` return and calls this, and `apg dev` applies
    what it returns. One verification, two appliers -- because a dev cluster
    built from a second reading of the same directory would be a second
    verification nobody compares (ADR 0203 §4).

    Raises `MigrationError` with the manifest's own vocabulary: no manifest at
    all, a directory that does not match it, or a file whose digest moved.
    """
    # Lazily, and in the direction `rendering` already does it: that module
    # imports this one inside its functions to keep the two from importing each
    # other at module level, so this one returns the favour.
    from agentic_postgres import rendering

    directory = Path(rendered_dir) / "migrations"
    manifest_path = directory / rendering.MIGRATION_MANIFEST_NAME
    if not manifest_path.is_file():
        raise MigrationError(
            f"no rendered migration manifest at {manifest_path}; "
            "this project was rendered by a release that did not write one."
        )

    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = list(recorded["migrations"])

    # One directory per set since ADR 0206, so the set of files is compared per
    # directory. An entry rendered before the split carries no `dir`; it read
    # from `migrations/`, which is what the release still uses.
    root = Path(rendered_dir)
    by_directory: dict[str, dict[str, str]] = {}
    for entry in entries:
        subdir = entry.get("dir") or rendering.RELEASE_MIGRATIONS_SUBDIR
        by_directory.setdefault(subdir, {})[entry["file"]] = entry["sha256"]

    for subdir, expected in sorted(by_directory.items()):
        payload_directory = root / subdir
        found = {path.name for path in payload_directory.glob("*.sql")}
        if found != set(expected):
            raise MigrationError(
                f"the rendered migration directory {subdir} does not match its "
                f"manifest: unexpected {sorted(found - set(expected))}, "
                f"missing {sorted(set(expected) - found)}"
            )
        for filename, sha in sorted(expected.items()):
            actual = digest((payload_directory / filename).read_text(encoding="utf-8"))
            if actual != sha:
                raise MigrationError(
                    f"{subdir}/{filename} does not match the payload that was rendered "
                    f"({actual[:16]} != {sha[:16]}); it was edited after rendering."
                )

    # A stray directory is as much a mismatch as a stray file: a project set
    # removed from a manifest but left on disk would otherwise still be mounted
    # and applied.
    stray = {
        path.name for path in root.glob(f"{rendering.PROJECT_MIGRATIONS_SUBDIR}*") if path.is_dir()
    } - set(by_directory)
    if stray:
        raise MigrationError(
            f"the render holds migration directories its manifest does not name: {sorted(stray)}"
        )

    return entries


def project_ledger_move_statement(rendered_dir: Path) -> str | None:
    """Move a project set's applied versions into the project table (ADR 0206).

    `None` when this project renders no project migration, so the caller issues
    nothing at all rather than an empty transaction.

    **This is the one-time repair D1288 needs, written to be re-runnable.** A
    cluster migrated before ADR 0206 recorded both sets in
    `app_private.schema_migrations`, so the release's `max(applied)` includes
    project versions -- which is exactly what made `up --strict` refuse a
    release migration stamped below one of them. Moving them restores the
    release's own ordering without re-applying anything: the example project's
    first migration is a bare `CREATE TABLE` and could not be re-applied, and a
    row deleted rather than moved would make the cluster's history unreadable.

    Driven by the RENDERED MANIFEST rather than by "everything not in the
    release lock". The manifest records which set each payload came from
    (TEN-SET-001), so this moves versions this release actually rendered as
    project migrations and nothing else -- a row belonging to a set that has
    since been removed stays where it is, visible, rather than being swept into
    a table it was never applied from.

    Both statements in one transaction: a delete that outlived its insert would
    lose the record that a migration ran.
    """
    from agentic_postgres import rendering

    manifest_path = Path(rendered_dir) / "migrations" / rendering.MIGRATION_MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    versions = sorted(
        entry["version"]
        for entry in recorded.get("migrations", [])
        if entry.get("set") == "project"
    )
    if not versions:
        return None

    listed = ", ".join(quote_literal(version) for version in versions)
    release_table = rendering.MIGRATIONS_TABLE
    project_table = rendering.PROJECT_MIGRATIONS_TABLE
    # S608, suppressed narrowly and for the reason the neighbouring ledger
    # insert gives: both table names are module constants in this repository,
    # and every version reaches the statement through `quote_literal` after
    # being read out of a manifest this release rendered. No value here comes
    # from an operator or from a caller.
    return (
        "BEGIN;\n"  # noqa: S608
        f"INSERT INTO {project_table} (version)\n"
        f"  SELECT version FROM {release_table} WHERE version IN ({listed})\n"
        "  ON CONFLICT (version) DO NOTHING;\n"
        f"DELETE FROM {release_table} WHERE version IN ({listed});\n"
        "COMMIT;\n"
    )


def ledger_insert_statement(
    document: dict[str, Any], rendered_dir: Path, repo_root: Path = REPO_ROOT
) -> str:
    """The statement that records WHICH BYTES ran, for every set this project applies.

    `app_private.migration_ledger` is not `schema_migrations`. dbmate's table
    records that a version ran; this records which bytes ran, and it is written
    **as the superuser** rather than by the migration plane -- a migration role
    that could write its own audit record could record bytes it did not execute.
    `migration_user` has no privilege on this table at all, which is the
    property that makes the row worth reading.

    **Every set's lock, not the release's alone.** D1096: the caller used to
    build its digests from the release lock and then index it by every RENDERED
    entry's version, so the first deploy that rendered a project migration
    raised `KeyError` *after dbmate had already applied it*. A cluster that has
    moved and a record that has not is the worst order a failure can arrive in.

    `ON CONFLICT (version) DO NOTHING`, so a re-run records nothing new and
    changes no `applied_at`. That is what makes the second `up` of a convergence
    check produce an identical ledger rather than a fresh set of timestamps.

    The statement only; issuing it is the caller's, because the deploy issues it
    over the container socket and `apg dev` issues it over its own (ADR 0203).
    """
    from agentic_postgres import rendering

    templates: dict[str, dict[str, Any]] = {}
    for migration_set in sets_for(document, repo_root):
        set_manifest = migration_set.load_manifest()
        follows = migration_set.load_lock().get("follows_release_version")
        built = build_lock(set_manifest, migration_set.root, follows_release_version=follows)
        for entry in built["migrations"]:
            templates[entry["version"]] = entry

    rendered = json.loads(
        (Path(rendered_dir) / "migrations" / rendering.MIGRATION_MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
    )

    values = []
    for entry in rendered["migrations"]:
        template = templates[entry["version"]]
        values.append(
            "("
            + ", ".join(
                quote_literal(value)
                for value in (
                    entry["version"],
                    entry["name"],
                    template["template_sha256"],
                    entry["sha256"],
                )
            )
            + ")"
        )

    return (
        "INSERT INTO app_private.migration_ledger "  # noqa: S608
        "(version, name, template_sha256, rendered_sha256) VALUES "
        + ", ".join(values)
        + " ON CONFLICT (version) DO NOTHING;"
    )

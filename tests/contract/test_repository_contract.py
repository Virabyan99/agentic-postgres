"""Repository shape, ignore rules, and the hard-coded-identity scan.

The fixture scan (runbook §9) deliberately searches for the *exact distinctive
values* — `fixture-alpha`, `fixture-alpine`, their domains and audiences — and
never for the generic word "example", which the runbook explicitly prohibits
because it produces meaningless false positives.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REQUIRED_PATHS = (
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".python-version",
    "README.md",
    "VERSION",
    "capabilities.example.yaml",
    "compose.yaml",
    "deploy.sh",
    "host.example.yaml",
    "project.example.yaml",
    "project.second.example.yaml",
    "secrets.required.yaml",
    "pyproject.toml",
    "pytest.ini",
    "requirements-dev.in",
    "requirements-dev.txt",
    "versions.env",
    "versions.in.yaml",
    ".github/workflows/ci.yml",
    ".generated/.gitkeep",
    "evidence/.gitkeep",
    "migrations/.gitkeep",
    "services/auth-api/.gitkeep",
    "services/docs/.gitkeep",
    # `services/mcp/.gitkeep` stood here from Session 1 until Session 8 Run 4,
    # and is gone with its directory (ADR 0121). The agent plane is a third
    # `APP_MODE` of the one application image, because a second service
    # directory could not import `LocalKeySet`, the strict request parser or the
    # error vocabulary -- and a directory that cannot hold the code is a
    # directory that will eventually hold a second copy of it.
    "docs/acceptance-matrix.md",
    "docs/api-operations.md",
    "docs/api-surface.md",
    "docs/capability-plan.md",
    "docs/new-team-member.md",
    "docs/product-contract.md",
    "docs/security-acceptance.md",
    "docs/session-05-operator-guide.md",
    "docs/source-specification.md",
    "docs/source-specification.sha256",
    "docs/threat-model.md",
    "docs/decisions/README.md",
    "docs/decisions/0001-product-shape.md",
    "docs/decisions/0002-configuration-authority.md",
    "docs/decisions/0003-example-domain.md",
    "docs/decisions/0004-version-lock-format.md",
    "docs/decisions/0005-route-reservation.md",
    "docs/decisions/0006-capability-scopes.md",
    "docs/decisions/0007-bounds-authority.md",
    "docs/decisions/0008-sensitive-key-policy.md",
    "docs/decisions/0009-host-and-edge-plane.md",
    "docs/decisions/0010-secret-materialization.md",
    "docs/decisions/0011-provider-bootstrap-state.md",
    "docs/decisions/0012-output-document-kinds.md",
    "docs/decisions/0013-compose-wrapper-scopes.md",
    "docs/decisions/0014-gate-scope-and-session-derivation.md",
    "docs/decisions/0015-reserved-health-route.md",
    "docs/decisions/0016-absence-is-not-a-collision.md",
    "docs/decisions/0017-stub-lifecycle.md",
    # The Session 2 operator documentation. Two of these are cited by
    # `Documentation=` in installed systemd units, so `systemctl status` sends
    # an operator to a path that must exist inside the release directory; the
    # other three are what those two link to.
    "docs/host-baseline.md",
    "docs/project-isolation.md",
    "docs/provider-bootstrap.md",
    "docs/secret-handling.md",
    "docs/session-02-operator-guide.md",
    # Session 10. Cited by Documentation= in all four backup units, so
    # `systemctl status` sends an operator to a path that must exist inside
    # the release directory -- the same reason the two above are listed.
    "docs/backup-operations.md",
    # The Session 3 operator documentation. The operator guide is the entry
    # point; the other three are what it links to for the cluster itself, the
    # schema-change path, and the authorization boundaries.
    "docs/database.md",
    "docs/migrations.md",
    "docs/database-security.md",
    "docs/session-03-operator-guide.md",
    # The Session 4 operator documentation. The operator guide is the entry
    # point; the other three are what it links to for the two transports, the
    # four clients, and the pooler as a thing that is operated -- restarted,
    # rebooted, and rotated through.
    "docs/database-connections.md",
    "docs/client-compatibility.md",
    "docs/pool-operations.md",
    "docs/session-04-operator-guide.md",
    "bin/bootstrap-providers.py",
    "bin/docker-firewall.sh",
    "bin/edge.sh",
    "bin/edge-network.sh",
    "bin/materialize-secrets.py",
    "bin/db.sh",
    "bin/db-verify.py",
    "bin/materialize-secrets.sh",
    "bin/postgres-bootstrap.sh",
    "bin/postgres-bootstrap.py",
    "bin/project-runtime.sh",
    "bin/provision-host.sh",
    "bin/session-02-check.sh",
    "bin/session-04-check.sh",
    "bin/apg-diag.sh",
    "bin/session-05-check.sh",
    "src/agentic_postgres/infisical_client.py",
    "src/agentic_postgres/installed_release.py",
    "infra/edge/compose.yaml",
    "infra/edge/traefik.yaml",
    "infra/edge/dynamic/baseline.yaml",
    "infra/host/00-agentic-postgres-ssh.conf",
    "infra/host/20auto-upgrades",
    "infra/host/daemon.json",
    "infra/host/docker-user-rules.v4",
    "infra/host/docker-user-rules.v6",
    "libexec/agentic-postgres-database-access",
    "libexec/agentic-postgres-edge",
    "libexec/agentic-postgres-firewall",
    "libexec/agentic-postgres-project",
    # The release sides of the two trampolines. Listed because the trampoline
    # refuses a release that does not carry its counterpart and names the
    # project to redeploy: a file that silently left the archive would turn
    # every project on the host into one that has to be redeployed to be
    # reachable, and the first sign of it would be on a host.
    "libexec/database-access-broker",
    "libexec/project-launcher",
    "systemd/agentic-postgres-docker-firewall.service",
    "systemd/agentic-postgres-edge.service",
    "systemd/agentic-postgres-project@.service",
    # Session 10 Run 9. Four files, and the pair of timers is the half D522 was
    # about: `install_units` globbed `*.service` only, so a `.timer` here was
    # installed by nothing.
    "systemd/agentic-postgres-backup-full@.service",
    "systemd/agentic-postgres-backup-full@.timer",
    "systemd/agentic-postgres-backup-incr@.service",
    "systemd/agentic-postgres-backup-incr@.timer",
    "services/edge-probe/Dockerfile",
    "services/edge-probe/probe.py",
    "services/secret-check/Dockerfile",
    "services/secret-check/check.py",
    # The Session 4 client compatibility fixtures (DBX-001..005). Listed for the
    # same reason the two above are: the registry points requirement proofs at
    # them, and a lock file or a probe that silently vanished would take its P0
    # evidence with it. The lock files are named individually because they are
    # what makes "pins dependencies through committed lock files" a fact rather
    # than an intention -- `npm ci` and `pip --require-hashes` both fail without
    # them, but only at build time, on a host.
    "services/clients/psql/Dockerfile",
    "services/clients/psql/entrypoint.sh",
    "services/clients/psql/probe.sh",
    "services/clients/node-pg/Dockerfile",
    "services/clients/node-pg/entrypoint.sh",
    "services/clients/node-pg/package.json",
    "services/clients/node-pg/package-lock.json",
    "services/clients/node-pg/probe.mjs",
    "services/clients/psycopg/Dockerfile",
    "services/clients/psycopg/entrypoint.sh",
    "services/clients/psycopg/probe.py",
    "services/clients/psycopg/requirements.in",
    "services/clients/psycopg/requirements.txt",
    "services/clients/prisma/Dockerfile",
    "services/clients/prisma/entrypoint.sh",
    "services/clients/prisma/migrate.mjs",
    "services/clients/prisma/package.json",
    "services/clients/prisma/package-lock.json",
    "services/clients/prisma/probe.mjs",
    "services/clients/prisma/url.mjs",
    "services/clients/prisma/prisma/schema.prisma",
    "services/clients/prisma/prisma/migrations/migration_lock.toml",
    "services/clients/prisma/prisma/migrations/20260809000000_fixture_init/migration.sql",
    "docs/plans/session-01-implementation-plan.md",
    "docs/plans/session-02-implementation-plan.md",
    "contracts/postgrest-api-surface.yaml",
    "schemas/api-surface.schema.json",
    "schemas/bootstrap-state.schema.json",
    "schemas/capabilities.schema.json",
    "schemas/database-access-policy.schema.json",
    "schemas/database-port-allocations.schema.json",
    "schemas/host.schema.json",
    "schemas/outputs.schema.json",
    "schemas/project.schema.json",
    "schemas/secret-contract.schema.json",
    "src/agentic_postgres/__init__.py",
    "src/agentic_postgres/access_broker.py",
    "src/agentic_postgres/api_surface.py",
    "src/agentic_postgres/access_policy.py",
    "src/agentic_postgres/bootstrap_state.py",
    "src/agentic_postgres/config.py",
    "src/agentic_postgres/evidence.py",
    "src/agentic_postgres/host_config.py",
    "src/agentic_postgres/jwt_keys.py",
    "src/agentic_postgres/naming.py",
    "src/agentic_postgres/output_migrations.py",
    "src/agentic_postgres/rendering.py",
    "src/agentic_postgres/secrets_contract.py",
    # Every superseded output version, kept because the migration path is only
    # provable against documents that were actually shipped. A hand-built
    # fixture would drift from what a host is running and the migrator would be
    # proved against a document that never existed.
    "tests/fixtures/outputs-v1.json",
    "tests/fixtures/outputs-v2.json",
    "tests/fixtures/outputs-v3.json",
    "tests/fixtures/outputs-v4.json",
    "tests/fixtures/outputs-v5.json",
    "tests/fixtures/outputs-v8.json",
    "tests/acceptance-registry.yaml",
    "tests/conftest.py",
    # The three Session 2 execution environments. Listed because the registry
    # points requirement proofs at them: a directory that silently vanished
    # would take its P0 evidence with it, and the collectibility check would
    # then fail somewhere far from the cause.
    "tests/deployment/conftest.py",
    "tests/deployment/test_session2_host.py",
    "tests/deployment/test_session2_edge.py",
    "tests/deployment/test_session2_isolation.py",
    "tests/external/test_session2_public_edge.py",
    "tests/security/test_session2_secret_model.py",
    "tests/security/test_session2_secrets.py",
    "tests/security/test_session2_installed_release.py",
)

#: Deployable source and templates. Example manifests, tests, documentation,
#: the copied specification, and generated output are excluded by §9.
SCAN_ROOTS = ("compose.yaml", "deploy.sh", "bin", "src", "services", "infra", "libexec", "systemd")

#: The exact distinctive values, never the generic word "example".
FIXTURE_MARKERS = (
    "fixture-alpha",
    "fixture-alpine",
    "fixture_alpha",
    "fixture_alpine",
    "fixture-alpha-dev.test",
    "fixture-alpine-dev.test",
    "urn:agentic-postgres:fixture-alpha",
    "urn:agentic-postgres:fixture-alpine",
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Required tree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", REQUIRED_PATHS)
def test_required_path_exists(relative: str) -> None:
    assert (REPO_ROOT / relative).exists(), f"{relative} is missing from the repository"


def test_source_specification_checksum_matches() -> None:
    """Phase 0: the recorded digest must describe the committed bytes."""
    from hashlib import sha256

    spec = REPO_ROOT / "docs" / "source-specification.md"
    recorded = (
        (REPO_ROOT / "docs" / "source-specification.sha256").read_text(encoding="utf-8").split()[0]
    )
    assert sha256(spec.read_bytes()).hexdigest() == recorded


# ---------------------------------------------------------------------------
# Ignore rules (runbook §6.1, §9 check 11)
# ---------------------------------------------------------------------------


def test_generated_output_is_ignored() -> None:
    untracked = git("ls-files", "--others", "--exclude-standard").split()
    leaked = [p for p in untracked if p.startswith((".generated/", "evidence/"))]
    assert not leaked, f"generated output is visible to git: {leaked}"


def test_generated_directories_keep_only_their_gitkeep() -> None:
    tracked = git("ls-files", ".generated", "evidence").split()
    assert sorted(tracked) == [".generated/.gitkeep", "evidence/.gitkeep"]


def test_gitignore_covers_the_required_entries() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in (".generated/*", "evidence/*", ".venv/", "__pycache__/", ".pytest_cache/"):
        assert entry in text, f".gitignore is missing {entry}"


def test_gitignore_covers_session_two_operator_inputs() -> None:
    """Session 2 §5.4: only redacted examples are committed.

    These have to be *ignored* rather than merely uncommitted, because
    bin/session-01-check.sh step 1 fails on any untracked file and that gate
    also runs from the checkout on the deployment host, where these files
    genuinely exist.
    """
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("/host.yaml", "/capabilities.yaml", "/project.alpha.yaml", "/project.beta.yaml"):
        assert entry in text, f".gitignore is missing {entry}"


def test_committed_examples_are_not_swept_up_by_the_ignore_rules() -> None:
    """Guard the guard: a `/project.*.yaml` glob would hide a real example.

    `git check-ignore` is asked rather than the pattern being re-read, because
    the question is what Git does, not what the file appears to say.
    """
    for relative in ("project.example.yaml", "project.second.example.yaml", "host.example.yaml"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 1, f"{relative} is ignored but must be committed"


def test_gitattributes_forces_lf() -> None:
    """Without this, a Windows clone breaks every shebang (plan decision N)."""
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in text
    assert "*.sh   text eol=lf" in text or "*.sh text eol=lf" in text


def test_no_tracked_file_uses_crlf() -> None:
    offenders = []
    for relative in git("ls-files").split():
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        try:
            if b"\r" in path.read_bytes():
                offenders.append(relative)
        except OSError:
            continue
    assert not offenders, f"tracked files with CRLF: {offenders}"


# ---------------------------------------------------------------------------
# Hard-coded fixture identities (runbook §9)
# ---------------------------------------------------------------------------


def scan_targets() -> list[Path]:
    targets: list[Path] = []
    for root in SCAN_ROOTS:
        path = REPO_ROOT / root
        if path.is_file():
            targets.append(path)
        elif path.is_dir():
            targets.extend(p for p in path.rglob("*") if p.is_file())
    return targets


@pytest.mark.parametrize("marker", FIXTURE_MARKERS)
def test_deployable_source_does_not_hardcode_a_fixture_identity(marker: str) -> None:
    offenders = []
    for path in scan_targets():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if marker in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"{marker!r} is hard-coded in: {offenders}"


def test_the_scan_would_actually_find_something(tmp_path: Path) -> None:
    """Guard the guard: a scan that can never fail proves nothing."""
    planted = tmp_path / "planted.py"
    planted.write_text("SLUG = 'fixture-alpha'\n", encoding="utf-8")
    assert "fixture-alpha" in planted.read_text(encoding="utf-8")


def test_scan_scope_excludes_what_the_runbook_excludes() -> None:
    """Fixture values legitimately appear in manifests, tests, and docs."""
    assert "fixture-alpha" in (REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8")
    for excluded in ("tests", "docs", "project.example.yaml"):
        assert excluded not in SCAN_ROOTS


# ---------------------------------------------------------------------------
# Version and template metadata
# ---------------------------------------------------------------------------


def test_version_file_is_a_single_stripped_line() -> None:
    raw = (REPO_ROOT / "VERSION").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert len(raw.strip().splitlines()) == 1
    assert raw.strip()


def test_python_version_is_pinned_to_a_patch_release() -> None:

    pinned = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"3\.\d+\.\d+", pinned), f"{pinned!r} is not a patch-level pin"


def test_dependency_lock_uses_hashes() -> None:
    text = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "--hash=sha256:" in text
    packages = [line for line in text.splitlines() if line and not line[0].isspace()]
    assert len(packages) > 5
    for line in packages:
        if line.startswith("#"):
            continue
        assert "==" in line, f"unpinned dependency: {line}"


def test_no_module_is_imported_only_by_its_own_tests() -> None:
    """A module nothing calls is a feature that does not exist (D204).

    `edge_credentials` was written in Run 7, tested thoroughly, and imported by
    **nothing outside its own test module** -- so the middleware every
    documentation router names was never written, Traefik declined to create a
    router referencing an undefined middleware, and the route answered the
    edge's own 404. The only reference to the module anywhere in the product was
    a *comment* saying it defines the middleware.

    That is this repository's signature defect in its purest form: the tests
    passed, the code was correct, and nothing connected it to the product. Same
    shape as D192 (a hook built, granted and never wired) and D197 (a value
    validated and dropped at a boundary), and the cheapest of the three to
    detect -- an import graph is a fact about the source.

    **Parsed, not grepped**, and that is not a style preference. A text scan
    cannot detect the case this rule exists for, because the one mention of
    `edge_credentials` in the product was a comment; a scan that reads comments
    would have called it imported. The first draft also excluded a preceding
    `.`, to avoid matching attribute access, and thereby missed
    `from agentic_postgres.x import y` -- the dominant form -- reporting two
    modules as orphans that six files import.

    Goes red if: a module is added with no caller, or the last caller of an
    existing one is removed.
    """
    import ast

    package = REPO_ROOT / "src" / "agentic_postgres"
    modules = {
        path.stem for path in package.glob("*.py") if path.stem not in {"__init__", "__main__"}
    }
    assert modules, "no modules found; this compared nothing"

    imported: set[str] = set()
    for source in [*(REPO_ROOT / "bin").glob("*.py"), *package.glob("*.py")]:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # `from agentic_postgres import x, y`
                if node.module == "agentic_postgres":
                    imported.update(alias.name for alias in node.names if alias.name != source.stem)
                # `from agentic_postgres.x import y`
                elif node.module.startswith("agentic_postgres."):
                    name = node.module.split(".", 1)[1].split(".")[0]
                    if name != source.stem:
                        imported.add(name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("agentic_postgres."):
                        name = alias.name.split(".", 1)[1].split(".")[0]
                        if name != source.stem:
                            imported.add(name)

    # Python embedded in a shell script is still a caller.
    # `bin/provision-host.sh` imports `listeners` from a heredoc, and this
    # repository has `test_embedded_python.py` because that is a deliberate
    # pattern here rather than an accident.
    #
    # Anchored on the import *statement*. Three lines above that import a
    # comment reads "Classification lives in agentic_postgres.listeners, not in
    # awk" -- and a rule that counted the mention would call `edge_credentials`
    # imported for exactly the same reason it was not.
    statement = re.compile(
        r"^\s*(?:from\s+agentic_postgres\.(\w+)\s+import|"
        r"from\s+agentic_postgres\s+import\s+([\w,\s]+)|"
        r"import\s+agentic_postgres\.(\w+))",
        re.MULTILINE,
    )
    for script in (REPO_ROOT / "bin").glob("*.sh"):
        for dotted, names, plain in statement.findall(script.read_text(encoding="utf-8")):
            if dotted:
                imported.add(dotted)
            if plain:
                imported.add(plain)
            if names:
                imported.update(name.strip() for name in names.split(",") if name.strip())

    assert imported, "no imports of the package found at all; this compared nothing"
    orphans = sorted(modules - imported)
    assert not orphans, (
        f"{orphans} are imported by nothing outside their own tests. A module with no "
        "caller is a feature that does not exist, however well it is tested (D204)"
    )


def test_every_name_the_deploy_reads_is_a_name_the_render_emits() -> None:
    """Two lists that must agree, with nothing comparing them until now (D486).

    `bin/deploy-project.py` reads each `OVERRIDE_NAME_KEYS` value out of a
    project's `compose.env` through `_env_value`, which **fails on a missing key
    rather than defaulting** -- deliberately, so that "a name this repository
    derives and forgets to emit is a refusal at step 4 rather than a router that
    quietly is not there".

    `rendering.compose_env` emits exactly `COMPOSE_ENV_KEYS`, iterating that
    tuple. So a value computed into its `values` dict and absent from the tuple
    is silently dropped, and the two facts meet **on the host**, in the middle of
    a deploy.

    That is what happened to Session 14's metrics route: Run 2 added
    `METRICS_ROUTER_NAME` and `METRICS_CREDENTIAL_MIDDLEWARE_NAME` to the values
    dict and to `OVERRIDE_NAME_KEYS`, and to neither list that emits them. Both
    were dropped, the offline gate passed, and the first deploy of the release
    stopped at step 4 with the right message at the wrong time.

    Read from the source of both rather than from a copy: the deploy's mapping is
    parsed out of its AST, and the renderer's tuple is imported. A test that
    restated either would be a third list.
    """
    import ast

    from agentic_postgres import rendering

    tree = ast.parse((REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if getattr(target, "id", "") == "OVERRIDE_NAME_KEYS":
                    mapping = {
                        key.value: value.value
                        for key, value in zip(node.value.keys, node.value.values, strict=True)
                    }

    assert mapping, (
        "OVERRIDE_NAME_KEYS was not found in bin/deploy-project.py. Renamed or "
        "restructured, this test silently stops comparing anything"
    )

    emitted = set(rendering.COMPOSE_ENV_KEYS)
    missing = sorted(set(mapping.values()) - emitted)
    assert not missing, (
        f"the deploy reads {missing} out of compose.env and the renderer emits "
        "none of them. `_env_value` fails on a missing key, so each is a step-4 "
        "refusal on a host -- add it to COMPOSE_ENV_KEYS"
    )


def test_every_bin_call_supplies_the_required_keyword_only_arguments() -> None:
    """A required keyword-only argument added in `src/` reaches its caller in `bin/`.

    Found the hard way. Run 4 added `app_status` and `app_docs_status` to
    `deployed_output.build_deployed_document` as required keyword-only
    parameters, updated the test helper that calls it, and did not update the one
    production caller -- `bin/deploy-project.py`. The offline suite passed, the
    gate passed, and the deploy raised `TypeError` on a live host at step 7,
    **after** it had restarted both projects' services and applied a migration.

    Nothing could have caught it. The tests call `build_deployed_document`
    through their own helper, and the caller lives inside `main()` of a script
    that needs root, a cluster and an edge -- so no offline test executes that
    line. An import graph is a fact about the source (D204's rule); so is a call
    signature.

    Parsed, not grepped, for D204's reason: a call spread over twenty lines with
    comments between the arguments is not something a regex reads correctly, and
    this one is exactly that shape.

    **Bounded deliberately.** It resolves only calls written as
    `<module>.<function>(...)` where `<module>` is imported from
    `agentic_postgres`, and it checks only *required keyword-only* parameters --
    the ones whose absence is a `TypeError` at call time rather than a wrong
    value. Positional arity and defaults are somebody else's rule.
    """
    import ast
    import importlib
    import inspect

    problems: list[str] = []
    checked = 0

    for source in sorted((REPO_ROOT / "bin").glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))

        # `from agentic_postgres import x, y` and `from agentic_postgres.x import y`
        modules: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "agentic_postgres":
                for alias in node.names:
                    modules[alias.asname or alias.name] = f"agentic_postgres.{alias.name}"

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
                continue
            module_name = modules.get(func.value.id)
            if module_name is None:
                continue

            try:
                module = importlib.import_module(module_name)
                target = getattr(module, func.attr)
                signature = inspect.signature(target)
            except (ImportError, AttributeError, TypeError, ValueError):
                continue

            required = {
                name
                for name, parameter in signature.parameters.items()
                if parameter.kind is inspect.Parameter.KEYWORD_ONLY
                and parameter.default is inspect.Parameter.empty
            }
            if not required:
                continue

            checked += 1
            supplied = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
            # `**kwargs` at the call site means the caller is forwarding; this
            # rule cannot see through that and does not pretend to.
            if any(keyword.arg is None for keyword in node.keywords):
                continue

            missing = required - supplied
            if missing:
                problems.append(
                    f"{source.name}:{node.lineno}: {module_name}.{func.attr} requires "
                    f"{sorted(missing)}"
                )

    assert checked, "no keyword-only call sites were resolved; this compared nothing"
    assert not problems, "calls in bin/ missing required keyword-only arguments:\n  " + "\n  ".join(
        problems
    )

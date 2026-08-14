"""Where the auth service meets the rest of the repository, and must agree.

Nothing here tests behaviour. Every test is a relation between two files that
would otherwise be two authorities for one fact -- which is this repository's
recurring defect, and the only thing that has ever caught it is something that
computes the relation.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, auth_profile, config, rendering
from app import main as main_module
from app import settings as settings_module

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SERVICE_ROOT = REPO_ROOT / "services" / "auth-api"
DOCKERFILE = SERVICE_ROOT / "Dockerfile"


@pytest.fixture(scope="module")
def compose_model() -> dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def auth_service(compose_model: dict[str, Any]) -> dict[str, Any]:
    assert "auth" in compose_model["services"], (
        "the `auth` service is missing from compose.yaml; three secrets in "
        "secrets.required.yaml name it as their consumer"
    )
    return compose_model["services"]["auth"]


@pytest.fixture(scope="module")
def candidates() -> dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / "versions.in.yaml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The frozen profile's one authority
# ---------------------------------------------------------------------------


def test_the_frozen_profile_module_needs_only_the_standard_library() -> None:
    """The property the whole arrangement rests on.

    `config.py` validates a manifest on a deploy host that has no `argon2`, no
    `pyjwt` and no `psycopg` anywhere near it, and it reads the frozen profile
    to do so. That works only while `profile.py` imports nothing but the
    standard library -- and it would break silently, at the first convenience
    import, in a way that surfaces as a deploy failing rather than a test.
    """
    tree = ast.parse(auth_profile.PROFILE_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])

    outside = imported - sys.stdlib_module_names
    assert not outside, (
        f"{auth_profile.PROFILE_SOURCE.name} imports {sorted(outside)}, which is outside "
        "the standard library; agentic_postgres.config reads this module on a host that "
        "has none of the service's dependencies installed"
    )


def test_the_repository_and_the_service_hold_one_profile_object() -> None:
    """Not two structurally equal ones (see `auth_profile._load`).

    A path-based import produced a second `Argon2Profile` class, and a
    dataclass compares `other.__class__ is self.__class__` before anything
    else -- so `parse_encoded(hash) == FROZEN` was False for two identical
    profiles. This asserts the identity rather than the equality, because
    equality is what silently stopped meaning anything.
    """
    from app import profile as service_profile

    assert auth_profile.FROZEN is service_profile.FROZEN
    assert auth_profile.Argon2Profile is service_profile.Argon2Profile


# ---------------------------------------------------------------------------
# ADR 0082: the memory relation
# ---------------------------------------------------------------------------


def test_the_memory_floor_is_the_relation_and_not_a_constant() -> None:
    """`concurrency x memory_cost + overhead`, and it has to VARY with concurrency.

    The first version of this test computed the expected value from the same
    three constants and compared. A mutation replacing the whole function body
    with `return 224` passed it -- the assertion was `224 == 224`, a tautology
    in the shape D173 recorded. What kills a constant is the *slope*: the floor
    must move by exactly one `memory_cost` for each additional concurrent hash,
    which no fixed number can do.
    """
    profile = auth_profile.FROZEN
    per_hash_mb = profile.memory_cost_kib // 1024

    at_one = auth_profile.hash_memory_budget_mb(concurrency=1)
    at_two = auth_profile.hash_memory_budget_mb(concurrency=2)
    at_four = auth_profile.hash_memory_budget_mb(concurrency=4)

    assert at_two - at_one == per_hash_mb, "the floor does not move with concurrency"
    assert at_four - at_two == 2 * per_hash_mb, "the floor is not linear in concurrency"
    assert at_one - per_hash_mb == auth_profile.PROCESS_OVERHEAD_MB, (
        "the constant term is not the measured process overhead"
    )

    # And the configured floor is that relation at the frozen concurrency.
    assert config.auth_memory_floor_mb() == auth_profile.hash_memory_budget_mb(
        concurrency=auth_profile.HASH_CONCURRENCY
    )


def test_the_measured_floor_is_what_run_7_measured() -> None:
    """The numbers ADR 0082 quotes, asserted so the prose cannot drift from them.

    Measured: 67.1 MiB resident for one concurrent hash at the frozen profile,
    131.1 for two, 259.0 for four, against a no-hash control at 0.0. Those are
    `memory_cost` plus about 3 MiB, so the relation's per-hash term is 64.
    """
    assert auth_profile.FROZEN.memory_cost_kib // 1024 == 64
    assert auth_profile.HASH_CONCURRENCY == 2
    assert config.auth_memory_floor_mb() == 2 * 64 + auth_profile.PROCESS_OVERHEAD_MB


def _example_manifest() -> dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))


def test_a_manifest_limit_below_the_floor_is_refused() -> None:
    """D234's whole point: three numbers with one relationship between them."""
    manifest = _example_manifest()
    manifest.setdefault("api", {}).setdefault("app", {})["enabled"] = True
    manifest["api"]["app"]["memory_limit_mb"] = config.auth_memory_floor_mb() - 1

    with pytest.raises(config.ManifestError, match="cannot hold the frozen Argon2id profile"):
        config.validate_project_semantics(manifest)


def test_a_manifest_limit_at_the_floor_is_accepted() -> None:
    """The boundary is a floor, not an approximation of one.

    Without this, a validator that refused everything would pass the test
    above -- which is the shape D173 recorded, a comparison that can only fail
    in one direction.
    """
    manifest = _example_manifest()
    manifest.setdefault("api", {}).setdefault("app", {})["enabled"] = True
    manifest["api"]["app"]["memory_limit_mb"] = config.auth_memory_floor_mb()
    config.validate_project_semantics(manifest)


def test_the_check_runs_for_a_project_that_declares_no_app_service() -> None:
    """D256's correction, applied to the new relation rather than rediscovered.

    The renderer publishes `AUTH_MEMORY_LIMIT` whether or not the service is
    enabled, so a check that ran only for an enabled service would disagree
    with the file that starts the container. The default therefore has to
    satisfy the relation on its own, or every project without an `api.app`
    section would fail to validate.
    """
    manifest = _example_manifest()
    manifest.setdefault("api", {}).pop("app", None)
    config.validate_project_semantics(manifest)

    assert config.API_APP_DEFAULTS["memory_limit_mb"] >= config.auth_memory_floor_mb()


def test_a_disabled_app_service_is_still_charged() -> None:
    """Same reason. A relation that a flag could switch off is not a bound."""
    manifest = _example_manifest()
    manifest.setdefault("api", {})["app"] = {
        "enabled": False,
        "memory_limit_mb": config.auth_memory_floor_mb() - 1,
    }
    with pytest.raises(config.ManifestError, match="cannot hold the frozen Argon2id profile"):
        config.validate_project_semantics(manifest)


def test_the_schema_default_and_the_config_default_agree(tmp_path: Path) -> None:
    """JSON Schema `default` annotates; it does not populate (see `API_APP_DEFAULTS`)."""
    schema = yaml.safe_load((REPO_ROOT / "schemas" / "project.schema.json").read_text("utf-8"))
    app_schema = schema["$defs"]["appService"]["properties"]
    for field, value in config.API_APP_DEFAULTS.items():
        if field in app_schema and "default" in app_schema[field]:
            assert app_schema[field]["default"] == value, field


# ---------------------------------------------------------------------------
# The compose service and the settings it must supply
# ---------------------------------------------------------------------------


def test_the_compose_service_supplies_every_setting_the_service_requires(
    auth_service: dict[str, Any],
) -> None:
    """The check that would have caught D178.

    A renderer emitting a variable the compose file does not read, or a service
    reading one the compose file does not set, is a container that fails at
    start with a message about the wrong thing. `load()` raises on any missing
    one, so the two lists must be equal rather than merely overlapping.
    """
    supplied = set(auth_service["environment"])
    required = set(settings_module.REQUIRED_VARIABLES)

    assert required - supplied == set(), (
        f"app/settings.py requires {sorted(required - supplied)}, which compose.yaml "
        "does not set; the container would fail at start"
    )
    assert supplied - required == set(), (
        f"compose.yaml sets {sorted(supplied - required)} for `auth`, which "
        "app/settings.py never reads -- a variable with no consumer"
    )


def test_every_setting_is_required_interpolation_or_a_literal(
    auth_service: dict[str, Any],
) -> None:
    """No `${VAR:-default}` anywhere: a default here is a second authority.

    Compose's `${VAR:?required}` refuses an *empty* value as well as an unset
    one (D178), which is why `settings.load` treats empty and unset the same.
    """
    for name, value in auth_service["environment"].items():
        text = str(value)
        if "${" not in text:
            continue
        for reference in re.findall(r"\$\{([^}]*)\}", text):
            assert ":?" in reference or "?" in reference, (
                f"{name} interpolates {reference!r} without `:?required`; a default "
                "would let the container start against something nobody declared"
            )


def test_every_variable_the_service_interpolates_is_one_something_emits() -> None:
    """The gap a mutation found: nothing checked the variable NAMES.

    `test_the_compose_service_supplies_every_setting_the_service_requires`
    compares the environment *keys* -- `APG_JWT_AUDIENCE` and the rest -- and is
    blind to what they interpolate. A mutation changing `${JWT_AUDIENCE}` to
    `${AUTH_JWT_AUDIENCE}`, a variable no renderer emits, left it green. The
    container would have failed to start, which is how the real version of that
    mistake was caught during this run -- by a render, not by a test.

    Two authorities may legitimately supply a variable: the per-project
    `compose.env` the renderer writes, and `versions.env`. Anything else is a
    name nobody sets.
    """
    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = model["services"]["auth"]

    emitted = set(rendering.COMPOSE_ENV_KEYS)
    locked = {
        line.partition("=")[0]
        for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    }

    referenced: set[str] = set()
    for section in ("environment", "labels"):
        for value in (service.get(section) or {}).values():
            referenced.update(re.findall(r"\$\{([A-Z0-9_]+)", str(value)))
    for value in (service.get("build", {}).get("args") or {}).values():
        referenced.update(re.findall(r"\$\{([A-Z0-9_]+)", str(value)))
    referenced.update(re.findall(r"\$\{([A-Z0-9_]+)", str(service.get("mem_limit", ""))))

    unknown = referenced - emitted - locked
    assert not unknown, (
        f"the `auth` service interpolates {sorted(unknown)}, which neither "
        "rendering.COMPOSE_ENV_KEYS nor versions.env supplies; the container would "
        "fail to start and `compose config` would refuse to render"
    )


def test_the_service_runs_as_the_uid_its_secrets_are_materialized_for(
    auth_service: dict[str, Any],
) -> None:
    """Duplicated by test_secret_contract.py for every service; asserted here too.

    Not redundant: this one names `auth` explicitly, so deleting the service
    from the contract would make the general test vacuous and this one fail.
    """
    contract = yaml.safe_load((REPO_ROOT / "secrets.required.yaml").read_text(encoding="utf-8"))
    grants = [
        consumer
        for secret in contract["secrets"]
        for consumer in secret["consumers"]
        if consumer.get("service") == "auth"
    ]
    assert grants, "no secret names `auth` as a consumer"
    for consumer in grants:
        assert auth_service["user"] == f"{consumer['uid']}:{consumer['gid']}"


def test_the_mounted_paths_the_service_reads_are_the_ones_the_contract_writes(
    auth_service: dict[str, Any],
) -> None:
    """The filename is derived from the contract, never typed (ADR 0075).

    D236's lesson: a proof that named a file the materializer does not write
    could not have run. The same applies to a service that reads one.
    """
    contract = yaml.safe_load((REPO_ROOT / "secrets.required.yaml").read_text(encoding="utf-8"))
    targets = {
        consumer["target_file"]
        for secret in contract["secrets"]
        for consumer in secret["consumers"]
        if consumer.get("service") == "auth"
    }
    environment = auth_service["environment"]
    for variable in ("APG_DATABASE_PASSFILE", "APG_SIGNING_KEY_FILE"):
        path = Path(str(environment[variable]))
        assert path.parent == Path("/run/secrets"), variable
        assert path.name in targets, (
            f"{variable} names {path.name!r}, which secrets.required.yaml does not "
            f"materialize for `auth` (it writes {sorted(targets)})"
        )


def test_the_service_carries_no_credential_in_its_environment(
    auth_service: dict[str, Any],
) -> None:
    """A file, not a variable. The standing rule, asserted at the one new surface."""
    for name, value in auth_service["environment"].items():
        assert "PASSWORD" not in name.upper(), name
        assert "SECRET" not in name.upper() or name.endswith("_FILE"), name
        assert "password=" not in str(value).lower(), name


def test_the_service_is_not_routable_yet(auth_service: dict[str, Any]) -> None:
    """Run 7's boundary, made checkable.

    `apg.traefik.scope: managed` is what makes a container visible to the edge
    at all (D186). Its absence is why no router can be attached before Run 10
    builds one -- and before `routes.app.status` has an administrator to gate
    on (D230). This test is what turns "we did not do that yet" into a
    property, so that adding the label is a deliberate change with a test to
    update rather than a line that slips in.
    """
    assert auth_service["networks"] == ["internal"]
    assert "apg.traefik.scope" not in auth_service.get("labels", {})
    assert not any(key.startswith("traefik.") for key in auth_service.get("labels", {}))


def test_the_service_has_a_memory_limit_from_the_renderer(
    auth_service: dict[str, Any],
) -> None:
    assert auth_service["mem_limit"] == "${AUTH_MEMORY_LIMIT:?required}"


# ---------------------------------------------------------------------------
# The version lock, and the three files that must agree with it
# ---------------------------------------------------------------------------


def _pinned_requirements() -> dict[str, str]:
    """`name==version` lines from requirements-dev.in, extras stripped."""
    pins: dict[str, str] = {}
    for line in (REPO_ROOT / "requirements-dev.in").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, version = line.partition("==")
        pins[re.sub(r"\[.*\]$", "", name).strip().lower().replace("_", "-")] = version.strip()
    return pins


def test_the_development_environment_installs_the_locked_service_versions(
    candidates: dict[str, Any],
) -> None:
    """Two files naming one version, with something computing the relation.

    The offline suite imports these libraries to measure them. If the
    development environment resolved something newer than the image installs,
    every measured claim in Run 7's batteries would be a claim about a version
    this product does not ship -- ADR 0065 arriving through the dependency
    resolver instead of through a rig.
    """
    locked = {
        entry["package"].lower().replace("_", "-"): entry["version"]
        for entry in candidates["packages"].values()
        if entry["registry"] == "pypi"
    }
    pinned = _pinned_requirements()

    shared = set(locked) & set(pinned)
    assert shared, "requirements-dev.in pins none of the locked PyPI packages"
    for package in sorted(shared):
        assert pinned[package] == locked[package], (
            f"requirements-dev.in pins {package}=={pinned[package]} while "
            f"versions.in.yaml locks {locked[package]}"
        )


def test_every_dependency_the_image_installs_is_pinned_in_the_development_set() -> None:
    """The image and the test environment install the same set, not overlapping ones.

    Read from the Dockerfile's own `pip install` rather than from a list kept
    beside it, because a list beside it is the third authority.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    installed = {
        re.sub(r"\[.*\]$", "", name).lower().replace("_", "-")
        for name in re.findall(r'"([a-zA-Z0-9_.\[\]-]+)==\$\{[A-Z_]+\}"', text)
    }
    assert installed, "no pinned pip installs found in the Dockerfile"

    pinned = set(_pinned_requirements())
    missing = installed - pinned
    assert not missing, (
        f"the image installs {sorted(missing)} but requirements-dev.in does not pin them; "
        "the offline suite would measure a different version from the one that ships"
    )


def test_every_dockerfile_build_argument_is_supplied_by_compose(
    auth_service: dict[str, Any],
) -> None:
    """An unsupplied ARG is empty, and `pip install "fastapi=="` is a build failure."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    # `[A-Z0-9_]`, not `[A-Z_]`: the first spelling stops at the digit in
    # ARGON2_CFFI_VERSION and reports a build argument called `ARGON`.
    declared = set(re.findall(r"^ARG ([A-Z0-9_]+)", text, flags=re.MULTILINE))
    supplied = set(auth_service["build"]["args"])

    assert declared - supplied == set(), (
        f"the Dockerfile declares {sorted(declared - supplied)}, which compose.yaml "
        "does not pass; an unsupplied ARG expands to the empty string"
    )
    assert supplied - declared == set(), (
        f"compose.yaml passes {sorted(supplied - declared)}, which the Dockerfile does not declare"
    )


def test_every_version_compose_passes_exists_in_the_lock(
    auth_service: dict[str, Any],
) -> None:
    """versions.env is the single authority (ADR 0077), so every name must be in it."""
    lock = {
        line.partition("=")[0]
        for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    }
    for value in auth_service["build"]["args"].values():
        for reference in re.findall(r"\$\{([A-Z0-9_]+)", str(value)):
            assert reference in lock, f"{reference} is not in versions.env"


def test_the_dockerfile_names_no_version_of_its_own() -> None:
    """A literal pin here would be a declaration bin/lock-versions.sh cannot see.

    That is D201 exactly: `SCALAR_VERSION` named a release that never existed
    for four sessions because nothing dereferenced it.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        literal = re.search(r'"[a-zA-Z0-9_.\[\]-]+==\d', stripped)
        assert literal is None, f"the Dockerfile pins a literal version: {stripped}"


# ---------------------------------------------------------------------------
# Local keys only, and the health surface
# ---------------------------------------------------------------------------


#: Names that would let this service fetch its own trust anchor. `PyJWKClient`
#: takes a URI; the rest are the transports it would use.
NETWORK_NAMES = frozenset({"PyJWKClient", "urllib", "httpx", "requests", "aiohttp", "socket"})


def _referenced_names(source: str) -> set[str]:
    """Every name the CODE uses -- imports, calls, attribute bases.

    Read from the AST rather than with `in text`, and that is not fastidiousness:
    the first spelling of this test searched the file for the string and failed
    on `tokens.py`'s own docstring, which explains *why* `PyJWKClient` must not
    be used, and on the word "requests." at the end of a sentence in
    `strict_json.py`. A grep over prose is a filesystem fact standing in for a
    logic test -- §6's pattern, produced by the test written to enforce §6.
    """
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
            names.update(alias.name.rsplit(".", 1)[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_the_service_never_constructs_a_network_jwks_client() -> None:
    """`PyJWKClient` takes a URI and fetches. This service must not hold one.

    A verifier that can fetch its keys is a verifier whose trust anchor is
    whatever answered the request -- and the rotation design depends on knowing
    exactly which key material each verifier holds at each moment.

    Asserted against the source rather than against behaviour, because an
    import nobody calls today is an import somebody calls next session, and by
    then the reason will be a comment nobody reads.
    """
    offenders: list[str] = []
    for path in sorted(SERVICE_ROOT.rglob("*.py")):
        used = _referenced_names(path.read_text(encoding="utf-8")) & NETWORK_NAMES
        if used:
            offenders.append(f"{path.relative_to(REPO_ROOT)} uses {sorted(used)}")
    assert not offenders, offenders


def test_that_scan_can_tell_code_from_prose() -> None:
    """The control for the test above.

    Two of these names appear in the service's own documentation -- `tokens.py`
    explains why `PyJWKClient` is forbidden -- so a scan that read the file as
    text would report an offence for a docstring saying the opposite of what it
    was accused of. This asserts the scan finds the name in code and does not
    find it in a string.
    """
    assert "PyJWKClient" in _referenced_names("from jwt import PyJWKClient")
    assert "PyJWKClient" in _referenced_names("client = jwt.PyJWKClient(uri)")
    assert "PyJWKClient" not in _referenced_names('"""Never use PyJWKClient."""')
    assert "PyJWKClient" not in _referenced_names('x = "PyJWKClient"')

    # And it really is present in the source that the test above passes on.
    text = (SERVICE_ROOT / "app" / "tokens.py").read_text(encoding="utf-8")
    assert "PyJWKClient" in text, "the docstring that makes this control meaningful is gone"


def test_the_application_publishes_only_the_two_container_local_health_paths() -> None:
    """D231: the project's public health answer stays `__apg/healthz`.

    A third and fourth answer to "is this project up" is two more things to
    keep in step, and one of them will drift.
    """
    application = main_module.create_app()
    served = set(main_module.route_paths(application))
    declared = set(main_module.health_paths())

    assert declared <= served, f"declared health paths {declared - served} are not served"
    # FastAPI adds nothing else when docs and openapi are disabled.
    assert served == declared, (
        f"the application serves unexpected paths: {sorted(served - declared)}"
    )


def test_the_application_generates_no_openapi_document() -> None:
    """`/docs/app` is a separate surface built from a reviewed snapshot (D226)."""
    application = main_module.create_app()
    assert application.openapi_url is None
    assert application.docs_url is None
    assert application.redoc_url is None


def test_the_healthcheck_asks_the_path_the_application_serves(
    auth_service: dict[str, Any],
) -> None:
    """The pair D236 is about: a probe naming a path nothing answers."""
    command = " ".join(str(part) for part in auth_service["healthcheck"]["test"])
    served = main_module.route_paths(main_module.create_app())
    assert any(path in command for path in served), (
        f"the healthcheck asks for a path the application does not serve: {command}"
    )

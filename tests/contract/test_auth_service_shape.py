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


#: The modules `src/agentic_postgres/` imports out of the service (ADR 0084).
#: Listed rather than discovered, because the rule is that only a *pure fact*
#: may move -- a scan that found them would grow silently as somebody moved
#: something that is not one.
#:
#: `strict_json` joined in Run 10, for `MAX_BODY_BYTES`. That number is a pure
#: fact by this rule's own test: the service enforces it on a parsed body, the
#: edge enforces it on a request body one hop earlier, and the two have to be
#: one number rather than two that happen to agree.
SHARED_MODULES = ("profile", "claims", "scopes", "strict_json")


@pytest.mark.parametrize("module", SHARED_MODULES)
def test_every_service_module_the_repository_imports_needs_only_the_standard_library(
    module: str,
) -> None:
    """ADR 0084's load-bearing half.

    `config.py` validates a manifest on a deploy host that has no `argon2`, no
    `pyjwt` and no `psycopg` anywhere near it, and it reads these modules to do
    it. That works only while they import nothing but the standard library --
    and it would break silently, at the first convenience import, in a way that
    surfaces as a deploy failing rather than a test.
    """
    source = (SERVICE_ROOT / "app" / f"{module}.py").read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])

    outside = imported - sys.stdlib_module_names - {"app"}
    assert not outside, (
        f"app/{module}.py imports {sorted(outside)}, which is outside the standard "
        "library; agentic_postgres imports this module on a host that has none of the "
        "service's dependencies installed"
    )


def test_the_service_never_imports_the_repository() -> None:
    """ADR 0084 is one-way, and the image is why.

    `services/auth-api/` is the whole build context: `agentic_postgres` is not
    in the image, so an import of it would work in every test and fail at
    startup in the container -- the exact shape of a defect that survives an
    offline suite and appears on a host.
    """
    offenders: list[str] = []
    for path in sorted(SERVICE_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            module = None
            if isinstance(node, ast.Import):
                module = ",".join(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
            if module and "agentic_postgres" in module:
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports {module}")
    assert not offenders, offenders


def test_the_shared_modules_are_the_ones_the_repository_actually_loads() -> None:
    """The list above is not decoration; it has to match what `src/` does.

    Otherwise a module could be added to the service and imported by the
    repository without ever meeting the standard-library rule -- which is the
    rule ADR 0084 rests on.
    """
    loaded: set[str] = set()
    for path in sorted((REPO_ROOT / "src" / "agentic_postgres").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        loaded.update(re.findall(r'service_source\.load\(\s*"([a-z_]+)"\s*\)', text))
    assert loaded == set(SHARED_MODULES), (
        f"the repository loads {sorted(loaded)} from the service, and this test covers "
        f"{sorted(SHARED_MODULES)}"
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


@pytest.mark.parametrize(
    ("service", "declared"),
    [
        ("auth", settings_module.REQUIRED_VARIABLES),
        ("storage", settings_module.STORAGE_VARIABLES),
    ],
)
def test_the_compose_service_supplies_every_setting_the_service_requires(
    compose_model: dict[str, Any], service: str, declared: tuple[str, ...]
) -> None:
    """The check that would have caught D178, now once per mode.

    A renderer emitting a variable the compose file does not read, or a service
    reading one the compose file does not set, is a container that fails at
    start with a message about the wrong thing. `load()` raises on any missing
    one, so the two lists must be equal rather than merely overlapping.

    **Both services, and separately** (Session 7 Run 6). Until this run only
    `auth` was compared, so the eight `APG_STORAGE_*` variables the `storage`
    service sets were checked against nothing at all. Parametrised rather than
    unioned, because one combined list would be satisfied by a compose file that
    handed every variable to both services -- and the boundary ADR 0101 rests on
    is precisely that it does not.

    `APP_MODE` is read by `main.create_app`, not by `settings.load`, so it is
    added here rather than to either declaration. It is genuinely required: the
    entrypoint is `--factory app.main:create_app`, called with no arguments, so
    this variable is the only thing deciding which router is mounted.
    """
    supplied = set(compose_model["services"][service]["environment"])
    required = set(declared) | {"APP_MODE"}

    assert required - supplied == set(), (
        f"the service requires {sorted(required - supplied)} for `{service}`, which "
        "compose.yaml does not set; the container would fail at start"
    )
    assert supplied - required == set(), (
        f"compose.yaml sets {sorted(supplied - required)} for `{service}`, which "
        "the service never reads -- a variable with no consumer"
    )


def test_each_mode_is_denied_the_other_s_credential_settings(
    compose_model: dict[str, Any],
) -> None:
    """The boundary ADR 0101 rests on, asserted against the compose file.

    One image runs both modes, so the image cannot be the boundary. What is real
    is which variables and which mounted files each service is given: `auth`
    holds no R2 credential and `storage` no signing key. `settings.load` refuses
    to start when the forbidden one is present; this asserts the file never
    presents it, so the two checks fail at different times rather than both
    depending on a container actually starting.
    """
    for service, forbidden in settings_module.FORBIDDEN_VARIABLES.items():
        supplied = set(compose_model["services"][service]["environment"])
        for name in forbidden:
            assert name not in supplied, (
                f"compose.yaml gives `{service}` the variable {name}, which its mode must not hold"
            )

    auth_environment = set(compose_model["services"]["auth"]["environment"])
    assert not {name for name in auth_environment if name.startswith("APG_STORAGE_")}, (
        "the auth service is given storage settings; it holds no R2 credential and "
        "must have nothing to point one at"
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


def test_the_service_is_visible_to_the_edge_and_says_which_network_on(
    auth_service: dict[str, Any],
) -> None:
    """Run 10 publishes it, and this replaces `test_the_service_is_not_routable_yet`.

    That test asserted the absence of the scope label so that adding it would be
    a deliberate change with a test to update rather than a line that slipped
    in. It did its job -- it failed the moment the label was added -- and it is
    replaced here by the stricter statement of what the label now has to be
    accompanied by.

    Three things, and each has its own failure:

    * `apg.traefik.scope: managed` is what makes the container visible at all.
      `infra/edge/traefik.yaml` constrains the docker provider on it, so without
      it a correct, measured router is attached to nothing and the edge answers
      404 while the service serves its own network (D186).
    * `edge` as well as `internal`. Visible is not reachable.
    * `traefik.docker.network`, because two networks give Traefik two addresses
      and the one it picks is not necessarily the one the edge can reach.

    The router and service labels are still absent here, and that is not a
    leftover: their keys carry the derived router name and Compose cannot
    interpolate inside a label key (ADR 0013), so `runtime_override.py` renders
    them. `test_every_routed_service_carries_the_label_the_edge_filters_on` is
    where the two halves are compared.
    """
    labels = auth_service.get("labels", {})
    assert set(auth_service["networks"]) == {"internal", "edge"}
    assert labels.get("apg.traefik.scope") == "managed"
    assert labels.get("traefik.docker.network") == "${EDGE_NETWORK_NAME:?required}"
    assert not any(key.startswith("traefik.http.") for key in labels), (
        "a router or middleware label here would carry an uninterpolated key (ADR 0013)"
    )


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


#: The one name that IS a network JWKS client. Banned outright, everywhere.
#:
#: `PyJWKClient` takes a URI and fetches. A verifier holding one has a trust
#: anchor decided by whatever answered the request, which is the thing ADR 0088's
#: rotation model cannot survive.
JWKS_CLIENT_NAME = "PyJWKClient"

#: Every transport this service could reach the network with.
#:
#: **`boto3` is in this set from Session 8 Run 5, and its absence was the hole**
#: (ADR 0124). The previous spelling banned five names and admitted boto3 --
#: through which `storage_client.py` has been calling `head_object` and
#: `delete_object` for a whole session. A guard that names transports and misses
#: the one actually in use is a filesystem fact standing in for a logic test,
#: which is D277's shape and CLAUDE.md §6's pattern.
TRANSPORT_NAMES = frozenset(
    {"urllib", "httpx", "requests", "aiohttp", "socket", "boto3", "botocore", "http"}
)

#: The modules permitted to name a transport, and which one, and why.
#:
#: A row is a reviewed act. The old blanket ban was reaching for exactly this and
#: could not express it, so it refused the wrong things and admitted the rest.
TRANSPORT_ALLOWLIST: dict[str, frozenset[str]] = {
    # The R2 adapter: presigning and the object lifecycle (ADR 0093, ADR 0107).
    "app/storage_client.py": frozenset({"boto3", "botocore"}),
    # The agent plane's one call upstream and its read executor, both
    # carrying the CALLER's own token (ADR 0125, ADR 0127).
    "app/mcp_upstream.py": frozenset({"urllib"}),
    # `urllib.parse` ONLY, for percent-encoding. This module builds a query
    # string and never sends one -- the scan sees the top-level package, so
    # the row is required, and the assertion below is what keeps it honest:
    # a module declared here may not name `urlopen` or `Request`.
    "app/mcp_query.py": frozenset({"urllib"}),
    # The agent plane's container-local health probe (ADR 0128). A loopback
    # GET to a route no Traefik router publishes, run by the container's own
    # healthcheck. Run 4 wrote this module and deleted it rather than weaken
    # the guard this allowlist replaced (D429); the row is what it was
    # waiting for.
    "app/mcp_health.py": frozenset({"urllib"}),
}

#: How a key set may be built. Both are local reads; neither can reach a network.
KEY_SET_CONSTRUCTORS = frozenset({"load", "from_path"})


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

    **Narrowed to its own subject in Session 8 Run 5 (ADR 0124), and the two
    tests below carry the rest.** This one used to ban five transports as a
    proxy for the property, which refused a PostgREST call that has nothing to do
    with key material and admitted the boto3 the service was already using.
    """
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in sorted(SERVICE_ROOT.rglob("*.py"))
        if JWKS_CLIENT_NAME in _referenced_names(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"{offenders} construct a network JWKS client"


def test_every_transport_in_the_service_is_declared_with_a_reason() -> None:
    """No module reaches the network unless ADR 0124's allowlist says which.

    **Replaces the blanket ban, and is stricter than it** (CLAUDE.md §5). The
    old version refused five names anywhere; this refuses EIGHT -- boto3 and
    botocore among them -- everywhere except in the modules that declare them.
    `storage_client.py` has been making real R2 round trips through boto3 since
    Session 7 and the old guard reported the tree clean.

    A module may name only the transport its row grants it, so a second one
    appearing in a declared module fails here too.
    """
    offenders: list[str] = []
    for path in sorted(SERVICE_ROOT.rglob("*.py")):
        relative = path.relative_to(SERVICE_ROOT).as_posix()
        used = _referenced_names(path.read_text(encoding="utf-8")) & TRANSPORT_NAMES
        permitted = TRANSPORT_ALLOWLIST.get(relative, frozenset())
        undeclared = used - permitted
        if undeclared:
            offenders.append(f"{relative} names {sorted(undeclared)}, which no row grants it")
    assert not offenders, offenders


def test_the_allowlist_describes_modules_that_exist_and_use_what_they_declare() -> None:
    """A row for a deleted module, or for a transport nobody imports, is a lie.

    The failure this prevents is the quiet one: a row outliving its module reads
    as a considered exemption and grants nothing, so the next reader believes the
    list is current. It is the same reasoning D211-D214 record about proofs that
    have never executed.
    """
    for relative, transports in sorted(TRANSPORT_ALLOWLIST.items()):
        path = SERVICE_ROOT / relative
        assert path.is_file(), f"{relative} is allowlisted and does not exist"
        used = _referenced_names(path.read_text(encoding="utf-8")) & TRANSPORT_NAMES
        assert used == transports, (
            f"{relative} declares {sorted(transports)} and names {sorted(used)}"
        )

    # `urllib` covers both `urllib.parse` (encoding) and `urllib.request`
    # (sending), and only two modules may send. Asserted separately because the
    # package name alone cannot tell them apart -- and a query builder that grew
    # a `urlopen` would otherwise be covered by its own row.
    senders = {"app/mcp_upstream.py", "app/mcp_health.py"}
    for relative in sorted(TRANSPORT_ALLOWLIST):
        names = _referenced_names((SERVICE_ROOT / relative).read_text(encoding="utf-8"))
        if relative in senders:
            continue
        assert not names & {"urlopen", "Request", "urlretrieve"}, (
            f"{relative} is allowlisted for encoding and names a sender"
        )


def test_a_key_set_is_only_ever_built_from_a_local_read() -> None:
    """The property the transport ban was a proxy for, asserted directly.

    Every `LocalKeySet` in this service comes from `load` or `from_path`, and
    both take bytes that were read locally -- a mounted file (ADR 0113) or the
    issuer's own signing key. Nothing constructs one from a response.

    The old guard inferred this from the absence of a transport, which is why it
    could be satisfied by importing a different one. This asks the question the
    docstring above has always been about.
    """
    constructions: list[str] = []
    for path in sorted(SERVICE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name):
                continue
            if node.func.value.id != "LocalKeySet":
                continue
            constructions.append(f"{path.relative_to(SERVICE_ROOT).as_posix()}:{node.func.attr}")

    assert constructions, "no LocalKeySet is constructed anywhere -- this test measures nothing"
    unexpected = [
        entry for entry in constructions if entry.rsplit(":", 1)[1] not in KEY_SET_CONSTRUCTORS
    ]
    assert not unexpected, f"a key set is built by something other than a local read: {unexpected}"


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

    # ADR 0124's addition, and the arm that would have caught the hole: the
    # scan must see boto3 as a transport, in both spellings, or the allowlist
    # above grants an exemption nothing was ever checking.
    assert "boto3" in _referenced_names("import boto3") & TRANSPORT_NAMES
    assert "boto3" in _referenced_names("client = boto3.client('s3')") & TRANSPORT_NAMES
    assert not _referenced_names('"""We use boto3 here."""') & TRANSPORT_NAMES

    # And it really is present in the source that the test above passes on.
    text = (SERVICE_ROOT / "app" / "tokens.py").read_text(encoding="utf-8")
    assert "PyJWKClient" in text, "the docstring that makes this control meaningful is gone"


def test_the_application_serves_exactly_the_declared_paths() -> None:
    """Two lists, and the router has to equal their union.

    D231 is the half about health: the project's public health answer stays
    `__apg/healthz`, and a third and fourth answer to "is this project up" is
    two more things to keep in step. `public_paths` is the other half -- what
    Run 10 will publish through the edge.

    Equality rather than containment, so a route added without a decision about
    which side of the edge it belongs on fails here rather than appearing on the
    internet. That is not hypothetical: the whole of Run 7's boundary was "this
    service is not routable yet", and the thing that keeps it true is a test
    that notices a new path.
    """
    application = main_module.create_app("auth")
    served = set(main_module.route_paths(application))
    declared = set(main_module.health_paths()) | set(main_module.public_paths())

    assert served == declared, (
        f"unexpected: {sorted(served - declared)}; missing: {sorted(declared - served)}"
    )


def test_no_health_path_is_in_the_public_list() -> None:
    """The two lists are disjoint, which is what makes their union meaningful.

    Without this, moving `/health/ready` into `public_paths` would keep the
    equality above green while publishing a health endpoint through the edge --
    the exact thing D231 decided against.
    """
    assert set(main_module.health_paths()).isdisjoint(main_module.public_paths())


def test_the_admin_surface_is_reachable_only_under_admin() -> None:
    """Every published path is one of the two prefixes the plan names (§6)."""
    for path in main_module.public_paths():
        assert path.startswith(("/auth/", "/admin/")), path


def test_the_application_generates_no_openapi_document() -> None:
    """`/docs/app` is a separate surface built from a reviewed snapshot (D226)."""
    application = main_module.create_app("auth")
    assert application.openapi_url is None
    assert application.docs_url is None
    assert application.redoc_url is None


def test_the_healthcheck_asks_the_path_the_application_serves(
    auth_service: dict[str, Any],
) -> None:
    """The pair D236 is about: a probe naming a path nothing answers."""
    command = " ".join(str(part) for part in auth_service["healthcheck"]["test"])
    served = main_module.route_paths(main_module.create_app("auth"))
    assert any(path in command for path in served), (
        f"the healthcheck asks for a path the application does not serve: {command}"
    )


# ---------------------------------------------------------------------------
# Two guards the Run 4 battery asked for (D843)
#
# Both mutations SURVIVED, and both survived for the same reason: a docstring
# claimed a property its body did not check. That is D374's shape -- a test
# passing for an unrelated reason -- and the battery is the only thing that
# distinguishes it from coverage.
# ---------------------------------------------------------------------------


def _function(source: ast.Module, name: str) -> ast.AST:
    for node in ast.walk(source):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is gone from the service")


def test_every_state_check_happens_after_the_hash_comparison() -> None:
    """The ordering that makes four failures cost the same (ADR 0172, D843).

    `login` and `agent_token` both verify the credential BEFORE consulting
    status or expiry, so an unknown subject, a wrong secret, a disabled account
    and an expired credential all pay one Argon2 comparison and answer in the
    same time. Reversing it makes the cheap cases measurable from outside, and
    an attacker who can time a request can then enumerate which agent ids exist.

    **The battery is why this exists.** Moving the expiry check above the hash
    changed no status code and no response body, so the endpoint test that
    asserted those two things stayed green -- while the property its docstring
    claimed was gone. Asserted over the AST rather than the text, because the
    subject is an ORDER of statements and a string scan cannot see one.
    """
    source = ast.parse(
        (REPO_ROOT / "services" / "auth-api" / "app" / "service.py").read_text("utf-8")
    )

    for name, checks in (
        ("login", ("status",)),
        ("agent_token", ("status", "secret_expired")),
    ):
        body = _function(source, name)
        # `max`, not `min`. `agent_token` verifies TWICE -- once against the
        # dummy in the non-UUID branch, which exists for this very timing
        # property -- and that call is earlier than the lookup. Anchoring on the
        # first one let a state check inserted after the lookup compare as
        # "after a verify", and the mutation survived. Every state read must
        # follow EVERY verify.
        verify_line = max(
            node.lineno
            for node in ast.walk(body)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "verify"
        )
        for attribute in checks:
            reads = [
                node.lineno
                for node in ast.walk(body)
                if isinstance(node, ast.Attribute) and node.attr == attribute
            ]
            assert reads, f"{name} no longer reads {attribute}"
            assert min(reads) > verify_line, (
                f"{name} reads `{attribute}` at line {min(reads)}, before the credential is "
                f"verified at line {verify_line}. The cheap failures become measurable by "
                "timing, and an id that exists becomes distinguishable from one that does not"
            )


def test_the_agent_expiry_column_has_no_default_so_it_does_not_backfill() -> None:
    """The migration's decision, asserted where a future edit would undo it (D843).

    `ADD COLUMN ... DEFAULT` **backfills every existing row** -- so a DEFAULT
    here would give a deadline to credentials already in use and expire agents
    whose operators were never told the rule changed. The column is added bare
    and the two functions that issue a secret supply the value.

    **The battery is why this exists.** Adding a DEFAULT left every endpoint
    test green, because those fixtures create their agents after the migration
    has run and never observe a backfill. The only reader that can see this is
    one that reads the `ALTER`.
    """
    migration = (
        REPO_ROOT / "migrations" / "templates" / "0025-agent-credential-lifecycle.sql"
    ).read_text(encoding="utf-8")

    alter = re.search(
        r"ALTER TABLE app_private\.agent_credentials\s*\n\s*ADD COLUMN expires_at[^;]*;",
        migration,
    )
    assert alter, "the expires_at column is no longer added by 0025"
    assert "DEFAULT" not in alter.group(0), (
        "expires_at gained a column DEFAULT, which backfills every existing row and "
        f"expires credentials issued before this release: {alter.group(0)!r}"
    )

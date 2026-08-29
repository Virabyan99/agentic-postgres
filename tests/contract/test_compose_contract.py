"""Validation-only Compose model and its controlled wrapper (runbook §7).

The central test here is ``test_inherited_variable_cannot_override_*``. Compose
gives shell environment variables *higher* interpolation precedence than
``--env-file`` values, so without the wrapper a stray ``COMPOSE_PROJECT_NAME``
would silently point a command at the wrong project and the model would still
render successfully.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from rendered_fixtures import (  # type: ignore[import-not-found]
    DETAIL,
    STATE,
    needs_rendered_fixtures,
)

from agentic_postgres import REPO_ROOT, output_migrations

pytestmark = [pytest.mark.contract, pytest.mark.p0]

COMPOSE_SH = REPO_ROOT / "bin" / "compose.sh"
MODEL = REPO_ROOT / "compose.yaml"
ALPHA = REPO_ROOT / ".generated" / "fixture-alpha-dev"
ALPINE = REPO_ROOT / ".generated" / "fixture-alpine-dev"

#: The twenty tests below resolve a Compose model or read an outputs document,
#: which needs `./deploy.sh --render-only` to have run. The other thirty-three
#: read committed source -- `compose.yaml`, `bin/compose.sh`, the Dockerfiles,
#: the edge model -- and need nothing.
#:
#: This was a **module-level** skip until Run 10, so in a clean checkout and in
#: the offline gate none of the 53 ran. That is how D178 reached a live deploy:
#: the assertion that would have caught a one-character interpolation error is
#: in this file, and it was not running. A skip wider than its dependency is a
#: coverage hole shaped like a precaution.
#:
#: It then asked `ALPHA.is_dir()` for one more run, which is an existence check
#: standing in for a currency check, and the Session 5 host gate ran this module
#: against a fixture rendered four schema versions earlier (D212, ADR 0073). The
#: guard is now the shared one: absent skips, **stale fails**.


def compose(project_dir: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [str(COMPOSE_SH), str(project_dir), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


def rendered(project_dir: Path) -> dict[str, Any]:
    result = compose(project_dir, "--profile", "contract", "config")
    assert result.returncode == 0, result.stderr
    return yaml.safe_load(result.stdout)


def outputs(project_dir: Path) -> dict[str, Any]:
    return json.loads((project_dir / "outputs.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The model source
# ---------------------------------------------------------------------------


def test_every_interpolation_is_required(code_only) -> None:
    """No interpolation may render silently. Two spellings are required (ADR 0062).

    This asserted `endswith(":?required}")` for every reference until Run 9.
    **Replaced by a stricter pair under ADR 0062, not weakened.** The property
    that mattered is unchanged and is still asserted here: a bare `${VAR}` and a
    defaulted `${VAR:-x}` both render without complaint, and an empty resource
    name would collapse two projects onto one network (`DEP-ISO-002`).

    What the old spelling rule could not express is *which* required form a
    variable should take. Compose's two differ: `${VAR:?err}` refuses an empty
    value as well as an unset one, `${VAR?err}` refuses only unset. The old rule
    therefore permitted `:?` on a variable whose empty value is meaningful — the
    defect D178 records, which passed for the life of the file and stopped the
    first live deploy at step 1.

    That half is now measured rather than spelled, in
    `test_output_schema.py::test_no_required_interpolation_names_a_value_that_renders_empty`:
    the set of variables that render empty and the set spelled `?required` must
    be the same set, both derived. It lives there because **this module skips
    entirely without rendered fixtures**, and an assertion that does not run in a
    clean checkout is how the gap survived.

    Goes red if: any reference loses its `?`, or gains a `:-` default.

    Comments are stripped first. The explanation of *why* one variable takes the
    lax spelling necessarily contains both spellings as examples, and scanning
    raw text counts them — the fifth time that shape has produced a false
    failure here, and the reason `code_only` is a shared fixture.
    """
    text = code_only(MODEL.read_text(encoding="utf-8"))
    for reference in re.findall(r"\$\{[^}]+\}", text):
        assert reference.endswith((":?required}", "?required}")), (
            f"{reference} is not a required interpolation"
        )
        assert ":-" not in reference and not re.search(r"[^:?]-", reference.split("}")[0][2:]), (
            f"{reference} carries a default; a default is a value nobody chose"
        )


def test_model_hardcodes_no_identity() -> None:
    text = MODEL.read_text(encoding="utf-8")
    for forbidden in ("fixture-alpha", "fixture-alpine", "apg-fixture"):
        assert forbidden not in text, f"compose.yaml hard-codes {forbidden}"


def test_model_does_not_use_container_name() -> None:
    """`container_name` is not project-scoped and would collide across projects.

    Checked structurally rather than by grepping the file: the model's own
    comment explains why the key is forbidden, and a text search would match
    that explanation.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    for name, service in document["services"].items():
        assert "container_name" not in service, f"service {name} sets container_name"


def test_model_references_only_locked_image_variables() -> None:
    """No image may bypass the lock by naming a repository inline.

    Session 2 added services that *build* rather than pull. A `FROM` line in a
    Dockerfile is a second, unlocked version declaration that
    `bin/lock-versions.sh` cannot see, so a built service must take its base
    image from the lock through a build argument instead — and this asserts one
    of the two forms is present, never neither.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    for name, service in document["services"].items():
        if "image" in service:
            image = service["image"]
            assert image.startswith("${") and image.endswith(":?required}"), (
                f"service {name} does not take its image from a locked variable: {image}"
            )
            continue

        # Every build argument whose name ends in BASE_IMAGE, not the one
        # spelled `BASE_IMAGE`. `services/docs/` is multi-stage and takes two
        # (ADR 0069); a rule that read one key would have checked the first
        # stage and ignored the second, which is the stage that ships.
        arguments = service["build"]["args"]
        bases = {key: value for key, value in arguments.items() if key.endswith("BASE_IMAGE")}
        assert bases, f"service {name} builds from no *BASE_IMAGE argument at all"
        for key, base in bases.items():
            assert base.startswith("${") and base.endswith(":?required}"), (
                f"service {name} builds from an unlocked base image via {key}: {base}"
            )


def test_no_dockerfile_names_its_own_base_image() -> None:
    """The other half of the same rule, checked where it could be broken.

    A `FROM python:3.12-slim` would build successfully, pass every Compose
    assertion, and quietly reintroduce a floating tag into a public-facing
    image.

    **Replaced, stricter, under ADR 0069.** This required the literal
    `FROM ${BASE_IMAGE}`, which `services/docs/` cannot satisfy: it is the first
    multi-stage first-party build, and its two stages need two different bases.
    Matching a form rather than the property let the form become the rule. What
    is checked now is the property, in three parts rather than one:

    * every `FROM` names a variable reference and nothing else, so no tag, no
      digest and no bare image name can appear;
    * the variable it names is declared as an `ARG` **in that file**, so a
      reference to a variable nobody passes -- which resolves to empty and fails
      obscurely at build time -- is caught here instead;
    * the name ends in `BASE_IMAGE`, so the wiring in `compose.yaml` stays
      greppable.

    A later stage may name an earlier one by its `AS` alias; that is not a base
    image, it is this file's own output.
    """
    from_line = re.compile(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?$", re.IGNORECASE)
    argument_reference = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")

    for dockerfile in sorted((REPO_ROOT / "services").rglob("Dockerfile")):
        text = dockerfile.read_text(encoding="utf-8")
        name = dockerfile.relative_to(REPO_ROOT)
        declared = set(re.findall(r"^ARG\s+([A-Z][A-Z0-9_]*)", text, re.MULTILINE))
        froms = [
            line.strip() for line in text.splitlines() if line.strip().upper().startswith("FROM ")
        ]
        assert froms, f"{name} has no FROM line"

        stages: set[str] = set()
        for line in froms:
            matched = from_line.match(line)
            assert matched, f"{name}: unparsable FROM line: {line}"
            reference, alias = matched.group(1), matched.group(2)

            if reference in stages:
                if alias:
                    stages.add(alias)
                continue

            variable = argument_reference.match(reference)
            assert variable, f"{name} names its own base image: {line}"
            assert variable.group(1) in declared, (
                f"{name}: {line} references {variable.group(1)}, which no ARG in this "
                "file declares. Docker resolves an undeclared build argument to the "
                "empty string, so this fails as `invalid reference format` rather than "
                "as the missing declaration it is"
            )
            assert variable.group(1).endswith("BASE_IMAGE"), (
                f"{name}: {line} takes its base from {variable.group(1)}, which does not "
                "end in BASE_IMAGE. The suffix is what makes the wiring in compose.yaml "
                "findable from the Dockerfile and back"
            )
            if alias:
                stages.add(alias)


def test_no_project_service_publishes_a_host_port() -> None:
    """Only Traefik publishes a host port (runbook §9, SEC-NET-001).

    Asserted against the model source as well as the resolved model, because a
    `ports` entry added here would be reviewed once and then enforced only by a
    live test that needs a host.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    for name, service in document["services"].items():
        assert "ports" not in service, f"service {name} publishes a host port"


#: The uid every BUILT service runs as, by service name (Session 10, D539).
#:
#: One shared literal until now, when `postgres` became the first service this
#: repository builds that legitimately runs as something else: 999 is the
#: image's own postgres user, it owns PGDATA, and 65532 would be a cluster that
#: cannot read its own data directory.
#:
#: A per-service map rather than a relaxed `!= 0`, and the distinction is the
#: whole repair. Widening to "not root" would accept any uid at all, including a
#: typo'd one -- weakening a passing assertion to admit a new case, which is
#: what D300 refuses. Pinning each service is STRICTER than one shared literal:
#: it now also fails on a service that starts or stops being built without a
#: decision, which the old form could not see.
BUILT_SERVICE_USERS = {
    "edge-probe": "65532:65532",
    "unlabeled-probe": "65532:65532",
    "secret-check": "65532:65532",
    "postgres": "999:999",
    "auth": "65532:65532",
    "storage": "65532:65532",
    "docs": "65532:65532",
    "mcp": "65532:65532",
    "client-psql": "65532:65532",
    "client-node-pg": "65532:65532",
    "client-psycopg": "65532:65532",
    "client-prisma": "65532:65532",
}

#: Built services whose root filesystem is writable, and there is exactly one.
#:
#: `postgres` cannot be otherwise: the entrypoint writes its socket, its PID
#: file and the whole of initdb's output, and a cluster with `read_only: true`
#: does not start. The other three hardening keys still apply to it, which is
#: what keeps this an exception rather than an exemption.
WRITABLE_ROOT_FILESYSTEM = frozenset({"postgres"})


def test_built_services_run_as_a_fixed_non_root_user() -> None:
    """A root container makes `cap_drop: ALL` and `no-new-privileges` cosmetic."""
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    built = {name for name, service in document["services"].items() if "build" in service}

    assert built == set(BUILT_SERVICE_USERS), (
        "a service started or stopped being built without a decision about which "
        f"uid it runs as. built={sorted(built)} declared={sorted(BUILT_SERVICE_USERS)}"
    )

    for name in sorted(built):
        service = document["services"][name]
        assert service["user"] == BUILT_SERVICE_USERS[name], (
            f"service {name} runs as {service.get('user')!r}"
        )
        assert service["user"].split(":")[0] != "0", f"service {name} runs as root"
        if name not in WRITABLE_ROOT_FILESYSTEM:
            assert service["read_only"] is True, f"service {name} has a writable root filesystem"
        assert service["cap_drop"] == ["ALL"], f"service {name} retains capabilities"
        assert "no-new-privileges:true" in service["security_opt"], name


# ---------------------------------------------------------------------------
# The Session 3 cluster is project-internal (DBX-PG-002, offline half)
# ---------------------------------------------------------------------------


def test_postgres_joins_only_the_internal_network() -> None:
    """The boundary is the network, not a bind address.

    `internal: true` on that network means no route off the host at all. This
    is the claim SEC-NET-001's external scan of 5432 measures from Session 3
    on -- until now it found the port closed because nothing was listening,
    which is a different fact wearing the same green tick.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    # Session 10 (ADR 0147). The cluster gained a SECOND network and this
    # assertion is replaced by a stricter one rather than relaxed: the old form
    # said "only internal" and would have been satisfied by any single network,
    # including `edge`. What matters is which two, and which one it is NOT on.
    assert document["services"]["postgres"]["networks"] == ["internal", "backup"]
    assert document["networks"]["internal"]["internal"] is True
    assert "edge" not in document["services"]["postgres"]["networks"], (
        "the database is on the network Traefik's public side lives on. `backup` "
        "exists precisely so that reaching R2 does not require this (D516)"
    )


def test_the_backup_network_carries_the_database_and_nothing_else() -> None:
    """ADR 0147's blast radius, stated as a membership rather than as prose.

    The egress network exists for one command in one container. A second member
    added later would widen what can reach the internet from inside a project,
    and it would do so invisibly -- there is no other assertion anywhere that
    counts who is on it.

    `internal: true` is deliberately NOT set on it: that is the whole point of
    the network. The assertion is that it is absent, so that a future edit
    "hardening" it -- which would silently stop every backup -- fails here
    instead of at the first archive-push.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))

    members = sorted(
        name
        for name, service in document["services"].items()
        if "backup" in (service.get("networks") or [])
    )
    assert members == ["postgres"], f"the egress network has other members: {members}"
    assert document["networks"]["backup"].get("internal") is not True, (
        "the backup network is marked internal, so it has no route off the host "
        "and archive-push cannot reach the repository. That is the state D516 "
        "measured and this network exists to leave"
    )


def test_postgres_carries_no_traefik_label_of_any_kind() -> None:
    """Not `traefik.enable`, not a router, not even the network hint.

    Checked over every key rather than against a list of known-dangerous ones:
    the edge-probe carries `traefik.docker.network` legitimately, so a test
    that only looked for `traefik.enable` would let a router label through.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    labels = document["services"]["postgres"].get("labels", {}) or {}
    offenders = [key for key in labels if "traefik" in str(key).lower()]
    assert not offenders, f"postgres carries Traefik labels: {offenders}"


def test_the_migration_service_is_also_project_internal() -> None:
    """dbmate reaches the cluster over the project network and nothing else."""
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    dbmate = document["services"]["dbmate"]
    assert dbmate["networks"] == ["internal"]
    assert "ports" not in dbmate
    labels = dbmate.get("labels", {}) or {}
    assert not [key for key in labels if "traefik" in str(key).lower()]


@needs_rendered_fixtures
def test_no_database_credential_appears_in_the_model_or_the_env() -> None:
    """The credential reaches dbmate by value only inside the container.

    The model does contain the *shape* of a connection URL, and from Run 7 it
    has to: the entrypoint assembles one from three interpolated identifiers and
    a password it reads out of a mounted file, because a stored URL would embed
    three derived names in an operator-entered value (ADR 0034).

    So the assertion is about the userinfo, not about the substring. Every
    `postgres://` in the model must be followed by variable references all the
    way to the `@`: a literal anywhere in there is a credential in the model,
    which is the thing being forbidden. `postgresql://` and `PGPASSWORD` stay
    banned outright -- nothing here has a use for either.

    Session 5 added the second URL and made the check understand Compose's own
    syntax. `${VAR:?required}` contains a colon, so splitting the userinfo on
    colons used to produce `?required}` and read it as a literal password. That
    is a parser fault, not a finding: the references are expanded away first,
    and what is asserted about the remainder is *stricter* than before -- every
    part must now be either a variable reference or empty, where it previously
    only had to start with `$`.
    """
    text = MODEL.read_text(encoding="utf-8")
    for marker in ("postgresql://", "PGPASSWORD"):
        assert marker not in text, f"compose.yaml contains {marker}"

    urls = re.findall(r"postgres://([^@\s]*)@", text)
    assert urls, "the model no longer assembles a connection URL; this test is measuring nothing"
    for userinfo in urls:
        # `${VAR}`, `${VAR:?required}` and the `$$VAR` a shell entrypoint sees.
        # Replaced by a marker rather than deleted, so that `${A}:${B}` still
        # shows two parts and an empty one cannot hide a dropped literal.
        expanded = re.sub(r"\$\{[^}]*\}|\$\$[A-Za-z_][A-Za-z0-9_]*", "$", userinfo)
        for part in expanded.split(":"):
            assert part == "$", (
                f"compose.yaml has a literal in a connection URL's userinfo: {part!r} "
                f"(from {userinfo!r})"
            )

    for directory in (ALPHA, ALPINE):
        env = (directory / "compose.env").read_text(encoding="utf-8")
        for marker in ("postgresql://", "postgres://", "PASSWORD", "PGPASSWORD"):
            assert marker not in env, f"{directory.name}/compose.env contains {marker}"


@needs_rendered_fixtures
def test_the_postgres_memory_limit_exceeds_the_declared_budget() -> None:
    """The measured failure, asserted on the rendered pair rather than the rule.

    `config` refuses a manifest whose limit is at the budget. This checks the
    other end -- that what actually reaches Compose still satisfies it, so a
    future renderer that emitted the budget into POSTGRES_MEMORY_LIMIT would
    fail here rather than on a host, where it looks like a slow cluster.
    """
    for directory in (ALPHA, ALPINE):
        budget = outputs(directory)["database"]["budget"]
        assert budget["memory_limit_mb"] > budget["unreclaimable_mb"], directory.name
        assert budget["shm_size_mb"] >= budget["shared_buffers_mb"], directory.name


def test_the_edge_probe_is_inert_without_the_runtime_override() -> None:
    """`traefik.enable` is absent from the committed model, deliberately.

    The router labels are rendered into the root-owned runtime override, so this
    file on its own cannot expose anything. Exposure is an act of deployment
    rather than a property of a file in the repository (ADR 0013).
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    labels = document["services"]["edge-probe"]["labels"]
    assert "traefik.enable" not in labels
    assert labels["apg.traefik.scope"] == "managed"
    assert not any(key.startswith("traefik.http.") for key in labels)


def test_the_unlabeled_probe_carries_no_discovery_label() -> None:
    """The control for DEP-EDGE-002 only controls if it is genuinely unlabeled."""
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    service = document["services"]["unlabeled-probe"]
    assert "labels" not in service, "the unlabeled probe has labels; it proves nothing"


def test_the_secret_check_service_declares_no_secret_source() -> None:
    """The generation path does not exist until materialization runs.

    A `file:` source in the committed model would either be a guess or a stable
    path -- and a stable path is exactly the shared, mutable location that
    immutable generations exist to avoid (ADR 0010).
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    assert "secrets" not in document, "the committed model declares a secret source"
    assert "secrets" not in document["services"]["secret-check"]


def test_probe_is_profile_gated() -> None:
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    assert document["services"]["contract-probe"]["profiles"] == ["contract"]
    assert document["services"]["contract-probe"]["restart"] == "no"


def test_internal_network_is_internal() -> None:
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    assert document["networks"]["internal"]["internal"] is True


# ---------------------------------------------------------------------------
# Rendered names match outputs.json exactly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("project_dir", [ALPHA, ALPINE], ids=lambda p: p.name)
@needs_rendered_fixtures
def test_model_renders(project_dir: Path) -> None:
    assert rendered(project_dir)["name"]


@pytest.mark.parametrize("project_dir", [ALPHA, ALPINE], ids=lambda p: p.name)
@needs_rendered_fixtures
def test_rendered_resource_names_match_outputs(project_dir: Path) -> None:
    """Runbook §12: the names Docker would create must equal the ones we published."""
    model = rendered(project_dir)
    declared = outputs(project_dir)["compose"]

    assert model["name"] == declared["project_name"]
    assert model["networks"]["edge"]["name"] == declared["networks"]["edge"]
    assert model["networks"]["internal"]["name"] == declared["networks"]["internal"]
    assert model["volumes"]["postgres-data"]["name"] == declared["volumes"]["postgres"]


@needs_rendered_fixtures
def test_rendered_image_carries_the_locked_digest() -> None:
    image = rendered(ALPHA)["services"]["contract-probe"]["image"]
    assert "@sha256:" in image
    locked = next(
        line.split("=", 1)[1]
        for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines()
        if line.startswith("PYTHON_RUNTIME_IMAGE=")
    )
    assert image == locked


def test_the_rendered_fixtures_are_not_stale() -> None:
    """A fixture older than the model is a wrong answer, not a missing one.

    New in Run 10 under ADR 0073. The Session 5 host gate resolved this module's
    Compose model against `.generated/fixture-alpha-dev` rendered on 2026-08-10
    at `schema_version: 4` -- before PostgREST existed -- and got eleven
    "missing a value" interpolation errors, which read as a defect in
    `compose.yaml`. The model was fine (D212).

    Absent is a skip: a clean checkout has rendered nothing and has done nothing
    wrong. **Stale is this failure**, and it is the only one, because the tests
    that depend on the fixture skip citing staleness rather than each producing
    its own symptom for the same cause.

    `schema_version` is a proxy, and `rendered_fixtures` says what it does not
    catch. It catches the drift that happened.
    """
    assert STATE != "stale", (
        f"the rendered fixtures are stale: {DETAIL}. "
        f"Every test that reads them is skipping, so this run measures the model "
        f"and not the render."
    )
    assert STATE in {"absent", "current"}, f"unknown fixture state {STATE!r}: {DETAIL}"


def test_the_fixture_currency_check_names_the_version_the_code_renders() -> None:
    """The guard's authority is the code's, not a number typed beside it.

    A currency check with its own copy of the current version is the tautology
    this repository keeps producing -- it would agree with itself while both
    drifted away from `output_migrations`. Asserting the wiring rather than the
    value, so a bump to `CURRENT_VERSION` needs no edit here.
    """
    import rendered_fixtures  # type: ignore[import-not-found]

    source = (REPO_ROOT / "tests" / "contract" / "rendered_fixtures.py").read_text(encoding="utf-8")
    assert "output_migrations.CURRENT_VERSION" in source, (
        "the currency check must read the version from output_migrations"
    )
    assert rendered_fixtures.output_migrations.CURRENT_VERSION == output_migrations.CURRENT_VERSION


@needs_rendered_fixtures
def test_two_projects_render_disjoint_resource_names() -> None:
    alpha, alpine = rendered(ALPHA), rendered(ALPINE)
    assert alpha["name"] != alpine["name"]
    assert alpha["networks"]["edge"]["name"] != alpine["networks"]["edge"]["name"]
    assert alpha["networks"]["internal"]["name"] != alpine["networks"]["internal"]["name"]
    assert alpha["volumes"]["postgres-data"]["name"] != alpine["volumes"]["postgres-data"]["name"]


# ---------------------------------------------------------------------------
# The override defence (runbook §7.2, §9 check 14)
# ---------------------------------------------------------------------------


@needs_rendered_fixtures
def test_inherited_project_name_cannot_override_the_generated_one() -> None:
    result = compose(
        ALPHA, "--profile", "contract", "config", env={"COMPOSE_PROJECT_NAME": "hijacked"}
    )
    assert result.returncode == 0, result.stderr
    assert "hijacked" not in result.stdout
    assert yaml.safe_load(result.stdout)["name"] == outputs(ALPHA)["compose"]["project_name"]


@needs_rendered_fixtures
def test_inherited_image_cannot_override_the_locked_digest() -> None:
    result = compose(
        ALPHA,
        "--profile",
        "contract",
        "config",
        env={"PYTHON_RUNTIME_IMAGE": "docker.io/library/evil:latest"},
    )
    assert result.returncode == 0, result.stderr
    assert "evil:latest" not in result.stdout
    assert "@sha256:" in yaml.safe_load(result.stdout)["services"]["contract-probe"]["image"]


@needs_rendered_fixtures
def test_inherited_network_name_cannot_override() -> None:
    result = compose(
        ALPHA, "--profile", "contract", "config", env={"EDGE_NETWORK_NAME": "hijacked-edge"}
    )
    assert result.returncode == 0, result.stderr
    assert "hijacked-edge" not in result.stdout


def test_wrapper_uses_an_allowlist_not_a_denylist() -> None:
    """`env -u` cannot be proven complete; `env -i` plus a list can.

    Comments are stripped first: the wrapper documents why it rejects the
    denylist approach, and that explanation names the thing being rejected.
    """
    code = "\n".join(
        line
        for line in COMPOSE_SH.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    )
    assert "env -i" in code
    assert "env -u" not in code


def test_wrapper_never_shell_sources_an_env_file() -> None:
    text = COMPOSE_SH.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not re.match(r"^(\.|source)\s+.*env", stripped), f"sources an env file: {line}"


# ---------------------------------------------------------------------------
# Session 1 starts nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcommand",
    ["up", "run", "start", "create", "restart", "exec", "attach", "cp", "watch", "scale"],
)
@needs_rendered_fixtures
def test_container_starting_subcommands_are_refused(subcommand: str) -> None:
    """Still exit 10 by default. Session 2 added a way through, not a hole.

    The first eight parameters are unchanged from Session 1; what changed
    there is the message: refusal is now conditional on ``--runtime`` rather
    than on the session, so asserting the old "Session 1 starts nothing" text
    would be asserting a sentence rather than a behaviour (ADR 0013).
    ``watch`` and ``scale`` were added after an audit against the currently
    installed Compose found both start containers from a subcommand that was
    not refused (ADR 0022).
    """
    result = compose(ALPHA, subcommand)
    assert result.returncode == 10, f"{subcommand} returned {result.returncode}"
    assert "requires --runtime with root" in result.stderr


@pytest.mark.parametrize("subcommand", ["up", "restart", "exec"])
@needs_rendered_fixtures
def test_runtime_mode_requires_root(subcommand: str) -> None:
    """Docker access is root-equivalent, so --runtime is not a flag you just add.

    The privilege check runs before the allowlist check deliberately: what an
    unprivileged caller may do is the same question regardless of which
    subcommand they asked for.
    """
    result = compose(ALPHA, "--runtime", subcommand)
    assert result.returncode == 3, f"{subcommand} returned {result.returncode}"
    assert "requires root" in result.stderr


# ---------------------------------------------------------------------------
# ADR 0021 -- a flag's value must not be mistaken for the subcommand
# ---------------------------------------------------------------------------


def _first_subcommand(*args: str, tmp_path: Path) -> str:
    """Call the real ``first_subcommand`` out of bin/compose.sh.

    Sources every definition in the script except its trailing `main "$@"`
    call, so this exercises the actual parser rather than a description of
    it. ``COMPOSE_ARGS`` is set to ``args`` before calling the function.
    """
    text = COMPOSE_SH.read_text(encoding="utf-8")
    body = text[: text.rindex('main "$@"')]
    quoted = " ".join(shlex.quote(a) for a in args)
    harness = tmp_path / "first_subcommand.sh"
    harness.write_text(body + f"\nCOMPOSE_ARGS=({quoted})\nfirst_subcommand\n", encoding="utf-8")
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True, check=True)
    return result.stdout


@needs_rendered_fixtures
def test_a_flag_with_a_value_cannot_smuggle_a_container_start() -> None:
    """A value-taking flag ahead of the subcommand must not defeat FORBIDDEN.

    Before ADR 0021, ``first_subcommand`` returned the flag's value
    (``session2``) instead of ``up``. ``session2`` is not in FORBIDDEN, so the
    refusal that is supposed to fire for every container-starting subcommand,
    unconditionally, by default, silently did not -- and the real
    ``docker compose ... up`` that followed still received the unexamined
    ``up`` in COMPOSE_ARGS.
    """
    result = compose(ALPHA, "--profile", "session2", "up")
    assert result.returncode == 10, result.stderr
    assert "requires --runtime with root" in result.stderr


@pytest.mark.parametrize("subcommand", ["up", "restart"])
@needs_rendered_fixtures
def test_runtime_call_with_a_flag_value_still_reaches_the_privilege_gate(
    subcommand: str,
) -> None:
    """The exact shape ``bin/project-runtime.sh`` uses
    (``--runtime --profile session2 <subcommand>``), run unprivileged.

    This alone does not distinguish a correct resolution from the ADR 0021
    bug: the privilege check in ``main()`` runs before the allowlist check
    regardless of which subcommand was resolved, by design
    (``test_runtime_mode_requires_root``). What it proves is that the parser
    change does not disturb that ordering, or raise before reaching it.
    ``test_first_subcommand_skips_a_flags_value``, below, is the test that
    actually pins the resolution.
    """
    result = compose(ALPHA, "--runtime", "--profile", "session2", subcommand)
    assert result.returncode == 3, f"{subcommand} returned {result.returncode}: {result.stderr}"
    assert "requires root" in result.stderr


def test_first_subcommand_skips_a_flags_value(tmp_path: Path) -> None:
    """The direct regression test for ADR 0021.

    Calls the real ``first_subcommand``, not a reimplementation of it, and
    proves it returns the subcommand rather than the value of a flag written
    ahead of it -- for both call shapes this repository actually uses
    (``--profile session2 up``/``down`` in bin/project-runtime.sh, and
    ``--profile contract config`` in bin/deploy-project.py's
    ``_model_digest``) and for the ``--flag=value`` form, which needs no
    entry in ``SUBCOMMAND_VALUE_FLAGS`` because it consumes nothing further.
    """
    up_args = ("--profile", "session2", "up", "-d", "--wait")
    assert _first_subcommand(*up_args, tmp_path=tmp_path) == "up"
    assert _first_subcommand("--profile", "session2", "down", tmp_path=tmp_path) == "down"
    assert _first_subcommand("--profile", "contract", "config", tmp_path=tmp_path) == "config"
    assert _first_subcommand("--profile=contract", "config", tmp_path=tmp_path) == "config"


def test_the_runtime_allowlist_excludes_container_entry_verbs() -> None:
    """`exec`, `attach`, `cp`, `watch` and `scale` all reach inside a container.

    --runtime does not grant them even to root. `run` was among them until
    Session 3, when the migration plane needed a one-shot container and said so
    in an ADR, which is the process the old comment on this list asked for
    (ADR 0034). It is the only addition, and it arrives with two refusals that
    the rest of the allowlist does not need -- asserted below, because `run`
    without them is a way to execute anything as root inside a project's
    network with its secrets mounted.

    Asserted against the script's allowlist because proving it at runtime would
    need a root test process.
    """
    text = COMPOSE_SH.read_text(encoding="utf-8")
    allowed = re.search(r'RUNTIME_ALLOWED="([^"]*)"', text)
    assert allowed is not None
    permitted = set(allowed.group(1).split())
    assert permitted == {"up", "down", "restart", "build", "ps", "config", "logs", "run"}
    assert not permitted & {"exec", "attach", "cp", "start", "create", "watch", "scale"}

    refused = re.search(r'RUN_FORBIDDEN_FLAGS="([^"]*)"', text)
    assert refused is not None, "run is permitted with no flag refusals at all"
    flags = set(refused.group(1).split())
    assert {"--entrypoint", "-e", "--env", "--volume", "-v", "--user", "-u"} <= flags


@pytest.mark.parametrize(
    "flag",
    [("--entrypoint", "sh"), ("-e", "APG_X=1"), ("--env", "APG_X=1"), ("-v", "/etc:/etc")],
    ids=["entrypoint", "short-env", "long-env", "volume"],
)
@needs_rendered_fixtures
def test_run_refuses_the_flags_that_would_replace_the_reviewed_model(flag: tuple[str, ...]) -> None:
    """Declared and enforced are different things.

    The list above says which flags are refused; this runs the command. Both,
    because a list is only a comment until something reads it, and this one
    guards the difference between "start the service the model declares" and
    "start anything, as root, on that network".

    Unprivileged on purpose: the refusal is checked before the --runtime gate,
    so it does not depend on who asked.
    """
    result = compose(ALPHA, "--profile", "migration", "run", *flag, "dbmate")
    assert result.returncode == 10, result.stderr
    assert flag[0] in result.stderr


@needs_rendered_fixtures
def test_run_with_an_equals_form_flag_is_refused_too() -> None:
    """`--entrypoint=sh` is the same request as `--entrypoint sh`."""
    result = compose(ALPHA, "--profile", "migration", "run", "--entrypoint=sh", "dbmate")
    assert result.returncode == 10, result.stderr


def test_the_forbidden_list_is_pinned_to_the_audited_compose_surface() -> None:
    """The default refusal covers every container-starting Compose subcommand
    an audit has actually checked for -- not just Session 1's original eight.

    Formerly ``test_the_forbidden_list_is_unchanged_from_session_one``: that
    name and its "only the escape is new" docstring stopped being true once
    ``watch`` and ``scale`` were added. Both create or start containers and
    were reachable with no ``--runtime`` and no root before this (ADR 0022) --
    the list had drifted behind the Compose surface it was meant to cover,
    which is a way this test's old formulation (diffing the file against its
    own past self) could never have caught. This asserts the audited list is
    what ships; it does not claim the audit is complete against any future
    Compose release.
    """
    text = COMPOSE_SH.read_text(encoding="utf-8")
    forbidden = re.search(r'FORBIDDEN="([^"]*)"', text)
    assert forbidden is not None
    assert forbidden.group(1).split() == [
        "up",
        "run",
        "start",
        "create",
        "restart",
        "exec",
        "attach",
        "cp",
        "watch",
        "scale",
    ]


def _compose_definitions_at_real_root() -> str:
    """`bin/compose.sh`'s real definitions, minus the trailing `main "$@"`
    call, with ROOT_DIR pointed at the real repository.

    Same shape as the helper of the same name in
    ``tests/contract/test_project_state_roots.py``, used there for the same
    reason: the harness runs from a tmp_path, so ROOT_DIR must not resolve
    against that instead.
    """
    text = COMPOSE_SH.read_text(encoding="utf-8")
    body = text[: text.rindex('main "$@"')]
    patched = body.replace(
        'ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"',
        f"ROOT_DIR={shlex.quote(str(REPO_ROOT))}",
    )
    assert patched != body, "could not redirect ROOT_DIR for the test"
    return patched


def _extract_runtime_allowed_check(compose_source: str) -> str:
    """The literal RUNTIME_ALLOWED conditional out of `main()`, unmodified.

    Run directly instead of through `main()`, for the same reason
    ``tests/contract/test_project_state_roots.py`` runs OVERRIDE_REQUIRED's
    conditional directly rather than calling `main()`: the privilege check
    (``--runtime requires root``, exit 3) runs first, unconditionally, before
    RUNTIME_ALLOWED is ever consulted. As a non-root test process, a real
    ``bin/compose.sh --runtime watch`` or ``--runtime scale`` call can only
    ever exit 3 with "requires root" -- never exit 10 with the allowlist
    message -- regardless of whether RUNTIME_ALLOWED excludes them. A test
    against the real subprocess could not even be made to pass while
    asserting the allowlist's own exit code, let alone distinguish a correct
    exclusion from a regression.

    Slicing the real conditional out of the current file -- not retyping its
    condition or its die() message -- keeps this tied to the actual code: if
    the condition or the message changes, the slice changes with it; if the
    anchor below stops matching, ``.index`` raises instead of silently
    testing stale text.
    """
    start_marker = 'if ! in_list "${subcommand}" "${RUNTIME_ALLOWED}"; then'
    start = compose_source.index(start_marker)
    end_marker = "\n    fi\n"
    end = compose_source.index(end_marker, start) + len(end_marker)
    return compose_source[start:end]


def _runtime_allowed_result(tmp_path: Path, subcommand: str) -> subprocess.CompletedProcess[str]:
    """Resolve `subcommand` for a project-scope `--runtime <subcommand>` call
    exactly as `main()` would -- via the real `parse_arguments` and
    `configure_project_scope` -- then run the real RUNTIME_ALLOWED
    conditional against what it resolved to.
    """
    runtime_check = _extract_runtime_allowed_check(COMPOSE_SH.read_text(encoding="utf-8"))
    harness = _compose_definitions_at_real_root() + (
        f"\nparse_arguments {shlex.quote(str(ALPHA))} --runtime {shlex.quote(subcommand)}"
        '\nENV_FILE_ARGS=(--env-file "${LOCK_ENV}")'
        '\nPROJECT_KEY=""'
        "\nconfigure_project_scope"
        '\nsubcommand="$(first_subcommand)"'
        f"\n{runtime_check}\n"
    )
    harness_path = tmp_path / "harness.sh"
    harness_path.write_text(harness, encoding="utf-8")
    return subprocess.run(["bash", str(harness_path)], capture_output=True, text=True, check=False)


@pytest.mark.parametrize("subcommand", ["watch", "scale"])
@needs_rendered_fixtures
def test_watch_and_scale_are_refused_with_runtime_even_as_root(
    subcommand: str, tmp_path: Path
) -> None:
    """`--runtime` does not grant `watch` or `scale` even to root -- neither
    is in RUNTIME_ALLOWED (ADR 0022), so both hit the same allowlist refusal
    `exec`, `attach`, `run` and `cp` already get.

    Asserted on the message rather than the exit code alone: exit 10 here is
    the allowlist's own die(), distinct from the privilege gate's exit 3 --
    but see `_extract_runtime_allowed_check` for why this cannot be proven
    by calling `bin/compose.sh` itself as a non-root test process.
    """
    result = _runtime_allowed_result(tmp_path, subcommand)
    assert result.returncode == 10, result.stderr
    assert "not permitted in --runtime mode" in result.stderr
    assert f"'{subcommand}'" in result.stderr


# ---------------------------------------------------------------------------
# The shared edge plane
# ---------------------------------------------------------------------------


def edge(*args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [str(COMPOSE_SH), "--edge", "--host", str(REPO_ROOT / "host.example.yaml"), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


def test_edge_model_renders_from_the_host_manifest() -> None:
    """`--edge config` must work offline: CI has no root-owned edge state."""
    result = edge("config")
    assert result.returncode == 0, result.stderr
    document = yaml.safe_load(result.stdout)
    assert document["name"] == "apg-edge"
    assert set(document["services"]) == {"traefik", "docker-socket-proxy"}


def test_edge_scope_requires_a_host_manifest() -> None:
    result = subprocess.run(
        [str(COMPOSE_SH), "--edge", "config"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "--host" in result.stderr


def test_edge_mode_refuses_volume_removal() -> None:
    """A deleted production ACME file turns a failed renewal into a rate limit.

    The state is a bind mount, so `down -v` cannot actually reach it. Refusing
    the flag removes the question rather than relying on that remaining true.
    """
    for flag in ("-v", "--volumes"):
        result = edge("down", flag)
        assert result.returncode == 2, flag
        assert "ACME state" in result.stderr


def test_project_mode_refuses_volume_removal() -> None:
    """`DEP-REMOVE-001`. The database volume is not removable by any command.

    The sibling above covers **edge** mode; until this test, project mode had
    none — and project mode is the one holding customer data. `deploy.sh` and
    `project-runtime.sh down` both go through here, and `down` preserves the
    volume deliberately: *"removing it here would make `systemctl restart` a
    data-loss command."* This is the guard that makes that a property rather
    than a convention.

    **The argument order is load-bearing and was measured, not assumed.**
    `--runtime` triggers a root check the moment it is parsed, so the natural
    ordering — `--runtime down --volumes` — answers *"requires root"* (exit 3)
    to an unprivileged caller and never reaches the refusal. Putting `--volumes`
    first reaches it at exit 2. A privileged caller passes the root check and
    reaches the refusal in any order, which is the case that matters: the
    refusal protects the caller who could actually do the damage.

    Written this way rather than skipped for want of root, because a guard on a
    data volume that nothing has ever executed is the shape of every defect this
    project has recorded (D211-D214).
    """
    for flag in ("-v", "--volumes"):
        result = subprocess.run(
            [str(COMPOSE_SH), str(ALPHA), flag, "--runtime", "down"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2, (
            f"{flag} in project mode exited {result.returncode}, not 2. If it is 3, the "
            "root check ran first and this assertion never reached the refusal it names"
        )
        assert "database volume" in result.stderr, (
            f"{flag} was refused for some other reason: {result.stderr.strip()[:200]}"
        )


def test_inherited_edge_stack_name_cannot_override() -> None:
    result = edge("config", env={"EDGE_STACK_NAME": "hijacked"})
    assert result.returncode == 0, result.stderr
    assert "hijacked" not in result.stdout


def test_only_traefik_publishes_host_ports() -> None:
    """Runbook §9 and SEC-NET-001, asserted against the resolved edge model."""
    document = yaml.safe_load(edge("config").stdout)
    assert "ports" not in document["services"]["docker-socket-proxy"]
    published = {p["published"] for p in document["services"]["traefik"]["ports"]}
    assert published == {"80", "443"}


def test_traefik_has_no_direct_docker_socket_mount() -> None:
    """DEP-EDGE-003. The whole reason the socket proxy exists."""
    document = yaml.safe_load(edge("config").stdout)
    for mount in document["services"]["traefik"].get("volumes", []):
        assert "docker.sock" not in mount["source"], "Traefik mounts the Docker socket directly"


def test_the_socket_proxy_denies_every_unneeded_api_section() -> None:
    """`POST: 0` is the important one: it is what keeps read access read-only."""
    document = yaml.safe_load(edge("config").stdout)
    environment = document["services"]["docker-socket-proxy"]["environment"]

    assert {k for k, v in environment.items() if v == "1"} == {
        "CONTAINERS",
        "EVENTS",
        "NETWORKS",
        "PING",
        "VERSION",
    }
    for denied in ("POST", "EXEC", "BUILD", "IMAGES", "VOLUMES", "SECRETS", "SWARM", "INFO"):
        assert environment[denied] == "0", f"{denied} is not explicitly disabled"


def test_the_socket_proxy_is_not_privileged_and_is_unpublished() -> None:
    document = yaml.safe_load(edge("config").stdout)
    proxy = document["services"]["docker-socket-proxy"]
    assert proxy.get("privileged") is not True
    assert "ports" not in proxy
    assert proxy["cap_drop"] == ["ALL"]
    assert proxy["read_only"] is True
    assert proxy["networks"] == {"control": None}


def test_the_control_network_is_internal() -> None:
    """The proxy is unreachable from any project network because of this."""
    document = yaml.safe_load(edge("config").stdout)
    assert document["networks"]["control"]["internal"] is True


def test_the_edge_declares_no_named_volume() -> None:
    """ACME state is a bind mount so `docker volume prune` cannot reach it."""
    document = yaml.safe_load(edge("config").stdout)
    assert "volumes" not in document or not document["volumes"]


#: What ``bin/compose.sh`` prints when a daemon subcommand cannot reach Docker.
#: Matched on the message rather than the exit code, because exit 3 covers
#: several unrelated prerequisites and only this one is a question the calling
#: account is not permitted to ask.
DAEMON_UNREACHABLE = "the Docker daemon is unreachable"


@pytest.mark.parametrize("project_dir", [ALPHA, ALPINE], ids=lambda p: p.name)
@needs_rendered_fixtures
def test_no_container_is_running(project_dir: Path) -> None:
    """ADR 0018: failing to reach the daemon is not the same answer as "none".

    The operator account on the deployment host is deliberately not in the
    ``docker`` group — membership is root-equivalent — so on that host this
    question cannot be asked at all. Reporting the refusal as a failure makes it
    indistinguishable from a fixture container actually running.

    The claim is not dropped there. ``bin/session-02-check.sh --mode host`` runs
    as root and enumerates every running container directly.
    """
    result = compose(project_dir, "ps", "--quiet")

    if result.returncode != 0 and DAEMON_UNREACHABLE in result.stderr:
        pytest.skip(
            "the Docker daemon is unreachable from this account, so whether a fixture "
            "container is running cannot be determined here; proved on the host by "
            "session-02-check.sh --mode host, which runs as root (ADR 0018)"
        )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"containers exist: {result.stdout}"


def test_a_running_container_would_still_fail() -> None:
    """Guard the guard: the skip must not grow into "skip if compose fails".

    Asserted against the test's own source, because producing a genuinely
    running container inside the contract suite is the one thing this suite
    exists to forbid.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    body = source.split("def test_no_container_is_running", 1)[1].split("\ndef ", 1)[0]

    assert "DAEMON_UNREACHABLE in result.stderr" in body, (
        "the skip is not conditioned on the daemon being unreachable"
    )
    assert 'assert result.stdout.strip() == ""' in body, (
        "the running-container assertion was removed rather than gated"
    )
    # Requiring a non-zero exit too: without it, a compose that succeeded and
    # printed container ids while mentioning the daemon would be skipped.
    assert "result.returncode != 0 and" in body


def test_config_does_not_require_the_daemon() -> None:
    """`config` is rendered client-side; only daemon subcommands probe it."""
    text = COMPOSE_SH.read_text(encoding="utf-8")
    needs_daemon = re.search(r'NEEDS_DAEMON="([^"]*)"', text)
    assert needs_daemon is not None
    assert "config" not in needs_daemon.group(1).split()


# ---------------------------------------------------------------------------
# Wrapper input handling
# ---------------------------------------------------------------------------


@needs_rendered_fixtures
def test_env_files_are_disjoint() -> None:
    def keys(path: Path) -> set[str]:
        return {
            line.split("=", 1)[0]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        }

    overlap = keys(REPO_ROOT / "versions.env") & keys(ALPHA / "compose.env")
    assert not overlap, f"overlapping variables: {sorted(overlap)}"


@needs_rendered_fixtures
def test_missing_project_directory_is_rejected(tmp_path: Path) -> None:
    result = compose(tmp_path / "absent")
    assert result.returncode == 2


@needs_rendered_fixtures
def test_directory_without_compose_env_is_rejected(tmp_path: Path) -> None:
    result = compose(tmp_path)
    assert result.returncode == 2
    assert "compose.env" in result.stderr


def test_help_is_available() -> None:
    result = subprocess.run(
        [str(COMPOSE_SH), "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "generated-project-dir" in result.stdout


# ---------------------------------------------------------------------------
# The skip itself (Run 10)
# ---------------------------------------------------------------------------


def test_no_skip_applies_to_this_whole_module() -> None:
    """A module-level skip here is a coverage hole shaped like a precaution.

    This file skipped **entirely** unless `.generated/fixture-alpha-dev`
    existed, so in a clean checkout and in the offline gate none of its tests
    ran -- which is how D178, a one-character interpolation error, reached a
    live deploy with the assertion that would have caught it sitting in this
    file.
    """
    import ast

    # Parsed, not grepped. The first version scanned the raw text for the
    # attribute call below -- and this test's own failure message names it, so
    # it failed against a file that was correct. The same hazard `code_only`
    # exists for, inside a test written to close a coverage hole.
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    module_level = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "append"
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "pytestmark"
    ]
    assert not module_level, (
        "a module-level marker is back; a skip that applies to the whole file "
        "hides every assertion in it, including the ones that need nothing"
    )


def test_the_render_dependent_skip_stays_on_the_tests_that_need_it() -> None:
    """Every test that reaches a rendered fixture carries the marker -- including
    the ones that reach it through a helper.

    Followed transitively, and that is not thoroughness for its own sake: the
    first pass at narrowing this skip read each test's own body, so
    `test_watch_and_scale_are_refused_with_runtime_even_as_root` -- which
    resolves `ALPHA` inside `_runtime_allowed_result` -- looked pure and failed
    with `not a directory` the moment the fixtures were hidden. D191's lesson,
    one file over: a scan that stops at the function boundary misses what is one
    call away.

    Goes red if: a test gains a dependency on a render without the marker, or
    carries the marker without needing it -- the second direction matters too,
    because a marker nobody needs is a test that stops running in a clean
    checkout for no reason.
    """
    import ast

    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    markers = {"ALPHA", "ALPINE", "rendered", "outputs", "compose"}

    def reaches(name: str, seen: set[str]) -> bool:
        if name in seen or name not in functions:
            return False
        seen.add(name)
        for child in ast.walk(functions[name]):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                if child.id in markers or reaches(child.id, seen):
                    return True
        return False

    decorated = {
        name
        for name, node in functions.items()
        if any(
            isinstance(decorator, ast.Name) and decorator.id == "needs_rendered_fixtures"
            for decorator in node.decorator_list
        )
    }
    needed = {
        name
        for name in functions
        if name.startswith("test_")
        and name != "test_the_render_dependent_skip_stays_on_the_tests_that_need_it"
        and reaches(name, set())
    }

    assert needed, "nothing was found to need a render; this compared nothing"
    assert not (needed - decorated), (
        f"{sorted(needed - decorated)} reach a rendered fixture without the marker, so "
        "they fail rather than skip in a clean checkout"
    )
    assert not (decorated - needed), (
        f"{sorted(decorated - needed)} carry the marker and need no render, so they stop "
        "running in a clean checkout for no reason"
    )

"""Generated output contract (runbook §4.2-§4.4).

Determinism is asserted on **bytes**, not on parsed objects. Comparing
``json.loads`` results would pass even if key order, indentation, or line
endings changed, and those are exactly what makes a render reproducible.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config, naming, rendering, template_version

#: The Compose model, read as text so an interpolation's *spelling* can be
#: asserted. Parsing it resolves the interpolations away, which is the thing
#: under test.
MODEL = REPO_ROOT / "compose.yaml"

pytestmark = [pytest.mark.contract, pytest.mark.p0]

GENERATED_FILES = ("outputs.json", "compose.env", "rendered-summary.txt")


@pytest.fixture(scope="module")
def rendered() -> dict[str, Path]:
    """Render both fixtures once and return their published directories."""
    directories = {}
    for manifest in ("project.example.yaml", "project.second.example.yaml"):
        directory = rendering.render_project(
            REPO_ROOT / manifest,
            REPO_ROOT / "capabilities.example.yaml",
        )
        directories[manifest] = directory
    return directories


@pytest.fixture(scope="module")
def alpha(rendered: dict[str, Path]) -> dict[str, Any]:
    path = rendered["project.example.yaml"] / "outputs.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("manifest", ["project.example.yaml", "project.second.example.yaml"])
def test_rendered_output_validates(rendered: dict[str, Path], manifest: str) -> None:
    document = json.loads((rendered[manifest] / "outputs.json").read_text(encoding="utf-8"))
    config.validate_against_schema(document, "outputs.schema.json")


def test_all_three_files_exist(rendered: dict[str, Path]) -> None:
    for directory in rendered.values():
        for name in GENERATED_FILES:
            assert (directory / name).is_file(), f"{directory / name} missing"


def test_unknown_field_is_rejected_recursively(alpha: dict[str, Any]) -> None:
    document = json.loads(json.dumps(alpha))
    document["database"]["roles"]["surprise"] = "apg_x"
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(document, "outputs.schema.json")


def test_placeholder_digest_is_rejected(alpha: dict[str, Any]) -> None:
    """The runbook's angle-bracket examples are documentation, not values."""
    document = json.loads(json.dumps(alpha))
    document["inputs"]["project_sha256"] = "<computed SHA-256>"
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(document, "outputs.schema.json")


# ---------------------------------------------------------------------------
# Endpoint honesty (runbook §4.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ["pooled", "direct"])
def test_endpoints_are_unavailable_not_faked(alpha: dict[str, Any], endpoint: str) -> None:
    record = alpha["database"][endpoint]
    assert record["status"] == "unavailable"
    assert record["available_from_session"] == 4
    assert record["host"] is None
    assert record["port"] is None
    assert record["url"] is None
    assert record["password_secret_ref"] is None


def test_unavailable_endpoint_may_not_carry_a_url(alpha: dict[str, Any]) -> None:
    document = json.loads(json.dumps(alpha))
    document["database"]["pooled"]["url"] = "postgres://host:5432/db"
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(document, "outputs.schema.json")


def test_no_angle_bracket_placeholder_survives(rendered: dict[str, Path]) -> None:
    for directory in rendered.values():
        for name in GENERATED_FILES:
            text = (directory / name).read_text(encoding="utf-8")
            assert "<" not in text, f"{name} contains a documentation placeholder"


# ---------------------------------------------------------------------------
# Secret policy (runbook §4.4)
# ---------------------------------------------------------------------------


def test_rendered_output_carries_no_secret(alpha: dict[str, Any]) -> None:
    rendering.assert_output_is_secret_free(alpha)


def test_credential_bearing_url_is_rejected() -> None:
    with pytest.raises(rendering.RenderError, match="credential-bearing URL"):
        rendering.assert_output_is_secret_free({"url": "postgres://user:pw@host:5432/db"})


def test_presigned_url_is_rejected() -> None:
    with pytest.raises(rendering.RenderError, match="presigned URL"):
        rendering.assert_output_is_secret_free(
            {"link": "https://r2.example/object?X-Amz-Signature=deadbeef"}
        )


def test_secret_bearing_key_is_rejected() -> None:
    with pytest.raises(rendering.RenderError, match="secret-bearing key"):
        rendering.assert_output_is_secret_free({"database": {"password": "x"}})


def test_secret_ref_must_be_null_or_a_reference() -> None:
    rendering.assert_output_is_secret_free({"password_secret_ref": None})
    rendering.assert_output_is_secret_free({"password_secret_ref": "agentic-postgres/alpha/db"})
    with pytest.raises(rendering.RenderError, match="validated reference string"):
        rendering.assert_output_is_secret_free({"password_secret_ref": "hunter2!!"})


# ---------------------------------------------------------------------------
# File modes (runbook §4.2, §9 check 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", GENERATED_FILES)
def test_generated_files_are_owner_only(rendered: dict[str, Path], name: str) -> None:
    """Asserted with Python's stat module, never GNU `stat -c`."""
    for directory in rendered.values():
        mode = stat.S_IMODE(os.stat(directory / name).st_mode)
        assert mode == 0o600, f"{directory / name} is {mode:o}, expected 600"


def test_generated_files_are_not_symlinks(rendered: dict[str, Path]) -> None:
    for directory in rendered.values():
        for name in GENERATED_FILES:
            assert not (directory / name).is_symlink()


# ---------------------------------------------------------------------------
# Input digests
# ---------------------------------------------------------------------------


def test_input_digests_are_real_and_correct(alpha: dict[str, Any]) -> None:
    expected = {
        "project_sha256": REPO_ROOT / "project.example.yaml",
        "capabilities_sha256": REPO_ROOT / "capabilities.example.yaml",
        "versions_lock_sha256": REPO_ROOT / "versions.env",
        "source_specification_sha256": REPO_ROOT / "docs" / "source-specification.md",
    }
    for field, path in expected.items():
        assert alpha["inputs"][field] == sha256(path.read_bytes()).hexdigest(), field


def test_every_generated_file_records_the_same_inputs(rendered: dict[str, Path]) -> None:
    """Runbook §4.1: an incomplete published set must be detectable.

    The set became five in Session 2 (ADR 0012) when ``secrets.required_names``
    started reaching rendered output. The count is asserted against the named
    set rather than a bare number, so adding a digest without deciding to is a
    failure rather than an arithmetic update.
    """
    expected = {
        "project_sha256",
        "capabilities_sha256",
        "secrets_contract_sha256",
        "versions_lock_sha256",
        "source_specification_sha256",
    }
    for directory in rendered.values():
        document = json.loads((directory / "outputs.json").read_text(encoding="utf-8"))
        assert set(document["inputs"]) == expected
        assert all(len(value) == 64 for value in document["inputs"].values())


def test_every_render_input_is_digested(rendered: dict[str, Path]) -> None:
    """Guard the guard: a digest block that omits a real input proves nothing.

    ``secrets.required_names`` is derived from ``secrets.required.yaml``. If that
    file were not in ``inputs``, two renders could legitimately differ with
    nothing in the document explaining why -- which is the exact failure the
    block exists to expose.
    """
    document = json.loads((rendered["project.example.yaml"] / "outputs.json").read_text("utf-8"))
    assert (
        document["inputs"]["secrets_contract_sha256"]
        == sha256((REPO_ROOT / "secrets.required.yaml").read_bytes()).hexdigest()
    )
    assert document["secrets"]["required_names"] == ["session2_sentinel"]


# ---------------------------------------------------------------------------
# Determinism (runbook §3.7 rules 10-11)
# ---------------------------------------------------------------------------


def test_repeated_render_is_byte_identical(rendered: dict[str, Path]) -> None:
    directory = rendered["project.example.yaml"]
    before = {name: (directory / name).read_bytes() for name in GENERATED_FILES}

    again = rendering.render_project(
        REPO_ROOT / "project.example.yaml", REPO_ROOT / "capabilities.example.yaml"
    )
    after = {name: (again / name).read_bytes() for name in GENERATED_FILES}

    for name in GENERATED_FILES:
        assert before[name] == after[name], f"{name} is not byte-stable across renders"


def test_render_is_byte_identical_across_processes() -> None:
    """PYTHONHASHSEED must not reach rendered bytes."""
    outputs = REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json"

    digests = []
    for seed in ("0", "1"):
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "render-config.py"),
                "--project",
                str(REPO_ROOT / "project.example.yaml"),
                "--capabilities",
                str(REPO_ROOT / "capabilities.example.yaml"),
                "--render",
            ],
            capture_output=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        digests.append(sha256(outputs.read_bytes()).hexdigest())

    assert digests[0] == digests[1]


def test_output_bytes_are_canonical(rendered: dict[str, Path]) -> None:
    raw = (rendered["project.example.yaml"] / "outputs.json").read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert raw == naming.canonical_json(json.loads(raw.decode("utf-8")))


def test_no_timestamp_reaches_rendered_output(rendered: dict[str, Path]) -> None:
    """Plan decision U: the spec asks for one, determinism forbids it."""
    for directory in rendered.values():
        document = json.loads((directory / "outputs.json").read_text(encoding="utf-8"))

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    assert not key.endswith(("_at", "_time", "timestamp")), key
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(document)


# ---------------------------------------------------------------------------
# compose.env (plan decision M)
# ---------------------------------------------------------------------------


def test_compose_env_defines_exactly_the_expected_keys(rendered: dict[str, Path]) -> None:
    text = (rendered["project.example.yaml"] / "compose.env").read_text(encoding="utf-8")
    keys = {
        line.split("=", 1)[0] for line in text.splitlines() if line and not line.startswith("#")
    }
    assert keys == set(rendering.COMPOSE_ENV_KEYS)


def test_compose_env_carries_no_host_derived_value(rendered: dict[str, Path]) -> None:
    """The boundary ADR 0013 draws, asserted rather than described.

    Every key here comes from the project manifest. A value from `host.yaml` --
    the ACME resolver name, the middleware chain -- would make this rendered
    file depend on which machine produced it, and `host.yaml` is not one of the
    five digested inputs. Those values live in the root-owned runtime env file
    instead, passed as a third `--env-file` in `--runtime` mode only.
    """
    host_derived = {
        "ACME_RESOLVER_NAME",
        "BASELINE_MIDDLEWARE_CHAIN",
        "ACME_EMAIL",
        "CONTROL_NETWORK_NAME",
        "EGRESS_NETWORK_NAME",
        "HTTP_ENTRYPOINT",
        "HTTPS_ENTRYPOINT",
    }
    text = (rendered["project.example.yaml"] / "compose.env").read_text(encoding="utf-8")
    keys = {
        line.split("=", 1)[0] for line in text.splitlines() if line and not line.startswith("#")
    }
    assert not keys & host_derived, (
        f"host-derived keys reached a rendered file: {keys & host_derived}"
    )


def test_compose_env_key_order_is_stable(rendered: dict[str, Path]) -> None:
    """Determinism covers ordering, not just membership."""
    text = (rendered["project.example.yaml"] / "compose.env").read_text(encoding="utf-8")
    keys = [
        line.split("=", 1)[0] for line in text.splitlines() if line and not line.startswith("#")
    ]
    assert keys == list(rendering.COMPOSE_ENV_KEYS)


def test_compose_env_is_disjoint_from_the_version_lock(rendered: dict[str, Path]) -> None:
    """Runbook §7.2: the two env files must not be able to override each other."""

    def keys_of(path: Path) -> set[str]:
        return {
            line.split("=", 1)[0]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        }

    generated = keys_of(rendered["project.example.yaml"] / "compose.env")
    locked = keys_of(REPO_ROOT / "versions.env")
    assert not generated & locked, f"overlapping variables: {sorted(generated & locked)}"


def test_compose_env_matches_outputs(rendered: dict[str, Path], alpha: dict[str, Any]) -> None:
    text = (rendered["project.example.yaml"] / "compose.env").read_text(encoding="utf-8")
    values = dict(
        line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#")
    )
    assert values["COMPOSE_PROJECT_NAME"] == alpha["compose"]["project_name"]
    assert values["EDGE_NETWORK_NAME"] == alpha["compose"]["networks"]["edge"]
    assert values["INTERNAL_NETWORK_NAME"] == alpha["compose"]["networks"]["internal"]
    assert values["POSTGRES_VOLUME_NAME"] == alpha["compose"]["volumes"]["postgres"]


# ---------------------------------------------------------------------------
# Miscellaneous contract
# ---------------------------------------------------------------------------


def test_template_version_comes_from_the_version_file(alpha: dict[str, Any]) -> None:
    """Plan decision G: VERSION is the single source."""
    assert alpha["template_version"] == template_version()
    assert alpha["template_version"] == (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_capabilities_default_to_none_enabled(alpha: dict[str, Any]) -> None:
    assert alpha["capabilities"]["enabled"] == []


def test_all_thirteen_roles_are_present(alpha: dict[str, Any]) -> None:
    assert set(alpha["database"]["roles"]) == set(naming.ROLE_SUFFIXES)
    for name in alpha["database"]["roles"].values():
        assert len(name.encode("utf-8")) <= 63


# ---------------------------------------------------------------------------
# A required interpolation must not name a value that renders empty (D178)
# ---------------------------------------------------------------------------

#: `${VAR:?err}` in Compose fails when the variable is unset **or empty**;
#: `${VAR?err}` fails only when it is unset. Measured against Compose 29.5.2
#: with both spellings against both inputs, because the difference is one
#: character and the failure it produces names neither.
STRICT_INTERPOLATION = re.compile(r"\$\{([A-Z0-9_]+):\?")

#: The lax half of the same pair. Matched with a negative lookbehind on the
#: colon so `${VAR:?x}` is not counted twice.
LAX_INTERPOLATION = re.compile(r"\$\{([A-Z0-9_]+)\?")


def render_without_a_rest_service(tmp_path: Path) -> dict[str, str]:
    """Render the case D150 says must work: a manifest with no `api.rest`.

    Returns the parsed `compose.env`. Rendered through `render_project` rather
    than by calling `build_compose_env` directly, so what is measured is the
    file a deploy actually stages.

    **The published directory is removed afterwards, and that is not tidiness.**
    ``render_project`` publishes to ``.generated/<key>`` derived from the
    manifest, not to wherever the manifest was written — so ``tmp_path``
    isolates the input and nothing isolates the output. The Session 1 gate
    compares every rendered project in ``.generated/`` pairwise for identity
    collisions, and this fixture's project shares the example's storage bucket
    and backup stanza. Left behind, it fails the gate for anyone who runs the
    suite first, which is exactly what it did on the run that introduced it.
    """
    import shutil

    from agentic_postgres import rendering

    manifest = yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))
    manifest["api"].pop("rest", None)
    manifest["project"]["slug"] = "norest"
    path = tmp_path / "project.norest.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    # `validate_compose=False`: this test is about what the model *would* do
    # with these values, and the validator needs a Docker daemon the offline
    # gate does not have. The comparison below is what stands in for it, and it
    # is stricter — it checks every variable rather than the one that happened
    # to be reached first.
    directory = rendering.render_project(
        path, REPO_ROOT / "capabilities.example.yaml", validate_compose=False
    )
    try:
        values: dict[str, str] = {}
        for line in (directory / "compose.env").read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip():
                values[name.strip()] = value
        return values
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_no_required_interpolation_names_a_value_that_renders_empty(
    tmp_path: Path, code_only
) -> None:
    """D178, and the first defect the live path produced.

    `project.alpha.yaml` declares no `api.rest`, so `allowed_cors_origins`
    defaulted to `[]`, `",".join([])` rendered `""`, and
    `${POSTGREST_CORS_ORIGINS:?required}` refused it — the deploy failed at step
    1 having never touched the host. The renderer's own comment asserted the
    opposite: that emitting an empty string satisfies a required interpolation.

    Nothing caught it because every other test renders `project.example.yaml`,
    which names an origin, so the empty case was never rendered.

    Goes red if: a `:?` interpolation is added for a variable that can render
    empty, or a variable that can render empty gains a `:?` reference. Both
    directions matter — the second is how this returns, by someone tightening a
    spelling that looks too lax.

    Derived rather than listed: the empty set comes from an actual render and
    the strict set from the model's own text, so neither side is a copy of the
    other that could agree while both are wrong.
    """
    values = render_without_a_rest_service(tmp_path)
    empty = {name for name, value in values.items() if value == ""}
    assert empty, (
        "no variable rendered empty for a project with no REST service, so this "
        "test compared two empty sets and proved nothing"
    )

    # Comments stripped: the explanation of why one variable takes the lax
    # spelling contains both spellings as examples, and scanning raw text counts
    # them as references (`code_only`'s docstring records four prior instances).
    text = code_only(MODEL.read_text(encoding="utf-8"))
    strict = set(STRICT_INTERPOLATION.findall(text))
    lax = set(LAX_INTERPOLATION.findall(text))
    assert strict, "no `${VAR:?...}` interpolation found in the model; the regex is wrong"
    assert not (strict & lax), "a variable is referenced both ways; the regexes overlap"

    # A variable that can render empty must use the form that tolerates empty.
    # This is the direction D178 failed in.
    collisions = sorted(empty & strict)
    assert not collisions, (
        f"{collisions} render empty for a project with no REST service and are "
        "referenced as `${VAR:?required}`, which Compose refuses for an empty "
        "value as well as an unset one. Use `${VAR?required}` for these"
    )

    # And the converse, which the old spelling rule could not express: the lax
    # form is only for variables that genuinely need it. Without this half, every
    # reference could be relaxed to `?required` and this test would still pass —
    # which would put `DEP-ISO-002`'s empty-resource-name hazard back.
    unjustified = sorted(lax - empty)
    assert not unjustified, (
        f"{unjustified} are referenced as `${{VAR?required}}` but never render empty, "
        "so nothing needs the lax form for them. `${VAR:?required}` is stricter and "
        "is what a value that is never legitimately empty should carry (ADR 0062)"
    )


# ---------------------------------------------------------------------------
# Statement timeouts (ADR 0067, D197)
# ---------------------------------------------------------------------------


def declared_timeouts(manifest: str) -> dict[str, str]:
    """What the manifest asks for, read from the manifest rather than written here."""
    document = yaml.safe_load((REPO_ROOT / manifest).read_text(encoding="utf-8"))
    return dict(document["api"]["rest"]["statement_timeouts"])


@pytest.mark.parametrize("manifest", ["project.example.yaml", "project.second.example.yaml"])
def test_every_timeout_the_manifest_declares_reaches_the_document(
    rendered: dict[str, Path], manifest: str
) -> None:
    """The assertion D197 needed and nobody had written.

    `api.rest.statement_timeouts` has existed since Run 1. `project.schema.json`
    declared it, `config._validate_statement_timeouts` refused a bad one, and
    the render dropped every value on the floor -- so the bootstrap plane, which
    reads only this document, set one hard-coded timeout on one role and none of
    the manifest's ever applied. Validation proves a manifest is well formed. It
    never proves anything consumes it.

    Read from the manifest, not from a list here: a copy of the manifest's
    values in this file would agree with itself after the manifest changed.
    """
    document = json.loads((rendered[manifest] / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    applied = document["database"]["statement_timeouts"]

    declared = declared_timeouts(manifest)
    assert declared, f"{manifest} declares no statement_timeouts; this test proved nothing"
    for suffix, timeout in declared.items():
        assert roles[suffix] in applied, (
            f"{manifest} declares statement_timeouts.{suffix} = {timeout} and the rendered "
            f"document names no timeout for {roles[suffix]}. A declared timeout that reaches "
            "no document reaches no role (D197)"
        )
        assert applied[roles[suffix]] == timeout


@pytest.mark.parametrize("manifest", ["project.example.yaml", "project.second.example.yaml"])
def test_the_timeouts_are_keyed_by_derived_role_name(
    rendered: dict[str, Path], manifest: str
) -> None:
    """Suffix or name is the whole difference between one authority and two.

    A document keyed by suffix would make the bootstrap plane derive the role
    name, which ADR 0002 allows exactly one place to do. It would also read
    almost identically in a diff.
    """
    document = json.loads((rendered[manifest] / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    applied = document["database"]["statement_timeouts"]

    assert applied, "the document names no statement timeouts at all"
    unknown = sorted(set(applied) - set(roles.values()))
    assert not unknown, f"statement_timeouts names {unknown}, which database.roles does not"
    suffixes = sorted(set(applied) & set(roles))
    assert not suffixes, (
        f"statement_timeouts is keyed by role suffix {suffixes} rather than by the derived "
        "role name, so a consumer would have to derive the name a second time"
    )


@pytest.mark.parametrize("manifest", ["project.example.yaml", "project.second.example.yaml"])
def test_the_runtime_role_is_bounded_even_though_no_manifest_names_it(
    rendered: dict[str, Path], manifest: str
) -> None:
    """The platform's own floor, and the reason it travels as data.

    Neither example manifest names `app_runtime`, and it must still be bounded:
    an application holding a server connection in a long statement holds it out
    of the pool, which under transaction pooling is the whole pool's problem.
    Before ADR 0067 this was a literal in `bin/postgres-bootstrap.py`, invisible
    to anyone reading the document it was supposed to describe.
    """
    document = json.loads((rendered[manifest] / "outputs.json").read_text(encoding="utf-8"))
    runtime = document["database"]["roles"]["app_runtime"]
    assert "app_runtime" not in declared_timeouts(manifest), (
        f"{manifest} now names app_runtime itself, so this no longer tests the default"
    )
    assert (
        document["database"]["statement_timeouts"][runtime]
        == rendering.DEFAULT_APP_RUNTIME_STATEMENT_TIMEOUT
    )


def test_a_manifest_entry_overrides_the_platform_default() -> None:
    """The default is a floor for silence, not a second answer to the question.

    Called directly rather than through a render: no committed manifest names
    `app_runtime`, and adding one to an example manifest to test this would
    change what every other test in this file renders.
    """
    roles = {"app_runtime": "apg_x_app_runtime", "anon": "apg_x_anon"}
    resolved = rendering.resolve_statement_timeouts(
        {"api": {"rest": {"statement_timeouts": {"app_runtime": "10s"}}}}, roles
    )
    assert resolved == {"apg_x_app_runtime": "10s"}


def test_a_project_with_no_rest_service_still_bounds_the_runtime_role() -> None:
    """Three ways a manifest can be silent, and none of them may drop the floor.

    `api` absent, `api.rest` absent, and `statement_timeouts` absent are three
    distinct paths through the resolver, and the second is the one D178 showed
    is real: a project with no REST service renders, and it still has an
    application holding connections.
    """
    roles = {"app_runtime": "apg_x_app_runtime"}
    floor = {"apg_x_app_runtime": rendering.DEFAULT_APP_RUNTIME_STATEMENT_TIMEOUT}
    assert rendering.resolve_statement_timeouts({}, roles) == floor
    assert rendering.resolve_statement_timeouts({"api": None}, roles) == floor
    assert rendering.resolve_statement_timeouts({"api": {"rest": None}}, roles) == floor
    assert rendering.resolve_statement_timeouts({"api": {"rest": {}}}, roles) == floor


def test_a_timeout_for_a_suffix_the_platform_does_not_derive_fails_the_render() -> None:
    """`config` refuses this first; the resolver must not paper over it if it ever stops.

    A `KeyError` here is the right failure. Silently skipping an unrecognised
    suffix would put back exactly the silence ADR 0067 exists to remove -- a
    timeout declared, accepted, and applied to nothing.
    """
    with pytest.raises(KeyError):
        rendering.resolve_statement_timeouts(
            {"api": {"rest": {"statement_timeouts": {"no_such_role": "5s"}}}},
            {"app_runtime": "apg_x_app_runtime"},
        )


# ---------------------------------------------------------------------------
# The API's connection commitment (ADR 0070, D161)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("manifest", ["project.example.yaml", "project.second.example.yaml"])
def test_the_published_budget_is_the_one_the_manifest_was_checked_against(
    rendered: dict[str, Path], manifest: str
) -> None:
    """One answer, from `config`, not a second sum written in the renderer.

    The manifest-side budget check reasons about
    `config.postgrest_connection_budget`, and the bootstrap plane divides the
    live budget using whatever this publishes. A renderer that computed its own
    sum would agree today and diverge on the day one of them moved -- which is
    the only day it would matter. ADR 0002's rule applied to a number.
    """
    document = yaml.safe_load((REPO_ROOT / manifest).read_text(encoding="utf-8"))
    rest = (document.get("api") or {}).get("rest") or {}
    expected = config.postgrest_connection_budget(rest)

    published = json.loads((rendered[manifest] / "outputs.json").read_text(encoding="utf-8"))
    assert published["database"]["api_connection_budget"] == expected


@pytest.mark.parametrize("manifest", ["project.example.yaml", "project.second.example.yaml"])
def test_the_published_budget_leaves_room_for_the_application(
    rendered: dict[str, Path], manifest: str
) -> None:
    """The document that publishes a commitment also publishes the ceiling it fits in.

    A commitment at or above `max_connections` is one the bootstrap plane could
    never divide, and refusing it here is cheaper than discovering it on a host.
    """
    published = json.loads((rendered[manifest] / "outputs.json").read_text(encoding="utf-8"))
    budget = published["database"]["api_connection_budget"]
    maximum = published["database"]["budget"]["max_connections"]
    assert 0 < budget < maximum


def test_a_project_with_no_rest_service_still_publishes_a_commitment() -> None:
    """The reservations are what a service *would* take.

    A value that depended on whether a service happened to be enabled would make
    the bootstrap's division of the budget depend on it too -- and a project that
    enables REST later would silently change every other role's ceiling.
    """
    assert rendering.resolve_api_connection_budget({}) == config.postgrest_connection_budget({})
    assert rendering.resolve_api_connection_budget({"api": None}) > 0
    assert rendering.resolve_api_connection_budget({"api": {"rest": None}}) > 0

"""Compute profiles (Session 38, ADR 0258, D2156, D2157).

A profile is a named set of values a manifest can already carry; `config.apply_compute_profile`
writes it in inside `load_project_manifest`, before every semantic rule, so the validators that
bound those values are the existing ones. `standard` is today's defaults exactly.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, capacity, compute_profiles, config, rendering

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"
EXAMPLE = REPO_ROOT / "project.example.yaml"


def _manifest(tmp_path: Path, document: dict[str, Any], name: str = "project.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _example() -> dict[str, Any]:
    """The example manifest with every member a profile OWNS removed.

    The example sets `api.rest.pool_size` and `storage.pool_size` itself, so naming a
    profile on it is refused by name (the rule
    `test_a_profile_and_an_owned_member_are_refused_together` proves). Every
    comparison here starts from the manifest a profile can apply to; both sides of
    the byte-identity check below start from it, so the comparison stays one of like
    with like."""
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for member in compute_profiles.owned_members():
        *parents, leaf = member.split(".")
        node: Any = document
        for part in parents:
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, dict):
            node.pop(leaf, None)
    return document


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    generated = tmp_path / "generated"
    monkeypatch.setattr(rendering, "GENERATED_ROOT", generated)
    monkeypatch.setattr(rendering, "STAGING_ROOT", generated / ".staging")
    monkeypatch.setattr(rendering, "LOCK_ROOT", generated / ".locks")
    return generated


def _render(manifest: Path) -> dict[str, bytes]:
    directory = rendering.render_project(manifest, CAPABILITIES, validate_compose=False)
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir()) if path.is_file()}


def _compose_env(files: dict[str, bytes]) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in files["compose.env"].decode("utf-8").splitlines()
        if "=" in line
    )


def test_standard_is_todays_defaults(tmp_path: Path, sandbox: Path) -> None:
    """Every value `standard` sets equals the default it replaces, and a manifest naming
    `compute: {profile: standard}` renders byte-identically to the same manifest naming none.
    Control: `small` renders differently."""
    standard = compute_profiles.PROFILES["standard"]
    assert standard["database"] == {
        key: config.DATABASE_BUDGET_DEFAULTS[key] for key in standard["database"]
    }
    assert set(standard["database"]) == set(config.DATABASE_BUDGET_DEFAULTS)
    assert standard["api"]["app"] == {
        key: config.API_APP_DEFAULTS[key] for key in standard["api"]["app"]
    }
    assert standard["api"]["rest"]["pool_size"] == config.API_REST_DEFAULTS["pool_size"]
    assert standard["storage"] == {key: config.STORAGE_DEFAULTS[key] for key in standard["storage"]}
    assert standard["resources"] == {}

    # Same profile set, every profile: one shape, so `owned_members` is the same for all three.
    shapes = {
        name: sorted(path for path, _ in compute_profiles.values(name))
        for name in compute_profiles.PROFILE_NAMES
    }
    assert len({tuple(shape) for shape in shapes.values()}) == 1, shapes

    plain = _render(_manifest(tmp_path, _example(), "plain.yaml"))
    named = _example()
    named["compute"] = {"profile": "standard"}
    rendered = _render(_manifest(tmp_path, named, "named.yaml"))
    # Every rendered file byte for byte -- except that `outputs.json` records the
    # digest of the manifest's own BYTES (`inputs.project_sha256`), which naming a
    # profile changes by definition; with that one leaf set aside the documents are
    # equal too, `compute.profile: standard` on both (absent reads as standard).
    assert {k: v for k, v in rendered.items() if k != "outputs.json"} == {
        k: v for k, v in plain.items() if k != "outputs.json"
    }
    named_doc, plain_doc = (json.loads(f["outputs.json"]) for f in (rendered, plain))
    assert named_doc["inputs"].pop("project_sha256") != plain_doc["inputs"].pop("project_sha256")
    assert named_doc == plain_doc

    small = _example()
    small["compute"] = {"profile": "small"}
    assert _render(_manifest(tmp_path, small, "small.yaml")) != plain


@pytest.mark.parametrize("profile", ["small", "standard", "large"])
def test_every_profile_passes_the_budget_validators(tmp_path: Path, profile: str) -> None:
    """Each profile, applied to the example manifest, loads through `load_project_manifest`
    -- the memory relation, the auth floor and the connection budget all accept it -- and the
    loaded manifest carries the profile's values. ADR 0258's charges are read back."""
    document = _example()
    # Every block a profile writes into, present -- a slot manifest's shape. The example
    # declares no `api.app`, and a profile writes only into declared blocks.
    document["api"]["app"] = {"enabled": True}
    document["compute"] = {"profile": profile}
    loaded = config.load_project_manifest(_manifest(tmp_path, document))
    for path, value in compute_profiles.values(profile):
        node: Any = loaded
        for part in path:
            node = node[part]
        assert node == value, (profile, path)
    charge = config.database_budget(loaded["database"])["unreclaimable_mb"]
    assert charge == {"small": 192, "standard": 304, "large": 840}[profile]


def test_a_profile_and_an_owned_member_are_refused_together(tmp_path: Path) -> None:
    """Two sources for one number are refused BY NAME. Control: a member the profile does not
    own (`database.pool_size`) beside a profile loads."""
    document = _example()
    document["compute"] = {"profile": "small"}
    document["database"]["shared_buffers_mb"] = 96
    with pytest.raises(config.ManifestError, match=r"database\.shared_buffers_mb"):
        config.load_project_manifest(_manifest(tmp_path, document))

    allowed = _example()
    allowed["compute"] = {"profile": "small"}
    allowed["database"]["pool_size"] = 18
    assert (
        config.load_project_manifest(_manifest(tmp_path, allowed, "ok.yaml"))["database"][
            "pool_size"
        ]
        == 18
    )


def test_compute_is_refused_below_schema_ten(tmp_path: Path) -> None:
    """`compute` is forbidden below 10 (the version 9 gate's shape). Control: the same manifest
    at 10 loads, and one at 9 without `compute` reads `standard`."""
    document = _example()
    document["schema_version"] = 9
    document["compute"] = {"profile": "small"}
    with pytest.raises(config.ManifestError):
        config.load_project_manifest(_manifest(tmp_path, document))

    document["schema_version"] = 10
    assert (
        config.compute_profile(
            config.load_project_manifest(_manifest(tmp_path, document, "ten.yaml"))
        )
        == "small"
    )

    older = _example()
    older["schema_version"] = 9
    assert (
        config.compute_profile(
            config.load_project_manifest(_manifest(tmp_path, older, "nine.yaml"))
        )
        == "standard"
    )
    assert config.PROJECT_COMPUTE_FROM == 10


def test_pids_and_cpus_come_from_the_profile(tmp_path: Path, sandbox: Path) -> None:
    """`small` gives postgres one core and moves nothing else; `standard` renders the defaults.
    Read from the rendered compose.env, which is what Compose interpolates."""
    small = _example()
    small["compute"] = {"profile": "small"}
    small_env = _compose_env(_render(_manifest(tmp_path, small, "small.yaml")))
    plain_env = _compose_env(_render(_manifest(tmp_path, _example(), "plain.yaml")))

    assert small_env["POSTGRES_CPUS"] == "1.0"
    assert plain_env["POSTGRES_CPUS"] == str(config.SERVICE_RESOURCE_DEFAULTS["postgres"]["cpus"])
    moved = sorted(
        key
        for key in small_env
        if (key.endswith("_CPUS") or key.endswith("_PIDS_LIMIT"))
        and small_env[key] != plain_env[key]
    )
    assert moved == ["POSTGRES_CPUS"], moved


def test_the_resize_message_names_only_a_measured_window() -> None:
    """D2157: while no envelope row measures the resize restart, the constant is None and the
    message says the window is unmeasured -- it carries no number. Once a row exists, Run 13
    sets the constant from it and this holds them equal."""
    rows = [m for m in capacity.ENVELOPE if m.subject.lower().startswith("resize")]
    if not rows:
        assert compute_profiles.RESIZE_WINDOW_SECONDS is None
        message = compute_profiles.resize_message()
        assert message == compute_profiles.UNMEASURED_RESIZE_MESSAGE
        assert not any(character.isdigit() for character in message)
    else:
        assert compute_profiles.RESIZE_WINDOW_SECONDS is not None
        assert str(compute_profiles.RESIZE_WINDOW_SECONDS) in rows[0].value
    # Control: given a window, the message carries it.
    assert "42 seconds" in compute_profiles.resize_message(42)
    assert copy.deepcopy(compute_profiles.PROFILE_NAMES) == ("small", "standard", "large")

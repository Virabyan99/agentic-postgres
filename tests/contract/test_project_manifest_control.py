"""Project manifest schema 9: the control-plane facility (ADR 0251, D2044).

`control: {enabled}` is optional at 9 and forbidden below it -- the connectors
facility's shape -- and `config.control_enabled` is its one reader, for a
manifest and a rendered or deployed document alike. A manifest that enables it
must name its migration set, because the control plane's tables are that set.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config

pytestmark = [pytest.mark.contract, pytest.mark.p0]


@pytest.fixture
def base() -> dict[str, Any]:
    """The example manifest at the newest version, WITHOUT the facility."""
    return yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))


def _load(tmp_path: Path, document: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return config.load_project_manifest(path)


def _control(document: dict[str, Any], enabled: bool = True) -> dict[str, Any]:
    document = copy.deepcopy(document)
    document["control"] = {"enabled": enabled}
    return document


def test_schema_nine_admits_control_with_and_without_it(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """Optional at 9: the base loads without the block and reads off; with it,
    either value loads and the reader returns exactly that value."""
    # The base is version 10 since Session 38 (ADR 0258); control arrived at 9.
    assert base["schema_version"] == 10 and config.PROJECT_CONTROL_FROM == 9
    assert 9 in config.SUPPORTED_PROJECT_SCHEMA_VERSIONS
    assert "control" not in base
    assert config.control_enabled(_load(tmp_path, base)) is False
    assert config.control_enabled(_load(tmp_path, _control(base, True))) is True
    assert config.control_enabled(_load(tmp_path, _control(base, False))) is False


def test_control_is_forbidden_below_nine(tmp_path: Path, base: dict[str, Any]) -> None:
    """The version 9 gate. The control: the same downgrade WITHOUT the block
    loads, so the refusal is the gate's and not some other version-8 rule."""
    eight = _control(base)
    eight["schema_version"] = 8
    with pytest.raises(config.ManifestError, match="control"):
        _load(tmp_path, eight)

    plain = copy.deepcopy(base)
    plain["schema_version"] = 8
    assert _load(tmp_path, plain)["schema_version"] == 8


def test_the_block_takes_exactly_one_boolean(tmp_path: Path, base: dict[str, Any]) -> None:
    for wrong in ({}, {"enabled": "true"}, {"enabled": True, "extra": 1}):
        document = copy.deepcopy(base)
        document["control"] = wrong
        with pytest.raises(config.ManifestError):
            _load(tmp_path, document)


def test_control_without_a_migration_set_is_refused(tmp_path: Path, base: dict[str, Any]) -> None:
    """The control plane's tables are its set (ADR 0251): enabling the facility
    with no `migrations.set` is refused at the render, by name. The control: the
    same manifest with the facility OFF and no set loads."""
    # `mcp.capabilities` goes too: it requires a set of its own (ADR 0201), and
    # left in place it would refuse both arms for a reason that is not this one.
    without = _control(base)
    del without["migrations"]
    without["mcp"].pop("capabilities", None)
    with pytest.raises(config.ManifestError, match=r"control\.enabled is true"):
        _load(tmp_path, without)

    off = _control(base, False)
    del off["migrations"]
    off["mcp"].pop("capabilities", None)
    assert config.control_enabled(_load(tmp_path, off)) is False


def test_one_reader_decides_the_facility_for_a_manifest_and_a_document() -> None:
    """`control_enabled` reads `control.enabled` wherever it sits, and an absent
    block -- every manifest below 9, every document below outputs 20 -- reads off."""
    assert config.control_enabled({}) is False
    assert config.control_enabled({"control": None}) is False
    assert config.control_enabled({"control": {"enabled": False}}) is False
    assert config.control_enabled({"control": {"enabled": True}}) is True
    assert config.control_enabled({"schema_version": 20, "control": {"enabled": True}}) is True


def test_neither_example_is_the_control_plane() -> None:
    """Both shipped fixtures are version 9 WITHOUT the facility, so nothing they
    render moves but the version (and the route every project names)."""
    for name in ("project.example.yaml", "project.second.example.yaml"):
        document = config.load_project_manifest(REPO_ROOT / name)
        assert document["schema_version"] == 10, name
        assert config.control_enabled(document) is False, name

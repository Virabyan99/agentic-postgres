"""Strict YAML parsing (runbook §3.2).

Every case here is something default PyYAML accepts. The duplicate-key case is
the sharpest: ``yaml.safe_load`` silently keeps the last value, so a typo that
repeats a key becomes an invisible configuration change rather than an error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentic_postgres import config

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def write(tmp_path: Path, text: str, name: str = "manifest.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_document_parses(tmp_path: Path) -> None:
    path = write(tmp_path, "a: 1\nb:\n  c: two\n")
    assert config.load_manifest(path) == {"a": 1, "b": {"c": "two"}}


def test_duplicate_key_is_rejected(tmp_path: Path) -> None:
    text = "a: 1\na: 2\n"
    # Default behaviour, stated so the regression is unmistakable.
    assert yaml.safe_load(text) == {"a": 2}

    with pytest.raises(config.ManifestError, match="duplicate mapping key"):
        config.load_manifest(write(tmp_path, text))


def test_duplicate_key_is_rejected_at_depth(tmp_path: Path) -> None:
    path = write(tmp_path, "outer:\n  inner:\n    x: 1\n    x: 2\n")
    with pytest.raises(config.ManifestError, match="duplicate mapping key 'x'"):
        config.load_manifest(path)


def test_multiple_documents_are_rejected(tmp_path: Path) -> None:
    path = write(tmp_path, "a: 1\n---\nb: 2\n")
    with pytest.raises(config.ManifestError, match="exactly one YAML document"):
        config.load_manifest(path)


def test_single_document_with_leading_marker_is_accepted(tmp_path: Path) -> None:
    assert config.load_manifest(write(tmp_path, "---\na: 1\n")) == {"a": 1}


def test_merge_keys_are_rejected(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "base: &base\n  x: 1\nderived:\n  <<: *base\n  y: 2\n",
    )
    with pytest.raises(config.ManifestError, match="merge keys are not allowed"):
        config.load_manifest(path)


@pytest.mark.parametrize("key", ["1", "true", "null", "3.5"])
def test_non_string_keys_are_rejected(tmp_path: Path, key: str) -> None:
    path = write(tmp_path, f"{key}: value\n")
    with pytest.raises(config.ManifestError, match="mapping keys must be strings"):
        config.load_manifest(path)


def test_quoted_numeric_key_is_accepted(tmp_path: Path) -> None:
    assert config.load_manifest(write(tmp_path, '"1": value\n')) == {"1": "value"}


def test_unsafe_python_tag_is_rejected(tmp_path: Path) -> None:
    path = write(tmp_path, "value: !!python/object/apply:os.system ['echo pwned']\n")
    with pytest.raises(config.ManifestError):
        config.load_manifest(path)


def test_unknown_tag_is_rejected(tmp_path: Path) -> None:
    path = write(tmp_path, "value: !CustomTag data\n")
    with pytest.raises(config.ManifestError):
        config.load_manifest(path)


def test_oversized_input_is_rejected_before_parsing(tmp_path: Path) -> None:
    payload = "key: " + "a" * (config.MAX_MANIFEST_BYTES + 100) + "\n"
    path = write(tmp_path, payload)
    with pytest.raises(config.ManifestError, match=r"above the .* byte limit"):
        config.load_manifest(path)


def test_input_just_under_the_limit_is_accepted(tmp_path: Path) -> None:
    filler = "a" * (config.MAX_MANIFEST_BYTES - 20)
    path = write(tmp_path, f"key: {filler}\n")
    assert path.stat().st_size <= config.MAX_MANIFEST_BYTES
    assert config.load_manifest(path)["key"] == filler


def test_non_mapping_top_level_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(config.ManifestError, match="top level must be a mapping"):
        config.load_manifest(write(tmp_path, "- one\n- two\n"))


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(config.ManifestError, match="not a file"):
        config.load_manifest(tmp_path / "absent.yaml")


def test_symlinked_manifest_is_rejected(tmp_path: Path) -> None:
    real = write(tmp_path, "a: 1\n", name="real.yaml")
    link = tmp_path / "link.yaml"
    link.symlink_to(real)
    with pytest.raises(config.ManifestError, match="symlink"):
        config.load_manifest(link)

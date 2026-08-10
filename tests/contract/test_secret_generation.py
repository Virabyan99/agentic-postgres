"""The manifest that describes a generation of secret files.

The deployed ``outputs.json`` requires ``secrets.generation_manifest`` and
constrains its path with a pattern. Nothing wrote the file. A deployment would
have declared secrets ready and pointed at something that did not exist — and
because the field is a string, the output schema would have validated happily.

The rule this module exists to hold: **placement, never content.** No secret
value belongs here and no digest of one either. A digest would make the manifest
an oracle — anyone who could guess a value could confirm it against the file —
and §16 already refuses digests as a substitute for isolation. Proof that a
consumer received its own secret is the mount list plus a successful read by
that consumer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, secret_generation
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

SENTINEL = "s3cr3t-value-that-must-never-be-written"

CONTRACT_ENTRIES = [
    {
        "name": "session2_sentinel",
        "provider_key": "SESSION2_SENTINEL",
        "provider_path": "/runtime",
        "consumers": [
            {
                "plane": "compose",
                "service": "secret-check",
                "target_file": "session2_sentinel",
                "uid": 65532,
                "gid": 65532,
                "mode": "0400",
                "format": "raw",
            }
        ],
    }
]


@pytest.fixture
def manifest() -> dict:
    return secret_generation.build_manifest(
        project_key="alpha-dev", generation_id="k7f2p9qd", secrets=CONTRACT_ENTRIES
    )


def test_a_built_manifest_validates(manifest: dict) -> None:
    assert secret_generation.validate_manifest(manifest) == manifest
    assert manifest["secrets"][0]["consumers"][0]["uid"] == 65532


def test_the_recorded_path_matches_what_the_output_schema_demands() -> None:
    """The deployed document constrains this path with a pattern.

    Two places construct it — this module and the schema — so they are compared
    rather than trusted to stay in step.
    """
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text(encoding="utf-8"))
    pattern = schema["$defs"]["deployedDocument"]["properties"]["secrets"]["properties"][
        "generation_manifest"
    ]["pattern"]

    import re

    path = secret_generation.manifest_path("alpha-dev", "k7f2p9qd")
    assert re.match(pattern, str(path)), f"{path} does not match the deployed schema's {pattern}"


def test_no_provider_coordinate_reaches_the_manifest(manifest: dict) -> None:
    """Where a value came from is bootstrap state's business.

    Copying the provider layout into a file that sits beside the values widens
    what reading one directory tells an attacker.
    """
    rendered = json.dumps(manifest)
    assert "SESSION2_SENTINEL" not in rendered
    assert "/runtime" not in rendered


def test_a_secret_value_cannot_be_smuggled_into_the_manifest() -> None:
    """Guard the guard: the sensitive-key scan actually runs on this document."""
    with pytest.raises(ManifestError):
        secret_generation.validate_manifest(
            {
                "schema_version": 1,
                "generation_id": "k7f2p9qd",
                "project_key": "alpha-dev",
                "materialized_at": "2026-08-05T00:00:00Z",
                "secrets": CONTRACT_ENTRIES,
                "password": SENTINEL,
            }
        )


@pytest.mark.parametrize("field", ["value", "sha256", "digest", "checksum"])
def test_a_content_field_on_a_contract_entry_never_reaches_the_manifest(field: str) -> None:
    """`build_manifest` copies five named fields and drops everything else.

    So a secret contract that grew a `sha256` key could not leak it here even by
    accident. Asserted on the output rather than by expecting a refusal: this
    function is not a validator of its input, it is a projection of it, and
    testing it as though it rejects would describe behaviour it does not have.
    """
    entries = [
        {
            "name": "session2_sentinel",
            "consumers": [
                {
                    "plane": "compose",
                    "service": "secret-check",
                    "target_file": "session2_sentinel",
                    "uid": 65532,
                    "gid": 65532,
                    "mode": "0400",
                    "format": "raw",
                    field: SENTINEL,
                }
            ],
        }
    ]
    manifest = secret_generation.build_manifest(
        project_key="alpha-dev", generation_id="k7f2p9qd", secrets=entries
    )
    rendered = json.dumps(manifest)
    assert field not in rendered
    assert SENTINEL not in rendered


@pytest.mark.parametrize("field", ["value", "sha256", "digest", "checksum"])
def test_a_hand_written_manifest_carrying_a_content_field_is_refused(field: str) -> None:
    """The other half: `additionalProperties: false` on the stored document.

    Dropping unknown fields on the way in protects against a contract that
    grows one. This protects against the file itself being edited, which is the
    case where a digest would actually sit next to the values it describes.
    """
    document = secret_generation.build_manifest(
        project_key="alpha-dev", generation_id="k7f2p9qd", secrets=CONTRACT_ENTRIES
    )
    document["secrets"][0]["consumers"][0][field] = SENTINEL
    with pytest.raises(ManifestError):
        secret_generation.validate_manifest(document)


def test_a_target_file_may_not_escape_the_generation_directory() -> None:
    entries = [
        {
            "name": "session2_sentinel",
            "consumers": [
                {
                    "plane": "compose",
                    "service": "secret-check",
                    "target_file": "../../../etc/cron.d/payload",
                    "uid": 0,
                    "gid": 0,
                    "mode": "0400",
                    "format": "raw",
                }
            ],
        }
    ]
    with pytest.raises(ManifestError):
        secret_generation.build_manifest(
            project_key="alpha-dev", generation_id="k7f2p9qd", secrets=entries
        )


def test_materialize_secrets_writes_the_manifest_before_the_rename(code_only) -> None:
    """It has to be part of the generation, not added to it afterwards."""
    source = (REPO_ROOT / "bin" / "materialize-secrets.py").read_text(encoding="utf-8")
    body = code_only(source)
    assert "write_manifest" in body, "materialize-secrets writes no generation manifest"
    assert body.index("write_manifest") < body.index("staging.rename(target)"), (
        "the manifest is written after the generation is renamed into place"
    )


def test_the_manifest_is_written_into_the_staging_directory() -> None:
    source = (REPO_ROOT / "bin" / "materialize-secrets.py").read_text(encoding="utf-8")
    assert 'staging / "manifest.json"' in source


def test_written_manifest_is_owner_read_only(tmp_path: Path, manifest: dict) -> None:
    path = tmp_path / "manifest.json"
    try:
        secret_generation.write_manifest(manifest, path)
    except PermissionError:
        pytest.skip("chown to root requires privilege this run does not have")
    assert path.stat().st_mode & 0o777 == 0o400, oct(path.stat().st_mode)

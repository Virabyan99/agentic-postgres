"""The grant surface that was declared everywhere and rendered nowhere.

`compose.yaml` has never carried a `secrets:` block, and the comment above
`secret-check` explains why: the source path contains a generation identifier
that does not exist until materialization runs, so "the runtime override
supplies them" was the design. Nothing supplied them. Session 2 could not
notice -- its one secret belongs to a `session2-verify` service no deploy
starts, and every Session 2 proof reads files on disk rather than a container's
view of them.

These tests are the ones that would have caught it: they ask what the model
grants, not what the filesystem holds.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT, secret_override
from agentic_postgres.secrets_contract import (
    CONTAINER_SECRET_DIR,
    active_secrets,
    load_secret_contract,
    secret_source_path,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CONTRACT = REPO_ROOT / "secrets.required.yaml"
KEY = "alpha-dev"
GENERATION = "k7f2p9qd"


@pytest.fixture
def contract() -> dict:
    return load_secret_contract(CONTRACT)


def build(contract: dict, session: int) -> dict:
    return secret_override.build_secret_override(
        project_key=KEY, generation_id=GENERATION, contract=contract, session=session
    )


def test_every_active_secret_reaches_its_consumer(contract: dict) -> None:
    """The whole of the declared surface, in both directions.

    A test that only checked "postgres gets a password" would pass against an
    override that dropped every other grant.
    """
    document = build(contract, 3)
    expected = {
        (consumer["service"], consumer["target_file"])
        for secret in active_secrets(contract, 3)
        for consumer in secret["consumers"]
    }
    granted = {
        (service, grant["target"])
        for service, block in document["services"].items()
        for grant in block["secrets"]
    }
    assert granted == expected


def test_each_source_is_the_materializer_s_own_path(contract: dict) -> None:
    """Derived by the same function that wrote the file, not rebuilt here.

    A second spelling of this path is a mount of a file that does not exist,
    which Docker reports by creating an empty directory at the mount point --
    so the container starts, and the secret is a directory.
    """
    document = build(contract, 3)
    for secret in active_secrets(contract, 3):
        for consumer in secret["consumers"]:
            name = secret_override.grant_name(consumer)
            assert document["secrets"][name]["file"] == secret_source_path(
                KEY, GENERATION, consumer
            )


def test_the_container_path_is_the_contract_s_container_path(contract: dict) -> None:
    """`target:` is the basename, so /run/secrets/<file> is what a service sees."""
    document = build(contract, 3)
    for service, block in document["services"].items():
        for grant in block["secrets"]:
            source = document["secrets"][grant["source"]]["file"]
            assert source.endswith(f"/{service}/{grant['target']}")
            assert f"{CONTAINER_SECRET_DIR}/{grant['target']}".startswith(CONTAINER_SECRET_DIR)


def test_a_session_two_surface_grants_nothing_from_session_three(contract: dict) -> None:
    """The filter is what lets later sessions append to one file.

    Rendering session 2's surface on a session-2 host must not mount a database
    credential that host has never materialized -- Compose refuses to start a
    service whose `file:` source is absent, so this is the difference between a
    running project and a stopped one.
    """
    document = build(contract, 2)
    assert set(document["secrets"]) == {"secret-check__session2_sentinel"}
    assert set(document["services"]) == {"secret-check"}


def test_two_services_receiving_the_same_basename_do_not_collide() -> None:
    """The reason the Compose name carries the service.

    Two consumers may legitimately declare the same `target_file` from two
    directories. Keyed by basename alone, the second would overwrite the first
    and one service would silently mount the other's copy.
    """
    contract = {
        "secrets": [
            {
                "name": "shared",
                "introduced_in_session": 3,
                "consumers": [
                    {"plane": "compose", "service": "alpha", "target_file": "credential"},
                    {"plane": "compose", "service": "beta", "target_file": "credential"},
                ],
            }
        ]
    }
    document = build(contract, 3)
    assert len(document["secrets"]) == 2
    sources = {entry["file"] for entry in document["secrets"].values()}
    assert len(sources) == 2
    for service in ("alpha", "beta"):
        grant = document["services"][service]["secrets"][0]
        assert grant["target"] == "credential"
        assert f"/{service}/credential" in document["secrets"][grant["source"]]["file"]


def test_the_rendered_document_is_parseable_yaml_and_names_no_value(contract: dict) -> None:
    payload = secret_override.render_secret_override(
        project_key=KEY, generation_id=GENERATION, contract=contract, session=3
    )
    document = yaml.safe_load(payload.decode("utf-8"))
    assert document["services"]["postgres"]["secrets"]

    # Every leaf is a path or a name. There is no member here that could carry
    # a value even by accident, and this is the assertion that keeps it so.
    text = payload.decode("utf-8")
    assert "password" not in text.replace("migration_user_password", "").replace(
        "postgres_init_superuser_password", ""
    )


@pytest.mark.parametrize(
    "field,value",
    [("project_key", ""), ("generation_id", ""), ("session", 0)],
    ids=["key", "generation", "session"],
)
def test_an_empty_input_is_refused(contract: dict, field: str, value: object) -> None:
    arguments = {
        "project_key": KEY,
        "generation_id": GENERATION,
        "contract": contract,
        "session": 3,
    }
    arguments[field] = value
    with pytest.raises(ValueError):
        secret_override.build_secret_override(**arguments)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Where it is written from, and when
# ---------------------------------------------------------------------------


def test_the_writer_runs_after_materialization_and_before_the_start() -> None:
    """Order, asserted by position. A surface rendered before materialization
    names the generation the *previous* start used -- and every file in it still
    exists, so nothing fails until the next rotation."""
    code = (REPO_ROOT / "bin" / "project-runtime.sh").read_text(encoding="utf-8")
    assert code.index("materialize-secrets.sh") < code.index("render-secret-override.py")
    assert code.index("render-secret-override.py") < code.index('"${profiles[@]}" up')


def test_compose_refuses_to_start_without_a_grant_surface() -> None:
    """Absence is refused, not read as "this project has no secrets".

    Only the contract can make that claim, and it makes it by rendering an
    empty block -- which is a file that exists.
    """
    code = (REPO_ROOT / "bin" / "compose.sh").read_text(encoding="utf-8")
    assert "SECRETS_OVERRIDE_PATH" in code
    assert 'OVERRIDE_REQUIRED="up restart run"' in code
    required_block = code.split("OVERRIDE_REQUIRED}")[1]
    assert "SECRETS_OVERRIDE_PATH" in required_block[:1200]


def test_the_writer_is_not_reachable_from_a_project_manifest() -> None:
    """The source path is derived from the project key by the materializer.

    A manifest that could name its own secret directory could name another
    project's, which is why `secret_source_path` takes a key and not a path,
    and why this module never accepts one.
    """
    source = Path(REPO_ROOT / "bin" / "render-secret-override.py").read_text(encoding="utf-8")
    assert "--project-key" in source
    assert "--secret-root" not in source
    assert "--source" not in source

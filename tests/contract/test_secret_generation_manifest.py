"""The generation manifest, built from the REAL contract and validated (D586).

**This module exists because a host deploy found what 4010 gate tests could
not.** Run 8b added `format: pgbackrest` to `secret-contract.schema.json` and
`secrets.required.yaml`, and the whole suite went green — because
`secret-generation.schema.json` is a *second* schema over the same two fields,
and nothing offline ever built a generation manifest from the real contract and
validated it. `agentic_postgres.secret_generation.validate_manifest` runs only
inside a real materialization, which needs a provider.

So the first Session 10 deploy died at step 5 with:

    secret-generation.schema.json:
      secrets/13/consumers/0/format: 'pgbackrest' is not one of ['raw', 'pgpass']
      secrets/13/consumers/0/target_file: '10-repo1-s3-key.conf' does not match
        '^[a-z][a-z0-9_.-]{0,63}$'

Two findings, not one. The format enum was a Run 8b omission. **The target_file
patterns had disagreed since long before Session 10** — the contract allows
letter-or-digit and the generation schema allowed letter only — and nothing had
ever exercised the gap because every target file until now began with a letter.

The tests below are in two layers, and the second is the one that generalises:
the two schemas must agree, and a manifest built from the shipped contract must
validate. A future `format` or a future `target_file` cannot repeat this.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, secret_generation, secrets_contract

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CONTRACT_SCHEMA = json.loads(
    (REPO_ROOT / "schemas" / "secret-contract.schema.json").read_text(encoding="utf-8")
)
GENERATION_SCHEMA = json.loads(
    (REPO_ROOT / "schemas" / "secret-generation.schema.json").read_text(encoding="utf-8")
)


def _generation_consumer() -> dict[str, Any]:
    return GENERATION_SCHEMA["properties"]["secrets"]["items"]["properties"]["consumers"]["items"][
        "properties"
    ]


# ---------------------------------------------------------------------------
# The two schemas are two authorities over one concept, so they must agree
# ---------------------------------------------------------------------------


def test_the_two_schemas_admit_the_same_formats() -> None:
    """A format the contract declares legal must be recordable in a generation.

    They disagreed for a whole session: `pgbackrest` was added to the contract in
    Run 8b and not here, so a project whose contract validated could not be
    materialized at all.
    """
    contract = CONTRACT_SCHEMA["$defs"]["format"]["enum"]
    generation = _generation_consumer()["format"]["enum"]
    assert generation == contract, (
        f"the contract admits {contract} and a generation admits {generation}. "
        "A format only one of them knows about is a project that validates and "
        "cannot be deployed."
    )
    # Not vacuous: both must actually carry the format this session added.
    assert "pgbackrest" in contract


def test_the_two_schemas_admit_the_same_target_file_names() -> None:
    """And the same basenames.

    The generation schema was stricter — letter-first against the contract's
    letter-or-digit — which made a legal contract undeployable the first time a
    target file began with a digit.
    """
    contract = CONTRACT_SCHEMA["$defs"]["composeConsumer"]["properties"]["target_file"]["pattern"]
    generation = _generation_consumer()["target_file"]["pattern"]
    assert generation == contract, (
        f"the contract accepts {contract!r} and a generation accepts {generation!r}. "
        "A name only one of them accepts is a project that validates and cannot "
        "be materialized."
    )


def test_the_root_consumer_shares_the_same_name_rule() -> None:
    """The third place the same pattern is written, and it must not drift either."""
    compose = CONTRACT_SCHEMA["$defs"]["composeConsumer"]["properties"]["target_file"]["pattern"]
    root = CONTRACT_SCHEMA["$defs"]["rootConsumer"]["properties"]["target_file"]["pattern"]
    assert root == compose


# ---------------------------------------------------------------------------
# The proof that was missing: build one from the SHIPPED contract
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")


# From 2: session 1 deploys nothing and materializes nothing, and the schema
# rightly refuses an empty secret set rather than recording a generation that
# holds no files.
@pytest.mark.parametrize("session", range(2, 11))
def test_a_generation_manifest_validates_for_every_session(
    contract: dict[str, Any], session: int
) -> None:
    """Every session's secret set produces a manifest the generation schema accepts.

    **This is the test whose absence cost a deploy.** `validate_manifest` was
    reachable only through a real materialization, so a contract change that was
    legal by one schema and illegal by the other passed every offline check and
    failed on the host, at step 5, after the release had been installed.

    Parametrized over every session rather than only the current one: a secret
    introduced in session 7 is still materialized by a session 10 deploy, and the
    manifest is built from whatever `active_secrets` returns.
    """
    active = secrets_contract.active_secrets(contract, session)
    document = secret_generation.build_manifest(
        project_key="fixture-alpha-dev",
        generation_id="0123456789abcdef",
        secrets=active,
    )
    assert document["secrets"], f"session {session} materializes nothing"


def test_the_session_ten_backup_secrets_are_in_the_manifest(contract: dict[str, Any]) -> None:
    """Named explicitly, because they are the three the deploy choked on.

    A parametrized sweep that silently stopped covering them would still pass, so
    this asserts the three are present and that each records the pgbackrest
    format and its include-path basename.
    """
    from agentic_postgres import config

    document = secret_generation.build_manifest(
        project_key="fixture-alpha-dev",
        generation_id="0123456789abcdef",
        secrets=secrets_contract.active_secrets(contract, 10),
    )
    by_name = {entry["name"]: entry for entry in document["secrets"]}

    for name in config.BACKUP_CREDENTIAL_NAMES:
        assert name in by_name, f"{name} is not in a session-10 generation manifest"
        consumers = by_name[name]["consumers"]
        assert consumers, f"{name} records no consumer"
        assert all(c["format"] == "pgbackrest" for c in consumers), consumers
        assert all(c["target_file"].endswith(".conf") for c in consumers), consumers

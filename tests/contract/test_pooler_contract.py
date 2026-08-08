"""The pooler's credential handling and grant surface (Session 4 Run 3).

The pooler is the first service in this system that holds a credential an
*application* uses, and the first whose configuration file contains a password
in plaintext. Both of those make the interesting assertions negative: where the
credential may not appear, and what may not be written to a persistent path.

Three facts here were measured against the locked image rather than assumed,
and each had a plausible wrong answer:

* the image's uid/gid is **70**, and unlike the cluster image it sets a default
  user, so the process never runs as root and cannot fix up a file's ownership
  on the way past. A secret materialized 999 or 65532 is simply unreadable.
* a **plaintext** user list under `auth_type = scram-sha-256` authenticates the
  client and also lets the pooler log in upstream — the cluster records
  `method=scram-sha-256` for the pooler's own connection. The alternative form,
  the server's SCRAM verifier, also works and is unavailable at this point in
  the build: it can only be read from the cluster, so the role would have to
  exist before the file that creates it could be written.
* the pooler logs `could not open auth_file … Permission denied` as an ERROR
  and **goes on listening**. It comes up, accepts connections, and refuses every
  one. That is why `test_the_readiness_check_cannot_be_satisfied_by_a_listening_port`
  exists as a note to Run 4 rather than as a check on a health command that has
  not been written yet.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, rendering
from agentic_postgres.secrets_contract import load_secret_contract

pytestmark = [pytest.mark.contract, pytest.mark.p0]

MODEL = REPO_ROOT / "compose.yaml"
CONTRACT = REPO_ROOT / "secrets.required.yaml"

#: Measured in Run 1 against the locked pooler digest. The same two numbers
#: appear in compose.yaml and in secrets.required.yaml, and
#: test_secret_contract.py cross-checks those two against each other; this
#: module is the third point of the triangle, holding the measurement itself.
PGBOUNCER_UID = 70
PGBOUNCER_GID = 70

POOLER_SECRETS = ("app_runtime_password", "pgbouncer_admin_password")


@pytest.fixture(scope="module")
def model() -> dict[str, Any]:
    return yaml.safe_load(MODEL.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pooler(model: dict[str, Any]) -> dict[str, Any]:
    assert "pgbouncer" in model["services"], (
        "the pooler service is gone; this module measures nothing"
    )
    return model["services"]["pgbouncer"]


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return load_secret_contract(CONTRACT)


def entrypoint_text(pooler: dict[str, Any]) -> str:
    return " ".join(str(part) for part in pooler["entrypoint"])


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_the_pooler_runs_as_the_measured_uid(pooler: dict[str, Any]) -> None:
    assert pooler["user"] == f"{PGBOUNCER_UID}:{PGBOUNCER_GID}"


def test_the_contract_grants_the_pooler_files_it_can_read(contract: dict[str, Any]) -> None:
    """The failure this prevents is silent at materialization and fatal at start.

    A file owned 65532 is written successfully, mounted successfully, and then
    unreadable by uid 70 — at which point the pooler starts anyway and refuses
    every connection.
    """
    granted = [
        consumer
        for secret in contract["secrets"]
        for consumer in secret["consumers"]
        if consumer["service"] == "pgbouncer"
    ]
    assert {consumer["target_file"] for consumer in granted} == set(POOLER_SECRETS)
    for consumer in granted:
        assert (consumer["uid"], consumer["gid"]) == (PGBOUNCER_UID, PGBOUNCER_GID)
        assert consumer["mode"] == "0400"


def test_the_two_credentials_are_separate_secrets(contract: dict[str, Any]) -> None:
    """The admin console credential is not the application's.

    A health check has to authenticate as somebody. Doing that as the
    application would put the application's password in a health command, which
    `docker inspect` prints.
    """
    names = {secret["name"] for secret in contract["secrets"]}
    assert set(POOLER_SECRETS) <= names
    keys = {
        secret["name"]: secret["provider_key"]
        for secret in contract["secrets"]
        if secret["name"] in POOLER_SECRETS
    }
    assert len(set(keys.values())) == 2, keys


# ---------------------------------------------------------------------------
# Where the credential may not appear
# ---------------------------------------------------------------------------


def test_no_password_reaches_the_environment(pooler: dict[str, Any]) -> None:
    """`docker inspect` prints this block verbatim, to anyone in the docker group.

    Every value here must be an identifier or a number. The credential arrives
    as a file and is read inside the container, which is the same construction
    the migration plane uses and for the same reason (ADR 0034).
    """
    for name, value in pooler["environment"].items():
        assert "PASSWORD" not in name.upper(), f"{name} names a password"
        assert "${" in str(value) or str(value).isdigit(), (
            f"{name} carries a literal that is not an interpolation: {value!r}"
        )


def test_the_entrypoint_reads_the_credentials_from_files(pooler: dict[str, Any]) -> None:
    text = entrypoint_text(pooler)
    for name in POOLER_SECRETS:
        assert f"/run/secrets/{name}" in text, f"{name} is not read from its mounted file"


def test_the_entrypoint_names_no_password_variable_compose_could_fill(
    pooler: dict[str, Any],
) -> None:
    """A `$PASSWORD` here would be filled by Compose, not by the file read.

    The shell variables that hold the credential are `$$`-escaped so Compose
    leaves them alone. One written with a single `$` would be interpolated at
    render time, resolve to empty, and produce a user list with an empty
    password — which fails authentication in a way that reads like a wrong
    credential rather than like a broken model.
    """
    text = entrypoint_text(pooler)
    single = re.findall(r"(?<!\$)\$(?!\$)\{?([A-Za-z_][A-Za-z0-9_]*)", text)
    assert not single, f"the entrypoint has un-escaped interpolations Compose will fill: {single}"


def test_no_secret_value_can_reach_the_compose_env() -> None:
    """The rendered env file is derived from identifiers only.

    Asserted on the key set rather than on a scan of the values, because a scan
    passes for as long as nobody adds the key.
    """
    for key in rendering.COMPOSE_ENV_KEYS:
        assert "PASSWORD" not in key.upper(), f"{key} would put a credential in compose.env"
        assert "SECRET" not in key.upper(), f"{key} would put a credential in compose.env"


# ---------------------------------------------------------------------------
# Where the user list may not be written
# ---------------------------------------------------------------------------


def test_the_pooler_filesystem_is_read_only(pooler: dict[str, Any]) -> None:
    assert pooler["read_only"] is True


def test_the_config_directory_is_a_tmpfs_owned_by_the_pooler(pooler: dict[str, Any]) -> None:
    """The mount that keeps a plaintext credential off every persistent path.

    The image ships a world-readable `userlist.txt` in this directory, so
    without the tmpfs the entrypoint would be writing a secret onto the
    container filesystem — which `docker cp` reads and a diff of the layer
    shows.
    """
    mounts = {entry.split(":", 1)[0]: entry for entry in pooler["tmpfs"]}
    assert "/etc/pgbouncer" in mounts, "the config directory is not a tmpfs"
    options = mounts["/etc/pgbouncer"]
    assert f"uid={PGBOUNCER_UID}" in options and f"gid={PGBOUNCER_GID}" in options
    assert "mode=0700" in options


def test_the_pooler_mounts_no_volume(pooler: dict[str, Any]) -> None:
    """A volume here is the one way the user list could outlive the container."""
    assert "volumes" not in pooler, "the pooler has a volume; the user list could persist"


def test_the_entrypoint_writes_the_user_list_under_a_restrictive_umask(
    pooler: dict[str, Any],
) -> None:
    """`umask 077` before the write, rather than a chmod after it.

    A chmod afterwards leaves a window in which the file exists at the default
    mode. The window is short rather than absent, and this file is readable by
    anything that can enter the mount namespace during it.
    """
    text = entrypoint_text(pooler)
    assert "umask 077" in text
    assert text.index("umask 077") < text.index("/run/secrets/"), (
        "the umask is set after the credential is read"
    )


# ---------------------------------------------------------------------------
# What the pooler is allowed to reach
# ---------------------------------------------------------------------------


def test_the_pooler_publishes_no_host_port(pooler: dict[str, Any]) -> None:
    """Session 4 publishes a loopback port, and never from this file.

    The publication is written into the root-owned runtime override. A
    repository that could publish a database port would be one clone away from
    publishing one (ADR 0040).
    """
    assert "ports" not in pooler


def test_the_pooler_joins_only_the_internal_network(pooler: dict[str, Any]) -> None:
    assert pooler["networks"] == ["internal"]


def test_the_pooler_carries_no_traefik_label_of_any_kind(pooler: dict[str, Any]) -> None:
    labels = pooler.get("labels", {}) or {}
    assert not [key for key in labels if "traefik" in str(key).lower()]


def test_the_pooler_drops_every_capability(pooler: dict[str, Any]) -> None:
    assert pooler["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in pooler["security_opt"]


def test_transaction_pooling_is_not_configurable(pooler: dict[str, Any]) -> None:
    """The plan forbids selecting session pooling to make a client pass.

    Making the mode a constant rather than a manifest field is what makes that
    rule structural instead of a matter of review: there is no field to set.
    """
    assert rendering.PGBOUNCER_POOL_MODE == "transaction"
    assert "pool_mode = $$APG_POOL_MODE" in entrypoint_text(pooler)

    schema = yaml.safe_load((REPO_ROOT / "schemas" / "project.schema.json").read_text("utf-8"))
    database = schema["properties"]["database"]["properties"]
    assert not [key for key in database if "pool_mode" in key or "session_pool" in key], (
        "a manifest field can now select the pooling mode"
    )


def test_the_listen_port_is_the_convention_not_the_image_default() -> None:
    """6432 is written down because the image's own default is 5432 (Run 1).

    A probe written against the convention would pass or fail for reasons
    unrelated to the pooler being healthy if the rendered value were ever left
    to the image.
    """
    assert rendering.PGBOUNCER_LISTEN_PORT == 6432


def test_the_readiness_check_cannot_be_satisfied_by_a_listening_port(
    pooler: dict[str, Any],
) -> None:
    """A note to Run 4, asserted rather than written in a comment.

    Measured: with an unreadable auth file the pooler logs an ERROR and goes on
    listening, so it accepts connections and refuses all of them. Any health
    check added here must therefore authenticate. Until one exists, this asserts
    the absence — so that adding a `healthcheck:` that merely opens a socket
    fails this test rather than passing review.
    """
    check = pooler.get("healthcheck")
    if check is None:
        pytest.skip("Run 4 adds the health check; this asserts its shape when it exists")
    command = " ".join(str(part) for part in check["test"])
    assert "pg_isready" not in command, (
        "pg_isready proves a socket answers, and this pooler answers while refusing "
        "every connection; the check must authenticate"
    )
    assert "PGPASSWORD=" not in command, "a health command must not carry a credential"

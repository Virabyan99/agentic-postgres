"""The endpoint derivation, and the manifest field it is derived from.

ADR 0106. The gap this closes is D343: `storage` was `additionalProperties:
false` with no account id, so an operator could not supply one even by hand,
and the container was handed a bucket with no way to know where it was. The
session plan's feasibility table called the account id an operator input for
four runs while nothing accepted it -- D276's shape from the other side, and the
rule it produces is *a plan's input table is not an interface; grep for the
reader.*
"""

from __future__ import annotations

import pytest

from agentic_postgres import config, naming, rendering
from agentic_postgres.config import ManifestError
from agentic_postgres.naming import NamingError

ALPHA = "0123456789abcdef0123456789abcdef"
BETA = "fedcba9876543210fedcba9876543210"


def test_the_endpoint_is_the_account_host():
    assert naming.storage_endpoint_url(ALPHA) == f"https://{ALPHA}.r2.cloudflarestorage.com"


def test_a_jurisdiction_changes_the_host_and_default_does_not():
    """A jurisdictional bucket is reachable only through its own endpoint.

    The two arms disagree deliberately: if `default` also inserted a label, the
    equality above would still hold for the wrong reason.
    """
    assert naming.storage_endpoint_url(ALPHA, "eu") == (
        f"https://{ALPHA}.eu.r2.cloudflarestorage.com"
    )
    assert naming.storage_endpoint_url(ALPHA, "default") == naming.storage_endpoint_url(ALPHA)


def test_two_accounts_produce_two_endpoints():
    """D332: two fixtures that agree on a value cannot prove the value is read.

    The example manifests are the fixtures that matter here and they disagree --
    see `test_every_storage_variable_is_read_from_the_manifest`. This is the
    unit-level pair, which exists because it can also cover the malformed and
    disabled cases a valid manifest cannot express.
    """
    assert naming.storage_endpoint_url(ALPHA) != naming.storage_endpoint_url(BETA)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "0123456789ABCDEF0123456789ABCDEF",  # uppercase
        "0123456789abcdef0123456789abcde",  # 31
        "0123456789abcdef0123456789abcdef0",  # 33
        "0123456789abcdef0123456789abcdeg",  # not hex
        f"{ALPHA}.evil.example.com",
    ],
)
def test_a_malformed_account_id_is_refused_at_derivation(bad):
    """A typo must fail here, not at the first presign.

    The last case is the one with teeth: an account id that is a hostname
    fragment would otherwise be concatenated into the endpoint and dial
    somebody else's host with this project's credential.
    """
    with pytest.raises(NamingError, match="account id"):
        naming.storage_endpoint_url(bad)


def test_an_unknown_jurisdiction_is_refused():
    with pytest.raises(NamingError, match="jurisdiction"):
        naming.storage_endpoint_url(ALPHA, "atlantis")


def test_the_jurisdiction_list_says_what_has_been_measured():
    """Only `default` has been dialled; the other two are vendor documentation.

    Asserting the tuple's contents is not the point -- the point is that the
    list is closed, so a value nobody has measured cannot arrive through a
    manifest without this test going red and somebody re-reading the comment.
    """
    assert naming.R2_JURISDICTIONS == ("default", "eu", "fedramp")


# --------------------------------------------------------------------------
# The manifest


def enabled_storage(**overrides) -> dict:
    base = {"enabled": True, "account_id": ALPHA, "jurisdiction": "default"}
    return {**base, **overrides}


def test_storage_enabled_without_an_account_is_refused_and_the_message_helps():
    """The message names where the value comes from; a schema error cannot."""
    with pytest.raises(ManifestError) as caught:
        config._validate_storage({"enabled": True})

    message = str(caught.value)
    assert "storage.account_id is required" in message
    assert "session-07-operator-guide" in message


def test_storage_disabled_may_not_carry_an_account():
    with pytest.raises(ManifestError, match=r"storage\.account_id"):
        config._validate_storage({"enabled": False, "account_id": ALPHA})


def test_a_malformed_account_reaches_the_manifest_error_through_the_deriver():
    """One authority for what a well-formed account id is (ADR 0002).

    `_validate_storage` calls `naming.storage_endpoint_url` rather than
    re-checking the pattern beside it. A second copy of the regex is the shape
    that drifts.
    """
    with pytest.raises(ManifestError, match="account id"):
        config._validate_storage(enabled_storage(account_id="nope"))


def test_the_default_jurisdiction_is_not_restated_by_the_validator():
    config._validate_storage({"enabled": True, "account_id": ALPHA})


def test_storage_defaults_carry_no_account_id():
    """No default, deliberately (ADR 0106).

    A default account id would be a well-formed value that authenticates to
    nothing -- ADR 0055's and D333's shape, where a generated stand-in for an
    operator-supplied secret was perfectly plausible and useless.
    """
    assert config.STORAGE_DEFAULTS["account_id"] is None
    assert config.STORAGE_DEFAULTS["jurisdiction"] == "default"


# --------------------------------------------------------------------------
# What the container receives


def test_the_endpoint_is_a_rendered_compose_variable():
    assert "STORAGE_ENDPOINT" in rendering.COMPOSE_ENV_KEYS


def _render(storage: dict) -> dict[str, str]:
    """One rendered `compose.env`, as a mapping, for a storage block."""
    identity = naming.derive(
        slug="alpha",
        environment="dev",
        domain="alpha.example.com",
        api_base_path="/api",
        mcp_base_path="/mcp",
        storage_enabled=bool(storage.get("enabled")),
    )
    database = {"max_client_connections": 100, "pool_size": 20}
    budget = config.database_budget(database)
    raw = rendering.build_compose_env(
        identity,
        budget,
        database,
        storage={**config.STORAGE_DEFAULTS, **storage},
    )
    values = {}
    for line in raw.decode("utf-8").splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            values[name] = value
    return values


def test_two_storage_blocks_render_two_endpoints():
    """The renderer reads both inputs, asserted on two blocks that disagree.

    The example manifests cover this too, and deliberately: alpha omits
    `jurisdiction` while alpine names `eu`. This pair is the same property at
    the unit level, held here so that a change to the fixtures cannot quietly
    remove the only coverage of the jurisdiction branch (D332).
    """
    alpha = _render({"enabled": True, "account_id": ALPHA, "jurisdiction": "default"})
    beta = _render({"enabled": True, "account_id": BETA, "jurisdiction": "eu"})

    assert alpha["STORAGE_ENDPOINT"] == f"https://{ALPHA}.r2.cloudflarestorage.com"
    assert beta["STORAGE_ENDPOINT"] == f"https://{BETA}.eu.r2.cloudflarestorage.com"
    assert alpha["STORAGE_ENDPOINT"] != beta["STORAGE_ENDPOINT"]


def test_a_disabled_project_renders_an_unresolvable_placeholder():
    """Compose refuses an empty value as firmly as an unset one (D178).

    A project with storage off still has to render, so the variable carries a
    placeholder rather than an empty string. `.invalid` is reserved by RFC 2606
    and resolves nowhere, so a service that somehow dialled it fails to connect
    rather than reaching something real -- which a plausible-looking hostname
    might, and which is how a wrong default becomes a silent success.
    """
    rendered = _render({"enabled": False})

    assert rendered["STORAGE_ENDPOINT"] == "https://storage.disabled.invalid"
    assert rendered["STORAGE_ENDPOINT"] != ""
    assert "r2.cloudflarestorage.com" not in rendered["STORAGE_ENDPOINT"]

"""The secret boundary, proved structurally — no secret required.

This is the half of SEC-SECRET-001 that is a property of the model rather than
of a running host, so it runs everywhere including CI: no path exists by which a
value *could* reach an environment variable, a generated dotenv, a Compose
interpolation, or a service that was never granted it.

The other half — that no value is in fact present anywhere it should not be —
needs a real secret and a real host, and lives in ``test_session2_secrets.py``.
Neither half is sufficient alone. Structure without measurement misses the leak
that bypassed the structure; measurement without structure passes on the day
nobody happened to log the value.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, runtime_override, secrets_contract
from agentic_postgres.config import is_sensitive_key
from agentic_postgres.secrets_contract import (
    SECRET_ROOT,
    active_secrets,
    granted_services,
    load_secret_contract,
)

pytestmark = [pytest.mark.p0, pytest.mark.security, pytest.mark.contract]

#: Both committed Compose models. Neither may hand a service a secret value.
COMPOSE_MODELS = ("compose.yaml", "infra/edge/compose.yaml")

#: What counts as a secret-bearing key is ``config.is_sensitive_key`` and
#: nothing else. Writing a second pattern here looked harmless and was wrong on
#: its first test: ADR 0008 matches a whole key or a *terminal* token, so
#: ``password_secret_ref`` is a reference and is safe, while a fresh regex
#: matching ``password`` anywhere rejects it. Two definitions of "sensitive"
#: would drift, and the copy nobody updates is the one enforcing the boundary.


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return load_secret_contract(REPO_ROOT / "secrets.required.yaml")


def load_model(relative: str) -> dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / relative).read_text(encoding="utf-8"))


def environment_entries(definition: dict[str, Any]) -> dict[str, str]:
    """Normalise both Compose environment forms to a mapping."""
    environment = definition.get("environment") or {}
    if isinstance(environment, dict):
        return {str(k): str(v) for k, v in environment.items()}
    return dict(entry.split("=", 1) for entry in environment if "=" in entry)


# ---------------------------------------------------------------------------
# No value can travel through the environment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", COMPOSE_MODELS)
def test_no_service_takes_a_secret_through_the_environment(
    relative: str, contract: dict[str, Any]
) -> None:
    """An ``environment:`` entry is visible in ``docker inspect`` forever.

    Checked against the declared secret names as well as the generic tokens,
    because a key called ``APG_SESSION2_SENTINEL`` carries none of the generic
    words and would otherwise pass.

    **A sensitive-named key may name a file, under three conditions (ADR 0064).**
    ``PGRST_JWT_SECRET`` is PostgREST's name rather than ours and ends in
    ``_secret``; its value is ``@`` followed by a path, which is a reference and
    not a value, and the file behind it is public verification material written
    0444. ADR 0008 drew that distinction once already at the key level --
    ``password_secret_ref`` is allowed because it is a reference -- and this is
    the same distinction one level down.

    The exemption is not by name. The value must *be* a reference, the path must
    be one ``runtime_override`` declares, and it must not be under the secret
    mount. That is stricter than what it replaces in two directions: the old rule
    read only the key's spelling, so it could not have refused a permitted key
    pointed at ``/run/secrets/anything``, and could not have refused a second
    ``@`` reference to an undeclared path.
    """
    declared = {secret["name"].lower() for secret in active_secrets(contract, session=2)}
    declared |= {secret["provider_key"].lower() for secret in active_secrets(contract, session=2)}

    offenders: list[str] = []
    for service, definition in (load_model(relative).get("services") or {}).items():
        for key, value in environment_entries(definition).items():
            lowered = key.lower()
            if any(name in f"{lowered} {value.lower()}" for name in declared):
                offenders.append(f"{relative}:{service}:{key} (names a declared secret)")
            elif is_sensitive_key(key) and not is_public_reference(value):
                offenders.append(f"{relative}:{service}:{key} (secret-bearing key)")

    assert not offenders, f"secret material reaches a service through the environment: {offenders}"


def is_public_reference(value: str) -> bool:
    """ADR 0064's three conditions, all required.

    A reference, to a declared path, outside the secret mount. A literal, an
    undeclared path, or anything under ``/run/secrets`` is not a public
    reference, and the caller treats it as an offender.
    """
    if not value.startswith("@"):
        return False
    referenced = value[1:]
    if referenced.startswith(f"{secrets_contract.CONTAINER_SECRET_DIR}/"):
        return False
    return referenced in runtime_override.PUBLIC_REFERENCE_PATHS


def test_the_public_reference_rule_refuses_everything_but_the_declared_path() -> None:
    """Guard the guard. ADR 0064 is an exemption, so its edges are the test.

    Goes red if: the rule starts accepting a literal, a path under the secret
    mount, or any path that is not declared -- each of which is a way for this
    exemption to become "a key called *_secret is fine".
    """
    declared = next(iter(runtime_override.PUBLIC_REFERENCE_PATHS))
    assert is_public_reference(f"@{declared}")

    for refused in (
        declared,  # a path, but not a reference
        f"@{secrets_contract.CONTAINER_SECRET_DIR}/postgrest_authenticator_pgpass",
        "@/etc/postgrest/anything-else.json",
        "@/run/secrets/../etc/postgrest/jwks.json",
        "hunter2",
        "",
    ):
        assert not is_public_reference(refused), refused


def test_the_key_scan_would_actually_reject_something() -> None:
    """Guard the guard, including the false positives ADR 0008 forbids."""
    for rejected in ("db_password", "API_TOKEN", "client_secret", "password"):
        assert is_sensitive_key(rejected), rejected
    for allowed in ("password_secret_ref", "tokenizer", "secret_name", "credentials_path"):
        assert not is_sensitive_key(allowed), allowed


# ---------------------------------------------------------------------------
# No value can travel through a file Compose reads on its own
# ---------------------------------------------------------------------------


def test_the_secret_root_is_absolute_and_outside_the_repository() -> None:
    """A secret root inside the checkout is one ``git add -A`` from published."""
    root = Path(SECRET_ROOT)
    assert root.is_absolute(), SECRET_ROOT
    assert root != REPO_ROOT
    assert REPO_ROOT not in root.parents


def test_nothing_generates_a_dotenv_under_the_secret_root() -> None:
    """Compose reads a dotenv without being asked, so a generated one is a leak."""
    offenders: list[str] = []
    pattern = re.compile(rf"{re.escape(SECRET_ROOT)}\S*/\.env\b")
    for root in ("bin", "src", "libexec", "systemd", "infra", "services"):
        for path in (REPO_ROOT / root).rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if pattern.search(text):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"a dotenv is written under the secret root by: {offenders}"


# ---------------------------------------------------------------------------
# No service holds a grant it was not given
# ---------------------------------------------------------------------------


def test_only_granted_services_declare_a_secret_mount(contract: dict[str, Any]) -> None:
    granted = granted_services(contract, session=2)
    offenders = [
        service
        for service, definition in (load_model("compose.yaml").get("services") or {}).items()
        if definition.get("secrets") and service not in granted
    ]
    assert not offenders, f"services mount a secret with no grant in the contract: {offenders}"


def test_the_edge_model_grants_no_secret_at_all(contract: dict[str, Any]) -> None:
    """The edge is the publicly reachable plane and holds nothing worth stealing."""
    del contract
    model = load_model("infra/edge/compose.yaml")
    assert not model.get("secrets"), model.get("secrets")
    offenders = [
        service
        for service, definition in (model.get("services") or {}).items()
        if definition.get("secrets")
    ]
    assert not offenders, f"the edge stack mounts secrets into: {offenders}"

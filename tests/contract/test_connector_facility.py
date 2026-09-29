"""The connectors facility: manifest 7, outputs 19, one gated secret, two derivations.

`CONN-FAC-001` (ADR 0237, D1784, D1785). A project that leaves
`connectors.enabled` off owes nothing new; one that turns it on owes exactly
`connector_signing_key`, from which every connector's key is DERIVED. The
derivation lives in the auth image (`connector_signature.derive`) and is proved
here against an HMAC this module writes itself; the host's copy arrives with its
caller, `bin/connector.py key`, in Run 7, and the two-copy agreement with it
(D204: a module nothing imports is a feature that does not exist, D1828).

No cluster and no host: the manifest loader, the facility reader, the secret
contract's project view, the secret override's mounts and the two derivations
are all pure functions over files in this checkout.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    config,
    secret_override,
    secrets_contract,
    service_source,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

CONTRACT = REPO_ROOT / "secrets.required.yaml"
RENDERED = (
    REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json",
    REPO_ROOT / ".generated" / "fixture-alpine-dev" / "outputs.json",
)
GATED_ENTRY = "connector_signing_key"
ENDPOINT = "http://apg-s34-sink:8080/ok"


@pytest.fixture
def base() -> dict[str, Any]:
    """The example manifest at the newest version, WITHOUT the facility."""
    return yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))


def _load(tmp_path: Path, document: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return config.load_project_manifest(path)


def _enabled(document: dict[str, Any], **endpoints: str) -> dict[str, Any]:
    document = copy.deepcopy(document)
    document["connectors"] = {"enabled": True, "endpoints": dict(endpoints)}
    return document


def _rendered(path: Path) -> dict[str, Any]:
    if not path.is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    return json.loads(path.read_text(encoding="utf-8"))


def test_schema_seven_admits_connectors_and_six_forbids_them(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """ADR 0177's rule a sixth time, `backup.mirror`'s shape: optional at 7."""
    assert base["schema_version"] == 7 == config.PROJECT_CONNECTORS_FROM
    assert "connectors" not in base
    assert config.connectors_enabled(_load(tmp_path, base)) is False

    loaded = _load(tmp_path, _enabled(base, **{"note-embedded": ENDPOINT}))
    assert config.connectors_enabled(loaded) is True
    assert config.connector_endpoints(loaded) == {"note-embedded": ENDPOINT}

    six = _enabled(base, **{"note-embedded": ENDPOINT})
    six["schema_version"] = 6
    with pytest.raises(config.ManifestError):
        _load(tmp_path, six)
    # The control: the same downgrade without the key loads.
    plain = copy.deepcopy(base)
    plain["schema_version"] = 6
    assert _load(tmp_path, plain)["schema_version"] == 6


@pytest.mark.parametrize(
    "endpoint",
    [
        pytest.param("https://user:secret@sink.test/hook", id="userinfo"),
        pytest.param("https://sink.test/hook?token=abc", id="query"),
        pytest.param("https://sink.test/hook#fragment", id="fragment"),
        pytest.param("ftp://sink.test/hook", id="scheme"),
        pytest.param("https://sink.test/ho ok", id="space"),
        pytest.param("https:///hook", id="no_host"),
    ],
)
def test_an_endpoint_may_not_carry_a_credential(
    tmp_path: Path, base: dict[str, Any], endpoint: str
) -> None:
    """D1786: no userinfo, no query, no fragment -- an endpoint cannot carry a
    credential, so a URL that reaches no record could not leak one anyway."""
    with pytest.raises(config.ManifestError):
        _load(tmp_path, _enabled(base, **{"note-embedded": endpoint}))
    # The control, in the same test: the sink's own address loads.
    _load(tmp_path, _enabled(base, **{"note-embedded": ENDPOINT}))


def test_one_reader_decides_the_facility(tmp_path: Path, base: dict[str, Any]) -> None:
    """`config.connectors_enabled` reads a manifest AND a rendered document at the
    same place, and `enabled_facilities` asks it for both (D1785) -- three
    callers decide facilities from a document, so a manifest-only reader would
    leave them blind."""
    manifest = _load(tmp_path, _enabled(base))
    assert secrets_contract.FACILITY_CONNECTORS in secrets_contract.enabled_facilities(manifest)
    assert secrets_contract.FACILITY_CONNECTORS not in secrets_contract.enabled_facilities(base)

    document = _rendered(RENDERED[0])
    assert document["schema_version"] == 19
    assert document["connectors"] == {"enabled": False}
    assert secrets_contract.FACILITY_CONNECTORS not in secrets_contract.enabled_facilities(document)
    on = copy.deepcopy(document)
    on["connectors"]["enabled"] = True
    assert secrets_contract.FACILITY_CONNECTORS in secrets_contract.enabled_facilities(on)

    # And a document that has no block at all -- below 19 -- reads off.
    below = copy.deepcopy(document)
    del below["connectors"]
    assert config.connectors_enabled(below) is False


def _owed(facilities: frozenset[str], session: int = 34) -> set[str]:
    """What deploy step 0 would demand of the provider (`_secrets_the_provider_
    is_missing`'s selection, with nothing managed)."""
    contract = secrets_contract.load_secret_contract(CONTRACT)
    return {
        secret["name"]
        for secret in secrets_contract.active_secrets(contract, session, facilities=facilities)
        if secret.get("required") and secret.get("origin") == "generated"
    }


def test_a_project_without_the_facility_requires_nothing_new() -> None:
    """Both example renders: no `connector_signing_key` anywhere a project's view
    is taken -- the rendered `required_names`, and deploy step 0's set at 34."""
    for path in RENDERED:
        document = _rendered(path)
        facilities = secrets_contract.enabled_facilities(document)
        assert GATED_ENTRY not in document["secrets"]["required_names"], path
        assert GATED_ENTRY not in _owed(facilities), path
    # The declared view still holds it, gated.
    contract = secrets_contract.load_secret_contract(CONTRACT)
    entry = next(s for s in contract["secrets"] if s["name"] == GATED_ENTRY)
    assert entry["facility"] == secrets_contract.FACILITY_CONNECTORS
    assert entry["required"] is True and entry["origin"] == "generated"
    assert entry["introduced_in_session"] == 34


def test_a_project_with_the_facility_requires_the_key(tmp_path: Path, base: dict[str, Any]) -> None:
    """On, the project owes exactly one more generated secret at session 34, and
    the secret override mounts it into `auth` -- and into nothing else."""
    manifest = _load(tmp_path, _enabled(base))
    on = secrets_contract.enabled_facilities(manifest)
    off = secrets_contract.enabled_facilities(base)
    assert _owed(on) - _owed(off) == {GATED_ENTRY}
    assert GATED_ENTRY not in _owed(on, session=33), "a deploy through 33 owes it already"

    contract = secrets_contract.load_secret_contract(CONTRACT)
    mounted = secret_override.render_secret_override(
        project_key="fixture-alpha-dev",
        generation_id="gen-proof",
        contract=contract,
        session=34,
        facilities=on,
    ).decode("utf-8")
    unmounted = secret_override.render_secret_override(
        project_key="fixture-alpha-dev",
        generation_id="gen-proof",
        contract=contract,
        session=34,
        facilities=off,
    ).decode("utf-8")
    assert GATED_ENTRY in mounted and GATED_ENTRY not in unmounted
    services = yaml.safe_load(mounted)["services"]
    holders = sorted(name for name, body in services.items() if GATED_ENTRY in json.dumps(body))
    assert holders == ["auth"], holders


def _vectors() -> list[tuple[str, str]]:
    names = ["a", "note-embedded", "notes-inbox", "notes-digest", "x" * 63, "a1-b2"]
    masters = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(4)]
    masters.append(hashlib.sha256(b"long").hexdigest() * 2)
    return [(master, name) for master in masters for name in names][:10]


def test_the_key_derivation_matches_an_independent_hmac() -> None:
    """The image's derivation against an HMAC this test writes itself, on ten
    fixed vectors, so a changed label or input order fails here. Run 7 adds the
    host's copy and the two-copy agreement (D1682's pattern, D1828)."""
    service = service_source.load("connector_signature")
    vectors = _vectors()
    assert len(vectors) == 10
    for master, name in vectors:
        independent = hmac.new(
            bytes.fromhex(master), b"apg-connector-key-v1\x00" + name.encode(), hashlib.sha256
        ).hexdigest()
        assert service.derive(master, name) == independent, (master[:8], name)

    # Rig 34b's vector, measured against `openssl dgst -sha256 -mac HMAC`.
    key = bytes(range(32)).hex()
    body = b'{"note_id":"00000000-0000-4000-8000-000000000001"}'
    digest = service.sign(key, 1727600000, "7f1c1d6e-0000-4000-8000-000000000034", body)
    assert digest == "3c87822a243911edc8870359fd62616a6867de84986eef164eb028888a257aba"


@pytest.mark.parametrize(
    "master,name",
    [
        pytest.param("ab" * 32, "Bad", id="uppercase_name"),
        pytest.param("ab" * 32, "", id="empty_name"),
        pytest.param("AB" * 32, "ok", id="uppercase_master"),
        pytest.param("ab" * 31, "ok", id="short_master"),
    ],
)
def test_the_derivation_refuses_a_bad_name_or_master(master: str, name: str) -> None:
    """And the refusal carries no value: a master in an error message is a
    master in a log."""
    service = service_source.load("connector_signature")
    with pytest.raises(ValueError) as raised:
        service.derive(master, name)
    assert master not in str(raised.value)

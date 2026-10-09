"""`REC-REHOME-001`, offline: a project's provider project moved between stores (ADR 0263).

`bin/bootstrap-providers.py --mode rehome-check|rehome` driven against TWO
recorded stores: the source the project's state records, read through the
runtime reader as the project's own identity (D2275), and the destination the
host manifest names, written through the control plane and read back through
the runtime reader as the NEW identity. Every value the source holds carries a
planted canary, and every proof that moves one asserts the canary reaches no
printed line, no record and no carried file.

The filesystem is recorded, not touched: `write_private`, `move_file` and
`remove_file` are the command's own three ways of changing a file, so the
ORDER of what a run did to the host -- pending credentials, then the old files
kept aside, then the new state -- is a property of the calls made.

Nothing here contacts a provider, needs root, or writes under /etc.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

from agentic_postgres import CURRENT_SESSION, REPO_ROOT, bootstrap_state, dr_kit, secret_age
from agentic_postgres.config import load_project_manifest
from agentic_postgres.host_config import load_host_manifest
from agentic_postgres.infisical_client import Credential, InfisicalError, SecretTimes
from agentic_postgres.secrets_contract import (
    active_secrets,
    enabled_facilities,
    is_operator_supplied,
    load_secret_contract,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

KEY = "fixture-alpha-dev"
CANARY = f"APG-REHOME-CANARY-{uuid.uuid4().hex}"
SOURCE_URL = "https://app.infisical.com"
DESTINATION_URL = "https://secrets.example.test"
SOURCE_PROJECT = "3f5c0f4a-2b0f-4f9a-9a4d-1c1f0e2d3a4b"
DESTINATION_PROJECT = "9a1b2c3d-0000-4000-8000-00000000d357"
OPTIONAL = "auth_jwt_prepared_key"
SOURCE_TIME = "2026-08-04T10:00:00.000Z"


def load_command() -> Any:
    spec = importlib.util.spec_from_file_location(
        f"apg_rehome_{uuid.uuid4().hex}", REPO_ROOT / "bin" / "bootstrap-providers.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def declared() -> list[dict[str, Any]]:
    manifest = load_project_manifest(REPO_ROOT / "project.example.yaml")
    contract = load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    return active_secrets(contract, CURRENT_SESSION, facilities=enabled_facilities(manifest))


# ---------------------------------------------------------------------------
# Two recorded stores
# ---------------------------------------------------------------------------


class Stores:
    """Both stores' contents, keyed (api_url, project, path, key) -> (value, times)."""

    values: ClassVar[dict[tuple[str, str, str, str], tuple[str, SecretTimes]]] = {}
    events: ClassVar[list[tuple[str, ...]]] = []
    granted: ClassVar[set[str]] = set()
    existing_slugs: ClassVar[set[str]] = set()
    #: A name whose COPY the destination corrupts, for the read-back proof.
    corrupt: ClassVar[str | None] = None


class Reader:
    """The runtime reader, for either store: login, raw reads, nothing else."""

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url
        self.identity: str | None = None

    def login(self, credential: Credential) -> None:
        Stores.events.append(("reader.login", self.api_url, credential.client_id))
        self.identity = credential.client_id

    def _get(self, name: str, project_id: str, secret_path: str) -> tuple[str, SecretTimes]:
        if self.api_url == DESTINATION_URL and self.identity not in Stores.granted:
            raise InfisicalError("GET raw failed with HTTP 403", status=403)
        found = Stores.values.get((self.api_url, project_id, secret_path, name))
        if found is None:
            raise InfisicalError(f"GET /api/v3/secrets/raw/{name} failed with HTTP 404", status=404)
        return found

    def read_secret(
        self,
        *,
        name: str,
        project_id: str,
        environment: str,
        secret_path: str = "/",  # noqa: S107 -- a provider folder
    ) -> str:
        Stores.events.append(("reader.read", self.api_url, name))
        return self._get(name, project_id, secret_path)[0]

    def read_secret_times(
        self,
        *,
        name: str,
        project_id: str,
        environment: str,
        secret_path: str = "/",  # noqa: S107 -- a provider folder
    ) -> SecretTimes:
        Stores.events.append(("reader.times", self.api_url, name))
        return self._get(name, project_id, secret_path)[1]

    def logout(self) -> None:
        Stores.events.append(("reader.logout", self.api_url))


class Control:
    """The destination's control plane. Writes go into `Stores.values`."""

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url

    @classmethod
    def login(cls, api_url: str, client_id: str, client_secret: str) -> Control:
        Stores.events.append(("control.login", api_url))
        return cls(api_url)

    def create_project(self, name: str, slug: str, organization_id: str) -> str:
        Stores.events.append(("control.create_project", slug))
        if slug in Stores.existing_slugs:
            raise bootstrap_state.BootstrapStateError(
                "POST /api/v2/workspace failed with HTTP 400. The provider sent an explanation."
            )
        return DESTINATION_PROJECT

    def ensure_folder(self, project_id: str, environment: str, folder: str) -> None:
        Stores.events.append(("control.ensure_folder", folder))

    def create_secret(
        self, project_id: str, environment: str, secret_path: str, name: str, value: str
    ) -> bool:
        Stores.events.append(("control.create_secret", name))
        if Stores.corrupt == name:
            value = value + "-corrupted"
        Stores.values[(self.api_url, project_id, secret_path, name)] = (
            value,
            SecretTimes(
                version=1, created_at="2026-10-10T00:00:00Z", updated_at="2026-10-10T00:00:00Z"
            ),
        )
        return True

    def create_identity(self, name: str, organization_id: str) -> str:
        Stores.events.append(("control.create_identity", name))
        return "identity-new"

    def attach_universal_auth(self, identity_id: str) -> str:
        Stores.events.append(("control.attach_universal_auth", identity_id))
        return "client-new"

    def create_client_secret(self, identity_id: str, description: str) -> tuple[str, str]:
        Stores.events.append(("control.create_client_secret", identity_id))
        return ("secret-id-new", "client-secret-new")

    def grant_project_access(self, project_id: str, identity_id: str, role: str) -> None:
        Stores.events.append(("control.grant", project_id, identity_id, role))
        Stores.granted.add("client-new")

    def revoke_identity(self, identity_id: str) -> None:
        Stores.events.append(("control.revoke", identity_id))

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the rehome called {name}, which it has no business calling")


def times_for(secret: dict[str, Any]) -> SecretTimes:
    # The rotated trio reads version 3 at the source, everything else 1 (D2022).
    version = 3 if "max_age_days" in secret else 1
    return SecretTimes(version=version, created_at=SOURCE_TIME, updated_at=SOURCE_TIME)


def state_document(**overrides: Any) -> dict[str, Any]:
    document = {
        "schema_version": 1,
        "project_key": KEY,
        "project_manifest_sha256": "a" * 64,
        "provider_inputs_sha256": "b" * 64,
        "provider": "infisical",
        "api_url": SOURCE_URL,
        "organization_slug": "example-team",
        "infisical_project_id": SOURCE_PROJECT,
        "environment_slug": "dev",
        "runtime_folder": "/runtime",
        "runtime_identity_id": "identity-old",
        "runtime_client_id": "client-old",
        "active_client_secret_id": "secret-id-old",
        "credential_files": bootstrap_state.credential_paths(KEY),
        "managed_resources": ["project", "runtime_identity", "runtime_client_secret"],
        "created_at": "2026-08-04T10:00:00Z",
        "updated_at": "2026-08-04T10:00:00Z",
    }
    document.update(overrides)
    bootstrap_state.validate_state(document)
    return document


@pytest.fixture
def rig(tmp_path: Path) -> Any:
    """The command, its two stores, and a recorded filesystem.

    The source holds every declared value but the optional one, each carrying
    the canary; the host manifest names the destination.
    """
    module = load_command()
    module.ControlPlane = Control
    module.SecretReader = Reader
    module.runtime_credential = lambda state: Credential("client-old", "runtime-secret-old")
    Stores.values = {}
    Stores.events = []
    Stores.granted = set()
    Stores.existing_slugs = set()
    Stores.corrupt = None
    for secret in declared():
        if secret["name"] == OPTIONAL:
            continue
        Stores.values[
            (SOURCE_URL, SOURCE_PROJECT, secret["provider_path"], secret["provider_key"])
        ] = (f"{CANARY}-{secret['name']}", times_for(secret))

    filesystem: list[tuple[str, str, Any]] = []

    def write_private(path: Path, content: str, *, mode: int) -> None:
        filesystem.append(("write", str(path), (content, mode)))

    module.write_private = write_private
    module.move_file = lambda source, destination: filesystem.append(
        ("move", str(source), str(destination))
    )
    module.remove_file = lambda path: filesystem.append(("remove", str(path), None))
    module.state_path = lambda key: tmp_path / "projects" / key / "bootstrap-state.json"
    module.read_state = lambda key: state_document()
    module.FILESYSTEM = filesystem

    host = yaml.safe_load((REPO_ROOT / "host.example.yaml").read_text(encoding="utf-8"))
    host["infisical"]["api_url"] = DESTINATION_URL
    host["infisical"]["organization_id"] = "11111111-1111-4111-8111-111111111111"
    host["infisical"]["organization_slug"] = "agentic-postgres"
    host_path = tmp_path / "host.yaml"
    host_path.write_text(yaml.safe_dump(host), encoding="utf-8")
    module.HOST = host_path
    credential = tmp_path / "control-plane.cred"
    credential.write_text("control-id\ncontrol-secret\n", encoding="utf-8")
    module.CREDENTIAL = credential
    return module


def run(rig: Any, mode: str, *extra: str) -> int:
    try:
        return rig.main(
            [
                "--host",
                str(rig.HOST),
                "--project",
                str(REPO_ROOT / "project.example.yaml"),
                "--mode",
                mode,
                "--operator-credential-file",
                str(rig.CREDENTIAL),
                *extra,
            ]
        )
    except SystemExit as stop:
        return int(stop.code)


def written(rig: Any) -> dict[str, tuple[str, int]]:
    return {path: payload for kind, path, payload in rig.FILESYSTEM if kind == "write"}


def destination_writes() -> list[tuple[str, ...]]:
    return [
        event
        for event in Stores.events
        if event[0].startswith("control.") and event[0] != "control.login"
    ]


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def test_the_check_reads_every_declared_value_as_the_runtime_identity_and_writes_nothing(
    rig: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(rig, "rehome-check") == 0
    printed = capsys.readouterr()

    names = [secret["name"] for secret in declared()]
    reads = [event[2] for event in Stores.events if event[0] == "reader.read"]
    assert reads == [s["provider_key"] for s in declared()], "not every declared value was read"
    assert {event[1] for event in Stores.events if event[0] == "reader.read"} == {SOURCE_URL}
    assert ("reader.login", SOURCE_URL, "client-old") in Stores.events, (
        "the source was not read as the project's own runtime identity (D2275)"
    )
    assert destination_writes() == [], "the check called the destination beyond its login"
    assert ("control.login", DESTINATION_URL) in Stores.events
    assert rig.FILESYSTEM == [], "the check changed a file on this host"

    for name in names:
        expected = "absent (optional)" if name == OPTIONAL else "present "
        line = next(
            line for line in printed.out.splitlines() if line.strip().startswith(name + " ")
        )
        assert expected in line, line
    assert "wrote nothing anywhere" in printed.out
    assert CANARY not in printed.out + printed.err


def test_a_required_value_absent_at_the_source_refuses_both_modes_before_any_write(
    rig: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = next(s for s in declared() if s["required"] and not is_operator_supplied(s))
    del Stores.values[
        (SOURCE_URL, SOURCE_PROJECT, missing["provider_path"], missing["provider_key"])
    ]
    for mode in ("rehome-check", "rehome"):
        Stores.events = []
        assert run(rig, mode) == 7, mode
        printed = capsys.readouterr()
        assert f"{missing['name']}" in printed.err and "ABSENT (required)" in printed.out
        assert not [e for e in Stores.events if e[0].startswith("control.")], (
            f"{mode} contacted the destination after finding a required value absent"
        )
    assert rig.FILESYSTEM == []


def test_a_host_still_naming_the_recorded_store_or_no_state_is_refused_before_any_read(
    rig: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    host = yaml.safe_load(rig.HOST.read_text(encoding="utf-8"))
    host["infisical"]["api_url"] = SOURCE_URL
    host["infisical"]["organization_slug"] = "example-team"
    rig.HOST.write_text(yaml.safe_dump(host), encoding="utf-8")
    assert run(rig, "rehome") == 7
    assert "nothing to move" in capsys.readouterr().err
    assert Stores.events == [], "a provider was contacted before the refusal"

    rig.read_state = lambda key: None
    assert run(rig, "rehome-check") == 3
    assert "no recorded state" in capsys.readouterr().err
    assert Stores.events == [] and rig.FILESYSTEM == []


def test_a_destination_that_already_has_the_project_is_refused_before_any_value_is_written(
    rig: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    Stores.existing_slugs = {KEY}
    assert run(rig, "rehome") == 7
    assert destination_writes() == [("control.create_project", KEY)], destination_writes()
    assert rig.FILESYSTEM == []
    assert "HTTP 400" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# The move
# ---------------------------------------------------------------------------


def test_the_move_writes_in_order_and_switches_only_after_every_value_reads_back(
    rig: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(rig, "rehome") == 0
    present = [s for s in declared() if s["name"] != OPTIONAL]

    kinds = [event[0] for event in destination_writes()]
    assert kinds[0] == "control.create_project"
    assert kinds[1 : 1 + 2 * len(present)] == [
        "control.ensure_folder",
        "control.create_secret",
    ] * len(present)
    assert kinds[1 + 2 * len(present) :] == [
        "control.create_identity",
        "control.attach_universal_auth",
        "control.create_client_secret",
        "control.grant",
    ]
    copied = {key: value for key, value in Stores.values.items() if key[0] == DESTINATION_URL}
    assert len(copied) == len(present)
    for secret in present:
        value, _times = copied[
            (DESTINATION_URL, DESTINATION_PROJECT, secret["provider_path"], secret["provider_key"])
        ]
        assert value == f"{CANARY}-{secret['name']}", "a copied value is not the source's value"

    read_back = [e for e in Stores.events if e[0] == "reader.read" and e[1] == DESTINATION_URL]
    assert len(read_back) == len(present), "not every value was read back"
    assert ("reader.login", DESTINATION_URL, "client-new") in Stores.events, (
        "the read-back was not made as the NEW runtime identity"
    )

    paths = bootstrap_state.credential_paths(KEY)
    state_file = rig.state_path(KEY)
    sequence = [(kind, path) for kind, path, _ in rig.FILESYSTEM]
    pending = [
        ("write", f"{paths['client_secret_path']}.rehome-pending"),
        ("write", f"{paths['client_id_path']}.rehome-pending"),
    ]
    assert sequence[:2] == pending, sequence
    moves = [entry for entry in rig.FILESYSTEM if entry[0] == "move"]
    assert moves[0][1] == str(state_file) and ".rehomed-" in moves[0][2]
    assert {
        (source, destination.split(".rehomed-")[0]) for _, source, destination in moves[1:3]
    } == {(raw, raw) for raw in paths.values()}
    assert {(source, destination) for _, source, destination in moves[3:5]} == {
        (f"{raw}.rehome-pending", raw) for raw in paths.values()
    }
    after = [path for kind, path in sequence[2 + len(moves) :]]
    assert after[0] == str(state_file), (
        "the new state was not the first thing written after the switch"
    )
    assert after[1].endswith(secret_age.CARRIED_AGES) and "rehome-" in Path(after[2]).name

    new_state = json.loads(written(rig)[str(state_file)][0])
    bootstrap_state.validate_state(new_state)
    assert new_state["api_url"] == DESTINATION_URL
    assert new_state["organization_slug"] == "agentic-postgres"
    assert new_state["infisical_project_id"] == DESTINATION_PROJECT
    assert new_state["runtime_identity_id"] == "identity-new"
    assert new_state["provider_inputs_sha256"] == bootstrap_state.provider_inputs_digest(
        load_project_manifest(REPO_ROOT / "project.example.yaml"), load_host_manifest(rig.HOST)
    ), "a --plan after the move would propose changes"
    managed = set(new_state["managed_resources"])
    assert {"project", "runtime_identity", "runtime_client_secret"} <= managed
    for secret in present:
        assert (secret["name"] in managed) == (
            secret["required"] and not is_operator_supplied(secret)
        ), f"{secret['name']}: managed_resources is not what --apply would record"
    out = capsys.readouterr().out
    assert "were NOT changed" in out and SOURCE_PROJECT in out


def test_a_copy_that_reads_back_differently_exits_six_and_leaves_this_host_untouched(
    rig: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    Stores.corrupt = next(s for s in declared() if s["name"] != OPTIONAL)["provider_key"]
    assert run(rig, "rehome") == 6
    printed = capsys.readouterr()

    kinds = [kind for kind, _, _ in rig.FILESYSTEM]
    assert "move" not in kinds, "a file was switched after a failed read-back"
    state_file = str(rig.state_path(KEY))
    assert state_file not in written(rig), "a state was written after a failed read-back"
    removed = {path for kind, path, _ in rig.FILESYSTEM if kind == "remove"}
    assert removed == {
        f"{raw}.rehome-pending" for raw in bootstrap_state.credential_paths(KEY).values()
    }
    assert ("control.revoke", "identity-new") in Stores.events
    assert DESTINATION_PROJECT in printed.out, "the new store's ids were not printed (D1046)"
    assert "differs from the source" in printed.err
    assert CANARY not in printed.out + printed.err


def test_no_value_reaches_stdout_stderr_the_state_the_record_or_the_carried_file(
    rig: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(rig, "rehome") == 0
    printed = capsys.readouterr()
    assert CANARY not in printed.out + printed.err
    for path, (content, mode) in written(rig).items():
        assert CANARY not in content, f"{path} holds a value"
        if path.endswith(".rehome-pending"):
            assert mode == 0o400, (path, oct(mode))
        else:
            assert mode == 0o600, (path, oct(mode))


def test_the_carried_ages_are_the_sources_times_and_a_second_move_keeps_the_first(
    rig: Any,
) -> None:
    assert run(rig, "rehome") == 0
    carried_file = next(p for p in written(rig) if p.endswith(secret_age.CARRIED_AGES))
    document = json.loads(written(rig)[carried_file][0])
    times = secret_age.parse_carried(document, project_key=KEY)
    present = [s for s in declared() if s["name"] != OPTIONAL]
    assert set(times) == {s["name"] for s in present}
    expected = datetime.fromisoformat(SOURCE_TIME).isoformat()
    assert {t.updated_at for t in times.values()} == {expected}
    assert document["source"] == {"api_url": SOURCE_URL, "project_id": SOURCE_PROJECT}

    earlier = SecretTimes(version=1, created_at=None, updated_at="2026-01-01T00:00:00+00:00")
    later = secret_age.carried_document(
        project_key=KEY,
        rehomed_at="2026-12-01T00:00:00Z",
        source_api_url=DESTINATION_URL,
        source_project_id=DESTINATION_PROJECT,
        times={
            "app_runtime_password": SecretTimes(
                version=1, created_at=None, updated_at="2026-10-10T00:00:00+00:00"
            )
        },
        previous={"app_runtime_password": earlier},
    )
    second = secret_age.parse_carried(later, project_key=KEY)
    assert second["app_runtime_password"].updated_at == earlier.updated_at, (
        "a second move replaced the first move's carried time with its own date"
    )


# ---------------------------------------------------------------------------
# The age reads the carried answer
# ---------------------------------------------------------------------------


NOW = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("version", "outcome", "source"),
    [
        (1, secret_age.OVERDUE, secret_age.CARRIED),
        (2, secret_age.OK, secret_age.PROVIDER),
        (None, secret_age.UNKNOWN, None),
    ],
)
def test_a_moved_secret_reads_its_carried_age_until_it_is_replaced(
    version: int | None, outcome: str, source: str | None
) -> None:
    """D2276. At the new store the move wrote version 1 a few days ago; the
    value is in truth 119 days old. Replaced since (version 2), the provider's
    own time is the truth; no version, and which one answers cannot be told."""
    moved = SecretTimes(
        version=version, created_at=None, updated_at=(NOW - timedelta(days=3)).isoformat()
    )
    carried = SecretTimes(
        version=1, created_at=None, updated_at=(NOW - timedelta(days=119)).isoformat()
    )
    age = secret_age.judge("app_runtime_password", 90, moved, now=NOW, carried=carried)
    assert (age.outcome, age.source) == (outcome, source), age
    if source == secret_age.CARRIED:
        assert age.age_days == 119 and "carried" in age.reason


def test_a_carried_file_that_is_not_one_the_rehome_wrote_is_refused() -> None:
    good = secret_age.carried_document(
        project_key=KEY,
        rehomed_at="2026-10-10T00:00:00Z",
        source_api_url=SOURCE_URL,
        source_project_id=SOURCE_PROJECT,
        times={
            "app_runtime_password": SecretTimes(version=1, created_at=None, updated_at=SOURCE_TIME)
        },
    )
    assert secret_age.parse_carried(good, project_key=KEY)
    for broken in (
        {**good, "kind": "something_else"},
        {**good, "project_key": "another-dev"},
        {**good, "entries": [{**good["entries"][0], "secretValue": "x"}]},
        {**good, "entries": [good["entries"][0], good["entries"][0]]},
        {
            **good,
            "entries": [
                {
                    "name": "x",
                    "created_at": None,
                    "updated_at": None,
                    "version": None,
                    "app_password": "v",
                }
            ],
        },
    ):
        with pytest.raises(secret_age.CarriedAgesError):
            secret_age.parse_carried(broken, project_key=KEY)


def test_the_doctor_reads_the_carried_age_and_reports_an_unreadable_file_for_every_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller that has to get the decision (§7's fifth question): the
    doctor's own reading, with the provider replaced at the reader."""
    spec = importlib.util.spec_from_file_location(
        "_apg_doctor_rehome", REPO_ROOT / "bin" / "doctor.py"
    )
    assert spec and spec.loader
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)
    monkeypatch.setattr(
        doctor.host_config,
        "load_host_manifest",
        lambda _path: {"infisical": {"api_url": DESTINATION_URL}},
    )
    monkeypatch.setattr(
        doctor.bootstrap_state,
        "load_state",
        lambda _path: {"infisical_project_id": DESTINATION_PROJECT, "environment_slug": "dev"},
    )
    moved_at = (NOW - timedelta(days=3)).isoformat()

    class MovedStore:
        def __init__(self, api_url: str) -> None:
            pass

        def login(self, credential: Any) -> None:
            pass

        def read_secret_times(self, **_: Any) -> SecretTimes:
            return SecretTimes(version=1, created_at=moved_at, updated_at=moved_at)

        def logout(self) -> None:
            pass

    monkeypatch.setattr(
        doctor.infisical_client.Credential, "from_files", classmethod(lambda cls, a, b: None)
    )
    document = {"deployed_through_session": CURRENT_SESSION, "project": {"key": KEY}}

    root = tmp_path / "projects"
    (root / KEY).mkdir(parents=True)
    unmoved = doctor.probe_secret_ages(KEY, document, root=root, client_factory=MovedStore, now=NOW)
    assert {age.outcome for age in unmoved} == {secret_age.OK}, (
        "with no carried file the move's date answers"
    )

    old = (NOW - timedelta(days=119)).isoformat()
    carried = secret_age.carried_document(
        project_key=KEY,
        rehomed_at=moved_at,
        source_api_url=SOURCE_URL,
        source_project_id=SOURCE_PROJECT,
        times={age.name: SecretTimes(version=3, created_at=old, updated_at=old) for age in unmoved},
    )
    (root / KEY / secret_age.CARRIED_AGES).write_text(json.dumps(carried), encoding="utf-8")
    ages = doctor.probe_secret_ages(KEY, document, root=root, client_factory=MovedStore, now=NOW)
    assert {(age.outcome, age.source, age.age_days) for age in ages} == {
        (secret_age.OVERDUE, secret_age.CARRIED, 119)
    }

    (root / KEY / secret_age.CARRIED_AGES).write_text("{not json", encoding="utf-8")
    broken = doctor.probe_secret_ages(KEY, document, root=root, client_factory=MovedStore, now=NOW)
    assert {age.outcome for age in broken} == {secret_age.UNKNOWN}
    assert all(secret_age.CARRIED_AGES in age.reason for age in broken)


# ---------------------------------------------------------------------------
# The kit carries the file when there is one
# ---------------------------------------------------------------------------


def test_the_kit_carries_the_ages_when_the_host_has_them_and_verifies_without_them(
    tmp_path: Path,
) -> None:
    from tests.contract import test_disaster_kit as kit

    rendered_path = REPO_ROOT / ".generated" / KEY / "outputs.json"
    if not rendered_path.exists():
        pytest.skip("fixtures are not rendered in this working tree")
    rendered = json.loads(rendered_path.read_text(encoding="utf-8"))
    state_root = tmp_path / "state"
    (state_root / KEY).mkdir(parents=True)
    (state_root / KEY / "bootstrap-state.json").write_text(
        json.dumps(kit.state_document()), encoding="utf-8"
    )
    (state_root / KEY / "outputs.json").write_text(
        json.dumps(kit.deployed_document(rendered)), encoding="utf-8"
    )
    contract = load_secret_contract(REPO_ROOT / "secrets.required.yaml")

    def export() -> list[dr_kit.KitEntry]:
        return dr_kit.plan_export(
            host_path=REPO_ROOT / "host.example.yaml",
            capabilities_path=REPO_ROOT / "capabilities.example.yaml",
            project_paths=(REPO_ROOT / "project.example.yaml",),
            state_root=state_root,
            contract=contract,
            session=kit.SESSION,
        )

    without = export()
    assert not [e for e in without if e.relative.endswith(dr_kit.CARRIED_AGES)]
    assert dr_kit.verify_kit(kit.write_kit(without, tmp_path / "kit-without")) == []

    carried = secret_age.carried_document(
        project_key=KEY,
        rehomed_at="2026-10-10T00:00:00Z",
        source_api_url=SOURCE_URL,
        source_project_id=SOURCE_PROJECT,
        times={
            "app_runtime_password": SecretTimes(
                version=3, created_at=SOURCE_TIME, updated_at=SOURCE_TIME
            )
        },
    )
    (state_root / KEY / dr_kit.CARRIED_AGES).write_text(json.dumps(carried), encoding="utf-8")
    with_ages = export()
    relative = f"projects/{KEY}/{dr_kit.CARRIED_AGES}"
    assert [e.relative for e in with_ages if e.relative.endswith(dr_kit.CARRIED_AGES)] == [relative]
    directory = kit.write_kit(with_ages, tmp_path / "kit-with")
    assert dr_kit.verify_kit(directory) == []

    (directory / relative).write_text(
        json.dumps({**carried, "project_key": "another-dev"}), encoding="utf-8"
    )
    problems = dr_kit.verify_kit(directory)
    assert any("digest mismatch" in p for p in problems) and any(
        "another-dev" in p for p in problems
    )


# ---------------------------------------------------------------------------
# The wrapper and its usage
# ---------------------------------------------------------------------------


def test_the_wrapper_admits_both_modes_with_root_and_the_new_stores_credential() -> None:
    source = (REPO_ROOT / "bin" / "bootstrap-providers.sh").read_text(encoding="utf-8")
    assert "--rehome-check|--rehome)" in source
    branch = source[source.index("    rehome-check|rehome)") :]
    branch = branch[: branch.index(";;")]
    assert '[ "$(id -u)" -eq 0 ] || die 3' in branch, "the modes do not require root"
    assert '[ -n "${OPERATOR_CREDENTIAL}" ] || die 2' in branch
    docs = (REPO_ROOT / "docs" / "provider-bootstrap.md").read_text(encoding="utf-8")
    assert "--rehome-check" in docs and "--rehome " in docs, (
        "the runbook does not document the move"
    )


def test_the_usage_names_every_flag_each_mode_requires() -> None:
    """D2272: `--destroy` refuses without `--operator-credential-file`, and its
    usage line did not name it. Each synopsis line now carries every flag its
    mode refuses to run without."""
    import subprocess

    result = subprocess.run(
        [str(REPO_ROOT / "bin" / "bootstrap-providers.sh"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    synopsis = result.stdout[: result.stdout.index("\n\n")]
    entries = synopsis.replace("\\\n", " ").split("bin/bootstrap-providers.sh")[1:]
    required = {
        "--apply": ["--operator-credential-file"],
        "--destroy": ["--confirm", "--operator-credential-file"],
        "--adopt": ["--state", "--operator-credential-file"],
        "--rehome-check": ["--operator-credential-file"],
        "--rehome ": ["--operator-credential-file"],
    }
    for mode, flags in required.items():
        line = next(
            (
                entry
                for entry in entries
                if f"{mode.strip()} " in entry + " "
                and (mode != "--rehome " or "--rehome-check" not in entry)
            ),
            None,
        )
        assert line is not None, f"no synopsis line for {mode.strip()}"
        for flag in flags:
            assert flag in line, f"the {mode.strip()} synopsis omits {flag}: {line.split()}"

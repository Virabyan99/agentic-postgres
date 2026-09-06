"""`REC-KIT-001` and `REC-KIT-002`, offline (ADR 0189, Session 18 Run 3).

The kit: `dr_kit.plan_export` over a state root a proof controls, the sentinel
planted in a secret generation and asserted absent from every file the kit
holds, `verify` refusing a kit missing any artifact or holding one that was
altered, and the command's own refusals. The adoption: `bootstrap-providers.py
--mode adopt` driven against a recorded control plane that answers BY ID and
records every call, so that "never searches by name" is a property of the
calls made rather than of the source text.

Nothing here contacts a provider, needs root, or opens a real generation.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, ClassVar

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT, bootstrap_state, deployed_output, dr_kit
from agentic_postgres.secrets_contract import load_secret_contract

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "fixture-alpha-dev"
SENTINEL = f"APG-SECRET-CANARY-{uuid.uuid4().hex}"
RECORDED_PROJECT = "3f5c0f4a-2b0f-4f9a-9a4d-1c1f0e2d3a4b"
ORGANISATION = "00000000-0000-4000-8000-000000000000"
#: The session the mirror pair is declared at (Run 5 bumps CURRENT_SESSION).
SESSION = 18


def load_command(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"apg_{name}", REPO_ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return load_secret_contract(REPO_ROOT / "secrets.required.yaml")


@pytest.fixture(scope="module")
def rendered() -> dict[str, Any]:
    path = REPO_ROOT / ".generated" / KEY / "outputs.json"
    if not path.exists():
        pytest.skip("fixtures are not rendered in this working tree")
    return json.loads(path.read_text(encoding="utf-8"))


def state_document(key: str = KEY, **overrides: Any) -> dict[str, Any]:
    document = {
        "schema_version": 1,
        "project_key": key,
        "project_manifest_sha256": "a" * 64,
        "provider_inputs_sha256": "b" * 64,
        "provider": "infisical",
        "api_url": "https://app.infisical.com",
        "organization_slug": "example-team",
        "infisical_project_id": RECORDED_PROJECT,
        "environment_slug": "dev",
        "runtime_folder": "/runtime",
        "runtime_identity_id": "idn-0123456789",
        "runtime_client_id": "cli-0123456789",
        "active_client_secret_id": "sec-0123456789",
        "credential_files": bootstrap_state.credential_paths(key),
        "managed_resources": ["project", "runtime_identity", "runtime_client_secret"],
        "created_at": "2026-08-04T10:00:00Z",
        "updated_at": "2026-08-04T10:00:00Z",
    }
    document.update(overrides)
    return document


def deployed_document(rendered: dict[str, Any]) -> dict[str, Any]:
    """A schema-valid deployed document for the fixture, the way the deploy builds one."""
    return deployed_output.build_deployed_document(
        rendered=rendered,
        source_commit="c" * 40,
        health_status="ready",
        rest_status="unavailable",
        docs_status="unavailable",
        app_status="unavailable",
        app_docs_status="unavailable",
        storage_status="unavailable",
        mcp_status="unavailable",
        metrics_status="unavailable",
        api=deployed_output.API_NOT_PUBLISHED,
        jwt=deployed_output.JWT_NOT_PUBLISHED,
        mcp=deployed_output.MCP_NOT_PUBLISHED,
        deployed_through_session=CURRENT_SESSION,
        host={
            "id": "apg-vps-01",
            "os_release": "26.04",
            "public_ipv4": "203.0.113.10",
            "public_ipv6": None,
        },
        edge={
            "stack_name": "apg-edge",
            "control_network": "apg-edge_control",
            "egress_network": "apg-edge_egress",
            "project_network_attached": True,
        },
        tls={
            "status": "issued",
            "acme_environment": "staging",
            "resolver": "letsencrypt-staging",
            "certificate_sha256": "c" * 64,
            "not_before": "2026-08-05T00:00:00Z",
            "not_after": "2026-11-03T00:00:00Z",
        },
        bootstrap={
            "status": "complete",
            "state_path": f"/etc/agentic-postgres/projects/{KEY}/bootstrap-state.json",
            "infisical_project_id": RECORDED_PROJECT,
            "runtime_identity_id": "idn-0123456789",
        },
        secrets={
            "status": "ready",
            "generation_id": "k7f2p9qd",
            "generation_manifest": (
                f"/var/lib/agentic-postgres/secrets/{KEY}/generations/k7f2p9qd/manifest.json"
            ),
            "required_names": rendered["secrets"]["required_names"],
            "fresh": True,
            "materialized_at": "2026-08-05T18:00:00Z",
        },
        runtime={
            "release_path": "/opt/agentic-postgres/releases/" + "c" * 40,
            "state_directory": f"/etc/agentic-postgres/projects/{KEY}",
            "compose_model_sha256": "d" * 64,
        },
        database_observed={
            "status": "observed",
            "server_version": "18.4",
            "extensions": {"vector": "0.8.6", "plpgsql": "1.0"},
            "memory": {"anon_mb": 62, "shmem_mb": 140, "file_mb": 410},
            "instance_uuid": "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f",
        },
    )


@pytest.fixture
def host(tmp_path: Path, rendered: dict[str, Any]) -> dict[str, Path]:
    """A host as the kit finds it: the state root with a bootstrap state and a
    deployed document per project, and a secret generation holding the
    SENTINEL -- which the kit must never open."""
    state_root = tmp_path / "state"
    (state_root / KEY).mkdir(parents=True)
    (state_root / KEY / "bootstrap-state.json").write_text(
        json.dumps(state_document()), encoding="utf-8"
    )
    (state_root / KEY / "outputs.json").write_text(
        json.dumps(deployed_document(rendered)), encoding="utf-8"
    )
    secrets = tmp_path / "secrets" / KEY / "generations" / "k7f2p9qd" / "postgres"
    secrets.mkdir(parents=True)
    (secrets / "10-repo1-s3-key.conf").write_text(
        f"[global]\nrepo1-s3-key={SENTINEL}\n", encoding="utf-8"
    )
    return {"state_root": state_root, "secrets": tmp_path / "secrets"}


def export(host: dict[str, Path], contract: dict[str, Any]) -> list[dr_kit.KitEntry]:
    return dr_kit.plan_export(
        host_path=REPO_ROOT / "host.example.yaml",
        capabilities_path=REPO_ROOT / "capabilities.example.yaml",
        project_paths=(REPO_ROOT / "project.example.yaml",),
        state_root=host["state_root"],
        contract=contract,
        session=SESSION,
    )


def write_kit(entries: list[dr_kit.KitEntry], directory: Path) -> Path:
    for entry in entries:
        path = directory / entry.relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(entry.content)
    manifest = dr_kit.kit_manifest(
        entries, exported_at="2026-09-05T20:00:00Z", release="c" * 40, session=SESSION
    )
    (directory / dr_kit.KIT_MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return directory


# ---------------------------------------------------------------------------
# The kit
# ---------------------------------------------------------------------------


def test_the_kit_holds_every_artifact_the_runbook_names_and_nothing_it_did_not_validate(
    host: dict[str, Path], contract: dict[str, Any]
) -> None:
    entries = export(host, contract)
    names = sorted(entry.relative for entry in entries)
    assert names == [
        dr_kit.CAPABILITIES_MANIFEST,
        dr_kit.HOST_MANIFEST,
        *sorted(f"projects/{KEY}/{artifact}" for artifact in dr_kit.PROJECT_ARTIFACTS),
    ]
    # Every copied file is the file it came from, byte for byte; the listing is
    # the one generated file.
    for entry in entries:
        if entry.source is not None:
            assert entry.content == entry.source.read_bytes()
    listing = next(e for e in entries if e.relative.endswith(dr_kit.SECRETS_LISTING))
    assert listing.source is None
    assert "backup_r2_access_key_id  /backup/APG_BACKUP_R2_ACCESS_KEY_ID  operator_supplied" in (
        listing.content.decode()
    )
    assert "mirror_s3_access_key_id" not in listing.content.decode(), (
        "the example project has no mirror; the listing is the project's view (ADR 0191)"
    )


def test_the_kit_carries_no_value_the_host_holds(
    host: dict[str, Path], contract: dict[str, Any], tmp_path: Path
) -> None:
    """The sentinel is in a materialized secret file on the host; no artifact
    of the kit contains it, and no artifact contains any line shaped like a
    value assignment from a generation."""
    assert SENTINEL in (
        host["secrets"] / KEY / "generations" / "k7f2p9qd" / "postgres" / "10-repo1-s3-key.conf"
    ).read_text(encoding="utf-8"), "the sentinel was not planted; this test reads nothing"
    entries = export(host, contract)
    for entry in entries:
        assert SENTINEL.encode() not in entry.content, f"{entry.relative} carries the sentinel"
        assert b"repo1-s3-key=" not in entry.content, f"{entry.relative} carries a key line"
    source = (REPO_ROOT / "src" / "agentic_postgres" / "dr_kit.py").read_text(encoding="utf-8")
    assert "generations" not in source and "SECRET_ROOT" not in source, (
        "the kit module knows where generations live; it must not"
    )


def test_a_kit_verifies_whole_and_refuses_a_missing_or_altered_artifact(
    host: dict[str, Path], contract: dict[str, Any], tmp_path: Path
) -> None:
    kit = write_kit(export(host, contract), tmp_path / "kit")
    assert dr_kit.verify_kit(kit) == []

    altered = shutil.copytree(kit, tmp_path / "altered")
    state = altered / "projects" / KEY / dr_kit.BOOTSTRAP_STATE
    document = json.loads(state.read_text(encoding="utf-8"))
    document["infisical_project_id"] = "not-the-recorded-one"
    state.write_text(json.dumps(document), encoding="utf-8")
    problems = dr_kit.verify_kit(altered)
    assert any("digest mismatch" in p and dr_kit.BOOTSTRAP_STATE in p for p in problems), problems

    missing = shutil.copytree(kit, tmp_path / "missing")
    (missing / "projects" / KEY / dr_kit.SECRETS_LISTING).unlink()
    problems = dr_kit.verify_kit(missing)
    assert any("missing artifact" in p and dr_kit.SECRETS_LISTING in p for p in problems), problems

    renamed = shutil.copytree(kit, tmp_path / "renamed")
    manifest = json.loads((renamed / dr_kit.KIT_MANIFEST).read_text(encoding="utf-8"))
    del manifest["artifacts"][f"projects/{KEY}/{dr_kit.DEPLOYED_DOCUMENT}"]
    (renamed / dr_kit.KIT_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    problems = dr_kit.verify_kit(renamed)
    assert any(dr_kit.DEPLOYED_DOCUMENT in p and "not in the kit" in p for p in problems), problems

    assert dr_kit.verify_kit(tmp_path / "nowhere")[0].startswith("no kit.json")


def test_a_project_directory_naming_another_project_is_refused(
    host: dict[str, Path], contract: dict[str, Any], tmp_path: Path
) -> None:
    """The state, the document and the manifest must all derive the directory's
    key: a kit that restores the wrong project under a key is the failure the
    whole kit exists to prevent."""
    kit = write_kit(export(host, contract), tmp_path / "kit")
    other = json.loads((kit / "projects" / KEY / dr_kit.BOOTSTRAP_STATE).read_text())
    other["project_key"] = "someone-else-dev"
    other["credential_files"] = bootstrap_state.credential_paths("someone-else-dev")
    (kit / "projects" / KEY / dr_kit.BOOTSTRAP_STATE).write_text(json.dumps(other))
    manifest = json.loads((kit / dr_kit.KIT_MANIFEST).read_text(encoding="utf-8"))
    manifest["artifacts"][f"projects/{KEY}/{dr_kit.BOOTSTRAP_STATE}"] = dr_kit.KitEntry(
        "x", json.dumps(other).encode()
    ).sha256
    (kit / dr_kit.KIT_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    problems = dr_kit.verify_kit(kit)
    assert any("records 'someone-else-dev'" in p for p in problems), problems


def test_an_export_refuses_a_project_with_no_recorded_bootstrap_or_no_deployed_document(
    host: dict[str, Path], contract: dict[str, Any]
) -> None:
    (host["state_root"] / KEY / "outputs.json").unlink()
    with pytest.raises(dr_kit.KitError, match="no valid deployed document"):
        export(host, contract)
    (host["state_root"] / KEY / "bootstrap-state.json").unlink()
    with pytest.raises(dr_kit.KitError, match="no provider ids to adopt by"):
        export(host, contract)


def test_the_command_writes_owner_only_refuses_an_existing_directory_and_verifies(
    host: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    command = load_command("dr-kit")
    output = tmp_path / "kit"
    argv = [
        "export",
        "--host",
        str(REPO_ROOT / "host.example.yaml"),
        "--capabilities",
        str(REPO_ROOT / "capabilities.example.yaml"),
        "--project",
        str(REPO_ROOT / "project.example.yaml"),
        "--output",
        str(output),
        "--state-root",
        str(host["state_root"]),
        "--session",
        "18",
    ]
    assert command.main(argv) == 0
    assert oct(output.stat().st_mode & 0o777) == "0o700"
    for path in output.rglob("*"):
        if path.is_file():
            assert oct(path.stat().st_mode & 0o777) == "0o600", path
    out = capsys.readouterr().out
    assert "no value is in it" in out and f"projects/{KEY}/{dr_kit.SECRETS_LISTING}" in out
    assert command.main(["verify", str(output)]) == 0
    assert "verifies" in capsys.readouterr().out

    assert command.main(argv) == 2, "an existing directory must be refused, not overwritten"
    (output / "projects" / KEY / dr_kit.SECRETS_LISTING).unlink()
    assert command.main(["verify", str(output)]) == 5


def test_the_wrapper_needs_root_for_export_unless_a_state_root_is_given() -> None:
    source = (REPO_ROOT / "bin" / "dr-kit.sh").read_text(encoding="utf-8")
    assert "export needs root" in source and "--state-root" in source
    assert "verify)" in source


# ---------------------------------------------------------------------------
# Adoption
# ---------------------------------------------------------------------------


class _RecordedControlPlane:
    """Answers BY ID only, and records every method it was asked for."""

    calls: ClassVar[list[tuple[str, tuple[Any, ...]]]] = []
    projects: ClassVar[dict[str, dict[str, Any]]] = {}

    @classmethod
    def login(cls, api_url: str, client_id: str, client_secret: str) -> _RecordedControlPlane:
        cls.calls.append(("login", (api_url,)))
        return cls()

    def get_project(self, project_id: str) -> dict[str, Any]:
        type(self).calls.append(("get_project", (project_id,)))
        if project_id not in type(self).projects:
            raise bootstrap_state.BootstrapStateError(
                f"GET /api/v1/workspace/{project_id} failed with HTTP 404"
            )
        return type(self).projects[project_id]

    def create_identity(self, name: str, organization_id: str) -> str:
        type(self).calls.append(("create_identity", (name, organization_id)))
        return "identity-new"

    def attach_universal_auth(self, identity_id: str) -> str:
        type(self).calls.append(("attach_universal_auth", (identity_id,)))
        return "client-new"

    def create_client_secret(self, identity_id: str, description: str) -> tuple[str, str]:
        type(self).calls.append(("create_client_secret", (identity_id,)))
        return ("secret-id-new", "client-secret-value")

    def grant_project_access(self, project_id: str, identity_id: str, role: str) -> None:
        type(self).calls.append(("grant_project_access", (project_id, identity_id, role)))

    def revoke_identity(self, identity_id: str) -> None:
        type(self).calls.append(("revoke_identity", (identity_id,)))

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"adoption called {name}, which is not a by-id operation")


@pytest.fixture
def bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = load_command("bootstrap-providers")
    module.ControlPlane = _RecordedControlPlane
    _RecordedControlPlane.calls = []
    _RecordedControlPlane.projects = {
        RECORDED_PROJECT: {"id": RECORDED_PROJECT, "orgId": ORGANISATION}
    }
    written: dict[str, Any] = {}

    def capture(path: Path, content: str, *, mode: int) -> None:
        written[str(path)] = (content, mode)

    module.write_private = capture
    module.state_path = lambda key: tmp_path / f"{key}-state.json"
    module.read_state = lambda key: None
    module.WRITTEN = written
    credential = tmp_path / "operator.cred"
    credential.write_text("client-id-line\nclient-secret-line\n", encoding="utf-8")
    module.CREDENTIAL = credential
    return module


def adopt(bootstrap: Any, state_file: Path, *extra: str) -> int:
    """`fail()` raises SystemExit with the code; a return is the success path."""
    try:
        return bootstrap.main(
            [
                "--host",
                str(REPO_ROOT / "host.example.yaml"),
                "--project",
                str(REPO_ROOT / "project.example.yaml"),
                "--mode",
                "adopt",
                "--state",
                str(state_file),
                "--operator-credential-file",
                str(bootstrap.CREDENTIAL),
                "--session",
                "18",
                *extra,
            ]
        )
    except SystemExit as stop:
        return int(stop.code)


def recorded_state(bootstrap: Any, tmp_path: Path, **overrides: Any) -> Path:
    """The kit's state, with the provider inputs digest this host computes --
    the kit was exported from a host with the same manifests."""
    from agentic_postgres.config import load_project_manifest
    from agentic_postgres.host_config import load_host_manifest

    digest = bootstrap_state.provider_inputs_digest(
        load_project_manifest(REPO_ROOT / "project.example.yaml"),
        load_host_manifest(REPO_ROOT / "host.example.yaml"),
    )
    path = tmp_path / "kit-state.json"
    path.write_text(
        json.dumps(state_document(provider_inputs_sha256=digest, **overrides)), encoding="utf-8"
    )
    return path


def test_adoption_binds_by_the_recorded_id_and_never_looks_anything_up_by_name(
    bootstrap: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state = recorded_state(bootstrap, tmp_path)
    assert adopt(bootstrap, state) == 0
    calls = [name for name, _ in _RecordedControlPlane.calls]
    assert calls == [
        "login",
        "get_project",
        "create_identity",
        "attach_universal_auth",
        "create_client_secret",
        "grant_project_access",
    ], calls
    by_name = {name: args for name, args in _RecordedControlPlane.calls}
    assert by_name["get_project"] == (RECORDED_PROJECT,)
    assert by_name["grant_project_access"] == (RECORDED_PROJECT, "identity-new", "viewer")
    assert "create_project" not in calls, "adoption created a project"

    written = {path: content for path, (content, _) in bootstrap.WRITTEN.items()}
    new_state = json.loads(next(c for p, c in written.items() if p.endswith("-state.json")))
    bootstrap_state.validate_state(new_state)
    assert new_state["infisical_project_id"] == RECORDED_PROJECT
    assert new_state["runtime_identity_id"] == "identity-new"
    assert new_state["runtime_client_id"] == "client-new"
    assert new_state["active_client_secret_id"] == "secret-id-new"  # noqa: S105 -- an id
    assert "project" not in new_state["managed_resources"], "the project is not ours to destroy"
    assert set(new_state["managed_resources"]) == {
        "runtime_identity",
        "runtime_membership",
        "runtime_client_secret",
    }
    secret_files = [p for p in written if p.endswith("infisical-client-secret")]
    assert len(secret_files) == 1 and written[secret_files[0]] == "client-secret-value\n"
    out = capsys.readouterr().out
    assert "adopted project" in out and "idn-0123456789" in out and "NOT revoked" in out
    assert "client-secret-value" not in out


def test_a_recorded_project_that_does_not_exist_is_refused_without_a_search(
    bootstrap: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _RecordedControlPlane.projects = {}
    state = recorded_state(bootstrap, tmp_path)
    assert adopt(bootstrap, state) == 7
    calls = [name for name, _ in _RecordedControlPlane.calls]
    assert calls == ["login", "get_project"], "something was created or searched after the 404"
    err = capsys.readouterr().err
    assert "does not exist" in err and "searches by name" in err
    assert not any(p.endswith("-state.json") for p in bootstrap.WRITTEN), "a state was written"


def test_a_host_that_already_records_the_project_is_refused(
    bootstrap: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bootstrap.read_state = lambda key: state_document()
    assert adopt(bootstrap, recorded_state(bootstrap, tmp_path)) == 7
    assert _RecordedControlPlane.calls == [], "the provider was contacted before the refusal"
    assert "already records a bootstrap" in capsys.readouterr().err


def test_a_project_in_another_organisation_or_with_other_inputs_is_refused(
    bootstrap: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _RecordedControlPlane.projects[RECORDED_PROJECT]["orgId"] = "another-org"
    assert adopt(bootstrap, recorded_state(bootstrap, tmp_path)) == 7
    assert "organisation" in capsys.readouterr().err
    assert "create_identity" not in [n for n, _ in _RecordedControlPlane.calls]

    _RecordedControlPlane.calls = []
    _RecordedControlPlane.projects[RECORDED_PROJECT]["orgId"] = ORGANISATION
    other = tmp_path / "other-inputs.json"
    other.write_text(json.dumps(state_document(provider_inputs_sha256="e" * 64)), encoding="utf-8")
    assert adopt(bootstrap, other) == 7
    assert "provider inputs on this host differ" in capsys.readouterr().err
    assert _RecordedControlPlane.calls == [], "refused before any provider call"


def test_a_state_recording_another_project_is_refused(
    bootstrap: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path / "other.json"
    other.write_text(json.dumps(state_document(key="someone-else-dev")), encoding="utf-8")
    assert adopt(bootstrap, other) == 2
    assert "records 'someone-else-dev'" in capsys.readouterr().err


def test_adopt_needs_its_two_inputs(bootstrap: Any, tmp_path: Path) -> None:
    common = [
        "--host",
        str(REPO_ROOT / "host.example.yaml"),
        "--project",
        str(REPO_ROOT / "project.example.yaml"),
        "--mode",
        "adopt",
    ]
    with pytest.raises(SystemExit) as no_state:
        bootstrap.main([*common, "--operator-credential-file", str(bootstrap.CREDENTIAL)])
    assert no_state.value.code == 2
    with pytest.raises(SystemExit) as no_credential:
        bootstrap.main([*common, "--state", str(recorded_state(bootstrap, tmp_path))])
    assert no_credential.value.code == 2


def test_the_wrapper_admits_adopt_with_its_state_file_and_root() -> None:
    source = (REPO_ROOT / "bin" / "bootstrap-providers.sh").read_text(encoding="utf-8")
    assert "--plan|--apply|--destroy|--adopt)" in source
    assert "--adopt requires --state FILE" in source
    assert "--adopt requires root" in source
    assert 'arguments+=(--state "${STATE_FILE}")' in source
    docs = (REPO_ROOT / "docs" / "provider-bootstrap.md").read_text(encoding="utf-8")
    assert "--adopt" in docs, "the bootstrap runbook does not document adoption"


def test_the_control_plane_reads_a_project_by_id_at_the_documented_route() -> None:
    """The route is the one the API's own router declares (`GET /:projectId`
    under v1/workspace); nothing offline can prove the provider honours it,
    and the trip did (D1013). **The wrapper key the trip measured is
    `workspace`** (app.infisical.com, 2026-09-06, the first live `--adopt`),
    where the source's router declares `project` (D1026); both are read."""
    source = (REPO_ROOT / "bin" / "bootstrap-providers.py").read_text(encoding="utf-8")
    body = source.split("def get_project(")[1].split("\n    def ")[0]
    assert '"GET", f"/api/v1/workspace/{urllib.parse.quote(project_id)}"' in body
    assert 'payload.get("workspace")' in body and 'payload.get("project")' in body
    code = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith(("#", '"""'))
    )
    assert '"/api/v1/projects"' not in code and '"/api/v1/workspace"' not in code
    assert "?" not in code.split("_call(")[1].split(")")[0], "a query string is a search"


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        ({"workspace": {"id": "p-1", "orgId": "org-1"}}, "p-1"),
        ({"project": {"id": "p-1", "orgId": "org-1"}}, "p-1"),
        ({"workspace": {"orgId": "org-1"}, "project": {"id": "p-2"}}, "p-2"),
        ({}, None),
        ({"workspace": "p-1"}, None),
    ],
)
def test_get_project_reads_the_measured_wrapper_and_the_sources_and_refuses_neither(
    answer: dict[str, Any], outcome: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1026, behaviourally: the hosted service wraps the project under
    `workspace`, the source under `project`; a wrapper without an id is not a
    project, and a body with neither is the refusal that stopped the first
    live adoption. Driven through a recorded `_call`, so the one GET is the
    only call made."""
    module = load_command("bootstrap-providers")
    control = object.__new__(module.ControlPlane)
    calls: list[tuple[str, str]] = []

    def call(method: str, path: str, body: Any = None) -> dict[str, Any]:
        calls.append((method, path))
        return answer

    monkeypatch.setattr(control, "_call", call)
    if outcome is None:
        with pytest.raises(bootstrap_state.BootstrapStateError, match="returned no project"):
            control.get_project("2c146f6b-582c-4ce9-af87-4cef645c00c3")
    else:
        assert control.get_project("2c146f6b-582c-4ce9-af87-4cef645c00c3")["id"] == outcome
    assert calls == [("GET", "/api/v1/workspace/2c146f6b-582c-4ce9-af87-4cef645c00c3")]


def test_the_runbook_names_only_commands_that_exist() -> None:
    """D693's method for the node-loss runbook: every `bin/<x>.sh` it names is a
    file in the tree, and the four verbs this run adds are among them."""
    import re

    runbook = (REPO_ROOT / "docs" / "node-loss-runbook.md").read_text(encoding="utf-8")
    named = set(re.findall(r"bin/([a-z0-9-]+\.sh)", runbook))
    assert named, "the runbook names no command"
    for name in sorted(named):
        assert (REPO_ROOT / "bin" / name).is_file(), (
            f"the runbook names bin/{name}, which does not exist"
        )
    assert {"dr-kit.sh", "bootstrap-providers.sh", "restore.sh", "materialize-secrets.sh"} <= named
    assert (REPO_ROOT / "deploy.sh").is_file() and "sudo ./deploy.sh" in runbook
    assert "--adopt" in runbook and "--from mirror" in runbook
    deploy = "./deploy.sh --host host.yaml --project <manifest> --through-session <N>\n"
    assert runbook.index("bin/restore.sh --outputs") < runbook.index(deploy), (
        "the runbook deploys before it restores (D1008)"
    )
    assert "schedule enable" in runbook and "never" in runbook.lower()

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
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, ClassVar

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT, bootstrap_state, deployed_output, dr_kit
from agentic_postgres.config import ManifestError
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
        control_status="unavailable",
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


def test_every_directory_in_the_kit_is_owner_only(
    host: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D1856: every DIRECTORY is 0700 and every file 0600, walked whole.

    `mkdir(parents=True, mode=0o700)` gave the mode to the last directory only,
    so every kit carried `projects/` at 0755 under a 0700 root -- and the
    proof above walked files alone. Under a permissive umask too, because the
    host's is not this test's to assume.
    """
    command = load_command("dr-kit")
    output = tmp_path / "kit"
    previous = os.umask(0o022)
    try:
        assert (
            command.main(
                [
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
            )
            == 0
        )
    finally:
        os.umask(previous)
    capsys.readouterr()
    directories = [output, *(path for path in output.rglob("*") if path.is_dir())]
    assert output / "projects" in directories and output / "projects" / KEY in directories
    wrong = [
        f"{path.relative_to(tmp_path)} {oct(path.stat().st_mode & 0o777)}"
        for path in [*directories, *(p for p in output.rglob("*") if p.is_file())]
        if path.stat().st_mode & 0o777 != (0o700 if path.is_dir() else 0o600)
    ]
    assert not wrong, wrong


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


# ---------------------------------------------------------------------------
# An unreadable kit is not an invalid kit (D1052, ADR 0195)
# ---------------------------------------------------------------------------


def test_an_unreadable_directory_is_not_reported_as_not_a_kit(tmp_path: Path) -> None:
    """D1052. The export runs as root and wrote the kit 0700/0600 into the
    operator's own home, then told that operator to copy it off the host.

    Running the verb documented as needing no root produced *"this is not a
    kit"* -- a definite claim about the artifact, when the truth was a fact
    about access. An operator who has just watched `export` succeed and is then
    told the result is not a kit goes looking for a broken export, which is the
    one place the fault is not.
    """
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / dr_kit.KIT_MANIFEST).write_text("{}", encoding="utf-8")

    kit.chmod(0o000)
    try:
        if os.geteuid() == 0:  # pragma: no cover - root ignores the mode
            pytest.skip("running as root; a mode cannot make this unreadable")
        problems = dr_kit.verify_kit(kit)
    finally:
        kit.chmod(0o700)

    assert problems, "an unreadable kit reported no problems at all"
    joined = " ".join(problems)
    assert "this is not a kit" not in joined, (
        "an unreadable directory was reported as not being a kit: " + joined
    )
    assert "permission denied" in joined.lower(), joined
    # The remedy, named. A refusal that does not say what to do next is where an
    # operator stops.
    assert "sudo" in joined.lower(), joined


def test_a_directory_that_really_is_not_a_kit_still_says_so(tmp_path: Path) -> None:
    """The paired control. A check that answered "permission denied" to
    everything would satisfy the test above and lose the property the message
    exists for."""
    empty = tmp_path / "not-a-kit"
    empty.mkdir()
    problems = dr_kit.verify_kit(empty)
    assert problems == [f"no {dr_kit.KIT_MANIFEST} in {empty}; this is not a kit"], problems


def test_the_export_hands_the_kit_to_the_operator_it_instructs() -> None:
    """The export's closing line tells the operator to carry the kit away, and
    until this session the kit was root-owned, so they could not.

    Asserted against the source rather than by running a root export, which no
    contract test may do. What is asserted is that the handover exists, reads
    the operator from the host manifest rather than guessing a name, and does
    not touch the modes -- the kit stays 0700/0600 whoever owns it.
    """
    source = (REPO_ROOT / "bin" / "dr-kit.py").read_text(encoding="utf-8")
    assert "_hand_to_operator" in source
    handover = source[source.index("def _hand_to_operator") :]
    assert "operator_user" in handover, "the handover invents an owner instead of reading one"
    assert "os.chown" in handover
    assert "chmod" not in handover, "the handover changes modes; only ownership may move"
    assert "os.geteuid() != 0" in handover, "a non-root export must not attempt a chown"


# ---------------------------------------------------------------------------
# REC-KIT-003 -- a kit is read at a later release than the one that wrote it
# (D1122, D1141)
# ---------------------------------------------------------------------------


def _kit_with_document(
    host: dict[str, Path], contract: dict[str, Any], document: dict[str, Any], directory: Path
) -> Path:
    """The fixture kit with its deployed document REPLACED before the digests
    are computed, so `verify` reads a whole kit whose document is the one under
    test rather than a tampered one."""
    entries = [
        dr_kit.KitEntry(entry.relative, json.dumps(document).encode("utf-8"), entry.source)
        if entry.relative.endswith(dr_kit.DEPLOYED_DOCUMENT)
        else entry
        for entry in export(host, contract)
    ]
    return write_kit(entries, directory)


def _previous_version(rendered: dict[str, Any]) -> dict[str, Any]:
    """A deployed document at the version BEFORE the current one, by subtracting
    what the current version added -- Session 20's fixture-by-subtraction
    shape, so this document is the one an older release actually wrote.

    **This helper moves with the outputs version.** At 20 the subtraction is
    `control` and `routes.control` (ADR 0251; at 19 it was `connectors`, at 18
    `mcp.project_capabilities`, at 17 the `migrations` block); when a run bumps
    the version it must subtract that version's addition instead, and the
    assertion below is what says so.
    """
    document = deployed_document(rendered)
    assert deployed_output.SCHEMA_VERSION == 20, (
        "the outputs version moved; teach this helper what the new version added"
    )
    del document["control"]
    del document["routes"]["control"]
    document["schema_version"] = 19
    return document


def test_verify_reads_a_kit_whose_deployed_document_predates_this_release(
    host: dict[str, Path], contract: dict[str, Any], rendered: dict[str, Any], tmp_path: Path
) -> None:
    """D1122. The kit exported at outputs version 16 exited 5 against the
    version 17 checkout on 2026-09-11, twice, *"is not valid under any of the
    given schemas"* -- in the one scenario a kit exists for, rebuilding a lost
    host from a CURRENT checkout. The schema admits exactly one version, and the
    migrator refuses a deployed document by decision (ADR 0012), so the reader
    is the thing that has to know about versions (D1141).

    The arm is a document one version behind; the two controls are what the
    version-aware path must still refuse -- another project's document, and
    one carrying a sensitive key -- because a reader that accepted every older
    document would satisfy the first assertion and verify nothing.
    """
    older = _previous_version(rendered)
    assert dr_kit.verify_kit(_kit_with_document(host, contract, older, tmp_path / "older")) == []

    foreign = json.loads(json.dumps(older))
    foreign["project"]["key"] = "fixture-beta-dev"
    problems = dr_kit.verify_kit(_kit_with_document(host, contract, foreign, tmp_path / "foreign"))
    assert any("describes another project" in p for p in problems), problems

    leaky = json.loads(json.dumps(older))
    leaky["secrets"]["password"] = "not-a-real-value"  # noqa: S105 -- a key name is the subject
    problems = dr_kit.verify_kit(_kit_with_document(host, contract, leaky, tmp_path / "leaky"))
    assert any("sensitive key" in p and "password" in p for p in problems), problems


def test_a_document_this_release_cannot_read_is_reported_as_such_and_not_as_invalid(
    host: dict[str, Path], contract: dict[str, Any], rendered: dict[str, Any], tmp_path: Path
) -> None:
    """ADR 0195's third outcome. A document from a LATER release, or one older
    than any kit the facility ever exported, is a fact about the reader and is
    said to be; *"does not validate"* would send an operator to audit a kit
    that is whole. The control is a current-version document with a real
    defect, which must still be reported as invalid -- otherwise every problem
    could hide behind "cannot read"."""
    future = deployed_document(rendered)
    future["schema_version"] = deployed_output.SCHEMA_VERSION + 1
    problems = dr_kit.verify_kit(_kit_with_document(host, contract, future, tmp_path / "future"))
    assert len(problems) == 1, problems
    assert "this release reads up to" in problems[0] and "nothing about whether" in problems[0]
    assert "does not validate" not in problems[0]

    ancient = deployed_document(rendered)
    ancient["schema_version"] = dr_kit.KIT_FIRST_OUTPUTS_VERSION - 1
    problems = dr_kit.verify_kit(_kit_with_document(host, contract, ancient, tmp_path / "ancient"))
    assert len(problems) == 1, problems
    assert "not written by an export" in problems[0]
    assert "does not validate" not in problems[0]

    broken = deployed_document(rendered)
    broken["routes"]["rest"]["status"] = "nonsense"
    problems = dr_kit.verify_kit(_kit_with_document(host, contract, broken, tmp_path / "broken"))
    assert any("does not validate" in p for p in problems), problems


# ---------------------------------------------------------------------------
# D1848 -- an EXISTING deployed document is read by version, never migrated
# ---------------------------------------------------------------------------
#
# Measured on the reference host on 2026-09-30: the first 1.12.0 deploy's step
# 0 read the neighbour's outputs-18 document against a schema that admits only
# 19, counted it unreadable, and refused. D1122's rule for a kit is now the
# rule for every reader of a document that already exists.


def previous_version(document: dict[str, Any]) -> dict[str, Any]:
    """The document the release before this one wrote: 19 added `connectors`
    and nothing else (ADR 0237), so 18 is the current document without it."""
    older = json.loads(json.dumps(document))
    del older["connectors"]
    older["schema_version"] = deployed_output.READABLE_PREVIOUS_VERSION
    return older


def test_a_document_one_outputs_version_behind_is_read_exactly_as_found(
    rendered: dict[str, Any],
) -> None:
    current = deployed_document(rendered)
    older = previous_version(current)
    before = json.dumps(older, sort_keys=True)
    assert deployed_output.read_deployed_document(older) is older
    assert json.dumps(older, sort_keys=True) == before, "the reader carried an observation forward"
    assert "connectors" not in older
    # The WRITER's validator is unchanged: this release still writes only 19.
    with pytest.raises(ManifestError, match="not valid under any of the given schemas"):
        deployed_output.validate_deployed_document(older)
    assert deployed_output.read_deployed_document(current) is current


@pytest.mark.parametrize("offset", [-2, 1])
def test_any_other_outputs_version_is_named_as_unreadable_at_this_release(
    rendered: dict[str, Any], offset: int
) -> None:
    document = deployed_document(rendered)
    document["schema_version"] = deployed_output.SCHEMA_VERSION + offset
    expected = (
        f"outputs version {deployed_output.SCHEMA_VERSION + offset}; this release reads "
        f"versions {deployed_output.READABLE_PREVIOUS_VERSION} and {deployed_output.SCHEMA_VERSION}"
    )
    with pytest.raises(deployed_output.UnreadableVersion) as raised:
        deployed_output.read_deployed_document(document)
    assert expected in str(raised.value)


def test_the_previous_version_is_still_checked_for_what_a_reader_trusts(
    rendered: dict[str, Any],
) -> None:
    older = previous_version(deployed_document(rendered))
    read = deployed_output.read_deployed_document

    with pytest.raises(ManifestError, match="expected document_kind 'deployed'"):
        read({**older, "document_kind": "rendered"})
    sensitive = json.loads(json.dumps(older))
    sensitive["database"]["password"] = "x"  # noqa: S105 -- the planted key under test
    with pytest.raises(ManifestError, match="looks like secret material"):
        read(sensitive)
    placeholder = json.loads(json.dumps(older))
    placeholder["project"]["domain"] = "<domain>"
    with pytest.raises(ManifestError, match="unfilled placeholder"):
        read(placeholder)
    # And the current version is refused exactly as before -- nothing weakened.
    broken = deployed_document(rendered)
    broken["routes"]["rest"]["status"] = "nonsense"
    with pytest.raises(ManifestError) as raised:
        read(broken)
    assert not isinstance(raised.value, deployed_output.UnreadableVersion)


def _admission_root(tmp_path: Path, document: dict[str, Any]) -> Path:
    root = tmp_path / "admission-state"
    (root / KEY).mkdir(parents=True)
    (root / KEY / "outputs.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def test_admission_charges_a_neighbour_one_outputs_version_behind(
    tmp_path: Path, rendered: dict[str, Any]
) -> None:
    """The measured refusal, closed: the candidate is another project, the
    neighbour is at the previous version, and its claim is COUNTED, not
    refused as unreadable. The control is two versions behind: unreadable,
    named by version, and `decide` still fails closed on it."""
    from agentic_postgres import capacity_probe, capacity_reading

    def runner(*argv: str, **_: Any) -> None:
        return None

    host_manifest = REPO_ROOT / "host.example.yaml"
    neighbour = previous_version(deployed_document(rendered))
    claimed = neighbour["database"]["budget"]["unreclaimable_mb"]
    reading, _ = capacity_probe.read(
        host_manifest, _admission_root(tmp_path / "a", neighbour), runner=runner,
        exclude="candidate-dev",
    )  # fmt: skip
    assert reading.unreadable == {}, reading.unreadable
    assert reading.committed == {KEY: claimed}

    stale = {**neighbour, "schema_version": deployed_output.SCHEMA_VERSION - 2}
    reading, _ = capacity_probe.read(
        host_manifest, _admission_root(tmp_path / "b", stale), runner=runner,
        exclude="candidate-dev",
    )  # fmt: skip
    assert KEY in reading.unreadable
    assert f"outputs version {deployed_output.SCHEMA_VERSION - 2}" in reading.unreadable[KEY]
    decision = capacity_reading.decide(
        reading, candidate_key="candidate-dev", candidate_unreclaimable_mb=1,
        candidate_is_deployed=True,
    )  # fmt: skip
    assert decision.outcome == "refused"
    assert KEY in decision.reason


def test_fleet_retire_and_the_kit_read_a_document_one_version_behind(
    tmp_path: Path, rendered: dict[str, Any], host: dict[str, Path], contract: dict[str, Any]
) -> None:
    older = previous_version(deployed_document(rendered))
    root = _admission_root(tmp_path, older)

    document, why = load_command("fleet").read_document(root, KEY)
    assert why is None and document == older, why
    assert load_command("project-retire").load_document(root, KEY) == older

    (host["state_root"] / KEY / "outputs.json").write_text(json.dumps(older), encoding="utf-8")
    entries = {entry.relative: entry for entry in export(host, contract)}
    stored = entries[f"projects/{KEY}/{dr_kit.DEPLOYED_DOCUMENT}"]
    assert json.loads(stored.content) == older, "the kit must store the document as found"
    assert dr_kit.verify_deployed_document(older, KEY) == []


def test_no_reader_outside_deployed_output_calls_the_writers_validator() -> None:
    """The class guard (D1848, question 5 of CLAUDE.md section 7): the four
    readers that failed on the host were the four that called the WRITER's
    validator on a document that already existed. Every call of it outside
    `deployed_output` is refused, whatever the reader is for."""
    callers = []
    for path in sorted([*(REPO_ROOT / "bin").glob("*.py"), *(REPO_ROOT / "src").rglob("*.py")]):
        if path.name == "deployed_output.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "validate_deployed_document(" in text:
            callers.append(str(path.relative_to(REPO_ROOT)))
    assert callers == [], callers

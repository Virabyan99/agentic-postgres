"""Session 18's live halves for the mirror, the kit and the replacement host.

`REC-REPO-001`..`003`, `REC-KIT-001`..`002`, `REC-NODE-001`..`002`. Written at
the bump (Run 5), not in the runs that built the planes -- D1020 records the
miss -- and none of it has executed before the trip. Each docstring says what
it asserts and the trip finds out.

**What can only be proved on a deployment**: that a mirrored project's copy
record and the doctor's live mirror check describe a copy that completed at
the second provider; that the mirror's credential is not the primary's and
the archiver's configuration never names the mirror; that a kit exported from
THIS host verifies and holds no value this host holds; that the replacement
adopted the provider project by the recorded id with a fresh identity; that
the restore from the mirror alone verified, publishes the original identity,
and that `restore.sh` refuses the volume it has just filled.

**Where each runs.** The first three read the production host. The kit and
node proofs are declarations of things that HAPPENED off this host and are
gated on the files the operator brings back: the kit directory
(`APG_KIT_DIR`), the replacement's deployed document
(`APG_REPLACEMENT_HOST_OUTPUTS`), and the restore's evidence record
(`APG_RESTORE_EVIDENCE_FILE`). `REC-NODE-001`'s refusal is run where the
volume is, so it is gated on the restore record being local.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    access_broker,
    backup_report,
    backup_schedule,
    config,
    deployed_output,
    diagnosis,
    dr_kit,
    fleet,
)

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

R2_SUFFIX = ".r2.cloudflarestorage.com"


def _declared_json(variable: str) -> dict[str, Any]:
    """A file an operator declared. Absence is a failure, not a skip: the gate
    exports the variable only when it was given a path (D687)."""
    path = Path(os.environ[variable])
    if not path.is_file():
        pytest.fail(f"{variable} points at {path}, which does not exist")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        pytest.fail(f"{variable} points at {path}, which is not readable JSON: {error}")
    assert isinstance(document, dict), f"{path} is not a JSON object"
    return document


def _declared_dir(variable: str) -> Path:
    path = Path(os.environ[variable])
    if not path.is_dir():
        pytest.fail(f"{variable} points at {path}, which is not a directory")
    return path


def _key(document: dict[str, Any]) -> str:
    return str(document["project"]["key"])


def _doctor_check(sh_status, key: str, name: str) -> tuple[str | None, dict[str, Any]]:
    code, out, err = sh_status(str(REPO_ROOT / "bin" / "doctor.py"), "--project", key, "--json")
    assert code in (0, 6), f"doctor --json exited {code} for {key}\n{err}"
    parsed = json.loads(out)
    for check in parsed["checks"]:
        if check["name"] == name:
            return check["verdict"], check
    return None, {}


def _postgres_consumer_dir(key: str) -> Path:
    generation = access_broker.active_generation(key)
    return Path(access_broker.SECRET_ROOT) / key / "generations" / generation / "postgres"


# ---------------------------------------------------------------------------
# REC-REPO-001..003 -- the mirror, on the production host
# ---------------------------------------------------------------------------


def test_every_mirrored_project_holds_a_completed_copy_the_doctor_reads(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root, sh_status
) -> None:
    """`REC-REPO-001`. Both permanent projects are mirrored by the trip's first
    step; a project without a mirror here is the finding, not a vacuous pass
    (ADR 0065). For each: the copy record beside the deployed document parses
    as a completed copy of more than zero objects, the doctor's live mirror
    check reads `ok` off that record, the third timer is enabled, and the
    deployed document publishes the copy time the deploy observed."""
    del as_root
    for document in (project_a, project_b):
        key = _key(document)
        assert config.backup_mirror_enabled(document), (
            f"{key} declares no backup mirror; the trip enables backup.mirror on both "
            "permanent projects before this gate, and a project without one proves nothing"
        )
        record_path = deployed_output.mirror_record_path(key)
        assert record_path.is_file(), (
            f"{key}: no copy record at {record_path}; run "
            f"`sudo bin/backup.sh --outputs {os.environ['APG_PROJECT_A_OUTPUTS']} mirror`"
        )
        record = backup_report.parse_mirror_record(record_path.read_text(encoding="utf-8"))
        assert record is not None, f"{key}: the copy record does not parse as a completed copy"
        assert record["objects"] > 0, f"{key}: the record says the mirror holds no object"

        verdict, check = _doctor_check(sh_status, key, "backup mirror")
        assert verdict == diagnosis.OK, f"{key}: the doctor's mirror check read {verdict}: {check}"
        assert check["evidence"]["reported_status"] == backup_report.MIRROR_STATUS_COPIED

        unit = backup_schedule.units(key, fleet.timer_kinds(document))[fleet.MIRROR_KIND]
        _, out, _ = sh_status("systemctl", "is-enabled", unit)
        assert out.strip() == "enabled", f"{key}: {unit} is {out.strip() or 'absent'}"

        published = (document.get("backup_state") or {}).get("mirror") or {}
        assert published.get("last_copied_at"), (
            f"{key}: the deployed document publishes no mirror copy time; redeploy after "
            "the first copy so backup_state.mirror records it"
        )


def test_the_mirror_credential_is_not_the_primarys_and_the_archiver_never_names_the_mirror(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root
) -> None:
    """`REC-REPO-002`, as far as a host can measure it without a cross-account
    S3 probe: the mirror's key id in the active generation is not the primary's
    key id (two credentials, read from the materialised files and never
    printed); the mirror is at a different provider from the primary (the
    endpoint is not R2's); and no include file the archiver loads names the
    mirror's endpoint or bucket. The values are compared in memory only.

    Not measured here: that the primary's key is refused BY the mirror bucket.
    That is the provider's account boundary, stated in the description as a
    property of two accounts rather than proved by a probe (D1022)."""
    del as_root
    for document in (project_a, project_b):
        key = _key(document)
        assert config.backup_mirror_enabled(document), f"{key} declares no mirror"
        mirror = config.backup_mirror(document)
        assert not str(mirror["endpoint"]).endswith(R2_SUFFIX), (
            f"{key}: the mirror endpoint is at R2, the primary's provider (ADR 0188)"
        )

        consumer = _postgres_consumer_dir(key)
        includes = sorted(consumer.glob("*.conf"))
        assert includes, f"{key}: no pgBackRest include in {consumer}"
        primary_key_id = None
        for include in includes:
            text = include.read_text(encoding="utf-8")
            assert str(mirror["endpoint"]) not in text, (
                f"{key}: {include.name} names the mirror endpoint; the archiver must never"
            )
            assert str(mirror["bucket"]) not in text, (
                f"{key}: {include.name} names the mirror bucket; the archiver must never"
            )
            for line in text.splitlines():
                if line.startswith("repo1-s3-key="):
                    primary_key_id = line.partition("=")[2].strip()
        assert primary_key_id, f"{key}: no repo1-s3-key include in the postgres consumer"

        mirror_key = consumer / "mirror-s3-access-key-id"
        assert mirror_key.is_file(), f"{key}: the mirror pair is not materialised for postgres"
        assert mirror_key.read_text(encoding="utf-8").strip() != primary_key_id, (
            f"{key}: the mirror's key id IS the primary's; one credential reaches both"
        )


@pytest.mark.requires_environment("APG_RESTORE_EVIDENCE_FILE")
def test_a_restore_from_the_mirror_alone_verified_on_the_replacement(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """`REC-REPO-003`. The record `bin/restore.sh --from mirror` wrote on the
    replacement: source `mirror`, the verdict passed with no reason, a replay
    LSN, a promoted timeline, and the identity of one of THIS host's projects
    -- so the cluster the mirror produced is the project the kit describes."""
    record = _declared_json("APG_RESTORE_EVIDENCE_FILE")
    assert record.get("kind") == "node_restore", f"not a restore record: {record.get('kind')!r}"
    assert record.get("source") == "mirror", (
        f"the restore read {record.get('source')!r}; REC-REPO-003 is the restore from the "
        "mirror ALONE"
    )
    verdict = record.get("verdict") or {}
    assert verdict.get("passed") is True, f"the restore did not verify: {verdict.get('reasons')}"
    recovery = record.get("recovery") or {}
    assert recovery.get("achieved_lsn"), "no replay LSN in the record"
    assert int(recovery.get("timeline_id") or 0) >= 2, "the restore was not promoted"
    identities = {
        _key(d): (d.get("database") or {}).get("observed", {}).get("instance_uuid")
        for d in (project_a, project_b)
    }
    observed = (record.get("identity") or {}).get("observed_instance_uuid")
    assert observed and observed == identities.get(record.get("project_key")), (
        f"the restored identity is not {record.get('project_key')}'s on this host"
    )


# ---------------------------------------------------------------------------
# REC-KIT-001..002 -- the kit, and the adoption it enabled
# ---------------------------------------------------------------------------


@pytest.mark.requires_environment("APG_KIT_DIR")
def test_the_kit_exported_from_this_host_verifies_and_holds_no_value(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root, sh_status
) -> None:
    """`REC-KIT-001`. The kit the operator exported from this host: `verify`
    exits 0, every project directory holds the four artefacts by name, the
    listing has names and never values, and no file in the kit contains any
    secret value this host's active generations hold for either project --
    read from the materialised files, compared in memory, never printed."""
    del as_root
    kit = _declared_dir("APG_KIT_DIR")
    code, out, err = sh_status(str(REPO_ROOT / "bin" / "dr-kit.sh"), "verify", str(kit))
    assert code == 0, f"dr-kit.sh verify exited {code}\n{out}\n{err}"

    keys = {_key(project_a), _key(project_b)}
    for key in keys:
        directory = kit / "projects" / key
        assert directory.is_dir(), f"the kit holds no directory for {key}"
        for artefact in dr_kit.PROJECT_ARTIFACTS:
            assert (directory / artefact).is_file(), f"{key}: {artefact} is missing from the kit"
        listing = (directory / dr_kit.SECRETS_LISTING).read_text(encoding="utf-8")
        for line in listing.splitlines():
            if line.strip() and not line.startswith("#"):
                assert len(line.split()) == 3, f"{key}: a listing line is not name/path/origin"

    values: set[str] = set()
    for key in keys:
        consumer = _postgres_consumer_dir(key)
        for file in consumer.iterdir():
            if file.is_file() and not file.name.endswith(".conf"):
                value = file.read_text(encoding="utf-8").strip()
                if len(value) >= 8:
                    values.add(value)
    assert values, "no secret value could be read from the active generations; the scan is empty"
    for file in sorted(p for p in kit.rglob("*") if p.is_file()):
        text = file.read_text(encoding="utf-8", errors="replace")
        for value in values:
            assert value not in text, f"{file.relative_to(kit)} holds a value this host holds"


@pytest.mark.requires_environment("APG_KIT_DIR", "APG_REPLACEMENT_HOST_OUTPUTS")
def test_the_replacement_adopted_by_the_recorded_id_with_a_fresh_identity(
    project_a: dict[str, Any],
) -> None:
    """`REC-KIT-002`. The replacement's deployed document records the SAME
    Infisical project id the kit's document does for that key -- adoption by
    id -- and a DIFFERENT runtime identity, minted for the replacement (ADR
    0189); and it is not this host's document with a new name."""
    kit = _declared_dir("APG_KIT_DIR")
    replacement = _declared_json("APG_REPLACEMENT_HOST_OUTPUTS")
    assert replacement.get("document_kind") == "deployed"
    key = _key(replacement)
    original_path = kit / "projects" / key / dr_kit.DEPLOYED_DOCUMENT
    assert original_path.is_file(), f"the kit holds no deployed document for {key}"
    original = json.loads(original_path.read_text(encoding="utf-8"))

    kit_bootstrap = original.get("bootstrap") or {}
    new_bootstrap = replacement.get("bootstrap") or {}
    assert new_bootstrap.get("infisical_project_id"), "the replacement records no provider project"
    assert new_bootstrap["infisical_project_id"] == kit_bootstrap.get("infisical_project_id"), (
        "the replacement is bound to a different provider project than the kit records"
    )
    assert new_bootstrap.get("runtime_identity_id") != kit_bootstrap.get("runtime_identity_id"), (
        "the replacement reuses the lost host's runtime identity; adoption mints a fresh one"
    )
    assert replacement.get("host") != project_a.get("host") or replacement.get(
        "source_commit"
    ) != project_a.get("source_commit"), "the declared replacement document is this host's own"


# ---------------------------------------------------------------------------
# REC-NODE-001..002 -- the restore on the replacement
# ---------------------------------------------------------------------------


@pytest.mark.requires_environment("APG_KIT_DIR", "APG_RESTORE_EVIDENCE_FILE")
def test_restore_refuses_the_populated_volume_on_the_replacement(
    project_a: dict[str, Any], as_root, sh_status
) -> None:
    """`REC-NODE-001`, on the host where the restore ran: the volume the
    restore filled holds a cluster, so `restore.sh --plan` against it is
    refused with exit 7 before anything starts, and the refusal names the
    reason. The kit's manifest and this host's rendered directory are the
    inputs the runbook names."""
    del as_root
    record = _declared_json("APG_RESTORE_EVIDENCE_FILE")
    key = str(record.get("project_key"))
    assert key == _key(project_a), (
        f"the restore record is {key}'s and project A here is {_key(project_a)}; this proof "
        "runs on the replacement, against the restored project"
    )
    manifest = _declared_dir("APG_KIT_DIR") / "projects" / key / dr_kit.PROJECT_MANIFEST
    assert manifest.is_file(), f"the kit holds no manifest for {key}"
    rendered = deployed_output.rendered_path(key)
    code, out, err = sh_status(
        str(REPO_ROOT / "bin" / "restore.sh"),
        "--outputs",
        os.environ["APG_PROJECT_A_OUTPUTS"],
        "--project",
        str(manifest),
        "--rendered-dir",
        str(rendered),
        "--from",
        "mirror",
        "--latest",
        "--plan",
    )
    assert code == 7, f"restore.sh --plan against a populated volume exited {code}\n{out}\n{err}"
    assert "holds a cluster" in err, f"the refusal does not say why:\n{err}"


@pytest.mark.requires_environment(
    "APG_KIT_DIR", "APG_REPLACEMENT_HOST_OUTPUTS", "APG_RESTORE_EVIDENCE_FILE"
)
def test_the_restored_project_publishes_the_originals_identity_and_every_route_ready() -> None:
    """`REC-NODE-002`. The replacement's deployed document carries the
    instance_uuid the kit's document carried -- the volume's identity survived
    the restore -- the restore record agrees, and every route the document
    publishes is `ready`."""
    kit = _declared_dir("APG_KIT_DIR")
    replacement = _declared_json("APG_REPLACEMENT_HOST_OUTPUTS")
    record = _declared_json("APG_RESTORE_EVIDENCE_FILE")
    key = _key(replacement)
    original = json.loads(
        (kit / "projects" / key / dr_kit.DEPLOYED_DOCUMENT).read_text(encoding="utf-8")
    )
    expected = (original.get("database") or {}).get("observed", {}).get("instance_uuid")
    observed = (replacement.get("database") or {}).get("observed", {}).get("instance_uuid")
    assert expected and observed == expected, (
        f"the replacement publishes instance {observed!r}; the kit recorded {expected!r}"
    )
    assert (record.get("identity") or {}).get("observed_instance_uuid") == expected
    assert record.get("project_key") == key
    routes = replacement.get("routes") or {}
    not_ready = sorted(name for name, route in routes.items() if route.get("status") != "ready")
    assert not not_ready, f"routes not ready on the replacement: {not_ready}"

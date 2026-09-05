"""The backup mirror, offline (ADR 0188, Session 18 Run 2).

A mirror is a copy of the repository's bucket at a second provider, made by a
host unit that runs `mc mirror` in a container, under the primary's cipher
pass, with the archiver never involved (D994-D1000). What this module proves
is every reader that had to move for that to be one thing rather than a
container beside a system that does not know it exists:

* the render -- a mirrored manifest publishes the block, the five identifiers
  the container reads, and the credential pair the project now requires;
* the contract -- a `facility` secret exists for a project exactly when the
  facility is enabled (`enabled_facilities`), and every writer, mounter and
  requirer asks the same reader;
* the record -- what a completed copy writes, what a reader makes of it, and
  what the listing count is built from (D1004);
* the timers -- a mirrored project has three, and `schedule`, the inventory,
  the retirement plan and the verb all count the third;
* the verb -- `backup.sh mirror` writes the record only after a pass that
  exits 0 AND a listing that parses (D1001);
* the doctor and the deploy -- one reads the record live, the other at deploy
  time, through one parser.

Nothing here contacts a provider, starts a container or needs root.
"""

from __future__ import annotations

import configparser
import copy
import importlib.util
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from agentic_postgres import (
    REPO_ROOT,
    backup_report,
    backup_schedule,
    config,
    deployed_output,
    diagnosis,
    fleet,
    naming,
    rendering,
    retirement,
    secret_override,
    secrets_contract,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CONTRACT = REPO_ROOT / "secrets.required.yaml"
SESSION = 18
MIRROR_PAIR = frozenset({"mirror_s3_access_key_id", "mirror_s3_secret_access_key"})
SOURCE_PAIR = frozenset({"backup_r2_access_key_id", "backup_r2_secret_access_key"})
MIRROR = {
    "enabled": True,
    "endpoint": "s3.eu-central-003.backblazeb2.com",
    "region": "eu-central-003",
}
SLUG = "mirrored"
KEY = f"{SLUG}-dev"
LAUNCHER = (REPO_ROOT / "libexec" / "project-launcher").read_text(encoding="utf-8")

#: `mc ls --recursive --json`'s output, verbatim from the pinned image against
#: a two-file directory (D1004): one object per line, `"type":"file"`, a prefix
#: only inside a key. The non-recursive form lists the prefix as its own
#: `"type":"folder"` line, which is the second sample.
RECURSIVE_LISTING = (
    '{"status":"success","type":"file","lastModified":"2026-09-05T19:01:27.736992517Z",'
    '"size":1,"key":"one.txt","etag":"","url":"/data/","versionOrdinal":1}\n'
    '{"status":"success","type":"file","lastModified":"2026-09-05T19:01:27.736992517Z",'
    '"size":2,"key":"sub/two.txt","etag":"","url":"/data/","versionOrdinal":1}\n'
)
FLAT_LISTING = (
    '{"status":"success","type":"file","lastModified":"2026-09-05T19:01:27.736992517Z",'
    '"size":1,"key":"one.txt","etag":"","url":"/data/","versionOrdinal":1}\n'
    '{"status":"success","type":"folder","lastModified":"2026-09-05T19:01:27.736992517Z",'
    '"size":60,"key":"sub/","etag":"","url":"/data/","versionOrdinal":1}\n'
)


def load_command(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"apg_{name}", REPO_ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return secrets_contract.load_secret_contract(CONTRACT)


@pytest.fixture(scope="module")
def mirrored_manifest() -> dict[str, Any]:
    """The example manifest with a mirror, under its own identity."""
    document = yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))
    document["project"]["slug"] = SLUG
    document["backup"]["stanza"] = KEY
    document["backup"]["mirror"] = dict(MIRROR)
    return document


@pytest.fixture(scope="module")
def mirrored(mirrored_manifest: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> Any:
    """The mirrored manifest rendered through `render_project`, and removed
    afterwards: it publishes under `.generated/<key>` and the gate compares
    every rendered project there for collisions."""
    path = tmp_path_factory.mktemp("mirror") / "project.yaml"
    path.write_text(yaml.safe_dump(mirrored_manifest, sort_keys=False), encoding="utf-8")
    directory = rendering.render_project(
        path, REPO_ROOT / "capabilities.example.yaml", validate_compose=False
    )
    try:
        outputs = json.loads((directory / "outputs.json").read_text(encoding="utf-8"))
        env: dict[str, str] = {}
        for line in (directory / "compose.env").read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip():
                env[name.strip()] = value
        yield {"outputs": outputs, "env": env, "manifest": config.load_project_manifest(path)}
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture(scope="module")
def unmirrored() -> dict[str, Any]:
    path = REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json"
    if not path.exists():
        pytest.skip("fixtures are not rendered in this working tree")
    return json.loads(path.read_text(encoding="utf-8"))


def rendered_state(outputs: dict[str, Any]) -> dict[str, Any]:
    """A `backup_state` block in the shape the deploy publishes, from a
    rendered document's own report block: the `not_observed` state."""
    return dict(deployed_output.BACKUP_NOT_OBSERVED)


# ---------------------------------------------------------------------------
# The render
# ---------------------------------------------------------------------------


def test_a_mirrored_manifest_publishes_the_block_and_the_containers_identifiers(
    mirrored: dict[str, Any], mirrored_manifest: dict[str, Any]
) -> None:
    """The rendered document carries the mirror as the manifest declared it
    plus the one derived value, and `compose.env` carries the five identifiers
    the container reads -- source and destination alike, every one of them
    from the document rather than typed (ADR 0002)."""
    outputs, env = mirrored["outputs"], mirrored["env"]
    assert outputs["schema_version"] == 16
    assert outputs["backup"]["mirror"] == {
        **MIRROR,
        "bucket": naming.backup_mirror_bucket_name(KEY),
    }
    assert outputs["backup"]["mirror"]["bucket"] == f"apg-{KEY}-backup-mirror"

    account = mirrored_manifest["backup"]["account_id"]
    source_host = naming.storage_endpoint_url(account, "default").removeprefix("https://")
    assert "://" not in source_host
    assert env["BACKUP_MIRROR_ENABLED"] == "true"
    assert env["BACKUP_MIRROR_SOURCE_ENDPOINT"] == source_host
    assert env["BACKUP_MIRROR_SOURCE_BUCKET"] == outputs["backup"]["bucket"]
    assert env["BACKUP_MIRROR_ENDPOINT"] == MIRROR["endpoint"]
    assert env["BACKUP_MIRROR_BUCKET"] == outputs["backup"]["mirror"]["bucket"]


def test_an_unmirrored_project_renders_the_disabled_shape_and_empty_identifiers(
    unmirrored: dict[str, Any],
) -> None:
    """The example fixture declares no mirror, so its document says so and the
    container it would start reads `false` -- and refuses (exit 6, `mirror.sh`)."""
    assert unmirrored["backup"]["mirror"] == {
        "enabled": False,
        "endpoint": None,
        "bucket": None,
        "region": None,
    }
    env = (REPO_ROOT / ".generated" / "fixture-alpha-dev" / "compose.env").read_text("utf-8")
    assert "BACKUP_MIRROR_ENABLED=false" in env
    assert re.search(r"^BACKUP_MIRROR_BUCKET=$", env, re.M), "the bucket renders non-empty"


def test_the_provider_side_readers_owe_the_mirror_pair_only_to_a_mirrored_project(
    mirrored: dict[str, Any], unmirrored: dict[str, Any]
) -> None:
    """The bootstrap's declared list drives what `--plan` names and what
    `--apply` creates, and the deploy's preflight checks the provider holds
    what the bootstrap should have made. Both ask the project's view: an
    unmirrored project is neither told to paste the pair nor refused for
    lacking it. (The rendered document's own `required_names` is Session 2's
    list by design -- `RENDER_SESSION` -- and is not this reader.)"""
    bootstrap = load_command("bootstrap-providers")
    on = secrets_contract.enabled_facilities(mirrored["outputs"])
    off = secrets_contract.enabled_facilities(unmirrored)
    assert on and not off, "the two fixtures do not differ in the facility"
    declared_on = {s["name"] for s in bootstrap.declared_provider_secrets(SESSION, on)}
    declared_off = {s["name"] for s in bootstrap.declared_provider_secrets(SESSION, off)}
    assert MIRROR_PAIR <= declared_on
    assert not MIRROR_PAIR & declared_off
    assert declared_on - declared_off == MIRROR_PAIR
    pasted_on = {s["name"] for s in bootstrap.operator_supplied_provider_secrets(SESSION, on)}
    pasted_off = {s["name"] for s in bootstrap.operator_supplied_provider_secrets(SESSION, off)}
    assert pasted_on - pasted_off == MIRROR_PAIR, "the paste-by-hand report did not move"
    # The generated list is the same either way: the pair is operator-supplied.
    assert {s["name"] for s in bootstrap.generated_provider_secrets(SESSION, on)} == {
        s["name"] for s in bootstrap.generated_provider_secrets(SESSION, off)
    }
    # And the deploy's preflight names nothing for either: operator-supplied
    # secrets are never "missing" there, with or without the facility.
    deploy = load_command("deploy-project")
    state = {
        "managed_resources": [s["name"] for s in bootstrap.generated_provider_secrets(SESSION, on)]
    }
    assert deploy._secrets_the_provider_is_missing(state, SESSION, on) == []
    assert deploy._secrets_the_provider_is_missing(state, SESSION, off) == []
    assert "facilities=secrets_contract.enabled_facilities(rendered)" in (
        REPO_ROOT / "bin" / "deploy-project.py"
    ).read_text(encoding="utf-8"), "the deploy's preflight does not pass the project's facilities"


# ---------------------------------------------------------------------------
# The contract: a facility secret
# ---------------------------------------------------------------------------


def test_the_facility_is_read_once_from_either_document_shape(
    mirrored: dict[str, Any], mirrored_manifest: dict[str, Any], unmirrored: dict[str, Any]
) -> None:
    """`enabled_facilities` answers from a manifest and from a rendered document
    alike, through `config.backup_mirror_enabled` -- the one reader -- and a
    mirror on disabled backups is no facility at all."""
    on = frozenset({secrets_contract.FACILITY_BACKUP_MIRROR})
    assert secrets_contract.enabled_facilities(mirrored["manifest"]) == on
    assert secrets_contract.enabled_facilities(mirrored["outputs"]) == on
    assert secrets_contract.enabled_facilities(unmirrored) == frozenset()
    assert secrets_contract.enabled_facilities({}) == frozenset()
    # Backups off with a mirror block still saying : the schema
    # refuses that manifest at load, but the reader is a function over a dict
    # and must not answer from the mirror block alone (the battery's M13 found
    # the earlier form of this arm could not tell).
    off = copy.deepcopy(mirrored_manifest)
    off["backup"] = {"enabled": False, "mirror": dict(MIRROR)}
    assert config.backup_mirror(off)["enabled"] is True, "the arm's premise"
    assert not config.backup_mirror_enabled(off)
    assert secrets_contract.enabled_facilities(off) == frozenset()
    assert fleet.timer_kinds(off) == fleet.TIMER_KINDS


def test_active_secrets_filters_by_facility_only_when_asked(contract: dict[str, Any]) -> None:
    """None is the declared view; a set is one project's. A secret with no
    facility is in both; the mirror pair is in a project's view only with the
    facility."""
    declared = {s["name"] for s in secrets_contract.active_secrets(contract, SESSION)}
    assert MIRROR_PAIR <= declared
    without = {
        s["name"]
        for s in secrets_contract.active_secrets(contract, SESSION, facilities=frozenset())
    }
    assert not MIRROR_PAIR & without
    assert declared - without == MIRROR_PAIR, "the filter removed something else"
    with_ = {
        s["name"]
        for s in secrets_contract.active_secrets(
            contract, SESSION, facilities=frozenset({secrets_contract.FACILITY_BACKUP_MIRROR})
        )
    }
    assert with_ == declared


def test_the_mirror_pair_is_a_required_facility_secret_for_the_mirror_container(
    contract: dict[str, Any],
) -> None:
    by_name = {s["name"]: s for s in contract["secrets"]}
    for name in MIRROR_PAIR:
        secret = by_name[name]
        assert secret["facility"] == secrets_contract.FACILITY_BACKUP_MIRROR
        assert secret["required"] is True
        assert secret["origin"] == secrets_contract.OPERATOR_SUPPLIED
        assert secret["introduced_in_session"] == SESSION
        assert [c["service"] for c in secret["consumers"]] == ["backup-mirror"]
        assert all(c["uid"] == 65532 and c["format"] == "raw" for c in secret["consumers"])
    facility_bound = {s["name"] for s in contract["secrets"] if s.get("facility")}
    assert facility_bound == MIRROR_PAIR, "another secret gained a facility; extend this proof"


def test_a_facility_secret_declared_optional_is_refused(tmp_path: Path) -> None:
    """The third state is required-when-present. `required: false` beside a
    facility would be optional for a project that has the facility, which is
    the state Compose refuses at start (a missing mount source)."""
    raw = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    for secret in raw["secrets"]:
        if secret["name"] == "mirror_s3_access_key_id":
            secret["required"] = False
    path = tmp_path / "optional.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(config.ManifestError, match=r"facility.*declared optional"):
        secrets_contract.load_secret_contract(path)


def test_an_unknown_facility_is_refused_by_schema_and_by_loader(tmp_path: Path) -> None:
    raw = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    for secret in raw["secrets"]:
        if secret["name"] == "mirror_s3_access_key_id":
            secret["facility"] = "teleport"
    path = tmp_path / "unknown.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises((config.ManifestError, ValueError)):
        secrets_contract.load_secret_contract(path)
    assert secrets_contract.FACILITIES == ("backup_mirror",)


def test_the_override_grants_the_mirror_container_only_for_a_mirrored_project(
    contract: dict[str, Any],
) -> None:
    """The grant surface is written per project at start; a grant naming a file
    the materializer did not write is a service Compose refuses to start."""
    without = secret_override.build_secret_override(
        project_key=KEY, generation_id="g1", contract=contract, session=SESSION, facilities=set()
    )
    assert "backup-mirror" not in without["services"]
    assert not any(name.startswith("backup-mirror__") for name in without["secrets"])

    with_ = secret_override.build_secret_override(
        project_key=KEY,
        generation_id="g1",
        contract=contract,
        session=SESSION,
        facilities=frozenset({secrets_contract.FACILITY_BACKUP_MIRROR}),
    )
    targets = sorted(
        Path(grant["target"]).name for grant in with_["services"]["backup-mirror"]["secrets"]
    )
    assert targets == [
        "mirror-s3-access-key-id",
        "mirror-s3-secret-access-key",
        "source-s3-access-key-id",
        "source-s3-secret-access-key",
    ]
    # The files `mirror.sh` opens, by those names.
    script = (REPO_ROOT / "services" / "backup-mirror" / "mirror.sh").read_text(encoding="utf-8")
    for target in targets:
        assert f"read_secret {target}" in script, f"the container never reads {target}"
    # The declared view (None) still grants it: that is the shape proof's view.
    declared = secret_override.build_secret_override(
        project_key=KEY, generation_id="g1", contract=contract, session=SESSION
    )
    assert "backup-mirror" in declared["services"]


def test_the_materializer_plans_the_mirror_files_only_with_the_facility(
    contract: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """`plan` is the materializer's own loop with the fetch and the write
    removed, so what it lists is what `materialize` would write."""
    materializer = load_command("materialize-secrets")
    materializer.plan(KEY, contract, SESSION, frozenset())
    without = capsys.readouterr().out
    assert "/backup-mirror/" not in without
    materializer.plan(KEY, contract, SESSION, frozenset({"backup_mirror"}))
    with_ = capsys.readouterr().out
    assert with_.count("/backup-mirror/") == 4, with_
    assert "mirror_s3_access_key_id" in with_
    # The line at the bottom counts what a rotation must reach (D108).
    assert re.search(r"\d+ files would be written for \d+ secrets", with_)


def test_the_override_command_reads_the_facility_off_the_rendered_document() -> None:
    """`bin/render-secret-override.py` runs between materialization and `up`,
    with the rendered directory in hand; that document is where it must read
    the facility from, and it must refuse a directory without one rather than
    default to the declared view and grant a file that was never written."""
    source = (REPO_ROOT / "bin" / "render-secret-override.py").read_text(encoding="utf-8")
    assert "enabled_facilities(" in source
    assert 'rendered_dir / "outputs.json"' in source
    assert "facilities=facilities" in source
    materializer = (REPO_ROOT / "bin" / "materialize-secrets.py").read_text(encoding="utf-8")
    assert materializer.count("facilities=facilities") >= 3, (
        "plan, its count line and materialize must all filter by the facility"
    )


# ---------------------------------------------------------------------------
# The record and its readers
# ---------------------------------------------------------------------------


def test_the_record_round_trips_and_only_a_complete_record_parses() -> None:
    now = datetime(2026, 9, 5, 4, 41, 7, 123456, tzinfo=UTC)
    record = backup_report.mirror_record(objects=1234, copied_at=now)
    assert record == {
        "status": "copied",
        "last_copied_at": "2026-09-05T04:41:07Z",
        "objects": 1234,
    }
    assert backup_report.parse_mirror_record(json.dumps(record)) == record
    with pytest.raises(ValueError):
        backup_report.mirror_record(objects=-1, copied_at=now)
    refused = [
        "",
        "not json",
        "[]",
        json.dumps({"status": "never"}),
        json.dumps({**record, "last_copied_at": None}),
        json.dumps({**record, "objects": "12"}),
        json.dumps({**record, "objects": True}),
        json.dumps({**record, "objects": -1}),
    ]
    for text in refused:
        assert backup_report.parse_mirror_record(text) is None, text


def test_the_reading_has_three_states_and_each_validates_against_the_schema() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))
    validator = Draft202012Validator({**schema["$defs"]["mirrorState"], "$defs": schema["$defs"]})
    record = backup_report.mirror_record(objects=3, copied_at=datetime.now(UTC))
    readings = {
        "disabled": backup_report.mirror_reading(enabled=False, record=None),
        "never": backup_report.mirror_reading(enabled=True, record=None),
        "copied": backup_report.mirror_reading(enabled=True, record=record),
    }
    for status, reading in readings.items():
        assert reading["status"] == status
        validator.validate(reading)
    assert readings["disabled"]["last_copied_at"] is None
    assert readings["never"]["objects"] is None
    assert readings["copied"] == record
    validator.validate(backup_report.MIRROR_NOT_OBSERVED)
    # A disabled reading given a record still says disabled: the manifest wins.
    assert backup_report.mirror_reading(enabled=False, record=record)["status"] == "disabled"


def test_the_listing_count_is_files_only_and_never_a_guess() -> None:
    """D1004, measured on the pinned image: recursive listings are file lines;
    the flat form adds folder lines, which are prefixes and not objects."""
    assert backup_report.count_listing(RECURSIVE_LISTING) == 2
    assert backup_report.count_listing(FLAT_LISTING) == 1
    assert backup_report.count_listing("") == 0
    assert backup_report.count_listing("\n\n") == 0
    assert backup_report.count_listing(RECURSIVE_LISTING + "mc: <ERROR> boom\n") is None
    assert backup_report.count_listing('["a"]\n') is None


def test_with_mirror_folds_without_touching_the_repositorys_status() -> None:
    state = {**deployed_output.BACKUP_NOT_OBSERVED, "status": "ready"}
    state.pop("mirror")
    folded = backup_report.with_mirror(state, None)
    assert folded["status"] == "ready"
    assert folded["mirror"] == backup_report.MIRROR_NOT_OBSERVED
    reading = backup_report.mirror_reading(enabled=True, record=None)
    assert backup_report.with_mirror(state, reading)["mirror"] == reading
    copied = backup_report.mirror_reading(
        enabled=True,
        record=backup_report.mirror_record(objects=9, copied_at=datetime.now(UTC)),
    )
    folded = backup_report.with_mirror(state, copied)
    assert folded["mirror"] == copied and folded["status"] == "ready"
    assert "mirror" not in state, "the input was mutated"
    # A copied reading that lost its values does not publish `copied` with nulls
    # as measured: the values follow the status.
    assert backup_report.with_mirror(state, {"status": "never", "objects": 4})["mirror"] == {
        "status": "never",
        "last_copied_at": None,
        "objects": None,
    }


def test_backup_state_starts_with_the_mirror_not_observed() -> None:
    """`backup_state` computes the repository's block; the mirror is a third
    source it has not read, and the deployed schema requires the key."""
    state = backup_report.backup_state(
        {"status_code": backup_report.REPOSITORY_MISSING_STANZA, "backup_count": 0}, None
    )
    assert state["mirror"] == backup_report.MIRROR_NOT_OBSERVED
    assert deployed_output.BACKUP_NOT_OBSERVED["mirror"] == backup_report.MIRROR_NOT_OBSERVED


# ---------------------------------------------------------------------------
# The timers: three for a mirrored project
# ---------------------------------------------------------------------------


def test_a_mirrored_project_has_three_timers_and_an_unmirrored_one_two(
    mirrored: dict[str, Any], unmirrored: dict[str, Any]
) -> None:
    assert fleet.timer_kinds(mirrored["outputs"]) == ("full", "incr", "mirror")
    assert fleet.timer_kinds(mirrored["manifest"]) == ("full", "incr", "mirror")
    assert fleet.timer_kinds(unmirrored) == ("full", "incr")
    assert fleet.timer_kinds({}) == ("full", "incr")
    assert fleet.timer_unit("mirror", KEY) == f"agentic-postgres-backup-mirror@{KEY}.timer"


def test_the_schedule_counts_the_mirror_timer_exactly_when_it_is_read() -> None:
    """Two enabled timers and a disabled mirror is unscheduled; the same two
    with no mirror reading is scheduled -- the fold is over what the project
    has, and a mandatory kind missing is unknown, never scheduled."""
    e, d, u = fleet.ENABLED, fleet.DISABLED, fleet.UNKNOWN
    assert fleet.schedule({"full": e, "incr": e}) == fleet.SCHEDULED
    assert fleet.schedule({"full": e, "incr": e, "mirror": e}) == fleet.SCHEDULED
    assert fleet.schedule({"full": e, "incr": e, "mirror": d}) == fleet.UNSCHEDULED
    assert fleet.schedule({"full": e, "incr": e, "mirror": fleet.ABSENT}) == fleet.UNSCHEDULED
    assert fleet.schedule({"full": e, "incr": e, "mirror": u}) == fleet.UNKNOWN
    assert fleet.schedule({"incr": e, "mirror": e}) == fleet.UNKNOWN


def test_the_schedule_verbs_documents_carry_the_third_timer() -> None:
    three = {"full": fleet.ENABLED, "incr": fleet.ENABLED, "mirror": fleet.DISABLED}
    document = backup_schedule.status_document(KEY, three)
    assert list(document["timers"]) == ["full", "incr", "mirror"]
    assert document["units"]["mirror"] == f"agentic-postgres-backup-mirror@{KEY}.timer"
    assert document["schedule"] == fleet.UNSCHEDULED
    text = backup_schedule.render_status(KEY, three)
    assert "mirror" in text and "schedule enable" in text
    assert backup_schedule.units(KEY) == backup_schedule.units(KEY, fleet.TIMER_KINDS)
    assert set(backup_schedule.units(KEY, fleet.ALL_TIMER_KINDS)) == {"full", "incr", "mirror"}

    why = backup_schedule.enable_refusal(
        {"full": fleet.ABSENT, "incr": fleet.ABSENT, "mirror": fleet.ABSENT},
        repository_status=backup_report.STATUS_READY,
        last_full_backup_at="t",
    )
    assert why is not None and "full, incr and mirror" in why
    only_mirror = backup_schedule.enable_refusal(
        {"full": fleet.DISABLED, "incr": fleet.DISABLED, "mirror": fleet.ABSENT},
        repository_status=backup_report.STATUS_READY,
        last_full_backup_at="t",
    )
    assert only_mirror is not None and "the mirror timer" in only_mirror
    two = backup_schedule.enable_refusal(
        {"full": fleet.ABSENT, "incr": fleet.ABSENT},
        repository_status=backup_report.STATUS_READY,
        last_full_backup_at="t",
    )
    assert two is not None and "full and incr" in two, "the two-timer wording changed"


def test_the_inventory_row_shows_the_third_timer_for_a_mirrored_project(
    mirrored: dict[str, Any], unmirrored: dict[str, Any]
) -> None:
    """The inventory's row is composed from the timers the reader took for the
    project's kinds; a reading for a kind the document lacks is dropped."""
    now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    timers = {"full": fleet.ENABLED, "incr": fleet.ENABLED, "mirror": fleet.DISABLED}
    row = fleet.row(
        KEY,
        mirrored["outputs"],
        doctor=None,
        doctor_problem="not run",
        timers=timers,
        denials={},
        window_hours=24,
        now=now,
    )
    assert row.backups["timers"] == timers
    assert row.backups["state"] == fleet.UNSCHEDULED
    text = fleet.render_text((row,), observed_at="t", window_hours=24)
    assert "mirror=disabled" in text

    plain = fleet.row(
        "fixture-alpha-dev",
        unmirrored,
        doctor=None,
        doctor_problem="not run",
        timers=timers,
        denials={},
        window_hours=24,
        now=now,
    )
    assert list(plain.backups["timers"]) == ["full", "incr"]
    assert plain.backups["state"] == fleet.SCHEDULED
    assert "mirror=" not in fleet.render_text((plain,), observed_at="t", window_hours=24)


def test_the_inventory_command_reads_the_timers_the_document_declares() -> None:
    source = (REPO_ROOT / "bin" / "fleet.py").read_text(encoding="utf-8")
    assert "fleet.timer_kinds(document)" in source
    assert "read_timers(key, document)" in source


def test_a_retirement_disables_the_mirror_timer_of_a_mirrored_project(
    mirrored: dict[str, Any], unmirrored: dict[str, Any], tmp_path: Path
) -> None:
    """A mirror timer left enabled after a retirement fires against a project
    whose secrets and containers are gone: a failed unit every night."""

    def resources(document: dict[str, Any], key: str) -> retirement.Resources:
        return retirement.resources_of(
            key,
            document,
            state_root=tmp_path / "state",
            secret_root=tmp_path / "secrets",
            rendered_root=tmp_path / "rendered",
            edge_dynamic_dir=tmp_path / "edge",
        )

    assert resources(mirrored["outputs"], KEY).timers == (
        f"agentic-postgres-backup-full@{KEY}.timer",
        f"agentic-postgres-backup-incr@{KEY}.timer",
        f"agentic-postgres-backup-mirror@{KEY}.timer",
    )
    assert len(resources(unmirrored, "fixture-alpha-dev").timers) == 2


# ---------------------------------------------------------------------------
# The units and the launcher
# ---------------------------------------------------------------------------


def read_unit(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read_string((REPO_ROOT / "systemd" / name).read_text(encoding="utf-8"))
    return parser


def test_the_mirror_timer_is_nightly_persistent_jittered_and_binds_to_the_project() -> None:
    timer = read_unit("agentic-postgres-backup-mirror@.timer")["Timer"]
    assert timer["Unit"] == "agentic-postgres-backup-mirror@%i.service"
    assert timer["OnCalendar"].startswith("*-*-*"), "the mirror is nightly, like the incremental"
    assert timer["Persistent"] == "true"
    assert timer["RandomizedDelaySec"]
    service = read_unit("agentic-postgres-backup-mirror@.service")
    assert service["Service"]["ExecStart"] == (
        "/usr/local/libexec/agentic-postgres/project %i backup-mirror"
    )
    assert service["Service"]["Type"] == "oneshot"
    assert "agentic-postgres-project@%i.service" in service["Unit"]["BindsTo"]


def test_the_launcher_runs_the_mirror_verb_and_no_check_before_it() -> None:
    """The copy reads the repository and never the cluster, and a repository
    whose archiver is broken is still the right copy to have; `check` is the
    backups' pre-flight, not the mirror's."""
    assert re.search(r"backup-full\|backup-incr\|backup-mirror\)", LAUNCHER)
    dispatch = LAUNCHER.split("backup-mirror)")[-1].split(";;")[0]
    assert re.search(r'backup\.sh" --outputs "\$\{deployment\}" mirror', dispatch), dispatch
    assert "check" not in dispatch
    assert "backup --type" not in dispatch


def test_the_container_is_the_mirror_profile_on_the_backup_network_only() -> None:
    """Reachable from the deploy's model: the `mirror` profile alone starts it,
    it joins the project's backup egress network and nothing else, and it runs
    as the non-root uid the contract grants its files to."""
    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = model["services"]["backup-mirror"]
    assert service["profiles"] == ["mirror"]
    assert list(service["networks"]) == ["backup"]
    assert str(service["user"]).startswith("65532")
    assert service["read_only"] is True
    assert service["restart"] == "no"
    for name in (
        "BACKUP_MIRROR_ENABLED",
        "BACKUP_MIRROR_SOURCE_ENDPOINT",
        "BACKUP_MIRROR_SOURCE_BUCKET",
        "BACKUP_MIRROR_ENDPOINT",
        "BACKUP_MIRROR_BUCKET",
    ):
        assert name in service["environment"], f"the container is not handed {name}"
        assert name in rendering.COMPOSE_ENV_KEYS, f"the render does not emit {name}"
    assert "MC_IMAGE" in (REPO_ROOT / "versions.env").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The verb: `backup.sh mirror`
# ---------------------------------------------------------------------------


class Compose:
    """A recorded `bin/compose.sh … run backup-mirror <action>`."""

    def __init__(
        self, *, copy_exit: int = 0, listing: str = RECURSIVE_LISTING, count_exit: int = 0
    ):
        self.copy_exit = copy_exit
        self.listing = listing
        self.count_exit = count_exit
        self.calls: list[str] = []

    def __call__(self, rendered: Path, action: str, *, timeout: int) -> Any:
        self.calls.append(action)
        assert (rendered / "compose.env").is_file(), "the verb ran against no rendered output"
        if action == "copy":
            return subprocess.CompletedProcess([], self.copy_exit, stdout="…\n", stderr="")
        if action == "count":
            return subprocess.CompletedProcess([], self.count_exit, stdout=self.listing, stderr="")
        raise AssertionError(action)


@pytest.fixture
def backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    module = load_command("backup")
    monkeypatch.setattr(module, "require_root", lambda: None)
    monkeypatch.setattr(module, "RENDERED_ROOT", tmp_path / "rendered")
    monkeypatch.setattr(module, "STATE_ROOT", tmp_path / "state")
    (tmp_path / "rendered" / KEY).mkdir(parents=True)
    (tmp_path / "rendered" / KEY / "compose.env").write_text("BACKUP_MIRROR_ENABLED=true\n")
    (tmp_path / "state" / KEY).mkdir(parents=True)
    module.TMP = tmp_path
    return module


def outputs_for(backup: Any, *, mirror: bool) -> Path:
    document = {
        "project": {"key": KEY},
        "database": {"container": f"apg-{KEY}-postgres-1", "name": "x"},
        "backup": {"stanza": KEY, "enabled": True, "mirror": {**MIRROR} if mirror else None},
    }
    path = backup.TMP / "state" / KEY / "outputs.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_the_verb_writes_the_record_only_after_a_clean_copy_and_a_parsed_listing(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    compose = Compose()
    monkeypatch.setattr(backup, "compose_mirror", compose)
    outputs = outputs_for(backup, mirror=True)
    before = datetime.now(UTC).replace(microsecond=0)
    assert backup.main(["--outputs", str(outputs), "mirror"]) == 0
    assert compose.calls == ["copy", "count"]
    record_path = deployed_output.mirror_record_path(KEY, root=backup.TMP / "state")
    record = backup_report.parse_mirror_record(record_path.read_text(encoding="utf-8"))
    assert record is not None and record["objects"] == 2
    copied_at = datetime.fromisoformat(record["last_copied_at"].replace("Z", "+00:00"))
    assert before <= copied_at <= datetime.now(UTC) + timedelta(seconds=1)
    assert oct(record_path.stat().st_mode & 0o777) == "0o600"
    assert "2 object(s)" in capsys.readouterr().out


def test_a_copy_that_exits_non_zero_writes_no_record_and_lists_nothing(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D1001: a pass that exits 1 has left objects behind. The previous record,
    if any, keeps describing the last COMPLETE copy."""
    record_path = deployed_output.mirror_record_path(KEY, root=backup.TMP / "state")
    previous = backup_report.mirror_record(objects=7, copied_at=datetime(2026, 9, 1, tzinfo=UTC))
    record_path.write_text(json.dumps(previous), encoding="utf-8")
    compose = Compose(copy_exit=1)
    monkeypatch.setattr(backup, "compose_mirror", compose)
    assert backup.main(["--outputs", str(outputs_for(backup, mirror=True)), "mirror"]) == 5
    assert compose.calls == ["copy"]
    assert json.loads(record_path.read_text(encoding="utf-8")) == previous
    assert "D1001" in capsys.readouterr().err


@pytest.mark.parametrize("listing, count_exit", [("mc: <ERROR> nope\n", 0), ("", 3)])
def test_an_unreadable_listing_after_a_clean_copy_writes_no_record(
    backup: Any, monkeypatch: pytest.MonkeyPatch, listing: str, count_exit: int
) -> None:
    """The count is measured or absent, never zero by default: zero is the
    number a restore would be planned against."""
    compose = Compose(listing=listing, count_exit=count_exit)
    monkeypatch.setattr(backup, "compose_mirror", compose)
    assert backup.main(["--outputs", str(outputs_for(backup, mirror=True)), "mirror"]) == 5
    assert compose.calls == ["copy", "count"]
    assert not deployed_output.mirror_record_path(KEY, root=backup.TMP / "state").exists()


def test_the_verb_refuses_a_project_without_a_mirror_before_starting_anything(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    compose = Compose()
    monkeypatch.setattr(backup, "compose_mirror", compose)
    assert backup.main(["--outputs", str(outputs_for(backup, mirror=False)), "mirror"]) == 2
    assert compose.calls == []
    assert "declares no backup mirror" in capsys.readouterr().err


def test_the_verb_refuses_a_project_with_no_rendered_output(
    backup: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose = Compose()
    monkeypatch.setattr(backup, "compose_mirror", compose)
    (backup.TMP / "rendered" / KEY / "compose.env").unlink()
    assert backup.main(["--outputs", str(outputs_for(backup, mirror=True)), "mirror"]) == 5
    assert compose.calls == []


def test_the_verb_reaches_the_container_through_the_wrapper_with_the_profile() -> None:
    """Through `bin/compose.sh --runtime --profile mirror run --rm`, so the
    installed overrides and the `run` refusals apply, and no credential is in
    this process's argv."""
    source = (REPO_ROOT / "bin" / "backup.py").read_text(encoding="utf-8")
    body = source.split("def compose_mirror(")[1].split("\ndef ")[0]
    argv = body.split("command = [")[1].split("]")[0]
    for token in ('"--runtime"', '"--profile"', '"mirror"', '"run"', '"--rm"', '"backup-mirror"'):
        assert token in argv, f"compose_mirror does not pass {token}"
    assert "stdin=subprocess.DEVNULL" in body, "D673: a run that inherits stdin can hang"
    assert "-e" not in argv.replace('"--rm"', "") and "--env" not in argv


def test_schedule_status_on_a_mirrored_project_reads_three_units(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    def systemctl(*arguments: str) -> Any:
        calls.append(arguments[-1])
        answer = "disabled" if "mirror@" in arguments[-1] else "enabled"
        return subprocess.CompletedProcess(list(arguments), 0 if answer == "enabled" else 1, answer)

    monkeypatch.setattr(backup, "systemctl", systemctl)
    assert (
        backup.main(
            ["--outputs", str(outputs_for(backup, mirror=True)), "schedule", "status", "--json"]
        )
        == 6
    )
    document = json.loads(capsys.readouterr().out)
    assert list(document["timers"]) == ["full", "incr", "mirror"]
    assert document["schedule"] == fleet.UNSCHEDULED
    assert [c.split("@")[0] for c in calls] == [
        "agentic-postgres-backup-full",
        "agentic-postgres-backup-incr",
        "agentic-postgres-backup-mirror",
    ]

    calls.clear()
    assert (
        backup.main(
            ["--outputs", str(outputs_for(backup, mirror=False)), "schedule", "status", "--json"]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["schedule"] == fleet.SCHEDULED
    assert len(calls) == 2, "an unmirrored project's status read a mirror timer"


# ---------------------------------------------------------------------------
# The doctor and the deploy
# ---------------------------------------------------------------------------


def test_the_doctor_classifies_every_mirror_state() -> None:
    check = diagnosis.mirror
    assert check(enabled=False, status=None, last_copied_at=None, age_days=None).verdict == (
        diagnosis.OK
    )
    assert check(enabled=True, status=None, last_copied_at=None, age_days=None).verdict == (
        diagnosis.UNKNOWN
    )
    assert (
        check(enabled=True, status="not_observed", last_copied_at=None, age_days=None).verdict
        == diagnosis.UNKNOWN
    )
    assert check(enabled=True, status="never", last_copied_at=None, age_days=None).verdict == (
        diagnosis.WARN
    )
    fresh = check(enabled=True, status="copied", last_copied_at="t", age_days=0)
    assert fresh.verdict == diagnosis.OK and "last copied t" in fresh.detail
    stale = check(
        enabled=True,
        status="copied",
        last_copied_at="t",
        age_days=diagnosis.MIRROR_STALE_AFTER_DAYS,
    )
    assert stale.verdict == diagnosis.WARN and "missed" in stale.detail
    assert check(enabled=True, status="copied", last_copied_at="t", age_days=None).verdict == (
        diagnosis.OK
    ), "an age nobody computed is reported by its timestamp, not assumed stale"
    assert check(enabled=True, status="weird", last_copied_at=None, age_days=None).verdict == (
        diagnosis.PROBLEM
    )
    assert {c.name for c in [fresh, stale]} == {"backup mirror"}
    assert dict(fresh.evidence)["age_days"] == "0"


def test_the_doctor_probe_reads_the_record_live_and_never_the_document(
    mirrored: dict[str, Any], unmirrored: dict[str, Any], tmp_path: Path
) -> None:
    doctor = load_command("doctor")
    (tmp_path / KEY).mkdir()
    # A document claiming a copy, and no record on disk: the record wins.
    claimed = copy.deepcopy(mirrored["outputs"])
    claimed["backup_state"] = {
        **deployed_output.BACKUP_NOT_OBSERVED,
        "mirror": {"status": "copied", "last_copied_at": "2026-09-01T00:00:00Z", "objects": 5},
    }
    never = doctor.probe_mirror(KEY, claimed, tmp_path)
    assert never.verdict == diagnosis.WARN and "never" in never.detail

    record_path = deployed_output.mirror_record_path(KEY, root=tmp_path)
    record_path.write_text(
        json.dumps(backup_report.mirror_record(objects=2, copied_at=datetime.now(UTC)))
    )
    assert doctor.probe_mirror(KEY, mirrored["outputs"], tmp_path).verdict == diagnosis.OK

    old = datetime.now(UTC) - timedelta(days=diagnosis.MIRROR_STALE_AFTER_DAYS + 1)
    record_path.write_text(json.dumps(backup_report.mirror_record(objects=2, copied_at=old)))
    stale = doctor.probe_mirror(KEY, mirrored["outputs"], tmp_path)
    assert stale.verdict == diagnosis.WARN and "missed" in stale.detail

    record_path.write_text("{not json")
    assert doctor.probe_mirror(KEY, mirrored["outputs"], tmp_path).verdict == diagnosis.UNKNOWN

    assert doctor.probe_mirror("fixture-alpha-dev", unmirrored, tmp_path).verdict == diagnosis.OK
    names = [c.name for c in (never, stale)]
    assert names == ["backup mirror", "backup mirror"]
    # And `diagnose` composes it, between the archiver and the disk.
    source = (REPO_ROOT / "bin" / "doctor.py").read_text(encoding="utf-8")
    body = source.split("def diagnose(")[1]
    assert body.index("probe_archiver(") < body.index("probe_mirror(") < body.index("probe_disk(")


def test_the_deploy_folds_the_mirror_into_every_branch_of_the_backup_state(
    mirrored: dict[str, Any], unmirrored: dict[str, Any], tmp_path: Path
) -> None:
    deploy = load_command("deploy-project")
    disabled = deploy.read_mirror("fixture-alpha-dev", unmirrored, root=tmp_path)
    assert disabled["status"] == "disabled"
    (tmp_path / KEY).mkdir()
    never = deploy.read_mirror(KEY, mirrored["outputs"], root=tmp_path)
    assert never["status"] == "never"
    record = backup_report.mirror_record(objects=3, copied_at=datetime.now(UTC))
    deployed_output.mirror_record_path(KEY, root=tmp_path).write_text(json.dumps(record))
    copied = deploy.read_mirror(KEY, mirrored["outputs"], root=tmp_path)
    assert copied == record

    for enabled, credentialed in ((False, False), (True, False), (True, True)):
        state = deploy.observe_backup(enabled=enabled, credentialed=credentialed, mirror=copied)
        assert state["mirror"] == copied, (enabled, credentialed)
        assert state["status"] in {"unconfigured", "not_observed"}
    summary = backup_report.backup_state(
        {"status_code": backup_report.REPOSITORY_OK, "backup_count": 1}, None
    )
    with_summary = deploy.observe_backup(
        enabled=True, credentialed=True, summary=summary, archiver=None, mirror=never
    )
    assert with_summary["mirror"] == never
    assert with_summary["status"] == summary["status"]
    # The deployed document built from it validates with the fold in place.
    deployed_output.validate_deployed_document(
        deployed_output.build_deployed_document(
            **_document_arguments(mirrored["outputs"]), backup_state=with_summary
        )
    )


def _document_arguments(rendered: dict[str, Any]) -> dict[str, Any]:
    """The keyword arguments `build_deployed_document` needs beside the state,
    borrowed from the fleet proof's deployed fixture shape."""
    key = rendered["project"]["key"]
    return {
        "rendered": rendered,
        "source_commit": "a" * 40,
        "health_status": "ready",
        "rest_status": "unavailable",
        "docs_status": "unavailable",
        "app_status": "unavailable",
        "app_docs_status": "unavailable",
        "storage_status": "unavailable",
        "mcp_status": "unavailable",
        "metrics_status": "unavailable",
        "api": deployed_output.API_NOT_PUBLISHED,
        "jwt": deployed_output.JWT_NOT_PUBLISHED,
        "mcp": deployed_output.MCP_NOT_PUBLISHED,
        "deployed_through_session": SESSION,
        "host": {
            "id": "apg-vps-01",
            "os_release": "26.04",
            "public_ipv4": "203.0.113.10",
            "public_ipv6": None,
        },
        "edge": {
            "stack_name": "apg-edge",
            "control_network": "apg-edge_control",
            "egress_network": "apg-edge_egress",
            "project_network_attached": True,
        },
        "tls": {
            "status": "issued",
            "acme_environment": "staging",
            "resolver": "letsencrypt-staging",
            "certificate_sha256": "c" * 64,
            "not_before": "2026-08-05T00:00:00Z",
            "not_after": "2026-11-03T00:00:00Z",
        },
        "bootstrap": {
            "status": "complete",
            "state_path": f"/etc/agentic-postgres/projects/{key}/bootstrap-state.json",
            "infisical_project_id": "5fffcd38-9af6-4f9d-bef9-c6eefc5e696f",
            "runtime_identity_id": "3302b5a4-7288-424f-bcd3-6cd158617827",
        },
        "secrets": {
            "status": "ready",
            "generation_id": "k7f2p9qd",
            "generation_manifest": (
                f"/var/lib/agentic-postgres/secrets/{key}/generations/k7f2p9qd/manifest.json"
            ),
            "required_names": rendered["secrets"]["required_names"],
            "fresh": True,
            "materialized_at": "2026-08-05T18:00:00Z",
        },
        "runtime": {
            "release_path": "/opt/agentic-postgres/releases/" + "a" * 40,
            "state_directory": f"/etc/agentic-postgres/projects/{key}",
            "compose_model_sha256": "d" * 64,
        },
        "database_observed": {
            "status": "observed",
            "server_version": "18.4",
            "extensions": {"vector": "0.8.6", "plpgsql": "1.0"},
            "memory": {"anon_mb": 62, "shmem_mb": 140, "file_mb": 410},
            "instance_uuid": "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f",
        },
    }

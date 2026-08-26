"""`bin/restore-test.sh`, the disposable restore rehearsal (D524, ADR 0017).

It left ``FUTURE_STUBS`` in this run -- the fourth and last command to do so --
so what replaces ``test_future_stub_exits_ten`` for it is this module, plus the
two assertions in ``test_cli_contract`` that drive every command rather than one.

**Most of this runs the command end to end against a stubbed `docker`**, for the
reason ``test_connect_command`` runs a real process against a fake ``ssh``: the
property under test is what the command *does*, and D523 says in advance that
reading the source cannot establish it.

> **An offline scan asserting the command's source never names the live volume is
> D277's shape** -- an AST or text scan asking whether a name is *mentioned* is
> satisfied by dead code, and ``test_no_operator_command_puts_a_service_directory_-
> on_the_path`` (D464) is the standing example in this repository of a text scan
> producing a false positive.

So the rig puts a recording ``docker`` on ``PATH``, lets the command build its
own argument vectors, and reads what it would have run. Three properties get the
most attention, because all three fail silently:

*The live volume never appears in a mount.* Every ``--mount`` the command emits
is captured and checked against the live volume name from the deployed document.

*A deliberately wrong derivation is caught.* The control arm makes
``naming.restore_drill_names`` return the live volume, drives the same command,
and requires it to refuse with exit 7 having started nothing. Without that arm
the check is D509's shape -- *a control that cannot fail for the reason it is
watching for is not a control* -- because a passing subject arm alone cannot
distinguish "the guard works" from "the guard is never reached".

*``--delta`` is never on the restore's argument vector.* pgBackRest refuses a
populated data directory with exit 40 (measured, rig 8), and ``--delta`` is the
one flag that disarms that refusal.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, naming, restore_drill, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0]

RESTORE_TEST_SH = str(REPO_ROOT / "bin" / "restore-test.sh")
RESTORE_TEST_PY = str(REPO_ROOT / "bin" / "restore-test.py")

PROJECT_KEY = "fixture-alpha-dev"
LIVE_VOLUME = "apg-fixture-alpha-dev-postgres"
LIVE_CONTAINER = "apg-fixture-alpha-dev-postgres-1"
COMPOSE_PROJECT = "apg-fixture-alpha-dev"
STANZA = "fixture-alpha-dev"
GENERATION = "/var/lib/agentic-postgres/secrets/fixture-alpha-dev/20260825T000000Z-abcd"


# ---------------------------------------------------------------------------
# The command's contract, without a daemon
# ---------------------------------------------------------------------------


def run(*args: str, env: dict[str, str] | None = None, cwd: Path | None = None):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env if env is None else {**os.environ, **env},
    )


def test_help_documents_both_flags_and_the_contract() -> None:
    """The contract paragraph is Session 1's, unchanged, because it was right."""
    result = run(RESTORE_TEST_SH, "--help")
    assert result.returncode == 0
    for phrase in (
        "--target-time",
        "--project-dir",
        "never be able to overwrite a live data directory",
        "A restore that cannot be verified is a failed restore",
    ):
        assert phrase in result.stdout, f"--help no longer says {phrase!r}"


def test_a_bare_invocation_is_missing_input_not_an_absent_capability() -> None:
    result = run(RESTORE_TEST_SH)
    assert result.returncode == 2, (
        f"expected 2, got {result.returncode}. A 10 here means the command went back "
        "to being a stub."
    )
    assert "required" in result.stderr.lower()


@pytest.mark.parametrize(
    "arguments",
    [
        ("--target-time", "2026-01-01T00:00:00Z"),
        ("--project-dir", "."),
        ("--target-time", "2026-01-01T00:00:00Z", "--nonsense", "x"),
    ],
)
def test_incomplete_input_is_refused_before_anything_runs(arguments: tuple[str, ...]) -> None:
    """Both flags are parsed for real, which is what D524 says was missing.

    The stub accepted ``--help`` and rejected everything else with exit 2 having
    parsed nothing. These arguments are refused for the *right* reason now, and
    the distinction matters because a command that rejects everything looks
    identical to a command that validates.
    """
    result = run(RESTORE_TEST_PY, *arguments)
    assert result.returncode == 2
    assert "required" in result.stderr.lower() or "unrecognized" in result.stderr.lower()


def test_a_project_directory_without_outputs_is_named_as_the_problem(tmp_path: Path) -> None:
    result = run(
        RESTORE_TEST_PY,
        "--target-time",
        "2026-01-01T00:00:00Z",
        "--project-dir",
        str(tmp_path),
    )
    # Root is checked first, so a non-root run stops at 3. Under root it is 2.
    assert result.returncode in (2, 3)


# ---------------------------------------------------------------------------
# The derivation
# ---------------------------------------------------------------------------


def test_the_drill_volume_is_never_the_live_volume() -> None:
    """Over many keys and many drill ids, and it is a derivation not a literal."""
    for key in ("a", PROJECT_KEY, "x" * 60, "project-with-a-very-long-name-indeed-" + "y" * 30):
        identity_volume = naming.compose_name(
            f"apg-{key}-postgres", context="compose_volume_postgres"
        )
        for drill_id in ("202608251200abcd", "0000", "z" * 24):
            names = naming.restore_drill_names(key, drill_id)
            assert names.volume != identity_volume
            assert names.container != names.restore_container
            assert len(names.volume) <= naming.COMPOSE_NAME_MAX


@pytest.mark.parametrize("key", ["a", PROJECT_KEY, "k" * 80])
def test_the_three_drill_names_are_distinct_for_short_and_long_keys(key: str) -> None:
    """Always three names, never two -- and the long key is why this is a test.

    The stems are ``…-restore-<id>``, ``…-restore-<id>-pg`` and
    ``…-restore-<id>-pgbackrest``. Drop the ``-pg`` and the volume and the
    instance container become the **same string** for any key short enough to
    escape truncation, while staying different for any key long enough to hit it
    -- an identity that is sometimes equal and sometimes not. A test written only
    against the long key would pass and would be measuring the fingerprint rather
    than the name (D374).
    """
    names = naming.restore_drill_names(key, "202608251200abcd")
    assert len({names.volume, names.container, names.restore_container}) == 3, names
    live = naming.compose_name(f"apg-{key}-postgres", context="compose_volume_postgres")
    assert live not in (names.volume, names.container, names.restore_container)


def test_two_drills_on_one_project_do_not_collide() -> None:
    first = naming.restore_drill_names(PROJECT_KEY, "202608251200aaaa")
    second = naming.restore_drill_names(PROJECT_KEY, "202608251200bbbb")
    assert first.volume != second.volume
    assert first.container != second.container


def test_a_truncating_key_still_separates_the_drill_from_the_live_volume() -> None:
    """The case a short key cannot reach: both names truncate, to different values.

    ``truncate`` fingerprints the *untruncated* value together with the context,
    and the two contexts differ -- which is the only reason these cannot collapse
    onto one string. Asserted rather than assumed, because
    ``evidence.ISOLATED_FIELDS`` compares identities between projects and would
    never see a collision within one.
    """
    key = "k" * 80
    live = naming.compose_name(f"apg-{key}-postgres", context="compose_volume_postgres")
    drill = naming.restore_drill_names(key, "202608251200abcd")
    assert len(live) == naming.COMPOSE_NAME_MAX
    assert len(drill.volume) == naming.COMPOSE_NAME_MAX
    assert live != drill.volume
    assert drill.volume != drill.container


@pytest.mark.parametrize("bad", ["", "ABC", "abc", "with-a-dash", "a" * 25, "id_1", "../x"])
def test_a_drill_id_that_is_not_an_identifier_is_refused(bad: str) -> None:
    """The one component of a derived name that does not come from the identity.

    A name assembled from an unvalidated component is a name whose shape depends
    on its caller. ``../x`` is in this list because a drill id reaches a volume
    name and an evidence filename.
    """
    with pytest.raises(naming.NamingError):
        naming.restore_drill_names(PROJECT_KEY, bad)


# ---------------------------------------------------------------------------
# The disposability check, driven directly
# ---------------------------------------------------------------------------


def _plan(**overrides: Any) -> restore_drill.DrillPlan:
    names = overrides.pop("names", naming.restore_drill_names(PROJECT_KEY, "202608251200abcd"))
    defaults: dict[str, Any] = {
        "image": "sha256:deadbeef",
        "names": names,
        "stanza": STANZA,
        "database": "fixture_alpha_dev",
        "project_key": PROJECT_KEY,
        "live_container": LIVE_CONTAINER,
        "live_volume": LIVE_VOLUME,
        "live_mount_sources": frozenset({LIVE_VOLUME, f"{GENERATION}/postgres/x"}),
        "inherited": (
            restore_drill.Mount(
                source=f"{GENERATION}/postgres/backup_r2_access_key_id",
                target="/run/secrets/backup_r2_access_key_id",
                readonly=True,
                kind="bind",
            ),
        ),
        "environment": {"PGBACKREST_REPO1_CIPHER_PASS": "not-a-real-value"},
        "network": "apg-fixture-alpha-dev-backup",
    }
    defaults.update(overrides)
    return restore_drill.DrillPlan(**defaults)


def test_a_correct_plan_is_accepted() -> None:
    """The subject arm. On its own it proves nothing; see the four below."""
    plan = _plan()
    restore_drill.assert_disposable(plan, restore_drill.restore_arguments(plan, "2026-01-01"))


def test_a_drill_volume_equal_to_the_live_volume_is_refused() -> None:
    """The control D523 asks for: a deliberately wrong derivation must be caught."""
    plan = _plan(names=naming.RestoreDrillNames(LIVE_VOLUME, "c", "r"))
    with pytest.raises(restore_drill.DisposabilityError, match="live data volume"):
        restore_drill.assert_disposable(plan, restore_drill.restore_arguments(plan, "2026-01-01"))


def test_a_drill_volume_the_live_container_already_mounts_is_refused() -> None:
    """Not the data volume alone. Any volume the live cluster holds."""
    borrowed = f"{GENERATION}/postgres/x"
    plan = _plan(names=naming.RestoreDrillNames(borrowed, "c", "r"))
    with pytest.raises(restore_drill.DisposabilityError, match="already mounted"):
        restore_drill.assert_disposable(plan, restore_drill.restore_arguments(plan, "2026-01-01"))


def test_a_mount_naming_the_live_volume_is_refused() -> None:
    """The derivation is right and the mount plan is wrong -- a different defect."""
    plan = _plan(
        inherited=(
            restore_drill.Mount(
                source=LIVE_VOLUME, target="/run/secrets/x", readonly=True, kind="volume"
            ),
        )
    )
    with pytest.raises(restore_drill.DisposabilityError, match="live data volume"):
        restore_drill.assert_disposable(plan, restore_drill.restore_arguments(plan, "2026-01-01"))


def test_a_writable_inherited_mount_is_refused() -> None:
    """Everything the drill inherits, it reads.

    A writable `pgbackrest.conf` is a config the drill could rewrite and the next
    `archive-push` would read.
    """
    plan = _plan(
        inherited=(
            restore_drill.Mount(
                source=f"{GENERATION}/postgres/pgbackrest.conf",
                target=runtime_override.PGBACKREST_CONF_CONTAINER_PATH,
                readonly=False,
                kind="bind",
            ),
        )
    )
    with pytest.raises(restore_drill.DisposabilityError, match="writable"):
        restore_drill.assert_disposable(plan, restore_drill.restore_arguments(plan, "2026-01-01"))


def test_delta_on_the_argument_vector_is_refused() -> None:
    """pgBackRest's exit-40 refusal is the outer guard, and this does not disarm it."""
    plan = _plan()
    arguments = (*restore_drill.restore_arguments(plan, "2026-01-01"), "--delta")
    with pytest.raises(restore_drill.DisposabilityError, match="--delta"):
        restore_drill.assert_disposable(plan, arguments)


def test_the_restore_argument_vector_carries_no_delta_and_overrides_the_log_level() -> None:
    """The log level is asserted as the LITERAL `info`, and that is the point.

    The first version of this test read
    ``f"--log-level-console={restore_drill.RESTORE_LOG_LEVEL}" in arguments`` and
    Run 8's battery arm Q5 -- flipping that constant to ``warn`` -- **survived**.
    It had to: both sides of the comparison moved together, which is CLAUDE.md
    §6's *a test comparing two constants is not testing the thing between them*.

    `info` is not a preference. It is a measured property of pgBackRest: at
    ``warn``, the level `build_pgbackrest_conf` renders, a **successful restore
    prints zero bytes on both streams**, so the backup set would be unreadable
    and every drill would publish an empty field. The literal is written here so
    that changing the constant fails.
    """
    plan = _plan()
    arguments = restore_drill.restore_arguments(plan, "2026-08-25 10:45:02.599903+00")
    assert "--delta" not in arguments
    assert "--log-level-console=info" in arguments
    assert restore_drill.RESTORE_LOG_LEVEL == "info"
    assert "--target-action=promote" in arguments
    assert "--type=time" in arguments
    assert f"--stanza={STANZA}" in arguments


def test_the_drill_instance_turns_archiving_off() -> None:
    """A promoted restore is on timeline 2 and must not push it into the stanza."""
    assert restore_drill.archive_mode_is_off(restore_drill.instance_command())
    assert not restore_drill.archive_mode_is_off(("postgres", "-c", "archive_mode=on"))


def test_the_data_mount_is_the_drill_volume_at_the_images_own_volume_path() -> None:
    plan = _plan()
    assert plan.data_mount.source == plan.names.volume
    assert plan.data_mount.target == runtime_override.POSTGRES_VOLUME_TARGET
    assert plan.data_mount.readonly is False
    assert "readonly" not in plan.data_mount.as_mount_argument()
    assert plan.inherited[0].as_mount_argument().endswith(",readonly")


# ---------------------------------------------------------------------------
# Reading the live container
# ---------------------------------------------------------------------------


def _inspect(**overrides: Any) -> dict[str, Any]:
    document = {
        "Name": f"/{LIVE_CONTAINER}",
        "Image": "sha256:deadbeef",
        "Config": {
            "Env": [
                "POSTGRES_DB=fixture_alpha_dev",
                "POSTGRES_PASSWORD_FILE=/run/secrets/postgres_init_superuser_password",
                "PGBACKREST_REPO1_CIPHER_PASS=not-a-real-value",
                "PGBACKREST_REPO1_S3_KEY=also-not-real",
            ]
        },
        "Mounts": [
            {"Type": "volume", "Name": LIVE_VOLUME, "Destination": "/var/lib/postgresql"},
            # Derived from the contract, not typed. Run 8b moved the three
            # backup secrets from /run/secrets to pgBackRest's config-include
            # path (ADR 0153), and a fixture spelling the old basenames would
            # have kept passing while the drill inherited nothing.
            *[
                {
                    "Type": "bind",
                    "Source": f"{GENERATION}/postgres{destination}",
                    "Destination": destination,
                }
                for destination in restore_drill.required_container_paths(_contract())
                if destination != runtime_override.PGBACKREST_CONF_CONTAINER_PATH
            ],
            {
                "Type": "bind",
                "Source": "/srv/apg/.generated/fixture-alpha-dev/pgbackrest.conf",
                "Destination": runtime_override.PGBACKREST_CONF_CONTAINER_PATH,
            },
        ],
    }
    document.update(overrides)
    return document


def _contract() -> dict[str, Any]:
    from agentic_postgres.secrets_contract import load_secret_contract

    return load_secret_contract(REPO_ROOT / "secrets.required.yaml")


def test_the_required_paths_come_from_the_secret_contract() -> None:
    """Not typed here: the target file names belong to `secrets.required.yaml`.

    Since Run 8b the three credentials land in pgBackRest's config-include path
    rather than /run/secrets (ADR 0153), and this reads that off the contract --
    so the drill follows the credential wherever the contract puts it, which is
    what ADR 0151 §2 was built for.
    """
    from agentic_postgres.secrets_contract import PGBACKREST_INCLUDE_DIR

    # **The literal, not the constant.** Battery arm R7 moved
    # `PGBACKREST_INCLUDE_DIR` to `/etc/pgbackrest/includes` and **survived**,
    # because every assertion derived its expectation from that same constant --
    # CLAUDE.md §6's *a test comparing two constants is not testing the thing
    # between them*, and the second instance of it this session after Q5.
    #
    # This path is not a choice. It is pgBackRest's own default, measured:
    # `pgbackrest help backup config-include-path` prints
    # `default: /etc/pgbackrest/conf.d`, and nothing sets the option. Any other
    # directory is one pgBackRest does not read, which is D558 again.
    assert PGBACKREST_INCLUDE_DIR == "/etc/pgbackrest/conf.d"

    paths = restore_drill.required_container_paths(_contract())
    assert runtime_override.PGBACKREST_CONF_CONTAINER_PATH in paths
    assert len(paths) == 4, paths
    credentials = [p for p in paths if p != runtime_override.PGBACKREST_CONF_CONTAINER_PATH]
    assert len(credentials) == 3, credentials
    for path in credentials:
        assert path.startswith(PGBACKREST_INCLUDE_DIR + "/"), (
            f"{path} is not where pgBackRest reads its includes from, so nothing "
            "would read it -- which is the whole of D558"
        )
        assert path.endswith(".conf"), (
            f"{path} does not end in .conf, and pgBackRest concatenates only .conf "
            "files from its include path"
        )


def test_only_the_archivers_own_material_is_carried_forward() -> None:
    """An allowlist of destinations, and the data volume is not on it."""
    mounts = restore_drill.inherited_mounts(
        _inspect(), restore_drill.required_container_paths(_contract())
    )
    sources = {mount.source for mount in mounts}
    assert LIVE_VOLUME not in sources
    assert all(mount.readonly for mount in mounts)
    assert len(mounts) == 4


def test_a_database_container_missing_the_config_mount_is_refused() -> None:
    """It cannot be archiving, so there is nothing for a drill to restore from."""
    inspect = _inspect()
    inspect["Mounts"] = [
        mount
        for mount in inspect["Mounts"]
        if mount["Destination"] != runtime_override.PGBACKREST_CONF_CONTAINER_PATH
    ]
    with pytest.raises(restore_drill.DrillError, match="does not mount"):
        restore_drill.inherited_mounts(inspect, restore_drill.required_container_paths(_contract()))


def test_only_the_pgbackrest_environment_namespace_is_inherited() -> None:
    environment = restore_drill.inherited_environment(_inspect())
    assert set(environment) == {"PGBACKREST_REPO1_CIPHER_PASS", "PGBACKREST_REPO1_S3_KEY"}
    assert "POSTGRES_PASSWORD_FILE" not in environment


def test_an_archiver_with_no_credential_environment_yields_an_empty_map() -> None:
    """Today's state (D558), and it must not read as an error here.

    Nothing populates the `PGBACKREST_*` namespace yet. The drill carries forward
    what exists, so this returns `{}` -- and the restore then fails with
    pgBackRest's own `[037]: ... requires option: repo1-cipher-pass` rather than
    with a message this repository invented about a gap.
    """
    inspect = _inspect()
    inspect["Config"]["Env"] = ["POSTGRES_DB=x"]
    assert restore_drill.inherited_environment(inspect) == {}


# ---------------------------------------------------------------------------
# Reading the repository and the restored instance
# ---------------------------------------------------------------------------


def test_the_backup_set_is_read_from_pgbackrests_own_line() -> None:
    """The exact string rig 8 measured, at --log-level-console=info."""
    output = (
        "2026-08-25 10:45:06.244 P00   INFO: repo1: restore backup set 20260825-104447F, "
        "recovery will start at 2026-08-25 10:44:47\n"
    )
    assert restore_drill.parse_backup_set(output) == "20260825-104447F"


def test_a_silent_restore_fails_the_drill_rather_than_publishing_nothing() -> None:
    """The empty capture is the case that matters.

    A successful restore prints **zero bytes** at the rendered `warn` level
    (measured). A command that returned None here would publish an empty backup
    set on every drill that worked, and an empty field is indistinguishable from
    one nobody filled in.
    """
    with pytest.raises(restore_drill.DrillError, match="did not name a backup set"):
        restore_drill.parse_backup_set("")


def test_the_backup_type_comes_from_info_and_not_from_the_labels_last_letter() -> None:
    backups = [
        {"label": "20260825-104447F", "type": "full"},
        {"label": "20260825-110000I", "type": "incr"},
    ]
    assert restore_drill.backup_set_type(backups, "20260825-104447F") == "full"
    with pytest.raises(restore_drill.DrillError, match="does not list a backup set"):
        restore_drill.backup_set_type(backups, "20260825-999999F")


def _observed(**overrides: Any) -> dict[str, Any]:
    document = {
        "requested_target": "2026-08-25 10:45:02.599903+00",
        "achieved_recovery_point": "2026-08-25 10:45:00.109084+00",
        "achieved_lsn": "0/50039F0",
        "timeline_id": 2,
        "schema_version": "20260101000000",
        "schema_migration_count": 21,
    }
    document.update(overrides)
    return document


_SMOKE_OK = {"answers_a_query": {"passed": True}, "left_recovery": {"passed": True}}


def test_a_verified_drill_passes() -> None:
    verdict = restore_drill.drill_verdict(
        observed=_observed(),
        repository={"latest_recoverable_time": "2026-08-25T10:42:29Z"},
        smoke=_SMOKE_OK,
    )
    assert verdict["passed"], verdict["reasons"]


def test_a_null_achieved_point_fails_because_it_means_the_wrong_instance() -> None:
    """`pg_last_xact_replay_timestamp()` is NULL on a cluster that never recovered.

    Measured, live control. So a null here is a drill that read something which
    is not a restore, and it is a failure rather than a missing value.
    """
    verdict = restore_drill.drill_verdict(
        observed=_observed(achieved_recovery_point=None),
        repository={"latest_recoverable_time": "2026-08-25T10:42:29Z"},
        smoke=_SMOKE_OK,
    )
    assert not verdict["passed"]
    assert any("never recovered" in reason for reason in verdict["reasons"])


def test_a_timeline_that_did_not_advance_fails() -> None:
    """Timeline 1 is what the live cluster is on; a promoted restore is on 2."""
    verdict = restore_drill.drill_verdict(
        observed=_observed(timeline_id=1),
        repository={"latest_recoverable_time": "2026-08-25T10:42:29Z"},
        smoke=_SMOKE_OK,
    )
    assert not verdict["passed"]
    assert any("timeline" in reason for reason in verdict["reasons"])


def test_landing_after_the_published_floor_is_not_an_inconsistency() -> None:
    """D550: `latest_recoverable_time` is a proven floor, and WAL extends past it."""
    verdict = restore_drill.drill_verdict(
        observed=_observed(achieved_recovery_point="2026-08-25T10:42:30Z"),
        repository={"latest_recoverable_time": "2026-08-25T10:42:29Z"},
        smoke=_SMOKE_OK,
    )
    assert verdict["passed"], verdict["reasons"]


def test_the_two_sources_spell_one_instant_two_ways_and_are_still_ordered() -> None:
    """The regression this module's own subject arm caught (D563).

    `pgbackrest info` reaches the verdict through ``backup_report`` as
    ``2026-08-25T10:42:29Z``; ``pg_last_xact_replay_timestamp()`` reaches it
    through psql as ``2026-08-25 10:45:00.109084+00``. **Compared as strings the
    second sorts first**, because a space is 0x20 and ``T`` is 0x54 -- so a drill
    that landed nearly three minutes after the floor reads as landing before it,
    and every correct drill fails with a sentence about an inconsistency that was
    the comparison's own.

    Written as a test rather than a comment because a string comparison is what
    anybody would write here, and it is right for as long as the two formats
    happen to agree, which is never.
    """
    achieved = "2026-08-25 10:45:00.109084+00"
    floor = "2026-08-25T10:42:29Z"
    assert achieved < floor, (
        "the premise of this test no longer holds: the two spellings now sort "
        "correctly as strings, so this regression cannot recur in this form"
    )
    assert restore_drill.instant(achieved) > restore_drill.instant(floor)

    verdict = restore_drill.drill_verdict(
        observed=_observed(achieved_recovery_point=achieved),
        repository={"latest_recoverable_time": floor},
        smoke=_SMOKE_OK,
    )
    assert verdict["passed"], verdict["reasons"]


@pytest.mark.parametrize(
    ("value", "expected_iso"),
    [
        ("2026-08-25T10:42:29Z", "2026-08-25T10:42:29+00:00"),
        ("2026-08-25 10:45:00.109084+00", "2026-08-25T10:45:00.109084+00:00"),
    ],
)
def test_both_timestamp_spellings_parse(value: str, expected_iso: str) -> None:
    parsed = restore_drill.instant(value)
    assert parsed is not None
    assert parsed.isoformat() == expected_iso


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_absent_timestamp_is_none_rather_than_an_error(value: str | None) -> None:
    assert restore_drill.instant(value) is None


def test_an_unparseable_timestamp_raises_rather_than_degrading_to_unknown() -> None:
    """A comparison that silently becomes "unknown" is how the defect comes back."""
    with pytest.raises(restore_drill.DrillError, match="not a timestamp"):
        restore_drill.instant("last tuesday")


def test_landing_before_the_published_floor_is_an_inconsistency() -> None:
    verdict = restore_drill.drill_verdict(
        observed=_observed(achieved_recovery_point="2026-08-25T10:00:00Z"),
        repository={"latest_recoverable_time": "2026-08-25T10:42:29Z"},
        smoke=_SMOKE_OK,
    )
    assert not verdict["passed"]
    assert any("EARLIER" in reason for reason in verdict["reasons"])


def test_a_failing_smoke_check_fails_the_drill() -> None:
    verdict = restore_drill.drill_verdict(
        observed=_observed(),
        repository={"latest_recoverable_time": "2026-08-25T10:42:29Z"},
        smoke={"answers_a_query": {"passed": False}},
    )
    assert not verdict["passed"]
    assert any("smoke" in reason for reason in verdict["reasons"])


# ---------------------------------------------------------------------------
# The evidence document
# ---------------------------------------------------------------------------


def _evidence(**overrides: Any) -> dict[str, Any]:
    plan = _plan()
    arguments: dict[str, Any] = {
        "plan": plan,
        "drill_id": "202608251200abcd",
        "requested_target": "2026-08-25 10:45:02.599903+00",
        "observed": _observed(),
        "repository": {"latest_recoverable_time": "2026-08-25T10:42:29Z"},
        "backup_set": {"label": "20260825-104447F", "type": "full"},
        "timings": {
            "restore_seconds": 5.337,
            "recovery_seconds": 3.4,
            "rto_seconds": 9.1,
            "pgbackrest_reported_ms": 5337,
        },
        "smoke": _SMOKE_OK,
        "release": "0.10.0",
    }
    arguments.update(overrides)
    return restore_drill.evidence_document(**arguments)


def test_the_evidence_document_records_every_field_the_requirement_names() -> None:
    """`REC-EVID-001`: backup set, requested AND achieved point, RTO, schema version."""
    document = _evidence()
    assert document["backup_set"] == {"label": "20260825-104447F", "type": "full"}
    assert document["recovery"]["requested_target"] == "2026-08-25 10:45:02.599903+00"
    assert document["recovery"]["achieved_recovery_point"] == "2026-08-25 10:45:00.109084+00"
    assert document["recovery"]["achieved_lsn"] == "0/50039F0"
    assert document["recovery"]["latest_recoverable_time"] == "2026-08-25T10:42:29Z"
    assert document["timing"]["rto_seconds"] == 9.1
    assert document["schema_version"] == "20260101000000"
    assert document["verdict"]["passed"] is True


def test_requested_and_achieved_are_separate_fields_and_do_differ() -> None:
    """D529's whole point: a restore that lands early is what the pair exposes."""
    recovery = _evidence()["recovery"]
    assert recovery["requested_target"] != recovery["achieved_recovery_point"]
    assert recovery["achieved_is_at_or_after_floor"] is True


def test_the_document_carries_no_secret_value() -> None:
    """The plan's environment holds one. It must not reach the document."""
    serialized = json.dumps(_evidence())
    assert "not-a-real-value" not in serialized
    assert "PGBACKREST_REPO1_CIPHER_PASS" not in serialized
    for forbidden in ("password", "secret", "cipher", "access_key"):
        assert forbidden not in serialized.lower(), f"the evidence document mentions {forbidden}"


def test_the_document_records_who_measured_the_time() -> None:
    """D529: RTO is wall time this command measured, not a number from anywhere else."""
    timing = _evidence()["timing"]
    assert "restore-test.py" in timing["measured_by"]
    # pgBackRest's own elapsed time is BESIDE ours, never instead of it: it
    # excludes recovery, so it is smaller than the RTO by that whole span.
    assert timing["pgbackrest_reported_ms"] == 5337
    assert timing["rto_seconds"] > timing["restore_seconds"]


# ---------------------------------------------------------------------------
# End to end, against a recording `docker`
# ---------------------------------------------------------------------------
#
# The command is imported and driven **in this process**, not spawned. Two
# reasons, and the second is the important one:
#
#   * `bin/restore-test.py` is not importable by name, so it is loaded by path
#     -- which is what lets `os.geteuid` and `naming.restore_drill_names` be
#     monkeypatched for the control arm.
#   * **The alternative was `skipif os.geteuid() != 0`, and a skip is not a
#     pass.** The three assertions below are the ones D523 exists for; guarding
#     them on root would have left them skipped in every run of this suite and
#     green in the gate's summary line. That is the defect this repository keeps
#     producing, one layer up.
#
# `docker` is a recording stub on PATH. It answers every query the drill makes
# so that the whole command runs to completion and writes a real evidence
# document, and it starts nothing -- so what the rig reads is the argument
# vector the daemon WOULD have been handed.


_STUB_DOCKER = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"${APG_DOCKER_LOG}"

sql_answer() {
  # Order matters, most specific first: `count(*)` appears in the migration
  # count AND in the RLS read, and `api.notes` is what tells them apart.
  case "$*" in
    *api.create_note*)                printf '%s\n' "${APG_WRITTEN_NOTE_ID}" ;;
    # The RLS read, both halves. The stub answers by the CLAIM in the statement,
    # which is what makes the two arms distinguishable at all: the drill owner
    # sees rows and the synthetic foreign identity sees none. A stub answering
    # one number for both would let a dropped policy pass.
    *"${APG_FOREIGN_OWNER}"*api.notes*) printf '0\n' ;;
    *"${APG_SMOKE_OWNER}"*api.notes*)   printf '3\n' ;;
    *api.notes*)                      printf '\n' ;;
    *"ORDER BY version"*)             printf '%s\n' "${APG_SCHEMA_VERSIONS}" ;;
    *pg_is_in_recovery*)              printf 'f\n' ;;
    *recovery_target_time*)           printf '%s\n' "${APG_REQUESTED_TARGET}" ;;
    *pg_last_xact_replay_timestamp*)  printf '%s\n' "${APG_ACHIEVED_POINT}" ;;
    *pg_last_wal_replay_lsn*)         printf '0/50039F0\n' ;;
    *timeline_id*)                    printf '2\n' ;;
    *"max(version)"*)                 printf '20260101000000\n' ;;
    *"count(*)"*)                     printf '21\n' ;;
    *"SELECT 1"*)                     printf '1\n' ;;
    *)                                printf '\n' ;;
  esac
}

case "$1" in
  ps)
    printf '%s\n' "${APG_LIVE_CONTAINER}"
    ;;
  inspect)
    for arg in "$@"; do
      [ "${arg}" = "{{.State.Running}}" ] && { printf 'true\n'; exit 0; }
    done
    shift
    [ "$1" = "${APG_LIVE_CONTAINER}" ] && { cat "${APG_INSPECT_FIXTURE}"; exit 0; }
    # Anything else is the pre-flight or the teardown asking whether a drill
    # resource exists. It does not.
    exit 1
    ;;
  volume)
    exit 1
    ;;
  exec)
    case "$*" in
      *"info --output=json"*) cat "${APG_INFO_FIXTURE}" ;;
      *psql*)                 sql_answer "$@" ;;
    esac
    exit 0
    ;;
  run)
    case "$*" in
      *" restore "*)
        # **The measured behaviour, reproduced**: pgBackRest prints the backup
        # set only at info level. At the rendered `warn` a successful restore
        # emits ZERO BYTES on both streams, so a stub that printed regardless
        # would let a drill asking for `warn` look identical to one asking for
        # `info` -- which is exactly how battery arm Q5 survived its first run.
        case "$*" in
          *--log-level-console=info*)
            printf '%s\n' "${APG_RESTORE_LINE}"
            printf 'P00   INFO: restore command end: completed successfully (5337ms)\n'
            ;;
        esac
        ;;
    esac
    exit "${APG_RUN_EXIT:-0}"
    ;;
  logs)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
"""

_RESTORE_LINE = (
    "2026-08-25 10:45:06.244 P00   INFO: repo1: restore backup set 20260825-104447F, "
    "recovery will start at 2026-08-25 10:44:47"
)
_REQUESTED_TARGET = "2026-08-25 10:45:02.599903+00"
_ACHIEVED_POINT = "2026-08-25 10:45:00.109084+00"


SMOKE_OWNER = "11111111-2222-4333-8444-555555555555"


def _released_versions() -> list[str]:
    lock = json.loads((REPO_ROOT / "migrations" / "released.lock.json").read_text(encoding="utf-8"))
    return [str(entry["version"]) for entry in lock["migrations"]]


def _foreign_owner() -> str:
    """The synthetic identity the drill asserts in order to see nothing.

    Read off the command rather than written here: two spellings of one uuid is
    a stub that answers `0` for an identity the product never asks about, and
    the RLS arm would then pass without the product's own second read.
    """
    return _load_command().SMOKE_FOREIGN_OWNER


def _load_command():
    """`bin/restore-test.py`, imported by path because its name has a hyphen."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("apg_restore_test", RESTORE_TEST_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A recording `docker` on PATH, a rendered project directory, and fixtures."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    stub = binaries / "docker"
    stub.write_text(_STUB_DOCKER, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    project_dir = tmp_path / "generated" / PROJECT_KEY
    project_dir.mkdir(parents=True)
    (project_dir / "outputs.json").write_text(
        json.dumps(
            {
                "project": {"key": PROJECT_KEY},
                "database": {
                    "name": "fixture_alpha_dev",
                    "roles": {"app_runtime": "apg_fixture_alpha_dev_app_runtime"},
                },
                "backup": {"enabled": True, "stanza": STANZA},
                "release": {"version": "0.10.0"},
                "compose": {
                    # `project_name` is what the database selector filters on
                    # since D587 -- Compose's own label, because `postgres` does
                    # not carry `apg.project.key`.
                    "project_name": COMPOSE_PROJECT,
                    "volumes": {"postgres": LIVE_VOLUME},
                    "networks": {"backup": "apg-fixture-alpha-dev-backup"},
                },
            }
        ),
        encoding="utf-8",
    )

    inspect_fixture = tmp_path / "inspect.json"
    inspect_fixture.write_text(json.dumps([_inspect()]), encoding="utf-8")

    info_fixture = tmp_path / "info.json"
    info_fixture.write_text(
        json.dumps(
            [
                {
                    "name": STANZA,
                    "status": {"code": 0, "message": "ok"},
                    "backup": [
                        {
                            "label": "20260825-104447F",
                            "type": "full",
                            "timestamp": {"start": 1787654500, "stop": 1787654549},
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    log = tmp_path / "docker.log"
    log.touch()

    for name, value in (
        ("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}"),
        ("APG_DOCKER_LOG", str(log)),
        ("APG_INSPECT_FIXTURE", str(inspect_fixture)),
        ("APG_INFO_FIXTURE", str(info_fixture)),
        ("APG_LIVE_CONTAINER", LIVE_CONTAINER),
        ("APG_RESTORE_LINE", _RESTORE_LINE),
        ("APG_REQUESTED_TARGET", _REQUESTED_TARGET),
        ("APG_ACHIEVED_POINT", _ACHIEVED_POINT),
        # Read from the same lock `released_versions()` reads, so a schema check
        # that passes here is a check comparing the real released set against
        # itself -- which is what the host arm compares against a real cluster.
        ("APG_SCHEMA_VERSIONS", "\n".join(_released_versions())),
        ("APG_SMOKE_OWNER", SMOKE_OWNER),
        ("APG_FOREIGN_OWNER", _foreign_owner()),
        ("APG_WRITTEN_NOTE_ID", "6f1c3a10-0000-4000-8000-00000000abcd"),
    ):
        monkeypatch.setenv(name, value)

    module = _load_command()
    # The drill runs as root on a host. Patched rather than skipped: see the
    # note at the top of this section.
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)

    return {
        "log": log,
        "module": module,
        "project_dir": project_dir,
        "evidence_dir": tmp_path / "evidence",
    }


def _drive(rig: dict[str, Any]) -> int:
    return rig["module"].main(
        [
            "--target-time",
            _REQUESTED_TARGET,
            "--project-dir",
            str(rig["project_dir"]),
            "--evidence-dir",
            str(rig["evidence_dir"]),
            "--smoke-owner-id",
            SMOKE_OWNER,
        ]
    )


def _mount_arguments(log: Path) -> list[str]:
    """Every `--mount` value the command handed the recording docker."""
    values: list[str] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        for index, part in enumerate(parts):
            if part == "--mount" and index + 1 < len(parts):
                values.append(parts[index + 1])
    return values


def test_the_drill_runs_to_completion_against_a_stubbed_daemon(rig: dict[str, Any]) -> None:
    """The subject arm, and the premise of the three that follow.

    An arm that reports "the live volume never appeared" without having built a
    single mount cannot tell success from having done nothing -- D557, the rig
    defect Run 7 paid for. So this asserts the drill actually completed and wrote
    a document before anything else reads its argument vectors.
    """
    assert _drive(rig) == 0, "the drill did not report a verified restore"

    documents = list(rig["evidence_dir"].glob("restore-drill-*.json"))
    assert len(documents) == 1, documents
    evidence = json.loads(documents[0].read_text(encoding="utf-8"))
    assert evidence["verdict"]["passed"] is True, evidence["verdict"]["reasons"]
    assert evidence["backup_set"]["label"] == "20260825-104447F"
    assert evidence["backup_set"]["type"] == "full"
    assert evidence["recovery"]["requested_target"] == _REQUESTED_TARGET
    assert evidence["recovery"]["achieved_recovery_point"] == _ACHIEVED_POINT
    assert evidence["recovery"]["timeline_id"] == 2
    assert evidence["schema_version"] == "20260101000000"
    assert evidence["timing"]["rto_seconds"] >= 0


def test_the_command_never_hands_docker_the_live_volume(rig: dict[str, Any]) -> None:
    """D523's proof: the argument vector, not the source.

    A text or AST scan asking whether the source *names* the live volume is
    satisfied by dead code (D277) and has produced a false positive in this
    repository before (D464). This drives the command until it emits mounts and
    reads them.
    """
    assert _drive(rig) == 0
    mounts = _mount_arguments(rig["log"])
    assert mounts, "the command built no mount at all, so this arm proves nothing"
    for mount in mounts:
        assert f"source={LIVE_VOLUME}" not in mount, f"the live volume reached a mount: {mount}"
    data_mounts = [m for m in mounts if f"target={runtime_override.POSTGRES_VOLUME_TARGET}" in m]
    assert data_mounts, "nothing was mounted at the image's own volume path"
    for mount in data_mounts:
        assert "-restore-" in mount, f"the data mount is not a drill volume: {mount}"


def test_the_command_never_passes_delta_and_never_mounts_read_write_material(
    rig: dict[str, Any],
) -> None:
    assert _drive(rig) == 0
    recorded = rig["log"].read_text(encoding="utf-8")
    assert "--delta" not in recorded
    for mount in _mount_arguments(rig["log"]):
        if f"target={runtime_override.POSTGRES_VOLUME_TARGET}" in mount:
            continue
        assert mount.endswith(",readonly"), f"an inherited mount is writable: {mount}"


def test_the_drill_instance_is_started_with_archiving_off(rig: dict[str, Any]) -> None:
    """A promoted restore is on timeline 2; archiving it would corrupt the stanza."""
    assert _drive(rig) == 0
    runs = [
        line
        for line in rig["log"].read_text(encoding="utf-8").splitlines()
        if line.startswith("run ") and "--entrypoint pgbackrest" not in line
    ]
    assert len(runs) == 1, runs
    assert "archive_mode=off" in runs[0]


def test_the_credential_environment_is_forwarded_but_never_written_down(
    rig: dict[str, Any],
) -> None:
    """The one value in this rig that must reach docker and must not reach disk."""
    assert _drive(rig) == 0
    recorded = rig["log"].read_text(encoding="utf-8")
    assert "PGBACKREST_REPO1_CIPHER_PASS=not-a-real-value" in recorded, (
        "the archiver's environment did not reach the drill, so a real drill could not authenticate"
    )
    document = next(rig["evidence_dir"].glob("restore-drill-*.json"))
    assert "not-a-real-value" not in document.read_text(encoding="utf-8")


def test_the_smoke_checks_run_and_are_recorded(rig: dict[str, Any]) -> None:
    """`REC-SMOKE-001`'s logic, driven offline (Run 9).

    The requirement's proof is a host test that has never executed, so this arm
    exists to make its *logic* something that has. It drives the real
    `smoke_checks` against the recording daemon and asserts the six checks that
    should be applicable are, and that all six pass.
    """
    assert _drive(rig) == 0
    evidence = json.loads(next(rig["evidence_dir"].glob("restore-drill-*.json")).read_text())
    smoke = evidence["smoke"]

    expected = {
        "answers_a_query",
        "left_recovery",
        "carries_a_schema_version",
        "schema_matches_the_release",
        "rls_read_is_owner_scoped",
        "write_rpc_succeeds",
    }
    assert set(smoke) == expected, sorted(set(smoke) ^ expected)
    for name, result in smoke.items():
        assert result["applicable"] is True, f"{name} did not run: {result['detail']}"
        assert result["passed"] is True, f"{name}: {result['detail']}"


def test_the_rls_read_asks_as_the_runtime_role_and_asserts_both_directions(
    rig: dict[str, Any],
) -> None:
    """The half that fails when a policy is dropped is the SECOND read.

    "the owner sees rows" passes against a table with RLS disabled. So the check
    asserts an unrelated identity sees **none**, and this reads the recorded
    daemon traffic to prove the product actually issued both reads -- as
    `app_runtime`, not as the superuser, because FORCE RLS exempts a superuser
    and the same SELECT as `postgres` returns every row (ADR 0065/0066).
    """
    assert _drive(rig) == 0
    recorded = rig["log"].read_text(encoding="utf-8")
    reads = [line for line in recorded.splitlines() if "api.notes" in line]
    assert len(reads) == 2, f"expected two RLS reads, saw {len(reads)}"
    assert any(SMOKE_OWNER in line for line in reads), "the drill owner was never asserted"
    assert any(_foreign_owner() in line for line in reads), (
        "no second identity was asserted, so a dropped policy would pass"
    )
    for line in reads:
        assert "SET LOCAL ROLE apg_fixture_alpha_dev_app_runtime" in line, (
            "the RLS read did not set the runtime role, so it ran as the superuser "
            "-- which FORCE RLS exempts"
        )


def test_without_an_owner_id_the_rls_checks_are_not_applicable_rather_than_passing(
    rig: dict[str, Any],
) -> None:
    """A check with nothing to do must not report success.

    This is the shape this repository keeps producing, and `REC-SMOKE-001` reads
    `applicable` as well as `passed` so that a drill run without
    `--smoke-owner-id` cannot satisfy the requirement.
    """
    assert (
        rig["module"].main(
            [
                "--target-time",
                _REQUESTED_TARGET,
                "--project-dir",
                str(rig["project_dir"]),
                "--evidence-dir",
                str(rig["evidence_dir"]),
            ]
        )
        == 0
    )
    smoke = json.loads(next(rig["evidence_dir"].glob("restore-drill-*.json")).read_text())["smoke"]
    for name in ("rls_read_is_owner_scoped", "write_rpc_succeeds"):
        assert smoke[name]["applicable"] is False, name
        assert smoke[name]["passed"] is None, f"{name} reported a verdict it did not earn"
    # And the drill as a whole still passes: a check that did not run is not a
    # failure either. `REC-SMOKE-001` is what refuses this document, not the
    # drill's own verdict.
    assert smoke["schema_matches_the_release"]["passed"] is True


def test_a_schema_set_that_differs_from_the_release_fails_the_drill(
    rig: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Set equality, not a count.

    A cluster restored from another release can carry the right NUMBER of
    migrations and a different set, and a count would report it healthy. The
    stub drops one version and adds one, keeping the count identical.
    """
    versions = _released_versions()
    tampered = [*versions[:-1], "29991231000000"]
    assert len(tampered) == len(versions)
    monkeypatch.setenv("APG_SCHEMA_VERSIONS", "\n".join(tampered))

    assert _drive(rig) == 6, "a restored cluster from another release was accepted"
    evidence = json.loads(next(rig["evidence_dir"].glob("restore-drill-*.json")).read_text())
    check = evidence["smoke"]["schema_matches_the_release"]
    assert check["applicable"] is True
    assert check["passed"] is False
    assert "only in the restore" in check["detail"]
    assert evidence["verdict"]["passed"] is False


def test_a_wrong_derivation_is_caught_and_nothing_is_started(
    rig: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control arm, and without it the four above prove only that nothing broke.

    ``naming.restore_drill_names`` is made to return the live volume -- a
    *derivation* producing the forbidden name, which is precisely the failure
    D523 says a source scan cannot see. The command must exit 7 and must not have
    run a single container.

    D509: *a control that cannot fail for the reason it is watching for is not a
    control.* This one fails for exactly that reason, and the assertion that no
    `docker run` was recorded is what makes "refused" mean "refused before
    acting" rather than "refused afterwards".
    """
    original = naming.restore_drill_names
    monkeypatch.setattr(
        naming,
        "restore_drill_names",
        lambda key, drill_id: naming.RestoreDrillNames(
            LIVE_VOLUME,
            original(key, drill_id).container,
            original(key, drill_id).restore_container,
        ),
    )

    assert _drive(rig) == 7, "a derivation producing the live volume was not refused"
    recorded = rig["log"].read_text(encoding="utf-8")
    assert not any(line.startswith("run ") for line in recorded.splitlines()), (
        "a container was started after the derivation produced the live volume"
    )
    assert not list(rig["evidence_dir"].glob("*.json")) if rig["evidence_dir"].exists() else True


def test_the_control_arm_is_reachable(rig: dict[str, Any]) -> None:
    """Guard the control: the subject and the control must differ in outcome.

    Both arms drive the same command with the same fixtures, so if this run's
    exit code were 7 for an unrelated reason the control above would pass while
    measuring nothing.
    """
    assert _drive(rig) == 0

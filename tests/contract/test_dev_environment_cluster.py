"""What `apg dev up` actually produces. `DEV-ENV-001`, `DEV-SUBJECT-001`,
`DEV-ISO-001`, ADR 0203.

**This module runs the product's own command.** Not `docker run` with the same
arguments, not the module's functions driven by hand: `bin/apg.sh dev up`, the
line an adopter types. Three of the four defects Session 20's trip found were
found by making a proof call the product's command instead of hand-rolling the
request that command makes (D1114, D1117), and the fourth was a proof that had
never run at all.

**The isolation clauses are split with `test_dev_environment.py` on purpose.**
What docker is TOLD is asserted there, without a daemon; what the container
then IS can only be read from a running one, and is asserted here. D1161 is why
the second half exists at all: a correct environment has exactly one mount --
the anonymous volume the image declares -- so a proof asserting *no mounts*
would be red on a correct environment and green on nothing.

The environment is removed in `finally`, whatever happens.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every interpolated value below is a role or database name read from the state
# file this command wrote, which it derived from a rendered outputs document.
# None of it is caller input, and a role name cannot be bound as a parameter --
# the same judgement every other module here records.
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, dev_environment

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.database, pytest.mark.security]

APG = REPO_ROOT / "bin" / "apg.sh"
PROJECT = "project.example.yaml"
FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"


def apg(*arguments: str, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(APG), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        timeout=timeout,
    )


def docker(*arguments: str, stdin: str | None = None, timeout: int = 120):
    return subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        check=False,
        input=stdin,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def environment() -> Any:
    """One environment, built by the command, removed by the command.

    Skips exactly as the six cluster fixtures skip -- no rendered fixture, no
    docker -- so this module is absent for the same reasons they are and never
    for a new one.
    """
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    apg("dev", "down", "--project", PROJECT)
    result = apg("dev", "up", "--project", PROJECT)
    try:
        assert result.returncode == 0, (
            f"`apg dev up` exited {result.returncode}\n{result.stdout}\n{result.stderr}"
        )
        state = json.loads(
            (dev_environment.state_dir("fixture-alpha-dev") / dev_environment.STATE_FILE).read_text(
                encoding="utf-8"
            )
        )
        yield {"state": state, "stdout": result.stdout, "stderr": result.stderr}
    finally:
        apg("dev", "down", "--project", PROJECT)


def as_superuser(state: dict[str, Any], sql: str) -> str:
    result = docker(
        "exec", "-i", state["container"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", state["database"], "-c", sql,
    )  # fmt: skip
    assert result.returncode == 0, f"{sql[:80]}: {result.stderr.strip()[:300]}"
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# DEV-ENV-001 -- both ledgers, and the roles
# ---------------------------------------------------------------------------


def test_up_applies_every_planned_migration_as_the_migration_user_and_records_both_ledgers(
    environment: dict[str, Any],
) -> None:
    """Two ledgers, because they answer two questions.

    `schema_migrations` is dbmate's and records that a VERSION ran, one row per
    migration, written inside the migration's own transaction.
    `migration_ledger` is the product's and records WHICH BYTES ran, written as
    the superuser because a migration role that could write its own audit record
    could record bytes it did not execute.

    A dev cluster carrying both is one `migrate.sh status` reads the same way a
    deployment's is read -- which is the whole claim of "the product path is the
    fixture path".
    """
    state = environment["state"]
    planned = dev_environment.planned_migrations(Path(state["rendered_dir"]))
    assert len(planned) >= 32, f"only {len(planned)} migrations were planned"

    # Both tables since ADR 0206, and UNION ALL rather than a join: each set
    # records into its own, and what this asserts is that between them they
    # carry exactly the planned versions. Ordered by version across the union,
    # which is how `planned` is ordered within each set -- the two sets no
    # longer interleave by version, so this also fails if a payload landed in
    # the wrong table.
    versions = as_superuser(
        state,
        "SELECT string_agg(version, ',' ORDER BY version) FROM ("
        "SELECT version FROM app_private.schema_migrations "
        "UNION ALL SELECT version FROM app_private.project_schema_migrations) AS every_set",
    )
    assert sorted(versions.split(",")) == sorted(entry["version"] for entry in planned), (
        "the two migration tables do not carry exactly the planned versions"
    )

    # And each set's versions are in ITS OWN table, which is the property ADR
    # 0206 rests on: one table is one ordering space, and that is what refused
    # beta's deploy (D1288).
    for table, label in (
        ("app_private.schema_migrations", "release"),
        ("app_private.project_schema_migrations", "project"),
    ):
        recorded = as_superuser(
            state, f"SELECT coalesce(string_agg(version, ',' ORDER BY version), '') FROM {table}"
        )
        expected = [
            entry["version"] for entry in planned if (entry.get("set") or "release") == label
        ]
        assert [v for v in recorded.split(",") if v] == expected, (
            f"{table} does not hold exactly the {label} set's versions"
        )

    ledger = as_superuser(
        state,
        "SELECT count(*)::text || '|' || count(DISTINCT rendered_sha256)::text "
        "FROM app_private.migration_ledger",
    )
    count, distinct = ledger.split("|")
    assert int(count) == len(planned), f"migration_ledger has {count} rows, not {len(planned)}"
    assert int(distinct) == len(planned), (
        "two ledger rows share a rendered digest, so the bytes recorded are not per migration"
    )

    # The digests are the RENDERED ones, which is what makes the row evidence
    # about what ran rather than about what was committed (ADR 0028).
    recorded = {entry["version"]: entry["sha256"] for entry in planned}
    sampled = as_superuser(
        state,
        "SELECT version || '=' || rendered_sha256 FROM app_private.migration_ledger "
        "ORDER BY version LIMIT 3",
    )
    for line in sampled.splitlines():
        version, digest = line.split("=")
        assert recorded[version] == digest, f"{version}'s ledger digest is not the rendered one"


def test_dev_up_installs_the_example_projects_definitions(
    environment: dict[str, Any],
) -> None:
    """**Session 32 (ADR 0228): the install path, executed rather than scanned.**

    `apg dev up` compiles the project's definitions and installs them through
    `app_private.workflow_install_definition` -- the same compiler and the same
    statement builder the deploy's step 6d uses -- so a definition that will
    not install at step 6d fails here, on a disposable container, instead of on
    a host with the cluster already migrated.

    It is also the only place in this release where the psql invocation rig 32g
    designed is *run*: the statement on stdin through `-f -`, every value a
    `-v` variable, and a body carrying an author's prose through both. A `-c`
    here would fail with `syntax error at or near ":"` (D1684).
    """
    state = environment["state"]
    installed = as_superuser(
        state,
        "SELECT name || ' v' || version FROM app_private.workflow_definition ORDER BY name",
    )
    assert installed.splitlines() == ["notes-retry v1", "notes-roundtrip v1"], (
        f"the example project ships two definitions and the cluster holds: {installed!r}"
    )

    # The BODY made the round trip, not just the row: the prose carries commas
    # and apostrophes, and psql's `:'body'` is what quotes it.
    description = as_superuser(
        state,
        "SELECT body ->> 'description' FROM app_private.workflow_definition "
        "WHERE name = 'notes-roundtrip'",
    )
    assert description.startswith("Creates a note"), description

    # And the scopes arrived as an ARRAY, not as one element containing a comma.
    scopes = as_superuser(
        state,
        "SELECT array_to_string(required_scopes, '|') FROM app_private.workflow_definition "
        "WHERE name = 'notes-roundtrip'",
    )
    assert scopes == "notes:read|notes:write", scopes

    assert "workflows   2 definition(s) installed" in environment["stdout"], (
        "up does not say what it installed, so an operator cannot tell an empty "
        "workflows/ directory from one that failed to be read"
    )


def test_exactly_two_roles_can_log_in_and_the_object_owner_is_not_one(
    environment: dict[str, Any],
) -> None:
    """The control is which role does NOT have a password.

    `object_owner` stays NOLOGIN, so the owner's authority is reachable only by
    `SET LOCAL ROLE` from the migration user -- the mechanism every migration in
    this release is written against, and the one D285's defect is invisible
    without (ADR 0026).
    """
    state = environment["state"]
    roles = state["roles"]
    can_login = set(
        as_superuser(
            state,
            "SELECT string_agg(rolname, ',' ORDER BY rolname) FROM pg_roles "
            "WHERE rolcanlogin AND rolname LIKE 'apg\\_%'",
        ).split(",")
    )
    expected = {roles[key] for key in dev_environment.ACTIVATED_ROLES}
    assert can_login == expected, (
        f"the roles that can log in are {sorted(can_login)}, not {sorted(expected)}"
    )
    assert roles["object_owner"] not in can_login
    assert roles["postgrest_authenticator"] not in can_login

    # And the membership option that makes the owner reachable only by SET ROLE.
    options = as_superuser(
        state,
        "SELECT m.admin_option::text || '|' || m.inherit_option::text || '|' "
        "|| m.set_option::text FROM pg_auth_members m "
        "JOIN pg_roles member ON member.oid = m.member "
        "JOIN pg_roles grantee ON grantee.oid = m.roleid "
        f"WHERE member.rolname = '{roles['migration_user']}' "
        f"AND grantee.rolname = '{roles['object_owner']}'",
    )
    assert options == "false|false|true", (
        f"the owner membership records {options!r}, not 'false|false|true'. With INHERIT "
        "TRUE the migration user would hold the owner's rights by connecting (D266)"
    )


def test_nothing_the_command_prints_is_a_password(environment: dict[str, Any]) -> None:
    """D105: read from the files, searched in the transcript.

    The passwords are read out of the 0600 env files this command wrote, so the
    search is for the actual values rather than for a pattern that might match
    them. A command that printed one would put a credential in a scrollback, a
    CI log and a support ticket.
    """
    directory = dev_environment.state_dir("fixture-alpha-dev")
    transcript = environment["stdout"] + environment["stderr"]
    assert transcript.strip(), "the command printed nothing, so this searches nothing"

    # The PASSWORD variables only. `superuser.env` also carries `POSTGRES_DB`,
    # which is the database name and is printed on purpose -- a scan that
    # treated every `KEY=value` as a secret refused the command for telling a
    # developer which database they have.
    passwords = {"POSTGRES_PASSWORD", "PGPASSWORD"}
    secrets_on_disk = []
    for name in (
        dev_environment.SUPERUSER_ENV,
        dev_environment.MIGRATION_USER_ENV,
        dev_environment.APP_RUNTIME_ENV,
    ):
        for line in (directory / name).read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() in passwords and value.strip():
                secrets_on_disk.append(value.strip())

    assert len(secrets_on_disk) == 3, (
        f"found {len(secrets_on_disk)} passwords on disk, not three. The superuser's, "
        "the migration user's and the application role's are what `up` generates"
    )
    assert len(set(secrets_on_disk)) == 3, "two of the three generated passwords are the same value"
    for value in secrets_on_disk:
        assert value not in transcript, (
            "a password this command generated appears in what it printed. Every one of "
            "them belongs in a 0600 file and nowhere else (D105, ADR 0203 §5)"
        )

    assert str(directory) in transcript, (
        "the command does not say where the passwords are, so a developer cannot find "
        "them without reading the source"
    )


# ---------------------------------------------------------------------------
# DEV-SUBJECT-001
# ---------------------------------------------------------------------------


def test_exactly_one_subject_exists_and_its_rows_are_visible_only_with_it_asserted(
    environment: dict[str, Any],
) -> None:
    """One subject, the right role, and the boundary it makes real.

    The three-way reading is the point: as the application role, the subject's
    row comes back with `app.user_id` set to it, and does not come back without
    it or with another subject's id. That is row-level security doing its work
    on a cluster a developer can break, which is what the environment is for.

    Nothing in the database refuses a `role_name` this deployment does not
    derive (D1176), so the role stored is read back and compared to the document.
    """
    state = environment["state"]
    roles = state["roles"]

    recorded = as_superuser(
        state,
        "SELECT count(*)::text || '|' || string_agg(username, ',') || '|' "
        "|| string_agg(role_name, ',') FROM app_private.users",
    )
    count, usernames, role_names = recorded.split("|")
    assert count == "1", f"{count} subjects exist, not one"
    assert usernames == dev_environment.SUBJECT_USERNAME
    assert role_names == roles["authenticated"], (
        f"the subject's role_name is {role_names!r}, not the document's authenticated "
        "role. Nothing downstream checks this, which is why it is checked here (D1176)"
    )
    assert state["subject_id"], "the state records no subject id"

    verifier = as_superuser(
        state, "SELECT left(password_hash, 10) FROM app_private.user_credentials"
    )
    assert verifier == "$argon2id$", f"the verifier is {verifier!r}"

    # The boundary. A note written as the subject, read back three ways.
    written = docker(
        "exec", "-i", "--env-file",
        str(dev_environment.state_dir("fixture-alpha-dev") / dev_environment.MIGRATION_USER_ENV),
        state["container"], "psql", "-U", roles["migration_user"], "-h", "127.0.0.1",
        "-d", state["database"], "-qtA", "-v", "ON_ERROR_STOP=1", "-1", "-f", "-",
        stdin=(
            f"SELECT set_config('app.user_id', '{state['subject_id']}', true);\n"
            f'SET LOCAL ROLE "{roles["object_owner"]}";\n'
            "SELECT api.create_note('apg-dev-canary', 'body');\n"
            "RESET ROLE;\n"
        ),
    )  # fmt: skip
    assert written.returncode == 0, written.stderr

    def as_application(subject: str | None) -> str:
        arguments = [
            "exec", "-i", "--env-file",
            str(dev_environment.state_dir("fixture-alpha-dev") / dev_environment.APP_RUNTIME_ENV),
        ]  # fmt: skip
        if subject:
            arguments += ["-e", f"PGOPTIONS=-c app.user_id={subject}"]
        arguments += [
            state["container"], "psql", "-U", roles["app_runtime"], "-h", "127.0.0.1",
            "-d", state["database"], "-qtA", "-v", "ON_ERROR_STOP=1",
            "-c", "SELECT count(*)::text FROM api.notes",
        ]  # fmt: skip
        result = docker(*arguments)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    assert as_application(state["subject_id"]) == "1", (
        "the subject cannot see its own row, so `apg dev psql` would hand a developer a "
        "session that reads nothing"
    )
    assert as_application(None) == "0", (
        "a session with no subject asserted read the subject's row, so row-level "
        "security is not deciding this"
    )
    assert as_application("00000000-0000-4000-8000-000000000001") == "0", (
        "another subject read this subject's row"
    )


# ---------------------------------------------------------------------------
# DEV-ISO-001 -- what the container IS, with the rendered model as the control
# ---------------------------------------------------------------------------


def test_the_environment_can_reach_no_backup_plane_and_the_rendered_model_can(
    environment: dict[str, Any],
) -> None:
    """D1161, both halves in one test, because one without the other proves
    nothing.

    The environment: one network and it is the default bridge; one mount and it
    is the anonymous volume the image declares; no mount naming pgbackrest; the
    published port on `127.0.0.1`; `wal_level` `replica`.

    The control: the same project's RENDERED Compose model, read from the file
    the deploy hands to Compose, which puts `postgres` on `internal` AND
    `backup` and mounts `pgbackrest.conf`. Without it, every assertion above
    would be satisfied by a deployment that had quietly stopped configuring any
    of it.
    """
    state = environment["state"]
    container = state["container"]

    networks = json.loads(
        docker("inspect", "-f", "{{json .NetworkSettings.Networks}}", container).stdout
    )
    assert sorted(networks) == ["bridge"], (
        f"the environment joined {sorted(networks)}. It is told no --network, so the "
        "default bridge is the only one it can be on"
    )

    mounts = json.loads(docker("inspect", "-f", "{{json .Mounts}}", container).stdout)
    assert [m["Type"] for m in mounts] == ["volume"], (
        f"the environment has mounts {[(m['Type'], m['Destination']) for m in mounts]}. "
        "Exactly one, and it is the anonymous volume the image declares -- a proof "
        "asserting NO mounts would be red on a correct environment (D1161)"
    )
    assert mounts[0]["Destination"] == "/var/lib/postgresql"
    for mount in mounts:
        assert "pgbackrest" not in json.dumps(mount), mount

    ports = json.loads(docker("inspect", "-f", "{{json .NetworkSettings.Ports}}", container).stdout)
    bindings = ports["5432/tcp"]
    assert [binding["HostIp"] for binding in bindings] == ["127.0.0.1"], (
        f"the port is published on {[b['HostIp'] for b in bindings]}. An unbound address "
        "publishes on 0.0.0.0 AND :: (rig 22a)"
    )

    assert as_superuser(state, "SHOW wal_level") == "replica", (
        "wal_level is not the image's default, so this command passed a -c it should not"
    )

    environment_variables = json.loads(
        docker("inspect", "-f", "{{json .Config.Env}}", container).stdout
    )
    joined = "\n".join(environment_variables)
    for forbidden in ("PGBACKREST", "CIPHER", "R2_", "B2_", "INFISICAL"):
        assert forbidden not in joined.upper(), f"the container's env names {forbidden}"

    # The control: the rendered model this project deploys.
    compose = (Path(state["rendered_dir"]) / "compose.env").read_text(encoding="utf-8")
    assert compose.strip(), "the rendered compose env is empty, so the control reads nothing"
    model = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "pgbackrest.conf" in model, (
        "the release's own Compose model no longer mounts pgbackrest.conf, so the "
        "environment's not mounting it says nothing"
    )
    assert "backup" in model and "internal" in model, (
        "the release's own model no longer declares the two networks the environment "
        "is being contrasted with"
    )


# ---------------------------------------------------------------------------
# DEV-SEED-001 on the cluster
# ---------------------------------------------------------------------------


def test_the_example_seed_applies_once_as_the_subject_and_is_refused_twice(
    environment: dict[str, Any],
) -> None:
    """The seed's rows are the subject's, and a second application is refused.

    Applied through the product's own command, not by piping the file: what is
    under test is `apg dev seed`, including the digest it verifies, the lint it
    runs and the identity it asserts.

    A second application would write the rows twice, and the cluster a developer
    then reasons about is one no sequence of commands produces. `reset` is the
    way back and the refusal says so.

    This test runs before the status test below, which takes the environment
    down; it leaves the rows in place for nothing else to read, because the
    fixture is module-scoped and removed in `finally`.
    """
    state = environment["state"]
    before = as_superuser(state, "SELECT count(*)::text FROM app.notes")

    applied = apg("dev", "seed", "example", "--project", PROJECT)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert "applied seed example" in applied.stdout, applied.stdout
    assert state["subject_id"] in applied.stdout, "the command does not say whose rows it wrote"

    counts = as_superuser(
        state,
        "SELECT (SELECT count(*) FROM app.notes)::text || '|' "
        "|| (SELECT count(*) FROM app.note_embeddings)::text || '|' "
        "|| (SELECT count(DISTINCT owner_id) FROM app.notes)::text || '|' "
        "|| (SELECT max(owner_id::text) FROM app.notes)",
    )
    notes, embeddings, owners, owner = counts.split("|")
    assert int(notes) == int(before) + 2, f"the seed wrote {notes} notes, not two more"
    assert embeddings == "1", f"the seed wrote {embeddings} embeddings, not one"
    assert owners == "1" and owner == state["subject_id"], (
        f"the seeded rows belong to {owner}, not to the development subject "
        f"{state['subject_id']}. Without `set_config('app.user_id', ...)` every write "
        "raises AP401; with the wrong one the rows are nobody's"
    )

    recorded = json.loads(
        (dev_environment.state_dir("fixture-alpha-dev") / dev_environment.SEEDS_FILE).read_text(
            encoding="utf-8"
        )
    )
    assert recorded == ["example"], recorded

    again = apg("dev", "seed", "example", "--project", PROJECT)
    assert again.returncode == dev_environment.EXIT_INPUT, again.stdout + again.stderr
    assert "already been applied" in again.stderr and "reset" in again.stderr, again.stderr

    unchanged = as_superuser(state, "SELECT count(*)::text FROM app.notes")
    assert unchanged == notes, (
        f"the refused second application changed the row count from {notes} to {unchanged}"
    )

    # And the control: a name the manifest does not declare is refused with the
    # names it does, without touching the cluster.
    unknown = apg("dev", "seed", "nosuchseed", "--project", PROJECT)
    assert unknown.returncode == dev_environment.EXIT_INPUT, unknown.stderr
    assert "This project declares: example" in unknown.stderr, unknown.stderr
    assert as_superuser(state, "SELECT count(*)::text FROM app.notes") == notes


def test_the_seeded_rows_are_visible_to_the_application_role_only_with_the_subject(
    environment: dict[str, Any],
) -> None:
    """The loop the environment exists to give a developer.

    `apg dev psql` connects as the application role with `app.user_id` preset;
    this makes the same connection with and without it. Two rows with the
    subject, none without it, none as another subject -- row-level security
    doing its work on a cluster a developer can break.

    It depends on the seed above having run, and applies it if it has not, so
    either test can be selected alone by node id (D1181's lesson, applied here
    rather than learned again).
    """
    state = environment["state"]
    if as_superuser(state, "SELECT count(*)::text FROM app.notes") == "0":
        assert apg("dev", "seed", "example", "--project", PROJECT).returncode == 0

    directory = dev_environment.state_dir("fixture-alpha-dev")

    def as_application(subject: str | None) -> str:
        argv = ["exec", "-i", "--env-file", str(directory / dev_environment.APP_RUNTIME_ENV)]
        if subject:
            argv += ["-e", f"PGOPTIONS=-c app.user_id={subject}"]
        argv += [
            state["container"], "psql", "-U", state["roles"]["app_runtime"],
            "-h", "127.0.0.1", "-d", state["database"], "-qtA", "-v", "ON_ERROR_STOP=1",
            "-c", "SELECT count(*)::text FROM api.notes",
        ]  # fmt: skip
        result = docker(*argv)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    # **Exactly the subject's rows, whatever their number.** Compared against
    # what the superuser counts for that owner rather than against a literal:
    # an earlier test in this module writes a canary note as the same subject,
    # so a hardcoded 2 was wrong the moment both tests ran together -- and the
    # property was never "two rows", it was "the rows that are the subject's".
    owned = as_superuser(
        state, f"SELECT count(*)::text FROM app.notes WHERE owner_id = '{state['subject_id']}'"
    )
    assert int(owned) >= 2, (
        f"the subject owns {owned} notes; the seed writes two, so this cluster does not "
        "carry what the test above applied"
    )
    assert as_application(state["subject_id"]) == owned, (
        f"the application role sees {as_application(state['subject_id'])} notes and the "
        f"subject owns {owned}. It must see its own rows and exactly those"
    )
    assert as_application(None) == "0", (
        "a session with no subject asserted read the seeded rows, so row-level security "
        "is not deciding this"
    )
    assert as_application("00000000-0000-4000-8000-000000000001") == "0"

    # The embedding too, through the project's own view -- the tenant surface a
    # developer is actually building on.
    argv = [
        "exec", "-i", "--env-file", str(directory / dev_environment.APP_RUNTIME_ENV),
        "-e", f"PGOPTIONS=-c app.user_id={state['subject_id']}",
        state["container"], "psql", "-U", state["roles"]["app_runtime"],
        "-h", "127.0.0.1", "-d", state["database"], "-qtA", "-v", "ON_ERROR_STOP=1",
        "-c", "SELECT count(*)::text FROM api.note_embeddings",
    ]  # fmt: skip
    result = docker(*argv)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1", (
        "the seeded embedding is not visible through the project's own view"
    )


def test_status_reports_three_outcomes_and_down_is_idempotent(
    environment: dict[str, Any],
) -> None:
    """Running, stopped, absent -- each with its own exit code, each measured.

    `unknown` is the fourth and is asserted in `test_dev_environment.py`, where
    a docker that cannot answer can be constructed; here the daemon is by
    definition answering.

    This test STOPS the container and starts it again, so it runs last in this
    module and leaves the environment as it found it -- and the fixture removes
    it in `finally` either way.
    """
    running = apg("dev", "status", "--project", PROJECT)
    assert running.returncode == 0, running.stdout + running.stderr
    assert "is running on 127.0.0.1:" in running.stdout, running.stdout

    container = environment["state"]["container"]
    assert docker("stop", container, timeout=90).returncode == 0
    try:
        stopped = apg("dev", "status", "--project", PROJECT)
        assert stopped.returncode == dev_environment.EXIT_CONTRACT, stopped.stdout
        assert "reset" in stopped.stdout, stopped.stdout
    finally:
        assert docker("start", container, timeout=90).returncode == 0

    removed = apg("dev", "down", "--project", PROJECT)
    assert removed.returncode == 0, removed.stderr
    assert "removed" in removed.stdout, removed.stdout

    again = apg("dev", "down", "--project", PROJECT)
    assert again.returncode == 0, again.stderr
    assert "nothing to remove" in again.stdout, (
        f"a second down reported {again.stdout!r}; it must be idempotent AND say which "
        "of the two happened"
    )

    absent = apg("dev", "status", "--project", PROJECT)
    assert absent.returncode == dev_environment.EXIT_NOT_RENDERED, absent.stdout
    assert "no development environment" in absent.stdout, absent.stdout

    # And the volume went with it: `docker rm -f` without `-v` leaves the
    # anonymous volume behind (rig 22a), which would accumulate one per reset.
    assert docker("inspect", container, timeout=30).returncode != 0, "the container survived `down`"

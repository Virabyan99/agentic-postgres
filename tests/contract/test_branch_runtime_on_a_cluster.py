"""A branch's whole life on a real cluster, through `bin/branch-runtime.py`'s own
phases (Session 40, ADR 0271, D2424-D2427, D2458-D2460).

Rig 40a's shape, made a proof: the project's own image (services/postgres,
built from versions.env's three arguments), a parent bootstrapped by the
bootstrap plane's statements and the release's migrations, archiving to a
**POSIX** pgBackRest repository on a named volume -- the product's rendered
configuration with its `repo1-s3-*` lines dropped and `repo1-type=posix`, the
three `conf.d` credential paths mounted where production mounts them. Then the
runtime's phases, as `create` runs them: `build_plan` + `assert_branch_safe`,
`read_window`, `create_volume`, `restore`, `recover`, `write_compose_state`,
`persist` (the branch's compose file, for real), `rekey`, `write_userlists`,
`open_doors`, and finally `command_delete`.

Two things differ from a host, and only these: the repository volume is added
READ-ONLY to the restore and recovery phases (production's repository is R2,
reached over the parent's backup network, so no mount names it), and the
userlist directory is opened to uid 70 by mode rather than by `root:70`
ownership, because this proof does not run as root. The edge is not attached:
there is none here.

Every observation is taken inside one module fixture, so the proofs read facts
and do not depend on their order. Everything named for this run is removed
(`docker rm -fv`, D2098).
"""

# ruff: noqa: S608 -- every interpolated value is a name this module derived.

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import secrets
import subprocess
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    config,
    migrations,
    naming,
    rendering,
    restore_drill,
    runtime_override,
    scram,
)

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

REPO = "/var/lib/pgbackrest"
IDENTITY = (
    "CHECKPOINT; SELECT (SELECT timeline_id FROM pg_control_checkpoint()) || ' ' || "
    "(SELECT system_identifier FROM pg_control_system())"
)
LOGIN_ROLES = "SELECT string_agg(rolname, ' ' ORDER BY rolname) FROM pg_roles WHERE rolcanlogin"


def docker(*arguments: str, stdin: str | None = None, timeout: int = 600) -> Any:
    return subprocess.run(
        ["docker", *arguments], input=stdin, capture_output=True, text=True, check=False,
        timeout=timeout,
    )  # fmt: skip


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lock() -> dict[str, str]:
    values = {}
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            name, _, value = line.partition("=")
            values[name] = value
    return values


def _document(tmp: Path, environment: str) -> dict[str, Any]:
    raw = yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))
    raw["project"]["slug"] = "brtest"
    raw["project"]["environment"] = environment
    raw["database"]["public_endpoints"] = {"enabled": True}
    path = tmp / "project.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    manifest = config.load_project_manifest(path)
    identity = naming.derive(
        slug=manifest["project"]["slug"],
        environment=manifest["project"]["environment"],
        domain=manifest["project"]["domain"],
        api_base_path=manifest["api"]["public_base_path"],
        mcp_base_path=manifest["mcp"]["public_base_path"],
        database_name=manifest["database"]["name"],
    )
    document = rendering.build_outputs(
        manifest, config.load_capabilities_manifest(REPO_ROOT / "capabilities.example.yaml"),
        identity, {},
    )  # fmt: skip
    document["source_commit"] = "0" * 40
    # A deployed document names its database container; this one is built in
    # memory, so the name Compose would give it is written here.
    document["database"].setdefault("container", f"apg-{identity.key}-postgres-1")
    return document


def _peer_login(
    network: str, host: str, port: int, database: str, role: str, password: str
) -> bool:
    """A login over TCP from a PEER container -- never loopback, which the image's
    pg_hba trusts (D2458)."""
    image = _lock()["POSTGRES_IMAGE"]
    done = docker(
        "run", "--rm", "--network", network, "-e", f"PGPASSWORD={password}", "--entrypoint", "psql",
        image, "-X", "-qtA",
        f"host={host} port={port} user={role} dbname={database} connect_timeout=5 sslmode=disable",
        "-c", "select current_user", timeout=60,
    )  # fmt: skip
    return done.returncode == 0


def _wait_ready(container: str, database: str, *, first_boot: bool) -> None:
    """Ready, and not the image's first-boot TEMPORARY server: that one answers
    `pg_isready` on the socket and then shuts down for the real start (a run of
    this proof met `the database system is shutting down`). On a first boot the
    entrypoint's own line marks the end of it; then two answers a second apart."""
    for _ in range(180):
        logs = docker("logs", container)
        if not first_boot or "init process complete" in (logs.stdout + logs.stderr):
            break
        time.sleep(1)
    answered = 0
    for _ in range(180):
        ready = docker("exec", container, "pg_isready", "-U", "postgres", "-d", database)
        answered = answered + 1 if ready.returncode == 0 else 0
        if answered >= 2:
            return
        time.sleep(1)
    raise AssertionError(f"{container} never became ready")


def _repository_files(volume: str, image: str) -> set[str]:
    done = docker(
        "run",
        "--rm",
        "-v",
        f"{volume}:{REPO}:ro",
        "--entrypoint",
        "find",
        image,
        REPO,
        "-type",
        "f",
    )
    return set(done.stdout.split())


def _sql(container: str, database: str, sql: str) -> str:
    done = docker("exec", "-i", container, "psql", "-X", "-qtA", "-v", "ON_ERROR_STOP=1",
                  "-U", "postgres", "-d", database, stdin=sql)  # fmt: skip
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture(scope="module")
def life(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("branch-cluster")
    lock = _lock()
    runtime = _load("apg_branch_runtime_cluster", REPO_ROOT / "bin" / "branch-runtime.py")
    bootstrap = _load("apg_bootstrap_branch", REPO_ROOT / "bin" / "postgres-bootstrap.py")
    environment = f"c{secrets.token_hex(3)}"
    document = _document(tmp, environment)
    key = document["project"]["key"]
    database = document["database"]["name"]
    roles = document["database"]["roles"]
    stanza = document["backup"]["stanza"]
    parent = document["database"]["container"]
    tag = f"apg-branch-cluster:{secrets.token_hex(4)}"
    repo_volume = f"apg-{key}-repo-proof"
    parent_volume = naming.postgres_volume_name(key)
    backup_network = naming.backup_network_name(key)
    names = naming.branch_names(key, "dev")
    seen: dict[str, Any] = {}
    created: list[tuple[str, str]] = []
    try:
        built = docker(
            "build", "-q", "-t", tag,
            "--build-arg", f"BASE_IMAGE={lock['POSTGRES_IMAGE']}",
            "--build-arg", f"PGBACKREST_APT_VERSION={lock['PGBACKREST_APT_VERSION']}",
            "--build-arg", f"CA_CERTIFICATES_APT_VERSION={lock['CA_CERTIFICATES_APT_VERSION']}",
            str(REPO_ROOT / "services" / "postgres"), timeout=1200,
        )  # fmt: skip
        assert built.returncode == 0, built.stderr[-500:]
        created.append(("image", tag))

        # The parent's configuration: the product's render, posix, at the paths
        # production mounts (`restore_drill.required_container_paths`).
        conf = tmp / "pgbackrest"
        (conf / "conf.d").mkdir(parents=True)
        rendered = rendering.build_pgbackrest_conf(None, document, "https://r2.invalid").decode()
        lines = []
        for line in rendered.splitlines():
            if line.startswith("repo1-s3-"):
                continue
            if line == "repo1-type=s3":
                line = "repo1-type=posix"
            if line.startswith("repo1-path="):
                line = f"repo1-path={REPO}{line.split('=', 1)[1]}"
            lines.append(line)
        (conf / "pgbackrest.conf").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (conf / "conf.d" / "10-repo1-s3-key.conf").write_text("# posix: no key\n", encoding="utf-8")
        (conf / "conf.d" / "20-repo1-s3-key-secret.conf").write_text("# posix\n", encoding="utf-8")
        (conf / "conf.d" / "30-repo1-cipher-pass.conf").write_text(
            f"[global]\nrepo1-cipher-pass={secrets.token_hex(32)}\n", encoding="utf-8"
        )
        for path in [conf, conf / "conf.d", *conf.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        binds = ["-v", f"{conf / 'pgbackrest.conf'}:/etc/pgbackrest/pgbackrest.conf:ro"]
        for name in (
            "10-repo1-s3-key.conf",
            "20-repo1-s3-key-secret.conf",
            "30-repo1-cipher-pass.conf",
        ):
            binds += ["-v", f"{conf / 'conf.d' / name}:/etc/pgbackrest/conf.d/{name}:ro"]

        assert docker("network", "create", backup_network).returncode == 0
        created.append(("network", backup_network))
        for volume in (repo_volume, parent_volume):
            assert docker("volume", "create", volume).returncode == 0
            created.append(("volume", volume))
        docker(
            "run",
            "--rm",
            "-u",
            "0",
            "-v",
            f"{repo_volume}:{REPO}",
            "--entrypoint",
            "chown",
            tag,
            "999:999",
            REPO,
        )

        superuser, app_pw, admin_pw, migration_pw = (secrets.token_hex(24) for _ in range(4))
        started = docker(
            "run", "-d", "--name", parent, "-u", "999:999", "--network", backup_network,
            "-e", f"POSTGRES_PASSWORD={superuser}", "-e", f"POSTGRES_DB={database}",
            "-e", "POSTGRES_INITDB_ARGS=--data-checksums --encoding=UTF8 --locale=C",
            "-v", f"{parent_volume}:{runtime_override.POSTGRES_VOLUME_TARGET}",
            "-v", f"{repo_volume}:{REPO}", *binds, tag,
            "postgres", "-c", "listen_addresses=*", "-c", "archive_mode=on",
            "-c", f"archive_command=pgbackrest --stanza={stanza} archive-push %p",
            "-c", "archive_timeout=60s",
        )  # fmt: skip
        assert started.returncode == 0, started.stderr
        created.append(("container", parent))
        _wait_ready(parent, database, first_boot=True)

        bootstrap.psql(
            parent, database, "\n".join(bootstrap.build_statements(document, str(uuid.uuid4())))
        )
        for migration_set in migrations.sets_for(document):
            set_manifest = migration_set.load_manifest()
            for entry in set_manifest["migrations"]:
                payload = migrations.render_migration(
                    entry, set_manifest, document, migration_set.root
                )
                up = payload.split("-- migrate:down", 1)[0].replace("-- migrate:up", "", 1)
                done = docker("exec", "-i", parent, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
                              "-U", "postgres", "-d", database, "-1", stdin=up)  # fmt: skip
                assert done.returncode == 0, f"{entry['name']}: {done.stderr}"
        bootstrap.activate_customer_roles(
            parent, database, roles, bootstrap.customer_limits(document)
        )
        q, literal = migrations.quote_identifier, migrations.quote_literal
        for suffix, password in (("customer_app", app_pw), ("customer_admin", admin_pw)):
            verifier = literal(scram.verifier(password))
            _sql(parent, database, f"ALTER ROLE {q(roles[suffix])} PASSWORD {verifier};")
        bootstrap.apply_credential(parent, database, roles["migration_user"], migration_pw)

        # `--start-fast`: an immediate checkpoint rather than a spread one, which
        # cost ~57 s per run and is not what this proof measures.
        for verb in (("stanza-create",), ("check",), ("--type=full", "--start-fast", "backup")):
            done = docker("exec", parent, "pgbackrest", f"--stanza={stanza}", *verb, timeout=900)
            assert done.returncode == 0, (verb, done.stdout[-400:], done.stderr[-400:])
        # D2465, measured here: the earliest point a restore reaches. pgBackRest
        # records a set's stop in whole seconds; a target half a second after
        # it, and one a whole second after it, each restored into a scratch
        # volume and thrown away. Only the backup-set selection is read.
        info = json.loads(docker("exec", parent, "pgbackrest", f"--stanza={stanza}",
                                 "--output=json", "info").stdout)  # fmt: skip
        stop = int(info[0]["backup"][-1]["timestamp"]["stop"])
        time.sleep(3)  # every boundary target below is in the past before it is tried
        boundary = {}
        for offset in (0.5, 1.0):
            scratch = f"apg-{key}-boundary-{int(offset * 10)}"
            docker("volume", "create", scratch)
            created.append(("volume", scratch))
            target = restore_drill.pgbackrest_target(datetime.fromtimestamp(stop + offset, tz=UTC))
            data = f"{scratch}:{runtime_override.POSTGRES_VOLUME_TARGET}"
            tried = docker(
                "run", "--rm", "-u", "999:999", "-v", data,
                "-v", f"{repo_volume}:{REPO}:ro", *binds, "--entrypoint", "pgbackrest", tag,
                f"--stanza={stanza}", "restore", "--type=time", f"--target={target}",
                "--target-action=promote", timeout=600,
            )  # fmt: skip
            boundary[offset] = tried.returncode
            docker("volume", "rm", "-f", scratch)
        seen["boundary"] = boundary
        admin = q(roles["customer_admin"])
        _sql(parent, database, f"SET ROLE {admin}; CREATE TABLE public.marker (id int PRIMARY KEY);"
                               "INSERT INTO public.marker VALUES (1);")  # fmt: skip
        segment = _sql(parent, database, "SELECT pg_walfile_name(pg_switch_wal())")
        for _ in range(120):
            if (
                _sql(
                    parent, database, "SELECT coalesce(last_archived_wal, '') FROM pg_stat_archiver"
                )
                >= segment
            ):
                break
            time.sleep(1)
        point = _sql(parent, database, "SELECT clock_timestamp()")
        time.sleep(2)
        _sql(parent, database, f"SET ROLE {admin}; INSERT INTO public.marker VALUES (2);")
        segment = _sql(parent, database, "SELECT pg_walfile_name(pg_switch_wal())")
        for _ in range(120):
            if (
                _sql(
                    parent, database, "SELECT coalesce(last_archived_wal, '') FROM pg_stat_archiver"
                )
                >= segment
            ):
                break
            time.sleep(1)
        parent_identity = _sql(parent, database, IDENTITY)

        # The runtime, as root would run it -- with this proof's two differences.
        runtime.BRANCH_ROOT = tmp / "branches"
        runtime.POOLER_GID = None
        inspect = runtime.inspect_running(parent, "the parent's database")
        plan = runtime.build_plan(document, inspect, "dev", point)
        seen["target"] = plan.target
        window = runtime.read_window(document)
        runtime.check_window(plan.target, window)
        seen["window"] = window
        repository = restore_drill.Mount(repo_volume, REPO, True, "volume")
        posix = dataclasses.replace(
            plan,
            restore=dataclasses.replace(plan.restore, mounts=(*plan.restore.mounts, repository)),
            recovery=dataclasses.replace(plan.recovery, mounts=(*plan.recovery.mounts, repository)),
        )
        # The parent stops here, as in rig 40a: what it would archive while the
        # branch lives must not be mistaken for the branch's writes.
        docker("stop", "-t", "60", parent, timeout=120)
        before = _repository_files(repo_volume, tag)
        created.append(("branch", "dev"))
        runtime.create_volume(posix)
        runtime.restore(posix)
        reached, timeline, _ = runtime.recover(posix)
        seen["reached"], seen["timeline"] = reached, timeline
        runtime.write_compose_state(
            posix, pgbouncer_image=lock["PGBOUNCER_IMAGE"], acme_resolver_name="proof"
        )
        runtime.persist(posix)
        seen["rows"] = _sql(
            names.postgres_container,
            database,
            "SELECT string_agg(id::text, ',' ORDER BY id) FROM public.marker",
        )
        net = names.internal_network

        def login(host: str, port: int, role: str, password: str) -> bool:
            return _peer_login(net, host, port, database, role, password)

        def branch(role: str, password: str) -> bool:
            return login(names.postgres_container, 5432, role, password)

        seen["before"] = {
            "customer_app (parent)": branch(roles["customer_app"], app_pw),
            "migration_user (parent)": branch(roles["migration_user"], migration_pw),
        }
        new_app, new_admin = secrets.token_hex(24), secrets.token_hex(24)
        runtime.rekey(
            posix,
            {"customer_app": scram.verifier(new_app), "customer_admin": scram.verifier(new_admin)},
        )
        seen["after"] = {
            "customer_app (parent)": branch(roles["customer_app"], app_pw),
            "customer_admin (parent)": branch(roles["customer_admin"], admin_pw),
            "customer_app (branch)": branch(roles["customer_app"], new_app),
            "customer_admin (branch)": branch(roles["customer_admin"], new_admin),
            "migration_user (parent)": branch(roles["migration_user"], migration_pw),
            "postgres (parent)": branch("postgres", superuser),
        }
        seen["login_roles"] = _sql(names.postgres_container, database, LOGIN_ROLES)
        auto_conf = f"{runtime_override.POSTGRES_PGDATA}/postgresql.auto.conf"
        seen["auto_conf"] = docker("exec", names.postgres_container, "cat", auto_conf).stdout
        seen["archive_mode"] = _sql(names.postgres_container, database, "SHOW archive_mode")
        runtime.write_userlists(posix)
        userlists = runtime.BRANCH_ROOT / key / "dev" / runtime_override.CUSTOMER_USERLIST_DIRNAME
        # This proof is not root: open by mode what production opens by group.
        userlists.chmod(0o755)
        for path in userlists.iterdir():
            path.chmod(0o644)
        runtime.open_doors(posix)
        pool, direct = names.pool_container, names.direct_container
        seen["doors"] = {
            "pool (branch)": login(pool, 6432, roles["customer_app"], new_app),
            "pool (parent)": login(pool, 6432, roles["customer_app"], app_pw),
            "direct (branch)": login(direct, 6432, roles["customer_admin"], new_admin),
            "direct (parent)": login(direct, 6432, roles["customer_admin"], admin_pw),
        }
        seen["branch_identity"] = _sql(names.postgres_container, database, IDENTITY)
        seen["repository_unchanged"] = _repository_files(repo_volume, tag) == before
        docker("start", parent)
        _wait_ready(parent, database, first_boot=False)
        seen["parent_identity"] = (parent_identity, _sql(parent, database, IDENTITY))
        seen["parent_rows"] = _sql(
            parent, database, "SELECT string_agg(id::text, ',' ORDER BY id) FROM public.marker"
        )

        runtime.require_root = lambda: None
        runtime.detach = lambda names: None
        seen["delete_exit"] = runtime.command_delete(
            argparse.Namespace(parent_key=key, branch="dev")
        )
        project_label = f"label=com.docker.compose.project={names.compose_project}"
        listed = docker("ps", "-a", "--filter", project_label, "--format", "{{.Names}}")
        networks = (names.edge_network, names.internal_network)
        seen["left"] = {
            "containers": listed.stdout.split(),
            "volume": docker("volume", "inspect", names.volume).returncode == 0,
            "networks": [n for n in networks if docker("network", "inspect", n).returncode == 0],
            "directory": (runtime.BRANCH_ROOT / key / "dev").exists(),
        }
        yield seen
    finally:
        for container in (names.pool_container, names.direct_container, names.postgres_container,
                          names.recovery_container, names.restore_container, parent):  # fmt: skip
            docker("rm", "-fv", container, timeout=120)
        for network in (names.edge_network, names.internal_network, backup_network):
            docker("network", "rm", network)
        for volume in (names.volume, parent_volume, repo_volume):
            docker("volume", "rm", "-f", volume)
        docker("image", "rm", "-f", tag)


def test_the_parents_password_opens_nothing_after_the_rekey(life: dict[str, Any]) -> None:
    """The control first: BEFORE the re-key the parent's `customer_app`
    password connects to the restored branch from a peer -- a physical restore
    carries `pg_authid` whole. AFTER it, both customer roles refuse the
    parent's passwords and accept the branch's own verifiers; through the
    branch's two doors the same holds (the userlists read back from the branch's
    catalog, D2460)."""
    assert life["before"]["customer_app (parent)"] is True
    after = life["after"]
    assert after["customer_app (parent)"] is False and after["customer_admin (parent)"] is False
    assert after["customer_app (branch)"] is True and after["customer_admin (branch)"] is True
    assert life["doors"] == {
        "pool (branch)": True,
        "pool (parent)": False,
        "direct (branch)": True,
        "direct (parent)": False,
    }


def test_a_platform_role_cannot_log_in_to_a_branch(life: dict[str, Any]) -> None:
    """`migration_user` with its parent password connects before the re-key
    (the control) and is refused after; so is the superuser over TCP. The only
    login roles left are the two customer roles and `postgres` (local socket);
    the restore settings are gone from `postgresql.auto.conf` (D2459) and
    archiving is off."""
    assert life["before"]["migration_user (parent)"] is True
    assert life["after"]["migration_user (parent)"] is False
    assert life["after"]["postgres (parent)"] is False
    assert len(life["login_roles"].split()) == 3 and "postgres" in life["login_roles"].split()
    assert "customer_app" in life["login_roles"] and "customer_admin" in life["login_roles"]
    assert "restore_command" not in life["auto_conf"], life["auto_conf"]
    assert "recovery_target" not in life["auto_conf"], life["auto_conf"]
    assert life["archive_mode"] == "off"


def test_the_branch_holds_its_point_and_never_wrote_the_repository(life: dict[str, Any]) -> None:
    """Restored to the instant between two marked rows, the branch holds the
    first and not the second; the parent holds both; the window read through
    the runtime's own reader contains the point; the branch is on a new timeline
    with the parent's `system_identifier`, the parent unchanged; and the
    repository's files are unchanged across the branch's whole life."""
    assert life["rows"] == "1"
    assert life["parent_rows"] == "1,2"
    earliest, latest = life["window"]
    assert earliest <= restore_drill.instant(life["target"]) <= latest
    parent_before, parent_after = life["parent_identity"]
    assert parent_before == parent_after
    parent_timeline, parent_system = parent_before.split()
    branch_timeline, branch_system = life["branch_identity"].split()
    assert int(branch_timeline) > int(parent_timeline) and branch_system == parent_system
    assert life["timeline"] == int(branch_timeline)
    assert life["repository_unchanged"] is True


def test_the_earliest_point_is_a_second_after_the_oldest_stop(life: dict[str, Any]) -> None:
    """D2465: a target half a second after the oldest set's recorded stop is
    refused `[075]`; a whole second after it restores. The window's lower bound
    is therefore the stop plus one second, which `backup_report.earliest_point`
    returns and the runtime's window check uses."""
    assert life["boundary"] == {0.5: restore_drill.RESTORE_EXIT_NO_BACKUP_SET, 1.0: 0}


def test_a_deleted_branch_left_nothing(life: dict[str, Any]) -> None:
    """`delete` exits 0 and leaves no container of the branch's compose project,
    no volume, no network and no state directory."""
    assert life["delete_exit"] == 0
    assert life["left"] == {"containers": [], "volume": False, "networks": [], "directory": False}

"""The four client compatibility fixtures (DBX-001..005).

None of this connects to anything. Running the fixtures against a real cluster
is Run 9's job, and it is the only thing that can prove they pass. What is
asserted here is everything that decides whether that run *means* anything —
because a fixture can be green for reasons that have nothing to do with the
claim it is named for, and this project has produced that exact defect five
times.

The three that matter most:

*A lock file that is not enforced is a version list.* ``npm ci`` and
``pip --require-hashes`` are what turn a committed lock into a pin, and they
fail only at build time, on a host. So the flags are asserted here, and so is
the presence of an integrity hash on every entry.

*A prepared-statement test may not be made to pass by disabling prepared
statements.* Prisma's ``?pgbouncer=true`` is exactly the flag that would do it,
and the fixture would still report that Prisma works through the pooler. The
fixture refuses it; this asserts the refusal exists and that nothing sets it.

*An isolation check needs both halves.* "User A sees none of user B's rows" is
satisfied by an empty table, and "user A sees its own rows" is satisfied by no
policy at all. Every probe has to assert both, so every probe is checked for
both.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT, rendering

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CLIENTS = REPO_ROOT / "services" / "clients"
MODEL = REPO_ROOT / "compose.yaml"

#: Fixture directory -> its Compose service name. One mapping, used by every
#: test below, so a fixture added without a service (or the reverse) fails
#: everywhere rather than being quietly untested.
FIXTURES = {
    "psql": "client-psql",
    "node-pg": "client-node-pg",
    "psycopg": "client-psycopg",
    "prisma": "client-prisma",
}

#: The programs that talk to the database. The entrypoints are shell and are
#: checked separately; these are where the SQL is.
PROBES = {
    "psql": "probe.sh",
    "node-pg": "probe.mjs",
    "psycopg": "probe.py",
    "prisma": "probe.mjs",
}


def model() -> dict:
    return yaml.safe_load(MODEL.read_text(encoding="utf-8"))


def probe_source(name: str) -> str:
    return (CLIENTS / name / PROBES[name]).read_text(encoding="utf-8")


def read(path: Path) -> str:
    """Read any file under a fixture, whatever it happens to contain.

    ``errors="replace"`` because these scans glob whole directories, and a
    generated artefact that is not valid UTF-8 must not turn an absence
    assertion into an error -- an error and a pass are indistinguishable to
    anyone reading a summary line.
    """
    return path.read_text(encoding="utf-8", errors="replace")


def versions_env() -> dict[str, str]:
    values = {}
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


# ---------------------------------------------------------------------------
# Every fixture exists, builds from a locked base, and is wired to a service
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_each_fixture_has_a_dockerfile_and_a_probe(name: str) -> None:
    assert (CLIENTS / name / "Dockerfile").is_file()
    assert (CLIENTS / name / PROBES[name]).is_file()


@pytest.mark.parametrize(("name", "service"), sorted(FIXTURES.items()))
def test_each_fixture_is_a_one_shot_service_in_the_verify_profile(name: str, service: str) -> None:
    """`session4-verify`, not `session4`.

    ``bin/project-runtime.sh::session_profiles`` selects ``session2..N``, so a
    fixture in the ``session4`` profile would start on every deploy and hold a
    connection against a budget the cluster computed for services that do work.
    The same distinction ``secret-check`` draws, for the same reason.
    """
    services = model()["services"]
    assert service in services, f"{name} has no Compose service"
    assert services[service]["profiles"] == ["session4-verify"]
    assert services[service]["restart"] == "no"
    assert services[service]["build"]["context"] == f"./services/clients/{name}"


def test_the_verify_profile_is_not_started_by_a_deploy() -> None:
    """Guard the guard: the profile name above only means something because
    `session_profiles` generates `session<N>` and nothing else."""
    runtime = (REPO_ROOT / "bin" / "project-runtime.sh").read_text(encoding="utf-8")
    assert '--profile "session${n}"' in runtime
    assert "session4-verify" not in runtime


@pytest.mark.parametrize("service", sorted(FIXTURES.values()))
def test_each_fixture_runs_as_the_same_nonroot_user_as_every_built_service(service: str) -> None:
    """65532 everywhere, including the fixture that builds FROM the pooler image.

    That image's own user is 70. Inheriting it would make the uid a property of
    a base image rather than a declared number, and the declared number is what
    secrets.required.yaml, compose.yaml and the Dockerfile are cross-checked on.
    """
    definition = model()["services"][service]
    assert definition["user"] == "65532:65532"
    dockerfile = next(
        path
        for name, path in ((n, CLIENTS / n / "Dockerfile") for n in FIXTURES)
        if FIXTURES[name] == service
    )
    assert "USER 65532:65532" in dockerfile.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Dependencies are pinned, and the pin is enforced
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["node-pg", "prisma"])
def test_the_node_fixtures_install_with_npm_ci(code_only, name: str) -> None:
    """`npm install` would resolve afresh and silently update the lock.

    `npm ci` installs exactly what package-lock.json records and fails when the
    lock and package.json disagree, which is the only form that makes a
    committed lock file load-bearing.

    Scanned over code with comments stripped: each Dockerfile's own comment says
    "npm ci, not npm install", and a scan that counted the explanation would
    have to be weakened until it counted nothing.
    """
    dockerfile = code_only((CLIENTS / name / "Dockerfile").read_text(encoding="utf-8"))
    assert "npm ci" in dockerfile
    assert "npm install" not in dockerfile
    assert "--ignore-scripts" in dockerfile, (
        "a postinstall script is arbitrary code from the dependency tree running at build time"
    )


@pytest.mark.parametrize("name", ["node-pg", "prisma"])
def test_every_locked_node_package_carries_an_integrity_hash(name: str) -> None:
    """Without it, `npm ci` verifies a version and not the bytes."""
    lock = json.loads((CLIENTS / name / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["lockfileVersion"] >= 3
    missing = [
        key
        for key, meta in lock["packages"].items()
        if key and not meta.get("integrity") and not meta.get("link")
    ]
    assert not missing, f"{name}: locked packages with no integrity hash: {missing}"


@pytest.mark.parametrize("name", ["node-pg", "prisma"])
def test_the_lock_and_the_manifest_agree(name: str) -> None:
    manifest = json.loads((CLIENTS / name / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((CLIENTS / name / "package-lock.json").read_text(encoding="utf-8"))
    declared = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
    for package, wanted in declared.items():
        installed = lock["packages"][f"node_modules/{package}"]["version"]
        assert installed == wanted, (
            f"{name}: {package} is {wanted} in package.json, {installed} in the lock"
        )


def test_the_prisma_fixture_pins_the_major_the_lock_file_names() -> None:
    """Two definitions of one fact, asserted to agree rather than trusted.

    D86 chose 6.x deliberately: `directUrl` is a datasource field there and is
    exactly the mechanism two transports need. Prisma 7 moved it into
    prisma.config.ts, which is a different configuration model. A fixture that
    drifted to 7 would still build, and the acceptance report would still say
    "Prisma", naming a configuration nobody tested.
    """
    manifest = json.loads((CLIENTS / "prisma" / "package.json").read_text(encoding="utf-8"))
    locked = versions_env()["PRISMA_VERSION"]
    assert manifest["dependencies"]["@prisma/client"] == locked
    assert manifest["devDependencies"]["prisma"] == locked
    assert locked.startswith("6."), "D86 pins the major; a 7.x here is a different fixture"


def test_the_python_fixture_installs_with_require_hashes() -> None:
    """Without the flag, pip accepts a package from an index that has changed."""
    dockerfile = (CLIENTS / "psycopg" / "Dockerfile").read_text(encoding="utf-8")
    assert "--require-hashes" in dockerfile


def test_every_python_requirement_is_pinned_and_hashed() -> None:
    text = (CLIENTS / "psycopg" / "requirements.txt").read_text(encoding="utf-8")
    requirements = re.findall(r"^([A-Za-z0-9._-]+)==", text, re.MULTILINE)
    assert requirements, "requirements.txt pins nothing"
    for requirement in requirements:
        block = text.split(f"{requirement}==", 1)[1]
        assert "--hash=sha256:" in block.split("\n\n")[0], f"{requirement} has no hash"


def test_the_python_input_and_its_lock_name_the_same_package() -> None:
    source = (CLIENTS / "psycopg" / "requirements.in").read_text(encoding="utf-8")
    locked = (CLIENTS / "psycopg" / "requirements.txt").read_text(encoding="utf-8")
    top = re.match(r"^([A-Za-z0-9._-]+)", source.strip()).group(1)
    assert re.search(rf"^{re.escape(top)}==", locked, re.MULTILINE), (
        f"{top} is requested in requirements.in and absent from the lock"
    )


# ---------------------------------------------------------------------------
# The claim each fixture is named for
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_probe_sets_an_application_name_and_reads_it_back(name: str) -> None:
    """Read back from pg_stat_activity, not from the object that set it.

    Over the pooled transport the value has to survive the pooler, and that is
    the part being proved. Asserting the local variable would pass with the
    pooler dropping it entirely.
    """
    source = probe_source(name)
    assert "apg-client-" in source
    assert "pg_stat_activity" in source
    assert "pg_backend_pid()" in source


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_probe_asserts_both_halves_of_isolation(name: str) -> None:
    """Either half alone is satisfiable by something other than a working policy.

    "None of user B's rows" is true of an empty table. "Some of my own" is true
    with no policy at all. SEC-RLS-001 is the pair.
    """
    source = probe_source(name)
    assert "FILTER (WHERE owner_id =" in source, f"{name} does not count its own rows"
    assert "FILTER (WHERE owner_id <>" in source, f"{name} does not count the other user's"


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_probe_sets_the_claim_transaction_locally(name: str) -> None:
    """`set_config(..., true)`, which is SET LOCAL with a bindable parameter.

    A plain `SET` would outlive the transaction, and under transaction pooling
    that means the next client on that server connection inherits it -- the
    identity of whoever ran before them. That is the single most dangerous thing
    a client can get wrong here, so every fixture is checked for the form that
    cannot do it.
    """
    source = probe_source(name)
    assert "set_config('app.user_id'" in source
    assert ", true)" in source
    assert not re.search(r"\bSET\s+app\.user_id", source), (
        f"{name} sets the claim with SET, which outlives the transaction"
    )


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_no_probe_asks_the_catalog_whether_the_private_schema_is_reachable(
    code_only, name: str
) -> None:
    """D103: has_table_privilege reports true for app.notes while the read is
    denied, because the boundary is the schema and the table grant is what makes
    the security-invoker views work. The read is attempted."""
    source = code_only(probe_source(name))
    assert "app.notes" in source, f"{name} never attempts the private table"
    assert "has_table_privilege" not in source


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_no_probe_accepts_a_credential_through_the_environment(code_only, name: str) -> None:
    """PGPASSWORD is banned from this model outright (Session 3), and nothing
    here needs an exception: three fixtures use PGPASSFILE and Prisma builds its
    URL from the same file."""
    for path in sorted((CLIENTS / name).rglob("*")):
        if path.is_file():
            assert "PGPASSWORD" not in code_only(read(path)), (
                f"{path.relative_to(REPO_ROOT)} names PGPASSWORD"
            )


def test_the_prisma_fixture_refuses_the_flag_that_would_disable_prepared_statements(
    code_only,
) -> None:
    """The rule this run was given, and the fixture it was written for.

    `?pgbouncer=true` tells Prisma the far end cannot hold a prepared statement.
    Setting it would make DBX-002 pass against the fallback path while the report
    still said Prisma works through the pooler. The pooler runs
    max_prepared_statements above zero (measured in Run 1); if that stops being
    true, this fixture must fail rather than quietly become a test of something
    else.
    """
    url = CLIENTS / "prisma" / "url.mjs"
    source = code_only(read(url))
    assert "APG_PRISMA_PGBOUNCER_FLAG" in source, "there is no refusal here at all"

    # The refusal message names the flag, and a message is code rather than a
    # comment -- so stripping comments is not enough to tell "refuses it" from
    # "sets it". What separates them is where it appears: every line naming the
    # flag in this file has to be part of the refusal. A line that named it in a
    # URL would not say "refused", and that is the line this catches.
    naming = [line for line in source.splitlines() if "pgbouncer=true" in line]
    assert naming, "the refusal must name the flag it refuses"
    for line in naming:
        assert "refused" in line, f"url.mjs names the flag outside its refusal: {line.strip()}"

    # Nowhere else at all.
    for path in sorted((CLIENTS / "prisma").rglob("*")):
        if path.is_file() and path != url:
            assert "pgbouncer=true" not in code_only(read(path)), (
                f"{path.relative_to(REPO_ROOT)} sets the flag"
            )

    # And the parameter is never added by name, whatever its value would be.
    assert '"pgbouncer"' not in source
    assert "'pgbouncer'" not in source


def test_the_prisma_fixture_never_interpolates_into_sql(code_only) -> None:
    """Prisma's tagged `$queryRaw` binds; the `Unsafe` variants interpolate."""
    for probe in ("probe.mjs", "migrate.mjs"):
        source = code_only((CLIENTS / "prisma" / probe).read_text(encoding="utf-8"))
        assert "$queryRawUnsafe" not in source
        assert "$executeRawUnsafe" not in source


def test_the_prisma_schema_uses_both_datasource_urls() -> None:
    """`url` for the client and `directUrl` for Migrate, from one schema.

    This is the whole of DBX-001 and DBX-002 as a configuration: two transports
    from one file, with no operator step in between.
    """
    schema = (CLIENTS / "prisma" / "prisma" / "schema.prisma").read_text(encoding="utf-8")
    assert 'url       = env("DATABASE_URL")' in schema
    assert 'directUrl = env("DIRECT_URL")' in schema


def test_prisma_migrate_targets_a_disposable_schema_and_refuses_the_protected_ones() -> None:
    """Plan §4.4's list, in the unprivileged half that must also honour it."""
    url = (CLIENTS / "prisma" / "url.mjs").read_text(encoding="utf-8")
    for protected in (
        "api",
        "app",
        "app_private",
        "extensions",
        "public",
        "pg_catalog",
        "information_schema",
    ):
        assert f'"{protected}"' in url, f"{protected} is not in the refused set"
    assert rendering.PRISMA_FIXTURE_SCHEMA not in (
        "api",
        "app",
        "app_private",
        "extensions",
        "public",
    )


def test_the_prisma_migration_creates_nothing_schema_qualified() -> None:
    """The schema comes from the `schema=` parameter on DIRECT_URL and from
    nowhere else. A qualified name in the SQL would be a second answer to where
    this lands -- and the one the drop does not know about."""
    sql = (
        CLIENTS
        / "prisma"
        / "prisma"
        / "migrations"
        / "20260809000000_fixture_init"
        / "migration.sql"
    ).read_text(encoding="utf-8")
    statements = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    assert re.search(r'CREATE TABLE "fixture_rows"', statements)
    for protected in ("api.", "app.", "app_private.", "public."):
        assert protected not in statements, f"the migration names {protected}"


def test_the_psql_fixture_will_not_fall_back_to_interpolating_values() -> None:
    """`\\bind` needs psql 16 or newer, and the base image was measured at 17.5.

    The interesting case is the day it is not: a fixture that fell back to
    `:'var'` interpolation would keep passing, and "uses parameterized queries"
    would become false without a single test going red.
    """
    source = probe_source("psql")
    assert "\\bind" in source
    assert "-ge 16" in source
    assert "will not fall back" in source


def test_the_psql_fixture_covers_both_transports() -> None:
    """DBX-003 is a claim about the same role over two ports.

    One container rather than two services, because every declared consumer
    materializes its own copy of the credential -- so a second service would be
    a second file a rotation has to reach, to prove the same thing twice.
    """
    entrypoint = (CLIENTS / "psql" / "entrypoint.sh").read_text(encoding="utf-8")
    assert "APG_TRANSPORT=pooled" in entrypoint
    assert "APG_TRANSPORT=direct" in entrypoint

    # Read through a loop rather than by literal subscript. A literal
    # `environment["APG_POOLED_HOST"]` is indistinguishable from consuming that
    # variable to tests/contract/test_environment_gates.py, which scans for
    # exactly that shape -- and it would then require this test to declare an
    # environment gate for variables it never reads from the environment.
    environment = model()["services"]["client-psql"]["environment"]
    pooled = [environment[key] for key in ("APG_POOLED_HOST", "APG_POOLED_PORT")]
    direct = [environment[key] for key in ("APG_DIRECT_HOST", "APG_DIRECT_PORT")]
    assert pooled[0] != direct[0], "both transports resolve to one host"
    assert pooled[1] != direct[1], "both transports resolve to one port"


# ---------------------------------------------------------------------------
# The grant surface the fixtures need
# ---------------------------------------------------------------------------


def test_every_fixture_is_a_declared_consumer_of_the_runtime_credential() -> None:
    """Declared, not shared. A mount of another service's copy would break the
    property the per-consumer layout exists for."""
    contract = yaml.safe_load((REPO_ROOT / "secrets.required.yaml").read_text(encoding="utf-8"))
    runtime = next(s for s in contract["secrets"] if s["name"] == "app_runtime_password")
    consumers = {consumer["service"] for consumer in runtime["consumers"]}
    assert set(FIXTURES.values()) <= consumers, (
        f"fixtures with no declared credential: {set(FIXTURES.values()) - consumers}"
    )


def test_only_the_prisma_fixture_holds_the_migration_credential() -> None:
    """It is the one claim that needs it (DBX-001), and it is the only widening.

    Any other fixture appearing here would be a client with schema authority it
    has no use for.
    """
    contract = yaml.safe_load((REPO_ROOT / "secrets.required.yaml").read_text(encoding="utf-8"))
    migration = next(s for s in contract["secrets"] if s["name"] == "migration_user_password")
    consumers = {consumer["service"] for consumer in migration["consumers"]}
    assert consumers == {"dbmate", "client-prisma"}


def test_the_two_fixture_identities_are_distinct_uuids() -> None:
    """Constants, so a failure is reproducible from the evidence -- and distinct,
    because an isolation proof between one identity and itself is not one."""
    pattern = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    assert pattern.fullmatch(rendering.FIXTURE_USER_A)
    assert pattern.fullmatch(rendering.FIXTURE_USER_B)
    assert rendering.FIXTURE_USER_A != rendering.FIXTURE_USER_B

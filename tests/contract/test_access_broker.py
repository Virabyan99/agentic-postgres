"""The release-side access broker, and the trampoline in front of it (ADR 0043).

Built against a directory tree in ``tmp_path``, which is the whole reason the
resolution lives in a module rather than in the shell script that calls it. The
interesting failures here — a stale generation pointer, two live allocations
carrying one project key, a document whose secret reference has drifted from the
release's — are ones that take a rotation, a rebuild or a bad deploy to produce
on a real host, and none of them can be produced on demand there.

What is asserted structurally rather than executed is the split itself: the
trampoline holds no answer a release owns, and the sudo rule names one program.
Those are properties of files, and reading the file is the honest way to check
a property of a file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, access_broker, access_policy
from agentic_postgres.access_broker import BrokerError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

LIBEXEC = REPO_ROOT / "libexec"
TRAMPOLINE = LIBEXEC / "agentic-postgres-database-access"
BROKER = LIBEXEC / "database-access-broker"

OPERATOR = "op"
PROJECT = "agentic-alpha-dev"
POOLED_PORT = 15432
DIRECT_PORT = 15433
LOOPBACK = "127.0.0.1"
DATABASE = "agentic_alpha_dev"
RUNTIME_ROLE = "apg_agentic_alpha_dev_app_runtime"
MIGRATION_ROLE = "apg_agentic_alpha_dev_migration_user"

#: Two generations, and the values differ. The point of every password test here
#: is *which* of the two comes back.
OLD_GENERATION = "aaaa1111bbbb2222"
NEW_GENERATION = "cccc3333dddd4444"
OLD_PASSWORD = "the-credential-a-rotation-replaced"  # noqa: S105
NEW_PASSWORD = "the-credential-the-pooler-is-mounting"  # noqa: S105


#: The container address a stub resolver returns.
#:
#: ADR 0044 made the endpoint's `host` the container's current address on the
#: project network, resolved from Docker at call time and never written down.
#: `endpoint()` takes the resolver as a parameter precisely so that the rest of
#: this module -- which reads files under a root it was given -- does not have
#: to move onto a host to keep testing the parts that have nothing to do with
#: Docker.
CONTAINER_ADDRESS = "172.23.0.9"


def stub_resolver(container: str, network: str) -> str:
    """Record what was asked for, and answer without Docker."""
    stub_resolver.calls.append((container, network))
    return CONTAINER_ADDRESS


stub_resolver.calls = []


def broker_endpoint(host, profile: str):
    """`endpoint()` with the stub resolver, so no test reaches for Docker."""
    return access_broker.endpoint(
        PROJECT, profile, etc_root=host.etc, resolve_address=stub_resolver
    )


# ---------------------------------------------------------------------------
# A host, in a temporary directory
# ---------------------------------------------------------------------------


def deployed_document(*, instance_uuid: str | None = None, **overrides: Any) -> dict[str, Any]:
    """A deployed document, at version 4 by default.

    Version 4 is the default on purpose: it is what every host is running until
    it is redeployed, and it is the shape in which the broker has no instance
    UUID to match on. Passing ``instance_uuid`` produces the version 5 shape,
    with a `database.observed` block carrying the identity the registry is keyed
    by (ADR 0053).
    """
    profiles = {
        "runtime_pooled": {
            "status": "available",
            "available_from_session": 4,
            "transport": "pooled",
            "role": RUNTIME_ROLE,
            "password_secret_ref": "app_runtime_password",
        },
        "runtime_direct": {
            "status": "available",
            "available_from_session": 4,
            "transport": "direct",
            "role": RUNTIME_ROLE,
            "password_secret_ref": "app_runtime_password",
        },
        "migration_direct": {
            "status": "available",
            "available_from_session": 4,
            "transport": "direct",
            "role": MIGRATION_ROLE,
            "password_secret_ref": "migration_user_password",
        },
    }
    document = {
        "schema_version": 4,
        "document_kind": "deployed",
        "source_commit": "0" * 40,
        "deployed_through_session": 4,
        "project": {"key": PROJECT},
        "edge": {"project_internal_network": "apg-agentic-alpha-dev-internal"},
        "database": {
            "name": DATABASE,
            "container": "apg-agentic-alpha-dev-postgres-1",
            "access_profiles": profiles,
        },
    }
    if instance_uuid is not None:
        document["schema_version"] = 5
        document["database"]["observed"] = {
            "status": "observed",
            "server_version": "18.4",
            "extensions": {"plpgsql": "1.0"},
            "memory": {"anon_mb": 1, "shmem_mb": 1, "file_mb": 1},
            "instance_uuid": instance_uuid,
        }
    document.update(overrides)
    return document


def allocation(
    *,
    uuid: str = "11111111-2222-3333-4444-555555555555",
    project_key: str = PROJECT,
    pooled: int = POOLED_PORT,
    direct: int = DIRECT_PORT,
    state: str = "active",
) -> dict[str, Any]:
    return {
        "instance_uuid": uuid,
        "project_key": project_key,
        "pooled_port": pooled,
        "direct_port": direct,
        "state": state,
        "reserved_at": "2026-08-09T00:00:00Z",
        "activated_at": "2026-08-09T00:00:01Z" if state == "active" else None,
        "released_at": "2026-08-09T00:00:02Z" if state == "released" else None,
    }


@pytest.fixture
def host(tmp_path: Path):
    """A minimal host: policy, host manifest, registry, project, secrets.

    Returned as a small object with the two roots the broker takes, so a test
    that wants to break one thing edits one file and leaves the rest correct.
    """
    etc = tmp_path / "etc"
    secrets = tmp_path / "secrets"
    (etc / "projects" / PROJECT).mkdir(parents=True)
    (secrets / PROJECT / "generations" / OLD_GENERATION / "pgbouncer").mkdir(parents=True)
    (secrets / PROJECT / "generations" / NEW_GENERATION / "pgbouncer").mkdir(parents=True)
    (secrets / PROJECT / "generations" / NEW_GENERATION / "dbmate").mkdir(parents=True)

    (etc / "host.yaml").write_text(
        f"schema_version: 2\ndatabase_access:\n  loopback_address: {LOOPBACK}\n"
        "  port_range_start: 15000\n  port_range_end: 15999\n",
        encoding="utf-8",
    )
    (etc / "database-access-policy.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "grants": [
                    {
                        "unix_user": OPERATOR,
                        "project_key": PROJECT,
                        "profiles": ["runtime_pooled", "runtime_direct"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (etc / "database-port-allocations.json").write_text(
        json.dumps({"schema_version": 1, "allocations": [allocation()]}), encoding="utf-8"
    )
    (etc / "projects" / PROJECT / "outputs.json").write_text(
        json.dumps(deployed_document()), encoding="utf-8"
    )

    (secrets / PROJECT / "active-secret-generation.json").write_text(
        json.dumps({"generation_id": NEW_GENERATION}), encoding="utf-8"
    )
    for generation, value in ((OLD_GENERATION, OLD_PASSWORD), (NEW_GENERATION, NEW_PASSWORD)):
        (
            secrets / PROJECT / "generations" / generation / "pgbouncer" / "app_runtime_password"
        ).write_text(value, encoding="utf-8")
    (
        secrets / PROJECT / "generations" / NEW_GENERATION / "dbmate" / "migration_user_password"
    ).write_text("the-migration-credential", encoding="utf-8")

    class Host:
        def __init__(self) -> None:
            self.etc = etc
            self.secrets = secrets

        def write_policy(self, document: Any) -> None:
            (etc / "database-access-policy.json").write_text(json.dumps(document), encoding="utf-8")

        def write_document(self, document: Any) -> None:
            (etc / "projects" / PROJECT / "outputs.json").write_text(
                json.dumps(document), encoding="utf-8"
            )

        def write_registry(self, allocations: list[dict[str, Any]]) -> None:
            (etc / "database-port-allocations.json").write_text(
                json.dumps({"schema_version": 1, "allocations": allocations}), encoding="utf-8"
            )

    return Host()


# ---------------------------------------------------------------------------
# Authorization happens before anything about the project is read
# ---------------------------------------------------------------------------


def test_a_caller_with_no_grant_is_refused_before_the_project_is_looked_up(host) -> None:
    """ADR 0043's point 5, made measurable.

    The project here does not exist -- there is no directory for it and no
    allocation -- and the refusal is identical to the one for a project that
    does. If authorization moved after the lookup, this would become exit 4 and
    an unauthorized caller could enumerate deployed projects by exit code.
    """
    with pytest.raises(BrokerError) as raised:
        access_broker.authorize(
            unix_user=OPERATOR,
            project_key="never-deployed-here",
            profile="runtime_direct",
            etc_root=host.etc,
        )
    assert raised.value.code == 6
    assert str(raised.value) == "refused."


def test_the_refusal_names_neither_the_project_nor_the_profile(host) -> None:
    """The caller already knows what they asked for. The only reader who learns
    anything from a specific message is one probing for what exists."""
    with pytest.raises(BrokerError) as raised:
        access_broker.authorize(
            unix_user="stranger",
            project_key=PROJECT,
            profile="migration_direct",
            etc_root=host.etc,
        )
    message = str(raised.value)
    assert PROJECT not in message
    assert "migration_direct" not in message


def test_authorization_succeeds_for_a_project_that_does_not_exist(host) -> None:
    """The other half of the same property, and the one that proves the order.

    A grant naming a project that was never deployed authorizes; the failure
    comes later, from the lookup. If this raised, authorization would be reading
    project state.
    """
    host.write_policy(
        {
            "schema_version": 1,
            "grants": [
                {
                    "unix_user": OPERATOR,
                    "project_key": "never-deployed-here",
                    "profiles": ["runtime_direct"],
                }
            ],
        }
    )
    access_broker.authorize(
        unix_user=OPERATOR,
        project_key="never-deployed-here",
        profile="runtime_direct",
        etc_root=host.etc,
    )


def test_an_absent_policy_is_a_missing_prerequisite_not_an_empty_one(host) -> None:
    """A host that never had a policy and one whose policy was deleted are both
    "no access". Only one of them is a state somebody meant to be in."""
    (host.etc / "database-access-policy.json").unlink()
    with pytest.raises(BrokerError) as raised:
        access_broker.load_policy(etc_root=host.etc)
    assert raised.value.code == 3


def test_an_unusable_policy_is_a_contract_failure(host) -> None:
    host.write_policy({"schema_version": 1, "grants": [{"unix_user": "op"}]})
    with pytest.raises(BrokerError) as raised:
        access_broker.load_policy(etc_root=host.etc)
    assert raised.value.code == 5


def test_a_symlinked_policy_is_refused(host, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps(access_policy.empty_policy()), encoding="utf-8")
    path = host.etc / "database-access-policy.json"
    path.unlink()
    path.symlink_to(elsewhere)

    with pytest.raises(BrokerError) as raised:
        access_broker.load_policy(etc_root=host.etc)
    assert raised.value.code == 2


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


def test_each_transport_gets_its_own_port(host) -> None:
    """The two ports differ, so a swapped mapping is visible rather than
    plausible. A pooled profile answered on the direct port would connect and
    work -- with none of the pooling the profile's name promises."""
    pooled = access_broker.endpoint(
        PROJECT, "runtime_pooled", etc_root=host.etc, resolve_address=stub_resolver
    )
    direct = access_broker.endpoint(
        PROJECT, "runtime_direct", etc_root=host.etc, resolve_address=stub_resolver
    )

    # ADR 0044 split the endpoint in two, and the split is the point. `port` is
    # the CONTAINER port -- the far end of the tunnel, which never varies -- and
    # `local_port` is the ALLOCATED port the developer binds, which is what has
    # to differ between the transports and stay stable across a redeploy.
    assert (pooled["transport"], pooled["local_port"]) == ("pooled", POOLED_PORT)
    assert (direct["transport"], direct["local_port"]) == ("direct", DIRECT_PORT)
    assert pooled["port"] == access_broker.CONTAINER_PORTS["pooled"]
    assert direct["port"] == access_broker.CONTAINER_PORTS["direct"]
    assert pooled["local_port"] != direct["local_port"]

    # The tunnel target is a container address, resolved per call and never
    # written down; the near end is the host's loopback.
    assert pooled["host"] == direct["host"] == CONTAINER_ADDRESS
    assert pooled["local_address"] == direct["local_address"] == LOOPBACK

    # And the two transports are resolved from DIFFERENT containers. One
    # container answering for both is how a pooled profile ends up connecting
    # straight to the cluster with none of the pooling its name promises.
    pooled_container, direct_container = stub_resolver.calls[-2][0], stub_resolver.calls[-1][0]
    assert pooled_container.endswith("-pgbouncer-1")
    assert direct_container.endswith("-postgres-1")

    assert pooled["role"] == direct["role"] == RUNTIME_ROLE
    assert pooled["database"] == DATABASE


def test_the_endpoint_carries_no_credential_and_no_reference_to_one(host) -> None:
    answer = access_broker.endpoint(
        PROJECT, "runtime_direct", etc_root=host.etc, resolve_address=stub_resolver
    )
    rendered = json.dumps(answer)
    assert NEW_PASSWORD not in rendered
    assert OLD_PASSWORD not in rendered
    assert "password" not in rendered.lower()


def test_the_migration_profile_reports_the_migration_role(host) -> None:
    answer = access_broker.endpoint(
        PROJECT, "migration_direct", etc_root=host.etc, resolve_address=stub_resolver
    )
    assert answer["role"] == MIGRATION_ROLE
    assert answer["local_port"] == DIRECT_PORT
    assert answer["port"] == access_broker.CONTAINER_PORTS["direct"]


def test_a_rendered_document_is_refused(host) -> None:
    """A render knows no endpoint. Reading one here would produce an answer
    assembled from nulls."""
    host.write_document(deployed_document(document_kind="rendered"))
    with pytest.raises(BrokerError) as raised:
        access_broker.endpoint(
            PROJECT, "runtime_direct", etc_root=host.etc, resolve_address=stub_resolver
        )
    assert raised.value.code == 5


def test_an_unavailable_profile_is_missing_state_not_a_refusal(host) -> None:
    document = deployed_document()
    document["database"]["access_profiles"]["runtime_pooled"]["status"] = "unavailable"
    document["database"]["access_profiles"]["runtime_pooled"]["password_secret_ref"] = None
    host.write_document(document)

    with pytest.raises(BrokerError) as raised:
        access_broker.endpoint(
            PROJECT, "runtime_pooled", etc_root=host.etc, resolve_address=stub_resolver
        )
    assert raised.value.code == 4


def test_a_drifted_secret_reference_is_refused_rather_than_resolved(host) -> None:
    """The release's mapping and the document's record are two answers.

    They are written by different code at different times. When they disagree,
    one of them describes a system that no longer exists, and choosing either
    would hand over a credential the broker cannot identify.
    """
    document = deployed_document()
    document["database"]["access_profiles"]["runtime_direct"]["password_secret_ref"] = (
        "app_runtime_password_v2"  # noqa: S105 -- a secret's name, not a secret
    )
    host.write_document(document)

    with pytest.raises(BrokerError) as raised:
        access_broker.endpoint(
            PROJECT, "runtime_direct", etc_root=host.etc, resolve_address=stub_resolver
        )
    assert raised.value.code == 5
    assert "will not choose" in str(raised.value)


def test_a_document_without_access_profiles_names_the_fix(host) -> None:
    document = deployed_document()
    del document["database"]["access_profiles"]
    host.write_document(document)

    with pytest.raises(BrokerError) as raised:
        access_broker.endpoint(
            PROJECT, "runtime_direct", etc_root=host.etc, resolve_address=stub_resolver
        )
    assert raised.value.code == 5
    assert "redeploy" in str(raised.value).lower()


def test_a_host_manifest_without_the_database_section_is_refused(host) -> None:
    (host.etc / "host.yaml").write_text("schema_version: 1\nssh:\n  port: 22\n", encoding="utf-8")
    with pytest.raises(BrokerError) as raised:
        access_broker.endpoint(
            PROJECT, "runtime_direct", etc_root=host.etc, resolve_address=stub_resolver
        )
    assert raised.value.code == 5
    assert "loopback_address" in str(raised.value)


# ---------------------------------------------------------------------------
# The allocation lookup, and the identifier it does not have
# ---------------------------------------------------------------------------


def test_a_released_allocation_does_not_answer_for_a_project(host) -> None:
    host.write_registry([allocation(state="released")])
    with pytest.raises(BrokerError) as raised:
        access_broker.endpoint(
            PROJECT, "runtime_direct", etc_root=host.etc, resolve_address=stub_resolver
        )
    assert raised.value.code == 4


def test_two_live_allocations_for_one_key_refuse_rather_than_pick_the_first(host) -> None:
    """The registry is keyed by the volume's instance UUID; the project key is
    recorded for humans and is explicitly not the match key.

    **This is the version 4 path**, and it is still here because every host is
    running a version 4 document until it is redeployed. Such a document records
    no instance UUID, so the lookup has nothing else to search by. What it does
    about that is refuse ambiguity rather than take a first match -- because a
    first match here is a credential handed out for the wrong cluster, and
    nothing downstream would notice.

    The version 5 path below does not reach this refusal at all: it matches on
    the identity and never enumerates by key.
    """
    host.write_registry(
        [
            allocation(uuid="11111111-2222-3333-4444-555555555555"),
            allocation(uuid="99999999-8888-7777-6666-555555555555", pooled=15442, direct=15443),
        ]
    )
    with pytest.raises(BrokerError) as raised:
        access_broker.endpoint(
            PROJECT, "runtime_direct", etc_root=host.etc, resolve_address=stub_resolver
        )
    assert raised.value.code == 5
    assert "instance UUID" in str(raised.value)


def test_a_released_record_alongside_a_live_one_is_not_ambiguity(host) -> None:
    """Otherwise a rebuilt project could never be reached again."""
    host.write_registry(
        [
            allocation(uuid="99999999-8888-7777-6666-555555555555", state="released"),
            allocation(),
        ]
    )
    assert broker_endpoint(host, "runtime_direct")["local_port"] == DIRECT_PORT


# ---------------------------------------------------------------------------
# Version 5: the identifier it now has (ADR 0053, D106)
# ---------------------------------------------------------------------------

OTHER_UUID = "99999999-8888-7777-6666-555555555555"
THIS_UUID = "11111111-2222-3333-4444-555555555555"


def test_the_document_uuid_resolves_what_the_key_could_not(host) -> None:
    """The whole reason `instance_uuid` reached the deployed document.

    Two live allocations carry this project's key -- the exact situation the
    version 4 broker refused, because either answer might be a credential for
    the wrong cluster. With the identity in the document there is a right
    answer, and it is not the first one in the file: the fixture deliberately
    lists the *other* cluster first, so a lookup that fell back to enumeration
    would return the wrong ports and pass.
    """
    host.write_document(deployed_document(instance_uuid=THIS_UUID))
    host.write_registry(
        [
            allocation(uuid=OTHER_UUID, pooled=15442, direct=15443),
            allocation(uuid=THIS_UUID),
        ]
    )
    assert broker_endpoint(host, "runtime_direct")["local_port"] == DIRECT_PORT


def test_a_document_naming_an_unregistered_instance_is_missing_state(host) -> None:
    """Not a fallback to the key. A UUID with no allocation is exit 4.

    Falling back would make the identifier advisory: the broker would use it
    when it agreed and ignore it when it did not, which is the same as not
    having it.
    """
    host.write_document(deployed_document(instance_uuid=OTHER_UUID))
    with pytest.raises(BrokerError) as raised:
        broker_endpoint(host, "runtime_direct")
    assert raised.value.code == 4
    assert OTHER_UUID in str(raised.value)


def test_a_released_allocation_is_not_found_by_uuid_either(host) -> None:
    host.write_document(deployed_document(instance_uuid=THIS_UUID))
    host.write_registry([allocation(uuid=THIS_UUID, state="released")])
    with pytest.raises(BrokerError) as raised:
        broker_endpoint(host, "runtime_direct")
    assert raised.value.code == 4


def test_a_key_that_disagrees_with_the_registry_is_refused(host) -> None:
    """The key stops being a search term and becomes a check.

    Two records describing one cluster have to agree about what it is called
    before either can be trusted about where it is. This is the rebuild case: the
    volume kept its identity and the project was renamed around it.
    """
    host.write_document(deployed_document(instance_uuid=THIS_UUID))
    host.write_registry([allocation(uuid=THIS_UUID, project_key="some-other-project")])
    with pytest.raises(BrokerError) as raised:
        broker_endpoint(host, "runtime_direct")
    assert raised.value.code == 5
    assert "some-other-project" in str(raised.value)


@pytest.mark.parametrize(
    "observed",
    [
        pytest.param(None, id="version-4-document"),
        pytest.param(
            {
                "status": "not_observed",
                "server_version": None,
                "extensions": None,
                "memory": None,
                "instance_uuid": None,
            },
            id="nothing-was-read",
        ),
    ],
)
def test_a_document_with_no_identity_falls_back_to_the_old_refusal(host, observed) -> None:
    """Three situations, one honest response.

    A document written before version 5, a deployment that interrogated no
    cluster, and a cluster whose identity could not be read all mean the same
    thing: there is no identity to match on. The response to all three is the
    refusal that predates the field, not a guess.
    """
    document = deployed_document()
    if observed is not None:
        document["database"]["observed"] = observed
    host.write_document(document)
    host.write_registry(
        [allocation(uuid=THIS_UUID), allocation(uuid=OTHER_UUID, pooled=15442, direct=15443)]
    )
    with pytest.raises(BrokerError) as raised:
        broker_endpoint(host, "runtime_direct")
    assert raised.value.code == 5
    assert "redeploy the project" in str(raised.value)


def test_the_recorded_identity_is_read_from_the_one_place_it_lives(host) -> None:
    """`recorded_instance_uuid` is total: it answers for every document shape."""
    assert access_broker.recorded_instance_uuid(deployed_document()) is None
    assert access_broker.recorded_instance_uuid({}) is None
    assert access_broker.recorded_instance_uuid({"database": {"observed": None}}) is None
    assert (
        access_broker.recorded_instance_uuid(deployed_document(instance_uuid=THIS_UUID))
        == THIS_UUID
    )


# ---------------------------------------------------------------------------
# The password
# ---------------------------------------------------------------------------


def test_the_password_comes_from_the_active_pointer_not_the_document(host) -> None:
    """This is the test the whole module is built around.

    Two generations exist with different values. The pointer names the newer
    one -- the one the pooler is actually mounting. A broker that read the
    generation recorded in the deployed document would return the older value
    after any rotation, and the failure would surface as "password
    authentication failed" on the developer's machine, where the credential is
    the last thing anybody suspects.
    """
    assert (
        access_broker.password(
            PROJECT, "runtime_direct", etc_root=host.etc, secret_root=host.secrets
        )
        == NEW_PASSWORD
    )


def test_the_two_runtime_profiles_share_one_credential(host) -> None:
    """Same role, two transports. Two files would be two things a rotation has
    to reach, and the second one is the one it misses."""
    pooled = access_broker.password(
        PROJECT, "runtime_pooled", etc_root=host.etc, secret_root=host.secrets
    )
    direct = access_broker.password(
        PROJECT, "runtime_direct", etc_root=host.etc, secret_root=host.secrets
    )
    assert pooled == direct == NEW_PASSWORD


def test_the_migration_profile_reads_a_different_file(host) -> None:
    value = access_broker.password(
        PROJECT, "migration_direct", etc_root=host.etc, secret_root=host.secrets
    )
    assert value == "the-migration-credential"
    assert value != NEW_PASSWORD


def test_a_generation_that_is_not_a_bare_token_is_refused(host) -> None:
    """It is about to be a path component."""
    (host.secrets / PROJECT / "active-secret-generation.json").write_text(
        json.dumps({"generation_id": "../../../etc"}), encoding="utf-8"
    )
    with pytest.raises(BrokerError) as raised:
        access_broker.password(
            PROJECT, "runtime_direct", etc_root=host.etc, secret_root=host.secrets
        )
    assert raised.value.code == 2


def test_an_unmaterialized_secret_is_a_secret_failure(host) -> None:
    (
        host.secrets
        / PROJECT
        / "generations"
        / NEW_GENERATION
        / "pgbouncer"
        / "app_runtime_password"
    ).unlink()
    with pytest.raises(BrokerError) as raised:
        access_broker.password(
            PROJECT, "runtime_direct", etc_root=host.etc, secret_root=host.secrets
        )
    assert raised.value.code == 8


def test_an_empty_secret_file_is_a_failure_rather_than_an_empty_password(host) -> None:
    (
        host.secrets
        / PROJECT
        / "generations"
        / NEW_GENERATION
        / "pgbouncer"
        / "app_runtime_password"
    ).write_text("", encoding="utf-8")
    with pytest.raises(BrokerError) as raised:
        access_broker.password(
            PROJECT, "runtime_direct", etc_root=host.etc, secret_root=host.secrets
        )
    assert raised.value.code == 8


def test_no_failure_path_puts_the_credential_in_its_message(host) -> None:
    """An exception is the thing most likely to be logged."""
    for generation in (OLD_GENERATION, NEW_GENERATION):
        (host.secrets / PROJECT / "generations" / generation / "pgbouncer").chmod(0o000)
    try:
        with pytest.raises(BrokerError) as raised:
            access_broker.password(
                PROJECT, "runtime_direct", etc_root=host.etc, secret_root=host.secrets
            )
        assert OLD_PASSWORD not in str(raised.value)
        assert NEW_PASSWORD not in str(raised.value)
    finally:
        for generation in (OLD_GENERATION, NEW_GENERATION):
            (host.secrets / PROJECT / "generations" / generation / "pgbouncer").chmod(0o700)


def test_every_broker_exit_code_is_one_the_convention_already_has() -> None:
    """D42 froze the set and D87 mapped Session 4 onto it. A new code needs a
    reason no existing one covers, and then exactly one."""
    source = (REPO_ROOT / "src" / "agentic_postgres" / "access_broker.py").read_text(
        encoding="utf-8"
    )
    used = {int(code) for code in re.findall(r"BrokerError\((\d+),", source)}
    assert used <= {2, 3, 4, 5, 6, 8, 9}, (
        f"unconventional exit codes: {sorted(used - {2, 3, 4, 5, 6, 8, 9})}"
    )


# ---------------------------------------------------------------------------
# The split, read off the files
# ---------------------------------------------------------------------------


def test_the_trampoline_delegates_to_the_release_broker() -> None:
    text = TRAMPOLINE.read_text(encoding="utf-8")
    assert 'readonly RELEASE_BROKER="libexec/database-access-broker"' in text
    assert 'exec "${broker}" "$@"' in text


def test_the_trampoline_names_no_profile_and_no_secret(code_only) -> None:
    """Which profiles exist and which secret each maps to are release facts.

    Covered by the parametrized ADR 0037 assertion in
    tests/contract/test_host_infrastructure.py as well; stated again here
    because this is the launcher where getting it wrong hands out a credential
    rather than starting the wrong profile.
    """
    source = code_only(TRAMPOLINE.read_text(encoding="utf-8"))
    for name in (*access_policy.PROFILES, "app_runtime_password", "migration_user_password"):
        assert name not in source, f"the trampoline names {name}, which a release owns"


def test_the_release_broker_holds_no_policy_of_its_own(code_only) -> None:
    """It resolves an interpreter and execs. The decision is in Python because
    that is where it can be tested without a host."""
    source = code_only(BROKER.read_text(encoding="utf-8"))
    assert "bin/database-access.py" in source
    for name in access_policy.PROFILES:
        assert name not in source, f"the release broker names {name} instead of deferring to it"


def test_the_operator_command_cannot_reach_the_broker_operations() -> None:
    """`bin/database-access.sh` manages the policy and nothing else.

    A second way in would be a second thing the sudoers rule would eventually
    have to name, and the value of naming one immutable path is that it is one.
    """
    text = (REPO_ROOT / "bin" / "database-access.sh").read_text(encoding="utf-8")
    assert re.search(r"^\s*check\|publish\|show\)", text, re.MULTILINE)
    assert "is a broker operation, not an operator one" in text


def test_provisioning_installs_one_sudo_rule_for_one_program() -> None:
    """The rule permits invoking a path, not reading a directory of secrets.

    ADR 0043 rejected the alternative -- letting the helper read root-owned files
    under sudo -- because the rule would then have to permit reading every
    project's secrets, and the authorization decision would live in the caller.
    """
    provision = (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")
    assert "ALL=(root) NOPASSWD: %s/database-access" in provision
    assert 'readonly SUDOERS_FILE="/etc/sudoers.d/agentic-postgres-database-access"' in provision
    # 0440, because sudo ignores a sudoers file that is group- or world-writable
    # -- and ignoring it is ignoring every rule in it.
    assert 'install -m 0440 -o root -g root "${staging}" "${SUDOERS_FILE}"' in provision


def test_the_sudoers_file_is_checked_before_it_is_installed() -> None:
    """An invalid file in /etc/sudoers.d does not break one rule, it breaks sudo.

    On a host whose only administrative path is sudo over SSH, that is a lockout
    with the same shape as the sshd one this script already arms a rollback timer
    for -- and it costs one `visudo -cf` to avoid.
    """
    provision = (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")
    assert 'visudo -cf "${staging}"' in provision
    assert "visudo -c >/dev/null" in provision
    assert 'rm -f "${SUDOERS_FILE}"' in provision, "a policy that fails to parse must be removed"

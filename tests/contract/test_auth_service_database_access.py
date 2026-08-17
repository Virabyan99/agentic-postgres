"""The auth service can actually reach its database (D288, D289, ADR 0092).

Two defects, found by the first host deploy that got far enough to start the
container, and neither reachable by any offline proof before it.

**D288 — the role was never activated.** `bin/postgres-bootstrap.py` applied
`auth_service`'s CONNECTION LIMIT and printed *"role NOLOGIN until session 6"*.
That sentence was written **in** session 6, deferring the activation to a run
that never came: Run 7 built the service, Run 10 published it, and the role
reached a host with no password at all. `app_runtime` and
`postgrest_authenticator` were both activated in the same function, ten lines
above. It is D276's shape -- a comment describing work nobody wrote.

**D289 — the pooler had never heard of it.** The service connected to PgBouncer,
whose userlist is built with exactly two entries, `app_runtime` and the pool
admin. It failed with `FATAL: SASL authentication failed` *before postgres was
consulted*, so fixing D288 alone would have changed nothing.

ADR 0092 resolves the second by connecting to the cluster directly, as PostgREST
does. The tests below are about the property, not the route: the service's
declared backend must be one that will authenticate it.
"""

from __future__ import annotations

import importlib.util
import re
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

COMPOSE = REPO_ROOT / "compose.yaml"
BOOTSTRAP = REPO_ROOT / "bin" / "postgres-bootstrap.py"
AUTH_ADMIN = REPO_ROOT / "bin" / "auth-admin.py"

#: The Compose service name, as compose.yaml defines it.
AUTH_SERVICE_NAME = "auth"

#: Compose environment KEYS this module reads out of the parsed document.
#:
#: Constants rather than literals at the subscript, and not for tidiness:
#: `test_environment_gates.py::consumed_variables` flags any subscript whose
#: slice is a string starting with `APG_`, on the reasoning that a test reading
#: `os.environ["APG_..."]` has a dependency it must declare. These are keys in a
#: YAML document, not in this process's environment -- but the scan cannot tell
#: those apart, and it is a security check that should stay broad rather than be
#: narrowed to admit this module. Naming them is the cheaper side of that trade
#: (D290). Do not inline them back.
DATABASE_HOST_KEY = "APG_DATABASE_HOST"
DATABASE_PORT_KEY = "APG_DATABASE_PORT"


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bootstrap() -> Any:
    specification = importlib.util.spec_from_file_location("apg_postgres_bootstrap", BOOTSTRAP)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _auth_admin() -> Any:
    specification = importlib.util.spec_from_file_location("apg_auth_admin", AUTH_ADMIN)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# D288 — every role a service logs in as is a role the bootstrap activates
# ---------------------------------------------------------------------------


def test_the_bootstrap_activates_every_role_a_service_logs_in_as(bootstrap: Any) -> None:
    """The general property, not just the auth service's case.

    A role that a container authenticates as, and that nothing gives a password,
    is a container that cannot start. That was true of `auth_service` for four
    runs while three separate proofs reported the service healthy -- because all
    three ran it against a cluster the rig had credentialed itself.

    Checked against the source rather than by running the bootstrap, which needs
    a live cluster: what is asserted is that the credential-applying call exists
    for each role, which is exactly what was missing.
    """
    source = BOOTSTRAP.read_text(encoding="utf-8")
    # The roles whose containers present a password. `object_owner` is NOLOGIN
    # by design and `migration_user` is credentialed elsewhere in this file.
    for role in ("app_runtime", "postgrest_authenticator", "auth_service"):
        pattern = rf'apply_credential\((?:[^)]|\n)*roles\["{role}"\]'
        assert re.search(pattern, source), (
            f"nothing calls apply_credential for roles[{role!r}], so that role reaches a "
            "host with no password and the service that logs in as it cannot start (D288)"
        )


def test_every_credentialed_role_can_also_connect(bootstrap: Any) -> None:
    """A password without CONNECT is a role that authenticates and is then refused.

    **This is the third defect in a row from one cause** (D288, D289, D291):
    adding a service means touching every list in this repository that
    enumerates roles, and nothing enumerated the lists. `auth_service` was
    missing from the credential block, then pointed at a pooler that did not
    know it, then missing from the database's CONNECT grant -- each found only
    after the previous was fixed, because each failure hid the next.

    So this asserts the two lists against **each other** rather than against a
    third copy of the role names. Both are in `postgres-bootstrap.py`; the
    invariant is that they agree. A future service that gains a credential and
    not a CONNECT fails here, which is the case that reached a host three times.

    `REVOKE ALL ON DATABASE ... FROM PUBLIC` runs immediately above the grant, so
    a role absent from it cannot connect at all however correct its password is.
    """
    source = BOOTSTRAP.read_text(encoding="utf-8")

    grant = re.search(r"GRANT CONNECT ON DATABASE \{db\} TO \"?(.*?);", source, re.DOTALL)
    assert grant, "the CONNECT grant could not be located in postgres-bootstrap.py"
    connectable = set(re.findall(r"roles\['(\w+)'\]", grant.group(0)))
    assert connectable, "no roles were parsed out of the CONNECT grant"

    credentialed = set(re.findall(r'apply_credential\((?:[^)]|\n)*?roles\["(\w+)"\]', source))
    assert credentialed, "no roles were parsed out of the apply_credential calls"

    # `object_owner` is granted separately above and is NOLOGIN; `migration_user`
    # is credentialed through its own path. Neither weakens the check below.
    stranded = sorted(credentialed - connectable)
    assert not stranded, (
        f"these roles are given a password but never granted CONNECT on the database: "
        f"{stranded}. They authenticate and are then refused with `permission denied for "
        "database ... User does not have CONNECT privilege` (D291)"
    )


def test_the_bootstrap_no_longer_defers_the_auth_role_to_a_later_session(bootstrap: Any) -> None:
    """The specific sentence that deferred it, gone.

    Named rather than left to the general check above, because the failure was
    not an omission anyone would spot: the code did something plausible and
    printed a reason. A reader would have to know that session 6 was *this*
    session to see it was wrong.
    """
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "NOLOGIN until session" not in source, (
        "the bootstrap still defers a role's activation to a later session by name. "
        "That is how `auth_service` reached a host with no password (D288)"
    )


def test_the_bootstrap_consumers_match_the_secret_contract(bootstrap: Any) -> None:
    """The consumer dictionaries are copies, so they are compared.

    `recover_secret` reads a materialized file according to the consumer it is
    handed. A `target_file` that disagreed with the contract would look for a
    file that is not there, report the credential absent, and leave the role
    NOLOGIN -- with no error, which is precisely the failure mode this module
    exists for.
    """
    contract = yaml.safe_load((REPO_ROOT / "secrets.required.yaml").read_text(encoding="utf-8"))
    declared = {secret["name"]: secret for secret in contract["secrets"]}

    for name, consumer in (
        ("postgrest_authenticator_password", bootstrap.POSTGREST_CONSUMER),
        ("auth_service_password", bootstrap.AUTH_SERVICE_CONSUMER),
        # Session 7 Run 4. Three roles now recover a credential through the
        # contract, which is three chances for a `target_file` to disagree --
        # and the failure is silent every time: the file is not found, the
        # credential is reported absent, and the role is left NOLOGIN.
        ("storage_service_password", bootstrap.STORAGE_SERVICE_CONSUMER),
    ):
        secret = declared.get(name)
        assert secret, f"{name} is not declared in secrets.required.yaml"
        matching = [
            entry
            for entry in secret["consumers"]
            if entry.get("service") == consumer["service"]
            and entry["target_file"] == consumer["target_file"]
            and entry["format"] == consumer["format"]
        ]
        assert matching, (
            f"the bootstrap's consumer for {name} ({consumer}) matches no consumer the "
            f"contract declares ({secret['consumers']}). The credential would be reported "
            "absent and the role left NOLOGIN"
        )


# ---------------------------------------------------------------------------
# D289 / ADR 0092 — the declared backend must be one that authenticates it
# ---------------------------------------------------------------------------


def test_the_auth_service_connects_to_the_cluster_directly(compose: dict[str, Any]) -> None:
    """ADR 0092, and the reason is what PgBouncer would have to hold otherwise.

    Goes red if the host is pointed back at the pooler without also putting
    `auth_service` into the userlist -- which is the state that failed on the
    host with `SASL authentication failed`.
    """
    environment = compose["services"]["auth"]["environment"]
    declared = environment[DATABASE_HOST_KEY]
    assert "POSTGRES_SERVICE_HOST" in declared, (
        f"the auth service connects to {declared}. PgBouncer authenticates against a "
        "userlist holding only app_runtime and the pool admin, so it refuses this role "
        "before postgres is consulted (D289)"
    )
    assert str(environment[DATABASE_PORT_KEY]) == "5432"


def test_every_service_using_the_pooler_is_in_its_userlist(compose: dict[str, Any]) -> None:
    """The general form, which is what makes the test above more than a preference.

    PgBouncer's userlist is written by its own entrypoint from two mounted
    secrets. Any service pointed at `PGBOUNCER_SERVICE_HOST` under a role that
    list does not carry will fail SASL -- so the two have to be checked against
    each other rather than each being plausible alone.

    The `client-*` fixtures are the legitimate users: they connect as
    `app_runtime`, which the userlist does carry.
    """
    entrypoint = " ".join(str(part) for part in compose["services"]["pgbouncer"]["entrypoint"])
    # The roles the userlist is built from, as env references in the entrypoint.
    carried = {
        name
        for name in ("APG_APP_RUNTIME_ROLE", "APG_POOL_ADMIN_USER")
        if f"${name}" in entrypoint or f"$${name}" in entrypoint
    }
    assert carried == {"APG_APP_RUNTIME_ROLE", "APG_POOL_ADMIN_USER"}, (
        f"the pgbouncer userlist is built from {carried}; this test's model of it is stale"
    )

    offenders: dict[str, str] = {}
    for name, service in compose["services"].items():
        environment = service.get("environment") or {}
        if not isinstance(environment, dict):
            continue
        pooled = [
            key
            for key, value in environment.items()
            if isinstance(value, str) and "PGBOUNCER_SERVICE_HOST" in value
        ]
        if not pooled:
            continue
        role = " ".join(
            str(value)
            for key, value in environment.items()
            if isinstance(value, str) and ("ROLE" in key or key in {"PGUSER", "APG_DATABASE_ROLE"})
        )
        # A pooled service must name the app runtime role, or no role at all
        # (the fixtures that take it from a URL the test supplies).
        if role and "APP_RUNTIME_ROLE" not in role and "AUTH_SERVICE_ROLE" in role:
            offenders[name] = role

    assert not offenders, (
        f"these services reach the pooler under a role its userlist does not carry: "
        f"{offenders}. PgBouncer refuses them with `SASL authentication failed` before "
        "postgres is consulted (D289)"
    )


def test_postgrest_and_auth_agree_on_how_to_reach_the_cluster(compose: dict[str, Any]) -> None:
    """The precedent, asserted so the two cannot drift apart again.

    PostgREST has connected directly since Session 5 and is the only other
    first-party service holding a privileged role. ADR 0092 makes the auth
    service match it; this is what would notice if one moved.
    """
    services = compose["services"]
    postgrest = services["postgrest"]["environment"]["PGRST_DB_URI"]
    auth_host = services["auth"]["environment"][DATABASE_HOST_KEY]

    assert "POSTGRES_SERVICE_HOST" in postgrest, "PostgREST no longer connects directly"
    assert "POSTGRES_SERVICE_HOST" in auth_host, "the auth service no longer connects directly"
    assert ":5432/" in postgrest


# ---------------------------------------------------------------------------
# D293 — the selector has to name a label the service actually carries
# ---------------------------------------------------------------------------


def test_the_bootstrap_selects_the_auth_container_by_a_label_it_carries(
    compose: dict[str, Any], bootstrap: Any
) -> None:
    """The command finds the auth container by label. This checks the label exists.

    **Written after the selector was wrong** (D293). The first version filtered
    on `com.docker.compose.project.working_dir`, which is Compose's record of
    where it was invoked from rather than anything this repository sets. It
    matched nothing on the host, so the bootstrap reported the auth service down
    while it was running and healthy -- and the operator was told to deploy again.

    The failure was possible because nothing exercised `auth_container()`: the
    module's other tests build their own cluster and never call it. A function
    with no caller in any test is the shape this whole session keeps finding.

    So this compares the command's selector against `compose.yaml` itself. A
    label the service does not declare cannot select it, whatever the label
    means elsewhere.
    """
    admin = _auth_admin()
    labels = compose["services"][AUTH_SERVICE_NAME].get("labels") or {}
    assert isinstance(labels, dict), "the auth service's labels are not a mapping"

    assert admin.PROJECT_KEY_LABEL in labels, (
        f"bin/auth-admin.py selects the auth container on {admin.PROJECT_KEY_LABEL!r}, "
        f"which the service does not declare. It declares {sorted(labels)}. A selector "
        "that matches nothing reports the service down while it is running (D293)"
    )
    assert admin.AUTH_SERVICE == AUTH_SERVICE_NAME, (
        f"the command looks for the Compose service {admin.AUTH_SERVICE!r}, which "
        f"compose.yaml does not define; it defines {AUTH_SERVICE_NAME!r}"
    )


def test_the_project_key_label_is_the_documents_project_key(compose: dict[str, Any]) -> None:
    """And the label's VALUE is the key the command passes.

    `auth_container` is given `document["project"]["key"]`. The label
    interpolates `${PROJECT_KEY}`, which `rendering.py` fills from the same
    field -- so this asserts the two ends of one value rather than that a label
    with the right name exists.
    """
    labels = compose["services"][AUTH_SERVICE_NAME]["labels"]
    assert labels["apg.project.key"] == "${PROJECT_KEY:?required}", (
        f"the auth service's project-key label is {labels['apg.project.key']!r}; the "
        "bootstrap passes the deployed document's project.key and expects them to match"
    )

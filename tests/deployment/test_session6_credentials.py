"""A raw credential exists nowhere but in the request that carried it (SEC-CRED-001).

Replaces the Session 6 placeholder
``tests/security/test_future_security_boundaries.py::test_raw_credentials_are_never_stored_or_logged``.

The requirement names six places: storage, logs, evidence, process arguments,
image layers and database error detail. Each is checked against a value this
test **plants itself**, which is the only construction that can fail. A scan for
"a password-shaped string" finds nothing in a system that stores hashes, and
passes equally well against one that logs every password it receives -- because
the scanner does not know what to look for. Planting the value first is the same
move ``--sentinel-file`` makes for the secret generations (D213), applied to a
credential that never touches disk at all.

Three of the six are properties of the running deployment and are measured here.
The other three -- image layers, evidence documents and process arguments -- are
already measured by Session 2's secret-model suite over every materialized
secret, and are re-asserted here only for the values this session introduced.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Interpolated values are a UUID from this module's own fixture and role names
# read from a validated deployed document. See this directory's conftest.
import json
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import runtime_override
from agentic_postgres.host_config import EDGE_STACK_NAME

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: The planted value. Distinctive enough that a substring search cannot match
#: anything else on the host, and long enough to pass `assess`.
PLANTED_PASSWORD = "apg-sentinel-plaintext-must-never-appear-31415926"  # noqa: S105

#: How far back to read each container's log. The login below happens seconds
#: earlier, so a window of minutes is generous and keeps the scan bounded on a
#: host that has been up for weeks.
LOG_WINDOW = "10m"


def test_a_password_this_test_planted_reaches_no_store_and_no_log(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    app_login: Callable[..., Any],
    api_call: Callable[..., Any],
    app_probe_subject: Any,
    psql: Callable[..., tuple[int, str, str]],
    sh: Callable[..., str],
    service_container: Callable[[str, str], str],
    as_root: None,
) -> None:
    """SEC-CRED-001, against a value that is definitely in the system.

    The value is sent twice on purpose: once as a **successful** login, after
    setting it as the probe subject's password, and once as a **failed** one.
    Both paths are interesting and they are not the same code -- a failure runs
    the dummy-verify path, and a service that logged the attempted password
    would most plausibly do it there, in an "authentication failed for X" line.

    Then four readings:

    * the identity registry -- the stored verifier is an Argon2id PHC string and
      the plaintext appears in no column of the row;
    * the auth container's log;
    * the edge's log, which sees every request body's *size* and must never see
      its content;
    * ``docker inspect`` over every running container, which covers process
      arguments and environment in one reading.

    Goes red if: a password reaches a log at any level; the service starts
    storing anything reversible; or a request body is echoed into an error.
    """
    del as_root
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    base = app_base(project_a)

    code, _, error = psql(
        project_a,
        f"SELECT app_private.auth_set_password('{app_probe_subject.user_id}', "
        f"'{hashing.Hasher().hash(PLANTED_PASSWORD)}');",
    )
    assert code == 0, f"could not set the planted password: {error}"

    try:
        good = app_login(project_a, app_probe_subject.username, PLANTED_PASSWORD)
        assert good.status == 200, (
            f"the planted password does not authenticate ({good.status}); it never "
            "entered the system, so nothing below is a measurement"
        )
        bad = app_login(project_a, "no-such-subject-at-all", PLANTED_PASSWORD)
        assert bad.status == 401, f"an unknown subject answered {bad.status}"

        # Also through the token endpoint, whose failure path differs.
        refused = api_call(
            f"{base}/auth/agent-token",
            method="POST",
            body={"agent_id": "no-such-agent", "secret": PLANTED_PASSWORD},
        )
        assert refused.status in (400, 401, 404, 422), f"an unknown agent answered {refused.status}"

        # 1. Storage.
        code, row, error = psql(
            project_a,
            "SELECT coalesce(string_agg(c.password_hash, ' '), '') FROM "
            "app_private.user_credentials c WHERE c.user_id = "
            f"'{app_probe_subject.user_id}';",
        )
        assert code == 0, f"could not read the stored verifier: {error}"
        assert PLANTED_PASSWORD not in row, "the plaintext password is in the credential store"
        assert row.startswith("$argon2id$"), (
            f"the stored verifier is not an Argon2id PHC string: {row[:32]!r}"
        )

        code, anywhere, error = psql(
            project_a,
            f"SELECT count(*) FROM app_private.users u WHERE u::text LIKE '%{PLANTED_PASSWORD}%';",
        )
        assert code == 0, f"could not scan the subject row: {error}"
        assert anywhere == "0", "the plaintext password appears somewhere in the subject's row"

        # 2 and 3. The logs of every container that saw the request.
        project_key = project_a["project"]["key"]
        for service in (runtime_override.AUTH_SERVICE, runtime_override.REST_SERVICE):
            container = service_container(project_key, service)
            log = sh("docker", "logs", "--since", LOG_WINDOW, container)
            assert PLANTED_PASSWORD not in log, (
                f"the {service} container logged the password it was sent"
            )

        # `apg-edge` is the STACK; the container is `apg-edge-traefik-1`. Read
        # from the same constant the Session 2 edge proofs use rather than
        # spelled out here -- a wrong container name fails as "no such
        # container", which reads as a broken deployment rather than as a typo.
        edge_log = sh("docker", "logs", "--since", LOG_WINDOW, f"{EDGE_STACK_NAME}-traefik-1")
        assert PLANTED_PASSWORD not in edge_log, "the edge logged a request body"

        # 4. Process arguments, environment and mounts, for everything running.
        names = [line for line in sh("docker", "ps", "--format", "{{.Names}}").splitlines() if line]
        assert names, "no containers are running, so nothing here was inspected"
        for name in names:
            assert PLANTED_PASSWORD not in sh("docker", "inspect", name), (
                f"{name} carries the password in its arguments, environment or labels"
            )

    finally:
        psql(
            project_a,
            f"SELECT app_private.auth_set_password('{app_probe_subject.user_id}', "
            f"'{hashing.Hasher().hash(app_probe_subject.password)}');",
        )


def test_a_database_error_reaches_the_caller_without_its_detail(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    admin_session: Any,
) -> None:
    """The sixth place: database error detail, which is published verbatim by default.

    ADR 0057 recorded that PostgREST publishes `HINT` and `DETAIL` from a `RAISE`
    straight to an HTTP caller. The auth service is a different program and makes
    its own choice, and this asserts the choice: a constraint violation must not
    reach the caller carrying the row that caused it.

    Driven through the scope ceiling, because that is a refusal the *database*
    makes -- `is_scope_set` and the role ceiling -- rather than one the service
    makes first. A payload refused by pydantic would never reach the cluster and
    would prove nothing about error detail.
    """
    answer = api_call(
        f"{app_base(project_a)}/admin/users",
        method="POST",
        token=admin_session.token,
        body={
            "username": "error-detail-probe",
            "display_name": "Error detail probe",
            "role": project_a["database"]["roles"]["authenticated"],
            "scopes": ["tasks:read", "notes:read"],
            "password": "an-entirely-adequate-passphrase-2288",
        },
    )

    # Sorted-scope order is what `is_scope_set` refuses (D248), so this is
    # expected to fail -- and if the service sorts before storing, it succeeds
    # instead. Both are acceptable outcomes for THIS test, whose subject is the
    # body of the response rather than the verdict.
    body = answer.body.lower()
    for leak in ("detail:", "hint:", "constraint", "app_private.users", "pg_catalog", "sqlstate"):
        assert leak not in body, (
            f"the response body carries {leak!r}, which is database error detail reaching "
            f"an HTTP caller (ADR 0057's shape in a different program): {answer.body[:300]!r}"
        )

    if answer.status >= 400:
        parsed = json.loads(answer.body)
        assert set(parsed) <= {"error", "message", "detail"}, (
            f"the error body carries members beyond the declared shape: {sorted(parsed)}"
        )

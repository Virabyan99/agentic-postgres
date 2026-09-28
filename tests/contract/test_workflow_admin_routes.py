"""The four HUMAN workflow routes: an access token, two scopes, fixed refusals.

`WF-ADMIN-001` and the route half of `WF-PROV-001` (ADR 0230-0234). Driven
over ASGI against the real `create_app("auth")` with the lifespan not run --
`test_workflow_routes.py`'s rig, and its stated trade: `app.state.service` and
`app.state.workflows` are set directly, which is what the lifespan sets them
to.

**Unlike that module, the service here is a REAL `AuthService`**, issuing and
verifying with one generated key, over a vocabulary read from the example
project's lock through the product's own chain. The load-bearing refusals of
these four routes are *which authenticator* and *which scope*, and a fake
service would answer both out of this module's own belief (CLAUDE.md §7,
question 6). So every token below is minted by `issue`, the approver's
`admin_workflows:approve` among them -- which also proves the `project_admin`
ceiling the lock carries admits the new scope at all.

The workflow repository IS a fake. What the database decides -- the owner
refused, a decision final, an expiry, what a listing or a provenance document
may carry -- is `test_workflow_gates.py`'s, under a real cluster; asked again
here it would be asked of a fake.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from tests.contract.test_workflow_routes import (
    FakeError,
    NoHasher,
    _lock_document,
    _signing_key,
    call,
)

from agentic_postgres import service_source

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

main = service_source.load("main")
errors = service_source.load("errors")
service_module = service_source.load("service")
repository_module = service_source.load("repository")

ADMIN_ROLE = "apg_fixture_alpha_dev_project_admin"
AGENT_ROLE = "apg_fixture_alpha_dev_agent_writer"

APPROVE = "admin_workflows:approve"
AUDIT = "admin_audit:read"

#: Three humans, each holding ONE administrative scope, so a refusal says which
#: scope was missing and a success says which one served. A subject holding
#: two could not tell the two routes' scopes apart.
APPROVER = uuid4()
AUDITOR = uuid4()
ROSTER_READER = uuid4()
HUMANS: dict[UUID, list[str]] = {
    APPROVER: [APPROVE],
    AUDITOR: [AUDIT],
    ROSTER_READER: ["admin_agents:read"],
}

AGENT = uuid4()
RUN = uuid4()

#: A value that stands for an argument, an input or a result. It is put where
#: the DATABASE could have put it -- its messages, its documents -- and must
#: never come back out of a refusal.
ARGUMENT_VALUE = "xyzzy-an-argument-value-nobody-may-read"


class Directory:
    """The service's repository: three humans and one agent, and nothing else.

    `state` is what `authenticate` compares a token against; `lookup_agent` is
    what `authenticate_agent` does. Mutable, so an arm can revoke the agent.
    """

    def __init__(self) -> None:
        self.states = {
            user: repository_module.SubjectState(
                username=f"human-{index}",
                display_name="A human",
                role_name=ADMIN_ROLE,
                scopes=sorted(scopes),
                status="active",
                credential_version=1,
                authz_version=1,
                last_login_at=None,
            )
            for index, (user, scopes) in enumerate(HUMANS.items())
        }
        self.agent = repository_module.AgentCredential(
            agent_id=AGENT,
            role_name=AGENT_ROLE,
            scopes=["notes:write"],
            status="active",
            authz_version=1,
            # A syntactically valid Argon2 encoding that verifies nothing (the
            # sibling module's reason; S106 matches on the name).
            secret_hash="$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA",  # noqa: S106
        )

    async def state(self, user_id: UUID) -> Any:
        return self.states.get(user_id)

    async def lookup_agent(self, agent_id: UUID) -> Any:
        return self.agent if agent_id == self.agent.agent_id else None


@pytest.fixture
def service() -> Any:
    """A REAL `AuthService` over one generated key and the example lock's vocabulary."""
    tokens = service_source.load("tokens")
    scope_map = service_source.load("scopes")

    private = _signing_key()
    lock = tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False)
    lock.write(json.dumps(_lock_document()))
    lock.close()
    return service_module.AuthService(
        repository=Directory(),
        hasher=NoHasher(),
        signing_key=private,
        key_set=tokens.LocalKeySet.load(json.dumps(private.jwks()).encode("utf-8")),
        issuer="https://workflow-admin-routes.invalid",
        audience="workflow-admin-routes",
        role_suffixes={ADMIN_ROLE: "project_admin", AGENT_ROLE: "agent_writer"},
        vocabulary=scope_map.load_vocabulary(lock.name),
    )


def human(service: Any, user_id: UUID) -> dict[str, str]:
    """An ACCESS token for one of the three humans, minted by `issue`."""
    state = service.repository.states[user_id]
    credential = repository_module.Credential(
        user_id=user_id,
        role_name=state.role_name,
        scopes=list(state.scopes),
        status=state.status,
        credential_version=state.credential_version,
        authz_version=state.authz_version,
        password_hash=None,
    )
    issued = service.issue(credential, token_use="access")  # noqa: S106
    return {"Authorization": f"Bearer {issued.token}"}


def agent(service: Any) -> dict[str, str]:
    """An AGENT token for the one agent, minted the way `/auth/agent-token` mints it."""
    issued = service.issue(
        service._as_credential(service.repository.agent),
        token_use="agent",  # noqa: S106
    )
    return {"Authorization": f"Bearer {issued.token}"}


class FakeWorkflows:
    """The repository's three human calls, recording and raising as told."""

    def __init__(
        self,
        raises: Exception | None = None,
        approvals: list[dict[str, Any]] | None = None,
        document: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._raises = raises
        self._approvals = approvals if approvals is not None else []
        self._document = document

    async def pending_approvals(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("pending_approvals", kwargs))
        if self._raises:
            raise self._raises
        return self._approvals

    async def decide(self, **kwargs: Any) -> str:
        self.calls.append(("decide", kwargs))
        if self._raises:
            raise self._raises
        return "approved" if kwargs["decision"] == "approve" else "rejected"

    async def provenance(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("provenance", kwargs))
        if self._raises:
            raise self._raises
        return self._document or {"run": {"id": str(kwargs["run_id"])}, "steps": []}

    # The agent routes' three, so the agent surface can be driven as a control.
    async def status(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("status", kwargs))
        return {"run_id": str(kwargs["run_id"]), "status": "cancelled", "steps": []}


def build(service: Any, workflows: Any = None) -> Any:
    application = main.create_app("auth")
    application.state.service = service
    application.state.workflows = workflows if workflows is not None else FakeWorkflows()
    return application


#: The four routes, as (method, path, body).
ROUTES = (
    ("GET", "/admin/workflows/approvals", None),
    ("POST", f"/admin/workflows/runs/{RUN}/approve", {"step": "set_the_status"}),
    ("POST", f"/admin/workflows/runs/{RUN}/reject", {"step": "set_the_status"}),
    ("GET", f"/admin/workflows/runs/{RUN}", None),
)


def send(application: Any, method: str, path: str, body: Any, headers: dict[str, str]) -> Any:
    return call(
        application, method, path, headers=headers, **({"json": body} if body is not None else {})
    )


# ---------------------------------------------------------------------------
# Mounted, and named by the document
# ---------------------------------------------------------------------------


def test_the_four_routes_are_mounted_in_auth_mode_and_named_by_the_openapi_document() -> None:
    """Four routes, in `auth` mode only, every one published and reachable.

    A route the document does not name is a surface nobody reviewed (ADR
    0050), and one missing from `public_paths` is a route an approver off the
    host cannot reach -- an approval nobody can give.
    """
    application = main.create_app("auth")
    mounted = {
        (method, route.path)
        for route in application.routes
        for method in (getattr(route, "methods", None) or ())
    }
    wanted = {
        ("GET", "/admin/workflows/approvals"),
        ("POST", "/admin/workflows/runs/{run_id}/approve"),
        ("POST", "/admin/workflows/runs/{run_id}/reject"),
        ("GET", "/admin/workflows/runs/{run_id}"),
    }
    assert wanted <= mounted, wanted - mounted

    storage = main.create_app("storage")
    assert not [r.path for r in storage.routes if r.path.startswith("/admin/workflows")]

    document = application.openapi()
    for method, path in wanted:
        operation = document["paths"][path][method.lower()]
        assert operation["summary"], path
        assert {"200", "401", "403"} <= set(operation["responses"]), (path, operation["responses"])
    for decision in ("approve", "reject"):
        responses = document["paths"][f"/admin/workflows/runs/{{run_id}}/{decision}"]["post"][
            "responses"
        ]
        assert {"400", "404", "409"} <= set(responses), responses
    limit = document["paths"]["/admin/workflows/approvals"]["get"]["parameters"]
    assert [parameter["name"] for parameter in limit] == ["limit"]

    assert {path for _, path in wanted} <= set(main.public_paths())


# ---------------------------------------------------------------------------
# The authenticator and the scopes
# ---------------------------------------------------------------------------


def test_an_agent_token_is_refused_by_every_admin_workflow_route(service: Any) -> None:
    """ADR 0232's first control: the agent whose run waits cannot decide it.

    Every route calls `authenticate`, which refuses a token whose `token_use`
    is `agent` BEFORE any scope is read -- so the answer is a 401 and nothing
    reaches the repository. The control is the same token accepted by the
    AGENT surface: it is a valid token, refused for what it is.
    """
    workflows = FakeWorkflows()
    application = build(service, workflows)
    token = agent(service)
    for method, path, body in ROUTES:
        answered = send(application, method, path, body, token)
        assert answered.status_code == 401, (path, answered.status_code, answered.text)
        assert answered.json() == errors.AUTHENTICATION_FAILED, path
    assert workflows.calls == [], workflows.calls

    control = call(application, "GET", f"/workflows/runs/{RUN}", headers=token)
    assert control.status_code == 200, (
        f"the control failed: the agent token is not accepted by its own surface either, so "
        f"the 401s above say nothing about which surface refused it -- {control.text}"
    )


def test_approve_and_reject_need_the_approve_scope(service: Any) -> None:
    """`admin_workflows:approve`, and not the audit scope or the roster's.

    The auditor holds `admin_audit:read`, which reads a run's whole
    provenance; it may not decide one. The decision reaches the repository
    only for the approver, and it carries the APPROVER'S id from the token --
    never one a caller named.
    """
    workflows = FakeWorkflows()
    application = build(service, workflows)
    for method, path, body in ROUTES[:3]:
        for refused in (AUDITOR, ROSTER_READER):
            answered = send(application, method, path, body, human(service, refused))
            assert answered.status_code == 403, (path, refused, answered.text)
            assert answered.json() == errors.AUTHORIZATION_FAILED
    assert workflows.calls == [], workflows.calls

    for decision, word in (("approve", "approved"), ("reject", "rejected")):
        answered = send(
            application,
            "POST",
            f"/admin/workflows/runs/{RUN}/{decision}",
            {"step": "set_the_status"},
            human(service, APPROVER),
        )
        assert answered.status_code == 200, answered.text
        assert answered.json() == {"run_id": str(RUN), "step": "set_the_status", "approval": word}
        assert answered.headers["cache-control"] == "no-store"

    listed = send(application, "GET", "/admin/workflows/approvals", None, human(service, APPROVER))
    assert listed.status_code == 200, listed.text

    decided = [arguments for name, arguments in workflows.calls if name == "decide"]
    assert decided == [
        {"run_id": RUN, "step": "set_the_status", "user_id": APPROVER, "decision": "approve"},
        {"run_id": RUN, "step": "set_the_status", "user_id": APPROVER, "decision": "reject"},
    ]


def test_provenance_is_served_under_the_audit_scope_only(service: Any) -> None:
    """The audit's reader, under the audit's scope (ADR 0234).

    The approver is refused: deciding one parked step is not reading every
    run's history. The roster reader is refused for the reason
    `test_auth_endpoints.py` gives about the audit endpoint -- which agents
    exist and what they did are different authorities.
    """
    workflows = FakeWorkflows()
    application = build(service, workflows)
    path = f"/admin/workflows/runs/{RUN}"
    for refused in (APPROVER, ROSTER_READER):
        answered = call(application, "GET", path, headers=human(service, refused))
        assert answered.status_code == 403, (refused, answered.text)
        assert answered.json() == errors.AUTHORIZATION_FAILED
    assert workflows.calls == []

    served = call(application, "GET", path, headers=human(service, AUDITOR))
    assert served.status_code == 200, served.text
    assert served.json() == {"run": {"id": str(RUN)}, "steps": []}
    assert served.headers["cache-control"] == "no-store"


def test_provenance_answers_a_revoked_agents_stopped_run(service: Any) -> None:
    """D1704's other half: the agent cannot read its stopped run; an auditor can.

    The route passes the run id and NOTHING about an agent -- the auditor's
    read is not the agent's read with a wider scope, it is a different
    question with no owner in it. The agent is revoked in the directory, and
    its own surface refuses it (the control, which is D1704 as it stands).
    """
    document = {
        "run": {"id": str(RUN), "status": "cancelled", "agent_status": "revoked"},
        "steps": [],
    }
    workflows = FakeWorkflows(document=document)
    application = build(service, workflows)
    revoked_token = agent(service)

    service.repository.agent = dataclasses.replace(service.repository.agent, status="revoked")

    own = call(application, "GET", f"/workflows/runs/{RUN}", headers=revoked_token)
    assert own.status_code == 401, own.text

    served = call(
        application, "GET", f"/admin/workflows/runs/{RUN}", headers=human(service, AUDITOR)
    )
    assert served.status_code == 200, served.text
    assert served.json() == document
    assert workflows.calls == [("provenance", {"run_id": RUN})], workflows.calls


# ---------------------------------------------------------------------------
# What the database refuses, translated
# ---------------------------------------------------------------------------


def test_each_refusal_is_a_fixed_document(service: Any) -> None:
    """Three words, three documents, and nothing the database said.

    Each refusal is read from the function's message for ONE word, under the
    errcode it is raised with. A word under the wrong errcode, or an errcode
    with a message this module does not know, is re-raised rather than guessed
    into one of the three (ADR 0195) -- and a malformed run id is the same 404
    a missing run gets, before the repository is asked anything.
    """
    token = human(service, APPROVER)
    path = f"/admin/workflows/runs/{RUN}/approve"
    for sqlstate, message, status, document in (
        ("PT403", "AP403: approver_is_owner", 403, errors.APPROVER_IS_OWNER),
        ("PT409", "AP409: approval_already_decided", 409, errors.APPROVAL_ALREADY_DECIDED),
        ("PT409", "AP409: approval_expired", 409, errors.APPROVAL_EXPIRED),
        ("PT404", "AP404: no such run", 404, errors.NO_SUCH_WORKFLOW),
    ):
        raised = FakeError(sqlstate, f"{message} {ARGUMENT_VALUE}")
        application = build(service, FakeWorkflows(raises=raised))
        answered = call(application, "POST", path, json={"step": "set_the_status"}, headers=token)
        assert answered.status_code == status, (message, answered.text)
        assert answered.json() == document, message
        assert answered.headers["cache-control"] == "no-store"
        assert ARGUMENT_VALUE not in answered.text

    assert errors.APPROVER_IS_OWNER == {"error": "approver_is_owner"}
    assert errors.APPROVAL_ALREADY_DECIDED == {"error": "approval_already_decided"}
    assert errors.APPROVAL_EXPIRED == {"error": "approval_expired"}

    for sqlstate, message in (
        ("PT409", "AP409: approver_is_owner"),
        ("PT403", "AP403: approval_expired"),
        ("PT409", "AP409: something this route has no word for"),
        ("57014", "canceling statement due to statement timeout"),
    ):
        application = build(service, FakeWorkflows(raises=FakeError(sqlstate, message)))
        with pytest.raises(psycopg.Error):
            call(application, "POST", path, json={"step": "set_the_status"}, headers=token)

    workflows = FakeWorkflows()
    application = build(service, workflows)
    for bad in ("not-a-uuid", "1"):
        malformed = call(
            application,
            "POST",
            f"/admin/workflows/runs/{bad}/approve",
            json={"step": "set_the_status"},
            headers=token,
        )
        assert malformed.status_code == 404, malformed.text
        assert malformed.json() == errors.NO_SUCH_WORKFLOW
    missing = call(
        application, "GET", "/admin/workflows/runs/not-a-uuid", headers=human(service, AUDITOR)
    )
    assert missing.status_code == 404
    assert workflows.calls == [], "a malformed id reached the repository"


def test_the_decision_is_bound_to_the_named_step(service: Any) -> None:
    """The run from the path, the step from the body, and nothing else.

    The body is closed: a `run_id` or a `decided_by` member is refused rather
    than ignored, so a body can never redirect a decision to another run or
    decide it as somebody else. A step name the definition schema could not
    have produced is refused before the database is asked.
    """
    workflows = FakeWorkflows()
    application = build(service, workflows)
    token = human(service, APPROVER)
    path = f"/admin/workflows/runs/{RUN}/approve"

    for body in (
        {"step": "set_the_status", "run_id": str(uuid4())},
        {"step": "set_the_status", "decided_by": str(uuid4())},
        {},
        {"step": "Set_The_Status"},
        {"step": "set-the-status"},
        {"step": ""},
        {"step": 3},
    ):
        answered = call(application, "POST", path, json=body, headers=token)
        assert answered.status_code == 400, (body, answered.text)
        assert answered.json() == errors.MALFORMED_REQUEST
    assert workflows.calls == []

    answered = call(application, "POST", path, json={"step": "the_second_step"}, headers=token)
    assert answered.status_code == 200, answered.text
    assert answered.json()["step"] == "the_second_step"
    assert workflows.calls == [
        (
            "decide",
            {"run_id": RUN, "step": "the_second_step", "user_id": APPROVER, "decision": "approve"},
        )
    ]


# ---------------------------------------------------------------------------
# The listing, and what a response may carry
# ---------------------------------------------------------------------------


def test_approvals_list_pending_with_no_argument_values(service: Any) -> None:
    """The database's document, relayed whole, with the one bound the route owns.

    What the listing CONTAINS is the function's (D1720, `test_workflow_gates.
    py::test_pending_approvals_list_no_argument_value_oldest_first`). What the
    route adds is asserted here: the database's list under `approvals`, the
    limit applied and reported, and NO other parameter -- nothing a caller
    could use to filter by agent, owner or tool, because the listing is
    whatever waits, for whoever may decide it.
    """
    pending = [
        {
            "approval_id": str(uuid4()),
            "run_id": str(RUN),
            "definition": "tasks-approval",
            "version": 1,
            "step": "set_the_status",
            "position": 1,
            "capability": "update_task_status@1.0.0",
            "tool": "update_task_status",
            "agent_id": str(AGENT),
            "owner_id": str(uuid4()),
            "requested_at": "2026-09-28T10:00:00+00:00",
            "expires_at": "2026-09-28T10:15:00+00:00",
        }
    ]
    workflows = FakeWorkflows(approvals=pending)
    application = build(service, workflows)
    token = human(service, APPROVER)

    default = call(application, "GET", "/admin/workflows/approvals", headers=token)
    assert default.status_code == 200, default.text
    assert default.json() == {"approvals": pending, "limit": 50}
    assert default.headers["cache-control"] == "no-store"

    widest = call(application, "GET", "/admin/workflows/approvals?limit=100", headers=token)
    assert widest.json()["limit"] == 100
    assert [arguments for _, arguments in workflows.calls] == [{"limit": 50}, {"limit": 100}]

    for query in (
        "limit=0",
        "limit=101",
        "limit=abc",
        "limit=",
        "limit=1&limit=2",
        "agent_id=" + str(AGENT),
        "tool=update_task_status",
    ):
        refused = call(application, "GET", f"/admin/workflows/approvals?{query}", headers=token)
        assert refused.status_code == 422, (query, refused.text)
        assert refused.json()["error"] == "invalid_request"
    assert len(workflows.calls) == 2, "a refused query reached the repository"

    # The order the audit endpoint keeps: authenticate, scope, THEN parse. An
    # anonymous caller is not told what the listing takes.
    anonymous = call(application, "GET", "/admin/workflows/approvals?limit=0&tool=x")
    assert anonymous.status_code == 401
    for leaked in ("limit", "tool", "between"):
        assert leaked not in anonymous.text


def test_no_admin_workflow_response_carries_an_argument_value(service: Any) -> None:
    """Every body this module writes is a fixed shape.

    A refusal is `{"error": <word>}` and nothing the database said; a decision
    is `{run_id, step, approval}` and nothing the request carried beyond the
    step. The provenance document is the database's own (its content is
    `test_workflow_gates.py::test_provenance_carries_no_parameters_result_or_
    input_value`'s), relayed without a key added.
    """
    token = human(service, APPROVER)
    for sqlstate, message in (
        ("PT403", f"AP403: approver_is_owner -- {ARGUMENT_VALUE}"),
        ("PT409", f"AP409: approval_expired -- {ARGUMENT_VALUE}"),
        ("PT404", f"AP404: no such run -- {ARGUMENT_VALUE}"),
    ):
        application = build(service, FakeWorkflows(raises=FakeError(sqlstate, message)))
        for decision in ("approve", "reject"):
            answered = call(
                application,
                "POST",
                f"/admin/workflows/runs/{RUN}/{decision}",
                json={"step": "set_the_status"},
                headers=token,
            )
            assert set(answered.json()) == {"error"}, answered.text
            assert ARGUMENT_VALUE not in answered.text
            assert message not in answered.text

    application = build(service)
    decided = call(
        application,
        "POST",
        f"/admin/workflows/runs/{RUN}/approve",
        json={"step": "set_the_status"},
        headers=token,
    )
    assert set(decided.json()) == {"run_id", "step", "approval"}

    document = {"run": {"id": str(RUN), "input_keys": ["title"]}, "steps": []}
    application = build(service, FakeWorkflows(document=document))
    read = call(application, "GET", f"/admin/workflows/runs/{RUN}", headers=human(service, AUDITOR))
    assert read.json() == document

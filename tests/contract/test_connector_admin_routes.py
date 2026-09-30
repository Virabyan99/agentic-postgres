"""The three HUMAN connector routes: an access token, two scopes, fixed refusals.

`CONN-ADMIN-001` (ADR 0236). Session 33's admin-route rig
(`test_workflow_admin_routes.py`): the real `create_app("auth")` over ASGI with
the lifespan not run, and a REAL `AuthService` issuing and verifying with one
generated key over the vocabulary the example project's lock carries -- so every
token below is minted by `issue`, and a human holding `admin_connectors:read`
or `:write` exists only because `project_admin`'s ceiling, read out of that
lock, admits the new scopes at all.

The connector repository IS a fake. What the database decides -- which agent
may be bound, what a status document carries, that disable clears the
schedule -- is `test_connectivity_substrate.py`'s, under a real cluster; asked
again here it would be asked of a fake. What is asked here is which
authenticator, which scope, what is parsed and when, and which word a
refusal becomes.
"""

from __future__ import annotations

import json
import tempfile
from typing import Any
from uuid import UUID, uuid4

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
service_module = service_source.load("service")
repository_module = service_source.load("repository")
signature = service_source.load("connector_signature")

ADMIN_ROLE = "apg_fixture_alpha_dev_project_admin"
AGENT_ROLE = "apg_fixture_alpha_dev_agent_writer"

READ = "admin_connectors:read"
WRITE = "admin_connectors:write"

#: Three humans, each holding ONE administrative scope, so a refusal says which
#: scope was missing and a success says which one served.
READER = uuid4()
WRITER = uuid4()
APPROVER = uuid4()
HUMANS: dict[UUID, list[str]] = {
    READER: [READ],
    WRITER: [WRITE],
    APPROVER: ["admin_workflows:approve"],
}

AGENT = uuid4()
MASTER = "cd" * 32

#: A document shaped like `connector_status`'s, with one field this module
#: would never expect a route to add. The route adds `dead_limit` and nothing.
STATUS = {
    "connectors": [
        {
            "name": "note-embedded",
            "kind": "outbound",
            "enabled": True,
            "endpoint_declared": True,
            "binding": "not_applicable",
            "deliveries": {"pending": 1, "delivered": 4, "dead": 1},
            "last_error": "http_500",
            "dead_letters": [{"event": "note_embedding.set@1", "last_error": "http_500"}],
        }
    ]
}


class Directory:
    """Three humans and one agent, and nothing else."""

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
        issuer="https://connector-admin-routes.invalid",
        audience="connector-admin-routes",
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
    """An AGENT token, minted the way `/auth/agent-token` mints it."""
    issued = service.issue(
        service._as_credential(service.repository.agent),
        token_use="agent",  # noqa: S106
    )
    return {"Authorization": f"Bearer {issued.token}"}


class FakeConnectors:
    """The repository's three administrative calls, recording and raising as told."""

    def __init__(self, raises: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._raises = raises

    async def status(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("status", kwargs))
        if self._raises:
            raise self._raises
        return json.loads(json.dumps(STATUS))

    async def enable(self, **kwargs: Any) -> str:
        self.calls.append(("enable", kwargs))
        if self._raises:
            raise self._raises
        return "enabled"

    async def disable(self, **kwargs: Any) -> str:
        self.calls.append(("disable", kwargs))
        if self._raises:
            raise self._raises
        return "disabled"


def build(service: Any, connectors: Any = None) -> Any:
    application = main.create_app("auth")
    application.state.service = service
    application.state.connectors = connectors if connectors is not None else FakeConnectors()
    application.state.connector_key = MASTER
    return application


#: The three routes, as (method, path, body).
ROUTES = (
    ("GET", "/admin/connectors", None),
    ("POST", "/admin/connectors/notes-inbox/enable", {"agent_id": str(AGENT)}),
    ("POST", "/admin/connectors/notes-inbox/disable", None),
)


def send(application: Any, method: str, path: str, body: Any, headers: dict[str, str]) -> Any:
    extra = {"content": json.dumps(body).encode("utf-8")} if body is not None else {}
    return call(application, method, path, headers=headers, **extra)


# ---------------------------------------------------------------------------
# Mounted, and named by the document
# ---------------------------------------------------------------------------


def test_the_three_routes_are_mounted_and_named_by_the_openapi_document() -> None:
    """Three routes in `auth` mode only, published, and each documented with
    the refusals it can actually produce -- the inbound route beside them."""
    application = main.create_app("auth")
    mounted = {
        (method, route.path)
        for route in application.routes
        for method in (getattr(route, "methods", None) or ())
    }
    wanted = {
        ("GET", "/admin/connectors"),
        ("POST", "/admin/connectors/{name}/enable"),
        ("POST", "/admin/connectors/{name}/disable"),
        ("POST", "/connectors/{name}"),
    }
    assert wanted <= mounted, wanted - mounted
    for _, path in wanted:
        assert path in main.public_paths(), path

    storage = main.create_app("storage")
    assert not [r.path for r in storage.routes if "connectors" in getattr(r, "path", "")]

    document = application.openapi()
    for method, path in wanted:
        assert document["paths"][path][method.lower()]["summary"], path
    responses = {
        path: set(document["paths"][path][method.lower()]["responses"]) for method, path in wanted
    }
    assert responses["/admin/connectors"] == {"200", "401", "403", "422"}
    assert responses["/admin/connectors/{name}/enable"] == {
        "200", "400", "401", "403", "404", "409", "422",
    }  # fmt: skip
    assert responses["/admin/connectors/{name}/disable"] == {"200", "400", "401", "403", "404"}
    assert responses["/connectors/{name}"] == {"202", "400", "401", "404", "409", "413", "422"}


# ---------------------------------------------------------------------------
# Who may call them
# ---------------------------------------------------------------------------


def test_an_agent_token_is_refused_by_every_admin_connector_route(service: Any) -> None:
    """`authenticate` refuses an agent token before any scope is read -- so the
    agent a connector is bound to cannot enable, disable or read one. Each
    route requires ITS scope: read for status, write for enable and disable,
    and a human holding another administrative scope is refused all three.

    Controls in the same test: the holder of each scope is served by the
    routes that scope names, which is what makes the refusals a scope check
    rather than a broken route.
    """
    connectors = FakeConnectors()
    application = build(service, connectors)
    for method, path, body in ROUTES:
        response = send(application, method, path, body, agent(service))
        assert response.status_code == 401, (path, response.text)
        assert response.json() == {"error": "authentication_failed"}
    assert connectors.calls == [], "an agent token reached the repository"

    expected = {
        READER: {"/admin/connectors": 200},
        WRITER: {
            "/admin/connectors/notes-inbox/enable": 200,
            "/admin/connectors/notes-inbox/disable": 200,
        },
        APPROVER: {},
    }
    for user, served in expected.items():
        for method, path, body in ROUTES:
            response = send(application, method, path, body, human(service, user))
            assert response.status_code == served.get(path, 403), (user, path, response.text)
            if path not in served:
                assert response.json() == {"error": "authorization_failed"}
    assert [name for name, _ in connectors.calls] == ["status", "enable", "disable"]


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_carries_no_endpoint_payload_or_key(service: Any) -> None:
    """The database's document, whole, plus the `dead_limit` it was read with
    -- and nothing the route could add: not the master it holds, not a key
    derived from it. `dead_limit` is parsed only after the scope, strictly:
    out of range, repeated or unknown is a 422 with no repository call."""
    connectors = FakeConnectors()
    application = build(service, connectors)
    headers = human(service, READER)

    response = send(application, "GET", "/admin/connectors", None, headers)
    assert response.status_code == 200, response.text
    assert response.json() == {**STATUS, "dead_limit": 20}
    assert response.headers["cache-control"] == "no-store"

    response = send(application, "GET", "/admin/connectors?dead_limit=5", None, headers)
    assert response.json()["dead_limit"] == 5
    assert connectors.calls == [("status", {"dead_limit": 20}), ("status", {"dead_limit": 5})]

    for text in (
        MASTER,
        signature.derive(MASTER, "note-embedded"),
        signature.derive(MASTER, "notes-inbox"),
        'endpoint"',
        "payload",
    ):
        assert text not in response.text, text

    connectors.calls.clear()
    for query in ("dead_limit=0", "dead_limit=21", "dead_limit=abc", "dead_limit=1&dead_limit=2",
                  "limit=5"):  # fmt: skip
        response = send(application, "GET", f"/admin/connectors?{query}", None, headers)
        assert response.status_code == 422, (query, response.text)
    assert connectors.calls == []

    # The scope comes FIRST: an agent's bad query is the 401, not the 422.
    response = send(application, "GET", "/admin/connectors?dead_limit=0", None, agent(service))
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# enable and disable
# ---------------------------------------------------------------------------


def test_enable_binds_an_agent_with_exactly_the_definitions_scopes(service: Any) -> None:
    """The route hands the database the name, the agent the body names (or
    None) and the ADMINISTRATOR as `user_id` -- whether the agent's stored
    scopes EQUAL the definition's is `connector_enable`'s to decide, and its
    refusal is the next proof's. The body is closed: `agent_id` must be
    present (null for an outbound connector), a uuid, and alone."""
    connectors = FakeConnectors()
    application = build(service, connectors)
    headers = human(service, WRITER)

    response = send(
        application,
        "POST",
        "/admin/connectors/notes-inbox/enable",
        {"agent_id": str(AGENT)},
        headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "notes-inbox", "outcome": "enabled"}
    response = send(
        application, "POST", "/admin/connectors/note-embedded/enable", {"agent_id": None}, headers
    )
    assert response.status_code == 200, response.text
    assert connectors.calls == [
        ("enable", {"name": "notes-inbox", "agent_id": AGENT, "user_id": WRITER}),
        ("enable", {"name": "note-embedded", "agent_id": None, "user_id": WRITER}),
    ]

    connectors.calls.clear()
    for body in (
        {},
        {"agent_id": "not-a-uuid"},
        {"agent_id": str(AGENT), "scopes": ["notes:write"]},
        {"agent_id": str(AGENT), "user_id": str(uuid4())},
    ):
        response = send(application, "POST", "/admin/connectors/notes-inbox/enable", body, headers)
        assert response.status_code == 400, (body, response.text)
    assert connectors.calls == [], "a malformed body reached the repository"


def test_each_binding_refusal_is_a_fixed_document(service: Any) -> None:
    """`connector_enable`'s words, answered as themselves and nothing more --
    its DETAIL names the missing and extra scopes, and that stays in the
    database. A name the column could not hold is the 404 without a call."""
    headers = human(service, WRITER)
    detail = "missing {notes:write}; extra {tasks:write} xyzzy"
    for raised, status, word in (
        (FakeError("PT404", "AP404: no_such_connector"), 404, "no_such_connector"),
        (FakeError("PT409", "AP409: agent_not_active"), 409, "agent_not_active"),
        (FakeError("PT409", "AP409: agent_already_bound"), 409, "agent_already_bound"),
        (FakeError("PT409", f"AP409: agent_scopes_differ {detail}"), 409, "agent_scopes_differ"),
        (FakeError("PT409", "AP409: no_endpoint"), 409, "no_endpoint"),
        (FakeError("PT422", "AP422: agent_not_needed"), 422, "agent_not_needed"),
    ):
        application = build(service, FakeConnectors(raises=raised))
        response = send(
            application,
            "POST",
            "/admin/connectors/notes-inbox/enable",
            {"agent_id": str(AGENT)},
            headers,
        )
        assert response.status_code == status, (word, response.text)
        assert response.json() == {"error": word}
        assert "xyzzy" not in response.text and "tasks:write" not in response.text

    connectors = FakeConnectors()
    application = build(service, connectors)
    for bad in ("Notes", "notes_inbox", "x" * 64):
        response = send(
            application, "POST", f"/admin/connectors/{bad}/enable", {"agent_id": None}, headers
        )
        assert response.status_code == 404, bad
        assert response.json() == {"error": "no_such_connector"}
    assert connectors.calls == []

    # An error the route does not recognise is NOT reported as a refusal.
    application = build(service, FakeConnectors(raises=FakeError("XX000", "internal")))
    with pytest.raises(FakeError):
        send(
            application,
            "POST",
            "/admin/connectors/notes-inbox/enable",
            {"agent_id": None},
            headers,
        )


def test_disable_clears_the_schedule(service: Any) -> None:
    """Disable takes NO body and names its administrator; clearing the
    schedule and holding the deliveries is `connector_disable`'s (the
    substrate's proof). A body is refused rather than ignored: a caller that
    sent one believes it said something."""
    connectors = FakeConnectors()
    application = build(service, connectors)
    headers = human(service, WRITER)

    response = send(application, "POST", "/admin/connectors/notes-digest/disable", None, headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "notes-digest", "outcome": "disabled"}
    assert connectors.calls == [("disable", {"name": "notes-digest", "user_id": WRITER})]

    connectors.calls.clear()
    response = send(
        application, "POST", "/admin/connectors/notes-digest/disable", {"agent_id": None}, headers
    )
    assert response.status_code == 400, response.text
    assert connectors.calls == []

    missing = build(service, FakeConnectors(raises=FakeError("PT404", "AP404: no_such_connector")))
    response = send(missing, "POST", "/admin/connectors/notes-digest/disable", None, headers)
    assert response.status_code == 404
    assert response.json() == {"error": "no_such_connector"}

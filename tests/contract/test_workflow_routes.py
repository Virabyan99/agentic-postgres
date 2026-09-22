"""The three routes: a second authenticator, and every authority the database's.

**Driven over ASGI against the real `create_app("auth")`, with the LIFESPAN not
run.** What is under test here is the route layer -- which authenticator each
route calls, how a substrate errcode becomes a status, and what an error body
may carry -- and none of that is a question about a cluster. The substrate's
own behaviour is `test_workflow_substrate.py`'s, under a real cluster as
`migration_user`; running one here would prove the same thing twice and make
this module skip without docker.

So `app.state.service` and `app.state.workflows` are set directly, which is
exactly what the lifespan sets them to. The trade is stated rather than hidden:
a defect in how the lifespan ASSEMBLES them is invisible here and is
`test_workflow_worker.py::test_the_loop_starts_in_auth_mode_only`'s to catch.

**The load-bearing proofs are the refusals**: an access token refused here, an
agent token still refused by `authenticate`, another agent's run answered with
the same 404 a missing one gets, and no error body carrying an argument, a
result or a definition name.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agentic_postgres import service_source

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

main = service_source.load("main")
errors = service_source.load("errors")
service_module = service_source.load("service")

AGENT = uuid4()
OTHER_RUN = uuid4()


class FakeError(psycopg.Error):
    """A `psycopg.Error` whose `diag.sqlstate` is what the substrate raised."""

    def __init__(self, sqlstate: str, message: str) -> None:
        super().__init__(message)
        self._sqlstate = sqlstate

    @property
    def diag(self) -> Any:  # type: ignore[override]
        return type("Diag", (), {"sqlstate": self._sqlstate})()


class FakeWorkflows:
    """The repository, recording calls and raising what it is told to."""

    def __init__(self, raises: Exception | None = None, document: Any = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._raises = raises
        self._document = document

    async def enqueue(self, **kwargs: Any) -> UUID:
        self.calls.append(("enqueue", kwargs))
        if self._raises:
            raise self._raises
        return uuid4()

    async def status(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("status", kwargs))
        if self._raises:
            raise self._raises
        return self._document or {"run_id": "x", "status": "succeeded", "steps": []}

    async def cancel(self, **kwargs: Any) -> str:
        self.calls.append(("cancel", kwargs))
        if self._raises:
            raise self._raises
        return "cancelled"


class FakeService:
    """Only what the three routes reach: one authenticator."""

    def __init__(self, principal: Any = None, refuse: Exception | None = None) -> None:
        self.seen: list[str | None] = []
        self._principal = principal
        self._refuse = refuse

    async def authenticate_agent(self, authorization: str | None) -> Any:
        self.seen.append(authorization)
        if self._refuse is not None:
            raise self._refuse
        return self._principal or service_module.AgentPrincipal(
            agent_id=AGENT, role_name="agent_writer", scopes=["notes:write"], authz_version=1
        )


def build(workflows: Any = None, service: Any = None) -> Any:
    application = main.create_app("auth")
    application.state.service = service or FakeService()
    application.state.workflows = workflows or FakeWorkflows()
    return application


def call(application: Any, method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://auth.invalid") as http:
            return await http.request(method, path, **kwargs)

    return asyncio.run(run())


AUTHORIZED = {"Authorization": "Bearer an.agent.token"}


# ---------------------------------------------------------------------------
# Mounted, and named by the document
# ---------------------------------------------------------------------------


def test_the_three_routes_are_mounted_in_auth_mode_and_named_by_the_openapi_document() -> None:
    """Three routes, in `auth` mode only, and every one of them published.

    A route the document does not name is a surface nobody reviewed (ADR 0050),
    and the document is the one `bin/app-contract.sh --check` compares against
    the committed snapshot.
    """
    application = main.create_app("auth")
    paths = {route.path for route in application.routes}
    wanted = {
        "/workflows/runs",
        "/workflows/runs/{run_id}",
        "/workflows/runs/{run_id}/cancel",
    }
    assert wanted <= paths

    storage = main.create_app("storage")
    assert not {path for path in {r.path for r in storage.routes} if path.startswith("/workflows")}

    document = application.openapi()
    assert set(document["paths"]) >= wanted
    assert document["paths"]["/workflows/runs"]["post"]["summary"]
    assert "201" in document["paths"]["/workflows/runs"]["post"]["responses"]
    assert "403" in document["paths"]["/workflows/runs"]["post"]["responses"]
    assert "404" in document["paths"]["/workflows/runs"]["post"]["responses"]


# ---------------------------------------------------------------------------
# The authenticator
# ---------------------------------------------------------------------------


def test_the_routes_call_authenticate_agent_and_not_authenticate() -> None:
    """The substitution ADR 0229 makes, read at the call site.

    A fake service that implements ONLY `authenticate_agent` is what proves it:
    a route calling `authenticate` would raise `AttributeError` and answer 500,
    not 201.
    """
    service = FakeService()
    application = build(service=service)
    answered = call(
        application, "POST", "/workflows/runs", json={"name": "notes-roundtrip"}, headers=AUTHORIZED
    )
    assert answered.status_code == 201, answered.text
    assert service.seen == ["Bearer an.agent.token"]


def test_a_refused_token_is_a_401_with_no_reason(caplog: Any) -> None:
    """Every authentication outcome is one 401 with one body (ADR 0097).

    An access token, a revoked agent and a stale `authz_version` are three
    different facts and one answer -- which is what keeps a token from being an
    oracle about the agent behind it.
    """
    for reason in (
        "token_use 'access' is not accepted by this API",
        "the subject is revoked",
        "authz_version is stale",
    ):
        application = build(
            service=FakeService(refuse=errors.AuthenticationFailed(reason)),
        )
        answered = call(
            application, "POST", "/workflows/runs", json={"name": "x"}, headers=AUTHORIZED
        )
        assert answered.status_code == 401
        assert answered.json() == {"error": "authentication_failed"}
        assert reason not in answered.text


def _signing_key() -> Any:
    """A real RSA key on disk, `test_verifier_key_sets.py:45-56`'s shape."""
    keys = service_source.load("keys")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    handle = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
    handle.write(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    handle.close()
    return keys.load_signing_key(Path(handle.name))


class OneAgentRepository:
    """Only what the two authenticators reach."""

    def __init__(self, credential: Any, state: Any = None) -> None:
        self._credential = credential
        self._state = state

    async def lookup_agent(self, agent_id: UUID) -> Any:
        return (
            self._credential if self._credential and agent_id == self._credential.agent_id else None
        )

    async def state(self, user_id: UUID) -> Any:
        return self._state


class NoHasher:
    async def verify(self, stored: Any, secret: str) -> bool:  # pragma: no cover -- unused here
        return False


@pytest.fixture(scope="module")
def real_service() -> Any:
    """A REAL `AuthService`, issuing and verifying with one generated key.

    Built because the battery's m4 -- `authenticate_agent` widened to accept an
    access token as well -- SURVIVED a proof that only read the two constants
    and the source. A constant comparison is not the check; the check is the
    comparison inside the function, and only a token driven through it can see
    that.
    """
    repository_module = service_source.load("repository")
    tokens = service_source.load("tokens")
    scope_map = service_source.load("scopes")

    private = _signing_key()
    credential = repository_module.AgentCredential(
        agent_id=AGENT,
        role_name="apg_fixture_alpha_dev_agent_writer",
        scopes=["notes:write"],
        status="active",
        authz_version=1,
        # A syntactically valid Argon2 encoding that verifies nothing: this
        # module never compares a secret, and the column's CHECK refuses a
        # value that is not shaped like one. (S106 matches on the name.)
        secret_hash="$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA",  # noqa: S106
        secret_expired=False,
    )
    lock = tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False)
    lock.write(json.dumps(_lock_document()))
    lock.close()

    return service_module.AuthService(
        repository=OneAgentRepository(credential),
        hasher=NoHasher(),
        signing_key=private,
        key_set=tokens.LocalKeySet.load(json.dumps(private.jwks()).encode("utf-8")),
        issuer="https://workflow-routes.invalid",
        audience="workflow-routes",
        role_suffixes={"apg_fixture_alpha_dev_agent_writer": "agent_writer"},
        vocabulary=scope_map.load_vocabulary(lock.name),
    )


def _lock_document() -> dict[str, Any]:
    """The example project's lock, through the product's own chain."""
    from agentic_postgres import (
        REPO_ROOT,
        capability_compiler,
        capability_manifest,
        config,
        naming,
        scope_registry,
    )
    from agentic_postgres import (
        workflow_definition as view_source,
    )

    manifest = config.load_project_manifest(REPO_ROOT / "project.example.yaml")
    inputs = capability_manifest.project_inputs(manifest)
    capabilities = config.load_capabilities_manifest(view_source.DEFAULT_CAPABILITIES)
    canonical = capability_manifest.compile_joint_contract(capabilities, inputs)
    return capability_compiler.compile_lock(
        canonical=canonical,
        project_key=naming.project_key(
            manifest["project"]["slug"], manifest["project"]["environment"]
        ),
        upstream=view_source.UNDEPLOYED_UPSTREAM,
        sources={
            "capabilities_sha256": "0" * 64,
            "api_surface_sha256": "0" * 64,
            "canonical_openapi_sha256": "0" * 64,
            "project_manifest_sha256": "0" * 64,
        },
        profile=manifest["mcp"]["profile"],
        vocabulary=scope_registry.vocabulary_block(inputs.surface),
    )


def test_authenticate_agent_accepts_an_agent_token_and_refuses_an_access_token(
    real_service: Any,
) -> None:
    """**Driven through the real function, with real tokens.**

    The battery is why: m4 widened the comparison to accept `access` as well,
    and a proof reading the two constants could not see it. What can see it is
    a token minted with `token_use="access"` for the same subject, with the
    same signature, reaching the same function and being refused.
    """
    agent_token = real_service.issue(
        _credential_for(real_service),
        token_use="agent",  # noqa: S106
    )
    accepted = asyncio.run(real_service.authenticate_agent(f"Bearer {agent_token.token}"))
    assert accepted.agent_id == AGENT
    assert accepted.scopes == ["notes:write"]

    access_token = real_service.issue(
        _credential_for(real_service),
        token_use="access",  # noqa: S106
    )
    with pytest.raises(errors.AuthenticationFailed, match="token_use"):
        asyncio.run(real_service.authenticate_agent(f"Bearer {access_token.token}"))


def _credential_for(service: Any) -> Any:
    return service._as_credential(service.repository._credential)


def test_authenticate_still_refuses_an_agent_token(real_service: Any) -> None:
    """**The control in the other direction**, and the reason ADR 0114 is
    amended rather than loosened.

    The same agent token, through `authenticate`, is refused -- so the two
    surfaces are disjoint by the claim a token carries and not by which handler
    happened to be mounted. A single constant, or a set containing both, would
    have made every human route reachable with an agent token.
    """
    assert service_module.ACCEPTED_TOKEN_USE == "access"  # noqa: S105
    assert service_module.AGENT_TOKEN_USE == "agent"  # noqa: S105
    assert service_module.ACCEPTED_TOKEN_USE != service_module.AGENT_TOKEN_USE

    agent_token = real_service.issue(
        _credential_for(real_service),
        token_use="agent",  # noqa: S106
    )
    with pytest.raises(errors.AuthenticationFailed, match="token_use"):
        asyncio.run(real_service.authenticate(f"Bearer {agent_token.token}"))


def test_a_revoked_or_reauthorized_agent_is_refused_at_the_route(real_service: Any) -> None:
    """SEC-REV-001's mechanism, applied to the surface ADR 0114 left without one.

    The token is minted while the agent is current and the RECORD is changed
    under it; the next call is refused. Three ways -- revoked, reauthorised,
    and gone -- and each one answers on the call after the change rather than
    at the next expiry.
    """
    import dataclasses

    token = real_service.issue(
        _credential_for(real_service),
        token_use="agent",  # noqa: S106
    )
    current = real_service.repository._credential

    for mutation, marker in (
        ({"status": "revoked"}, "revoked"),
        ({"authz_version": 2}, "authz_version is stale"),
        ({"scopes": ["notes:read"]}, "the scopes have changed"),
    ):
        real_service.repository._credential = dataclasses.replace(current, **mutation)
        with pytest.raises(errors.AuthenticationFailed, match=marker):
            asyncio.run(real_service.authenticate_agent(f"Bearer {token.token}"))

    real_service.repository._credential = None
    with pytest.raises(errors.AuthenticationFailed, match="no longer exists"):
        asyncio.run(real_service.authenticate_agent(f"Bearer {token.token}"))

    real_service.repository._credential = current
    assert asyncio.run(real_service.authenticate_agent(f"Bearer {token.token}")).agent_id == AGENT


# ---------------------------------------------------------------------------
# The substrate's refusals, translated
# ---------------------------------------------------------------------------


def test_a_definition_nobody_installed_is_one_404() -> None:
    application = build(
        workflows=FakeWorkflows(raises=FakeError("PT404", "AP404: no such definition"))
    )
    answered = call(
        application, "POST", "/workflows/runs", json={"name": "absent"}, headers=AUTHORIZED
    )
    assert answered.status_code == 404
    assert answered.json() == {"error": "no_such_workflow"}
    assert answered.headers["cache-control"] == "no-store"


def test_scope_not_held_is_a_403_carrying_the_substrates_own_word() -> None:
    """One of `mcp_errors.DENIAL_REASONS`' nine boundaries, not a tenth word.

    The check is the DATABASE's, against the agent's stored scopes -- so an
    agent narrowed since its token was minted is refused here even though the
    token it presented still carries the wider set.
    """
    application = build(workflows=FakeWorkflows(raises=FakeError("PT403", "AP403: scope_not_held")))
    answered = call(application, "POST", "/workflows/runs", json={"name": "x"}, headers=AUTHORIZED)
    assert answered.status_code == 403
    assert answered.json() == {"error": "scope_not_held"}


def test_a_revoked_agent_reaching_enqueue_is_a_401_and_not_a_403() -> None:
    """`PT403` from the substrate has two causes and they answer differently.

    An agent revoked between `authenticate_agent` and the insert is an
    authentication outcome -- the record stopped being current -- and a 403
    would claim an authentication that no longer holds.
    """
    application = build(
        workflows=FakeWorkflows(
            raises=FakeError("PT403", "AP403: this operation requires an active agent identity")
        )
    )
    answered = call(application, "POST", "/workflows/runs", json={"name": "x"}, headers=AUTHORIZED)
    assert answered.status_code == 401
    assert answered.json() == {"error": "authentication_failed"}


def test_an_unrecognised_database_error_is_not_reported_as_a_404() -> None:
    """**Translated, never relayed, and never guessed** (D433, ADR 0195).

    A sqlstate this route does not know is re-raised, so it reaches the
    application's own handler. Reporting it as a 404 about the agent's own run
    would be a reader folding an unknown into an answer.
    """
    application = build(workflows=FakeWorkflows(raises=FakeError("57014", "canceling statement")))
    with pytest.raises(psycopg.Error):
        call(application, "POST", "/workflows/runs", json={"name": "x"}, headers=AUTHORIZED)


# ---------------------------------------------------------------------------
# Ownership, and what a body may carry
# ---------------------------------------------------------------------------


def test_status_and_cancel_pass_the_tokens_agent_and_nothing_a_caller_chose() -> None:
    """The agent id comes from the PRINCIPAL, never from the path or the body.

    That is what makes ownership unbypassable by this code: there is no
    argument a caller could supply to read another agent's run, because the
    only agent id that reaches the substrate is the one the token verified.
    """
    workflows = FakeWorkflows()
    application = build(workflows=workflows)
    run_id = uuid4()

    assert (
        call(application, "GET", f"/workflows/runs/{run_id}", headers=AUTHORIZED).status_code == 200
    )
    assert (
        call(
            application, "POST", f"/workflows/runs/{run_id}/cancel", headers=AUTHORIZED
        ).status_code
        == 200
    )

    for name, arguments in workflows.calls:
        assert arguments["agent_id"] == AGENT, name
        assert arguments["run_id"] == run_id, name


def test_another_agents_run_and_a_missing_one_are_the_same_404() -> None:
    """A run id must not be an ownership oracle (ADR 0229).

    Both come out of the substrate as `PT404` for exactly this reason, and a
    malformed id is the same answer: a 400 would tell a caller that a
    well-formed id it cannot read is well formed.
    """
    application = build(workflows=FakeWorkflows(raises=FakeError("PT404", "AP404: no such run")))
    for path in (f"/workflows/runs/{OTHER_RUN}", f"/workflows/runs/{OTHER_RUN}/cancel"):
        method = "POST" if path.endswith("cancel") else "GET"
        answered = call(application, method, path, headers=AUTHORIZED)
        assert answered.status_code == 404
        assert answered.json() == {"error": "no_such_workflow"}

    malformed = call(build(), "GET", "/workflows/runs/not-a-uuid", headers=AUTHORIZED)
    assert malformed.status_code == 404
    assert malformed.json() == {"error": "no_such_workflow"}


def test_no_error_body_carries_an_argument_or_a_result_value() -> None:
    """Every refusal is a fixed document (ADR 0141's rule, applied to a run).

    The definition's name, the run id and the substrate's own message are all
    absent from every error body -- so a 404 cannot be used to discover which
    definitions a deployment installed.
    """
    secret_name = "a-definition-nobody-may-learn-about"  # noqa: S105
    for sqlstate, status in (("PT404", 404), ("PT403", 403)):
        message = "AP403: scope_not_held" if sqlstate == "PT403" else "AP404: no such definition"
        application = build(workflows=FakeWorkflows(raises=FakeError(sqlstate, message)))
        answered = call(
            application,
            "POST",
            "/workflows/runs",
            json={"name": secret_name, "input": {"a_caller_value": "xyzzy"}},
            headers=AUTHORIZED,
        )
        assert answered.status_code == status
        body = answered.text
        assert secret_name not in body
        assert "xyzzy" not in body
        assert message not in body
        assert set(json.loads(body)) == {"error"}


def test_the_request_body_is_closed_and_a_run_cannot_describe_its_own_work() -> None:
    """`extra="forbid"`, and there is no `steps` field to forbid it in.

    A body that could describe the work would be a body that could describe
    work nobody reviewed -- which is the whole reason a definition is installed
    by a deploy rather than submitted with a run.
    """
    application = build()
    refused = call(
        application,
        "POST",
        "/workflows/runs",
        json={"name": "x", "steps": [{"capability": "create_note@1.0.0"}]},
        headers=AUTHORIZED,
    )
    assert refused.status_code == 400
    assert refused.json() == {"error": "malformed_request"}

    models = service_source.load("models")
    assert set(models.WorkflowRunRequest.model_fields) == {"name", "version", "input", "dry_run"}


def test_a_dry_run_reaches_the_substrate_as_a_flag_on_the_same_call() -> None:
    """One route, one handler, one audit shape. `dry_run` is a field."""
    workflows = FakeWorkflows()
    application = build(workflows=workflows)
    call(
        application,
        "POST",
        "/workflows/runs",
        json={"name": "notes-roundtrip", "version": 2, "dry_run": True, "input": {"a": 1}},
        headers=AUTHORIZED,
    )
    enqueued = workflows.calls[0][1]
    assert enqueued["dry_run"] is True
    assert enqueued["version"] == 2
    assert enqueued["name"] == "notes-roundtrip"
    assert json.loads(enqueued["run_input"]) == {"a": 1}
    assert enqueued["agent_id"] == AGENT


def test_every_answer_is_no_store() -> None:
    """A cached run document is a run document read after the run moved.

    And a cached 404 is worse: it could answer one agent with the absence
    another agent's run produced.
    """
    application = build()
    for method, path, body in (
        ("POST", "/workflows/runs", {"name": "x"}),
        ("GET", f"/workflows/runs/{uuid4()}", None),
        ("POST", f"/workflows/runs/{uuid4()}/cancel", None),
    ):
        answered = call(
            application, method, path, headers=AUTHORIZED, **({"json": body} if body else {})
        )
        assert answered.headers["cache-control"] == "no-store", path

"""`POST /connectors/{name}`: the signature before anything else (ADR 0237).

`CONN-IN-001`. Driven over ASGI against the real `create_app("auth")` with the
lifespan not run -- `test_workflow_routes.py`'s rig and its stated trade:
`app.state.connectors` and `app.state.connector_key` are set directly, which is
what the lifespan sets them to.

**The load-bearing proof is the ORDER.** Every request that fails its signature
is driven against a repository that RAISES on any call (`Untouchable`), so a
route that read the declaration, or parsed the body into a database call,
before the signature held would answer 500 and record the call -- the proof
cannot pass vacuously. The control is the same route with a good signature
against a recording repository, which makes exactly the two calls expected.

Every signature below is computed by THIS module's own HMAC over the bytes
sent, never by the service's `sign`, so a changed label or byte order in the
service cannot be matched by the proof sharing it (CLAUDE.md §7, question 6).
The key is derived by the service's `derive`, which
`test_connector_facility.py` holds against an independent HMAC.

What the database decides -- which connector is enabled, whether a delivery id
was accepted, whether the bound agent's scopes equal the definition's -- is
`test_connectivity_substrate.py`'s, under a real cluster.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from uuid import UUID, uuid4

import pytest
from tests.contract.test_workflow_routes import FakeError, call

from agentic_postgres import service_source

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

main = service_source.load("main")
signature = service_source.load("connector_signature")
strict_json = service_source.load("strict_json")

MASTER = hashlib.sha256(b"session-34-run-7-master").hexdigest()
OTHER_MASTER = hashlib.sha256(b"another-projects-master").hexdigest()
NAME = "notes-inbox"
RUN_ID = uuid4()

DECLARATION = {
    "members": {
        "content": {"type": "string", "required": True, "max_length": 4000},
        "title": {"type": "string", "required": True, "max_length": 200},
    }
}
GOOD_BODY = {"title": "a signed title", "content": "a signed content"}


def _hmac(key_hex: str, t: int, delivery: str, body: bytes) -> str:
    """This module's own HMAC over `<t>.<delivery>.<body>` (ADR 0237)."""
    return hmac.new(
        bytes.fromhex(key_hex), f"{t}.{delivery}.".encode("ascii") + body, hashlib.sha256
    ).hexdigest()


def signed(
    body: bytes,
    *,
    name: str = NAME,
    master: str = MASTER,
    delivery: str | None = None,
    t: int | None = None,
    signed_delivery: str | None = None,
    signed_body: bytes | None = None,
) -> dict[str, str]:
    """Headers for one delivery. Every knob is one way to be wrong."""
    delivery = delivery if delivery is not None else str(uuid4())
    t = t if t is not None else int(time.time())
    digest = _hmac(
        signature.derive(master, name),
        t,
        signed_delivery if signed_delivery is not None else delivery,
        signed_body if signed_body is not None else body,
    )
    return {
        "X-Apg-Delivery": delivery,
        "X-Apg-Signature": f"t={t},v1={digest}",
        "Content-Type": "application/json",
    }


def encode(document: Any) -> bytes:
    return json.dumps(document).encode("utf-8")


class Untouchable:
    """A repository that raises on ANY call and remembers that it was made."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        async def refuse(**kwargs: Any) -> Any:
            self.calls.append(name)
            raise AssertionError(f"the route called the repository ({name}) too early")

        return refuse


class Recording:
    """The two calls the route makes, recording and answering as told."""

    def __init__(
        self,
        *,
        declaration: dict[str, Any] | None = None,
        inbound_raises: Exception | None = None,
        accept_raises: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._declaration = declaration if declaration is not None else DECLARATION
        self._inbound_raises = inbound_raises
        self._accept_raises = accept_raises

    async def inbound(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("inbound", kwargs))
        if self._inbound_raises:
            raise self._inbound_raises
        return {"connector_id": str(uuid4()), "body_declaration": self._declaration}

    async def accept(self, **kwargs: Any) -> UUID:
        self.calls.append(("accept", kwargs))
        if self._accept_raises:
            raise self._accept_raises
        return RUN_ID


def build(connectors: Any, key: str | None = MASTER) -> Any:
    application = main.create_app("auth")
    application.state.connectors = connectors
    application.state.connector_key = key
    return application


def post(application: Any, body: bytes, headers: dict[str, str], name: str = NAME) -> Any:
    return call(application, "POST", f"/connectors/{name}", content=body, headers=headers)


def _bad_signatures() -> dict[str, tuple[bytes, dict[str, str]]]:
    """Twelve ways a request fails its signature: eleven on the good body, and
    one whose body is not even JSON -- which only the ORDER keeps a 401."""
    body = encode(GOOD_BODY)
    now = int(time.time())
    delivery = str(uuid4())
    good = signed(body, delivery=delivery)
    return {
        "no_signature_header": (body, {k: v for k, v in good.items() if k != "X-Apg-Signature"}),
        "no_delivery_header": (body, {k: v for k, v in good.items() if k != "X-Apg-Delivery"}),
        "malformed_signature": (body, {**good, "X-Apg-Signature": "v1=deadbeef"}),
        "delivery_not_a_uuid": (body, signed(body, delivery="not-a-uuid")),
        "delivery_not_canonical": (body, signed(body, delivery=delivery.upper())),
        "stale": (body, signed(body, t=now - signature.TIMESTAMP_TOLERANCE_SECONDS - 5)),
        "from_the_future": (body, signed(body, t=now + signature.TIMESTAMP_TOLERANCE_SECONDS + 5)),
        "wrong_key": (body, signed(body, master=OTHER_MASTER)),
        "another_connectors_key": (body, signed(body, name="note-embedded")),
        "wrong_delivery_id": (body, signed(body, signed_delivery=str(uuid4()))),
        "changed_body": (body, signed(body, signed_body=encode({**GOOD_BODY, "title": "x"}))),
        # Not JSON, and not signed: a route that parsed before it verified
        # would answer this 400 and tell a prober its body was read.
        "unsigned_non_json": (b"not json", signed(b"not json", master=OTHER_MASTER)),
    }


# ---------------------------------------------------------------------------
# Before the signature
# ---------------------------------------------------------------------------


def test_a_bad_name_or_no_key_is_not_found() -> None:
    """(1) and (2): a name the column could not hold, and a deployment without
    the facility, are the one 404 -- and neither reaches the repository.

    The no-key arm carries a signature that WOULD verify under the master, so
    a route that checked the signature first and the key second could not
    answer 404 for it by accident.
    """
    body = encode(GOOD_BODY)
    for bad in ("Notes-Inbox", "notes_inbox", "-notes", "9notes", "x" * 64):
        repository = Untouchable()
        response = post(build(repository), body, signed(body), name=bad)
        assert response.status_code == 404, (bad, response.text)
        assert response.json() == {"error": "no_such_connector"}
        assert repository.calls == [], bad

    repository = Untouchable()
    response = post(build(repository, key=None), body, signed(body))
    assert response.status_code == 404, response.text
    assert response.json() == {"error": "no_such_connector"}
    assert repository.calls == []

    storage = main.create_app("storage")
    assert not [r.path for r in storage.routes if "connectors" in getattr(r, "path", "")]


def test_an_oversized_body_is_refused() -> None:
    """(3): above 16 KiB is 413 before an HMAC is computed; at 16 KiB exactly
    the bound is not what refuses it (the control: a 400 for not being JSON)."""
    limit = strict_json.MAX_BODY_BYTES
    over = b"x" * (limit + 1)
    repository = Untouchable()
    response = post(build(repository), over, signed(over))
    assert response.status_code == 413, response.text
    assert response.json() == {"error": "body_too_large"}
    assert repository.calls == []

    at = b"x" * limit
    response = post(build(Untouchable()), at, signed(at))
    assert response.status_code == 400, response.text


def test_every_signature_failure_is_one_fixed_document() -> None:
    """(4): twelve causes, ONE answer -- status, body and headers identical.

    A prober that could tell a stale timestamp from a wrong key would know it
    had the key; one that could tell a wrong delivery id from a changed body
    would know which half it had captured.
    """
    answers = set()
    for cause, (body, headers) in _bad_signatures().items():
        response = post(build(Untouchable()), body, headers)
        assert response.status_code == 401, (cause, response.text)
        answers.add(
            (
                response.status_code,
                response.content,
                response.headers.get("www-authenticate"),
                response.headers.get("cache-control"),
            )
        )
    assert answers == {(401, b'{"error":"signature_invalid"}', "APG-Signature", "no-store")}, (
        answers
    )


def test_no_database_call_precedes_the_signature() -> None:
    """(4) before (6), against a repository that raises on any call.

    Control, in the same test: a good signature against a RECORDING repository
    makes exactly `inbound` then `accept` -- so the no-call arms fail if the
    route ever consults the repository first, and the control fails if the
    route stops reaching it at all.
    """
    for cause, (body, headers) in _bad_signatures().items():
        repository = Untouchable()
        response = post(build(repository), body, headers)
        assert response.status_code == 401, (cause, response.text)
        assert repository.calls == [], (cause, repository.calls)

    body = encode(GOOD_BODY)
    recording = Recording()
    response = post(build(recording), body, signed(body))
    assert response.status_code == 202, response.text
    assert [name for name, _ in recording.calls] == ["inbound", "accept"]


# ---------------------------------------------------------------------------
# After the signature
# ---------------------------------------------------------------------------


def test_a_signed_non_object_is_malformed() -> None:
    """(5): parsed only once signed, and parsed strictly -- still before the
    database. A non-object root and a duplicate member are the house's 400."""
    for raw in (b"[1, 2]", b'"a string"', b"12", b"not json", b'{"title": "a", "title": "b"}'):
        repository = Untouchable()
        response = post(build(repository), raw, signed(raw))
        assert response.status_code == 400, (raw, response.text)
        assert response.json() == {"error": "malformed_request"}
        assert repository.calls == [], raw


def test_a_body_outside_the_declaration_names_the_member() -> None:
    """(6): the declaration is read, the body checked against it, and a refusal
    names a DECLARED member and a fixed reason -- never a value, never an
    undeclared member's name (the sender's own text). Nothing is accepted."""
    cases = {
        "missing": ({"title": "a"}, {"reason": "missing", "member": "content"}),
        "type": ({"title": 7, "content": "c"}, {"reason": "type", "member": "title"}),
        "too_long": (
            {"title": "t" * 201, "content": "c"},
            {"reason": "too_long", "member": "title"},
        ),
        "unexpected": (
            {**GOOD_BODY, "evil_member_name": "evil-value"},
            {"reason": "unexpected_member", "member": None},
        ),
    }
    for case, (document, expected) in cases.items():
        body = encode(document)
        recording = Recording()
        response = post(build(recording), body, signed(body))
        assert response.status_code == 422, (case, response.text)
        assert response.json() == {"error": "body_not_permitted", **expected}, case
        assert "evil" not in response.text, case
        assert [name for name, _ in recording.calls] == ["inbound"], case


def test_a_replayed_delivery_is_refused() -> None:
    """`connector_accept`'s `delivery_replayed`, answered as itself: a retry of
    an accepted delivery id starts nothing. The database's message is read for
    one word; what else it says is never relayed."""
    body = encode(GOOD_BODY)
    recording = Recording(
        accept_raises=FakeError("PT409", "AP409: delivery_replayed -- xyzzy-internal")
    )
    response = post(build(recording), body, signed(body))
    assert response.status_code == 409, response.text
    assert response.json() == {"error": "delivery_replayed"}
    assert "xyzzy" not in response.text


def test_a_disabled_connector_refuses_after_the_signature() -> None:
    """Disabled is the DATABASE's answer, reached only by a signed request: an
    unsigned one to the same disabled connector is the 401 and learns nothing
    about whether it is enabled."""
    body = encode(GOOD_BODY)
    disabled = FakeError("PT409", "AP409: connector_disabled")
    response = post(build(Recording(accept_raises=disabled)), body, signed(body))
    assert response.status_code == 409, response.text
    assert response.json() == {"error": "connector_disabled"}

    unsigned = Recording(accept_raises=disabled)
    response = post(build(unsigned), body, signed(body, master=OTHER_MASTER))
    assert response.status_code == 401
    assert unsigned.calls == []

    for sqlstate, message in (("PT404", "AP404: no_such_connector"),):
        response = post(
            build(Recording(inbound_raises=FakeError(sqlstate, message))), body, signed(body)
        )
        assert response.status_code == 404
        assert response.json() == {"error": "no_such_connector"}


def test_a_widened_agent_is_refused() -> None:
    """A bound agent whose stored scopes stopped EQUALLING the definition's --
    widened, narrowed, or revoked -- starts nothing, and the sender is told the
    status document's word for it. `workflow_enqueue`'s own two PT403 refusals
    map onto the same words."""
    body = encode(GOOD_BODY)
    for raised, word in (
        (FakeError("PT409", "AP409: agent_scopes_differ"), "agent_scopes_differ"),
        (FakeError("PT403", "AP403: scope_not_held"), "agent_scopes_differ"),
        (
            FakeError("PT403", "AP403: this operation requires an active agent identity"),
            "agent_not_active",
        ),
    ):
        response = post(build(Recording(accept_raises=raised)), body, signed(body))
        assert response.status_code == 409, (word, response.text)
        assert response.json() == {"error": word}


def test_a_signed_request_enqueues_a_run_as_the_bound_agent(caplog: Any) -> None:
    """The one success: 202, the run's id, `no-store` -- and the repository is
    handed the name, the delivery id and the PARSED body, and nothing naming an
    agent: the run starts as whichever agent the database has bound.

    The one log line is `StructuredRequestLog`'s route TEMPLATE; no line
    carries the connector's name, the delivery id, the signature or a value.
    """
    caplog.set_level(logging.INFO)
    body = encode(GOOD_BODY)
    delivery = str(uuid4())
    headers = signed(body, delivery=delivery)
    recording = Recording()
    response = post(build(recording), body, headers)
    assert response.status_code == 202, response.text
    assert response.json() == {"run_id": str(RUN_ID), "status": "queued"}
    assert response.headers["cache-control"] == "no-store"

    assert recording.calls == [
        ("inbound", {"name": NAME}),
        ("accept", {"name": NAME, "delivery_id": UUID(delivery), "body": GOOD_BODY}),
    ]

    # The SERVICE's loggers only: the test client's own `httpx` logs the URL it
    # was asked to send, which is this module's line and not the service's.
    logged = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name.startswith(("apg", "app", "uvicorn"))
    )
    assert "/connectors/{name}" in logged, "the request log line is missing"
    for value in (NAME, delivery, headers["X-Apg-Signature"], "a signed title", MASTER):
        assert value not in logged, value

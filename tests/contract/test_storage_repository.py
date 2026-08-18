"""What `StorageRepository` sends, and that the owner reaches every call.

**This module exists because a mutation battery found the layer untested.**
`tests/contract/test_storage_endpoints.py` replaces the repository wholesale
with a fake, so M11 -- swapping `owner_id` for `object_id` in the arguments to
`storage_completion_key`, which is the ownership filter -- left every endpoint
test green. The SQL functions themselves are proved against a real cluster in
`test_storage_plane.py`; what neither covered was the code that CALLS them.

That gap is the recurring one in a new place: 0014's functions filter on owner
and this module decides what owner they are given, so a defect here is a
correct plane asked the wrong question. The tests below record the statement and
the parameters rather than reaching a database, because what is under test is
the argument list -- and a live cluster would prove the SQL a second time while
still not proving this.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.storage_repository import StorageRepository

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

OWNER = UUID("11111111-1111-4111-8111-111111111111")


class RecordingCursor:
    def __init__(self, sink: list[tuple[str, tuple[Any, ...]]], row: dict[str, Any]) -> None:
        self._sink = sink
        self._row = row

    async def execute(self, statement: str, parameters: tuple[Any, ...]) -> None:
        self._sink.append((statement, parameters))

    async def fetchone(self) -> dict[str, Any]:
        return self._row


class RecordingConnection:
    def __init__(self, sink, row) -> None:
        self._sink = sink
        self._row = row

    def cursor(self, row_factory=None):  # the signature psycopg uses
        return RecordingCursor(self._sink, self._row)


class RecordingPool:
    """Enough of `AsyncConnectionPool` to capture one round trip."""

    def __init__(self, row: dict[str, Any]) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._row = row

    def connection(self):
        sink, row = self.calls, self._row

        class Context:
            async def __aenter__(self):
                return RecordingConnection(sink, row)

            async def __aexit__(self, *exception):
                return False

        return Context()


def run(coroutine):
    return asyncio.run(coroutine)


@pytest.mark.parametrize(
    ("method", "kwargs", "function", "row"),
    [
        (
            "completion_key",
            {"object_id": uuid4(), "owner_id": OWNER},
            "storage_completion_key",
            {"object_key": "objects/alpha-dev/v1/x"},
        ),
        (
            "complete",
            {"object_id": uuid4(), "owner_id": OWNER, "verified_bytes": 12},
            "storage_complete_upload",
            {"state": "available"},
        ),
        (
            "lookup_for_download",
            {"object_id": uuid4(), "owner_id": OWNER},
            "storage_lookup_for_download",
            {"object_key": "k", "content_type": None, "verified_bytes": 1},
        ),
        (
            "tombstone",
            {"object_id": uuid4(), "owner_id": OWNER},
            "storage_tombstone",
            {"moved": True},
        ),
    ],
)
def test_every_owner_scoped_call_passes_the_owner_and_not_something_else(
    method, kwargs, function, row
):
    """The ownership filter is an ARGUMENT, so passing the wrong one defeats it.

    Each call takes an object id and an owner id, both `uuid`, so swapping them
    is a type-correct mistake that no signature catches. The assertion is that
    the owner appears in the parameters AND that it is not the object id -- the
    second half is what M11 would have failed, and the first half alone would
    not have.
    """
    pool = RecordingPool(row)
    repository = StorageRepository(pool)

    run(getattr(repository, method)(**kwargs))

    statement, parameters = pool.calls[0]
    assert function in statement
    assert kwargs["owner_id"] in parameters, f"{method} never sent the owner"
    assert parameters.count(kwargs["object_id"]) == 1, (
        f"{method} sent the object id where the owner belongs; the ownership "
        "filter would match on the wrong column"
    )
    assert parameters.index(kwargs["object_id"]) < parameters.index(kwargs["owner_id"]), (
        f"{method} sent (owner, object) where 0014 declares (id, owner)"
    )


def test_create_intent_sends_the_key_the_service_generated():
    """The key travels as a parameter and is never interpolated into the SQL.

    `S608` is disabled in some test modules for interpolated identifiers; this
    asserts the object key is not one of them. A key inside the statement text
    would be an injection surface reachable from an upload request.
    """
    identifier = uuid4()
    pool = RecordingPool({"id": identifier})
    repository = StorageRepository(pool)
    key = "objects/alpha-dev/v1/8f14e45f-ceea-467a-9f16-7b8b1a0a4a55"

    run(
        repository.create_intent(
            owner_id=OWNER,
            object_key=key,
            content_type="text/plain",
            declared_bytes=12,
            ttl_seconds=900,
        )
    )

    statement, parameters = pool.calls[0]
    assert "storage_create_upload_intent" in statement
    assert key not in statement, "the object key was interpolated into the statement text"
    assert parameters == (OWNER, key, "text/plain", 12, 900)


def test_the_repository_holds_no_privilege_of_its_own():
    """Every statement is a function call, never a table reference.

    `storage_service` has EXECUTE on the eight functions and NO privilege of any
    kind on `app_private.storage_objects` (Run 3, Run 4), so a statement naming
    the table would fail on a real cluster. Asserting it here means the failure
    is a test rather than a 500 in a container.
    """
    import inspect

    source = inspect.getsource(StorageRepository)

    assert "storage_objects" not in source, (
        "the repository names the table; the role holds no privilege on it and "
        "every access must go through a SECURITY DEFINER function"
    )
    for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert verb not in source.upper().replace("SELECT APP_PRIVATE", ""), verb

"""The four storage endpoints, their two orderings, and what they refuse to say.

`STO-OWN-001`, `STO-KEY-001`, `STO-URL-001`, `STO-COMPLETE-001`.

**What is faked here, and what deliberately is not.** ADR 0065/0066: a rig is a
second configuration of the product, and Run 9 of Session 5 produced three
defects from exactly that. So the **real `R2Adapter` presigns every URL in this
file** -- presigning is local arithmetic with no network, so there is nothing to
stand in for, and the URLs asserted below are the ones the product would issue.
What is replaced is the database (a cluster is `tests/integration/`'s) and the
single `HeadObject`, which is the only network call in the request path.

The fake repository answers exactly what migration 0014's functions answer,
including their obscuring: `None` for absent, foreign and wrong-state alike. A
fake that distinguished them would let a test pass that the real plane fails.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError

from app import errors
from app import scopes as scope_map
from app import settings as settings_module
from app.object_keys import KEY_VERSION, is_derived_key, object_key
from app.storage_client import R2Adapter, StorageConfig, StorageError
from app.storage_models import UploadIntentRequest
from app.storage_service import StorageService

ACCOUNT = "0123456789abcdef0123456789abcdef"
PREFIX = "objects/alpha-dev/"
OWNER = UUID("11111111-1111-4111-8111-111111111111")
STRANGER = UUID("22222222-2222-4222-8222-222222222222")


def make_adapter() -> R2Adapter:
    return R2Adapter(
        StorageConfig(
            endpoint=f"https://{ACCOUNT}.r2.cloudflarestorage.com",
            bucket="apg-alpha-dev",
            prefix=PREFIX,
            access_key_id="a" * 32,
            secret_access_key="b" * 64,
            upload_url_ttl_seconds=900,
            download_url_ttl_seconds=300,
            max_upload_bytes=1024,
        )
    )


class FakeRepository:
    """Answers exactly what 0014's functions answer, obscuring included."""

    def __init__(self) -> None:
        self.rows: dict[UUID, dict[str, Any]] = {}
        self.completed: list[tuple[UUID, UUID, int]] = []

    async def create_intent(
        self, *, owner_id, object_key, content_type, declared_bytes, ttl_seconds
    ):
        identifier = uuid4()
        self.rows[identifier] = {
            "owner": owner_id,
            "key": object_key,
            "state": "pending",
            "content_type": content_type,
        }
        return identifier

    async def completion_key(self, *, object_id, owner_id):
        # `pending` OR `available`, matching 0015's predicate exactly. A fake
        # that filtered on pending alone would make the idempotency test below
        # pass against a plane that does not have the property -- which is how
        # the defect it now covers got in.
        row = self.rows.get(object_id)
        if row is None or row["owner"] != owner_id or row["state"] not in ("pending", "available"):
            return None
        return row["key"]

    async def complete(self, *, object_id, owner_id, verified_bytes):
        self.completed.append((object_id, owner_id, verified_bytes))
        row = self.rows.get(object_id)
        if row is None or row["owner"] != owner_id:
            return None
        if row["state"] == "pending":
            row["state"] = "available"
        return row["state"]

    async def lookup_for_download(self, *, object_id, owner_id):
        from app.storage_repository import DownloadTarget

        row = self.rows.get(object_id)
        if row is None or row["owner"] != owner_id or row["state"] != "available":
            return None
        return DownloadTarget(row["key"], row["content_type"], 12)

    async def tombstone(self, *, object_id, owner_id):
        row = self.rows.get(object_id)
        if row is None or row["owner"] != owner_id or row["state"] == "tombstoned":
            return False
        row["state"] = "tombstoned"
        return True


class FakeBounded:
    """Only the HeadObject. The one network call in the request path."""

    def __init__(self, length: int | None = 12, raises: Exception | None = None) -> None:
        self.length = length
        self.raises = raises
        self.calls: list[str] = []

    async def head_object(self, key: str) -> dict[str, Any]:
        self.calls.append(key)
        if self.raises is not None:
            raise self.raises
        return {"content_length": self.length}


class FakePrincipal:
    def __init__(self, user_id: UUID, scopes: set[str]) -> None:
        self.user_id = user_id
        self.scopes = scopes


class FakeAuth:
    """Counts `authenticate` calls, so the re-check ordering is observable."""

    def __init__(self, principals: list[FakePrincipal] | None = None) -> None:
        self.principals = principals or []
        self.calls = 0

    async def authenticate(self, header: str | None):
        index = min(self.calls, len(self.principals) - 1)
        self.calls += 1
        principal = self.principals[index]
        if isinstance(principal, Exception):
            raise principal
        return principal

    @staticmethod
    def require_scope(principal, scope: str) -> None:
        if scope not in principal.scopes:
            raise errors.AuthorizationFailed(scope)


def build(
    *,
    repository: FakeRepository | None = None,
    bounded: FakeBounded | None = None,
    principals: list[Any] | None = None,
    max_upload_bytes: int = 1024,
):
    """A storage-mode application with the real router and real presigning."""
    from app import main as main_module
    from app import storage_routes

    repository = repository if repository is not None else FakeRepository()
    bounded = bounded if bounded is not None else FakeBounded()
    adapter = make_adapter()

    application = main_module.create_app("storage")
    application.state.storage = StorageService(
        repository,
        adapter,
        bounded,
        max_upload_bytes=max_upload_bytes,
        upload_ttl_seconds=900,
        download_ttl_seconds=300,
        object_prefix=PREFIX,
    )
    everyone = {scope_map.OBJECTS_READ, scope_map.OBJECTS_WRITE}
    auth = FakeAuth(principals or [FakePrincipal(OWNER, everyone)])
    application.state.service = auth

    # `require_scope` is a staticmethod on the real AuthService and the route
    # calls it on the CLASS, not the instance -- so the fake above cannot
    # intercept it and the REAL scope check runs. That is deliberate: the scope
    # gate is the product's, and a fake that answered it would leave
    # `test_a_token_without_the_scope_is_refused` measuring the fake.
    del storage_routes
    return application, repository, bounded, auth


def call(application, method: str, path: str, **kwargs) -> httpx.Response:
    import asyncio

    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://storage.invalid") as c:
            return await c.request(method, path, **kwargs)

    return asyncio.run(run())


# ---------------------------------------------------------------------------
# ADR 0101 -- one image, two modes, and the surface each one has


def test_the_auth_mode_does_not_serve_the_storage_surface():
    from app import main as main_module

    paths = {route.path for route in main_module.create_app("auth").routes}

    assert "/upload-intents" not in paths
    assert "/auth/login" in paths


def test_the_storage_mode_does_not_serve_the_auth_surface():
    """The complement, and it is the half that matters.

    A storage container serving `/auth/login` would be an issuer nobody
    published -- except it holds no signing key, so it would be an issuer that
    500s. Either way it is a surface nothing tested.
    """
    from app import main as main_module

    paths = {route.path for route in main_module.create_app("storage").routes}

    assert "/upload-intents" in paths
    assert "/auth/login" not in paths
    assert "/admin/users" not in paths


@pytest.mark.parametrize("bad", ["", "auth-api", "Storage", "both", None])
def test_an_unnamed_or_unknown_mode_refuses_to_build(bad, monkeypatch):
    """No default. ADR 0055's reasoning applied to behaviour rather than a value.

    A default would start the wrong service with a correct-looking
    configuration -- which is exactly how D333's fresh-bootstrap path stored 64
    characters of hex as an RSA key for two sessions.
    """
    from app import main as main_module

    monkeypatch.delenv("APP_MODE", raising=False)
    with pytest.raises(settings_module.MissingSetting, match="APP_MODE"):
        main_module.create_app(bad)


def test_storage_mode_refuses_to_start_holding_a_signing_key(tmp_path):
    """Absent, not ignored (ADR 0101, D320).

    Tolerating the variable would mean a storage container that had somehow been
    handed a key would start normally and hold one. The boundary between the two
    modes is only real if something refuses.

    **`APG_JWKS_FILE` was added to this environment by ADR 0113**, which made a
    key set source required in storage mode. The assertion and the control are
    both unchanged; what changed is that a storage environment carrying no key
    set is no longer a *valid* one, so the control half would otherwise fail for
    a reason this test is not about. Nothing was weakened -- D381 is what a
    storage runtime with no key set actually does, and it is now asserted in
    `tests/contract/test_verifier_key_sets.py`.
    """
    environment = {
        "APG_JWKS_FILE": str(tmp_path / "jwks.json"),
        "APG_PROJECT_KEY": "alpha-dev",
        "APG_PROJECT_ENVIRONMENT": "dev",
        "APG_JWT_ISSUER": "https://alpha.example.com",
        "APG_JWT_AUDIENCE": "apg",
        "APG_DATABASE_HOST": "pgbouncer",
        "APG_DATABASE_PORT": "6432",
        "APG_DATABASE_NAME": "app",
        "APG_DATABASE_ROLE": "apg_alpha_dev_storage_service",
        "APG_DATABASE_PASSFILE": str(tmp_path / "pgpass"),
        "APG_POOL_SIZE": "4",
        "APG_LISTEN_PORT": "8080",
        "APG_ROLE_NAMES": json.dumps({"authenticated": "apg_alpha_dev_authenticated"}),
        "APG_SIGNING_KEY_FILE": str(tmp_path / "key.pem"),
    }
    with pytest.raises(settings_module.MissingSetting, match="APG_SIGNING_KEY_FILE"):
        settings_module.load(environment, mode="storage")

    # The control: the same environment without it loads.
    #
    # `.pop` rather than `del environment[...]`, and not for style.
    # `test_every_test_declares_the_environment_it_consumes` counts any
    # subscript with an `APG_`-prefixed string constant as a real environment
    # read, because reading one directly is the same dependency as taking the
    # fixture. That is deliberately broad and it is right to be: the dict here
    # is one this test built, so the flag was a false positive, and the fix
    # belongs on this side rather than in a scanner that would then stop
    # catching the true case.
    environment.pop("APG_SIGNING_KEY_FILE")
    assert settings_module.load(environment, mode="storage").signing_key_file is None


# ---------------------------------------------------------------------------
# STO-KEY-001 -- the key is generated, never accepted


def test_the_request_model_has_no_key_or_bucket_field():
    """Enforced on the MODEL, which is stronger than enforcing it in a handler.

    A handler can be edited to read a field; a model with `extra="forbid"`
    refuses the request before any handler sees it.
    """
    fields = set(UploadIntentRequest.model_fields)

    assert fields == {"declared_bytes", "content_type"}
    # `extra_forbidden` specifically, not any exception: without
    # `extra="forbid"` pydantic ACCEPTS and silently discards the member, so the
    # model would build and the assertion above would still hold. Measured in
    # `models.py`'s docstring, and this is the arm that proves it here.
    with pytest.raises(ValidationError) as caught:
        UploadIntentRequest(declared_bytes=1, object_key="objects/alpha-dev/v1/mine")
    assert {item["type"] for item in caught.value.errors()} == {"extra_forbidden"}


def test_a_client_supplied_key_is_refused_rather_than_ignored():
    application, repository, _, _ = build()

    response = call(
        application,
        "POST",
        "/upload-intents",
        content=json.dumps({"declared_bytes": 10, "key": "objects/alpha-dev/v1/mine"}),
    )

    assert response.status_code == 400
    assert response.json() == {"error": "malformed_request"}
    assert repository.rows == {}, "a refused request created a row"


def test_the_generated_key_has_the_derived_shape_and_the_validator_is_not_a_tautology():
    """`is_derived_key` is written independently of `object_key` (D173).

    The negative arms are what make that claim real: each one is a plausible
    near-miss that a validator built from the generator's own expression would
    accept.
    """
    key = object_key(PREFIX)

    assert is_derived_key(PREFIX, key)
    assert key.startswith(f"{PREFIX}{KEY_VERSION}/")
    for wrong in (
        "objects/other-dev/v1/" + key.rsplit("/", 1)[1],  # another project's prefix
        f"{PREFIX}v2/" + key.rsplit("/", 1)[1],  # another layout generation
        f"{PREFIX}{KEY_VERSION}/not-a-uuid",
        f"{PREFIX}{KEY_VERSION}/11111111-1111-1111-8111-111111111111",  # uuid1, not 4
        key + "/extra",
    ):
        assert not is_derived_key(PREFIX, wrong), wrong


def test_the_response_carries_no_bucket_no_key_and_no_etag():
    application, _, _, _ = build()

    body = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 10})
    ).json()

    assert set(body) == {"object_id", "upload_url", "expires_in", "max_bytes", "required_headers"}
    rendered = json.dumps(body)
    assert "apg-alpha-dev" not in rendered.replace(body["upload_url"], "")
    assert "etag" not in rendered.lower()


# ---------------------------------------------------------------------------
# STO-OWN-001 -- a stranger's id and a nonexistent id are one answer


def test_a_download_for_a_stranger_and_for_nothing_are_byte_identical():
    """The property, asserted as an equality between two responses.

    Comparing both against a literal 404 would pass if one of them started
    carrying a `message`; comparing them against EACH OTHER is what makes the
    indistinguishability the thing under test.
    """
    application, repository, _, _ = build()
    stranger_object = uuid4()
    repository.rows[stranger_object] = {
        "owner": STRANGER,
        "key": object_key(PREFIX),
        "state": "available",
        "content_type": "text/plain",
    }

    foreign = call(application, "GET", f"/objects/{stranger_object}/download-url")
    absent = call(application, "GET", f"/objects/{uuid4()}/download-url")

    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json() == {"error": "object_unavailable"}
    assert foreign.headers["cache-control"] == absent.headers["cache-control"] == "no-store"


def test_an_owner_can_download_their_own_available_object():
    """The happy path, and it is here because the battery found it missing.

    Every other download test in this file asserts a REFUSAL, so M1 -- breaking
    the owner filter so that `lookup_for_download` matches nothing -- left the
    whole suite green. A surface tested only through what it denies is a surface
    nobody has checked answers at all, and the refusal tests then pass for a
    service that is simply broken.
    """
    application, repository, _, _ = build()
    mine = uuid4()
    key = object_key(PREFIX)
    repository.rows[mine] = {
        "owner": OWNER,
        "key": key,
        "state": "available",
        "content_type": "text/plain",
    }

    response = call(application, "GET", f"/objects/{mine}/download-url")

    assert response.status_code == 200
    body = response.json()
    assert body["content_type"] == "text/plain"
    assert body["expires_in"] == 300
    assert f"/apg-alpha-dev/{key}" in body["download_url"]
    assert "X-Amz-Signature=" in body["download_url"]


def test_two_upload_intents_never_share_a_key():
    """122 unguessable bits per key, and nothing asserted it until the battery.

    M4 replaced `uuid.uuid4()` with a constant. The key still matched
    `is_derived_key` -- a fixed uuid4-shaped string is a well-formed one -- and
    every test stayed green. Two intents on one key is the collision the
    first-write condition exists to make loud rather than silent, and ADR 0102's
    "independent random values" was a claim nothing checked.
    """
    application, repository, _, _ = build()

    for _ in range(8):
        call(application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 10}))

    keys = [row["key"] for row in repository.rows.values()]
    assert len(keys) == 8
    assert len(set(keys)) == 8, "two upload intents were given the same object key"


def test_a_pending_object_is_as_invisible_as_a_missing_one():
    """The four causes are absent, foreign, PENDING and tombstoned."""
    application, repository, _, _ = build()
    pending = uuid4()
    repository.rows[pending] = {
        "owner": OWNER,
        "key": object_key(PREFIX),
        "state": "pending",
        "content_type": None,
    }

    response = call(application, "GET", f"/objects/{pending}/download-url")

    assert response.status_code == 404
    assert response.json() == {"error": "object_unavailable"}


def test_deleting_a_stranger_s_object_answers_204_and_does_not_move_it():
    """Idempotent AND obscuring, and the second assertion is the real one.

    204 on a stranger's object is not permissiveness -- the row is untouched.
    Answering 404 instead would make DELETE an existence oracle for exactly the
    ids the download path refuses to answer about.
    """
    application, repository, _, _ = build()
    stranger_object = uuid4()
    repository.rows[stranger_object] = {
        "owner": STRANGER,
        "key": object_key(PREFIX),
        "state": "available",
        "content_type": None,
    }

    first = call(application, "DELETE", f"/objects/{stranger_object}")
    second = call(application, "DELETE", f"/objects/{uuid4()}")

    assert first.status_code == second.status_code == 204
    assert repository.rows[stranger_object]["state"] == "available", "a stranger moved the row"


def test_a_malformed_object_id_is_400_and_not_404():
    """The one place this surface does distinguish, and why.

    404 is the answer for a well-formed id the caller may not know about. A
    string that is not a uuid names no object at all, so refusing it structurally
    reveals nothing -- and answering 404 would leave a client unable to tell a
    typo from a permission boundary while debugging its own code.
    """
    application, _, _, _ = build()

    response = call(application, "GET", "/objects/not-a-uuid/download-url")

    assert response.status_code == 400
    assert response.json() == {"error": "malformed_request"}


# ---------------------------------------------------------------------------
# STO-COMPLETE-001 -- the ordering


def test_completion_revalidates_the_subject_after_the_provider_call():
    """The ordering this endpoint exists to get right.

    The subject is authenticated, the provider is asked, and THEN the subject is
    authenticated again before anything is written. Here the second call raises,
    standing in for a subject disabled while the bytes were in flight -- and the
    assertion is that the CAS never ran.
    """
    application, repository, bounded, auth = build(
        principals=[
            FakePrincipal(OWNER, {scope_map.OBJECTS_WRITE}),
            errors.AuthenticationFailed("disabled mid-upload"),
        ]
    )
    intent = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 10})
    ).json()

    auth.calls = 0  # the intent above consumed the first principal
    auth.principals = [
        FakePrincipal(OWNER, {scope_map.OBJECTS_WRITE}),
        errors.AuthenticationFailed("disabled mid-upload"),
    ]
    response = call(
        application,
        "POST",
        f"/upload-intents/{intent['object_id']}/complete",
        content="{}",
    )

    assert response.status_code == 401
    assert bounded.calls, "the provider was never asked, so the ordering is untested"
    assert repository.completed == [], "the CAS ran for a subject that had been refused"


def test_completion_is_idempotent():
    """A retried completion is a 200, not a conflict (STO-COMPLETE-001).

    The CAS matches zero rows the second time and the function reports the state
    the object already has, which the service treats as success.
    """
    application, _, _, _ = build()
    intent = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 10})
    ).json()
    path = f"/upload-intents/{intent['object_id']}/complete"

    first = call(application, "POST", path, content="{}")
    second = call(application, "POST", path, content="{}")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_completing_an_object_whose_bytes_never_arrived_is_a_404():
    """`ObjectAbsent` from the provider must not be distinguishable.

    Otherwise completing a guessed id tells the caller their guess named a real
    pending intent.
    """
    from app.storage_client import ObjectAbsent

    application, _, _, _ = build(
        bounded=FakeBounded(raises=ObjectAbsent("head_object", "404", 404))
    )
    intent = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 10})
    ).json()

    response = call(
        application, "POST", f"/upload-intents/{intent['object_id']}/complete", content="{}"
    )

    assert response.status_code == 404
    assert response.json() == {"error": "object_unavailable"}


def test_completion_records_the_providers_count_and_not_the_clients_claim():
    """`declared_bytes` is a claim; `verified_bytes` is what the provider counted."""
    application, repository, _, _ = build(bounded=FakeBounded(length=7))
    intent = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 999})
    ).json()

    body = call(
        application, "POST", f"/upload-intents/{intent['object_id']}/complete", content="{}"
    ).json()

    assert body["size_bytes"] == 7
    assert repository.completed[0][2] == 7


def test_a_completion_body_that_declares_a_size_is_refused():
    """The empty model is what refuses it, rather than the handler ignoring it."""
    application, _, _, _ = build()
    intent = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 10})
    ).json()

    response = call(
        application,
        "POST",
        f"/upload-intents/{intent['object_id']}/complete",
        content=json.dumps({"verified_bytes": 1}),
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# STO-URL-001 -- no-store, and no provider detail


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/upload-intents", json.dumps({"declared_bytes": 10})),
        ("GET", "/objects/{id}/download-url", None),
        ("DELETE", "/objects/{id}", None),
        ("GET", "/objects/not-a-uuid/download-url", None),
    ],
)
def test_every_response_is_no_store_including_the_failures(method, path, body):
    """A cache holding either a URL or a 404 serves it to the next subject."""
    application, repository, _, _ = build()
    identifier = uuid4()
    repository.rows[identifier] = {
        "owner": OWNER,
        "key": object_key(PREFIX),
        "state": "available",
        "content_type": None,
    }

    response = call(application, method, path.replace("{id}", str(identifier)), content=body)

    assert response.headers.get("cache-control") == "no-store", response.status_code


def test_a_provider_failure_is_not_reported_to_the_caller():
    """`SignatureDoesNotMatch` would tell a caller about the credential state."""
    application, _, _, _ = build(
        bounded=FakeBounded(raises=StorageError("head_object", "SignatureDoesNotMatch", 403))
    )
    intent = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 10})
    ).json()

    response = call(
        application, "POST", f"/upload-intents/{intent['object_id']}/complete", content="{}"
    )

    assert response.status_code == 404
    assert response.json() == {"error": "object_unavailable"}
    assert "Signature" not in response.text


def test_the_upload_url_is_a_real_presigned_url_carrying_the_first_write_condition():
    """Presigned by the REAL adapter, so this asserts what the product issues."""
    application, _, _, _ = build()

    body = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 10})
    ).json()

    assert f"https://{ACCOUNT}.r2.cloudflarestorage.com/apg-alpha-dev/" in body["upload_url"]
    assert "if-none-match" in body["upload_url"].lower()
    assert body["required_headers"] == {"If-None-Match": "*"}


# ---------------------------------------------------------------------------
# Bounds and scopes


def test_a_declared_size_over_the_limit_is_refused_before_a_url_is_issued():
    application, repository, _, _ = build(max_upload_bytes=100)

    response = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 101})
    )

    assert response.status_code == 422
    assert repository.rows == {}, "a doomed upload reserved a key"


def test_a_provider_count_over_the_limit_leaves_the_object_pending():
    """The provider counted more than the bound allows.

    Refusing rather than recording is what keeps `available` meaning "within the
    bound this deployment published".
    """
    application, repository, _, _ = build(max_upload_bytes=100, bounded=FakeBounded(length=101))
    intent = call(
        application, "POST", "/upload-intents", content=json.dumps({"declared_bytes": 10})
    ).json()

    response = call(
        application, "POST", f"/upload-intents/{intent['object_id']}/complete", content="{}"
    )

    assert response.status_code == 422
    assert repository.completed == []
    assert repository.rows[UUID(intent["object_id"])]["state"] == "pending"


@pytest.mark.parametrize(
    ("method", "path", "needed"),
    [
        ("POST", "/upload-intents", scope_map.OBJECTS_WRITE),
        ("GET", "/objects/{id}/download-url", scope_map.OBJECTS_READ),
        ("DELETE", "/objects/{id}", scope_map.OBJECTS_WRITE),
    ],
)
def test_each_route_requires_its_scope(method, path, needed):
    """Gated on the scope, never on the role -- API-ADMIN-001's rule, reused.

    The token below carries every OTHER storage scope, so a route that checked
    "has any storage scope" would pass. It is refused because it lacks the one
    this route names.
    """
    others = ({scope_map.OBJECTS_READ, scope_map.OBJECTS_WRITE} - {needed}) or set()
    application, _, _, _ = build(principals=[FakePrincipal(OWNER, others)])

    response = call(
        application,
        method,
        path.replace("{id}", str(uuid4())),
        content=json.dumps({"declared_bytes": 10}) if method == "POST" else None,
    )

    assert response.status_code == 403
    assert response.json() == {"error": "authorization_failed"}

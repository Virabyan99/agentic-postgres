"""The four storage endpoints, under `/api/app/storage`.

Human tokens only, `no-store` on every response, and the ownership-obscuring
answer on every path that could otherwise be turned into an existence oracle.

**Why this is a second router rather than four more routes in `routes.py`.**
One image runs two modes (ADR 0101), and the mode decides which router is
mounted. A storage endpoint reachable from the auth service's port would be a
surface nothing published and nothing tested, and `APP_MODE` is what keeps the
two apart at the only moment it can be enforced -- application construction.

**Every response carries `Cache-Control: no-store`, including the failures.**
Two of them carry a presigned URL, which is a bearer credential; the rest carry
a statement about whether an object exists, which is the thing STO-OWN-001 is
about. A shared cache holding either would serve one subject's answer to the
next one asking.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import errors, openapi_docs
from app import scopes as scope_map

# The strict body reader, imported rather than reimplemented. It applies the
# bound to the raw bytes before building the document, refuses a duplicate JSON
# member, and turns a pydantic failure into `MalformedRequest` carrying the
# error TYPES and never the offending values -- four behaviours, each measured,
# and a second copy of them is the duplicate-plus-test shape D175 and D260 have
# already cost this project twice. The leading underscore says "not the public
# surface of this service"; it does not mean "write another one".
from app.routes import _body as read_body
from app.service import AuthService
from app.storage_client import StorageError
from app.storage_models import (
    CompletedObjectResponse,
    CompleteUploadRequest,
    DownloadGrantResponse,
    UploadIntentRequest,
    UploadIntentResponse,
)

router = APIRouter()

#: Repeated on every response rather than applied by middleware, deliberately.
#: A middleware that added it would be one edit away from being scoped to a path
#: prefix that later stops matching, and the failure mode is silent: a presigned
#: URL becomes cacheable and nothing goes red. Naming it at each site is the
#: shape `routes.py` already uses for the token responses.
NO_STORE = {"Cache-Control": "no-store"}


def _storage(request: Request):
    return request.app.state.storage


def _auth(request: Request) -> AuthService:
    return request.app.state.service


def _object_id(raw: str) -> UUID:
    """Parse the path parameter, or refuse the request structurally.

    A malformed uuid is `malformed_request` -- 400, with nothing in it -- and
    NOT `object_unavailable`. The distinction is deliberate and runs the
    opposite way to the rest of this module: 404 is the answer for a *well-formed
    id the caller may not know about*, and using it here too would mean a client
    could not tell a typo from a permission boundary while debugging its own
    code. A string that is not a uuid names no object at all, so refusing it
    reveals nothing about any object.
    """
    try:
        return UUID(raw)
    except ValueError as exc:
        raise errors.MalformedRequest("object id is not a uuid") from exc


def _no_store(response: Response) -> Response:
    """Stamp `no-store`, including on the four shared error responses.

    The shared helpers in `errors.py` are the auth service's too, and three of
    them do not set the header. Rather than change what the auth surface returns
    from a storage run, the guard stamps every response leaving this router --
    which also means a route added later cannot omit it.

    **This exists because a test caught the docstring above being false.** The
    module said "every response carries no-store, including the failures", and a
    malformed uuid came back 400 with no cache header at all. A comment claiming
    a property the code does not have is D267's shape, and the only reason this
    one was caught is that the test enumerated the failure paths rather than the
    happy ones.
    """
    response.headers.setdefault("Cache-Control", "no-store")
    return response


async def _guard(handler) -> Response:
    """One place the storage exceptions become responses.

    Mirrors `routes._guard` and extends it with the two storage types. A
    decorator rather than per-route `try` blocks, so a route added later cannot
    forget one and answer 500 with a traceback -- which here would be a
    traceback naming an object key.
    """
    try:
        return _no_store(await handler())
    except errors.AuthenticationFailed:
        return _no_store(errors.unauthenticated())
    except errors.AuthorizationFailed:
        return _no_store(errors.unauthorized())
    except errors.MalformedRequest:
        return _no_store(errors.malformed())
    except errors.InvalidRequest as exc:
        return _no_store(errors.invalid(str(exc)))
    except errors.ObjectUnavailable:
        return errors.object_unavailable()
    except errors.ObjectStateConflict as exc:
        return errors.object_state_conflict(exc.state)
    except StorageError:
        # A provider failure never reaches the caller as itself. The exception
        # carries an operation and a provider error code and no target, which
        # makes it safe to log -- but a caller told `SignatureDoesNotMatch`
        # learns about this deployment's credential state and one told
        # `AccessDenied` learns its token's scope. They get the same 404 the
        # ownership filter gives, so the provider being misconfigured is
        # indistinguishable from the object not being theirs.
        return errors.object_unavailable()


# ---------------------------------------------------------------------------
# What the published reference says about this surface
# ---------------------------------------------------------------------------
#
# **This block is Run 9's, and its absence was a real defect.** Run 6 built these
# four routes with bare `Request`/`Response` signatures and no `responses=`, so
# the document FastAPI generated said each one returns `200` with an
# unspecified body and nothing else -- for operations that answer 201, 204, 401,
# 403, 404, 409 and 422. It also published a `422` shaped as FastAPI's own
# `HTTPValidationError`, which this service never emits: a malformed object id
# is `MalformedRequest` and comes back 400 in the house shape.
#
# `openapi_docs.py` exists precisely to prevent that and says so in its own
# docstring. It was written for the auth router and never applied here. *When a
# decision is implemented, ask which of its callers got the implementation*
# (D333) -- and nothing noticed for three runs, because the storage half of the
# document was not aggregated into anything until `app-contract` was taught to.
#
# `responses=` REPLACES and `openapi_extra` deep-merges, measured in Session 6
# and recorded in `openapi_docs.py`. The replacement is what removes FastAPI's
# `HTTPValidationError`, so every status below goes through `responses=`.

DOC_UPLOAD_INTENT = openapi_docs.described(
    summary="Reserve an object and mint a first-write upload URL",
    description=(
        "The server generates the object id and the key. There is no field for either "
        "in the request model and no code path by which a client-supplied key could "
        "reach a presign (STO-KEY-001).\n\n"
        "`upload_url` is a bearer credential with a short life. Send it the "
        "`required_headers` exactly: the URL is signed over `If-None-Match: *`, so "
        "omitting the header yields 403 from the provider rather than an unconditional "
        "write, and a second PUT to the same key yields 412."
    ),
    request_model=UploadIntentRequest,
)
RESP_UPLOAD_INTENT = {
    201: openapi_docs.created(
        "Reserved. The object is `pending` until it is completed.", UploadIntentResponse
    ),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    422: openapi_docs.INVALID,
}

DOC_COMPLETE = openapi_docs.described(
    summary="Verify the uploaded bytes and make the object available",
    description=(
        "Asks the provider how many bytes actually arrived, then compare-and-sets. "
        "Idempotent: a repeated call on an already-available object returns the same "
        "200 rather than a conflict.\n\n"
        "The subject is re-authenticated **after** the provider answers and before "
        "anything is written, so a subject disabled while the bytes were in flight is "
        "refused rather than completing an upload on a revoked identity."
    ),
    request_model=CompleteUploadRequest,
)
RESP_COMPLETE = {
    200: openapi_docs.ok("Verified and available.", CompletedObjectResponse),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    404: openapi_docs.UNAVAILABLE,
    409: openapi_docs.CONFLICT,
    422: openapi_docs.INVALID,
}

DOC_DOWNLOAD_URL = openapi_docs.described(
    summary="Mint a short-lived download URL for an object you own",
    description=(
        "Owned and available only.\n\n"
        "**Issuing this is an authorization decision made now, and a later delete does "
        "not revoke it.** Nothing in this system can withdraw a presigned URL; the "
        "residual is bounded by `expires_in`, which is why the download TTL is "
        "configured shorter than the upload's."
    ),
)
RESP_DOWNLOAD_URL = {
    200: openapi_docs.ok("A short-lived GET.", DownloadGrantResponse),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    404: openapi_docs.UNAVAILABLE,
}

DOC_DELETE = openapi_docs.described(
    summary="Tombstone an object",
    description=(
        "Answers 204 for an object that was moved, for one already tombstoned, for one "
        "that never existed and for another subject's alike. Not a 404 on absence: the "
        "caller's intent is satisfied either way, and answering differently would make "
        "DELETE non-idempotent for the owner and turn it into an existence oracle.\n\n"
        "The bytes are removed by a later cleanup pass, not by this call. An object "
        "whose upload URL is still live is not collected until it expires, because a "
        "tombstone cannot revoke a presigned URL."
    ),
)
RESP_DELETE = {
    204: openapi_docs.no_content("Tombstoned, or already was, or never existed."),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
}


@router.post(
    "/upload-intents",
    status_code=201,
    openapi_extra=DOC_UPLOAD_INTENT,
    responses=RESP_UPLOAD_INTENT,
)
async def create_upload_intent(request: Request) -> Response:
    """Reserve an id and a key, and return a first-write URL.

    The response carries no bucket, no key and no ETag -- only the id the caller
    needs to complete, the URL, and the two bounds. `STO-KEY-001`: the key is
    generated server-side and appears nowhere except inside the signed URL.
    """

    async def run() -> Response:
        principal = await _auth(request).authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.OBJECTS_WRITE)

        payload = await read_body(request, UploadIntentRequest)
        assert isinstance(payload, UploadIntentRequest)

        intent = await _storage(request).create_upload_intent(
            owner_id=principal.user_id,
            declared_bytes=payload.declared_bytes,
            content_type=payload.content_type,
        )
        return JSONResponse(
            {
                "object_id": str(intent.object_id),
                "upload_url": intent.upload_url,
                "expires_in": intent.expires_in,
                "max_bytes": intent.max_bytes,
                # What the client must send for the conditional PUT to verify.
                # Named rather than assumed: the URL is signed over
                # `If-None-Match: *`, so a client that omits the header gets 403
                # SignatureDoesNotMatch, which is measured (Run 5) and would
                # otherwise look like a broken credential.
                "required_headers": {"If-None-Match": "*"},
            },
            status_code=201,
            headers=NO_STORE,
        )

    return await _guard(run)


@router.post(
    "/upload-intents/{object_id}/complete",
    openapi_extra=DOC_COMPLETE,
    responses=RESP_COMPLETE,
)
async def complete_upload(request: Request, object_id: str) -> Response:
    """Verify against the provider, then compare-and-set.

    **The subject is revalidated after the provider call**, and that is the
    ordering this endpoint exists to get right. A token that was current when
    the intent was created may not be current when the upload completes: the
    subject can be disabled, its scopes cut or its credential rotated while the
    bytes are in flight, and a `HeadObject` round trip is long enough for it to
    happen. So `authenticate` runs twice -- once to decide whether to look at
    all, once after the provider answers and before anything is written -- and
    the second call is what the CAS's owner id comes from.

    **No database transaction spans the provider call.** Three separate round
    trips, and the CAS is what tolerates the gaps between them, which is also
    what makes a retried completion idempotent rather than a conflict.
    """

    async def run() -> Response:
        storage = _storage(request)
        identifier = _object_id(object_id)

        principal = await _auth(request).authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.OBJECTS_WRITE)

        payload = await read_body(request, CompleteUploadRequest)
        assert isinstance(payload, CompleteUploadRequest)

        key = await storage.key_for(owner_id=principal.user_id, object_id=identifier)

        # The provider call. Everything between here and the CAS below is
        # unbounded in duration as far as this service is concerned: a
        # `HeadObject` is a network round trip to a third party.
        verified = await storage.verify_uploaded_bytes(key)

        # **Re-authenticate, AFTER the provider answered and before anything is
        # written.** This is the ordering the endpoint exists to get right, and
        # it is only expressible because `verify_uploaded_bytes` and `finalize`
        # are two calls: a subject disabled while the bytes were in flight is
        # refused here rather than completing an upload on a revoked identity.
        recheck = await _auth(request).authenticate(request.headers.get("authorization"))
        AuthService.require_scope(recheck, scope_map.OBJECTS_WRITE)
        if recheck.user_id != principal.user_id:
            # Cannot arise from a well-formed token, and asserted rather than
            # assumed: if it ever did, the CAS would run against a subject
            # different from the one whose key was read.
            raise errors.AuthenticationFailed("subject changed mid-request")

        size = await storage.finalize(
            owner_id=recheck.user_id, object_id=identifier, verified_bytes=verified
        )
        return JSONResponse(
            {"object_id": str(identifier), "state": "available", "size_bytes": size},
            headers=NO_STORE,
        )

    return await _guard(run)


@router.get(
    "/objects/{object_id}/download-url",
    openapi_extra=DOC_DOWNLOAD_URL,
    responses=RESP_DOWNLOAD_URL,
)
async def download_url(request: Request, object_id: str) -> Response:
    """A short-lived GET for an object this subject owns.

    Issuing this is an authorization decision made **now**. It is not revoked by
    a later tombstone, and the response says so in `expires_in` rather than
    implying a revocation this surface cannot perform.
    """

    async def run() -> Response:
        principal = await _auth(request).authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.OBJECTS_READ)

        grant = await _storage(request).download_url(
            owner_id=principal.user_id, object_id=_object_id(object_id)
        )
        return JSONResponse(
            {
                "download_url": grant.download_url,
                "expires_in": grant.expires_in,
                "content_type": grant.content_type,
                "size_bytes": grant.size_bytes,
            },
            headers=NO_STORE,
        )

    return await _guard(run)


@router.delete(
    "/objects/{object_id}",
    status_code=204,
    openapi_extra=DOC_DELETE,
    responses=RESP_DELETE,
)
async def delete_object(request: Request, object_id: str) -> Response:
    """Tombstone, and answer identically whatever was there.

    204 for an object that was moved, for one already tombstoned, for one that
    never existed and for another subject's alike. Not a 404 on absence: the
    caller's intent is satisfied either way, and answering differently would
    make DELETE non-idempotent for the owner *and* turn it into the existence
    oracle the download path refuses to be.

    The provider DELETE is not done here. It belongs to the cleanup lease,
    outside any transaction, at least once (ADR 0104) -- which is safe because
    `DeleteObject` on an absent key was measured to return 204.
    """

    async def run() -> Response:
        principal = await _auth(request).authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.OBJECTS_WRITE)

        await _storage(request).delete(owner_id=principal.user_id, object_id=_object_id(object_id))
        return Response(status_code=204, headers=NO_STORE)

    return await _guard(run)

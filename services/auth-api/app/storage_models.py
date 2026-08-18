"""The storage surface's request shapes, and the fields that are absent by design.

Same `_Strict` base as `models.py` and for the measured reason recorded there:
without `extra="forbid"` pydantic accepts and *discards* an unknown member, so a
client naming a field the server does not know leaves no trace at all.

**`STO-KEY-001` is enforced here, not in the service.** There is no `bucket`
field, no `key` field and no `object_key` field on any model in this file, so a
client-supplied key has no argument to arrive through -- and with `extra="forbid"`
a request that invents one is refused rather than silently stripped. Asserting
the absence on the model is stronger than asserting it in the handler, because a
handler can be edited to read something the model would have rejected.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: The longest content type this surface will record. RFC 6838 bounds a type and
#: subtree at 127 characters each; 255 covers both plus parameters, and the
#: value is stored and echoed rather than interpreted.
CONTENT_TYPE_MAX = 255


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class UploadIntentRequest(_Strict):
    """What a client may say about an upload it has not made yet.

    `declared_bytes` is a CLAIM, and the field is named so that nothing reads it
    as a fact. It is bounded against `max_upload_bytes` so the deployment can
    refuse a doomed upload before issuing a URL for it, but what is recorded as
    the object's size at completion is what the provider counted -- a separate
    column, filled from `HeadObject`. A client's assertion about its own bytes is
    not evidence, and the row keeps both so the difference stays visible.

    `content_type` is advisory in exactly the same way. It is echoed back on
    download and never used to decide anything; the storage surface does not
    sniff, transform, or trust it.
    """

    declared_bytes: int = Field(gt=0)
    content_type: str | None = Field(default=None, max_length=CONTENT_TYPE_MAX)


class CompleteUploadRequest(_Strict):
    """Deliberately empty, and that is the whole point of it.

    Everything completion needs is already server-side: the object id is in the
    path, the owner is the authenticated subject, the key is read from the
    pending row (migration 0015), and the size comes from the provider. There is
    nothing left for a client to supply.

    The model exists rather than the route accepting any body, so that a request
    carrying `{"verified_bytes": 1}` is refused with `malformed_request` instead
    of being ignored. A client trying to declare its own verified size is
    exactly the request this surface must not quietly accept.
    """


# ---------------------------------------------------------------------------
# What the routes return
# ---------------------------------------------------------------------------
#
# **Descriptive only, and never bound as a `response_model`.** `openapi_docs`'s
# docstring records why: FastAPI would filter and re-serialize every response
# through the model, and the route would no longer be returning what it built.
# These exist so the published document says what the surface does -- which,
# until Run 9, it did not: FastAPI generated a single `200` for each of these
# four operations from their bare `Response` signatures, so the reference
# advertised `200` for a 201 and for a 204, documented none of the failures, and
# published a `422` in FastAPI's own `HTTPValidationError` shape that this
# service never emits.
#
# That is the exact failure `openapi_docs.py`'s docstring describes and exists
# to prevent. It was written for the auth router in Session 6 and the storage
# router shipped without it in Run 6 -- *when a decision is implemented, ask
# which of its callers got the implementation* (D333).
#
# **What none of them carries**: a bucket, an object key, an ETag, a checksum, a
# provider request id, or any sign of another subject's existence.


class UploadIntentResponse(BaseModel):
    """What a caller gets to perform the upload, and nothing more.

    `upload_url` is a bearer credential with a short life -- anyone holding it
    can perform the PUT it authorizes. It is returned once and stored nowhere.

    `required_headers` is named rather than assumed. The URL is signed over
    `If-None-Match: *`, so a client that omits the header does not get an
    unconditional write -- it gets **403 SignatureDoesNotMatch** (measured, Run
    5), which is indistinguishable from a broken credential from where the
    client stands. Publishing the header is what makes the condition usable.
    """

    object_id: str
    upload_url: str
    expires_in: int
    max_bytes: int
    required_headers: dict[str, str]


class CompletedObjectResponse(BaseModel):
    """The object is available, and `size_bytes` is the provider's count.

    Not the client's `declared_bytes`. The two are separate fields in the row
    precisely because completion exists to detect that they disagree, and this
    reports the one that was verified.
    """

    object_id: str
    state: Literal["available"]
    size_bytes: int


class DownloadGrantResponse(BaseModel):
    """A short-lived GET, and an authorization decision made at issue time.

    **It is not revoked by a later tombstone.** Nothing in this system can
    withdraw a presigned URL; the residual is bounded by `expires_in`, which is
    why the download TTL is configured shorter than the upload's. The reference
    says so plainly rather than implying a revocation that does not exist.
    """

    download_url: str
    expires_in: int
    content_type: str | None
    size_bytes: int | None

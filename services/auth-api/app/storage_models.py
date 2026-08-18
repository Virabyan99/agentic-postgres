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

"""The four storage operations, and the two orderings that are correctness.

**Nothing here holds a database transaction across the provider call.** ADR
0104's reasoning, applied to the request path rather than to cleanup: a
transaction open across a network call to a third party is a lock whose duration
a third party sets. Completion is three separate steps -- authenticate,
`HeadObject`, compare-and-set -- and the gap between them is exactly what the
CAS exists to tolerate.

**The finalize revalidates the subject**, and this is the part that is easy to
leave out. A token that was current when the intent was created may not be
current when the upload completes: the subject can be disabled, its scopes cut,
or its credential rotated in between, and a provider round trip is long enough
for it to happen. So completion authenticates again *after* the provider call,
not only before it, and the CAS runs against the re-checked identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app import errors
from app.object_keys import object_key
from app.storage_client import BoundedR2, ObjectAbsent, R2Adapter, StorageError
from app.storage_repository import StorageRepository


@dataclass(frozen=True, slots=True)
class UploadIntent:
    object_id: UUID
    upload_url: str
    expires_in: int
    max_bytes: int


@dataclass(frozen=True, slots=True)
class DownloadGrant:
    download_url: str
    expires_in: int
    content_type: str | None
    size_bytes: int | None


class StorageService:
    """Orchestration only. Every authorization decision belongs to somebody else.

    The ownership filter is the database's (migration 0014), the signature is
    the provider's, and the scope check is the route's. What is here is the
    ORDER, which is the part that cannot be delegated -- and the two orderings
    that matter are named in the module docstring.
    """

    def __init__(
        self,
        repository: StorageRepository,
        adapter: R2Adapter,
        bounded: BoundedR2,
        *,
        max_upload_bytes: int,
        upload_ttl_seconds: int,
        download_ttl_seconds: int,
        object_prefix: str,
    ) -> None:
        self._repository = repository
        self._adapter = adapter
        self._bounded = bounded
        self._max_upload_bytes = max_upload_bytes
        self._upload_ttl_seconds = upload_ttl_seconds
        self._download_ttl_seconds = download_ttl_seconds
        self._object_prefix = object_prefix

    # -- upload ------------------------------------------------------------

    async def create_upload_intent(
        self, *, owner_id: UUID, declared_bytes: int, content_type: str | None
    ) -> UploadIntent:
        """Reserve a key, record a pending object, and mint a first-write URL.

        `declared_bytes` is what the client SAYS it will upload and is bounded
        here; what is stored as truth at completion is what the provider counted.
        The two are deliberately different fields in the row, because a client's
        claim about its own upload is not evidence.

        The key is generated -- never accepted. `UploadIntentRequest` has no key
        or bucket member, so there is no argument for one to arrive through.
        """
        if declared_bytes > self._max_upload_bytes:
            # 422 with a reason: the caller is authenticated, it is their own
            # request, and the bound is a fact they can act on by sending less.
            raise errors.InvalidRequest(
                f"declared_bytes exceeds the {self._max_upload_bytes} byte limit"
            )

        key = object_key(self._object_prefix)
        object_id = await self._repository.create_intent(
            owner_id=owner_id,
            object_key=key,
            content_type=content_type,
            declared_bytes=declared_bytes,
            ttl_seconds=self._upload_ttl_seconds,
        )
        # Presigning is local -- no network, no thread. It does not go through
        # the bounded executor, which exists to cap concurrent provider calls,
        # and putting it there would burn a permit on arithmetic.
        url = self._adapter.presign_put(key, first_write_only=True)
        return UploadIntent(
            object_id=object_id,
            upload_url=url,
            expires_in=self._upload_ttl_seconds,
            max_bytes=self._max_upload_bytes,
        )

    async def verify_uploaded_bytes(self, object_key_hint: str) -> int:
        """Ask the provider what actually arrived. **The whole provider call.**

        Split from `finalize` rather than sequenced inside one method, and the
        split is the point: the route re-authenticates the subject BETWEEN these
        two calls, and a single method would make that impossible to place. An
        ordering that a caller cannot express is an ordering the code does not
        really have -- the first draft of this module had one method and a
        docstring claiming the recheck happened after the provider call, which
        it could not have.

        `ObjectAbsent` becomes `ObjectUnavailable`: an intent whose bytes were
        never uploaded must be indistinguishable from an object that is not the
        caller's, or completing a guessed id tells the caller their guess named
        a real pending intent.
        """
        try:
            head = await self._bounded.head_object(object_key_hint)
        except ObjectAbsent as exc:
            raise errors.ObjectUnavailable() from exc

        verified = int(head["content_length"] or 0)
        if verified > self._max_upload_bytes:
            # The provider counted more than the bound allows. The row stays
            # pending and the cleanup lease reaps it; refusing here rather than
            # recording it is what keeps `available` meaning "within the bound
            # this deployment published".
            raise errors.InvalidRequest("uploaded object exceeds the configured limit")
        return verified

    async def finalize(self, *, owner_id: UUID, object_id: UUID, verified_bytes: int) -> int:
        """The compare-and-set. No provider call, no transaction held open.

        `owner_id` is the RE-CHECKED subject's, not the one the request started
        with. Idempotent by construction: a second identical call matches zero
        rows and the function reports the state the object already has, so a
        retried completion is a 200 rather than a conflict.
        """
        state = await self._repository.complete(
            object_id=object_id, owner_id=owner_id, verified_bytes=verified_bytes
        )
        if state is None:
            raise errors.ObjectUnavailable()
        if state != "available":
            raise errors.ObjectStateConflict(state)
        return verified_bytes

    # -- download and delete -----------------------------------------------

    async def download_url(self, *, owner_id: UUID, object_id: UUID) -> DownloadGrant:
        """Mint a short-lived GET for an object this subject owns.

        **Issuing this is an authorization decision made now, and it is not
        revoked by a later tombstone.** The residual is bounded by the TTL, and
        the documentation says so plainly rather than implying revocation.
        """
        target = await self._repository.lookup_for_download(object_id=object_id, owner_id=owner_id)
        if target is None:
            raise errors.ObjectUnavailable()
        return DownloadGrant(
            download_url=self._adapter.presign_get(target.object_key),
            expires_in=self._download_ttl_seconds,
            content_type=target.content_type,
            size_bytes=target.verified_bytes,
        )

    async def delete(self, *, owner_id: UUID, object_id: UUID) -> bool:
        """Tombstone, and answer identically whatever was there.

        The tombstone commits before any later grant can be authorized, because
        the later grant reads the state through the same filter. The provider
        DELETE is NOT done here -- it is the cleanup lease's, outside any
        transaction, at least once (ADR 0104), which is safe because
        `DeleteObject` on an absent key was measured to be a 204.

        Returns whether this call moved the object -- and **the route
        deliberately discards it**. The value is returned rather than swallowed
        here because the cleanup worker and the operator surface will both want
        it, and because a function that cannot report what it did is hard to
        test. What must not happen is a route branching on it: 204 for a moved
        object and 404 for one that was not is exactly the existence oracle the
        download path refuses to be, and it would break idempotency for the
        owner at the same time.
        """
        return await self._repository.tombstone(object_id=object_id, owner_id=owner_id)

    # -- shared ------------------------------------------------------------

    async def key_for(self, *, owner_id: UUID, object_id: UUID) -> str:
        """The stored key of an object this subject may still complete.

        Used only by completion, which needs the key to ask the provider about
        it and must not accept one from the client. Raises `ObjectUnavailable`
        rather than returning None, so a caller cannot forget to check.

        Answers for `pending` and for `available` alike, because completion is
        idempotent (STO-COMPLETE-001) and a retry arrives when the object is
        already available. Tombstoned is not answered for: completing one would
        resurrect it.
        """
        key = await self._repository.completion_key(object_id=object_id, owner_id=owner_id)
        if key is None:
            raise errors.ObjectUnavailable()
        return key

    @staticmethod
    def wrap_provider_failure(exc: StorageError) -> Exception:
        """A provider failure is never reported verbatim to a caller.

        `StorageError` carries an operation and a provider error code and no
        target, which makes it safe to LOG -- but a caller learning
        `SignatureDoesNotMatch` learns about this deployment's credential state,
        and one learning `AccessDenied` learns the token's scope. They get the
        same 404 the ownership filter gives.
        """
        return errors.ObjectUnavailable()

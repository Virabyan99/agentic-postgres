"""The R2 adapter: one frozen client, a bounded executor, and four operations.

**Every constant here was measured against a real bucket before it was written**
(Run 5, ADRs 0106 and 0107). The rig ran inside the locked ``python:3.12-slim``
digest with the locked boto3/botocore, against ``apg-session7-r2-probe``, and
each arm was paired with a control that came out the other way. What the
measurement changed, rather than confirmed, is recorded at each site -- because
this repository's defect pattern is a value that looked measured and was not,
and a constant that merely agrees with the S3 documentation is indistinguishable
from one that was checked.

**Nothing here logs a URL, a key or a credential.** A presigned URL *is* a
bearer credential (see :func:`redact`), an object key is the unguessable half of
one, and ``STO-URL-001`` is a canary scan over the application logs, the edge
log, the journal, evidence, outputs and container inspection. The adapter raises
exceptions that name an operation and a provider error code, never a target.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

#: R2 ignores the region but SigV4 signs it, so it has to be *a* value and the
#: same value on both sides. Cloudflare documents `auto`; measured working in
#: every arm of Run 5's rig.
REGION = "auto"

#: ADR 0107, and this is the constant the measurement changed.
#:
#: Both styles work against R2 -- a presigned PUT under each returned 200 with
#: the bytes actually sent. `path` is frozen because it is the only one that is
#: INVARIANT: botocore silently falls back from virtual to path when the bucket
#: name is not usable as a TLS hostname label, so declaring `virtual` yields
#: virtual only for some bucket names. The deciding input is `storage.bucket`,
#: an operator-supplied manifest value that ADR 0105 uses verbatim and the
#: schema bounds only at 3-63 characters -- so a dotted override would silently
#: change the shape of every URL this service issues.
#:
#: `auto` is refused although it resolves to `path` here today: it is a
#: behaviour rather than a choice, decided by botocore's version and the bucket
#: name together.
ADDRESSING_STYLE = "path"

#: SigV4. Named rather than defaulted because a presigned URL's query string is
#: the signature's shape, and a client that silently signed v2 would produce
#: URLs that fail at the provider rather than at construction.
SIGNATURE_VERSION = "s3v4"

#: Bounded, and small. Every call this adapter makes sits inside a request the
#: user is waiting on, so a long retry chain converts a provider blip into a
#: held connection from the pool the connection budget sizes (ADR 0099).
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 15

#: How many times a call may be sent in total, including the first.
#:
#: **This is not the number botocore's config key takes**, and the difference
#: was measured rather than read. `retries={"max_attempts": N}` resolves, at
#: client construction, to `total_max_attempts: N + 1` -- so botocore's
#: `max_attempts` means RETRIES, although the AWS documentation describes it as
#: "the maximum number of attempts". Measured across N = 1, 2, 3, 5, which all
#: resolved to 2, 3, 4, 6.
#:
#: Written as the total because that is the number with a consequence: at a
#: 15-second read timeout, the difference between 3 and 4 is fifteen seconds of
#: a request the user is waiting on, holding a connection from the pool ADR 0099
#: sized. The off-by-one was live in this file until the test read the resolved
#: client instead of the key that was set.
TOTAL_ATTEMPTS = 3

#: What to hand botocore to get :data:`TOTAL_ATTEMPTS`. Derived, never written
#: twice -- two numbers with one true relationship between them is D234's shape.
_BOTOCORE_MAX_ATTEMPTS = TOTAL_ATTEMPTS - 1

#: How many provider calls may be resident at once. Four, matching the pool
#: size, for a different reason than `BoundedHasher`'s: that bound exists
#: because each Argon2 hash holds 64 MiB and the container's limit is derived
#: from it (ADR 0082); this one exists because each call holds a thread and an
#: outbound connection, and an unbounded pool would let a slow provider grow the
#: thread count without limit. The number is not measured and says so -- the
#: memory floor for this container is still the session's open item.
PROVIDER_CONCURRENCY = 4

#: The provider error codes this adapter distinguishes, all OBSERVED in Run 5
#: rather than read from the S3 error reference:
#:
#:   PreconditionFailed    412, second write to a key presigned If-None-Match:*
#:   SignatureDoesNotMatch 403, a mutated key AND a mutated signature alike --
#:                         indistinguishable to the caller, which is the wanted
#:                         shape: it leaks nothing about which half was wrong
#:   ExpiredRequest        403, a URL used after its expiry
#:   AccessDenied          403, an operation outside the token's permission
#:   404                   HeadObject on a key that is not there
#:
#: NoSuchBucket is deliberately absent: HeadBucket on a bucket that does not
#: exist returned **403, not 404**, because a bucket-scoped token cannot
#: distinguish "absent" from "not yours". Anything reasoning about bucket
#: existence from this adapter's errors would be reasoning about the token.
PRECONDITION_FAILED = "PreconditionFailed"
SIGNATURE_MISMATCH = "SignatureDoesNotMatch"
EXPIRED = "ExpiredRequest"
ACCESS_DENIED = "AccessDenied"


class StorageError(RuntimeError):
    """A provider call failed. Carries an operation and a code, never a target.

    The message is assembled from an operation name this module chose and a
    provider error code, so it is safe to log in full. It deliberately does not
    carry the bucket, the key or the URL: "do not compile a diagnosis into an
    error message" (Session 5) has a companion here, which is "do not compile a
    credential into one".
    """

    def __init__(self, operation: str, code: str, status: int) -> None:
        super().__init__(f"{operation} failed: {code} (HTTP {status})")
        self.operation = operation
        self.code = code
        self.status = status


class ObjectAbsent(StorageError):
    """HeadObject found nothing. Distinguished because completion depends on it."""


def redact(url: str) -> str:
    """A presigned URL reduced to something safe to put in a log.

    Returns the scheme, host and path with the query string replaced by the
    sorted NAMES of its parameters. The signature, the credential scope and the
    expiry are dropped; the object key is dropped with the path.

    A presigned URL is a bearer credential with a short life -- anyone holding
    one can perform the operation it authorizes, and a tombstone does not revoke
    it. Half-redacting is worse than not logging: a URL missing only
    `X-Amz-Signature` still names the bucket, the key and the account.

    **Split by hand rather than with `urllib.parse`**, and that is a constraint
    rather than a preference. `test_the_service_never_constructs_a_network_jwks_client`
    refuses any reference to `urllib` anywhere under this service, because a
    verifier able to fetch its own keys has whatever answered the request as its
    trust anchor. `urlsplit` is pure string handling and would have been
    harmless -- but the scan is deliberately a name scan, since "an import
    nobody calls today is an import somebody calls next session", and buying an
    exemption for the safe half of a module is how the unsafe half arrives. Two
    `partition` calls cost less than the exemption would.
    """
    scheme, _, rest = url.partition("://")
    hostpath, _, query = rest.partition("?")
    host, _, _path = hostpath.partition("/")
    names = sorted({p.partition("=")[0] for p in query.split("&") if p})
    return f"{scheme}://{host}/<path> ?{{{','.join(names)}}}"


@dataclass(frozen=True, slots=True)
class StorageConfig:
    """Everything the adapter needs, resolved once at startup.

    ``endpoint`` arrives FINISHED, derived by ``naming.storage_endpoint_url``
    from the manifest's account id and jurisdiction (ADR 0106). This module
    deliberately cannot build one: an account id and a URL template here would
    be a second authority for a value the deploy already computed, which is what
    two derivations of the documentation route cost in Session 5 (D177).
    """

    endpoint: str
    bucket: str
    prefix: str
    access_key_id: str
    secret_access_key: str
    upload_url_ttl_seconds: int
    download_url_ttl_seconds: int
    max_upload_bytes: int


def _read_secret_file(variable: str, environ: dict[str, str]) -> str:
    """Read one credential half from the file the secret contract materialized.

    The value is a mounted file and never an environment variable, which is what
    keeps it out of the argument vector and out of `docker inspect` (D60). The
    error names the VARIABLE and the path, never the content -- and not the
    length either, which for a 64-character hex secret would confirm its shape.
    """
    path = environ.get(variable)
    if not path:
        raise RuntimeError(f"{variable} is required and was not set")
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"{variable}: cannot read {path}") from exc
    if not value:
        raise RuntimeError(f"{variable}: {path} is empty")
    return value


def load_config(environ: dict[str, str] | None = None) -> StorageConfig:
    """Resolve the adapter's configuration from the container's environment.

    Every setting is required and none has a default, for `settings.py`'s stated
    reason: a default would be a second authority for a value `naming.py`
    derives and the deployed document publishes, and its symptom is a service
    that starts, talks to the wrong thing and reports itself healthy.
    """
    env = dict(os.environ if environ is None else environ)

    def need(name: str) -> str:
        value = env.get(name)
        if value is None or value == "":
            # Empty and unset are one failure, because Compose's
            # `${VAR:?required}` refuses both (D178) and a service that
            # disagreed with the file that starts it would be the bug.
            raise RuntimeError(f"{name} is required and was not set")
        return value

    def need_int(name: str) -> int:
        raw = need(name)
        try:
            return int(raw)
        except ValueError as exc:
            raise RuntimeError(f"{name} must be an integer") from exc

    return StorageConfig(
        endpoint=need("APG_STORAGE_ENDPOINT"),
        bucket=need("APG_STORAGE_BUCKET"),
        prefix=need("APG_STORAGE_PREFIX"),
        access_key_id=_read_secret_file("APG_STORAGE_ACCESS_KEY_ID_FILE", env),
        secret_access_key=_read_secret_file("APG_STORAGE_SECRET_ACCESS_KEY_FILE", env),
        upload_url_ttl_seconds=need_int("APG_STORAGE_UPLOAD_URL_TTL_SECONDS"),
        download_url_ttl_seconds=need_int("APG_STORAGE_DOWNLOAD_URL_TTL_SECONDS"),
        max_upload_bytes=need_int("APG_STORAGE_MAX_UPLOAD_BYTES"),
    )


def build_client(config: StorageConfig) -> Any:
    """One low-level S3 client, with every behaviour named rather than defaulted.

    **No ambient credential chain and no IMDS lookup.** The two credential halves
    are passed explicitly, which short-circuits botocore's provider chain before
    it reaches environment variables, `~/.aws/*` or the instance metadata
    service. That matters beyond tidiness: a container whose mounted credential
    failed to materialize must FAIL, not quietly authenticate as whatever else
    the environment offers. The `session_token=None` is explicit for the same
    reason -- it says the credential is a long-lived pair, not a
    temporary-credentials triple this adapter has never measured.
    """
    return boto3.client(
        "s3",
        endpoint_url=config.endpoint,
        region_name=REGION,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        aws_session_token=None,
        config=Config(
            signature_version=SIGNATURE_VERSION,
            s3={"addressing_style": ADDRESSING_STYLE},
            retries={"max_attempts": _BOTOCORE_MAX_ATTEMPTS, "mode": "standard"},
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            read_timeout=READ_TIMEOUT_SECONDS,
        ),
    )


def _fail(operation: str, exc: ClientError) -> StorageError:
    meta = exc.response.get("ResponseMetadata", {})
    status = int(meta.get("HTTPStatusCode", 0))
    code = str(exc.response.get("Error", {}).get("Code", ""))
    if status == 404:
        return ObjectAbsent(operation, code or "404", status)
    return StorageError(operation, code or str(status), status)


class R2Adapter:
    """The four provider operations the storage surface needs, and no others.

    There is no list operation and there will not be one here. §4's cleanup plan
    is metadata-driven and never lists the bucket, because a reconciler that
    lists and deletes untracked objects can delete data a human put there to
    recover something -- and an adapter that cannot list is a stronger guarantee
    of that than a rule saying nobody should.
    """

    def __init__(self, config: StorageConfig, client: Any | None = None) -> None:
        self.config = config
        self.client = client if client is not None else build_client(config)

    def presign_put(self, key: str, *, first_write_only: bool = True) -> str:
        """A short-lived URL that authorizes exactly one PUT of one key.

        **`first_write_only` is a correctness mechanism, not a convenience**, and
        Run 5 measured all three of its parts:

        * `IfNoneMatch="*"` lands in `X-Amz-SignedHeaders`, so the condition is
          part of what the signature covers;
        * the first write returns 200 and the second returns **412
          PreconditionFailed**;
        * a caller that simply OMITS the header does not get an unconditional
          write -- it gets **403 SignatureDoesNotMatch**.

        That third arm is the one that matters. Without it the condition would be
        enforced only by client cooperation, which is no enforcement at all
        against the holder of a bearer credential. The control that a plain
        presigned PUT to the same key overwrites at 200 is what proves the 412
        came from the condition rather than from something incidental.
        """
        params: dict[str, Any] = {"Bucket": self.config.bucket, "Key": key}
        if first_write_only:
            params["IfNoneMatch"] = "*"
        return self.client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=self.config.upload_url_ttl_seconds,
            HttpMethod="PUT",
        )

    def presign_get(self, key: str) -> str:
        """A short-lived URL that authorizes one GET.

        Issuing this is an authorization decision made at issue time. It is NOT
        revoked by a later tombstone, and the documentation says so plainly
        rather than implying otherwise; the residual is bounded by the TTL, which
        is why `download_url_ttl_seconds` defaults shorter than the upload's.
        """
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.config.bucket, "Key": key},
            ExpiresIn=self.config.download_url_ttl_seconds,
            HttpMethod="GET",
        )

    def head_object(self, key: str) -> dict[str, Any]:
        """What the provider says about an uploaded object. Raises `ObjectAbsent`.

        **R2 returns no checksum of any kind**, measured: `HeadObject` on an
        object uploaded through a presigned PUT carried no `Checksum*` member, no
        `ServerSideEncryption` and no `StorageClass`. So completion cannot verify
        a provider-computed SHA-256, whatever the session plan's invariant matrix
        implies -- what is actually available is `ContentLength` and an `ETag`
        that was measured to equal the body's MD5 for a single-part PUT.

        Those are different trust levels and the caller must not confuse them:
        the length is the provider counting bytes it stored, while any
        `x-amz-meta-*` digest is a value the UPLOADER asserted about its own
        bytes. Run 6 decides what to do with that; this function reports both and
        judges neither.
        """
        try:
            response = self.client.head_object(Bucket=self.config.bucket, Key=key)
        except ClientError as exc:
            raise _fail("head_object", exc) from exc
        return {
            "content_length": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
            "etag": (response.get("ETag") or "").strip('"'),
            "metadata": dict(response.get("Metadata") or {}),
            "last_modified": response.get("LastModified"),
        }

    def delete_object(self, key: str) -> None:
        """Remove one object. Idempotent, and that is a measured claim.

        ADR 0104 makes the cleanup lease the correctness mechanism precisely
        because the provider DELETE happens outside the transaction, which means
        it may run more than once. That is only safe if deleting an absent key is
        not an error -- a property the ADR inherited from the S3 documentation and
        that nothing had checked against R2.

        Measured in Run 5: `DeleteObject` on an absent key returns **204**, byte
        for byte the same shape as deleting a key that exists, with no
        `DeleteMarker` and no `VersionId`. The control was a present key deleted
        and then `HeadObject`-ed, which returned 404 -- so the 204 on the present
        arm really did delete something, and the two 204s mean what they appear
        to mean.
        """
        try:
            self.client.delete_object(Bucket=self.config.bucket, Key=key)
        except ClientError as exc:
            raise _fail("delete_object", exc) from exc


class BoundedR2:
    """`R2Adapter`, off the event loop, with at most `concurrency` in flight.

    The same shape as `BoundedHasher` and for one of the same two reasons. The
    semaphore is released by the WORKER, not by the caller, so a client that
    disconnects mid-request cannot free a permit while the thread it started is
    still resident; and the inner future is SHIELDED, because a submission the
    executor has not yet started is the case where cancellation succeeds, the
    worker never runs, its `finally` never runs, and the permit leaks for the
    life of the process.

    That second paragraph is stated in the order the mutation battery taught
    rather than the order intuition suggests: cancelling a call that has already
    begun is harmless, and it is the QUEUED one that leaks. `BoundedHasher`'s
    docstring asserted the reverse until a battery removed its shield and every
    test stayed green.
    """

    def __init__(self, adapter: R2Adapter, concurrency: int = PROVIDER_CONCURRENCY) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self.adapter = adapter
        self.concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._in_flight = 0

    async def _run(self, function, /, *arguments):
        await self._semaphore.acquire()
        loop = asyncio.get_running_loop()
        self._in_flight += 1

        def worker():
            try:
                return function(*arguments)
            finally:
                # Scheduled onto the loop rather than released here: the
                # semaphore belongs to the loop and this runs in a thread, so
                # releasing directly would be a data race on the waiter queue.
                loop.call_soon_threadsafe(self._release)

        return await asyncio.shield(loop.run_in_executor(None, worker))

    def _release(self) -> None:
        self._in_flight -= 1
        self._semaphore.release()

    async def head_object(self, key: str) -> dict[str, Any]:
        return await self._run(self.adapter.head_object, key)

    async def delete_object(self, key: str) -> None:
        await self._run(self.adapter.delete_object, key)

    def in_flight(self) -> int:
        """How many provider calls are resident right now. Diagnostic only."""
        return self._in_flight

    def permits_available(self) -> int:
        """How many could start right now. Diagnostic only."""
        return max(0, self.concurrency - self._in_flight)

"""The R2 adapter, and the two ADRs Run 5's measurement produced.

`STO-URL-001`. Every constant asserted here was measured against a real bucket
before the adapter was written, and the tests are written so that they fail if
the *behaviour* changes rather than if a constant is renamed. Two of them exist
specifically because the obvious assertion cannot fail:

* asserting `Config.s3["addressing_style"] == "path"` would pass in exactly the
  case ADR 0107 exists to prevent, because the defect is that botocore does not
  honour the key for some bucket names. The test presigns and reads the URL.
* asserting that `presign_put` "passes IfNoneMatch" would pass against a
  signature that never covered it. The test reads `X-Amz-SignedHeaders`.

D173 and D260 are the standing reasons: a test that compares a value against
itself is green forever and measures nothing.
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest

from app.storage_client import (
    ADDRESSING_STYLE,
    REGION,
    SIGNATURE_VERSION,
    TOTAL_ATTEMPTS,
    BoundedR2,
    ObjectAbsent,
    R2Adapter,
    StorageConfig,
    StorageError,
    build_client,
    load_config,
    redact,
)

ACCOUNT = "0123456789abcdef0123456789abcdef"
ENDPOINT = f"https://{ACCOUNT}.r2.cloudflarestorage.com"


def make_config(**overrides) -> StorageConfig:
    base = {
        "endpoint": ENDPOINT,
        "bucket": "apg-alpha-dev",
        "prefix": "objects/alpha-dev/",
        "access_key_id": "a" * 32,
        "secret_access_key": "b" * 64,
        "upload_url_ttl_seconds": 900,
        "download_url_ttl_seconds": 300,
        "max_upload_bytes": 26214400,
    }
    return StorageConfig(**{**base, **overrides})


def adapter(**overrides) -> R2Adapter:
    return R2Adapter(make_config(**overrides))


# --------------------------------------------------------------------------
# ADR 0107 -- the addressing style, asserted on the emitted URL


@pytest.mark.parametrize("bucket", ["apg-alpha-dev", "apg.dotted.bucket", "a-b", "x" * 63])
def test_every_bucket_name_the_schema_admits_presigns_path_style(bucket):
    """The URL shape does not depend on the bucket name. ADR 0107.

    This is the assertion the ADR is about. Under `virtual`, botocore emits a
    virtual-hosted URL for `apg-alpha-dev` and silently falls back to path for
    `apg.dotted.bucket` -- so the same configuration would produce two shapes
    depending on a manifest value ADR 0105 uses verbatim. Under `path` there is
    one shape for every name the schema admits.

    Mutating ADDRESSING_STYLE to "virtual" turns the dotted case green and the
    plain case red, which is what makes this a measurement rather than a
    restatement of the constant.
    """
    url = adapter(bucket=bucket).presign_put("objects/alpha-dev/v1/abc")
    parts = urlsplit(url)

    assert parts.netloc == f"{ACCOUNT}.r2.cloudflarestorage.com"
    assert parts.path.startswith(f"/{bucket}/")
    assert bucket not in parts.netloc


def test_the_addressing_style_is_not_auto():
    """`auto` resolves to path today and is still refused (ADR 0107).

    It is a behaviour rather than a choice -- decided by botocore's version and
    the bucket name together -- and the lock pinning a version is not a
    substitute for stating the intent.
    """
    assert ADDRESSING_STYLE == "path"
    assert SIGNATURE_VERSION == "s3v4"
    assert REGION == "auto"


# --------------------------------------------------------------------------
# ADR 0106 -- the endpoint arrives finished


def test_the_adapter_cannot_build_an_endpoint():
    """The account id is never assembled here (ADR 0106, ADR 0002).

    A second assembly site would be a second authority for a value the deploy
    already computed -- D177's shape, where two derivations of the documentation
    route disagreed and the one commented as "kept in step" had drifted.
    """
    import app.storage_client as module

    source = module.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()

    # The literal that would appear in any hand-rolled endpoint. Its absence is
    # asserted on the source rather than by trusting the docstring, because a
    # docstring saying "we do not derive this" is what D276 found attached to a
    # value nothing derived.
    assert "r2.cloudflarestorage.com" not in text.replace("#", "")


def test_the_endpoint_is_used_verbatim():
    url = adapter().presign_put("k")
    assert url.startswith(ENDPOINT + "/")


# --------------------------------------------------------------------------
# The first-write condition


def test_the_first_write_condition_is_inside_the_signature():
    """`If-None-Match` is signed, not merely sent. Measured in Run 5.

    The arm that makes this load-bearing: a client that OMITS the header gets
    403 SignatureDoesNotMatch, not an unconditional write. A condition enforced
    only by client cooperation is no enforcement at all against the holder of a
    bearer credential, and the only thing that makes it more than cooperation is
    its presence in `X-Amz-SignedHeaders`.
    """
    url = adapter().presign_put("objects/alpha-dev/v1/abc")
    signed = parse_qs(urlsplit(url).query)["X-Amz-SignedHeaders"][0]

    assert "if-none-match" in signed.split(";")


def test_the_condition_can_be_left_off_and_then_is_not_signed():
    """The control for the test above: without it, the header is absent.

    Two fixtures that agree cannot prove a field is read (D332). This is the
    same rule applied to a flag: if both arms signed `if-none-match`, the test
    above would pass for a `presign_put` that ignored its argument.
    """
    url = adapter().presign_put("k", first_write_only=False)
    signed = parse_qs(urlsplit(url).query)["X-Amz-SignedHeaders"][0]

    assert "if-none-match" not in signed.split(";")


def test_the_two_ttls_are_read_from_the_configuration_and_are_not_the_same():
    """Upload and download TTLs are distinct values, and each is used.

    Deliberately asymmetric numbers: with 900/900 a swapped pair would be
    invisible, which is D332's mechanism exactly.
    """
    config = make_config(upload_url_ttl_seconds=601, download_url_ttl_seconds=207)
    subject = R2Adapter(config)

    put = parse_qs(urlsplit(subject.presign_put("k")).query)
    get = parse_qs(urlsplit(subject.presign_get("k")).query)

    assert put["X-Amz-Expires"] == ["601"]
    assert get["X-Amz-Expires"] == ["207"]


def test_a_presigned_get_is_a_get_and_carries_no_write_condition():
    url = adapter().presign_get("k")
    signed = parse_qs(urlsplit(url).query)["X-Amz-SignedHeaders"][0]

    assert "if-none-match" not in signed
    assert "X-Amz-Signature" in parse_qs(urlsplit(url).query)


# --------------------------------------------------------------------------
# The client's frozen configuration


def test_the_client_carries_no_ambient_credentials(monkeypatch):
    """A stray AWS credential in the environment must not be reachable.

    The container's credential arrives as two mounted files. If botocore's
    provider chain could still be consulted, a container whose materialization
    failed would authenticate as whatever the environment offered rather than
    failing -- which is D283's shape (a fake never 404s) turned into a
    credential.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ambient-must-not-win")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "ambient-must-not-win")

    client = build_client(make_config())
    frozen = client._request_signer._credentials

    assert frozen.access_key == "a" * 32
    assert frozen.secret_key == "b" * 64
    assert frozen.token is None


def test_the_client_bounds_its_retries_and_its_timeouts():
    """Each call sits inside a request the user waits on (ADR 0099's budget).

    **Asserted on the RESOLVED client, not on the key that was set**, and that
    is the whole point of this test rather than a detail of it. botocore's
    `retries={"max_attempts": N}` resolves at client construction to
    `total_max_attempts: N + 1` -- its `max_attempts` counts retries, though the
    documentation calls it attempts. A test reading back the key it just set
    would have been a tautology (D173) AND would have agreed with an adapter
    that sent four requests while claiming three.

    Measured: N = 1, 2, 3, 5 resolve to 2, 3, 4, 6.
    """
    client = build_client(make_config())
    config = client.meta.config

    assert config.retries["total_max_attempts"] == TOTAL_ATTEMPTS
    assert config.retries["mode"] == "standard"
    assert config.connect_timeout == 5
    assert config.read_timeout == 15


def test_the_attempt_budget_is_expressed_as_a_total_not_as_botocores_key():
    """The relation between the two numbers, computed rather than restated.

    Two constants with one true relationship between them is D234's shape, and
    the way it fails is that somebody edits one. This asserts the derivation.
    """
    from app import storage_client

    assert storage_client._BOTOCORE_MAX_ATTEMPTS == TOTAL_ATTEMPTS - 1


# --------------------------------------------------------------------------
# Nothing leaks


def test_redact_drops_the_signature_the_key_and_the_query_values():
    url = adapter().presign_put("objects/alpha-dev/v1/9f8e7d")
    safe = redact(url)

    assert "9f8e7d" not in safe
    assert "X-Amz-Signature=" not in safe
    assert "X-Amz-Signature" in safe  # the NAME survives; the value does not
    for value in parse_qs(urlsplit(url).query).values():
        assert value[0] not in safe


def test_a_storage_error_names_no_target():
    """An exception message is a log line. It carries an operation and a code."""
    error = StorageError("head_object", "AccessDenied", 403)
    text = str(error)

    assert "head_object" in text and "AccessDenied" in text
    assert "apg-alpha-dev" not in text
    assert "objects/" not in text


def test_object_absent_is_a_storage_error():
    """Completion distinguishes it; everything else may treat it as a failure."""
    assert issubclass(ObjectAbsent, StorageError)


# --------------------------------------------------------------------------
# Configuration loading


def test_the_credential_is_read_from_a_file_and_never_from_the_environment(tmp_path):
    """D60: a value in the environment is in `docker inspect` and the argv."""
    key_file = tmp_path / "id"
    secret_file = tmp_path / "secret"
    # Deliberately not shaped like a real credential. A 64-hex string here would
    # be indistinguishable from the genuine article to any scanner that ever
    # reads this tree, and STO-URL-001 is a canary scan.
    written_id = "id-from-file"
    written_secret = "secret-from-file"  # noqa: S105 — a marker, not a credential
    key_file.write_text(written_id + "\n", encoding="utf-8")
    secret_file.write_text(written_secret + "\n", encoding="utf-8")

    config = load_config(
        {
            "APG_STORAGE_ENDPOINT": ENDPOINT,
            "APG_STORAGE_BUCKET": "apg-alpha-dev",
            "APG_STORAGE_PREFIX": "objects/alpha-dev/",
            "APG_STORAGE_ACCESS_KEY_ID_FILE": str(key_file),
            "APG_STORAGE_SECRET_ACCESS_KEY_FILE": str(secret_file),
            "APG_STORAGE_UPLOAD_URL_TTL_SECONDS": "900",
            "APG_STORAGE_DOWNLOAD_URL_TTL_SECONDS": "300",
            "APG_STORAGE_MAX_UPLOAD_BYTES": "26214400",
        }
    )

    # Distinct values, and each asserted against its own: with one string in
    # both files, a loader that read the same file twice would pass.
    assert config.access_key_id == written_id
    assert config.secret_access_key == written_secret


@pytest.mark.parametrize(
    "missing",
    [
        "APG_STORAGE_ENDPOINT",
        "APG_STORAGE_BUCKET",
        "APG_STORAGE_PREFIX",
        "APG_STORAGE_UPLOAD_URL_TTL_SECONDS",
        "APG_STORAGE_DOWNLOAD_URL_TTL_SECONDS",
        "APG_STORAGE_MAX_UPLOAD_BYTES",
    ],
)
def test_every_setting_is_required_and_an_empty_value_is_a_missing_one(missing, tmp_path):
    """Compose refuses an empty value as firmly as an unset one (D178)."""
    key_file = tmp_path / "id"
    secret_file = tmp_path / "secret"
    key_file.write_text("k", encoding="utf-8")
    secret_file.write_text("s", encoding="utf-8")

    env = {
        "APG_STORAGE_ENDPOINT": ENDPOINT,
        "APG_STORAGE_BUCKET": "apg-alpha-dev",
        "APG_STORAGE_PREFIX": "objects/alpha-dev/",
        "APG_STORAGE_ACCESS_KEY_ID_FILE": str(key_file),
        "APG_STORAGE_SECRET_ACCESS_KEY_FILE": str(secret_file),
        "APG_STORAGE_UPLOAD_URL_TTL_SECONDS": "900",
        "APG_STORAGE_DOWNLOAD_URL_TTL_SECONDS": "300",
        "APG_STORAGE_MAX_UPLOAD_BYTES": "26214400",
    }
    env[missing] = ""

    with pytest.raises(RuntimeError, match=missing):
        load_config(env)


def test_an_unreadable_credential_file_names_the_variable_and_not_the_content(tmp_path):
    env = {
        "APG_STORAGE_ENDPOINT": ENDPOINT,
        "APG_STORAGE_BUCKET": "b",
        "APG_STORAGE_PREFIX": "p/",
        "APG_STORAGE_ACCESS_KEY_ID_FILE": str(tmp_path / "absent"),
        "APG_STORAGE_SECRET_ACCESS_KEY_FILE": str(tmp_path / "absent"),
        "APG_STORAGE_UPLOAD_URL_TTL_SECONDS": "900",
        "APG_STORAGE_DOWNLOAD_URL_TTL_SECONDS": "300",
        "APG_STORAGE_MAX_UPLOAD_BYTES": "1",
    }
    with pytest.raises(RuntimeError, match="APG_STORAGE_ACCESS_KEY_ID_FILE"):
        load_config(env)


# --------------------------------------------------------------------------
# The bounded executor


def test_the_executor_admits_only_its_concurrency_at_once():
    started = asyncio.Event()
    release = asyncio.Event()
    loop_holder: dict = {}

    class Slow:
        def head_object(self, key):
            loop_holder["loop"].call_soon_threadsafe(started.set)
            # Block until the test says otherwise, so the permit is held.
            while not loop_holder["go"]:
                pass
            return {"key": key}

    async def scenario():
        loop_holder["loop"] = asyncio.get_running_loop()
        loop_holder["go"] = False
        bounded = BoundedR2(Slow(), concurrency=1)

        first = asyncio.create_task(bounded.head_object("a"))
        await started.wait()
        assert bounded.in_flight() == 1
        assert bounded.permits_available() == 0

        second = asyncio.create_task(bounded.head_object("b"))
        await asyncio.sleep(0.05)
        assert not second.done(), "the second call started while the first held the permit"

        loop_holder["go"] = True
        await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
        assert bounded.in_flight() == 0

    asyncio.run(scenario())
    assert not release.is_set()


def test_a_cancelled_caller_does_not_leak_its_permit():
    """What `asyncio.shield` is actually for, and the obvious reasoning has it
    backwards.

    Cancelling a caller whose call has already BEGUN is harmless either way:
    `Future.cancel()` on started work returns False and the worker's `finally`
    runs. The leak is the opposite case -- work submitted to the executor and
    not yet started, where cancellation succeeds, the worker never runs, and the
    permit is never returned. The service's effective concurrency then falls by
    one for the life of the process.

    **Reaching that case needs a thread pool SMALLER than `concurrency`.** The
    first draft of this test used `concurrency=1` and blocked the second caller
    on the semaphore rather than on the executor -- so nothing was ever queued,
    and a mutation removing the shield left it green. That is D260 exactly,
    reproduced in a test written to prevent it, and caught only because the
    battery ran. The same mistake, in the same shape, one file over from where
    `BoundedHasher` records having made it first.
    """
    from concurrent.futures import ThreadPoolExecutor

    class Blocking:
        def __init__(self) -> None:
            self.release = False

        def head_object(self, key):
            while not self.release:
                pass
            return {"key": key}

    adapter = Blocking()
    bounded = BoundedR2(adapter, concurrency=2)

    async def drive() -> int:
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as single:
            loop.set_default_executor(single)

            running = asyncio.create_task(bounded.head_object("holds"))
            while bounded.in_flight() < 1:
                await asyncio.sleep(0.001)

            # Takes the second permit, and QUEUES -- the single thread is busy.
            queued = asyncio.create_task(bounded.head_object("queued"))
            while bounded.in_flight() < 2:
                await asyncio.sleep(0.001)

            queued.cancel()
            with pytest.raises(asyncio.CancelledError):
                await queued

            adapter.release = True
            await running

            for _ in range(500):
                if bounded.in_flight() == 0:
                    break
                await asyncio.sleep(0.01)
            return bounded.in_flight()

    assert asyncio.run(drive()) == 0, (
        "a cancelled submission never ran its release, so the permit is leaked and the "
        "service's provider concurrency is permanently one lower than it reports"
    )


def test_the_executor_refuses_a_concurrency_below_one():
    with pytest.raises(ValueError):
        BoundedR2(object(), concurrency=0)

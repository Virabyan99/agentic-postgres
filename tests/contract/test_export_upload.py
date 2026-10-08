"""A project export's upload, inside the storage container (ADR 0259, D2164, D2190).

`python -m app.export_upload --operation <uuid>` reads the storage settings the
storage lifespan reads, writes stdin ONCE with the adapter's `put_object`, and
prints one presigned GET valid 900 s. Offline: the adapter's own boto client
with botocore's `Stubber` on the write (nothing reaches a provider) and the URL
signed locally, as `test_storage_client.py` reads its URLs. The live write and
the expiry are measured on the host (Run 12; control: a URL past 900 s -> 403).
"""

from __future__ import annotations

import importlib.util
import io
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from botocore.stub import Stubber

from agentic_postgres import REPO_ROOT
from app import export_upload, storage_client
from app.storage_client import R2Adapter

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

OPERATION = "6f1c2a4e-1b7d-4d0e-9a51-0c3f8e2d7b10"
ARCHIVE = b"PGDMP\x01 the customer's schemas"
PREFIX = "objects/slot1-dev/"


@pytest.fixture
def environ(tmp_path: Path) -> dict[str, str]:
    """The storage container's environment: settings, and the two mounted
    credential halves as files."""
    key_id, secret = tmp_path / "key-id", tmp_path / "secret"
    key_id.write_text("0123456789abcdef0123456789abcdef\n", "utf-8")
    secret.write_text("f" * 64 + "\n", "utf-8")
    return {
        "APP_MODE": "storage",
        "APG_STORAGE_ENDPOINT": "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
        "APG_STORAGE_BUCKET": "apg-slot1-dev-storage",
        "APG_STORAGE_PREFIX": PREFIX,
        "APG_STORAGE_ACCESS_KEY_ID_FILE": str(key_id),
        "APG_STORAGE_SECRET_ACCESS_KEY_FILE": str(secret),
        "APG_STORAGE_UPLOAD_URL_TTL_SECONDS": "300",
        "APG_STORAGE_DOWNLOAD_URL_TTL_SECONDS": "300",
        "APG_STORAGE_MAX_UPLOAD_BYTES": "1048576",
    }


def _adapter(environ: dict[str, str]) -> tuple[R2Adapter, Stubber]:
    adapter = R2Adapter(storage_client.load_config(environ))
    return adapter, Stubber(adapter.client)


def _run(environ: dict[str, str], adapter: Any, *, body: bytes = ARCHIVE) -> int:
    return export_upload.main(
        ["--operation", OPERATION], stdin=io.BytesIO(body), environ=environ, adapter=adapter
    )


def test_the_export_is_written_once_and_signed_for_900_seconds(
    environ: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    """One `put_object` of exactly the archive, first-write-only, under
    `<prefix>exports/<operation>.dump`; then ONE line: a GET signed for 900 s
    on that key."""
    adapter, stubber = _adapter(environ)
    key = f"{PREFIX}exports/{OPERATION}.dump"
    stubber.add_response(
        "put_object",
        {},
        {"Bucket": "apg-slot1-dev-storage", "Key": key, "Body": ARCHIVE, "IfNoneMatch": "*"},
    )
    with stubber:
        assert _run(environ, adapter) == 0
        stubber.assert_no_pending_responses()
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    url = urlsplit(lines[0])
    assert url.path.endswith(f"/apg-slot1-dev-storage/{key}")
    query = parse_qs(url.query)
    assert query["X-Amz-Expires"] == ["900"]
    assert "X-Amz-Signature" in query


def test_a_named_expiry_is_bounded_at_900_seconds(environ: dict[str, str]) -> None:
    """D2190: a caller may name 1 to 900 seconds; anything else is refused before
    anything is signed. Absent, the configured TTL (the storage API's path)."""
    adapter, _ = _adapter(environ)
    for refused in (901, 3600, 0, -1, True):
        with pytest.raises(ValueError):
            adapter.presign_get("k", expires_in=refused)
    assert parse_qs(urlsplit(adapter.presign_get("k")).query)["X-Amz-Expires"] == ["300"]
    assert parse_qs(urlsplit(adapter.presign_get("k", expires_in=900)).query)["X-Amz-Expires"] == [
        "900"
    ]
    assert export_upload.EXPORT_URL_SECONDS == storage_client.LONGEST_NAMED_EXPIRY_SECONDS


def test_a_second_write_is_refused_and_signs_nothing(
    environ: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    """The provider's 412 on a key already written is exit 5 with no URL."""
    adapter, stubber = _adapter(environ)
    stubber.add_client_error(
        "put_object", service_error_code="PreconditionFailed", http_status_code=412
    )
    with stubber:
        assert _run(environ, adapter) == 5
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "put_object failed: PreconditionFailed (HTTP 412)" in captured.err


def test_it_runs_only_as_the_storage_mode_and_only_on_an_archive(
    environ: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 outside the storage container's mode; 2 for an empty archive or
    an operation id that is not one. Nothing is written in any of them."""
    adapter, stubber = _adapter(environ)
    with stubber:
        assert _run({**environ, "APP_MODE": "auth"}, adapter) == 3
        assert _run(environ, adapter, body=b"") == 2
        assert (
            export_upload.main(
                ["--operation", "../x"], stdin=io.BytesIO(ARCHIVE), environ=environ, adapter=adapter
            )
            == 2
        )
    assert capsys.readouterr().out == ""
    assert export_upload.export_key(PREFIX, OPERATION.upper()) == (
        f"{PREFIX}exports/{uuid.UUID(OPERATION)}.dump"
    )


def test_the_reconciler_and_the_container_agree_on_the_url_life() -> None:
    """The result's `expires_at` is computed by the reconciler from its own
    constant; the URL's lifetime is the container's."""
    spec = importlib.util.spec_from_file_location(
        "apg_reconciler_export", REPO_ROOT / "bin" / "reconciler.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.EXPORT_URL_SECONDS == export_upload.EXPORT_URL_SECONDS == 900

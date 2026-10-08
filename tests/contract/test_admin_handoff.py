"""The first administrator, handed over by hash, on a real project cluster (ADR 0260, D2163).

OPN-DISPATCH-001's handoff half, rig 38c kept as a proof. The cluster, the
release set, the bootstrapped administrator and the auth app in-process are
`test_auth_endpoints.py`'s own fixtures; what is proved here is the
RECONCILER's half -- its own `database_call` and the SQL in
`reconciler_dispatch`, as the superuser in the project's database:

1. the administrator `auth-admin bootstrap` created is found by username
   (`ADMIN_ID_SQL`);
2. a reset is opened for them, by them, keyed by `sha256(T)`, for 24 hours
   (`OPEN_HANDOFF_SQL`) -- T itself never reaches the reconciler or the control
   plane;
3. the member presents T at `/auth/reset-password` and chooses the password.

Controls: a wrong T, the hash presented as the token, and T a second time are
each refused; the bootstrap password no longer logs in once T was consumed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import secrets
import uuid
from typing import Any

import pytest
from test_auth_endpoints import (  # noqa: F401 -- the module's fixtures, reused
    PASSPHRASE,
    administrator,
    cluster,
    drive,
    environment,
    signing_key,
)

from agentic_postgres import REPO_ROOT, reconciler_dispatch

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]


def _reconciler() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_reconciler_handoff", REPO_ROOT / "bin" / "reconciler.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _login(call: Any, password: str) -> Any:
    return call(
        "POST", "/auth/login", content=json.dumps({"username": "ada", "password": password})
    )


def _consume(call: Any, token: str, password: str) -> Any:
    return call(
        "POST",
        "/auth/reset-password",
        content=json.dumps({"reset_token": token, "password": password}),
    )


def test_the_administrator_is_handed_over_by_the_hash_of_a_token(
    cluster: dict[str, Any],  # noqa: F811
    administrator: str,  # noqa: F811
    drive: Any,  # noqa: F811
) -> None:
    reconciler = _reconciler()
    container, database = cluster["cluster"].name, cluster["database"]
    assert _login(drive, PASSPHRASE).status_code == 200, "the bootstrap password, before"

    user = reconciler.database_call(
        container, database, reconciler_dispatch.ADMIN_ID_SQL, {"username": "ada"}
    )
    assert user == administrator.strip()

    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    reset = reconciler.database_call(
        container, database, reconciler_dispatch.OPEN_HANDOFF_SQL, {"user": user, "hash": digest}
    )
    assert uuid.UUID(reset)
    stored = cluster["cluster"].psql(
        "SELECT token_hash = '" + digest + "', issued_by = user_id, "
        "expires_at > now() + interval '23 hours' "
        f"FROM app_private.password_resets WHERE id = '{reset}'"
    )
    assert stored == "t|t|t"

    chosen = "the member's own " + secrets.token_hex(8)
    assert _consume(drive, secrets.token_urlsafe(32), chosen).status_code == 401, "a wrong T"
    assert _consume(drive, digest, chosen).status_code == 401, "the hash is not the token"
    assert _consume(drive, token, chosen).status_code == 200
    assert _login(drive, chosen).status_code == 200
    assert _login(drive, PASSPHRASE).status_code == 401, "the bootstrap password, after"
    assert _consume(drive, token, chosen + "x").status_code == 401, "T a second time"

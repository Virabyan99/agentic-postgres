"""The human endpoints, driven against a real cluster with the real migrations.

`API-AUTH-001`, `API-ADMIN-001` and `SEC-BOOT-001`, offline.

**Not a mock.** The cluster is the locked image, the schema is the twelve
rendered migrations applied in order, and the service is the same `create_app`
the container runs -- reached over ASGI rather than over a socket, which is the
only part that is not the product. ADR 0065 is the standing warning and it has
arrived five times: a rig is a second configuration of the product, so this one
configures as little as it can.

What the rig does supply is what the *bootstrap plane* supplies in production
and this run does not build: the database, the `extensions` schema, and
`auth_service`'s `LOGIN` and password. D246 deferred that credential to the run
that ships the compose service, and Run 7 shipped the service with the role
still `NOLOGIN`.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agentic_postgres import REPO_ROOT, migrations

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

PASSPHRASE = "a-correct-horse-battery-staple"  # noqa: S105 -- a fixture, hashed and verified
ADMIN_SCOPES = ["admin_users:read", "admin_users:write", "notes:read"]


def _lock() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            name, _, value = line.partition("=")
            values[name] = value
    return values


def _docker(*arguments: str, stdin: str | None = None, timeout: int = 300):
    return subprocess.run(
        ["docker", *arguments],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


class Cluster:
    """A throwaway cluster with the released schema applied."""

    def __init__(self, name: str, port: int, database: str) -> None:
        self.name = name
        self.port = port
        self.database = database

    def psql(self, statement: str, *, database: str | None = None) -> str:
        result = _docker(
            "exec",
            "-i",
            self.name,
            "psql",
            "-qtA",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            database or self.database,
            "-c",
            statement,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()


@pytest.fixture(scope="module")
def cluster(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """The locked image, the twelve migrations, and one bootstrapped administrator."""
    lock = _lock()
    suffix = secrets.token_hex(4)
    name = f"apg-auth-endpoints-{suffix}"
    port = 55400 + (int(suffix, 16) % 120)

    started = _docker(
        "run",
        "-d",
        "--name",
        name,
        "-e",
        f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
        "-p",
        f"{port}:5432",
        lock["POSTGRES_IMAGE"],
    )
    if started.returncode != 0:
        pytest.skip(f"cannot start the locked cluster: {started.stderr.strip()[:200]}")

    try:
        # Two consecutive successes: the initdb server answers once and goes
        # away, and a rig that took the first answer would race it.
        rounds = 0
        for _ in range(90):
            probe = _docker("exec", name, "pg_isready", "-U", "postgres", timeout=30)
            rounds = rounds + 1 if probe.returncode == 0 else 0
            if rounds >= 2:
                break
            time.sleep(1)
        assert rounds >= 2, "the cluster never became ready"

        document = json.loads(
            (REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json").read_text("utf-8")
        )
        roles = document["database"]["roles"]
        owner = roles["object_owner"]
        auth_role = roles["auth_service"]
        auth_password = secrets.token_hex(24)
        database = "apgauth"

        statements = [f'CREATE ROLE "{role}" NOLOGIN;' for role in sorted(roles.values())]
        result = _docker(
            "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
            stdin="\n".join(statements),
        )  # fmt: skip
        assert result.returncode == 0, result.stderr

        cluster = Cluster(name, port, database)
        cluster.psql(f'CREATE DATABASE {database} OWNER "{owner}"', database="postgres")
        cluster.psql(f'CREATE SCHEMA extensions AUTHORIZATION "{owner}"')

        manifest = migrations.load_manifest()
        for entry in manifest["migrations"]:
            payload = migrations.render_migration(entry, manifest, document)
            up = payload.split("-- migrate:down", 1)[0].replace("-- migrate:up", "", 1)
            applied = _docker(
                "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-d", database, "-1",
                stdin=up,
            )  # fmt: skip
            assert applied.returncode == 0, f"{entry['name']}: {applied.stderr}"

        # S608 flags the interpolation. `database` is a constant this fixture
        # chose a few lines above; nothing here comes from outside the test.
        bind_identity = (
            "INSERT INTO app_private.project_identity "  # noqa: S608
            "(project_key, database_name, compose_project_name, instance_uuid) "
            f"VALUES ('fixture-alpha-dev', '{database}', 'apg-fixture-alpha-dev', "
            "gen_random_uuid())"
        )
        cluster.psql(bind_identity)

        # What the bootstrap plane does in production (D102, D246).
        cluster.psql(
            f"ALTER ROLE \"{auth_role}\" LOGIN PASSWORD '{auth_password}'", database="postgres"
        )

        yield {
            "cluster": cluster,
            "document": document,
            "roles": roles,
            "owner": owner,
            "auth_role": auth_role,
            "auth_password": auth_password,
            "port": port,
            "database": database,
            "work": tmp_path_factory.mktemp("auth-endpoints"),
        }
    finally:
        _docker("rm", "-f", name, timeout=120)


@pytest.fixture(scope="module")
def signing_key(cluster: dict[str, Any]) -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = cluster["work"] / "signing.pem"
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


@pytest.fixture(scope="module")
def administrator(cluster: dict[str, Any]) -> str:
    """One administrator, created the way `bin/auth-admin.sh` creates it.

    Through `auth_bootstrap_administrator`, as the object owner, over a direct
    connection -- not through the service, which is not granted that function.
    """
    from app.hashing import Hasher

    hashed = Hasher().hash(PASSPHRASE)
    scopes = ",".join(f"'{scope}'" for scope in ADMIN_SCOPES)
    return cluster["cluster"].psql(
        f'SET ROLE "{cluster["owner"]}"; '
        "SELECT app_private.auth_bootstrap_administrator("
        f"'ada', 'Ada Lovelace', '{cluster['roles']['project_admin']}', "
        f"ARRAY[{scopes}]::text[], '{hashed}')"
    )


@pytest.fixture(scope="module")
def environment(cluster: dict[str, Any], signing_key: Path) -> dict[str, str]:
    document = cluster["document"]
    role_names = {
        suffix: cluster["roles"][suffix]
        for suffix in ("anon", "authenticated", "agent_reader", "agent_writer", "project_admin")
    }
    passfile = cluster["work"] / "pgpass"
    passfile.write_text(f"*:*:*:*:{cluster['auth_password']}\n", encoding="utf-8")
    passfile.chmod(0o600)
    return {
        "APG_PROJECT_KEY": "fixture-alpha-dev",
        "APG_PROJECT_ENVIRONMENT": "dev",
        "APG_JWT_ISSUER": document["jwt"]["issuer"],
        "APG_JWT_AUDIENCE": document["jwt"]["audience"],
        "APG_DATABASE_HOST": "127.0.0.1",
        "APG_DATABASE_PORT": str(cluster["port"]),
        "APG_DATABASE_NAME": cluster["database"],
        "APG_DATABASE_ROLE": cluster["auth_role"],
        "APG_DATABASE_PASSFILE": str(passfile),
        "APG_POOL_SIZE": "2",
        "APG_SIGNING_KEY_FILE": str(signing_key),
        "APG_LISTEN_PORT": "8080",
        "APG_ROLE_NAMES": json.dumps(role_names, separators=(",", ":"), sort_keys=True),
    }


@pytest.fixture(scope="module")
def drive(environment: dict[str, str], administrator: str) -> Any:
    """Returns `call(method, path, **kwargs) -> Response`, over one live app."""
    import asyncio
    import os
    from contextlib import asynccontextmanager

    from app import main as main_module

    del administrator

    previous = dict(os.environ)
    os.environ.update(environment)
    application = main_module.create_app()

    @asynccontextmanager
    async def started() -> Any:
        # `router.lifespan_context` is what uvicorn calls; using it here means
        # the pool and the service are built by the same code path the
        # container runs, rather than by the test assembling them.
        async with application.router.lifespan_context(application):
            yield

    loop = asyncio.new_event_loop()
    context = started()
    loop.run_until_complete(context.__aenter__())

    def call(method: str, path: str, **kwargs: Any) -> httpx.Response:
        async def run() -> httpx.Response:
            transport = httpx.ASGITransport(app=application)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://auth.invalid"
            ) as http:
                return await http.request(method, path, **kwargs)

        return loop.run_until_complete(run())

    try:
        yield call
    finally:
        loop.run_until_complete(context.__aexit__(None, None, None))
        loop.close()
        os.environ.clear()
        os.environ.update(previous)


def _login(drive: Any, username: str = "ada", password: str = PASSPHRASE) -> httpx.Response:
    return drive("POST", "/auth/login", content=json.dumps({
        "username": username, "password": password,
    }))  # fmt: skip


# ---------------------------------------------------------------------------
# API-AUTH-001
# ---------------------------------------------------------------------------


def test_login_issues_a_token_that_verifies_against_the_published_jwks(drive: Any) -> None:
    response = _login(drive)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "Bearer"  # noqa: S105 -- RFC 6750 scheme name
    assert response.headers["cache-control"] == "no-store"

    published = drive("GET", "/auth/jwks.json").json()
    assert [key["kid"] for key in published["keys"]]

    import jwt

    header = jwt.get_unverified_header(body["access_token"])
    assert header["kid"] == published["keys"][0]["kid"]
    assert header["alg"] == "RS256"

    claims = jwt.decode(
        body["access_token"],
        jwt.PyJWK.from_dict(published["keys"][0]).key,
        algorithms=["RS256"],
        audience=claims_audience(drive),
        options={"verify_iss": False},
    )
    assert claims["token_use"] == "access"  # noqa: S105 -- a claim value
    assert claims["scope"] == sorted(ADMIN_SCOPES)
    assert claims["exp"] - claims["iat"] == 900


def claims_audience(drive: Any) -> str:
    """The audience the service was configured with, read back from a token."""
    import jwt

    token = _login(drive).json()["access_token"]
    return jwt.decode(token, options={"verify_signature": False})["aud"]


@pytest.mark.parametrize(
    ("username", "password", "why"),
    [
        ("nobody", PASSPHRASE, "unknown subject"),
        ("ada", "wrong-" + PASSPHRASE, "wrong password"),
        ("ADA", "wrong-" + PASSPHRASE, "wrong password, normalised username"),
    ],
)
def test_every_authentication_failure_is_the_same_response(
    drive: Any, username: str, password: str, why: str
) -> None:
    """Same status, same bytes, same header. `why` is for the reader only."""
    response = drive("POST", "/auth/login", content=json.dumps({
        "username": username, "password": password,
    }))  # fmt: skip
    assert response.status_code == 401
    assert response.json() == {"error": "authentication_failed"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_username_is_matched_after_normalisation(drive: Any) -> None:
    """`ADA` is `ada`, as the unique index already says it is."""
    assert _login(drive, username="ADA").status_code == 200


def test_me_reflects_current_state(drive: Any) -> None:
    token = _login(drive).json()["access_token"]
    response = drive("GET", "/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["username"] == "ada"
    assert body["scopes"] == sorted(ADMIN_SCOPES)
    assert body["status"] == "active"


def test_me_refuses_a_request_with_no_token(drive: Any) -> None:
    assert drive("GET", "/auth/me").status_code == 401


def test_the_jwks_carries_no_private_material(drive: Any) -> None:
    document = drive("GET", "/auth/jwks.json").json()
    for key in document["keys"]:
        assert set(key) & {"d", "p", "q", "dp", "dq", "qi"} == set()
        assert key["kty"] == "RSA"


# ---------------------------------------------------------------------------
# API-ADMIN-001 and the lifecycle
# ---------------------------------------------------------------------------


def test_an_administrator_can_create_a_subject_and_it_can_log_in(drive: Any) -> None:
    token = _login(drive).json()["access_token"]
    created = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        content=json.dumps(
            {
                "username": "grace",
                "display_name": "Grace Hopper",
                "role": "authenticated",
                "scopes": ["notes:read", "notes:write"],
                "password": "another-correct-horse-passphrase",
            }
        ),
    )
    assert created.status_code == 201, created.text

    logged_in = _login(drive, "grace", "another-correct-horse-passphrase")
    assert logged_in.status_code == 200, logged_in.text


def test_a_client_may_not_name_a_scope_outside_the_roles_ceiling(drive: Any) -> None:
    """ADR 0079's ceiling, enforced by the issuer rather than by the database."""
    token = _login(drive).json()["access_token"]
    response = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        content=json.dumps(
            {
                "username": "over-reach",
                "display_name": "Over Reach",
                "role": "authenticated",
                "scopes": ["notes:read", "admin_users:write"],
                "password": "yet-another-good-passphrase",
            }
        ),
    )
    assert response.status_code == 422, response.text
    assert "admin_users:write" in response.json()["message"]


def test_a_disabled_subject_cannot_log_in_and_looks_like_a_wrong_password(drive: Any) -> None:
    token = _login(drive).json()["access_token"]
    listed = drive("GET", "/admin/users", headers={"Authorization": f"Bearer {token}"})
    target = next(u for u in listed.json()["users"] if u["username"] == "grace")

    changed = drive(
        "PATCH",
        f"/admin/users/{target['user_id']}",
        headers={"Authorization": f"Bearer {token}"},
        content=json.dumps({"status": "disabled"}),
    )
    assert changed.status_code == 200, changed.text

    refused = _login(drive, "grace", "another-correct-horse-passphrase")
    assert refused.status_code == 401
    assert refused.json() == {"error": "authentication_failed"}


def test_a_password_change_invalidates_a_token_issued_before_it(drive: Any) -> None:
    """SEC-REV-001's mechanism, on the one path Run 8 builds.

    The token is still signed, still unexpired and still for the right
    audience. What refuses it is `credential_version`, compared against current
    state inside the request.
    """
    admin = _login(drive).json()["access_token"]
    created = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps(
            {
                "username": "reset-me",
                "display_name": "Reset Me",
                "role": "authenticated",
                "scopes": ["notes:read"],
                "password": "the-first-good-passphrase",
            }
        ),
    )
    user_id = created.json()["user_id"]

    theirs = _login(drive, "reset-me", "the-first-good-passphrase").json()["access_token"]
    assert (
        drive("GET", "/auth/me", headers={"Authorization": f"Bearer {theirs}"}).status_code == 200
    )

    drive(
        "PATCH",
        f"/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps({"password": "the-second-good-passphrase"}),
    )

    after = drive("GET", "/auth/me", headers={"Authorization": f"Bearer {theirs}"})
    assert after.status_code == 401, "a token issued before the reset still worked"


def test_a_scope_change_invalidates_a_token_issued_before_it(drive: Any) -> None:
    admin = _login(drive).json()["access_token"]
    created = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps(
            {
                "username": "regrade-me",
                "display_name": "Regrade Me",
                "role": "authenticated",
                "scopes": ["notes:read"],
                "password": "a-perfectly-fine-passphrase",
            }
        ),
    )
    user_id = created.json()["user_id"]
    theirs = _login(drive, "regrade-me", "a-perfectly-fine-passphrase").json()["access_token"]

    drive(
        "PATCH",
        f"/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps({"role": "authenticated", "scopes": ["notes:read", "notes:write"]}),
    )

    assert (
        drive("GET", "/auth/me", headers={"Authorization": f"Bearer {theirs}"}).status_code == 401
    )


def test_a_re_enabled_subject_cannot_reuse_a_token_issued_before_the_disable(
    drive: Any,
) -> None:
    """Non-resurrection, and the only test that isolates `authz_version`.

    Found by mutation: removing the `authz_version` comparison altogether left
    `test_a_scope_change_invalidates_a_token_issued_before_it` **green**,
    because the scope-list comparison two lines below catches a scope change
    too. That test therefore proved a redundant guard, not the one it named.

    This is the case no other check can cover. After disable then re-enable the
    subject's role, scopes and status are all *identical* to what the token
    carries -- the only thing that moved is `authz_version`, twice, because
    `auth_set_status` increments on every call rather than on a transition. So
    a token issued before the disable is refused, and nothing but the version
    comparison can refuse it.
    """
    admin = _login(drive).json()["access_token"]
    created = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps(
            {
                "username": "resurrect-me",
                "display_name": "Resurrect Me",
                "role": "authenticated",
                "scopes": ["notes:read"],
                "password": "an-entirely-serviceable-passphrase",
            }
        ),
    )
    user_id = created.json()["user_id"]
    theirs = _login(drive, "resurrect-me", "an-entirely-serviceable-passphrase").json()[
        "access_token"
    ]
    assert (
        drive("GET", "/auth/me", headers={"Authorization": f"Bearer {theirs}"}).status_code == 200
    )

    for status in ("disabled", "active"):
        changed = drive(
            "PATCH",
            f"/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {admin}"},
            content=json.dumps({"status": status}),
        )
        assert changed.status_code == 200, changed.text

    # Everything the token asserts is true again. Only the version moved.
    current = drive("GET", "/admin/users", headers={"Authorization": f"Bearer {admin}"})
    subject = next(u for u in current.json()["users"] if u["username"] == "resurrect-me")
    assert subject["status"] == "active"
    assert subject["scopes"] == ["notes:read"]

    import jwt as pyjwt

    carried = pyjwt.decode(theirs, options={"verify_signature": False})
    assert carried["scope"] == subject["scopes"], "the scope check would catch this instead"
    assert carried["role"] == subject["role"], "the role check would catch this instead"
    assert carried["authz_version"] != subject["authz_version"]

    after = drive("GET", "/auth/me", headers={"Authorization": f"Bearer {theirs}"})
    assert after.status_code == 401, (
        "a token issued before the disable was accepted after the re-enable; "
        "authz_version is what refuses it and nothing else can"
    )


def test_a_subject_without_the_scope_is_refused_though_it_holds_the_role(drive: Any) -> None:
    """API-ADMIN-001, stated exactly.

    This subject IS a `project_admin`. It holds no `admin_users:write`, and that
    is the whole requirement: a route that checked the role would serve it.
    """
    admin = _login(drive).json()["access_token"]
    created = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps(
            {
                "username": "toothless-admin",
                "display_name": "Toothless Admin",
                "role": "project_admin",
                "scopes": ["notes:read"],
                "password": "a-thoroughly-unguessable-phrase",
            }
        ),
    )
    assert created.status_code == 201, created.text

    theirs = _login(drive, "toothless-admin", "a-thoroughly-unguessable-phrase").json()
    response = drive(
        "GET", "/admin/users", headers={"Authorization": f"Bearer {theirs['access_token']}"}
    )
    assert response.status_code == 403
    assert response.json() == {"error": "authorization_failed"}


def test_an_unauthenticated_caller_cannot_reach_the_admin_surface(drive: Any) -> None:
    assert drive("GET", "/admin/users").status_code == 401
    assert drive("POST", "/admin/users", content="{}").status_code == 401


# ---------------------------------------------------------------------------
# API-AUTH-002, over the wire rather than in a unit
# ---------------------------------------------------------------------------


def test_a_duplicate_member_in_the_login_body_is_refused(drive: Any) -> None:
    """The measurement that makes `strict_json` load-bearing, end to end.

    Starlette would resolve this to `root` before pydantic saw it, so a service
    using FastAPI's own body binding would authenticate the second value while
    any log written from the first named the first.
    """
    response = drive(
        "POST",
        "/auth/login",
        content='{"username": "ada", "username": "root", "password": "x"}',
    )
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


def test_an_unknown_member_in_the_login_body_is_refused(drive: Any) -> None:
    """A client naming its own role gets an error, not a silent discard."""
    response = drive(
        "POST",
        "/auth/login",
        content=json.dumps({"username": "ada", "password": PASSPHRASE, "role": "project_admin"}),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("body", ["[]", '"a string"', "42", "null", ""])
def test_a_non_object_login_body_is_refused(drive: Any, body: str) -> None:
    assert drive("POST", "/auth/login", content=body).status_code == 422


def test_an_oversized_bearer_token_is_refused_without_being_parsed(drive: Any) -> None:
    response = drive("GET", "/auth/me", headers={"Authorization": "Bearer " + "A" * 20000})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# SEC-BOOT-001
# ---------------------------------------------------------------------------


def test_the_service_cannot_bootstrap_an_administrator(cluster: dict[str, Any]) -> None:
    """No public bootstrap endpoint, and no private one either.

    The service's role is not granted the function, so even a route that called
    it would be refused by the database. That is the property rather than the
    absence of a route, because a route can be added.
    """
    result = _docker(
        "exec", "-i", cluster["cluster"].name, "psql", "-qtA", "-U", "postgres",
        "-d", cluster["database"], "-c",
        f'SET ROLE "{cluster["auth_role"]}"; '
        "SELECT app_private.auth_bootstrap_administrator('x','x','y',ARRAY['a'],'$argon2id$h')",
    )  # fmt: skip
    assert result.returncode != 0
    assert "permission denied for function" in result.stderr


def test_a_second_bootstrap_is_refused(cluster: dict[str, Any], administrator: str) -> None:
    """One administrator, and the second attempt is told to go and look."""
    del administrator
    result = _docker(
        "exec", "-i", cluster["cluster"].name, "psql", "-qtA", "-U", "postgres",
        "-d", cluster["database"], "-c",
        f'SET ROLE "{cluster["owner"]}"; '
        "SELECT app_private.auth_bootstrap_administrator('someone','Someone',"
        f"'{cluster['roles']['project_admin']}',ARRAY['notes:read'],'$argon2id$h')",
    )  # fmt: skip
    assert result.returncode != 0
    assert "AP409" in result.stderr


def test_the_service_cannot_read_the_tables_it_reaches_through_functions(
    cluster: dict[str, Any],
) -> None:
    for table in ("users", "user_credentials"):
        result = _docker(
            "exec", "-i", cluster["cluster"].name, "psql", "-qtA", "-U", "postgres",
            "-d", cluster["database"], "-c",
            f'SET ROLE "{cluster["auth_role"]}"; SELECT count(*) FROM app_private.{table}',  # noqa: S608
        )  # fmt: skip
        assert result.returncode != 0, f"auth_service can read app_private.{table} directly"
        assert "permission denied" in result.stderr

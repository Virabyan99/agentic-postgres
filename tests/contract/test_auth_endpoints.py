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
import uuid as uuid_module
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agentic_postgres import REPO_ROOT, migrations


def _bootstrap_module() -> Any:
    """`bin/postgres-bootstrap.py`, loaded by path.

    It is an operator command rather than a package module, so it is loaded the
    way the other proofs that read it load it. What this file wants from it is
    `AUTHENTICATOR_REQUEST_ROLES` -- the single authority for which roles a token
    may name, which D301 and D492 are both about not copying.
    """
    import importlib.util

    specification = importlib.util.spec_from_file_location(
        "apg_postgres_bootstrap_auth_endpoints", REPO_ROOT / "bin" / "postgres-bootstrap.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

PASSPHRASE = "a-correct-horse-battery-staple"  # noqa: S105 -- a fixture, hashed and verified
ADMIN_SCOPES = [
    "admin_agents:read",
    "admin_agents:write",
    "admin_users:read",
    "admin_users:write",
    "notes:read",
]


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

        # What the bootstrap plane does in production (D102, D246). The rig
        # supplies it because Run 7 shipped the service with the role NOLOGIN.
        cluster.psql(
            f"ALTER ROLE \"{auth_role}\" LOGIN PASSWORD '{auth_password}'", database="postgres"
        )

        # And the request-role memberships, with the three options the bootstrap
        # plane sets, **read from the product's own constant** (D492).
        #
        # This was a written-down list of four until Session 9 Run 2, with a
        # comment saying the agent roles were deliberately omitted because
        # `test_the_authenticator_cannot_become_an_agent_role` measured their
        # absence. That stopped being true in Session 8, which activated
        # `agent_reader`: from then on the fixture was manufacturing the
        # condition the test measured, and the test asserted a property the
        # product no longer had. Both stayed green for a session and a half.
        #
        # A fifth copy of an enumeration that exists as a constant precisely so
        # proofs read it rather than restate it -- D301's shape, and Session 8
        # Run 2 deleted three others (D416).
        authenticator = roles["postgrest_authenticator"]
        authenticator_password = secrets.token_hex(24)
        cluster.psql(
            f"ALTER ROLE \"{authenticator}\" LOGIN PASSWORD '{authenticator_password}'",
            database="postgres",
        )
        for request_role in _bootstrap_module().AUTHENTICATOR_REQUEST_ROLES:
            cluster.psql(
                f'GRANT "{roles[request_role]}" TO "{authenticator}" '
                "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE",
                database="postgres",
            )

        yield {
            "cluster": cluster,
            "document": document,
            "roles": roles,
            "owner": owner,
            "auth_role": auth_role,
            "auth_password": auth_password,
            "authenticator_password": authenticator_password,
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
    application = main_module.create_app("auth")

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
    # 400 and `malformed_request`, not 422 and `invalid_request` (ADR 0097).
    # This asserted 422 while the live proof asserted 400 -- two authorities for
    # one status inside one service, each internally consistent, and the
    # disagreement survived because the live one had never run (D264's shape,
    # D303).
    assert response.status_code == 400
    assert response.json() == {"error": "malformed_request"}
    # The property that was actually violated: an unauthenticated caller was
    # told WHICH member it had duplicated. Asserting the absence of a message
    # rather than the status alone is what makes this stricter than what it
    # replaces.
    assert "message" not in response.json()
    assert "username" not in response.text


def test_an_unknown_member_in_the_login_body_is_refused(drive: Any) -> None:
    """A client naming its own role gets an error, not a silent discard."""
    response = drive(
        "POST",
        "/auth/login",
        content=json.dumps({"username": "ada", "password": PASSPHRASE, "role": "project_admin"}),
    )
    # A model with `extra="forbid"` refusing an unknown member is as structural
    # as a duplicate one, and it was disclosing pydantic's error TYPES to an
    # unauthenticated caller (ADR 0097).
    assert response.status_code == 400
    assert response.json() == {"error": "malformed_request"}
    assert "role" not in response.text


@pytest.mark.parametrize("body", ["[]", '"a string"', "42", "null", ""])
def test_a_non_object_login_body_is_refused(drive: Any, body: str) -> None:
    """400 with nothing in it, for every shape that is not an object (ADR 0097)."""
    response = drive("POST", "/auth/login", content=body)
    assert response.status_code == 400
    assert response.json() == {"error": "malformed_request"}


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
    # `agent_audit` since Session 9 Run 7. Migration 0020 gives `auth_service`
    # EXECUTE on one definer function over this table and nothing else, so the
    # property it already had for the identity registry has to hold for the
    # audit record too -- and if it ever stops holding, the endpoint that reads
    # it would keep working, which is exactly the failure that would go
    # unnoticed.
    for table in ("users", "user_credentials", "agent_audit"):
        result = _docker(
            "exec", "-i", cluster["cluster"].name, "psql", "-qtA", "-U", "postgres",
            "-d", cluster["database"], "-c",
            f'SET ROLE "{cluster["auth_role"]}"; SELECT count(*) FROM app_private.{table}',  # noqa: S608
        )  # fmt: skip
        assert result.returncode != 0, f"auth_service can read app_private.{table} directly"
        assert "permission denied" in result.stderr


# ---------------------------------------------------------------------------
# Run 9: agents, one-time secrets, and the hook that stopped trusting a signature
# ---------------------------------------------------------------------------


def _create_agent(drive: Any, admin: str, name: str, role: str = "agent_reader") -> dict[str, Any]:
    response = drive(
        "POST",
        "/admin/agents",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps(
            {
                "name": name,
                "description": "a fixture",
                "role": role,
                "scopes": ["notes:read", "tasks:read"],
            }
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_creating_an_agent_returns_its_secret_exactly_once(drive: Any) -> None:
    """The one response that carries it, and the only one.

    Everything after this reads the agent through `GET /admin/agents`, which
    returns no secret and no hash -- because `auth_list_agents` returns neither.
    The absence is a property of the function, not of this handler remembering.
    """
    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "harvester")
    assert created["shown_once"] is True
    assert len(created["secret"]) >= 32

    listed = drive("GET", "/admin/agents", headers={"Authorization": f"Bearer {admin}"})
    assert listed.status_code == 200, listed.text
    entry = next(a for a in listed.json()["agents"] if a["name"] == "harvester")
    assert "secret" not in entry
    assert "secret_hash" not in entry
    assert entry["owner_id"], "an agent with no owner is an authority nobody is accountable for"


def test_no_endpoint_returns_an_agent_secret_twice(drive: Any) -> None:
    """SEC-CRED-001's agent half, asserted as an absence.

    A retrieval path is not something the service declines to expose -- there is
    no function in either migration that returns `secret_hash` to anything but
    the token exchange, and no route that reads one. This walks every published
    path and asserts none of them answers with the secret.
    """
    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "no-second-look")
    secret = created["secret"]
    agent_id = created["agent_id"]

    headers = {"Authorization": f"Bearer {admin}"}
    for method, path in (
        ("GET", "/admin/agents"),
        ("GET", "/admin/users"),
        ("GET", "/auth/me"),
        ("GET", "/auth/jwks.json"),
    ):
        response = drive(method, path, headers=headers)
        assert secret not in response.text, f"{method} {path} returned the agent secret"
        assert agent_id not in response.text or path == "/admin/agents"


def test_an_agent_can_exchange_its_secret_for_a_token(drive: Any) -> None:
    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "exchanger")

    response = drive(
        "POST",
        "/auth/agent-token",
        content=json.dumps({"agent_id": created["agent_id"], "secret": created["secret"]}),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_use"] == "agent"  # noqa: S105 -- a claim value

    import jwt as pyjwt

    claims = pyjwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["scope"] == ["notes:read", "tasks:read"]
    assert claims["credential_version"] == 0, (
        "an agent has no password, so it has no version of one -- reusing "
        "authz_version for both would make a rotation move two claims that mean "
        "different things"
    )
    assert claims["authz_version"] == 1


@pytest.mark.parametrize(
    ("agent_id", "secret", "why"),
    [
        ("00000000-0000-0000-0000-000000000000", "anything", "unknown agent"),
        ("not-a-uuid", "anything", "malformed id"),
    ],
)
def test_every_agent_token_failure_is_the_same_response(
    drive: Any, agent_id: str, secret: str, why: str
) -> None:
    response = drive(
        "POST", "/auth/agent-token", content=json.dumps({"agent_id": agent_id, "secret": secret})
    )
    assert response.status_code == 401
    assert response.json() == {"error": "authentication_failed"}


def test_a_wrong_secret_is_the_same_response(drive: Any) -> None:
    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "wrong-secret")
    response = drive(
        "POST",
        "/auth/agent-token",
        content=json.dumps({"agent_id": created["agent_id"], "secret": "not-it"}),
    )
    assert response.status_code == 401
    assert response.json() == {"error": "authentication_failed"}


def test_a_revoked_agent_is_refused_and_looks_the_same(drive: Any) -> None:
    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "revoke-me")

    changed = drive(
        "PATCH",
        f"/admin/agents/{created['agent_id']}",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps({"status": "revoked"}),
    )
    assert changed.status_code == 200, changed.text

    response = drive(
        "POST",
        "/auth/agent-token",
        content=json.dumps({"agent_id": created["agent_id"], "secret": created["secret"]}),
    )
    assert response.status_code == 401
    assert response.json() == {"error": "authentication_failed"}


def test_rotating_a_secret_replaces_the_old_one(drive: Any) -> None:
    """The documented recovery for a lost secret, and it is not additive.

    The old secret stops working. That is what makes "rotate again" a recovery
    rather than a way to accumulate live credentials for one agent.
    """
    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "rotator")

    rotated = drive(
        "POST",
        f"/admin/agents/{created['agent_id']}/rotate-secret",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["secret"] != created["secret"]
    assert rotated.json()["authz_version"] == 2

    old = drive(
        "POST",
        "/auth/agent-token",
        content=json.dumps({"agent_id": created["agent_id"], "secret": created["secret"]}),
    )
    assert old.status_code == 401, "the secret a rotation replaced still worked"

    new = drive(
        "POST",
        "/auth/agent-token",
        content=json.dumps({"agent_id": created["agent_id"], "secret": rotated.json()["secret"]}),
    )
    assert new.status_code == 200, new.text


def test_an_agent_may_not_hold_a_scope_outside_its_roles_ceiling(drive: Any) -> None:
    """The agent ceiling is deliberately narrower than the human one on writes."""
    admin = _login(drive).json()["access_token"]
    response = drive(
        "POST",
        "/admin/agents",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps(
            {
                "name": "over-reaching-agent",
                "description": "",
                "role": "agent_reader",
                "scopes": ["notes:read", "notes:write"],
            }
        ),
    )
    assert response.status_code == 422, response.text
    assert "notes:write" in response.json()["message"]


def test_the_agent_surface_needs_the_agent_scope_not_the_user_one(drive: Any) -> None:
    """Two administrative classes, and holding one is not holding the other."""
    admin = _login(drive).json()["access_token"]
    created = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps(
            {
                "username": "users-only-admin",
                "display_name": "Users Only",
                "role": "project_admin",
                "scopes": ["admin_users:read", "admin_users:write"],
                "password": "a-completely-adequate-passphrase",
            }
        ),
    )
    assert created.status_code == 201, created.text
    theirs = _login(drive, "users-only-admin", "a-completely-adequate-passphrase").json()
    header = {"Authorization": f"Bearer {theirs['access_token']}"}

    assert drive("GET", "/admin/users", headers=header).status_code == 200
    assert drive("GET", "/admin/agents", headers=header).status_code == 403


def test_an_unauthenticated_caller_cannot_reach_the_agent_surface(drive: Any) -> None:
    assert drive("GET", "/admin/agents").status_code == 401
    assert drive("POST", "/admin/agents", content="{}").status_code == 401


# ---------------------------------------------------------------------------
# The hook, against the cluster rather than against PostgREST
# ---------------------------------------------------------------------------


def _hook(cluster: dict[str, Any], role: str, claims: dict[str, Any] | None) -> Any:
    """Run the pre-request hook as a request role, with claims set the way
    PostgREST sets them.

    Not through PostgREST: that needs the whole edge, and Run 10 is where the
    two verifiers are measured together. What this proves is the half that is a
    property of the database -- that the hook refuses a token whose claims no
    longer match, which no amount of correct signing can rescue.
    """
    setting = "SET LOCAL request.jwt.claims = " + (
        "DEFAULT" if claims is None else "'" + json.dumps(claims).replace("'", "''") + "'"
    )
    return _docker(
        "exec", "-i", cluster["cluster"].name, "psql", "-qtA", "-U", "postgres",
        "-d", cluster["database"], "-c",
        f'BEGIN; SET LOCAL ROLE "{role}"; {setting}; '
        "SELECT app_private.postgrest_pre_request(); "
        "SELECT current_setting('app.user_id', true); COMMIT;",
    )  # fmt: skip


def _claims_for(cluster: dict[str, Any], subject: str, **overrides: Any) -> dict[str, Any]:
    row = cluster["cluster"].psql(
        f'SET ROLE "{cluster["owner"]}"; '  # noqa: S608
        "SELECT role_name, array_to_string(scopes, ','), credential_version, authz_version "
        f"FROM app_private.auth_user_state('{subject}'::uuid)"
    )
    role_name, scopes, credential_version, authz_version = row.split("|")
    claims = {
        "sub": subject,
        "role": role_name,
        "scope": scopes.split(","),
        "credential_version": int(credential_version),
        "authz_version": int(authz_version),
    }
    claims.update(overrides)
    return claims


def test_the_hook_accepts_a_token_that_matches_current_state(
    cluster: dict[str, Any], administrator: str
) -> None:
    result = _hook(cluster, cluster["roles"]["project_admin"], _claims_for(cluster, administrator))
    assert result.returncode == 0, result.stderr
    assert administrator in result.stdout, "app.user_id was not established"


def test_the_hook_still_serves_an_anonymous_request(cluster: dict[str, Any]) -> None:
    """No claims at all is a role with no identity, which is the honest state."""
    result = _hook(cluster, cluster["roles"]["anon"], None)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("field", "value", "what"),
    [
        ("credential_version", 99, "a password reset after issuance"),
        ("authz_version", 99, "a role, scope or status change after issuance"),
        ("role", "apg_wrong_role", "a role that is not the stored one"),
        ("scope", ["notes:read"], "scopes narrowed after issuance"),
        ("sub", "00000000-0000-0000-0000-000000000000", "a subject that does not exist"),
    ],
)
def test_the_hook_refuses_a_token_that_no_longer_matches(
    cluster: dict[str, Any], administrator: str, field: str, value: Any, what: str
) -> None:
    """SEC-REV-001 at the second verifier.

    Every one of these tokens is perfectly signed. What refuses them is the
    comparison against current state, inside the request's own transaction --
    which is the whole difference between "this token was issued" and "this
    token is still true".
    """
    claims = _claims_for(cluster, administrator, **{field: value})
    result = _hook(cluster, cluster["roles"]["project_admin"], claims)
    assert result.returncode != 0, f"the hook served a token describing {what}"
    assert "no longer current" in result.stderr or "could not be read" in result.stderr


def test_the_hook_refuses_a_disabled_subject_whose_claims_are_otherwise_current(
    cluster: dict[str, Any], drive: Any
) -> None:
    """The one case the version comparison cannot cover.

    Found by mutation: removing `status = 'active'` from the helper left every
    hook test green, because disabling a subject also moves `authz_version` and
    the version check caught it first. The isolating case is a token whose
    claims are read back AFTER the disable -- every field then matches current
    state, and `status` is the only thing left to refuse it.

    That is not a contrived shape. It is what an attacker holding a token and a
    way to read current state would construct, and it is what any future code
    path that re-issues from current state would produce.
    """
    admin = _login(drive).json()["access_token"]
    created = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps(
            {
                "username": "hook-disabled",
                "display_name": "Hook Disabled",
                "role": "authenticated",
                "scopes": ["notes:read"],
                "password": "a-thoroughly-ordinary-passphrase",
            }
        ),
    )
    user_id = created.json()["user_id"]

    drive(
        "PATCH",
        f"/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps({"status": "disabled"}),
    )

    # Built from current state, so every version, the role and the scopes match.
    claims = _claims_for(cluster, user_id)
    result = _hook(cluster, cluster["roles"]["authenticated"], claims)

    assert result.returncode != 0, (
        "the hook served a disabled subject whose other claims were current; "
        "only the status check can refuse this one"
    )
    assert "no longer current" in result.stderr


def test_the_hook_refuses_a_space_delimited_scope(
    cluster: dict[str, Any], administrator: str
) -> None:
    """Which is what most of the world's JWTs carry, and is not this contract's."""
    claims = _claims_for(cluster, administrator, scope="notes:read admin_users:read")
    result = _hook(cluster, cluster["roles"]["project_admin"], claims)
    assert result.returncode != 0
    assert "could not be read" in result.stderr


def test_the_documentation_role_still_needs_no_record(cluster: dict[str, Any]) -> None:
    """0009 and 0010's clause, kept -- including the half I got wrong.

    A role that reads the published shape of the API and none of its data is not
    a subject in the identity registry, so it returns before the current-state
    comparison and needs no record. What it does NOT do is accept a subject: a
    documentation token carrying one is **refused**, because ignoring it would
    be the same outcome today and a silent one (D158).

    The first version of this test asserted the opposite and passed a subject,
    which would have relaxed a Session 5 property to make a Session 6 test
    green. The suite refused it.
    """
    bare = _hook(cluster, cluster["roles"]["api_documentation"], None)
    assert bare.returncode == 0, bare.stderr

    with_subject = _hook(
        cluster,
        cluster["roles"]["api_documentation"],
        {
            "sub": "11111111-2222-3333-4444-555555555555",
            "role": cluster["roles"]["api_documentation"],
            "scope": ["meta:read"],
            "credential_version": 1,
            "authz_version": 1,
        },
    )
    assert with_subject.returncode != 0, "a documentation token carrying a subject was served"
    assert "no request identity" in with_subject.stderr


def test_the_service_keeps_its_access_plane_after_0013(cluster: dict[str, Any]) -> None:
    """D267: `REVOKE ... FROM PUBLIC` does not touch a named grant.

    0013 ends with a blanket revoke over every function in the schema. If that
    took 0012's grants with it, the service would lose its access plane the
    moment 0013 applied -- and the first draft of 0013 restated all eight grants
    under a comment claiming a measurement that was never run. This is the
    measurement.
    """
    for function, arguments in (
        ("auth_lookup_user", "'nobody'"),
        ("auth_list_users", ""),
        ("auth_lookup_agent", "'00000000-0000-0000-0000-000000000000'::uuid"),
        ("auth_list_agents", ""),
    ):
        result = _docker(
            "exec", "-i", cluster["cluster"].name, "psql", "-qtA", "-U", "postgres",
            "-d", cluster["database"], "-c",
            f'SET ROLE "{cluster["auth_role"]}"; '  # noqa: S608
            f"SELECT count(*) FROM app_private.{function}({arguments})",
        )  # fmt: skip
        assert result.returncode == 0, f"{function}: {result.stderr}"


def test_the_authenticator_becomes_exactly_the_request_roles(cluster: dict[str, Any]) -> None:
    """Which roles a token may name, measured through a real connection (D492).

    **This used to be `test_the_authenticator_cannot_become_an_agent_role`, and
    it had been asserting a false property since Session 8.** It named
    `agent_reader` and `agent_writer` as roles the authenticator must not become
    -- but Session 8 activated `agent_reader`, so in production the authenticator
    *can* become it. The test kept passing because the fixture granted a
    hardcoded list of four that omitted both, which is the fixture manufacturing
    the condition the test measures.

    Its docstring's other premise expired at the same time. It said *"there is no
    path on which the hook could emit an agent-specific error"*; migration 0018's
    `token_use` branch is exactly that path, and raises `AP401`.

    So the assertion becomes the rule the old list was an instance of: **the
    authenticator becomes exactly the roles the bootstrap plane grants it, and no
    others.** Both halves are read from `AUTHENTICATOR_REQUEST_ROLES`, so the
    refusal below is about a service identity rather than about whichever agent
    role happens to be waiting for activation this session.

    Re-derived, not relaxed (ADR 0096): the negative arm is now over *every*
    project role outside the request set, which is strictly more than the two
    names it replaced.
    """
    authenticator = cluster["roles"]["postgrest_authenticator"]
    request_roles = set(_bootstrap_module().AUTHENTICATOR_REQUEST_ROLES)

    def become(role_suffix: str) -> subprocess.CompletedProcess[str]:
        # Connected AS the authenticator, over TCP, with its own password. The
        # first version of this test ran `SET ROLE authenticator; SET ROLE
        # agent_reader` inside a superuser session -- and it PASSED, because a
        # further SET ROLE is checked against the SESSION user, which was
        # `postgres`. It proved that a superuser can become anything. ADR 0065's
        # warning, reached through a connection rather than a configuration.
        return _docker(
            "exec", "-i", "-e", f"PGPASSWORD={cluster['authenticator_password']}",
            cluster["cluster"].name, "psql", "-qtA",
            "-h", "127.0.0.1", "-U", authenticator, "-d", cluster["database"],
            "-c", f'SET ROLE "{cluster["roles"][role_suffix]}"; SELECT current_user',
        )  # fmt: skip

    # The positive half, over every request role. Without it a broken connection
    # would refuse everything and look identical to a perfect boundary.
    for role_suffix in sorted(request_roles):
        result = become(role_suffix)
        assert result.returncode == 0, (
            f"the authenticator cannot become {role_suffix}, which is a request role: "
            f"{result.stderr[:200]}"
        )
        assert cluster["roles"][role_suffix] in result.stdout

    # The negative half, over everything else this project declares -- service
    # identities, the owner, the migration user. `mcp_audit_service` is among
    # them and ADR 0135 keeps it there.
    others = sorted(
        suffix
        for suffix in cluster["roles"]
        if suffix not in request_roles and suffix != "postgrest_authenticator"
    )
    assert others, "no non-request role to refuse; the negative half would be vacuous"
    for role_suffix in others:
        result = become(role_suffix)
        assert result.returncode != 0, (
            f"the authenticator became {role_suffix}, which this release does not activate"
        )
        assert "permission denied to set role" in result.stderr


# ---------------------------------------------------------------------------
# Run 7: the admin audit endpoint (ADR 0142, migration 0020)
#
# `GET /admin/audit` is four pieces in one order -- `_service`, `authenticate`,
# `require_scope`, then the query string -- and the order is load-bearing: a
# caller that has not proved who it is cannot use a parse refusal to enumerate
# the filters this endpoint takes.
# ---------------------------------------------------------------------------

AUDIT_SCOPES = [
    "admin_audit:read",
    "admin_users:read",
    "notes:read",
]


def _errors_module() -> Any:
    """`app.errors`, for the refusal payloads.

    Imported inside a function because this module only puts the service on the
    path once `create_app` has run, the way every other import of `app.*` here
    does. The payloads are read rather than restated: a body compared against a
    literal passes when both copies are edited together, which is exactly the
    class of proof CLAUDE.md section 6 is about.
    """
    from app import errors

    return errors


def _seed_audit_row(cluster: dict[str, Any], agent_id: str, owner_id: str, tool: str) -> None:
    """One `agent_plane` row, written the way the pre-request hook would arrange it.

    There is no PostgREST in this rig, so the GUCs are set directly -- which is
    what `tests/contract/test_agent_audit_plane.py` does and says why. All of it
    in ONE `-c`, because `set_config(..., true)` is transaction-local and a GUC
    set in one session and read in another is a different measurement entirely.
    """
    cluster["cluster"].psql(
        f'SET ROLE "{cluster["roles"]["agent_reader"]}"; '
        f"SELECT set_config('app.agent_id', '{agent_id}', true); "
        f"SELECT set_config('app.user_id', '{owner_id}', true); "
        f"SELECT api.agent_audit_begin('{tool}')"
    )


def _auditor(drive: Any, admin: str, username: str) -> str:
    """A second administrator holding `admin_audit:read`, created THROUGH THE PRODUCT.

    `POST /admin/users`, not an INSERT and not `auth_bootstrap_administrator`:
    ADR 0065/0066's rule is that a proof reaching the right end state by a route
    the product does not take proves the end state is reachable, not that the
    product reaches it. The bootstrap function is also refused a second time by
    design, so a direct route would not have worked twice anyway.

    It exists because `ada` deliberately does NOT hold the scope. That is
    `API-ADMIN-001`'s shape: the role never implies the scope, so the same
    `project_admin` role is refused on one token and served on another.
    """
    created = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps(
            {
                "username": username,
                "display_name": "An auditor",
                "role": "project_admin",
                "scopes": AUDIT_SCOPES,
                "password": PASSPHRASE,
            }
        ),
    )
    assert created.status_code == 201, created.text
    token = _login(drive, username=username).json()["access_token"]
    return str(token)


def test_the_audit_endpoint_needs_its_own_scope_not_the_agent_roster_one(drive: Any) -> None:
    """API-ADMIN-001, on the scope Session 9 adds.

    `ada` is a `project_admin` holding `admin_agents:read` -- she can list every
    agent -- and she is refused here. Listing WHICH agents exist and reading WHAT
    THEY DID are different authorities, and reusing the roster scope would have
    made that one decision, taken once, by whoever first granted the roster.

    The positive half is the next test. Without it a route that refused
    everybody would pass this one.
    """
    admin = _login(drive).json()["access_token"]
    assert "admin_audit:read" not in ADMIN_SCOPES, (
        "ada now holds the audit scope, so this test measures nothing"
    )

    roster = drive("GET", "/admin/agents", headers={"Authorization": f"Bearer {admin}"})
    assert roster.status_code == 200, "the control failed: ada cannot reach the roster either"

    response = drive("GET", "/admin/audit", headers={"Authorization": f"Bearer {admin}"})
    assert response.status_code == 403, response.text
    assert response.json() == _errors_module().AUTHORIZATION_FAILED


def test_an_administrator_holding_the_scope_reads_the_record(
    drive: Any, cluster: dict[str, Any]
) -> None:
    """The positive half, end to end: HTTP, the scope, the grant and 0020's function.

    This is the assertion migration 0020 exists for. Before it, `auth_service`
    held schema USAGE on `app_private` and nothing else, so this request had no
    statement it was allowed to send (D501) -- and it would have failed here with
    `permission denied for function`, not with an empty list.
    """
    admin = _login(drive).json()["access_token"]
    auditor = _auditor(drive, admin, "auditor-reads")

    agent, owner = str(uuid_module.uuid4()), str(uuid_module.uuid4())
    _seed_audit_row(cluster, agent, owner, "query_resource")

    response = drive("GET", "/admin/audit", headers={"Authorization": f"Bearer {auditor}"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"

    body = response.json()
    assert body["limit"] == 100, "the default limit is not the documented one"
    row = next(entry for entry in body["audit"] if entry["agent_id"] == agent)
    assert row["source"] == "agent_plane"
    assert row["outcome"] == "started"
    assert row["tool"] == "query_resource"
    assert row["owner_id"] == owner
    assert row["started_at"]
    # D500, rendered rather than omitted. An absent key and a null one read the
    # same to a client and only one of them is honest about the gap.
    assert "request_id" in row


def test_the_audit_endpoint_returns_no_secret_material(drive: Any, cluster: dict[str, Any]) -> None:
    """The record names a tool and a principal, never a credential.

    Asserted as an absence over the response rather than field by field: a
    column added to `agent_audit` by a later migration reaches this endpoint
    through `SELECT *`, so the guard has to be over what came back.
    """
    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "audited-agent")
    auditor = _auditor(drive, admin, "auditor-no-secrets")
    _seed_audit_row(cluster, created["agent_id"], str(uuid_module.uuid4()), "run_report")

    response = drive("GET", "/admin/audit", headers={"Authorization": f"Bearer {auditor}"})
    assert response.status_code == 200, response.text
    assert created["secret"] not in response.text
    for forbidden in ("secret", "password", "hash", "token"):
        assert forbidden not in response.text.lower(), f"the audit response contains {forbidden!r}"


def test_a_repeated_query_parameter_is_refused_rather_than_resolved(
    drive: Any, cluster: dict[str, Any]
) -> None:
    """The measured defect, refused (Run 7's rig7).

    `QueryParams("limit=1&limit=9999")["limit"]` is `"9999"` on the locked
    Starlette -- last value wins, silently, which is `strict_json`'s
    duplicate-member defect arriving over the query string. A caller that sends
    a modest bound and an enormous one would get the enormous one.

    The control is the same request with the parameter once, which must be
    served: a route that refused every `limit` would pass the refusal half.
    """
    admin = _login(drive).json()["access_token"]
    auditor = _auditor(drive, admin, "auditor-duplicates")
    headers = {"Authorization": f"Bearer {auditor}"}

    control = drive("GET", "/admin/audit?limit=1", headers=headers)
    assert control.status_code == 200, f"the control failed: {control.text}"

    response = drive("GET", "/admin/audit?limit=1&limit=9999", headers=headers)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_request"
    assert "more than once" in body["message"]
    assert "limit" in body["message"]

    # And it is not a special case for `limit`. A repeated filter resolves the
    # same way and would silently answer a different question than the one asked.
    repeated_filter = drive(
        "GET",
        f"/admin/audit?agent_id={uuid_module.uuid4()}&agent_id={uuid_module.uuid4()}",
        headers=headers,
    )
    assert repeated_filter.status_code == 422, repeated_filter.text


def test_an_unknown_query_parameter_is_refused(drive: Any) -> None:
    """`extra="forbid"`'s reasoning, over the query string.

    Without it the framework accepts and DISCARDS the parameter, so a caller
    that believes it filtered is served the unfiltered record and nothing tells
    it otherwise. That is `models.py`'s stated measurement -- an unknown member
    leaves no trace at all -- and a silently ignored filter on an audit endpoint
    is the same failure with worse consequences.
    """
    admin = _login(drive).json()["access_token"]
    auditor = _auditor(drive, admin, "auditor-unknown")
    headers = {"Authorization": f"Bearer {auditor}"}

    response = drive("GET", "/admin/audit?cursor=abc", headers=headers)
    assert response.status_code == 422, response.text
    assert "unknown query parameter" in response.json()["message"]

    # Case-sensitivity, measured in rig7: `Limit` and `limit` are DISTINCT keys,
    # so an allowlist that folded case would accept `LIMIT` and one that did not
    # must refuse it. This asserts which of the two this endpoint is.
    assert drive("GET", "/admin/audit?Limit=5", headers=headers).status_code == 422


@pytest.mark.parametrize(
    ("query", "why"),
    [
        ("limit=0", "below the range"),
        ("limit=501", "above the range"),
        ("limit=-1", "negative"),
        ("limit=abc", "not an integer"),
        ("limit=", "present and empty"),
        ("agent_id=not-a-uuid", "not a uuid"),
        ("agent_id=", "present and empty"),
    ],
)
def test_a_value_outside_its_contract_is_refused_and_never_clamped(
    drive: Any, query: str, why: str
) -> None:
    """A refusal names the bound; a clamp answers a question nobody asked.

    `limit=501` is the arm that matters. A clamp would return 500 rows with a
    `200` and say nothing, and the caller would believe it had read the whole
    record. The bound lives at the route and migration 0020's reader
    deliberately does not restate it: two bounds over one rule drift the moment
    either moves (D495, D463).

    `limit=` and `agent_id=` are the empty-value arms. Measured in rig7: an
    empty query value is PRESENT, not absent, so a converter that let it fall
    through to a default would be the one path by which a caller could make a
    filter disappear.
    """
    admin = _login(drive).json()["access_token"]
    auditor = _auditor(drive, admin, f"auditor-{abs(hash(query)) % 100000}")
    response = drive("GET", f"/admin/audit?{query}", headers={"Authorization": f"Bearer {auditor}"})
    assert response.status_code == 422, f"{why}: {response.status_code} {response.text}"
    assert response.json()["error"] == "invalid_request"


def test_the_advertised_boundary_is_the_enforced_one(drive: Any) -> None:
    """The bound the DOCUMENT publishes, sent to the endpoint that publishes it.

    Read from the generated document rather than from `routes.py`'s constant,
    which is the whole point: the offline test next to this one can only show
    that the document is coherent, because both of its sides come from the same
    constant. This sends the advertised maximum and one past it, so a route
    enforcing a number it does not publish is refused for a request its own
    contract says is legal -- and goes red here.
    """
    from app import main as main_module

    document = main_module.create_app("auth").openapi()
    parameters = document["paths"]["/admin/audit"]["get"]["parameters"]
    schema = next(p for p in parameters if p["name"] == "limit")["schema"]
    advertised_max = int(schema["maximum"])
    advertised_min = int(schema["minimum"])

    admin = _login(drive).json()["access_token"]
    auditor = _auditor(drive, admin, "auditor-boundary")
    headers = {"Authorization": f"Bearer {auditor}"}

    for value in (advertised_min, advertised_max):
        served = drive("GET", f"/admin/audit?limit={value}", headers=headers)
        assert served.status_code == 200, (
            f"limit={value} is inside the advertised range and was refused "
            f"({served.status_code}): {served.text}"
        )
        assert served.json()["limit"] == value, "the endpoint applied a different limit"

    for value in (advertised_min - 1, advertised_max + 1):
        refused = drive("GET", f"/admin/audit?limit={value}", headers=headers)
        assert refused.status_code == 422, (
            f"limit={value} is outside the advertised range and was served "
            f"({refused.status_code}), so the published bound is not the enforced one"
        )


def test_the_limit_is_applied_and_reported(drive: Any, cluster: dict[str, Any]) -> None:
    """What the caller asked for is what ran, and the response says which.

    The reported `limit` is what makes the absence of a clamp observable from
    outside: a response that returned fewer rows than asked and named no bound
    would be indistinguishable from a record that simply has fewer rows.
    """
    admin = _login(drive).json()["access_token"]
    auditor = _auditor(drive, admin, "auditor-limits")
    agent, owner = str(uuid_module.uuid4()), str(uuid_module.uuid4())
    for tool in ("query_resource", "run_report", "list_resources"):
        _seed_audit_row(cluster, agent, owner, tool)

    headers = {"Authorization": f"Bearer {auditor}"}
    full = drive("GET", f"/admin/audit?agent_id={agent}", headers=headers).json()
    assert len(full["audit"]) == 3
    assert full["limit"] == 100

    bounded = drive("GET", f"/admin/audit?agent_id={agent}&limit=2", headers=headers).json()
    assert len(bounded["audit"]) == 2
    assert bounded["limit"] == 2
    # Every prefix of the full ordering, which is what the reader's `id` tiebreak
    # is for -- the three rows above share a `started_at` to the microsecond.
    assert [row["id"] for row in bounded["audit"]] == [row["id"] for row in full["audit"]][:2]


def test_the_filters_narrow_the_record_and_do_not_widen_it(
    drive: Any, cluster: dict[str, Any]
) -> None:
    """`agent_id` and `owner_id` narrow a permitted read rather than authorize one.

    That is what makes them acceptable as parameters at all, while the agent
    plane's own audit functions take no identity argument (SEC-PARAM-001, D473).
    There a parameter naming a principal WOULD be the authority; here the caller
    has already been authorized to read the whole record by a scope, so a filter
    can only ever return less.
    """
    admin = _login(drive).json()["access_token"]
    auditor = _auditor(drive, admin, "auditor-filters")
    headers = {"Authorization": f"Bearer {auditor}"}

    mine, other, owner = (str(uuid_module.uuid4()) for _ in range(3))
    _seed_audit_row(cluster, mine, owner, "query_resource")
    _seed_audit_row(cluster, other, owner, "query_resource")

    def rows(query: str) -> list[dict[str, Any]]:
        response = drive("GET", f"/admin/audit?{query}&limit=500", headers=headers)
        assert response.status_code == 200, response.text
        return list(response.json()["audit"])

    unfiltered = rows("")
    by_agent = rows(f"agent_id={mine}")
    by_owner = rows(f"owner_id={owner}")

    assert {row["agent_id"] for row in by_agent} == {mine}
    assert {row["agent_id"] for row in by_owner} == {mine, other}
    assert len(unfiltered) >= len(by_owner) > len(by_agent), (
        "a filter returned more than the unfiltered read, which would make it a widening"
    )
    assert rows(f"agent_id={mine}&owner_id={uuid_module.uuid4()}") == [], (
        "the filters are not conjunctive, so the counts above prove nothing"
    )


def test_an_unauthenticated_caller_learns_nothing_about_the_parameters(drive: Any) -> None:
    """The ORDER of the four pieces, asserted rather than left to reading order.

    Authenticate, require the scope, then parse. A route that parsed first would
    answer 422 `unknown query parameter: 'cursor' (this endpoint takes agent_id,
    limit, owner_id)` to a caller holding no credential at all -- which hands an
    anonymous prober the filter names and the fact that the endpoint exists.

    Both wrong-caller cases are covered: no token, and a token whose subject
    holds every other administrative scope. Each must answer its own refusal and
    neither may name a parameter.
    """
    bad_query = "?cursor=x&limit=1&limit=2&agent_id=not-a-uuid"

    anonymous = drive("GET", f"/admin/audit{bad_query}")
    assert anonymous.status_code == 401, anonymous.text

    admin = _login(drive).json()["access_token"]
    unscoped = drive(
        "GET", f"/admin/audit{bad_query}", headers={"Authorization": f"Bearer {admin}"}
    )
    assert unscoped.status_code == 403, unscoped.text

    for response in (anonymous, unscoped):
        for leaked in ("cursor", "agent_id", "owner_id", "limit", "uuid"):
            assert leaked not in response.text, (
                f"a refusal before the scope check named {leaked!r}, so the query string "
                "was parsed before the caller was authorized"
            )


# ---------------------------------------------------------------------------
# Run 7: SEC-REV-001's database half -- revocation PROVED, not built (D471, D472)
#
# **Session 9 adds no revocation mechanism and must not appear to.** Migration
# 0018 already carries the authoritative check and its own COMMENT states the
# property: *"A revoked, disabled or re-authorized agent stops on the NEXT
# request, not at the token's expiry."* And `PATCH /admin/agents/{agent_id}`
# already revokes, gated on `admin_agents:write`, since Session 6. Building a
# second of either would give one fact two authorities that have to be kept in
# step, and the two would drift on the `authz_version` bump -- which is the part
# that actually stops the token.
#
# So this section takes the product's own route in and asserts the effect at the
# authority. It runs `PATCH`, never an `UPDATE` against the table: ADR 0065/0066
# says a proof reaching the right end state by a route the product does not take
# proves the end state is reachable, not that the product reaches it.
# ---------------------------------------------------------------------------


def _agent_claims(cluster: dict[str, Any], agent_id: str) -> dict[str, Any]:
    """An agent token's claims, read from the registry the way the issuer reads them.

    `credential_version` is `0` by convention (D397): an agent has no password,
    so "not a human" is a VALUE rather than an absence, and the hook checks the
    convention itself. `token_use` is the discriminator and is the only claim in
    the token that is one (ADR 0117).
    """
    row = cluster["cluster"].psql(
        f'SET ROLE "{cluster["owner"]}"; '  # noqa: S608
        "SELECT role_name, array_to_string(scopes, ','), authz_version "
        f"FROM app_private.auth_lookup_agent('{agent_id}'::uuid)"
    )
    role_name, scopes, authz_version = row.split("|")
    return {
        "sub": agent_id,
        "role": role_name,
        "scope": scopes.split(","),
        "credential_version": 0,
        "authz_version": int(authz_version),
        "token_use": "agent",
    }


def test_a_revoked_agents_existing_token_stops_at_the_authoritative_check(
    drive: Any, cluster: dict[str, Any]
) -> None:
    """SEC-REV-001's database half, through the product's own revocation route.

    The claims are captured BEFORE the revocation and replayed unchanged after
    it, which is the whole point: this is a perfectly signed token that was true
    when it was issued. Nothing about the signature changes; what changes is the
    answer to "is this still true", asked inside the request's own transaction.

    **The positive arm runs first and must succeed.** Without it, a hook that
    refused every agent would pass the negative arm, and the test would report a
    boundary where there was a broken fixture. That is not hypothetical here --
    an agent whose scopes were stored unsorted would fail the array equality and
    look exactly like a revocation.
    """
    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "revoked-mid-session", role="agent_writer")
    agent_id = created["agent_id"]
    role = cluster["roles"]["agent_writer"]

    claims = _agent_claims(cluster, agent_id)

    before = _hook(cluster, role, claims)
    assert before.returncode == 0, (
        f"the control failed: an ACTIVE agent's claims were refused: {before.stderr[:300]}"
    )
    assert before.stdout.strip(), "app.user_id was not established for an active agent"

    revoked = drive(
        "PATCH",
        f"/admin/agents/{agent_id}",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps({"status": "revoked"}),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["authz_version"] > claims["authz_version"], (
        "revoking did not move authz_version, which is the part that stops the token"
    )

    after = _hook(cluster, role, claims)
    assert after.returncode != 0, (
        "the same claims were still accepted after revocation, so the token outlives "
        "the credential it was issued against"
    )
    assert "AP401" in after.stderr, after.stderr[:400]


def test_the_status_type_admits_no_third_state_and_terminality_is_UNENFORCED(
    drive: Any, cluster: dict[str, Any]
) -> None:
    """D472's half that holds, and D503 -- the half that does not.

    `app_private.agent_status` is a TWO-value enum, because 0011 decided that
    *"a user is `disabled` by an administrator and can be re-enabled; an agent
    credential is `revoked`, which is terminal for that credential"* -- and that
    comment names `SEC-REV-001` as its proof. Read from the catalog, not from the
    migration text: what a release ships is the type, and a comment in a file is
    not a constraint.

    **Which is exactly what this test found.** The enum is what stops a third
    state existing. Nothing stops the SECOND transition: `auth_set_agent_status`
    is an unguarded `UPDATE`, so `revoked -> active` is legal and answers 200.
    "Terminal" was stated in a comment and enforced by nothing, for three
    sessions, while the requirement whose proof it claims to be sat as a
    placeholder.

    CLAUDE.md section 6's first question, asked of a comment rather than a test:
    what would have to break for this to go red? Until Run 7, nothing.
    """
    values = cluster["cluster"].psql(
        "SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder) "
        "FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
        "JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = 'app_private' AND t.typname = 'agent_status'"
    )
    assert values.strip() == "active,revoked", (
        f"app_private.agent_status is {values!r}. A third value would make un-revoking "
        "expressible, and the kill switch would become a toggle"
    )

    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "terminal-state", role="agent_reader")
    agent_id = created["agent_id"]
    initial_version = int(_agent_claims(cluster, agent_id)["authz_version"])

    for _ in range(2):
        response = drive(
            "PATCH",
            f"/admin/agents/{agent_id}",
            headers={"Authorization": f"Bearer {admin}"},
            content=json.dumps({"status": "revoked"}),
        )
        assert response.status_code == 200, response.text

    # **And here is what the product actually does** (D503). Measured in Run 7:
    # setting a revoked agent back to `active` answers 200 and the agent works
    # again. Nothing enforces the terminality 0011's comment states -- the enum
    # stops `disabled` from existing, and `auth_set_agent_status` is a plain
    # `UPDATE ... SET status = p_status` with no transition guard.
    #
    # Asserted as it IS, deliberately. Session 9 Run 7 proves revocation rather
    # than building it (D471, D472), and a guard is a migration and a product
    # change. The day one lands, this assertion fails and points at its own
    # premise -- which is the arrangement D500's deployment test uses for the
    # same reason.
    restored = drive(
        "PATCH",
        f"/admin/agents/{agent_id}",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps({"status": "active"}),
    )
    assert restored.status_code == 200, (
        "un-revoking is now refused, which is a product change. If it was intended, "
        "invert this assertion and close D503; the guard belongs in a migration"
    )

    # What revocation DOES guarantee, and it is the half that matters: every
    # status change moves `authz_version`, so no token issued before either
    # transition survives. Un-revoking restores the SECRET's usefulness -- which
    # revocation never invalidated -- and resurrects no token.
    versions = [int(response.json()["authz_version"]) for response in (restored,)]
    assert versions[0] > initial_version + 2, (
        "a status change did not move authz_version, which is the part that stops "
        f"the token: {versions[0]} against {initial_version}"
    )


def test_a_revoked_agent_cannot_exchange_its_secret_for_a_fresh_token(drive: Any) -> None:
    """The other half of the kill switch, and the reason it is a kill switch.

    Refusing the OLD token would be worth little if the agent could simply ask
    for a new one -- the secret it holds is unchanged by revocation. Both doors
    have to be shut, and this is the second one.

    The refusal is the same shape as every other authentication failure and
    names no cause (ADR 0097): whether the agent was revoked, never existed, or
    sent the wrong secret costs a caller the same.
    """
    admin = _login(drive).json()["access_token"]
    created = _create_agent(drive, admin, "revoked-then-asks-again", role="agent_reader")

    def exchange() -> Any:
        return drive(
            "POST",
            "/auth/agent-token",
            content=json.dumps({"agent_id": created["agent_id"], "secret": created["secret"]}),
        )

    assert exchange().status_code == 200, "the control failed: an active agent cannot exchange"

    revoked = drive(
        "PATCH",
        f"/admin/agents/{created['agent_id']}",
        headers={"Authorization": f"Bearer {admin}"},
        content=json.dumps({"status": "revoked"}),
    )
    assert revoked.status_code == 200, revoked.text

    refused = exchange()
    assert refused.status_code == 401, refused.text
    assert refused.json() == _errors_module().AUTHENTICATION_FAILED


# ---------------------------------------------------------------------------
# IDN-SESSION-001 / IDN-SESSION-002 -- the session plane (Session 15, ADR 0171)
#
# Against the same live cluster every test above uses, with all 24 migrations
# applied through the product's own render path. These are the behavioural
# assertions: what a refresh DOES, and -- the run's actual subject -- what every
# refusal looks like from outside.
# ---------------------------------------------------------------------------


def _new_subject(drive: Any, username: str, password: str) -> None:
    """A subject of this test's own, so sessions do not accumulate across tests."""
    token = _login(drive).json()["access_token"]
    created = drive(
        "POST",
        "/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        content=json.dumps(
            {
                "username": username,
                "display_name": username.title(),
                "role": "authenticated",
                "scopes": ["notes:read"],
                "password": password,
            }
        ),
    )
    assert created.status_code == 201, created.text


def _refresh(drive: Any, token: str) -> httpx.Response:
    return drive("POST", "/auth/refresh", content=json.dumps({"refresh_token": token}))


def test_a_login_carries_a_refresh_token_and_it_rotates(drive: Any) -> None:
    """The exchange, and the fact that makes it single-use.

    The successor differs from what was presented, and the presented one is
    refused from that moment. A rotation that returned the same value, or left
    the old one live, would be a long-lived credential wearing a short-lived
    name.
    """
    _new_subject(drive, "rita", "a-passphrase-for-rita-here")
    first = _login(drive, "rita", "a-passphrase-for-rita-here").json()
    assert first["refresh_token"], "login issued no refresh token"

    rotated = _refresh(drive, first["refresh_token"])
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()

    assert second["refresh_token"] != first["refresh_token"], "the token did not rotate"
    assert second["access_token"] != first["access_token"]
    assert second["expires_at"] >= first["expires_at"], "the new token expires no later"

    spent = _refresh(drive, first["refresh_token"])
    assert spent.status_code == 401, "a consumed refresh token was accepted again"


def test_a_client_renews_across_the_token_lifetime_without_the_password(drive: Any) -> None:
    """IDN-SESSION-001, and D813 is the reason it is a security property.

    `MAX_TTL_SECONDS` is 900 and the service issues at the ceiling, so before
    this plane existed a client that wanted to stay logged in past fifteen
    minutes had to keep the PASSWORD and replay it. This asserts the half that
    makes the short TTL affordable: holding the refresh token ALONE, a client
    obtains a working access token and reaches an authenticated route with it.

    **The boundary is crossed by discarding the password, not by waiting 930
    seconds.** A test that slept would assert the same thing and cost fifteen
    minutes; what it would additionally prove -- that an expired access token is
    refused -- is already `test_a_password_change_invalidates_a_token_issued
    _before_it`'s territory and the claim contract's.
    """
    _new_subject(drive, "sonia", "a-passphrase-for-sonia-here")
    issued = _login(drive, "sonia", "a-passphrase-for-sonia-here").json()

    # Everything the client keeps. The password is deliberately not carried
    # past this line, which is the property under test.
    held = issued["refresh_token"]

    renewed = _refresh(drive, held)
    assert renewed.status_code == 200, renewed.text
    access = renewed.json()["access_token"]

    me = drive("GET", "/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200, me.text
    assert me.json()["username"] == "sonia"


def test_a_replayed_refresh_token_ends_the_whole_session(drive: Any) -> None:
    """Reuse detection, and the reason the plane has families at all.

    The server cannot tell a replay by the owner from a replay by a thief, so
    it assumes the chain leaked and closes it. **The successor is the control**:
    without asserting that the still-unused token stops working, this would pass
    against an implementation that merely refused the replayed value and left
    the thief's copy live.
    """
    _new_subject(drive, "tamsin", "a-passphrase-for-tamsin-x")
    first = _login(drive, "tamsin", "a-passphrase-for-tamsin-x").json()

    second = _refresh(drive, first["refresh_token"]).json()
    assert second["refresh_token"]

    replay = _refresh(drive, first["refresh_token"])
    assert replay.status_code == 401, "a replayed token was accepted"

    # The CONTROL. The live successor was never presented by an attacker and is
    # still refused, because the family ended.
    successor = _refresh(drive, second["refresh_token"])
    assert successor.status_code == 401, (
        "the replay refused the presented token and left the live successor working, "
        "so a thief who replayed once would still hold a usable session"
    )


def test_every_refresh_failure_is_the_same_response(drive: Any) -> None:
    """The run's subject: four causes, one answer, byte for byte.

    Unknown, replayed, revoked and malformed reach the caller as the same 401
    and the same body. Distinguishing them would tell whoever presented a guess
    whether it named something real -- which is exactly what
    `test_every_authentication_failure_is_the_same_response` withholds on the
    login path, for the same reason.
    """
    _new_subject(drive, "ursula", "a-passphrase-for-ursula-y")
    issued = _login(drive, "ursula", "a-passphrase-for-ursula-y").json()
    spent = issued["refresh_token"]
    live = _refresh(drive, spent).json()["refresh_token"]

    # Replayed: consumes the family, so `live` becomes a revoked-family case.
    replayed = _refresh(drive, spent)
    revoked = _refresh(drive, live)
    unknown = _refresh(drive, "A" * 43)
    malformed = _refresh(drive, "not-a-token")

    answers = {
        "replayed": replayed,
        "revoked": revoked,
        "unknown": unknown,
        "malformed": malformed,
    }
    for name, response in answers.items():
        assert response.status_code == 401, f"{name} answered {response.status_code}"

    bodies = {name: response.content for name, response in answers.items()}
    assert len(set(bodies.values())) == 1, f"the four refusals are distinguishable: {bodies}"

    headers = {name: response.headers.get("www-authenticate") for name, response in answers.items()}
    assert len(set(headers.values())) == 1, f"the challenge differs between causes: {headers}"


def test_sessions_are_listable_and_ending_one_refuses_its_token(drive: Any) -> None:
    """IDN-SESSION-002, both halves, and the second is what makes it real.

    A listing that named sessions but could not end them would be a report. The
    assertion that matters is that the refresh token of a terminated session
    stops working -- ending a session has to reach the credential, not just a
    row somebody reads.
    """
    _new_subject(drive, "vera", "a-passphrase-for-vera-zzz")
    first = _login(drive, "vera", "a-passphrase-for-vera-zzz").json()
    second = _login(drive, "vera", "a-passphrase-for-vera-zzz").json()
    access = second["access_token"]

    listed = drive("GET", "/auth/sessions", headers={"Authorization": f"Bearer {access}"})
    assert listed.status_code == 200, listed.text
    sessions = listed.json()
    assert len(sessions) == 2, f"expected two sessions, got {sessions}"
    assert all(row["revoked_at"] is None for row in sessions)
    # No caller-supplied string is stored (D829), so the listing cannot name a
    # device. Asserted so that adding one later is a decision rather than a drift.
    assert set(sessions[0]) == {
        "session_id",
        "created_at",
        "last_used_at",
        "revoked_at",
        "revoked_reason",
    }

    ended = drive(
        "DELETE",
        f"/auth/sessions/{sessions[0]['session_id']}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert ended.status_code == 204, ended.text

    # One of the two refresh tokens is now dead and the other is not. Which one
    # is decided by `last_used_at DESC`, so both are tried and exactly one must
    # survive -- an assertion that does not depend on the ordering being what
    # this test guessed.
    outcomes = [
        _refresh(drive, first["refresh_token"]).status_code,
        _refresh(drive, second["refresh_token"]).status_code,
    ]
    assert sorted(outcomes) == [200, 401], (
        f"ending one session left {outcomes}; exactly one refresh token should survive"
    )


def test_one_subject_cannot_end_another_subjects_session(drive: Any) -> None:
    """The scoping is in SQL, and this is what would notice if it moved.

    `auth_revoke_session` filters on the owner, so naming somebody else's family
    id is the same answer as naming one that does not exist. The response is 204
    either way -- the caller learns nothing -- and the CONTROL is that the
    victim's session still works afterwards.
    """
    _new_subject(drive, "wanda", "a-passphrase-for-wanda-ab")
    _new_subject(drive, "xenia", "a-passphrase-for-xenia-cd")

    victim = _login(drive, "wanda", "a-passphrase-for-wanda-ab").json()
    victim_access = victim["access_token"]
    victim_sessions = drive(
        "GET", "/auth/sessions", headers={"Authorization": f"Bearer {victim_access}"}
    ).json()
    target = victim_sessions[0]["session_id"]

    attacker = _login(drive, "xenia", "a-passphrase-for-xenia-cd").json()
    attempt = drive(
        "DELETE",
        f"/auth/sessions/{target}",
        headers={"Authorization": f"Bearer {attacker['access_token']}"},
    )
    assert attempt.status_code == 204, "the attempt answered differently and so confirmed the id"

    survived = _refresh(drive, victim["refresh_token"])
    assert survived.status_code == 200, (
        "one subject ended another's session; the SQL scoping is not holding"
    )


def test_refreshing_needs_no_access_token_at_all(drive: Any) -> None:
    """A renewal that required a live access token would only work while unneeded.

    Asserted rather than left implicit, because the obvious way to write this
    endpoint -- behind the same `authenticate` call every other route uses --
    would pass every other test in this file and be useless in the only
    situation the plane exists for.
    """
    _new_subject(drive, "yolanda", "a-passphrase-for-yolanda")
    issued = _login(drive, "yolanda", "a-passphrase-for-yolanda").json()

    renewed = drive(
        "POST",
        "/auth/refresh",
        content=json.dumps({"refresh_token": issued["refresh_token"]}),
    )
    assert renewed.status_code == 200, renewed.text

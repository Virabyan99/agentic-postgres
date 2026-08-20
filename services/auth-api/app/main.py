"""The application object, its lifespan, and the two health paths. No auth yet.

Run 7 is "the service core, before any route", and that is literal: there is no
`/auth/login` here, no `/auth/me` and no `/admin`. Those are Runs 8 and 9. What
exists is the thing they will all be built on -- a process that opens its pool
explicitly, loads its key material from local files, refuses to start if any of
that fails, and can be asked whether it is alive.

**The health paths are container-local (D231).** This project already publishes
a public health route -- `https://<domain>/__apg/healthz`, served by
`edge-probe`, with a Session 5 proof about it. Two more public answers to "is
this project up" is two more things to keep in step, and one of them will drift.
So `/health/live` and `/health/ready` bind the container interface, are excluded
from the generated OpenAPI, and are what the Compose healthcheck asks. What the
public learns about this service's health continues to be what `__apg/healthz`
says.

**Live and ready are different questions and are answered differently.** Live
is "this process is running its event loop" and touches nothing; a live probe
that consulted the database would restart a healthy container every time the
cluster hiccuped. Ready is "a request would succeed", which for this service
means the pool hands out a connection that answers.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from app import db, keys, openapi_docs, routes, storage_client, storage_routes
from app import settings as settings_module
from app.hashing import BoundedHasher
from app.profile import HASH_CONCURRENCY
from app.repository import Repository
from app.service import AuthService
from app.storage_client import BoundedR2, R2Adapter
from app.storage_repository import StorageRepository
from app.storage_service import StorageService
from app.tokens import LocalKeySet

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

#: Everything the process holds for its lifetime, assembled by the lifespan.
#: On `app.state` rather than in module globals so that a test can build a
#: second application without the first one's pool following it around.


def _build_storage(pool: Any) -> StorageService:
    """Assemble the storage plane from its own environment.

    Read here rather than folded into `Settings`, because the storage settings
    include two mounted CREDENTIAL FILES and `Settings` is a frozen dataclass
    that is put on `app.state` and read by health handlers. A credential in it
    would be one `repr()` away from a log line.
    """
    config = storage_client.load_config()
    adapter = R2Adapter(config)
    return StorageService(
        StorageRepository(pool),
        adapter,
        BoundedR2(adapter),
        max_upload_bytes=config.max_upload_bytes,
        upload_ttl_seconds=config.upload_url_ttl_seconds,
        download_ttl_seconds=config.download_url_ttl_seconds,
        object_prefix=config.prefix,
    )


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Acquire everything, or fail the start.

    The order is deliberate: settings, then key material, then the pool. Each
    step is cheaper to fail than the one after it, and the pool is last because
    it is the only one that takes a connection from the cluster's budget -- a
    process that was going to die on a missing key file should not spend four
    connections first.
    """
    mode = application.state.mode
    settings = settings_module.load(mode=mode)
    application.state.settings = settings

    # Read once, at startup, and held in memory. Re-reading per request would
    # make the file's contents a runtime input, and the rotation design needs
    # to know exactly when a verifier changed what it holds -- a restart is an
    # observable moment, a lazy re-read is not.
    #
    # `load_signing_key` derives the public JWK and the `kid` from the private
    # key rather than reading a stored copy, which is ADR 0051's rule and the
    # reason D257 refused a stored `jwt_public_jwks` secret.
    #
    # **None in storage mode**, because storage is granted no signing key
    # (ADR 0101, D320). `settings.load` has already refused to start if one was
    # present, so this branch cannot silently skip a key that exists.
    signing_key = (
        keys.load_signing_key(settings.signing_key_file)
        if settings.signing_key_file is not None
        else None
    )
    application.state.signing_key = signing_key

    hasher = BoundedHasher(concurrency=HASH_CONCURRENCY)
    application.state.hasher = hasher

    pool = db.build_pool(settings.conninfo, size=settings.pool_size)
    application.state.pool = pool
    async with db.pool_lifespan(pool):
        # Assembled after the pool is open, so a route can assume a working one
        # rather than checking. Nothing is served before this point: the
        # lifespan has not yielded.
        #
        # Both modes build the AuthService: storage VERIFIES the tokens auth
        # issues (ADR 0098's third verifier) and so needs the same
        # `authenticate`, including its current-state comparison. What it does
        # not have is a signing key, so it can verify and never issue -- and
        # `/auth/login` is not mounted for it to try.
        #
        # The key set is resolved HERE, per mode, and handed in (ADR 0113).
        # Deriving it inside `AuthService` is exactly what D381 was: storage
        # received `signing_key=None` precisely as intended, that argument was
        # the only key-set source, and the container exited 3 on its first
        # start on any host. An issuer verifies with the public half of what it
        # signs with; a non-issuing verifier reads the same rendered JWKS
        # PostgREST is given.
        if signing_key is not None:
            key_set = LocalKeySet.load(json.dumps(signing_key.jwks()).encode("utf-8"))
        else:
            jwks_file = settings.jwks_file
            if jwks_file is None:  # pragma: no cover -- settings.load refuses this
                raise settings_module.MissingSetting(
                    "no signing key and no APG_JWKS_FILE: this runtime could verify nothing"
                )
            key_set = LocalKeySet.from_path(jwks_file)

        application.state.service = AuthService(
            repository=Repository(pool),
            hasher=hasher,
            signing_key=signing_key,
            key_set=key_set,
            issuer=settings.issuer,
            audience=settings.audience,
            role_suffixes={name: suffix for suffix, name in settings.role_names.items()},
        )
        if mode == "storage":
            application.state.storage = _build_storage(pool)
        yield


def create_app(mode: str | None = None) -> Any:
    """Build the application. A function, not a module-level object.

    A module-level `app = FastAPI()` runs at import, which means importing the
    module for a unit test starts building the thing under test. This is also
    what lets `tests/contract/` import `main.py` without a database.

    **`mode` decides which surface is built, and that is where ADR 0101's modes
    become real.** One image, three services, and the only moment the boundary
    can be enforced is application construction: after this function returns,
    the surface is whatever was mounted. An auth process with the storage router
    attached would serve `/upload-intents` on a port nothing published and
    nothing tested.

    Required rather than defaulted, from `APP_MODE`, for ADR 0055's reasoning
    applied to behaviour: a default would start the wrong service with a
    correct-looking configuration.

    The return type is `Any` rather than `FastAPI` because ADR 0121's third mode
    returns a Starlette application built by FastMCP. One factory rather than a
    second entrypoint: the image's `ENTRYPOINT` names this function, so a mode
    with its own factory would be a second way in that `APP_MODE` does not
    guard -- and "the mode decides the surface" would stop being true of the
    place that says so.
    """
    resolved = mode if mode is not None else os.environ.get("APP_MODE", "")
    if resolved not in settings_module.APP_MODES:
        raise settings_module.MissingSetting(
            f"APP_MODE must be one of {sorted(settings_module.APP_MODES)}, not {resolved!r}"
        )

    if resolved == "mcp":
        # Returned before any of the below, because none of it applies: no
        # pool, so no `lifespan`; no router, so no health routes on a FastAPI
        # object that would never open a connection to report readiness about.
        # The agent plane's own liveness is its container healthcheck.
        from app.mcp_runtime import create_mcp_app

        return create_mcp_app()

    application = FastAPI(
        title="Agentic Postgres auth",
        lifespan=lifespan,
        # No interactive documentation from this process. `/docs/app` is a
        # separate first-party surface built in Run 10 from a reviewed
        # snapshot (D226), for the same reason the REST documentation is: a
        # page served by the API is a page that changes when the API does,
        # with nobody having read the difference.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @application.get("/health/live", include_in_schema=False)
    async def live() -> Response:
        """The event loop is running. Touches nothing else, on purpose."""
        return JSONResponse({"status": "live"})

    @application.get("/health/ready", include_in_schema=False)
    async def ready() -> Response:
        """A request would succeed: the pool hands out a connection that answers."""
        pool = getattr(application.state, "pool", None)
        if pool is None:
            return JSONResponse({"status": "starting"}, status_code=503)
        try:
            async with pool.connection() as connection:
                await connection.execute("SELECT 1")
        except Exception:
            # Deliberately not the exception's text. A readiness body is read
            # by a healthcheck and written to a log; a psycopg error carries
            # the conninfo, which carries the role name and the passfile path.
            return JSONResponse({"status": "unready"}, status_code=503)
        return JSONResponse({"status": "ready"})

    # Exactly one of the two, never both. Written as an if/else over the mode
    # rather than as two conditional `include_router` calls, so that adding a
    # third mode is a change here and cannot leave both mounted by accident.
    application.state.mode = resolved
    if resolved == "storage":
        application.include_router(storage_routes.router)
    else:
        application.include_router(routes.router)

    # The document this application publishes, with FastAPI's unreachable `422`
    # removed (Run 9). Overridden here rather than in `bin/app-contract.py` so
    # that there is exactly one document: a prune applied only at capture time
    # would mean `create_app(mode).openapi()` and the committed snapshot
    # described different surfaces, and every test that read the first would be
    # measuring something nobody serves.
    #
    # `openapi_url=None` above, so this is never served -- it is read by the
    # contract command and by the tests. The reference page is a reviewed
    # snapshot, not a live capture (ADR 0069).
    generated = application.openapi

    def openapi() -> dict[str, Any]:
        return openapi_docs.prune_unreachable_validation_errors(generated(), application.routes)

    application.openapi = openapi  # type: ignore[method-assign]
    return application


def health_paths() -> tuple[str, ...]:
    """The paths that must never be published (D231).

    Declared here and asserted by `tests/contract/test_auth_service_shape.py`
    against the routes the application actually carries, so that a third health
    path added in a later session is a test failure rather than a surprise on
    the edge.
    """
    return ("/health/live", "/health/ready")


def public_paths() -> tuple[str, ...]:
    """Every path Run 10 will publish through the edge.

    Declared beside the health paths so the two lists are read together: what
    the router carries has to be exactly these plus those, and a route added
    without a decision about which side it falls on fails
    `test_the_application_serves_exactly_the_declared_paths`.
    """
    return (
        "/admin/agents",
        "/admin/agents/{agent_id}",
        "/admin/agents/{agent_id}/rotate-secret",
        "/admin/users",
        "/admin/users/{user_id}",
        "/auth/agent-token",
        "/auth/jwks.json",
        "/auth/login",
        "/auth/me",
    )


def route_paths(application: FastAPI) -> tuple[str, ...]:
    """Every path this application serves. Used by the tests, and by nothing else."""
    paths: list[str] = []
    for route in application.routes:
        path: Any = getattr(route, "path", None)
        if isinstance(path, str):
            paths.append(path)
    return tuple(sorted(paths))

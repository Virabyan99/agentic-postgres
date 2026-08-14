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

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from app import db, keys, routes
from app import settings as settings_module
from app.hashing import BoundedHasher
from app.profile import HASH_CONCURRENCY
from app.repository import Repository
from app.service import AuthService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

#: Everything the process holds for its lifetime, assembled by the lifespan.
#: On `app.state` rather than in module globals so that a test can build a
#: second application without the first one's pool following it around.


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Acquire everything, or fail the start.

    The order is deliberate: settings, then key material, then the pool. Each
    step is cheaper to fail than the one after it, and the pool is last because
    it is the only one that takes a connection from the cluster's budget -- a
    process that was going to die on a missing key file should not spend four
    connections first.
    """
    settings = settings_module.load()
    application.state.settings = settings

    # Read once, at startup, and held in memory. Re-reading per request would
    # make the file's contents a runtime input, and the rotation design needs
    # to know exactly when a verifier changed what it holds -- a restart is an
    # observable moment, a lazy re-read is not.
    #
    # `load_signing_key` derives the public JWK and the `kid` from the private
    # key rather than reading a stored copy, which is ADR 0051's rule and the
    # reason D257 refused a stored `jwt_public_jwks` secret.
    signing_key = keys.load_signing_key(settings.signing_key_file)
    application.state.signing_key = signing_key

    hasher = BoundedHasher(concurrency=HASH_CONCURRENCY)
    application.state.hasher = hasher

    pool = db.build_pool(settings.conninfo, size=settings.pool_size)
    application.state.pool = pool
    async with db.pool_lifespan(pool):
        # Assembled after the pool is open, so a route can assume a working one
        # rather than checking. Nothing is served before this point: the
        # lifespan has not yielded.
        application.state.service = AuthService(
            repository=Repository(pool),
            hasher=hasher,
            signing_key=signing_key,
            issuer=settings.issuer,
            audience=settings.audience,
            role_suffixes={name: suffix for suffix, name in settings.role_names.items()},
        )
        yield


def create_app() -> FastAPI:
    """Build the application. A function, not a module-level object.

    A module-level `app = FastAPI()` runs at import, which means importing the
    module for a unit test starts building the thing under test. This is also
    what lets `tests/contract/` import `main.py` without a database.
    """
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

    application.include_router(routes.router)
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
        "/admin/users",
        "/admin/users/{user_id}",
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

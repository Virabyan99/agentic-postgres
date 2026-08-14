# Session 6 auth service.
#
# The base image and every dependency version arrive as build arguments, so
# versions.env stays the single authority for what this is built from. A `FROM`
# line naming a tag, or a `pip install fastapi` with a version written here,
# would be a second unlocked version declaration that bin/lock-versions.sh
# cannot see -- which is exactly how SCALAR_VERSION named a release that has
# never existed for four sessions (D201, ADR 0077). There are deliberately no
# defaults: a missing argument fails the build rather than floating.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG ARGON2_CFFI_VERSION
ARG CRYPTOGRAPHY_VERSION
ARG FASTAPI_VERSION
ARG PSYCOPG_POOL_VERSION
ARG PSYCOPG_VERSION
ARG PYDANTIC_SETTINGS_VERSION
ARG PYDANTIC_VERSION
ARG PYJWT_VERSION
ARG UVICORN_VERSION

# 65532:65532 is the conventional "nonroot" pair and matches the `user:` in
# compose.yaml and the numeric ownership secrets.required.yaml declares for
# this service's mounted credential. Numeric rather than named, for the reason
# the edge probe gives: a name resolved inside the image could disagree with
# the numeric owner set on the host.
RUN set -eu; \
    groupadd --gid 65532 nonroot; \
    useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot

# `psycopg[binary]`, and the extra is load-bearing rather than an optimisation
# (ADR 0083). Measured in Run 7 against this exact base image digest: it ships
# no libpq, no pg_config and no compiler, and `psycopg` alone -- installed
# successfully, at the locked version -- raises `ImportError: no pq wrapper
# available` on the first import. The three implementations it looks for are
# psycopg_c (needs a compiler), psycopg_binary (this wheel) and a pure-Python
# path that needs a system libpq. Exactly one of the three is reachable here.
#
# The extra rather than a second pin, because psycopg's own metadata declares
# `psycopg-binary==3.3.4; extra == "binary"` -- an exact equality. A separate
# `psycopg-binary==${...}` would be a second authority for a version psycopg
# already fixes, and versions.in.yaml records why it is not an entry there:
# psycopg-binary publishes 55 wheels and no sdist, so the lock has no canonical
# artifact to dereference.
#
# psycopg-pool IS a separate pin, because psycopg declares it with no version
# at all (`psycopg-pool; extra == "pool"`) and it is a different number -- 3.3.1
# against psycopg's 3.3.4. That one is a real choice, so it is locked.
#
# The trailing import is the build's own control: every one of these installing
# is not the same claim as every one of them importing, which is precisely what
# `psycopg` alone demonstrated.
RUN set -eu; \
    pip install --no-cache-dir --no-compile \
      "argon2-cffi==${ARGON2_CFFI_VERSION}" \
      "cryptography==${CRYPTOGRAPHY_VERSION}" \
      "fastapi==${FASTAPI_VERSION}" \
      "psycopg[binary]==${PSYCOPG_VERSION}" \
      "psycopg-pool==${PSYCOPG_POOL_VERSION}" \
      "pydantic==${PYDANTIC_VERSION}" \
      "pydantic-settings==${PYDANTIC_SETTINGS_VERSION}" \
      "pyjwt==${PYJWT_VERSION}" \
      "uvicorn==${UVICORN_VERSION}"; \
    python -c "import argon2, fastapi, jwt, psycopg, psycopg_pool, pydantic, uvicorn"

WORKDIR /app
COPY app /app/app

# Byte-compiled once, as root, so that a read-only root filesystem does not
# force the interpreter to recompile on every start with nowhere to write.
RUN python -m compileall -q /app/app

USER 65532:65532

EXPOSE 8080

# Container-local, and the only health surface this service has (D231). The
# project's public health answer stays `__apg/healthz`, served by edge-probe,
# which already has a proof about it; three answers to "is this project up" is
# three things to keep in step and one of them will drift.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=2).status==200 else 1)"]

# Exec form: the process must receive SIGTERM directly so the lifespan's
# `finally` runs and the pool returns its connections, rather than sitting
# behind a shell that would swallow the signal.
#
# `--factory`, because app.main exposes `create_app()` rather than a
# module-level application object: a module-level `FastAPI()` runs at import,
# which would mean importing the module for a unit test starts building the
# thing under test.
ENTRYPOINT ["python", "-u", "-m", "uvicorn", "--factory", "app.main:create_app", \
            "--host", "0.0.0.0", "--port", "8080", \
            "--no-server-header", "--no-access-log", "--proxy-headers", \
            "--forwarded-allow-ips", "*"]

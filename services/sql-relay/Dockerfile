# Session 44 SQL relay (ADR 0286).
#
# One stage, one dependency. The base image and the `websockets` version arrive
# as build arguments from versions.env (`PYTHON_RUNTIME_IMAGE`, passed by
# compose.yaml as PYTHON_BASE_IMAGE; `WEBSOCKETS_VERSION`) with no defaults: a
# missing argument fails the build rather than floating (ADR 0077). The import
# below is the build's own control that the pinned version installed.
#
# The image's system trust store (`/etc/ssl/certs/ca-certificates.crt`, present
# in the base -- rig 44c) is what verifies the door; nothing here adds a CA,
# and the entrypoint passes no argument (D2772).
ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE}

ARG WEBSOCKETS_VERSION
RUN set -eu; \
    pip install --no-cache-dir --no-compile "websockets==${WEBSOCKETS_VERSION}"; \
    python -c "import websockets, sys; sys.exit(0 if websockets.__version__ == '${WEBSOCKETS_VERSION}' else 1)"

# 65532:65532, the console's numeric nonroot pair and compose.yaml's `user:`.
RUN set -eu; \
    groupadd --gid 65532 nonroot; \
    useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot

WORKDIR /app
COPY relay.py /app/relay.py

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/__apg/healthz', timeout=2).status==200 else 1)"]

# Exec form: the process receives SIGTERM directly. No argument: the relay reads
# its four values from the environment and nothing else.
ENTRYPOINT ["python", "-u", "/app/relay.py"]

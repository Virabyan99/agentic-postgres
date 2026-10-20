# Session 43 console (ADR 0280).
#
# One stage: every file it serves is this repository's own, so there is no
# bundle to fetch and nothing third-party to vendor. The base image arrives as
# a build argument from versions.env (`PYTHON_RUNTIME_IMAGE`, passed by
# compose.yaml as PYTHON_BASE_IMAGE, the docs image's spelling) with no
# default: a missing argument fails the build rather than floating (ADR 0077).
ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE}

# 65532:65532, the docs image's numeric nonroot pair and compose.yaml's `user:`.
RUN set -eu; \
    groupadd --gid 65532 nonroot; \
    useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot

WORKDIR /app
COPY public /app/public
COPY serve.py /app/serve.py

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/__apg/healthz', timeout=2).status==200 else 1)"]

# Exec form: the process receives SIGTERM directly and its shutdown handler runs.
ENTRYPOINT ["python", "-u", "/app/serve.py"]

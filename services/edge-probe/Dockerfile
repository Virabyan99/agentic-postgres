# Session 2 edge probe.
#
# The base image is supplied as a build argument rather than written here, so
# versions.env stays the single authority for what this is built from. A FROM
# line naming a tag would be a second, unlocked version declaration, and
# bin/lock-versions.sh could not see it.
#
# The caller must pass a digest-pinned reference:
#   --build-arg BASE_IMAGE=${PYTHON_RUNTIME_IMAGE}
# and bin/compose.sh wires that from the lock. There is deliberately no default.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# Build steps run with BuildKit networking disabled (see bin/compose.sh runtime
# mode), so nothing here may fetch. Everything the probe needs is in the base
# image's standard library, which is why there is no package installation step.

# 65532:65532 is the conventional "nonroot" pair and matches the `user:` in
# compose.yaml. The numbers are fixed rather than named because the secret
# contract declares numeric ownership, and a name resolved inside the image
# could disagree with the numeric owner set on the host.
RUN set -eu; \
    groupadd --gid 65532 nonroot; \
    useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot

WORKDIR /app
COPY probe.py /app/probe.py

USER 65532:65532

EXPOSE 8080

# Container-local, so it works with a read-only root filesystem and no shell
# utilities. The probe answers its own health path.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/__apg/healthz', timeout=2).status==200 else 1)"]

# Exec form: the process must receive SIGTERM directly so its shutdown handler
# runs, rather than sitting behind a shell that would swallow the signal.
ENTRYPOINT ["python", "-u", "/app/probe.py"]

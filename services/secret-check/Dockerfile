# Session 2 secret-check.
#
# Same shape as the edge probe: the base image arrives as a build argument so
# versions.env stays the single authority, and there is no default.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# No package installation. Builds run with BuildKit networking disabled and
# consume no build secrets -- this image must not be able to acquire anything
# during a build, because it is the one image whose whole job is handling
# secret material at runtime.

# Must match both `user:` in compose.yaml and the numeric uid/gid declared for
# this service's consumers in secrets.required.yaml. The host sets that
# ownership on the secret files before Compose mounts them, so a mismatch here
# produces a file the process cannot read.
RUN set -eu; \
    groupadd --gid 65532 nonroot; \
    useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot

WORKDIR /app
COPY check.py /app/check.py

USER 65532:65532

ENTRYPOINT ["python", "-u", "/app/check.py"]

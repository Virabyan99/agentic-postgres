# Session 4 client compatibility fixture: Psycopg 3.
#
# The base image arrives as a build argument so versions.env stays the single
# authority, and there is no default.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# --require-hashes, which makes pip refuse the whole file if any requirement
# lacks a hash. That is the flag that turns requirements.txt from a list of
# versions into a lock: without it, a package resolved from an index that has
# been tampered with installs quietly.
#
# psycopg[binary] rather than plain psycopg: the binary wheel carries its own
# libpq, so this image needs no apt step and therefore no second, unlocked
# version declaration for the library actually being tested.
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /app/requirements.txt

COPY probe.py /app/probe.py
COPY entrypoint.sh /app/entrypoint.sh

# Must match `user:` in compose.yaml and the uid/gid declared for this service's
# consumer entry in secrets.required.yaml. The host sets that ownership on the
# secret file before Compose mounts it, so a mismatch here produces a file the
# process cannot read.
RUN set -eu; \
    groupadd --gid 65532 nonroot; \
    useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot

USER 65532:65532

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

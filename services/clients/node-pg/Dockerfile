# Session 4 client compatibility fixture: node-postgres.
#
# The base image arrives as a build argument so versions.env stays the single
# authority, and there is no default.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# `npm ci`, not `npm install`. `ci` installs exactly what package-lock.json
# records and fails if package.json and the lock disagree, which is the only
# form that makes a committed lock file load-bearing rather than decorative.
# `--ignore-scripts` because a postinstall script is arbitrary code from the
# dependency tree running at build time, and nothing in this tree needs one.
WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund

COPY probe.mjs /app/probe.mjs
COPY entrypoint.sh /app/entrypoint.sh

# 65532 is the conventional distroless "nonroot" uid/gid and is the number used
# by every Session 2 consumer. It matches `user:` in compose.yaml and the uid/gid
# declared for this service's consumer entry in secrets.required.yaml; the host
# sets that ownership on the secret file before Compose mounts it, so a mismatch
# here produces a file the process cannot read.
RUN set -eu; \
    addgroup -g 65532 nonroot; \
    adduser -u 65532 -G nonroot -H -D -s /sbin/nologin nonroot

USER 65532:65532

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

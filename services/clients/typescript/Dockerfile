# Session 23 toolchain image: typechecks a GENERATED client, and runs its smoke.
#
# Unlike the four Session 4 fixtures beside it, this image is not a driver
# reaching the database. It holds a compiler, and its whole purpose is that the
# thing this product writes for a developer is checked by one before it is
# committed -- the defect D1223 records (an emitted client that did not compile,
# past eight green structural proofs) is the reason it exists.
#
# The base image arrives as a build argument so versions.env stays the single
# authority, and there is no default.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# `npm ci`, not `npm install`. `ci` installs exactly what package-lock.json
# records and fails if package.json and the lock disagree, which is the only
# form that makes a committed lock file load-bearing rather than decorative.
# `--ignore-scripts` because a postinstall script is arbitrary code from the
# dependency tree running at build time.
#
# **Not `--omit=dev`**: typescript and @types/node are `dependencies` here, not
# devDependencies, because for this image they are not a development
# convenience -- they ARE the image.
WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci --ignore-scripts --no-audit --no-fund

COPY entrypoint.sh /app/entrypoint.sh

# 65532 is the conventional distroless "nonroot" uid/gid, the number every
# Session 2 consumer uses. A generated client is mounted at /work READ-ONLY and
# nothing here writes to it: a toolchain that wrote into the directory it was
# handed would dirty the checkout it was asked to check.
RUN set -eu; \
    addgroup -g 65532 nonroot; \
    adduser -u 65532 -G nonroot -H -D -s /sbin/nologin nonroot

USER 65532:65532

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

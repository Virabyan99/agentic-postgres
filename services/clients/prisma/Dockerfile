# Session 4 client compatibility fixture: Prisma at the locked major (D86).
#
# The base image arrives as a build argument so versions.env stays the single
# authority, and there is no default.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# `npm ci`, not `npm install`: it installs exactly what package-lock.json
# records and fails if package.json and the lock disagree, which is what makes a
# committed lock file load-bearing rather than decorative.
#
# The dev dependency IS installed here, unlike the other Node fixture. `prisma`
# is the CLI that runs `migrate deploy`, and DBX-001 is a claim about that
# command; omitting it would leave the image able to prove only half of what
# this fixture exists for.
#
# --ignore-scripts, and then `prisma generate` explicitly. Prisma's postinstall
# runs `generate` as a side effect of installing, which means a build failure
# there reports as an install failure; running it as its own step makes the
# generated client a visible artefact of the build rather than a side effect.
WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci --ignore-scripts --no-audit --no-fund

COPY prisma /app/prisma
RUN node_modules/.bin/prisma generate

COPY probe.mjs migrate.mjs url.mjs entrypoint.sh /app/

# Must match `user:` in compose.yaml and the uid/gid declared for this service's
# consumer entries in secrets.required.yaml -- both of them, since this is the
# one fixture that holds two credentials.
RUN set -eu; \
    addgroup -g 65532 nonroot; \
    adduser -u 65532 -G nonroot -H -D -s /sbin/nologin nonroot

USER 65532:65532

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

#!/bin/sh
#
# Two modes, named rather than inferred.
#
#   migrate  Prisma Migrate through the direct transport (DBX-001).
#   client   Prisma Client through the pooled transport (DBX-002).
#
# One image with a named mode rather than two images, because the thing being
# proved is that ONE schema.prisma and one dependency tree serve both -- which
# is the configuration an application ships. Two images could each be correct
# and the pair could still not be a working application.
#
# No credential is written to a file here, unlike the other three fixtures:
# Prisma has no PGPASSFILE support and no per-field connection options, so the
# value has to reach it inside a URL. url.mjs builds that URL at run time from
# the mounted secret, which is ADR 0034's rule applied a second time.

set -eu

mode="${1:-}"
case "${mode}" in
    migrate) exec node /app/migrate.mjs ;;
    client) exec node /app/probe.mjs ;;
    "")
        printf 'client-prisma: a mode is required: migrate | client\n' >&2
        exit 2
        ;;
    *)
        printf 'client-prisma: unknown mode: %s (expected migrate or client)\n' "${mode}" >&2
        exit 2
        ;;
esac

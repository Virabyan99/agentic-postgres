# The project's PostgreSQL image: the pinned upstream one, plus an archiver.
#
# **This is the first time this repository builds its own database image**, and
# ADR 0144 is why it has to. `archive_command` is run by the postmaster, inside
# this container, and must return non-zero synchronously for a segment to count
# as unarchived. A sidecar sharing the data volume can take a backup; it cannot
# serve an archive command. So pgBackRest lives here or continuous WAL archiving
# does not exist.
#
# The base and the package version arrive as build arguments with NO defaults,
# which is `services/auth-api/Dockerfile`'s rule and its reason: a `FROM` naming
# a tag, or an `apt-get install pgbackrest` with a version written here, would be
# a second unlocked version declaration that `bin/lock-versions.sh` cannot see --
# which is how SCALAR_VERSION named a release that never existed for four
# sessions (D201, ADR 0077). A missing argument fails the build rather than
# floating.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG PGBACKREST_APT_VERSION
ARG CA_CERTIFICATES_APT_VERSION

# Measured in Run 1 against this exact base digest, with a control (the same
# build at `pgbackrest=0.0.0-doesnotexist`, which exits 100):
#
#   * the PGDG repository is ALREADY configured in the base image, so no key and
#     no source list are added here;
#   * this pin installs exactly two packages -- `pgbackrest` and `libssh2-1` --
#     and adds 800,863 bytes to a 158,801,932-byte base;
#   * `libssh2-1` is precisely the library the rejected multi-stage COPY route
#     was missing, which is the whole of why that route is not this one (D531).
#
# `--no-install-recommends` because the recommends set for pgbackrest pulls in a
# mail transport agent, and a database container has no business holding one.
#
# The apt lists are removed in the SAME layer they are created in, so the ~40 MB
# `apt-get update` writes does not survive into the image. Split across two RUNs
# it would persist in the lower layer and the delete would only mask it.
#
# `pgbackrest version` at the end of the layer is not decoration: it is the
# difference between "the package installed" and "the binary runs", which ADR
# 0083 records as two different claims after `psycopg` installed cleanly and
# raised ImportError on first use.
# `ca-certificates` is installed in the SAME layer and is not optional: the
# repository is reached over HTTPS and this image ships no trust store at all.
# Measured (D590): `/etc/ssl/certs/ca-certificates.crt` is absent from the base,
# the package is in neither pgbackrest's Depends nor its Recommends, and without
# it pgBackRest connects to R2 and then refuses the certificate with
# `[095] ... [20] unable to get local issuer certificate`.
#
# No rig caught this because every rig used a POSIX repository on a local
# volume, so nothing ever negotiated TLS -- ADR 0065/0066's warning about a
# proof that reaches the right end state by a route the product does not take.
#
# `update-ca-certificates` is not run explicitly: the package's own postinst
# does it, and the `test -s` below is what proves the bundle exists rather than
# trusting that.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        "pgbackrest=${PGBACKREST_APT_VERSION}" \
        "ca-certificates=${CA_CERTIFICATES_APT_VERSION}"; \
    rm -rf /var/lib/apt/lists/*; \
    pgbackrest version; \
    test -s /etc/ssl/certs/ca-certificates.crt

# The directories pgBackRest writes to that are NOT the repository: its log and
# its async spool. Created here, owned by the postmaster's own uid, because the
# container runs as `999:999` and cannot create them at start -- `/var/log` and
# `/var/spool` are root-owned in the base image.
#
# 999:999 rather than a name: a name resolved inside the image could disagree
# with the numeric owner the host sets on the mounted secrets, which is the
# reason `services/edge-probe` gives for doing the same thing.
RUN set -eux; \
    install -d -o 999 -g 999 -m 0750 /var/log/pgbackrest; \
    install -d -o 999 -g 999 -m 0750 /var/spool/pgbackrest

# No USER line, no ENTRYPOINT, no CMD. The base image's entrypoint is what
# initialises a cluster and it is deliberately untouched; `compose.yaml` sets
# `user: "999:999"` and the postgres command line, exactly as it did before this
# image existed. What changed is that the binary is present -- nothing else.

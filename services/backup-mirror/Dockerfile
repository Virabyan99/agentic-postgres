# The mirror client (ADR 0188): the primary backup repository's bucket copied
# object for object to a bucket at a second provider, by a scheduled host unit
# and never by the archiver.
#
# Built rather than pulled, for the reason every other service image is: the
# base is pinned by digest in versions.env and arrives as a build argument, and
# the one file added is the script the unit runs. The image is MinIO's client,
# a single static binary in a minimal base with no shell utilities beyond `sh`
# (measured: no `grep`, no `awk`, D1001), so everything the script prints is
# what `mc` prints, and every count is taken on the host from `mc ls --json`.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# The client's config directory has to be writable and is not a place a
# credential lives: aliases are supplied through MC_HOST_* in the process
# environment, built by mirror.sh from the mounted secret files, so no alias
# is ever written to disk.
ENV MC_CONFIG_DIR=/tmp/mc

COPY mirror.sh /usr/local/bin/mirror.sh
ENTRYPOINT ["/usr/local/bin/mirror.sh"]

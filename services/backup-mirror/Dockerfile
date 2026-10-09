# The mirror client (ADR 0188): the primary backup repository's bucket copied
# object for object to a bucket at a second provider, by a scheduled host unit
# and never by the archiver.
#
# Built rather than pulled, for the reason every other service image is: the
# base is pinned by digest in versions.env and arrives as a build argument, and
# the one file added is the script the unit runs. The image is rclone's
# (ADR 0264): MinIO's `mc` was the client until its images and binaries stopped
# being served anonymously (D2285: quay.io and Docker Hub 401, dl.min.io 410).
# rclone's image is Alpine with `/bin/sh`; everything the script prints is what
# rclone prints, and the count is `rclone size --json`, read on the host.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# No config file is read or written: the two remotes arrive as RCLONE_CONFIG_*
# in the process environment, built by mirror.sh from the mounted secret files
# (RCLONE_CONFIG=/dev/null there). HOME points somewhere writable for a client
# that runs as uid 65532 on a read-only root; nothing was measured landing in it.
ENV HOME=/tmp

COPY mirror.sh /usr/local/bin/mirror.sh
ENTRYPOINT ["/usr/local/bin/mirror.sh"]

# Session 5 documentation service: a vendored Scalar bundle and a server that
# refuses to serve anything else (ADR 0069, D128, D202).
#
# Two stages, two base images, both supplied as build arguments so versions.env
# stays the single authority. A `FROM` line naming a tag would be a second,
# unlocked version declaration that bin/lock-versions.sh could not see. There
# are deliberately no defaults.
#
# The build stage exists because the published Scalar bundle is **not
# self-contained** and no version of it is: measured on 1.36.2 and 1.64.1,
# `dist/browser/standalone.js` names `fonts.scalar.com` fourteen times and
# `proxy.scalar.com` beside it, and `withDefaultFonts` is declared `default:
# true`. Vendoring the file is what lets this deployment serve it under its own
# Content-Security-Policy; an image whose bytes and headers belong to somebody
# else could not.
ARG NODE_BASE_IMAGE
ARG PYTHON_BASE_IMAGE

FROM ${NODE_BASE_IMAGE} AS bundle

# `npm ci`, not `npm install`: it installs exactly what package-lock.json
# records and fails if the two disagree, which is what makes a committed lock
# load-bearing rather than decorative. `--ignore-scripts` because a
# documentation page has no business running a dependency's install hooks.
WORKDIR /build
COPY package.json package-lock.json /build/
RUN npm ci --ignore-scripts --no-audit --no-fund

# One file leaves this stage. The install is ~230 MB and the page needs a single
# script; copying the tree would ship a build environment to a public route.
RUN set -eu; \
    mkdir -p /out; \
    cp /build/node_modules/@scalar/api-reference/dist/browser/standalone.js /out/standalone.js; \
    test -s /out/standalone.js


FROM ${PYTHON_BASE_IMAGE}

# 65532:65532 is the conventional "nonroot" pair and matches the `user:` in
# compose.yaml. Numeric rather than named for the reason the edge probe gives:
# a name resolved inside the image could disagree with the numeric owner the
# secret contract declares on the host.
RUN set -eu; \
    groupadd --gid 65532 nonroot; \
    useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot

WORKDIR /app
COPY --from=bundle /out/standalone.js /app/public/standalone.js
COPY index.html /app/public/index.html
COPY serve.py /app/serve.py

# The reviewed OpenAPI snapshot is **mounted**, not baked. It is the artefact a
# human approved (`contracts/postgrest-openapi.canonical.json`), and baking it
# would mean a documentation image per project per revision, each one a place
# the reviewed bytes could differ from the reviewed bytes.
VOLUME ["/app/snapshot"]

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/__apg/healthz', timeout=2).status==200 else 1)"]

# Exec form: the process must receive SIGTERM directly so its shutdown handler
# runs rather than sitting behind a shell that would swallow the signal.
ENTRYPOINT ["python", "-u", "/app/serve.py"]

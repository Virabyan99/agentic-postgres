# Session 47 Run 6: the image the served Go `pgx` snippet runs in
# (tests/contract/test_connection_snippets.py). Test-only.
#
# The base arrives as a build argument (GO_RUNTIME_IMAGE from versions.env, by
# digest). `go mod download` verifies every module against the committed
# go.sum; the warm build fills the build cache, so the test's own compile reads
# nothing from a network (GOPROXY=off, GOFLAGS=-mod=readonly, no toolchain
# download).
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENV GOTOOLCHAIN=local
WORKDIR /src
COPY go.mod go.sum warm.go /src/
RUN go mod download && go build -o /dev/null .
ENV GOPROXY=off GOFLAGS=-mod=readonly

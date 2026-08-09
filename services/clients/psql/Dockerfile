# Session 4 client compatibility fixture: psql.
#
# The base image arrives as a build argument so versions.env stays the single
# authority, and there is no default. It is the *pooler* image rather than the
# cluster image, and that is a decision rather than convenience: Run 1 measured
# psql 17.5 in it against the locked digest, it is already pulled on any host
# running this project, and its uid/gid 70 is the number secrets.required.yaml
# already declares for a consumer of app_runtime_password.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# No package installation. This image runs a shell script against a client that
# the base image already ships; adding a package manager step would introduce a
# second, unlocked version declaration for the one binary being tested.

WORKDIR /app
COPY probe.sh entrypoint.sh /app/

# 65532:65532, and NOT the base image's own 70. The number here is not inherited
# from whatever the base image happens to run as; it is the number
# secrets.required.yaml declares for this service's consumer and that
# compose.yaml sets as `user:`, cross-checked by
# tests/contract/test_secret_contract.py. Every built service in this model runs
# as 65532, which is what makes that a property rather than a coincidence.
#
# No passwd entry is created. A numeric USER needs none, psql is invoked with
# -X so no user's .psqlrc is read, and PGUSER and PGPASSFILE are both explicit
# -- so nothing here resolves the running uid to a name or a home directory.
# Adding a user would be one more thing to keep in step with a base image this
# fixture does not otherwise depend on.
USER 65532:65532

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

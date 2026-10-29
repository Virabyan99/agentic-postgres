# Session 47 Run 6: the image the served psycopg snippet runs in
# (tests/contract/test_connection_snippets.py). Test-only -- the deployment's
# psycopg fixture is services/clients/psycopg, and this is not it.
#
# It carries `certifi` because the snippet does: psycopg[binary]'s bundled
# OpenSSL looks for the system's roots under the directory it was BUILT in
# (OPENSSLDIR "/host/tmp/libpq.build", 3.2.12 and 3.3.4 alike), so
# `sslrootcert=system` verifies against nothing on any machine. The base
# arrives as a build argument (PYTHON_RUNTIME_IMAGE, by digest); every
# requirement is installed by hash.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /app/requirements.txt

# Session 47 Run 6: the image the served Drizzle snippet runs in
# (tests/contract/test_connection_snippets.py). Test-only -- the deployment's
# client fixtures are services/clients/*, and this is not one of them.
#
# The base arrives as a build argument (NODE_RUNTIME_IMAGE from versions.env,
# by digest), and `npm ci --ignore-scripts` installs exactly the committed
# lock, every entry of which carries an integrity hash.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund

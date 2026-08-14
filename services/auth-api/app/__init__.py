"""The Agentic Postgres auth service.

Session 6. Run 7 built the core -- the frozen Argon2id profile and its bounded
executor, strict request parsing, the bounded compact-JWT pre-parser,
local-only key resolution and the explicitly-opened connection pool. Runs 8 and
9 add the endpoints that use them.

The package is `app` rather than `auth_api` because that is what it is called
inside the image (`WORKDIR /app`), and a package whose import name changes
between the repository and the container is a package whose tests exercise a
different module from the one that runs.
"""

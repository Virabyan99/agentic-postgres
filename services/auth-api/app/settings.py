"""Everything the process reads from its environment, and where each came from.

**No value here is a secret.** The database password arrives as a mounted
`pgpass` file that libpq reads through `PGPASSFILE`, exactly as it does for
PostgREST and for the three client fixtures (ADR 0034, D60): the conninfo is
assembled from derived identifiers and carries `?passfile=`, never a password.
The signing key arrives as a mounted file that is read once at startup. Neither
becomes an environment variable, an argument or a log line.

**Nothing here has a default that would work.** Every setting is required, and
a missing one fails the start. A default would be a second authority for a
value `naming.py` derives and the deployed document publishes -- and the
symptom of a wrong default is a service that starts, connects to the wrong
thing, and reports itself healthy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class MissingSetting(RuntimeError):
    """A required environment variable that was not set.

    Names the variable and nothing else. A message that included the value of a
    neighbouring variable would be a message that could carry a credential into
    a log the moment somebody moved one.
    """


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        # Empty and unset are the same failure. Compose's `${VAR:?required}`
        # refuses an *empty* value as well as an unset one -- measured in
        # Session 5, D178 -- and a service that treated them differently would
        # disagree with the file that starts it.
        raise MissingSetting(f"{name} is required and was not set")
    return value


def _required_int(name: str, *, minimum: int = 1) -> int:
    raw = _required(name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise MissingSetting(f"{name} must be an integer") from exc
    if value < minimum:
        raise MissingSetting(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """The resolved environment. Built once, at startup, or not at all."""

    project_key: str
    environment: str
    issuer: str
    audience: str
    database_host: str
    database_port: int
    database_name: str
    database_role: str
    passfile: Path
    pool_size: int
    signing_key_file: Path
    listen_port: int

    @property
    def conninfo(self) -> str:
        """A libpq conninfo with a passfile reference and no password.

        Assembled here from derived identifiers rather than stored whole, for
        the reason D60 gives about dbmate: a stored URL would put a derived
        role name inside an operator-entered value, where nothing checks it
        against `naming.ROLE_SUFFIXES`.
        """
        return (
            f"host={self.database_host} "
            f"port={self.database_port} "
            f"dbname={self.database_name} "
            f"user={self.database_role} "
            f"passfile={self.passfile} "
            # The service talks to the pooler in transaction mode; a session
            # the pooler cannot hand to another client is a connection the
            # budget paid for and nobody can use.
            "application_name=apg-auth"
        )


def load(environ: dict[str, str] | None = None) -> Settings:
    """Read the environment, or raise.

    `environ` is a parameter so the contract tests can exercise this without a
    process to configure -- and so that "what this service reads" is a list a
    test can assert against rather than a set of `os.environ` lookups scattered
    through the module that happens to need each one.
    """
    if environ is not None:
        previous = dict(os.environ)
        os.environ.clear()
        os.environ.update(environ)
        try:
            return load()
        finally:
            os.environ.clear()
            os.environ.update(previous)

    return Settings(
        project_key=_required("APG_PROJECT_KEY"),
        environment=_required("APG_PROJECT_ENVIRONMENT"),
        issuer=_required("APG_JWT_ISSUER"),
        audience=_required("APG_JWT_AUDIENCE"),
        database_host=_required("APG_DATABASE_HOST"),
        database_port=_required_int("APG_DATABASE_PORT"),
        database_name=_required("APG_DATABASE_NAME"),
        database_role=_required("APG_DATABASE_ROLE"),
        passfile=Path(_required("APG_DATABASE_PASSFILE")),
        pool_size=_required_int("APG_POOL_SIZE"),
        signing_key_file=Path(_required("APG_SIGNING_KEY_FILE")),
        listen_port=_required_int("APG_LISTEN_PORT"),
    )


#: The exact set `load` requires. Declared rather than derived, so that
#: `test_the_compose_service_supplies_every_setting_the_service_requires` can
#: compare it against `compose.yaml` -- which is the check that would have
#: caught D178, where a renderer emitted a variable and the compose file
#: refused the empty value it emitted.
REQUIRED_VARIABLES: tuple[str, ...] = (
    "APG_PROJECT_KEY",
    "APG_PROJECT_ENVIRONMENT",
    "APG_JWT_ISSUER",
    "APG_JWT_AUDIENCE",
    "APG_DATABASE_HOST",
    "APG_DATABASE_PORT",
    "APG_DATABASE_NAME",
    "APG_DATABASE_ROLE",
    "APG_DATABASE_PASSFILE",
    "APG_POOL_SIZE",
    "APG_SIGNING_KEY_FILE",
    "APG_LISTEN_PORT",
)

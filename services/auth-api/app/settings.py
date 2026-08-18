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

#: The two modes one image runs (ADR 0101). Required, never defaulted: an image
#: that picked a mode by omission would start the wrong service with a
#: correct-looking configuration, which is ADR 0055's reasoning applied to
#: behaviour rather than to a value.
APP_MODES: frozenset[str] = frozenset({"auth", "storage"})


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


def _required_role_names(name: str) -> dict[str, str]:
    """The suffix -> derived-name map, parsed strictly.

    Rendered by `rendering.build_compose_env` from `naming.py`, which is the
    single authority for derivation (ADR 0002). Parsed here rather than trusted:
    a map that arrived as a list, or with a non-string value, would produce a
    role name of the wrong type in a signed token.
    """
    import json

    try:
        parsed = json.loads(_required(name))
    except ValueError as exc:
        raise MissingSetting(f"{name} is not valid JSON") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise MissingSetting(f"{name} must be a non-empty JSON object")
    for suffix, role in parsed.items():
        if not isinstance(suffix, str) or not isinstance(role, str) or not suffix or not role:
            raise MissingSetting(f"{name} maps {suffix!r} to something that is not a role name")
    return parsed


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
    #: `None` in storage mode, and its absence is a security property rather
    #: than an optional field (ADR 0101, D320). One image runs both modes and
    #: the boundary is the secret contract's per-consumer materialization: the
    #: `storage` consumer is granted no signing key, so `APG_SIGNING_KEY_FILE`
    #: is absent from its environment and there is nothing on its filesystem to
    #: read. Storage is a third VERIFIER (ADR 0098) and never an issuer.
    signing_key_file: Path | None
    listen_port: int
    role_names: dict[str, str]

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


def load(environ: dict[str, str] | None = None, *, mode: str = "auth") -> Settings:
    """Read the environment, or raise.

    `environ` is a parameter so the contract tests can exercise this without a
    process to configure -- and so that "what this service reads" is a list a
    test can assert against rather than a set of `os.environ` lookups scattered
    through the module that happens to need each one.

    `mode` decides one thing: whether `APG_SIGNING_KEY_FILE` is required. In
    storage mode it must be **absent**, not merely unread (ADR 0101). Tolerating
    it would mean a container that had somehow been handed a signing key would
    start normally and hold one -- and the whole point of running two modes from
    one image is that the credential boundary is enforced somewhere real. Here,
    that is a refusal to start.
    """
    if environ is not None:
        previous = dict(os.environ)
        os.environ.clear()
        os.environ.update(environ)
        try:
            return load(mode=mode)
        finally:
            os.environ.clear()
            os.environ.update(previous)

    if mode not in APP_MODES:
        raise MissingSetting(f"APP_MODE must be one of {sorted(APP_MODES)}, not {mode!r}")

    if mode == "storage":
        # Absent, not ignored. A storage container holding a signing key is a
        # second issuer nobody published, and ADR 0098's whole model is that a
        # verifier's set is decided by what issuers declare -- an undeclared one
        # would verify tokens no verifier was configured for.
        if os.environ.get("APG_SIGNING_KEY_FILE"):
            raise MissingSetting(
                "APG_SIGNING_KEY_FILE is set in storage mode; storage is a verifier "
                "and never an issuer, and must be granted no signing key (ADR 0101)"
            )
        signing_key_file: Path | None = None
    else:
        signing_key_file = Path(_required("APG_SIGNING_KEY_FILE"))

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
        signing_key_file=signing_key_file,
        listen_port=_required_int("APG_LISTEN_PORT"),
        role_names=_required_role_names("APG_ROLE_NAMES"),
    )


#: The exact set `load` requires. Declared rather than derived, so that
#: `test_the_compose_service_supplies_every_setting_the_service_requires` can
#: compare it against `compose.yaml` -- which is the check that would have
#: caught D178, where a renderer emitted a variable and the compose file
#: refused the empty value it emitted.
#: What both modes read.
SHARED_VARIABLES: tuple[str, ...] = (
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
    "APG_LISTEN_PORT",
    "APG_ROLE_NAMES",
)

REQUIRED_VARIABLES: tuple[str, ...] = (*SHARED_VARIABLES, "APG_SIGNING_KEY_FILE")

#: Session 7. What the storage mode reads INSTEAD of the signing key, plus the
#: six settings that are its own. Declared beside the auth set so
#: `test_the_compose_service_supplies_every_setting_the_service_requires` can
#: compare each mode against the Compose service that runs it -- one list per
#: mode, because a single union would be satisfied by a compose file that gave
#: every variable to both services, which is the boundary ADR 0101 relies on.
STORAGE_VARIABLES: tuple[str, ...] = (
    *SHARED_VARIABLES,
    "APG_STORAGE_ENDPOINT",
    "APG_STORAGE_BUCKET",
    "APG_STORAGE_PREFIX",
    "APG_STORAGE_ACCESS_KEY_ID_FILE",
    "APG_STORAGE_SECRET_ACCESS_KEY_FILE",
    "APG_STORAGE_UPLOAD_URL_TTL_SECONDS",
    "APG_STORAGE_DOWNLOAD_URL_TTL_SECONDS",
    "APG_STORAGE_MAX_UPLOAD_BYTES",
)

#: The variable each mode must NOT be given. Stated as a set rather than left
#: implicit, because "storage has no signing key" is only a property if
#: something checks it -- and what checks it is `load`, which refuses to start.
FORBIDDEN_VARIABLES: dict[str, tuple[str, ...]] = {
    "auth": (),
    "storage": ("APG_SIGNING_KEY_FILE",),
}

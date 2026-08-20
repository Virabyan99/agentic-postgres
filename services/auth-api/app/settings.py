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

#: The three modes one image runs (ADR 0101, extended by ADR 0121). Required,
#: never defaulted: an image that picked a mode by omission would start the
#: wrong service with a correct-looking configuration, which is ADR 0055's
#: reasoning applied to behaviour rather than to a value.
#:
#: `mcp` is Session 8's, and it is the first mode that reads NO database
#: settings at all. It is a mode of this image rather than a second service
#: directory for the reason `compose.yaml` gives at `storage`: a second
#: directory could not import `LocalKeySet`, the strict request parser or the
#: error vocabulary -- and the fourth verifier getting a second key-set parser
#: is how D381 happened to the third.
APP_MODES: frozenset[str] = frozenset({"auth", "storage", "mcp"})


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


def _required_http_url(name: str) -> str:
    """A required `http://` or `https://` URL, with no credential in it.

    Parsed rather than trusted, for the reason every other setting here is: a
    value that arrived as `postgres://user:pass@...` would put a credential into
    an environment variable and then into `docker inspect` (D60) -- and a value
    that arrived as a bare hostname would be concatenated into a request path
    and reach a different service entirely.

    The userinfo check is not theoretical. `PGRST_DB_URI` in the same deployment
    IS a `postgres://` URL with an authenticator role in it, so the two spellings
    sit metres apart in `compose.yaml`, and the failure of confusing them is a
    request that succeeds against the wrong thing.
    """
    value = _required(name)
    if not value.startswith(("http://", "https://")):
        raise MissingSetting(f"{name} must be an http:// or https:// URL")
    authority = value.split("://", 1)[1].split("/", 1)[0]
    if "@" in authority:
        raise MissingSetting(f"{name} carries userinfo; a credential must not travel in a URL")
    if not authority:
        raise MissingSetting(f"{name} names no host")
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
    #: Where a NON-ISSUING verifier reads its key set (ADR 0113). `None` in auth
    #: mode, where the set is derived from the signing key -- an issuer that
    #: verified with anything other than what it signs with is the split ADR
    #: 0098 exists to prevent.
    #:
    #: Exactly one of these two fields is set in either mode, and that is the
    #: point. D381 was a container told it was the third verifier and given
    #: nothing to verify with, because the key set was *implied* by a field that
    #: is deliberately absent here.
    jwks_file: Path | None
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


@dataclass(frozen=True, slots=True)
class McpSettings:
    """The agent plane's environment, and what it does NOT contain is the point.

    A separate type rather than `Settings` with six optional fields, because the
    database members of `Settings` are not "unused here" -- they are **forbidden
    here** (ADR 0121, D407). The MCP runtime holds no database credential, which
    is why it takes no share of ADR 0099's connection budget, and a dataclass
    whose `database_role` was merely `None` would make that zero an accident
    rather than a decision: the next person to need a connection would find a
    field waiting for a value.

    So there is no `conninfo` property here, no pool size and no passfile. The
    only way to add one is to add it, in front of a reviewer, with the budget
    arithmetic to answer for.
    """

    project_key: str
    environment: str
    issuer: str
    audience: str
    #: Required, not optional. MCP is the FOURTH verifier (ADR 0113, ADR 0122)
    #: and issues nothing, so this is its only source of key material. A
    #: verifier with no key set refuses every token, and a container that starts
    #: and refuses everything is worse than one that does not start -- it looks
    #: deployed. That sentence is D381's epitaph and it is repeated here because
    #: this is the boundary where it would happen again.
    jwks_file: Path
    listen_port: int
    #: Where the agent plane asks who its caller is (ADR 0125).
    #:
    #: A URL rather than a host and a port, because the agent plane never
    #: assembles an address -- the same rule ADR 0106 states for the storage
    #: endpoint. `naming`/`rendering` derive it and hand it over finished, so
    #: there is one authority for how PostgREST is addressed and this image is
    #: not it (ADR 0002).
    #:
    #: This is **not** a database credential and does not make the agent plane a
    #: claimant on ADR 0099's connection budget: the request is HTTP, it carries
    #: the CALLER's token, and the connection it costs is PostgREST's own -- one
    #: already counted in the api share of 13.
    postgrest_url: str
    #: The deployed capability lock (ADR 0127).
    #:
    #: Required, and read once at startup. A runtime without it serves no tools
    #: at all, so starting without one would be a container that looks deployed
    #: and answers every discovery with an empty list -- D381's shape applied to
    #: a capability surface rather than to a key set.
    capability_lock_file: Path


def load_mcp(environ: dict[str, str] | None = None) -> McpSettings:
    """Read the agent plane's environment, or raise.

    Split from `load` rather than folded into it because the two return
    different shapes and share no database settings at all. What they DO share
    is the discipline: every setting required, none defaulted, and the variables
    a mode must not receive refused rather than ignored.
    """
    if environ is not None:
        previous = dict(os.environ)
        os.environ.clear()
        os.environ.update(environ)
        try:
            return load_mcp()
        finally:
            os.environ.clear()
            os.environ.update(previous)

    for name in FORBIDDEN_VARIABLES["mcp"]:
        if os.environ.get(name):
            raise MissingSetting(
                f"{name} is set in mcp mode. The agent plane verifies tokens and reaches "
                "PostgREST over HTTP as the caller; it holds no signing key and no database "
                "credential, and its zero share of the connection budget is a decision "
                "(ADR 0121, D407) rather than an omission"
            )

    return McpSettings(
        project_key=_required("APG_PROJECT_KEY"),
        environment=_required("APG_PROJECT_ENVIRONMENT"),
        issuer=_required("APG_JWT_ISSUER"),
        audience=_required("APG_JWT_AUDIENCE"),
        jwks_file=Path(_required("APG_JWKS_FILE")),
        listen_port=_required_int("APG_LISTEN_PORT"),
        postgrest_url=_required_http_url("APG_POSTGREST_URL"),
        capability_lock_file=Path(_required("APG_MCP_LOCK_FILE")),
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

    if mode == "mcp":
        # Refused rather than handled, because every field below it is a
        # database setting the agent plane must not have (ADR 0121). Falling
        # through would take the `else` branch and demand a SIGNING KEY of the
        # one runtime furthest from being an issuer -- a wrong answer that looks
        # like a configuration mistake.
        raise MissingSetting(
            "mcp mode has no database settings and is loaded by load_mcp(); "
            "Settings is the auth and storage shape"
        )

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
        # Required, not optional. A verifier with no key set refuses every
        # token, and a container that starts and refuses everything is worse
        # than one that does not start: it looks deployed (ADR 0113, D381).
        jwks_file: Path | None = Path(_required("APG_JWKS_FILE"))
    else:
        signing_key_file = Path(_required("APG_SIGNING_KEY_FILE"))
        # Absent in auth mode, and refused rather than ignored, for the same
        # reason storage refuses a signing key: two sources for one key set is
        # two authorities for one value (D264), and the issuer's set must be
        # what it signs with.
        if os.environ.get("APG_JWKS_FILE"):
            raise MissingSetting(
                "APG_JWKS_FILE is set in auth mode; an issuer verifies with what it signs "
                "with, and must not be given a second key set (ADR 0113)"
            )
        jwks_file = None

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
        jwks_file=jwks_file,
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
    # What it verifies with (ADR 0113). Its absence from this list is half of
    # why D381 survived a green suite: the list and `compose.yaml` agreed, and
    # a test comparing two incomplete lists is satisfied by both (D332).
    "APG_JWKS_FILE",
    "APG_STORAGE_ENDPOINT",
    "APG_STORAGE_BUCKET",
    "APG_STORAGE_PREFIX",
    "APG_STORAGE_ACCESS_KEY_ID_FILE",
    "APG_STORAGE_SECRET_ACCESS_KEY_FILE",
    "APG_STORAGE_UPLOAD_URL_TTL_SECONDS",
    "APG_STORAGE_DOWNLOAD_URL_TTL_SECONDS",
    "APG_STORAGE_MAX_UPLOAD_BYTES",
)

#: Session 8. What the agent plane reads, and it is SHARED_VARIABLES minus every
#: database setting rather than plus anything (ADR 0121). Six entries, and the
#: six that are absent -- `APG_DATABASE_HOST`, `_PORT`, `_NAME`, `_ROLE`,
#: `_PASSFILE` and `APG_POOL_SIZE` -- are the list that matters: they are in
#: `FORBIDDEN_VARIABLES["mcp"]` below, so their absence is enforced rather than
#: observed.
#:
#: `APG_ROLE_NAMES` is absent too, and for a different reason: it exists so the
#: issuer can put a derived role name in a token it MINTS. The agent plane mints
#: nothing and forwards the caller's own token (D407), so a role map here would
#: be a setting nobody reads -- which is how a value stops being checked and
#: starts being believed.
MCP_VARIABLES: tuple[str, ...] = (
    "APG_PROJECT_KEY",
    "APG_PROJECT_ENVIRONMENT",
    "APG_JWT_ISSUER",
    "APG_JWT_AUDIENCE",
    "APG_JWKS_FILE",
    "APG_LISTEN_PORT",
    # Session 8 Run 5. Where the agent plane asks who its caller is (ADR 0125).
    # An HTTP address, not a conninfo: the request carries the CALLER's token
    # and this runtime still holds no database credential.
    "APG_POSTGREST_URL",
    # Session 8 Run 6. The compiled capability lock this project serves
    # (ADR 0127). A file, mounted read-only, exactly as the key set is.
    "APG_MCP_LOCK_FILE",
)

#: The variable each mode must NOT be given. Stated as a set rather than left
#: implicit, because "storage has no signing key" is only a property if
#: something checks it -- and what checks it is `load`, which refuses to start.
FORBIDDEN_VARIABLES: dict[str, tuple[str, ...]] = {
    # An issuer verifies with what it signs with, so a second key set is
    # refused rather than ignored (ADR 0113).
    "auth": ("APG_JWKS_FILE",),
    "storage": ("APG_SIGNING_KEY_FILE",),
    # The longest list, and every entry is load-bearing. A signing key would
    # make a verifier into an undeclared issuer (ADR 0098); a database setting
    # would make ADR 0099's considered zero into an oversight (D407). D309 was
    # the opposite mistake -- a service added with no term in the budget -- and
    # the only difference between a considered zero and an oversight is whether
    # something refuses to start.
    "mcp": (
        "APG_SIGNING_KEY_FILE",
        "APG_DATABASE_HOST",
        "APG_DATABASE_PORT",
        "APG_DATABASE_NAME",
        "APG_DATABASE_ROLE",
        "APG_DATABASE_PASSFILE",
        "APG_POOL_SIZE",
    ),
}

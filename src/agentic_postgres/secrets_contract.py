"""Secret requirements contract (Session 2, Phase 2).

`secrets.required.yaml` declares *which* secrets exist, *which* service consumes
each one, and *under what numeric ownership* it is materialized. It never
declares a value, and this module never reads one — every function here operates
on identifiers.

The design commitment recorded in `docs/decisions/0010-secret-materialization.md`
is that a secret is an **individual file granted to one service**, not an entry
in an environment bundle. Two consequences shape this module:

* a provider secret consumed by two services is materialized as two separate
  files, one per consumer directory, so there is no shared path whose
  permissions have to satisfy two different runtime users;
* the *source path* is derived from the project key by the materializer and can
  never be supplied from a manifest, because a manifest that could name its own
  secret directory could name another project's.

The session filter matters more than it looks. `active_secrets(contract, 2)`
returns only secrets introduced by session 2 or earlier, so a Session 3 database
credential declared here does not become a Session 2 Compose mount — which is
what lets later sessions append to this file without changing Session 2's
tested grant surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_postgres import config
from agentic_postgres.config import ManifestError

#: Where a materialized generation lives. `{project_key}` and `{generation_id}`
#: are substituted by the materializer; nothing in a manifest reaches this.
#: S105 is a false positive twice over here: these are directory paths, and the
#: whole point of this module is that it handles *names* and never a value.
SECRET_ROOT = "/var/lib/agentic-postgres/secrets"  # noqa: S105

#: Where Compose exposes a granted file inside a container.
CONTAINER_SECRET_DIR = "/run/secrets"  # noqa: S105

#: The generation subdirectory holding root-plane files (ADR 0054).
#:
#: An underscore, and that is the whole design: the Compose service pattern is
#: ``^[a-z][a-z0-9-]{1,30}$``, which admits no underscore, so no service can ever
#: name this directory. A root-plane file and a service's directory cannot
#: collide by construction rather than by anybody remembering not to.
ROOT_PLANE_DIRECTORY = "_root"

#: The two planes a consumer can be on. `compose` is a container that mounts the
#: file; `root` is a value no container may hold at all.
PLANES = ("compose", "root")

#: What the materializer writes into a consumer's file (ADR 0056).
FORMATS = ("raw", "pgpass")

#: Who creates a secret's value (ADR 0103), which is a different question from
#: what kind of value it is.
#:
#: `generated` is every secret through Session 6: the provider bootstrap makes
#: one from `value_kind`. `operator_supplied` is a value that exists only
#: because a third party issued it, so there is nothing to generate and the
#: bootstrap must say so rather than converge.
#:
#: A separate field rather than a widened `value_kind`, because the R2 secret
#: access key answers both questions and the answers do not agree: Cloudflare
#: defines it as the SHA-256 of the API token value, so it *is* a 64-character
#: hex string, and `secrets.token_hex(32)` would produce something
#: indistinguishable from a credential nobody issued.
ORIGINS = ("generated", "operator_supplied")

#: The origin that no generator may run for.
OPERATOR_SUPPLIED = "operator_supplied"

#: The `pgpass` template. Wildcards in all four match fields, deliberately: the
#: alternative names a host, a port, a database and a role that `naming.py`
#: already derives, which is a second derivation path inside a secret file and a
#: file that goes stale when any of them changes. The narrowing buys nothing --
#: the file is `0400`, owned by the one uid its container runs as, and that
#: container has exactly one connection target.
PGPASS_TEMPLATE = "*:*:*:*:{value}\n"


def load_secret_contract(path: Path) -> dict[str, Any]:
    """Parse, schema-validate and semantically validate the requirements file."""
    document = config.load_manifest(path)
    config.assert_no_sensitive_keys(document)
    config.validate_against_schema(document, "secret-contract.schema.json")
    _validate_semantics(document)
    return document


def active_secrets(contract: dict[str, Any], session: int) -> list[dict[str, Any]]:
    """Secrets introduced by ``session`` or earlier, in declaration order."""
    return [s for s in contract["secrets"] if s["introduced_in_session"] <= session]


def is_operator_supplied(secret: dict[str, Any]) -> bool:
    """Whether this secret's value can only come from a third party (ADR 0103).

    Read from the declared ``origin`` and never inferred from the name or the
    provider path. Inferring is how `value_kind` came to be doing this job by
    implication: every secret was generated, so nothing had to say so, and the
    first secret that was not would have been generated anyway.
    """
    return secret["origin"] == OPERATOR_SUPPLIED


def operator_supplied_secrets(contract: dict[str, Any], session: int) -> list[dict[str, Any]]:
    """Active secrets an operator has to obtain and paste, in declaration order.

    What ``--plan`` names separately, because the operator's next action for one
    of these is not "run --apply" -- it is to go to a third party's console,
    issue a credential, and put the value in the provider by hand (D249).
    """
    return [secret for secret in active_secrets(contract, session) if is_operator_supplied(secret)]


def is_root_plane(consumer: dict[str, Any]) -> bool:
    """Whether this consumer is a value no container may hold (ADR 0054).

    Read from the declared ``plane`` and never inferred from the absence of a
    service. Inferring would make a consumer that lost its service key by
    accident indistinguishable from one that was deliberately put out of every
    container's reach.
    """
    return consumer["plane"] == "root"


def compose_consumers(secret: dict[str, Any]) -> list[dict[str, Any]]:
    """The consumers that are Compose services. Everything mounted, nothing else."""
    return [consumer for consumer in secret["consumers"] if not is_root_plane(consumer)]


def consumers_of(contract: dict[str, Any], service: str, session: int) -> list[dict[str, Any]]:
    """Every ``(secret, consumer)`` grant this service holds through ``session``.

    This is the function that answers "what does this container get", and it is
    the one the Compose renderer and the isolation tests both use, so that the
    rendered model and the assertion about the rendered model cannot be derived
    from two different readings of the file.

    A root-plane consumer is never returned, whatever ``service`` is asked for.
    It is not a container's grant and there is no service name that would reach
    it.
    """
    grants: list[dict[str, Any]] = []
    for secret in active_secrets(contract, session):
        for consumer in compose_consumers(secret):
            if consumer["service"] == service:
                grants.append({"secret": secret, "consumer": consumer})
    return grants


def granted_services(contract: dict[str, Any], session: int) -> set[str]:
    return {
        consumer["service"]
        for secret in active_secrets(contract, session)
        for consumer in compose_consumers(secret)
    }


def generation_directory(project_key: str, generation_id: str) -> str:
    """Absolute path of one immutable generation. Derived, never supplied."""
    return f"{SECRET_ROOT}/{project_key}/generations/{generation_id}"


def render_secret(value: str, consumer: dict[str, Any]) -> str:
    """The bytes this consumer's file gets, from the provider's value.

    The one place a secret value is transformed at all, and it is a pure
    function so that the transformation is testable without a provider, a host
    or a file. Everything else in this module handles identifiers; this handles
    a value and deliberately does nothing else with it -- it is not logged, not
    measured, and not returned in an exception.
    """
    fmt = consumer["format"]
    if fmt == "raw":
        return value
    if fmt == "pgpass":
        # A newline in the value would end the pgpass line and make the rest a
        # second, malformed entry -- silently, with libpq skipping it and the
        # connection failing for a reason nothing states. Refused rather than
        # escaped: the generator produces hex, so a value with a newline in it
        # is a provider that handed back something nobody declared.
        if "\n" in value or "\r" in value:
            raise ManifestError(
                "a pgpass-format secret value contains a line break, which would end "
                "the line and leave the remainder as a malformed second entry. The "
                "value is not what this consumer's contract declares"
            )
        return PGPASS_TEMPLATE.format(value=value)
    raise ManifestError(f"no writer for secret format {fmt!r}")


def recover_secret(rendered: str, consumer: dict[str, Any]) -> str:
    """The provider's value, back out of the bytes :func:`render_secret` wrote.

    The bootstrap plane needs the password itself -- `ALTER ROLE … PASSWORD`
    takes a value, not a pgpass line -- and it reads it from the materialized
    file rather than from the provider, because a second declared consumer would
    materialize a second copy of one credential and give a rotation two files to
    reach instead of one.

    Written here, beside the writer, and asserted to round-trip. The realistic
    failure is not that this is wrong today; it is that a third format arrives
    and only one of the two functions learns about it. Both raise on an unknown
    format for that reason, so the pair fails loudly rather than one of them
    passing a wrapper through as though it were a value.

    Trailing newlines only, matching :func:`render_secret`'s template and the
    `$(cat …)` every container entrypoint uses. A `.strip()` would also take
    leading whitespace and hand back a value no consumer presents.
    """
    fmt = consumer["format"]
    if fmt == "raw":
        return rendered.rstrip("\n")
    if fmt == "pgpass":
        line = rendered.rstrip("\n")
        prefix = PGPASS_TEMPLATE.split("{value}")[0]
        if not line.startswith(prefix):
            # No value is echoed. The file holds a secret whatever shape it is
            # in, and a message quoting the malformed line would put it in a log.
            raise ManifestError(
                f"a pgpass-format secret file does not begin with {prefix!r}. It was "
                "not written by this contract's materializer, so what the remainder "
                "means is unknown"
            )
        return line[len(prefix) :]
    raise ManifestError(f"no reader for secret format {fmt!r}")


def consumer_directory(consumer: dict[str, Any]) -> str:
    """The generation subdirectory this consumer's file lands in.

    The service name for a Compose consumer, and :data:`ROOT_PLANE_DIRECTORY`
    for a root-plane one. One function, because two call sites deciding this
    separately is how a root-plane file ends up in a directory some container
    mounts.
    """
    return ROOT_PLANE_DIRECTORY if is_root_plane(consumer) else consumer["service"]


def consumer_named(
    contract: dict[str, Any], secret_name: str, consumer_key: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The declared secret and the one consumer whose directory is ``consumer_key``.

    ``consumer_key`` is what :func:`consumer_directory` returns — a service name,
    or :data:`ROOT_PLANE_DIRECTORY` for a value no container holds. So a caller
    names *a secret and who holds it*, which is what it actually knows, and the
    filename is derived here rather than spelled at the call site.

    That distinction is the point (ADR 0075). ``postgrest_authenticator_password``
    is materialized into a file called ``postgrest_authenticator_pgpass``, and a
    caller that spells the filename has made a second derivation of something this
    module already derives — one that goes stale the moment a consumer's
    ``target_file`` or ``format`` changes, and whose failure is a missing file
    rather than a wrong answer only because nothing had looked yet.

    Raises rather than returning ``None``: every caller is asking about a grant it
    believes exists, and a soft miss reads as "this secret is not held here",
    which is a security claim nobody measured. The messages name identifiers
    only.
    """
    for secret in contract["secrets"]:
        if secret["name"] != secret_name:
            continue
        for consumer in secret["consumers"]:
            if consumer_directory(consumer) == consumer_key:
                return secret, consumer
        held_by = sorted(consumer_directory(item) for item in secret["consumers"])
        raise ManifestError(
            f"secret {secret_name!r} declares no consumer {consumer_key!r}; it is held by {held_by}"
        )

    declared = sorted(secret["name"] for secret in contract["secrets"])
    raise ManifestError(f"no secret named {secret_name!r} in the contract; it declares {declared}")


def secret_source_path(project_key: str, generation_id: str, consumer: dict[str, Any]) -> str:
    """Absolute host path of one materialized secret file.

    Per-consumer, not per-secret: the service name is a path component. That is
    what makes "service A cannot read service B's copy" a filesystem property
    rather than a convention.
    """
    root = generation_directory(project_key, generation_id)
    return f"{root}/{consumer_directory(consumer)}/{consumer['target_file']}"


def container_secret_path(consumer: dict[str, Any]) -> str:
    return f"{CONTAINER_SECRET_DIR}/{consumer['target_file']}"


# ---------------------------------------------------------------------------
# Semantic validation — what JSON Schema cannot say
# ---------------------------------------------------------------------------


def _validate_semantics(document: dict[str, Any]) -> None:
    secrets = document["secrets"]

    _reject_duplicates(
        [s["name"] for s in secrets],
        "secret name",
        "two declarations of one name make the grant surface ambiguous",
    )
    _reject_duplicates(
        [s["provider_key"] for s in secrets],
        "provider_key",
        "two local names for one provider key would fetch the same value twice "
        "and make rotation ambiguous",
    )

    for secret in secrets:
        _validate_consumers(secret)
        _validate_formats(secret)


def _validate_formats(secret: dict[str, Any]) -> None:
    """A format has to make sense of the kind of value it is given (ADR 0056).

    A pgpass line holding a PEM is not a thing. Refused at contract load rather
    than at the first failed connection, where the message would be
    `fe_sendauth` and the file would look plausible.
    """
    for consumer in secret["consumers"]:
        if consumer["format"] == "pgpass" and secret["value_kind"] != "random_hex":
            raise ManifestError(
                f"secret {secret['name']!r} is a {secret['value_kind']} and a consumer "
                "asks for it in pgpass format. A password file holds a password"
            )


def _validate_consumers(secret: dict[str, Any]) -> None:
    name = secret["name"]
    consumers = secret["consumers"]

    # Uniqueness is per (directory, target_file), not per target_file: two
    # services legitimately receive the same basename, because each gets its
    # own directory and each sees it at the same /run/secrets path. The root
    # plane is one more directory under the same rule.
    pairs = [(consumer_directory(c), c["target_file"]) for c in consumers]
    _reject_duplicates(
        pairs,
        f"consumer of secret {name!r}",
        "one service cannot receive two files with the same name",
    )

    for consumer in consumers:
        target = consumer["target_file"]
        where = consumer_directory(consumer)
        # The schema pattern already excludes '/' and a leading dot, so this is
        # belt and braces -- but path escape is the failure this contract exists
        # to prevent, and a defence that lives only in a regex is one edit from
        # being gone.
        if "/" in target or ".." in target or Path(target).name != target:
            raise ManifestError(
                f"secret {name!r} consumer {where!r} declares target_file "
                f"{target!r}, which is not a simple basename; a target filename must not "
                "be able to leave its generation directory"
            )
        # Root ownership: refused on the compose plane, required on the root
        # plane. The schema states both with a const and this states the reason,
        # because the two rules are opposites and a reader who found only one of
        # them would take it for the whole rule.
        if is_root_plane(consumer):
            if consumer["uid"] != 0 or consumer["gid"] != 0:
                raise ManifestError(
                    f"secret {name!r} declares a root-plane consumer owned "
                    f"{consumer['uid']}:{consumer['gid']}; a value no container may hold "
                    "must not be readable by a uid some container runs as"
                )
        elif consumer["uid"] == 0 or consumer["gid"] == 0:
            raise ManifestError(
                f"secret {name!r} consumer {where!r} declares root ownership; "
                "a root-owned secret file is unreadable by a container that drops privileges"
            )


def _reject_duplicates(values: list[Any], what: str, why: str) -> None:
    seen: set[Any] = set()
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise ManifestError(f"duplicate {what}: {duplicates}; {why}")


__all__ = [
    "CONTAINER_SECRET_DIR",
    "FORMATS",
    "OPERATOR_SUPPLIED",
    "ORIGINS",
    "PGPASS_TEMPLATE",
    "PLANES",
    "ROOT_PLANE_DIRECTORY",
    "SECRET_ROOT",
    "active_secrets",
    "compose_consumers",
    "consumer_directory",
    "consumer_named",
    "consumers_of",
    "container_secret_path",
    "generation_directory",
    "granted_services",
    "is_operator_supplied",
    "is_root_plane",
    "load_secret_contract",
    "operator_supplied_secrets",
    "recover_secret",
    "render_secret",
    "secret_source_path",
]

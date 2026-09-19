"""Secret requirements contract (Session 2, Phase 2).

`secrets.required.yaml` declares *which* secrets exist, *which* service consumes
each one, and *under what numeric ownership* it is materialized. It never
declares a value.

Three functions here are handed one — `render_secret`, `recover_secret` and
`check_value_kind` — and they are pure for the reason ADR 0056 gives: the
transformation a value undergoes, and now the check it must pass, are testable
with no provider and no host. **None of the three returns a value into a
message, and none of them logs.** Everything else in this module operates on
identifiers alone.

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

import re
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

#: What the materializer writes into a consumer's file (ADR 0056, ADR 0153).
FORMATS = ("raw", "pgpass", "pgbackrest")

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

#: The facilities a secret may belong to (ADR 0188). A secret with a facility
#: exists for a project exactly when the project enables that facility, and is
#: required by construction whenever it exists: the third state beside
#: required and optional, because an optional secret cannot reach a container
#: (Compose refuses a missing mount source) and a required-everywhere one
#: would fail every project without the facility.
FACILITY_BACKUP_MIRROR = "backup_mirror"
FACILITIES = (FACILITY_BACKUP_MIRROR,)

#: The `pgpass` template. Wildcards in all four match fields, deliberately: the
#: alternative names a host, a port, a database and a role that `naming.py`
#: already derives, which is a second derivation path inside a secret file and a
#: file that goes stale when any of them changes. The narrowing buys nothing --
#: the file is `0400`, owned by the one uid its container runs as, and that
#: container has exactly one connection target.
PGPASS_TEMPLATE = "*:*:*:*:{value}\n"

#: The `pgbackrest` template (ADR 0153, Session 10 Run 8b).
#:
#: A one-option pgBackRest configuration fragment. pgBackRest concatenates every
#: `.conf` under `config-include-path` with its main configuration, and rig 9
#: measured that **three files each carrying their own `[global]` header
#: concatenate cleanly** (exit 0) -- which is what lets this contract keep its
#: rule that it materializes one value per file.
#:
#: **The header is not optional and its absence is a leak.** Measured, K3: a file
#: whose first line is a bare `key=value` fails with
#: `[029]: key/value found outside of section at line 1:` **followed by the
#: value**, on pgBackRest's console and in its log -- and for `archive-push` that
#: is the postmaster's stderr. So `render_secret` refuses a value containing a
#: line break (a newline would end the line and leave the remainder outside the
#: section, reaching K3's condition from the value rather than from the header)
#: and `recover_secret` verifies the header before returning anything.
PGBACKREST_TEMPLATE = "[global]\n{option}={value}\n"

#: Where pgBackRest reads its configuration includes from.
#:
#: Its own default, measured rather than assumed: `pgbackrest help backup
#: config-include-path` prints `default: /etc/pgbackrest/conf.d`. Nothing sets
#: the option, so this is the path that is in force, and a consumer whose format
#: is `pgbackrest` is mounted here instead of under `CONTAINER_SECRET_DIR`.
PGBACKREST_INCLUDE_DIR = "/etc/pgbackrest/conf.d"


def load_secret_contract(path: Path) -> dict[str, Any]:
    """Parse, schema-validate and semantically validate the requirements file."""
    document = config.load_manifest(path)
    config.assert_no_sensitive_keys(document)
    config.validate_against_schema(document, "secret-contract.schema.json")
    _validate_semantics(document)
    return document


def active_secrets(
    contract: dict[str, Any], session: int, *, facilities: frozenset[str] | None = None
) -> list[dict[str, Any]]:
    """Secrets live at ``session``: introduced by it, and not yet retired.

    ``facilities`` is which facilities the project has (ADR 0188), from
    `enabled_facilities`. Given, a secret that belongs to a facility the
    project lacks is not returned; omitted, every live secret is -- the
    DECLARED view, for the readers that ask what the contract holds rather
    than what one project materializes. The four that write, mount, require or
    publish for a project pass it: the materializer, the secret override, the
    render's required names, and the deploy's credential check.

    ``introduced_in_session <= session < retired_in_session``, where an absent
    ``retired_in_session`` means "still live" -- which is every secret but one.

    **The upper bound is Session 15's, and it is the half that was missing**
    (ADR 0170). Retiring the bootstrap issuer's key by guarding the renderer's
    append accomplished nothing on its own: a secret with no retirement is
    materialized into every new generation for ever, so the file was present, the
    guard passed, and the published set stayed full at ``MAX_VERIFICATION_KEYS``
    exactly as before. It was green in a checkout because a fixture writes only
    the keys its test wants, and unchanged on a deployment because the
    materializer writes them all -- the fixture and the code sharing a belief the
    deployment does not.

    The upper comparison is strict so that **a deploy asking for an earlier
    session still gets the secret.** A project pinned to Session 14 needs its
    bootstrap key; retirement says what the RELEASE stops issuing, not what every
    generation must lose, and a project is not upgraded by this repository
    deciding that it should be.
    """
    live = [
        s
        for s in contract["secrets"]
        if s["introduced_in_session"] <= session < s.get("retired_in_session", session + 1)
    ]
    if facilities is None:
        return live
    # A project's view: a facility-gated secret only with its facility, and a
    # facility-gated CONSUMER of any secret likewise -- the mirror container's
    # read of the primary's credential pair (ADR 0188), which an unmirrored
    # project neither writes nor mounts. Copies, so the declared view stays as
    # loaded.
    selected: list[dict[str, Any]] = []
    for secret in live:
        if secret.get("facility") is not None and secret["facility"] not in facilities:
            continue
        consumers = [
            c
            for c in secret["consumers"]
            if c.get("facility") is None or c["facility"] in facilities
        ]
        selected.append({**secret, "consumers": consumers})
    return selected


def enabled_facilities(document: dict[str, Any]) -> frozenset[str]:
    """Which facilities a project has, read from its manifest or its rendered
    document -- both carry `backup.mirror.enabled` at the same place, and a
    manifest that omits the block has none (ADR 0188).

    One reader of the fact, for every caller that decides what a project
    materializes, mounts or requires. A second expression of "does this
    project have a mirror" beside a materializer would be the two-authority
    shape ADR 0002 forbids.
    """
    enabled: set[str] = set()
    if config.backup_mirror_enabled(document):
        enabled.add(FACILITY_BACKUP_MIRROR)
    return frozenset(enabled)


def secret_is_active(contract: dict[str, Any], name: str, session: int) -> bool:
    """Whether ``name`` is materialized at ``session`` (ADR 0170).

    One reading of the retirement, for the readers that need the answer rather
    than the list. `jwt.temporary` in the deployed document is the first: it says
    whether the bootstrap issuer is still live, and it was the literal `True` for
    ten sessions -- with a comment reading *"True until Session 6 replaces the
    issuer"*, written before Session 6 and never revisited after it.

    Derived here and not beside each reader, because a second expression for
    "is this credential still issued" is a second authority for the value the
    contract owns (ADR 0002).
    """
    return any(secret["name"] == name for secret in active_secrets(contract, session))


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
    if fmt == "pgbackrest":
        # The same refusal as pgpass, and here it prevents a LEAK rather than a
        # malformed entry (ADR 0153 §4). A newline ends the `key=value` line and
        # leaves the remainder as a key outside any section, which pgBackRest
        # reports as `[029]: key/value found outside of section at line N:`
        # **quoting the line** -- so a value with a newline in it puts part of
        # itself into the archiver's log. No value is echoed here either.
        if "\n" in value or "\r" in value:
            raise ManifestError(
                "a pgbackrest-format secret value contains a line break. pgBackRest "
                "reports a key outside a section by quoting the line, so this would "
                "put part of the value into the archiver's log. The value is not what "
                "this consumer's contract declares"
            )
        return PGBACKREST_TEMPLATE.format(option=consumer["option"], value=value)
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
    if fmt == "pgbackrest":
        # The header is verified, not assumed, and that is the whole point of
        # this branch: a file that reached the container without it makes
        # pgBackRest print the value (ADR 0153 §4). Neither the line nor the
        # value is echoed in the refusal.
        # Split on the placeholder rather than formatting an empty value, which
        # is what `pgpass` above does and for the reason this branch first got
        # wrong: formatting with `value=""` keeps the template's TRAILING
        # newline, so the prefix is `[global]\nopt=\n` and no real file starts
        # with it. Caught by the round-trip the module's own docstring demands.
        prefix = PGBACKREST_TEMPLATE.split("{value}")[0].format(option=consumer["option"])
        line = rendered.rstrip("\n")
        if not line.startswith(prefix):
            raise ManifestError(
                "a pgbackrest-format secret file does not begin with its [global] "
                f"header and {consumer['option']!r}. It was not written by this "
                "contract's materializer, and pgBackRest reports a key outside a "
                "section by quoting the line -- so this file must not be mounted"
            )
        return line[len(prefix) :].rstrip("\n")
    raise ManifestError(f"no reader for secret format {fmt!r}")


#: What a `rsa_private_pem` value has to carry. PKCS#8, which is the form
#: `openssl genpkey` writes and the form ADR 0055's description names -- an
#: `RSA PRIVATE KEY` header is PKCS#1 and a different thing, so matching it
#: here would accept a value `render-jwks` would then have to interpret.
PEM_BEGIN = "-----BEGIN PRIVATE KEY-----"
PEM_END = "-----END PRIVATE KEY-----"

#: The floor a body of key material clears. A 2048-bit PKCS#8 private key in
#: PEM is around 1,700 characters; the shortest thing that could be mistaken
#: for one is a header and a footer with nothing between them, at 52. 1,000 is
#: below anything real and far above every truncation D1578 observed.
#:
#: **It is a floor, not a length check.** The delimiters cannot catch a key
#: that was truncated after its header and had its footer pasted back on, and
#: that was one of the four malformations. Nothing here re-derives the key's
#: size: that would mean parsing key material in this loop, which ADR 0225
#: rejected on purpose.
PEM_MINIMUM_LENGTH = 1000

#: Lowercase hex, whole string. `secrets.token_hex` emits exactly this, and
#: `fullmatch` rather than `search` because a hex prefix on something else is
#: the shape a half-pasted value has.
_HEX_VALUE = re.compile(r"[0-9a-f]+")


def check_value_kind(kind: str, value: str) -> str | None:
    """Is this value the kind of thing the contract says it is? (ADR 0225)

    Returns ``None`` when it is, and otherwise **a reason built from the kind,
    the delimiter names and the length floor -- never from the value**. This
    function is called with key material in hand, and the string it returns is
    printed to an operator's terminal by a command that runs as root. A reason
    carrying so much as ``value[:20]`` would put part of a private key into a
    scrollback buffer, and the point of `bin/render-jwks` suppressing openssl's
    stderr is that even the key's *path* is more than that command should say.

    `value_kind` has been declared on every secret since ADR 0055 and its
    schema description has always stated what it is for -- *a default is how a
    hex string ends up stored under a name that says key* -- while the only
    runtime reader was the pgpass cross-check in `_validate_formats`, which
    asks a question about the consumer rather than about the value. D816's
    shape: a declared field whose stated purpose no code performed.

    **Three outcomes, and the third is reported** (ADR 0195): the value is what
    it claims, the value is not, or the kind is one this function does not
    know. The last one cannot arrive from a loaded contract -- the enum is
    closed and `load_secret_contract` validates it -- but this function is the
    only reader of the field, so a kind added to the schema and not added here
    fails closed and says which kind it was, rather than returning ``None``
    and passing an unchecked value through the branch that means *fine*.

    Pure, and it neither normalises nor trims. A value that passes is written
    byte for byte as the provider held it: a transformation here would make
    this a second place where a secret's bytes are decided, and the value path
    in `bin/materialize-secrets.py` has exactly one.
    """
    if kind == "rsa_private_pem":
        # Each boundary on a line of its own, which is what RFC 7468 requires
        # and what `openssl rsa` enforces. A `in value` test alone accepts a
        # delimiter JOINED to the body -- one of the four malformations of
        # 2026-09-19, at 1701 bytes with a longest line of 91 -- and that is
        # the one whose failure lands in `render-jwks` mid-deploy with
        # openssl's stderr suppressed. Stripped, because trailing whitespace
        # on a boundary line is not what anybody means by malformed.
        boundaries = {line.strip() for line in value.splitlines()}
        for delimiter in (PEM_BEGIN, PEM_END):
            if delimiter not in value:
                return (
                    f"declared {kind} and the value does not contain {delimiter!r}. "
                    "A PKCS#8 private key carries both delimiters"
                )
            if delimiter not in boundaries:
                return (
                    f"declared {kind} and {delimiter!r} is not on a line of its own. "
                    "Joined to the body it is a substring rather than an "
                    "encapsulation boundary, and openssl refuses the file"
                )
        if len(value) < PEM_MINIMUM_LENGTH:
            return (
                f"declared {kind} and the value is shorter than "
                f"{PEM_MINIMUM_LENGTH} characters. A 2048-bit key in PEM is "
                "several times that, so this one is truncated"
            )
        return None

    if kind == "random_hex":
        if not _HEX_VALUE.fullmatch(value):
            return f"declared {kind} and the value is not lowercase hexadecimal from end to end"
        return None

    return (
        f"declares value_kind {kind!r}, which `check_value_kind` does not know "
        "how to check. A kind added to the schema is added here in the same "
        "change, or a value of it would be written unexamined"
    )


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
    """Where this consumer's file appears inside its container.

    **The single authority on that, since Run 8b** (ADR 0153 §6). The grant
    surface used to emit a bare `target_file`, which Compose resolves under
    `/run/secrets` -- one fact spelled in two places, and the `pgbackrest` format
    needs them to disagree.

    A `pgbackrest`-format file is mounted where pgBackRest reads its includes
    from, because that is the only way it is read at all: there is no
    `repo-cipher-pass-file` option, and nothing in this repository puts a value
    into the archiver's environment (D558).

    Measured (rig 9, K8), with a control: Compose accepts an **absolute** target
    and the file lands exactly there; a relative one lands in `/run/secrets`, as
    documented. The same arm measured that Compose **ignores** the grant's `uid`,
    `gid` and `mode` -- it warns and passes the host file's through -- so what
    protects the file is `materialize-secrets` chowning the generation on the
    host, which is what the contract's own fields have always driven.
    """
    if consumer.get("format") == "pgbackrest":
        return f"{PGBACKREST_INCLUDE_DIR}/{consumer['target_file']}"
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
        _validate_facility(secret)


def _validate_facility(secret: dict[str, Any]) -> None:
    """A facility-gated secret is required by construction (ADR 0188).

    `required: false` beside a facility would make the secret optional for the
    projects that have the facility, which is the state
    `test_every_optional_secret_is_root_plane` refuses for a compose consumer:
    Compose does not start a service whose mount source is missing.
    """
    facility = secret.get("facility")
    for consumer in secret["consumers"]:
        gated = consumer.get("facility")
        if gated is None:
            continue
        if gated not in FACILITIES:
            raise ManifestError(
                f"secret {secret['name']!r} has a consumer naming facility {gated!r}; "
                f"known: {list(FACILITIES)}"
            )
        if facility is not None:
            raise ManifestError(
                f"secret {secret['name']!r} names facility {facility!r} and so does one of "
                "its consumers: one statement of the fact, on the secret"
            )
    if facility is None:
        return
    if facility not in FACILITIES:
        raise ManifestError(
            f"secret {secret['name']!r} names facility {facility!r}; known: {list(FACILITIES)}"
        )
    if not secret["required"]:
        raise ManifestError(
            f"secret {secret['name']!r} belongs to facility {facility!r} and is declared "
            "optional. A facility-gated secret is required whenever it exists at all: "
            "absent for a project without the facility, required for one with it"
        )


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
        # `option` is required by the format that uses it and forbidden to the
        # ones that do not. Both directions, because a consumer carrying an
        # `option` its format ignores is a line a reader will believe (ADR 0153).
        has_option = "option" in consumer
        if consumer["format"] == "pgbackrest" and not has_option:
            raise ManifestError(
                f"secret {secret['name']!r} has a pgbackrest-format consumer that names "
                "no `option`. The file it writes is `[global]` and one `option=value` "
                "line, so without it there is nothing to write -- and the option is not "
                "derived from the target file's name, because a rename would then be a "
                "silent behaviour change"
            )
        if consumer["format"] != "pgbackrest" and has_option:
            raise ManifestError(
                f"secret {secret['name']!r} has a {consumer['format']}-format consumer "
                "carrying an `option`, which that format does not write. A field nothing "
                "reads is a field somebody will trust"
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
    "FACILITIES",
    "FACILITY_BACKUP_MIRROR",
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
    "enabled_facilities",
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

"""Normalizing the document PostgREST serves, so two projects can share one snapshot.

ADR 0050 makes `contracts/postgrest-openapi.canonical.json` the generated half of
a pair whose hand-written half is `contracts/postgrest-api-surface.yaml`. This
module is the whole of the transformation between the live document and the
committed one, and it lives here rather than in `bin/api-contract.sh` for the
reason the plan gives: a comparator that lives in shell cannot be unit-tested
against a drifted document.

Everything below was measured against the locked PostgREST, not read:

- The document is **Swagger 2.0**, not OpenAPI 3. There is no `servers` block.
- **Exactly three top-level fields carry a project's identity**: `host`,
  `basePath` and `schemes`. Restarting the same service with
  `openapi-server-proxy-uri` set changed those three and nothing else — the
  paths, the definitions, the parameters and `info` were byte-identical.
- **`info.title` is the constant `"PostgREST API"`.** ADR 0050's consequences
  name a "title suffix" among the fields normalization replaces; no such field
  exists (D166). `info.version` is the PostgREST version, `externalDocs.url`
  carries its major, and both are deliberately *kept* — a version bump has to
  reach a reviewer, and the snapshot is where it does.
- **The `Host` request header does not reach the document.** `host` comes from
  the proxy URI, or from the container's own bind address when there is none.
  So a capture made without the proxy URI carries `0.0.0.0:3000`, which is why
  the real values are validated before anything is substituted.
- **Key order is a hash artifact.** It is stable for a given set of keys —
  creating the same objects in the opposite order produced identical order — but
  it is neither lexical nor creation order, and an inserted path lands in the
  middle. Sorting therefore buys a *reviewable* diff rather than a stable one
  (D167), and saying that correctly is the point of writing it down.

Two rules the sorting must not break, both of them load-bearing:

**Map keys are sorted; array order is never touched.** `enum` arrays carry the
type's `enumsortorder`, which the surface contract calls order-sensitive because
a reordering passes a set comparison and changes what every generated client
lists first. `required` arrays carry parameter order. Sorting an array here
would normalize away a real difference.

**Substitution is checked for residue.** Validating a value and then replacing
it is two steps, and this repository's signature defect is a placeholder
substituted somewhere nobody looked. After substitution the document is scanned
for the project's own host and base path, and their survival anywhere is a
refusal rather than a diff.

**This module has no writer**, for the same reason `api_surface` has none: ADR
0050 asks for a gate that cannot approve its own subject, and the cheapest way
to get it is a check path containing no function that writes a contract file.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from agentic_postgres.config import ManifestError

#: Every top-level key the locked PostgREST emits, measured. The set is exact
#: rather than a floor: a key this does not name is a document this normalizer
#: has never seen, and normalizing an unknown field into a snapshot is how a
#: change ships without a reviewer. A PostgREST upgrade is *expected* to fail
#: here, and the repair is to re-measure and re-approve, not to widen the set.
KNOWN_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "swagger",
        "info",
        "host",
        "basePath",
        "schemes",
        "consumes",
        "produces",
        "paths",
        "definitions",
        "parameters",
        "externalDocs",
    }
)

#: Present or the document is not describable at all.
REQUIRED_TOP_LEVEL: frozenset[str] = frozenset({"swagger", "info", "paths"})

#: The three fields that differ between two deployments of this repository.
PROJECT_SPECIFIC: frozenset[str] = frozenset({"host", "basePath", "schemes"})

#: The only Swagger version measured. A document announcing anything else is a
#: different format wearing the same filename.
SWAGGER_VERSION = "2.0"

#: `.invalid` is reserved by RFC 2606 and can never resolve, so the sentinel
#: cannot collide with a host any deployment could actually serve. A sentinel a
#: real value could equal is a sentinel that can be satisfied by accident.
SENTINEL_HOST = "project.invalid:443"

#: Not a path any manifest can declare: `config.RESERVED_BASE_PATHS` validates
#: base paths as segments, and this one is deliberately unusable as one.
SENTINEL_BASE_PATH = "/__project_base_path__"

#: Kept rather than substituted. Every deployed project is reached over HTTPS
#: through the edge, so this is a constant to be *asserted* — and asserting it
#: is what makes a capture taken without the proxy URI fail (it carries
#: `["http"]`) instead of normalizing into agreement with the snapshot.
REQUIRED_SCHEMES: tuple[str, ...] = ("https",)

#: A served document is a few tens of kilobytes. The bound exists so a truncated
#: or substituted response fails as a size before it fails as a parse.
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024

__all__ = [
    "KNOWN_TOP_LEVEL",
    "MAX_DOCUMENT_BYTES",
    "PROJECT_SPECIFIC",
    "REQUIRED_SCHEMES",
    "REQUIRED_TOP_LEVEL",
    "SENTINEL_BASE_PATH",
    "SENTINEL_HOST",
    "SWAGGER_VERSION",
    "NormalizationError",
    "canonical_bytes",
    "declared_objects",
    "fingerprint",
    "load_document",
    "normalize",
    "sort_maps",
]


class NormalizationError(ManifestError):
    """The document cannot be normalized into a comparable form.

    A subclass of :class:`ManifestError` so the CLI exit-code mapping applies
    unchanged: like a manifest that validates and lies, this is a well-formed
    input that cannot mean what the comparison needs it to mean.
    """


def load_document(raw: str | bytes) -> dict[str, Any]:
    """Parse the served bytes strictly. Raises :class:`NormalizationError`.

    Strict in three ways JSON itself is not:

    1. **Duplicate keys are refused.** `json.loads` keeps the last of a repeated
       key and says nothing, so a document carrying `"paths"` twice would be
       normalized down to whichever copy happened to come second — and the
       objects in the other copy would be in the served surface and absent from
       everything that reviews it.
    2. **`NaN`, `Infinity` and `-Infinity` are refused.** Python accepts all
       three by default and emits them back out, producing a "JSON" file no
       other parser will read.
    3. **The root must be an object**, because a bare array or string parses
       fine and then fails much later as a missing key.
    """
    payload = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise NormalizationError(
            f"the document is {len(payload)} bytes, over the {MAX_DOCUMENT_BYTES} bound. "
            "A served OpenAPI document is tens of kilobytes; this is something else"
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NormalizationError(f"the document is not UTF-8: {error}") from error

    try:
        document = json.loads(
            text,
            object_pairs_hook=_refuse_duplicate_keys,
            parse_constant=_refuse_constant,
        )
    except json.JSONDecodeError as error:
        raise NormalizationError(f"the document is not JSON: {error}") from error

    if not isinstance(document, dict):
        raise NormalizationError(f"the document's root is {type(document).__name__}, not an object")
    return document


def _refuse_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise NormalizationError(
                f"duplicate key {key!r}. JSON permits it and every parser resolves it "
                "differently, so a document carrying one means two things at once"
            )
        seen.add(key)
    return dict(pairs)


def _refuse_constant(name: str) -> Any:
    raise NormalizationError(
        f"the document contains {name}, which is not JSON. Python round-trips it and "
        "no other parser will read the result"
    )


def normalize(
    document: dict[str, Any],
    *,
    expected_host: str,
    expected_base_path: str,
) -> dict[str, Any]:
    """Return the project-neutral form of `document`.

    `expected_host` and `expected_base_path` are what the *deployed document*
    says this project publishes. They are arguments rather than something read
    out of the served response, because ADR 0050 requires the real values to be
    validated before they are substituted: a project whose host is wrong must
    fail rather than normalize into agreement with the snapshot.

    Raises :class:`NormalizationError` on anything it cannot vouch for.
    """
    _validate_shape(document)
    _validate_project_fields(
        document, expected_host=expected_host, expected_base_path=expected_base_path
    )

    neutral = dict(document)
    neutral["host"] = SENTINEL_HOST
    neutral["basePath"] = SENTINEL_BASE_PATH
    neutral["schemes"] = list(REQUIRED_SCHEMES)

    sorted_document = sort_maps(neutral)
    _refuse_residue(
        sorted_document, expected_host=expected_host, expected_base_path=expected_base_path
    )
    return sorted_document


def _validate_shape(document: dict[str, Any]) -> None:
    """The document is the format this normalizer was measured against."""
    missing = REQUIRED_TOP_LEVEL - set(document)
    if missing:
        raise NormalizationError(
            f"the document has no {sorted(missing)}. That is not a served OpenAPI "
            "document; a capture that reached the wrong endpoint looks exactly like this"
        )

    announced = document["swagger"]
    if announced != SWAGGER_VERSION:
        raise NormalizationError(
            f"the document announces swagger {announced!r}, not {SWAGGER_VERSION!r}. "
            "Every field this module names was measured against 2.0, and a document in "
            "another format would be normalized by rules that do not describe it"
        )

    unknown = set(document) - KNOWN_TOP_LEVEL
    if unknown:
        raise NormalizationError(
            f"the document carries top-level {sorted(unknown)}, which this normalizer has "
            "never seen. A PostgREST upgrade is expected to fail here: re-measure what the "
            "new version emits and approve a new snapshot, rather than widening the set"
        )

    for field in PROJECT_SPECIFIC:
        if field not in document:
            raise NormalizationError(
                f"the document has no {field!r}, so there is nothing to substitute. A "
                "sentinel written into an absent field would make every project's "
                "document agree about a value none of them published"
            )


def _validate_project_fields(
    document: dict[str, Any], *, expected_host: str, expected_base_path: str
) -> None:
    """ADR 0050: validate the real values, then substitute. Not the other way."""
    if not expected_host or not expected_base_path:
        raise NormalizationError(
            "expected_host and expected_base_path are both required. Normalizing without "
            "them would replace whatever was served with a sentinel and call it a match"
        )

    served_host = document["host"]
    if served_host != expected_host:
        raise NormalizationError(
            f"the document publishes host {served_host!r}, but this project's deployed "
            f"document says {expected_host!r}. A capture taken without "
            "openapi-server-proxy-uri carries the container's bind address, and "
            "substituting a sentinel over it would hide that the snapshot describes a "
            "service nobody can reach at the published address"
        )

    served_base_path = document["basePath"]
    if served_base_path != expected_base_path:
        raise NormalizationError(
            f"the document publishes basePath {served_base_path!r}, but this project's "
            f"deployed document says {expected_base_path!r}. Every generated client "
            "prefixes every request with this string"
        )

    served_schemes = document["schemes"]
    if list(served_schemes) != list(REQUIRED_SCHEMES):
        raise NormalizationError(
            f"the document publishes schemes {served_schemes!r}, not "
            f"{list(REQUIRED_SCHEMES)!r}. A document offering http tells every generated "
            "client that cleartext is a supported way to reach this API"
        )


def sort_maps(node: Any) -> Any:
    """Recursively sort every object's keys, leaving every array's order alone.

    The asymmetry is the whole function. `enum` arrays carry `enumsortorder`,
    which the surface contract calls order-sensitive; `required` arrays carry
    argument order; `produces` lists content types in preference order. Sorting
    any of those would normalize away a difference that means something, and it
    would do it silently, in a comparator whose job is to notice differences.
    """
    if isinstance(node, dict):
        return {key: sort_maps(node[key]) for key in sorted(node)}
    if isinstance(node, list):
        return [sort_maps(item) for item in node]
    return node


def _refuse_residue(
    document: dict[str, Any], *, expected_host: str, expected_base_path: str
) -> None:
    """No project-specific value survives anywhere in the normalized document.

    The guard on the substitution. `normalize` replaces two named top-level
    fields, which is correct only for as long as those are the only two places
    the values appear — and "a placeholder substituted somewhere nobody looked"
    is this repository's signature defect. Measured today, the paths and
    definitions carry neither value; asserted here so that the day one of them
    does, the capture refuses instead of committing a project's hostname into a
    file both projects compare against.

    The bare hostname is searched for as well as the `host:port` form, because
    that is the form a `$ref`, a description or an example would carry.
    """
    serialized = json.dumps(document, ensure_ascii=False)
    bare_host = expected_host.rsplit(":", 1)[0] if ":" in expected_host else expected_host
    for label, value in (
        ("host", expected_host),
        ("hostname", bare_host),
        ("basePath", expected_base_path),
    ):
        if value and value in serialized:
            raise NormalizationError(
                f"the project's {label} {value!r} survives in the normalized document. "
                "Substituting the two fields that are known to carry it is only "
                "sufficient while they are the only ones that do"
            )


def canonical_bytes(document: dict[str, Any]) -> bytes:
    """The committed form: one document, one byte string, always.

    Two spellings of the same document must not produce two snapshots, so the
    serialization is pinned rather than left to a default: sorted keys, two-space
    indent, no ASCII escaping, `\\n` endings and a trailing newline. `indent`
    rather than the compact form because a reviewer reads this file in a diff,
    which is the only reason it is committed at all.
    """
    text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def fingerprint(document: dict[str, Any]) -> str:
    """SHA-256 of the canonical bytes.

    What `API-CACHE-001` compares across a schema reload: the fingerprint moves
    when the published surface moves, and it is computed from the normalized form
    so a redeployment at a different host does not look like a DDL change.
    """
    return sha256(canonical_bytes(document)).hexdigest()


def declared_objects(document: dict[str, Any]) -> set[str]:
    """Every object the document publishes, as `relation` and `rpc/name` strings.

    Spelled the way `api_surface.declared_objects` spells them once the schema is
    prefixed by the caller, so the two sides of `API-CONTRACT-001` can be
    compared without either side reformatting the other's names. A comparison
    whose sides spell an object differently reports a difference that is not
    one, and the repair for that is always to loosen the comparison.

    `/` is the document's own root path and is not an object.
    """
    names: set[str] = set()
    for path in document.get("paths", {}):
        if path == "/":
            continue
        names.add(path.lstrip("/"))
    return names

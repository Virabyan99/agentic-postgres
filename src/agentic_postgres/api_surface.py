"""The reviewed API surface: loading it, and the rules the schema cannot state.

ADR 0050 makes `contracts/postgrest-api-surface.yaml` the hand-written half of a
pair. The other half — `contracts/postgrest-openapi.canonical.json` — is
generated from a running PostgREST, and the comparison between them is Session
5's `API-CONTRACT-001`. This module owns the hand-written half: it parses it
through the same strict loader every manifest uses, validates it against its
schema, and then applies the four rules JSON Schema has no way to express.

**Nothing here reads a catalog and nothing here reads OpenAPI.** Both of those
need a running database or a running service, and a contract that could only be
loaded where those exist would be a contract no offline test could read. The
comparison lives in `bin/api-contract.sh`; what lives here is the answer to
"what does the reviewed file say", which is a pure function of a file.

The one property worth stating twice: **this module has no writer.** ADR 0050
asks for a gate that cannot approve its own subject, and the cheapest way to get
that is for the code path the gate runs to contain no function that writes a
contract file. `test_the_module_cannot_write_a_contract` asserts it on the
public surface rather than trusting the absence.
"""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from agentic_postgres import REPO_ROOT, config
from agentic_postgres.config import ManifestError

#: The reviewed contract. One file, at a fixed path, because a contract that can
#: be pointed somewhere else is a contract that can be pointed at a copy of the
#: thing it constrains.
CONTRACT_PATH = REPO_ROOT / "contracts" / "postgrest-api-surface.yaml"

SCHEMA_NAME = "api-surface.schema.json"

#: The four schemas that must never be published, whatever the file says. Held
#: here as well as in the file for the reason `output_migrations` keeps its own
#: copy of the profile transports: two copies of a fact with a test between them
#: are one fact, and a contract that could quietly drop `app_private` from its
#: own forbidden list would be a contract that permits reaching it.
REQUIRED_FORBIDDEN_SCHEMAS = frozenset({"public", "app", "app_private", "extensions"})

#: Reads are `GET` and `HEAD`; writes are `POST` to an RPC. Stated as data so
#: that "no table-style write is granted on a view" is one comparison rather than
#: four `!=` checks somebody could add a fifth method past.
RELATION_METHODS = frozenset({"GET", "HEAD"})
RPC_METHODS = frozenset({"POST"})

#: An agent-plane function is STABLE and takes nothing, so PostgREST serves it
#: both ways whether or not anybody wanted it to (ADR 0118). Both are listed
#: because "reachable two ways" is the fact a reviewer needs; the argument list
#: is what makes the GET harmless, and `validate_surface` requires it empty.
AGENT_RPC_METHODS = frozenset({"GET", "POST"})

#: Characters that cannot appear in any identifier the schema accepts, listed so
#: the refusal names the thing it refuses. A wildcard is the interesting one:
#: `columns: ["*"]` is the shape of contract that describes everything and
#: therefore constrains nothing.
_WILDCARD = re.compile(r"[*%?]")

__all__ = [
    "AGENT_RPC_METHODS",
    "CONTRACT_PATH",
    "RELATION_METHODS",
    "REQUIRED_FORBIDDEN_SCHEMAS",
    "RPC_METHODS",
    "SCHEMA_NAME",
    "SurfaceError",
    "contract_digest",
    "declared_objects",
    "declared_types",
    "load_surface",
    "published_objects",
    "validate_surface",
]


class SurfaceError(ManifestError):
    """The reviewed surface contract is unusable as a contract.

    A subclass of :class:`ManifestError` so the CLI's exit-code mapping applies
    unchanged: this is a well-formed file asserting something that cannot be
    true, which is the same class of failure as a manifest that validates and
    lies.
    """


def load_surface(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    """Parse, schema-check and semantically validate the reviewed surface.

    Uses `config.load_manifest`, so the contract inherits every refusal the
    project manifests get: duplicate keys, multiple documents, merge keys,
    non-string keys, a symlink, an oversized file. A duplicate `relations` key
    silently keeping the last value would be a contract with objects nobody
    reviewed in it.
    """
    document = config.load_manifest(path)
    config.validate_against_schema(document, SCHEMA_NAME)
    validate_surface(document)
    return document


def validate_surface(document: dict[str, Any]) -> None:
    """The rules the schema cannot state. Raises :class:`SurfaceError`.

    Four of them, and each one is a way for a file that validates to fail at
    being a contract.
    """
    exposed = document["exposed_schema"]
    forbidden = set(document["forbidden_schemas"])

    # 1. The forbidden list must actually forbid the four that matter. A file
    #    that dropped `app_private` would still validate: the schema requires a
    #    non-empty list, not a particular one.
    missing = REQUIRED_FORBIDDEN_SCHEMAS - forbidden
    if missing:
        raise SurfaceError(
            f"forbidden_schemas does not name {sorted(missing)}. These are the schemas a "
            "misconfigured db-schemas or a default db-extra-search-path would actually "
            "reach, so a contract that stops naming one stops refusing it"
        )

    # 2. The exposed schema cannot also be forbidden. Nothing would be servable,
    #    and the contradiction would surface as an empty published surface that
    #    every comparison agrees with.
    if exposed in forbidden:
        raise SurfaceError(
            f"exposed_schema {exposed!r} is also in forbidden_schemas. Every object would "
            "be both required and refused, and a surface with nothing in it agrees with "
            "every catalog"
        )

    # 3. Methods, per kind. The schema already enumerates them, and this states
    #    the rule the enumeration is an instance of -- so a later widening has to
    #    change a set that has a reason written next to it.
    for name, relation in document["relations"].items():
        extra = set(relation["methods"]) - RELATION_METHODS
        if extra:
            raise SurfaceError(
                f"relation {name!r} declares {sorted(extra)}. Writes are RPCs that derive "
                "ownership; a table-style write on a view would let a caller name the "
                "owner_id it likes and satisfy the row policy by saying so"
            )
    for name, rpc in document["rpcs"].items():
        extra = set(rpc["methods"]) - RPC_METHODS
        if extra:
            raise SurfaceError(
                f"rpc {name!r} declares {sorted(extra)}. A GET /rpc/ puts the arguments in "
                "a query string, which is in every log and every cache between the caller "
                "and the database"
            )

    # 4. An agent-plane function takes nothing (ADR 0118). The schema states it
    #    as `maxItems: 0`; this states the rule the bound is an instance of, so a
    #    later widening has to change something with a reason beside it. An
    #    argument here reaches a query string -- PostgREST serves a stable
    #    function over GET as well as POST -- and a caller-supplied value makes
    #    the tool's operation a runtime choice, which docs/capability-plan.md
    #    places outside the product.
    for name, entry in document["agent_rpcs"].items():
        if entry["arguments"]:
            raise SurfaceError(
                f"agent_rpcs {name!r} declares arguments {entry['arguments']}. PostgREST "
                "serves a stable function over GET as well as POST, so an argument here "
                "reaches the query string -- and a caller-supplied value makes the tool's "
                "operation a runtime choice"
            )
        extra = set(entry["methods"]) - AGENT_RPC_METHODS
        if extra:
            raise SurfaceError(
                f"agent_rpcs {name!r} declares {sorted(extra)}, which is not how PostgREST "
                "serves a stable argument-free function"
            )

    # 5. No wildcard anywhere. The identifier pattern already forbids one, so
    #    this is the guard on the guard -- and it is the rule worth stating,
    #    because a contract that describes everything constrains nothing.
    for pointer, value in _strings(document):
        if _WILDCARD.search(value):
            raise SurfaceError(
                f"{pointer} contains a wildcard: {value!r}. A contract that names a class "
                "of objects cannot refuse a member of it"
            )

    _refuse_name_collisions(document)


def _refuse_name_collisions(document: dict[str, Any]) -> None:
    """No two declared objects may share a name, whatever their kinds.

    PostgREST serves relations at `/{name}` and functions at `/rpc/{name}`, so
    those two do not collide on the wire -- but they do collide in every
    message, every comparison and every review that says "the contract names
    `tasks`". The catalog permits it; a document a human has to read against a
    catalog should not.

    An enum type is included because PostgreSQL puts types and relations in the
    same namespace: `CREATE TYPE api.tasks` fails against the view of that name,
    so a contract declaring both would describe a catalog that cannot exist.
    """
    labels = {
        "relations": "a relation",
        "rpcs": "an RPC",
        "agent_rpcs": "an agent-plane RPC",
        "enums": "an enum type",
    }
    seen: dict[str, str] = {}
    for kind, label in labels.items():
        for name in document[kind]:
            if name in seen:
                raise SurfaceError(
                    f"{name!r} is declared as both {seen[name]} and {label}. Declared "
                    "objects are indistinguishable in every sentence written about "
                    "them, and a type may not share a name with a relation at all"
                )
            seen[name] = label


def _strings(node: Any, pointer: str = "") -> list[tuple[str, str]]:
    """Every string in the document, with the path that reaches it."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{pointer}.{key}" if pointer else str(key)
            if isinstance(key, str):
                found.append((where, key))
            found.extend(_strings(value, where))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_strings(value, f"{pointer}[{index}]"))
    elif isinstance(node, str):
        found.append((pointer, node))
    return found


def declared_objects(document: dict[str, Any]) -> set[str]:
    """Every object the contract permits, as `schema.name` strings.

    The form the catalog comparison needs, produced here so that both sides of
    `API-CONTRACT-001` name objects the same way. A comparison whose two sides
    spell the same object differently reports a difference that is not one, and
    the repair for that is always to loosen the comparison.
    """
    schema = document["exposed_schema"]
    return {
        f"{schema}.{name}"
        for name in (*document["relations"], *document["rpcs"], *document["agent_rpcs"])
    }


def published_objects(document: dict[str, Any]) -> set[str]:
    """The subset that the generated OpenAPI document is expected to name.

    :func:`declared_objects` answers "what may exist in the exposed schema" and
    this answers "what may be advertised", and Session 8 is where those stopped
    being the same question (ADR 0118). The agent plane's functions exist, are
    reachable over HTTP by one role, and are deliberately absent from the
    document because `api_documentation` holds no `EXECUTE` on them.

    Two functions rather than a flag, because the two sets are compared against
    different artefacts -- the catalog on one side and the served document on
    the other -- and a single set with a filter at each call site is how one of
    the call sites eventually gets the filter wrong.
    """
    schema = document["exposed_schema"]
    return {f"{schema}.{name}" for name in (*document["relations"], *document["rpcs"])}


def declared_types(document: dict[str, Any]) -> set[str]:
    """Every enum type the contract permits, as `schema.name` strings.

    Kept apart from :func:`declared_objects` rather than folded into it, because
    the two are compared against different catalogs -- `pg_class` and `pg_proc`
    on one side, `pg_type` on the other. A single set would make a difference
    ambiguous: a missing `api.task_status` would be reported the same way
    whether the type or a view of that name had gone.
    """
    schema = document["exposed_schema"]
    return {f"{schema}.{name}" for name in document["enums"]}


def contract_digest(path: Path = CONTRACT_PATH) -> str:
    """SHA-256 of the reviewed file, for `api.api_surface_sha256`.

    Of the bytes, not of the parsed document: what a deployment served is a file
    somebody reviewed, and a digest of the parse would be equal for two files
    whose comments -- which is where the reasoning lives -- differ.
    """
    return sha256(path.read_bytes()).hexdigest()

"""What the published reference says, built from the models that decide it.

**Descriptive only.** Nothing here changes what the service accepts or returns.
That is not a stylistic preference: declaring a pydantic model as a route
*parameter* would make FastAPI bind the body itself, and FastAPI's binding is
`json.loads` with no `object_pairs_hook` -- so `{"username":"alice",
"username":"root"}` would reach the model as `root` with the duplicate gone.
`strict_json` exists because of that, and API-AUTH-002 asserts it. A
`response_model` would be the same mistake pointing outwards: FastAPI would
filter and re-serialize every response through it, and the route would no longer
be returning what it built.

`responses=` and `openapi_extra=` do neither. They reach the document and wire
nothing.

**Why this file exists at all.** Every handler takes a bare `Request` and
returns a bare `Response`, so the document FastAPI generates from the signatures
alone is nine paths, **no request bodies**, and a single `200` apiece. Measured,
before this was written. A reference saying `POST /auth/login` takes no body and
always succeeds is worse than no reference -- it is the failure `index.html`'s
own surface note names, and ADR 0060 is this repository's record of publishing a
document that misdescribed a surface.

**Two mechanisms, because they behave differently, and the difference was
measured rather than read.**

* `openapi_extra` is **deep-merged** into the operation FastAPI generated.
  Declaring `responses` there for a route with a path parameter left FastAPI's
  own `422` in place, and writing a schema over it produced
  `{"$ref": "#/components/schemas/HTTPValidationError", "type": "object", ...}`
  -- both, because the merge reaches inside the schema. Under JSON Schema
  2020-12 `$ref` applies alongside its siblings, so that is a schema nothing can
  satisfy.
* `responses=` on the decorator **replaces**. Measured with the same route:
  `responses={422: {"model": Invalid}}` yields exactly one `$ref`, to `Invalid`,
  and `HTTPValidationError` is gone.

So every response goes through `responses=`, and `openapi_extra` carries only
the request body -- which `responses=` cannot express without binding it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.models import (
    AuthenticationFailedResponse,
    AuthorizationFailedResponse,
    InvalidRequestResponse,
    MalformedRequestResponse,
    ObjectStateConflictResponse,
    ObjectUnavailableResponse,
)

#: The failures the routes share, phrased the way `errors.py` phrases them: one
#: answer for every cause, because the causes are what an attacker is trying to
#: tell apart.
UNAUTHENTICATED: dict[str, Any] = {
    "model": AuthenticationFailedResponse,
    "description": (
        "No usable credential. Unknown subject, wrong password, disabled subject and "
        "malformed token are all this answer, and they cost the same."
    ),
}
UNAUTHORIZED: dict[str, Any] = {
    "model": AuthorizationFailedResponse,
    "description": "Authenticated, and the required scope is not held. Role names never grant.",
}
MALFORMED: dict[str, Any] = {
    "model": MalformedRequestResponse,
    "description": (
        "Refused before any domain logic ran: oversized body, duplicate JSON member, "
        "non-object root, unknown field, or a field outside its bounds."
    ),
}
INVALID: dict[str, Any] = {
    "model": InvalidRequestResponse,
    "description": (
        "Individually well formed and jointly refused -- a scope outside the role's "
        "ceiling, a username already taken. The caller is an authenticated administrator, "
        "so the reason is returned."
    ),
}

#: The two the storage surface adds.
UNAVAILABLE: dict[str, Any] = {
    "model": ObjectUnavailableResponse,
    "description": (
        "Absent, another subject's, still pending, or tombstoned -- one answer for all "
        "four (STO-OWN-001), and for a provider failure too. An answer that told them "
        "apart would make an object id an existence oracle, and object ids travel in URLs."
    ),
}
CONFLICT: dict[str, Any] = {
    "model": ObjectStateConflictResponse,
    "description": (
        "The caller's own object cannot make this transition. Naming the state is safe "
        "only because this answer is unreachable unless the row matched on owner id; "
        "every non-owned case is the 404 above."
    ),
}


def created(description: str, model: type[BaseModel] | None = None) -> dict[str, Any]:
    """A 201. Separate from `ok` so a route cannot silently publish the wrong one.

    Until Run 9 the upload-intent route published `200` for a response it sends
    as `201`, because FastAPI defaults to 200 for a handler returning a bare
    `Response` and nothing had ever compared the document to the surface.
    """
    fragment: dict[str, Any] = {"description": description}
    if model is not None:
        fragment["model"] = model
    return fragment


def no_content(description: str) -> dict[str, Any]:
    """A 204, which by definition has no body and therefore no model.

    Passing a model here would publish a body for a response that must not have
    one -- and FastAPI would happily document it.
    """
    return {"description": description}


def ok(description: str, model: type[BaseModel] | None = None) -> dict[str, Any]:
    """A 200, described by a model where the service has one for it."""
    fragment: dict[str, Any] = {"description": description}
    if model is not None:
        fragment["model"] = model
    return fragment


def body(model: type[BaseModel]) -> dict[str, Any]:
    """The `requestBody` fragment for a model the route parses itself.

    Inlined rather than referenced. These models are flat -- strings, integers
    and lists of strings -- so `$defs` is empty or trivial, and a fragment whose
    `$ref`s point at component names it never registers renders as an empty box.
    """
    schema = model.model_json_schema()
    schema.pop("$defs", None)
    return {
        "required": True,
        "content": {"application/json": {"schema": schema}},
    }


def query_parameter(
    name: str, *, schema: dict[str, Any], description: str, required: bool = False
) -> dict[str, Any]:
    """One entry for a route's `parameters` array.

    **Declared here rather than bound by FastAPI**, for the reason this whole
    module exists: a declared parameter hands parsing to the framework, and
    Starlette resolves a repeated query parameter to its LAST value silently --
    measured in Session 9 Run 7, `QueryParams("limit=1&limit=9999")["limit"]` is
    `"9999"`. That is `strict_json`'s duplicate-member defect arriving over the
    query string, and `strict_query` is what refuses it. So the document
    describes the parameter and the route still parses it.

    That split has a cost worth naming: this fragment and `strict_query`'s
    allowlist are two statements of one surface, and nothing in the framework
    holds them together. `test_the_documented_query_parameters_are_the_parsed
    _ones` is what does, by comparing the generated document against the
    allowlist the route passes.
    """
    return {
        "name": name,
        "in": "query",
        "required": required,
        "schema": schema,
        "description": description,
    }


def described(
    *,
    summary: str,
    description: str,
    request_model: type[BaseModel] | None = None,
    query_parameters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The `openapi_extra` half: prose, a request body, and query parameters.

    `openapi_extra` is deep-merged into what FastAPI generated (the measurement
    is at the top of this module), and a route that declares no parameter of its
    own generates no `parameters` key at all -- so this adds one rather than
    merging into one.
    """
    fragment: dict[str, Any] = {"summary": summary, "description": description}
    if request_model is not None:
        fragment["requestBody"] = body(request_model)
    if query_parameters is not None:
        fragment["parameters"] = query_parameters
    return fragment


def prune_unreachable_validation_errors(document: dict[str, Any], routes: Any) -> dict[str, Any]:
    """Drop the `422` FastAPI adds to a route that cannot produce one.

    **FastAPI adds a `422` to every operation with a parameter**, whether or not
    any input on that route can fail its validation. `DELETE /objects/{object_id}`
    takes one `str` path parameter, which accepts every string, so FastAPI's
    validation layer never rejects anything -- and the route's own `_object_id`
    refuses a non-uuid as `MalformedRequest`, which is a **400** in the house
    shape. The published `422 HTTPValidationError` was therefore a response the
    service cannot emit, in a shape it never produces.

    That is ADR 0060's complaint exactly: a document advertising what the
    surface does not do. It is worth removing rather than tolerating, because
    the auth surface only avoided it by coincidence -- every auth route with a
    path parameter happens to declare a real 422, which *replaces* FastAPI's.

    **The rule is derived, not listed.** An operation keeps its 422 when its
    route declared one, and loses it otherwise. So a route that gains a genuine
    `InvalidRequest` path keeps its documentation by declaring it, and no list
    here has to be kept in step with the routes -- which is the second-authority
    failure this repository keeps paying for (D177).
    """
    declared: set[tuple[str, str]] = set()
    for route in routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or ()
        responses = getattr(route, "responses", None) or {}
        if path is None:
            continue
        if 422 in responses or "422" in responses:
            for method in methods:
                declared.add((path, method.lower()))

    for path, operations in (document.get("paths") or {}).items():
        for method, operation in operations.items():
            responses = operation.get("responses") or {}
            if "422" in responses and (path, method.lower()) not in declared:
                del responses["422"]

    # `HTTPValidationError` and `ValidationError` are only ever referenced by
    # those responses, so a components block still carrying them after the prune
    # would publish two schemas nothing points at. Removed only when genuinely
    # unreferenced -- checked against the serialized document rather than
    # assumed, because assuming it is how a dangling `$ref` gets published.
    import json as _json

    # To a FIXED POINT, and that is not tidiness. `HTTPValidationError`
    # REFERENCES `ValidationError`, so a single pass computed against one
    # snapshot of the document removes the first and then finds the second still
    # referenced -- by the schema it has just deleted. The first version of this
    # did exactly that and left an orphaned `ValidationError` in the published
    # components, pointed at by nothing.
    schemas = (document.get("components") or {}).get("schemas") or {}
    removable = ("HTTPValidationError", "ValidationError")
    while True:
        body = _json.dumps(document)
        dropped = [
            name
            for name in removable
            if name in schemas and f'"#/components/schemas/{name}"' not in body
        ]
        if not dropped:
            break
        for name in dropped:
            del schemas[name]
    if not schemas:
        (document.get("components") or {}).pop("schemas", None)
    return document

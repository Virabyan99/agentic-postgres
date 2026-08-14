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


def described(
    *, summary: str, description: str, request_model: type[BaseModel] | None = None
) -> dict[str, Any]:
    """The `openapi_extra` half: prose, and a request body if the route takes one."""
    fragment: dict[str, Any] = {"summary": summary, "description": description}
    if request_model is not None:
        fragment["requestBody"] = body(request_model)
    return fragment

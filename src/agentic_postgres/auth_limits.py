"""The auth service's request bound, as the edge has to know it.

One number, declared in `services/auth-api/app/strict_json.py` and read here
(ADR 0084). The service refuses a body larger than `MAX_BODY_BYTES`; the edge
refuses one larger than the same number, one hop earlier, with a Traefik
buffering middleware.

**Both are needed, and Run 10 measured why.** `routes.py::_body` does
``parse_object(await request.body())``, and `request.body()` reads the *whole*
body before `parse_object` looks at its length. Measured against the locked
FastAPI and Starlette, with a control: a 108-byte body is read as 108 bytes; an
**8 388 616-byte** body is read in full and then refused for exceeding 16 384 --
8 MiB allocated to enforce a 16 KiB limit, a factor of 512, and nothing bounds
it above that. The service's bound protects the parser. It does not protect the
process, because by the time it runs the memory has already been spent.

So the edge is where the allocation is actually bounded, and it is bounded at
the same number rather than at a second one: `test_the_edge_bound_is_the_service
_bound` compares them, and this module existing is what makes that comparison a
comparison rather than a tautology (D260's third mutation -- a test that
computes its expectation from the constant under test asserts nothing).
"""

from __future__ import annotations

from agentic_postgres import service_source

_strict_json = service_source.load("strict_json")

#: The largest request body the auth service will parse, in bytes.
MAX_BODY_BYTES: int = _strict_json.MAX_BODY_BYTES

__all__ = ["MAX_BODY_BYTES"]

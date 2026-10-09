"""Which of a deployed document's routes a proof may hold to `ready`, shared.

**A test helper, not a product module** (D2195's reason, `isolation_matrix.py`'s
shape): only proofs ask this question.

Since 1.15.0 every deployed document carries `routes.control`, and a project
with the control facility off records it `unavailable` by design; so does
`routes.storage` on a project with `storage.enabled: false` (control-prod). The
rule D2143 wrote into DEP-REMOVE-001's proof is the one this module holds:

* a route is excused ONLY when the SAME document declares its facility
  `enabled: false` -- read from the document, never from a list of names a
  proof expects to be down;
* a project that serves the route is still held to `ready`, and so is a
  document that does not say (an absent block excuses nothing).

D2294 found the second proof that needed it: REC-NODE-002 (Session 18) held
EVERY route to `ready`, was `not_run` by decision until Session 38's move put a
replacement host under it, and failed on its first execution on alpha's
by-design `unavailable` control route. Two copies of one rule drift, so both
proofs read it from here.

**REST is not in the set, deliberately.** Since Session 38 (D2137, D2172) a
manifest may turn REST off, but the deployed document does not carry the flag;
an excusal this module cannot read from the document is not one it grants. A
proof reading such a document reports `rest` as unready, which is the honest
reading until the document says why.
"""

from __future__ import annotations

from typing import Any

#: The routes whose facility a deployed document declares at `<name>.enabled`.
FACILITY_ROUTES: tuple[str, ...] = ("control", "storage")


def not_served(document: dict[str, Any]) -> frozenset[str]:
    """Routes this document itself says the project does not serve."""
    return frozenset(
        name for name in FACILITY_ROUTES if (document.get(name) or {}).get("enabled") is False
    )


def unready_routes(document: dict[str, Any]) -> list[str]:
    """Every route not `ready` that the document does not excuse, sorted."""
    excused = not_served(document)
    return sorted(
        name
        for name, route in (document.get("routes") or {}).items()
        if isinstance(route, dict) and name not in excused and route.get("status") != "ready"
    )

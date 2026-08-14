"""Loading a module that lives in the auth service's build context.

**The rule, stated once (ADR 0084).** A fact both the repository and the running
service need lives in `services/auth-api/app/`, and `src/agentic_postgres/`
imports it. Not the other way round, and never a copy.

The reason is the Docker build context. `compose.yaml` builds the auth service
with `context: ./services/auth-api`, so a `COPY` cannot reach `src/`. The
alternatives were measured against what they cost:

* **Build from the repository root.** Keeps the layout CLAUDE.md describes, and
  puts the whole tree in the build context -- including `schemas/`, which
  `config.py` reads and which `scope_registry` needs. The dependency chain that
  drags in is larger than the facts being shared.
* **Duplicate, and tie the copies with a test.** This repository's own recorded
  failure mode: D175 notes that a test comparing two constants goes green again
  the moment somebody regenerates the copy, and D260 found three tests in one
  run that compared a value against itself.
* **Invert.** One file, imported by both. Run 7 did this for the Argon2 profile
  and this generalises it.

**What may move and what may not.** Only pure facts with no third-party import:
the claim contract's shape, the scope ceiling, the Argon2 profile. Everything
that is *about* those facts rather than being one of them stays in `src/` --
`POSTGREST_ENFORCES` is a record of a measurement, `sql_required_claims` renders
a migration literal, and neither is something the service does.
`test_every_service_module_the_repository_imports_needs_only_the_standard_library`
is what keeps the first half true.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

from agentic_postgres import REPO_ROOT

#: The service's package root. On `sys.path` so `app.<name>` imports by name --
#: a path-based load creates a SECOND module object with its own classes, and a
#: dataclass compares `other.__class__ is self.__class__` before anything else.
#: Run 7 shipped that bug and a test comparing across the boundary caught it.
SERVICE_ROOT = REPO_ROOT / "services" / "auth-api"


def load(name: str) -> ModuleType:
    """Import `app.<name>` from the service's build context."""
    root = str(SERVICE_ROOT)
    if root not in sys.path:
        # Appended rather than prepended: this must never take precedence over a
        # module the caller already has, and `app` is a common enough package
        # name that shadowing one would be hard to attribute.
        sys.path.append(root)
    return importlib.import_module(f"app.{name}")

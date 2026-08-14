"""The frozen Argon2id profile, as the repository's own code sees it.

There is no profile *here*. This module loads
`services/auth-api/app/profile.py` -- the file that lives inside the image's
build context and is therefore the copy the running service applies -- and
re-exports it, so that `config.py` and the contract tests can `from
agentic_postgres import auth_profile` like any other module while there is
still exactly one declaration of the numbers.

The alternative was to declare the profile here and copy it into the image.
That is the shape D234 named: two values in two files that must agree, with
nothing computing the relation. A copy would be checkable by a test, and a test
that compares two constants is a test that goes green again the moment somebody
regenerates the copy -- which is D175's failure mode, recorded and unfixed.
Loading the real file has no such state.

`profile.py` imports nothing but the standard library, which is what makes this
safe: the deploy host validates a manifest without `argon2`, `pyjwt` or
`psycopg` installed anywhere near it.
`test_the_frozen_profile_module_needs_only_the_standard_library` asserts that,
because it is the property this whole arrangement rests on and it would break
silently the first time somebody added a convenience import.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

from agentic_postgres import REPO_ROOT

#: The directory the service's package lives in, put on the path so that
#: `app.profile` is importable by name.
SERVICE_ROOT = REPO_ROOT / "services" / "auth-api"

#: The one file. Named for the tests that assert what it may import.
PROFILE_SOURCE = SERVICE_ROOT / "app" / "profile.py"


def _load() -> ModuleType:
    """Import `app.profile` -- the module, not a copy of it.

    **A path-based load was the first attempt and it was wrong**, in a way this
    repository has produced before. `importlib.util.spec_from_file_location`
    under a private name produces a SECOND module object with its own
    `Argon2Profile` class, and a dataclass `__eq__` compares
    `other.__class__ is self.__class__` first. So
    `parse_encoded(hash) == auth_profile.FROZEN` was False for two structurally
    identical profiles -- a comparison that could never succeed, which is D173's
    shape (`probe not in {api.notes,...}` can never fail) pointing the other way.

    Caught by the first test that compared across the boundary. Putting the
    service root on `sys.path` and importing by name gives one module object,
    so there is one `Argon2Profile` class and equality means what it reads as.

    `app/__init__.py` imports nothing, so this does not drag `argon2`,
    `fastapi` or `psycopg` into a deploy host that has none of them --
    `test_the_frozen_profile_module_needs_only_the_standard_library` is what
    keeps that true.
    """
    root = str(SERVICE_ROOT)
    if root not in sys.path:
        # Appended, not prepended: this must never take precedence over a
        # module the caller already has, and `app` is a common enough name that
        # shadowing one would be a hard failure to attribute.
        sys.path.append(root)
    return importlib.import_module("app.profile")


_source = _load()

Argon2Profile = _source.Argon2Profile
FROZEN = _source.FROZEN
HASH_CONCURRENCY = _source.HASH_CONCURRENCY
PROCESS_OVERHEAD_MB = _source.PROCESS_OVERHEAD_MB
parse_encoded = _source.parse_encoded
hash_memory_budget_mb = _source.hash_memory_budget_mb

__all__ = [
    "FROZEN",
    "HASH_CONCURRENCY",
    "PROCESS_OVERHEAD_MB",
    "PROFILE_SOURCE",
    "SERVICE_ROOT",
    "Argon2Profile",
    "hash_memory_budget_mb",
    "parse_encoded",
]

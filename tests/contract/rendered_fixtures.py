"""Whether the rendered contract fixtures may be trusted (ADR 0073, D212).

Four modules read `.generated/fixture-alpha-dev` and `.generated/fixture-alpine-dev`,
and until Run 10 each decided for itself whether to run by asking whether the
directory existed. **An existence check answers a question nobody asked.** The
Session 5 host gate ran against fixtures rendered at `schema_version: 4`, before
the PostgREST service existed, and `compose config` reported eleven variables
"missing a value" -- as though the model were broken. The model was fine and the
fixture was four schema versions old.

So there are three states, not two, and only one of them is a skip:

    absent   nobody has rendered in this tree -- skip, the dependency is missing
    stale    rendered at a version the code has left -- FAIL, and say the gap
    current  rendered at output_migrations.CURRENT_VERSION -- run

`schema_version` is a **proxy** and this module says so rather than implying
more. It is the one number a render stamps that the code also declares, which
makes a fixture predating an outputs migration detectable with no extra
machinery -- the drift that actually occurred. It does not catch a fixture at the
current version whose `compose.env` is missing a key, because a Compose variable
can be added without an outputs migration. That fuller check needs the required
interpolation set, which is profile-dependent and deliberately incomplete for the
references whose values arrive from root-owned state at deploy time (ADR 0013).
Named narrowly on purpose: a check whose name is wider than its evidence is this
repository's standing defect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, output_migrations

RENDER_ROOT = REPO_ROOT / ".generated"

#: The two projects the contract suite renders. They are a pair because
#: `DEP-ISO-002` is a claim about two projects' names being disjoint, and one
#: project cannot be disjoint from nothing.
FIXTURE_KEYS = ("fixture-alpha-dev", "fixture-alpine-dev")

RERENDER = "re-render: ./deploy.sh --render-only"


def _state() -> tuple[str, str]:
    """Return ``(state, detail)`` where state is absent, stale or current."""
    versions: dict[str, int | None] = {}
    for key in FIXTURE_KEYS:
        document = RENDER_ROOT / key / "outputs.json"
        if not document.is_file():
            return "absent", f"{key} is not rendered in this working tree"
        try:
            versions[key] = json.loads(document.read_text(encoding="utf-8"))["schema_version"]
        except (json.JSONDecodeError, KeyError) as exc:
            # An unreadable render is not an absent one. Treating it as absent
            # would skip, and a skip is not a pass.
            return "stale", f"{key}/outputs.json carries no readable schema_version ({exc})"

    current = output_migrations.CURRENT_VERSION
    behind = {key: version for key, version in versions.items() if version != current}
    if behind:
        gaps = ", ".join(f"{key} at v{version}" for key, version in sorted(behind.items()))
        return "stale", f"{gaps}; the code renders v{current} -- {RERENDER}"
    return "current", f"both fixtures at v{current}"


STATE, DETAIL = _state()

#: Guard for a test that reads a rendered fixture. Absent skips, because a clean
#: checkout has done nothing wrong. **Stale also skips here** -- not because it
#: is acceptable, but because `test_the_rendered_fixtures_are_not_stale` has
#: already failed the run by then, and one sentence naming the version gap is
#: worth more than eleven interpolation errors about a healthy model.
needs_rendered_fixtures = pytest.mark.skipif(
    STATE != "current", reason=f"rendered fixtures {STATE}: {DETAIL}"
)


def fixture_dir(key: str) -> Path:
    return RENDER_ROOT / key

"""`bootstrap-providers --apply` prints the number of resources it created (D2642).

Session 42's `--apply` for `slot6-prod` printed *"created 4 resource(s)"* for a
plan of 17 changes: the count was a literal, true in Session 2 when the project,
the identity, the client secret and the one sentinel value were everything a
fresh bootstrap made. A count printed as a literal is a sentence, not a reading.

What `--apply` creates: the Infisical project, the runtime machine identity,
the Universal Auth client secret, and one secret value per generated provider
secret. The plan's extra change -- the read-only grant -- is a permission, not
a resource. The expected number is read from what the fake provider RECORDED,
never from the helper `apply()` itself reads (D173's shape), and two sessions
whose contracts differ in size are both checked, so no literal passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import test_secret_origin as origin  # type: ignore[import-not-found]

from agentic_postgres import CURRENT_SESSION

pytestmark = [pytest.mark.contract, pytest.mark.p0]

#: The project, the runtime identity, its client secret.
FIXED_RESOURCES = 3


def _created_line(output: str) -> str:
    lines = [line for line in output.splitlines() if " resource(s) for " in line]
    assert len(lines) == 1, output
    return lines[0]


@pytest.mark.parametrize("session", [2, CURRENT_SESSION])
def test_the_created_count_is_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], session: int
) -> None:
    written, documents = origin._run_fresh_bootstrap(tmp_path, session=session)
    assert documents, "apply() wrote no state document; the run never reached its report"
    expected = FIXED_RESOURCES + len(written)
    line = _created_line(capsys.readouterr().out)
    assert line == f"bootstrap-providers: created {expected} resource(s) for alpha-dev", line


def test_the_two_sessions_differ() -> None:
    """The control: if both sessions declared the same number of secrets, the
    parametrised test above could not tell a count from a literal."""
    module = origin.bootstrap_module()
    sizes = {
        len(module.generated_provider_secrets(session, frozenset()))
        for session in (2, CURRENT_SESSION)
    }
    assert len(sizes) == 2, sizes

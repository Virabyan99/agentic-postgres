"""`provision-host.sh --check` verifies exactly the launchers the install installs (D2637).

`install_launchers` globs the checkout's `libexec/agentic-postgres-*` (six
since Session 42 added the telemetry launcher); `--check` verified a TYPED
list of five, so the telemetry launcher was installed and never checked. Two
readers of one set agree only when they read one definition (D600): both now
call `launcher_names`.

Driven through the script's own functions, from a copy with `main` removed:
the repository root is a temporary checkout holding the real launchers plus a
seventh, `LIBEXEC` a temporary directory, and `install`'s root-only `-o`/`-g`
dropped by a shell function so the real `install_launchers` runs unprivileged.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "provision-host.sh"
REAL_LAUNCHERS = sorted(path.name for path in (REPO_ROOT / "libexec").glob("agentic-postgres-*"))

#: `install` without the ownership flags, which only root may pass.
UNPRIVILEGED_INSTALL = """
install() {
  local arguments=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -o|-g) shift 2 ;;
      *) arguments+=("$1"); shift ;;
    esac
  done
  command install "${arguments[@]}"
}
"""


def _checkout(tmp_path: Path, extra: tuple[str, ...] = ("agentic-postgres-seventh",)) -> Path:
    """A checkout whose `libexec/` holds the real launchers and `extra`; returns the script copy."""
    root = tmp_path / "checkout"
    (root / "bin").mkdir(parents=True)
    (root / "libexec").mkdir()
    for name in REAL_LAUNCHERS:
        shutil.copy2(REPO_ROOT / "libexec" / name, root / "libexec" / name)
    for name in extra:
        (root / "libexec" / name).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (root / "libexec" / name).chmod(0o755)
    text = SCRIPT.read_text(encoding="utf-8")
    for old, new in (
        ('readonly LIBEXEC="/usr/local/libexec/agentic-postgres"',
         f'readonly LIBEXEC="{tmp_path / "installed"}"'),
        ('\nmain "$@"\n', "\n"),
    ):  # fmt: skip
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    copy = root / "bin" / "provision-host.sh"
    copy.write_text(text, encoding="utf-8")
    return copy


def _run(copy: Path, body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'. "{copy}"; {UNPRIVILEGED_INSTALL}\n{body}'],
        capture_output=True, text=True, check=False, timeout=60,
    )  # fmt: skip


def _check(copy: Path, before: str = "") -> tuple[int, str]:
    done = _run(copy, f'{before}\nviolations=0; check_launchers; echo "violations=$violations"')
    assert done.returncode == 0, done.stderr
    *lines, last = done.stdout.strip().splitlines()
    return int(last.removeprefix("violations=")), "\n".join(lines)


def test_the_check_reads_the_install_glob(tmp_path: Path) -> None:
    """Before the install, the check names every launcher the checkout holds as missing --
    the seventh included -- and after it, every one is `ok`."""
    copy = _checkout(tmp_path)
    expected = {name.removeprefix("agentic-postgres-") for name in [*REAL_LAUNCHERS, "seventh"]}
    assert "telemetry" in expected and len(expected) == len(REAL_LAUNCHERS) + 1

    violations, output = _check(copy, f'mkdir -p "{tmp_path / "installed"}"')
    assert violations == len(expected), output
    for name in expected:
        assert f"DEVIATE launcher {name} is not installed" in output, output

    violations, output = _check(copy, "install_launchers >/dev/null")
    assert violations == 0, output
    assert {line.split()[-1] for line in output.splitlines()} == expected, output


def test_a_seventh_launcher_is_checked(tmp_path: Path) -> None:
    """A launcher the install put in place and then lost is named, by name."""
    copy = _checkout(tmp_path)
    violations, output = _check(
        copy, f'install_launchers >/dev/null; rm "{tmp_path / "installed" / "seventh"}"'
    )
    assert violations == 1, output
    assert "DEVIATE launcher seventh is not installed" in output, output


def test_a_checkout_with_no_launcher_is_a_deviation(tmp_path: Path) -> None:
    """An empty glob must not read as a clean check (ADR 0195: the third outcome is said)."""
    copy = _checkout(tmp_path)
    for path in (copy.parents[1] / "libexec").iterdir():
        path.unlink()
    violations, output = _check(copy, f'mkdir -p "{tmp_path / "installed"}"')
    assert violations == 1, output
    assert "DEVIATE no launcher found" in output, output

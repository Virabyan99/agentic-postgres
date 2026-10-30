#!/usr/bin/env python
"""Stage and build the customer CLI as the `agentic-postgres-cli` distribution.

ADR 0284. One source: `bin/cloud.py`, the command this repository's own tests
run, with ONLY the text between its two packaging-seam markers replaced -- the
checkout's `sys.path` insert and `agentic_postgres` imports become the
package's own (`apg_cli`), its version, and the name its usage lines carry --
plus byte-equal copies of `src/agentic_postgres/control_client.py` and
`scram.py`, which import the standard library only. Nothing staged is ever
committed: `--out` inside the repository is refused, because the gate fails on
any untracked file and a second copy of the CLI is the drift this design
exists to prevent.

    --out DIR   stage into DIR (absent or empty) and build DIR/dist with uv

The distribution: `agentic-postgres-cli`, version `VERSION`, `requires-python
>=3.11` (rig 43d: 3.10 has no `datetime.UTC`, D2683), no dependencies, the
command `apg`, licensed Apache-2.0 (the repository's LICENSE, D2685).

Exit codes (runbook §2 convention):
    0  staged and built; the two artefacts' names and sha256 printed
    2  invalid operator input (an --out inside the repository, or not empty)
    3  bin/cloud.py's seam markers are not each present exactly once
    4  uv is not on PATH, or the build failed
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import REPO_ROOT as PACKAGE_ROOT  # noqa: E402

#: The one name the distribution is published under (D2652). Changing it is a
#: change here and nowhere else.
DISTRIBUTION = "agentic-postgres-cli"
PACKAGE = "apg_cli"
COMMAND = "apg"
REQUIRES_PYTHON = ">=3.11"
SEAM_BEGIN = "# packaging seam: begin\n"
SEAM_END = "# packaging seam: end\n"

#: What the seam becomes in the package: the package's own modules, version,
#: name and the way a hint names another command.
STAGED_SEAM = """\
# Staged by bin/build-cli.py from bin/cloud.py (ADR 0284): the package's own
# modules, its version, and the name its usage lines and hints carry.
from apg_cli import __version__
from apg_cli import control_client as cc
from apg_cli import scram
from apg_cli.control_client import ClientError

PROG = "apg"
COMMAND = "apg {}"
"""

#: The site's page for the CLI does not exist until Session 43's Run 7, so the
#: README is a fixed paragraph naming where the documentation is published.
README = """\
# agentic-postgres-cli

The command-line client for Agentic Postgres: sign in, manage organisations,
projects, branches and their connections, read usage, Query Insights and
monitoring -- every family the hosted service offers to a customer.

    pipx install agentic-postgres-cli      # or: uv tool install agentic-postgres-cli
    apg --version
    apg login password --endpoint https://control.nomipg.com/api/v1 --username NAME

The documentation is at https://nomipg.com/docs/cli/. The service is
invite-only during the beta.
"""


def fail(code: int, message: str) -> None:
    print(f"build-cli: {message}", file=sys.stderr)
    raise SystemExit(code)


def staged_cli(source: str) -> str:
    """`bin/cloud.py` with the seam's text replaced, and nothing else."""
    if source.count(SEAM_BEGIN) != 1 or source.count(SEAM_END) != 1:
        fail(3, "bin/cloud.py does not hold each packaging-seam marker exactly once")
    head, rest = source.split(SEAM_BEGIN)
    _old, tail = rest.split(SEAM_END)
    return head + SEAM_BEGIN + STAGED_SEAM + SEAM_END + tail


def pyproject(version: str) -> str:
    return f"""\
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "{DISTRIBUTION}"
version = "{version}"
description = "The customer command-line client for Agentic Postgres (apg)."
readme = "README.md"
requires-python = "{REQUIRES_PYTHON}"
license = {{ text = "Apache-2.0" }}
dependencies = []
classifiers = [
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Environment :: Console",
]

[project.urls]
Homepage = "https://nomipg.com/"
Source = "https://github.com/Virabyan99/agentic-postgres"

[project.scripts]
{COMMAND} = "{PACKAGE}.cli:main"

[tool.setuptools]
package-dir = {{ "" = "src" }}
packages = ["{PACKAGE}"]
license-files = ["LICENSE"]
"""


def stage(out: Path) -> None:
    version = (PACKAGE_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    licence = PACKAGE_ROOT / "LICENSE"
    if not licence.is_file():
        fail(2, "the repository has no LICENSE; a public package needs the operator's licence")
    package = out / "src" / PACKAGE
    package.mkdir(parents=True)
    source = (PACKAGE_ROOT / "bin" / "cloud.py").read_text(encoding="utf-8")
    (package / "cli.py").write_text(staged_cli(source), encoding="utf-8")
    for module in ("control_client.py", "scram.py"):
        shutil.copyfile(PACKAGE_ROOT / "src" / "agentic_postgres" / module, package / module)
    (package / "__init__.py").write_text(
        f'"""The Agentic Postgres customer CLI (ADR 0284)."""\n\n__version__ = "{version}"\n',
        encoding="utf-8",
    )
    (package / "__main__.py").write_text(
        "from apg_cli.cli import main\n\nraise SystemExit(main())\n", encoding="utf-8"
    )
    (out / "pyproject.toml").write_text(pyproject(version), encoding="utf-8")
    (out / "README.md").write_text(README, encoding="utf-8")
    shutil.copyfile(licence, out / "LICENSE")


def build(out: Path) -> list[Path]:
    uv = shutil.which("uv")
    if uv is None:
        fail(4, "uv is not on PATH; it builds the sdist and the wheel")
    done = subprocess.run(
        [uv, "build", "--sdist", "--wheel", "--out-dir", str(out / "dist"), str(out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if done.returncode != 0:
        sys.stderr.write(done.stderr)
        fail(4, f"uv build exited {done.returncode}")
    # uv also writes a `.gitignore` into the out-dir; the directory the publish
    # job uploads holds the two artefacts and nothing else.
    (out / "dist" / ".gitignore").unlink(missing_ok=True)
    artefacts = sorted((out / "dist").glob("*"))
    kinds = sorted(path.suffix for path in artefacts)
    if kinds != [".gz", ".whl"]:
        fail(4, f"the build left {[path.name for path in artefacts]}, not one wheel and one sdist")
    return artefacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build-cli", allow_abbrev=False)
    parser.add_argument(
        "--out", required=True, help="an absent or empty directory outside the tree"
    )
    arguments = parser.parse_args(argv)
    out = Path(arguments.out).resolve()
    if out == PACKAGE_ROOT or PACKAGE_ROOT in out.parents:
        fail(2, f"{out} is inside the repository; nothing staged is ever committed")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        fail(2, f"{out} exists and is not an empty directory")
    out.mkdir(parents=True, exist_ok=True)
    stage(out)
    for artefact in build(out):
        digest = hashlib.sha256(artefact.read_bytes()).hexdigest()
        print(f"{artefact.name}  sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

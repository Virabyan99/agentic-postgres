"""The console's SCRAM verifier equals the CLI's, and every console script parses.

Session 43 (ADR 0280, D2660): `CON-SCRAM-001`. `services/console/public/scram.js`
run by Node's WebCrypto in the pinned `NODE_RUNTIME_IMAGE` (`--network none`),
with a fixed password and salt, compared to `agentic_postgres.scram.verifier`
for the same pair -- the CLI's verifier, which `test_endpoint_cli` proves a
real cluster admits. Rig 43a read Chromium's PBKDF2 equal to Python's; this
holds the whole verifier, byte for byte, on every run.

The scripts are copied as `.mjs` so Node reads them as the modules a browser
loads (`<script type="module">`).
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from tests.contract.test_image_contracts import LOCK, requires_docker

from agentic_postgres import REPO_ROOT, scram

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security, requires_docker]

PUBLIC = REPO_ROOT / "services" / "console" / "public"
NODE = LOCK["NODE_RUNTIME_IMAGE"]
PASSWORD = "a-fixed-password-for-the-proof"  # noqa: S105 -- a fixture, never a credential
SALTS = (bytes(range(16)), bytes(range(16, 32)))


def _node(tmp_path: Path, driver: str) -> str:
    for script in PUBLIC.glob("*.js"):
        shutil.copy(script, tmp_path / f"{script.stem}.mjs")
    (tmp_path / "driver.mjs").write_text(driver, encoding="utf-8")
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{tmp_path}:/c:ro", NODE,
         "node", "/c/driver.mjs"],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_the_browser_verifier_equals_the_clis(tmp_path: Path) -> None:
    salts = json.dumps([base64.b64encode(salt).decode("ascii") for salt in SALTS])
    driver = (
        'import { verifier } from "/c/scram.mjs";\n'
        f"const salts = {salts};\n"
        "for (const salt of salts) {\n"
        '  const bytes = Uint8Array.from(Buffer.from(salt, "base64"));\n'
        f'  console.log(await verifier("{PASSWORD}", bytes));\n'
        "}\n"
    )
    produced = _node(tmp_path, driver).split()
    expected = [scram.verifier(PASSWORD, salt=salt) for salt in SALTS]
    assert produced == expected
    # The control: a different salt is a different verifier -- the comparison
    # above is not two copies of one constant.
    assert produced[0] != produced[1]
    assert all(scram.VERIFIER.fullmatch(line) for line in produced)


def test_the_password_is_the_clis_shape(tmp_path: Path) -> None:
    """32 random bytes, base64url, unpadded -- `secrets.token_urlsafe(32)`'s shape (D2698)."""
    driver = (
        'import { newPassword } from "/c/scram.mjs";\n'
        "console.log(newPassword()); console.log(newPassword());\n"
    )
    first, second = _node(tmp_path, driver).split()
    for password in (first, second):
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", password), password
    assert first != second


def test_every_script_parses(tmp_path: Path) -> None:
    """`node --check` over every script the console serves, as a module: a
    parse alone, so an import a browser resolves and Node cannot does not mask
    a syntax error."""
    names = sorted(script.stem for script in PUBLIC.glob("*.js"))
    # `pg` and `sql` since Session 44 (ADR 0285): the SQL editor's wire client
    # and its DOM-free decisions. `create` since Session 46 (ADR 0291): the
    # creation's DOM-free decisions. `messages`, `nav`, `progress` and `ui` since
    # Session 47 (ADR 0295 decision 3): the refusals' words, the shell, a long
    # operation's progress (DOM-free) and the components. `copies` since Session
    # 47 Run 6 (D3017): what Connect and the editor hand a person to copy, DOM-free.
    assert names == ["api", "app", "copies", "create", "messages", "nav", "pg", "progress", "scram",
                     "sql", "ui"], names  # fmt: skip
    for script in PUBLIC.glob("*.js"):
        shutil.copy(script, tmp_path / f"{script.stem}.mjs")
    checks = " && ".join(f"node --check /c/{name}.mjs" for name in names)
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{tmp_path}:/c:ro", NODE,
         "sh", "-c", f"{checks} && echo parsed"],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert (done.returncode, done.stdout.strip()) == (0, "parsed"), done.stderr

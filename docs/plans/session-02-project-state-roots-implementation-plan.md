# Project State Roots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `./deploy.sh --through-session 2` and `systemctl start agentic-postgres-project@<key>` both work, by splitting a project's files into a configuration root and a generated root and giving every file a writer.

**Architecture:** Two roots, one rule each. `/etc/agentic-postgres/projects/<key>/` holds what an operator supplied or what records a decision; `/var/lib/agentic-postgres/rendered/<key>/` holds what the tool generated and can regenerate. The Compose project directory becomes the rendered directory, which is what stops `bin/compose.sh` comparing one env file with itself. The installed release stays a pristine copy of the tree.

**Tech Stack:** Bash (POSIX-ish, `set -euo pipefail`, shellcheck-clean), Python 3.12 in `.venv`, pytest with `contract`/`p0` markers, Docker Compose v2/v5, Traefik v3.7.

**Spec:** `docs/plans/session-02-project-state-roots-design.md`
**Decision record:** `docs/decisions/0020-project-state-roots.md`
**Starting commit:** `6610606`

## Global Constraints

- `bin/session-01-check.sh` must exit 0 **on a clean tree** at the end of every task. Mid-task use `bin/smoke-test.sh`. A task is not done until the clean form passes.
- A contract test may only change with an ADR. ADR 0020 authorizes exactly one change: generalizing `test_every_state_file_a_launcher_requires_has_a_writer`. Nothing else.
- A currently-passing test may not be weakened. Baseline is **1183 passed, 4 skipped**.
- `./deploy.sh --render-only` must keep working with no host and no root.
- No secret value may enter source control, Compose interpolation, process arguments, image layers, or logs.
- Every tracked file is LF. Write through WSL, never the Windows filesystem.
- All work happens in WSL: `wsl -d Ubuntu bash -lc '...'`, a login shell, from `~/projects/agentic-postgres`, with `.venv` activated for pytest.
- Divergences between plan and code go in the divergence table at the end of this document or in an ADR. Never reconcile silently.
- Commits go on `main`, small, each green, then pushed and transported to the host by `git bundle` + `scp`. Never a GitHub credential on the VPS.

---

### Task 1: Move the roots and correct the launcher

Nothing in the tree writes the three files `libexec/agentic-postgres-project` requires, and `bin/project-runtime.sh` hands `bin/compose.sh` the same `compose.env` twice. This task moves `PROJECT_STATE_ROOT` to `/etc`, introduces the rendered root, and points the launcher at the file that will actually exist.

**Files:**
- Modify: `src/agentic_postgres/deployed_output.py:41` (and `__all__` at 43-50)
- Modify: `bin/compose.sh:74`
- Modify: `bin/project-runtime.sh:31`, `96-101`, `115-157`
- Modify: `libexec/agentic-postgres-project:69`, `74-75`
- Test: `tests/contract/test_project_state_roots.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `deployed_output.PROJECT_STATE_ROOT: Path` = `/etc/agentic-postgres/projects`; `deployed_output.RENDERED_ROOT: Path` = `/var/lib/agentic-postgres/rendered`; `deployed_output.rendered_path(project_key: str, *, root: Path = RENDERED_ROOT) -> Path` returning the directory (not a file). `deployed_path` keeps its existing signature and now resolves under `/etc`.

- [ ] **Step 1: Observe the defect before changing anything**

This is the observation ADR 0020 and the spec are built on. Run the current scan and record what it finds. Do not commit anything in this step.

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python - <<PY
import re
from pathlib import Path
required = set()
for launcher in sorted(Path("libexec").iterdir()):
    if launcher.is_file():
        for m in re.finditer(r"^readonly \w+=\"(/(?:etc|var)/[^\"]+\.json)\"",
                             launcher.read_text(encoding="utf-8"), re.M):
            required.add(m.group(1))
print("current scan finds:", sorted(required))
PY'
```

Expected output, exactly:

```
current scan finds: ['/etc/agentic-postgres/edge-state.json']
```

One path, for four launchers. Task 4 replaces this scan; you have now seen why.

- [ ] **Step 2: Write the failing test**

Create `tests/contract/test_project_state_roots.py`:

```python
"""The two roots a project's files live in, and the fact that they differ.

`bin/project-runtime.sh` passed one directory to `bin/compose.sh` as the Compose
project directory *and* let `bin/compose.sh` derive its runtime env file from the
same key. Both resolved to `<dir>/compose.env`, so `assert_disjoint` compared a
file with itself, every key overlapped, and the runtime path could only exit 5.

The test that matters here is the last one: the two roots must not share a
prefix. Everything else is a detail of where each file lives.
"""

from __future__ import annotations

import pytest

from agentic_postgres import REPO_ROOT, deployed_output

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def test_configuration_lives_under_etc() -> None:
    assert str(deployed_output.PROJECT_STATE_ROOT) == "/etc/agentic-postgres/projects"


def test_generated_output_lives_under_var_lib() -> None:
    assert str(deployed_output.RENDERED_ROOT) == "/var/lib/agentic-postgres/rendered"


def test_the_deployed_document_is_outputs_json_under_the_state_root() -> None:
    assert (
        str(deployed_output.deployed_path("alpha-dev"))
        == "/etc/agentic-postgres/projects/alpha-dev/outputs.json"
    )


def test_rendered_path_is_a_directory_under_the_rendered_root() -> None:
    assert (
        str(deployed_output.rendered_path("alpha-dev"))
        == "/var/lib/agentic-postgres/rendered/alpha-dev"
    )


def test_the_two_roots_do_not_share_a_prefix() -> None:
    """The self-comparison regression.

    If either root is a prefix of the other, `bin/compose.sh` can once again be
    handed the same `compose.env` as both its project env file and its runtime
    env file, and `assert_disjoint` will compare it with itself.
    """
    state = str(deployed_output.PROJECT_STATE_ROOT)
    rendered = str(deployed_output.RENDERED_ROOT)
    assert not state.startswith(rendered)
    assert not rendered.startswith(state)


def test_compose_sh_reads_the_state_root_from_etc() -> None:
    source = (REPO_ROOT / "bin" / "compose.sh").read_text(encoding="utf-8")
    assert 'readonly PROJECT_STATE_ROOT="/etc/agentic-postgres/projects"' in source


def test_project_runtime_resolves_two_distinct_directories() -> None:
    source = (REPO_ROOT / "bin" / "project-runtime.sh").read_text(encoding="utf-8")
    assert 'readonly PROJECT_STATE_ROOT="/etc/agentic-postgres/projects"' in source
    assert 'readonly PROJECT_RENDERED_ROOT="/var/lib/agentic-postgres/rendered"' in source


def test_the_launcher_reads_the_document_the_deploy_writes() -> None:
    """`deployment.json` was never written under any name, and
    `installed_release_commit` belongs to edge state."""
    source = (REPO_ROOT / "libexec" / "agentic-postgres-project").read_text(encoding="utf-8")
    assert "deployment.json" not in source
    assert "installed_release_commit" not in source
    assert "outputs.json" in source
    assert ".source_commit" in source
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python -m pytest -q tests/contract/test_project_state_roots.py'
```

Expected: FAIL. `AttributeError: module 'agentic_postgres.deployed_output' has no attribute 'RENDERED_ROOT'` on two tests, and assertion failures on the rest.

- [ ] **Step 4: Move the roots in `deployed_output.py`**

Replace line 41 and the `__all__` block (lines 43-50):

```python
PROJECT_STATE_ROOT = Path("/etc/agentic-postgres/projects")
RENDERED_ROOT = Path("/var/lib/agentic-postgres/rendered")

__all__ = [
    "PROJECT_STATE_ROOT",
    "RENDERED_ROOT",
    "SCHEMA_VERSION",
    "build_deployed_document",
    "deployed_path",
    "rendered_path",
    "validate_deployed_document",
    "write_deployed_document",
]
```

Add after `deployed_path` (line 54):

```python
def rendered_path(project_key: str, *, root: Path = RENDERED_ROOT) -> Path:
    """The installed rendered directory, not a file inside it.

    Callers need the directory: it is what `bin/compose.sh` is given as the
    Compose project directory. Returning `outputs.json` here would make the one
    caller that wants the directory derive it back out with `.parent`.
    """
    return root / project_key
```

- [ ] **Step 5: Move the root in `bin/compose.sh`**

Line 74 becomes:

```bash
readonly PROJECT_STATE_ROOT="/etc/agentic-postgres/projects"
```

No other change. The disjointness logic at lines 316-326 is correct and was being fed the same file twice.

- [ ] **Step 6: Split the directories in `bin/project-runtime.sh`**

Line 31 becomes two declarations:

```bash
readonly PROJECT_STATE_ROOT="/etc/agentic-postgres/projects"
readonly PROJECT_RENDERED_ROOT="/var/lib/agentic-postgres/rendered"
```

Replace `state_directory()` (lines 96-101) with a parameterised resolver:

```bash
# `printf` stays last on purpose. Under `set -e` a bare `[ -L x ] && die` as the
# final command of a function returns 1 when the path is not a symlink, and the
# function would fail exactly when the check passes.
resolved_directory() {
  local directory="$1" label="$2"
  [ -d "${directory}" ] || die 4 "no ${label} for ${PROJECT_KEY}: ${directory}"
  [ -L "${directory}" ] && die 2 "${directory} is a symlink, which is not accepted."
  printf '%s' "${directory}"
}
```

Replace the body of `main()` from line 115 to the end of the `case` with:

```bash
  local state rendered

  case "${ACTION}" in
    status)
      rendered="$(resolved_directory "${PROJECT_RENDERED_ROOT}/${PROJECT_KEY}" "rendered output")"
      "${ROOT_DIR}/bin/compose.sh" "${rendered}" ps
      ;;

    up)
      state="$(resolved_directory "${PROJECT_STATE_ROOT}/${PROJECT_KEY}" "runtime state")"
      rendered="$(resolved_directory "${PROJECT_RENDERED_ROOT}/${PROJECT_KEY}" "rendered output")"

      # Before the containers, not after. A container that starts and then finds
      # its secret missing fails in its own way, at its own time, and reports it
      # as an application error.
      "${ROOT_DIR}/bin/materialize-secrets.sh" \
        --project "${state}/manifest.yaml" \
        --requirements "${state}/secrets.required.yaml" \
        --session 2 \
        || die 8 "secrets could not be materialized for ${PROJECT_KEY}."

      "${ROOT_DIR}/bin/compose.sh" "${rendered}" --runtime --profile session2 up -d --wait \
        || die 9 "the project did not become healthy."

      # Last, and only now that --wait has returned.
      "${ROOT_DIR}/bin/edge-network.sh" attach --project-key "${PROJECT_KEY}" \
        || die 9 "the project is running but has no ingress."

      printf 'project-runtime: %s is up and attached.\n' "${PROJECT_KEY}"
      ;;

    down)
      rendered="$(resolved_directory "${PROJECT_RENDERED_ROOT}/${PROJECT_KEY}" "rendered output")"

      # First. Compose cannot remove a network that still has an endpoint on it,
      # and the failure is reported as a network error rather than as the
      # missing detach it actually is.
      "${ROOT_DIR}/bin/edge-network.sh" detach --project-key "${PROJECT_KEY}" \
        || die 9 "could not detach the edge; refusing to tear down underneath it."

      # No -v. The Postgres volume outlives the project by design; removing it
      # here would make `systemctl restart` a data-loss command.
      "${ROOT_DIR}/bin/compose.sh" "${rendered}" --runtime --profile session2 down \
        || die 9 "the project did not stop cleanly."

      printf 'project-runtime: %s is down. Volumes are preserved.\n' "${PROJECT_KEY}"
      ;;
  esac
```

Also update the header comment block (lines 20-24) so exit code 4 names both directories:

```bash
#   4  missing runtime state or rendered output (the project was never deployed
#      here). Configuration lives under /etc/agentic-postgres/projects/<key>/;
#      generated output under /var/lib/agentic-postgres/rendered/<key>/ (ADR 0020).
```

- [ ] **Step 7: Correct `libexec/agentic-postgres-project`**

Line 69 becomes:

```bash
  local deployment="${STATE_ROOT}/${project_key}/outputs.json"
```

Lines 74-75 become:

```bash
  commit="$(jq -r '.source_commit // empty' "${deployment}")"
  [ -n "${commit}" ] || die 4 "${deployment} records no source commit."
```

Update the docstring at lines 39-41:

```bash
Resolves the installed release recorded in that project's deployed outputs
document and runs that release's scripts. Not intended for direct operator use;
systemd invokes it through agentic-postgres-project@<project-key>.service.
```

Leave every validation — key pattern, hex commit, length check, symlink refusal, root ownership — exactly as it is. Note that `manifest` and `requirements` at lines 93-94 already resolve under `STATE_ROOT`, which is `/etc`, and are now correct without change.

- [ ] **Step 8: Run the test to verify it passes**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python -m pytest -q tests/contract/test_project_state_roots.py'
```

Expected: PASS, 8 passed.

- [ ] **Step 9: Run shellcheck and the full gate**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && shellcheck deploy.sh bin/*.sh libexec/*'
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && git add -A && git commit -q -m wip && source .venv/bin/activate && bin/session-01-check.sh 2>&1 | tail -20'
```

Expected: shellcheck silent; gate `PASSED` with **1191 passed, 4 skipped** (1183 + 8 new). If the count is anything else, stop: a passing test was weakened.

- [ ] **Step 10: Commit**

Amend the `wip` commit rather than adding to it.

```bash
wsl -d Ubuntu bash -lc "cd ~/projects/agentic-postgres && git commit -q --amend -F - <<'MSG'
fix(session-2): a project's files live in two roots, not one

libexec/agentic-postgres-project read deployment.json and
installed_release_commit. Nothing writes that file under any name, and that
field belongs to edge state; a deployed document records source_commit. The
launcher exited 4 before reaching project-runtime.sh and had never run.

project-runtime.sh passed the state directory to compose.sh as the Compose
project directory, so compose.sh resolved <dir>/compose.env as both its project
env file and its runtime env file and called assert_disjoint on one path twice.

Configuration now lives under /etc/agentic-postgres/projects/<key>/ and
generated output under /var/lib/agentic-postgres/rendered/<key>/ (ADR 0020).
The roots do not share a prefix, which is what a test now asserts.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG"
```

---

### Task 2: The deploy establishes both roots

`bin/deploy-session-2.py` writes one file into one directory. It must copy the operator's inputs into the configuration root and install the rendered output into the generated root, so that both the launcher and `project-runtime.sh` find what they open.

**Files:**
- Modify: `bin/deploy-session-2.py:30-58` (imports and constants), `287-297` (step 4), `352-363` (`_model_digest`)
- Test: `tests/contract/test_deploy_establishes_roots.py` (create)

**Interfaces:**
- Consumes: `deployed_output.PROJECT_STATE_ROOT`, `deployed_output.RENDERED_ROOT`, `deployed_output.rendered_path` from Task 1.
- Produces: in `bin/deploy-session-2.py` — `_establish_directory(path: Path) -> Path`, `_write_root_only(path: Path, payload: bytes) -> None`, `_install_file(source: Path, destination: Path) -> None`, `_env_value(path: Path, key: str) -> str`, `install_rendered(source: Path, destination: Path) -> Path`.

- [ ] **Step 1: Write the failing test**

Create `tests/contract/test_deploy_establishes_roots.py`:

```python
"""Every file the launcher and the runtime open is written by the deploy.

This is a source-level contract, not a behavioural one: `bin/deploy-session-2.py`
requires root and a provisioned host, so the test asserts that the code names
each destination and installs it atomically, and the host run proves the rest.
"""

from __future__ import annotations

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]


@pytest.fixture(scope="module")
def source() -> str:
    return (REPO_ROOT / "bin" / "deploy-session-2.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "destination",
    ['"manifest.yaml"', '"secrets.required.yaml"', '"compose.env"'],
)
def test_the_deploy_writes_each_configuration_file(source: str, destination: str) -> None:
    assert destination in source, f"nothing in the deploy writes {destination}"


def test_the_rendered_directory_is_installed_out_of_the_checkout(source: str) -> None:
    """systemd may not run out of a working tree, and neither may the runtime
    read its Compose project directory from one."""
    assert "install_rendered" in source
    assert "rendered_path" in source


def test_the_install_is_atomic(source: str) -> None:
    """A half-written rendered directory is one the next boot treats as
    complete."""
    assert "os.replace" in source


def test_the_router_name_is_read_back_not_re_derived(source: str) -> None:
    """Deriving the router name a second time creates a second path to the same
    answer; the deployed document would describe a project the render never
    produced."""
    assert "HEALTH_ROUTER_NAME" in source
    assert "health_router_name" not in source
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python -m pytest -q tests/contract/test_deploy_establishes_roots.py'
```

Expected: FAIL — 5 failures. `"manifest.yaml"`, `"secrets.required.yaml"`, `install_rendered`, `rendered_path` and `HEALTH_ROUTER_NAME` are all absent.

- [ ] **Step 3: Add the imports and helpers**

In `bin/deploy-session-2.py`, add `shutil` and `tempfile` to the import block (lines 32-39, keep alphabetical):

```python
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
```

Add these helpers immediately after `run()` (line 73), before the `Preconditions` banner:

```python
def _establish_directory(path: Path) -> Path:
    """Create a root-only directory, refusing a symlink at the destination."""
    if path.is_symlink():
        fail(EXIT_VALIDATION, f"{path} is a symlink, which is not accepted.")
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    os.chown(path, 0, 0)
    return path


def _write_root_only(path: Path, payload: bytes) -> None:
    """Write `0600 root:root`, atomically.

    A reader that opens this file while it is half-written gets a truncated
    document rather than the previous one, and every reader here treats a
    truncated document as a hard failure.
    """
    if path.is_symlink():
        fail(EXIT_VALIDATION, f"{path} is a symlink, which is not accepted.")
    handle = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    try:
        with handle:
            handle.write(payload)
        os.chmod(handle.name, 0o600)
        os.chown(handle.name, 0, 0)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def _install_file(source: Path, destination: Path) -> None:
    """Copy an operator input into the configuration root.

    A copy, not a reference. A deployed project keeps working after the operator
    deletes their clone, which is the whole reason the launcher reads from /etc.
    """
    _write_root_only(destination, source.read_bytes())


def _env_value(path: Path, key: str) -> str:
    """Read one KEY=VALUE without shell-sourcing the file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name == key:
            return value
    fail(EXIT_VALIDATION, f"{key} is absent from {path}")
    raise AssertionError("unreachable")


def install_rendered(source: Path, destination: Path) -> Path:
    """Install the rendered directory out of the checkout, atomically.

    The runtime's Compose project directory may not be a working tree: a
    `git checkout` on a Friday afternoon would otherwise change what the next
    `systemctl restart` runs.
    """
    if not (source / "compose.env").is_file():
        fail(EXIT_VALIDATION, f"nothing rendered at {source}; the render step did not run")

    _establish_directory(destination.parent)

    staging = destination.parent / f".{destination.name}.incoming"
    previous = destination.parent / f".{destination.name}.previous"
    for path in (staging, previous):
        shutil.rmtree(path, ignore_errors=True)

    shutil.copytree(source, staging)
    for path in (staging, *staging.rglob("*")):
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
        os.chown(path, 0, 0)

    if destination.exists():
        os.replace(destination, previous)
    os.replace(staging, destination)
    shutil.rmtree(previous, ignore_errors=True)
    return destination
```

- [ ] **Step 4: Replace step 4 of `main()`**

Replace lines 287-297 entirely:

```python
    step("4. Root-owned configuration and generated output")
    state_directory = _establish_directory(deployed_output.PROJECT_STATE_ROOT / key)

    _install_file(arguments.project, state_directory / "manifest.yaml")
    _install_file(REPO_ROOT / "secrets.required.yaml", state_directory / "secrets.required.yaml")
    _write_root_only(state_directory / "compose.env", runtime_compose_env(host))
    print(f"  {state_directory}")

    rendered_directory = install_rendered(rendered_dir, deployed_output.rendered_path(key))
    print(f"  {rendered_directory}")
```

- [ ] **Step 5: Digest what runs, not what was rendered in the checkout**

Line 330 currently passes `rendered_dir`. Change it to the installed directory:

```python
            "compose_model_sha256": _model_digest(rendered_directory),
```

The digest must describe the model the runtime resolves. Hashing the checkout's copy would record agreement with a directory nothing runs from.

- [ ] **Step 6: Run the test to verify it passes**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python -m pytest -q tests/contract/test_deploy_establishes_roots.py'
```

Expected: PASS, 6 passed.

- [ ] **Step 7: Prove `--render-only` still needs no host and no root**

This is a non-negotiable constraint and the change sits next to it.

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && ./deploy.sh --project project.example.yaml --capabilities capabilities.example.yaml --render-only && echo "exit=$?"'
```

Expected: exit 0, as a non-root user, with no `host.yaml` anywhere.

- [ ] **Step 8: Run the full gate and commit**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && git add -A && git commit -q -m wip && source .venv/bin/activate && bin/session-01-check.sh 2>&1 | tail -20'
```

Expected: `PASSED`, **1197 passed, 4 skipped**.

```bash
wsl -d Ubuntu bash -lc "cd ~/projects/agentic-postgres && git commit -q --amend -F - <<'MSG'
feat(session-2): the deploy writes the files the launcher opens

Step 4 wrote one file into one directory. The launcher opens three it never
created, and project-runtime.sh reads its Compose project directory from a path
nothing installed.

The deploy now copies the project manifest and the secret contract into
/etc/agentic-postgres/projects/<key>/, writes the host-derived compose.env
beside them, and installs the rendered directory to
/var/lib/agentic-postgres/rendered/<key>/ out of the checkout. The install is
staged and moved into place, because a half-written rendered directory is one
the next boot would treat as complete.

The Compose model digest now hashes the installed directory. Hashing the
checkout's copy recorded agreement with a directory nothing runs from.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG"
```

---

### Task 3: The runtime override nothing generated

`runtime-compose.override.yaml` is named by `bin/compose.sh:317` and by ADR 0013, and no component produces it. Without it the project has no `traefik.enable` and no router, so it starts and is never routed.

**Files:**
- Create: `src/agentic_postgres/runtime_override.py`
- Modify: `bin/deploy-session-2.py` (import, and step 4 from Task 2)
- Test: `tests/contract/test_runtime_override.py` (create)

**Interfaces:**
- Consumes: `_env_value`, `_write_root_only`, `install_rendered` from Task 2.
- Produces: `runtime_override.ROUTED_SERVICE: str` = `"edge-probe"`; `runtime_override.ROUTED_SERVICE_PORT: int` = `8080`; `runtime_override.build_override(*, router_name: str, https_entrypoint: str) -> dict[str, Any]`; `runtime_override.render_override(*, router_name: str, https_entrypoint: str) -> bytes`.

- [ ] **Step 1: Write the failing test**

Create `tests/contract/test_runtime_override.py`:

```python
"""Router label keys are rendered; the values that matter are not.

A router label's *key* contains the router name, and interpolation inside a
label key is not portable to the Compose version floor (ADR 0013), so the key is
rendered here. The resolver and the middleware chain stay as interpolation
references on purpose: they come from the root-owned runtime env file, and an
operator who can write a project's rendered output must not thereby be able to
change which resolver issues its certificate or drop the middleware chain.
"""

from __future__ import annotations

import pytest
import yaml

from agentic_postgres import runtime_override
from agentic_postgres.naming import HEALTH_ROUTE_PATH

pytestmark = [pytest.mark.contract, pytest.mark.p0]

ROUTER = "apg-alpha-dev-health"


@pytest.fixture
def labels() -> dict[str, str]:
    document = runtime_override.build_override(
        router_name=ROUTER, https_entrypoint="websecure"
    )
    return document["services"][runtime_override.ROUTED_SERVICE]["labels"]


def test_no_label_key_contains_an_interpolation(labels: dict[str, str]) -> None:
    """The defect this file exists to prevent. Compose 2.24 renders
    `traefik.http.routers.${X}.rule` as a literal key."""
    offenders = [key for key in labels if "$" in key]
    assert not offenders, f"label keys must be fully rendered: {offenders}"


def test_the_router_name_is_in_the_keys(labels: dict[str, str]) -> None:
    assert f"traefik.http.routers.{ROUTER}.rule" in labels
    assert f"traefik.http.services.{ROUTER}.loadbalancer.server.port" in labels


def test_traefik_is_enabled_here_and_not_in_the_committed_model(
    labels: dict[str, str],
) -> None:
    """Exposure is a deliberate act of deployment, not a property of a file in
    the repository."""
    assert labels["traefik.enable"] == "true"


def test_the_resolver_and_middlewares_stay_interpolated(labels: dict[str, str]) -> None:
    assert labels[f"traefik.http.routers.{ROUTER}.tls.certresolver"] == (
        "${ACME_RESOLVER_NAME:?required}"
    )
    assert labels[f"traefik.http.routers.{ROUTER}.middlewares"] == (
        "${BASELINE_MIDDLEWARE_CHAIN:?required}"
    )


def test_the_rule_matches_the_reserved_health_path(labels: dict[str, str]) -> None:
    rule = labels[f"traefik.http.routers.{ROUTER}.rule"]
    assert "${PROJECT_DOMAIN:?required}" in rule
    assert HEALTH_ROUTE_PATH in rule


def test_the_router_and_service_names_agree(labels: dict[str, str]) -> None:
    """Mismatched `routers.<n>.service` and `services.<n>` labels produce a
    router that resolves to nothing."""
    assert labels[f"traefik.http.routers.{ROUTER}.service"] == ROUTER


def test_the_rendered_document_is_parseable_yaml() -> None:
    payload = runtime_override.render_override(
        router_name=ROUTER, https_entrypoint="websecure"
    )
    document = yaml.safe_load(payload.decode("utf-8"))
    assert runtime_override.ROUTED_SERVICE in document["services"]


@pytest.mark.parametrize("field", ["router_name", "https_entrypoint"])
def test_an_empty_input_is_refused(field: str) -> None:
    arguments = {"router_name": ROUTER, "https_entrypoint": "websecure"}
    arguments[field] = ""
    with pytest.raises(ValueError):
        runtime_override.build_override(**arguments)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python -m pytest -q tests/contract/test_runtime_override.py'
```

Expected: FAIL — `ModuleNotFoundError: No module named 'agentic_postgres.runtime_override'`.

- [ ] **Step 3: Write the module**

Create `src/agentic_postgres/runtime_override.py`:

```python
"""The router labels Compose cannot interpolate.

`compose.yaml` carries the identity labels and the network hint but neither
`traefik.enable` nor the router and service labels. A router label's *key*
contains the router name, and interpolation inside a label key is not portable
to `COMPOSE_MINIMUM_VERSION` (ADR 0013), so the keys are rendered here — once,
by the only component that holds a host manifest.

Values are deliberately *not* all rendered. `ACME_RESOLVER_NAME` and
`BASELINE_MIDDLEWARE_CHAIN` stay as interpolation references so that they keep
coming from the root-owned runtime env file rather than from the rendered
directory: an operator who can write a project's rendered output must not
thereby be able to change which resolver issues its certificate, or drop the
middleware chain from its routes.
"""

from __future__ import annotations

from typing import Any

import yaml

from agentic_postgres.naming import HEALTH_ROUTE_PATH

#: The service in `compose.yaml` that carries the public route.
ROUTED_SERVICE = "edge-probe"

#: `services/edge-probe/probe.py` LISTEN_PORT. Traefik needs the container port;
#: the probe publishes none, because only Traefik publishes a host port.
ROUTED_SERVICE_PORT = 8080

__all__ = [
    "ROUTED_SERVICE",
    "ROUTED_SERVICE_PORT",
    "build_override",
    "render_override",
]


def build_override(*, router_name: str, https_entrypoint: str) -> dict[str, Any]:
    """Build the override document for one project's health route."""
    if not router_name:
        raise ValueError("router_name is required")
    if not https_entrypoint:
        raise ValueError("https_entrypoint is required")

    router = f"traefik.http.routers.{router_name}"
    service = f"traefik.http.services.{router_name}"

    return {
        "services": {
            ROUTED_SERVICE: {
                "labels": {
                    "traefik.enable": "true",
                    f"{router}.rule": (
                        "Host(`${PROJECT_DOMAIN:?required}`) && "
                        f"Path(`{HEALTH_ROUTE_PATH}`)"
                    ),
                    f"{router}.entrypoints": https_entrypoint,
                    f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
                    f"{router}.middlewares": "${BASELINE_MIDDLEWARE_CHAIN:?required}",
                    f"{router}.service": router_name,
                    f"{service}.loadbalancer.server.port": str(ROUTED_SERVICE_PORT),
                }
            }
        }
    }


def render_override(*, router_name: str, https_entrypoint: str) -> bytes:
    """Serialize the override deterministically, with a header saying what it is."""
    document = build_override(
        router_name=router_name, https_entrypoint=https_entrypoint
    )
    header = (
        "# Generated from host.yaml and the rendered compose.env by ./deploy.sh.\n"
        "# Do not edit; do not shell-source. Router label keys are rendered\n"
        "# because Compose cannot interpolate inside a label key (ADR 0013).\n"
    )
    body = yaml.safe_dump(
        document, sort_keys=True, default_flow_style=False, width=10_000
    )
    return (header + body).encode("utf-8")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python -m pytest -q tests/contract/test_runtime_override.py'
```

Expected: PASS, 9 passed.

- [ ] **Step 5: Wire it into the deploy**

In `bin/deploy-session-2.py`, add `runtime_override` to the package import at line 43:

```python
from agentic_postgres import deployed_output, edge_state, installed_release, runtime_override
```

Append to step 4, after `install_rendered`:

```python
    _write_root_only(
        rendered_directory / "runtime-compose.override.yaml",
        runtime_override.render_override(
            router_name=_env_value(rendered_directory / "compose.env", "HEALTH_ROUTER_NAME"),
            https_entrypoint=host["edge"]["https_entrypoint"],
        ),
    )
```

The router name is read back out of the installed `compose.env` rather than re-derived from the key. Deriving it again would create a second path to the same answer, and the failure that produces is a router the render never named.

- [ ] **Step 6: Run the full gate and commit**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && git add -A && git commit -q -m wip && source .venv/bin/activate && bin/session-01-check.sh 2>&1 | tail -20'
```

Expected: `PASSED`, **1206 passed, 4 skipped**.

```bash
wsl -d Ubuntu bash -lc "cd ~/projects/agentic-postgres && git commit -q --amend -F - <<'MSG'
feat(session-2): generate the runtime override that nothing generated

bin/compose.sh adds runtime-compose.override.yaml as a second model file in
--runtime mode, and ADR 0013 explains why its router label keys must be
rendered rather than interpolated. No component produced the file, so a project
would have started with no traefik.enable and no router, and never been routed.

Label keys are rendered because Compose 2.24 cannot interpolate inside one. The
resolver and the middleware chain stay interpolation references, so they keep
coming from the root-owned runtime env file rather than from the rendered
directory an operator might write.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG"
```

---

### Task 4: Make the writer scan see what it claims to see

`test_every_state_file_a_launcher_requires_has_a_writer` returns one path for four launchers. It missed `deployment.json` because the launcher composes that path with `local` and interpolation, and it missed two `.yaml` files because the pattern demands `.json`. ADR 0020 authorizes this change.

**Files:**
- Modify: `tests/contract/test_edge_state.py:118-169`

**Interfaces:**
- Consumes: the writers created in Tasks 1-3.
- Produces: `_launcher_state_files(text: str) -> set[str]` in `tests/contract/test_edge_state.py`.

- [ ] **Step 1: Write the meta-test first**

A scan that measures nothing passes silently. Add this above the existing scan test, mirroring `test_repository_contract.py:283`:

```python
def test_the_scan_resolves_a_composed_path() -> None:
    """The scan must see a path built from a root, not only a whole literal.

    The original scan matched `readonly NAME="/etc/....json"` and nothing else.
    Three of the four files a launcher requires are declared with `local` and
    built by interpolating a `readonly` root; two of them end in `.yaml`.
    """
    planted = "\n".join(
        [
            'readonly STATE_ROOT="/etc/agentic-postgres/projects"',
            '  local deployment="${STATE_ROOT}/${project_key}/planted.json"',
            '  local contract="${STATE_ROOT}/${project_key}/planted.yaml"',
            '  local ignored="${STATE_ROOT}/${project_key}"',
        ]
    )
    found = {path.rsplit("/", 1)[-1] for path in _launcher_state_files(planted)}
    assert found == {"planted.json", "planted.yaml"}
```

- [ ] **Step 2: Run it to verify it fails**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python -m pytest -q tests/contract/test_edge_state.py::test_the_scan_resolves_a_composed_path'
```

Expected: FAIL — `NameError: name '_launcher_state_files' is not defined`.

- [ ] **Step 3: Write the resolver and rewrite the scan**

Replace lines 145-153 of `tests/contract/test_edge_state.py` — the `required` collection loop — with a helper defined above `test_every_state_file_a_launcher_requires_has_a_writer`:

```python
def _launcher_state_files(text: str) -> set[str]:
    """Every /etc or /var file one launcher opens, including composed paths.

    Unknown variables become a placeholder segment rather than disqualifying the
    path: `${project_key}` is a systemd instance name, so the *file* is what
    this scan is after and the directory it sits in varies by project.
    """
    roots = dict(re.findall(r'^readonly (\w+)="([^"$]+)"', text, re.M))

    resolved: set[str] = set()
    for raw in re.findall(r'^\s*(?:readonly|local) \w+="([^"]+)"', text, re.M):
        path = re.sub(r"\$\{(\w+)\}", lambda m: roots.get(m.group(1), "_"), raw)
        if "$" in path or not path.startswith(("/etc/", "/var/")):
            continue
        if path.rsplit("/", 1)[-1].rsplit(".", 1)[-1] in {"json", "yaml", "env"}:
            resolved.add(path)
    return resolved
```

Then the collection loop becomes:

```python
    required: set[str] = set()
    for launcher in sorted((REPO_ROOT / "libexec").iterdir()):
        if launcher.is_file():
            required |= _launcher_state_files(launcher.read_text(encoding="utf-8"))

    assert len(required) >= 4, (
        f"the scan found only {sorted(required)}; it is measuring almost nothing. "
        "Four launchers open state files under /etc."
    )
```

Leave `write_primitives`, the `sources` collection and the orphan assertion exactly as they are.

- [ ] **Step 4: Run the meta-test to verify it passes**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python -m pytest -q tests/contract/test_edge_state.py -v 2>&1 | tail -15'
```

Expected: PASS. If `test_every_state_file_a_launcher_requires_has_a_writer` fails here, read the orphan list before changing anything — it is naming a real file with no writer, and the answer is a writer, never a narrower scan.

- [ ] **Step 5: Confirm the scan now sees the whole surface**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, \"tests/contract\")
from pathlib import Path
from test_edge_state import _launcher_state_files
found = set()
for l in sorted(Path(\"libexec\").iterdir()):
    if l.is_file():
        found |= _launcher_state_files(l.read_text(encoding=\"utf-8\"))
print(*sorted(found), sep=chr(10))
"'
```

Expected, five paths — `edge-state.json`, `host.yaml`, and the three under `projects/_/`:

```
/etc/agentic-postgres/edge-state.json
/etc/agentic-postgres/host.yaml
/etc/agentic-postgres/projects/_/manifest.yaml
/etc/agentic-postgres/projects/_/outputs.json
/etc/agentic-postgres/projects/_/secrets.required.yaml
```

- [ ] **Step 6: Run the full gate and commit**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && git add -A && git commit -q -m wip && source .venv/bin/activate && bin/session-01-check.sh 2>&1 | tail -20'
```

Expected: `PASSED`, **1207 passed, 4 skipped**.

```bash
wsl -d Ubuntu bash -lc "cd ~/projects/agentic-postgres && git commit -q --amend -F - <<'MSG'
test(session-2): the writer scan found one path for four launchers

test_every_state_file_a_launcher_requires_has_a_writer is the general form of
the edge-state defect, and it could only ever find the one file it was written
for: its pattern wanted a readonly declaration ending in .json, while the
project launcher composes its paths with local and interpolation over two .yaml
files.

The scan now resolves ${VAR} against readonly assignments in the same launcher,
matches local as well as readonly, and accepts .yaml and .env. A meta-test
plants a composed path and asserts the scan resolves it, because a scan that
measures nothing passes silently.

Authorized by ADR 0020.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG"
```

---

### Task 5: Prove it on the host

Every defect this session that mattered was invisible offline. Nothing above is finished until the systemd path — which has never executed once — runs.

**Files:** none. This task changes no code.

- [ ] **Step 1: Transport the tested commit**

```bash
wsl -d Ubuntu bash -lc 'cd ~/projects/agentic-postgres && git push && ~/apg-tr.sh'
```

`~/apg-tr.sh` lives outside the repository. It refuses a dirty tree, bundles the
commit and `scp`s it; no GitHub credential ever lands on the VPS.

- [ ] **Step 2: Confirm the host is at the new commit**

```bash
wsl -d Ubuntu bash -lc 'ssh -i ~/.ssh/agentic_postgres_ed25519 op@62.238.99.122 "cd ~/agentic-postgres && git rev-parse --short HEAD && git status --porcelain"'
```

Expected: the commit from Task 4, clean tree. `install_release` refuses a dirty tree.

- [ ] **Step 3: Deploy**

On the host, from `~/agentic-postgres`:

```bash
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
  --capabilities capabilities.yaml --through-session 2
```

Expected: exit 0, ending `deploy: alpha-dev deployed through session 2`. Step 3 of its output also reinstalls the release at the new commit, which retires the stale `d4e3633`.

- [ ] **Step 4: Verify both roots exist with the right ownership**

```bash
sudo ls -la /etc/agentic-postgres/projects/alpha-dev/
sudo ls -la /var/lib/agentic-postgres/rendered/alpha-dev/
```

Expected: `/etc` holds `manifest.yaml`, `secrets.required.yaml`, `bootstrap-state.json`, `compose.env`, `outputs.json`; `/var/lib` holds `compose.env`, `outputs.json`, `runtime-compose.override.yaml`. Directories `0700 root:root`, files `0600 root:root`. No `.incoming` or `.previous` left behind.

- [ ] **Step 5: Run the systemd path, which has never run**

This is the point of the task. Correcting the launcher proves nothing until it executes.

```bash
sudo systemctl start agentic-postgres-project@alpha-dev
sudo systemctl status agentic-postgres-project@alpha-dev --no-pager
```

Expected: active, no exit 4. If it exits 4, the message names the file — read it rather than guessing.

- [ ] **Step 6: Verify the route from the host, then from outside**

```bash
curl -k --fail https://alpha-db.agenticpostgresql.com/__apg/healthz
```

Then from a different network — the redirect-port defect was invisible from the host:

```bash
wsl -d Ubuntu bash -lc 'curl -sS -o /dev/null -w "%{http_code} %{redirect_url}\n" http://alpha-db.agenticpostgresql.com/__apg/healthz; curl -ksS -o /dev/null -w "%{http_code}\n" https://alpha-db.agenticpostgresql.com/__apg/healthz'
```

Expected: `301 https://alpha-db.agenticpostgresql.com/__apg/healthz` with no port, then `200`. The certificate is staging and therefore untrusted; `-k` is expected here and `--fail` is not a certificate check.

- [ ] **Step 7: Prove the edge reconciles the attachment**

```bash
sudo bin/edge.sh --host host.yaml restart && sleep 15 && \
  curl -k --fail https://alpha-db.agenticpostgresql.com/__apg/healthz
```

Expected: 200. This is the attachment-reconciliation proof from the session-02 plan's Run 6.

- [ ] **Step 8: Run the gate on the host checkout**

```bash
source .venv/bin/activate && bin/session-01-check.sh
```

Expected: `PASSED`. Then record the run in the session evidence and stop — production ACME promotion is Run 7 and is not part of this plan.

---

## Self-review

**Spec coverage.** Design §3.1 → Task 1 step 4. §3.2 → Task 1 step 5. §3.3 → Task 1 step 6. §3.4 → Task 2 steps 3-5. §3.5 → Task 3. §3.6 → Task 1 step 7. §4 (error handling) → Task 2 step 3 helpers, which carry the symlink refusal, `0700`/`0600` and atomic replace. §5 (testing) → Tasks 1-4 offline, Task 5 on the host. §6 (sequencing) → task order, with the refinement recorded below.

**Placeholders.** None. Every code step carries the code.

**Type consistency.** `rendered_path` returns a directory in Task 1 and is consumed as a directory in Task 2 step 4. `_write_root_only(path, payload)` takes `bytes` in Task 2 and is fed `render_override(...) -> bytes` in Task 3 step 5. `_env_value(path, key) -> str` feeds `build_override(router_name=...)`, which takes `str`. `ROUTED_SERVICE` is used as the service key in both the module and its test.

**Test counts.** 1183 baseline, +8 (Task 1), +6 (Task 2), +9 (Task 3), +1 (Task 4) = 1207. If a task's count differs from the plan, stop and find out why before continuing; a silently absorbed count is how a weakened test hides.

## Divergences

Recorded rather than reconciled, per the standing constraint.

| Source says | Plan does | Why |
|---|---|---|
| Design §6 sequences the generalized scan as step 2, before the fix | Tasks 1-3 fix, Task 4 generalizes; the *observation* of the failing scan is Task 1 step 1 | Every commit must be green on a clean tree. The scan cannot pass until writers exist, so committing it first would leave a red gate. The observation the design asks for still happens first, and is recorded in Task 1 step 1. |
| Brainstorming chose "deploy-session-2.py generates the override" over a dedicated module | The decision to write it lives in `deploy-session-2.py`; the pure builder lives in `src/agentic_postgres/runtime_override.py` | Design §5 requires offline unit tests for the override builder, and `bin/` is not an importable package. Ownership is unchanged — the deploy still owns the file, because it holds the host manifest. |
| Session-02 plan Run 1 lists `schemas/deployment-state.schema.json` | No such schema; the deployed document is `outputs.json` under `outputs.schema.json` with `document_kind: "deployed"` | The tree wins over the plan. |
| Session-02 plan calls the rendered-label rule "D12" | Cited as ADR 0013 | `compose.yaml:56-58` cites ADR 0013. |
| `libexec/agentic-postgres-project` reads `.installed_release_commit` | Reads `.source_commit` | That field exists only in `edge-state.schema.json`. A deployed document records `source_commit`. |

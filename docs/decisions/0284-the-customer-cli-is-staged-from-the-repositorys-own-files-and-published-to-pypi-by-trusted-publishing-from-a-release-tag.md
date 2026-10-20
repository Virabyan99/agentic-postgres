# 0284 — The customer CLI is staged from the repository's own files and published to PyPI by trusted publishing from a release tag

- **Status:** Accepted
- **Date:** 2026-10-19
- **Session:** 43, Run 1 (`docs/plans/session-43-implementation-plan.md`,
  D2652, D2666, D2667, D2683, D2684, D2685; rig 43d)
- **Affects:** `bin/cloud.py` (a marked import seam; `plans` leaves it;
  `--version`; the program name), `bin/build-cli.py` (new, Run 6),
  `.github/workflows/publish-cli.yml` (new, Run 6), `LICENSE` (new, Run 6),
  the GitHub environment `pypi`, PyPI's pending publisher for
  `agentic-postgres-cli`. Requirements `DX-PKG-001`, `DX-PKG-002`.
- **Related:** ADR 0093 (a `bin/` command imports only `agentic_postgres` and
  `yaml`), ADR 0246 (the hosted boundary), ADR 0252 (the control plane's
  accounts), ADR 0274 (plans), D1425 (deploy, sweep and tag on one commit),
  D2041 (tags pushed from the workstation), D2594.

## Context

A customer today runs the CLI from a clone: fourteen shims in `bin/` exec
`bin/cloud.py`, which puts `src/` on `sys.path` and imports
`agentic_postgres.control_client`, `scram` and `plans`. `plans` re-exports the
auth service's own module through `service_source`, which resolves
`services/auth-api` from the repository root and so cannot travel in a wheel.
D2594 asks for a distribution holding only the customer families, versioned as
the release, installed with `pipx` or `uv tool`, and published from CI by
PyPI's trusted publishing, *"only from a tagged commit whose CI passed"*. The
operator chose the name `agentic-postgres-cli` and the command `apg` (D2652).
The repository is public and had no licence. The operator chose
**Apache-2.0** on 2026-10-19 (D2685).

## Measured

Rig 43d (2026-10-19, WSL `~/s43/rigs/43d/`, `~/s43/rigs/43d.txt`; uv 0.12.1):

- `bin/cloud.py` staged by hand as `apg_cli/cli.py`. The seam is lines 82–87,
  `REPO_ROOT`, the `sys.path` insert and the three `agentic_postgres` imports,
  replaced by `from apg_cli import control_client as cc`, `from apg_cli
  import scram` and `from apg_cli.control_client import ClientError`. The one
  reader of `plans` (`INTEREST_PLANS`, `:1298`) was replaced for the rig only.
  `control_client.py` and `scram.py` were copied byte-for-byte (both import the
  standard library only). A generated `pyproject.toml` (setuptools, no
  dependencies, `[project.scripts] apg = "apg_cli.cli:main"`) built with `uv
  build --wheel --sdist`: a 27,186-byte wheel and a 25,636-byte sdist.
- The wheel installed with `pip install --no-index` into `--network none`
  containers. In `python:3.12-slim@sha256:a6e34c59…` and
  `python:3.11-slim@sha256:e88e9763…`, `apg --help` and `apg login --help`
  printed **byte-for-byte** the usage that `bin/cloud.py --help` and
  `bin/cloud.py login --help` print from the tree (the control). Both exit 2:
  the top-level parser has `add_help=False`, so `--help` is a usage error
  today, in the tree as well as in the wheel. **`python:3.10-slim@sha256:6ff50646…`
  fails** at import: `from datetime import UTC` (3.11+). So
  `requires-python = ">=3.11"` (D2683).
- The usage text says `usage: cloud.py`: `argparse.ArgumentParser(prog="cloud.py")`
  (`:1509`). The packaged command must say `apg` (D2684).
- `pypa/gh-action-pypi-publish` **v1.14.2** (released 2026-07-29), tag object
  `a892a5a61159132606e93a2fa6f4358831b04d26` → commit
  **`dc37677b2e1c63e2034f94d8a5b11f265b73ba33`**.
- PyPI's documentation
  (<https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>,
  read 2026-10-19): *"A "pending" publisher does not create a project or
  reserve a project's name until it is actually used to publish. If you create
  a "pending" publisher but another user registers the project name before you
  actually publish to it, your "pending" publisher will be invalidated."* The
  name was still free at 19:4xZ (`/pypi/agentic-postgres-cli/json` → 404). The
  operator registered the pending publisher (Sheet C2: `agentic-postgres-cli`
  / `Virabyan99` / `agentic-postgres` / `publish-cli.yml` / `pypi`) and chose to
  let the first publish, Session 43's tag, claim the name.

## Decision

1. **One source, staged at build time.** `bin/cloud.py`'s import block is
   wrapped in `# packaging seam: begin` / `# packaging seam: end`.
   `bin/build-cli.py --out DIR` stages `apg_cli/` from it: `__init__.py`
   (`__version__` = `VERSION`), `__main__.py`, `cli.py` (`cloud.py` with only
   the seam replaced), and byte-equal copies of `control_client.py` and
   `scram.py`. It adds a generated `pyproject.toml` (`name =
   "agentic-postgres-cli"`, `version` = `VERSION`, `requires-python =
   ">=3.11"`, no dependencies, `license = "Apache-2.0"`, `[project.scripts] apg
   = "apg_cli.cli:main"`), a README and the repository's `LICENSE`, then runs
   `uv build`. **Nothing staged is committed.** `--out` inside the repository
   is refused, and the tests build into `tmp_path`.
2. **`plans` leaves the CLI.** `plan notify-me` reads `GET /v1/plans` and
   refuses locally a name that is absent or `active`, with today's message.
   `INTEREST_PLANS` is removed.
3. **The command names itself.** The parser's `prog` is the invoked name's
   basename (`cloud.py` from the tree, `apg` from the package), so each prints
   its own usage. `cloud.py` gains `--version`.
4. **Published only from a release tag whose `contract` run succeeded.**
   `.github/workflows/publish-cli.yml` runs on a tag matching
   `[0-9]+.[0-9]+.[0-9]+` and has `permissions: {}` at the top. Job `verify`
   reads that SHA's `contract` runs and passes only on a `success`; an empty
   list fails, as does any other conclusion (D1057). The tag must equal
   `VERSION`. Then `build` runs, then `publish`. `publish` runs in environment
   `pypi`, holds `id-token: write`, and uses `pypa/gh-action-pypi-publish` at
   `dc37677b2e1c63e2034f94d8a5b11f265b73ba33`. **No token exists anywhere**:
   PyPI trusts the workflow, the repository and the environment, and the `pypi`
   environment admits only release tags.
5. **Apache-2.0.** `LICENSE` at the repository root (the Apache License 2.0
   text, unmodified). The wheel and the sdist carry it.

## Alternatives

- **A committed copy of the CLI in a package directory**: two sources that
  drift. The repository's tests exercise `bin/cloud.py`, so a copy would ship
  code no test ran. Rejected.
- **Publishing the repository's own `pyproject.toml`**: it describes the
  whole product (server code, operator commands) and `plans` would still need
  `services/`. Rejected.
- **An API token in a GitHub secret**: a stored credential that can publish
  from any workflow that reads it. Trusted publishing binds the publish to one
  workflow file and one environment. Rejected.
- **`requires-python = ">=3.12"`** (D2666's fallback): rig 43d shows 3.11 runs
  the CLI. The lowest version that passes is the honest floor.

## Consequences

- A customer installs with `pipx install agentic-postgres-cli` or `uv tool
  install agentic-postgres-cli` and runs `apg`, with no clone.
- **A PyPI version can never be re-uploaded.** A broken `1.21.0` is fixed by
  `1.21.1`, which is a release under D1425's one-commit rule: a CLI-only fix
  costs a release of four.
- Until Session 43's tag publishes, the name is not booked. If someone takes it
  first, the pending publisher is invalidated and the operator chooses again
  (§9's stop). The distribution name is one constant in `bin/build-cli.py`.
- The CLI's version is the product's, so a customer's `apg --version` names
  the release whose API it was built against.

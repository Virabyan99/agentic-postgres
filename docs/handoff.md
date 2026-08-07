# Handoff — environment and workflow

For whoever (or whatever) picks this up next. Onboarding is in
[new-team-member.md](new-team-member.md); this file covers only the things
about *this machine* that are not obvious from the repository.

## Where the project lives

```
/home/gmpar/projects/agentic-postgres        # inside WSL2 Ubuntu — the real location
\\wsl$\Ubuntu\home\gmpar\projects\...        # same thing, seen from Windows
```

It is **not** on the Windows drive, and that is deliberate. `chmod 0600` on
NTFS silently becomes `0666`, and `0600` output modes are a tested contract
here (`CFG-006`). It is also outside OneDrive, whose sync engine holds file
handles and would make the render's rename-based publish intermittently fail.

Open it with:

```bash
wsl -d Ubuntu
cd ~/projects/agentic-postgres
code .          # launches VS Code in WSL mode
```

Do **not** open `\\wsl$\...` as a folder from Windows VS Code — that treats it
as a network share, which is slow and breaks the integrated terminal.

## Starting a session

```bash
cd ~/projects/agentic-postgres
export PATH="$HOME/.local/bin:$PATH"   # shellcheck, jq, uv live here
source .venv/bin/activate
bin/doctor.sh                          # exits 0 when everything is present
```

`bin/doctor.sh` returning 3 tells you exactly what is missing.

## Git

Identity and credentials are already configured:

- Remote: `https://github.com/Virabyan99/agentic-postgres` (private)
- Author: `Virabyan99 <gmparstone99@gmail.com>`
- Credential helper: the Windows `gh.exe`, wired in as a repo-local config, so
  `git push` from inside WSL works with no extra login.

```bash
git add -A
git commit -m "..."
git push
```

Branch is `main`. Nothing else is set up — no branch protection, no CI secrets.

## Three environment traps that already cost time

**`pyenv-win` leaks into WSL.** WSL inherits the Windows `PATH`, so a bare
`python` can resolve to `/mnt/c/Users/gmpar/.pyenv/pyenv-win/shims/python` — a
CRLF Windows script that dies with `bad interpreter`. Under `set -euo pipefail`
that kills whatever script hit it. Always activate `.venv` first; `doctor.sh`
detects and names this specific case.

**Writing files through `\\wsl$\` strips the executable bit.** If you edit a
script from Windows, `chmod +x deploy.sh bin/*.sh bin/*.py` afterwards. The git
index modes are what the contract tests check (`100755`), so a stripped bit
shows up as a test failure, not a silent break.

**Line endings.** The Windows Git config sets `core.autocrlf=true` system-wide.
`.gitattributes` overrides it for this repository. Do not remove that file — a
CRLF checkout breaks every `#!/usr/bin/env bash` shebang.

## Before you claim anything works

```bash
bin/session-01-check.sh
```

That is the gate. CI runs the identical script — there is no second definition
of passing. It requires a clean tracked tree, and it writes
`evidence/session-01.json` from parsed test artifacts rather than from
hand-entered numbers.

For fast iteration: `bin/smoke-test.sh`, or
`bin/session-01-check.sh --allow-dirty` (which deliberately writes no evidence,
because evidence must describe a committed state).

## The deployment host

Session 2 added a second machine. It is not a development environment, and the
repository on it is a checkout of an installed commit rather than a place to
edit.

- Transport is **`git bundle` + `scp`**. No GitHub credential exists on the VPS,
  and none should be created there.
- `host.yaml`, `capabilities.yaml`, `project.alpha.yaml` and `project.beta.yaml`
  live only on the host and are gitignored individually. They name a real
  machine, real DNS and a real provider organisation. **Never commit them.**
- `sudo` there needs a TTY, so anything privileged is run by a human at a
  terminal rather than piped over `ssh`.
- `bin/session-01-check.sh` also runs there and needs **both** `~/.local/bin`
  (uv, shellcheck, jq — reached by `bash -l` sourcing `.profile`) and
  `.venv/bin` (python, ruff, pytest — reached only by activating). Either alone
  fails. `bin/lock-dev-deps.sh --check` runs `uv pip compile`, so the gate needs
  PyPI egress from wherever it runs.

Everything else about operating it is in the
[Session 2 operator guide](session-02-operator-guide.md).

## Starting Session 3

Read, in this order:

1. [The Session 2 divergence table and decision log](plans/session-02-implementation-plan.md)
   — every ambiguity that was closed, and why. **New ambiguities go there or
   into an ADR; they do not get resolved inline.**
2. [The product contract](product-contract.md) and the
   [ADRs](decisions/README.md).
3. [The acceptance matrix](acceptance-matrix.md).

Activating a requirement means **removing its `future` marker and implementing
the body** — the placeholder already fails when executed, which is what makes it
activatable. The gate then enforces that nothing owned by session ≤ N is still a
placeholder via `APG_ACCEPTANCE_SESSION`.

Preserve `--render-only`. Do not weaken an active test to make a new one pass.
A contract test changes only with an ADR.

**The defect pattern to look for.** Session 2's recurring failure — five times
in Run 7 alone — was *a value that looked measured and was not*: a hard-coded
`"staging"` where an environment should have been read, a network name copied
from the wrong scope, a placeholder substituted somewhere nobody looked, a
filesystem fact standing in for a logic test, and an evidence key naming the
suite that ran rather than the thing it proved. Each passed for exactly as long
as its wrong answer happened to coincide with the right one. When a test is
green, ask what would have to break for it to go red.

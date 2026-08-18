# Handoff — environment and workflow

For whoever (or whatever) picks this up next. Onboarding is in
[new-team-member.md](new-team-member.md); this file covers only the things
about *this machine* that are not obvious from the repository.


## The live handoff is not here

**`CLAUDE.md` at the repository's launch folder is the per-run status**: what is
done, what is next, and the traps. This file describes the *machine and the
workflow* and is deliberately not rewritten every run — if the two disagree
about where the project stands, `CLAUDE.md` is right.

## The session documents

- [The API surface](api-surface.md) — what is published, the four authorities in
  order, and the three verbs the document advertises and the surface refuses.
- [API operations](api-operations.md) — the divided connection budget, the
  restart matrix, and rotating each of the three credentials.
- [Session 5 operator guide](session-05-operator-guide.md) — deploying,
  capturing the snapshot, the gate's three modes, and the evidence merge.
- [Session 6 operator guide](session-06-operator-guide.md) — the identity plane
  and the signing-key cutover's phases.
- [Session 7 operator guide](session-07-operator-guide.md) — object storage: the
  bucket, the token, the cleanup and rotation surface, and **§5.4, the host
  sequence for the trip that has not happened yet**.

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

## The database

Session 3 gave every project its own PostgreSQL 18 cluster. Four documents, and
the operator guide is the entry point:

- [Session 3 operator guide](session-03-operator-guide.md) — deploying a project
  with its database, the gate, the evidence, and the traps
- [The database](database.md) — the image, the volume, the memory budget, the
  identity a volume carries
- [Migrations](migrations.md) — templates, the rendered payload, dbmate, and why
  the ledger is written by the superuser
- [Database security](database-security.md) — thirteen roles, two authorities,
  forced RLS, and one statement that reports success and stores nothing

`bin/session-03-check.sh` is the gate, in two modes. There is no external mode.

## The transports

Session 4 gave every project a PgBouncer pool alongside the direct endpoint, and
a developer a way to reach either. Four documents, and the operator guide is the
entry point:

- [Session 4 operator guide](session-04-operator-guide.md) — deploying the
  transports, the gate in three modes, the two-half evidence, and the traps
- [Database connections](database-connections.md) — the two transports, the three
  access profiles, the tunnel, the broker, and why nothing is published
- [Client compatibility](client-compatibility.md) — psql, Prisma, Node `pg` and
  Psycopg, and what transaction pooling costs each of them
- [Pool operations](pool-operations.md) — the settings that matter, the admin
  console, the restart matrix, and the credential rotation

`bin/session-04-check.sh` is the gate, in three modes, and it needs both the host
and the external half: `transport_boundary` and `connection_tooling` are measured
from off-host, so a session document cannot be written from a host run alone
([ADR 0045](decisions/0045-a-claim-is-shaped-by-where-it-can-be-measured.md)).

## Starting a session

Read `CLAUDE.md` first — it says which run is next. Then, in this order:

1. **The current session's divergence table and decision log**, in
   `plans/session-0N-implementation-plan.md` §1 — every ambiguity that was
   closed, and why. **New ambiguities go there or into an ADR; they are never
   resolved inline.** Earlier sessions' tables are still cited by number and
   remain the record: sessions
   [02](plans/session-02-implementation-plan.md),
   [03](plans/session-03-implementation-plan.md),
   [04](plans/session-04-implementation-plan.md),
   [05](plans/session-05-implementation-plan.md),
   [06](plans/session-06-implementation-plan.md),
   [07](plans/session-07-implementation-plan.md).
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

Session 3 produced it again, in a form worth naming separately: **a proof that
had never been executed against the thing it describes.** A `--check` that could
not fail. A grant surface nothing rendered. Three tests asserting psql's printed
booleans. Two tests reading a key that exists only on the other branch of the
output schema. A password check run on the side of the boundary the image
trusts. And a launcher fix that shipped inside two installed releases and was
never once run, because the only thing that installed launchers was
provisioning. Green, all of it, until something executed it.

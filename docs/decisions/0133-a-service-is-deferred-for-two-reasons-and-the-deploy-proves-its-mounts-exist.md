# 0133 — A service is deferred for two reasons, and the deploy proves its mounts exist

Status: accepted
Date: 2026-08-22
Session: 8, Run 10
Affects: ADR 0063, ADR 0113, D381, D410, D463,
`src/agentic_postgres/runtime_override.py`, `bin/deploy-project.py`

## Context

The first deploy of the agent plane anywhere **failed**, on both projects:

```
IsADirectoryError: [Errno 21] Is a directory: '/etc/mcp/jwks.json'
```

The container mounts two files out of the rendered directory — the key set it
verifies with (ADR 0113) and the compiled capability lock (ADR 0127). **Docker
creates a bind-mount source that does not exist as a directory**, so the fourth
verifier opened a directory where its key set should be and exited 1.

`deploy-project.py` already carries a comment naming this trap, written for
PostgREST:

> *"A bind mount whose source does not exist is created by Docker as a
> **directory**, and the symptom of that is a service reading a key set it
> cannot parse."*

The trap was known. The guard did not reach the new consumer.

## What was measured

On the host, at `bf1d398`, after four deploys:

| Observation | Value |
|---|---|
| `apg-alpha-dev-mcp-1`, `apg-beta-dev-mcp-1` | **Exited (1)** |
| the other fourteen containers | up, healthy, untouched |
| `/var/lib/agentic-postgres/rendered/alpha-dev/jwks.json` | **a directory**, `drwxr-xr-x`, created at deploy time |
| `…/mcp-capability-lock.json` | **a directory**, same timestamp |
| the deployed document | still **v11**, `routes.mcp: null`, no `mcp` block |

And the ordering, read out of `deploy-project.py`:

| line | step |
|---|---|
| 1327 | `install_rendered(...)` — the rendered directory is **replaced** |
| 1332 | step 5: `project-runtime.sh --defer <POST_BOOTSTRAP_SERVICES> up` |
| 1413 | `render-jwks.py --rendered-dir <rendered>` — the key set is **written** |
| 1453 | `mcp-contract.sh lock` — the capability lock is **written** |
| 1518 | step 6b: the deferred services start |

**`mcp` is not in `POST_BOOTSTRAP_SERVICES`, so step 5 starts it — eighty lines
before the two files it mounts are written.**

The deploy then fails at line 1413 rather than continuing: `render-jwks.py`
finishes with `staging.replace(destination)`, and replacing onto a directory
raises. So the deployed document is never written, and **every subsequent deploy
fails identically** until the directories are removed. That is the behaviour to
keep: it is loud, and it refused to publish a document claiming an agent plane
that had not started.

## The cause, and it is not a typo

`MCP_SERVICE`'s own docstring explains the exclusion, correctly:

> *"That is why it is **deliberately absent from `POST_BOOTSTRAP_SERVICES`** …
> every other application service is in that tuple because it logs in as a role
> the bootstrap plane must activate first. This one has no role to activate
> (D410)."*

Every word of that is true. `test_the_agent_plane_is_absent_from_the_post_bootstrap_services`
asserts it and is **right**.

**The constant was doing two jobs under one name.** A service lands in it for
one stated reason — *it authenticates as a role the bootstrap must activate* —
and the deploy uses it for a second, unstated one: *it must not start before the
deploy has written the files it mounts*. PostgREST needs both, so membership
satisfied the second by accident, and nothing ever separated them.

The agent plane needs the second and **not** the first. It was excluded for a
correct reason about the first, and lost the second with it.

**This is §6's question 5 — *when a decision is implemented, which of its callers
got it?* — and D381's family.** Storage was declared the third verifier in four
places and handed no key set. Here the mount was written in the right run, by an
author who cited D381 while writing it, and the *start ordering* was the caller
nobody asked about.

## Decision

**1. Two constants, because there are two reasons.**

```
POST_BOOTSTRAP_SERVICES   cannot start until the bootstrap has activated the
                          role they authenticate as              (ADR 0063)
POST_ARTIFACT_SERVICES    cannot start until the deploy has written the files
                          they mount                             (this ADR)
DEFERRED_SERVICES         the union -- what `--defer` receives
```

`mcp` joins the second and stays out of the first, so D410's assertion and its
docstring remain true as written. Nothing is weakened: a service that needs both
appears in both, and a service that needs one is a deliberate entry rather than
an omission somebody has to notice.

**The union is computed, not typed.** A third list that had to agree with two
others is the shape this repository has paid for repeatedly (D175, D264).

**2. The deploy proves its file mounts exist before it starts anything.**

The ordering fix makes *this* instance impossible. It does not make the class
impossible: the next service to mount a file the deploy writes late will fail
the same way, at the same silent seam, and the failure will again arrive as a
runtime error inside a container rather than as a refusal from the deploy.

So before step 5's `up`, the deploy asks `runtime_override.file_mount_sources()`
for every host path the override mounts **as a file**, and refuses if any is
missing or is a directory. The message names the path and says what Docker will
do with it.

**Derived from the override the deploy is about to write**, not from a second
list. A hand-maintained inventory of mounts is exactly the thing that goes stale
when a mount is added — which is the defect this ADR exists because of.

## Alternatives rejected

**Add `mcp` to `POST_BOOTSTRAP_SERVICES`.** One line, and it works. It also makes
the constant mean two things while its docstring names one, and puts a service
with no database role in a tuple defined as "services that authenticate as a
role the bootstrap must activate". The next reader would either believe the
docstring and be wrong, or believe the membership and go looking for the role.
**The bug was one name carrying two ideas; solving it by adding a third case to
that name is the same bug with more members.**

**Move `render-jwks` and the lock compile before step 5.** It fixes the ordering
without splitting the concept, and it is the wrong direction: the key set is
derived from the secret generation that **step 5 materializes**, which is why the
step sits where it does and why the deploy re-reads the generation immediately
after. Moving it would publish a key set derived from the superseded generation —
D76's trap, which the code above it already warns about.

**Create the files as empty placeholders so the mount finds something.** A zero
byte `jwks.json` is a verifier that starts and refuses every request with `no key
with kid`, which is a container that **looks deployed** (D381's own words). The
current failure is better: it is loud, immediate, and stops the deploy.

**Let the healthcheck catch it.** The agent plane has one and it would have gone
red — after Compose restarted the container, after the deploy had moved on, and
with the same message a genuinely unready plane produces. A start that cannot
succeed should not be attempted.

## Consequences

- **The agent plane starts in step 6b**, with the other three application
  services, after the key set and the lock exist. It still holds no database
  credential and still activates no role; only its start time moved.
- **A missing file mount is now a named refusal** with the path in it, for every
  service, including ones added later.
- The two directories Docker created on the host must be removed before the next
  deploy can succeed — `rmdir`, which refuses a non-empty directory and is
  therefore the safe verb. That is a one-time repair of damage already done, not
  part of the fix.
- **`POST_BOOTSTRAP_SERVICES` keeps its meaning and its tests.** This ADR adds a
  concept rather than redefining one, which is what lets D410's assertion stand
  unchanged.

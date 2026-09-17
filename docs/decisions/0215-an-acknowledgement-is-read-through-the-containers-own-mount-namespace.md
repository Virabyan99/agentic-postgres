# 0215 — An acknowledgement is read through the container's own mount namespace

- **Status:** Accepted
- **Date:** 2026-09-17
- **Session:** 28, Run 8 (D1468–D1478)
- **Affects:** `bin/rotate-signing-key.py`'s `loaded_digest`, the one reader
  behind `acknowledge` and therefore behind `promote`'s refusal. No schema, no
  migration, no deployment. The rotation has never been performed, so nothing
  in the field has ever depended on the reading this replaces.
- **Supersedes:** ADR 0122's *mechanism* for reading a verifier's key set. Its
  decision — that the verifier roster is a table and every verifier is in it —
  is untouched.
- **Related:** ADR 0088 (the cutover), ADR 0195 (a report may not substitute an
  answer for not knowing), ADR 0155 (a deploy recreates a container whose
  mounted content changed), D276, D305, D411, D427, D591.

## Context

`acknowledge` exists to answer one question: **what key set is this verifier
actually holding?** `promote` — the irreversible step — is refused until every
verifier's answer matches the published set. The whole design rests on that
reading being of the *process*, not of the host.

`loaded_digest`'s own docstring has said so since Session 8:

> A read of the container's filesystem, not of the host path. The two differ
> exactly when it matters: a replaced file leaves the container bound to the
> previous inode, so the host shows the new set and the process is verifying
> against the old one.

And `tests/contract/test_rotate_signing_key.py` states the consequence in as
many words: *"a command written the second way would report every verifier as
current no matter what it held."*

**Rig 28j measured that `docker cp` is a command written the second way.**

### What was measured, with both controls in the same run

A native `dockerd 27.5.1`, a file bind-mounted into a running container, and the
file then replaced by `write beside, rename over` — which is exactly what
`bin/render-jwks.py`'s `write()` does:

| | the host file | `/proc/<pid>/root/<path>` | `docker cp` |
|---|---|---|---|
| **control** — before anything moves | `ORIGINAL` | `ORIGINAL` | `ORIGINAL` |
| **subject** — after the atomic replace | `REPLACED` | **`ORIGINAL`** | **`REPLACED`** |
| **control** — after a recreate | `REPLACED` | `REPLACED` | `REPLACED` |

The middle row is the whole finding. The process is bound to the unlinked inode
and is verifying against `ORIGINAL`; `docker cp` re-resolves the bind mount's
**source path** and returns the host's current bytes. The two readers agree in
both control rows, so this is a difference that appears exactly where it
matters and nowhere else.

**So `acknowledge` reports every verifier as holding the published set the
moment the deploy has written it** — recreated or not — and `promote` unblocks
on that. That is D276's symptom arriving through the step built to prevent it.

### Why it was not caught before

The rotation has never been performed (D860), and no rig had ever replaced a key
set under a running container: rig 28d, this run's own rehearsal, produced its
"behind" state by *recreating* containers onto a different file, which both
readers report identically. The defect lives in the one transition nobody had
reproduced.

ADR 0122 chose `docker cp` for a good and still-true reason: the locked
PostgREST image is distroless and has neither `cat` nor `sh` — both exit **127**,
re-measured on today's image — so `docker exec … cat` could not read the only
verifier the roster then held. That correction fixed *readability* and, without
anyone noticing, replaced *what was being read*.

### The candidate, measured in the same run

`/proc/<pid>/root/<path>`, where `<pid>` is the container's init as `docker
inspect` reports it, traverses the container's **own mount namespace**. It
resolves the mount rather than the path, needs no binary inside the image — so
the distroless problem does not come back — and needs root, which this command
already requires for every step.

## Decision

**An acknowledgement is read through the container's own mount namespace, by
pid, and never by a path the host resolves.**

1. `container_pid(container)` reads `docker inspect -f '{{.State.Pid}}'`.
2. `read_path(pid, jwks_path)` is a pure function returning
   `/proc/<pid>/root/<jwks_path>`, so the shape stays assertable offline.
3. `loaded_digest` hashes that file's bytes.

**A pid of `0` is the third outcome, reported and never folded** (ADR 0195). A
container whose init pid is not visible to this host is one whose key set this
command cannot read, and it says so and exits 5 — it does not fall back to a
reading it has just decided is wrong. Docker Desktop's Linux VM reports `0` for
exactly this reason, which is why the new reader could not be measured on the
workstation and was measured against a native daemon instead.

**`docker cp` does not remain as a fallback.** A fallback here is the defect
with a retry in front of it: it would produce a clean acknowledgement in the one
case the primary reader refused, which is the case that matters.

## Consequences

**`promote` can no longer be unblocked by a verifier that was not recreated.**
That is the property ADR 0088 has claimed since Session 6 and has not had.

**One new failure mode, and it is a loud one.** If the host's daemon does not
report a usable pid, `acknowledge` refuses and the rotation cannot proceed —
where before it would have proceeded on a false reading. Session 29's sheet
turns that into a pre-flight: `sudo docker inspect -f '{{.State.Pid}}' <any
project container>` must print a non-zero number **before** the window opens,
not in the middle of it.

**This changes a credential path immediately before the session that performs
it, and that is a real risk taken deliberately.** The alternative is a sheet
that tells an operator to trust a reading measured to be wrong in the one
direction that unblocks an irreversible step. The rotation has never run, so no
deployment depends on the old behaviour, and both readings are exercised by the
tests this ADR authorises.

**A passing contract test is replaced by a stricter one**, which is what this
ADR is for (`docs/CLAUDE.md` §6). `test_the_digest_is_read_from_inside_the_container`
asserted `docker cp` while its own docstring described the property `docker cp`
violates; the replacement asserts the pid path, keeps the forbidden-mechanism
list, and adds the host's mount source to it.

**What is still not measured**: the host's own daemon. The measurement is from
`dockerd 27.5.1` in `dind`, which is a native daemon of the same family as the
VPS's and not the VPS's. The pre-flight above is what makes that gap visible
before it costs anything.

## Alternatives rejected

**Leave it, and say so in the sheet.** This was the first instinct — a
rehearsal records, it does not repair. It fails on what the record would have to
say: *the step that guards the irreversible one cannot tell you what you need to
know.* A sheet carrying that sentence describes a rotation nobody should
perform.

**`docker exec … cat`, again.** ADR 0122's measurement stands: the distroless
PostgREST has no `cat` and no `sh`, both 127, re-measured on today's locked
image. It also reintroduces a dependency on what happens to be inside a third
party's image.

**`nsenter --target <pid> --mount -- cat`.** The same namespace, one more
binary, and one more thing to be absent on a host. `/proc/<pid>/root` is the
same traversal with nothing between it and the kernel.

**Hash the host file and compare mtimes or inodes instead.** An inode number is
not evidence about what a process has open, and a reading that infers *held*
from *written* is the assumption this ADR exists to delete.

**Keep `docker cp` and add a recreate-then-read.** It hides the question rather
than answering it: after a recreate both readers agree, so the command would be
asserting a state it had just caused rather than measuring the one it found.

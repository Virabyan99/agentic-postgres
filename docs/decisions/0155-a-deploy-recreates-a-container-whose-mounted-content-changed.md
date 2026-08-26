# 0155 — A deploy recreates a container whose mounted content changed

- **Status:** accepted
- **Date:** 2026-08-26
- **Session:** 10, Run 11
- **Related:** ADR 0088 (a verifier acknowledges by being recreated), ADR 0113
  (a non-issuing verifier reads the rendered `jwks.json` by path), ADR 0133
  (`DEFERRED_SERVICES` is derived, never declared), ADR 0154 (the render decides
  a mode; the install decides an owner), **D591**, D588, D589.

## Context

`install_rendered` installs a project's rendered directory atomically:
`shutil.copytree` into a staging directory, then `os.replace(staging,
destination)`. That is deliberate — a half-installed directory is a project the
next boot treats as complete — and it means **every file gets a new inode on
every deploy**.

`bin/project-runtime.sh` then runs `compose up -d --build --wait`. Compose
decides whether to recreate a container by hashing its **service definition**,
and a bind mount's source path is the identical string on every deploy. So
nothing looks changed, the container is left running, and it keeps its open file
handle on the **deleted** inode.

Measured on the host, mid-session: the installed `pgbackrest.conf` was
`-r--r--r--` dated 06:14 while the running container saw `-rw------- 0 root
root` dated 05:36 — **link count 0**. The container had been created before two
consecutive, individually correct fixes (D588, then D589), and **neither could
reach it**. Three deploys were spent on that.

This is not a backup problem. **ADR 0088 has the same residual and says so**:
*"a verifier acknowledges by being recreated"*, and the deploy prints *"the key
set CHANGED: every verifier must be RECREATED, not restarted"* on every run — a
warning followed by relying on Compose to notice a change it structurally cannot
see. A JWKS rotation has this defect, and so does any future bind-mounted
artefact.

## Decision

**A third Compose override carries one label per service whose value is a digest
of what that service bind-mounts.** Compose hashes labels into the config hash,
so a service whose mounted *content* changed is recreated and one whose content
did not is left alone.

- `runtime_override.mounted_paths_by_service` reads the inventory **out of the
  runtime override** rather than from a list — ADR 0133's rule, and for its
  reason: a hand-maintained inventory of mounts is exactly what goes stale when
  a mount is added, and a stale one here means a container silently not
  recreated, which is the defect.
- `runtime_override.mounted_digest` covers each source's **path and bytes**, and
  for a directory every file under it. A source that does not exist contributes
  a marker: at step 5 the deferred services' artefacts do not exist yet, and
  refusing to compute would fail a correct deploy. Its absence being *part of*
  the digest means the artefact arriving is itself a change.
- `bin/render-mount-digests.py` writes it, called from `bin/project-runtime.sh`
  **immediately before `up`** and after the secret override — the same placement
  and the same reason: it must describe the files as they are when the
  containers are created, which is after the deploy has written its late
  artefacts and after a reboot has changed nothing.
- `bin/compose.sh` loads it last, so its labels merge over the router labels.

### Rejected: `--force-recreate`

It is one word and it works. It also restarts **every** container on **every**
deploy, including the ones nothing touched — turning a convergence step into a
full outage each release, on a host where three services gate on `postgres:
service_healthy`. The digest recreates exactly the affected containers.

## Consequences

- **A rotation is no longer a warning.** After ADR 0088's cutover the rendered
  `jwks.json` changes, its digest changes, and all four verifiers are recreated
  by the same mechanism — without anybody remembering to.
- **The digest must not move when nothing moved.** A digest covering an mtime,
  an inode or the render time would recreate the world on every deploy — the
  rejected option in disguise. This is asserted, and the assertion had to be
  repaired: battery arm U2 (a digest over `st_mtime_ns`) **survived** the first
  version of the test, because Linux stamps files from a coarse clock and two
  files written microseconds apart share an mtime. The test now moves the mtime
  deliberately.
- **Absence and emptiness must differ.** Battery arm U4 survived the first
  version of that test too, because the artefact it created was non-empty and
  the digests differed on content regardless. A file that arrives empty — a
  truncated render, a failed write — is now a change.
- The label leaks nothing: the output is one hex digest per service, which
  matters because some of what a service mounts is a credential.
- **What is not proved offline is Compose.** That a changed label causes a
  recreate is Compose's behaviour and needs a daemon; it belongs to the host
  gate. What is proved offline is that the label has the two properties that
  behaviour would be worth anything for.

## What this does not decide

Whether `install_rendered` should preserve inodes for unchanged files instead.
That would remove the cause rather than make it visible, but it trades an atomic
directory replace — whose failure mode is a project that never half-exists — for
a per-file merge whose failure modes are numerous and quiet. The digest was
chosen because it makes the change *visible* without making the install *clever*.

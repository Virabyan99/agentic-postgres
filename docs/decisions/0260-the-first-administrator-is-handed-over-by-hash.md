# 0260 — The first administrator is handed over by hash

- **Status:** Accepted
- **Date:** 2026-10-07
- **Session:** 38, Run 1 (D2163)
- **Affects:** `bin/project.sh create|claim` and `src/agentic_postgres/control_client.py`
  (Run 8), the reconciler's `admin` step (Run 6), the control set's `0004`
  (`project.create`'s `handoff_sha256` argument), `schemas/operation-arguments.schema.json`.
  No release migration: the reset plane every project already has is used as
  it is. Requirement `LIFE-HANDOFF-001`.
- **Related:** ADR 0173 (the administrator issues a reset and never learns the
  password), ADR 0171 (the stored digest is deterministic), ADR 0246 (the
  control plane holds nothing that opens a project's data or admin plane),
  ADR 0253 (the control plane stores hashes of keys and invitations), ADR 0256.

## Context

The stage plan (D1969) has the reconciler bootstrap the creating member as the
project's first `project_admin` and show *"the one-time secret once to that
member"*. The reconciler is pull-based: anything it shows the member transits
the control database, which would make the control plane — the
internet-facing process and its database, backups and WAL — a holder, however
briefly, of a credential to the new project's admin plane.

Every project already has a reset plane (`0026`):
`app_private.auth_open_password_reset(user, issued_by, token_hash, expires_at)`
**takes the hash**, and `POST /auth/reset-password {reset_token, password}` is
unauthenticated and lets the SUBJECT choose the password. Rig 38c measured
the whole handoff on the locked image with the release set and the auth app
in-process:

- `T = secrets.token_urlsafe(32)` is 43 characters and well-formed for the
  product's `one_time_tokens`, whose `hash_token(T)` equals `sha256(T)` in hex;
- the superuser's `auth_open_password_reset(user, user, sha256(T), now() + 24 h)`
  stored `sha256(T)` (self-issued is accepted: `issued_by` is a real foreign
  key to the same user);
- `T` presented → 200, and the chosen password logs in → 200.
- Controls: a wrong `T` → 401; **`sha256(T)` presented as the token → 401**;
  `T` a second time → 401; the bootstrap password after the consume → 401.

## Decision

1. **The member's CLI mints `T` locally** (`bin/project.sh create`), keeps it
   at `$XDG_CONFIG_HOME/apg/handoffs/<operation-id>` (0600, the CLI's state
   rules) and sends only `handoff_sha256 = sha256(T)` in the creation request.
2. **The reconciler, after the first deploy,** bootstraps the administrator
   with `auth-admin.sh bootstrap --username <admin_username> --password-fd N`
   and a random 32-byte password it writes to a pipe and never stores, reads
   the new user's id, and calls — as the superuser in the PROJECT's database,
   through `container_exec.run` — `app_private.auth_open_password_reset(user,
   user, :'hash', now() + interval '24 hours')`. The random password is then
   useless to everyone, because nobody holds it.
3. **`bin/project.sh claim --project KEY`** reads the project's `routes.app`
   from `GET /v1/projects/{key}`, presents `T` at its `/auth/reset-password`
   with a password from `--password-file` or a TTY, and deletes the handoff
   file.
4. **`T` reaches the control plane never; `sha256(T)` opens nothing.** The
   stage plan's *"shown once"* becomes *"never shown to the control plane at
   all"*.

## Alternatives rejected

- **The reconciler writes a one-time password into the operation's result.**
  The control database would hold a credential to the project's admin plane
  until read, and in its WAL and backups after.
- **The control plane mints `T` and shows it once.** The same, one step
  earlier.
- **A new release migration for a handoff table.** The reset plane is the
  handoff already; a second one is two implementations of one value (ADR
  0002's argument).

## Consequences

- A member who loses the handoff file before claiming cannot claim, and the
  reset expires in 24 hours. No project administrator exists yet to issue
  another through `/admin`, and **no command re-opens a handoff in Session
  38**: recovery is the operator's, as root, by the same superuser call with a
  new hash the member sends out of band — named in the plan's §10, not built.
- The bootstrap password is never logged, stored or printed; a proof reads
  that no reconciler log line or argv carries it.

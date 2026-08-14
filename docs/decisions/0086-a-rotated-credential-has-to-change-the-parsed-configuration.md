# 0086 — A rotated credential has to change the parsed configuration

Status: accepted
Date: 2026-08-14
Session: 6, Run 10
Affects: D252, D163, ADR 0061, `edge_credentials.py`, `docs/api-operations.md`

## Context

D252 is a live product defect, found on the host during the first documentation
credential rotation this project has ever performed. The new password returned
401, the old password returned **200**, and the correct new hash was on disk
throughout. The diagnosis in `docs/api-operations.md` names the mechanism —
the middleware declares a `usersFile` *path*, so rewriting the file behind that
path leaves the parsed configuration identical, Traefik has nothing to rebuild,
and the middleware never re-reads the file it already read — and prescribes
`bin/edge.sh --host host.yaml restart` as the operator's repair.

It had never been measured against the locked image, only inferred from the
symptom. This run measured it, and measured the repair.

## The measurement

Locked Traefik, file provider with `watch: true`, one `basicAuth` middleware,
two bcrypt hashes for two different passwords produced inside the locked Python
runtime image. Control at the start of each pass: password one is accepted and
password two is refused, so the rig can tell the two credentials apart.

**A rewritten `usersFile`, the middleware definition unchanged** — ten seconds:

    old password   200      <- still works
    new password   401
    control        the new hash is the one on disk

D252 exactly, now reproducible offline.

**The same file rewritten, plus one unrelated byte changed in the middleware's
own definition** (`realm: rig` → `realm: rig2`) — ten seconds:

    old password   401
    new password   200

So the provider is watching, and the reload is real. What triggers the
middleware's rebuild is a change to the **document the provider parses**, not a
change to a file that document names.

**The hash inline, in `basicAuth.users`, rewritten in place** — ten seconds:

    old password   401
    new password   200

## Decision

**The bcrypt hash goes inline in `basicAuth.users`, in the document the file
provider parses.** There is no `.htpasswd` file and no `usersFile`.

The property this buys is not "Traefik reloads" — it already did. It is that
**the artifact a rotation rewrites and the artifact the provider parses are the
same artifact**, so a rotation cannot be applied to something nothing is
watching. The old shape made the correct-looking action a no-op, and the symptom
was a credential that had been rotated everywhere except where it is checked.

`assert_bcrypt` keeps its job unchanged: Traefik still refuses every non-bcrypt
htpasswd format with a 401 indistinguishable from a wrong password (D165), and
that is still checked here rather than discovered on the host.

`docs/api-operations.md` loses the `bin/edge.sh --host host.yaml restart` step
from the documentation-credential rotation. The edge restart was a real repair
for a real defect and it is no longer needed; leaving it in would be an
instruction whose reason had been removed, which is the shape D177 punished.

## Alternatives

**Keep the `usersFile` and make the deploy touch the middleware document.**
Measured to work — that is the `realm: rig2` pass above. Refused: it makes
correctness depend on a second write whose only purpose is to be noticed, and
the failure mode of forgetting it is silent and is precisely D252 again. A
checksum-of-the-credential field written into the document would be the tidy
version of the same trick, and it is still two artifacts where one will do.

**Keep the `usersFile` and restart the edge on every credential rotation.** The
currently documented repair. It works, and it takes every project's routes down
for the restart to rotate one project's documentation password.

**Two files, with the `.htpasswd` extension the provider ignores.** That
property was measured in Session 5 and is real (`test_the_credential_file_is_not
_read_as_configuration`). It was load-bearing for the `usersFile` shape and is
now simply not needed: with the hash inline there is no second file to hide from
the parser. The test that proves it keeps running, because the directory is
shared and a future contributor adding a `.htpasswd` should still find that the
provider ignores it.

## Consequences

- One file per project in the dynamic directory instead of two.
- The hash now appears in a file the file provider parses and logs errors about.
  It is a bcrypt hash of a password, root-owned, in a root-owned directory, and
  it was already in a sibling file in the same directory — no boundary moves.
- **A credential rotation is now a rewrite of one document and nothing else.**
  No edge restart, so rotating project A's documentation password does not
  interrupt project B.
- D253 is untouched and still open. It is the same class of defect one layer
  down — a *container* holding a stale generation because `compose up` without
  `--force-recreate` does not recreate for a changed bind-mount source — and it
  needs its own measurement of Compose's recreate behaviour.

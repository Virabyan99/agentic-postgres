---
title: Branches
description: Copies of a project, and restoring to a point in time.
ledger: [branches, restore_to_branch, backups_and_pitr]
---
# Branches

A branch is a full copy of a project, restored from the project's own backups, with its own two passwords and its own two doors. One branch per project on the Free plan.

**A branch is not backed up**: deleting it, or losing the server, loses what it holds. An expiry, if you set one, deletes it then.

## Making a branch

A branch name is 2 to 12 lowercase letters and digits, starting with a letter, and not `main`. The console's *Branches* view makes the two passwords in your browser, sends only their verifiers, and shows them once. With the command-line client the passwords are written to a directory you name:

```
apg branch create --branch dev --password-dir ./branches --wait
apg branch list
apg branch show --branch dev
```

## Restoring to a point in time

A restore makes a new branch at a moment inside the project's backup window; the project itself is never overwritten.

```
apg branch create --branch before --password-dir ./branches --at 2026-10-20T09:30:00Z --wait
```

## Resetting and deleting

A reset restores the branch again -- to a moment, or to the end of the backups -- with two new passwords; what was written to it is lost. A delete needs the branch's name typed again.

```
apg branch reset --branch dev --password-dir ./branches --wait
apg branch delete --branch dev --confirm dev --wait
```

To connect to a branch, add `--branch dev` to `apg endpoint connect`.

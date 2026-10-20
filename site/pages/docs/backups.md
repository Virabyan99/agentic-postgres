---
title: Backups
description: The restore window, and what sleeping does to it.
ledger: [backups_and_pitr, restore_to_branch, sleep, export]
---
# Backups

Backups are continuous, to off-site object storage, with a nightly copy to a second provider. A project's restore window -- the span a branch can be restored to -- is shown with how recently it was read, and never shown when it could not be read.

```
apg project backups
```

The console's *Backups* view shows the same reading. When it says the window could not be determined, it gives the reason instead of a window.

## Sleeping stops backups

While a project sleeps its backups stop, so its last restore point is the moment it went to sleep. Waking it starts them again.

## Restoring

A restore is always into a new branch -- see [Branches](/docs/branches/). The project itself is never overwritten.

## Exporting

An export is the project's own data -- the `app`, `api` and `public` schemas -- as one archive, downloaded once by the person who asked, within 15 minutes:

```
apg project export --output ./export.tar.gz
```

The console's project *Settings* shows the download link once.

Something here wrong or missing? Write to [invite@agenticpostgresql.com](mailto:invite@agenticpostgresql.com).

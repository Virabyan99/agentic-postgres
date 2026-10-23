---
title: Plans and usage
description: The Free plan, usage readings, notifications, sleep and compute size.
ledger: [plan_free, plan_premium, usage, notifications, sleep, idle_sleep, compute_profiles, region]
---
# Plans and usage

## Plans

During the beta every organisation is on the Free plan, at no cost: one project, one branch per project, every compute size. Storage and agent calls are shown against usage and not enforced. The Premium plan is defined and not available during the beta; *Notify me* records that you asked. [Pricing](/pricing/) lists every limit.

```
apg plan list
apg plan show
apg plan notify-me
```

## Usage

A project's usage over a window -- its database's size, its backup repository's, its branches, its connections, the requests it answered, the time it was awake and asleep -- is read every five minutes. A figure that could not be read is said, never shown as zero.

```
apg usage show --hours 24
apg usage show --organization ORGANIZATION
```

## Notifications

One for every finished operation, and a notice once a day when a project passes 80% of a shown limit. Nothing is emailed.

```
apg notifications list --limit 50
```

## Sleep, idle sleep and size

A project can be put to sleep and woken; its data is kept, and while it sleeps its doors refuse connections and its backups stop. It can also sleep after 15, 30 or 60 minutes with no request and no connection; that is off unless you turn it on.

```
apg project sleep
apg project wake
apg project idle-sleep --minutes 30
apg compute set --profile standard
```

A size change restarts the project. Every project runs in one location, the one server this beta runs on.

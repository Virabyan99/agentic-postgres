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

A project's usage over a window -- its database's size, its backup repository's, its branches, its connections, the requests it answered, the time it was awake and asleep -- is read every five minutes. A figure that could not be read is said, never shown as zero. In the console: a project's *Usage*, and an organisation's *Usage* for all its projects.

```
apg usage show --hours 24
apg usage show --organization ORGANIZATION
```

## Notifications

An organisation's *Notifications* page lists what happened to its projects, newest first, each in one sentence with a link onward. **Nothing is emailed**: the page is where they appear. Five kinds of event make one:

| Kind | Made when | Its link |
|---|---|---|
| Started | a project creation, a branch, a restore or a branch reset began | the operation's own page, to follow it |
| Finished | an operation succeeded, or failed and said why | the operation's page; a finished creation links to *Connect* |
| Asleep | a project went to sleep after its idle time | the project's *Settings*, to wake it |
| Expired | a branch reached its expiry time and was deleted | the project's *Branches* |
| Limit near | a project passed 80% of a limit your plan shows, at most once a day | the organisation's *Plan and usage* |

```
apg notifications list --limit 50
```

## Limits, before you reach them

When an organisation holds every project its plan allows -- or all but one, on a plan with more than one -- a banner at the top of *Projects* and *New project* says so, such as *Free plan: 1 of 1 project*, with *See plans* and *Your plan*. A project being created already counts. While the plan is full, or while a creation is under way, *New project* is disabled and says why, and a creation is refused before its form is sent, `plan_limit_reached`, with nothing recorded. A project that holds every branch its plan allows shows the same banner on *Branches*.

## Sleep, idle sleep and size

A project can be put to sleep and woken; its data is kept, and while it sleeps its doors refuse connections and its backups stop. It can also sleep after 15, 30 or 60 minutes with no request and no connection; that is off unless you turn it on.

```
apg project sleep
apg project wake
apg project idle-sleep --minutes 30
apg compute set --profile standard
```

A size change restarts the project. Every project runs in one location, the one server this beta runs on.

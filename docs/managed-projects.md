# Managed projects

Since Session 43 (ADR 0283) **the customer documentation is the public site**:
its sources are `site/pages/` in this repository, built by
`bin/build-site.py` and published at https://agenticpostgresql.com/docs/ by
`.github/workflows/site.yml` after `contract` succeeds. What this page used to
say -- creating and claiming a project, sleeping and waking, idle sleep, sizes,
exports, deletion, the two database doors, backups, branches, plans, usage,
Query Insights and monitoring, notifications, and what each refusal means -- is
`site/pages/docs/` now, written for a customer and checked against the
[Reality Ledger](reality-ledger.md) at every build.

The operator's half -- slots, the reconciler, revocation -- is the
[operator guide](operator-guide.md) §20; the routes and the roles are in
[the control plane](control-plane.md).

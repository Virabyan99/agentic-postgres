# 0168 — A rule states what its silence means, and each hop reports its own failure

- **Status:** accepted
- **Date:** 2026-09-02
- **Session:** 14, Run 5 (`OPS-ALERT-001`, D782–D789)
- **Related:** **D782** (the certificate metric exists, and Run 4's filter dropped
  it), **D783** (`up == 0` and `absent(up)` answer different questions), **D784**
  (two hops, one signal), **D785** (a regex is not a YAML string), **D786** (the
  fixture-staleness hole fired), **D787** (D762 paid a third time), **D788** (the
  drift guard met a third category), **D789** (five of the plan's failure classes
  have no series), ADR 0167 (a metric reads from the decision that owns its
  value), ADR 0164 (the surface, and the store's place in it), ADR 0165 (a
  telemetry component carries an explicit memory limit), ADR 0147 (the one named
  egress residual), D769 (an absent series is not a zero), D553 (a rule that
  always fires), D145 (a rule that never fires), D300 (never loosen an allowlist
  to a subset check).

## Context

`OPS-ALERT-001` asks for two things and the second is the harder one: **a rule
fires when the failure is induced, and a healthy deployment produces none.**

This repository has already shipped both failure modes. `failed_count > 0` stood
at 26 on a healthy, fully-caught-up cluster (D553) — a rule that would have
fired always. `postgrest --ready` returned 0 while every request 404'd (D145) —
a signal that never fired. Between them they describe the whole risk here, and
the second is worse: **a rule that cannot fire is indistinguishable from a
deployment that is well.**

Two facts shaped the run before any rule was written.

**The collector cannot evaluate anything.** It serves exposition; an alert needs
a range over time. So `OPS-ALERT-001` needs a store, or it needs no rules.

**Run 4 built five of the plan's nine candidate metrics and deliberately left
four classes unbuilt** — backup, WAL, disk, and the connection family — each for
a reason recorded there. So most of the plan's named failure classes arrive at
Run 5 with **no series to write a rule over**.

## Decision

### 1. The store is Prometheus, on measured numbers

Bounded, against a real scrape target with ingestion confirmed at both ends
(Run 1): **Prometheus 21.2 MB anon, peak 37.4; VictoriaMetrics 45.6, peak 48.2.**
The reputation inverts under measurement — VictoriaMetrics ships the far smaller
image (17.5 MB against 104.3) and carries twice the resident set, and on a
swapless host the resident set is what decides an OOM. Prometheus also evaluates
rules natively where VictoriaMetrics needs `vmalert`: half the memory and one
fewer container.

It carries an explicit `mem_limit` (ADR 0165), holds no credential, has **no
router label of any kind**, and originates no connection off the host. ADR 0164
published the *collector* at the edge exactly so the store never needs to be
reachable from outside the deployment — a store with a router would be a query
interface over this project's whole metric history behind one password.

**It is on `edge` rather than `internal`, and that diverges from ADR 0164 §3's
wording deliberately.** Following that sentence literally would mean putting the
*collector* on `internal` so the store could meet it there — reversing Run 2's
decision to keep the collector off `internal` entirely, and widening the reach of
the one container that is published at the edge. The property §3 was protecting
is that the store holds no edge credential and is routed nowhere; both hold.

### 2. Every rule states what an absent series means

A rule over a series that does not exist evaluates to nothing and reports healthy
for ever. **Three different things produce an absence here and they are not the
same event**: the series was never published, nothing has happened yet, or the
emitter has stopped. Each rule names which it means, in a comment, because a rule
is read on the host by whoever is looking at it — and a test refuses a rule that
does not.

### 3. `up == 0` and `absent(up)` are different rules, because they are different failures

Measured, and the assumption was backwards. With a configured target **stopped**,
`up` becomes **0, not absent** — so `absent(up)` did not fire and the plain
comparison did. `absent()` catches a scrape config that vanished; `up == 0`
catches a target that is configured and unreachable. Writing only one leaves a
real gap in whichever direction was chosen.

### 4. Each hop reports its own failure

Two hops carry this project's metrics — store→collector and collector→proxy —
and they fail for different reasons with different remedies. **A single rule
conflated them, measured**: Prometheus's `honor_labels` defaults to false, so the
collector's forwarded `up{job="edge"}` is restamped `job=collector` beside the
store's own, `exported_job` and all. One rule matched two series and named
whichever it caught.

So `honor_labels: true` — the collector is a *carrier*, not an origin, and
everything it serves already carries its own `job` — and three rules where there
was one: `ApgCollectorUnreachable`, `ApgEdgeUnreachable`, `ApgStoreScrapeMissing`.
**The store failing to reach the collector is a failure of the observation; the
collector failing to reach the proxy is a failure of the deployment.** Reporting
them under one name tells an operator to look in the wrong place.

### 5. A threshold is read from the decision that owns it

ADR 0167's rule, applied inside a rule file. `diagnosis.TLS_WARN_DAYS` has owned
"how many days before a certificate deadline matters" since Session 11 — 21,
chosen because Let's Encrypt renews at 30 days remaining, so it means *"renewal
should already have happened and did not"* rather than *"renewal is due"*. A rule
file spelling `21` would be a second authority on that sentence, and one nobody
grepping for the constant would find.

**The test for this had to be repaired by its own mutation battery.** Asserting
that the rendered rule contains `< 21` passes whether the constant was read or
spelled, because the constant *is* 21 — a test comparing two values that are
equal by coincidence. It now moves `TLS_WARN_DAYS` and requires the rule to
follow.

### 6. No rule is written over a metric no deployment publishes

Five of the plan's failure classes have no series (D789): backup freshness, WAL
archiving, disk headroom, pooler saturation and connection counts. **A rule over
a series nothing publishes is silent in exactly the way a healthy deployment
is**, so writing one produces a rule set that looks complete and measures a
fraction of what it names — the more dangerous half of this claim, arriving
disguised as the safe half. A test refuses any rule naming one of those metrics,
and the plan records which classes are unreported and why.

## Consequences

- **The certificate class was rescued, and it cost Run 4's filter a branch.**
  `traefik_tls_certs_not_after` exists at the pinned digest, is absent without a
  certificate, and its value matches `openssl`'s `notAfter` exactly — so a
  certificate deadline needs no new source. But it is labelled `cn`, `sans` and
  `serial`, carrying **neither `router` nor `service`**, so Run 4's two-branch
  filter dropped it and the rule would have been quiet for ever (D782). The
  filter now has a third branch on `cn`. **Question 5 arriving one run later**:
  the filter was written from the labels it had.
- **A regex is not a YAML string** (D785). The `cn` branch is `re.escape`d, so it
  carries `\.` and `\-`; emitted in a double-quoted YAML scalar the collector
  refuses the whole document with *"found unknown escape character"* and exits
  before serving anything. Single-quoted scalars perform no escape processing,
  which is what a regex needs.
- **A certificate covering more than one domain is not served by this.** The `cn`
  branch is an equality, so a project whose domain appeared only in `sans` would
  see its certificate dropped. That is the safe direction — a missed alert rather
  than another project's expiry on this surface — and the rule says an absent
  certificate series means *unknown*, not *fine*.
- **Nothing pages anybody.** There is no Alertmanager and no receiver: a rule with
  no measured false-positive rate is not a rule anybody should be woken by
  (plan §4.4). `ALERTS{alertstate="firing"}` in the store is the observable that
  proves both halves. Routing is a later decision, and `ALERT_FOR_SECONDS` is the
  first number to re-derive from what the deployment actually does when it is
  taken.
- **`ALERT_ERROR_RATIO` is chosen, not measured**, and says so. No deployment here
  has ever been observed under load; Run 6's envelope is what should correct it.
- **The rendered set gained two world-readable files.** `prometheus.yaml` and
  `alert-rules.yaml` join `otelcol.yaml` on exactly its terms: the store runs as
  a uid that does not own the rendered directory, and neither file holds a
  secret. Both allowlists were **widened to the measured set and kept as exact
  equalities** — loosening either to a containment check is the move D300
  forbids.
- **The store keeps a named volume, and it is not scratch.** A rule evaluated over
  a range needs history across a restart; a store that forgot on every deploy
  would report every rule quiet immediately after one, which is what a healthy
  deployment looks like.

## Alternatives considered

**VictoriaMetrics plus `vmalert`.** Rejected on Run 1's measured numbers: twice
the resident set and a second container, for a smaller image that buys nothing on
a host where memory is the constraint.

**Alertmanager now.** It is the routing layer, and nothing routes anywhere yet, so
it would be a container with no consumer — on a host where every container is
measured against 2,110 MB of headroom. Deferred with the receiver decision.

**One `up` rule for both hops.** This is what was written first, and the
measurement rejected it: the two hops are different failures and `honor_labels`'
default silently merged them.

**Writing the backup, WAL and disk rules anyway, against series a later run would
add.** Rejected as the most dangerous option available: every one of them would
have been permanently silent, the rule set would have looked complete, and
`OPS-ALERT-001` would have reported a guarantee nobody had.

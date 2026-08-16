# 0103 — Where a value comes from is not what kind of value it is

Status: accepted
Date: 2026-08-16
Session: 7, Run 2
Extends: [0055](0055-the-contract-declares-what-kind-of-value-a-secret-is.md)
Affects: SEC-BOOT-001, SEC-CRED-001

## Context

Session 7 needs two secrets this repository cannot create. Cloudflare issues an
R2 Access Key ID and Secret Access Key together, shows the secret exactly once,
and never shows it again. Nothing here can generate one, and `--apply` must say
so rather than converge.

The session plan (D311) proposed a **new `value_kind`**. That is the obvious
move — `value_kind` already exists, `generate_secret_value` already dispatches on
it, and ADR 0055 already says an unknown kind is refused. It is also wrong, and
the reason is a measurement rather than a preference.

**Cloudflare's documentation defines the Secret Access Key as the SHA-256 hash of
the API token's value.** It is a 64-character lowercase hex string. That is
byte-for-byte the shape `secrets.token_hex(32)` produces. So for this secret:

- *What kind of value is it?* — `random_hex`. True, and useful: it is what lets
  `_validate_formats` know a `pgpass` consumer could read it.
- *May this repository create one?* — **No.** A generated value would be a
  perfectly-formed credential that authenticates to nothing.

One field cannot answer both. Spelling the kind `operator_supplied` would make
the contract stop stating what the value *is*, and would silently forbid a future
operator-supplied credential from ever being materialized in `pgpass` format,
because that rule is written against `value_kind == "random_hex"`.

This is ADR 0055's own scenario relocated. 0055 exists because a hex string
stored under a name that says *key* would satisfy every check in the repository
and fail several runs later as a JWKS derived from something that is not a key.
Here the hex string would satisfy every check and fail as a signature rejection
from a bucket — with nothing between the cause and the symptom naming the wrong
value.

**A second defect was found while establishing this, and it is the sharper
finding.** `generate_secret_value` had exactly one caller. The fresh-bootstrap
path in `apply()` called `secrets.token_hex(SECRET_ENTROPY_BYTES)` inline —
correct in Session 2, when the sentinel was the only declared secret and hex was
genuinely what it was, and silently wrong from Session 5 onward. Measured with a
control, from one contract in one process: the fresh path produced hex for
`bootstrap_jwt_signing_key`, the converge path a PKCS#8 PEM. **ADR 0055 had been
half implemented for two sessions**, and it never fired only because both live
projects were bootstrapped in Session 2 and reached their later credentials
through `add_missing_secrets`. See D333.

## Decision

**A secret declares `origin` as well as `value_kind`, and they answer different
questions.**

- `origin: generated` — the provider bootstrap creates the value from
  `value_kind`. Every secret through Session 6, stated rather than assumed.
- `origin: operator_supplied` — the value exists only because a third party
  issued it. There is no generator, `--plan` names the secret and where its value
  comes from, and `--apply` creates everything else and stops short of this.

Required on every secret, for the reason `plane`, `format` and `value_kind` are:
a new secret has to state which it is, and a default is how the unstated half
goes unread.

**`generate_secret_value` takes the secret, not its kind.** The origin check runs
first, before any dispatch. A signature that accepted only a `value_kind` string
made the prior question unaskable at the one place a value is created, and a bare
string argument is what made it easy to route around — which is exactly what
`apply()` did for two sessions.

**An operator-supplied secret is never recorded in `managed_resources`, and the
schema refuses it there.** That enum is what `--destroy` reads. §8.2's rule is
that this project removes what it recorded creating and nothing else, and a
credential Cloudflare issued and a human pasted in was not created here.

**`--plan` and `--apply` both name them, always.** Not only when something is
missing: this command deliberately contacts nothing, so it cannot know whether
the operator has done it yet. A standing statement is honest; a "no changes" that
omitted them would not be, and what it hides is a 404 in the middle of the next
materialization — which is D66 exactly.

## Consequences

**The bootstrap can no longer invent a credential it has no business inventing**,
and the refusal is at the point of creation rather than in a caller that has to
remember. The message names the provider path and key the operator must fill in.

**`value_kind` keeps meaning what it meant**, which is what lets the `pgpass`
rule keep working: a future operator-supplied database password can still declare
`random_hex` and be materialized as a libpq password file.

**Every existing secret gained a line.** Eleven declarations now say
`origin: generated`, which is a reviewable diff and is the point — the fact was
already true and was nowhere stated.

**Two tests changed shape, one of them replaced by a stricter form.**
`test_every_required_secret_the_contract_declares_can_be_recorded_as_managed`
now keys its coverage half on `origin: generated` and gains a refusal it did not
have: an operator-supplied secret may **not** appear in `managed_resources`.
Without that second half, the obvious way to make the first half pass would have
been to add both R2 names to the enum — the wrong answer, arrived at by making a
test green.

**A field with one exercised branch is a known risk here, and it is answered.**
D283 is what happens otherwise: `required: false` was read by one of its two
readers and honoured by neither the other nor any test, and the gap surfaced on a
host eleven runs later. Both `origin` values are exercised by the committed
contract from the day the field exists.

## Alternatives considered

**A new `value_kind` (the plan's own proposal, D311).** Rejected on the
measurement above: it would make the contract unable to state a true fact about
the R2 secret access key, and would couple provenance to the `pgpass` format
rule, which is written against `value_kind == "random_hex"`.

**Infer it from `required: false`.** Rejected — they are unrelated. An
operator-supplied secret is *required*; it is `auth_jwt_prepared_key`, a
generated one, that is optional. Conflating them would make the materializer's
404 tolerance apply to a credential whose absence must fail the run.

**Infer it from the provider path or the name prefix.** Rejected for the reason
`is_root_plane` is read from a declared `plane` rather than from the absence of a
service: inference makes a secret that lost the property by accident
indistinguishable from one that never had it.

**Have `--apply` fail outright when an operator-supplied secret is declared.**
Rejected. On a fresh bootstrap the project, identity and client secret are
created first and the client secret cannot be re-read, so failing after them
would leave a live credential nobody asked for; failing before them would mean a
project can never be bootstrapped until a human has visited Cloudflare. Creating
everything it can, and naming precisely what it did not, is the same shape as
D230's two-stage convergence.

**Add a provider read so `--plan` can report whether the value is there yet.**
Rejected for this run, and it is a real cost: the "supply these" list is printed
unconditionally and an operator who has already done it still sees it. Adding a
read would give `--plan` a credential requirement it does not have today —
`--plan` needs no root and contacts nothing — and that property is worth more
than suppressing a line. Materialization already answers the question by exact
key, with a message that names it.

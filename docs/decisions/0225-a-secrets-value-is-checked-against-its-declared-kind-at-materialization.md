# 0225 — A secret's value is checked against its declared kind at materialization

- **Status:** Accepted
- **Date:** 2026-09-19
- **Session:** 31, Run 1 (D1598, carrying D1578 from Session 30)
- **Affects:** `secrets_contract.check_value_kind` (new),
  `bin/materialize-secrets.py`'s write loop. No migration, no schema move —
  `value_kind` already exists on every secret and its enum does not widen.
- **Related:** ADR 0055 (`value_kind` says what the value is), ADR 0103
  (`origin` says who creates it), ADR 0195, D276, D600, D816, D1578.

## Context

Every secret in `secrets.required.yaml` declares a `value_kind`, one of
`random_hex` or `rsa_private_pem`. The schema is explicit about why the field
is required rather than defaulted:

> a default is how a hex string ends up stored under a name that says key —
> and every check in this repository would pass, with the failure surfacing
> several runs later as a JWKS derived from something that is not a key.

**The field has exactly one runtime reader**, and it is not that check: it is
the pgpass cross-check in `secrets_contract.py:543-546`, which refuses a
consumer asking for a non-`random_hex` secret in pgpass format. The
materialization loop in `bin/materialize-secrets.py:219-235` fetches whatever
the provider holds and writes it to a `0o400` file **without ever reading
`value_kind`**. It is a declared field whose stated purpose no code performs —
D816's shape in the file that declares it.

The one PEM check that does exist, `bin/bootstrap-providers.py:159-165`,
validates the delimiters of **the key the product itself just generated**:

> openssl exiting 0 with output that is not a private key is not a case
> anybody expects, and it is exactly the case that would store a truncated
> value and pass.

That reasoning is right and it is applied to the one value that is least
likely to be wrong. **Nothing validates the PEM a human pastes into the
provider console.** For an `operator_supplied` secret no generator runs at
all, so the bootstrap check never sees it.

Session 30's trip produced **four distinct malformations in one day**, none
caught by anything in the repository — only by a script written during the
window. Where a bad value lands today is `render-jwks`, **mid-deploy**, and
that command suppresses openssl's stderr by design, because openssl names the
key's path in its error.

## Decision

**`secrets_contract.check_value_kind(kind, value) -> str | None` is called in
the materialization loop, before the value is written.**

1. **The check belongs where the value first lands on disk.** Earlier is the
   provider, which this product does not own; later is `render-jwks`, which
   cannot say why it failed without printing a path it must not print.

2. **The rules, from the schema's own definitions:**
   - `rsa_private_pem` requires **both** PKCS#8 delimiters (`BEGIN PRIVATE
     KEY` and `END PRIVATE KEY`) **and** a body of at least 1,000 characters.
     The length catches the malformation the delimiters cannot: a truncated
     key that kept its header and footer.
   - `random_hex` requires lowercase hexadecimal.
   - An unknown kind is a contract error, not a value error, and cannot reach
     here — the enum is closed and validated at contract load.

3. **The reason names no byte of the value.** It names the secret's **name**
   and its **kind**, and nothing else. A test plants a sentinel inside a
   malformed value and greps the whole output for it.

4. **A failing check exits 8** — *a secret could not be fetched or written* —
   which is the existing convention for this command and is exactly what
   happened: the secret could not be written.

5. **A value that passes is written unchanged.** The check reads; it never
   normalises, trims or re-encodes. A transformation here would be a second
   place where a secret's bytes are decided.

**Not built here:** distinguishing *deliberately absent* from *mistyped
name*. `required: false` already means the provider is allowed not to hold a
secret, and telling a deliberate absence from a typo in the provider key needs
an `absent at the provider, and optional` declaration that nothing carries
yet. It is §10's item, named rather than silently skipped.

## Consequences

- A malformed operator-supplied key is refused at the moment it would be
  written, by name, instead of surfacing mid-deploy as an openssl failure with
  its explanation suppressed.
- `value_kind` gains the reader its schema description has always described,
  so the field stops being a declaration nobody enforces.
- `bin/materialize-secrets.py` refuses a value it used to write. Both
  projects' provider values are the product's own PEMs — D1578's four
  malformations were all repaired on trip day — so the trip's deploy is the
  live control for the change.
- The bootstrap's own delimiter check stays. It guards a different moment
  (generation) and removing it would trade a cheap check for a later one.

## Alternatives considered

- **Check in `render-jwks`.** It is where a bad value lands today, and it
  cannot report the failure without naming the key's path, which is why it
  suppresses stderr in the first place. Rejected.
- **Check at the provider, on write.** `bootstrap-providers.py` only ever
  creates values the product generated; an `operator_supplied` secret is
  pasted into a console this product does not control. Rejected as
  unreachable.
- **Parse the PEM properly with `cryptography` and verify it is a 2048-bit RSA
  key.** Strictly better validation, and it puts key material through a parser
  inside the one loop whose whole discipline is that the value is never
  formatted, logged, or passed anywhere. Rejected for now; it is a reasonable
  future strengthening under a new ADR.

## Amendment, Run 5 (D1618)

**The sentence "the delimiter-and-length pair catches every malformation
actually observed" was written from the four shapes and not measured against
them. Measured, it caught one.** The rule implemented is therefore stricter
than the one decided above, and what it still cannot reach is named rather
than implied:

| 2026-09-19's malformation | delimiter + length | as implemented |
|---|---|---|
| body pasted without its delimiter lines | **refused** | refused |
| delimiters present but **joined to the body** (1701 bytes, longest line 91) | *accepted* | **refused** — each boundary must be on a line of its own (RFC 7468), which is also what `openssl rsa` enforces |
| **byte-identical on a re-read** — the edit at the provider was never committed | *accepted* | *accepted*, and **it cannot be otherwise**: the value is a well-formed key, just the previous one. This is a staleness question, not a shape question, and nothing in a value answers it. The operator guide's re-read is what answers it. |
| the key **name** carried a trailing dot | not reached | not reached — no value is fetched, and the `absent at the provider, and optional` line is printed. Telling a deliberate absence from a mistyped name is §10's deferred item, above. |

Two of four, with the remaining two out of reach of any check of this kind and
said so. The line-of-its-own rule does not refuse a key wrapped at 76
characters rather than 64, because the body's wrapping is not a boundary and a
false refusal here would block a legitimate key mid-window.

## Amendment, the trip (D1634)

**The two-kind enum could not describe a credential a third party issued, and
the first production run of this check found out.** Alpha's deploy on
2026-09-20 was refused at step 5:

```
materialize-secrets: mirror_s3_secret_access_key: declared random_hex and the
value is not lowercase hexadecimal from end to end
```

The check was right and **the contract was wrong**.
`mirror_s3_secret_access_key` is a Backblaze B2 application key -- 31
characters in a base64url alphabet -- declared `random_hex` since Session 18
added the mirror. Nothing could tell, because until this ADR nothing read the
field. **That is this ADR's own thesis arriving from the other side**: it
argued that a declared field with no reader is an unverified field, and the
first reader found the declaration false.

Its sibling `mirror_s3_access_key_id` is mis-declared identically and
**passed**, because a B2 key id happens to fall inside `[0-9a-f]`. A
declaration that is false and *sometimes* satisfied is worse than one that is
simply false: it would have been read as evidence the pair was checked.

**`opaque` is added to the enum** -- a credential a third party issued whose
shape this product does not define and must not constrain -- and both mirror
secrets are declared with it. `check_value_kind` returns `None` for it, and
the explicit branch matters: an UNKNOWN kind fails closed, because it means
the schema gained one and nobody taught the checker; `opaque` means somebody
considered the shape and concluded there is nothing here to assert. A rule
over a format this product does not own would refuse a working key the day the
provider changed it.

**Cloudflare's four R2 secrets stay `random_hex`, and that is not an
inconsistency.** For them it is TRUE: the secret access key is the SHA-256 of
the token, 64 hex characters. The contract's own comment above them argues
that changing it would be wrong, because the trap there is the opposite one --
a generator could produce a perfectly-shaped credential Cloudflare never
issued, which is what `origin` exists to prevent.

**What this cost and what it bought.** It cost a deploy, stopped before
anything was written, with the running plane untouched and both projects
serving throughout -- which is the check failing in the direction it was built
to fail. It bought a `value_kind` that is true about every secret for the
first time, and an audit
(`test_every_operator_supplied_secret_declares_a_kind_its_issuer_can_satisfy`)
that compares each operator-supplied secret against the issuer that produces
it. **That audit is what should have run before this check shipped**: a
reader was given to a field without walking the declarations it would read.
- **Leave it and document the failure mode.** Four malformations in one day,
  with the only diagnosis being a script written under time pressure during a
  host window. Rejected.

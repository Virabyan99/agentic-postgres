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
  formatted, logged, or passed anywhere. The delimiter-and-length pair catches
  every malformation actually observed. Rejected for now; it is a reasonable
  future strengthening under a new ADR.
- **Leave it and document the failure mode.** Four malformations in one day,
  with the only diagnosis being a script written under time pressure during a
  host window. Rejected.

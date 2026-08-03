# 0008 — Sensitive key detection by terminal token, never substring

- **Status:** Accepted
- **Date:** 2026-08-03
- **Session:** 1
- **Affects:** `CFG-001`, `CFG-009`, and the Session 2 secret-boundary requirements

> Transcribed 2026-08-04 from decision **F** of
> [the Session 1 implementation plan](../plans/session-01-implementation-plan.md).
> The decision was made and implemented in Session 1; only this record was
> missing, and `src/agentic_postgres/config.py` cited it as its source of
> truth.

## Context

Runbook §3.6 requires a project manifest to be rejected when it carries a
secret-bearing key, and requires the same check over rendered output. It names
neither the denylist nor the matching rule.

The matching rule is where this goes wrong. A substring test is the obvious
implementation and it is unusable: `secret` as a substring rejects
`password_secret_ref`, which is the *reference* field the schema requires and
which by construction holds no secret. Once the false positives start, the
allowlist grows until it is load-bearing, and a load-bearing allowlist is a
list of ways to smuggle a credential past the check.

## Decision

**Matching rule.** For every mapping key at every depth, lowercased:

1. If the key is in `SAFE_KEY_ALLOWLIST`, accept. The allowlist is consulted
   first.
2. Reject iff `key in DENY` **or** `key.endswith("_" + d)` for some `d` in
   `DENY`.

That is a whole-key match or a terminal `_`-delimited token match. **Never a
substring test.**

**`SENSITIVE_KEY_DENYLIST`:**

```
password  passwd  passphrase  secret  private_key  access_key
secret_access_key  client_secret  api_token  refresh_token
access_token  session_key  signing_key  credentials  token
```

**`SAFE_KEY_ALLOWLIST`:**

```
password_secret_ref  token_ttl_seconds  token_use  secret_ref
```

**Why the allowlist is not load-bearing, which is the property that matters.**
Under terminal-token matching, none of its four entries actually collides:
`password_secret_ref` ends in `_ref`, not `_password`, `_secret` or
`_secret_ref`; `token_ttl_seconds` ends in `_seconds`. Every entry would be
accepted with the allowlist deleted. It is a regression guard with a test
behind it, not a set of exceptions holding the rule up.

This is also what makes the bare tokens `token` and `secret` safe to list at
all. Under substring matching they would reject a large fraction of any
realistic manifest.

## Consequences

Makes easy:

- `db_password`, `aws_secret_access_key`, `client_secret`, `api_token` and
  bare `password` are all rejected, at any nesting depth, in manifests and in
  rendered output.
- Adding a reference-style field is safe by naming convention rather than by
  amending an exception list.

Makes hard:

- A key named in an unusual way — `pw`, `creds`, `sekrit` — passes. This check
  is a guard against accident, not against an operator determined to store a
  credential in a non-secret file, and it is not the only control: rendered
  output is separately scanned for credential-bearing URLs and presigned-URL
  signatures, and Session 2 adds the leak scan over images, logs, `docker
  inspect` and Compose output.

Enforced by `is_sensitive_key()` in `src/agentic_postgres/config.py`, applied
by `rendering.assert_output_is_secret_free()`, and tested in **both**
directions by
`tests/contract/test_project_manifest.py::test_sensitive_keys_are_rejected` and
`::test_safe_keys_are_not_false_positives`. Testing only rejection would leave
the false-positive behaviour — the thing that actually breaks the design —
unmeasured.

## Alternatives considered

**Substring matching.** Rejected: rejects `password_secret_ref`, and the
allowlist needed to repair that becomes the real policy.

**Leading-token matching** (`key.startswith(d + "_")`). Rejected: it accepts
`db_password` and `aws_secret_access_key`, which are the two most likely
spellings of the mistake being prevented.

**Regex per denied term.** Rejected: fifteen hand-written patterns is fifteen
opportunities to write `.*secret.*`, and the resulting behaviour cannot be
stated in one sentence.

**Value-based detection — entropy or credential-shaped strings.** Rejected for
manifests: it is a heuristic with both error modes, and it inspects values,
which means the check itself must handle secret material. Key-based detection
inspects only names. Value-shaped detection does have a place, and it is where
Session 2 puts it: scanning for one *known* sentinel byte sequence, not
guessing at what a secret looks like.

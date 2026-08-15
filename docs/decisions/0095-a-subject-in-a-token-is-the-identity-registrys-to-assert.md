# 0095 — A subject in a token is the identity registry's to assert

Status: accepted
Date: 2026-08-15
Session: 6, Run 14
Affects: ADR 0051, ADR 0078, ADR 0084, D105, D298,
`bin/dev-token.py`, `bin/api.py`, `migrations/templates/0013-*`,
`tests/deployment/test_session5_*`

## Context

`bin/dev-token.py` has minted `authenticated` tokens carrying a subject since
Session 5. The subject is *derived* rather than accepted — a UUIDv5 of the
project key — for a reason the module states plainly:

> A caller-supplied subject is a caller who can read any owner's rows through a
> policy that is working exactly as designed.

That was sound while a subject was nothing but a row-policy claim. Session 6
built an identity registry, and migration 0013's pre-request hook now compares
a token's subject against it, inside the request's own transaction.

The first host gate run after 0013 returned **ten failures**, all of them
`AP401: the request identity is no longer current`, and one of them was not a
test at all: `bin/api.sh list-notes` — the operator's own read tool — answered
**401** against a correct deployment. It has been broken since 0013 was applied
and nothing could notice, because the host gate had not run since.

## What was measured

`app_private.auth_claims_are_current` is an `EXISTS` over five equalities:

```sql
WHERE u.id = p_user_id AND u.status = 'active' AND u.role_name = p_role_name
  AND u.credential_version = p_credential_version
  AND u.authz_version      = p_authz_version
  AND u.scopes             = p_scopes
```

A bootstrap-issued token carries `role`, `iat`, `exp`, `iss`, `aud` and `sub`.
It carries **no** `credential_version`, **no** `authz_version` and **no**
`scope`, so three of the five comparisons are against NULL, `EXISTS` is false,
and the hook raises `PT401`. This is not a tuning problem: **no value of the
derived subject can satisfy it**, because the subject is not in `app_private.users`
at all, and no bootstrap token carries the other four claims.

The auth service's tokens do carry all five (`services/auth-api/app/claims.py`).
So the two issuers are not interchangeable, and 0013 is what made them different.

Also measured, because the fix depends on it: **nothing in the data plane reads
`scope`.** `grep scope` over migrations 0003, 0004 and 0005 returns nothing —
scopes are the auth service's vocabulary, and the data plane authorizes by
GRANT and by row policy. A read-scoped subject can therefore still exercise the
write RPCs, and a proof that uses one is not measuring scope enforcement by
accident.

## Decision

**A token may name a role. Only the identity registry's issuer may name a
subject.**

1. `bin/dev-token.py` no longer derives or carries a subject, for any of its
   three roles. `development_subject` and the `sub` claim are removed rather
   than made conditional: a flag that sometimes produces a credential the
   deployment refuses is worse than one that never does.
2. Proofs that need an owner identity obtain a token the way production does —
   `POST /auth/login` as a subject registered through
   `app_private.auth_create_user` — through the new `owner_session` fixture.

This is **stricter than what it replaces**, which is the only kind of change to
a passing test the non-negotiables permit, and it is stricter in the direction
the module docstring already argued for: an operator tool loses the ability to
assert an identity, and the only way to hold one is to authenticate as it.

`bin/api.sh` keeps working and reads no owner-scoped rows: with no subject the
hook returns early, `app.user_id` is never set, and the row policies return
nothing. A 200 with an empty array is the honest answer to "what can this
operator read as nobody", and it is what the tool now measures — reachability of
the surface, not the contents of somebody's rows.

## Alternatives rejected

**Seed the derived subject into `app_private.users` at deploy time.** It would
make every deployment carry a subject with no credential, no owner and no expiry,
whose only purpose is to let a local command impersonate a user. That is a
backdoor with a changelog entry.

**Have `dev-token` read the registry and copy the four missing claims.** It would
need a database connection, and it would rebuild exactly the enumeration surface
`auth_claims_are_current` exists to refuse — a caller who can ask "what are
subject X's scopes" can probe every subject's authority. The function returns a
boolean for that reason; a command that assembled the tuple would be the query
it declines to answer, written in Python.

**Exempt tokens with no version claims from the currency check.** The hook would
then accept any token naming any subject as long as it omitted three claims,
which is a bypass available to anyone holding the bootstrap key — and the
bootstrap key exists on every deployment until ADR 0051's retirement. It would
turn 0013 from a boundary into a suggestion.

**Leave the Session 5 proofs minting synthetic subjects and mark them expected
failures.** Ten proofs of the REST surface would then measure nothing, and
`rest_surface` and `api_authorization` would report `failed` forever. The
failures are correct; what they are telling us is that those proofs were written
against a world with no identity registry in it.

## Consequences

Ten Session 5 proofs now exercise the surface as a **registered** subject, which
is what a real caller is. That is a better measurement than the one it replaces:
the row-policy assertions were previously made about an identity nothing in the
deployment had ever heard of, and they now run against one the registry holds,
through the login route, with the hook's currency check in the path.

`DX-API-001`'s broker proof keeps its meaning. `bin/api.sh` still performs a
request, still exits 0, and the token still reaches the child through `execve` —
the five places a credential could leak are unchanged, and what it reads is not
what that requirement is about.

**The bootstrap issuer is now visibly a role-only issuer**, which is a step
toward ADR 0051's retirement rather than a workaround: after the cutover there
will be no key that can sign a token naming a subject except the auth service's.

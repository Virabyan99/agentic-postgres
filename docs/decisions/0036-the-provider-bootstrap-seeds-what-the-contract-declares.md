# 0036 — The provider bootstrap seeds what the contract declares

- **Status:** Accepted
- **Date:** 2026-08-08
- **Session:** 3
- **Affects:** `bin/bootstrap-providers.py`, `schemas/bootstrap-state.schema.json`,
  `tests/contract/test_bootstrap_state.py`, SEC-SECRET-001

## Context

Run 7's first command on the host stopped one step in:

```
materialize-secrets: could not read postgres_init_superuser_password:
GET /api/v3/secrets/raw/APG_POSTGRES_INIT_SUPERUSER_PASSWORD failed with HTTP 404
```

`bin/materialize-secrets.py` reads `secrets.required.yaml` and fetches every
secret required at or before the session it is given. `bin/bootstrap-providers.py`
created exactly one secret, and created it by name:

```python
control.create_secret(
    project_id,
    infisical["environment_slug"],
    infisical["runtime_folder"],
    "APG_SESSION2_SENTINEL",
    secrets.token_hex(32),
)
```

One writer, one hard-coded name; one reader, a declared contract. They agreed
for the length of Session 2, which declared one secret. Session 3 declares three,
and the two that Session 3 added existed nowhere.

The folder had the same shape of defect and it had not bitten yet. Bootstrap
wrote into `host.yaml`'s `infisical.runtime_folder`; materialization reads each
secret's own `provider_path`. Both said `/runtime`, so both were right. Session
3's credentials declare `/database`.

## Decision

**`secrets.required.yaml` is the authority for what bootstrap creates, as it
already was for what materialization fetches.**

`declared_provider_secrets(session)` returns every `required: true` secret at or
before a session. Fresh bootstrap creates each one, in that secret's own
`provider_path`. `add_sentinel` becomes `add_missing_secrets`: a project
bootstrapped in an earlier session converges by acquiring the secrets a later
session declared, rather than by being destroyed and recreated to gain one
value. `--session N` selects the set, defaulting to `CURRENT_SESSION` and
printed on every run.

**An existing secret is never overwritten.** The provider answers a conflict and
that is reported as "already present; not overwritten". Overwriting would rotate
a live credential from a command whose job is to create missing ones — and for
`postgres_init_superuser_password` it would be worse: the image reads that file
only when the data directory is empty, so a new value would change the file and
not the cluster, and materialization would then deliver a password that does not
work against a database it cannot open.

**`managed_resources` stays a closed enum**, with one entry per secret named by
the contract's own `name`. That list is what destruction reads, so it is not
free text. A contract test asserts the enum covers every required secret the
contract declares, which converts "remember to add it" into a property that
fails on the day the secret is declared rather than on the day someone deploys.

## Consequences

Existing state files list `session2_sentinel`, which is already the contract's
name for that secret, so nothing on the host needs rewriting. `alpha-dev` and
`beta-dev` converge by `--apply`, which now sees two missing secrets and creates
them.

Values are `secrets.token_hex(32)` — 32 bytes, hex. Hex rather than URL-safe
base64 because the migration credential is percent-encoded into a connection URL
by the dbmate entrypoint; that encoding is total, but a value that needs none of
it is one less thing that has to be right.

An operator can still create a secret by hand at the provider. Bootstrap adopts
it rather than replacing it, and says so. Recording it as managed is deliberate:
`managed_resources` describes this project's provider resources, not who typed
the value.

## Alternatives considered

**Create the two secrets by hand for this run and record the gap.** It is one
command per secret per project, so Run 8 would need it again for `beta-dev`, and
the obvious way to do it by hand puts a credential in a shell argument — which
every other secret decision in this repository exists to prevent.

**Have `materialize-secrets` create a secret it cannot find.** It runs on every
project start. A missing secret would then be silently invented at 3am, and the
first thing to notice would be a cluster rejecting a password it no longer has.
The command that creates provider resources is the one that runs by hand and
rarely.

**Free text in `managed_resources`.** Destruction reads that list. The enum's
own description already says why.

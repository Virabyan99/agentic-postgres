# Provider bootstrap

How a project acquires its provider resources, and why the script would rather
refuse than adopt.

The authority is `bin/bootstrap-providers.sh` and
`src/agentic_postgres/bootstrap_state.py`. The decision behind it is
[ADR 0011](decisions/0011-provider-bootstrap-state.md).

## The one rule

**Ownership is recorded by ID, never adopted by name.**

If a project or machine identity with the expected name already exists at the
provider and is not in our state file, it is not ours. Adopting it would mean
managing — and eventually, on `--destroy`, deleting — something somebody else
created. So there are exactly two outcomes: create it and record the identifier,
or refuse and say why.

Name equality is not evidence of ownership. A reused slug can resolve to a
different organisation entirely, which is why the host manifest carries both
`organization_id` (the UUID every create call actually takes) and
`organization_slug` (what a human recognises in an error message) rather than
resolving one from the other.

## The three modes

```bash
# Read-only. Contacts the provider, writes nothing, needs no root.
bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml --plan

# Creates what is missing and records the identifiers.
sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml \
     --apply --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential

# Removes, by ID, exactly what the state file says we own.
sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml \
     --destroy --confirm alpha-dev
```

Running `--plan` twice after an `--apply` reports no changes. That is the
property worth having: convergence, not idempotence by accident.

Nothing here accepts a credential as an argument, and no value is ever printed.

`--plan` needs no root in a checkout. On a host it needs `sudo` to read the
project's recorded state, which is root-owned; without it the command says so
and exits `3` rather than treating unreadable state as an absent project (D67).

## The control-plane credential

`--apply` is the only mode that needs it, and it is **not** the per-project
runtime credential under `/etc/agentic-postgres/credentials/<key>/`. That one
belongs to a read-only identity, lives on the host permanently, and is read on
every project start. This one can create projects, machine identities and secret
values — which is why it is passed by path, used once, and does not have to stay
on the host at all.

**Format: two non-empty lines.** Universal Auth client ID first, client secret
second. Nothing else — not JSON, whatever the filename suggests. A file with any
other number of non-empty lines is refused by name and line count, and its
contents are never echoed (that refusal exists because an earlier version passed
the file whole as a bearer token, and `http.client` printed the rejected value).

The path above is the one this host actually uses. Until Run 7 these examples
named `/root/.config/agentic-postgres/infisical.json`, which never existed
anywhere: an operator following the document would have created an empty file at
a path nothing had ever written, and concluded the credential was lost.

```
7f3c1e2a-0000-0000-0000-000000000000
st.abcd1234...
```

Write it root-owned and `0600`, and remove it when the bootstrap is done:

```bash
CRED=/root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo install -m 0600 -o root -g root /dev/null "$CRED"
sudo nano "$CRED"          # two lines, no quotes
# ... run --apply ...
sudo shred -u "$CRED"
```

**`nano` leaves a copy.** Interrupted, it writes the buffer to `<file>.save`
beside the original, and that copy holds the credential at whatever mode nano
chose. Check for one and shred it too:

```bash
sudo find /root/.config/agentic-postgres -name '*.save' -print
```

Removing it is the recommendation rather than an oversight, which is why a later
session may find it absent: it carries organisation-level authority and the host
has no standing need for it between bootstraps. Re-create it from the provider
when the next `--apply` needs one — a new Universal Auth client secret on the
same control-plane identity, shown exactly once.

## What it writes

| Path | Mode | Contents |
|---|---|---|
| `/etc/agentic-postgres/projects/<key>/bootstrap-state.json` | root-only | Provider identifiers, the convergence key, the credential paths |
| `/etc/agentic-postgres/credentials/<key>/infisical-client-id` | `0400 root` | Universal Auth client ID |
| `/etc/agentic-postgres/credentials/<key>/infisical-client-secret` | `0400 root` | Universal Auth client secret |

The state file must name **exactly** the credential paths
`bootstrap_state.credential_paths()` derives for its own project key. A state
file naming another project's directory is the cross-project escape
`validate_state` exists to refuse.

`needs_credential_repair` deliberately treats an *unreadable* path as intact.
Reporting a repair on a path it could not read would send an operator to
re-issue a credential that is present and healthy — which is the credential
churn the function exists to prevent. See
[ADR 0024](decisions/0024-a-contract-test-asserted-the-absence-of-a-real-host-path.md)
for how a test of that behaviour went wrong by asserting about `/etc` instead of
about the logic.

## Convergence is keyed narrowly

The state file records `provider_inputs_sha256`, computed over **exactly the
manifest fields that can change a provider resource** — not over the whole
manifest. A digest over everything would force provider churn on every unrelated
edit: change a comment in `project.yaml`, and the next `--apply` would decide
the identity needs replacing.

## Stop condition: partial state

**A client secret was created but the local write failed, or the saved
identifiers disagree with the provider.** Halt. Revoke the orphan **by ID**.
Never adopt by name, and never guess which of two similarly-named identities is
yours.

## Known deviation

The Infisical control-plane identity currently holds **organisation admin**. It
needs enough authority to create projects and machine identities, and the
provider's role model did not offer a narrower fit at bootstrap time. This is
recorded rather than absorbed: it is the largest single piece of standing
authority in the deployment, and narrowing it is open work.

Secret generations also accumulate on every deploy with no pruning. Nothing
reads a superseded generation — the active one is named by
`active-secret-generation.json` — but the directory grows without bound.

## See also

- [Secret handling](secret-handling.md) — what happens to the credential this
  script writes
- [Host baseline](host-baseline.md)
- [ADR 0010 — secrets are individual files in immutable generations](decisions/0010-secret-materialization.md)
- [ADR 0011 — provider ownership is recorded by ID, and convergence is keyed narrowly](decisions/0011-provider-bootstrap-state.md)
- [ADR 0017 — a stub that becomes real stops returning 10](decisions/0017-stub-lifecycle.md)

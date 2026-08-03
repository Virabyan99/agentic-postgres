# 0011 — Provider ownership is recorded by ID, and convergence is keyed narrowly

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** `DEP-BOOT-001`, `DEP-BOOT-002`, `SEC-SECRET-003`, `DEP-ISO-002`

## Context

`bin/bootstrap-providers.sh` is the only command in this repository permitted to
create, update, revoke or delete resources in an external control plane. It is
therefore the only command that can do damage nothing in the repository can
undo, and the damage is not hypothetical: two projects share one Infisical
organization, and the resources they own are distinguished by name.

Three specific failures have to be designed out.

**Adoption by name.** A second `--apply` finds a project called `alpha-dev`
already exists. Adopting it because the name matches means one project can be
made to manage — and destroy — another project's resources by choosing a name.
Provider names are not unique identifiers and carry no ownership claim.

**Convergence churn.** If convergence is keyed on the project manifest's digest,
every ordinary edit — a domain, a row limit, a pool size — makes `--plan` report
provider drift. None of those change a single provider resource. A plan full of
changes an operator cannot account for is a plan nobody reads, and `--plan`'s
entire value is that a converged second run says nothing.

**The half-created credential.** Bootstrap creates a Universal Auth client
secret and the local write fails. State records the secret ID; the file is
absent. On the next `--apply` the naive behaviours are both wrong: creating a
second secret leaves the first live and unaccounted for, and revoking the first
before a replacement is validated leaves the project unable to authenticate at
all.

## Decision

**Ownership is an ID.** `bootstrap-state.json` records
`infisical_project_id`, `runtime_identity_id`, `runtime_client_id` and
`active_client_secret_id`. Destruction and revocation act on those. A resource
with no recorded ID is not managed and is not destroyed — validation refuses a
state document that claims to manage a client secret without recording its ID,
because the only remaining way to revoke it would be a name lookup.

**Adoption requires a matching saved ID and expected ownership metadata.** Name
equality is explicitly insufficient. Ambiguous or conflicting external state is
an error requiring operator resolution, not an invitation to guess.

**Convergence is keyed by `provider_inputs_sha256`,** computed over an explicit,
short list of provider-relevant fields — `project.slug`, `project.environment`,
and the four `infisical.*` coordinates from `host.yaml`. It is a digest of a
selected field map in canonical JSON, not of the manifests, so adding a field to
the convergence key is a visible source change rather than a side effect of
editing a manifest. `project_manifest_sha256` is still recorded, for evidence,
and is deliberately not the convergence key.

**A missing credential file is a repair condition, not an apply.** Ordinary
`--apply` performs no mutation and directs the operator to
`--repair-runtime-credential`, which creates a new client secret, writes it
atomically, validates login *and* exact-path read access, and only then revokes
the previously recorded secret ID. The order is the whole control: at no point
does the project have zero working credentials, and at no point is a live
credential left unrecorded.

**Credential paths are recorded, and they are derived from the project key.**
`credential_files` holds `/etc/agentic-postgres/credentials/{project_key}/…`, so
the path itself carries the project scope, and a state file naming another
project's credential directory is detectable by comparison — which validation
does. This is runbook §15's "Project B is configured to use Project A's
credential directory" made into a check.

**The path fields are named `client_id_path` and `client_secret_path`, not
`client_id` and `client_secret`.** The runbook's Phase 4 fragment uses the bare
names, and a key literally named `client_secret` is rejected by the inherited
sensitive-key rule of [0008](0008-sensitive-key-policy.md). That rejection is
correct — the rule reads key names and cannot tell that this one holds a
filename — so the field is renamed for what it contains rather than the rule
being weakened. Recorded as divergence D28 in the Session 2 plan.

**State contains no secret value.** `runtime_client_id` is a username.
`active_client_secret_id` is the provider's identifier *for* a secret, and
survives the sensitive-key rule on its own merits because it ends in `_id` under
terminal-token matching.

## Consequences

Makes easy:

- `--plan` after `--apply` reports nothing, which is what makes `DEP-BOOT-002`
  testable rather than a claim.
- Destruction is precise: it names IDs this project recorded, so it cannot reach
  a resource it did not create.
- A domain change costs no provider work, so operators can edit manifests
  without wondering what will churn.

Makes hard:

- State and the provider can genuinely disagree — a resource deleted in the
  provider console, an ID that no longer resolves. The command stops and
  requires operator resolution rather than reconciling. That is the correct
  behaviour and it is also the annoying one.
- Adding a provider-relevant field means editing `PROVIDER_RELEVANT_FIELDS`
  deliberately. Intended: it is an assertion that changing that field must cause
  convergence work.
- `--repair-runtime-credential` is a distinct operator verb that has to be
  documented and remembered. The alternative is a silent leak.

## Alternatives considered

**Adopt by name when the name matches.** Rejected: it makes ownership claimable
by anyone who can choose a project name, in an organization two projects share.

**Key convergence on the whole project manifest.** Rejected: every ordinary edit
becomes provider drift, and the plan output stops carrying information.

**Recreate a missing client secret during ordinary `--apply`.** Rejected: it
leaves the previous secret live and unrecorded. A credential nobody knows exists
is worse than a command that refuses.

**Revoke first, then create.** Rejected: a failure between the two leaves the
project with no working credential and no automated way back.

**Store provider resource identity only in the provider.** Rejected: it makes
every operation a search, and a search returns matches rather than ownership.

# 0257 — Slots, the region, and one Infisical identity per project

- **Status:** Accepted
- **Date:** 2026-10-07
- **Session:** 38, Run 1 (D2145, D2146, D2148–D2150, D2158, D2161, D2180)
- **Affects:** `schemas/host.schema.json` (schema 4: `region`, `slots`, Run 3),
  `src/agentic_postgres/host_config.py` (`region()`, `declared_slots()`),
  `bin/slot.sh|py` and `src/agentic_postgres/slot.py` (new, Run 5),
  `bin/project-retire.sh --defer-provider` and `src/agentic_postgres/retirement.py`
  (Run 5), outputs schema 21's `region` (Run 3). Requirements
  `LIFE-SLOT-001`, `LIFE-REGION-001`, `LIFE-DELETE-001`.
- **Related:** ADR 0110 (the provider half is console work), ADR 0187 (what
  retirement never touches), ADR 0002 (identities derived once), ADR 0221/0222
  (the host declares itself; admission), ADR 0256 (the reconciler).

## Context

A managed project needs, before a customer can create it: an Infisical
project and machine identity, two R2 buckets and their tokens, a B2 mirror
bucket and key, a DNS record and the secrets materialized. The bootstrap path
that makes them (`bootstrap-providers --apply`) needs the Infisical
organisation administrator's credential on disk, and the buckets, tokens and
DNS record are console work (ADR 0110). The reconciler must hold no
provider-administering credential (Session 38's *Must not*). So the provider
half cannot happen at creation time.

The host is a CX23 (3,814 MiB, no swap): 1,624 MiB available with three
projects. The operator decided on 2026-10-07 to stay on it with ONE customer
slot, the rescale or a move owed before Session 41 (D2145); to upgrade the
Infisical plan, whose four free machine identities are all used (D2146); and
to make an explicit grey A record per slot (D2148).

## Decision

1. **A slot is a project the operator prepared in advance and no customer has
   yet.** Declared in `host.yaml` schema 4 under `slots` (`declared: [{key,
   domain}]` and `defaults`: the provider facts every slot manifest copies —
   no secret); its manifest written by `sudo bin/slot.sh prepare` to
   `/etc/agentic-postgres/slots/<key>/manifest.yaml` (0600) at profile `small`;
   its providers made on a sheet by the existing `bootstrap-providers
   --plan/--apply`, the credential placed and shredded by the operator; its
   secrets materialized. **Creation consumes nothing at a provider**, so
   *"No resources were created"* is true by construction (D2150).
2. **No state in `host.yaml`.** A slot's state is DERIVED by `slot.state()`
   from four readings, each with three outcomes — declared; prepared (the
   manifest, the bootstrap state, an active secret generation); occupied (a
   deployed document, or the reconciler's allocation); consumed (the
   tombstone) — plus DNS: `declared`, `prepared`, `ready` (prepared and the A
   record reads the host's address with no AAAA), `allocated`, `quarantined`,
   `consumed`, `undetermined`. `slot.sh status` exits 6 on any undetermined.
   A field root rewrote in an operator's file would be a second source of
   truth (D2149).
3. **A slot is single-use.** Deletion writes
   `/etc/agentic-postgres/slots/<key>/consumed` (0600), which **no command
   removes**; `consumed` and `quarantined` are never `ready`.
4. **Deletion defers the provider half** (D2158). `project-retire.sh
   --defer-provider` runs every retirement step but `provider-destroy`,
   moves `bootstrap-state.json` to the slot's directory before the state
   directory is removed, and removes the local credential files;
   `--defer-provider` and `--operator-credential-file` are mutually exclusive.
   **The operator revokes later** with `slot.sh revoke --slot KEY
   --operator-credential-file F --confirm KEY`, which runs `bootstrap-providers
   --destroy` against the kept state of a CONSUMED slot. The Infisical project,
   the buckets, the backup repository and the DNS record stay (ADR 0187).
5. **One Infisical identity per project, on the upgraded plan** (D2146). A
   shared runtime identity would let one customer's secrets be read with
   another's credential; a second Infisical organisation is code written for a
   billing problem. Provisioning failing on the identity is a stop, never
   retried before the output is read (D1046).
6. **DNS is an explicit grey A record per slot, made by hand** (D2148):
   `slot1.agenticpostgresql.com → 62.238.99.122`, DNS only, no AAAA; the
   proxied wildcard is untouched. `slot.sh status` reads it from the host with
   `dig @1.1.1.1`; no `dig` is `could not determine`.
7. **One region, declared by the operator** (D2161). Host schema 4 requires
   `region: {id, display_name, provider, location}`, the operator's values read
   from the provider's console (`eu-hel-1`, "Helsinki, Finland", Hetzner,
   `hel1`); outputs schema 21 carries it in every deployed document;
   `migrate_v20_to_v21` writes `region: null` for an archived document, an
   unknown every reader that needs it refuses. **No `regions` table**: one
   host, one region, nobody else writes it.
8. **Slot keys are `slot<n>-prod`** (D2180). The first is `slot1-prod`, domain
   `slot1.agenticpostgresql.com`, buckets `apg-slot1-prod` and
   `apg-slot1-prod-backup`, Infisical project `slot1-prod`, identity
   `slot1-prod-runtime`. **The customer's project name is a display name in
   `control_projects.display_name`**, never a key, a role or a host — a key the
   customer chose would be a customer-controlled input to every derived
   identity.

## Alternatives rejected

- **`slot.sh provision` wrapping the console half.** It cannot do the console
  half; a wrapper pretending to would be the first fake-complete command.
- **Slot state as a field in `host.yaml`.** Root writing an operator file at
  runtime; two copies of `host.yaml` are already read (D2020).
- **The reconciler destroying the provider resources at deletion.** Needs the
  organisation administrator's credential in a standing root process.
- **A shared runtime identity, or a second Infisical organisation.** Above.
- **A proxied wildcard for slots.** HTTP-01 needs a grey record at the host
  (D2083).

## Consequences

- Slots are a stock of ONE on this host; a second needs the rescale or a move.
- A slot's provider resources and backup repository outlive it; no
  deletion-policy window exists (D2181).
- `quarantined` has no clearing command: an interrupted creation is retired
  by the operator by hand and then marked consumed.

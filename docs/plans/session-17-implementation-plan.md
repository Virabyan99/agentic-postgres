# Session 17 — Multi-project operation: the fleet inventory, project lifecycle, and retirement

```
CURRENT_SESSION **16** -> 17 in Run 6, ALL-OR-NOTHING (D690).
template_version **0.5.0** -> 0.6.0 at the same bump (ADR 0162: a manifest
                bump and a new outputs version are each a minor; this takes one).
migrations      30 released, 30 applied on both clusters. **Session 17 adds
                NONE.** Everything it builds is host state, a manifest field and
                a verb; nothing here changes the cluster (§1, D949).
outputs schema  v14 -> **v15** in Run 3 (`project.lifecycle`), the first move
                since Session 14 Run 7.
project manifest schema 2 -> **3** in Run 3. v1 and v2 stay valid and mean
                what they always meant (D949).
divergences     Next free **D944**. This plan opens §1 at D944 with fifteen
                planning-time rows.
ADRs            184 released. Next free **0185**.
claims          93: 85 passed, 8 not_run, 0 failed. Session 17 adds seven
                requirements and four claims (§2) and closes ONE of the eight
                inherited not_run by declaration: `project_removal` (D953).
host            62.238.99.122, Session 16 on both projects at `8237c77`,
                checkout `50d700d`. 3814 MB, NO SWAP, 1949 MB available and
                25 GB free at planning time. Kernel restart pending.
                **NO BACKUP TIMER IS INSTALLED** (D944).
```

**This is the fourth Stage 2 session and the stage plan calls it one session
made of three specification sessions** (`stage-2-plan.md` §3: 17 + 21). §1 shows
that two of the brief's five nouns name things the product contract forbids or
the tree cannot express, that one names a data-copy path that does not exist,
and that the one Stage 1 claim it closes needs a **third project** to exist and
then to stop existing. Seven runs, one of them the trip.

---

## 0. Where the session starts

`docs/plans/stage-2-plan.md` §0 and §3 own this, and its §5 *Session 17* entry
is the brief. Session 16 closed at `7282cc5` with the host at `50d700d`, the
deployed release `8237c77`, and `evidence/session-16.json` reporting 85 passed /
8 not_run / 0 failed of 93. Both host manifests are still project schema
version 1 and the host's `capabilities.yaml` schema version 1, neither of which
decides anything the plane serves (D930).

**The brief was checked against the tree before this plan was costed** (D812,
D934). Two of its statements are exactly right and are not re-litigated: every
field the registry is asked to record **is** already published per project in
the deployed document (D709), and the removal surface **is** `project-runtime.sh
down` plus `bootstrap-providers.sh --destroy --confirm KEY` and nothing else
(D691). What the brief got wrong, and what the deployment turned out to be
doing, is §1.

**Read `docs/scope-closure.md` §2 before anything else, and then read D954
below**, because §2 and the README both describe the position of two Session 12
claims wrongly, in the direction that makes work look undone.

---

## 1. The divergence table

Six columns, the house shape. **Every row is a fact measured against the tree at
`7282cc5` or against the deployment on 2026-09-04**, not a prediction.

**Next free number after this table is D964.** D944–D958 were written at
planning; D959 and D960 are Run 1's; D961–D963 are Run 2's.

| # | The plan says | The repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D944** | The stage brief: the inventory view shows *"health, backups and agent-denial rates"*, and `docs/backup-operations.md` step 5: *"Enable the timers, once the first backup exists."* Read as: backups are scheduled and the inventory reports how they are going. | **No scheduled backup has ever run on the deployment, because the four backup units are not installed.** `systemctl list-unit-files 'agentic-postgres-*'` on the host lists **three** unit files — `docker-firewall`, `edge`, `project@` — and `/etc/systemd/system` holds the same three. `install_units` runs only from `provision-host.sh --apply`, which last ran when the host was provisioned (2026-08-04 to 08-07); Session 10 Run 9 widened its glob to `*.timer` (D522) and **nothing has run it since**. No deploy installs a unit. `systemctl list-timers --all` shows eleven timers, none of them this product's. Both deployed documents say `backup_state.status: ready`; alpha's `last_full_backup_at` is **2026-08-28**, beta's 2026-09-03 — each a manual full taken on a trip. WAL archiving works (267 and 257 archived). | **Run 5 builds `bin/backup.sh schedule status\|enable\|disable`**, `enable` refusing when the unit files are absent and naming the provisioning command; **the trip installs the units and enables the timers on both permanent projects** (§5 Run 7, step 3), and the inventory reports a project whose timers are not enabled as **`unscheduled`** rather than reading `backup_state.status`. `FLEET-BACKUP-001` registers it (§2). | **D522 one layer up, again.** Session 10 found a schedule written and not installed and repaired the installer; `test_backup_schedule.py` proves the glob *would* pick the timers up. Nothing asked whether the installer had *run* on the one host that matters — question 2, with the same answer it has given five times. And the signal that would have said so, `backup_state.status`, is a deploy-time snapshot (D700) that reads `ready` for a project whose newest full backup is a week old. **The brief's "backups" column, built over the deployed document, would have shown two green rows.** | — |
| **D945** | The stage brief: *"a cross-project inventory view."* | **`docs/product-contract.md` §5 lists, under *Non-goals* — "not deferred, outside the product": *"A shared, multi-tenant control plane, or any cross-project shared catalog"* and *"Cross-project reporting or aggregation."*** Both sentences are in the frozen contract, and `test_repository_contract.py` tracks the file. | **The inventory is an operator's read over files already on the host's disk, run as root at a TTY, holding nothing, serving nothing, and read by nothing** — `apg-diag containers`' existing loop over `/etc/agentic-postgres/projects/*/` with more columns. **ADR 0185** amends §5's wording to say what the non-goal protects: nothing a project's users or agents can reach may see another project. Run 1. | A non-goal a session steps over silently stops being a non-goal. The stage plan's own stop condition (§9: *"the registry needs authority it is forbidden"*) draws the same line from the other side; this row draws it in the contract. **What survives the ADR unchanged**: no route, no service, no credential, no daemon, no file another command reads. | 0185 |
| **D946** | *"Create a thin project registry… It may begin as a file-based registry."* | **"Registry" already names four things in this tree**: the acceptance registry (`tests/acceptance-registry.yaml`), the identity registry (migration 0011, ADR 0080), the scope registry (`scope_registry.py`, ADR 0079), and the port registry (`database-ports.py load_registry`, `/etc/agentic-postgres/database-port-allocations.json`, ADR 0042). | **The artefact is the `fleet` inventory** — `bin/fleet.sh`, `src/agentic_postgres/fleet.py` — and the requirement family is `FLEET-*` as the brief proposes. The word "registry" is not used for it anywhere. | Nothing indexes the ~940 measured facts by subject; the pointer is a `grep`, and a fifth thing called "registry" is a grep that returns four wrong answers first. | — |
| **D947** | The registry is *"thin, file-based, non-authoritative"*, with *"can be deleted and reconstructed"* as an exit criterion. | **Every field is published per project and NOTHING reads more than one project's document at once**, except `apg-diag containers` (a `for directory in "${PROJECT_ROOT}"/*/` loop, root, read-only, containers only). `doctor.sh` is per-project and **text-only** — no `--json`; `diagnosis.report` renders prose. `upgrade.sh check\|plan\|verify` is per-project. | **The inventory writes nothing**, so "deleted and reconstructed" is vacuous and is asserted as *writes nothing* (`FLEET-INV-002`). **Run 1 gives `doctor.py` a `--json` output** and Run 2 composes the inventory from it: live verdicts from doctor's probes, identity and release from the document, nothing cached. | D709 said the registry is *"an aggregation over documents that already exist"* and priced it as free. The aggregation is free; **the machine-readable per-project read it aggregates does not exist**, and building the inventory over doctor's *text* would be a second parser of one report — D486's shape. | 0158 |
| **D948** | *"…agent-denial rates."* | **The rate exists and is deliberately not an alarm.** `mcp_metrics.py` exposes `agent_tool_calls_total{outcome, tool}` (`METRIC_LABELS = ("outcome", "tool")`) on the `/metrics` route, which is behind the project's metrics Basic Auth credential (`OPS-METRIC-001`); the deployed alert rules say, at `ApgAgentPlaneFailing`: *"`failed` and not `refused`: a refusal is the boundary working."* A registry that scraped the route would hold the metrics credential — the brief's own *Must not*. | **Denials are read from `app_private.agent_audit` over the container socket as root**, the route `doctor.py probe_database` already takes, and reported as **counts by `denial_reason` over a window**, never as a rate the alert plane has decided means nothing. No credential is held. | The number the brief asks for is one Session 16 built a taxonomy for (ADR 0178): *which boundary refused* is the operator's question, and a rate erases it. And the metrics route is the wrong door for a host-local read — ADR 0065's route rule in the other direction: reaching a value by a route the operator would never take proves the route, not the value. | 0178 |
| **D949** | *"Ephemeral/preview projects with TTL metadata."* | **The manifest cannot say that a project expires.** `project.environment` is a 2–16 character lowercase string; `naming.project_key` is `{slug}-{environment}`; a preview project is a project whose environment differs and nothing more. Project schema **v2 is one run old** (Run 8, ADR 0183), both host manifests are **v1**, and the `--migrate-manifest` decision is open (D930). `SUPPORTED_PROJECT_SCHEMA_VERSIONS` is `{1, 2}`. | **Project manifest schema v3: `project.lifecycle: {kind: permanent \| ephemeral, expires_at}`**, `kind` required at v3, `expires_at` required iff `ephemeral`, and **absent means `permanent`** — which is what every v1 and v2 manifest has always meant, so nothing existing changes meaning and no manifest needs migrating. The deployed document publishes it at outputs **v15**. ADR 0186, Run 3. | Three manifest versions in two sessions is the cost of adding a field at the version that introduces it (ADR 0177's rule, applied to the project manifest), and it is smaller than a `lifecycle` block whose absence has to be guessed at. **D930 does not move**: a v1 host manifest compiles the lock it always did and renders as a permanent project. | 0186 |
| **D950** | *"…masking hooks…"* | **Nothing seeds one project from another's data.** `restore-test.py` restores a backup into a **drill** volume derived through `naming`, refuses any plan that could reach the live volume (ADR 0151 §5), and tears itself down; the product contract's §5 lists *"database branching or copy-on-write forks"* as a non-goal. An ephemeral project starts as every project starts: an empty cluster, migrated. **There is nothing to mask.** | **Not built, not registered**, and recorded here so no run discovers it. A preview seeded from a permanent project's backup is Session 18's restore-to-new-host shape plus a decision the non-goal forbids; if it is ever wanted it arrives with its own ADR and its masking in the same run. | D864's shape one more time: a brief that says *"add X to Y"* prices new construction as a widening. Here Y is a copy path, and there is none. | — |
| **D951** | *"…automatic cleanup…"* and the specification's *"expiration cleanup cannot affect permanent projects."* | **Every removal path needs root at a TTY** — `project-runtime.sh down` (root), `bootstrap-providers.sh --destroy --confirm KEY --operator-credential-file` (root and the operator's provider token) — and the stage plan's D713 names a cleanup that expires into destroying `pgbackrest_repo_cipher_pass` a *data-loss timer*. Measured, what a retirement has to reach **on the host**: ten containers, three networks (`edge`, `internal`, `backup`), two volumes (postgres, store), one enabled `agentic-postgres-project@<key>.service` instance, two timers once D944 is repaired, `/etc/agentic-postgres/projects/<key>` (root, 0700), `/var/lib/agentic-postgres/secrets/<key>`, `/var/lib/agentic-postgres/rendered/<key>`, the edge middleware file `EDGE_DYNAMIC_DIR/<middleware_file_name(key)>`, and the port allocation. **Off the host**: the Infisical identity, client secret and folder (`--destroy` reaches these), two R2 buckets and two API tokens (created by hand — ADR 0110: *nothing in this repository creates a bucket*, so nothing here deletes one), one DNS record, and a certificate in `acme.json`. | **Expiry is READ, never acted on.** `bin/project-retire.sh` is a verb: root, `--confirm KEY`, a `--plan` that prints every resource by name and mutates nothing, refuses a `permanent` project without `--permanent`, refuses an unexpired ephemeral project without `--before-expiry`, and removes volumes only with `--destroy-data`. The inventory reports an ephemeral project past `expires_at` as **`expired`**, and that is the whole automation. **No unit, timer or cron in the release names `retire`** (`FLEET-EXPIRE-001`). ADR 0187, Run 4. | The hard half of an ephemeral project — isolation — is the product; what is missing is a lifecycle, and a lifecycle whose last step is a timer is a data-loss timer with a schedule. **A retirement is a human reading a plan and typing the key twice.** | 0187 |
| **D952** | *"CI integration"* — the specification's *"CI creates, tests and destroys an isolated project automatically."* | **CI has no host and may not have one**: transport is `git bundle` + `scp` and no GitHub credential exists on the VPS, by decision. CI already renders `fixture-alpha-dev` with `--render-only`, resolves its Compose model, and the render-isolation proofs create and delete `fixture-*` projects — **the render-plane lifecycle exists and runs on every push**. | **CI's integration is the render plane plus `project-retire.sh --plan` run against a rendered fixture**; the deployed lifecycle is proved on the host, in the trip, once, on a third project (D953). No CI job deploys anything. | A CI job that deployed to the one host would be the credential-on-the-VPS this repository refuses, and an ephemeral project in a fixture is what `.generated/fixture-*` has been since Session 12. | — |
| **D953** | *"Closes `project_removal`."* | **`DEP-REMOVE-001`'s live proof needs a project actually removed, and only two exist.** `test_removing_one_project_leaves_the_other_whole` reads `APG_REMOVED_PROJECT_FILE` — the removed key and its resource names, **captured before the removal** — and asserts the survivor serves and holds rows while nothing named for the removed key runs. Removing alpha or beta breaks every two-project proof (`DEP-ISO-001`'s 179 leaves among them). The claim's session is 12 and stays 12 (D696). | **The trip creates a THIRD project, ephemeral by manifest, deploys it, proves the inventory sees three, retires it, and the retirement record is the declaration.** `project_removal` closes on Session 17's gate through the proof that already exists — no claim moves, no second proof. **Cost, stated**: an Infisical bootstrap (`bootstrap-providers.sh --apply`), two R2 buckets and two tokens **by hand**, one grey-cloud DNS record, one ACME issuance under the 5/hour cap, and memory: `free -m` at planning time shows 1949 MB available with two projects on a swapless host. **Run 1 measures whether a third fits**, by ADR 0165's method (`anon`, per container, summed), before anything is provisioned. | This is the one Stage 1 claim whose event nobody has been able to arrange, and Session 17 is the session that builds the thing the event needs. Arranging it inside the trip is D211's shape stated in advance: the retire verb's first host execution is also its first proof. | — |
| **D954** | `README.md`, *What is intentionally unavailable*: *"Session 12 owns the rest. Removing a project is not built … `DEP-REMOVE-001`, and the two-project runtime isolation matrix is `DEP-ISO-001`. Neither is claimed."* `docs/scope-closure.md` §2: *"`DEP-ISO-001` and `DEP-REMOVE-001` await one host trip."* | **`isolation_matrix` has been `passed` since Session 12's trip** and is `passed` in `evidence/session-16.json`; `project_removal` is `not_run`. The README and the ledger describe both as unclaimed and both as waiting. | **Corrected in Run 1's documentation commit**: the README names the one that is open and its reason; §2 of the ledger gets the D860 treatment for the removal claim. | D860's shape: the ledger describing a claim's position wrongly, and here in the direction that makes finished work look unfinished — which is the direction nobody chases. The documented-path guard (D693) reads commands and session numbers, not prose truth. | — |
| **D955** | Stage plan D707: *"The genuinely new verbs are `upgrade check\|plan\|verify` and `project retire`"*, folded into Session 13. | **Session 13 built the first and not the second.** `bin/upgrade.sh` exists with the three verbs; no `retire` exists in `bin/`, and the Session 13 plan does not contain the word. | The retire verb is Session 17's, as the stage plan's own §5 says. Recorded because a reader of D707 would look for it in 13. | A stage-level row priced a verb into one session and the session plan dropped it without a row of its own — the sixth *mischaracterised* ledger entry this stage. | — |
| **D956** | A retirement is "down, then destroy." | **`database-ports.py release --instance-uuid --project-key` exists and has never run on a host**, and ADR 0042 keys an allocation by **the identity the volume carries** (`database.observed.instance_uuid` in the deployed document). After the volume is gone nothing can name the allocation. | **The retire verb reads the deployed document and the instance uuid FIRST and releases the ports BEFORE `--destroy-data` removes a volume**, and its `--plan` prints the uuid it will release under. The order is a contract test. | An ordering that is right by accident is D183's family. The verb that could strand every future allocation on this host is the one being written, and the trap is visible at planning time. | 0042 |
| **D957** | `docs/backup-operations.md`: *"`pgbackrest_repo_cipher_pass` … is in `managed_resources`, so `--destroy` may remove it — correct for a project being torn down, and catastrophic for one that is not."* CLAUDE.md §9 carries the same warning. | **`--destroy` does not remove it.** `bootstrap-providers.py destroy()` revokes the runtime identity, unlinks the two credential files and the state file, and prints *"project … was left in place. Delete it in the Infisical console if you also want its secrets gone."* Every secret, the cipher pass included, survives a `--destroy`. The licence in `managed_resources` exists; nothing exercises it. | **ADR 0187 makes the current behaviour the decision**: a retirement never deletes a backup repository, a bucket, or the cipher pass; the retirement record names the bucket and the Infisical project that still hold them, and their removal is a console action the operator records afterwards. `--destroy-data` destroys volumes and nothing off the host. | The warning describes a capability the verb does not have, which is the reassuring direction (D930): everybody was careful around a step that could not happen, and nobody noticed that a destroyed project's backups stay readable to anyone holding the console. Both facts belong in the ADR. | 0187 |
| **D958** | Session 10's brief: *"Scheduled full and incremental backups."* | **No requirement registers the schedule.** The `REC-*` family is `PITR`, `SAFE`, `SMOKE`, `EVID`, `WAL`; the four units and D522's glob are proved by `test_backup_schedule.py` under no requirement id and no claim — which is why nothing ever asked whether they were installed (D944). | `FLEET-BACKUP-001` registers the schedule with a live half that reads `systemctl is-enabled` on the host for every permanent project. | D697's rule, *every registered requirement belongs to a claim*, has a converse this row is: **a proof under no requirement is reported by nothing**, and a schedule reported by nothing was never enabled. | — |
| **D959** | This plan's §0 and D953: *"1949 MB available with two projects on a swapless host. Run 1 measures whether a third fits."* | **A third project fits, measured by ADR 0165's method as `op` with no root** (D765's walk over `/sys/fs/cgroup/system.slice/docker-*.scope/memory.stat`, labelled from each scope's first pid). Anonymous memory on 2026-09-04: **alpha-dev 348 MB, beta-dev 351 MB, the shared edge 31 MB, total 730 MB** across 22 scopes; `free -m` reports 1832 MB used and **1982 MB available** of 3814. The largest single holders are the two `uvicorn` services per project (66–94 MB each) and the collector (53–66 MB); PostgreSQL holds 18–19 MB anon plus ~19 MB shmem against its 768 MB cap. A third project at the measured ~350 MB leaves ~1.6 GB available before page cache. | **The trip creates the third project.** §9's first stop condition does not apply. The number is recorded here rather than in a memory file because it is a fact about this deployment on this day. | D767's point holds one session later: the caps in aggregate exceed the machine and nothing holds them, so `anon` is the figure and the caps are not a budget. What bounds the third project is what it *holds*, and that is ~350 MB. | 0165 |
| **D960** | CLAUDE.md §2 and D766: *"18 containers, not 16"*. | **The machine runs 22.** Session 14 added the collector and the store to every project — `apg-diag containers` lists 10 per project, and the cgroup walk finds 20 project scopes plus `traefik` and `haproxy`. The handoff carried the Session 14 planning-time count for three sessions. | The handoff's number is corrected; `apg-diag containers` was right all along and needs no change. | The same shape as D766 in the other direction: a count written down once and read as current. A count in a handoff is a measurement with a date, and this one had lost its date. | — |
| **D961** | This plan's Run 2: *"runs doctor's probes in-process per project."* | **In-process would make the inventory a second caller of every probe's internals** -- `probe_containers(key)`, `probe_repository(key, root)`, the document loader -- and Run 1 built `doctor.py --json` precisely so a consumer could compose the doctor's *document* instead of its functions (D947: "composes rather than parses"). | **`bin/fleet.py` runs `bin/doctor.py --project KEY --json --root ROOT` as a subprocess with the same interpreter and reads the document.** What the inventory reports as health is byte-for-byte what the operator's own command prints, and the doctor's redaction (ADR 0159) is inherited whole rather than re-asserted. `doctor.py` gained `--root` so the fixture-root contract test drives the real pipeline. | A seam built in Run 1 and bypassed in Run 2 would have been a declared reader with no reader (D816's shape), and two callers of one probe set is question 5 waiting to happen. The cost is one process per project, which on a host of three is nothing. | — |
| **D962** | `FLEET-BACKUP-001`: the inventory *"reports a project whose timers are not enabled as `unscheduled`"* -- one state for "not enabled". | **`systemctl is-enabled` distinguishes three states, measured on the host as `op`:** an instance of a template that is **not installed** answers `not-found` and exits **4**; an instance of an installed template that nobody enabled answers `disabled` and exits **1**; an enabled instance answers `enabled` and exits **0**. `systemctl show` on the absent instance reports `LoadState=not-found` with an empty `UnitFileState`. | **`fleet.unit_state` classifies four ways** -- `enabled`, `disabled`, `absent`, `unknown` -- and `schedule` folds the first three to `scheduled`/`unscheduled` while an `unknown` timer makes the schedule `unknown` (not measured is not measured absent, ADR 0158). `absent` is kept apart from `disabled` because the repairs differ: `provision-host.sh --apply` installs, `enable` enables. | The deployment is in the `absent` state today (D944), and an inventory that folded it into `disabled` would send an operator to `systemctl enable`, which fails on a unit that does not exist. The vocabulary is measured, not typed (D674). | — |
| **D963** | Run 2's targeted modules were green and the commit was pushed as `3b1ac58`. | **CI was red on both jobs, one cause**: `test_no_module_is_imported_only_by_its_own_tests` reported `fleet` *"imported by nothing outside its own tests"*. The scan discounted any import whose name equalled the importing **file's** stem — a rule written so a package module importing itself is not its own caller — and applied it to every file under `bin/` too, so `bin/fleet.py`'s `from agentic_postgres import fleet` was discounted as a self-import. Every earlier `bin/` script happened to differ in stem from the module it drives (`doctor.py`/`diagnosis`, `upgrade.py`/`upgrade_plan`, `migrate.py`/`migrations`), so the rule had never been exercised on the case it gets wrong. | **The self-import exclusion is scoped to sources inside the package**, and a control asserts both directions: a `bin/` script sharing a module's stem is a caller, a package module importing itself is not. Repaired as the scan, not by renaming the command — a guard that decides a real caller is not one is wrong about the boundary it guards, and renaming would have left it wrong for the next same-stem pair. | The module the guard was written to catch (`edge_credentials`, D204) had no caller; this one had exactly one and the guard could not see it. A false positive in a guard over a real boundary is repaired in the guard when the guard's *rule* is wrong, and moved in the code when only the *name* collides (D464) — this is the first kind. **And the module was not in Run 2's targeted list**, which is what CI is for. | — |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

Decided now, because Run 6's bump is all-or-nothing (D690) and there are no
`future` placeholders — every requirement arrives with its proofs in the commit
that moves the constant. `ID_PATTERN` gains `FLEET`; the product contract's
generated table follows.

| Requirement | P | What it asserts |
|---|---|---|
| `FLEET-INV-001` | P0 | `bin/fleet.sh` reports every deployed project on the host — identity (key, domain, environment, lifecycle), release (`source_commit`, `deployed_through_session`, `template_version`), health (doctor's live verdicts, not the document's), backup (timer state and full-backup age, never `backup_state.status`), and agent denials (counts by `denial_reason` over a window, from the audit table over the socket). It holds no credential, prints nothing `test_doctor_redaction` forbids, and names each project's values under its own key only |
| `FLEET-INV-002` | P0 | The inventory **writes nothing** — no file under `/etc`, `/var/lib`, the checkout or `$HOME` changes when it runs, measured by mtime — and **nothing reads it**: no service, unit, route or command in the release names a fleet artefact |
| `FLEET-LIFE-001` | P0 | A project manifest declares its lifecycle at schema v3; a v1 or v2 manifest renders as `permanent`; an ephemeral manifest without `expires_at` is refused at render; the deployed document publishes the lifecycle at outputs v15 and the isolation matrix classifies it |
| `FLEET-EXPIRE-001` | P0 | Expiry is read, never acted on: the inventory reports an ephemeral project past `expires_at` as `expired`; `project-retire.sh` refuses an unexpired ephemeral project without `--before-expiry`; no unit, timer or cron in the release names `retire` |
| `FLEET-RETIRE-001` | P0 | `project-retire.sh` removes exactly the resources derived from its own key and recorded in its own state, refuses without a matching `--confirm`, refuses a `permanent` project without `--permanent`, releases the port allocation under the volume's identity **before** any volume is removed, and `--plan` mutates nothing. The survivor is untouched — which is `DEP-REMOVE-001`'s live proof, reused rather than duplicated |
| `FLEET-RETIRE-002` | P0 | A retirement never deletes a backup repository, a bucket, or `pgbackrest_repo_cipher_pass`; `--destroy-data` removes volumes and nothing off the host; the retirement record names, in words, what still holds the project's backups |
| `FLEET-BACKUP-001` | P0 | Every permanent project's two backup timers are installed and enabled on the host, `backup.sh schedule enable` refuses while no full backup exists or the units are absent, and the inventory reports a project whose timers are not enabled as `unscheduled` |

**Four claims**, each with at least one live half because `claim_mode` refuses a
claim whose every proof is offline (D856):

`fleet_inventory` (`FLEET-INV-001`, `FLEET-INV-002`) · `project_lifecycle`
(`FLEET-LIFE-001`, `FLEET-EXPIRE-001`) · `project_retirement`
(`FLEET-RETIRE-001`, `FLEET-RETIRE-002`) · `backup_schedule` (`FLEET-BACKUP-001`).

**And one Stage 1 claim closes without moving**: `project_removal`
(`DEP-REMOVE-001`, session 12) through `APG_REMOVED_PROJECT_FILE`, which the
retire verb writes (D953). Its proof is not touched.

**Each run writes its live half IN that run** (D938). Runs 2, 3, 4 and 5 each
add to `tests/deployment/test_session17_fleet.py`; Run 6 adds none.

---

## 4. Irreversible operations

| Operation | What makes it safe |
|---|---|
| **Retiring the third project** with `--destroy-data` | It is ephemeral by manifest and exists for this; its retirement record is captured **before** anything is removed (the proof's own rule); its backups stay readable until the console action D957 describes, which is deliberately separate |
| **Enabling the backup timers** on alpha and beta | Reversible (`schedule disable`), but each full backup costs six minutes at `process-max` 1 (D593) and R2 storage under `retain_full`; the first scheduled run is watched on the trip, not assumed. **Nothing is enabled before a full backup exists** (the operator guide's rule, now enforced by the verb) |
| **`provision-host.sh --apply` on a provisioned host**, to install the units | `--check` first, at a TTY; D659 says three `--apply` passes shaped the host and the SSH-hardening step refuses without an armed rollback timer. If `--check` reports anything but the missing units, the units are installed by hand with `install -m 0644` and `daemon-reload` and the difference is a §1 row |
| **Provisioning the third project** | Two buckets and two tokens created by hand and scoped to those buckets only (the Session 7 guide's rule); one DNS record, grey cloud; one ACME issuance, **never retried in a loop** (5/hour/hostname). `bootstrap-providers.sh --plan` before `--apply` |
| **The bump** (Run 6) | `CURRENT_SESSION` 16 → 17, `template_version` 0.5.0 → 0.6.0, outputs v15, project schema v3, all seven requirements and their proofs, in one commit (D690) |
| **The kernel restart** the host has been asking for | Optional, the operator's call, and it has a proof (`APG_AFTER_REBOOT`, Session 4 Run 10). If taken, it is taken with three projects up and **before** the retirement, so the restart matrix measures three instances returning and the retirement measures one instance staying gone |

---

## 5. Build order, run by run

Seven runs. Each ends with `**Done.**` and what it measured. The gate cadence is
`stage-2-plan.md` §11's: documentation → nothing; generated artefacts →
`session-01-check.sh`; code → targeted modules, the full suite once before the
trip and at the close, **nowhere else**.

### Run 1 — `doctor --json`, ADR 0185, and the ledger

- **Measure first**: `docker stats`-free `anon` per container on the host by
  ADR 0165's method, summed per project, and the host's `free -m`. **Decide,
  with a number in a §1 row, whether a third project fits.** If it does not,
  §9's first stop condition applies and the trip runs without the ephemeral
  project.
- `bin/doctor.py --json`: the same checks, as a document — `project_key`,
  `checks[]` of `{name, status, detail}`, `worst`, `observed_at`. `diagnosis`
  gains the renderer; `bin/doctor.sh` passes the flag. The redaction proof
  (`test_doctor_redaction.py`) runs over both renderings.
- **ADR 0185** — *an operator's read over the host's own files is not a
  cross-project catalog*: what §5's non-goal protects, and the four properties
  the inventory keeps (no route, no service, no credential, no reader).
  `docs/product-contract.md` §5 gains the sentence.
- The ledger: README's *intentionally unavailable* paragraph (D954),
  `docs/scope-closure.md` §2's two Session 12 claims, and D944 written into
  `docs/backup-operations.md` where the timers are described as running.
- Mutation battery over the JSON renderer: a check dropped, a status
  mis-ranked, a detail leaking a value the redaction list forbids.

**Done.** Measured first, as `op` with no root (D959): 22 scopes, 730 MB anon
in total, ~350 MB per project, 1982 MB available — the third project fits, and
D960 corrects the handoff's container count. `diagnosis.document` and
`diagnosis.render_json` render the same checks as a document with the module's
own `worst` and `exit_code`; `bin/doctor.py --json` and `bin/doctor.sh --json`
carry it, refusing `--verbose` beside it (two renderings of one report, D374's
shape at the command line) and `--json` without `--project`. The redaction
scan now runs over three renderings, and the JSON arm has its own premise test
(every probe present, every check with evidence, no UNKNOWN). ADR 0185 draws
the inventory's line and the product contract's §5 gains the paragraph that
says what its two non-goals protect. The ledger: README's *intentionally
unavailable* paragraph, `scope-closure.md` §2's heading and the two Session 12
claims (D954), `backup-operations.md`'s cipher-pass warning (D957) and its
timer step (D944). The battery's arms and their outcomes are in the run's
commit message.

### Run 2 — the fleet inventory

- `src/agentic_postgres/fleet.py`, pure: `rows(documents, checks, timers,
  denials)` → a report; `render_text`, `render_json`. Every project-scoped value
  under its own key; a document that fails `validate_deployed_document` is a
  row saying so, not an exception that hides the other rows.
- `bin/fleet.py` + `bin/fleet.sh` (root; `--json`; `--window HOURS` for the
  denial counts, default 24): iterates `PROJECT_STATE_ROOT`, runs doctor's
  probes in-process per project, reads `systemctl is-enabled` for both timers,
  reads denial counts by `denial_reason` over the container socket as root
  (the psql route `doctor.py` takes, D948). **Writes nothing** — asserted by a
  contract test that runs it against a fixture root and diffs mtimes.
- The reader guard: `test_no_operator_command_reads_a_key_the_deployed_document_does_not_have`
  covers the new module by construction (D600); nothing derives a name a second
  time (ADR 0002 — the inventory prints what the document says).
- Live half, written now: `test_the_inventory_sees_every_deployed_project_and_nothing_else`,
  `test_the_inventory_writes_nothing`, `test_the_inventory_prints_no_credential`.
- Battery: a project dropped from the loop, a value printed under the wrong key,
  a denial count read without the window, the timer state read from the
  document instead of systemd.

**Done.** Measured first: `systemctl is-enabled` on the host answers
`not-found`/4 for an instance of an uninstalled template, `disabled`/1 for an
instance nobody enabled, `enabled`/0 otherwise (D962), so the inventory keeps
`absent` apart from `disabled`. `src/agentic_postgres/fleet.py` composes a row
from the document's identity and release, the doctor's JSON document (run as a
subprocess, D961 — the plan said in-process), the two timers' states, and
refusals by reason over a window read from the audit table over the socket;
`bin/fleet.py` and `bin/fleet.sh` (root, `--json`, `--window`, `--root`)
iterate the state root and print every value under its own key, writing
nothing. `doctor.py` gained `--root` so the contract test drives the real
pipeline against a fixture root of one valid, one invalid and one empty
project. Twenty contract proofs in `test_fleet.py` including a poisoned-blocks
redaction scan with its control and an mtime-diff *writes nothing* proof with
its control; four live halves in `tests/deployment/test_session17_fleet.py`,
written now (D938). Registered in `SHELL_COMMANDS`, `PYTHON_COMMANDS`,
`ROOT_COMMANDS`, `PRIVILEGED_INVOCATIONS`, the environment-echo guard and
`DEPLOYED_DOCUMENT_READERS` (which caught a read of the doctor's document under
the name `document` — renamed, not exempted). Battery: ten arms, ten killed,
control green in every arm; the arms are in the commit message.

### Run 3 — the lifecycle field, outputs v15, ADR 0186

- `schemas/project.schema.json` v3: `project.lifecycle` (`kind` enum
  `permanent|ephemeral`, `expires_at` RFC 3339 UTC, required iff ephemeral);
  `SUPPORTED_PROJECT_SCHEMA_VERSIONS = {1, 2, 3}`; `config.py` reads it with
  `permanent` as the meaning of absence (D949). `bounds_table` learns the block.
- Outputs schema v15: `project.lifecycle` on both branches;
  `migrate_v14_to_v15` fills `permanent`; `SCHEMA_VERSION = 15`; the isolation
  matrix classifies `project.lifecycle.*` (it is project scope and may
  coincide — the category the matrix uses for that is read before it is chosen,
  D702).
- The render refuses an ephemeral manifest without `expires_at` and an
  `expires_at` in the past at render time (a project born expired is a typo).
- The inventory's `lifecycle` and `expired` columns.
- **ADR 0186** — *permanent is what every earlier manifest meant, and expiry is
  a fact the operator reads*.
- Live half: `test_a_permanent_project_publishes_its_lifecycle_at_v15`.
- Battery: absence read as ephemeral, the past-expiry check inverted, the
  migrator leaving the field absent.

### Run 4 — `project-retire.sh`, ADR 0187

- `bin/project-retire.py` + `bin/project-retire.sh`: root, TTY,
  `--project KEY --confirm KEY [--plan] [--permanent] [--before-expiry]
  [--destroy-data] --record PATH`. Order, and it is a contract test (D956):
  read the deployed document → derive every name through `naming` and read the
  instance uuid → write the record → `project-runtime.sh down` → `systemctl
  disable` the instance and both timers → `database-ports.py release` →
  remove the edge middleware file → remove state, secrets and rendered
  directories → `--destroy-data`: the two volumes → `bootstrap-providers.sh
  --destroy`. Nothing off the host (D957).
- `--plan` prints every name and mutates nothing (mtime diff, as Run 2).
- The record is `APG_REMOVED_PROJECT_FILE`'s shape: `project_key`, the
  resource names, `captured_at`, `lifecycle`, and what still holds the backups.
- **ADR 0187** — *a retirement removes what its key derives and its state
  records, on this host, and never a backup*.
- Live halves: `test_a_retirement_plan_mutates_nothing`,
  `test_a_retirement_refuses_the_wrong_confirmation`; the removal itself is
  proved by `DEP-REMOVE-001`'s existing proof on the trip.
- Battery: a name typed instead of derived, the release after the volume, the
  plan that writes, the confirm compared loosely.

### Run 5 — `backup.sh schedule`, the timers

- `bin/backup.sh schedule status|enable|disable --outputs FILE`: `status`
  reads `systemctl is-enabled` for both timers; `enable` refuses when either
  unit file is absent (naming `provision-host.sh --apply`) or when `info`
  reports no full backup; `disable` is unconditional.
- The inventory's `unscheduled` verdict comes from this, not from the document.
- Live half: `test_every_permanent_project_is_scheduled` — and it is the proof
  that goes red on the deployment as it is today, which is the point.
- `docs/backup-operations.md` step 5 becomes the verb.

### Run 6 — the bump

`CURRENT_SESSION` 17, `template_version` 0.6.0, the seven requirements, the four
claims, the `FLEET` prefix, `bin/session-17-check.sh` derived **by diff** from
session-16's (D505, D507, D678, D693) and registered in `SHELL_COMMANDS`; the
product-contract table and the acceptance matrix regenerated; `docs/fleet-
operations.md` written and indexed; README's documented path names the two new
verbs. No live half is written here — Runs 2–5 wrote theirs.

### Run 7 — the host trip

Gate once, every mode, before it; `pytest --setup-plan` with the environment
variables **set** (D671, D676). Then, in order, the operator at a TTY:

1. Bundle under the release name, `op` fetches, verifies `FETCH_HEAD`, checks
   out, `uv pip sync`, `sudo chown -R op:op .generated`, renders.
2. Deploy alpha and beta `--through-session 17` (v15 documents, `permanent`).
3. `provision-host.sh --check`, then `--apply` or the by-hand install (§4);
   `backup.sh schedule enable` on both. **Wait for the first `incr` timer**
   (`*-*-* 03:30`, 20 minute jitter) if the trip's timing allows; otherwise the
   scheduled run is read from the next day's `journalctl` and recorded.
4. The third project — `project.gamma.yaml`, ephemeral, `expires_at` an hour
   ahead — providers, DNS, deploy. `fleet.sh` shows three.
5. Optional: the kernel restart, three instances return, `APG_AFTER_REBOOT`.
6. After expiry: `project-retire.sh --plan`, then the retirement with
   `--destroy-data --record`. `fleet.sh` shows two.
7. Host gate with `--removed-project-file`, external mode, merge. **Expected:
   `project_removal` passes; seven not_run remain.**

Three gates and two repairs is the shape (Sessions 15 and 16); budget for it.

---

## 7. Evidence and claims

What each claim may honestly report **before its live half exists**, fixed now
so no proof is shaped to a verdict (D820).

| Claim | Offline may report | Needs a live half for |
|---|---|---|
| `fleet_inventory` | The report shape over fixture documents; the redaction scan; *writes nothing* against a fixture root | Three real documents on one host, doctor's verdicts live, the denial counts from a real audit table |
| `project_lifecycle` | v1/v2/v3 rendering, the refusals, the v15 migrator | A deployed document at v15 saying `permanent` for a project that never declared it |
| `project_retirement` | The order, the plan's inertness, the confirmations | The plan run as root against a deployed project; the removal itself is `DEP-REMOVE-001` |
| `backup_schedule` | The verb's refusals against fixtures | `is-enabled` on the host for both permanent projects, and a scheduled run that happened |
| `project_removal` (12) | — | `APG_REMOVED_PROJECT_FILE` from the trip |

**No claim spans both modes. A skip is not a pass**, and an offline half may not
stand in for a live one. **The other seven inherited `not_run` stay `not_run`**
and this session must not appear to close them (D478).

---

## 8. Security invariants this session touches

| Invariant | Control | Proof |
|---|---|---|
| Nothing a project serves can see another project | The inventory has no route, no service, no reader (ADR 0185) | `FLEET-INV-002` |
| The inventory holds no credential | It reads the document and the socket as root; the metrics route is not used (D948) | `FLEET-INV-001`, the redaction scan |
| A removal reaches only what its key derives and its state records | Every name through `naming`; `managed_resources` is the licence (ADR 0011) | `FLEET-RETIRE-001`, `DEP-REMOVE-001` |
| A backup outlives its project | Nothing off the host is deleted (ADR 0187) | `FLEET-RETIRE-002` |
| Expiry never destroys anything by itself | No unit names `retire`; the verb refuses without a human's flags | `FLEET-EXPIRE-001` |
| Projects share no project-scoped value | The matrix, 179 leaves + the lifecycle leaves | `DEP-ISO-001` |
| A restore never mounts the active volume | Standing (ADR 0151) | Unchanged |
| The MCP runtime holds no credential | Standing | Unchanged |

---

## 9. Stop conditions

Stop and ask when:

- **A third project does not fit** by Run 1's measurement. Then the trip runs
  without it, `project_removal` stays `not_run` with that reason in §1, and the
  retire verb's first live execution waits for a larger host.
- **The inventory would need a credential, a route, or a file another command
  reads.** That is the registry the product contract forbids and the stage
  plan's §9 stop; it is evidence for a Stage 3 specification, not a wider run.
- **Anything proposes a timer, a unit, or a deploy step that calls `retire`.**
- **The retire verb would need to name a resource its key does not derive** or
  its state does not record — a bucket, a DNS record, an Infisical secret.
  Those are the operator's, by ADR 0110, and stay so.
- **`provision-host.sh --check` on the provisioned host reports anything beyond
  the missing units.** Then `--apply` is not the repair and the units go in by
  hand, with a §1 row.
- **A v3 project manifest cannot accept a v1 one.** Both host manifests are v1
  and this repository does not hold them.
- **The first scheduled backup fails or overlaps the trip's own full backup**;
  `process-max` is 1 and two pgBackRest processes on one stanza is a
  measurement nobody has made.
- **An ACME issuance for the third domain fails.** Never retry in a loop; the
  cap is 5/hour/hostname and the trip has one hostname to spend.
- A currently-passing test would be weakened, or an allowlist loosened to a
  subset check.

---

## Appendix — what to consult

`docs/plans/stage-2-plan.md` §2, §3, §5, §9 and §11. `docs/scope-closure.md`
§2 — and D954 above, which says where it is wrong. ADR 0002 before Runs 2 and
4 (every name is derived once), ADR 0011 and 0110 before Run 4 (what the
bootstrap owns and what it does not create), ADR 0030 and 0042 before Run 4
(the volume's identity and the allocation keyed on it), ADR 0145 and 0147
before writing ADR 0187 (the backup account and its residual), ADR 0158 and
0165 before Runs 1 and 2 (the deployed document is the address book; `anon` is
the memory figure), ADR 0177 and 0183 before Run 3 (a field at the version that
introduces it; the last project-schema bump).

**Grep the plans for anything this session touches.** Nothing indexes the ~940
measured facts by subject. D522, D576–D579 (the units and their trampoline),
D691 (the removal surface), D700–D702 (the document's staleness and the matrix's
categories), D930 (which file decides what), and D940–D943 (the last trip) are
the rows this session will meet first.

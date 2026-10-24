"""Agentic Postgres Primitive — deterministic repository contract.

This package holds the logic that derives every project-scoped identity from a
validated, non-secret manifest. Nothing here reads a secret, opens a network
connection, or starts a service.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Session whose acceptance gate this working tree currently targets.
#: ``APG_ACCEPTANCE_SESSION`` overrides it; see plan decision P. Keeping a
#: default here means a bare ``pytest`` run enforces the same registry policy
#: as ``bin/session-01-check.sh`` instead of silently skipping it.
#:
#: Moved to 6 in Session 6 Run 11 and to 7 in Session 7 Run 9, each time with
#: the placeholders (D54). The move is what makes
#: ``test_no_requirement_at_or_before_the_gate_session_remains_future`` enforce
#: this session's own requirements: every ID targeted at 7 or earlier must now
#: point at a real test rather than at a ``future`` marker, so the eleven
#: entries Run 9 activated cannot quietly revert to placeholders.
#:
#: **This also arms the `session7` Compose profile.** The storage container is
#: held back by that profile, so until this line moved nothing could start one
#: -- and nothing had. A deploy from here on will try to, which means the two R2
#: secrets have to exist at the provider first. That is Run 10's sequence and
#: `docs/session-07-operator-guide.md` is the order to follow.
#:
#: **Session 10, since Run 10.** Moved together with the five recovery
#: placeholders' replacement, which is the pairing D439/D484 requires: the
#: placeholder policy and the overdue policy are exact mirrors on the gate
#: session. The constraint binds one way -- the bump requires the replacements,
#: and not the reverse -- so Run 9 replaced them and this run takes the bump,
#: together with ``bin/session-10-check.sh``. A tree declaring session 10
#: without its gate script is a tree whose gate cannot run (D579).
#:
#: **This arms no new Compose profile**, and that is the difference from every
#: previous bump. Session 10 added none: the archiver lives in the ``session3``
#: postgres service and the backup network is attached unconditionally. What it
#: arms is the deploy's **step 6c**, which creates a stanza and runs
#: ``pgbackrest check`` -- and a check failure fails the deploy. So a deploy from
#: here on needs the three repository secrets present at the provider, and an R2
#: bucket and token an operator created out of band. That is Runs 11+, and
#: ``docs/session-10-operator-guide.md`` is the order to follow.
#:
#: **Session 11 arms no new Compose profile either.** `session_profiles` emits
#: ``--profile session11`` and no service carries it -- exactly as sessions 9 and
#: 10 do, whose profiles compose.yaml also does not define. What Session 11 adds
#: is a step 0 preflight, a deployed `doctor.sh`, one request id stamped on every
#: response, and migration 0022.
#:
#: **It moves in Run 9, not Run 11, and the suite is what decided that** (D672).
#: The plan put the bump in Run 11 and asked Run 9 to redeploy
#: ``--through-session 11`` -- which `deploy.sh` refuses above this number
#: (D59). Two more guards agree: `test_every_later_requirement_has_a_placeholder`
#: keeps a placeholder for any requirement targeting a session past this one, and
#: `test_every_claim_belongs_to_a_session_the_release_has_reached` refuses a
#: claim above it. Activation cannot precede the bump, and the trip cannot
#: precede activation.
#:
#: **Session 13 arms no new Compose profile and adds no service.** What it
#: activates is the release-identity surface: the compatibility rules on
#: `template_version` (ADR 0162), the `upgrade check | plan | verify` verbs, and
#: one front door over the commands that already exist.
#:
#: **The bump is all-or-nothing** (D690).
#: `test_no_requirement_at_or_before_the_gate_session_remains_future` refuses any
#: requirement due by now that is still a placeholder, so all four `REL-*`
#: requirements stop being placeholders in the same commit that moves this.
#:
#: **Session 13 is the first Stage 2 release, and it is where this constant stops
#: being the only version.** `VERSION` moved to `0.2.0` in the same commit and now
#: carries meaning: ADR 0162 says what each bump permits. **Both axes are kept
#: deliberately** (D705) -- this one is the internal release ordinal the evidence
#: model is keyed to, and `template_version` is the product version an operator
#: quotes. Replacing the ordinal would cost a session and buy a number already
#: published under another name.
#:
#: **And moving it is what D719 was waiting for.** `bin/write-session-evidence.py`
#: held `1 <= session <= 12` as a literal -- correct at every check for twelve
#: sessions, because the number it named and the number it meant were the same
#: one. It derives from here now, and so does its `--help`.
#:
#: **Session 16 moved it in Run 9, all-or-nothing again** (D690): nine
#: requirements and seven claims landed in the same commit, with their proofs,
#: because there were no `future` placeholders left to activate and a
#: requirement targeted at 16 arrives whole or not at all. `VERSION` moved to
#: `0.5.0` in that commit: four released migrations and a capability manifest
#: bump, each of which ADR 0162 prices at a minor.
#:
#: **Session 17 moved it in Run 6, all-or-nothing again**: seven `FLEET-*`
#: requirements and four claims, with every live half already written in the
#: run that built its plane (D938 applied). `VERSION` moved to `0.6.0`: a
#: project manifest bump (schema 3) and an outputs bump (v15), no migration --
#: ADR 0162 prices the manifest bump at a minor and this took one.
#:
#: **Session 18 moved it in Run 5, all-or-nothing again**: fifteen `REC-*` and
#: `OPS-REHEARSE-*` requirements and four claims. The offline halves were
#: written in the runs that built each plane; the live halves were not
#: (D1020) and landed here, gated on the trip's declarations. `VERSION`
#: moved to `1.0.0`: the Stage 2 release candidate, with the compatibility
#: sentence D991 asked for in the product contract's section 7 -- a manifest
#: bump (schema 4) and an outputs bump (v16), both additive with migrators,
#: inside the major.
#:
#: **Session 19 moved it to `1.0.1`, and `CURRENT_SESSION` stays 18.** The two
#: numbers answer different questions, and this is the first release where they
#: come apart: `CURRENT_SESSION` is what the evidence model is keyed to, and
#: Session 19 built no plane, registered no requirement and wrote no evidence
#: document. It repaired nineteen defects an adopter found in 1.0.0.
#:
#: A patch under section 7's sentence: no manifest field, no migration, no
#: contract entry, no capability and no secret was added, removed or retyped,
#: and nothing here is a change an operator must act on before upgrading.
#:
#: The tag exists because **1.0.0 does not carry its own documented-path
#: repairs** (D1033). `b60814b`, `2e82f46`, `04d71c7` and `e49c5aa` all landed
#: after that tag was made, so the one ref a new adopter has any reason to
#: trust was the one ref that still had the defects.
#:
#: **Session 20 moves it to 20, all-or-nothing again** (D690): seven `TEN-*`,
#: `API-*` and `OPS-READ-*` requirements and three claims, with every offline
#: half written in the run that built its plane and every live half here,
#: gated on the trip's declarations -- D938's rule, applied deliberately after
#: D1020 recorded Session 18 missing it.
#:
#: **19 is skipped, and the skip is the record** (D1063). `CURRENT_SESSION`
#: keys the evidence model, and Session 19 built no plane, registered no
#: requirement and wrote no evidence document -- so there is no session 19 in
#: the acceptance registry and never will be. A reader finding 18 followed by
#: 20 is reading a repair session that moved `VERSION` alone, which is the one
#: time in this project's history the two numbers have come apart.
#:
#: `VERSION` moves to `1.1.0`, and ADR 0162 prices it. The session adds a
#: project manifest field with a default (`migrations.set`, schema 5), one
#: released migration (0031), one reviewed contract entry (`create_task`), an
#: outputs bump with a migrator (v17), and a new api-surface schema version for
#: a project's own contract. Every one of them is ADDITIVE: a manifest below 5
#: still loads and renders as a project with no set of its own, a version 16
#: document migrates, and no operator must act on any of it before upgrading.
#: A minor, and Run 7's `upgrade plan` on the host is what confirms it -- a
#: `major` required there is a stop condition, not a number to write down.
#:
#: **Session 21 moves it to 21, all-or-nothing again** (D690): six `AGT-*`,
#: `EVAL-*` and `REC-*` requirements and two claims, every offline half written
#: in the run that built its plane (Runs 1-5) and every live half here, gated
#: on the roster variables the gate already exports. The agent plane is opened
#: to a tenant's domain (ADR 0200, ADR 0201): the scope vocabulary is derived
#: from the reviewed surface, the runtime registers its roster from the lock,
#: and a project owns a capability manifest beside its migration set.
#:
#: `VERSION` moves to `1.2.0`, and ADR 0162 prices it: a project manifest
#: field with a default (`mcp.capabilities`, schema 6), a capability manifest
#: version whose scope is a shape rather than an enum (schema 4, older versions
#: still load), a lock schema the runtime serves alongside 1-3 (4), and an
#: outputs bump with a migrator (v18). Every one is ADDITIVE, and a project
#: that declares nothing new serves exactly the six tools it served. A minor,
#: proposed here and confirmed by Run 7's `upgrade plan` on the host.
#:
#: **Session 22 moves it to 22, all-or-nothing again** (D690): nine `DEV-*`,
#: `EVD-*`, `OPS-*` and `AGT-*` requirements and six claims, every offline half
#: written in the run that built its plane (Runs 2-5) and every live half
#: written there too -- there is no trip this session, so the two host claims
#: are collected by Session 24's (D1163). `apg dev` is the session's work: a
#: disposable local PostgreSQL cluster built from the rendered document and the
#: release, applying the project's own migration set as the role that will
#: apply it, before any deploy exists to apply it to (ADR 0203).
#:
#: **This arms no Compose profile and starts no service.** The environment is
#: `docker run` on the locked image and nothing else -- it is not a deployment,
#: not a branch, and not a thing the fleet knows about.
#:
#: **What it does arm is a third EVIDENCE MODE** (ADR 0202), and that is the
#: one an operator reading this should notice. Until now a claim was measured
#: against a deployment or it was not a claim; four of this session's six are
#: measured against a CHECKOUT, and they are offline because
#: `evidence_claims.OFFLINE_CLAIMS` names them -- never because a marker was
#: missing. A session whose work is a developer's own command has claims no
#: host can answer, and the declaration is what keeps that from becoming a way
#: for a live claim to go green while its live proofs stopped being collected.
#:
#: `VERSION` moves to `1.3.0`, and ADR 0162 prices it. The session adds a new
#: operator command (`apg dev`), an optional `projects/<slug>/seeds/` directory
#: a project may or may not have, one additive migration in the example
#: project's own set (`20260914120002`, two `GRANT`s), and a third evidence
#: mode. **No manifest, outputs, capability, lock or secret schema moves**, and
#: no released migration is added -- a project that adopts this release and
#: never types `apg dev` renders byte-identical artefacts. A minor, proposed
#: here; Session 24's `upgrade plan` on the host is what confirms it, and a
#: `major` required there is a stop condition rather than a number to write
#: down.
#:
#: **Session 23 moves it to 23, all-or-nothing again** (D690): nine `GEN-*` and
#: `AGT-*` requirements and four claims, with every offline half written in the
#: run that built its plane and the two live halves here, gated on the trip's
#: declarations -- D938's rule, applied deliberately for the third session
#: running after D1020 recorded Session 18 missing it.
#:
#: What it ships is a GENERATED ARTEFACT, which is a kind of thing this
#: repository had not produced before. `apg generate` writes a typed TypeScript
#: client over the surface a project publishes, and ADR 0204's sentence is what
#: makes it more than a convenience: **a generated client is a claim about the
#: surface it was generated from**. The claim is a digest in the package, and
#: `init()` is where a caller checks it against the document the deployment
#: actually serves -- as the caller, through the route a caller uses, because
#: PostgREST serves a different document to every role.
#:
#: Two of this session's four claims are OFFLINE (ADR 0202's third mode, used
#: here for the second time): the IR, the emitter, the version rule, the
#: command and the toolchain are all answerable in a checkout with Docker. The
#: other two are HOST claims and are deliberately not declared offline, because
#: a checkout cannot say whether a deployment serves the surface a client was
#: generated for, nor which lock a running plane loaded. They are `not_run` at
#: this session's close and Session 24's trip collects them.
#:
#: `VERSION` moves to `1.4.0`, and ADR 0162 prices it. The session adds a new
#: operator command (`apg generate`), an optional `projects/<slug>/clients/`
#: directory a project may or may not have, **one additive member in a metadata
#: tool's result** (`list_resources` gains `lock` beside `resources`; every
#: existing key unchanged), and a new fixture image nothing deployed runs.
#: **No manifest, outputs, capability, lock or secret schema moves**, and no
#: released migration is added -- a project that adopts this release and never
#: types `apg generate` renders byte-identical artefacts and deploys the same
#: containers. A minor, proposed here; Session 24's `upgrade plan` on the host
#: is what confirms it, and a `major` required there is a stop condition rather
#: than a number to write down.
#:
#: **Session 24 moves it to 24, all-or-nothing again** (D690): ten `STU-*`
#: requirements, one more `AGT-*`, and four claims -- two declared offline and
#: two deliberately not, because a revocation is about a running plane refusing
#: the next request and a boundary is about a refusal that plane recorded. The
#: live module is collected under `--setup-plan` with its three declarations
#: set, in this commit, rather than discovered on a host.
#:
#: `VERSION` moves to `1.5.0`, and ADR 0162 prices it a MINOR. The session adds
#: a new operator command (`apg studio`), a `services/studio/` directory of
#: three first-party files that no image builds and no deploy runs, **one
#: released migration** (0032: the audit reader returns `denial_reason`, a DROP
#: + CREATE at the same arity because PostgreSQL refuses to change an existing
#: function's return type), and **one additive member in an existing response**
#: (`GET /admin/audit` rows gain `denial_reason`; every other key unchanged, and
#: that 200 has no schema to widen). **No manifest, outputs, capability, lock or
#: secret schema moves.** A caller that ignores the new member reads exactly
#: what it read before, and a project that adopts this release and never types
#: `apg studio` deploys the same containers with one more migration applied.
#: Proposed here; Run 7's `upgrade plan` on the host is what confirms it, and a
#: `major` required there is a stop condition rather than a number to write
#: down.
#:
#: **Session 25 moves it to 25, all-or-nothing again** (D690): six `DX-*`,
#: `SEC-*` and `REL-*` requirements and four claims -- three declared offline
#: and one deliberately not, because whether a deployment runs the release the
#: tree names and prices it as the class the tree proposes is a fact about a
#: deployment. Five of the six requirements' proofs were written in the runs
#: that built their planes (Runs 2-4) and arrive here whole; the sixth is this
#: run's own, and its live half is collected under `--setup-plan` with the
#: three declarations set, in this commit, rather than discovered on a host.
#:
#: What the session ships is HARDENING and a WALK, not a plane. The three DX
#: surfaces are held against every stage-plan security invariant by a matrix
#: that names a collectible node id per cell; the developer-experience layer
#: gains a context variable, a completion script and a record the outsider's
#: second walk is measured by; and the documentation an adopter reads was
#: re-derived by walking it, which is how three product defects were found
#: (D1340, D1341, D1342).
#:
#: `VERSION` moves to `1.6.0`, and ADR 0162 prices it a MINOR. The session adds
#: **two new operator commands** (`apg completion`, `apg dx-record`), **one
#: environment variable the dispatcher reads** (`APG_PROJECT`, applied only to
#: a verb whose own `--help` names `--project`, announced on stderr every time
#: it applies), and **one optional generated document per project**
#: (`projects/<slug>/docs/mcp-tool-catalog.md`, written only when asked for).
#: **No manifest, outputs, capability, lock or secret schema moves, and no
#: released migration is added.** A project that adopts this release and sets
#: no `APG_PROJECT` renders byte-identical artefacts and deploys the same
#: containers. Proposed at 1.6.0; Session 25's Run 7 `upgrade plan` on the host
#: returned `minor` on both projects with exactly one leaf differing, which is
#: what confirmed it.
#:
#: **Session 27 moves `VERSION` to `1.6.1`, and `CURRENT_SESSION` stays 25.**
#: The second time the two numbers have come apart, and for the same reason as
#: the first (1.0.1, Session 19): this session builds no plane, registers no
#: requirement and writes no evidence document. It repairs eighteen defects an
#: outside agent found while upgrading a real application from 1.0.0 to 1.6.0
#: holding only this repository's documentation, plus the defects that reading
#: exposed in the product underneath it.
#:
#: The pages are the other half of it. `docs/upgrade-guide.md` and
#: `docs/operator-guide.md` are release artefacts held by test from this
#: release on (ADR 0209): each states the release it is part of, the upgrade
#: guide's release table carries a row for it, and both are inside the two
#: documentation scans they were outside of. That decision exists because
#: **neither page is in tag `1.6.0`** -- they land one commit past it, which is
#: D1033's failure a second time, seven sessions later, committed by the
#: session that had read the first.
#:
#: **ADR 0162 prices it a PATCH.** What moved: `client_ir.FORMAT_TYPES` gained
#: the spellings PostgREST actually serves, measured against a running one
#: (`int32`, `int64` and every array form -- the table could not type an
#: `integer` anywhere, as a column or an argument); four `mkdir` sites in
#: `rendering.py` name the owner and the remedy the way `publish` already did;
#: `--help` is answered anywhere in the arguments by three wrappers that used
#: to dispatch the verb first; `bin/upgrade.sh`'s usage names `--also` and its
#: eight classes; two readers say which question they answered and tell an
#: absent key from a null; `deploy.sh --help` names the session this release
#: implements; and a command that is going to refuse no longer prints a success
#: sentence first. **No manifest, outputs, capability, lock or secret
#: schema moves, no released migration is added, and no command gains or
#: loses a verb.** Every change is a refusal that arrives better, a spelling the
#: generator already should have had, or a sentence that was false. **This
#: session takes no host trip**, so nothing here has been priced against a
#: deployment: the next trip's `upgrade plan` is what confirms the class, and a
#: `major` required there is a stop condition rather than a number to write
#: down. That trip also inherits D1401 -- both projects are deployed at `1.6.0`
#: and the tree now reads `1.6.1`, so `stage_release`'s live half fails until
#: it deploys before it sweeps, which is an obligation rather than a defect and
#: is stated here because a reader of this constant is who meets it.
#:
#: **`1.6.2` follows within the hour, and the reason is worth more than the
#: release.** Auditing 1.6.1 against the findings file it answers turned up two
#: repairs and produced a reply page -- and all three landed ONE COMMIT PAST
#: tag `1.6.1`. That is D1033's shape a third time, in the release built to
#: stop it. It was caught by a reading rather than by a reader this time, which
#: is the only difference, and the precedent for the fix is exact: `1.0.0` ->
#: `1.0.1` was the same thing for the same reason.
#:
#: **`VERSION` moves to `1.6.2`, and ADR 0162 prices it a PATCH.** What moved:
#: the refusal in `_assert_follows_release_version` had its REMEDY repaired --
#: 1.6.1's version told an operator to re-freeze the project lock, and
#: `freeze_project_lock` recomputes the floor from the current checkout, so
#: that instruction sends a set authored against an earlier release around a
#: loop. It now splits the two cases and says, for the one that matters, that
#: there is no supported way forward today and why re-stamping is worse. The
#: upgrade guide's first precondition stopped being absolute: *anything that is
#: not 10 ok is repaired* gave a reader no way to tell a disabled backup mirror
#: from a broken migration plane, and the step now sorts the doctor's verdicts.
#: And `docs/upgrade-findings-response.md` maps all thirty-four of the reader's
#: findings to Fixed, Documented, Open or No action, leading with the two that
#: are still open. **No manifest, outputs, capability, lock or secret
#: schema moves, no released migration is added, and no command gains or loses
#: a verb** -- the enforcement `_assert_follows_release_version` performs is
#: byte-for-byte what it was. Still no host trip, so the next trip's
#: `upgrade plan` is what confirms the class, and it still inherits D1401.
#:
#: **Session 28 moves it to 28, and 26 and 27 are skipped the way 19 is**
#: (D1063). Neither built a plane, registered a requirement nor wrote an
#: evidence document; the skip is the record, and `claims_through_session(28)`
#: inherits every earlier session's claims unchanged. Three requirements and
#: three claims: `DX-FOLLOWS-001` and `REL-READ-001` declared offline, and
#: `AGT-RETAIN-001` deliberately not -- what two tables on a nine-session-old
#: cluster are carrying, and whether a prune removes a row of it, is a fact
#: about a deployment and `not_run` until Session 29 sweeps.
#:
#: What the session ships is an AUDIT ACTED ON, not a plane.
#: `docs/pre-stage-4-audit.md` was its single input -- thirty-six rows this
#: project already knew were wrong with itself -- and the first run re-measured
#: all of them against the tree in both directions, finding fourteen already
#: answered and **three whose closing act would have done damage as written**.
#: What came out of the rest: the pre-`projects/<slug>/` fork's on-ramp decided
#: and documented (ADR 0210, 0211, 0212, `docs/on-ramp.md`); four readers that
#: reported a file event as a domain event repaired under ADR 0195; the four
#: modules that collected zero under every sweep selector brought inside one;
#: the installed distributions checked against the lock's pins by the gate, a
#: deferral written as a *when* in Session 6 and read as a *whether* for
#: twenty-two sessions while it cost three gate runs; what the agent record
#: keeps and for how long (ADR 0213); the reading before a tag (ADR 0214); and
#: the signing-key rotation rehearsed end to end, which found that the step
#: guarding the one irreversible act in this product could not see what a
#: verifier was holding (ADR 0215).
#:
#: **`VERSION` moves to `1.7.0`, and ADR 0162 prices it a MINOR.** One new
#: released migration (`20260917120033`: two prune functions granted to nobody,
#: a size reading granted to the record's existing reader, no schedule and no
#: caller), one new operator command (`apg release-reading`), and **the project
#: lock schema moves 2 -> 3** -- a set's lock now records whether its
#: `follows_release_version` was computed or declared, a schema-2 lock reads as
#: `computed`, and nothing an operator holds has to move for it. **No manifest,
#: outputs, capability or secret schema moves**, no API operation is added,
#: removed or changed, and the one migration is additive over two tables no
#: reachable identity can delete from. A project that adopts this release and
#: declares nothing new deploys the same containers with one more migration
#: applied. **The class was priced HERE rather than deferred, by the product's
#: own command** (D1481): rig 28l rendered the example project from `72cb2de`,
#: the 1.6.2 checkout, and from this one, and ran `upgrade plan --also
#: migration_added` between the two documents -- `bump minor`, `requires
#: minor`, verdict `ok`, no blocking reason, and **exactly one leaf differs,
#: `template_version`**. The control in the same run is what makes that mean
#: something: without the declaration the same pair requires only a `patch`, so
#: the `minor` is the migration rather than the version string. Every release
#: since 1.3.0 wrote *the trip's `upgrade plan` is what confirms the class* and
#: left the number unpriced until the trip, and ADR 0162's rule is decidable
#: from two RENDERED documents, which need no host and no root. **This session
#: takes no host trip and cuts no tag**, so nothing here is priced against a
#: DEPLOYMENT -- an installed document is not a render of the same manifest,
#: and only it can say what an operator would have to supply -- so Session 29's
#: `upgrade plan` still confirms the price against the running release, and a
#: `major` required there is a stop condition rather than a number to write
#: down. It does not inherit D1401, and that is the first time in four
#: releases: the tag now waits for the deploy rather than the deploy for the
#: tag (D1425).
#:
#: **Session 30 moves it to 30, and 29 is skipped the way 19, 26 and 27 are**
#: (D1063, D1514). That session took the trip that deployed 1.7.0, swept it and
#: tagged it; it built no plane and registered no requirement, so it has no
#: claim to introduce and the gap is the record.
#: `claims_through_session(30)` inherits every earlier session's claims
#: unchanged.
#:
#: **Five requirements and five claims**, and the split is four offline to one
#: host. `OPS-EXEC-001` (`exec_discipline`): every `docker exec` and every
#: `compose.sh run` this product performs is built by one function and runs
#: with stdin closed unless input is supplied, and an AST scan over the tree
#: finds no site outside it (ADR 0218). `REL-READ-002` (`release_reading_ref`):
#: `apg release-reading --ref REF` reads the commit a ref resolves to rather
#: than the working tree, which is what the tag procedure needs, because the
#: commit a tag goes on is behind `HEAD` on every trip (D1425, ADR 0219).
#: `CAP-COMPILE-001` (`contract_compile_output`): `mcp-contract.sh compile
#: --output PATH` writes only after the compile succeeded, and no documented
#: compile line redirects with a `>` that would truncate its target before the
#: command ran (D1359, D1540). `EVD-SHAPE-001` (`suite_shape`): no local hides
#: a module-level helper, and every deployment proof is a node id of some
#: requirement or is named in a list compared for equality (D1509, D1236).
#: Those four are DECLARED OFFLINE (ADR 0202): each is a property of this
#: checkout -- an argv, a `git` read, a file this command writes, the shape of
#: this suite -- and a deployment would answer none of them differently.
#:
#: **`STU-QUERY-002` is a HOST claim and is deliberately not declared**
#: (`studio_tenant_read`). It registers a proof that has existed since Session
#: 24, belonged to no requirement, and errored at setup on every sweep since:
#: its fixture created a stranger with an empty scope array that migration 0011
#: refuses. All three Studio claims read `passed` while it never ran, which is
#: what a proof belonging to no claim costs (D386, D1236). Whether a human's
#: rows and a stranger's stay apart through Studio's forwarder on a RUNNING
#: deployment is not something a checkout can answer, so it is `not_run` until
#: this session's trip sweeps -- and the trip is its first execution.
#:
#: **`VERSION` moves to `1.8.0`.** What moved: one new internal module
#: (`container_exec`) and one sourced shell library (`bin/lib/tty-guard.sh`)
#: through which every container exec in the product now runs; two new options
#: on two existing commands, `release-reading --ref REF` and `mcp-contract.sh
#: compile --output PATH`; two new contract modules that guard the suite's own
#: shape; and a documentation repair that stops two pages telling an adopter to
#: truncate their capability contract. **No manifest, outputs, capability, lock
#: or secret schema moves, no released migration is added, and no command gains
#: or loses a verb.** A project that adopts this release deploys the same
#: containers with the same migrations applied, and an operator supplies
#: nothing they did not supply for 1.7.0.
#: **ADR 0162 prices it a MINOR, and this is the first release where that price
#: is a judgement rather than a reading** (D1561). The product's own command was
#: asked: rig 30e rendered `project.example.yaml` from `8c61309`, the deployed
#: 1.7.0 commit, in a throwaway worktree and from this one, and ran `upgrade
#: plan` between the two documents -- `bump minor`, **`requires patch`**,
#: verdict `ok`, `reasons []`, `changes []`, and exactly one leaf differs,
#: `template_version`. `requires patch` is correct and is not a disagreement:
#: every one of ADR 0162's eight rows names something a RENDERED DOCUMENT shows
#: -- a migration, an API operation, a capability, a secret, a document schema,
#: an operator manifest -- and two new options on two existing commands show up
#: in no document at all, so by the table this release is *implementation only*.
#: What `requires` reports is the FLOOR: the smallest bump that permits the
#: change, which is what an operator has to do to take it. Nothing.
#: The minor is chosen above that floor, and the precedent is this project's
#: own: `1.3.0` shipped `apg dev` and `1.6.0` shipped `apg completion` and `apg
#: dx-record`, each priced a minor with the same one-leaf reading and the
#: upgrade guide's own words -- *a minor a deployment cannot see*. A release
#: that gives an operator something new to type is a minor even when no
#: rendered document moves, and bumping above the floor never costs anybody
#: anything. **This session takes a host trip**, so unlike 1.6.1, 1.6.2 and
#: 1.7.0 the class is confirmed against a DEPLOYMENT in the same session: Run
#: 7's `upgrade plan` on both projects, before the deploy, and a `major`
#: required there is a stop condition rather than a number to write down.
#: **Session 31 moves it to 31, all-or-nothing again** (D690): TEN
#: requirements and ten claims, six of them declared offline and four host,
#: with every offline half written in the run that built its plane (Runs 2-5)
#: and every live half here, gated on the trip's declarations -- D938's rule,
#: applied deliberately after D1020 recorded Session 18 missing it.
#:
#: **The session's subject is the node as a finite resource**, and the five
#: ADRs are its shape. ADR 0221: capacity is DECLARED in `host.yaml` and never
#: inferred from the machine, admission DECIDES against that declaration at
#: every deploy's step 0 with exit 12, and a reading REPORTS -- a decision may
#: fail closed, a report may not. ADR 0222: every project service is bounded in
#: processes and the nine long-running ones in CPU. ADR 0223: the collector is
#: consumed and every series names its project. ADR 0224: the rotation's
#: overlap window is closed by the operator's step-6 deploy, and `retire`
#: reports that it was instead of refusing for the wrong reason. ADR 0225: a
#: secret's value is checked against its declared kind at materialization.
#:
#: `NODE` is a new requirement family and the argument is `STU`'s: its subject
#: is the MACHINE -- what this node has, what has been claimed of it, whether
#: one more project fits -- and `DEP`, `OPS` and `CFG` are each about
#: something else. The tenth requirement, `AGT-METHOD-001`, is not this
#: session's plane at all: it registers two Session 9 proofs that have run on
#: every sweep since and belonged to no claim, found by the orphan triage
#: (D1597). `KNOWN_UNREGISTERED` went 22 -> 0.
#:
#: **`host.yaml` schema 3 is ADDITIVE and there is no migrator.** Schema 2
#: still validates and declares nothing; a schema 2 document carrying a
#: `capacity` block is refused rather than quietly read; and with no
#: declaration, admission refuses only a project this host has never deployed,
#: so an existing project is never made undeployable by a host that has not
#: declared yet. **No outputs schema moves** (v18 stays), no capability, lock,
#: project-manifest or secret schema moves, and no released migration is added
#: -- 33 stays 33. The one thing an operator MUST do is nothing; the one thing
#: they may do is declare, and until they do the product behaves as it did.
#:
#: **`VERSION` moves to `1.9.0`.** What moved: one new command (`bin/admit.sh`
#: and `bin/admit.py`), two new verbs on an existing one (`apg doctor
#: capacity|usage`) and one on another (`backup.sh usage`); a ninth rehearsal
#: scenario; `pids_limit` on all twenty compose services and `cpus` on nine;
#: `APG_OTLP_ENDPOINT` on the mcp service and `const_labels` on the collector's
#: exporter; two new internal modules (`capacity_reading`, `capacity_probe`);
#: an operator manifest schema (`host.yaml` 2 -> 3, additive); and two
#: behaviour changes in existing commands -- a deploy now takes an admission
#: decision before it renders, and `rotate-signing-key retire` reports a third
#: outcome where it used to refuse.
#:
#: **The price, read rather than chosen** (D704). The rig: a git worktree at
#: `be987cf`, the commit that IS deployed, and a copy of this working tree,
#: each rendering the example project, with `upgrade plan` run between the two
#: documents. **Neither side renders in the checkout**, because the example
#: project renders under the same key as one of the four fixtures the gate
#: compares for collisions, and a render here would overwrite it (D1485,
#: D1624). Read: `bump minor`, `requires patch`, verdict `ok`, `reasons []`,
#: `changes []`, `operator_digests_moved []`, and **exactly one leaf differs
#: -- `template_version`, 1.8.0 to 1.9.0.** Both documents are 5,948 bytes.
#: The compose environment's eighteen new keys do not appear, which the plan
#: for this run left open and this reading closes: `pids_limit` and `cpus` are
#: written into `compose.env`, and `outputs.json` is not that file (D1625).
#:
#: **And the one row of ADR 0162 this release does hit is invisible to that
#: command.** `host.yaml` goes from schema 2 to schema 3 -- an operator
#: manifest bump, which the table prices at a minor -- and `host.yaml` is an
#: operator INPUT that appears in no rendered document, so the floor came back
#: computed without the field that would have raised it (D1626). Reported
#: rather than folded: teaching `upgrade` to read an operator input would make
#: it a second reader of `host.yaml` beside `host_config` (ADR 0002, D816).
#:
#: **ADR 0162 prices it a MINOR**, and `1.9.0` is above the floor its own
#: command reports. `requires patch` is that floor -- the smallest bump that
#: permits the change, which is what an operator has to DO to take it, and the
#: answer is nothing. **No outputs, capability, lock, project-manifest or
#: secret schema moves**, no released migration is added and no command loses
#: a verb; the only schema that moves is an operator's, additively, with no
#: migrator. So the minor is chosen above the floor for the reason 1.3.0,
#: 1.6.0 and 1.8.0 were -- a release that gives an operator something new to
#: type -- AND for one those three did not have, a manifest schema that really
#: did move where the reading cannot see it. Bumping above the floor costs
#: nobody anything. **This session takes a host trip**, so the class is
#: confirmed against a DEPLOYMENT in the same session: Run 7's `upgrade plan`
#: on both projects before the deploy, and a `major` required there is a stop
#: condition rather than a number to write down.
#:
#: **Session 32 moves it to 32, all-or-nothing again** (D690): THIRTEEN
#: requirements and thirteen claims -- `CLAIMS` 145 -> 158 and `OFFLINE_CLAIMS`
#: 24 -> 32, counted from the tuples rather than by hand (D1628) -- eight
#: declared offline and five host, with every offline half written in the run
#: that built its plane (Runs 2-6) and every live half here.
#:
#: **The session's subject is durable work an agent starts and a loop
#: executes**, and the four ADRs are its shape. ADR 0226: the worker is a loop
#: INSIDE the auth process, using that service's own role, pool and token
#: issuance -- no container, role, secret, claimant or document field is
#: added, and the loop's idle cost measured 7.8 MiB. ADR 0227: the state is
#: four `app_private` tables nobody may read and nine definer functions; a
#: step's idempotency key is per (run, step) and never per attempt, so a
#: replay after a crash is re-read rather than written twice; and -- amended
#: in Run 7 (D1696) -- a step records the request id the PLANE minted, read off
#: its response, because the plane ignores one a caller sends (ADR 0160).
#: ADR 0228: a definition is a reviewed artefact compiled against the
#: project's lock and installed by a deploy's step 6d, immutable per name and
#: version. ADR 0229: three routes for AGENT tokens behind a second
#: authenticator, amending ADR 0114. And D1636 is repaired first: the ceilings
#: reading counts the database.
#:
#: `WF` is a new requirement family and the argument is `NODE`'s: its subject
#: is a WORKFLOW -- properties that hold ACROSS requests and across processes,
#: a lease, a replay, a park, a resumption after a crash -- and `AGT`, whose
#: every property holds for the length of one call, does not name them.
#:
#: **One migration, 0034, and it is the floor once applied** (ADR 0162 §3). It
#: was amended three times while applied nowhere -- the claim returning its
#: request id (D1686), taking a margin rather than a lease (D1687), and then
#: returning none, because the id that correlates is the plane's (D1696) --
#: and after this session's deploy it is fixed forward like every other. **No
#: outputs, capability, lock, project-manifest, secret or host schema moves**,
#: and outputs stays v18 with no new field (D1654).
#:
#: **`VERSION` moves to `1.10.0`.** What moved: migration 0034; three
#: operations on the auth service's application API (`POST /workflows/runs`,
#: `GET /workflows/runs/{run_id}`, `POST /workflows/runs/{run_id}/cancel`); a
#: loop in the auth process, so the `auth` image moves and a deploy recreates
#: it; one new command, `bin/workflow.sh`, with six verbs; a deploy step 6d; a
#: twelfth doctor check; a tenth rehearsal; one member in the restore drill's
#: evidence; `doctor capacity`'s ceilings grouped by compose project; and one
#: new page, `docs/workflows.md`.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git
#: worktree at `4344a1f`, the commit that IS deployed, and a `tar`-piped copy
#: of this working tree, each rendering the example project outside the
#: checkout. **Two readings, because the command prices only what a document
#: shows** (D1666). With `--also migration_added --also api_operation_added`:
#: `bump minor`, **`requires minor`**, verdict `ok`, `changes
#: [api_operation_added, migration_added]`, `reasons []`,
#: `operator_digests_moved []`. Without the declarations: `requires patch` --
#: the floor the documents alone establish, wrong in the reassuring direction,
#: which is why the declaration exists. **Exactly two leaves differ, and the
#: plan predicted a different second one** (D1703): `template_version` 1.9.0 ->
#: 1.10.0 and `migrations.release_lock_sha256`; the rendered document carries
#: no migration COUNT, so there was never a `migrations.count` leaf to move.
#: 5,948 bytes -> 5,949. **ADR 0162 prices it a MINOR, and here the minor is
#: the floor rather than a judgement above it**: a new released migration and
#: a new API operation are each a minor by the table, and the first makes a
#: rollback by image impossible past it. `1.10.0` is that floor exactly. **No
#: outputs, capability, lock, project-manifest, secret or host schema moves**,
#: so an operator supplies nothing new to take it -- what they must know is
#: that 0034 is applied at step 6 and cannot be taken back by an image.
#: **This session takes a host trip**, so
#: the class is confirmed against a DEPLOYMENT in the same session: Run 8's
#: `upgrade plan` on both projects, with the same two declarations, before the
#: deploy -- and a `major` there is a stop condition.
#:
#: **Session 33 moves it to 33, all-or-nothing again** (D690): FOURTEEN
#: requirements and fourteen claims -- `CLAIMS` 158 -> 172 and `OFFLINE_CLAIMS`
#: 32 -> 42, counted from the tuples rather than by hand (D1628) -- ten
#: declared offline and four host, with every offline half written in the run
#: that built its plane (Runs 2-7) and every live half here.
#:
#: **The session's subject is a human in the loop of durable work**, and the
#: five ADRs are its shape. ADR 0230: an approval is a PARKED step and a
#: human's recorded decision -- the plane's own `approval_required` refusal
#: parks it, a decision releases or rejects it, and a rejection is a cancel.
#: ADR 0231: an approved call carries a signed `apg_approval {id, tool, key}`
#: claim that only the signer builds, from a decided row it reads itself, and
#: the plane serves a gated write only for that tool and that key -- every
#: caller without the claim is refused byte for byte as before. ADR 0232: the
#: decision is an administrative scope, `admin_workflows:approve`, that
#: `project_admin` alone may carry and the run's OWNER may not use. ADR 0233:
#: compensation is reverse-ordered forward steps appended at failure or cancel,
#: and a wait is a park. ADR 0234: provenance is one reader joined by the
#: plane's request id, under the audit's own scope, and the audit reader pages
#: by keyset with the window's counts on every page (D1248 answered, not
#: refused). No family is added: the gates are a run's (`WF`), the claim and
#: the filters the agent plane's (`AGT`), the ledger print an operator's
#: (`OPS`, D1707).
#:
#: **One migration, 0035, and it is the floor once applied** (ADR 0162 §3):
#: two `app_private` tables nobody may read, the approval functions, a run
#: status `compensating`, and the audit reader re-created at nine arguments.
#: **No outputs, capability, lock, project-manifest, secret or host schema
#: moves**; the capability schema's administrative enum gains one member
#: without its `schema_version` moving, the way `admin_audit:read` joined it
#: in Session 9.
#:
#: **`VERSION` moves to `1.11.0`.** What moved: migration 0035; four
#: operations on the auth service's application API for HUMAN tokens (`GET
#: /admin/workflows/approvals`, `POST /admin/workflows/runs/{run_id}/approve`
#: and `/reject`, `GET /admin/workflows/runs/{run_id}`) and five new query
#: parameters on `GET /admin/audit`; one administrative scope; the loop's
#: gates, waits and compensations, so the `services/auth-api` image moves and
#: a deploy recreates `auth`, `storage` and `mcp`; `bin/workflow.sh` gains four
#: verbs (ten); the doctor's `workflow` check reports pending approvals; the
#: drill member carries approvals; `migrate.sh --runtime status` prints the
#: ledger again.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git
#: worktree at `275a19e`, the commit that IS deployed, and a `tar`-piped copy
#: of this working tree, each rendering the example project outside the
#: checkout. With `--also migration_added --also api_operation_added`: `bump
#: minor`, **`requires minor`**, verdict `ok`, `changes [api_operation_added,
#: migration_added]`, `reasons []`, `operator_digests_moved []`. Without the
#: declarations: `requires patch` -- the documents' own floor, wrong in the
#: reassuring direction, which is why the declaration exists (D1666). **Exactly
#: two leaves differ, the two the plan predicted**: `template_version` 1.10.0
#: -> 1.11.0 and `migrations.release_lock_sha256`; 5,949 bytes on both sides.
#: **ADR 0162 prices it a MINOR, and the minor is the floor**: a released
#: migration and new API operations are each a minor by the table, and
#: `1.11.0` is that floor exactly. **No outputs, capability, lock,
#: project-manifest, secret or host schema moves**, so an operator supplies
#: nothing new to take it. What an operator must KNOW is two things the
#: reading cannot show: 0035
#: cannot be taken back by an image, and **no existing administrator gains the
#: new scope** -- it is granted with `PATCH /admin/users/{id}`, role and scopes
#: together, or nobody on the deployment can decide an approval. **This
#: session takes a host trip, ON BETA** (D1733) -- alpha installs no
#: definition -- so the class is confirmed against a DEPLOYMENT in the same
#: session: Run 9's `upgrade plan` on both projects, with the same two
#: declarations, before the deploy -- and a `major` there is a stop condition.
#:
#: **Session 34 moves it to 34, all-or-nothing again** (D690): SIXTEEN
#: requirements and sixteen claims -- `CLAIMS` 172 -> 188 and `OFFLINE_CLAIMS`
#: 42 -> 53, counted from the tuples rather than by hand (D1628) -- eleven
#: declared offline and five host, with every offline half written in the run
#: that built its plane (Runs 2-8) and every live half here. Two families join
#: the registry: `EVT` (what an event is and who may write or wait on one) and
#: `CONN` (what a connector is, how it is bound, delivered and started).
#:
#: **The session's subject is governed connectivity**, and the five ADRs are its
#: shape. ADR 0235: an event is written only by a reviewed definer function in
#: a project's own set calling `app.emit_event`, which NO role may call, and is
#: recorded only when something listens. ADR 0236: a connector is a project
#: file the deploy installs DISABLED (step 6e) and an administrator enables,
#: binding an agent whose stored scopes EQUAL its definition's. ADR 0237: the
#: inbound route verifies an HMAC over the delivery before it reads anything
#: else, and every connector's key is derived from ONE facility-gated secret.
#: ADR 0238: delivery is the loop's second pass -- signed, at least once, never
#: redirected, dead after `max + 1` attempts. ADR 0239: a wait resumes on its
#: run owner's matching event.
#:
#: **One migration, 0036, and it is the floor once applied** (ADR 0162 §3):
#: four `app_private` connector tables nobody may read, the emitter granted to
#: nobody, the connector functions (seven to `auth_service`, the install and
#: the rehearsal's to nobody), the event wait, and `workflow_counts` with four
#: delivery members. **Outputs move to v19** (`connectors.enabled`, migrated
#: from v18 as `false`) and **the project manifest to schema 7**
#: (`connectors: {enabled, endpoints}`); the secret contract gains ONE
#: facility-gated secret; the capability schema's administrative enum gains two
#: members without its `schema_version` moving.
#:
#: **`VERSION` moves to `1.12.0`.** What moved: migration 0036; one operation
#: on the auth service's application API that takes NO token (`POST
#: /connectors/{name}`, a signature) and three for HUMAN tokens (`GET
#: /admin/connectors`, `POST /admin/connectors/{name}/enable` and `/disable`);
#: two administrative scopes; the loop's delivery and schedule passes and the
#: event wait, so the `services/auth-api` image moves and a deploy recreates
#: `auth`, `storage` and `mcp`; deploy step 6e; `bin/connector.sh` (six verbs);
#: the doctor's `workflow` check reports deliveries; the drill member carries
#: them; an eleventh rehearsal, `delivery-retry-storm`; the example set's
#: `0003` emits `note_embedding.set@1` and three definitions and four
#: connectors join it.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git
#: worktree at `02ffbbd`, the commit that IS deployed, and a `tar`-piped copy
#: of this working tree, the candidate rendering the INSTALLED tree's
#: `project.example.yaml` -- an operator's manifest does not move with a
#: release, and rendering each tree's own read `blocked` on `project_sha256`,
#: the rig's artefact. With `--also migration_added --also api_operation_added
#: --also document_schema_migratable`: `bump minor`, **`requires minor`**,
#: verdict `ok`, `changes [api_operation_added, document_schema_migratable,
#: implementation, migration_added]`, `reasons []`, `operator_digests_moved
#: []`, and **no `secret_required_added`** -- the facility-gated secret is
#: owed by no project that leaves the facility off, which is the minor's whole
#: argument (D1784). Without the declarations: `requires patch`, the
#: documents' own floor. **Seven leaves differ**: D1811's five --
#: `template_version` 1.11.0 -> 1.12.0, `schema_version` 18 -> 19,
#: `connectors.enabled` absent -> false, `migrations.release_lock_sha256`,
#: `inputs.secrets_contract_sha256` -- and two it did not name,
#: `migrations.project_set.count` 2 -> 3 and `migrations.project_set.lock_sha256`,
#: the example set's own `0003` (5,949 -> 5,993 bytes).
#: **ADR 0162 prices it a MINOR, and `1.12.0` is that floor exactly.** Its two
#: schema moves are MIGRATABLE -- outputs v18 migrates to v19 as `false`, and
#: a schema-6 project manifest still validates -- and no capability, lock,
#: secret or host schema moves, so an operator supplies nothing new unless it
#: turns the facility on. What an operator must KNOW the reading cannot show:
#: 0036 cannot be taken back by an image; **no existing administrator gains
#: either connector scope**; and **the facility is off
#: until a manifest turns it on**, as its own operation with
#: `bootstrap-providers.sh --apply` (D1807). **This session takes a host trip,
#: ON BETA** (D1809) -- alpha is the control without the facility -- so the
#: class is confirmed against a DEPLOYMENT in the same session: Run 10's
#: `upgrade plan` on both projects, with the same three declarations, before
#: the deploy -- and a `major` there is a stop condition.
#:
#: **Session 35 moves it to 35, all-or-nothing again** (D690): TEN requirements
#: and ten claims -- `CLAIMS` 188 -> 198 and `OFFLINE_CLAIMS` 53 -> 60, counted
#: from the tuples rather than by hand (D1628) -- seven declared offline and
#: three host, with every offline half written in the run that built its plane
#: (Runs 2-6) and every live half here. One family joins the registry: `GOV`
#: (what a proposed change to a project's set is, who records its review, and
#: what a host refuses to apply without one).
#:
#: **The session's subject is the ACT of changing a deployment**, and the four
#: ADRs are its shape. ADR 0242: approval is enforced in the DATABASE by
#: `app.require_approval`, granted to NOBODY, which a gated project RPC calls
#: first -- an agent's direct call is refused `PT403` unless its token's
#: `apg_approval` names the tool, its `Idempotency-Key` equals the claim's key,
#: and an approved decision for both exists on a running run of that agent; a
#: human's own call passes. ADR 0243: a change to a project's migration set is
#: PROPOSED (`bin/migrate.sh propose`, a committed record keyed by the sha256
#: of the set's lock, with the lint, the destructive findings, a from-empty
#: apply, the reviewed surface and the approval-gate check) and APPROVED by a
#: second declared name (`approve`), and a host applies a set with a pending
#: version only when the committed proposal names it -- the names are declared,
#: not authenticated, and the records say so. ADR 0244: the edge's two
#: containers and every long-running project service are bounded. ADR 0245:
#: the diagnostic account reads the auth, storage and MCP logs.
#:
#: **One migration, 0037, and it is the floor once applied** (ADR 0162 §3): one
#: function, no table, no column, no `api` object. **The project manifest moves
#: to schema 8** (`migrations.approvals_required: 0|1`), and 1-7 still load
#: unchanged; **no outputs, capability, lock, secret or host schema moves**.
#:
#: **`VERSION` moves to `1.13.0`.** What moved: migration 0037; the example
#: set's `0004` (`api.set_note_embedding` with the guard first) and its
#: committed proposal and approval; `bin/migrate.sh propose|approve` and the
#: host gate in `up`, with `status`'s proposal line and deploy step 6's
#: capability report; `migrations.destructive_findings`; the approval-gate
#: check (refused by `mcp-contract.sh check --project` and `propose`, reported
#: by the render); `mem_limit`, `pids_limit` and `cpus` on `traefik` and
#: `docker-socket-proxy`, and `mem_limit` on pgbouncer, postgrest, docs and
#: edge-probe, so a deploy recreates those four and `bin/edge.sh restart`
#: recreates the edge; `apg-diag`'s allowlist and its JSON-key redaction; a DR
#: kit's every directory 0700 (D1856). The `services/auth-api` image does not
#: move.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig as Session 34
#: ran it (D1844): a git worktree at `14b1b9d`, the commit that IS deployed,
#: and a `tar`-piped copy of this working tree, both rendering the INSTALLED
#: tree's `project.example.yaml` (schema 7, no `approvals_required`). With
#: `--also migration_added`: `bump minor`, **`requires minor`**, verdict `ok`,
#: `changes [migration_added]`, `reasons []`, `operator_digests_moved []`.
#: Without the declaration: `requires patch`, the documents' own floor -- the
#: fourth release in a row whose price the command sees only by declaration
#: (D1561, D1703, D1811, D1889). **Four leaves differ, the four D1889
#: predicted**: `template_version` 1.12.0 -> 1.13.0, `migrations.
#: release_lock_sha256`, `migrations.project_set.count` 3 -> 4 and
#: `migrations.project_set.lock_sha256` (the example set's `0004`); the
#: compose limits reach no document leaf; 5,993 bytes on both sides.
#: **ADR 0162 prices it a MINOR, and `1.13.0` is that floor exactly**: a
#: released migration is a minor by the table; **no outputs, capability, lock,
#: secret or host schema moves**, and the project manifest's schema 8
#: invalidates no older manifest, so an operator supplies nothing new. What an
#: operator must KNOW the reading cannot show: 0037 cannot be taken back by an
#: image; **a project that ADDS a migration now proposes
#: it first, and a host refuses a pending set without its proposal** -- a new
#: step, not an invalidated manifest, and a set already applied needs none;
#: and **the edge's limits take effect only when the edge is recreated**,
#: which drops every project's ingress for the measured interval. **This
#: session takes a host trip** (Run 10), so the class is confirmed against a
#: DEPLOYMENT in the same session: `upgrade plan` on both projects, with the
#: same declaration, before the deploy -- and a `major` there is a stop
#: condition.
#:
#: **Session 36 moves it to 36, all-or-nothing again** (D690): EIGHT
#: requirements and eight claims -- `CLAIMS` 198 -> 206 and `OFFLINE_CLAIMS`
#: 60 -> 65, counted from the tuples rather than by hand (D1628) -- five
#: declared offline and three host, with every offline half written in the run
#: that built its plane (Runs 2-6) and every live half registered here. One
#: family joins the registry: `LEDGER` (the Reality Ledger).
#:
#: **The session's subject is what a hosted reading needs before the host is
#: hosted** -- Stage 5's preconditions (ADR 0246) -- and four ADRs are its
#: shape. ADR 0248: the Stage 4 record is pruned by an operator who states a
#: horizon -- three prunes by aggregate (runs, deliveries, agents), a size
#: reading, and the worker's withdrawal of pending approvals on ended runs on
#: its idle polls -- reached through the record command, which nothing
#: schedules. ADR 0249: the `apg.*` and worker INFO lines reach `docker logs`
#: through one stdout handler `create_app` installs first, with propagation
#: left on (D2017). ADR 0247: the Reality Ledger, `docs/reality-ledger.yaml`, a
#: program's record of what each product concept is today, whose `available`
#: and `beta` rows must name evidence that passed. ADR 0250: each secret that
#: declares `max_age_days` has its provider update time read by `doctor
#: secrets` -- never its value, and nothing rotates a secret because it is old.
#: The hosted threats are a list until their controls exist (D1999).
#:
#: **Two migrations, 0038 and 0039, and they are the floor once applied** (ADR
#: 0162 §3): an enum value and five functions, no table, column or `api`
#: object. **No outputs, manifest, capability, lock or host schema moves**; the
#: secret contract admits an optional `max_age_days`.
#:
#: **`VERSION` moves to `1.14.0`.** What moved: migrations 0038 and 0039;
#: the record command (`size`, `prune`); the worker's idle withdrawal;
#: `services/auth-api/app/log_setup.py`; `docs/reality-ledger.yaml`, its
#: schema, `bin/render-reality-ledger.py` and the generated page;
#: `max_age_days` on three secrets, `InfisicalClient.read_secret_times`,
#: `secret_age.py` and `doctor secrets`. The `services/auth-api` image moves.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig as Sessions
#: 34 and 35 ran it: a git worktree at `f7fb96d`, the commit that IS deployed,
#: and a `tar`-piped copy of this working tree, both rendering the INSTALLED
#: tree's `project.example.yaml` (schema 8). With `--also migration_added`:
#: `bump minor`, **`requires minor`**, verdict `ok`, `changes [implementation,
#: migration_added]`, `reasons []`, `operator_digests_moved []`. Without the
#: declaration: `requires patch` -- the fifth release in a row whose price the
#: command sees only by declaration (D1561, D1703, D1811, D1889, D2001).
#: **Three leaves differ**: `template_version` 1.13.0 -> 1.14.0,
#: `migrations.release_lock_sha256`, and `inputs.secrets_contract_sha256` (the
#: `max_age_days` declarations -- a release digest, so `implementation`);
#: 5,993 bytes on both sides. **ADR 0162 prices it a MINOR, and `1.14.0` is
#: that floor exactly**: a released migration is a minor by the table; no
#: manifest, outputs, capability, lock or host schema moves; and the secret
#: contract's schema only ADMITS an optional `max_age_days`, which invalidates
#: no contract. What an operator must KNOW the reading cannot show:
#: 0038 and 0039 cannot be taken back by an image; a prune removes rows for
#: good, and an idempotency prune re-arms every key it removes; and the auth
#: container's log now carries a line per request. **This session takes a host
#: trip** (Runs 9 and 10), so the class is confirmed against a DEPLOYMENT in
#: the same session: `upgrade plan` on both projects, with the same
#: declaration, before the first 1.14.0 deploy -- and a `major` there is a stop
#: condition.
#:
#: **Session 37 moves it to 37, all-or-nothing again** (D690): THIRTEEN
#: requirements and thirteen claims -- `CLAIMS` 206 -> 219 and `OFFLINE_CLAIMS`
#: 65 -> 74, counted from the tuples rather than by hand (D1628) -- nine
#: declared offline, three EXTERNAL and one host, with every offline half
#: written in the run that built its plane (Runs 2-7) and every live half here.
#: Two families join the registry: `CTL` (the control plane) and `KEY`
#: (management API keys). The three external claims are the first that are a
#: CUSTOMER's, proved through the control project's public route alone (D2058).
#:
#: **The session's subject is the control plane** -- the one project that holds
#: accounts, organisations and a registry of the others (ADR 0246's first
#: hosted surface) -- and four ADRs are its shape. ADR 0251: a project manifest
#: at schema 9 may enable the `control` facility; its `auth` container then runs
#: `APP_MODE=control` (health, `/auth/me` and the management API `/v1`, nothing
#: else), a control router publishes `{api}/v1`, and its migration set
#: `projects/control` is its tables; it reads no other project's document,
#: URL or credential, and the registry is written by root from the deployed
#: documents (`bin/control.sh adopt|registry|totp-reset`). ADR 0252: accounts
#: by invitation only -- an account invitation by the registry administrator,
#: a membership invitation by an owner or admin -- with a TOTP second factor an
#: owner or admin must enrol before anything else; tokens stored hashed, seeds
#: the stated exception. ADR 0253: four roles, a role matrix over every route,
#: and management keys whose scopes are their own intersected with their
#: owner's current role, minted only by a person. ADR 0254: operations are a
#: closed type table and none is accepted while its Ledger row is `planned`.
#: The terminal reaches it through `bin/login.sh`, `logout.sh`, `context.sh`,
#: `org.sh` and `project.sh` (a 0700 directory of 0600 files, https only).
#:
#: **No released migration** -- the control plane's three are its own set's,
#: frozen in `projects/control/migrations/released.lock.json`. **Outputs move
#: to v20** (`routes.control` and `control: {enabled}`, migrated from v19 as
#: off with the route derived from the app route) and **the project manifest to
#: schema 9** (`control: {enabled}`, optional); no capability, lock, secret or
#: host schema moves. A second contract snapshot,
#: `contracts/control-openapi.canonical.json`, is the `/v1` surface.
#:
#: **`VERSION` moves to `1.15.0`.** What moved: the control mode of
#: `services/auth-api` (`control_routes`, `control_service`,
#: `control_repository`, `control_roles`, `totp`, `operations`), so the image
#: moves and a deploy recreates `auth`, `storage` and `mcp`; the control set;
#: manifest 9 and outputs 20; the control router and the app rule's negation;
#: the lint's one function-grant form for `{{auth_service}}`; `bin/control.sh`;
#: the five CLI commands and `control_client.py`; `project.control.example.yaml`.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig as Sessions
#: 34-36 ran it: a git worktree at `2538ac0`, the commit that IS deployed, and a
#: `tar`-piped copy of this working tree, both rendering the INSTALLED tree's
#: `project.example.yaml` (schema 8). With `--also document_schema_migratable
#: --also api_operation_added`: `bump minor`, **`requires minor`**, verdict
#: `ok`, `changes [api_operation_added, document_schema_migratable]`, `reasons
#: []`, `operator_digests_moved []`. Without the declarations: `requires patch`
#: -- the sixth release in a row whose price the command sees only by
#: declaration. **Four leaves differ**: `template_version` 1.14.0 -> 1.15.0,
#: `schema_version` 19 -> 20, `control.enabled` absent -> false, and
#: `routes.control` absent -> the example's own domain with `/api/v1` (5,993 ->
#: 6,090 bytes).
#: **ADR 0162 prices it a MINOR, and `1.15.0` is that floor exactly**: the
#: outputs move is MIGRATABLE, the manifest's schema 9 invalidates no older
#: manifest, and no capability, lock, secret or host schema moves, so an
#: operator supplies nothing new for alpha or beta. What an operator must KNOW
#: the reading cannot show: the control project is a THIRD deployment with its
#: own providers, certificate, backup and unit (Sheets P1-C5), and its first
#: accounts cannot be deleted in 1.15.0 (D2065). **This session takes a host
#: trip** (Runs 10 and 11), so the class is confirmed against a DEPLOYMENT in
#: the same session: `upgrade plan` on both projects, with the same two
#: declarations, before the first 1.15.0 deploy -- and a `major` there is a
#: stop condition.
#:
#: **Session 38 moves it to 38, all-or-nothing again** (D690): EIGHTEEN
#: requirements and eighteen claims -- `CLAIMS` 219 -> 237 and `OFFLINE_CLAIMS`
#: 74 -> 89, counted from the tuples rather than by hand (D1628) -- fifteen
#: declared offline, two EXTERNAL and one host, with every offline half written
#: in the run that built its piece (Runs 2-8) and every live half here. Two
#: families join the registry: `OPN` (the reconciler and the operations it
#: executes) and `LIFE` (a managed project's lifecycle). The two external
#: claims are the lifecycle a customer drove, read back through the control
#: project's route and the slot's own (D2174). **The migration's Run M3 adds
#: two more** (ADR 0262-0263, D2278), both offline: `REC-REHOME-001` and
#: `REC-STORE-001` -- requirements 330 -> 332, `CLAIMS` 237 -> 239,
#: `OFFLINE_CLAIMS` 89 -> 91. No version moves for them.
#:
#: **The session's subject is a managed project** -- one a customer creates,
#: sleeps, wakes, resizes, exports and deletes through `/v1` -- and six ADRs
#: are its shape. ADR 0256: a root unit on the host, the reconciler, claims each
#: operation from the control database through the control project's
#: container, executes it from a closed table with argv lists built from
#: validated members, opens no socket, never resumes an interrupted operation,
#: and acts only on declared slots. ADR 0257: slots -- keys, domains and provider
#: resources the operator prepares in advance, declared in `host.yaml` schema 4
#: with the host's `region`, their state derived from what exists, single-use.
#: ADR 0258: three compute profiles, `standard` the release defaults, and a
#: resize admitted before anything changes. ADR 0259: sleep and wake by request,
#: and an export whose one URL lives at most 900 seconds. ADR 0260: the first
#: administrator handed over by the hash of a token only the customer holds.
#: ADR 0261: a sixth Ledger status, `trial`, bounded to the session that
#: introduced its claims -- the six rows move to it here, and the session's
#: close resolves them.
#:
#: **No released migration** -- the reconciler's tables and functions are the
#: control set's `0004`. **Outputs move to v21** (`region` and
#: `compute.profile`, migrated from v20), **the project manifest to schema 10**
#: (`compute`, optional) and **the host manifest to schema 4** (`region`
#: required, `slots` optional; 2 and 3 still load); no capability, lock or
#: secret schema moves.
#:
#: **`VERSION` moves to `1.16.0`.** What moved: the control mode's project
#: routes, states and refusals, `operations.ACCEPTED_TYPES` (the six), the
#: export upload and the bounded presign in `services/auth-api`, so the image
#: moves and a deploy recreates `auth`, `storage` and `mcp`; the control set's
#: `0004`; manifest 10, outputs 21 and host 4; the REST flag's reader (D2172);
#: `project-runtime.sh stop|start`, `project-retire.sh --defer-provider`;
#: `bin/reconciler.sh`, `bin/slot.sh`, `bin/compute.sh`, `bin/operation.sh` and
#: the new verbs of `bin/project.sh`.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig as Sessions
#: 34-37 ran it: a git worktree at `c3eec1d`, the commit that IS deployed, and
#: a `tar`-piped copy of this working tree, both rendering the INSTALLED tree's
#: `project.example.yaml` (schema 9). With `--also document_schema_migratable
#: --also api_operation_added`: `bump minor`, **`requires minor`**, verdict
#: `ok`, `changes [api_operation_added, document_schema_migratable]`, `reasons
#: []`, `operator_digests_moved []`. Without the declarations: `requires patch`
#: -- the seventh release in a row whose price the command sees only by
#: declaration. **Three leaves differ**: `template_version` 1.15.0 -> 1.16.0,
#: `schema_version` 20 -> 21 and `compute.profile` absent -> `standard` (6,090 ->
#: 6,136 bytes); `region` is absent from both, because a render reads no host.
#: **ADR 0162 prices it a MINOR, and `1.16.0` is that floor exactly**: the
#: outputs move is MIGRATABLE, manifest 10 and host 4 invalidate no older
#: manifest, and no capability, lock or secret schema moves. What an operator
#: must KNOW the reading cannot show: `host.yaml` must move to schema 4 for a
#: deployed document to carry its region, a slot is provider resources made by
#: hand before a customer can create anything, and the reconciler is a new
#: root unit an operator installs (operator guide §20). **The trip** confirms
#: the class against a DEPLOYMENT: `upgrade plan` on every project, with the
#: same two declarations, before the first 1.16.0 deploy -- and a `major`
#: there is a stop condition.
#:
#: **Session 39 moves it to 39, all-or-nothing again** (D690): FOURTEEN
#: requirements and fourteen claims -- `CLAIMS` 239 -> 253 and `OFFLINE_CLAIMS`
#: 91 -> 101, counted from the tuples (D1628) -- ten declared offline, three
#: EXTERNAL and one host, every offline half written in the run that built its
#: piece (Runs 2-8) and every live half here. One family joins the registry:
#: `EP`, the public Postgres endpoints. The three external claims are a
#: customer at the live slot's public names, the public address scanned, and
#: the re-trial lifecycle read back through `/v1` (D2343); the host claim is
#: the edge, the firewall and the live slot's doors on the machine.
#:
#: **The session's subject is a project's public Postgres doors**, and three
#: ADRs are their shape. ADR 0268: the edge's `postgres` entrypoint on `:8432`,
#: published as 5432, routes TLS by name to two customer-only PgBouncers --
#: `pool.<domain>` in transaction mode, `direct.<domain>` in session mode --
#: never to the database or the platform's own pooler, with one certificate per
#: project by HTTP-01; only a slot has the facility. ADR 0269: two customer
#: roles, `customer_app` and `customer_admin`, the second creating in `public`
#: and nothing else, each a claimant on the connection budget, and a credential
#: set by its SCRAM verifier alone -- the password is generated on the
#: customer's workstation and never exists on the host or in the control plane.
#: ADR 0270: a refusal proof proves the DECISION against admission's own
#: reading, which a resize now records in its result.
#:
#: **No released migration** -- the doors' registry is the control set's
#: `0005`. **Outputs move to v22** (`database.public` and the two customer
#: roles, migrated from v21) and **the project manifest to schema 11**
#: (`database.public_endpoints`, optional); no host, capability, lock or secret
#: schema moves. The Ledger's six managed-project rows and the two endpoint rows
#: are `trial` again (ADR 0261), so the seven executed types are accepted.
#:
#: **`VERSION` moves to `1.17.0`.** What moved: the control mode's two routes,
#: `credential.rotate` accepted and the connection snippets in
#: `services/auth-api`, so the image moves and a deploy recreates `auth`,
#: `storage` and `mcp`; the edge's static configuration and dynamic baseline
#: (the edge is recreated once, its own sheet); the firewall policy (5432);
#: the compose model's two customer poolers and the runtime override's TCP
#: routers; the bootstrap's customer roles and budget; the control set's
#: `0005`; manifest 11 and outputs 22; `bin/customer-credentials.sh`,
#: `bin/endpoint.sh` and `deploy.sh`'s step 6f.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig as Sessions
#: 34-38 ran it: a git worktree at `efaef09`, the commit that IS deployed, and
#: a `tar`-piped copy of this working tree, both rendering the INSTALLED tree's
#: `project.example.yaml` (schema 10). With `--also document_schema_migratable
#: --also api_operation_added`: `bump minor`, **`requires minor`**, verdict
#: `ok`, `changes [api_operation_added, document_schema_migratable]`, `reasons
#: []`, `operator_digests_moved []`. Without the declarations: `requires patch`
#: -- the eighth release in a row whose price the command sees only by
#: declaration. **Five leaves differ**: `template_version` 1.16.0 -> 1.17.0,
#: `schema_version` 21 -> 22, `database.public.enabled` absent -> `false`, and
#: the two customer roles absent -> derived (6,136 -> 6,350 bytes).
#: **ADR 0162 prices it a MINOR, and `1.17.0` is that floor exactly**: the
#: outputs move is MIGRATABLE, manifest 11 invalidates no older manifest, and no capability,
#: lock or secret schema moves. What an operator must KNOW the reading cannot
#: show: the edge must be recreated with the new entrypoint before any deploy
#: through 39 (the deploy refuses otherwise, D2374), the host firewall must
#: admit 5432, and a slot's three DNS records -- its domain, `pool.` and
#: `direct.` -- are the operator's, grey, before its creation. **The trip**
#: confirms the class against a DEPLOYMENT: `upgrade plan` on every project,
#: with the same two declarations, before the first 1.17.0 deploy -- and a
#: `major` there is a stop condition.
#:
#: **Session 40 moves it to 40, all-or-nothing again** (D690): FOURTEEN
#: requirements and fourteen claims -- `CLAIMS` 253 -> 267 and `OFFLINE_CLAIMS`
#: 101 -> 111, counted from the tuples (D1628) -- ten declared offline, three
#: EXTERNAL and one host, every offline half written in the run that built its
#: piece (Runs 2-7) and every live half here. One family joins the registry:
#: `BR`, branches. The three external claims are a customer's branches of the
#: kept slot through `/v1` and its public names alone, and the re-earned
#: lifecycle and endpoints on a NEW slot (D2415, D2442); the host claim is the
#: branch on the machine -- bounded, charged, the parent untouched, back after
#: the reboot, nothing left after its deletion.
#:
#: **The session's subject is a project's branches**, and three ADRs are their
#: shape. ADR 0271: a branch is its own three-service cluster restored from its
#: parent's repository to the end of the archive or to a point inside the
#: window, re-keyed before its two doors open (every platform role NOLOGIN, its
#: own two customer verifiers), never backed up, one per project, charged
#: `small`'s 192 MiB. ADR 0272: a branch's expiry is a trigger -- the
#: reconciler requests ONE deletion on behalf of the member who set it, its
#: `origin` `expiry`. ADR 0273: the backups surface, a recorded reading served
#: with its age, a window or `could_not_determine`, never a guess.
#:
#: **No released migration** -- the branches' registry is the control set's
#: `0006` and `0007`. **No outputs, manifest, host, capability, lock or secret
#: schema moves** (outputs stay v22, the project manifest 11). The Ledger's six
#: managed-project rows, the two endpoint rows and the three branch rows are
#: `trial` (ADR 0261), so the eleven executed types are accepted.
#:
#: **`VERSION` moves to `1.18.0`.** What moved: the control mode's seven
#: branch, restore and backups routes and the operation read's `origin` in
#: `services/auth-api`, so the image moves and a deploy recreates `auth`,
#: `storage` and `mcp`; the reconciler's four branch handlers, its readings and
#: its expiry request (`bin/reconciler.py`, a restart of the unit);
#: `bin/branch-runtime.sh` and `infra/branch/compose.yaml`;
#: `bin/edge-network.sh`'s network verbs; the control set's `0006` and `0007`;
#: `bin/branch.sh`, `bin/project.sh backups` and `bin/slot.sh redeploy`.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git
#: worktree at `b0249ce`, the commit that IS deployed, and a `tar`-piped copy of
#: this working tree, both rendering the INSTALLED tree's `project.example.yaml`.
#: With `--also api_operation_added`: `bump minor`, **`requires minor`**,
#: verdict `ok`, `changes [api_operation_added]`, `reasons []`,
#: `operator_digests_moved []`. Without the declaration: `requires patch` --
#: the ninth release in a row whose price the command sees only by
#: declaration. **One leaf differs**: `template_version` 1.17.0 -> 1.18.0
#: (6,350 -> 6,350 bytes). **ADR 0162 prices it a MINOR, and `1.18.0` is that
#: floor exactly**: no manifest, outputs, capability, lock or
#: secret schema moves. What an operator must KNOW the reading cannot show: a
#: branch parent's two grey wildcard records (`*.pool.<domain>`,
#: `*.direct.<domain>`) before its first branch, the reconciler restarted
#: after the checkout moves (D2179), and a managed project moved to the
#: release by `slot.sh redeploy` with the reconciler stopped (D2443). **The
#: trip** confirms the class against a DEPLOYMENT: `upgrade plan` on every
#: project, with the same declaration, before the first 1.18.0 deploy -- and
#: a `major` there is a stop condition.
#:
#: **Session 41 moves it to 41, all-or-nothing again** (D690): SEVENTEEN
#: requirements and seventeen claims -- `CLAIMS` 267 -> 284 and `OFFLINE_CLAIMS`
#: 111 -> 121, counted from the tuples (D1628) -- ten declared offline, six
#: EXTERNAL and one host, every offline half written in the run that built its
#: piece (Runs 2-7) and every live half here. Two families join the registry:
#: `PLAN`, plans and entitlements, and `USE`, usage samples, notifications and
#: idle sleep. The external claims are the managed project's life re-earned a
#: third time on a NEW slot in a NEW organisation, the plans and their refusal,
#: the slot's usage, its idle sleep and its notifications, all through `/v1` and
#: the public names alone, and the branches of the kept slot with the backups
#: surface reading a window; the host claim is the branch back BY ITSELF after
#: the reboot, listed by the diagnosis account.
#:
#: **The session's subject is two repairs and the control plane's half of the
#: brief.** The repairs: the reconciler's backups reading computed from the
#: producer's own printed block (D2501, Run 2), and a branch's database image
#: resolved from its recorded tag and content digest at EVERY start, `ready`
#: written only once its door answers (D2504, D2503, Run 3). ADR 0274: plans
#: are a release table enforced before an operation exists -- Free one project
#: per organisation, one branch, every profile; the plan's refusal read
#: before the slot. ADR 0275: usage is a sample the reconciler records every
#: 300 s, a figure not read named and never a zero, and a notification is
#: written in the transaction that finishes an operation. ADR 0276: idle sleep
#: is a trigger -- opt-in, 15, 30 or 60 minutes, decided by the control set from
#: the samples, offered only while sleeping is (D2548).
#:
#: **No released migration** -- the plans, the samples, the notifications and
#: idle sleep are the control set's `0008`. **No outputs, manifest, host,
#: capability, lock or secret schema moves** (outputs stay v22, the project
#: manifest 11). Sixteen Ledger rows are `trial` (ADR 0261), so the eleven
#: executed types are accepted again.
#:
#: **`VERSION` moves to `1.19.0`.** What moved: the control mode's seven plan,
#: usage, notification and idle-sleep routes in `services/auth-api`, so the
#: image moves and a deploy recreates `auth`, `storage` and `mcp`; the
#: reconciler's usage pass, its idle request, its limit notices and its kept
#: branch-start output (`bin/reconciler.py`, a restart of the unit);
#: `bin/branch-runtime.py`'s image identity and door; `bin/backup.py usage`;
#: `bin/apg-diag.sh`'s branch listing (re-installed by hand, Sheet PV); the
#: control set's `0008`; `bin/plan.sh`, `bin/usage.sh`, `bin/notifications.sh`
#: and `bin/project.sh idle-sleep`.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git
#: worktree at `8cc3440`, the commit that IS deployed, and a `tar`-piped copy of
#: this working tree, both rendering the INSTALLED tree's `project.example.yaml`.
#: With `--also api_operation_added`: `bump minor`, **`requires minor`**,
#: verdict `ok`, `changes [api_operation_added]`, `reasons []`,
#: `operator_digests_moved []`. Without the declaration: `requires patch` --
#: the tenth release in a row whose price the command sees only by
#: declaration. **One leaf differs**: `template_version` 1.18.0 -> 1.19.0
#: (6,350 -> 6,350 bytes). **ADR 0162 prices it a MINOR, and `1.19.0` is that
#: floor exactly**: no manifest, outputs, capability, lock or
#: secret schema moves. What an operator must KNOW the reading cannot show: the
#: control project's eighth migration applied by its own deploy, the
#: reconciler restarted after the checkout moves (D2179), `apg-diag`
#: re-installed by hand, and a managed project moved to the release by
#: `slot.sh redeploy` with the reconciler stopped (D2443). **The trip**
#: confirms the class against a DEPLOYMENT: `upgrade plan` on every project,
#: with the same declaration, before the first 1.19.0 deploy -- and a `major`
#: there is a stop condition.
#:
#: **Session 42 moves it to 42, all-or-nothing again** (D690): EIGHTEEN
#: requirements and eighteen claims -- `CLAIMS` 284 -> 302 and `OFFLINE_CLAIMS`
#: 121 -> 133, counted from the tuples (D1628) -- twelve declared offline, four
#: EXTERNAL and two host, every offline half written in the run that built its
#: piece (Runs 2-7) and every live half here. One family joins the registry:
#: `INS`, the telemetry plane, `pg_stat_statements`, Query Insights and
#: monitoring; the three repairs go under the families their proofs already
#: live in (`DEP`, `LIFE-EXPORT`, `TEN`) and DB time under `USE`. The external
#: claims are the managed project's life re-earned a fourth time on a NEW slot
#: in a NEW organisation -- its probe samples written as they are taken (D2581)
#: -- its idle sleep, its notifications counted by outcome, and its insights
#: after a known workload, all through `/v1` and the public names alone; the
#: host claims are the plane bounded, charged and unreachable, and every
#: database loading the extension it refuses to `customer_app`.
#:
#: **The session's subject is three repairs and the stage's observability.**
#: The repairs: an edge attach that loses a race to another unit reads the
#: network again (D2558, Run 2), an upload's refusal carries the provider's code
#: (D2559), and the SQL reader keeps a `--` inside a literal (D2544). ADR 0277:
#: ClickStack bounded on the host, fed by each project's own collector, which
#: stamps the project over the payload's and exports through a bounded queue --
#: a project never waits for it. ADR 0278: `pg_stat_statements` on every
#: database and branch, `track=top`, utility statements off, revoked from
#: `PUBLIC`; the customer roles' statements sampled into the control database
#: and read as increases -- numbers, never advice. ADR 0279: monitoring is a
#: list of readings, each naming its table and column.
#:
#: **No released migration** -- the insight samples and DB time are the control
#: set's `0009`. **No outputs, manifest, host, capability, lock or secret
#: schema moves** (outputs stay v22, the project manifest 11, `host.yaml` 4).
#: Ten Ledger rows are `trial` (ADR 0261), so the eleven executed types are
#: accepted again.
#:
#: **`VERSION` moves to `1.20.0`.** What moved: `postgres`'s command gains five
#: `-c` flags, so the deploy RECREATES every database once (D2567), and the
#: bootstrap creates the extension and revokes it; each collector's logs
#: pipeline and the ingest network its `metrics` joins; `auth`, `storage` and
#: `mcp` export their request lines, so the image moves; the control mode's
#: insights and monitoring routes; the reconciler's insight sample and DB time
#: (a restart of the unit); `bin/telemetry.sh`, its unit and `infra/telemetry/`
#: (a platform plane, installed by hand, Sheet T1); `bin/edge-network.sh`;
#: `bin/apg-diag.sh`'s plane section (re-installed by hand, Sheet PV);
#: `bin/insights.sh` and `bin/monitoring.sh`.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git
#: worktree at `601a0ea`, the commit that IS deployed, and a `tar`-piped copy of
#: this working tree, both rendering the INSTALLED tree's `project.example.yaml`.
#: With `--also api_operation_added`: `bump minor`, **`requires minor`**,
#: verdict `ok`, `changes [api_operation_added, image_digest]`, `reasons []`,
#: `operator_digests_moved []`. Without the declaration: `requires patch` --
#: the lock's added images alone. **Two leaves differ**: `versions_lock_sha256`
#: and `template_version` 1.19.0 -> 1.20.0 (6,350 -> 6,350 bytes).
#: **ADR 0162 prices it a MINOR, and `1.20.0` is that floor exactly**: no manifest,
#: outputs, capability, lock or secret schema moves. What an operator must KNOW
#: the reading cannot show: every project's database restarted once by its
#: 1.20.0 deploy, the telemetry plane admitted and charged (3,552 MiB) by
#: `telemetry.sh up`, the control project's ninth migration applied by its own
#: deploy, the reconciler restarted after the checkout moves (D2179), `apg-diag`
#: re-installed by hand, and a managed project moved to the release by
#: `slot.sh redeploy` with the reconciler stopped (D2443). **The trip**
#: confirms the class against a DEPLOYMENT: `upgrade plan` on every project,
#: with the same declaration, before the first 1.20.0 deploy -- and a `major`
#: there is a stop condition.
#:
#: **Session 43 moves it to 43, all-or-nothing again** (D690): TWENTY
#: requirements and twenty claims -- `CLAIMS` 302 -> 322 and `OFFLINE_CLAIMS`
#: 133 -> 149, counted from the tuples (D1628) -- sixteen declared offline, three
#: EXTERNAL and one host, every offline half written in the run that built its
#: piece (Runs 2-7) and every live half here. Two families join the registry:
#: `CON`, the console and its session, and `SITE`, the public site; the three
#: repairs go under the families their proofs already live in (`INS`, `DEP`,
#: `OPS`) and the packaged CLI under `DX`. The external claims are a person's
#: walk in a real browser -- an invitation link to a working connection string,
#: through the console's public origin alone -- the console's policy and its
#: CSRF rule read live, and the site served byte for byte as this commit builds
#: it; the host claim is the console on the control project only, bounded, the
#: listeners unchanged. **The lifecycle and the branches are re-earned on the
#: trip** (D2714, the operator's 2026-10-20): the Sessions 38-42 proofs refuse a
#: record of another release, so they read a NEW slot's record at 1.21.0.
#:
#: **The session's subject is the web.** ADR 0280: the console, a fixed-route
#: static server on the control project's own host (`/`, `/accept`,
#: `/console/...`), every page a named `/v1` call, no SQL, no third-party byte.
#: ADR 0281: the console's session is two `__Host-` cookies, `HttpOnly`,
#: `Secure`, `SameSite=Strict`, honoured only with `X-Apg-Console: 1` and -- for
#: a write -- the console's own `Origin`; a bearer is unchanged. ADR 0282: the
#: invitation is a link whose token rides the fragment, and the factor's QR an
#: SVG data URI drawn by the server. ADR 0283: the public site on Cloudflare
#: Pages, built from the tree alone, deployed only after `contract` passed on
#: `main`. ADR 0284: the customer CLI packaged as `agentic-postgres-cli`,
#: published from a release tag by trusted publishing. The repairs: the plane's
#: status reads a container with no healthcheck (D2636), `provision-host.sh
#: --check` reads the launchers the install installs (D2637), and
#: `bootstrap-providers --apply` counts what it created (D2642).
#:
#: **No released migration. No outputs, manifest, host, capability, lock or
#: secret schema moves** (outputs stay v22, the project manifest 11, `host.yaml`
#: 4). The Ledger's `console` row was `trial` (ADR 0261) and `sql_editor`
#: `planned` for Session 44 -- `console` moved to `beta` at Session 43's close.
#:
#: **`VERSION` moves to `1.21.0`.** What moved: the `console` service, under a
#: Compose profile only the control project's render enables (`APG_CONSOLE=1`),
#: its router on the control host; the control mode's session routes in cookie
#: mode, the invitation's `accept_url` and the enrolment's `otpauth_qr` (segno
#: pinned), so the `services/auth-api` image moves; `bin/cloud.py`'s seam and
#: `bin/build-cli.py`; `site/` and `bin/build-site.py` (no host reads them);
#: `bin/telemetry.sh`, `bin/provision-host.sh` and `bin/bootstrap-providers.py`.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git
#: worktree at `77303e4`, the commit that IS deployed, and a `tar`-piped copy of
#: this working tree, both rendering the INSTALLED tree's `project.example.yaml`.
#: With `--also api_operation_added`: `bump minor`, **`requires minor`**,
#: verdict `ok`, `changes [api_operation_added, image_digest]`, `reasons []`,
#: `operator_digests_moved []`. Without the declaration: `requires patch` --
#: the lock's moved images alone. **Two leaves differ**: `versions_lock_sha256`
#: and `template_version` 1.20.0 -> 1.21.0 (6,350 -> 6,350 bytes). The
#: declaration is the console's cookie mode of the session routes and the two
#: answer fields: additive, so a client of 1.20.0 is unchanged.
#: **ADR 0162 prices it a MINOR, and `1.21.0` is that floor exactly**: no
#: manifest, outputs, capability, lock or secret schema moves. What an operator
#: must KNOW the reading cannot show: the control project's deploy starts the
#: console (a new container on the edge network, bounded at 192 MiB), the other
#: projects' deploys start nothing new, the reconciler is restarted after the
#: checkout moves (D2179), and a managed project moves to the release by
#: `slot.sh redeploy` with the reconciler stopped (D2443). **The trip**
#: confirms the class against a DEPLOYMENT: `upgrade plan` on every project,
#: with the same declaration, before the first 1.21.0 deploy -- and a `major`
#: there is a stop condition.
#:
#: **Session 44 moves it to 44, all-or-nothing again** (D690): NINE requirements
#: and nine claims -- `CLAIMS` 322 -> 331 and `OFFLINE_CLAIMS` 149 -> 155, counted
#: from the tuples (D1628) -- six declared offline, two EXTERNAL and one host,
#: every offline half written in the run that built its piece (Runs 2-6) and every
#: live half here. One family joins the registry: `SQL`, the browser SQL editor and
#: its relay. The external claims are the editor walk in a real browser -- a member
#: signed in, a project's editor used on both doors, PostgreSQL deciding every
#: refusal -- and the relay asked through its public name with clients a browser
#: could not be; the host claim is the relay on the control project only, bounded,
#: its whole log holding session lines alone. **The lifecycle and the branches are
#: re-earned on the trip** (D2748) and the console walk re-run (D2749): the
#: Sessions 38-43 proofs refuse a record of another release.
#:
#: **The session's subject is the SQL editor.** ADR 0285: the customer's own
#: PostgreSQL client, written here (`pg.js`: SCRAM-SHA-256 through WebCrypto, the
#: server's signature checked before AuthenticationOk, the simple query protocol,
#: a cancel as its own relay session), the password held only in the page, the
#: console's policy naming one more origin -- and ADR 0246's sentence amended: no
#: product surface runs SQL on the platform's side or holds a credential that
#: opens a project's data. ADR 0286: the relay, its own service on its own name
#: (`sql.<zone>`), authenticating nothing, holding nothing, reaching only door
#: names through the edge's own Postgres entrypoint, and recording none of what it
#: carries.
#:
#: **No released migration. No outputs, manifest, host, capability, lock or secret
#: schema moves** (outputs stay v22, the project manifest 11, `host.yaml` 4). The
#: Ledger's `sql_editor` row was `trial` (ADR 0261) -- `beta` at Session 44's
#: close; the `console` row has been `beta` since Session 43's close.
#:
#: **`VERSION` moves to `1.22.0`.** What moved: the `sql-relay` service, under a
#: Compose profile only the control project's render enables (`APG_SQL_RELAY=1`),
#: its router on its own name; the console's server (its policy from one rendered
#: origin, `pg.js` and `sql.js`), so the console image moves; the Postgres image's
#: apt pins (D2731 on `main` since Session 43's close), so **every project's
#: database restarts once** (D2747); `websockets` pinned for the relay's image.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git worktree at
#: `012ac06`, the commit that IS deployed, and a `tar`-piped copy of this working
#: tree, both rendering the INSTALLED tree's `project.example.yaml`: `bump minor`,
#: **`requires patch`**, verdict `ok`, `changes [image_digest]`, `reasons []`,
#: `operator_digests_moved []`; two leaves differ (`versions_lock_sha256`,
#: `template_version` 1.21.0 -> 1.22.0). No pair of rendered documents can see a
#: new service on the control project or a console policy, so the reading prices
#: the lock alone. **ADR 0162 prices it a MINOR, and `1.22.0` is proposed above
#: the reading's floor** (D2791) -- a new public surface is a feature, and minor
#: covers patch: no manifest, outputs, capability, lock or secret schema moves.
#: What an operator must KNOW the
#: reading cannot show: the control project's deploy starts the relay and its
#: certificate is the edge resolver's first issuance for `sql.<zone>`; every
#: project's database restarts once; the reconciler is restarted after the
#: checkout moves (D2179). **The trip** confirms the class against a DEPLOYMENT:
#: `upgrade plan` on every project before the first 1.22.0 deploy -- and a `major`
#: there is a stop condition.
#:
#: **Session 45 moves it to 45, all-or-nothing again** (D690): EIGHT requirements
#: and eight claims -- `CLAIMS` 331 -> 339 and `OFFLINE_CLAIMS` 155 -> 160, counted
#: from the tuples (D1628) -- five declared offline and three EXTERNAL, every
#: offline half written in the run that built its piece (Runs 2-6) and every live
#: half here. One family joins the registry: `UI`, the visual pass. The external
#: claims are the look walk in a real browser -- every site page and the console's
#: sign-in at two widths, nothing asked of another origin -- a woken project left
#: untouched, idle-slept, and notifications re-earned on the new slot's record
#: (`notifications_reearned_live`, D2857). **The lifecycle and the branches are
#: re-earned on the trip** (D2714, D2837: slot9-prod, in ONE attempt): the
#: `notifications` row is `trial` from this bump, naming that claim (ADR 0261),
#: until the close reads it beside Sessions 41's and 42's.
#:
#: **The session's subject is the look, and D2805.** ADR 0288: two typefaces made
#: once from `google/fonts` at a pinned commit and pinned by sha256, served from
#: our own origins under `font-src 'self'`; one token block in both stylesheets;
#: presentation by stylesheets and SVG attributes alone; the site's layout from a
#: closed vocabulary and its numbers from the builder; the console by hooks only.
#: ADR 0289: an absent request series reads zero only when the project's own store
#: shows the edge was read for it -- the reconciler's sampler alone changes, and
#: the control set's decision is unchanged.
#:
#: **No released migration and no control-set migration. No outputs, manifest,
#: host, capability, lock or secret schema moves** (outputs stay v22, the project
#: manifest 11, `host.yaml` 4). The Ledger's schema admits a row for Session 46.
#:
#: **`VERSION` moves to `1.23.0`.** What moved: the console's files (its
#: typefaces, favicon, stylesheet, `app.js`'s hooks), so the console image moves
#: on the control project; the reconciler's usage sampler (`usage_reading.
#: requests_below_400`); the site's builder and pages. No Postgres image moves, so
#: **no database restarts**.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git worktree at
#: `224b660`, the commit that IS deployed, and a `tar`-piped copy of this working
#: tree, both rendering the INSTALLED tree's `project.example.yaml`: `bump minor`,
#: **`requires patch`**, verdict `ok`, `changes []`, `reasons []`,
#: `operator_digests_moved []`; one leaf differs (`template_version` 1.22.0 ->
#: 1.23.0). No pair of rendered documents can see a console image or a sampler, so
#: the reading prices the template alone. **ADR 0162 prices it a MINOR, and
#: `1.23.0` is proposed above the reading's floor** -- a new look and a changed
#: decision input are features, and minor covers patch: no manifest, outputs,
#: capability, lock or secret schema moves. What an operator must KNOW the reading
#: cannot show: the control project's deploy recreates the console; no database
#: restarts; **the reconciler is restarted after the checkout moves** (D2179,
#: D2411) -- the repair of D2805 lives in it. **The trip** confirms the class
#: against a DEPLOYMENT: `upgrade plan` on every project before the first 1.23.0
#: deploy -- and a `major` there is a stop condition.
#:
#: **Session 46 moves it to 46, all-or-nothing again** (D690): NINE requirements
#: and nine claims -- `CLAIMS` 339 -> 348 and `OFFLINE_CLAIMS` 160 -> 164, counted
#: from the tuples (D1628) -- four declared offline, four EXTERNAL and one host,
#: every offline half written in the run that built its piece (Runs 2-6) and every
#: live half here. One family joins the registry: `JRN`, the journey. **ADR 0290
#: moves `documented_path` to `DX-HOSTED-001`**: the person's walk of the published
#: site from an invitation link, the product customers get; the clone walk keeps
#: its proof under a new claim, `appliance_documented_path`, `failed` on the
#: Session 25 record until a person walks the clone (D1935) -- a Session 12 claim
#: by its requirement, as `documented_path` is 46's now (D2927). **The lifecycle
#: and the branches are re-earned on the trip** (D2714, D2885): the lifecycle on
#: `slot11-prod`, continuing the journey's creation in ONE attempt (D2872).
#:
#: **The session's subject is the customer's journey.** ADR 0291: the console
#: creates a project -- the handoff token made in the page, only its SHA-256 sent,
#: shown once at acceptance -- and `apg project claim --token-file` claims with it,
#: choosing no creation. ADR 0292: the support bundle -- the reconciler records the
#: doctor's verdicts, never its evidence, and a member reads them with the project's
#: operations. ADR 0293: `control.sh status`, root and read-only, its states from the
#: service's own function. `doctor usage` reads the request series with ADR 0289's
#: witnesses.
#:
#: **No released migration; ONE control-set migration, `0010`** (the diagnostics
#: table and its two functions, on the control project's deploy). No outputs,
#: manifest, host, capability, lock or secret schema moves (outputs stay v22, the
#: project manifest 11, `host.yaml` 4).
#:
#: **`VERSION` moves to `1.24.0`.** What moved: the console's files (`create.js`,
#: `app.js`, `pages.json`), so the console image moves on the control project; the
#: auth service's control mode (the diagnostics route) and its shared
#: `control_states`; the reconciler (the diagnostics pass); `bin/control.sh`,
#: `bin/cloud.py` (`project diagnostics`, `claim --token-file`), `bin/doctor.py`;
#: the site's pages. No Postgres image moves, so **no database restarts**.
#:
#: **The price, read rather than chosen** (D704), by D1624's rig: a git worktree
#: at `4f4b207`, the commit that IS deployed, and a `tar`-piped copy of this
#: working tree, both rendering the INSTALLED tree's `project.example.yaml`:
#: `bump minor`, **`requires patch`**, verdict `ok`, `changes []`, `reasons []`,
#: `operator_digests_moved []`; one leaf differs (`template_version` 1.23.0 ->
#: 1.24.0). No pair of rendered documents can see a console image, a control-set
#: migration or a reconciler pass, so the reading prices the template alone.
#: **ADR 0162 prices it a MINOR, and `1.24.0` is proposed above the reading's
#: floor** -- a new way to create a project, a new route and a new operator verb
#: are features, and minor covers patch: no manifest, outputs, capability, lock
#: or secret schema moves. What an operator must KNOW the reading cannot show:
#: the control project's deploy applies control migration `0010` and recreates
#: the console; no database restarts; **the reconciler is restarted after the
#: checkout moves** (D2179, D2411) -- the diagnostics pass lives in it. **The
#: trip** confirms the class against a DEPLOYMENT: `upgrade plan` on every
#: project before the first 1.24.0 deploy -- and a `major` there is a stop
#: condition.
CURRENT_SESSION = 46

#: Repository root, resolved from this file rather than the caller's cwd so
#: that scripts and tests behave identically when invoked from anywhere
#: (runbook §8.5, "scripts work when invoked outside the repository root").
REPO_ROOT = Path(__file__).resolve().parents[2]


def template_version() -> str:
    """Return the template version.

    ``VERSION`` at the repository root is the single source of truth for
    ``outputs.json.template_version`` (plan decision G).
    """
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def acceptance_session() -> int:
    """The session whose registry policy is in force, honouring the override.

    **Here rather than in ``tests/conftest.py``, since Session 10 Run 10.** It
    was written there when the tests were its only reader; D526 gave it a second
    one. ``bin/render-acceptance-matrix.py`` hard-coded ``session == 1`` for
    "active", so ``docs/acceptance-matrix.md`` said *"placeholders owned by
    Session 2"* beside thirteen shipped, passing requirements -- a generated
    document asserting the opposite of the tree, which is the drift the generator
    exists to prevent. It said so for nine sessions and nobody read it.

    A second implementation in ``bin/`` would have been the same defect one layer
    up (D264), so the derivation moved here and ``tests/conftest.py`` wraps it.

    Raises ``ValueError`` on a non-integer override, and the caller decides what
    that means: a test run wants ``pytest.UsageError``, a generator wants to exit.
    """
    raw = os.environ.get("APG_ACCEPTANCE_SESSION")
    if raw is None:
        return CURRENT_SESSION
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"APG_ACCEPTANCE_SESSION must be an integer, got {raw!r}") from error


__all__ = ["CURRENT_SESSION", "REPO_ROOT", "acceptance_session", "template_version"]

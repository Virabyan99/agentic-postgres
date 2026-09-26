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
CURRENT_SESSION = 32

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

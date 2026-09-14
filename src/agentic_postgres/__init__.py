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
#: containers. Proposed here; Run 7's `upgrade plan` on the host is what
#: confirms it, and a `major` required there is a stop condition rather than a
#: number to write down.
CURRENT_SESSION = 25

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

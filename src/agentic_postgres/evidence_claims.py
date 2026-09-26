"""Named claims, and the acceptance requirements that prove them.

Session 2's evidence recorded ``{"tests": {"host_suite": "passed"}}`` — the name
of the suite that ran, not the name of anything it proved. A reader learning
that "the host suite passed" learns which command exited zero and nothing about
whether secrets stayed in, or whether two projects stayed apart. The plan's own
Run 8 check asks for ``.tests.isolation`` and ``.tests.secret_leakage``, keys no
version of the writer could produce.

A **claim** is a guarantee stated in the words the session is about. It is not a
new authority: it names acceptance-registry requirement IDs, and its verdict is
computed from the JUnit results of exactly the node IDs that registry lists. So
a requirement that gains a test gains it here too, and a claim cannot quietly
come to mean less than it did.

Three rules keep a claim from being weaker than it looks.

**Absence is not success.** A node ID the registry lists and the JUnit file does
not contain makes the claim ``not_run``, never ``passed``. A suite that stopped
collecting a test would otherwise report the claim green on what remained.

**A skip is not a pass.** ``requires_environment`` skips are how the deployment
tests behave in a checkout, which is correct there and worthless as evidence.

**Each claim is measured in one environment.** Its live proofs carry exactly one
of ``live_host`` or ``external``, so the mode that can prove it is derived
rather than declared, and a claim whose proofs straddle both environments is an
error rather than a half-measured verdict.
"""

from __future__ import annotations

import ast
import xml.etree.ElementTree as ElementTree
from functools import cache
from pathlib import Path

import yaml

from agentic_postgres import REPO_ROOT

TESTS_ROOT = REPO_ROOT / "tests"
REGISTRY_PATH = TESTS_ROOT / "acceptance-registry.yaml"

#: Gate mode -> the pytest marker its suite selects.
#:
#: The two LIVE modes, and only those: a marker is how a deployment mode picks
#: its proofs out of the suite. ``offline`` has no marker and is not here --
#: what identifies an offline claim is that it is DECLARED (`OFFLINE_CLAIMS`),
#: never that a marker is missing (ADR 0202). Iterate `ALL_MODES` when the
#: question is "which modes exist" and this when it is "what does a live mode
#: select".
MODE_MARKERS = {"host": "live_host", "external": "external"}

#: The third mode: a claim about a CHECKOUT rather than about a deployment.
#:
#: ADR 0202. Session 22's `apg dev` claims are the first of them -- there is no
#: host on which a disposable local cluster could be measured differently, so a
#: session whose work is a developer's own command has claims no deployment can
#: answer.
OFFLINE_MODE = "offline"

#: Every mode an evidence half can be written in.
ALL_MODES = (*MODE_MARKERS, OFFLINE_MODE)

#: Claims measured in a checkout, DECLARED here and nowhere else (ADR 0202).
#:
#: **Membership is the whole definition.** A claim with no live proof that is
#: not named here is still refused with the sentence it has always been refused
#: with -- so the twenty-one requirements `docs/scope-closure.md` §4 lists
#: become reportable one declaration at a time, each a decision, and never by
#: inference (D696).
#:
#: Inferring the mode from a missing marker is the cheap version of this and it
#: is wrong twice: it would make those twenty-one reportable without anyone
#: deciding to, and it would turn a claim whose live proofs stopped being
#: collected -- a marker removed, a module renamed, a gate variable unset --
#: into a green claim answered from a checkout. That is ADR 0195's substitution
#: in the most expensive place it could happen.
#:
#: **Session 22 declares the first four**, and they are the shape ADR 0202 was
#: written for: `apg dev` is a command a developer runs on their own machine,
#: and there is no host on which a disposable local cluster could be measured
#: differently. `dev_churn` includes `DEV-CI-001`, whose proof reads the
#: workflow file -- CI runs the round trip, and the assertion is that the
#: workflow says so, which is a property of this checkout.
#:
#: **Session 23 declares two more**, and they are a different shape from
#: Session 22's. `apg dev` had no host on which it could be measured
#: differently; `apg generate` does -- a deployment is exactly where a client
#: meets the surface it claims. What makes these two offline is narrower and
#: is worth stating: the IR, the emitter, the version rule, the command and
#: the toolchain are all properties OF THE ARTEFACT AND ITS GENERATOR, and
#: every one of them is settled by four committed files and a container. The
#: properties that need a deployment were split out into two separate HOST
#: claims rather than folded in, which is the line ADR 0202 exists to make
#: drawable at all.
#: Session 24 adds two, and the line runs where Session 23's did. What Studio
#: IS -- where it binds, what it holds, what it refuses, what it ships, how its
#: command behaves -- is settled by the source and by a rig this checkout can
#: build, and a production deployment would answer none of it differently. What
#: needed one was split into two HOST claims rather than folded in: a
#: revocation is about a running plane refusing the NEXT request, and a
#: boundary is about a refusal a deployed plane actually recorded. Docker is
#: required for both of these; a skip is not a pass.
OFFLINE_CLAIMS: frozenset[str] = frozenset(
    {
        "dev_environment",
        "dev_isolation",
        "dev_churn",
        "offline_evidence",
        "generated_client",
        "generated_client_toolchain",
        "studio_boundary",
        "studio_surface",
        # Session 25 (ADR 0207). The dispatcher's context variable, the
        # completion script, the walk's record reader, the documentation an
        # adopter reads, and the hardening matrix over the three DX surfaces.
        # Every proof behind these runs in a checkout: a dispatcher is a shell
        # script, a completion is a bash session this test starts, a record is
        # a JSON file, a document is a file in this tree, and the hardening
        # scan reads sources and a `.generated/.dev/<key>` this checkout builds
        # with Docker. A production deployment would answer none of it
        # differently -- and a skip is not a pass, so the gate refuses an
        # absent daemon as 24's does.
        "dx_context",
        "dx_walk_instrument",
        "dx_hardening",
        # Session 28 (ADR 0210, ADR 0214). Two, and the line runs where
        # Session 23's did. `project_set_release_record` is about what a
        # CHECKOUT'S lock file records and what the command that writes it
        # refuses: a deployment holds no project lock -- the lock is compiled
        # into the release and the record is a statement about the checkout
        # that froze the set -- so there is nothing a running system could
        # answer differently. `release_reading` is about a command that reads
        # `git` in a clone and prints; its subject IS the checkout, and the one
        # place it could be run against something else is CI, where there are
        # no tags (D1466) and the reading is therefore the third outcome.
        #
        # The session's THIRD claim is deliberately not here.
        # `agent_record_retention` is about two tables on a cluster that has
        # been written to for nine sessions, and a checkout cannot say what the
        # deployment is carrying nor that a prune removes a row of it. It is
        # `not_run` until Session 29 applies migration 0033 and sweeps, which
        # is the honest verdict rather than the convenient one.
        "project_set_release_record",
        "release_reading",
        # Session 30 (ADR 0218, ADR 0219). FOUR, which is one more than
        # any session has declared, and each is a property of a CHECKOUT
        # rather than of a running system. `exec_discipline` is an argv and
        # an AST scan over this tree. `release_reading_ref` is a command
        # that reads `git` in a clone and prints; its subject IS the
        # checkout. `contract_compile_output` is what a command writes into
        # a temporary directory and what two pages in this repository say.
        # `suite_shape` is the shape of this suite, which no deployment has
        # an opinion about. A deployment would answer none of the four
        # differently, and a claim about them that waited for a trip would
        # wait for a measurement nobody could take.
        #
        # The session's FIFTH claim is deliberately not here.
        # `studio_tenant_read` is about whether a running plane keeps two
        # subjects' rows apart through Studio's forwarder, and a checkout
        # cannot say. It is `not_run` until the trip sweeps (D1543).
        "exec_discipline",
        "release_reading_ref",
        "contract_compile_output",
        "suite_shape",
        # ADR 0220, added after Run 6 at the operator's instruction. The
        # verb's retry is proved against a FAKE `compose_mirror` -- a first
        # pass that fails and a second that does not, with the control
        # being two that fail -- and neither proof touches a network or a
        # container. What a production `mc` does with a flaked object is
        # not what this claims; what it claims is that a pass which
        # transferred what it could is completed before it is judged.
        "mirror_retry",
        # Session 31 (ADR 0221-0225). SIX, which is again one more than any
        # session has declared, and each is a property of a CHECKOUT rather
        # than of a running system.
        #
        # `capacity_declared` is a JSON Schema and an example document.
        # `capacity_reading` is a parser over fixture text and a reporter
        # over readings this suite builds -- the FIGURES are the host's and
        # the parsing is not. `admission_decision` is arithmetic over those
        # same synthesised readings, which is exactly what makes it testable
        # without a host: `decide` is pure by construction and the probe that
        # feeds it is a separate module for that reason. `process_limits` is
        # a compose model plus two containers this workstation can start --
        # and the fork proof runs under Docker here, on CI and on the host,
        # which is how D1602 was found in the first place. `telemetry_bounded`
        # is a rendered YAML file and an in-process meter provider.
        # `secret_kind_checked` is a pure function over values the test
        # builds, deliberately malformed.
        #
        # The session's other FOUR claims are deliberately not here:
        # `admission_live`, `usage_read`, `telemetry_read` and
        # `agent_write_method` each need a deployment to answer, and a claim
        # about them that waited for nothing would be a claim about a
        # checkout wearing a host's name.
        "capacity_declared",
        "capacity_reading",
        "admission_decision",
        "process_limits",
        "telemetry_bounded",
        "secret_kind_checked",
        # Session 32 (ADR 0226-0229). EIGHT, and each is a property of a
        # CHECKOUT. `capacity_ceilings` is a pure grouping over an inspect
        # payload this suite builds. `workflow_definition` is a schema and a
        # compiler over a committed lock. `workflow_substrate` is migration
        # 0034 under a real cluster this workstation starts -- the gate
        # refuses an absent daemon, and a skip is not a pass.
        # `workflow_worker` is the loop over fakes that RECORD. `workflow_
        # surface` is `create_app('auth')` with fakes behind it.
        # `workflow_command` is a command's closed tables and its argv.
        # `workflow_install` is an AST scan of the deploy and a statement's
        # shape, plus `apg dev up` on this machine. `workflow_reading` is three
        # readers over canned inputs and a rehearsal driven against a rig.
        #
        # The session's other FIVE claims are deliberately not here:
        # `ceilings_read`, `workflow_run`, `workflow_resume`,
        # `workflow_revocation` and `workflow_restore` each need a running
        # loop, a running plane or a restored drill -- and the one defect this
        # session found before its trip (D1696) was invisible to every offline
        # proof because the plane the loop was proved against was a fake.
        "capacity_ceilings",
        "workflow_definition",
        "workflow_substrate",
        "workflow_worker",
        "workflow_surface",
        "workflow_command",
        "workflow_install",
        "workflow_reading",
    }
)

#: Claim name -> the acceptance requirements whose tests prove it.
#:
#: A ``public_boundary`` claim over ``SEC-NET-001`` was written and removed: that
#: requirement's proofs include an IPv6 scan, the deployment host holds a global
#: IPv6 address, and no network available to run the external gate from has IPv6
#: transit. The claim could only ever come out ``failed`` — not because the
#: boundary is open but because nobody can look at it from here — and a claim
#: that cannot pass is a blocker invented by the evidence writer. The gap is
#: recorded as a divergence and in ``docs/host-baseline.md`` instead, which is
#: what an unmeasured surface deserves. Both modes stay implemented, so the day
#: a scan can be run from an IPv6 network the claim is three lines.
#:
#: Session 3 adds four. Not every Session 3 requirement is a claim, and the
#: reason is structural rather than editorial: a claim needs at least one proof
#: that runs against a deployment (see ``claim_mode``), and ``DBX-MIG-002`` and
#: ``DBX-MIG-003`` are about render determinism and preflight refusal — both
#: entirely properties of a checkout. They are proved, and they appear in the
#: acceptance matrix; they are not guarantees about a running system, so this
#: session's evidence does not name them as ones.
#:
#: Session 4 adds five, and two of them differ from the shape its plan drafted
#: (ADR 0045).
#:
#: ``direct_transport`` was drafted as ``DBX-001, DBX-003, DBX-005,
#: SEC-DBX-001`` — and ``claim_mode`` refuses it, correctly. The first two are
#: proved on the host by running Prisma Migrate and ``psql``; the last two are
#: proved from *off-host*, by failing to reach the same endpoint. One claim, two
#: environments, and neither half of the evidence could report a verdict on it.
#: So the guarantee is split where the measurement is: ``direct_transport`` is
#: "the direct endpoint works for the tools that need it" and
#: ``transport_boundary`` is "neither transport is reachable from outside".
#: ``transport_boundary`` is also the external claim ``public_boundary`` could
#: not be: its proofs scan IPv4 only, so unlike ``SEC-NET-001``'s it can pass
#: from a network with no IPv6 transit.
#:
#: ``transport_isolation`` is separate from ``database_isolation`` for a reason
#: that only appears when you follow the mechanism through. The plan says
#: ``database_isolation`` *gains* ``DEP-ISO-004``; ``claim_session`` is the max
#: of its requirements' sessions, so gaining a Session 4 requirement would move
#: the whole claim to Session 4 — and ``claims_through_session(3)`` would then
#: stop returning it. Session 3's gate would quietly stop recording a claim it
#: has been recording, and the jq expression its operator guide documents would
#: fail against freshly written evidence. Cumulative was meant to mean a later
#: session keeps proving an earlier one's guarantees, not that a later
#: requirement withdraws one from the earlier session's evidence.
CLAIMS: dict[str, tuple[str, ...]] = {
    # Session 22 (ADR 0202, ADR 0203). Six claims, and they do not all resolve
    # the same way -- which is the session's point rather than an accident.
    #
    # The first four are OFFLINE, declared in `OFFLINE_CLAIMS` above. `apg dev`
    # is a command a developer runs on their own machine; there is no host on
    # which a disposable local cluster could be measured differently, so a
    # claim about it that waited for a deployment would wait forever. Under ADR
    # 0202 that makes them offline only because they are NAMED, and a mistake
    # in either direction is caught: a marker on any of their proofs is
    # refused, and a fifth claim with no live proof that nobody declared is
    # still refused exactly as it always was.
    #
    # The last two are HOST claims and are deliberately NOT declared offline,
    # even though this session has no trip. Both are about a running plane --
    # whether the document's tool count is the one the container serves, and
    # whether an agent can read a tenant's rows -- and a checkout cannot answer
    # either. They are `not_run` at this session's close, and Session 24's trip
    # collects them (D1163). That is the honest verdict and the reason the
    # offline mode is a declaration rather than an inference: making these two
    # offline would take eight minutes of beta serving the wrong lock (D1152)
    # and report it green.
    "dev_environment": ("DEV-ENV-001", "DEV-SUBJECT-001", "DEV-SEED-001"),
    "dev_isolation": ("DEV-ISO-001",),
    "dev_churn": ("DEV-CHURN-001", "DEV-CI-001"),
    "offline_evidence": ("EVD-OFFLINE-001",),
    "plane_confirmed_count": ("OPS-PLANE-001",),
    "agent_tenant_read": ("AGT-TENANT-002",),
    # Session 23 (ADR 0204). Four claims, split two and two along the line
    # ADR 0202 exists to make drawable.
    #
    # `generated_client` and `generated_client_toolchain` are OFFLINE. Every
    # proof under them is about the artefact and its generator -- what the IR
    # reads, what the emitter writes, how the version is derived, what the
    # command refuses, and whether the emitted JavaScript computes the same
    # fingerprint Python does -- and each is settled by four committed files
    # and a container. Docker is required and a skip is not a pass: the gate
    # refuses an absent daemon exactly as Session 22's does.
    #
    # `generated_client_hash` and `agent_lock_reported` are HOST claims, and
    # the reason they are not declared offline is the whole point of the
    # session. A checkout cannot answer whether a deployment SERVES the
    # surface a client was generated for -- PostgREST serves a different
    # document to every role, so the question is about a running service and
    # a caller's identity, not about a file. Nor can it answer which lock a
    # running plane LOADED, which is the fact Session 21's trip spent eight
    # minutes not knowing (D1152). Each has one live proof on beta with alpha
    # as the control. They are `not_run` at this session's close, by design,
    # and Session 24's trip collects them.
    "generated_client": (
        "GEN-IR-001",
        "GEN-EMIT-001",
        "GEN-TYPES-001",
        "GEN-VERSION-001",
        "GEN-CMD-001",
    ),
    "generated_client_toolchain": ("GEN-TOOLCHAIN-001", "GEN-ENV-001"),
    "generated_client_hash": ("GEN-HASH-001",),
    "agent_lock_reported": ("AGT-META-001",),
    # Session 24 (ADR 0205). `apg studio`: a loopback page over a deployment,
    # holding the human's token and handing the browser a launch cookie.
    #
    # Four claims. `studio_boundary` is what Studio IS -- where it binds, what
    # it holds, what it ships, how its command behaves -- and `studio_surface`
    # is what it SHOWS: the four launch answers, the query builder, the audit
    # page and the session plane. Both are declared offline: every proof behind
    # them runs against the source or against a rig this checkout builds (a dev
    # cluster, the real auth application, the pinned PostgREST verifying its
    # published JWKS, the pinned Traefik in front).
    #
    # `studio_revocation` and `audit_boundary_reported` are NOT declared, and
    # the reason is the whole of what a live half is for: a revocation is about
    # a running plane refusing the next request, and a boundary is about a
    # refusal that plane actually recorded. Both are `not_run` at this
    # session's close, by design, and Run 7's trip collects them alongside
    # Sessions 22's and 23's four.
    #
    # `AGT-AUDIT-002` extends an existing family and still gets a claim of its
    # own: joining it into a Session 9 claim would re-date that claim, because
    # a claim's session is the MAX of its requirements' target sessions
    # (ADR 0089, D1150).
    "studio_boundary": (
        "STU-BIND-001",
        "STU-TOKEN-001",
        "STU-SUPPLY-001",
        "STU-CMD-001",
    ),
    "studio_surface": (
        "STU-SURFACE-001",
        "STU-QUERY-001",
        "STU-AUDIT-001",
        "STU-SESSION-001",
        "STU-ENV-001",
    ),
    "studio_revocation": ("STU-REVOKE-001",),
    "audit_boundary_reported": ("AGT-AUDIT-002",),
    # Session 25 (ADR 0207). The hardening pass, the second walk's instrument,
    # and the Stage 3 release.
    #
    # Four claims. `dx_context` is what the developer surface GAINED -- a
    # context variable the dispatcher applies by derivation and a completion
    # script that embeds nothing -- and `dx_walk_instrument` is what the walk
    # is MEASURED BY: the record reader and the documentation the walker
    # reads. They are separate because they fail separately; a completion
    # script that leaked an environment value and a guide that mislabelled a
    # step are not one fact about one thing.
    #
    # `dx_hardening` is `SEC-DX-001` alone and stays alone. Its last two node
    # ids are the ones that make it more than a scan: a matrix that names a
    # collectible proof per invariant per surface, and a check that the
    # offline sweep's own selector picks each one up. A security claim whose
    # coverage is asserted by its author is the shape D1236 names one level up.
    #
    # `stage_release` is a HOST claim and is deliberately NOT declared. The
    # offline half of `REL-STAGE-001` says the tree names one release
    # consistently and prices it; only a deployment can say whether it RUNS
    # that release and whether upgrading to it costs the operator anything.
    # Declaring it offline would let the tree grade its own release. It is
    # `not_run` at this session's close, by design, and Run 7's trip collects
    # it alongside the two standing Session 12 claims the walk and the
    # operator's file move.
    "dx_context": ("DX-CTX-001", "DX-COMPLETE-001"),
    "dx_walk_instrument": ("DX-WALK-001", "DX-DOC-001"),
    "dx_hardening": ("SEC-DX-001",),
    "stage_release": ("REL-STAGE-001",),
    # Session 28 (ADR 0210, ADR 0213, ADR 0214). Three claims, one per
    # requirement, which is ADR 0089's rule and not a shape chosen here.
    #
    # **Two offline and one host, and the split is the session's own
    # argument.** A project set's record of the release it was frozen against
    # is a property of a lock file in a checkout; the reading before a tag is a
    # property of a clone and of `git`. The agent record is a property of a
    # cluster that nine sessions of trips have written to, and the one thing
    # this session's rig could not supply is history nobody arranged (D940).
    #
    # **No claim is added for the rotation**, although it is this session's
    # headline act. `bootstrap_identity`, `api_authorization` and
    # `credential_rotation_planes` already exist and are `not_run`; Session
    # 29's trip moves them by running proofs that are already registered. A
    # claim about a rotation having been REHEARSED would be a claim about the
    # planning, which is what ADR 0163 exists to refuse -- and D1469 measured
    # that the cutover alone moves none of the three anyway, because each needs
    # four rotations and nine node ids.
    "project_set_release_record": ("DX-FOLLOWS-001",),
    "agent_record_retention": ("AGT-RETAIN-001",),
    "release_reading": ("REL-READ-001",),
    # Session 30 (ADR 0216-0220). SIX claims, landing with the constant
    # (D690), FIVE offline and one host -- measured 2026-09-19 against
    # `CLAIM_INTRODUCED_IN` and `OFFLINE_CLAIMS` rather than counted by hand
    # (D1595). The five are `contract_compile_output`, `exec_discipline`,
    # `mirror_retry`, `release_reading_ref` and `suite_shape`; the host one is
    # `studio_tenant_read`. No claim is added for the
    # signing-key rotation this session PERFORMS for the first time:
    # `bootstrap_identity`, `api_authorization` and
    # `credential_rotation_planes` already exist, the cutover moves ONE of
    # their nine node ids and closes none of them (D1469), and a claim
    # about an act having been carried out would be a claim about the
    # operator rather than about the system (ADR 0163).
    "exec_discipline": ("OPS-EXEC-001",),
    "release_reading_ref": ("REL-READ-002",),
    "contract_compile_output": ("CAP-COMPILE-001",),
    "suite_shape": ("EVD-SHAPE-001",),
    "studio_tenant_read": ("STU-QUERY-002",),
    # ADR 0220, after Run 6. Its own claim rather than a widening of an
    # existing one (ADR 0089, D1150): `backup_schedule` is about which
    # timers a project has and `disaster_kit` about what a kit holds, and
    # neither is about what a pass does when one object flakes.
    "mirror_retry": ("OPS-MIRROR-001",),
    # Session 31 (ADR 0221-0225). TEN claims, landing with the constant
    # (D690), six offline and four host. The session's subject is the node as
    # a finite resource: what it has, what has been claimed of it, whether one
    # more project fits, and what one project is actually using.
    #
    # The six OFFLINE ones are declared in `OFFLINE_CLAIMS` above and each is
    # a property of a CHECKOUT: a schema and an example document
    # (`capacity_declared`); a pure parser and a pure decision over readings
    # this suite synthesises (`capacity_reading`, `admission_decision`); a
    # compose model and two containers this workstation can start
    # (`process_limits`); a rendered collector configuration and an
    # in-process meter provider (`telemetry_bounded`); a pure check over
    # values built in the test (`secret_kind_checked`). A deployment would
    # answer none of the six differently.
    #
    # The four HOST ones are deliberately not declared. `admission_live` is
    # `decide` against a real declaration with a real committed total, and
    # the control beside it is what says the rule does not refuse everything
    # (D1611 shipped exactly that). `usage_read` is eight figures off two
    # clusters with nine sessions of data in them, compared with `free -m`
    # and `df -Pk`. `telemetry_read` is whether a metric crosses an OTLP
    # connection into a Prometheus that is routed nowhere -- which has never
    # happened in this product's life, because `mcp_metrics.configure` had no
    # production caller until this release. `agent_write_method` is Session
    # 9's pair, registered here by the orphan triage (D1597): the property is
    # ADR 0136's and no entry stated it, so three sessions of sweeps read
    # those two proofs' results into nothing.
    "capacity_declared": ("NODE-CAP-001",),
    "capacity_reading": ("NODE-READ-001",),
    "admission_decision": ("NODE-ADMIT-001",),
    "admission_live": ("NODE-ADMIT-002",),
    "process_limits": ("NODE-LIMIT-001",),
    "telemetry_bounded": ("OPS-TELEMETRY-001",),
    "telemetry_read": ("OPS-TELEMETRY-002",),
    "usage_read": ("NODE-USAGE-001",),
    "secret_kind_checked": ("SEC-KIND-001",),
    "agent_write_method": ("AGT-METHOD-001",),
    # Session 32 (ADR 0226-0229). THIRTEEN claims, landing with the constant
    # (D690), eight offline and five host -- counted from these tuples and
    # from `OFFLINE_CLAIMS`, never by hand (D1628). Each requirement is its
    # own claim (ADR 0089, D1150). The session's subject is durable work:
    # a definition compiled against the lock, a substrate of four tables
    # nobody may read, a loop in the auth process, three routes for agent
    # tokens, and the readers. The five HOST claims are the first time any
    # of it executes against a real plane.
    "capacity_ceilings": ("NODE-READ-002",),
    "ceilings_read": ("NODE-READ-003",),
    "workflow_definition": ("WF-DEF-001",),
    "workflow_substrate": ("WF-STATE-001",),
    "workflow_worker": ("WF-WORK-001",),
    "workflow_surface": ("WF-ROUTE-001",),
    "workflow_command": ("WF-CMD-001",),
    "workflow_install": ("WF-INSTALL-001",),
    "workflow_reading": ("WF-READ-001",),
    "workflow_run": ("WF-RUN-001",),
    "workflow_resume": ("WF-RESUME-001",),
    "workflow_revocation": ("WF-REVOKE-001",),
    "workflow_restore": ("REC-WF-001",),
    # Session 21 (ADR 0200, ADR 0201). Two claims: the agent plane opened to a
    # tenant's domain -- the vocabulary derived from the reviewed surface, the
    # roster compiled from the lock, a project's own capability manifest joined
    # into its lock -- and the scaffold that writes such a manifest. Each has
    # exactly one live node id per requirement, on beta, with alpha as the
    # control that declares nothing of its own and serves exactly the six.
    # The plan had `EVAL-HARNESS-002` joining `evaluation_harness` and
    # `REC-KIT-003` joining `disaster_kit`, and ADR 0089 refuses it: a claim's
    # session is the MAX of its requirements' target sessions, so joining a
    # Session 21 requirement re-dates a Session 16 and a Session 18 claim, and
    # `test_a_claim_resolves_to_the_session_that_introduced_it` said so on the
    # first run (D1150). Four claims, then: each requirement of this session
    # in a claim dated 21, the two widenings named for what they widen.
    "agent_tenant_surface": ("AGT-VOCAB-001", "AGT-ROSTER-001", "AGT-TENANT-001"),
    "agent_scaffold": ("AGT-INIT-001",),
    "project_evaluation_harness": ("EVAL-HARNESS-002",),
    "kit_read_at_a_later_release": ("REC-KIT-003",),
    # Session 20 (ADR 0198, ADR 0199). Three claims: what an adopter can now
    # add, the task domain restored, and the two readers that had two outcomes
    # where they needed three. Each has exactly one live node id, which is what
    # `claim_mode` requires -- a claim whose halves are all offline is a claim
    # about a checkout rather than about a deployment.
    "tenant_extension_point": ("TEN-SET-001", "TEN-SET-002", "TEN-SURF-001", "TEN-DOC-001"),
    "task_domain": ("API-TASK-001",),
    "honest_readers": ("OPS-READ-001", "OPS-READ-002"),
    "isolation": ("DEP-ISO-002",),
    "secret_leakage": ("SEC-SECRET-001", "SEC-SECRET-002"),
    "least_privilege": ("SEC-DB-001", "SEC-DB-002", "DBX-MIG-001"),
    "row_level_security": (
        "SEC-RLS-001",
        "SEC-VIEW-001",
        "SEC-FUNC-001",
        "SEC-DEFAULT-001",
        "SEC-OWNER-001",
    ),
    "database_isolation": ("DEP-ISO-003", "DBX-PG-003"),
    "boot_convergence": ("DEP-BOOT-001",),
    "pooled_transport": ("DBX-002", "DBX-POOL-001", "DBX-POOL-002", "DBX-POOL-003"),
    "direct_transport": ("DBX-001", "DBX-003"),
    "transport_boundary": ("DBX-005", "SEC-DBX-001"),
    "connection_tooling": ("DX-DB-001", "DX-DB-002"),
    "transport_isolation": ("DEP-ISO-004",),
    # Session 5 adds seven, and adds nothing to an existing claim.
    #
    # That is a decision rather than an oversight, and it is the paragraph above
    # applied a second time. `claim_session` is the maximum of a claim's
    # requirements' sessions, so giving `connection_tooling` a Session 5
    # requirement would move the whole claim to Session 5 and **withdraw it from
    # Session 4's evidence** -- and the jq expression
    # `docs/session-04-operator-guide.md` documents would fail against freshly
    # written Session 4 evidence with the product's behaviour unchanged. The
    # same applies to `database_isolation` and `transport_boundary`. Extending a
    # claim is right when the guarantee genuinely grew and wrong when a new
    # requirement merely neighbours an old one (D119).
    #
    # `api_authorization` and `public_api_boundary` are split for the reason
    # `direct_transport` and `transport_boundary` are. `SEC-DOCS-001` is proved
    # on the host, by reading where the credential was materialized and what the
    # containers hold; `SEC-API-001` is proved from off-host, by failing to
    # reach anything. One claim over both could be measured by neither half.
    "rest_surface": (
        "API-SCHEMA-001",
        "API-REST-001",
        "API-RPC-001",
        "API-ERR-001",
        "API-LIMIT-001",
    ),
    "api_contract": ("API-CONTRACT-001", "API-CACHE-001"),
    "api_authorization": ("SEC-ANON-001", "SEC-PRIV-001", "SEC-ROLE-001", "SEC-DOCS-001"),
    "bootstrap_identity": ("SEC-BOOT-001",),
    "api_isolation": ("DEP-ISO-005",),
    "api_tooling": ("DX-API-001",),
    "public_api_boundary": ("SEC-API-001",),
    # Session 6 adds seven, and every one of them names requirement IDs targeted
    # at Session 6. That sounds like a restatement of the obvious and is the
    # decision ADR 0089 records, because the plan's own §7 table did not.
    #
    # Three of the six IDs §2 introduced as "new" already existed:
    # `SEC-BOOT-001` (Session 5), `SEC-REV-001` (Session 9) and `DEP-ISO-003`
    # (Session 3). Prefix validity was checked; the directory was not. Taking
    # them literally was measured, and neither failure is loud:
    #
    #   `project_isolation: ("DEP-ISO-003",)` resolves to claim_session=3, so
    #   the Session 3, 4 and 5 gates each gain a claim whose proofs are Session
    #   6 auth tests. Run through the real `merge`, Session 3's evidence goes
    #   from exit 0 / `passed` to exit 5 / `failed` -- and the failing document
    #   is still written, so nobody gets an error to investigate.
    #
    #   `token_non_resurrection: ("SEC-REV-001",)` resolves to claim_session=9.
    #   `claims_for_mode("host", 6)` simply does not contain it. No error, no
    #   warning, no entry: the property §2 calls the session's sharpest would
    #   have been absent from the evidence and the gate would have exited 0.
    #
    # So the three are `DEP-ISO-006`, `SEC-REV-002` and `SEC-BOOT-002`.
    # `SEC-BOOT-002` is also a meaning split rather than only a session one:
    # `SEC-BOOT-001` is that the temporary bootstrap *issuer* holds the only
    # private key, and Session 6's property is that the first *administrator* is
    # created locally and exactly once. One ID for two guarantees is what D47
    # refused, read backwards.
    #
    # `admin_authorization` pairs API-ADMIN-001 with SEC-BOOT-002 because the
    # scope check is only meaningful while administrator creation is not an HTTP
    # capability -- an endpoint that mints administrators makes every scope
    # check decorative.
    #
    # `key_ownership` carries SEC-KEY-002, whose transition is deliberately
    # unexercised this session (ADR 0088). Its live proofs assert the
    # invariants that hold without starting a rotation; the convergence itself
    # is recorded in the run log as unproved rather than claimed here.
    "token_contract": ("SEC-JWT-001", "API-AUTH-002"),
    "key_ownership": ("SEC-KEY-001", "SEC-KEY-002"),
    "credential_storage": ("SEC-CRED-001", "SEC-CRED-002"),
    "identity_endpoints": ("API-AUTH-001",),
    "admin_authorization": ("API-ADMIN-001", "SEC-BOOT-002"),
    "token_non_resurrection": ("SEC-REV-002",),
    "project_isolation": ("DEP-ISO-006",),
    # Session 7 added nothing here in Run 1, and that was a measured constraint
    # rather than an omission (D331).
    #
    # Run 1 wrote `connection_budget_division` and `storage_scope_class` and the
    # model refused both: `claim_mode` raises *"has no live proof: every test it
    # names runs in a checkout, so no deployment is being measured"*. Run 1's
    # guarantees are the connection division and the scope partition, and both
    # are proved entirely offline -- so neither is a claim under ADR 0045, which
    # shapes a claim by where it can be measured. **They are still not here**,
    # for the same reason, and their tests exist and pass as ordinary suite
    # properties.
    #
    # Run 9 adds the nine below, and every one names requirement IDs targeted at
    # Session 7 and only at Session 7 (ADR 0089). That is not a restatement of
    # the obvious: `claim_session` derives from `max()`, so a single older ID
    # mixed in either drags the whole claim into an earlier session's evidence or
    # hides it from this one's gate, and both failures are silent.
    #
    # One claim per guarantee (D47). `object_completion` carries two IDs because
    # "an object becomes available only when the provider has verified it, and
    # only within the bound this deployment published" is one guarantee measured
    # from two sides; `storage_credentials` carries two for the same reason --
    # what the runtimes hold, and what the credential they hold can do.
    #
    # **Every one of these will report `not_run` until a host trip.** All eleven
    # requirements are proved by `live_host` tests that have never executed in
    # any environment, because no deployment has ever started a storage
    # container. D282 is Session 6 writing this sentence one run before its own
    # trip found nine defects, and it is written here for the same reason: a
    # claim that has never been measured must not be mistaken for one that
    # passed.
    "object_ownership": ("STO-OWN-001",),
    "object_keys": ("STO-KEY-001",),
    "presigned_url_containment": ("STO-URL-001",),
    "object_completion": ("STO-COMPLETE-001", "STO-BOUND-001"),
    "tombstone_ordering": ("STO-TOMB-001",),
    "cleanup_convergence": ("STO-CLEAN-001",),
    "storage_authorization": ("STO-AGENT-001",),
    "storage_credentials": ("STO-SECRET-001", "STO-CRED-001"),
    "storage_isolation": ("DEP-ISO-007",),
    # The one Session 7 claim measured from off-host, which is what makes the
    # gate's external mode meaningful for this session rather than ceremonial.
    "public_storage_boundary": ("STO-PUBLIC-001",),
    # Session 8 adds eight, and ADR 0132 is the decision behind their shape.
    #
    # Run 6 replaced five placeholders with CONTRACT tests, which was right --
    # they are contract properties -- and left the session with no claim it could
    # make. Measured before anything was written: every node id the six Session 8
    # requirements named carried no environment marker, and a claim over two of
    # them was refused *"has no live proof: every test it names runs in a
    # checkout"*. The control was `object_ownership`, which resolves to `host`.
    #
    # So four requirements gained live proofs rather than twins -- the guarantee
    # did not change, only where it is measured -- and four new ids carry
    # guarantees that are about a deployment and did not exist offline.
    #
    # `agent_query_construction` carries two ids for the reason
    # `object_completion` does: *no caller input becomes syntax* is ONE guarantee
    # measured from two sides, the builder's and the attacker's.
    #
    # **`AGT-DRIFT-001` is deliberately absent.** Its guarantee is a property of
    # the compiler and is complete in a checkout, so under ADR 0045 it is not a
    # claim. D331 is the precedent and it is exactly this situation: Session 7's
    # Run 1 wrote `connection_budget_division` and `storage_scope_class`, the
    # model refused both, and they stayed out as ordinary suite properties rather
    # than being given a host arm to qualify them.
    #
    # **Every one of these reports `not_run` until a host trip.** No deployment
    # has started an MCP container anywhere. D282 wrote this sentence one run
    # before Session 6's trip found nine defects; a claim that has never been
    # measured must not be mistaken for one that passed.
    "agent_reads": ("AGT-READ-001",),
    "agent_query_construction": ("AGT-SQL-001", "SEC-INJ-001"),
    "agent_scopes": ("AGT-SCOPE-001",),
    "agent_budgets": ("AGT-BUDGET-001",),
    "agent_surface": ("AGT-PLANE-001",),
    "agent_authentication": ("AGT-TOKEN-001",),
    "agent_credentials": ("AGT-CRED-001",),
    # The one measured from off-host, and the reason Session 8's external mode
    # is not ceremonial.
    "public_agent_boundary": ("AGT-PUBLIC-001",),
    # Session 9 adds five, one per requirement, and every one names an ID
    # targeted at Session 9 and only at Session 9 (ADR 0089). No ID is new: all
    # five have existed since Session 1 as placeholders, and D279 is why that was
    # checked rather than assumed -- three of Session 6's six "new" IDs were
    # already taken, and because `claim_session` derives from `max()`, one would
    # have turned three earlier sessions' evidence red while the other vanished
    # from the gate with no error at all.
    #
    # **Five claims rather than three**, and the splits are decisions:
    #
    #   `agent_audit_record` and `agent_audit_fails_closed` are separate because
    #   they are different guarantees, not one guarantee measured twice. The
    #   first is *what is recorded* -- two records from two routes that agree
    #   (D480) -- and the second is *what happens when recording is impossible*,
    #   which ADR 0141 decides asymmetrically: a write fails closed and a read
    #   does not. Folding them would make the asymmetry unreportable, and D119 is
    #   the rule: extending a claim is right when the guarantee genuinely grew
    #   and wrong when a new requirement merely neighbours an old one.
    #
    #   `agent_revocation` is NOT extended into `token_non_resurrection`, which
    #   is Session 6's `SEC-REV-002`. Extending it would retroactively change
    #   what Session 6's evidence asserts, and `claim_session` would move the
    #   claim to 9 and drop it out of Session 6's gate silently -- the exact
    #   failure D279 measured.
    #
    # **Every one of these carries at least one live node id**, which `claim_mode`
    # requires and which shaped two of Run 8's tests rather than the other way
    # round. `AGT-AUDITFAIL-001` had only offline proofs, and its live arm --
    # withdrawing a real grant so the write path fails through the real transport
    # -- was written because the alternative was a claim that read as
    # deployment-measured while its central property was not. `SEC-REV-001`'s
    # one-token-three-requests arm was named as live-host by Run 7 and did not
    # exist; registering a claim against a test nobody had written is D211-D214's
    # shape, so Run 8 wrote it before naming it here.
    #
    # **Every one of these reports `not_run` until a host trip**, and two
    # migrations (0019 and 0020) are released and applied on no cluster, so they
    # would report `failed` on a cluster that has not been migrated. D282's
    # sentence stands: a claim that has never been measured must not be mistaken
    # for one that passed.
    "agent_writes": ("AGT-WRITE-001",),
    "agent_audit_record": ("AGT-AUDIT-001",),
    "agent_audit_fails_closed": ("AGT-AUDITFAIL-001",),
    "agent_revocation": ("SEC-REV-001",),
    "agent_parameter_boundary": ("SEC-PARAM-001",),
    # Session 10 adds five, one per requirement, and extends nothing.
    #
    # **No ID is new**, and that was checked rather than assumed (D279, ADR 0089):
    # all five have existed since Session 1 as placeholders. Three of Session 6's
    # six "new" IDs turned out to be already taken, and because `claim_session`
    # derives from `max()`, one would have turned three earlier sessions' evidence
    # red while the other vanished from the gate with no error at all. The five
    # claim NAMES were grepped for too, for the same reason one layer up.
    #
    # **Five claims rather than one `recovery`**, and the splits are the same
    # decision D119 governs -- extending a claim is right when the guarantee
    # genuinely grew and wrong when a new requirement merely neighbours an old
    # one. These are five different guarantees and each fails on its own:
    #
    #   `point_in_time_recovery` is *a restore to a chosen instant happens*.
    #   `restore_isolation` is *and it cannot have touched production* -- which is
    #   true or false independently of whether the restore worked at all, and is
    #   the one an operator needs before running the drill rather than after.
    #   `restore_verification` is *and the restored instance was asked* -- ADR
    #   0152's premise that a restore which cannot be verified is a failed
    #   restore, and the half that would silently disappear if it were folded into
    #   the first.
    #   `recovery_evidence` is *and the numbers were measured rather than
    #   written* -- D529's prohibition, which is about the report and not about
    #   the recovery.
    #   `wal_archiving_signal` is P1 and is about the interval between backups,
    #   not about a restore at all.
    #
    # **All five are `host`**, and no external arm was invented to make the shape
    # symmetric: there is nothing about a backup repository a stranger on the
    # public internet can measure, and an external arm would be a proof reaching
    # an end state by a route the product does not take (ADR 0065).
    #
    # `restore_isolation` and `restore_verification` name **offline arms beside
    # their live ones**, and `claim_mode` resolves them to `host` because only
    # `live_host` is a mode marker. That is deliberate: D523 makes `REC-SAFE-001`
    # two proofs, and the offline one -- the rig driving the command with a
    # stubbed `docker`, with a control arm proving a wrong derivation is caught --
    # is the arm that has actually executed.
    #
    # **Every one of these reports `not_run` until a host trip**, and unlike
    # Session 9's five they are blocked on more than a deploy: an operator has to
    # create an R2 bucket and issue a token out of band, and the first full backup
    # is a command at a TTY. D282's sentence stands -- a claim that has never been
    # measured must not be mistaken for one that passed.
    "point_in_time_recovery": ("REC-PITR-001",),
    "restore_isolation": ("REC-SAFE-001",),
    "restore_verification": ("REC-SMOKE-001",),
    "recovery_evidence": ("REC-EVID-001",),
    "wal_archiving_signal": ("REC-WAL-001",),
    # Session 11 adds four, and deliberately does not claim a fifth.
    #
    # **The ordering here is enforced, not remembered** (D670, D672).
    # `test_every_claim_belongs_to_a_session_the_release_has_reached` refuses a
    # claim whose `claim_session` exceeds `CURRENT_SESSION`, so these could not
    # exist until that moved to 11 -- which Run 9 did, because
    # `test_every_later_requirement_has_a_placeholder` refuses to let the node
    # ids be activated before it either, and `deploy.sh` refuses
    # `--through-session 11` above it. Three guards, one forced order.
    #
    # `deployment_preflight` and `deployment_convergence` are separate rather
    # than one "deployment" claim, and D119 is the rule: a refusal that changes
    # nothing and a redeploy that preserves everything are different guarantees,
    # not one guarantee measured twice. The first is about a deploy that never
    # starts; the second about one that runs a second time.
    #
    # **`DEP-001` is absent, deliberately** (D669). Its offline half is proved
    # and its live half was not run: Run 8's rehearsal reached the host baseline
    # and the edge plane on a genuinely fresh machine and stopped, because leg 3
    # needed scratch provider state to exercise commands the live host already
    # runs on every deploy. A claim on the offline half alone would promise a
    # deployment nobody performed. Session 12 inherits it beside `DX-001`.
    "deployment_preflight": ("DEP-PRE-001",),
    "deployment_convergence": ("DEP-002",),
    "operational_diagnosis": ("OPS-001",),
    "log_correlation": ("OPS-LOG-001",),
    # Session 12 adds three, and every one is a claim whose live half is an
    # operator declaration rather than an observation.
    #
    # **`DEP-ISO-001` joins `isolation` rather than founding a fourth isolation
    # claim.** ADR 0089: a claim is a guarantee, not a file. `isolation` already
    # answers "these two projects do not reach each other"; the matrix makes that
    # answer complete by asserting what is ALLOWED to be shared, which is the
    # half that was missing (D689). A separate claim would report the same
    # guarantee twice and let one of them be green while the other was not.
    #
    # **`documented_path` and `fresh_host` are separate, and D119 is the rule.**
    # "The path resolves and needs no source edit" and "a host that started empty
    # reached a working deployment" are different guarantees, measured
    # differently, failing for different reasons. One claim over both would be
    # provable by neither half alone and reported as though it were.
    #
    # **Each will report `not_run` until its declaration is supplied**, and that
    # is the intended state rather than a gap to be closed by weakening them:
    # an offline half proves a path resolves, never that anybody walked it.
    "isolation_matrix": ("DEP-ISO-001",),
    "project_removal": ("DEP-REMOVE-001",),
    "documented_path": ("DX-001",),
    "fresh_host": ("DEP-001",),
    # -----------------------------------------------------------------------
    # Session 13 Run 6 -- the retrofit D697 asked for, as far as the model allows
    # -----------------------------------------------------------------------
    #
    # **These are dated to Sessions 2, 3 and 4, not to Session 13**, because
    # `claim_session` is the max of their requirements' sessions and those
    # requirements have not moved. That is the point: Session 2's evidence has
    # never said whether its own host is hardened, and dating these to 13 would
    # leave that true forever while looking closed.
    #
    # **It costs those gates nothing they were not already doing.** Measured
    # before any of this was written: sessions 2, 3 and 4 already carry claims
    # (2, 4 and 5 of them), so each already runs the claims path and each already
    # has the mode these need. A claim here is an extra row in a document that is
    # already produced -- not a new obligation on a gate that produced none.
    #
    # **One claim per requirement, and that is the conservative answer rather
    # than the lazy one.** Grouping two requirements asserts they are one
    # guarantee, which is a claim about the product that nothing here makes. Not
    # grouping asserts nothing. Single-requirement claims are already four of the
    # entries above.
    # Session 13. Four claims, four requirements, each with an offline half that
    # runs in a checkout and a live half gated on `APG_LIVE_HOST`. `claim_mode`
    # resolves each to `host` because that is the only environment marker any of
    # their node ids carries -- the offline halves carry none, which is what lets
    # one claim hold both.
    "release_version": ("REL-VER-001",),
    "upgrade_compatibility": ("REL-COMPAT-001",),
    "upgrade_plan": ("REL-PLAN-001",),
    "operator_front_door": ("REL-CLI-001",),
    "document_kinds": ("CFG-016",),
    "provider_convergence": ("DEP-PROV-001",),
    "release_immutability": ("DEP-REL-001",),
    "docker_api_boundary": ("SEC-DOCKER-001",),
    "host_baseline": ("SEC-HOST-001",),
    "log_redaction": ("SEC-LOG-001",),
    "published_ports": ("SEC-NET-002",),
    "database_extensions": ("DBX-PG-001",),
    "driver_round_trip": ("DBX-004",),
    "port_allocation": ("DBX-PORT-001",),
    "runtime_role_privilege": ("SEC-DBX-002",),
    "pooled_state_reset": ("SEC-DBX-003",),
    "credential_rotation_planes": ("SEC-DBX-004",),
    #
    # Session 14's four, and they are four rather than one for ADR 0045's
    # reason. `metrics_surface` is proved by reading a route; `alerting` by
    # reading a store that is routed nowhere; `telemetry_redaction` by planting
    # a value and failing to find it; `capacity_envelope` by comparing a
    # document to a deployment. One claim over all four would be measured by
    # none of those halves, and a single failure would say only that
    # observability was wrong.
    "metrics_surface": ("OPS-METRIC-001",),
    "alerting": ("OPS-ALERT-001",),
    "telemetry_redaction": ("OPS-REDACT-001",),
    "capacity_envelope": ("CAP-ENV-001",),
    #
    # Session 15. The identity lifecycle, and every one of the four carries a
    # live node id because `claim_mode` refuses a claim whose every proof is
    # offline -- rightly: an identity plane that has never been exercised
    # through its own front door has not been exercised (ADR 0065/0066).
    #
    # `session_lifecycle` holds BOTH session requirements, because they are one
    # subject: a session is a refresh family, and listing or ending one is the
    # same object seen from the other end (ADR 0171). Splitting them would make
    # two claims that can never disagree.
    "session_lifecycle": ("IDN-SESSION-001", "IDN-SESSION-002"),
    "agent_credential_lifecycle": ("IDN-AGENT-001",),
    "password_reset": ("IDN-RESET-001",),
    #
    # **NOT `credential_rotation_planes`**, which is an existing `not_run` claim
    # describing an EVENT an operator performs. This one describes a SURFACE the
    # repository ships. Two claims one word apart is how D696 starts, so they
    # are named apart deliberately.
    "credential_rotation_surface": ("IDN-ROT-001",),
    # Session 16 adds seven, all `host`, in Run 9's commit with the constant
    # (D690). **Every one's live half was written in Run 9 and none had executed
    # when this was written** (D938): Runs 2-8 proved their planes in a checkout
    # and wrote nothing that reaches the deployment, so all seven report
    # `not_run` until Run 10's trip, and that is the evidence model working.
    #
    # `capability_governance` holds BOTH the version and the risk requirement,
    # because they are one declaration: three fields arriving at one manifest
    # version (ADR 0177), read by one loader, refused together. Splitting them
    # would make two claims that cannot disagree.
    #
    # `agent_dry_run` holds the rehearsal AND the approval refusal, for the
    # reason ADR 0182 shipped them together: both are what a write does before
    # it is dialled, declared side by side at the same manifest version, with
    # opposite polarity (D925). `evaluation_harness` is one requirement covering
    # the harness and its CI enforcement (plan §2): a claim purely about CI
    # would have no live half in either mode that exists.
    "capability_governance": ("AGT-CAPVER-001", "AGT-RISK-001"),
    "denial_taxonomy": ("AGT-DENIAL-001",),
    "agent_quota": ("AGT-QUOTA-001",),
    "agent_idempotency": ("AGT-IDEM-001",),
    "agent_dry_run": ("AGT-DRYRUN-001", "AGT-APPROVE-001"),
    "capability_profile": ("AGT-PROFILE-001",),
    "evaluation_harness": ("EVAL-HARNESS-001",),
    # -----------------------------------------------------------------------
    # Session 17 -- multi-project operation (ADR 0185, 0186, 0187)
    # -----------------------------------------------------------------------
    #
    # Four claims, all `host`, landing with the constant (D690). Every live half
    # was written in the run that built its plane (Runs 2-5), not here -- D938's
    # lesson applied. `project_lifecycle` holds the field AND the reading of it,
    # because a lifecycle nothing acts on is one declaration (ADR 0186);
    # `project_retirement` holds what the verb removes AND what it never
    # touches, because ADR 0187 is one decision with two halves.
    #
    # `backup_schedule` is the claim that goes red on the deployment as it was
    # on 2026-09-04 (D944), and `project_removal` -- Session 12's -- closes on
    # this session's trip through the record the retirement verb writes.
    "fleet_inventory": ("FLEET-INV-001", "FLEET-INV-002"),
    "project_lifecycle": ("FLEET-LIFE-001", "FLEET-EXPIRE-001"),
    "project_retirement": ("FLEET-RETIRE-001", "FLEET-RETIRE-002"),
    "backup_schedule": ("FLEET-BACKUP-001",),
    # -----------------------------------------------------------------------
    # Session 18 -- independent recovery (ADR 0188-0193)
    # -----------------------------------------------------------------------
    #
    # Four claims, all `host`, landing with the constant (D690). The live
    # halves were written at the bump rather than in the runs that built each
    # plane (D1020), gated on four declarations the trip brings back -- the
    # kit, the replacement's document, the restore record, the rehearsal
    # records -- so three of the four report `not_run` until Run 6, and
    # `independent_repository` until both projects are mirrored.
    "independent_repository": ("REC-REPO-001", "REC-REPO-002", "REC-REPO-003"),
    "disaster_kit": ("REC-KIT-001", "REC-KIT-002"),
    "replacement_host_restore": ("REC-NODE-001", "REC-NODE-002"),
    "failure_rehearsal": (
        "OPS-REHEARSE-001",
        "OPS-REHEARSE-002",
        "OPS-REHEARSE-003",
        "OPS-REHEARSE-004",
        "OPS-REHEARSE-005",
        "OPS-REHEARSE-006",
        "OPS-REHEARSE-007",
        "OPS-REHEARSE-008",
    ),
    #
    # **Three of the sixteen candidates are deliberately NOT here**, and each has
    # a different reason. They stay in `UNCLAIMED_BY_HISTORY`, which now records
    # why rather than only that.
    #
    # `SEC-NET-001` -- a `public_boundary` claim over it was written and removed
    # once already (the note above this dict): its proofs include an IPv6 scan no
    # available network can run, so the claim could only ever come out `failed`.
    # **And a second reason arrived with the measurement**: Session 2 carries no
    # external claim today, so adding one would make `--external-input` newly
    # required for every Session 2 merge.
    #
    # `OPS-HEALTH-001` and `SEC-TLS-001` -- each carries **both** `live_host` and
    # `external` markers, and `claim_mode` refuses a claim spanning two modes
    # because one evidence half would have to report a verdict on tests it could
    # not run. ADR 0045 split `direct_transport` from `transport_boundary` for
    # exactly this, and that split worked because the halves were **separate
    # requirements**. Here it is one requirement whose node ids span two modes,
    # and a claim names requirements rather than node ids -- so there is no
    # subset to claim. **Splitting these means splitting the requirement**, which
    # renumbers a Session 2 contract, and that is a decision with a blast radius
    # this run has no reason to accept.
}

#: Worst-first, so combining two observations of one test is a max().
_SEVERITY = ("failed", "skipped", "passed")


class ClaimError(RuntimeError):
    """A claim cannot be resolved. No verdict is produced for it."""


# ---------------------------------------------------------------------------
# The registry side
# ---------------------------------------------------------------------------


@cache
def _registry() -> dict[str, dict[str, object]]:
    entries = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not entries:
        raise ClaimError(f"{REGISTRY_PATH} is empty")
    return {
        entry["id"]: {
            "nodeids": tuple(entry.get("test_nodeids") or ()),
            "target_session": entry["target_session"],
        }
        for entry in entries
    }


def _requirement(requirement: str) -> dict[str, object]:
    try:
        return _registry()[requirement]
    except KeyError:
        raise ClaimError(f"{requirement} is not in the acceptance registry") from None


def requirement_nodeids(requirement: str) -> tuple[str, ...]:
    nodeids = _requirement(requirement)["nodeids"]
    if not nodeids:
        raise ClaimError(f"{requirement} lists no test node IDs")
    return nodeids  # type: ignore[return-value]


def claim_session(claim: str) -> int:
    """The session a claim belongs to: the latest of its requirements'.

    Derived from the registry rather than declared beside the claim, for the
    same reason ``claim_mode`` is derived from markers: a claim that gains a
    requirement from a later session becomes that session's claim without
    anyone remembering to say so.

    It exists because ``CLAIMS`` is one dictionary and the gates are not.
    Session 2's evidence must not report a verdict on a guarantee Session 2 did
    not make -- and, worse, ``merge`` refuses to write a document that is silent
    about a claim, so a Session 3 claim in the flat set would have made the
    Session 2 merge unsatisfiable by any pair of runs (ADR 0039).
    """
    if claim not in CLAIMS:
        raise ClaimError(f"unknown claim: {claim}")
    return max(int(_requirement(name)["target_session"]) for name in CLAIMS[claim])


def claims_through_session(session: int) -> tuple[str, ...]:
    """Every claim a gate for ``session`` is answerable for, cumulatively.

    Cumulative because the product is: Session 3 does not stop having to keep
    secrets out of its images. The Session 3 gate therefore proves Session 2's
    claims as well, and its evidence records them.
    """
    return tuple(claim for claim in sorted(CLAIMS) if claim_session(claim) <= session)


def claim_nodeids(claim: str) -> tuple[str, ...]:
    """Every node ID that proves a claim, in registry order, without duplicates."""
    if claim not in CLAIMS:
        raise ClaimError(f"unknown claim: {claim}")
    seen: dict[str, None] = {}
    for requirement in CLAIMS[claim]:
        for nodeid in requirement_nodeids(requirement):
            seen[nodeid] = None
    return tuple(seen)


# ---------------------------------------------------------------------------
# Which environment a test needs
# ---------------------------------------------------------------------------


def _decorator_name(decorator: ast.expr) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return target.attr if isinstance(target, ast.Attribute) else None


@cache
def _environment_markers() -> dict[str, frozenset[str]]:
    """``path::test_name`` -> the environment markers it carries.

    Parsed with ``ast`` rather than by collecting with pytest, for the reason
    ``tests/conftest.py`` parses its ``future`` markers the same way: importing
    a test module executes it, and this runs inside the evidence writer, which
    must not be able to start a socket by reading a file.

    ``tests/contract/test_environment_gates.py`` performs a similar scan for a
    different question — whether every live test declares the variable it needs.
    That one polices the tests; this one reports where a claim can be measured.
    Merging them would put a test-suite policy check inside the library the
    writer imports.
    """
    wanted = set(MODE_MARKERS.values())
    found: dict[str, frozenset[str]] = {}

    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        module_level: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in node.targets
            ):
                if isinstance(node.value, ast.List):
                    module_level |= {
                        name
                        for entry in node.value.elts
                        if (name := _decorator_name(entry)) in wanted
                    }

        relative = path.relative_to(REPO_ROOT).as_posix()
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            markers = set(module_level)
            markers |= {
                name
                for decorator in node.decorator_list
                if (name := _decorator_name(decorator)) in wanted
            }
            found[f"{relative}::{node.name}"] = frozenset(markers)

    return found


def environment_markers(nodeid: str) -> frozenset[str]:
    markers = _environment_markers().get(nodeid)
    if markers is None:
        raise ClaimError(
            f"{nodeid} names no test function in {TESTS_ROOT.name}/. "
            "The acceptance registry and the suite have drifted apart."
        )
    return markers


def claim_mode(claim: str) -> str:
    """The one gate mode that can run a claim's live proofs.

    Derived from the markers rather than declared beside the claim, so a test
    that moves between environments moves its claim with it.
    """
    markers = {marker for nodeid in claim_nodeids(claim) for marker in environment_markers(nodeid)}
    modes = sorted(mode for mode, marker in MODE_MARKERS.items() if marker in markers)

    # **Declared, and the declaration is checked against the proofs** (ADR
    # 0202). A claim named in `OFFLINE_CLAIMS` whose proofs carry a live marker
    # is a claim whose declaration is now wrong -- somebody added a live half to
    # something declared to have none -- and the refusal says so rather than
    # choosing one of the two answers. No claim with a live half can be reported
    # through the offline half, by construction and then again in `write_half`.
    if claim in OFFLINE_CLAIMS:
        if modes:
            raise ClaimError(
                f"claim {claim!r} is declared offline and carries {modes}: a claim with a "
                "live half may not be reported through the offline half. Either remove it "
                "from OFFLINE_CLAIMS or remove the marker from its proofs."
            )
        return OFFLINE_MODE

    if not modes:
        raise ClaimError(
            f"claim {claim!r} has no live proof: every test it names runs in a checkout, "
            "so no deployment is being measured. A claim that measures a checkout is "
            "declared in OFFLINE_CLAIMS, which is a decision per claim (ADR 0202)."
        )
    if len(modes) > 1:
        raise ClaimError(
            f"claim {claim!r} spans {modes}. One evidence half would have to report a "
            "verdict on tests it could not run."
        )
    return modes[0]


def claims_for_mode(mode: str, session: int) -> tuple[str, ...]:
    """The claims of ``mode`` that a gate for ``session`` is answerable for.

    ``session`` is required rather than defaulted. A default would be a fourth
    place that knows which session is current, and the one thing every caller
    here does know is which session's gate it is.
    """
    if mode not in ALL_MODES:
        raise ClaimError(f"unknown mode: {mode}. Expected one of {sorted(ALL_MODES)}.")
    return tuple(claim for claim in claims_through_session(session) if claim_mode(claim) == mode)


def static_nodeids_for_mode(mode: str, session: int) -> tuple[str, ...]:
    """The claim proofs of ``mode`` that carry no environment marker.

    They run anywhere, so the mode's own ``-m live_host`` (or ``-m external``)
    selector does not collect them, and a claim that needed them would come out
    ``not_run`` forever. The gate runs these explicitly rather than widening the
    selector, which would drag the whole contract suite into a deployment run.

    **For ``offline`` this is every proof the mode's claims name**, and the body
    below already says so without a special case: an offline claim carries no
    marker on any of its proofs -- `claim_mode` refuses it otherwise -- so the
    filter admits all of them. That is the property, not a coincidence, and it
    is why the offline gate needs no selector of its own.

    Empty is a legitimate answer, and means this mode carries no claim. The
    caller must not read it as "run everything": ``pytest`` with no node IDs
    collects the entire suite.
    """
    nodeids: dict[str, None] = {}
    for claim in claims_for_mode(mode, session):
        for nodeid in claim_nodeids(claim):
            if not environment_markers(nodeid):
                nodeids[nodeid] = None
    return tuple(sorted(nodeids))


# ---------------------------------------------------------------------------
# The JUnit side
# ---------------------------------------------------------------------------


def junit_key(nodeid: str) -> tuple[str, str]:
    """``path::Class::test`` -> the ``(classname, name)`` pytest writes for it.

    Looking a known node ID up in the XML, rather than reconstructing node IDs
    out of it: ``xunit2`` — pytest's default family since 6.0 — writes no
    ``file`` attribute, so the reverse direction cannot tell a package component
    from a class one.
    """
    path, *rest = nodeid.split("::")
    if not rest:
        raise ClaimError(f"{nodeid} names a file, not a test")
    module = path.removesuffix(".py").replace("/", ".")
    return ".".join([module, *rest[:-1]]), rest[-1]


def _worst(left: str, right: str) -> str:
    return min(left, right, key=_SEVERITY.index)


def junit_outcomes(paths: list[Path]) -> dict[tuple[str, str], str]:
    """``(classname, name)`` -> the worst outcome recorded for it.

    Parameter cases collapse onto their base name, because the registry says a
    node ID naming a parametrized test refers to all of its cases. Worst wins:
    one failing case is a failing test.
    """
    outcomes: dict[tuple[str, str], str] = {}
    for path in paths:
        if not path.is_file():
            raise ClaimError(f"required test artifact is missing: {path}")
        try:
            # S314: JUnit XML this repository's own pytest run produced moments
            # earlier, under a path the gate controls -- the same judgement
            # evidence.parse_junit records.
            root = ElementTree.fromstring(path.read_text(encoding="utf-8"))  # noqa: S314
        except ElementTree.ParseError as exc:
            raise ClaimError(f"{path} is not parseable JUnit XML: {exc}") from exc

        for case in root.iter("testcase"):
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            key = (case.get("classname", ""), case.get("name", "").split("[", 1)[0])
            outcomes[key] = _worst(outcomes.get(key, "passed"), outcome)

    if not outcomes:
        raise ClaimError(f"no test case was recorded in {[str(path) for path in paths]}")
    return outcomes


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------


def claim_result(claim: str, outcomes: dict[tuple[str, str], str]) -> dict[str, object]:
    """One claim's verdict, with the node IDs behind it.

    ``not_run`` is a distinct status from ``failed``: ``failed`` means the system
    is wrong, ``not_run`` means the evidence is.

    **Three things can happen to a proof, not two** (ADR 0163). Until Session 13
    ``not_run`` fired only when a node id was **absent from the JUnit** -- and a
    *skipped* test is not absent. pytest records it, ``junit_outcomes`` maps it to
    ``skipped``, and it fell through to ``failed``.

    **It had never been emitted.** Measured across three releases: sessions 11,
    12 and 13 reported only ``passed`` and ``failed``, zero ``not_run``. The
    Session 13 host run recorded **330 passed, 28 skipped, 0 failed** and
    published **twelve claims as `failed`** -- twelve guarantees asserted broken
    when nobody had looked at them. Four gate scripts documented the behaviour
    this now implements, and the Session 13 gate *printed* it at the top of the
    run that contradicted it.

    ``failed`` outranks ``not_run``: a claim with one failure and one skip is
    ``failed``, because a real failure is the more important thing to report and
    a skip beside it does not soften it.

    **Nothing about pass/fail semantics changes.** Every consumer tests
    ``!= "passed"``, so a ``not_run`` claim still makes its half unproved, still
    makes the merged document ``failed``, and still produces exit 5 (D686). A skip
    is still not a pass (ADR 0018). What changes is only the word the document
    uses to say why -- and that word is the whole of what a reader has to go on.
    """
    nodeids = claim_nodeids(claim)
    missing = [nodeid for nodeid in nodeids if junit_key(nodeid) not in outcomes]
    skipped = [nodeid for nodeid in nodeids if outcomes.get(junit_key(nodeid)) == "skipped"]

    worst = "passed"
    for nodeid in nodeids:
        outcome = outcomes.get(junit_key(nodeid))
        if outcome is not None:
            worst = _worst(worst, outcome)

    if worst == "failed":
        status = "failed"
    elif missing or skipped:
        status = "not_run"
    else:
        status = "passed"

    result: dict[str, object] = {
        "status": status,
        "requirements": list(CLAIMS[claim]),
        "node_ids": list(nodeids),
    }
    # Named, not just counted. A status that says "the evidence is missing"
    # without saying WHICH evidence sends its reader back to a JUnit file.
    if missing:
        result["missing_node_ids"] = missing
    if skipped:
        result["skipped_node_ids"] = skipped
    return result


def results_for_mode(
    mode: str, session: int, junit_paths: list[Path]
) -> dict[str, dict[str, object]]:
    """Every claim this mode is responsible for, judged against its artifacts."""
    outcomes = junit_outcomes(junit_paths)
    return {claim: claim_result(claim, outcomes) for claim in claims_for_mode(mode, session)}

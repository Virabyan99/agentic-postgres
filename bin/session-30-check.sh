#!/usr/bin/env bash
#
# The Session 30 gate: one discipline for every container exec, a reading that
# takes a ref, a compile that writes only when it succeeded, two guards over
# this suite's own shape, and — on the deployment — a query view that keeps two
# subjects' rows apart (ADR 0216-0220). It does not replace
# bin/session-01-check.sh, which must still exit 0, nor the Session 2-28 gates,
# which still own their sessions.
#
# **Derived from bin/session-28-check.sh by diff, not retyped** (D505, D507,
# D678, D693, D703, D1108, D1109). `readonly SESSION=30` is the only session
# literal; everything else that differs is a named substitution, and every
# substitution in the derivation was asserted to match exactly once.
#
# **This header and the usage block below were REWRITTEN, not patched.** Three
# derivations running have each missed a half of the prose (D853, D858), and
# D693's guard is scoped to the `--session N` an operator TYPES and is right not
# to flag prose -- so both halves are read line by line at every derivation,
# and the next one should expect to do the same.
#
# **29 has no gate and never will**, and the reason is a new one. 19, 26 and 27
# built nothing; 29 took THE TRIP -- it deployed 1.7.0, swept it and tagged it
# on the commit that was deployed (D1425). A trip that registers no requirement
# still writes no half of its own, so there is no gate to write it and the
# session number goes 28 -> 30 (D1063, D1514). `claims_through_session(30)`
# inherits every earlier session's claims unchanged.
#
# **This session ships NO migration and moves NO schema.** What it ships is one
# internal module and one sourced shell library through which every `docker
# exec` and every `compose.sh run` in the product now runs; `apg release-reading
# --ref REF`; `bin/mcp-contract.sh compile --output PATH`; and two contract
# modules that guard the shape of this suite. `VERSION` moves to 1.8.0. An
# operator supplies nothing they did not supply for 1.7.0, and the deploy this
# release asks for applies nothing: **the ledger does not move**, which is the
# opposite of what the Session 28 gate said and the thing most likely to be
# read past in a derivation.
#
# **FIVE of this session's six claims are declared offline** (ADR 0202), two
# more than any session has declared, and each is a property of a CHECKOUT.
# `exec_discipline` is an argv and an AST scan over this tree. `release_reading_
# ref` is a command that reads `git` in a clone and prints. `contract_compile_
# output` is what a command writes into a temporary directory and what two
# pages in this repository say. `suite_shape` is the shape of this suite, which
# no deployment has an opinion about. `mirror_retry` is what the mirror verb
# does with a pass that transferred what it could, proved against a fake
# `compose_mirror` that never opens a socket (ADR 0220). A deployment would
# answer none of the five differently.
#
# **`mirror_retry` arrived after this session's Run 6**, at the operator's
# instruction and hours before the host's next timed pass. It is the repair for
# the defect Run 1 diagnosed: on 2026-09-18 `mc` transferred a whole 3,700-
# object bucket and exited 1 because ONE small object came back with an empty
# body against an advertised `ContentLength`, and that one object cost a failed
# unit, a `degraded` host, an unwritten record, and a doctor reporting a stale
# mirror that was materially current (D1546). The flake is upstream and nothing
# in this release removes it; what this removes is the fold.
#
# **`studio_tenant_read` is a HOST claim and is deliberately NOT declared.**
# Whether a human's rows and a stranger's stay apart through Studio's forwarder
# is a property of a RUNNING plane and of PostgreSQL's policies on it, and a
# checkout cannot answer it. It is `not_run` until this session's trip sweeps.
#
# **Its proof has never executed.** `test_the_query_view_shows_the_human_their_
# own_rows_and_not_anothers` has been in `tests/deployment/test_session24_
# studio.py` since Session 24, belonged to no requirement, and errored at setup
# on every sweep since: its fixture created a stranger with `ARRAY[]::text[]`,
# which migration 0011 refuses. All three Studio claims read `passed` while it
# never ran, because a proof that is a node id of no claim moves nothing when
# it runs and nothing notices when it does not (D386, D1236). The fixture now
# gives the stranger `notes:read`, which is also the stronger subject. **This
# gate's host mode is its first execution anywhere.**
#
# **`--redeploy-before-file` is given on THIS trip, and it never has been.**
# `deployment_convergence` (DEP-002, Session 11) has been `not_run` since it was
# registered because the flag that admits its two proofs was never declared.
# The recipe is in the session plan's Sheet A2: write a sentinel row on alpha
# and record the CURRENT generation id in a two-field JSON before the redeploy,
# then pass that file here. If the claim still reads `not_run` after the flag
# was given, read `skipped_node_ids` -- it names the precondition the recipe
# missed -- and do not re-run the deploy to make it move.
#
# Three modes, and the shape is Session 5's deliberately (D221). A gate over
# manifests measures what was asked for; a gate over deployed documents measures
# what happened.
#
#   --mode offline    a checkout that produces evidence: everything Session 28
#                     checked, plus Session 30's own four offline halves -- the
#                     exec discipline and its AST scan (test_container_exec),
#                     the reading taken of a ref (test_release_reading), the
#                     compile that writes only on success and the documented
#                     lines that no longer redirect (test_capability_compiler,
#                     test_session12_documented_path), and the two shape guards
#                     (test_suite_shape, test_deployment_suite_shape). Step 3's
#                     sweep carries all of them by their marks; nothing here is
#                     selected by name that the sweep does not already collect.
#                     **Requires docker**, as Session 28's does and for the same
#                     reasons. No host, no root.
#   --mode host       the deployment, and it answers for THIS session and the
#                     two standing Session 12 claims below. `studio_tenant_
#                     read`: Studio's query view forwarded as the human returns
#                     that human's rows and none of a second registered
#                     subject's, and the second subject's row is proved to EXIST
#                     by reading it as that subject through the same surface --
#                     so an empty result is separated from a filtered one (ADR
#                     0195). **`--redeploy-before-file` is new on this trip**
#                     and moves `deployment_convergence` for the first time.
#                     **The sweep needs docker**, which it has.
#   --mode external   a different network: what a stranger reaches. Session 30
#                     adds no external claim of its own -- nothing it ships is
#                     reachable from a network at all -- and still needs this
#                     mode for the cumulative reason below.
#
# **Session 30's own claims are offline and host.** The gate still has three
# modes because `claims_through_session(30)` is CUMULATIVE: a Session 30
# document must answer for the external claims inherited from Sessions 4-9, and
# the writer refuses a document silent about a claim. Run all three, merge --
# and the merge REQUIRES `--offline-input`, exactly because this session has
# offline claims (ADR 0202).
#
# **Inventing an external claim to make the shape symmetric was refused** (ADR
# 0065): a proof that reaches an end state by a route the product does not take
# proves the end state is reachable, not that the product reaches it.
#
# **`apg release-reading` is deliberately NOT a step here** (D1467, ADR 0214),
# and this session giving it `--ref` does not change that. It is taken by a
# person at a workstation with a full clone, before the tag goes on the commit
# that was deployed, and the argument against wiring it into a gate is the
# measurement: the reading needs tags, and two of CI's three jobs check out
# without any. A step that printed *the reading cannot be taken here* on every
# run is a line nobody reads.
#
# **Every flag a claim depends on is written INTO the documented command below**,
# not mentioned underneath it. D213 recorded thirteen secret proofs gated on a
# flag that was not passed once all session.
#
# **Session 18's five declaration flags are BACK, and stay in every later gate**
# (D1133, reversing D1021's reading). `claims_through_session(30)` runs Session
# 18's proofs, and a proof that runs in this sweep and skips for want of its
# declaration OUTVOTES the pass Session 18's own gate recorded when the two
# JUnits are merged (D1123). A gate carries every declaration a proof it RUNS
# can read -- not only the proofs it adds. One sweep writes the host half.
#
# **What must be true of this WORKSTATION before offline mode means anything**:
#
#   1. **Docker running**, and this gate needs it for everything Session 28's
#      did. Step 8 stands a cluster up; step 8b builds the toolchain image and
#      typechecks the committed client; step 3's sweep runs modules that each
#      stand up a cluster, and the exec-discipline module runs a real container
#      to prove that a fed stdin reaches the child. Without a daemon all of it
#      SKIPS, and a skip is not a pass -- every offline claim that depends on a
#      cluster would report `not_run` and this gate would exit 5 having written
#      a half that proves less than it looks like. So the daemon is checked up
#      front and its absence is exit 3, not a skip.
#   2. **The fixtures rendered.** `apg dev up` refuses a project this checkout
#      has not rendered, naming the render command; step 2 checks the same
#      thing the six cluster fixtures check.
#   3. **A clean tree**, as for every gate: it measures the checkout, and a
#      checkout with uncommitted changes is not a release.
#
# **What must be true of the deployment before host mode means anything**, and
# these are checked rather than assumed:
#
#   1. Both projects deployed `--through-session 30`, which publishes outputs
#      **v18** -- unchanged, because Session 30 moves no outputs schema. **The
#      ledger does NOT move on either project**: this release adds no migration,
#      so alpha stays at 33 and beta at 35 across ADR 0206's two ledgers. Read
#      the ledger rather than the migrator's line (D941), and read the container
#      rather than the lock file (D1152, D1153). A redeploy recreates only a
#      container whose mounted content moved (ADR 0155), so the verifiers keep
#      their ages and that is the expected reading, not a deploy that did
#      nothing.
#   2. **Beta's manifest at schema 6 naming `projects/example` for BOTH keys**
#      (`migrations.set` and `mcp.capabilities`), and alpha's at schema 4, which
#      is the control that an older manifest still deploys under a schema 6
#      release (D930). Checked in step 4c.
#   3. **The issuer answering on both projects**, read before anything else, so
#      that a gate run against an issuer that had not come back does not report
#      forty refusals about one restart.
#   4. **The repository must be ready** -- inherited and unchanged: the stanza
#      exists, at least one full backup exists, and the archiver is not failing.
#   5. **The mirror enabled and copied on both permanent projects** -- inherited
#      from Session 18 and checked in step 4b. **Both units have failed since
#      2026-09-18** (D1512): the copy's own transport flake, one object per pass,
#      diagnosed in this session's Run 1 and repaired by hand on both projects
#      before this trip. What this step reads is the record that repair left.
#   6. **The five declarations that admit the kit, the replacement and the
#      rehearsals**: `--kit-dir`, `--replacement-host-outputs`,
#      `--replacement-bootstrap-state`, `--restore-evidence-file` and
#      `--rehearsal-evidence-dir`. Without them the proofs they admit skip and
#      `disaster_kit`, `replacement_host_restore` and `failure_rehearsal` report
#      `not_run`, as they must. `REC-KIT-003`'s offline half runs regardless.
#      **`--kit-dir` must keep pointing at the kit exported BEFORE this
#      release** (D1282); see its help text below.
#   7. **`--fresh-host-outputs` and `--dx-record-file`** admit `fresh_host` and
#      `documented_path` (Session 12). `documented_path` is `failed` and this
#      session did not repair it either: it stays failed until a PERSON walks
#      the path, and two model walks recording 6 and 11 undocumented steps are
#      not that person. **`--removed-project-file`** admits `project_removal`
#      (Session 17); **`--admin-password-file` is required** for every `IDN-*`,
#      Session 16, Session 21 and Session 22 live proof, and for the Studio
#      claim this session adds.
#   8. **`host.yaml` in the checkout**: the retirement plan proof passes it to
#      `project-retire.sh --host`, and fails rather than skips when it is absent.
#
# **The signing-key rotation is NOT this gate's business**, and that is worth
# saying twice in the session that performs it for the first time. No flag here
# performs a rotation. `--rotated-jwt-from-file` admits a proof about a rotation
# that has ALREADY happened, and on this trip nothing has: the rotation is a
# separate sitting on its own sheets, AFTER the sweep and the tag, so the three
# `--rotated-*` flags are not passed and the three credential claims stay
# `not_run` with the remaining rotations named. If a rotation is ever performed
# on the same day as a sweep, the sweep goes AFTER `retire` (D1470): the
# signing-key proof is red between `promote` and `retire` by design.
#
# It VERIFIES. It does not deploy. A gate that deploys the system it measures
# cannot be re-run to confirm a fix, and its result depends on whether it was
# the first run (D20).
#
# Exit codes:
#   0  every check in the selected mode passed
#   2  invalid operator input
#   3  missing prerequisite for the selected mode
#   5  the evidence was WRITTEN and some claim in it is not `passed` (D686).
#      Not a failure of the suite -- `write-session-evidence` returns this when
#      a claim's node ids did not all pass, which includes a node id that
#      SKIPPED because its flag was not given. A skip is not a pass, and this
#      exit code is that rule reaching the operator. Read the "not proved by
#      this run" line: it names them.
#   6  a check failed
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR
cd "${ROOT_DIR}"

readonly EVIDENCE_DIR="${ROOT_DIR}/evidence"

readonly SESSION=30

# The gate's own name, derived rather than written. Eleven references to the
# previous session's name survived the diff into this file -- in the usage
# block an operator copies and in every message the gate prints about
# itself. D751's guard is scoped to the numbers an operator TYPES and is
# right not to flag a program's name, so this is the same loss one layer
# down (D505, D507, D678, D693).
readonly PROGRAM="session-${SESSION}-check"
# Derived from SESSION rather than written out, and defined AFTER it. Session
# 5's copy of this file carries the reason: every other `session-04` in it was
# renamed when it was copied, and these two were built by concatenating a
# literal prefix onto a variable, so the rename did not match them and the gate
# would have written the previous session's filenames while its own --help named
# files it never writes. A number that appears once cannot be left behind.
EVIDENCE_PREFIX="$(printf 'session-%02d' "${SESSION}")"
readonly EVIDENCE_PREFIX

MODE=""
HOST_MANIFEST=""
PROJECT_A_OUTPUTS=""
PROJECT_B_OUTPUTS=""
SENTINEL_FILE=""
ADMIN_PASSWORD_FILE=""
ROTATED_FROM_FILE=""
ROTATED_AUTHENTICATOR_FROM_FILE=""
ROTATED_DOCS_FROM_FILE=""
REDEPLOY_BEFORE_FILE=""
FRESH_HOST_OUTPUTS=""
REMOVED_PROJECT_FILE=""
DX_RECORD_FILE=""
# Session 18. Four declarations of things that HAPPENED off this host or
# were run on it by an operator: the kit, the replacement's document, the
# restore's record and the rehearsals' records. Declared rather than
# produced, because a gate that exported a kit or ran a rehearsal would be
# measuring its own run. Session 20 removed them (D1021) and Session 21
# brings them back (D1133): a gate carries every declaration a proof it
# RUNS can read, and this sweep runs Session 18's.
KIT_DIR=""
REPLACEMENT_HOST_OUTPUTS=""
REPLACEMENT_BOOTSTRAP_STATE=""
RESTORE_EVIDENCE_FILE=""
REHEARSAL_EVIDENCE_DIR=""
# Session 14. Which alert an operator induced, by name.
#
# The NAME rather than a flag: three rules watch three different hops, and
# one firing when another was induced is exactly the conflation D784
# measured. A boolean would admit the proof on the strength of any alert.
INDUCED_ALERT_FILE=""
ROTATED_JWT_FROM_FILE=""
PUBLIC_IPV4=""
PUBLIC_IPV6=""
SSH_DESTINATION=""
AFTER_REBOOT=0
KEYWORD=""

usage() {
  # The script's own name is the ONE value interpolated here. The heredoc below
  # stays single-quoted because it carries a `$(sudo python3 -c ...)` example an
  # operator copies, and an unquoted heredoc would RUN it while printing help.
  printf 'Usage: bin/%s.sh --mode offline\n' "${PROGRAM}"
  printf '       sudo bin/%s.sh --mode host --host host.yaml \\\n' "${PROGRAM}"
  cat <<'USAGE'
            --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
            --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
            --admin-password-file /root/alpha-dev-administrator \
            --sentinel-file "$(sudo python3 -c "
import json
from pathlib import Path
root = Path('/var/lib/agentic-postgres/secrets/alpha-dev')
gen = json.loads((root / 'active-secret-generation.json').read_text())['generation_id']
print(root / 'generations' / gen / 'secret-check' / 'session2_sentinel')
")" \
            [--rotated-from-file FILE] [--rotated-authenticator-from-file FILE] \
            [--rotated-docs-from-file FILE] [--rotated-jwt-from-file FILE] \
            [--kit-dir DIR] [--replacement-host-outputs FILE] [--replacement-bootstrap-state FILE] \
            [--restore-evidence-file FILE] [--rehearsal-evidence-dir DIR] \
            [--after-reboot] [-k EXPRESSION]

  DERIVE the sentinel path, never type it: the generation directory changes on
  every start, so a hard-coded one silently names a superseded generation and
  the scan then fails to find what it planted.
USAGE
  printf '       bin/%s.sh --mode external --public-ipv4 ADDR \\\n' "${PROGRAM}"
  cat <<'USAGE'
            --project-a-outputs FILE --ssh-destination op@HOST \
            [--public-ipv6 ADDR] [--project-b-outputs FILE] [-k EXPRESSION]

  --mode offline   Contracts, schemas and models, plus Session 30's own FIVE
                   offline halves: the exec discipline and the AST scan that
                   finds no docker or compose subprocess outside the helper;
                   the reading taken of a ref rather than of the working tree;
                   the compile that writes only when it succeeded, and the two
                   documented lines that no longer redirect; and the two guards
                   over this suite's own shape. Step 3's sweep carries all four
                   by their marks. Step 6 checks the committed example client is
                   CURRENT -- this release's bump moves `templateVersion` in it
                   (D1238); step 7 checks the project's own tool catalog beside
                   the registry's documents; step 8b typechecks the client on
                   the pinned toolchain with no network; step 8c asserts Studio
                   ships no third-party code; step 9 WRITES A HALF --
                   evidence/session-30-offline.json. The FIVE claims it reports
                   are `exec_discipline`, `release_reading_ref`,
                   `contract_compile_output`, `suite_shape` and `mirror_retry`.
                   Requires docker. No host, no root.
  --mode host      Session 28's sweep with ONE flag added, and it answers for
                   THIS SESSION ALONE: 29 took the trip that tagged 1.7.0 and
                   registered nothing, so there is no earlier half owed.
                   `studio_tenant_read`: Studio's query view, forwarded as the
                   human and holding only the human's own token, returns that
                   human's rows and none of a second registered subject's -- and
                   the second subject's row is proved to EXIST by reading it as
                   that subject through the same surface, so an empty result is
                   told apart from a filtered one (ADR 0195). The stranger is
                   registered with a real read scope on the relation rather than
                   an empty scope set -- which migration 0011 refuses, and which
                   is why the proof had never run -- and that is also the
                   stronger subject: a caller who CAN read the relation and
                   still sees none of the auditor's rows says something a caller
                   who can read nothing does not.
                   **That proof has never executed anywhere**: it belonged to no
                   requirement and errored at setup on every sweep since Session
                   24 while three Studio claims read `passed` (D386, D1236).
                   **The one new flag is `--redeploy-before-file`**, which moves
                   `deployment_convergence` for the first time since Session 11
                   registered it. `stage_release` moves too, because this trip
                   deploys the release the tree names before it sweeps (D1425).
                   **No migration is applied by that deploy** -- read the ledger
                   and expect it unchanged. **The sweep runs docker**, which it
                   has. Needs root, host.yaml in the checkout, and the
                   declarations for every claim that is about something that
                   happened elsewhere.
  --mode external  What the public internet reaches. Session 30 adds no external
                   claim -- it ships no service, no port and no route, and its
                   four offline claims are about a checkout -- but the
                   inherited ones still need it, because
                   claims_through_session(30) is cumulative. MUST run from a
                   network that is not the deployment host.

  --project-b-outputs   Required in host mode. `project_isolation` is a claim
                        about two projects' identity planes, and one project
                        cannot be isolated from nothing. **Session 11 runs its
                        restore drill against BETA**, in the frozen example
                        domain under a drill-only owner id, so this is the
                        project the drill disturbs. Optional in external mode,
                        where no test reads it and the merge compares which
                        deployment each half described.
  --sentinel-file       The planted secret value, from the ACTIVE generation.
                        It is in the command above rather than described below
                        it, because a flag mentioned under a command is a flag
                        that does not get passed (D213). Without it the secret
                        leakage proofs skip and the claim reports unproved.
  --fresh-host-outputs  A deployed document from a host that started EMPTY.
                        Admits DEP-001's live half. Without it that claim is
                        unproved, and its offline half may not stand in for it.
  --removed-project-file  What an operator recorded BEFORE removing a project:
                        its key and the resources it owned. Captured after, it
                        would be a list of things that no longer exist.
  --dx-record-file      The record of a developer who did not build this
  --induced-alert-file  A file naming the alert an operator induced
                        following the documented path: what they ran, what they
                        edited, and what the documentation did not tell them.
  --redeploy-before-file  Opened before a redeploy: the generation and the
                        sentinel row that must survive it. Without it both
                        DEP-002 proofs skip and `deployment_convergence` is
                        unproved.
  --kit-dir DIR         The kit `bin/dr-kit.sh export` wrote on THIS host and
                        the operator copied off it. Admits REC-KIT-001's live
                        half (it verifies and holds no value this host holds)
                        and, with the next flag, REC-KIT-002 and REC-NODE-002.
                        **Point it at the kit exported BEFORE this release, not
                        the newest one** (D1282). REC-KIT-003's claim IS the
                        version gap between a kit and the tree that reads it,
                        and its proof `pytest.fail`s on exactly that -- so
                        aiming this at a kit taken from the current release
                        destroys the proof without failing anything. As of this
                        session that means kit-2026-09-11, and a newer export
                        discharges the OPERATIONAL obligation without moving
                        this flag.
  --replacement-host-outputs FILE
                        The restored project's deployed document, fetched from
                        the replacement host. It records the kit's provider
                        project id with a fresh runtime identity, and the
                        original instance_uuid.
  --replacement-bootstrap-state FILE
                        The bootstrap state `--adopt` wrote on the replacement,
                        fetched from /etc/agentic-postgres/projects/<key>/ there.
                        Admits REC-KIT-002's live half: the kit's provider
                        project by id, a fresh runtime identity, the same
                        inputs. A rehearsal ends at the restore, so this is
                        the record adoption leaves rather than a deploy's.
  --restore-evidence-file FILE
                        The record `bin/restore.sh --from mirror` wrote:
                        REC-REPO-003's live half. On the replacement it also
                        admits REC-NODE-001, which runs `restore.sh --plan`
                        against the volume the restore filled and expects 7.
  --rehearsal-evidence-dir DIR
                        Where the eight rehearsals wrote their records
                        (evidence/ by default). OPS-REHEARSE-002..008 read one
                        record each; -001 reads them all and the host after.
  --admin-password-file The project administrator's password, as written when
                        `bin/auth-admin.sh bootstrap` created it. It cannot be
                        recovered from the host -- only an Argon2id hash is
                        stored, which is what SEC-CRED-001 asserts -- so the
                        proofs that need an administrator session have to be
                        given one. Without it they skip, and four claims report
                        `not_run` rather than passing on a subset.
  --ssh-destination     Required in external mode, and it is `op@HOST`. D466:
                        the access broker grants ONE enumerated account, and
                        `apg-agent@` -- the read-only diagnosis account, and the
                        intuitive choice -- is refused. Without a destination
                        the two connection-tooling proofs skip, and a skip is
                        not a pass.
  --rotated-from-file FILE
                        The application credential this window replaced, as
                        the provider held it before the rotation. Exports
                        APG_ROTATED_FROM_FILE and admits the proof that the
                        replaced value no longer opens a session. **Accepted
                        by every gate since Session 5 and documented by
                        none**: the parser took it, `--help` did not name
                        it, and an operator who had performed the rotation
                        had no way to learn the gate would read it.
  --rotated-authenticator-from-file FILE
                        The authenticator password this window replaced.
  --rotated-docs-from-file FILE
                        The documentation Basic Auth password this window
                        replaced.
  --rotated-jwt-from-file FILE
                        The retired signing key's public material, as JSON.
                        There are THREE verifiers that ACKNOWLEDGE a key
                        set (D1472): PostgREST, storage and the agent plane --
                        the three services compose.yaml mounts the rendered
                        jwks.json into, and the three
                        `bin/rotate-signing-key.sh acknowledge` prints. `auth`
                        is the ISSUER and is not one of them: ADR 0098 is titled
                        *the issuer's published set is not the verifier's set*,
                        and an acknowledgement from it would be the issuer
                        agreeing with itself. All three are RECREATED rather
                        than restarted after the published set changes (ADR
                        0088, ADR 0155).
  --after-reboot        Declare that the host has just rebooted, which admits
                        the proof that the clusters came back by themselves.
                        Wait for the units to reach `active` first.
  -k EXPRESSION         Restrict to matching tests. Writes no evidence: a run
                        that selected a subset cannot support a claim about the
                        whole.

BEFORE host mode, in this order, once per project:

  1. An operator creates an R2 bucket and a token scoped to it, OUT OF BAND.
     Nothing in this repository creates a bucket or issues a token (ADR 0110).
  2. The two halves of that token go into the provider at /backup, and the
     cipher pass is generated. All three must exist before a deploy will do
     anything with the repository.
  3. Deploy. Step 6c creates the stanza and runs `pgbackrest check`, and a check
     failure FAILS THE DEPLOY -- it is the only end-to-end test of the archiver,
     and a release converging over a broken one is the failure it prevents.
  4. Take the first full backup by hand:
       sudo bin/backup.sh --outputs FILE backup --type full
     Until this runs the document says `awaiting_first_backup` and the drill has
     nothing to restore. This gate refuses to start without it.

USAGE

  # **Derived, because this is the half that keeps going stale** (D703, and
  # D751 in this session). The block above is a quoted heredoc, so a session
  # number written inside it cannot interpolate -- and three derivations running,
  # the merge example told an operator to write `evidence/session-10.json` from a
  # Session 12 gate. An operator who copied it would have overwritten an earlier
  # session's evidence with this one's, and both commands would have exited 0.
  #
  # Every session number an operator is told to type now comes from ${SESSION}.
  printf '\n'
  printf 'Each mode writes one evidence half. Session %s needs ALL THREE -- its own\n' "${SESSION}"
  printf 'claims are measured in a checkout, the external claims inherited from\n'
  printf 'Sessions 4-9 are measured from off-host, and the rest on the deployment.\n'
  printf 'Merge them with:\n'
  printf '  python bin/write-session-evidence.py --session %s \\\n' "${SESSION}"
  printf '    --host-input evidence/session-%02d-host.json \\\n' "${SESSION}"
  printf '    --external-input evidence/session-%02d-external.json \\\n' "${SESSION}"
  printf '    --offline-input evidence/session-%02d-offline.json \\\n' "${SESSION}"
  printf '    --output evidence/session-%02d.json\n' "${SESSION}"
  printf '\n'
  # `printf -- ` because the line begins with two dashes and bash's printf
  # would read them as its own option terminator.
  printf -- '--offline-input is REQUIRED here and refused for a session with no\n'
  printf 'offline claim (ADR 0202). Run the merge from a checkout at the commit the\n'
  printf 'offline half measured, or the writer prints the difference -- recorded,\n'
  printf 'never required and never hidden.\n'
  printf '\n'
  printf 'This command verifies and never deploys. Use ./deploy.sh --through-session %s\n' \
    "${SESSION}"
  printf 'to deploy, then run this to find out whether it worked.\n'
}

die() {
  local code="$1"
  shift
  printf '%s: %s\n' "${PROGRAM}" "$*" >&2
  exit "$code"
}

# Interpreter resolution, in this order and for these reasons:
#
#   1. the repository's own venv, because sudo resets PATH to secure_path and a
#      venv the operator activated is therefore invisible to this script;
#   2. python3, because Ubuntu ships no bare `python` and has not for years;
#   3. python, for a machine where the venv is already on PATH.
python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3, python)."
  fi
}

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# Host mode runs under sudo, so everything written below lands root:root -- and
# the operator who has to read the verdict and commit the evidence cannot.
restore_evidence_ownership() {
  [ -n "${SUDO_UID:-}" ] && [ -n "${SUDO_GID:-}" ] || return 0
  chown -R "${SUDO_UID}:${SUDO_GID}" "${EVIDENCE_DIR}" 2>/dev/null || true
}

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --mode)
        [ "$#" -ge 2 ] || die 2 "--mode requires a value."
        MODE="$2"
        shift 2
        ;;
      --host)
        [ "$#" -ge 2 ] || die 2 "--host requires a value."
        HOST_MANIFEST="$2"
        shift 2
        ;;
      --project-a-outputs)
        [ "$#" -ge 2 ] || die 2 "--project-a-outputs requires a value."
        PROJECT_A_OUTPUTS="$2"
        shift 2
        ;;
      --project-b-outputs)
        [ "$#" -ge 2 ] || die 2 "--project-b-outputs requires a value."
        PROJECT_B_OUTPUTS="$2"
        shift 2
        ;;
      --sentinel-file)
        [ "$#" -ge 2 ] || die 2 "--sentinel-file requires a value."
        SENTINEL_FILE="$2"
        shift 2
        ;;
      --admin-password-file)
        [ "$#" -ge 2 ] || die 2 "--admin-password-file requires a value."
        ADMIN_PASSWORD_FILE="$2"
        shift 2
        ;;
      --rotated-authenticator-from-file)
        [ "$#" -ge 2 ] || die 2 "--rotated-authenticator-from-file requires a value."
        ROTATED_AUTHENTICATOR_FROM_FILE="$2"
        shift 2
        ;;
      --rotated-docs-from-file)
        [ "$#" -ge 2 ] || die 2 "--rotated-docs-from-file requires a value."
        ROTATED_DOCS_FROM_FILE="$2"
        shift 2
        ;;
      --redeploy-before-file)
        [ "$#" -ge 2 ] || die 2 "--redeploy-before-file requires a value."
        REDEPLOY_BEFORE_FILE="$2"
        shift 2
        ;;
      # Session 12's three, and each admits a proof of something that HAPPENED
      # rather than of a state that holds: a host that started empty, a project
      # an operator removed, and a developer who did not build this. Same shape
      # as --after-reboot and --rotated-*-from-file, for the same reason.
      --fresh-host-outputs)
        [ "$#" -ge 2 ] || die 2 "--fresh-host-outputs requires a value."
        FRESH_HOST_OUTPUTS="$2"
        shift 2
        ;;
      --removed-project-file)
        [ "$#" -ge 2 ] || die 2 "--removed-project-file requires a value."
        REMOVED_PROJECT_FILE="$2"
        shift 2
        ;;
      --dx-record-file)
        [ "$#" -ge 2 ] || die 2 "--dx-record-file requires a value."
        DX_RECORD_FILE="$2"
        shift 2
        ;;
      # Session 18's five, back (D1133). Each admits a proof of something that
      # HAPPENED -- a kit exported, a replacement adopted and restored, eight
      # rehearsals run -- and this sweep runs those proofs.
      --kit-dir)
        [ "$#" -ge 2 ] || die 2 "--kit-dir requires a value."
        KIT_DIR="$2"
        shift 2
        ;;
      --replacement-host-outputs)
        [ "$#" -ge 2 ] || die 2 "--replacement-host-outputs requires a value."
        REPLACEMENT_HOST_OUTPUTS="$2"
        shift 2
        ;;
      --replacement-bootstrap-state)
        [ "$#" -ge 2 ] || die 2 "--replacement-bootstrap-state requires a value."
        REPLACEMENT_BOOTSTRAP_STATE="$2"
        shift 2
        ;;
      --restore-evidence-file)
        [ "$#" -ge 2 ] || die 2 "--restore-evidence-file requires a value."
        RESTORE_EVIDENCE_FILE="$2"
        shift 2
        ;;
      --rehearsal-evidence-dir)
        [ "$#" -ge 2 ] || die 2 "--rehearsal-evidence-dir requires a value."
        REHEARSAL_EVIDENCE_DIR="$2"
        shift 2
        ;;
      # The plan's own name for the first of these predates Session 18 Run 1's
      # reversal (D1021): there is no second repository to check, and the
      # mirror's readiness is a precondition, not a flag.
      --secondary-repo-check|--secondary-repo-check=*)
        die 2 "there is no --secondary-repo-check: the mirror's readiness is checked in step 4b of host mode. See --help."
        ;;
      --induced-alert-file)
        [ "$#" -ge 2 ] || die 2 "--induced-alert-file requires a value."
        INDUCED_ALERT_FILE="$2"
        shift 2
        ;;
      --rotated-jwt-from-file)
        [ "$#" -ge 2 ] || die 2 "--rotated-jwt-from-file requires a value."
        ROTATED_JWT_FROM_FILE="$2"
        shift 2
        ;;
      --rotated-from-file)
        [ "$#" -ge 2 ] || die 2 "--rotated-from-file requires a value."
        ROTATED_FROM_FILE="$2"
        shift 2
        ;;
      --public-ipv4)
        [ "$#" -ge 2 ] || die 2 "--public-ipv4 requires a value."
        PUBLIC_IPV4="$2"
        shift 2
        ;;
      --public-ipv6)
        [ "$#" -ge 2 ] || die 2 "--public-ipv6 requires a value."
        PUBLIC_IPV6="$2"
        shift 2
        ;;
      --ssh-destination)
        [ "$#" -ge 2 ] || die 2 "--ssh-destination requires a value."
        SSH_DESTINATION="$2"
        shift 2
        ;;
      --after-reboot)
        AFTER_REBOOT=1
        shift
        ;;
      -k)
        [ "$#" -ge 2 ] || die 2 "-k requires an expression."
        KEYWORD="$2"
        shift 2
        ;;
      --mode=*|--host=*|--project-a-outputs=*|--project-b-outputs=*|--sentinel-file=*)
        die 2 "use a space, not '=': ${1%%=*} VALUE"
        ;;
      --admin-password-file=*|--rotated-from-file=*|--public-ipv4=*|--public-ipv6=*)
        die 2 "use a space, not '=': ${1%%=*} VALUE"
        ;;
      --ssh-destination=*)
        die 2 "use a space, not '=': ${1%%=*} VALUE"
        ;;
      # The runbook's shapes for this gate, named rather than swept into
      # "unknown argument". An operator reading the runbook is asking a
      # reasonable question, and the answer is a different flag rather than a
      # usage error.
      --project|--project=*)
        die 2 "there is no --project: the gate takes DEPLOYED documents, not manifests. A gate over manifests measures what was asked for. See --help."
        ;;
      --peer-project|--peer-project=*)
        # D404, and D316 is the same refusal from Session 7. The runbook family
        # has now proposed this invocation twice.
        die 2 "there is no --peer-project: use --project-b-outputs, which names the peer's DEPLOYED document rather than its manifest. See --help."
        ;;
      --capabilities|--capabilities=*)
        die 2 "there is no --capabilities: the gate takes deployed documents, not operator inputs. The compiled capability contract is checked in offline mode by bin/mcp-contract.sh. See --help."
        ;;
      --capability-lock|--capability-lock=*)
        # The lock the runtime obeys is the DEPLOYED one, mounted into the
        # container. A gate handed a lock would be measuring the file somebody
        # typed rather than the file the plane reads (ADR 0126).
        die 2 "there is no --capability-lock: the plane obeys the lock mounted into its container, and that is what host mode measures. See --help."
        ;;
      --agent-token|--agent-token=*)
        # The suite creates its own agent through the product's own
        # `auth_create_agent` and obtains a token from the deployment. A gate
        # given one would prove that somebody can hold a token.
        die 2 "there is no --agent-token: the suite creates an agent through the product's own auth_create_agent and obtains a token from the deployment. See --help."
        ;;
      --baseline-only)
        die 2 "--baseline-only belongs to bin/session-02-check.sh; Session 11 measures a deployed system."
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  case "${MODE}" in
    offline|host|external) ;;
    "") usage >&2; die 2 "--mode is required." ;;
    *) die 2 "unknown mode: ${MODE}. Expected offline, host or external." ;;
  esac
}

# Every mode runs pytest with the same selector shape, so none can drift into its
# own definition of passing.
run_suite() {
  local marker="$1" junit="$2"
  local -a arguments=(-q -m "${marker}")
  [ -n "${KEYWORD}" ] && arguments+=(-k "${KEYWORD}")
  [ -n "${junit}" ] && arguments+=(--junitxml="${junit}")

  "$(python_bin)" -m pytest "${arguments[@]}"
}

# A claim's proofs are not all environment-gated: some also name contract tests
# that run anywhere, which `-m live_host` therefore never collects. They are run
# explicitly rather than by widening the selector, which would drag the whole
# contract suite into a deployment run. The node IDs come from the acceptance
# registry, so a requirement that gains a test gains it here without anyone
# editing this script.
#
# Session 8 has more of these than any session before it. ADR 0132 is why: four
# of its requirements were proved offline first and gained live proofs rather
# than twins, so each carries both halves.
claim_static_nodeids() {
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "$1" "$2" <<'PYTHON'
import sys

from agentic_postgres.evidence_claims import static_nodeids_for_mode

for nodeid in static_nodeids_for_mode(sys.argv[1], int(sys.argv[2])):
    print(nodeid)
PYTHON
}

# Writes ${junit} only if this mode has environment-free proofs to run. An empty
# list is legitimate and does NOT mean the mode carries no claim. It must never
# be read as "run everything": `pytest` with no arguments collects the whole
# suite, which is the most expensive possible way to measure nothing.
run_claim_proofs() {
  local mode="$1" junit="$2"
  local -a nodeids=()
  local listing status line

  rm -f "${junit}"

  # Declared, then assigned on its own line, then the status read on its own
  # line. `local listing="$(...)"` returns the exit status of `local`, so a
  # failed resolver would look like a mode that simply carries no claim -- and
  # this run would then produce evidence asserting nothing.
  listing=""
  listing="$(claim_static_nodeids "${mode}" "${SESSION}")"
  status=$?
  [ "${status}" -eq 0 ] \
    || die 6 "could not resolve the claim proofs for ${mode} mode (exit ${status})."

  while IFS= read -r line; do
    [ -n "${line}" ] && nodeids+=("${line}")
  done <<<"${listing}"

  if [ "${#nodeids[@]}" -eq 0 ]; then
    printf 'Every proof of this mode'"'"'s claims carries its own marker; the suite above ran them all.\n'
    return 0
  fi

  "$(python_bin)" -m pytest -q --junitxml="${junit}" "${nodeids[@]}"
}

# One writer invocation for both evidence-writing modes. Two copies drifted
# apart once already in Session 2 -- the host branch gained --project-b-outputs
# and the external one did not, which the merge then reported as two different
# deployments.
write_evidence() {
  local mode="$1"
  local suite_junit="${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-${mode}-tests.xml"
  local claims_junit="${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-${mode}-claims.xml"

  local -a arguments=(
    --session "${SESSION}" --mode "${mode}"
    --junit "${suite_junit}"
    --output "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-${mode}.json"
  )
  # Session 22 (ADR 0202): an offline half measures a CHECKOUT, so it passes no
  # deployed document -- the writer refuses one, and would be right to: a half
  # naming a deployment it never read is the misreading the third mode exists
  # to prevent. The two live modes are unchanged.
  if [ "${mode}" != "offline" ]; then
    arguments+=(--project-a-outputs "${PROJECT_A_OUTPUTS}")
    [ -n "${PROJECT_B_OUTPUTS}" ] && arguments+=(--project-b-outputs "${PROJECT_B_OUTPUTS}")
  fi
  [ -f "${claims_junit}" ] && arguments+=(--junit "${claims_junit}")

  "$(python_bin)" bin/write-session-evidence.py "${arguments[@]}"
}

# Evidence is written only by a run that selected everything. -k is for iterating
# on one failure, and an evidence file produced from a filtered run would report
# a claim on the strength of whichever tests the expression happened to match.
evidence_is_supportable() {
  [ -z "${KEYWORD}" ]
}

announce_no_evidence() {
  printf '\nNo evidence written: -k selected a subset of the suite, so this run\n'
  printf 'cannot support a claim about the whole.\n'
}

# D212, as a hard failure rather than a skip (ADR 0073).
#
# The state comes from `tests/contract/rendered_fixtures.py`, which is already
# the authority on it, rather than from a second implementation here.
check_rendered_fixtures() {
  local state detail
  local report
  report="$(PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}/tests/contract" "$(python_bin)" -c \
    'import rendered_fixtures as f; print(f.STATE); print(f.DETAIL)')" \
    || die 6 "could not determine the rendered fixtures' state."

  state="$(printf '%s' "${report}" | sed -n 1p)"
  detail="$(printf '%s' "${report}" | sed -n 2p)"

  case "${state}" in
    current)
      printf 'rendered fixtures: %s\n' "${detail}"
      ;;
    absent|stale)
      die 6 "rendered fixtures are ${state}: ${detail}

A gate does not skip this. The compose-model proofs read those fixtures, and a
run that never collected them exits 0 having measured less than it reports --
which is D212. Re-render both projects ON THE HOST (D383 -- .generated/ is
gitignored and is never transported):

  ./deploy.sh --project project.example.yaml        --capabilities capabilities.example.yaml --render-only
  ./deploy.sh --project project.second.example.yaml --capabilities capabilities.example.yaml --render-only"
      ;;
    *)
      die 6 "unknown fixture state: ${state}"
      ;;
  esac
}

# Inherited from Session 9, unchanged, and still a precondition: the agent plane
# has to be served for the claims Session 11 carries forward. Session 11 adds no
# requirement over it, and it is kept rather than dropped because a gate that
# stopped checking it would let a Session 11 document report on a deployment
# whose agent plane was down.
#
# D326's two-stage convergence is the ordinary case, not an error: the deploy
# that FIRST starts an MCP container observes it before it is reachable, so
# `unavailable` is what a correct first deploy publishes. The answer is to
# deploy again.
check_agent_plane_is_published() {
  local document="$1"
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${document}" <<'PYTHON' || exit 6
import json
import sys
from pathlib import Path

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
route = (document.get("routes") or {}).get("mcp")
mcp = document.get("mcp") or {}

if not isinstance(route, dict):
    sys.exit(
        f"routes.mcp is {route!r}, not a published-route object. Outputs v12 publishes "
        "it as one; a string means this deployment predates the version that carries "
        "the agent plane, and evidence.py refuses a document that is not current -- so "
        "REDEPLOY before running this gate."
    )

if route.get("status") != "ready":
    sys.exit(
        f"routes.mcp is {route.get('status')!r}, not 'ready'. If an MCP container has "
        "just started for the first time, this is D326's two-stage convergence working "
        "as designed: the deploy observed the route before the edge had attached it. "
        "DEPLOY AGAIN and re-run."
    )

if mcp.get("status") != "ready" or not mcp.get("protocol_revision"):
    sys.exit(
        f"the mcp block is {mcp.get('status')!r} with protocol_revision "
        f"{mcp.get('protocol_revision')!r}. The route is served and the block is not, "
        "which is the asymmetry D395 found in the other direction."
    )

print(f"agent plane: {route['url']} at protocol {mcp['protocol_revision']}")
PYTHON
}

# **Session 10's own precondition**, and it is the reason this session has one.
# Session 10 releases NO migration -- Run 5 measured that every privilege an
# online backup wants is refused to a NOSUPERUSER object owner, so all five
# grants are bootstrap-plane -- so the ledger check Session 9 needed is not this
# session's dependency. What is:
#
#   1. the stanza exists in the repository;
#   2. at least one backup set exists;
#   3. the archiver is not currently failing.
#
# All three are read from ONE `bin/backup.sh info --json` per project, which is
# `backup_report.backup_state` -- the same function the deploy publishes from, so
# the gate and the deployed document cannot disagree about what a repository's
# report means (ADR 0149).
#
# **Nothing here reads an exit code from `pgbackrest info`.** It exits 0 in every
# state including a stanza that does not exist (D548), which is why the status is
# in a field. `bin/backup.sh info --json` exits 6 when the state is `failing`,
# and that is this command's own code rather than pgBackRest's.
#
# The second condition is the one an operator trips over: the first full backup
# of any project is a command at a TTY, deliberately, because it is the first
# operation that writes a meaningful amount to a repository nobody has paid for
# yet. Until it runs, the document says `awaiting_first_backup` and the drill has
# nothing to restore.
check_the_repository_is_ready() {
  local document="$1"
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${document}" <<'PYTHON' || exit 6
import json
import subprocess
import sys
from pathlib import Path

from agentic_postgres import backup_report

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
container = document["database"]["container"]
backup = document.get("backup") or {}
stanza = backup.get("stanza")

if not backup.get("enabled") or not stanza:
    sys.exit(
        f"backups are not enabled for {document['project']['key']}. Every Session 10 "
        "host claim measures a repository; there is nothing here to measure. Enable "
        "backup.enabled in the project manifest and redeploy."
    )

probe = subprocess.run(  # noqa: S603
    [
        "docker", "exec", "-u", "999", container,
        "pgbackrest", f"--stanza={stanza}", "info", "--output=json",
    ],
    capture_output=True,
    text=True,
    check=False,
    timeout=120,
)
# The EXIT CODE is deliberately not read. `pgbackrest info` exits 0 for a stanza
# that does not exist, for one with no backups and for a healthy one (D548), so
# the only thing checked is that it produced parseable JSON.
if not probe.stdout.strip():
    sys.exit(
        f"pgbackrest info produced no output in {container} (exit {probe.returncode}): "
        f"{probe.stderr.strip()[:300]}"
    )

try:
    summary = backup_report.summarise(json.loads(probe.stdout), stanza)
except ValueError as error:
    sys.exit(f"pgbackrest info could not be read for stanza {stanza}: {error}")

archiver = None
reader = subprocess.run(  # noqa: S603
    [
        "docker", "exec", "-i", container,
        "psql", "-U", "postgres", "-d", document["database"]["name"],
        "-X", "-qtA", "-F", backup_report.ARCHIVER_SEPARATOR,
        "-c", backup_report.ARCHIVER_QUERY,
    ],
    capture_output=True,
    text=True,
    check=False,
    timeout=60,
)
if reader.returncode == 0:
    archiver = backup_report.parse_archiver(reader.stdout)

state = backup_report.backup_state(summary, archiver)

if not state["stanza_created"]:
    sys.exit(
        f"stanza {stanza} does not exist in the repository. The deploy's step 6c "
        "creates it and fails the deploy if `pgbackrest check` fails, so a missing "
        "stanza here means this project has not been deployed through Session 10. "
        "DEPLOY FIRST."
    )

if not state["last_full_backup_label"]:
    sys.exit(
        f"stanza {stanza} holds no full backup, so the drill has nothing to restore "
        "and REC-PITR-001, REC-SAFE-001, REC-SMOKE-001 and REC-EVID-001 would all "
        "fail on the same missing thing.\n"
        "The first full backup of any project is an operator command at a TTY, by "
        "design -- it is the first operation that writes a meaningful amount to a "
        "repository nobody has paid for yet:\n"
        f"  sudo bin/backup.sh --outputs {sys.argv[1]} backup --type full"
    )

if state["status"] == backup_report.STATUS_FAILING:
    sys.exit(
        f"stanza {stanza} reports {state['status']!r}. WAL is not reaching the "
        f"repository (archived {state['wal_archived_count']}, failed "
        f"{state['wal_failed_count']}), so a point-in-time target between two writes "
        "may not be reachable at all. Repair archiving before gating: "
        f"sudo bin/backup.sh --outputs {sys.argv[1]} check"
    )

print(
    f"repository: {stanza} is {state['status']}, newest full "
    f"{state['last_full_backup_label']} at {state['last_full_backup_at']}, "
    f"latest proven recoverable {state['latest_recoverable_time']}"
)
PYTHON
}

# **Session 18's own precondition.** Every `REC-REPO-*` live proof reads a
# mirrored project: the manifest at schema 4 with `backup.mirror`, the mirror
# pair materialised, the unit pair installed, and one copy completed by hand
# so that a record exists. A project without a mirror would fail four
# requirements on one missing operator step, in a way that reads as a product
# defect; it is refused here, with the steps, before anything runs.
#
# Read from the deployed document and the record beside it -- the same
# readers the doctor and the fleet use (ADR 0188) -- and never from the
# document's `backup_state.mirror`, which is a deploy-time snapshot.
check_the_mirror_is_ready() {
  local document="$1"
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${document}" <<'PYTHON' || exit 6
import json
import sys
from pathlib import Path

from agentic_postgres import backup_report, config, deployed_output

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
key = document["project"]["key"]

if not config.backup_mirror_enabled(document):
    sys.exit(
        f"{key} declares no backup mirror. Every Session 18 repository claim measures "
        "the mirror; enable backup.mirror in the project manifest (schema 4), put the "
        "mirror pair under /backup at the provider, materialize, and redeploy."
    )

record = deployed_output.mirror_record_path(key)
if not record.is_file():
    sys.exit(
        f"{key} has no copy record at {record}: no mirror copy has completed. The first "
        "copy is an operator command at a TTY, by design:\n"
        f"  sudo bin/backup.sh --outputs {sys.argv[1]} mirror"
    )
parsed = backup_report.parse_mirror_record(record.read_text(encoding="utf-8"))
if parsed is None:
    sys.exit(f"{record} does not parse as a completed copy; run the copy again")

print(f"mirror: {key} copied {parsed['objects']} object(s) at {parsed['last_copied_at']}")
PYTHON
}

# **Session 21's own precondition.** Every `AGT-*` live half reads beta's lock
# carrying the tenant write and alpha's not, so both documents must be at
# outputs v18 from a deploy through this session, beta's manifest must name
# the example project for both keys, and the issuer must have come back on
# both -- a deploy through 21 recreates `auth` and `mcp` (ADR 0155). Refused
# here, with the step, before a suite reports forty refusals about one thing.
check_the_tenant_surface_is_deployed() {
  local alpha="$1" beta="$2"
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${alpha}" "${beta}" <<'PYTHON' || exit 6
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from agentic_postgres import CURRENT_SESSION, output_migrations

alpha = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
beta = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

for document in (alpha, beta):
    key = document["project"]["key"]
    version = document.get("schema_version")
    if version != output_migrations.CURRENT_VERSION:
        sys.exit(
            f"{key} publishes outputs v{version}; this gate reads v"
            f"{output_migrations.CURRENT_VERSION}. Deploy --through-session "
            f"{CURRENT_SESSION} first."
        )
    if (document.get("mcp") or {}).get("status") != "ready":
        sys.exit(f"{key}: the agent plane is not ready; deploy again (D326)")

if (beta.get("mcp") or {}).get("project_capabilities") is None:
    sys.exit(
        f"{beta['project']['key']} records no project capabilities. Its manifest on the "
        "host must be at schema 6 with `mcp.capabilities: projects/example` beside "
        "`migrations.set`, then deployed; every AGT-* live half reads that lock."
    )
if (alpha.get("mcp") or {}).get("project_capabilities") is not None:
    sys.exit(
        f"{alpha['project']['key']} records project capabilities, and it is the control "
        "that declares none. Alpha's manifest stays at schema 1 (D930)."
    )

for document in (alpha, beta):
    key = document["project"]["key"]
    route = (document.get("routes") or {}).get("app") or {}
    if route.get("status") != "ready" or not route.get("url"):
        sys.exit(f"{key} publishes no ready application route, so the issuer cannot be read")
    request = urllib.request.Request(  # noqa: S310 -- the deployed document's own https URL
        f"{route['url'].rstrip('/')}/auth/login",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as answer:  # noqa: S310
            status = answer.status
    except urllib.error.HTTPError as error:
        status = error.code
    except (urllib.error.URLError, TimeoutError) as error:
        sys.exit(
            f"{key}: /auth/login did not answer ({error}). A deploy through this session "
            "recreates the issuer (ADR 0155); wait for it to come back, then re-run."
        )
    if not 400 <= status < 500:
        sys.exit(f"{key}: /auth/login answered {status} to an empty body rather than a 4xx")
    print(f"issuer: {key} answers at {route['url']}")

# D1153: `tool_count` is null when the deploy could not confirm that the
# running plane had loaded the lock on disk. "None tools" would read as a
# measurement; "unconfirmed" is what it is.
def tools(document):
    count = document["mcp"]["tool_count"]
    return "an unconfirmed number of" if count is None else str(count)


print(
    f"tenant surface: {beta['project']['key']} carries "
    f"{beta['mcp']['project_capabilities']['root']} "
    f"({tools(beta)} tools); {alpha['project']['key']} carries none "
    f"({tools(alpha)} tools)"
)
PYTHON
}

mode_offline() {
  step "1. Static quality"
  # `bin/lib/*.sh` is SOURCED, not executed, so `bin/*.sh` does not reach it --
  # and a shellcheck run that does not hold a sourced file among its inputs
  # emits SC1091 and exits non-zero, which under `set -e` ends the gate at step
  # 1. `deploy.sh:27` has sourced `bin/lib/tty-guard.sh` since Session 30 Run 3;
  # that run added this glob to `bin/session-01-check.sh` and to no other caller
  # (D1564). A library nothing lints is a library whose refusal nobody checks.
  shellcheck deploy.sh bin/*.sh bin/lib/*.sh libexec/*
  "$(python_bin)" -m ruff check src bin tests
  "$(python_bin)" -m ruff format --check src bin tests
  bin/lock-versions.sh --check

  step "2. Rendered fixtures are current"
  check_rendered_fixtures

  # Session 22 (DEV-ENV-001). **Checked, not skipped.** Every cluster fixture in
  # the suite -- the six inherited ones and this session's `apg dev` module --
  # skips when there is no daemon, and a skip is not a pass: the offline half
  # this mode now writes would report `dev_environment` as `not_run` and exit 5
  # after producing a document that looks like evidence. An absent daemon is a
  # missing PREREQUISITE for this mode, so it is exit 3 and says what to start.
  step "2b. Docker is available"
  docker version --format '{{.Server.Version}}' >/dev/null 2>&1 \
    || die 3 "docker is not available, and offline mode needs it in three places:
DEV-ENV-001's proofs stand a cluster up with the product's own command and step
8 runs the five verbs; GEN-TOOLCHAIN-001 builds the hash-locked toolchain image
and step 8b typechecks the committed client in it; and GEN-HASH-001's offline
half stands up a cluster, a PostgREST and the pinned edge to check a generated
client against a surface something is actually serving. Without a daemon all of
it SKIPS, and a skipped proof makes the claim not_run rather than failing -- a
half that proves less than it appears to. Start Docker and run this again."
  printf 'docker server %s\n' "$(docker version --format '{{.Server.Version}}')"

  # Session 22: the suite's JUnit is KEPT now, because step 9 computes the
  # offline half's verdicts from it. Every earlier offline mode discarded it,
  # which was correct while offline mode wrote nothing.
  mkdir -p "${EVIDENCE_DIR}"
  step "3. Offline contract suite"
  # **A failing proof does not stop the evidence being written** (D1373, D1487).
  # Session 25 repaired this in BOTH LIVE MODES and left the offline one under
  # `set -e` with a bare call, so any failing proof ended the run before step 9
  # -- no half written, and an exit of 1, which is not a code this gate's header
  # documents. That is D1373's own defect surviving in the mode it was not
  # applied to. **Measured, not reasoned, on the gate this one was derived
  # from**: its first run exited 1 with `session-28-offline-tests.xml` written
  # and `session-28-offline.json` absent. FIVE of this session's six claims are
  # offline -- more than any session has declared -- so a single red proof
  # anywhere in the suite would close the session having reported none of
  # them.
  suite_status=0
  run_suite "p0 and not future and not live_host and not external" \
    "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-offline-tests.xml" || suite_status=$?
  if [ "${suite_status}" -ne 0 ]; then
    printf '\n\033[1m%s: the suite reported failures (pytest exit %s).\033[0m\n' \
      "${PROGRAM}" "${suite_status}"
    printf 'The evidence below is written anyway, from the JUnit it wrote: a claim whose\n'
    printf 'proof failed is FAILED, which is a RESULT and not an absence of one.\n'
  fi

  step "4. Environment-gated tests collect and skip"
  # A module that opened a socket at import time would break collection for the
  # whole suite, and this is the cheapest place to find that out. It is also the
  # only offline check that touches this session's new deployment modules.
  run_suite "live_host or external" ""

  step "5. Models resolve"
  bin/compose.sh --edge --host host.example.yaml config >/dev/null
  printf 'edge model resolves\n'

  step "6. The reviewed API surfaces and the capability contract"
  bin/api-contract.sh --check
  bin/app-contract.sh --check
  # Inherited: the compiled, project-neutral capability contract, and the
  # check path contains no writer (ADR 0119, ADR 0120).
  bin/mcp-contract.sh check
  # Session 16 (inherited): each example project's profile applied to the approved contract
  # and refused if it would widen any bound (ADR 0183). Compile time is HERE,
  # with no host and no root, and at the deploy's lock step -- never at request
  # time.
  bin/mcp-contract.sh check --project project.example.yaml
  bin/mcp-contract.sh check --project project.second.example.yaml
  # Session 16 (inherited): the evaluation report is current, and the render REFUSES when
  # an enabled capability has no cases or a written case is bound to a version
  # the contract no longer declares (ADR 0184). This is the gate's half of
  # EVAL-HARNESS-001; the harness proofs themselves ran in step 3.
  "$(python_bin)" bin/render-evaluation-report.py --check
  # Session 21 (ADR 0201): `check --project project.example.yaml` above now
  # also compares the example project's committed contract byte for byte
  # with what its manifest compiles to, and this checks the project's own
  # report beside it -- the gate's half of EVAL-HARNESS-002.
  "$(python_bin)" bin/render-evaluation-report.py --check --project project.example.yaml
  # Session 17 (inherited): the bounds document carries the lifecycle relation, and the
  # example manifests are at project schema version 3 -- both are read by the
  # render in step 3; here the generated table is checked current.
  "$(python_bin)" bin/render-config.py --bounds-doc --check
  # Session 23 (GEN-VERSION-001, D1208). The committed example client is what
  # its contract generates, asked by running the product's own command rather
  # than by re-emitting and comparing (D1114). It belongs beside the contract
  # checks above and not with the typecheck below, because the two answer
  # different questions: this one asks whether the artefact is CURRENT, and a
  # stale client is usually still perfectly valid TypeScript.
  bin/apg.sh generate --check --project project.example.yaml
  # Session 18 adds no offline step here: its four offline modules ran in
  # step 3, and the eight rehearsal plans need a deployed document (0600
  # root) to plan against, so --plan is a host-mode reading.

  step "7. Registry and generated documentation"
  "$(python_bin)" -m pytest -q tests/contract/test_acceptance_registry.py
  "$(python_bin)" bin/render-acceptance-matrix.py --check
  # Session 25 (DX-DOC-001, ADR 0201, D1309). A project's OWN tools get a
  # catalog at projects/<slug>/docs/mcp-tool-catalog.md, written by the same
  # renderer that writes the release's and drift-checked the same way. Run 4
  # put this line in bin/session-01-check.sh's step 6; it is here too because
  # this session's claim is the one that depends on it, and because a gate is
  # what an operator runs before a release. The release catalog's own check
  # stays in the Session 1 gate, which this one does not replace.
  "$(python_bin)" bin/render-mcp-catalog.py --check --project project.example.yaml

  # Session 22 (DEV-CI-001's twin). The suite already exercises every verb; what
  # this adds is the ROUND TRIP in the order a developer takes it, through
  # bin/apg.sh rather than through a fixture. CI runs the same five lines on a
  # machine nobody prepared (.github/workflows/ci.yml), and this is the half an
  # operator can run before pushing.
  #
  # `down` first, because a gate is re-run to confirm a fix and the second run
  # must start where the first did (D20).
  step "8. The local environment round trip"
  bin/apg.sh dev down --project project.example.yaml >/dev/null
  bin/apg.sh dev up --project project.example.yaml
  bin/apg.sh dev status --project project.example.yaml
  bin/apg.sh dev seed --project project.example.yaml example
  bin/apg.sh dev reset --project project.example.yaml
  bin/apg.sh dev down --project project.example.yaml

  # Session 23 (GEN-TOOLCHAIN-001). The compiler is the only total check a
  # generator's output has, and not running it declines it (D1223) -- the first
  # emitted package passed every structural proof and did not compile. The
  # image is built from this checkout with the pinned BASE_IMAGE, and the run
  # takes `smoke`, so the package is EXECUTED and not merely typechecked: the
  # second emitted package typechecked at exit 0 and could not run at all
  # (D1226). `--network none` is the image's own default and matters here --
  # `npx tsc` would resolve from the working directory and fetch (D1225),
  # inside a claim declared offline. The smoke has no URL, so it reports
  # `unreachable` and exits 2 by design; what is asserted is the typecheck,
  # which is the exit the image gives before it ever runs node.
  step "8b. The generated client typechecks on the pinned toolchain"
  # ONE value out of the lock, read rather than sourced. `set -a; . versions.env`
  # would export every name in it into the rest of this process -- step 9 writes
  # evidence after this -- and a gate whose later steps inherit forty variables
  # from an earlier one depends on the order it happened to run in.
  # `awk`, not `sed ... | head`, and not for taste: test_cli_contract scans
  # every command for `env | `, which a pipe out of a file named *.env matches
  # exactly. The guard is right about the class it protects, so the script is
  # what changes.
  local base_image
  base_image="$(awk -F= '$1 == "NODE_RUNTIME_IMAGE" { print $2; exit }' versions.env)"
  [ -n "${base_image}" ] || die 3 "versions.env carries no NODE_RUNTIME_IMAGE, so the
toolchain image would be built on whatever \`node:22-alpine\` resolves to today.
Run bin/lock-versions.sh --check."
  docker build -q --build-arg "BASE_IMAGE=${base_image}" \
    -t apg-client-typescript services/clients/typescript >/dev/null
  docker run --rm -v "${ROOT_DIR}/projects/example/clients/typescript:/work:ro" \
    apg-client-typescript

  # Session 24 (STU-SUPPLY-001), inherited. Cheap, and the SENTENCE is what it is
  # for: the
  # claim ADR 0205 makes about Studio is mostly about what is NOT there, and a
  # decision kept by nobody noticing it is one commit away from being untrue.
  # Step 3 already collected this module by its marks; running it by name here
  # is what puts the words in front of an operator reading the gate's output.
  step "8c. Studio ships no third-party code"
  "$(python_bin)" -m pytest -q tests/contract/test_studio_assets.py

  # Session 22 introduced this step (ADR 0202) and Session 28 keeps it. TWO of
  # this session's THREE claims are declared offline -- `project_set_release_record`
  # and `release_reading` -- and the one that is not is the reason the
  # declaration is worth having: a checkout cannot say what two tables nine
  # sessions of trips have written to are carrying, nor that a prune removes a
  # row of that record, and folding `agent_record_retention` in would prove a
  # retention claim against history the proof itself seeded (D940). The
  # half is written from step 3's JUnit -- the run that selected everything --
  # for the reason every other half is: a verdict computed from a
  # differently-selected run is a verdict about a different collection.
  #
  # No `run_claim_proofs offline` beside it, and the reason is the property
  # ADR 0202 leans on: every proof of an offline claim is markerless, so step
  # 3's sweep already collected all of them. A second selective run would
  # measure the same tests twice and write a second JUnit saying so.
  step "9. Offline evidence"
  if evidence_is_supportable; then
    # The writer's own status is the authority on 5, exactly as in the two live
    # modes: it returns it when a claim's node ids did not all pass.
    evidence_status=0
    write_evidence offline || evidence_status=$?
    if [ "${evidence_status}" -ne 0 ]; then
      exit "${evidence_status}"
    fi
    printf 'This is one half of three. Session %s also needs --mode host and\n' "${SESSION}"
    printf -- '--mode external, which are this session'"'"'s own trip; see --help.\n'
    printf -- 'No session before this one is owed a half: 26 and 27 registered\n'
    printf -- 'nothing, 29 took the trip that paid 28'"'"'s, and Session 24'"'"'s\n'
    printf -- 'trip paid 22, 23 and 24 (D1244).\n'
  else
    announce_no_evidence
  fi

  # A red proof OUTSIDE every claim is still a red proof, and it is reported as
  # exit 6 rather than swallowed -- the same sentence the host mode gives, for
  # the same reason. The half is written first; the verdict comes after it.
  if [ "${suite_status}" -ne 0 ]; then
    die 6 "the evidence is written and every claim in it passed, but the suite \
reported failures. A proof outside every claim went red; read \
${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-offline-tests.xml."
  fi

  printf '\n\033[1m%s: offline PASSED\033[0m\n' "${PROGRAM}"
}

mode_host() {
  # Arguments before privilege, deliberately. An operator iterating on a command
  # line should learn they mistyped a flag without first having to obtain root
  # to be told.
  [ -n "${HOST_MANIFEST}" ] || die 2 "--mode host requires --host."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"
  [ -n "${PROJECT_A_OUTPUTS}" ] || die 2 "--mode host requires --project-a-outputs."
  [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found: ${PROJECT_A_OUTPUTS}"

  [ -n "${PROJECT_B_OUTPUTS}" ] \
    || die 2 "--mode host requires --project-b-outputs: the isolation claim is about two projects."
  [ -f "${PROJECT_B_OUTPUTS}" ] || die 2 "not found: ${PROJECT_B_OUTPUTS}"

  # Checked here, before root is demanded and before anything runs. A path with
  # a typo in it is otherwise discovered after `sudo`, in a suite that skips the
  # proof the flag exists to admit -- and a skip is indistinguishable from "no
  # rotation happened in this run", which is the honest reading of the flag's
  # absence and the wrong reading of its misspelling.
  # Session 18's five declarations are in this gate again (D1133), so they
  # are in this loop again -- the loop and the flags move together (D1108:
  # a pre-flight over a variable the gate no longer declares is `set -u`
  # before anything is checked). The two directories are checked as
  # directories.
  local file directory
  for file in "${SENTINEL_FILE}" "${ADMIN_PASSWORD_FILE}" "${ROTATED_FROM_FILE}" \
              "${ROTATED_AUTHENTICATOR_FROM_FILE}" "${ROTATED_DOCS_FROM_FILE}" \
              "${ROTATED_JWT_FROM_FILE}" "${REDEPLOY_BEFORE_FILE}" \
              "${FRESH_HOST_OUTPUTS}" "${REMOVED_PROJECT_FILE}" \
              "${DX_RECORD_FILE}" "${REPLACEMENT_HOST_OUTPUTS}" \
              "${REPLACEMENT_BOOTSTRAP_STATE}" "${RESTORE_EVIDENCE_FILE}"; do
    [ -z "${file}" ] || [ -f "${file}" ] || die 2 "not found: ${file}"
  done
  for directory in "${KIT_DIR}" "${REHEARSAL_EVIDENCE_DIR}"; do
    [ -z "${directory}" ] || [ -d "${directory}" ] || die 2 "not a directory: ${directory}"
  done

  [ "$(id -u)" -eq 0 ] || die 3 "--mode host requires root: it reads root-only host state."

  # Said rather than refused. A window in which the operator does not have the
  # administrator's password to hand is a legitimate run, and the claims it
  # cannot prove will report `not_run` -- which is the evidence model working.
  if [ -z "${ADMIN_PASSWORD_FILE}" ]; then
    printf '%s: no --admin-password-file, so the proofs needing an\n' "${PROGRAM}"
    printf 'administrator session will skip, and every claim they support will report\n'
    printf 'not_run. Session 21'"'"'s agent_tenant_surface is one of them: the ceiling\n'
    printf 'at agent creation is measured through the admin endpoint, as an administrator.\n'
  fi

  step "1. Host baseline, unchanged by this run"
  bin/provision-host.sh --host "${HOST_MANIFEST}" --check

  step "2. Rendered fixtures are current"
  check_rendered_fixtures

  step "3. The agent plane is published"
  check_agent_plane_is_published "${PROJECT_A_OUTPUTS}"

  step "4. The repository is ready"
  # Both projects, because the claims are measured over both and a project whose
  # first full backup nobody has taken would fail four requirements on one
  # missing thing, in a way that reads as a product defect rather than as a
  # deliberate operator step.
  check_the_repository_is_ready "${PROJECT_A_OUTPUTS}"
  check_the_repository_is_ready "${PROJECT_B_OUTPUTS}"

  step "4b. The mirror is enabled and has copied, on both projects"
  check_the_mirror_is_ready "${PROJECT_A_OUTPUTS}"
  check_the_mirror_is_ready "${PROJECT_B_OUTPUTS}"

  step "4c. The tenant surface is deployed on beta, not on alpha, and the issuer answers"
  check_the_tenant_surface_is_deployed "${PROJECT_A_OUTPUTS}" "${PROJECT_B_OUTPUTS}"

  step "5. Host-local acceptance suite, over two projects"
  mkdir -p "${EVIDENCE_DIR}"
  # On EXIT, not after the last step: the evidence is written whether or not the
  # suite passed, and a failing gate is the run whose output an operator most
  # needs to read.
  trap restore_evidence_ownership EXIT
  export APG_LIVE_HOST=1
  export APG_EDGE_DEPLOYED=1
  export APG_PROJECT_A_OUTPUTS="${PROJECT_A_OUTPUTS}"
  export APG_PROJECT_B_OUTPUTS="${PROJECT_B_OUTPUTS}"
  [ -n "${SENTINEL_FILE}" ] && export APG_SECRET_SENTINEL_FILE="${SENTINEL_FILE}"
  # NOT in `tests/conftest.py`'s roster, deliberately (D1278), and this gate
  # said it was until D1595 measured it. What consumes it is the
  # `admin_password` FIXTURE in tests/deployment/conftest.py, which SKIPS with
  # the variable's name when it is unset -- so a sweep run outside a window
  # where the operator had the password to hand is a legitimate run and the
  # claims it cannot prove come out `not_run`.
  #
  # It cannot simply join the roster: `test_every_registered_variable_is_used`
  # calls an entry used when a test module declares it on a marker or names it
  # as a constant, and `all_test_modules()` is `rglob("test_*.py")` -- it does
  # not walk conftests, which is the only place this name appears. Adding it
  # would read as unused on the day it was added. Widening that scan is a
  # change to a guard several other checks share and is section 10's item.
  [ -n "${ADMIN_PASSWORD_FILE}" ] && export APG_ADMIN_PASSWORD_FILE="${ADMIN_PASSWORD_FILE}"
  [ -n "${ROTATED_FROM_FILE}" ] && export APG_ROTATED_FROM_FILE="${ROTATED_FROM_FILE}"
  # One variable per credential. A window rotates one at a time, and a single
  # flag would admit all three proofs on the strength of whichever was actually
  # rotated.
  [ -n "${ROTATED_AUTHENTICATOR_FROM_FILE}" ] &&
    export APG_ROTATED_AUTHENTICATOR_FROM_FILE="${ROTATED_AUTHENTICATOR_FROM_FILE}"
  [ -n "${ROTATED_DOCS_FROM_FILE}" ] && export APG_ROTATED_DOCS_FROM_FILE="${ROTATED_DOCS_FROM_FILE}"
  # D687, and the sentence is about the session that found it rather than this
  # one: `deployment_convergence` was one of ITS claims and the gate could not
  # pass the flag that admits it -- the variable was read only by the test, so
  # both DEP-002 proofs skipped and the claim reported unproved in a run that
  # had otherwise measured everything. Question 5, committed while writing the
  # gate that records the claim. It is not one of Session 28's three (D1488).
  [ -n "${REDEPLOY_BEFORE_FILE}" ] && export APG_REDEPLOY_BEFORE_FILE="${REDEPLOY_BEFORE_FILE}"
  [ -n "${FRESH_HOST_OUTPUTS}" ] && export APG_FRESH_HOST_OUTPUTS="${FRESH_HOST_OUTPUTS}"
  [ -n "${REMOVED_PROJECT_FILE}" ] && export APG_REMOVED_PROJECT_FILE="${REMOVED_PROJECT_FILE}"
  [ -n "${DX_RECORD_FILE}" ] && export APG_DX_RECORD_FILE="${DX_RECORD_FILE}"
  # Session 21 exports NOTHING new of its own (D687 read from the other end):
  # every live half this session adds reads `APG_LIVE_HOST`, the two outputs
  # and `APG_ADMIN_PASSWORD_FILE` -- the first three in the roster, the fourth
  # NOT in it and read by a fixture instead (see the export line above; the
  # claim that all four were in the roster was this sentence's, and D1595
  # measured it false). All four are exported here, so `pytest --setup-plan`
  # can answer "will these run" before the trip.
  #
  # Session 18's five declarations are exported again (D1133). They admit that
  # session's kit, replacement and rehearsal proofs, which THIS sweep runs
  # (claims_through_session is cumulative), and a proof that skips here for
  # want of its declaration outvotes the pass an older gate recorded when
  # the JUnits are merged (D1123). One sweep writes the host half.
  [ -n "${KIT_DIR}" ] && export APG_KIT_DIR="${KIT_DIR}"
  [ -n "${REPLACEMENT_HOST_OUTPUTS}" ] &&
    export APG_REPLACEMENT_HOST_OUTPUTS="${REPLACEMENT_HOST_OUTPUTS}"
  [ -n "${REPLACEMENT_BOOTSTRAP_STATE}" ] &&
    export APG_REPLACEMENT_BOOTSTRAP_STATE="${REPLACEMENT_BOOTSTRAP_STATE}"
  [ -n "${RESTORE_EVIDENCE_FILE}" ] && export APG_RESTORE_EVIDENCE_FILE="${RESTORE_EVIDENCE_FILE}"
  [ -n "${REHEARSAL_EVIDENCE_DIR}" ] &&
    export APG_REHEARSAL_EVIDENCE_DIR="${REHEARSAL_EVIDENCE_DIR}"
  # Session 14, and D687's rule applied on the day rather than after it: a
  # variable a test reads and no gate exports is a proof that skips, and a
  # claim that comes back unproved in a run that measured everything else.
  [ -n "${INDUCED_ALERT_FILE}" ] &&
    export APG_INDUCED_ALERT_FILE="${INDUCED_ALERT_FILE}"
  [ -n "${ROTATED_JWT_FROM_FILE}" ] && export APG_ROTATED_JWT_FROM_FILE="${ROTATED_JWT_FROM_FILE}"
  [ "${AFTER_REBOOT}" -eq 1 ] && export APG_AFTER_REBOOT=1

  # `-m live_host` with NO PATH, and that is D211. The sweep everyone had been
  # using was `pytest tests/deployment -m live_host`, which selects by path --
  # so tests/security/ was a directory it never reached, and five green host
  # runs were five reports about a subset nobody had stated the boundary of.
  # **A failing proof does not stop the evidence being written** (D1373).
  # Under `set -e` this call used to end the run, so steps 6 and 7 never ran and
  # a claim that is genuinely FALSE could not be recorded as `failed` -- the
  # status ADR 0163 defines, `claim_result` computes, and the header above
  # documents as exit 5. Session 25's walk record is the first false claim this
  # project has had, and it took the whole host half with it.
  suite_status=0
  run_suite "live_host" "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-host-tests.xml" || suite_status=$?
  if [ "${suite_status}" -ne 0 ]; then
    printf '\n\033[1m%s: the suite reported failures (pytest exit %s).\033[0m\n' \
      "${PROGRAM}" "${suite_status}"
    printf 'The evidence below is written anyway, from the JUnit it wrote: a claim whose\n'
    printf 'proof failed is FAILED, which is a RESULT and not an absence of one.\n'
  fi

  if ! evidence_is_supportable; then
    announce_no_evidence
    printf '\n\033[1m%s: host PASSED\033[0m\n' "${PROGRAM}"
    return 0
  fi

  step "6. Static proofs of the claims this run records"
  run_claim_proofs host "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-host-claims.xml"

  step "7. Host evidence"
  # The writer's own status is the authority on 5: it returns it when a claim's
  # node ids did not all pass. Captured rather than inherited so the suite's
  # status can still be reported when the writer is content.
  evidence_status=0
  write_evidence host || evidence_status=$?
  if [ "${evidence_status}" -ne 0 ]; then
    exit "${evidence_status}"
  fi
  if [ "${suite_status}" -ne 0 ]; then
    die 6 "the evidence is written and every claim in it passed, but the suite \
reported failures. A proof outside every claim went red; read ${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-host-tests.xml."
  fi

  printf '\n\033[1m%s: host PASSED\033[0m\n' "${PROGRAM}"
  printf 'This is one half of three. Session %s also needs --mode external and\n' "${SESSION}"
  printf -- '--mode offline, whose claims no deployment can answer; see --help.\n'
}

mode_external() {
  [ -n "${PUBLIC_IPV4}" ] || die 2 "--mode external requires --public-ipv4."
  [ -n "${PROJECT_A_OUTPUTS}" ] || die 2 "--mode external requires --project-a-outputs."
  [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found: ${PROJECT_A_OUTPUTS}"

  [ -n "${SSH_DESTINATION}" ] \
    || die 2 "--mode external requires --ssh-destination: the helper and the broker are reached over SSH."

  # Optional, and not exported: no external test reads project B. It is here
  # because the merge compares which deployment each half described.
  [ -z "${PROJECT_B_OUTPUTS}" ] || [ -f "${PROJECT_B_OUTPUTS}" ] \
    || die 2 "not found: ${PROJECT_B_OUTPUTS}"

  # Not enforceable from here -- the host could be behind the same NAT as the
  # operator -- so it is stated rather than checked, and the suite carries its
  # own positive control: 443 must answer, or every "closed" result below is a
  # statement about this network rather than about the host.
  printf '%s: this mode is only meaningful from a network that is\n' "${PROGRAM}"
  printf 'not the deployment host. A scan run on the host measures its own\n'
  printf 'routing table -- and the agent plane'"'"'s health routes answer 200 there,\n'
  printf 'which is exactly the difference this mode exists to observe.\n'

  step "1. The agent plane is published"
  check_agent_plane_is_published "${PROJECT_A_OUTPUTS}"

  step "2. Public-path and helper acceptance suite"
  mkdir -p "${EVIDENCE_DIR}"
  trap restore_evidence_ownership EXIT
  export APG_PUBLIC_IPV4="${PUBLIC_IPV4}"
  export APG_PROJECT_A_OUTPUTS="${PROJECT_A_OUTPUTS}"
  export APG_SSH_DESTINATION="${SSH_DESTINATION}"
  [ -n "${PUBLIC_IPV6}" ] && export APG_PUBLIC_IPV6="${PUBLIC_IPV6}"

  # D1373, the same repair in the other live mode: repairing one caller of a
  # decision and not the other is §7's fifth question.
  suite_status=0
  run_suite "external" "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-external-tests.xml" || suite_status=$?
  if [ "${suite_status}" -ne 0 ]; then
    printf '\n\033[1m%s: the suite reported failures (pytest exit %s); the evidence is written anyway.\033[0m\n' \
      "${PROGRAM}" "${suite_status}"
  fi

  if ! evidence_is_supportable; then
    announce_no_evidence
    printf '\n\033[1m%s: external PASSED\033[0m\n' "${PROGRAM}"
    return 0
  fi

  step "3. Static proofs of the claims this run records"
  run_claim_proofs external "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-external-claims.xml"

  step "4. External evidence"
  evidence_status=0
  write_evidence external || evidence_status=$?
  if [ "${evidence_status}" -ne 0 ]; then
    exit "${evidence_status}"
  fi
  if [ "${suite_status}" -ne 0 ]; then
    die 6 "the evidence is written and every claim in it passed, but the suite \
reported failures. Read ${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-external-tests.xml."
  fi

  printf '\n\033[1m%s: external PASSED\033[0m\n' "${PROGRAM}"
  printf 'This is one half of three. Session %s also needs --mode host and\n' "${SESSION}"
  printf -- '--mode offline, whose claims no deployment can answer; see --help.\n'
}

main() {
  parse_arguments "$@"
  case "${MODE}" in
    offline) mode_offline ;;
    host) mode_host ;;
    external) mode_external ;;
  esac
}

main "$@"

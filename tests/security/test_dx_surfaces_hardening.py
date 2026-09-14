"""`SEC-DX-001` -- the closing review of the three DX surfaces (stage plan §8).

Stage 3 built three surfaces whose job is to put a human in front of a
deployment: `apg dev` (ADR 0203), `apg generate` (ADR 0204) and `apg studio`
(ADR 0205). Each shipped with its own negative tests, in its own session, and
nothing has ever asked the question the stage plan's §8 asks: **for each
invariant, and for each of the three surfaces, which proof holds it?**

**A list of proofs is not an answer to that question.** The three sessions'
§8 sections are prose, one bullet per invariant the session happened to touch,
and prose cannot say what is MISSING. `HARDENING_MATRIX` is the same content as
a total function: sixteen invariants times three surfaces, forty-eight cells,
and every cell carries either a node id or the reason the invariant does not
reach that surface. A cell that is neither does not exist, because the type
does not allow one.

**Two guards make the matrix more than a document.** Every node id it names must
exist and be COLLECTED by the sweep that would record this claim -- D1242's
lesson, where about fifty proofs turned out to be collected by no sweep at all
-- and every invariant the stage plan lists must appear as a key for all three
surfaces, so an invariant cannot be dropped by being forgotten.

**And a cell may honestly say "not applicable".** ADR 0195's shape at the level
of a review: the third answer is *this invariant does not reach this surface*,
and it is written down with its reason rather than left blank. A blank is
indistinguishable from an oversight, which is what a review is for.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

# `tests/contract` is on the path when a contract module is collected and not
# when this directory is run alone, so the selector's home is named explicitly.
# **Imported and never retyped** (D486, D1242): the selector is one fact, and a
# copy of it here would be a second one that goes stale the session the gate
# changes -- which is exactly the failure the guard it comes from exists for.
sys.path.insert(0, str(REPO_ROOT / "tests" / "contract"))

from test_acceptance_registry import OFFLINE_SWEEP_SELECTOR

pytestmark = [pytest.mark.security, pytest.mark.p0, pytest.mark.contract]

APG = REPO_ROOT / "bin" / "apg.sh"

#: The three surfaces under review, and the verb each is reached by.
SURFACES = ("dev", "generate", "studio")

#: Every invariant the stage plan's §8 table lists, in its own words.
#:
#: Copied verbatim rather than paraphrased: the matrix is a claim about THAT
#: table, and a paraphrase would let a row drift out of the review without
#: anything noticing. `test_the_matrix_covers_every_invariant_the_stage_plan_lists`
#: reads the table out of the plan and compares.
INVARIANTS = (
    "PostgreSQL is the final authorization authority",
    "A project's identities are derived once, in `naming`",
    "An agent cannot run SQL",
    "A human cannot run SQL through a product surface",
    "The DX layer holds nothing the human does not hold",
    "A revoked token stops on its next request, locally",
    "An unauditable write does not happen",
    "An agent record carries no URL, key, token or caller value",
    "The MCP runtime holds no credential",
    "One service cannot read another's credential",
    "A restore never overwrites the active volume",
    "A workstation holds no production secret",
    "Projects share no project-scoped value",
    "There is no public Postgres endpoint",
    "A deploy over a broken archiver fails",
    "A report may not substitute an answer for a failure to determine one",
)

#: A cell the invariant does not reach. The reason is the value: a blank is
#: indistinguishable from an oversight, and this is a review.
#:
#: Every OTHER cell is a node id, and every one of those turned out to be
#: collected by the offline sweep -- which is what makes `SEC-DX-001` a
#: declarable offline claim rather than one waiting on a host.
NA = "not applicable: "

#: Every §8 invariant, for every surface. Forty-eight cells, no blanks.
#:
#: **Filled from the three sessions' own §8 lists first** (Sessions 22, 23 and
#: 24), by node id, and only the cells those lists left empty got a new proof in
#: Session 25. Four names in Session 23's list did not resolve to anything --
#: they were written before the proofs' names settled and never reconciled
#: (D1333) -- and the resolved names are what appear here.
HARDENING_MATRIX: dict[tuple[str, str], str] = {
    # --- PostgreSQL is the final authorization authority ---------------------
    ("PostgreSQL is the final authorization authority", "dev"): (
        "tests/contract/test_dev_environment_cluster.py::"
        "test_the_seeded_rows_are_visible_to_the_application_role_only_with_the_subject"
    ),
    ("PostgreSQL is the final authorization authority", "generate"): (
        "tests/contract/test_generated_client_runtime.py::"
        "test_a_refused_write_arrives_as_the_pt_code_the_database_raised"
    ),
    ("PostgreSQL is the final authorization authority", "studio"): (
        "tests/contract/test_studio_runtime.py::test_a_query_as_a_returns_as_rows_and_none_of_bs"
    ),
    # --- A project's identities are derived once, in `naming` ----------------
    ("A project's identities are derived once, in `naming`", "dev"): (
        "tests/contract/test_dev_environment.py::"
        "test_the_state_root_and_the_document_root_are_the_checkouts_and_never_the_hosts"
    ),
    ("A project's identities are derived once, in `naming`", "generate"): (
        "tests/contract/test_client_typescript.py::test_the_emitter_reads_the_ir_and_nothing_else"
    ),
    ("A project's identities are derived once, in `naming`", "studio"): (
        "tests/contract/test_studio_command.py::"
        "test_a_password_argument_or_environment_variable_is_refused"
    ),
    # --- An agent cannot run SQL ---------------------------------------------
    ("An agent cannot run SQL", "dev"): (
        NA + "`apg dev` serves no agent. It builds a cluster and applies a "
        "migration set; there is no agent plane in it to reach SQL through, and "
        "the seed door is a manifest name rather than a statement "
        "(tests/contract/test_dev_environment.py::test_seed_takes_a_name_and_never_a_path "
        "holds that separate door)."
    ),
    ("An agent cannot run SQL", "generate"): (
        "tests/contract/test_client_typescript.py::"
        "test_a_write_wrapper_requires_the_two_reserved_parameters"
    ),
    ("An agent cannot run SQL", "studio"): (
        "tests/contract/test_studio_core.py::test_the_forwarder_table_has_no_rest_write"
    ),
    # --- A human cannot run SQL through a product surface --------------------
    ("A human cannot run SQL through a product surface", "dev"): (
        "tests/contract/test_dev_environment.py::"
        "test_the_seed_lint_refuses_ddl_and_app_private_and_accepts_the_example_seed"
    ),
    ("A human cannot run SQL through a product surface", "generate"): (
        "tests/contract/test_client_typescript.py::"
        "test_a_request_names_only_reviewed_columns_operators_and_arguments"
    ),
    ("A human cannot run SQL through a product surface", "studio"): (
        "tests/contract/test_studio_core.py::"
        "test_rest_query_refuses_a_relation_a_column_or_an_operator_the_surface_does_not_name"
    ),
    # --- The DX layer holds nothing the human does not hold ------------------
    ("The DX layer holds nothing the human does not hold", "dev"): (
        "tests/security/test_dx_surfaces_hardening.py::"
        "test_no_dx_artefact_carries_a_credential_but_the_two_declared_files"
    ),
    ("The DX layer holds nothing the human does not hold", "generate"): (
        "tests/contract/test_client_typescript.py::"
        "test_no_emitted_file_carries_a_credential_a_token_or_a_url_with_userinfo"
    ),
    ("The DX layer holds nothing the human does not hold", "studio"): (
        "tests/contract/test_studio_server.py::test_studio_holds_no_key_and_verifies_nothing"
    ),
    # --- A revoked token stops on its next request, locally ------------------
    ("A revoked token stops on its next request, locally", "dev"): (
        NA + "`apg dev` issues no token that outlives it. The dev subject's "
        "verifier verifies nothing and the environment has no login path (D1171), "
        "so there is nothing to revoke -- `down` removes the container and the "
        "subject with it."
    ),
    ("A revoked token stops on its next request, locally", "generate"): (
        NA + "a generated client HOLDS a token the caller supplied and issues "
        "none. Revocation is the issuer's; what the client owes is that a refused "
        "call is classified rather than relayed, which is this table's "
        "*a report may not substitute an answer* row."
    ),
    ("A revoked token stops on its next request, locally", "studio"): (
        "tests/contract/test_studio_runtime.py::"
        "test_revocation_through_studio_stops_the_agents_next_exchange"
    ),
    # --- An unauditable write does not happen --------------------------------
    ("An unauditable write does not happen", "dev"): (
        NA + "the agent audit is a deployed-plane table and `apg dev` runs no "
        "agent plane. A dev cluster's writes are a developer's own, against their "
        "own container."
    ),
    ("An unauditable write does not happen", "generate"): (
        NA + "the client is a caller of the plane, not a part of it. The audit "
        "record is written by the plane before the scope check (ADR 0135), and "
        "nothing a client can do reorders that."
    ),
    ("An unauditable write does not happen", "studio"): (
        "tests/contract/test_studio_core.py::test_the_forwarder_table_has_no_rest_write"
    ),
    # --- An agent record carries no URL, key, token or caller value ----------
    ("An agent record carries no URL, key, token or caller value", "dev"): (
        NA + "`apg dev` writes no agent record. What it must not print is a "
        "password, which is this table's *a workstation holds no production "
        "secret* row."
    ),
    ("An agent record carries no URL, key, token or caller value", "generate"): (
        "tests/contract/test_client_typescript.py::test_nothing_the_client_emits_prints_or_retries"
    ),
    ("An agent record carries no URL, key, token or caller value", "studio"): (
        "tests/contract/test_studio_runtime.py::"
        "test_nothing_studio_prints_is_a_token_a_key_or_a_value"
    ),
    # --- The MCP runtime holds no credential ---------------------------------
    ("The MCP runtime holds no credential", "dev"): (
        "tests/contract/test_dev_environment.py::"
        "test_no_secret_name_the_contract_declares_reaches_the_environment"
    ),
    ("The MCP runtime holds no credential", "generate"): (
        NA + "the generator emits a client and starts no runtime. That the "
        "emitted package declares no dependency that could reach one is "
        "tests/contract/test_client_typescript.py::"
        "test_the_package_declares_no_runtime_dependency."
    ),
    ("The MCP runtime holds no credential", "studio"): (
        "tests/contract/test_studio_server.py::test_studio_holds_no_key_and_verifies_nothing"
    ),
    # --- One service cannot read another's credential ------------------------
    ("One service cannot read another's credential", "dev"): (
        "tests/contract/test_dev_environment.py::"
        "test_the_command_reads_no_facility_gated_secret_and_no_deployed_document"
    ),
    ("One service cannot read another's credential", "generate"): (
        NA + "the generator reads four contract inputs and the rendered "
        "document, and no secret generation exists in a checkout to read. What it "
        "must not EMIT is covered by the *DX layer holds nothing* row."
    ),
    ("One service cannot read another's credential", "studio"): (
        "tests/contract/test_studio_server.py::test_studio_holds_no_key_and_verifies_nothing"
    ),
    # --- A restore never overwrites the active volume ------------------------
    ("A restore never overwrites the active volume", "dev"): (
        NA + "`apg dev` never restores (stage plan §8's own words). Its volume "
        "is the anonymous one the image declares and `down` removes."
    ),
    ("A restore never overwrites the active volume", "generate"): (
        NA + "the generator writes a TypeScript package under "
        "`projects/<slug>/clients/`. It touches no volume and knows of no backup."
    ),
    ("A restore never overwrites the active volume", "studio"): (
        NA + "Studio's forwarder table is REST reads, the audit reader, agents, "
        "sessions and revocation. There is no restore operation in it -- which "
        "the table's own enumeration is the proof of, "
        "tests/contract/test_studio_core.py::test_the_forwarder_table_has_no_rest_write."
    ),
    # --- A workstation holds no production secret ----------------------------
    ("A workstation holds no production secret", "dev"): (
        "tests/contract/test_dev_environment.py::"
        "test_the_state_root_and_the_document_root_are_the_checkouts_and_never_the_hosts"
    ),
    ("A workstation holds no production secret", "generate"): (
        "tests/contract/test_client_typescript.py::"
        "test_nothing_the_generate_command_prints_is_a_credential"
    ),
    ("A workstation holds no production secret", "studio"): (
        "tests/contract/test_studio_command.py::"
        "test_a_password_argument_or_environment_variable_is_refused"
    ),
    # --- Projects share no project-scoped value ------------------------------
    ("Projects share no project-scoped value", "dev"): (
        "tests/contract/test_dev_environment.py::"
        "test_the_run_arguments_carry_no_network_no_mount_and_no_server_option"
    ),
    ("Projects share no project-scoped value", "generate"): (
        "tests/contract/test_generated_client_runtime.py::"
        "test_init_refuses_a_surface_with_another_fingerprint_naming_both"
    ),
    ("Projects share no project-scoped value", "studio"): (
        "tests/contract/test_studio_command.py::"
        "test_a_password_argument_or_environment_variable_is_refused"
    ),
    # --- There is no public Postgres endpoint --------------------------------
    ("There is no public Postgres endpoint", "dev"): (
        "tests/contract/test_dev_environment.py::"
        "test_the_psql_arguments_carry_the_subject_the_loopback_and_no_password"
    ),
    ("There is no public Postgres endpoint", "generate"): (
        NA + "the client speaks HTTP to PostgREST and the agent plane and has no "
        "database driver at all -- "
        "tests/contract/test_client_typescript.py::"
        "test_the_package_declares_no_runtime_dependency."
    ),
    ("There is no public Postgres endpoint", "studio"): (
        "tests/contract/test_studio_server.py::test_the_listener_is_on_loopback_and_nowhere_else"
    ),
    # --- A deploy over a broken archiver fails -------------------------------
    ("A deploy over a broken archiver fails", "dev"): (
        "tests/contract/test_dev_environment_cluster.py::"
        "test_the_environment_can_reach_no_backup_plane_and_the_rendered_model_can"
    ),
    ("A deploy over a broken archiver fails", "generate"): (
        NA + "the generator is not a deploy. It writes files and converges "
        "nothing; step 6c is `deploy.sh`'s and is unchanged by Stage 3."
    ),
    ("A deploy over a broken archiver fails", "studio"): (
        NA + "Studio is a client of a deployment that already exists. It "
        "converges nothing and cannot start a deploy -- the forwarder's table has "
        "no such operation."
    ),
    # --- A report may not substitute an answer -------------------------------
    ("A report may not substitute an answer for a failure to determine one", "dev"): (
        "tests/contract/test_dev_environment.py::"
        "test_state_that_is_absent_unreadable_or_stale_are_three_different_answers"
    ),
    ("A report may not substitute an answer for a failure to determine one", "generate"): (
        "tests/contract/test_client_typescript.py::"
        "test_init_reports_three_outcomes_and_never_folds_unreachable_into_stale"
    ),
    ("A report may not substitute an answer for a failure to determine one", "studio"): (
        "tests/contract/test_studio_core.py::"
        "test_an_undetermined_own_session_is_reported_and_none_is_ended"
    ),
}


# ---------------------------------------------------------------------------
# The two guards that make the matrix a claim
# ---------------------------------------------------------------------------


def _stage_plan_invariants() -> list[str]:
    """The first column of the stage plan's §8 table, read out of the plan."""
    text = (REPO_ROOT / "docs" / "plans" / "stage-3-plan.md").read_text(encoding="utf-8")
    section = text.split("## 8. The security invariants")[1].split("## 9.")[0]
    rows: list[str] = []
    for line in section.splitlines():
        if not line.startswith("| ") or line.startswith("| Invariant") or "---|" in line:
            continue
        first = line.split("|")[1].strip()
        rows.append(first.strip("*").strip())
    return rows


def test_the_matrix_covers_every_invariant_the_stage_plan_lists() -> None:
    """Sixteen invariants times three surfaces, and no blanks.

    Read out of the plan rather than compared against a copy of it: an
    invariant added to that table and not to this matrix is a row nobody
    reviewed, and the way that happens is silently.
    """
    from_plan = _stage_plan_invariants()
    assert len(from_plan) >= 16, (
        f"only {len(from_plan)} rows were parsed out of the stage plan's §8 table, so this "
        "comparison is close to vacuous. Read the table's shape before trusting a green"
    )

    assert sorted(from_plan) == sorted(INVARIANTS), (
        "the matrix and the stage plan's §8 table disagree: only in the plan "
        f"{sorted(set(from_plan) - set(INVARIANTS))}, only in the matrix "
        f"{sorted(set(INVARIANTS) - set(from_plan))}"
    )

    missing = [
        (invariant, surface)
        for invariant in INVARIANTS
        for surface in SURFACES
        if (invariant, surface) not in HARDENING_MATRIX
    ]
    assert not missing, f"cells with no entry at all: {missing}"
    assert len(HARDENING_MATRIX) == len(INVARIANTS) * len(SURFACES), (
        f"the matrix has {len(HARDENING_MATRIX)} cells and the review needs "
        f"{len(INVARIANTS) * len(SURFACES)}"
    )

    for (invariant, surface), value in HARDENING_MATRIX.items():
        assert surface in SURFACES, (invariant, surface)
        if value.startswith(NA):
            assert len(value) > len(NA) + 40, (
                f"({invariant!r}, {surface!r}) is marked not applicable with no reason worth "
                f"reading: {value!r}"
            )
        else:
            assert "::" in value, (
                f"({invariant!r}, {surface!r}) is neither a node id nor a reason: {value!r}"
            )


def test_every_matrix_cell_names_a_proof_the_offline_sweep_collects() -> None:
    """D1242: collectible, collected, and collected-by-WHICH-sweep differ.

    About fifty proofs in this repository turned out to be collected by no
    sweep at all, which is how a claim stays `not_run` with every half written.
    A matrix of node ids nobody collects would be the same failure with better
    presentation, so each one is checked against the selector the sweep that
    records this claim actually runs -- imported from the guard that keeps that
    selector honest, never retyped.

    A `live:` cell is checked for EXISTENCE and for carrying `live_host`: it is
    a proof about a deployment and the offline sweep is right not to collect it.
    """
    # A `not applicable` reason may CITE a node id in its prose -- several
    # do, because the honest reason for a cell is often *the neighbouring
    # proof already holds this*. Those are not cells claiming a proof, and
    # reading them as such is what the first run of this guard did, in four
    # cells.
    offline = {
        value for value in HARDENING_MATRIX.values() if "::" in value and not value.startswith(NA)
    }
    assert offline, "no cell names a proof at all, so this guard checks nothing"

    collected = subprocess.run(
        [
            # This interpreter, never a bare `python`: the name is on PATH only
            # with the venv activated, and a gate that runs `.venv/bin/python -m
            # pytest` would get FileNotFoundError instead of an answer.
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:randomly",
            "-m",
            OFFLINE_SWEEP_SELECTOR,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert collected.returncode == 0, collected.stdout[-2000:] + collected.stderr[-2000:]
    swept = {line.split("[")[0].strip() for line in collected.stdout.splitlines() if "::" in line}
    assert len(swept) > 1000, (
        f"the offline sweep collected {len(swept)} node ids, which is too few to be the "
        "sweep. Read the selector before trusting this"
    )

    # **Every filled cell is in that set**, which is not a given: it is what
    # makes `SEC-DX-001` a declarable offline claim rather than one waiting on a
    # host (ADR 0202). The two modules that look live -- `test_studio_runtime`
    # and `test_generated_client_runtime` -- are `p0` and `database`, not
    # `live_host`; they build their own containers in a checkout. A future cell
    # that could only be held on a deployment turns this red, and the claim's
    # MODE is then the thing to reconsider, not this assertion.
    unswept = sorted(node for node in offline if node not in swept)
    assert not unswept, (
        f"these matrix cells name proofs the offline sweep does not collect: {unswept}. "
        f"The selector is `-m '{OFFLINE_SWEEP_SELECTOR}'`; a proof it does not collect "
        "cannot record this claim, whatever it asserts (D1242)"
    )


# ---------------------------------------------------------------------------
# The three cross-cutting proofs
# ---------------------------------------------------------------------------

#: The pure modules behind the three surfaces.
DX_MODULES = (
    "src/agentic_postgres/dev_environment.py",
    "src/agentic_postgres/client_ir.py",
    "src/agentic_postgres/client_typescript.py",
    "src/agentic_postgres/studio.py",
    "src/agentic_postgres/dx_record.py",
)

#: The commands the three surfaces are reached by.
DX_COMMANDS = (
    "bin/dev.py",
    "bin/generate.py",
    "bin/studio.py",
    "bin/dx-record.py",
)

#: Paths that exist on a deployment host and must not exist in a DX surface.
#:
#: A DX surface runs on a workstation. A host path in one is either a read that
#: will fail there, or a read that will SUCCEED on the host and quietly make the
#: surface a second reader of production state.
HOST_PATHS = ("/var/lib/agentic-postgres", "/etc/agentic-postgres", "/root")


def test_no_dx_module_imports_services_or_names_a_host_path() -> None:
    """A workstation surface that knows a host path is one edit from reading it.

    Read with `ast` for the imports, because a string scan cannot tell
    `import services.x` from the word in a docstring -- and with a string scan
    for the paths, because a path IS a string and there is nothing else to read.
    Comments are stripped first (D1197): a comment explaining why a surface does
    NOT read `/var/lib/agentic-postgres` is the opposite of a violation.
    """
    offenders: list[str] = []
    for relative in DX_MODULES + DX_COMMANDS:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} is in this list and not in the tree"
        source = path.read_text(encoding="utf-8")

        tree = ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in {"services", "app"}:
                    offenders.append(f"{relative} imports {name}")

        code = "\n".join(
            re.sub(r'(?<!["\'])#.*$', "", line)
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        code = re.sub(r'"""[\s\S]*?"""', "", code)
        for host_path in HOST_PATHS:
            if host_path in code:
                offenders.append(f"{relative} names the host path {host_path}")

    assert not offenders, (
        f"a DX surface reaches outside a workstation: {offenders}. `apg dev`, `apg generate` "
        "and `apg studio` run where a developer is, and a host path in one is either a read "
        "that fails there or a read that succeeds on a host"
    )


#: A value nothing in this repository generates, planted in the environment.
PLANTED_SECRET = "APG_PLANTED_bd41f0c7a9e34f5182ac6d3b7e0195cc"  # noqa: S105

#: The second half: a value in a 0600 file handed where a verb takes one.
PLANTED_FILE_SECRET = "APG_PLANTED_FILE_7c2ae91d05b34862ae19f4d6b8033ac1"  # noqa: S105


def test_no_dx_command_prints_a_planted_secret_on_its_three_cheapest_exits(
    tmp_path: Path,
) -> None:
    """Nine runs: three surfaces times the three exits a developer reaches most.

    `--help`, an argument error, and an unrendered project. They are the cheapest
    exits and therefore the ones written last and read least -- and each of them
    prints a message assembled from whatever the command had in hand, which is
    where an environment value gets into a scrollback (D105).

    Both halves are planted: a value in the environment, and a value in a `0600`
    file handed to the one verb that takes a password file. Neither may appear
    in stdout or stderr on any of the nine runs.
    """
    password_file = tmp_path / "password"
    password_file.write_text(PLANTED_FILE_SECRET + "\n", encoding="utf-8")
    password_file.chmod(0o600)
    unrendered = tmp_path / "not-rendered.yaml"
    unrendered.write_text("schema_version: 5\n", encoding="utf-8")

    environment = {
        **{key: value for key, value in os.environ.items() if key != "APG_PROJECT"},
        "APG_PLANTED_SECRET": PLANTED_SECRET,
        "PGPASSWORD": PLANTED_SECRET,
    }

    invocations = [
        ("dev", ["--help"]),
        ("dev", ["--no-such-flag"]),
        ("dev", ["status", "--project", str(unrendered)]),
        ("generate", ["--help"]),
        ("generate", ["--no-such-flag"]),
        ("generate", ["--project", str(unrendered)]),
        ("studio", ["--help"]),
        ("studio", ["--no-such-flag"]),
        ("studio", ["--project", str(unrendered), "--outputs", str(unrendered),
                    "--password-file", str(password_file)]),
    ]  # fmt: skip

    assert len(invocations) == len(SURFACES) * 3, "nine runs, three per surface"

    for verb, arguments in invocations:
        result = subprocess.run(
            [str(APG), verb, *arguments],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            timeout=120,
        )
        transcript = result.stdout + result.stderr
        assert transcript.strip(), (
            f"`apg {verb} {' '.join(arguments)}` printed nothing, so this run searches nothing"
        )
        for planted in (PLANTED_SECRET, PLANTED_FILE_SECRET):
            assert planted not in transcript, (
                f"`apg {verb} {' '.join(arguments)}` printed a planted secret. A DX surface "
                "puts values in a scrollback, a shell history and a support ticket (D105)"
            )


def test_no_dx_artefact_carries_a_credential_but_the_two_declared_files(tmp_path: Path) -> None:
    """What the three surfaces LEAVE on the disk, scanned byte by byte.

    `apg dev up` generates three passwords and writes them into `0600` env
    files, which is the design (ADR 0203 §5). Everything else a DX surface
    writes -- Studio's assets, the generated TypeScript package, the rest of the
    dev state directory -- must carry none of them.

    **Docker is required and its absence is not a skip.** `SEC-DX-001` is a
    declared offline claim, and a claim that reports `passed` from a run where
    the scan did not happen is the shape ADR 0202 exists to prevent. An absent
    daemon fails this proof, saying so.
    """
    daemon = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True, text=True, check=False, timeout=60,
    )  # fmt: skip
    assert daemon.returncode == 0, (
        "docker is not available, and this proof records a DECLARED offline claim: a pass "
        f"from a run that never scanned anything is worse than a red. {daemon.stderr.strip()}"
    )

    fixture = REPO_ROOT / ".generated" / "fixture-alpha-dev"
    assert (fixture / "outputs.json").is_file(), (
        "no rendered fixture; run ./deploy.sh --project project.example.yaml "
        "--capabilities capabilities.example.yaml --render-only"
    )

    from agentic_postgres import dev_environment

    project = "project.example.yaml"
    subprocess.run(
        [str(APG), "dev", "down", "--project", project],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    up = subprocess.run(
        [str(APG), "dev", "up", "--project", project],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=900,
    )  # fmt: skip
    try:
        assert up.returncode == 0, f"`apg dev up` failed: {up.stderr[-1500:]}"

        state = dev_environment.state_dir("fixture-alpha-dev")
        declared = {
            dev_environment.SUPERUSER_ENV,
            dev_environment.MIGRATION_USER_ENV,
            dev_environment.APP_RUNTIME_ENV,
        }

        secrets: list[str] = []
        for name in declared:
            for line in (state / name).read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition("=")
                if key.strip() in {"POSTGRES_PASSWORD", "PGPASSWORD"} and value.strip():
                    secrets.append(value.strip())
        assert len(set(secrets)) == 3, (
            f"expected three distinct generated passwords on disk, found {len(set(secrets))}. "
            "The scan below would be searching for the wrong thing"
        )

        for name in declared:
            mode = (state / name).stat().st_mode & 0o777
            assert mode == 0o600, f"{name} is mode {oct(mode)}, not 0600"

        scanned: list[str] = []
        leaks: list[str] = []
        roots = [
            state,
            REPO_ROOT / "services" / "studio",
            REPO_ROOT / "projects" / "example" / "clients" / "typescript",
        ]
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.name in declared:
                    continue
                try:
                    blob = path.read_bytes()
                except OSError:
                    continue
                scanned.append(path.relative_to(REPO_ROOT).as_posix())
                for secret in secrets:
                    if secret.encode() in blob:
                        leaks.append(f"{path.relative_to(REPO_ROOT)} carries a dev password")

        # **Named, not counted** (the first version guessed 20 and the real
        # figure is 16). A count is a number nobody measured; these are the
        # artefacts the three surfaces actually leave on a workstation, and a
        # scan that did not reach them is a scan of something else.
        must_have_reached = {
            "services/studio/studio.js",
            "services/studio/index.html",
            "projects/example/clients/typescript/client.ts",
            "projects/example/clients/typescript/agent.ts",
        }
        missed = sorted(must_have_reached - set(scanned))
        assert not missed, (
            f"the scan did not reach {missed}, so it is not scanning the three surfaces' "
            f"artefacts. It read {len(scanned)} files: {sorted(scanned)[:8]}"
        )
        assert len(scanned) >= 12, (
            f"only {len(scanned)} files were scanned. A vacuous scan passes for the same "
            "reason a real one does"
        )
        assert not leaks, f"a generated credential is outside the two declared 0600 files: {leaks}"
    finally:
        subprocess.run(
            [str(APG), "dev", "down", "--project", project],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=300,
        )  # fmt: skip

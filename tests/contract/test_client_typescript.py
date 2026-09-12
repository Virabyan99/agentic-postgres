"""`GEN-EMIT-001` and `GEN-CMD-001`'s drift half (Session 23 Run 3).

These proofs read the emitted TEXT: the emitter's inputs, the banner, where a
digest may appear, what may never appear, that every union is exactly the
contract's names, and that the committed example client is what its contract
generates -- asked by running the product's own `--check` rather than by
re-emitting here (D1114).

**Reading the text is not enough, and this module is where that was learned.**
The first version of the emitter passed every proof below and did not compile:
`agent.ts` declared `listResources` twice and named a type nothing emitted
(D1223). It typechecked, later, and still could not RUN, because its import
specifiers named `.js` files a package that is never compiled does not have
(D1226). Both were found by a compiler and a runtime, not by a scan.

So the proofs that build and execute live in
`tests/contract/test_generated_client_toolchain.py`, against the hash-locked
image, with `--network none`.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess

import pytest
from tests.contract.test_client_ir import (  # the four inputs, assembled once
    project_inputs,  # noqa: F401 -- a fixture, used by name
    project_ir,  # noqa: F401
    release_ir,  # noqa: F401
)

from agentic_postgres import REPO_ROOT, client_ir, client_typescript, openapi_normalize

# `GEN-EMIT-001`, and `GEN-CMD-001`'s drift half: the emitted text, and
# the product's own `--check`.
#
# **Marked, and the marks are load-bearing** (D1240). Without them no
# marker-selected sweep collects this module at all -- not the Session 1
# gate's `contract and not future`, not CI's `p0 and not future and not
# live_host and not external` -- so every proof here passes only when
# somebody names the file. The registry's node ids stayed COLLECTIBLE the
# whole time, which is exactly why `test_acceptance_registry` could not
# see it: collectible and collected are different questions.
pytestmark = [pytest.mark.contract, pytest.mark.p0]

TYPESCRIPT_VERSION = "7.0.2"
TYPES_NODE_VERSION = "22.20.2"


def _emit(ir: client_ir.IR, version: str = "1.0.0") -> dict[str, str]:
    return client_typescript.emit(
        ir,
        client_version=version,
        # Read from the module that OWNS them, never retyped: a sentinel that
        # differed by one character would make every init() normalize
        # differently from the capture, and the failure would read as a stale
        # contract on a correct deployment.
        sentinel_host=openapi_normalize.SENTINEL_HOST,
        sentinel_base_path=openapi_normalize.SENTINEL_BASE_PATH,
        required_schemes=openapi_normalize.REQUIRED_SCHEMES,
        typescript_version=TYPESCRIPT_VERSION,
        types_node_version=TYPES_NODE_VERSION,
    )


@pytest.fixture(scope="module")
def emitted(project_ir: client_ir.IR) -> dict[str, str]:  # noqa: F811
    return _emit(project_ir)


# ---------------------------------------------------------------------------
# GEN-EMIT-001 -- structural
# ---------------------------------------------------------------------------


def test_the_emitter_reads_the_ir_and_nothing_else() -> None:
    """**GEN-EMIT-001.** One input, proved by AST.

    This is what makes `--check` meaningful and what makes a Python client
    unnecessary (D1205): if the emitter reads only the IR, a second emitter in
    another language needs no second reader of the contracts.
    """
    source = (REPO_ROOT / "src" / "agentic_postgres" / "client_typescript.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    outside = {
        name
        for name in imported
        if name.startswith("agentic_postgres") and not name.endswith("client_ir")
    }
    assert not outside, (
        f"the emitter imports {sorted(outside)}; it reads the IR and the standard library "
        "only, so that the IR is provably sufficient to generate a client (D1205)"
    )
    assert "app" not in {name.split(".")[0] for name in imported}

    # **Over the CODE, not the prose** (D1197). The first version of this scanned
    # the file text and failed on the module docstring, which says the emitter
    # reads no path under `contracts/` -- a scan over a well-commented file is a
    # scan over its comments unless they are stripped first. Comments are absent
    # from the AST, and docstrings are removed here, so what is left is the
    # literals the code actually evaluates.
    # Identified STRUCTURALLY -- the first statement of a module, class or
    # function body. `ast.get_docstring` returns a *cleaned* (dedented) string,
    # so comparing raw literals against it matches nothing, which is how the
    # first repair of this proof still failed.
    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstring_nodes.add(id(first.value))
    code_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_nodes
    ]
    assert code_literals, "no string literals were read; this compared nothing"

    for forbidden in ("contracts/", "projects/", "outputs.json", ".generated"):
        offenders = [literal for literal in code_literals if forbidden in literal]
        assert not offenders, (
            f"the emitter's CODE names {forbidden!r} in {offenders[:2]}. Every value it "
            "writes comes from the IR or from an argument its caller read out of the "
            "authority that owns it"
        )


def test_every_emitted_file_carries_the_generated_banner(emitted: dict[str, str]) -> None:
    """**GEN-EMIT-001.** A generated file says so, on its first line."""
    for name, text in sorted(emitted.items()):
        if not name.endswith(".ts"):
            continue
        first = text.splitlines()[0]
        assert first.startswith("// Generated by bin/apg.sh generate from "), (
            f"{name} does not open with the banner; a committed generated file that does "
            "not say it is generated gets edited"
        )
        assert "do not edit" in first


def test_no_emitted_file_carries_a_credential_a_token_or_a_url_with_userinfo(
    emitted: dict[str, str],
) -> None:
    """**GEN-EMIT-001.** The scan, over every emitted byte (D105, ADR 0204).

    These files are committed and copied onto machines this project will never
    see. The emitter refuses these patterns itself as well, so the failure is
    caught before a developer's checkout as well as before a commit -- two
    different people's failure.
    """
    patterns = {
        "a URL carrying userinfo": r"://[^/\s\"'`]*:[^/\s\"'`]*@",
        "a JWT literal": r"eyJ[A-Za-z0-9_-]{10,}\.",
        "a private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "an assigned password": (
            r"(?i)\b(password|passwd|secret|api[_-]?key)\s*[:=]\s*[\"'][^\"']{6,}"
        ),
    }
    for name, text in sorted(emitted.items()):
        for label, pattern in patterns.items():
            found = re.search(pattern, text)
            assert not found, f"{name} contains {label}: {found.group(0)[:40]!r}"

    # And the emitter refuses it rather than relying on this test alone.
    with pytest.raises(ValueError, match="userinfo"):
        client_typescript._refuse_secrets({"x.ts": 'const u = "https://u:p@host/";'})


def test_the_digests_live_in_one_file_and_the_app_one_is_never_compared(
    emitted: dict[str, str],
    project_ir: client_ir.IR,  # noqa: F811
) -> None:
    """**GEN-EMIT-001.** `contract.ts` is the one place a digest appears (D486).

    And `appOpenapiSha256` is carried without being compared (D1209, D1203):
    the application document is not served to a caller on a route this client
    holds, and its canonical form is not reproducible in JavaScript -- a client
    that compared it could never pass.
    """
    for name, text in sorted(emitted.items()):
        digests = re.findall(r"\b[0-9a-f]{64}\b", text)
        if name == "contract.ts":
            assert sorted(digests) == sorted(
                [
                    project_ir.digests.merged_surface_sha256,
                    project_ir.digests.rest_openapi_sha256,
                    project_ir.digests.app_openapi_sha256,
                    project_ir.digests.tools_sha256,
                ]
            ), "contract.ts carries exactly the IR's four digests"
        else:
            assert not digests, f"{name} carries a digest literal; they belong in contract.ts"

    for consumer in ("client.ts", "agent.ts"):
        assert "appOpenapiSha256" not in emitted[consumer], (
            "the application digest is provenance and is never compared at runtime"
        )
    assert "restOpenapiSha256" in emitted["client.ts"], "init() compares the REST digest"
    assert "toolsSha256" in emitted["agent.ts"], "listResources() compares the lock digest"


def test_a_request_names_only_reviewed_columns_operators_and_arguments(
    emitted: dict[str, str],
    project_ir: client_ir.IR,  # noqa: F811
) -> None:
    """**GEN-EMIT-001.** A call the contract does not name cannot be expressed.

    The stage plan's *must not*: no base table, no column outside the
    allowlist, no filter operator outside the set. Enforced by the emitted
    TYPES rather than by a check at call time, which is why the typecheck proof
    below is the one that makes it real.
    """
    types = emitted["types.ts"]

    for operator in project_ir.filter_operators:
        assert f'"{operator}"' in types
    operators = re.search(r"export type FilterOperator = ([^;]+);", types)
    assert operators, "no FilterOperator union was emitted"
    assert sorted(re.findall(r'"([^"]+)"', operators.group(1))) == sorted(
        project_ir.filter_operators
    ), "the operator union is exactly the capability schema's set, no more and no less"

    for relation in project_ir.relations:
        union = re.search(
            rf"export type {relation.name.title().replace('_', '')}Column = ([^;]+);", types
        )
        assert union, f"no column union for {relation.name}"
        assert sorted(re.findall(r'"([^"]+)"', union.group(1))) == sorted(
            column.name for column in relation.columns
        )

    # No forbidden schema, and no base table, reaches any emitted file.
    everything = "\n".join(emitted.values())
    for forbidden in ("app_private", "/app.", "extensions.", "public."):
        assert forbidden not in everything, f"an emitted file names {forbidden!r}"


def test_the_package_declares_no_runtime_dependency(
    emitted: dict[str, str],
) -> None:
    """**GEN-EMIT-001.** Nothing to trust but the runtime.

    Every dependency is a second thing the holder has to trust before believing
    the digest check, so there are none.
    """
    package = json.loads(emitted["package.json"])
    assert package["dependencies"] == {}
    assert sorted(package["devDependencies"]) == ["@types/node", "typescript"]
    assert package["devDependencies"]["typescript"] == TYPESCRIPT_VERSION
    assert package["private"] is True and package["type"] == "module"

    imports = re.findall(
        r'from "([^"]+)"', "\n".join(emitted[n] for n in emitted if n.endswith(".ts"))
    )
    for module in imports:
        assert module.startswith("./") or module.startswith("node:"), (
            f"an emitted file imports {module!r}; the package has no runtime dependency"
        )


def test_nothing_the_client_emits_prints_or_retries(emitted: dict[str, str]) -> None:
    """**GEN-EMIT-001.** No `console.*`, no retry, and the token in a closure.

    A client that logged would log on someone else's machine, into someone
    else's sink, and the one value it holds is a caller's token (D105).
    """
    for name in ("client.ts", "agent.ts", "canonical.ts", "contract.ts", "types.ts"):
        text = emitted[name]
        assert "console." not in text, f"{name} prints"
        assert "setTimeout" not in text and "retry" not in text.lower(), f"{name} retries"

    client = emitted["client.ts"]
    assert "const token = options.token;" in client, "the token is held in a closure"
    assert "${token}" not in client.replace("Bearer ${token}", ""), (
        "the token reaches exactly one place: the Authorization header"
    )


def test_init_reports_three_outcomes_and_never_folds_unreachable_into_stale(
    emitted: dict[str, str],
) -> None:
    """**GEN-EMIT-001**, ADR 0195 at the client.

    A client that could not reach a service knows nothing about its contract.
    Reporting that as `stale_contract` would send the operator to re-capture a
    snapshot that was already right -- which is the exact wrong turn ADR 0195
    was written after.
    """
    client = emitted["client.ts"]
    for outcome in ("stale_contract", "unreachable", "unparsable", "not_initialised"):
        assert outcome in client, f"init() cannot answer {outcome}"

    stale = re.search(r'kind: "stale_contract"[^}]*}', client)
    assert stale and "expected" in stale.group(0) and "served" in stale.group(0), (
        "a stale-contract answer names BOTH digests; 'they differ' sends the reader to source"
    )

    agent = emitted["agent.ts"]
    assert "unconfirmable" in agent, (
        "a lock below schema 4 reports no digest, and that is a THIRD answer -- never `ok`"
    )


def test_the_error_unions_are_the_pt_codes_and_the_seven_tokens(
    emitted: dict[str, str],
    project_ir: client_ir.IR,  # noqa: F811
) -> None:
    """**GEN-EMIT-001.** The two refusal vocabularies, as EMITTED.

    `test_the_caller_facing_tokens_match_the_runtimes` and
    `test_the_pt_codes_are_scanned_from_the_release_and_the_set` already prove
    the IR carries the right names. **That is not this.** Between the IR and
    the file is an emitter that writes the unions out, and a union emitted from
    a hard-coded list would satisfy every IR-side proof while shipping a
    vocabulary that drifts the next time either set moves.

    Both halves matter, for different reasons:

    * `PtCode` is what a caller **branches on**. A code the release raises and
      the union omits lands in the `string` arm of `PtCode | string` and gets
      handled as an unknown — the failure is silent and reads as a caller bug.
    * `AgentRefusal` is what an agent may be **told**: the closed set in
      `mcp_errors.CALLER_FACING_TOKENS`, which exists because nothing upstream
      of the plane is relayed to a caller (D433). A union that gained a member
      would be a client typed to receive something the runtime must never send.

    Exact equality in both directions, not containment — a superset is the
    failure this is for, and a containment check would pass on one.

    Goes red if: either union is emitted from a literal that stops tracking its
    source; a code or token is added to the product and not to the emitter; or
    the emitter starts widening `AgentRefusal` to `string`.
    """
    types = emitted["types.ts"]

    for name, expected in (
        ("PtCode", project_ir.pt_codes),
        ("AgentRefusal", project_ir.caller_facing_tokens),
    ):
        declaration = re.search(rf"export type {name} = ([^;]+);", types)
        assert declaration, f"no {name} union was emitted"
        members = tuple(sorted(re.findall(r'"([^"]+)"', declaration.group(1))))
        assert members == tuple(sorted(expected)), (
            f"the emitted {name} union is {members} and the contract's is "
            f"{tuple(sorted(expected))}. A union that is not exactly the vocabulary "
            "is a caller typed for a set the product does not use"
        )


def test_a_write_wrapper_requires_the_two_reserved_parameters(
    emitted: dict[str, str],
    project_ir: client_ir.IR,  # noqa: F811
) -> None:
    """**GEN-EMIT-001**, ADR 0181 and ADR 0182 at the client.

    Every write tool the lock carries takes `idempotency_key` and `dry_run`,
    and the generated wrapper declares both **required**. Optional is the
    failure worth naming: TypeScript's `?` would let a caller omit the key, the
    runtime would then have no claim to make in the write's own transaction,
    and a retried write would commit twice. `idempotency_key?: string` is easy
    to write and nearly invisible in a review.

    `dry_run` likewise: a rehearsal that costs what the write costs less the
    commit is only a rehearsal if the caller had to ask for it (ADR 0182).

    The roster is read from the IR rather than listed here, because a hand-
    listed roster stays right about the tools it names while a new one ships
    unguarded.

    Goes red if: either parameter is emitted optional or dropped; a write tool
    gains a wrapper that does not carry both; or the emitter starts treating
    the reserved pair as ordinary arguments.
    """
    agent = emitted["agent.ts"]
    writes = tuple(tool for tool in project_ir.tools if tool.kind == "write")
    assert writes, "the example contract carries no write tool; this would prove nothing"

    signatures = dict(re.findall(r"async (\w+)\(args: \{([^}]*)\}\): Promise<AgentOutcome>", agent))
    carrying = {
        name: parameters
        for name, parameters in signatures.items()
        if "idempotency_key" in parameters or "dry_run" in parameters
    }
    assert len(carrying) == len(writes), (
        f"the contract carries {len(writes)} write tools and the emitter wrote "
        f"{len(carrying)} wrappers taking a reserved parameter: {sorted(carrying)}"
    )
    for name, parameters in carrying.items():
        for reserved in ("idempotency_key", "dry_run"):
            assert reserved in parameters, f"{name} does not take {reserved}"
            assert f"{reserved}?" not in parameters, (
                f"{name} declares {reserved} OPTIONAL. A caller may then omit it: "
                "without the key the write has no claim to make in its own "
                "transaction, and a retry commits twice (ADR 0181)"
            )


def test_ci_typechecks_and_smokes_the_example_client() -> None:
    """**GEN-TOOLCHAIN-001**'s CI clause. The workflow, read as YAML (D1169).

    A generated artefact that is committed has exactly one failure mode worth
    a gate: it stops being what the generator produces. `generate --check`
    catches that in a fifth of a second, and the typecheck catches the case
    `--check` cannot -- a client that IS a fresh generation and does not
    compile, which is what shipped on the emitter's first run (D1223).

    Three properties, and the ORDER of the first two is the assertion:

    * `generate --check` runs BEFORE the container. A committed client that
      has drifted would otherwise be typechecked -- successfully, because a
      stale client is usually still valid TypeScript -- and the step would go
      green on the wrong artefact;
    * the image is built from `services/clients/typescript` with the pinned
      `BASE_IMAGE`, not from whatever `node:22-alpine` resolves to on the
      runner;
    * the step sits AFTER the `apg dev` round trip, so a runner that never got
      as far as a working checkout fails on the cheaper thing first.

    Read as YAML rather than grepped, because a text scan over a workflow
    answers *does this string appear somewhere in the file*, which a comment
    satisfies (D277) -- and this workflow's comment names `generate --check`.

    Goes red if: the step is deleted or renamed; `--check` is dropped, leaving
    a typecheck of an artefact nobody compared; the build stops passing
    `BASE_IMAGE`; or the step is moved ahead of the round trip that produces
    the render it needs.
    """
    import yaml

    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["session-2-contract"]["steps"]
    names = [str(step.get("name", "")) for step in steps]

    matching = [
        index for index, name in enumerate(names) if "generated example client" in name.lower()
    ]
    assert len(matching) == 1, (
        f"{len(matching)} steps name the generated client; the job has {names}"
    )
    index = matching[0]

    round_trip = [
        i for i, name in enumerate(names) if "local environment stands up" in name.lower()
    ]
    assert round_trip and index > round_trip[0], (
        "the client step runs before the `apg dev` round trip. It needs the render that "
        "step's job has already done, and a runner with a broken checkout should fail on "
        "the cheaper thing first"
    )

    script = str(steps[index]["run"])
    # Comments are what a text scan over a workflow accepts (D277), and this
    # step HAS a comment naming `generate --check`. Read the commands.
    commands = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))

    checked = commands.find("generate --check --project project.example.yaml")
    ran = commands.find("docker run")
    assert checked >= 0, f"the step does not run `generate --check`:\n{commands}"
    assert ran >= 0, f"the step does not run the toolchain image:\n{commands}"
    assert checked < ran, (
        "the step typechecks before it checks for drift. A stale client is usually still "
        "valid TypeScript, so the container would go green on an artefact nobody compared"
    )
    assert "services/clients/typescript" in commands, (
        "the step does not build the image from its own directory"
    )
    assert "BASE_IMAGE=${NODE_RUNTIME_IMAGE}" in commands, (
        "the image is built without the pinned base, so it carries whatever the runner's "
        "`node:22-alpine` resolves to today"
    )
    assert "projects/example/clients/typescript:/work:ro" in commands, (
        "the committed client is not mounted read-only into the check"
    )


def test_the_example_client_is_the_emitters_output_byte_for_byte() -> None:
    """**GEN-EMIT-001.** The committed client has not drifted from its contract.

    Asked by running **the product's own command** rather than by re-emitting
    here and comparing (D1114, D1117): `--check` is the thing an adopter runs,
    so it is the thing this proves works. A re-implementation in the test would
    pass while the command was broken, which is exactly how
    `api-contract.sh --check --project` could never exit 0 for four sessions.

    The version rule is part of what this catches. Applied as planned it moved
    the number on every regeneration, because `required_level([])` is `patch` --
    so the first `--check` this command ever ran failed on a client it had just
    written (D1224).
    """
    client = REPO_ROOT / "projects" / "example" / "clients" / "typescript"
    assert client.is_dir(), (
        f"{client} is not there. The example project's client is committed and drift-checked; "
        "generate it with `bin/apg.sh generate --project project.example.yaml`"
    )

    done = subprocess.run(
        [
            str(REPO_ROOT / "bin" / "generate.sh"),
            "--project",
            "project.example.yaml",
            "--capabilities",
            "capabilities.example.yaml",
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, (
        "the committed example client is not what its contract generates:\n"
        f"{done.stdout}\n{done.stderr}\n"
        "Regenerate it with `bin/apg.sh generate --project project.example.yaml`"
    )
    assert "is what this contract generates" in done.stdout


def test_nothing_the_generate_command_prints_is_a_credential() -> None:
    """**GEN-CMD-001.** The command prints digests and paths, and nothing else.

    There is no token for it to print -- it holds none -- which is the point:
    the check is that nothing has been added that would have one.
    """
    done = subprocess.run(
        [
            str(REPO_ROOT / "bin" / "generate.sh"),
            "--project",
            "project.example.yaml",
            "--capabilities",
            "capabilities.example.yaml",
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    printed = done.stdout + done.stderr
    for pattern in (
        r"eyJ[A-Za-z0-9_-]{10,}\.",
        r"://[^/\s]*:[^/\s]*@",
        r"(?i)password\s*[:=]\s*\S",
    ):
        assert not re.search(pattern, printed), f"the command printed something matching {pattern}"


# ---------------------------------------------------------------------------
# The proofs that need the image live in `test_generated_client_toolchain.py`
# ---------------------------------------------------------------------------
#
# `tsc --noEmit --strict` over the emitted package, and `canonical.ts` compared
# against `openapi_normalize.fingerprint`, were both here first -- and both
# installed `typescript` from the npm registry inside the test (D1227). They
# were green, and they would have failed in a gate run with no route out, while
# `generated_client_toolchain` is DECLARED an offline claim (ADR 0202).
#
# They now run against the hash-locked toolchain image with `--network none`.
# They are not duplicated here: two proofs of one fact, where one is weaker, is
# the arrangement in which the weaker one is the one that stays green.

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

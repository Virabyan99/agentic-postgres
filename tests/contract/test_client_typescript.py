"""`GEN-EMIT-001` and the reproducibility half of `GEN-TOOLCHAIN-001` (Session 23 Run 3).

Two kinds of proof here, and the second is the one that earns its cost.

The **structural** proofs read the emitted text: the emitter's inputs, the
banner, where a digest may appear, what may never appear, and that every union
is exactly the contract's names. They are cheap and they run everywhere.

The **toolchain** proofs run the emitted package through the pinned Node image:
`tsc --noEmit --strict` over the generated client, and the emitted
`canonical.ts` over every committed snapshot compared against
`openapi_normalize.fingerprint`. They are the only proofs that can answer
whether the thing this product writes for a developer actually *works* -- and
the first run of the typecheck found two defects in emitted code that every
structural proof had passed (D1223). A generated client nobody compiled is a
value that looks measured and is not.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest
from tests.contract.test_client_ir import (  # the four inputs, assembled once
    APP_SNAPSHOT,
    CANONICAL_MCP,
    RELEASE_SNAPSHOT,
    project_inputs,  # noqa: F401 -- a fixture, used by name
    project_ir,  # noqa: F401
    release_ir,  # noqa: F401
)
from tests.contract.test_image_contracts import requires_docker

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


def _node_image() -> str:
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if line.startswith("NODE_RUNTIME_IMAGE="):
            return line.split("=", 1)[1].strip()
    pytest.fail("versions.env pins no NODE_RUNTIME_IMAGE")


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
# GEN-TOOLCHAIN-001 -- the proofs that need the image
# ---------------------------------------------------------------------------


def _run_in_node(work: Path, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{work}:/w",
            "-w",
            "/w",
            _node_image(),
            "sh",
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )


@requires_docker
def test_the_emitted_client_typechecks_strict_in_the_pinned_image(
    emitted: dict[str, str], tmp_path: Path
) -> None:
    """**GEN-TOOLCHAIN-001.** The generated package COMPILES.

    **This proof found two defects nothing else could** (D1223): `agent.ts`
    declared `listResources` twice -- once by hand and once from the tool
    roster -- and referred to an `AgentFilter` type the emitter never wrote.
    Every structural proof above passed on that code.

    The control is a deliberately wrong line in the same container: a typecheck
    that cannot fail proves nothing, and `tsc`'s exit status for a type error
    is 1 under 7.0.2 where it was 2 under 5.x (D1212), so the assertion is on
    the MESSAGE as well as on a non-zero status.
    """
    for name, text in emitted.items():
        (tmp_path / name).write_text(text, encoding="utf-8")

    install = _run_in_node(
        tmp_path,
        "npm install --package-lock-only --ignore-scripts --no-audit --no-fund >/dev/null 2>&1 "
        "&& npm ci --ignore-scripts --no-audit --no-fund >/dev/null 2>&1 && echo installed",
    )
    assert "installed" in install.stdout, f"the toolchain did not install: {install.stderr[-400:]}"

    good = _run_in_node(tmp_path, "./node_modules/.bin/tsc -p tsconfig.json --noEmit")
    assert good.returncode == 0, (
        f"the GENERATED client does not typecheck under --strict:\n{good.stdout}\n{good.stderr}"
    )

    # The control, in the same container, on the same toolchain.
    broken = tmp_path / "contract.ts"
    original = broken.read_text(encoding="utf-8")
    broken.write_text(
        original + "\nconst wrong: number = CONTRACT.restContractId;\n", encoding="utf-8"
    )
    try:
        control = _run_in_node(tmp_path, "./node_modules/.bin/tsc -p tsconfig.json --noEmit")
    finally:
        broken.write_text(original, encoding="utf-8")

    assert control.returncode != 0, "a typecheck that passes a type error measures nothing"
    assert "contract.ts" in control.stdout and "TS2322" in control.stdout, (
        f"the control failed for the wrong reason: {control.stdout}\n{control.stderr}"
    )


@requires_docker
def test_canonical_ts_reproduces_pythons_fingerprint_for_every_committed_snapshot(
    emitted: dict[str, str], tmp_path: Path
) -> None:
    """**GEN-TOOLCHAIN-001.** The second canonical form, GUARDED (D1203).

    Two implementations of one serialization rule now exist in two languages,
    and `init()`'s whole value rests on them agreeing. So they are compared,
    over every committed snapshot, in the image the client will run on.

    **The application document is asserted to DIFFER**, and that is the point of
    including it: the boundary is written down, so the day it stops differing
    somebody has to read why rather than discovering it in a client.
    """
    (tmp_path / "canonical.ts").write_text(emitted["canonical.ts"], encoding="utf-8")
    contracts = tmp_path / "c"
    contracts.mkdir()

    sources = {
        "release-rest.json": RELEASE_SNAPSHOT,
        "release-mcp.json": CANONICAL_MCP,
        "project-rest.json": REPO_ROOT
        / "projects/example/contracts/postgrest-openapi.canonical.json",
        "project-mcp.json": REPO_ROOT
        / "projects/example/contracts/mcp-capabilities.canonical.json",
        "app.json": APP_SNAPSHOT,
    }
    for name, path in sources.items():
        assert path.is_file(), f"{path} is missing; the comparison needs every committed contract"
        (contracts / name).write_bytes(path.read_bytes())

    (tmp_path / "driver.ts").write_text(
        'import { readFileSync, readdirSync } from "node:fs";\n'
        'import { fingerprint } from "./canonical.ts";\n'
        'for (const name of readdirSync("c").sort()) {\n'
        '  const doc = JSON.parse(readFileSync(`c/${name}`, "utf8"));\n'
        "  console.log(JSON.stringify({ name, fingerprint: fingerprint(doc) }));\n"
        "}\n",
        encoding="utf-8",
    )

    done = _run_in_node(tmp_path, "node driver.ts")
    assert done.returncode == 0, f"the driver did not run: {done.stdout}\n{done.stderr}"
    javascript = {
        row["name"]: row["fingerprint"]
        for row in (json.loads(line) for line in done.stdout.splitlines() if line.startswith("{"))
    }
    assert set(javascript) == set(sources), f"the driver read {sorted(javascript)}"

    differ = []
    for name, path in sources.items():
        python = openapi_normalize.fingerprint(json.loads(path.read_text(encoding="utf-8")))
        if python != javascript[name]:
            differ.append(name)
        elif name == "project-rest.json":
            assert python == "808ac715c09aeebc382dd5afc886c1680fe2ea9870e729b9d34a623dee8d18de", (
                "the project snapshot's fingerprint moved; rig 23a measured this exact value "
                "being served to the authenticated role, and init() compares against it"
            )

    assert differ == ["app.json"], (
        f"the JavaScript canonical form agrees with Python everywhere except {differ}. "
        "D1203 recorded exactly one exception -- the application document's two Pydantic "
        "floats. If that list has changed, re-read rig 23b before trusting either side"
    )
    assert client_ir.js_reproducible(json.loads(APP_SNAPSHOT.read_text(encoding="utf-8"))), (
        "the Python walker must find the same document unreproducible that the byte "
        "comparison does; the two are checking one fact from two sides"
    )

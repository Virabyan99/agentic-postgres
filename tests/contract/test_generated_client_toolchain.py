"""`GEN-TOOLCHAIN-001` (Session 23 Run 3 step 3).

The image that checks what this product writes for a developer. Three things
are proved, and the third is what makes the claim an OFFLINE one (ADR 0202):

* the image is pinned and hash-locked -- Node by digest through `versions.env`,
  `typescript` and `@types/node` by a `package-lock.json` every entry of which
  carries an integrity hash, installed with `npm ci --ignore-scripts`;
* the emitted `canonical.ts` reproduces `openapi_normalize.fingerprint` for
  every committed REST and MCP snapshot, and **differs for the application
  document**, which is asserted so the boundary D1203 recorded cannot move
  unnoticed;
* the committed example client typechecks under the settings it ships with,
  mounted **read-only**, with **no network at all**.

That last clause is the point of the image existing rather than a bare
`docker run node`. The two proofs this module replaces installed `typescript`
from the registry inside the test: they passed, and they would have failed in a
gate run offline -- while `generated_client_toolchain` is declared an offline
claim. A proof that reaches a registry is not one an offline gate can trust.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest
from tests.contract.test_image_contracts import requires_docker

from agentic_postgres import REPO_ROOT, client_ir, openapi_normalize

# `GEN-TOOLCHAIN-001`: the hash-locked image, the compiler and the runtime.
#
# **Marked, and the marks are load-bearing** (D1240). Without them no
# marker-selected sweep collects this module at all -- not the Session 1
# gate's `contract and not future`, not CI's `p0 and not future and not
# live_host and not external` -- so every proof here passes only when
# somebody names the file. The registry's node ids stayed COLLECTIBLE the
# whole time, which is exactly why `test_acceptance_registry` could not
# see it: collectible and collected are different questions.
pytestmark = [pytest.mark.contract, pytest.mark.p0]

TOOLCHAIN = REPO_ROOT / "services" / "clients" / "typescript"
EXAMPLE_CLIENT = REPO_ROOT / "projects" / "example" / "clients" / "typescript"
APP_SNAPSHOT = REPO_ROOT / "contracts" / "app-openapi.canonical.json"

#: Every committed snapshot the JavaScript canonical form must reproduce, and
#: the one it must NOT. Named individually rather than globbed: a glob that
#: matched nothing would make this proof pass over an empty tree.
REPRODUCIBLE = {
    "release-rest.json": REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json",
    "release-mcp.json": REPO_ROOT
    / "contracts"
    / "snapshots"
    / "mcp"
    / "mcp-capabilities.canonical.json",
    "project-rest.json": REPO_ROOT
    / "projects"
    / "example"
    / "contracts"
    / "postgrest-openapi.canonical.json",
    "project-mcp.json": REPO_ROOT
    / "projects"
    / "example"
    / "contracts"
    / "mcp-capabilities.canonical.json",
}


def node_image() -> str:
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if line.startswith("NODE_RUNTIME_IMAGE="):
            return line.split("=", 1)[1].strip()
    pytest.fail("versions.env pins no NODE_RUNTIME_IMAGE")


def versions_value(name: str) -> str:
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    pytest.fail(f"versions.env pins no {name}")


@pytest.fixture(scope="module")
def toolchain_image() -> str:
    """The image, built from the checkout's own Dockerfile and lock.

    Tagged by the locked `typescript` version so a stale image from an earlier
    pin cannot be the thing under test.
    """
    tag = f"apg-client-typescript:{versions_value('TYPESCRIPT_VERSION')}"
    done = subprocess.run(
        [
            "docker",
            "build",
            "-q",
            "--build-arg",
            f"BASE_IMAGE={node_image()}",
            "-t",
            tag,
            str(TOOLCHAIN),
        ],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert done.returncode == 0, f"the toolchain image did not build:\n{done.stdout}\n{done.stderr}"
    return tag


def run_toolchain(image: str, work: Path, *arguments: str, network: bool = False, env=None):
    """The image's own entrypoint over `work`, mounted READ-ONLY."""
    command = ["docker", "run", "--rm"]
    if not network:
        command += ["--network", "none"]
    for key, value in (env or {}).items():
        command += ["-e", f"{key}={value}"]
    command += ["-v", f"{work}:/work:ro", image, *arguments]
    return subprocess.run(command, capture_output=True, text=True, timeout=900)


def readable_copy(source: Path, destination: Path) -> Path:
    """Copy a client into `destination` and make it readable by uid 65532.

    **pytest's `tmp_path` is 0700**, and this image runs as 65532, so a mount of
    it is not absent -- it is unreadable. That cost two failures before D1228
    made the image say so; the repair there was the product's, and the repair
    here is to hand it a directory it can actually read, which is what a
    developer's checkout looks like anyway (0755/0644).
    """
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.is_file():
            target = destination / entry.name
            target.write_bytes(entry.read_bytes())
            target.chmod(0o644)
    for parent in (destination, *destination.parents):
        try:
            parent.chmod(0o755)
        except (PermissionError, OSError):
            break
        if parent == Path(tempfile.gettempdir()):
            break
    return destination


# ---------------------------------------------------------------------------
# the image is pinned and hash-locked -- no daemon needed
# ---------------------------------------------------------------------------


def test_the_image_pins_node_and_typescript_and_the_lock_carries_integrity_hashes() -> None:
    """**GEN-TOOLCHAIN-001.** `npm ci` verifies bytes, not a version string.

    The `test_client_fixtures` shape over this directory: `npm ci` and never
    `npm install`, `--ignore-scripts`, a lockfile at version 3 or better, and
    an `integrity` hash on **every** entry. Without the hashes `npm ci` checks
    that a version number matches and nothing about what it downloaded.
    """
    dockerfile = (TOOLCHAIN / "Dockerfile").read_text(encoding="utf-8")
    code = "\n".join(line for line in dockerfile.splitlines() if not line.lstrip().startswith("#"))
    assert "npm ci" in code
    assert "npm install" not in code, (
        "`npm install` resolves afresh and silently updates the lock, which makes a "
        "committed lock decorative"
    )
    assert "--ignore-scripts" in code
    assert "ARG BASE_IMAGE" in code and "FROM ${BASE_IMAGE}" in code, (
        "the base image arrives as a build argument so versions.env stays the authority"
    )
    assert "USER 65532:65532" in code

    manifest = json.loads((TOOLCHAIN / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((TOOLCHAIN / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["lockfileVersion"] >= 3

    missing = [
        key
        for key, meta in lock["packages"].items()
        if key and not meta.get("integrity") and not meta.get("link")
    ]
    assert not missing, f"locked packages with no integrity hash: {missing}"

    # The manifest, the lock and versions.env are three copies of two numbers,
    # and they are asserted to agree rather than trusted (D486).
    for package, pinned in (
        ("typescript", versions_value("TYPESCRIPT_VERSION")),
        ("@types/node", versions_value("TYPES_NODE_VERSION")),
    ):
        assert manifest["dependencies"][package] == pinned, (
            f"{package} is {manifest['dependencies'][package]} in package.json and {pinned} "
            "in versions.env"
        )
        assert lock["packages"][f"node_modules/{package}"]["version"] == pinned

    # **`dependencies`, not `devDependencies`.** For this image the compiler is
    # not a development convenience; it is the whole payload, and `--omit=dev`
    # somewhere downstream would produce an image with nothing in it.
    assert "devDependencies" not in manifest or not manifest["devDependencies"]


def test_the_entrypoint_addresses_the_compiler_by_path_and_never_through_npx() -> None:
    """**GEN-TOOLCHAIN-001.** The check may not reach a registry (D1225).

    `npx tsc` resolves from the current directory first and, finding nothing,
    FETCHES the package -- so an entrypoint using it would silently make every
    typecheck a network call, and would pass for the wrong reason on a machine
    that happened to be online. The offline arm below is what proves the repair;
    this asserts the mechanism, so a future edit cannot reintroduce it quietly.
    """
    entrypoint = (TOOLCHAIN / "entrypoint.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in entrypoint.splitlines() if not line.lstrip().startswith("#"))
    assert "npx" not in code, "npx can fetch from the registry; address the compiler by path"
    assert "/app/node_modules/.bin/tsc" in code
    assert "--typeRoots" in code, (
        "the generated client has no node_modules of its own, and the toolchain may not "
        "write one into the directory it was handed"
    )


# ---------------------------------------------------------------------------
# the proofs that need the daemon
# ---------------------------------------------------------------------------


@requires_docker
def test_the_example_client_typechecks_strict(toolchain_image: str) -> None:
    """**GEN-TOOLCHAIN-001.** The committed client compiles, and the check can fail.

    Mounted **read-only**, so a toolchain that wrote into the directory it was
    asked to check would fail here rather than in somebody's `git status`.

    The control is a deliberately wrong line in a COPY of the client, run
    through the same image: a typecheck that passes a type error measures
    nothing. Asserted on the MESSAGE as well as a non-zero status, because that
    status is 1 under typescript 7 and 2 under 5.x (D1212).
    """
    assert EXAMPLE_CLIENT.is_dir(), f"{EXAMPLE_CLIENT} is not there"

    good = run_toolchain(toolchain_image, EXAMPLE_CLIENT)
    assert good.returncode == 0, (
        f"the committed example client does not typecheck:\n{good.stdout}\n{good.stderr}"
    )
    assert "typechecks" in good.stdout


@requires_docker
def test_a_type_error_in_a_generated_client_fails_the_toolchain(
    toolchain_image: str, tmp_path: Path
) -> None:
    """**GEN-TOOLCHAIN-001.** The control for the proof above (D499).

    In a copy, never in the checkout: the committed client is an artefact under
    `--check`, and a proof that edited it in place would leave the tree dirty
    when it failed partway.
    """
    work = readable_copy(EXAMPLE_CLIENT, tmp_path / "client")
    broken = work / "contract.ts"
    broken.write_text(
        broken.read_text(encoding="utf-8") + "\nconst wrong: number = CONTRACT.restContractId;\n",
        encoding="utf-8",
    )
    broken.chmod(0o644)

    done = run_toolchain(toolchain_image, work)
    assert done.returncode != 0
    assert "contract.ts" in done.stdout and "TS2322" in done.stdout, (
        f"the control failed for the wrong reason:\n{done.stdout}\n{done.stderr}"
    )

    # And a directory that holds no client is refused as input rather than
    # reported as passing -- an empty check is the one that silently succeeds.
    empty = tmp_path / "empty"
    empty.mkdir()
    empty.chmod(0o755)
    nothing = run_toolchain(toolchain_image, empty)
    assert nothing.returncode == 2, f"an empty /work should exit 2, got {nothing.returncode}"
    assert "tsconfig.json is not there" in nothing.stderr


@requires_docker
def test_the_toolchain_typechecks_with_no_network_at_all(toolchain_image: str) -> None:
    """**GEN-TOOLCHAIN-001**, and the clause that makes this an OFFLINE claim.

    Run with `--network none`. The two proofs this module replaced installed
    `typescript` from the registry inside the test; they were green, and they
    would have failed in a gate with no route out -- while
    `generated_client_toolchain` is DECLARED offline (ADR 0202). A claim whose
    proof needs the internet is not an offline claim, and the difference shows
    up exactly once, on the day it matters.
    """
    done = run_toolchain(toolchain_image, EXAMPLE_CLIENT, network=False)
    assert done.returncode == 0, (
        "the toolchain could not typecheck without a network, so the image does not hold "
        f"everything it needs:\n{done.stdout}\n{done.stderr}"
    )


@requires_docker
def test_canonical_ts_reproduces_pythons_fingerprint_for_every_committed_snapshot(
    toolchain_image: str, tmp_path: Path
) -> None:
    """**GEN-TOOLCHAIN-001.** The second canonical form, guarded (D1203).

    Two implementations of one serialization rule now exist in two languages,
    and `init()`'s whole value rests on them agreeing -- so they are compared,
    over every committed snapshot, on the pinned runtime, with no network.

    **The application document is asserted to DIFFER.** That is why it is in the
    list: the boundary is written down, so the day it stops differing somebody
    has to read why rather than finding out through a client that refuses a
    correct deployment.
    """
    work = readable_copy(EXAMPLE_CLIENT, tmp_path / "client")

    contracts = work / "c"
    contracts.mkdir()
    contracts.chmod(0o755)
    every = {**REPRODUCIBLE, "app.json": APP_SNAPSHOT}
    for name, path in every.items():
        assert path.is_file(), f"{path} is missing; the comparison needs every committed contract"
        (contracts / name).write_bytes(path.read_bytes())
        (contracts / name).chmod(0o644)

    (work / "driver.ts").write_text(
        'import { readFileSync, readdirSync } from "node:fs";\n'
        'import { fingerprint } from "./canonical.ts";\n'
        'for (const name of readdirSync("c").sort()) {\n'
        '  const doc = JSON.parse(readFileSync(`c/${name}`, "utf8"));\n'
        "  console.log(JSON.stringify({ name, fingerprint: fingerprint(doc) }));\n"
        "}\n",
        encoding="utf-8",
    )
    (work / "driver.ts").chmod(0o644)

    done = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "node",
            "-v",
            f"{work}:/work:ro",
            "-w",
            "/work",
            toolchain_image,
            "driver.ts",
        ],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert done.returncode == 0, f"the driver did not run:\n{done.stdout}\n{done.stderr}"

    javascript = {
        row["name"]: row["fingerprint"]
        for row in (json.loads(line) for line in done.stdout.splitlines() if line.startswith("{"))
    }
    assert set(javascript) == set(every), f"the driver read {sorted(javascript)}"

    differ = []
    for name, path in every.items():
        python = openapi_normalize.fingerprint(json.loads(path.read_text(encoding="utf-8")))
        if python != javascript[name]:
            differ.append(name)

    assert differ == ["app.json"], (
        f"the JavaScript canonical form agrees with Python everywhere except {differ}. D1203 "
        "recorded exactly one exception -- the application document's two Pydantic floats. If "
        "that list has changed, re-read rig 23b before trusting either side"
    )
    assert javascript["project-rest.json"] == (
        "808ac715c09aeebc382dd5afc886c1680fe2ea9870e729b9d34a623dee8d18de"
    ), (
        "the project snapshot's fingerprint moved. Rig 23a measured this exact value being "
        "served to the authenticated role, and every generated client compares against it"
    )

    # The two sides of one fact: the byte comparison above found the application
    # document unreproducible, and the Python walker must find it too.
    offender = client_ir.js_reproducible(json.loads(APP_SNAPSHOT.read_text(encoding="utf-8")))
    assert offender is not None and "secret_ttl_seconds" in offender, (
        f"the walker and the byte comparison disagree about the app document: {offender}"
    )


@requires_docker
def test_the_smoke_reports_unreachable_rather_than_a_stale_contract(
    toolchain_image: str,
) -> None:
    """**GEN-TOOLCHAIN-001**, ADR 0195 proved at RUNTIME rather than in a string.

    With no network and an address that resolves to nothing, `init()` must
    answer `unreachable`. Reporting that as `stale_contract` would send an
    operator to re-capture a snapshot that was already correct, which is the
    wrong turn ADR 0195 exists to prevent -- and the three earlier proofs of it
    read the emitted SOURCE for the three branches, which cannot tell whether
    the runtime takes them.

    The missing-environment arm is the control: a driver that printed the same
    thing whatever it was handed would pass the first assertion too.
    """
    unset = run_toolchain(toolchain_image, EXAMPLE_CLIENT, "smoke")
    assert unset.returncode == 2, f"expected exit 2 with no environment: {unset.stdout}"
    assert json.loads(unset.stdout.splitlines()[0]) == {
        "step": "environment",
        "missing": "APG_REST_URL",
    }

    done = run_toolchain(
        toolchain_image,
        EXAMPLE_CLIENT,
        "smoke",
        env={
            "APG_REST_URL": "https://nothing.invalid/api/rest",
            # Not a credential: a string that cannot authenticate anywhere, and
            # the point of the arm is that it is never reached or printed.
            "APG_TOKEN": "not-a-real-token",
        },
    )
    assert done.returncode == 1
    steps = [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]
    init = next(step for step in steps if step["step"] == "init")
    assert init["kind"] == "unreachable", (
        f"a service that did not answer was reported as {init['kind']!r}; nothing is known "
        "about the contract of a service that could not be reached"
    )
    assert "expected" not in init and "served" not in init, (
        "an unreachable service has no served digest to name"
    )

    # Nothing it printed is the token it was handed.
    assert "not-a-real-token" not in done.stdout + done.stderr


@requires_docker
def test_an_unreadable_mount_is_reported_as_unreadable_and_never_as_absent(
    toolchain_image: str, tmp_path: Path
) -> None:
    """**GEN-TOOLCHAIN-001**, ADR 0195's third outcome (D1228).

    This image runs as 65532. A client directory at 0700 from another uid is
    **not absent** -- it is unreadable, and every `[ -f … ]` inside is false for
    both reasons. Until this was measured the image answered *"tsconfig.json is
    not there, so there is no generated client to check"* for a client that was
    sitting right in front of it, which would send a developer to regenerate
    something already correct.

    The control is the SAME directory at 0755: if that also failed, this would
    be measuring something other than the permission.
    """
    work = tmp_path / "unreadable"
    work.mkdir()
    for entry in EXAMPLE_CLIENT.iterdir():
        if entry.is_file():
            (work / entry.name).write_bytes(entry.read_bytes())
    for parent in (tmp_path, *tmp_path.parents):
        try:
            parent.chmod(0o755)
        except (PermissionError, OSError):
            break
        if parent == Path(tempfile.gettempdir()):
            break
    work.chmod(0o700)

    refused = run_toolchain(toolchain_image, work)
    assert refused.returncode == 3, (
        f"an unreadable mount exited {refused.returncode}; 2 would mean 'no client here' and "
        f"0 would mean it checked something:\n{refused.stdout}\n{refused.stderr}"
    )
    assert "cannot read it" in refused.stderr
    assert "is not there" not in refused.stderr, (
        "an unreadable directory reported as an absent one is the third outcome folded into "
        "the second (ADR 0195)"
    )

    # The control: the same bytes, readable, typecheck clean.
    work.chmod(0o755)
    for entry in work.iterdir():
        entry.chmod(0o644)
    allowed = run_toolchain(toolchain_image, work)
    assert allowed.returncode == 0, (
        f"the same directory at 0755 did not typecheck, so the arm above was not measuring "
        f"the permission:\n{allowed.stdout}\n{allowed.stderr}"
    )

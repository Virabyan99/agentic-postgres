"""Session 23's live halves: a client's claim, and the lock a plane confirmed.

**Two claims, and neither can be answered in a checkout.**

`GEN-HASH-001` (`generated_client_hash`). ADR 0204's sentence is that a
generated client is a claim about the surface it was generated from, and
`init()` is where the claim is checked -- against the document the deployment
SERVES, fetched as the caller. That is not a fact about a file. PostgREST
serves a different document to every role (rig 23a: the anonymous role is
served zero paths), so the answer depends on a running service, a route and an
identity, none of which a checkout has. Every offline proof of `init()` runs
against a cluster this repository stands up; this one runs the COMMITTED
example client against the deployment it was generated for, and against the
other project as the control.

`AGT-META-001` (`agent_lock_reported`). `list_resources` reports the digest of
the lock the running process loaded. Offline, that is proved against a
constructed lock; here it is asked of the container, and compared with what the
plane's own probe reports AND with the digest compiled into the committed
client. A process cannot be wrong about which lock it loaded, and the file on
disk can be ahead of it: Session 21's trip had beta serving six tools and
refusing a tenant scope for eight minutes while the document said seven (D1152,
D1153). This is the caller's-eye view of the same fact.

**Measured at Session 24's trip, not Session 23's close.** Session 23 has no
host trip: it closes on its offline half alone, and these two claims are
registered now with their live proofs gated on the roster variables so that the
next trip runs them rather than rediscovering that they are owed. That trip
owes a deploy `--through-session >= 23` first, so the auth/mcp container is
recreated and answers with its `lock` member at all.

**Docker is required**, for the first proof: the client runs in the hash-locked
toolchain image, because running it any other way would be running a compiler
and a runtime nobody pinned. The sweep has Docker -- the doctor and every
Session 18 rehearsal use it as root -- and `bin/session-23-check.sh --mode
host` says so in its usage.

**The token is the deployment's own** (D298, ADR 0095). A subject is created
through `app_private.auth_create_user`, the product's own function, and then
LOGS IN through `POST /auth/login`. Minting one here would prove that this
suite can sign.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, agent_plane, runtime_override

# ruff: noqa: S608 -- every literal here is this module's own constant, run by an
# operator's psql against probe projects. The same waiver every deployment module
# carries, for the same reason.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

MCP_ACCEPT = "application/json, text/event-stream"
#: The committed client, and the image that can run it.
EXAMPLE_CLIENT = REPO_ROOT / "projects" / "example" / "clients" / "typescript"
TOOLCHAIN_CONTEXT = REPO_ROOT / "services" / "clients" / "typescript"
TOOLCHAIN_TAG = "apg-s23-client-typescript"

OWNER_USERNAME = "apg-s23-client-owner"
OWNER_PASSWORD = "client-owner-probe-6d3e81b0af52"  # noqa: S105 -- a probe credential
READER_NAME = "apg-s23-lock-reader"
AGENT_SECRET = "s23-lock-secret-41c7e9b2d605"  # noqa: S105 -- a probe credential
READER_SCOPES = ("meta:read",)


# ---------------------------------------------------------------------------
# reading the committed client, and running it
# ---------------------------------------------------------------------------


def contract_constant(name: str) -> str:
    """One field of the committed client's `contract.ts`, read as text.

    Read from the artefact rather than recomputed from the tree, because the
    artefact is what an adopter holds: a test that rebuilt the IR here would
    compare the deployment against this checkout and call it a comparison
    against the client (D486 -- two copies of a fact with a test between them
    are one fact).
    """
    source = (EXAMPLE_CLIENT / "contract.ts").read_text(encoding="utf-8")
    found = re.search(rf"{name}:\s*\"([0-9a-f]{{64}})\"", source)
    assert found, f"{name} is not in the committed client's contract.ts"
    return found.group(1)


@pytest.fixture(scope="module")
def toolchain_image(sh_status: Callable[..., tuple[int, str, str]]) -> str:
    """Build the hash-locked toolchain image from this checkout.

    `--build-arg BASE_IMAGE` from `versions.env`, the same way the contract
    module and CI build it: the base is pinned by digest, and an image built
    without it would be whatever `node:22-alpine` means on the host today.
    """
    versions = {}
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            versions[key.strip()] = value.strip().strip('"')
    base = versions.get("NODE_RUNTIME_IMAGE")
    assert base, "versions.env carries no NODE_RUNTIME_IMAGE"

    code, _, error = sh_status(
        "docker",
        "build",
        "-q",
        "--build-arg",
        f"BASE_IMAGE={base}",
        "-t",
        TOOLCHAIN_TAG,
        str(TOOLCHAIN_CONTEXT),
    )
    assert code == 0, f"the toolchain image did not build: {error.strip()[:400]}"
    return TOOLCHAIN_TAG


def run_client(
    sh_status: Callable[..., tuple[int, str, str]],
    image: str,
    environment: Path,
) -> tuple[int, str, str]:
    """Run the committed client's smoke in the toolchain image.

    The client is mounted READ-ONLY and the credential reaches the container
    through `--env-file`, never as an argument: a token in `docker run`'s
    argv is a token in the host's process table and in any shell history that
    recorded the command (D105).
    """
    return sh_status(
        "docker",
        "run",
        "--rm",
        "--env-file",
        str(environment),
        "-v",
        f"{EXAMPLE_CLIENT}:/work:ro",
        image,
        "smoke",
    )


def steps(output: str) -> dict[str, dict[str, Any]]:
    """The smoke's steps, by name.

    Read from `smoke.ts` rather than assumed. It prints ONE JSON LINE PER STEP
    -- `init`, `read`, `filter`, `rpc`, `lock`, `done` -- so the last line is
    `done` and never the answer this proof is about. It also exits 1 as soon as
    `init()` answers anything but `ok`, which is precisely the alpha arm: a
    reader that judged on the exit code would call the refusal it exists to
    prove a failure to run.
    """
    found: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and "step" in record:
            found[str(record["step"])] = record
    return found


def write_environment(directory: Path, rest_url: str, token: str) -> Path:
    """An 0600 env file holding the URL and the token, and nothing else."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "client.env"
    path.write_text(f"APG_REST_URL={rest_url}\nAPG_TOKEN={token}\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def rest_url_of(document: dict[str, Any]) -> str:
    route = (document.get("routes") or {}).get("rest")
    if not isinstance(route, dict) or route.get("status") != "ready" or not route.get("url"):
        pytest.fail(
            f"{document['project']['key']}: routes.rest is {route!r}. There is no served "
            "surface for a client to check itself against"
        )
    return str(route["url"])


# ---------------------------------------------------------------------------
# subjects and agents, made through the product's own functions
# ---------------------------------------------------------------------------


def make_owner(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any]
) -> tuple[str, Callable[[], None]]:
    """A registered subject on one project, and the sweep that removes it."""
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = document["database"]["roles"]["authenticated"]
    stored = hashing.Hasher().hash(OWNER_PASSWORD)

    def sweep() -> None:
        psql(document, f"DELETE FROM app_private.agents WHERE name = '{READER_NAME}';")
        psql(document, f"DELETE FROM app_private.users WHERE username = '{OWNER_USERNAME}';")

    sweep()
    code, user_id, error = psql(
        document,
        "SELECT app_private.auth_create_user("
        f"'{OWNER_USERNAME}', 'Session 23 client owner', '{role_name}', "
        "ARRAY['notes:read', 'notes:write']::text[], "
        f"'{stored}');",
    )
    assert code == 0 and user_id.strip(), (
        f"could not create the client owner on {document['project']['key']}: {error}"
    )
    return user_id.strip(), sweep


def plane_report(
    document: dict[str, Any], sh_status: Callable[..., tuple[int, str, str]]
) -> agent_plane.Report:
    """What the RUNNING plane says about itself, through the product's own probe.

    Session 22's helper, copied rather than imported: importing across two
    deployment modules would make a sweep of either drag the other's fixtures
    in. The probe itself is `agent_plane.PROBE` in both, which is the copy that
    would matter (D486).
    """
    key = document["project"]["key"]
    code, out, err = sh_status(
        "docker", "ps", *agent_plane.container_filters(key, runtime_override.MCP_SERVICE)
    )
    assert code == 0, f"{key}: docker ps exited {code}: {err.strip()[:300]}"
    container = agent_plane.sole_container(out)
    assert container, f"{key}: {out.strip()!r} is not one agent-plane container"

    code, out, err = sh_status("docker", "exec", "-i", container, "python", "-c", agent_plane.PROBE)
    assert code == 0, f"{key}: the plane did not answer the probe: {err.strip()[:300]}"
    report = agent_plane.parse_report(out)
    assert report is not None, f"{key}: the plane's report is unreadable: {out.strip()[:200]!r}"
    return report


def sse_result(body: str) -> dict[str, Any] | None:
    """The JSON-RPC message out of an SSE response (D458)."""
    payload = None
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
    return payload


@pytest.fixture(scope="module")
def mcp_rpc(api_call: Callable[..., Any]) -> Callable[..., Any]:
    def call(
        url: str, *, token: str | None, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        return api_call(
            url,
            method="POST",
            token=token,
            body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={"Accept": MCP_ACCEPT},
        )

    return call


# ---------------------------------------------------------------------------
# GEN-HASH-001 -- the client's claim, checked against what is served
# ---------------------------------------------------------------------------


def test_the_example_client_initialises_on_beta_and_refuses_alpha(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    app_login: Callable[..., Any],
    sh_status: Callable[..., tuple[int, str, str]],
    toolchain_image: str,
    tmp_path: Path,
) -> None:
    """`GEN-HASH-001`. The committed client, run against two deployments.

    **The control is the whole proof.** A client that answered `ok` on beta
    would satisfy a reader who never asked what it does when the surface is
    different -- and an `init()` that returned `ok` unconditionally would pass
    that reader too. So the same package, the same image and the same command
    are pointed at alpha, which publishes the RELEASE surface alone: no
    `note_embeddings` relation, no `set_note_embedding` function. That is a
    different document with a different fingerprint, and the answer must be
    `stale_contract` NAMING BOTH DIGESTS.

    Both tokens are the deployment's own, issued by `POST /auth/login` to a
    subject created through `app_private.auth_create_user` (D298, ADR 0095).
    The reason is not ceremony: PostgREST serves a document per ROLE, so a
    token that did not name a real registered subject would have the client
    checking the anonymous surface -- which is zero paths, and would fail for
    a reason that has nothing to do with the contract (rig 23a).

    Goes red if: the deployment moved and the committed client was not
    regenerated (the designed outcome, and what `apg generate --check` catches
    offline first); the client stops fetching as the caller; or `init()` stops
    discriminating and answers the same thing on both projects.

    **This has never executed.** It is the thirteenth never-executed proof this
    project has carried to a host, and `pytest --setup-plan` is the cheap half
    that says only whether it would run.
    """
    expected = contract_constant("restOpenapiSha256")

    outcomes: dict[str, dict[str, Any]] = {}
    beta_steps: dict[str, dict[str, Any]] = {}
    sweeps: list[Callable[[], None]] = []
    try:
        for label, document in (("beta", project_b), ("alpha", project_a)):
            _, sweep = make_owner(psql, document)
            sweeps.append(sweep)

            answer = app_login(document, OWNER_USERNAME, OWNER_PASSWORD)
            assert answer.status == 200, (
                f"{label}: the client owner could not log in ({answer.status}). It was "
                "created moments ago through the product's own auth_create_user, so this "
                "is the login path failing rather than a missing subject"
            )
            token = json.loads(answer.body)["access_token"]

            environment = write_environment(tmp_path / label, rest_url_of(document), token)
            code, out, err = run_client(sh_status, toolchain_image, environment)

            # NOT judged on the exit code. The smoke exits 1 the moment init()
            # answers anything but `ok`, and the alpha arm below is exactly
            # that answer -- so a reader keyed to the status would report the
            # refusal this proof exists to prove as a failure to run. What
            # would be a failure to run is the container not printing the step
            # at all, and that is what is asserted.
            reported = steps(out)
            assert "init" in reported, (
                f"{label}: the client printed no `init` step (exit {code}). "
                f"stdout={out.strip()[:300]!r} stderr={err.strip()[:300]!r}"
            )
            outcomes[label] = reported["init"]
            if label == "beta":
                beta_steps = reported

            # D105, both streams: the token reached the container through an
            # env file and must appear in neither.
            assert token not in out and token not in err, (
                f"{label}: the client printed its own token"
            )

        assert outcomes["beta"]["kind"] == "ok", (
            f"beta answered {outcomes['beta']!r}. The example client was generated from "
            "this project's own contract, so the deployment is serving a surface it was "
            "not generated from -- regenerate from the commit the deployment is at"
        )
        # And a typed read through the same client, on the same run: `init()`
        # answering `ok` says the surface matches, not that anything can be
        # fetched through it.
        read = beta_steps.get("read")
        assert read and read.get("kind") == "ok", (
            f"beta's typed read answered {read!r}. The contract matches and the call "
            "still did not work, which is a grant or a policy rather than a digest"
        )

        assert outcomes["alpha"]["kind"] == "stale_contract", (
            f"alpha answered {outcomes['alpha']!r}. Alpha publishes the release surface "
            "alone -- no note_embeddings -- so a client generated from beta's contract "
            "MUST refuse it. Anything else means init() does not discriminate, and beta's "
            "`ok` above proves nothing"
        )
        stale = outcomes["alpha"]
        assert stale.get("expected") == expected, (
            f"the refusal names {stale.get('expected')!r} as what the client expects and "
            f"the committed contract.ts says {expected!r}"
        )
        assert stale.get("served") and stale["served"] != expected, (
            "the refusal does not name the digest alpha actually served. 'They differ' "
            "sends the reader to source (ADR 0195)"
        )
    finally:
        for sweep in sweeps:
            sweep()


# ---------------------------------------------------------------------------
# AGT-META-001 -- the lock the plane confirmed, as a caller sees it
# ---------------------------------------------------------------------------


def test_list_resources_on_beta_reports_the_lock_the_plane_confirmed(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    mcp_rpc: Callable[..., Any],
    sh_status: Callable[..., tuple[int, str, str]],
) -> None:
    """`AGT-META-001`. Three readings of one digest, and they must be one.

    * what `list_resources` returns to a caller holding `meta:read`;
    * what the plane's own probe reports for the lock it loaded;
    * what the committed example client carries as `toolsSha256`.

    The first two agreeing says the tool reports the PROCESS's lock rather than
    recomputing something from the roster it serves. The third says the client
    an adopter holds is a claim about THIS deployment's agent surface -- which
    is the half `init()` cannot check, because `init()` reads the REST document
    and the lock is not in it.

    Alpha is the control, and it is a real one: alpha serves the release's six
    tools and beta seven, so alpha's digest must DIFFER from the client's. A
    reading that matched on both would mean the digest is a release constant
    rather than a deployment's fact.

    Goes red if: the plane recomputes the digest instead of carrying the one
    the lock was signed with; the deployment's lock and the committed client
    come apart (regenerate); or `list_resources` stops reporting the member,
    in which case this says so rather than accepting `None` as agreement.

    **This has never executed.**
    """
    embedded = contract_constant("toolsSha256")

    sweeps: list[Callable[[], None]] = []
    try:
        digests: dict[str, str | None] = {}
        for label, document in (("beta", project_b), ("alpha", project_a)):
            owner_id, sweep = make_owner(psql, document)
            sweeps.append(sweep)

            from agentic_postgres import service_source

            hashing = service_source.load("hashing")
            role_name = document["database"]["roles"]["agent_reader"]
            array = ", ".join(f"'{scope}'" for scope in sorted(READER_SCOPES))
            code, agent_id, error = psql(
                document,
                "SELECT app_private.auth_create_agent("
                f"'{READER_NAME}', 'Session 23 lock read probe', '{role_name}', "
                f"ARRAY[{array}]::text[], '{owner_id}', "
                f"'{hashing.Hasher().hash(AGENT_SECRET)}', NULL);",
            )
            assert code == 0 and agent_id.strip(), (
                f"could not create {READER_NAME!r} on {label}: {error}"
            )

            route = (document.get("routes") or {}).get("mcp") or {}
            assert route.get("status") == "ready" and route.get("url"), (
                f"{label}: routes.mcp is {route!r}; deploy twice (D326)"
            )
            answer = mcp_rpc(
                str(route["url"]),
                token=AGENT_SECRET,
                method="tools/call",
                params={"name": "list_resources", "arguments": {}},
            )
            assert answer.status == 200, f"{label}: list_resources answered {answer.status}"
            message = sse_result(answer.body)
            assert message and "error" not in message, f"{label}: {answer.body[:300]}"
            structured = message["result"].get("structuredContent") or json.loads(
                message["result"]["content"][0]["text"]
            )

            lock = structured.get("lock")
            assert isinstance(lock, dict), (
                f"{label}: list_resources returned no `lock` member ({structured.keys()}). "
                "Either the deployed release predates Session 23, or the deploy did not "
                "recreate the container -- read the container, not the file (D1153)"
            )
            digests[label] = lock.get("tools_sha256")

            report = plane_report(document, sh_status)
            assert digests[label] == report.tools_sha256, (
                f"{label}: the tool reports {digests[label]!r} and the plane's own probe "
                f"{report.tools_sha256!r}. A caller and the process disagree about which "
                "lock is loaded, which means one of them is computing rather than carrying"
            )
            assert lock.get("tool_count") == report.tool_count, (
                f"{label}: the tool reports {lock.get('tool_count')} tools and the plane "
                f"{report.tool_count}"
            )

        assert digests["beta"] == embedded, (
            f"beta's plane loaded {digests['beta']!r} and the committed client was "
            f"generated against {embedded!r}. The client's `listResources()` will answer "
            "`stale_contract` for every adopter holding it -- regenerate"
        )
        assert digests["alpha"] != embedded, (
            "alpha's plane reports the same lock digest as beta's. Alpha declares no "
            "capabilities of its own and serves six tools against beta's seven, so an "
            "equal digest means the reported value is a release constant rather than "
            "this deployment's lock -- and the assertion above proves nothing"
        )
    finally:
        for sweep in sweeps:
            sweep()

"""Session 11's operations plane, against the deployment.

`OPS-001`, `OPS-LOG-001`'s ingress leg, `DEP-002` and `DEP-PRE-001`'s host half.
Everything here needs a running deployment and could not be proved elsewhere.

**Read this before the trip, not at the terminal.** Every proof in this module is
executing for the first time, which is the shape that produced *five defective
never-executed proofs across two trips* — a `SELECT` list missing the column its
own `ORDER BY` named, a control satisfied by the failure it guarded against
(D509), enum labels absent from `api.task_status`, and five recovery proofs that
all died on a column renamed six sessions earlier (D596).

**The first draft of this module would have been the sixth, seventh and eighth.**
It used `mcp_route`, `mcp_rpc` and `mcp_writer_session` — which are **module-local
to `test_session8_agent_plane.py` and `test_session9_agent_writes.py`**, not
conftest fixtures, so every MCP test here would have ERRORed on a missing
fixture. It called `materialized_secret(key, name)`, which takes **three**
arguments. And it unpacked `api_call` as a tuple, which returns a frozen
`ApiResponse` dataclass. None of that is visible from reading the tests; all of
it is visible from reading the fixtures, which is what "before the trip" means.

**So OPS-LOG-001 is split rather than duplicated.** Its `agent_plane` ↔
`database` join is already asserted by
`test_session9_agent_writes.py::test_the_request_id_is_recorded_and_is_this_planes_own_mint`,
which Run 6 replaced with the stricter form. What has no proof anywhere is the
**ingress** leg — that Traefik logs the id the runtime served — and that needs no
agent at all, because `StampRequestId` wraps every response the application
plane makes.
"""

from __future__ import annotations

import json
import os
import secrets as secrets_module
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

# ruff: noqa: S608 -- every literal here is this module's own constant, run by an
# operator against a probe project. The same waiver every deployment module
# carries, for the same reason.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

EDGE_STACK_NAME = "apg-edge"

#: The check names `diagnosis` produces. `route health` is `f"route {name}"`
#: with `name="health"`; the rest are literals in `agentic_postgres.diagnosis`.
EXPECTED_CHECKS = (
    "containers",
    "route health",
    "tls",
    "database",
    "migrations",
    "backup repository",
    "wal archiver",
    "disk headroom",
)


def project_key(document: dict[str, Any]) -> str:
    return str(document["project"]["key"])


# ---------------------------------------------------------------------------
# OPS-001 — the diagnostic command, against a real deployment
# ---------------------------------------------------------------------------


def test_the_doctor_reports_every_check_family(
    project_a: dict[str, Any], as_root, sh_status
) -> None:
    """**Run 3's probes, executing for the first time.**

    Every one was written offline against a stubbed subprocess layer. What has
    never been measured is whether a `docker ps --format` filter matches a real
    project's containers, whether `du` and `df` parse on this host's coreutils,
    and whether `bin/backup.sh info --json` answers in the shape
    `probe_repository` expects.

    Goes red if: a check family is missing, or the command exits outside its
    documented codes. **An `UNKNOWN` fails this test** — on a healthy deployment
    every probe should reach its parsing path, and an unknown means a probe
    reached for something this host does not have, which is precisely the
    never-executed-proof defect and not a statement about the deployment.
    """
    del as_root
    key = project_key(project_a)
    code, out, err = sh_status("bin/doctor.sh", "--project", key)
    report = out + err

    assert code in (0, 6), (
        f"doctor.sh --project {key} exited {code}; the documented codes are 0 (well), "
        f"6 (a check failed or could not run) and 4 (never deployed here).\n{report}"
    )

    missing = [name for name in EXPECTED_CHECKS if name not in report]
    assert not missing, f"the report omits {missing}. Full report:\n{report}"

    unknown = [line for line in report.splitlines() if line.strip().startswith("UNKNOWN")]
    assert not unknown, (
        "a probe could not run against a healthy deployment, so it is reaching for "
        "something this host does not have:\n" + "\n".join(unknown)
    )


def test_the_doctor_prints_no_live_credential(
    project_a: dict[str, Any], as_root, sh_status, migration_password
) -> None:
    """`OPS-001`'s actual claim — *without secrets* — against **real** material.

    The offline tests plant a canary and scan for it. This reads a credential
    that genuinely exists in the active generation and asserts it is absent from
    both verbosities. A value really present in the deployment is the one a leak
    would leak.

    Goes red if: any byte of a live credential reaches the operator's screen.
    """
    del as_root
    key = project_key(project_a)
    value = migration_password(key).strip()

    # The premise. Scanning for an empty string passes against any output (D374).
    assert len(value) >= 16, (
        f"the credential read back is {len(value)} bytes; this scan would pass vacuously"
    )

    for arguments in (("--project", key), ("--project", key, "--verbose")):
        _, out, err = sh_status("bin/doctor.sh", *arguments)
        assert value not in out + err, f"doctor.sh {' '.join(arguments)} printed a live credential"


def test_the_doctor_refuses_a_project_that_was_never_deployed_here(as_root, sh_status) -> None:
    """Exit 4, the documented code for missing runtime state.

    **The control for the two tests above.** Without it, a `doctor.sh` that
    answered identically for every input — including a project that does not
    exist — would satisfy both: the first looks for check names in the output,
    and the second looks for the absence of a string.
    """
    del as_root
    code, out, err = sh_status("bin/doctor.sh", "--project", "apg-not-a-project-dev")
    assert code == 4, f"expected 4 (never deployed here), got {code}.\n{out}{err}"


# ---------------------------------------------------------------------------
# OPS-LOG-001 — the ingress leg
# ---------------------------------------------------------------------------


def test_the_edge_logs_the_request_id_the_runtime_served(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    as_root,
    sh,
) -> None:
    """**The leg D478 left open, closed on the way out** (ADR 0160).

    The runtime mints one id per HTTP request and stamps it on the **response**;
    Traefik's shipped access-log policy keeps it as `downstream_X-Request-Id`.
    Rig E measured that against the locked digest offline; this measures the
    running edge.

    **Any published path will do, and the status does not matter.**
    `StampRequestId` wraps the whole application, so a 401 carries the header as
    surely as a 200 — and using a refusal keeps this proof independent of any
    credential.

    Goes red if: the response carries no id, or the edge did not log the id it
    served. Each is asserted separately so a failure names which half broke.
    """
    del as_root
    response = api_call(f"{app_base(project_a)}/admin/agents")
    served = response.headers.get("X-Request-Id") or response.headers.get("x-request-id")

    assert response.status != 0, (
        f"nothing answered at {app_base(project_a)}/admin/agents, so there is no "
        "response to correlate and the assertion below would search for None"
    )
    assert served, (
        "the application's response carried no X-Request-Id. StampRequestId wraps "
        "create_app, so this means the deployed release predates Run 5 or the "
        "middleware is not in the stack"
    )

    logs = sh("docker", "logs", "--since", "5m", f"{EDGE_STACK_NAME}-traefik-1")
    assert '"RouterName"' in logs, (
        "no access-log line was captured at all, only startup output, so the "
        "ingress assertion below would prove nothing (D186's guard-the-guard)"
    )
    assert served in logs, (
        f"the edge logged no request carrying {served}. Either the response header "
        "did not reach Traefik, or the access-log policy stopped keeping "
        "X-Request-ID — which rig E measured that the shipped policy does"
    )


def test_a_malformed_request_id_header_does_not_destroy_the_write(
    project_a: dict[str, Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    owner_session: Any,
    as_root,
) -> None:
    """**D633, on the deployment.** The measurement that shaped migration 0022.

    Offline, an unguarded cast on a malformed caller-supplied `X-Request-Id`
    raised `22P02`, answered 400, and left the table with **zero rows** — the
    caller's own note destroyed by a header. `app_private.agent_request_id()`
    tests the shape before casting, so a bad header records `NULL` and the write
    proceeds.

    Through the REST surface rather than MCP, because a caller reaching
    PostgREST directly is the path that can carry an arbitrary header — and it
    is the path ADR 0135 already contemplates.

    **`owner_session`, not `mint_token`** (D675). The first version of this
    proof minted a token for the `authenticated` role naming a registered
    subject, and the deployment answered `401 PT401 "the request identity is no
    longer current"` — the request never reached `api.create_note`, so it said
    nothing at all about 0022's guard. That is **D298 exactly**: migration
    0013's `auth_claims_are_current` is an EXISTS over five equalities including
    `credential_version`, `authz_version` and an exact scope array, and a
    bootstrap-minted token carries none of the three. `owner_session`'s
    docstring says so, four sessions before this run rebuilt the defect.

    Goes red if: migration 0022's guard is absent or unapplied.
    """
    del as_root
    base = rest_base(project_a)
    title = f"apg-run9-malformed-{secrets_module.token_hex(4)}"

    response = api_call(
        f"{base}/rpc/create_note",
        method="POST",
        token=owner_session.token,
        body={"p_title": title, "p_content": "x"},
        headers={"X-Request-Id": "not-a-uuid"},
    )
    # 401 is NOT this proof's subject, and conflating the two is what made the
    # first failure unreadable: the assertion blamed migration 0022 for a
    # refusal that happened two layers earlier.
    assert response.status != 401, (
        f"the token was refused before the RPC ran ({response.body[:200]}). This proof "
        "measured nothing about the header guard — repair the identity, not 0022"
    )
    assert response.status < 400, (
        f"a malformed X-Request-Id refused the write with {response.status}: "
        f"{response.body[:300]}. Migration 0022's guard is missing or unapplied — "
        "an unguarded cast raises 22P02 and rolls the caller's own row back (D633)"
    )

    code, out, _ = psql(project_a, f"SELECT count(*) FROM app.notes WHERE title = '{title}'")
    assert code == 0 and out.strip() == "1", (
        f"the note was not committed (count={out.strip()!r}), so the malformed header "
        "took the write with it — which is exactly D633"
    )

    # The positive half. "It did not crash" is satisfied by a build where
    # `agent_request_id()` returns NULL unconditionally, so the audit row has to
    # be read: a malformed header records NULL, and the write is still audited.
    code, out, _ = psql(
        project_a,
        "SELECT coalesce(request_id::text, 'NULL'), source FROM app_private.agent_audit "
        f"WHERE owner_id = '{owner_session.user_id}' AND tool = 'create_note' "
        "ORDER BY completed_at DESC LIMIT 1",
    )
    assert code == 0 and out.strip().startswith("NULL|"), (
        f"the audit row for the malformed write reads {out.strip()!r}. It must be "
        "NULL: a header that is not a uuid is not a request id, and recording one "
        "anyway would put a caller-supplied string into a correlation column"
    )


# ---------------------------------------------------------------------------
# DEP-PRE-001's host half — a refusal changes nothing
# ---------------------------------------------------------------------------


def test_a_refused_deploy_writes_nothing(as_root, sh_status, tmp_path: Path) -> None:
    """**ADR 0157 on the deployment**: every absence reported, nothing changed.

    Driven with a project key this host has never deployed, so the bootstrap and
    the secret generation are both genuinely absent and the refusal is real
    rather than arranged.

    Goes red if: the deploy renders anything, reports fewer absences than exist
    (a fail-fast preflight reports one), or exits outside 3/4.
    """
    del as_root
    from agentic_postgres import REPO_ROOT

    manifest = tmp_path / "project.probe.yaml"
    source = (REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8")
    manifest.write_text(source.replace("fixture-alpha", "apg-refusal-probe"), encoding="utf-8")

    generated = REPO_ROOT / ".generated"
    before = sorted(p.name for p in generated.iterdir()) if generated.is_dir() else []

    code, out, err = sh_status(
        "./deploy.sh",
        "--host",
        "host.yaml",
        "--project",
        str(manifest),
        "--capabilities",
        "capabilities.yaml",
        "--through-session",
        "10",
    )
    report = out + err

    assert code in (3, 4), f"expected a refusal (3 or 4), got {code}:\n{report}"
    assert "Nothing has been changed" in report, "the preflight did not say it changed nothing"
    assert report.count("MISSING") >= 2, (
        "fewer than two absences were reported for a project with neither a bootstrap "
        f"nor a generation; a fail-fast preflight reports exactly one:\n{report}"
    )

    after = sorted(p.name for p in generated.iterdir()) if generated.is_dir() else []
    assert before == after, f"the refused deploy changed .generated/: {set(after) ^ set(before)}"


# ---------------------------------------------------------------------------
# DEP-002 — a redeploy converges without destroying data
# ---------------------------------------------------------------------------


@pytest.fixture
def redeploy_window() -> dict[str, str]:
    """What the operator recorded BEFORE redeploying.

    Session 5's rotation-window shape (`APG_ROTATED_*_FROM_FILE`), for its
    reason: a before/after claim whose "before" is read *after* the event is not
    a before/after claim. The file carries the sentinel note's title and the
    secret generation id that was active before the deploy.

    Skips rather than passes when absent. A skip is not a pass, and a proof that
    quietly degraded to "a row exists" would assert nothing about convergence.
    """
    path = os.environ.get("APG_REDEPLOY_BEFORE_FILE")
    if not path:
        pytest.skip("APG_REDEPLOY_BEFORE_FILE is not set; no redeploy window was opened")
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    for field in ("sentinel_title", "generation_id"):
        assert document.get(field), f"{path} carries no {field!r}"
    return document


def test_a_redeploy_preserves_rows_written_before_it(
    project_a: dict[str, Any],
    redeploy_window: dict[str, str],
    psql: Callable[..., tuple[int, str, str]],
    as_root,
) -> None:
    """`DEP-002`. A row written through the product's own route before the
    redeploy is still there after it.

    Goes red if: the redeploy destroyed or replaced the volume.
    """
    del as_root
    title = redeploy_window["sentinel_title"]
    code, out, _ = psql(project_a, f"SELECT count(*) FROM app.notes WHERE title = '{title}'")
    assert code == 0, out
    assert out.strip() == "1", (
        f"the sentinel row written before the redeploy is gone (count={out.strip()!r}). "
        "A converging deploy does not destroy data"
    )


def test_the_redeploy_actually_ran(
    project_a: dict[str, Any], redeploy_window: dict[str, str], as_root, sh
) -> None:
    """**The control, and without it the test above is worthless.**

    A deploy that did nothing preserves every row perfectly. The signal is the
    product's own: `materialize-secrets` writes a *new* immutable generation on
    every deploy and repoints `active-secret-generation.json` at it, so a
    generation id equal to the one recorded before the window means no deploy
    ran.

    D509's rule — *a control that cannot fail for the reason it is watching for
    is not a control* — applied to the one assertion that would otherwise pass
    on a no-op.
    """
    del as_root
    key = project_key(project_a)
    pointer = f"/var/lib/agentic-postgres/secrets/{key}/active-secret-generation.json"
    now = json.loads(sh("cat", pointer))["generation_id"]

    assert now != redeploy_window["generation_id"], (
        f"the active secret generation is still {now}, the one recorded before the "
        "window. No deploy ran, so the preservation assertion proved nothing"
    )

"""Admission: does this project fit on this node? (`NODE-ADMIT-001`, ADR 0221)

**Every proof here drives `bin/admit.py` as a subprocess** rather than calling
`decide` directly (D1114: a proof calls the product's own command). The thing
under test is not the arithmetic -- `test_capacity_reading.py` owns that -- it
is what an operator gets: the exit code, the six lines, and the refusal's
words.

**The fixtures are built through the product's own validator.** Each synthetic
deployed document is written from `tests/fixtures/outputs-v10.json` and then
passed through `deployed_output.validate_deployed_document`, so a fixture that
has drifted from the schema fails here rather than proving something about a
document nobody has (§7 question 6).

**No Docker, and no hidden switch that turns it off.** `docker inspect` is not
available in this suite, and a fixture flag only a test sets is D1509's shape.
The ceilings are a REPORT line and never a rule input, so `admit` decides
anyway and the report says it could not read them -- which is exactly the
behaviour the trip depends on, since a wedged daemon must not refuse a deploy.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import (  # noqa: E402
    capacity_reading,
    config,
    deployed_output,
    naming,
    rendering,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]

ADMIT = REPO_ROOT / "bin" / "admit.py"
ADMIT_SH = REPO_ROOT / "bin" / "admit.sh"


def render(slug: str) -> dict[str, Any]:
    """Render a manifest through the PURE renderer.

    `rendering.render_project` publishes into `.generated/<key>`, which the
    gate compares across projects for identity collisions -- so a test that
    called it would have to delete what it published. `build_outputs` is the
    function underneath and touches nothing (the shape
    `test_backup_plane.py::_render` already uses).
    """
    document = yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))
    document["project"]["slug"] = slug
    capabilities_path = REPO_ROOT / "capabilities.example.yaml"
    capabilities = config.load_capabilities_manifest(capabilities_path)
    identity = naming.derive(
        slug=document["project"]["slug"],
        environment=document["project"]["environment"],
        domain=document["project"]["domain"],
        api_base_path=document["api"]["public_base_path"],
        mcp_base_path=document["mcp"]["public_base_path"],
        database_name=document["database"].get("name"),
        storage_enabled=bool((document.get("storage") or {}).get("enabled", False)),
        storage_bucket=(document.get("storage") or {}).get("bucket"),
        storage_prefix=(document.get("storage") or {}).get("prefix"),
        backup_enabled=bool((document.get("backup") or {}).get("enabled", False)),
        backup_stanza=(document.get("backup") or {}).get("stanza"),
        backup_repository_prefix=(document.get("backup") or {}).get("repository_prefix"),
        backup_bucket=(document.get("backup") or {}).get("bucket"),
    )
    digests = rendering.input_digests(REPO_ROOT / "project.example.yaml", capabilities_path)
    return rendering.build_outputs(document, capabilities, identity, digests)


def write_deployed(root: Path, key: str, unreclaimable: int) -> Path:
    """One deployed document, built the way the deploy builds one.

    Built rather than borrowed, and rather than read from `.generated/`: a
    hand-written dict would agree with itself and with nothing else, and a
    fixture read off disk would make these proofs SKIP in a tree where the
    example has not been rendered. A skip is not a pass.

    `validate_deployed_document` runs before the file is written, so a fixture
    that has drifted from the schema fails here rather than quietly proving
    something about a document nobody has.
    """
    rendered = render(key.rsplit("-", 1)[0])
    document = deployed_output.build_deployed_document(
        rendered=rendered,
        source_commit="a" * 40,
        health_status="ready",
        rest_status="unavailable",
        docs_status="unavailable",
        app_status="unavailable",
        app_docs_status="unavailable",
        storage_status="unavailable",
        mcp_status="unavailable",
        metrics_status="unavailable",
        api=deployed_output.API_NOT_PUBLISHED,
        jwt=deployed_output.JWT_NOT_PUBLISHED,
        mcp=deployed_output.MCP_NOT_PUBLISHED,
        deployed_through_session=3,
        host={
            "id": "apg-vps-01",
            "os_release": "26.04",
            "public_ipv4": "203.0.113.10",
            "public_ipv6": None,
        },
        edge={
            "stack_name": "apg-edge",
            "control_network": "apg-edge_control",
            "egress_network": "apg-edge_egress",
            "project_network_attached": True,
        },
        tls={
            "status": "issued",
            "acme_environment": "staging",
            "resolver": "letsencrypt-staging",
            "certificate_sha256": "c" * 64,
            "not_before": "2026-08-05T00:00:00Z",
            "not_after": "2026-11-03T00:00:00Z",
        },
        bootstrap={
            "status": "complete",
            "state_path": f"/etc/agentic-postgres/projects/{key}/bootstrap-state.json",
            "infisical_project_id": "5fffcd38-9af6-4f9d-bef9-c6eefc5e696f",
            "runtime_identity_id": "3302b5a4-7288-424f-bcd3-6cd158617827",
        },
        secrets={
            "status": "ready",
            "generation_id": "k7f2p9qd",
            "generation_manifest": (
                f"/var/lib/agentic-postgres/secrets/{key}/generations/k7f2p9qd/manifest.json"
            ),
            "required_names": ["session2_sentinel"],
            "fresh": True,
            "materialized_at": "2026-08-05T18:00:00Z",
        },
        runtime={
            "release_path": "/opt/agentic-postgres/releases/" + "a" * 40,
            "state_directory": f"/etc/agentic-postgres/projects/{key}",
            "compose_model_sha256": "d" * 64,
        },
        database_observed={
            "status": "observed",
            "server_version": "18.4",
            "extensions": {"vector": "0.8.6", "plpgsql": "1.0"},
            "memory": {"anon_mb": 62, "shmem_mb": 140, "file_mb": 410},
            "instance_uuid": "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f",
        },
    )
    document["database"]["budget"]["unreclaimable_mb"] = unreclaimable
    deployed_output.validate_deployed_document(document)

    directory = root / key
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "outputs.json"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def host_manifest(tmp_path: Path) -> Path:
    """A schema 3 host, from the committed example rather than hand-built."""
    document = yaml.safe_load((REPO_ROOT / "host.example.yaml").read_text(encoding="utf-8"))
    assert document["schema_version"] == 3
    assert document["capacity"]["memory_mb"] == 3814
    path = tmp_path / "host.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def schema_two_host(tmp_path: Path) -> Path:
    document = yaml.safe_load((REPO_ROOT / "host.example.yaml").read_text(encoding="utf-8"))
    document["schema_version"] = 2
    del document["capacity"]
    path = tmp_path / "host-v2.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def write_manifest(tmp_path: Path, *, slug: str, database: dict[str, Any] | None = None) -> Path:
    """A candidate manifest from `project.example.yaml`, with its budget moved."""
    document = yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))
    document["project"]["slug"] = slug
    if database:
        document.setdefault("database", {}).update(database)
    path = tmp_path / f"{slug}.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def run_admit(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADMIT), *argv],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


@pytest.fixture
def deployment(tmp_path: Path) -> Path:
    """Two deployed projects at the release defaults: 304 MiB each."""
    root = tmp_path / "projects"
    write_deployed(root, "alpha-dev", 304)
    write_deployed(root, "beta-dev", 304)
    return root


#: The budget that does not fit: 896 + 64 + 56*2 = 1072 against 992 available.
#: All THREE members move, and that is rig 31e's finding (D1608) rather than a
#: flourish -- with only `shared_buffers_mb` raised, `_validate_memory_budget`
#: refuses the manifest for `shm_size_mb`, and with shm raised it refuses again
#: for `memory_limit_mb`. A candidate rejected by the per-project validator
#: would make this whole proof pass for the wrong reason.
TOO_BIG = {"shared_buffers_mb": 896, "shm_size_mb": 896, "memory_limit_mb": 1280}


def test_a_candidate_that_does_not_fit_is_refused_with_exit_twelve(
    tmp_path: Path, host_manifest: Path, deployment: Path
) -> None:
    manifest = write_manifest(tmp_path, slug="gamma", database=TOO_BIG)
    result = run_admit(
        "--host", str(host_manifest), "--project", str(manifest), "--root", str(deployment)
    )
    assert result.returncode == 12, result.stdout + result.stderr
    assert "admission: refused" in result.stdout
    assert "1072" in result.stdout and "992" in result.stdout


def test_the_candidate_that_does_not_fit_is_a_legal_project(tmp_path: Path) -> None:
    """The control that makes the refusal mean anything (D1608).

    `_validate_memory_budget` must ACCEPT this budget on its own. If it did
    not, the refusal above would be the per-project guardrail firing and the
    cross-project decision would be untested -- a proof passing for the
    opposite of its stated reason.
    """
    manifest = write_manifest(tmp_path, slug="gamma", database=TOO_BIG)
    loaded = config.load_project_manifest(manifest)
    budget = config.database_budget(loaded["database"])
    assert budget["unreclaimable_mb"] == 1072
    assert budget["unreclaimable_mb"] <= config.HOST_MEMORY_GUARDRAIL_MB


def test_a_candidate_that_fits_is_admitted(
    tmp_path: Path, host_manifest: Path, deployment: Path
) -> None:
    """The control. Without it, a command that refused everything passes."""
    manifest = write_manifest(tmp_path, slug="gamma")
    result = run_admit(
        "--host", str(host_manifest), "--project", str(manifest), "--root", str(deployment)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "admission: admitted" in result.stdout


def test_a_redeploy_charges_only_the_other_projects(
    tmp_path: Path, host_manifest: Path, deployment: Path
) -> None:
    """beta-dev raising its own budget is charged against alpha-dev alone.

    Charged against its own committed 304 as well it would see 992 and be
    refused -- for memory it is about to stop using. 1072 against 1296 fits;
    against 992 it does not, so the number distinguishes the two
    implementations rather than passing under both.
    """
    manifest = write_manifest(tmp_path, slug="beta", database=TOO_BIG)
    result = run_admit(
        "--host", str(host_manifest), "--project", str(manifest), "--root", str(deployment)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "alpha-dev" in result.stdout
    assert "beta-dev 304" not in result.stdout, (
        "beta-dev's own committed claim was charged against its redeploy"
    )


def test_no_declaration_refuses_a_new_project_and_admits_a_redeploy(
    tmp_path: Path, schema_two_host: Path, deployment: Path
) -> None:
    """The asymmetry that keeps this release a minor (D1584)."""
    new = write_manifest(tmp_path, slug="gamma")
    refused = run_admit(
        "--host", str(schema_two_host), "--project", str(new), "--root", str(deployment)
    )
    assert refused.returncode == 12, refused.stdout + refused.stderr
    assert "schema_version 3" in refused.stdout

    redeploy = write_manifest(tmp_path, slug="alpha")
    admitted = run_admit(
        "--host", str(schema_two_host), "--project", str(redeploy), "--root", str(deployment)
    )
    assert admitted.returncode == 0, admitted.stdout + admitted.stderr


def test_an_unknown_figure_fails_closed_naming_it(
    tmp_path: Path, host_manifest: Path, deployment: Path
) -> None:
    """A decision may fail closed; it may not guess.

    beta-dev's document is replaced with something that is not a document. Its
    claim is then unknown, and an unknown claim is not zero -- summing it as
    zero would admit a candidate on the strength of a file this command could
    not read.
    """
    (deployment / "beta-dev" / "outputs.json").write_text("{not json", encoding="utf-8")
    manifest = write_manifest(tmp_path, slug="gamma")
    result = run_admit(
        "--host", str(host_manifest), "--project", str(manifest), "--root", str(deployment)
    )
    assert result.returncode == 12, result.stdout + result.stderr
    assert "beta-dev" in result.stdout


def test_the_refusal_prints_the_six_lines(
    tmp_path: Path, host_manifest: Path, deployment: Path
) -> None:
    """Ordered, so an operator finds the number they can change by scanning."""
    manifest = write_manifest(tmp_path, slug="gamma", database=TOO_BIG)
    result = run_admit(
        "--host", str(host_manifest), "--project", str(manifest), "--root", str(deployment)
    )
    for label in (
        "declared memory",
        "reserved",
        "committed",
        "requested",
        "safe available",
        "suggested action",
    ):
        assert label in result.stdout, f"{label!r} is missing from the refusal"


def test_the_ceilings_line_says_it_could_not_read_them_rather_than_reporting_zero(
    tmp_path: Path, host_manifest: Path, deployment: Path
) -> None:
    """A figure that decides nothing may still not be invented.

    With no Docker daemon reachable in this suite the ceilings cannot be read,
    and the report must SAY so. Reporting `0 MiB of mem_limit` would be the
    most reassuring possible lie about a host.
    """
    manifest = write_manifest(tmp_path, slug="gamma")
    result = run_admit(
        "--host",
        str(host_manifest),
        "--project",
        str(manifest),
        "--root",
        str(deployment),
        "--json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    document = json.loads(result.stdout)
    ceilings = [line for line in document["lines"] if line["label"] == "ceilings"]
    assert len(ceilings) == 1
    value = ceilings[0]["value"]
    assert value.startswith("unknown") or "mem_limit" in value, value


def test_admit_renders_nothing_and_writes_nothing(
    tmp_path: Path, host_manifest: Path, deployment: Path
) -> None:
    """The refusal has to be free.

    This is the command an operator runs BEFORE committing to a deploy. One
    that left `.generated/<key>` behind would have changed the checkout it was
    refusing to deploy from -- D614's shape, one command earlier. The whole
    fixture root's mtime set is compared, not just a path somebody thought of.
    """

    def snapshot(root: Path) -> dict[str, float]:
        return {str(p): p.stat().st_mtime for p in sorted(root.rglob("*"))}

    generated = REPO_ROOT / ".generated"
    before_generated = sorted(p.name for p in generated.iterdir()) if generated.is_dir() else []
    before = snapshot(deployment)

    manifest = write_manifest(tmp_path, slug="gamma", database=TOO_BIG)
    result = run_admit(
        "--host", str(host_manifest), "--project", str(manifest), "--root", str(deployment)
    )
    assert result.returncode == 12

    assert snapshot(deployment) == before, "admit changed something under the project root"
    after_generated = sorted(p.name for p in generated.iterdir()) if generated.is_dir() else []
    assert after_generated == before_generated, "admit published something under .generated"


def test_the_json_carries_the_same_decision_as_the_text(
    tmp_path: Path, host_manifest: Path, deployment: Path
) -> None:
    """Two renderings, one answer.

    A `--json` that disagreed with the text would be the machine-readable
    half of a command telling an operator and a script two different things.
    """
    manifest = write_manifest(tmp_path, slug="gamma", database=TOO_BIG)
    common = ["--host", str(host_manifest), "--project", str(manifest), "--root", str(deployment)]
    text = run_admit(*common)
    document = json.loads(run_admit(*common, "--json").stdout)

    assert document["outcome"] == "refused"
    assert document["exit_code"] == text.returncode == 12
    assert document["requested_unreclaimable_mb"] == 1072
    assert document["already_deployed_here"] is False
    assert document["declaration_injected"] is False


def test_an_injected_declaration_is_marked_injected(
    tmp_path: Path, host_manifest: Path, deployment: Path
) -> None:
    """A rehearsal's reading may never be mistaken for the host's (ADR 0190).

    Both halves: the injection changes the answer, AND the answer says it was
    injected. Either one alone is a rehearsal whose record cannot be trusted
    later -- the evidence pattern `disk_headroom` already follows.
    """
    manifest = write_manifest(tmp_path, slug="gamma")

    honest = run_admit(
        "--host", str(host_manifest), "--project", str(manifest), "--root", str(deployment)
    )
    assert honest.returncode == 0
    assert "(injected)" not in honest.stdout

    injected = run_admit(
        "--host",
        str(host_manifest),
        "--project",
        str(manifest),
        "--root",
        str(deployment),
        "--reserve-memory-mb",
        "1000000000",
    )
    assert injected.returncode == 12, injected.stdout + injected.stderr
    assert "(injected)" in injected.stdout

    document = json.loads(
        run_admit(
            "--host",
            str(host_manifest),
            "--project",
            str(manifest),
            "--root",
            str(deployment),
            "--reserve-memory-mb",
            "1000000000",
            "--json",
        ).stdout
    )
    assert document["declaration_injected"] is True


def test_every_header_names_exit_twelve() -> None:
    """Four headers, one number (D1585).

    An operator reading `$?` has to be able to tell a refusal from a
    precondition (4) and from a failed check (6). A code documented in three
    places out of four is a code somebody will read the wrong table for.
    """
    headers = {
        "deploy.sh": REPO_ROOT / "deploy.sh",
        "bin/deploy-project.py": REPO_ROOT / "bin" / "deploy-project.py",
        "bin/admit.sh": ADMIT_SH,
        "bin/admit.py": ADMIT,
    }
    missing = []
    for name, path in headers.items():
        assert path.is_file(), f"{name} does not exist"
        # The header block only: the first 40 lines of each file, so a `12`
        # appearing in the body cannot satisfy this.
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:40])
        if "12" not in head or "admission" not in head.lower():
            missing.append(name)
    assert not missing, f"these headers do not name exit 12: {missing}"

    assert capacity_reading.EXIT_ADMISSION_REFUSED == 12


def test_the_one_convention_table_carries_the_row() -> None:
    """`docs/session-02-operator-guide.md` says a new code belongs in THAT
    table and not in a second one, so there is exactly one row."""
    guide = (REPO_ROOT / "docs" / "session-02-operator-guide.md").read_text(encoding="utf-8")
    assert guide.count("| `12` |") == 1
    assert "Admission refused" in guide


def test_the_deploy_decides_admission_before_it_renders() -> None:
    """An AST-free scan with a precise question: which comes first?

    A refusal arriving after the render has already rewritten
    `.generated/<key>` -- the checkout it was refusing to deploy from (D614).
    Ordering is the whole property, so ordering is what is measured.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")

    decide_at = source.find("capacity_reading.decide(")
    render_at = source.find('step("1. Render')
    assert decide_at != -1, "the deploy no longer decides admission at all"
    assert render_at != -1, "the render step's marker moved; this scan is measuring nothing"
    assert decide_at < render_at, (
        "the deploy renders before it decides admission, so a refusal would "
        "arrive after the checkout had already been rewritten (D614)"
    )

    refuse_at = source.find("EXIT_ADMISSION_REFUSED,")
    assert refuse_at != -1 and refuse_at < render_at, "the refusal does not fail before the render"

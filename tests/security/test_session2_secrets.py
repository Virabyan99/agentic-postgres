"""The live half of the secret boundary: one real value, looked for everywhere.

Reads the Session 2 sentinel through a root-only file and searches for the exact
byte sequence in every place a leak would land. It never prints what it matched,
and never prints a digest of it either — a digest of a low-entropy secret is a
checkable guess, and §16 forbids a digest as an isolation substitute regardless.

The structural half, which needs no secret and runs in CI, is
``test_session2_secret_model.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres.secrets_contract import (
    SECRET_ROOT,
    active_secrets,
    granted_services,
    load_secret_contract,
    secret_source_path,
)

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_SECRET_SENTINEL_FILE"
    ),
]


@pytest.fixture(scope="module")
def sentinel() -> str:
    """The sentinel value, in memory only.

    Never returned into an assertion message, a report, or a log line. Every
    failure below names a path or a container and stops there.
    """
    raw = Path(os.environ["APG_SECRET_SENTINEL_FILE"]).read_text(encoding="utf-8").strip()
    if not raw:
        pytest.fail("the sentinel file is empty; every scan below would prove nothing")
    if len(raw) < 16:
        pytest.fail("the sentinel is too short to be distinctive; a false negative is likely")
    return raw


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return load_secret_contract(REPO_ROOT / "secrets.required.yaml")


@pytest.fixture(scope="module")
def deployed_session(project_a: dict[str, Any]) -> int:
    """The session the deployment says it reached (ADR 0074, D213).

    Two proofs below ask the contract which secrets are active and which
    services are granted, and both passed the literal ``2`` until Run 10.
    Session 2 was the only session that existed when they were written, so the
    literal and the truth coincided -- and kept coinciding, because these
    thirteen proofs need ``--sentinel-file`` and it was not passed once in
    Session 5. Their first execution against a Session 5 deployment was the gate
    run on 2026-08-13, where a correct mount of a Session 5 grant read as a
    service helping itself.

    ``CURRENT_SESSION`` would be the repository's answer to a question about the
    *deployment*: a checkout at session 6 measuring a host still at session 5
    would expect grants that were never made. The document is the authority on
    what was deployed.
    """
    return int(project_a["deployed_through_session"])


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


def output(*command: str) -> str:
    """Both streams of a command, unjudged — a tool that failed leaked nothing."""
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return result.stdout + result.stderr


def project_containers(key: str) -> list[str]:
    names = [
        line.strip()
        for line in output(
            "docker", "ps", "--filter", f"label=apg.project.key={key}", "--format", "{{.Names}}"
        ).splitlines()
        if line.strip()
    ]
    if not names:
        pytest.fail(f"no running container carries the project label for {key}")
    return names


# ---------------------------------------------------------------------------
# SEC-SECRET-001 — the value is nowhere it should not be
# ---------------------------------------------------------------------------


def test_the_scan_would_find_a_planted_value_and_would_not_print_it(
    sentinel: str, tmp_path: Path
) -> None:
    """Guard the guard, twice over, before trusting any negative result below.

    A scanner that cannot find a planted value proves nothing, and one that
    echoes what it found turns every failure report into a second disclosure.
    """
    planted = tmp_path / "planted.conf"
    planted.write_text(f"token={sentinel}\n", encoding="utf-8")

    hits = [
        str(path)
        for path in tmp_path.rglob("*")
        if path.is_file() and sentinel in path.read_text(encoding="utf-8")
    ]

    assert hits == [str(planted)], hits
    assert sentinel not in " ".join(hits)


def test_the_sentinel_is_absent_from_every_git_visible_file(sentinel: str) -> None:
    tracked = output("git", "-C", str(REPO_ROOT), "ls-files").split()
    untracked = output("git", "-C", str(REPO_ROOT), "ls-files", "-o", "--exclude-standard").split()

    offenders: list[str] = []
    for relative in sorted({*tracked, *untracked}):
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        try:
            if sentinel in path.read_text(encoding="utf-8"):
                offenders.append(relative)
        except (UnicodeDecodeError, OSError):
            continue

    assert not offenders, f"the sentinel appears in repository files: {offenders}"


def test_the_sentinel_is_absent_from_container_inspection(
    sentinel: str, project_a: dict[str, Any]
) -> None:
    offenders = [
        name
        for name in project_containers(project_a["project"]["key"])
        if sentinel in output("docker", "inspect", name)
    ]
    assert not offenders, f"the sentinel is visible in docker inspect for: {offenders}"


def test_the_sentinel_is_absent_from_image_history(
    sentinel: str, project_a: dict[str, Any]
) -> None:
    """A build argument or a copied file would sit in a layer permanently."""
    images = {
        line.strip()
        for line in output(
            "docker",
            "ps",
            "--filter",
            f"label=apg.project.key={project_a['project']['key']}",
            "--format",
            "{{.Image}}",
        ).splitlines()
        if line.strip()
    }
    assert images, "no image was found for the project"

    offenders = [
        image
        for image in sorted(images)
        if sentinel in output("docker", "history", "--no-trunc", image)
    ]
    assert not offenders, f"the sentinel is present in image history for: {offenders}"


def test_the_sentinel_is_absent_from_the_systemd_journal(sentinel: str) -> None:
    journal = output("journalctl", "--no-pager", "--since", "-24h", "-u", "agentic-postgres-*")
    assert journal.strip(), "no journal output was captured; this scan proved nothing"
    assert sentinel not in journal, "the sentinel reached the systemd journal"


def test_the_sentinel_is_absent_from_container_logs(sentinel: str) -> None:
    names = [
        line.strip()
        for line in output("docker", "ps", "--format", "{{.Names}}").splitlines()
        if line.strip()
    ]
    assert names, "no containers are running; this scan proved nothing"
    offenders = [
        name for name in names if sentinel in output("docker", "logs", "--tail", "2000", name)
    ]
    assert not offenders, f"the sentinel reached container logs for: {offenders}"


def test_the_sentinel_is_absent_from_resolved_compose_output(
    sentinel: str, project_a: dict[str, Any]
) -> None:
    """The model may reference the file; it may never carry the value."""
    release = Path(project_a["runtime"]["release_path"])
    resolved = output(
        str(release / "bin" / "compose.sh"),
        "--runtime",
        str(Path(project_a["runtime"]["state_directory"])),
        "--profile",
        "session2",
        "config",
    )
    assert resolved.strip(), "compose config produced nothing; this scan proved nothing"
    assert sentinel not in resolved, "the sentinel appears in resolved Compose output"


def test_the_sentinel_is_absent_from_evidence(sentinel: str) -> None:
    evidence = REPO_ROOT / "evidence"
    files = [path for path in evidence.rglob("*.json") if path.is_file()]
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in files
        if sentinel in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"the sentinel reached evidence files: {offenders}"


# ---------------------------------------------------------------------------
# SEC-SECRET-002 — a materialized secret is readable only by its consumer
# ---------------------------------------------------------------------------


def test_materialized_files_are_read_only_and_owned_by_the_declared_consumer(
    contract: dict[str, Any], project_a: dict[str, Any], deployed_session: int
) -> None:
    """Every consumer the deployment carries, not the five Session 2 declared.

    **Stricter under ADR 0074, not weakened.** This read `session=2`, so five of
    eleven consumers were checked and `assert checked` reported success on the
    strength of the subset. The mode, uid, gid and non-emptiness of the Session 3
    to Session 5 consumers -- including the two root-plane ones ADR 0054
    introduced -- were measured by nothing.
    """
    key = project_a["project"]["key"]
    generation = project_a["secrets"]["generation_id"]

    checked = 0
    for secret in active_secrets(contract, session=deployed_session):
        for consumer in secret["consumers"]:
            path = Path(secret_source_path(key, generation, consumer))
            assert path.is_file(), f"{path} was not materialized"

            stat = path.stat()
            mode = oct(stat.st_mode & 0o777)
            assert mode == f"0o{consumer['mode'].lstrip('0')}" or mode == "0o400", (
                f"{path} is {mode}, expected {consumer['mode']}"
            )
            assert stat.st_uid == consumer["uid"], (
                f"{path} is owned by uid {stat.st_uid}, expected {consumer['uid']}"
            )
            assert stat.st_gid == consumer["gid"], (
                f"{path} has gid {stat.st_gid}, expected {consumer['gid']}"
            )
            assert stat.st_size > 0, f"{path} is empty"
            checked += 1

    assert checked, "no consumer was checked; the contract declares no active secret"


def test_only_the_granted_service_mounts_a_secret(
    contract: dict[str, Any], project_a: dict[str, Any], deployed_session: int
) -> None:
    """Proved by the mount list, never by comparing what each service read.

    A digest comparison would show two services hold different bytes. It would
    not show that the ungranted one could not have read the other's file, which
    is the claim.

    **The session is the deployment's, under ADR 0074.** Reading `session=2`,
    this failed the Session 5 gate on `postgrest` mounting
    `postgrest_authenticator_pgpass` -- a grant the contract declares, for a
    secret introduced in session 5, which a constant that stops at 2 cannot
    reach. The proof is stricter this way and not weaker: a container mounting a
    secret from a session *later* than the deployment still fails, and so does
    one mounting another service's copy, because the consumer's service name is
    a path component (D213).
    """
    granted = granted_services(contract, session=deployed_session)

    for name in project_containers(project_a["project"]["key"]):
        mounts = json.loads(
            output("docker", "inspect", "--format", "{{json .Mounts}}", name) or "[]"
        )
        secret_mounts = sorted(
            str(mount.get("Source", ""))
            for mount in mounts
            if str(mount.get("Source", "")).startswith(SECRET_ROOT)
        )
        labels = json.loads(
            output("docker", "inspect", "--format", "{{json .Config.Labels}}", name) or "{}"
        )
        service = labels.get("com.docker.compose.service")

        if service in granted:
            assert secret_mounts, f"{name} is granted a secret but mounts none"
        else:
            assert not secret_mounts, f"{name} mounts a secret it was not granted: {secret_mounts}"


def test_no_container_mounts_another_projects_secret_directory(
    project_a: dict[str, Any],
) -> None:
    own_root = f"{SECRET_ROOT}/{project_a['project']['key']}/"

    offenders: list[str] = []
    for name in output("docker", "ps", "--format", "{{.Names}}").splitlines():
        name = name.strip()
        if not name:
            continue
        mounts = json.loads(
            output("docker", "inspect", "--format", "{{json .Mounts}}", name) or "[]"
        )
        for mount in mounts:
            source = str(mount.get("Source", ""))
            if source.startswith(f"{SECRET_ROOT}/") and not source.startswith(own_root):
                labels = json.loads(
                    output("docker", "inspect", "--format", "{{json .Config.Labels}}", name) or "{}"
                )
                if labels.get("apg.project.key") == project_a["project"]["key"]:
                    offenders.append(f"{name} -> {source}")

    assert not offenders, f"containers mount another project's secret directory: {offenders}"


def active_generation(project_key: str) -> str:
    pointer = Path(SECRET_ROOT) / project_key / "active-secret-generation.json"
    assert pointer.is_file(), f"{pointer} does not exist"
    return json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]


def test_the_active_generation_pointer_names_a_real_generation(
    project_a: dict[str, Any],
) -> None:
    """What the name says, and only that.

    This used to also assert that the pointer equals
    ``project_a["secrets"]["generation_id"]``, and that equality does not hold
    and was never designed to. Every start materializes a *new* generation and
    repoints; the deployed document records the generation the deploy verified
    and is not rewritten afterwards, because rewriting it would mean systemd
    mutating ``/etc`` state at every boot. The two therefore diverge at the first
    restart. It passed for two sessions because on this host nothing had ever
    restarted a project between a deploy and a gate -- Run 8 restarts them on
    purpose, and a reboot restarts them without asking (D76, ADR 0038).

    What that equality was reaching for is measured by the test below, against
    the containers rather than against a second file.
    """
    key = project_a["project"]["key"]
    generation = Path(SECRET_ROOT) / key / "generations" / active_generation(key)
    assert generation.is_dir(), f"{generation} does not exist"
    assert oct(generation.stat().st_mode & 0o777) == "0o700"
    assert generation.stat().st_uid == 0, "the generation directory is not root-owned"


def test_the_running_containers_mount_the_generation_the_pointer_names(
    project_a: dict[str, Any],
) -> None:
    """The live claim: what is mounted is what the pointer says is current.

    Strictly stronger than the equality it replaces. Two files agreeing said
    nothing about any running process; this fails if a container is still
    holding a superseded generation -- which is exactly the state a restart that
    materialized but did not recreate would leave behind, and exactly what a
    rotation has to produce and then clear.
    """
    key = project_a["project"]["key"]
    active = f"{SECRET_ROOT}/{key}/generations/{active_generation(key)}/"
    generations_root = f"{SECRET_ROOT}/{key}/generations/"

    stale: list[str] = []
    for name in project_containers(key):
        mounts = json.loads(
            output("docker", "inspect", "--format", "{{json .Mounts}}", name) or "[]"
        )
        for mount in mounts:
            source = str(mount.get("Source", ""))
            if source.startswith(generations_root) and not source.startswith(active):
                stale.append(f"{name} -> {source}")

    assert not stale, (
        f"containers hold a generation the pointer has superseded (active {active}): {stale}"
    )

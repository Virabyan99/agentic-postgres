#!/usr/bin/env python3
"""Rehearse one bounded, reversible failure and read the detection that exists.

Invoked by `sudo bin/rehearse.sh SCENARIO --outputs FILE [--plan]` (ADR 0190,
ADR 0193). The plan -- what is induced, what is read, what is reversed -- is
`agentic_postgres.rehearsal`'s; this program reads the facts the plan needs off
the deployment, executes the three phases in order, reverses in a `finally`
whatever happened in between, verifies the reversal, and writes
`evidence/rehearsal-<key>-<scenario>-<id>.json`.

**One rehearsal at a time.** An in-progress file beside the projects' state
directory names the un-reversed scenario; a second scenario is refused while
it exists, and `reverse` replays the recorded reversal after a crash.

**What is printed is what this program produced**: exit codes, verdicts it
parsed out of the doctor's document, counts, seconds. Never a subprocess's
words (ADR 0159): the one third party here whose failure names paths and keys
is pgBackRest, and its stderr stays where it was.

Exit codes:
  0   the rehearsal ran, the reader read, the reversal verified
  2   invalid operator input
  3   missing prerequisite, or not root
  5   refused: another rehearsal is un-reversed, or the scenario has nothing
      to induce on this deployment (no mirror, no lock, no registry)
  6   the rehearsal ran and was reversed, and the reader read nothing --
      a finding, recorded in the evidence file
  7   the reversal did not verify; the in-progress file stays and names it
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import (
    REPO_ROOT,
    config,
    deployed_output,
    naming,
    port_allocations,
    rehearsal,
    runtime_override,
)

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5
EXIT_UNREAD = 6
EXIT_UNREVERSED = 7

QUICK_TIMEOUT_SECONDS = 60
DOCTOR_TIMEOUT_SECONDS = 180
CHECK_TIMEOUT_SECONDS = 600
POLL_SECONDS = 2.0


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def run(*argv: str, timeout: int = QUICK_TIMEOUT_SECONDS) -> subprocess.CompletedProcess | None:
    """Every subprocess, bounded; None when it could not complete at all."""
    try:
        return subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the deployed document is 0600 root and every scenario reaches "
            "Docker, the doctor or host state.",
        )


def resolve(hostname: str) -> tuple[str, ...]:
    """The endpoint's IPv4 addresses, sorted; empty when it does not resolve."""
    try:
        answers = socket.getaddrinfo(hostname, 443, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return ()
    return tuple(sorted({str(entry[4][0]) for entry in answers}))


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_rehearsal_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M") + secrets.token_hex(2)


def sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def load_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise OperatorError(EXIT_INPUT, f"deployed document not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise OperatorError(EXIT_INPUT, f"{path} is not readable as JSON: {error}") from error
    if not isinstance(document, dict) or document.get("document_kind") != "deployed":
        raise OperatorError(
            EXIT_INPUT,
            f"{path} is not a deployed document; a rehearsal reads the host's own record "
            "of the project (/etc/agentic-postgres/projects/<key>/outputs.json).",
        )
    return document


# ---------------------------------------------------------------------------
# The facts
# ---------------------------------------------------------------------------


def project_containers(compose_project: str) -> dict[str, str]:
    """Service name -> container name, for every container Compose started
    for this project, found by label rather than predicted (D55)."""
    listing = run(
        "docker",
        "ps",
        "-a",
        "--filter",
        f"label={runtime_override.COMPOSE_PROJECT_LABEL}={compose_project}",
        "--format",
        f'{{{{.Label "{runtime_override.COMPOSE_SERVICE_LABEL}"}}}}\t{{{{.Names}}}}',
    )
    containers: dict[str, str] = {}
    if listing is None or listing.returncode != 0:
        return containers
    for line in listing.stdout.splitlines():
        service, _, name = line.partition("\t")
        if service.strip() and name.strip():
            containers[service.strip()] = name.strip()
    return containers


def container_facts(name: str) -> tuple[int | None, int | None]:
    """(main process id, restart count), each None when unreadable."""
    inspected = run("docker", "inspect", "-f", "{{.State.Pid}} {{.RestartCount}}", name)
    if inspected is None or inspected.returncode != 0:
        return None, None
    parts = inspected.stdout.split()
    if len(parts) != 2:
        return None, None
    try:
        pid, count = int(parts[0]), int(parts[1])
    except ValueError:
        return None, None
    return (pid if pid > 0 else None), count


def network_subnet(network: str) -> str | None:
    inspected = run(
        "docker", "network", "inspect", "-f", "{{(index .IPAM.Config 0).Subnet}}", network
    )
    if inspected is None or inspected.returncode != 0:
        return None
    subnet = inspected.stdout.strip()
    return subnet if "/" in subnet else None


def gather_facts(
    document: dict[str, Any], arguments: argparse.Namespace, rehearsal_id: str
) -> rehearsal.Facts:
    key = str((document.get("project") or {}).get("key") or "")
    if not key:
        raise OperatorError(EXIT_INPUT, "the deployed document names no project key")
    compose_project = naming.compose_project_name(key)

    containers = project_containers(compose_project)
    pids: dict[str, int] = {}
    counts: dict[str, int] = {}
    for service, name in containers.items():
        pid, count = container_facts(name)
        if pid is not None:
            pids[service] = pid
        if count is not None:
            counts[name] = count

    routes = document.get("routes") or {}
    health = routes.get("health") or {}
    mcp_route = routes.get("mcp") or {}
    backup = document.get("backup") or {}
    mirror = config.backup_mirror(document) if backup else {"enabled": False}
    mirror_enabled = bool(backup) and config.backup_mirror_enabled(document)
    mirror_endpoint = str(mirror.get("endpoint") or "") or None
    observed = (document.get("database") or {}).get("observed") or {}
    instance_uuid = observed.get("instance_uuid") if isinstance(observed, dict) else None

    registry = Path(arguments.registry)
    lock_path = deployed_output.rendered_path(key, root=arguments.rendered_root) / (
        runtime_override.MCP_LOCK_FILENAME
    )
    lock_recorded = bool((document.get("mcp") or {}).get("capability_lock_sha256"))

    return rehearsal.Facts(
        project_key=key,
        rehearsal_id=rehearsal_id,
        outputs_path=str(arguments.outputs),
        doctor_argv=(
            sys.executable,
            str(REPO_ROOT / "bin" / "doctor.py"),
            "--root",
            str(arguments.state_root),
        ),
        backup_sh=str(REPO_ROOT / "bin" / "backup.sh"),
        database_ports_sh=str(REPO_ROOT / "bin" / "database-ports.sh"),
        containers=containers,
        container_pids=pids,
        restart_counts=counts,
        health_url=str(health.get("url") or "") or None,
        mcp_url=(str(mcp_route.get("url") or "") or None)
        if mcp_route.get("status") == "ready"
        else None,
        stanza=str(backup.get("stanza") or "") or None,
        bucket=str(backup.get("bucket") or "") or None,
        mirror_enabled=mirror_enabled,
        mirror_endpoint=mirror_endpoint,
        mirror_bucket=str(mirror.get("bucket") or "") or None,
        mirror_addresses=resolve(mirror_endpoint) if mirror_enabled and mirror_endpoint else (),
        backup_subnet=network_subnet(naming.backup_network_name(key)) if mirror_enabled else None,
        registry_path=str(registry),
        registry_present=registry.is_file(),
        registry_sha256=sha256_of(registry),
        instance_uuid=str(instance_uuid) if instance_uuid else None,
        lock_path=str(lock_path),
        lock_present=lock_path.is_file(),
        lock_recorded=lock_recorded,
        foreign_lock_path=str(
            Path(arguments.state_root)
            / key
            / f"{rehearsal.rule_comment(rehearsal_id)}-capability-lock.json"
        ),
        # Session 31. `None` for every scenario but `admission-refused`, which
        # refuses rather than planning around their absence: it asks whether
        # THIS host would admit THAT project, and neither manifest is
        # derivable from a deployed document.
        host_manifest=str(arguments.host) if arguments.host else None,
        project_manifest=str(arguments.manifest) if arguments.manifest else None,
        admit_py=str(REPO_ROOT / "bin" / "admit.py"),
    )


# ---------------------------------------------------------------------------
# Executing a phase
# ---------------------------------------------------------------------------


def execute(action: rehearsal.Action, facts: rehearsal.Facts) -> subprocess.CompletedProcess | None:
    """One action. File kinds are done here, never through a shell."""
    if action.kind == "none":
        return None
    if action.kind == "run":
        return run(*action.argv, timeout=CHECK_TIMEOUT_SECONDS)
    if action.kind == "rename":
        assert action.source and action.target
        if Path(action.target).exists():
            raise OperatorError(
                EXIT_REFUSED, f"{action.target} already exists; refusing to overwrite it"
            )
        os.replace(action.source, action.target)
        return None
    if action.kind == "write":
        assert action.target and facts.lock_path
        content = rehearsal.foreign_lock(
            Path(facts.lock_path).read_text(encoding="utf-8"), facts.rehearsal_id
        )
        target = Path(action.target)
        if target.exists():
            raise OperatorError(EXIT_REFUSED, f"{target} already exists; refusing to overwrite it")
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        return None
    if action.kind == "remove":
        assert action.target
        Path(action.target).unlink(missing_ok=True)
        return None
    raise OperatorError(EXIT_INPUT, f"unknown action kind {action.kind!r}")


def http_status(argv: tuple[str, ...]) -> int | None:
    result = run(*argv, timeout=30)
    if result is None or result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def doctor_checks(argv: tuple[str, ...], *names: str) -> dict[str, str | None]:
    result = run(*argv, timeout=DOCTOR_TIMEOUT_SECONDS)
    text = result.stdout if result is not None else ""
    return {name: rehearsal.doctor_check(text, name) for name in names}


def doctor_document(argv: tuple[str, ...]) -> dict[str, Any] | None:
    result = run(*argv, timeout=DOCTOR_TIMEOUT_SECONDS)
    if result is None:
        return None
    try:
        document = json.loads(result.stdout)
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


def observations(plan: rehearsal.Plan) -> dict[str, rehearsal.Observation]:
    return {observation.name: observation for observation in plan.observe}


def observe(plan: rehearsal.Plan, facts: rehearsal.Facts) -> dict[str, Any]:
    """Every reading of the scenario, as values this program parsed."""
    by_name = observations(plan)
    checks = rehearsal.DEPLOYED_DOCTOR_CHECKS
    readings: dict[str, Any] = {}

    if plan.scenario == "service-termination":
        container = facts.containers[rehearsal.HEALTH_SERVICE]
        before = facts.restart_counts.get(container, 0)
        started = time.monotonic()
        state = run(*by_name["state_after_kill"].argv)
        running, count = rehearsal.inspect_state(state.stdout if state else "")
        readings["state_after_kill"] = {"running": running, "restart_count": count}
        at_kill = doctor_checks(
            by_name["doctor_at_kill"].argv, checks["containers"], checks["health"]
        )
        readings["doctor_at_kill"] = at_kill
        readings["gap_reported"] = any(v is not None and v != "ok" for v in at_kill.values())
        readings["restart_count_before"] = before
        readings["restarted"] = False
        deadline = started + plan.bound_seconds
        while time.monotonic() < deadline:
            state = run(*by_name["restarted"].argv)
            running, count = rehearsal.inspect_state(state.stdout if state else "")
            if running and count is not None and count > before:
                readings["restarted"] = True
                readings["restart_count_after"] = count
                break
            time.sleep(POLL_SECONDS)
        readings["route_status_after"] = None
        while time.monotonic() < deadline:
            status = http_status(by_name["route_ready"].argv)
            if status == 200:
                readings["route_status_after"] = 200
                break
            readings["route_status_after"] = status
            time.sleep(POLL_SECONDS)
        readings["seconds_to_ready"] = round(time.monotonic() - started, 1)
        readings["doctor_after"] = doctor_checks(
            by_name["doctor_after"].argv, checks["containers"], checks["health"]
        )
        return readings

    if plan.scenario == "database-restart":
        started = time.monotonic()
        names = (checks["containers"], checks["database"], checks["health"])
        deadline = started + plan.bound_seconds
        after: dict[str, str | None] = {}
        while True:
            after = doctor_checks(by_name["doctor_recovered"].argv, *names)
            if all(after.get(name) == "ok" for name in names) or time.monotonic() >= deadline:
                break
            time.sleep(POLL_SECONDS * 2)
        readings["doctor_after"] = after
        readings["seconds_to_ok"] = round(time.monotonic() - started, 1)
        listing = run(*by_name["dependents_not_restarted"].argv)
        restarted: list[str] = []
        counts: dict[str, int | None] = {}
        for name in listing.stdout.split() if listing and listing.returncode == 0 else []:
            _, count = container_facts(name)
            counts[name] = count
            if count is not None and count > facts.restart_counts.get(name, 0):
                restarted.append(name)
        readings["restart_counts_after"] = counts
        readings["dependents_restarted"] = sorted(restarted)
        if "agent_route" in by_name:
            readings["agent_route_status"] = http_status(by_name["agent_route"].argv)
        return readings

    if plan.scenario == "backup-credential-failure":
        readings["repository"] = {"stanza": facts.stanza, "bucket": facts.bucket}
        wrong = run(*by_name["check_with_wrong_credential"].argv, timeout=CHECK_TIMEOUT_SECONDS)
        readings["wrong_credential_exit"] = wrong.returncode if wrong else "timeout"
        control = run(
            *by_name["check_with_deployed_credential"].argv, timeout=CHECK_TIMEOUT_SECONDS
        )
        readings["deployed_credential_exit"] = control.returncode if control else "timeout"
        readings["a_deploy_would"] = (
            "refuse at step 6c: the deploy fails on this check's non-zero exit"
            if readings["wrong_credential_exit"] != 0
            else "have converged over a credential that authenticates to nothing"
        )
        return readings

    if plan.scenario == "wal-archiving-failure":
        before = doctor_checks(by_name["doctor_before"].argv, checks["archiver"], checks["mirror"])
        readings["archiver_before"] = before[checks["archiver"]]
        readings["mirror_before"] = before[checks["mirror"]]
        copy = run(*by_name["mirror_copy_blocked"].argv, timeout=plan.bound_seconds)
        readings["blocked_copy_exit"] = copy.returncode if copy else "timeout"
        under = doctor_checks(
            by_name["doctor_under_block"].argv, checks["archiver"], checks["mirror"]
        )
        readings["archiver_under_block"] = under[checks["archiver"]]
        readings["mirror_under_block"] = under[checks["mirror"]]
        readings["blocked_addresses"] = list(facts.mirror_addresses)
        return readings

    if plan.scenario == "registry-loss":
        registry = Path(facts.registry_path or "")
        for name, observation in (
            ("show", by_name["show_refused"]),
            ("release", by_name["release_refused"]),
        ):
            result = run(*observation.argv)
            readings[f"{name}_exit"] = result.returncode if result else "timeout"
            readings[f"registry_present_after_{name}"] = registry.exists()
        return readings

    if plan.scenario == "disk-threshold":
        default = doctor_document(by_name["disk_default"].argv)
        text = json.dumps(default) if default else ""
        readings["disk_default"] = rehearsal.doctor_check(text, checks["disk"])
        for entry in (default or {}).get("checks") or []:
            if entry.get("name") == checks["disk"]:
                readings["disk_evidence"] = entry.get("evidence")
        readings["disk_warn"] = doctor_checks(by_name["disk_warn"].argv, checks["disk"])[
            checks["disk"]
        ]
        readings["disk_problem"] = doctor_checks(by_name["disk_problem"].argv, checks["disk"])[
            checks["disk"]
        ]
        return readings

    if plan.scenario == "capability-drift":
        readings["drift_foreign"] = doctor_checks(by_name["drift_foreign"].argv, checks["drift"])[
            checks["drift"]
        ]
        readings["drift_deployed"] = doctor_checks(by_name["drift_deployed"].argv, checks["drift"])[
            checks["drift"]
        ]
        return readings

    if plan.scenario == "admission-refused":
        # Both runs are `bin/admit.py --json`, so the decision is read out of
        # the command's own document rather than scraped from its prose --
        # D1114's rule with the machine-readable half already provided.
        for name in ("admission_as_declared", "admission_refused"):
            result = run(*by_name[name].argv, timeout=CHECK_TIMEOUT_SECONDS)
            if result is None:
                readings[name] = "timeout"
                continue
            try:
                # NOT `document`: in a `bin/` command that name means the
                # DEPLOYED document, and `test_container_selectors.py` reads
                # every `document[...]` here against the outputs schema by
                # name (D1184). This is admit's own report.
                decision = json.loads(result.stdout)
            except ValueError:
                readings[name] = "unreadable"
                continue
            readings[name] = decision.get("outcome")
            readings[f"{name}_exit"] = result.returncode
            if name == "admission_as_declared":
                # The half that stops a rehearsal proving nothing: the
                # control's own report must NOT claim an injected
                # declaration, or the two readings cannot be told apart.
                readings["control_declaration_injected"] = decision.get("declaration_injected")
        return readings

    if plan.scenario == "provider-loss":
        readings["record"] = rehearsal.PROVIDER_LOSS_RECORD
        return readings

    raise OperatorError(EXIT_INPUT, f"no observer for {plan.scenario!r}")


def delete_tagged_rules(comment: str) -> int | None:
    """Every DOCKER-USER rule with ``comment`` deleted; the number remaining,
    None when the chain could not be listed."""
    listing = run("iptables", "-S", "DOCKER-USER")
    if listing is None or listing.returncode != 0:
        return None
    for argv in rehearsal.iptables_delete_arguments(listing.stdout, comment):
        run(*argv)
    again = run("iptables", "-S", "DOCKER-USER")
    if again is None or again.returncode != 0:
        return None
    return len(rehearsal.iptables_delete_arguments(again.stdout, comment))


def reverse(
    plan: rehearsal.Plan, facts: rehearsal.Facts, readings: dict[str, Any]
) -> dict[str, Any]:
    """Every reverse action, then the verification: a dict of named booleans,
    all of which must hold for the rehearsal to count as reversed."""
    checks = rehearsal.DEPLOYED_DOCTOR_CHECKS
    verification: dict[str, Any] = {}
    shown: subprocess.CompletedProcess | None = None
    for action in plan.reverse:
        if action.conditional and readings.get(action.conditional):
            continue
        if action.kind == "run" and action.argv[:3] == ("iptables", "-S", "DOCKER-USER"):
            remaining = delete_tagged_rules(rehearsal.rule_comment(facts.rehearsal_id))
            readings["rules_remaining"] = remaining
            verification["no tagged rule remains"] = remaining == 0
            continue
        result = execute(action, facts)
        if plan.scenario == "registry-loss" and action.kind == "run":
            shown = result
        if plan.scenario == "wal-archiving-failure" and action.kind == "run":
            if action.argv[-1] == "mirror":
                readings["copy_after_reversal_exit"] = result.returncode if result else "timeout"
                verification["the copy after the reversal exited 0"] = (
                    bool(result) and result.returncode == 0
                )
            elif "doctor.py" in action.argv[1]:
                readings["mirror_after"] = rehearsal.doctor_check(
                    result.stdout if result else "", checks["mirror"]
                )

    if plan.scenario in {"service-termination", "database-restart"}:
        service = (
            rehearsal.HEALTH_SERVICE
            if plan.scenario == "service-termination"
            else rehearsal.DATABASE_SERVICE
        )
        container = facts.containers[service]
        state = run("docker", "inspect", "-f", "{{.State.Running}} {{.RestartCount}}", container)
        running, _ = rehearsal.inspect_state(state.stdout if state else "")
        verification[f"{container} is running"] = running is True
    elif plan.scenario == "registry-loss":
        registry = Path(facts.registry_path or "")
        verification["registry present with its original bytes"] = (
            registry.is_file() and sha256_of(registry) == facts.registry_sha256
        )
        verification["database-ports.sh show exits 0"] = bool(shown) and shown.returncode == 0
    elif plan.scenario == "capability-drift":
        verification["foreign lock absent"] = not Path(facts.foreign_lock_path or "").exists()
        verification["deployed lock unchanged"] = Path(facts.lock_path or "").is_file()
    return verification


# ---------------------------------------------------------------------------
# The in-progress file and the verbs
# ---------------------------------------------------------------------------


def state_path(state_root: Path) -> Path:
    return state_root.parent / rehearsal.STATE_FILENAME


def write_state(path: Path, document: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def refuse_if_in_progress(path: Path) -> None:
    if not path.exists():
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        detail = (
            f"{state.get('scenario')} on {state.get('project_key')} "
            f"(id {state.get('rehearsal_id')}, started {state.get('started_at')})"
        )
    except (OSError, ValueError):
        detail = "unreadable"
    raise OperatorError(
        EXIT_REFUSED,
        f"a rehearsal is un-reversed: {detail}. {path} names it; run "
        "`rehearse.sh reverse` to replay its reversal before inducing another.",
    )


def write_evidence(directory: Path, record: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = (
        directory / f"rehearsal-{record['project_key']}-{record['scenario']}"
        f"-{record['rehearsal_id']}.json"
    )
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def print_readings(readings: dict[str, Any]) -> None:
    for name, value in readings.items():
        rendered = (
            json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        )
        print(f"  {name:<28} {rendered}")


def rehearse(arguments: argparse.Namespace) -> int:
    document = load_document(arguments.outputs)
    rehearsal_id = new_rehearsal_id()
    facts = gather_facts(document, arguments, rehearsal_id)
    try:
        plan = rehearsal.plan(arguments.scenario, facts)
    except rehearsal.RehearsalError as error:
        raise OperatorError(EXIT_REFUSED, str(error)) from error

    if arguments.plan:
        print(rehearsal.render_plan(plan, facts))
        print("\nplan only: nothing was run, written or moved.")
        return 0

    progress = state_path(arguments.state_root)
    refuse_if_in_progress(progress)
    started_at = now()
    if plan.induced:
        write_state(progress, rehearsal.state_document(plan, facts, started_at=started_at))

    print(rehearsal.render_plan(plan, facts))
    print()
    readings: dict[str, Any] = {}
    verification: dict[str, Any] = {}
    try:
        for action in plan.induce:
            execute(action, facts)
        readings = observe(plan, facts)
    except Exception as error:
        # An observation that raised is a reading that was not taken, and the
        # rehearsal is unread -- never un-reversed. The reversal below runs
        # regardless, and the error is recorded where the readings would be.
        readings["error"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            verification = reverse(plan, facts, readings)
        except Exception as error:  # the reversal is reported, never swallowed
            verification = {"the reversal raised": False, "error": str(error)}

    reversed_ = all(value is True for name, value in verification.items() if name != "error")
    if reversed_ and plan.induced:
        progress.unlink(missing_ok=True)

    finished_at = now()
    evidence = rehearsal.record(
        plan,
        facts,
        started_at=started_at,
        finished_at=finished_at,
        readings=readings,
        reversed_=reversed_,
        verification=verification,
    )
    path = write_evidence(arguments.evidence_dir, evidence)

    print("readings")
    print_readings(readings)
    print("verification")
    print_readings(verification)
    print(
        f"\nrehearse: {plan.scenario} on {facts.project_key}: {evidence['verdict']} -- "
        f"{evidence['why']}"
    )
    print(f"rehearse: reversed: {'yes' if reversed_ else 'NO'}; evidence written to {path}")
    if not reversed_:
        print(
            f"rehearse: {progress} names what is left; `rehearse.sh reverse` replays the reversal",
            file=sys.stderr,
        )
        return EXIT_UNREVERSED
    return 0 if evidence["verdict"] in {"read", "recorded"} else EXIT_UNREAD


def reverse_from_state(arguments: argparse.Namespace) -> int:
    """Replay the reversal an interrupted rehearsal recorded, then verify."""
    progress = state_path(arguments.state_root)
    if not progress.exists():
        print("rehearse: no rehearsal is in progress; nothing to reverse")
        return 0
    try:
        state = json.loads(progress.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise OperatorError(
            EXIT_UNREVERSED, f"{progress} is unreadable ({error}); reverse by hand"
        ) from error
    print(
        f"rehearse: reversing {state.get('scenario')} on {state.get('project_key')} "
        f"(id {state.get('rehearsal_id')})"
    )
    comment = rehearsal.rule_comment(str(state.get("rehearsal_id")))
    verification: dict[str, Any] = {}
    for entry in state.get("reverse") or []:
        action = rehearsal.Action(
            what=str(entry.get("what")),
            kind=str(entry.get("kind")),
            argv=tuple(entry.get("argv") or ()),
            source=entry.get("source"),
            target=entry.get("target"),
            conditional=entry.get("conditional"),
        )
        print(f"  - {action.what}")
        if action.kind == "run" and action.argv[:3] == ("iptables", "-S", "DOCKER-USER"):
            verification["no tagged rule remains"] = delete_tagged_rules(comment) == 0
        elif action.kind == "rename":
            if action.target and Path(action.target).exists():
                verification[f"{action.target} present"] = True
            elif action.source and Path(action.source).exists():
                os.replace(action.source, action.target)
                verification[f"{action.target} present"] = Path(str(action.target)).is_file()
            else:
                verification[f"{action.target} present"] = False
        elif action.kind == "remove":
            Path(str(action.target)).unlink(missing_ok=True)
            verification[f"{action.target} absent"] = not Path(str(action.target)).exists()
        elif action.kind == "run" and not action.conditional:
            result = run(*action.argv, timeout=CHECK_TIMEOUT_SECONDS)
            verification[action.what] = bool(result) and result.returncode == 0
    recorded = state.get("registry_sha256")
    if recorded:
        for entry in state.get("reverse") or []:
            if entry.get("kind") == "rename" and entry.get("target"):
                verification["registry bytes unchanged"] = (
                    sha256_of(Path(entry["target"])) == recorded
                )
    print("verification")
    print_readings(verification)
    if all(value is True for value in verification.values()):
        progress.unlink(missing_ok=True)
        print("rehearse: reversed; the in-progress file is removed")
        return 0
    print(f"rehearse: the reversal did not verify; {progress} stays", file=sys.stderr)
    return EXIT_UNREVERSED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rehearse", description=__doc__, add_help=True)
    parser.add_argument("scenario", choices=(*rehearsal.SCENARIOS, "reverse"))
    parser.add_argument("--outputs", type=Path, help="the project's deployed document")
    parser.add_argument("--plan", action="store_true", help="print the three phases; do nothing")
    parser.add_argument("--evidence-dir", type=Path, default=REPO_ROOT / "evidence")
    parser.add_argument("--state-root", type=Path, default=deployed_output.PROJECT_STATE_ROOT)
    parser.add_argument("--rendered-root", type=Path, default=deployed_output.RENDERED_ROOT)
    parser.add_argument("--registry", type=Path, default=Path(port_allocations.REGISTRY_PATH))
    # Session 31 (ADR 0221). Required by `admission-refused` and ignored by
    # every other scenario -- checked in `main`, where the scenario is known,
    # rather than made globally required.
    parser.add_argument("--host", type=Path, default=None, help="the host manifest")
    parser.add_argument(
        "--manifest", type=Path, default=None, help="the candidate project manifest"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        require_root()
        if arguments.scenario == "reverse":
            return reverse_from_state(arguments)
        if arguments.outputs is None:
            raise OperatorError(EXIT_INPUT, "--outputs is required for a scenario")
        return rehearse(arguments)
    except OperatorError as error:
        print(f"rehearse: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())

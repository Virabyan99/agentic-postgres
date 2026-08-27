"""`OPS-001` — verbose prints more, and never prints more secret (ADR 0159).

**Sentinel scans, not pattern assertions.** D622: a redaction filter is a
denylist against a third party's future output, so a test of one is a test of the
denylist — it passes because the pattern matched the string the test chose, which
says nothing about what `pgbackrest` 2.60 will emit.

**Two sentinels, because there are two claims**, and the first draft of this file
conflated them:

* ``SUBPROCESS`` is planted in every command's stdout *and* stderr. Nothing a
  subprocess emits may reach the report.
* ``SENSITIVE`` is planted only in the deployed document's sensitive blocks —
  `bootstrap`, `secrets`, `jwt`, `backup`, `backup_state`, `tls`. Those are what
  make that document `0600 root`: a map of where the secrets are.

The blocks left clean are left clean deliberately. `routes.health.url` is the
address the public internet uses and `project.domain` is in DNS; poisoning them
would have asserted that printing a public URL is a leak, which is not a claim
worth making and would have forced the check to stop saying anything useful.

`test_the_scan_catches_a_deliberately_leaky_renderer` is the control, and it is
not optional: without it a scan looking at the wrong string reports success
forever (D374).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import uuid
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, diagnosis

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SUBPROCESS = f"APG-SUBPROC-CANARY-{uuid.uuid4().hex}"
SENSITIVE = f"APG-SECRET-CANARY-{uuid.uuid4().hex}"

#: Blocks the doctor may legitimately echo: public addresses and the identities
#: this repository derived. Poisoning these would assert that printing a public
#: URL is a leak.
PRINTABLE_BLOCKS = {
    "schema_version",
    "document_kind",
    "source_commit",
    "deployed_through_session",
    "template_version",
    "observed_at",
    "project",
    "routes",
    "database",
    "host",
    "edge",
    "runtime",
}

#: Blocks that must never appear in output, at any verbosity.
SENSITIVE_BLOCKS = {
    "bootstrap",
    "secrets",
    "jwt",
    "backup",
    "backup_state",
    "tls",
    "mcp",
    "api",
    "storage",
}


@pytest.fixture(scope="module")
def doctor() -> Any:
    """`bin/doctor.py`, imported the way this suite imports its other commands."""
    spec = importlib.util.spec_from_file_location("apg_doctor", REPO_ROOT / "bin" / "doctor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def document() -> dict[str, Any]:
    """A realistic deployed document with SENSITIVE planted in the sensitive half."""
    return {
        "schema_version": 13,
        "document_kind": "deployed",
        "source_commit": "0" * 40,
        "deployed_through_session": 11,
        "template_version": 1,
        "observed_at": "2026-08-27T00:00:00Z",
        "project": {"key": "apg-canary-dev", "domain": "canary.example.test"},
        "routes": {"health": {"url": "https://canary.example.test/healthz"}},
        "database": {
            "container": "apg-canary-dev-postgres-1",
            "name": "apg_canary_dev",
            "pooled": {"host": "127.0.0.1", "port": 1},
        },
        "host": {"id": "host-1"},
        "edge": {"stack_name": "apg-edge"},
        "runtime": {"release_path": "/opt/agentic-postgres/releases/abc"},
        # --- everything below is poisoned -----------------------------------
        "bootstrap": {
            "infisical_project_id": SENSITIVE,
            "runtime_identity_id": SENSITIVE,
            "state_path": f"/etc/{SENSITIVE}",
        },
        "secrets": {
            "generation_id": SENSITIVE,
            "generation_manifest": f"/var/lib/{SENSITIVE}/manifest.json",
            "required_names": [SENSITIVE],
        },
        "jwt": {"issuer": SENSITIVE},
        "backup": {"enabled": True, "stanza": SENSITIVE, "bucket": SENSITIVE},
        "backup_state": {"status": "ok", "last_full_backup_label": SENSITIVE},
        "tls": {"status": "ok", "certificate_sha256": SENSITIVE},
        "mcp": {"status": "ready", "capability_lock_sha256": SENSITIVE},
        "api": {"issuer": SENSITIVE},
        "storage": {"bucket": SENSITIVE},
    }


@pytest.fixture
def poisoned_run(monkeypatch: pytest.MonkeyPatch, doctor: Any) -> None:
    """Every subprocess answers with the sentinel on BOTH streams.

    Non-zero as well, because the tempting place to print a transcript is exactly
    the failing branch. The `docker ps` line is realistic — a container name is
    ADR 0159's one named carve-out, and poisoning it would certify a rule that
    ADR does not make.
    """

    def fake(*command: str, timeout: int = 0) -> subprocess.CompletedProcess[str]:
        joined = " ".join(command)

        # STRUCTURED channels answer realistically, so every probe reaches its
        # parsing path. The first draft of this rig returned non-zero for
        # everything, so every probe bailed early and the leak test was
        # measuring error branches only -- D605's rule, in the file written to
        # obey it: a rig that constructs a condition must measure that it did.
        if "ps" in command:
            stdout = "apg-canary-dev-postgres-1\trunning\tUp 2 hours (unhealthy)\n"
        elif "SELECT 1" in joined:
            stdout = "1\n"
        elif "migration_ledger" in joined:
            stdout = "21\n"
        elif "pg_stat_archiver" in joined:
            stdout = "5|2026-08-27 00:00:00+00|0||\n"
        elif "du" in command:
            stdout = "1024\t/var/lib/postgresql/18/docker\n"
        elif "df" in command:
            stdout = (
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/sda1 100000 20000 80000 20% /var/lib/postgresql\n"
            )
        elif "curl" in command:
            stdout = "200"
        elif "info" in command:
            stdout = json.dumps({"status": "ok", "last_full_backup_at": "2026-08-27T00:00:00Z"})
        else:
            # UNSTRUCTURED stdout -- an `openssl s_client` handshake is the real
            # case. The probe regexes a date out of it; everything else in it is
            # prose, and prose is where a credential appears.
            stdout = (
                f"CONNECTED(00000003)\nsubject=CN={SUBPROCESS}\n"
                f"NotAfter: Dec 31 23:59:59 2026 GMT\nverify error:{SUBPROCESS}\n"
            )

        return subprocess.CompletedProcess(
            args=list(command),
            returncode=0,
            stdout=stdout,
            # Every branch, including the successful ones: the tempting place to
            # print a transcript is the failing one, but a probe that printed
            # stderr unconditionally would leak on a warning too.
            stderr=f"stderr carrying {SUBPROCESS}: password={SUBPROCESS}\n",
        )

    monkeypatch.setattr(doctor, "run", fake)


def render(doctor: Any, *, verbose: bool) -> str:
    """Run every real probe against the stubbed layer, then render."""
    doc = document()
    checks: list[diagnosis.Check] = [doctor.probe_containers("apg-canary-dev")]
    checks.extend(doctor.probe_routes(doc))
    checks.append(doctor.probe_tls(doc))
    checks.append(doctor.probe_database(doc))
    checks.append(doctor.probe_migrations(doc))
    # The one whose third party talks about credentials for a living: a
    # `pgbackrest` failure names repository paths and S3 keys.
    checks.append(doctor.probe_repository("apg-canary-dev"))
    checks.append(doctor.probe_archiver(doc))
    checks.append(doctor.probe_disk(doc))
    return diagnosis.report(tuple(checks), project_key="apg-canary-dev", verbose=verbose)


# ---------------------------------------------------------------------------
# Claim 1: nothing a subprocess emitted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verbose", [False, True])
@pytest.mark.usefixtures("poisoned_run")
def test_no_subprocess_output_reaches_the_report(doctor: Any, verbose: bool) -> None:
    """The claim `OPS-001` makes, measured against the real probes.

    Both verbosities: verbose is the new risk, but a test that only checked the
    new flag would say nothing about whether the default had been leaking all
    along.
    """
    assert SUBPROCESS not in render(doctor, verbose=verbose), (
        "output carries a value a subprocess emitted. ADR 0159: what --verbose "
        "adds is resolution, never a third party's bytes."
    )


# ---------------------------------------------------------------------------
# Claim 2: nothing from the document's sensitive blocks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verbose", [False, True])
@pytest.mark.usefixtures("poisoned_run")
def test_no_sensitive_document_block_reaches_the_report(doctor: Any, verbose: bool) -> None:
    """The deployed document is `0600 root` because it is a map of where the
    secrets are. A diagnostic that reprinted that map at any verbosity would have
    undone the file mode."""
    assert SENSITIVE not in render(doctor, verbose=verbose)


@pytest.mark.usefixtures("poisoned_run")
def test_verbose_actually_prints_more(doctor: Any) -> None:
    """The premise. A verbose flag that changed nothing would satisfy every
    assertion above for the least interesting possible reason (D374)."""
    quiet, loud = render(doctor, verbose=False), render(doctor, verbose=True)
    assert len(loud) > len(quiet), "--verbose added nothing, so it proves nothing"
    assert " = " in loud, "verbose should print evidence pairs"


@pytest.mark.usefixtures("poisoned_run")
def test_every_probe_reached_its_parsing_path(doctor: Any) -> None:
    """THE PREMISE, and the first draft of this rig failed it silently.

    That draft returned non-zero for every command, so every probe took its
    early-return branch and the leak tests above were scanning error messages.
    They passed. D605's lesson exactly — *a rig that CONSTRUCTS a condition must
    MEASURE that it constructed it* — in the file written to obey it.

    An `UNKNOWN` here means a probe never got to the code that formats a value,
    and a leak test that cannot reach the formatting proves nothing about it.
    """
    rendered = render(doctor, verbose=True)
    assert "UNKNOWN" not in rendered, (
        f"a probe did not reach its parsing path, so the leak scan never exercised "
        f"its formatting:\n{rendered}"
    )


@pytest.mark.usefixtures("poisoned_run")
def test_the_containers_check_still_names_an_unhealthy_container(doctor: Any) -> None:
    """ADR 0159 draws its line by channel, not by origin: a container name is an
    identity `naming` derived and Compose was given, read back by position out of
    a `--format` line. Asserted so that tightening the rule to "no bytes at all"
    later is a deliberate act rather than a silent loss of the most useful line
    this check can print."""
    assert "apg-canary-dev-postgres-1" in render(doctor, verbose=False)


def test_the_scan_catches_a_deliberately_leaky_renderer() -> None:
    """THE CONTROL. Without it every assertion above could be scanning nothing.

    A renderer that does what a careless `--verbose` would do — append the
    transcript of the command behind each check — must be caught by the same
    assertion, spelled the same way.
    """
    leaked_stderr = f"ERROR: repo1-s3-key={SUBPROCESS}"
    rendered = (
        diagnosis.report(
            (diagnosis.archiver(failing=None, last_archived_time=None),),
            project_key="apg-canary-dev",
            verbose=True,
        )
        + f"\n    stderr: {leaked_stderr}"
    )
    assert SUBPROCESS in rendered, (
        "the scan did not find a sentinel in output that plainly contains one, so "
        "every test above is measuring nothing"
    )


# ---------------------------------------------------------------------------
# The structural half — asserted, not reviewed
# ---------------------------------------------------------------------------


def test_no_probe_puts_subprocess_output_into_a_check() -> None:
    """ADR 0159's mechanism, over `bin/doctor.py`'s source.

    Looks for `.stdout` or `.stderr` reaching a `diagnosis.*` call. Parsing them
    is fine and expected — `probe_disk` reads `df`'s fourth field — but the
    parsed *value* is what travels onward, and the parse happens before the call
    rather than inside it. `int(x.stdout)` could not leak text either way; the
    rule is spelled this way because a scan can check it and a reader can apply
    it without judgement, and one extra line is cheaper than an exemption.
    """
    tree = ast.parse((REPO_ROOT / "bin" / "doctor.py").read_text(encoding="utf-8"))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "diagnosis"
        ):
            continue
        for argument in [*node.args, *(kw.value for kw in node.keywords)]:
            for inner in ast.walk(argument):
                if isinstance(inner, ast.Attribute) and inner.attr in {"stdout", "stderr"}:
                    offenders.append(f"{node.func.attr} (line {node.lineno})")

    assert not offenders, (
        f"these calls pass subprocess output into a Check: {sorted(set(offenders))}. "
        "Parse it into a value first (ADR 0159)."
    )


def test_the_probes_do_not_know_about_verbose() -> None:
    """`verbose` reaches the renderer and nothing else.

    This is what makes "a probe cannot print more when verbose" structural: a
    probe that never receives the flag cannot branch on it, so no future probe
    has to remember the rule.
    """
    source = (REPO_ROOT / "bin" / "doctor.py").read_text(encoding="utf-8")
    for probe in source.split("def diagnose(")[0].split("def probe_")[1:]:
        name = probe.split("(")[0]
        assert "verbose" not in probe, f"probe_{name} references verbose; only the renderer may"


def test_the_evidence_helper_takes_values_rather_than_formatted_text() -> None:
    """`_pairs` does the `str()` itself, so a caller cannot hand it something it
    was given. A helper taking pre-formatted strings would make the rule a habit
    rather than a property."""
    assert diagnosis._pairs(count=3, flag=True, missing=None) == (
        ("count", "3"),
        ("flag", "True"),
        ("missing", "null"),
    )


def test_every_schema_block_is_classified_by_this_file() -> None:
    """The scan is only as good as the set it poisoned.

    Without this, a block added to `deployedDocument` later is a block neither
    list mentions — and both tests keep passing while covering less. D211's
    shape: a sweep scoped to a set nobody restated.
    """
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))
    declared = set(schema["$defs"]["deployedDocument"].get("properties") or {})
    unclassified = sorted(declared - PRINTABLE_BLOCKS - SENSITIVE_BLOCKS)
    assert not unclassified, (
        f"{unclassified} appear in the schema and in neither list here. Decide whether "
        "the doctor may echo them, then add them to PRINTABLE_BLOCKS or to "
        "SENSITIVE_BLOCKS and poison them in document()."
    )


def test_every_sensitive_block_is_actually_poisoned() -> None:
    """Guard the guard: a block listed as sensitive but never given a sentinel
    would be a block the leak tests silently do not cover."""
    body = json.dumps(document())
    for block in SENSITIVE_BLOCKS:
        assert block in body, f"{block} is classified sensitive but absent from document()"
    poisoned = {block for block, value in document().items() if SENSITIVE in json.dumps(value)}
    assert poisoned == SENSITIVE_BLOCKS, (
        f"these sensitive blocks carry no sentinel: {sorted(SENSITIVE_BLOCKS - poisoned)}"
    )

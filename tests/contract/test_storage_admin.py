"""The object-storage operator surface, and the parts of it a host cannot check.

**This module exists because the mutation battery had nothing to bite on here.**
Run 8's battery put fifteen mutations into the migration, the sweep and the
repository and every one went red -- and then the honest question was which
lines it had *not* been able to reach. `bin/storage-admin.py`'s own logic was the
answer: the verb-to-exit-code mapping, the `-i` on `docker exec`, and what
crosses into the container on stdin were covered by nothing at all, so a
mutation in any of them would have survived silently.

That is the same question Session 6 Run 14 turned into a standing rule, pointed
at a battery rather than at a defect: *which side of the system got the fix.*
Here it is *which side of the system got the test* -- the plane and the worker
were thoroughly measured and the command that drives them was not.

What cannot be asserted here is anything requiring a running container, and the
module says so rather than faking a container and calling the result a proof
(ADR 0065, ADR 0066: a rig is a second configuration of the product). The
container-side programs are checked for the properties that are readable from
their text, and their behaviour belongs to the host trip.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

COMMAND = REPO_ROOT / "bin" / "storage-admin.py"
WRAPPER = REPO_ROOT / "bin" / "storage-admin.sh"


@pytest.fixture(scope="module")
def command() -> Any:
    """The module, imported. Every side effect is behind `main()`."""
    specification = importlib.util.spec_from_file_location("apg_storage_admin", COMMAND)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# What crosses into the container, and how
# ---------------------------------------------------------------------------


def test_docker_exec_gets_dash_i_exactly_when_there_is_stdin(command, monkeypatch):
    """Without `-i` stdin is not attached and the program reads nothing.

    The container then exits 0 having done nothing, and the caller sees a
    success. This project's own notes record paying for that twice, in a
    different command, in a different session -- so it is asserted rather than
    remembered.

    Both directions are asserted. A command that always passed `-i` would work
    and would be wrong in the other way that matters: it allocates the stream for
    verbs that have no business receiving one.
    """
    seen: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = '{"ok": true}'
        stderr = ""

    def fake_run(arguments, **kwargs):
        seen.append(list(arguments))
        return Result()

    monkeypatch.setattr(command.subprocess, "run", fake_run)

    command.in_container("c1", "print(1)")
    assert "-i" not in seen[-1], "a verb with no stdin allocated an input stream"

    command.in_container("c1", "print(1)", stdin='{"a": 1}')
    assert seen[-1][:3] == ["docker", "exec", "-i"], (
        "a program that reads stdin was run without -i, so it would read nothing "
        "and the container would exit 0 having done nothing"
    )


def test_only_the_two_credential_halves_reach_the_container(command, monkeypatch, tmp_path):
    """A retired-credential file with extra members must not forward them.

    An operator's file is a file an operator wrote. If it happens to carry the
    account id, a Cloudflare API token or a note to themselves, none of that has
    any business crossing into a container -- and `json.dumps(pair)` would send
    all of it.
    """
    path = tmp_path / "retired.json"
    path.write_text(
        json.dumps(
            {
                "access_key_id": "AKID",
                "secret_access_key": "SECRET",
                "cloudflare_api_token": "MUST-NOT-TRAVEL",
                "note": "the one I rotated on Tuesday",
            }
        ),
        encoding="utf-8",
    )

    forwarded: dict[str, Any] = {}

    def fake_in_container(container, program, *arguments, stdin=None, timeout=900):
        forwarded["stdin"] = stdin
        return {"outcome": "revoked", "polls": []}

    monkeypatch.setattr(command, "require_root", lambda: None)
    monkeypatch.setattr(command, "load_document", lambda p: {"database": {}, "project": {}})
    monkeypatch.setattr(command, "storage_container", lambda d: "storage-1")
    monkeypatch.setattr(command, "in_container", fake_in_container)

    arguments = command.build_parser().parse_args(
        [
            "--outputs",
            "/dev/null",
            "confirm-revoked",
            "--retired-credential-file",
            str(path),
        ]
    )
    assert command.confirm_revoked(arguments) == 0

    sent = json.loads(forwarded["stdin"])
    assert set(sent) == {"access_key_id", "secret_access_key"}, (
        f"the command forwarded more than the credential pair: {sorted(sent)}"
    )
    assert "MUST-NOT-TRAVEL" not in forwarded["stdin"]


def test_no_credential_is_ever_an_argument(command, monkeypatch, tmp_path):
    """D105, asserted on the call rather than on the help text.

    `test_no_command_documents_a_secret_argument` reads `--help`, which catches a
    documented flag and not an undocumented one. This watches what actually goes
    into argv.
    """
    path = tmp_path / "retired.json"
    path.write_text(
        json.dumps({"access_key_id": "AKID-XYZ", "secret_access_key": "SECRET-XYZ"}),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def fake_in_container(container, program, *arguments, stdin=None, timeout=900):
        captured["arguments"] = arguments
        return {"outcome": "revoked", "polls": []}

    monkeypatch.setattr(command, "require_root", lambda: None)
    monkeypatch.setattr(command, "load_document", lambda p: {"database": {}, "project": {}})
    monkeypatch.setattr(command, "storage_container", lambda d: "storage-1")
    monkeypatch.setattr(command, "in_container", fake_in_container)

    arguments = command.build_parser().parse_args(
        ["--outputs", "/dev/null", "confirm-revoked", "--retired-credential-file", str(path)]
    )
    command.confirm_revoked(arguments)

    joined = " ".join(captured["arguments"])
    assert "AKID-XYZ" not in joined and "SECRET-XYZ" not in joined, (
        "a credential reached the argument vector, where ps, /proc/<pid>/cmdline "
        "and the docker daemon's own record of the exec can all read it"
    )


# ---------------------------------------------------------------------------
# The verdicts, which are the part an operator acts on
# ---------------------------------------------------------------------------


def _verb(command, monkeypatch, verb: str, answer: dict, extra: list[str] | None = None) -> int:
    monkeypatch.setattr(command, "require_root", lambda: None)
    monkeypatch.setattr(command, "load_document", lambda p: {"database": {}, "project": {}})
    monkeypatch.setattr(command, "storage_container", lambda d: "storage-1")
    monkeypatch.setattr(
        command,
        "in_container",
        lambda *a, stdin=None, timeout=900, **k: answer,
    )
    arguments = command.build_parser().parse_args(["--outputs", "/dev/null", verb, *(extra or [])])
    return int(arguments.handler(arguments))


def test_a_credential_that_reaches_the_bucket_exits_zero(command, monkeypatch):
    assert (
        _verb(
            command,
            monkeypatch,
            "verify-credential",
            {"accepted": True, "code": "404", "status": 404},
        )
        == 0
    )


def test_a_credential_that_does_not_reach_the_bucket_exits_refused(command, monkeypatch):
    """Exit 6, not 0 and not 5. The command ran; its answer is no."""
    assert (
        _verb(
            command,
            monkeypatch,
            "verify-credential",
            {"accepted": False, "code": "AccessDenied", "status": 403},
        )
        == command.EXIT_REFUSED
    )


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("revoked", 0),
        ("not_observed", 6),
        ("control_failed", 6),
    ],
)
def test_the_revocation_poll_reports_three_different_things(
    command, monkeypatch, tmp_path, outcome, expected
):
    """`not_observed` and `control_failed` are both non-zero and are not the same.

    A poll that timed out says nothing about the revocation -- R2 permission
    changes are eventually consistent and this project has never timed one. A
    poll whose CONTROL failed says nothing about anything, because the live
    credential stopped working during the run, and a retired credential failing
    for that reason would otherwise read as a successful revocation. Collapsing
    the two into "failed" would lose the distinction an operator acts on.
    """
    path = tmp_path / "retired.json"
    path.write_text(json.dumps({"access_key_id": "a", "secret_access_key": "b"}), encoding="utf-8")
    assert (
        _verb(
            command,
            monkeypatch,
            "confirm-revoked",
            {"outcome": outcome, "polls": []},
            ["--retired-credential-file", str(path)],
        )
        == expected
    )


def test_a_sweep_that_met_a_provider_failure_still_exits_zero(command, monkeypatch):
    """A failed delete is retried by design, so it is not a command failure.

    Exiting non-zero here would make a scheduled sweep look broken for exactly
    the condition it is built to absorb: the object keeps its lease, the lease
    expires, and the next sweep collects it.
    """
    assert (
        _verb(
            command,
            monkeypatch,
            "cleanup",
            {
                "expired": 1,
                "claimed": 2,
                "deleted": 1,
                "finished": 1,
                "lease_lost": 0,
                "failed": 1,
                "abandoned": 0,
                "failed_ids": ["11111111-1111-4111-8111-111111111111"],
            },
        )
        == 0
    )


# ---------------------------------------------------------------------------
# What the surface refuses to be
# ---------------------------------------------------------------------------


def test_no_verb_accepts_a_bucket_or_an_object_key(command):
    """The whole of STO-KEY-001, restated at the operator surface.

    A client cannot choose a key because the request model has no field for one.
    An operator must not be able to either -- a `--key` here would be a path from
    a typed string to a provider DELETE, and the database's record of what exists
    would no longer describe what is in the bucket.
    """
    parser = command.build_parser()
    forbidden = {"--bucket", "--key", "--object-key", "--prefix", "--endpoint"}

    subparsers = [
        action for action in parser._actions if hasattr(action, "choices") and action.choices
    ]
    seen: set[str] = set()
    for action in subparsers:
        for name, sub in (action.choices or {}).items():
            for option in sub._actions:
                seen.update(option.option_strings)
            assert isinstance(name, str)

    offending = seen & forbidden
    assert not offending, f"a verb accepts {sorted(offending)}"


def test_there_is_no_bucket_administering_verb(command):
    """ADR 0110, asserted rather than trusted to stay true.

    Creating a bucket, reading its identity back and issuing or revoking a token
    are Cloudflare REST operations a human performs with a credential no process
    here holds. The absence is the control: a verb that existed and refused would
    be a rule, and an absent verb is a property.
    """
    parser = command.build_parser()
    verbs: set[str] = set()
    for action in parser._actions:
        if getattr(action, "choices", None):
            verbs.update(str(name) for name in action.choices)

    assert verbs == {
        "status",
        "cleanup",
        "verify-credential",
        "credential-digest",
        "confirm-revoked",
    }, f"the verb set changed: {sorted(verbs)}"

    # Scanned for a CALL, not for a word, and it took two attempts to get the
    # width right. Reading the raw file tripped on this module's own docstring,
    # which cites Run 5's measured `CreateBucket` 403; counting the word in the
    # unparsed code then tripped on a `print()` explaining to an operator why a
    # `HeadBucket` cannot distinguish absent from not-yours.
    #
    # Both were the scan being wrong rather than the code, and in both cases the
    # fix was to narrow the scan rather than to move the prose -- because a scan
    # that forbids DISCUSSING an operation is a scan that gets an exemption
    # written for it, and D277 is the record of exemptions arriving that way.
    #
    # What is forbidden is an administering operation reachable as a call: an
    # attribute call on any object, or the operation's exact name as a string,
    # which is how botocore takes an operation for a presign. Prose containing
    # the word is not a call and never was.
    called = _administering_calls(COMMAND)
    assert not called, (
        f"the operator surface can perform {sorted(called)}. The runtime credential "
        "cannot (measured 403, Run 5) and ADR 0110 puts the credential that can "
        "outside this repository entirely"
    )


def test_the_container_programs_import_only_the_services_own_modules(command):
    """ADR 0093: the command reaches the service's logic by running it there.

    Each `python -c` program is code nobody lints, so what it imports is worth
    asserting. Anything reached through `app.*` is the image's own version of the
    logic; anything else would be this command reimplementing a service's
    behaviour inside the service's container, which has the shape of ADR 0093
    and none of its value.
    """
    import ast

    programs = {
        name: value
        for name, value in vars(command).items()
        if name.endswith("_PROGRAM") and isinstance(value, str)
    }
    assert len(programs) >= 4, f"expected the container programs, found {sorted(programs)}"

    allowed_roots = {"app", "asyncio", "dataclasses", "hashlib", "json", "sys", "time", "uuid"}
    for name, program in programs.items():
        tree = ast.parse(program)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                roots = {(node.module or "").split(".")[0]}
            else:
                continue
            unexpected = roots - allowed_roots
            assert not unexpected, f"{name} imports {sorted(unexpected)}"


def test_the_probe_key_cannot_collide_with_a_real_object_key(command):
    """ADR 0102 makes every real key `<prefix>v1/<uuid4>`.

    The probe reads a key that does not exist, so a collision would be harmless
    today -- and the segment is kept outside `v1/` anyway, because the next
    person to add a probe that WRITES should inherit a prefix that was already
    safe rather than have to notice.
    """
    for name in ("_PROBE_PROGRAM", "_REVOCATION_PROGRAM"):
        program = getattr(command, name)
        assert '"_probe/"' in program, f"{name} does not use the reserved probe segment"
        assert 'prefix + "v1/' not in program, f"{name} probes inside the real key space"


def test_the_wrapper_confirms_before_deleting_anything() -> None:
    """`cleanup` is the only verb that mutates, and what it mutates is at R2.

    A provider DELETE cannot be undone and the bytes are not recoverable from
    here, so the wrapper shows the queue and requires a typed word -- the shape
    `rotate-signing-key.sh` uses for `promote`, for the same reason: an operator
    approving a deletion should be reading what they are deleting.
    """
    text = WRAPPER.read_text(encoding="utf-8")
    assert 'if [ "${verb}" = "cleanup" ]; then' in text
    assert "Type CLEANUP to continue" in text
    assert '"${answer}" = "CLEANUP"' in text
    # And the escape hatch is explicit rather than implied, because a scheduled
    # sweep needs one and an undocumented one is how a confirmation quietly
    # stops happening.
    assert "--yes" in text


def test_the_wrapper_does_not_forward_its_own_flag() -> None:
    """`--yes` belongs to the wrapper and argparse has never heard of it.

    Forwarded, it would make every confirmed cleanup exit 2 -- a confirmation
    that works only when you decline it.
    """
    text = WRAPPER.read_text(encoding="utf-8")
    assert '[ "${argument}" = "--yes" ] && continue' in text


def test_the_storage_service_name_is_read_and_not_spelled(command) -> None:
    """One authority for the Compose service name (ADR 0002).

    A literal `"storage"` here would be a second place the name lives, and the
    symptom of a disagreement is a selector that matches nothing -- reported as
    "the service is down" while it is up, which is D293 exactly.
    """
    source = COMMAND.read_text(encoding="utf-8")
    assert "runtime_override.STORAGE_SERVICE" in source
    assert 'com.docker.compose.service=storage"' not in source
    assert command.runtime_override.STORAGE_SERVICE == runtime_override.STORAGE_SERVICE


def test_the_status_metrics_name_no_owner_and_no_key(command) -> None:
    """STO-URL-001 at the reporting surface.

    A key is the unguessable half of a bearer credential, and a per-owner
    breakdown would be a subject enumeration an operator already has a better
    command for. Asserted on the SELECT list rather than on an example run,
    because an example run only shows the rows that happened to exist.
    """
    statement = command._STATUS_SQL
    for column in ("object_key", "owner_id", "cleanup_lease_holder"):
        assert column not in statement, f"the status query selects {column}"


def _executable_text(path) -> str:
    """A module's code and its non-docstring string literals, without prose.

    Docstrings and comments are removed; everything else -- including the
    container programs, which are ordinary module-level assignments -- survives.
    A scan over the raw file cannot tell a warning about an operation from the
    operation, and this module's own docstring is the proof.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_the_prose_scan_would_catch_a_real_call() -> None:
    """Guard the guard: the narrowed scan must still see an actual call.

    Narrowing a scan is how a scan stops working, so the narrowing is tested
    against a module that contains the thing in code and the thing in prose.
    """
    import tempfile
    from pathlib import Path as _Path

    with tempfile.TemporaryDirectory() as directory:
        prose = _Path(directory) / "prose.py"
        prose.write_text('"""We never call CreateBucket."""\nx = 1\n', encoding="utf-8")
        assert "Bucket" not in _executable_text(prose)

        real = _Path(directory) / "real.py"
        real.write_text('"""Harmless."""\nclient.create_bucket(Bucket="b")\n', encoding="utf-8")
        assert "create_bucket" in _executable_text(real)
        assert "Bucket" in _executable_text(real)


#: Operations that administer a bucket rather than an object in one.
#:
#: Both spellings, because botocore takes either: `client.create_bucket(...)` as
#: a method, and `"CreateBucket"` as an operation name for a presign or an event
#: hook. A scan for one spelling only is a scan the other spelling walks past.
ADMINISTERING = frozenset(
    {
        "create_bucket",
        "delete_bucket",
        "list_buckets",
        "put_bucket_policy",
        "put_bucket_cors",
        "delete_bucket_policy",
        "CreateBucket",
        "DeleteBucket",
        "ListBuckets",
        "PutBucketPolicy",
        "PutBucketCors",
        "DeleteBucketPolicy",
    }
)


def _administering_calls(path) -> set[str]:
    """Administering operations reachable as a call, in a module and its programs.

    Walks the module's AST and, separately, the AST of every `*_PROGRAM` string
    -- those are ordinary module-level assignments, so their contents are code
    that will run inside a container and must be read as code rather than as
    text.
    """
    source = path.read_text(encoding="utf-8")
    found: set[str] = set()

    def scan(tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ADMINISTERING:
                found.add(node.attr)
            elif isinstance(node, ast.Name) and node.id in ADMINISTERING:
                found.add(node.id)
            elif isinstance(node, ast.Constant) and node.value in ADMINISTERING:
                found.add(str(node.value))

    module = ast.parse(source)
    scan(module)
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and any(
                isinstance(target, ast.Name) and target.id.endswith("_PROGRAM")
                for target in node.targets
            )
        ):
            scan(ast.parse(node.value.value))
    return found


def test_the_administering_scan_would_catch_a_real_call() -> None:
    """Guard the guard. Narrowing a scan is how a scan stops working.

    Three arms: prose mentioning the operation is allowed, a method call is
    caught, and an operation NAME inside a container program is caught -- the
    last because the programs are strings in this module and would otherwise be
    the one place an administering call could hide.
    """
    import tempfile
    from pathlib import Path as _Path

    with tempfile.TemporaryDirectory() as directory:
        prose = _Path(directory) / "prose.py"
        prose.write_text(
            '"""CreateBucket is refused 403."""\nprint("HeadBucket cannot tell")\n',
            encoding="utf-8",
        )
        assert _administering_calls(prose) == set()

        call = _Path(directory) / "call.py"
        call.write_text('client.create_bucket(Bucket="b")\n', encoding="utf-8")
        assert "create_bucket" in _administering_calls(call)

        inside = _Path(directory) / "inside.py"
        inside.write_text(
            '_X_PROGRAM = """\nclient.create_bucket(Bucket="b")\n"""\n', encoding="utf-8"
        )
        assert "create_bucket" in _administering_calls(inside), (
            "an administering call inside a container program was not seen, which "
            "is the one place it could actually be hidden"
        )

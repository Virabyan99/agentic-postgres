"""The connector compiler: what a connector file may say, and what it may not.

`CONN-DEF-001` (ADR 0236, ADR 0237, D1786, D1787). Compiled against the example
project's REAL lock and its real definitions -- the same `lock_view_for_project`
and the same workflow compiler step 6e calls -- so a connector's recorded scopes
are the ones the definition compiles to, never a second derivation.

The load-bearing proofs are the refusals, each naming the member it is about;
`test_the_example_sets_four_connectors_compile` is their control. The body
subset has TWO readers, the host's `check_body` and the service's
`connector_body.check`, and `test_the_two_body_validators_agree` holds them to
one verdict per case (D1682's pattern).

Nothing here reaches a database, a network or a container.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config, service_source
from agentic_postgres import connector_definition as cd
from agentic_postgres import workflow_definition as wd

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

EXAMPLE = REPO_ROOT / "project.example.yaml"
PROJECT_ROOT = REPO_ROOT / "projects" / "example"


@pytest.fixture(scope="module")
def lock() -> wd.LockView:
    return wd.lock_view_for_project(EXAMPLE)


@pytest.fixture(scope="module")
def definitions(lock: wd.LockView) -> dict[tuple[str, int], wd.Compiled]:
    return cd.definitions_for(PROJECT_ROOT, lock)


OUTBOUND = {
    "schema_version": 1,
    "name": "probe-out",
    "version": 1,
    "description": "a probe",
    "kind": "outbound",
    "event": "note_embedding.set@1",
    "retry": {"max": 2, "backoff_seconds": 2},
}
INBOUND = {
    "schema_version": 1,
    "name": "probe-in",
    "version": 1,
    "description": "a probe",
    "kind": "inbound",
    "workflow": "notes-inbox@1",
    "body": {
        "members": {
            "title": {"type": "string", "required": True, "max_length": 200},
            "content": {"type": "string", "required": True, "max_length": 4000},
        }
    },
}
SCHEDULED = {
    "schema_version": 1,
    "name": "probe-sched",
    "version": 1,
    "description": "a probe",
    "kind": "scheduled",
    "workflow": "notes-digest@1",
    "schedule": {"every_seconds": 60},
    "input": {"limit": 1},
}


def compile_it(
    document: dict[str, Any],
    lock: wd.LockView,
    definitions: dict[tuple[str, int], wd.Compiled],
) -> cd.CompiledConnector:
    config.validate_against_schema(document, cd.SCHEMA_NAME)
    return cd.compile(document, lock, definitions, source_sha256="0" * 64)


def refusal(
    document: dict[str, Any],
    lock: wd.LockView,
    definitions: dict[tuple[str, int], wd.Compiled],
) -> cd.ConnectorError:
    """The compiler's refusal, reached WITHOUT the schema -- so a case the
    schema also refuses still proves the compiler refuses it."""
    with pytest.raises(cd.ConnectorError) as refused:
        cd.compile(document, lock, definitions, source_sha256="0" * 64)
    return refused.value


def with_(document: dict[str, Any], **changes: Any) -> dict[str, Any]:
    changed = copy.deepcopy(document)
    for key, value in changes.items():
        if value is None:
            changed.pop(key, None)
        else:
            changed[key] = value
    return changed


# ---------------------------------------------------------------------------
# The three kinds
# ---------------------------------------------------------------------------


def test_the_three_kinds_compile(
    lock: wd.LockView, definitions: dict[tuple[str, int], wd.Compiled]
) -> None:
    """Each kind compiles to the row `connector_install` takes and the body the
    substrate reads: the route reads `body -> 'body'`, `connector_fire_due`
    reads `body -> 'input'`. No compiled form carries an endpoint."""
    outbound = compile_it(OUTBOUND, lock, definitions)
    assert (outbound.kind, outbound.event, outbound.retry_max, outbound.backoff_seconds) == (
        "outbound",
        "note_embedding.set@1",
        2,
        2,
    )
    assert outbound.definition_name is None and outbound.required_scopes == ()

    inbound = compile_it(INBOUND, lock, definitions)
    assert inbound.body()["body"] == {
        "members": {
            "content": {"type": "string", "required": True, "max_length": 4000},
            "title": {"type": "string", "required": True, "max_length": 200},
        }
    }
    assert inbound.event is None and inbound.every_seconds is None

    scheduled = compile_it(SCHEDULED, lock, definitions)
    assert scheduled.body()["input"] == {"limit": 1}
    assert scheduled.every_seconds == 60

    for compiled in (outbound, inbound, scheduled):
        install = compiled.as_install()
        assert set(install) == {
            "name",
            "version",
            "kind",
            "body",
            "source_sha256",
            "event",
            "definition_name",
            "definition_version",
            "required_scopes",
            "every_seconds",
            "retry_max",
            "backoff_seconds",
        }, "as_install carries more or less than connector_install's twelve non-endpoint values"
        assert "endpoint" not in repr(install).lower()


def test_a_member_of_another_kind_is_refused_by_name(
    lock: wd.LockView, definitions: dict[tuple[str, int], wd.Compiled]
) -> None:
    for document, member in (
        (with_(OUTBOUND, workflow="notes-inbox@1"), "workflow"),
        (with_(INBOUND, event="note_embedding.set@1"), "event"),
        (with_(SCHEDULED, body=INBOUND["body"]), "body"),
        (with_(OUTBOUND, retry=None), "retry"),
        (with_(SCHEDULED, schedule=None), "schedule"),
    ):
        refused = refusal(document, lock, definitions)
        assert refused.member == member, (member, str(refused))
    with pytest.raises(cd.ConnectorError) as refused_kind:
        cd.compile(with_(OUTBOUND, kind="webhook"), lock, definitions, source_sha256="0" * 64)
    assert refused_kind.value.member == "kind"


def test_an_outbound_connector_names_a_versioned_event(
    lock: wd.LockView, definitions: dict[tuple[str, int], wd.Compiled]
) -> None:
    for event in ("note_embedding.set", "note_embedding.set@0", "Note.set@1", "a.b.c.d.e@1"):
        refused = refusal(with_(OUTBOUND, event=event), lock, definitions)
        assert refused.member == "event" and "not an event reference" in refused.reason
        with pytest.raises(config.ManifestError):
            config.validate_against_schema(with_(OUTBOUND, event=event), cd.SCHEMA_NAME)
    for retry, word in (
        ({"max": 11, "backoff_seconds": 2}, "max 11"),
        ({"max": 1, "backoff_seconds": 0}, "backoff_seconds 0"),
    ):
        refused = refusal(with_(OUTBOUND, retry=retry), lock, definitions)
        assert refused.member == "retry" and word in refused.reason
    # The control: the bounds themselves compile.
    assert (
        compile_it(
            with_(OUTBOUND, retry={"max": 10, "backoff_seconds": 3600}), lock, definitions
        ).retry_max
        == 10
    )


def test_an_inbound_connector_names_a_definition_and_records_its_scopes(
    lock: wd.LockView, definitions: dict[tuple[str, int], wd.Compiled]
) -> None:
    """The scopes are the COMPILED definition's, read, never re-derived; a
    definition the set does not have at that version is refused naming what
    the set has."""
    compiled = compile_it(INBOUND, lock, definitions)
    assert compiled.required_scopes == definitions[("notes-inbox", 1)].required_scopes
    assert compiled.required_scopes == ("notes:write",)
    assert (compiled.definition_name, compiled.definition_version) == ("notes-inbox", 1)

    for workflow, sentence in (
        ("notes-inbox@2", "not a definition of this set's workflows/"),
        ("no-such@1", "not a definition of this set's workflows/"),
        ("notes-inbox", "not a definition reference"),
    ):
        refused = refusal(with_(INBOUND, workflow=workflow), lock, definitions)
        assert refused.member == "workflow" and sentence in refused.reason, refused.reason
    assert (
        "notes-inbox@1" in refusal(with_(INBOUND, workflow="no-such@1"), lock, definitions).reason
    )

    # A scheduled connector records its definition's scopes the same way.
    scheduled = compile_it(SCHEDULED, lock, definitions)
    assert scheduled.required_scopes == definitions[("notes-digest", 1)].required_scopes

    # Definitions compiled against ANOTHER lock are refused, not trusted.
    import dataclasses

    elsewhere = dataclasses.replace(lock, tools_sha256="f" * 64)
    refused = refusal(INBOUND, elsewhere, definitions)
    assert "compiled against another lock" in refused.reason


def test_a_scheduled_interval_is_bounded(
    lock: wd.LockView, definitions: dict[tuple[str, int], wd.Compiled]
) -> None:
    for seconds in (59, 86401):
        refused = refusal(with_(SCHEDULED, schedule={"every_seconds": seconds}), lock, definitions)
        assert refused.member == "schedule" and f"every_seconds {seconds}" in refused.reason
    for seconds in (60, 86400):
        assert (
            compile_it(
                with_(SCHEDULED, schedule={"every_seconds": seconds}), lock, definitions
            ).every_seconds
            == seconds
        )

    # Its input: literals, exactly the keys the definition reads.
    for supplied, member, sentence in (
        ({"limit": "{{input.limit}}"}, "input.limit", "is not a literal"),
        ({"limit": [1]}, "input.limit", "is not a literal"),
        ({}, "input", "does not give limit"),
        ({"limit": 1, "extra": 2}, "input", "gives extra"),
    ):
        refused = refusal(with_(SCHEDULED, input=supplied), lock, definitions)
        assert refused.member == member and sentence in refused.reason, (supplied, str(refused))


def test_the_body_subset_refuses_what_it_does_not_name(
    lock: wd.LockView, definitions: dict[tuple[str, int], wd.Compiled]
) -> None:
    """Both directions, because the body IS the run's input (D1787): a member
    no step reads is accepted for nothing, and a reference to an undeclared
    member fails every run `input_unresolved`. And a read member may not be
    optional, because the worker has no default for an absent key (D1831)."""
    members = INBOUND["body"]["members"]
    extra = {**members, "tag": {"type": "string", "required": True, "max_length": 10}}
    refused = refusal(with_(INBOUND, body={"members": extra}), lock, definitions)
    assert refused.member == "body" and "declares tag" in refused.reason

    only_title = {"title": members["title"]}
    refused = refusal(with_(INBOUND, body={"members": only_title}), lock, definitions)
    assert refused.member == "body" and "does not declare content" in refused.reason

    optional = {**members, "content": {**members["content"], "required": False}}
    refused = refusal(with_(INBOUND, body={"members": optional}), lock, definitions)
    assert refused.member == "body" and "not required" in refused.reason
    assert "D1831" in refused.reason

    for member, sentence in (
        ({"type": "string", "required": True}, "declares no max_length"),
        ({"type": "integer", "required": True, "minimum": 1}, "declares no minimum and maximum"),
        (
            {"type": "integer", "required": True, "minimum": 5, "maximum": 1},
            "minimum above maximum",
        ),
        ({"type": "boolean", "required": True, "max_length": 4}, "carries max_length"),
    ):
        broken = {**members, "title": member}
        refused = refusal(with_(INBOUND, body={"members": broken}), lock, definitions)
        assert refused.member == "body.members.title" and sentence in refused.reason, refused

    # The schema's half: no nesting, no seventeenth member, no stray key.
    for body in (
        {"members": {"title": {"type": "object", "required": True}}},
        {"members": {f"m{index}": {"type": "boolean", "required": True} for index in range(17)}},
        {
            "members": {
                "title": {"type": "string", "required": True, "max_length": 9, "pattern": "x"}
            }
        },
        {"members": {"Title": {"type": "boolean", "required": True}}},
    ):
        with pytest.raises(config.ManifestError):
            config.validate_against_schema(with_(INBOUND, body=body), cd.SCHEMA_NAME)


# ---------------------------------------------------------------------------
# The two readers of the subset
# ---------------------------------------------------------------------------

DECLARATION = {
    "members": {
        "title": {"type": "string", "required": True, "max_length": 5},
        "count": {"type": "integer", "required": False, "minimum": 0, "maximum": 10},
        "flag": {"type": "boolean", "required": False},
    }
}

#: Twelve cases, each with the verdict both readers must return.
CASES: tuple[tuple[str, Any, str | None], ...] = (
    ("missing required", {}, "missing:title"),
    ("extra member", {"title": "a", "other": 1}, "unexpected_member"),
    ("wrong type: string", {"title": 5}, "type:title"),
    ("wrong type: integer", {"title": "a", "count": "3"}, "type:count"),
    ("wrong type: boolean", {"title": "a", "flag": 1}, "type:flag"),
    ("string too long", {"title": "abcdef"}, "too_long:title"),
    ("integer out of range", {"title": "a", "count": 11}, "out_of_range:count"),
    ("bool given as a string", {"title": "a", "flag": "true"}, "type:flag"),
    ("empty body, nothing required", {}, None),
    ("nested object", {"title": {"a": 1}}, "type:title"),
    ("list", ["title"], "not_an_object"),
    ("exactly at the bound", {"title": "abcde", "count": 10, "flag": False}, None),
)


def test_the_two_body_validators_agree() -> None:
    """The host's `check_body` and the image's `connector_body.check` on the
    same twelve cases, with the verdict written here as well: agreement alone
    would pass two readers that were wrong the same way.

    "Empty body, nothing required" uses a declaration whose members are all
    optional, the one shape that reaches it."""
    service = service_source.load("connector_body")
    optional = {
        "members": {
            name: {**member, "required": False} for name, member in DECLARATION["members"].items()
        }
    }
    assert len(CASES) == 12
    for label, body, verdict in CASES:
        declaration = optional if label == "empty body, nothing required" else DECLARATION
        host = cd.check_body(declaration, body)
        image = service.check(declaration, body)
        assert host == image == verdict, (label, host, image, verdict)

    # A boolean is not an integer to either reader, though it is to Python.
    assert cd.check_body(DECLARATION, {"title": "a", "count": True}) == "type:count"
    assert service.check(DECLARATION, {"title": "a", "count": True}) == "type:count"


def test_a_refusal_carries_no_value_and_no_undeclared_name() -> None:
    """A refusal is a token and a DECLARED member's name. The value and an
    undeclared member's name are caller text, and the route puts the word in a
    response (ADR 0237)."""
    service = service_source.load("connector_body")
    secretish = "s3cr3t-value-" + "x" * 40
    for body in (
        {"title": secretish},
        {"title": "a", "count": secretish},
        {"title": "a", secretish: 1},
    ):
        for verdict in (cd.check_body(DECLARATION, body), service.check(DECLARATION, body)):
            assert verdict is not None and "s3cr3t" not in verdict


# ---------------------------------------------------------------------------
# The shipped set
# ---------------------------------------------------------------------------


def test_the_example_sets_four_connectors_compile(
    lock: wd.LockView, definitions: dict[tuple[str, int], wd.Compiled]
) -> None:
    """**The control for every refusal above**, over the files step 6e installs
    on beta: two outbound on one event, one inbound, one scheduled. No file
    names an endpoint -- the manifest does (D1786)."""
    paths = cd.connectors_of(PROJECT_ROOT)
    assert [path.name for path in paths] == [
        "note-embedded.yaml",
        "notes-deadletter.yaml",
        "notes-digest.yaml",
        "notes-inbox.yaml",
    ]
    compiled = {path.name: cd.compile_file(path, lock, definitions) for path in paths}
    assert {name: c.kind for name, c in compiled.items()} == {
        "note-embedded.yaml": "outbound",
        "notes-deadletter.yaml": "outbound",
        "notes-digest.yaml": "scheduled",
        "notes-inbox.yaml": "inbound",
    }
    assert compiled["note-embedded.yaml"].event == "note_embedding.set@1"
    assert compiled["notes-deadletter.yaml"].event == "note_embedding.set@1"
    assert compiled["notes-inbox.yaml"].required_scopes == ("notes:write",)
    assert compiled["notes-digest.yaml"].required_scopes == ("notes:read",)
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text and "https://" not in text, path.name
        assert compiled[path.name].source_sha256 == wd.source_digest(path)
        assert "endpoint" not in yaml.safe_load(text)


def test_the_init_skeletons_validate(
    tmp_path: Path, lock: wd.LockView, definitions: dict[tuple[str, int], wd.Compiled]
) -> None:
    """**The round trip, D1836**: `bin/connector.sh init` prints a skeleton of
    each kind, and the product's own `validate` compiles each as printed -- a
    scaffold whose first edit had to be structural would teach the wrong file.

    The inbound skeleton declares exactly the members its definition reads and
    the scheduled one gives exactly its keys, so the compiler's both-direction
    checks are what this proves the scaffold satisfies. The compiled kinds are
    read back so an `init` that printed the wrong kind cannot pass.
    """
    import subprocess

    command = REPO_ROOT / "bin" / "connector.sh"
    for kind in cd.KINDS:
        printed = subprocess.run(
            [str(command), "init", "--kind", kind, "--project", str(EXAMPLE)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            cwd=tmp_path,
        )
        assert printed.returncode == 0, (kind, printed.stderr)
        assert not list(tmp_path.iterdir()), "init wrote a file; it streams to stdout"
        skeleton = tmp_path.parent / f"{tmp_path.name}-{kind}.yaml"
        skeleton.write_text(printed.stdout, encoding="utf-8")

        validated = subprocess.run(
            [str(command), "validate", "--project", str(EXAMPLE), "--file", str(skeleton)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert validated.returncode == 0, (kind, validated.stderr, printed.stdout)
        assert "1 connector(s) compile" in validated.stdout
        assert cd.compile_file(skeleton, lock, definitions).kind == kind

    refused = subprocess.run(
        [str(command), "init", "--kind", "sideways", "--project", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert refused.returncode == 2
    assert refused.stdout == ""


def test_connectors_of_a_project_with_no_directory_is_empty(tmp_path: Path) -> None:
    assert cd.connectors_of(tmp_path) == []

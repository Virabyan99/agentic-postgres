"""A selector may only use labels the service it selects actually carries (D587).

**This module exists because a host deploy found what the gate could not.**
`bin/backup.py` selected the database container with
`label=apg.project.key=<key>` from Run 6, and `bin/restore-test.py` copied it in
Run 8. That label is applied by `compose.yaml` to six **edge-facing** services --
`edge-probe`, `postgrest`, `docs`, `auth`, `storage`, `mcp` -- and to none of
`postgres`, `pgbouncer` or `dbmate`.

So the selector returned **0 containers on a healthy cluster**, measured on the
host in the same invocation that showed Compose's own pair returning **1**. It
went unnoticed for five runs because step 6c had never executed against a
deployment: §6's question 2, and question 3 in the same breath -- *whose
identity, through which tool, and is it the one production uses.*

The check below is the general form rather than a patch. For each first-party
label a selector relies on, the service it selects must declare it in the
**rendered Compose model** -- not in `compose.yaml`'s text, because a label can
arrive through the runtime override, and not by naming the services, because the
next service to lose a label would not be in the list.

`com.docker.compose.*` labels are exempt and stated as such: Compose applies them
at container creation, so they are absent from `config` output and present on
every container. That exemption is the one thing here taken on documentation
rather than measurement, and the host measurement above is what stands behind it.
"""

from __future__ import annotations

import ast
import json
import subprocess
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0]

#: Labels Compose itself applies to every container it creates.
COMPOSE_OWNED_PREFIX = "com.docker.compose."

#: The rendered fixture whose model these selectors are checked against.
FIXTURE = "fixture-alpha-dev"


@pytest.fixture(scope="module")
def model() -> dict[str, Any]:
    """The RESOLVED Compose model, not `compose.yaml`'s text.

    A label can reach a service through `runtime_override`, so reading the
    committed file would miss one and reading it would be a second opinion about
    what Compose will do. This asks Compose.
    """
    rendered = REPO_ROOT / ".generated" / FIXTURE
    if not rendered.is_dir():
        pytest.fail(
            f"{rendered} does not exist; render the fixtures first "
            "(bin/session-01-check.sh step 3 does it)"
        )
    result = subprocess.run(
        # `--profile '*'` -- every profile, not `contract`. The six services that
        # carry `apg.project.key` all sit behind session profiles, so a
        # contract-only resolution shows none of them and this module would
        # then assert the label exists nowhere.
        [str(REPO_ROOT / "bin" / "compose.sh"), str(rendered), "--profile", "*", "config"],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(f"the model would not resolve: {result.stderr.strip()[:400]}")
    return yaml.safe_load(result.stdout)


def service_labels(model: dict[str, Any], service: str) -> dict[str, str]:
    block = (model.get("services") or {}).get(service) or {}
    labels = block.get("labels") or {}
    if isinstance(labels, list):
        return dict(item.split("=", 1) for item in labels if "=" in item)
    return {str(k): str(v) for k, v in labels.items()}


def selector_label_keys(filters: tuple[str, ...]) -> list[str]:
    """The label KEYS a `docker ps --filter` sequence relies on."""
    keys = []
    for value in filters:
        assert value.startswith("label="), f"not a label filter: {value!r}"
        keys.append(value[len("label=") :].split("=", 1)[0])
    return keys


def test_the_database_selector_uses_only_labels_postgres_carries(model: dict[str, Any]) -> None:
    """The defect, in its general form.

    Every first-party label the database selector uses must be declared on the
    `postgres` service in the resolved model. `apg.project.key` is not, which is
    exactly why the selector matched nothing.
    """
    filters = runtime_override.database_container_filters("apg-fixture-alpha-dev")
    labels = service_labels(model, runtime_override.DATABASE_SERVICE)

    for key in selector_label_keys(filters):
        if key.startswith(COMPOSE_OWNED_PREFIX):
            continue
        service = runtime_override.DATABASE_SERVICE
        assert key in labels, (
            f"the database selector filters on {key!r}, which the {service!r} service "
            f"does not declare. It declares {sorted(labels)}. A selector on a label "
            "the service does not carry matches nothing, on a cluster that is up and "
            "healthy (D587)."
        )


def test_postgres_really_does_not_carry_the_first_party_project_label(
    model: dict[str, Any],
) -> None:
    """The premise, asserted so the test above cannot pass vacuously.

    If `postgres` ever gains `apg.project.key`, this fails and someone re-reads
    the selector deliberately rather than discovering on a host that two
    reasonable-looking selectors now both work.
    """
    labels = service_labels(model, runtime_override.DATABASE_SERVICE)
    assert "apg.project.key" not in labels, (
        "the postgres service now declares apg.project.key. That is a change to "
        "the Compose model's labelling, and D587's selector reasoning should be "
        "re-read before it is relied on."
    )


def test_the_services_that_do_carry_it_still_do(model: dict[str, Any]) -> None:
    """The other half: the label is real and is on the edge-facing services.

    Without this, the two tests above would keep passing if `apg.project.key`
    vanished from the model entirely -- which would silently break the three
    `bin/` commands that legitimately select an edge-facing service with it.
    """
    carriers = [
        name
        for name in (model.get("services") or {})
        if "apg.project.key" in service_labels(model, name)
    ]
    assert carriers, "no service declares apg.project.key at all"
    assert runtime_override.DATABASE_SERVICE not in carriers


def test_the_deployed_document_carries_no_compose_block() -> None:
    """The premise of D592, asserted so the tests below cannot pass vacuously.

    The RENDERED document publishes `compose.project_name`; the DEPLOYED one --
    what `/etc/agentic-postgres/projects/<key>/outputs.json` holds, and what an
    operator passes to `bin/backup.sh --outputs` -- publishes no `compose` block
    at all. A selector that read the published value therefore worked from a
    render and raised from a deployment, which is exactly how step 6c passed and
    the very next operator command failed.
    """
    source = (REPO_ROOT / "src" / "agentic_postgres" / "deployed_output.py").read_text("utf-8")
    assert '"document_kind": "deployed"' in source, "this test is reading the wrong module"
    assert '"compose": {' not in source, (
        "the deployed document now carries a `compose` block. If it publishes "
        "`project_name`, D592's reasoning should be re-read before anything "
        "starts depending on it again."
    )


def test_the_selector_needs_only_the_project_key_which_both_kinds_carry() -> None:
    """One code path for both document kinds (D592).

    Deriving through `naming.compose_project_name` is not a second derivation
    under ADR 0002 -- it IS the authority, and `naming.derive` calls it too.
    What ADR 0002 forbids is re-implementing `f"apg-{key}"` elsewhere, which is
    what this exists to prevent.
    """
    from agentic_postgres import naming

    rendered_path = REPO_ROOT / ".generated" / FIXTURE / "outputs.json"
    if not rendered_path.is_file():
        pytest.fail(f"{rendered_path} does not exist; render the fixtures first")
    rendered = json.loads(rendered_path.read_text(encoding="utf-8"))

    key = rendered["project"]["key"]
    derived = naming.compose_project_name(key)

    # The published value and the derivation must agree, or one of them is wrong.
    assert derived == rendered["compose"]["project_name"], (
        "naming.compose_project_name disagrees with what the render published"
    )

    # And a document shaped like the DEPLOYED one -- no `compose` block at all --
    # must still produce the same filters.
    deployed = {"project": {"key": key}, "database": {"name": "x"}}
    assert "compose" not in deployed
    assert runtime_override.database_container_filters(
        naming.compose_project_name(deployed["project"]["key"])
    ) == runtime_override.database_container_filters(rendered["compose"]["project_name"])


def test_the_selector_reads_the_project_name_from_the_document() -> None:
    """The value is the deployed document's, not a second derivation of the key.

    `naming.compose_project_name` derives it and `outputs.json` publishes it
    (ADR 0002). A selector that rebuilt `apg-<key>` here would be a second
    authority over a name, and the model deliberately does not pin
    `container_name:` (D55) precisely so that nothing depends on predicting it.
    """
    rendered = REPO_ROOT / ".generated" / FIXTURE / "outputs.json"
    if not rendered.is_file():
        pytest.fail(f"{rendered} does not exist; render the fixtures first")
    document = json.loads(rendered.read_text(encoding="utf-8"))
    published = document["compose"]["project_name"]

    filters = runtime_override.database_container_filters(published)
    assert f"label={runtime_override.COMPOSE_PROJECT_LABEL}={published}" in filters

    with pytest.raises(ValueError, match="required"):
        runtime_override.database_container_filters("")


# ---------------------------------------------------------------------------
# The class guard: D592, D598 and D600 were one defect, three times
# ---------------------------------------------------------------------------

#: Every module that is handed a DEPLOYED document at runtime.
#:
#: `bin/backup.py` and `bin/restore-test.py` take `--outputs
#: /etc/agentic-postgres/projects/<key>/outputs.json`, which is the deployed
#: kind and the only kind an operator ever passes. `restore_drill` and
#: `backup_report` are handed the parsed result. `bin/doctor.py` loads it
#: itself, from `deployed_output.deployed_path`.
#:
#: **This tuple is hand-maintained, and that is a known weakness** (D637). The
#: guard it feeds is exactly the "guard the class, not the field" repair D600
#: called for — but a reader added without a line here is a reader the class does
#: not cover. Discovery was considered and rejected: 33 files under `bin/` and
#: `src/` read some `document["..."]`, and almost all of them are reading a
#: manifest, a bootstrap state or an OpenAPI document. A scan matching those
#: would trade a precise guard for a vague one, which is the trade
#: `_top_level_document_reads` already refuses one level down.
DEPLOYED_DOCUMENT_READERS = (
    "bin/backup.py",
    "bin/doctor.py",
    "bin/fleet.py",
    "bin/project-retire.py",
    "bin/restore-test.py",
    "src/agentic_postgres/retirement.py",
    "src/agentic_postgres/restore_drill.py",
    "src/agentic_postgres/backup_report.py",
)


def _deployed_document_keys() -> set[str]:
    """The deployed document's top-level members, from the schema that defines it."""
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))
    deployed = schema["$defs"]["deployedDocument"]
    return set(deployed.get("properties") or {})


def _top_level_document_reads(source: str) -> set[str]:
    """Every literal key read off a name spelled `document`.

    Matches `document["x"]` and `document.get("x")`. A read through an
    intermediate variable is not matched and is not meant to be -- the defect
    this catches is the direct one, three times over, and a scan that tried to
    follow assignments would trade a precise guard for a vague one.
    """
    keys: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "document"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "document"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
    return keys


def test_no_operator_command_reads_a_key_the_deployed_document_does_not_have() -> None:
    """One guard for a defect that arrived three times in one session.

    D592: `bin/backup.py` read `compose.project_name` and raised on every real
    invocation. D598: `restore_drill.build_plan` read `compose.volumes.postgres`
    and, one line later, `compose.networks.backup` -- refusing every drill with
    exit 5. D600: the same command read a `release` block that **no** document
    kind has, and wrote `"release": null` into every evidence document it ever
    produced, including the first real one.

    Each was found by a deployment failing, and each repair was scoped to the
    field that failed rather than to the class. This asks the question of every
    reader at once, against the schema that defines the document rather than
    against a list written here -- so a member added to or removed from
    `deployedDocument` moves this test with it.
    """
    deployed = _deployed_document_keys()

    # Premise, in both directions. Without the first this passes vacuously; the
    # second is what makes it discriminating, since `compose` is precisely the
    # block D592 and D598 read and the rendered document does publish it.
    assert len(deployed) > 5, (
        f"the schema's deployedDocument declares only {sorted(deployed)}; this test "
        "is reading the wrong definition and would accept anything"
    )
    assert "compose" not in deployed, (
        "the deployed document now declares a `compose` block. If that is intended, "
        "re-read D592 and D598 before anything starts depending on it again -- this "
        "test would no longer catch what it was written for"
    )

    for relative in DEPLOYED_DOCUMENT_READERS:
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        unknown = sorted(_top_level_document_reads(source) - deployed)
        assert not unknown, (
            f"{relative} reads {unknown} off a deployed document, and the schema's "
            f"deployedDocument declares no such member. Only the RENDERED document "
            f"carries `compose`, and nothing carries `release`. Derive it through "
            f"`naming` from `project.key`, which both kinds carry (D592/D598/D600)."
        )

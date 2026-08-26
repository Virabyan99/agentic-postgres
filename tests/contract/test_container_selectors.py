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

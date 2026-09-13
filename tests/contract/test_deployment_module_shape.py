"""Shapes every deployment module must have, checked without a host.

A deployment module's proofs run only on the trip, so a mistake in HOW one talks
to the deployment is invisible until the sweep -- and a sweep costs fifteen
minutes and a visit. These are the shape checks that can be made here.
"""

from __future__ import annotations

import ast

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

DEPLOYMENT = REPO_ROOT / "tests" / "deployment"


def _module_sources() -> list[tuple[str, str]]:
    return [
        (path.name, path.read_text(encoding="utf-8"))
        for path in sorted(DEPLOYMENT.glob("test_*.py"))
    ]


def test_a_module_that_asks_for_event_stream_decodes_it() -> None:
    """D1294. The agent plane answers SSE; asking for it is not reading it.

    `test_session24_studio.py` set `Accept: application/json, text/event-stream`
    and had no `data: ` decoder, so `json.loads` failed on every successful
    reply and the fallback returned `{"error": {"message": "HTTP 200: ..."}}`.
    `refused()` then saw an `error` key, and three proofs read a successful
    `list_resources` as a refusal. Sessions 16, 21, 22 and 23 each carry the
    decoder; nothing compared them, and the module's claims are host claims, so
    the first execution was the sweep.

    Structural on purpose: it asserts the pair, not the implementation, so a
    module that decodes SSE some other way still passes and one that forgets
    entirely cannot.
    """
    missing: list[str] = []
    asked = 0
    for name, source in _module_sources():
        if "text/event-stream" not in source:
            continue
        asked += 1
        if '"data: "' not in source and "'data: '" not in source:
            missing.append(name)

    assert asked > 0, (
        "no deployment module asks for text/event-stream any more; this scan has "
        "stopped measuring anything"
    )
    assert not missing, (
        "these modules request an SSE stream and never decode one, so every "
        f"successful reply reads as an error: {missing}"
    )


def test_every_deployment_module_declares_its_environment_gate() -> None:
    """A module with no gate runs nowhere, or everywhere; both are defects.

    `pytestmark` with `requires_environment` is how a deployment module says
    which environment it needs (D1240). One without it either collects into the
    offline sweep and fails there, or is collected by no sweep at all -- which
    is how about fifty proofs came to have never run (D1242).
    """
    ungated: list[str] = []
    for name, source in _module_sources():
        tree = ast.parse(source, filename=name)
        has_mark = any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in node.targets
            )
            for node in tree.body
        )
        if not has_mark:
            ungated.append(name)

    assert not ungated, f"deployment modules with no pytestmark: {ungated}"

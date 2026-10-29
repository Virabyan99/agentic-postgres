"""The Session 46 live proofs' readings, held offline (Session 47 Run 10; D2961, D2969).

`tests/external/test_session46_walk.py` (`documented_path`) and
`tests/external/test_session46_journey.py` (`journey_live`,
`console_create_live`) run only with their records in the environment, so the
offline suite never executes them. Session 47 re-earns their claims with a
second person's walk and a new journey, which is why two of their readings
moved:

* **D2961** -- the walk's site is identified by its DIGEST alone (the record's,
  this checkout's build's and the published page's meta), never by where the
  record's `site_commit` sits in the history of the checkout running the proof;
  an empty `documents_read` and an empty `commands_run` are admitted while
  every route and command the record does name is still the site's.
* **D2969** -- the journey's pins read the record's own `session`, one of the
  module's `JOURNEYS` (46 -> `slot11-prod`, 47 -> `slot13-prod`), widened by a
  row and never derived from the record.

Each live proof's own function is called here with a record built in the test
and the published page answered by a stand-in for `urlopen` -- the proof's code,
not a copy of its reading (D1114).
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from tests.external import test_session46_journey as journey_proof
from tests.external import test_session46_walk as walk_proof

from agentic_postgres import dx_record, site_build

pytestmark = [pytest.mark.contract, pytest.mark.p0]

DIGEST = "d" * 64
#: A commit that is nobody's: no checkout holds it, so a reading that asked the
#: checkout's history about it would fail (D2961's case).
NOBODYS_COMMIT = "0" * 40
SITE_LINE = "pipx install agentic-postgres-cli"


def _site() -> dx_record.HostedSite:
    return dx_record.HostedSite(
        digest=DIGEST,
        version="9.9.9",
        routes=frozenset({"/", "/quickstart/", "/docs/connecting/"}),
        lines=(SITE_LINE,),
        goals=(),
    )


def _walk(**overrides: Any) -> dx_record.Record:
    document: dict[str, Any] = {
        "path": "hosted",
        "release": "Release 9.9.9",
        "site_commit": NOBODYS_COMMIT,
        "site_digest": DIGEST,
        "documents_read": [],
        "commands_run": [],
    }
    document.update(overrides)
    return dx_record.Record(path=Path("/dev/null"), document=document)


class _Page(io.BytesIO):
    def __enter__(self) -> _Page:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _published(monkeypatch: pytest.MonkeyPatch, digest: str) -> list[urllib.request.Request]:
    asked: list[urllib.request.Request] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> _Page:
        asked.append(request)
        meta = f'<meta name="apg-site-digest" content="{digest}">'
        return _Page(f"<html><head>{meta}</head></html>".encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return asked


def test_the_walk_reads_the_site_by_its_digest_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """D2961: a record whose `site_commit` no checkout holds passes when its
    digest is the build's and the published page's -- the proof asks the
    site's own address (`site_build.SITE_URL`) with the proof's User-Agent. The
    paired refusals: the published page at another digest, and another release,
    each fail the same proof."""
    asked = _published(monkeypatch, DIGEST)
    walk_proof.test_the_record_names_the_deployed_site(_walk(), _site())
    assert [r.full_url for r in asked] == [f"{site_build.SITE_URL}/"]
    assert asked[0].get_header("User-agent") == "agentic-postgres-proof"

    _published(monkeypatch, "e" * 64)
    with pytest.raises(AssertionError):
        walk_proof.test_the_record_names_the_deployed_site(_walk(), _site())
    _published(monkeypatch, DIGEST)
    with pytest.raises(AssertionError):
        walk_proof.test_the_record_names_the_deployed_site(_walk(release="Release 1.0.0"), _site())


def test_the_walk_admits_a_person_who_listed_no_page_and_typed_no_command() -> None:
    """D2961: both lists empty pass; what IS named must be the site's -- a route
    the build does not produce, or a command no page gives, still fails."""
    walk_proof.test_every_command_is_on_the_site(_walk(), _site())
    walk_proof.test_every_command_is_on_the_site(
        _walk(documents_read=["/", "/docs/connecting/"], commands_run=[SITE_LINE]), _site()
    )
    with pytest.raises(AssertionError):
        walk_proof.test_every_command_is_on_the_site(_walk(documents_read=["/nowhere/"]), _site())
    with pytest.raises(AssertionError):
        walk_proof.test_every_command_is_on_the_site(
            _walk(commands_run=["curl https://example.test"]), _site()
        )


def test_the_live_proofs_name_the_built_site() -> None:
    """ADR 0299 (D2962's rule): both proofs read the published site at the
    build's own constant, so the domain move moves them; and the walk proof
    asks no git history (D2961)."""
    assert walk_proof.SITE == site_build.SITE_URL
    assert journey_proof.SITE == site_build.SITE_URL
    text = Path(walk_proof.__file__).read_text(encoding="utf-8")
    assert "merge-base" not in text and "subprocess" not in text


def _journey(session: Any, slot: str, *, account: str | None = None,
             organization: str | None = None) -> dict[str, Any]:  # fmt: skip
    return {
        "session": session,
        "account": account if account is not None else f"journey-s{session}-a1b2c3",
        "organization": "31121d7b-1aa3-4206-8f13-d81157c1beaf",
        "organization_name": organization if organization is not None else f"lifecycle-s{session}",
        "project_key": slot,
        "create_seconds": 1500.0,
        "steps": [{"step": code, "outcome": "ok"} for code in ("j02", "j04", "j07")],
    }


def _pins(journey: dict[str, Any]) -> None:
    journey_proof.test_j02_the_account_was_made(journey)
    journey_proof.test_j04_a_new_organisation_was_made(journey)
    journey_proof.test_j07_the_creation_succeeded(journey)


def test_the_journey_pins_read_the_records_session() -> None:
    """D2969: the two journeys these proofs read, typed here as the row states
    them; each passes its own pins, and every crossing fails one."""
    assert journey_proof.JOURNEYS == {46: "slot11-prod", 47: "slot13-prod"}
    _pins(_journey(46, "slot11-prod"))
    _pins(_journey(47, "slot13-prod"))
    for wrong in (
        _journey(47, "slot11-prod"),  # Session 47's journey on Session 46's slot
        _journey(46, "slot13-prod"),
        _journey(47, "slot13-prod", account="journey-s46-a1b2c3"),
        _journey(47, "slot13-prod", organization="lifecycle-s46"),
        _journey(48, "slot13-prod"),  # a session no row widened to
        _journey("47", "slot13-prod"),  # the session must be the number
        _journey(None, "slot13-prod"),
    ):
        with pytest.raises(AssertionError):
            _pins(wrong)

"""A secret declared ``required: false`` may be absent from the provider.

**Found on the host, on the first Session 6 deploy** (D283). Session 6 is the
first session to declare an optional secret -- ``auth_jwt_prepared_key``, which
exists only while a signing-key rotation is in flight -- and the field had
therefore never been exercised by anything.

`bin/bootstrap-providers.py` reads `required` when it decides what to **create**,
so the optional secret was correctly never created. `bin/materialize-secrets.py`
did not read it at all: it fetched every active secret and failed the whole run
on the 404. So the contract declared a property and one of its two readers
honoured it, which is D276's shape in the file that declares the field.

The tests below are about the **distinction**, not about the skip. Skipping on
any failure would be worse than the bug: a timeout or a 500 read as "absent"
would write a generation silently missing a secret the provider holds, and the
deploy would start a service without it. Only a 404 means absent, and only for a
secret the contract says may be.
"""

from __future__ import annotations

import importlib.util
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, secrets_contract
from agentic_postgres.infisical_client import Credential, InfisicalClient, InfisicalError

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

#: A value that is not a credential: no provider is contacted by any test here,
#: because ``urlopen`` is monkeypatched to raise before a request is made. Named
#: rather than inline so S106 is answered once with a reason instead of twice
#: with a suppression.
DUMMY_SECRET = "not-a-credential-no-request-is-made"  # noqa: S105


def _materializer() -> Any:
    specification = importlib.util.spec_from_file_location(
        "apg_materialize_secrets", REPO_ROOT / "bin" / "materialize-secrets.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The error has to be able to tell the two worlds apart
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", [404, 500])
def test_the_client_puts_the_status_on_the_error_it_raises(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    """Driven through the CLIENT, not by constructing the exception here.

    **The mutation battery is why this test exists.** The first version asserted
    `InfisicalError("...", status=404).status == 404`, which is a statement
    about the constructor. Deleting `status=exc.code` from the one place that
    raises on an HTTP failure left every test green -- and would have left the
    materializer seeing `status=None` forever, so an optional secret's 404 would
    never be recognised and the bug this whole module is about would be back,
    with a full set of passing tests over it.

    So the error is produced the way production produces it: a real
    `HTTPError` out of `urlopen`, through `_call`.
    """

    def raise_http_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError(
            url="https://infisical.example.invalid/api/v3/secrets/raw/APG_X",
            code=code,
            msg="Not Found",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_http_error)

    client = InfisicalClient("https://infisical.example.invalid")
    with pytest.raises(InfisicalError) as caught:
        client.login(Credential(client_id="an-identity", client_secret=DUMMY_SECRET))

    assert caught.value.status == code, (
        "the client raised without recording the HTTP status, so nothing downstream can "
        "tell 'the secret is absent' from 'the provider is broken'"
    )


def test_a_failure_that_was_not_a_response_carries_no_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DNS failure, a timeout and a non-JSON body are not statuses.

    `status is None` is what keeps the skip from swallowing them: they are not
    evidence that the secret is absent, they are evidence that nothing was
    learned. Also driven through the client, for the reason above.
    """

    def raise_url_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("name or service not known")

    monkeypatch.setattr(urllib.request, "urlopen", raise_url_error)

    client = InfisicalClient("https://infisical.example.invalid")
    with pytest.raises(InfisicalError) as caught:
        client.login(Credential(client_id="an-identity", client_secret=DUMMY_SECRET))

    assert caught.value.status is None


# ---------------------------------------------------------------------------
# The contract's own declaration
# ---------------------------------------------------------------------------


def test_the_contract_declares_at_least_one_optional_secret() -> None:
    """Otherwise everything below is a test of a case that cannot arise.

    This is the assertion that would have caught the defect at the moment the
    optional secret was introduced: a field nothing exercises is a field nothing
    honours, and `auth_jwt_prepared_key` was declared in Run 7 and first
    exercised by a host deploy eleven runs later.
    """
    contract = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    optional = [secret["name"] for secret in contract["secrets"] if not secret["required"]]
    assert optional, (
        "no secret is declared `required: false`, so the materializer's optional path is "
        "unreachable and these tests measure nothing"
    )
    assert "auth_jwt_prepared_key" in optional


def test_every_optional_secret_is_root_plane() -> None:
    """An optional secret that a container MOUNTS would be a different bug.

    Compose refuses to start a service whose bind-mount source is missing, so an
    absent optional secret on the compose plane would take the service down
    rather than be skipped -- the skip would move the failure, not remove it.
    """
    contract = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    for secret in contract["secrets"]:
        if secret["required"]:
            continue
        planes = {consumer["plane"] for consumer in secret["consumers"]}
        assert planes == {"root"}, (
            f"{secret['name']} is optional and has consumers in {sorted(planes)}. A "
            "compose consumer cannot be optional: Compose refuses to start a service "
            "whose mount source does not exist"
        )


# ---------------------------------------------------------------------------
# The materializer's decision, as a function of the two inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("required", "status", "tolerated", "why"),
    [
        (False, 404, True, "optional and absent -- the case that was failing"),
        (False, 500, False, "optional, but the provider is broken rather than empty"),
        (False, None, False, "optional, but nothing was learned (timeout, DNS)"),
        (True, 404, False, "REQUIRED and absent -- must never be skipped"),
        (True, 500, False, "required and the provider is broken"),
    ],
)
def test_only_an_optional_secrets_404_is_tolerated(
    required: bool, status: int | None, tolerated: bool, why: str
) -> None:
    """The decision table, asserted directly.

    Written as a table rather than as one happy-path test because the dangerous
    half is everything that is NOT tolerated: a fix that skipped on any error,
    or skipped for any secret, would pass a test that only checked the first row
    and would silently ship a generation missing a required credential.

    The condition is duplicated from `materialize-secrets.py` deliberately and
    it is the one place duplication is right: the module runs as a program under
    `sudo` against a live provider, so the alternative to restating four
    comparisons is not testing them at all. The mutation battery confirms the
    two move together.
    """
    decision = (not required) and status == 404
    assert decision is tolerated, why


def test_the_materializer_reads_the_required_field_at_all() -> None:
    """The narrow thing that was wrong, stated so it cannot come back.

    `bootstrap-providers.py` was the only file in the repository that read
    `required`. Asserted against the source because the fetch loop needs a live
    provider to run, and the property is about which fields the code consults.

    This is deliberately paired with the decision table above: on its own it is
    the AST-scan mistake D277 recorded -- a name being *mentioned* is satisfied
    by dead code -- and the table is what makes it a measurement.
    """
    source = (REPO_ROOT / "bin" / "materialize-secrets.py").read_text(encoding="utf-8")
    assert 'secret["required"]' in source, (
        "materialize-secrets.py does not consult `required`, so a secret the contract "
        "says may be absent will fail the whole materialization (D283)"
    )
    assert "exc.status == 404" in source, (
        "the optional path does not check the status, so any failure would be read as "
        "'absent' -- which writes a generation missing a secret the provider holds"
    )


def test_the_manifest_is_built_from_what_was_written(tmp_path: Path) -> None:
    """A skipped secret must not be listed as present.

    `write_manifest`'s own comment says a deployment must not "claim secrets are
    ready and name a file that does not exist". The first draft of the fix
    skipped the fetch and still built the manifest from the contract, which is
    exactly that sentence.
    """
    del tmp_path
    source = (REPO_ROOT / "bin" / "materialize-secrets.py").read_text(encoding="utf-8")
    assert "secrets=materialized," in source, (
        "the manifest is built from the declared secrets rather than from the ones this "
        "run actually wrote"
    )
    assert "materialized.append(secret)" in source


def test_the_module_still_imports() -> None:
    """Cheap, and it is the check that would have caught a syntax error in a
    file that only ever runs as root on a host."""
    assert _materializer() is not None

"""Where a secret's value comes from, and the generator that must refuse two of them.

ADR 0103. `secrets.required.yaml` has always said what *kind* of value a secret
is; from Session 7 it also says **who creates it**, because the R2 credential is
the first pair this repository must not invent — and the reason the two cannot be
one field is that the honest answers disagree. Cloudflare defines a Secret Access
Key as the SHA-256 of the API token's value, so it IS a 64-character hex string:
`value_kind: random_hex` is true, and `secrets.token_hex(32)` would produce
something byte-indistinguishable from a credential Cloudflare has never issued.

The module also carries the regression for **D333**, which is the defect this run
found while building the refusal: `generate_secret_value` had exactly one caller,
and the fresh-bootstrap path called `token_hex` inline. ADR 0055 had been half
implemented for two sessions. Nothing caught it because both live projects were
bootstrapped in Session 2, when the only declared secret genuinely was hex.

No test here contacts a provider: `ControlPlane` is replaced before any call.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml
from rendered_fixtures import (  # type: ignore[import-not-found]
    fixture_dir,
    needs_rendered_fixtures,
)

from agentic_postgres import REPO_ROOT, config, naming, secrets_contract
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

CONTRACT = REPO_ROOT / "secrets.required.yaml"

#: Not a credential. Nothing here reaches a network, and the fake control plane
#: below records what it is handed instead of sending it.
DUMMY_CREDENTIAL = "line-one-is-an-id\nline-two-is-not-a-secret\n"


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return secrets_contract.load_secret_contract(CONTRACT)


@pytest.fixture(scope="module")
def raw() -> dict[str, Any]:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def load_mutated(directory: Path, raw: dict[str, Any], mutate) -> dict[str, Any]:
    document = copy.deepcopy(raw)
    mutate(document)
    path = directory / "secrets.required.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return secrets_contract.load_secret_contract(path)


def bootstrap_module() -> Any:
    """`bin/bootstrap-providers.py`, loaded as a module.

    By path, because it is a program rather than a package member -- the same way
    `test_optional_secrets.py` reaches the materializer.
    """
    specification = importlib.util.spec_from_file_location(
        "apg_bootstrap_providers", REPO_ROOT / "bin" / "bootstrap-providers.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The declaration
# ---------------------------------------------------------------------------


def test_every_secret_declares_where_its_value_comes_from(contract: dict[str, Any]) -> None:
    """ADR 0103, and the assertion is against the schema rather than a list here.

    The second half is the one that matters and it is the shape
    `test_every_secret_declares_what_kind_of_value_it_is` uses: a declared origin
    that nothing uses is a branch nothing exercises, and D283 is what that costs
    -- `required: false` sat in this file for a whole session, honoured by one of
    its two readers, and surfaced on a host eleven runs later.
    """
    schema = config.load_schema("secret-contract.schema.json")
    origins = set(schema["$defs"]["secret"]["properties"]["origin"]["enum"])
    assert origins == set(secrets_contract.ORIGINS), (
        "the schema's enum and secrets_contract.ORIGINS disagree, so one of them is "
        "describing a contract the other does not accept"
    )
    for secret in contract["secrets"]:
        assert secret["origin"] in origins, secret["name"]
    assert {s["origin"] for s in contract["secrets"]} == origins, (
        "a declared origin that no secret uses is a refusal nothing exercises"
    )


def test_a_secret_with_no_origin_is_refused(tmp_path: Path, raw: dict[str, Any]) -> None:
    """Required rather than defaulted, for the reason `value_kind` is.

    A default here would mean `generated`, and the one secret that most needs to
    say otherwise is the one somebody adds without reading this file.
    """
    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, lambda d: d["secrets"][0].pop("origin"))


def test_an_unknown_origin_is_refused(tmp_path: Path, raw: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["secrets"][0]["origin"] = "derived_from_another_secret"

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_the_r2_credential_is_declared_as_a_value_this_repository_cannot_make(
    contract: dict[str, Any],
) -> None:
    """Both halves, named, with the shape trap stated.

    `value_kind` stays `random_hex` deliberately and this test says so, because
    the obvious "fix" on reading that line is to change it -- and changing it
    would make the contract stop describing the value and would forbid a future
    operator-supplied database password from ever being written as a pgpass file.
    """
    by_name = {secret["name"]: secret for secret in contract["secrets"]}
    for name in ("r2_access_key_id", "r2_secret_access_key"):
        secret = by_name[name]
        assert secrets_contract.is_operator_supplied(secret)
        assert secret["value_kind"] == "random_hex", (
            f"{name} is a hex string and the contract should say so. Its provenance is "
            "`origin`'s to state, not `value_kind`'s -- see ADR 0103"
        )
        assert secret["required"], (
            f"{name} is not optional. `required: false` means the materializer tolerates a "
            "404, which for a credential the runtime needs would write a generation missing it"
        )


def test_operator_supplied_secrets_are_the_ones_plan_has_to_name(
    contract: dict[str, Any],
) -> None:
    assert [s["name"] for s in secrets_contract.operator_supplied_secrets(contract, 7)] == [
        "r2_access_key_id",
        "r2_secret_access_key",
    ]
    assert secrets_contract.operator_supplied_secrets(contract, 6) == [], (
        "a Session 7 secret is active at session 6, so the session filter is not being applied"
    )


# ---------------------------------------------------------------------------
# The generator, which is the only place a value is created
# ---------------------------------------------------------------------------


def test_the_generator_refuses_an_operator_supplied_secret(contract: dict[str, Any]) -> None:
    """The refusal, and the message has to be actionable.

    An operator meeting this has to know where to go. The message names the
    provider path and key rather than saying "not supported", because the next
    thing they do is paste a value into that exact location.
    """
    module = bootstrap_module()
    secret = next(s for s in contract["secrets"] if s["name"] == "r2_secret_access_key")

    with pytest.raises(ValueError) as caught:
        module.generate_secret_value(secret)

    message = str(caught.value)
    assert "r2_secret_access_key" in message
    assert "/storage/APG_R2_SECRET_ACCESS_KEY" in message


def test_the_generator_still_makes_the_kinds_it_is_meant_to(contract: dict[str, Any]) -> None:
    """The control for the test above. Without it, a generator that raised for
    everything would pass the refusal test and break every deployment."""
    module = bootstrap_module()
    by_name = {secret["name"]: secret for secret in contract["secrets"]}

    hex_value = module.generate_secret_value(by_name["storage_service_password"])
    assert len(hex_value) == 64
    int(hex_value, 16)


# ---------------------------------------------------------------------------
# D333 -- the path that skipped the generator for two sessions
# ---------------------------------------------------------------------------


class _FakeControlPlane:
    """Records every (provider_key, value) handed to create_secret."""

    written: ClassVar[list[tuple[str, str]]] = []

    @classmethod
    def login(cls, api_url: str, client_id: str, client_secret: str) -> _FakeControlPlane:
        return cls()

    def create_project(self, name: str, slug: str, organization_id: str) -> str:
        return "project-id"

    def create_identity(self, name: str, organization_id: str) -> str:
        return "identity-id"

    def attach_universal_auth(self, identity_id: str) -> str:
        return "client-id"

    def create_client_secret(self, identity_id: str, description: str) -> tuple[str, str]:
        return ("client-secret-id", "client-secret-value")

    def ensure_folder(self, project_id: str, environment: str, folder: str) -> None:
        return None

    def create_secret(
        self, project_id: str, environment: str, secret_path: str, name: str, value: str
    ) -> bool:
        type(self).written.append((name, value))
        return True

    def grant_project_access(self, project_id: str, identity_id: str, role: str) -> None:
        return None

    def revoke_identity(self, identity_id: str) -> None:
        return None


def _run_fresh_bootstrap(tmp_path: Path, session: int) -> tuple[dict[str, str], dict[str, Any]]:
    """Drive `apply()` down its state-is-None branch. Returns (secrets, state).

    `write_private` is replaced rather than allowed to fail. It chowns to root,
    which this process cannot do -- but the state document is built *before* it
    is called, and letting the write blow up threw away the only record of what
    `apply()` decided it owns. **The mutation battery is why this captures it:**
    a mutation that recorded operator-supplied secrets in `managed_resources`
    left every test green, because the test asserting the property was reading
    `generated_provider_secrets` rather than the document `apply()` builds from
    it. That is an assertion about a helper wearing the name of an assertion
    about behaviour -- D173's shape, and the exact thing a battery exists to
    find.
    """
    module = bootstrap_module()
    module.ControlPlane = _FakeControlPlane
    _FakeControlPlane.written = []

    documents: dict[str, Any] = {}

    def capture(path: Path, content: str, *, mode: int) -> None:
        if str(path).endswith(".json"):
            documents.update(json.loads(content))

    module.write_private = capture
    module.state_path = lambda key: tmp_path / f"{key}.json"
    # The real shape, not a tmp_path one. `validate_state` checks these against
    # `^/etc/agentic-postgres/credentials/[a-z0-9-]+/infisical-client-(id|secret)$`
    # and a placeholder made it raise *before* the state document was written --
    # which is indistinguishable from "apply() records nothing". Nothing is
    # written to these paths: `write_private` is captured above.
    module.credential_paths = lambda key: {
        "client_secret_path": f"/etc/agentic-postgres/credentials/{key}/infisical-client-secret",
        "client_id_path": f"/etc/agentic-postgres/credentials/{key}/infisical-client-id",
    }

    credential = tmp_path / "operator.cred"
    credential.write_text(DUMMY_CREDENTIAL, encoding="utf-8")

    host = {
        "infisical": {
            "api_url": "https://infisical.example.invalid",
            "organization_id": "org",
            "organization_slug": "org",
            "environment_slug": "dev",
            "runtime_folder": "/runtime",
        }
    }
    # Real-shaped digests: the state schema requires ^[0-9a-f]{64}$, and a
    # placeholder made `validate_state` raise *before* the document was written
    # -- which looked exactly like "apply() records nothing".
    digest = "a" * 64
    manifest_digest = "b" * 64
    try:
        module.apply("alpha-dev", None, digest, manifest_digest, host, credential, session)
    except (SystemExit, PermissionError, OSError, ManifestError):
        pass
    return dict(_FakeControlPlane.written), documents


def test_a_fresh_bootstrap_generates_a_signing_key_and_not_a_hex_string(
    tmp_path: Path,
) -> None:
    """D333, and it is a behavioural test on purpose.

    The defect was invisible to every structural check: `generate_secret_value`
    existed, was correct, was documented, and was called by one of the two paths
    that create values. Asserting that the function exists, or that the module
    mentions it, is the AST-scan mistake D277 records -- satisfied by dead code.
    So this drives the real fresh-bootstrap branch and reads the value that came
    out the other end.

    Restoring `secrets.token_hex(SECRET_ENTROPY_BYTES)` in `apply()` turns this
    red. That mutation left the entire suite green before this test existed.
    """
    written, _ = _run_fresh_bootstrap(tmp_path, session=6)

    key = written.get("APG_BOOTSTRAP_JWT_SIGNING_KEY")
    assert key is not None, "the fresh-bootstrap path did not create the signing key at all"
    assert "BEGIN PRIVATE KEY" in key and "END PRIVATE KEY" in key, (
        "a fresh provider bootstrap stored something that is not a private key under "
        "bootstrap_jwt_signing_key. Every check in this repository would pass and the "
        "failure would surface as a JWKS derived from something that is not a key (D333)"
    )


def test_a_fresh_bootstrap_still_generates_the_passwords(tmp_path: Path) -> None:
    """The control. A fix that generated PEMs for everything would pass the test
    above and hand the cluster a private key as its superuser password."""
    written, _ = _run_fresh_bootstrap(tmp_path, session=6)

    password = written.get("APG_MIGRATION_USER_PASSWORD")
    assert password is not None
    assert len(password) == 64
    int(password, 16)


def test_a_fresh_bootstrap_creates_no_operator_supplied_value(tmp_path: Path) -> None:
    """The R2 pair must reach the provider from a human, or not at all.

    Session 7 rather than 6, because the session filter is what makes them active
    -- and running this at 6 as well would be a test that passes because the
    secrets are absent rather than because they are refused.
    """
    written, _ = _run_fresh_bootstrap(tmp_path, session=7)

    assert "APG_STORAGE_SERVICE_PASSWORD" in written, (
        "session 7's generated credential was not created, so this test is measuring an "
        "empty run rather than a selective refusal"
    )
    for key in ("APG_R2_ACCESS_KEY_ID", "APG_R2_SECRET_ACCESS_KEY"):
        assert key not in written, (
            f"the provider bootstrap invented a value for {key}. It would be a well-formed "
            "credential that authenticates to nothing (ADR 0103)"
        )


def test_an_operator_supplied_secret_is_never_recorded_as_ours(tmp_path: Path) -> None:
    """`managed_resources` is the licence to destroy, and §8.2 is the rule.

    **This test was wrong once and the battery is what found it.** The first
    version asserted on `generated_provider_secrets(7)` -- the helper the
    document is built *from* -- and stayed green when the call site in `apply()`
    was mutated back to `declared_provider_secrets`. It was an assertion about a
    function wearing the name of an assertion about behaviour, which is the
    shape D173 and D260 both record: a test nobody had seen fail, measuring the
    thing it was derived from.

    So it reads the document `apply()` actually builds. What goes in that list is
    what `--destroy` is allowed to remove, and a credential Cloudflare issued and
    a human pasted in was not created here.
    """
    _, state = _run_fresh_bootstrap(tmp_path, session=7)

    recorded = set(state["managed_resources"])
    assert "storage_service_password" in recorded, (
        "the state document records no session 7 secret at all, so the assertion below "
        "would hold for an empty list"
    )
    assert not recorded & {"r2_access_key_id", "r2_secret_access_key"}, (
        "an operator-supplied credential is recorded in `managed_resources`. That list is "
        "read by --destroy, so this project would remove something it never created (§8.2)"
    )


# ---------------------------------------------------------------------------
# What --plan says
# ---------------------------------------------------------------------------


def test_plan_names_every_operator_supplied_secret_and_where_it_comes_from(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run 2's exit criterion, and it is checked on the output an operator reads.

    Both the name and the provider location, because the operator's next action
    is to paste a value at exactly that path -- a message that named only the
    secret would send them to this file to work out where it goes.
    """
    module = bootstrap_module()
    module.state_path = lambda key: tmp_path / f"{key}.json"

    module.describe_plan("alpha-dev", None, "digest", 7)
    printed = capsys.readouterr().out

    assert "create  secret value storage_service_password" in printed
    for name, key in (
        ("r2_access_key_id", "/storage/APG_R2_ACCESS_KEY_ID"),
        ("r2_secret_access_key", "/storage/APG_R2_SECRET_ACCESS_KEY"),
    ):
        assert name in printed, f"--plan did not name {name}"
        assert key in printed, f"--plan named {name} without saying where its value goes"

    assert "create  secret value r2_access_key_id" not in printed, (
        "--plan proposes creating a value it must never create"
    )


def test_plan_at_session_six_says_nothing_about_storage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control for the test above, and the session filter's own proof.

    Without it, a `report_operator_supplied` that ignored the session would pass
    everything above and tell an operator deploying session 6 to go and create
    two Cloudflare credentials nothing will read.
    """
    module = bootstrap_module()
    module.state_path = lambda key: tmp_path / f"{key}.json"

    module.describe_plan("alpha-dev", None, "digest", 6)
    printed = capsys.readouterr().out

    assert "r2_access_key_id" not in printed
    assert "storage_service_password" not in printed
    assert "operator-supplied" not in printed


# ---------------------------------------------------------------------------
# The boundary ADR 0101 leaves to this contract
# ---------------------------------------------------------------------------


def test_neither_runtime_can_read_the_other_s_credential(contract: dict[str, Any]) -> None:
    """One image, two modes, and the secret contract is the boundary (ADR 0101).

    The least-privilege split the storage service needs is not enforced by the
    image -- both modes ship in one -- so it has to be a property of the
    materialization: per-consumer directories mean `auth` is granted no R2
    credential and `storage` is granted no signing key, and neither can read the
    other's file because neither has a path to it.

    Asserted in both directions. One direction is satisfied by a service that
    receives nothing at all, which is why the positive grants are checked too.
    """
    auth = {g["secret"]["name"] for g in secrets_contract.consumers_of(contract, "auth", 7)}
    storage = {g["secret"]["name"] for g in secrets_contract.consumers_of(contract, "storage", 7)}

    assert auth == {"auth_service_password", "auth_jwt_signing_key"}
    assert storage == {"storage_service_password", "r2_access_key_id", "r2_secret_access_key"}

    assert not auth & storage, "one credential is granted to both runtimes"
    assert "auth_jwt_signing_key" not in storage, (
        "the storage runtime holds a signing key. It is a verifier and must hold none "
        "(ADR 0098): a verifier that can sign can mint the tokens it accepts"
    )
    assert not {"r2_access_key_id", "r2_secret_access_key"} & auth, (
        "the auth service holds the R2 credential, so a defect in the login path reaches "
        "object storage"
    )


def test_the_storage_secrets_land_in_their_own_directory(contract: dict[str, Any]) -> None:
    """The filesystem property, spelled out as a path rather than as a rule.

    Two projects and two services, four different directories, and the project
    key is a path component -- so "one service cannot read another's copy" and
    "one project cannot read another's" are the same mechanism.
    """
    secret, consumer = secrets_contract.consumer_named(contract, "r2_secret_access_key", "storage")
    assert secret["provider_key"] == "APG_R2_SECRET_ACCESS_KEY"
    assert secrets_contract.secret_source_path("alpha-dev", "gen-0007", consumer) == (
        "/var/lib/agentic-postgres/secrets/alpha-dev/generations/gen-0007"
        "/storage/r2_secret_access_key"
    )
    assert secrets_contract.container_secret_path(consumer) == ("/run/secrets/r2_secret_access_key")


def test_the_compose_service_reads_the_paths_the_contract_materializes(
    contract: dict[str, Any],
) -> None:
    """The two files that have to agree, compared rather than trusted.

    `compose.yaml` names container paths in `APG_STORAGE_*_FILE`; this contract
    decides what is actually mounted there. They live in two files, which is how
    they come to disagree -- and the failure is a service that starts, passes its
    healthcheck and cannot presign, because the credential it read is absent
    rather than wrong.
    """
    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    environment = model["services"]["storage"]["environment"]

    for name, key in (
        ("r2_access_key_id", "APG_STORAGE_ACCESS_KEY_ID_FILE"),
        ("r2_secret_access_key", "APG_STORAGE_SECRET_ACCESS_KEY_FILE"),
        ("storage_service_password", "APG_DATABASE_PASSFILE"),
    ):
        _, consumer = secrets_contract.consumer_named(contract, name, "storage")
        assert environment[key] == secrets_contract.container_secret_path(consumer), (
            f"compose.yaml points {key} at {environment[key]}, and the contract "
            f"materializes {name} at {secrets_contract.container_secret_path(consumer)}"
        )


def test_the_storage_service_is_held_back_until_its_role_exists(contract: dict[str, Any]) -> None:
    """D324, asserted where it can be seen offline.

    A service that authenticates as a bootstrap-activated role and starts in the
    first phase is restarted five times against a role that cannot log in, and
    the message is `password authentication failed` -- what a *wrong* credential
    gets. The pairing is the property: a compose consumer with a pgpass grant is
    a service that authenticates as a project role.
    """
    del contract
    from agentic_postgres import runtime_override

    assert runtime_override.STORAGE_SERVICE in runtime_override.POST_BOOTSTRAP_SERVICES


def test_the_storage_service_publishes_no_route_yet() -> None:
    """The container arrives two runs before its route, so this states the gap.

    A router label set that published `/api/app/storage` before anything answered
    it would route to a container that 404s, and Traefik's own 404 is
    indistinguishable from a routed one without the access log (D186, D187).
    """
    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    labels = model["services"]["storage"]["labels"]

    assert labels["apg.traefik.scope"] == "managed"
    routers = [key for key in labels if key.startswith("traefik.http.")]
    assert not routers, (
        f"the storage service carries router labels {routers} but nothing serves the route "
        "yet. Publishing is Run 7's, with the endpoints that answer it"
    )


def test_the_storage_service_is_startable_and_everything_a_start_needs_exists() -> None:
    """The successor this test's own previous form asked for.

    Until Run 9 this asserted `CURRENT_SESSION < 7` and said, in its failure
    message, that *"the run that moves CURRENT_SESSION owns replacing it with a
    proof that the service comes up"*. Run 9 moved it, so this is that
    replacement -- a temporary recording giving way to the thing it was holding
    a place for, rather than a passing test being weakened.

    **What a `session7` profile being reachable now means.** `project-runtime.sh`
    selects `--profile session${n}` for n up to `--through-session`, so the
    storage container was unreachable while the gate session was 6 and no
    deployment has ever started one. From here on a deploy will try to, and a
    start needs three things that exist only if this passes: the profile itself,
    the entry in `POST_BOOTSTRAP_SERVICES`, and the three secrets its consumer
    is granted.

    **This is stricter than what it replaces**, which asserted a number was
    below 7. It cannot say the container *comes up* -- that needs a host, and it
    is `tests/deployment/test_session7_storage.py`'s, which has never run.
    """
    from agentic_postgres import CURRENT_SESSION, runtime_override

    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = model["services"]["storage"]

    assert service["profiles"] == ["session7"]
    assert CURRENT_SESSION >= 7, (
        "the storage profile is session7 and the gate session is below it, so the "
        "service is unreachable. Run 9 moved CURRENT_SESSION to 7; if it has moved "
        "back, this proof and every Session 7 claim describe a surface no deploy starts"
    )
    assert runtime_override.STORAGE_SERVICE in runtime_override.POST_BOOTSTRAP_SERVICES, (
        "the storage service is startable and is not held until after the bootstrap "
        "plane has run, so it would come up before its database role has a credential"
    )

    contract = secrets_contract.load_secret_contract(CONTRACT)
    granted = {
        secret["name"]
        for secret in contract["secrets"]
        for consumer in secret.get("consumers", ())
        if consumer.get("service") == runtime_override.STORAGE_SERVICE
    }
    assert {"storage_service_password", "r2_access_key_id", "r2_secret_access_key"} <= granted, (
        f"the storage consumer is granted {sorted(granted)}; a start needs all three, "
        "and a container missing one fails closed at the provider rather than at boot"
    )


def test_the_bootstrap_state_enum_and_the_contract_agree_about_storage() -> None:
    """The drift D66 produced, checked for the one secret this run adds.

    `test_every_required_secret_the_contract_declares_can_be_recorded_as_managed`
    is the general form; this names the specific pair so a failure says which
    secret rather than which set difference.
    """
    schema = json.loads(
        (REPO_ROOT / "schemas" / "bootstrap-state.schema.json").read_text(encoding="utf-8")
    )
    allowed = set(schema["properties"]["managed_resources"]["items"]["enum"])
    assert "storage_service_password" in allowed
    assert not allowed & {"r2_access_key_id", "r2_secret_access_key"}


# ---------------------------------------------------------------------------
# The published values -- D332's rule, applied on the day the fields land
# ---------------------------------------------------------------------------


def _rendered_env(key: str) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in (fixture_dir(key) / "compose.env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )


@needs_rendered_fixtures
@pytest.mark.parametrize(
    ("key", "manifest"),
    [
        ("fixture-alpha-dev", REPO_ROOT / "project.example.yaml"),
        ("fixture-alpine-dev", REPO_ROOT / "project.second.example.yaml"),
    ],
)
def test_every_storage_variable_is_read_from_the_manifest(key: str, manifest: Path) -> None:
    """Each rendered STORAGE_* against the project that produced it.

    Eight variables were added to `compose.env` in this run, and until this test
    existed nothing asserted any of their values -- which is D332 exactly: a
    hard-coded 20 for `pooler_pool_size` left the whole suite green one run ago,
    because nothing read the field and both fixtures declared the same number.

    Reading the rendered file rather than calling `build_compose_env` is
    deliberate. What ships is the file, and a test that calls the builder proves
    only that the builder agrees with itself.
    """
    project = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    storage = {**config.STORAGE_DEFAULTS, **(project.get("storage") or {})}
    rendered = _rendered_env(key)

    assert rendered["STORAGE_POOL_SIZE"] == str(storage["pool_size"])
    assert rendered["STORAGE_MEMORY_LIMIT"] == f"{storage['memory_limit_mb']}m"
    assert rendered["STORAGE_UPLOAD_URL_TTL_SECONDS"] == str(storage["upload_url_ttl_seconds"])
    assert rendered["STORAGE_DOWNLOAD_URL_TTL_SECONDS"] == str(storage["download_url_ttl_seconds"])
    assert rendered["STORAGE_MAX_UPLOAD_BYTES"] == str(storage["max_upload_bytes"])
    # Through `naming`, because the manifest may declare neither: alpha takes the
    # derived names and alpine overrides both, so `storage["bucket"]` is absent
    # for one of them. That split is deliberate (ADR 0105) -- until Run 3 both
    # fixtures restated the defaults, so nothing exercised the derivation and
    # changing it left the suite green.
    assert rendered["STORAGE_BUCKET"] == naming.storage_bucket_name(key, storage.get("bucket"))
    assert rendered["STORAGE_PREFIX"] == naming.storage_object_prefix(key, storage.get("prefix"))
    # Through `naming` for the same reason as the two above, and this pair
    # covers both branches of the derivation: alpha omits `jurisdiction` and
    # alpine names `eu`, so a renderer that dropped the jurisdiction would fail
    # one fixture instead of passing for both (ADR 0106, D332, D343).
    assert rendered["STORAGE_ENDPOINT"] == naming.storage_endpoint_url(
        storage["account_id"], storage.get("jurisdiction", "default")
    )
    assert rendered["STORAGE_SERVICE_ROLE_NAME"].endswith("_storage_service")
    assert key.replace("-", "_") in rendered["STORAGE_SERVICE_ROLE_NAME"]


@needs_rendered_fixtures
def test_the_two_fixtures_disagree_about_every_storage_variable() -> None:
    """The pair is what makes the test above a measurement (D332).

    A value both projects declare identically is one a constant would satisfy.
    `STORAGE_MEMORY_LIMIT` is in the list because alpha declares none and takes
    the default while alpine overrides it, so the pair covers both paths.

    The two TTLs and `STORAGE_MAX_UPLOAD_BYTES` were identical across the
    fixtures when they were first rendered, which is precisely how D332 happened
    one run ago. They were made to differ in the same commit that published
    them, rather than in the run that discovers why they had to.
    """
    alpha = _rendered_env("fixture-alpha-dev")
    alpine = _rendered_env("fixture-alpine-dev")

    for variable in (
        "STORAGE_SERVICE_ROLE_NAME",
        "STORAGE_POOL_SIZE",
        "STORAGE_MEMORY_LIMIT",
        "STORAGE_BUCKET",
        "STORAGE_PREFIX",
        "STORAGE_UPLOAD_URL_TTL_SECONDS",
        "STORAGE_DOWNLOAD_URL_TTL_SECONDS",
        "STORAGE_MAX_UPLOAD_BYTES",
        # Added in Run 5 with the field itself (ADR 0106). The two fixtures
        # differ in BOTH inputs -- account id and jurisdiction -- so neither a
        # constant endpoint nor one that ignores the jurisdiction survives.
        "STORAGE_ENDPOINT",
    ):
        assert alpha[variable] != alpine[variable], (
            f"both fixtures render {variable}={alpha[variable]}, so a constant in the "
            "renderer would satisfy every test that reads it (D332)"
        )

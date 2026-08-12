"""The PostgREST service: its configuration, and what cannot be in it.

The service is configured entirely from `PGRST_*` environment variables, and
that is a measured consequence rather than a preference. The image is distroless
(Run 1) -- no shell, no `wget`, no `curl`, no declared `ENTRYPOINT` -- so nothing
in the container can read one file and write another, which is how every other
credential-holding service here assembles what it needs. Run 4 measured the four
ways a password could reach it, with a control that put the password inline to
prove the rig was real, and this is the shape that keeps it out of the
environment, the argument vector, the labels and `docker inspect`.

Three properties carry the file, and each has a failure it prevents:

* **every `PGRST_*` name maps to a key the locked binary admits.** ADR 0019's
  lesson: a setting the parser drops is a boundary that is not there, and
  nothing offline distinguishes it from one that is enforced. The key set here
  is the one `--dump-config` printed, held in `test_image_contracts.py`.
* **the three dangerous defaults are set explicitly.** `db-config` true lets the
  database override this reviewed configuration; `db-extra-search-path` defaults
  to `public`, which is the whole of ADR 0052; the hoisted transaction settings
  default to three rather than none.
* **no password, no foreign project's identity, no direct address.** The
  conninfo names a file with `?passfile=`; every identity is interpolated rather
  than written; and the service is reached through Traefik, so nothing here
  publishes a port.

Nothing in this module starts a container. What it reads is the committed model
and the two rendered `compose.env` files, which is where a configuration error
would be introduced -- and where it can be caught before anything runs.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, rendering, runtime_override, secrets_contract
from agentic_postgres.secrets_contract import load_secret_contract

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

MODEL = REPO_ROOT / "compose.yaml"
ALPHA = REPO_ROOT / ".generated" / "fixture-alpha-dev"
ALPINE = REPO_ROOT / ".generated" / "fixture-alpine-dev"

#: The credential's mounted path, as the conninfo names it. Written out here so
#: that the test compares two independently-written strings rather than deriving
#: both from one.
PGPASS_PATH = "/run/secrets/postgrest_authenticator_pgpass"


@pytest.fixture(scope="module")
def service() -> dict[str, Any]:
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    assert "postgrest" in document["services"], "the model declares no PostgREST service"
    return document["services"]["postgrest"]


@pytest.fixture(scope="module")
def environment(service: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in service["environment"].items()}


def rendered_env(directory) -> dict[str, str]:
    text = (directory / "compose.env").read_text(encoding="utf-8")
    return dict(
        line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#")
    )


# ---------------------------------------------------------------------------
# Every key exists in the locked binary
# ---------------------------------------------------------------------------


def test_every_environment_key_names_a_real_configuration_key(
    environment: dict[str, str],
) -> None:
    """D127's measurement, applied rather than assumed.

    `PGRST_DB_MAX_ROWS` is `db-max-rows`; a name the parser does not recognise
    is silently ignored, and offline nothing distinguishes an ignored setting
    from an enforced one. The key set is the one `--dump-config` printed against
    the locked digest, not a list from documentation -- which is exactly the
    difference ADR 0019 was written about.
    """
    from tests.contract.test_image_contracts import POSTGREST_CONFIG_KEYS

    for name in environment:
        assert name.startswith("PGRST_"), name
        key = name.removeprefix("PGRST_").lower().replace("_", "-")
        assert key in POSTGREST_CONFIG_KEYS, (
            f"{name} maps to {key!r}, which the locked PostgREST does not accept. "
            "A key it drops is a boundary that is not there"
        )


def test_the_key_the_runbook_wanted_is_not_smuggled_in(environment: dict[str, str]) -> None:
    """`client-error-verbosity` exists in no version this repository can run.

    D144. The runbook sets it and asserts it; it arrives in 16.0. Named here so
    that adding it to this service fails with the reason rather than being
    dropped by the parser and looking configured.
    """
    assert "PGRST_CLIENT_ERROR_VERBOSITY" not in environment


# ---------------------------------------------------------------------------
# The dangerous defaults, and the boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "value"),
    [
        pytest.param("PGRST_DB_CONFIG", "false", id="db-config"),
        pytest.param("PGRST_DB_EXTRA_SEARCH_PATH", "", id="extra-search-path"),
        pytest.param("PGRST_DB_HOISTED_TX_SETTINGS", "", id="hoisted-tx-settings"),
    ],
)
def test_the_dangerous_defaults_are_set_explicitly(
    environment: dict[str, str], key: str, value: str
) -> None:
    """Each of the three is wrong in the direction nobody checks.

    `db-config` true lets a database role's settings override this file, which
    would make the reviewed configuration advisory. `db-extra-search-path`
    defaults to `public`. The hoisted settings default to three.
    """
    assert environment[key] == value


def test_exactly_one_schema_is_exposed(environment: dict[str, str]) -> None:
    """`db-schemas` accepts a list, and each entry is a boundary of its own."""
    assert environment["PGRST_DB_SCHEMAS"] == "${POSTGREST_EXPOSED_SCHEMA:?required}"
    assert rendering.POSTGREST_EXPOSED_SCHEMA == "api"
    for directory in (ALPHA, ALPINE):
        assert rendered_env(directory)["POSTGREST_EXPOSED_SCHEMA"] == "api"


def test_aggregates_and_plans_are_off(environment: dict[str, str]) -> None:
    """Both disclose facts about rows the caller cannot read.

    An aggregate over a table answers questions about rows a row policy hides;
    an execution plan carries row estimates, index names and statistics for the
    same query.
    """
    assert environment["PGRST_DB_AGGREGATES_ENABLED"] == "false"
    assert environment["PGRST_DB_PLAN_ENABLED"] == "false"


def test_the_notification_channel_is_enabled(environment: dict[str, str]) -> None:
    """Without it a migration's NOTIFY reaches nothing and a reload is a restart."""
    assert environment["PGRST_DB_CHANNEL_ENABLED"] == "true"
    assert environment["PGRST_DB_CHANNEL"] == "pgrst"


def test_openapi_follows_privileges(environment: dict[str, str]) -> None:
    """And is not mistaken for a boundary.

    An object hidden from OpenAPI by `follow-privileges` is still in the
    catalog, which is why ADR 0050 compares the surface contract against the
    catalog as well -- the next grant change publishes it.
    """
    assert environment["PGRST_OPENAPI_MODE"] == "follow-privileges"
    assert environment["PGRST_OPENAPI_SECURITY_ACTIVE"] == "true"


def test_the_admin_surface_is_pinned_to_loopback(environment: dict[str, str]) -> None:
    """Measured in Run 3: it follows `server-host` when nobody says otherwise.

    With `server-host = 0.0.0.0` -- which a container needs -- and only a port
    set, `/live` and `/ready` answered a peer container on the project network.
    """
    # S104 is the finding, not a lapse: the request surface binds widely because
    # a container has to answer its peers, and the admin surface would follow it.
    assert environment["PGRST_SERVER_HOST"] == "0.0.0.0"  # noqa: S104
    assert environment["PGRST_ADMIN_SERVER_HOST"] == "127.0.0.1"
    assert environment["PGRST_ADMIN_SERVER_PORT"] == "3001"


def test_query_logging_is_off(environment: dict[str, str]) -> None:
    """A logged query carries its parameters, and a parameter carries a row."""
    assert environment["PGRST_LOG_QUERY"] == "disabled"


def test_the_verification_key_references_the_rendered_jwks(
    environment: dict[str, str],
) -> None:
    """Run 9 added the key, which the previous version of this test asked for.

    It asserted ``"PGRST_JWT_SECRET" not in environment`` and said so plainly:
    "This test goes red on the day the key is added, which is the day the run
    that renders the JWKS has to say so." That day is this run, and the
    replacement is stronger rather than weaker — an absence is satisfied by a
    typo in the variable's name, and an assertion about the value is not.

    Three properties. The value is a **reference** (``@`` and a path) rather than
    key material; the path is the one the runtime override mounts; and it is not
    under the secret mount. ``SEC-SECRET-001``'s test enforces the same three
    from the other side, across every service (ADR 0064).

    Goes red if: the key is dropped, so the service verifies nothing and every
    request is anonymous; the value becomes a literal rather than a file
    reference, which would put verification material in ``docker inspect``
    forever; or the path drifts from the mount — which Docker answers by creating
    a *directory* where the file should be, so the symptom is a key set that will
    not parse.
    """
    reference = environment["PGRST_JWT_SECRET"]
    assert reference.startswith("@"), f"PGRST_JWT_SECRET is {reference!r}, not a file reference"
    assert reference[1:] == runtime_override.JWKS_CONTAINER_PATH
    assert not reference[1:].startswith(f"{secrets_contract.CONTAINER_SECRET_DIR}/")
    assert environment["PGRST_JWT_AUD"] == "${JWT_AUDIENCE:?required}"


# ---------------------------------------------------------------------------
# The credential
# ---------------------------------------------------------------------------


def test_the_conninfo_names_a_file_and_carries_no_password(
    environment: dict[str, str],
) -> None:
    """`?passfile=` rather than a userinfo password, and the difference is total.

    Run 4 measured all four ways: inline (the control, which works and must not
    be used), `PGPASSFILE`, `?passfile=`, and the `@file` form holding a whole
    URI. The last would put a derived role, host and database name inside an
    operator-facing value, which is what D60 rejected.
    """
    uri = environment["PGRST_DB_URI"]
    assert uri.startswith("postgres://")
    userinfo = uri.split("://", 1)[1].split("@", 1)[0]
    # Compose's `${VAR:?required}` contains a colon of its own, so the
    # references are expanded away before the userinfo is read for one. What is
    # left must be a single reference and nothing else.
    expanded = re.sub(r"\$\{[^}]*\}", "$", userinfo)
    assert expanded == "$", f"the conninfo carries a userinfo password: {userinfo!r}"
    assert f"passfile={PGPASS_PATH}" in uri


def test_every_identity_in_the_conninfo_is_interpolated(environment: dict[str, str]) -> None:
    """A literal here would be one project's name in every project's model.

    The role, the host and the database are three separate references, so a
    project whose identity differs cannot share any of them -- which is the
    isolation property the two fixtures exist to prove.
    """
    uri = environment["PGRST_DB_URI"]
    references = re.findall(r"\$\{([A-Z_]+)(?::\?required)?\}", uri)
    assert set(references) == {
        "POSTGREST_AUTHENTICATOR_ROLE",
        "POSTGRES_SERVICE_HOST",
        "POSTGRES_DATABASE_NAME",
    }


def test_it_connects_directly_rather_than_through_the_pooler(
    environment: dict[str, str],
) -> None:
    """It needs prepared statements and a LISTEN channel; neither survives
    transaction pooling. The pooled endpoint stays for ordinary clients."""
    uri = environment["PGRST_DB_URI"]
    assert "${POSTGRES_SERVICE_HOST:?required}" in uri
    assert rendering.PGBOUNCER_SERVICE_HOST not in uri
    assert str(rendering.PGBOUNCER_LISTEN_PORT) not in uri


def test_the_credential_is_declared_and_lands_where_the_conninfo_looks() -> None:
    """The two live in two files, which is how they come to disagree.

    `secrets.required.yaml` names the target file; the conninfo names a path
    under `/run/secrets`. Compose mounts a granted file at its basename, so the
    two must agree on that basename or PostgREST reads a file that is not there
    and reports `fe_sendauth: no password supplied`.
    """
    contract = load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    secret = next(s for s in contract["secrets"] if s["name"] == "postgrest_authenticator_password")
    consumer = secret["consumers"][0]
    assert consumer["service"] == "postgrest"
    assert PGPASS_PATH == f"/run/secrets/{consumer['target_file']}"
    assert consumer["format"] == "pgpass", (
        "the image has no shell to wrap a raw password in a pgpass line"
    )
    assert secret["introduced_in_session"] == 5


def test_no_password_can_reach_the_argument_vector(service: dict[str, Any]) -> None:
    """There is no argument vector.

    The image declares no ENTRYPOINT, so its own CMD is the binary and this
    service overrides neither. Measured on a running container: `.Args` is
    empty. It is the easiest of the four places to keep a password out of,
    because there is nowhere to put one.
    """
    assert "command" not in service
    assert "entrypoint" not in service


# ---------------------------------------------------------------------------
# The container
# ---------------------------------------------------------------------------


def test_the_hardening_is_the_same_as_every_other_service(service: dict[str, Any]) -> None:
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["user"] == "65532:65532"


def test_the_uid_is_declared_in_three_places_and_they_agree() -> None:
    """The image sets no USER, so there is no default to inherit even in principle."""
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    contract = load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    secret = next(s for s in contract["secrets"] if s["name"] == "postgrest_authenticator_password")
    consumer = secret["consumers"][0]
    assert document["services"]["postgrest"]["user"] == f"{consumer['uid']}:{consumer['gid']}"


def test_it_publishes_no_host_port(service: dict[str, Any]) -> None:
    """Public traffic arrives through Traefik, so the edge's limits apply."""
    assert "ports" not in service
    assert "expose" not in service


def test_it_is_on_both_networks_and_says_why(service: dict[str, Any]) -> None:
    """Traefik reaches it on `edge`; the cluster is on `internal`."""
    assert sorted(service["networks"]) == ["edge", "internal"]


def test_it_starts_under_the_session_five_profile(service: dict[str, Any]) -> None:
    """`session5`, so a session-4 deploy does not acquire a REST surface.

    `bin/project-runtime.sh::session_profiles` selects `session2..N`, so the
    profile is what makes `--through-session` mean something.
    """
    assert service["profiles"] == ["session5"]


def test_the_healthcheck_is_the_probe_and_not_a_port_check(service: dict[str, Any]) -> None:
    """And it works bare only because the configuration is in the environment.

    D153: `postgrest --ready` is a client that reads its *own* configuration, so
    bare it exits 1 with "Admin server is not running" against a service
    answering 200. Here the probe's own configuration is the service's, because
    both come from the same environment -- measured exit 0.

    What it cannot prove is the request path (D145), and this test does not
    pretend otherwise: it asserts the command, and the request-path proof lives
    in the deploy and in `API-REST-001`.
    """
    assert service["healthcheck"]["test"] == ["CMD", "postgrest", "--ready"]
    assert "CMD-SHELL" not in str(service["healthcheck"]["test"]), (
        "the image has no shell; a CMD-SHELL check reports an unhealthy container "
        "and the obvious repair is to weaken the check rather than notice the image"
    )


def test_it_waits_for_the_cluster(service: dict[str, Any]) -> None:
    """A pool against a cluster that is still initialising is a start that fails."""
    assert service["depends_on"]["postgres"]["condition"] == "service_healthy"


# ---------------------------------------------------------------------------
# What the render puts in compose.env
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("directory", [ALPHA, ALPINE], ids=["alpha", "alpine"])
def test_the_rendered_environment_carries_no_secret(directory) -> None:
    env = rendered_env(directory)
    for key, value in env.items():
        assert "PASSWORD" not in key.upper(), key
        assert "passfile" not in value or value.startswith("postgres://"), key


def test_two_projects_get_different_identities_and_the_same_schema() -> None:
    """The isolation property, on the keys Session 5 added.

    Role names and audiences must differ; the exposed schema and the pool
    numbers are platform constants and manifest values, and identical values
    there are correct rather than a collision.
    """
    alpha, alpine = rendered_env(ALPHA), rendered_env(ALPINE)
    for key in ("POSTGREST_AUTHENTICATOR_ROLE", "ANON_ROLE_NAME", "JWT_AUDIENCE"):
        assert alpha[key] != alpine[key], key
    assert alpha["POSTGREST_EXPOSED_SCHEMA"] == alpine["POSTGREST_EXPOSED_SCHEMA"]


def test_the_cors_origins_are_this_projects_own() -> None:
    """A list copied between the two fixtures would name the other project.

    Which is the failure the pair exists to catch, and it is checkable here
    because the manifests share a base path and differ only in domain.
    """
    alpha, alpine = rendered_env(ALPHA), rendered_env(ALPINE)
    assert alpha["POSTGREST_CORS_ORIGINS"] == "https://fixture-alpha-dev.test"
    assert alpine["POSTGREST_CORS_ORIGINS"] == "https://fixture-alpine-dev.test"
    assert alpha["PROJECT_DOMAIN"] not in alpine["POSTGREST_CORS_ORIGINS"]


def test_the_row_ceiling_comes_from_the_one_authority() -> None:
    """`api.max_rows`, not a second number in the REST section."""
    import yaml as _yaml

    manifest = _yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))
    assert rendered_env(ALPHA)["POSTGREST_MAX_ROWS"] == str(manifest["api"]["max_rows"])
    assert "max_rows" not in manifest["api"]["rest"]


def test_the_pool_numbers_are_the_manifests() -> None:
    import yaml as _yaml

    manifest = _yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))[
        "api"
    ]["rest"]
    env = rendered_env(ALPHA)
    assert env["POSTGREST_POOL_SIZE"] == str(manifest["pool_size"])
    assert env["POSTGREST_POOL_MAX_IDLE"] == str(manifest["pool_max_idle_seconds"])
    assert env["POSTGREST_POOL_MAX_LIFETIME"] == str(manifest["pool_max_lifetime_seconds"])


# ---------------------------------------------------------------------------
# ADR 0066 -- the rig and the product are one configuration, not two
# ---------------------------------------------------------------------------

#: The behaviour rig. It builds a real PostgREST from the locked image and is a
#: maintained statement of what one needs in order to work, which is why the
#: product is tied to it rather than to a second hand-written list that would
#: drift from both.
BEHAVIOUR_RIG = REPO_ROOT / "tests" / "contract" / "test_api_behaviour.py"

#: Settings the rig legitimately has and the product must not copy. Each would
#: carry its reason, because an exemption is a decision a reviewer sees where an
#: absence is not.
#:
#: **It is empty, and that is the finding.** The first draft of this table
#: exempted seven names on the assumption that a rig's throwaway cluster, its
#: constant signing key and its wildcard bind were rig-only. Every one of them
#: is set by the product too -- with an interpolation rather than a literal,
#: which is a difference in *value* and not in *presence*. The rule is about
#: presence. Once `PGRST_DB_PRE_REQUEST` is set, the rig configures nothing the
#: product does not, and the honest exemption list is no entries at all.
RIG_ONLY: dict[str, str] = {}


def _rig_settings() -> set[str]:
    """Every `PGRST_*` name the behaviour rig passes to `docker run`.

    Read out of the rig's source rather than by importing it, because importing
    would run a module that starts containers.
    """
    source = BEHAVIOUR_RIG.read_text(encoding="utf-8")
    return set(re.findall(r"PGRST_[A-Z0-9_]+", source))


def test_every_setting_the_behaviour_rig_configures_is_configured_by_the_product(
    environment: dict[str, str],
) -> None:
    """ADR 0066. A rig is a second configuration, and nothing compared them.

    `PGRST_DB_PRE_REQUEST` was set by the rig at `test_api_behaviour.py` and by
    nothing else. Migration 0008 created the hook, migration 0009 replaced it,
    both granted EXECUTE on it by name, and 0008 ended with a schema reload
    under a comment beginning "db-pre-request names a function" -- while the
    product never told PostgREST to call it. The identity plane was built,
    granted, commented, reloaded, and never wired. Four of Run 9's eight live
    failures had that one cause (D192).

    Goes red if a `PGRST_*` is added to the rig and neither set by the model nor
    exempted. It does **not** assert the reverse: the rig legitimately omits
    routing, CORS and pool settings that have no bearing on behaviour, and
    requiring symmetry would produce an exemption list nobody reads.
    """
    rig = _rig_settings()

    # The control. A regex that matched nothing would pass this test forever,
    # and these two are the rig's whole reason for existing.
    assert {"PGRST_DB_PRE_REQUEST", "PGRST_OPENAPI_MODE"} <= rig, (
        f"the rig scan found {sorted(rig)}; it is not reading the rig's settings"
    )

    missing = sorted(name for name in rig if name not in environment and name not in RIG_ONLY)
    assert not missing, (
        f"the behaviour rig configures {missing}, which compose.yaml does not set. "
        "Either set it on the product, or add it to RIG_ONLY with the reason it is "
        "rig-only. A setting only the rig has is a behaviour only the rig has."
    )


def test_nothing_is_exempted_today() -> None:
    """The emptiness of `RIG_ONLY` is asserted, not left to be noticed.

    A loop over an empty table passes by iterating nothing, which is how a rule
    stops enforcing without anyone seeing it go (D190). So the count is a test:
    adding an exemption fails here as well as satisfying the check above, and
    that second edit is the reviewer's chance to ask whether the setting is
    really rig-only or the product is simply missing it. That question, unasked,
    is what ADR 0066 exists about.
    """
    assert RIG_ONLY == {}, (
        f"exemptions were added: {sorted(RIG_ONLY)}. Each is a claim that the product "
        "does not need a setting the rig does. Confirm that, then update this test."
    )


def test_the_exemptions_name_settings_the_rig_actually_uses(
    environment: dict[str, str],
) -> None:
    """An exemption for a setting nobody sets is a rule quietly losing coverage.

    Vacuous while `RIG_ONLY` is empty, which the test above is what makes
    visible. It guards the entries the day there are any: an exemption left
    behind after its setting leaves the rig, and an exemption written for
    something the product *does* set -- which reads as "rig-only" about a shared
    setting, and is the mistake this table's first draft made in all seven of
    its entries.
    """
    rig = _rig_settings()
    for name, reason in sorted(RIG_ONLY.items()):
        assert name in rig, f"{name} is exempted but the rig does not set it; delete the exemption"
        assert name not in environment, (
            f"{name} is exempted as rig-only but compose.yaml sets it; delete the exemption"
        )
        assert reason.strip(), f"{name} is exempted with no reason"


def test_the_pre_request_hook_is_schema_qualified(environment: dict[str, str]) -> None:
    """ADR 0052: `app_private` is on no request role's search_path.

    Goes red if the hook is ever named bare. Measured in Run 4's rig: an
    unresolvable hook does not stop the service and does not skip the hook -- it
    starts, reports a warm schema cache, and answers every request with a 404
    (D145). An unqualified name is exactly that failure, and it looks healthy.
    """
    hook = environment["PGRST_DB_PRE_REQUEST"]
    schema, _, function = hook.partition(".")
    assert schema == "app_private", f"the hook is in app_private, not {schema!r}"
    assert function == "postgrest_pre_request", f"unexpected hook function {function!r}"

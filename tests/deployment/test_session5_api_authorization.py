"""The REST surface cannot widen the authorization model.

SEC-ANON-001, SEC-PRIV-001, SEC-ROLE-001 and SEC-DOCS-001. Replaces four Session
5 placeholders in ``tests/security/test_future_security_boundaries.py``.

**Under ``tests/deployment/`` with the ``security`` marker**, which is D111's
shape one session on: the marker decides what runs and what the evidence
records, the directory decides which conftest is in scope, and the fixtures that
make these measurable -- minting a token, calling the route, reaching the
cluster -- are there. A second copy of the one piece of plumbing that handles a
credential is what D111 declined to grow.

**Every negative has a positive control in the same test** (§4.2). A PostgREST
that refuses every request passes every negative here completely, and that is
precisely what a misconfigured authenticator produces.

**Every test states what would have to break for it to go red**, because every
test here is deselected in an offline gate.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every statement below interpolates values that came from a deployed outputs
# document -- role names and a database name derived by `naming` and validated
# by the outputs schema -- plus fixed UUID constants declared in this file. None
# of it is operator input, and parameter binding is unavailable where an
# identifier, a role name or a `SET` target goes, which is the same reason
# `migrations.quote_identifier` exists. Suppressed per module rather than per
# line, as `tests/security/test_session3_authorization.py` does, because a wall
# of inline noqa comments is one nobody reads.
import json
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, secrets_contract
from agentic_postgres.secret_generation import SECRET_ROOT

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: The one private object a request role may reach (ADR 0052). Everything else
#: in `app_private` is proved unreachable by attempting it.
PRE_REQUEST_FUNCTION = "app_private.postgrest_pre_request"


@pytest.fixture(scope="module")
def roles(project_a: dict[str, Any]) -> dict[str, str]:
    return project_a["database"]["roles"]


# ---------------------------------------------------------------------------
# SEC-ANON-001 — the anonymous role reads nothing it was not granted
# ---------------------------------------------------------------------------


def test_the_anonymous_role_reads_nothing_it_was_not_granted(
    project_a: dict[str, Any],
    roles: dict[str, str],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    mint_token: Callable[..., str],
    request_subject: Callable[[str], str],
) -> None:
    """SEC-ANON-001, and an empty 200 is not accepted as a refusal.

    The manifest's ``anonymous_access`` is ``deny_data``, so an anonymous caller
    may reach the surface and must read no rows. That makes the interesting
    failure a *successful* response: a 200 carrying ``[]`` is what both a working
    boundary and a policy that denies everyone look like, and only the
    authenticated control tells them apart.

    So this test asserts three things in one place: the anonymous caller is
    refused or reads nothing, an authenticated caller reading the same resource
    gets rows, and the rows exist to be read.

    Goes red if: ``anon`` is granted SELECT on either view; the pre-request hook
    starts establishing an identity for a token with no subject, which would
    turn the anonymous role into whichever caller last used the connection; or
    the row policies stop denying a NULL claim -- and, in the other direction,
    if the authenticated read stops working, in which case the anonymous
    emptiness is meaningless and this says so rather than passing.
    """
    base = rest_base(project_a)
    subject = request_subject(project_a["project"]["key"])

    authenticated = mint_token(project_a, roles["authenticated"], subject=subject)
    seeded = api_call(
        f"{base}/rpc/create_note",
        method="POST",
        token=authenticated,
        body={"p_title": "anon-001-control", "p_content": ""},
    )
    assert seeded.status in (200, 201, 204), f"the control write returned {seeded.status}"

    control = api_call(f"{base}/notes?select=id", token=authenticated)
    assert control.status == 200 and json.loads(control.body), (
        "the authenticated caller read no rows, so an empty anonymous read below "
        "would prove nothing about the anonymous role"
    )

    # Three spellings of "anonymous": no header at all, an explicit anon token,
    # and an anon token carrying a subject. The third is the one that matters --
    # it is a caller asking the hook to give the anonymous role an identity.
    attempts = {
        "no token": api_call(f"{base}/notes?select=id"),
        "anon token": api_call(
            f"{base}/notes?select=id", token=mint_token(project_a, roles["anon"], subject=None)
        ),
        "anon token with a subject": api_call(
            f"{base}/notes?select=id",
            token=mint_token(project_a, roles["anon"], subject=subject),
        ),
    }
    for name, response in attempts.items():
        if response.status == 200:
            assert json.loads(response.body) == [], (
                f"the {name} request read {len(json.loads(response.body))} rows"
            )
        else:
            assert response.status in (401, 403), (
                f"the {name} request returned {response.status}, which is neither a "
                "refusal nor an empty read"
            )

    written = api_call(
        f"{base}/rpc/create_note",
        method="POST",
        token=mint_token(project_a, roles["anon"], subject=subject),
        body={"p_title": "anon-001-write", "p_content": ""},
    )
    assert written.status >= 400, f"the anonymous role performed a write ({written.status})"


# ---------------------------------------------------------------------------
# SEC-PRIV-001 — the private schemas stay private
# ---------------------------------------------------------------------------


def test_the_private_schemas_are_unreachable_through_postgrest(
    project_a: dict[str, Any],
    roles: dict[str, str],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    mint_token: Callable[..., str],
    request_subject: Callable[[str], str],
) -> None:
    """SEC-PRIV-001. Every private object refused **by attempting it**.

    D103 is why this attempts rather than reads a catalog bit:
    ``has_table_privilege`` returned true for ``app.notes`` while the read was
    denied, so a privilege query and an authorization result are different
    facts and only the second is the boundary.

    ADR 0052's exception is asserted in both directions. The pre-request function
    is the one private object a request role may reach, and it must be reachable
    -- a role that cannot execute it cannot make any request at all, including
    the ones this file proves succeed. Every *other* object in ``app_private`` is
    attempted and must fail.

    Goes red if: ``db-schemas`` gains ``app`` or ``app_private``; a request role
    is granted USAGE on ``app``; a future migration adds an object to
    ``app_private`` under default privileges that are not closed; or the grant
    on the hook is widened to the schema rather than to the function.
    """
    base = rest_base(project_a)
    subject = request_subject(project_a["project"]["key"])
    token = mint_token(project_a, roles["authenticated"], subject=subject)

    reachable = api_call(f"{base}/notes?limit=1", token=token)
    assert reachable.status == 200, (
        f"the api surface returned {reachable.status}, so the refusals below would be "
        "about a service that answers nothing"
    )

    # The hook runs on every request, so the read above already proves the
    # exception. Asserted explicitly as well, because "it must be reachable" is
    # half of ADR 0052 and an implicit proof is one nobody can point at.
    status, executable, _ = psql(
        project_a,
        f"SELECT has_function_privilege('{roles['authenticated']}', "
        f"'{PRE_REQUEST_FUNCTION}()', 'EXECUTE');",
        role=None,
    )
    assert status == 0 and executable == "t", (
        f"{roles['authenticated']} cannot execute {PRE_REQUEST_FUNCTION}; no request "
        "from that role can succeed at all"
    )

    status, others, error = psql(
        project_a,
        "SELECT coalesce(string_agg(format('%s.%s', n.nspname, c.relname), ','), '') "
        "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname IN ('app', 'app_private') AND c.relkind IN ('r', 'v', 'm', 'p');",
        role=None,
    )
    assert status == 0, f"could not enumerate the private objects: {error}"
    private_objects = [name for name in others.split(",") if name]
    assert private_objects, (
        "the cluster reports no objects in app or app_private, so there is nothing "
        "here to prove unreachable"
    )

    for qualified in private_objects:
        schema, _, relation = qualified.partition(".")
        by_path = api_call(f"{base}/{qualified}", token=token)
        assert by_path.status != 200, f"{qualified} is readable over HTTP"
        by_profile = api_call(f"{base}/{relation}", token=token, headers={"Accept-Profile": schema})
        assert by_profile.status != 200, f"{qualified} is readable through Accept-Profile"

    # The hook itself, called as an RPC. It is the one object a request role may
    # execute, and it must still not be *addressable*: `db-schemas` exposes only
    # `api`, so a caller cannot name it however the grant reads.
    invoked = api_call(f"{base}/rpc/postgrest_pre_request", method="POST", token=token, body={})
    assert invoked.status != 200, "the pre-request hook is callable as an RPC"


# ---------------------------------------------------------------------------
# SEC-ROLE-001 — role switching cannot exceed granted memberships
# ---------------------------------------------------------------------------


def test_role_switching_cannot_exceed_the_authenticators_memberships(
    project_a: dict[str, Any],
    roles: dict[str, str],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    mint_token: Callable[..., str],
    request_subject: Callable[[str], str],
) -> None:
    """SEC-ROLE-001, with the allowed set derived rather than written down.

    ADR 0046's shape, applied to memberships instead of to LOGIN. The roles a
    token may name are read out of ``pg_auth_members`` for the authenticator, and
    the negatives are the *set difference* against the project's own roles. So
    the session that activates ``agent_reader`` makes the membership assertion
    fail rather than makes this test stale -- which is what a hand-written list
    of forbidden roles would have done, silently, for as long as nobody ran it.

    Every granted role is exercised as a positive control before the refusals,
    because a service that refused every ``SET ROLE`` would pass a negative-only
    matrix perfectly.

    Goes red if: the authenticator gains membership in a role this session does
    not activate; ``SET FALSE`` is dropped from a grant so an inherited role can
    be assumed deliberately; the authenticator itself becomes a superuser or
    gains ``BYPASSRLS``; or a token naming a role outside the memberships stops
    being refused.

    A genuinely foreign project's role is **not** attempted here. That is
    ``DEP-ISO-005``'s claim and it has its own node ID for D70's reason: a
    requirement whose description is broader than its node IDs is a claim the
    evidence file reports as passed.
    """
    base = rest_base(project_a)
    subject = request_subject(project_a["project"]["key"])
    authenticator = roles["postgrest_authenticator"]

    status, granted, error = psql(
        project_a,
        "SELECT coalesce(string_agg(r.rolname, ','), '') FROM pg_catalog.pg_auth_members m "
        "JOIN pg_catalog.pg_roles r ON r.oid = m.roleid "
        "JOIN pg_catalog.pg_roles a ON a.oid = m.member "
        f"WHERE a.rolname = '{authenticator}';",
        role=None,
    )
    assert status == 0, f"could not read the authenticator's memberships: {error}"
    memberships = {name for name in granted.split(",") if name}

    activated = {roles["anon"], roles["authenticated"], roles["api_documentation"]}
    assert memberships == activated, (
        f"{authenticator} is a member of {sorted(memberships)}; this session activates "
        f"exactly {sorted(activated)}. A session that activates another role must move "
        "this assertion with it rather than leave the refusals below measuring nothing"
    )

    # One row per attribute, named. The first version concatenated all three and
    # compared the result to "f,f,f" -- psql's *display* form for a boolean,
    # which is not what `::text` produces. The cast yields "false", so the
    # assertion compared 'false,false,false' to 'f,f,f' and failed on a role
    # that held none of the three. Its message then read "holds superuser,
    # bypassrls or createrole (false,false,false)", which says the opposite of
    # what it found. Named attributes make both mistakes hard to repeat (D193).
    for attribute in ("rolsuper", "rolbypassrls", "rolcreaterole"):
        status, value, error = psql(
            project_a,
            f"SELECT {attribute}::text FROM pg_catalog.pg_roles WHERE rolname = '{authenticator}';",
            role=None,
        )
        assert status == 0, f"could not read {attribute}: {error}"
        # The control on the reading itself: an empty result would compare
        # unequal to "true" and pass this as though the attribute were absent,
        # when it means the role was not found at all.
        assert value in ("true", "false"), (
            f"reading {attribute} for {authenticator} returned {value!r}, which is "
            "neither true nor false -- the role was not found, or the query changed"
        )
        assert value == "false", (
            f"{authenticator} holds {attribute}; nothing below constrains a role "
            "that can become anything"
        )

    # The positive control is `authenticated`, and only `authenticated`.
    #
    # This loop used to require 200 or 206 from *every* membership, which is a
    # claim that contradicts SEC-ANON-001 in the same file: `anonymous_access` is
    # `deny_data`, so `anon` reading `/notes` must be refused. Both tests
    # described the same request and asserted opposite outcomes, and the live run
    # settled it -- `anon` returned `401 {"code":"42501","message":"permission
    # denied for view notes"}`, a PostgreSQL *grant* refusal, which is the
    # boundary SEC-ANON-001 exists to prove (D195).
    #
    # What this test needs from the granted roles is narrower than "can read":
    # it needs the switch to have *happened*, so that the refusals below are
    # about membership rather than about a service that switches to nothing. A
    # PostgreSQL SQLSTATE in the body is that evidence -- the request reached the
    # database as some role -- where a JWT-layer rejection never gets that far.
    reader = api_call(
        f"{base}/notes?limit=1",
        token=mint_token(project_a, roles["authenticated"], subject=subject),
    )
    assert reader.status in (200, 206) and json.loads(reader.body), (
        f"the authenticated role read nothing ({reader.status}); every refusal below "
        "would then be about a service that switches to nothing"
    )

    for role in sorted(memberships):
        allowed = api_call(
            f"{base}/notes?limit=1", token=mint_token(project_a, role, subject=subject)
        )
        if allowed.status in (200, 206):
            continue
        assert "42501" in allowed.body, (
            f"a token naming the granted role {role} returned {allowed.status} with "
            f"{allowed.body[:120]!r}. A granted role is either served or refused by a "
            "grant; anything else means the authenticator did not switch to it"
        )

    # Every other role the project derives, plus a name from no project at all.
    # The second is what a token minted against another deployment's role list
    # would look like to this cluster, and it must fail on the membership rather
    # than on the name being unknown -- which is why both are asserted the same
    # way rather than by matching an error string.
    forbidden = sorted((set(roles.values()) - memberships) | {"apg_no_such_role"})
    for role in forbidden:
        refused = api_call(
            f"{base}/notes?limit=1", token=mint_token(project_a, role, subject=subject)
        )
        assert refused.status in (401, 403, 500), (
            f"a token naming {role} returned {refused.status}; the authenticator "
            "switched to a role it is not a member of"
        )
        assert refused.status != 200, f"a token naming {role} was served rows"


# ---------------------------------------------------------------------------
# SEC-DOCS-001 — the documentation credential reaches no service
# ---------------------------------------------------------------------------


def test_the_documentation_credential_reaches_no_service_and_no_served_byte(
    project_a: dict[str, Any],
    roles: dict[str, str],
    docs_command: Any,
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    mint_token: Callable[..., str],
    sh: Callable[..., str],
    as_root: None,
) -> None:
    """SEC-DOCS-001, in the three places the credential could leak.

    **The filesystem.** ``docs_basic_auth_password`` declares one consumer, in
    the root plane. Asserted against the contract *and* against the generation
    on disk, because the contract says what was declared and the directory says
    what was written -- per-consumer copies are what make "one service cannot
    read another's credential" a filesystem property rather than a policy.

    **The running containers.** No container's environment, command or mounts
    may carry the value. Read from ``docker inspect`` rather than from the
    Compose model: the model says what was asked for, and a value can reach a
    container through a path the model does not describe.

    **The served bytes.** The documentation page's content is the published
    OpenAPI document, and it must carry no credential of any kind -- not the
    Basic Auth password, not an authenticator password, not a bearer token. A
    documentation UI that helpfully pre-filled an API token would satisfy every
    other assertion here.

    The route's own refusal is delegated to ``bin/docs.py``'s ``check``, which
    reports an unreachable route as unreachable. The REST route is asserted to
    answer first: a 401 from a hostname nothing is listening on is not a
    boundary, and that is exactly the state Run 9 deploys through on its way to
    publishing one.

    Goes red if: the credential gains a ``plane: compose`` consumer; a deploy
    materializes it into a container's environment; the middleware is removed
    from the docs router, or its ``usersFile`` stops being read, in which case
    the route answers 200 without a credential; or the served document starts
    carrying credential material.
    """
    del as_root
    project_key = project_a["project"]["key"]

    declared = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    entry = [item for item in declared["secrets"] if item["name"] == "docs_basic_auth_password"]
    assert entry, "the secrets contract declares no docs_basic_auth_password"
    planes = {consumer["plane"] for consumer in entry[0]["consumers"]}
    assert planes == {"root"}, (
        f"docs_basic_auth_password declares consumers in {sorted(planes)}; a compose "
        "consumer is a container that holds the documentation password"
    )

    generation = project_a["secrets"]["generation_id"]
    root_copy = (
        SECRET_ROOT
        / project_key
        / "generations"
        / generation
        / secrets_contract.ROOT_PLANE_DIRECTORY
        / "docs_basic_auth_password"
    )
    assert root_copy.is_file(), f"no documentation credential at {root_copy}"
    secret = root_copy.read_text(encoding="utf-8").rstrip("\n")
    assert secret, f"{root_copy} is empty; the searches below would match everything"

    # Every consumer directory except the root plane's, so this is about where
    # the value went rather than about which files happen to exist.
    for path in sorted((SECRET_ROOT / project_key / "generations" / generation).rglob("*")):
        if not path.is_file() or path == root_copy:
            continue
        assert secret not in path.read_text(encoding="utf-8", errors="replace"), (
            f"the documentation password was materialized into {path}"
        )

    names = [line for line in sh("docker", "ps", "--format", "{{.Names}}").splitlines() if line]
    assert names, "no containers are running, so nothing here was inspected"
    for name in names:
        assert secret not in sh("docker", "inspect", name), (
            f"the documentation password is visible in `docker inspect {name}`"
        )

    base = rest_base(project_a)
    reachable = api_call(
        f"{base}/notes?limit=1", token=mint_token(project_a, roles["authenticated"], subject=None)
    )
    assert reachable.status != 0, (
        f"nothing answered at {base} ({reachable.reason}); a refusal from the "
        "documentation route below would be silence rather than a boundary"
    )

    url = docs_command.docs_url(project_a)
    assert docs_command.check(url) == 0, (
        f"{url} did not refuse with a 401 and a Basic challenge; see the message "
        "bin/docs.py printed for which of the two it was"
    )

    document = api_call(base, token=mint_token(project_a, roles["api_documentation"], subject=None))
    assert document.status == 200, f"the documentation role was served {document.status}"
    for material in (secret, "Bearer ey", "eyJhbGciOi"):
        assert material not in document.body, (
            f"the served document carries {material!r}; a browser loading the "
            "documentation page receives a credential"
        )

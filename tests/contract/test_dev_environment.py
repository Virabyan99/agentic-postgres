"""`apg dev`'s decisions, without a daemon. `DEV-ENV-001`, `DEV-ISO-001`, ADR 0203.

Everything here is a property of `agentic_postgres.dev_environment`, which is
why that module is pure: the arguments `docker run` is given, the statements
that are issued, where the state lives and what `status` concludes can all be
asserted with no container, no image and no network. The cluster module beside
this one measures what they produce.

**The isolation proof is here and not there, for one of its four clauses.** A
container that has not been created cannot be inspected, so the clauses about
its runtime shape belong with the cluster. What belongs here is the clause that
decides them: what this command *tells* docker. D1161's reason -- a property
asserted about an imagined container shape would be red on a correct
environment and green on nothing -- applies to both halves, and the two halves
are named in each other's docstrings so neither can be dropped quietly.
"""

from __future__ import annotations

import ast
import base64
import itertools
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import (
    CURRENT_SESSION,
    REPO_ROOT,
    dev_environment,
    evidence,
    migrations,
    secrets_contract,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"
DEV_PY = REPO_ROOT / "bin" / "dev.py"
DEV_SH = REPO_ROOT / "bin" / "dev.sh"

#: A stand-in path for the superuser env file. These tests never open it --
#: what they read is the argument LIST it lands in -- so it is a constant
#: rather than a real temporary file.
ENV_FILE = Path("superuser.env")


def code_of(path: Path) -> str:
    """A source file with its comments and docstrings removed.

    **A scan that reads prose measures prose.** D277 is the standing instance in
    the other direction -- a check asking whether a name is MENTIONED was
    satisfied by a comment -- and the three scans below hit the same wall
    forbidding a name that only their own subject's docstrings contain: `dev.py`
    explains that it reads neither host root, and naming them is how it explains
    it.

    Python goes through the AST, where a docstring is an expression statement
    whose value is a string constant and a comment does not exist at all. Shell
    has no AST here, so full-line comments are dropped and the rest is kept --
    which is what `sql_surface` does for SQL, and for the same reason.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".py":
        return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))

    tree = ast.parse(text)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                body.pop(0)
    return ast.unparse(tree)


def imports_of(path: Path) -> set[str]:
    """Every module name a Python file imports, as NAMES rather than characters.

    A substring scan cannot tell `bootstrap_state` from `bootstrap_statements`,
    and refusing the second because it contains the first is how a guard refuses
    the thing it was written to require.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
            if node.module:
                names.add(node.module.split(".")[-1])
    return names


#: `read_state` on an unreadable directory, made as the CHECKOUT'S OWNER.
#:
#: D1155's shape, for D1155's reason: root traverses a 0000 directory, so the
#: state this asserts on cannot be observed as root at all -- and the gate runs
#: its static claim proofs as root. A `skipif` here would be a proof the gate
#: can never record. Out of process because privilege cannot be dropped for one
#: call and put back, and it IMPORTS the reader rather than reimplementing it
#: (D673).
_READ_STATE_AS_OWNER = """
import json, pathlib, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from agentic_postgres import dev_environment

try:
    dev_environment.read_state("unreadable-dev", pathlib.Path(sys.argv[3]))
except dev_environment.StateUnreadable as error:
    print(json.dumps({"kind": "unreadable", "message": str(error)}))
except dev_environment.StateAbsent as error:
    print(json.dumps({"kind": "absent", "message": str(error)}))
except Exception as error:
    print(json.dumps({"kind": type(error).__name__, "message": str(error)}))
else:
    print(json.dumps({"kind": "read", "message": ""}))
"""


def _read_state_as_the_checkout_owner(root: Path) -> tuple[str, str]:
    owner = REPO_ROOT.stat()
    if owner.st_uid == 0:
        pytest.skip(
            f"{REPO_ROOT} is root-owned, so there is no unprivileged checkout owner to "
            "make the reading as (D1121/D1155)"
        )
    result = subprocess.run(
        [
            "sudo", "-n", "-u", f"#{owner.st_uid}", "-g", f"#{owner.st_gid}",
            str(REPO_ROOT / ".venv" / "bin" / "python"), "-c", _READ_STATE_AS_OWNER,
            str(REPO_ROOT / "src"), str(REPO_ROOT / "services" / "auth-api"), str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )  # fmt: skip
    assert result.returncode == 0, (
        f"the reading as the checkout owner did not run: {result.stderr.strip()[:400]}"
    )
    answer = json.loads(result.stdout)
    return answer["kind"], answer["message"]


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    return json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# What docker is told (DEV-ISO-001's decisive half)
# ---------------------------------------------------------------------------


def test_the_run_arguments_name_the_locked_image_by_digest_and_nothing_else() -> None:
    """The image is the release's, pinned, and the list ends with it.

    A tag would let the environment, the contract suite and a deployment drift
    onto three sets of bytes while every one of them reported the same name.
    """
    image = dev_environment.locked_image()
    assert "@sha256:" in image, f"{image} is not pinned by digest"

    arguments = dev_environment.run_arguments("apg-dev-x", image, ENV_FILE)
    assert arguments[0] == "run", "the list is the WHOLE docker invocation, verb included"
    assert arguments[-1] == image, "the image is not the last argument, so it is not the command"

    lock = (REPO_ROOT / "versions.env").read_text(encoding="utf-8")
    assert f"POSTGRES_IMAGE={image}" in lock, "the image is not the one versions.env pins"


def test_the_run_arguments_carry_no_network_no_mount_and_no_server_option() -> None:
    """D1161 and D1172 and D1175, at the point where they are decided.

    What a container can reach is decided by what `docker run` is told. Told no
    `--network`, it joins the default bridge and nothing else; told no `-v` or
    `--mount`, its only mount is the anonymous volume the image itself declares;
    told no `-c`, it runs the image's own `wal_level`.

    The port clause is the sharp one. `-p 127.0.0.1:0:5432` records `HostIp
    127.0.0.1`; `-p 0:5432` records `0.0.0.0` AND `::` -- measured in rig 22a,
    which is why this asserts the ADDRESS and not merely that a port is
    published.
    """
    arguments = dev_environment.run_arguments("apg-dev-x", "img@sha256:aa", ENV_FILE)

    for forbidden in ("--network", "-v", "--volume", "--mount", "-c", "--privileged", "--user"):
        assert forbidden not in arguments, (
            f"{forbidden} is in the run arguments. The environment's isolation is a "
            "property of what docker is told, and this tells it something else"
        )

    published = [value for flag, value in itertools.pairwise(arguments) if flag == "-p"]
    assert published == ["127.0.0.1:0:5432"], (
        f"the published ports are {published}. Exactly one, on loopback, with an "
        "ephemeral host port -- an unbound address publishes on 0.0.0.0 and :: both"
    )


def test_no_password_is_ever_an_argument() -> None:
    """D105, D1160: a value in an argument vector is a value `ps` reads.

    The superuser password reaches the container through `--env-file`, and the
    two role passwords reach `psql` the same way. This asserts the shape in the
    arguments AND in the source of the command that builds the rest of them,
    because the second is where a future `-e PGPASSWORD=…` would be written.
    """
    arguments = dev_environment.run_arguments("apg-dev-x", "img", ENV_FILE)
    assert "--env-file" in arguments
    assert not any(argument.startswith("-e") for argument in arguments), arguments

    source = DEV_PY.read_text(encoding="utf-8")
    offenders = re.findall(r'"-e",\s*f?"(?:PG)?PASSWORD=', source)
    assert not offenders, (
        f"bin/dev.py passes a password as an argument: {offenders}. `--env-file` is the "
        "mechanism, measured on docker 29.5.2 for both `run` and `exec` (D1160)"
    )
    assert "--env-file" in source


def test_the_state_root_and_the_document_root_are_the_checkouts_and_never_the_hosts() -> None:
    """An environment is a thing a developer owns, in their own checkout.

    `/var/lib/agentic-postgres` and `/etc/agentic-postgres` are the host's roots
    and need root to read; a dev command that touched either would be a command
    that works for one user on one machine.
    """
    assert dev_environment.STATE_ROOT == REPO_ROOT / ".generated" / ".dev"
    assert dev_environment.state_dir("x-dev").is_relative_to(REPO_ROOT)

    for path in (DEV_PY, DEV_SH):
        source = code_of(path)
        for host_root in ("/var/lib/agentic-postgres", "/etc/agentic-postgres"):
            assert host_root not in source, (
                f"{path.name} names {host_root} in its CODE. Both need root to read, and "
                "an environment is a thing a developer owns"
            )
        assert "sudo" not in source, f"{path.name} runs sudo; an environment needs no root"

    # The control, in the same test: the scan reads code and not prose, so a
    # forbidden name IS found when it is in the code. Without this, a `code_of`
    # that returned the empty string would satisfy every assertion above.
    #
    # `deployed_output` and not `doctor.py`, which was the first guess and was
    # wrong: the doctor reaches the host's rendered root through
    # `rendered_path`, and the literal is in the module that derives it. A
    # control asserting something false reports a working scan as broken.
    host_reader = code_of(REPO_ROOT / "src" / "agentic_postgres" / "deployed_output.py")
    assert "/var/lib/agentic-postgres" in host_reader, (
        "the module that derives the host's rendered root does not name it in its code "
        "and this scan did not see it, so the scan above is reading nothing"
    )


def test_the_state_directory_is_dot_prefixed_and_invisible_to_the_evidence_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1173: a running environment is not a rendered project.

    `evidence.load_rendered` walks `.generated/` and every directory it finds is
    a project in the isolation collision count. The environment's state sits
    under a DOT-prefixed directory, which that reader skips -- so an environment
    can never turn up in a collision count or in an evidence document.

    The control is in the same test: a normally-named directory beside it IS
    found, or "the reader skips it" would be true of a reader that finds
    nothing.
    """
    generated = tmp_path / ".generated"
    current = {"schema_version": evidence.OUTPUTS_SCHEMA_VERSION, "document_kind": "rendered"}
    for name in (".dev/fixture-x-dev", "fixture-y-dev"):
        directory = generated / name
        directory.mkdir(parents=True)
        (directory / "outputs.json").write_text(json.dumps(current), encoding="utf-8")

    monkeypatch.setattr(evidence, "REPO_ROOT", tmp_path)
    found = evidence.load_rendered()

    assert set(found) == {"fixture-y-dev"}, (
        f"the evidence reader found {sorted(found)}. A development environment under "
        ".generated/.dev/ must be invisible to it, and a rendered project beside it "
        "must not be"
    )
    assert dev_environment.STATE_ROOT.name.startswith("."), (
        "the state root is not dot-prefixed, so the reader above would find it"
    )


# ---------------------------------------------------------------------------
# The statements (DEV-ENV-001, DEV-SUBJECT-001)
# ---------------------------------------------------------------------------


def test_the_activation_statements_quote_the_role_and_the_password(
    document: dict[str, Any],
) -> None:
    """Exactly two roles get a password, and the control is which one does not.

    `object_owner` stays NOLOGIN: the owner's authority is reachable only
    through `SET LOCAL ROLE` from the migration user, which is the mechanism
    every migration in this release is written against and the mechanism D285's
    defect was invisible without (ADR 0026, D266).
    """
    roles = document["database"]["roles"]
    statements = dev_environment.activation_statements(document, "migration-pw", "runtime-pw")

    assert len(statements) == 2, statements
    named = {roles[key] for key in dev_environment.ACTIVATED_ROLES}
    for statement in statements:
        assert statement.startswith("ALTER ROLE ")
        assert any(f'"{role}"' in statement for role in named), statement
        assert "LOGIN PASSWORD '" in statement

    joined = "\n".join(statements)
    assert roles["object_owner"] not in joined, (
        "the object owner is activated with a password. It is NOLOGIN by design, and a "
        "login on it makes `SET LOCAL ROLE` one of two routes to the owner's authority"
    )
    for role in ("postgrest_authenticator", "auth_service", "storage_service", "backup_user"):
        assert roles[role] not in joined, f"{role} is activated by a development environment"

    # The password is a quoted LITERAL, through the renderer's own quoter -- so
    # a value that could change the statement's shape cannot reach it.
    assert migrations.quote_literal("mig'ration") == "'mig''ration'"
    quoted = dev_environment.activation_statements(document, "a'b", "c'd")
    assert "'a''b'" in quoted[0], quoted[0]


def test_the_placeholder_verifier_satisfies_the_check_and_encodes_no_password(
    document: dict[str, Any],
) -> None:
    """D1171: a verifier for no password is the honest row for a subject nobody
    can log in as.

    `app_private.user_credentials` carries `CHECK (password_hash LIKE
    '$argon2id$%')`, so the row has to be well formed; the environment has no
    login path, so there is nothing behind it. Both halves are asserted: the
    shape the CHECK wants, and that two calls do not agree -- a constant would
    be a credential shipped in source.
    """
    verifier = dev_environment.placeholder_verifier()
    assert verifier.startswith("$argon2id$"), verifier
    parameters, salt, digest = verifier.rsplit("$", 2)
    assert parameters == "$argon2id$v=19$m=65536,t=3,p=4"
    assert "=" not in salt and "=" not in digest, "argon2's encoding carries no padding"
    assert len(salt) == 22 and len(digest) == 43, (salt, digest)
    base64.b64decode(salt + "==")
    base64.b64decode(digest + "=")

    assert dev_environment.placeholder_verifier() != verifier, (
        "two calls produced the same verifier, so it is a constant in the source rather "
        "than an encoding of random bytes"
    )


def test_the_subject_statement_names_the_authenticated_role_and_the_derived_vocabulary(
    document: dict[str, Any],
) -> None:
    """D1176: nothing downstream checks the role name, so this does.

    Rig 22b-2 created a subject with `role_name` `'nobody'` and got a uuid back:
    `app_private.users` has no FK, CHECK or trigger over that column, and
    `_role_name` -- the auth service's guard -- is in a service this command
    does not run. The derivation is this command's job.

    The scopes are the merged surface's whole derived data class (ADR 0200),
    which for the example project is seven and for the release alone is five.
    """
    roles = document["database"]["roles"]
    vocabulary = dev_environment.subject_vocabulary(document)
    statement = dev_environment.subject_statement(document, vocabulary)

    assert "app_private.auth_create_user(" in statement
    assert f"'{roles['authenticated']}'" in statement, (
        f"the subject is not created with {roles['authenticated']}, the role the auth "
        "service stores in full"
    )
    for other in ("app_runtime", "migration_user", "anon", "agent_reader"):
        assert f"'{roles[other]}'" not in statement, f"the subject names {other}"

    assert vocabulary == tuple(sorted(vocabulary)), "the scopes are not sorted"
    assert len(set(vocabulary)) == len(vocabulary), "the scopes carry a duplicate"
    assert "note_embeddings:read" in vocabulary, (
        "the fixture project declares a set and a surface, so the merged vocabulary "
        "carries its relation; without it this asserts the RELEASE's vocabulary and "
        "says nothing about merging"
    )
    assert "meta:read" in vocabulary
    for scope in vocabulary:
        assert f"'{scope}'" in statement, f"{scope} is not in the statement"


def test_a_project_with_no_set_gets_the_release_vocabulary_alone() -> None:
    """The control for the test above: merging is what the project surface does.

    `project.second.example.yaml` renders a document with no `project_set`, so
    its subject holds the release's scopes and not the example project's.
    """
    second = REPO_ROOT / ".generated" / "fixture-alpine-dev" / "outputs.json"
    if not second.is_file():
        pytest.skip("no second rendered fixture; run ./deploy.sh --render-only")
    document = json.loads(second.read_text(encoding="utf-8"))
    assert (document.get("migrations") or {}).get("project_set") is None

    vocabulary = dev_environment.subject_vocabulary(document)
    assert "meta:read" in vocabulary
    assert not [scope for scope in vocabulary if scope.startswith("note_embeddings")], (
        f"a project with no set got the example project's scopes: {vocabulary}"
    )


def test_planned_migrations_are_the_rendered_files_in_manifest_order_and_a_moved_digest_is_refused(
    tmp_path: Path,
) -> None:
    """ADR 0028: the rendered payload is the immutable unit, and this is where a
    dev cluster is told so.

    The same verification `bin/migrate.py` runs before dbmate reads the
    directory -- one function, so a dev cluster and a deploy cannot disagree
    about which bytes are legitimate. The refusal is measured by editing a
    rendered file, which is exactly the accident the digest exists for.
    """
    entries = dev_environment.planned_migrations(FIXTURE)
    versions = [entry["version"] for entry in entries]
    assert versions == sorted(versions), "the planned order is not version order"
    assert len(versions) >= 32, f"only {len(versions)} migrations were planned"

    recorded = json.loads(
        (FIXTURE / "migrations" / "rendered-manifest.json").read_text(encoding="utf-8")
    )
    assert versions == [entry["version"] for entry in recorded["migrations"]], (
        "the planned order is not the manifest's order, which is the order dbmate "
        "applies the directory in"
    )

    # A copy, edited. The committed fixture is never touched.
    copied = tmp_path / "rendered"
    (copied / "migrations").mkdir(parents=True)
    for path in (FIXTURE / "migrations").glob("*"):
        (copied / "migrations" / path.name).write_bytes(path.read_bytes())

    target = copied / "migrations" / recorded["migrations"][0]["file"]
    target.write_text(target.read_text(encoding="utf-8") + "\n-- edited\n", encoding="utf-8")
    with pytest.raises(migrations.MigrationError, match="edited after rendering"):
        dev_environment.planned_migrations(copied)


def test_the_migration_transaction_carries_the_up_half_and_its_own_ledger_row() -> None:
    """The row dbmate writes, written where dbmate writes it.

    Inside the migration's own transaction, so a migration that fails leaves no
    row. The `down` half is dropped, because a payload applied whole would run
    the `AP900` refusal every released migration carries.
    """
    payload = (
        "-- migrate:up\nCREATE TABLE app.x ();\n"
        "-- migrate:down\nDO $$ BEGIN RAISE EXCEPTION 'AP900'; END $$;\n"
    )
    transaction = dev_environment.transaction_body(payload, "20260101120000")

    assert "CREATE TABLE app.x ();" in transaction
    assert "-- migrate:up" not in transaction
    assert "AP900" not in transaction, "the down half is in the transaction"
    assert transaction.rstrip().endswith(
        "INSERT INTO app_private.schema_migrations (version) VALUES ('20260101120000');"
    ), transaction

    # The version is a quoted literal, like every other value here.
    assert "'20260101120000'" in transaction


# ---------------------------------------------------------------------------
# The state, and its three outcomes
# ---------------------------------------------------------------------------


def test_the_state_is_written_private_and_read_back_whole(tmp_path: Path) -> None:
    environment = dev_environment.Environment(
        project_key="fixture-x-dev",
        container="apg-dev-fixture-x-dev",
        database="fixture_x_dev",
        roles={"migration_user": "m", "app_runtime": "a"},
        port=32768,
        subject_id="6662ebe0-c198-404a-9747-62b20ee6e581",
        image="img@sha256:aa",
        release_commit="abc123",
        started_at="2026-09-11T22:06:00+00:00",
        rendered_dir=str(FIXTURE),
    )
    path = dev_environment.write_state(environment, tmp_path)

    assert path.stat().st_mode & 0o777 == dev_environment.STATE_FILE_MODE
    assert path.parent.stat().st_mode & 0o777 == dev_environment.STATE_DIR_MODE
    assert dev_environment.read_state("fixture-x-dev", tmp_path) == environment


def test_state_that_is_absent_unreadable_or_stale_are_three_different_answers(
    tmp_path: Path,
) -> None:
    """ADR 0195, and D1060 is what folding two of them together costs.

    A directory this user cannot traverse answers `is_file()` false exactly as a
    missing one does. Reporting *"no environment"* about one that exists sends a
    developer to create a second.

    **The unreadable arm was missing and Run 3's battery found it.** The first
    version of this test asserted absent, half-written and unparseable, and a
    mutation that made `read_state` answer `StateAbsent` on `PermissionError`
    survived it -- the branch under discussion in the docstring was the one
    branch not exercised. Constructing it needs a directory this process cannot
    traverse, which root can traverse anyway, so under root the reading is made
    as the checkout's owner (D1155's shape).
    """
    with pytest.raises(dev_environment.StateAbsent):
        dev_environment.read_state("nothing-here-dev", tmp_path)

    shut = dev_environment.state_dir("unreadable-dev", tmp_path)
    shut.mkdir(parents=True)
    (shut / dev_environment.STATE_FILE).write_text("{}", encoding="utf-8")
    shut.chmod(0o000)
    try:
        if os.geteuid() == 0:
            kind, message = _read_state_as_the_checkout_owner(tmp_path)
        else:
            with pytest.raises(dev_environment.StateUnreadable) as raised:
                dev_environment.read_state("unreadable-dev", tmp_path)
            kind, message = "unreadable", str(raised.value)
    finally:
        shut.chmod(0o700)

    assert shut.stat().st_mode & 0o777 == 0o700, "the fixture directory was not restored"
    assert kind == "unreadable", (
        f"a state directory this user cannot traverse was reported as {kind!r}. "
        "Reporting 'no environment' about an environment that exists is D1060"
    )
    assert "cannot read" in message and "chown" in message, message
    assert "no development environment" not in message, (
        "the unreadable message carries the sentence that means absent"
    )

    directory = dev_environment.state_dir("half-written-dev", tmp_path)
    directory.mkdir(parents=True)
    (directory / dev_environment.STATE_FILE).write_text('{"project_key": "x"}', encoding="utf-8")
    with pytest.raises(dev_environment.DevEnvironmentError, match="missing"):
        dev_environment.read_state("half-written-dev", tmp_path)

    (directory / dev_environment.STATE_FILE).write_text("not json", encoding="utf-8")
    with pytest.raises(dev_environment.DevEnvironmentError, match="not readable JSON"):
        dev_environment.read_state("half-written-dev", tmp_path)


# ---------------------------------------------------------------------------
# What `status` concludes
# ---------------------------------------------------------------------------


def test_status_has_four_answers_and_unknown_is_one_of_them() -> None:
    """A container that cannot be asked and a container that is not there are
    different facts, and a developer acts differently on each (ADR 0195)."""
    environment = dev_environment.Environment(
        project_key="k", container="apg-dev-k", database="d", roles={}, port=1,
        subject_id="s", image="i", release_commit="c", started_at="t", rendered_dir="r",
    )  # fmt: skip

    assert dev_environment.status_of(None, None, None, 33)[0] == dev_environment.ABSENT
    assert dev_environment.status_of(environment, None, None, 33)[0] == dev_environment.UNKNOWN
    assert dev_environment.status_of(environment, "exited", None, 33)[0] == dev_environment.STOPPED
    assert dev_environment.status_of(environment, "running", None, 33)[0] == dev_environment.UNKNOWN
    assert dev_environment.status_of(environment, "running", 30, 33)[0] == dev_environment.STOPPED
    assert dev_environment.status_of(environment, "running", 33, 33)[0] == dev_environment.RUNNING

    # Every answer says something a developer can act on.
    for arguments in (
        (None, None, None, 33),
        (environment, None, None, 33),
        (environment, "exited", None, 33),
        (environment, "running", 30, 33),
    ):
        _, sentence = dev_environment.status_of(*arguments)
        assert sentence and sentence[0].islower(), sentence
        assert len(sentence) > 20, sentence


# ---------------------------------------------------------------------------
# DEV-ISO-001: no name the secrets contract declares
# ---------------------------------------------------------------------------


def test_no_secret_name_the_contract_declares_reaches_the_environment(
    document: dict[str, Any],
) -> None:
    """D1161: the question is whether ANY declared name is here, every facility.

    Narrowing to the environment's own facilities would be circular -- it has
    none -- so the declared view is read whole and the environment's three file
    names and its `docker run` arguments are checked against it.
    """
    contract = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    declared = {
        secret["name"] for secret in secrets_contract.active_secrets(contract, CURRENT_SESSION)
    }
    assert len(declared) > 5, (
        f"the contract declares only {sorted(declared)}; this is reading the wrong "
        "document and would accept anything"
    )

    surface = [
        dev_environment.SUPERUSER_ENV,
        dev_environment.MIGRATION_USER_ENV,
        dev_environment.APP_RUNTIME_ENV,
        dev_environment.STATE_FILE,
        dev_environment.SEEDS_FILE,
        *dev_environment.run_arguments("apg-dev-x", "img", ENV_FILE),
    ]
    for name in declared:
        for item in surface:
            assert name not in item, (
                f"the environment's {item!r} names the declared secret {name!r}. A dev "
                "cluster holds no production credential (ADR 0203 §5)"
            )


def test_the_command_reads_no_facility_gated_secret_and_no_deployed_document() -> None:
    """The source, because an absence is what is being asserted.

    A dev environment reads the RENDERED document from the checkout and nothing
    from the host's secret root, its backup configuration or its provider state.
    """
    # **The IMPORTS, from the AST, not a substring scan.** `bootstrap_state` is
    # a prefix of `bootstrap_statements`, which this command imports on purpose
    # -- a substring scan cannot tell a module from a run of characters, and the
    # first version of this test refused the command for importing the thing it
    # is built on.
    forbidden = {"secrets_contract", "bootstrap_state", "edge_state", "jwt_keys"}
    imported = imports_of(DEV_PY)
    assert forbidden.isdisjoint(imported), (
        f"bin/dev.py imports {sorted(forbidden & imported)}. A development environment "
        "reads the rendered document from the checkout and nothing from the host's "
        "secret root, its provider state or its signing keys (ADR 0203 §5)"
    )
    assert "bootstrap_statements" in imported, (
        "the command does not import the bootstrap statements, so it is applying a "
        "second implementation of them (F-005)"
    )

    # The control: the same reader over the deploy, which DOES import all of it.
    # Without it, an `imports_of` that returned nothing would satisfy the above.
    deploy_imports = imports_of(REPO_ROOT / "bin" / "deploy-project.py")
    assert forbidden & deploy_imports, (
        f"the deploy imports none of {sorted(forbidden)}, so the absences asserted "
        "above are absences from a reader that reads nothing"
    )

    source = code_of(DEV_PY) + "\n" + code_of(DEV_SH)
    for name in ("materialize", "pgbackrest", "SECRET_ROOT", "runtime=True"):
        assert name not in source, (
            f"bin/dev.* names {name} in its CODE. A development environment holds no "
            "production credential and reads no host state (ADR 0203 §5)"
        )

    assert "read_rendered_document" in source, "the command does not read the rendered document"
    assert "runtime=False" in source, (
        "the command reads the runtime document rather than the render"
    )

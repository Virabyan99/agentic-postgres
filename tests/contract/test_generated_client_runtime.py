"""`GEN-HASH-001`'s offline half and `GEN-TYPES-001` (Session 23 Run 4).

The generated client against a **real served surface**, in the toolchain image,
with no host and no network beyond the rig's own.

**The rig is the product's own edge, and that is not decoration** (ADR 0065,
ADR 0066). Production serves the REST document with `basePath: /api/rest`
because Traefik strips that prefix before PostgREST; PostgREST itself serves at
the root and has no prefix option. A rig reaching PostgREST directly therefore
CANNOT reproduce the shape every adopter has — measured in rig 23h: the client
pointed at the root is refused (correctly) for a basePath mismatch, and pointed
at the prefix gets a 404. So the rig runs the pinned Traefik with a
`stripPrefix` middleware over the project's own `API_REST_PATH`, and the client
is exercised at exactly the URL shape a deployment publishes (D1230).

**Configured from the product's own model.** The PostgREST container's
environment is `compose.yaml`'s `services.postgrest.environment` block with
every `${NAME}` resolved from the rendered `compose.env` — read, not retyped, so
a configuration change in the product reaches this rig rather than drifting away
from it.

**One superuser action, named as a rig's** (ADR 0066): the dev environment
activates two roles by decision (ADR 0203) and the authenticator is not one of
them, so this rig activates it — through `docker exec` stdin, never an argument
(D1160).

**The token carries a role and no subject**, which is `bin/dev-token.py`'s
documented property: migration 0013's hook returns early without a `sub`, so the
token reaches the surface and reads no owner's rows. That is what makes the read
proof honest about its empty result and the write proof a real `PT401`.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import time
from typing import Any

import pytest
from tests.contract.test_image_contracts import requires_docker

from agentic_postgres import REPO_ROOT, openapi_normalize

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.database, pytest.mark.security]

APG = REPO_ROOT / "bin" / "apg.sh"
PROJECT = "project.example.yaml"
KEY = "fixture-alpha-dev"
FIXTURE = REPO_ROOT / ".generated" / KEY
CLIENT = REPO_ROOT / "projects" / "example" / "clients" / "typescript"
SNAPSHOT = REPO_ROOT / "projects" / "example" / "contracts" / "postgrest-openapi.canonical.json"
TOOLCHAIN = REPO_ROOT / "services" / "clients" / "typescript"


def docker(*arguments: str, stdin: str | None = None, timeout: int = 600):
    return subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        check=False,
        input=stdin,
        timeout=timeout,
    )


def apg(*arguments: str, timeout: int = 900):
    return subprocess.run(
        [str(APG), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        timeout=timeout,
    )


def locked(name: str) -> str:
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    pytest.fail(f"versions.env pins no {name}")


def rendered_environment() -> dict[str, str]:
    """The project's own rendered `compose.env`, as `KEY=VALUE` lines."""
    values: dict[str, str] = {}
    for line in (FIXTURE / "compose.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def postgrest_environment(
    resolved: dict[str, str], *, authenticator: str, database: str, anon_role: str, proxy_uri: str
) -> dict[str, str]:
    """`compose.yaml`'s own `postgrest.environment`, with `${…}` resolved.

    Read from the file rather than restated, so a change to the product's
    configuration reaches this rig. An unresolved `${…}` fails loudly below
    rather than becoming an empty string, which is how a rig comes to measure a
    service configured differently from the one it claims to stand in for.
    """
    import re

    import yaml

    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    block = compose["services"]["postgrest"]["environment"]

    overrides = {
        "POSTGREST_AUTHENTICATOR_ROLE": authenticator,
        "POSTGRES_DATABASE_NAME": database,
        "ANON_ROLE_NAME": anon_role,
        **resolved,
    }
    # Compose writes both `${NAME:?err}` and `${NAME?err}`; matching only the
    # colon form left one value unresolved, and the assertion below is what
    # said so rather than a service quietly configured with a literal.
    pattern = re.compile(r"\$\{([A-Z0-9_]+)(?:[:?][^}]*)?\}")

    values: dict[str, str] = {}
    for key, raw in block.items():
        text = "" if raw is None else str(raw)

        def substitute(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in overrides:
                pytest.fail(
                    f"compose.yaml's postgrest block names ${{{name}}}, which the rendered "
                    "compose.env does not carry. A rig that substituted an empty string here "
                    "would configure a different service and report on it as though it were "
                    "the product's"
                )
            return overrides[name]

        resolved_value = pattern.sub(substitute, text)
        assert "${" not in resolved_value, f"{key} still holds a placeholder: {resolved_value}"
        values[key] = resolved_value

    # The proxy URI is the ONE value the rig overrides, and only in the arm that
    # needs a different base: the edge below serves the product's own.
    values["PGRST_OPENAPI_SERVER_PROXY_URI"] = proxy_uri
    # The conninfo names the rig's own pgpass path, keeping the product's
    # `?passfile=` shape so no password reaches `docker inspect`.
    values["PGRST_DB_URI"] = (
        f"postgres://{authenticator}@{resolved['POSTGRES_SERVICE_HOST']}:5432/"
        f"{database}?passfile=/run/secrets/postgrest_authenticator_pgpass"
    )
    # **The rig signs its own tokens** (D1231). compose.yaml sets no
    # `PGRST_JWT_SECRET` -- the deployment configures a JWKS from the auth
    # service's published key, and this rig has neither. Without one PostgREST
    # answers 500 to every request carrying an Authorization header, and the
    # generated client ALWAYS carries one: measured in rig 23g, where all four
    # arms returned 500 before this line existed.
    # Inside the container, reached only over the rig's own user-defined
    # network; it publishes no port to the host.
    values.setdefault("PGRST_SERVER_HOST", "0.0.0.0")  # noqa: S104
    values.setdefault("PGRST_SERVER_PORT", "3000")
    values["PGRST_ADMIN_SERVER_HOST"] = "127.0.0.1"
    values["PGRST_ADMIN_SERVER_PORT"] = "3001"
    values["PGRST_LOG_LEVEL"] = "error"
    return values


def mint(secret: str, *, role: str, audience: str) -> str:
    """A token PostgREST verifies, naming a ROLE and no subject.

    HS256 with a secret this rig generates and discards. Production signs RS256
    against the auth service's published JWKS; the algorithm is the rig's own
    configuration and the client is indifferent to it -- it sends what it was
    handed, which is the whole of its involvement with credentials.
    """
    import jwt

    return jwt.encode(
        {"role": role, "aud": audience, "exp": int(time.time()) + 900},
        secret,
        algorithm="HS256",
    )


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """A dev cluster, PostgREST on the product's configuration, and the edge.

    Removed in `finally`, whatever happens -- including the network, which a
    left-behind container would otherwise pin.
    """
    if not (FIXTURE / "compose.env").is_file():
        pytest.skip("the fixture project is not rendered in this checkout")

    work = tmp_path_factory.mktemp("client-runtime")
    suffix = secrets.token_hex(3)
    network = f"apg-client-runtime-{suffix}"
    secret = secrets.token_hex(32)
    containers: list[str] = []
    connected = None

    apg("dev", "down", "--project", PROJECT)
    up = apg("dev", "up", "--project", PROJECT)
    assert up.returncode == 0, f"`apg dev up` exited {up.returncode}\n{up.stdout}\n{up.stderr}"

    try:
        from agentic_postgres import dev_environment

        state = json.loads(
            (dev_environment.state_dir(KEY) / dev_environment.STATE_FILE).read_text(
                encoding="utf-8"
            )
        )
        outputs = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
        resolved = rendered_environment()
        roles = outputs["database"]["roles"]
        authenticator = roles["postgrest_authenticator"]
        database = state["database"]

        # The rig's one superuser action, through stdin.
        password = secrets.token_hex(24)
        altered = docker(
            "exec", "-i", state["container"],
            "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database,
            stdin=f"ALTER ROLE \"{authenticator}\" LOGIN PASSWORD '{password}';\n",
        )  # fmt: skip
        assert altered.returncode == 0, altered.stderr

        pgpass = work / "pgpass"
        pgpass.write_text(f"*:*:*:{authenticator}:{password}\n", encoding="utf-8")
        pgpass.chmod(0o600)

        created = docker("network", "create", network)
        assert created.returncode == 0, created.stderr
        joined = docker(
            "network", "connect", "--alias", resolved["POSTGRES_SERVICE_HOST"],
            network, state["container"],
        )  # fmt: skip
        assert joined.returncode == 0, joined.stderr
        connected = state["container"]

        rest_path = resolved["API_REST_PATH"]
        proxy_uri = f"https://{resolved['PROJECT_DOMAIN']}{rest_path}"
        values = postgrest_environment(
            resolved,
            authenticator=authenticator,
            database=database,
            anon_role=roles["anon"],
            proxy_uri=proxy_uri,
        )
        values["PGRST_JWT_SECRET"] = secret
        env_file = work / "postgrest.env"
        env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
        env_file.chmod(0o600)

        rest = f"apg-client-runtime-rest-{suffix}"
        made = docker(
            "run", "-d", "--name", rest,
            "--network", network, "--network-alias", "postgrest",
            "--env-file", str(env_file),
            "-v", f"{pgpass}:/run/secrets/postgrest_authenticator_pgpass:ro",
            locked("POSTGREST_IMAGE"),
        )  # fmt: skip
        assert made.returncode == 0, made.stderr
        containers.append(rest)

        deadline = time.monotonic() + 90
        warm = False
        while time.monotonic() < deadline:
            logs = docker("logs", rest)
            if "Schema cache loaded" in logs.stdout + logs.stderr:
                warm = True
                break
            time.sleep(1)
        assert warm, (
            f"PostgREST never loaded its schema cache:\n{docker('logs', rest).stderr[-800:]}"
        )

        # The edge, with the product's own prefix stripped the way it strips it.
        (work / "dynamic").mkdir()
        (work / "traefik.yaml").write_text(
            "entryPoints:\n  web:\n    address: ':8080'\n"
            "providers:\n  file:\n    directory: /etc/traefik/dynamic\n    watch: false\n"
            "log:\n  level: ERROR\n",
            encoding="utf-8",
        )
        (work / "dynamic" / "rest.yaml").write_text(
            "http:\n"
            "  routers:\n"
            "    rest:\n"
            f'      rule: "PathPrefix(`{rest_path}`)"\n'
            "      entryPoints: [web]\n"
            "      middlewares: [strip]\n"
            "      service: rest\n"
            "  middlewares:\n"
            "    strip:\n"
            "      stripPrefix:\n"
            f'        prefixes: ["{rest_path}"]\n'
            "  services:\n"
            "    rest:\n"
            "      loadBalancer:\n"
            "        servers:\n"
            '          - url: "http://postgrest:3000"\n',
            encoding="utf-8",
        )
        for path in (work / "traefik.yaml", work / "dynamic" / "rest.yaml"):
            path.chmod(0o644)
        (work / "dynamic").chmod(0o755)

        edge = f"apg-client-runtime-edge-{suffix}"
        made = docker(
            "run", "-d", "--name", edge,
            "--network", network, "--network-alias", "edge",
            "-v", f"{work / 'traefik.yaml'}:/etc/traefik/traefik.yaml:ro",
            "-v", f"{work / 'dynamic'}:/etc/traefik/dynamic:ro",
            locked("TRAEFIK_IMAGE"),
        )  # fmt: skip
        assert made.returncode == 0, made.stderr
        containers.append(edge)
        time.sleep(4)

        image = f"apg-client-typescript:{locked('TYPESCRIPT_VERSION')}"
        built = docker(
            "build", "-q", "--build-arg", f"BASE_IMAGE={locked('NODE_RUNTIME_IMAGE')}",
            "-t", image, str(TOOLCHAIN),
        )  # fmt: skip
        assert built.returncode == 0, f"{built.stdout}\n{built.stderr}"

        yield {
            "network": network,
            "image": image,
            "work": work,
            "rest_url": f"http://edge:8080{rest_path}",
            "direct_url": "http://postgrest:3000",
            "authenticated": mint(
                secret, role=roles["authenticated"], audience=resolved["JWT_AUDIENCE"]
            ),
            "anon": mint(secret, role=roles["anon"], audience=resolved["JWT_AUDIENCE"]),
            "containers": containers,
            "fingerprint": openapi_normalize.fingerprint(
                json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            ),
        }
    finally:
        for name in containers:
            docker("rm", "-f", "-v", name, timeout=120)
        if connected:
            docker("network", "disconnect", "-f", network, connected, timeout=120)
        docker("network", "rm", network, timeout=120)
        apg("dev", "down", "--project", PROJECT)


def client_run(served: dict[str, Any], **environment: str) -> subprocess.CompletedProcess[str]:
    """The generated client, in the toolchain image, reading its environment
    from a `0600` file rather than from `-e NAME=VALUE` (which `docker inspect`
    and `ps` both show)."""
    env_file = served["work"] / f"smoke-{secrets.token_hex(4)}.env"
    env_file.write_text(
        "".join(f"{key}={value}\n" for key, value in environment.items()), encoding="utf-8"
    )
    env_file.chmod(0o600)
    return docker(
        "run", "--rm", "--network", served["network"],
        "--env-file", str(env_file),
        "-v", f"{CLIENT}:/work:ro", served["image"], "smoke",
    )  # fmt: skip


def steps(done: subprocess.CompletedProcess[str]) -> dict[str, dict[str, Any]]:
    """The smoke's JSON lines, by step. Parsed, never matched as prose."""
    found: dict[str, dict[str, Any]] = {}
    for line in done.stdout.splitlines():
        if line.startswith("{"):
            entry = json.loads(line)
            found[entry["step"]] = entry
    assert found, f"the client printed no step at all:\n{done.stdout}\n{done.stderr}"
    return found


# ---------------------------------------------------------------------------
# GEN-HASH-001 -- the offline half
# ---------------------------------------------------------------------------


@requires_docker
def test_init_accepts_the_served_surface_it_was_generated_from(served: dict[str, Any]) -> None:
    """**GEN-HASH-001.** The chain closes: capture, client, live service.

    The number is arrived at TWO WAYS in one assertion -- computed here from the
    committed snapshot by `openapi_normalize.fingerprint`, and computed inside
    the container by the emitted `canonical.ts` over the document the service
    actually served, through the product's own edge, as the caller.

    Rig 23a measured that the `authenticated` role is served exactly the
    capture. This is that fact, made a proof, with the client as the instrument.
    """
    done = client_run(served, APG_REST_URL=served["rest_url"], APG_TOKEN=served["authenticated"])
    found = steps(done)

    assert found["init"]["kind"] == "ok", (
        f"init did not accept the surface it was generated from: {found['init']}\n{done.stderr}"
    )
    assert served["fingerprint"] == (
        "808ac715c09aeebc382dd5afc886c1680fe2ea9870e729b9d34a623dee8d18de"
    ), "the committed snapshot's fingerprint moved; rig 23a measured this value being served"
    assert done.returncode == 0, (
        f"a run with no write attempted should exit 0: {done.stdout}\n{done.stderr}"
    )
    assert found["done"]["ok"] is True


@requires_docker
def test_init_refuses_a_surface_with_another_fingerprint_naming_both(
    served: dict[str, Any],
) -> None:
    """**GEN-HASH-001.** A different surface is `stale_contract`, with BOTH digests.

    The same service, the same edge, the same client -- only the token's role
    differs, so `anon` is served a document with no paths at all. "They differ"
    without the values sends the reader to source; naming both says which way.

    And the refusal is total: after it, every other call answers
    `not_initialised` rather than being attempted against a surface the client
    cannot vouch for.
    """
    done = client_run(served, APG_REST_URL=served["rest_url"], APG_TOKEN=served["anon"])
    found = steps(done)

    assert found["init"]["kind"] == "stale_contract", found["init"]
    assert found["init"]["expected"] == served["fingerprint"]
    assert found["init"]["served"] != served["fingerprint"]
    assert len(found["init"]["served"]) == 64
    assert done.returncode == 1
    assert "read" not in found, (
        "the client went on to read after refusing the surface; the refusal is what stops "
        "every later call"
    )


@requires_docker
def test_init_separates_unreachable_from_a_document_it_cannot_read(
    served: dict[str, Any],
) -> None:
    """**GEN-HASH-001**, ADR 0195's three outcomes against a real service.

    Three distinct answers, none folded into another:

    * nothing listening -> `unreachable`. A client that could not reach a
      service knows NOTHING about its contract, and reporting that as a stale
      contract would send an operator to re-capture a snapshot that was already
      right.
    * the right service at the WRONG path -> also `unreachable`, because the
      edge answers 404: there is no document to judge.
    * the right service at its own root, where the document IS served but
      describes a different base -> `unparsable`, naming the mismatch.

    The third is the interesting one: the service answered, the document parsed,
    and it still is not the one this client was pointed at.
    """
    nothing = client_run(
        served, APG_REST_URL="http://127.0.0.1:9/", APG_TOKEN=served["authenticated"]
    )
    assert steps(nothing)["init"]["kind"] == "unreachable", steps(nothing)["init"]

    wrong_path = client_run(
        served,
        APG_REST_URL=f"{served['rest_url']}/not-the-api",
        APG_TOKEN=served["authenticated"],
    )
    assert steps(wrong_path)["init"]["kind"] == "unreachable", steps(wrong_path)["init"]

    direct = client_run(
        served, APG_REST_URL=served["direct_url"], APG_TOKEN=served["authenticated"]
    )
    init = steps(direct)["init"]
    assert init["kind"] == "unparsable", init
    assert "basePath" in init["reason"], init
    assert "expected" not in init and "served" not in init, (
        "a document the client could not read has no fingerprint to name"
    )


# ---------------------------------------------------------------------------
# GEN-TYPES-001
# ---------------------------------------------------------------------------


@requires_docker
def test_a_typed_read_returns_rows_of_the_declared_shape(served: dict[str, Any]) -> None:
    """**GEN-TYPES-001.** A generated read reaches the real surface and answers `ok`.

    **Empty is the correct result and the shape is the claim.** The token names
    a role and no subject, so migration 0013's hook sets no `app.user_id` and
    every owner-scoped policy matches nothing. A read that returned rows here
    would mean the policy was not applied.

    The control is in the same run: the write below is refused while this
    succeeds, so a rig that refused everything could not produce this pair.
    """
    done = client_run(served, APG_REST_URL=served["rest_url"], APG_TOKEN=served["authenticated"])
    found = steps(done)

    assert found["init"]["kind"] == "ok"
    assert found["read"]["kind"] == "ok", f"a typed read was refused: {found['read']}"
    assert found["read"]["rows"] == 0, (
        "a token naming no subject read rows; the owner policy was not applied"
    )


@requires_docker
def test_a_refused_write_arrives_as_the_pt_code_the_database_raised(
    served: dict[str, Any],
) -> None:
    """**GEN-TYPES-001.** The product's own errcode reaches the caller as a value.

    `create_note` without an identity: the hook sets no subject, the function
    raises `AP401` with `ERRCODE = PT401`, PostgREST maps it to 401, and the
    client classifies it as `{kind: "refused", code: "PT401"}` -- not as a
    thrown transport error, and not as a bare status. `PT401` is in the union
    the generator scanned out of `migrations/templates/` (ADR 0139).

    **The control is the read in the same invocation**, which answers `ok`: a
    rig that refused everything would pass a refusal test for the wrong reason.
    """
    done = client_run(
        served,
        APG_REST_URL=served["rest_url"],
        APG_TOKEN=served["authenticated"],
        APG_SMOKE_ALLOW_WRITE="1",
    )
    found = steps(done)

    assert found["read"]["kind"] == "ok", "the control read must succeed beside the refusal"
    assert found["rpc"]["kind"] == "refused", f"the write was not refused: {found['rpc']}"
    assert found["rpc"]["code"] == "PT401", (
        f"the refusal carried {found['rpc'].get('code')!r}, not the PT code the database "
        "raised. A client reporting a bare status loses the product's own vocabulary"
    )

    from agentic_postgres import client_ir

    ir = json.loads((CLIENT / "generated.json").read_text(encoding="utf-8"))
    assert "PT401" in ir["pt_codes"], "the code the service raised is not in the generated union"
    assert client_ir.PT_CODE_PATTERN.match(found["rpc"]["code"])


@requires_docker
def test_a_filter_value_is_a_value_and_never_query_syntax(served: dict[str, Any]) -> None:
    """**GEN-TYPES-001**, ADR 0127 at the client.

    The probe value carries `&select=` -- the shape that, unencoded, stops being
    a value and becomes two query parameters, the second naming a column the
    relation does not have. PostgREST answers that with `400 PGRST` and a
    message about the column; percent-encoded, it is an ordinary filter that
    matches nothing and answers 200.

    So the two outcomes are far apart and neither is a coincidence: `ok` means
    the value was encoded, and `refused` with a 400 means it was concatenated
    into the query string. The battery removes `encodeURIComponent` from the
    emitter and this is what goes red.

    The unfiltered read in the same invocation is the control -- it answers `ok`
    either way, so a rig that had simply stopped serving could not produce this
    pair.
    """
    done = client_run(
        served,
        APG_REST_URL=served["rest_url"],
        APG_TOKEN=served["authenticated"],
        APG_SMOKE_FILTER_VALUE="probe&select=no_such_column",
    )
    found = steps(done)

    assert found["read"]["kind"] == "ok", "the control read must succeed beside the filtered one"
    assert found["filter"]["kind"] == "ok", (
        f"a filter value containing `&select=` was not sent as a VALUE: {found['filter']}. "
        "Unencoded it becomes a second query parameter, which is the injection ADR 0127 "
        "exists to make impossible"
    )
    assert found["filter"]["relation"] == "notes"
    assert found["filter"]["column"] == "title"


@requires_docker
def test_nothing_any_container_prints_is_the_token(served: dict[str, Any]) -> None:
    """**GEN-TYPES-001**, D105. The one value the client holds never appears.

    Over the client's own streams AND the services' logs: a token in a server
    log is a token in a support bundle. The assertion is on the whole token and
    on a distinctive prefix of it, because a truncated one is still a leak of
    the part that matters.
    """
    token = served["authenticated"]
    done = client_run(
        served,
        APG_REST_URL=served["rest_url"],
        APG_TOKEN=token,
        APG_SMOKE_ALLOW_WRITE="1",
    )
    printed = done.stdout + done.stderr
    assert token not in printed
    assert token[:40] not in printed, "a prefix of the token reached the client's output"

    for name in served["containers"]:
        logs = docker("logs", name)
        stream = logs.stdout + logs.stderr
        assert token not in stream, f"{name} logged the caller's token"
        assert token[:40] not in stream, f"{name} logged a prefix of the caller's token"

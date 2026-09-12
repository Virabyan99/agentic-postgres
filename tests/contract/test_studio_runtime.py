"""`STU-*`'s positive halves -- Studio against a deployment, not against a shape.

`test_studio_server.py` proves the server's own rules with a stand-in, because
those rules are about the socket and a deployment would cost three minutes per
assertion. **This module is the other half and it is the one that counts.**
Every proof here launches `bin/studio.sh` as a subprocess against a real cluster
with real migrations, the real auth application issuing real tokens, real
PostgREST verifying them against the application's own published JWKS, and the
real edge in front -- and then drives it the way the page drives it, over a
socket, with the launch cookie and the custom header and nothing else.

**The rig is rig 24b** (Session 24 Run 1), and three of its measurements are
what make the fixture possible at all:

* `openapi_normalize.normalize` refuses `schemes: ["http"]` outright (D1261), so
  a loopback rig cannot simply announce the scheme it is actually reached over.
  What works is a proxy URI naming the **loopback host with the https scheme** --
  the field describes the address a caller was told to use, the transport stays
  cleartext on `127.0.0.1`, and `published_address` derives the same pair from
  `routes.rest.url`. Arm C measured that the served document then normalizes to
  exactly the committed snapshot's fingerprint.
* `fingerprint()` does not normalize and the committed snapshot already is
  normalized (D1260), which is why `surface_answer` takes the expected address.
  A rig that got this wrong would have reported `stale_contract` here and the
  product would have been "fixed" to match it.
* the edge must start **before** PostgREST, because the proxy URI has to name
  the published port and Docker does not choose one until the container runs.
  Traefik's file provider resolves its backend by DNS per request, so a service
  named in the dynamic file and started afterwards is reached.

**One superuser action, named as a rig's** (ADR 0066): `apg dev` activates two
roles by decision (ADR 0203) and neither the authenticator nor the auth service
is one of them, so this rig gives both a password -- through `docker exec`
stdin, never an argument (D1160).

**Marked, and the marks are load-bearing** (D1240).
"""

# ruff: noqa: S608 -- the SQL below is the rig's own, run as the superuser over
# `docker exec` stdin against a throwaway cluster, and every value interpolated
# into it is a uuid this module generated. There is no caller to inject and no
# parameterised route into a psql invocation.

from __future__ import annotations

import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid as uuid_module
import warnings
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_image_contracts import requires_docker
from tests.contract.test_studio_server import Launched, StandIn

from agentic_postgres import REPO_ROOT, studio

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.database, pytest.mark.security]

APG = REPO_ROOT / "bin" / "apg.sh"
STUDIO = REPO_ROOT / "bin" / "studio.sh"
PROJECT_FILE = REPO_ROOT / "project.example.yaml"
PROJECT = "project.example.yaml"
KEY = "fixture-alpha-dev"
FIXTURE = REPO_ROOT / ".generated" / KEY
SNAPSHOT = REPO_ROOT / "projects" / "example" / "contracts" / "postgrest-openapi.canonical.json"

#: The administrator this rig bootstraps. Holds every administrative scope the
#: Studio views need -- including `admin_audit:read`, which `ada` deliberately
#: does NOT hold in `test_auth_endpoints.py` because that module's subject is
#: the scope check itself. Here the scope check is not the subject; what a
#: subject who HAS the authority sees is.
ADMIN_SCOPES = [
    "admin_agents:read",
    "admin_agents:write",
    "admin_audit:read",
    "admin_users:read",
    "admin_users:write",
    "notes:read",
]
PASSPHRASE = "a-correct-horse-battery-staple"  # noqa: S105

#: A value stored in a note and then asked for two ways (D1250). It is PostgREST
#: syntax: a comma, a dot, brackets and an `&`. Sent as a filter value it must
#: find nothing; stored in a row it must be found by `eq`, and the pair is what
#: separates "the encoding works" from "the query returned nothing".
SYNTAX_VALUE = "a,b)or(1=1&limit=99"


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


def answers(host: str, port: int, *, seconds: float = 20.0) -> bool:
    """Can this process open a TCP connection there? Asked, never assumed."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def cluster_address(container: str, recorded: int | None) -> tuple[str, int, str]:
    """An address for the dev cluster that THIS process can actually reach.

    Two candidates and a probe, because the answer differs by machine:

    * the published port. `apg dev up` publishes `127.0.0.1:0:5432` by decision
      (D1175) -- the port exists on loopback and nowhere else, which is the
      right decision for a developer's machine and depends on a host-to-loopback
      DNAT that a daemon can be configured not to make work. On the CI runner it
      does not: Run 4's fixture reached the same container with `docker exec`
      and could not open its published port.
    * the container's own address on its network, read from the container.
      Reachable from the host on a Linux bridge, and unaffected by how the port
      was published.

    Returns the host, the port and which candidate answered, so the caller can
    say it rather than discover it again.
    """
    published = docker("port", container, "5432", timeout=60)
    port = recorded
    if published.returncode == 0 and ":" in published.stdout:
        port = int(published.stdout.splitlines()[0].rsplit(":", 1)[1])
    if port is not None and answers("127.0.0.1", port, seconds=20):
        return "127.0.0.1", port, "the published port"

    inspected = docker(
        "inspect",
        "--format",
        "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
        container,
        timeout=60,
    )
    for address in inspected.stdout.split():
        if answers(address, 5432, seconds=10):
            return address, 5432, "the container's own address"

    pytest.fail(
        f"the dev cluster {container} is running -- `docker exec psql` reaches it -- and "
        f"this process can open neither its published port ({published.stdout.strip() or 'none'}, "
        f"recorded {recorded}) nor any of its container addresses "
        f"({inspected.stdout.strip() or 'none'}). A rig that went on from here would spend "
        "five minutes in a pool timeout and report it as an application fault"
    )
    raise AssertionError("unreachable")


def http(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, bytes]:
    """One request, as a caller of the deployment. Never as Studio."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, TimeoutError) as error:
        return 0, str(getattr(error, "reason", error)).encode("utf-8")


# ---------------------------------------------------------------------------
# the rig
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def studio_rig(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """A deployment on loopback, and the deployed document that names it.

    Module scope, and the cost is stated rather than hidden: rig 24b measured
    40 s to this point on this workstation, of which `apg dev up` is 16 s. That
    is D1211's price restated -- PostgREST beside `apg dev` is a rig and not a
    verb, and a rig this expensive is built once per module or not at all.

    Everything is removed in `finally`, including the network, which a
    left-behind container would otherwise pin.
    """
    if not (FIXTURE / "compose.env").is_file():
        pytest.skip("the fixture project is not rendered in this checkout")

    work = tmp_path_factory.mktemp("studio-runtime")
    work.chmod(0o755)
    suffix = secrets.token_hex(3)
    network = f"apg-studio-rt-{suffix}"
    containers: list[str] = []
    connected: str | None = None
    server: Any = None
    previous_environment = dict(os.environ)

    apg("dev", "down", "--project", PROJECT)
    started_at = time.monotonic()
    up = apg("dev", "up", "--project", PROJECT)
    assert up.returncode == 0, f"`apg dev up` exited {up.returncode}\n{up.stdout}\n{up.stderr}"

    try:
        from agentic_postgres import dev_environment

        state = json.loads(
            (dev_environment.state_dir(KEY) / dev_environment.STATE_FILE).read_text(
                encoding="utf-8"
            )
        )
        document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
        resolved: dict[str, str] = {}
        for line in (FIXTURE / "compose.env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                name, value = line.split("=", 1)
                resolved[name] = value

        roles = document["database"]["roles"]
        database = state["database"]
        container = state["container"]
        rest_path = resolved["API_REST_PATH"]

        def su(sql: str, db: str | None = None):
            return docker(
                "exec", "-i", container,
                "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-d", db or database,
                stdin=sql,
            )  # fmt: skip

        authenticator = roles["postgrest_authenticator"]
        auth_role = roles["auth_service"]
        authenticator_password = secrets.token_hex(24)
        auth_password = secrets.token_hex(24)
        altered = su(
            f"ALTER ROLE \"{authenticator}\" LOGIN PASSWORD '{authenticator_password}';\n"
            f"ALTER ROLE \"{auth_role}\" LOGIN PASSWORD '{auth_password}';\n",
            db="postgres",
        )
        assert altered.returncode == 0, altered.stderr

        from app.hashing import Hasher

        scopes = ",".join(f"'{scope}'" for scope in ADMIN_SCOPES)
        made = su(
            f'SET ROLE "{roles["object_owner"]}"; '
            "SELECT app_private.auth_bootstrap_administrator("
            f"'ada', 'Ada Lovelace', '{roles['project_admin']}', "
            f"ARRAY[{scopes}]::text[], '{Hasher().hash(PASSPHRASE)}')"
        )
        assert made.returncode == 0, made.stderr

        # -- the auth application, on its own loopback socket ------------------
        # -- the network FIRST, then the address -------------------------------
        #
        # Attaching a running container to a second network is the last thing
        # here that can change how this process reaches it, and on the CI
        # runner's daemon it changes it completely: the published port answers
        # a probe before this and refuses a connection after (D1276). So the
        # topology is built first and the address is proved in it.
        created = docker("network", "create", network)
        assert created.returncode == 0, created.stderr
        joined = docker(
            "network", "connect", "--alias", resolved["POSTGRES_SERVICE_HOST"], network, container
        )
        assert joined.returncode == 0, joined.stderr
        connected = container

        cluster_host, cluster_port, how = cluster_address(container, state.get("port"))
        if how != "the published port":
            warnings.warn(
                f"studio_rig reached the dev cluster at {cluster_host}:{cluster_port} via "
                f"{how}: its published port was not reachable from this process once the "
                "container had joined the rig's network. That is a property of this "
                "machine's daemon, not of the product (D1276)",
                stacklevel=1,
            )

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        signing_key = work / "signing.pem"
        signing_key.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        signing_key.chmod(0o600)

        passfile = work / "pgpass"
        passfile.write_text(f"*:*:*:*:{auth_password}\n", encoding="utf-8")
        passfile.chmod(0o600)

        from agentic_postgres import (
            api_surface,
            capability_compiler,
            scope_registry,
        )

        project_surface = api_surface.load_project_surface(
            api_surface.project_contract_path(REPO_ROOT / "projects" / "example")
        )
        merged = api_surface.merged_surface(api_surface.load_surface(), project_surface)
        lock = capability_compiler.compile_lock(
            canonical=json.loads(
                (
                    REPO_ROOT
                    / "contracts"
                    / "snapshots"
                    / "mcp"
                    / "mcp-capabilities.canonical.json"
                ).read_text(encoding="utf-8")
            ),
            project_key=KEY,
            upstream="https://alpha.example.test/api/rest",
            sources={
                "capabilities_sha256": "0" * 64,
                "api_surface_sha256": "0" * 64,
                "canonical_openapi_sha256": "0" * 64,
            },
            vocabulary=scope_registry.vocabulary_block(merged),
        )
        lock_path = work / "capability-lock.json"
        lock_path.write_text(
            capability_compiler.canonical_bytes(lock).decode("utf-8"), encoding="utf-8"
        )

        os.environ.update(
            {
                "APG_MCP_LOCK_FILE": str(lock_path),
                "APG_PROJECT_KEY": KEY,
                "APG_PROJECT_ENVIRONMENT": "dev",
                "APG_JWT_ISSUER": document["jwt"]["issuer"],
                "APG_JWT_AUDIENCE": document["jwt"]["audience"],
                "APG_DATABASE_HOST": cluster_host,
                "APG_DATABASE_PORT": str(cluster_port),
                "APG_DATABASE_NAME": database,
                "APG_DATABASE_ROLE": auth_role,
                "APG_DATABASE_PASSFILE": str(passfile),
                "APG_POOL_SIZE": "4",
                "APG_SIGNING_KEY_FILE": str(signing_key),
                "APG_LISTEN_PORT": "8080",
                "APG_ROLE_NAMES": json.dumps(
                    {
                        name: roles[name]
                        for name in (
                            "anon",
                            "authenticated",
                            "agent_reader",
                            "agent_writer",
                            "project_admin",
                        )
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            }
        )

        import uvicorn

        from app import main as main_module

        config = uvicorn.Config(
            main_module.create_app("auth"), host="127.0.0.1", port=0, log_level="warning"
        )
        server = uvicorn.Server(config)
        threading.Thread(target=server.run, daemon=True).start()
        deadline = time.monotonic() + 90
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started, "the auth application never started"
        # Rig 24a measured this attribute at the pinned uvicorn: a server bound
        # to port 0 reports the port the kernel chose here and nowhere else.
        app_port = server.servers[0].sockets[0].getsockname()[1]
        app_url = f"http://127.0.0.1:{app_port}"

        status, raw = http("GET", f"{app_url}/auth/jwks.json")
        assert status == 200, raw[:300]
        jwks = work / "jwks.json"
        jwks.write_bytes(raw)
        jwks.chmod(0o644)

        # -- the edge, then PostgREST ------------------------------------------
        # The network already exists and the cluster is already on it; what is
        # left is the order the edge and PostgREST have to start in, which is
        # the edge first: the proxy URI has to name the published port and
        # Docker does not choose one until the container runs.
        (work / "dynamic").mkdir()
        (work / "traefik.yaml").write_text(
            "entryPoints:\n  web:\n    address: ':8080'\n"
            "providers:\n  file:\n    directory: /etc/traefik/dynamic\n    watch: false\n"
            "log:\n  level: ERROR\n",
            encoding="utf-8",
        )
        (work / "dynamic" / "rest.yaml").write_text(
            "http:\n  routers:\n    rest:\n"
            f'      rule: "PathPrefix(`{rest_path}`)"\n'
            "      entryPoints: [web]\n      middlewares: [strip]\n      service: rest\n"
            "  middlewares:\n    strip:\n      stripPrefix:\n"
            f'        prefixes: ["{rest_path}"]\n'
            "  services:\n    rest:\n      loadBalancer:\n        servers:\n"
            '          - url: "http://postgrest:3000"\n',
            encoding="utf-8",
        )
        for path in (work / "traefik.yaml", work / "dynamic" / "rest.yaml"):
            path.chmod(0o644)
        (work / "dynamic").chmod(0o755)

        edge = f"apg-studio-rt-edge-{suffix}"
        made = docker(
            "run", "-d", "--name", edge, "--network", network, "--network-alias", "edge",
            "-p", "127.0.0.1:0:8080",
            "-v", f"{work / 'traefik.yaml'}:/etc/traefik/traefik.yaml:ro",
            "-v", f"{work / 'dynamic'}:/etc/traefik/dynamic:ro",
            locked("TRAEFIK_IMAGE"),
        )  # fmt: skip
        assert made.returncode == 0, made.stderr
        containers.append(edge)
        time.sleep(4)

        published = docker("port", edge, "8080")
        assert published.stdout.strip(), f"the edge published no port: {published.stderr}"
        edge_port = int(published.stdout.splitlines()[0].rsplit(":", 1)[1])
        rest_url = f"http://127.0.0.1:{edge_port}{rest_path}"

        import yaml

        compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
        overrides = {
            "POSTGREST_AUTHENTICATOR_ROLE": authenticator,
            "POSTGRES_DATABASE_NAME": database,
            "ANON_ROLE_NAME": roles["anon"],
            **resolved,
        }
        pattern = re.compile(r"\$\{([A-Z0-9_]+)(?:[:?][^}]*)?\}")
        values: dict[str, str] = {}
        for name, raw_value in compose["services"]["postgrest"]["environment"].items():
            text = "" if raw_value is None else str(raw_value)
            substituted = pattern.sub(lambda match: overrides[match.group(1)], text)
            assert "${" not in substituted, f"{name}: {substituted}"
            values[name] = substituted
        values["PGRST_DB_URI"] = (
            f"postgres://{authenticator}@{resolved['POSTGRES_SERVICE_HOST']}:5432/"
            f"{database}?passfile=/run/secrets/postgrest_authenticator_pgpass"
        )
        # **The https scheme over a loopback host** (D1261). `normalize` refuses
        # `schemes: ["http"]`, and `published_address` derives the expected pair
        # from `routes.rest.url` -- so the document has to publish this host with
        # that scheme for the two to agree. The transport is still cleartext to
        # 127.0.0.1 and never leaves this machine.
        values["PGRST_OPENAPI_SERVER_PROXY_URI"] = f"https://127.0.0.1:{edge_port}{rest_path}"
        # Not a secret: the `@file` form names the JWKS the auth application
        # publishes, which is a PUBLIC key. The private half never leaves the
        # application's own process.
        values["PGRST_JWT_SECRET"] = "@/etc/postgrest/jwks.json"  # noqa: S105
        values.setdefault("PGRST_SERVER_HOST", "0.0.0.0")  # noqa: S104
        values.setdefault("PGRST_SERVER_PORT", "3000")
        values["PGRST_ADMIN_SERVER_HOST"] = "127.0.0.1"
        values["PGRST_ADMIN_SERVER_PORT"] = "3001"
        values["PGRST_LOG_LEVEL"] = "error"

        pgpass = work / "rest-pgpass"
        pgpass.write_text(f"*:*:*:{authenticator}:{authenticator_password}\n", encoding="utf-8")
        pgpass.chmod(0o600)
        inspected = docker(
            "inspect", "--format", "{{.Config.User}}", locked("POSTGREST_IMAGE"), timeout=120
        )
        rest_uid = (inspected.stdout.strip() or "0").split(":", 1)[0]
        # D1233: the file has to belong to the uid the image declares, or libpq
        # reports a permission fault as "no password supplied".
        owned = docker(
            "run", "--rm", "-v", f"{work}:/w", locked("PYTHON_RUNTIME_IMAGE"),
            "sh", "-c", f"chown {rest_uid}:{rest_uid} /w/rest-pgpass && chmod 600 /w/rest-pgpass",
            timeout=300,
        )  # fmt: skip
        assert owned.returncode == 0, owned.stderr

        env_file = work / "postgrest.env"
        env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
        env_file.chmod(0o600)

        rest = f"apg-studio-rt-rest-{suffix}"
        made = docker(
            "run", "-d", "--name", rest, "--network", network, "--network-alias", "postgrest",
            "--env-file", str(env_file),
            "-v", f"{pgpass}:/run/secrets/postgrest_authenticator_pgpass:ro",
            "-v", f"{jwks}:/etc/postgrest/jwks.json:ro",
            locked("POSTGREST_IMAGE"),
        )  # fmt: skip
        assert made.returncode == 0, made.stderr
        containers.append(rest)

        deadline = time.monotonic() + 120
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
        time.sleep(2)

        # -- the human subjects, through the product's own endpoints -----------
        status, raw = http(
            "POST", f"{app_url}/auth/login", body={"username": "ada", "password": PASSPHRASE}
        )
        assert status == 200, raw[:300]
        admin_token = json.loads(raw)["access_token"]

        subjects: dict[str, dict[str, Any]] = {}
        for who, notes in (("alpha-user-a", 2), ("beta-user-b", 1)):
            password = f"{secrets.token_hex(12)}-Aa1!"
            status, raw = http(
                "POST", f"{app_url}/admin/users", token=admin_token,
                body={
                    "username": who, "display_name": who.upper(), "role": "authenticated",
                    "scopes": ["notes:read"], "password": password,
                },
            )  # fmt: skip
            assert status == 201, f"{status} {raw[:300]}"
            user_id = json.loads(raw)["user_id"]
            status, raw = http(
                "POST", f"{app_url}/auth/login", body={"username": who, "password": password}
            )
            assert status == 200, raw[:300]
            token = json.loads(raw)["access_token"]
            for index in range(notes):
                # `api.create_note(p_title, p_content)`. The parameter names are
                # the surface's, corrected once by PGRST202's own hint.
                title = SYNTAX_VALUE if (who == "alpha-user-a" and index == 0) else f"note-{index}"
                status, raw = http(
                    "POST", f"{rest_url}/rpc/create_note", token=token,
                    body={"p_title": title, "p_content": "x"},
                )  # fmt: skip
                assert status in (200, 201, 204), f"{status} {raw[:300]}"
            password_file = work / f"password-{who}"
            password_file.write_text(password + "\n", encoding="utf-8")
            password_file.chmod(0o600)
            subjects[who] = {
                "user_id": user_id,
                "password": password,
                "password_file": password_file,
                "token": token,
                "notes": notes,
            }

        admin_password_file = work / "password-ada"
        admin_password_file.write_text(PASSPHRASE + "\n", encoding="utf-8")
        admin_password_file.chmod(0o600)

        outputs = work / "outputs.json"
        outputs.write_text(
            json.dumps(
                {
                    "document_kind": "deployed",
                    "routes": {
                        "rest": {"status": "ready", "url": rest_url},
                        "app": {"status": "ready", "url": app_url},
                    },
                }
            ),
            encoding="utf-8",
        )

        yield {
            "work": work,
            "app_url": app_url,
            "rest_url": rest_url,
            "rest_path": rest_path,
            "outputs": outputs,
            "admin_token": admin_token,
            "admin_password_file": admin_password_file,
            "subjects": subjects,
            "roles": roles,
            "psql": su,
            "database": database,
            "seconds": time.monotonic() - started_at,
            "cluster_address": f"{cluster_host}:{cluster_port} via {how}",
        }
    finally:
        if server is not None:
            server.should_exit = True
            time.sleep(1)
        for name in containers:
            docker("rm", "-f", "-v", name, timeout=120)
        if connected:
            docker("network", "disconnect", "-f", network, connected, timeout=120)
        docker("network", "rm", network, timeout=120)
        apg("dev", "down", "--project", PROJECT)
        os.environ.clear()
        os.environ.update(previous_environment)


def launch(rig: dict[str, Any], username: str, password_file: Path, outputs: Path | None = None):
    """`bin/studio.sh`, as a subprocess, against this rig (D1114).

    The product's own command with the product's own wrapper -- not `main()`
    called in-process, which would skip the argument parsing, the password
    file's mode check and the signal handlers, all three of which are the
    subject of a proof somewhere.
    """
    process = subprocess.Popen(
        [
            str(STUDIO), "--project", str(PROJECT_FILE),
            "--outputs", str(outputs or rig["outputs"]),
            "--username", username, "--password-file", str(password_file),
        ],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip

    deadline = time.monotonic() + 60
    url = ""
    lines: list[str] = []
    while time.monotonic() < deadline:
        line = process.stdout.readline() if process.stdout else ""
        if not line:
            if process.poll() is not None:
                break
            continue
        lines.append(line.rstrip("\n"))
        if "open http://" in line:
            url = line.split("open ", 1)[1].strip()
            break
    if not url:
        process.kill()
        stderr = process.stderr.read() if process.stderr else ""
        pytest.fail(f"studio printed no URL. stdout={lines} stderr={stderr[:1200]}")
    return Launched(process, url, lines)


def stop(started: Launched, *, signal_number: int = signal.SIGTERM) -> str:
    """End a launch and return everything it wrote to stderr."""
    started.process.send_signal(signal_number)
    try:
        started.process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        started.process.kill()
        started.process.wait(timeout=10)
    out = started.process.stdout.read() if started.process.stdout else ""
    err = started.process.stderr.read() if started.process.stderr else ""
    started.lines.extend(out.splitlines())
    return err


def json_call(started: Launched, method: str, path: str, payload: Any = None):
    """One page call, and its parsed body. `Launched.call` is the browser."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else None
    status, response_headers, raw = started.call(method, path, headers=headers, body=body)
    try:
        return status, response_headers, json.loads(raw)
    except json.JSONDecodeError:
        return status, response_headers, raw


@pytest.fixture
def as_admin(studio_rig: dict[str, Any]) -> Any:
    """A Studio launched as the administrator, ended however the test ends.

    Its surface answer is `stale_contract` and that is CORRECT -- see
    `test_an_administrators_surface_is_the_one_their_grants_reach`. The views
    this fixture is used for are the application's, which no REST contract
    gates.
    """
    started = launch(studio_rig, "ada", studio_rig["admin_password_file"])
    try:
        yield started
    finally:
        stop(started)


@pytest.fixture
def as_user(studio_rig: dict[str, Any]) -> Any:
    """A Studio launched as an ORDINARY subject -- the role the capture is of.

    `authenticated`, because that is whose document
    `projects/example/contracts/postgrest-openapi.canonical.json` is: rig 23a
    measured it, rig 24d measured that no other role is served the same one.
    """
    started = launch(
        studio_rig, "alpha-user-a", studio_rig["subjects"]["alpha-user-a"]["password_file"]
    )
    try:
        yield started
    finally:
        stop(started)


# ---------------------------------------------------------------------------
# STU-SURFACE-001 -- the four launch answers
# ---------------------------------------------------------------------------


@requires_docker
def test_launch_answers_ok_against_the_surface_the_ir_was_built_from(
    studio_rig: dict[str, Any], as_user: Launched
) -> None:
    """**STU-SURFACE-001.** The chain closes: capture, IR, deployment, Studio.

    The digest is arrived at two ways in one assertion -- by `client_ir.build`
    from the four committed inputs inside the Studio process, and by PostgREST
    serving a document to this human's own application-issued token, normalized
    against the address the deployed document publishes. Rig 23a measured that
    equality for a role token; rig 24b measured it for a token the auth service
    issued, which is the one Studio actually holds.

    **As an `authenticated` subject, and the role is the point** (D1275). The
    committed capture is that role's document; rig 24d measured that no other
    role is served it. The administrator's answer is the next proof.
    """
    status, _, state = json_call(as_user, "GET", "/__apg/state")
    assert status == 200, state

    assert state["surface"]["answer"] == "ok", (
        f"the launch did not confirm the surface: {state['surface']}. The rig serves the "
        "committed snapshot through the product's own edge, so anything but ok here is "
        "Studio's comparison being wrong rather than the deployment's document"
    )
    assert state["surface"]["served_sha256"] == state["surface"]["expected_sha256"]
    assert state["surface"]["served_sha256"] == (
        "808ac715c09aeebc382dd5afc886c1680fe2ea9870e729b9d34a623dee8d18de"
    ), "the committed snapshot's fingerprint moved; rigs 23a and 24b both measured this value"
    assert state["subject"] == "alpha-user-a"
    assert state["own_session_known"] is True

    schema_status, _, schema = json_call(as_user, "GET", "/__apg/schema")
    assert schema_status == 200, schema
    assert schema["relations"], "the schema view names no relation"


@requires_docker
def test_an_administrators_surface_is_the_one_their_grants_reach(
    studio_rig: dict[str, Any], as_admin: Launched
) -> None:
    """**STU-SURFACE-001**, D1275 -- the served document is scoped to the caller.

    Rig 24d, one URL and three tokens: `authenticated` is served eight paths and
    three definitions and equals the capture; `project_admin` is served ONE path
    and no definitions, byte for byte the same document as `anon`, because the
    administrative role administers the auth service's endpoints and holds
    nothing in `api`.

    So an administrator's launch answers `stale_contract`, and it is right to.
    The answer means *the surface served to this subject is not the captured
    one*, which is the same meaning Session 23's client has -- that module
    produces the answer by changing only the token's role.

    **What this proof is really guarding is the sentence.** One answer with two
    causes, only one of which was named, is ADR 0195's folded outcome in the
    reassuring direction: an operator told to regenerate would have regenerated
    a capture that was exactly right. The launch line now names both, and this
    asserts it does.

    The control is above: the same rig, the same deployment, the same command,
    an `authenticated` subject -- `ok`.
    """
    status, _, state = json_call(as_admin, "GET", "/__apg/state")
    assert status == 200, state
    assert state["subject"] == "ada"
    assert state["surface"]["answer"] == "stale_contract", state["surface"]
    assert state["surface"]["served_sha256"] != state["surface"]["expected_sha256"]

    schema_status, _, refusal = json_call(as_admin, "GET", "/__apg/schema")
    assert schema_status == 409, (schema_status, refusal)

    printed = "\n".join(as_admin.lines)
    assert "stale_contract" in printed, printed
    assert "bin/apg.sh generate" in printed, (
        f"the launch line does not name the regeneration half: {printed}"
    )
    assert "role" in printed and "anonymous document" in printed, (
        "the launch line names only the stale-capture cause. An administrator reading it "
        f"would regenerate a capture that is correct (D1275): {printed}"
    )

    # And the views an administrator actually came for are unaffected, which is
    # why the two contracts have to stay apart.
    assert json_call(as_admin, "GET", "/__apg/audit")[2]["status"] == "ok"
    assert json_call(as_admin, "GET", "/__apg/agents")[2]["status"] == "ok"


@requires_docker
def test_launch_answers_stale_contract_naming_both_digests_and_refuses_the_rest_views(
    studio_rig: dict[str, Any], tmp_path: Path
) -> None:
    """**STU-SURFACE-001.** A different document is `stale_contract`, and the split holds.

    The stand-in serves the same document with ONE description changed, at its
    own address, so it normalizes cleanly and differs only in the digest -- which
    is the case a caller cannot detect any other way, and the case a fingerprint
    exists for.

    Then the half this proof is really about: the REST views are refused and the
    **application views are not**. `/admin/audit` is served by the auth service
    over the release's own migrations; a REST contract this checkout disagrees
    with says nothing about it, and folding the two would make one stale capture
    hide every denial in the record.
    """
    double = StandIn()
    double.start()
    try:
        served = double.document()
        paths = served.get("paths") or served.get("definitions") or {}
        assert paths, "the snapshot the double serves has nothing to perturb"
        blob = json.dumps(served)
        assert '"description"' in blob, "the snapshot carries no description to change"
        mutated = json.loads(re.sub(r'("description"\s*:\s*")', r"\1x", blob, count=1))
        assert mutated != served
        double.answers[f"{studio_rig['rest_path']}/"] = (200, json.dumps(mutated).encode("utf-8"))

        outputs = tmp_path / "stale-outputs.json"
        outputs.write_text(
            json.dumps(
                {
                    "document_kind": "deployed",
                    "routes": {
                        "rest": {
                            "status": "ready",
                            "url": f"{double.base}{studio_rig['rest_path']}",
                        },
                        # The APPLICATION half is the real one: this arm is about
                        # which views survive a stale REST contract, and that is
                        # only a question if the survivors are real.
                        "app": {"status": "ready", "url": studio_rig["app_url"]},
                    },
                }
            ),
            encoding="utf-8",
        )
        started = launch(studio_rig, "ada", studio_rig["admin_password_file"], outputs=outputs)
        try:
            _, _, state = json_call(started, "GET", "/__apg/state")
            assert state["surface"]["answer"] == "stale_contract", state["surface"]
            assert len(state["surface"]["served_sha256"]) == 64
            assert len(state["surface"]["expected_sha256"]) == 64
            assert state["surface"]["served_sha256"] != state["surface"]["expected_sha256"], (
                "a stale_contract answer that names one digest twice has told nobody which "
                "way the disagreement runs"
            )

            schema_status, _, schema = json_call(started, "GET", "/__apg/schema")
            assert schema_status == 409, (schema_status, schema)
            assert schema["reason"] == "stale_contract"

            query_status, _, _ = json_call(
                started, "POST", "/__apg/query", {"relation": "notes", "select": [], "limit": 1}
            )
            assert query_status == 409

            audit_status, _, audit = json_call(started, "GET", "/__apg/audit")
            assert audit_status == 200, (audit_status, audit)
            assert audit["status"] == "ok", (
                f"the audit view was refused because a REST contract disagreed: {audit}. Those "
                "are two contracts and one says nothing about the other"
            )
        finally:
            stop(started)
    finally:
        double.stop()


@requires_docker
def test_unreachable_and_unreadable_are_two_answers(
    studio_rig: dict[str, Any], tmp_path: Path
) -> None:
    """**STU-SURFACE-001**, ADR 0195's third outcome, twice and kept apart.

    Nothing listening is *I could not determine it*. A service answering with
    something that is not a document is a DIFFERENT *I could not determine it* --
    the route exists and something is on it. Reporting either as
    `stale_contract` would send an operator to regenerate a capture that was
    never in question.
    """

    def answer_for(rest_url: str) -> dict[str, Any]:
        outputs = tmp_path / f"outputs-{secrets.token_hex(3)}.json"
        outputs.write_text(
            json.dumps(
                {
                    "document_kind": "deployed",
                    "routes": {
                        "rest": {"status": "ready", "url": rest_url},
                        "app": {"status": "ready", "url": studio_rig["app_url"]},
                    },
                }
            ),
            encoding="utf-8",
        )
        started = launch(studio_rig, "ada", studio_rig["admin_password_file"], outputs=outputs)
        try:
            _, _, state = json_call(started, "GET", "/__apg/state")
            return dict(state["surface"])
        finally:
            stop(started)

    # Port 9 is `discard`: reserved, and nothing on this machine listens there.
    nothing = answer_for("http://127.0.0.1:9/")
    assert nothing["answer"] == "unreachable", nothing
    assert nothing["served_sha256"] is None, (
        "an unreachable route produced a served digest, which means something was digested"
    )

    double = StandIn()
    double.start()
    try:
        double.answers[f"{studio_rig['rest_path']}/"] = (200, b"not json")
        unreadable = answer_for(f"{double.base}{studio_rig['rest_path']}")
    finally:
        double.stop()
    assert unreadable["answer"] == "unreadable", unreadable
    assert unreadable["answer"] != nothing["answer"]
    assert "not JSON" in (unreadable["reason"] or "")


# ---------------------------------------------------------------------------
# STU-QUERY-001 -- the query view, as the human whose token it is
# ---------------------------------------------------------------------------


@requires_docker
def test_a_query_as_a_returns_as_rows_and_none_of_bs(studio_rig: dict[str, Any]) -> None:
    """**STU-QUERY-001.** RLS, through Studio, with the identity as the variable.

    Two launches, the same relation, the same code path, different subjects --
    so the only thing that can explain two counts is the policy. The stronger
    half is the second assertion: A's rows carry A's owner and no other, which a
    count alone would not say.

    **Studio is a holder, not a verifier.** Nothing here was decided by the
    forwarder: PostgREST verified a token the auth service signed and the
    database applied the policy. That is the property the whole design rests on
    and this is where it is measured.
    """
    subjects = studio_rig["subjects"]
    seen: dict[str, list[dict[str, Any]]] = {}
    for who in ("alpha-user-a", "beta-user-b"):
        started = launch(studio_rig, who, subjects[who]["password_file"])
        try:
            status, _, answer = json_call(
                started,
                "POST",
                "/__apg/query",
                {"relation": "notes", "select": [], "filters": [], "limit": 100},
            )
            assert status == 200, (status, answer)
            assert answer["status"] == "ok", answer
            seen[who] = answer["rows"]
        finally:
            stop(started)

    assert len(seen["alpha-user-a"]) == subjects["alpha-user-a"]["notes"] == 2, seen
    assert len(seen["beta-user-b"]) == subjects["beta-user-b"]["notes"] == 1, seen

    b_owner = subjects["beta-user-b"]["user_id"]
    assert all(row.get("owner_id") != b_owner for row in seen["alpha-user-a"]), (
        f"A was served a row owned by B through Studio: {seen['alpha-user-a']}"
    )
    a_owner = subjects["alpha-user-a"]["user_id"]
    assert {row.get("owner_id") for row in seen["alpha-user-a"]} == {a_owner}


@requires_docker
def test_a_query_syntax_value_finds_nothing_and_the_stored_value_is_found(
    studio_rig: dict[str, Any],
) -> None:
    """**STU-QUERY-001**, D1250's pair. A value is a value.

    The filter value is PostgREST's own syntax -- a comma, a bracket, an `&`.
    Sent as a filter it must match no row, because `rest_query` percent-encodes
    with no safe characters and the string reaches the service as characters.

    **The control is the half that makes it evidence** (D499): the same string
    is the TITLE of one of A's notes, and `eq` finds it. Without that, a
    forwarder that dropped the filter, or one that broke the request entirely,
    would pass the first assertion as convincingly as a correct one.
    """
    subjects = studio_rig["subjects"]
    started = launch(studio_rig, "alpha-user-a", subjects["alpha-user-a"]["password_file"])
    try:
        status, _, injected = json_call(
            started,
            "POST",
            "/__apg/query",
            {
                "relation": "notes",
                "select": ["id", "title"],
                "filters": [["title", "eq", SYNTAX_VALUE + "-absent"]],
                "limit": 100,
            },
        )
        assert status == 200, injected
        assert injected["status"] == "ok", injected
        assert injected["rows"] == [], (
            f"a filter value carrying PostgREST syntax matched rows: {injected}"
        )

        status, _, found = json_call(
            started,
            "POST",
            "/__apg/query",
            {
                "relation": "notes",
                "select": ["id", "title"],
                "filters": [["title", "eq", SYNTAX_VALUE]],
                "limit": 100,
            },
        )
        assert status == 200, found
        assert found["status"] == "ok", found
        assert [row["title"] for row in found["rows"]] == [SYNTAX_VALUE], (
            "the control failed: the stored value was not found by an eq filter, so the arm "
            f"above proves only that this path returns nothing at all -- {found}"
        )
    finally:
        stop(started)


# ---------------------------------------------------------------------------
# STU-AUDIT-001 -- the record, its boundary and its page
# ---------------------------------------------------------------------------


def seed_audit(
    studio_rig: dict[str, Any], agent_id: str, owner_id: str, outcome: str, reason: str | None,
    *, times: int = 1,
) -> None:  # fmt: skip
    """Rows written through the definer functions, as the agent (ADR 0135).

    One transaction, explicitly: `set_config(…, true)` is transaction-local and
    psql over stdin is autocommit, so a script that set the identity in one
    statement and wrote in the next would write rows belonging to nobody.
    """
    boundary = "NULL" if reason is None else f"'{reason}'"
    done = studio_rig["psql"](
        "BEGIN;\n"
        f'SET ROLE "{studio_rig["roles"]["agent_reader"]}";\n'
        f"SELECT set_config('app.agent_id', '{agent_id}', true);\n"
        f"SELECT set_config('app.user_id', '{owner_id}', true);\n"
        "DO $seed$ BEGIN\n"
        f"  FOR counter IN 1..{times} LOOP\n"
        "    PERFORM api.agent_audit_complete("
        "      api.agent_audit_begin('list_resources', NULL, NULL, NULL, NULL),"
        f"      '{outcome}', 7, 1, {boundary});\n"
        "  END LOOP;\n"
        "END $seed$;\n"
        "COMMIT;\n"
    )
    assert done.returncode == 0, done.stderr


@requires_docker
def test_the_audit_view_renders_every_row_of_the_page_with_its_boundary(
    studio_rig: dict[str, Any], as_admin: Launched
) -> None:
    """**STU-AUDIT-001**, ADR 0178 and migration 0032, through the page's own call.

    Five rows for one owner: three served, two refused at two DIFFERENT
    boundaries. Two rather than one because a field that always carries the same
    value is indistinguishable from a constant -- `scope_not_held` alone would
    pass against a reader that ignored the column and wrote the word.

    `denial_reason` on the served rows must be null: the boundary names what
    refused, and a row nothing refused has none.
    """
    owner = str(uuid_module.uuid4())
    served_agent = str(uuid_module.uuid4())
    seed_audit(studio_rig, served_agent, owner, "served", None, times=3)
    seed_audit(studio_rig, str(uuid_module.uuid4()), owner, "refused", "scope_not_held")
    seed_audit(studio_rig, str(uuid_module.uuid4()), owner, "refused", "budget_exceeded")

    status, _, answer = json_call(as_admin, "GET", f"/__apg/audit?owner_id={owner}")
    assert status == 200, answer
    assert answer["status"] == "ok", answer

    rows = answer["rows"]
    assert len(rows) == 5, f"{len(rows)} rows for one owner: {rows}"
    assert answer["total"] == 5
    assert answer["header"] == "showing 5 of 5 rows on this page; the page is the newest 500"
    assert answer["header"] == studio.audit_view_header(5, 5)

    boundaries = {row["denial_reason"] for row in rows if row["outcome"] == "refused"}
    assert boundaries == {"scope_not_held", "budget_exceeded"}, (
        f"the two refusals did not carry two boundaries: {rows}. Before migration 0032 the "
        "endpoint served every refusal without saying what refused it (D1247)"
    )
    assert all(row["denial_reason"] is None for row in rows if row["outcome"] == "served"), rows


@requires_docker
def test_the_audit_page_count_equals_the_tables_newest_rows(
    studio_rig: dict[str, Any], as_admin: Launched
) -> None:
    """**STU-AUDIT-001**, D1248: the page is a page and the header says so.

    520 rows for one agent, so the page cannot hold them. Studio serves 500 --
    `AUDIT_PAGE_LIMIT`, which is also the endpoint's own ceiling -- and the
    header states that the page is the newest 500 rather than reporting 500 as
    a total.

    **The number the header cannot show is read another way**: as the superuser,
    over the table, in the same cluster. The point is not that 520 is right; it
    is that Studio cannot know it and says so instead of implying otherwise.
    This is the row `agent_audit` grows without bound on (ledger §9).
    """
    agent = str(uuid_module.uuid4())
    owner = str(uuid_module.uuid4())
    seed_audit(studio_rig, agent, owner, "served", None, times=520)

    status, _, answer = json_call(as_admin, "GET", f"/__apg/audit?agent_id={agent}")
    assert status == 200, answer
    assert answer["status"] == "ok", answer
    assert len(answer["rows"]) == studio.AUDIT_PAGE_LIMIT == 500, len(answer["rows"])
    assert answer["page_limit"] == 500
    assert answer["header"].endswith("the page is the newest 500"), answer["header"]

    counted = studio_rig["psql"](
        f"SELECT count(*) FROM app_private.agent_audit WHERE agent_id = '{agent}'::uuid;"
    )
    assert counted.returncode == 0, counted.stderr
    assert int(counted.stdout.strip()) == 520, counted.stdout

    newest = studio_rig["psql"](
        "SELECT count(*) FROM (SELECT id FROM app_private.agent_audit "
        f"WHERE agent_id = '{agent}'::uuid ORDER BY started_at DESC LIMIT 500) AS page;"
    )
    assert int(newest.stdout.strip()) == 500, newest.stdout


@requires_docker
def test_a_view_filter_hides_no_row_from_the_pages_count(as_admin: Launched) -> None:
    """**STU-AUDIT-001.** A filter cannot happen upstream of the count (D1248).

    The page's filter boxes hide rows in the DOM. The proof that they CANNOT do
    anything else is here: the forwarder takes the endpoint's own two filters
    and refuses every other parameter with 400, so there is no request shape in
    which `outcome=served` narrows what was read -- and therefore none in which
    a viewer is shown a count that silently excludes refusals.

    `agent_id` alone is the control: it is accepted, so the 400 above is about
    which parameter and not about parameters.
    """
    for parameter in ("outcome=refused", "denial_reason=scope_not_held", "since=2026-01-01"):
        status, _, answer = json_call(as_admin, "GET", f"/__apg/audit?{parameter}")
        assert status == 400, (parameter, status, answer)
        assert answer["status"] == "invalid", answer

    status, _, answer = json_call(as_admin, "GET", f"/__apg/audit?agent_id={uuid_module.uuid4()}")
    assert status == 200, (status, answer)
    assert answer["status"] == "ok", (
        f"the control failed: an accepted filter was refused too, so the 400s above say "
        f"nothing about which parameters this view takes -- {answer}"
    )


@requires_docker
def test_a_token_without_the_audit_scope_is_refused_and_classified(
    studio_rig: dict[str, Any],
) -> None:
    """**STU-AUDIT-001.** A holder holds what the human holds, and no more.

    A launched as themself carries `notes:read`. The audit endpoint answers 403
    and Studio classifies that as `refused` -- a word, not a relayed body
    (D433). The stage plan's invariant is exactly this: the DX layer holds
    nothing the human does not hold, so a view being visible in the page is not
    the same as its data being reachable.
    """
    subjects = studio_rig["subjects"]
    started = launch(studio_rig, "alpha-user-a", subjects["alpha-user-a"]["password_file"])
    try:
        status, _, answer = json_call(started, "GET", "/__apg/audit")
        assert status == 200, (status, answer)
        assert answer == {"status": "refused"}, (
            f"the refusal carried more than the kind of no: {answer}"
        )
    finally:
        stop(started)


# ---------------------------------------------------------------------------
# STU-REVOKE-001
# ---------------------------------------------------------------------------


@requires_docker
def test_revocation_through_studio_stops_the_agents_next_exchange(
    studio_rig: dict[str, Any], as_admin: Launched
) -> None:
    """**STU-REVOKE-001.** The typed confirmation, and what the click actually does.

    Four states in order, and the third is the control: a WRONG confirmation is
    422 and **the agent still works**. Without that, a proof that revocation
    stops an exchange cannot tell a refused confirmation from a confirmation
    that was ignored and a revocation that happened anyway.

    The last assertion goes past HTTP to the boundary itself: migration 0018's
    comparison helper returns the agent's owner on a full tuple match and NULL
    otherwise, and a revoked agent stops on the NEXT request rather than at its
    token's expiry. That is what a 401 at `/auth/agent-token` means, said in the
    database's own terms.
    """
    status, raw = http(
        "POST", f"{studio_rig['app_url']}/admin/agents", token=studio_rig["admin_token"],
        body={
            "name": f"studio-revokes-{secrets.token_hex(3)}",
            "description": "a fixture",
            "role": "agent_reader",
            "scopes": ["notes:read", "tasks:read"],
        },
    )  # fmt: skip
    assert status == 201, raw[:400]
    agent = json.loads(raw)
    exchange = {"agent_id": agent["agent_id"], "secret": agent["secret"]}

    status, raw = http("POST", f"{studio_rig['app_url']}/auth/agent-token", body=exchange)
    assert status == 200, f"the agent could not exchange its secret before anything: {raw[:300]}"

    before = studio_rig["psql"](
        "SELECT role_name || '|' || array_to_string(scopes, ',') || '|' || authz_version "
        f"FROM app_private.agents WHERE id = '{agent['agent_id']}'::uuid;"
    )
    assert before.returncode == 0, before.stderr
    role_name, scope_list, authz_version = before.stdout.strip().split("|")

    status, _, refused = json_call(
        as_admin,
        "POST",
        "/__apg/revoke",
        {"agent_id": agent["agent_id"], "confirm": "yes"},
    )
    assert status == 422, (status, refused)
    assert refused["status"] == "invalid"
    assert agent["agent_id"] in refused["reason"], refused

    status, raw = http("POST", f"{studio_rig['app_url']}/auth/agent-token", body=exchange)
    assert status == 200, (
        "the control failed: the agent stopped working after a REFUSED confirmation, so the "
        f"revocation below proves nothing about the confirmation -- {raw[:300]}"
    )

    status, _, revoked = json_call(
        as_admin,
        "POST",
        "/__apg/revoke",
        {"agent_id": agent["agent_id"], "confirm": agent["agent_id"]},
    )
    assert status == 200, (status, revoked)
    assert revoked["status"] == "ok", revoked

    status, raw = http("POST", f"{studio_rig['app_url']}/auth/agent-token", body=exchange)
    assert status == 401, f"a revoked agent exchanged its secret: {status} {raw[:300]}"

    current = studio_rig["psql"](
        "SELECT coalesce(app_private.agent_claims_are_current("
        f"'{agent['agent_id']}'::uuid, '{role_name}', "
        f"ARRAY[{','.join(repr(scope) for scope in scope_list.split(','))}]::text[], "
        f"{authz_version})::text, 'NULL');"
    )
    assert current.returncode == 0, current.stderr
    assert current.stdout.strip() == "NULL", (
        "the claims a live token carries still match a revoked agent, so the 401 above came "
        f"from somewhere else: {current.stdout!r}"
    )


# ---------------------------------------------------------------------------
# STU-SESSION-001
# ---------------------------------------------------------------------------


@requires_docker
def test_studio_ends_the_session_it_began(studio_rig: dict[str, Any]) -> None:
    """**STU-SESSION-001.** A tool that opens a session closes it.

    Read through a SEPARATE login of the same subject, before and after, because
    Studio's own session cannot report on its own ending -- the token that would
    ask is the one being revoked. The row is identified by difference rather than
    by guessing which is newest: whatever `/auth/sessions` gains between the two
    reads is what the launch opened.
    """
    password_file = studio_rig["subjects"]["alpha-user-a"]["password_file"]
    subject = "alpha-user-a"
    password = studio_rig["subjects"][subject]["password"]

    def sessions() -> dict[str, Any]:
        status, raw = http(
            "POST", f"{studio_rig['app_url']}/auth/login",
            body={"username": subject, "password": password},
        )  # fmt: skip
        assert status == 200, raw[:300]
        token = json.loads(raw)["access_token"]
        status, raw = http("GET", f"{studio_rig['app_url']}/auth/sessions", token=token)
        assert status == 200, raw[:300]
        return {row["session_id"]: row for row in json.loads(raw)}

    before = sessions()
    started = launch(studio_rig, subject, password_file)
    _, _, state = json_call(started, "GET", "/__apg/state")
    assert state["own_session_known"] is True, (
        "the launch could not determine its own session, so it will end none and this proof "
        "is measuring the wrong thing (ADR 0195: it SAYS so rather than guessing)"
    )
    during = sessions()

    opened = set(during) - set(before)
    # Two rows appear: Studio's and the reading login's own. Studio's is the one
    # that is not the reader's, and the reader's is the newest of the two.
    assert opened, "no session row appeared when Studio logged in"
    candidates = {session_id for session_id in opened if during[session_id]["revoked_at"] is None}
    assert candidates, during

    stop(started)
    after = sessions()

    ended = [
        session_id
        for session_id in candidates
        if after.get(session_id, {}).get("revoked_at") is not None
    ]
    assert ended, (
        "Studio stopped without ending any session it opened: "
        f"{[after.get(s) for s in candidates]}. A session a tool opened and did not close is "
        "a credential with nobody's name on it"
    )


@requires_docker
def test_studio_refreshes_before_expiry(studio_rig: dict[str, Any], tmp_path: Path) -> None:
    """**STU-SESSION-001**, D1252 -- measured against a short expiry, not a clock.

    **The rig's application cannot issue one.** `app.service.TOKEN_TTL_SECONDS`
    is `claims.MAX_TTL_SECONDS`, a module constant of 900 with no settings path;
    rig 24b read `expires_at` back from a real login and it was 900 seconds out.
    So the arm that drives the refresh uses a stand-in that hands out an access
    token expiring inside `STUDIO_REFRESH_BEFORE_SECONDS`, which drives the
    PRODUCT's own `Upstream.bearer` rather than a stand-in of it.

    The control is the rig itself: every other proof in this module runs against
    the real application with a 900-second token and none of them refreshes, so
    a `bearer()` that refreshed unconditionally would not survive them.
    """
    double = StandIn()
    double.start()
    try:
        double.answers["/auth/login"] = (
            200,
            {
                "access_token": "short-lived-access-token",
                "token_type": "Bearer",
                # Inside the window, so the NEXT upstream call must refresh.
                "expires_at": int(time.time()) + 10,
                "token_use": "access",
                "refresh_token": "a-refresh-token",
            },
        )
        outputs = tmp_path / "refresh-outputs.json"
        outputs.write_text(json.dumps(double.deployed()), encoding="utf-8")

        started = launch(studio_rig, "ada", studio_rig["admin_password_file"], outputs=outputs)
        try:
            json_call(started, "GET", "/__apg/me")
        finally:
            stop(started)

        assert ("POST", "/auth/refresh") in double.requests, (
            "the process made no refresh call with an access token ten seconds from expiry; "
            f"it made {double.requests}"
        )
        assert studio.STUDIO_REFRESH_BEFORE_SECONDS == 120
    finally:
        double.stop()


# ---------------------------------------------------------------------------
# STU-SECRET-001 (D1256)
# ---------------------------------------------------------------------------


@requires_docker
def test_no_page_response_header_or_asset_carries_the_token(
    studio_rig: dict[str, Any], as_admin: Launched
) -> None:
    """**STU-SECRET-001.** The browser is handed a launch key and never a token.

    The token this launch holds is a real one, so it is obtained here the same
    way Studio obtained it -- a second login as the same subject -- and then
    looked for in every byte the page can see. A page that could read the token
    would make the whole arrangement pointless: the process exists precisely so
    the credential stays on one side of the socket.
    """
    status, raw = http(
        "POST", f"{studio_rig['app_url']}/auth/login",
        body={"username": "ada", "password": PASSPHRASE},
    )  # fmt: skip
    assert status == 200, raw[:300]
    issued = json.loads(raw)
    # A JWT's signature differs per issuance; its payload does not, and that is
    # the part that would be a credential in a page.
    payload = issued["access_token"].split(".")[1]
    assert len(payload) > 20

    for path in ("/", "/studio.js", "/studio.css", "/__apg/state", "/__apg/me"):
        status, headers, body = as_admin.call("GET", path)
        assert status == 200, (path, status)
        blob = body.decode("utf-8", "replace") + json.dumps(headers)
        assert payload not in blob, f"{path} carried the access token's payload"
        assert "Authorization" not in headers
        assert issued.get("refresh_token", "no-refresh-token-issued") not in blob

    _, headers, _ = as_admin.call("GET", "/__apg/state")
    assert "Set-Cookie" not in headers, (
        "the launch cookie is set once, at /open/<key>, and re-sent by the browser; a "
        "Set-Cookie on every response is a key travelling more often than it needs to"
    )


@requires_docker
def test_nothing_studio_prints_is_a_token_a_key_or_a_value(
    studio_rig: dict[str, Any], tmp_path: Path
) -> None:
    """**STU-SECRET-001**, D1256. The log is a method, a path and nothing else.

    Driven with a query whose VALUE is distinctive, a filter whose value is
    distinctive, and the launch key itself in a URL -- all three are the shapes
    a default `http.server` logger writes to stderr, because it logs the request
    line and the request line carries the query string.

    **stdout and the log are two places and only one of them is the subject.**
    The launch key is PRINTED, once, on stdout: it is the URL a human opens, and
    a tool that would not tell anybody where it is listening is not a tool. The
    claim is that it does not then appear in the request log, where it would be
    written once per request by a logger nobody chose -- so the key is asserted
    absent from stderr and asserted to appear exactly once on stdout.
    """
    marker = f"do-not-log-{secrets.token_hex(8)}"
    started = launch(studio_rig, "ada", studio_rig["admin_password_file"])
    try:
        started.call("GET", f"/open/{started.key}")
        started.call("GET", f"/__apg/audit?agent_id={marker}")
        json_call(
            started,
            "POST",
            "/__apg/query",
            {
                "relation": "notes",
                "select": ["id"],
                "filters": [["title", "eq", marker]],
                "limit": 5,
            },
        )
    finally:
        log = stop(started)

    announced = "\n".join(started.lines)
    assert marker not in log, f"a value a caller sent was written to the log: {log[-800:]}"
    assert marker not in announced, f"a value a caller sent was announced: {announced[-400:]}"
    assert started.key not in log, (
        "the launch key reached the request log; `redact_for_log` replaces it rather than "
        f"trimming the path: {log[-800:]}"
    )
    assert "/open/<key>" in log, (
        f"the log recorded no redacted launch path, so the assertion above is vacuous: {log!r}"
    )
    assert announced.count(started.key) == 1, (
        f"the launch key was printed {announced.count(started.key)} times; it is the URL a "
        "human opens and is printed once"
    )
    assert PASSPHRASE not in log + announced


@requires_docker
def test_the_capabilities_view_is_served_whatever_the_surface_answered(
    studio_rig: dict[str, Any], as_user: Launched, tmp_path: Path
) -> None:
    """**D1274.** Two contracts, two answers, and neither one folded into the other.

    The compiled lock is not the REST document. Studio never asks the deployment
    which lock it loaded -- `list_resources` reports that (D1201) and
    `bin/apg.sh doctor` compares it -- so no launch answer is evidence about the
    lock either way, and refusing this view because a REST capture is stale would
    report one contract's staleness as another's.

    Both arms run: served under `ok`, and served identically under
    `unreachable`, where the schema view beside it is refused.
    """
    status, _, ok_view = json_call(as_user, "GET", "/__apg/capabilities")
    assert status == 200, ok_view
    assert ok_view["tools"], "the capabilities view names no tool"
    assert len(ok_view["tools_sha256"]) == 64
    assert ok_view["note"] == studio.CAPABILITIES_NOTE
    assert "doctor" in ok_view["note"]

    outputs = tmp_path / "no-rest-outputs.json"
    outputs.write_text(
        json.dumps(
            {
                "document_kind": "deployed",
                "routes": {
                    "rest": {"status": "ready", "url": "http://127.0.0.1:9/"},
                    "app": {"status": "ready", "url": studio_rig["app_url"]},
                },
            }
        ),
        encoding="utf-8",
    )
    started = launch(studio_rig, "ada", studio_rig["admin_password_file"], outputs=outputs)
    try:
        _, _, state = json_call(started, "GET", "/__apg/state")
        assert state["surface"]["answer"] == "unreachable"

        schema_status, _, _ = json_call(started, "GET", "/__apg/schema")
        assert schema_status == 409, (
            "the control failed: the schema view was served under an unreachable surface, so "
            "the capabilities view being served says nothing about the split"
        )

        status, _, unreachable_view = json_call(started, "GET", "/__apg/capabilities")
        assert status == 200, unreachable_view
        assert unreachable_view == ok_view, (
            "the capabilities view changed with the surface answer, which is the folding this "
            f"proof exists to refuse: {unreachable_view}"
        )
    finally:
        stop(started)


@requires_docker
def test_the_rig_cost_is_recorded(studio_rig: dict[str, Any]) -> None:
    """Not a claim -- the number D1211 asks every rig of this shape to state.

    PostgREST beside `apg dev` is a rig and not a verb, and its price is paid by
    every offline sweep that collects this module. Printed rather than bounded:
    a threshold here would fail on a slower machine and say nothing true.
    """
    seconds = studio_rig["seconds"]
    sys.stdout.write(
        f"\nstudio_rig built in {seconds:.1f} s, cluster at {studio_rig['cluster_address']}\n"
    )
    assert seconds > 0
    assert "via" in studio_rig["cluster_address"]

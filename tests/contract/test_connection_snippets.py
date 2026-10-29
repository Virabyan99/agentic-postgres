"""The connection snippets `/v1` serves for a project's public doors (D2352,
ADR 0268 item 6; Session 47 Run 6, ADR 0295 decision 7, D2956, D2991).

The property: **no snippet can carry a password.** Every place a password
goes says `PASSWORD_PLACEHOLDER`, and a record carrying a value under any name
does not reach the text. Then what each client needs, and a `where` line for
each (which file, what to install).

**And every served text RUNS** (the second half of this module). A snippet
nobody ran is a value that looks measured: rig 39c connected the first four
clients with an explicit CA file, so `sslrootcert=system` -- the text psycopg
was served for seven sessions -- was never executed, and executed here it
verifies against nothing (psycopg[binary]'s OpenSSL looks under the directory
it was built in). So each client's text is rendered by the REAL `snippets()`
with a rig's doors, the rig's password put where the placeholder is (only
here), and run in its client's pinned image:

* the rig is the product's: the two customer poolers started from
  `compose.yaml`'s own entrypoints (transaction mode behind the pooled door,
  session mode behind the direct one), their userlists written by the sync
  verb's own functions (`test_customer_poolers.Rig`), the roles' grants from
  `bootstrap_statements.customer_statements`, and Traefik with the edge's own
  `postgres` entrypoint (`infra/edge/traefik.yaml`) and TLS options
  (`infra/edge/dynamic/baseline.yaml`) terminating TLS in front of them;
* what it OMITS, stated: the edge reads its TCP routers from Docker labels
  through the socket proxy, and the rig writes the same routers in a file; the
  certificate is a private CA's, not the resolver's; there is no port 5432 ->
  8432 publication (the clients reach the entrypoint on the rig's network);
* trust is installed where each client looks in production: the system bundle
  (libpq's `sslrootcert=system`, Go, Prisma's OpenSSL), Node's own store
  (`NODE_EXTRA_CA_CERTS`), certifi's bundle (psycopg);
* each run does something real -- a parameterised query through the
  transaction pooler (and, for every driver, a NAMED prepared statement run
  twice), and a migration on the direct door for every client that has one;
* **the control**: the same text pointed at a name the certificate does not
  carry fails, each door on its own, asserted on the client's own words for a
  name mismatch -- and the same misnamed door answers a client that does not
  verify, so the refusal is the name check and not the route.
"""

# ruff: noqa: E501 -- the client programs embedded below keep their own
# languages' line lengths; they run in containers, not here.

from __future__ import annotations

import copy
import functools
import json
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.contract.test_customer_poolers import DIRECT, POOL, Rig, _lock, _wait, docker
from tests.contract.test_image_contracts import requires_docker

from agentic_postgres import REPO_ROOT, bootstrap_statements, service_source

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

snippets_module = service_source.load("connection_snippets")
PLACEHOLDER = snippets_module.PASSWORD_PLACEHOLDER

DOORS: dict[str, Any] = {
    "enabled": True,
    "pooled": {
        "host": "pool.slot1.example.com", "port": 5432, "user": "slot1_prod_customer_app",
        "database": "slot1_prod", "sslmode": "verify-full", "connection_limit": 2,
    },
    "direct": {
        "host": "direct.slot1.example.com", "port": 5432, "user": "slot1_prod_customer_admin",
        "database": "slot1_prod", "sslmode": "verify-full", "connection_limit": 2,
    },
}  # fmt: skip

SERVED = ("psql", "prisma", "node-pg", "psycopg", "drizzle", "go-pgx", "env")
SNIPPET_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "snippet-clients"
CLIENT_FIXTURES = REPO_ROOT / "services" / "clients"


def test_every_measured_client_has_one_snippet_and_no_other() -> None:
    served = snippets_module.snippets(DOORS)
    assert tuple(served) == snippets_module.CLIENTS == SERVED


def test_no_snippet_can_carry_a_password() -> None:
    """A record carrying a value -- as `password`, inside a door, or as an
    extra member -- never reaches the text; every snippet that names a
    password names the placeholder."""
    tainted = copy.deepcopy(DOORS)
    secret = "s3cret-value-never-served"  # noqa: S105 -- the planted value the proof hunts
    tainted["password"] = secret
    tainted["pooled"]["password"] = secret
    tainted["direct"]["password"] = secret
    tainted["direct"]["url"] = f"postgresql://x:{secret}@h/d"
    served = snippets_module.snippets(tainted)
    assert served == snippets_module.snippets(DOORS)
    for client, text in served.items():
        assert secret not in text, client
        if client != "psql":
            assert PLACEHOLDER in text, client
    # psql reads the password from the prompt or PGPASSFILE: its line names none.
    assert "password" not in served["psql"].split("#")[0]


def test_each_client_verifies_the_server() -> None:
    served = snippets_module.snippets(DOORS)
    assert served["psql"].count("sslmode=verify-full sslrootcert=system") == 2
    assert "rejectUnauthorized: true" in served["node-pg"]
    prisma = served["prisma"].splitlines()
    assert prisma[0].startswith('DATABASE_URL="postgresql://slot1_prod_customer_app:')
    assert "@pool.slot1.example.com:5432/slot1_prod?" in prisma[0]
    assert prisma[1].startswith('DIRECT_URL="postgresql://slot1_prod_customer_admin:')
    assert "@direct.slot1.example.com:5432/slot1_prod?" in prisma[1]
    for line in prisma:
        assert line.endswith('?sslmode=require&sslaccept=strict"'), line
    assert "pgbouncer" not in served["prisma"]

    # psycopg: certifi's roots, NEVER `system` -- psycopg[binary]'s bundled
    # OpenSSL finds no system roots on any machine (measured below).
    assert 'sslmode=verify-full sslrootcert=" + certifi.where()' in served["psycopg"]
    assert "sslrootcert=system" not in served["psycopg"]
    assert served["psycopg"].startswith("import certifi\nimport psycopg\n")

    # Drizzle is node-postgres underneath: the same verification.
    assert "ssl: { rejectUnauthorized: true }" in served["drizzle"]
    assert "rejectUnauthorized: false" not in served["drizzle"]

    # pgx: both doors, verify-full against the system roots, and no exec-mode
    # override -- the default (cached prepared statements) is what ran.
    assert served["go-pgx"].count("sslmode=verify-full sslrootcert=system") == 2
    assert "default_query_exec_mode" not in served["go-pgx"]
    assert "pgbouncer" not in served["go-pgx"]

    env = [line for line in served["env"].splitlines() if not line.startswith("#")]
    assert [line.split("=", 1)[0] for line in env] == ["DATABASE_URL", "DIRECT_URL"]
    for line in env:
        assert line.endswith('?sslmode=verify-full&sslrootcert=system"'), line


def test_the_pooled_door_is_the_default_and_the_direct_is_named() -> None:
    served = snippets_module.snippets(DOORS)
    for client in ("node-pg", "psycopg", "drizzle"):
        assert "pool.slot1.example.com" in served[client]
        assert "direct." not in served[client]
    assert "host=pool.slot1.example.com" in served["psql"]
    assert "host=direct.slot1.example.com" in served["psql"]
    # Drizzle's migrations are the direct door's, named by its role.
    assert "as slot1_prod_customer_admin" in served["drizzle"]
    go = served["go-pgx"]
    assert go.index("host=pool.slot1.example.com") < go.index("host=direct.slot1.example.com")
    assert "user=slot1_prod_customer_app" in go and "user=slot1_prod_customer_admin" in go
    urls = dict(
        line.split("=", 1) for line in served["env"].splitlines() if not line.startswith("#")
    )
    assert "@pool.slot1.example.com:5432/" in urls["DATABASE_URL"]
    assert "slot1_prod_customer_app:" in urls["DATABASE_URL"]
    assert "@direct.slot1.example.com:5432/" in urls["DIRECT_URL"]
    assert "slot1_prod_customer_admin:" in urls["DIRECT_URL"]


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": False},
        {"pooled": None},
        {"direct": {"host": "x", "port": 5432, "user": "u", "database": "d"}},
        {"pooled": {**DOORS["pooled"], "host": 'pool.example.com" && rm -rf /'}},
        {"pooled": {**DOORS["pooled"], "port": "5432"}},
        {"pooled": {**DOORS["pooled"], "port": True}},
        {"pooled": {**DOORS["pooled"], "user": "Robert'); DROP TABLE"}},
        {"direct": {**DOORS["direct"], "database": "a b"}},
    ],
)
def test_a_record_that_is_not_one_yields_no_snippet(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        snippets_module.snippets({**DOORS, **change})


# ---------------------------------------------------------------------------
# `where`: which file, what to install
# ---------------------------------------------------------------------------


def test_every_served_client_says_where_it_goes_and_what_to_install() -> None:
    """One `where` per served client, in the snippets' order, no other; each a
    file and an install line, neither empty. A copy: editing it edits nothing."""
    where = snippets_module.where()
    assert tuple(where) == snippets_module.CLIENTS
    for client, line in where.items():
        assert set(line) == {"file", "install"}, client
        assert all(isinstance(v, str) and v.strip() for v in line.values()), client
    where["psql"]["file"] = "edited"
    assert snippets_module.where()["psql"]["file"] != "edited"
    assert where != snippets_module.where()


def _installed(command: str, prefix: str) -> dict[str, str | None]:
    """`npm install a b@6` -> {a: None, b: "6"}; a scoped name keeps its `@`."""
    assert command.startswith(prefix), command
    found: dict[str, str | None] = {}
    for token in command[len(prefix) :].split():
        scoped = token.startswith("@")
        name, at, version = (token[1:] if scoped else token).partition("@")
        found[("@" if scoped else "") + name] = version if at else None
    return found


def test_each_install_line_names_exactly_what_its_executed_image_pins() -> None:
    """The install line is read against the image the snippet RAN in, so it
    cannot name a package the proof never installed, or omit one it needed:
    Prisma's major is pinned because the snippet's model (`directUrl` in the
    schema) is Prisma 6's -- Prisma 7 moved it into `prisma.config.ts`."""
    where = snippets_module.where()

    def dependencies(directory: Path) -> dict[str, str]:
        manifest = json.loads((directory / "package.json").read_text(encoding="utf-8"))
        return {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}

    node_pg = dependencies(CLIENT_FIXTURES / "node-pg")
    assert set(_installed(where["node-pg"]["install"], "npm install ")) == set(node_pg)
    drizzle = dependencies(SNIPPET_FIXTURES / "drizzle")
    assert set(_installed(where["drizzle"]["install"], "npm install ")) == set(drizzle)
    prisma = dependencies(CLIENT_FIXTURES / "prisma")
    named = _installed(where["prisma"]["install"], "npm install ")
    assert set(named) == set(prisma)
    for package, version in prisma.items():
        assert named[package] == version.split(".")[0], package

    requirements = (SNIPPET_FIXTURES / "psycopg" / "requirements.in").read_text("utf-8")
    pinned = {line.split("==")[0] for line in requirements.split() if "==" in line}
    command = where["psycopg"]["install"]
    assert command.startswith("pip install ")
    assert set(command[len("pip install ") :].replace('"', "").split()) == pinned

    go_mod = (SNIPPET_FIXTURES / "go-pgx" / "go.mod").read_text("utf-8")
    direct = re.findall(r"^require (\S+) v", go_mod, re.MULTILINE)
    assert where["go-pgx"]["install"] == f"go get {direct[0]}" and len(direct) == 1


# ---------------------------------------------------------------------------
# The executed half: each served text run through a TLS rig
# ---------------------------------------------------------------------------

LOCK = _lock()
DOMAIN = "snip.rig.test"
POOL_HOST, DIRECT_HOST, MISNAMED = f"pool.{DOMAIN}", f"direct.{DOMAIN}", f"misnamed.{DOMAIN}"
#: The bundle the system's OpenSSL (Debian and Alpine alike) and Go read.
SYSTEM_TRUST = "cat /rig/ca.crt >> /etc/ssl/certs/ca-certificates.crt"
CERTIFI_TRUST = 'cat /rig/ca.crt >> "$(python -c "import certifi; print(certifi.where())")"'
#: How each client says a certificate names another host (each measured).
NAME_MISMATCH = {
    "psql": f'does not match host name "{MISNAMED}"',
    "prisma": "(hostname mismatch)",
    "node-pg": "ERR_TLS_CERT_ALTNAME_INVALID",
    "psycopg": f'does not match host name "{MISNAMED}"',
    "drizzle": "ERR_TLS_CERT_ALTNAME_INVALID",
    "go-pgx": f"not {MISNAMED}",
    "env": f'does not match host name "{MISNAMED}"',
}
#: The clients whose text opens both doors (the others open the pooled one).
BOTH_DOORS = ("psql", "prisma", "go-pgx", "env")


@dataclass
class TlsRig:
    network: str
    certs: Path
    port: int
    password: str
    work: Path
    poolers: Rig

    def doors(self, *, misnamed: str | None = None) -> dict[str, Any]:
        def door(name: str, host: str, user: str) -> dict[str, Any]:
            return {
                "host": MISNAMED if misnamed == name else host, "port": self.port,
                "user": user, "database": "app", "sslmode": "verify-full",
                "connection_limit": 2,
            }  # fmt: skip

        return {
            "enabled": True,
            "pooled": door("pooled", POOL_HOST, "customer_app"),
            "direct": door("direct", DIRECT_HOST, "customer_admin"),
        }

    def text(self, client: str, *, misnamed: str | None = None) -> str:
        """The SERVED text for the rig's doors, the password where the
        placeholder is -- the only place in this repository it is replaced."""
        served = snippets_module.snippets(self.doors(misnamed=misnamed))[client]
        return served.replace(PLACEHOLDER, self.password)

    def scrub(self, text: str) -> str:
        return text.replace(self.password, "<rig password>")


def _readable(directory: Path, files: dict[str, str]) -> Path:
    """`files` under `directory`, 0755/0644 inside the mount. The clients run
    as root and the daemon resolves the bind's source, so pytest's 0700 parents
    are not in the way (the toolchain's 65532 is why `readable_copy` exists)."""
    directory.mkdir(parents=True)
    for name, text in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o644)
    for path in [directory, *(p for p in directory.rglob("*") if p.is_dir())]:
        path.chmod(0o755)
    return directory


def _openssl(*arguments: str) -> None:
    done = subprocess.run(["openssl", *arguments], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr


def _certificates(directory: Path) -> None:
    """A private CA and one certificate for the two doors -- never the
    misnamed one, which the edge answers with this certificate anyway."""
    directory.mkdir()
    d = str(directory)
    _openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
             "-subj", "/CN=apg snippet rig CA",
             "-keyout", f"{d}/ca.key", "-out", f"{d}/ca.crt")  # fmt: skip
    _openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={POOL_HOST}",
             "-keyout", f"{d}/server.key", "-out", f"{d}/server.csr")  # fmt: skip
    (directory / "san.ext").write_text(f"subjectAltName=DNS:{POOL_HOST},DNS:{DIRECT_HOST}\n")
    _openssl("x509", "-req", "-in", f"{d}/server.csr", "-CA", f"{d}/ca.crt",
             "-CAkey", f"{d}/ca.key", "-CAcreateserial", "-days", "2",
             "-extfile", f"{d}/san.ext", "-out", f"{d}/server.crt")  # fmt: skip
    directory.chmod(0o755)
    for path in directory.iterdir():
        path.chmod(0o644)


def _edge_files(directory: Path, poolers: Rig) -> int:
    """Traefik's static and dynamic files: the edge's own `postgres` entrypoint
    and TLS options, read from the files the edge ships; the rig adds the
    certificate, the routers (the edge's come from labels) and `lenient` --
    the `postgres` option with `sniStrict` off, for the misnamed name only, so
    the edge answers it with the doors' certificate rather than refusing the
    handshake (a refusal no client's verification would be tested by)."""
    static = yaml.safe_load((REPO_ROOT / "infra/edge/traefik.yaml").read_text("utf-8"))
    entrypoint = static["entryPoints"]["postgres"]
    baseline = (REPO_ROOT / "infra/edge/dynamic/baseline.yaml").read_text("utf-8")
    baseline = "\n".join(
        line for line in baseline.splitlines() if line.strip() != "__HSTS_BLOCK__"
    )  # the render's placeholder (bin/render-config.py); nothing TLS-shaped
    options = dict(yaml.safe_load(baseline)["tls"]["options"])
    assert options["postgres"]["sniStrict"] is True, "the edge's postgres option moved"
    options["lenient"] = {**options["postgres"], "sniStrict": False}
    certificate = {"certFile": "/certs/server.crt", "keyFile": "/certs/server.key"}

    def router(host: str, service: str, option: str) -> dict[str, Any]:
        return {
            "entryPoints": ["postgres"], "rule": f"HostSNI(`{host}`)",
            "service": service, "tls": {"options": option},
        }  # fmt: skip

    def service(container: str) -> dict[str, Any]:
        return {"loadBalancer": {"servers": [{"address": f"{container}:6432"}]}}

    dynamic = {
        "tls": {
            "options": options,
            "certificates": [certificate],
            "stores": {"default": {"defaultCertificate": certificate}},
        },
        "tcp": {
            "routers": {
                "pool": router(POOL_HOST, "pool", "postgres"),
                "direct": router(DIRECT_HOST, "direct", "postgres"),
                "misnamed-pool": router(MISNAMED, "pool", "lenient"),
            },
            "services": {
                "pool": service(poolers.poolers[POOL]),
                "direct": service(poolers.poolers[DIRECT]),
            },
        },
    }
    static_file = {
        "entryPoints": {"postgres": entrypoint},
        "providers": {"file": {"directory": "/etc/traefik/dynamic", "watch": False}},
        "log": {"level": "INFO"},
    }
    _readable(
        directory,
        {"traefik.yaml": yaml.safe_dump(static_file), "dynamic/rig.yaml": yaml.safe_dump(dynamic)},
    )
    return int(str(entrypoint["address"]).rsplit(":", 1)[-1])


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TlsRig]:
    if shutil.which("openssl") is None:
        pytest.skip("no openssl on this machine, so the rig has no certificate authority")
    root = tmp_path_factory.mktemp("snippet-rig")
    root.chmod(0o755)
    userlists = root / "userlists"
    userlists.mkdir()
    userlists.chmod(0o755)
    certs = root / "certs"
    _certificates(certs)
    poolers = Rig(secrets.token_hex(4), LOCK, userlists)
    edge = f"{poolers.network}-edge"
    password = secrets.token_urlsafe(32)  # the shape the CLI and the console mint
    try:
        # `--internal`: the rig reaches nothing outside itself.
        assert docker("network", "create", "--internal", poolers.network).returncode == 0
        started = docker(
            "run", "-d", "--name", poolers.cluster, "--network", poolers.network,
            "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}", "-e", "POSTGRES_DB=app",
            "-e", "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256", LOCK["POSTGRES_IMAGE"],
        )  # fmt: skip
        assert started.returncode == 0, started.stderr
        assert _wait(
            lambda: (
                docker(
                    "exec", poolers.cluster, "psql", "-U", "postgres", "-d", "app", "-c", "SELECT 1"
                ).returncode
                == 0
            ),
            90,
        ), "the cluster never became ready"
        time.sleep(2)
        document = {
            "database": {
                "name": "app",
                "roles": {"customer_app": "customer_app", "customer_admin": "customer_admin"},
                "public": {"enabled": True},
            }
        }
        poolers.sql(
            "REVOKE ALL ON DATABASE app FROM PUBLIC;\n"
            "REVOKE CREATE ON SCHEMA public FROM PUBLIC;\n"
            "CREATE SCHEMA extensions; CREATE EXTENSION vector SCHEMA extensions;\n"
            "CREATE ROLE customer_app LOGIN NOINHERIT CONNECTION LIMIT 4;\n"
            "CREATE ROLE customer_admin LOGIN NOINHERIT CONNECTION LIMIT 3;\n"
            "SET password_encryption = 'scram-sha-256';\n"
            f"ALTER ROLE customer_app PASSWORD '{password}';\n"
            f"ALTER ROLE customer_admin PASSWORD '{password}';\n"
            + "\n".join(bootstrap_statements.customer_statements(document))
        )
        poolers.sync()
        for name, container in poolers.poolers.items():
            poolers.start_pooler(name, container)
        for name, container in poolers.poolers.items():
            assert _wait(lambda s=name, c=container: poolers.healthy(s, c)), f"{name} unhealthy"
        port = _edge_files(root / "edge", poolers)
        started = docker(
            "run", "-d", "--name", edge, "--network", poolers.network,
            "--network-alias", POOL_HOST, "--network-alias", DIRECT_HOST,
            "--network-alias", MISNAMED,
            "-v", f"{root}/edge/traefik.yaml:/etc/traefik/traefik.yaml:ro",
            "-v", f"{root}/edge/dynamic:/etc/traefik/dynamic:ro",
            "-v", f"{certs}:/certs:ro", LOCK["TRAEFIK_IMAGE"],
        )  # fmt: skip
        assert started.returncode == 0, started.stderr
        built = TlsRig(poolers.network, certs, port, password, root / "work", poolers)

        def answers() -> bool:
            probe = docker(
                "run", "--rm", "--network", built.network, "-v", f"{certs}:/rig:ro",
                "-e", f"PGPASSWORD={password}", "--entrypoint", "psql", LOCK["PGBOUNCER_IMAGE"],
                f"host={POOL_HOST} port={port} user=customer_app dbname=app "
                "sslmode=verify-full sslrootcert=/rig/ca.crt",
                "-XAtc", "SELECT 1",
            )  # fmt: skip
            return probe.returncode == 0

        assert _wait(answers, 60), built.scrub(docker("logs", edge).stderr[-2000:])
        yield built
    finally:
        for container in (edge, *poolers.poolers.values(), poolers.cluster):
            docker("rm", "-fv", container)
        docker("network", "rm", poolers.network)


@functools.cache
def _image(client: str) -> str:
    """The image a client's text runs in: the deployment fixture's own where
    one exists (node-postgres, Prisma), the psql the psql fixture is built on
    (the locked PgBouncer image, psql 17), and a test fixture beside this
    module otherwise -- each built from a pinned base by digest."""
    if client in ("psql", "env"):
        return LOCK["PGBOUNCER_IMAGE"]
    context, base = {
        "prisma": (CLIENT_FIXTURES / "prisma", "NODE_RUNTIME_IMAGE"),
        "node-pg": (CLIENT_FIXTURES / "node-pg", "NODE_RUNTIME_IMAGE"),
        "psycopg": (SNIPPET_FIXTURES / "psycopg", "PYTHON_RUNTIME_IMAGE"),
        "drizzle": (SNIPPET_FIXTURES / "drizzle", "NODE_RUNTIME_IMAGE"),
        "go-pgx": (SNIPPET_FIXTURES / "go-pgx", "GO_RUNTIME_IMAGE"),
    }[client]
    tag = f"apg-snippet-{client}:s47"
    done = docker(
        "build", "-q", "--build-arg", f"BASE_IMAGE={LOCK[base]}", "-t", tag, str(context),
        timeout=1800,
    )  # fmt: skip
    assert done.returncode == 0, f"the {client} image did not build:\n{done.stderr[-3000:]}"
    return tag


def _run(
    rig: TlsRig,
    label: str,
    image: str,
    script: str,
    files: dict[str, str],
    *,
    mounts: dict[str, str] | None = None,
    workdir: str = "/work",
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """`script` in `image` on the rig's network, as root (so it can install
    the rig's CA where the client looks), `files` mounted read-only."""
    work = _readable(rig.work / f"{label}-{secrets.token_hex(3)}", files)
    argv = ["run", "--rm", "--network", rig.network, "--user", "0",
            "-v", f"{rig.certs}:/rig:ro", "-w", workdir]  # fmt: skip
    for source, target in (mounts or {"": "/work"}).items():
        argv += ["-v", f"{work / source if source else work}:{target}:ro"]
    for key, value in (env or {}).items():
        argv += ["-e", f"{key}={value}"]
    argv += ["--entrypoint", "sh", image, "-c", script]
    return docker(*argv, timeout=900)


def _result(done: subprocess.CompletedProcess[str], rig: TlsRig) -> list[dict[str, Any]]:
    printed = rig.scrub(done.stdout + done.stderr)
    assert done.returncode == 0, f"the snippet did not run (exit {done.returncode}):\n{printed}"
    found = [
        json.loads(line[7:]) for line in done.stdout.splitlines() if line.startswith("RESULT ")
    ]
    assert found, f"the harness printed no RESULT:\n{printed}"
    return found


#: psql 17 (the psql fixture's, from the locked PgBouncer image): `\\bind`
#: sends the extended protocol's parse/bind/execute; a NAMED statement
#: (`\\parse`) is psql 18's, and the drivers below carry that half.
PSQL_POOLED = """\
SELECT 'user=' || current_user;
SELECT $1::int + 1 AS n \\bind 6 \\g
SELECT $1::int + 1 AS n \\bind 41 \\g
"""


def _psql_direct(table: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS public.{table} (id serial PRIMARY KEY, label text NOT NULL);\n"
        f"INSERT INTO public.{table} (label) VALUES ('a');\n"
        f"SELECT 'user=' || current_user || ' rows=' || count(*) FROM public.{table};\n"
    )


def _psql_result(done: subprocess.CompletedProcess[str], rig: TlsRig) -> dict[str, Any]:
    """psql prints lines; the harness wraps them as one RESULT."""
    printed = rig.scrub(done.stdout + done.stderr)
    assert done.returncode == 0, f"the snippet did not run (exit {done.returncode}):\n{printed}"
    return {"lines": done.stdout.splitlines()}


def _psql_lines(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if line.startswith('psql "')]
    assert len(lines) == 2, text
    return lines


#: Three rounds of eight at once over the pool: a client connection that
#: prepared `snippet_q` in one round uses it again in the next, on whichever
#: server connection the transaction pooler hands it -- the case the pooler's
#: `max_prepared_statements` exists for (with it at 0 this fails; mutation c).
NODE_PG_HARNESS = """
const one = await pool.query("select current_user as u, $1::int as n", [7]);
const q = (n) => ({ name: "snippet_q", text: "select $1::int + 1 as n", values: [n] });
let sum = 0;
for (let round = 0; round < 3; round++) {
  const many = await Promise.all(Array.from({ length: 8 }, (_, i) => pool.query(q(i))));
  sum += many.reduce((s, r) => s + r.rows[0].n, 0);
}
console.log("RESULT " + JSON.stringify({ user: one.rows[0].u, n: one.rows[0].n, prepared: sum }));
await pool.end();
"""

PSYCOPG_HARNESS = """
with conn:
    user = conn.execute("select current_user").fetchone()[0]
    values = [conn.execute("select %s::int + 1", (n,), prepare=True).fetchone()[0] for n in (6, 41, 41)]
print("RESULT " + json.dumps({"user": user, "values": values}))
"""

PRISMA_CLIENT = """\
import { PrismaClient } from "@prisma/client";
const p = new PrismaClient();
try {
  for (let i = 0; i < 3; i++) await p.fixtureRow.create({ data: { label: "r" + i } });
  const rows = await p.fixtureRow.count();
  const who = await p.$queryRaw`select current_user::text as u, ${7}::int as n`;
  let found = 0;
  for (let round = 0; round < 3; round++) {
    const many = await Promise.all([0, 1, 2, 3, 4, 5].map((i) => p.fixtureRow.findMany({ where: { label: "r" + (i % 3) } })));
    found += many.reduce((s, r) => s + r.length, 0);
  }
  console.log("RESULT " + JSON.stringify({ rows, user: who[0].u, n: who[0].n, found }));
} finally {
  await p.$disconnect();
}
"""

DRIZZLE_HARNESS = """\
import { sql, eq } from "drizzle-orm";
import { pgTable, serial, text } from "drizzle-orm/pg-core";
import { db, pool } from "./db.js";
const rows = pgTable("drizzle_rows", { id: serial("id").primaryKey(), label: text("label").notNull() });
const one = await db.execute(sql`select current_user as u, ${7}::int as n`);
await db.insert(rows).values([{ label: "a" }, { label: "b" }, { label: "b" }]);
const q = db.select().from(rows).where(eq(rows.label, sql.placeholder("l"))).prepare("snippet_by_label");
const a = await q.execute({ l: "a" });
const b = await q.execute({ l: "b" });
let found = 0;
for (let round = 0; round < 3; round++) {
  const many = await Promise.all(Array.from({ length: 8 }, (_, i) => q.execute({ l: i % 2 ? "a" : "b" })));
  found += many.reduce((s, r) => s + r.length, 0);
}
console.log("RESULT " + JSON.stringify({ user: one.rows[0].u, n: one.rows[0].n, a: a.length, b: b.length, found }));
await pool.end();
"""

DRIZZLE_MIGRATION = (
    'CREATE TABLE IF NOT EXISTS "drizzle_rows" ("id" serial PRIMARY KEY, "label" text NOT NULL);\n'
)

GO_HARNESS = """\
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sync"
)

func main() {
	ctx := context.Background()
	direct, err := connectDirect(ctx)
	if err != nil {
		fmt.Println("FAILED direct:", err)
		os.Exit(1)
	}
	if _, err := direct.Exec(ctx, "create table if not exists public.go_rows (id serial primary key, label text not null)"); err != nil {
		fmt.Println("FAILED migration:", err)
		os.Exit(1)
	}
	direct.Close(ctx)
	pool, err := connect(ctx)
	if err != nil {
		fmt.Println("FAILED pool:", err)
		os.Exit(1)
	}
	defer pool.Close()
	var user string
	if err := pool.QueryRow(ctx, "select current_user").Scan(&user); err != nil {
		fmt.Println("FAILED pooled:", err)
		os.Exit(1)
	}
	var wg sync.WaitGroup
	errs := make(chan error, 40)
	for w := 0; w < 4; w++ {
		wg.Add(1)
		go func(w int) {
			defer wg.Done()
			for i := 0; i < 10; i++ {
				var n int
				if err := pool.QueryRow(ctx, "select $1::int + $2::int", w, i).Scan(&n); err != nil {
					errs <- err
					return
				}
				if _, err := pool.Exec(ctx, "insert into public.go_rows (label) values ($1)", fmt.Sprint(w, "-", i)); err != nil {
					errs <- err
					return
				}
			}
		}(w)
	}
	wg.Wait()
	close(errs)
	for e := range errs {
		fmt.Println("FAILED parallel:", e)
		os.Exit(1)
	}
	var rows int
	if err := pool.QueryRow(ctx, "select count(*) from public.go_rows").Scan(&rows); err != nil {
		fmt.Println("FAILED count:", err)
		os.Exit(1)
	}
	out, _ := json.Marshal(map[string]any{"user": user, "rows": rows,
		"mode": pool.Config().ConnConfig.DefaultQueryExecMode.String()})
	fmt.Println("RESULT " + string(out))
}
"""

ENV_GO = """\
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func main() {
	ctx := context.Background()
	direct, err := pgx.Connect(ctx, os.Getenv("DIRECT_URL"))
	if err != nil {
		fmt.Println("FAILED direct:", err)
		os.Exit(1)
	}
	if _, err := direct.Exec(ctx, "create table if not exists public.env_go_rows (id int)"); err != nil {
		fmt.Println("FAILED migration:", err)
		os.Exit(1)
	}
	direct.Close(ctx)
	pool, err := pgxpool.New(ctx, os.Getenv("DATABASE_URL"))
	if err != nil {
		fmt.Println("FAILED pool:", err)
		os.Exit(1)
	}
	defer pool.Close()
	var user string
	var n int
	if err := pool.QueryRow(ctx, "select current_user, $1::int + 1", 41).Scan(&user, &n); err != nil {
		fmt.Println("FAILED pooled:", err)
		os.Exit(1)
	}
	out, _ := json.Marshal(map[string]any{"user": user, "n": n})
	fmt.Println("RESULT " + string(out))
}
"""


def _go_module() -> dict[str, str]:
    return {
        name: (SNIPPET_FIXTURES / "go-pgx" / name).read_text("utf-8")
        for name in ("go.mod", "go.sum")
    }


def _execute(rig: TlsRig, client: str, *, misnamed: str | None = None) -> list[dict[str, Any]]:
    """Run `client`'s served text against the rig; its RESULTs, or an
    AssertionError carrying what it printed (password scrubbed)."""
    text = rig.text(client, misnamed=misnamed)
    if client != "psql":
        assert rig.password in text, f"{client}'s text names no password placeholder"
    label = f"{client}-{misnamed or 'ok'}"
    if client == "psql":
        pooled, direct = _psql_lines(text)
        script = "\n".join(
            (
                "set -eu",
                SYSTEM_TRUST,
                f"{pooled} -qXAt -v ON_ERROR_STOP=1 -f /work/pooled.sql",
                f"{direct} -qXAt -v ON_ERROR_STOP=1 -f /work/direct.sql",
            )
        )
        done = _run(
            rig, label, _image(client), script,
            {"pooled.sql": PSQL_POOLED, "direct.sql": _psql_direct("psql_rows")},
            env={"PGPASSWORD": rig.password},
        )  # fmt: skip
        return [_psql_result(done, rig)]
    if client == "env":
        script = "\n".join(
            (
                "set -eu",
                SYSTEM_TRUST,
                "set -a; . /work/.env; set +a",
                'psql "$DATABASE_URL" -qXAt -v ON_ERROR_STOP=1 -f /work/pooled.sql',
                'psql "$DIRECT_URL" -qXAt -v ON_ERROR_STOP=1 -f /work/direct.sql',
            )
        )
        files = {".env": text, "pooled.sql": PSQL_POOLED, "direct.sql": _psql_direct("env_rows")}
        psql = _psql_result(_run(rig, label, _image("env"), script, files), rig)
        go_script = "\n".join(("set -eu", SYSTEM_TRUST, "set -a; . /work/.env; set +a", "go run ."))
        go = _run(
            rig, f"{label}-go", _image("go-pgx"), go_script,
            {".env": text, "main.go": ENV_GO, **_go_module()},
        )  # fmt: skip
        return [psql, *_result(go, rig)]
    if client == "prisma":
        # `migrate deploy` refuses a `public` holding tables it did not make
        # (P3005: rig 39c's ordering defect, met again here) -- so the other
        # clients' tables go first, leaving `public` as a new project's is.
        rig.poolers.sql(
            "DO $$ DECLARE t text; BEGIN FOR t IN SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename NOT IN ('_prisma_migrations', "
            "'fixture_rows') LOOP EXECUTE format('DROP TABLE public.%I CASCADE', t); "
            "END LOOP; END $$;"
        )
        script = "\n".join(
            (
                "set -eu",
                SYSTEM_TRUST,
                "node_modules/.bin/prisma migrate deploy --schema prisma/schema.prisma",
                "node --env-file=.env snippet-client.mjs",
            )
        )
        done = _run(
            rig, label, _image(client), script, {".env": text, "client.mjs": PRISMA_CLIENT},
            mounts={".env": "/app/.env", "client.mjs": "/app/snippet-client.mjs"}, workdir="/app",
        )  # fmt: skip
        found = _result(done, rig)
        assert re.search(
            r"All migrations have been successfully applied|No pending migrations", done.stdout
        ), rig.scrub(done.stdout)
        return found
    if client == "node-pg":
        done = _run(
            rig, label, _image(client), "node db.js", {"db.js": text + "\n" + NODE_PG_HARNESS},
            mounts={"": "/app/w"}, workdir="/app/w", env={"NODE_EXTRA_CA_CERTS": "/rig/ca.crt"},
        )  # fmt: skip
        return _result(done, rig)
    if client == "psycopg":
        program = "import json\n" + text + "\n" + PSYCOPG_HARNESS
        done = _run(
            rig, label, _image(client), f"{CERTIFI_TRUST}; python -u db.py", {"db.py": program}
        )
        return _result(done, rig)
    if client == "drizzle":
        # The snippet's own instruction: migrations' SQL through the direct door
        # with the psql snippet's second line.
        if misnamed is None:
            direct = _psql_lines(rig.text("psql"))[1]
            migrated = _run(
                rig, f"{label}-migrate", _image("psql"),
                f"set -eu; {SYSTEM_TRUST}; {direct} -qXAt -v ON_ERROR_STOP=1 "
                "-f /work/drizzle/0000_snippet.sql",
                {"drizzle/0000_snippet.sql": DRIZZLE_MIGRATION}, env={"PGPASSWORD": rig.password},
            )  # fmt: skip
            assert migrated.returncode == 0, rig.scrub(migrated.stdout + migrated.stderr)
        done = _run(
            rig, label, _image(client), "node run.mjs",
            {"db.js": text, "run.mjs": DRIZZLE_HARNESS},
            mounts={"": "/app/w"}, workdir="/app/w", env={"NODE_EXTRA_CA_CERTS": "/rig/ca.crt"},
        )  # fmt: skip
        return _result(done, rig)
    if client == "go-pgx":
        done = _run(
            rig, label, _image(client), f"set -eu; {SYSTEM_TRUST}; go run .",
            {"db.go": text, "main.go": GO_HARNESS, **_go_module()},
        )  # fmt: skip
        return _result(done, rig)
    raise AssertionError(f"no harness for {client}")


@requires_docker
def test_the_rig_is_the_products_poolers_behind_the_edges_tls(rig: TlsRig) -> None:
    """What the executions below stand on: the two poolers read their modes,
    their prepared-statement allowance and their `search_path` tracking from
    `compose.yaml`'s own entrypoints."""
    for name, mode in ((POOL, "transaction"), (DIRECT, "session")):
        reading = rig.poolers.config(rig.poolers.poolers[name])
        assert reading["pool_mode"] == mode
        assert reading["max_prepared_statements"] == "100"
        assert "search_path" in reading["track_extra_parameters"].lower()


@requires_docker
@pytest.mark.parametrize("client", SERVED)
def test_each_served_snippet_runs_through_its_doors_with_verified_tls(
    rig: TlsRig, client: str
) -> None:
    """The served text, verbatim but for the password, in the client's image:
    the pooled door's work as `customer_app` with a parameterised query and a
    named prepared statement through the transaction pooler, and the direct
    door's migration as `customer_admin` wherever the text names that door."""
    found = _execute(rig, client)
    if client in ("psql", "env"):
        lines = found[0]["lines"]
        table = "psql_rows" if client == "psql" else "env_rows"
        assert lines[:3] == ["user=customer_app", "7", "42"], (table, lines)
        assert lines[3] == "user=customer_admin rows=1", lines
        if client == "env":
            assert found[1] == {"user": "customer_app", "n": 42}
    elif client == "prisma":
        assert found == [{"rows": 3, "user": "customer_app", "n": 7, "found": 18}]
    elif client == "node-pg":
        # 3 rounds x (1 + 2 + ... + 8)
        assert found == [{"user": "customer_app", "n": 7, "prepared": 108}]
    elif client == "psycopg":
        # One connection (the snippet opens one), so its prepared statement is
        # reused on one client connection only: mutation c does not reach it.
        assert found == [{"user": "customer_app", "values": [7, 42, 42]}]
    elif client == "drizzle":
        assert found == [{"user": "customer_app", "n": 7, "a": 1, "b": 2, "found": 36}]
    elif client == "go-pgx":
        # Four goroutines, ten statements each, on the DEFAULT mode: pgx's
        # cached prepared statements through the transaction pooler.
        assert found == [{"user": "customer_app", "rows": 40, "mode": "cache statement"}]


MISNAMED_CASES = [
    pytest.param(client, door, id=f"{client}-{door}")
    for client in SERVED
    for door in (("pooled", "direct") if client in BOTH_DOORS else ("pooled",))
]


@requires_docker
@pytest.mark.parametrize(("client", "door"), MISNAMED_CASES)
def test_each_served_snippet_refuses_a_certificate_for_another_name(
    rig: TlsRig, client: str, door: str
) -> None:
    """THE CONTROL (D499): the same text with one door's host a name the
    certificate does not carry -- which the edge answers, with the doors'
    certificate -- fails, in the client's own words for a name mismatch."""
    with pytest.raises(AssertionError) as refused:
        _execute(rig, client, misnamed=door)
    said = str(refused.value)
    assert "did not run" in said, f"{client} failed some other way:\n{said}"
    assert NAME_MISMATCH[client] in said, f"{client} was not refused for the name:\n{said}"
    assert "RESULT " not in said


@requires_docker
def test_the_misnamed_door_answers_a_client_that_does_not_verify(rig: TlsRig) -> None:
    """The control's control: the misnamed name routes to the pool and the
    edge answers it, so a client that does not check the name connects -- the
    refusals above are the name check, not a missing route."""
    done = _run(
        rig, "unverified", LOCK["PGBOUNCER_IMAGE"],
        f'psql "host={MISNAMED} port={rig.port} user=customer_app dbname=app sslmode=require" '
        "-XAtc 'SELECT current_user'",
        {}, env={"PGPASSWORD": rig.password},
    )  # fmt: skip
    assert (done.returncode, done.stdout.strip()) == (0, "customer_app"), rig.scrub(done.stderr)


@requires_docker
def test_drizzles_own_migrator_is_refused_on_the_direct_door(rig: TlsRig) -> None:
    """Why the Drizzle snippet sends migrations through psql: drizzle-orm's
    `migrate()` runs `CREATE SCHEMA IF NOT EXISTS` before anything, and the
    customer roles have no CREATE on the database (ADR 0269) -- measured with
    its default schema and with `migrationsSchema: "public"` alike. If this
    goes green the grants moved, and the snippet can gain `migrate()`."""
    harness = """\
import pg from "pg";
import { drizzle } from "drizzle-orm/node-postgres";
import { migrate } from "drizzle-orm/node-postgres/migrator";
const client = new pg.Client({ host: process.env.H, port: Number(process.env.P),
  user: "customer_admin", database: "app", password: process.env.PW,
  ssl: { rejectUnauthorized: true } });
await client.connect();
for (const options of [{}, { migrationsSchema: "public" }]) {
  try {
    await migrate(drizzle(client), { migrationsFolder: "./drizzle", ...options });
    console.log("RESULT " + JSON.stringify({ migrated: true }));
  } catch (error) {
    console.log("REFUSED " + String(error.cause && error.cause.message));
  }
}
await client.end();
"""
    journal = {
        "version": "7", "dialect": "postgresql",
        "entries": [{"idx": 0, "version": "7", "when": 1761696000000,
                     "tag": "0000_snippet", "breakpoints": True}],
    }  # fmt: skip
    done = _run(
        rig, "drizzle-migrator", _image("drizzle"), "node migrator.mjs",
        {"migrator.mjs": harness, "drizzle/0000_snippet.sql": DRIZZLE_MIGRATION,
         "drizzle/meta/_journal.json": json.dumps(journal)},
        mounts={"": "/app/w"}, workdir="/app/w",
        env={"NODE_EXTRA_CA_CERTS": "/rig/ca.crt", "H": DIRECT_HOST, "P": str(rig.port),
             "PW": rig.password},
    )  # fmt: skip
    printed = rig.scrub(done.stdout + done.stderr)
    assert done.returncode == 0, printed
    refusals = [line for line in done.stdout.splitlines() if line.startswith("REFUSED ")]
    assert refusals == ["REFUSED permission denied for database app"] * 2, printed

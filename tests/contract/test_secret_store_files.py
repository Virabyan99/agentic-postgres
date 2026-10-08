"""The self-hosted secret store's files (ADR 0262, REC-STORE-001).

`infra/secret-store/` is not part of the release: nothing renders it and no
product host runs it. It runs on its own host and holds every project's every
secret, the backup cipher pass among them, so what it publishes, which images
it trusts and whether its backup can be read by the host that wrote it are
contracts, asserted here from the committed files.
"""

from __future__ import annotations

import re

import pytest
import yaml

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.security]

STORE = REPO_ROOT / "infra" / "secret-store"
COMPOSE = STORE / "compose.yaml"
CADDYFILE = STORE / "Caddyfile"
BACKUP = STORE / "backup.sh"

#: The names whose values are secrets. Each lives in exactly one env file
#: (`ENV_FILES`) and never in a compose `environment` block or a literal.
SECRET_NAMES = {
    "infisical.env": ("ENCRYPTION_KEY", "AUTH_SECRET", "DB_CONNECTION_URI"),
    "db.env": ("POSTGRES_PASSWORD",),
    "backup.env": ("RCLONE_CONFIG_STORE_ACCOUNT", "RCLONE_CONFIG_STORE_KEY"),
}

#: Which service reads which env file -- one each, and no other.
ENV_FILES = {"backend": "infisical.env", "db": "db.env"}

DIGEST = re.compile(r"^docker\.io/[a-z0-9./-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")


def _model() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _services() -> dict[str, dict]:
    return _model()["services"]


def _logical_lines(text: str) -> list[str]:
    """Shell lines with backslash continuations joined, comments dropped."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return [
        line for line in joined.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]


def test_every_image_is_a_tag_pinned_by_digest() -> None:
    """A tag says which release; the digest says which bytes. A tag alone is
    whatever the registry serves on the day the host pulls."""
    images = {name: service["image"] for name, service in _services().items()}
    assert set(images) == {"backend", "db", "redis", "edge"}
    for name, image in images.items():
        assert DIGEST.fullmatch(image), f"{name}: {image!r} is not a tag pinned by digest"
    rclone = re.search(
        r'^RCLONE_IMAGE="([^"]+)"$', BACKUP.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert rclone and DIGEST.fullmatch(rclone.group(1)), "backup.sh's rclone image is not pinned"


def test_only_the_backend_publishes_and_only_on_loopback() -> None:
    """The backend answers 127.0.0.1:8080, which only the host-network edge
    reaches; the database and Redis publish nothing. A published port is
    reachable past ufw (Docker's NAT), which is why the edge is not published
    either but runs on the host network (D2250)."""
    services = _services()
    assert services["backend"].get("ports") == ["127.0.0.1:8080:8080"]
    for name in ("db", "redis", "edge"):
        assert "ports" not in services[name], f"{name} publishes {services[name]['ports']}"
        assert "expose" not in services[name], f"{name} exposes {services[name]['expose']}"
    assert services["edge"].get("network_mode") == "host"
    for name in ("backend", "db", "redis"):
        assert services[name].get("network_mode") is None, f"{name} is on the host network"
        assert services[name].get("networks") == ["store"]


def test_each_secret_lives_in_one_env_file_that_one_service_reads() -> None:
    """The database never sees the encryption key, the backend never sees the
    backup credential, and no value is written in the compose file."""
    services = _services()
    for name, service in services.items():
        files = service.get("env_file", [])
        if name in ENV_FILES:
            assert files == [f"${{SECRET_STORE_ETC:-/etc/secret-store}}/{ENV_FILES[name]}"], (
                f"{name} reads {files}"
            )
        else:
            assert not files, f"{name} reads an env file it has no use for: {files}"
        environment = service.get("environment") or {}
        for secrets in SECRET_NAMES.values():
            for secret in secrets:
                assert secret not in environment, f"{name} sets {secret} in compose.yaml"
    backend = services["backend"]["environment"]
    assert backend["SITE_URL"] == "https://secrets.agenticpostgresql.com"
    assert backend["TELEMETRY_ENABLED"] == "false"


@pytest.mark.parametrize("env_file", sorted(SECRET_NAMES))
def test_the_env_examples_name_every_secret_and_hold_none(env_file: str) -> None:
    example = STORE / f"{env_file}.example"
    assignments = dict(
        line.split("=", 1)
        for line in example.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    for secret in SECRET_NAMES[env_file]:
        assert secret in assignments, f"{example.name} does not name {secret}"
        assert assignments[secret] == "", f"{example.name} holds a value for {secret}"


def test_the_dump_is_encrypted_before_anything_writes_or_uploads_it() -> None:
    """`pg_dump`'s output reaches `age --recipient` before any redirection,
    the file written is the encrypted one, and rclone copies only that file.
    The host keeps the RECIPIENT; the identity that decrypts is the
    operator's (D2239), so the host cannot read its own backups."""
    text = BACKUP.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text
    assert "umask 077" in text
    lines = _logical_lines(text)
    dumps = [line for line in lines if "pg_dump" in line]
    assert len(dumps) == 1, f"expected one pg_dump pipeline, found {dumps}"
    before, sep, after = dumps[0].partition('| age --recipient "${recipient}"')
    assert sep, f"pg_dump is not piped into age: {dumps[0]}"
    assert ">" not in before, f"the dump is redirected before it is encrypted: {before}"
    assert re.fullmatch(r'\s*> "\$\{partial\}"\s*', after), f"the encrypted dump goes to {after!r}"
    assert 'target="${OUT_DIR}/infisical-${stamp}.dump.age"' in lines
    assert 'partial="${target}.partial"' in lines
    assert 'name="$(basename "${target}")"' in lines
    copies = [line for line in lines if " copyto " in line]
    assert len(copies) == 1, f"expected one upload, found {copies}"
    assert '"/backups/${name}" "store:${BUCKET}/${name}"' in copies[0]
    assert '-v "${OUT_DIR}:/backups:ro"' in copies[0]
    assert "lsf --format s" in text, "the upload's size is never read back"


def test_the_edge_serves_only_the_store_name_with_no_admin_endpoint() -> None:
    text = CADDYFILE.read_text(encoding="utf-8")
    assert "admin off" in text
    sites = re.findall(r"^(\S+) \{$", text, re.MULTILINE)
    assert sites == ["secrets.agenticpostgresql.com"], sites
    assert "reverse_proxy 127.0.0.1:8080" in text


def test_the_backup_runs_nightly_and_catches_up_after_downtime() -> None:
    timer = (STORE / "secret-store-backup.timer").read_text(encoding="utf-8")
    service = (STORE / "secret-store-backup.service").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 05:15:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "ExecStart=/usr/local/sbin/secret-store-backup" in service
    assert "Type=oneshot" in service


def test_both_gates_lint_the_store_script() -> None:
    """A script nothing lints is a script whose refusals nobody checks; the
    newest session gate repeats session-01's line, so both carry it."""
    for gate in ("session-01-check.sh", "session-38-check.sh"):
        text = (REPO_ROOT / "bin" / gate).read_text(encoding="utf-8")
        assert re.search(r"^\s*shellcheck .*infra/secret-store/\*\.sh", text, re.MULTILINE), gate


def test_no_store_file_holds_anything_shaped_like_a_key() -> None:
    """No file under infra/secret-store carries anything shaped like a key:
    an age identity, a 32-hex encryption key or a base64 secret of 32 bytes."""
    shapes = (
        re.compile(r"AGE-SECRET-KEY-1[0-9A-Z]+"),
        re.compile(r"=[0-9a-f]{32}\b"),
        re.compile(r"=[A-Za-z0-9+/]{43}="),
    )
    for path in sorted(STORE.iterdir()):
        text = path.read_text(encoding="utf-8")
        for shape in shapes:
            assert not shape.search(text), f"{path.name} holds something shaped like a key"

"""A connector's key on the host: derived from the active generation's master (ADR 0237).

**The second copy of one derivation, on purpose.** The auth image derives every
connector's key from `connector_signing_key` in
`services/auth-api/app/connector_signature.py`, and a `bin/` command may not
import a service module (ADR 0093). So `bin/connector.py key` derives it here,
and `test_connector_facility.py::test_the_two_key_derivations_agree` holds the
two copies to the same bytes on fixed vectors (D1828).

**Where the master is read is derived, never typed.** The generation is the one
`active-secret-generation.json` names -- the one the running `auth` container
mounts -- and the file within it is the secret contract's own consumer entry for
`connector_signing_key`, held by `auth` (`secrets_contract.consumer_named`). A
path an operator could type is a path that could name another project's
generation.

No value leaves this module in a message: every refusal names a path or a
reason, never a master or a key.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path
from typing import Any

from agentic_postgres import access_broker, secrets_contract

#: The derivation's label, byte for byte the image's (`CONNECTOR_KEY_LABEL`).
CONNECTOR_KEY_LABEL = b"apg-connector-key-v1\x00"

#: `app_private.connector.name`'s own constraint, the image's `NAME`.
NAME = re.compile(r"[a-z][a-z0-9-]{0,62}")

#: The master's shape: the generator's `random_hex`, 64 characters or more.
MASTER = re.compile(r"[0-9a-f]{64,}")

#: The one secret every connector's key is derived from, and the consumer that
#: holds it -- the directory its file lands in inside a generation.
SECRET_NAME = "connector_signing_key"  # noqa: S105 -- a secret's NAME, not a value
CONSUMER = "auth"

SECRET_ROOT = access_broker.SECRET_ROOT


class KeyRefused(ValueError):
    """A refusal with an exit code, naming no value."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def derive(master_hex: str, name: str) -> str:
    """The connector's key as 64 lowercase hex characters -- the image's `derive`."""
    if NAME.fullmatch(name) is None:
        raise ValueError("a connector name is lowercase letters, digits and hyphens")
    master = master_hex.strip()
    if MASTER.fullmatch(master) is None:
        raise ValueError("the connector master is not 64 or more lowercase hex characters")
    return hmac.new(
        bytes.fromhex(master), CONNECTOR_KEY_LABEL + name.encode("ascii"), hashlib.sha256
    ).hexdigest()


def master_path(
    project_key: str, contract: dict[str, Any], *, secret_root: Path = SECRET_ROOT
) -> Path:
    """The active generation's `connector_signing_key` file for one project.

    Exit code 4 when there is no generation to read: the state a running
    deployment would have is absent, which is the doctor's `EXIT_STATE`.
    """
    try:
        generation = access_broker.active_generation(project_key, secret_root=secret_root)
    except access_broker.BrokerError as error:
        raise KeyRefused(4, f"no active secret generation for {project_key}: {error}") from error
    _, consumer = secrets_contract.consumer_named(contract, SECRET_NAME, CONSUMER)
    relative = Path(secrets_contract.secret_source_path(project_key, generation, consumer))
    # `secret_source_path` roots the path at the fixed secret root; re-rooted
    # here so the one argument that can move it is the one a proof passes.
    return secret_root / relative.relative_to(secrets_contract.SECRET_ROOT)


def read_master(path: Path) -> str:
    """The master, read from a regular file that is not a symlink."""
    if path.is_symlink():
        raise KeyRefused(4, f"{path} is a symlink, which is not accepted")
    try:
        master = path.read_text(encoding="ascii").strip()
    except FileNotFoundError as error:
        raise KeyRefused(
            4,
            f"{path} does not exist: this project's active generation carries no connector "
            "master. Enable the facility in the manifest and redeploy first.",
        ) from error
    except (OSError, UnicodeDecodeError) as error:
        raise KeyRefused(4, f"{path} cannot be read: {type(error).__name__}") from error
    if MASTER.fullmatch(master) is None:
        raise KeyRefused(5, f"{path} is not 64 or more lowercase hex characters")
    return master


__all__ = [
    "CONNECTOR_KEY_LABEL",
    "CONSUMER",
    "SECRET_NAME",
    "SECRET_ROOT",
    "KeyRefused",
    "derive",
    "master_path",
    "read_master",
]

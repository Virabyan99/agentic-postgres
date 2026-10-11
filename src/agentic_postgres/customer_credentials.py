"""The customer poolers' userlists, from `pg_authid` (ADR 0269 item 5).

`bin/customer-credentials.sh sync` is the one writer. It reads each customer
role's SCRAM verifier out of the cluster -- the ONE source, so a restore or a
branch carries the credential with the data -- and writes one userlist per
pooler, one role per file (ADR 0269 item 3), then SIGHUPs both poolers.

What is here is the pure half and the file writes: the query, the parse, the
line, and the rename. Nothing here prints a verifier, and the command prints
none either: a line says which role has a credential, never what it is.

**No customer password exists anywhere on the host** (ADR 0269 item 5): the
verifier is computed on the customer's workstation and set by
`credential.rotate`. A NULL `rolpassword` -- a slot whose customer has set no
credential yet -- writes an EMPTY userlist, which the pooler starts with and
refuses every login against (rig 39c).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from agentic_postgres import deployed_output, runtime_override

#: The pooler image's uid and gid (`compose.yaml`'s `user: "70:70"`, measured
#: against the locked digest in Session 4). The userlists are `root:70` 0640 in
#: a `root:70` 0750 directory: the pooler reads them, nothing else but root does.
POOLER_GID = 70
DIRECTORY_MODE = 0o750
FILE_MODE = 0o640

#: Both roles in one query, through `container_exec.run` as `postgres`. The
#: names arrive as psql variables (`-v pool_role=...`), never interpolated.
VERIFIER_QUERY = (
    "SELECT rolname || '|' || coalesce(rolpassword, '') FROM pg_authid "
    "WHERE rolname IN (:'pool_role', :'direct_role') ORDER BY rolname;"
)

#: A role name as `naming` derives one -- what may be quoted into a userlist.
_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
#: PostgreSQL's SCRAM-SHA-256 verifier: `SCRAM-SHA-256$<iter>:<salt>$<stored>:<server>`.
_SCRAM = re.compile(r"^SCRAM-SHA-256\$[0-9]+:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+$")


def userlist_directory(key: str, *, root: Path = deployed_output.PROJECT_STATE_ROOT) -> Path:
    """`/etc/agentic-postgres/projects/<key>/customer-poolers`: derived, never
    typed -- the deploy binds it and the verb writes it from this one function."""
    return root / key / runtime_override.CUSTOMER_USERLIST_DIRNAME


class CredentialError(Exception):
    """The verifiers could not be read as what they must be."""


def parse_verifiers(stdout: str, roles: tuple[str, ...]) -> dict[str, str | None]:
    """`{role: verifier or None}` for exactly `roles`, out of `VERIFIER_QUERY`'s lines.

    A role the cluster does not have is an error, not an empty userlist: the
    bootstrap creates both on every project (ADR 0269 item 1), so its absence
    means this is not the cluster the document names. A non-SCRAM value (an
    MD5 hash, a plaintext) is refused: the pooler's `auth_type` is
    scram-sha-256, and a verifier it cannot use would refuse the customer with
    no word about why.
    """
    found: dict[str, str | None] = {}
    for line in stdout.splitlines():
        if not line.strip():
            continue
        role, separator, verifier = line.partition("|")
        if not separator or role not in roles:
            raise CredentialError("the cluster answered a row this query did not ask for")
        if verifier and not _SCRAM.match(verifier):
            raise CredentialError(f"{role}'s stored credential is not a SCRAM-SHA-256 verifier")
        found[role] = verifier or None
    missing = [role for role in roles if role not in found]
    if missing:
        raise CredentialError(f"the cluster has no role {', '.join(missing)}")
    return found


def userlist(role: str, verifier: str | None) -> str:
    """One pooler's userlist: one line naming one role, or empty for no credential."""
    if not _ROLE.match(role):
        raise CredentialError(f"not a derived role name: {role!r}")
    if verifier is None:
        return ""
    return f'"{role}" "{verifier}"\n'


def ensure_directory(directory: Path, *, gid: int | None = POOLER_GID) -> None:
    """The userlist directory, `root:70` 0750 -- a bind source, so it must exist
    before the poolers start, or Docker creates it in its place as root's 0755
    (D463). Its files are `ensure_userlist`'s and `write_userlist`'s."""
    directory.mkdir(mode=DIRECTORY_MODE, exist_ok=True)
    if gid is not None:
        os.chown(directory, 0, gid)
    directory.chmod(DIRECTORY_MODE)


def ensure_userlist(directory: Path, filename: str, *, gid: int | None = POOLER_GID) -> None:
    """Create `filename` empty if it is absent; leave an existing one alone."""
    if not (directory / filename).exists():
        write_userlist(directory, filename, "", gid=gid)


def write_userlist(
    directory: Path, filename: str, text: str, *, gid: int | None = POOLER_GID
) -> None:
    """Write beside and rename, so a pooler reloading on SIGHUP reads the old
    file or the new one and never half of either. The mode and owner are set
    on the descriptor BEFORE a byte is written."""
    staging = directory / f".{filename}.new"
    staging.unlink(missing_ok=True)
    descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    try:
        os.fchmod(descriptor, FILE_MODE)
        if gid is not None:
            os.fchown(descriptor, 0, gid)
        os.write(descriptor, text.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(staging, directory / filename)

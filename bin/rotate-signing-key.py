#!/usr/bin/env python3
"""The signing-key cutover: acknowledge, promote, retire (ADR 0088).

**There is no `prepare` here, and that is D249's rule rather than an omission.**
No command in this repository sets a value at the provider. A rotation is
prepared by putting the new key at `APG_AUTH_JWT_PREPARED_KEY` by hand and
redeploying: `materialize-secrets` writes it into the generation's root plane,
`render-jwks.py` sees the file and publishes its public half beside the active
key, and nothing has started signing with it. Everything from there is here.

**What each step is, and why it is a step.**

`status`
    What is published, what signs, and which verifiers have acknowledged. It
    reads the deployed document and the key set and reports the phase; it
    changes nothing and needs no privilege beyond reading root-owned state.

`acknowledge`
    Reads the key set **out of each verifier's running container** and records
    its digest. Not off the host's copy of the file: the deploy writes the key
    set by atomic replace, which creates a new inode, and a file bind mount
    binds the inode -- so a container can be reading a file that no longer
    exists while the host holds the correct one. Measured, with an in-place
    rewrite as the control. Reading from inside is the only way to learn what a
    verifier actually has.

`promote`
    The irreversible step, and it is refused unless every verifier has
    acknowledged **this** key set. A running PostgREST never re-reads its key
    set -- measured -- so a verifier that was not recreated cannot have
    acknowledged, and promoting past it would sign tokens it refuses.

`retire`
    Refused before the deadline. Removing the retiring key early refuses tokens
    that are still inside their own lifetime, and that failure arrives at
    whoever holds one with no cause visible from where they stand.

`abandon`
    The only rollback, available for exactly one phase. Before promotion nothing
    signs with the incoming key, so withdrawing it costs nothing. After
    promotion there is no way back and the recovery is to complete forward.

Exit codes (runbook section 2 convention):
  0  the step completed
  2  invalid operator input
  3  missing local prerequisite, or not root
  5  the deployed state is unusable
  6  the step was refused by a rule -- see the message
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import deployed_output, jwt_keys, runtime_override
from agentic_postgres.jwt_keys import JwkError

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_STATE = 5
EXIT_REFUSED = 6


class Verifier(NamedTuple):
    """One service that reads the published key set, and where it reads it.

    A row rather than a name, because the two things that differ between
    verifiers are the service and the path -- and a single `VERIFIER_JWKS_PATH`
    constant beside a list of names is what let the second verifier be
    inspectable at the first one's path (ADR 0122).

    `NamedTuple` and **not** `@dataclass`, which is a constraint of this file
    rather than a preference. The contract tests load this module with
    `spec_from_file_location` + `exec_module` and never register it in
    `sys.modules`; `dataclasses` looks the defining module up by name while
    processing annotations, so a dataclass here raises `AttributeError:
    'NoneType' object has no attribute '__dict__'` at import -- in the test, not
    in the command. Measured while writing this, and recorded because the next
    person to reach for a dataclass in a `bin/` command will meet it too.
    """

    service: str
    jwks_path: str


#: The verifiers this project has (ADR 0122).
#:
#: **Three, and until Session 8 Run 4 this tuple said one.** That is the entry
#: worth reading before adding to it. Session 7 made storage the third verifier
#: -- in ADR 0098, in `compose.yaml`, in `settings.py`, in `main.py` and in ADR
#: 0113's own Consequences section, which states in so many words that "storage
#: joins the recreate list" -- and this line did not move. The comment that used
#: to sit here said "one today ... and Session 9 adds agent-facing verifiers",
#: which was true when written and became the sentence that made the omission
#: look intended.
#:
#: What it cost, had a rotation been run: `promote` unblocks as soon as every
#: name here has acknowledged. With PostgREST alone listed, promotion would
#: switch the signing key while the storage container still held the retired
#: set -- and every token would be refused by one surface and served by the
#: other. That is D276's symptom exactly, and blocking it is the entire purpose
#: of the refusal `promote_rotation` implements.
#:
#: The auth service is deliberately NOT here, and this remains the one thing the
#: old comment had right. It is the issuer; it holds the private key and derives
#: its verification set from the half it signs with (ADR 0098), so an
#: acknowledgement from it would be the issuer agreeing with itself.
#:
#: `mcp` is Session 8's fourth verifier (ADR 0121). It is listed from the run
#: that builds it rather than from the run that publishes it, because "add it
#: when it starts" is the reasoning that produced the storage gap.
VERIFIERS: tuple[Verifier, ...] = (
    Verifier(
        service=runtime_override.REST_SERVICE,
        jwks_path=runtime_override.JWKS_CONTAINER_PATH,
    ),
    Verifier(
        service=runtime_override.STORAGE_SERVICE,
        jwks_path=runtime_override.STORAGE_JWKS_CONTAINER_PATH,
    ),
    Verifier(
        service=runtime_override.MCP_SERVICE,
        jwks_path=runtime_override.MCP_JWKS_CONTAINER_PATH,
    ),
)


def consumer_names() -> list[str]:
    """The roster as `jwt_keys` spells it: consumer names.

    Derived from `VERIFIERS` rather than written a second time, which is the
    whole reason the omission this function replaces could exist -- a second
    spelling of a list is a second place for it to be short by one.
    """
    return [verifier.service for verifier in VERIFIERS]


#: The overlap a promotion allows for, in seconds.
#:
#: The longest token lifetime this issuer mints, plus the leeway the verifier
#: applies. **The leeway is not a guess**: D241 measured the locked PostgREST
#: accepting a token up to 30 seconds past `exp` and 30 before `nbf`, bisected
#: -- 30s served, 31s refused, symmetrically. A window computed from the TTL
#: alone would retire the old key while tokens it signed were still being
#: accepted.
MAX_TOKEN_TTL_SECONDS = 900
CLOCK_SKEW_SECONDS = 30


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the deployed document and the secret generations are "
            "root-owned, and reading a verifier's key set means reaching its container.",
        )


def load_document(path: Path) -> dict:
    if not path.is_file():
        raise OperatorError(EXIT_STATE, f"no deployed document at {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise OperatorError(EXIT_STATE, f"{path} is not readable as JSON: {error}") from error


def key_state(document: dict) -> dict:
    """The `jwt` block's key members, validated before anything acts on them."""
    jwt = document.get("jwt") or {}
    if jwt.get("status") != "ready":
        raise OperatorError(
            EXIT_STATE,
            "this deployment publishes no issuer (jwt.status is not `ready`). There is "
            "no key set to rotate.",
        )
    state = {
        member: jwt.get(member)
        for member in (
            "algorithm",
            "active_kid",
            "verification_kids",
            "temporary",
            "retire_after",
            "verifier_acknowledgements",
        )
    }
    try:
        return jwt_keys.validate_key_state(state)
    except JwkError as error:
        raise OperatorError(EXIT_STATE, f"the deployed key state is unusable: {error}") from error


def container_for(project_key: str, service: str) -> str:
    """The running container for one project's service, by label.

    Found rather than predicted. `naming` predicts Compose's container name and
    the model deliberately does not enforce it with `container_name:` (D55), so
    a command that built the name would be depending on a convention this
    repository has chosen not to depend on. The labels are the model's own.
    """
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=apg.project.key={project_key}",
            "--filter",
            f"label=com.docker.compose.service={service}",
            "--format",
            "{{.Names}}",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    names = [line for line in result.stdout.splitlines() if line.strip()]
    if len(names) != 1:
        raise OperatorError(
            EXIT_STATE,
            f"expected exactly one running `{service}` container for {project_key}, "
            f"found {names or 'none'}. A verifier that is not running cannot acknowledge, "
            "and that is the state promotion is meant to be blocked by.",
        )
    return names[0]


def read_command(container: str, jwks_path: str) -> list[str]:
    """The command that reads one container's copy of the key set.

    Built by a pure function so the shape is assertable offline. `-` streams the
    archive to stdout, which is what keeps this a read with no temporary file to
    clean up or to leave a key set lying in.
    """
    return ["docker", "cp", f"{container}:{jwks_path}", "-"]


def loaded_digest(container: str, jwks_path: str) -> str:
    """The sha256 of the key set as THIS container holds it, at ITS path.

    A read of the container's filesystem, not of the host path. The two differ
    exactly when it matters: a replaced file leaves the container bound to the
    previous inode, so the host shows the new set and the process is verifying
    against the old one.

    **`docker cp`, not `docker exec … cat`,** and that is a correction rather
    than a preference (ADR 0122). Measured against the locked images: the
    PostgREST image is distroless and has neither `cat` nor `sh` -- both exit
    **127**, *"executable file not found in $PATH"* -- while `docker cp` on the
    same image exits 0. The control is the `python:3.12-slim` the other two
    verifiers run, where both binaries are present. So the previous
    implementation could not read the digest of the only verifier it knew about,
    and `acknowledge` could never unblock a promotion (D305, D411, D427).

    `docker cp` streams a tar archive, so the member is extracted here. The
    digest is of the FILE's bytes, which is what `published_digest` is a digest
    of -- hashing the archive would be a stable, plausible, wrong number.
    """
    result = subprocess.run(
        read_command(container, jwks_path),
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise OperatorError(
            EXIT_STATE,
            f"{container} could not read {jwks_path}: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}",
        )
    return hashlib.sha256(_only_member(result.stdout, container, jwks_path)).hexdigest()


def _only_member(archive: bytes, container: str, jwks_path: str) -> bytes:
    """The single file inside a `docker cp` stream.

    Refuses anything other than exactly one regular file. A directory, or two
    members, means the path named something other than the key set -- and
    hashing the first member of a surprise would produce a digest that simply
    never matches, which reads as "this verifier is behind" rather than as "this
    command was pointed at the wrong thing".
    """
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        members = [member for member in bundle.getmembers() if member.isfile()]
        if len(members) != 1:
            raise OperatorError(
                EXIT_STATE,
                f"{container}:{jwks_path} is not a single file "
                f"({len(members)} regular files in the copy)",
            )
        extracted = bundle.extractfile(members[0])
        if extracted is None:  # pragma: no cover -- isfile() has already excluded this
            raise OperatorError(EXIT_STATE, f"{container}:{jwks_path} could not be read")
        return extracted.read()


def published_digest(document: dict) -> str:
    digest = (document.get("jwt") or {}).get("public_jwks_sha256")
    if not digest:
        raise OperatorError(EXIT_STATE, "the deployed document records no published key set")
    return str(digest)


def write_back(path: Path, document: dict, state: dict) -> None:
    """Persist the key members back into the deployed document.

    The whole document is rewritten through `deployed_output`, so it is
    validated against the schema on the way out. A rotation step that wrote a
    document the schema would refuse would be a rotation that made the next
    deploy unable to read its own state.
    """
    document = {**document, "jwt": {**document["jwt"], **state}}
    deployed_output.write_deployed_document(document, path)


# ---------------------------------------------------------------------------
# The steps
# ---------------------------------------------------------------------------


def describe(document: dict, state: dict) -> None:
    kids = state["verification_kids"]
    print(f"issuer        {document['jwt']['issuer']}")
    print(f"published     {published_digest(document)}")
    print(f"active        {state['active_kid']}")
    for kid in kids:
        marker = "signing" if kid == state["active_kid"] else "verify-only"
        print(f"  {kid}  {marker}")
    if len(kids) == 1:
        print("phase         steady -- one key, nothing in flight")
    elif state["retire_after"] is None:
        print("phase         PREPARED -- two keys published, the old one still signs")
    else:
        print(f"phase         PROMOTED -- retiring the old key after {state['retire_after']}")

    acknowledgements = state["verifier_acknowledgements"]
    if acknowledgements is None:
        print("acknowledged  nothing has been asked")
        return
    behind = jwt_keys.unacknowledged(
        state, consumers=consumer_names(), jwks_sha256=published_digest(document)
    )
    for verifier in VERIFIERS:
        held = acknowledgements.get(verifier.service)
        if held is None:
            print(f"  {verifier.service:12s} has not acknowledged")
        elif held == published_digest(document):
            print(f"  {verifier.service:12s} holds the published set")
        else:
            print(f"  {verifier.service:12s} holds {held[:16]}…, which is NOT the published set")
    if behind:
        print(f"promotion     BLOCKED on {behind}")
    else:
        print("promotion     every verifier has acknowledged")


def acknowledge(arguments, path: Path, document: dict, state: dict) -> dict:
    published = published_digest(document)
    for verifier in VERIFIERS:
        container = container_for(document["project"]["key"], verifier.service)
        digest = loaded_digest(container, verifier.jwks_path)
        state = jwt_keys.record_acknowledgement(
            state, consumer=verifier.service, jwks_sha256=digest
        )
        if digest == published:
            print(f"  {verifier.service}: holds the published set ({digest[:16]}…)")
        else:
            # Recorded anyway, and this is deliberate. The record is what the
            # verifier HAS, not what it should have -- a step that refused to
            # write a disagreeing digest would leave the document saying nothing
            # where the truth is "this one is behind", and `promote` compares.
            session = document["deployed_through_session"]
            print(
                f"  {verifier.service}: holds {digest[:16]}…, "
                f"the published set is {published[:16]}…\n"
                f"    this verifier has NOT picked up the current key set. Recreate it:\n"
                f"    sudo bin/project-runtime.sh --host host.yaml"
                f" --project-key {document['project']['key']}"
                f" --through-session {session} down\n"
                f"    then redeploy. A restart is not enough and, after a key set has been\n"
                f"    replaced, is measured to leave the container unable to start at all."
            )
    del arguments, path
    return state


def promote(arguments, path: Path, document: dict, state: dict) -> dict:
    kids = state["verification_kids"]
    incoming = [kid for kid in kids if kid != state["active_kid"]]
    if len(incoming) != 1:
        raise OperatorError(
            EXIT_REFUSED,
            f"the published set is {kids}. Promotion needs exactly one prepared key "
            "beside the active one; prepare a rotation first.",
        )
    del arguments
    del path
    return jwt_keys.promote_rotation(
        state,
        incoming_kid=incoming[0],
        consumers=consumer_names(),
        jwks_sha256=published_digest(document),
        now=datetime.now(UTC),
        max_token_ttl_seconds=MAX_TOKEN_TTL_SECONDS,
        clock_skew_seconds=CLOCK_SKEW_SECONDS,
    )


def retire(arguments, path: Path, document: dict, state: dict) -> dict:
    del arguments, path, document
    return jwt_keys.retire_rotation(state, now=datetime.now(UTC))


def abandon(arguments, path: Path, document: dict, state: dict) -> dict:
    del arguments, path, document
    return jwt_keys.abandon_rotation(state)


STEPS = {"acknowledge": acknowledge, "promote": promote, "retire": retire, "abandon": abandon}

#: What an operator has to do after a step, because the step only records a
#: decision. The key set on disk is rewritten by `render-jwks.py` during a
#: deploy, and a verifier only picks one up by being recreated.
FOLLOW_UP = {
    "promote": (
        "The auth service must now be given the promoted key as its ACTIVE key:\n"
        "  set APG_AUTH_JWT_SIGNING_KEY to the prepared key's value at the provider,\n"
        "  clear APG_AUTH_JWT_PREPARED_KEY,\n"
        "  bring the project down, and redeploy.\n"
        "Until then the document says the new key signs and the service is still\n"
        "using the old one -- which is the one state this command cannot detect."
    ),
    "retire": (
        "Redeploy to republish the key set without the retired key, then recreate\n"
        "the verifiers so they stop accepting it."
    ),
    "abandon": (
        "Clear APG_AUTH_JWT_PREPARED_KEY at the provider and redeploy, so the\n"
        "prepared key stops being published and stops existing."
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rotate-signing-key",
        description="The signing-key cutover: acknowledge, promote, retire.",
        allow_abbrev=False,
    )
    parser.add_argument("--outputs", required=True, type=Path, metavar="FILE")
    parser.add_argument(
        "step",
        choices=["status", *STEPS],
        help="status reads and changes nothing; the others record a decision.",
    )
    arguments = parser.parse_args(argv)

    try:
        require_root()
        document = load_document(arguments.outputs)
        state = key_state(document)

        if arguments.step == "status":
            describe(document, state)
            return 0

        updated = STEPS[arguments.step](arguments, arguments.outputs, document, state)
        jwt_keys.validate_key_state(updated)
        write_back(arguments.outputs, document, updated)
        print(f"\nrotate-signing-key: {arguments.step} recorded in {arguments.outputs}")
        if arguments.step in FOLLOW_UP:
            print(f"\n{FOLLOW_UP[arguments.step]}")
        return 0
    except JwkError as error:
        print(f"rotate-signing-key: refused: {error}", file=sys.stderr)
        return EXIT_REFUSED
    except OperatorError as error:
        print(f"rotate-signing-key: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    raise SystemExit(main())

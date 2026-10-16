#!/usr/bin/env python
"""`apg login|logout|context|org|project|compute|operation|endpoint|branch`: the
management API.

Invoked by `bin/login.sh`, `bin/logout.sh`, `bin/context.sh`, `bin/org.sh`,
`bin/project.sh`, `bin/compute.sh`, `bin/operation.sh`, `bin/endpoint.sh` and
`bin/branch.sh`,
each passing its family as the first argument. Everything a
test can hold still -- the private state directory, the checked secret files,
the context, the refresh exchange, https -- is
`agentic_postgres.control_client`; this file is the verbs.

**A secret enters only through a 0600 file whose mode is checked, or a TTY**:
`--password-file`, `--key-file`, `--invitation-file`, `getpass`, and the TOTP
code on stdin (`--totp-code-stdin`) or at a prompt. **A secret leaves only
through `--output FILE`** (written once, 0600, refused if it exists, checked
before the server mints anything) **or a terminal**: no verb prints a token,
key or seed to a stdout that is not a TTY.

A live session is ended by `logout`, never dropped: a login refuses while one
is held. A key context is forgotten by `logout`, never revoked (`org
key-revoke` does that).

**A project's first administrator is handed over by hash** (ADR 0260, D2163):
`project create` mints the token, keeps it in `handoffs/<operation-id>` (0600,
in the 0700 state directory) and sends only its SHA-256; `project claim`
presents it to the PROJECT's own `/auth/reset-password` -- never to the
control plane -- and removes the file once the project accepted it. **An
export's download URL is a one-time bearer credential** (ADR 0259): `project
export` waits for the operation, downloads the archive without following a
redirect, checks its SHA-256 against the operation's result, and writes it
0600 to `--output`; the URL is printed nowhere.

**A customer's database password never leaves this machine** (Session 39, ADR
0269, D2353): `endpoint credential` generates it here, writes it ONCE to
`--password-file` (0600, refused if it exists, written before anything is
sent) and sends only its SCRAM-SHA-256 verifier (`agentic_postgres.scram`);
`endpoint connect` hands it to a local `psql` through a 0600 `PGPASSFILE` in a
private temporary directory, removed when psql ends, never through an argument
or the environment.

**A branch's two passwords never leave this machine either** (Session 40, ADR
0271, D2449): `branch create|reset` generate them here, write each ONCE to
`--password-dir D` as `D/<key>/<branch>/customer_app` and `customer_admin`
(0600, `O_EXCL`, every directory made 0700 and chmod'ed, D2417) before
anything is sent, and send only their verifiers. `branch create --at T` is a
restore to a point (`restore.create`); there is no customer verb named
`backup` or `restore` -- those are the operator's root commands (D2437).

Exit codes: 0 ok; 2 usage; 3 no context, no credential, an unusable local file,
or not https; 5 refused by the server, or the operation failed; 6 the server
unreachable or unreadable, or an outcome that could not be determined; 7
`wait` (and `export`) stopped at its own `--timeout`.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import control_client as cc  # noqa: E402
from agentic_postgres import scram  # noqa: E402
from agentic_postgres.control_client import ClientError  # noqa: E402

ROLES = ("owner", "admin", "member", "viewer")

#: The compute profiles a project may ask for (ADR 0258) -- the request's
#: schema validates them too; listed here so `--help` names them.
PROFILES = ("small", "standard", "large")

#: `wait`'s own timeout, distinct from every server answer (D2169).
EXIT_TIMEOUT = 7

#: How often `wait` reads the operation, and how long it waits by default: a
#: creation takes minutes (D2184). Session 41 (D2516): past the longest
#: operation bound -- a branch's 3,600 s (`bin/reconciler.py`
#: OPERATION_SECONDS_BY_TYPE, held below this by test_restore_promotion_bound).
POLL_SECONDS = 5
WAIT_SECONDS = 3900

#: The terminal states, and the one that is a success.
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


# ---------------------------------------------------------------------------
# Reading what the person gives
# ---------------------------------------------------------------------------


def read_password(password_file: str | None, prompt: str, *, confirm: bool = False) -> str:
    if password_file is not None:
        text = cc.read_private_file(Path(password_file)).decode("utf-8").strip("\n")
        if not text:
            raise ClientError(cc.EXIT_PREREQUISITE, f"{password_file} is empty")
        return text
    if not sys.stdin.isatty():
        raise ClientError(
            cc.EXIT_PREREQUISITE,
            "no TTY to prompt at and no --password-file: a password is read from a prompt or "
            "a 0600 file, never an argument or the environment",
        )
    first = getpass.getpass(prompt)
    if confirm and getpass.getpass("repeat: ") != first:
        raise ClientError(cc.EXIT_USAGE, "the two passwords differ")
    return first


def read_code(from_stdin: bool) -> str:
    if from_stdin:
        code = sys.stdin.readline().strip()
    elif sys.stdin.isatty():
        code = getpass.getpass("second-factor code: ").strip()
    else:
        raise ClientError(
            cc.EXIT_PREREQUISITE,
            "no TTY to prompt at: pass the code on stdin with --totp-code-stdin",
        )
    if not (len(code) == 6 and code.isdigit()):
        raise ClientError(cc.EXIT_USAGE, "a second-factor code is six digits")
    return code


def read_invitation(path: str) -> str:
    token = cc.read_private_file(Path(path)).decode("utf-8", errors="replace").strip()
    if not token or any(c.isspace() for c in token):
        raise ClientError(cc.EXIT_PREREQUISITE, f"{path} does not hold one invitation token")
    return token


def organization_id(text: str) -> str:
    try:
        return str(uuid.UUID(text))
    except ValueError as error:
        raise ClientError(cc.EXIT_USAGE, f"not an organisation id: {text!r}") from error


# ---------------------------------------------------------------------------
# The state a verb works from
# ---------------------------------------------------------------------------


def directory() -> Path:
    return cc.state_directory()


def session() -> cc.Session:
    where = directory()
    return cc.Session(where, cc.load_context(where))


def person_session() -> cc.Session:
    current = session()
    if current.is_key:
        raise ClientError(
            cc.EXIT_PREREQUISITE,
            "this verb needs a person's session; the context holds a management key",
        )
    return current


def current_organization(current: cc.Session, given: str | None) -> str:
    if given is not None:
        return organization_id(given)
    chosen = current.context.get("organization")
    if not chosen:
        raise ClientError(
            cc.EXIT_PREREQUISITE, "no organisation chosen: bin/org.sh use --organization ID"
        )
    return chosen


def refuse_a_live_session(where: Path) -> None:
    if cc.existing_state_directory(where) is not None and cc.load_session(where) is not None:
        raise ClientError(
            cc.EXIT_USAGE,
            "a session is already held; end it first with bin/logout.sh (a login never drops "
            "a live session)",
        )


def emit(document: Any, as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        for line in lines:
            print(line)


def table(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> list[str]:
    if not rows:
        return ["  (none)"]
    widths = {c: max(len(c), *(len(str(r.get(c) or "-")) for r in rows)) for c in columns}
    out = ["  " + "  ".join(c.upper().ljust(widths[c]) for c in columns)]
    for row in rows:
        out.append("  " + "  ".join(str(row.get(c) or "-").ljust(widths[c]) for c in columns))
    return out


def deliver_secret(output: str | None, text: str, what: str) -> None:
    """To `--output` (0600, new) or a terminal; never a non-TTY stdout."""
    if output is not None:
        cc.write_new_private_file(Path(output), (text + "\n").encode("utf-8"))
        print(f"{what} written to {output} (mode 0600); it is printed nowhere")
    else:
        print(text)


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


def _open_session(endpoint: str, username: str, password: str, code: str | None) -> tuple[int, Any]:
    body: dict[str, Any] = {"username": username, "password": password}
    if code is not None:
        body["totp_code"] = code
    return cc.send("POST", f"{endpoint}/sessions", body)


def login_password(arguments: argparse.Namespace) -> int:
    endpoint = cc.check_endpoint(arguments.endpoint)
    where = directory()
    refuse_a_live_session(where)
    password = read_password(arguments.password_file, f"password for {arguments.username}: ")
    code = read_code(True) if arguments.totp_code_stdin else None
    status, body = _open_session(endpoint, arguments.username, password, code)
    if (
        status == 401
        and code is None
        and isinstance(body, dict)
        and body.get("error") == "second_factor_required"
    ):
        if not sys.stdin.isatty():
            raise ClientError(
                cc.EXIT_REFUSED,
                "refused by the server (401): second_factor_required -- pass the code with "
                "--totp-code-stdin",
            )
        status, body = _open_session(endpoint, arguments.username, password, read_code(False))
    if status != 200 or not isinstance(body, dict):
        raise cc.refusal(status, body)
    cc.ensure_state_directory(where)
    cc.save_session(where, body["refresh_token"])
    context = {"endpoint": endpoint, "organization": None, "project": None, "session": True}
    cc.save_context(where, context)
    current = cc.Session(where, context)
    current.adopt_access_token(body["access_token"])
    me = current.call("GET", "/me")
    print(f"logged in to {endpoint} as {me['username']}")
    factor = me.get("second_factor") or {}
    if factor.get("required") and not factor.get("enabled"):
        print("enrol a second factor before anything else: bin/login.sh totp-enroll --output FILE")
    if len(me.get("organizations") or []) == 1:
        context["organization"] = me["organizations"][0]["id"]
        cc.save_context(where, context)
        print(f"using organisation {context['organization']}")
    return cc.EXIT_OK


def login_key(arguments: argparse.Namespace) -> int:
    endpoint = cc.check_endpoint(arguments.endpoint)
    where = directory()
    refuse_a_live_session(where)
    # absolute(), never resolve(): resolving follows a symlink, and the file
    # recorded and read must be the one named, checked with O_NOFOLLOW.
    key_file = Path(arguments.key_file).absolute()
    key = cc.read_key(key_file)
    # A key reaches only read routes and may lack `organizations:read`: a 403
    # is a key that authenticated; only a 401 is a key that did not.
    status, body = cc.send("GET", f"{endpoint}/organizations", bearer=key)
    if status == 401:
        raise cc.refusal(status, body)
    organization = None
    if status == 200 and isinstance(body, dict) and len(body.get("organizations") or []) == 1:
        organization = body["organizations"][0]["id"]
    elif status not in (200, 403):
        raise cc.refusal(status, body)
    cc.ensure_state_directory(where)
    cc.save_context(
        where,
        {"endpoint": endpoint, "organization": organization, "project": None,
         "key_file": str(key_file)},
    )  # fmt: skip
    print(f"using the key in {key_file} at {endpoint} (the key itself is stored nowhere else)")
    if organization:
        print(f"using organisation {organization}")
    return cc.EXIT_OK


def login_accept(arguments: argparse.Namespace) -> int:
    token = read_invitation(arguments.invitation_file)
    if arguments.username is None:
        # Signed in: the token alone, and the caller joins its organisation.
        if arguments.endpoint is not None or arguments.display_name or arguments.password_file:
            raise ClientError(
                cc.EXIT_USAGE,
                "signed in, accept takes --invitation-file alone; a new account takes "
                "--endpoint and --username",
            )
        current = person_session()
        accepted = current.call("POST", "/invitations/accept", {"invitation_token": token})
        print(f"joined organisation {accepted.get('organization_id')} as {accepted.get('role')}")
        if accepted.get("organization_id") and not current.context.get("organization"):
            current.context["organization"] = accepted["organization_id"]
            cc.save_context(current.directory, current.context)
        return cc.EXIT_OK
    if arguments.endpoint is None:
        raise ClientError(cc.EXIT_USAGE, "a new account needs --endpoint")
    endpoint = cc.check_endpoint(arguments.endpoint)
    where = directory()
    refuse_a_live_session(where)
    password = read_password(
        arguments.password_file, f"new password for {arguments.username}: ", confirm=True
    )
    display = arguments.display_name or arguments.username
    status, accepted = cc.send(
        "POST",
        f"{endpoint}/invitations/accept",
        {"invitation_token": token, "username": arguments.username,
         "display_name": display, "password": password},
    )  # fmt: skip
    if status != 200 or not isinstance(accepted, dict):
        raise cc.refusal(status, accepted)
    print(f"account {arguments.username} created ({accepted.get('user_id')})")
    status, body = _open_session(endpoint, arguments.username, password, None)
    if status != 200 or not isinstance(body, dict):
        raise cc.refusal(status, body)
    cc.ensure_state_directory(where)
    cc.save_session(where, body["refresh_token"])
    cc.save_context(
        where,
        {"endpoint": endpoint, "organization": accepted.get("organization_id"), "project": None,
         "session": True},
    )  # fmt: skip
    print(f"logged in to {endpoint} as {arguments.username}")
    if accepted.get("organization_id"):
        print(f"using organisation {accepted['organization_id']} as {accepted.get('role')}")
    return cc.EXIT_OK


def login_totp_enroll(arguments: argparse.Namespace) -> int:
    if arguments.output is not None:
        cc.refuse_existing_output(Path(arguments.output))
    elif not sys.stdout.isatty():
        raise ClientError(
            cc.EXIT_USAGE,
            "the seed is printed only to a terminal; pass --output FILE to write it to a "
            "0600 file instead",
        )
    current = person_session()
    enrolment = current.call("POST", "/me/totp")
    deliver_secret(
        arguments.output,
        f"{enrolment['otpauth_uri']}\n{enrolment['secret']}",
        "the otpauth:// URI and the seed",
    )
    print("add it to an authenticator, then: bin/login.sh totp-confirm")
    return cc.EXIT_OK


def login_totp_confirm(arguments: argparse.Namespace) -> int:
    current = person_session()
    code = read_code(arguments.totp_code_stdin)
    answer = current.call("POST", "/me/totp/confirm", {"totp_code": code})
    cc.remove_session(current.directory)
    print(
        f"second factor enabled; {answer.get('sessions_ended')} session(s) ended, this one "
        f"included. Log in again with a code: bin/login.sh password --endpoint "
        f"{current.endpoint} --username NAME"
    )
    return cc.EXIT_OK


# ---------------------------------------------------------------------------
# logout and context
# ---------------------------------------------------------------------------


def logout(arguments: argparse.Namespace) -> int:
    current = session()
    if current.is_key:
        (current.directory / cc.CONTEXT_NAME).unlink()
        emit(
            {"ended": "key_context", "key_file": current.context["key_file"]},
            arguments.json,
            [f"forgot the key context; the key in {current.context['key_file']} is NOT "
             "revoked (bin/org.sh key-revoke revokes it)"],
        )  # fmt: skip
        return cc.EXIT_OK
    refresh = cc.load_session(current.directory)
    if refresh is None:
        emit({"ended": None}, arguments.json, ["no session is held; nothing to end"])
        return cc.EXIT_OK
    status, body = cc.send(
        "DELETE", f"{current.endpoint}/sessions/current", {"refresh_token": refresh}
    )
    if status != 204:
        raise cc.refusal(status, body)
    cc.remove_session(current.directory)
    emit({"ended": "session"}, arguments.json, ["logged out: the session is ended on the server"])
    return cc.EXIT_OK


def context_show(arguments: argparse.Namespace) -> int:
    current = session()
    held = cc.load_session(current.directory) is not None
    shown = {
        "endpoint": current.endpoint,
        "credential": "key" if current.is_key else ("session" if held else "none"),
        "key_file": current.context.get("key_file"),
        "organization": current.context.get("organization"),
        "project": current.context.get("project"),
    }
    emit(shown, arguments.json, [f"  {name:<12}  {value or '-'}" for name, value in shown.items()])
    return cc.EXIT_OK


# ---------------------------------------------------------------------------
# org
# ---------------------------------------------------------------------------


def org_list(arguments: argparse.Namespace) -> int:
    current = session()
    rows = current.call("GET", "/organizations")["organizations"]
    chosen = current.context.get("organization")
    marked = [{**row, "current": "*" if row["id"] == chosen else ""} for row in rows]
    emit(rows, arguments.json, table(marked, ("current", "id", "role", "name")))
    return cc.EXIT_OK


def org_create(arguments: argparse.Namespace) -> int:
    current = person_session()
    created = current.call("POST", "/organizations", {"name": arguments.name})
    print(f"organisation {created['id']} created; you are its owner")
    if not current.context.get("organization"):
        current.context["organization"] = created["id"]
        cc.save_context(current.directory, current.context)
        print(f"using organisation {created['id']}")
    return cc.EXIT_OK


def org_use(arguments: argparse.Namespace) -> int:
    current = session()
    chosen = organization_id(arguments.organization)
    current.call("GET", f"/organizations/{chosen}")
    current.context.update(organization=chosen, project=None)
    cc.save_context(current.directory, current.context)
    print(f"using organisation {chosen}")
    return cc.EXIT_OK


def org_members(arguments: argparse.Namespace) -> int:
    current = session()
    org = current_organization(current, arguments.organization)
    rows = current.call("GET", f"/organizations/{org}/members")["members"]
    emit(rows, arguments.json, table(rows, ("user_id", "role", "username", "display_name")))
    return cc.EXIT_OK


def org_invite(arguments: argparse.Namespace) -> int:
    cc.refuse_existing_output(Path(arguments.output))
    current = person_session()
    body: dict[str, Any] = {}
    if not arguments.account:
        body = {"organization_id": current_organization(current, arguments.organization),
                "role": arguments.role}  # fmt: skip
    elif arguments.organization is not None:
        raise ClientError(cc.EXIT_USAGE, "an account invitation names no organisation")
    if arguments.expires_hours is not None:
        body["expires_in_hours"] = arguments.expires_hours
    minted = current.call("POST", "/invitations", body)
    deliver_secret(arguments.output, minted["invitation_token"], "the invitation token")
    kind = "an account" if arguments.account else f"{minted['role']} in {minted['organization_id']}"
    print(f"invitation {minted['id']} for {kind}, expires {minted['expires_at']}")
    return cc.EXIT_OK


def org_set_role(arguments: argparse.Namespace) -> int:
    current = person_session()
    org = current_organization(current, arguments.organization)
    changed = current.call(
        "PATCH", f"/organizations/{org}/members/{arguments.user}", {"role": arguments.role}
    )
    print(f"{changed['user_id']} is now {changed['role']} in {org}")
    return cc.EXIT_OK


def org_remove(arguments: argparse.Namespace) -> int:
    current = person_session()
    org = current_organization(current, arguments.organization)
    current.call("DELETE", f"/organizations/{org}/members/{arguments.user}")
    print(f"{arguments.user} removed from {org}; their keys there are revoked")
    return cc.EXIT_OK


def org_keys(arguments: argparse.Namespace) -> int:
    current = person_session()
    org = current_organization(current, arguments.organization)
    rows = current.call("GET", f"/organizations/{org}/keys")["keys"]
    shown = [{**row, "scopes": ",".join(row["scopes"])} for row in rows]
    emit(rows, arguments.json,
         table(shown, ("key_id", "name", "scopes", "last_used_at", "revoked_at")))  # fmt: skip
    return cc.EXIT_OK


def org_key_create(arguments: argparse.Namespace) -> int:
    cc.refuse_existing_output(Path(arguments.output))
    scopes = [scope for scope in arguments.scopes.split(",") if scope]
    if not scopes:
        raise ClientError(cc.EXIT_USAGE, "--scopes names at least one scope")
    current = person_session()
    org = current_organization(current, arguments.organization)
    minted = current.call(
        "POST", f"/organizations/{org}/keys", {"name": arguments.name, "scopes": scopes}
    )
    deliver_secret(arguments.output, minted["key"], "the key")
    print(f"key {minted['key_id']} ({','.join(minted['scopes'])}) for organisation {org}")
    return cc.EXIT_OK


def org_key_revoke(arguments: argparse.Namespace) -> int:
    current = person_session()
    org = current_organization(current, arguments.organization)
    current.call("DELETE", f"/organizations/{org}/keys/{arguments.key_id}")
    print(f"key {arguments.key_id} revoked; its next request is refused")
    return cc.EXIT_OK


# ---------------------------------------------------------------------------
# project
# ---------------------------------------------------------------------------


def project_list(arguments: argparse.Namespace) -> int:
    current = session()
    named = arguments.organization or current.context.get("organization")
    query = f"?organization={organization_id(named)}" if named else ""
    rows = current.call("GET", f"/projects{query}")["projects"]
    emit(
        rows, arguments.json, table(rows, ("key", "domain", "template_version", "organization_id"))
    )
    return cc.EXIT_OK


def _project_key(current: cc.Session, given: str | None) -> str:
    key = given or current.context.get("project")
    if not key:
        raise ClientError(
            cc.EXIT_PREREQUISITE, "no project chosen: bin/project.sh use --project-key KEY"
        )
    if not all(c.isalnum() or c == "-" for c in key):
        raise ClientError(cc.EXIT_USAGE, f"not a project key: {key!r}")
    return key


def project_use(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    record = current.call("GET", f"/projects/{key}")
    current.context.update(project=key, organization=record["organization_id"])
    cc.save_context(current.directory, current.context)
    print(f"using project {key} (organisation {record['organization_id']})")
    return cc.EXIT_OK


def project_show(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    record = current.call("GET", f"/projects/{key}")
    emit(record, arguments.json, [f"  {name:<16}  {value}" for name, value in record.items()])
    return cc.EXIT_OK


def _operation_id(text: str) -> str:
    try:
        return str(uuid.UUID(text))
    except ValueError as error:
        raise ClientError(cc.EXIT_USAGE, f"not an operation id: {text!r}") from error


def _accepted(answer: Any, as_json: bool, *, what: str) -> dict[str, Any]:
    operation = answer["operation"]
    lines = [
        f"{what}: operation {operation['id']} recorded ({operation['status']})",
        f"  follow it: bin/operation.sh wait --operation {operation['id']}",
    ]
    if answer.get("message"):
        lines.append(f"  {answer['message']}")
    emit(answer, as_json, lines)
    return operation


def project_create(arguments: argparse.Namespace) -> int:
    """The handoff token is kept BEFORE anything is sent, so a request the
    server recorded always has its token on this machine (ADR 0260)."""
    current = person_session()
    org = current_organization(current, arguments.organization)
    handoffs = cc.handoff_directory(current.directory)
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    pending = handoffs / f"pending-{digest[:16]}"
    cc.write_new_private_file(pending, (token + "\n").encode("utf-8"))
    body = {
        "organization": org,
        "name": arguments.name,
        "profile": arguments.profile,
        "admin_username": arguments.admin_username,
        "handoff_sha256": digest,
    }
    try:
        answer = current.call("POST", "/projects", body)
    except ClientError as error:
        if error.code == cc.EXIT_REFUSED:
            pending.unlink(missing_ok=True)  # refused: nothing was recorded
        else:
            print(f"project: whether the creation was recorded is not known; its handoff token "
                  f"is kept in {pending}", file=sys.stderr)  # fmt: skip
        raise
    operation = answer["operation"]
    kept = handoffs / _operation_id(str(operation["id"]))
    os.replace(pending, kept)
    _accepted(answer, arguments.json, what="creating")
    if not arguments.json:
        print(f"  the administrator's handoff token is in {kept} (0600); once the operation has "
              "succeeded: bin/project.sh claim --project-key KEY")  # fmt: skip
    return cc.EXIT_OK


def project_claim(arguments: argparse.Namespace) -> int:
    """The token presented to the PROJECT (its `routes.app`, read from the
    registry), never to the control plane; the file removed once accepted."""
    current = person_session()
    key = _project_key(current, arguments.project_key)
    record = current.call("GET", f"/projects/{key}")
    if not record.get("app_route"):
        raise ClientError(cc.EXIT_PREREQUISITE, f"{key} has no application address yet")
    app = cc.check_endpoint(str(record["app_route"]))
    operations = current.call("GET", f"/operations?organization={record['organization_id']}")
    created = [
        row
        for row in operations["operations"]
        if row["type"] == "project.create"
        and row["project_key"] == key
        and row["status"] == "succeeded"
    ]
    if not created:
        raise ClientError(cc.EXIT_PREREQUISITE, f"no succeeded creation of {key} is visible")
    # D2316/D2345: a key reused after a deletion has more than one succeeded
    # creation. The token names the creation: the one whose handoff file this
    # CLI holds is the one to claim -- never the first row, never a guess.
    handoffs = cc.handoff_directory(current.directory)
    held = [
        handoffs / _operation_id(str(row["id"]))
        for row in created
        if (handoffs / _operation_id(str(row["id"]))).is_file()
    ]
    if not held:
        raise ClientError(cc.EXIT_PREREQUISITE, f"no handoff token for {key} is held here")
    if len(held) > 1:
        raise ClientError(
            cc.EXIT_PREREQUISITE,
            f"{len(held)} succeeded creations of {key} have a token here",
        )
    (path,) = held
    token = cc.read_private_file(path).decode("utf-8").strip()
    password = read_password(
        arguments.password_file, f"new password for {key}'s administrator: ", confirm=True
    )
    status, body = cc.send(
        "POST", f"{app}/auth/reset-password", {"reset_token": token, "password": password}
    )
    if status != 200:
        raise cc.refusal(status, body)
    path.unlink()
    print(f"claimed: {key}'s administrator now has the password you chose; sign in at {app}")
    return cc.EXIT_OK


def project_status(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    record = current.call("GET", f"/projects/{key}")
    shown = {name: record.get(name) for name in ("key", "state", "managed_by", "profile", "region")}
    emit(shown, arguments.json, [f"  {name:<12}  {value or '-'}" for name, value in shown.items()])
    return cc.EXIT_OK


def project_sleep(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    _accepted(current.call("POST", f"/projects/{key}/sleep"), arguments.json, what="sleeping")
    return cc.EXIT_OK


def project_wake(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    _accepted(current.call("POST", f"/projects/{key}/wake"), arguments.json, what="waking")
    return cc.EXIT_OK


def project_delete(arguments: argparse.Namespace) -> int:
    current = person_session()
    key = _project_key(current, arguments.project_key)
    if arguments.confirm != key:
        raise ClientError(
            cc.EXIT_USAGE, f"--confirm must be the project's key exactly ({key}); nothing was sent"
        )
    _accepted(current.call("DELETE", f"/projects/{key}"), arguments.json, what="deleting")
    return cc.EXIT_OK


def project_export(arguments: argparse.Namespace) -> int:
    """Request, wait, download once, check, write 0600 -- the URL printed nowhere."""
    output = Path(arguments.output)
    cc.refuse_existing_output(output)
    current = person_session()
    key = _project_key(current, arguments.project_key)
    operation = current.call("POST", f"/projects/{key}/export")["operation"]
    print(f"exporting: operation {operation['id']} recorded; waiting for it", file=sys.stderr)
    final = _wait(current, str(operation["id"]), arguments.timeout, arguments.interval)
    if final["status"] != "succeeded":
        raise _unsuccessful(final)
    url = final.get("download_url")
    if not isinstance(url, str):
        raise ClientError(
            cc.EXIT_UNREACHABLE,
            "the export succeeded but its download URL was not handed to this command (it is "
            "handed out once); export again",
        )
    archive = cc.download(url)
    digest = hashlib.sha256(archive).hexdigest()
    result = final.get("result") or {}
    if digest != result.get("sha256") or len(archive) != result.get("size_bytes"):
        raise ClientError(
            cc.EXIT_UNREACHABLE,
            "the downloaded archive is not the one the export recorded; nothing was written",
        )
    cc.write_new_private_file(output, archive)
    emit(
        {
            "operation": final["id"],
            "output": str(output),
            "sha256": digest,
            "size_bytes": len(archive),
        },
        arguments.json,
        [f"exported {key} to {output} (0600): {len(archive)} bytes, sha256 {digest}"],
    )
    return cc.EXIT_OK


def project_backups(arguments: argparse.Namespace) -> int:
    """The project's backups and its restore window, as the server last read
    them (ADR 0273): a window, sleeping, or -- exit 6 -- could not be
    determined, with the reason. A reading that could not be made is never
    printed as a window (ADR 0195)."""
    current = session()
    key = _project_key(current, arguments.project_key)
    served = current.call("GET", f"/projects/{key}/backups")
    status = served.get("status") if isinstance(served, dict) else None
    if status == "window":
        lines = [
            f"{key}: restorable from {served['earliest']} to {served['latest']}",
            f"  last full backup {served.get('last_full_at') or '-'}; read {served['observed_at']}",
        ]
        if served.get("message"):
            lines.append(f"  {served['message']}")
        emit(served, arguments.json, lines)
        return cc.EXIT_OK
    if status == "sleeping":
        emit(served, arguments.json, [f"{key}: sleeping. {served.get('message') or ''}".rstrip()])
        return cc.EXIT_OK
    if status == "could_not_determine":
        reason = served.get("reason")
        emit(
            served, arguments.json, [f"{key}: the restore window could not be determined: {reason}"]
        )
        return cc.EXIT_UNREACHABLE
    raise ClientError(cc.EXIT_UNREACHABLE, "the backups reading answered in an unreadable shape")


# ---------------------------------------------------------------------------
# compute
# ---------------------------------------------------------------------------


def compute_get(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    record = current.call("GET", f"/projects/{key}")
    shown = {"key": key, "profile": record.get("profile")}
    emit(shown, arguments.json, [f"  {key}  {record.get('profile') or '-'}"])
    return cc.EXIT_OK


def compute_set(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    answer = current.call("PUT", f"/projects/{key}/compute", {"profile": arguments.profile})
    _accepted(answer, arguments.json, what=f"resizing to {arguments.profile}")
    return cc.EXIT_OK


# ---------------------------------------------------------------------------
# operation
# ---------------------------------------------------------------------------


def _shown(row: dict[str, Any]) -> dict[str, Any]:
    """An operation as printed: a download URL is never printed. If this read
    was the one that received it, the URL is gone with this process."""
    if "download_url" not in row:
        return row
    print(
        "operation: this read received the export's one-time download URL and discards it; "
        "bin/project.sh export fetches the archive itself",
        file=sys.stderr,
    )
    return {name: value for name, value in row.items() if name != "download_url"}


def _unsuccessful(row: dict[str, Any]) -> ClientError:
    reason = (row.get("result") or {}).get("reason")
    detail = f": {row.get('error_code')}" + (f" ({reason})" if reason else "")
    return ClientError(cc.EXIT_REFUSED, f"operation {row['id']} {row['status']}{detail}")


def _wait(current: cc.Session, operation: str, timeout: int, interval: int) -> dict[str, Any]:
    """Read the operation every `interval` s until it is terminal; a reading
    that fails is that failure (ADR 0195), never a guess; exit 7 at `timeout`."""
    operation = _operation_id(operation)
    deadline = time.monotonic() + timeout
    while True:
        row = current.call("GET", f"/operations/{operation}")
        if not isinstance(row, dict) or not isinstance(row.get("status"), str):
            raise ClientError(cc.EXIT_UNREACHABLE, "the operation answered in an unreadable shape")
        if row["status"] in TERMINAL:
            return row
        if time.monotonic() + interval > deadline:
            raise ClientError(
                EXIT_TIMEOUT,
                f"operation {operation} is still {row['status']} (step {row.get('step') or '-'}, "
                f"{row.get('progress')}%) after {timeout} s; it continues on the server",
            )
        time.sleep(interval)


def operation_show(arguments: argparse.Namespace) -> int:
    current = session()
    row = _shown(current.call("GET", f"/operations/{_operation_id(arguments.operation)}"))
    emit(row, arguments.json, [f"  {name:<12}  {value}" for name, value in row.items()])
    return cc.EXIT_OK


def operation_list(arguments: argparse.Namespace) -> int:
    current = session()
    org = current_organization(current, arguments.organization)
    rows = current.call("GET", f"/operations?organization={org}")["operations"]
    emit(rows, arguments.json,
         table(rows, ("id", "type", "project_key", "status", "step", "created_at")))  # fmt: skip
    return cc.EXIT_OK


def operation_wait(arguments: argparse.Namespace) -> int:
    current = session()
    row = _shown(_wait(current, arguments.operation, arguments.timeout, arguments.interval))
    emit(row, arguments.json, [f"operation {row['id']} {row['status']}"])
    if row["status"] != "succeeded":
        raise _unsuccessful(row)
    return cc.EXIT_OK


def operation_cancel(arguments: argparse.Namespace) -> int:
    current = session()
    row = current.call("POST", f"/operations/{_operation_id(arguments.operation)}/cancel")
    emit(row, arguments.json, [f"operation {row['operation']['id']} cancelled"])
    return cc.EXIT_OK


# ---------------------------------------------------------------------------
# endpoint (Session 39, ADR 0268, ADR 0269, D2353)
# ---------------------------------------------------------------------------

#: `--role` -> the customer role it names and the door that admits it: the
#: pooled door (transaction mode) admits `customer_app` only, the direct door
#: (a session) `customer_admin` only (ADR 0269 item 3).
ENDPOINT_ROLES = {"app": ("customer_app", "pooled"), "admin": ("customer_admin", "direct")}

_HOST = re.compile(r"(?=.{1,253}\Z)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def _door(current: cc.Session, key: str, role: str, branch: str | None = None) -> dict[str, Any]:
    """The door `role` opens, as the server recorded it -- each member checked,
    because a value from a response is about to become a psql argument. A
    BRANCH's door is the project's with the branch's own host (ADR 0271): its
    roles and database are the restored copy's, the same names."""
    _name, door = ENDPOINT_ROLES[role]
    served = current.call("GET", f"/projects/{key}/connections")
    found = served.get(door) if isinstance(served, dict) else None
    if not isinstance(found, dict):
        raise ClientError(cc.EXIT_UNREACHABLE, "the server's answer names no such door")
    host, port = found.get("host"), found.get("port")
    if branch is not None:
        recorded = current.call("GET", f"/projects/{key}/branches/{_branch_name(branch)}")
        if not isinstance(recorded, dict):
            raise ClientError(cc.EXIT_UNREACHABLE, "the branch answered in an unreadable shape")
        if recorded.get("state") != "ready":
            raise ClientError(
                cc.EXIT_PREREQUISITE, f"branch {branch} is {recorded.get('state')}, not ready"
            )
        host = recorded.get("pool_host" if door == "pooled" else "direct_host")
    user, database = found.get("user"), found.get("database")
    if (
        not isinstance(host, str)
        or not _HOST.fullmatch(host)
        or not isinstance(port, int)
        or isinstance(port, bool)
        or not 0 < port < 65536
        or not all(isinstance(v, str) and _IDENTIFIER.fullmatch(v) for v in (user, database))
    ):
        raise ClientError(cc.EXIT_UNREACHABLE, "the server's door is not a door this CLI can use")
    return {"host": host, "port": port, "user": user, "database": database}


def endpoint_show(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    served = current.call("GET", f"/projects/{key}/connections")
    lines = [f"{key}: two doors, both TLS (sslmode verify-full) on port 5432"]
    for flag, (role, door) in ENDPOINT_ROLES.items():
        found = served[door]
        lines.append(
            f"  {door:<7} {found['host']}:{found['port']}  user {found['user']}  "
            f"database {found['database']}  (--role {flag}, {role})"
        )
    lines.append(
        f"  the password is the file `credential` wrote; snippets say {served['password']}"
    )
    for client, snippet in served["snippets"].items():
        lines += ["", f"# {client}", snippet]
    emit(served, arguments.json, lines)
    return cc.EXIT_OK


def endpoint_credential(arguments: argparse.Namespace) -> int:
    """A new password for one customer role (ADR 0269): generated HERE, written
    once 0600 before anything is sent -- so a request the server recorded
    always has its password on this machine -- and only its verifier sent."""
    output = Path(arguments.password_file)
    cc.refuse_existing_output(output)
    current = person_session()
    key = _project_key(current, arguments.project_key)
    role, _door_name = ENDPOINT_ROLES[arguments.role]
    password = secrets.token_urlsafe(32)
    cc.write_new_private_file(output, (password + "\n").encode("utf-8"))
    body = {"role": role, "verifier": scram.verifier(password)}
    del password
    try:
        answer = current.call("POST", f"/projects/{key}/credentials", body)
    except ClientError as error:
        if error.code == cc.EXIT_REFUSED:
            output.unlink(missing_ok=True)  # refused: nothing was recorded
        else:
            print(f"endpoint: whether the credential was recorded is not known; the password "
                  f"it would set is kept in {output}", file=sys.stderr)  # fmt: skip
        raise
    if not arguments.wait:
        _accepted(answer, arguments.json, what=f"setting {role}'s password")
        if not arguments.json:
            print(f"  the password is in {output} (0600); it works once the operation succeeds")
        return cc.EXIT_OK
    operation = answer["operation"]
    print(f"endpoint: operation {operation['id']} recorded; waiting for it", file=sys.stderr)
    final = _wait(current, str(operation["id"]), arguments.timeout, arguments.interval)
    if final["status"] != "succeeded":
        raise _unsuccessful(final)
    emit(
        {"operation": final["id"], "role": role, "password_file": str(output)},
        arguments.json,
        [f"set: {role}'s password is in {output} (0600); the previous one no longer works"],
    )
    return cc.EXIT_OK


def _pgpass(value: str) -> str:
    """One `.pgpass` field: backslash and colon escaped, as libpq reads them."""
    return value.replace("\\", "\\\\").replace(":", "\\:")


def endpoint_connect(arguments: argparse.Namespace) -> int:
    """A local `psql` through one door, `verify-full` against the system's
    authorities. The password reaches psql through a 0600 `PGPASSFILE` in a
    private temporary directory -- never an argument, never `PGPASSWORD` -- and
    the directory is removed when psql ends, whatever ended it. psql is a CHILD
    with this terminal, not an `exec`: an exec could not remove the file."""
    current = session()
    key = _project_key(current, arguments.project_key)
    door = _door(current, key, arguments.role, arguments.branch)
    password = cc.read_private_file(Path(arguments.password_file)).decode("utf-8").strip()
    if not password or "\n" in password:
        raise ClientError(cc.EXIT_PREREQUISITE, f"{arguments.password_file} holds no password")
    extra = list(arguments.psql)
    if extra[:1] == ["--"]:
        extra = extra[1:]
    conninfo = (
        f"host={door['host']} port={door['port']} dbname={door['database']} "
        f"user={door['user']} sslmode=verify-full sslrootcert=system"
    )
    with tempfile.TemporaryDirectory(prefix="apg-connect-") as scratch:
        passfile = Path(scratch) / "pgpass"
        fields = (door["host"], str(door["port"]), door["database"], door["user"], password)
        cc.write_new_private_file(passfile, (":".join(map(_pgpass, fields)) + "\n").encode())
        del password
        environment = {k: v for k, v in os.environ.items() if k != "PGPASSWORD"}
        environment["PGPASSFILE"] = str(passfile)
        try:
            child = subprocess.Popen(["psql", conninfo, *extra], env=environment)
        except FileNotFoundError as error:
            raise ClientError(cc.EXIT_PREREQUISITE, "psql is not installed here") from error
        except OSError as error:
            # D2394: a psql that is there and cannot be run (no executable bit,
            # a wrong interpreter line) is a prerequisite, said -- not a traceback.
            raise ClientError(
                cc.EXIT_PREREQUISITE, f"psql could not be started: {error.strerror}"
            ) from error
        while True:
            try:
                return child.wait()
            except KeyboardInterrupt:
                # psql's to answer (it cancels the query); this process waits on.
                continue


# ---------------------------------------------------------------------------
# branch (Session 40, ADR 0271, ADR 0272, D2437, D2449)
# ---------------------------------------------------------------------------

#: A branch's two customer roles; each password is kept in a file of its name.
BRANCH_ROLES = ("customer_app", "customer_admin")

#: ADR 0272's bounds on an expiry, as the server holds them (a test holds the
#: two equal to `services/auth-api/app/operations.py`).
EXPIRY_BOUNDS = (15 * 60, 7 * 24 * 3600)

#: The server measures an expiry from the moment it RECEIVES it, so a request
#: for exactly the minimum arrives a little under it: at either bound the CLI
#: keeps this far inside, and the bound it offers is one the server accepts
#: (D2475).
EXPIRY_MARGIN_SECONDS = 60

_BRANCH = re.compile(r"[a-z][a-z0-9]{1,11}")
_INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z")
_DURATION = re.compile(r"([0-9]{1,6})([mhd]?)")
_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "": 3600}


def _branch_name(text: str) -> str:
    if not _BRANCH.fullmatch(text) or text == "main":
        raise ClientError(
            cc.EXIT_USAGE,
            f"not a branch name: {text!r} (a lowercase letter, then 1-11 lowercase letters or "
            "digits; `main` is the project itself)",
        )
    return text


def _instant(text: str) -> str:
    if not _INSTANT.fullmatch(text):
        raise ClientError(
            cc.EXIT_USAGE, f"not a UTC instant: {text!r} (YYYY-MM-DDTHH:MM:SS[.ffffff]Z)"
        )
    return text


def _expiry(text: str, *, now: datetime | None = None) -> str:
    """`--expires-in` (`15m`, `2h`, `7d`; a bare number is hours) as the instant
    the server is sent, kept a minute inside either bound."""
    match = _DURATION.fullmatch(text)
    if not match:
        raise ClientError(cc.EXIT_USAGE, f"not a duration: {text!r} (such as 15m, 2h or 7d)")
    seconds = int(match.group(1)) * _UNIT_SECONDS[match.group(2)]
    low, high = EXPIRY_BOUNDS
    if not low <= seconds <= high:
        raise ClientError(cc.EXIT_USAGE, "--expires-in is at least 15m and at most 7d")
    seconds = min(max(seconds, low + EXPIRY_MARGIN_SECONDS), high - EXPIRY_MARGIN_SECONDS)
    moment = (now or datetime.now(UTC)) + timedelta(seconds=seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _password_directory(given: str, key: str, branch: str) -> Path:
    """`D/<key>/<branch>/`: each level created 0700 and chmod'ed, or refused
    when it exists and is not private (D2417). D's own parent must exist."""
    base = Path(given)
    if not base.parent.is_dir():
        raise ClientError(cc.EXIT_USAGE, f"{base.parent} is not a directory; nothing was requested")
    where = base
    for part in ("", key, branch):
        where = where / part if part else where
        cc.ensure_state_directory(where)
    return where


def _branch_request(
    current: cc.Session,
    arguments: argparse.Namespace,
    key: str,
    branch: str,
    route: str,
    body: dict[str, Any],
    *,
    what: str,
) -> int:
    """Two passwords generated HERE and written once, 0600, BEFORE anything is
    sent -- so a request the server recorded always has its passwords on this
    machine -- and only their verifiers sent (D2449). A refusal removes them; an
    outcome that is not known keeps them and says where."""
    where = _password_directory(arguments.password_dir, key, branch)
    files = {role: where / role for role in BRANCH_ROLES}
    for path in files.values():
        if path.exists() or path.is_symlink():
            raise ClientError(
                cc.EXIT_USAGE,
                f"{path} already exists; nothing was requested (a reset's new passwords need "
                "the old ones moved away, or another --password-dir)",
            )
    verifiers: dict[str, str] = {}
    try:
        for role, path in files.items():
            password = secrets.token_urlsafe(32)
            cc.write_new_private_file(path, (password + "\n").encode("utf-8"))
            verifiers[role] = scram.verifier(password)
            del password
    except BaseException:
        for path in files.values():
            path.unlink(missing_ok=True)
        raise
    body = {
        **body,
        "app_verifier": verifiers["customer_app"],
        "admin_verifier": verifiers["customer_admin"],
    }
    try:
        answer = current.call("POST", route, body)
    except ClientError as error:
        if error.code == cc.EXIT_REFUSED:
            for path in files.values():
                path.unlink(missing_ok=True)  # refused: nothing was recorded
        else:
            print(f"branch: whether the request was recorded is not known; the passwords it "
                  f"would set are kept in {where}", file=sys.stderr)  # fmt: skip
        raise
    note = f"  the passwords are in {where} (0600); they work once the operation succeeds"
    return _branch_follow(current, arguments, answer, what=what, note=note)


def _branch_follow(
    current: cc.Session,
    arguments: argparse.Namespace,
    answer: dict[str, Any],
    *,
    what: str,
    note: str,
) -> int:
    if not arguments.wait:
        _accepted(answer, arguments.json, what=what)
        if not arguments.json:
            print(note)
        return cc.EXIT_OK
    operation = answer["operation"]
    print(f"branch: operation {operation['id']} recorded; waiting for it", file=sys.stderr)
    final = _wait(current, str(operation["id"]), arguments.timeout, arguments.interval)
    if final["status"] != "succeeded":
        raise _unsuccessful(final)
    result = {k: v for k, v in (final.get("result") or {}).items() if k != "steps"}
    lines = [f"{what}: done", *(f"  {name:<14}  {value}" for name, value in result.items())]
    lines.append(note.replace("they work once the operation succeeds", "they work now"))
    emit({"operation": final["id"], **result}, arguments.json, lines)
    return cc.EXIT_OK


def branch_create(arguments: argparse.Namespace) -> int:
    """A branch at the end of the archive, or -- `--at T` -- a restore to the
    point T into a new branch (`restore.create`, D2434). The project itself is
    never overwritten."""
    branch = _branch_name(arguments.branch)
    body: dict[str, Any] = {"branch": branch}
    if arguments.at is not None:
        body["target_time"] = _instant(arguments.at)
    if arguments.expires_in is not None:
        body["expires_at"] = _expiry(arguments.expires_in)
    current = person_session()
    key = _project_key(current, arguments.project_key)
    route = f"/projects/{key}/restores" if arguments.at is not None else f"/projects/{key}/branches"
    what = f"restoring {key} to {arguments.at} into {branch}" if arguments.at else (
        f"branching {key} into {branch}")  # fmt: skip
    return _branch_request(current, arguments, key, branch, route, body, what=what)


def branch_reset(arguments: argparse.Namespace) -> int:
    """The branch restored again -- to `--at T` or the end of the archive --
    with two new passwords; its names stay. What was written to it is lost."""
    branch = _branch_name(arguments.branch)
    body: dict[str, Any] = {}
    if arguments.at is not None:
        body["target_time"] = _instant(arguments.at)
    current = person_session()
    key = _project_key(current, arguments.project_key)
    route = f"/projects/{key}/branches/{branch}/reset"
    return _branch_request(current, arguments, key, branch, route, body,
                           what=f"resetting {key}'s {branch}")  # fmt: skip


def branch_delete(arguments: argparse.Namespace) -> int:
    branch = _branch_name(arguments.branch)
    if arguments.confirm != branch:
        raise ClientError(
            cc.EXIT_USAGE,
            f"--confirm must be the branch's name exactly ({branch}); nothing was sent",
        )
    current = person_session()
    key = _project_key(current, arguments.project_key)
    answer = current.call("DELETE", f"/projects/{key}/branches/{branch}")
    note = "  a branch is not backed up: what it held is gone; its passwords open nothing"
    return _branch_follow(current, arguments, answer, what=f"deleting {key}'s {branch}", note=note)


def branch_list(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    served = current.call("GET", f"/projects/{key}/branches")
    rows = served["branches"]
    lines = table(rows, ("name", "state", "reached_point", "expires_at", "pool_host"))
    emit(served, arguments.json, [*lines, f"  {served['notice']}"])
    return cc.EXIT_OK


def branch_show(arguments: argparse.Namespace) -> int:
    current = session()
    key = _project_key(current, arguments.project_key)
    found = current.call("GET", f"/projects/{key}/branches/{_branch_name(arguments.branch)}")
    lines = [f"  {name:<16}  {value if value is not None else '-'}"
             for name, value in found.items() if name != "notice"]  # fmt: skip
    emit(found, arguments.json, [*lines, f"  {found['notice']}"])
    return cc.EXIT_OK


# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------


def _verbs(family: argparse.ArgumentParser) -> Any:
    return family.add_subparsers(dest="verb", required=True)


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="cloud.py", add_help=False)
    families = top.add_subparsers(dest="family", required=True)

    login = _verbs(families.add_parser("login", add_help=False))
    verb = login.add_parser("password", add_help=False)
    verb.set_defaults(run=login_password)
    verb.add_argument("--endpoint", required=True)
    verb.add_argument("--username", required=True)
    verb.add_argument("--password-file")
    verb.add_argument("--totp-code-stdin", action="store_true")
    verb = login.add_parser("key", add_help=False)
    verb.set_defaults(run=login_key)
    verb.add_argument("--endpoint", required=True)
    verb.add_argument("--key-file", required=True)
    verb = login.add_parser("accept", add_help=False)
    verb.set_defaults(run=login_accept)
    verb.add_argument("--endpoint")
    verb.add_argument("--invitation-file", required=True)
    verb.add_argument("--username")
    verb.add_argument("--display-name")
    verb.add_argument("--password-file")
    verb = login.add_parser("totp-enroll", add_help=False)
    verb.set_defaults(run=login_totp_enroll)
    verb.add_argument("--output")
    verb = login.add_parser("totp-confirm", add_help=False)
    verb.set_defaults(run=login_totp_confirm)
    verb.add_argument("--totp-code-stdin", action="store_true")

    family = families.add_parser("logout", add_help=False)
    family.set_defaults(run=logout)
    family.add_argument("--json", action="store_true")

    context = _verbs(families.add_parser("context", add_help=False))
    verb = context.add_parser("show", add_help=False)
    verb.set_defaults(run=context_show)
    verb.add_argument("--json", action="store_true")

    org = _verbs(families.add_parser("org", add_help=False))
    for name, run in (("list", org_list), ("members", org_members), ("keys", org_keys)):
        verb = org.add_parser(name, add_help=False)
        verb.set_defaults(run=run)
        verb.add_argument("--json", action="store_true")
        if name != "list":
            verb.add_argument("--organization")
    verb = org.add_parser("create", add_help=False)
    verb.set_defaults(run=org_create)
    verb.add_argument("--name", required=True)
    verb = org.add_parser("use", add_help=False)
    verb.set_defaults(run=org_use)
    verb.add_argument("--organization", required=True)
    verb = org.add_parser("invite", add_help=False)
    verb.set_defaults(run=org_invite)
    kind = verb.add_mutually_exclusive_group(required=True)
    kind.add_argument("--account", action="store_true")
    kind.add_argument("--role", choices=ROLES)
    verb.add_argument("--output", required=True)
    verb.add_argument("--organization")
    verb.add_argument("--expires-hours", type=int)
    verb = org.add_parser("set-role", add_help=False)
    verb.set_defaults(run=org_set_role)
    verb.add_argument("--user", required=True, type=organization_id)
    verb.add_argument("--role", required=True, choices=ROLES)
    verb.add_argument("--organization")
    verb = org.add_parser("remove", add_help=False)
    verb.set_defaults(run=org_remove)
    verb.add_argument("--user", required=True, type=organization_id)
    verb.add_argument("--organization")
    verb = org.add_parser("key-create", add_help=False)
    verb.set_defaults(run=org_key_create)
    verb.add_argument("--name", required=True)
    verb.add_argument("--scopes", required=True)
    verb.add_argument("--output", required=True)
    verb.add_argument("--organization")
    verb = org.add_parser("key-revoke", add_help=False)
    verb.set_defaults(run=org_key_revoke)
    verb.add_argument("--key-id", required=True)
    verb.add_argument("--organization")

    project = _verbs(families.add_parser("project", add_help=False))
    verb = project.add_parser("list", add_help=False)
    verb.set_defaults(run=project_list)
    verb.add_argument("--organization")
    verb.add_argument("--json", action="store_true")
    verb = project.add_parser("use", add_help=False)
    verb.set_defaults(run=project_use)
    verb.add_argument("--project-key", required=True)
    verb = project.add_parser("show", add_help=False)
    verb.set_defaults(run=project_show)
    verb.add_argument("--project-key")
    verb.add_argument("--json", action="store_true")
    verb = project.add_parser("create", add_help=False)
    verb.set_defaults(run=project_create)
    verb.add_argument("--name", required=True)
    verb.add_argument("--profile", required=True, choices=PROFILES)
    verb.add_argument("--admin-username", required=True)
    verb.add_argument("--organization")
    verb.add_argument("--json", action="store_true")
    verb = project.add_parser("claim", add_help=False)
    verb.set_defaults(run=project_claim)
    verb.add_argument("--project-key")
    verb.add_argument("--password-file")
    for name, run in (("status", project_status), ("sleep", project_sleep),
                      ("wake", project_wake)):  # fmt: skip
        verb = project.add_parser(name, add_help=False)
        verb.set_defaults(run=run)
        verb.add_argument("--project-key")
        verb.add_argument("--json", action="store_true")
    verb = project.add_parser("delete", add_help=False)
    verb.set_defaults(run=project_delete)
    verb.add_argument("--project-key", required=True)
    verb.add_argument("--confirm", required=True)
    verb.add_argument("--json", action="store_true")
    verb = project.add_parser("export", add_help=False)
    verb.set_defaults(run=project_export)
    verb.add_argument("--project-key")
    verb.add_argument("--output", required=True)
    _waiting(verb)
    verb = project.add_parser("backups", add_help=False)
    verb.set_defaults(run=project_backups)
    verb.add_argument("--project-key")
    verb.add_argument("--json", action="store_true")

    compute = _verbs(families.add_parser("compute", add_help=False))
    verb = compute.add_parser("get", add_help=False)
    verb.set_defaults(run=compute_get)
    verb.add_argument("--project-key")
    verb.add_argument("--json", action="store_true")
    verb = compute.add_parser("set", add_help=False)
    verb.set_defaults(run=compute_set)
    verb.add_argument("--project-key")
    verb.add_argument("--profile", required=True, choices=PROFILES)
    verb.add_argument("--json", action="store_true")

    endpoint = _verbs(families.add_parser("endpoint", add_help=False))
    verb = endpoint.add_parser("show", add_help=False)
    verb.set_defaults(run=endpoint_show)
    verb.add_argument("--project-key")
    verb.add_argument("--json", action="store_true")
    verb = endpoint.add_parser("credential", add_help=False)
    verb.set_defaults(run=endpoint_credential)
    verb.add_argument("--project-key")
    verb.add_argument("--role", required=True, choices=tuple(ENDPOINT_ROLES))
    verb.add_argument("--password-file", required=True)
    verb.add_argument("--wait", action="store_true")
    _waiting(verb)
    verb = endpoint.add_parser("connect", add_help=False)
    verb.set_defaults(run=endpoint_connect)
    verb.add_argument("--project-key")
    verb.add_argument("--role", required=True, choices=tuple(ENDPOINT_ROLES))
    verb.add_argument("--password-file", required=True)
    verb.add_argument("--branch")
    verb.add_argument("psql", nargs=argparse.REMAINDER)

    operation = _verbs(families.add_parser("operation", add_help=False))
    for name, run in (("show", operation_show), ("cancel", operation_cancel)):
        verb = operation.add_parser(name, add_help=False)
        verb.set_defaults(run=run)
        verb.add_argument("--operation", required=True)
        verb.add_argument("--json", action="store_true")
    verb = operation.add_parser("list", add_help=False)
    verb.set_defaults(run=operation_list)
    verb.add_argument("--organization")
    verb.add_argument("--json", action="store_true")
    verb = operation.add_parser("wait", add_help=False)
    verb.set_defaults(run=operation_wait)
    verb.add_argument("--operation", required=True)
    _waiting(verb)

    branch = _verbs(families.add_parser("branch", add_help=False))
    for name, run in (("create", branch_create), ("reset", branch_reset)):
        verb = branch.add_parser(name, add_help=False)
        verb.set_defaults(run=run)
        verb.add_argument("--project-key")
        verb.add_argument("--branch", required=True)
        verb.add_argument("--password-dir", required=True)
        verb.add_argument("--at")
        if name == "create":
            verb.add_argument("--expires-in")
        verb.add_argument("--wait", action="store_true")
        _waiting(verb)
    verb = branch.add_parser("delete", add_help=False)
    verb.set_defaults(run=branch_delete)
    verb.add_argument("--project-key")
    verb.add_argument("--branch", required=True)
    verb.add_argument("--confirm", required=True)
    verb.add_argument("--wait", action="store_true")
    _waiting(verb)
    verb = branch.add_parser("list", add_help=False)
    verb.set_defaults(run=branch_list)
    verb.add_argument("--project-key")
    verb.add_argument("--json", action="store_true")
    verb = branch.add_parser("show", add_help=False)
    verb.set_defaults(run=branch_show)
    verb.add_argument("--project-key")
    verb.add_argument("--branch", required=True)
    verb.add_argument("--json", action="store_true")
    return top


def _seconds(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("at least 1")
    return value


def _waiting(verb: argparse.ArgumentParser) -> None:
    verb.add_argument("--timeout", type=_seconds, default=WAIT_SECONDS)
    verb.add_argument("--interval", type=_seconds, default=POLL_SECONDS)
    verb.add_argument("--json", action="store_true")


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
    except SystemExit:
        return cc.EXIT_USAGE
    try:
        return arguments.run(arguments)
    except ClientError as error:
        print(f"{arguments.family}: {error}", file=sys.stderr)
        return error.code
    except KeyboardInterrupt:
        print(f"{arguments.family}: interrupted", file=sys.stderr)
        return cc.EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())

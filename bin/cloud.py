#!/usr/bin/env python
"""`apg login|logout|context|org|project`: the management API from a terminal (D2066, D2067).

Invoked by `bin/login.sh`, `bin/logout.sh`, `bin/context.sh`, `bin/org.sh` and
`bin/project.sh`, each passing its family as the first argument. Everything a
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

Exit codes: 0 ok; 2 usage; 3 no context, no credential, an unusable local file,
or not https; 5 refused by the server; 6 the server unreachable or unreadable.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import control_client as cc  # noqa: E402
from agentic_postgres.control_client import ClientError  # noqa: E402

ROLES = ("owner", "admin", "member", "viewer")


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
    return top


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

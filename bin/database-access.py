#!/usr/bin/env python3
"""The database access broker, and the policy that decides what it hands out.

Two audiences in one file, on purpose.

*The broker operations* — ``endpoint`` and ``password`` — are reached only
through ``libexec/agentic-postgres-database-access``, the installed trampoline
that resolves which release deployed a project and execs that release's copy of
this program (ADR 0043). They run as root because the state they read is
root-owned, and they decide nothing: the decision is in
``agentic_postgres.access_policy`` and the resolution in
``agentic_postgres.access_broker``, both of which run under a test with no
privilege at all.

*The policy operations* — ``publish``, ``show`` and ``check`` — are the
operator's. ``check`` needs no root and no host, so a policy can be reviewed
before it is anywhere near a machine that would act on it.

**No path is accepted for state.** Not for the deployed document, not for the
port registry, not for the secret. ``publish`` takes a path because the operator
is handing over a file they wrote, and that file is validated and copied — the
published location is derived, never given. A broker that could be pointed at a
directory is a broker that can be pointed at any directory.

**The caller is resolved, not declared.** ``SUDO_UID`` is set by sudo from the
real invoker and cannot be forged by someone reaching this through the sudoers
rule, which is the only way an unprivileged account reaches it at all. There is
no ``--as-user``: an identity supplied on a command line is not an identity.

Exit codes follow the convention (D42, D87):
  0   success
  2   invalid operator input
  3   missing prerequisite, or not root
  4   missing runtime state
  5   a contract failure -- state that exists and cannot be acted on
  6   refused
  8   a secret could not be read
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import access_broker, access_policy
from agentic_postgres.access_broker import BrokerError

EXIT_INVALID = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 6

#: Not a caller-supplied path. Derived from the state root so that the one place
#: it is written and the one place it is read cannot drift.
POLICY_PATH = Path(access_policy.POLICY_PATH)


def fail(code: int, message: str) -> int:
    print(f"database-access: {message}", file=sys.stderr)
    return code


def caller_unix_user() -> str:
    """The account that invoked sudo, or ``root`` when there was no sudo.

    Root reaching this directly is permitted without consulting the policy, and
    that is not a hole: root can read every file the broker reads, so a policy
    check on root would be a ceremony that protects nothing while suggesting it
    protects something. The policy exists to bound *delegation* — which
    unprivileged account may have which credential — and delegation is exactly
    what ``SUDO_UID`` being present means.
    """
    raw = os.environ.get("SUDO_UID")
    if raw is None:
        return "root"
    try:
        return pwd.getpwuid(int(raw)).pw_name
    except (ValueError, KeyError):
        # A UID sudo set that no longer resolves: the account was removed
        # between the sudo and this call, or /etc/passwd is inconsistent. Either
        # way there is no name to match a grant against, and inventing one is
        # how a deleted account keeps its access.
        raise SystemExit(fail(EXIT_REFUSED, "refused.")) from None


def require_root(action: str) -> None:
    if os.geteuid() != 0:
        raise SystemExit(
            fail(
                EXIT_PREREQUISITE,
                f"{action} must run as root: the state it reads is root-owned. "
                "It is reached through /usr/local/libexec/agentic-postgres/database-access.",
            )
        )


# ---------------------------------------------------------------------------
# Broker operations
# ---------------------------------------------------------------------------


def command_endpoint(arguments: argparse.Namespace) -> int:
    require_root("endpoint")
    unix_user = caller_unix_user()
    try:
        access_broker.authorize(
            unix_user=unix_user, project_key=arguments.project_key, profile=arguments.profile
        )
        answer = access_broker.endpoint(arguments.project_key, arguments.profile)
    except BrokerError as error:
        return fail(error.code, str(error))

    print(json.dumps(answer, indent=2, sort_keys=True))
    return 0


def command_password(arguments: argparse.Namespace) -> int:
    require_root("password")
    unix_user = caller_unix_user()
    try:
        access_broker.authorize(
            unix_user=unix_user, project_key=arguments.project_key, profile=arguments.profile
        )
        value = access_broker.password(arguments.project_key, arguments.profile)
    except BrokerError as error:
        return fail(error.code, str(error))

    # Written to the descriptor rather than printed, and with no trailing
    # newline. `print` would add one, and a caller that reads the stream instead
    # of using command substitution would then hold a password with a newline
    # on the end -- which authenticates nowhere and looks like a wrong password.
    sys.stdout.write(value)
    sys.stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# Policy operations
# ---------------------------------------------------------------------------


def load_candidate(path: Path) -> dict:
    if path.is_symlink():
        raise SystemExit(fail(EXIT_INVALID, f"{path} is a symlink, which is not accepted"))
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(fail(EXIT_INVALID, f"{path} does not exist")) from None
    except json.JSONDecodeError as error:
        raise SystemExit(fail(EXIT_INVALID, f"{path} is not valid JSON: {error}")) from None

    try:
        return access_policy.validate(document)
    except access_policy.PolicyError as error:
        raise SystemExit(fail(5, f"{path} is not a usable access policy: {error}")) from None


def describe(policy: dict) -> str:
    if not policy["grants"]:
        return "  (no grants: this host delegates no database access)"
    lines = []
    for grant in sorted(policy["grants"], key=lambda g: (g["unix_user"], g["project_key"])):
        privileged = sorted(set(grant["profiles"]) & access_policy.PRIVILEGED_PROFILES)
        note = f"   << includes {', '.join(privileged)}" if privileged else ""
        lines.append(
            f"  {grant['unix_user']:<16} {grant['project_key']:<24} "
            f"{','.join(sorted(grant['profiles']))}{note}"
        )
    return "\n".join(lines)


def command_check(arguments: argparse.Namespace) -> int:
    policy = load_candidate(Path(arguments.policy).expanduser())
    print(
        f"database-access: {arguments.policy} is a valid policy with "
        f"{len(policy['grants'])} grant(s)"
    )
    print(describe(policy))
    return 0


def command_publish(arguments: argparse.Namespace) -> int:
    require_root("publish")
    policy = load_candidate(Path(arguments.policy).expanduser())

    if arguments.plan:
        print(f"database-access: would publish {len(policy['grants'])} grant(s) to {POLICY_PATH}")
        print(describe(policy))
        return 0

    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(policy, indent=2, sort_keys=True) + "\n"

    # Written beside and renamed. The broker may be reading this file right now,
    # and a truncated policy is one that denies everything -- silently, and only
    # for as long as the write takes, which is the hardest kind of failure to
    # reproduce afterwards.
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=POLICY_PATH.parent, delete=False, prefix=".policy."
    )
    try:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()

    staging = Path(handle.name)
    os.chmod(staging, stat.S_IRUSR | stat.S_IWUSR)
    os.chown(staging, 0, 0)
    staging.replace(POLICY_PATH)

    descriptor = os.open(POLICY_PATH.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    print(
        f"database-access: published {len(policy['grants'])} grant(s) to {POLICY_PATH} (0600 root)"
    )
    print(describe(policy))
    return 0


def command_show(arguments: argparse.Namespace) -> int:
    require_root("show")
    try:
        policy = access_broker.load_policy()
    except BrokerError as error:
        return fail(error.code, str(error))
    print(f"database-access: {POLICY_PATH}")
    print(describe(policy))
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="database-access",
        description="Resolve one access profile of one project, and manage the policy that "
        "decides who may. No secret is ever accepted as an argument.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("endpoint", "Print where to connect and as whom. Contains no secret."),
        ("password", "Print one profile's password on stdout, and nothing else."),
    ):
        sub = subcommands.add_parser(name, help=help_text)
        sub.add_argument("project_key")
        sub.add_argument("profile", choices=sorted(access_policy.PROFILE_SECRETS))
        sub.set_defaults(handler=command_endpoint if name == "endpoint" else command_password)

    publish = subcommands.add_parser("publish", help="Install a policy file atomically.")
    publish.add_argument("--policy", required=True, help="The candidate policy document.")
    publish.add_argument("--plan", action="store_true", help="Report without writing.")
    publish.set_defaults(handler=command_publish)

    check = subcommands.add_parser(
        "check", help="Validate a candidate policy. Needs no root and no host."
    )
    check.add_argument("--policy", required=True)
    check.set_defaults(handler=command_check)

    show = subcommands.add_parser("show", help="Print the published policy.")
    show.set_defaults(handler=command_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as error:
        # argparse exits 2 for a usage error, which is the convention's code for
        # invalid input already. Anything else it raises is --help.
        return int(error.code or 0)
    return int(arguments.handler(arguments))


if __name__ == "__main__":
    raise SystemExit(main())

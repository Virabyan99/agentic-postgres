#!/usr/bin/env python3
"""The object-storage operator surface: five verbs, and no way to name a key.

**Every verb that touches R2 runs inside the storage container** (ADR 0093). Not
a preference: the host has no `boto3`, no `botocore`, no venv on a deployment
host, and -- deliberately -- no R2 credential. The two credential halves are
materialized per consumer into files owned by uid 65532 inside one container's
generation, and that per-consumer materialization is what makes "the auth
service cannot read the R2 credential" a filesystem property rather than a rule
somebody keeps. A command that reproduced the S3 call here would need the
credential here, and would delete the property.

D292 is the record of the alternative being tried: `auth-admin.py` imported the
service's hasher, `argon2` exists only in that service's image, and the command
was unrunnable on the only machine it is ever run on.

**There is no verb that prints a credential** (D105), and no verb that takes a
bucket or an object key. The bucket comes from the deployed document, the prefix
with it, and the only keys this command ever handles are ones the database
already holds -- which it passes to the container and never prints.
`credential-digest` answers "which credential is mounted" with a **SHA-256**,
because that is the question an operator has after a rotation and the value is
not the answer to it.

**This command cannot administer the bucket, and that is structural** (ADR 0110).
Creating a bucket, reading its identity back and issuing or revoking a token are
Cloudflare REST API operations performed by a human with a Cloudflare API token
that no process in this repository holds. The runtime's S3 credential cannot do
any of them -- measured in Run 5: `CreateBucket` 403, `ListBuckets` 403,
`HeadBucket` on another bucket in the same account 403.

The verbs:

  status             What the plane holds, by state, plus the cleanup queue.
                     Read over the container-local privileged socket, like
                     `auth-admin list`. Names no key and no owner.
  cleanup            One sweep: expire stale intents, then collect what is
                     collectable. Runs the service's own `storage_cleanup` in
                     the service's own container.
  verify-credential  Does the mounted credential reach the configured bucket?
                     A HeadObject on a key that does not exist -- **nothing is
                     written**. Accepted looks like 404; refused looks like 403.
  credential-digest  The SHA-256 of each mounted credential half, read from
                     inside the container. What a container HOLDS is read from
                     the container, never from the deployed document (D76, D306)
                     and never from the host's copy of a replaced file (D278).
  confirm-revoked    Poll, within a bounded window, until a retired credential
                     stops being accepted -- with the live credential probed in
                     the same loop as the control. Never asserts revocation
                     instantaneously.

Exit codes (runbook section 2 convention):
  0  the verb completed
  2  invalid operator input
  3  missing local prerequisite, or not root
  5  the deployment or the database refused the operation
  6  the verb ran and its answer is "no" -- see the message
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import runtime_override  # noqa: E402

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_STATE = 5
EXIT_REFUSED = 6

#: The first-party label every container this project owns carries.
#:
#: Not `com.docker.compose.project.working_dir` -- D293 is the record of that
#: selector matching nothing on the host while the service was up and healthy,
#: because it is Compose's note of where it was invoked from rather than
#: anything this repository sets.
PROJECT_KEY_LABEL = "apg.project.key"

#: How long a claimed object's lease lasts, by default. Long enough for a batch
#: of deletes at the adapter's worst case, short enough that a worker killed
#: mid-sweep does not strand its batch for an operator's whole afternoon.
DEFAULT_LEASE_SECONDS = 300

#: How many objects one sweep will handle. Bounded for the reason every sweep
#: here is bounded: an unbounded pass is a duration nobody chose.
DEFAULT_LIMIT = 100

#: The revocation poll's defaults.
#:
#: **The window is not measured and says so.** R2 permission changes are
#: described as eventually consistent and this repository has never timed one,
#: so the command reports "not observed revoked within N seconds" rather than
#: declaring a credential live. Ten minutes is chosen to be longer than any
#: propagation this project would tolerate, not because a measurement produced
#: it -- and the poll's honesty is what makes an unmeasured window acceptable:
#: it never says "revoked" without having watched the refusal happen.
DEFAULT_POLL_WINDOW_SECONDS = 600
DEFAULT_POLL_INTERVAL_SECONDS = 15


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Reaching the deployment
# ---------------------------------------------------------------------------


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the deployed document and the secret generations are "
            "root-owned, and every verb here reaches a container over the local socket.",
        )


def load_document(path: Path) -> dict:
    if not path.is_file():
        raise OperatorError(EXIT_INPUT, f"deployed document not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise OperatorError(EXIT_STATE, f"{path} is not readable as JSON: {error}") from error
    if "database" not in document:
        raise OperatorError(EXIT_INPUT, f"{path} is not a deployed document (no 'database')")
    return document


def project_key(document: dict) -> str:
    key = (document.get("project") or {}).get("key")
    if not key:
        raise OperatorError(EXIT_STATE, "the deployed document names no project key")
    return str(key)


def storage_container(document: dict) -> str:
    """The running storage container, found by label rather than predicted.

    `naming` predicts Compose's container name and the model deliberately does
    not pin it with `container_name:` (D55), so building the name here would
    depend on a convention this repository has chosen not to depend on.
    """
    key = project_key(document)
    filters = [
        f"label={PROJECT_KEY_LABEL}={key}",
        f"label=com.docker.compose.service={runtime_override.STORAGE_SERVICE}",
    ]
    arguments = ["docker", "ps"]
    for value in filters:
        arguments += ["--filter", value]
    arguments += ["--format", "{{.Names}}"]

    result = subprocess.run(arguments, capture_output=True, text=True, check=False, timeout=60)
    names = [line for line in result.stdout.split() if line]
    if len(names) != 1:
        # A selector that matches nothing and a service that is genuinely down
        # look identical from here. D293 is the record of reporting the second
        # while the first was true, so both are named.
        raise OperatorError(
            EXIT_STATE,
            f"expected exactly one running storage container matching {filters}, found "
            f"{names or 'none'}. If the service is up, the selector is wrong; if it is "
            "down, note that the storage service sits on `profiles: [session7]` and does "
            "not start while CURRENT_SESSION is 6.",
        )
    return names[0]


def in_container(
    container: str, program: str, *arguments: str, stdin: str | None = None, timeout: int = 900
) -> dict:
    """Run one program inside the storage container and read back its JSON.

    `-i` is passed whenever there is stdin, and its absence is a real trap this
    project has paid for twice: without it stdin is not attached, the program
    reads nothing, and the container exits 0 having done nothing at all.

    Arguments are for values that are not secrets -- limits, intervals, counts.
    Anything that is a credential goes over **stdin**, because argv is visible in
    `ps`, in `/proc/<pid>/cmdline`, to any audit rule watching execve, and in the
    daemon's own record of the exec.
    """
    command = ["docker", "exec"]
    if stdin is not None:
        command.append("-i")
    command += [container, "python", "-c", program, *arguments]

    result = subprocess.run(
        command,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise OperatorError(
            EXIT_STATE,
            f"the storage service could not run the request (exit {result.returncode}): "
            f"{result.stderr.strip()[:400]}",
        )
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as error:
        # Never echo stdout here. If the program failed in a way that printed
        # its configuration, that output carries a bucket and possibly a key.
        raise OperatorError(
            EXIT_STATE,
            f"the storage service returned something that is not JSON ({error}). "
            "Its output is deliberately not repeated here: a failing program can "
            "print its own configuration, and that carries the bucket and the prefix.",
        ) from error


def psql(container: str, database: str, statement: str) -> str:
    """One statement in the project's PostgreSQL container, over stdin.

    Over stdin rather than `-c` for the reason `auth-admin` gives: a statement in
    the argument vector is a statement in `ps`. Nothing here carries a secret,
    and the habit is kept anyway -- the next person to add a verb should not have
    to notice that this one was safe.
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-qtA",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            database,
        ],
        input=statement,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise OperatorError(EXIT_STATE, result.stderr.strip() or "psql failed with no message")
    return result.stdout.strip()


def quote_identifier(value: str) -> str:
    if not value or '"' in value or "\x00" in value:
        raise OperatorError(EXIT_STATE, f"refusing to quote identifier {value!r}")
    return f'"{value}"'


# ---------------------------------------------------------------------------
# The programs that run inside the container
# ---------------------------------------------------------------------------
#
# Each one is small and does exactly one thing, because a program passed to
# `python -c` is code nobody lints. What they have in common is that all of the
# logic they invoke lives in the image, imported from `app.*`, so the version
# that runs is the version the image pins.

#: One cleanup sweep. Limit and lease come in as arguments; neither is a secret.
_SWEEP_PROGRAM = """
import asyncio, json, sys
from app import storage_cleanup

report = asyncio.run(
    storage_cleanup.sweep_from_environment(
        limit=int(sys.argv[1]), lease_seconds=int(sys.argv[2])
    )
)
print(json.dumps(report.as_dict()))
"""

#: The write grace the worker uses, read from the image rather than restated.
#:
#: `status` needs it to say how many tombstones are collectable *now*, and a
#: second copy on the host would be two numbers with one true relationship
#: between them -- D234's shape, and the reason `lease_margin_seconds` is derived
#: rather than written down twice.
_GRACE_PROGRAM = """
import json
from app import storage_cleanup
print(json.dumps({"write_grace_seconds": storage_cleanup.WRITE_GRACE_SECONDS}))
"""

#: Does the mounted credential reach the configured bucket?
#:
#: A HeadObject on a key that does not exist. **Nothing is written**, so this is
#: safe to run against a live project at any time.
#:
#: The discrimination is the point and it needs no prior knowledge of R2's error
#: vocabulary: a credential the provider ACCEPTS gets a 404 for an absent key
#: (measured, Run 5), and one it does not gets something else. The probe key sits
#: outside the `v1/` segment every real object key carries (ADR 0102), so it
#: cannot collide with one even in principle.
_PROBE_PROGRAM = """
import json, uuid
from app import storage_client

def probe(adapter):
    key = adapter.config.prefix + "_probe/" + str(uuid.uuid4())
    try:
        adapter.head_object(key)
    except storage_client.ObjectAbsent as exc:
        return {"accepted": True, "code": exc.code, "status": exc.status}
    except storage_client.StorageError as exc:
        return {"accepted": False, "code": exc.code, "status": exc.status}
    return {"accepted": True, "code": "present", "status": 200}

print(json.dumps(probe(storage_client.R2Adapter(storage_client.load_config()))))
"""

#: The SHA-256 of each mounted credential half.
#:
#: Read from inside the container and hashed there, so the value never crosses
#: the boundary at all. `load_config` is the service's own reader, so this
#: reports what the service reads rather than what a file on the host says --
#: D278's lesson, where a replaced file left a container bound to the previous
#: inode while the host showed the new contents.
_DIGEST_PROGRAM = """
import hashlib, json
from app import storage_client

config = storage_client.load_config()
print(json.dumps({
    "access_key_id_sha256":
        hashlib.sha256(config.access_key_id.encode("utf-8")).hexdigest(),
    "secret_access_key_sha256":
        hashlib.sha256(config.secret_access_key.encode("utf-8")).hexdigest(),
    "bucket": config.bucket,
    "endpoint": config.endpoint,
}))
"""

#: Poll until a retired credential stops being accepted, or the window ends.
#:
#: The retired pair arrives on **stdin**, once, and is never written to disk and
#: never placed in argv. The loop runs in here rather than on the host so it
#: crosses the boundary once instead of once per poll.
#:
#: **The live credential is probed in the same iteration, and that is the
#: control.** Without it, a retired credential that started failing because the
#: bucket was renamed, the network broke or the endpoint moved would be reported
#: as successfully revoked. Session 6 Run 9's rule -- a measurement without its
#: control is not evidence -- applied to a credential.
_REVOCATION_PROGRAM = """
import dataclasses, json, sys, time, uuid
from app import storage_client

window = int(sys.argv[1])
interval = int(sys.argv[2])

retired_pair = json.loads(sys.stdin.read())
live = storage_client.load_config()
retired = dataclasses.replace(
    live,
    access_key_id=retired_pair["access_key_id"],
    secret_access_key=retired_pair["secret_access_key"],
)

def accepted(config):
    adapter = storage_client.R2Adapter(config)
    key = config.prefix + "_probe/" + str(uuid.uuid4())
    try:
        adapter.head_object(key)
    except storage_client.ObjectAbsent:
        return True, "404"
    except storage_client.StorageError as exc:
        return False, exc.code
    return True, "present"

polls = []
started = time.monotonic()
outcome = "not_observed"
while True:
    retired_ok, retired_code = accepted(retired)
    live_ok, live_code = accepted(live)
    polls.append({
        "at_seconds": round(time.monotonic() - started, 1),
        "retired_accepted": retired_ok,
        "retired_code": retired_code,
        "live_accepted": live_ok,
        "live_code": live_code,
    })
    if not live_ok:
        outcome = "control_failed"
        break
    if not retired_ok:
        outcome = "revoked"
        break
    if time.monotonic() - started + interval > window:
        break
    time.sleep(interval)

print(json.dumps({"outcome": outcome, "polls": polls}))
"""


# ---------------------------------------------------------------------------
# The verbs
# ---------------------------------------------------------------------------

#: What `status` reads. Label/value pairs so the parsing is trivial and so a new
#: metric is one line here rather than a change to a format.
#:
#: `verified_bytes` is summed only over `available`, because it is NULL
#: everywhere else by constraint and a sum over the table would silently be a
#: sum over one state while looking like a total.
_STATUS_SQL = """
SELECT 'objects_' || state, count(*)::text
  FROM app_private.storage_objects GROUP BY state
UNION ALL
SELECT 'available_bytes', coalesce(sum(verified_bytes), 0)::text
  FROM app_private.storage_objects WHERE state = 'available'
UNION ALL
SELECT 'intents_past_deadline', count(*)::text
  FROM app_private.storage_objects
 WHERE state = 'pending' AND intent_expires_at < now()
UNION ALL
SELECT 'cleanup_collectable', count(*)::text
  FROM app_private.storage_objects
 WHERE state = 'tombstoned' AND cleanup_completed_at IS NULL
   AND (cleanup_lease_expires_at IS NULL OR cleanup_lease_expires_at < now())
   AND (completed_at IS NOT NULL
        OR intent_expires_at < now() - make_interval(secs => %GRACE%))
UNION ALL
SELECT 'cleanup_leased', count(*)::text
  FROM app_private.storage_objects
 WHERE state = 'tombstoned' AND cleanup_completed_at IS NULL
   AND cleanup_lease_expires_at >= now()
UNION ALL
SELECT 'cleanup_completed', count(*)::text
  FROM app_private.storage_objects WHERE cleanup_completed_at IS NOT NULL
UNION ALL
SELECT 'cleanup_attempts_max', coalesce(max(cleanup_attempts), 0)::text
  FROM app_private.storage_objects
UNION ALL
SELECT 'cleanup_attempts_over_three', count(*)::text
  FROM app_private.storage_objects
 WHERE cleanup_attempts > 3 AND cleanup_completed_at IS NULL
ORDER BY 1
"""


def status(arguments: argparse.Namespace) -> int:
    require_root()
    document = load_document(Path(arguments.outputs))
    database = document["database"]

    grace = int(in_container(storage_container(document), _GRACE_PROGRAM)["write_grace_seconds"])

    owner = quote_identifier(database["roles"]["object_owner"])
    rows = psql(
        database["container"],
        database["name"],
        f"SET ROLE {owner};\n{_STATUS_SQL.replace('%GRACE%', str(grace))};\n",
    )

    print(f"storage plane, write grace {grace}s (read from the container, not restated here)")
    if not rows:
        print("  the plane is empty")
        return 0
    for line in rows.splitlines():
        label, _, value = line.partition("|")
        print(f"  {label:30s} {value}")

    print()
    print("No object key, no owner and no URL appears above, by design: a key is the")
    print("unguessable half of a bearer credential (STO-URL-001).")
    return 0


def cleanup(arguments: argparse.Namespace) -> int:
    require_root()
    document = load_document(Path(arguments.outputs))
    container = storage_container(document)

    report = in_container(
        container,
        _SWEEP_PROGRAM,
        str(arguments.limit),
        str(arguments.lease_seconds),
        timeout=arguments.lease_seconds + 120,
    )

    print("cleanup sweep")
    for label in (
        "expired",
        "claimed",
        "deleted",
        "finished",
        "lease_lost",
        "failed",
        "abandoned",
    ):
        print(f"  {label:12s} {report.get(label, 0)}")

    if report.get("abandoned"):
        print()
        print(
            f"  {report['abandoned']} claimed objects were not reached before the lease ran "
            "short. They keep their lease until it expires and are collected on a later "
            f"sweep. If this is every sweep, --limit {arguments.limit} is too high for "
            f"--lease-seconds {arguments.lease_seconds}."
        )

    failed_ids = report.get("failed_ids") or []
    if failed_ids:
        print()
        print("  the provider refused these objects; their leases will expire and retry:")
        for identifier in failed_ids:
            print(f"    {identifier}")
        # Not an exit 6. A failed delete is retried by design and a sweep that
        # met one still did the rest of its work; exiting non-zero would make a
        # scheduled sweep look broken for a condition it is built to absorb.
    return 0


def verify_credential(arguments: argparse.Namespace) -> int:
    require_root()
    document = load_document(Path(arguments.outputs))
    result = in_container(storage_container(document), _PROBE_PROGRAM, timeout=120)

    if result["accepted"]:
        print("the mounted credential reaches the configured bucket")
        print(f"  probe answered {result['code']} (HTTP {result['status']})")
        print("  nothing was written: this is a HeadObject on a key that does not exist")
        return 0

    print("the mounted credential does NOT reach the configured bucket")
    print(f"  probe answered {result['code']} (HTTP {result['status']})")
    print()
    print("A bucket-scoped token cannot tell 'absent' from 'not yours': HeadBucket on a")
    print("bucket that does not exist was measured at 403, not 404 (Run 5). So this says")
    print("the credential and the bucket do not work together, and deliberately does not")
    print("guess which of the two is wrong.")
    return EXIT_REFUSED


def credential_digest(arguments: argparse.Namespace) -> int:
    require_root()
    document = load_document(Path(arguments.outputs))
    result = in_container(storage_container(document), _DIGEST_PROGRAM, timeout=120)

    print("the credential this container is holding right now")
    print(f"  access key id      sha256:{result['access_key_id_sha256']}")
    print(f"  secret access key  sha256:{result['secret_access_key_sha256']}")
    print(f"  bucket             {result['bucket']}")
    print(f"  endpoint           {result['endpoint']}")
    print()
    print("Read from inside the container, through the service's own reader. What a")
    print("container holds is never read from the deployed document (D76, D306), and")
    print("never from the host's copy of a file that may have been replaced under a")
    print("still-bound inode (D278).")
    return 0


def confirm_revoked(arguments: argparse.Namespace) -> int:
    require_root()
    document = load_document(Path(arguments.outputs))

    path = Path(arguments.retired_credential_file)
    if not path.is_file():
        raise OperatorError(EXIT_INPUT, f"no retired credential file at {path}")
    try:
        pair = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise OperatorError(
            EXIT_INPUT,
            f"{path} is not JSON ({error}). It must be an object with "
            "'access_key_id' and 'secret_access_key'.",
        ) from error
    missing = [k for k in ("access_key_id", "secret_access_key") if not pair.get(k)]
    if missing:
        raise OperatorError(EXIT_INPUT, f"{path} is missing {', '.join(missing)}")

    result = in_container(
        storage_container(document),
        _REVOCATION_PROGRAM,
        str(arguments.window_seconds),
        str(arguments.interval_seconds),
        # Only the two halves are forwarded, so a file carrying extra members
        # does not send them into a container.
        stdin=json.dumps(
            {
                "access_key_id": pair["access_key_id"],
                "secret_access_key": pair["secret_access_key"],
            }
        ),
        timeout=arguments.window_seconds + 180,
    )

    polls = result.get("polls") or []
    print(f"revocation poll: {len(polls)} probes over {arguments.window_seconds}s")
    for poll in polls:
        retired = "accepted" if poll["retired_accepted"] else f"refused {poll['retired_code']}"
        live = "accepted" if poll["live_accepted"] else f"refused {poll['live_code']}"
        print(f"  +{poll['at_seconds']:>6.1f}s  retired: {retired:<24s} live: {live}")
    print()

    outcome = result.get("outcome")
    if outcome == "revoked":
        print("the retired credential is refused and the live one is accepted.")
        print("The live probe in the same iteration is the control: without it, a retired")
        print("credential failing because the bucket, the network or the endpoint changed")
        print("would read as a successful revocation.")
        return 0

    if outcome == "control_failed":
        print("REFUSED: the control failed. The LIVE credential stopped being accepted")
        print("during the poll, so nothing here says anything about the retired one --")
        print("this run is uninformative rather than negative. Check the deployment")
        print("before drawing any conclusion about the revocation.")
        return EXIT_REFUSED

    print(
        f"NOT OBSERVED: the retired credential was still accepted after "
        f"{arguments.window_seconds}s."
    )
    print()
    print("This does not mean the revocation failed. R2 permission changes are")
    print("eventually consistent, this project has never measured how long one takes,")
    print("and the window above is a bound chosen rather than a bound measured. Re-run")
    print("with a longer --window-seconds. What this command will not do is declare a")
    print("credential revoked without having watched the refusal happen.")
    return EXIT_REFUSED


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="storage-admin",
        description="Operate the object-storage plane. No verb names a bucket or a key.",
    )
    parser.add_argument("--outputs", required=True, help="the project's deployed outputs.json")
    verbs = parser.add_subparsers(dest="verb", required=True)

    show = verbs.add_parser("status", help="what the plane holds, and the cleanup queue")
    show.set_defaults(handler=status)

    sweep = verbs.add_parser("cleanup", help="one sweep: expire stale intents, collect tombstones")
    sweep.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    sweep.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    sweep.set_defaults(handler=cleanup)

    verify = verbs.add_parser(
        "verify-credential",
        help="does the mounted credential reach the bucket? Writes nothing",
    )
    verify.set_defaults(handler=verify_credential)

    digest = verbs.add_parser(
        "credential-digest",
        help="the sha256 of each mounted credential half, read from the container",
    )
    digest.set_defaults(handler=credential_digest)

    revoked = verbs.add_parser(
        "confirm-revoked",
        help="poll until a retired credential stops being accepted",
    )
    revoked.add_argument(
        "--retired-credential-file",
        required=True,
        help=(
            "a JSON object with 'access_key_id' and 'secret_access_key' -- the pair "
            "the rotation REPLACED. Written before the rotation, not after: the value "
            "is unrecoverable once Cloudflare has stopped showing it. There is "
            "deliberately no flag that takes the pair directly (D105)"
        ),
    )
    revoked.add_argument("--window-seconds", type=int, default=DEFAULT_POLL_WINDOW_SECONDS)
    revoked.add_argument("--interval-seconds", type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    revoked.set_defaults(handler=confirm_revoked)

    return parser


def validate(arguments: argparse.Namespace) -> None:
    """Bounds that are the operator's mistake rather than the deployment's."""
    if getattr(arguments, "limit", 1) < 1:
        raise OperatorError(EXIT_INPUT, "--limit must be at least 1")
    if getattr(arguments, "lease_seconds", 1) < 1:
        raise OperatorError(EXIT_INPUT, "--lease-seconds must be at least 1")
    if getattr(arguments, "interval_seconds", 1) < 1:
        raise OperatorError(EXIT_INPUT, "--interval-seconds must be at least 1")
    window = getattr(arguments, "window_seconds", None)
    if window is not None:
        if window < 1:
            raise OperatorError(EXIT_INPUT, "--window-seconds must be at least 1")
        if window < arguments.interval_seconds:
            raise OperatorError(
                EXIT_INPUT,
                "--window-seconds is shorter than --interval-seconds, so the poll would "
                "probe once and report 'not observed' having waited for nothing.",
            )


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        validate(arguments)
        return int(arguments.handler(arguments))
    except OperatorError as error:
        print(f"storage-admin: {error}", file=sys.stderr)
        return error.code
    except subprocess.TimeoutExpired as error:
        print(
            f"storage-admin: the container did not answer within {error.timeout}s. "
            "Nothing here is transactional -- a cleanup sweep that timed out may have "
            "deleted objects it did not record, and those keep their lease and are "
            "collected again. Deletion is at least once by design.",
            file=sys.stderr,
        )
        return EXIT_STATE


if __name__ == "__main__":
    raise SystemExit(main())

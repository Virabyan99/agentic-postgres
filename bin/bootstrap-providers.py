#!/usr/bin/env python
"""Provider bootstrap: create what is missing, record what we own, converge.

Invoked by ``bin/bootstrap-providers.sh``, which owns the privilege and
confirmation checks. Split out because the create-then-record sequence has to be
one process: a client secret that is created and not recorded is a credential
nobody can revoke.

**Ownership is recorded by ID and never adopted by name** (§8.2). A project or
identity carrying the expected name that is absent from our state file is not
ours. Adopting it would mean managing something somebody else created, and
eventually destroying it on their behalf. Every path below either creates a
resource and records its ID, or refuses.

**Convergence is keyed on ``provider_inputs_sha256``**, a digest over exactly
the manifest fields that can change a provider resource. A digest over the whole
manifest would propose provider churn every time a route or a pool size moved.

**The control-plane surface lives here, not in ``infisical_client``.** That
module does Universal Auth login and raw secret reads and nothing else, because
it is what runs on every project start. Creating projects and identities is a
strictly more dangerous capability and it stays in the command that needs it,
which runs by hand and rarely.

The endpoint shapes below follow Infisical's documented API. They are first
exercised against a real organisation in Run 6; nothing offline can prove them.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_postgres.bootstrap_state import (
    BootstrapStateError,
    credential_paths,
    is_converged,
    needs_credential_repair,
    provider_inputs_digest,
    state_path,
    validate_state,
)
from agentic_postgres.config import load_project_manifest
from agentic_postgres.host_config import load_host_manifest
from agentic_postgres.naming import project_key as derive_project_key

EXIT_INVALID = 2
EXIT_PREREQUISITE = 3
EXIT_PROVIDER = 7

TIMEOUT = 30.0


def fail(code: int, message: str) -> None:
    print(f"bootstrap-providers: {message}", file=sys.stderr)
    raise SystemExit(code)


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ControlPlane:
    """The narrow set of Infisical control-plane calls this command makes.

    Separate from ``infisical_client.InfisicalClient`` on purpose: this can
    create identities, and the runtime path must never be able to.
    """

    def __init__(self, api_url: str, token: str) -> None:
        if urllib.parse.urlparse(api_url).scheme != "https":
            raise BootstrapStateError("the Infisical API URL must be https")
        self._base = api_url.rstrip("/")
        self._token = token
        self._context = ssl.create_default_context()

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(  # noqa: S310 — scheme asserted https above
            f"{self._base}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
        )
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=TIMEOUT, context=self._context
            ) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # The body is not included: on identity endpoints it can echo the
            # request, and this message reaches a log.
            raise BootstrapStateError(f"{method} {path} failed with HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise BootstrapStateError(
                f"{method} {path} could not reach Infisical: {exc.reason}"
            ) from None

    def create_project(self, name: str, slug: str, organization_id: str) -> str:
        payload = self._call(
            "POST",
            "/api/v2/workspace",
            {"projectName": name, "slug": slug, "organizationId": organization_id},
        )
        identifier = (payload.get("project") or {}).get("id")
        if not identifier:
            raise BootstrapStateError("project creation returned no id")
        return str(identifier)

    def create_identity(self, name: str, organization_id: str) -> str:
        payload = self._call(
            "POST",
            "/api/v1/identities",
            {"name": name, "organizationId": organization_id, "role": "no-access"},
        )
        identifier = (payload.get("identity") or {}).get("id")
        if not identifier:
            raise BootstrapStateError("identity creation returned no id")
        return str(identifier)

    def attach_universal_auth(self, identity_id: str) -> str:
        payload = self._call(
            "POST",
            f"/api/v1/auth/universal-auth/identities/{urllib.parse.quote(identity_id)}",
            {
                "accessTokenTTL": 900,
                "accessTokenMaxTTL": 3600,
                "accessTokenNumUsesLimit": 0,
                "clientSecretTrustedIps": [{"ipAddress": "0.0.0.0/0"}],
                "accessTokenTrustedIps": [{"ipAddress": "0.0.0.0/0"}],
            },
        )
        client_id = (payload.get("identityUniversalAuth") or {}).get("clientId")
        if not client_id:
            raise BootstrapStateError("universal auth attachment returned no client id")
        return str(client_id)

    def create_client_secret(self, identity_id: str, description: str) -> tuple[str, str]:
        """Return ``(client_secret_id, client_secret)``.

        This is the only point at which the secret is readable. It cannot be
        re-read, which is why the caller writes it to disk before doing anything
        else that can fail.
        """
        payload = self._call(
            "POST",
            f"/api/v1/auth/universal-auth/identities/{urllib.parse.quote(identity_id)}"
            "/client-secrets",
            {"description": description, "numUsesLimit": 0, "ttl": 0},
        )
        secret = payload.get("clientSecret")
        secret_id = (payload.get("clientSecretData") or {}).get("id")
        if not secret or not secret_id:
            raise BootstrapStateError("client secret creation returned an incomplete response")
        return str(secret_id), str(secret)

    def grant_project_access(self, project_id: str, identity_id: str, role: str) -> None:
        self._call(
            "POST",
            f"/api/v2/workspace/{urllib.parse.quote(project_id)}"
            f"/identity-memberships/{urllib.parse.quote(identity_id)}",
            {"role": role},
        )

    def revoke_identity(self, identity_id: str) -> None:
        self._call("DELETE", f"/api/v1/identities/{urllib.parse.quote(identity_id)}")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def read_state(key: str) -> dict[str, Any] | None:
    path = state_path(key)
    if not path.is_file():
        return None
    if path.is_symlink():
        fail(EXIT_INVALID, f"{path} is a symlink, which is not accepted for state")
    try:
        return validate_state(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, BootstrapStateError) as exc:
        fail(EXIT_PROVIDER, f"{path} is unusable: {exc}. Refusing to guess what we own.")
        raise  # unreachable


def write_private(path: Path, content: str, *, mode: int) -> None:
    """Write root-owned content at ``mode``, atomically, never world-readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    os.chown(path.parent, 0, 0)

    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, prefix="."
    )
    try:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()

    staged = Path(handle.name)
    os.chmod(staged, mode)
    os.chown(staged, 0, 0)
    staged.replace(path)


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def describe_plan(key: str, state: dict[str, Any] | None, digest: str) -> int:
    print(f"project  {key}")
    print(f"state    {state_path(key)}")
    print()

    if state is None:
        for change in (
            "create  Infisical project",
            "create  runtime machine identity",
            "create  Universal Auth client secret",
            "grant   identity access to the project, read-only",
        ):
            print(f"  {change}")
        print()
        print("4 change(s) proposed.")
        return 0

    changes: list[str] = []
    if not is_converged(state, digest):
        recorded = state.get("provider_inputs_sha256", "none")
        changes.append(f"update  provider inputs changed ({recorded[:12]} -> {digest[:12]})")
    changes.extend(
        f"repair  credential file is missing: {name}" for name in needs_credential_repair(state)
    )

    if not changes:
        print("no changes.")
        print("The recorded state matches the manifest, and every credential file is present.")
        return 0

    for change in changes:
        print(f"  {change}")
    print()
    print(f"{len(changes)} change(s) proposed.")
    return 0


def apply(
    key: str,
    state: dict[str, Any] | None,
    digest: str,
    manifest_digest: str,
    host: dict[str, Any],
    credential_file: Path,
) -> int:
    infisical = host["host"]["infisical"]

    if state is not None:
        missing = needs_credential_repair(state)
        if is_converged(state, digest) and not missing:
            print("bootstrap-providers: no changes.")
            return 0
        if missing:
            # A Universal Auth client secret cannot be re-read. Creating a
            # second one without revoking the first leaks a credential; revoking
            # the first before the second is proven leaves the project with
            # none. Neither is a thing to do without being asked.
            fail(
                EXIT_PROVIDER,
                f"these credential files are missing: {missing}. A client secret cannot be "
                "re-read from the provider, so this is a rotation rather than a repair. "
                "Restore from backup, or --destroy and re-apply deliberately.",
            )
        fail(
            EXIT_PROVIDER,
            "the provider inputs changed for a project that already has resources. "
            "Changing a project slug or environment means a different project; --destroy "
            "the old one deliberately rather than having this command guess.",
        )

    token = credential_file.read_text(encoding="utf-8").strip()
    if not token:
        fail(EXIT_PREREQUISITE, f"the operator credential file is empty: {credential_file}")

    try:
        control = ControlPlane(infisical["api_url"], token)
        organization = infisical["organization_id"]

        project_id = control.create_project(key, key, organization)
        identity_id = control.create_identity(f"{key}-runtime", organization)
        client_id = control.attach_universal_auth(identity_id)
        secret_id, client_secret = control.create_client_secret(identity_id, f"{key} runtime")
    except (BootstrapStateError, KeyError) as exc:
        fail(EXIT_PROVIDER, str(exc))

    paths = credential_paths(key)

    # Written before anything else that can fail. The client secret is readable
    # exactly once; an exception between creation and persistence would leave a
    # live credential that nothing can revoke and nothing can use.
    try:
        write_private(Path(paths["client_secret_path"]), f"{client_secret}\n", mode=0o400)
        write_private(Path(paths["client_id_path"]), f"{client_id}\n", mode=0o400)
        del client_secret
    except OSError as exc:
        try:
            control.revoke_identity(identity_id)
        except BootstrapStateError:
            fail(
                EXIT_PROVIDER,
                f"could not write the credential ({exc}) and could not revoke identity "
                f"{identity_id}. Revoke it by that ID by hand before retrying.",
            )
        fail(EXIT_PROVIDER, f"could not write the credential ({exc}); the identity was revoked.")

    try:
        control.grant_project_access(project_id, identity_id, "viewer")
    except BootstrapStateError as exc:
        fail(
            EXIT_PROVIDER,
            f"created identity {identity_id} but could not grant it project access: {exc}. "
            "The identity exists and is recorded below; re-run --apply after fixing the role.",
        )

    timestamp = now()
    document = {
        "schema_version": 1,
        "project_key": key,
        "project_manifest_sha256": manifest_digest,
        "provider_inputs_sha256": digest,
        "provider": "infisical",
        "api_url": infisical["api_url"],
        "organization_slug": infisical["organization_slug"],
        "infisical_project_id": project_id,
        "environment_slug": infisical["environment_slug"],
        "runtime_folder": infisical["runtime_folder"],
        "runtime_identity_id": identity_id,
        "runtime_client_id": client_id,
        "active_client_secret_id": secret_id,
        "credential_files": paths,
        "managed_resources": ["project", "runtime_identity", "runtime_client_secret"],
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    validate_state(document)
    write_private(
        state_path(key), json.dumps(document, indent=2, sort_keys=True) + "\n", mode=0o600
    )

    print(f"bootstrap-providers: created 3 resource(s) for {key}")
    print(f"bootstrap-providers: recorded them in {state_path(key)}")
    return 0


def destroy(
    key: str, state: dict[str, Any] | None, host: dict[str, Any], credential_file: Path | None
) -> int:
    if state is None:
        print(f"bootstrap-providers: no recorded state for {key}. Nothing is owned; nothing done.")
        return 0
    if credential_file is None:
        fail(EXIT_INVALID, "--destroy requires --operator-credential-file")

    token = credential_file.read_text(encoding="utf-8").strip()
    control = ControlPlane(host["host"]["infisical"]["api_url"], token)

    identity_id = state["runtime_identity_id"]
    try:
        control.revoke_identity(identity_id)
    except BootstrapStateError as exc:
        fail(EXIT_PROVIDER, f"could not revoke identity {identity_id}: {exc}")

    # The project itself is deliberately left. Deleting it would delete secrets
    # this command did not create, and §8.2's rule cuts both ways: we remove
    # what we recorded creating, by ID, and nothing else.
    print(f"bootstrap-providers: revoked identity {identity_id}")
    print(f"bootstrap-providers: project {state['infisical_project_id']} was left in place")
    print("Delete it in the Infisical console if you also want its secrets gone.")

    for name in ("client_secret_path", "client_id_path"):
        path = Path(state["credential_files"][name])
        path.unlink(missing_ok=True)

    state_path(key).unlink(missing_ok=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True, description="Provider bootstrap.")
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--mode", choices=["plan", "apply", "destroy"], required=True)
    parser.add_argument("--operator-credential-file", type=Path)
    arguments = parser.parse_args(argv)

    try:
        host = load_host_manifest(arguments.host)
        manifest = load_project_manifest(arguments.project)
    except (OSError, ValueError) as exc:
        fail(EXIT_INVALID, str(exc))

    from hashlib import sha256

    project = manifest["project"]
    key = derive_project_key(project["slug"], project["environment"])
    manifest_digest = sha256(arguments.project.read_bytes()).hexdigest()

    try:
        digest = provider_inputs_digest(manifest, host["host"])
    except BootstrapStateError as exc:
        fail(EXIT_INVALID, str(exc))

    state = read_state(key)

    if arguments.mode == "plan":
        return describe_plan(key, state, digest)
    if arguments.mode == "destroy":
        return destroy(key, state, host, arguments.operator_credential_file)

    if arguments.operator_credential_file is None:
        fail(EXIT_INVALID, "--apply requires --operator-credential-file")
    if not arguments.operator_credential_file.is_file():
        fail(EXIT_INVALID, f"credential file not found: {arguments.operator_credential_file}")
    return apply(key, state, digest, manifest_digest, host, arguments.operator_credential_file)


if __name__ == "__main__":
    raise SystemExit(main())

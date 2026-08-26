"""The Compose grant surface for one materialized generation.

`compose.yaml` carries no `secrets:` block and no per-service grant, and the
comment above `secret-check` has always said why: the source path contains a
generation identifier that does not exist until `bin/materialize-secrets.sh`
runs. What that comment claimed, and what nothing did, is supply them.

Session 2 never noticed. Its one secret is consumed by `secret-check`, a
`session2-verify` service that no deploy starts, and every Session 2 proof
reads the *files on disk* — ownership, mode, generation directory — rather than
a container's view of them. So a model with no grants at all passed a suite
whose subject was secrets.

Session 3 is where it fails: `POSTGRES_PASSWORD_FILE` names
`/run/secrets/postgres_init_superuser_password`, and a cluster whose entrypoint
cannot read that file does not initialise.

**Rendered at start, not at deploy.** `bin/materialize-secrets.sh` writes a new
immutable generation on every `up`, so a block written once at deploy time
names a directory that the next restart supersedes. This is rendered by
`bin/project-runtime.sh` immediately after materialization and immediately
before `compose up`, from the generation pointer it has just written.

**Grants are per (service, target_file).** The Compose secret *name* carries the
service, because two services may legitimately receive the same basename from
different directories; the `target:` is the basename alone, so each container
still sees it at `/run/secrets/<target_file>` exactly as
`secrets_contract.container_secret_path` says. Deriving the name without the
service would collide two sources onto one mount, and the loser would be
whichever service Compose resolved second.
"""

from __future__ import annotations

from typing import Any

import yaml

from agentic_postgres.secrets_contract import (
    CONTAINER_SECRET_DIR,
    active_secrets,
    compose_consumers,
    container_secret_path,
    secret_source_path,
)

__all__ = [
    "OVERRIDE_FILENAME",
    "build_secret_override",
    "grant_name",
    "mount_target",
    "render_secret_override",
]

#: Written into the project's rendered directory, beside the router override.
OVERRIDE_FILENAME = "secrets-compose.override.yaml"


def mount_target(entry: Any) -> str:
    """Where one Compose `secrets:` entry lands inside the container.

    The inverse of what :func:`build_secret_override` writes, and it lives here
    because the module that produces a grant owns the rule for reading it back.

    **`target` is ABSOLUTE since ADR 0153** -- `/run/secrets/<target_file>` for a
    `raw` or `pgpass` consumer, and pgBackRest's include directory for a
    `pgbackrest` one, which is the whole reason it stopped being a bare
    basename. A reader that prefixes `/run/secrets/` onto it produces
    `/run/secrets//run/secrets/<file>`: a mount that exists, holds the right
    bytes, and sits at a path the container's own entrypoint has no reason to
    open (D597).

    Compose's short form -- a bare secret name with no `target` -- is still a
    basename, and still means `/run/secrets/<name>`. Both are accepted here so
    that one function answers the question for every entry shape.
    """
    if isinstance(entry, dict):
        target = entry.get("target") or entry["source"]
    else:
        target = str(entry)
    if target.startswith("/"):
        return target
    return f"{CONTAINER_SECRET_DIR}/{target}"


def grant_name(consumer: dict[str, Any]) -> str:
    """The Compose secret name for one consumer. Unique per (service, file)."""
    return f"{consumer['service']}__{consumer['target_file']}"


def build_secret_override(
    *, project_key: str, generation_id: str, contract: dict[str, Any], session: int
) -> dict[str, Any]:
    """The `secrets:` block and per-service grants for one generation."""
    if not project_key:
        raise ValueError("project_key is required")
    if not generation_id:
        raise ValueError("generation_id is required")
    if session < 1:
        raise ValueError("session must be a positive integer")

    secrets: dict[str, Any] = {}
    services: dict[str, Any] = {}

    # `compose_consumers`, not `secret["consumers"]`. A root-plane consumer
    # (ADR 0054) gets no `secrets:` entry, no service grant and no mount -- and
    # it gets them by not being iterated here, rather than by a filter somebody
    # could reorder. There is no service name to key a grant under and no
    # container that may hold the value.
    for secret in active_secrets(contract, session):
        for consumer in compose_consumers(secret):
            name = grant_name(consumer)
            secrets[name] = {"file": secret_source_path(project_key, generation_id, consumer)}
            grants = services.setdefault(consumer["service"], {"secrets": []})["secrets"]
            # `container_secret_path`, not `target_file` (ADR 0153 §6). The
            # bare basename and that function were two spellings of one fact,
            # and a `pgbackrest`-format consumer needs them to disagree: its
            # file belongs in pgBackRest's include directory, not in
            # /run/secrets. Measured that Compose accepts an absolute target.
            grants.append({"source": name, "target": container_secret_path(consumer)})

    # An empty document is a valid answer -- session 1 grants nothing -- but it
    # must still be a document Compose accepts rather than `{}` with no keys.
    return {"secrets": secrets, "services": services}


def render_secret_override(
    *, project_key: str, generation_id: str, contract: dict[str, Any], session: int
) -> bytes:
    document = build_secret_override(
        project_key=project_key,
        generation_id=generation_id,
        contract=contract,
        session=session,
    )
    header = (
        "# Generated by bin/project-runtime.sh from the active secret generation.\n"
        "# Do not edit; do not shell-source. It is rewritten on every start,\n"
        "# because materialization writes a new generation each time.\n"
        "#\n"
        "# Paths only. No secret value appears here, and none ever may.\n"
    )
    body = yaml.safe_dump(document, sort_keys=True, default_flow_style=False, width=10_000)
    return (header + body).encode("utf-8")

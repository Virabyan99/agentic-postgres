"""A project's workflow definitions: loaded, compiled against its lock (ADR 0228).

A definition is a project artefact like a migration set -- reviewed in the
checkout, installed by the deploy, immutable once applied, fixed forward by a
new version (D1660). This module is the whole of what "compiled" means: a step
names a CAPABILITY by `name@version`, and compiling resolves that capability to
the tool the project's lock says serves it, to the resource behind it for a
relation read, and to the scopes the run will need. Everything that cannot be
decided from the lock -- what a caller's input will hold, whether the upstream
will answer -- stays a run-time question.

**A capability, not a tool** (D1660). A tool may be backed by several
capabilities that move independently: `query_resource` is `query_notes` and
`query_tasks`, and either can be deprecated while the other is not
(`mcp_lock.CapabilityRef`'s own comment). So the tool name is not the versioned
thing and a definition may not name it.

**The lock is read as JSON here, by a small reader of this module's own**, and
the service's `app.mcp_lock` is not imported. `src/agentic_postgres` is what a
`bin/` command may import (ADR 0093); the service package is what runs inside
the image. The duplication is deliberate and it is guarded: a proof asserts
that `ToolView.read_shape` and `mcp_lock.Tool.read_shape` answer the same word
for every tool in a real lock, because that rule -- not a field -- is what
decides which arguments a read step may carry.

**What a reference means.** A string argument may carry `{{input.<key>}}` or
`{{steps.<name>.<field>}}`. Neither is resolved here: the input arrives at
enqueue and a prior step's result arrives when that step succeeds. What
compiling does is refuse a reference that could never resolve -- one naming a
step that does not exist, or one naming a step that runs LATER -- and refuse a
`{{` that is not a well-formed reference at all. That last refusal is D1679's
lesson borrowed from the migration renderer: a marker the pattern did not match
is a typo, not a literal, and a definition that installs one would pass it to
the upstream as text.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    capability_manifest,
    config,
    naming,
    scope_registry,
)

#: The schema a definition file is validated against before it is compiled.
SCHEMA_NAME = "workflow.schema.json"

#: `projects/<slug>/workflows/*.yaml`. The directory is optional: a project
#: that declares no workflows is not a project with an empty one, and step 6d
#: says so rather than reporting zero.
WORKFLOWS_SUBDIR = "workflows"

#: A reference, and the only two namespaces there are. `input` takes one key,
#: `steps` takes a step name and a field of that step's recorded result --
#: which is what `workflow_claim_step` hands the worker as `prior`, an object
#: keyed by step name.
REFERENCE = re.compile(r"\{\{(input\.[a-z][a-z0-9_]*|steps\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\}\}")

#: Any brace pair at all. Anything this finds that `REFERENCE` did not consume
#: is a typo (D1679).
BRACES = re.compile(r"\{\{|\}\}")

#: A capability reference in a step: `name@major.minor.patch`.
CAPABILITY = re.compile(r"^([a-z][a-z0-9_]*)@([0-9]+\.[0-9]+\.[0-9]+)$")

#: The arguments a RELATION read accepts, from the shape the runtime registers
#: it with (`mcp_tools.register_relation_read`). `resource` is deliberately
#: absent: the compiler derives it from the capability, so an author who names
#: it is naming something the compiler has already decided (D1660).
RELATION_READ_ARGUMENTS = ("columns", "filters", "order_by", "limit")

#: The lifecycle a step's capability must be in. Not a list with one member
#: for its own sake: `deprecated` and `retired` are the other two the manifest
#: schema admits, and a workflow is a STORED authority that outlives the
#: session that wrote it -- installing one over a capability already on its way
#: out is how a deprecation becomes invisible.
ACTIVE = "active"

#: The floor under a step's timeout when the file does not give one, and the
#: ceiling the table's CHECK enforces.
DEFAULT_STEP_TIMEOUT_SECONDS = 60
MAX_STEP_TIMEOUT_SECONDS = 600

#: The run's own bound, and its default.
DEFAULT_RUN_TIMEOUT_SECONDS = 600
MAX_RUN_TIMEOUT_SECONDS = 3600

MAX_RETRIES = 5
DEFAULT_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 300


class DefinitionError(Exception):
    """One refusal, and the step it is about.

    `step_name` is `None` for a refusal about the definition itself. The two
    are kept apart rather than flattened into a message because `validate`
    prints `<file>: step <name>: <reason>` and the deploy's step 6d prints the
    same sentence: a caller that had to parse the string to find the step would
    be re-deriving what this already knows.
    """

    def __init__(self, step_name: str | None, reason: str) -> None:
        self.step_name = step_name
        self.reason = reason
        super().__init__(reason if step_name is None else f"step {step_name}: {reason}")


# ---------------------------------------------------------------------------
# The lock, as this compiler reads it
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CapabilityView:
    """One authorization a tool is backed by, with what it declares.

    `requires_approval` and `supports_dry_run` are `False` and `True` by
    absence rather than `None`: on a READ capability the lock carries neither
    field at all (measured against the release's own contract), and a read
    neither requires approval nor needs a dry run to be safe. This is the one
    place a default is not D600's `null` that looks measured -- the absence is
    the schema's own rule (ADR 0179), not a missing reading.
    """

    name: str
    version: str
    lifecycle: str
    requires_approval: bool
    supports_dry_run: bool


@dataclass(frozen=True, slots=True)
class ResourceView:
    """One queryable resource behind a read capability."""

    name: str
    capability: str
    required_scopes: tuple[str, ...]
    method: str


@dataclass(frozen=True, slots=True)
class ToolView:
    """One registered tool of the project's lock, as the compiler needs it."""

    name: str
    kind: str
    timeout_ms: int
    capabilities: tuple[CapabilityView, ...]
    arguments: tuple[str, ...]
    required_scopes: tuple[str, ...]
    resources: tuple[ResourceView, ...]

    @property
    def read_shape(self) -> str | None:
        """`relation` or `rpc` for a read, from what its resources reach.

        **The same rule as `mcp_lock.Tool.read_shape`, and a proof holds the
        two together.** It is duplicated rather than imported because this
        module is `src/` and that one is the service's; it is duplicated
        rather than replaced by a declared field because the runtime derives
        it, and a compiler that trusted a field would compile against a shape
        the runtime does not register.
        """
        if self.kind != "read":
            return None
        methods = {resource.method for resource in self.resources}
        return "relation" if methods == {"get"} else "rpc"


@dataclass(frozen=True, slots=True)
class Resolved:
    """What a capability reference resolved to."""

    tool: ToolView
    capability: CapabilityView
    resource: ResourceView | None


@dataclass(frozen=True, slots=True)
class LockView:
    """The project's compiled lock, read as JSON by this module's own reader."""

    tools: tuple[ToolView, ...]
    tools_sha256: str

    @classmethod
    def from_json(cls, text: str | bytes) -> LockView:
        try:
            document = json.loads(text)
        except ValueError as error:
            raise DefinitionError(None, f"the capability lock is not JSON: {error}") from error
        if not isinstance(document, dict):
            raise DefinitionError(None, "the capability lock is not an object")

        digest = document.get("tools_sha256")
        if not isinstance(digest, str):
            raise DefinitionError(
                None,
                "the capability lock carries no tools_sha256. A definition records what it "
                "compiled against, and a lock the compiler did not sign is one nobody can "
                "say that about (ADR 0200).",
            )

        tools: list[ToolView] = []
        for entry in document.get("tools") or []:
            capabilities = tuple(
                CapabilityView(
                    name=reference["name"],
                    version=reference["version"],
                    lifecycle=reference["lifecycle"],
                    requires_approval=bool(reference.get("requires_approval", False)),
                    supports_dry_run=bool(reference.get("supports_dry_run", False)),
                )
                for reference in entry.get("capabilities") or []
            )
            resources = tuple(
                ResourceView(
                    name=resource["name"],
                    capability=resource["capability"],
                    required_scopes=tuple(resource.get("required_scopes") or ()),
                    method=resource["operation"]["method"],
                )
                for resource in entry.get("resources") or []
            )
            tools.append(
                ToolView(
                    name=entry["name"],
                    kind=entry["kind"],
                    timeout_ms=int(entry["timeout_ms"]),
                    capabilities=capabilities,
                    arguments=tuple(entry.get("arguments") or ()),
                    required_scopes=tuple(entry.get("required_scopes") or ()),
                    resources=resources,
                )
            )
        return cls(tools=tuple(tools), tools_sha256=digest)

    @property
    def capability_names(self) -> tuple[str, ...]:
        """Every capability this lock serves, sorted, for a refusal to name."""
        return tuple(
            sorted(
                f"{capability.name}@{capability.version}"
                for tool in self.tools
                for capability in tool.capabilities
            )
        )

    def resolve(self, step_name: str, reference: str) -> Resolved:
        """`name@version` to the tool that serves it, or a refusal naming why.

        The four refusals are separate on purpose. *No such capability* and
        *that capability at another version* are different mistakes with
        different fixes, and folding them into one would tell an author to go
        looking for a typo when the lock simply moved.
        """
        match = CAPABILITY.match(reference)
        if match is None:
            raise DefinitionError(
                step_name,
                f"{reference!r} is not a capability reference; a step names one as name@version",
            )
        name, version = match.group(1), match.group(2)

        serving = [
            (tool, capability)
            for tool in self.tools
            for capability in tool.capabilities
            if capability.name == name
        ]
        if not serving:
            raise DefinitionError(
                step_name,
                f"this project's lock compiles no capability named {name!r}. "
                f"It serves: {', '.join(self.capability_names)}",
            )

        versioned = [pair for pair in serving if pair[1].version == version]
        if not versioned:
            carried = ", ".join(sorted(capability.version for _, capability in serving))
            raise DefinitionError(
                step_name,
                f"the lock carries {name} at {carried}, not at {version}",
            )
        if len(versioned) > 1:
            names = ", ".join(sorted(tool.name for tool, _ in versioned))
            raise DefinitionError(
                step_name,
                f"{name}@{version} is served by more than one tool ({names}); the lock is "
                "ambiguous and this is reported rather than resolved by picking one",
            )

        tool, capability = versioned[0]
        if tool.kind == "metadata":
            raise DefinitionError(
                step_name,
                f"{name}@{version} is served by {tool.name}, a metadata tool. A workflow step "
                "does work; reading the lock is not work, and a run that spent a step on it "
                "would be a run whose record says nothing happened",
            )
        if capability.lifecycle != ACTIVE:
            raise DefinitionError(
                step_name,
                f"{name}@{version} is {capability.lifecycle}, not {ACTIVE}. A definition is "
                "stored and outlives the session that wrote it, so installing one over a "
                "capability already on its way out is how a deprecation becomes invisible",
            )
        if capability.requires_approval:
            raise DefinitionError(
                step_name,
                f"{name}@{version} requires approval, and approval steps arrive in Session 33. "
                "A worker that ran it would be an approval gate nobody passed",
            )

        resource: ResourceView | None = None
        if tool.kind == "read":
            behind = [item for item in tool.resources if item.capability == name]
            if len(behind) != 1:
                raise DefinitionError(
                    step_name,
                    f"{name}@{version} is a read served by {tool.name} and the lock names "
                    f"{len(behind)} resources behind it; exactly one is required",
                )
            resource = behind[0]

        return Resolved(tool=tool, capability=capability, resource=resource)


# ---------------------------------------------------------------------------
# The compiled definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompiledStep:
    """One step, with every question the lock can answer already answered."""

    name: str
    tool: str
    capability: str
    capability_version: str
    resource: str | None
    kind: str
    arguments: dict[str, Any]
    retry: dict[str, int]
    timeout_seconds: int

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tool": self.tool,
            "capability": self.capability,
            "capability_version": self.capability_version,
            "resource": self.resource,
            "kind": self.kind,
            "arguments": self.arguments,
            "retry": dict(self.retry),
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class Compiled:
    """A definition ready to install: the row's six values, and the body."""

    name: str
    version: int
    description: str
    timeout_seconds: int
    steps: tuple[CompiledStep, ...]
    required_scopes: tuple[str, ...]
    lock_tools_sha256: str
    source_sha256: str

    def body(self) -> dict[str, Any]:
        """The JSON the worker reads. `workflow_enqueue` reads
        `timeout_seconds` and each step's `name`, `retry` and
        `timeout_seconds` out of exactly this document."""
        return {
            "schema_version": 1,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "timeout_seconds": self.timeout_seconds,
            "steps": [step.as_json() for step in self.steps],
            "required_scopes": list(self.required_scopes),
            "lock_tools_sha256": self.lock_tools_sha256,
            "source_sha256": self.source_sha256,
        }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def definitions_of(project_set_root: Path) -> list[Path]:
    """`<root>/workflows/*.yaml`, sorted; an empty list when there is no directory.

    Sorted because the deploy installs them in this order and a deploy whose
    output depends on a directory listing's order is one whose transcript
    cannot be compared with the last one's.
    """
    directory = Path(project_set_root) / WORKFLOWS_SUBDIR
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.yaml"))


def load(path: Path) -> dict[str, Any]:
    """Read one definition file and validate its SHAPE. Nothing about the lock."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise DefinitionError(None, f"cannot be read: {error}") from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise DefinitionError(None, f"is not YAML: {error}") from error
    if not isinstance(document, dict):
        raise DefinitionError(None, "is not a mapping")
    try:
        config.validate_against_schema(document, SCHEMA_NAME)
    except config.ManifestError as error:
        raise DefinitionError(None, str(error)) from error
    return document


def source_digest(path: Path) -> str:
    """The digest of the FILE's bytes, comments and all.

    Over the bytes and not over the parsed document, for the reason
    `mcp-contract lock` records about its own sources: a digest over a
    re-serialization is equal for two files whose comments differ, and the
    comments are where the reasoning lives.
    """
    return sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Compiling
# ---------------------------------------------------------------------------


def _references(value: Any, step_name: str) -> list[str]:
    """Every reference in a step's arguments, with a typo refused on the way.

    Walks lists and objects as well as strings: `filters` is a list of small
    objects and its operands are exactly where a reference is useful.
    """
    found: list[str] = []
    if isinstance(value, str):
        consumed = REFERENCE.sub("", value)
        residue = BRACES.search(consumed)
        if residue is not None:
            raise DefinitionError(
                step_name,
                f"{value!r} carries {consumed[residue.start() : residue.start() + 2]!r}, which is "
                "not a reference. A marker the pattern did not match is a typo, not a literal",
            )
        found.extend(REFERENCE.findall(value))
    elif isinstance(value, list):
        for item in value:
            found.extend(_references(item, step_name))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_references(item, step_name))
    return found


def _accepted_arguments(resolved: Resolved, step_name: str) -> tuple[str, ...]:
    """Which argument names this step may carry, by SHAPE (ADR 0200).

    The lock declares an argument list for a WRITE and for nothing else, which
    is why this is not simply `tool.arguments`: a read's arguments are the ones
    the runtime registers its closure with, and an RPC read registers none.
    """
    tool = resolved.tool
    if tool.kind == "write":
        return tool.arguments
    shape = tool.read_shape
    if shape == "relation":
        return RELATION_READ_ARGUMENTS
    if shape == "rpc":
        return ()
    raise DefinitionError(
        step_name,
        f"{tool.name} is a {tool.kind} tool and this compiler has no argument contract for it",
    )


def _step_timeout(document: dict[str, Any], resolved: Resolved, step_name: str) -> int:
    """The step's own bound, defaulted from the tool's and floored by it."""
    floor = max(1, math.ceil(resolved.tool.timeout_ms / 1000))
    if floor > MAX_STEP_TIMEOUT_SECONDS:
        raise DefinitionError(
            step_name,
            f"{resolved.tool.name} declares timeout_ms {resolved.tool.timeout_ms}, whose floor "
            f"of {floor}s is above the {MAX_STEP_TIMEOUT_SECONDS}s a step may take",
        )
    declared = document.get("timeout_seconds")
    if declared is None:
        return min(max(floor, DEFAULT_STEP_TIMEOUT_SECONDS), MAX_STEP_TIMEOUT_SECONDS)
    if declared < floor:
        raise DefinitionError(
            step_name,
            f"timeout_seconds {declared} is below {resolved.tool.name}'s own floor of {floor}s; "
            "a step timeout under the tool's would fail a call the plane was still serving",
        )
    if declared > MAX_STEP_TIMEOUT_SECONDS:
        raise DefinitionError(
            step_name, f"timeout_seconds {declared} is above {MAX_STEP_TIMEOUT_SECONDS}"
        )
    return int(declared)


def _retry(document: dict[str, Any], step_name: str) -> dict[str, int]:
    retry = document.get("retry") or {}
    maximum = int(retry.get("max", 0))
    backoff = int(retry.get("backoff_seconds", DEFAULT_BACKOFF_SECONDS))
    if not 0 <= maximum <= MAX_RETRIES:
        raise DefinitionError(step_name, f"retry.max {maximum} is outside 0..{MAX_RETRIES}")
    if not 1 <= backoff <= MAX_BACKOFF_SECONDS:
        raise DefinitionError(
            step_name, f"retry.backoff_seconds {backoff} is outside 1..{MAX_BACKOFF_SECONDS}"
        )
    return {"max": maximum, "backoff_seconds": backoff}


def compile(definition: dict[str, Any], lock: LockView, *, source_sha256: str) -> Compiled:
    """Resolve every step against the lock, or refuse naming the step and why.

    `source_sha256` is a parameter rather than something computed here because
    it is a digest of the FILE and this takes a parsed document: `compile_file`
    is the pairing, and a caller holding a document it did not read off disk
    has to say what it is a compilation OF.
    """
    run_timeout = int(definition.get("timeout_seconds", DEFAULT_RUN_TIMEOUT_SECONDS))
    if not 1 <= run_timeout <= MAX_RUN_TIMEOUT_SECONDS:
        raise DefinitionError(
            None, f"timeout_seconds {run_timeout} is outside 1..{MAX_RUN_TIMEOUT_SECONDS}"
        )

    steps: list[CompiledStep] = []
    scopes: set[str] = set()
    seen: list[str] = []

    for entry in definition["steps"]:
        name = entry["name"]
        if name in seen:
            raise DefinitionError(name, "names a step this definition already has")

        resolved = lock.resolve(name, entry["capability"])
        arguments = entry.get("arguments") or {}

        accepted = _accepted_arguments(resolved, name)
        undeclared = sorted(set(arguments) - set(accepted))
        if undeclared:
            offered = ", ".join(accepted) if accepted else "none"
            raise DefinitionError(
                name,
                f"{resolved.tool.name} does not take {', '.join(undeclared)}; it takes {offered}",
            )

        for reference in _references(arguments, name):
            namespace, _, rest = reference.partition(".")
            if namespace == "input":
                # A run's input arrives at enqueue. There is nothing here to
                # check it against, and inventing a declared input block so
                # that there would be is a second contract nobody writes.
                continue
            referenced = rest.split(".")[0]
            if referenced == name:
                raise DefinitionError(name, f"{{{{{reference}}}}} refers to itself")
            if referenced not in seen:
                later = any(step["name"] == referenced for step in definition["steps"])
                where = "runs later" if later else "is not a step of this definition"
                raise DefinitionError(name, f"{{{{{reference}}}}} names a step that {where}")

        scopes.update(
            resolved.tool.required_scopes
            if resolved.tool.kind == "write"
            else (resolved.resource.required_scopes if resolved.resource else ())
        )

        steps.append(
            CompiledStep(
                name=name,
                tool=resolved.tool.name,
                capability=resolved.capability.name,
                capability_version=resolved.capability.version,
                resource=resolved.resource.name if resolved.resource else None,
                kind=resolved.tool.kind,
                arguments=dict(arguments),
                retry=_retry(entry, name),
                timeout_seconds=_step_timeout(entry, resolved, name),
            )
        )
        seen.append(name)

    return Compiled(
        name=definition["name"],
        version=int(definition["version"]),
        description=definition["description"],
        timeout_seconds=run_timeout,
        steps=tuple(steps),
        required_scopes=tuple(sorted(scopes)),
        lock_tools_sha256=lock.tools_sha256,
        source_sha256=source_sha256,
    )


def compile_file(path: Path, lock: LockView) -> Compiled:
    """`load` + `compile`, with the digest taken from the bytes that were read."""
    document = load(path)
    return compile(document, lock, source_sha256=source_digest(path))


# ---------------------------------------------------------------------------
# The lock a checkout can see
# ---------------------------------------------------------------------------

#: The release's approved contract, the one `mcp-contract.sh check` compares a
#: manifest against.
CANONICAL_CONTRACT = (
    REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
)

#: The release's capability manifest in a checkout. The real one is a gitignored
#: operator input; this is the committed example every offline command compiles
#: against (`bin/generate.py`, `bin/mcp-contract.py`, `bin/dev.py` all default
#: to it).
DEFAULT_CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"

#: What `lock_view_for_project` puts in the `upstream` field of a lock it
#: computes and throws away.
#:
#: **A lock compiled here is never written** -- `mcp-contract.sh check
#: --project` already computes a narrowed contract and discards it for the same
#: reason, so that a profile that would widen a bound fails in a checkout
#: rather than becoming a runtime denial. The address is the one input a
#: checkout genuinely does not have (it comes from a RENDER), and a plausible
#: placeholder would be worse than an obviously impossible one: D465 is the
#: record of what happens when a wrong input produces a publishable artefact.
#: A proof asserts `tools_sha256` is identical under two different upstreams,
#: so the digest a definition records does not depend on this at all.
UNDEPLOYED_UPSTREAM = "urn:agentic-postgres:no-deployment-in-a-checkout"


def lock_view_for_project(manifest_path: Path, capabilities_path: Path | None = None) -> LockView:
    """The tools a project's deployed lock WOULD serve, computed in a checkout.

    The same chain `bin/mcp-contract.py lock` walks, and the product's own join
    function rather than a second one (D1114): the release's approved contract
    when the project declares no capabilities of its own, and
    `compile_joint_contract` over the two manifests when it does.

    `validate` runs with no host, no root and no render, which is the whole
    point of validating in a checkout -- so this is how it reaches a lock.
    """
    manifest = config.load_project_manifest(Path(manifest_path))
    inputs = capability_manifest.project_inputs(manifest)
    canonical = capability_manifest.load_contract_document(CANONICAL_CONTRACT)

    surface = None
    if inputs is not None:
        capabilities = config.load_capabilities_manifest(
            Path(capabilities_path or DEFAULT_CAPABILITIES)
        )
        canonical = capability_manifest.compile_joint_contract(capabilities, inputs)
        surface = inputs.surface
    else:
        surface = api_surface.load_surface()

    profile = (
        manifest["mcp"]["profile"]
        if manifest["schema_version"] >= config.PROJECT_PROFILE_FROM
        else None
    )
    lock = capability_compiler.compile_lock(
        canonical=canonical,
        project_key=naming.project_key(
            manifest["project"]["slug"], manifest["project"]["environment"]
        ),
        upstream=UNDEPLOYED_UPSTREAM,
        sources={
            # Digests of nothing, and named so. This lock is discarded; the
            # deployed one records the real ones. A digest invented here that
            # LOOKED like a real one is the failure this naming refuses.
            "capabilities_sha256": "0" * 64,
            "api_surface_sha256": "0" * 64,
            "canonical_openapi_sha256": "0" * 64,
            "project_manifest_sha256": "0" * 64,
        },
        profile=profile,
        vocabulary=scope_registry.vocabulary_block(surface),
    )
    return LockView.from_json(capability_compiler.canonical_bytes(lock))


__all__ = [
    "ACTIVE",
    "CANONICAL_CONTRACT",
    "CAPABILITY",
    "DEFAULT_CAPABILITIES",
    "RELATION_READ_ARGUMENTS",
    "SCHEMA_NAME",
    "UNDEPLOYED_UPSTREAM",
    "WORKFLOWS_SUBDIR",
    "CapabilityView",
    "Compiled",
    "CompiledStep",
    "DefinitionError",
    "LockView",
    "Resolved",
    "ResourceView",
    "ToolView",
    "compile",
    "compile_file",
    "definitions_of",
    "load",
    "lock_view_for_project",
    "source_digest",
]

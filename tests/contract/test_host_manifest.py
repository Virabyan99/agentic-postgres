"""Host manifest contract (Session 2, Phase 1).

Every negative case here mutates a *copy of the real example* rather than
building a minimal document from scratch. Hand-built fixtures drift away from
the file operators actually edit, and then the test proves something about a
document nobody has.

The checks that need a live host — is the address assigned, does the operator
user exist, is the port open in the provider firewall — are deliberately absent.
They belong to ``bin/provision-host.sh --check``. This module must pass in CI,
where there is no host.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config, host_config
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

EXAMPLE = REPO_ROOT / "host.example.yaml"
SCHEMA = REPO_ROOT / "schemas" / "host.schema.json"


@pytest.fixture(scope="module")
def example() -> dict[str, Any]:
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


def write(directory: Path, document: dict[str, Any]) -> Path:
    path = directory / "host.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def load_mutated(directory: Path, example: dict[str, Any], mutate) -> dict[str, Any]:
    document = copy.deepcopy(example)
    mutate(document)
    return host_config.load_host_manifest(write(directory, document))


# ---------------------------------------------------------------------------
# The example itself
# ---------------------------------------------------------------------------


def test_example_manifest_is_valid() -> None:
    host_config.load_host_manifest(EXAMPLE)


def test_example_manifest_carries_no_secret_material(example: dict[str, Any]) -> None:
    """The Infisical block holds coordinates. It must never hold a credential."""
    config.assert_no_sensitive_keys(example)


def test_example_uses_documentation_only_addresses(example: dict[str, Any]) -> None:
    """A committed example naming a real host is a committed piece of recon."""
    assert example["host"]["expected_public_ipv4"].startswith("203.0.113.")
    assert example["ssh"]["allowed_source_cidrs"] == ["198.51.100.24/32"]


def test_example_starts_on_staging_acme(example: dict[str, Any]) -> None:
    """Production is reached only through edge.sh promote-acme."""
    assert example["edge"]["initial_acme_environment"] == "staging"


# ---------------------------------------------------------------------------
# Schema authority
# ---------------------------------------------------------------------------


def test_supported_releases_mirror_matches_the_schema() -> None:
    """ADR 0007: the schema owns anything the schema can express.

    ``host_config.SUPPORTED_OS_RELEASES`` exists only so error messages and
    ``provision-host.sh`` can name the allowlist. This asserts the mirror is a
    mirror, because a mirror that can drift is a second authority.
    """
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert set(schema["$defs"]["osRelease"]["enum"]) == set(host_config.SUPPORTED_OS_RELEASES)
    assert host_config.CANONICAL_OS_RELEASE in host_config.SUPPORTED_OS_RELEASES


def test_unknown_field_is_rejected_recursively(tmp_path: Path, example: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["edge"]["dashboard"] = True

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, example, mutate)


def test_manifest_cannot_widen_the_supported_release_allowlist(
    tmp_path: Path, example: dict[str, Any]
) -> None:
    """The single most important rule in this schema.

    If configuration could add a release, the supported-host contract would be
    whatever the operator typed, and the acceptance tests would be asserting
    against a moving target.
    """

    def mutate(document: dict[str, Any]) -> None:
        document["host"]["supported_os_releases"].append("22.04")

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, example, mutate)


def test_manifest_may_narrow_the_supported_release_allowlist(
    tmp_path: Path, example: dict[str, Any]
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["host"]["supported_os_releases"] = ["26.04"]

    assert load_mutated(tmp_path, example, mutate)["host"]["supported_os_releases"] == ["26.04"]


# ---------------------------------------------------------------------------
# SSH
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("port", [80, 443])
def test_ssh_port_may_not_collide_with_the_edge(
    tmp_path: Path, example: dict[str, Any], port: int
) -> None:
    """Discovering this collision at runtime costs either SSH or ingress."""

    def mutate(document: dict[str, Any]) -> None:
        document["ssh"]["port"] = port

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, example, mutate)


def test_at_least_one_ssh_source_cidr_is_required(tmp_path: Path, example: dict[str, Any]) -> None:
    """Required even when the answer is 0.0.0.0/0, so the choice is written down."""

    def mutate(document: dict[str, Any]) -> None:
        document["ssh"]["allowed_source_cidrs"] = []

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, example, mutate)


def test_host_bits_set_in_a_cidr_are_rejected(tmp_path: Path, example: dict[str, Any]) -> None:
    """`198.51.100.24/24` means 256 addresses and is almost always a typo.

    The schema pattern accepts it -- it is shape-correct -- which is why the
    semantic layer parses with ``strict=True`` rather than trusting the regex.
    """

    def mutate(document: dict[str, Any]) -> None:
        document["ssh"]["allowed_source_cidrs"] = ["198.51.100.24/24"]

    with pytest.raises(ManifestError, match="not a valid CIDR"):
        load_mutated(tmp_path, example, mutate)


def test_a_default_route_is_permitted_but_reported(tmp_path: Path, example: dict[str, Any]) -> None:
    """The accepted deviation for an operator with no static source address.

    It loads, because refusing it would push operators into deleting the field
    or inventing a fake CIDR. It is reported, because a deviation that produces
    no output stops being a deviation and becomes the default.
    """

    def mutate(document: dict[str, Any]) -> None:
        document["ssh"]["allowed_source_cidrs"] = ["0.0.0.0/0"]

    document = load_mutated(tmp_path, example, mutate)
    assert host_config.unrestricted_ssh_sources(document) == ["0.0.0.0/0"]


def test_a_restricted_cidr_is_not_reported_as_a_deviation(example: dict[str, Any]) -> None:
    assert host_config.unrestricted_ssh_sources(example) == []


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------


# S104 flags the literal "0.0.0.0" as a bind-to-all-interfaces address. Here it
# is the opposite: the parameter list is the set of addresses this test proves
# are *rejected*.
@pytest.mark.parametrize("address", ["127.0.0.1", "0.0.0.0", "224.0.0.1"])  # noqa: S104
def test_unroutable_public_addresses_are_rejected(
    tmp_path: Path, example: dict[str, Any], address: str
) -> None:
    """`format: ipv4` proves it parses, not that it could face the Internet."""

    def mutate(document: dict[str, Any]) -> None:
        document["host"]["expected_public_ipv4"] = address

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, example, mutate)


def test_a_private_address_requires_nat_mode(tmp_path: Path, example: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["host"]["expected_public_ipv4"] = "10.0.0.5"

    with pytest.raises(ManifestError, match="address_mode: nat"):
        load_mutated(tmp_path, example, mutate)


def test_a_private_address_is_accepted_in_nat_mode(tmp_path: Path, example: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["host"]["address_mode"] = "nat"
        document["host"]["expected_public_ipv4"] = "10.0.0.5"

    assert load_mutated(tmp_path, example, mutate)["host"]["address_mode"] == "nat"


def test_a_host_with_no_address_at_all_is_rejected(tmp_path: Path, example: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["host"]["expected_public_ipv4"] = None
        document["host"]["expected_public_ipv6"] = None

    with pytest.raises(ManifestError, match="no address for DNS"):
        load_mutated(tmp_path, example, mutate)


# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------


def test_production_acme_cannot_be_selected_from_source(
    tmp_path: Path, example: dict[str, Any]
) -> None:
    """`const`, not `enum`. This is the rate-limit guard.

    Promotion writes root-owned edge state through
    ``edge.sh promote-acme --to production --confirm <host.id>``. Editing the
    manifest is not a path to the production ACME directory.
    """

    def mutate(document: dict[str, Any]) -> None:
        document["edge"]["initial_acme_environment"] = "production"

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, example, mutate)


def test_control_and_egress_networks_must_differ(tmp_path: Path, example: dict[str, Any]) -> None:
    """Sharing one network puts the socket proxy on the project traffic segment."""

    def mutate(document: dict[str, Any]) -> None:
        document["edge"]["egress_network"] = document["edge"]["control_network"]

    with pytest.raises(ManifestError, match="must differ"):
        load_mutated(tmp_path, example, mutate)


def test_infisical_api_url_must_be_https_without_userinfo(
    tmp_path: Path, example: dict[str, Any]
) -> None:
    """`https://user:pw@host` is how a credential ends up in a committed file."""

    def mutate(document: dict[str, Any]) -> None:
        document["infisical"]["api_url"] = "https://id:secret@app.infisical.com"

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, example, mutate)


def test_plain_http_provider_url_is_rejected(tmp_path: Path, example: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["infisical"]["api_url"] = "http://app.infisical.com"

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, example, mutate)


# ---------------------------------------------------------------------------
# Strict parsing is inherited, not reimplemented
# ---------------------------------------------------------------------------


def test_duplicate_key_is_rejected(tmp_path: Path) -> None:
    """The Session 1 strict loader applies here too (runbook Phase 1)."""
    path = tmp_path / "host.yaml"
    path.write_text("schema_version: 1\nschema_version: 2\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="duplicate"):
        host_config.load_host_manifest(path)


def test_a_secret_bearing_key_is_rejected(tmp_path: Path, example: dict[str, Any]) -> None:
    """Rejected before the schema runs, so the message names the real problem."""
    document = copy.deepcopy(example)
    # S105: a synthetic value that exists to be rejected. Detecting it is the
    # test passing, which makes the lint finding an endorsement.
    document["infisical"]["client_secret"] = "st.abc123"  # noqa: S105
    with pytest.raises(ManifestError, match="secret material"):
        host_config.load_host_manifest(write(tmp_path, document))


# ---------------------------------------------------------------------------
# Every field a script reads must be a field the schema defines
# ---------------------------------------------------------------------------


def test_no_script_reads_an_infisical_field_the_schema_does_not_define() -> None:
    """The schema is ``additionalProperties: false``, so a field a script reads
    but the schema omits can never be present in a valid manifest.

    Not hypothetical. ``bin/bootstrap-providers.py`` read
    ``infisical["organization_id"]`` for a full run before anyone noticed the
    schema defined only ``organization_slug`` -- so ``--apply`` would have
    raised ``KeyError`` on a perfectly valid host.yaml, and the surrounding
    handler would have reported it as a provider failure. Nothing caught it
    because no offline test reaches that line and there was no host to run it.
    """
    import re

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    defined = set(schema["properties"]["infisical"]["properties"])

    pattern = re.compile(r"""infisical\[\s*["']([a-z_]+)["']\s*\]""")
    offenders: list[str] = []
    for relative in ("bin/bootstrap-providers.py", "bin/materialize-secrets.py"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        offenders.extend(
            f"{relative} reads infisical[{field!r}]"
            for field in sorted(set(pattern.findall(text)))
            if field not in defined
        )

    assert not offenders, (
        f"scripts read Infisical fields the host schema does not define: {offenders}. "
        f"Defined fields are {sorted(defined)}."
    )


def test_the_field_scan_would_catch_a_real_mismatch() -> None:
    """Guard the guard: the pattern must match the access form actually used."""
    import re

    pattern = re.compile(r"""infisical\[\s*["']([a-z_]+)["']\s*\]""")
    assert pattern.findall('organization = infisical["organization_id"]') == ["organization_id"]
    assert pattern.findall("x = infisical['api_url']") == ["api_url"]


def test_no_script_looks_for_a_top_level_block_inside_the_host_block() -> None:
    """``infisical``, ``ssh`` and ``edge`` are siblings of ``host``, not children.

    The second bug of the same family, and the one the field scan above could
    not see: three scripts wrote ``host["host"]["infisical"]``, which raises
    ``KeyError`` on every valid manifest. The field names were right; the level
    was wrong, so a scan looking at names found nothing.
    """
    import re

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    top_level = set(schema["properties"]) - {"host"}
    inside_host = set(schema["properties"]["host"]["properties"])

    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "bin").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for block in sorted(top_level):
            if re.search(rf"""\["host"\]\s*\[\s*["']{block}["']""", text):
                offenders.append(f"{path.name} reads host['host'][{block!r}]")

    assert not offenders, (
        f"{offenders}. These are top-level keys: {sorted(top_level)}. "
        f"Only {sorted(inside_host)} live inside the host block."
    )


def test_the_level_scan_would_catch_a_real_mismatch() -> None:
    """Guard the guard, on the exact string that shipped."""
    import re

    assert re.search(r"""\["host"\]\s*\[\s*["']infisical["']""", 'x = host["host"]["infisical"]')
    assert not re.search(r"""\["host"\]\s*\[\s*["']infisical["']""", 'x = host["infisical"]')


def test_every_field_path_a_shell_script_asks_for_resolves(example: dict[str, Any]) -> None:
    """Resolve each ``host_field a.b`` against the real example manifest.

    The third occurrence of the same family, and the first two tests could not
    see it: the access lived inside a Python heredoc embedded in a shell script,
    so a scan over ``bin/*.py`` never read it. ``host_field`` resolved from
    inside the ``host`` block while every caller passed a top-level path, and
    ``host_field network.public_interface`` named a block that does not exist.

    Both produced a bare ``KeyError`` on a live host with no field name in it.
    Resolving the paths against the committed example is what makes them
    checkable offline at all.
    """
    import re

    paths: list[tuple[str, str]] = []
    for path in sorted((REPO_ROOT / "bin").glob("*.sh")):
        text = path.read_text(encoding="utf-8")
        paths.extend(
            # Digits belong in the character class: without them
            # `expected_public_ipv4` is extracted as `expected_public_ipv` and
            # this test reports a failure against a field that is perfectly fine.
            (path.name, dotted)
            for dotted in set(re.findall(r"host_field\s+([a-z0-9_.]+)", text))
        )

    assert paths, "no host_field call was found; this test is measuring nothing"

    unresolved: list[str] = []
    for script, dotted in sorted(paths):
        value: Any = example
        for part in dotted.split("."):
            if not isinstance(value, dict) or part not in value:
                unresolved.append(f"{script}: host_field {dotted} (stopped at {part!r})")
                break
            value = value[part]

    assert not unresolved, f"field paths that do not exist in host.example.yaml: {unresolved}"


def test_the_path_walk_would_reject_a_bad_path(example: dict[str, Any]) -> None:
    """Guard the guard. The first version of the walk above checked each level
    without descending into it, so every two-part path failed at its second
    component -- it rejected the correct paths and would have accepted nothing.
    """

    def resolves(dotted: str) -> bool:
        value: Any = example
        for part in dotted.split("."):
            if not isinstance(value, dict) or part not in value:
                return False
            value = value[part]
        return True

    assert resolves("ssh.port")
    assert resolves("host.public_interface")
    assert resolves("edge.acme_email")
    assert not resolves("network.public_interface")
    assert not resolves("host.ssh.port")
    assert not resolves("ssh.nonexistent")


def test_the_field_path_resolver_starts_at_the_document_root() -> None:
    """``ssh`` and ``edge`` are siblings of ``host``, so resolution starts above
    all of them. Starting inside ``host`` makes every path silently wrong."""
    text = (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")
    body = text.split("host_field()", 1)[1].split("PYTHON\n}", 1)[0]
    assert 'load_host_manifest(Path(sys.argv[1]))["host"]' not in body, (
        "host_field resolves from inside the host block; callers pass full paths"
    )
    assert "sys.exit(" in body, (
        "host_field raises a bare KeyError instead of naming the missing field"
    )


def test_the_organization_id_is_a_uuid(example: dict[str, Any]) -> None:
    """The create calls take a UUID. A slug here fails at the provider, over the
    network, after a credential has already been sent."""
    import re

    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        example["infisical"]["organization_id"],
    )


def test_a_slug_in_the_organization_id_field_is_rejected(
    tmp_path: Path, example: dict[str, Any]
) -> None:
    document = copy.deepcopy(example)
    document["infisical"]["organization_id"] = "my-team"
    with pytest.raises(ManifestError):
        host_config.load_host_manifest(write(tmp_path, document))

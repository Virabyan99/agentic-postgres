"""What the deploy publishes about a cluster it just started.

`database.observed` is the only part of a deployed document a render cannot
produce, which makes it the only part that can be wrong in this project's
recurring way: a value that looked measured and was not. Every test here is
about the difference between measuring something and appearing to.
"""

from __future__ import annotations

import pytest

from agentic_postgres import database_observation as observation

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.database]

# Real output, kept verbatim. A trimmed fixture would let a parser pass that
# cannot read what a cluster actually prints.
MEMORY_STAT = """anon 65073152
file 430080000
kernel 12345678
kernel_stack 262144
pagetables 1441792
percpu 4032
sock 0
vmalloc 0
shmem 146800640
file_mapped 89141248
file_dirty 0
"""

SERVER_VERSION = "18.4 (Debian 18.4-1.pgdg13+3)\n"
EXTENSIONS = "plpgsql 1.0\nvector 0.8.6\n"
INSTANCE_UUID = "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f\n"


def test_the_three_memory_figures_are_kept_apart() -> None:
    """A single total averages an unreclaimable number with page cache and
    reports something true of neither."""
    assert observation.parse_memory_stat(MEMORY_STAT) == {
        "anon_mb": 62,
        "shmem_mb": 140,
        "file_mb": 410,
    }


def test_memory_current_is_not_what_is_read() -> None:
    """`memory.current` is the sum, and the sum hides which half grew.

    D52's budget is stated in the same three terms this reads, so a total could
    not be compared against it at all.
    """
    with pytest.raises(ValueError, match="cgroup v2"):
        observation.parse_memory_stat("memory.current 1234\n")


def test_a_partial_memory_stat_is_an_error_not_a_zero() -> None:
    with pytest.raises(ValueError, match="shmem_mb"):
        observation.parse_memory_stat("anon 1048576\nfile 2097152\n")


def test_the_version_keeps_the_number_and_drops_the_packaging() -> None:
    assert observation.parse_server_version(SERVER_VERSION) == "18.4"


@pytest.mark.parametrize("raw", ["", "  \n", "unknown\n"])
def test_a_version_that_is_not_a_version_is_refused(raw: str) -> None:
    with pytest.raises(ValueError):
        observation.parse_server_version(raw)


def test_extensions_are_a_mapping_of_installed_to_version() -> None:
    assert observation.parse_extensions(EXTENSIONS) == {"plpgsql": "1.0", "vector": "0.8.6"}


def test_an_empty_extension_list_is_refused() -> None:
    """`plpgsql` is in every database PostgreSQL creates.

    So an empty result is not "a cluster with no extensions" -- it is a query
    that did not run, and publishing `{}` for it would be indistinguishable
    from a real measurement.
    """
    with pytest.raises(ValueError, match="plpgsql"):
        observation.parse_extensions("")


def test_a_malformed_extension_row_is_refused() -> None:
    with pytest.raises(ValueError):
        observation.parse_extensions("vector\n")


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("", id="empty"),
        pytest.param("(0 rows)\n", id="psql-said-nothing"),
        pytest.param("01927D3F-1A2B-7C4D-8E5F-6A7B8C9D0E1F\n", id="uppercase"),
        pytest.param("01927d3f1a2b7c4d8e5f6a7b8c9d0e1f\n", id="unhyphenated"),
        pytest.param("01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f extra\n", id="trailing-token"),
    ],
)
def test_an_instance_uuid_that_is_nearly_one_is_refused(raw: str) -> None:
    """The registry matches on this string, so nearly-right is worse than absent.

    Uppercase is in this list on purpose. It is the same identity to a person and
    a different one to `==`, and the broker's answer to a mismatch is to refuse --
    which would be the right answer about the wrong thing.
    """
    with pytest.raises(ValueError, match="instance UUID"):
        observation.parse_instance_uuid(raw)


def test_the_block_is_whole_or_it_is_an_exception() -> None:
    """No member defaults. A partial observation is not published as a whole
    one, and it is not downgraded to `not_observed` either -- that would record
    "nobody looked" about a deploy that looked and failed."""
    document = observation.build_observation(
        server_version=SERVER_VERSION,
        extensions=EXTENSIONS,
        memory_stat=MEMORY_STAT,
        instance_uuid=INSTANCE_UUID,
    )
    assert document == {
        "status": "observed",
        "server_version": "18.4",
        "extensions": {"plpgsql": "1.0", "vector": "0.8.6"},
        "memory": {"anon_mb": 62, "shmem_mb": 140, "file_mb": 410},
        "instance_uuid": "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f",
    }

    with pytest.raises(ValueError):
        observation.build_observation(
            server_version=SERVER_VERSION,
            extensions="",
            memory_stat=MEMORY_STAT,
            instance_uuid=INSTANCE_UUID,
        )
    with pytest.raises(ValueError):
        observation.build_observation(
            server_version=SERVER_VERSION,
            extensions=EXTENSIONS,
            memory_stat=MEMORY_STAT,
            instance_uuid="",
        )


def test_the_observed_members_are_exactly_what_the_schema_requires() -> None:
    """Guard the guard: a builder that omitted a member the schema requires
    would be caught by validation, but a builder that produced a member the
    schema does not name would not be -- `additionalProperties` is checked on
    the document, and this block is validated on its own in one test above.
    """
    from agentic_postgres import config

    schema = config.load_schema("outputs.schema.json")["$defs"]["databaseObserved"]
    built = observation.build_observation(
        server_version=SERVER_VERSION,
        extensions=EXTENSIONS,
        memory_stat=MEMORY_STAT,
        instance_uuid=INSTANCE_UUID,
    )
    assert set(built) == set(schema["required"]) == set(schema["properties"])


def test_the_observation_validates_against_the_schema() -> None:
    """The block is only useful if a deployed document will accept it.

    Validated against the schema's own `$defs.databaseObserved` rather than
    against a copy of its rules written here, which would agree with itself
    forever.
    """
    import jsonschema

    from agentic_postgres import config

    document = observation.build_observation(
        server_version=SERVER_VERSION,
        extensions=EXTENSIONS,
        memory_stat=MEMORY_STAT,
        instance_uuid=INSTANCE_UUID,
    )
    schema = config.load_schema("outputs.schema.json")
    jsonschema.validate(document, {"$defs": schema["$defs"], **schema["$defs"]["databaseObserved"]})

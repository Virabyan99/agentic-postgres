"""An operator command imports only what the host has (D292, ADR 0093).

`bin/auth-admin.py` imported `app.hashing` from `services/auth-api/`, which
imports `argon2` at module scope. `argon2-cffi` is pinned in exactly one place --
the auth service's Dockerfile -- so it exists inside that image and nowhere else.
The host has no venv and its `python3` has no such package.

The command was therefore unrunnable on the only machine it is ever run on. It
failed with `ModuleNotFoundError: No module named 'argon2'` at the first host
bootstrap, after a deploy that had otherwise fully succeeded, at the last step
before `routes.app` could be published.

**Nothing offline could have caught it, and the reason is worth stating.** Every
proof of this command runs in the repository's own virtualenv, which installs the
service's dependencies so that the service's tests can run. The venv is a
superset of both the host and the image, so a module that could only work in one
of them works in the venv. That is ADR 0065/0066's class again, in its last
remaining hiding place: not a rig that configures the product differently, but an
*environment* that is more capable than either place the code actually runs.

So this module asserts the boundary rather than the symptom: the operator plane
runs on a host that has Python, Docker and nothing else, and reaches everything
else through a container.
"""

from __future__ import annotations

import ast

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

BIN = REPO_ROOT / "bin"
SERVICES = REPO_ROOT / "services"

#: Top-level packages the host is guaranteed to have: the standard library, and
#: this repository's own `src/`. Anything else has to be reached through a
#: container.
#:
#: `yaml` is the one third-party exception and it is deliberate: the host
#: installs PyYAML as a system package because `provision-host.sh` needs it
#: before any container exists. It is listed rather than inferred, so a second
#: exception has to be argued for rather than added.
HOST_PACKAGES = {"agentic_postgres", "yaml"}

#: Commands that run in a CHECKOUT and never on the host, with the reason.
#:
#: The distinction is real and this test found it: `bin/app-contract.py` imports
#: the service's `app` package for the same reason `auth-admin.py` did, and is
#: fine, because it reviews a committed OpenAPI snapshot in a working tree where
#: the venv has the service's dependencies. It is never run by an operator on a
#: deployment host, and `test_no_checkout_only_command_is_run_in_host_mode`
#: below is what keeps that true rather than assumed.
#:
#: Adding to this set is a claim that a command is developer-facing. It is not a
#: way to quiet the check for something an operator runs.
CHECKOUT_ONLY = {
    # Compares the reviewed application-API document against what `create_app`
    # produces. Needs FastAPI to produce it, runs under `--mode offline`, and
    # `--render-only` and the host gate never call it.
    "app-contract.py",
}


def _service_packages() -> set[str]:
    """Top-level package names that live only inside a service image."""
    return {
        path.name
        for service in SERVICES.iterdir()
        if service.is_dir()
        for path in service.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }


def _imports(tree: ast.AST) -> set[str]:
    """Every top-level package name a module imports, at any depth."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_at_least_one_service_package_exists() -> None:
    """Otherwise the check below is vacuous.

    `services/auth-api/app/` is the package that caused this. If the layout
    changes so that nothing is found, the scan would pass against a `bin/`
    importing anything at all.
    """
    packages = _service_packages()
    assert packages, "no service packages were found; the scan below would measure nothing"
    assert "app" in packages, f"expected the auth service's `app` package, found {packages}"


def test_no_operator_command_imports_a_service_package() -> None:
    """The boundary, as a property of the source.

    An operator command runs on the host as root. A service package runs inside
    an image built for it, with dependencies the host does not have and is not
    meant to have -- `argon2-cffi`, `fastapi`, `psycopg`, `uvicorn`.

    Reaching the service's logic is not forbidden; reaching it *by import* is.
    `bin/auth-admin.py` now runs the hasher with `docker exec` into the auth
    container, which is both runnable and stricter: the hash is produced by the
    process that will verify it.

    Note that `src/agentic_postgres/service_source.py` imports the same package
    on purpose (ADR 0084) and is not a `bin/` command. That is the seam: pure
    contract facts may be imported into the library, and the library is used by
    tests, which run in a venv. An operator command may not.
    """
    service_packages = _service_packages()
    offenders: dict[str, list[str]] = {}

    for path in sorted(BIN.glob("*.py")):
        if path.name in CHECKOUT_ONLY:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        reached = sorted(_imports(tree) & service_packages)
        if reached:
            offenders[path.name] = reached

    assert not offenders, (
        f"these operator commands import a package that exists only inside a service "
        f"image: {offenders}. They run on the host, which has no such package, and fail "
        "with ModuleNotFoundError at the moment they are most needed (D292). Reach the "
        "service's logic through a container instead."
    )


def test_no_operator_command_puts_a_service_directory_on_the_path() -> None:
    """The other half, and the one that made the import look legitimate.

    `bin/auth-admin.py` did `sys.path.insert(0, REPO_ROOT / "services" / "auth-api")`
    before importing `app.hashing`, which is what made a package that is not
    installed anywhere importable *in a checkout*. A `bin/` command that does
    this is telling the reader the import is fine, and it is fine everywhere
    except the host.
    """
    offenders: list[str] = []
    for path in sorted(BIN.glob("*.py")):
        if path.name in CHECKOUT_ONLY:
            continue
        source = path.read_text(encoding="utf-8")
        if '"services"' in source and "sys.path" in source:
            offenders.append(path.name)

    assert not offenders, (
        f"these operator commands add a service directory to sys.path: {offenders}. That "
        "makes an image-only package importable in a checkout and nowhere else"
    )


def test_operator_commands_import_only_host_packages() -> None:
    """The general form: the whole third-party surface of `bin/`, listed.

    Broader than the two checks above and deliberately so -- the defect was not
    really about `app`, it was about `bin/` depending on something the host does
    not install. A new third-party import here is a new host prerequisite, and
    that should be an explicit decision rather than a `ModuleNotFoundError` on a
    machine somebody has driven to at the end of a deploy.
    """
    standard = set(getattr(__import__("sys"), "stdlib_module_names", frozenset()))
    assert standard, "this interpreter does not expose stdlib_module_names"

    unexpected: dict[str, list[str]] = {}
    for path in sorted(BIN.glob("*.py")):
        if path.name in CHECKOUT_ONLY:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        outside = sorted(_imports(tree) - standard - HOST_PACKAGES)
        if outside:
            unexpected[path.name] = outside

    assert not unexpected, (
        f"these operator commands import packages the host is not known to have: "
        f"{unexpected}. Either add the package to HOST_PACKAGES with a reason and make "
        "`provision-host.sh` install it, or reach it through a container."
    )


def test_no_checkout_only_command_is_run_in_host_mode() -> None:
    """`CHECKOUT_ONLY` is a claim, and this is what makes it one that can fail.

    A command excused from the import check because "it only runs in a checkout"
    is excused on a promise about where it is invoked. Every session gate has a
    host mode, and if one of them called such a command the promise would be
    false and the failure would land on a host, mid-deploy, which is exactly
    where D292 landed.

    Checked against each gate's `mode_host` function rather than the whole file:
    `mode_offline` calls `bin/app-contract.sh` on purpose, and a scan of the
    whole script would report that as a violation.
    """
    stems = {name.removesuffix(".py") for name in CHECKOUT_ONLY}
    offenders: dict[str, list[str]] = {}

    for gate in sorted(BIN.glob("session-*-check.sh")):
        source = gate.read_text(encoding="utf-8")
        start = source.find("mode_host()")
        if start == -1:
            continue
        end = source.find("\nmode_external()", start)
        body = source[start : end if end != -1 else len(source)]
        called = sorted(stem for stem in stems if stem in body)
        if called:
            offenders[gate.name] = called

    assert not offenders, (
        f"these gates call a checkout-only command in host mode: {offenders}. Those "
        "commands import packages the host does not have, so the gate would fail on the "
        "host with ModuleNotFoundError (D292)."
    )

# 0093 — An operator command reaches service logic through a container

Status: accepted
Date: 2026-08-15
Session: 6, Run 12
Affects: ADR 0065, ADR 0066, ADR 0081, ADR 0084, D292, `bin/auth-admin.py`

## Context

`bin/auth-admin.sh` creates the first project administrator. It is the last step
before `routes.app` can be published, it is run by a human at a terminal on the
deployment host, and until now it began like this:

```python
sys.path.insert(0, str(REPO_ROOT / "services" / "auth-api"))
from app.hashing import Hasher, PasswordRejected, assess
```

`app.hashing` imports `argon2` at module scope. `argon2-cffi` is pinned in
exactly one place in this system — the auth service's Dockerfile — so it exists
inside that image and nowhere else. The host has no virtualenv and its `python3`
has no such package.

The command was therefore unrunnable on the only machine it is ever run on. It
failed on the first host bootstrap, after a deploy that had otherwise fully
succeeded:

```
ModuleNotFoundError: No module named 'argon2'
```

**Nothing offline could have caught it.** Every proof of this command runs in the
repository's own virtualenv, which installs the service's dependencies so that
the service's own tests can run. The venv is a *superset* of both the host and
the image, so code that could only work in one of them works there. That is ADR
0065 and 0066's class in its last hiding place: not a rig that configures the
product differently, but an **environment more capable than either place the code
actually runs**.

## Decision

**An operator command reaches a service's logic by running it inside that
service's container, never by importing it.**

`bin/auth-admin.py` now screens and hashes the password with `docker exec` into
the project's running `auth` container, over stdin, and receives the PHC string
on stdout. It imports nothing from `services/`.

The rule has a seam, and the seam is where ADR 0084 already drew it:

* `src/agentic_postgres/` **may** import pure contract facts from the service's
  package (`service_source.load`) — that is ADR 0084, and it is used by tests,
  which run in a venv;
* `bin/*.py` **may not**, because it runs on a host that has Python, Docker and
  nothing else.

## Why this is better than making the import work

Installing `argon2-cffi` on the host would have been one line in
`provision-host.sh`, and it is the wrong line:

* it puts a second Argon2 build in the system, and ADR 0081's whole subject is
  that the profile a hash was produced at must be knowable from the hash. Two
  builds is two answers to "what produced this";
* the host's build would drift from the image's on any upgrade of either, and
  the failure would be an administrator who cannot log in — discovered at a
  login, not at a deploy;
* it widens the host's dependency surface for a value that exists for one
  command, one time, per project.

Running it in the container is the stronger arrangement rather than the
expedient one: **the hash an administrator is created with is produced by the
very process that will later verify it**, at the same build and the same frozen
profile. That property was not available by import at all.

## Consequences

The password still never reaches argv — it goes to the container on stdin, for
the same reason it goes to `psql` on stdin. Only the forbidden values (the
username and the project key, neither secret, both already in the deployed
document) are arguments.

The auth container must be running to bootstrap. That is true anyway — the
bootstrap follows a completed deploy, which starts it — and the command says so
plainly when it is not.

`tests/contract/test_operator_commands_run_on_the_host.py` asserts the boundary
in four ways: no `bin/` command imports a service package, none puts a service
directory on `sys.path`, none imports any third-party package outside a listed
host set, and — the one that keeps the exception honest — **no gate calls a
checkout-only command from its host mode**.

That last check exists because writing this test immediately found a second
instance: `bin/app-contract.py` imports the same package for the same reason. It
is legitimate, because it reviews a committed OpenAPI snapshot in a working tree
and is never run on a host. `CHECKOUT_ONLY` records that claim, and the host-mode
check is what would falsify it.

Mutation-tested by restoring the import: three of the five assertions go red.

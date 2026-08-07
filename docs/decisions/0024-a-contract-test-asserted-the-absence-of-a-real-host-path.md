# 0024 — A contract test asserted the absence of a real host path

- **Status:** Accepted
- **Date:** 2026-08-07
- **Session:** 2
- **Affects:** `tests/contract/test_bootstrap_state.py::test_missing_credential_files_are_reported_as_repair`

## Context

`test_missing_credential_files_are_reported_as_repair` builds a state document
with `make_state()` and asserts that both of its credential files are missing:

```python
document = make_state()
assert sorted(bootstrap_state.needs_credential_repair(document)) == [
    "client_id_path",
    "client_secret_path",
]
```

`make_state()` defaults to `project_key="alpha-dev"` and fills
`credential_files` from the real `bootstrap_state.credential_paths()`, so those
two paths are literally
`/etc/agentic-postgres/credentials/alpha-dev/infisical-client-id` and
`…/infisical-client-secret`.

`alpha-dev` is the name of a project actually deployed to the Session 2 host.
Those files exist there, `0400 root`, created by `bootstrap-providers.sh
--apply`. The assertion is therefore a claim about the machine the suite is
running on, not about the code: it passes wherever no project named `alpha-dev`
has been bootstrapped, and fails on the one host where the thing it describes
is real.

Run 7 is the first time `bin/session-01-check.sh` has run on a host with two
projects deployed, and it failed there:

```
E  AssertionError: assert [] == ['client_id_path', 'client_secret_path']
```

The gate is required to exit 0 on a clean tree at the end of every run, and it
runs on the deployment host — that requirement is why ADR 0013's D13 exists at
all. So this is not a test that merely *could* meet a hostile environment; it
meets one by design, every run, from now on.

Two further points make the current form worse than it looks.

**The test already asks for `tmp_path` and uses it for only half the
assertion.** The second half writes a real file into `tmp_path` and points
`client_id_path` at it. Someone reached for hermeticity, got it for one path,
and left the other reading `/etc`.

**Non-root cannot observe the behaviour at all.** Credential files live under a
`0700 root` directory, so `Path.is_file()` raises `PermissionError` for any
other caller, and `needs_credential_repair` deliberately treats unreadable as
intact (that choice stands; reporting a repair on an unreadable path would send
an operator to re-issue a credential that is present and healthy, which is the
credential leak the function exists to prevent). The gate runs as the operator
account. So on the host this test could only ever have seen `[]` — from the
permission branch if the directory was unreadable, and from the file existing
if it was not.

## Decision

The test becomes hermetic: `credential_files` is pointed at `tmp_path` for
both entries, and the assertions are about `needs_credential_repair`'s logic
rather than about `/etc`.

This is a strengthening, not a weakening, on three counts:

- It can now fail for the right reason. Before, it passed on a developer
  machine because of an accident of that machine's filesystem, and no amount of
  breaking `needs_credential_repair` would have been noticed there as reliably
  as the current false failure is noticed.
- The truth table is completed. The old test covered "both missing" and "one
  present". It now also covers "both present", which is the case an ordinary
  converged apply takes and the one whose regression would be silent.
- The documented `PermissionError` behaviour gains its first test. It is
  asserted by patching `Path.is_file` to raise, not by `chmod`, so it holds
  whether the suite runs as root or not — a `chmod 0000` test would pass as the
  operator and fail as root, reintroducing exactly the machine dependence this
  ADR removes.

Nothing about `bootstrap_state.needs_credential_repair`,
`credential_paths`, or `validate_state` changes.

`make_state()` keeps returning real `credential_paths()`, and deliberately.
`validate_state` *requires* a state document to name exactly those paths — a
state file naming another project's directory is the cross-project escape it
refuses — so a fixture that returned `tmp_path` paths would make every
validation test in the module test the wrong document. The two concerns are
separate, and only the test that asserts about the filesystem needs to override
the field.

## Consequences

- `bin/session-01-check.sh` exits 0 on the deployment host with projects
  deployed, which is a standing requirement rather than a Run 7 convenience.
- The test no longer tells anyone whether `/etc/agentic-postgres/credentials`
  is populated. It never usefully did; it reported the state of whichever
  machine ran it.
- One test in this module still reads a real absolute path: none. The scan that
  would keep it that way is not written here, because the general form — "no
  contract test may depend on the presence or absence of a host path" — is not
  mechanically checkable from inside the process that would have to violate it
  to find out.

## Alternatives considered

**Give `make_state()` a `project_key` no real deployment will use.** Rejected:
it makes the test pass by betting that nobody deploys a project with that name,
which is the same bet the current test makes about `alpha-dev` and lost. The
failure would also return silently, years later, to whoever chose the name.

**Skip the test when the paths exist.** Rejected: a test that skips exactly
when its subject is real is worse than one that fails there. It would report
green on the host while measuring nothing, and ADR 0018's rule — a check that
cannot reach the thing reports that, not a verdict — is the same principle
pointing the other way.

**Run the gate as root on the host so the paths are readable.** Rejected: it
would fix the permission half and not the existence half — as root the files
are readable *and present*, so the assertion still fails — and it would leave
root-owned artifacts in a checkout the operator account has to keep clean for
the gate's own step 1.

**Leave it, and accept the gate failing on the host.** Rejected: the gate
exiting 0 on a clean tree is a stated non-negotiable, and a known-failing test
in it teaches everyone to read a red gate as normal.

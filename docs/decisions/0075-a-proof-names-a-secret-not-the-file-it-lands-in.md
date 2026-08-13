# 0075 — A proof names a secret, not the file it lands in

Status: accepted
Date: 2026-08-13
Session: 6, Run 1
Amends: [0056](0056-a-consumer-declares-the-format-its-file-is-written-in.md)
Affects: SEC-BOOT-001, SEC-DOCS-001, SEC-DBX-004, DEP-ISO-004, DEP-ISO-005

## Context

Session 6's Run 1 is Session 5's deferred rotation window. Preparing it meant
reading the three proofs it exists to admit, and one of them cannot run:

    tests/deployment/test_session5_convergence.py
      ::test_a_rotated_authenticator_serves_the_plane_and_the_old_password_does_not

    new = materialized_secret(key(project_a), "postgrest", "postgrest_authenticator_password")

`materialized_secret` took a project key, a consumer directory and **a
filename**, and joined them. The materializer does not write a file by that
name. `postgrest_authenticator_password` is the secret's name in
`secrets.required.yaml`; its one consumer declares
`target_file: postgrest_authenticator_pgpass` and `format: pgpass`, because the
PostgREST image has no shell and the file has to arrive in the shape libpq reads
(ADR 0056). So the fixture would have called `pytest.fail` on its first
execution — in a maintenance window, after a credential had already been
rotated and could no longer be recovered.

Measured offline against the committed contract, with a control: the same lookup
for `pgbouncer` / `app_runtime_password` resolves, so the miss is this consumer's
and not the mechanism's.

**The filename is the only entry in the contract where the two differ.** Every
other secret's `target_file` equals its `name`, so "the filename is the secret's
name" held for twelve consumers out of thirteen and was wrong for the one whose
proof had never run.

Two further things follow, and the second is worse than the first.

Had the filename been right, `new` would have been the **pgpass line**
`*:*:*:*:<password>`, not the password. The assertion directly beneath it —

    assert old != new, "the value declared as pre-rotation is the active one;
                        nothing was rotated"

— is the control that refuses a false declaration, and it would have been
incapable of failing: a password is never equal to a line containing it. A
window in which nothing was rotated would then have reached the next assertion
and failed there, reporting *"the pre-rotation authenticator password still
opens the cluster; the verifier was not replaced"* — a diagnosis of the bootstrap
plane, for a window where the true finding was that nobody rotated anything.
That is the failure this repository already wrote a rule about: do not compile a
diagnosis into an error message.

And the correct idiom was already in the repository, one file away.
`tests/deployment/test_session5_api_isolation.py` reads
`postgrest_authenticator_pgpass` and passes it through
`secrets_contract.recover_secret`. **Two spellings of one object**, which is
D173 exactly — and the spelling that had run was the right one.

## Decision

**A test names a secret and who holds it. The filename and the format are
derived.**

`secrets_contract.consumer_named(contract, secret_name, consumer_key)` returns
the declared secret and the one consumer whose `consumer_directory` matches —
a service name, or `_root` for a value no container holds. `materialized_secret`
is built on it, resolves the path through the existing `secret_source_path`, and
returns `recover_secret(...)` of the bytes.

So a caller receives **the provider's value**, whatever shape the file is in, and
cannot spell a path at all. For a `raw` consumer that is the file's bytes without
their trailing newline, which is exactly what the fixture returned before.

A miss raises rather than returning `None`. Every caller is asking about a grant
it believes exists, and a soft miss reads as "this secret is not held here" —
a security claim nobody measured. Both messages name identifiers only, because
this runs as root beside real generation directories.

## Alternatives

**Correct the one filename.** Rejected. It restores the second, worse defect: the
test would then hold a pgpass line believing it held a password, its
false-declaration control would be dead, and the run would misdiagnose. The
cheap fix is the one that keeps the trap loaded.

**Recover at the call site**, as `test_session5_api_isolation.py` did. Rejected:
that is the shape that produced two spellings. It leaves every future caller free
to write the filename and forget the recovery, and the two proofs that read this
secret would still be free to disagree.

**Declare a second `raw` consumer for the authenticator.** Rejected outright.
It materializes a second copy of one credential — the thing this contract's
per-consumer layout exists to prevent, argued at length in three of its own
comments — so that a test can avoid one function call. It also gives a rotation
two files to reach.

## Consequences

- `test_a_rotated_authenticator_serves_the_plane_and_the_old_password_does_not`
  can execute. It never has.
- `test_session5_api_isolation.py` loses eleven lines and its local contract
  load; the assertion is unchanged.
- The operator's declared pre-rotation value is **the password**, and
  `docs/api-operations.md` now says so with a command that produces one. It
  previously showed `sudo cat …/postgrest/…`, whose output is a pgpass line.
- Four mutations, each paired with a control in the same invocation: ignoring the
  holder is caught by the wrong-holder refusal and by the five-consumer
  discrimination; returning the whole pgpass line is caught by the round-trip
  over every declared consumer; renaming `target_file` in the contract is caught
  by the filename assertion. The root-plane lookup does **not** catch the first
  of those, because that secret has one consumer — recorded here because it was
  written as a detector and measured not to be one.
- **The finding is not the filename.** It is that a proof gated behind a
  maintenance window nobody had held was carrying a wrong constant, and that the
  right constant was already written down in a sibling file. Fifth instance in
  two runs, after D211–D214.

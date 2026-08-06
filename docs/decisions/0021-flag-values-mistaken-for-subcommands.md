# 0021 — A Compose flag's value can be mistaken for the subcommand

- **Status:** Accepted
- **Date:** 2026-08-06
- **Session:** 2
- **Affects:** `bin/compose.sh`, `tests/contract/test_compose_contract.py`

## Context

`bin/compose.sh`'s `first_subcommand()` picks the Compose subcommand out of
`COMPOSE_ARGS` by scanning for the first token that does not begin with `-`:

```sh
first_subcommand() {
  local argument
  for argument in "${COMPOSE_ARGS[@]+"${COMPOSE_ARGS[@]}"}"; do
    case "${argument}" in
      -*) ;;
      *) printf '%s' "${argument}"; return 0 ;;
    esac
  done
}
```

It does not know that some Compose flags consume the following token as a
value rather than standing alone. `--profile` is one: `--profile session2 up`
is, to Compose, the flag `--profile` with value `session2`, followed by the
subcommand `up`. To `first_subcommand`, `session2` is the first token that
doesn't start with `-`, so it is returned as the subcommand. `up` is never
looked at by the gate at all, though it is still passed to Compose verbatim in
`COMPOSE_ARGS` and Compose acts on it.

This one gap in one function has two independent consequences, discovered
while wiring `bin/deploy-session-2.py`'s `_model_digest` to run under
`--runtime` (final fix wave, item 3 of the Session 2 remainder):

**1. The runtime path was dead.** `bin/project-runtime.sh` is the only caller
of `--runtime up` and `--runtime down` in this repository, and both calls are
shaped `--runtime --profile session2 <subcommand>`:

```
bin/project-runtime.sh:142   compose.sh "${rendered}" --runtime --profile session2 up -d --wait
bin/project-runtime.sh:163   compose.sh "${rendered}" --runtime --profile session2 down
```

Sourcing the real `parse_arguments` and `first_subcommand` out of the
unmodified script and calling them with the exact `up` arguments confirms:

```
RUNTIME=1
COMPOSE_ARGS=--profile session2 up -d --wait
subcommand=session2
```

`session2` is not in `RUNTIME_ALLOWED` ("up down restart build ps config
logs"), so `main()`'s allowlist check fires every time:

```
die 10 "'session2' is not permitted in --runtime mode; allowed: ..."
```

`bin/project-runtime.sh up` and `down` could not previously succeed against a
real Docker daemon as root — an unconditional `die 10` on every invocation.
Deploy step 5 ("Start the project") in `bin/deploy-session-2.py`, which shells
out to `project-runtime.sh up`, inherits the same failure.

No test caught this. `test_runtime_mode_requires_root` in
`tests/contract/test_compose_contract.py` calls `compose(ALPHA, "--runtime",
subcommand)` with no `--profile`, and exits at the *privilege* check (exit 3,
unprivileged) before subcommand detection is ever exercised with a
value-taking flag in front of it.

**2. The FORBIDDEN gate — Session 1's original, absolute guarantee — can be
defeated by any caller, without `--runtime`, without root.** Compare:

```
compose.sh .generated/fixture-alpha-dev up                     -> refused, exit 10
compose.sh .generated/fixture-alpha-dev --profile contract up  -> not refused
```

Without `--runtime`, `main()` takes the `elif in_list "${subcommand}"
"${FORBIDDEN}"` branch. With `--profile contract` in front of `up`,
`first_subcommand` returns `contract`, which is not in `FORBIDDEN`. The
refusal that is supposed to fire for every container-starting subcommand,
unconditionally, by default, does not fire — and the real `docker compose`
invocation that follows still receives `up`, unexamined, in `COMPOSE_ARGS`.
Prefixing any `--profile` (or `--file`, `--env-file`, `--project-name`, ...)
ahead of a forbidden subcommand is enough to walk through the gate ADR 0013
describes as "Session 2's largest security control."

The gate's own validation call, `--profile contract config` (used throughout
`tests/contract/test_compose_contract.py` and by `_model_digest`), has never
actually validated `config` for the same reason — it validated `contract` and
found it, correctly but uselessly, not forbidden.

## Decision

`first_subcommand` becomes value-aware. A new constant lists every Compose
global flag that consumes a separate following token as its value:

```sh
readonly SUBCOMMAND_VALUE_FLAGS="--profile --file -f --env-file --project-name -p --project-directory --parallel --progress --ansi"
```

`first_subcommand` skips the token immediately after any argument matching
this list, in addition to skipping the flag token itself. A flag written
`--flag=value` needs no entry: the value is inside the same token, already
matched and skipped by the existing `-*` case, and consumes nothing further.

This is fixed in the parser, not by reordering the two call sites in
`bin/project-runtime.sh`. Nothing about `bin/project-runtime.sh`'s source
changes, so `test_the_project_runtime_attaches_after_starting_and_detaches_before_stopping`
in `tests/contract/test_root_script_policy.py`, which pins the literal
substrings `"--profile session2 up"` and `"--profile session2 down"` in that
file, is untouched by this ADR.

## Consequences

- `bin/deploy-session-2.py`'s `_model_digest` can call
  `bin/compose.sh --runtime --profile contract config` and have it resolve to
  `config`, which is what item 3 of the final fix wave needed and could not
  safely do before this ADR.
- `bin/project-runtime.sh up` and `down` reach the allowlist check with the
  correct subcommand for the first time.
- Three tests in `tests/contract/test_compose_contract.py` pin both
  consequences by invoking the real script and the real `first_subcommand`
  function (not by matching source text):
  - `test_a_flag_with_a_value_cannot_smuggle_a_container_start` — `--profile
    session2 up` with no `--runtime` is still refused, exit 10.
  - `test_runtime_call_with_a_flag_value_still_reaches_the_privilege_gate` —
    `--runtime --profile session2 up`, run unprivileged, still dies 3 at the
    root check rather than erroring some other way, so the parser change does
    not disturb the check ordering `test_runtime_mode_requires_root` already
    pins.
  - `test_first_subcommand_skips_a_flags_value` — calls the real
    `first_subcommand` (sourced out of the script, not re-implemented) with
    `--profile session2 up`, `--profile session2 down`, and `--profile
    contract config`, and asserts it returns `up`, `down`, and `config`
    respectively. This is the test that would have caught both consequences
    directly; the root check in `main()` makes the two subprocess-level tests
    unable to distinguish a correct resolution from an incorrect one for an
    unprivileged caller, since the privilege check runs first regardless of
    which subcommand was resolved (by design, per ADR 0013 /
    `test_runtime_mode_requires_root`'s own docstring).
- The flag list in `SUBCOMMAND_VALUE_FLAGS` is Compose's, not this
  repository's, and is only as complete as enumerated above. A future flag
  this repository starts passing ahead of a subcommand needs an entry added
  here or it reintroduces the same class of defect.

## Alternatives considered

**Reorder the two call sites so the subcommand comes first
(`up --profile session2` instead of `--profile session2 up`).** Rejected:
`docker compose` requires global flags like `--profile` before the
subcommand, not after, so this is not just a cosmetic reorder — it also
changes what `docker compose` itself does with the flag. It would also
require rewriting the literal strings
`test_the_project_runtime_attaches_after_starting_and_detaches_before_stopping`
matches, which is a contract test change with no independent justification
beyond working around this bug.

**Adopt `--flag=value` everywhere instead of `--flag value`.** This does fix
`first_subcommand` without touching it, since `-*` already skips
`--profile=session2` as one token. Rejected for the same reason as above: it
still rewrites the literal substrings the same contract test matches, and it
only protects call sites this repository controls — an operator typing
`--profile foo up` at the shell (a documented, supported invocation shape)
would still defeat the gate.

**Leave it.** Rejected: consequence 2 is a live security defect in the
control ADR 0013 calls "Session 2's largest security control," reachable
without `--runtime` and without root.

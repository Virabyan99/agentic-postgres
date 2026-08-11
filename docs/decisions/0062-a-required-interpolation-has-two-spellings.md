# 0062 — A required interpolation has two spellings, and which one is not a style choice

Status: accepted
Date: 2026-08-11
Session: 5, Run 9
Amends: [0013](0013-compose-wrapper-scopes.md)
Affects: DEP-ISO-002, CFG-001

## Context

`test_every_interpolation_is_required` has asserted since Session 1 that every
`${...}` in `compose.yaml` ends `:?required}`:

```python
for reference in re.findall(r"\$\{[^}]+\}", text):
    assert reference.endswith(":?required}")
```

The property it protects is real and is not negotiable: **a bare `${VAR}`
renders empty, and an empty resource name would collapse two projects onto one
network.** That is `DEP-ISO-002`, and it is the isolation guarantee the whole
model rests on.

D178 then produced a case the rule did not anticipate. Compose's two required
forms are not equivalent:

| spelling | unset | empty |
|---|---|---|
| `${VAR:?err}` | fails | **fails** |
| `${VAR?err}` | fails | renders `""` |

Measured against Compose 29.5.2, both spellings against both inputs, with a
non-empty control.

`POSTGREST_CORS_ORIGINS` is the one variable in the model whose empty value is
*meaningful*: an empty allowed-origins list means "permit no cross-origin
browser request", and it is the correct rendering for a project that declares no
REST service — which D150 makes optional and which `build_compose_env` emits as
an empty string. Under `:?` that project could not render at all. The first live
deploy of Session 5 failed at step 1 for exactly this reason, having touched
nothing on the host.

So the original rule is right about every variable except one, and wrong about
that one in a way that is invisible until an empty value actually occurs.

## Decision

**Both required forms are permitted, and which one a variable takes is derived
rather than chosen.**

`test_every_interpolation_is_required` is **replaced by a stricter pair**, not
weakened. It keeps refusing a bare `${VAR}` and a defaulted `${VAR:-x}`, and it
now accepts either required form — while the question it used to answer by
spelling is answered by measurement instead, in
`test_no_required_interpolation_names_a_value_that_renders_empty`:

- every variable the renderer can emit **empty** must be referenced `${VAR?...}`
- every variable referenced `${VAR?...}` must be one the renderer can emit empty

Both sets are derived: the first from an actual render of a manifest with no
`api.rest`, the second from the model's own text. Neither is a hand-written
allowlist, so the two cannot agree while both are wrong.

**This is stricter than what it replaces in the direction that matters.** The
old rule permitted `:?` on a variable that renders empty — which is the defect
D178 records, and it passed for the entire life of the file. The new rule refuses
it. It also refuses the opposite error, a variable given the lax spelling when it
can never legitimately be empty, which the old rule could not express at all.

The load-bearing half lives in `tests/contract/test_output_schema.py` rather than
beside the old assertion in `tests/contract/test_compose_contract.py`, and that
placement is deliberate: the compose module skips entirely unless
`.generated/fixture-alpha-dev` has been rendered, so an assertion there is one
that does not run in a clean checkout. That is also why the original rule's gap
went unnoticed — the module was skipped in the gate that would have caught it.

The rejected alternatives:

**A sentinel origin for the empty case.** `PGRST_SERVER_CORS_ALLOWED_ORIGINS`
would then carry a value PostgREST parses as an origin, and "no origins" would be
spelled as "one origin nobody uses". A permissive default wearing a disguise.

**Make the `postgrest` service conditional on `api.rest.enabled`.** D150 refused
this deliberately: a service whose environment depends on whether a manifest
section exists is two services wearing one name, and `compose config` would
resolve differently depending on which project produced the file.

**Keep `:?` and forbid the empty list.** This would require every project to
declare a REST service, which is the option that makes `api.rest` optional in
name only.

## Consequences

- One variable in `compose.yaml` is spelled `${VAR?required}`, with the
  measurement recorded beside it. Adding a second requires this ADR's rule to be
  satisfied — the renderer must actually be able to emit it empty.
- `DEP-ISO-002`'s guarantee is unchanged: every resource name is still an
  identifier the renderer never emits empty, and is still `:?`.
- A test that skips in a clean checkout is now a known hazard in this
  repository, not a surprise. It is the reason this defect survived to a live
  deploy, and `test_compose_contract.py`'s module-level skip is worth revisiting
  in Run 10.

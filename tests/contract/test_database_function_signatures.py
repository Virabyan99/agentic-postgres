"""Every call to a released `app_private` function uses a released arity.

**ADR 0175.** Run 4 added `p_expires_at` to `auth_create_agent` with no
`DEFAULT`. The product got the change; four proof call sites did not, and the
result was 21 errors in the Session 15 host gate after thirteen minutes of host
time, in a suite green offline throughout four runs.

Nothing offline could have caught it. Those fixtures only execute against a live
host, and the failure was inside a fixture BODY rather than in its graph, so
`--setup-plan` — the cheap half of the never-executed-proof problem — resolves
them without complaint. The information was in the tree the whole time: the
migrations declare the signature and the call sites use it, and nothing compared
the two.

That is §7's question 5 — *when a decision is implemented, which of its callers
got it?* — and it is the ninth instance. D697 and D687 are the precedent for
answering it as a class rather than per instance.

**What this is honest about.** It counts arguments; it does not resolve a call.
Types, defaults and `OUT` parameters are outside it, and a change to any of them
passes. It is a text scan standing in for a construct (D464), and the mitigation
is that its claim is narrow enough to need one exemption rather than a list:

* **arity only**, because types would need PostgreSQL's overload rules and would
  founder on the `unknown` literals the deployment's own error message named;
* **only functions the migrations declare**, so a test's local `writes_a_row`
  and the bootstrap plane's `project_identity` are outside the claim rather than
  inside an exception list — four would-be exceptions removed at a stroke;
* **product and proofs together**, because a guard watching only the tests would
  cover half the class. The battery mutated both.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, sql_surface

#: `contract` and `p0`, and the p0 is not decoration: this module's one test is a
#: REGISTERED proof of `AGT-AUDIT-002` (P0) and carried no marker at all, so the
#: only thing that ever ran it was the gate's explicit claim-proof run in HOST
#: mode -- present in `evidence/session-25-host-claims.xml`, absent from
#: `session-25-offline-tests.xml`. A session that takes no trip ran it nowhere,
#: and what it compares is two files in a checkout (D1240, D1447).
pytestmark = [pytest.mark.contract, pytest.mark.p0]

#: **Both released schemas, and `api` was missing until Session 16 Run 3**
#: (D889). The guard read `app_private.` alone, and the two functions the
#: agent plane calls on every single request -- `api.agent_audit_begin` and
#: `api.agent_audit_complete` -- are `api.`. Migration 0027 widened both
#: signatures and this guard, built for precisely that, stayed green while
#: four call sites in the suite still passed the old arity. Question 5, in
#: the schema the rule was not applied to.
#:
#: `api` is the only schema exposed over HTTP, so its functions are the ones
#: whose arity a caller can be refused by -- which makes it the schema this
#: mattered most in and the one it did not cover.
SCHEMAS = ("app_private", "api")
_QUALIFIED = f"(?:{'|'.join(SCHEMAS)})"

#: `CREATE FUNCTION <schema>.name(` — the declaration.
CREATE = re.compile(
    rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+{_QUALIFIED}\.(\w+)\s*\(", re.IGNORECASE
)
#: `DROP FUNCTION <schema>.name(` — a signature leaving the released set.
DROP = re.compile(rf"DROP\s+FUNCTION\s+(?:IF\s+EXISTS\s+)?{_QUALIFIED}\.(\w+)\s*\(", re.IGNORECASE)
#: A call. **No whitespace before the paren**, which is what separates
#: `auth_create_agent(` from a prose reference like `app_private.users (id)`.
CALL = re.compile(rf"{_QUALIFIED}\.(\w+)\(")

#: Directories whose Python is held to the released signatures. The product is
#: here as well as the proofs: the defect this guards against was in four
#: proofs, and the identical mistake in `repository.py` would have been a broken
#: endpoint nobody noticed until a host gate either.
SCANNED = ("tests", "bin", "services", "src")

#: The one call that is SUPPOSED to name a signature the migrations retired.
#:
#: `test_the_pre_0016_collectable_set_is_unreachable` calls the three-argument
#: `storage_claim_cleanup_batch` and asserts the call FAILS. Its whole subject is
#: a retired signature, so a guard that refused it would be refusing the proof
#: that the retirement worked. Named as one tuple rather than by filename, so it
#: cannot quietly widen to every call in that module.
DELIBERATE_RETIRED_CALLS = {
    ("tests/contract/test_storage_plane.py", "storage_claim_cleanup_batch", 3),
}


def _arguments(text: str, open_paren: int) -> list[str] | None:
    """The top-level arguments of the call whose ``(`` is at ``open_paren``.

    Depth is counted over ``()`` and ``[]``. Two things are opaque, and both were
    false positives before they were:

    * a ``{...}`` Python interpolation, whose expression may contain commas and
      parens that are not SQL;
    * a **SQL single-quoted string**, because an argon2 hash reads
      ``$argon2id$v=19$m=65536,t=3,p=4$...`` — one argument holding two commas,
      which made a five-argument call count as seven.
    """
    depth = 0
    args: list[str] = []
    current: list[str] = []
    index = open_paren
    in_sql_string = False

    # **An argument list that does not close within this many characters is not
    # a call** (D1450). `_is_a_call`'s three rules all read the argument list,
    # so an occurrence whose paren never closes nearby -- a docstring example
    # ending mid-signature, which this module's own `_is_a_call` docstring
    # contains -- is parsed by running forward through whatever happens to
    # follow it. That makes the verdict depend on UNRELATED TEXT BELOW: adding
    # a function to this file flipped that example from *not a call* to *a call
    # with 14 arguments*, measured. The bound is generous by two orders of
    # magnitude against every real call in the tree (the longest is 84
    # characters) and `checked > 100` below is what says it did not narrow the
    # scan.
    limit = open_paren + 400

    while index < len(text) and index < limit:
        char = text[index]

        if in_sql_string:
            if char == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    index += 2  # an escaped quote, not the end
                    continue
                in_sql_string = False
            index += 1
            continue

        if char == "'":
            in_sql_string = True
            current.append("<sql-string>")
            index += 1
            continue

        if char == "{":
            brace = 1
            index += 1
            while index < len(text) and brace:
                if text[index] == "{":
                    brace += 1
                elif text[index] == "}":
                    brace -= 1
                index += 1
            current.append("<expr>")
            continue

        if char in "([":
            depth += 1
            if depth > 1:
                current.append(char)
        elif char in ")]":
            depth -= 1
            if depth == 0:
                args.append("".join(current).strip())
                return [argument for argument in args if argument]
            current.append(char)
        elif char == "," and depth == 1:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1

    return None


def _callable_arities(parameters: list[str]) -> set[int]:
    """Every argument count this declaration can be called with.

    **A parameter with a `DEFAULT` may be omitted**, and PostgreSQL requires the
    defaulted ones to come last — so a declaration of *n* parameters of which *d*
    carry a default is callable with anything from ``n - d`` through ``n``.

    This was outside the guard while it read `app_private` alone, and the module
    docstring said so. Widening to `api` made it load-bearing at once:
    ``api.create_note(p_title text, p_content text DEFAULT '')`` is called with
    one argument in five places, every one of them correct, and a guard counting
    only the full arity called all five defects (D889). **A guard that cries wolf
    about correct code gets widened back**, which is how this one would have
    died a session after it was built.
    """
    total = len(parameters)
    defaulted = sum(1 for parameter in parameters if re.search(r"\bDEFAULT\b", parameter, re.I))
    return set(range(total - defaulted, total + 1))


def released_signatures() -> dict[str, set[int]]:
    """Every released function the migrations leave live, by callable arity.

    Migrations are read in filename order and `DROP` is applied before `CREATE`
    **at the position each appears**, because 0025 drops and recreates four
    functions in one file — reading all the creates first would leave the old
    arities live alongside the new ones and the guard would accept both.

    A `DROP` names a signature **by its types**, so it retires that
    declaration's whole callable range and not merely the count it spells: a
    `DROP FUNCTION f(text, uuid, jsonb)` retires the `f(a)` and `f(a, b)` forms
    that the same declaration's `DEFAULT`s made legal. Declarations are
    therefore held per full arity and dropped by that key, which is why this
    does not simply subtract sets — subtracting left `agent_audit_begin`
    declaring `[1, 2, 5]`, an old signature's defaulted forms outliving the
    signature itself.
    """
    live: dict[str, dict[int, set[int]]] = {}
    for path in sorted((REPO_ROOT / "migrations" / "templates").glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        events = [(match.start(), "drop", match) for match in DROP.finditer(text)]
        events += [(match.start(), "create", match) for match in CREATE.finditer(text)]
        for _, kind, match in sorted(events, key=lambda event: event[0]):
            arguments = _arguments(text, match.end() - 1)
            if arguments is None:
                continue
            declarations = live.setdefault(match.group(1), {})
            if kind == "drop":
                declarations.pop(len(arguments), None)
            else:
                declarations[len(arguments)] = _callable_arities(arguments)

    return {
        name: {arity for arities in declarations.values() for arity in arities}
        for name, declarations in live.items()
        if declarations
    }


#: An argument that is a bare identifier or SQL type name and nothing else.
_BARE = re.compile(r"^[A-Za-z_][A-Za-z0-9_ \[\]]*$")


def _is_a_call(text: str, match: re.Match[str], arguments: list[str]) -> bool:
    """Whether this occurrence is a CALL rather than a signature or prose.

    Widening the scan to `api` brought in three things that are not calls and
    that `app_private` never contained (D890):

    * a **type signature** — ``"api.agent_audit_begin(text, uuid, jsonb)"``,
      passed to `has_function_privilege`;
    * **prose** in a docstring naming parameters —
      ``api.agent_audit_begin(p_tool, p_request_id, p_parameters)``;
    * a **prefix string** used for scanning — ``"CREATE FUNCTION
      api.agent_audit_begin("`` — whose closing paren is somewhere unrelated.

    The first two are exactly the arguments that are **all bare identifiers**,
    and the third is the one whose ``(`` is immediately followed by the quote
    that opened the Python literal it sits in.

    **Both rules were measured before being written, against all 157 real calls
    in the tree**: none of them has an all-bare argument list, and none has its
    string's own delimiter as the first character after the paren. The
    zero-argument calls — 25 of them, `postgrest_pre_request()` among them — are
    unaffected, which is why the bare rule requires a non-empty list.
    """
    if arguments and all(_BARE.match(argument.strip()) for argument in arguments):
        return False

    line_start = text.rfind("\n", 0, match.start()) + 1
    quotes = [char for char in text[line_start : match.start()] if char in "\"'"]
    after = text[match.end() : match.end() + 1]
    return not (quotes and after == quotes[-1])


#: The bodies that are SUPPOSED to name a parameter no declaration has.
#:
#: `DELIBERATE_RETIRED_CALLS`' shape one blind spot over, and for its reason: a
#: guard that refused these would be refusing the proofs that the surface
#: refuses them. Both were found by this guard's first execution (D1449).
#:
#: * `owner_id` -- posted to prove a caller-supplied owner is IGNORED and the
#:   row lands under the request identity. The whole subject is a key the
#:   function does not declare.
#: * `nope` -- posted to prove an unknown RPC argument is refused without the
#:   refusal disclosing a role, a token or the database name.
#:
#: Named per (file, function, key) rather than per file, so it cannot quietly
#: widen to every body in that module.
DELIBERATE_UNDECLARED_KEYS = {
    ("tests/deployment/test_session5_rest_surface.py", "create_note", "owner_id"),
    ("tests/deployment/test_session5_rest_surface.py", "create_note", "nope"),
}

#: Keys a request body carries that are NOT the function's parameters.
#:
#: A proof posts the whole envelope in one dict in places -- a JSON-RPC frame
#: around an MCP call, for instance -- and those keys belong to the transport.
#: Enumerated rather than pattern-matched, so a key added here is a decision
#: somebody made rather than a prefix that quietly swallowed a typo.
_NOT_A_PARAMETER = frozenset({"jsonrpc", "id", "method", "params", "name", "arguments"})


#: A released signature named somewhere that is NOT a `CREATE` or a `DROP`.
#:
#: **ADR 0175's first blind spot, and it has 153 live instances** (D942, D1448).
#: `GRANT EXECUTE ON FUNCTION api.create_task(text, uuid)`,
#: `REVOKE ALL ON FUNCTION ...`, `COMMENT ON FUNCTION ...` and
#: `ALTER FUNCTION ...` each name a signature by its ARGUMENT TYPES. When a
#: released function's signature moves, every one of these is a place that can
#: be left naming the old one -- and the guard above never saw them, because
#: `SCANNED` is Python and these are SQL.
#:
#: Matched within one statement over comment-stripped SQL, so a sentence in a
#: `--` block that happens to contain both words cannot pair them -- **and the
#: gap may not contain a `CREATE`**, which is not a refinement but the thing
#: that makes the pattern correct. Measured on its first execution: without it,
#: a `GRANT` several statements above paired with the next
#: `CREATE FUNCTION app_private.storage_create_upload_intent(` in `0014` and the
#: guard reported a declaration as a stale reference to itself (D1448).
SQL_SIGNATURE = re.compile(
    rf"\b(?:GRANT|REVOKE|COMMENT\s+ON|ALTER)\b(?:(?!\bCREATE\b)[^;])*?\bFUNCTION\s+"
    rf"(?:IF\s+EXISTS\s+)?{_QUALIFIED}\.(\w+)\s*\(",
    re.IGNORECASE | re.DOTALL,
)

#: An HTTP body posted to an RPC, in the two spellings this repository uses.
#:
#: **ADR 0175's second blind spot.** PostgREST takes an RPC's arguments as JSON
#: keys, so `{"p_title": "x"}` posted to `/rpc/create_note` names the
#: declaration's parameters as surely as a SQL call does -- and by NAME rather
#: than by position, which is the half a count can never catch.
#: **No leading quote.** The first draft required one and read ZERO bodies: the
#: deployment proofs build the URL as `f"{base}/rpc/create_note"`, so the
#: character before the path is a brace. A guard that measures nothing passes
#: (D1449).
RPC_PATH = re.compile(r"/rpc/(\w+)")


def released_parameter_names() -> dict[str, set[str]]:
    """Every released function's declared parameter names, by the same walk.

    The same ordering rule `released_signatures` states and for the same reason:
    a `DROP` retires the declaration it names before a later `CREATE` in the
    same file replaces it. Names rather than counts, because an HTTP body names
    parameters and a positional count cannot see a renamed one.
    """
    live: dict[str, dict[int, set[str]]] = {}
    for path in sorted((REPO_ROOT / "migrations" / "templates").glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        events = [(match.start(), "drop", match) for match in DROP.finditer(text)]
        events += [(match.start(), "create", match) for match in CREATE.finditer(text)]
        for _, kind, match in sorted(events, key=lambda event: event[0]):
            arguments = _arguments(text, match.end() - 1)
            if arguments is None:
                continue
            declarations = live.setdefault(match.group(1), {})
            if kind == "drop":
                declarations.pop(len(arguments), None)
                continue
            names = set()
            for argument in arguments:
                parts = argument.strip().split()
                # `p_title text DEFAULT ''` -- the name is the first token, and
                # a declaration with no name at all (`text`) contributes none.
                if len(parts) >= 2 and re.fullmatch(r"[a-z_][a-z0-9_]*", parts[0], re.I):
                    names.add(parts[0])
            declarations[len(arguments)] = names

    return {
        name: {parameter for names in declarations.values() for parameter in names}
        for name, declarations in live.items()
        if declarations
    }


def _stale_sql_signatures(templates: list[Path]) -> tuple[list[str], int]:
    """Walk templates in order; return what is stale and how much was compared.

    Extracted from the proof so it can be pointed at a SYNTHETIC set that is
    stale (D1454). Inside the proof it was unreachable by any input, which made
    the proof's own assertion vacuous on a healthy tree -- and Run 5's battery
    measured exactly that: a mutation removing the comparison survived.
    """
    live: dict[str, dict[int, set[int]]] = {}
    checked = 0
    stale: list[str] = []

    for path in templates:
        text = sql_surface.sql_only(path.read_text(encoding="utf-8"))
        events = [(match.start(), "drop", match) for match in DROP.finditer(text)]
        events += [(match.start(), "create", match) for match in CREATE.finditer(text)]
        events += [(match.start(), "named", match) for match in SQL_SIGNATURE.finditer(text)]

        for _, kind, match in sorted(events, key=lambda event: event[0]):
            arguments = _arguments(text, match.end() - 1)
            if arguments is None:
                continue
            name = match.group(1)
            declarations = live.setdefault(name, {})

            if kind == "drop":
                declarations.pop(len(arguments), None)
            elif kind == "create":
                declarations[len(arguments)] = _callable_arities(arguments)
            else:
                checked += 1
                if len(arguments) not in declarations:
                    stale.append(
                        f"{path.name}: {name}({', '.join(arguments)}) spells "
                        f"{len(arguments)} argument(s); the declarations live at that "
                        f"point are {sorted(declarations) or 'none'}"
                    )

    return stale, checked


def test_every_sql_signature_names_a_declaration_that_is_live_at_that_point() -> None:
    """ADR 0175's first blind spot, widened against the DEFINITION (D942, D1448).

    The rule the guard above enforces is *nothing may name a released
    function's signature except the released one*. It enforced that for Python
    call sites only, and a `GRANT EXECUTE ON FUNCTION api.f(text, uuid)` names a
    signature exactly as surely -- by argument types, which is stricter than a
    count.

    **Checked against the declaration in force AT THAT MIGRATION, not against
    the newest.** A grant in `0007` names the function as `0007` found it, and
    `0032` changing that function later does not make `0007` wrong: `0007` ran,
    and D912 freezes it. So this walks the templates in version order, applying
    `DROP` and `CREATE` at the position each appears, and asks of each
    reference whether the arity it spells was live *then*. That is D940's rule
    for a proof rather than for a migration -- a thing with history is checked
    against its history.

    Measured when it was written: **140 such references across 34 templates**,
    and every one of them names a live declaration. A guard that found nothing
    on the day it was built would be a guard nobody could tell from a broken
    one, so the count is asserted too.

    The first draft counted 153 and thirteen of those were the pattern pairing a
    `GRANT` with a later `CREATE` across intervening statements. The count moved
    because the pattern was repaired, and it is written down here with that
    reason so the next reader does not "restore" it (D1448).
    """
    stale, checked = _stale_sql_signatures(
        sorted((REPO_ROOT / "migrations" / "templates").glob("*.sql"))
    )

    assert not stale, "a SQL statement names a signature no declaration had:\n" + "\n".join(stale)
    assert checked >= 135, (
        f"only {checked} SQL signatures were checked. This was 140 when the guard was "
        "written; a collapse to zero is what a broken pattern looks like, and it would "
        "pass the assertion above (D173, D260)"
    )


def test_the_sql_signature_walk_detects_a_stale_reference(tmp_path: Path) -> None:
    """The POSITIVE control, and the battery is why it exists (D1454).

    The proof above is vacuous on a healthy tree: nothing is stale, so `stale`
    is empty whether the comparison runs or not. Run 5's own battery proved it
    -- a mutation that made the walk stop comparing **survived**, green, with
    `checked` still counting. `checked >= 135` says the guard LOOKED; only this
    says it COMPARED.

    Three templates, in version order, so the walk is exercised exactly as it is
    over the release: a declaration, a grant that matches it, and a grant that
    does not. The matching one must NOT be reported -- without that arm a walk
    that reported everything would pass this too.
    """
    (tmp_path / "0001-create.sql").write_text(
        "CREATE FUNCTION api.widget(p_a text, p_b uuid) RETURNS void AS $$ $$ LANGUAGE sql;\n",
        encoding="utf-8",
    )
    (tmp_path / "0002-right.sql").write_text(
        "GRANT EXECUTE ON FUNCTION api.widget(text, uuid) TO nobody;\n",
        encoding="utf-8",
    )
    stale, checked = _stale_sql_signatures(sorted(tmp_path.glob("*.sql")))
    assert checked == 1, checked
    assert stale == [], f"a grant matching its declaration was reported stale: {stale}"

    (tmp_path / "0003-wrong.sql").write_text(
        "REVOKE ALL ON FUNCTION api.widget(text, uuid, jsonb) FROM nobody;\n",
        encoding="utf-8",
    )
    stale, checked = _stale_sql_signatures(sorted(tmp_path.glob("*.sql")))
    assert checked == 2, checked
    assert len(stale) == 1, stale
    assert "0003-wrong.sql" in stale[0] and "3 argument(s)" in stale[0], stale

    # And a reference BEFORE the declaration it names is stale too, which is the
    # ordering half: a grant in an earlier migration cannot name a function a
    # later one creates.
    early = tmp_path / "0000-early.sql"
    early.write_text(
        "GRANT EXECUTE ON FUNCTION api.widget(text, uuid) TO nobody;\n", encoding="utf-8"
    )
    stale, _ = _stale_sql_signatures(sorted(tmp_path.glob("*.sql")))
    assert any("0000-early.sql" in item for item in stale), stale


def test_an_rpc_body_names_only_parameters_the_declaration_has() -> None:
    """ADR 0175's second blind spot, and the half a count cannot see (D942, D1449).

    PostgREST takes an RPC's arguments as JSON keys, so a body posted to
    `/rpc/create_note` names the declaration's parameters **by name**. A
    renamed parameter leaves every such body naming one that no longer exists,
    and the arity guard above sees nothing at all: there is no
    `schema.function(` anywhere in the request.

    **The stated limit, because this is a text scan and not an interpreter**
    (D464's rule applied to a second scan): a body is read only when a literal
    `{...}` follows a `body=` or `json=` within 600 characters of the path, and
    only its top-level string keys are read. A body built from a variable, a
    loop or a helper is invisible here, and this docstring is where that is
    written down rather than discovered. The direction is the safe one -- an
    unread body is not asserted against, so this under-reports rather than
    inventing a failure.

    **`body=` is required and that requirement was measured** (D1449). Taking
    the next literal dict instead matched the OpenAPI *schema* documents that
    `test_client_ir.py` and `test_openapi_normalize.py` build beside a
    `/rpc/create_note` path -- `properties`, `required`, `type`, `in` -- and
    reported four failures against a guard that had found nothing real. A scan
    whose first execution produces only false positives gets deleted, which is
    how a guard dies a session after it is built.

    Functions the migrations do not declare are skipped on purpose: the suite
    posts to `/rpc/rpc_probe`, `/rpc/e_28000` and a dozen other names that exist
    only inside a fixture's own cluster, and a guard that demanded a released
    declaration for those would be refusing the proofs that probe an
    unreleased surface.
    """
    declared = released_parameter_names()
    assert declared, "no released parameter names were read at all"

    key = re.compile(r"[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*:")
    wrong: list[str] = []
    bodies = 0

    for directory in ("tests", "bin", "services", "src"):
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for match in RPC_PATH.finditer(text):
                name = match.group(1)
                if name not in declared:
                    continue
                window = text[match.end() : match.end() + 600]
                assigned = max(window.find("body="), window.find("json="))
                if assigned == -1:
                    continue
                start = window.find("{", assigned)
                if start == -1:
                    continue
                depth = 0
                end = -1
                for index in range(start, len(window)):
                    if window[index] == "{":
                        depth += 1
                    elif window[index] == "}":
                        depth -= 1
                        if depth == 0:
                            end = index
                            break
                if end == -1:
                    continue
                body = window[start : end + 1]
                keys = {found.group(1) for found in key.finditer(body)}
                if not keys:
                    continue
                bodies += 1
                relative = str(path.relative_to(REPO_ROOT))
                unknown = sorted(
                    key
                    for key in keys - declared[name] - _NOT_A_PARAMETER
                    if (relative, name, key) not in DELIBERATE_UNDECLARED_KEYS
                )
                if unknown:
                    wrong.append(
                        f"{path.relative_to(REPO_ROOT)}: a body posted to /rpc/{name} names "
                        f"{unknown}, which {name} does not declare "
                        f"(it declares {sorted(declared[name])})"
                    )

    assert not wrong, "an RPC body names a parameter no declaration has:\n" + "\n".join(wrong)
    assert bodies >= 1, (
        "no literal RPC body was read at all, so this guard is measuring nothing. "
        "Either the scan broke or the suite stopped posting literal bodies; both are "
        "worth knowing and neither is caught by the assertion above"
    )


def test_every_call_to_a_released_function_uses_a_released_arity() -> None:
    """ADR 0175. The guard whose absence cost a host trip.

    Two mutations established that it fires — the fixture call reverted to six
    arguments, and the product's `%s` list cut to six — each detected, with a
    control it cannot reach (renaming a local variable) staying green.
    """
    live = released_signatures()
    assert len(live) > 30, (
        f"only {len(live)} released function(s) were parsed out of the migrations. "
        "The declaration scan has broken, and every assertion below would pass by "
        "selecting almost nothing"
    )

    # **Both schemas, named**, because narrowing `SCHEMAS` back to `app_private`
    # would leave this test green (every call is correct today) while silently
    # dropping the two functions the agent plane calls on every request. That is
    # how the hole D887 found was invisible for a whole session, and a guard
    # whose coverage can shrink without a failure is a guard that will.
    for schema, witness in (("app_private", "auth_create_agent"), ("api", "agent_audit_begin")):
        assert witness in live, (
            f"{witness} is not in the released set, so schema {schema!r} is no longer "
            "being read. This test would still pass, and would be checking half the "
            "surface it claims to (D887)"
        )

    wrong: list[str] = []
    checked = 0

    for area in SCANNED:
        for path in sorted((REPO_ROOT / area).rglob("*.py")):
            relative = path.relative_to(REPO_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for match in CALL.finditer(text):
                name = match.group(1)
                if name not in live:
                    continue  # not a released function; outside this claim
                arguments = _arguments(text, match.end() - 1)
                if arguments is None:
                    continue
                if not _is_a_call(text, match, arguments):
                    continue  # a signature, prose, or a prefix string (D890)
                checked += 1
                arity = len(arguments)
                if arity in live[name]:
                    continue
                if (relative, name, arity) in DELIBERATE_RETIRED_CALLS:
                    continue
                line = text[: match.start()].count("\n") + 1
                # The schema comes from the match, not from a literal: the guard
                # reads two schemas now, and naming every finding `app_private`
                # would send a reader to the wrong file (D889).
                schema = match.group(0).split(".", 1)[0]
                wrong.append(
                    f"{relative}:{line} calls {schema}.{name} with {arity} "
                    f"argument(s); the migrations declare {sorted(live[name])}"
                )

    # The control, and it is not decoration. Narrowing the claim to released
    # functions is what removed the exception list, and the same narrowing could
    # select nothing at all if the declaration scan drifted -- leaving this test
    # green having compared no calls (D509).
    assert checked > 100, (
        f"only {checked} call(s) to released functions were examined, so the "
        "assertion below is close to vacuous. The call scan has broken"
    )

    assert not wrong, (
        "a call does not match the signature its migrations released. The product "
        "and its proofs are both scanned, so read which one this is:\n  " + "\n  ".join(wrong)
    )

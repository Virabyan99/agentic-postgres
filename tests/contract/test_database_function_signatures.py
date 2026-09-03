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

from agentic_postgres import REPO_ROOT

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

    while index < len(text):
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

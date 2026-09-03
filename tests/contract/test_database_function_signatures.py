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

#: `CREATE FUNCTION app_private.name(` — the declaration.
CREATE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+app_private\.(\w+)\s*\(", re.IGNORECASE
)
#: `DROP FUNCTION app_private.name(` — a signature leaving the released set.
DROP = re.compile(r"DROP\s+FUNCTION\s+(?:IF\s+EXISTS\s+)?app_private\.(\w+)\s*\(", re.IGNORECASE)
#: A call. **No whitespace before the paren**, which is what separates
#: `auth_create_agent(` from a prose reference like `app_private.users (id)`.
CALL = re.compile(r"app_private\.(\w+)\(")

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


def released_signatures() -> dict[str, set[int]]:
    """Every `app_private` function the migrations leave live, by arity.

    Migrations are read in filename order and `DROP` is applied before `CREATE`
    **at the position each appears**, because 0025 drops and recreates four
    functions in one file — reading all the creates first would leave the old
    arities live alongside the new ones and the guard would accept both.
    """
    live: dict[str, set[int]] = {}
    for path in sorted((REPO_ROOT / "migrations" / "templates").glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        events = [(match.start(), "drop", match) for match in DROP.finditer(text)]
        events += [(match.start(), "create", match) for match in CREATE.finditer(text)]
        for _, kind, match in sorted(events, key=lambda event: event[0]):
            arguments = _arguments(text, match.end() - 1)
            if arguments is None:
                continue
            bucket = live.setdefault(match.group(1), set())
            if kind == "drop":
                bucket.discard(len(arguments))
            else:
                bucket.add(len(arguments))
    return {name: arities for name, arities in live.items() if arities}


def test_every_call_to_a_released_function_uses_a_released_arity() -> None:
    """ADR 0175. The guard whose absence cost a host trip.

    Two mutations established that it fires — the fixture call reverted to six
    arguments, and the product's `%s` list cut to six — each detected, with a
    control it cannot reach (renaming a local variable) staying green.
    """
    live = released_signatures()
    assert len(live) > 30, (
        f"only {len(live)} released app_private function(s) were parsed out of the "
        "migrations. The declaration scan has broken, and every assertion below "
        "would pass by selecting almost nothing"
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
                checked += 1
                arity = len(arguments)
                if arity in live[name]:
                    continue
                if (relative, name, arity) in DELIBERATE_RETIRED_CALLS:
                    continue
                line = text[: match.start()].count("\n") + 1
                wrong.append(
                    f"{relative}:{line} calls app_private.{name} with {arity} "
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

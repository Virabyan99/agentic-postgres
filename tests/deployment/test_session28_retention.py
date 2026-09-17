"""`AGT-RETAIN-001`'s live half — the agent record, on the deployment (ADR 0213).

**Why a live half at all, when the offline one is twenty-three proofs.** Rig
28b built a cluster with history and measured every refusal, both prunes, the
re-arming of an idempotency key and the size reading; that cluster's history
was written by the proof that then read it. A deployment's was written by the
deployed plane, over nine sessions, by callers this suite never ran — which is
the difference D940 names: *a migration over a table with history must be
proved against a cluster with history*, and the history that matters is the one
nobody arranged.

**Nothing here deletes a row of the agent record, and that is a decision rather
than caution.** The record is evidence (ADR 0135, ADR 0142), and §8 of this
session's plan says a migration that removes it silently is a migration that
destroys evidence. So the one proof that runs a prune against the real record
runs it inside a transaction it rolls back, and the row count before and after
is the control — ADR 0182's shape exactly, a write performed and undone in
order to report what it would have done. The count it returns is the
measurement; the count that survives is the proof that the measurement cost
nothing.

**Both projects.** Alpha declares nothing of its own and beta carries a
migration set and a capability manifest; they have come apart before (D1288),
and a retention claim measured on one would say the release's functions are
present when one project's ledger had not reached them.

**A grant question and a reach question are different questions** (ADR 0134),
so the two prunes are read from the catalog AND attempted by `SET ROLE` as each
request role. A function granted to nobody is still reachable by a role that
owns it or inherits the owner, and a catalog read alone would not notice.

**The doctor's eleventh check is read here rather than asserted offline**
(D1462). Offline it is proved to have no threshold; here it is proved to
produce this deployment's own numbers, which is the half a checkout cannot
answer — and the probe reads the two TABLES rather than 0033's functions, so it
answers the same way before and after the migration lands.

**Gated on three declarations**, all in `tests/conftest.py`'s roster; nothing
here reads a credential, and every reading is made over the container socket
the way every other deployment probe reaches the cluster.

**Marked, and the marks are load-bearing** (D1240).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

# ruff: noqa: S608 -- every literal here is this module's own constant, run by
# an operator's psql over the container socket. The same waiver every
# deployment module carries, for the same reason.
pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

#: The three functions migration 0033 creates, with the argument lists that
#: identify them. Written out rather than globbed over `app_private`: a glob
#: would pass on a deployment carrying two of the three.
#:
#: **The spellings are rig 28k's and not this author's** (D1479). The draft
#: read `pg_get_function_arguments` and expected `timestamp with time zone,
#: integer`. Measured against the pinned cluster image, that function returns
#: `p_before timestamp with time zone, p_limit integer DEFAULT NULL::integer`
#: -- the parameter NAMES and the rendered default -- so the proof would have
#: gone red on its first execution, on the host, in the window, for a reason
#: about PostgreSQL's spelling rather than about the deployment.
#: `pg_get_function_identity_arguments` drops the default and KEEPS the names,
#: and a zero-argument function answers it with the empty string, which is why
#: presence is asked separately below rather than read off this value.
RETENTION_FUNCTIONS: tuple[tuple[str, str], ...] = (
    ("agent_audit_prune", "p_before timestamp with time zone, p_limit integer"),
    ("agent_idempotency_prune", "p_before timestamp with time zone, p_limit integer"),
    ("agent_record_size", ""),
)

#: The request roles a prune must not reach. `auth_service` is the interesting
#: one: it already reads whole audit rows through `auth_list_agent_audit`, so it
#: is the identity somebody would reach for when adding the grant later.
REQUEST_ROLES: tuple[str, ...] = (
    "auth_service",
    "agent_writer",
    "agent_reader",
    "authenticated",
)

#: How far back the rolled-back prune reaches. Seven days rather than the
#: horizon an operator would choose, because the measurement wanted here is
#: *the function removes rows that exist on this deployment*, and a horizon
#: that matched nothing would report zero and prove only that the call
#: succeeded (D600's shape: a zero that looks measured).
ROLLBACK_HORIZON = "now() - interval '7 days'"

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


def _projects(project_a: dict[str, Any], project_b: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    return (project_a, project_b)


def _key(document: dict[str, Any]) -> str:
    return str(document["project"]["key"])


def _one(psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], sql: str) -> str:
    code, out, error = psql(document, sql)
    assert code == 0, f"{_key(document)}: {sql}\n{error}"
    return out.strip()


def test_both_projects_carry_the_three_retention_functions(
    project_a: dict[str, Any], project_b: dict[str, Any], psql: Callable[..., tuple[int, str, str]]
) -> None:
    """The release's own ledger says 0033 is applied; this says the cluster has it.

    **Read the ledger, never the migrator's line** (D941) is the rule for
    whether a migration ran. This is the question after that one: whether the
    objects the migration creates are in the catalog of the database the plane
    talks to. They come apart when a migration is applied to one project and
    not the other, which is what Session 24's trip looked like from the outside
    (D1288).
    """
    for document in _projects(project_a, project_b):
        for name, arguments in RETENTION_FUNCTIONS:
            #: Presence and shape are two readings, because a zero-argument
            #: function's identity argument list IS the empty string (rig 28k)
            #: -- so an absent function and `agent_record_size` are
            #: indistinguishable in the second reading alone.
            present = _one(
                psql,
                document,
                "SELECT count(*) FROM pg_proc p "
                "WHERE p.pronamespace = 'app_private'::regnamespace "
                f"  AND p.proname = '{name}';",
            )
            assert present == "1", (
                f"{_key(document)} has {present} app_private.{name}. Migration 0033 is in "
                "this release's set; a deployment running this release without it is a "
                "deployment whose ledger and whose catalog disagree"
            )
            found = _one(
                psql,
                document,
                "SELECT pg_get_function_identity_arguments(p.oid) FROM pg_proc p "
                "WHERE p.pronamespace = 'app_private'::regnamespace "
                f"  AND p.proname = '{name}';",
            )
            assert found == arguments, (
                f"{_key(document)}: app_private.{name} takes ({found}) and this release "
                f"creates it taking ({arguments})"
            )


def test_neither_prune_is_reachable_by_any_request_role_on_the_deployment(
    project_a: dict[str, Any], project_b: dict[str, Any], psql: Callable[..., tuple[int, str, str]]
) -> None:
    """ADR 0213's decision, on the cluster an agent actually reaches.

    The catalog half subtracts the owner for `aclexplode`'s reason — an owner's
    implicit entry is not a grant somebody made — and the reach half is the one
    that matters: a delete authority over the agent record behind a reachable
    identity is 0020's refusal with one more function in front of it.

    **The reach attempt is made against the real cluster and is expected to
    fail**, so it removes nothing even if the refusal were missing: a
    `permission denied` is raised before the function body runs, and the
    control for "this arm can fail at all" is the offline half's accepted call,
    which runs against a cluster this suite may destroy.
    """
    for document in _projects(project_a, project_b):
        roles = document["roles"]
        for name in ("agent_audit_prune", "agent_idempotency_prune"):
            grantees = _one(
                psql,
                document,
                "SELECT coalesce(string_agg(DISTINCT a.grantee::regrole::text, ','), '') "
                "FROM pg_proc p, aclexplode(p.proacl) a "
                "WHERE p.pronamespace = 'app_private'::regnamespace "
                f"  AND p.proname = '{name}' AND a.grantee <> p.proowner;",
            )
            assert grantees == "", (
                f"{_key(document)}: app_private.{name} is granted to {grantees}. "
                "ADR 0213 grants it to nobody"
            )

            for role_key in REQUEST_ROLES:
                code, _, error = psql(
                    document,
                    f"SELECT app_private.{name}(now() - interval '100 years', 1);",
                    role=roles[role_key],
                )
                assert code != 0, f"{_key(document)}: {role_key} reached app_private.{name}"
                assert "permission denied" in (error or ""), (
                    f"{_key(document)}: {role_key} was refused for the wrong reason: {error}"
                )

        served = _one(
            psql,
            document,
            "SELECT count(*) FROM app_private.agent_record_size();",
        )
        assert served == "1", f"{_key(document)}: agent_record_size returned {served} rows"


def test_the_record_reading_answers_on_a_cluster_with_history(
    project_a: dict[str, Any], project_b: dict[str, Any], psql: Callable[..., tuple[int, str, str]]
) -> None:
    """The four numbers, off the deployment, and the assertion that there is a
    record to count.

    **`audit_rows > 0` on at least one project is the load-bearing half.** A
    size reading that returned four zeros would satisfy every structural
    assertion here and would mean this claim had been proved against an empty
    table — D940's shape, one level up from the migration. This deployment's
    agent plane has been called by every trip since Session 16, so the record
    exists; if it does not, the honest reading is that something removed it,
    and that is exactly what this claim is about.

    The dates are read as facts and not compared to a threshold: ADR 0213 puts
    no threshold anywhere, and inventing one in a proof would be inventing one
    in the place hardest to argue with.
    """
    readings: dict[str, tuple[int, str, int, str]] = {}
    for document in _projects(project_a, project_b):
        row = _one(
            psql,
            document,
            "SELECT audit_rows::text || '|' || coalesce(audit_oldest::text, '') || '|' || "
            "idempotency_rows::text || '|' || coalesce(idempotency_oldest::text, '') "
            "FROM app_private.agent_record_size();",
        )
        fields = row.split("|")
        assert len(fields) == 4, f"{_key(document)}: agent_record_size returned {row!r}"
        readings[_key(document)] = (
            int(fields[0]),
            fields[1],
            int(fields[2]),
            fields[3],
        )

    assert any(rows > 0 for rows, _, _, _ in readings.values()), (
        f"no project carries an agent audit row: {readings}. Either the agent plane has "
        "never been called on this deployment -- which nine sessions of trips say is "
        "false -- or something removed the record. A retention claim proved against an "
        "empty table is D940"
    )

    for key, (audit_rows, audit_oldest, idempotency_rows, idempotency_oldest) in readings.items():
        assert audit_rows >= 0 and idempotency_rows >= 0, key
        for label, rows, oldest in (
            ("audit", audit_rows, audit_oldest),
            ("idempotency", idempotency_rows, idempotency_oldest),
        ):
            if rows:
                assert _TIMESTAMP.match(oldest), (
                    f"{key}: {rows} {label} rows and the oldest is {oldest!r}. A non-empty "
                    "table whose minimum timestamp is absent is a reading that did not "
                    "arrive in the shape it was asked for"
                )
            else:
                assert oldest == "", f"{key}: no {label} rows and an oldest of {oldest!r}"


def test_a_prune_against_the_real_record_is_measured_inside_a_transaction_that_is_rolled_back(
    project_a: dict[str, Any], project_b: dict[str, Any], psql: Callable[..., tuple[int, str, str]]
) -> None:
    """The prune, on the record the deployed plane wrote, removing nothing.

    **A dry run is a rolled-back write** (ADR 0182), and this is that pattern
    applied to the one function in this release whose whole job is destructive.
    The transaction reports what the prune removed and is then undone; the
    count read afterwards, outside it, is the control. Without the control arm
    a prune that removed nothing would pass — and a prune that removed
    everything and a proof that never checked would be the worst outcome this
    module could have.

    **The bounded form is used** so that the blast radius of a rollback that
    somehow did not happen is one row rather than the whole record. It is also
    the form an operator would run: rig 28b measured that bounded is not the
    faster one (D1461), so the reason to prefer it is this one.

    A project whose record holds nothing older than the horizon is reported as
    such rather than passed over, because *there was nothing to prune* and
    *the prune did not run* are the two readings ADR 0195 exists to keep apart.
    """
    exercised = 0
    for document in _projects(project_a, project_b):
        key = _key(document)
        before = int(_one(psql, document, "SELECT count(*) FROM app_private.agent_audit;"))
        candidates = int(
            _one(
                psql,
                document,
                "SELECT count(*) FROM app_private.agent_audit "
                f"WHERE started_at < {ROLLBACK_HORIZON};",
            )
        )
        if not candidates:
            continue

        removed = int(
            _one(
                psql,
                document,
                f"BEGIN; SELECT app_private.agent_audit_prune({ROLLBACK_HORIZON}, 1); ROLLBACK;",
            )
        )
        assert removed == 1, (
            f"{key}: a bounded prune over {candidates} eligible rows removed {removed}"
        )

        after = int(_one(psql, document, "SELECT count(*) FROM app_private.agent_audit;"))
        assert after == before, (
            f"{key}: the agent record held {before} rows and holds {after} after a prune "
            "this proof rolled back. A row of the agent record has been destroyed by a "
            "test, which is the one outcome ADR 0135 and ADR 0142 make unacceptable"
        )
        exercised += 1

    assert exercised, (
        "neither project holds an agent audit row older than seven days, so the prune was "
        "never run against real history. That is a reading rather than a pass: say so and "
        "widen the horizon rather than recording this claim as proved"
    )


def test_the_doctors_agent_record_check_reports_this_deployments_numbers(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    as_root: None,
    sh_status: Callable[..., tuple[int, str, str]],
) -> None:
    """D1462's check, against the deployment it was written for.

    Offline this check is proved to have no threshold and to report the third
    outcome when the cluster does not answer. What only a deployment can say is
    whether it produces THIS deployment's numbers — and the number it must
    agree with is the one `agent_record_size()` returns, because the probe
    reads the two tables directly and the function reads them too. Two readers
    of one pair of tables that disagree is the drift the check would otherwise
    hide.

    The verdict must be `ok` or `unknown` and never a warning, because ADR 0213
    puts no threshold anywhere: a doctor that graded the record would be
    grading it against a number nobody measured (D1441).
    """
    del as_root
    for document in _projects(project_a, project_b):
        key = _key(document)
        code, out, error = sh_status(
            str(REPO_ROOT / "bin" / "doctor.py"), "--project", key, "--json"
        )
        assert code in (0, 6), f"doctor --json for {key} exited {code}\n{error}"
        checks = {check["name"]: check for check in json.loads(out)["checks"]}
        assert "agent record" in checks, (
            f"{key}: the doctor reports no `agent record` check. It is the eleventh "
            "(D1459, D1462) and a deployment that does not get it is reading an older "
            "checkout"
        )
        check = checks["agent record"]
        assert check["verdict"] in ("ok", "unknown"), (
            f"{key}: the agent record check reported {check['verdict']}. ADR 0213 puts no "
            "threshold anywhere, so there is no reading of these two counts that is a "
            "problem this command can name"
        )
        assert "nothing prunes either unless an operator asks" in check["detail"], (
            f"{key}: the detail line is {check['detail']!r}"
        )


def test_the_doctors_numbers_are_the_clusters_numbers(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    as_root: None,
    sh_status: Callable[..., tuple[int, str, str]],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """Two readers, one pair of tables, and they have to agree.

    The doctor's probe runs its own SQL over the container socket; the function
    0033 creates reads the same two tables from inside the database. A
    difference between them is either a probe reading a different database than
    it says or a function counting something else — and both are the class
    where a number looks measured and is not.

    Read in the order doctor-then-function and asserted with a tolerance of
    zero: the agent plane is not being called while this runs, because nothing
    on this deployment calls it but this suite.
    """
    del as_root
    for document in _projects(project_a, project_b):
        key = _key(document)
        code, out, error = sh_status(
            str(REPO_ROOT / "bin" / "doctor.py"), "--project", key, "--json"
        )
        assert code in (0, 6), f"doctor --json for {key} exited {code}\n{error}"
        checks = {check["name"]: check for check in json.loads(out)["checks"]}
        evidence = dict(checks["agent record"].get("evidence") or {})

        row = _one(
            psql,
            document,
            "SELECT audit_rows::text || '|' || idempotency_rows::text "
            "FROM app_private.agent_record_size();",
        )
        audit_rows, idempotency_rows = (int(field) for field in row.split("|"))

        assert int(evidence["audit_rows"]) == audit_rows, (
            f"{key}: the doctor read {evidence['audit_rows']} audit rows and "
            f"agent_record_size() reads {audit_rows}"
        )
        assert int(evidence["idempotency_rows"]) == idempotency_rows, (
            f"{key}: the doctor read {evidence['idempotency_rows']} idempotency claims and "
            f"agent_record_size() reads {idempotency_rows}"
        )

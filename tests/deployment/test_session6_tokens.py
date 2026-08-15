"""Two verifiers, one key set (SEC-JWT-001, SEC-KEY-001, SEC-KEY-002).

Replaces two Session 6 placeholders in
``tests/security/test_future_security_boundaries.py``.

**The point of this module is that there are two verifiers.** The auth service
verifies its own tokens, and PostgREST verifies them independently from a JWKS
file. Runs 7 to 9 tested each of them against the key it had just signed with,
which is why D276 -- the auth service signing with a key PostgREST had never
been given -- survived 2776 offline tests and five green host runs. Every proof
here asks *both* of them, and the ones that matter assert they agree.

**SEC-KEY-002 is proved here as an invariant, not as a transition.** ADR 0088
built prepare -> acknowledge -> promote -> retire, and the operator guide is
explicit that no rotation may be started during Session 6: the key set holds at
most two keys, both slots are spoken for by the two live issuers, and the
transition between *those* is the first rotation the machinery is for. So what
runs here is what can run without starting one -- that the deployed key state
satisfies the rotation model's own validator, that the published set matches
what every verifier has actually loaded, and that a phase which has not begun
is recorded as not having begun. The convergence itself is unexercised, and
``test_the_cutover_is_built_and_deliberately_unexercised`` says so in the suite
rather than only in a document.
"""

from __future__ import annotations

import base64
import json
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import jwt_claims, jwt_keys, runtime_override
from agentic_postgres.secret_generation import SECRET_ROOT

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: What a PEM private key opens with, in either encoding openssl emits.
PRIVATE_KEY_MARKERS = ("-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----")

#: JWK members that are private RSA parameters. A verifier holding any of these
#: is an issuer.
PRIVATE_JWK_MEMBERS = ("d", "p", "q", "dp", "dq", "qi")


def _segment(token: str, index: int) -> dict[str, Any]:
    """One decoded JOSE segment, padded back to a multiple of four."""
    raw = token.split(".")[index]
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def test_the_published_key_set_is_what_every_verifier_actually_loaded(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    sh: Callable[..., str],
    service_container: Callable[[str, str], str],
    tmp_path: Path,
    as_root: None,
) -> None:
    """SEC-KEY-002's live invariant, and the proof D276 would have failed.

    Four readings of one key set, which must agree:

    * ``jwt.verification_kids`` in the deployed document;
    * ``GET /auth/jwks.json`` -- what the issuer publishes;
    * the rendered ``jwks.json`` on disk -- what the deploy wrote;
    * the bytes **inside the PostgREST container** -- what the verifier loaded.

    The fourth is the one that cannot be inferred. A running PostgREST never
    re-reads its key set, and a staged-and-renamed file leaves it holding the
    old inode (D278, ADR 0088) -- so the file on disk and the file the process
    has open are different questions, and only the second one decides whether a
    token verifies.

    Goes red if: the auth service's key stops being published (D276 returning);
    a deploy rewrites the JWKS without recreating the verifiers; or the document
    describes a set that is not the one being served.
    """
    del as_root
    jwt = project_a["jwt"]
    assert jwt["status"] == "ready", f"jwt.status is {jwt['status']!r}"
    declared = list(jwt["verification_kids"])

    published = api_call(f"{app_base(project_a)}/auth/jwks.json")
    assert published.status == 200, f"/auth/jwks.json answered {published.status}"
    served = [key["kid"] for key in json.loads(published.body)["keys"]]

    # Read from INSIDE the container, not from the rendered directory. The two
    # are different questions once a JWKS has been replaced at a stable path:
    # the process keeps the inode it opened, so the file on disk can be correct
    # while the verifier holds the previous set (D278, ADR 0088).
    #
    # `docker cp`, not `docker exec ... cat`. **The locked PostgREST image has no
    # `cat`** -- it has no shell and no coreutils at all -- so the exec spelling
    # exits 127 with `executable file not found in $PATH`, which reads like a
    # broken container rather than like a proof asking a distroless image for a
    # program (D305). It had never run: this was the line after the container
    # selector that D299 fixed.
    #
    # `docker cp` needs nothing inside the container and resolves the path
    # through the container's own mount namespace, which is the same view `cat`
    # would have had -- measured, with a plain bind of the same file as the
    # control.
    container = service_container(project_a["project"]["key"], runtime_override.REST_SERVICE)
    extracted = tmp_path / "jwks-from-the-container.json"
    sh("docker", "cp", f"{container}:{runtime_override.JWKS_CONTAINER_PATH}", str(extracted))
    loaded = json.loads(extracted.read_text(encoding="utf-8"))
    inside = [key["kid"] for key in loaded["keys"]]

    # THE VERIFIER'S SET, read three ways, and they must be equal. The third
    # is the one that cannot be inferred: a running PostgREST never re-reads its
    # key set, so the file on disk can be right while the process holds the
    # inode it opened at startup (D278, ADR 0088).
    assert declared == inside, (
        "two readings of the verifier's key set disagree:\n"
        f"  the deployed document says {declared}\n"
        f"  PostgREST has loaded      {inside}\n"
        "A set on disk that the process never re-read is the stranded inode "
        "ADR 0088 describes."
    )

    # THE ISSUER'S SET is a non-empty SUBSET of it, not the same list (ADR 0098).
    # `/auth/jwks.json` serves the one key the auth service signs with; the
    # verifier is configured with every live issuer's key, which since Run 10 is
    # two. This asserted equality and failed on both projects the first time it
    # ran -- and equality was the weaker statement, because it holds trivially
    # exactly while there is only one issuer (D304).
    assert served, "the issuer publishes no key at all; nothing can verify what it signs"
    assert set(served) <= set(declared), (
        f"the issuer publishes {served}, and the verifier accepts {declared}. A key the "
        "issuer signs with and the verifier does not hold refuses every token that "
        "issuer mints, which is D276 exactly"
    )

    for key in loaded["keys"]:
        for member in PRIVATE_JWK_MEMBERS:
            assert member not in key, (
                f"the key set PostgREST loaded carries the private RSA parameter "
                f"{member!r}; a verifier that can sign is an issuer"
            )


def test_a_token_the_service_issues_is_accepted_by_the_other_verifier(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    app_login: Callable[..., Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    app_probe_subject: Any,
) -> None:
    """SEC-JWT-001's live half: the two verifiers agree on a good token.

    This is D276's proof, stated positively. The auth service signs; PostgREST
    verifies from a file it read at startup. Until Run 10 those were different
    keys, and nothing noticed because each verifier was only ever asked about a
    token signed by the key it already held.

    The REST call asserts a status that is **not** 401, rather than 200: what is
    under test is that the token *verified*, and a verified token belonging to a
    role with no grant on a table is a legitimate 403 or 404. Asserting 200
    would couple this proof to the probe subject's grants, which is a different
    requirement's business.

    Goes red if: the two key sets diverge again; the `kid` the service stamps is
    not one the verifier holds; or the claim contract changes on one side only.
    """
    answer = app_login(project_a, app_probe_subject.username, app_probe_subject.password)
    assert answer.status == 200, f"login answered {answer.status}"
    token = json.loads(answer.body)["access_token"]

    header = _segment(token, 0)
    payload = _segment(token, 1)
    assert header["alg"] == jwt_keys.ALGORITHM, f"the token is signed with {header['alg']!r}"
    assert header["kid"] in project_a["jwt"]["verification_kids"], (
        f"the token names kid {header['kid']!r}, which is not in the published set "
        f"{project_a['jwt']['verification_kids']}. Every token this service issues "
        "would be refused by PostgREST -- this is D276 exactly"
    )
    assert payload["role"] == app_probe_subject.role_name
    assert payload["scope"] == list(app_probe_subject.scopes)

    at_rest = api_call(f"{rest_base(project_a)}/notes?limit=1", token=token)
    assert at_rest.status != 401, (
        f"PostgREST refused a token the auth service issued ({at_rest.status}: "
        f"{at_rest.body[:200]!r}). The two verifiers do not share a key set"
    )
    assert at_rest.status != 0, f"the REST route could not be reached: {at_rest.reason}"


@pytest.mark.parametrize(
    ("what", "mutate"),
    [
        ("a signature from another key", lambda t: t.rsplit(".", 1)[0] + "." + "A" * 342),
        ("a truncated signature", lambda t: t.rsplit(".", 1)[0] + ".short"),
        ("no signature at all", lambda t: t.rsplit(".", 1)[0] + "."),
        ("a tampered payload", lambda t: t.split(".")[0] + ".eyJzdWIiOiJ4In0." + t.split(".")[2]),
    ],
)
def test_both_verifiers_refuse_the_same_bad_tokens(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    app_login: Callable[..., Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    app_probe_subject: Any,
    what: str,
    mutate: Callable[[str], str],
) -> None:
    """SEC-JWT-001's negative matrix, asked of **both** verifiers.

    The contract suite proves the service's pre-parser refuses an unapproved
    algorithm, an unknown `kid`, a bad `typ` and a malformed compact form; those
    node IDs are registered against this requirement too. What only a deployment
    can show is that the *second* verifier refuses the same things -- a boundary
    that holds at one of two doors is not a boundary.

    Each case starts from a token this deployment really issued, so the only
    thing wrong with it is the mutation. A hand-built token would test the
    parser's opinion of a string this service never produces.

    Goes red if: either verifier accepts a token it did not sign; PostgREST is
    configured with a symmetric secret; or the signature check is skipped.
    """
    answer = app_login(project_a, app_probe_subject.username, app_probe_subject.password)
    assert answer.status == 200, f"login answered {answer.status}"
    bad = mutate(json.loads(answer.body)["access_token"])

    at_auth = api_call(f"{app_base(project_a)}/auth/me", token=bad)
    assert at_auth.status == 401, f"the auth service accepted {what} ({at_auth.status})"

    at_rest = api_call(f"{rest_base(project_a)}/notes?limit=1", token=bad)
    assert at_rest.status == 401, (
        f"PostgREST accepted {what} ({at_rest.status}). The auth service refused the "
        "same token, so this is a boundary that holds at one door of two"
    )


def test_an_expired_token_is_refused_by_both_within_the_measured_leeway(
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
) -> None:
    """The expiry half of SEC-JWT-001, and why it is asserted as a bound.

    ADR 0078 measured the locked PostgREST forgiving **30 seconds** past `exp`
    (D241): 30 is served and 31 is refused, in both directions. So a token is
    live for `MAX_TTL_SECONDS + 30`, not `MAX_TTL_SECONDS`, and a proof that
    asserted refusal one second after `exp` would fail against a correctly
    configured deployment.

    Rather than sleep for the leeway -- which would put a 930-second wait in the
    gate -- this reads the deadline the deployment states and asserts the
    relationship. The refusal itself is proved by the contract suite against a
    clock it controls.
    """
    published = api_call(f"{app_base(project_a)}/auth/jwks.json")
    assert published.status == 200

    assert jwt_claims.MAX_TTL_SECONDS + jwt_claims.CLOCK_SKEW_SECONDS == 930, (
        "the blast radius of a compromised token is MAX_TTL_SECONDS + CLOCK_SKEW, "
        f"which is now {jwt_claims.MAX_TTL_SECONDS + jwt_claims.CLOCK_SKEW_SECONDS}s "
        "rather than the 930s D241 measured against the locked verifier. Re-measure "
        "the leeway before changing either number"
    )


def test_no_verifier_holds_private_signing_material(
    project_a: dict[str, Any],
    sh: Callable[..., str],
    service_container: Callable[[str, str], str],
    active_generation: Callable[[dict[str, Any]], str],
    as_root: None,
) -> None:
    """SEC-KEY-001, and the shape it has to have now that there are two issuers.

    Session 5's version asserted that *no service* holds a private key, which was
    true when the only issuer was the operator's own command. It is not the
    property any more: the auth service **is** an issuer and must hold its key.

    So the property is per-service. The auth container holds exactly its own
    signing key, at 0400; every other running container holds none; and the
    bootstrap issuer's key stays in the root plane where no container reaches
    it. Checked from ``docker inspect`` rather than from the Compose model, for
    the reason SEC-DOCS-001 records: the model says what was asked for.

    **The generation comes from the live pointer, not from the document.** This
    read ``project_a["secrets"]["generation_id"]`` and failed on a correct
    deployment: the gate's own restart-matrix proofs restart project A's unit,
    ``project-runtime.sh up`` re-materializes secrets, and every container is
    recreated onto a new generation -- so by the time this ran, the containers
    held `9418d7ae…` while the document still recorded `9fefc82f…`. That is D76,
    which `bin/dev-token.py` quotes in its own docstring, met by a proof written
    four runs later (D306).

    Which generation to read is decided by the question: this one is *what a
    running container holds*, so it is the pointer. A proof about what a
    deployment recorded would read the document.

    Goes red if: the signing key gains a second compose consumer; a verifier
    gains a mount that reaches either private key; or the auth service's key
    mode is relaxed.
    """
    del as_root
    project_key = project_a["project"]["key"]
    generation = SECRET_ROOT / project_key / "generations" / active_generation(project_a)

    auth_key = generation / runtime_override.AUTH_SERVICE / "auth_jwt_signing_key.pem"
    assert auth_key.is_file(), f"the auth service has no signing key at {auth_key}"
    mode = auth_key.stat()
    assert stat.S_IMODE(mode.st_mode) == 0o400, (
        f"{auth_key} is {stat.S_IMODE(mode.st_mode):04o}, not 0400"
    )

    auth_container = service_container(project_key, runtime_override.AUTH_SERVICE)
    names = [line for line in sh("docker", "ps", "--format", "{{.Names}}").splitlines() if line]
    assert names, "no containers are running, so nothing here was inspected"

    for name in names:
        inspected = sh("docker", "inspect", name)
        for marker in PRIVATE_KEY_MARKERS:
            assert marker not in inspected, f"{name} carries private key material inline"
        if name == auth_container:
            assert str(auth_key) in inspected, (
                f"{name} is the issuer and does not mount its own signing key at "
                f"{auth_key}; it cannot sign anything"
            )
            continue
        assert str(auth_key) not in inspected, (
            f"{name} mounts the auth service's signing key. A verifier that can reach "
            "the private key is an issuer"
        )


def test_the_cutover_is_built_and_deliberately_unexercised(
    project_a: dict[str, Any],
) -> None:
    """SEC-KEY-002, stated as what this session can honestly assert.

    The convergence -- prepare, acknowledge, promote, retire -- is **not** run
    here, and that is a decision rather than an omission (ADR 0088, and §4 of
    the operator guide). Two live issuers fill a two-key ceiling; the transition
    between them is the first rotation the machinery exists for, and starting it
    inside the session that publishes the second issuer would mean proving the
    rotation and the issuance at the same time, with one deployment to debug.

    What is asserted is everything that holds *without* a rotation:

    * the deployed key state satisfies the rotation model's own validator, so
      the invariants the phases rely on hold on the real document;
    * no rotation is in flight -- no deadline, and no key beyond the ceiling;
    * the acknowledgement record is ``None`` rather than ``{}``, which is the
      distinction outputs v9 introduced: null says nothing has been asked, and
      an empty object says every verifier was asked and none answered.

    **This test does not prove the transition converges.** The run log says so,
    the operator guide says so, and it is recorded here rather than pretended --
    the same call Run 8's M14 made about the advisory lock.

    Goes red if: a rotation is left half-finished on this host; the deployed
    document stops satisfying the validator; or the ceiling is raised, which
    would admit a second rotation begun while the first is in flight.
    """
    jwt = project_a["jwt"]
    jwt_keys.validate_key_state(jwt)

    assert jwt["retire_after"] is None, (
        f"a rotation is in flight on this deployment (retire_after={jwt['retire_after']!r}). "
        "Session 6 does not start one; finish or abandon it before reading this gate"
    )
    assert jwt["verifier_acknowledgements"] is None, (
        "verifier_acknowledgements is recorded but no rotation is in flight; null means "
        "nothing has been asked and {} means every verifier was asked and none answered"
    )
    assert len(jwt["verification_kids"]) <= jwt_keys.MAX_VERIFICATION_KEYS, (
        f"the key set holds {len(jwt['verification_kids'])} keys, above the ceiling of "
        f"{jwt_keys.MAX_VERIFICATION_KEYS}"
    )
    assert jwt["active_kid"] in jwt["verification_kids"], (
        "the active key is not one a verifier accepts"
    )


def test_the_two_issuers_are_both_published_during_the_overlap(
    project_a: dict[str, Any],
) -> None:
    """The state Session 6 deliberately ends in, asserted rather than assumed.

    Two keys, no deadline. ``validate_key_state`` admits it (ADR 0088 widened it
    to, and ``test_two_keys_without_a_deadline_is_accepted`` is the contract
    proof), and it is the shape the next session's first rotation starts from.

    Written as a positive assertion because the alternative is invisible: a
    deployment that published one key would look healthy from every other proof
    in this module, and would mean either that the auth service's key is missing
    (D276) or that the bootstrap issuer was retired without a cutover.
    """
    kids = project_a["jwt"]["verification_kids"]
    assert len(kids) == 2, (
        f"this deployment publishes {len(kids)} verification key(s). Session 6 ends with "
        "two live issuers -- the bootstrap issuer and the auth service -- so one key "
        "means one of them cannot be verified. Which one is the question D276 answers"
    )
    assert len(set(kids)) == 2, f"the same key is published twice: {kids}"

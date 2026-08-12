"""The documentation service's contract (ADR 0069, D128, D202).

What is asserted here is what makes the page self-contained *as a property of
this deployment* rather than as a promise about a third party's code. The
distinction is the whole of ADR 0069: `withDefaultFonts: false` is Scalar
honouring its own flag, and the Content-Security-Policy is the visitor's browser
refusing whatever the bundle attempts.

Measured on the built image before any of this was written: every route 200,
`/../serve.py` and `/app/serve.py` 404, every verb other than GET and HEAD 501,
the served document byte-identical to the committed snapshot, and all seven
security headers present. These tests hold the same properties at the source,
where they can go red without a docker daemon.
"""

from __future__ import annotations

import importlib.util
import re
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SERVICE = REPO_ROOT / "services" / "docs"
PAGE = SERVICE / "index.html"
DOCKERFILE = SERVICE / "Dockerfile"


@pytest.fixture(scope="module")
def serve() -> Any:
    """`services/docs/serve.py`, imported rather than run.

    Importing is safe by construction: the module binds constants and classes,
    and every side effect lives under `main()` behind the guard. That is also
    why the Dockerfile test below exists -- `importlib` never fires the guard,
    so a definition placed after it is bound here and unbound in the container
    (D185).
    """
    specification = importlib.util.spec_from_file_location("apg_docs_serve", SERVICE / "serve.py")
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The policy that makes the page self-contained
# ---------------------------------------------------------------------------


def directives(policy: str) -> dict[str, str]:
    return {
        part.strip().split(" ", 1)[0]: part.strip() for part in policy.split(";") if part.strip()
    }


def instructions(dockerfile: str) -> str:
    """A Dockerfile with its comments removed.

    The comment explaining *why* the snapshot is not baked names the snapshot,
    so a scan of the raw text counts the explanation as the thing it warns
    against. `test_output_schema.code_only`'s docstring records four prior
    instances of that; this is the fifth, found by writing the assertion and
    watching it fail against correct code.
    """
    return "\n".join(line for line in dockerfile.splitlines() if not line.lstrip().startswith("#"))


def markup(page: str) -> str:
    """The page with its HTML comments and its `//` script comments removed.

    Same hazard, two comment syntaxes. The script block's comment says "No
    `proxyUrl`" -- which is the correct configuration, described in the one
    vocabulary that makes a scan for `proxyUrl` find it.
    """
    without_html = re.sub(r"<!--.*?-->", "", page, flags=re.DOTALL)
    return "\n".join(
        line for line in without_html.splitlines() if not line.lstrip().startswith("//")
    )


def test_the_policy_refuses_by_default(serve: Any) -> None:
    """`default-src 'none'` first, so anything unnamed is refused rather than inherited.

    A policy that named only the sources it wanted would leave every fetch type
    nobody thought of -- `manifest-src`, `media-src`, `worker-src` -- at the
    browser's default, which is *allow*.
    """
    parsed = directives(serve.CONTENT_SECURITY_POLICY)
    assert parsed["default-src"] == "default-src 'none'"


@pytest.mark.parametrize(
    ("directive", "expected"),
    [
        ("script-src", "script-src 'self'"),
        ("font-src", "font-src 'self'"),
        ("connect-src", "connect-src 'self'"),
        ("base-uri", "base-uri 'none'"),
        ("form-action", "form-action 'none'"),
        ("frame-ancestors", "frame-ancestors 'none'"),
    ],
)
def test_the_policy_pins_each_fetch_the_bundle_could_make(
    serve: Any, directive: str, expected: str
) -> None:
    """Written as literals rather than derived from the constant under test.

    A parametrization computed from `CONTENT_SECURITY_POLICY` collapses to an
    empty parameter set the moment the constant is emptied -- and pytest reports
    an empty set as a pass, which is how a refusal test once deleted itself
    (D190).

    `font-src` and `connect-src` are the two that matter most: the vendored
    bundle names `fonts.scalar.com` and `proxy.scalar.com`, and these are what
    make those names inert.
    """
    assert directives(serve.CONTENT_SECURITY_POLICY)[directive] == expected


def test_only_style_src_is_relaxed(serve: Any) -> None:
    """The one concession, held to exactly one directive.

    Scalar writes component styles into the document at runtime and the page is
    unstyled without `'unsafe-inline'`. An inline *style* cannot fetch, navigate
    or execute; an inline *script* can, which is why the same allowance must
    never appear in `script-src`.
    """
    relaxed = [
        name
        for name, value in directives(serve.CONTENT_SECURITY_POLICY).items()
        if "unsafe-inline" in value or "unsafe-eval" in value
    ]
    assert relaxed == ["style-src"]


def test_every_response_carries_the_security_headers(serve: Any) -> None:
    for header in (
        "Content-Security-Policy",
        "Referrer-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Cross-Origin-Opener-Policy",
        "Cross-Origin-Resource-Policy",
    ):
        assert header in serve.SECURITY_HEADERS, f"{header} is not sent"
    assert serve.SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert serve.SECURITY_HEADERS["Referrer-Policy"] == "no-referrer"


# ---------------------------------------------------------------------------
# The server is a route table, not a static file server
# ---------------------------------------------------------------------------


def test_the_route_table_is_closed(serve: Any) -> None:
    """Four paths, and no way to name a fifth.

    This is a shorter argument than any traversal defence: there is no path
    joining and no directory walk, so there is no path to traverse. Measured on
    the image -- `/../serve.py` and `/app/serve.py` are both 404.
    """
    assert set(serve.ROUTES) == {"/", "/index.html", "/standalone.js", "/openapi.json"}


def test_nothing_joins_a_request_path_to_a_directory(serve: Any) -> None:
    """The property behind the closed table, asserted at the source.

    A route table that was later "generalised" into `PUBLIC / path` would keep
    every test above green and reintroduce every traversal question at once.
    """
    source = (SERVICE / "serve.py").read_text(encoding="utf-8")
    body = source[source.index("def _serve") :]
    body = body[: body.index("def do_GET")]
    for hazard in ("PUBLIC /", "os.path.join", "/ path", "resolve()", "iterdir"):
        assert hazard not in body, f"the request path reaches the filesystem via {hazard!r}"
    assert "ROUTES.get(path)" in body, "the handler no longer looks the path up in the table"


def test_the_handler_serves_only_get_and_head(serve: Any) -> None:
    """Anything else is 501 from the base handler, which is the right refusal.

    A `do_POST` here would be a write surface on a page whose whole design is
    that it has none.
    """
    verbs = {name for name in dir(serve.Handler) if name.startswith("do_")}
    assert verbs == {"do_GET", "do_HEAD"}


def test_an_unreadable_snapshot_is_not_an_empty_document(serve: Any) -> None:
    """503, never 200 with nothing.

    The snapshot is a mount, so absent is a deployment state rather than an
    impossibility -- and an empty OpenAPI document is *valid* and describes
    nothing, so serving one would publish "this API has no operations" as though
    it were reviewed.
    """
    source = (SERVICE / "serve.py").read_text(encoding="utf-8")
    handler = source[source.index("except OSError:") :]
    handler = handler[: handler.index("return")]
    assert "503" in handler


def test_the_snapshot_is_mounted_rather_than_baked() -> None:
    """The reviewed bytes exist once.

    Baking the snapshot would mean a documentation image per project per
    revision, each one a place where the reviewed bytes could differ from the
    reviewed bytes.
    """
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert 'VOLUME ["/app/snapshot"]' in dockerfile
    assert "canonical.json" not in instructions(dockerfile), (
        "the reviewed snapshot is copied into the image"
    )


# ---------------------------------------------------------------------------
# The page, and what it is obliged to say
# ---------------------------------------------------------------------------


def test_the_page_loads_nothing_from_another_origin() -> None:
    """Every `src` and `href` is relative.

    The CSP refuses a cross-origin script anyway; this is the other half, so a
    page that tried would fail review rather than fail silently in a browser
    whose report nobody reads.
    """
    page = PAGE.read_text(encoding="utf-8")
    external = re.findall(r'(?:src|href)\s*=\s*"([^"]+)"', page)
    remote = [value for value in external if value.startswith(("http://", "https://", "//"))]
    assert not remote, f"the page loads {remote} from another origin"


def test_the_page_turns_off_the_two_defaults_that_fetch() -> None:
    """`withDefaultFonts` is `default: true` at every measured version (D202).

    Set here *and* refused by the header, deliberately: this half is a promise
    about a third party's code honouring its own flag, and the header is the
    half a browser enforces.
    """
    page = markup(PAGE.read_text(encoding="utf-8"))
    assert "withDefaultFonts: false" in page
    assert "proxyUrl" not in page, "a proxyUrl routes a reader's request through a third party"


def test_the_page_says_the_verbs_it_advertises_do_not_work() -> None:
    """ADR 0060, in the one place a reader will look.

    `follow-privileges` publishes DELETE, PATCH and POST on both views because
    the documentation role holds EXECUTE on the write RPCs, and all three return
    403. No PostgREST setting filters methods by grant, so the document cannot be
    fixed -- and a reference that showed those verbs without saying so would be
    the first thing in this deployment to lie about the surface.
    """
    page = PAGE.read_text(encoding="utf-8")
    note = page[page.index('id="apg-surface-note"') :]
    for verb in ("DELETE", "PATCH", "POST"):
        assert verb in note, f"the page does not mention {verb}"
    assert "403" in note


def test_the_page_says_the_document_is_a_reviewed_snapshot() -> None:
    """A live capture and a reviewed one look identical to a reader."""
    page = PAGE.read_text(encoding="utf-8")
    assert "snapshot" in page[page.index('id="apg-surface-note"') :]


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def test_the_lock_file_is_committed_and_names_the_locked_version() -> None:
    """`npm ci` fails if package.json and the lock disagree, which is what makes
    a committed lock load-bearing rather than decorative."""
    import json

    lock = json.loads((SERVICE / "package-lock.json").read_text(encoding="utf-8"))
    manifest = json.loads((SERVICE / "package.json").read_text(encoding="utf-8"))
    declared = manifest["dependencies"]["@scalar/api-reference"]
    resolved = lock["packages"]["node_modules/@scalar/api-reference"]["version"]
    assert resolved == declared

    versions = (REPO_ROOT / "versions.env").read_text(encoding="utf-8")
    assert f"SCALAR_VERSION={declared}\n" in versions, (
        "the service pins a Scalar version the lock file does not record. D201 is "
        "what happens when those two drift and nothing dereferences either"
    )


def test_the_build_installs_from_the_lock_and_runs_no_scripts() -> None:
    """Instructions only, and that is not a detail.

    This read the raw file until a mutation walked through it: the Dockerfile's
    comment says "`npm ci`, not `npm install`" and explains `--ignore-scripts`,
    so swapping the actual instruction for `npm install` left both assertions
    satisfied *by the comment warning against it*. Sixth instance in this
    repository, and the first inside a test written the same hour as the helper
    that prevents it.
    """
    dockerfile = instructions(DOCKERFILE.read_text(encoding="utf-8"))
    assert "npm ci" in dockerfile, "npm install would resolve fresh and ignore the lock"
    assert "--ignore-scripts" in dockerfile
    assert "npm install" not in dockerfile


def test_only_the_bundle_crosses_the_stage_boundary() -> None:
    """The install is ~230 MB and the page needs one file.

    Copying the tree would ship a build environment -- npm, a package cache, 280
    packages of transitive dependency -- to a public route.
    """
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    copies = re.findall(r"^COPY --from=(\S+)\s+(\S+)\s+(\S+)$", dockerfile, re.MULTILINE)
    assert copies, "nothing crosses the stage boundary; the bundle is not vendored"
    assert len(copies) == 1, f"more than the bundle crosses the boundary: {copies}"
    assert copies[0][1].endswith("standalone.js")


def test_the_service_runs_as_the_nonroot_pair() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER 65532:65532" in dockerfile

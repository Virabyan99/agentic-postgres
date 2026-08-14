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
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SERVICE = REPO_ROOT / "services" / "docs"
PAGE = SERVICE / "index.html"
#: The application API's page (D226). A second document under the same server,
#: the same CSP and the same credential.
APP_PAGE = SERVICE / "app.html"
#: Both, for the properties that are about "a page this service serves" rather
#: than about one surface's contents. Written as a list so a third page cannot
#: be added without every one of them seeing it -- which is the failure mode
#: D175 records for a registry, at the scale of a directory.
PAGES = [PAGE, APP_PAGE]
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
    """Eight paths across two surfaces, and no way to name a ninth.

    This is a shorter argument than any traversal defence: there is no path
    joining and no directory walk, so there is no path to traverse. Measured on
    the image -- `/../serve.py` and `/app/serve.py` are both 404.

    The table was four paths at the container root until ADR 0087 moved both
    surfaces under their own segment. The edge now strips only the documentation
    *root*, which is what lets one container tell `/docs/rest` from `/docs/app`
    -- and, the reason it changed, `/docs/rest` from `/docs/rest/`.
    """
    assert set(serve.ROUTES) == {
        "/rest/",
        "/rest/index.html",
        "/rest/standalone.js",
        "/rest/openapi.json",
        "/app/",
        "/app/index.html",
        "/app/standalone.js",
        "/app/openapi.json",
    }


def test_the_two_surfaces_serve_two_documents_and_one_bundle(serve: Any) -> None:
    """D226's claim, made checkable at the source.

    "One image, one CSP, one credential" is only true if the second surface is a
    second *file* rather than a second container -- so the bundle is shared and
    the documents are not. A table pointing both surfaces at one snapshot would
    render the REST document under the application's URL, which reads as a
    working page.
    """
    assert serve.ROUTES["/rest/standalone.js"] == serve.ROUTES["/app/standalone.js"]
    assert serve.ROUTES["/rest/openapi.json"][0] != serve.ROUTES["/app/openapi.json"][0]
    assert serve.ROUTES["/rest/"][0] != serve.ROUTES["/app/"][0], (
        "both surfaces serve the same HTML, so one of them carries the other's "
        "surface note -- which is the page lying about what it describes"
    )


def test_the_slash_less_form_of_each_surface_redirects_relatively(serve: Any) -> None:
    """ADR 0087, and the defect it repairs.

    Measured against the locked Traefik: a browser given `/docs/rest` resolves
    the page's own `<script src="standalone.js">` against `/docs/` and asks for
    `/docs/standalone.js`, which **404s** -- with `/docs/rest/standalone.js` at
    200 as the control. The page returned 200, the HTML was correct, and it did
    not render.

    The target must be **relative**. An absolute `/rest/` would send a visitor
    at `/docs/rest` to a path no router matches, and it would be this process
    deriving a published prefix it is deliberately never told (ADR 0061).
    """
    assert set(serve.REDIRECTS) == {"/rest", "/app"}
    for source, target in serve.REDIRECTS.items():
        assert not target.startswith("/"), f"{source} redirects to an absolute path: {target}"
        assert f"/{target}" == f"{source}/", f"{source} redirects somewhere else: {target}"
        assert f"{source}/" in serve.ROUTES, f"{source} redirects to a path with no route"


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


@pytest.mark.parametrize("page_path", PAGES, ids=lambda path: path.name)
def test_the_page_loads_nothing_from_another_origin(page_path: Path) -> None:
    """Every `src` and `href` is relative, on every page this service serves.

    The CSP refuses a cross-origin script anyway; this is the other half, so a
    page that tried would fail review rather than fail silently in a browser
    whose report nobody reads.
    """
    page = page_path.read_text(encoding="utf-8")
    external = re.findall(r'(?:src|href)\s*=\s*"([^"]+)"', page)
    remote = [value for value in external if value.startswith(("http://", "https://", "//"))]
    assert not remote, f"{page_path.name} loads {remote} from another origin"


@pytest.mark.parametrize("page_path", PAGES, ids=lambda path: path.name)
def test_the_page_turns_off_the_two_defaults_that_fetch(page_path: Path) -> None:
    """`withDefaultFonts` is `default: true` at every measured version (D202).

    Set here *and* refused by the header, deliberately: this half is a promise
    about a third party's code honouring its own flag, and the header is the
    half a browser enforces. Asked of both pages, because a second surface that
    forgot it would be refused by the CSP and would render without the
    explanation.
    """
    page = markup(page_path.read_text(encoding="utf-8"))
    assert "withDefaultFonts: false" in page
    assert "proxyUrl" not in page, "a proxyUrl routes a reader's request through a third party"


@pytest.mark.parametrize("page_path", PAGES, ids=lambda path: path.name)
def test_every_asset_a_page_names_is_a_route_the_server_has(page_path: Path, serve: Any) -> None:
    """ADR 0087's proof, and the one this repository was missing.

    The measurement that found the defect: a browser given `/docs/rest` resolves
    `<script src="standalone.js">` against `/docs/` and asks for
    `/docs/standalone.js`, which 404s. Every proof the page had asked for the
    page's own URL and read the status -- **none had ever asked for what the
    page then asks for.**

    Asserted here against the route table, which is where a relative reference
    lands after the edge has stripped the documentation root: a page under
    `/rest/` naming `standalone.js` resolves to `/rest/standalone.js`. The live
    half runs at the edge, where the strip is real.
    """
    page = page_path.read_text(encoding="utf-8")
    segment = serve.APP_SEGMENT if page_path is APP_PAGE else serve.REST_SEGMENT

    named = set(re.findall(r'src\s*=\s*"([^"]+)"', page))
    named |= set(re.findall(r"url:\s*'([^']+)'", page))
    assert named, f"no asset reference was found in {page_path.name}; the scan is broken"

    for reference in sorted(named):
        assert not reference.startswith(("/", "http://", "https://", "//")), (
            f"{page_path.name} names {reference!r} absolutely, which this server cannot "
            "answer for -- it is never told the published prefix (ADR 0061)"
        )
        resolved = f"{segment}/{reference}"
        assert resolved in serve.ROUTES, (
            f"{page_path.name} asks for {reference!r}, which resolves to {resolved} and "
            "is not a route this server has"
        )


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


@pytest.mark.parametrize("page_path", PAGES, ids=lambda path: path.name)
def test_the_page_says_the_document_is_a_reviewed_snapshot(page_path: Path) -> None:
    """A live capture and a reviewed one look identical to a reader."""
    page = page_path.read_text(encoding="utf-8")
    assert "snapshot" in page[page.index('id="apg-surface-note"') :]


def test_the_application_page_does_not_repeat_the_rest_surfaces_warning() -> None:
    """ADR 0060's note is about `follow-privileges`, which the auth service is not.

    The REST document advertises DELETE, PATCH and POST that all return 403,
    because it is generated from database privileges and no PostgREST setting
    filters methods by grant. The application document is generated from route
    definitions, so it advertises what the service implements -- and a page that
    copied the warning across would be describing a surface it is not
    describing, which is the failure `index.html`'s own note names.
    """
    note = APP_PAGE.read_text(encoding="utf-8")
    note = note[note.index('id="apg-surface-note"') :]
    assert "403" not in note, "the application page repeats the REST surface's warning"
    assert "role" in note and "scope" in note, (
        "the application page says nothing about the one rule underneath its whole "
        "surface: a client never submits a role or a scope"
    )


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

"""The site's chrome and components come from the builder (Session 45, ADR 0288).

`UI-SITE-001`. Every chip is `STATUS_WORDS`' text for the row it names, every
count and the stacked bar are the Ledger's, every docs page is in exactly one
group and previous / next follow the groups, heading ids are unique and *On
this page* lists every `h2`, the current section is marked by prefix, no page
carries a `style=` attribute or a script, the restore example's command is the
documented one, and the layout vocabulary is closed. The built pages are read
with `html.parser`; each refusal is also driven with a page that must fail.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, reality_ledger, site_build

pytestmark = [pytest.mark.contract, pytest.mark.p0]


class _Elements(HTMLParser):
    """Every element's tag, attributes and the text inside it, in order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[dict[str, Any]] = []
        self._open: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = {
            "tag": tag,
            "attrs": {k: v or "" for k, v in attrs},
            "text": [],
            "parents": [e["tag"] + "." + e["attrs"].get("class", "") for e in self._open],
        }
        self.found.append(element)
        if tag not in ("input", "meta", "link", "rect", "br", "path"):
            self._open.append(element)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index]["tag"] == tag:
                del self._open[index:]
                return

    def handle_data(self, data: str) -> None:
        for element in self._open:
            element["text"].append(data)


def _elements(text: str) -> list[dict[str, Any]]:
    parser = _Elements()
    parser.feed(text)
    for element in parser.found:
        element["text"] = "".join(element["text"]).strip()
    return parser.found


def _classes(element: dict[str, Any]) -> set[str]:
    return set(element["attrs"].get("class", "").split())


@pytest.fixture(scope="module")
def built() -> dict[str, str]:
    return {
        name: data.decode("utf-8")
        for name, data in site_build.build().items()
        if name.endswith(".html")
    }


@pytest.fixture(scope="module")
def ledger() -> dict[str, Any]:
    return reality_ledger.load()


def _route(name: str) -> str:
    return "/" + name.removesuffix("index.html")


def test_chips_are_the_rows_words(built: dict[str, str], ledger: dict[str, Any]) -> None:
    """Each chip's class names a status and its text is that status's
    `STATUS_WORDS`; every status has a chip class with a rule in `site.css`;
    a docs page's chips are its `ledger:` rows, in order, each with its status."""
    status_of_class = {cls: status for status, cls in site_build.CHIP_CLASSES.items()}
    assert set(site_build.CHIP_CLASSES) == set(reality_ledger.STATUSES)
    css = (REPO_ROOT / "site" / "static" / "site.css").read_text(encoding="utf-8")
    for cls in site_build.CHIP_CLASSES.values():
        assert re.search(rf"\.{cls}\b[^{{]*\{{", css), cls
    by_id = {row["id"]: row for row in ledger["rows"]}
    seen = 0
    for name, text in built.items():
        for element in _elements(text):
            if "chip" not in _classes(element) or element["tag"] != "span":
                continue
            named = _classes(element) & set(status_of_class)
            if not named:
                assert _classes(element) == {"chip", "state-ready"}, (name, element)
                continue
            (cls,) = named
            assert element["text"] == site_build.STATUS_WORDS[status_of_class[cls]], (name, element)
            seen += 1
    assert seen > len(ledger["rows"]), "the scan read almost no chip"
    for page in site_build.pages():
        if not site_build._is_docs(page.route):
            continue
        text = built[page.route.lstrip("/") + "index.html"]
        concepts = [
            e["text"]
            for e in _elements(text)
            if e["tag"] == "span" and _classes(e) == {"concept"} and "ul.chips" in e["parents"]
        ]
        assert concepts == [by_id[row]["concept"] for row in page.ledger], page.route


def test_the_counts_are_the_ledgers(built: dict[str, str], ledger: dict[str, Any]) -> None:
    """The menu's notes, the ledger page's filter labels and its count line are
    the build's own numbers, never typed."""
    statuses = Counter(row["status"] for row in ledger["rows"])
    total = len(ledger["rows"])
    documents = [
        p for p in site_build.pages() if p.route.startswith("/docs/") and p.route != "/docs/"
    ]
    steps = sum(
        1
        for line in (REPO_ROOT / "site" / "pages" / "quickstart.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("## ")
    )
    notes = [e["text"] for e in _elements(built["index.html"]) if _classes(e) == {"menu-note"}]
    assert notes == [
        f"{steps} steps",
        f"{len(documents)} pages",
        "Free in the beta",
        f"{total} concepts",
        "for members",
    ]
    page = _elements(built["ledger/index.html"])
    labels = [e["text"] for e in page if e["tag"] == "label"]
    expected = [f"all, {total}"] + [
        f"{site_build.STATUS_WORDS[s]}, {statuses[s]}"
        for s in reality_ledger.STATUSES
        if statuses[s]
    ]
    assert labels == expected
    assert [e["text"] for e in page if _classes(e) == {"count"}] == [f"{total} concepts"]
    radios = [e["attrs"]["id"] for e in page if e["tag"] == "input"]
    assert radios == ["status-all"] + [
        "status-" + site_build.CHIP_CLASSES[s].removeprefix("chip-")
        for s in reality_ledger.STATUSES
        if statuses[s]
    ]


def _bar(html_text: str) -> tuple[list[tuple[str, int, int]], list[str]]:
    rects = [
        (e["attrs"]["class"], int(e["attrs"]["x"]), int(e["attrs"]["width"]))
        for e in _elements(html_text)
        if e["tag"] == "rect"
    ]
    legend = [e["text"] for e in _elements(html_text) if e["tag"] == "li"]
    return rects, legend


def test_the_bar_sums_to_the_ledger(ledger: dict[str, Any]) -> None:
    """The segments are contiguous, their widths the counts, summing to the
    total; a status with no row has no segment and no legend entry; the
    heading's two numbers are the total and the rows that work today. Driven
    with a second Ledger holding one `trial` row, which gains its segment."""
    for rows in (ledger["rows"], [*ledger["rows"][:-1], {**ledger["rows"][-1], "status": "trial"}]):
        counts = Counter(row["status"] for row in rows)
        rendered = site_build.ledger_summary({"rows": rows})
        rects, legend = _bar(rendered)
        present = [s for s in reality_ledger.STATUSES if counts[s]]
        assert [r[0].split()[1] for r in rects] == [
            "seg-" + site_build.CHIP_CLASSES[s].removeprefix("chip-") for s in present
        ]
        x = 0
        for (_, at, width), status in zip(rects, present, strict=True):
            assert (at, width) == (x, counts[status])
            x += width
        assert x == len(rows)
        assert legend == [f"{site_build.STATUS_WORDS[s]}, {counts[s]}" for s in present]
        working = counts["beta"] + counts["available"]
        assert f"{len(rows)} concepts. {working} of them work today." in rendered
        assert f'viewBox="0 0 {len(rows)} 1"' in rendered


def test_every_docs_page_is_in_one_group() -> None:
    """Each page under `site/pages/docs/` but the index is in exactly one group,
    and each group entry is a page; a page no group holds is refused."""
    pages = site_build.pages()
    documents = {p.route for p in pages if p.route.startswith("/docs/")} - {"/docs/"}
    order = site_build.docs_order()
    assert len(order) == len(set(order))
    assert documents <= set(order) and set(order) <= {p.route for p in pages}
    assert "/docs/sql-editor/" in site_build.DOCS_GROUPS[1][1]
    stray = site_build.Page(
        source=site_build.PAGES_ROOT / "docs" / "stray.md",
        route="/docs/stray/",
        title="Stray",
        description="d",
        ledger=("postgresql",),
        body="# Stray\n",
        body_line=5,
    )
    with pytest.raises(site_build.SiteError, match="no documentation group holds"):
        site_build.check_groups([*pages, stray])


def test_previous_and_next_follow_the_groups(built: dict[str, str]) -> None:
    order = site_build.docs_order()
    for at, route in enumerate(order):
        if not site_build._is_docs(route):
            continue
        links = {
            e["attrs"]["class"]: e["attrs"]["href"]
            for e in _elements(built[route.lstrip("/") + "index.html"])
            if e["tag"] == "a" and _classes(e) & {"previous", "next"}
        }
        expected = {}
        if at > 0:
            expected["previous"] = order[at - 1]
        if at < len(order) - 1:
            expected["next"] = order[at + 1]
        assert links == expected, route


def test_heading_ids_are_unique_and_listed(built: dict[str, str]) -> None:
    """No page repeats an id; a docs page's *On this page* lists every `h2` of
    its article, in order; a repeated heading gets `-2`; a link to an id that
    does not exist is refused."""
    for name, text in built.items():
        ids = re.findall(r'\bid="([^"]+)"', text)
        assert len(ids) == len(set(ids)), (name, [i for i in ids if ids.count(i) > 1])
        if site_build._is_docs(_route(name)):
            article = text[text.index("<article>") : text.index("</article>")]
            toc = (
                re.findall(r'<li><a href="#([^"]+)">', text[text.index('class="toc"') :])
                if 'class="toc"' in text
                else []
            )
            assert toc == re.findall(r'<h2 id="([^"]+)">', article), name
    assert site_build.unique_ids('<h2 id="a">x</h2><h2 id="a">y</h2><h3 id="a">z</h3>') == (
        '<h2 id="a">x</h2><h2 id="a-2">y</h2><h3 id="a-3">z</h3>'
    )
    page = site_build.Page(
        source=site_build.PAGES_ROOT / "x.md",
        route="/x/",
        title="x",
        description="d",
        ledger=("postgresql",),
        body="",
        body_line=5,
    )
    site_build._check_anchors({"/x/": (page, '<h2 id="here">h</h2><a href="#here">ok</a>')})
    with pytest.raises(site_build.SiteError, match="names no id"):
        site_build._check_anchors({"/x/": (page, '<h2 id="here">h</h2><a href="#gone">no</a>')})


def test_the_current_section_is_marked(built: dict[str, str]) -> None:
    """The header marks the section whose route prefixes the page's -- *Docs*
    on every docs page, nothing on the home page -- and the sidebar marks the
    page itself."""
    for name, text in built.items():
        route = _route(name)
        if name == "404.html":
            route = ""
        marked = [
            e["attrs"]["href"]
            for e in _elements(text)
            if e["tag"] == "a"
            and e["attrs"].get("aria-current") == "page"
            and any(p.startswith("nav.primary") for p in e["parents"])
        ]
        expected = [h for h, _ in site_build.NAVIGATION if h != "/" and route.startswith(h)]
        assert marked == expected, (name, marked)
        if site_build._is_docs(route) and route != "/docs/":
            sidebar = [
                e["attrs"]["href"]
                for e in _elements(text)
                if e["tag"] == "a"
                and e["attrs"].get("aria-current") == "page"
                and any(p.startswith("nav.sidebar") for p in e["parents"])
            ]
            assert sidebar == [route], name
    assert not any(
        e["attrs"].get("aria-current")
        for e in _elements(built["index.html"])
        if any(p.startswith("nav.primary") for p in e["parents"])
    )


def test_no_page_carries_a_style_attribute(built: dict[str, str]) -> None:
    """The policy has no `'unsafe-inline'` (D2820): presentation lives in the
    stylesheet and SVG attributes, never a `style=` or a script."""
    for name, text in built.items():
        assert not re.search(r"\sstyle\s*=", text, re.IGNORECASE), name
        assert "<script" not in text and "<style" not in text, name
        assert not any("style" in e["attrs"] for e in _elements(text)), name
    assert site_build.LOGO.count("<rect") == 3 and "style" not in site_build.LOGO


def test_the_restore_example_is_a_documented_command() -> None:
    """The hero's command, its `--at` value aside, is `docs/branches.md`'s
    restore line, and the block says it is an example."""
    documented = [
        line
        for line in (site_build.PAGES_ROOT / "docs" / "branches.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("apg branch create") and " --at " in line
    ]
    assert documented, "branches.md documents no restore at a point"

    def shape(command: str) -> str:
        return re.sub(r"--at \S+", "--at <time>", command)

    assert shape(site_build.RESTORE_EXAMPLE["command"]) in {shape(line) for line in documented}
    rendered = site_build.restore_example()
    assert "Example project" in rendered and site_build.RESTORE_EXAMPLE["command"] in rendered
    assert "2026-10-23T08:40:00Z" in rendered and "Fri 23 Oct 08:40 UTC" in rendered


def test_an_unknown_container_is_refused() -> None:
    """The vocabulary is closed: a container outside `CONTAINERS`, one left
    open, a third level of nesting, a generated block no resolver knows and
    `@chips` naming a row outside the page's list are each a build error; a
    known container renders a `div` around ordinary Markdown."""
    source = site_build.PAGES_ROOT / "x.md"
    render = site_build.render_markdown
    assert (
        render(source, "::: note\nA sentence.\n:::")
        == '<div class="note">\n<p>A sentence.</p>\n</div>\n'
    )
    nested = "::: features\n::: feature\nOne.\n:::\n:::"
    assert '<div class="features">\n<div class="feature">' in render(source, nested)
    for text, why in (
        ("::: banner\nx\n:::", "no container"),
        ("::: note\nx", "not closed"),
        ("::: band\n::: features\n::: feature\nx\n:::\n:::\n:::", "one level"),
        (":::\n", "names one container"),
        ("@ledger-summary", "outside the subset"),
    ):
        with pytest.raises(site_build.SiteError, match=why):
            render(source, text)
    page = site_build.Page(
        source=source,
        route="/x/",
        title="x",
        description="d",
        ledger=("postgresql",),
        body="",
        body_line=5,
    )
    resolve = site_build._blocks_for(page, reality_ledger.load(), site_build.pages())
    assert "chip-beta" in render(source, "@chips postgresql", blocks=resolve)
    for text, why in (
        ("@chips branches", "own ledger"),
        ("@ledger-examples", "home page"),
        ("@plan-summary now", "nothing after"),
        ("@pricing", "outside the subset"),
    ):
        with pytest.raises(site_build.SiteError, match=why):
            render(source, text, blocks=resolve)

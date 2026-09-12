"""`STU-ASSET-001` -- the three files Studio hands a browser, read as files.

**The claim is about what is NOT there.** ADR 0205 decided that Studio ships no
third-party code: no bundler, no framework, no font, no stylesheet or script
fetched from anywhere. A decision like that is kept by nobody noticing it, which
is the state in which it stops being true -- one `<script src>` pointing at a CDN
is a supply chain, and a `@font-face` naming a host is a page that tells a third
party who opened it and when.

So this module reads the directory rather than the page's behaviour. The runtime
proofs next door drive the served page; these two ask what is in the checkout,
which is the question a reviewer of a diff is actually able to answer.

**Comments are stripped before the URL scan** (D1197). A comment explaining why
a URL is absent would otherwise fail the scan that enforces the absence, and the
first person to hit that would delete the explanation. The battery drives both
halves: `https://example` inside a comment must still pass, and the same string
outside one must fail -- a stripper that strips everything passes the first arm
and the second one is what says so.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from agentic_postgres import studio

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

#: The whole of `services/studio/`. Named here rather than globbed, because the
#: claim is that these are the files -- a glob would pass whatever it found.
EXPECTED_FILES = {"index.html", "studio.js", "studio.css", "README.md"}

#: What a scheme looks like on the wire. `://` catches `https://`, `http://` and
#: `//cdn.example` is caught by the separate protocol-relative check below,
#: which a scheme scan alone would miss entirely.
SCHEME = "://"


def strip_js_comments(source: str) -> str:
    """`//` to end of line and `/* … */`, with strings left alone.

    Written as a small state machine rather than a regular expression: a regex
    that removes `//…` removes the middle of any string containing one, which is
    how a scan comes to pass because it deleted the thing it was looking for.
    """
    out: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        character = source[index]
        if character in ("'", '"', "`"):
            quote = character
            out.append(character)
            index += 1
            while index < length:
                out.append(source[index])
                if source[index] == "\\":
                    index += 2
                    if index <= length:
                        out.append(source[index - 1])
                    continue
                if source[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = length if end == -1 else end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = length if end == -1 else end + 2
            continue
        out.append(character)
        index += 1
    return "".join(out)


def strip_css_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)


def strip_html_comments(source: str) -> str:
    return re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)


STRIPPERS = {
    ".js": strip_js_comments,
    ".css": strip_css_comments,
    ".html": strip_html_comments,
    ".md": lambda source: source,
}


class Page(HTMLParser):
    """`index.html`, as tags and attributes rather than as text.

    A text scan for `<script>` answers a different question from the one asked
    here: `<script\\n src=…>` and `<SCRIPT SRC=…>` are both scripts and neither
    matches a naive pattern, and an attribute quoted with a single quote is
    still an attribute. The stdlib parser answers the tag question as a parser;
    the scan above answers the URL question as a scan, and they are not each
    other's substitute.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[dict[str, str | None]] = []
        self.links: list[dict[str, str | None]] = []
        self.styles: list[str] = []
        self.inline_handlers: list[tuple[str, str]] = []
        self.style_attributes: list[str] = []
        self.script_bodies: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        mapping = dict(attrs)
        for name, value in attrs:
            if name.lower().startswith("on"):
                self.inline_handlers.append((tag, name))
            if name.lower() == "style":
                self.style_attributes.append(f"{tag}[style={value!r}]")
        if tag == "script":
            self.scripts.append(mapping)
            self._in_script = True
        if tag == "link":
            self.links.append(mapping)
        if tag == "style":
            self.styles.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script and data.strip():
            self.script_bodies.append(data.strip())


def test_studio_assets_carry_no_third_party_code() -> None:
    """**STU-ASSET-001.** Four files, no manifest, no URL outside a comment.

    Every clause is a way the decision has been lost elsewhere: a `package.json`
    that arrived with a tool nobody meant to keep; a font loaded from a CDN by a
    stylesheet somebody copied; a `//cdn.example/x.js` that is not `https` and
    therefore passes a scheme scan. The directory listing is an equality rather
    than a subset check, so a fifth file has to be argued for here.
    """
    root = studio.ASSET_ROOT
    assert root.is_dir(), f"{root} is not a directory"

    present = {path.name for path in root.iterdir()}
    assert present == EXPECTED_FILES, (
        f"services/studio/ holds {sorted(present)}; the decision is that it holds "
        f"{sorted(EXPECTED_FILES)} and nothing else. A file here is a file a browser may be "
        "handed"
    )
    assert not list(root.glob("package*.json")), "a package manifest appeared under services/studio"
    assert not list(root.glob("*.lock")), "a lockfile appeared under services/studio"
    assert not (root / "node_modules").exists()

    for name in sorted(EXPECTED_FILES):
        path = root / name
        source = path.read_text(encoding="utf-8")
        code = STRIPPERS[path.suffix](source)
        assert SCHEME not in code, (
            f"{name} names a URL outside a comment: "
            f"{code[max(0, code.find(SCHEME) - 60) : code.find(SCHEME) + 40]!r}. Studio's page "
            "fetches nothing from anywhere; the Content-Security-Policy would refuse it, and "
            "a reviewer should not have to rely on that"
        )
        for match in re.finditer(r"""(?:src|href|url)\s*[=(]\s*["']?//""", code):
            pytest.fail(
                f"{name} names a protocol-relative URL at offset {match.start()}, which is an "
                "external reference a scheme scan does not see"
            )


def test_the_page_carries_no_inline_script_and_no_external_reference() -> None:
    """**STU-ASSET-001.** The page, parsed: one script, one stylesheet, no handlers.

    This is the half the Content-Security-Policy is *also* enforcing, and both
    halves exist on purpose. The policy is what a browser applies; this is what a
    reviewer applies, and a page that needed `'unsafe-inline'` to work would fail
    here before anybody tried to loosen the policy to make it work.

    `on*=` attributes are the specific shape: a page whose behaviour lives in
    attributes is a page whose behaviour is in the markup a renderer wrote, and
    every listener in `studio.js` is attached with `addEventListener` instead.
    """
    page = Page()
    page.feed((studio.ASSET_ROOT / "index.html").read_text(encoding="utf-8"))

    assert page.scripts, "index.html loads no script at all; the page would do nothing"
    for script in page.scripts:
        assert script.get("src") == "studio.js", (
            f"a <script> names {script.get('src')!r}; the only script this page loads is its own"
        )
    assert not page.script_bodies, (
        f"index.html carries an inline script: {page.script_bodies[:1]}. The policy is "
        f"{studio.CONTENT_SECURITY_POLICY!r}, under which it would not run -- so a page that "
        "has one is a page somebody is about to loosen the policy for"
    )

    assert page.links, "index.html loads no stylesheet"
    for link in page.links:
        assert link.get("href") == "studio.css", (
            f"a <link> names {link.get('href')!r}; the only stylesheet is its own"
        )
    assert not page.styles, "index.html carries an inline <style> block"
    assert not page.style_attributes, (
        f"index.html carries style attributes: {page.style_attributes}"
    )
    assert not page.inline_handlers, (
        f"index.html carries inline event handlers: {page.inline_handlers}. Every listener is "
        "attached in studio.js with addEventListener"
    )

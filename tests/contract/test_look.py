"""The site and the console share one look (Session 45, ADR 0288).

`UI-TOKENS-001` and `UI-FONTS-001`'s offline half. The two stylesheets carry
ONE token block, byte-equal, light only; every text pair the brief names meets
WCAG AA 4.5:1 by the formula, computed from the tokens as parsed; every
interactive element shows a focus ring; each file fits its own budget (ADR
0295 decision 4: the site's 30,720 B, the console's 40,960 B, each alone).
The two typefaces are the files rig 45a made from `google/fonts` at one pinned
commit -- their sha256 written here from ADR 0288's table, so a changed byte
fails offline (threat item 27) -- each beside its OFL licence, and the only
`url()` either stylesheet holds is one of them.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, site_build

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

SITE_CSS = REPO_ROOT / "site" / "static" / "site.css"
CONSOLE = REPO_ROOT / "services" / "console"
CONSOLE_CSS = CONSOLE / "public" / "app.css"
FONTS = CONSOLE / "public" / "fonts"

#: ADR 0288's output table (rig 45a, `google/fonts` e7db6ca603fd4862010383ff17ffd6cc4ffac1c0).
RECORDED = {
    "schibsted-grotesk.woff2": "b29bc789f8a864ac7e25e71e8b997056fa0bee0fe8799ff56923dc28a2671d06",
    "jetbrains-mono.woff2": "61a4199a67c39cf39239c0b5b3a89f01f53e244c4e4d60d77ae85f557aa16a5b",
    "OFL-schibsted-grotesk.txt": "3b4f3063b6ac7c1e403e2c4a5e8ef3a58190ff83ed7b15af66511858699139ce",
    "OFL-jetbrains-mono.txt": "b2fe5e8987594e9ffd1d2ca52a2f5d73eb8335243893c5d6254b5ad69269591d",
}

#: Every text pair the stylesheets use, as (text token, background token): the
#: brief's colour table, its status chips, the dark surfaces and the warning.
TEXT_PAIRS = (
    ("ink", "ground"), ("ink", "surface"), ("ink", "surface-hover"), ("ink", "accent-wash"),
    ("ink-body", "surface"), ("ink-body", "ground"),
    ("text-2", "ground"), ("text-2", "surface"),
    ("text-3", "ground"), ("text-3", "surface"), ("text-3", "surface-sunk"),
    ("text-3", "surface-hover"),
    ("accent", "surface"), ("accent", "ground"), ("accent", "accent-tint"),
    ("accent", "accent-wash"), ("accent-hover", "surface"), ("accent-hover", "ground"),
    ("surface", "accent"), ("surface", "accent-hover"),
    ("chip-beta-text", "chip-beta-bg"), ("chip-verify-text", "chip-verify-bg"),
    ("chip-planned-text", "chip-planned-bg"), ("chip-absent-text", "chip-absent-bg"),
    ("chip-unmetered-text", "chip-unmetered-bg"),
    ("warning-text", "warning-bg"),
    ("on-ink-text", "ink"), ("on-ink-muted", "ink"), ("on-ink-comment", "ink"),
    ("on-ink-action", "ink"), ("on-ink-action-text", "on-ink-action"),
    # Session 47 Run 9 (the brief's §8): the console's text on the surfaces it
    # inherits -- the navigation's and the callout's sunk ground, a hovered
    # tab, a chosen door card, the warning panels, a step's colour, the
    # numbered step on ink. A rule that sets both colours is read by
    # `test_every_rule_that_sets_both_colours_meets_4_5` instead.
    ("ink-body", "surface-sunk"), ("ink", "surface-sunk"), ("text-2", "surface-sunk"),
    ("accent", "surface-sunk"), ("warning-text", "surface-sunk"),
    ("text-2", "surface-hover"), ("ink-body", "surface-hover"), ("accent", "surface-hover"),
    ("text-2", "accent-wash"), ("text-3", "accent-wash"),
    ("chip-verify-text", "surface"), ("warning-text", "surface"),
    ("ink", "warning-bg"), ("ink-body", "warning-bg"), ("text-2", "warning-bg"),
    ("text-3", "warning-bg"), ("accent", "warning-bg"),
    ("surface", "ink"),
)  # fmt: skip

#: The elements a person can reach with the keyboard on either surface.
FOCUSABLE = ("a", "button", "input", "select", "textarea", "summary")
#: ADR 0295 decision 4: one budget per stylesheet, each measured alone.
SITE_BUDGET = 30_720
CONSOLE_BUDGET = 40_960
BLOCK = re.compile(r"/\* tokens: begin.*?/\* tokens: end \*/\n", re.DOTALL)


def _block(path: Path) -> str:
    found = BLOCK.findall(path.read_text(encoding="utf-8"))
    assert len(found) == 1, f"{path.name} holds {len(found)} token blocks"
    return found[0]


def _tokens() -> dict[str, str]:
    pairs = re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6});", _block(SITE_CSS))
    tokens = dict(pairs)
    assert len(tokens) == len(pairs) and len(tokens) > 40, "the token block parsed to nothing"
    return tokens


def _luminance(colour: str) -> float:
    def channel(value: int) -> float:
        scaled = value / 255
        return scaled / 12.92 if scaled <= 0.04045 else ((scaled + 0.055) / 1.055) ** 2.4

    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast(first: str, second: str) -> float:
    """WCAG 2's contrast ratio of two `#rrggbb` colours."""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _rules(css: str) -> list[tuple[str, str]]:
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return [(s.strip(), b) for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", stripped)]


def _serve() -> Any:
    specification = importlib.util.spec_from_file_location("apg_console_look", CONSOLE / "serve.py")
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# UI-TOKENS-001
# ---------------------------------------------------------------------------


def test_the_two_stylesheets_share_one_token_block() -> None:
    """One block, byte-equal, at the top of each file (after its header
    comment): the builder has no include, so the duplication is guarded."""
    assert _block(SITE_CSS) == _block(CONSOLE_CSS)
    for path in (SITE_CSS, CONSOLE_CSS):
        text = path.read_text(encoding="utf-8")
        before = text[: text.index("/* tokens: begin")]
        assert "{" not in before, f"{path.name} has a rule before its token block"


def test_every_text_pair_meets_4_5() -> None:
    """Every pair, from the tokens as parsed -- so a token edited to a lighter
    grey fails here, not in a person's eyes. The control: a pair known to fail
    (the muted dark text on white) reads below 4.5 by the same formula."""
    tokens = _tokens()
    for text, background in TEXT_PAIRS:
        ratio = contrast(tokens[text], tokens[background])
        assert ratio >= 4.5, f"{text} on {background}: {ratio:.2f}"
    assert contrast(tokens["on-ink-muted"], tokens["surface"]) < 4.5


def test_there_is_no_dark_theme() -> None:
    """Light only (D2825): no `prefers-color-scheme` block and one
    `color-scheme` declaration, `light`, in the shared block."""
    for path in (SITE_CSS, CONSOLE_CSS):
        text = path.read_text(encoding="utf-8")
        assert "prefers-color-scheme" not in text, path.name
        assert re.findall(r"color-scheme:\s*([^;]+);", text) == ["light"], path.name


def test_every_interactive_element_shows_focus() -> None:
    """A rule in each file draws `outline: 2px solid var(--focus)` on
    `:focus-visible` for every focusable element (the brief; rig 45b measured
    that a Tab draws it and a mouse click does not)."""
    for path in (SITE_CSS, CONSOLE_CSS):
        rings = [
            {part.strip() for part in selector.split(",")}
            for selector, body in _rules(path.read_text(encoding="utf-8"))
            if "outline: 2px solid var(--focus)" in body
        ]
        covered = set().union(*rings) if rings else set()
        for element in FOCUSABLE:
            assert f"{element}:focus-visible" in covered, (path.name, element)


def _token(value: str) -> str | None:
    found = re.fullmatch(r"var\(--([a-z0-9-]+)\)", value.strip())
    return found.group(1) if found else None


def _body(body: str) -> dict[str, str]:
    """A rule's declarations, by property (the last wins, as in the cascade)."""
    found: dict[str, str] = {}
    for part in body.split(";"):
        if ":" in part:
            name, _, value = part.partition(":")
            found[name.strip()] = value.strip()
    return found


def _px(value: str | None) -> float | None:
    found = re.fullmatch(r"(\d+(?:\.\d+)?)px", (value or "").strip())
    return float(found.group(1)) if found else None


def test_every_rule_that_sets_both_colours_meets_4_5() -> None:
    """Session 47 Run 9 (the brief's §8): every console rule that sets a text
    colour AND a background, each a token, is a pair -- computed from the
    stylesheet itself, so a rule added later is read without a list. The
    control: the pattern reads a pair from a rule written here."""
    tokens = _tokens()
    pairs = set()
    for selector, body in _rules(CONSOLE_CSS.read_text(encoding="utf-8")):
        declared = _body(body)
        text = _token(declared.get("color", ""))
        ground = _token(declared.get("background", declared.get("background-color", "")))
        if text and ground:
            pairs.add((text, ground, selector))
    assert len(pairs) >= 15, sorted(pairs)
    for text, ground, selector in sorted(pairs):
        ratio = contrast(tokens[text], tokens[ground])
        assert ratio >= 4.5, f"{selector}: {text} on {ground} is {ratio:.2f}"
    probe = _rules(".x { color: var(--text-3); background: var(--surface-hover); }")
    assert (_token(_body(probe[0][1])["color"]), _token(_body(probe[0][1])["background"])) == (
        "text-3", "surface-hover",
    )  # fmt: skip


def test_the_console_rings_whatever_a_script_makes_focusable() -> None:
    """The 2 px ring reaches every element the console's scripts make
    focusable by `tabIndex` (a tab panel) -- `[tabindex]:focus-visible` -- and
    no rule takes an outline away from anything."""
    rings = [
        {part.strip() for part in selector.split(",")}
        for selector, body in _rules(CONSOLE_CSS.read_text(encoding="utf-8"))
        if "outline: 2px solid var(--focus)" in body
    ]
    scripts = "".join(p.read_text(encoding="utf-8") for p in (CONSOLE / "public").glob("*.js"))
    assert "tabIndex: 0" in scripts, "no script makes an element focusable: the guard reads nothing"
    assert "[tabindex]:focus-visible" in set().union(*rings)
    for selector, body in _rules(CONSOLE_CSS.read_text(encoding="utf-8")):
        if "outline" in body and "outline: 2px solid var(--focus)" not in body:
            raise AssertionError(f"{selector} sets an outline: {body.strip()}")


def test_reduced_motion_stops_every_animation() -> None:
    """The brief's §8: with `prefers-reduced-motion` the bar, the skeleton and
    the spinner stop. A class's `animation` outranks `*`, and `*` matches no
    pseudo-element (the bar is `.indeterminate::after`), so the block covers
    `*`, `*::before` and `*::after` with `!important`; and every animation the
    stylesheet runs is one the block reaches."""
    text = CONSOLE_CSS.read_text(encoding="utf-8")
    block = re.search(
        r"@media \(prefers-reduced-motion: reduce\) \{\s*([^{}]+)\{([^{}]*)\}\s*\}", text
    )
    assert block, "no reduced-motion block"
    selectors = {part.strip() for part in block.group(1).split(",")}
    assert selectors == {"*", "*::before", "*::after"}, selectors
    declared = _body(block.group(2))
    assert declared.get("animation") == "none !important", declared
    assert declared.get("transition") == "none !important", declared
    animated = [
        s for s, b in _rules(text) if "animation:" in b and "none" not in _body(b)["animation"]
    ]
    assert len(animated) >= 3, animated  # the spinner, the bar, the skeleton


#: A control by the stylesheet's own selector: its last compound names a
#: button, a summary, a select, a text input, or one of the links drawn as a
#: control. Links inside a sentence are WCAG 2.5.8's inline exception.
CONTROL = re.compile(
    r"(?:^|[\s>])(?:button|summary|select|input|textarea)(?:[.\[:][^\s>]*)?$"
    r"|\.(?:top-link|nav-group a|menu a|head-actions > a(?::not\(\.help-link\))?)$"
)
#: The smallest target WCAG 2.2 AA allows (2.5.8), in CSS pixels.
TARGET_PX = 24


#: The body's line box (`font: 400 15px/1.55`), which a rule that sets no font inherits.
BODY_FONT = (15.0, 1.55)


def _spaced(value: str) -> float | None:
    """A length in px, a `--space-N` token resolved from the token block."""
    token = _token(value)
    if token:
        spaces = dict(re.findall(r"--(space-\d+):\s*(\d+)px;", _block(CONSOLE_CSS)))
        return float(spaces[token]) if token in spaces else None
    return _px(value)


def _block_size(declared: dict[str, str]) -> float | None:
    """The height a rule gives its element: its `height`/`min-height` when it
    sets one above 0, else -- when it sets a vertical padding -- that padding
    plus its line box (its own font, or the body's); None when it sets none."""
    for name in ("height", "min-height"):
        size = _px(declared.get(name))
        if size:
            return size
    padding = declared.get("padding", "").split()
    if not padding:
        return None
    vertical = [_spaced(padding[0]), _spaced(padding[2] if len(padding) > 2 else padding[0])]
    if any(v is None for v in vertical):
        return None
    size, line = BODY_FONT
    font = re.search(r"(\d+(?:\.\d+)?)px/(\d+(?:\.\d+)?)\b", declared.get("font", ""))
    if font:
        size, line = float(font.group(1)), float(font.group(2))
    elif _px(declared.get("font-size")):
        size = _px(declared.get("font-size")) or size
    return sum(v for v in vertical if v is not None) + size * line


def test_every_control_is_at_least_24_px() -> None:
    """WCAG 2.2 AA 2.5.8 (the brief's §8: controls are 32-44 px): every rule
    that sizes a control sizes it to 24 px or more. A checkbox or radio is
    clicked through its label, so ITS label's rule is read (`label.inline`,
    `.segment label`). The control: a 20 px button rule written here fails."""
    rules = _rules(CONSOLE_CSS.read_text(encoding="utf-8"))
    by_selector = {}
    for selector, body in rules:
        for part in selector.split(","):
            by_selector.setdefault(part.strip(), {}).update(_body(body))
    read = 0
    for selector, declared in by_selector.items():
        if "::" in selector or not CONTROL.search(selector):
            continue
        size = _block_size(declared)
        if size is None and re.search(r"(?:^|[\s>])summary$", selector):
            # A summary is no button: unsized, it is one inherited line box.
            size = BODY_FONT[0] * BODY_FONT[1]
        if size is None:
            continue  # every other control inherits `button`'s or `input`'s size
        read += 1
        if size < TARGET_PX and selector.endswith(" input"):
            owner = selector[: -len(" input")]
            label = by_selector.get(owner if owner.endswith("label") else f"{owner} label", {})
            size = _block_size(label)
            assert size is not None and size >= TARGET_PX, (selector, "its label", size)
            continue
        assert size >= TARGET_PX, (selector, size)
    assert read >= 10, read
    # Every checkbox sits in a `label.inline`, which is sized as a target.
    assert (_block_size(by_selector["label.inline"]) or 0) >= TARGET_PX
    scripts = (CONSOLE / "public" / "app.js").read_text(encoding="utf-8")
    assert (
        scripts.count('type: "checkbox"')
        == scripts.count('h("label", { className: "inline" }')
        == 1
    )
    # The control: the reader sees a small target and sizes what it is meant to.
    assert _block_size({"min-height": "20px"}) == 20 and _block_size({}) is None
    assert _block_size({"min-height": "0", "padding": "8px 10px", "font": "500 15px/1.4 x"}) == 37


def test_the_stylesheets_fit_the_budget() -> None:
    """ADR 0295 decision 4 (superseding ADR 0288's joint budget): each file
    alone within its own budget, fonts excluded -- the site's unchanged at
    30,720 B, the console's 40,960 B. Neither borrows what the other leaves."""
    for path, budget in ((SITE_CSS, SITE_BUDGET), (CONSOLE_CSS, CONSOLE_BUDGET)):
        size = path.stat().st_size
        assert 0 < size <= budget, (path.name, size, budget)


# ---------------------------------------------------------------------------
# UI-FONTS-001 (offline)
# ---------------------------------------------------------------------------


def test_the_fonts_are_the_recorded_files() -> None:
    """The four files are exactly ADR 0288's, and nothing else is in `fonts/`."""
    assert sorted(path.name for path in FONTS.iterdir()) == sorted(RECORDED)
    for name, recorded in RECORDED.items():
        data = (FONTS / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == recorded, name
        if name.endswith(".woff2"):
            assert data[:4] == b"wOF2", name


def test_each_font_has_its_licence() -> None:
    """Each typeface ships beside its SIL Open Font License, which names it."""
    for font, family in (("schibsted-grotesk", "Schibsted-Grotesk"),
                         ("jetbrains-mono", "JetBrains Mono")):  # fmt: skip
        assert (FONTS / f"{font}.woff2").is_file()
        licence = (FONTS / f"OFL-{font}.txt").read_text(encoding="utf-8")
        assert licence.startswith("Copyright") and family in licence.splitlines()[0], font
        assert "SIL OPEN FONT LICENSE Version 1.1" in licence, font


def test_every_url_is_one_of_the_fonts() -> None:
    """The site's `url()`s are its build's `/fonts/` copies, the console's its
    own `/console/fonts/` routes; each file names both typefaces once and
    imports nothing -- no other origin, no other file."""
    routes = _serve().ROUTES
    expected = {
        SITE_CSS: ["/fonts/jetbrains-mono.woff2", "/fonts/schibsted-grotesk.woff2"],
        CONSOLE_CSS: ["/console/fonts/jetbrains-mono.woff2",
                      "/console/fonts/schibsted-grotesk.woff2"],
    }  # fmt: skip
    for path, wanted in expected.items():
        text = path.read_text(encoding="utf-8")
        assert "@import" not in text, path.name
        urls = sorted(u.strip("\"'") for u in re.findall(r"url\(([^)]*)\)", text))
        assert urls == wanted and text.count("url(") == 2, (path.name, urls)
    for url in expected[SITE_CSS]:
        assert url.lstrip("/") in site_build.SHARED_ASSETS, url
    for url in expected[CONSOLE_CSS]:
        assert routes[url][1] == "font/woff2", url

"""The public site, built from the repository (Session 43, ADR 0283).

Static files only: the pages are `site/pages/**/*.md`, rendered by a Markdown
SUBSET whose whole grammar is this module (D2663) -- front matter, `#`-`###`
headings, paragraphs, one-level `-` and `1.` lists, fenced code, inline code,
`**strong**`, `*em*`, links, and pipe tables. **Anything else is a build
error naming the file and line, raw HTML included**, and every character of
text is escaped by `html.escape`.

**Every claim comes from the Reality Ledger** (D2662). A page names the rows
it describes in its front matter, and the build refuses one that is not
reachable; it refuses a §59 word (`reality_ledger.FORBIDDEN_WORDS`), and an
operator's command -- `bin/`, `sudo`, `ssh `, `git clone`, `--session`. The
pricing page's body is `plans.PLANS` and `plans.BETA_SENTENCE`, generated, with
no price (D2664); the Ledger page is the YAML's rows (D2674).

**Deterministic**: no timestamp, sorted iteration, `\\n` endings, so two builds
of one tree are byte-equal and every page carries a digest of its inputs.
`bin/build-site.py` is the only caller.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agentic_postgres import REPO_ROOT, naming, plans, reality_ledger

SITE_ROOT = REPO_ROOT / "site"
PAGES_ROOT = SITE_ROOT / "pages"
TEMPLATE = SITE_ROOT / "templates" / "base.html"
STYLESHEET = SITE_ROOT / "static" / "site.css"

#: ADR 0288 (D2814): the assets the site and the console share live ONCE, in
#: the console's tree -- its image bakes only its own build context -- and the
#: build copies exactly these, listed, never globbed, to the same relative
#: paths. The fonts' bytes are pinned by `tests/contract/test_look.py`.
CONSOLE_PUBLIC = REPO_ROOT / "services" / "console" / "public"
SHARED_ASSETS = (
    "fonts/schibsted-grotesk.woff2",
    "fonts/jetbrains-mono.woff2",
    "fonts/OFL-schibsted-grotesk.txt",
    "fonts/OFL-jetbrains-mono.txt",
    "favicon.svg",
)

#: The product's published address for a request for an invitation (D2654):
#: forwarded by Cloudflare Email Routing; the product sends and stores nothing.
INVITATION_ADDRESS = "invite@agenticpostgresql.com"
#: The production control plane's domain, from which the console and the API
#: addresses are DERIVED by `naming`, never typed twice.
CONTROL_DOMAIN = "control.agenticpostgresql.com"
CONSOLE_URL = naming.console_origin(CONTROL_DOMAIN) + "/console/"
CONTROL_ENDPOINT = naming.console_origin(CONTROL_DOMAIN) + "/api" + naming.CONTROL_PATH_SUFFIX
SITE_URL = "https://agenticpostgresql.com"

#: Every `https://` a page may name: the site itself, the control plane, and the
#: repository. Anything else is a third party (D2596, ADR 0283 item 8).
ALLOWED_ORIGINS = (
    "https://agenticpostgresql.com",
    "https://www.agenticpostgresql.com",
    "https://control.agenticpostgresql.com",
    "https://github.com/Virabyan99/agentic-postgres",
    "https://pypi.org/project/agentic-postgres-cli",
)

#: ADR 0283 item 7: the console's policy (ADR 0280) with nothing to connect
#: to and no data URI to draw; `font-src 'self'` since ADR 0288, for the two
#: typefaces the build carries and no host.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self'",
        "connect-src 'none'",
        "font-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)

#: Rig 43c: `_headers` applies to every answer, `/missing` included; Pages'
#: default Referrer-Policy is REPLACED by ours and its `Access-Control-Allow-
#: Origin: *` DETACHED by `!`; its NEL headers cannot be detached (D2687).
HEADERS_FILE = (
    "/*\n"
    f"  Content-Security-Policy: {CONTENT_SECURITY_POLICY}\n"
    "  Referrer-Policy: no-referrer\n"
    "  X-Content-Type-Options: nosniff\n"
    "  X-Frame-Options: DENY\n"
    "  Cross-Origin-Opener-Policy: same-origin\n"
    "  ! Access-Control-Allow-Origin\n"
    "  Cache-Control: public, max-age=300\n"
)

#: What a page may not say (D2662): an operator's command, a clone.
OPERATOR_TEXT = ("bin/", "sudo", "ssh ", "git clone", "--session")
#: What the pricing page may not print (D2664): the beta charges nothing.
PRICE_MARKS = ("$", "€", "£", "/mo", "per month")

#: The site's four sections (ADR 0288, D2823), the same on every page; the
#: wordmark links home, and the console and the invitation stand apart.
NAVIGATION = (
    ("/quickstart/", "Quickstart"),
    ("/docs/", "Docs"),
    ("/pricing/", "Pricing"),
    ("/ledger/", "What exists"),
)
#: The one primary action: a request for an invitation, by mail (D2654).
INVITATION_HREF = f"mailto:{INVITATION_ADDRESS}?subject=Invitation%20request"

#: The documentation's groups (ADR 0288, D2822), in the brief's order, with the
#: SQL editor in *Use a project* after *Connecting* (D2811): every page under
#: `site/pages/docs/` but its index is in exactly one group, and previous /
#: next follow this order. Titles are the pages' own.
DOCS_GROUPS = (
    ("Start", ("/quickstart/", "/docs/getting-started/", "/docs/cli/")),
    ("Use a project", ("/docs/projects/", "/docs/connecting/", "/docs/sql-editor/",
                       "/docs/branches/", "/docs/backups/")),
    ("Watch and plan", ("/docs/plans-and-usage/", "/docs/insights-and-monitoring/")),
    ("Reference", ("/docs/refusals/", "/ledger/")),
)  # fmt: skip

#: A page whose body is generated from data rather than written: the line is
#: replaced by HTML built here, from escaped values. It is the body's FIRST
#: line, and Markdown may follow it (ADR 0288, D2818).
DIRECTIVES = ("@pricing", "@ledger")

#: ADR 0288 (D2821): the layout vocabulary. `::: <name>` opens a
#: `<div class="<name>">` around ordinary Markdown and `:::` closes it, one
#: level of nesting; a name outside this set is refused.
CONTAINERS = (
    "hero", "lead", "actions", "features", "feature", "steps", "band", "band-dark",
    "note", "warning", "doors",
)  # fmt: skip
#: ADR 0288 (D2821): a line that is exactly one of these is replaced by HTML the
#: builder makes from the Ledger, the plan table or the docs groups; `@chips`
#: takes row ids from the page's own `ledger:` list.
BLOCKS = (
    "@restore-example", "@ledger-summary", "@ledger-examples", "@plan-summary",
    "@docs-index", "@chips",
)  # fmt: skip


class SiteError(ValueError):
    """A page the build refuses: the file, the line, and why."""

    def __init__(self, path: Path, line: int, reason: str) -> None:
        super().__init__(f"{_relative(path)}:{line}: {reason}")


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class Page:
    source: Path
    route: str
    title: str
    description: str
    ledger: tuple[str, ...]
    body: str
    body_line: int


# ---------------------------------------------------------------------------
# Reading a page
# ---------------------------------------------------------------------------


def route_of(source: Path) -> str:
    """`index.md` -> `/`, `quickstart.md` -> `/quickstart/`, `docs/index.md`
    -> `/docs/`, `docs/connecting.md` -> `/docs/connecting/`."""
    parts = source.relative_to(PAGES_ROOT).with_suffix("").parts
    if parts[-1] == "index":
        parts = parts[:-1]
    return "/" + "".join(f"{part}/" for part in parts)


def read_page(source: Path) -> Page:
    text = source.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SiteError(source, 1, "a page starts with front matter between two --- lines")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SiteError(source, 1, "the front matter is not closed by a --- line")
    front = yaml.safe_load(text[4:end])
    if not isinstance(front, dict) or set(front) - {"title", "description", "ledger"}:
        raise SiteError(source, 2, "front matter holds title, description and ledger only")
    title, ledger = front.get("title"), front.get("ledger")
    if not isinstance(title, str) or not title:
        raise SiteError(source, 2, "a page has a title")
    if ledger == "*":
        rows: tuple[str, ...] = ("*",)
    elif isinstance(ledger, list) and ledger and all(isinstance(row, str) for row in ledger):
        rows = tuple(ledger)
    else:
        raise SiteError(source, 2, "a page names the Ledger rows it describes")
    body_line = text[: end + 5].count("\n") + 1
    return Page(
        source=source,
        route=route_of(source),
        title=title,
        description=str(front.get("description") or title),
        ledger=rows,
        body=text[end + 5 :],
        body_line=body_line,
    )


def check_page(page: Page, ledger: dict[str, Any]) -> None:
    """D2662's refusals: an unreachable row, a §59 word, an operator command."""
    statuses = {row["id"]: row["status"] for row in ledger["rows"]}
    # `@ledger` is the first line of the one page that names every row, and of
    # no other (ADR 0288: Markdown may follow it).
    first = next((line.strip() for line in page.body.splitlines() if line.strip()), "")
    if (page.ledger == ("*",)) != (first == "@ledger"):
        raise SiteError(page.source, page.body_line, "only the Ledger page names every row")
    for row in () if page.ledger == ("*",) else page.ledger:
        if statuses.get(row) not in reality_ledger.REACHABLE:
            raise SiteError(
                page.source, 2, f"names the Ledger row {row!r}, which is {statuses.get(row)}"
            )
    for number, line in enumerate(page.body.splitlines(), start=page.body_line):
        lowered = line.lower()
        for word in reality_ledger.FORBIDDEN_WORDS:
            if re.search(rf"(?<![a-z0-9-]){re.escape(word)}(?![a-z0-9-])", lowered):
                raise SiteError(page.source, number, f"uses {word!r}")
        for operator in OPERATOR_TEXT:
            if operator in line:
                raise SiteError(page.source, number, f"holds an operator's command ({operator!r})")


# ---------------------------------------------------------------------------
# The subset
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,3}) (.+)$")
_BULLET = re.compile(r"^- (.+)$")
_ORDERED = re.compile(r"^\d+\. (.+)$")
_FENCE = re.compile(r"^```([a-z]*)$")
_CODE_SPAN = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_RAW = re.compile(r"<[A-Za-z!/?]")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _href(source: Path, number: int, href: str) -> str:
    if href.startswith("mailto:"):
        if href.split("?", 1)[0] != f"mailto:{INVITATION_ADDRESS}":
            raise SiteError(source, number, f"a mailto: names {href!r}, not {INVITATION_ADDRESS}")
        return href
    if href.startswith("https://"):
        if not any(href == origin or href.startswith(origin + "/") for origin in ALLOWED_ORIGINS):
            raise SiteError(source, number, f"links to another origin: {href}")
        return href
    if href.startswith(("#", "/")) and not href.startswith("//"):
        return href
    raise SiteError(
        source, number, f"a link is relative, #, https:// or the invitation mailto: {href}"
    )


def inline(source: Path, number: int, text: str) -> str:
    """Code spans first (their text escaped and nothing else), then the rest:
    refused if it holds raw HTML, escaped, then links, strong and em."""
    pieces = _CODE_SPAN.split(text)
    out: list[str] = []
    for index, piece in enumerate(pieces):
        if index % 2:
            out.append(f"<code>{html.escape(piece)}</code>")
            continue
        if _RAW.search(piece):
            raise SiteError(source, number, "raw HTML is refused; write the subset")
        escaped = html.escape(piece)

        def link(match: re.Match[str]) -> str:
            href = _href(source, number, html.unescape(match.group(2)))
            return f'<a href="{html.escape(href)}">{match.group(1)}</a>'

        escaped = _LINK.sub(link, escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"(?<![*\w])\*([^*\s][^*]*)\*(?![*\w])", r"<em>\1</em>", escaped)
        out.append(escaped)
    return "".join(out)


def _table(source: Path, first: int, rows: list[str]) -> str:
    def cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    if len(rows) < 2 or not re.fullmatch(r"\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*\|?", rows[1].strip()):
        raise SiteError(source, first, "a table is a header row, a --- row, then rows")
    head = "".join(f"<th>{inline(source, first, cell)}</th>" for cell in cells(rows[0]))
    body = "".join(
        "<tr>"
        + "".join(f"<td>{inline(source, first + 2 + i, cell)}</td>" for cell in cells(line))
        + "</tr>"
        for i, line in enumerate(rows[2:])
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


_CONTAINER = re.compile(r"^::: ([a-z][a-z-]*)$")


def _container_end(source: Path, lines: list[str], start: int, first_line: int) -> int:
    """The index of the `:::` closing the container opened at `start`."""
    depth = 0
    for index in range(start, len(lines)):
        if _CONTAINER.match(lines[index]):
            depth += 1
        elif lines[index] == ":::":
            depth -= 1
            if depth == 0:
                return index
    raise SiteError(source, first_line + start, "a ::: container is not closed")


def render_markdown(
    source: Path,
    text: str,
    first_line: int = 1,
    *,
    blocks: Any = None,
    depth: int = 0,
) -> str:
    """The subset, block by block. Unknown shapes are refused, never guessed.

    `blocks(source, number, line)` resolves a generated block's line (ADR 0288);
    without it, such a line is outside the subset. A container nests one level.
    """
    lines = text.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        number = first_line + index
        if not line.strip():
            index += 1
            continue
        if line.startswith(":::"):
            opened = _CONTAINER.match(line)
            if not opened:
                raise SiteError(source, number, f"a ::: line names one container: {line[:40]!r}")
            if opened.group(1) not in CONTAINERS:
                raise SiteError(source, number, f"no container is called {opened.group(1)!r}")
            if depth >= 2:
                raise SiteError(source, number, "containers nest one level deep")
            end = _container_end(source, lines, index, first_line)
            inner = render_markdown(source, "\n".join(lines[index + 1 : end]), number + 1,
                                    blocks=blocks, depth=depth + 1)  # fmt: skip
            out.append(f'<div class="{opened.group(1)}">\n{inner}</div>')
            index = end + 1
            continue
        if line.startswith("@"):
            if blocks is None or line.split(" ", 1)[0] not in BLOCKS:
                raise SiteError(source, number, f"outside the subset: {line.strip()[:40]!r}")
            out.append(blocks(source, number, line))
            index += 1
            continue
        fence = _FENCE.match(line)
        if fence:
            end = index + 1
            while end < len(lines) and lines[end] != "```":
                end += 1
            if end == len(lines):
                raise SiteError(source, number, "a code fence is not closed")
            language = f' class="language-{fence.group(1)}"' if fence.group(1) else ""
            code = html.escape("\n".join(lines[index + 1 : end]))
            out.append(f"<pre><code{language}>{code}</code></pre>")
            index = end + 1
            continue
        heading = _HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            out.append(f'<h{level} id="{slug(title)}">{inline(source, number, title)}</h{level}>')
            index += 1
            continue
        if line.startswith("|"):
            end = index
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            out.append(_table(source, number, lines[index:end]))
            index = end
            continue
        for pattern, tag in ((_BULLET, "ul"), (_ORDERED, "ol")):
            if pattern.match(line):
                items = []
                while index < len(lines) and pattern.match(lines[index]):
                    item = pattern.match(lines[index]).group(1)  # type: ignore[union-attr]
                    items.append(f"<li>{inline(source, first_line + index, item)}</li>")
                    index += 1
                out.append(f"<{tag}>{''.join(items)}</{tag}>")
                break
        else:
            # An indent, a quote, another bullet form or an unspaced heading is
            # Markdown this subset does not have -- refused, never guessed.
            if line.startswith((" ", "\t", ">", "* ", "+ ", "#")) or line in DIRECTIVES:
                raise SiteError(source, number, f"outside the subset: {line.strip()[:40]!r}")
            paragraph = []
            while index < len(lines) and lines[index].strip() and not _starts_block(lines[index]):
                paragraph.append(lines[index].strip())
                index += 1
            out.append(f"<p>{inline(source, number, ' '.join(paragraph))}</p>")
    return "\n".join(out) + "\n"


def _starts_block(line: str) -> bool:
    return bool(
        _FENCE.match(line) or _HEADING.match(line) or line.startswith(("|", ":::", "@"))
        or _BULLET.match(line) or _ORDERED.match(line)
    )  # fmt: skip


# ---------------------------------------------------------------------------
# The generated bodies
# ---------------------------------------------------------------------------

#: A plan's status, in words (D2664).
PLAN_STATUS_WORDS = {
    "active": "Every organisation has it during the beta.",
    "unavailable_during_beta": (
        "Not available during the beta. Notify me in the console records that you asked."
    ),
}


def _value(value: Any) -> str:
    if isinstance(value, tuple):
        return ", ".join(value)
    return str(value)


def pricing_body() -> str:
    """The two plans' entitlements from `plans.PLANS`, and the beta sentence."""
    parts = [f'<p class="lead">{html.escape(plans.BETA_SENTENCE)}</p>']
    for name in plans.PLAN_NAMES:
        plan = plans.PLANS[name]
        # The fourth cell's text is the live proof's (D2818); its class only
        # draws the marker.
        rows = "".join(
            "<tr>"
            f"<td>{html.escape(entitlement_name.replace('_', ' '))}</td>"
            f"<td>{html.escape(_value(entitlement.value))}</td>"
            f"<td>{html.escape('' if entitlement.unit == 'text' else entitlement.unit)}</td>"
            + ('<td class="enforced">enforced</td>' if entitlement.enforced
               else '<td class="shown">shown, not enforced</td>')
            + "</tr>"
            for entitlement_name, entitlement in plan.entitlements.items()
        )  # fmt: skip
        parts.append(
            f'<section class="plan plan-{slug(name)}">'
            f'<h2 id="{slug(name)}">{html.escape(name.capitalize())}</h2>'
            '<p class="plan-status">'
            f"{html.escape(PLAN_STATUS_WORDS.get(plan.status, plan.status))}</p>"
            "<table><thead><tr><th>Limit</th><th>Value</th><th>Unit</th><th></th></tr></thead>"
            f"<tbody>{rows}</tbody></table></section>"
        )
    return "\n".join(parts) + "\n"


#: A Ledger status, in words (D2674).
STATUS_WORDS = {
    "available": "available",
    "beta": "in the beta",
    "trial": "being verified",
    "planned": "planned",
    "not_metered": "not metered",
    "not_offered": "not offered",
}


#: One chip class per Ledger status (ADR 0288, D2816): the words are
#: `STATUS_WORDS`, the colours the stylesheet's; `available` has the beta's.
CHIP_CLASSES = {status: "chip-" + status.replace("_", "-") for status in reality_ledger.STATUSES}


def chip(status: str) -> str:
    """A status, as a chip: `STATUS_WORDS`' text, never typed in a page."""
    return f'<span class="chip {CHIP_CLASSES[status]}">{html.escape(STATUS_WORDS[status])}</span>'


def _counts(ledger: dict[str, Any]) -> list[tuple[str, int]]:
    """Each status with at least one row, in `reality_ledger.STATUSES` order."""
    counted = {status: 0 for status in reality_ledger.STATUSES}
    for row in ledger["rows"]:
        counted[row["status"]] += 1
    return [(status, n) for status, n in counted.items() if n]


def _text(row: dict[str, Any]) -> str:
    return " ".join(row["customer_text"].split())


def ledger_body(ledger: dict[str, Any]) -> str:
    """Every row in YAML order; its status a chip INSIDE the *Today* cell, so the
    row still starts `<tr><td>{concept}</td>` (D2819). Before it, a radio per
    status present and *All*: `site.css`'s `:has()` rules hide the other rows,
    and without `:has()` every row shows. No script."""
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['concept'])}</td>"
        f"<td>{chip(row['status'])}</td>"
        f"<td>{html.escape(_text(row))}</td>"
        "</tr>"
        for row in ledger["rows"]
    )
    total = len(ledger["rows"])
    choices = [("all", f"all, {total}", True)] + [
        (CHIP_CLASSES[status].removeprefix("chip-"), f"{STATUS_WORDS[status]}, {n}", False)
        for status, n in _counts(ledger)
    ]
    radios = "".join(
        f'<input type="radio" name="status" id="status-{key}"{" checked" if checked else ""}>'
        f'<label for="status-{key}">{html.escape(text)}</label>'
        for key, text, checked in choices
    )
    return (
        "<p>Every concept this product names, and what it is today. A concept is in the "
        "beta only when a test that proves it passed against the running service.</p>"
        f'<div class="filter" role="group" aria-label="Show">{radios}</div>'
        f'<div class="count">{total} concepts</div>'
        '<div class="ledger-table">'
        "<table><thead><tr><th>Concept</th><th>Today</th><th>What you get</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>\n"
    )


def ledger_summary(ledger: dict[str, Any]) -> str:
    """`@ledger-summary` (D2817): the heading's two numbers, a stacked bar whose
    segments' widths ARE the counts, and a legend -- only for a status with at
    least one row, so the counts sum to the total."""
    counts = _counts(ledger)
    total = len(ledger["rows"])
    working = sum(n for status, n in counts if status in ("available", "beta"))
    title = f"{total} concepts. {working} of them work today."
    rects, x = [], 0
    for status, n in counts:
        rects.append(f'<rect class="seg seg-{CHIP_CLASSES[status].removeprefix("chip-")}" '
                     f'x="{x}" y="0" width="{n}" height="1"/>')  # fmt: skip
        x += n
    label = "; ".join(f"{STATUS_WORDS[status]}, {n}" for status, n in counts)
    legend = "".join(
        f'<li><span class="swatch seg-{CHIP_CLASSES[status].removeprefix("chip-")}"></span>'
        f"{html.escape(STATUS_WORDS[status])}, {n}</li>"
        for status, n in counts
    )
    return (
        f'<h2 id="{slug(title)}">{html.escape(title)}</h2>\n'
        f'<div class="status-bar"><svg viewBox="0 0 {total} 1" preserveAspectRatio="none" '
        f'width="100%" height="28" role="img" aria-label="{html.escape(label)}">'
        f"{''.join(rects)}</svg></div>\n"
        f'<ul class="legend">{legend}</ul>\n'
    )


def ledger_examples(ledger: dict[str, Any]) -> str:
    """`@ledger-examples` (D2843): per status present, the FIRST row in YAML
    order whose concept and text hold no forbidden word -- from the Ledger, so
    an example cannot claim more than the Ledger does."""
    picked = []
    for status, _ in _counts(ledger):
        for row in ledger["rows"]:
            said = f"{row['concept']} {_text(row)}".lower()
            if row["status"] == status and not any(
                w in said for w in reality_ledger.FORBIDDEN_WORDS
            ):
                picked.append(row)
                break
    items = "".join(
        f'<li><span class="concept">{html.escape(row["concept"])}</span>{chip(row["status"])}'
        f'<span class="what">{html.escape(_text(row))}</span></li>'
        for row in picked
    )
    return f'<ul class="ledger-examples">{items}</ul>\n'


#: `@plan-summary`'s four rows (D2821): the plan table's key, the label, and
#: whether the unit is printed with the value.
PLAN_SUMMARY = (
    ("projects_active", "Active projects", False),
    ("branches_total", "Branches per project", False),
    ("compute_profiles", "Compute sizes", False),
    ("storage_gb", "Storage", True),
)


def plan_summary() -> str:
    """Four of the plan table's rows, Free beside Premium, generated."""
    head = "".join(f"<th>{html.escape(name.capitalize())}</th>" for name in plans.PLAN_NAMES)
    rows = []
    for key, label, with_unit in PLAN_SUMMARY:
        cells = []
        for name in plans.PLAN_NAMES:
            entitlement = plans.PLANS[name].entitlements[key]
            value = _value(entitlement.value) + (f" {entitlement.unit}" if with_unit else "")
            cells.append(f"<td>{html.escape(value)}</td>")
        rows.append(f"<tr><td>{html.escape(label)}</td>{''.join(cells)}</tr>")
    return (
        '<table class="plan-summary"><thead><tr><th>Limit</th>'
        f"{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>\n"
    )


#: `@restore-example` (D2831): a static example, said to be one, whose command
#: is `docs/branches.md`'s line with the marker's time.
RESTORE_EXAMPLE = {
    "project": "shop-backend",
    "from": "Mon 19 Oct 02:00 UTC",
    "to": "Fri 23 Oct 08:40 UTC",
    "command": "apg branch create --branch before --password-dir ./branches "
    "--at 2026-10-23T08:40:00Z --wait",
}


def restore_example() -> str:
    """The home page's instrument: an example project header with a `ready`
    chip, its two doors, the hatched restore window and the restore command --
    SVG by presentation attributes and classes only (D2820)."""
    example = RESTORE_EXAMPLE
    window = (
        f"Restore window from {example['from']} to {example['to']}; "
        f"the restore point marked at {example['to']}"
    )
    return (
        '<div class="instrument">\n'
        '<div class="instrument-caption">Example project</div>\n'
        f'<div class="instrument-head"><span class="project-name">{example["project"]}</span>'
        '<span class="chip state-ready">ready</span></div>\n'
        '<div class="spec-tiles">'
        '<div class="tile"><span class="tile-label">Pooled</span>'
        "<code>pool.[domain]:5432</code></div>"
        '<div class="tile"><span class="tile-label">Direct</span>'
        "<code>direct.[domain]:5432</code></div>"
        "</div>\n"
        f'<svg class="window" viewBox="0 0 100 24" preserveAspectRatio="none" width="100%" '
        f'height="24" role="img" aria-label="{html.escape(window)}">'
        '<defs><pattern id="restore-hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><rect class="stripe-b" width="6" height="6"/>'
        '<rect class="stripe-a" width="3" height="6"/></pattern></defs>'
        '<rect class="window-frame" x="0.5" y="2" width="99" height="20" rx="2" '
        'fill="url(#restore-hatch)"/>'
        '<rect class="window-tick" x="0.5" y="0" width="1" height="24"/>'
        '<rect class="window-marker" x="98.5" y="0" width="1" height="24"/></svg>\n'
        '<div class="window-labels">'
        f"<span>Last full backup<br>{example['from']}</span>"
        f"<span>Latest restore point<br>{example['to']}</span></div>\n"
        '<div class="restore-at">'
        f'<div class="restore-caption">Restore into a new branch at {example["to"]}</div>'
        f'<pre class="terminal"><code>{html.escape(example["command"])}</code></pre>'
        '<div class="restore-caption">The project itself is never overwritten.</div>'
        "</div>\n</div>\n"
    )


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def digest_inputs() -> list[Path]:
    """Everything the built bytes depend on, so the live site can be compared
    with the commit it claims to be (`SITE-LIVE-001`)."""
    files = sorted(path for path in SITE_ROOT.rglob("*") if path.is_file())
    return [
        *files,
        *(CONSOLE_PUBLIC / relative for relative in SHARED_ASSETS),
        REPO_ROOT / "services" / "auth-api" / "app" / "plans.py",
        reality_ledger.LEDGER_PATH,
        REPO_ROOT / "VERSION",
        Path(__file__),
    ]


def digest() -> str:
    hashed = hashlib.sha256()
    for path in digest_inputs():
        relative = path.relative_to(REPO_ROOT).as_posix()
        hashed.update(relative.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return hashed.hexdigest()


def pages() -> list[Page]:
    return [read_page(path) for path in sorted(PAGES_ROOT.rglob("*.md"))]


#: The mark (ADR 0288, D2820): two doors in a rounded square, by presentation
#: attributes only -- the same markup as the console's two pages.
LOGO = (
    '<svg class="logo" width="28" height="28" viewBox="0 0 28 28" aria-hidden="true" '
    'focusable="false"><rect x="1" y="1" width="26" height="26" rx="6" fill="none" '
    'stroke="#142027" stroke-width="2"/><rect x="8" y="7" width="4" height="14" rx="1" '
    'fill="#0B6B4F"/><rect x="16" y="7" width="4" height="14" rx="1" fill="#142027"/></svg>'
)
_HEADING_ID = re.compile(r'<(h[1-3]) id="([^"]*)">')
_H2 = re.compile(r'<h2 id="([^"]+)">(.*?)</h2>')


def docs_order() -> tuple[str, ...]:
    """The groups' pages in order: the sidebar's, and previous / next's."""
    return tuple(route for _, routes in DOCS_GROUPS for route in routes)


def _is_docs(route: str) -> bool:
    return route == "/quickstart/" or route.startswith("/docs/")


def _current(href: str, route: str) -> str:
    """D2823: a section is current when its route is a prefix of the page's."""
    return ' aria-current="page"' if href != "/" and route.startswith(href) else ""


def _here(href: str, route: str) -> str:
    """The sidebar's current page: an exact route."""
    return ' aria-current="page"' if href == route else ""


def check_groups(all_pages: list[Page]) -> None:
    """Every docs page but the index is in exactly one group, and every group
    entry is a page (D2822)."""
    routes = {page.route for page in all_pages}
    docs = {page.route for page in all_pages if page.route.startswith("/docs/")} - {"/docs/"}
    where = PAGES_ROOT / "docs" / "index.md"
    order = docs_order()
    for route in order:
        if order.count(route) != 1:
            raise SiteError(where, 1, f"{route} is in more than one documentation group")
        if route not in routes:
            raise SiteError(where, 1, f"the documentation groups name {route}, which is no page")
    missing = sorted(docs - set(order))
    if missing:
        raise SiteError(where, 1, f"no documentation group holds {missing}")


def _header(route: str, descriptions: dict[str, str]) -> str:
    links = "".join(
        f'<a href="{html.escape(href)}"{_current(href, route)}>{html.escape(text)}</a>'
        for href, text in NAVIGATION
    )
    items = "".join(
        f'<li><a href="{html.escape(href)}"{_current(href, route)}><span>{html.escape(text)}</span>'
        f'<span class="menu-note">{html.escape(descriptions[href])}</span></a></li>'
        for href, text in (*NAVIGATION, (CONSOLE_URL, "Console"))
    )
    button = f'<a class="button" href="{html.escape(INVITATION_HREF)}">Request an invitation</a>'
    return (
        f'<a class="brand" href="/">{LOGO}Agentic Postgres</a>'
        f'<nav class="primary" aria-label="Main">{links}</nav>'
        f'<div class="header-actions"><a class="console-link" href="{CONSOLE_URL}">Console</a>'
        f"{button}</div>"
        f'<details class="menu"><summary>Menu</summary><ul>{items}</ul>{button}</details>'
    )


def _footer(version: str, titles: dict[str, str]) -> str:
    columns = (
        ("Start", DOCS_GROUPS[0][1]),
        ("Use a project", DOCS_GROUPS[1][1]),
        ("Understand it", ("/pricing/", "/ledger/", "/docs/refusals/")),
    )
    parts = [
        f'<div class="footer-column"><span class="footer-title">{html.escape(title)}</span><ul>'
        + "".join(f'<li><a href="{r}">{html.escape(titles[r])}</a></li>' for r in routes)
        + "</ul></div>"
        for title, routes in columns
    ]
    parts.append(
        '<div class="footer-column"><span class="footer-title">Contact</span><ul>'
        f'<li><a href="mailto:{INVITATION_ADDRESS}">{INVITATION_ADDRESS}</a></li>'
        f'<li><a href="{CONSOLE_URL}">Console</a></li></ul></div>'
    )
    return (
        f'<div class="footer-columns">{"".join(parts)}</div>'
        f'<div class="footer-rule">Agentic Postgres {html.escape(version)}, beta</div>'
    )


def _layout(template: str, *, title: str, description: str, header: str, kind: str,
            body: str, site_digest: str, version: str, footer: str) -> str:  # fmt: skip
    values = {
        "title": html.escape(title),
        "description": html.escape(description),
        "digest": site_digest,
        "version": html.escape(version),
        "header": header,
        "layout": kind,
        "body": body,
        "feedback": (
            "Something here wrong or missing? Write to "
            f'<a href="mailto:{INVITATION_ADDRESS}">{INVITATION_ADDRESS}</a>'
        ),
        "footer": footer,
    }
    out = template
    for name, value in values.items():
        out = out.replace("{{" + name + "}}", value)
    return out


def unique_ids(body: str) -> str:
    """Heading ids made unique within a page: the slug, then `-2`, `-3` ..."""
    used: set[str] = set()

    def rename(match: re.Match[str]) -> str:
        base, number = match.group(2), 1
        candidate = base
        while candidate in used:
            number += 1
            candidate = f"{base}-{number}"
        used.add(candidate)
        return f'<{match.group(1)} id="{candidate}">'

    return _HEADING_ID.sub(rename, body)


def chips_for(rows: tuple[str, ...], ledger: dict[str, Any]) -> str:
    """The named rows' concepts, each with its status chip."""
    by_id = {row["id"]: row for row in ledger["rows"]}
    items = "".join(
        f'<li><span class="concept">{html.escape(by_id[row]["concept"])}</span>'
        f"{chip(by_id[row]['status'])}</li>"
        for row in rows
    )
    return f'<ul class="chips">{items}</ul>\n'


def docs_index(all_pages: list[Page]) -> str:
    """`@docs-index`: the four groups, each page with its own description."""
    by_route = {page.route: page for page in all_pages}
    parts = []
    for group, routes in DOCS_GROUPS:
        items = "".join(
            f'<li><a href="{route}">{html.escape(by_route[route].title)}</a>'
            f'<span class="description">{html.escape(by_route[route].description)}</span></li>'
            for route in routes
        )
        parts.append(f'<h2 id="{slug(group)}">{html.escape(group)}</h2>\n'
                     f'<ul class="docs-index">{items}</ul>')  # fmt: skip
    return "\n".join(parts) + "\n"


def _blocks_for(page: Page, ledger: dict[str, Any], all_pages: list[Page]) -> Any:
    """The resolver of a page's generated blocks (ADR 0288, D2821)."""

    def resolve(source: Path, number: int, line: str) -> str:
        name, _, rest = line.partition(" ")
        if name != "@chips" and rest:
            raise SiteError(source, number, f"{name} takes nothing after it")
        if name == "@restore-example":
            return restore_example()
        if name == "@ledger-summary":
            return ledger_summary(ledger)
        if name == "@ledger-examples":
            if page.route != "/":
                raise SiteError(source, number, "@ledger-examples is the home page's alone")
            return ledger_examples(ledger)
        if name == "@plan-summary":
            return plan_summary()
        if name == "@docs-index":
            return docs_index(all_pages)
        rows = tuple(rest.split())
        if not rows or any(row not in page.ledger for row in rows):
            raise SiteError(source, number, "@chips names rows of the page's own ledger: list")
        return chips_for(rows, ledger)

    return resolve


def _docs_layout(page: Page, body: str, ledger: dict[str, Any], titles: dict[str, str]) -> str:
    """D2822: the sidebar from `DOCS_GROUPS`, the article -- breadcrumb, the
    page's own `#` heading, the lead, its status chips, the body, previous /
    next -- and *On this page* from the body's `h2`s."""
    head, closed, rest = body.partition("</h1>\n")
    if not closed:
        raise SiteError(
            page.source, page.body_line, "a documentation page starts with its # heading"
        )
    group = next((name for name, routes in DOCS_GROUPS if page.route in routes), None)
    sidebar = "".join(
        f'<div class="sidebar-group"><span class="group-title">{html.escape(name)}</span><ul>'
        + "".join(
            f'<li><a href="{route}"{_here(route, page.route)}>{html.escape(titles[route])}</a></li>'
            for route in routes
        )
        + "</ul></div>"
        for name, routes in DOCS_GROUPS
    ) + (
        '<div class="sidebar-api"><span class="group-title">Management API</span>'
        f"<code>{html.escape(CONTROL_ENDPOINT)}</code></div>"
    )
    crumb = (
        '<div class="breadcrumb"><a href="/docs/">Docs</a>'
        + (f" / {html.escape(group)}" if group else "")
        + "</div>\n"
    )
    links = []
    order = docs_order()
    if page.route in order:
        at = order.index(page.route)
        for caption, other in (("Previous", at - 1), ("Next", at + 1)):
            if 0 <= other < len(order):
                route = order[other]
                links.append(
                    f'<a class="{caption.lower()}" href="{route}"><span class="caption">{caption}'
                    f'</span><span class="title">{html.escape(titles[route])}</span></a>'
                )
    pager = (
        f'<nav class="prev-next" aria-label="Previous and next">{"".join(links)}</nav>\n'
        if links else ""
    )  # fmt: skip
    sections = _H2.findall(rest)
    toc = (
        '<nav class="toc" aria-label="On this page"><span class="group-title">On this page</span>'
        "<ul>" + "".join(f'<li><a href="#{anchor}">{text}</a></li>' for anchor, text in sections)
        + "</ul></nav>"
        if sections else ""
    )  # fmt: skip
    chips = chips_for(page.ledger, ledger) if page.ledger != ("*",) else ""
    return (
        '<div class="docs-layout">'
        f'<nav class="sidebar" aria-label="Documentation">{sidebar}</nav>\n'
        f'<article>\n{crumb}{head}{closed}<p class="lead">{html.escape(page.description)}</p>\n'
        f"{chips}{rest}{pager}</article>\n{toc}</div>\n"
    )


def _check_anchors(rendered: dict[str, tuple[Page, str]]) -> None:
    """A link to `#id` -- on its own page or another -- names an id that exists."""
    ids = {route: set(re.findall(r'\bid="([^"]+)"', text)) for route, (_, text) in rendered.items()}
    for route, (page, text) in rendered.items():
        for href in re.findall(r'href="([^"]*#[^"]*)"', text):
            path, _, anchor = href.partition("#")
            target = path or route
            if target not in ids or anchor not in ids[target]:
                raise SiteError(page.source, page.body_line, f"links to {href}, which names no id")


def build() -> dict[str, bytes]:
    """`{relative path: bytes}` for the whole site, or `SiteError`."""
    ledger = reality_ledger.load()
    template = TEMPLATE.read_text(encoding="utf-8")
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    site_digest = digest()
    all_pages = pages()
    check_groups(all_pages)
    titles = {page.route: page.title for page in all_pages}
    by_route = {page.route: page for page in all_pages}
    steps = sum(1 for line in by_route["/quickstart/"].body.splitlines() if line.startswith("## "))
    documents = sum(1 for route in titles if route.startswith("/docs/") and route != "/docs/")
    descriptions = {
        "/quickstart/": f"{steps} steps",
        "/docs/": f"{documents} pages",
        "/pricing/": "Free in the beta",
        "/ledger/": f"{len(ledger['rows'])} concepts",
        CONSOLE_URL: "for members",
    }
    footer = _footer(version, titles)
    rendered: dict[str, tuple[Page, str]] = {}
    files: dict[str, bytes] = {}
    for page in all_pages:
        check_page(page, ledger)
        lines = page.body.split("\n")
        first = next((i for i, line in enumerate(lines) if line.strip()), 0)
        blocks = _blocks_for(page, ledger, all_pages)
        if lines[first].strip() in DIRECTIVES:
            generated = (
                pricing_body() if lines[first].strip() == "@pricing" else ledger_body(ledger)
            )
            rest = "\n".join(lines[first + 1 :])
            body = f"<h1>{html.escape(page.title)}</h1>\n" + generated + (
                render_markdown(page.source, rest, page.body_line + first + 1, blocks=blocks)
                if rest.strip() else ""
            )  # fmt: skip
        else:
            body = render_markdown(page.source, page.body, page.body_line, blocks=blocks)
        body = unique_ids(body)
        if _is_docs(page.route):
            body = _docs_layout(page, body, ledger, titles)
        kind = "home" if page.route == "/" else "docs" if _is_docs(page.route) else "page"
        rendered[page.route] = (page, body)
        target = page.route.strip("/")
        name = f"{target}/index.html" if target else "index.html"
        files[name] = _layout(
            template, title=page.title, description=page.description,
            header=_header(page.route, descriptions), kind=kind, body=body,
            site_digest=site_digest, version=version, footer=footer,
        ).encode("utf-8")  # fmt: skip
    _check_anchors(rendered)
    files["404.html"] = _layout(
        template, title="Not found", description="This page does not exist.",
        header=_header("", descriptions), kind="page",
        body=('<h1>Not found</h1>\n<p>Nothing is published at this address. Start from '
              '<a href="/">the home page</a> or <a href="/docs/">the documentation</a>.</p>\n'),
        site_digest=site_digest, version=version, footer=footer,
    ).encode("utf-8")  # fmt: skip
    files["site.css"] = STYLESHEET.read_bytes()
    for relative in SHARED_ASSETS:
        files[relative] = (CONSOLE_PUBLIC / relative).read_bytes()
    files["_headers"] = HEADERS_FILE.encode("utf-8")
    pricing = files.get("pricing/index.html", b"").decode("utf-8")
    for mark in PRICE_MARKS:
        if mark in pricing:
            raise SiteError(PAGES_ROOT / "pricing.md", 1, f"the pricing page prints {mark!r}")
    return dict(sorted(files.items()))

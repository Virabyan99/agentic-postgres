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

NAVIGATION = (
    ("/", "Home"),
    ("/quickstart/", "Quickstart"),
    ("/docs/", "Documentation"),
    ("/pricing/", "Pricing"),
    ("/ledger/", "What exists"),
    (CONSOLE_URL, "Console"),
)

#: A page whose body is generated from data rather than written: the line is
#: replaced by HTML built here, from escaped values.
DIRECTIVES = ("@pricing", "@ledger")


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
    if page.ledger == ("*",):
        if page.body.strip() != "@ledger":
            raise SiteError(page.source, page.body_line, "only the Ledger page names every row")
    else:
        for row in page.ledger:
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


def render_markdown(source: Path, text: str, first_line: int = 1) -> str:
    """The subset, block by block. Unknown shapes are refused, never guessed."""
    lines = text.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        number = first_line + index
        if not line.strip():
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
        _FENCE.match(line) or _HEADING.match(line) or line.startswith("|")
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
    parts = [f"<p>{html.escape(plans.BETA_SENTENCE)}</p>"]
    for name in plans.PLAN_NAMES:
        plan = plans.PLANS[name]
        rows = "".join(
            "<tr>"
            f"<td>{html.escape(entitlement_name.replace('_', ' '))}</td>"
            f"<td>{html.escape(_value(entitlement.value))}</td>"
            f"<td>{html.escape('' if entitlement.unit == 'text' else entitlement.unit)}</td>"
            f"<td>{'enforced' if entitlement.enforced else 'shown, not enforced'}</td>"
            "</tr>"
            for entitlement_name, entitlement in plan.entitlements.items()
        )
        parts.append(
            f'<h2 id="{slug(name)}">{html.escape(name.capitalize())}</h2>'
            f"<p>{html.escape(PLAN_STATUS_WORDS.get(plan.status, plan.status))}</p>"
            "<table><thead><tr><th>Limit</th><th>Value</th><th>Unit</th><th></th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
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


def ledger_body(ledger: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['concept'])}</td>"
        f"<td>{html.escape(STATUS_WORDS[row['status']])}</td>"
        f"<td>{html.escape(' '.join(row['customer_text'].split()))}</td>"
        "</tr>"
        for row in ledger["rows"]
    )
    return (
        "<p>Every concept this product names, and what it is today. A concept is in the "
        "beta only when a test that proves it passed against the running service.</p>"
        "<table><thead><tr><th>Concept</th><th>Today</th><th>What you get</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>\n"
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


def _navigation(current: str) -> str:
    links = []
    for href, text in NAVIGATION:
        marker = ' aria-current="page"' if href == current else ""
        links.append(f'<a href="{html.escape(href)}"{marker}>{html.escape(text)}</a>')
    return "".join(links)


def _layout(template: str, *, title: str, description: str, route: str, body: str,
            site_digest: str, version: str) -> str:  # fmt: skip
    footer = (
        f"Agentic Postgres {html.escape(version)} · beta · "
        f'<a href="mailto:{INVITATION_ADDRESS}">{INVITATION_ADDRESS}</a>'
    )
    values = {
        "title": html.escape(title),
        "description": html.escape(description),
        "digest": site_digest,
        "nav": _navigation(route),
        "body": body,
        "footer": footer,
    }
    out = template
    for name, value in values.items():
        out = out.replace("{{" + name + "}}", value)
    return out


def build() -> dict[str, bytes]:
    """`{relative path: bytes}` for the whole site, or `SiteError`."""
    ledger = reality_ledger.load()
    template = TEMPLATE.read_text(encoding="utf-8")
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    site_digest = digest()
    files: dict[str, bytes] = {}
    for page in pages():
        check_page(page, ledger)
        stripped = page.body.strip()
        if stripped == "@pricing":
            body = f"<h1>{html.escape(page.title)}</h1>\n" + pricing_body()
        elif stripped == "@ledger":
            body = f"<h1>{html.escape(page.title)}</h1>\n" + ledger_body(ledger)
        else:
            body = render_markdown(page.source, page.body, page.body_line)
        target = page.route.strip("/")
        name = f"{target}/index.html" if target else "index.html"
        files[name] = _layout(
            template, title=page.title, description=page.description, route=page.route,
            body=body, site_digest=site_digest, version=version,
        ).encode("utf-8")  # fmt: skip
    files["404.html"] = _layout(
        template, title="Not found", description="This page does not exist.", route="",
        body=('<h1>Not found</h1>\n<p>Nothing is published at this address. Start from '
              '<a href="/">the home page</a> or <a href="/docs/">the documentation</a>.</p>\n'),
        site_digest=site_digest, version=version,
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

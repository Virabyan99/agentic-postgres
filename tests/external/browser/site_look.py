"""The look walk: every site page and the console's sign-in, read in a real Chromium.

Session 45 (ADR 0288, D2830, D2849). Run inside the pinned Playwright image by
`~/s45/run7/s45-look.sh` (never collected: no `test_` prefix). For each page of
the site -- the routes derived from `site/pages/**/*.md` by `site_build.route_of`'s
rule, never typed -- and the console's `/console/` signed out, at 390 x 844 and
1280 x 800, it waits for the `load` event, `document.fonts.ready` and a short settle
(never `networkidle`: the signed-out console leaves a refused refresh's 401 body
unread, `services/console/public/api.js` `call()`, and Chromium never reports an
unread fetch body finished -- measured live, D2858) and records:

- `scrollWidth` against `innerWidth` (the page must not scroll sideways);
- every request the page ATTEMPTED (Playwright's `request` event fires for a
  request the policy then blocks too -- rig 45b -- so this is the stricter
  reading of "no request leaves the origin");
- each font family's status (`loaded`, or `unloaded` where the page sets no
  text in it -- D2849 -- or `error`);
- after one Tab, the focused element's outline and whether it matches
  `:focus-visible` (rig 45b: the keyboard draws the ring, a click does not);
- the site page's `apg-site-digest`, and a screenshot path.

It holds no secret and signs nothing in, so the record (JSON, 0600) has nothing
to leak; `tests/external/test_session45_look.py` reads it through
`APG_LOOK_RECORD_FILE`. `--rehearse` marks a record made against a local build
and console image; `--plant-foreign` (rehearsal only) adds one request to a
third-party host to a page, which the record must name. `--dry` writes no record.

Exit codes: 0 walked; 2 usage; 4 a page could not be read.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Route, sync_playwright

VIEWPORTS = ((390, 844), (1280, 800))
FAMILIES = ("Schibsted Grotesk", "JetBrains Mono")
FOREIGN = "https://third-party.invalid/planted.png"
SETTLE_MS = 1500  # after `load` and the fonts: a script's late request is still attempted
INIT = """window.__violations = [];
document.addEventListener('securitypolicyviolation',
  (e) => window.__violations.push(e.effectiveDirective));"""
RING = """() => {
  const e = document.activeElement; const s = getComputedStyle(e);
  return {tag: e.tagName, style: s.outlineStyle, width: s.outlineWidth, color: s.outlineColor,
          focus_visible: e.matches(':focus-visible')};
}"""


def site_routes(pages_root: Path) -> list[str]:
    """`site_build.route_of` for every page: `index.md` -> `/`, `docs/x.md` -> `/docs/x/`."""
    routes = []
    for source in sorted(pages_root.rglob("*.md")):
        parts = source.relative_to(pages_root).with_suffix("").parts
        if parts[-1] == "index":
            parts = parts[:-1]
        routes.append("/" + "".join(f"{part}/" for part in parts))
    return routes


def write_private(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)


def read(page: Any, url: str, shots: Path | None, name: str) -> dict[str, Any]:
    attempted: list[str] = []
    page.on("request", lambda request: attempted.append(request.url))
    page.goto(url, wait_until="load")
    page.evaluate("document.fonts.ready.then(() => 1)")
    page.wait_for_timeout(SETTLE_MS)
    fonts = page.evaluate("[...document.fonts].map((f) => [f.family.replace(/\"/g, ''), f.status])")
    statuses: dict[str, str] = {}
    for family, status in fonts:
        statuses[family] = status if statuses.get(family) in (None, status) else "mixed"
    reading: dict[str, Any] = {
        "url": url,
        "scroll": page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]"),
        "requests": attempted,
        "fonts": {family: statuses.get(family, "absent") for family in FAMILIES},
        "violations": page.evaluate("window.__violations"),
        "digest": page.evaluate(
            "(document.querySelector('meta[name=apg-site-digest]') || {}).content || null"
        ),
    }
    page.mouse.click(1, 1)
    page.keyboard.press("Tab")
    reading["focus"] = page.evaluate(RING)
    if shots is not None:
        target = shots / f"{name}.png"
        page.screenshot(path=str(target), full_page=True)
        reading["screenshot"] = str(target)
    return reading


def walk(arguments: argparse.Namespace) -> int:
    site = arguments.site.rstrip("/")
    console = arguments.console.rstrip("/")
    record: dict[str, Any] = {
        "version": 1, "session": 45, "kind": "look",
        "mode": "rehearsal" if arguments.rehearse else "live",
        "site": site, "console": console, "source_commit": arguments.source_commit,
        "dry": arguments.dry, "pages": [], "started": time.time(),
    }  # fmt: skip
    routes = site_routes(arguments.pages_root)
    record["routes"] = routes
    exit_code = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        record["chromium"] = browser.version
        for width, height in VIEWPORTS:
            context = browser.new_context(viewport={"width": width, "height": height})
            context.add_init_script(INIT)
            if arguments.plant_foreign:
                # Rehearsal control: the home page gains one third-party image.
                def plant(route: Route) -> None:
                    response = route.fetch()
                    body = response.text().replace(
                        "</main>", f'<img src="{FOREIGN}" alt=""></main>', 1
                    )
                    route.fulfill(response=response, body=body)

                context.route(f"{site}/", plant)
            targets = [(f"{site}{route}", "site", route) for route in routes]
            targets.append((f"{console}/console/", "console", "/console/"))
            for url, surface, route in targets:
                name = f"{surface}{route.replace('/', '-').rstrip('-') or '-home'}-{width}"
                page = context.new_page()
                try:
                    reading = read(page, url, arguments.shots, name)
                except Exception as error:  # the record names the page, never a value
                    reading = {"url": url, "error": type(error).__name__}
                    exit_code = 4
                reading.update({"surface": surface, "route": route, "viewport": [width, height]})
                record["pages"].append(reading)
                page.close()
            context.close()
        browser.close()
    record["exit"] = exit_code
    record["seconds"] = round(time.time() - record.pop("started"), 1)
    if arguments.dry:
        print(f"site_look: dry walk exit {exit_code}; {len(record['pages'])} pages read, no record")
        return exit_code
    write_private(arguments.record, json.dumps(record, indent=1, sort_keys=True) + "\n")
    print(f"site_look: {record['mode']} walk exit {exit_code}; record {arguments.record}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="site_look", allow_abbrev=False)
    # The product's names since ADR 0299 (`site_build.SITE_URL` and the console's
    # origin, which this image cannot import; a launcher passes them).
    parser.add_argument("--site", default="https://nomipg.com")
    parser.add_argument("--console", default="https://control.nomipg.com")
    parser.add_argument("--pages-root", type=Path, default=Path("/repo/site/pages"))
    parser.add_argument("--record", type=Path)
    parser.add_argument("--shots", type=Path, default=None)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--rehearse", action="store_true")
    parser.add_argument("--plant-foreign", action="store_true")
    parser.add_argument("--dry", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.plant_foreign and not arguments.rehearse:
        print("site_look: --plant-foreign is a rehearsal's control", file=sys.stderr)
        return 2
    if not arguments.dry and (arguments.record is None or arguments.record.exists()):
        print(
            "site_look: give a --record that does not exist yet (one walk per record)",
            file=sys.stderr,
        )
        return 2
    if not arguments.dry and not arguments.rehearse and not arguments.source_commit:
        print(
            "site_look: a live record names the deployed commit (--source-commit)", file=sys.stderr
        )
        return 2
    return walk(arguments)


if __name__ == "__main__":
    raise SystemExit(main())

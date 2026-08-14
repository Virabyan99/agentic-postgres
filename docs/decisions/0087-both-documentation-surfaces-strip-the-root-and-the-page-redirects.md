# 0087 — Both documentation surfaces strip the root, and the page redirects

Status: accepted
Date: 2026-08-14
Session: 6, Run 10
Affects: ADR 0061, ADR 0069, D177, D187, D226, `services/docs/serve.py`, `naming.py`

## Context

Run 10 publishes `/docs/app` as a second surface of the existing documentation
service (D226). Two routers onto one container need the container to be able to
tell them apart, so the second surface's strip was going to be the documentation
**root** while the first kept stripping its whole page path. Measuring that
asymmetry found something about the surface that is already deployed.

### The measurement

Locked Traefik, the shipped rules, an upstream that reports the path it was
asked for. `index.html` references its assets **relatively** —
`<script src="standalone.js">` and `url: 'openapi.json'` — so what the browser
requests next depends on what it resolves those against, which depends on
whether the page URL ends in a slash.

    what the container is asked for
      GET /docs/rest       200   path "/"
      GET /docs/rest/      200   path "/"          <- indistinguishable

    the asset the page then asks for
      page at /docs/rest   -> base /docs/      -> GET /docs/standalone.js   404
      page at /docs/rest/  -> base /docs/rest/ -> GET /docs/rest/standalone.js  200

The control is the second line of each pair: the with-slash form resolves to a
path the router matches and serves, so the rig can tell a working reference from
a broken one.

**`routes.docs` publishes `https://<domain>/docs/rest`, without the slash.** So
the URL this deployment hands an operator serves an HTML document whose script
tag 404s, and the page does not render. Every proof this surface has ever had is
satisfied by that: `observe_docs` records `ready` on a **401**, the credential
tests assert 401 and 200 on the page URL, and `SEC-DOCS-001` is a byte scan of
the served files. D142 refused a browser harness for good reasons, and the cost
of that refusal is visible here for the first time — **nothing has ever asked
for the asset the page goes on to request.**

The container cannot repair this on its own, because `/docs/rest` and
`/docs/rest/` both arrive as `/`. The information needed to redirect has been
removed by the strip before the process sees it.

## Decision

**Both routers strip the documentation root, and the container serves each
surface under its own path.**

    /docs/rest   -> /rest    /docs/rest/  -> /rest/
    /docs/app    -> /app     /docs/app/   -> /app/

`serve.py`'s route table is keyed by those paths, and the slash-less form gets a
**301 with a relative `Location`** — `rest/` from `/rest`, which a browser
resolves against `/docs/rest` to give `/docs/rest/`. Relative because the
container does not know the published prefix and must not learn it: a
`Location: /docs/rest/` would be the second derivation of a path ADR 0061 exists
to keep singular, and it would be wrong the moment a project published the page
somewhere else.

One consequence is a simplification rather than a cost: **the two routers share
one strip-prefix middleware**, because they now strip the same thing. The
`app_docs_stripprefix` name added earlier in this run is removed again.

`HEALTH_PATH` stays at the container root. The healthcheck reaches it directly
on `127.0.0.1:8080` and never passes the edge, so it is not under either prefix
and must not be.

## Alternatives

**Publish the URL with a trailing slash.** One character, and it makes the link
this deployment hands out work. Refused as the whole fix: a person who types the
URL without the slash still gets a page that does not render, and the failure is
invisible — 200, correct HTML, blank screen. It is worth doing *as well*, and
`routes.docs` keeps its slash-less form only because `Path()` in the router rule
matches it and the redirect now handles it.

**Keep the REST strip and give the app surface the asymmetric one.** What this
run set out to do. It works for the new surface, whose container-side path
retains the distinction, and it leaves the deployed surface broken. Refused: the
defect is real and this is the run that found it.

**Absolute asset references in the HTML.** `<script src="/docs/rest/standalone.js">`
resolves correctly from either form. Refused: it puts the published path inside
the build context, where `naming.py` cannot reach it, and D177 is precisely what
happens when a documentation path is derived in two places — the copy carrying a
comment saying it was kept in step was the one that had drifted.

**A browser-driven proof.** Still refused, still for D142's reasons. The
measurement that found this needed no browser: it asked for the URL the page's
own markup names. That is the proof this run adds, and it holds for every
visitor rather than for the one that was driven.

## Consequences

- A deployed surface changes its container-side paths, so both projects need a
  redeploy for the documentation page to keep working. The router rules and the
  published URLs are unchanged.
- `serve.py` gains a redirect and a second document, and is still a route table
  with no path joining, no directory walk and no way to name a file that is not
  listed.
- **The proof this repository was missing is now cheap and is added:** fetch the
  page, extract every `src` and `url` its markup names, and fetch each of those
  through the edge. It is a `live_host` proof for both surfaces, and it would
  have gone red on the deployment that has been running since Run 9a.
- The question that found it generalises. Run 10's standing pair — what would
  have to break for this to go red, and has it run at all since the thing it
  measures changed — gains a third: **does the proof ask for what the artifact
  itself asks for?**

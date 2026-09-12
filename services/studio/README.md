# services/studio

Three files, served by `bin/studio.py` from the machine a human is sitting at.

**This is not a container and not a service.** Every other directory under
`services/` builds an image that a deploy runs; this one is read by an operator
command and handed to a browser on `127.0.0.1`. There is no Dockerfile here on
purpose: a container would publish through Docker's proxy and would make the
human's token cross a container boundary for a page of tables (ADR 0205).

**There is no `package.json`, no lockfile, no bundle and no build step.** The
SBOM for this directory is the Python standard library and these three files.
`services/docs` vendors 230 MB to ship one 2 MB bundle because a schema
*reference* wants Scalar's renderer; Studio's views are tables and forms, and a
dependency that is not here needs no audit, no lock and no CVE watch (D1249).

The page is served under a Content-Security-Policy stricter than the
documentation page's — `default-src 'none'; script-src 'self'; style-src 'self';
connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none';
frame-ancestors 'none'` — with no `'unsafe-inline'` anywhere, because nothing
here writes styles or script at runtime. `test_studio_assets.py` is what keeps
that true: no external reference, no inline `<script>`, no `style=` attribute,
no `on*=` handler, and no file in this directory but these four.

**The page holds no token.** It holds a launch cookie (`HttpOnly`,
`SameSite=Strict`) and sends `X-Apg-Studio: 1` on every call to `/__apg/`; the
process checks the cookie, the `Host`, the `Origin` and that header, refuses
`OPTIONS`, and makes every upstream request itself. Nothing this page sends
decides anything: a relation outside the surface, an operator outside the
contract and a revocation confirmation that is not the agent's id are all
refused in the process, because a control the page enforces is not a boundary
(ADR 0140).
